from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from uuid import uuid4

logger = logging.getLogger("jarvis_core.chat")

from fastapi import HTTPException, status
from jarvis_contracts import ErrorResponse
from starlette.websockets import WebSocket

from ai import AIService
from core.db.db_connection import DBClient
from core.db.db_operations import (
    add_message,
    create_user_model_config,
    create_memory_item,
    create_user_persona,
    ensure_default_persona_for_user,
    ensure_user_settings,
    get_active_model_for_user,
    get_latest_chat_summary,
    get_model_config_by_id_for_user,
    get_or_create_session_for_user,
    get_selected_persona_for_user,
    get_user_ai_selection,
    get_user_settings,
    list_recent_messages,
    list_memory_items,
    list_user_personas,
    select_user_persona,
    list_user_model_configs,
    set_user_ai_selection,
    update_user_persona,
    update_user_model_config,
)
from router import choose_route
from safety import safety_gate

from .schemas import (
    ChatOnceRequest,
    ModelConfigUpsertRequest,
    MemoryCreateRequest,
    ModelSelectionUpsertRequest,
    PersonaSelectionRequest,
    PersonaUpsertRequest,
)


# ── 베이스 시스템 프롬프트 ─────────────────────────────────
# 페르소나보다 먼저 적용되는 JARVIS 핵심 정체성·규칙.
# 모든 대화(realtime, deep)에서 항상 포함된다.
# Workbench UI에서 수정 가능 (prompts.yaml → base_system 키).
from core.config.prompt_loader import load_prompt as _load_prompt

_BASE_SYSTEM_PROMPT_FALLBACK = """\
You are JARVIS — an intelligent AI assistant system.

## Core rules
1. Always respond in the same language the user uses. If the user writes in Korean, respond in Korean. If English, respond in English.
2. Be accurate. If you are unsure, say so honestly rather than guessing.
3. Be concise but thorough. Avoid unnecessary filler, but include all relevant details.
4. When the user asks you to do something (open apps, search, create files, etc.), focus on carrying out the action rather than explaining what you would do.
5. Respect privacy. Never ask for sensitive personal information unless the user offers it.
6. If a request is ambiguous, ask one clarifying question before proceeding.

## Capabilities
- General conversation and Q&A
- Web search for real-time information (weather, news, prices, etc.)
- Deep analysis and multi-step reasoning
- Remote PC control: terminal commands, app launch, file operations, mouse/keyboard, screenshots
- Planning and step-by-step task execution

## Response style
- Use markdown formatting when it improves readability (lists, bold, code blocks).
- For simple questions, answer directly without unnecessary structure.
- For complex tasks, break down into clear steps.
"""


def _get_base_system_prompt() -> str:
    """prompts.yaml에서 base_system을 읽고, 없으면 fallback을 반환한다."""
    loaded = _load_prompt("base_system")
    return loaded if loaded else _BASE_SYSTEM_PROMPT_FALLBACK


class ChatService:
    def __init__(self, db: DBClient, ai_service: AIService) -> None:
        self.db = db
        self.ai_service = ai_service

    def _fallback_model_config(self) -> dict[str, str | bool | None]:
        return {
            "id": "default-local",
            "provider_mode": "local",
            "provider_name": "local-default",
            "model_name": "local-stub",
            "api_key": None,
            "endpoint": None,
            "is_active": True,
            "is_default": True,
            "supports_stream": True,
            "supports_realtime": False,
            "transport": "http_sse",
            "input_modalities": "text",
            "output_modalities": "text",
        }

    def _select_model_config(
        self, user_id: str, purpose: str
    ) -> dict[str, str | bool | None]:
        selected_id: str | None = None
        selection = get_user_ai_selection(self.db, user_id=user_id)
        if selection is not None:
            if purpose == "deep":
                selected_id = selection.get("deep_model_config_id")
            else:
                selected_id = selection.get("realtime_model_config_id")

        if selected_id:
            selected_model = get_model_config_by_id_for_user(
                self.db, user_id=user_id, model_config_id=selected_id
            )
            if selected_model is not None and bool(
                selected_model.get("is_active", True)
            ):
                logger.info(
                    "[chat] model selected purpose=%s provider=%s/%s model=%s config_id=%s user=%s",
                    purpose,
                    selected_model["provider_mode"],
                    selected_model["provider_name"],
                    selected_model["model_name"],
                    selected_model["id"],
                    user_id,
                )
                return selected_model

        config = get_active_model_for_user(self.db, user_id=user_id)
        result = config or {**self._fallback_model_config()}
        logger.info(
            "[chat] model fallback purpose=%s provider=%s/%s model=%s user=%s",
            purpose,
            result.get("provider_mode"),
            result.get("provider_name"),
            result.get("model_name"),
            user_id,
        )
        return result

    def _resolve_route(self, message: str, task_type: str, route_override: str | None) -> str:
        if route_override in {"realtime", "deep"}:
            return route_override
        return choose_route(message, task_type)

    def _build_prompt_context(
        self, *, user_id: str, chat_id: str, route: str
    ) -> tuple[str | None, list[dict[str, str]]]:
        settings = ensure_user_settings(self.db, user_id=user_id)
        persona = get_selected_persona_for_user(self.db, user_id=user_id)
        if persona is None:
            persona = ensure_default_persona_for_user(self.db, user_id=user_id)

        memories = list_memory_items(self.db, user_id=user_id, chat_id=chat_id, limit=5)
        summary = get_latest_chat_summary(self.db, chat_id=chat_id)
        recent_messages = list_recent_messages(self.db, chat_id, limit=12)
        metadata = settings.get("metadata", {}) if isinstance(settings, dict) else {}
        persona_hint = metadata.get("persona_hint") if isinstance(metadata, dict) else None
        custom_instructions = metadata.get("custom_instructions") if isinstance(metadata, dict) else None
        memory_lines = [f"- ({item['type']}/{item['importance']}) {item['content']}" for item in memories]
        route_line = (
            "Use deeper analysis, surface assumptions, and be explicit about tradeoffs."
            if route == "deep"
            else "Respond with low latency and concise, directly useful guidance."
        )
        system_parts = [
            _get_base_system_prompt(),
            f"## Persona\n{persona['prompt_template']}",
            f"Tone: {persona['tone'] or 'balanced'}",
            f"Route mode: {route}",
            f"User locale: {settings['locale']}",
            f"User timezone: {settings['timezone']}",
            f"Preferred response style: {settings['response_style']}",
            route_line,
        ]
        if persona_hint:
            system_parts.append(f"Persona hint from user settings: {persona_hint}")
        if custom_instructions:
            system_parts.append(f"Custom user instructions: {custom_instructions}")
        if memory_lines:
            system_parts.append("Relevant memory:\n" + "\n".join(memory_lines))
        if summary is not None and summary.get("summary_text"):
            system_parts.append(summary["summary_text"])
        system_prompt = "\n\n".join(system_parts)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(recent_messages)
        return system_prompt, messages

    async def request_once(
        self, body: ChatOnceRequest, request_id: str, user_id: str, email: str
    ) -> dict[str, str] | ErrorResponse:
        allowed, reason = safety_gate(body.message, body.confirm)
        if not allowed:
            return ErrorResponse(
                error_code="SAFETY_BLOCKED",
                message=reason or "blocked",
                request_id=request_id,
            )

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing user id in auth token",
            )

        session = get_or_create_session_for_user(
            self.db, user_id=user_id, email=email or "unknown@local.jarvis"
        )
        session_id = session["id"]
        route = self._resolve_route(body.message, body.task_type, body.route_override)
        system_prompt, prompt_messages = self._build_prompt_context(
            user_id=user_id, chat_id=session_id, route=route
        )
        add_message(self.db, session_id, "user", body.message)

        purpose = "deep" if route == "deep" else "realtime"
        selected = self._select_model_config(user_id=user_id, purpose=purpose)
        ai_result = await self.ai_service.respond_once(
            {
                "message": body.message,
                "route": route,
                "request_id": request_id,
                "provider_mode": selected["provider_mode"],
                "provider_name": selected["provider_name"],
                "model_name": selected["model_name"],
                "api_key": selected.get("api_key"),
                "endpoint": selected.get("endpoint"),
                "system_prompt": system_prompt,
                "messages": [
                    *prompt_messages,
                    {"role": "user", "content": body.message},
                ],
            }
        )
        add_message(self.db, session_id, "assistant", ai_result["content"])
        return {
            "request_id": request_id,
            "route": route,
            "provider_mode": ai_result["provider_mode"],
            "provider_name": ai_result["provider_name"],
            "model_name": ai_result["model_name"],
            "content": ai_result["content"],
        }

    # ── realtime 함수에서 쓸 함수들 ───────────────────────────────────────────

    @staticmethod
    def _parse_ws_event(raw: str) -> dict | None:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    async def _cancel_task(task: asyncio.Task[None] | None) -> None:
        """Cancel an asyncio task and suppress CancelledError."""
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _interrupt_generation(
        self,
        websocket: WebSocket,
        generation: asyncio.Task[None] | None,
        rt_session_id: str | None,
        request_payload: dict[str, object] | None,
        reason: str,
    ) -> None:
        """Cancel the active generation task and notify the client."""
        await self._cancel_task(generation)
        if rt_session_id and request_payload:
            await self.ai_service.cancel_generation(request_payload, rt_session_id)
        payload: dict[str, str] = {"type": "interrupted", "content": reason}
        if request_payload:
            rid = request_payload.get("request_id")
            if rid:
                payload["request_id"] = str(rid)
        await websocket.send_json(payload)

    async def _stream_generation(
        self,
        websocket: WebSocket,
        request_payload: dict[str, object],
        rt_session_id: str,
        request_id: str,
        chat_session_id: str,
    ) -> None:
        """Stream tokens from the AI service to the WebSocket client."""
        chunks: list[str] = []
        try:
            async for token in self.ai_service.realtime_session_send(
                request_payload, rt_session_id
            ):
                chunks.append(token)
                await websocket.send_json(
                    {
                        "type": "assistant_delta",
                        "request_id": request_id,
                        "content": token,
                    }
                )
        except asyncio.CancelledError:
            return
        except Exception:
            await websocket.send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "content": "generation failed",
                }
            )
            return

        full = "".join(chunks).strip()
        if full:
            add_message(self.db, chat_session_id, "assistant", full)
        await websocket.send_json({"type": "assistant_done", "request_id": request_id})

    # ── run_realtime ────────────────────────────────────────────

    async def run_realtime(
        self, websocket: WebSocket, user_id: str, email: str
    ) -> None:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing user id in auth token",
            )

        await websocket.accept()
        await websocket.send_json({"type": "ready"})

        session = get_or_create_session_for_user(
            self.db, user_id=user_id, email=email or "unknown@local.jarvis"
        )
        chat_session_id = session["id"]
        active_generation: asyncio.Task[None] | None = None
        active_rt_session_id: str | None = None
        active_request: dict[str, object] | None = None
        realtime_session_request: dict[str, object] | None = None

        try:
            while True:
                raw = await websocket.receive_text()
                event = self._parse_ws_event(raw)
                if event is None:
                    await websocket.send_json(
                        {"type": "error", "content": "invalid json"}
                    )
                    continue

                event_type = str(event.get("type", ""))
                if event_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if event_type == "interrupt":
                    await self._interrupt_generation(
                        websocket,
                        active_generation,
                        active_rt_session_id,
                        active_request,
                        reason="user_interrupt",
                    )
                    active_generation = None
                    continue

                if event_type != "user_message":
                    await websocket.send_json(
                        {"type": "error", "content": "unsupported event type"}
                    )
                    continue

                # Barge-in: new message interrupts in-flight generation
                if active_generation is not None and not active_generation.done():
                    await self._interrupt_generation(
                        websocket,
                        active_generation,
                        active_rt_session_id,
                        active_request,
                        reason="barge_in",
                    )
                    active_generation = None

                content = str(event.get("content", "")).strip()
                task_type = str(event.get("task_type", "general"))
                confirm = bool(event.get("confirm", False))
                if not content:
                    await websocket.send_json(
                        {"type": "error", "content": "empty content"}
                    )
                    continue

                allowed, reason = safety_gate(content, confirm)
                if not allowed:
                    await websocket.send_json(
                        {"type": "error", "content": reason or "blocked"}
                    )
                    continue

                selected = self._select_model_config(
                    user_id=user_id, purpose="realtime"
                )
                if not bool(selected.get("supports_realtime", False)):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "content": "selected model does not support realtime",
                        }
                    )
                    continue

                route = self._resolve_route(
                    content, task_type, event.get("route_override")
                )
                request_id = str(uuid4())
                system_prompt, prompt_messages = self._build_prompt_context(
                    user_id=user_id, chat_id=chat_session_id, route=route
                )
                add_message(self.db, chat_session_id, "user", content)
                request_payload: dict[str, object] = {
                    "message": content,
                    "route": route,
                    "request_id": request_id,
                    "provider_mode": str(selected["provider_mode"]),
                    "provider_name": str(selected["provider_name"]),
                    "model_name": str(selected["model_name"]),
                    "api_key": selected.get("api_key"),
                    "endpoint": selected.get("endpoint"),
                    "system_prompt": system_prompt,
                    "messages": [
                        *prompt_messages,
                        {"role": "user", "content": content},
                    ],
                }
                active_request = request_payload

                if active_rt_session_id is None:
                    active_rt_session_id = await self.ai_service.realtime_session_start(
                        request_payload
                    )
                    realtime_session_request = request_payload

                await websocket.send_json(
                    {
                        "type": "meta",
                        "request_id": request_id,
                        "route": route,
                        "provider_mode": selected["provider_mode"],
                        "provider_name": selected["provider_name"],
                        "model_name": selected["model_name"],
                        "session_id": active_rt_session_id,
                    }
                )

                active_generation = asyncio.create_task(
                    self._stream_generation(
                        websocket,
                        request_payload,
                        active_rt_session_id or "",
                        request_id,
                        chat_session_id,
                    )
                )
        finally:
            await self._cancel_task(active_generation)
            if active_rt_session_id and realtime_session_request:
                await self.ai_service.realtime_session_close(
                    realtime_session_request, active_rt_session_id
                )

    async def run_realtime_sse(
        self,
        message: str,
        task_type: str,
        confirm: bool,
        route_override: str | None,
        request_id: str,
        user_id: str,
        email: str,
    ) -> AsyncGenerator[str, None]:
        """SSE 스트리밍: AI 제공자에서 토큰을 받아 SSE 이벤트로 yield."""
        if not user_id:
            yield f"event: error\ndata: {json.dumps({'content': 'missing user id'})}\n\n"
            return

        allowed, reason = safety_gate(message, confirm)
        if not allowed:
            yield f"event: error\ndata: {json.dumps({'content': reason or 'blocked'})}\n\n"
            return

        session = get_or_create_session_for_user(
            self.db, user_id=user_id, email=email or "unknown@local.jarvis"
        )
        session_id = session["id"]
        route = self._resolve_route(message, task_type, route_override)
        system_prompt, prompt_messages = self._build_prompt_context(
            user_id=user_id, chat_id=session_id, route=route
        )
        add_message(self.db, session_id, "user", message)

        purpose = "deep" if route == "deep" else "realtime"
        selected = self._select_model_config(user_id=user_id, purpose=purpose)

        if not bool(selected.get("supports_stream", False)):
            yield f"event: error\ndata: {json.dumps({'content': 'selected model does not support streaming'})}\n\n"
            return

        request_payload = {
            "message": message,
            "route": route,
            "request_id": request_id,
            "provider_mode": str(selected["provider_mode"]),
            "provider_name": str(selected["provider_name"]),
            "model_name": str(selected["model_name"]),
            "api_key": selected.get("api_key"),
            "endpoint": selected.get("endpoint"),
            "system_prompt": system_prompt,
            "messages": [
                *prompt_messages,
                {"role": "user", "content": message},
            ],
        }

        # meta event
        meta = {
            "type": "meta",
            "request_id": request_id,
            "route": route,
            "provider_mode": selected["provider_mode"],
            "provider_name": selected["provider_name"],
            "model_name": selected["model_name"],
        }
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"

        # stream tokens
        chunks: list[str] = []
        try:
            async for token in self.ai_service.stream_tokens(request_payload):
                chunks.append(token)
                yield f"event: assistant_delta\ndata: {json.dumps({'request_id': request_id, 'content': token})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'request_id': request_id, 'content': str(exc)})}\n\n"
            return

        full = "".join(chunks).strip()
        if full:
            add_message(self.db, session_id, "assistant", full)

        yield f"event: assistant_done\ndata: {json.dumps({'request_id': request_id, 'content': full})}\n\n"

    async def close_realtime_session(
        self, request: dict[str, object], realtime_session_id: str
    ) -> None:
        await self.ai_service.realtime_session_close(request, realtime_session_id)

    def create_model_config(
        self, user_id: str, body: ModelConfigUpsertRequest
    ) -> dict[str, str | bool | None]:
        return create_user_model_config(
            self.db,
            user_id=user_id,
            provider_mode=body.provider_mode,
            provider_name=body.provider_name,
            model_name=body.model_name,
            api_key=body.api_key,
            endpoint=body.endpoint,
            is_default=body.is_default,
            supports_stream=body.supports_stream,
            supports_realtime=body.supports_realtime,
            transport=body.transport,
            input_modalities=body.input_modalities,
            output_modalities=body.output_modalities,
        )

    def list_model_configs(self, user_id: str) -> list[dict[str, str | bool | None]]:
        return list_user_model_configs(self.db, user_id=user_id)

    def update_model_config(
        self,
        user_id: str,
        model_config_id: str,
        body: ModelConfigUpsertRequest,
    ) -> dict[str, str | bool | None]:
        result = update_user_model_config(
            self.db,
            user_id=user_id,
            model_config_id=model_config_id,
            provider_mode=body.provider_mode,
            provider_name=body.provider_name,
            model_name=body.model_name,
            api_key=body.api_key,
            endpoint=body.endpoint,
            is_default=body.is_default,
            supports_stream=body.supports_stream,
            supports_realtime=body.supports_realtime,
            transport=body.transport,
            input_modalities=body.input_modalities,
            output_modalities=body.output_modalities,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="model config not found")
        return result

    def set_model_selection(
        self, user_id: str, body: ModelSelectionUpsertRequest
    ) -> dict[str, str | None]:
        if body.realtime_model_config_id is not None:
            realtime = get_model_config_by_id_for_user(
                self.db, user_id=user_id, model_config_id=body.realtime_model_config_id
            )
            if realtime is None:
                raise HTTPException(
                    status_code=400, detail="invalid realtime_model_config_id"
                )
        if body.deep_model_config_id is not None:
            deep = get_model_config_by_id_for_user(
                self.db, user_id=user_id, model_config_id=body.deep_model_config_id
            )
            if deep is None:
                raise HTTPException(
                    status_code=400, detail="invalid deep_model_config_id"
                )

        return set_user_ai_selection(
            self.db,
            user_id=user_id,
            realtime_model_config_id=body.realtime_model_config_id,
            deep_model_config_id=body.deep_model_config_id,
        )

    def get_model_selection(self, user_id: str) -> dict[str, str | None]:
        selection = get_user_ai_selection(self.db, user_id=user_id)
        if selection is not None:
            return selection
        return {
            "realtime_model_config_id": None,
            "deep_model_config_id": None,
        }

    def list_personas(self, user_id: str) -> list[dict[str, object]]:
        ensure_default_persona_for_user(self.db, user_id=user_id)
        return list_user_personas(self.db, user_id=user_id)

    def create_persona(
        self, user_id: str, body: PersonaUpsertRequest
    ) -> dict[str, object]:
        return create_user_persona(
            self.db,
            user_id=user_id,
            name=body.name,
            description=body.description,
            prompt_template=body.prompt_template,
            tone=body.tone,
            alias=body.alias,
        )

    def update_persona(
        self, user_id: str, user_persona_id: str, body: PersonaUpsertRequest
    ) -> dict[str, object]:
        result = update_user_persona(
            self.db,
            user_id=user_id,
            user_persona_id=user_persona_id,
            name=body.name,
            description=body.description,
            prompt_template=body.prompt_template,
            tone=body.tone,
            alias=body.alias,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="persona not found")
        return result

    def select_persona(
        self, user_id: str, body: PersonaSelectionRequest
    ) -> dict[str, object]:
        result = select_user_persona(
            self.db, user_id=user_id, user_persona_id=body.user_persona_id
        )
        if result is None:
            raise HTTPException(status_code=404, detail="persona not found")
        return result

    def list_memory(self, user_id: str, chat_id: str | None = None) -> list[dict[str, object]]:
        return list_memory_items(self.db, user_id=user_id, chat_id=chat_id, limit=50)

    def create_memory(
        self, user_id: str, body: MemoryCreateRequest
    ) -> dict[str, object]:
        return create_memory_item(
            self.db,
            user_id=user_id,
            chat_id=body.chat_id,
            memory_type=body.type,
            content=body.content,
            importance=body.importance,
            source_message_id=body.source_message_id,
            expires_at=body.expires_at,
        )
