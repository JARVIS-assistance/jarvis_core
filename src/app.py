from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from jarvis_contracts import (
    ClientAction,
    DeepThinkPlanRequest,
    DeepThinkPlanResponse,
    DeepThinkRequest,
    DeepThinkResponse,
    DeepThinkStepPayload,
    DeepThinkStepResult,
    InternalConversationRequest,
    InternalConversationResponse,
    JarvisCoreEndpoints,
)

from ai import AIService
from ai.client import StubAIClient
from application.deepthink import DeepThinkService
from application.deepthink.schemas import (
    DeepThinkInternalRequest,
    DeepThinkPlanInternalRequest,
    DeepThinkStepInput,
)
from application.chat.schemas import (
    ChatOnceRequest,
    ChatOnceResponse,
    MemoryCreateRequest,
    MemoryResponse,
    ModelConfigResponse,
    ModelConfigUpsertRequest,
    ModelSelectionResponse,
    ModelSelectionUpsertRequest,
    PersonaResponse,
    PersonaSelectionRequest,
    PersonaUpsertRequest,
)
from application.chat.service import ChatService
from core.db.db_connection import DBClient, connect
from core.db.db_schema import init_db
from jarvis_core import available_modes, run_deep_thinking, run_realtime_conversation
from middleware import RequestIDMiddleware


def _get_chat_service(app: FastAPI) -> ChatService:
    return ChatService(db=app.state.db, ai_service=app.state.ai_service)


def _get_deepthink_service(app: FastAPI) -> DeepThinkService:
    return DeepThinkService(db=app.state.db, ai_service=app.state.ai_service)


def create_app(db: DBClient | None = None, ai_service: AIService | None = None) -> FastAPI:
    app = FastAPI(title="jarvis-core", version="0.3.0")
    app.add_middleware(RequestIDMiddleware)

    @app.on_event("startup")
    def startup() -> None:
        if not hasattr(app.state, "db") or app.state.db is None:
            app.state.db = db or connect()
            init_db(app.state.db)
        if not hasattr(app.state, "ai_service") or app.state.ai_service is None:
            app.state.ai_service = ai_service or AIService(default_client=StubAIClient())

    @app.on_event("shutdown")
    def shutdown() -> None:
        db_client: DBClient | None = getattr(app.state, "db", None)
        if db_client is not None:
            db_client.conn.close()

    # ── health ──────────────────────────────────────────────

    @app.get(JarvisCoreEndpoints.HEALTH.path)
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "jarvis-core",
            "mode": "library-first",
            "capabilities": list(available_modes()),
        }

    # ── internal: conversation (기존) ───────────────────────

    @app.post(
        JarvisCoreEndpoints.INTERNAL_CONVERSATION_RESPOND.path,
        response_model=InternalConversationResponse,
    )
    def respond(body: InternalConversationRequest) -> InternalConversationResponse:
        result = (
            run_deep_thinking(body.message)
            if body.mode == "deep"
            else run_realtime_conversation(body.message)
        )
        return InternalConversationResponse(
            mode=result.mode,
            summary=result.summary,
            content=result.content,
            next_actions=result.next_actions,
        )

    # ── internal: chat ──────────────────────────────────────

    @app.post("/internal/chat/request", response_model=ChatOnceResponse)
    async def chat_request(
        body: ChatOnceRequest,
        x_user_id: str = Header(...),
        x_user_email: str = Header(default=""),
        x_request_id: str = Header(default=""),
    ) -> ChatOnceResponse:
        service = _get_chat_service(app)
        result = await service.request_once(
            body=body,
            request_id=x_request_id,
            user_id=x_user_id,
            email=x_user_email,
        )
        from jarvis_contracts import ErrorResponse

        if isinstance(result, ErrorResponse):
            return ChatOnceResponse(
                request_id=result.request_id or x_request_id,
                route="blocked",
                provider_mode="local",
                provider_name="safety",
                model_name="none",
                content=result.message or "blocked",
            )
        return ChatOnceResponse(**result)

    @app.post("/internal/chat/stream")
    async def chat_stream(
        body: ChatOnceRequest,
        x_user_id: str = Header(...),
        x_user_email: str = Header(default=""),
        x_request_id: str = Header(default=""),
    ) -> StreamingResponse:
        service = _get_chat_service(app)
        return StreamingResponse(
            service.run_realtime_sse(
                message=body.message,
                task_type=body.task_type,
                confirm=body.confirm,
                route_override=body.route_override,
                request_id=x_request_id,
                user_id=x_user_id,
                email=x_user_email,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── internal: model config ──────────────────────────────

    @app.post("/internal/chat/model-config", response_model=ModelConfigResponse)
    def create_model_config(
        body: ModelConfigUpsertRequest,
        x_user_id: str = Header(...),
    ) -> ModelConfigResponse:
        service = _get_chat_service(app)
        result = service.create_model_config(user_id=x_user_id, body=body)
        return ModelConfigResponse(**result)

    @app.get("/internal/chat/model-config", response_model=list[ModelConfigResponse])
    def list_model_configs(
        x_user_id: str = Header(...),
    ) -> list[ModelConfigResponse]:
        service = _get_chat_service(app)
        result = service.list_model_configs(user_id=x_user_id)
        return [ModelConfigResponse(**item) for item in result]

    @app.put("/internal/chat/model-config/{model_config_id}", response_model=ModelConfigResponse)
    def update_model_config(
        model_config_id: str,
        body: ModelConfigUpsertRequest,
        x_user_id: str = Header(...),
    ) -> ModelConfigResponse:
        service = _get_chat_service(app)
        result = service.update_model_config(
            user_id=x_user_id,
            model_config_id=model_config_id,
            body=body,
        )
        return ModelConfigResponse(**result)

    @app.post("/internal/chat/model-selection", response_model=ModelSelectionResponse)
    def set_model_selection(
        body: ModelSelectionUpsertRequest,
        x_user_id: str = Header(...),
    ) -> ModelSelectionResponse:
        service = _get_chat_service(app)
        result = service.set_model_selection(user_id=x_user_id, body=body)
        return ModelSelectionResponse(**result)

    @app.get("/internal/chat/model-selection", response_model=ModelSelectionResponse)
    def get_model_selection(
        x_user_id: str = Header(...),
    ) -> ModelSelectionResponse:
        service = _get_chat_service(app)
        result = service.get_model_selection(user_id=x_user_id)
        return ModelSelectionResponse(**result)

    @app.post("/internal/chat/persona", response_model=PersonaResponse)
    def create_persona(
        body: PersonaUpsertRequest,
        x_user_id: str = Header(...),
    ) -> PersonaResponse:
        service = _get_chat_service(app)
        result = service.create_persona(user_id=x_user_id, body=body)
        return PersonaResponse(**result)

    @app.get("/internal/chat/persona", response_model=list[PersonaResponse])
    def list_personas(
        x_user_id: str = Header(...),
    ) -> list[PersonaResponse]:
        service = _get_chat_service(app)
        result = service.list_personas(user_id=x_user_id)
        return [PersonaResponse(**item) for item in result]

    @app.put("/internal/chat/persona/{user_persona_id}", response_model=PersonaResponse)
    def update_persona(
        user_persona_id: str,
        body: PersonaUpsertRequest,
        x_user_id: str = Header(...),
    ) -> PersonaResponse:
        service = _get_chat_service(app)
        result = service.update_persona(
            user_id=x_user_id,
            user_persona_id=user_persona_id,
            body=body,
        )
        return PersonaResponse(**result)

    @app.post("/internal/chat/persona/select", response_model=PersonaResponse)
    def select_persona(
        body: PersonaSelectionRequest,
        x_user_id: str = Header(...),
    ) -> PersonaResponse:
        service = _get_chat_service(app)
        result = service.select_persona(user_id=x_user_id, body=body)
        return PersonaResponse(**result)

    @app.post("/internal/chat/memory", response_model=MemoryResponse)
    def create_memory(
        body: MemoryCreateRequest,
        x_user_id: str = Header(...),
    ) -> MemoryResponse:
        service = _get_chat_service(app)
        result = service.create_memory(user_id=x_user_id, body=body)
        return MemoryResponse(**result)

    @app.get("/internal/chat/memory", response_model=list[MemoryResponse])
    def list_memory(
        x_user_id: str = Header(...),
        chat_id: str | None = None,
    ) -> list[MemoryResponse]:
        service = _get_chat_service(app)
        result = service.list_memory(user_id=x_user_id, chat_id=chat_id)
        return [MemoryResponse(**item) for item in result]

    # ── internal: deepthink ────────────────────────────────

    @app.post(
        JarvisCoreEndpoints.INTERNAL_DEEPTHINK_PLAN.path,
        response_model=DeepThinkPlanResponse,
    )
    async def deepthink_plan(
        body: DeepThinkPlanRequest,
        x_user_id: str = Header(...),
        x_request_id: str = Header(default=""),
    ) -> DeepThinkPlanResponse:
        service = _get_deepthink_service(app)
        internal_req = DeepThinkPlanInternalRequest(
            request_id=body.request_id,
            message=body.message,
        )
        result = await service.plan(internal_req, user_id=x_user_id)
        return DeepThinkPlanResponse(
            request_id=result.request_id,
            goal=result.goal,
            steps=[
                DeepThinkStepPayload(
                    id=s.id,
                    title=s.title,
                    description=s.description,
                )
                for s in result.steps
            ],
            constraints=result.constraints,
        )

    @app.post(
        JarvisCoreEndpoints.INTERNAL_DEEPTHINK_EXECUTE.path,
        response_model=DeepThinkResponse,
    )
    async def deepthink_execute(
        body: DeepThinkRequest,
        x_user_id: str = Header(...),
        x_request_id: str = Header(default=""),
    ) -> DeepThinkResponse:
        service = _get_deepthink_service(app)
        internal_req = DeepThinkInternalRequest(
            request_id=body.request_id,
            message=body.message,
            plan_steps=[
                DeepThinkStepInput(
                    id=step.id,
                    title=step.title,
                    description=step.description,
                )
                for step in body.plan_steps
            ],
        )
        result = await service.execute(internal_req, user_id=x_user_id)

        def _to_client_action(a) -> ClientAction:
            return ClientAction(
                type=a.type,
                command=a.command,
                target=a.target,
                payload=a.payload,
                args=a.args,
                description=a.description,
                requires_confirm=a.requires_confirm,
                step_id=a.step_id,
            )

        return DeepThinkResponse(
            request_id=result.request_id,
            steps=[
                DeepThinkStepResult(
                    step_id=s.step_id,
                    title=s.title,
                    status=s.status,
                    content=s.content,
                    actions=[_to_client_action(a) for a in s.actions],
                )
                for s in result.steps
            ],
            summary=result.summary,
            content=result.content,
            actions=[_to_client_action(a) for a in result.actions],
        )

    return app


app = create_app()
