from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from jarvis_contracts import ErrorResponse
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from ...gateway_client import GatewayAuthClient
except ImportError:  # pragma: no cover - direct script execution fallback
    from gateway_client import GatewayAuthClient


OPEN_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

gateway_auth_client = GatewayAuthClient()


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS" or request.url.path.startswith(OPEN_PATH_PREFIXES):
            return await call_next(request)

        authorization = request.headers.get("authorization")
        if not authorization:
            return self._reject(request, "missing authorization header")

        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return self._reject(request, "invalid authorization header")

        try:
            principal = gateway_auth_client.validate_token(
                parts[1],
                client_id=request.headers.get("x-client-id"),
                request_id=request.headers.get("x-request-id"),
            )
            request.state.auth_payload = {
                "sub": principal.user_id,
                "tenant_id": principal.tenant_id,
                "role": principal.role,
            }
        except Exception as exc:
            detail = getattr(exc, "detail", "invalid or expired token")
            return self._reject(request, str(detail))

        return await call_next(request)

    @staticmethod
    def _reject(request: Request, message: str) -> JSONResponse:
        err = ErrorResponse(
            error_code="AUTH_REQUIRED",
            message=message,
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(status_code=401, content=err.model_dump())
