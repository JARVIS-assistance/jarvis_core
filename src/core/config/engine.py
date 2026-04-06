from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CoreResponse:
    mode: str
    summary: str
    content: str
    next_actions: list[str] = field(default_factory=list)


def available_modes() -> tuple[str, str]:
    return ("realtime", "deep")


def run_realtime_conversation(message: str) -> CoreResponse:
    normalized = message.strip()
    return CoreResponse(
        mode="realtime",
        summary="빠른 응답 경로에서 요청을 처리했습니다.",
        content=f"실시간 응답: {normalized}",
        next_actions=["세부 로그 확인", "필요하면 deep 분석으로 전환"],
    )


def run_deep_thinking(message: str) -> CoreResponse:
    normalized = " ".join(line.strip() for line in message.splitlines() if line.strip())
    signals: list[str] = []
    lowered = normalized.lower()
    if "traceback" in lowered or "error" in lowered or "bad state" in lowered:
        signals.append("error-log")
    if "분석" in normalized or "analysis" in lowered or "원인" in normalized:
        signals.append("analysis-request")
    signal_summary = ", ".join(signals) if signals else "general-review"
    return CoreResponse(
        mode="deep",
        summary="심층 분석 경로에서 요청을 처리했습니다.",
        content=f"Deep thinking result: {normalized} [{signal_summary}]",
        next_actions=["가설 검증", "재현 절차 수집"],
    )
