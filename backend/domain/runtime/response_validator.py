"""ResponseValidator - validates user-facing responses for unsafe patterns."""

from __future__ import annotations

import re
from re import Pattern

from .errors import ResponseValidationError


class ResponseValidator:
    """Validates user-facing responses for unsafe patterns.

    Rejects these patterns:
    - Python dict repr: {'key': 'value'}
    - LangChain internals: ToolMessage, AIMessage, HumanMessage
    - Stack traces: Traceback (most recent call last)
    - Internal IDs: workflow_id, request_id, approval_id, tool_execution_id, session_id
    - Provider leaks: openai, anthropic, groq, ollama, vllm
    - Secret patterns: sk-, Bearer, API_KEY, JWT

    Important nuance:
    Internal IDs may be returned only if the API endpoint is explicitly internal/admin/debug.
    User-facing chat responses must hide them.
    """

    # Patterns to reject in user-facing responses
    PATTERNS: list[tuple[str, Pattern[str]]] = [
        (
            "Python dict repr",
            re.compile(r"\{[^}]*'[^']*':\s*[^}]*\}"),
        ),
        (
            "LangChain ToolMessage",
            re.compile(r"ToolMessage", re.IGNORECASE),
        ),
        (
            "LangChain AIMessage",
            re.compile(r"AIMessage", re.IGNORECASE),
        ),
        (
            "LangChain HumanMessage",
            re.compile(r"HumanMessage", re.IGNORECASE),
        ),
        (
            "Stack trace",
            re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
        ),
        (
            "Internal workflow_id",
            re.compile(r"workflow_id[:\s]*[a-f0-9-]{36}", re.IGNORECASE),
        ),
        (
            "Internal request_id",
            re.compile(r"request_id[:\s]*[a-f0-9-]{36}", re.IGNORECASE),
        ),
        (
            "Internal approval_id",
            re.compile(r"approval_id[:\s]*[a-f0-9-]{36}", re.IGNORECASE),
        ),
        (
            "Internal tool_execution_id",
            re.compile(r"tool_execution_id[:\s]*[a-f0-9-]{36}", re.IGNORECASE),
        ),
        (
            "Internal session_id",
            re.compile(r"session_id[:\s]*[a-f0-9-]{36}", re.IGNORECASE),
        ),
        (
            "Provider leak: openai",
            re.compile(r"openai", re.IGNORECASE),
        ),
        (
            "Provider leak: anthropic",
            re.compile(r"anthropic", re.IGNORECASE),
        ),
        (
            "Provider leak: groq",
            re.compile(r"\bgroq\b", re.IGNORECASE),
        ),
        (
            "Provider leak: ollama",
            re.compile(r"ollama", re.IGNORECASE),
        ),
        (
            "Provider leak: vllm",
            re.compile(r"vllm", re.IGNORECASE),
        ),
        (
            "Secret pattern: sk-",
            re.compile(r"sk-[a-zA-Z0-9]{20,}"),
        ),
        (
            "Secret pattern: Bearer",
            re.compile(r"Bearer\s+[a-zA-Z0-9_-]+"),
        ),
        (
            "Secret pattern: API_KEY",
            re.compile(r"API_KEY\s*[:=]\s*[a-zA-Z0-9_-]+", re.IGNORECASE),
        ),
        (
            "Secret pattern: JWT",
            re.compile(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"),
        ),
    ]

    @classmethod
    def validate_user_facing_response(cls, response: str) -> None:
        """Validate a user-facing response for unsafe patterns.

        Args:
            response: The response text to validate

        Raises:
            ResponseValidationError: If unsafe patterns are detected
        """
        for pattern_name, pattern in cls.PATTERNS:
            if pattern.search(response):
                raise ResponseValidationError(
                    f"Unsafe pattern detected in user-facing response: {pattern_name}"
                )

    @classmethod
    def validate_internal_response(cls, response: str) -> None:
        """Validate an internal/admin/debug response.

        Internal responses may include internal IDs but still must not include
        secrets or stack traces.

        Args:
            response: The response text to validate

        Raises:
            ResponseValidationError: If unsafe patterns are detected
        """
        # Allow internal IDs but still reject secrets and stack traces
        restricted_patterns = [
            ("Python dict repr", cls.PATTERNS[0][1]),
            ("LangChain ToolMessage", cls.PATTERNS[1][1]),
            ("LangChain AIMessage", cls.PATTERNS[2][1]),
            ("LangChain HumanMessage", cls.PATTERNS[3][1]),
            ("Stack trace", cls.PATTERNS[4][1]),
            ("Secret pattern: sk-", cls.PATTERNS[10][1]),
            ("Secret pattern: Bearer", cls.PATTERNS[11][1]),
            ("Secret pattern: API_KEY", cls.PATTERNS[12][1]),
            ("Secret pattern: JWT", cls.PATTERNS[13][1]),
        ]

        for pattern_name, pattern in restricted_patterns:
            if pattern.search(response):
                raise ResponseValidationError(
                    f"Unsafe pattern detected in internal response: {pattern_name}"
                )

    @classmethod
    def sanitize_user_facing_response(cls, response: str) -> str:
        """Sanitize a user-facing response by removing unsafe patterns.

        Args:
            response: The response text to sanitize

        Returns:
            Sanitized response with unsafe patterns removed or replaced
        """
        sanitized = response

        # Replace Python dict repr with placeholder
        sanitized = re.sub(r"\{[^}]*'[^']*':\s*[^}]*\}", "[structured data]", sanitized)

        # Remove LangChain message types
        sanitized = re.sub(r"ToolMessage", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"AIMessage", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"HumanMessage", "", sanitized, flags=re.IGNORECASE)

        # Remove stack traces
        sanitized = re.sub(
            r"Traceback \(most recent call last\).*?(?=\n\n|\Z)",
            "[system error details removed]",
            sanitized,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove internal IDs
        sanitized = re.sub(
            r"(workflow_id|request_id|approval_id|tool_execution_id|session_id)[:\s]*[a-f0-9-]{36}",
            "[internal ID removed]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Remove provider names
        sanitized = re.sub(r"openai", "[provider]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"anthropic", "[provider]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bgroq\b", "[provider]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"ollama", "[provider]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"vllm", "[provider]", sanitized, flags=re.IGNORECASE)

        # Remove secrets
        sanitized = re.sub(r"sk-[a-zA-Z0-9]{20,}", "[secret removed]", sanitized)
        sanitized = re.sub(r"Bearer\s+[a-zA-Z0-9_-]+", "[secret removed]", sanitized)
        sanitized = re.sub(
            r"API_KEY\s*[:=]\s*[a-zA-Z0-9_-]+",
            "[secret removed]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",
            "[secret removed]",
            sanitized,
        )

        return sanitized
