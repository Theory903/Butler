"""FinalResponseComposer - converts internal evidence into user-facing language."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .tool_result_envelope import ToolResultEnvelope


class FinalResponseComposer:
    """Converts internal evidence into user-facing language.

    Example:
        Input: ToolResultEnvelope(
            tool_name="get_current_time",
            status="success",
            summary="Current UTC date/time resolved.",
            data={
                "current_time": "2026-04-25T10:02:32.978425+00:00",
                "timezone": "UTC",
                "formatted": "2026-04-25 10:02:32 UTC",
            },
            user_visible=True,
            safe_to_quote=True,
        )

        Output: The current date is April 25, 2026. In UTC, the time is 10:02.

        If user locale/timezone is India:
        Output: The current date is April 25, 2026. In India, the time is 3:32 PM IST.
    """

    @classmethod
    def compose_from_tool_result(
        cls,
        envelope: ToolResultEnvelope,
        locale: str = "en",
        timezone: str = "UTC",
    ) -> str:
        """Compose a user-facing response from a tool result envelope.

        Args:
            envelope: ToolResultEnvelope containing tool execution result
            locale: User locale (e.g., "en", "en-US", "hi-IN")
            timezone: User timezone (e.g., "UTC", "Asia/Kolkata")

        Returns:
            User-facing response string
        """
        if not envelope.user_visible:
            return ""

        if envelope.summary:
            return cls._localize_summary(envelope.summary, locale, timezone)

        if envelope.safe_to_quote and envelope.data:
            return cls._format_data_as_text(envelope.data, locale, timezone)

        return f"{envelope.tool_name} completed."

    @classmethod
    def compose_from_multiple_tool_results(
        cls,
        envelopes: list[ToolResultEnvelope],
        locale: str = "en",
        timezone: str = "UTC",
    ) -> str:
        """Compose a user-facing response from multiple tool result envelopes.

        Args:
            envelopes: List of ToolResultEnvelope instances
            locale: User locale (e.g., "en", "en-US", "hi-IN")
            timezone: User timezone (e.g., "UTC", "Asia/Kolkata")

        Returns:
            User-facing response string
        """
        visible_results = [e for e in envelopes if e.user_visible]

        if not visible_results:
            return ""

        if len(visible_results) == 1:
            return cls.compose_from_tool_result(visible_results[0], locale, timezone)

        # Multiple results: compose a summary
        summaries = []
        for envelope in visible_results:
            summary = cls.compose_from_tool_result(envelope, locale, timezone)
            if summary:
                summaries.append(summary)

        return " ".join(summaries)

    @classmethod
    def _localize_summary(cls, summary: str, locale: str, timezone: str) -> str:
        """Localize a summary for the given locale and timezone.

        Args:
            summary: Summary text to localize
            locale: User locale
            timezone: User timezone

        Returns:
            Localized summary
        """
        # TODO: Implement proper localization with date/time formatting
        # For now, return as-is
        return summary

    @classmethod
    def _format_data_as_text(
        cls, data: dict[str, Any], locale: str, timezone: str
    ) -> str:
        """Format structured data as user-friendly text.

        Args:
            data: Structured data from tool output
            locale: User locale
            timezone: User timezone

        Returns:
            User-friendly text representation
        """
        # Special handling for common data types
        if "current_time" in data or "time" in data:
            return cls._format_time_data(data, locale, timezone)

        if "date" in data:
            return cls._format_date_data(data, locale, timezone)

        # Generic formatting for other data types
        return cls._format_generic_data(data)

    @classmethod
    def _format_time_data(
        cls, data: dict[str, Any], locale: str, timezone: str
    ) -> str:
        """Format time-related data as user-friendly text.

        Args:
            data: Time-related data
            locale: User locale
            timezone: User timezone

        Returns:
            User-friendly time text
        """
        current_time = data.get("current_time") or data.get("time")
        if not current_time:
            return "Time information retrieved."

        try:
            # Parse ISO format datetime
            if isinstance(current_time, str):
                dt = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
            else:
                dt = current_time

            # Format date
            date_str = dt.strftime("%B %d, %Y")

            # Format time based on timezone
            # TODO: Implement proper timezone conversion
            time_str = dt.strftime("%I:%M %p")

            return f"The current date is {date_str}. The time is {time_str} {timezone}."
        except Exception:
            return "Time information retrieved."

    @classmethod
    def _format_date_data(
        cls, data: dict[str, Any], locale: str, timezone: str
    ) -> str:
        """Format date-related data as user-friendly text.

        Args:
            data: Date-related data
            locale: User locale
            timezone: User timezone

        Returns:
            User-friendly date text
        """
        date_value = data.get("date")
        if not date_value:
            return "Date information retrieved."

        try:
            if isinstance(date_value, str):
                dt = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
            else:
                dt = date_value

            date_str = dt.strftime("%B %d, %Y")
            return f"The date is {date_str}."
        except Exception:
            return "Date information retrieved."

    @classmethod
    def _format_generic_data(cls, data: dict[str, Any]) -> str:
        """Format generic structured data as user-friendly text.

        Args:
            data: Structured data

        Returns:
            User-friendly text representation
        """
        # Avoid dumping raw dicts to user
        # Extract key-value pairs in a readable format
        if not data:
            return ""

        items = []
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)):
                items.append(f"{key}: {value}")
            elif isinstance(value, dict):
                # Nested dict - skip for now
                continue
            elif isinstance(value, list):
                # List - skip for now
                continue
            else:
                # Complex type - skip
                continue

        if not items:
            return "Data retrieved."

        return ". ".join(items) + "."
