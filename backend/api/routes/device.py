"""API routes for Device / Environment / Ambient automation operations.

Re-mapped away from raw registration into semantic 'pairing' flows per IoT trust rules.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.gateway import get_current_account
from core.deps import get_db, get_redis
from domain.auth.contracts import AccountContext
from services.device.service import DeviceService


def get_device_service(
    redis: Redis = Depends(get_redis), db: AsyncSession = Depends(get_db)
) -> DeviceService:
    return DeviceService(redis=redis, db=db)


router = APIRouter(prefix="/devices", tags=["device"])


class PairDeviceRequest(BaseModel):
    protocol: str = "api"
    vendor: str = "butler_generic"
    model: str = "unknown_model"
    capabilities: list[str] = []


class DeviceActionRequest(BaseModel):
    action: str
    params: dict = {}


class DeviceResponse(BaseModel):
    id: str
    protocol: str
    vendor: str
    model: str
    capabilities: list[str]
    trust_state: str
    online_state: str


@router.get("/", response_model=list[DeviceResponse])
async def list_devices(
    account: AccountContext = Depends(get_current_account),
    svc: DeviceService = Depends(get_device_service),
):
    devices = await svc.list_devices(str(account.account_id))
    return [
        DeviceResponse(
            id=str(d.id),
            protocol=d.protocol,
            vendor=d.vendor,
            model=d.model,
            capabilities=d.capabilities,
            trust_state=d.trust_state,
            online_state=d.online_state,
        )
        for d in devices
    ]


@router.post("/pair", response_model=DeviceResponse)
async def pair_device(
    req: PairDeviceRequest,
    account: AccountContext = Depends(get_current_account),
    svc: DeviceService = Depends(get_device_service),
):
    device = await svc.pair_device(str(account.account_id), req.model_dump())
    return DeviceResponse(
        id=str(device.id),
        protocol=device.protocol,
        vendor=device.vendor,
        model=device.model,
        capabilities=device.capabilities,
        trust_state=device.trust_state,
        online_state=device.online_state,
    )


@router.get("/{device_id}/state")
async def get_device_state(device_id: str, svc: DeviceService = Depends(get_device_service)):
    # Depending on adapter load, this may block until Zigbee/MQTT returns.
    return await svc.get_state(device_id)


@router.post("/{device_id}/action")
async def dispatch_device_action(
    device_id: str,
    req: DeviceActionRequest,
    account: AccountContext = Depends(get_current_account),
    svc: DeviceService = Depends(get_device_service),
):
    try:
        return await svc.dispatch_command(
            requester_account_id=str(account.account_id),
            device_id=device_id,
            action=req.action,
            params=req.params,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
