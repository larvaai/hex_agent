---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery brief — autogen điều khiển multi-agent: port gì vào drag_from_zero?

- Ngày: 2026-06-29 10:27 +07
- Slug: `autogen-control-port-to-dragzero`
- Evidence: [research report — autogen multi-agent control](../reports/research-260629-1027-autogen-multiagent-control-report.md) (verify SOLID, nguồn sơ cấp)

---

## 1. Vấn đề (framing)

User muốn (a) HỌC cách autogen điều khiển multi-agent, (b) biết cơ chế nào đáng mang vào drag_from_zero. Hai hệ điều khiển bằng **triết lý đối nghịch**:

- **autogen** = bàn tròn hội thoại trên message-bus. N agent ngang hàng; một *manager* (LLM ở `SelectorGroupChat`, hoặc handoff ở `Swarm`) quyết **ai nói tiếp**; điều kiện dừng kiểm tra delta mỗi lượt. **Model lái control-flow.**
- **drag_from_zero** = cây giao việc. Cha đẻ con; control chảy cha→con→cha; **code lái control-flow**, model chỉ propose, code adjudicate verdict; dừng bằng **định lý** μ-giảm.

Câu hỏi shape: cái hay của autogen có củng cố drag_from_zero không, hay làm loãng kỷ luật propose/adjudicate?

## 2. Bằng chứng (đã verify)

Chi tiết ở research report. Ba cơ chế, neo nguồn sơ cấp:
- **Actor model (v0.4 `autogen-core`):** runtime sở hữu vòng đời agent; `send_message` (trực tiếp) vs `publish_message` (pub-sub qua `TopicId`/`TypeSubscription`); `RoutedAgent` + `@message_handler`. Async, single-process hoặc gRPC phân tán.
- **Speaker selection:** `RoundRobinGroupChat` (xoay vòng) / `SelectorGroupChat` (**LLM emit tên** người kế, parse regex) / `Swarm` (worker `HandoffMessage.target`) / `MagenticOne` (Orchestrator + ledger).
- **Termination:** `TerminationCondition` compose `&`/`|`, đánh giá trên **delta** mỗi lượt, trả `TaskResult.stop_reason`; 11 built-in. (v0.2: `max_round` + `is_termination_msg` rải rác.)

⚠️ autogen ở **maintenance mode** (~2026); successor MAF. Học **ý tưởng**, không cưới framework.

## 3. Đối chiếu autogen ↔ drag_from_zero (rút gọn)

| Chiều | autogen | drag_from_zero |
|---|---|---|
| Nguồn sự thật | message thread mutable trong RAM | **event log append-only**; view = `reduce(events)` |
| Topology | bàn tròn peer trên message-bus | **cây giao việc** cha→con |
| Ai quyết bước kế | **LLM emit tên** (Selector) / worker handoff | **code**; model chỉ propose |
| Ai phán xong | LLM/`TextMentionTermination('APPROVE')` | **code adjudicate** done_when; worker không ghi verdict |
| Dừng | condition heuristic (count/text/time/token) | **định lý** μ-giảm + MAX_DEPTH + step_budget + STUCK |
| Runtime | async actor, có bản phân tán | **một-process, đồng bộ, stdlib** |
| Quyền | tool gắn agent, honor mọi handoff | **capability token** đóng băng, chỉ thu hẹp |

## 4. Không gian lựa chọn → hướng chọn (PORT / ADAPT / SKIP)

| Cơ chế autogen | Verdict | Lý do (1 dòng) |
|---|---|---|
| **`stop_reason` — bản ghi-kết-thúc có cấu trúc** | **PORT** | Phát một event terminal mang "clause nào cháy" (μ-floor/MAX_DEPTH/budget/STUCK). Trung lập kiến trúc, làm giàu projection — UI render được *vì sao* subtree dừng. |
| **Đánh giá trên DELTA mỗi lượt** | **PORT** | Khớp tự nhiên với fold event-sourced: adjudicate trên delta event mới, không quét lại cả log. Mượn hợp đồng, không mượn mutable-thread. |
| **TerminationCondition compose `&`/`|`** | **ADAPT** | Ý mạnh nhất của autogen, hợp nhất: một đại số stop-predicate and/or map thẳng lên định lý dừng (`MAX_DEPTH | step_budget | μ-floor | STUCK` chính là OR các stop condition). ADAPT vì phải **code-owned**, fold trên event log, giữ bảo đảm của định lý. |
| **`ExternalTermination` (kill-switch) + `reset()`** | **ADAPT** | Nút dừng cho operator hữu ích, nhưng hiện thực bằng **event append vào log**, không phải mutable state. Replay tự "re-arm", bỏ máy raise-until-reset. |
| **MagenticOne Task/Progress Ledger** | **ADAPT** | *Khái niệm* ledger (plan tường minh + theo dõi tiến độ + phát hiện kẹt) vần với decompose + STUCK. Lấy bookkeeping (giữ plan là tree-state code-owned); **bỏ** phần LLM-Orchestrator tự re-plan/giao agent. |
| **LLM speaker-selection (`SelectorGroupChat`/v0.2 `auto`)** | **SKIP** | **Đụng trực diện** kỷ luật lõi: giao control-flow cho model yếu — đúng cái "không field verdict nào worker ghi được" mà drag_from_zero tồn tại để chặn. Cây giao việc đã trả lời "chạy gì kế" bằng code. |
| **Swarm handoff (worker chọn đích kế)** | **SKIP** | Sắc hơn: **worker tự ghi quyết-định-control-flow** qua tool-call. Cha trong cây quyết dispatch con; worker không bàn giao ngang hàng. |
| **Actor runtime (mailbox, pub/sub, `@message_handler`)** | **SKIP** | Đụng cả-kiến-trúc: drag_from_zero một-process đồng bộ stdlib, không cần mailbox/async/topic. Actor giải bài toán phân tán/scale mà drag_from_zero cố ý KHÔNG có; nhận vào = đổi event log replay-được lấy actor graph khó deterministic. |
| **`RoundRobinGroupChat`** | **SKIP** | Primitive của bàn tròn; cây không có vòng để xoay. Thứ tự con là thuộc tính của cây, code quyết. |

**Hướng chọn:** mượn **đại số termination** của autogen làm hình mẫu cho một lớp **stop-condition code-owned, compose được, fold trên event log**, kèm **`stop_reason` event terminal**. Bỏ toàn bộ máy chat/actor/LLM-routing — chúng làm loãng propose/adjudicate.

## 5. Rủi ro

- **Cám dỗ "thêm cho giống autogen":** Selector/Swarm trông tiện nhưng tái nhập "tin model lái control" — đúng anti-pattern. Hàng rào: bất kỳ thứ gì để worker tự định tuyến = từ chối ở review.
- **Over-engineer termination:** định lý hiện tại (`accept.py` + budget) đã dừng đúng. Đại số compose chỉ đáng làm khi có ≥3 stop-clause cần phối hợp tường minh + cần `stop_reason` cho UI. Nếu chưa → YAGNI, để backlog.
- autogen API là moving target + maintenance mode → đừng copy chữ ký, chỉ copy hình dạng.

## 6. Câu hỏi mở

1. drag_from_zero hiện có bao nhiêu stop-clause rời? Nếu đã gom gọn trong orchestrator thì "đại số compose" có thừa không?
2. `stop_reason` đã được phát như một event chưa, hay đang chôn trong log/verdict? (quyết định PORT này S hay đã có).
3. Kill-switch operator có nằm trong use-case local một-người không, hay YAGNI?

## 7. Ngoài phạm vi (OUT)

- Mọi LLM-routing / handoff / actor-runtime / chat-topology của autogen (đã SKIP ở §4).
- Migrate drag_from_zero sang async — vi phạm ràng buộc một-process stdlib.
- Học/port MAF hay Semantic Kernel — ngoài câu hỏi.
- Hệ root hex_agent cũ.

## Next step

- Cơ chế đáng nhất = **stop_reason event** (PORT, có thể S) → trả lời câu hỏi mở #2 trước. Nếu chưa có, đó là một slice nhỏ độc lập.
- "Đại số termination compose" (ADAPT) chỉ vào plan khi câu hỏi mở #1 cho thấy có ≥3 clause cần phối hợp.
- `/clear` trước khi `/hs:plan` nếu quyết làm.
