from __future__ import annotations

from collections.abc import AsyncGenerator

from .client import AIClient, LocalLLMAIClient, TokenAIClient
from .schemas import AIRequest, AIResponse, AIStreamChunk


class AIService:
    def __init__(
        self,
        default_client: AIClient,
        token_client: AIClient | None = None,
        local_client: AIClient | None = None,
    ) -> None:
        self.default_client = default_client
        self.token_client = token_client or TokenAIClient()
        self.local_client = local_client or LocalLLMAIClient()

    def _choose_client(self, provider_mode: str) -> AIClient:
        if provider_mode == "token":
            return self.token_client
        if provider_mode == "local":
            return self.local_client
        return self.default_client

    async def stream_response(
        self, message: str, route: str, request_id: str
    ) -> AsyncGenerator[AIStreamChunk, None]:
        async for chunk in self.default_client.stream_chat(
            message=message, route=route, request_id=request_id
        ):
            yield chunk

    async def respond_once(self, request: AIRequest) -> AIResponse:
        client = self._choose_client(request["provider_mode"])
        return await client.respond_once(request)

    async def stream_tokens(self, request: AIRequest) -> AsyncGenerator[str, None]:
        client = self._choose_client(request["provider_mode"])
        async for token in client.stream_tokens(request):
            yield token

    async def realtime_session_start(self, request: AIRequest) -> str:
        client = self._choose_client(request["provider_mode"])
        return await client.realtime_session_start(request)

    async def realtime_session_send(
        self, request: AIRequest, realtime_session_id: str
    ) -> AsyncGenerator[str, None]:
        client = self._choose_client(request["provider_mode"])
        async for token in client.realtime_session_send(realtime_session_id, request):
            yield token

    async def realtime_session_close(
        self, request: AIRequest, realtime_session_id: str
    ) -> None:
        client = self._choose_client(request["provider_mode"])
        await client.realtime_session_close(realtime_session_id)

    async def cancel_generation(
        self, request: AIRequest, realtime_session_id: str
    ) -> None:
        client = self._choose_client(request["provider_mode"])
        await client.cancel_generation(realtime_session_id)
