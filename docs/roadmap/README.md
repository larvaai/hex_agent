# Roadmap — kho lạnh có nhãn-ngưỡng (living notes)

> Nguồn: report `roadmap-living-notes` §"Dàn ý README" + §"Thaw Protocol". Đây là **chỉ mục sống** cho `future/`.

## 1. Roadmap là gì
KHÔNG phải backlog "sẽ làm hết". Là tập **living note** có điều kiện rã đông đo-được. Triết lý xuyên suốt:

> **`deps 🟢` = *được phép* làm, KHÔNG phải *nên* làm.**

Một field ghi-mà-không-đọc (vd `.department`, read-sites = 0) là tín hiệu YAGNI, không phải tín hiệu sẵn sàng.

## 2. Nguồn sự thật
- [project-roadmap.md](project-roadmap.md) — trạng thái epic E01–E21 (đã/đang/chưa).
- [dependency-map.md](dependency-map.md) — bảng phụ thuộc + cổng (nguồn **cấu trúc**).
- [THRESHOLDS.md](THRESHOLDS.md) — sổ đo ngưỡng theo ngày.
- `plans/reports/architecture-map-260625-2009-hex-agent-report.md` — file key + responsibility.

Note ↔ bảng lệch → **bảng là nguồn cấu trúc, note là nguồn ý-định**; sửa bảng trước rồi tiếp.

## 3. Cách đọc 1 note
Đọc theo thứ tự: `verdict` → `wiring_threshold` → `dependencies` → `wiring_sketch`. `current_anchors` lệch (file/line đổi) = note cần refresh. Mỗi note ở [future/](future/) có đủ **8 trường**: problem_solved · why_not_now · current_anchors (file:line) · wiring_threshold (đo được) · wiring_sketch (seam) · dependencies (cổng) · critique (YAGNI) · verdict.

## 4. Vòng đời
```
future ─(ngưỡng chạm)─▶ triggered ─(deps re-eval OK + plan duyệt)─▶ planned ─(/hs:cook)─▶ active ─(AC xanh E19)─▶ done
```
+ nhánh **`merge-into-other`** (E15 → vào E21, KHÔNG qua planned/active độc lập);
+ nhánh **`block-on:<epic>`** (triggered nhưng deps thiếu → về `future`).

## 5. Thaw Protocol — giao thức "rã đông" một món roadmap
Biến một `wiring_threshold` bị chạm thành plan thực thi, KHÔNG bỏ bước đánh-giá-lại-phụ-thuộc.

- **Bước 0 — Phát hiện ngưỡng (Detect)**: đo định kỳ (mở sprint / thêm role/feature) bằng các lệnh đếm trong [THRESHOLDS.md](THRESHOLDS.md). Ghi vào sổ kèm ngày đo. Ngưỡng "chạm" khi METRIC vượt, không cảm tính.
- **Bước 1 — Xác nhận trigger**: `future → triggered` khi ≥1 điều kiện `wiring_threshold` xác nhận bằng số đo + evidence. Verdict `merge-into-other` (E15): mở backlog-item trong epic chủ, không thành epic riêng. Trigger "consumer khởi động" = consumer thật đã in-progress (PR/branch), không phải dự định.
- **Bước 2 — Đánh giá lại phụ thuộc (BẮT BUỘC)**: mở `dependencies` + đối chiếu [dependency-map.md](dependency-map.md). Kiểm: (1) gate-in mọi dep còn Done? (2) vòng chờ chéo? (E11↔E12) → "mồi phá vòng": rã đông MỨC TỐI THIỂU đủ cho consumer thiết kế. (3) map drift? → sửa bảng trước. Output: `{proceed-full | proceed-minimal | block-on:<epic>}`.
- **Bước 3 — Chọn altitude (YAGNI)**: đọc `critique`, chọn bản RẺ NHẤT — E11→registry+validate · E12→GlobalSupervisor rule-based · E13→cờ pin_route ~50 dòng · E14→B1 SQLite global · E15→siết judge_acceptance trong E21.
- **Bước 4 — Plan**: `/hs:plan` với input = `wiring_sketch` (seam file:line). Plan PHẢI dùng seam sẵn (không subsystem song song) · gắn AC vào E19 · khai báo ranh giới epic lân cận. `triggered → planned` khi duyệt.
- **Bước 5 — Cook → Done**: `/hs:cook`; `planned → active`. AC xanh E19 → `active → done`; cập nhật roadmap 🔴→🟢, bảng phụ thuộc, gỡ trigger phụ. **Hậu-kiểm**: chạy lại Bước 0 cho note downstream (rã đông E11 thường chạm trigger "consumer khởi động" của E12).

## 6. Trạng thái hiện tại
Hôm nay (2026-06-26) **cả 5 note ở `future`**; E15 đã `merge-into-other` (vào E21, không có note riêng).

| Epic | Verdict | Trạng thái vòng đời | Trigger gần nhất | Block-on | Ngày đo cuối |
|---|---|---|---|---|---|
| [E11 Departments](future/E11-departments.md) | park-with-trigger | future | — | E12 thiết kế | 2026-06-26 |
| [E12 Router/Supervisor](future/E12-router-supervisor.md) | park-with-trigger | future | — | E11 + E13 | 2026-06-26 |
| [E13 Software Factory](future/E13-software-factory.md) | park-with-trigger | future | — | E12 | 2026-06-26 |
| [E14 Ledger & Memory](future/E14-ledger-memory.md) | park-with-trigger | future | — | E12 | 2026-06-26 |
| [E20 Labs](future/E20-labs.md) | park-with-trigger | future | — | cổng-thời-điểm (S5) | 2026-06-26 |
| E15 Self-eval | **merge-into-other** | → E21 (S21.33) | — | — | 2026-06-26 |

## 7. Bảo trì (anti-rot)
- Chạy Thaw Bước 0 ([THRESHOLDS.md](THRESHOLDS.md)) định kỳ + mỗi khi `roles/library/` đổi.
- Refresh `current_anchors` khi seam đổi (file/line trôi).
- Mâu thuẫn map ↔ note → sửa bảng + ghi vào [../decisions.md](../decisions.md).
