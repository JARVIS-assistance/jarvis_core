import asyncio
import json

from ai.client import LocalLLMAIClient


class _FakeContent:
    def __init__(self, lines: list[dict[str, object]]) -> None:
        self._lines = [json.dumps(line).encode("utf-8") + b"\n" for line in lines]

    def __aiter__(self):
        self._iter = iter(self._lines)
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeResponse:
    status = 200

    def __init__(self) -> None:
        self.content = _FakeContent(
            [
                {"response": "first ", "done": False},
                {"response": "second", "done": False},
                {"done": True},
            ]
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return ""


class _FakeSession:
    requests: list[dict[str, object]] = []

    def __init__(self, *, timeout) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, endpoint, *, json, headers):
        self.requests.append({"endpoint": endpoint, "json": json, "headers": headers})
        return _FakeResponse()


class _NoRespondOnceLocalClient(LocalLLMAIClient):
    async def respond_once(self, request):  # pragma: no cover - should never be called
        raise AssertionError("ollama streaming must not fall back to respond_once")


def test_ollama_stream_tokens_uses_native_streaming(monkeypatch) -> None:
    _FakeSession.requests.clear()
    monkeypatch.setattr("ai.client.aiohttp.ClientSession", _FakeSession)

    request = {
        "message": "hello",
        "route": "realtime",
        "request_id": "r-ollama",
        "provider_mode": "local",
        "provider_name": "ollama",
        "model_name": "llama3.2",
        "api_key": None,
        "endpoint": "http://ollama:11434",
        "system_prompt": "Be fast.",
        "messages": [],
    }

    async def collect() -> list[str]:
        return [token async for token in _NoRespondOnceLocalClient().stream_tokens(request)]

    assert asyncio.run(collect()) == ["first ", "second"]
    assert _FakeSession.requests == [
        {
            "endpoint": "http://ollama:11434/api/generate",
            "json": {
                "model": "llama3.2",
                "prompt": "System:\nBe fast.\n\nUser:\nhello",
                "stream": True,
            },
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/x-ndjson",
                "User-Agent": "JARVIS/1.0",
            },
        }
    ]
