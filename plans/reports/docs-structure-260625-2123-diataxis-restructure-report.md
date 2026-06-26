---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Cấu trúc lại `docs/` — Diátaxis-hybrid + tách spec / thực thi / roadmap

Brainstorm report · 2026-06-25 21:23 · DEC-1 (`docs/decisions.md`)
Nguồn scout: `docs/` (60 file), `MAP.md`, `plans/`, `harness/` convention, `git log`.

---

## 1. Quyết định đã chốt

| Trục | Chốt |
|---|---|
| Phạm vi brainstorm | Cấu trúc mục tiêu **+ checklist di chuyển**, không động file (vai cố vấn) |
| Lớp per-module (`docs/core/*.md`…) | **Bỏ** lớp mirror-source; dựa `MAP.md` auto-gen + giữ explainer chỉ cho module lõi |
| Bố cục hiện tại/tương lai | `docs/` = spec · `plans/` = thực thi · `docs/roadmap/` = tương lai (giữ ý tưởng) |
| Chuẩn IA | **Diátaxis** (tutorial / how-to / reference / explanation) hybrid epic-spec |
| Điều kiện trước plan | **dependency map rõ ràng** là cổng vào `/hs:plan` |

---

## 2. Chẩn đoán hiện trạng (vì sao cần đổi)

`docs/` đang trộn 5 loại tài liệu trong cùng một mặt phẳng, không có taxonomy:

1. **Điều hướng** — `HOW_TO_FOLLOW.md`, `codebase-summary.md`, `RUNTIME_FLOW.md`, `KNOWN_RISKS.md`
2. **Tham chiếu ổn định** — `system-architecture.md`, `project-overview-pdr.md`, `project-roadmap.md`, `code-standards.md` (mới, dated 2026-06-25, chất lượng tốt)
3. **Explainer per-module** — `core/*.md`, `discipline/*.md`, `graph/*.md`, `llm/*.md`, `toolbox/*.md`, `safety/*.md`, `observability/*.md`, `tests/*.md`, `features/*.md`, `config/*.md` (mirror 1:1 cây source)
4. **Spec theo epic** — `rebuild_from_zero/Exx/` (PRD/stories/acceptance)
5. **Snapshot lịch sử / trùng lặp**

Ba vấn đề đo được:

- **Trùng lặp byte-identical**: `docs/MCP_TOOLS.md` ≡ `docs/architecture/MCP_TOOLS.md` (764 dòng, `diff` = identical). `CLASS_ENCYCLOPEDIA.md` (348) vs `ChatGPTCodex/class_encyclopedia.md` (846) — hai bản, cả hai tự nhận snapshot cũ.
- **Lớp per-module rot ngay**: `docs/core/kernel.md` nhúng `## Toàn bộ nội dung file` + nguyên source Python. Code đổi 1 dòng → doc sai; không ai regen tay. ~30+ file kiểu này.
- **Hiện tại vs tương lai trộn lẫn**: E21 (active, phần lớn pending) và E11–E15/E20 (chưa bắt đầu) nằm chung `rebuild_from_zero/` với spec đã-done; không phân trạng thái → khó biết "làm gì tiếp".

---

## 3. Cấu trúc mục tiêu (Diátaxis-hybrid)

```
docs/
├── README.md                       # ★ NEW — index/bản đồ của bản đồ; điểm vào duy nhất
│
├── getting-started.md              # TUTORIAL  ← gộp HOW_TO_FOLLOW + run_smoke (đọc-gì-trước + chạy-thử)
│
├── guides/                         # HOW-TO (task-oriented)
│   ├── regenerate-map.md           #   ← tools/gen_map.md (phần how-to)
│   ├── add-a-feature.md            # ★ NEW — convention plugin loader (features.yaml → install)
│   └── run-console-ui.md           # ★ NEW — python -m ui.server (127.0.0.1:8765)
│
├── reference/                      # REFERENCE (ổn định, tra cứu)
│   ├── architecture.md             #   ← system-architecture.md
│   ├── runtime-flow.md             #   ← RUNTIME_FLOW.md
│   ├── known-risks.md              #   ← KNOWN_RISKS.md (invariant + module dễ vỡ)
│   ├── code-standards.md           #   ← code-standards.md
│   ├── codebase-summary.md         #   ← codebase-summary.md
│   ├── mcp-tools.md                #   ← MCP_TOOLS.md (giữ 1 bản)
│   ├── langgraph.md                #   ← architecture/LANGGRAPH.md
│   └── map.md                      #   ← MAP.md (auto-gen, 1 dòng/module; hoặc giữ ở root + symlink)
│
├── explanation/                    # EXPLANATION (vì sao / thiết kế)
│   ├── overview-pdr.md             #   ← project-overview-pdr.md
│   ├── design-decisions.md         #   ← CYCLE_E07_E09_skill_role.md (+ trỏ docs/decisions.md / DEC-*)
│   └── modules/                    #   explainer SÂU chỉ cho module lõi (KHÔNG mirror source, KHÔNG nhúng code)
│       ├── kernel.md               #     ← core/kernel.md (cắt block full-code)
│       ├── graph-state.md          #     ← graph/state.md
│       ├── graph-runtime.md        #     ← graph/runtime.md
│       └── safety-sandbox.md       #     ← safety/sandbox.md
│
├── spec/                           # SPEC theo epic (hợp đồng: PRD/stories/acceptance)
│   ├── done/                       #   epic đã ship — spec đóng băng
│   │   ├── E08-rag/                #     ← rebuild_from_zero/E08_rag/
│   │   └── E10-multi-agent-graph/  #     ← rebuild_from_zero/E10_multi_agent_graph/
│   └── active/                     #   epic ĐANG triển khai
│       └── E21-realtime-control-plane/   # ← rebuild_from_zero/E21_realtime_control_plane/
│
├── roadmap/                        # ROADMAP (hiện tại + TƯƠNG LAI, giữ ý tưởng)
│   ├── project-roadmap.md          #   ← project-roadmap.md (bảng trạng thái epic)
│   ├── dependency-map.md           #   ★ ← 01_BUILD_ORDER_AND_DEPENDENCIES.md (CỔNG VÀO /hs:plan)
│   └── future/                     #   epic chưa bắt đầu — ý tưởng + phụ thuộc
│       ├── E11-departments.md      # ★ NEW stub
│       ├── E12-router-supervisor.md#   ← rebuild_from_zero/E12_intent_router_supervisor/PRD.md
│       ├── E13-software-factory.md # ★ NEW stub
│       ├── E14-ledger-memory.md    # ★ NEW stub
│       ├── E15-self-eval.md        # ★ NEW stub
│       └── E20-labs.md             # ★ NEW stub
│
└── archive/                        # snapshot lịch sử (rào rõ, không phải sự thật hiện tại)
    └── class-encyclopedia.md       #   ← CLASS_ENCYCLOPEDIA.md (đánh dấu historical)
```

**Vì sao map này khớp Diátaxis + ý người dùng:**
- 4 trục Diátaxis (`getting-started` / `guides/` / `reference/` / `explanation/`) cho người đọc 4 nhu cầu khác nhau, không trộn.
- `spec/` (hợp đồng epic) tách khỏi `explanation/` (vì-sao) — spec đóng băng theo trạng thái `done/active`.
- `roadmap/` gom toàn bộ forward-looking; `dependency-map.md` là cổng vào trước khi `/hs:plan`.
- `plans/` (harness) = nơi `/hs:plan` đẻ ra `plans/{date}-{slug}/` khi một epic/phase được nhặt lên thực thi → đúng convention "docs=spec, plans=thực thi".

---

## 4. Dependency map (cổng vào trước khi plan)

### 4a. Hiện tại — E21 Realtime Control Plane (các pha nội bộ)

```
A (S-CONTRACT) ✓ ── B1 (EventEmitter) ✓ ── B2–B14 (control-store + queue + intervention) ⬜
                                                  │
                                                  ├── S-CONTROL (live command lifecycle) ⬜
                                                  │        │
                                   S-TRANSPORT (HTTP+SSE) ⬜┤
                                                  │        │
                                            S-UI (Control Tower) ⬜
                                                           │
                                            S-RELIABILITY (crash recovery) ⬜
```

Thứ tự gợi ý (roadmap §"Theo thứ tự gợi ý"): **B2–B14 → S-CONTROL → S-TRANSPORT → S-UI → S-RELIABILITY**.
Cổng pre-UI (6 điều kiện, roadmap §"Điều kiện trước khi bắt tay UI") phải xanh trước S-TRANSPORT + S-UI: control-store SQLite, command queue + idempotency, approval-checkpoint ở `supervisor/_drive`, `pending_human_commands` vào `_state_view`, redaction boundary test (0 secret lọt `ui_payload`), audit trail có actor.

### 4b. Tương lai — E11–E15, E20 (nguồn: `01_BUILD_ORDER_AND_DEPENDENCIES.md`)

| Epic | Phụ thuộc | Trạng thái cổng | Ghi chú |
|---|---|---|---|
| **E11** Departments | E09, E06, E08 → **đều done** | 🟢 **Sẵn sàng plan** | Hiện chỉ có string field ở RoleSpec |
| **E13** Software Factory | E09, E10 → **đều done** | 🟢 **Sẵn sàng plan** | Spec → handoff |
| **E14** Ledger & Memory | E06, E08 → **đều done** | 🟢 **Sẵn sàng plan** | Durable work + state ledger |
| **E12** Router/Supervisor | E10 ✓, **E11 ⬜, E13 ⬜** | 🔴 Chặn bởi E11 + E13 | `supervisor/` hiện tại là E10, KHÔNG phải E12 |
| **E15** Self-eval & Governance | E04 ✓, E10 ✓, **E16→E21 ⬜** | 🟡 Chặn một phần bởi E21 | Gộp với E21 thay E16 |
| **E20** Labs | sau nền vững | ⚪ Cuối cùng | Tiện ích dùng chung |

**Đọc map này:** 3 epic tương lai **không bị chặn** (E11, E13, E14) — chọn 1 để `/hs:plan` ngay. E12 phải chờ E11+E13. E15 chờ E21. Đây là dependency map mà người dùng yêu cầu làm rõ trước khi plan.

---

## 5. Checklist di chuyển (move / merge / delete / strip)

### MERGE → 1 file
- `HOW_TO_FOLLOW.md` + `run_smoke.md` → `docs/getting-started.md`

### MOVE + RENAME (giữ nội dung)
- `system-architecture.md` → `reference/architecture.md`
- `RUNTIME_FLOW.md` → `reference/runtime-flow.md`
- `KNOWN_RISKS.md` → `reference/known-risks.md`
- `code-standards.md` → `reference/code-standards.md`
- `codebase-summary.md` → `reference/codebase-summary.md`
- `MCP_TOOLS.md` → `reference/mcp-tools.md`
- `architecture/LANGGRAPH.md` → `reference/langgraph.md`
- `project-overview-pdr.md` → `explanation/overview-pdr.md`
- `CYCLE_E07_E09_skill_role.md` → `explanation/design-decisions.md`
- `tools/gen_map.md` → `guides/regenerate-map.md`
- `project-roadmap.md` → `roadmap/project-roadmap.md`
- `rebuild_from_zero/01_BUILD_ORDER_AND_DEPENDENCIES.md` → `roadmap/dependency-map.md`
- `rebuild_from_zero/E08_rag/` → `spec/done/E08-rag/`
- `rebuild_from_zero/E10_multi_agent_graph/` → `spec/done/E10-multi-agent-graph/`
- `rebuild_from_zero/E21_realtime_control_plane/` → `spec/active/E21-realtime-control-plane/`
- `rebuild_from_zero/E12_intent_router_supervisor/PRD.md` → `roadmap/future/E12-router-supervisor.md`
- `CLASS_ENCYCLOPEDIA.md` → `archive/class-encyclopedia.md` (header: "SNAPSHOT LỊCH SỬ")

### STRIP rồi MOVE (cắt block `## Toàn bộ nội dung file`)
- `core/kernel.md` → `explanation/modules/kernel.md`
- `graph/state.md` → `explanation/modules/graph-state.md`
- `graph/runtime.md` → `explanation/modules/graph-runtime.md`
- `safety/sandbox.md` → `explanation/modules/safety-sandbox.md`

### DELETE
- `architecture/MCP_TOOLS.md` — trùng byte-identical với bản giữ
- `ChatGPTCodex/class_encyclopedia.md` — bản dup của encyclopedia (đã archive bản kia)
- **Toàn bộ lớp per-module còn lại** (mirror source, nhúng full code): `core/{__init__,bootstrap,events,ports,registry,schemas,state}.md`, `discipline/*.md`, `graph/nodes.md`, `llm/*.md`, `observability/*.md`, `safety/policy.md`, `tests/*.md`, `toolbox/*.md`, `features/*.md`, `config/features.md` → thay bằng `MAP.md` auto-gen (`python tools/gen_map.py`)

### NEW (viết mới, ngắn)
- `docs/README.md` (index) · `guides/add-a-feature.md` · `guides/run-console-ui.md`
- `roadmap/future/{E11,E13,E14,E15,E20}-*.md` (stub: mục đích + phụ thuộc + "chưa bắt đầu")

### Tài sản đặc biệt
- `class_dependency.mermaid`, `rebuild_from_zero/E10*/flow_taskloop.mermaid` → `reference/assets/` (cạnh doc tham chiếu chúng)

**Quy mô**: ~12 MOVE, 1 MERGE, 4 STRIP, ~30+ DELETE, ~8 NEW. Phần lớn công sức là DELETE (rủi ro thấp — nội dung tái sinh từ `MAP.md` + code).

---

## 6. Phương án thay thế đã cân nhắc (trade-off)

| Phương án | Ưu | Nhược | Verdict |
|---|---|---|---|
| **A. Diátaxis-hybrid (chọn)** | Chuẩn ngành, 4 nhu cầu tách bạch, dễ điều hướng khi repo lớn | 8 vùng top-level — cần `README.md` index để khỏi lạc | ✅ Adopt |
| B. Diátaxis "gọn" (gộp tutorial+guides) | Ít thư mục hơn | Trộn learning-oriented với task-oriented — đúng cái Diátaxis muốn tách | Dự phòng nếu thấy A quá nhiều folder |
| C. Giữ 5-lớp hiện tại, chỉ dọn dup | Ít thay đổi nhất | Không giải quyết per-module rot + không tách hiện tại/tương lai | ❌ Không đạt yêu cầu |

Rủi ro chính của A: tách quá mịn cho repo ~60 doc. Giảm thiểu bằng `docs/README.md` làm điểm vào + giữ mỗi vùng tối thiểu 2 file thực chất (vùng 1 file thì gộp lên cha).

---

## 7. Rủi ro & câu hỏi mở

- **Link nội bộ vỡ**: nhiều doc trỏ chéo nhau bằng đường dẫn tương đối (vd `codebase-summary.md` trỏ `./HOW_TO_FOLLOW.md`, `./rebuild_from_zero/`). MOVE phải sửa đồng loạt — gom vào bước thực thi, không làm tay rời rạc.
- **`MAP.md` ở root hay `docs/reference/`?**: đang ở root + auto-gen bởi `tools/gen_map.py` (đọc docstring). Nếu chuyển vào `docs/` phải sửa đường ghi của `gen_map.py` (đụng code tooling — ngoài phạm vi brainstorm). Khuyến nghị: **giữ `MAP.md` ở root**, `reference/` chỉ trỏ tới.
- **Root snapshot lệch** (`README.md`, `CHANGELOG.md` dừng ở E08, `project_context.txt`): ngoài `docs/` nên không nằm trong checklist này, nhưng nên đồng bộ trong cùng đợt — cần xác nhận có muốn gom không.
- **E16/E17/E18 cũ**: đã gộp vào E21; build-order vẫn liệt kê riêng. Khi viết `dependency-map.md` cần ghi rõ "E16+E17+E18 → E21" để khỏi hiểu nhầm còn 3 epic.

---

## 8. Bước kế

1. **`/hs:plan`** biến report này thành phase thực thi reorg (move/merge/delete + sửa link + dựng stub), gate bằng `python run_smoke.py` + kiểm CI invariant (md chỉ trong `plans/` + `docs/`).
2. Hoặc trước đó: viết `roadmap/dependency-map.md` + chọn 1 trong 3 epic 🟢 (E11/E13/E14) làm mục tiêu plan kế tiếp.

---

*Câu hỏi mở chờ người dùng:* (a) có gom đồng bộ root snapshot (`README`/`CHANGELOG`/`project_context.txt`) trong cùng đợt không; (b) `MAP.md` giữ root hay chuyển `docs/reference/`.
