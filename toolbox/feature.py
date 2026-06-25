"""Tool feature — register sandboxed fs + terminal tools, each behind the safety chokepoint. Epic E06."""
from __future__ import annotations

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor
from safety.policy import SafeToolPort, ToolPolicy
from toolbox.filesystem import FsList, FsRead, FsWrite
from toolbox.terminal import Terminal

FEATURE = FeatureDescriptor(
    name="toolbox",
    capabilities=("fs_read", "fs_write", "fs_list", "terminal_run"),
    description="Workspace-sandboxed filesystem + terminal tools, gated by the safety chokepoint.",
)


# Retry/risk semantics per tool: reads are idempotent + low risk; effects must not be
# retried (non-idempotent) and carry the blast-radius risk the policy/retry layers key on.
_DESCRIPTORS = {
    "fs_read": {"kind": "read", "idempotent": True, "risk": "low"},
    "fs_list": {"kind": "read", "idempotent": True, "risk": "low"},
    "fs_write": {"kind": "effect", "idempotent": False, "risk": "medium"},
    "terminal_run": {"kind": "effect", "idempotent": False, "risk": "high"},
}


def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    policy = ToolPolicy()
    for tool in (FsRead(), FsWrite(), FsList(), Terminal()):
        kernel.registry.register_tool(
            tool.name,
            SafeToolPort(tool.name, tool, policy),
            feature_name=FEATURE.name,
            **_DESCRIPTORS[tool.name],
        )
