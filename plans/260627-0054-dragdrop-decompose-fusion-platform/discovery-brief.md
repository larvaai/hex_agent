---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery Brief — Nền tảng kéo-thả agent (fusion: topology authoring × decompose-until-trivial)

**Date:** 2026-06-27
**Status:** finalized
**Codename:** `agentplat` (tạm)

---

## 1. Problem framing

Cần một nền tảng **kéo-thả agent** dùng cho **1 người / 1 máy / 1 process**, phát triển bền vững, kiến trúc hexagonal, business logic thật. Đã có 2 codebase prior-art (`drag_from_zero`, `decompose_agent`) cùng giải một phần bài toán nhưng theo 2 mô hình khác nhau; chưa có một nền hợp nhất, có ranh giới cứng để lớn lên không thành spaghetti. Brief này chốt **hướng kiến trúc** qua 8 quyết định interview, không viết code.

**Root cause:** Hai prior-art mâu thuẫn ở "đâu là sự thật" (event-log vs tree.yaml) và "agent là gì" (role-dispatch vs 1 Worker); cần quyết dứt khoát trước khi build để khỏi rewrite.
**Current impact:** Code đang rải ở 2 cây, DEC-11 chốt "thuê Burr" nay không khớp mô hình đã chọn → cần điều chỉnh.
**Deadline / urgency:** Không deadline cứng; mục tiêu là nền đúng-ngay-từ-đầu, không phải nhanh.

---

## 2. Hard constraints

| Constraint | Type | Notes |
|---|---|---|
| Single-user / single-machine / single-process | policy | Bỏ control-plane / event-sourcing-cho-multi-tenant / authz / replay (DEC-11) |
| Stdlib-first, vendored, dep ngoài tối thiểu | technical | Cả 2 codebase đang giữ; runtime tự viết (xem D5) |
| Local 35B làm Worker | technical | Model PROPOSE; CODE adjudicate — không field verdict nào model ghi được |
| Đĩa là sự thật, resume = đọc lại file | technical | Không phụ thuộc snapshot in-memory hay network replay |
| Hexagonal: `domain` không import ngược `ports`/`adapters` | technical | Là cơ chế "bền vững", enforce ở import-rule + test |
| Python | technical | Khớp prior-art; snake_case |

---

## 3. Evidence summary

**Research report:** [SKIPPED — interview-driven; dùng prior-art reports làm nền bằng chứng, không chạy research run mới]

Nền bằng chứng (verbatim, không viết lại):
- `plans/reports/brainstorm-260626-1615-greenfield-dragdrop-engine-report.md` — DEC-11 chốt project mới, single-user-local, generic builder; nêu "3 vòng đời state tách rời" là quyết định chịu lực nhất; cycle-check compile-time là safety không phải polish; LLM không bao giờ sinh route/verdict.
- `plans/reports/codebase-map-260626-2229-drag-from-zero-report.md` — `drag_from_zero` ~5.6k LOC: "2 đồ thị không trộn" (topology config + execution-tree = projection của event-log); slice 6b verifier code-owned (`dragzero/verifier.py`): done_when = typed triple, CHECK_VOCAB đóng, artifact-assert fresh, μ = done_when_count; verdict re-derive ở projection boundary, override claim của model.
- `plans/reports/design-260626-1502-drag-drop-composition-layer-report.md` — idiom `Spec + parse_*(data,source) gateway + Registry.assert_known + load-YAML` đã lặp 5 lần; config chỉ được SIẾT bound bằng `min()`; wall-clock timeout không serialize qua resume → dùng step-budget.
- `plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md` — với target local-1-process, ~70% LOC hex_agent là dead weight; giữ nguyên-lý (no-verdict-field, μ+budget có backstop độc lập, thang JSON-repair deterministic-first, 1 chokepoint/effect inline).
- Memory: `decompose-until-trivial-principle`, `hex-agent-lessons-to-carry`.

---

## 4. Option space (8 fork đã hỏi — đáp án in đậm)

| # | Fork | Lựa chọn |
|---|---|---|
| D1 | Lõi domain | Compose-a-team / Decompose-until-trivial / **Fusion 2-lớp** |
| D2 | Seam runtime | 1-cây-agent-là-role / **Cây-lồng-cây** / DAG-tĩnh+node-hard |
| D3 | Source of truth (execution) | **1 event-log nest by parent-id (projection)** / N tree.yaml / Lai |
| D4 | Agent × model | **1 model, port mang `agent` (multi sau)** / Multi-model ngay / 1-model-cứng |
| D5 | Runtime engine | Thuê Burr (DEC-11) → **tự viết vendored stdlib-first** (Burr không khớp event-log-projection) |
| D6 | Palette | Tối-thiểu-3 / 4-loại / **Full 6: Agent/Tool/Router/Memory/Hook/Gate** |
| D7 | Chat lifecycle | Cùng-1-log-3-projection / **Log-thực-thi + turn-ledger riêng** / 1-state-object(bẫy) |
| D8 | UI / transport | Headless-1-format / **Headless-2-format (canvas-JSON ↔ spec qua compiler)** / Tái-dùng-Agent-IDE |

---

## 5. Chosen direction + rationale

**Chosen direction:** Fusion 2-lớp = top-orchestrator kiểu `drag_from_zero` (route giữa các agent đã-kéo: delegate/solo) **bọc** recursion kiểu `decompose_agent` (mỗi agent: μ-giảm tới leaf), trên **1 event-log/projection**, **hexagonal headless**, UI là consumer của contract.

**Why:**
1. Mỗi mảnh (orchestrator route, decomposer μ-giảm, event-log projection, verifier code-owned) đã chạy thật trong prior-art — fusion = ghép bằng cách lồng, không phát minh lại.
2. 1 event-log + projection thuần làm resume thành "đọc lại + fold"; verdict/μ/budget không bao giờ lưu, luôn re-derive — code là verdict-authority duy nhất.
3. Hexagonal `adapters→ports→domain` biến "bền vững" thành ràng buộc import cơ học, không phải khẩu hiệu; UI/eval ở ngoài chỉ ăn contract → thay được.

**Accepted trade-off:**
- Cây-lồng-cây ⇒ N budget / N μ, vì cần "đội agent mỗi con tự bẻ việc"; trị bằng `budget_child = min(authored, parent_remaining)` và `μ_parent` chỉ giảm khi subtree con đóng.
- 2 resume path (event-log within-run + turn-ledger across-turn), vì 3 vòng đời phải tách vật lý (brainstorm: gộp = đường chìm).
- 1 compiler canvas-JSON↔spec để giữ UI tự do tiến hóa schema mà không đụng engine.
- LLM port mang `agent` dù giờ chỉ 1 model — chấp nhận trừu tượng "chưa dùng" để sau thêm multi-model không sửa core.

### 5a. Bộ khung hexagonal (chốt)

```
agentplat/
  domain/                    # thuần, 0 I/O, invariants ở __post_init__
    topology/                # design-time (Đồ thị 1)  [D1,D6]
      node.py spec.py validate.py palette.py
    runtime/                 # run-time (Đồ thị 2⊕3 hợp nhất qua projection)  [D2,D3]
      event.py reduce.py orchestrator.py decomposer.py budget.py mu.py
    gate/                    # adjudication — code là verdict-authority  [D3]
      done_when.py vocab.py adjudicate.py
    conversation/ turn.py    # cross-turn  [D7]
  ports/                     # Protocol (cạnh hexagon)
    llm.py tool.py event_store.py turn_ledger.py transport.py
  adapters/                  # I/O thật (chỗ DUY NHẤT side-effect)
    llm_local.py llm_fake.py tools_fs.py event_store_jsonl.py
    turn_ledger_jsonl.py transport_sse.py canvas_compiler.py  [D8]
  app/                       # composition root (port gặp adapter)
    wiring.py turn_driver.py server.py
  __main__.py
tests/{domain,adapters,invariants}/
ui/      # NGOÀI core — consumer contract (Agent IDE giờ / React-Flow sau)  [D8]
eval/    # harness chấm điểm; consume core, core không import nó
```

### 5b. Invariants chịu lực (encode vào parse-gateway + test ngày 0)

1. `domain/` không import `ports`/`adapters`; chỉ `app/` nối — enforce bằng import-rule test.
2. Reducer (`reduce.py`) là FOLD THUẦN: cấm thời gian/random; verdict/μ/budget re-derive, không bao giờ đọc từ trường lưu.
3. Không key verdict-shaped (`passed`/`status`/`score`…) tồn tại ở chỗ model ghi được — reject lúc construct `done_when`.
4. Mọi cycle trong topology phải đi qua node tính budget — cycle-check **compile-time** (lúc load), không phải runtime.
5. Router-node = ràng buộc routing engine phải tôn trọng; Memory-node = view có tên vào projection. **Không** node nào thành source-of-truth thứ 2 — engine sở hữu route + memory.
6. `budget_child = min(authored, parent_remaining)`; có backstop step-budget độc lập với μ (2 terminator, không cái nào tin model).
7. Leaf-ness phát hiện bằng thử K lần, không do model khẳng định. Artifact-assert: exist + non-empty + path-jailed + FRESH (mtime ≥ activated_at); no-artifact = FAIL.
8. 3 vòng đời tách: per-run state RESET tại turn-boundary; conversation ledger persist ngoài engine; display stream ephemeral, không bao giờ là truth.
9. Saved topology mang `schema_version` + reject-unknown từ turn 1.

**DEC recorded:** **DEC-15** (`docs/decisions.md`) — supersede phần "thuê Burr" của DEC-11; giữ nguyên phần single-user-local/greenfield.

---

## 6. Open questions (chốt trước/trong hs:plan)

- [ ] CHECK_VOCAB ban đầu gồm những check nào (ship tối thiểu mấy cái)?
- [ ] Cross-tree termination: child cạn budget/μ-stuck thì bubble lên parent ra sao — FAIL cứng hay partial-complete?
- [ ] Leaf-by-K-attempts: K = mấy, per-node hay global?
- [ ] Router-node semantics chính xác: "ràng buộc" enforce thế nào ở `validate.py` + lúc route runtime?
- [ ] Memory-node: "view có tên" được fold thế nào, scope (per-agent / global) ra sao?
- [ ] Canvas-JSON schema cụ thể + mapping của `canvas_compiler.py` sang TopologySpec.
- [ ] Liên kết turn-ledger ↔ event-log qua `run_id`: thứ tự resume nào trước khi mở lại 1 thread đang dở?
- [ ] Khi nào cần snapshot/compaction cho event-log lớn dần (ngưỡng)?

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cây-lồng-cây: N budget/μ loạn, parent-child không hội tụ | medium | high | `min()` bounding + backstop step-budget + invariant "μ_parent giảm chỉ khi child đóng"; test termination trên FakeLLM |
| Full palette: Router/Memory thành truth-2 | medium | high | Invariant #5; `validate.py` chặn; Memory = projection-view only |
| 2 resume path (log + ledger) lệch nhau | medium | medium | run_id là khoá liên kết; test resume cả 2 cùng lúc; ledger inject read-only |
| 2-format compiler phình / lệch schema | low | medium | `schema_version` 2 bên + 1 bộ test round-trip canvas↔spec |
| Port multi-model "chưa dùng" thành ceremony chết | low | low | Chỉ 1 tham số `agent` trong ctx; không xây dispatcher tới khi có model thứ 2 |
| Trust model plugin chưa chốt (generic builder + node-pack = chạy Python lạ) | medium | high | OUT of scope giờ; flag bắt buộc chốt trước khi mở community node |

---

## 8. Explicitly OUT of scope

- Multi-user / multi-tenant / authz / control-plane / replay (single-user-local).
- Multi-model **thực thi** (port để ngỏ; chưa build dispatcher).
- Async / parallel execution (synchronous FIFO depth-first trước, như slice 1).
- Plugin sandbox / community node-pack / trust model (flag — chốt trước khi mở).
- Snapshot / compaction event-log (defer tới khi log đủ to).
- Migration engine cho saved topology (chỉ làm `schema_version` + reject-unknown; engine migrate sau).
- Build React-Flow canvas mới (UI ngoài core; Agent IDE hiện có là consumer tạm).
- Burr / external FSM runtime (D5 đã bỏ).

_(Mọi thứ không liệt kê = chưa quyết, không phải đã duyệt.)_

---

## Handoff → hs:plan

Brief này là input cho `hs:plan`. Khuyến nghị `/clear` trước để tránh carryover-bias từ interview (workflow-handoffs #5), rồi:

```
/hs:plan /Users/uspro/Desktop/namnson/hex_agent/plans/260627-0054-dragdrop-decompose-fusion-platform/discovery-brief.md
```

Slice dọc đầu tiên đề xuất (để hs:plan tinh chỉnh): **1 agent + 1 Gate + decomposer** trên FakeLLM — `load_spec → run → event-log → reduce(projection) → adjudicate done_when` — chứng minh μ-giảm + no-verdict-field + fold-purity trước khi đụng nesting/orchestrator/real-35B.
