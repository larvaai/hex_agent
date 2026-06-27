---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 5 — Workflow build-along: Skills & RAG

> Cặp với: roadmap [phase-5-skills-rag.md](../phase-5-skills-rag.md) · Epic E07+E08 · Invariant health-gate + ports · Mục tiêu: vừa BUILD vừa HIỂU phase này qua skill + cổng

Phase này dạy **một bài học kiểm soát hai lần**: tách hợp đồng khỏi hiện thực. Skill tách *contract tool* khỏi *role dùng nó* (role-agnostic); RAG tách *logic ingest/search* khỏi *Qdrant chạy nó* (Port + health-gate). Hai nhánh `skills/` và `rag/` không phụ thuộc nhau về code — chỉ gặp ở một chokepoint: `kernel.execute_tool` + `kernel.registry`.

---

## 0. Bạn sẽ rời phase này khi

**Build được X** (mỗi gạch đầu dòng là một lệnh chạy được — nếu chưa chạy trong turn này thì chưa "done", Iron Law):
- `pytest tests/test_skills.py tests/test_rag.py tests_audit/test_rag_edges_rigor.py tests_audit/test_rag_qdrant_adapter_contract.py tests_audit/test_roles_skills_config_integrity.py` — 100% pass, **không khởi Qdrant** (DoD, [phase-5-skills-rag.md:220](../phase-5-skills-rag.md)).
- `python -c "from rag.ports import VectorStorePort; print('ok')"` chạy được trên máy **chưa cài** qdrant-client ([phase-5-skills-rag.md:103](../phase-5-skills-rag.md)).
- `reg.render("code_review", mode="contract")` ra description+Allowed+Forbidden; `mode="full"` mới thêm Steps+Report (`registry.py:57-76`).
- `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`; `python -m pytest -q` → 0 fail.

**Giải thích được Y (theo *luật → file·hàm → phá ra mất gì*):**
- I1 — vì sao 3 tool RAG phải qua `execute_tool` (`feature.py:113-121`) chứ không gọi service tay.
- Health-gate — vì sao `health()` **không bao giờ ném** (`stores_qdrant.py:83`) biến "Qdrant chết" thành nhánh `if`, không phải exception.
- Ports/I2-roadmap — vì sao `grep -n qdrant rag/service.py` phải **rỗng**.
- Pitfall E07↔E09 — vì sao `SkillSpec` **không có trường role** (`spec.py:26`) phá được vòng phụ thuộc.

**Vẽ được đường đi một lệnh `rag_search` (seam nằm đâu):** caller → `kernel.execute_tool("rag_search", args)` (chokepoint + `tool.*` event) → `RagSearchTool.execute` (`feature.py:89`, +`rag.search` event) → `RagService.search` (`service.py:78`) → `_require_healthy()`→`store.health()` (HEALTH-GATE: down → envelope, dừng) → `embedder.embed([query])` (qua `EmbedderPort`) → `store.search(vector, k, threshold)` (qua `VectorStorePort` ← SEAM) → `InMemory cosine | Qdrant query_points` (adapter cụ thể, service không biết) ([phase-5-skills-rag.md:47-56](../phase-5-skills-rag.md)). Từ `RagService` trở xuống **không một dòng nhắc `qdrant`** — đó là chứng cứ seam đặt đúng.

Không đạt **cả hai** → đọc lại `phase-5-skills-rag.md` §5 (invariant) + §6 (pitfall), chạy lệnh tự kiểm, quiz lại. (giao thức cổng điều kiện (a)+(b)).

---

## 1. Ý tưởng triển khai khả thi (đọc là biết làm gì)

Năm ý tưởng cụ thể, mỗi cái neo file:line thật từ roadmap. Thứ tự bắt buộc: **hợp đồng trước, hạ tầng sau; offline trước, prod sau** ([phase-5-skills-rag.md:83](../phase-5-skills-rag.md)).

**Y1 — Parser SKILL.md → `SkillSpec` frozen, không role** (`skills/spec.py`).
`SkillSpec` là `@dataclass(frozen=True)` chỉ chứa tool canonical, **không trường role** (`spec.py:26`). `parse_skill` tách frontmatter (`_split_frontmatter`, `spec.py:39`) → cắt body theo heading (`_split_sections`, `spec.py:50`); thiếu `name`/`description`/frontmatter → `ValueError` (`spec.py:103-106`). Hai mẹo phải bắt: heading match bằng *substring case-insensitive* nên "Allowed (tools)" ≡ "Allowed Tools" (`spec.py:19-21`); `_bullets` lọc placeholder (`""`, `none`, `n/a`, `-`) để section rỗng không sinh tool ma (`spec.py:23,76-85`).
→ *Ra cái gì để biết xong:* `pytest tests/test_skills.py -k "parse or missing"` — 4 test xanh (`test_parse_extracts_contract_fields`, `test_missing_name_raises`, `test_missing_description_raises`, `test_missing_frontmatter_raises`).

**Y2 — Registry + progressive disclosure** (`skills/registry.py`).
`render(name, mode="contract")` chỉ ghép description+Allowed+Forbidden; `mode="full"` thêm Steps+Report (`registry.py:57-76`); mode lạ → `ValueError` (`registry.py:58-59`). `register` từ chối trùng tên thay vì ghi đè im lặng (`registry.py:22-26`). `union_tools` (`registry.py:79`) là *đóng góp phía skill* cho allowlist E09 — registry **không** tự nhắc role.
→ *Ra cái gì:* `pytest tests/test_skills.py -k "render or union"` — `test_render_contract_excludes_steps_report`, `test_render_full_includes_steps_report`, `test_union_tools_across_skills` xanh.

**Y3 — RAG Port + value types + service health-gated** (`rag/ports.py`, `rag/service.py`).
Định nghĩa **seam trước adapter**. Value types `Chunk`/`Hit` frozen (`ports.py:8,16`) là "tiền tệ" hai bên seam; ports là `Protocol` `runtime_checkable` (`ports.py:24,31`) nên adapter không cần kế thừa. `RagConfig.from_dict` lọc field lạ (`ports.py:53`). `RagService._require_healthy()` (`service.py:30`) chạy **trước** mọi ingest/search; store down → envelope `dependency_unavailable`, không ném. Ingest qua jail `resolve_in_workspace` (`service.py:47`, móc về Phase 3 I8); refuse cardinality mismatch trước upsert (`service.py:64-69`); `delete_by_source` **trước** `upsert` (`service.py:71`).
→ *Ra cái gì:* `python -c "from rag.ports import VectorStorePort; print('ok')"` không cần qdrant; `pytest tests/test_rag.py` — health-gate chặn khi down, path ngoài workspace bị từ chối.

**Y4 — Offline store + embedder, rồi wire 3 tool qua chokepoint** (`rag/stores.py`, `rag/embedders.py`, `rag/feature.py`).
`InMemoryVectorStore.set_healthy()` bật/tắt cổng dep không cần server (`stores.py:32`); cosine deterministic sort `(-score, source, chunk_index)` rồi cắt `top_k` (`stores.py:47-56`). `FakeEmbedder` bag-of-words hash L2 (`embedders.py:33-46`). `build_service` chọn backend từ config — `memory` mặc định, `qdrant` lazy-import; backend lạ → `ValueError` (`feature.py:30-42`). `install` đăng ký `FeatureDescriptor`+3 tool vào `kernel.registry` (`feature.py:109-121`); mỗi wrapper phát event ngữ nghĩa `rag.health`/`rag.ingest`/`rag.search` (`feature.py:72,81,90`) song song `tool.*` của kernel.
→ *Ra cái gì:* `pytest tests/test_rag.py tests_audit/test_rag_edges_rigor.py` xanh không docker; `pytest tests_audit/test_roles_skills_config_integrity.py -k "tool_names_are_known"` xanh.

**Y5 — Qdrant adapter (prod, optional, lazy)** (`rag/stores_qdrant.py`).
Chỉ làm **sau** khi offline xanh. `qdrant_client` import **lazy trong `__init__`** (`stores_qdrant.py:43`); `__init__` chấp nhận `client: object | None` inject → test bằng FakeClient không cần server. Collection tạo lười theo dim ở lần upsert đầu (`_ensure_collection`, `stores_qdrant.py:52`): check tồn tại *ngoài* lock rồi create *trong* lock + double-check → dưới nhiều upsert đồng thời chỉ tạo đúng một lần (`stores_qdrant.py:57-73`). `upsert` validate cả batch (vector không None/rỗng, đồng nhất dim) **trước** mọi network call (`stores_qdrant.py:104-112`) để batch xấu không nửa-ghi. `_point_id = uuid5(source::chunk_index)` (`stores_qdrant.py:28`); `health()` bọc `try/except` → unreachable trả `{"ok": False}` (`stores_qdrant.py:83-90`).
→ *Ra cái gì:* `pytest tests_audit/test_rag_qdrant_adapter_contract.py` dùng FakeClient (`:63`), không cần Qdrant; `test_lazy_collection_creation_is_singleton_under_concurrent_first_upsert` (`:218`) xanh.

**Config knobs cần khi rebuild** (neo từ [phase-5-skills-rag.md:73-79](../phase-5-skills-rag.md) — nắm trước khi cook để AC khớp default):

| Knob | Mặc định | Ở đâu | Ý nghĩa |
|---|---|---|---|
| `rag.backend` | `memory` | `config/features.yaml:19` | `memory` (offline) hoặc `qdrant` (prod) |
| `score_threshold` | `0.8` | `ports.py:45` | điểm cosine tối thiểu mới tính là hit (**inclusive** — test biên `>=`) |
| `top_k` | `5` | `ports.py:46` | số hit trả về sau khi sort |
| `chunk_size`/`overlap` | `800`/`100` | `ports.py:43-44` | cửa sổ ký tự; `step = size - overlap` clamp ≥1 (overlap≥size → step=1, không loop vô hạn, `chunking.py:23`) |
| `qdrant_timeout` | `30.0` | `ports.py:51` | nới rộng vì tạo collection có thể chậm vài giây |

---

## 2. Workflow skill-by-skill (vòng lặp build)

Bám buildLoop kernel brief: understand/scout → plan → critique → cook TDD → test → code-review → debug/fix → remember. Curriculum tối thiểu: **scout(2) → plan(4) → approve(5) → cook(6) → test(7) → review(8)**.

| Bước | Skill (invoke) | Prompt mẫu (copy-được) | Artifact (path thật) | Mục đích |
|---|---|---|---|---|
| 1 | `hs:understand` — `/hs:understand rag/ skills/` | `Đọc rag/ và skills/ trong hex_agent. Tôi sắp build Phase 5 (E07 skills + E08 RAG) theo plans/260626-1358-clone-hex-agent-roadmap/phase-5-skills-rag.md. Dựng bản đồ: seam Port nằm đâu, health-gate ở hàm nào, vì sao SkillSpec không có role. Đừng sửa code.` | `plans/reports/<slug>-report.md` | Hiểu vùng code lạ trước khi plan |
| 2 | `hs:scout` — `/hs:scout` | `Định vị trong hex_agent: (1) RagService._require_healthy và mọi đường gọi ingest/search; (2) build_service chọn backend; (3) parse_skill + SkillRegistry.render; (4) các test phase 5 trong tests/ và tests_audit/. Trả file:line + Open questions.` | `plans/reports/<scope>-<YYMMDD-HHMM>-skills-rag-report.md` | Neo file:line cho plan; đóng open question |
| 3 | `hs-think:brainstorm` (tuỳ chọn) — `/hs-think:brainstorm "..." --critique` | `Khi build E08, nên đặt health-gate ở RagService hay ở từng tool wrapper trong feature.py? Cho 2 hướng kèm trade-off, evidence file:line từ service.py:30 và feature.py:72. Chốt 1 hướng.` | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` (+DEC) | Chốt hướng có trade-off khi mơ hồ |
| 4 | `hs:plan` — `/hs:plan hard --tdd` | `Lập plan TDD cho Phase 5 theo plans/260626-1358-clone-hex-agent-roadmap/phase-5-skills-rag.md. 7 bước B1-B7 (spec→registry→ports→service→memory store→qdrant adapter→feature wire). Mỗi AC là 1 lệnh chạy được (vd: pytest tests/test_skills.py -k parse). Bám 5 invariant §5. Red-team mọi [UNVERIFIED].` | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | Plan kiểm chứng, 0 mâu thuẫn |
| 5 | `hs:plan` (approve, HUMAN #1) — AskUserQuestion | (skill tự hỏi Review/Approve/Reject; reviewer≠author) | `plans/<slug>/artifacts/plan-approval.json` | Gate người duyệt; `plan_hash` chưa trôi |
| 6 | `hs:cook` — `/hs:cook <abs-plan-path> --phase B4` | `/clear rồi: /hs:cook /Users/uspro/Desktop/namnson/hex_agent/plans/<slug>/plan.md --phase B4` — cook B4 (RagService health-gate) TDD red→green. KHÔNG xoá/skip test. Lệch plan → STOP hỏi.` | `plans/<slug>/artifacts/verification.json` (+`review-decision.json` per-phase) | Thực thi từng bước, evidence file:line |
| 6b | `hs:cook` — `/hs:cook <abs-plan-path> --phase B6` | `Cook B6 (Qdrant adapter) CHỈ sau khi B1-B5 offline xanh. Dùng FakeClient inject vào __init__ (stores_qdrant.py:43), KHÔNG khởi Qdrant thật. Khoá: health() try/except, lazy collection singleton (:218), upsert reject batch lệch dim trước network.` | `plans/<slug>/artifacts/verification.json` | Prod adapter sau offline; vẫn test không docker |
| 7 | `hs:test` — `/hs:test unit` | `Chạy suite Phase 5: pytest tests/test_skills.py tests/test_rag.py tests_audit/test_rag_edges_rigor.py tests_audit/test_rag_qdrant_adapter_contract.py tests_audit/test_roles_skills_config_integrity.py. 100% pass, KHÔNG khởi Qdrant. Báo verdict + checks[].` | `verification.json` (verdict+checks[]) + QA report | 100% pass = gate; FAIL → hard stage chặn |
| 8 | `hs:code-review` — `/hs:code-review --pending --spec <plan>` | `Review pending changes phase 5 theo spec plan. Kiểm 5 invariant: grep -n qdrant rag/service.py phải rỗng (I-ports); health() không ném; SkillSpec không có role; 3 tool qua execute_tool. Verdict PASS chính xác.` | `plans/<slug>/artifacts/review-decision.json` | Gate review; ≠PASS → STOP |
| 9 | `hs:debug` (khi bug) — `/hs:debug --system` | `health-gate không chặn: gọi ingest khi set_healthy(False) vẫn upsert. Tìm root cause quanh service.py:30,43,86. Viết failing repro test trước.` | `plans/reports/<slug>-debug-report.md` + repro test | Root cause + failing repro |
| 10 | `hs:fix` — `/hs:fix standard` | `Fix bug health-gate vừa debug. RED→GREEN, full suite pass, verdict≠BLOCKED. Regression test viết TRƯỚC fix.` | `verification.json` + báo cáo root cause | RED→GREEN, không làm yếu test |
| 11 | `hs-mem:remember` — `/hs-mem:remember` | `Ghi quyết định: vì sao health-gate đặt ở RagService chứ không ở từng wrapper; vì sao SkillSpec role-agnostic phá vòng E07↔E09.` | `docs/decisions.md` (DEC-N) | Không relitigate quyết định |

Prompt cook nên đi **từng bước B1→B7** (mỗi bước 1 lần `--phase`), không gộp — bám "một epic mỗi đợt" của roadmap. Nhánh skill (B1-B2) và nhánh RAG (B3-B7) không phụ thuộc nhau, cook song song được; nhưng trong nhánh RAG phải **B5 offline xanh trước B6 prod** — đảo thứ tự là vi phạm "offline trước, prod sau".

Curriculum tối thiểu dừng ở review(8). Khép vòng kernel buildLoop: sau review PASS, ship qua `/hs:ship` (HUMAN #2, gated) — tiêu thụ cả ba license `verification.json` + `review-decision.json` + `plan-approval.json` mới push/PR (xem §3 cho từng artifact).

---

## 3. Artifact: đọc & quản lý thế nào

Luật cốt lõi cho mọi artifact dưới đây: **artifact là NGUỒN, không phải lời kể**. Claim không neo file:line hoặc không kèm command chạy được → UNVERIFIABLE → loại. Đọc bằng cách kiểm `detail`/`rationale` có output thật, không tin verdict trống.

**Report (scout/understand/brainstorm)** — `plans/reports/<scope>-<YYMMDD-HHMM>-skills-rag-report.md`.
- *Là gì:* input cho plan/debug. Đọc **Relevant files** trước (phải có file:line như `service.py:30`, `feature.py:113-121`), rồi **Open questions**.
- *Tốt:* mọi finding neo file:line thật; open question về health-gate/Port đã đóng.
- *Dở:* finding không file:line, hoặc `[FALLBACK_INTERNAL]`, hoặc path stale.
- *Hành động khi dở:* mở rộng scout; không plan khi open question load-bearing (vd "health-gate ở đâu") còn mở.

**plan.md** — `plans/<YYMMDD-HHMM>-<slug>/plan.md`.
- *Là gì:* hợp đồng thực thi. Đọc frontmatter `status` (phải `approved`+tên người duyệt mới cook) → bảng Phases → **Acceptance (plan-level)** (mỗi AC là LỆNH chạy được, vd `pytest tests_audit/test_rag_edges_rigor.py`) → Out of scope → Locked decisions.
- *Tốt:* AC chạy được; mọi `[UNVERIFIED]` resolved; 5 invariant §5 có test map.
- *Dở:* 🔴 `status: draft` mà đã cook · AC chung chung ("RAG hoạt động") · claim không file:line.
- *Hành động khi dở:* quay lại bước 4, red-team lại; AC mơ hồ → viết lại thành lệnh.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`.
- *Là gì:* license cook. Shape `{schema:"plan-approval/v1", plan, plan_hash, file_hashes, author, reviewer, verdict:"APPROVED", rationale, ts}`.
- *Tốt:* `verdict:"APPROVED"` + `plan_hash` khớp plan.md hiện tại ⇒ cook được.
- *Dở:* 🔴 `author==reviewer` (`plan_approval.py` ép role) · `plan_hash` lệch = plan-drift.
- *Hành động khi dở:* hash lệch → duyệt lại qua `plan_approval.py` (reviewer≠author), KHÔNG sửa hook.

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`).
- *Là gì:* bằng chứng test. Shape `{stage, plan, actor, ts, checks[]{name,status,detail}, verdict}`. Đọc verdict → từng check `detail` phải có output thật (`pytest → N passed, exit 0`).
- *Tốt:* verdict `PASS` + mọi check `PASS`, detail neo output thật (vd `345 passed, exit 0`, không docker).
- *Dở:* 🔴 bất kỳ check `FAIL` → hard stage chặn · verdict `PASS` mà có check `FAIL` (gian dối) · detail rỗng = UNVERIFIABLE.
- *Hành động khi dở:* check FAIL → STOP, sửa **code không sửa artifact**, chạy lại đến mọi check PASS.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`).
- *Là gì:* ship license. Shape `{verdict, reviewer, role, rationale, ts}`.
- *Tốt:* `verdict=="PASS"` đúng chữ; rationale nêu đã kiểm gì (vd "grep qdrant rag/service.py rỗng, health() có try/except").
- *Dở:* 🔴 `BLOCKED` chặn ship · `PASS_WITH_RISK` ≠ ship license · reviewer trùng author · rationale chỉ "LGTM".
- *Hành động khi dở:* ≠PASS → STOP; PASS_WITH_RISK → AskUserQuestion(fix/accept/cancel); BLOCKED → `hs:fix` → re-review ≤3 vòng.

**DEC-N** — `docs/decisions.md`.
- *Là gì:* sổ quyết định (vd "health-gate ở service", "skill role-agnostic"). Block YAML `id,status,date,actor,ts,affects`.
- *Tốt:* `status:active`; giải trình *hướng loại & vì sao*.
- *Dở:* đảo ngược DEC bằng abstract concern không evidence mới (sticky-decision).

---

## 4. Công hiệu (phải đạt mỗi sang phase kế)

Checklist điều kiện (b) của giao thức cổng. Mỗi mục neo invariant health-gate + ports + I# cụ thể. Tick được = nói thành lời theo *luật → file·hàm → phá ra mất gì* (không phải đọc lại), và chạy được lệnh ở cột chứng cứ. Một mục chưa tick = chưa sang Phase 6.

- [ ] **GIẢI THÍCH** health-gate: vì sao `_require_healthy()` chạy **trước** mọi ingest/search (`service.py:43,85`) và `health()` **không ném** (`stores_qdrant.py:83`). *Phá ra mất gì:* server down thành exception rải rác, agent crash giữa chừng thay vì suy biến gọn. (invariant §5.1)
- [ ] **CHỈ RA trong code** seam Port: `grep -n qdrant rag/service.py` **rỗng**; `RagService.__init__` chỉ giữ `VectorStorePort`/`EmbedderPort` ([phase-5-skills-rag.md:135-140](../phase-5-skills-rag.md)). *Phá ra mất gì:* đổi store phải sửa logic, CI offline chết. (invariant §5.2)
- [ ] **CHỈ RA** 3 tool qua chokepoint: đăng ký vào `kernel.registry` (`feature.py:113-121`), không gọi service tay → middleware/observability bám `execute_tool` (`core/kernel.py:106`). *Phá ra mất gì:* mất observability/safety/envelope cho call đó. (**I1**, invariant §5.3)
- [ ] **GIẢI THÍCH** skill role-agnostic: `SkillSpec` không trường role (`spec.py:26`); `union_tools` chỉ trả union, E09 tự gộp + forbidden-wins. *Phá ra mất gì:* E07 cần E09 và ngược lại — vòng phụ thuộc khoá cả hai epic. (pitfall §6, roadmap pitfall E07↔E09)
- [ ] **CHỈ RA** id ổn định: `_point_id = uuid5(source::chunk_index)` (`stores_qdrant.py:28`) + `delete_by_source` trước upsert (`service.py:71`). *Phá ra mất gì:* re-ingest nhân bản chunk, KB phình. (pitfall §6)
- [ ] **CHẠY** được offline: backend mặc định `memory` (`config/features.yaml:19`); toàn suite phase 5 xanh không `docker compose up`. *Phá ra mất gì:* CI offline đỏ. (invariant §5.5)
- [ ] **CHẠY** `python run_smoke.py` → `CORE_AGENT_SMOKE_OK` + `pytest -q` → 0 fail, vào `verification.json` verdict PASS, mỗi AC §7 → ≥1 test.

Quiz §6 ≥6/8 **và** giải thích được I1 + health-gate + Port theo *luật→file→phá ra mất gì* mới sang Phase 6.

---

## 5. Quy tắc quay lại (rollback bắt buộc)

| Trigger cụ thể | Hành động |
|---|---|
| DoD test ĐỎ (bất kỳ test §7 fail) | `/hs:debug --system` (root cause + failing repro) → `/hs:fix`. KHÔNG xoá/skip/làm yếu test. KHÔNG sang phase kế. |
| `verification.json` có check FAIL | STOP. Sửa **code không sửa artifact**. Chạy lại đến mọi check PASS, detail neo output thật. |
| `grep -n qdrant rag/service.py` **không rỗng** | Quay lại bước 6 (cook B4). Logic đang chạm infra — kéo lại sau Port (`ports.py:24,31`). Đọc lại roadmap §5.2. |
| `health()` ném exception (không try/except) | Quay lại bước 6 (cook B6). Bọc `try/except` → unreachable trả `{"ok": False}` (`stores_qdrant.py:83-90`). Đọc lại §6 pitfall đầu. |
| Không chỉ ra được 3 tool qua `execute_tool` trong `feature.py:113-121` | Quay lại bước 1 (understand). Đọc lại roadmap §5.3 + I1. |
| Re-ingest 1 file → KB phình / chunk cũ còn lẫn | Quay lại bước 6 (cook B6). `_point_id=uuid5` (`stores_qdrant.py:28`) + `delete_by_source` trước upsert (`service.py:71`) — thiếu một trong hai vẫn rò. Đọc §6 pitfall id ổn định. |
| Test cố kết nối Qdrant (suite không offline) | Quay lại bước 6. Dùng `InMemoryVectorStore`+`FakeEmbedder`; adapter test dùng FakeClient (`test_rag_qdrant_adapter_contract.py:63`). Đọc §6 pitfall "Test bắt buộc cần docker". |
| `SkillSpec` lỡ thêm trường role | Quay lại bước 6 (cook B1). Xoá role — skill chỉ khai tool canonical (`spec.py:8-10,26`). Đọc §6 pitfall E07↔E09. |
| review verdict `PASS_WITH_RISK` | KHÔNG ship. AskUserQuestion(fix/accept/cancel). `BLOCKED` → `hs:fix` → re-review ≤3 vòng. |
| `plan_hash` trôi sau approve | Duyệt lại qua `plan_approval.py` (reviewer≠author). KHÔNG sửa hook. |
| Lệch plan khi cook | STOP hỏi user. 3 lần fix / 3+ hypothesis fail → STOP hỏi user. |
| Quiz §6 <70% hoặc không giải thích được I# | KHÔNG sang Phase 6. Đọc lại `phase-5-skills-rag.md` §5+§6, chạy lệnh tự kiểm, quiz lại. |

---

## 6. Câu hỏi kiểm tra hiểu (tự chấm / nhờ Claude chấm)

Mục đậu: **≥6/8 đúng**, và **bắt buộc đúng** câu 1, 2, 4 (invariant cốt lõi: I1 + health-gate + Port/role-agnostic). Sai bất kỳ câu nào trong 1/2/4 → chưa qua, kể cả tổng ≥6.

1. **(I1)** Vì sao 3 tool RAG phải đăng ký vào `kernel.registry` (`feature.py:113-121`) thay vì để caller gọi `RagService.search()` trực tiếp?
   *Điểm phải chấm:* mọi call qua đúng một cửa `execute_tool` (`core/kernel.py:106`) → observability/safety/envelope áp một lần cho tất cả; gọi service tay = mất cả ba. (**I1**)

2. **(health-gate)** `health()` của `QdrantVectorStore` (`stores_qdrant.py:83`) khi server chết phải trả gì, và vì sao **không** được ném exception?
   *Điểm phải chấm:* trả `{"ok": False, ...}` (try/except); gate đọc `h.get("ok")` (`service.py:33`) biến "Qdrant chết" thành nhánh `if` trả envelope `dependency_unavailable` → suy biến dự đoán được, không crash rải rác. (invariant §5.1)

3. **(Port)** `grep -n qdrant rag/service.py` ra kết quả gì là ĐÚNG, và điều đó chứng minh ranh giới nào?
   *Điểm phải chấm:* **rỗng**; `RagService` chỉ thấy `VectorStorePort`/`EmbedderPort` → đổi adapter = đổi 1 dòng `config/features.yaml`, không sửa logic. (invariant §5.2)

4. **(role-agnostic / E07↔E09)** Nếu thêm trường `role` vào `SkillSpec` (`spec.py:26`) thì vòng phụ thuộc nào tái lập, và `union_tools` (`registry.py:79`) đóng vai gì?
   *Điểm phải chấm:* E07 cần E09 và ngược lại → cả hai không build độc lập. `union_tools` là điểm DUY NHẤT E09 tiêu thụ; registry không nhắc role, E09 tự gộp core tool + forbidden-wins. (pitfall §6)

5. **(id ổn định)** Vì sao `_point_id` dùng `uuid5(source::chunk_index)` (`stores_qdrant.py:28`) thay vì `uuid4`, và vì sao **vẫn cần** `delete_by_source` trước upsert (`service.py:71`)?
   *Điểm phải chấm:* uuid5 lo *cập nhật tại chỗ* (cùng index ghi đè, không nhân bản); `delete_by_source` lo *thu nhỏ* (file ngắn lại còn ít chunk hơn). Thiếu một → re-ingest rò chunk cũ. (pitfall §6)

6. **(offline / cardinality)** Vì sao suite phase 5 chạy được không docker, và service refuse gì trước khi chạm store (`service.py:64-69`)?
   *Điểm phải chấm:* backend mặc định `memory` + `FakeEmbedder` (`config/features.yaml:19`); `[rag]` không nằm base, import lazy. Service refuse *cardinality mismatch* (số vector ≠ số chunk) để không nửa-ghi lệch. (invariant §5.5)

7. **(VẬN DỤNG — quan sát)** Bạn thêm tool RAG thứ 4 `rag_stats` bằng cách viết một wrapper trong `feature.py` đăng ký vào `kernel.registry`. Nó **có tự có observability `tool.*`** không? Vì sao? Cần làm thêm gì để có event ngữ nghĩa `rag.stats`?
   *Điểm phải chấm:* CÓ `tool.*` tự động vì mọi call qua chokepoint `execute_tool` phát event ở cửa (**I1**) — không phải viết tay. Muốn event ngữ nghĩa `rag.stats` phải tự phát trong wrapper kèm lineage `request.context.event_fields()` (`feature.py:61-68`), song song `tool.*`. (cho thấy hiểu: chokepoint cho free observability; semantic event là add-on tự nguyện)

8. **(VẬN DỤNG — đổi backend)** Sếp bảo chuyển prod sang Qdrant. Bạn phải sửa bao nhiêu dòng trong `rag/service.py` và `rag/ports.py`? Ba bước thật là gì?
   *Điểm phải chấm:* **0 dòng** ở `service.py`/`ports.py` (và mọi caller giữ nguyên). Ba bước: (1) `pip install -e ".[rag]"`; (2) `docker compose -f docker-compose.rag.yml up -d`; (3) đổi `rag.backend: qdrant` trong `config/features.yaml`. `build_service` (`feature.py:35`) thấy `qdrant` thì lazy-import adapter. Đó là toàn bộ chi phí — vì Port là ranh giới logic/infra. (invariant §5.2, §8 roadmap)

---

## 7. Prompt chấm hiểu cho Claude

Copy-dán:

```
Tôi đang học Phase 5 (Skills & RAG) của roadmap clone hex_agent. Đây là câu trả lời của tôi cho phần invariant health-gate + ports:

[DÁN CÂU TRẢ LỜI CỦA BẠN — vd: "health() phải trả {ok:False} thay vì ném vì... ; RagService không import qdrant vì... ; SkillSpec không có role vì..."]

Dựa trên plans/260626-1358-clone-hex-agent-roadmap/phase-5-skills-rag.md (invariant §5: health-gate trước ingest/search service.py:43,85; logic chỉ chạm infra qua Port; 3 tool qua execute_tool feature.py:113-121; skill role-agnostic spec.py:26) và bảng I1-I17 ở ../README.md:

1. Chấm tôi đã hiểu chưa, theo từng invariant, neo file:line.
2. Chỉ chỗ tôi hổng (đặc biệt: tôi có nhầm health-gate với try/except rải rác không? có hiểu vì sao Port phá vòng E07↔E09 không?).
3. Cho điểm /8 theo §6 và nói rõ tôi có nên cho qua sang Phase 6 không (mục đậu ≥6/8 + bắt buộc đúng câu 1,2,4). Nếu chưa, chỉ chính xác đọc lại mục nào.
```

---

*Điều hướng: ← [Phase 4 build-workflow](phase-4-build-workflow.md) · → [Phase 6 build-workflow](phase-6-build-workflow.md) · Roadmap gốc: [phase-5-skills-rag.md](../phase-5-skills-rag.md) · [README.md](../README.md)*
