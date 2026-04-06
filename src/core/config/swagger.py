from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def get_swagger_settings() -> dict[str, Any]:
    return {
        "title": os.getenv("JARVIS_SWAGGER_TITLE", "jarvis-core API"),
        "version": os.getenv("JARVIS_SWAGGER_VERSION", "1.0.0"),
        "description": os.getenv(
            "JARVIS_SWAGGER_DESCRIPTION",
            "Jarvis Core API documentation.",
        ),
        "docs_url": os.getenv("JARVIS_SWAGGER_DOCS_URL", "/docs"),
        "redoc_url": os.getenv("JARVIS_SWAGGER_REDOC_URL", "/redoc"),
        "openapi_url": os.getenv("JARVIS_SWAGGER_OPENAPI_URL", "/openapi.json"),
        "swagger_ui_parameters": {
            "displayRequestDuration": True,
            "docExpansion": "none",
            "persistAuthorization": True,
        },
        "openapi_tags": [
            {"name": "auth", "description": "Authentication and identity endpoints"},
        ],
    }


def apply_swagger_security(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Use: Bearer <access_token>",
        }
        schema.setdefault("security", [{"BearerAuth": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[assignment]
