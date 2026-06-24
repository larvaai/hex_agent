"""Thread-safe delegation store with ordered, idempotent progress writes."""
from __future__ import annotations

import threading

from core.schemas import DelegationProgress, DelegationRequest, DelegationResult


class InMemoryDelegationStore:
    """Deterministic v1 store; a durable adapter can implement the same port later."""

    def __init__(self) -> None:
        self._requests: dict[str, DelegationRequest] = {}
        self._progress: dict[str, list[DelegationProgress]] = {}
        self._results: dict[str, DelegationResult] = {}
        self._lock = threading.RLock()

    def start(self, request: DelegationRequest) -> None:
        with self._lock:
            if request.delegation_id in self._requests:
                raise ValueError(f"Delegation already exists: {request.delegation_id}")
            self._requests[request.delegation_id] = request
            self._progress[request.delegation_id] = []

    def append_progress(self, progress: DelegationProgress) -> None:
        with self._lock:
            items = self._progress.get(progress.delegation_id)
            if items is None:
                raise LookupError(f"Unknown delegation: {progress.delegation_id}")
            if any(item.event_id == progress.event_id for item in items):
                return
            expected = len(items) + 1
            if progress.sequence != expected:
                raise ValueError(
                    f"Progress sequence must be {expected} for {progress.delegation_id}, "
                    f"got {progress.sequence}."
                )
            items.append(progress)

    def finish(self, result: DelegationResult) -> None:
        with self._lock:
            if result.delegation_id not in self._requests:
                raise LookupError(f"Unknown delegation: {result.delegation_id}")
            existing = self._results.get(result.delegation_id)
            if existing is not None and existing != result:
                raise ValueError(f"Delegation already has a different result: {result.delegation_id}")
            self._results[result.delegation_id] = result

    def progress(self, delegation_id: str) -> tuple[DelegationProgress, ...]:
        with self._lock:
            return tuple(self._progress.get(delegation_id, ()))

    def result(self, delegation_id: str) -> DelegationResult | None:
        with self._lock:
            return self._results.get(delegation_id)
