"""ToolPort protocol — the seam every concrete tool implements. Epic E01."""
from __future__ import annotations

from typing import Any, Callable, Protocol, TYPE_CHECKING, runtime_checkable

from core.schemas import (
    DelegationPolicy,
    DelegationProgress,
    DelegationRequest,
    DelegationResult,
    DelegationSpec,
    ToolRequest,
)

if TYPE_CHECKING:
    from core.session import KernelSession


@runtime_checkable
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port."""

    name: str

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...


ProgressSink = Callable[[DelegationProgress], None]


@runtime_checkable
class DelegationPort(Protocol):
    name: str

    def can_handle(self, target: str) -> bool:
        ...

    def run(
        self,
        request: DelegationRequest,
        child_session: "KernelSession",
        progress_sink: ProgressSink,
    ) -> DelegationResult:
        ...


class DelegationStorePort(Protocol):
    def start(self, request: DelegationRequest) -> None:
        ...

    def append_progress(self, progress: DelegationProgress) -> None:
        ...

    def finish(self, result: DelegationResult) -> None:
        ...

    def progress(self, delegation_id: str) -> tuple[DelegationProgress, ...]:
        ...

    def result(self, delegation_id: str) -> DelegationResult | None:
        ...


class DelegationServicePort(Protocol):
    def available_targets(self) -> tuple[str, ...]:
        ...

    def delegate(
        self,
        parent_session: "KernelSession",
        target: str,
        spec: DelegationSpec,
        policy: DelegationPolicy | None = None,
    ) -> DelegationResult:
        ...
