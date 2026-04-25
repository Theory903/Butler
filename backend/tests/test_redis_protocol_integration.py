"""Comprehensive tests for Redis protocol abstractions.

Tests cover:
- RedisCache implementation
- RedisLock implementation
- RedisRateLimit implementation
- RedisArtifact implementation
- RedisSandbox implementation
- RedisWorkflow implementation
- Protocol conformance
- Edge cases and error handling
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.redis_abstractions import (
    ArtifactAbstraction,
    CacheAbstraction,
    LockAbstraction,
    RateLimitAbstraction,
    RedisArtifact,
    RedisCache,
    RedisLock,
    RedisRateLimit,
    RedisSandbox,
    RedisWorkflow,
    SandboxAbstraction,
    SandboxStatus,
    WorkflowAbstraction,
    WorkflowStatus,
)


class TestRedisCache:
    """Test RedisCache implementation."""

    @pytest.mark.asyncio
    async def test_get_with_json_value(self):
        """Test getting JSON value from cache."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b'{"key": "value"}'

        cache = RedisCache(redis=mock_redis)
        result = await cache.get("ns", "key")

        assert result == {"key": "value"}
        mock_redis.get.assert_called_once_with("ns:key")

    @pytest.mark.asyncio
    async def test_get_with_string_value(self):
        """Test getting string value from cache."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"string_value"

        cache = RedisCache(redis=mock_redis)
        result = await cache.get("ns", "key")

        # JSON decode fails, returns raw bytes
        assert result == b"string_value"

    @pytest.mark.asyncio
    async def test_get_with_none(self):
        """Test getting non-existent key."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        cache = RedisCache(redis=mock_redis)
        result = await cache.get("ns", "key")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_string(self):
        """Test setting string value."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.set("ns", "key", "value", 60)

        mock_redis.setex.assert_called_once_with("ns:key", 60, "value")

    @pytest.mark.asyncio
    async def test_set_with_dict(self):
        """Test setting dict value (JSON serialized)."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.set("ns", "key", {"key": "value"}, 60)

        mock_redis.setex.assert_called_once_with("ns:key", 60, json.dumps({"key": "value"}))

    @pytest.mark.asyncio
    async def test_set_with_number(self):
        """Test setting numeric value."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.set("ns", "key", 42, 60)

        mock_redis.setex.assert_called_once_with("ns:key", 60, "42")

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting key."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.delete("ns", "key")

        mock_redis.delete.assert_called_once_with("ns:key")

    @pytest.mark.asyncio
    async def test_exists_true(self):
        """Test exists returns True."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1

        cache = RedisCache(redis=mock_redis)
        result = await cache.exists("ns", "key")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        """Test exists returns False."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        cache = RedisCache(redis=mock_redis)
        result = await cache.exists("ns", "key")

        assert result is False

    @pytest.mark.asyncio
    async def test_protocol_conformance(self):
        """Test RedisCache conforms to CacheAbstraction protocol."""
        mock_redis = AsyncMock()
        cache = RedisCache(redis=mock_redis)

        assert isinstance(cache, CacheAbstraction)


class TestRedisLock:
    """Test RedisLock implementation."""

    @pytest.mark.asyncio
    async def test_acquire_success(self):
        """Test successful lock acquisition."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        lock = RedisLock(redis=mock_redis)
        result = await lock.acquire("ns", "lock_name", 60)

        assert result is True
        mock_redis.set.assert_called_once_with("ns:lock:lock_name", "1", nx=True, ex=60)

    @pytest.mark.asyncio
    async def test_acquire_failure(self):
        """Test failed lock acquisition (already locked)."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = False

        lock = RedisLock(redis=mock_redis)
        result = await lock.acquire("ns", "lock_name", 60)

        assert result is False

    @pytest.mark.asyncio
    async def test_release(self):
        """Test releasing lock."""
        mock_redis = AsyncMock()

        lock = RedisLock(redis=mock_redis)
        await lock.release("ns", "lock_name")

        mock_redis.delete.assert_called_once_with("ns:lock:lock_name")

    @pytest.mark.asyncio
    async def test_is_locked_true(self):
        """Test is_locked returns True."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1

        lock = RedisLock(redis=mock_redis)
        result = await lock.is_locked("ns", "lock_name")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_locked_false(self):
        """Test is_locked returns False."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        lock = RedisLock(redis=mock_redis)
        result = await lock.is_locked("ns", "lock_name")

        assert result is False

    @pytest.mark.asyncio
    async def test_protocol_conformance(self):
        """Test RedisLock conforms to LockAbstraction protocol."""
        mock_redis = AsyncMock()
        lock = RedisLock(redis=mock_redis)

        assert isinstance(lock, LockAbstraction)


class TestRedisRateLimit:
    """Test RedisRateLimit implementation."""

    @pytest.mark.asyncio
    async def test_check_within_limit(self):
        """Test check returns True when within limit."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True

        rate_limit = RedisRateLimit(redis=mock_redis)
        result = await rate_limit.check("ns", "limit_id", 10, 60)

        assert result is True
        mock_redis.incr.assert_called_once_with("ns:rate_limit:limit_id")
        mock_redis.expire.assert_called_once_with("ns:rate_limit:limit_id", 60)

    @pytest.mark.asyncio
    async def test_check_exceeds_limit(self):
        """Test check returns False when limit exceeded."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 11

        rate_limit = RedisRateLimit(redis=mock_redis)
        result = await rate_limit.check("ns", "limit_id", 10, 60)

        assert result is False

    @pytest.mark.asyncio
    async def test_increment(self):
        """Test increment counter."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 5

        rate_limit = RedisRateLimit(redis=mock_redis)
        result = await rate_limit.increment("ns", "limit_id")

        assert result == 5
        mock_redis.incr.assert_called_once_with("ns:rate_limit:limit_id")

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test reset counter."""
        mock_redis = AsyncMock()

        rate_limit = RedisRateLimit(redis=mock_redis)
        await rate_limit.reset("ns", "limit_id")

        mock_redis.delete.assert_called_once_with("ns:rate_limit:limit_id")

    @pytest.mark.asyncio
    async def test_protocol_conformance(self):
        """Test RedisRateLimit conforms to RateLimitAbstraction protocol."""
        mock_redis = AsyncMock()
        rate_limit = RedisRateLimit(redis=mock_redis)

        assert isinstance(rate_limit, RateLimitAbstraction)


class TestRedisArtifact:
    """Test RedisArtifact implementation."""

    @pytest.mark.asyncio
    async def test_store(self):
        """Test storing artifact."""
        mock_redis = AsyncMock()

        artifact = RedisArtifact(redis=mock_redis)
        data = b"artifact_data"
        await artifact.store("ns", "artifact_id", data, 60)

        mock_redis.setex.assert_called_once_with("ns:artifact:artifact_id", 60, data)

    @pytest.mark.asyncio
    async def test_retrieve_success(self):
        """Test retrieving existing artifact."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"artifact_data"

        artifact = RedisArtifact(redis=mock_redis)
        result = await artifact.retrieve("ns", "artifact_id")

        assert result == b"artifact_data"
        mock_redis.get.assert_called_once_with("ns:artifact:artifact_id")

    @pytest.mark.asyncio
    async def test_retrieve_not_found(self):
        """Test retrieving non-existent artifact."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        artifact = RedisArtifact(redis=mock_redis)
        result = await artifact.retrieve("ns", "artifact_id")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting artifact."""
        mock_redis = AsyncMock()

        artifact = RedisArtifact(redis=mock_redis)
        await artifact.delete("ns", "artifact_id")

        mock_redis.delete.assert_called_once_with("ns:artifact:artifact_id")

    @pytest.mark.asyncio
    async def test_list(self):
        """Test listing artifacts."""
        mock_redis = AsyncMock()
        # scan_iter returns an async iterator
        async def mock_scan_iter(**kwargs):
            for key in [b"ns:artifact:artifact1", b"ns:artifact:artifact2"]:
                yield key
        mock_redis.scan_iter = mock_scan_iter

        artifact = RedisArtifact(redis=mock_redis)
        result = await artifact.list("ns")

        assert result == ["artifact1", "artifact2"]

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """Test listing artifacts when empty."""
        mock_redis = AsyncMock()
        async def mock_scan_iter(**kwargs):
            return
            yield  # Never reached
        mock_redis.scan_iter = mock_scan_iter

        artifact = RedisArtifact(redis=mock_redis)
        result = await artifact.list("ns")

        assert result == []

    @pytest.mark.asyncio
    async def test_protocol_conformance(self):
        """Test RedisArtifact conforms to ArtifactAbstraction protocol."""
        mock_redis = AsyncMock()
        artifact = RedisArtifact(redis=mock_redis)

        assert isinstance(artifact, ArtifactAbstraction)


class TestRedisSandbox:
    """Test RedisSandbox implementation."""

    @pytest.mark.asyncio
    async def test_create(self):
        """Test creating sandbox."""
        mock_redis = AsyncMock()

        sandbox = RedisSandbox(redis=mock_redis)
        config = {"image": "python:3.9"}
        result = await sandbox.create("ns", "sandbox_id", config)

        assert result == "sandbox_id"
        assert mock_redis.set.call_count == 2

    @pytest.mark.asyncio
    async def test_destroy(self):
        """Test destroying sandbox."""
        mock_redis = AsyncMock()

        sandbox = RedisSandbox(redis=mock_redis)
        await sandbox.destroy("ns", "sandbox_id")

        assert mock_redis.set.call_count == 1
        mock_redis.delete.assert_called_once_with("ns:sandbox:sandbox_id:config")

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting sandbox status."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"running"

        sandbox = RedisSandbox(redis=mock_redis)
        result = await sandbox.get_status("ns", "sandbox_id")

        assert result == SandboxStatus.RUNNING
        mock_redis.get.assert_called_once_with("ns:sandbox:sandbox_id:status")

    @pytest.mark.asyncio
    async def test_get_status_not_found(self):
        """Test getting status for non-existent sandbox."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        sandbox = RedisSandbox(redis=mock_redis)
        result = await sandbox.get_status("ns", "sandbox_id")

        assert result == SandboxStatus.FAILED

    @pytest.mark.asyncio
    async def test_protocol_conformance(self):
        """Test RedisSandbox conforms to SandboxAbstraction protocol."""
        mock_redis = AsyncMock()
        sandbox = RedisSandbox(redis=mock_redis)

        assert isinstance(sandbox, SandboxAbstraction)


class TestRedisWorkflow:
    """Test RedisWorkflow implementation."""

    @pytest.mark.asyncio
    async def test_start(self):
        """Test starting workflow."""
        mock_redis = AsyncMock()

        workflow = RedisWorkflow(redis=mock_redis)
        input_data = {"param": "value"}
        result = await workflow.start("ns", "workflow_id", input_data)

        assert result.startswith("exec_workflow_id_")
        assert mock_redis.set.call_count == 2

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting workflow status."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"running"

        workflow = RedisWorkflow(redis=mock_redis)
        result = await workflow.get_status("ns", "execution_id")

        assert result == WorkflowStatus.RUNNING
        mock_redis.get.assert_called_once_with("ns:workflow:execution_id:status")

    @pytest.mark.asyncio
    async def test_get_status_not_found(self):
        """Test getting status for non-existent workflow."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        workflow = RedisWorkflow(redis=mock_redis)
        result = await workflow.get_status("ns", "execution_id")

        assert result == WorkflowStatus.FAILED

    @pytest.mark.asyncio
    async def test_cancel(self):
        """Test canceling workflow."""
        mock_redis = AsyncMock()

        workflow = RedisWorkflow(redis=mock_redis)
        await workflow.cancel("ns", "execution_id")

        mock_redis.set.assert_called_once_with("ns:workflow:execution_id:status", "cancelled")

    @pytest.mark.asyncio
    async def test_protocol_conformance(self):
        """Test RedisWorkflow conforms to WorkflowAbstraction protocol."""
        mock_redis = AsyncMock()
        workflow = RedisWorkflow(redis=mock_redis)

        assert isinstance(workflow, WorkflowAbstraction)


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_cache_get_invalid_json(self):
        """Test cache get with invalid JSON returns raw value."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"not_valid_json"

        cache = RedisCache(redis=mock_redis)
        result = await cache.get("ns", "key")

        assert result == b"not_valid_json"

    @pytest.mark.asyncio
    async def test_cache_get_bytes_value(self):
        """Test cache get with bytes value."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"bytes_value"

        cache = RedisCache(redis=mock_redis)
        result = await cache.get("ns", "key")

        assert result == b"bytes_value"

    @pytest.mark.asyncio
    async def test_artifact_list_string_keys(self):
        """Test artifact list with string keys from Redis."""
        mock_redis = AsyncMock()
        async def mock_scan_iter(**kwargs):
            for key in ["ns:artifact:artifact1", "ns:artifact:artifact2"]:
                yield key
        mock_redis.scan_iter = mock_scan_iter

        artifact = RedisArtifact(redis=mock_redis)
        result = await artifact.list("ns")

        assert result == ["artifact1", "artifact2"]

    @pytest.mark.asyncio
    async def test_sandbox_status_string_value(self):
        """Test sandbox status with string value from Redis."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "running"

        sandbox = RedisSandbox(redis=mock_redis)
        result = await sandbox.get_status("ns", "sandbox_id")

        assert result == SandboxStatus.RUNNING

    @pytest.mark.asyncio
    async def test_workflow_status_string_value(self):
        """Test workflow status with string value from Redis."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "completed"

        workflow = RedisWorkflow(redis=mock_redis)
        result = await workflow.get_status("ns", "execution_id")

        assert result == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cache_set_with_bool_true(self):
        """Test cache set with boolean true."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.set("ns", "key", True, 60)

        mock_redis.setex.assert_called_once_with("ns:key", 60, "True")

    @pytest.mark.asyncio
    async def test_cache_set_with_bool_false(self):
        """Test cache set with boolean false."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.set("ns", "key", False, 60)

        mock_redis.setex.assert_called_once_with("ns:key", 60, "False")

    @pytest.mark.asyncio
    async def test_cache_set_with_float(self):
        """Test cache set with float value."""
        mock_redis = AsyncMock()

        cache = RedisCache(redis=mock_redis)
        await cache.set("ns", "key", 3.14, 60)

        mock_redis.setex.assert_called_once_with("ns:key", 60, "3.14")


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_cache_lifecycle(self):
        """Test full cache lifecycle: set, get, exists, delete."""
        mock_redis = AsyncMock()
        mock_redis.setex.return_value = True
        mock_redis.get.return_value = b'{"key": "value"}'
        mock_redis.exists.return_value = 1

        cache = RedisCache(redis=mock_redis)

        await cache.set("ns", "key", {"key": "value"}, 60)
        result = await cache.get("ns", "key")
        exists = await cache.exists("ns", "key")
        await cache.delete("ns", "key")

        assert result == {"key": "value"}
        assert exists is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_lock_lifecycle(self):
        """Test full lock lifecycle: acquire, is_locked, release."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        mock_redis.exists.return_value = 1

        lock = RedisLock(redis=mock_redis)

        acquired = await lock.acquire("ns", "lock_name", 60)
        is_locked = await lock.is_locked("ns", "lock_name")
        await lock.release("ns", "lock_name")

        assert acquired is True
        assert is_locked is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_rate_limit_lifecycle(self):
        """Test full rate limit lifecycle: check, increment, reset."""
        mock_redis = AsyncMock()
        # Make incr return 1, then 2 on successive calls
        mock_redis.incr.side_effect = [1, 2]
        mock_redis.expire.return_value = True

        rate_limit = RedisRateLimit(redis=mock_redis)

        allowed = await rate_limit.check("ns", "limit_id", 10, 60)
        count = await rate_limit.increment("ns", "limit_id")
        await rate_limit.reset("ns", "limit_id")

        assert allowed is True
        # check calls incr once (returns 1), increment calls incr again (returns 2)
        assert count == 2
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_artifact_lifecycle(self):
        """Test full artifact lifecycle: store, retrieve, list, delete."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"artifact_data"
        async def mock_scan_iter(**kwargs):
            for key in [b"ns:artifact:artifact_id"]:
                yield key
        mock_redis.scan_iter = mock_scan_iter

        artifact = RedisArtifact(redis=mock_redis)

        await artifact.store("ns", "artifact_id", b"artifact_data", 60)
        retrieved = await artifact.retrieve("ns", "artifact_id")
        artifacts = await artifact.list("ns")
        await artifact.delete("ns", "artifact_id")

        assert retrieved == b"artifact_data"
        assert artifacts == ["artifact_id"]
        mock_redis.delete.assert_called_once()
