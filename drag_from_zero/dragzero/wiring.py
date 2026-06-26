"""Build a runnable Orchestrator from a Topology (Đồ thị 1 → live runtime).

This is the bridge from declarative config to behaviour: agent nodes become a
Roster, tool/hook/router nodes wire the registries from named catalogs, and the
budget node sets the gate. Unknown capability names fail loudly. Swapping the
LLM (FakeLLM ↔ local model) is just the `llm` argument — the topology is data.
"""
from __future__ import annotations

from dataclasses import dataclass

from .agent import Agent
from .builtins import BUILTIN_HOOKS, BUILTIN_RULES
from .orchestrator import Orchestrator
from .registries import Budget, HookRegistry, RuleRegistry, ToolRegistry
from .roster import Roster
from .topology import TopologyError


@dataclass
class Runtime:
    orchestrator: Orchestrator
    entry: object  # the entry Agent

    def run(self, task: str):
        return self.orchestrator.run(task, agent=self.entry)


def build_runtime(
    topology,
    llm,
    *,
    tool_catalog: dict = None,
    hook_catalog: dict = None,
    rule_catalog: dict = None,
    sandbox: object = None,
    max_tool_steps: int = 8,
) -> Runtime:
    topology.validate(raise_on_error=True)
    tool_catalog = tool_catalog or {}
    hook_catalog = BUILTIN_HOOKS if hook_catalog is None else hook_catalog
    rule_catalog = BUILTIN_RULES if rule_catalog is None else rule_catalog

    tools = ToolRegistry()
    hooks = HookRegistry()
    rules = RuleRegistry()
    agent_nodes: list = []
    entry_node = None

    for node in topology.nodes:
        if node.type == "agent":
            agent_nodes.append(node)
            if node.attrs.get("entry"):
                entry_node = node
        elif node.type == "tool":
            name = node.attrs["tool"]
            if name not in tool_catalog:
                raise TopologyError(f"unknown tool {name!r} (node {node.id!r})")
            tools.register(tool_catalog[name])
        elif node.type == "hook":
            name = node.attrs["hook"]
            if name not in hook_catalog:
                raise TopologyError(f"unknown hook {name!r} (node {node.id!r})")
            hooks.register(node.attrs.get("phase", "pre_delegate"), hook_catalog[name])
        elif node.type == "router":
            name = node.attrs["rule"]
            if name not in rule_catalog:
                raise TopologyError(f"unknown rule {name!r} (node {node.id!r})")
            rules.add(rule_catalog[name](node.attrs.get("config", {})))
        elif node.type == "memory":
            pass  # placeholder node type — kept for round-trip / the UI, not wired yet

    if not agent_nodes:
        raise TopologyError("topology has no agent nodes")
    entry_node = entry_node or agent_nodes[0]
    ordered = [entry_node] + [n for n in agent_nodes if n is not entry_node]
    roster = Roster([Agent(n.id, n.attrs["role"], llm) for n in ordered])

    budget = Budget(limit=topology.budget.get("max_llm_calls")) if topology.budget else Budget()
    orch = Orchestrator(
        roster,
        hooks=hooks,
        budget=budget,
        rules=rules,
        tools=tools,
        sandbox=sandbox,
        max_tool_steps=max_tool_steps,
    )
    return Runtime(orch, roster.first())
