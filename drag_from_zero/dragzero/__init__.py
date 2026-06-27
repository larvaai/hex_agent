"""drag_from_zero — Slice 1.

A dynamically composable multi-agent runtime. The event log is the single source
of truth; the execution tree (the live view) is a pure projection of it.

This slice ships the *harness* (gates, not policy) and runs entirely on a
deterministic FakeLLM so the invariants are testable. A real local LLM
(llama.cpp / LM Studio) slots in behind the same `LLM.complete()` seam in Slice 2.
"""
from .agent import Agent, AgentStep, Task
from .contracts import (
    DelegationDecision,
    DelegationMode,
    PlanSpec,
    PlanStep,
    TaskStatus,
    ToolCall,
    TriageResult,
)
from .events import Event, EventLog, EventType
from .live_view import render, render_log, render_tree
from .llm import LLM, FakeLLM, by_role
from .orchestrator import Orchestrator
from .read_model import TaskBox, TaskNode, reduce, reduce_inbox
from .builtins import BUILTIN_HOOKS, BUILTIN_RULES
from .registries import Budget, HookRegistry, RuleRegistry, ToolRegistry
from .roster import Roster
from .tools import SandboxError, Tool, ToolResult
from .topology import Edge, Node, Topology, TopologyError, dump_json, load_file, load_json
from .wiring import Runtime, build_runtime

__all__ = [
    "Agent",
    "AgentStep",
    "Task",
    "DelegationDecision",
    "DelegationMode",
    "PlanSpec",
    "PlanStep",
    "TaskStatus",
    "ToolCall",
    "TriageResult",
    "SandboxError",
    "Tool",
    "ToolResult",
    "Event",
    "EventLog",
    "EventType",
    "render",
    "render_log",
    "render_tree",
    "LLM",
    "FakeLLM",
    "by_role",
    "Orchestrator",
    "TaskNode",
    "TaskBox",
    "reduce",
    "reduce_inbox",
    "Budget",
    "HookRegistry",
    "RuleRegistry",
    "ToolRegistry",
    "Roster",
    "Topology",
    "Node",
    "Edge",
    "TopologyError",
    "load_json",
    "dump_json",
    "load_file",
    "build_runtime",
    "Runtime",
    "BUILTIN_HOOKS",
    "BUILTIN_RULES",
]
