# jarvis-core Architecture

- API Layer (`app.py`): HTTP 엔드포인트와 스트리밍 응답 제공
- Router (`router.py`): 입력 길이/키워드/작업 타입 기반 `fast|deep` 결정
- Safety Gate (`safety.py`): 위험 액션 감지 및 confirm 정책 적용
- Memory (`db.py`, `db_connection.py`, `db_schema.py`, `db_operations.py`): PostgreSQL(user/chat/message/memory) 스키마 + SQLite fallback 저장
- Middleware (`middleware.py`): request_id 부여 및 로그 일관성 유지

외부 실행(How)은 `jarvis-controller`에 위임하고, 본 서비스는 판단(What/Why)만 담당한다.
