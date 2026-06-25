# 00 — Feature Catalog & Epic Backlog (cho lần xây lại)

> Tóm gọn từng tính năng HAY của `my_agents` hiện tại, rồi gom thành backlog epic để viết PRD/epic/story/AC.
> Nguồn: toàn bộ review + chạy thử + log thật (xem `NEW_REPO_BUILD_GUIDE.md`, `REVIEW_*.md`, `docs/21–24`).
> Ghi chú vui: project đã có sẵn **Software Factory** sinh BRD/PRD/epic/AC tự động — nhưng để "xây lại từ đầu cho sạch & dễ kiểm soát", ta tự viết tay (có kiểm soát) thay vì sinh máy.

## A. Catalog tính năng hay (giữ lại cho bản mới)

Cột **Trạng thái**: ✅ giữ gần nguyên · 🔧 giữ ý tưởng nhưng làm lại sạch hơn · ✨ mới (chưa có, nên thêm).

### Tầng nền (Phase 0)
- **F01 — Agent Kernel (hexagonal)**: state + events + registry, hành vi nằm sau ports/adapters. *Hay vì*: lõi tối giản, thêm năng lực không đụng lõi. ✅
- **F02 — CapabilityResult envelope**: mọi tool trả cùng `{ok,capability,feature,data,error,metadata}`. *Hay vì*: orchestrator không phải đoán shape. ✅
- **F03 — Capability registry + Null-object fallback**: thiếu tool vẫn trả kết quả có cấu trúc, kernel không chết. *Hay vì*: degrade graceful. ✅
- **F04 — Feature plugin (config-driven)**: bật/tắt feature qua `features.yaml`, mỗi feature khai test. *Hay vì*: tháo-lắp, có hợp đồng. ✅
- **F05 — Output discipline (JSON gate + repair)**: ép JSON-only, sửa JSON hỏng. *Hay vì*: trị model hay lệch format. 🔧 (thêm JSON-mode/grammar ở LLM layer — log thật hỏng 33%).
- **F06 — Observability event-sourced**: event log JSONL (Message/Action/Observation/State) + `inspect_runs` CLI. *Hay vì*: debug & audit dễ. ✅
- **F07 — Context condense + finish-gate + budget chống loop**: nén observation, chặn final khi chưa validate, ngân sách lặp. *Hay vì*: kỷ luật runtime. ✅

### Tầng single-agent + tools/skills/RAG (Phase 1–2)
- **F08 — Single-agent tool loop (ReAct)**: lặp gọi tool → quan sát → final. *Hay vì*: nền của mọi thứ. 🔧 (xây trên graph từ đầu).
- **F09 — MCP tool layer "một cửa"**: resolve→validate→policy→spawn→envelope; 18 server nội bộ. *Hay vì*: ranh giới tool sạch. 🔧 (persistent session).
- **F10 — Sandbox & policy an toàn**: path-jail workspace, git-mutation hard-block, terminal argv-only + risk metadata, docker opt-in. *Hay vì*: an toàn thật (đã verify runtime). 🔧 (gom về 1 chokepoint).
- **F11 — Skills (contract markdown)**: workflow + Allowed/Forbidden + tool đích danh. *Hay vì*: đặt "thói quen" + ranh giới cho agent. 🔧 (theo template `docs/24` + progressive disclosure).
- **F12 — RAG local**: Qdrant + fastembed, health→ingest→search, sandbox workspace. *Hay vì*: trí nhớ/tra cứu ngoài prompt. ✅

### Tầng multi-agent (Phase 3)
- **F13 — Config-driven roles**: `roles/*.yaml` với allowed_tools, route_permissions, test_ownership (tách nhiệm vụ: code không tự validate). *Hay vì*: RBAC khai báo, rất sạch. ✅
- **F14 — Lenses**: góc nhìn review nhận thức nhúng vào prompt department. *Hay vì*: kiểm tra đa chiều rẻ. ✅
- **F15 — LangGraph runtime**: roles trên StateGraph, finish-gate, **repair-mode ép vá hẹp**, budget per-subtask, bám required-files. *Hay vì*: multi-agent có kỷ luật. 🔧 (làm runtime DUY NHẤT, single = 1 node).
- **F16 — Company pipeline**: research→BA→planner→architect→(code↔test)→review→ledger→final, handoff có gác cổng. *Hay vì*: quy trình kỹ sư rõ. ✅
- **F17 — Departments**: research (search/source/pdf/citation), safety (permission/risk/prompt-injection/tool-scope). *Hay vì*: nhóm năng lực + chốt an toàn. ✅

### Tầng cognition / tự cải tiến (Phase 4)
- **F18 — Intent Router + Global Supervisor**: phân loại task → chọn graph/department (đa nhiệm). *Hay vì*: 1 router cho nhiều loại task. 🔧 (thêm fallback LLM khi confidence thấp).
- **F19 — Software Factory**: prompt lớn → BRD/PRD/epic/AC/domain/architecture/implementation-spec/handoff (artifact thật). *Hay vì*: biến yêu cầu thành spec có thể trace. ✅
- **F20 — Ledger (bộ nhớ kinh nghiệm)**: append-only decision/failure/lesson. *Hay vì*: nền tự học. ✅
- **F21 — Self-eval & governed self-improvement**: blind evaluator, **critical auditor (bắt multi-agent theater)**, flow observer, trace health, **evolution proposal-only** (cần người duyệt). *Hay vì*: bản sắc — hệ tự đánh giá, không tự ý sửa mình. ✅
- **F22 — User Agent / live control**: chèn directive khi run đang chạy (inbox). *Hay vì*: human điều khiển giữa chừng. ✅
- **F23 — Human Review Gate (Plannotator-style)**: approve/deny/annotate plan & diff trước hành động nguy hiểm. *Hay vì*: chốt người-trong-vòng-lặp. ✨
- **F24 — Process Dashboard UI**: xem process/log/state. *Hay vì*: quan sát trực quan. ✅

### Cross-cutting & labs
- **F25 — Test/Regression harness**: groups (project/rag/chain/mcp_ext/langgraph/skill/e2e), smoke/demo, dev_checks, capability_suite, feature-contract tests. *Hay vì*: kiểm hồi quy hành vi agent. ✅
- **F26 — Repo Understanding (deterministic)**: scan/AST/graph/test-map → context-pack → answer/impact, **No-Leap Guardian** (evidence-bounded). *Hay vì*: agent hiểu repo bằng bằng chứng, không đoán. ✅
- **F27 — Mini-repo lab harness**: registry `runpy` chạy lab độc lập (business_prompt_lab, self_eval_qa_lab, repo_understanding_lab). *Hay vì*: vườn ươm thí nghiệm có kỷ luật. ✅
- **F28 — Docs/ADR discipline**: docs đánh số + ADR. *Hay vì*: quyết định có vết. ✅

## B. Backlog Epic đề xuất (để viết PRD)

Gom feature thành epic, theo thứ tự phase của `NEW_REPO_BUILD_GUIDE.md`:

| Epic | Phase | Gồm feature | Mục tiêu một dòng |
|---|---|---|---|
| **E01 — Agent Kernel & Contracts** | P0 | F01,F02,F03,F04 | Lõi hexagonal + envelope + registry + feature plugin |
| **E02 — Output Discipline** | P0 | F05,F07 | JSON gate + JSON-mode + condense + finish-gate + budget (module dùng chung) |
| **E03 — LLM Adapter** | P0 | (F05) | OpenAI-compatible, JSON-mode, lazy-init, retry |
| **E04 — Observability** | P0 | F06 | Event log + run artifacts + inspect CLI |
| **E05 — Single-agent Graph Loop** | P1 | F08 | LangGraph 1-node: agent↔tool, route_next |
| **E06 — MCP Tool Layer & Safety** | P2 | F09,F10 | Một-cửa + policy chokepoint + sandbox + persistent session |
| **E07 — Skills System** | P2 | F11 | Contract template (Allowed/Forbidden + tool đích danh) + loader progressive |
| **E08 — RAG** | P2 | F12 | Qdrant+fastembed health/ingest/search |
| **E09 — Roles & Lenses** | P3 | F13,F14 | Roles YAML (allowlist/route/test-ownership) + lens groups |
| **E10 — Multi-agent Graph (Company)** | P3 | F15,F16 | Pipeline roles trên cùng graph + repair-mode + gated handoff |
| **E11 — Departments** | P3 | F17 | Research + Safety department |
| **E12 — Intent Router & Supervisor** | P4 | F18 | Định tuyến đa nhiệm |
| **E13 — Software Factory** | P4 | F19 | Pipeline spec (BRD→implementation spec) |
| **E14 — Ledger & Memory** | P4 | F20 | Bộ nhớ kinh nghiệm + RAG kinh nghiệm |
| **E15 — Self-eval & Governance** | P4 | F21 | Blind eval + critical auditor + evolution proposal-only |
| **E16 — Human Review Gate** | P4 | F23 | Approve/deny/annotate plan & diff |
| **E17 — User Live Control** | cross | F22 | Directive inbox giữa run |
| **E18 — UI & Dashboard** | P4 | F24 | Process/log/state UI |
| **E19 — Test/Regression Harness** | cross | F25 | Groups + smoke + dev_checks |
| **E20 — Labs (optional)** | sau | F26,F27 | Repo-understanding, prompt-lab, self-eval-lab |

## C. Quy trình viết PRD (đề xuất)

- **1 PRD / epic**, mỗi PRD gồm: *Problem & Goal · Scope (in/out) · Stories · Acceptance Criteria (testable) · Dependencies · Exit/metrics*.
- Thứ tự viết theo phase: **E01 → E04 (P0)** trước, vì mọi thứ phụ thuộc nền.
- Lưu tại `rebuild_from_zero/E01_kernel/PRD.md`, `.../stories.md`, `.../acceptance.md` (hoặc gộp 1 file/epic — tùy bạn).
- Mỗi story có AC dạng Given/When/Then để map thẳng sang test (hợp với E19 harness).

(Đầy đủ catalog + epic ở trên; bước sau ta viết từng PRD.)
