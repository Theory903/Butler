"""Comprehensive tests for TenantAwareLogger.

Tests cover:
- TenantAwareLogger initialization
- Context sanitization (tenant_id/account_id hashing)
- All log level methods (info, warning, error, debug, exception)
- Hash function consistency
- Edge cases and error conditions
- Hardened error handling
"""

from unittest.mock import patch

from core.tenant_aware_logger import (
    TenantAwareLogger,
    get_tenant_aware_logger,
    hash_account_id,
    hash_tenant_id,
)


class TestHashFunctions:
    """Test hash functions for tenant and account IDs."""

    def test_hash_tenant_id(self):
        """Test tenant_id hashing."""
        result = hash_tenant_id("tenant_1")
        assert len(result) == 8
        assert result != "tenant_1"

    def test_hash_tenant_id_consistency(self):
        """Test tenant_id hash is consistent."""
        result1 = hash_tenant_id("tenant_1")
        result2 = hash_tenant_id("tenant_1")
        assert result1 == result2

    def test_hash_tenant_id_different_inputs(self):
        """Test different tenant_ids produce different hashes."""
        result1 = hash_tenant_id("tenant_1")
        result2 = hash_tenant_id("tenant_2")
        assert result1 != result2

    def test_hash_account_id(self):
        """Test account_id hashing."""
        result = hash_account_id("account_1")
        assert len(result) == 8
        assert result != "account_1"

    def test_hash_account_id_consistency(self):
        """Test account_id hash is consistent."""
        result1 = hash_account_id("account_1")
        result2 = hash_account_id("account_1")
        assert result1 == result2

    def test_hash_account_id_different_inputs(self):
        """Test different account_ids produce different hashes."""
        result1 = hash_account_id("account_1")
        result2 = hash_account_id("account_2")
        assert result1 != result2

    def test_hash_with_special_characters(self):
        """Test hashing with special characters."""
        result = hash_tenant_id("tenant-1_special@#")
        assert len(result) == 8

    def test_hash_with_unicode(self):
        """Test hashing with unicode characters."""
        result = hash_tenant_id("tenant_日本語")
        assert len(result) == 8

    def test_hash_with_empty_string(self):
        """Test hashing empty string."""
        result = hash_tenant_id("")
        assert len(result) == 8


class TestTenantAwareLogger:
    """Test TenantAwareLogger initialization and configuration."""

    def test_init(self):
        """Test TenantAwareLogger initialization."""
        logger = TenantAwareLogger("test_logger")
        assert logger is not None
        assert logger.logger is not None

    def test_init_with_different_name(self):
        """Test initialization with different logger name."""
        logger1 = TenantAwareLogger("logger_1")
        logger2 = TenantAwareLogger("logger_2")
        assert logger1.logger is not logger2.logger


class TestContextSanitization:
    """Test context sanitization."""

    def test_sanitize_context_with_tenant_id(self):
        """Test sanitization with tenant_id."""
        logger = TenantAwareLogger("test_logger")
        context = {"tenant_id": "tenant_1", "user_id": "user_1"}
        sanitized = logger._sanitize_context(context)

        assert "tenant_id" not in sanitized
        assert "tenant_hash" in sanitized
        assert "user_id" in sanitized
        assert sanitized["user_id"] == "user_1"

    def test_sanitize_context_with_account_id(self):
        """Test sanitization with account_id."""
        logger = TenantAwareLogger("test_logger")
        context = {"account_id": "account_1", "user_id": "user_1"}
        sanitized = logger._sanitize_context(context)

        assert "account_id" not in sanitized
        assert "account_hash" in sanitized
        assert "user_id" in sanitized

    def test_sanitize_context_with_both_ids(self):
        """Test sanitization with both tenant_id and account_id."""
        logger = TenantAwareLogger("test_logger")
        context = {
            "tenant_id": "tenant_1",
            "account_id": "account_1",
            "user_id": "user_1",
        }
        sanitized = logger._sanitize_context(context)

        assert "tenant_id" not in sanitized
        assert "account_id" not in sanitized
        assert "tenant_hash" in sanitized
        assert "account_hash" in sanitized
        assert "user_id" in sanitized

    def test_sanitize_context_without_ids(self):
        """Test sanitization without tenant/account IDs."""
        logger = TenantAwareLogger("test_logger")
        context = {"user_id": "user_1", "action": "test"}
        sanitized = logger._sanitize_context(context)

        assert "tenant_id" not in sanitized
        assert "account_id" not in sanitized
        assert "tenant_hash" not in sanitized
        assert "account_hash" not in sanitized
        assert "user_id" in sanitized
        assert "action" in sanitized

    def test_sanitize_context_original_unchanged(self):
        """Test that original context is not mutated."""
        logger = TenantAwareLogger("test_logger")
        context = {"tenant_id": "tenant_1", "user_id": "user_1"}
        original_tenant_id = context["tenant_id"]

        sanitized = logger._sanitize_context(context)

        assert context["tenant_id"] == original_tenant_id
        assert "tenant_id" in context

    def test_sanitize_context_hash_values(self):
        """Test that hash values are correct."""
        logger = TenantAwareLogger("test_logger")
        context = {"tenant_id": "tenant_1", "account_id": "account_1"}
        sanitized = logger._sanitize_context(context)

        expected_tenant_hash = hash_tenant_id("tenant_1")
        expected_account_hash = hash_account_id("account_1")

        assert sanitized["tenant_hash"] == expected_tenant_hash
        assert sanitized["account_hash"] == expected_account_hash


class TestLogMethods:
    """Test all log level methods."""

    def test_info_log(self):
        """Test info log method."""
        logger = TenantAwareLogger("test_logger")
        # Should not raise any exception
        logger.info("Test message", tenant_id="tenant_1")

    def test_info_log_with_sanitization(self):
        """Test info log sanitizes tenant_id."""
        logger = TenantAwareLogger("test_logger")
        # Mock the underlying logger to capture the sanitized context
        with patch.object(logger.logger, "info") as mock_info:
            logger.info("Test message", tenant_id="tenant_1", user_id="user_1")

            call_args = mock_info.call_args
            assert call_args[0][0] == "Test message"
            assert "tenant_id" not in call_args[1]
            assert "tenant_hash" in call_args[1]
            assert call_args[1]["user_id"] == "user_1"

    def test_warning_log(self):
        """Test warning log method."""
        logger = TenantAwareLogger("test_logger")
        logger.warning("Test warning", account_id="account_1")

    def test_warning_log_with_sanitization(self):
        """Test warning log sanitizes account_id."""
        logger = TenantAwareLogger("test_logger")
        with patch.object(logger.logger, "warning") as mock_warning:
            logger.warning("Test warning", account_id="account_1")

            call_args = mock_warning.call_args
            assert "account_id" not in call_args[1]
            assert "account_hash" in call_args[1]

    def test_error_log(self):
        """Test error log method."""
        logger = TenantAwareLogger("test_logger")
        logger.error("Test error", tenant_id="tenant_1")

    def test_error_log_with_sanitization(self):
        """Test error log sanitizes both IDs."""
        logger = TenantAwareLogger("test_logger")
        with patch.object(logger.logger, "error") as mock_error:
            logger.error("Test error", tenant_id="tenant_1", account_id="account_1")

            call_args = mock_error.call_args
            assert "tenant_id" not in call_args[1]
            assert "account_id" not in call_args[1]
            assert "tenant_hash" in call_args[1]
            assert "account_hash" in call_args[1]

    def test_debug_log(self):
        """Test debug log method."""
        logger = TenantAwareLogger("test_logger")
        logger.debug("Test debug", tenant_id="tenant_1")

    def test_debug_log_with_sanitization(self):
        """Test debug log sanitizes context."""
        logger = TenantAwareLogger("test_logger")
        with patch.object(logger.logger, "debug") as mock_debug:
            logger.debug("Test debug", tenant_id="tenant_1")

            call_args = mock_debug.call_args
            assert "tenant_id" not in call_args[1]
            assert "tenant_hash" in call_args[1]

    def test_exception_log(self):
        """Test exception log method."""
        logger = TenantAwareLogger("test_logger")
        logger.exception("Test exception", tenant_id="tenant_1")

    def test_exception_log_with_sanitization(self):
        """Test exception log sanitizes context."""
        logger = TenantAwareLogger("test_logger")
        with patch.object(logger.logger, "exception") as mock_exception:
            logger.exception("Test exception", account_id="account_1")

            call_args = mock_exception.call_args
            assert "account_id" not in call_args[1]
            assert "account_hash" in call_args[1]


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_log_with_empty_context(self):
        """Test logging with empty context."""
        logger = TenantAwareLogger("test_logger")
        logger.info("Test message")

    def test_log_with_large_context(self):
        """Test logging with large context."""
        logger = TenantAwareLogger("test_logger")
        large_context = {f"key_{i}": f"value_{i}" for i in range(100)}
        logger.info("Test message", **large_context)

    def test_log_with_none_values(self):
        """Test logging with None values."""
        logger = TenantAwareLogger("test_logger")
        logger.info("Test message", tenant_id=None, user_id=None)  # type: ignore

    def test_log_with_numeric_values(self):
        """Test logging with numeric values."""
        logger = TenantAwareLogger("test_logger")
        logger.info("Test message", count=42, price=3.14)

    def test_log_with_nested_dict(self):
        """Test logging with nested dictionary."""
        logger = TenantAwareLogger("test_logger")
        logger.info("Test message", data={"nested": {"key": "value"}})

    def test_log_with_list_values(self):
        """Test logging with list values."""
        logger = TenantAwareLogger("test_logger")
        logger.info("Test message", items=[1, 2, 3])

    def test_hash_collision_unlikely(self):
        """Test that hash collisions are unlikely."""
        hashes = set()
        for i in range(1000):
            h = hash_tenant_id(f"tenant_{i}")
            hashes.add(h)

        # With 1000 different inputs, we should have close to 1000 unique hashes
        # (probability of collision is extremely low with SHA256 truncated to 8 chars)
        assert len(hashes) > 990


class TestFactoryFunction:
    """Test factory function."""

    def test_get_tenant_aware_logger(self):
        """Test factory function."""
        logger = get_tenant_aware_logger("test_logger")
        assert isinstance(logger, TenantAwareLogger)

    def test_get_tenant_aware_logger_different_names(self):
        """Test factory function with different names."""
        logger1 = get_tenant_aware_logger("logger_1")
        logger2 = get_tenant_aware_logger("logger_2")
        assert logger1 is not logger2


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_full_logging_flow(self):
        """Test full logging flow with sanitization."""
        logger = TenantAwareLogger("test_logger")

        with patch.object(logger.logger, "info") as mock_info:
            logger.info(
                "User action",
                tenant_id="tenant_1",
                account_id="account_1",
                user_id="user_1",
                action="login",
            )

            call_args = mock_info.call_args
            assert call_args[0][0] == "User action"
            assert "tenant_id" not in call_args[1]
            assert "account_id" not in call_args[1]
            assert "tenant_hash" in call_args[1]
            assert "account_hash" in call_args[1]
            assert call_args[1]["user_id"] == "user_1"
            assert call_args[1]["action"] == "login"

    def test_multiple_log_calls(self):
        """Test multiple sequential log calls."""
        logger = TenantAwareLogger("test_logger")

        with patch.object(logger.logger, "info") as mock_info:
            for i in range(10):
                logger.info(f"Message {i}", tenant_id=f"tenant_{i}")

            assert mock_info.call_count == 10

    def test_different_log_levels(self):
        """Test different log levels in sequence."""
        logger = TenantAwareLogger("test_logger")

        with (
            patch.object(logger.logger, "info") as mock_info,
            patch.object(logger.logger, "warning") as mock_warning,
            patch.object(logger.logger, "error") as mock_error,
        ):
            logger.info("Info", tenant_id="tenant_1")
            logger.warning("Warning", tenant_id="tenant_1")
            logger.error("Error", tenant_id="tenant_1")

            assert mock_info.call_count == 1
            assert mock_warning.call_count == 1
            assert mock_error.call_count == 1

    def test_log_with_unicode_message(self):
        """Test logging with unicode message."""
        logger = TenantAwareLogger("test_logger")
        logger.info("メッセージ 日本語 中文", tenant_id="tenant_1")

    def test_log_with_very_long_message(self):
        """Test logging with very long message."""
        logger = TenantAwareLogger("test_logger")
        long_message = "Test " * 10000
        logger.info(long_message, tenant_id="tenant_1")
