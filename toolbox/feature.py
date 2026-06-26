"""Tool feature — register sandboxed fs + terminal + code-intelligence tools, each behind the safety chokepoint. Epic E06."""
from __future__ import annotations

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor
from safety.policy import SafeToolPort, ToolPolicy
from toolbox.code_index import CODE_INDEX_TOOLS
from toolbox.filesystem import FsInsert, FsList, FsRead, FsStrReplace, FsWrite, FsWriteLines
from toolbox.lint_test import LINT_TEST_TOOLS
from toolbox.terminal import Terminal

FEATURE = FeatureDescriptor(
    name="toolbox",
    capabilities=(
        "fs_read",
        "fs_write",
        "fs_list",
        "fs_str_replace",
        "fs_insert",
        "fs_write_lines",
        "terminal_run",
        "code_index",
        "code_find_symbol",
        "code_find_references",
        "code_dependency_graph",
        "lint_compile",
        "ruff_check",
        "pytest_run",
    ),
    description="Workspace-sandboxed filesystem, surgical editors, terminal, code index, and validation tools.",
)


# Retry/risk semantics per tool: reads are idempotent + low risk; mutating effects must not be
# retried (non-idempotent) and carry the blast-radius risk the policy/retry layers key on;
# validation tools spawn a subprocess but never mutate the workspace, so they stay idempotent.
_DESCRIPTORS = {
    "fs_read": {"kind": "read", "idempotent": True, "risk": "low"},
    "fs_list": {"kind": "read", "idempotent": True, "risk": "low"},
    "fs_write": {"kind": "effect", "idempotent": False, "risk": "medium"},
    "fs_str_replace": {"kind": "effect", "idempotent": False, "risk": "medium"},
    "fs_insert": {"kind": "effect", "idempotent": False, "risk": "medium"},
    "fs_write_lines": {"kind": "effect", "idempotent": False, "risk": "medium"},
    "terminal_run": {"kind": "effect", "idempotent": False, "risk": "high"},
    "code_index": {"kind": "read", "idempotent": True, "risk": "low"},
    "code_find_symbol": {"kind": "read", "idempotent": True, "risk": "low"},
    "code_find_references": {"kind": "read", "idempotent": True, "risk": "low"},
    "code_dependency_graph": {"kind": "read", "idempotent": True, "risk": "low"},
    "lint_compile": {"kind": "effect", "idempotent": True, "risk": "low"},
    "ruff_check": {"kind": "effect", "idempotent": True, "risk": "low"},
    "pytest_run": {"kind": "effect", "idempotent": True, "risk": "medium"},
}

_TOOL_CLASSES = (
    FsRead,
    FsWrite,
    FsList,
    FsStrReplace,
    FsInsert,
    FsWriteLines,
    Terminal,
    *CODE_INDEX_TOOLS,
    *LINT_TEST_TOOLS,
)


def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    policy = ToolPolicy()
    for tool_cls in _TOOL_CLASSES:
        tool = tool_cls()
        kernel.registry.register_tool(
            tool.name,
            SafeToolPort(tool.name, tool, policy),
            feature_name=FEATURE.name,
            **_DESCRIPTORS[tool.name],
        )
