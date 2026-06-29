"""decompose_agent — a local-35B "decompose-until-trivial" agent.

Navigator (deterministic CODE) owns every global — the on-disk node tree, the DFS
cursor, all gates, all budgets, the decomposition cache. The Worker (35B) is a local
proposer on ONE node and never writes a verdict, resolves a path, or mutates the tree.
Code is the sole PASS/FAIL authority. See plans/260626-1221-recursive-decompose-agent/spec.md.
"""
