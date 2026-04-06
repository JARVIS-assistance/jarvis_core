from __future__ import annotations

from typing import Optional, Tuple

SENSITIVE_KEYWORDS = {"delete", "payment", "send"}


def detect_sensitive_action(message: str) -> list[str]:
    lowered = message.lower()
    return [keyword for keyword in SENSITIVE_KEYWORDS if keyword in lowered]


def safety_gate(message: str, confirmed: bool) -> Tuple[bool, Optional[str]]:
    matched = detect_sensitive_action(message)
    if matched and not confirmed:
        reason = f"Blocked sensitive action without confirm: {', '.join(sorted(matched))}"
        return False, reason
    return True, None
