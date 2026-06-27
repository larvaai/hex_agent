---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Roadmap: clone `hex_agent` từ số 0 — dạy vibe coding một agent có kiến trúc bền

> **Cho ai:** người mới, biết Python, muốn tự dựng lại một multi-agent system **microkernel/hexagonal**
> từ con số 0 — và quan trọng hơn: hiểu *vì sao* mỗi mảnh được tổ chức như thế để **giữ kiểm soát**.
>
> **Phạm vi:** toàn bộ sản phẩm agent (P0→P3 + E21 control plane). **Không** gồm `harness/`
> (đó là bộ tooling SDLC riêng cho Claude Code, không phải sản phẩm).
>
> **Cách đọc:** đọc file này trước (triết lý + bản đồ phase + bảng invariant + bảng pitfall),
> rồi đi tuần tự `phase-1` → `phase-7`. Mỗi phase là một mảnh **chạy được + test xanh** trước khi sang phase kế.

---

## 0. Một câu chốt triết lý

> **"Hard = chưa chia đủ nhỏ."** Mỗi phase chỉ thêm **một** năng lực mới, và mọi năng lực mới đều phải
> đi qua **một cái cửa đã có sẵn** (chokepoint). Không có đường tắt. Kiến trúc không phải để đẹp —
> nó là cách bạn **không bao giờ mất quan sát, mất an toàn, hay mất khả năng resume** khi hệ thống lớn lên.

Ba luật nền, lặp lại ở mọi phase:

1. **Một cửa duy nhất (single chokepoint).** Mọi hành động ra ngoài — gọi LLM, gọi tool, đọc/ghi file —
   đều chui qua `AgentKernel.execute_tool`. Thêm observability/safety/envelope một lần ở cửa = áp cho *tất cả*.
2. **Đóng băng cái chia sẻ, cô lập cái thay đổi (freeze vs session).** `AgentKernel` được `freeze()`
   rồi dùng chung, **bất biến**; mọi state thay đổi-theo-run sống trong `KernelSession` riêng. Không state nào rò giữa các run.
3. **Sự thật nằm ở một chỗ (one source of truth).** Resume đọc **SQLite**, không đọc `checkpoint.json`
   (cái đó chỉ là projection cho UI). State điều phối **chỉ chứa giá trị serializable**. Lệch một cái là vỡ âm thầm.

Hệ quả cho cách *vibe coding*: bạn không "code cho chạy rồi tính" — bạn dựng **cái cửa và cái khung trước**,
sau đó mọi feature chỉ là **cắm thêm một adapter vào port đã có**. Đó là lý do thêm tool thứ 50 cũng dễ như tool thứ 1.

---

## 1. Bản đồ phase (thứ tự xây = đường găng)

```
Phase 1  Microkernel + chokepoint + observability   (E01, E04)   ← nền, làm trước hết
Phase 2  LLM-as-capability + Output discipline       (E03, E02)
Phase 3  Toolbox + Safety jail + middleware          (E06)
Phase 4  Single-agent graph + resume (SQLite-truth)  (E05)
Phase 5  Skills + RAG                                 (E07, E08)
Phase 6  Roles + Multi-agent delegation              (E09, E10)
Phase 7  Realtime control plane                       (E21)
```

Đường găng (chuỗi phụ thuộc dài nhất, tối ưu lịch theo nó):
`Phase1 → Phase2 → Phase4 → Phase6`. Phase 3 (toolbox) làm song song được sau Phase 1; Phase 5 nhánh rẽ
sau Phase 3. Nguồn: [`docs/roadmap/dependency-map.md`](../../docs/roadmap/dependency-map.md).

| Phase | Epic | Mục tiêu một dòng | Definition of Done (cổng đóng phase) |
|---|---|---|---|
| 1 | E01+E04 | Kernel đăng ký tool → gọi qua `execute_tool` → envelope chuẩn → event log | `run_smoke.py` in `CORE_AGENT_SMOKE_OK`; mỗi run ghi `events.jsonl`+`summary.json`; `inspect` CLI đọc được |
| 2 | E03+E02 | LLM là một capability (`llm.chat`) qua cửa; parse+repair JSON, budget, finish-gate | adapter JSON-mode + lazy-init; discipline là module dùng chung; test parse/budget xanh |
| 3 | E06 | Tool fs/terminal/lint **sandboxed**, mỗi tool sau chokepoint safety + workspace jail | path-jail chặn traversal; terminal no-shell + timeout; policy gate chặn tool nguy hiểm |
| 4 | E05 | Một LangGraph substrate điều phối; resume qua process restart đọc SQLite | single-agent loop chạy task thật; `test_resume.py` xanh; resume không chạy lại node đã chạy |
| 5 | E07+E08 | Skills progressive-disclosure; RAG health-gated ingest/search qua ports | skill render đúng; RAG `health/ingest/search` qua cửa; suite offline không cần docker |
| 6 | E09+E10 | Role enforce allowlist; delegation chokepoint **riêng**; TaskLoop Agent-O + acceptance gate | scope con ⊆ cha; multi-agent loop chạy LLM thật; acceptance honor evidence thật |
| 7 | E21 | Control plane realtime: event/command/approval contract, emitter+redaction, UI-on-fake-backend | contracts + EventEmitter (redact→seq→fan-out); evidence-typed acceptance; secret không rò ra SSE |

> **Quy tắc đóng phase (chốt cứng):** chỉ mở phase kế khi **cổng vào** (deps) đủ; đóng phase khi **DoD test xanh**.
> Mỗi AC của epic → ≥1 test. Đây là cách "chậm mà chắc": test là cái cổng, không phải cái để làm sau.

---

## 2. Bảng invariant xuyên suốt — *cái gì giữ cho hệ thống không vỡ*

Đây là phần quan trọng nhất của cả roadmap. Mỗi dòng là **một cơ chế kiểm soát** + **biến/hàm cụ thể** thực thi nó.
Người mới thường bỏ qua mấy cái này → hệ thống chạy được lúc nhỏ, vỡ lúc lớn.

| # | Invariant (luật không được phá) | Thực thi bởi (file · biến/hàm) | Phá ra thì mất gì | Phase |
|---|---|---|---|---|
| I1 | **Mọi LLM/tool đi qua đúng một cửa** | `core/kernel.py` · `execute_tool()` | Mất observability+safety+envelope cho *toàn bộ* call | 1 |
| I2 | **Kernel đóng băng trước session đầu** | `core/kernel.py` · `freeze()` | Config/registry sửa giữa chừng → state rò giữa run | 1 |
| I3 | **State thay đổi-theo-run cô lập khỏi kernel** | `core/session.py` `KernelSession` · `core/state.py` snapshot/restore deep-copy | Hai run alias chung mutable state → nhiễm chéo | 1 |
| I4 | **Lineage gắn vào mọi event** | `core/kernel.py` · `run_id/task_id/session_id/parent_session_id/delegation_id/actor_id` | Không truy vết được ai gọi gì | 1 |
| I5 | **LLM cũng chỉ là một capability** | `features/llm_chat.py` · `llm.chat` qua `execute_tool` | LLM thành đường tắt né mọi kỷ luật | 2 |
| I6 | **Đúng một action mỗi vòng (JSON gate)** | `discipline/json_gate.py` · `parse_action` | Model lảm nhảm → loop mất kiểm soát | 2 |
| I7 | **Budget chặn loop vô tận** | `discipline/budget.py` · `max_steps`, parse-error, same-tool | Agent quay vòng đốt tiền/không terminate | 2,4 |
| I8 | **Workspace path-jail** | `safety/sandbox.py` · `resolve_in_workspace()` (`resolve()`+`is_relative_to`) | Path traversal ra ngoài `var/workspace` | 3 |
| I9 | **Mỗi tool sau chokepoint safety** | `safety/policy.py` · `SafeToolPort` | Tool độc/lỗi làm hại ngoài jail | 3 |
| I10 | **State điều phối chỉ chứa serializable** | `graph/state.py` · `AgentState`, `encode/decode_session_state`, `schema_version` | Nhét object thường → checkpoint/resume **vỡ âm thầm** | 4 |
| I11 | **SQLite là sự thật; `checkpoint.json` chỉ projection** | `orchestrator/loop.py`+`checkpoint.py` · `resume()` đọc SQLite, `run_id==thread_id` | Resume sai → mất tiến trình hoặc **chạy lại** node có side-effect | 4 |
| I12 | **Mọi nhánh graph kết thúc đúng một lần** | `graph/runtime.py`+`nodes.py` · `_route`, `complete_task/fail_task` | Loop vô tận hoặc đóng lifecycle hai lần | 4 |
| I13 | **Delegation là chokepoint RIÊNG, không phải method kernel** | `delegation/manager.py:63` · `DelegationServicePort.delegate` | Trộn delegation vào kernel → mất audit/scope per-child | 6 |
| I14 | **Scope con ⊆ scope cha** | `delegation/policy.py` · `validate()`, `scope <= parent.allowed_capabilities` | Con leo quyền vượt cha; đệ quy không kiểm soát | 6 |
| I15 | **Acceptance honor evidence thật, không scaffolding** | `supervisor/evidence.py` · `NON_EVIDENCE_KINDS`, `≥1-valid` | Agent-O "pass" bằng cách trỏ vào giấy nháp của chính nó | 6,7 |
| I16 | **Redact trước khi payload ra UI/SSE** | `control/redaction.py` · `Redactor().apply()` (mask, không mutate gốc) | Secret/PII rò ra client | 7 |
| I17 | **attribution ≠ authz** | `control/authz.py` · `requires_permission`+`checkpoint`, không phải `issued_by` | Tin lời người gọi tự khai → leo quyền | 7 |

**Đọc bảng này như một tín điều:** khi bạn sửa một file ở cột 3, mở phase tương ứng để biết test nào phải chạy lại.

---

## 3. Bảng pitfall tổng — *bug & footgun sẽ gặp khi tự dựng*

Gộp từ [`docs/reference/known-risks.md`](../../docs/reference/known-risks.md). `LIVE` = có thật ở config mặc định;
`LATENT` = chỉ thành rủi ro khi bật/thêm gì đó. Chi tiết "triệu chứng → nguyên nhân → cách tránh" nằm trong từng phase.

| Pitfall | Trạng thái | Nơi | Bài học | Phase |
|---|---|---|---|---|
| **Log raw `args` vào `events.jsonl`** | 🔴 LIVE | `core/kernel.py` `tool.requested` | Secret/PII vào disk. Redact/`args_digest` trước khi bật write/MCP tool | 1,7 |
| **Retry không biết idempotency** | 🟡 LATENT | `middleware/retry.py` | Retry *mọi* `ok=False` → side-effect chạy 2 lần. Chỉ retry khi `read_only/idempotent` | 3 |
| **Không deny-list ở kernel mặc định** | 🟡 LATENT | `core/bootstrap.py` PolicyGate opt-in | Capability ngoài toolbox không qua policy nào. Bật `middleware.policy` khi thêm tool ngoài | 3 |
| **Tưởng `checkpoint.json` là state resume** | 🟡 LATENT | `orchestrator/checkpoint.py` | Debug sai, sửa tay vô tác dụng. Nó là read-only cho UI | 4 |
| **Hợp đồng serializable *ngầm* của state** | 🟡 LATENT | `graph/state.py` | Nhét dataclass vào `session.state` → vỡ resume *về sau*. Thêm test resume cho state mới | 4 |
| **Middleware fail-open chạy tool 2 lần (FM-HIGH)** | ✅ đã vá | `core/kernel.py` `_LatchedNext` (DEC-8) | `nxt` latch one-shot: raise sau khi gọi `nxt` **không** chạy lại tool | 1,3 |
| **Same-tool guard nhân đôi** | ⚠️ thiết kế | guard ở graph nodes, **cố ý không** ở middleware | Bộ đếm là per-run → đừng đặt ở middleware (`bootstrap.py`) | 4 |
| **E07↔E09 / E11↔E12 vòng phụ thuộc** | ⚠️ thiết kế | roadmap | Phá vòng bằng *interface trước, nội dung sau* (skill role-agnostic) | 5,6 |

---

## 4. Quy ước repo (đặt từ Phase 0, giữ tới cuối)

Mấy cái nhỏ này là "vệ sinh" giúp dự án **bền** — bỏ qua thì 3 tháng sau trả nợ:

- **`var/` luôn gitignored.** Mọi tạo tác run (`events.jsonl`, `summary.json`, `langgraph.sqlite`,
  `checkpoint.json`, `workspace/`) sống dưới `var/agent_runs/<run_id>/`. Không bao giờ commit.
- **UTF-8 không BOM** ở mọi file. (Nhỏ nhưng vỡ JSON/parse nếu lẫn BOM.)
- **`MAP.md` tự sinh** bằng `python tools/gen_map.py` — mỗi module **bắt buộc** có 1 dòng docstring mục đích + epic.
  Thêm/đổi file → chạy lại. Đây là cách "bản đồ không bao giờ lạc hậu".
- **Một epic mỗi đợt.** Không nhảy cóc. CHANGELOG ghi "thêm gì, vì sao", gắn Sprint+Epic.
- **Ports/Adapters (hexagonal).** `core/` **không import** LangGraph/Qdrant/OpenAI. Hạ tầng nằm sau `*Port`
  (`core/ports.py`, `rag/ports.py`, `control/ports.py`). Đổi hạ tầng = viết adapter mới, không sửa logic.
- **Optional deps tách group.** `pip install -e ".[dev]"` cho base; `.[rag]` (qdrant/fastembed) khi cần —
  không nhồi mọi thứ vào base install.
- **Decision register.** Mọi quyết định kiến trúc ghi vào `docs/decisions.md` (DEC-N) để **không relitigate**.

---

## 5. Cách tự kiểm chứng (chạy ở mọi phase)

```bash
python -m pip install -e ".[dev]"                 # base
python run_smoke.py                                # CORE_AGENT_SMOKE_OK (no LLM/network)
python -m pytest -q                                # phải xanh hết
python -m observability.inspect summary latest     # tóm tắt run gần nhất
python -m observability.inspect events latest      # chuỗi event qua chokepoint
```

**Triết lý test:** `tests/` = unit/contract đi cùng feature; `tests_audit/` = adversarial/property/fuzz/security
(soát biên, jail-escape, resume-matrix, round-trip contract). Viết test cho AC **ngay khi** mỗi epic xong,
không để dồn. Test là *cổng đóng phase*, không phải việc làm cuối.

---

## 6. Map về tài liệu gốc trong repo (đối chiếu khi nghi ngờ)

| Muốn biết | Đọc |
|---|---|
| File nào là gì | [`MAP.md`](../../MAP.md) (tự sinh) |
| Một task chạy input→output thế nào | [`docs/reference/runtime-flow.md`](../../docs/reference/runtime-flow.md) |
| File dễ vỡ + footgun | [`docs/reference/known-risks.md`](../../docs/reference/known-risks.md) |
| Thứ tự xây + cổng phụ thuộc | [`docs/roadmap/dependency-map.md`](../../docs/roadmap/dependency-map.md) |
| Vì sao chọn thế này | [`docs/decisions.md`](../../docs/decisions.md) (DEC-1..8) · [`docs/spec/`](../../docs/spec/) |
| Thêm gì, vì sao, khi nào | [`CHANGELOG.md`](../../CHANGELOG.md) |

---

*Tài liệu này là index. Đi tiếp: [Phase 1 — Microkernel & chokepoint](phase-1-microkernel-chokepoint.md).*
