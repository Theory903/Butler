from __future__ import annotations

import time
from collections import deque
from threading import Lock


class RetryBudget:
    """
    Finagle-style Retry Budget.

    Ensures that we don't spam a failing service by limiting retries
    to a fixed percentage of total requests.

    Logic:
    - Track counts of 'deposits' (successful requests) and 'withdrawals' (retries).
    - Allow retry only if withdrawals < (deposits * ratio) + minimum_budget.
    """

    def __init__(
        self,
        ratio: float = 0.1,  # 10% retry allowance
        min_retries_per_sec: int = 5,
        window_seconds: int = 10,
    ):
        self._ratio = ratio
        self._min_retries_per_sec = min_retries_per_sec
        self._window_seconds = window_seconds

        # Deque of (timestamp, is_retry)
        self._history: deque[tuple[float, bool]] = deque()
        self._lock = Lock()

        # Current window counters
        self._deposits = 0
        self._withdrawals = 0

    def deposit(self):
        """Record a successful (non-retry) request."""
        self._record(is_retry=False)

    def withdraw(self) -> bool:
        """Attempt to record a retry. Returns True if within budget."""
        with self._lock:
            self._prune()

            # Withdrawal logic: allow if under the ratio OR under minimum floor
            allowed_by_ratio = self._withdrawals < (self._deposits * self._ratio)
            allowed_by_floor = self._withdrawals < (
                self._min_retries_per_sec * self._window_seconds
            )

            if allowed_by_ratio or allowed_by_floor:
                self._record(is_retry=True, lock_acquired=True)
                return True

            return False

    def _record(self, is_retry: bool, lock_acquired: bool = False):
        now = time.monotonic()

        def _exec():
            self._history.append((now, is_retry))
            if is_retry:
                self._withdrawals += 1
            else:
                self._deposits += 1
            self._prune()

        if lock_acquired:
            _exec()
        else:
            with self._lock:
                _exec()

    def _prune(self):
        """Remove entries outside the sliding window. Must be called under lock."""
        now = time.monotonic()
        cutoff = now - self._window_seconds

        while self._history and self._history[0][0] < cutoff:
            _, was_retry = self._history.popleft()
            if was_retry:
                self._withdrawals -= 1
            else:
                self._deposits -= 1

    @property
    def stats(self) -> dict:
        with self._lock:
            self._prune()
            return {
                "deposits": self._deposits,
                "withdrawals": self._withdrawals,
                "ratio": self._ratio,
                "window": self._window_seconds,
            }
