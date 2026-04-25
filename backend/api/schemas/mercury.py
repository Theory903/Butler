from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MercuryFrame(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = Field(..., pattern="^(req|res|event)$")


class MercuryRequest(MercuryFrame):
    type: str = "req"
    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class MercuryResponse(MercuryFrame):
    type: str = "res"
    id: str
    ok: bool
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class MercuryEvent(MercuryFrame):
    type: str = "event"
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
    seq: int | None = None


class ConnectParams(BaseModel):
    minProtocol: int = 3
    maxProtocol: int = 3
    client: dict[str, Any]
    role: str = Field(..., pattern="^(node|operator)$")
    scopes: list[str] = Field(default_factory=list)
    caps: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    auth: dict[str, Any] = Field(default_factory=dict)
    device: dict[str, Any] = Field(default_factory=dict)
