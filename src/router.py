DEEP_KEYWORDS = {
    "plan",
    "analyze",
    "analysis",
    "design",
    "architecture",
    "tradeoff",
    "debug",
    "root cause",
}


def choose_route(message: str, task_type: str = "general") -> str:
    lowered = message.lower()
    if task_type == "analysis":
        return "deep"
    if len(message) >= 220:
        return "deep"
    if any(keyword in lowered for keyword in DEEP_KEYWORDS):
        return "deep"
    return "fast"
