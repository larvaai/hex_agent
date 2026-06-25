# How-to: chạy Console UI (local)

Console UI là bảng điều khiển HTTP/SSE local để xem các run: prompts, state, logs, file explorer. Nguồn: [reference/codebase-summary.md](../reference/codebase-summary.md) (gói `ui/`, Epic E18).

## Khởi động
```bash
python -m ui.server
```
Mở trình duyệt tại **http://127.0.0.1:8765**.

## Endpoints (`/api/...`)
Server phục vụ một trang console + các API đọc dữ liệu run:

| Endpoint | Trả về |
|---|---|
| `/api/bootstrap` | dữ liệu khởi tạo trang (danh sách run, cấu hình hiển thị). |
| `/api/runs` | danh sách các run trong `var/agent_runs/`. |
| `/api/snapshot` | snapshot state của một run. |
| `/api/tree` | cây file/artifact của run. |
| `/api/file` | nội dung một file/artifact cụ thể. |
| `/api/stream` | luồng SSE event realtime của run đang chạy. |

## Lưu ý
- UI hiện là **legacy E18**, KHÔNG import `control/` (Control Plane E21 chưa wire vào UI — xem [roadmap/project-roadmap.md](../roadmap/project-roadmap.md) §E21).
- Dữ liệu đọc từ `var/agent_runs/<run_id>/` (gitignored). Chạy `python run_smoke.py` hoặc một task để có run xem thử.
- Control Tower (graph · timeline · inspector · approval modal) thuộc giai đoạn S-UI của E21 — chưa có (xem [spec/active/E21-realtime-control-plane/](../spec/active/E21-realtime-control-plane/)).
