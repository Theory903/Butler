"""Communication Channel Management API Routes.

Multi-tenant channel registration, configuration, and management.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.deps import get_channel_registry
from services.realtime.channels import ChannelConfig, ChannelKind, build_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/channels", tags=["integrations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChannelRegistrationRequest(BaseModel):
    """Request to register a new communication channel."""

    channel_id: str = Field(..., description="Unique channel ID")
    channel_kind: ChannelKind = Field(..., description="Type of channel (DISCORD, SLACK, TELEGRAM, WHATSAPP)")
    token: str | None = Field(None, description="Bot token (for Discord/Telegram/WhatsApp)")
    webhook_url: str | None = Field(None, description="Webhook URL (for Slack/WhatsApp)")
    extra: dict[str, Any] = Field(default_factory=dict)


class ChannelResponse(BaseModel):
    """Channel registration response."""

    channel_id: str
    channel_kind: str
    is_connected: bool


class ChannelListResponse(BaseModel):
    """List of registered channels."""

    channels: list[ChannelResponse]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_channel(
    request: ChannelRegistrationRequest,
    http_request: Request,
    registry: Any = Depends(get_channel_registry),
) -> ChannelResponse:
    """Register a new communication channel.

    Multi-tenant: channel_id is scoped to tenant_id from auth context.
    """
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{request.channel_id}"

    if registry.get(scoped_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Channel {request.channel_id} already registered for tenant {tenant_id}",
        )

    config = ChannelConfig(
        kind=request.channel_kind,
        token=request.token,
        webhook_url=request.webhook_url,
        extra=request.extra,
    )

    channel = build_channel(request.channel_kind, config)
    await channel.connect()

    registry.register(scoped_id, channel)

    logger.info("channel_registered", extra={"tenant_id": tenant_id, "channel_id": request.channel_id})

    return ChannelResponse(
        channel_id=request.channel_id,
        channel_kind=request.channel_kind.value,
        is_connected=channel.is_connected,
    )


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    http_request: Request,
    registry: Any = Depends(get_channel_registry),
) -> ChannelListResponse:
    """List all channels for the current tenant."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    prefix = f"{tenant_id}:"

    all_channels = registry.list()
    tenant_channels = [c for c in all_channels if c.startswith(prefix)]

    responses = []
    for scoped_id in tenant_channels:
        channel = registry.get(scoped_id)
        if channel:
            base_id = scoped_id.replace(prefix, "", 1)
            responses.append(
                ChannelResponse(
                    channel_id=base_id,
                    channel_kind=channel.kind.value,
                    is_connected=channel.is_connected,
                )
            )

    return ChannelListResponse(channels=responses)


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: str,
    http_request: Request,
    registry: Any = Depends(get_channel_registry),
) -> dict[str, str]:
    """Delete a channel for the current tenant."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{channel_id}"

    channel = registry.get(scoped_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found for tenant {tenant_id}",
        )

    await channel.disconnect()
    del registry._channels[scoped_id]

    logger.info("channel_deleted", extra={"tenant_id": tenant_id, "channel_id": channel_id})

    return {"message": f"Channel {channel_id} deleted"}


@router.post("/{channel_id}/connect")
async def connect_channel(
    channel_id: str,
    http_request: Request,
    registry: Any = Depends(get_channel_registry),
) -> dict[str, str]:
    """Connect a channel for the current tenant."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{channel_id}"

    channel = registry.get(scoped_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found for tenant {tenant_id}",
        )

    await channel.connect()

    logger.info("channel_connected", extra={"tenant_id": tenant_id, "channel_id": channel_id})

    return {"message": f"Channel {channel_id} connected"}


@router.post("/{channel_id}/disconnect")
async def disconnect_channel(
    channel_id: str,
    http_request: Request,
    registry: Any = Depends(get_channel_registry),
) -> dict[str, str]:
    """Disconnect a channel for the current tenant."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{channel_id}"

    channel = registry.get(scoped_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found for tenant {tenant_id}",
        )

    await channel.disconnect()

    logger.info("channel_disconnected", extra={"tenant_id": tenant_id, "channel_id": channel_id})

    return {"message": f"Channel {channel_id} disconnected"}
