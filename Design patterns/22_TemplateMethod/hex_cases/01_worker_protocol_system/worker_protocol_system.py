"""
Case 01 — Worker Protocol: khung cố định propose/decompose, hai cách hiện thực.

NGUỒN THẬT (distill từ hex_agent):
  - decompose_agent/worker.py:182-185   -> Worker(Protocol): khai báo SKELETON
                                           (hai method bắt buộc: propose, decompose)
  - decompose_agent/worker.py:188-227   -> ScriptedWorker: hiện thực "test double"
                                           (script/satisfy tất định, không network)
  - decompose_agent/worker.py:230-301   -> LocalLLMWorker: hiện thực "production"
                                           (gọi API OpenAI-compatible + retry/backoff)
  - decompose_agent/solve.py:80-122     -> solve_leaf(): KHUNG vòng-thử gọi
                                           worker.propose(ctx) như một hook
  - decompose_agent/solve.py:132-184    -> _decompose(): KHUNG vòng decompose gọi
                                           worker.decompose(node) như một hook

Ý TƯỞNG PATTERN (Template Method ở scale Protocol, không inheritance):
  hex_agent KHÔNG dùng base class + override. Nó dùng structural typing (Protocol)
  để định nghĩa "khung hợp đồng" (skeleton contract): bất cứ Worker nào cũng phải
  có propose() và decompose() với CÙNG chữ ký. Bên gọi (solve_leaf/_decompose) giữ
  thứ tự bước CỐ ĐỊNH (assemble context -> propose -> parse -> run -> check) và chỉ
  gọi hook propose()/decompose() — đúng tinh thần Hollywood: "Don't call us, we'll
  call you". Hai hiện thực (Scripted vs LLM) cho ra hành vi khác hẳn nhau qua CÙNG
  một khung.

Phiên bản rút gọn này dùng STDLIB thuần. "LLM" được thay bằng một bộ máy fake tất
định (FakeChatEndpoint) trả JSON theo từ khoá; "network" được thay bằng một bộ đếm
lỗi nhân tạo để minh hoạ retry/backoff mà KHÔNG cần socket thật.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ─────────────────────────────────────────────────────────────────────────────
# Hạ tầng tối thiểu (thay cho FourCell/Node/parser thật trong hex_agent)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FourCell:
    """Bản rút gọn của decompose_agent context (identity + 4 ô thông tin)."""
    node_id: str
    identity: str
    goal: str

    def render(self) -> str:
        return f"GOAL[{self.node_id}]: {self.goal}"


@dataclass(frozen=True)
class Node:
    id: str
    goal: str
    done_when: tuple[str, ...]


class JsonGateError(ValueError):
    """Phỏng theo discipline.JsonGateError: chuỗi không parse được thành JSON."""


class WorkerError(RuntimeError):
    """Phỏng theo decompose_agent.worker.WorkerError: endpoint chết/hết retry."""


def parse_object(raw: str) -> dict[str, Any]:
    """Thay cho 'repair ladder' thật: chỉ cần json.loads + kiểm tra là dict."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonGateError(f"không parse được object: {exc}") from exc
    if not isinstance(obj, dict):
        raise JsonGateError("kết quả không phải JSON object")
    return obj


def parse_children(raw: Any) -> list[dict]:
    """Thay cho parse_children thật: chấp nhận list sẵn, hoặc parse từ chuỗi JSON."""
    if isinstance(raw, list):
        return raw
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonGateError(f"không parse được children: {exc}") from exc
    if not isinstance(obj, list):
        raise JsonGateError("children phải là JSON array")
    return obj


def normalize_action(obj: dict[str, Any]) -> dict[str, Any]:
    """Phỏng theo normalize_action: đảm bảo có khoá 'action'."""
    obj.setdefault("action", "write")
    return obj


def write_action(files: dict[str, str]) -> dict[str, Any]:
    return {"action": "write", "files": files}


# ─────────────────────────────────────────────────────────────────────────────
# SKELETON CONTRACT — Worker Protocol  (worker.py:182-185)
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class Worker(Protocol):
    """Khung cố định: MỌI worker phải cung cấp đúng hai bước này, cùng chữ ký.

    Đây là "abstract template" theo nghĩa structural — không có code chung ở đây;
    code chung (khung gọi) nằm ở solve_leaf/_decompose phía dưới. Bản thân Protocol
    chỉ ép HỢP ĐỒNG của hai hook.
    """
    def propose(self, ctx: FourCell) -> dict[str, Any]: ...
    def decompose(self, node: Node, failure_evidence: Any = None,
                  reason: str | None = None) -> Any: ...


# ─────────────────────────────────────────────────────────────────────────────
# HIỆN THỰC A — ScriptedWorker (test double)  (worker.py:188-227)
# ─────────────────────────────────────────────────────────────────────────────
class ScriptedWorker:
    """Tất định: trả action/children theo 'script' đã nạp sẵn, hoặc tự sinh khi có
    'satisfy'. Không bao giờ chạm network. Dùng cho test."""

    def __init__(self, scripts: dict[str, list[Any]] | None = None, *,
                 satisfy: bool = False,
                 decompose_scripts: dict[str, list[Any]] | None = None) -> None:
        self._scripts = scripts or {}
        self._decompose_scripts = decompose_scripts or {}
        self._satisfy = satisfy
        self._calls: dict[str, int] = {}
        self._dcalls: dict[str, int] = {}

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        nid = ctx.node_id
        i = self._calls.get(nid, 0)
        self._calls[nid] = i + 1
        script = self._scripts.get(nid)
        if script:
            item = script[i] if i < len(script) else script[-1]
            if isinstance(item, str):
                return normalize_action(parse_object(item))  # có thể raise JsonGateError (fumble)
            return item
        if self._satisfy:
            return write_action({"out.txt": "ok\n"})  # tự sinh action "thoả mãn"
        return write_action({})  # không script, không satisfy -> no-op (gate sẽ FAIL)

    def decompose(self, node: Node, failure_evidence: Any = None,
                  reason: str | None = None) -> list[dict]:
        nid = node.id
        i = self._dcalls.get(nid, 0)
        self._dcalls[nid] = i + 1
        script = self._decompose_scripts.get(nid)
        if script:
            item = script[i] if i < len(script) else script[-1]
            return parse_children(item) if isinstance(item, str) else item
        if self._satisfy:
            # chia 2 tất định: mỗi con một tiêu chí nhỏ hơn cha
            return [{"id": f"{nid}.c{j}", "depends_on": [],
                     "done_when": [f"file_exists:c{j}.txt"]} for j in range(2)]
        raise NotImplementedError(f"decompose() chưa có script cho {nid!r}")


# ─────────────────────────────────────────────────────────────────────────────
# HIỆN THỰC B — LocalLLMWorker (production)  (worker.py:230-301)
# ─────────────────────────────────────────────────────────────────────────────
class FakeChatEndpoint:
    """Thay cho client OpenAI thật. Tất định, có thể giả lập N lỗi transient đầu
    tiên để minh hoạ retry/backoff trong _chat()."""

    def __init__(self, *, transient_failures: int = 0) -> None:
        self._left = transient_failures
        self.calls = 0

    def chat(self, messages: list[dict]) -> str:
        self.calls += 1
        if self._left > 0:
            self._left -= 1
            raise ConnectionError("endpoint tạm thời không phản hồi")
        # "Suy luận" tất định theo nội dung user message.
        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        if "SPLIT" in user:  # decompose request
            base = user.split("SPLIT:")[-1].strip() or "task"
            return json.dumps([
                {"id": f"{base}.a", "depends_on": [], "done_when": ["file_exists:a.txt"]},
                {"id": f"{base}.b", "depends_on": [], "done_when": ["file_exists:b.txt"]},
            ])
        return json.dumps({"action": "write", "files": {"answer.txt": "from-llm\n"}})


def _is_transient(exc: Exception) -> bool:
    return isinstance(exc, (ConnectionError, TimeoutError))


class LocalLLMWorker:
    """Gọi 'LLM' qua endpoint injectable; cùng chữ ký propose/decompose với
    ScriptedWorker nhưng nội tạng khác hẳn (chat + retry + parse)."""

    def __init__(self, *, client: FakeChatEndpoint, retries: int = 2,
                 retry_base: float = 0.0) -> None:
        self._client = client
        self._retries = retries
        self._retry_base = retry_base  # 0.0 để test chạy nhanh; thật là 0.4

    def _chat(self, messages: list[dict]) -> str:
        """Một lần gọi chat, có backoff hàm mũ trên lỗi transient (worker.py:254-277)."""
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                return self._client.chat(messages)
            except Exception as exc:
                last = exc
                if attempt < self._retries and _is_transient(exc):
                    if self._retry_base:
                        time.sleep(self._retry_base * (2 ** attempt))
                    continue
                break
        raise WorkerError(f"LLM call thất bại sau {self._retries + 1} lần: {last}")

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        raw = self._chat([{"role": "system", "content": ctx.identity},
                          {"role": "user", "content": ctx.render()}])
        return normalize_action(parse_object(raw))

    def decompose(self, node: Node, failure_evidence: Any = None,
                  reason: str | None = None) -> list[dict]:
        raw = self._chat([{"role": "system", "content": "You split ONE task into >=2 children."},
                          {"role": "user", "content": f"SPLIT:{node.id}"}])
        return parse_children(raw)


# ─────────────────────────────────────────────────────────────────────────────
# KHUNG GỌI (concrete operations chung)  — solve.py:80-122 và 132-184
# Đây là "template method" thực sự: thứ tự bước CỐ ĐỊNH, chỉ hook propose/decompose
# là thay đổi tuỳ worker.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Outcome:
    node_id: str
    status: str
    detail: str = ""


def run_checks(action: dict[str, Any], done_when: tuple[str, ...]) -> bool:
    """Bản rút gọn của run_checks: gate pass nếu action có ghi file (không no-op)."""
    files = action.get("files") or {}
    return bool(files)


def solve_leaf(node: Node, worker: Worker, *, k_attempts: int = 2,
               parse_max: int = 2, log: list[str] | None = None) -> Outcome:
    """KHUNG vòng-thử cho một leaf (solve.py:80-122). Thứ tự bước bất biến:
        assemble context -> worker.propose(HOOK) -> parse/handle -> run_checks -> gate.
    """
    log = log if log is not None else []
    attempts = 0
    parse_errors = 0
    while attempts < k_attempts:
        ctx = FourCell(node_id=node.id, identity="agent", goal=node.goal)  # 1. assemble (chung)
        try:
            action = worker.propose(ctx)                                   # 2. HOOK
        except WorkerError as exc:                                         # endpoint chết -> infra block
            log.append(f"    propose WORKER_ERROR: {exc}")
            return Outcome(node.id, "blocked", "WORKER_ERROR")
        except JsonGateError as exc:                                       # parse fumble: KHÔNG tốn attempt
            parse_errors += 1
            log.append(f"    propose parse fumble #{parse_errors}: {exc}")
            if parse_errors >= parse_max:
                return Outcome(node.id, "blocked", "PARSE_BUDGET")
            continue
        attempts += 1
        ok = run_checks(action, node.done_when)                           # 3+4. run + check (chung)
        log.append(f"    attempt {attempts}: action={action.get('action')} files={list((action.get('files') or {}))} gate={'OK' if ok else 'FAIL'}")
        if ok:
            return Outcome(node.id, "done")
    return Outcome(node.id, "needs_decompose" if len(node.done_when) > 1 else "blocked",
                   "UNSOLVABLE_LEAF" if len(node.done_when) == 1 else "")


def decompose_node(node: Node, worker: Worker, *, log: list[str] | None = None) -> list[dict]:
    """KHUNG decompose (solve.py:132-184), rút gọn: record step -> worker.decompose(HOOK)
    -> parse -> trả children. Cùng khung, hook decompose() là điểm biến thiên."""
    log = log if log is not None else []
    raw = worker.decompose(node)            # HOOK
    children = parse_children(raw)
    log.append(f"    decomposed {node.id} -> {[c['id'] for c in children]}")
    return children


# ─────────────────────────────────────────────────────────────────────────────
# Đối chứng: KHÔNG có khung/hợp đồng chung -> bên gọi phải if/elif theo loại worker
# ─────────────────────────────────────────────────────────────────────────────
def solve_leaf_NO_PATTERN(node: Node, worker: Any, log: list[str]) -> Outcome:
    """Cách KHÔNG dùng pattern: bên gọi phải biết từng loại worker và rẽ nhánh thủ
    công. Thêm 1 loại worker = sửa hàm này. Đây chính là anti-pattern if/elif."""
    if isinstance(worker, ScriptedWorker):
        ctx = FourCell(node.id, "agent", node.goal)
        action = worker.propose(ctx)
    elif isinstance(worker, LocalLLMWorker):
        ctx = FourCell(node.id, "agent", node.goal)
        action = worker.propose(ctx)
    else:
        raise TypeError(f"loại worker chưa được hỗ trợ: {type(worker).__name__}")
    ok = run_checks(action, node.done_when)
    log.append(f"    [NO-PATTERN] gate={'OK' if ok else 'FAIL'}")
    return Outcome(node.id, "done" if ok else "blocked")


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 74)
    print("CASE 01 — Worker Protocol: cùng khung propose/decompose, hai hiện thực")
    print("=" * 74)

    node = Node(id="root", goal="ghi file kết quả", done_when=("file_exists:answer.txt",))

    # --- A. ScriptedWorker chạy qua khung solve_leaf -------------------------
    print("\n[A] ScriptedWorker (test double, tất định) — qua KHUNG solve_leaf:")
    scripted = ScriptedWorker(satisfy=True)
    log_a: list[str] = []
    out_a = solve_leaf(node, scripted, log=log_a)
    for line in log_a:
        print(line)
    print(f"  => outcome: {out_a.status}")

    # --- B. LocalLLMWorker chạy qua CÙNG khung solve_leaf --------------------
    print("\n[B] LocalLLMWorker (gọi 'LLM' fake) — qua CÙNG KHUNG solve_leaf:")
    endpoint = FakeChatEndpoint()
    llm = LocalLLMWorker(client=endpoint, retries=2)
    log_b: list[str] = []
    out_b = solve_leaf(node, llm, log=log_b)
    for line in log_b:
        print(line)
    print(f"  => outcome: {out_b.status}  (endpoint calls={endpoint.calls})")

    # --- C. Khung KHÔNG quan tâm worker là loại nào (polymorphism qua Protocol)
    print("\n[C] CÙNG hàm solve_leaf nhận cả hai worker — không if/elif theo loại:")
    workers: list[Worker] = [ScriptedWorker(satisfy=True),
                             LocalLLMWorker(client=FakeChatEndpoint())]
    for w in workers:
        assert isinstance(w, Worker), "worker phải thoả Protocol Worker"
        res = solve_leaf(node, w)
        print(f"  {type(w).__name__:18s} -> {res.status}")
        assert res.status == "done"

    # --- D. retry/backoff: endpoint lỗi 2 lần rồi mới ok --------------------
    print("\n[D] LocalLLMWorker._chat retry trên lỗi transient (2 lỗi rồi ok):")
    flaky = FakeChatEndpoint(transient_failures=2)
    llm2 = LocalLLMWorker(client=flaky, retries=2, retry_base=0.0)
    res_d = solve_leaf(node, llm2)
    print(f"  outcome={res_d.status}, tổng số lần gọi endpoint={flaky.calls} (1 fail + 1 fail + 1 ok)")
    assert res_d.status == "done"
    assert flaky.calls == 3, "phải gọi đúng 3 lần (2 retry + 1 thành công)"

    # --- E. retry hết quota -> WorkerError -> block (không crash) -----------
    print("\n[E] Endpoint chết hẳn (3 lỗi, chỉ 2 retry) -> WorkerError -> block:")
    dead = FakeChatEndpoint(transient_failures=5)
    llm3 = LocalLLMWorker(client=dead, retries=2, retry_base=0.0)
    res_e = solve_leaf(node, llm3)
    print(f"  outcome={res_e.status} detail={res_e.detail}")
    assert res_e.status == "blocked" and res_e.detail == "WORKER_ERROR"

    # --- F. decompose: cùng khung, hook khác --------------------------------
    print("\n[F] decompose_node — cùng khung, hai hook decompose() khác nhau:")
    big = Node(id="big", goal="task to lớn", done_when=("a", "b"))
    children_scripted = decompose_node(big, ScriptedWorker(satisfy=True))
    children_llm = decompose_node(big, LocalLLMWorker(client=FakeChatEndpoint()))
    print(f"  scripted children: {[c['id'] for c in children_scripted]}")
    print(f"  llm      children: {[c['id'] for c in children_llm]}")
    assert len(children_scripted) >= 2 and len(children_llm) >= 2

    # --- G. ĐỐI CHỨNG: không pattern thì bên gọi phải if/elif ---------------
    print("\n[G] ĐỐI CHỨNG — solve_leaf_NO_PATTERN phải if/elif theo từng loại:")
    log_g: list[str] = []
    solve_leaf_NO_PATTERN(node, ScriptedWorker(satisfy=True), log_g)
    for line in log_g:
        print(line)

    class ThirdPartyWorker:  # worker mới, đúng chữ ký, nhưng NO-PATTERN không biết
        def propose(self, ctx: FourCell) -> dict[str, Any]:
            return write_action({"answer.txt": "x\n"})
        def decompose(self, node: Node, failure_evidence: Any = None,
                      reason: str | None = None) -> list[dict]:
            return []

    new_worker = ThirdPartyWorker()
    # Khung dùng Protocol: nhận worker mới NGAY, không sửa gì.
    assert isinstance(new_worker, Worker)
    assert solve_leaf(node, new_worker).status == "done"
    print("  Worker mới (ThirdPartyWorker) chạy NGAY qua khung Protocol — không sửa solve_leaf.")
    # Còn NO-PATTERN thì nổ:
    try:
        solve_leaf_NO_PATTERN(node, new_worker, [])
        raise AssertionError("đáng lẽ phải TypeError")
    except TypeError as exc:
        print(f"  NO-PATTERN nổ với worker mới: {exc}")

    print("\nKẾT LUẬN: Protocol Worker là 'khung hợp đồng' cố định (propose/decompose).")
    print("Khung gọi solve_leaf/decompose_node giữ THỨ TỰ bước bất biến và chỉ gọi")
    print("hai hook đó. Đổi worker = đổi nội tạng, KHÔNG đổi khung. Đó là Template")
    print("Method ở scale Protocol (structural typing thay cho inheritance).")


if __name__ == "__main__":
    demo()
