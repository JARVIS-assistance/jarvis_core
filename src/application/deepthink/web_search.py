"""서버 사이드 웹 검색 유틸리티.

ddgs(DuckDuckGo Search) 라이브러리를 사용하여 검색 결과를 가져온다.
외부 API 키 없이 동작한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger("jarvis_core.deepthink.web_search")

_DEFAULT_MAX_RESULTS = 5


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


async def web_search(
    query: str,
    *,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> list[SearchResult]:
    """DuckDuckGo 검색을 수행하여 결과 목록을 반환한다."""
    loop = asyncio.get_running_loop()
    try:
        raw_results = await loop.run_in_executor(
            None, _sync_search, query, max_results,
        )
    except Exception as exc:
        logger.error("web search failed query=%r error=%s", query, exc)
        return []

    results = [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("href", r.get("link", "")),
            snippet=r.get("body", r.get("snippet", "")),
        )
        for r in raw_results
        if r.get("title")
    ]

    logger.info("web_search query=%r results=%d", query, len(results))
    return results


def _sync_search(query: str, max_results: int) -> list[dict]:
    """동기 함수 — executor에서 실행된다."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


def format_search_results(results: list[SearchResult]) -> str:
    """검색 결과를 텍스트로 포맷한다."""
    if not results:
        return "검색 결과가 없습니다."

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. 제목: {r.title}")
        if r.snippet:
            lines.append(f"   내용: {r.snippet}")
        lines.append(f"   URL: {r.url}")
    return "\n".join(lines)
