"""Tests for RuntimeContext."""

from datetime import datetime
from uuid import uuid4

import pytest

from domain.runtime.context import RuntimeContext, RuntimeContextError


def test_runtime_context_creation():
    """Test RuntimeContext creation with all fields."""
    tenant_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    session_id = str(uuid4())
    request_id = str(uuid4())
    trace_id = str(uuid4())

    ctx = RuntimeContext.create(
        tenant_id=tenant_id,
        account_id=account_id,
        session_id=session_id,
        request_id=request_id,
        trace_id=trace_id,
        user_id=user_id,
    )

    assert ctx.tenant_id == tenant_id
    assert ctx.account_id == account_id
    assert ctx.user_id == user_id
    assert ctx.session_id == session_id
    assert ctx.request_id == request_id
    assert ctx.trace_id == trace_id
    assert ctx.channel == "api"
    assert ctx.locale == "en"
    assert ctx.timezone == "UTC"
    assert ctx.environment == "production"
    assert isinstance(ctx.created_at, datetime)


def test_runtime_context_defaults():
    """Test RuntimeContext creation with defaults."""
    ctx = RuntimeContext.create(
        tenant_id=str(uuid4()),
        account_id=str(uuid4()),
        session_id=str(uuid4()),
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
    )

    assert ctx.channel == "api"
    assert ctx.locale == "en"
    assert ctx.timezone == "UTC"
    assert ctx.region == "default"
    assert ctx.cell == "default"
    assert ctx.environment == "production"
    assert ctx.permissions == frozenset()
    assert ctx.roles == frozenset()
    assert ctx.workflow_id is None
    assert ctx.task_id is None
    assert ctx.agent_id is None


def test_runtime_context_require_tenant_scope():
    """Test require_tenant_scope validates required fields."""
    ctx = RuntimeContext.create(
        tenant_id=str(uuid4()),
        account_id=str(uuid4()),
        session_id=str(uuid4()),
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
    )

    # Should not raise
    ctx.require_tenant_scope()


def test_runtime_context_require_tenant_scope_missing_tenant():
    """Test require_tenant_scope raises when tenant_id is missing."""
    ctx = RuntimeContext(
        tenant_id="",
        account_id=str(uuid4()),
        user_id=None,
        session_id=str(uuid4()),
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
        workflow_id=None,
        task_id=None,
        agent_id=None,
        device_id=None,
        channel="api",
        locale="en",
        timezone="UTC",
        permissions=frozenset(),
        roles=frozenset(),
        region="default",
        cell="default",
        environment="production",
        created_at=datetime.utcnow(),
        metadata={},
    )

    with pytest.raises(RuntimeContextError):
        ctx.require_tenant_scope()


def test_runtime_context_require_workflow_scope():
    """Test require_workflow_scope validates workflow_id."""
    ctx = RuntimeContext(
        tenant_id=str(uuid4()),
        account_id=str(uuid4()),
        user_id=None,
        session_id=str(uuid4()),
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
        workflow_id=None,
        task_id=None,
        agent_id=None,
        device_id=None,
        channel="api",
        locale="en",
        timezone="UTC",
        permissions=frozenset(),
        roles=frozenset(),
        region="default",
        cell="default",
        environment="production",
        created_at=datetime.utcnow(),
        metadata={},
    )

    with pytest.raises(RuntimeContextError):
        ctx.require_workflow_scope()


def test_runtime_context_require_agent_scope():
    """Test require_agent_scope validates agent_id."""
    ctx = RuntimeContext(
        tenant_id=str(uuid4()),
        account_id=str(uuid4()),
        user_id=None,
        session_id=str(uuid4()),
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
        workflow_id=str(uuid4()),
        task_id=str(uuid4()),
        agent_id=None,
        device_id=None,
        channel="api",
        locale="en",
        timezone="UTC",
        permissions=frozenset(),
        roles=frozenset(),
        region="default",
        cell="default",
        environment="production",
        created_at=datetime.utcnow(),
        metadata={},
    )

    with pytest.raises(RuntimeContextError):
        ctx.require_agent_scope()


def test_runtime_context_immutability():
    """Test RuntimeContext is frozen and immutable."""
    ctx = RuntimeContext.create(
        tenant_id=str(uuid4()),
        account_id=str(uuid4()),
        session_id=str(uuid4()),
        request_id=str(uuid4()),
        trace_id=str(uuid4()),
    )

    # Should raise AttributeError for assignment
    with pytest.raises(AttributeError):
        ctx.tenant_id = "new_tenant_id"
