"""Capability validation core.

Enforces capability constraints. A device cannot be commanded to execute
a behavior it does not possess in its schema.
"""

import structlog

from domain.device.models import DeviceRegistry

logger = structlog.get_logger(__name__)


class CapabilityValidator:
    """Validates requested states against device capabilities."""

    # Pre-defined known capabilities to standardize action execution
    KNOWN_CAPABILITIES = {
        "switch.power": ["power_on", "power_off", "toggle"],
        "light.brightness": ["set_brightness", "get_brightness"],
        "lock.security": ["lock", "unlock", "get_status"],
        "av.media": ["play", "pause", "set_volume", "mute"],
        "climate.thermostat": ["set_target_temperature", "set_mode"],
        "sensor.presence": ["get_occupancy"],
        "sensor.environment": ["get_temperature", "get_humidity"],
    }

    @classmethod
    def validate_action(cls, device: DeviceRegistry, action: str) -> bool:
        """
        Determines if the requested action is resolvable by any of the device's recorded capabilities.
        """
        device_caps = device.capabilities

        # A device list might look like: ["switch.power", "sensor.environment"]
        if not device_caps:
            logger.warning("capability_rejected_empty", device=device.id, requested_action=action)
            return False

        for cap in device_caps:
            supported_actions = cls.KNOWN_CAPABILITIES.get(cap, [])
            if action in supported_actions:
                return True

        logger.warning(
            "capability_rejected_mismatch",
            device=device.id,
            requested_action=action,
            available_capabilities=device_caps,
        )
        return False
