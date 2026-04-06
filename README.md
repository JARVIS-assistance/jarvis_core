# jarvis_core

`jarvis_core`는 실제 AI provider 연동과 코어 추론, DB 작업을 담당하는 도메인 계층이다.

이 모듈은 JARVIS의 "생각하고 처리하는 중심"에 해당한다.  
사용자 인증/인가나 외부 진입 API 관리가 아니라, 실제 AI 호출과 데이터 저장, 코어 판단 로직을 맡는다.

## 역할

- AI provider 연동
- realtime/deep 등 코어 추론 수행
- 채팅/세션 관련 DB 작업
- 모델 설정 및 사용자별 AI 선택 관리
- 코어 도메인 로직 축적

## 책임 범위

`jarvis_core`는 아래 영역을 책임진다.

- 어떤 provider와 model을 사용할지 선택
- 요청을 AI 호출 형태로 변환
- 응답을 저장하거나 후속 처리 가능한 형태로 정리
- 대화, 메모리, 세션 등 데이터 계층 관리
- 향후 플래닝 지능이 고도화될 경우 핵심 알고리즘을 수용

즉, `jarvis_core`는 "무엇을 판단하고 어떤 결과를 만들 것인가"에 집중한다.

## 다른 모듈과의 관계

- `jarvis_controller`는 사용자 요청 흐름을 조정하고, 실제 AI/DB 작업은 `jarvis_core`에 위임한다.
- `jarvis_gateway`는 인증/인가를 끝낸 뒤, 신뢰 가능한 사용자 컨텍스트를 상위 계층에 넘긴다.
- `jarvis_contracts`는 core 결과를 외부 응답으로 맞출 때 공통 계약 기준이 된다.
- `jarvis_contracts.endpoints`는 controller가 호출할 core endpoint 경로를 공통으로 관리한다.

## 현재 코드 기준 구성

- `src/jarvis_core/`
  - controller가 직접 호출하는 코어 엔진 인터페이스
- `src/ai/`
  - provider client와 AI 서비스 계층
- `src/application/chat/`
  - 채팅 요청 처리, 저장, 스트리밍 관련 애플리케이션 서비스
- `src/application/auth/`
  - 인증 연계용 애플리케이션 계층 일부
- `src/core/db/`
  - DB 연결, 스키마, DB 연산 기반 계층
- `src/app.py`
  - 현재 외부 노출 중인 core HTTP 진입점 (`/health`, `/internal/conversation/respond`)
- `src/jarvis_core.py`
  - controller와 app이 재사용하는 core 엔진 공개 import 진입점
- `jarvis_contracts/endpoints.py`
  - controller/core가 함께 참조하는 endpoint 레지스트리

추가 설명은 아래 문서를 참고한다.

- `docs/architecture.md`
- `docs/runbook.md`

## 설계 원칙

- provider 연동 로직은 core에 모은다.
- DB 접근은 controller가 아니라 core 내부에서 관리한다.
- controller는 orchestration, core는 intelligence와 persistence를 담당한다.
- 외부 공개 API보다 내부 도메인 안정성을 우선한다.
- controller가 사용하는 core endpoint path는 문자열 하드코딩 대신 계약 레이어에서 관리한다.

## Install

```bash
python3.12 -m pip install -r requirements.txt
python3.12 -m pip install -r requirements-dev.txt
```

## Run

```bash
python3.12 -m uvicorn app:app --app-dir src --reload --port 8000
```

라이브러리로 직접 쓰는 예시:

```bash
PYTHONPATH=src python3.12 -c "from jarvis_core import run_realtime_conversation; print(run_realtime_conversation('hello').content)"
```

## Test

```bash
python3.12 -m pytest
```

## Lint

```bash
ruff check .
```

## 할 일

- AI provider adapter 계층을 정리해 provider 추가 비용 줄이기
- 현재 분산된 core 엔진과 application/chat 로직의 경계 재정리
- DB 스키마와 메모리 전략을 문서화하고 마이그레이션 기준 마련
- planning intelligence가 core에 자연스럽게 들어올 수 있도록 인터페이스 정리
- controller가 의존하는 공개 진입점 API를 명확히 고정
