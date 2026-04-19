import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MLAdmin:
    """Twitter-Server style administrative controls for the ML Platform.
    
    Enables runtime management of:
    - Service Flags (Dynamic Toggles)
    - Shadow Deployment Status
    - Request Quotas (Token Buckets)
    """

    def __init__(self):
        # Default flags
        self._flags = {
            "enable_t2_escalation": True,
            "enable_t3_escalation": True,
            "shadow_mode_enabled": False,
            "rerank_ml_weight": 0.7,
            "rerank_signal_weight": 0.3
        }
        self._metrics = {
            "requests_total": 0,
            "shadow_mismatch_count": 0,
            "errors_total": 0
        }

    def get_flag(self, name: str, default: Any = None) -> Any:
        return self._flags.get(name, default)

    def set_flag(self, name: str, value: Any):
        logger.info("admin_flag_changed", name=name, old=self._flags.get(name), new=value)
        self._flags[name] = value

    def update_metrics(self, category: str, increment: int = 1):
        if category in self._metrics:
            self._metrics[category] += increment

    def get_stats(self) -> Dict[str, Any]:
        return {
            "flags": self._flags,
            "metrics": self._metrics,
            "uptime_status": "healthy"
        }

class HealthProbe:
    """Deep observability probes for the Intelligence Platform."""
    
    def __init__(self, registry):
        self._registry = registry

    async def check_readiness(self) -> Dict[str, Any]:
        """Check if all active backends are reachable."""
        results = {}
        # 1. Check Registry
        results["registry"] = "ok" if self._registry.MODELS else "fail"
        
        # 2. Check local vLLM (Phase 2 stub)
        t2_models = self._registry.get_active_by_tier(2)
        results["t2_backends"] = "available" if t2_models else "empty"
        
        # 3. Check connectivity to Cloud T3 (Mocked)
        results["t3_connectivity"] = "pingable"
        
        status = "healthy" if all(v != "fail" for v in results.values()) else "degraded"
        return {"status": status, "probes": results}

class ShadowManager:
    """Manages dual-inference for 'Shadow' deployment verification."""
    
    def __init__(self, runtime):
        self._runtime = runtime

    async def execute_shadow(self, primary_result: Any, shadow_model: str, request_data: Dict[str, Any]):
        """Fire-and-forget shadow request to compare with primary."""
        if not shadow_model:
            return
            
        async def _run_shadow():
            try:
                shadow_result = await self._runtime.execute_inference(shadow_model, request_data)
                # In a real system, we'd log the diff between shadow_result and primary_result
                logger.debug("shadow_execution_complete", 
                             model=shadow_model, 
                             mismatch=False) # Simplified for Phase 3
            except Exception as e:
                logger.warning("shadow_execution_failed", error=str(e))

        asyncio.create_task(_run_shadow())
