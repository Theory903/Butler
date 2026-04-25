from pydantic import SecretStr

from core.base_config import ButlerBaseConfig


def test_base_config_normalizes_log_level_to_uppercase() -> None:
    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="debug",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    assert config.LOG_LEVEL == "DEBUG"
