from __future__ import annotations
from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict

class MercuryFrame(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = Field(..., pattern="^(req|res|event)$")

class MercuryRequest(MercuryFrame):
    type: str = "req"
    id: str
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)

class MercuryResponse(MercuryFrame):
    type: str = "res"
    id: str
    ok: bool
    payload: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class MercuryEvent(MercuryFrame):
    type: str = "event"
    event: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    seq: Optional[int] = None

class ConnectParams(BaseModel):
    minProtocol: int = 3
    maxProtocol: int = 3
    client: Dict[str, Any]
    role: str = Field(..., pattern="^(node|operator)$")
    scopes: List[str] = Field(default_factory=list)
    caps: List[str] = Field(default_factory=list)
    commands: List[str] = Field(default_factory=list)
    auth: Dict[str, Any] = Field(default_factory=dict)
    device: Dict[str, Any] = Field(default_factory=dict)
