from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatOnceRequest(BaseModel):
    message: str = Field(min_length=1)
    task_type: Literal["general", "analysis", "execution"] = "general"
    confirm: bool = False
    route_override: Literal["realtime", "deep"] | None = None


class ChatOnceResponse(BaseModel):
    request_id: str
    route: str
    provider_mode: Literal["token", "local"]
    provider_name: str
    model_name: str
    content: str


class ModelConfigUpsertRequest(BaseModel):
    provider_mode: Literal["token", "local"]
    provider_name: str = Field(min_length=1, max_length=60)
    model_name: str = Field(min_length=1, max_length=120)
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    is_default: bool = False
    supports_stream: bool = True
    supports_realtime: bool = False
    transport: Literal["http_sse", "websocket"] = "http_sse"
    input_modalities: str = "text"
    output_modalities: str = "text"


class ModelConfigResponse(BaseModel):
    id: str
    provider_mode: Literal["token", "local"]
    provider_name: str
    model_name: str
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    supports_stream: bool = True
    supports_realtime: bool = False
    transport: Literal["http_sse", "websocket"] = "http_sse"
    input_modalities: str = "text"
    output_modalities: str = "text"


class ModelSelectionUpsertRequest(BaseModel):
    realtime_model_config_id: str | None = None
    deep_model_config_id: str | None = None


class ModelSelectionResponse(BaseModel):
    realtime_model_config_id: str | None = None
    deep_model_config_id: str | None = None


class PersonaUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    prompt_template: str = Field(min_length=1)
    tone: str | None = Field(default=None, max_length=40)
    alias: str | None = Field(default=None, max_length=80)


class PersonaSelectionRequest(BaseModel):
    user_persona_id: str = Field(min_length=1)


class PersonaResponse(BaseModel):
    user_persona_id: str
    persona_id: str
    name: str
    description: str | None = None
    prompt_template: str
    tone: str | None = None
    alias: str | None = None
    is_active: bool = True
    is_selected: bool = False


class MemoryCreateRequest(BaseModel):
    type: Literal["preference", "fact", "task"]
    content: str = Field(min_length=1)
    importance: int = Field(default=3, ge=1, le=5)
    chat_id: str | None = None
    source_message_id: str | None = None
    expires_at: str | None = None


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    chat_id: str | None = None
    type: Literal["preference", "fact", "task"]
    content: str
    importance: int
    source_message_id: str | None = None
    created_at: str
    expires_at: str | None = None
