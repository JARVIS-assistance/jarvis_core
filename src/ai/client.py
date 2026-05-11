from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import aiohttp

from .schemas import AIRequest, AIResponse, AIStreamChunk

logger = logging.getLogger(__name__)


class AIClient(Protocol):
    async def stream_chat(
        self, message: str, route: str, request_id: str
    ) -> AsyncGenerator[AIStreamChunk, None]: ...

    async def respond_once(self, request: AIRequest) -> AIResponse: ...

    async def stream_tokens(self, request: AIRequest) -> AsyncGenerator[str, None]: ...

    async def realtime_session_start(self, request: AIRequest) -> str: ...

    async def realtime_session_send(
        self, realtime_session_id: str, request: AIRequest
    ) -> AsyncGenerator[str, None]: ...

    async def realtime_session_close(self, realtime_session_id: str) -> None: ...

    async def cancel_generation(self, realtime_session_id: str) -> None: ...


class StubAIClient:
    async def stream_chat(
        self, message: str, route: str, request_id: str
    ) -> AsyncGenerator[AIStreamChunk, None]:
        yield {"type": "meta", "route": route, "request_id": request_id}
        yield {"type": "token", "content": "[stub] reasoning started"}
        yield {"type": "done", "content": "[stub] response complete"}

    async def respond_once(self, request: AIRequest) -> AIResponse:
        system_prefix = ""
        if request.get("system_prompt"):
            system_prefix = f"[system:{request['system_prompt'][:80]}] "
        return {
            "provider_mode": request["provider_mode"],
            "provider_name": request["provider_name"],
            "model_name": request["model_name"],
            "content": f"[stub:{request['provider_mode']}] {system_prefix}{request['message']}",
        }

    async def stream_tokens(self, request: AIRequest) -> AsyncGenerator[str, None]:
        result = await self.respond_once(request)
        for token in result["content"].split():
            yield token + " "

    async def realtime_session_start(self, request: AIRequest) -> str:
        return str(uuid4())

    async def realtime_session_send(
        self, realtime_session_id: str, request: AIRequest
    ) -> AsyncGenerator[str, None]:
        async for token in self.stream_tokens(request):
            yield token

    async def realtime_session_close(self, realtime_session_id: str) -> None:
        return None

    async def cancel_generation(self, realtime_session_id: str) -> None:
        return None


class TokenAIClient(StubAIClient):
    @staticmethod
    def _build_messages(request: AIRequest) -> list[dict[str, str]]:
        if request.get("messages"):
            return [
                {"role": message["role"], "content": message["content"]}
                for message in request["messages"]
            ]
        messages: list[dict[str, str]] = []
        if request.get("system_prompt"):
            messages.append({"role": "system", "content": str(request["system_prompt"])})
        messages.append({"role": "user", "content": request["message"]})
        return messages

    @staticmethod
    def _build_prompt_text(request: AIRequest) -> str:
        parts: list[str] = []
        if request.get("system_prompt"):
            parts.append(f"System:\n{request['system_prompt']}")
        parts.append(f"User:\n{request['message']}")
        return "\n\n".join(parts)

    @staticmethod
    def _post_json(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 60
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url=url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    @staticmethod
    def _openai_key(explicit: str | None) -> str | None:
        return explicit or os.getenv("OPENAI_API_KEY")

    @staticmethod
    def _gemini_key(explicit: str | None) -> str | None:
        return explicit or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    async def respond_once(self, request: AIRequest) -> AIResponse:
        provider = request["provider_name"].lower()
        try:
            if provider in {"openai", "chatgpt"}:
                key = self._openai_key(request.get("api_key"))
                if not key:
                    raise ValueError("missing OpenAI API key")
                endpoint = (
                    request.get("endpoint")
                    or "https://api.openai.com/v1/chat/completions"
                )
                data = self._post_json(
                    endpoint,
                    {
                        "model": request["model_name"],
                        "messages": self._build_messages(request),
                    },
                    {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {key}",
                    },
                )
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if not content:
                    raise ValueError("empty OpenAI response")
                return {
                    "provider_mode": "token",
                    "provider_name": request["provider_name"],
                    "model_name": request["model_name"],
                    "content": str(content),
                }

            if provider == "gemini":
                key = self._gemini_key(request.get("api_key"))
                if not key:
                    raise ValueError("missing Gemini API key")
                base = (
                    request.get("endpoint")
                    or "https://generativelanguage.googleapis.com/v1beta/models"
                )
                endpoint = f"{base}/{request['model_name']}:generateContent?key={key}"
                data = self._post_json(
                    endpoint,
                    {
                        "contents": [
                            {
                                "parts": [
                                    {"text": self._build_prompt_text(request)}
                                ]
                            }
                        ]
                    },
                    {"Content-Type": "application/json"},
                )
                parts = (
                    data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                )
                content = parts[0].get("text") if parts else None
                if not content:
                    raise ValueError("empty Gemini response")
                return {
                    "provider_mode": "token",
                    "provider_name": request["provider_name"],
                    "model_name": request["model_name"],
                    "content": str(content),
                }

            raise ValueError(f"unsupported token provider: {request['provider_name']}")
        except (
            HTTPError,
            URLError,
            TimeoutError,
            KeyError,
            IndexError,
            ValueError,
        ) as exc:
            return {
                "provider_mode": "token",
                "provider_name": request["provider_name"],
                "model_name": request["model_name"],
                "content": f"[provider-error] {exc}",
            }


class LocalLLMAIClient(StubAIClient):
    @staticmethod
    def _build_messages(request: AIRequest) -> list[dict[str, str]]:
        if request.get("messages"):
            return [
                {"role": message["role"], "content": message["content"]}
                for message in request["messages"]
            ]
        messages: list[dict[str, str]] = []
        if request.get("system_prompt"):
            messages.append({"role": "system", "content": str(request["system_prompt"])})
        messages.append({"role": "user", "content": request["message"]})
        return messages

    @staticmethod
    def _build_prompt_text(request: AIRequest) -> str:
        parts: list[str] = []
        system_prompt = request.get("system_prompt")
        if system_prompt:
            parts.append(f"System:\n{system_prompt}")
        parts.append(f"User:\n{request['message']}")
        return "\n\n".join(parts)

    @staticmethod
    def _resolve_ollama_endpoint(raw_endpoint: str | None) -> tuple[str, str]:
        raw = (raw_endpoint or "http://localhost:11434").rstrip("/")
        path = urlparse(raw).path.rstrip("/")
        if path.endswith("/api/chat") or path.endswith("/chat"):
            return raw, "chat"
        if path.endswith("/api/generate") or path.endswith("/generate"):
            return raw, "generate"
        return f"{raw}/api/generate", "generate"

    @staticmethod
    def _post_json(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 120
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers.setdefault("User-Agent", "JARVIS/1.0")
        logger.info("[AI-REQUEST] POST %s", url)
        logger.info("[AI-REQUEST] headers=%s", headers)
        logger.info("[AI-REQUEST] payload=%s", json.dumps(payload, ensure_ascii=False))
        req = Request(url=url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
                logger.info("[AI-RESPONSE] status=%s body=%s", response.status, raw[:500])
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            logger.error(
                "[AI-ERROR] %s %s | status=%s body=%s",
                exc, url, exc.code, error_body[:500],
            )
            raise

    async def _respond_ollama(self, request: AIRequest) -> AIResponse:
        endpoint, endpoint_type = self._resolve_ollama_endpoint(request.get("endpoint"))
        if endpoint_type == "chat":
            payload = {
                "model": request["model_name"],
                "messages": self._build_messages(request),
                "stream": False,
            }
        else:
            payload = {
                "model": request["model_name"],
                "prompt": self._build_prompt_text(request),
                "stream": False,
            }
        data = self._post_json(
            endpoint,
            payload,
            {"Content-Type": "application/json"},
        )
        if endpoint_type == "chat":
            content = data.get("message", {}).get("content")
        else:
            content = data.get("response")
        if not content:
            raise ValueError("empty Ollama response")
        return {
            "provider_mode": "local",
            "provider_name": request["provider_name"],
            "model_name": request["model_name"],
            "content": str(content),
        }

    def _resolve_openai_compat_endpoint(self, raw_endpoint: str) -> str:
        """Resolve full URL for OpenAI-compatible endpoint."""
        path = urlparse(raw_endpoint).path
        if path and path != "/" and "/completions" in path:
            return raw_endpoint
        return f"{raw_endpoint}/v1/chat/completions"

    async def _respond_openai_compat(self, request: AIRequest) -> AIResponse:
        raw_endpoint = (request.get("endpoint") or "http://localhost:8080").rstrip("/")
        path = urlparse(raw_endpoint).path
        if path and path != "/" and "/completions" in path:
            # Full URL with path provided (e.g. http://host/engines/v1/chat/completions)
            endpoint = raw_endpoint
        else:
            # Base URL only — append default OpenAI-compatible path
            endpoint = f"{raw_endpoint}/v1/chat/completions"
        model = request["model_name"]
        data = self._post_json(
            endpoint,
            {
                "model": model,
                "messages": self._build_messages(request),
                "stream": False,
            },
            {"Content-Type": "application/json"},
        )
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise ValueError("empty response from local provider")
        return {
            "provider_mode": "local",
            "provider_name": request["provider_name"],
            "model_name": model,
            "content": str(content),
        }

    # ── SSE 비동기 스트리밍 ──────────────────────────────

    async def stream_tokens(self, request: AIRequest) -> AsyncGenerator[str, None]:
        """aiohttp로 OpenAI-compatible SSE 엔드포인트에서 토큰을 실시간 스트리밍."""
        provider = request["provider_name"].lower()
        if provider == "ollama":
            async for token in self._stream_ollama_tokens(request):
                yield token
            return

        raw_endpoint = (request.get("endpoint") or "http://localhost:8080").rstrip("/")
        endpoint = self._resolve_openai_compat_endpoint(raw_endpoint)
        model = request["model_name"]
        payload = {
            "model": model,
            "messages": self._build_messages(request),
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "JARVIS/1.0",
        }
        logger.info("[AI-SSE-REQUEST] POST %s", endpoint)

        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("[AI-SSE-ERROR] status=%s body=%s", resp.status, body[:300])
                        yield f"[provider-error] HTTP {resp.status}"
                        return

                    count = 0
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                        if not line.startswith("data: "):
                            continue
                        data_str = line[len("data: "):]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                count += 1
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
                    logger.info("[AI-SSE-RESPONSE] streamed %d tokens", count)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("[AI-SSE-ERROR] %s", exc)
            yield f"[provider-error] {exc}"

    # ── respond_once / realtime (unchanged pattern) ─────────────────

    async def _stream_ollama_tokens(
        self,
        request: AIRequest,
    ) -> AsyncGenerator[str, None]:
        endpoint, endpoint_type = self._resolve_ollama_endpoint(request.get("endpoint"))
        if endpoint_type == "chat":
            payload = {
                "model": request["model_name"],
                "messages": self._build_messages(request),
                "stream": True,
            }
        else:
            payload = {
                "model": request["model_name"],
                "prompt": self._build_prompt_text(request),
                "stream": True,
            }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
            "User-Agent": "JARVIS/1.0",
        }
        logger.info("[AI-OLLAMA-STREAM-REQUEST] POST %s", endpoint)

        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            "[AI-OLLAMA-STREAM-ERROR] status=%s body=%s",
                            resp.status,
                            body[:300],
                        )
                        yield f"[provider-error] HTTP {resp.status}"
                        return

                    count = 0
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if endpoint_type == "chat":
                            token = chunk.get("message", {}).get("content")
                        else:
                            token = chunk.get("response")
                        if isinstance(token, str) and token:
                            count += 1
                            yield token
                        if chunk.get("done") is True:
                            break
                    logger.info("[AI-OLLAMA-STREAM-RESPONSE] streamed %d tokens", count)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("[AI-OLLAMA-STREAM-ERROR] %s", exc)
            yield f"[provider-error] {exc}"

    async def respond_once(self, request: AIRequest) -> AIResponse:
        provider = request["provider_name"].lower()
        try:
            if provider == "ollama":
                return await self._respond_ollama(request)
            return await self._respond_openai_compat(request)
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError) as exc:
            return {
                "provider_mode": "local",
                "provider_name": request["provider_name"],
                "model_name": request["model_name"],
                "content": f"[provider-error] {exc}",
            }
