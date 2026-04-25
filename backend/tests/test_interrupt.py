from datetime import UTC, datetime, timedelta

from services.orchestrator.resume import check_approval_expired


def test_approval_not_expired():
    now = datetime.now(UTC)
    assert check_approval_expired(now) is False


def test_approval_expired():
    old = datetime.now(UTC) - timedelta(minutes=31)
    assert check_approval_expired(old) is True
