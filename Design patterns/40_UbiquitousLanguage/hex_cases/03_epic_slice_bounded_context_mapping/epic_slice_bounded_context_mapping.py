"""epic_slice_bounded_context_mapping.py — UL ở tầng CHIẾN LƯỢC: Epic/Slice ↔ code.

Bản DISTILL TRUNG THỰC của cách hex_agent dùng Ubiquitous Language vượt khỏi term
lẻ, lên tới KHÁI NIỆM CHIẾN LƯỢC: docstring module ghi Epic (E10 Supervisor, E21
Control Plane) + Slice (S10.1, S10.8...), và decision register (DEC-2, DEC-8) cột
term glossary vào quyết định. Architect nói "E10 composes teams" và dev đọc
supervisor/graph.py thấy CÙNG mental model.

NGUỒN THẬT distill từ (đã mở file xác minh path:line):
  - supervisor/graph.py:1-8   docstring "Supervisor nodes ... Epic E10."; node = phase
  - supervisor/graph.py:86    "# ── compose_team (S10.1) ──"
  - supervisor/graph.py:107   "# ── o_decide (S10.8) ──"
  - supervisor/graph.py:136   "# ── run_round (S10.2/S10.3/S10.5/S10.14) ──"
  - supervisor/contracts.py:1-8  docstring "Supervisor data contracts ... Epic E10."
  - control/events.py:1       docstring "RuntimeEvent envelope ... Epic E21 (S21.1/S21.7-info)."
  - delegation/manager.py:1   docstring "Sequential delegation chokepoint..." (term glossary)
  - docs/decisions.md:25-27 (DEC-2)  roster-growth + department + authority gate (graph.py:142-147)
  - docs/decisions.md:103-105 (DEC-8)  attribution≠authz
  - bài học gốc 40_UbiquitousLanguage.md §1.6 (Event Storming output IS UL) + invariant 1.

KHÔNG dùng gì ngoài thư viện chuẩn Python 3.14. KHÔNG import hex_agent.
Thay việc đọc file/grep thật bằng "module fixture" in-memory (docstring + comment).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# 1. MODULE FIXTURE — distill docstring + comment thật của vài module hex_agent.
#    Mỗi chuỗi giữ NGUYÊN dấu vết Epic/Slice + term để parser bắt được.
# ─────────────────────────────────────────────────────────────────────────────
MODULES: dict[str, str] = {
    "supervisor/graph.py": (
        "Supervisor nodes — compose_team / o_decide / run_round / judge / tool. Epic E10.\n"
        "# ── compose_team (S10.1) ──\n"
        "# ── o_decide (S10.8) ──\n"
        "# ── run_round (S10.2/S10.3/S10.5/S10.14) ──\n"
        "# authority gate: every assignment must target an agent the composition selected\n"
        "# roster-growth: a to-admit member runs next round via AddAgentToLoop\n"
    ),
    "supervisor/contracts.py": (
        "Supervisor data contracts — Agent O decisions + Context Broker packet. Epic E10.\n"
        "# team composition (S10.1)\n"
        "# orchestrator decision (S10.6/S10.8)\n"
        "# context packet (S10.3/S10.4/S10.14)\n"
    ),
    "control/events.py": (
        "RuntimeEvent envelope — the single shape every control-plane event uses. "
        "Epic E21 (S21.1/S21.7-info).\n"
    ),
    "delegation/manager.py": (
        "Sequential delegation chokepoint: policy, child session, progress, events, result.\n"
    ),
    "control/command_registry.py": (
        "Command-type registry — declares when each command applies and what it needs. "
        "Epic E21 (S21.4).\n"
        "# requires_permission resolves authz — doctrine: attribution≠authz\n"
    ),
    "roles/spec.py": (
        "RoleSpec (canonical) + RoleView (E10 projection) + role loader. Epic E09.\n"
        "# department: a named group of roles (RoleSpec.department) the Agent-O can target\n"
    ),
}

# Decision register (distill DEC-2 / DEC-8) — term glossary cột vào quyết định + Epic.
DECISIONS: dict[str, dict] = {
    "DEC-2": {
        "epic": "E21",
        "terms": ("roster-growth", "department", "authority gate"),
        "cites": ("supervisor/graph.py", "supervisor/contracts.py", "roles/spec.py"),
        "summary": "Delegation linh hoạt qua control plane; roster-growth + department qua AddAgentToLoop.",
    },
    "DEC-8": {
        "epic": "E21",
        "terms": ("attribution≠authz",),
        "cites": ("control/command_registry.py",),
        "summary": "attribution≠authz: issued_by là ghi nhận; authz = requires_permission tại checkpoint.",
    },
}

# Glossary term load-bearing (distill docs/GLOSSARY.md) — nguồn chân lý của UL.
GLOSSARY_TERMS = ("chokepoint", "roster-growth", "department", "authority gate", "attribution≠authz")


# ─────────────────────────────────────────────────────────────────────────────
# 2. PARSER — rút Epic/Slice/Term từ docstring + comment (gốc: đọc module thật)
# ─────────────────────────────────────────────────────────────────────────────
_EPIC_RE = re.compile(r"\bEpic (E\d{2})\b")
_SLICE_RE = re.compile(r"\b(S\d{1,2}\.\d{1,2})\b")


@dataclass
class ModuleRef:
    path: str
    epic: str | None
    slices: tuple[str, ...]
    terms: tuple[str, ...]    # term glossary xuất hiện trong module


def parse_module(path: str, text: str) -> ModuleRef:
    epics = _EPIC_RE.findall(text)
    slices = tuple(dict.fromkeys(_SLICE_RE.findall(text)))   # unique, giữ thứ tự
    terms = tuple(t for t in GLOSSARY_TERMS if re.search(rf"{re.escape(t)}", text))
    return ModuleRef(path=path, epic=(epics[0] if epics else None), slices=slices, terms=terms)


# ─────────────────────────────────────────────────────────────────────────────
# 3. MA TRẬN Epic → Slice → Module → Term (gốc: traceability chiến lược)
# ─────────────────────────────────────────────────────────────────────────────
def build_matrix(refs: list[ModuleRef]) -> dict[str, dict]:
    matrix: dict[str, dict] = {}
    for ref in refs:
        if ref.epic is None:
            continue
        bucket = matrix.setdefault(ref.epic, {"modules": [], "slices": set(), "terms": set()})
        bucket["modules"].append(ref.path)
        bucket["slices"].update(ref.slices)
        bucket["terms"].update(ref.terms)
    return matrix


# ─────────────────────────────────────────────────────────────────────────────
# 4. DRIFT CHECK — quyết định (ADR) có còn khớp code không (gốc: DEC cột term)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StaleDecision:
    decision_id: str
    missing_terms: list[str] = field(default_factory=list)   # term ADR nói nhưng code không còn
    missing_cites: list[str] = field(default_factory=list)   # module ADR trỏ nhưng không tồn tại


def check_decisions(decisions: dict, refs: list[ModuleRef], modules: dict[str, str]) -> list[StaleDecision]:
    """Một ADR 'tươi' nếu mọi term nó nói còn xuất hiện trong code + module nó trỏ còn tồn tại.

    Đây là cơ chế chống UL drift ở tầng chiến lược: rename term mà không update DEC ⇒ ADR stale.
    """
    all_text = "\n".join(modules.values())
    stale: list[StaleDecision] = []
    for dec_id, dec in decisions.items():
        rec = StaleDecision(decision_id=dec_id)
        for term in dec["terms"]:
            if not re.search(rf"{re.escape(term)}", all_text):
                rec.missing_terms.append(term)
        for cite in dec["cites"]:
            if cite not in modules:
                rec.missing_cites.append(cite)
        if rec.missing_terms or rec.missing_cites:
            stale.append(rec)
    return stale


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 03 — Epic/Slice ↔ Bounded Context mapping (UL chiến lược, hex_agent)")
    print("=" * 72)

    refs = [parse_module(p, t) for p, t in MODULES.items()]

    print("\n[1] Parse docstring/comment → Epic + Slice + Term mỗi module:")
    for r in refs:
        print(f"    {r.path:<30} epic={r.epic or '-':<4} slices={list(r.slices)} terms={list(r.terms)}")

    print("\n[2] Ma trận Epic → Slice → Module → Term (mental model chung architect↔dev):")
    matrix = build_matrix(refs)
    for epic, info in sorted(matrix.items()):
        print(f"    {epic}:")
        print(f"        modules: {info['modules']}")
        print(f"        slices : {sorted(info['slices'])}")
        print(f"        terms  : {sorted(info['terms'])}")

    # Bất biến: E10 phải gom đúng supervisor modules + có slice S10.1 (compose_team).
    assert "E10" in matrix, "Epic E10 (Supervisor) phải xuất hiện trong ma trận."
    assert "supervisor/graph.py" in matrix["E10"]["modules"]
    assert "S10.1" in matrix["E10"]["slices"], "S10.1 (compose_team) phải nối với E10."
    # E21 control plane gom events + command_registry.
    assert "E21" in matrix and "control/events.py" in matrix["E21"]["modules"]

    print("\n[3] Term glossary có mặt trong code (UL chảy vào docstring/comment):")
    for term in GLOSSARY_TERMS:
        where = [r.path for r in refs if term in r.terms]
        print(f"    {term:<18} ⇐ {where if where else 'KHÔNG thấy trong module fixture'}")
    # Bất biến: 'authority gate' phải xuất hiện trong supervisor/graph.py.
    assert any("authority gate" in r.terms and r.path == "supervisor/graph.py" for r in refs)

    print("\n[4] ADR còn khớp code? (DEC cột term glossary — gốc DEC-2/DEC-8):")
    stale = check_decisions(DECISIONS, refs, MODULES)
    assert not stale, f"Lúc này mọi ADR phải còn tươi, nhưng stale={stale}"
    print("    OK — mọi term DEC-2/DEC-8 còn trong code, mọi module được trỏ còn tồn tại.")

    print("\n[5] ĐỐI CHỨNG — UL drift: dev đổi term trong CODE mà KHÔNG update DEC-2:")
    drifted = dict(MODULES)
    # Dev rename 'roster-growth' → 'team_expansion' trong code, quên sửa glossary + DEC-2.
    drifted["supervisor/graph.py"] = drifted["supervisor/graph.py"].replace(
        "roster-growth", "team_expansion")
    refs_drift = [parse_module(p, t) for p, t in drifted.items()]
    stale2 = check_decisions(DECISIONS, refs_drift, drifted)
    print(f"    ADR stale phát hiện: {[(s.decision_id, s.missing_terms) for s in stale2]}")
    assert any(s.decision_id == "DEC-2" and "roster-growth" in s.missing_terms for s in stale2), (
        "DEC-2 phải stale khi term 'roster-growth' biến mất khỏi code mà ADR vẫn nói tới.")
    print("    → DEC-2 trở thành ADR 'nói dối': nó tham chiếu term không còn trong code.")
    print("    → Đây chính là UL drift ở tầng chiến lược — mapping Epic/Slice/Term vỡ.")

    print("\nKẾT: UL không dừng ở term lẻ. Epic/Slice trong docstring + DEC cột term vào")
    print("     quyết định ⇒ architect và dev chia sẻ MỘT mental model; drift bị phát hiện.")


if __name__ == "__main__":
    demo()
