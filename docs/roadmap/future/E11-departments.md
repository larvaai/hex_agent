# E11 — Departments · `park-with-trigger`

> Living note (roadmap "kho lạnh có nhãn-ngưỡng"). Nguồn: report `roadmap-living-notes` §E11 (bám code thật). Đọc cùng [README.md](../README.md) (vòng đời + Thaw Protocol) và [dependency-map.md](../dependency-map.md) (cổng phụ thuộc). `deps 🟢` = *được phép* ≠ *nên*.

## 1. problem_solved (tồn tại để giải vấn đề gì)
Đơn vị tổ chức trung gian giữa "1 role" và "cả company". Cho E12 một trục định tuyến cấp-phòng-ban (fan-out theo team thay vì hard-code danh sách role); cho phép áp policy/scope/ngân sách theo department thay vì lặp trên từng role; nâng separation-of-duties lên cấp tổ chức.

## 2. why_not_now (vì sao chưa đấu nối)
Chưa có thứ tiêu thụ `department`. Định tuyến chạy thuần theo role qua `may_route_to` (`roles/spec.py:49`, `roles/agent.py:53`); grep `department` trong delegation/orchestrator/supervisor/control/core = **rỗng**. Library 4 role / 2 phòng ban (engineering×3, product×1) — string là đủ. Consumer thật (E12) chưa bắt đầu.

## 3. current_anchors (neo file:line — verbatim)
- `roles/spec.py:19` — `department` là field bắt buộc.
- `roles/spec.py:45` — `department: str` (string trần).
- `roles/spec.py:104` — parse `str(...).strip()`, không validate.
- `roles/library/{code,test,reviewer}.yaml:3` = engineering · `business_analyst.yaml:3` = product.
- read-sites của `.department` ngoài test = **0**.

## 4. wiring_threshold (ngưỡng đo-được — chạm 1 trong số)
1. dept distinct ≥4 (nay **2**) — đếm: `grep -h '^department:' roles/library/*.yaml | sort -u | wc -l`.
2. role ≥8 khiến `may_route_to` phình O(n²) (nay **4**) — đếm: `ls roles/library/*.yaml | wc -l`.
3. **E12 vào thiết kế cần trục route theo team** — trigger mạnh nhất.
4. cần policy theo nhóm khiến 1 rule copy ≥3 lần.

## 5. wiring_sketch (seam file:line)
Nâng `department: str` (`roles/spec.py:45`) → value object / `DepartmentRegistry` cạnh `roles/registry.py`, validate tại `roles/spec.py:104`; thêm hàm derive role-theo-department cho E12 fan-out; policy cấp-department cắm vào hợp nhất scope `roles/spec.py:53-63` giữ "forbidden wins". Bắt đầu nhỏ: **registry + validate** trước.

## 6. dependencies (cổng)
Gate-in 🟢 E09/E06/E08 done · gate-out 🔴 chờ E12. **Deadlock ngưỡng E11↔E12**: E12 chờ E11 ship, nhưng trigger mạnh nhất của E11 lại là "E12 in-progress" → áp mồi phá vòng: E11 rã đông **mức tối thiểu (registry-only)** khi E12 vào thiết kế.

## 7. critique (YAGNI · risks-built · risks-skipped)
YAGNI mạnh ở dạng "hạ tầng". Field bắt buộc từ E09 mà 0 read-site = tính năng đầu cơ điển hình. Rẻ hơn: giữ string, chỉ thêm registry khi E12 gọi.
- **Build sớm** = đóng băng abstraction sai cho 2 phòng ban (rủi ro over-engineer hierarchy / policy-engine).
- **Bỏ hẳn** = `may_route_to` phình O(n²), SoD kẹt ở role↔role, nợ đẩy sang E12.

## 8. verdict
`park-with-trigger`. Tầng rã đông: **1 (minimal)** — DepartmentRegistry + validate, theo trigger-consumer (E12 thiết kế), không build full hierarchy.
