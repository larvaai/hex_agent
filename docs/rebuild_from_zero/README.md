# rebuild_from_zero — PRD / Story / Acceptance cho repo agent mới

Bản nháp spec để xây lại `my_agents` sạch & dễ kiểm soát. Đọc kèm:
- `00_FEATURE_CATALOG_AND_EPICS.md` — 28 tính năng hay + backlog epic.
- `NEW_REPO_BUILD_GUIDE.md` — kiến trúc khuyến nghị + lộ trình 5 phase.
- `flow_J_epic_dependencies.mermaid` — sơ đồ phụ thuộc epic.

Mỗi epic = 1 thư mục `E##_<name>/` với 3 file: `PRD.md`, `stories.md`, `acceptance.md` (AC dạng Given/When/Then để map sang test ở E19).

## Thứ tự triển khai (theo phase)

| Phase | Epic |
|---|---|
| **P0 — Nền** | E01 Kernel · E02 Output Discipline · E03 LLM Adapter · E04 Observability |
| **P1 — Single-agent** | E05 Single-agent Graph |
| **P2 — Tools/Skills/RAG** | E06 MCP & Safety · E07 Skills · E08 RAG |
| **P3 — Multi-agent** | E09 Roles & Lenses · E10 Multi-agent Graph · E11 Departments |
| **P4 — Cognition** | E12 Router & Supervisor · E13 Software Factory · E14 Ledger · E15 Self-eval & Governance · E16 Human Review Gate · E18 UI/Dashboard |
| **Cross-cutting** | E17 User Live Control · E19 Test Harness |
| **Sau** | E20 Labs |

## Nguyên tắc xuyên suốt (từ bài học repo cũ)
- Một substrate graph duy nhất (single = 1 node); discipline dùng chung (không nhân đôi).
- Structured output (JSON-mode) ở LLM layer ngay từ đầu.
- An toàn = một chokepoint; observability từ commit đầu.
- py3.11+, UTF-8 no-BOM, `.gitignore var/`, không commit secret, lazy-init client.
- Tự sửa mình = proposal-only + human gate.

## Trạng thái
Tất cả 20 epic đã có **PRD nháp + stories + acceptance**. Bước kế: chọn epic để tinh chỉnh sâu (mình đề xuất bắt đầu **E01 → E04**), rồi map acceptance → test (E19) trước khi code.
