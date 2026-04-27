"""Tests for FinalResponseComposer."""

from domain.runtime.final_response_composer import FinalResponseComposer
from domain.runtime.tool_result_envelope import ToolResultEnvelope


def test_compose_from_tool_result_with_summary():
    """Test composing response with user-visible summary."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_current_time",
        summary="The current time is 10:00 AM UTC",
        user_visible=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert response == "The current time is 10:00 AM UTC"


def test_compose_from_tool_result_without_visibility():
    """Test composing response when not user-visible."""
    envelope = ToolResultEnvelope.success(
        tool_name="internal_tool",
        summary="Internal operation completed",
        user_visible=False,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert response == ""


def test_compose_from_tool_result_safe_to_quote():
    """Test composing response with safe-to-quote data."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_current_time",
        summary="Time retrieved",
        data={"time": "2026-04-25T10:00:00Z"},
        user_visible=True,
        safe_to_quote=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert "Time retrieved" in response


def test_compose_from_multiple_tool_results():
    """Test composing response from multiple tool results."""
    envelopes = [
        ToolResultEnvelope.success(
            tool_name="get_time",
            summary="Current time is 10:00 AM",
            user_visible=True,
        ),
        ToolResultEnvelope.success(
            tool_name="get_weather",
            summary="Weather is sunny",
            user_visible=True,
        ),
    ]

    response = FinalResponseComposer.compose_from_multiple_tool_results(envelopes)
    assert "10:00 AM" in response
    assert "sunny" in response


def test_compose_from_multiple_tool_results_mixed_visibility():
    """Test composing response with mixed visibility."""
    envelopes = [
        ToolResultEnvelope.success(
            tool_name="visible_tool",
            summary="Visible result",
            user_visible=True,
        ),
        ToolResultEnvelope.success(
            tool_name="internal_tool",
            summary="Internal result",
            user_visible=False,
        ),
    ]

    response = FinalResponseComposer.compose_from_multiple_tool_results(envelopes)
    assert "Visible result" in response
    assert "Internal result" not in response


def test_compose_from_multiple_tool_results_empty():
    """Test composing response with no visible results."""
    envelopes = [
        ToolResultEnvelope.success(
            tool_name="internal_tool",
            summary="Internal result",
            user_visible=False,
        ),
    ]

    response = FinalResponseComposer.compose_from_multiple_tool_results(envelopes)
    assert response == ""


def test_compose_from_tool_result_with_locale():
    """Test composing response with locale parameter."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_time",
        summary="Time retrieved",
        data={"time": "2026-04-25T10:00:00Z"},
        user_visible=True,
        safe_to_quote=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope, locale="en", timezone="UTC")
    # Locale handling is a TODO, so just verify it doesn't crash
    assert isinstance(response, str)


def test_compose_from_tool_result_time_data():
    """Test formatting time-related data."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_time",
        data={"current_time": "2026-04-25T10:00:00Z"},
        user_visible=True,
        safe_to_quote=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert "2026" in response or "April" in response or "date" in response.lower()


def test_compose_from_tool_result_date_data():
    """Test formatting date-related data."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_date",
        data={"date": "2026-04-25"},
        user_visible=True,
        safe_to_quote=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert "2026" in response or "April" in response or "date" in response.lower()


def test_compose_from_tool_result_generic_data():
    """Test formatting generic structured data."""
    envelope = ToolResultEnvelope.success(
        tool_name="get_info",
        data={"name": "test", "value": 123},
        user_visible=True,
        safe_to_quote=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert isinstance(response, str)


def test_compose_from_tool_result_empty_data():
    """Test composing response with empty data."""
    envelope = ToolResultEnvelope.success(
        tool_name="test_tool",
        user_visible=True,
    )

    response = FinalResponseComposer.compose_from_tool_result(envelope)
    assert "test_tool" in response.lower()


def test_compose_from_multiple_results_single():
    """Test composing from single result in list."""
    envelopes = [
        ToolResultEnvelope.success(
            tool_name="get_time",
            summary="Time is 10:00 AM",
            user_visible=True,
        ),
    ]

    response = FinalResponseComposer.compose_from_multiple_tool_results(envelopes)
    assert response == "Time is 10:00 AM"
