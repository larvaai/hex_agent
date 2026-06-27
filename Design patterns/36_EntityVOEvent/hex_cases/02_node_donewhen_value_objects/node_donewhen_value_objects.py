"""
Case 02 — Node (Entity) sở hữu DoneWhen (Value Object)

BẢN DISTILL TRUNG THỰC từ codebase hex_agent:
    - decompose_agent/node.py:33-47   -> assert_safe_relpath()  (path-jail tại authoring time)
    - decompose_agent/node.py:50-99   -> DoneWhen   (VALUE OBJECT: frozen, validate, from_dict chống forgery)
    - decompose_agent/node.py:102-176 -> Node       (ENTITY: có id, lifecycle, frozen-nhưng-replace, sở hữu
                                                       tuple[DoneWhen], validate invariant ở __post_init__)
    - decompose_agent/node.py:20      -> FORBIDDEN_VERDICT_KEYS (criterion không được mang verdict)
    - decompose_agent/node.py:28-30   -> VALID_STATUSES / VALID_KINDS / REDUCE_OPS

Quan hệ cốt lõi của Lesson 36:
    * DoneWhen = VALUE OBJECT   — một tiêu chí "{check, params, artifact}". Không identity,
      không lifecycle, equality by attribute, validate ở constructor. Replace cả VO, không sửa.
    * Node     = ENTITY         — có `id` bền vững; equality theo id, KHÔNG theo attribute;
      có lifecycle (pending → active → done); SỞ HỮU một tuple các DoneWhen.
      Node frozen nhưng "mutate" trạng thái qua dataclasses.replace() -> Entity mới cùng id.

ĐÃ LƯỢC BỎ so với bản thật (thay bằng fake stdlib tối thiểu):
    - Toàn bộ tầng runner / gate / filesystem (gates.py) -> bỏ; chỉ giữ assert_safe_relpath để
      minh hoạ VO defensive validation.
    - reduce_op / inputs / depth / order / activated_at  -> rút gọn còn vài field cốt lõi.
    - from_dict đầy đủ                                    -> giữ phần chống "verdict forgery" vì nó là
      điểm dạy học (criterion là CÂU HỎI, không phải CÂU TRẢ LỜI).

Chạy: python3 node_donewhen_value_objects.py   (thoát code 0, không traceback)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace, FrozenInstanceError
from pathlib import PurePosixPath
from typing import Any


# ── Tập hằng (giữ tinh thần decompose_agent/node.py:20-30) ────────────────────────
FORBIDDEN_VERDICT_KEYS = frozenset({"verdict", "passed", "status", "score", "done"})
_CRITERION_KEYS = frozenset({"check", "params", "artifact"})
ARTIFACTLESS_CHECKS = frozenset({"all_children_done"})
VALID_STATUSES = frozenset({"pending", "active", "decomposed", "done", "blocked"})
VALID_KINDS = frozenset({"work", "reduce"})


def assert_safe_relpath(path: str) -> str:
    """Distill decompose_agent/node.py:33-47 — VO defensive check tại authoring time.

    Chỉ chấp nhận đường dẫn tương đối, trong workspace. Từ chối absolute, '~', và '..'.
    Đây là validation đặc trưng của Value Object: bất biến enforce NGAY khi construct.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("artifact phải là chuỗi không rỗng")
    p = path.strip()
    if os.path.isabs(p) or p.startswith("~"):
        raise ValueError(f"artifact phải tương đối, trong workspace: {path!r}")
    if ".." in PurePosixPath(p).parts:
        raise ValueError(f"artifact không được thoát workspace ('..'): {path!r}")
    return p


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ VALUE OBJECT — DoneWhen (decompose_agent/node.py:50-99)                    ║
# ║   Một tiêu chí nghiệm thu. Không identity, không lifecycle.                ║
# ║   Equality by attribute. Validate (kể cả path-jail) ngay tại constructor.  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
@dataclass(frozen=True)
class DoneWhen:
    """VALUE OBJECT: một câu hỏi để gate trả lời — '{check, params, artifact}'. Không bao giờ là câu trả lời."""

    check: str
    params: dict[str, Any] = field(default_factory=dict)
    artifact: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.check, str) or not self.check.strip():
            raise ValueError("DoneWhen thiếu 'check' không rỗng")
        if not isinstance(self.params, dict):
            raise ValueError(f"DoneWhen.params phải là mapping, nhận {type(self.params).__name__}")
        if self.artifact is not None:
            # frozen vẫn cho phép normalize trong __post_init__ qua object.__setattr__ (giống bản thật).
            object.__setattr__(self, "artifact", assert_safe_relpath(self.artifact))
        elif self.check not in ARTIFACTLESS_CHECKS:
            raise ValueError(f"DoneWhen {self.check!r} cần một 'artifact'")

    @classmethod
    def from_dict(cls, raw: Any) -> "DoneWhen":
        """Chống 'verdict forgery': criterion KHÔNG được mang field verdict — gate viết verdict, không phải author."""
        if not isinstance(raw, dict):
            raise ValueError(f"DoneWhen phải là mapping, nhận {type(raw).__name__}")
        extra = set(raw) - _CRITERION_KEYS
        forged = extra & FORBIDDEN_VERDICT_KEYS
        if forged:
            raise ValueError(
                f"DoneWhen không được mang field verdict {sorted(forged)} — gate viết verdict, không phải author"
            )
        if extra:
            raise ValueError(f"DoneWhen có field lạ {sorted(extra)}; criterion đúng là {{check, params, artifact}}")
        return cls(check=raw.get("check"), params=dict(raw.get("params") or {}), artifact=raw.get("artifact"))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.check}
        if self.params:
            out["params"] = dict(self.params)
        if self.artifact is not None:
            out["artifact"] = self.artifact
        return out


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ ENTITY — Node (decompose_agent/node.py:102-176)                            ║
# ║   Có `id` bền vững. Lifecycle pending→active→done. Frozen nhưng "mutate"   ║
# ║   trạng thái qua dataclasses.replace() (Navigator sở hữu cây).             ║
# ║   SỞ HỮU một tuple[DoneWhen] — Entity chứa các VO.                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
@dataclass(frozen=True)
class Node:
    """ENTITY: định danh bằng `id`, có lifecycle, sở hữu tuple DoneWhen. Equality THEO id."""

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
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Node.id bắt buộc, phải là chuỗi không rỗng")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"Node.kind phải thuộc {sorted(VALID_KINDS)}, nhận {self.kind!r}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Node.status phải thuộc {sorted(VALID_STATUSES)}, nhận {self.status!r}")
        if not isinstance(self.depends_on, tuple):
            raise ValueError("Node.depends_on phải là tuple")
        if not isinstance(self.done_when, tuple) or not all(isinstance(c, DoneWhen) for c in self.done_when):
            raise ValueError("Node.done_when phải là tuple các DoneWhen")
        if self.max_attempts < 1:
            raise ValueError("Node.max_attempts phải >= 1")
        if self.attempts < 0:
            raise ValueError("Node.attempts phải >= 0")

    # ── Equality by ID (đặc trưng Entity của Lesson 36) ──────────────────────────
    # frozen dataclass mặc định so sánh theo MỌI field; ta override để equality CHỈ theo id,
    # đúng định nghĩa Entity: 2 Node cùng id là cùng một thực thể dù attribute khác nhau.
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Node) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        if not isinstance(d, dict) or "id" not in d:
            raise ValueError("node phải là mapping có 'id'")
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


# ── ĐỐI CHỨNG: Entity bị treat như VO — equality theo attribute (Lesson 36, Vi phạm B) ──
@dataclass
class NodeBadEquality:
    """Anti-pattern: nếu Node so sánh theo attribute (status) thay vì id thì cache/FK vỡ."""

    id: str
    status: str = "pending"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NodeBadEquality) and self.status == other.status  # ✗ SAI

    def __hash__(self) -> int:
        return hash(self.status)


def demo() -> None:
    print("=" * 74)
    print("CASE 02 — Node (Entity) sở hữu DoneWhen (Value Object)")
    print("Distill từ: decompose_agent/node.py:33-176")
    print("=" * 74)

    # ── Bước 1: Dựng các Value Object DoneWhen ────────────────────────────────────
    print("\n[1] Dựng Value Object DoneWhen (mỗi tiêu chí là một câu hỏi cho gate)")
    c1 = DoneWhen(check="file_exists", artifact="out/report.md")
    c2 = DoneWhen(check="json_has_key", params={"key": "total"}, artifact="out/data.json")
    c3 = DoneWhen(check="all_children_done")  # artifactless hợp lệ
    print(f"    c1 = {c1.as_dict()}")
    print(f"    c2 = {c2.as_dict()}")
    print(f"    c3 = {c3.as_dict()}  (all_children_done không cần artifact)")

    # VO: equality by attribute.
    c1_again = DoneWhen(check="file_exists", artifact="out/report.md")
    assert c1 == c1_again, "VO equal khi cùng attribute"
    print("    [assert] DoneWhen(...) == DoneWhen(...) cùng dữ liệu  -> VO equality by attribute  OK")

    # ── Bước 2: Entity Node SỞ HỮU tuple các VO ───────────────────────────────────
    print("\n[2] Dựng Entity Node sở hữu tuple[DoneWhen]")
    node = Node(id="n-1", done_when=(c1, c2, c3))
    print(f"    node.id        = {node.id!r}")
    print(f"    node.status    = {node.status!r}  (đầu lifecycle)")
    print(f"    số tiêu chí    = {len(node.done_when)}  (Entity chứa VO)")
    assert all(isinstance(c, DoneWhen) for c in node.done_when)
    print("    [assert] mọi phần tử done_when là DoneWhen  -> Entity owns VOs  OK")

    # ── Bước 3: Equality theo ID, KHÔNG theo attribute (đặc trưng Entity) ──────────
    print("\n[3] Equality của Entity theo ID, không theo attribute")
    same_id_diff_attr = Node(id="n-1", status="done", notes="khác hẳn node trên")
    diff_id = Node(id="n-2", done_when=(c1, c2, c3))
    assert node == same_id_diff_attr, "cùng id => cùng Entity dù attribute khác"
    assert node != diff_id, "khác id => khác Entity dù cùng done_when"
    print("    node(id=n-1, pending) == node(id=n-1, done)   -> cùng id, cùng Entity  OK")
    print("    node(id=n-1) != node(id=n-2) dù cùng tiêu chí  -> khác id, khác Entity  OK")

    # ── Bước 4: Lifecycle qua dataclasses.replace() (frozen-nhưng-tiến-hoá) ────────
    print("\n[4] Lifecycle: 'mutate' trạng thái bằng dataclasses.replace() -> Entity mới CÙNG id")
    activated = replace(node, status="active", attempts=node.attempts + 1)
    done = replace(activated, status="done")
    print(f"    pending -> {activated.status} -> {done.status}")
    assert node.status == "pending", "bản gốc KHÔNG bị thay đổi (frozen)"
    assert done.id == node.id, "vẫn cùng id => cùng Entity qua các trạng thái"
    assert done == node, "equality theo id: done và node là cùng Entity"
    print("    [assert] node gốc vẫn 'pending', done cùng id  -> tiến hoá bất biến  OK")

    # ── Bước 5: Frozen — không thể gán trực tiếp ──────────────────────────────────
    print("\n[5] Frozen: không thể gán trực tiếp field (phải dùng replace)")
    try:
        node.status = "done"  # type: ignore[misc]
        raise AssertionError("LẼ RA phải raise FrozenInstanceError")
    except FrozenInstanceError:
        print("    [assert] gán node.status -> FrozenInstanceError  (đúng: phải dùng replace)  OK")

    # ── Bước 6: VO validate — path-jail tại constructor ───────────────────────────
    print("\n[6] VO validate (DoneWhen): path-jail chặn artifact nguy hiểm ngay khi construct")
    for bad_art, why in [
        ("/etc/passwd", "absolute path"),
        ("~/secrets", "đường dẫn '~'"),
        ("../../escape.txt", "chứa '..'"),
    ]:
        try:
            DoneWhen(check="file_exists", artifact=bad_art)
            raise AssertionError(f"LẼ RA phải raise: {why}")
        except ValueError:
            print(f"    [assert] artifact={bad_art!r} ({why})  -> ValueError tại __post_init__  OK")

    # ── Bước 7: Chống verdict-forgery (criterion là câu hỏi, không phải câu trả lời) ─
    print("\n[7] DoneWhen.from_dict chặn 'verdict forgery' (criterion không được tự chấm đỗ)")
    try:
        DoneWhen.from_dict({"check": "file_exists", "artifact": "out/x.md", "passed": True})
        raise AssertionError("LẼ RA phải chặn field 'passed'")
    except ValueError as e:
        assert "verdict" in str(e)
        print("    [assert] criterion mang 'passed=True'  -> bị từ chối  OK")

    # ── Bước 8: ĐỐI CHỨNG — Entity equality theo attribute thì hỏng thế nào ────────
    print("\n[8] ĐỐI CHỨNG: nếu Entity so sánh theo attribute thay vì id")
    a = NodeBadEquality(id="n-1", status="pending")
    b = NodeBadEquality(id="n-2", status="pending")  # node KHÁC nhưng cùng status
    assert a == b, "đúng như Lesson 36 cảnh báo: 2 thực thể khác bị coi là 'bằng nhau'"
    cache = {a: "kết quả của n-1"}
    print(f"    cache[a] = {cache[a]!r}; nhưng cache[b] = {cache.get(b)!r}  (b ĐÈ lên a do cùng hash)")
    print("    => Bài học: Entity PHẢI equality by id như Node ở trên, nếu không cache/FK sẽ vỡ")

    print("\n" + "=" * 74)
    print("KẾT LUẬN: Node là ENTITY (id bền vững, lifecycle, equality by id, tiến hoá")
    print("qua replace()). DoneWhen là VALUE OBJECT (frozen, validate, equality by attribute).")
    print("Entity SỞ HỮU các Value Object — đúng quan hệ Lesson 36.")
    print("=" * 74)


if __name__ == "__main__":
    demo()
