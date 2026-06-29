---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Schema 8→9 (prior_art external anchor)

> Áp DEC-7. Sửa 3 file: `docs/roadmap/README.md`, `docs/roadmap/THRESHOLDS.md`, `docs/GLOSSARY.md`.
> Nguồn: [report §2](../reports/brainstorm-260626-0159-prior-art-schema-committee-agent-report.md).

## Step 1.1 — README.md §3 "Cách đọc 1 note"

Hiện (`docs/roadmap/README.md:21`) liệt kê **8 trường**:
`problem_solved · why_not_now · current_anchors (file:line) · wiring_threshold · wiring_sketch · dependencies · critique · verdict`.

Sửa thành **9 trường**, chèn `prior_art` NGAY SAU `current_anchors`:
`problem_solved · why_not_now · current_anchors (file:line) · **prior_art (external anchor)** · wiring_threshold · wiring_sketch · dependencies · critique · verdict`.

> Lưu ý đánh số: trong file note dùng nhãn **3b** cho `prior_art` (giữ `current_anchors`=3, `wiring_threshold`=4...) để KHÔNG phá thứ tự đọc `verdict → wiring_threshold → dependencies → wiring_sketch` đã ghi ở §3.

Thêm khối mô tả `prior_art` (đặt ngay dưới câu liệt kê 9 trường):

```
**prior_art** = "external anchor" — bằng chứng feature đã chạy ngoài đời (không phải code mình).
Cùng loài với `current_anchors` (neo nội); đây là neo NGOẠI. Khuôn mỗi dòng:
  `<tên> — <URL> — mechanism:"<NGUYÊN-LÝ đã chạy, KHÔNG phải tên-UI>" — checked:<date>`
3 luật cứng:
- proof-of-FEASIBILITY ≠ proof-of-NEED: "ngoài kia có" KHÔNG làm bài toán cấp thiết hơn (Rust RFC 2333).
- prior-art KHÔNG bao giờ là thaw-trigger (trigger chỉ là metric NỘI BỘ ở `wiring_threshold`).
- `critique` BẮT BUỘC có dòng `proven-elsewhere != needed-here: <vì sao>`.
```

## Step 1.2 — README.md §7 "Bảo trì (anti-rot)"

Thêm 1 gạch đầu dòng vào §7 (`README.md:53-55`):

```
- Refresh `prior_art.checked:<date>` đi CÙNG nhịp refresh `current_anchors` (cả hai là anchor). URL chết → dùng `mechanism` (nguyên-lý) tìm nguồn tương đương, KHÔNG xoá entry.
```

## Step 1.3 — THRESHOLDS.md ghi chú

Thêm 1 đoạn ngắn vào cuối phần đầu của `docs/roadmap/THRESHOLDS.md` (sau block "Lệch đếm", trước "Đo: ..."):

```
> **prior_art KHÔNG có ở đây.** Nó là external anchor (proof-of-feasibility), refresh theo `checked:<date>` cùng nhịp `current_anchors` — KHÔNG phải metric trigger. Đừng thêm lệnh-đếm cho prior-art vào sổ ngưỡng này.
```

## Step 1.4 — GLOSSARY.md +1 hàng

Thêm hàng vào bảng (`docs/GLOSSARY.md`):

```
| external anchor | Bằng chứng một feature đã chạy NGOÀI đời (phần mềm/paper ngoài internet), lưu trong trường `prior_art` của future-note ([roadmap/README.md](roadmap/README.md) §3). Cùng loài `current_anchors` (neo nội) nhưng trỏ ra ngoài: `<tên> — <URL> — mechanism — checked:<date>`. Là proof-of-feasibility, KHÔNG phải proof-of-need, KHÔNG phải thaw-trigger. |
```

## Acceptance (phase 1)

- `grep -n 'prior_art' docs/roadmap/README.md` → §3 có 9 trường + 3 luật; §7 có dòng refresh.
- `grep -n 'prior_art\|external anchor' docs/roadmap/THRESHOLDS.md` → có ghi chú "KHÔNG phải trigger".
- `grep -c 'external anchor' docs/GLOSSARY.md` → ≥1.
