"""
Concurrency, Circuit Breaker, Budget Guards, and Response Caching for Model Gateway.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is tripped due to consecutive failures."""
    pass


class BudgetExceededError(Exception):
    """Raised when the daily model spending budget has been exceeded."""
    pass


class ConcurrencyAndCostController:
    """
    Guards provider resources:
    - Restricts concurrent requests via Semaphore
    - Circuit breaker trips after failure threshold
    - Daily token budget guard
    - Deduplication cache by safe input hash
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        daily_budget_limit: float = 100.0,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.daily_budget_limit = daily_budget_limit

        self._consecutive_failures = 0
        self._state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._last_failure_time: float = 0.0

        self._cumulative_cost = 0.0
        self._response_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}  # hash -> (result_dict, timestamp)
        self._cache_ttl = 300.0  # 5 minutes

    @property
    def state(self) -> str:
        """Current circuit state, considering recovery timeout."""
        if self._state == "OPEN":
            if time.time() - self._last_failure_time > self.recovery_timeout_seconds:
                self._state = "HALF_OPEN"
        return self._state

    def check_can_execute(self) -> None:
        """Check circuit state and budget before sending a request."""
        st = self.state
        if st == "OPEN":
            raise CircuitBreakerOpen(
                f"Model provider circuit breaker is OPEN due to {self._consecutive_failures} consecutive failures. "
                f"Recovery attempt in {max(0, int(self.recovery_timeout_seconds - (time.time() - self._last_failure_time)))}s."
            )
        if self._cumulative_cost >= self.daily_budget_limit:
            raise BudgetExceededError(
                f"Daily model budget limit (${self.daily_budget_limit:.2f}) reached. Current cost: ${self._cumulative_cost:.2f}"
            )

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[None, None]:
        """Acquire concurrency semaphore while respecting circuit breaker and budget."""
        self.check_can_execute()
        async with self.semaphore:
            yield

    def record_cost(self, cost: float) -> None:
        """Add cost to cumulative daily spending."""
        self._cumulative_cost += float(cost)

    def record_success(self, cost: float = 0.0) -> None:
        """Record successful call, reset failures."""
        self._consecutive_failures = 0
        self._state = "CLOSED"
        self._cumulative_cost += cost

    def record_failure(self) -> None:
        """Record failed call; trip circuit if threshold reached."""
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        if self._consecutive_failures >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                f"Model provider circuit breaker TRIPPED to OPEN after {self._consecutive_failures} failures"
            )

    def get_cached(self, input_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached response if within TTL."""
        if input_hash in self._response_cache:
            data, timestamp = self._response_cache[input_hash]
            if time.time() - timestamp < self._cache_ttl:
                return data
            else:
                del self._response_cache[input_hash]
        return None

    def set_cached(self, input_hash: str, data: Dict[str, Any]) -> None:
        """Cache response data."""
        self._response_cache[input_hash] = (data, time.time())

    @staticmethod
    def compute_hash(task_id: str, payload: Any) -> str:
        """Compute stable hash for safe deduplication."""
        serialized = json.dumps({"task": task_id, "data": payload}, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_status(self) -> Dict[str, Any]:
        """Observability status."""
        return {
            "circuit_state": self.state,
            "consecutive_failures": self._consecutive_failures,
            "daily_budget_limit": self.daily_budget_limit,
            "daily_budget_used": round(self._cumulative_cost, 4),
            "cached_entries": len(self._response_cache),
        }


_global_controller: Optional[ConcurrencyAndCostController] = None


def get_controller() -> ConcurrencyAndCostController:
    """Retrieve or initialize the global ConcurrencyAndCostController instance."""
    global _global_controller
    if _global_controller is None:
        try:
            from cauveris.config import get_settings
            settings = get_settings()
            max_concurrent = getattr(settings, "nebius_max_concurrent_requests", 4)
            daily_budget = getattr(settings, "nebius_daily_budget_limit", 50.0)
        except Exception:
            max_concurrent = 4
            daily_budget = 50.0

        _global_controller = ConcurrencyAndCostController(
            max_concurrent=max_concurrent,
            failure_threshold=5,
            recovery_timeout_seconds=60.0,
            daily_budget_limit=daily_budget,
        )
    return _global_controller

