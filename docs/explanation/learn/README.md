# Giáo trình tương tác — "Xây quốc gia hex_agent"

> Học kiến trúc `hex_agent` theo lối **xây quốc gia từ nhu cầu**: mỗi chương bắt đầu bằng một
> *nhu cầu* ("tôi cần X"), đố bạn đoán giải pháp, rồi mới cho xem cơ chế thật chạy bằng animation.
> Mỗi chương là **một file HTML tự chứa** — mở bằng browser là chạy, không cần build, không cần mạng.

Đây là **đợt 1**: bản đồ + 3 chương lõi. Chương 4–12 sẽ ra ở đợt sau.

## Luật chơi (nhịp mỗi chương)

Mọi file `chapter-N.html` đi đúng một nhịp sư phạm — đọc theo thứ tự này:

| # | Khối | Vai trò |
|---|---|---|
| 1 | **Nhu cầu** (header) | Một câu: "tôi cần gì" → đây là lý do class/cơ chế của chương ra đời. |
| 2 | **Câu đố** | Hỏi trước, đáp án ẩn sau nút **"Lật"**. Đoán trước rồi mới lật → nhớ lâu. |
| 3 | **Sân khấu** (SVG) | Một "token" chạy qua luồng thật. Nút **▶ Play / ⏭ Step / ⏮ Reset**. |
| 4 | **Bảng `__init__`** | (chương sâu) Mỗi field của class → vai trò, gồm cả field nội bộ (`_frozen`, `_closed`…). |
| 5 | **Hộp "slice"** | (chương khó) `<details>` mở rộng, có snippet tối giản **chạy được**. |
| 6 | **Bằng chứng** (footer) | Mọi claim trỏ `file:line` thật — verify lại được khi code đổi. |

Vì sao nhịp này? Người học đi từ *cảm giác cần* → *tự đoán* → *thấy cơ chế* → *kiểm chứng được*.
Không nhồi định nghĩa khô; mỗi class xuất hiện vì một nhu cầu cụ thể đẻ ra nó.

## Các chương

| # | Chương | Nhu cầu trả lời | File |
|---|---|---|---|
| 0 | **Bản đồ** | "Toàn cảnh đứng trên cái gì?" | [chapter-0-ban-do.html](chapter-0-ban-do.html) |
| 1 | **Kernel + execute_tool** | "Tôi ra lệnh, có thứ thi hành." | [chapter-1-kernel.html](chapter-1-kernel.html) |
| 2 | **Session + state** | "Mỗi lần chạy phải có bộ nhớ riêng." | [chapter-2-session.html](chapter-2-session.html) |
| 3 | **Middleware onion** | "Cài hành vi quanh cửa mà không sửa cửa." | [chapter-3-middleware.html](chapter-3-middleware.html) |

> Chương 0 ở độ cao **bản đồ** (chỉ khối + mũi tên, chưa có tên biến). Chương 1–3 đi sâu vào từng class.

## Ràng buộc kỹ thuật (cho ai sửa / tái sinh)

- **Tự chứa tuyệt đối**: mỗi `.html` chỉ có `<style>` + `<script>` inline. KHÔNG `src`/`href` ngoài, KHÔNG CDN.
- **Template chung**: design-system (CSS variables) + 2 engine JS (`flip` đáp án, `STEPS` sân khấu) định nghĩa
  ở [chapter-0-ban-do.html](chapter-0-ban-do.html); các chương sau copy rồi chỉ thay **mảng `STEPS`** + nội dung.
  CSS lặp giữa 4 file là đánh đổi có chủ đích (mở-browser-là-chạy quan trọng hơn DRY) — về sau một *generator*
  sẽ tái sinh, không sửa tay từng file.
- **Chống drift**: mọi claim code cite `file:line` thật. Nếu sửa `core/*.py`, mở lại footer chương liên quan để verify.

## Nguồn

Khung kiến trúc: [`../../system-architecture.md`](../../system-architecture.md) ·
luồng runtime: [`../../reference/runtime-flow.md`](../../reference/runtime-flow.md) ·
ngôn ngữ chung: [`../../GLOSSARY.md`](../../GLOSSARY.md).
