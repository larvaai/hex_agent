"""
CASE 03 — OCP qua Worker Protocol + ScriptedWorker/LocalLLMWorker (Strategy)
===========================================================================

Bản DISTILL TRUNG THỰC (chỉ stdlib) của Worker strategy trong hex_agent.

NGUỒN THẬT (đã mở file kiểm chứng):
  - decompose_agent/worker.py:182-185   Worker Protocol: propose(ctx) + decompose(node, ...)
  - decompose_agent/worker.py:188-227   ScriptedWorker — deterministic double (test-friendly)
  - decompose_agent/worker.py:230-301   LocalLLMWorker — LLM-backed (client injectable, retry/backoff)
  - (đối chiếu) supervisor/orchestrator.py:15-39  OrchestratorPort + ScriptedOrchestrator (cùng motif)
  - (đối chiếu) supervisor/llm.py:52-91           ChatLLM Protocol + LLMOrchestrator(llm) DI

Ý TƯỞNG OCP (lesson 25, bảng 2.1 cơ chế #1 — Strategy):
  Switch implementation hoàn toàn ở DEPENDENCY INJECTION, KHÔNG ở conditional.
  Test dùng ScriptedWorker (deterministic), prod dùng LocalLLMWorker (gọi LLM).
  Caller (Decomposer) phụ thuộc Worker Protocol — không biết concrete nào.

  - Worker Protocol = abstraction.
  - ScriptedWorker / LocalLLMWorker / HybridWorker = concrete strategies.
  - Decomposer = caller phụ thuộc abstraction (nhận worker qua constructor).
  - worker injection = extension point: thêm strategy = thêm class, 0 sửa Decomposer.

LƯỢC BỎ so với bản thật:
  - Bỏ FourCell/Node phức tạp, repair ladder JSON, WorkerError, env-var config, backoff thật.
  - LocalLLMWorker dùng FAKE client (callable stdlib), KHÔNG mạng, KHÔNG SDK openai.
  - Giữ NGUYÊN trục Strategy: 2 method (propose/decompose), DI, 2+ impl hoàn toàn khác nhau.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


# ── Domain types tối thiểu (distill ý của FourCell/Node) ─────────────────────────
@dataclass(frozen=True)
class FourCell:
    """Ngữ cảnh để worker đề xuất 1 action (distill: identity + node_id + render())."""

    node_id: str
    identity: str
    goal: str

    def render(self) -> str:
        return f"node={self.node_id} goal={self.goal}"


@dataclass(frozen=True)
class Node:
    id: str
    done_when: tuple[str, ...]


# ── 1. ABSTRACTION: Worker Protocol (distill worker.py:182-185) ─────────────────
@runtime_checkable
class Worker(Protocol):
    """Contract cấu trúc: mỗi strategy phải có propose() + decompose().
    Structural typing (Protocol) — không cần kế thừa."""

    def propose(self, ctx: FourCell) -> dict[str, Any]: ...
    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]: ...


# ── 2. CONCRETE STRATEGY A: ScriptedWorker (distill worker.py:188-227) ──────────
class ScriptedWorker:
    """Deterministic double cho test. propose() tra script[node_id][call_count];
    decompose() dùng decompose_scripts. Hoàn toàn offline."""

    def __init__(self, scripts: dict[str, list[Any]] | None = None,
                 decompose_scripts: dict[str, list[dict]] | None = None) -> None:
        self._scripts = scripts or {}
        self._decompose_scripts = decompose_scripts or {}
        self._calls: dict[str, int] = {}
        self._dcalls: dict[str, int] = {}

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        nid = ctx.node_id
        i = self._calls.get(nid, 0)
        self._calls[nid] = i + 1
        script = self._scripts.get(nid)
        if script:
            item = script[i] if i < len(script) else script[-1]
            return item
        return {"action": "noop", "node": nid}  # không script -> no-op (gate sẽ FAIL)

    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]:
        nid = node.id
        i = self._dcalls.get(nid, 0)
        self._dcalls[nid] = i + 1
        script = self._decompose_scripts.get(nid)
        if script:
            return script[i] if i < len(script) else script[-1]
        # split 2-way mặc định: mỗi con 1 tiêu chí trivial
        return [{"id": f"{nid}.c{j}", "done_when": [f"c{j}.txt"]} for j in range(2)]


# ── 3. CONCRETE STRATEGY B: LocalLLMWorker (distill worker.py:230-301) ──────────
def _fake_llm_client(messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
    """FAKE thay openai client: KHÔNG mạng. Sinh JSON deterministic từ nội dung prompt."""
    user = messages[-1]["content"] if messages else ""
    if "SPLIT" in user:  # nhánh decompose
        nid = user.split("SPLIT:")[-1].strip()
        return json.dumps([{"id": f"{nid}.a", "done_when": ["a.txt"]},
                           {"id": f"{nid}.b", "done_when": ["b.txt"]}])
    return json.dumps({"action": "write", "node": user.split("goal=")[-1].strip()})


class LocalLLMWorker:
    """LLM-backed strategy. `client` injectable (mặc định fake) nên test không chạm mạng.
    Có retry tối thiểu trên 'transient' để giữ đúng motif của bản thật."""

    def __init__(self, *, client: Callable[..., str] | None = None,
                 temperature: float = 0.0, retries: int = 2) -> None:
        self._client = client or _fake_llm_client
        self._temperature = temperature
        self._retries = retries

    def _chat(self, messages: list[dict[str, str]], temperature: float) -> str:
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                return self._client(messages, temperature=temperature)
            except Exception as exc:  # duck-typed transient retry (không import lib bên ngoài)
                last = exc
                if attempt < self._retries:
                    continue
                break
        raise RuntimeError(f"LLM call failed after {self._retries + 1} attempt(s): {last}")

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        raw = self._chat(
            [{"role": "system", "content": ctx.identity},
             {"role": "user", "content": ctx.render()}],
            self._temperature,
        )
        return json.loads(raw)

    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]:
        raw = self._chat(
            [{"role": "system", "content": "You split ONE task into >=2 children."},
             {"role": "user", "content": f"SPLIT:{node.id}"}],
            0.0,
        )
        return json.loads(raw)


# ── 4. CALLER phụ thuộc abstraction: Decomposer ─────────────────────────────────
@dataclass
class Decomposer:
    """Caller. Nhận MỘT Worker qua DI (constructor). KHÔNG có if mode=='scripted' / 'llm'.
    Đổi strategy = đổi đối tượng truyền vào, 0 sửa Decomposer."""

    worker: Worker
    proposals: list[dict] = field(default_factory=list)

    def run(self, ctx: FourCell) -> dict[str, Any]:
        action = self.worker.propose(ctx)
        self.proposals.append(action)
        return action

    def split(self, node: Node) -> list[dict]:
        return self.worker.decompose(node)


# ── 5. EXTENSION DEMO: strategy MỚI mà KHÔNG sửa Decomposer ──────────────────────
class HybridWorker:
    """STRATEGY MỚI ('open for extension'): thử ScriptedWorker trước; nếu node không có
    script (-> action 'noop'), fallback sang LocalLLMWorker. Chỉ cần implement propose()
    + decompose(). Decomposer KHÔNG đổi 1 dòng ('closed for modification')."""

    def __init__(self, scripted: ScriptedWorker, llm: LocalLLMWorker) -> None:
        self._scripted = scripted
        self._llm = llm

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        action = self._scripted.propose(ctx)
        if action.get("action") == "noop":   # không có script -> nhường LLM
            return self._llm.propose(ctx)
        return action

    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]:
        return self._scripted.decompose(node, failure_evidence, reason)


class RandomWorker:
    """STRATEGY MỚI thứ 2: chọn ngẫu nhiên 1 worker từ list cho mỗi propose() (load-spread).
    Lại chỉ 2 method; Decomposer vẫn không đổi."""

    def __init__(self, workers: list[Worker], *, seed: int = 0) -> None:
        self._workers = workers
        self._rng = random.Random(seed)

    def propose(self, ctx: FourCell) -> dict[str, Any]:
        return self._rng.choice(self._workers).propose(ctx)

    def decompose(self, node: Node, failure_evidence: Any = None, reason: str | None = None) -> list[dict]:
        return self._rng.choice(self._workers).decompose(node, failure_evidence, reason)


# ── 6. ĐỐI CHỨNG: nếu KHÔNG dùng Strategy -> if/elif trên mode ──────────────────
def propose_anti_ocp(mode: str, ctx: FourCell, scripts: dict[str, list[Any]]) -> dict[str, Any]:
    """VI PHẠM OCP: dispatch bằng if/elif trên 'mode'. Mỗi mode mới (hybrid, random, async)
    = SỬA chính hàm này. Param signature phình theo (scripts, client, workers, ...)."""
    if mode == "scripted":
        i = 0
        return scripts.get(ctx.node_id, [{"action": "noop"}])[i]
    elif mode == "llm":
        return json.loads(_fake_llm_client([{"role": "user", "content": ctx.render()}]))
    # muốn thêm 'hybrid'? -> phải MỞ hàm này ra, thêm elif + param mới.
    else:
        raise ValueError(f"Unknown worker mode: {mode}")


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — OCP qua Worker Protocol + ScriptedWorker/LocalLLMWorker (Strategy)")
    print("=" * 72)

    ctx = FourCell(node_id="root", identity="builder", goal="ghi file README")
    node = Node(id="root", done_when=("readme.txt", "license.txt"))

    # --- Bước 1: cùng Decomposer, đổi strategy chỉ qua DI ---
    print("\n[1] Cùng 1 Decomposer, swap strategy CHỈ bằng đối số constructor (DI):")
    scripted = ScriptedWorker(scripts={"root": [{"action": "write", "node": "root"}]})
    d_scripted = Decomposer(worker=scripted)
    a1 = d_scripted.run(ctx)
    print("    ScriptedWorker  ->", a1)
    assert a1 == {"action": "write", "node": "root"}

    llm = LocalLLMWorker()  # fake client, không mạng
    d_llm = Decomposer(worker=llm)
    a2 = d_llm.run(ctx)
    print("    LocalLLMWorker  ->", a2)
    assert a2["action"] == "write" and a2["node"] == "ghi file README"

    # Cả 2 cùng đi qua đúng 1 dòng Decomposer.run -> worker.propose(ctx) (polymorphic dispatch).
    assert d_scripted.proposals and d_llm.proposals

    # --- Bước 2: decompose cũng polymorphic ---
    print("\n[2] decompose() cũng polymorphic — mỗi strategy split theo cách riêng:")
    print("    Scripted split:", d_scripted.split(node))
    print("    LLM split:     ", d_llm.split(node))
    assert len(d_scripted.split(node)) == 2 and len(d_llm.split(node)) == 2

    # --- Bước 3: THÊM strategy mới (HybridWorker) — invariant OCP ---
    import inspect
    dec_src_before = inspect.getsource(Decomposer)
    print("\n[3] THÊM HybridWorker (strategy MỚI). Decomposer KHÔNG đổi 1 dòng:")
    hybrid = HybridWorker(
        scripted=ScriptedWorker(scripts={"root": [{"action": "write", "node": "root"}]}),
        llm=LocalLLMWorker(),
    )
    d_hy = Decomposer(worker=hybrid)
    # node 'root' có script -> dùng scripted
    print("    hybrid trên 'root' (có script) ->", d_hy.run(ctx))
    # node 'other' KHÔNG có script -> fallback LLM
    ctx_other = FourCell(node_id="other", identity="builder", goal="task khác")
    print("    hybrid trên 'other' (no script -> LLM fallback) ->", d_hy.run(ctx_other))
    assert d_hy.proposals[0]["node"] == "root"
    assert d_hy.proposals[1]["node"] == "task khác"  # đến từ LLM
    dec_src_after = inspect.getsource(Decomposer)
    assert dec_src_before == dec_src_after, "Decomposer KHÔNG được sửa khi thêm strategy!"
    print("    OK: Decomposer bất biến (closed for modification).")

    # --- Bước 4: strategy thứ 2 (RandomWorker) — vẫn chỉ 2 method ---
    print("\n[4] THÊM RandomWorker — cũng chỉ implement propose()+decompose():")
    rnd = RandomWorker([scripted, LocalLLMWorker()], seed=1)
    d_rnd = Decomposer(worker=rnd)
    print("    random propose ->", d_rnd.run(ctx))
    assert isinstance(d_rnd.proposals[0], dict)

    # --- Bước 5: ĐỐI CHỨNG anti-OCP ---
    print("\n[5] ĐỐI CHỨNG — phiên bản if/elif trên 'mode' (anti-OCP):")
    print("    'scripted' & 'llm' chạy được, nhưng 'hybrid' CHƯA có nhánh:")
    print("    ", propose_anti_ocp("scripted", ctx, {"root": [{"action": "write"}]}))
    try:
        propose_anti_ocp("hybrid", ctx, {})
        raise AssertionError("đáng lẽ phải raise")
    except ValueError as exc:
        print("     hybrid ->", exc)
    print("    => Mỗi mode mới buộc mở lại hàm cũ + thêm param. Strategy + DI loại bỏ điều đó.")

    print("\n[KẾT] Strategy = interface + nhiều impl, swap qua DI; caller bất biến. OCP đạt.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
