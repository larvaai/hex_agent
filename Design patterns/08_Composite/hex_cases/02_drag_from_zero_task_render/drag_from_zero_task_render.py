"""
Case 02 — Composite: Cây render task của drag_from_zero (TaskNode)

Bản DISTILL TRUNG THỰC, chỉ dùng thư viện chuẩn Python 3.14.
KHÔNG import gì từ hex_agent.

Nguồn thật được rút gọn (đã mở & xác minh từng dòng):
  - drag_from_zero/dragzero/read_model.py:16-46
        TaskNode dataclass: id, description, parent_id, status, children (list).
        Mọi node CÙNG schema -> không phân biệt loại (Component).
        reduce(events): fold event log thành cây.
          * ROOT_TASK_CREATED  (dòng 36-39) -> tạo gốc.
          * SUBTASK_SPAWNED    (dòng 40-46) -> tạo con, append vào parent.children.
  - drag_from_zero/dragzero/live_view.py:27-50
        render_tree(root): đi DFS bằng hàm walk() LỒNG bên trong (dòng 32-47).
        Với mỗi node: in status, rồi đệ quy walk(child) cho mọi node.children.
        KHÔNG isinstance, KHÔNG type-check — duck typing trên node.children.

Những gì bị LƯỢC BỎ so với bản thật (vẫn giữ đúng pattern):
  - Bộ Event/EventType đầy đủ (TASK_STARTED, TOOL_RESULT, DELEGATION_DECIDED, ...)
    -> giữ lại 3 loại đủ minh hoạ Composite: ROOT_TASK_CREATED, SUBTASK_SPAWNED,
       TASK_COMPLETED.
  - Glyph/connector trang trí phong phú -> giữ glyph trạng thái tối thiểu + connector
    ├─ └─ giống bản thật, đủ để thấy đệ quy render đúng độ sâu.
  - TaskStatus enum -> dùng hằng chuỗi đơn giản.
Giữ NGUYÊN: TaskNode cùng-một-kiểu; reduce() fold event -> cây; render_tree()
            đệ quy ĐỒNG NHẤT không type-check; cây sâu tuỳ ý tự render đúng.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Trạng thái (rút gọn của TaskStatus enum).
# ─────────────────────────────────────────────────────────────────────────────
PENDING = "pending"
RUNNING = "running"
DELEGATED = "delegated"   # cha đã decompose -> còn chờ con xong
DONE = "done"
FAILED = "failed"

GLYPH = {PENDING: "○", RUNNING: "◐", DELEGATED: "◇", DONE: "●", FAILED: "✗"}
_TERMINAL = {DONE, FAILED}


# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT — TaskNode. Mọi node CÙNG một kiểu. children=[] => leaf, có con => composite.
# (distill: drag_from_zero/dragzero/read_model.py:16-27)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TaskNode:
    id: str
    description: str
    parent_id: str | None
    status: str = PENDING
    children: list = field(default_factory=list)   # list[TaskNode]


# ─────────────────────────────────────────────────────────────────────────────
# EVENT — bản ghi bất biến trong log (rút gọn của Event).
# ─────────────────────────────────────────────────────────────────────────────
ROOT_TASK_CREATED = "ROOT_TASK_CREATED"
SUBTASK_SPAWNED = "SUBTASK_SPAWNED"
TASK_COMPLETED = "TASK_COMPLETED"


@dataclass
class Event:
    type: str
    task_id: str
    payload: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# reduce() — FOLD event log thành cây TaskNode (pure projection / read-model).
# (distill: drag_from_zero/dragzero/read_model.py:30-83)
# ─────────────────────────────────────────────────────────────────────────────
def reduce(events: list[Event]) -> tuple[TaskNode | None, dict]:
    nodes: dict[str, TaskNode] = {}
    root_id: str | None = None

    for e in events:
        if e.type == ROOT_TASK_CREATED:
            node = TaskNode(e.task_id, e.payload.get("description", ""), None)
            nodes[e.task_id] = node
            root_id = e.task_id
        elif e.type == SUBTASK_SPAWNED:
            parent = e.payload.get("parent")
            node = TaskNode(e.task_id, e.payload.get("subtask", ""), parent)
            nodes[e.task_id] = node
            if parent in nodes:
                nodes[parent].children.append(node)   # gắn con vào cha
                # cha có con -> chuyển sang DELEGATED nếu đang pending/running
                if nodes[parent].status in (PENDING, RUNNING):
                    nodes[parent].status = DELEGATED
        elif e.type == TASK_COMPLETED:
            if e.task_id in nodes:
                nodes[e.task_id].status = DONE

    return (nodes.get(root_id) if root_id else None), nodes


# ─────────────────────────────────────────────────────────────────────────────
# render_tree() — đi DFS ĐỆ QUY ĐỒNG NHẤT, không isinstance.
# (distill: drag_from_zero/dragzero/live_view.py:27-50)
# ─────────────────────────────────────────────────────────────────────────────
def render_tree(root: TaskNode | None) -> str:
    if root is None:
        return "(empty)"
    lines: list[str] = []

    def walk(node: TaskNode, prefix: str, is_last: bool, is_root: bool) -> None:
        glyph = GLYPH.get(node.status, "·")
        connector = "" if is_root else ("└─ " if is_last else "├─ ")
        lines.append(f"{prefix}{connector}{glyph} {node.description} [{node.status}]")
        child_prefix = prefix + ("   " if is_root else ("    " if is_last else "│   "))
        # ĐỆ QUY: leaf và composite duyệt y hệt nhau qua node.children.
        for i, child in enumerate(node.children):
            walk(child, child_prefix, i == len(node.children) - 1, False)

    walk(root, "", True, True)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Một operation đệ quy KHÁC trên cùng cây (minh hoạ "đệ quy đóng gói"):
# đếm số leaf đã done — định nghĩa MỘT lần, đúng cho mọi độ sâu.
# ─────────────────────────────────────────────────────────────────────────────
def count_done_leaves(node: TaskNode) -> int:
    if not node.children:                      # leaf
        return 1 if node.status == DONE else 0
    return sum(count_done_leaves(c) for c in node.children)  # composite: tổng đệ quy


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG: KHÔNG dùng Composite -> render bằng if-else theo "loại" + độ sâu cứng.
# ─────────────────────────────────────────────────────────────────────────────
def render_naive_BAD(root: TaskNode) -> str:
    """Anti-pattern: render HARD-CODE 2 cấp (gốc + con trực tiếp).
    Bug: cháu (cấp 3+) bị BỎ SÓT — không in ra. Cây sâu thêm là sai ngay."""
    out = [f"{GLYPH.get(root.status, '·')} {root.description} [{root.status}]"]
    for child in root.children:
        out.append(f"  - {GLYPH.get(child.status, '·')} {child.description} [{child.status}]")
        # KHÔNG đệ quy xuống child.children -> cháu biến mất
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("CASE 02 — Composite: cây render TaskNode của drag_from_zero")
    print("=" * 70)

    # Dựng event log: gốc -> 2 subtask -> 1 subtask con của subtask -> hoàn thành.
    events = [
        Event(ROOT_TASK_CREATED, "root", {"description": "Viết báo cáo Q4"}),
        Event(SUBTASK_SPAWNED, "s1", {"parent": "root", "subtask": "Thu thập số liệu"}),
        Event(SUBTASK_SPAWNED, "s2", {"parent": "root", "subtask": "Soạn slide"}),
        # subtask LỒNG: con của s1 -> cây sâu 3 cấp
        Event(SUBTASK_SPAWNED, "s1a", {"parent": "s1", "subtask": "Truy vấn DB"}),
        Event(SUBTASK_SPAWNED, "s1b", {"parent": "s1", "subtask": "Làm sạch dữ liệu"}),
        Event(TASK_COMPLETED, "s1a", {}),
        Event(TASK_COMPLETED, "s1b", {}),
        Event(TASK_COMPLETED, "s2", {}),
    ]

    print("\n[1] reduce() fold event log thành cây TaskNode (read-model thuần):")
    root, all_nodes = reduce(events)
    print(f"    Tổng số node trong cây: {len(all_nodes)}")
    print(f"    root.children = {[c.id for c in root.children]}")
    print(f"    s1.children   = {[c.id for c in all_nodes['s1'].children]}  <- cây sâu 3 cấp")

    print("\n[2] render_tree() — ĐỆ QUY ĐỒNG NHẤT, không isinstance, tự đúng mọi độ sâu:")
    print()
    for line in render_tree(root).splitlines():
        print("    " + line)

    print("\n[3] Một operation đệ quy KHÁC trên cùng cây (count_done_leaves):")
    done = count_done_leaves(root)
    print(f"    Số leaf đã done = {done}  (s1a, s1b, s2 — định nghĩa 1 lần, đúng mọi cấp)")

    print("\n[4] Đối chứng — render thủ công hard-code 2 cấp BỎ SÓT cháu:")
    print()
    for line in render_naive_BAD(root).splitlines():
        print("    " + line)
    print("    ^ thiếu hẳn s1a, s1b (cấp 3) — anti-pattern không scale theo độ sâu.")

    # ── ASSERT chứng minh bất biến của Composite ──
    rendered = render_tree(root)
    # 1) đệ quy đồng nhất: MỌI node (kể cả cháu cấp 3) đều xuất hiện trong render.
    for nid, node in all_nodes.items():
        assert node.description in rendered, f"node {nid} phải có trong render đệ quy"
    # 2) đối chứng: render thủ công bỏ sót cháu cấp 3.
    naive = render_naive_BAD(root)
    assert "Truy vấn DB" not in naive, "render thủ công đáng lẽ bỏ sót cháu cấp 3"
    assert "Truy vấn DB" in rendered, "Composite phải in được cháu cấp 3"
    # 3) closure đếm leaf đúng: 3 leaf done.
    assert count_done_leaves(root) == 3, "phải có đúng 3 leaf done"
    # 4) cấu trúc cây: parent_id của con khớp id cha (bất biến fold).
    for nid, node in all_nodes.items():
        for child in node.children:
            assert child.parent_id == nid, f"{child.id}.parent_id phải = {nid}"
    # 5) cây rỗng -> render an toàn "(empty)" (leaf/None xử lý đồng nhất).
    assert render_tree(None) == "(empty)"

    print("\n[5] PASS — mọi assert đúng: render đệ quy in đủ cháu cấp 3, operation đệ quy")
    print("    khác chạy đúng trên cùng cây, và đối chứng thủ công lộ rõ chỗ bỏ sót.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
