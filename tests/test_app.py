from fastapi.testclient import TestClient
from jarvis_contracts import JarvisCoreEndpoints

from app import create_app


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
