"""
Case 01 — Customer-Supplier giữa Supervisor Context và Delegation Context.

Bản DISTILL TRUNG THỰC (chỉ stdlib) của các đoạn code thật trong hex_agent:

  Nguồn thật (đã mở file kiểm chứng):
  - supervisor/contracts.py:39-45   AgentAssignment (Agent O cấp scope qua allowed_capabilities)
  - supervisor/contracts.py:59-73   ContextPacket: KHÔNG có trường scope; to_spec() loại scope ra
  - supervisor/graph.py:152-179     run_round: Broker viết packet (chỉ shape info),
                                    rồi tạo DelegationPolicy CHỈ từ assignment.allowed_capabilities (S10.14)
  - supervisor/graph.py:158-162     Broker không được đổi target turn sang agent khác
  - core/schemas.py:158-178         DelegationPolicy (hợp đồng Published giữa 2 context)
  - core/schemas.py:132-155         DelegationSpec (DTO mang objective + briefing, KHÔNG mang scope)
  - delegation/manager.py:63-80     DelegationManager.delegate() nhận DelegationPolicy từ upstream O
  - delegation/policy.py:13-32      DelegationPolicyEngine.validate(): scope con phải ⊆ scope cha
  - roles/agent.py:42-54            Worker (Agent) enforce allowlist qua guard_tool_call()

Bài học Bounded Context được minh hoạ:
  * Supervisor = UPSTREAM SUPPLIER: O quyết định scope (allowed_capabilities).
  * Delegation  = DOWNSTREAM CUSTOMER: nhận DelegationPolicy và bắt buộc tôn trọng.
  * DelegationPolicy = hợp đồng Published Language giữa hai context.
  * ContextPacket = Anti-Corruption boundary: Broker chỉ "nắn" thông tin, KHÔNG bao giờ đặt scope.
    => Quyền cấp scope (authorization) không bao giờ rò qua đường nắn-thông-tin.

Hạ tầng nặng được thay bằng fake stdlib tối thiểu:
  - Không có LLM thật: Agent O và Broker là hàm Python xác định (deterministic).
  - Không có KernelSession/SQLite/event bus: lược bỏ, chỉ giữ nguyên các hợp đồng dữ liệu.
  - Không có DelegationStore/child session thật: worker là một hàm chạy ngay tại chỗ.

Chạy: python3 supervisor_delegation_customer_supplier.py  ->  exit code 0, không traceback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ════════════════════════════════════════════════════════════════════════════
# SUPERVISOR CONTEXT — ngôn ngữ riêng: "Assignment", "ContextPacket", "Agent O", "Broker"
#   Trong context này, "Agent" nghĩa là MỘT QUYẾT ĐỊNH ĐIỀU PHỐI (orchestration decision),
#   không phải process thực thi.
# ════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AgentAssignment:
    """Distill của supervisor/contracts.py:39-45.

    Đây là nơi DUY NHẤT scope của một worker được khai báo: allowed_capabilities.
    O (orchestrator) là người điền trường này.
    """
    agent_id: str
    objective: str
    allowed_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DelegationSpec:
    """Distill của core/schemas.py:132-155 — DTO đi qua biên giới context.

    CHÚ Ý: KHÔNG có trường scope/allowed_capabilities ở đây. Spec chỉ mang
    *thông tin* (objective + briefing), không mang *quyền*.
    """
    objective: str
    input_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextPacket:
    """Distill của supervisor/contracts.py:59-73.

    Broker viết 'briefing' để nắn ngữ cảnh cho worker. Packet CỐ Ý không có
    trường scope: "Scope is NOT here — O/policy owns it" (comment gốc dòng 68).
    """
    target_agent_id: str
    objective: str
    briefing: str                      # Broker viết phần này
    source_ids: tuple[str, ...] = ()

    def to_spec(self) -> DelegationSpec:
        # Ánh xạ packet -> DelegationSpec, CỐ Ý loại scope ra (supervisor/contracts.py:67-73).
        return DelegationSpec(
            objective=self.objective,
            input_context={"briefing": self.briefing, "source_ids": list(self.source_ids)},
        )


def orchestrator_decide_assignment(task: str) -> AgentAssignment:
    """Fake 'Agent O' xác định thay cho LLM.

    O là kẻ DUY NHẤT cấp scope. Ở đây O quyết: worker 'writer' chỉ được dùng
    hai capability 'fs_read' và 'fs_write' — KHÔNG có 'terminal_run'.
    """
    return AgentAssignment(
        agent_id="writer",
        objective=f"Soạn tài liệu cho: {task}",
        allowed_capabilities=("fs_read", "fs_write"),
    )


class Broker:
    """Fake 'Context Broker'. Vai trò: SHAPE INFORMATION ONLY (S10.4/S10.14).

    Broker có thể viết briefing thoải mái, nhưng KHÔNG có cách nào đặt scope:
    ContextPacket không có trường scope, nên dù Broker "muốn" leo thang quyền
    cũng không có chỗ để ghi.
    """

    def write_packet(self, assignment: AgentAssignment, store_slice: list[dict[str, Any]]) -> ContextPacket:
        briefing = "Tham chiếu: " + "; ".join(s["text"] for s in store_slice) if store_slice else "(rỗng)"
        return ContextPacket(
            target_agent_id=assignment.agent_id,
            objective=assignment.objective,
            briefing=briefing,
            source_ids=tuple(s["id"] for s in store_slice),
        )


# ════════════════════════════════════════════════════════════════════════════
# PUBLISHED LANGUAGE — hợp đồng giữa hai context: DelegationPolicy
#   Đây là DTO chung (core/schemas.py), không thuộc riêng context nào.
# ════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DelegationPolicy:
    """Distill của core/schemas.py:158-178.

    allowed_capabilities là CƠ CHẾ DUY NHẤT để scope đi vào Delegation Context.
    """
    allowed_capabilities: frozenset[str] = frozenset()
    max_depth: int = 3


# ════════════════════════════════════════════════════════════════════════════
# DELEGATION CONTEXT — ngôn ngữ riêng: "target", "policy", "DelegationManager"
#   Trong context này, "agent" nghĩa là MỘT TARGET THỰC THI (execution target).
# ════════════════════════════════════════════════════════════════════════════

class CapabilityScopeError(PermissionError):
    """Tương ứng PermissionError trong delegation/policy.py:26-27."""


class DelegationPolicyEngine:
    """Distill của delegation/policy.py:13-32.

    Bất biến cốt lõi: scope con phải là TẬP CON của scope cha.
    """

    def __init__(self, parent_scope: frozenset[str], parent_depth: int = 0) -> None:
        self.parent_scope = parent_scope
        self.parent_depth = parent_depth

    def validate(self, requested: DelegationPolicy) -> DelegationPolicy:
        scope = requested.allowed_capabilities or self.parent_scope
        if not scope <= self.parent_scope:
            raise CapabilityScopeError(
                "Delegation capability scope exceeds the parent scope."
            )
        if self.parent_depth + 1 > requested.max_depth:
            raise CapabilityScopeError("Delegation depth limit exceeded.")
        return DelegationPolicy(allowed_capabilities=frozenset(scope), max_depth=requested.max_depth)


@dataclass(frozen=True)
class DelegationResult:
    """Distill rút gọn của core/schemas.py:235-252."""
    outcome: str                       # "success" | "rejected" | "failed"
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# Worker = một hàm chạy với scope đã được áp. Trong code thật đây là child session
# + roles.Agent.guard_tool_call (roles/agent.py:42-54). Ở đây ta dùng closure đơn giản.
WorkerFn = Callable[[DelegationSpec, frozenset[str]], DelegationResult]


class DelegationManager:
    """Distill của delegation/manager.py:63-80.

    delegate() nhận DelegationPolicy do upstream O thiết lập; policy.allowed_capabilities
    là điểm DUY NHẤT scope nhập vào context này.
    """

    def __init__(self, engine: DelegationPolicyEngine) -> None:
        self._engine = engine

    def delegate(
        self,
        target: str,
        spec: DelegationSpec,
        policy: DelegationPolicy,
        worker: WorkerFn,
    ) -> DelegationResult:
        if not target:
            raise ValueError("Delegation target must not be empty.")
        if not spec.objective:
            raise ValueError("Delegation objective must not be empty.")
        try:
            active_policy = self._engine.validate(policy)   # cổng scope (delegation/manager.py:80)
        except CapabilityScopeError as exc:
            return DelegationResult(outcome="rejected", error=str(exc))
        # Worker CHỈ thấy scope đã duyệt — không thấy gì khác từ Supervisor Context.
        return worker(spec, active_policy.allowed_capabilities)


# ════════════════════════════════════════════════════════════════════════════
# WORKER (roles context) — enforcer của allowlist. Distill roles/agent.py:42-54.
# ════════════════════════════════════════════════════════════════════════════

def make_writer_worker() -> WorkerFn:
    """Worker chỉ gọi tool nằm trong scope; tool ngoài scope -> blocker (guard_tool_call)."""

    def guard_tool_call(tool: str, scope: frozenset[str]) -> dict | None:
        if tool in scope:
            return None
        return {"finish_reason": "blocker", "blocked_tool": tool,
                "reason": f"Tool '{tool}' nằm ngoài allowlist của worker."}

    def worker(spec: DelegationSpec, scope: frozenset[str]) -> DelegationResult:
        # worker muốn: đọc file, ghi file (hợp lệ) — rồi thử chạy terminal (ngoài scope).
        plan = ["fs_read", "fs_write", "terminal_run"]
        executed: list[str] = []
        for tool in plan:
            blocker = guard_tool_call(tool, scope)
            if blocker is not None:
                # Đúng pattern: worker bị chặn ngay khi vượt scope do O cấp.
                return DelegationResult(
                    outcome="success",
                    summary={"executed": executed, "blocked": blocker["blocked_tool"]},
                )
            executed.append(tool)
        return DelegationResult(outcome="success", summary={"executed": executed, "blocked": None})

    return worker


# ════════════════════════════════════════════════════════════════════════════
# run_round — distill supervisor/graph.py:152-179 (đường đi Customer-Supplier).
# ════════════════════════════════════════════════════════════════════════════

def run_round(
    task: str,
    broker: Broker,
    manager: DelegationManager,
    worker: WorkerFn,
    *,
    tamper_packet_scope: bool = False,
) -> DelegationResult:
    """Một vòng: O quyết -> Broker nắn info -> tạo policy TỪ O -> delegate.

    tamper_packet_scope mô phỏng đối chứng: nếu ta CỐ để Broker/packet quyết scope
    thay vì O, ta sẽ thấy nó vô hiệu — vì packet không có trường scope.
    """
    assignment = orchestrator_decide_assignment(task)              # graph.py:112-123 (rút gọn)
    store_slice = [{"id": "art-0001", "text": "ghi chú nền"}]
    packet = broker.write_packet(assignment, store_slice)          # graph.py:155-156

    # Authority/target check: Broker không được đổi target (graph.py:158-162).
    if packet.target_agent_id != assignment.agent_id:
        raise PermissionError("Broker packet target does not match assigned agent.")

    if tamper_packet_scope:
        # Cố tình "muốn" packet quyết scope rộng hơn. ContextPacket KHÔNG có chỗ ghi scope,
        # nên ý đồ này không thể hiện thực hoá: ta vẫn buộc phải lấy scope từ O.
        # (Đây chính là Anti-Corruption boundary — supervisor/contracts.py:59,67-73.)
        pass

    # Scope comes ONLY from O's assignment — never from the Broker (graph.py:175-176, S10.14).
    policy = DelegationPolicy(allowed_capabilities=frozenset(assignment.allowed_capabilities))
    return manager.delegate(assignment.agent_id, packet.to_spec(), policy, worker)  # graph.py:177-179


# ════════════════════════════════════════════════════════════════════════════
# DEMO
# ════════════════════════════════════════════════════════════════════════════

def demo() -> None:
    print("=" * 74)
    print("CASE 01 — Customer-Supplier: Supervisor (supplier) -> Delegation (customer)")
    print("=" * 74)

    # Scope cha của Supervisor (giới hạn tối đa mà O có thể cấp xuống).
    parent_scope = frozenset({"fs_read", "fs_write", "rag_search"})
    engine = DelegationPolicyEngine(parent_scope=parent_scope, parent_depth=0)
    manager = DelegationManager(engine)
    broker = Broker()
    worker = make_writer_worker()

    print("\n[1] Agent O (UPSTREAM SUPPLIER) quyết định scope cho worker.")
    assignment = orchestrator_decide_assignment("viết README")
    print(f"    assignment.agent_id            = {assignment.agent_id!r}")
    print(f"    assignment.allowed_capabilities = {assignment.allowed_capabilities}")
    print("    -> Trong SUPERVISOR context, 'agent' = một quyết định điều phối.")

    print("\n[2] Broker chỉ NẮN THÔNG TIN (briefing). ContextPacket KHÔNG có trường scope.")
    packet = broker.write_packet(assignment, [{"id": "art-0001", "text": "ghi chú nền"}])
    packet_fields = set(vars(packet).keys())
    print(f"    Các trường của ContextPacket   = {sorted(packet_fields)}")
    assert "allowed_capabilities" not in packet_fields, "Packet không được mang scope!"
    assert "scope" not in packet_fields, "Packet không được mang scope!"
    print("    -> ASSERT: packet không hề có 'scope'/'allowed_capabilities'. (Anti-Corruption boundary)")

    print("\n[3] DelegationSpec (DTO qua biên giới) cũng KHÔNG mang scope.")
    spec = packet.to_spec()
    spec_fields = set(vars(spec).keys())
    print(f"    Các trường của DelegationSpec  = {sorted(spec_fields)}")
    assert "allowed_capabilities" not in spec_fields and "scope" not in spec_fields
    print("    -> ASSERT: scope không lọt qua DTO. Quyền và thông tin tách bạch.")

    print("\n[4] Scope đi vào DELEGATION context CHỈ qua DelegationPolicy dựng từ assignment.")
    result = run_round("viết README", broker, manager, worker)
    print(f"    worker outcome = {result.outcome}")
    print(f"    worker executed = {result.summary.get('executed')}")
    print(f"    worker blocked  = {result.summary.get('blocked')!r}")
    assert result.outcome == "success"
    assert result.summary["executed"] == ["fs_read", "fs_write"], "Chỉ chạy tool trong scope O cấp."
    assert result.summary["blocked"] == "terminal_run", "terminal_run phải bị chặn (ngoài scope)."
    print("    -> ASSERT: worker chạy đúng fs_read/fs_write; terminal_run bị chặn.")
    print("       (Customer tôn trọng hợp đồng scope do Supplier ban hành.)")

    print("\n[5] Thử LEO THANG qua Broker/packet (đối chứng): không có tác dụng.")
    result2 = run_round("viết README", broker, manager, worker, tamper_packet_scope=True)
    assert result2.summary["blocked"] == "terminal_run", (
        "Dù Broker 'muốn' nới scope, packet không có chỗ ghi scope nên vô hiệu."
    )
    print("    -> ASSERT: Broker KHÔNG thể nới scope. Vì packet không có trường scope,")
    print("       quyền không thể rò qua đường nắn-thông-tin. (đây là điểm cốt lõi)")

    print("\n[6] Bất biến scope ⊆ parent: O không thể cấp capability vượt scope cha.")
    over_scope_policy = DelegationPolicy(allowed_capabilities=frozenset({"fs_read", "net_exec"}))
    rejected = manager.delegate("writer", spec, over_scope_policy, worker)
    print(f"    delegate(scope=fs_read+net_exec) -> outcome = {rejected.outcome}")
    print(f"    error = {rejected.error}")
    assert rejected.outcome == "rejected", "Scope vượt parent phải bị từ chối."
    assert "exceeds the parent scope" in (rejected.error or "")
    print("    -> ASSERT: scope vượt parent bị từ chối (delegation/policy.py:26).")

    print("\n[ĐỐI CHỨNG] Nếu KHÔNG có biên giới: một class 'Agent' dùng chung.")
    no_boundary_anti_pattern()

    print("\n" + "=" * 74)
    print("KẾT LUẬN: 'agent' nghĩa khác nhau ở 2 context; scope chỉ chảy qua hợp đồng")
    print("DelegationPolicy (Published Language). Broker nắn info, O cấp scope — tách bạch.")
    print("=" * 74)


def no_boundary_anti_pattern() -> None:
    """Mô phỏng kiểu KHÔNG có Bounded Context: một class God-'Agent' gánh mọi nghĩa.

    Hậu quả: 'agent' vừa là quyết định điều phối, vừa là target thực thi, vừa giữ scope,
    vừa giữ briefing. Broker và O cùng ghi vào một object => quyền rò lẫn với thông tin.
    """

    class GodAgent:
        def __init__(self) -> None:
            self.agent_id = "writer"
            self.objective = ""
            self.briefing = ""               # đáng lẽ thuộc Broker (info)
            self.allowed_capabilities: set[str] = set()  # đáng lẽ chỉ O được đặt (quyền)

    god = GodAgent()
    # O đặt scope hẹp...
    god.allowed_capabilities = {"fs_read", "fs_write"}
    # ...nhưng Broker (chỉ nên nắn info) lại "tiện tay" ghi cả scope vì cùng một object:
    god.briefing = "tham chiếu nền"
    god.allowed_capabilities.add("terminal_run")   # <-- rò quyền! không có tường ngăn.
    print(f"    GodAgent.allowed_capabilities sau khi Broker đụng vào = {sorted(god.allowed_capabilities)}")
    assert "terminal_run" in god.allowed_capabilities
    print("    -> Vì KHÔNG tách context, Broker (info) vô tình leo thang quyền worker.")
    print("       Đây đúng là lỗi mà ContextPacket-không-scope ngăn chặn được.")


if __name__ == "__main__":
    demo()
