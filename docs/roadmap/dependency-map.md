# 01 — Build Order & Dependencies (control sheet)

> Để triển khai có kiểm soát: epit nào phụ thuộc gì, xây theo thứ tự nào, và Sprint 0 gồm gì.
> Nguồn: mục Dependencies trong từng `E##/PRD.md`.
>
> **Cập nhật DEC-4 (2026-06-26):** **E16 + E17 + E18 đã gộp → E21** (Realtime Control Plane). Bảng dưới đã sửa map-drift: **E15 phụ thuộc E21** (không còn E16). Các epic tương lai (E11–E14, E20) là *living note* ở [future/](future/); bảng cổng phụ thuộc của chúng ở cuối file (§"Cổng phụ thuộc — epic tương lai").

## Bảng phụ thuộc

| Epic | Phase | Phụ thuộc (phải xong/đủ dùng trước) |
|---|---|---|
| E01 Kernel | P0 | — (nền) |
| E03 LLM Adapter | P0 | — |
| E02 Output Discipline | P0 | E03 |
| E04 Observability | P0 | E01 |
| E06 MCP Tools & Safety | P2 | E01 |
| E05 Single-agent Graph | P1 | E01, E02, E03, E04, E06 |
| E07 Skills | P2 | E06 |
| E08 RAG | P2 | E06 |
| E09 Roles & Lenses | P3 | E01, E06, E07 |
| E10 Multi-agent Graph | P3 | E05, E09, E02, E06, E04 |
| E11 Departments | P3 | E09, E06, E08 |
| E13 Software Factory | P4 | E09, E10 |
| E12 Router & Supervisor | P4 | E10, E11, E13 |
| E14 Ledger & Memory | P4 | E06, E08 |
| E17 User Live Control | cross | E05/E10, E04 |
| E18 UI / Dashboard | P4 | E04, E16 |
| E16 Human Review Gate | P4 | E17, E18, E13, E15 |
| E15 Self-eval & Governance | P4 | E04, E10, E21 — **đã gộp vào E21** (verdict merge-into-other; không còn epic future độc lập) |
| E19 Test Harness | cross | tất cả (kiểm chúng) |
| E20 Labs | sau | tiện ích dùng chung |
| **E21 Realtime Control Plane** | P4 (cross) | E10, E04, E06, E09 — **gộp E16+E17+E18** (xem `E21_realtime_control_plane/`) |

Lưu ý vòng phụ thuộc mềm: **E07↔E09** — **đã gỡ**: skill là role-agnostic, role mới bind skill + suy allowlist → chiều thật là E07→E09 (xem `CYCLE_E07_E09_skill_role.md`). Còn cụm **E15/E16/E18** (self-eval ↔ review gate ↔ UI) giải bằng *interface trước, nội dung sau*: định nghĩa hợp đồng (schema/seam) rồi mới hoàn thiện từng bên. **Cập nhật:** E16 (review gate) + E17 (live control) + E18 (UI) đã được **hợp nhất thành E21 — Realtime Control Plane**; ba số hiệu cũ giữ làm cross-reference cho từng slice (S-Gate/S-Control/S-UI). Thứ tự nội bộ E21: *contracts → backend chuẩn hoá (điều kiện-trước-UI) → transport → UI → reliability*.

## Thứ tự xây đề xuất (critical path)

```
E01 ─┬─ E03 ── E02 ─┐
     └─ E04         ├─ E05 ── E09 ── E10 ─┬─ E13 ── E12
        E06 ────────┘        ↑            ├─ E11 ──┘
        E07 ──────────────────┘            └─ E14
                                  (P4 cluster: E18→E16→E15, + E17 cross)
                                  E19 chạy song song toàn bộ · E20 sau cùng
```

- **Tầng nền chốt trước**: E01 → E03 → E02 → E04 (P0). E06 có thể làm song song E04.
- **Mở khoá runtime**: E05 cần P0 + E06.
- **Mở khoá multi-agent**: E09 (cần E06+E07) → E10.
- **Mở khoá cognition**: E13/E11/E14 → E12; cụm review/self-eval/UI (E16/E15/E18) xây cùng nhau.
- **E19 (test harness) làm sớm và song song** — viết test cho AC ngay khi mỗi epit hoàn thành.

## Đường găng (critical path)
`E01 → E03 → E02 → E05 → E09 → E10 → E12`. Đây là chuỗi dài nhất; tối ưu lịch theo chuỗi này.

## Sprint 0 (đề xuất) — P0 + đủ để có single-agent

Phạm vi: **E01, E03, E02, E04** (+ khung E06, E05 ở cuối sprint nếu kịp).
Definition of Done Sprint 0:
- Kernel chạy: đăng ký tool → gọi → envelope → event log (AC E01).
- LLM adapter JSON-mode + lazy-init (AC E03).
- Discipline: parse+repair, budget, finish-gate là module dùng chung (AC E02).
- Observability: mỗi run ghi events.jsonl + summary.json + inspect CLI (AC E04).
- E19 tối thiểu: deterministic smoke cho E01–E04 chạy offline, xanh.
→ Kết thúc Sprint 0 là có nền vững + 1 single-agent loop (E05) đọc được task thật.

## Phân bổ sprint (chốt sprint)

| Sprint | Phase | Epics | Cổng vào (deps đủ) | DoD (AC xanh) | ☐ |
|---|---|---|---|---|---|
| **S0** | P0 | E01, E03, E02, E04 | — | kernel + adapter (JSON-mode) + discipline + observability; smoke offline xanh | ☐ |
| **S1** | P1+P2 | E06, E05 | S0 | tool một-cửa + sandbox; single-agent loop chạy task thật | ☐ |
| **S2** | P2+P3 | E07, E08, E09 | S0, S1 | skills contract; RAG health/ingest/search; roles enforce allowlist | ☐ |
| **S3** | P3 | E10, E11 | S2 | company pipeline + departments chạy LLM thật, separation-of-duties | ☐ |
| **S4** | P4 | E13, E12, E14 | S3 | factory spec→handoff; router đa nhiệm; ledger | ☐ |
| **S5** | P4 | E18, E16, E15, E17 | S4 | UI; review gate; self-eval governance; user live control | ☐ |
| **xuyên suốt** | — | E19 | theo từng epic | mỗi AC epic → ≥1 test trong harness | ☐ |
| **sau** | — | E20 | nền vững | labs chạy mock offline | ☐ |

Quy tắc chốt: chỉ mở một sprint khi **Cổng vào** đã đạt; đóng sprint khi **DoD (AC xanh)** đủ trong E19.

## Cổng phụ thuộc — epic tương lai (living note ở `future/`)

> Nguồn: report `roadmap-living-notes` §TL;DR. Nguyên tắc: `deps 🟢` = *được phép* làm, KHÔNG phải *nên* làm.

| Epic | Verdict | Cổng vào | Cổng ra | Ngưỡng rã đông (rút gọn) |
|---|---|---|---|---|
| E11 Departments | park-with-trigger | 🟢 E09/E06/E08 done | 🔴 chờ E12 | dept distinct ≥4 (nay 2) HOẶC role ≥8 (nay 4) HOẶC E12 thiết kế |
| E13 Software Factory | park-with-trigger | 🟢 E09/E10 done | 🔴 chờ E12 | owns_validation:false ≥3 (nay 1) HOẶC E12 khởi động |
| E14 Ledger & Memory | park-with-trigger | 🟢 E06/E08 done | 🔴 chờ E12 | run >500 (nay 0) HOẶC resume-call-site >0 (nay 0) HOẶC E12 cần lịch sử |
| E12 Router & Supervisor | park-with-trigger | 🔴 chờ E11+E13 | — | E11 có ≥2 template + ≥3 loại task + ≥1 request "mixed" |
| E15 Self-eval | **merge-into-other** | 🟡 vào E21 | — | siết `judge_acceptance` trong E21 S21.33 (không thành epic riêng) |
| E20 Labs | park-with-trigger | ⚪ cổng-thời-điểm | — | ≥3 utility feature trùng lặp HOẶC cần profile labs-vs-prod |

Chi tiết từng epic + ngưỡng đo-được: [future/](future/). Giao thức rã đông một món: [README.md](README.md).

## Cách dùng control sheet này
1. Mở `E##/acceptance.md` của epic đang làm → biến mỗi AC (Given/When/Then) thành 1 test trong E19.
2. Chỉ bắt đầu epic khi cột "Phụ thuộc" đã đủ.
3. Mỗi epic xong = AC xanh trong harness trước khi sang epic kế.
