"""Run a tiny scenario end-to-end on FakeLLM and print the event log + live view.

    python demo.py
"""
from dragzero import Agent, FakeLLM, Orchestrator, Roster, by_role, reduce, render_log, render_tree


SCRIPT = by_role({
    "planner": {
        "plan": {"steps": [{"id": "s1", "description": "scope the report"}], "next": "delegate research"},
        "decision": {"mode": "delegate", "target": "researcher", "subtask": "gather 3 sources"},
    },
    "researcher": {
        "plan": {"steps": [{"id": "s1", "description": "search + read"}], "next": "summarise findings"},
        "decision": {"mode": "solo"},
    },
})


def main() -> None:
    llm = FakeLLM(SCRIPT)
    roster = Roster([Agent("a1", "planner", llm), Agent("a2", "researcher", llm)])
    orch = Orchestrator(roster)
    log = orch.run("Write a short report on X")

    print("=== event log (source of truth) ===")
    print(render_log(log.events()))
    print("\n=== execution tree (read-model projection) ===")
    root, _ = reduce(log.events())
    print(render_tree(root))


if __name__ == "__main__":
    main()
