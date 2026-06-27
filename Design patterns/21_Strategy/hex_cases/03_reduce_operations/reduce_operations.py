"""
Case 03 — Reduce Node: Pluggable Aggregation Strategies (pick/concat/merge/manifest)
====================================================================================

Bản DISTILL TRUNG THỰC từ hex_agent. Nguồn thật:
  - decompose_agent/node.py:28          -> REDUCE_OPS = frozenset({"merge_json","pick","manifest","concat"})
  - decompose_agent/node.py:114-115     -> Node.reduce_op + Node.inputs (khai báo strategy + nguồn)
  - decompose_agent/node.py:132-133     -> __post_init__: reduce node BẮT BUỘC có reduce_op hợp lệ
  - decompose_agent/reduce.py:44-77     -> run_reduce(): dispatch theo node.reduce_op
  - decompose_agent/reduce.py:35-41     -> _deep_merge() (helper cho strategy merge_json)
  - decompose_agent/reduce.py:80-92     -> _size/_read_text/_load_json (helper từng strategy)
  - decompose_agent/tests/test_reduce.py:34-55 -> test mỗi strategy độc lập

Strategy ở đây xuất hiện ở DẠNG "dispatch theo selector": một phép toán gộp (reduce)
N output anh-em thành 1 aggregate, với 4 cách gộp khác nhau. Selector là chuỗi
node.reduce_op khai báo TRÊN Node — KHÔNG hardcode trong handler.

Lưu ý trung thực: code thật dùng if/elif trong run_reduce() (chấp nhận được vì số
strategy ít & ổn định — đúng như 21_Strategy.md mục "Khi nào KHÔNG dùng"/registry).
Distill này GIỮ NGUYÊN tinh thần đó nhưng tách rõ từng strategy thành callable + một
REGISTRY {tên: callable} để LÀM NỔI BẬT vai trò Strategy, đồng thời cho thấy lợi ích
mở rộng (thêm strategy = thêm 1 entry, không sửa Context).

Distill này thay filesystem (Path/read/write) bằng một "workspace trong RAM": dict
{node_id: {artifact_name: bytes}}. Giữ nguyên ngữ nghĩa: gom theo destination, deep-merge
JSON, concat text, pick (copy bản cuối), manifest (liệt kê tồn tại + size).

CHẠY: python3 reduce_operations.py   (exit 0, không traceback)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

# REDUCE_OPS — đúng tập hợp của node.py:28
REDUCE_OPS = frozenset({"merge_json", "pick", "manifest", "concat"})


# ─────────────────────────────────────────────────────────────────────────────
# NODE — selector của strategy (node.py:97-135, rút gọn)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Node:
    """Một reduce node khai báo NÓ gộp bằng strategy nào (reduce_op) và gộp NHỮNG GÌ
    (inputs). Bất biến cấu trúc: reduce node phải có reduce_op hợp lệ (node.py:132-133)."""

    id: str
    reduce_op: str
    inputs: tuple[dict[str, Any], ...] = ()      # [{from, artifact, as?}]
    manifest_target: str = "manifest.json"

    def __post_init__(self) -> None:
        if self.reduce_op not in REDUCE_OPS:
            raise ValueError(
                f"reduce node {self.id!r} needs reduce_op ∈ {sorted(REDUCE_OPS)}, got {self.reduce_op!r}")


# ─────────────────────────────────────────────────────────────────────────────
# WORKSPACE — thay filesystem bằng RAM. {node_id: {artifact: bytes}}
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Workspace:
    files: dict[str, dict[str, bytes]] = field(default_factory=dict)

    def write(self, node_id: str, artifact: str, data: bytes) -> None:
        self.files.setdefault(node_id, {})[artifact] = data

    def read(self, node_id: str, artifact: str) -> bytes | None:
        return self.files.get(node_id, {}).get(artifact)

    def exists(self, node_id: str, artifact: str) -> bool:
        return self.read(node_id, artifact) is not None

    def size(self, node_id: str, artifact: str) -> int:
        data = self.read(node_id, artifact)
        return len(data) if data is not None else 0


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — reduce.py:35-41, 80-92
# ─────────────────────────────────────────────────────────────────────────────
def _deep_merge(into: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(into.get(k), dict):
            _deep_merge(into[k], v)
        else:
            into[k] = v
    return into


def _read_text(data: bytes | None) -> str:
    return data.decode("utf-8", errors="replace") if data is not None else ""


def _load_json(data: bytes | None) -> Any:
    try:
        return json.loads(_read_text(data))
    except (json.JSONDecodeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CONCRETE STRATEGIES — mỗi cách gộp là 1 callable cùng chữ ký.
# Chữ ký: (node, ws, by_dst) -> None. by_dst: {dst: [(from_id, artifact)]}
# (manifest không theo by_dst — nó liệt kê toàn bộ inputs.)
# ─────────────────────────────────────────────────────────────────────────────
ReduceStrategy = Callable[[Node, Workspace, dict[str, list[tuple[str, str]]]], None]


def _strategy_pick(node: Node, ws: Workspace, by_dst: dict[str, list[tuple[str, str]]]) -> None:
    """pick — copy bản cuối cùng vào destination (reduce.py:67-68)."""
    for dst, srcs in by_dst.items():
        last_from, last_art = srcs[-1]
        ws.write(node.id, dst, ws.read(last_from, last_art) or b"")


def _strategy_concat(node: Node, ws: Workspace, by_dst: dict[str, list[tuple[str, str]]]) -> None:
    """concat — nối text các nguồn cùng destination (reduce.py:69-70)."""
    for dst, srcs in by_dst.items():
        joined = "".join(_read_text(ws.read(f, a)) for f, a in srcs)
        ws.write(node.id, dst, joined.encode("utf-8"))


def _strategy_merge_json(node: Node, ws: Workspace, by_dst: dict[str, list[tuple[str, str]]]) -> None:
    """merge_json — deep-merge mọi JSON cùng destination (reduce.py:71-77)."""
    for dst, srcs in by_dst.items():
        merged: dict[str, Any] = {}
        for f, a in srcs:
            obj = _load_json(ws.read(f, a))
            if isinstance(obj, dict):
                _deep_merge(merged, obj)
        ws.write(node.id, dst, json.dumps(merged, ensure_ascii=False).encode("utf-8"))


def _strategy_manifest(node: Node, ws: Workspace, by_dst: dict[str, list[tuple[str, str]]]) -> None:
    """manifest — ghi JSON liệt kê tồn tại + size của từng input (reduce.py:50-57)."""
    inputs = [{"from": i["from"], "artifact": i["artifact"],
               "exists": ws.exists(i["from"], i["artifact"]),
               "size": ws.size(i["from"], i["artifact"])}
              for i in node.inputs]
    ws.write(node.id, node.manifest_target,
             json.dumps({"inputs": inputs}, ensure_ascii=False).encode("utf-8"))


# REGISTRY — Strategy registry (21_Strategy.md mục 2.4 "Strategy registry").
# Thêm strategy mới = thêm 1 entry, KHÔNG sửa run_reduce.
STRATEGIES: dict[str, ReduceStrategy] = {
    "pick": _strategy_pick,
    "concat": _strategy_concat,
    "merge_json": _strategy_merge_json,
    "manifest": _strategy_manifest,
}


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT — run_reduce() dispatch theo node.reduce_op (reduce.py:44-77)
# ─────────────────────────────────────────────────────────────────────────────
def run_reduce(node: Node, ws: Workspace) -> None:
    """Thực thi reduce_op của node, ghi aggregate vào dir của chính reduce node."""
    if node.reduce_op == "manifest":
        STRATEGIES["manifest"](node, ws, {})
        return
    # gom theo destination để nhiều nguồn fold vào 1 aggregate (reduce.py:60-62)
    by_dst: dict[str, list[tuple[str, str]]] = {}
    for item in node.inputs:
        dst = item.get("as") or item["artifact"]
        by_dst.setdefault(dst, []).append((item["from"], item["artifact"]))
    STRATEGIES[node.reduce_op](node, ws, by_dst)


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — run_reduce nhồi if/elif và KHÔNG dùng selector trên Node
# ─────────────────────────────────────────────────────────────────────────────
def run_reduce_hardcoded(reduce_op_param: str, node: Node, ws: Workspace) -> None:
    """Anti-pattern: caller phải truyền reduce_op rời (dễ lệch với node), và mọi
    strategy nhồi vào 1 hàm. Thêm strategy mới = mở hàm này sửa (vi phạm Open/Closed).
    Selector tách rời Node -> mất tính 'khai báo' và dễ truyền sai."""
    by_dst: dict[str, list[tuple[str, str]]] = {}
    for item in node.inputs:
        dst = item.get("as") or item["artifact"]
        by_dst.setdefault(dst, []).append((item["from"], item["artifact"]))
    if reduce_op_param == "pick":
        for dst, srcs in by_dst.items():
            f, a = srcs[-1]
            ws.write(node.id, dst, ws.read(f, a) or b"")
    elif reduce_op_param == "concat":
        for dst, srcs in by_dst.items():
            ws.write(node.id, dst, "".join(_read_text(ws.read(f, a)) for f, a in srcs).encode())
    # ... merge_json, manifest cũng phải copy logic vào đây -> trùng lặp & dễ quên.
    else:
        raise ValueError(f"hardcoded reducer chưa cài: {reduce_op_param}")


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def _seed_workspace() -> Workspace:
    ws = Workspace()
    # 2 anh-em P.a, P.b mỗi cái sinh artifact JSON + text
    ws.write("P.a", "a.json", json.dumps({"recall_at_5": 0.91, "meta": {"k": 5}}).encode())
    ws.write("P.b", "b.json", json.dumps({"queries": list(range(50)), "meta": {"src": "qd"}}).encode())
    ws.write("P.a", "part.txt", b"hello ")
    ws.write("P.b", "part.txt", b"world")
    return ws


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — Reduce Aggregation Strategies (pick/concat/merge_json/manifest)")
    print("=" * 72)

    print("\n[1] CÙNG bộ input anh-em, đổi reduce_op -> aggregate KHÁC HẲN\n")

    # --- merge_json: deep-merge 2 JSON vào cùng report.json ---
    ws = _seed_workspace()
    node_merge = Node("P.reduce", "merge_json", inputs=(
        {"from": "P.a", "artifact": "a.json", "as": "report.json"},
        {"from": "P.b", "artifact": "b.json", "as": "report.json"},
    ))
    run_reduce(node_merge, ws)
    merged = json.loads(_read_text(ws.read("P.reduce", "report.json")))
    print(f"  merge_json -> keys={sorted(merged)} meta={merged['meta']}")
    assert merged["recall_at_5"] == 0.91 and len(merged["queries"]) == 50
    assert merged["meta"] == {"k": 5, "src": "qd"}, "deep-merge nested dict (reduce.py:35-41)"

    # --- concat: nối 2 part.txt ---
    ws = _seed_workspace()
    node_concat = Node("P.reduce", "concat", inputs=(
        {"from": "P.a", "artifact": "part.txt", "as": "all.txt"},
        {"from": "P.b", "artifact": "part.txt", "as": "all.txt"},
    ))
    run_reduce(node_concat, ws)
    text = _read_text(ws.read("P.reduce", "all.txt"))
    print(f"  concat     -> {text!r}")
    assert text == "hello world", "concat nối theo thứ tự inputs"

    # --- pick: copy bản cuối ---
    ws = _seed_workspace()
    node_pick = Node("P.reduce", "pick", inputs=(
        {"from": "P.a", "artifact": "a.json", "as": "chosen.json"},
    ))
    run_reduce(node_pick, ws)
    picked = json.loads(_read_text(ws.read("P.reduce", "chosen.json")))
    print(f"  pick       -> chosen.json = {picked}")
    assert picked["recall_at_5"] == 0.91, "pick copy verbatim"

    # --- manifest: liệt kê tồn tại + size ---
    ws = _seed_workspace()
    node_manifest = Node("P.reduce", "manifest", inputs=(
        {"from": "P.a", "artifact": "a.json"},
        {"from": "P.b", "artifact": "missing.json"},  # cố tình thiếu
    ), manifest_target="manifest.json")
    run_reduce(node_manifest, ws)
    manifest = json.loads(_read_text(ws.read("P.reduce", "manifest.json")))
    print(f"  manifest   -> {manifest}")
    assert manifest["inputs"][0]["exists"] is True and manifest["inputs"][0]["size"] > 0
    assert manifest["inputs"][1]["exists"] is False and manifest["inputs"][1]["size"] == 0
    print("  -> 4 reduce_op, 4 aggregate khác nhau, CÙNG input. Đó là Strategy.")

    print("\n[2] BẤT BIẾN: reduce node phải khai báo reduce_op hợp lệ (node.py:132-133)\n")
    try:
        Node("P.bad", "bogus_op")
        raise AssertionError("đáng lẽ phải raise ValueError cho reduce_op lạ")
    except ValueError as exc:
        print(f"  Node('P.bad', 'bogus_op') -> ValueError: {exc}")
    assert set(STRATEGIES) == REDUCE_OPS, "registry phải phủ ĐÚNG tập REDUCE_OPS"
    print(f"  registry phủ đủ REDUCE_OPS = {sorted(REDUCE_OPS)}")

    print("\n[3] MỞ RỘNG (Open/Closed): thêm strategy 'count' KHÔNG đụng run_reduce\n")

    def _strategy_count(node: Node, ws: Workspace, by_dst: dict[str, list[tuple[str, str]]]) -> None:
        for dst, srcs in by_dst.items():
            ws.write(node.id, dst, json.dumps({"n_inputs": len(srcs)}).encode())

    STRATEGIES["count"] = _strategy_count  # chỉ thêm 1 entry vào registry

    @dataclass(frozen=True)
    class ExtNode(Node):
        def __post_init__(self) -> None:  # nới lỏng để nhận 'count'
            if self.reduce_op not in (REDUCE_OPS | {"count"}):
                raise ValueError("bad op")

    ws = _seed_workspace()
    node_count = ExtNode("P.reduce", "count", inputs=(
        {"from": "P.a", "artifact": "a.json", "as": "c.json"},
        {"from": "P.b", "artifact": "b.json", "as": "c.json"},
    ))
    run_reduce(node_count, ws)
    cnt = json.loads(_read_text(ws.read("P.reduce", "c.json")))
    print(f"  count      -> {cnt}")
    assert cnt["n_inputs"] == 2
    print("  -> Thêm cách gộp mới = thêm 1 callable vào registry. run_reduce() bất biến.")
    del STRATEGIES["count"]  # dọn dẹp

    print("\n[4] ĐỐI CHỨNG — run_reduce_hardcoded: selector tách rời Node + if/elif cứng\n")
    ws = _seed_workspace()
    run_reduce_hardcoded("concat", node_concat, ws)  # phải tự nhớ truyền 'concat'
    print(f"  hardcoded concat -> {_read_text(ws.read('P.reduce', 'all.txt'))!r} (ok khi truyền đúng)")
    try:
        run_reduce_hardcoded("merge_json", node_merge, _seed_workspace())
    except ValueError as exc:
        print(f"  hardcoded 'merge_json' -> {exc}")
        print("  -> mỗi strategy mới phải MỞ hàm này sửa; selector rời Node dễ truyền lệch.")

    print("\n" + "=" * 72)
    print("KẾT LUẬN: reduce_op = selector strategy (khai báo trên Node).")
    print("pick/concat/merge_json/manifest = ConcreteStrategy. run_reduce = Context dispatch.")
    print("Registry hoá -> Open/Closed. Cùng input, khác reduce_op = khác aggregate. Mọi assert PASS.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
