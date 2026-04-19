import json
import hashlib
import structlog
from typing import Optional, Dict, Any
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

class IdempotencyManager:
    """
    Production deduplication utilizing Redis atomic `setnx` semantics.
    Enforces the dedupe window to drop exact replays without false positives.
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.TTL_SECONDS = 86400  # 24 hours dedupe window

    def compute_idem_key(
        self, 
        actor: str,
        channel: str,
        recipient: str,
        content: Dict[str, Any],
        template_id: Optional[str] = None,
        media_ref: Optional[str] = None
    ) -> str:
        """Computes deterministic robust hash for checking duplicate payloads."""
        
        try:
            content_json = json.dumps(content, sort_keys=True)
        except Exception:
            content_json = str(content)
            
        canonical = {
            "actor": actor,
            "channel": channel,
            "recipient": recipient,
            "content_hash": hashlib.sha256(content_json.encode('utf-8')).hexdigest()[:16],
            "template_id": template_id,
            "media_ref": media_ref
        }
        
        key_input = json.dumps(canonical, sort_keys=True)
        # Avoid prepending 'idem:' twice in other logic
        return f"idem:{hashlib.sha256(key_input.encode('utf-8')).hexdigest()[:24]}"
    
    async def try_acquire_lock(self, idem_key: str, message_id: str) -> bool:
        """
        Attempts to write the key atomically.
        Returns True if acquired (message is new).
        Returns False if key exists (message is duplicate).
        """
        payload = json.dumps({"message_id": message_id, "status": "processing"})
        # NX=True ensures it only writes if the key does not exist. Race safe.
        acquired = await self.redis.set(idem_key, payload, ex=self.TTL_SECONDS, nx=True)
        return bool(acquired)

    async def get_existing_message_id(self, idem_key: str) -> Optional[str]:
        """Fetch the message_id for a blocked duplicate request."""
        existing = await self.redis.get(idem_key)
        if existing:
            try:
                data = json.loads(existing)
                return data.get("message_id")
            except json.JSONDecodeError:
                pass
        return None
    
    async def mark_processed(
        self, 
        idem_key: str, 
        message_id: str, 
        provider_ref: Optional[str] = None
    ):
        """Update the lock with the provider ref post-delivery."""
        payload = json.dumps({
            "message_id": message_id,
            "provider_ref": provider_ref,
            "status": "processed"
        })
        # Reset TTL to full window upon processing completion.
        await self.redis.set(idem_key, payload, ex=self.TTL_SECONDS)
