---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — engine kéo-thả LLM workflow + chat (greenfield, single-user-local)

> Quyết định: **DEC-11** (`docs/decisions.md`). Câu hỏi gốc: *kiến trúc hex_agent hiện tại có hợp lý để xây kéo-thả không, hay tạo project mới?* → đã chốt: **project mới**, vì 4 câu trả lời discovery dưới đây.

## Bối cảnh đã chốt (không relitigate)

| Trục | Chốt | Hệ quả |
|---|---|---|
| Người dùng | **single-user / local** (1 user, 1 máy, 1 process) | control-plane/event-sourcing/replay/authz = gánh nặng → áp "bỏ ~70% LOC" của Report B |
| Domain | **generic workflow builder** (kiểu Flowise/n8n) | bỏ luôn domain SDLC/decompose/TDD-gate; engine domain-agnostic |
| Chat | canvas + run **và** turn-by-turn có lịch sử; workflow chạy sau mỗi message; **UI đã có** | cần **backend engine headless**, UI = canvas tự build (React-Flow style) |
| Reuse | **greenfield hoàn toàn** | hex_agent chỉ là prior-art; không kế thừa code |

Hai báo cáo prior-art là nền bằng chứng:
- `plans/reports/design-260626-1502-drag-drop-composition-layer-report.md` — core đã làm config-driven composition **5 lần** bằng 1 idiom: `Spec (dataclass) + parse_*(data,source) gateway + Registry assert_known + load-YAML`. Invariant chịu lực: termination proven lúc compile (cycle phải đi qua node tính budget); LLM không bao giờ tự sinh route/verdict; config chỉ được **siết** bound bằng `min()`; wall-clock timeout không serialize được qua resume → dùng step-budget.
- `plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md` — với target local-1-process, ~70% LOC (control/ 1566 LOC, roles/skills/delegation, langgraph onion, freeze in-memory, thread-safety) là dead weight. Giữ **nguyên lý**: no-verdict-field; mu+budget termination có backstop độc lập; thang JSON-repair deterministic-first; đĩa là sự thật duy nhất (resume = đọc lại); 1 chokepoint/effect INLINE; `route-as-state-field + node-as-fn(state)->patch` (bỏ engine đẻ ra chúng).

## Verdict

**Tự xây phần LÀ của mình — YAML spec + parse-gateway + registry + compile-time cycle-check + canvas-contract. Thuê FSM runtime (Burr).** Không xây cả engine, không fork cả platform.
Lý do: đã có UI → canvas của platform là đồ thừa; cyclic-FSM-có-persist/resume là commodity Apache-2.0 → tự viết = xây lại Burr để sở hữu.

## 3 hướng

| | Tự xây | Thuê | Verdict |
|---|---|---|---|
| **D1 — thin kernel thuần** | tất cả: interpreter, persist, resume, scheduler, spec layer (~800–1500 LOC) | — | chỉ hợp khi có lý do NIH/zero-dep cứng; nếu không = xây lại lõi Burr |
| **D2′ — spec layer trên Burr** ✅ | spec/registry/validation + **cycle-check** + canvas-contract + turn-driver | Burr: cyclic FSM, SQLite persist/resume, headless, Apache-2.0 | **đề xuất** — giữ 100% safety envelope, thuê runtime; ít LOC nhất cho 1-user-local greenfield |
| **D3 — fork platform** ❌ | node packs | Flowise/Langflow/Dify/n8n | **loại** — có UI rồi → canvas thừa; + UI-lock/license (n8n fair-code, Dify cấm SaaS) |

**Đã chốt cách quyết D1 vs D2′:** spike Burr 1 cuối tuần (xem dưới), không đoán.

## Build-vs-adopt — bằng chứng (substrate libraries là fork thật, không phải platforms)

| Lib | Local? | License | "chain loop-until-accept" native? | spec từ config-file? | headless (UI ngoài drive được)? |
|---|---|---|---|---|---|
| **Burr** (DAGWorks) | có, pure lib, persisters SQLite/mem | Apache-2.0 | **có** — `with_transitions`, loop `("p","p",~when(done=True))`, `halt_after`; condition code-defined, LLM không sinh được | **một phần** — graph dựng bằng Python, KHÔNG có YAML layer; **không có step-budget sẵn** | **có** — "headless", `chat_history` là state field |
| Pydantic-Graph | có, FSM thuần, snapshot/node | MIT | có (generic FSM) | không | có — nhưng resume cross-turn còn rough (issue #1361) |
| LlamaIndex Workflows | có, SqliteWorkflowStore | MIT | event-driven, KHÔNG route-on-state (lệch idiom) | không | có |
| Flowise / Langflow / Dify / n8n | server + DB | open-core / license traps | không phải primitive A→B→accept | canvas-JSON, không file-first | UI riêng là mặc định → fork JS để gắn UI mình |

Kết luận YAGNI: platform sai abstraction (đã có UI). Substrate ranking: **Burr > Pydantic-Graph > LlamaIndex**. Phần Burr **không** cho — YAML-spec + parse-gateway + compile-time termination proof + canvas-contract — chính là IP cần tự viết, bất kể D1/D2′.

Nguồn: [Burr persistence](https://burr.dagworks.io/concepts/state-persistence/) · [Burr transitions](https://burr.dagworks.io/concepts/transitions/) · [Pydantic-Graph](https://ai.pydantic.dev/graph/) · [pydantic-ai #1361](https://github.com/pydantic/pydantic-ai/issues/1361) · [LlamaIndex Workflows](https://developers.llamaindex.ai/python/llamaagents/workflows/deployment/) · [Langflow backend-only](https://docs.langflow.org/configuration-backend-only) · [Dify LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE) · [n8n SUL](https://docs.n8n.io/sustainable-use-license/)

## Stress test: "department = stack A→B→…→done" + canvas có gộp 1 executor được không?

- **Loop-until-accept gộp được.** Department = subgraph: `agent_A` ghi output vào channel → `agent_B` đọc → edge cuối → `gate` đọc channel `accepted` → fail thì route về chain-head, chặn bằng step-budget. Burr `("gate","head",~when(accepted=True))` chứng minh runtime làm đúng cái này. Report A phải tách 3 executor chỉ vì hex_agent đã có sẵn 3 (langgraph + while-loop + DFS) — **greenfield không kế thừa nên claim "department cần executor thứ 2" là SAI.**
- **Chỗ vỡ thật là lịch sử chat, không phải loop.** Chat thread là chuỗi N run *liên-turn* ở time-scale khác với state *trong-turn*. Nhét `chat_history` vào state channel (đúng cái ví dụ `with_state(chat_history=[])` của Burr gợi ý) = ghép 2 vòng đời: state per-run phải **reset mỗi turn** vs hội thoại phải **persist + lớn dần**. → turn 2 resume budget turn 1; hoặc append-list double-append (footgun đã ghi ở `design-...1502:162`).
- **Seam đúng:** lịch sử sống **ngoài graph** trong turn-ledger (JSONL append-only `{role,content,run_id}`), inject read-only lúc đầu turn, append reply lúc cuối turn. "Department" = subgraph; chat thread = **turn-driver ~10 dòng** bọc graph, KHÔNG phải executor thứ 2.

## Xương sống bất-khả-thương-lượng (đúng cho cả D1 lẫn D2′ — encode vào parse-gateway ngày 0)

1. **QUYẾT ĐỊNH CHỊU LỰC NHẤT — 3 vòng đời state tách rời** (sai cái này là chìm project):
   - **(a) state per-run** — reset mỗi turn (budget, route, scratch)
   - **(b) conversation ledger** — JSONL append-only, persist cross-turn, **ngoài graph**, inject read-only đầu turn, append reply cuối turn
   - **(c) display stream** — token ephemeral ra UI, **không bao giờ là source-of-truth**

   Nước đi hiển-nhiên-mà-sai (cả pure-D1 lẫn ví dụ Burr đều dụ): gộp 3 thành 1 state object → budget bleed, mất history khi resume, phantom streamed output. Murder để gỡ một khi đã có saved workflow + chat thread trên đĩa.
2. **Compile-time cycle-check = safety chịu lực, không phải polish.** User vẽ `A→B→A` không có budget node → process local treo vĩnh viễn (không có scheduler multi-tenant để kill). Burr KHÔNG làm hộ — code của bạn. Mọi cycle phải đi qua node tính budget, prove lúc load.
3. **LLM không bao giờ sinh route/verdict.** Generic builder → user SẼ muốn node có param "node kế tiếp". Cấm cấu trúc: không param nào được router đọc. Enforce ở gateway.
4. **Plugin ≠ `importlib` chuỗi tùy ý.** Generic builder + community node-pack = "kéo node" lặng lẽ chạy Python người lạ in-process. Registry ký/allow-list hoặc subprocess boundary — chốt trust model ngay.
5. **Saved workflow phải có `schema_version` + migration + reject-unknown** từ turn 1 (generic builder ⇒ user tích lũy flow trên đĩa; flow lưu theo `node v1` mở bằng `v2` đổi param = sai ngầm).

## Tension thành thật

"Greenfield hoàn toàn" vs D2′ thêm 1 dep (Burr): không mâu thuẫn — greenfield = *không reuse hex_agent*, D2′ là 100% code mới chỉ thuê 1 FSM loop thay vì viết lại. Pure-D1 zero-dep nhưng tốn ~30–40% LOC xây lại thứ Burr đã ship. **Tie-breaker = spike:** wire `department: chain→gate→loop-until-accept` lên Burr + turn-driver lịch-sử-ngoài-ledger. Sạch → D2′. Phải viết adapter để "un-Burr" Burr → D1.

## Bước tiếp

1. **Spike Burr (1 cuối tuần)** — tiêu chí PASS: (a) department loop-until-accept chạy được trên Burr transitions; (b) turn-driver giữ 3 vòng đời tách rời (ledger ngoài graph); (c) cycle-check tự cài được không chọi abstraction Burr; (d) SSE stream tách khỏi state. Sạch hết → khóa D2′; vướng (a)/(c) → D1.
2. `/hs:plan` cho slice dọc đầu tiên (sau khi spike chốt substrate): engine headless tối thiểu = `load_spec(yaml) → run(initial_state) → SSE stream`, 1 department 2-agent + 1 gate, ledger + turn-driver, cycle-check lúc load. Hoãn: plugin sandbox, schema migration, multi-department compose.

## Câu hỏi mở (chốt trước/trong spike)

- Burr `when/expr` có nuốt sạch route-on-state-field đã validate compile-time không, hay phải đánh nhau với state model của nó? (tiêu chí PASS của spike)
- Trust model plugin: allow-list ký vs subprocess vs WASM — chọn cái nào cho local-1-user (đơn giản nhất đủ an toàn)?
- Streaming: SSE đã có tham chiếu ở `ui/ide/server.py:387` (hex_agent) — port pattern hay viết mới cho canvas React-Flow?
- Canvas-contract: schema JSON mà React-Flow export ↔ YAML spec engine — 1 format hay 2 (canvas-JSON ↔ compile sang spec)?
