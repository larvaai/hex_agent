# 01 — Build Order & Dependencies (control sheet)

> Để triển khai có kiểm soát: epit nào phụ thuộc gì, xây theo thứ tự nào, và Sprint 0 gồm gì.
> Nguồn: mục Dependencies trong từng `E##/PRD.md`.

## Bảng phụ thuộc

| Epic | Phase | Phụ thuộc (phải xong/đủ dùng trước) |
|---|---|---|
| E01 Kernel | P0 | — (nền) |
| E03 LLM Adapter | P0 | — |
| E02 Output Discipline | P0 | E03 |
| E04 Observability | P0 | E01 |
| E06 MCP Tools & Safety | P2 | E01 |
| E05 Single-agent Graph | P1 | E01, E02, E03, E04, E06 |
| E07 Skills | P2 | E06, E09 |
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
| E15 Self-eval & Governance | P4 | E04, E10, E16 |
| E19 Test Harness | cross | tất cả (kiểm chúng) |
| E20 Labs | sau | tiện ích dùng chung |

Lưu ý vòng phụ thuộc mềm: **E07↔E09** (skills khai báo tool ↔ role gắn skill) và cụm **E15/E16/E18** (self-eval ↔ review gate ↔ UI). Giải bằng cách xây *interface trước, nội dung sau*: định nghĩa hợp đồng (schema/seam) rồi mới hoàn thiện từng bên.

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

## Cách dùng control sheet này
1. Mở `E##/acceptance.md` của epic đang làm → biến mỗi AC (Given/When/Then) thành 1 test trong E19.
2. Chỉ bắt đầu epic khi cột "Phụ thuộc" đã đủ.
3. Mỗi epic xong = AC xanh trong harness trước khi sang epic kế.
