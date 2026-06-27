"""
Case 03 — DecompCache: Content-Addressed Flyweight Pool cho kết quả decompose
=============================================================================

Bản DISTILL trung thực từ hex_agent. Nguồn thật được mô phỏng:

  - decompose_agent/store.py:27-32  canonical_spec(node): JSON xác định
                                    (deterministic) của spec phân rã — trích ra
                                    INTRINSIC state (id + done_when + notes).
  - decompose_agent/store.py:35-37  decomp_id(node): sha256(node_id ‖ canonical_spec
                                    ‖ decomposer_version) -> khóa content-addressed.
                                    Cùng input => cùng id.
  - decompose_agent/store.py:62-66  DecompCache.get(decomp_id): đọc kết quả cache
                                    VERBATIM, KHÔNG re-validate. Cache hit => tái dùng.
  - decompose_agent/store.py:68-92  stage()/commit()/_attach(): "staging file IS the
                                    cache"; gắn children và lật parent sang 'decomposed'
                                    bằng dataclasses.replace (node bất biến).
  - decompose_agent/node.py:102-140 Node là @dataclass(frozen=True); chuyển trạng thái
                                    qua replace() chứ không mutate.
  - decompose_agent/node.py:20      FORBIDDEN_VERDICT_KEYS frozenset — chặn forge verdict
                                    ngay lúc construct.

Vai trò Flyweight:
  DecompCache    = Flyweight Factory (cache kết quả theo content address).
  canonical_spec = key function trích intrinsic state (chính cái spec).
  decomp_id      = hash map intrinsic -> khóa cache duy nhất.
  Node (frozen)  = Flyweight instance bất biến.
  extrinsic      = ngữ cảnh node (vị trí trong cây) truyền vào riêng.

Ý nghĩa: decompose 1 task tốn kém (gọi LLM). Gặp lại CÙNG spec lúc retry/resume
-> tái dùng children đã cache, không decompose lại. Node bất biến đảm bảo cache
an toàn khi chia sẻ.

Thay LLM/disk/YAML nặng bằng fake tối thiểu (stdlib hashlib/json + dict in-memory).
Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any

_US = "␟"  # unit separator — giống decompose_agent/store.py:24
DEFAULT_DECOMPOSER_VERSION = 3

# distill decompose_agent/node.py:20 — key dạng verdict bị cấm trên 1 criterion.
FORBIDDEN_VERDICT_KEYS = frozenset({"verdict", "passed", "status", "score", "done"})


# ---------------------------------------------------------------------------
# Frozen records — distill decompose_agent/node.py:50-99, 102-140
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DoneWhen:
    """Một acceptance criterion: câu hỏi để gate trả lời, KHÔNG phải câu trả lời.
    (decompose_agent/node.py:50-69)"""
    check: str
    params: dict[str, Any] = field(default_factory=dict)
    artifact: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DoneWhen":
        # Chặn forge verdict ngay lúc construct (node.py:73-78).
        forged = (set(raw) - {"check", "params", "artifact"}) & FORBIDDEN_VERDICT_KEYS
        if forged:
            raise ValueError(
                f"done_when criterion must not carry a verdict field {sorted(forged)} — "
                "the gate writes the verdict, not the author"
            )
        return cls(check=raw["check"], params=dict(raw.get("params") or {}),
                   artifact=raw.get("artifact"))


@dataclass(frozen=True)
class Node:
    """Một đơn vị công việc. Frozen — chuyển trạng thái qua dataclasses.replace
    (decompose_agent/node.py:102-103)."""
    id: str
    parent: str | None = None
    status: str = "pending"
    done_when: tuple[DoneWhen, ...] = ()
    notes: str = ""
    depth: int = 0
    order: int = 0


# ---------------------------------------------------------------------------
# Cây node tối thiểu (thay tree_state.yaml trên đĩa)
# ---------------------------------------------------------------------------
@dataclass
class Tree:
    nodes: dict[str, Node] = field(default_factory=dict)

    def add(self, node: Node) -> None:
        self.nodes[node.id] = node


# ---------------------------------------------------------------------------
# Key functions — distill decompose_agent/store.py:27-37
# ---------------------------------------------------------------------------
def canonical_spec(node: Node) -> str:
    """JSON xác định của INTRINSIC spec. (store.py:27-32)
    Lưu ý: chỉ gồm id + done_when + notes — KHÔNG gồm extrinsic (depth/order/status)."""
    dw = sorted(
        json.dumps({"check": c.check, "params": c.params, "artifact": c.artifact},
                   sort_keys=True, ensure_ascii=False)
        for c in node.done_when
    )
    return json.dumps({"id": node.id, "done_when": dw, "notes": node.notes},
                      sort_keys=True, ensure_ascii=False)


def decomp_id(node: Node, decomposer_version: int = DEFAULT_DECOMPOSER_VERSION) -> str:
    """Content address: sha256(node_id ‖ canonical_spec ‖ version). (store.py:35-37)"""
    blob = f"{node.id}{_US}{canonical_spec(node)}{_US}{decomposer_version}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# DecompCache — Flyweight Factory content-addressed
#   distill decompose_agent/store.py:53-92 (đĩa/YAML -> dict in-memory)
# ---------------------------------------------------------------------------
class DecompCache:
    def __init__(self) -> None:
        # "staging file IS the cache" -> ở đây là dict: decomp_id -> children spec.
        self._store: dict[str, list[dict]] = {}
        self.decompose_calls = 0  # đếm số lần thực sự "gọi LLM" (cache miss)

    def get(self, did: str) -> list[dict] | None:
        # store.py:62-66 — đọc verbatim, KHÔNG re-validate.
        return self._store.get(did)

    def stage(self, did: str, children: list[dict]) -> None:
        # store.py:68-72 — staging chính là cache.
        self._store[did] = children

    def commit(self, tree: Tree, parent_id: str, children: list[dict], did: str) -> None:
        # store.py:74-78 — stage trước, rồi attach + lật parent, đều bằng replace().
        self.stage(did, children)
        self._attach(tree, parent_id, children)

    def _attach(self, tree: Tree, parent_id: str, children: list[dict]) -> None:
        # store.py:79-85 — dùng dataclasses.replace cho node bất biến.
        parent = tree.nodes[parent_id]
        for i, c in enumerate(children):
            child = Node(
                id=c["id"], parent=parent_id, status="pending",
                done_when=tuple(DoneWhen.from_dict(x) for x in c.get("done_when", ())),
                notes=c.get("notes", ""),
                depth=parent.depth + 1, order=len(tree.nodes) + i,
            )
            tree.nodes[child.id] = child
        tree.nodes[parent_id] = replace(parent, status="decomposed")


# ---------------------------------------------------------------------------
# "Decomposer" giả lập (thay LLM temp-0). Chỉ chạy khi cache MISS.
# ---------------------------------------------------------------------------
def expensive_decompose(cache: DecompCache, node: Node) -> list[dict]:
    """Trả children cho 1 node. Nếu cache hit -> tái dùng; miss -> 'gọi LLM'."""
    did = decomp_id(node)
    cached = cache.get(did)
    if cached is not None:
        return cached  # cache hit -> KHÔNG gọi lại
    cache.decompose_calls += 1
    # Giả lập kết quả phân rã (deterministic theo spec để minh họa).
    children = [
        {"id": f"{node.id}.1", "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
        {"id": f"{node.id}.2", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]},
    ]
    cache.stage(did, children)
    return children


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — DecompCache: Content-Addressed Flyweight Pool")
    print("=" * 72)

    cache = DecompCache()

    print("\n[1] Tạo node với spec (intrinsic: id + done_when + notes).")
    node1 = Node(
        id="root",
        done_when=(DoneWhen(check="build_ok", artifact="dist/app"),),
        notes="ship the app",
        depth=0, order=0,
    )
    print(f"    node1.id={node1.id}  canonical_spec={canonical_spec(node1)[:60]}...")
    print(f"    decomp_id(node1)={decomp_id(node1)[:16]}...")

    print("\n[2] Node 'giống hệt spec' nhưng KHÁC extrinsic (depth/order/status).")
    node2 = Node(
        id="root",  # cùng id + spec
        done_when=(DoneWhen(check="build_ok", artifact="dist/app"),),
        notes="ship the app",
        depth=5, order=99, status="active",  # extrinsic khác hẳn
    )
    print(f"    canonical_spec(node1) == canonical_spec(node2) -> "
          f"{canonical_spec(node1) == canonical_spec(node2)}")
    assert canonical_spec(node1) == canonical_spec(node2), \
        "intrinsic giống => canonical_spec giống (extrinsic bị bỏ qua)"
    print(f"    decomp_id(node1) == decomp_id(node2) -> {decomp_id(node1) == decomp_id(node2)}")
    assert decomp_id(node1) == decomp_id(node2)

    print("\n[3] Decompose node1 lần đầu -> cache MISS -> 'gọi LLM' 1 lần.")
    c1 = expensive_decompose(cache, node1)
    print(f"    children={[c['id'] for c in c1]}  decompose_calls={cache.decompose_calls}")
    assert cache.decompose_calls == 1

    print("\n[4] Decompose node2 (cùng spec, khác extrinsic) -> cache HIT -> KHÔNG gọi lại.")
    c2 = expensive_decompose(cache, node2)
    print(f"    children={[c['id'] for c in c2]}  decompose_calls={cache.decompose_calls}")
    assert cache.decompose_calls == 1, "cache hit: số lần gọi không tăng"
    print(f"    c1 is c2 (cùng object cache) -> {c1 is c2}")
    assert c1 is c2, "content-addressed: cùng id => trả về cùng kết quả cache"

    print("\n[5] Node có spec KHÁC -> decomp_id khác -> cache MISS -> gọi lại.")
    node_other = Node(id="other", done_when=(DoneWhen(check="lint_ok", artifact="x"),))
    print(f"    decomp_id(node_other) != decomp_id(node1) -> "
          f"{decomp_id(node_other) != decomp_id(node1)}")
    assert decomp_id(node_other) != decomp_id(node1)
    expensive_decompose(cache, node_other)
    print(f"    decompose_calls={cache.decompose_calls} (đã tăng lên 2)")
    assert cache.decompose_calls == 2

    print("\n[6] commit(): attach children + lật parent -> 'decomposed' qua replace (frozen).")
    tree = Tree()
    tree.add(node1)
    cache.commit(tree, "root", c1, decomp_id(node1))
    print(f"    parent status sau commit = {tree.nodes['root'].status!r}")
    print(f"    children trong cây = {[n for n in tree.nodes if n != 'root']}")
    assert tree.nodes["root"].status == "decomposed"
    assert "root.1" in tree.nodes and "root.2" in tree.nodes

    print("\n[7] Node BẤT BIẾN: mutate trực tiếp bị chặn -> cache an toàn (thread-safe).")
    mutate_failed = False
    try:
        tree.nodes["root"].status = "hacked"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        mutate_failed = True
    print(f"    Thử node.status='hacked' -> bị chặn? {mutate_failed}")
    assert mutate_failed

    print("\n[8] Chặn forge verdict ngay lúc construct criterion (node.py:73-78).")
    forge_failed = False
    try:
        DoneWhen.from_dict({"check": "x", "artifact": "y", "passed": True})
    except ValueError:
        forge_failed = True
    print(f"    Thử nhét 'passed':True vào criterion -> bị từ chối? {forge_failed}")
    assert forge_failed

    print("\n[9] ĐỐI CHỨNG — KHÔNG content-addressed: mỗi lần đều decompose lại.")
    naive_calls = 0
    for _ in range(3):
        naive_calls += 1  # không có cache key => luôn 'gọi LLM'
    print(f"    Không cache: 3 lần xử lý node giống hệt -> {naive_calls} lần gọi (lãng phí).")
    print("    Có Flyweight cache: chỉ 1 lần gọi cho cùng intrinsic spec.")
    assert naive_calls == 3

    print("\n[KẾT] Content address (hash của intrinsic) = khóa Flyweight. Cùng spec => tái dùng.")
    print("All asserts passed.")


if __name__ == "__main__":
    demo()
