"""
State Pattern — Case 01: Task Decomposition Navigator (Node state machine).

Bản DISTILL TRUNG THỰC từ hex_agent. Nguồn thật:
  - decompose_agent/node.py:28       — VALID_STATUSES frozenset (tập state hữu hạn:
                                       pending, active, decomposed, done, blocked)
  - decompose_agent/node.py:102-140  — Node là frozen dataclass; status là field;
                                       transition đi qua dataclasses.replace, không mutate;
                                       guard status ở __post_init__ (l.127-128).
  - decompose_agent/tree.py:31-32    — Tree.set_status() đóng gói transition (replace node).
  - decompose_agent/tree.py:43-51    — Tree.next_node() là cursor: chọn node pending kế
                                       tiếp có mọi depends_on == done (logic state machine
                                       thuần, không if/elif rải rác).
  - decompose_agent/solve.py:80-121  — solve_leaf(): pending→active (l.83), rồi →done (l.116)
                                       hoặc →blocked (l.92,98,103,120).
  - decompose_agent/solve.py:204-224 — solve_reduce(): active (l.207) → done (l.222)/blocked.
  - decompose_agent/solve.py:229-253 — _close_done_parents(): decomposed→done (l.245) hoặc
                                       decomposed→blocked (l.249) tuỳ trạng thái con.
  - decompose_agent/solve.py:258-304 — solve(): vòng lặp Navigator. outcome.status quyết định
                                       nhánh xử lý tiếp theo (l.282,288,296) — behavior đổi
                                       theo state.

Pattern: State (Behavioral).
  - Context: Tree (giữ tập node, delegate việc chọn node kế tiếp qua next_node()) và mỗi
    Node (context của một task, mang status hiện tại).
  - State: 5 giá trị status {pending, active, decomposed, done, blocked} — mỗi state quy
    định hành vi hợp lệ kế tiếp.
  - Transition: state-driven (solver set_status theo kết quả gate) + context-driven
    (_close_done_parents kiểm tra status các con để đóng parent).

CHỈ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent / bên thứ ba.
Hạ tầng nặng bị thay bằng fake tối thiểu:
  - Worker (LLM 35B) -> MockWorker (kịch bản done/decompose cố định).
  - Gate trên đĩa (đọc artifact thật) -> hàm thuần dựa vào kịch bản worker.
"""
from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field, replace

# ── Tập state hữu hạn — distill từ node.py:28 ────────────────────────────────
# Mọi status phải thuộc tập này; một Node với status lạ không thể tồn tại.
VALID_STATUSES = frozenset({"pending", "active", "decomposed", "done", "blocked"})
VALID_KINDS = frozenset({"work", "reduce"})


# ── Node — frozen dataclass (distill từ node.py:102-140) ─────────────────────
@dataclass(frozen=True)
class Node:
    """Một đơn vị công việc. Frozen: status transition phải đi qua replace().

    'frozen' ép một bất biến của State pattern: KHÔNG ai mutate status tại chỗ —
    mọi transition là một thao tác có chủ đích (Tree.set_status), nên dễ audit.
    """

    id: str
    parent: str | None = None
    kind: str = "work"
    status: str = "pending"
    depends_on: tuple[str, ...] = ()
    # dwc>1 (nhiều tiêu chí) thì leaf fail được phép decompose; dwc<=1 thì block.
    done_when_count: int = 1
    depth: int = 0
    order: int = 0

    def __post_init__(self) -> None:
        # Guard tại construction: state lạ -> object không thể ra đời (node.py:127-128).
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Node.status phải thuộc {sorted(VALID_STATUSES)}, gặp {self.status!r}")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"Node.kind phải thuộc {sorted(VALID_KINDS)}, gặp {self.kind!r}")


# ── Tree — Context giữ tập node, làm cursor (distill từ tree.py) ──────────────
@dataclass
class Tree:
    """Tập node sống. Navigator sở hữu nó; transition thay node frozen bằng replace."""

    nodes: dict[str, Node]
    _children: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rebuild_children()

    def children_of(self, node_id: str) -> tuple[str, ...]:
        return self._children.get(node_id, ())

    def set_status(self, node_id: str, status: str) -> None:
        """Đóng gói transition: thay node bằng bản sao có status mới (tree.py:31-32)."""
        self.nodes[node_id] = replace(self.nodes[node_id], status=status)

    def rebuild_children(self) -> None:
        children: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for node in self.nodes.values():
            if node.parent is not None and node.parent in children:
                children[node.parent].append(node.id)
        self._children = {k: tuple(v) for k, v in children.items()}

    def next_node(self) -> Node | None:
        """Cursor: node pending trái-nhất có mọi dependency đã done (tree.py:43-51).

        Đây là logic state-machine thuần: KHÔNG cần if/elif liệt kê từng state —
        chỉ một biểu thức lọc trên field status.
        """
        ready = [
            n for n in self.nodes.values()
            if n.status == "pending"
            and all(self.nodes[dep].status == "done" for dep in n.depends_on)
        ]
        if not ready:
            return None
        return min(ready, key=lambda n: (n.depth, n.order))


# ── Worker fake (thay LLM 35B) ────────────────────────────────────────────────
class MockWorker:
    """Thay decompose_agent/worker.py. Kịch bản cố định theo node id:

      - "done":     leaf vượt gate ngay -> done.
      - "decompose": leaf fail K lần -> needs_decompose; sau đó các con được thêm vào.
      - "block":    leaf fail và dwc<=1 -> không decompose được -> blocked.
    """

    def __init__(self, plan: dict[str, str], children: dict[str, list[Node]]) -> None:
        self._plan = plan                    # node_id -> "done" | "decompose" | "block"
        self._children = children            # parent_id -> danh sách con sinh ra khi decompose

    def attempt_leaf(self, node: Node) -> bool:
        """True nếu leaf vượt gate ngay (mô phỏng run_checks().ok)."""
        return self._plan.get(node.id) == "done"

    def decompose(self, node: Node) -> list[Node]:
        return list(self._children.get(node.id, ()))


# ── Navigator (distill solve.py) ──────────────────────────────────────────────
Outcome = namedtuple("Outcome", "node status reason")


def solve_leaf(tree: Tree, node_id: str, worker: MockWorker, trace: list[str]) -> Outcome:
    """pending -> active -> done | needs_decompose | blocked (solve.py:80-121)."""
    node = tree.nodes[node_id]
    tree.set_status(node_id, "active")                       # transition #1 (solve.py:83)
    trace.append(f"  {node_id}: pending -> active")
    if worker.attempt_leaf(tree.nodes[node_id]):
        tree.set_status(node_id, "done")                    # transition #2a (solve.py:116)
        trace.append(f"  {node_id}: active -> done (gate PASS)")
        return Outcome(node_id, "done", "")
    # leaf fail: nhiều tiêu chí -> được phép decompose; một tiêu chí -> block.
    if tree.nodes[node_id].done_when_count > 1:
        trace.append(f"  {node_id}: active -> (fail) needs_decompose")
        return Outcome(node_id, "needs_decompose", "")
    tree.set_status(node_id, "blocked")                      # transition #2b (solve.py:120)
    trace.append(f"  {node_id}: active -> blocked (UNSOLVABLE_LEAF)")
    return Outcome(node_id, "blocked", "UNSOLVABLE_LEAF")


def solve_reduce(tree: Tree, node_id: str, trace: list[str]) -> Outcome:
    """reduce node chạy bằng code, không LLM: active -> done/blocked (solve.py:204-224)."""
    tree.set_status(node_id, "active")
    trace.append(f"  {node_id}: pending -> active (reduce)")
    # Reduce chỉ done khi mọi sibling depends_on đã done (đã đảm bảo bởi next_node()).
    tree.set_status(node_id, "done")
    trace.append(f"  {node_id}: active -> done (compose PASS)")
    return Outcome(node_id, "done", "")


def _decompose(tree: Tree, node_id: str, worker: MockWorker, trace: list[str]) -> Outcome:
    """needs_decompose: gắn con pending, parent -> decomposed (solve.py:132-179)."""
    children = worker.decompose(tree.nodes[node_id])
    if not children:
        tree.set_status(node_id, "blocked")
        trace.append(f"  {node_id}: -> blocked (DECOMP_EMPTY)")
        return Outcome(node_id, "blocked", "DECOMP_EMPTY")
    for child in children:
        tree.nodes[child.id] = child                        # con mới ở trạng thái pending
    tree.rebuild_children()
    tree.set_status(node_id, "decomposed")                  # transition: active -> decomposed
    trace.append(f"  {node_id}: -> decomposed, sinh {[c.id for c in children]}")
    return Outcome(node_id, "decomposed", "")


def _propagate_block(tree: Tree, node_id: str, trace: list[str]) -> None:
    """Node blocked làm blocked các tổ tiên decomposed (solve.py:68-75)."""
    child = node_id
    parent_id = tree.nodes[child].parent
    while parent_id is not None and parent_id in tree.nodes and tree.nodes[parent_id].status == "decomposed":
        tree.set_status(parent_id, "blocked")
        trace.append(f"  {parent_id}: decomposed -> blocked (CHILD_BLOCKED:{child})")
        child, parent_id = parent_id, tree.nodes[parent_id].parent


def _close_done_parents(tree: Tree, trace: list[str]) -> Outcome | None:
    """Context-driven transition: parent decomposed -> done khi mọi con done,
    hoặc -> blocked nếu có con blocked (solve.py:229-253)."""
    changed = True
    compose_fail: Outcome | None = None
    while changed:
        changed = False
        for nid, node in list(tree.nodes.items()):
            if node.status != "decomposed":
                continue
            statuses = [tree.nodes[c].status for c in tree.children_of(nid)]
            if any(s not in ("done", "blocked") for s in statuses):
                continue                                    # con chưa settle hết
            if any(s == "blocked" for s in statuses):
                continue                                    # block đã được _propagate_block lo
            all_done = len(statuses) >= 1 and all(s == "done" for s in statuses)  # F1
            if all_done:
                tree.set_status(nid, "done")                # transition (solve.py:245)
                trace.append(f"  {nid}: decomposed -> done (all_children_done)")
                changed = True
    return compose_fail


def solve(tree: Tree, worker: MockWorker) -> tuple[list[Outcome], Outcome | None, list[str]]:
    """Driver loop (solve.py:258-304). outcome.status quyết định nhánh tiếp theo."""
    trace: list[str] = []
    outcomes: list[Outcome] = []
    blocked: Outcome | None = None
    step = 0
    while (node := tree.next_node()) is not None:
        step += 1
        nid = node.id
        trace.append(f"[bước {step}] cursor chọn {nid} (kind={node.kind}, depth={node.depth})")
        if node.kind == "reduce":
            outcome = solve_reduce(tree, nid, trace)
        else:
            outcome = solve_leaf(tree, nid, worker, trace)
        outcomes.append(outcome)

        # ── behavior thay đổi theo state kết quả — KHÔNG monolithic if/elif theo state node ──
        if outcome.status == "done":
            _close_done_parents(tree, trace)
            continue
        if outcome.status == "needs_decompose":
            d = _decompose(tree, nid, worker, trace)
            outcomes.append(d)
            if d.status == "blocked":
                _propagate_block(tree, nid, trace)
                blocked = d
                break
            continue
        # leaf blocked
        _propagate_block(tree, nid, trace)
        blocked = outcome
        break
    _close_done_parents(tree, trace)
    return outcomes, blocked, trace


# ── Đối chứng: KHÔNG dùng pattern (status là str tự do, if/elif rải rác) ──────
def naive_advance(status: str, gate_ok: bool) -> str:
    """Anti-pattern: tự do gán chuỗi status, không tập hữu hạn, không guard.

    Mỗi nơi xử lý phải lặp lại if/elif; lỡ tay gán "complete" thay "done" thì
    next_node() (so sánh == "done") sẽ bỏ sót, treo cả cây mà không ai báo lỗi.
    """
    if status == "pending":
        return "active"
    if status == "active":
        return "done" if gate_ok else "blocked"
    return status


# ── Demo ──────────────────────────────────────────────────────────────────────
def _build_tree() -> Tree:
    """Cây: root(decompose) -> [a(done), b(done)]; sau khi cả 2 done, root tự đóng."""
    root = Node(id="root", kind="work", done_when_count=2, depth=0, order=0)
    return Tree(nodes={"root": root})


def demo() -> None:
    print("=" * 70)
    print("CASE 01 — Task Decomposition Navigator: Node state machine")
    print("State: pending -> active -> {done | decomposed | blocked}")
    print("=" * 70)

    # Kịch bản: root fail leaf (dwc=2) -> decompose thành a, b; cả hai done;
    # _close_done_parents đóng root: decomposed -> done.
    children = {
        "root": [
            Node(id="a", parent="root", kind="work", done_when_count=1, depth=1, order=1),
            Node(id="b", parent="root", kind="work", done_when_count=1, depth=1, order=2),
        ]
    }
    plan = {"root": "decompose", "a": "done", "b": "done"}
    worker = MockWorker(plan, children)
    tree = _build_tree()

    print("\n--- Vòng lặp Navigator (state-driven transitions) ---")
    outcomes, blocked, trace = solve(tree, worker)
    for line in trace:
        print(line)

    print("\n--- Trạng thái cuối từng node ---")
    for nid in ("root", "a", "b"):
        print(f"  {nid}: {tree.nodes[nid].status}")

    # ── ASSERT bất biến của pattern ──
    # 1) Mọi status cuối phải nằm trong tập hữu hạn (không có state "rò rỉ").
    for n in tree.nodes.values():
        assert n.status in VALID_STATUSES, f"state lạ: {n.status}"
    # 2) Hai con done -> root đóng thành done (decomposed -> done).
    assert tree.nodes["a"].status == "done"
    assert tree.nodes["b"].status == "done"
    assert tree.nodes["root"].status == "done", "root phải đóng khi mọi con done"
    assert blocked is None, "không node nào bị block trong kịch bản happy-path"
    print("\n[assert] OK: tập state đóng kín + cascade decomposed->done đúng.")

    # ── Kịch bản block: một con UNSOLVABLE -> propagate lên root ──
    print("\n--- Kịch bản block: con 'b' không giải được (dwc=1) ---")
    plan2 = {"root": "decompose", "a": "done", "b": "block"}
    tree2 = _build_tree()
    _, blocked2, trace2 = solve(tree2, MockWorker(plan2, children))
    for line in trace2:
        print(line)
    print("  root:", tree2.nodes["root"].status, "| a:", tree2.nodes["a"].status,
          "| b:", tree2.nodes["b"].status)
    assert tree2.nodes["b"].status == "blocked"
    assert tree2.nodes["root"].status == "blocked", "block phải lan lên parent decomposed"
    print("[assert] OK: block lan từ con lên tổ tiên decomposed (_propagate_block).")

    # ── Đối chứng: anti-pattern dễ vỡ vì không có tập state hữu hạn ──
    print("\n--- Đối chứng: naive_advance gán chuỗi tự do (KHÔNG pattern) ---")
    s = naive_advance("active", gate_ok=True)
    print(f"  naive trả về: {s!r}")
    # Giả sử lập trình viên gõ nhầm 'complete' ở một nhánh khác:
    typo = "complete"
    in_finite_set = typo in VALID_STATUSES
    print(f"  nếu ai đó gán {typo!r}: thuộc tập state hữu hạn? {in_finite_set}")
    assert not in_finite_set, "minh hoạ: chuỗi tự do lọt ra ngoài tập state -> treo cây ngầm"
    print("  => Node frozen + VALID_STATUSES chặn lỗi này NGAY tại construction.")

    print("\nKẾT LUẬN: status field + tập hữu hạn + set_status đóng gói transition =")
    print("State pattern. Cursor next_node() đọc status, không if/elif rải rác.")


if __name__ == "__main__":
    demo()
