---
type: brainstorm
slug: control-tower-ui-delta
created: 2026-06-26 02:26
mode: brainstorm (diverge→converge, standard rigor)
scope: chắt lọc delta UI "Agent Runtime Control Tower" vs spec E21 đã có
epics: [E21]
related:
  - docs/spec/active/E21-realtime-control-plane/02_FULL_FEATURE_MAP.md
  - docs/spec/active/E21-realtime-control-plane/acceptance.md
  - plans/260626-0212-e21-control-plane-ui-fake-backend/plan.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — Control Tower UI: chắt lọc DELTA (không phải PRD lần hai)

## 1. Điều phải nói trước mọi thứ

Bản PRD "Agent Runtime Control Tower" (25 feature) **không phải đất trống**. Spec E21 hiện
hữu đã có **52 story `S21.1–S21.52`** + acceptance map 1–1, và
[02_FULL_FEATURE_MAP.md:3](../../docs/spec/active/E21-realtime-control-plane/02_FULL_FEATURE_MAP.md)
mở đầu bằng đúng câu: *"Bạn gửi một PRD đầy đủ 20 Feature (superset của bản đầu). File này
đối chiếu từng feature với E21..."*.

→ Việc "vét cạn PRD→feature→epic→story→AC" **đã làm rồi** cho gần như cùng PRD này. Viết
lại = lặp (DRY), đốt token, 0 tri thức mới. Giá trị thật = **chắt DELTA** (cái spec CHƯA có)
và **vạch cut-line** (cái nên cắt). Đó là nội dung report này.

## 2. Vì sao 7 nguyên tắc đã được lo "by construction"

Không phải lời hứa trong doc — nằm trong dataclass thật, có test (`tests/test_control_*`):

| Nguyên tắc | Ép ở đâu (bằng chứng) |
|---|---|
| Không sửa state trực tiếp | Can thiệp = `RuntimeCommand`; `parse_command` reject nếu thiếu key [commands.py:100](../../control/commands.py) |
| Không hành động ngầm | `EventTypeRegistry.assert_known` chặn event lạ [event_registry.py](../../control/event_registry.py) |
| Replay được | `RuntimeEvent.seq` đơn điệu/session + `durable` flag [events.py:193](../../control/events.py) |
| Payload inspect + redact | `payload` (raw) vs `ui_payload` (redacted) tách cứng [events.py:113-132](../../control/events.py) |
| Quyết định có evidence | `S21.33`: AC `passed` cần ≥1 evidence, thiếu ⇒ không `finished` [acceptance.md](../../docs/spec/active/E21-realtime-control-plane/acceptance.md) |
| Causal trace ("Why?") | `trace_id/span_id/parent_span_id` đã có trong **mọi** event [events.py:53-82](../../control/events.py) + `S21.41/42` |
| Bảo vệ user khỏi UI | `RuntimeCheckpoint` risk `low/medium/high/dangerous` + transition-guard [checkpoint.py:18-20,57-68](../../control/checkpoint.py) |

**Điểm sướng nhất:** "đinh" Causal Trace gần **miễn phí** — dữ liệu nhân-quả đã nằm trong envelope.

## 3. Bảng DELTA — chỉ cái PRD dán CÓ mà E21 CHƯA có

Đối chiếu từng ý với 52 story + 2 registry thật (`config/runtime_{command,event}_types.yaml`):

| Delta | E21 đã có? | Verdict | Bằng chứng |
|---|---|---|---|
| Approve-with-instruction | ✗ | Hoãn (rẻ) | registry chỉ `ApproveCheckpoint` [runtime_command_types.yaml:27](../../config/runtime_command_types.yaml) |
| Blast Radius Preview | ✗ | Hoãn (rẻ→vừa) | `Permission` thiếu `allowed_artifact_paths` [permission.py:20-27](../../control/permission.py) |
| **Attach-Evidence / Request-Reviewer (command)** | ✗ | **GREENLIT** | `S21.33` có evidence-types, **không có command** để gắn/yêu cầu |
| **Preflight Simulation** | ✗ | **GREENLIT — discovery riêng** | cần O "dry-run 1 round không execute" = năng lực orchestrator MỚI |
| Fork Session + Compare | ✗ | CẮT (YAGNI) | không có `ForkSession`; cost cao; `S21.23` Replay đã cho ~80% giá trị debug |
| Ops UI (Kafka/Redis/deadletter/worker) | T2/X | CẮT (YAGNI) | hạ tầng chưa tồn tại (in-process JSONL); `S21.45` health/metrics đủ |
| RBAC routing / notify theo role | — | CẮT (gold-plating) | tool local 1 user; authz đã thu về "static-token seam"; `S21.37` là lát đúng |
| Saved views / layout / Cmd+K / a11y | một phần | SAU (build cuối) | polish, 0 rủi ro kiến trúc khi hoãn |

## 4. Quyết định phiên này (cut-line user đã chốt)

- **GREENLIT (làm tiếp):**
  1. `AttachEvidenceToAC` + `RequestReviewer` — command mới, đóng nốt AC action loop.
  2. **Preflight Simulation** — mở `hs-research:discover` riêng (không build now).
- **HOÃN — rẻ, để backlog "consider" (user không chọn round này):** Approve-with-instruction,
  Blast Radius Preview. Ghi lại vì cả hai contract-backed, chi phí thấp nếu revisit.
- **CẮT (YAGNI/gold-plating):** Fork Session, Ops UI, RBAC routing, full a11y/saved-views.
  Feature map của chính dự án đã tier chúng ra T2/X — kéo vào v1 là "core phình to".

> Honest note: 2 món HOÃN rẻ hơn 2 món GREENLIT, và Preflight là món đắt nhất + build được
> muộn nhất (phụ thuộc live backend). Đây là đánh đổi user chấp nhận, ghi để khỏi đào lại.

## 5. Next-step cụ thể cho 2 món greenlit

### 5a. Attach-Evidence / Request-Reviewer (nhỏ, contract-backed → đi thẳng `/hs:plan`)
- Thêm 2 `command_type` vào [runtime_command_types.yaml](../../config/runtime_command_types.yaml):
  - `AttachEvidenceToAC` — `payload: {ac_id, evidence_ref:{type∈artifact|tool_result|reviewer_report|diff|test_result, id}}`; `apply_at: next_checkpoint`.
  - `RequestReviewer` — `payload: {ac_id, reviewer_agent_id, instruction}`; `apply_at: next_checkpoint`; `requires_permission: workflow.modify_agents` (tái dùng).
- Resolve evidence trên Blackboard (siết `S21.33`); O tạo reviewer `AgentInvocation` qua path
  pending-command sẵn có (`S21.13`).
- Không cần dataclass mới: `RuntimeCommand` đã đủ shape — chỉ thêm type + xử lý ở O.

### 5b. Preflight Simulation (mở `hs-research:discover` — câu hỏi cần trả lời)
1. O cần **mode dry-run** tách riêng, hay chặn `OrchestratorDecision` *trước* execute là đủ?
2. Contract "preflight result" = event mới (`preflight.computed`) hay API đồng bộ? Field gì
   (predicted agents/hooks/tools/checkpoints/risks)?
3. **Rủi ro lõi:** LLM nondeterministic → preview có thể lệch reality. Preview sai *nguy hiểm
   hơn* không có. Discovery phải định lượng "preview đáng tin tới đâu".
4. **Phụ thuộc:** cần live backend emit. Plan hiện tại
   ([260626-0212](../../plans/260626-0212-e21-control-plane-ui-fake-backend/plan.md)) là *fake
   backend* → Preflight build được **sớm nhất sau** lát live-wiring.

## 6. Sequencing (đừng đảo thứ tự)

```
1. SHIP plan T1 đang có (260626-0212, 7 phase) ── xương sống, fake backend
2. Live-wiring slice (supervisor emit thật → snapshot)   ── chưa có plan
3. Attach-Evidence/Request-Reviewer  ── nhỏ, làm cạnh (2) hoặc sau
4. Preflight discovery → plan         ── CHỈ sau (2) live emit
   (Approve-with-instruction + Blast Radius: chèn vào (3) nếu đổi ý — rẻ)
```

Lý do thứ tự: drag/drop, preflight, blast-radius chỉ *an toàn/khả thi* khi đã có command
schema + checkpoint + permission + event projection — tất cả nằm ở (1)-(2). Bắt đầu bằng món
đẹp mắt trước là lật ngược rủi ro.

## 7. Câu hỏi mở (chưa giải)

1. **Live-wiring chưa có plan.** Mọi món greenlit (nhất là Preflight) chặn sau nó. Ai/lúc nào
   viết lát "supervisor emit envelope thật → build_snapshot"? Đây là nút cổ chai thật.
2. **Permission tier "profile"** (read_only_reviewer / artifact_writer / admin_agent trong PRD)
   chưa có trong [permission.py](../../control/permission.py) (mới có fine-grained + effective_from).
   Có cần tầng profile, hay fine-grained là đủ cho 1 user local? — chưa quyết.
3. **DEC cut-line:** có muốn ghi sổ "cắt Fork/Ops/RBAC khỏi E21 v1" qua
   `decision_register.py` để chặn re-litigate không? Đây là scope decision, chưa phải DEC kiến
   trúc — tôi chưa tự ghi.
