---
title: "Port harness design → control plane: authz doctrine + middleware posture + AC verdict"
slug: control-plane-harness-ports
status: draft
mode: hard
tdd: true
created: 2026-06-26 03:47
owner: namson.nguyen102@gmail.com
decision: DEC-8 (attribution≠authz; permission-edit cần human checkpoint kể cả dưới trust-O)
source_report: plans/reports/port-analysis-260626-0316-harness-design-to-control-plane-report.md
epics: [E21, E06, E10]
phases: 3
depends_on: []   # KHÔNG phụ thuộc command_bridge / pending_commands (DEC-7: chúng không có trên branch)
risk: low-medium — Phase 2 đụng core/kernel.py (file dễ vỡ nhất); Phase 1+3 backward-compatible
standards:
  - docs/code-standards.md          # bất biến §1.1 chokepoint, §1.7 budget, §1.9 hai lớp safety
  - docs/GLOSSARY.md                # trust-O, authority gate, safe checkpoint
  - docs/decisions.md               # DEC register (DEC-7 = lý do command_bridge vắng)
  - docs/explanation/design-decisions.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Port 3 kỷ luật harness vào control plane

> hs:cook đọc file này làm hợp đồng. Claim không hiển nhiên có anchor `file:line`. Tag `[UNVERIFIED]` nếu thiếu.

## Vì sao plan này (cho người mới)

Harness và hex_agent xây **cùng một loại máy**: control plane gate/policy/telemetry cho agent.
Báo cáo port (`source_report`) tìm ra 8 pattern; sau khi đọc code-standards + GLOSSARY + DEC-7,
**phần lớn đã có hoặc YAGNI**. User chốt làm **đủ ba** port đã nêu, right-sized:

- **Port A — doctrine attribution≠authz** (trọng tâm, on-branch, rủi ro thấp).
- **Port C — posture thất bại của middleware** (guardrail nhìn-về-trước; đụng `kernel.py`).
- **Port B — overall verdict trên ac_report** (thêm vào S21.33 đã ship, không sửa logic gate).

## Hiện trạng đã verify (đọc code, KHÔNG qua agent)

- `requires_permission` mới **khai báo** trong `config/runtime_command_types.yaml:11-36` + getter
  `control/command_registry.py:56`; **chưa chỗ nào thực thi**. `command_bridge`/`pending_commands`
  **không tồn tại** trên branch (DEC-7, `docs/decisions.md:90`).
- `UpdateAgentPermission: requires_permission: workflow.modify_permissions`
  (`config/runtime_command_types.yaml:27`); `Permission.can_modify_permissions`
  (`control/permission.py:26`) + `Permission.patched()` (`:38`) tồn tại nhưng **không ai gọi**.
- `IssuedBy` docstring tự nhận "names who acted (for authz + audit)" (`control/commands.py:6`) —
  đúng cái bẫy: `issued_by` là attribution do người phát tự khai.
- GLOSSARY `trust-O`: lệnh O-phát **bỏ qua** `requires_permission`; `authority gate`
  (`supervisor/graph.py:142-147`) chỉ chặn target ngoài roster, **không** chặn cấp quyền.
- `core/kernel.py:139-147` đã try/except quanh middleware chain → middleware ném exception **đã**
  thành `ok=False` (fail-closed cho **mọi** middleware, kể cả advisory).
- `TimingLog` (`middleware/timing.py:18-23`) + `CondenseResult` đã **tự** bọc side-effect →
  bộ middleware hiện tại đã an toàn; Port C là guardrail cho middleware **tương lai**.
- Acceptance gate S21.33 **đã ship**: `supervisor/evidence.py` (evidence_type + ac_report),
  `tests/test_acceptance_gate.py` 8 test xanh; gate FINISHED = `all_accepted()` (`state.py:102`).

## Locked decisions

| # | Quyết định | Lý do / anchor |
|---|---|---|
| LD1 | Làm đủ A+B+C theo user (2026-06-26) nhưng right-sized; ghi caveat YAGNI | scope-challenge; B đã ship, C lý thuyết với bộ middleware hiện tại |
| LD2 | Phase 1 **không** build command_bridge/enforcement; chỉ doctrine doc + predicate thuần ở contract layer + test | DEC-7: bridge vắng trên branch; tránh YAGNI machinery |
| LD3 | `issued_by`/`Actor` = **attribution**; authz = `requires_permission` resolve tại **checkpoint**; permission-edit (`UpdateAgentPermission`→`can_modify_permissions`) cần **human `RuntimeCheckpoint`** kể cả dưới trust-O | harness "actor≠authz" đảo kết luận; `control/checkpoint.py:1-8` đã có surface |
| LD4 | Port C: default posture = **fail-closed** (an toàn); advisory opt-in **fail-open**. Giữ §1.1 (try/except boundary), §1.7 (budget không middleware), §1.9 (PolicyGate default-off) | `docs/code-standards.md:9,127,165` |
| LD5 | Port B: tier ánh xạ harness `PASS_WITH_RISK` → "passed nhưng chỉ evidence `artifact` generic" (tín hiệu thật), KHÔNG bịa tier. Enum `{passed, passed_with_risk, pending}`, policy trong `evidence.py`. Gate FINISHED không đổi | `supervisor/evidence.py:16` (EVIDENCE_TYPES strong vs generic) |

## Phases

| # | Tên | File | Đụng | Rủi ro |
|---|---|---|---|---|
| 1 | Authz≠attribution doctrine + contract predicate | [phase-01](phase-01-authz-attribution-doctrine.md) | `docs/explanation/`, `control/authz.py` (mới), comments | thấp |
| 2 | Middleware failure posture (fail-open/closed) | [phase-02](phase-02-middleware-failure-posture.md) | `core/middleware.py`, `core/kernel.py` | **med** (file dễ vỡ) |
| 3 | Overall verdict trên ac_report | [phase-03](phase-03-ac-report-verdict.md) | `supervisor/evidence.py` | thấp (additive) |

Thứ tự đề xuất: 1 → 3 → 2 (để phần đụng `kernel.py` nằm sau, sau khi suite đã xanh hai lần).

## Out of scope (vòng này)

- Build `command_bridge` / `pending_commands` / **thực thi** `requires_permission` (epic tương lai; doc Phase 1 đặt tên chỗ này).
- UI tiêu thụ verdict (fake backend, DEC-6).
- Posture-mode config YAML cho middleware (YAGNI cho 5 middleware); multi-tier redaction; Kafka transport.
- Đụng logic gate FINISHED của S21.33 (đã xanh, chỉ thêm field).

## Acceptance (plan-level)

1. `python -m pytest -q` xanh (cả `tests/` và `tests_audit/`) — 8 test acceptance cũ vẫn xanh.
2. `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`.
3. `docs/explanation/authz-vs-attribution.md` tồn tại; nêu rõ (a) attribution≠authz, (b) permission-edit cần human checkpoint, (c) **đặt tên** chỗ enforcement bị hoãn.
4. Phase 2: advisory middleware ném exception → tool vẫn chạy (`ok=True`); blocking middleware ném → `ok=False`; ordering + PolicyGate-deny không đổi.
5. Phase 3: `ac_report.verdict ∈ {passed, passed_with_risk, pending}`, policy trong code; 8 test cũ xanh.
6. `python tools/gen_map.py` chạy lại; `CHANGELOG.md` thêm dòng; DEC-pending → DEC số hoá.

## Rollback

- Mỗi phase = 1 commit độc lập. Revert order: 3 → 2 → 1.
- Phase 2 rollback = revert đúng thay đổi `_wrap`/`execute_tool` (1 hàm) ở `core/kernel.py`.
- Phase 1 = xoá doc + `control/authz.py` + test (không ai import → an toàn).
- Phase 3 = bỏ field `verdict` khỏi `record_ac_report` (additive, không ai phụ thuộc cứng).

## Rủi ro & giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Phase 2 phá chokepoint observability (§1.1) | med | TDD; chạy `test_kernel.py`, `test_trace_ids.py`, `test_middleware.py`, `tests_audit/test_middleware_exact_semantics.py` trước/sau |
| Port C YAGNI với middleware hiện tại | thấp | Khung hình "guardrail tương lai" trong doc/comment; default fail-closed an toàn |
| Phase 1 predicate trở thành dead code đến khi bridge ra đời | thấp | Test pin invariant; doc đặt tên call-site tương lai → không phải speculative API |
| Phase 3 verdict bịa nghĩa | thấp | LD5: tier neo vào evidence-strength có thật, không tier rỗng |

## Câu hỏi còn mở

- Tên permission cho human-only approve permission-edit: dùng `workflow.modify_permissions` (đã khai báo) hay tách `checkpoint.approve`? → chốt ở Phase 1 (đề xuất: giữ `workflow.modify_permissions`, doc ghi nó là human-held).
