# Factory Method trong `hex_agent` — Tập case thực chiến

> Tài liệu này soi pattern **Factory Method (Creational)** qua chính mã nguồn `hex_agent`: mỗi case rút gọn một chỗ dùng pattern thật thành một file Python chạy được bằng thư viện chuẩn, kèm bài học và đối chứng.

Bài học khái niệm gốc: [`../02_FactoryMethod.md`](../02_FactoryMethod.md). Tài liệu này **không** sửa bài gốc; nó chỉ bổ sung phần "pattern này trông thế nào trong codebase thật".

---

## Pattern xuất hiện thế nào trong hex_agent

Factory Method hiện diện rõ ở `hex_agent`, chủ yếu trong **tạo session** và **khởi tạo service/agent**. Điểm chung theo đúng tinh thần GoF: một interface/quy trình chung, còn **quyết định kiểu cụ thể** được ủy thác cho factory method/hàm factory chọn implementation theo **ngữ cảnh hoặc cấu hình**.

Codebase trải đủ phổ của họ "factory":
- **Factory Method đa phương thức**: `SessionFactory` với `create_root`/`create_child`/`restore`.
- **Factory dựa registry/config**: `AgentRegistry.build_agent` chọn Agent theo tên role (không if-else).
- **Simple Factory**: `build_service` của RAG — if-elif chọn backend (ranh giới dạy học: khi nào đủ, khi nào nâng cấp).
- **Plugin Factory ở quy mô hệ thống**: `install_configured_features` — registry các hàm `install` của plugin.
- **Factory dạng projection/adapter**: `AgentRegistry.role_view` — chiếu `RoleSpec` thành `RoleView`.

---

## Các case con

| # | Case | Chỗ thật (file:line) | Loại factory | Điểm dạy học chính |
|---|------|----------------------|--------------|--------------------|
| 01 | [`session_factory`](./01_session_factory/) | `core/session.py:104-203` | Factory Method (đa phương thức) | Nhiều biến thể tạo + bất biến (freeze, event, scope-subset) dồn vào một Creator |
| 02 | [`agent_registry_build`](./02_agent_registry_build/) | `roles/registry.py:60-66` | Factory + Dependency Injection | "Tạo gì" do config (RoleSpec) quyết định, không if-else; tiêm skills/lenses |
| 03 | [`rag_service_factory`](./03_rag_service_factory/) | `rag/feature.py:27-42` | Simple Factory (→ Registry) | Phân biệt Simple Factory vs FM GoF; import lười; khi nào nâng cấp |
| 04 | [`kernel_bootstrap`](./04_kernel_bootstrap/) | `core/bootstrap.py:56-66`, `features/loader.py:10-25` | Plugin Factory (registry) | Factory ở quy mô hệ thống: registry các `install`, chọn theo config |
| 05 | [`role_view_factory`](./05_role_view_factory/) | `roles/registry.py:69-79` | Factory (projection/adapter) | FM không chỉ chọn subclass — còn để dựng view/adapter hợp ngữ cảnh |

Mỗi thư mục con có `README.md` (6 mục: bối cảnh → trích code thật → ánh xạ vai trò → bản rút gọn → cái giá → câu hỏi) và một file `.py` self-contained.

---

## Cách chạy

```bash
python3 01_session_factory/session_factory.py
python3 02_agent_registry_build/agent_registry_build.py
python3 03_rag_service_factory/rag_service_factory.py
python3 04_kernel_bootstrap/kernel_bootstrap.py
python3 05_role_view_factory/role_view_factory.py
```

Mỗi file chỉ dùng thư viện chuẩn Python (3.14), in narration tiếng Việt từng bước, có `assert` chứng minh bất biến của pattern, và một đối chứng "khi không dùng pattern thì hỏng/khó thế nào". Tất cả thoát code 0, không traceback.

---

## Sơ đồ phổ "factory" trong hex_agent

```
                 "Tạo loại nào / dựng ra sao" được đóng gói ở đâu?

  Simple Factory            Factory Method            Plugin / Registry Factory
  (1 hàm if-elif)           (Creator + method/s)      (registry các factory fn)
        │                          │                            │
  rag.build_service        SessionFactory.create_*       install_configured_features
  (rag/feature.py:27)      (core/session.py:104)         (features/loader.py:10)
                           AgentRegistry.build_agent
                           (roles/registry.py:60)
                                   │
                           biến thể projection:
                           AgentRegistry.role_view
                           (roles/registry.py:69)
```

Xem [`CATALOG.md`](./CATALOG.md) cho bảng vét cạn mọi nơi mang dáng dấp factory trong codebase.
