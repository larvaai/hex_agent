"""
Case 01 — Composite: Cây task của decompose_agent (cha-con đệ quy)

Bản DISTILL TRUNG THỰC, chỉ dùng thư viện chuẩn Python 3.14.
KHÔNG import gì từ hex_agent.

Nguồn thật được rút gọn (đã mở & xác minh từng dòng):
  - decompose_agent/tree.py:21-51
        Tree giữ `nodes: dict[str, Node]` và `_children: dict[str, tuple]`
        (index cha -> id các con).
        * children_of(node_id)  (dòng 28-29)  -> interface đồng nhất truy vấn con.
        * rebuild_children()    (dòng 34-41)  -> dựng lại index từ con trỏ parent.
        * next_node()           (dòng 43-51)  -> con trỏ DFS theo (depth, order),
                                                  chỉ chọn node 'pending' mà mọi
                                                  depends_on đã 'done'.
  - decompose_agent/node.py:97-153
        Node (frozen dataclass) = Component. Có parent, depends_on, done_when, status.
        Mỗi node thay thế được cho nhau; client không phân biệt leaf vs composite.
  - decompose_agent/solve.py:262-293
        solve(): vòng lặp `while tree.next_node()` xử lý đồng nhất —
        leaf -> solve_leaf(); khi cần thì _decompose() gắn con (dòng 126-179);
        khi node xong -> _close_done_parents() (dòng 223-247) lan completion
        NGƯỢC LÊN cha, đệ quy bottom-up.

Những gì bị LƯỢC BỎ so với bản thật (để self-contained, vẫn giữ đúng pattern):
  - LLM Worker (worker.propose / worker.decompose) -> thay bằng "kịch bản" cố định.
  - Gate chấm điểm artifact trên đĩa -> thay bằng kiểm tra done_when đơn giản.
  - YAML loader, store two-phase commit, journal, budget -> bỏ.
  - Ràng buộc "decompose phải làm bài toán nhỏ đi" (DEC-D1/D2) -> mô phỏng bằng
    'satisfy_at_depth': dưới một độ sâu nhất định thì leaf giải được luôn.
Giữ NGUYÊN: interface đồng nhất (children_of), con trỏ next_node theo (depth, order),
            cây lớn lên động khi decompose, closure lan ngược lên cha.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT — Node. Một đơn vị công việc. Có thể là leaf hoặc composite.
# (distill: decompose_agent/node.py:97-153)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Node:
    """Frozen như bản thật: status đổi qua dataclasses.replace, Tree làm chủ.

    'done_when' = tiêu chí nghiệm thu (số tiêu chí dwc quyết định leaf hay phải tách).
    Một node KHÔNG biết nó là leaf hay composite — điều đó do cấu trúc cây quyết định.
    """
    id: str
    parent: str | None = None
    status: str = "pending"          # pending | active | decomposed | done | blocked
    depends_on: tuple[str, ...] = ()
    done_when: tuple[str, ...] = ()  # rút gọn: danh sách tên tiêu chí
    depth: int = 0
    order: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Tập node sống. Tree làm chủ cấu trúc; transition replace node frozen.
# (distill: decompose_agent/tree.py:21-51)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Tree:
    nodes: dict[str, Node]
    _children: dict[str, tuple[str, ...]]

    # --- interface ĐỒNG NHẤT: hỏi con của bất kỳ node nào, leaf hay composite ---
    def children_of(self, node_id: str) -> tuple[str, ...]:   # tree.py:28-29
        return self._children.get(node_id, ())

    def set_status(self, node_id: str, status: str) -> None:  # tree.py:31-32
        self.nodes[node_id] = replace(self.nodes[node_id], status=status)

    def rebuild_children(self) -> None:                       # tree.py:34-41
        """Dựng lại index cha->con từ con trỏ parent (sau khi decompose gắn con mới)."""
        children: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for node in self.nodes.values():
            if node.parent is not None and node.parent in children:
                children[node.parent].append(node.id)
        self._children = {k: tuple(v) for k, v in children.items()}

    def next_node(self) -> Node | None:                       # tree.py:43-51
        """Con trỏ: node 'pending' trái nhất theo (depth, order) mà mọi dep đã done."""
        ready = [
            n for n in self.nodes.values()
            if n.status == "pending"
            and all(self.nodes[dep].status == "done" for dep in n.depends_on)
        ]
        if not ready:
            return None
        return min(ready, key=lambda n: (n.depth, n.order))


def build_tree(node_list: list[Node]) -> Tree:
    """Rút gọn của load_tree: gán order theo thứ tự, gán depth theo chuỗi parent,
    rồi dựng index con. (distill: decompose_agent/tree.py:99-127)"""
    nodes = {n.id: replace(n, order=i) for i, n in enumerate(node_list)}
    # gán depth từ chuỗi parent
    for nid in nodes:
        depth, cur = 0, nid
        while nodes[cur].parent is not None:
            cur = nodes[cur].parent
            depth += 1
        nodes[nid] = replace(nodes[nid], depth=depth)
    tree = Tree(nodes=nodes, _children={})
    tree.rebuild_children()
    return tree


# ─────────────────────────────────────────────────────────────────────────────
# WORKER (kịch bản) — thay LLM. Quyết định một leaf có giải được không, và khi
# cần tách thì sinh con gì. Bản thật: decompose_agent/worker.py + accept.py.
# Ràng buộc THẬT mô phỏng: phải tách nhỏ tới khi đủ "đơn giản" mới giải được.
# ─────────────────────────────────────────────────────────────────────────────
class ScriptedWorker:
    def __init__(self, satisfy_at_depth: int) -> None:
        # leaf giải được NGAY nếu depth >= ngưỡng (đã đủ nhỏ); ngược lại phải decompose.
        self.satisfy_at_depth = satisfy_at_depth
        self._counter = 0

    def can_solve_leaf(self, node: Node) -> bool:
        return node.depth >= self.satisfy_at_depth

    def decompose(self, node: Node) -> list[Node]:
        """Sinh 2 con cho node — bài toán nhỏ đi 1 cấp (depth + 1)."""
        out = []
        for k in (1, 2):
            self._counter += 1
            cid = f"{node.id}.{k}"
            out.append(Node(id=cid, parent=node.id, status="pending",
                            done_when=(f"crit_{cid}",)))
        return out


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER + closure đệ quy.  (distill: decompose_agent/solve.py)
# ─────────────────────────────────────────────────────────────────────────────
def _solve_leaf(tree: Tree, nid: str, worker: ScriptedWorker) -> str:
    """Thử giải leaf. Trả 'done' nếu được, 'needs_decompose' nếu phải tách.
    (rút gọn của solve_leaf, solve.py:80-121)"""
    tree.set_status(nid, "active")
    if worker.can_solve_leaf(tree.nodes[nid]):
        tree.set_status(nid, "done")
        return "done"
    return "needs_decompose"


def _decompose(tree: Tree, nid: str, worker: ScriptedWorker) -> None:
    """Tách node thành con & gắn vào cây. Cây LỚN LÊN ở đây.
    (rút gọn của _decompose + cache.commit, solve.py:126-179)"""
    children = worker.decompose(tree.nodes[nid])
    for child in children:
        # gán depth = depth cha + 1 (loader thật làm điều này khi attach)
        tree.nodes[child.id] = replace(child, depth=tree.nodes[nid].depth + 1,
                                       order=len(tree.nodes))
    tree.set_status(nid, "decomposed")
    tree.rebuild_children()   # index cha->con cập nhật lại từ con trỏ parent


def _close_done_parents(tree: Tree) -> None:
    """Lan completion NGƯỢC LÊN: node 'decomposed' mà MỌI con 'done' -> 'done'.
    Lặp tới khi không còn thay đổi (đệ quy bottom-up).
    (rút gọn của _close_done_parents, solve.py:223-247)"""
    changed = True
    while changed:
        changed = False
        for nid, node in list(tree.nodes.items()):
            if node.status != "decomposed":
                continue
            kids = tree.children_of(nid)
            statuses = [tree.nodes[c].status for c in kids]
            # F1: 0 con -> False; phải có >=1 con và TẤT CẢ done
            if len(statuses) >= 1 and all(s == "done" for s in statuses):
                tree.set_status(nid, "done")
                changed = True


def solve(tree: Tree, worker: ScriptedWorker) -> list[tuple[str, str]]:
    """Vòng lặp driver. Con trỏ next_node() đi cây ĐỒNG NHẤT — không phân biệt
    leaf/composite. (rút gọn của solve, solve.py:262-298)"""
    log: list[tuple[str, str]] = []
    while (node := tree.next_node()) is not None:
        nid = node.id
        outcome = _solve_leaf(tree, nid, worker)
        log.append((nid, outcome))
        if outcome == "done":
            _close_done_parents(tree)
            continue
        if outcome == "needs_decompose":
            _decompose(tree, nid, worker)
            log.append((nid, "decomposed"))
            continue
    _close_done_parents(tree)
    return log


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG: KHÔNG dùng Composite -> đệ quy thủ công theo type, dễ quên cấp.
# ─────────────────────────────────────────────────────────────────────────────
def naive_all_done_BAD(tree: Tree, nid: str) -> bool:
    """Anti-pattern: kiểm tra "cả cây xong" bằng if-else theo độ sâu, HARD-CODE 2 cấp.
    Bug: chỉ nhìn con trực tiếp, KHÔNG đệ quy xuống cháu -> sai khi cây sâu hơn."""
    kids = tree.children_of(nid)
    if not kids:                                  # coi như leaf
        return tree.nodes[nid].status == "done"
    # CHỈ xét con trực tiếp, quên đệ quy xuống cấp dưới -> bug ngầm
    return all(tree.nodes[c].status == "done" for c in kids)


def composite_all_done_GOOD(tree: Tree, nid: str) -> bool:
    """Composite đúng: đệ quy ĐỒNG NHẤT, một định nghĩa đúng cho mọi cấp lồng."""
    kids = tree.children_of(nid)
    if not kids:
        return tree.nodes[nid].status == "done"
    return all(composite_all_done_GOOD(tree, c) for c in kids)


# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("CASE 01 — Composite: cây task của decompose_agent")
    print("=" * 70)

    # Một node gốc 'root' với 2 tiêu chí (dwc>1 => không phải leaf nguyên tử).
    root = Node(id="root", parent=None, status="pending",
                done_when=("crit_a", "crit_b"))
    tree = build_tree([root])

    # Worker chỉ giải được leaf khi depth >= 2 => root phải tách 2 lần.
    worker = ScriptedWorker(satisfy_at_depth=2)

    print("\n[1] Cây ban đầu — chỉ có gốc 'root' (depth 0), trạng thái pending.")
    print("    children_of('root') =", tree.children_of("root"))
    print("    next_node() =", tree.next_node().id, "  <- con trỏ chọn node pending")

    print("\n[2] Chạy solve(). Con trỏ đi cây ĐỒNG NHẤT, không phân biệt leaf/composite.")
    log = solve(tree, worker)
    for nid, outcome in log:
        depth = tree.nodes[nid].depth
        print(f"    {'  ' * depth}- {nid:<10} -> {outcome}")

    print("\n[3] Cây SAU khi chạy — đã lớn lên động qua 2 lần decompose:")
    for nid in sorted(tree.nodes, key=lambda x: (tree.nodes[x].depth, tree.nodes[x].order)):
        n = tree.nodes[nid]
        kids = tree.children_of(nid)
        tag = "LEAF" if not kids else "COMPOSITE"
        print(f"    {'  ' * n.depth}{nid:<12} [{n.status:<10}] {tag}"
              + (f"  con={list(kids)}" if kids else ""))

    print("\n[4] Closure đã lan NGƯỢC LÊN: mọi con done => cha done => gốc done.")
    print("    root.status =", tree.nodes["root"].status)

    # ── ĐỐI CHỨNG: dựng cây sâu 3 cấp, một cháu CHƯA done ──
    print("\n[5] Đối chứng — vì sao đệ quy thủ công theo type dễ sai:")
    # A.1 bị đánh 'done' ở cấp của nó, nhưng cháu A.1.y vẫn pending => cây CHƯA xong.
    deep = build_tree([
        Node(id="A", parent=None, status="decomposed"),
        Node(id="A.1", parent="A", status="done"),       # con trực tiếp: done
        Node(id="A.1.x", parent="A.1", status="done"),
        Node(id="A.1.y", parent="A.1", status="pending"),  # cháu CHƯA done
    ])
    bad = naive_all_done_BAD(deep, "A")
    good = composite_all_done_GOOD(deep, "A")
    print(f"    naive_all_done_BAD('A')       = {bad}    <- SAI: chỉ nhìn con trực tiếp 'A.1' (done)")
    print(f"    composite_all_done_GOOD('A')  = {good}   <- ĐÚNG: đệ quy tới cháu 'A.1.y' (pending)")

    # ── ASSERT chứng minh bất biến của Composite ──
    # 1) gốc đóng được nhờ closure lan ngược lên.
    assert tree.nodes["root"].status == "done", "closure phải lan completion lên gốc"
    # 2) mọi leaf đều done, mọi composite đều done (đệ quy đồng nhất).
    for nid, n in tree.nodes.items():
        if tree.children_of(nid):
            assert n.status == "done", f"composite {nid} phải done khi mọi con done"
            assert composite_all_done_GOOD(tree, nid), f"{nid} chưa đệ quy-done"
        else:
            assert n.status == "done", f"leaf {nid} phải done"
    # 3) bất biến cấu trúc: con trỏ parent và index _children khớp nhau.
    for nid, n in tree.nodes.items():
        if n.parent is not None:
            assert nid in tree.children_of(n.parent), \
                f"{nid} phải nằm trong children_of({n.parent})"
    # 4) đối chứng: naive sai, composite đúng — chứng minh giá trị của pattern.
    assert bad is True and good is False, "đệ quy thủ công bỏ sót cấp -> kết quả sai"

    print("\n[6] PASS — mọi assert đúng: closure đệ quy, index cha-con nhất quán,")
    print("    và đệ quy đồng nhất của Composite cho kết quả đúng ở mọi độ sâu.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
