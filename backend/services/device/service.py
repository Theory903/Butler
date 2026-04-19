import uuid
import json
import structlog
from typing import Dict, Any, List
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from domain.device.models import DeviceRegistry
from services.device.adapters import AdapterRegistry
from services.device.policy import DevicePolicy
from services.device.capabilities import CapabilityValidator

logger = structlog.get_logger(__name__)


class DeviceService:
    """Device registry and operational automation control plane.
    
    Orchestrates the lifecycle, discovery, and physical validation pipelines ensuring
    requests map cleanly and securely to specific hardware protocols.
    """
    
    def __init__(
        self, 
        redis: Redis,
        db: AsyncSession
    ):
        self._redis = redis
        self._db = db
        self._adapters = AdapterRegistry()
    
    async def get_device(self, device_id: str) -> DeviceRegistry:
        device = await self._db.get(DeviceRegistry, uuid.UUID(device_id))
        if not device:
            raise ValueError(f"Device {device_id} not found in registry")
        return device

    async def pair_device(self, account_id: str, device_config: dict) -> DeviceRegistry:
        """
        Officially maps a discovered hardware footprint to a network tenant.
        Devices default to 'pending' state—preventing operational action until the challenge finishes.
        """
        device = DeviceRegistry(
            owner_account_id=uuid.UUID(account_id),
            protocol=device_config.get("protocol", "api"),
            vendor=device_config.get("vendor", "butler_generic"),
            model=device_config.get("model", "unknown_device"),
            capabilities=device_config.get("capabilities", []),
            trust_state="pending", # Safe implicit default!
            online_state="resolving",
        )
        self._db.add(device)
        await self._db.commit()
        await self._db.refresh(device)
        logger.info("device_pairing_initiated", device=device.id, protocol=device.protocol)
        return device
    
    async def list_devices(self, account_id: str) -> List[DeviceRegistry]:
        stmt = select(DeviceRegistry).where(DeviceRegistry.owner_account_id == uuid.UUID(account_id))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_state(self, device_id: str) -> Dict[str, Any]:
        """
        Attempts a hyper-fast Redis fetch. 
        Upon Cache Miss, fetches the Device model to resolve the correct Hardware Adapter
        and issues a physical state-fetch over the local protocol.
        """
        cached = await self._redis.get(f"device:{device_id}:state")
        if cached:
            return json.loads(cached)
            
        logger.info("device_state_cache_miss", device=device_id)
        
        # Hydrate through physical adapter integration
        device = await self.get_device(device_id)
        adapter = self._adapters.resolve(device.protocol)
        
        try:
            live_state = await adapter.fetch_state(device)
            # Fire an async commit to redis with 5-minute expiry to heal the cache loop
            await self._redis.setex(f"device:{device_id}:state", 300, json.dumps(live_state))
            return live_state
        except Exception as e:
            logger.error("adapter_fetch_failed", device=device_id, error=str(e))
            return {"status": "error", "message": "Physical hardware unreachable."}
    
    async def dispatch_command(self, requester_account_id: str, device_id: str, action: str, params: dict) -> Dict[str, Any]:
        """
        The formal Action Pipeline mapping the software request strictly through structural
        and security gating procedures before executing physical transitions.
        """
        device = await self.get_device(device_id)
        
        # 1. Device Policy verification Check (Permissions, Online State, Local Trust)
        policy_result = DevicePolicy.evaluate_dispatch(device, requester_account_id)
        if not policy_result.allowed:
            logger.warning("device_command_drop_policy", device=device_id, action=action, reason=policy_result.reason)
            raise ValueError(f"Policy Rejection: {policy_result.reason}")
            
        # 2. Capability Schema verification (Does 'smart_lock' have 'play_music'?)
        is_supported = CapabilityValidator.validate_action(device, action)
        if not is_supported:
            raise ValueError(f"Action '{action}' unavailable based on device capability schema.")
            
        # 3. Locate Protocol & Dispatch
        adapter = self._adapters.resolve(device.protocol)
        logger.info("device_command_dispatching", device=device_id, protocol=device.protocol, action=action)
        
        try:
            result = await adapter.dispatch_command(device, action, params)
            # Proactively clear physical state cache so next read isn't immediately stale
            await self._redis.delete(f"device:{device_id}:state")
            return result
        except Exception as e:
            logger.error("adapter_dispatch_failed", device=device_id, error=str(e))
            raise RuntimeError(f"Hardware dispatch failure: {str(e)}")
