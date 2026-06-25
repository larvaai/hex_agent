# THRESHOLDS — sổ ngưỡng rã đông (đo thủ công theo ngày)

> Thaw Protocol **Bước 0 — Detect**. Đo định kỳ (mở sprint / thêm role/feature). Ngưỡng "chạm" khi METRIC vượt số, không cảm tính. Mỗi lần đo → thêm 1 khối ngày mới (không sửa khối cũ — giữ chuỗi thời gian).

## Lệnh đếm (chạy từ repo root)
```bash
# E11/E12 — dept distinct  (ngưỡng E11 ≥4)
grep -h '^department:' roles/library/*.yaml | sort -u | wc -l
# E11/E12 — role count  (ngưỡng E11 ≥8 → may_route_to O(n²))
ls roles/library/*.yaml | wc -l
# E13 — owns_validation:false  (ngưỡng ≥3 → chuỗi handoff ≥3 cạnh)
grep -rl 'owns_validation: false' roles/library/*.yaml | wc -l
# E14 — run count  (ngưỡng >500)
ls var/agent_runs/ 2>/dev/null | wc -l
# E14 — resume-call-site: load_checkpoint() dùng để RESUME một graph  (ngưỡng >0)
grep -rn --include="*.py" 'load_checkpoint(' . | grep -v 'def load_checkpoint'
# + status E12/E21 trong project-roadmap.md (trigger "consumer khởi động" của E11/E13/E15)
```

## Đo: 2026-06-26

| Metric | Giá trị | Ngưỡng | Đã chạm? | Ghi chú |
|---|---|---|---|---|
| E11/E12 dept distinct | 2 | ≥4 | ✗ CHƯA | engineering×3, product×1 |
| E11/E12 role count | 4 | ≥8 | ✗ CHƯA | business_analyst, code, reviewer, test |
| E13 owns_validation:false | 1 | ≥3 | ✗ CHƯA | chỉ `code.yaml` (code→test, 1 cạnh) |
| E14 run count (`var/agent_runs/`) | 155 | >500 | ✗ CHƯA | snapshot — tăng mỗi run (test/smoke/agent); đo lại `ls var/agent_runs/ | wc -l` khi cần, còn xa ngưỡng |
| E14 resume-call-site (resume-a-graph) | 0 | >0 | ✗ CHƯA | xem nuance ↓ |
| E12 consumer (E11 template chọn-được) | 0 | ≥2 | ✗ CHƯA | chưa có IntentRouter/template |
| E21 status (trigger E15) | Phase A + B1 | vượt Phase B | ✗ CHƯA | E15 chờ runtime PAUSE thật |

**Nuance E14 resume-call-site**: lệnh `grep load_checkpoint(` trả **7** dòng thô = 6 test (`tests/test_resume.py`, `tests/test_checkpoint.py`, `tests_audit/test_graph_resume_matrix.py`) + 1 non-test `orchestrator/loop.py:148`. Nhưng `loop.py:148` chỉ **đọc state**, KHÔNG resume một langgraph — resume CỐ Ý tắt (`orchestrator/checkpoint.py:139` "Resume intentionally does not call this", `:26` "not used to resume a graph"). Vì vậy metric ngữ-nghĩa "resume-một-graph" = **0** → CHƯA chạm.

**Kết luận ngày 2026-06-26**: KHÔNG ngưỡng nào chạm. Cả 5 living note giữ ở `future`. Trigger mạnh nhất cho cụm E11/E13/E14 vẫn là "E12 vào thiết kế" (consumer khởi động) — E12 chưa có branch/PR.
