from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient
from ai import AIService
from jarvis_contracts import JarvisCoreEndpoints

from app import create_app
from core.db.db_connection import connect


class RecordingAIClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.force_provider_error = False

    async def respond_once(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        if self.force_provider_error:
            content = "[provider-error] HTTP Error 500: Internal Server Error"
        else:
            content = (
                '{"goal":"메모리 확인","constraints":[],"steps":['
                '{"id":"s1","title":"확인","description":"메모리를 반영한다"}]}'
                if "planning engine" in str(request.get("system_prompt", ""))
                else "메모리를 반영한 응답"
            )
        return {
            "provider_mode": request["provider_mode"],
            "provider_name": request["provider_name"],
            "model_name": request["model_name"],
            "content": content,
        }

    async def stream_chat(self, message: str, route: str, request_id: str):
        yield {"type": "done", "content": ""}

    async def stream_tokens(self, request: dict[str, object]):
        yield "ok"

    async def realtime_session_start(self, request: dict[str, object]) -> str:
        return "rt-test"

    async def realtime_session_send(
        self,
        realtime_session_id: str,
        request: dict[str, object],
    ):
        yield "ok"

    async def realtime_session_close(self, realtime_session_id: str) -> None:
        return None

    async def cancel_generation(self, realtime_session_id: str) -> None:
        return None


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get(JarvisCoreEndpoints.HEALTH.path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["mode"] == "library-first"
    assert payload["capabilities"] == ["realtime", "deep"]


def test_internal_conversation_realtime_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        JarvisCoreEndpoints.INTERNAL_CONVERSATION_RESPOND.path,
        json={"mode": "realtime", "message": "배포 상태 알려줘"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "realtime"
    assert "실시간 응답" in payload["content"]


def test_internal_conversation_deep_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        JarvisCoreEndpoints.INTERNAL_CONVERSATION_RESPOND.path,
        json={"mode": "deep", "message": "Traceback: bad state"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "deep"
    assert "Deep thinking result" in payload["content"]


def test_internal_chat_request_accepts_deep_override() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/internal/chat/request",
        json={
            "message": "깊게 분석해줘",
            "route_override": "deep",
        },
        headers={"x-user-id": "u1", "x-user-email": "u1@example.com", "x-request-id": "r1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "deep"


def test_internal_persona_and_memory_endpoints() -> None:
    client = TestClient(create_app())

    persona_response = client.post(
        "/internal/chat/persona",
        json={
            "name": "Architect",
            "description": "Focus on design",
            "prompt_template": "You are Jarvis acting as a careful architect.",
            "tone": "analytical",
            "alias": "architect",
        },
        headers={"x-user-id": "u1"},
    )
    assert persona_response.status_code == 200
    persona = persona_response.json()
    assert persona["name"] == "Architect"

    memory_response = client.post(
        "/internal/chat/memory",
        json={
            "type": "preference",
            "content": "Prefer concise Korean answers.",
            "importance": 5,
        },
        headers={"x-user-id": "u1"},
    )
    assert memory_response.status_code == 200
    memory = memory_response.json()
    assert memory["type"] == "preference"

    list_response = client.get("/internal/chat/persona", headers={"x-user-id": "u1"})
    assert list_response.status_code == 200
    assert len(list_response.json()) >= 1

    memory_list_response = client.get("/internal/chat/memory", headers={"x-user-id": "u1"})
    assert memory_list_response.status_code == 200
    assert len(memory_list_response.json()) >= 1


def test_deepthink_uses_memory_and_saves_user_message() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            memory_response = client.post(
                "/internal/chat/memory",
                json={
                    "type": "preference",
                    "content": "항상 한국어로 짧게 답하기",
                    "importance": 5,
                },
                headers={"x-user-id": "u-memory"},
            )
            assert memory_response.status_code == 200

            plan_response = client.post(
                JarvisCoreEndpoints.INTERNAL_DEEPTHINK_PLAN.path,
                json={"request_id": "r-memory", "message": "내 선호 기억하고 있어?"},
                headers={"x-user-id": "u-memory"},
            )
            assert plan_response.status_code == 200

            assert ai_client.requests
            system_prompt = str(ai_client.requests[0]["system_prompt"])
            assert "Relevant memory" in system_prompt
            assert "항상 한국어로 짧게 답하기" in system_prompt

            db = client.app.state.db
            cursor = db.conn.execute(
                "SELECT role, content FROM messages WHERE role = ? AND content = ?",
                ("user", "내 선호 기억하고 있어?"),
            )
            assert cursor.fetchone() is not None


def test_deepthink_scroll_fallback_creates_browser_action() -> None:
    ai_client = RecordingAIClient()
    ai_client.force_provider_error = True
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            response = client.post(
                JarvisCoreEndpoints.INTERNAL_DEEPTHINK_EXECUTE.path,
                json={
                    "request_id": "r-scroll",
                    "message": "스크롤 내려줘",
                    "plan_steps": [
                        {
                            "id": "s1",
                            "title": "Initiate Scroll Down",
                            "description": "Execute scroll down in browser",
                        }
                    ],
                },
                headers={"x-user-id": "u-scroll"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"][0]["type"] == "browser_control"
    assert payload["actions"][0]["command"] == "scroll"
    assert payload["actions"][0]["target"] == "active_tab"
    assert payload["actions"][0]["args"]["direction"] == "down"
