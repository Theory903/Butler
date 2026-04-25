"""Tests for ResponseValidator."""

import pytest

from domain.runtime.response_validator import ResponseValidator, ResponseValidationError


def test_validate_user_facing_response_safe():
    """Test validation passes for safe response."""
    safe_response = "This is a safe response with no internal details."
    ResponseValidator.validate_user_facing_response(safe_response)


def test_validate_user_facing_response_python_dict():
    """Test validation rejects Python dict repr."""
    unsafe_response = "Here is the data: {'key': 'value', 'nested': {'inner': 'data'}}"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Python dict repr" in str(exc_info.value)


def test_validate_user_facing_response_langchain_tool_message():
    """Test validation rejects LangChain ToolMessage."""
    unsafe_response = "ToolMessage(content='test', name='tool')"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "LangChain ToolMessage" in str(exc_info.value)


def test_validate_user_facing_response_langchain_ai_message():
    """Test validation rejects LangChain AIMessage."""
    unsafe_response = "AIMessage(content='test')"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "LangChain AIMessage" in str(exc_info.value)


def test_validate_user_facing_response_langchain_human_message():
    """Test validation rejects LangChain HumanMessage."""
    unsafe_response = "HumanMessage(content='test')"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "LangChain HumanMessage" in str(exc_info.value)


def test_validate_user_facing_response_stack_trace():
    """Test validation rejects stack traces."""
    unsafe_response = "Traceback (most recent call last):\n  File \"test.py\", line 1"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Stack trace" in str(exc_info.value)


def test_validate_user_facing_response_internal_workflow_id():
    """Test validation rejects internal workflow_id."""
    unsafe_response = "workflow_id: 550e8400-e29b-41d4-a716-446655440000"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Internal workflow_id" in str(exc_info.value)


def test_validate_user_facing_response_internal_request_id():
    """Test validation rejects internal request_id."""
    unsafe_response = "request_id: 550e8400-e29b-41d4-a716-446655440000"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Internal request_id" in str(exc_info.value)


def test_validate_user_facing_response_provider_openai():
    """Test validation rejects provider leaks: openai."""
    unsafe_response = "Using openai model gpt-4"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Provider leak: openai" in str(exc_info.value)


def test_validate_user_facing_response_provider_anthropic():
    """Test validation rejects provider leaks: anthropic."""
    unsafe_response = "Using anthropic claude model"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Provider leak: anthropic" in str(exc_info.value)


def test_validate_user_facing_response_secret_sk():
    """Test validation rejects secret patterns: sk-."""
    unsafe_response = "API key: sk-proj-abc123xyz789"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Secret pattern: sk-" in str(exc_info.value)


def test_validate_user_facing_response_secret_bearer():
    """Test validation rejects secret patterns: Bearer."""
    unsafe_response = "Authorization: Bearer eyJhbGciOiJIUzI1NiIs"
    with pytest.raises(ResponseValidationError) as exc_info:
        ResponseValidator.validate_user_facing_response(unsafe_response)
    assert "Secret pattern: Bearer" in str(exc_info.value)


def test_validate_internal_response_allows_ids():
    """Test internal validation allows internal IDs."""
    response = "workflow_id: 550e8400-e29b-41d4-a716-446655440000"
    ResponseValidator.validate_internal_response(response)


def test_validate_internal_response_rejects_secrets():
    """Test internal validation still rejects secrets."""
    unsafe_response = "API key: sk-proj-abc123xyz789"
    with pytest.raises(ResponseValidationError):
        ResponseValidator.validate_internal_response(unsafe_response)


def test_sanitize_user_facing_response_dict():
    """Test sanitization removes Python dict repr."""
    unsafe_response = "Data: {'key': 'value'}"
    sanitized = ResponseValidator.sanitize_user_facing_response(unsafe_response)
    assert "[structured data]" in sanitized
    assert "{'key': 'value'}" not in sanitized


def test_sanitize_user_facing_response_provider():
    """Test sanitization removes provider names."""
    unsafe_response = "Using openai model"
    sanitized = ResponseValidator.sanitize_user_facing_response(unsafe_response)
    assert "[provider]" in sanitized
    assert "openai" not in sanitized.lower()


def test_sanitize_user_facing_response_secret():
    """Test sanitization removes secrets."""
    unsafe_response = "Key: sk-proj-abc123xyz789"
    sanitized = ResponseValidator.sanitize_user_facing_response(unsafe_response)
    assert "[secret removed]" in sanitized
    assert "sk-" not in sanitized


def test_sanitize_user_facing_response_safe():
    """Test sanitization leaves safe response unchanged."""
    safe_response = "This is a safe response."
    sanitized = ResponseValidator.sanitize_user_facing_response(safe_response)
    assert sanitized == safe_response


def test_sanitize_user_facing_response_stack_trace():
    """Test sanitization removes stack traces."""
    unsafe_response = "Error: Traceback (most recent call last):\n  File \"test.py\", line 1\nError"
    sanitized = ResponseValidator.sanitize_user_facing_response(unsafe_response)
    assert "[system error details removed]" in sanitized
    assert "Traceback" not in sanitized
