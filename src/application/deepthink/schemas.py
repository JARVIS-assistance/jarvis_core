from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from jarvis_contracts import ClientActionType


class DeepThinkStepInput(BaseModel):
    id: str
    title: str
    description: str


class ClientActionInternal(BaseModel):
    type: ClientActionType
    command: Optional[str] = None
    target: Optional[str] = None
    payload: Optional[str] = None
    args: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    requires_confirm: bool = True
    step_id: Optional[str] = None


class DeepThinkStepOutput(BaseModel):
    step_id: str
    title: str
    status: Literal["completed", "failed", "skipped"]
    content: str
    actions: list[ClientActionInternal] = Field(default_factory=list)


class DeepThinkPlanInternalRequest(BaseModel):
    request_id: str
    message: str = Field(..., min_length=1)


class DeepThinkPlanInternalResponse(BaseModel):
    request_id: str
    goal: str
    steps: list[DeepThinkStepInput] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class DeepThinkInternalRequest(BaseModel):
    request_id: str
    message: str = Field(..., min_length=1)
    plan_steps: list[DeepThinkStepInput] = Field(default_factory=list)
    execution_context: list[str] = Field(default_factory=list)


class DeepThinkInternalResponse(BaseModel):
    request_id: str
    steps: list[DeepThinkStepOutput] = Field(default_factory=list)
    summary: str
    content: str
    actions: list[ClientActionInternal] = Field(default_factory=list)
