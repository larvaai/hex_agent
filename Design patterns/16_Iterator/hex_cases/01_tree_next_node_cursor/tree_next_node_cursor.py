#!/usr/bin/env python3
"""
Tree Cursor Iterator — next_node() cho DAG traversal (distill từ hex_agent).

NGUỒN THẬT distill từ:
  - decompose_agent/tree.py:43-51   -> Tree.next_node(): trả node 'pending' kế tiếp,
                                       theo (depth, order), với mọi depends_on đã 'done'.
                                       Đây là CURSOR thật sự của DAG.
  - decompose_agent/tree.py:31-32   -> Tree.set_status(): chuyển trạng thái node (pending -> done).
  - decompose_agent/solve.py:262-293-> Vòng solve(): while (node := tree.next_node()) is not None.
                                       Client kéo cursor đến khi None, KHÔNG biết logic topo-sort.

Ý TƯỞNG: Iterator đóng gói _cách duyệt_ một DAG task tree (respecting depends_on)
sao cho client (solve loop) chỉ cần gọi next_node() lặp đi lặp lại đến khi None —
giống V1 visual cortex chỉ xử lý fixation hiện tại, không cần biết SC chọn nó thế nào.

Bản distill này:
  - GIỮ NGUYÊN vai trò pattern: Aggregate (Tree) sở hữu nodes; Iterator (next_node)
    giữ state cursor qua STATUS của node; Client (solve loop) duyệt mà không biết cấu trúc.
  - GIỮ NGUYÊN bất biến: chỉ trả node mà mọi dependency đã done; thứ tự (depth, order).
  - LƯỢC BỎ: load YAML, validate referential integrity / acyclicity, LLM worker,
    journal/cache, budget. Thay bằng tree dựng tay trong code và "worker" giả lập
    chỉ đánh dấu node done.

Chạy: python3 tree_next_node_cursor.py   (chỉ dùng stdlib, thoát code 0)
"""
from __future__ import annotations

from dataclasses import dataclass, replace


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE — Node + Tree (rút gọn từ decompose_agent/node.py + tree.py)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Node:
    """Một task trong DAG. frozen=True: status đổi bằng cách replace() ra node mới,
    giống node.py thật (immutable, transition tạo bản sao)."""
    id: str
    parent: str | None = None
    depends_on: tuple[str, ...] = ()
    depth: int = 0
    order: int = 0
    status: str = "pending"  # pending -> done


@dataclass
class Tree:
    """The live node set — Aggregate. Sở hữu nodes; KHÔNG lộ cách duyệt ra ngoài."""
    nodes: dict[str, Node]

    def set_status(self, node_id: str, status: str) -> None:
        # tree.py:31-32 — transition thay frozen node bằng bản replace().
        self.nodes[node_id] = replace(self.nodes[node_id], status=status)

    def children_of(self, node_id: str) -> tuple[str, ...]:
        # tree.py:28-29 — tiện ích duyệt con (không phải cursor chính).
        return tuple(n.id for n in self.nodes.values() if n.parent == node_id)

    # ── ITERATOR — cursor thật sự của DAG (tree.py:43-51) ────────────────────
    def next_node(self) -> Node | None:
        """Trả node 'pending' kế tiếp mà MỌI depends_on đã 'done', chọn theo
        (depth, order). Toàn bộ logic topo-order nằm Ở ĐÂY — client không thấy.

        State cursor = chính các STATUS trong nodes (không có biến index riêng).
        Mỗi lần status đổi (done), tập 'ready' đổi theo → cursor tự tiến."""
        ready = [
            n for n in self.nodes.values()
            if n.status == "pending"
            and all(self.nodes[dep].status == "done" for dep in n.depends_on)
        ]
        if not ready:
            return None
        return min(ready, key=lambda n: (n.depth, n.order))


# ─────────────────────────────────────────────────────────────────────────────
# Một "worker" giả lập — thay cho LLM worker thật trong solve_leaf()
# ─────────────────────────────────────────────────────────────────────────────
def fake_solve(node: Node) -> None:
    """Trong bản thật, worker.propose() gọi LLM rồi gate kiểm tra. Ở đây ta chỉ
    in ra là đã 'làm xong' node. Đối tượng của case là TRAVERSAL, không phải worker."""
    print(f"    [worker] giải xong node {node.id!r} (depth={node.depth}, order={node.order})")


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — vòng solve() (rút gọn từ solve.py:262-293)
# ─────────────────────────────────────────────────────────────────────────────
def solve(tree: Tree) -> list[str]:
    """Client KHÔNG biết DAG được duyệt thế nào. Chỉ làm: lấy node kế tiếp, giải,
    đánh done, lặp lại. Đây chính là 'while (node := tree.next_node()) is not None'."""
    visited_order: list[str] = []
    while (node := tree.next_node()) is not None:
        fake_solve(node)
        tree.set_status(node.id, "done")  # cursor tiến nhờ status đổi
        visited_order.append(node.id)
    return visited_order


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — khi client TỰ duyệt mà không có cursor che giấu logic
# ─────────────────────────────────────────────────────────────────────────────
def naive_iterate_wrong(tree: Tree) -> list[str]:
    """Client tự duyệt bằng cách lặp dict.values() theo thứ tự chèn — KHÔNG tôn
    trọng depends_on. Đây là điều xảy ra nếu KHÔNG có Iterator: client phải tự
    biết cấu trúc, và rất dễ 'climb early' (giải node trước khi dependency xong)."""
    return [n.id for n in tree.nodes.values()]  # bỏ qua mọi ràng buộc depends_on


# ─────────────────────────────────────────────────────────────────────────────
def build_tree() -> Tree:
    """root có 3 con: c0, c1, c2. c1 PHỤ THUỘC c0 (c0 phải done trước c1).
    Thứ tự chèn cố tình ĐẶT c1 TRƯỚC c0 để chứng minh cursor không đi theo thứ
    tự chèn mà theo (depth, order) + ràng buộc depends_on."""
    nodes = [
        Node(id="root", depth=0, order=0),
        Node(id="c1", parent="root", depth=1, order=1, depends_on=("c0",)),  # cố tình đặt trước c0
        Node(id="c0", parent="root", depth=1, order=2),
        Node(id="c2", parent="root", depth=1, order=3),
    ]
    return Tree(nodes={n.id: n for n in nodes})


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Tree Cursor Iterator: next_node() cho DAG traversal")
    print("=" * 72)

    print("\n[1] Cấu trúc tree (Aggregate sở hữu nodes):")
    print("    root")
    print("    ├─ c0            (order=2, không phụ thuộc gì)")
    print("    ├─ c1            (order=1, depends_on=c0)  <- chèn TRƯỚC c0 trong dict")
    print("    └─ c2            (order=3, không phụ thuộc gì)")

    print("\n[2] ĐỐI CHỨNG — client tự duyệt dict.values() (KHÔNG dùng cursor):")
    tree_wrong = build_tree()
    wrong = naive_iterate_wrong(tree_wrong)
    print(f"    Thứ tự duyệt 'ngây thơ': {wrong}")
    # root xuất hiện trước c0/c1/c2 (ổn), nhưng c1 đứng TRƯỚC c0 -> sai topo!
    pos_c0 = wrong.index("c0")
    pos_c1 = wrong.index("c1")
    print(f"    -> c1 ở vị trí {pos_c1}, c0 ở vị trí {pos_c0}: c1 bị duyệt TRƯỚC c0 mà nó phụ thuộc!")
    assert pos_c1 < pos_c0, "Đối chứng: cách ngây thơ vi phạm depends_on (climb early)"
    print("    => Không có Iterator, client phải tự sort topo — dễ sai, lặp code khắp nơi.")

    print("\n[3] DÙNG Iterator — next_node() là cursor, client chỉ kéo đến khi None:")
    tree = build_tree()
    order = solve(tree)
    print(f"\n    Thứ tự cursor trả về: {order}")

    print("\n[4] Kiểm tra bất biến (invariants) của Iterator:")
    # Bất biến 1: mọi node đều được duyệt đúng 1 lần.
    assert sorted(order) == ["c0", "c1", "c2", "root"], "Phải duyệt đủ 4 node, không trùng"
    print("    [ok] Mọi node được duyệt đúng 1 lần.")

    # Bất biến 2: dependency phải done TRƯỚC node phụ thuộc — c0 trước c1.
    assert order.index("c0") < order.index("c1"), "c0 (dependency) phải trước c1"
    print("    [ok] c0 được giải TRƯỚC c1 (tôn trọng depends_on, không climb early).")

    # Bất biến 3: parent (root, depth 0) đi trước con (depth 1) theo (depth, order).
    assert order[0] == "root", "root (depth nhỏ nhất) phải được trả đầu tiên"
    print("    [ok] root (depth=0) được trả đầu tiên — đúng thứ tự (depth, order).")

    # Bất biến 4: sau khi duyệt hết, next_node() trả None (cursor cạn).
    assert tree.next_node() is None, "Duyệt hết thì cursor phải trả None"
    print("    [ok] next_node() trả None sau khi cạn — client biết khi nào dừng.")

    print("\n[5] Hai cursor độc lập không ảnh hưởng nhau:")
    t_a = build_tree()
    t_b = build_tree()
    first_a = t_a.next_node()
    # Tiến cursor A một bước (đánh root done), cursor B phải vẫn ở trạng thái đầu.
    t_a.set_status(first_a.id, "done")
    first_b = t_b.next_node()
    assert first_b.id == "root", "Cursor B độc lập, vẫn bắt đầu từ root"
    print(f"    [ok] Tiến cursor A (đã done {first_a.id!r}); cursor B vẫn trả {first_b.id!r}.")

    print("\nKẾT LUẬN: solve() chỉ gọi next_node() lặp lại — không hề biết topo-sort,")
    print("status tracking hay (depth, order). Toàn bộ 'cách duyệt' bị giấu trong cursor.")
    print("Đó là Iterator: SC chọn fixation, V1 chỉ xử lý cái đang fixate.")


if __name__ == "__main__":
    demo()
