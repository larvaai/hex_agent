"""glossary_canonical_registry.py — Glossary as code + CI guard + rename impact.

Bản DISTILL TRUNG THỰC của cách hex_agent biến Ubiquitous Language thành HẠ TẦNG:
glossary là first-class artifact, được CI canh, và rename term là migration nhiều phase.

NGUỒN THẬT distill từ (đã mở file xác minh path:line):
  - docs/GLOSSARY.md:1-19
        Bảng glossary chính: 9+ term load-bearing (chokepoint, roster-growth,
        department alias, safe checkpoint, trust-O, authority gate,
        attribution≠authz...). Mỗi term: nghĩa + trỏ file:line định nghĩa nó.
  - harness/tests/test_glossary_invariants.py:1-69
        CI gate: glossary file phải tồn tại; bảng phải còn cột; core term phải
        còn hàng; ban-wording phải đăng ký. Chống "hollowing-out" + drift.
  - docs/decisions.md:25-27 (DEC-2) và :103-105 (DEC-8)
        Term glossary (roster-growth, department, attribution≠authz) được cột
        vào quyết định kiến trúc → rename term kéo theo update ADR.
  - bài học gốc 40_UbiquitousLanguage.md §2.2 (drift detection) + §2.3 (5-phase rename).

KHÔNG dùng gì ngoài thư viện chuẩn Python 3.14. KHÔNG import hex_agent.
Thay markdown/CI/grep thật bằng glossary in-memory + scan chuỗi tối thiểu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# 1. GLOSSARY AS CODE — Term là first-class object (gốc: docs/GLOSSARY.md hàng bảng)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Term:
    """Một thuật ngữ load-bearing của Ubiquitous Language.

    Phản chiếu một HÀNG trong docs/GLOSSARY.md: term có nghĩa + nơi định nghĩa
    (backing) + danh sách synonym bị cấm (deprecated) + chỗ code dùng nó (used_by).
    """
    name: str
    definition: str
    backing: str                          # file:line định nghĩa term (vd core/kernel.py:106)
    used_by: tuple[str, ...] = ()         # class/method/event dùng term này
    synonyms: tuple[str, ...] = ()        # tên thay thế ĐÃ bị deprecate
    deprecated: bool = False


@dataclass
class Glossary:
    """Sổ đăng ký UL của một bounded context. Gốc: docs/GLOSSARY.md + CI gate."""
    bc_name: str
    terms: dict[str, Term] = field(default_factory=dict)

    def add(self, term: Term) -> None:
        if term.name in self.terms:
            raise ValueError(f"Term '{term.name}' đã có trong glossary — không đặt lại tên.")
        self.terms[term.name] = term

    # ── CI guard (gốc: test_glossary_invariants.py) ─────────────────────────
    def assert_invariants(self, core_terms: tuple[str, ...], banned_wording: tuple[str, ...]) -> None:
        """Mô phỏng test_glossary_invariants.py: glossary không được rỗng hoá/drift."""
        assert self.terms, "GLOSSARY rỗng — planning skills tham chiếu nó sẽ thành dangling reference."
        missing = [t for t in core_terms if t not in self.terms]
        assert not missing, f"GLOSSARY mất core term: {missing}"
        for term in self.terms.values():
            assert term.definition.strip(), f"Term '{term.name}' không có nghĩa."
            assert term.backing.strip(), f"Term '{term.name}' không trỏ nơi định nghĩa (backing)."
        # ban-wording: tên không được hứa điều cơ chế không làm được
        # (gốc: test_bug_class_invariants ban 'write-fence' cho fs_guard).
        for term in self.terms.values():
            for word in banned_wording:
                assert word.lower() not in term.definition.lower(), (
                    f"Term '{term.name}' dùng wording bị cấm: {word!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. DRIFT DETECTOR — code dùng từ NÀO so với glossary (gốc: bài học §2.2)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DriftReport:
    undefined_in_code: list[str] = field(default_factory=list)   # code dùng nhưng glossary không có
    deprecated_in_code: list[str] = field(default_factory=list)  # code còn dùng synonym đã deprecate
    orphaned_terms: list[str] = field(default_factory=list)      # glossary có nhưng code không dùng

    @property
    def clean(self) -> bool:
        return not (self.undefined_in_code or self.deprecated_in_code or self.orphaned_terms)


def drift_check(glossary: Glossary, code: str) -> DriftReport:
    """Dò language drift giữa glossary và một đoạn code (chuỗi).

    Heuristic giống bài học: tìm từ deprecated còn trong code; tìm term-y word
    code dùng nhưng glossary chưa định nghĩa; tìm term glossary không ai dùng.
    """
    report = DriftReport()
    # Token định danh đơn (CamelCase / snake_case), tách riêng từng cái.
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", code))
    # Chuẩn hoá: so khớp theo tên term (có thể nhiều từ như "safe checkpoint").
    canonical = set(glossary.terms)
    all_synonyms = {syn: t.name for t in glossary.terms.values() for syn in t.synonyms}

    # (a) synonym deprecated còn xuất hiện trong code → drift.
    for syn, canon in all_synonyms.items():
        if re.search(rf"\b{re.escape(syn)}\b", code):
            report.deprecated_in_code.append(f"{syn} (đáng lẽ dùng '{canon}')")

    # (b) term được đánh dấu used_by nhưng không thấy trong code → orphaned.
    for term in glossary.terms.values():
        if not term.deprecated and not re.search(rf"\b{re.escape(term.name)}\b", code):
            report.orphaned_terms.append(term.name)

    # (c) "từ giống term" (CamelCase hoặc snake_case domain) nhưng không có trong glossary.
    #     Bỏ qua keyword Python + token đã là một phần của term/synonym đã biết.
    _ignore = {"def", "class", "return", "self", "None", "True", "False"}
    # Vocabulary đã biết = tên term + synonym + mọi class/method/event trong used_by.
    used_by_tokens = {u for t in glossary.terms.values() for u in t.used_by}
    vocab = canonical | set(all_synonyms) | used_by_tokens
    known_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", " ".join(vocab)))
    candidate_terms = {
        w for w in identifiers
        if (re.search(r"[a-z][A-Z]", w) or "_" in w) and w not in _ignore
    }
    for w in sorted(candidate_terms):
        if w not in known_tokens:
            report.undefined_in_code.append(w)
    return report


# ─────────────────────────────────────────────────────────────────────────────
# 3. RENAME IMPACT — rename là migration nhiều phase (gốc: bài học §2.3, DEC-2)
# ─────────────────────────────────────────────────────────────────────────────
def plan_rename(glossary: Glossary, old: str, new: str) -> list[str]:
    """Sinh kế hoạch rename 5-phase cho một term UL.

    Phản chiếu bài học: rename KHÔNG big-bang. Term cột vào ADR (DEC-2) nên đổi
    tên kéo theo update decision + mọi used_by. Trả về danh sách dòng kế hoạch.
    """
    assert old in glossary.terms, f"Không thể rename: '{old}' không có trong glossary."
    assert new not in glossary.terms, f"'{new}' đã tồn tại — collision."
    term = glossary.terms[old]
    touch_points = list(term.used_by) + [term.backing, "docs/decisions.md (ADR cột term)"]
    plan = [
        f"PHASE 1 (tuần 1) — Deprecate: thêm '{new}' làm preferred, mark '{old}' deprecated,",
        f"                    viết ADR giải thích lý do; code VẪN dùng '{old}'.",
        f"PHASE 2 (tuần 2-4) — Dual support: cập nhật {len(touch_points)} touch-point sang '{new}':",
    ]
    plan += [f"                    - {tp}" for tp in touch_points]
    plan += [
        f"PHASE 3 (tháng 2-3) — Migration window: downstream consumer chuyển dần; theo dõi còn ai dùng '{old}'.",
        f"PHASE 4 (tháng 4) — Remove old: bỏ alias '{old}', gỡ synonym khỏi glossary.",
        f"PHASE 5 (tháng 5) — Cleanup: rà stragglers; glossary mark '{old}' until=today.",
    ]
    return plan


def apply_rename(glossary: Glossary, old: str, new: str) -> None:
    """Áp rename: '{new}' kế thừa nghĩa của '{old}', '{old}' thành synonym deprecated."""
    term = glossary.terms.pop(old)
    renamed = Term(
        name=new,
        definition=term.definition,
        backing=term.backing,
        used_by=term.used_by,
        synonyms=term.synonyms + (old,),   # giữ lịch sử: old thành synonym
    )
    glossary.terms[new] = renamed


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def build_hex_glossary() -> Glossary:
    """Dựng lại (rút gọn) glossary thật của hex_agent từ docs/GLOSSARY.md."""
    g = Glossary(bc_name="hex_agent")
    g.add(Term(
        name="chokepoint",
        definition="Cửa duy nhất mọi LLM+tool call phải đi qua: AgentKernel.execute_tool.",
        backing="core/kernel.py:106",
        used_by=("execute_tool", "delegation.manager"),
    ))
    g.add(Term(
        name="roster-growth",
        definition="Thêm một agent/role vào team của TaskLoop ĐANG chạy, áp tại safe checkpoint.",
        backing="docs/decisions.md:25 (DEC-2)",
        used_by=("AddAgentToLoop", "pending_commands"),
    ))
    g.add(Term(
        name="authority gate",
        definition="Kiểm tra trong run_round: mọi assignment phải target agent đã trong selected_agents.",
        backing="supervisor/graph.py:142-149",
        used_by=("run_round",),
    ))
    g.add(Term(
        name="attribution≠authz",
        definition="issued_by/Actor chỉ GHI NHẬN ai phát (audit); authz thật = requires_permission tại checkpoint.",
        backing="docs/decisions.md:103-105 (DEC-8)",
        used_by=("Actor", "requires_permission"),
    ))
    return g


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Glossary as code + CI guard + rename impact (hex_agent)")
    print("=" * 72)

    g = build_hex_glossary()
    print(f"\n[1] Dựng glossary BC '{g.bc_name}' với {len(g.terms)} term load-bearing:")
    for t in g.terms.values():
        print(f"    - {t.name:<18} → {t.backing}")

    print("\n[2] CI guard chạy (mô phỏng test_glossary_invariants.py)...")
    g.assert_invariants(
        core_terms=("chokepoint", "authority gate", "attribution≠authz"),
        banned_wording=("write-fence",),  # gốc: ban cho fs_guard
    )
    print("    OK — glossary không rỗng, đủ core term, mọi term có nghĩa + backing,")
    print("         không dùng wording bị cấm. Glossary không thể bị hollowing-out.")

    print("\n[3] ĐỐI CHỨNG — khi KHÔNG có glossary/UL: code dùng term lẫn lộn")
    drifted_code = (
        "def push_agent(...): ...        # đáng lẽ là roster-growth\n"
        "class ExecutionGateway: ...     # term lạ, không định nghĩa ở đâu\n"
        "def dispatch_tool(...): ...     # đáng lẽ đi qua chokepoint\n"
    )
    # Cho biết 'push_agent' là synonym deprecated của 'roster-growth' để detector bắt được.
    g.terms["roster-growth"] = Term(
        name="roster-growth",
        definition=g.terms["roster-growth"].definition,
        backing=g.terms["roster-growth"].backing,
        used_by=g.terms["roster-growth"].used_by,
        synonyms=("push_agent",),
    )
    report = drift_check(g, drifted_code)
    print("    Drift detector phát hiện:")
    print(f"      - synonym deprecated còn trong code : {report.deprecated_in_code}")
    print(f"      - term lạ không định nghĩa          : {report.undefined_in_code}")
    print("    → New dev đọc code này phải HỎI 'ExecutionGateway là gì?' và nhận 3 câu trả lời khác nhau.")
    assert not report.clean, "Code lẫn lộn term PHẢI bị drift detector bắt."
    assert "ExecutionGateway" in report.undefined_in_code
    assert any("push_agent" in d for d in report.deprecated_in_code)

    print("\n[4] Code SẠCH (dùng đúng UL) → drift detector im lặng:")
    clean_code = (
        "# chokepoint: mọi call đi qua execute_tool\n"
        "# roster-growth tại safe checkpoint qua AddAgentToLoop\n"
        "# authority gate trong run_round\n"
        "# attribution≠authz: requires_permission quyết định\n"
    )
    clean_report = drift_check(g, clean_code)
    print(f"      undefined={clean_report.undefined_in_code} deprecated={clean_report.deprecated_in_code}"
          f" orphaned={clean_report.orphaned_terms}")
    assert not clean_report.undefined_in_code, "Code dùng đúng UL không được có term undefined."
    assert not clean_report.deprecated_in_code, "Code sạch không được dùng synonym deprecated."
    print("    OK — mọi term trong code khớp glossary.")

    print("\n[5] RENAME 'chokepoint' → 'execution_gate' KHÔNG big-bang (gốc bài học §2.3):")
    plan = plan_rename(g, "chokepoint", "execution_gate")
    for line in plan:
        print("    " + line)
    apply_rename(g, "chokepoint", "execution_gate")
    assert "execution_gate" in g.terms, "Sau rename, term mới phải có trong glossary."
    assert "chokepoint" not in g.terms, "Term cũ phải rời khỏi danh sách chính."
    assert "chokepoint" in g.terms["execution_gate"].synonyms, "Term cũ phải được giữ làm synonym (lịch sử)."
    # bất biến: nghĩa được kế thừa, không mất.
    assert "execute_tool" in g.terms["execution_gate"].definition
    print("    OK — 'execution_gate' kế thừa nghĩa; 'chokepoint' thành synonym deprecated (giữ lịch sử).")

    print("\nKẾT: UL trong hex_agent là HẠ TẦNG — glossary as code, CI canh drift,")
    print("     rename là migration nhiều phase. Không phải Confluence page bị bỏ quên.")


if __name__ == "__main__":
    demo()
