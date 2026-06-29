"""
Case 02 — Node / DoneWhen: Factory method (from_dict) + Specification (validation-as-construction).

DISTILL TRUNG THỰC từ codebase hex_agent:
  - decompose_agent/node.py:102-176  Node (frozen dataclass) + __post_init__ + from_dict/as_dict
  - decompose_agent/node.py:50-99    DoneWhen + __post_init__ + from_dict (FORBIDDEN_VERDICT_KEYS)
  - decompose_agent/node.py:33-47    assert_safe_relpath (path-jail = predicate kiểu spec)
  - decompose_agent/node.py:19-30    FORBIDDEN_VERDICT_KEYS / VALID_STATUSES / VALID_KINDS

Bài học gốc văn phong: Design patterns/37_RepoFactorySpec/37_RepoFactorySpec.md

KHÔNG import gì từ hex_agent và KHÔNG dùng thư viện bên thứ ba.
Hạ tầng nặng (YAML loader, runner filesystem) bị lược; ta chỉ giữ:
  - dataclass frozen + __post_init__ (factory enforce invariant lúc dựng).
  - from_dict (factory entry) + as_dict (reverse cho persistence) -> round-trip.
  - Specification: FORBIDDEN_VERDICT_KEYS (chống worker giả mạo verdict) + path-jail.

Bối cảnh DDD: Node là "1 đơn vị công việc trên đĩa". Một node SAI CẤU TRÚC không được phép
tồn tại — mọi invariant enforce TẠI construct, không phải sau đó. DoneWhen là "câu hỏi mà
gate sẽ trả lời", KHÔNG BAO GIỜ là câu trả lời -> mọi key dạng verdict bị từ chối tại factory.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# decompose_agent/node.py:20  — verdict-shaped keys mà criterion KHÔNG được mang.
FORBIDDEN_VERDICT_KEYS = frozenset({"verdict", "passed", "status", "score", "done"})
# decompose_agent/node.py:23  — đúng 3 field hợp lệ của một criterion.
_CRITERION_KEYS = frozenset({"check", "params", "artifact"})
# decompose_agent/node.py:26  — các check không cần artifact (ở đây rút gọn còn 1 cái).
ARTIFACTLESS_CHECKS = frozenset({"all_children_done"})
# decompose_agent/node.py:28-29
VALID_STATUSES = frozenset({"pending", "active", "decomposed", "done", "blocked"})
VALID_KINDS = frozenset({"work", "reduce"})


# ─────────────────────────────────────────────────────────────────────────────
# Specification kiểu predicate áp lúc construct — distill assert_safe_relpath (node.py:33-47)
# ─────────────────────────────────────────────────────────────────────────────

def assert_safe_relpath(path: str) -> str:
    """Path-jail artifact tại lúc author: chỉ chấp nhận đường dẫn tương đối, trong workspace.

    Từ chối absolute path, '~', và mọi segment '..'. Đây là một specification (predicate
    thuần) áp NGAY khi dựng object — đường dẫn không an toàn không bao giờ chạm tới filesystem.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("artifact path must be a non-empty string")
    p = path.strip()
    if p.startswith("/") or p.startswith("~"):
        raise ValueError(f"artifact path must be relative and in-workspace: {path!r}")
    if ".." in p.split("/"):
        raise ValueError(f"artifact path must not escape the workspace ('..'): {path!r}")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# DoneWhen — value object + factory + Specification chống forgery (node.py:50-99)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DoneWhen:
    """Một tiêu chí nghiệm thu: câu hỏi gate trả lời. KHÔNG bao giờ là câu trả lời."""

    check: str
    params: dict[str, Any] = field(default_factory=dict)
    artifact: str | None = None

    def __post_init__(self) -> None:
        # Invariant enforce tại construct (node.py:58-69).
        if not isinstance(self.check, str) or not self.check.strip():
            raise ValueError("done_when criterion is missing a non-empty 'check'")
        if not isinstance(self.params, dict):
            raise ValueError(
                f"done_when criterion 'params' must be a mapping, got {type(self.params).__name__}"
            )
        if self.artifact is not None:
            # frozen dataclass -> phải dùng object.__setattr__ để normalize.
            object.__setattr__(self, "artifact", assert_safe_relpath(self.artifact))
        elif self.check not in ARTIFACTLESS_CHECKS:
            raise ValueError(f"done_when criterion {self.check!r} requires an 'artifact' path")

    @classmethod
    def from_dict(cls, raw: Any) -> "DoneWhen":
        # Factory entry với SPECIFICATION an toàn (node.py:71-91).
        if not isinstance(raw, dict):
            raise ValueError(f"done_when criterion must be a mapping, got {type(raw).__name__}")
        extra = set(raw) - _CRITERION_KEYS
        forged = extra & FORBIDDEN_VERDICT_KEYS
        if forged:
            # Worker đề xuất action; GATE mới ghi verdict. Key verdict = giả mạo -> chặn.
            raise ValueError(
                f"done_when criterion must not carry a verdict field {sorted(forged)} — "
                "the gate writes the verdict, not the author"
            )
        if extra:
            raise ValueError(
                f"done_when criterion has unexpected field(s) {sorted(extra)}; "
                "criteria are exactly {check, params, artifact}"
            )
        return cls(
            check=raw.get("check"),
            params=dict(raw.get("params") or {}),
            artifact=raw.get("artifact"),
        )

    def as_dict(self) -> dict[str, Any]:
        # Reverse về primitives cho persistence (node.py:93-99).
        out: dict[str, Any] = {"check": self.check}
        if self.params:
            out["params"] = dict(self.params)
        if self.artifact is not None:
            out["artifact"] = self.artifact
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Node — aggregate frozen + factory from_dict + invariant __post_init__ (node.py:102-176)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Node:
    """Một đơn vị công việc. Frozen — chuyển status qua dataclasses.replace,
    không ai mutate trực tiếp (chỉ Navigator sở hữu cây).
    """

    id: str
    parent: str | None = None
    kind: str = "work"
    status: str = "pending"
    depends_on: tuple[str, ...] = ()
    done_when: tuple[DoneWhen, ...] = ()
    max_attempts: int = 3
    attempts: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        # Mọi invariant enforce tại construct (node.py:122-140). Node sai cấu trúc KHÔNG tồn tại.
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Node.id is required and must be a non-empty string")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"Node.kind must be one of {sorted(VALID_KINDS)}, got {self.kind!r}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Node.status must be one of {sorted(VALID_STATUSES)}, got {self.status!r}")
        if not isinstance(self.depends_on, tuple):
            raise ValueError("Node.depends_on must be a tuple")
        if not isinstance(self.done_when, tuple) or not all(isinstance(c, DoneWhen) for c in self.done_when):
            raise ValueError("Node.done_when must be a tuple of DoneWhen")
        if self.max_attempts < 1:
            raise ValueError("Node.max_attempts (K) must be >= 1")
        if self.attempts < 0:
            raise ValueError("Node.attempts must be >= 0")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        # Factory entry (node.py:143-158): build DoneWhen lồng nhau qua factory của nó.
        if not isinstance(d, dict) or "id" not in d:
            raise ValueError("node must be a mapping with an 'id'")
        return cls(
            id=d["id"],
            parent=d.get("parent"),
            kind=d.get("kind", "work"),
            status=d.get("status", "pending"),
            depends_on=tuple(d.get("depends_on") or ()),
            done_when=tuple(DoneWhen.from_dict(c) for c in (d.get("done_when") or ())),
            max_attempts=int(d.get("max_attempts", 3)),
            attempts=int(d.get("attempts", 0)),
            notes=d.get("notes", ""),
        )

    def as_dict(self) -> dict[str, Any]:
        # Reverse cho persistence (node.py:160-176) — chỉ giữ field cốt lõi cho demo.
        out: dict[str, Any] = {
            "id": self.id,
            "parent": self.parent,
            "kind": self.kind,
            "status": self.status,
            "depends_on": list(self.depends_on),
            "max_attempts": self.max_attempts,
            "done_when": [c.as_dict() for c in self.done_when],
        }
        if self.notes:
            out["notes"] = self.notes
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Đối chứng: KHÔNG có factory/spec -> dùng dict trần, verdict giả mạo lọt qua
# ─────────────────────────────────────────────────────────────────────────────

def naive_gate_without_spec(criterion: dict[str, Any]) -> bool:
    """ANTI-PATTERN: gate đọc 'verdict' lẫn trong criterion do worker tự ghi.

    Vì không có Specification chặn lúc construct, criterion {'verdict': True} được tin
    như sự thật -> worker tự nghiệm thu chính mình. Đây là lỗ hổng mà DoneWhen.from_dict bịt.
    """
    if criterion.get("verdict") is True:   # tin lời worker
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────

def demo() -> None:
    print("=" * 70)
    print("CASE 02 — Node/DoneWhen: Factory (from_dict) + Specification (validation)")
    print("=" * 70)

    # ---- Factory happy path -------------------------------------------------
    print("\n[1] Node.from_dict: factory dựng node hợp lệ")
    valid = {
        "id": "ai.rag",
        "done_when": [
            {"check": "file_exists", "artifact": "out/x.json"},
            {"check": "all_children_done"},  # check artifactless -> không cần artifact
        ],
    }
    n = Node.from_dict(valid)
    print(f"    -> n.id={n.id!r}, status={n.status!r}, #criteria={len(n.done_when)}")
    print(f"    -> criterion[0].artifact (đã normalize)={n.done_when[0].artifact!r}")
    assert n.id == "ai.rag"
    assert n.status == "pending"
    assert len(n.done_when) == 2

    # ---- Round-trip qua persistence -----------------------------------------
    print("\n[2] Round-trip: from_dict(as_dict(n)) == as_dict ban đầu")
    round_tripped = Node.from_dict(n.as_dict()).as_dict()
    print(f"    -> bằng nhau: {round_tripped == n.as_dict()}")
    assert round_tripped == n.as_dict(), "as_dict/from_dict phải round-trip ổn định"

    # ---- Specification chống forgery: từ chối key verdict --------------------
    print("\n[3] DoneWhen.from_dict TỪ CHỐI key dạng verdict (worker không tự nghiệm thu)")
    for bad_key in ("verdict", "passed", "status", "score", "done"):
        hacked = {"check": "file_exists", "artifact": "x.json", bad_key: True}
        try:
            DoneWhen.from_dict(hacked)
            raise AssertionError(f"Phải chặn key verdict {bad_key!r}")
        except ValueError as e:
            print(f"    -> chặn {bad_key!r}: {str(e)[:55]}...")

    # ---- Specification path-jail --------------------------------------------
    print("\n[4] assert_safe_relpath chặn path thoát workspace")
    for evil in ("/etc/passwd", "~/secret", "../../escape.json"):
        try:
            DoneWhen(check="file_exists", artifact=evil)
            raise AssertionError(f"Phải chặn path {evil!r}")
        except ValueError as e:
            print(f"    -> chặn {evil!r}: {str(e)[:50]}...")

    # ---- Invariant: kind/status/max_attempts ---------------------------------
    print("\n[5] __post_init__ enforce invariant cấu trúc")
    try:
        Node.from_dict({"id": "x", "kind": "bogus"})
        raise AssertionError("kind sai phải raise")
    except ValueError as e:
        print(f"    -> kind sai bị chặn: {str(e)[:45]}...")
    try:
        Node.from_dict({"id": "x", "max_attempts": 0})
        raise AssertionError("max_attempts<1 phải raise")
    except ValueError as e:
        print(f"    -> max_attempts=0 bị chặn: {str(e)[:45]}...")

    # ---- Frozen: status chỉ đổi qua replace ----------------------------------
    print("\n[6] Node frozen: gán trực tiếp raise; chuyển status qua dataclasses.replace")
    try:
        n.status = "done"           # type: ignore[misc]
        raise AssertionError("frozen node không cho gán")
    except Exception as e:           # FrozenInstanceError là subclass của Exception
        print(f"    -> gán trực tiếp bị chặn ({type(e).__name__})")
    advanced = replace(n, status="active")
    print(f"    -> replace -> status mới={advanced.status!r}, bản gốc giữ {n.status!r}")
    assert advanced.status == "active"
    assert n.status == "pending", "replace tạo bản mới, không mutate bản cũ"

    # ---- ĐỐI CHỨNG: không có spec -> verdict giả mạo lọt qua -----------------
    print("\n[7] ĐỐI CHỨNG — gate KHÔNG có Specification thì bị worker lừa")
    forged_criterion = {"check": "file_exists", "artifact": "x.json", "verdict": True}
    print(f"    -> gate ngây thơ trả: {naive_gate_without_spec(forged_criterion)} (SAI: worker tự nghiệm thu)")
    assert naive_gate_without_spec(forged_criterion) is True, "minh hoạ lỗ hổng khi thiếu spec"
    print("    -> với Specification (DoneWhen.from_dict), criterion này bị chặn NGAY lúc dựng:")
    try:
        DoneWhen.from_dict(forged_criterion)
        raise AssertionError
    except ValueError:
        print("       => criterion forgery không bao giờ trở thành object. Lỗ hổng bịt tại factory.")

    print("\n[OK] Mọi assert pass. Factory enforce invariant + Specification chặn forgery đúng.")


if __name__ == "__main__":
    demo()
