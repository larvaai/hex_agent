---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# STATUS — bảng điều khiển build hex_agent (MỘT nơi để quản lý)

> Đây là **mặt quản lý duy nhất**. Mở file này để biết trong 10 giây: đang ở phase nào, bước nào,
> gate nào xanh, AC đạt bao nhiêu. Đừng đi đọc JSON thô rải rác — kéo về đây.
>
> **Hai nguồn sự thật, hai cách cập nhật:**
> - **Gate máy** (DoD / verify / review): chạy `python plans/260626-1358-clone-hex-agent-roadmap/workflow/status.py`
>   → nó render mọi `verification.json` / `review-decision.json` / `plan-approval.json` thành người-đọc-được + cờ đỏ.
>   Chép verdict vào cột tương ứng. **Không tự đọc JSON để quản lý.**
> - **Gate người** (hiểu / AC): bạn tự tick §B sau khi quiz ≥70% (xem `phase-N-build-workflow.md` §6).
>
> **Quy tắc DONE:** một phase ✔ chỉ khi **cột DoD ✔ VÀ cột Hiểu ✔**. Một cột xanh = **chưa xong** → rollback (guide §4).
> Ghi **commit SHA thật** vào Ghi chú (Iron Law: bằng chứng, không lời kể).

---

## A. Bảng tổng — at a glance

Con trỏ "đang ở đây": **Phase __ · bước __**  ·  Cập nhật lần cuối: ____  (chạy `status.py` để làm mới gate máy)

| Phase | Bước loop `S P A C T R` | DoD máy (verify PASS) | Hiểu (quiz ≥70%) | AC đạt | Plan dir (slug) | Ghi chú (SHA / bug) |
|---|---|---|---|---|---|---|
| 1 — Microkernel + chokepoint (E01,E04) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |
| 2 — LLM + discipline (E03,E02) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |
| 3 — Toolbox + safety jail (E06) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |
| 4 — Graph + resume (E05) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |
| 5 — Skills + RAG (E07,E08) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |
| 6 — Roles + delegation (E09,E10) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |
| 7 — Control plane (E21) | ☐☐☐☐☐☐ | ☐ | ☐ | 0/3 | | |

`S P A C T R` = Scout · Plan · Approve · Cook · Test · Review (tick từng bước của vòng lặp chuẩn — guide §1).
Cột **AC đạt** = số nhóm AC ở §B đã tick / 3 (Build · DoD máy · Hiểu). Phase HOÀN TOÀN đạt AC khi = 3/3.

---

## B. AC checklist từng phase — "đạt HOÀN TOÀN" = tick hết 3 nhóm

Mỗi phase có đúng 3 nhóm AC. Tick hết cả 3 mới được điền ✔ vào cột Hiểu+DoD của §A và sang phase kế.

### Phase 1 — Microkernel + chokepoint (E01,E04) · I1–I4
- **Build:** ☐ kernel đăng ký tool → `execute_tool` → envelope chuẩn → event log; ☐ `freeze()` chặn sửa config sau session đầu; ☐ run ghi `var/agent_runs/<id>/{events.jsonl,summary.json}`.
- **DoD máy:** ☐ `python run_smoke.py` → `CORE_AGENT_SMOKE_OK` · ☐ `pytest tests/test_kernel.py tests/test_trace_ids.py tests/test_observability.py tests/test_state.py -q` xanh → `verification.json` verdict PASS.
- **Hiểu (giải thích *luật→file·hàm→phá ra mất gì*):** ☐ I1 một-cửa `execute_tool` ☐ I2 `freeze()` ☐ I3 `KernelSession` cô lập state ☐ I4 lineage trên event.

### Phase 2 — LLM + Output discipline (E03,E02) · I5–I7
- **Build:** ☐ adapter JSON-mode + lazy client (không network lúc import); ☐ `parse_action` cho đúng 1 action/vòng; ☐ budget chặn step/parse-error/same-tool.
- **DoD máy:** ☐ `pytest tests/test_llm_adapter.py tests/test_llm_retry.py tests/test_llm_capability.py tests/test_json_gate_repair.py -q` xanh → verification PASS.
- **Hiểu:** ☐ I5 LLM là capability (`llm.chat` qua cửa) ☐ I6 JSON gate 1-action ☐ I7 budget (parse-error KHÔNG tốn step).

### Phase 3 — Toolbox + Safety jail + middleware (E06) · I8,I9
- **Build:** ☐ `resolve_in_workspace` chặn path traversal; ☐ terminal chạy argv no-shell + timeout; ☐ `SafeToolPort` bọc mọi tool toolbox.
- **DoD máy:** ☐ `pytest tests/test_safety.py tests/test_toolbox.py tests/test_middleware.py tests/test_file_editor.py tests_audit/test_toolbox_sandbox_rigor.py tests_audit/test_security_boundaries.py -q` xanh → verification PASS.
- **Hiểu:** ☐ I8 path-jail ☐ I9 một-cửa-safety + thứ tự middleware (timing→policy→budget→retry→condense) ☐ vì sao retry phải biết idempotency.

### Phase 4 — Graph + resume SQLite-truth (E05) · I10–I12
- **Build:** ☐ `AgentState` chỉ-primitive + codec; ☐ topology 6 node đóng lifecycle đúng 1 lần; ☐ `resume()` qua process-restart đọc SQLite, không chạy lại node đã chạy.
- **DoD máy:** ☐ `pytest tests/test_state.py tests/test_resume.py tests/test_lifecycle.py tests/test_orchestrator.py tests_audit/test_graph_resume_matrix.py tests_audit/test_orchestrator_loop_rigor.py -q` xanh → verification PASS.
- **Hiểu:** ☐ I10 serializable-only ☐ I11 SQLite-truth + `run_id==thread_id` ☐ I12 đóng lifecycle 1 lần.

### Phase 5 — Skills + RAG (E07,E08) · health-gate + ports
- **Build:** ☐ skill render progressive-disclosure; ☐ RAG `health/ingest/search` qua chokepoint; ☐ logic chỉ chạm infra qua `VectorStorePort`, `health()` không ném.
- **DoD máy:** ☐ `pytest tests/test_skills.py tests/test_lens_catalog.py tests_audit/test_rag_edges_rigor.py tests_audit/test_rag_qdrant_adapter_contract.py tests_audit/test_roles_skills_config_integrity.py -q` xanh (offline, không docker) → verification PASS.
- **Hiểu:** ☐ health-gate trước ingest/search ☐ ports tách infra (đổi store = adapter mới) ☐ optional deps `[rag]`.

### Phase 6 — Roles + Multi-agent delegation (E09,E10) · I13–I15
- **Build:** ☐ role enforce allowlist; ☐ delegation chokepoint RIÊNG + scope con ⊆ cha; ☐ TaskLoop/Agent-O acceptance honor evidence thật.
- **DoD máy:** ☐ `pytest tests/test_roles.py tests/test_delegation.py tests/test_supervisor_loop.py tests/test_supervisor_resume.py tests/test_acceptance_gate.py tests/test_evidence.py tests_audit/test_supervisor_adversarial_matrix.py tests_audit/test_session_delegation_state_machine.py -q` xanh → verification PASS.
- **Hiểu:** ☐ I13 delegation tách kernel ☐ I14 scope⊆parent ☐ I15 acceptance ≥1-valid evidence.

### Phase 7 — Realtime control plane (E21) · I16,I17
- **Build:** ☐ RuntimeEvent/Command contract + registry allowlist; ☐ EventEmitter gate→seq→redact→fan-out; ☐ Redactor mask trước khi ra SSE; (E21 còn pending: live transport/UI/reliability — đánh dấu N/A nếu chưa làm).
- **DoD máy:** ☐ `pytest tests/test_control_contracts.py tests/test_control_emitter.py tests/test_fake_control_server.py tests/test_authz_attribution.py tests_audit/test_acceptance_evidence_adversarial.py -q` xanh → verification PASS.
- **Hiểu:** ☐ I16 redact tại biên ☐ I17 attribution≠authz ☐ UI đọc `ui_payload`, không đọc raw payload.

---

## C. Làm mới & đọc artifact (đừng đọc JSON thô)

1. **Toàn cảnh gate máy:** `python plans/260626-1358-clone-hex-agent-roadmap/workflow/status.py`
   → đọc dòng `-> TONG:` mỗi plan (SẴN SÀNG SHIP / ĐANG BỊ CHẶN / CHƯA ĐỦ) + dòng 🔴 cờ đỏ. Chép verdict vào §A.
2. **Một file cụ thể, muốn hiểu sâu:** `/hs:explain plans/<slug>/artifacts/verification.json`
   hoặc prompt 1-dòng: *"Tóm tắt file này thành 1 dòng: stage, verdict, check nào FAIL/detail rỗng, hành động."*
3. **Cờ đỏ phổ biến status.py bắt giúp** (xem guide §2 để xử lý): check FAIL nhưng verdict PASS (gian dối) ·
   `author==reviewer` (tự duyệt) · PASS_WITH_RISK bị tưởng là ship-license · detail rỗng (UNVERIFIABLE).
4. **Một dòng §A chỉ ✔ khi DoD máy ✔ và Hiểu ✔.** Thiếu một → rollback (guide §4), không sang phase kế.

*Quay về: [`00-curriculum-guide.md`](00-curriculum-guide.md) · roadmap [`../README.md`](../README.md).*
