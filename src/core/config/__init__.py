__all__ = [
    "AuthGuardMiddleware",
    "CoreResponse",
    "apply_swagger_security",
    "available_modes",
    "get_swagger_settings",
    "run_deep_thinking",
    "run_realtime_conversation",
]


def __getattr__(name: str):
    if name in {"CoreResponse", "available_modes", "run_deep_thinking", "run_realtime_conversation"}:
        from .engine import (
            CoreResponse,
            available_modes,
            run_deep_thinking,
            run_realtime_conversation,
        )

        return {
            "CoreResponse": CoreResponse,
            "available_modes": available_modes,
            "run_deep_thinking": run_deep_thinking,
            "run_realtime_conversation": run_realtime_conversation,
        }[name]

    if name == "AuthGuardMiddleware":
        from .gaurd import AuthGuardMiddleware

        return AuthGuardMiddleware

    if name in {"apply_swagger_security", "get_swagger_settings"}:
        from .swagger import apply_swagger_security, get_swagger_settings

        return {
            "apply_swagger_security": apply_swagger_security,
            "get_swagger_settings": get_swagger_settings,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
