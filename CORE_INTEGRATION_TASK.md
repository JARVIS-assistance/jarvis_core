# jarvis_core 작업 요청

## 목적

`jarvis_controller`가 `jarvis_core`를 직접 import 하지 않고, HTTP endpoint로 호출하도록 연결 구조를 바꾸고 있습니다.

`jarvis_core` 쪽에서 내부 연동용 conversation endpoint를 추가해주세요.

## 수정 대상

- `/Users/chawonje/Desktop/Workspace/project/JARVIS/core/jarvis_core/src/app.py`
- `/Users/chawonje/Desktop/Workspace/project/JARVIS/core/jarvis_core/tests/test_app.py`

## 해야 할 일

### 1. 내부 endpoint 추가

`src/app.py`에 아래 endpoint를 추가해주세요.

- `POST /internal/conversation/respond`

### 요청 바디

```json
{
  "mode": "realtime" | "deep",
  "message": "string"
}
```

조건:
- `mode`는 `realtime` 또는 `deep`만 허용
- `message`는 빈 문자열이면 안 됨

### 응답 바디

```json
{
  "mode": "realtime" | "deep",
  "summary": "string",
  "content": "string",
  "next_actions": ["string"]
}
```

## 구현 규칙

- 기존 함수 재사용
  - `run_realtime_conversation`
  - `run_deep_thinking`
- `/health` endpoint는 그대로 유지
- 이번 작업은 얇은 내부 adapter 추가가 목적이므로, 불필요한 리팩터링은 하지 말 것

## 동작 방식

- `mode == "deep"` 이면 `run_deep_thinking(body.message)` 호출
- `mode == "realtime"` 이면 `run_realtime_conversation(body.message)` 호출
- 결과를 HTTP 응답 모델로 그대로 매핑

## 구현 예시

```python
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from jarvis_core import available_modes, run_deep_thinking, run_realtime_conversation


class InternalConversationRequest(BaseModel):
    mode: Literal["realtime", "deep"]
    message: str = Field(min_length=1)


class InternalConversationResponse(BaseModel):
    mode: str
    summary: str
    content: str
    next_actions: list[str] = Field(default_factory=list)


def create_app() -> FastAPI:
    app = FastAPI(title="jarvis-core", version="0.2.0")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "jarvis-core",
            "mode": "library-first",
            "capabilities": list(available_modes()),
        }

    @app.post("/internal/conversation/respond", response_model=InternalConversationResponse)
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

    return app
```

## 테스트 추가

`tests/test_app.py`에 아래 2개 테스트를 추가해주세요.

### realtime 테스트

```python
def test_internal_conversation_realtime_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/internal/conversation/respond",
        json={"mode": "realtime", "message": "배포 상태 알려줘"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "realtime"
    assert "실시간 응답" in payload["content"]
```

### deep 테스트

```python
def test_internal_conversation_deep_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/internal/conversation/respond",
        json={"mode": "deep", "message": "Traceback: bad state"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "deep"
    assert "Deep thinking result" in payload["content"]
```

## 완료 조건

- `POST /internal/conversation/respond` 추가 완료
- `realtime`, `deep` 모두 정상 동작
- `/health` 기존 동작 유지
- 관련 테스트 추가 완료
