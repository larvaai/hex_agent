# `docs/` — bản đồ của bản đồ

Tài liệu `hex_agent` xếp theo **Diátaxis-hybrid**: 4 trục (bắt đầu / how-to / tra cứu / vì-sao) + hợp đồng epic (`spec/`) + tương lai (`roadmap/`). Mỗi mục một dòng, bấm vào đi thẳng.

| Trục | Ở đâu | Dùng khi |
|---|---|---|
| **Bắt đầu** (tutorial) | [getting-started.md](getting-started.md) | Lần đầu mở repo: 5 lớp dẫn đường + thứ tự đọc + smoke check. |
| **How-to** (guides) | [guides/](guides/) — [regenerate-map.md](guides/regenerate-map.md) · [add-a-feature.md](guides/add-a-feature.md) · [run-console-ui.md](guides/run-console-ui.md) | Làm một việc cụ thể từng bước. |
| **Tra cứu** (reference) | [reference/](reference/) — [codebase-summary.md](reference/codebase-summary.md) · [runtime-flow.md](reference/runtime-flow.md) · [known-risks.md](reference/known-risks.md) · [mcp-tools.md](reference/mcp-tools.md) · [langgraph.md](reference/langgraph.md) · [GLOSSARY.md](GLOSSARY.md) | Tra "cái gì là gì / chạy thế nào". |
| **Chuẩn (contract)** | [system-architecture.md](system-architecture.md) · [code-standards.md](code-standards.md) | Hợp đồng kiến trúc + kỷ luật code (giữ ở gốc `docs/`, là standards contract). |
| **Vì sao** (explanation) | [explanation/](explanation/) — [overview-pdr.md](explanation/overview-pdr.md) · [design-decisions.md](explanation/design-decisions.md) · [modules/](explanation/modules/) (kernel, graph-state, graph-runtime, safety-sandbox) · sổ quyết định [decisions.md](decisions.md) | Hiểu *tại sao* một thiết kế ra như vậy. |
| **Hợp đồng epic** (spec) | [spec/done/](spec/done/) (E08-rag, E10-multi-agent-graph) · [spec/active/](spec/active/) (E21-realtime-control-plane) | PRD/stories/acceptance của từng epic đã/đang làm. |
| **Roadmap** (tương lai) | [roadmap/README.md](roadmap/README.md) (vòng đời + Thaw Protocol) · [project-roadmap.md](roadmap/project-roadmap.md) · [dependency-map.md](roadmap/dependency-map.md) · [future/](roadmap/future/) (5 living note) · [THRESHOLDS.md](roadmap/THRESHOLDS.md) | Epic chưa đấu nối + điều kiện rã đông đo-được. |
| **Lịch sử** (archive) | [archive/class-encyclopedia.md](archive/class-encyclopedia.md) | Snapshot cũ — KHÔNG phải sự thật hiện tại. |

> `MAP.md` (1 dòng/module, auto-gen) giữ ở **root repo** (`../MAP.md`), regenerate bằng [guides/regenerate-map.md](guides/regenerate-map.md).

## Thứ tự đọc cho người mới
1. [reference/codebase-summary.md](reference/codebase-summary.md) — cái gì là gì + cách chạy.
2. [getting-started.md](getting-started.md) — 5 lớp dẫn đường (MAP, CHANGELOG, epic doc, test, git log).
3. [reference/runtime-flow.md](reference/runtime-flow.md) — một task chạy từ input → output.
4. [reference/known-risks.md](reference/known-risks.md) — file nào dễ vỡ + invariant cần giữ.
5. `../plans/reports/architecture-map-260625-2009-hex-agent-report.md` — file key + responsibility chi tiết.
6. Mở epic đang quan tâm ở [spec/](spec/) (E08 → E21); roadmap tương lai ở [roadmap/](roadmap/).
7. Đọc test tương ứng (`tests/`) + module code.

## Quy ước bố cục (giữ khi thêm doc)
- Mọi `.md` nằm trong `docs/` (trừ `README.md` + `CHANGELOG.md` ở root repo) — md-location invariant.
- Lớp per-module KHÔNG nhúng full source: code là sự thật, `MAP.md` cho tóm tắt, `explanation/modules/` chỉ giữ vai trò/invariant cho 4 module lõi.
- `system-architecture.md` + `code-standards.md` ở gốc `docs/` (standards contract, không move).
