---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery Brief — Đệ quy "decompose-until-trivial" KHÔNG có AC (ungated recursion)

**Date:** 2026-06-28
**Status:** draft

---

## 1. Problem framing

Muốn có tính năng: một task rẽ nhánh thành vài subtask, subtask lại rẽ nhánh tiếp, agent giải đệ quy bottom-up, giải xong hết con thì cha hoàn thành. Tạm **hoãn AC** (acceptance-criteria / `done_when`) — chỉ cần cơ chế đệ quy chạy trước ("đã" = trước/tạm, tức tuần tự, không phải bỏ AC vĩnh viễn). Câu hỏi đi kèm: xây thành vertical slice độc lập rồi ghép vào dragzero được không, và mở rộng thành nhiều slice ghép lại được không.

**Phát hiện lật ngược đề bài:** engine đệ quy **đã tồn tại và đã có test** trong dragzero — `_solve_gated` → `_handle_decomposition` → `_spawn_decomp_child` → `_settle`/`_close_parent` ([orchestrator.py:410-575](../../drag_from_zero/dragzero/orchestrator.py)). Nó làm đúng branch→đệ quy→compose-bottom-up mà bạn mô tả. Vấn đề thật **không phải "thiếu đệ quy"** mà là: đệ quy đang **bị khóa sau AC**. Task không có `done_when` hôm nay **không thể** decompose — `_handle_terminal` đẩy DECOMPOSE → `_complete("solo")`, kèm comment "(no measure to shrink)" ([orchestrator.py:367](../../drag_from_zero/dragzero/orchestrator.py)).

**Root cause:** chứng minh dừng (termination proof) gắn chặt vào AC — μ(parent)=`len(done_when)`, mỗi con phải nhỏ hơn ngặt, (ℕ,<) well-order nên không đệ quy vô hạn ([accept.py:1-13, :147, :172](../../drag_from_zero/dragzero/accept.py)). Bỏ `done_when` → mất μ → mất bảo đảm dừng, và mất luôn tín hiệu PASS/FAIL nên "đã giải xong leaf" và "đủ trivial chưa" đều thành vô định.

**Impact / urgency:** không gấp. Đây là bước scaffold để học/sở hữu plumbing đệ quy trước khi bật lại AC.

---

## 2. Hard constraints

| Constraint | Type | Notes |
|---|---|---|
| stdlib-only, single-process, single-user, local-35B | technical | dragzero giữ standalone, không import chéo `decompose_agent/` |
| Bất biến repo: run KHÔNG dùng feature mới phải **byte-identical** slice cũ | technical | seam mặc-định-off (xem §4); regression gate = `tests/test_*.py` xanh nguyên |
| KHÔNG sửa `accept.py` | policy | μ-proof gắn AC, giữ nguyên; con ungated bypass `accept_decomposition` |
| `reduce`/`reduce_inbox` là pure fold, không default-case | technical | event type lạ bị bỏ qua → APPEND enum an toàn, không vỡ projection cũ |
| Code phán xử, model chỉ đề xuất (no-verdict-field) | policy | ungated sẽ vi phạm một phần — xem §7 "accepted cost" |

---

## 3. Evidence summary

**Research report:** folded vào fan-out 7-agent (3 option × adversarial critique × converge), ground bằng code đọc trực tiếp — không có report rời. Bằng chứng gốc = file:line dưới đây.

Findings (đã verify trong code, không phải suy đoán):
- Engine đệ quy có sẵn + có test: `test_decompose.py` pin `test_failed_leaf_decomposes_and_children_verify`, `test_compose_fail_when_a_child_fails`, `test_delegation_only_runs_are_unchanged` ([tests/test_decompose.py:88,137,181](../../drag_from_zero/tests/test_decompose.py)).
- Ungated task hôm nay dead-end ở `_complete("solo")` ([orchestrator.py:367](../../drag_from_zero/dragzero/orchestrator.py)) — đây là chỗ duy nhất cần mở nhánh.
- **3 bug chặn-feature** mà critique tìm ra, **dùng chung cho cả 3 approach** (nên không approach nào "an toàn hơn" ở khía cạnh này):
  1. `_decomp_sig` ([orchestrator.py:35-41](../../drag_from_zero/dragzero/orchestrator.py)) chỉ hash `done_when` của con. Con ungated có `done_when=[]` → mọi proposal hash về **một hằng** → STUCK_DECOMP nổ giả ngay proposal thứ 2 toàn cây, giết luôn đệ quy nhiều tầng. **Phải re-key sig theo goal-text/title cho nhánh ungated.**
  2. `_close_parent` else-branch ([orchestrator.py:571-574](../../drag_from_zero/dragzero/orchestrator.py)) phát `TASK_COMPLETED result="delegated"` **vô điều kiện**, bỏ qua list `failed` nó tự tính ở 551-552. Parent ungated có con FAILED vẫn báo DONE sạch — đúng cái silent-DONE mà docstring 545-547 thề không cho. **Phải thêm nhánh thứ 3: parent-ungated-decomposed DONE chỉ khi không con nào fail, ngược lại COMPOSE_FAIL.**
  3. `record_step()` chỉ gọi ở [orchestrator.py:~435,~452](../../drag_from_zero/dragzero/orchestrator.py); đường spawn/settle/close **không** đụng `_steps` → spawn con là "miễn phí" so với budget 200. **`_solve_ungated` phải `record_step()` mỗi lần vào**, nếu không bảo đảm dừng duy nhất bốc hơi.
- Seam "ghép slice" đã được chứng minh **2 lần**: (a) slice cộng dồn trên một spine (Slice 1→6b, Gaps 1-3, entrypoint `submit()`/`reduce_inbox` của D1); (b) build rời rồi **vendor** (`accept.py`/`verifier.py` vendor từ `decompose_agent/`).

---

## 4. Option space

| # | Approach | Pros | Cons | Complexity |
|---|---|---|---|---|
| **A** | Một nhánh `_solve_ungated` ngay trên spine, tái dùng `_spawn_decomp_child`/`_settle`/`_close_parent` nguyên vẹn; bounded bằng depth+step+fan-budget | Diff nhỏ nhất; 0 code vứt đi; merge-back AC = lật cờ; đã "merged sẵn về hình dạng" | Không có termination proof; phải fix 3 bug trên trước | **low** |
| B | Package `recurse/` standalone, prove bằng fake worker rồi vendor vào | Cô lập để học/sở hữu | RNode ≠ `_WorkRec` (không capability/agent/sandbox) → test standalone **bảo vệ số 0** phần vendor; nhân đôi rồi vứt; rủi ro 2 engine song song | medium |
| C | Tách `Measure` protocol (`CriteriaMeasure` vs `BudgetDepthMeasure`), plumbing dùng chung, "merge" = đổi 1 instance | End-state đẹp nhất; μ=`MAX_DEPTH-depth` là luận cứ dừng vững nhất | Trừu tượng hóa **trước khi** có instance thứ 2 để kiểm chứng → dễ leak `verdict.reasons`/`activated_at` rồi sụp về if/else; vẫn phải fix 3 bug | medium-high |

Cả 3 critique đều ra verdict **REVISE** (không cái nào KILL, không cái nào KEEP nguyên).

---

## 5. Chosen direction + rationale

**Chosen direction:** **Option A (revised)** — thêm một nhánh đệ quy ungated trên spine sẵn có, đóng khung là **scaffold hội tụ VỀ engine AC**, không phải engine cạnh tranh.

**Why:**
1. Ungating ≈ **90% là gỡ cái gate** khỏi engine đang chạy, cách đúng một nhánh `if`. B (engine mới) và C (abstraction) trả giá lớn để tái tạo plumbing chỉ-một-nhánh-là-tới.
2. A **đã "merged về hình dạng"** — nhánh cộng dồn trên một spine, nên không có vendor-seam để lệch (chí tử của B: test standalone bảo vệ số 0 phần vendor) và không có abstraction non để kiểm chứng (thuế protocol của C).
3. Chi phí thật (không proof dừng, leaf do model tự khai) **giống hệt nhau ở cả 3** vì nó nội tại của việc hoãn AC, không phải của approach → chọn carrier rẻ nhất là A.
4. Merge-back AC là **lật cờ, không viết lại**: `done_when` quay lại → con ungated mang criteria → route lại qua `accept_decomposition` (μ-gate còn nguyên) → nhánh `if prec.task.done_when` của `_close_parent` tự bật compose-verify.

**Cơ chế đệ quy (Option A, sau fix):** `_solve_ungated` chạy `_react_until_terminal` một lần; đọc `DelegationMode` cuối của worker làm tín hiệu — SOLO → đóng leaf bằng `_complete(..., "solo-leaf")` (gắn cờ **unverified**, không bao giờ `"verified"`/`"composed"`); DECOMPOSE → đệ quy, spawn con qua `_spawn_decomp_child(gated=False)` (ép `done_when=[]`, bỏ `accept_decomposition`).

**Dừng = bounded, KHÔNG proven.** Bán đúng sự thật: cặp lex `(steps_remaining, max_depth-depth)` trên (ℕ×ℕ, lex) giảm ngặt mỗi lần vào đệ quy → **proof rằng SCHEDULER dừng**, hiện ra dưới dạng fail STEP_BUDGET/MAX_DEPTH, **không bao giờ silent DONE**. Đây **không** phải proof "đã đạt trivial".

**Accepted trade-off:**
- Leaf-ness thành lời tự khai SOLO của model, không phải verdict K-fail → vi phạm luật #1 (leaf phải DISCOVERED bằng thử, không assert). Giảm thiểu: gắn `result="solo-leaf"` (unverified) nên ledger không bao giờ tuyên một measure đã đạt; bật lại AC nâng đúng các node này lên "verified" mà không đổi hình cây.
- Decomposition không size-reducing (bypass NOT_SMALLER/UNDERCOVER) → breadth không bị measure nào chặn, chỉ `RootBudget(200)` chặn kích thước cây. Nói thẳng "bounded, not proven".

**DEC recorded:** none — chưa chốt kiến trúc; chờ giải fork ở §6 trước khi đụng DEC.

---

## 6. Open questions

- [ ] **Fork chính (chặn slice 3 vs 4):** bạn muốn (a) scaffold **vứt-đi** để học plumbing, xong bật lại AC và xóa/tắt nhánh ungated — A là đủ, không cần gì thêm; HAY (b) **thay luôn** mô hình dừng bằng AC-free làm hướng sản phẩm dài hạn — khi đó "bounded, not proven" + leaf-tự-khai thành thuộc tính vĩnh viễn, và `Measure` protocol (C) thành end-state khuyến nghị chứ không phải slice tùy chọn. "Đã" nghiêng mạnh về (a), nhưng không loại (b). Fork này quyết định `solo-leaf` là scaffold tạm hay semantic giao hàng.
- [ ] `fan_budget` mặc định = N bao nhiêu (số proposal/node trước STUCK/BLOCKED)? Ảnh hưởng worst-case kích thước cây (N^MAX_DEPTH) trước khi `RootBudget(200)` cắt.
- [ ] `solo-leaf` nên là EventType riêng (APPEND theo contract, lợi cho live_view render cây) hay tái dùng `TASK_COMPLETED` với `result="solo-leaf"` trong payload (giữ fold nguyên)?

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `_decomp_sig` sụp trên ungated (bug #1) | **high** (chắc chắn nếu không fix) | giết đệ quy nhiều tầng | re-key sig theo goal-text/title cho nhánh ungated — **must-fix, slice 1** |
| `_close_parent` silent-DONE khi con fail (bug #2) | **high** | vi phạm luật #1, báo thành công sai | thêm nhánh parent-ungated-decomposed: DONE chỉ khi không con fail — **must-fix, slice 1** |
| `_solve_ungated` không `record_step()` (bug #3) | medium | mất bảo đảm dừng duy nhất | bắt buộc `record_step()` mỗi lần vào — **must-fix, slice 2** |
| Bỏ `accept_decomposition` cũng bỏ luôn validate cấu trúc (forgery key, path-jail, dep-cycle) | medium | regression bảo mật | factor các check cấu trúc (`FORBIDDEN_VERDICT_KEYS`, `_unsafe_artifact`, `_has_cycle`) ra helper, **giữ bắt buộc trên cả 2 nhánh** |
| Không có proof dừng theo descent | high (by design) | cây có thể chạy tới MAX_DEPTH rồi mới dừng | chấp nhận + nói thẳng; RootBudget(200) là cái thật sự chặn size |

---

## 8. Explicitly OUT of scope

- AC / `done_when` ở leaf và ở compose — hoãn theo yêu cầu ("đã"). Coi việc bật lại là **merge-back target (slice 3)**, không phải việc hiện tại.
- Sửa `accept.py` — μ-proof giữ nguyên, con ungated bypass.
- Package `recurse/` standalone (Approach B) — loại: type-gap RNode/`_WorkRec` làm test standalone vô dụng, nhân đôi rồi vứt.
- `Measure` protocol (Approach C) — dời sang **slice 4 tùy chọn** sau khi có 2 instance thật; không trừu tượng hóa đầu cơ.
- Sửa fold sẵn có của `reduce` — cây ungated render từ `SUBTASK_SPAWNED`/`TASK_COMPLETED`/`TASK_FAILED` đang có; chỉ APPEND nếu muốn event type mới.
- Một termination PROOF thật cho nhánh ungated — bất khả thi khi không có content measure; brief giao "bounded by lex (steps_remaining, max_depth-depth)" và nói rõ thế.

_(Mọi thứ không liệt kê ở đây là chưa quyết, không phải đã duyệt.)_

---

## Phụ lục — "Nhiều vertical slice rồi ghép hết vào nhau" được không?

**Được, và repo đã chứng minh 2 lần.** Cơ chế ghép = 3 nước đi đã có sẵn:
1. `events.py` EventType enum **là contract** — slice mới **APPEND** event type, không reorder (D1 `INPUT_CLASSIFIED`, Gap-2 `LEAF_VERIFIED`).
2. `read_model.reduce` là pure fold **không default-case** → bỏ qua event lạ → slice mới hoặc mở rộng fold, hoặc thêm **sibling fold trên tập event rời** (`reduce_inbox` làm đúng vậy cho D1).
3. Orchestrator thêm **entrypoint mới ngoài đường start()/run()** (`submit()`/D1) → run không dùng feature mới byte-identical.

**Lưu ý quan trọng:** slice của dragzero **không phải đảo độc lập rồi bolt vào** — chúng là **lớp cộng dồn trên MỘT spine chung** (event log), giữ nguyên mọi invariant trước. Đó là lý do A thắng: bạn không "ghép" gì cả, bạn mở thêm một nhánh sau seam mặc-định-off.

**Trình tự slice + thứ tự merge (1 → 2 → 3, 4 tùy chọn cuối):**
- **Slice 1 (nền):** fix 3 bug — re-key `_decomp_sig` cho `done_when` rỗng; thêm nhánh ungated-decomposed vào `_close_parent`; factor structural-validations ra helper bắt buộc. (Lợi cho cả nhánh gated.)
- **Slice 2 (scaffold):** seam opt-in (`recurse_ungated` flag hoặc `solve_recursive` entrypoint) + `_solve_ungated` + `_spawn_decomp_child(gated=False)` + `fan_budget` trên `_WorkRec` + `record_step()` mỗi entry. Đóng leaf `result="solo-leaf"`. Mặc-định-off; prove byte-identity với `test_invariants` + `test_delegation_only_runs_are_unchanged`.
- **Slice 3 (hội tụ về AC — giải "đã"):** `done_when` quay lại, lật spawn để con mang criteria → route lại qua `accept_decomposition` → `_close_parent` bật compose-verify. Đây là merge-back, **lật cờ chứ không viết lại**.
- **Slice 4 (tùy chọn):** nếu cả 2 nhánh đã live & ổn → tách `Measure` protocol (C) để 2 nhánh khác nhau đúng 1 constructor swap. Dời tới khi có 2 instance thật.

---

## Handoff → hs:plan

Brief này là input cho `hs:plan`. Khi gọi:
```
/hs:plan /Users/uspro/Desktop/namnson/hex_agent/plans/260628-1129-recursion-without-ac/discovery-brief.md
```
**`/clear` trước** để tránh bias mang context discovery sang planning (`harness/rules/workflow-handoffs.md` #5). **Giải fork §6 trước khi plan slice 3/4.**
