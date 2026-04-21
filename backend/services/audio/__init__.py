from typing import Any

__all__ = ["AudioService"]


def __getattr__(name: str) -> Any:
    if name == "AudioService":
        from .service import AudioService

        return AudioService
    raise AttributeError(name)
