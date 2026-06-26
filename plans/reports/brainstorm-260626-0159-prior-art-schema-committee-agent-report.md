---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — Trường `prior_art` cho roadmap future + note Committee-Agent (E21)

> Skill: `hs-think:brainstorm`. Ngày 2026-06-26. Branch `main`.
> Câu hỏi gốc: lưu ý tưởng đột phá (đã chứng minh chạy được ngoài internet) như "sản phẩm chờ lắp", không chỉ là note mơ hồ — đến khi nền tảng đủ mạnh thì đấu nối.

## TL;DR

1. Repo **đã có** hệ "kho lạnh có nhãn-ngưỡng" ở `docs/roadmap/future/` (8-field living note + Thaw Protocol + `THRESHOLDS.md`). Không xây lại.
2. Khoảng trống thật: schema 8-field **không có chỗ** cho bằng chứng "đã chạy ngoài kia" — `grep` toàn bộ note = **0** ref prior-art.
3. Quyết định (DEC-7): thêm **1 trường `prior_art` ở vị trí 3b** (ngay sau `current_anchors`), coi nó là **external anchor** → thừa kế cơ chế refresh-anchor sẵn có, có người-đọc mà KHÔNG biến thành thaw-trigger.
4. Ca thử (ý tưởng của user): **"nhiều subagent đóng góp thinking → gói thành 1 lượt agent → output vẫn 1 message; reasoning trung gian đổ `trash/`"**. Quyết định (DEC-8): nhà = **E21** (per user), với carve rõ ràng.
5. Phát hiện đối kháng quan trọng: prior-art chỉ chứng minh **một nửa** (method proven, chưa proven đúng cấu hình của ta) — đúng là cái guard `proven ≠ needed` mà trường mới bắt được.

---

## 1. Hiện trạng đã xác minh (evidence)

- 8-field hiện tại (`docs/roadmap/README.md:21`): `problem_solved · why_not_now · current_anchors · wiring_threshold · wiring_sketch · dependencies · critique · verdict`.
- Triết lý khoá (`README.md:8`): `deps 🟢 = *được phép* làm, KHÔNG phải *nên* làm`. Tín hiệu YAGNI = field ghi-mà-không-đọc (`README.md:10`).
- Anti-rot sẵn có: `current_anchors` lệch = note cần refresh (`README.md:21`, §7); Thaw Bước 0 đo định kỳ (`README.md:53`).
- Gap: `grep -rniE 'prior.?art|external|proven|internet' docs/roadmap/future/` = **0**.

---

## 2. Quyết định schema (DEC-7) — `prior_art` là một "external anchor"

### 2.1. Ba hướng đã cân (brainstormer)

| Trục | A — 1 field sau `problem_solved` | B — 2 field (`prior_art`+`alternatives_rejected`)+verdict mới | C — 0 field, nhúng vào `wiring_threshold` |
|---|---|---|---|
| Schema | 8→9 | 8→10 | 8→8 |
| Anti-rot | `what-to-look-for`+`checked` (thủ công) | `mechanism`+`fit-gap` (có người đọc) | ăn nhịp Thaw Bước 0 |
| Hợp triết lý | cao nhất | thấp (kéo về ADR/PRD — vi phạm "anti-PRD") | cao nhưng làm bẩn nghĩa field |
| Rủi ro chính | field chết âm thầm (read=0) | nặng/rỗng hàng loạt | prior-art lén thành trigger |

### 2.2. Tension brainstormer bí

Để prior-art không mục cần "người đọc định kỳ". Người-đọc-định-kỳ duy nhất nó thấy là Thaw Bước 0 — sinh ra để đo *trigger*. Tách prior-art khỏi trigger → mất người đọc → mục; bám trigger → nhiễm nghĩa "trigger" → phá `được phép ≠ nên`.

### 2.3. Lối thoát (synthesis đã chốt)

Brainstormer bỏ sót người-đọc thứ hai: **kỷ luật refresh `current_anchors`** (`README.md:21`, §7) — đây KHÔNG phải đo trigger, mà là "note còn bám thực tại không".

Bản chất: `current_anchors` = neo NỘI (feature móc vào code mình, `file:line`); `prior_art` = neo NGOẠI (feature tồn tại ngoài đời, `URL`+cơ-chế). Cùng một loài.

→ **Đặt `prior_art` ở vị trí 3b, ngay sau `current_anchors`.** Nó thừa kế cơ chế refresh-anchor → có người đọc mà người đọc đó KHÔNG phải Thaw Bước 0 → `wiring_threshold` không bị động một chữ. Tension tan.

**Khuôn trường mới:**
```
## 3b. prior_art (external anchor — proof-of-FEASIBILITY, KHÔNG phải proof-of-NEED)
- <tên> — <URL> — mechanism:"<cơ-chế/NGUYÊN-LÝ đã chạy ngoài kia, KHÔNG phải tên-UI>" — checked:<date>
```
- `mechanism` (nguyên-lý, không phải UI/feature-name) → URL chết / paywall vẫn còn nguyên-lý để tìm nguồn tương đương. Đây là guard tối thiểu cho "link trần sẽ chết".
- `wiring_threshold`: prior-art **vĩnh viễn KHÔNG là trigger**.
- `critique`: thêm **1 dòng bắt buộc** — `"proven-elsewhere ≠ needed-here: ..."` (Rust RFC 2333: *precedent does not on its own motivate an RFC*).
- `verdict`: KHÔNG thêm type mới (loại B — YAGNI).

Loại **B** (vi phạm constraint anti-PRD + nặng) và **C** (rủi ro prior-art lén thành trigger — second-order tệ nhất).

Nguồn chuẩn ngoài: [Rust RFC template](https://github.com/rust-lang/rfcs/blob/master/0000-template.md) · [RFC 2333 Prior art](https://rust-lang.github.io/rfcs/2333-prior-art.html) · [Nygard ADR](https://github.com/joelparkerhenderson/architecture-decision-record).

---

## 3. Ca thử (DEC-8) — note "Committee-Agent" cho E21

User reframe giữa chừng: KHÔNG phải "1 model nhỏ chạy nhiều vòng ở tầng LLM-call", mà là **abstraction tầng-agent**: nhiều subagent đóng góp thinking → gói thành MỘT lượt agent → output vẫn 1 message; reasoning trung gian đổ `trash/`, bỏ qua được. Coi cụm như một agent.

### 3.1. Note 9-trường (worked example — schema mới chạy thật)

```
# Committee-Agent (nhiều subagent → 1 lượt agent) · epic: E21 · park-with-trigger

1. problem_solved
   Một lượt agent đôi khi cần nhiều "luồng nghĩ" mới trả lời tốt. Gói N subagent đóng góp thinking
   → tổng hợp thành MỘT message → ngoài nhìn vẫn là 1 agent / 1 lượt. Reasoning trung gian đổ trash/, ignore được.

3. current_anchors (verbatim)
   - adapters/agents/langgraph_agent.py:83-95 — turn output = DelegationResult{summary, artifacts}. (xác nhận "output 1 lượt = 1 message")
   - supervisor/graph.py:263-310 (run_round) — vòng next_agent_calls, delegate TUẦN TỰ, merge Blackboard. KHÔNG có bước aggregate.
   - supervisor/loop.py:147-239 (_drive) + :249-259 (_result.final_output) — delegation HIỆN across-round, CHƯA within-one-turn.
   - var/agent_runs/<run_id>/ (observability/event_log.py:34-54) — sink reasoning hiện có (events.jsonl).
   - control/events.py (RuntimeEvent, TraceContext.child parent/child span) + control/redaction.py (RedactionInfo.level=internal) — máy móc E21 để hiện/ẩn sub-round.

3b. prior_art (external anchor — proof-of-FEASIBILITY ≠ proof-of-NEED)
   - Mixture-of-Agents — https://arxiv.org/abs/2406.04692 — mechanism:"N proposer agent → aggregator tổng hợp → 1 output, layered" — checked:2026-06-26
   - Self-Refine — https://arxiv.org/abs/2303.17651 — mechanism:"1 LLM lặp generate→tự-phê→refine" — checked:2026-06-26
   - Least-to-Most — https://arxiv.org/abs/2205.10625 — mechanism:"chia bài toán con→giải tuần tự→re-feed" — checked:2026-06-26

4. why_not_now
   Delegation hôm nay TUẦN TỰ across-round (supervisor/graph.py:263-310); CHƯA within-one-turn fan-out; CHƯA có bước aggregate/reduce (grep 'aggregate|ensemble|committee' non-test = 0). Chưa nhu cầu đo được (≤2 delegation call-site; subagent/run ~1-5). Chưa chốt chiến lược gộp (vote/concat/LLM-summary).

5. wiring_threshold (đo được — prior-art KHÔNG ở đây, KHÔNG phải trigger)
   - subagent/round > 3 thường xuyên (ensemble có giá) — đếm next_agent_calls trong var/agent_runs.
   - ≥1 report đo nhu cầu "1 lượt cần nhiều luồng nghĩ" (chất lượng/độ trễ).
   - E21 T1 (event+redaction) release (gate cho phần observe/trash-channel).

6. wiring_sketch (seam file:line)
   Wrap run_round (supervisor/graph.py:263-310): sau vòng delegate, thêm bước AGGREGATE (vote/concat/LLM-summary, cấu hình được) → 1 message cho O. Subagent reasoning → var/agent_runs/<run_id>/trash/round_k/ với redaction.level="internal" (control/redaction.py) → ẩn mặc định ở UI, fetch raw qua payload inspector. Tái dùng TraceContext.child (control/events.py) link sub-round vào parent span. KHÔNG subsystem song song; chạy N subagent SONG SONG mới đụng async — ghi nhận là phần đắt.

7. dependencies (cổng)
   gate-in: E10 (TaskLoop/DelegationManager — supervisor/graph.py) 🟢. Phần CORE (fan-out+aggregate) là orchestration MỚI, KHÔNG phải E21.
   gate: E21 T1 (control/events.py + redaction) cho phần observe/ẩn/trash-channel 🟡 (đang làm — Phase A+B1).
   CARVE: E21 SỞ HỮU phần quan-sát/redact/trash của committee-turn; phần fan-out+aggregate là năng-lực orchestration (E10-adjacent) mà E21 tiêu thụ.

8. critique (YAGNI · proven ≠ needed)
   proven-elsewhere ≠ needed-here: MoA chứng minh committee-of-agents ở model frontier / NHIỀU model khác nhau, CHƯA chứng minh ở cụm subagent dùng model NHỎ giống nhau. Hôm nay 0 hạ tầng aggregate + delegation tuần tự across-turn → đây KHÔNG phải wiring mỏng, là orchestration mới + chọn chiến lược gộp + (có thể) concurrency. Rẻ nhất: aggregate TUẦN TỰ (concat/LLM-summary) trên run_round, KHÔNG song-song-hoá vội.

9. verdict
   park-with-trigger. Tầng rã đông: bước aggregate tuần tự trên run_round + trash/ redaction; kích khi subagent/round >3 hoặc có report đo nhu cầu "1 lượt nhiều luồng nghĩ".
```

### 3.2. Hai phát hiện đối kháng (load-bearing)

**(a) Prior-art chỉ chứng minh một nửa** — verdict đối kháng `holds=false`:
- Least-to-Most: 99% vs 16% trên SCAN nhưng ở **175B** (GPT-3), chưa có bằng chứng ở model nhỏ.
- Self-Refine: +20% nhưng dùng **self-critique**, không phải gộp sub-answer.
- MoA: cần nhiều model **khác nhau** / layer; biến thể 1-model kém hẳn.
- → Giao của (model nhỏ + nhiều subagent gộp + 1-turn) **chưa paper nào chứng minh trực tiếp**. Khả thi về NGUYÊN-LÝ, chưa khả thi đã-đo. `critique` ghi trung thực — đây là tính năng của trường `prior_art`, không phải lỗi.

**(b) Tranh luận E21 vs E22 → user reframe → E21 (có carve):**
- Phân tích ĐẦU (framing LLM-call level): cả scout lẫn revalidator độc lập kết luận **E22**, vì E21 PRD scope-out reasoning (`docs/spec/active/E21-realtime-control-plane/PRD.md:25`: "Logic sinh plan/proposal — E21 chỉ review/điều khiển, không sinh").
- User reframe sang **tầng-agent** (committee-as-one-agent). Scout lại xác nhận E21 hợp lý cho phần **observe/redact/trash-channel**: `control/events.py` (TraceContext.child parent/child span) + `control/redaction.py` (level=internal = ẩn mặc định = đúng "trash/ tôi không cần xem").
- Kết luận trung thực: **E21 sở hữu phần quan-sát**; phần **fan-out+aggregate core** là orchestration mới (gate-in E10), E21 tiêu thụ. Nhà = E21 per user, carve ghi rõ trong `dependencies`.

---

## 4. Ràng buộc thiết kế trung thực (đừng giấu)

1. Delegation hôm nay **tuần tự, across-round** (`supervisor/graph.py:263-310`), KHÔNG within-one-turn → committee-as-one-turn cần wrap `run_round` + **thêm bước aggregate chưa tồn tại**. Không phải wiring mỏng.
2. **Chưa có chiến lược gộp**: vote? concat? LLM-summary? Phải chốt khi rã đông.
3. **`trash/` chưa có**: redaction layer (`control/redaction.py`) sẵn sàng, nhưng chưa route artifact trung gian vào `trash/` với `visibility=internal`.
4. Song-song-hoá N subagent trong 1 turn = thêm async/thread-pool = phần đắt; bản rẻ nhất chạy tuần tự.

---

## 5. Câu hỏi mở

- Chiến lược aggregate mặc định khi rã đông: concat đơn giản hay LLM-summary (đắt hơn 1 call)?
- `trash/` đổ theo `round_k/` hay `agent_id/`? Có TTL dọn rác không?
- Committee-turn áp ở mức O-decision (`supervisor/graph.py`) hay mức agent-loop (`graph/nodes.py:agent_node`)?
- Bước aggregate có tiêu `budget.steps` (fail nhanh) hay float ngoài như parse-retry hiện tại (`discipline/budget.py`)?

---

## 6. Bước tiếp

- **Wiring DEC-7** (nếu muốn áp thật): cập nhật `docs/roadmap/README.md` schema 8→9 (thêm 3b), thêm dòng đếm prior-art-check vào `docs/roadmap/THRESHOLDS.md` §maintenance, tạo file note `docs/roadmap/future/committee-agent.md`. → việc docs, hợp `/hs:plan` (fast) hoặc làm trực tiếp.
- **Chưa tới lúc cook**: cả 2 DEC là roadmap/schema, không phải feature. Committee-Agent giữ `park-with-trigger`.
