# E13 — Software Factory · `park-with-trigger`

> Living note (roadmap "kho lạnh có nhãn-ngưỡng"). Nguồn: report `roadmap-living-notes` §E13 (bám code thật). Đọc cùng [README.md](../README.md) + [dependency-map.md](../dependency-map.md). `deps 🟢` = *được phép* ≠ *nên*.

## 1. problem_solved
Dây chuyền xác định, lặp-lại-được: spec → BA làm rõ → code → test → reviewer, theo thứ tự **CỐ ĐỊNH** có cổng handoff, thay vì để Agent O chọn tuyến tự do mỗi vòng. Biến SoD (đang là quy ước yaml) thành pipeline thật có artifact bàn giao + audit per-chặng. Cùng spec chạy lại đi đúng cùng đường — thứ TaskLoop hiện không đảm bảo.

## 2. why_not_now
Chưa đủ "tải". Library 5 vai trò, chỉ DUY NHẤT `code` không-tự-validate (`roles/library/code.yaml:18-19` owns_validation:false, must_handoff_to:test) → chuỗi handoff bắt buộc dài **1 cạnh** (code→test). Định tuyến đa-role ĐÃ chạy qua E10: Agent O phát `next_agent_calls` mỗi vòng (`supervisor/contracts.py:48-55`), `_drive` lặp tới terminal (`supervisor/loop.py:153-199`). "Đi qua nhiều role" không bị chặn — chỉ chưa cố-định-hóa.

## 3. current_anchors (verbatim)
- DAG handoff tĩnh trong yaml: `business_analyst.yaml:7-9`, `code.yaml:13-19`, `test.yaml:11-13`, `reviewer.yaml:12-14`.
- enforcement per-role không có orchestrator dây chuyền: `roles/agent.py:31-34`, `:56-68` (guard_finish).
- "spec" hiện chỉ là per-call `DelegationSpec` (`core/schemas.py:135-137`) + per-round `AgentAssignment` (`supervisor/contracts.py:40-44`).
- tên "Factory" duy nhất = `SessionFactory` (`core/session.py:104`, KHÔNG liên quan).

## 4. wiring_threshold (chạm 1 trong số)
- (a) owns_validation:false ≥3 (nay **1**) → chuỗi handoff ≥3 cạnh — đếm: `grep -rl 'owns_validation: false' roles/library/*.yaml | wc -l`.
- (b) cùng spec chạy lại ≥10 lần theo thứ tự cố định.
- (c) cần audit "chặng nào tạo artifact nào" mà `delegation.finished` (`delegation/manager.py:52-61`) chỉ cho artifact_count phẳng.
- (d) **E12 khởi động** (map E12→E13).

## 5. wiring_sketch (seam file:line)
Định nghĩa `FactorySpec` cạnh `core/schemas.py` (KHÔNG nhồi vào DelegationSpec); driver tái dùng `compose_team`/`_drive` (`supervisor/loop.py:147-199`) nhưng đọc thứ tự stage TỪ `may_route_to`/`must_handoff_to` (`roles/spec.py:48-50`); mỗi chuyển-chặng qua `DelegationManager.delegate` (`delegation/manager.py:63`) giữ scope-⊆-parent; thêm `stage_id` vào event để audit. Altitude rẻ nhất: cờ `pin_route` ~50 dòng khoá o_decide vào tuyến cố định.

## 6. dependencies (cổng)
Gate-in 🟢 E09/E10 done · gate-out 🔴 chờ E12. Trên critical path `E10 → E13 → E12` — phải sẵn TRƯỚC E12. *Lý do duy nhất không bỏ: E13 mở khóa E12.*

## 7. critique (YAGNI · risks-built · risks-skipped)
Mục tiêu cốt lõi ("task qua nhiều role có SoD") ĐÃ đạt bằng E10 + role guards, miễn phí. E13 chỉ thêm giá khi cần tính XÁC ĐỊNH của tuyến, không phải khả năng đi nhiều role. Rẻ hơn: cờ `pin_route` ~50 dòng trong supervisor/.
- **Build sớm** = 2 đường định tuyến song song phải bảo trì.
- **Bỏ hẳn** = E12+E16 khai báo phụ thuộc E13 → phải tái định nghĩa "đơn vị factory" sau.

## 8. verdict
`park-with-trigger`. Tầng rã đông: **2 (minimal)** — cờ `pin_route`, kích khi E12 vào thiết kế (hoặc owns_validation:false ≥3).
