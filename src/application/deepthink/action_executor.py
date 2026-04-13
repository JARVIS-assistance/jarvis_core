"""액션 실행 엔진.

참고 아키텍처(WebSocket 에이전트)의 패턴을 HTTP/SSE 환경에 맞게 구현한다.

┌────────────────────────────────────────────────┐
│                ActionExecutor                   │
│                                                 │
│  액션 분류                                       │
│  ┌─────────────────┐  ┌──────────────────────┐  │
│  │  server actions  │  │   client actions      │  │
│  │  (서버 직접 실행) │  │  (클라이언트에 위임)  │  │
│  │                  │  │                       │  │
│  │  - web_search    │  │  - terminal           │  │
│  │                  │  │  - app_control        │  │
│  │                  │  │  - file_write/read    │  │
│  │                  │  │  - mouse_click/drag   │  │
│  │                  │  │  - keyboard_type      │  │
│  │                  │  │  - hotkey             │  │
│  │                  │  │  - screenshot         │  │
│  │                  │  │  - open_url           │  │
│  │                  │  │  - clipboard          │  │
│  │                  │  │  - notify             │  │
│  └─────────────────┘  └──────────────────────┘  │
│                                                 │
│  서버 실행 결과 → accumulated_context에 주입     │
│  클라이언트 액션 → response.actions로 반환       │
└────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .schemas import ClientActionInternal
from .web_search import SearchResult, format_search_results, web_search

logger = logging.getLogger("jarvis_core.deepthink.action_executor")


# ── 서버 실행 가능 액션 타입 ─────────────────────────────────
# 이 set에 포함된 타입은 서버에서 직접 실행하고 클라이언트에 전달하지 않음
SERVER_EXECUTABLE_ACTIONS: set[str] = {"web_search"}


@dataclass(slots=True)
class ActionResult:
    """단일 서버 실행 결과."""

    action_type: str
    query: str
    success: bool
    data: str  # 포맷된 결과 텍스트
    raw: Any = None  # 원본 데이터 (SearchResult 리스트 등)


@dataclass(slots=True)
class ExecutionResult:
    """액션 실행 결과 묶음."""

    server_results: list[ActionResult] = field(default_factory=list)
    client_actions: list[ClientActionInternal] = field(default_factory=list)

    @property
    def has_server_results(self) -> bool:
        return len(self.server_results) > 0

    @property
    def has_client_actions(self) -> bool:
        return len(self.client_actions) > 0

    def get_server_context(self) -> str:
        """서버 실행 결과를 AI 컨텍스트용 텍스트로 반환한다."""
        parts: list[str] = []
        for r in self.server_results:
            status = "성공" if r.success else "실패"
            parts.append(
                f"[서버 실행: {r.action_type} ({status})] "
                f"쿼리: {r.query}\n{r.data}"
            )
        return "\n\n".join(parts)

    def get_search_results_text(self) -> str | None:
        """검색 결과 텍스트만 반환한다 (없으면 None)."""
        for r in self.server_results:
            if r.action_type == "web_search" and r.success:
                return r.data
        return None


class ActionExecutor:
    """액션을 분류하고 서버 실행 가능한 것을 직접 처리한다.

    참고 코드의 패턴:
    - web_search: 서버에서 ddgs로 직접 실행 (proxy 불필요)
    - proxy_tool: 클라이언트에 WebSocket으로 위임 → JARVIS에서는 response.actions로 반환

    HTTP/SSE 환경이므로 클라이언트 실행 결과는 별도 follow-up 요청으로 받는다.
    """

    async def execute(
        self,
        actions: list[ClientActionInternal],
    ) -> ExecutionResult:
        """액션 리스트를 분류·실행하고 결과를 반환한다."""
        result = ExecutionResult()

        for action in actions:
            if action.type in SERVER_EXECUTABLE_ACTIONS:
                server_result = await self._execute_server_action(action)
                result.server_results.append(server_result)
            else:
                result.client_actions.append(action)

        logger.info(
            "action execution done: server=%d client=%d",
            len(result.server_results),
            len(result.client_actions),
        )
        return result

    # ── 서버 실행 핸들러 ──────────────────────────────────────

    async def _execute_server_action(
        self, action: ClientActionInternal
    ) -> ActionResult:
        """서버에서 직접 실행 가능한 액션을 처리한다."""
        handler = self._SERVER_HANDLERS.get(action.type)
        if handler is None:
            return ActionResult(
                action_type=action.type,
                query=action.command or "",
                success=False,
                data=f"지원하지 않는 서버 액션: {action.type}",
            )
        return await handler(self, action)

    async def _handle_web_search(
        self, action: ClientActionInternal
    ) -> ActionResult:
        """web_search 액션을 서버에서 실행한다.

        참고 코드 패턴:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
        """
        query = action.command or ""
        if not query:
            return ActionResult(
                action_type="web_search",
                query=query,
                success=False,
                data="검색 쿼리가 비어있습니다.",
            )

        max_results = action.args.get("max_results", 5)
        search_results: list[SearchResult] = await web_search(
            query, max_results=max_results,
        )

        formatted = format_search_results(search_results)
        logger.info(
            "web_search executed query=%r found=%d",
            query,
            len(search_results),
        )

        return ActionResult(
            action_type="web_search",
            query=query,
            success=len(search_results) > 0,
            data=formatted,
            raw=search_results,
        )

    # 핸들러 레지스트리 — 새 서버 실행 액션 추가 시 여기에 등록
    _SERVER_HANDLERS = {
        "web_search": _handle_web_search,
    }
