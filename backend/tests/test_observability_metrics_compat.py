from __future__ import annotations

from core.observability import ButlerMetrics


def test_inc_counter_compatibility_does_not_raise() -> None:
    ButlerMetrics.reset()
    metrics = ButlerMetrics.get()

    metrics.inc_counter("memory.consent.pii_redacted", tags={"tenant": "demo"})
    metrics.inc_counter("memory.consent.scrubbed_bytes", value=128)
    metrics.inc_counter("gateway.transport.rejected", tags={"reason": "auth_failure"})
