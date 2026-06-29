---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — Note Committee-Agent + bảng trạng thái

> Áp DEC-8. Tạo `docs/roadmap/future/committee-agent.md`; sửa `docs/roadmap/README.md` §6; thêm GLOSSARY.
> DEC-8 đã chốt nhà = E21 — KHÔNG relitigate E21-vs-E22.

## Step 2.1 — Tạo `docs/roadmap/future/committee-agent.md`

Nội dung (lấy verbatim từ [report §3.1](../reports/brainstorm-260626-0159-prior-art-schema-committee-agent-report.md); anchors giữ nguyên `file:line`):

```markdown
# Committee-Agent — nhiều subagent → 1 lượt agent · `park-with-trigger`

> Living note (roadmap "kho lạnh có nhãn-ngưỡng"). Epic: **E21** (xem [decisions.md](../../decisions.md) DEC-8).
> Đọc cùng [README.md](../README.md) + [dependency-map.md](../dependency-map.md). `deps 🟢` = *được phép* ≠ *nên*.

## 1. problem_solved
Một lượt agent đôi khi cần nhiều "luồng nghĩ" mới trả lời tốt. Gói N subagent đóng góp thinking → tổng hợp thành MỘT message → ngoài nhìn vẫn là 1 agent / 1 lượt. Reasoning trung gian đổ `trash/`, ignore được. Abstraction tầng cao: "một agent" thật ra là một uỷ-ban.

## 2. why_not_now
Delegation hôm nay TUẦN TỰ across-round (`supervisor/graph.py:263-310`); CHƯA within-one-turn fan-out; CHƯA có bước aggregate/reduce (`grep -rniE 'aggregate|ensemble|committee' --include=*.py` non-test = 0). Chưa nhu cầu đo được (≤2 delegation call-site; subagent/run ~1–5). Chưa chốt chiến lược gộp (vote/concat/LLM-summary).

## 3. current_anchors (verbatim)
- `adapters/agents/langgraph_agent.py:83-95` — turn output = `DelegationResult{summary, artifacts}` (xác nhận "output 1 lượt = 1 message").
- `supervisor/graph.py:263-310` (`run_round`) — vòng `next_agent_calls`, delegate TUẦN TỰ, merge Blackboard. KHÔNG có bước aggregate.
- `supervisor/loop.py:147-239` (`_drive`) + `:249-259` (`_result.final_output`) — delegation HIỆN across-round, CHƯA within-one-turn.
- `var/agent_runs/<run_id>/` (`observability/event_log.py:34-54`) — sink reasoning hiện có (`events.jsonl`).
- `control/events.py` (`RuntimeEvent`, `TraceContext.child` parent/child span) + `control/redaction.py` (`RedactionInfo.level=internal`) — máy móc E21 để hiện/ẩn sub-round.

## 3b. prior_art (external anchor — proof-of-FEASIBILITY ≠ proof-of-NEED)
- Mixture-of-Agents — https://arxiv.org/abs/2406.04692 — mechanism:"N proposer agent → aggregator tổng hợp → 1 output, layered" — checked:2026-06-26
- Self-Refine — https://arxiv.org/abs/2303.17651 — mechanism:"1 LLM lặp generate→tự-phê→refine" — checked:2026-06-26
- Least-to-Most — https://arxiv.org/abs/2205.10625 — mechanism:"chia bài toán con→giải tuần tự→re-feed" — checked:2026-06-26

## 4. wiring_threshold (đo được — prior-art KHÔNG ở đây, KHÔNG phải trigger)
- subagent/round > 3 thường xuyên (ensemble có giá) — đếm `next_agent_calls` trong `var/agent_runs`.
- ≥1 report đo nhu cầu "1 lượt cần nhiều luồng nghĩ" (chất lượng/độ trễ).
- E21 T1 (event+redaction) release (gate cho phần observe/trash-channel).

## 5. wiring_sketch (seam file:line)
Wrap `run_round` (`supervisor/graph.py:263-310`): sau vòng delegate, thêm bước AGGREGATE (vote/concat/LLM-summary, cấu hình được) → 1 message cho O. Subagent reasoning → `var/agent_runs/<run_id>/trash/round_k/` với `redaction.level="internal"` (`control/redaction.py`) → ẩn mặc định ở UI, fetch raw qua payload inspector. Tái dùng `TraceContext.child` (`control/events.py`) link sub-round vào parent span. KHÔNG subsystem song song; chạy N subagent SONG SONG mới đụng async — ghi nhận là phần đắt.

## 6. dependencies (cổng)
gate-in: E10 (TaskLoop/DelegationManager — `supervisor/graph.py`) 🟢. Phần CORE (fan-out+aggregate) là orchestration MỚI, KHÔNG phải E21.
gate: E21 T1 (`control/events.py` + redaction) cho phần observe/ẩn/trash-channel 🟡 (đang làm — Phase A+B1).
**CARVE**: E21 SỞ HỮU phần quan-sát/redact/trash của committee-turn; phần fan-out+aggregate là năng-lực orchestration (E10-adjacent) mà E21 tiêu thụ.

## 7. critique (YAGNI · proven ≠ needed)
proven-elsewhere != needed-here: MoA chứng minh committee-of-agents ở model frontier / NHIỀU model khác nhau, CHƯA chứng minh ở cụm subagent dùng model NHỎ giống nhau. Hôm nay 0 hạ tầng aggregate + delegation tuần tự across-turn → đây KHÔNG phải wiring mỏng, là orchestration mới + chọn chiến lược gộp + (có thể) concurrency. Rẻ nhất: aggregate TUẦN TỰ (concat/LLM-summary) trên `run_round`, KHÔNG song-song-hoá vội.

## 8. verdict
`park-with-trigger`. Tầng rã đông: bước aggregate tuần tự trên `run_round` + `trash/` redaction; kích khi subagent/round >3 hoặc có report đo nhu cầu "1 lượt nhiều luồng nghĩ".
```

> Lưu ý nhãn mục: note này dùng `## 1..8` + `## 3b` để khớp 9-trường (prior_art = 3b). Khác note epic cũ ở chỗ có thêm `prior_art` — đúng schema DEC-7.

## Step 2.2 — README.md §6 bảng trạng thái

Thêm 1 dòng vào bảng §6 (`docs/roadmap/README.md`):

```
| [Committee-Agent](future/committee-agent.md) | park-with-trigger | future | — | E21 (observe) + E10 (core) | 2026-06-26 |
```

## Step 2.3 — GLOSSARY.md +1 hàng

```
| Committee-Agent | Abstraction tầng-agent: N subagent đóng góp thinking, gộp thành MỘT lượt agent (output 1 message), reasoning trung gian đổ `trash/`. Parked future-note ([roadmap/future/committee-agent.md](roadmap/future/committee-agent.md), DEC-8). E21 sở hữu phần observe/redact/trash; fan-out+aggregate core = orchestration (gate-in E10). |
```

## Acceptance (phase 2)

- `test -f docs/roadmap/future/committee-agent.md` → tồn tại; `grep -c '^## ' docs/roadmap/future/committee-agent.md` → ≥9.
- `grep -n 'committee-agent\|Committee-Agent' docs/roadmap/README.md` → §6 có dòng mới.
- `grep -c 'Committee-Agent' docs/GLOSSARY.md` → ≥1.
- URL + file:line trong note verbatim khớp report §3.1.
