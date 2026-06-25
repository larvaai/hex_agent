# Build Guide — Repo agent đa nhiệm (xây từ đầu, theo tầng)

> Tổng hợp từ toàn bộ review + chạy thử + phân tích run thật của `my_agents`, cộng ý tưởng ClaudeKit/Plannotator.
> Mục tiêu: xây một repo MỚI lên tới mức của repo hiện tại, nhưng **không lặp lại nợ kỹ thuật** đã phát hiện.
> Đọc kèm: `REVIEW_multi_agent_and_mcp.md`, `RUN_EVALUATION.md`, `LOG_ANALYSIS_run_20260614_152853.md`, `docs/21`, `docs/22`.

---

## Phần I — Kiến trúc nên theo TỪ ĐẦU (cho đa nhiệm vụ)

**Khuyến nghị một câu:**
> Hexagonal **Agent Kernel** (ports & adapters) + **một** substrate orchestration dạng graph (single-agent = graph 1 node, multi-agent = N node) + **config-driven** roles/features/routing + **module "kỷ luật" dùng chung** (JSON gate, condense, finish-gate, budget) + **MCP tool boundary** một cửa + **observability event-sourced** ngay từ commit đầu.

Đây chính là phần TỐT NHẤT của repo hiện tại (`core/` kernel của bạn rất chuẩn), nhưng **bỏ đi 2 nợ lớn**: (1) hai thế hệ orchestrator song song, (2) trùng lặp "discipline" giữa `orchestrator.py` và `langgraph_orchestrator.py`.

### Vì sao kiến trúc này hợp "đa nhiệm vụ"
Đa nhiệm = nhiều loại task (hỏi đáp, repo Q&A, code, research, product build...). Cách scale sạch:
- **Kernel** không biết gì về task — chỉ sở hữu state/events/registry.
- **Router** chọn *workflow/sub-graph* phù hợp từng loại task (rule-based trước, LLM fallback sau).
- **Mỗi loại task = một graph** dùng chung node/loop/discipline. Thêm nhiệm vụ mới = thêm graph + entry router, **không sửa lõi**.
Đây là điều giúp bạn không bị "một pipeline cứng" và cũng không bị "N orchestrator rời rạc".

### 10 nguyên tắc baked-in (mỗi cái là một bài học thật)
1. **Một substrate orchestration duy nhất (graph).** Single-agent = graph 1 node. KHÔNG viết loop lần 2 cho multi-agent. *(Tránh nợ #1 của repo cũ.)*
2. **Discipline là module dùng chung**: JSON gate + repair, context condense, finish-gate, loop/stuck budget — viết MỘT lần, mọi node/graph import. *(Tránh trùng `orchestrator.py` ↔ `langgraph_orchestrator.py`.)*
3. **Structured output ở tầng LLM ngay từ đầu**: bật JSON-mode / GBNF grammar trong LLM adapter. *(Run thật cho thấy model local hỏng JSON 33% ở bước final khi không ép schema.)*
4. **Hexagonal kernel + envelope chuẩn** `CapabilityResult{ok,capability,feature,data,error,metadata}`. Tool nào cũng trả cùng hình dạng.
5. **Config-driven**: `features.yaml` (feature tháo-lắp), `roles/*.yaml` (allowed_tools, route_permissions, test_ownership, lenses), `routing.yaml`. Thêm role/feature không cần sửa code lõi.
6. **An toàn = một chokepoint policy**, không rải rác mỗi server. Path-jail, mutation block, shell/argv guard tập trung ở policy layer + base tool class. *(Repo cũ rải guard khắp các server → dễ quên khi thêm server.)*
7. **Observability từ commit 1**: event log JSONL (Message/Action/Observation/State) + run artifacts + CLI inspect. Rẻ khi làm sớm, đắt khi nhồi sau.
8. **Vệ sinh nền tảng**: `requires-python>=3.11` *(repo cũ crash vì `tomllib` trên 3.10)*; UTF-8 không BOM + pre-commit chặn BOM *(11 file BOM ở repo cũ)*; `.gitignore var/` + chặn secret *(repo cũ commit `cookies.json`)*; **lazy-init LLM client** *(repo cũ init lúc import → kẹt proxy)*.
9. **Human-in-the-loop gate là seam hạng nhất** (Plannotator-style): thiết kế chỗ "approve/deny/annotate" sớm, kể cả khi build sau.
10. **Tự sửa mình chỉ ở dạng proposal** (cần người duyệt) — không bao giờ tự áp dụng. *(Đã đúng ở `self_eval_qa_lab`.)*

### Tech stack đề xuất
- **Python 3.11+** (ép trong `pyproject.toml`), quản lý bằng `uv` hoặc venv+pip.
- **LangGraph** làm substrate graph (dùng từ Phase 1, single-agent luôn).
- **pydantic** cho action schema + tool args + structured output (sạch hơn validator tay).
- **MCP** cho tool boundary (stdio nhưng **persistent session**, đừng spawn mỗi call).
- **Qdrant + fastembed** cho RAG.
- **ruff + pytest + pre-commit** (lint, test, chặn BOM/secret).
- **LLM adapter** OpenAI-compatible: JSON-mode/grammar, lazy init, timeout, retry.

### Cây thư mục gợi ý (ổn định qua mọi phase)
```
core/        kernel: state, events, registry, schemas(envelope), ports/
discipline/  json_gate, repair, condense, finish_gate, budget   (dùng chung)
llm/         adapter OpenAI-compatible (JSON-mode, lazy, retry)
features/    plugin: mcp_tools, rag, ...  (+ loader, contracts, nulls)
graphs/      single_agent.py, company.py, ... (cùng node/loop)
agents/      role agents + lenses (build từ config)
config/      features.yaml, roles/*.yaml, routing.yaml
tools_mcp/   các MCP server nội bộ + policy chokepoint
skills/      *.SKILL.md (workflow instructions)
memory/      ledger, rag store
observability/ event log + run artifacts + inspect CLI
review_gate/ (Phase 4) human approve/deny/annotate
app.py       CLI verbs: plan / cook / test / review / ask
var/         (gitignored) runs, plans, reviews, lessons, qdrant
```

---

## Phần II — Lộ trình 5 tầng (Phase)

> Mỗi phase có **exit criteria** rõ. Không sang phase sau khi chưa đạt.

### Phase 0 — Nền móng (trước khi có agent)
**Xây:** `core/` kernel (state, EventBus, CapabilityRegistry + NullToolPort fallback, `CapabilityResult`), `discipline/` (JSON gate + repair, condense, finish-gate, budget), `llm/` adapter (JSON-mode + lazy init), `config/` loader, observability (event log + run dir), policy chokepoint khung. Set `pyproject` 3.11+, ruff/pytest/pre-commit (chặn BOM+secret), `.gitignore var/`.
**Exit:** đăng ký được 1 dummy tool → gọi qua kernel → nhận envelope → ghi event log; `pytest` xanh; pre-commit chặn BOM.

### Phase 1 — Single-agent loop (trên graph 1 node)
**Xây:** một LangGraph `StateGraph` tối giản: node `agent` (gọi LLM → action JSON qua discipline) + node `tool` + `route_next` (tool/final). Tái dùng toàn bộ `discipline/`. 2–3 MCP tool đầu (filesystem, terminal). CLI `app.py ask "<task>"`.
**Vì sao graph ngay từ single-agent:** để Phase 3 multi-agent **không phải viết lại loop** — chỉ thêm node. Đây là quyết định kiến trúc quan trọng nhất.
**Exit:** chạy LLM thật, hoàn thành 1 task đọc-tool (vd git/đọc file), event log sạch, JSON discipline giữ (đo parse-error rate < ngưỡng nhờ JSON-mode).

### Phase 2 — Tools (MCP) + Skills + RAG
**Xây:** MCP layer sau kernel registry (một cửa: resolve → validate → policy → spawn(persistent) → envelope), path-jail + policy chokepoint. Skills (`*.SKILL.md`) nạp vào prompt. RAG = một feature/MCP (Qdrant + fastembed: health → ingest → search, sandbox workspace).
**Exit:** agent dùng được tool + skill + RAG; mọi I/O sandbox; MCP dùng persistent session (không spawn mỗi call); RAG health-gate trước search.

### Phase 3 — Multi-agent (roles trên cùng graph)
**Xây:** role agents từ `config/roles/*.yaml` (allowed_tools + route_permissions + test_ownership + lenses); BaseAgent enforce allowlist runtime. Graph company: research → plan → architect → (code ↔ test) → review → ledger → final, dùng **cùng** node/loop/discipline + finish-gate + repair-mode (vá hẹp) + budget chống loop. Departments: research, safety (permission/risk/prompt-injection). Router chọn graph theo intent.
**Exit:** pipeline company chạy LLM thật, separation-of-duties đúng (code không tự validate), code↔test hội tụ, có event trail đầy đủ.

### Phase 4 — Cognition & self-improvement (mức repo hiện tại + tích hợp)
**Xây:**
- **Ledger** (bộ nhớ kinh nghiệm: decision/failure/lesson) + RAG kinh nghiệm.
- **Self-eval harness** (như `self_eval_qa_lab`): simple-answer baseline, blind evaluator, flow observer, **critical auditor** (bắt "multi-agent theater"), trace-health, **evolution decider proposal-only**.
- **Software-factory** style: prompt lớn → plan/spec artifact → handoff sang coding.
- **Global supervisor / intent router** cho đa nhiệm (đây là chỗ "đa nhiệm vụ" được giải quyết: 1 router → nhiều graph).
- **Review gate (Plannotator-style)** trên process dashboard + user-agent inbox: approve/deny/annotate trước hành động nguy hiểm và trước khi update skill/lens.
- **Mode flags** (fast/deep/red_team/parallel/tdd/review_gate) + **artifact tree** (`var/{plans,reviews,decisions,failures,lessons}`) + **CLI verbs** (plan/cook/test/review) — học ClaudeKit.
**Exit:** hệ tự quan sát + tự đánh giá + có human gate, chạy đa loại task qua router, đề xuất cải tiến (không tự áp dụng).

---

## Phần III — Bảng map nhanh (cũ → mới)

| Repo hiện tại | Giữ lại | Sửa khi làm mới |
|---|---|---|
| `core/` kernel + envelope | ✅ giữ gần như nguyên | — |
| `orchestrator.py` + `langgraph_orchestrator.py` | ý tưởng guardrail | **gộp làm một** graph substrate + discipline dùng chung |
| `output_gate` | ✅ ý tưởng | + bật JSON-mode ở LLM layer (đừng chỉ repair sau) |
| `features/mcp_tools/client.py` | ✅ một-cửa | + persistent session + policy chokepoint tập trung |
| `config/roles/*.yaml` + lenses | ✅ rất tốt | giữ |
| `mcp_servers/*` | ✅ | bỏ BOM, base class có guard chung |
| `experiments/self_eval_qa_lab` | ✅ bản sắc | đưa lên thành tầng cognition chuẩn, tách file (đừng để 3k dòng) |
| labs đặt 3 nơi | — | gom `labs/` ở root |
| `llm.py` init lúc import | — | lazy init |

## Phần IV — Quyết định cần chốt sớm
1. **LangGraph** làm substrate (khuyến nghị) hay graph tự viết tối giản? → LangGraph để khỏi tự bảo trì engine; chấp nhận 1 dependency.
2. **MCP stdio persistent** hay in-process tool registry cho tool nội bộ? → cân nhắc in-process cho tool Python nội bộ (nhanh hơn nhiều), giữ MCP cho external.
3. **Mức tự động của review gate**: chặn cứng hành động nguy hiểm ngay từ Phase 3 hay để Phase 4? → khuyến nghị có "khóa an toàn" tối thiểu (git mutation, xóa file) ngay Phase 2–3.

## Kết
Bạn đã có sẵn các mảnh đúng (kernel, envelope, config-roles, lens, ledger, self-eval). Repo mới nên **giữ những mảnh đó nhưng đặt trên một substrate graph duy nhất + discipline dùng chung + structured-output từ LLM layer**, và làm observability/safety/human-gate thành nền chứ không phải vá sau. Xây theo 5 phase, mỗi phase chạy được thật trước khi lên tầng tiếp theo — đó là cách lên tới mức repo hiện tại mà không tích nợ.
