"""Supervisor — the Agent-O multi-agent TaskLoop (E10 v2).

A thin layer ABOVE the frozen kernel (not inside it): Agent O composes a team and
emits structured decisions; the Context Broker writes scoped briefings; worker
turns run as isolated child sessions via the delegation chokepoint. Core stays
minimal. See docs/spec/done/E10-multi-agent-graph/.
"""
from __future__ import annotations

from supervisor.broker import BrokerPort, DeterministicBroker
from supervisor.checkpoint import SqliteTaskLoopStore, taskloop_db_path
from supervisor.contracts import (
    AgentAssignment,
    AgentSelection,
    ContextPacket,
    OrchestratorDecision,
    SessionPlan,
    parse_decision,
    parse_session_plan,
)
from supervisor.llm import ChatLLM, KernelChatLLM, LLMBroker, LLMOrchestrator
from supervisor.loop import resume_task_loop, run_task_loop
from supervisor.orchestrator import OrchestratorPort, ScriptedOrchestrator
from supervisor.state import (
    AcceptanceCheck,
    AgentTurn,
    TaskLoopState,
    TaskLoopStatus,
    decode_taskloop_state,
    encode_taskloop_state,
)

__all__ = [
    "run_task_loop",
    "resume_task_loop",
    "SqliteTaskLoopStore",
    "taskloop_db_path",
    "OrchestratorPort",
    "ScriptedOrchestrator",
    "BrokerPort",
    "DeterministicBroker",
    "ChatLLM",
    "KernelChatLLM",
    "LLMOrchestrator",
    "LLMBroker",
    "SessionPlan",
    "AgentSelection",
    "AgentAssignment",
    "OrchestratorDecision",
    "ContextPacket",
    "parse_decision",
    "parse_session_plan",
    "TaskLoopState",
    "TaskLoopStatus",
    "AcceptanceCheck",
    "AgentTurn",
    "encode_taskloop_state",
    "decode_taskloop_state",
]
