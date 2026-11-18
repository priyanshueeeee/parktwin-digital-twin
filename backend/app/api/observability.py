"""Privacy-safe structured logging, operational metrics, rate limiting, and payload guards."""

from __future__ import annotations

from collections import defaultdict, deque
import json
import logging
import threading
import time
from typing import Any


logger = logging.getLogger("parktwin.api")


def log_safe_event(
    *,
    event: str,
    request_id: str,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    latency_ms: float | None = None,
    actor_id: str | None = None,
    error_code: str | None = None,
) -> None:
    """Emit a structured JSON log line strictly free of raw speech features or PII."""
    payload: dict[str, Any] = {
        "event": event,
        "request_id": request_id,
    }
    if method is not None:
        payload["method"] = method
    if path is not None:
        payload["path"] = path
    if status_code is not None:
        payload["status_code"] = status_code
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 3)
    if actor_id is not None:
        payload["actor_id"] = actor_id
    if error_code is not None:
        payload["error_code"] = error_code
    logger.info(json.dumps(payload, sort_keys=True))


class MetricsRegistry:
    """Thread-safe in-memory operational metrics matching ARCHITECTURE.md Section 9."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._requests_total: dict[str, int] = defaultdict(int)
            self._endpoint_latencies_ms: dict[str, list[float]] = defaultdict(list)
            self._validation_failures: dict[str, int] = defaultdict(int)
            self._stage_latencies_ms: dict[str, list[float]] = {
                "inference": [],
                "trajectory": [],
                "simulation": [],
            }
            self._model_load_failures = 0
            self._insufficient_data_states = 0
            self._quality_warnings = 0

    def record_request(self, endpoint: str, status_code: int, latency_ms: float) -> None:
        with self._lock:
            key = f"{endpoint}:{status_code}"
            self._requests_total[key] += 1
            samples = self._endpoint_latencies_ms[endpoint]
            samples.append(latency_ms)
            if len(samples) > 1000:
                del samples[:-1000]

    def record_validation_failure(self, code: str) -> None:
        with self._lock:
            self._validation_failures[code] += 1

    def record_stage_latency(self, stage: str, latency_ms: float) -> None:
        with self._lock:
            samples = self._stage_latencies_ms.setdefault(stage, [])
            samples.append(latency_ms)
            if len(samples) > 1000:
                del samples[:-1000]

    def record_model_load_failure(self) -> None:
        with self._lock:
            self._model_load_failures += 1

    def record_insufficient_data(self) -> None:
        with self._lock:
            self._insufficient_data_states += 1

    def record_quality_warnings(self, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            self._quality_warnings += count

    @staticmethod
    def _summarize(values: list[float]) -> dict[str, float | int]:
        if not values:
            return {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
        ordered = sorted(values)
        p95_idx = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
        return {
            "count": len(ordered),
            "avg_ms": round(sum(ordered) / len(ordered), 3),
            "p95_ms": round(ordered[p95_idx], 3),
            "max_ms": round(ordered[-1], 3),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests_by_endpoint_status": dict(self._requests_total),
                "endpoint_latency_ms": {
                    ep: self._summarize(vals) for ep, vals in self._endpoint_latencies_ms.items()
                },
                "stage_latency_ms": {
                    stage: self._summarize(vals)
                    for stage, vals in self._stage_latencies_ms.items()
                },
                "validation_failures": dict(self._validation_failures),
                "model_load_failures": self._model_load_failures,
                "insufficient_data_states": self._insufficient_data_states,
                "data_quality_warnings_total": self._quality_warnings,
            }


class SlidingWindowRateLimiter:
    """Lightweight in-memory per-client sliding-window rate limiter for prototype API protection."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, client_key: str) -> bool:
        if self.max_requests <= 0:
            return True
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets[client_key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True
