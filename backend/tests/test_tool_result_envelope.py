"""Tests for ToolResultEnvelope."""

import pytest

from domain.runtime.tool_result_envelope import (
    ToolResultEnvelope,
    ToolResultError,
    ToolStatus,
)


def test_tool_result_envelope_success():
    """Test creating a successful tool result envelope."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_current_time",
        summary="Current time retrieved",
        data={"time": "2026-04-25T10:00:00Z"},
        user_visible=True,
        safe_to_quote=True,
        latency_ms=100,
    )

    assert envelope.tool_name == "get_current_time"
    assert envelope.status == "success"
    assert envelope.summary == "Current time retrieved"
    assert envelope.data == {"time": "2026-04-25T10:00:00Z"}
    assert envelope.user_visible is True
    assert envelope.safe_to_quote is True
    assert envelope.latency_ms == 100
    assert envelope.is_success()
    assert not envelope.is_partial()
    assert not envelope.is_failed()


def test_tool_result_envelope_partial():
    """Test creating a partially successful tool result envelope."""
    envelope = ToolResultEnvelope.partial(
        tool_name="search_web",
        summary="Partial search results",
        data={"results": ["item1"]},
        user_visible=True,
        latency_ms=200,
    )

    assert envelope.tool_name == "search_web"
    assert envelope.status == "partial"
    assert envelope.is_partial()
    assert not envelope.is_success()
    assert not envelope.is_failed()


def test_tool_result_envelope_failure():
    """Test creating a failed tool result envelope."""
    envelope = ToolResultEnvelope.failure(
        tool_name="external_api",
        error_code="TIMEOUT",
        error_message="Request timed out",
        latency_ms=5000,
    )

    assert envelope.tool_name == "external_api"
    assert envelope.status == "failed"
    assert envelope.error_code == "TIMEOUT"
    assert envelope.error_message == "Request timed out"
    assert envelope.is_failed()
    assert not envelope.is_success()
    assert not envelope.is_partial()


def test_tool_result_envelope_require_success():
    """Test require_success raises on non-success."""
    envelope = ToolResultEnvelope.failure(
        tool_name="test_tool",
        error_code="ERROR",
        error_message="Test error",
    )

    with pytest.raises(ToolResultError) as exc_info:
        envelope.require_success()

    assert "test_tool" in str(exc_info.value)
    assert "failed" in str(exc_info.value)


def test_tool_result_envelope_require_success_passes():
    """Test require_success passes on success."""
    envelope = ToolResultEnvelope.success(
        tool_name="test_tool",
        summary="Success",
    )

    # Should not raise
    envelope.require_success()


def test_tool_result_envelope_get_user_visible_summary():
    """Test get_user_visible_summary."""
    envelope = ToolResultEnvelope.success(
        tool_name="test_tool",
        summary="Test summary",
        user_visible=True,
    )

    assert envelope.get_user_visible_summary() == "Test summary"


def test_tool_result_envelope_get_user_visible_summary_not_visible():
    """Test get_user_visible_summary returns empty when not visible."""
    envelope = ToolResultEnvelope.success(
        tool_name="test_tool",
        summary="Test summary",
        user_visible=False,
    )

    assert envelope.get_user_visible_summary() == ""


def test_tool_result_envelope_get_user_visible_summary_no_summary():
    """Test get_user_visible_summary returns default when no summary."""
    envelope = ToolResultEnvelope.success(
        tool_name="test_tool",
        user_visible=True,
    )

    assert "test_tool" in envelope.get_user_visible_summary()


def test_tool_result_envelope_defaults():
    """Test default values for ToolResultEnvelope."""
    envelope = ToolResultEnvelope.success(tool_name="test_tool")

    assert envelope.summary is None
    assert envelope.data == {}
    assert envelope.artifacts == []
    assert envelope.user_visible is False
    assert envelope.safe_to_quote is False
    assert envelope.error_code is None
    assert envelope.error_message is None
    assert envelope.latency_ms is None


def test_tool_result_envelope_status_values():
    """Test valid status values."""
    assert ToolResultEnvelope.success(tool_name="test").status == "success"
    assert ToolResultEnvelope.partial(tool_name="test").status == "partial"
    assert ToolResultEnvelope.failure(tool_name="test").status == "failed"
