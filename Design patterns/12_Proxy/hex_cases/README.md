# Proxy (Structural) trong hex_agent — Hex Cases

> **Một câu chốt:** Proxy đứng **cùng interface** với RealSubject để **chèn cross-cutting logic** (auth/policy, rate-limit, retry, timing, condense, lazy) **giữa client và real subject**, mà client KHÔNG biết mình đang nói chuyện với proxy.

Tài liệu này soi pattern **Proxy** trong codebase thật `hex_agent`, kèm các bản distill chạy được bằng stdlib. Xem bài học gốc: [`../12_Proxy.md`](../12_Proxy.md).

---

## Pattern xuất hiện ở đâu

hex_agent dùng Proxy **rất rộng** quanh việc thực thi tool, theo hai hình thái:

1. **Stacked Proxy (chuỗi middleware).** Mọi tool chạy qua một chokepoint duy nhất `AgentKernel.execute_tool` (`core/kernel.py:106-225`). Quanh nó là một chuỗi middleware, mỗi cái là một Proxy cùng interface `ToolHandler`, chèn một concern rồi delegate cho `nxt`. Kernel lắp chuỗi theo thứ tự ngược (`core/kernel.py:192-194`). Đây là ví dụ Proxy **hoàn chỉnh nhất**: nhiều loại proxy khác nhau (Protection / Rate-limit / Smart-reference) xếp chồng, cùng interface, trong suốt với client, thứ tự quan trọng.

2. **Wrapper Proxy đơn (SafeToolPort).** `SafeToolPort` (`safety/policy.py:105-124`) bọc trực tiếp một executor: lưu real subject trong `_inner`, check policy rồi block-or-delegate. Đây là Proxy **một-class rõ ràng nhất**, đúng khuôn mẫu GoF.

Các vai trò pattern (chung cho cả hai):
- **Subject interface** = `ToolHandler` (callable) / `ToolPort.execute`.
- **RealSubject** = tool executor lõi (`core/kernel.py:152-177`) / executor được bọc.
- **Proxy** = mỗi middleware (`PolicyGate`, `BudgetGuard`, `Retry`, `TimingLog`, `CondenseResult`) / `SafeToolPort`.
- **Client** = vòng lặp agent gọi `execute_tool`.

---

## Các case con

| # | Folder | Flagship | Vai trò Proxy minh hoạ |
|---|---|---|---|
| 01 | [`01_kernel_middleware_stack/`](./01_kernel_middleware_stack/) | Middleware Chain as Proxy Stack | Stacked Proxy: Protection + Rate-limit + Smart-reference xếp chồng quanh 1 chokepoint |
| 02 | [`02_safe_tool_port_protection/`](./02_safe_tool_port_protection/) | SafeToolPort — Protection Proxy | Protection Proxy một-class: `_inner` + pre-check policy + delegate |

Mỗi folder có `README.md` (bài học) và một file `.py` chạy được bằng `python3` (chỉ stdlib).

Danh sách **vét cạn** mọi occurrence của Proxy trong codebase: xem [`CATALOG.md`](./CATALOG.md).

---

## Cách chạy

```bash
python3 01_kernel_middleware_stack/kernel_middleware_stack.py
python3 02_safe_tool_port_protection/safe_tool_port_protection.py
```

Cả hai in narration tiếng Việt từng bước, có `assert` chứng minh bất biến của pattern, và một mục **đối chứng** cho thấy "khi KHÔNG dùng Proxy thì hỏng/khó thế nào".

---

## Phân biệt với họ hàng (nhắc lại từ bài gốc)

| Pattern | Cùng interface? | Intent |
|---|---|---|
| **Adapter** | KHÁC | Đổi interface |
| **Decorator** | CÙNG | Thêm hành vi |
| **Proxy** | CÙNG | **Kiểm soát truy cập** |
| **Facade** | KHÁC | Đơn giản hoá subsystem |

Lưu ý: middleware chain ở case 01 có cấu trúc giống Decorator/Chain-of-Responsibility, nhưng **intent** ở đây là *control* (chặn, giới hạn, gác cổng) nên xếp vào Proxy — đúng như plan discover phân loại. Tên class theo intent (`PolicyGate`, `BudgetGuard`, `SafeToolPort`) làm rõ vai trò gác cổng.
