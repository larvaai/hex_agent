# Case 04 — `build_kernel` + `install_configured_features` (Plugin Factory)

> Factory Method ở **quy mô hệ thống**: một **registry các hàm factory** (mỗi plugin một `install`), chọn nạp gì theo config.

---

## 1. Bối cảnh trong hex_agent

Khi khởi động, `hex_agent` dựng một `AgentKernel` rồi cài các **feature** được bật trong `config['features']` (vd `llm_chat`, `rag`, `example_echo`). Không phải lúc nào cũng muốn tất cả: test thường chỉ cần `example_echo`; bản dev không muốn kéo nguyên Qdrant của `rag`.

`install_configured_features` đọc danh sách feature, **import động** module được khai báo (`spec['module']`), rồi gọi `module.install(kernel)`. Mỗi `install()` đóng vai **factory riêng của feature**: nó tự khởi tạo và đăng ký tool/capability của mình vào kernel. Đây là Factory Method mở rộng để xử lý **extensibility (plugin)**: thay vì một factory chọn một kiểu, ta có **một registry các factory function**, gọi có điều kiện theo config (late-binding).

- File: `core/bootstrap.py:56-66` — `build_kernel(config)` dựng kernel rồi gọi `install_configured_features` + `_install_middleware`.
- File: `features/loader.py:10-25` — `install_configured_features`: import động + `getattr(module, "install")`.
- File: `rag/feature.py:109-121` — `install(kernel)` của RAG: build service rồi đăng ký 3 tool (nested factory).
- File: `core/bootstrap.py:28-53` — `_install_middleware`: factory orchestrator bật/tắt middleware theo config.

---

## 2. Trích đoạn code thật

```python
# features/loader.py:10-25
def install_configured_features(kernel: AgentKernel, config: dict[str, Any]) -> None:
    """Install each enabled feature declared in config['features']."""
    features = config.get("features", {}) or {}
    for name, spec in features.items():
        spec = spec or {}
        if not spec.get("enabled", False):
            continue
        module_path = spec.get("module")
        if not module_path:
            raise ValueError(f"Feature '{name}' is enabled but has no 'module'.")
        module = importlib.import_module(module_path)
        install = getattr(module, "install", None)
        if install is None:
            raise ValueError(f"Feature module '{module_path}' has no install(kernel).")
        install(kernel)
```

```python
# core/bootstrap.py:56-66
def build_kernel(config: dict[str, Any]) -> AgentKernel:
    kernel = AgentKernel(registry=CapabilityRegistry(), events=EventBus(), config=config)
    from features.loader import install_configured_features
    install_configured_features(kernel, config)
    _install_middleware(kernel, config)
    return kernel
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò | Thành phần trong hex_agent |
|---------|----------------------------|
| **Dispatcher** (điều phối) | `install_configured_features` (`features/loader.py:10`) |
| **Concrete creators** (factory per plugin) | hàm `install()` trong từng feature: `rag/feature.py:109`, `features/llm_chat.py`, `features/example_echo.py` |
| **Product** | `ToolPort` / `FeatureDescriptor` đăng ký vào kernel |
| **Context selector** | tên feature trong `config['features']` (+ `enabled`) |
| **Late-binding** | `importlib.import_module(spec['module'])` → `getattr(module, "install")` |
| **Factory orchestrator** | `_install_middleware` (`core/bootstrap.py:28`) bật/tắt middleware theo config |

---

## 4. Bản rút gọn chạy được

File: [`kernel_bootstrap.py`](./kernel_bootstrap.py) — chạy `python3 kernel_bootstrap.py`.

Nó mô phỏng:
- `FakeKernel` (giữ config + registry tool + middleware), ba feature `echo`/`llm_chat`/`rag` mỗi cái có một `install()` tự đăng ký tool (RAG đăng ký 3 tool = nested factory).
- `install_configured_features` chỉ nạp feature được `enabled` — bản min chỉ có `echo`.
- `_install_middleware` bật đúng middleware theo config, đúng thứ tự ngoài→trong.
- **Mở rộng**: thêm plugin `metrics` chỉ bằng cách đăng ký 1 installer, loader/`build_kernel` không đổi.
- **Đối chứng** `build_monolithic_kernel`: nhồi cứng mọi tool, không bật/tắt được, luôn kéo phụ thuộc nặng.

Đã lược bỏ: `importlib` + module thật được thay bằng một `dict[str, installer]` (`FEATURE_INSTALLERS`) trong cùng file — giữ nguyên ý "tên feature → factory, chọn theo config". Hạ tầng kernel/event/middleware thật được fake tối thiểu.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Khó truy vết tĩnh**: import động + getattr khiến IDE/linter khó theo dõi "feature nào nạp gì". Cần test khởi động và thông điệp lỗi rõ (như `loader.py:17-24`: raise "no module" ở 18-19, raise "no install(kernel)." ở 23-24). Lưu ý: bản rút gọn dùng dict `FEATURE_INSTALLERS` (xem §4) nên chuỗi lỗi của nó là `'... is enabled but has no installer.'`, KHÁC chuỗi gốc `'... is enabled but has no \'module\'.'` / `'... has no install(kernel).'` — đây là hệ quả trung thực của việc thay `importlib` bằng registry dict, không phải sai sót.
- **Bậc tự do quá mức**: nếu chỉ có vài feature cố định, một danh sách `install()` viết tay còn rõ ràng hơn loader động.
- **Thứ tự nạp & phụ thuộc giữa plugin**: registry không tự giải quyết thứ tự; nếu feature A cần feature B đã nạp trước, phải quản lý riêng.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao tách mỗi feature thành một `install(kernel)` riêng lại tốt hơn một hàm khổng lồ đăng ký mọi tool?
2. `importlib.import_module` + `getattr(module, "install")` đem lại lợi ích gì so với `import` tĩnh tất cả feature ở đầu file?
3. Đây giống Factory Method ở điểm nào, và khác ở điểm nào (gợi ý: "một factory chọn một kiểu" vs. "registry nhiều factory")?
