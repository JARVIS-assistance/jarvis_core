import logging
from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient
from jarvis_contracts import JarvisCoreEndpoints

from ai import AIService
from app import create_app
from core.config.prompt_loader import load_prompt
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
        self.requests.append(request)
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


def test_default_prompt_loader_reads_workbench_prompt() -> None:
    prompt = load_prompt("base_system")

    assert prompt is not None
    assert "진행하겠습니다!" in prompt


def test_realtime_request_uses_workbench_base_prompt() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            response = client.post(
                "/internal/chat/request",
                json={"message": "브라우저 열어줘", "route_override": "realtime"},
                headers={
                    "x-user-id": "u-prompt",
                    "x-user-email": "u-prompt@example.com",
                    "x-request-id": "r-prompt",
                },
            )

    assert response.status_code == 200
    system_prompt = str(ai_client.requests[-1]["system_prompt"])
    assert "진행하겠습니다!" in system_prompt
    assert "Do not explain that you cannot operate the screen" in system_prompt


def test_realtime_stream_marks_latest_user_message_as_current_turn() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            for index, message in enumerate(
                (
                    "점심 메뉴 추천해줘",
                    "sublimetext켜서 안녕하세요 작성해볼래?",
                )
            ):
                with client.stream(
                    "POST",
                    "/internal/chat/stream",
                    json={"message": message, "route_override": "realtime"},
                    headers={
                        "x-user-id": "u-latest-turn",
                        "x-user-email": "u-latest-turn@example.com",
                        "x-request-id": f"r-latest-{index}",
                    },
                ) as response:
                    body = "".join(response.iter_text())
                assert response.status_code == 200
                assert "assistant_delta" in body

    messages = ai_client.requests[-1]["messages"]
    latest = messages[-1]
    assert latest["role"] == "user"
    assert latest["content"].startswith("Latest user message.")
    assert "sublimetext켜서 안녕하세요 작성해볼래?" in latest["content"]
    assert "점심 메뉴 추천" not in latest["content"]
    assert "Current-turn priority" in str(ai_client.requests[-1]["system_prompt"])


def test_realtime_stream_prefers_selected_realtime_model_over_default(caplog) -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        caplog.set_level(logging.INFO, logger="jarvis_core.chat")
        with TestClient(app) as client:
            default_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "default-model",
                    "is_default": True,
                    "supports_stream": True,
                    "supports_realtime": True,
                },
                headers={"x-user-id": "u-model"},
            )
            assert default_response.status_code == 200

            realtime_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "selected-realtime-model",
                    "is_default": False,
                    "supports_stream": True,
                    "supports_realtime": True,
                },
                headers={"x-user-id": "u-model"},
            )
            assert realtime_response.status_code == 200
            realtime_id = realtime_response.json()["id"]

            selection_response = client.post(
                "/internal/chat/model-selection",
                json={"realtime_model_config_id": realtime_id},
                headers={"x-user-id": "u-model"},
            )
            assert selection_response.status_code == 200

            with client.stream(
                "POST",
                "/internal/chat/stream",
                json={"message": "바로 답해줘", "route_override": "realtime"},
                headers={
                    "x-user-id": "u-model",
                    "x-user-email": "u-model@example.com",
                    "x-request-id": "r-model",
                },
            ) as response:
                body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "selected-realtime-model" in body
    assert ai_client.requests[-1]["model_name"] == "selected-realtime-model"
    assert "model request request_id=r-model" in caplog.text
    assert "model response request_id=r-model" in caplog.text
    assert "model=selected-realtime-model" in caplog.text


def test_default_model_update_preserves_realtime_selection() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            default_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "default-non-realtime",
                    "is_default": True,
                    "supports_stream": False,
                    "supports_realtime": False,
                },
                headers={"x-user-id": "u-preserve-selection"},
            )
            assert default_response.status_code == 200
            default_id = default_response.json()["id"]

            realtime_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "selected-realtime",
                    "is_default": False,
                    "supports_stream": True,
                    "supports_realtime": True,
                },
                headers={"x-user-id": "u-preserve-selection"},
            )
            assert realtime_response.status_code == 200
            realtime_id = realtime_response.json()["id"]

            selection_response = client.post(
                "/internal/chat/model-selection",
                json={"realtime_model_config_id": realtime_id},
                headers={"x-user-id": "u-preserve-selection"},
            )
            assert selection_response.status_code == 200

            updated_default = client.put(
                f"/internal/chat/model-config/{default_id}",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "default-non-realtime",
                    "is_default": True,
                    "supports_stream": False,
                    "supports_realtime": False,
                },
                headers={"x-user-id": "u-preserve-selection"},
            )
            assert updated_default.status_code == 200

            current_selection = client.get(
                "/internal/chat/model-selection",
                headers={"x-user-id": "u-preserve-selection"},
            )

    assert current_selection.status_code == 200
    assert current_selection.json()["realtime_model_config_id"] == realtime_id
    assert current_selection.json()["deep_model_config_id"] == default_id


def test_realtime_selection_rejects_non_realtime_model() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            model_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "default-non-realtime",
                    "is_default": True,
                    "supports_stream": False,
                    "supports_realtime": False,
                },
                headers={"x-user-id": "u-reject-selection"},
            )
            assert model_response.status_code == 200

            selection_response = client.post(
                "/internal/chat/model-selection",
                json={"realtime_model_config_id": model_response.json()["id"]},
                headers={"x-user-id": "u-reject-selection"},
            )

    assert selection_response.status_code == 400
    assert selection_response.json()["detail"] == "invalid realtime_model_config_id"


def test_delete_model_config_removes_user_model() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            created = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "delete-me",
                    "is_default": False,
                    "supports_stream": True,
                    "supports_realtime": False,
                },
                headers={"x-user-id": "u-delete-model"},
            )
            assert created.status_code == 200
            model_id = created.json()["id"]

            deleted = client.delete(
                f"/internal/chat/model-config/{model_id}",
                headers={"x-user-id": "u-delete-model"},
            )
            listed = client.get(
                "/internal/chat/model-config",
                headers={"x-user-id": "u-delete-model"},
            )

    assert deleted.status_code == 200
    assert deleted.json() == {"id": model_id, "deleted": True}
    assert listed.status_code == 200
    assert listed.json() == []


def test_realtime_stream_prefers_realtime_capable_model_without_selection() -> None:
    ai_client = RecordingAIClient()
    ai_service = AIService(
        default_client=ai_client,
        local_client=ai_client,
        token_client=ai_client,
    )

    with NamedTemporaryFile(suffix=".db") as db_file:
        app = create_app(db=connect(db_file.name), ai_service=ai_service)
        with TestClient(app) as client:
            default_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "default-non-realtime-model",
                    "is_default": True,
                    "supports_stream": True,
                    "supports_realtime": False,
                },
                headers={"x-user-id": "u-realtime-auto"},
            )
            assert default_response.status_code == 200

            realtime_response = client.post(
                "/internal/chat/model-config",
                json={
                    "provider_mode": "local",
                    "provider_name": "ollama",
                    "model_name": "realtime-enabled-model",
                    "is_default": False,
                    "supports_stream": True,
                    "supports_realtime": True,
                },
                headers={"x-user-id": "u-realtime-auto"},
            )
            assert realtime_response.status_code == 200

            with client.stream(
                "POST",
                "/internal/chat/stream",
                json={"message": "바로 답해줘", "route_override": "realtime"},
                headers={
                    "x-user-id": "u-realtime-auto",
                    "x-user-email": "u-realtime-auto@example.com",
                    "x-request-id": "r-realtime-auto",
                },
            ) as response:
                body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "realtime-enabled-model" in body
    assert ai_client.requests[-1]["model_name"] == "realtime-enabled-model"


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
