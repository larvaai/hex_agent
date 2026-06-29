# Case 04 — Composition Root: Feature Bootstrap (Wiring Adapters into Core)

> **Pattern**: Clean Architecture — *composition root* (vòng 4 chạm vòng 1).
> Clean Architecture cho phép ĐÚNG MỘT chỗ import mọi vòng — nơi outer gặp inner. hex_agent
> phân tán composition qua `build_kernel` + feature installer + bootstrap subsystem.
> Config-driven lazy loading: tắt feature → KHÔNG import adapter (và dep nặng) của nó.

---

## 1. Bối cảnh trong hex_agent

`AgentKernel` (lõi) không được phép biết feature nào tồn tại — nếu nó `import features.rag` thì lõi phụ thuộc adapter, vi phạm dependency rule. Nhưng *ai đó* phải nối adapter vào lõi. Clean Architecture trả lời: **composition root** — nơi duy nhất nhìn thấy mọi vòng.

hex_agent có nhiều composition root nhỏ, mỗi cái cho một subsystem:

- `build_kernel` (**`core/bootstrap.py:56-66`**) tạo `AgentKernel`, rồi gọi `install_configured_features` + `_install_middleware`. Đây là điểm hội tụ chính.
- `install_configured_features` (**`features/loader.py:10-25`**) duyệt `config['features']`, **bỏ qua feature `enabled=False`**, `importlib.import_module(module_path)` rồi gọi `module.install(kernel)`. Lazy: feature tắt → module không bao giờ được import.
- `features/llm_chat.py:17-37`: `LLMChatTool` (adapter) + `install(kernel)` đăng ký feature/tool vào `kernel.registry`. Một "feature module" = use case + adapter + port đóng gói.
- `delegation/bootstrap.py:13-24` là composition root của subsystem delegation, cùng pattern (đã phân tích ở case 01).

Hệ quả thực dụng: nếu RAG bị tắt trong `config/features.yaml`, `qdrant_client`/`fastembed` không bị import → base install nhẹ, khởi động nhanh.

---

## 2. Trích đoạn code thật

Composition root chính (`core/bootstrap.py:56-66`):

```python
def build_kernel(config: dict[str, Any]) -> AgentKernel:
    kernel = AgentKernel(
        registry=CapabilityRegistry(),
        events=EventBus(),
        config=config,
    )
    from features.loader import install_configured_features
    install_configured_features(kernel, config)
    _install_middleware(kernel, config)
    return kernel
```

Lazy loader bỏ qua feature tắt (`features/loader.py:10-25`):

```python
def install_configured_features(kernel: AgentKernel, config: dict[str, Any]) -> None:
    features = config.get("features", {}) or {}
    for name, spec in features.items():
        spec = spec or {}
        if not spec.get("enabled", False):
            continue                                   # <- tắt: không import module
        module_path = spec.get("module")
        if not module_path:
            raise ValueError(f"Feature '{name}' is enabled but has no 'module'.")
        module = importlib.import_module(module_path)  # <- lazy import theo config
        install = getattr(module, "install", None)
        if install is None:
            raise ValueError(f"Feature module '{module_path}' has no install(kernel).")
        install(kernel)                                # <- adapter tự đăng ký vào registry
```

Một feature module = adapter + `install` (`features/llm_chat.py:35-37`):

```python
def install(kernel: AgentKernel, *, client: Any = None) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=client), feature_name=FEATURE.name)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Clean Architecture | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Composition root (vòng 4)** | `build_kernel` — thấy config + adapter + middleware | `core/bootstrap.py:56-66` |
| **Composition root subsystem** | `create_delegation_service` | `delegation/bootstrap.py:13-24` |
| **DIP container thủ công** | `install_configured_features` (lazy import theo config) | `features/loader.py:10-25` |
| **Feature = use case + adapter + port** | `features/llm_chat.py` (`LLMChatTool` + `install`) | `features/llm_chat.py:17-37` |
| **Application registry (vòng 2)** | `CapabilityRegistry` (register/resolve/freeze) | `core/registry.py:43-122` |
| **Graceful fallback** | `NullToolPort` khi tool thiếu | `core/registry.py:29-40` |
| **DIP metadata** | `config['features']` (enabled + module) | `config/features.yaml` |

---

## 4. Bản rút gọn chạy được

File: [`feature_installer_composition.py`](feature_installer_composition.py)

Nó **mô phỏng**:
- `FeatureDescriptor`, `CapabilityRegistry` (register/resolve/freeze), `NullToolPort`, `AgentKernel` tối giản.
- Hai feature module (`features.llm_chat`, `features.rag`), mỗi cái có adapter + `install(kernel)`.
- `install_configured_features` bỏ qua feature tắt; `build_kernel` là composition root.
- Một "module registry" trong-tiến-trình + bộ đếm `_IMPORT_COUNTS` đứng thay `importlib` + filesystem, để **chứng minh lazy loading**: tắt `rag` → `features.rag` không được import, dep nặng `__heavy_qdrant__` không xuất hiện; bật `rag` → mới import.

Nó **lược bỏ** (so với bản thật):
- `importlib.import_module` + file thật → "module registry" trong bộ nhớ (để case chạy mà không cần các file `features/*` của hex_agent).
- `EventBus`, `_install_middleware`, `register_tools`, descriptor metadata (kind/risk/idempotent), fallback executor có cấu hình.
- YAML loader (`load_config`) → config truyền thẳng dạng dict.

Chạy:

```bash
python3 feature_installer_composition.py
```

Các `assert` chứng minh: (a) feature tắt → module không import → dep nặng không kéo theo; (b) feature bật → module import đúng một lần → dep nặng xuất hiện; (c) tool thiếu → `NullToolPort`, kernel không crash; (d) `freeze` chặn mutate sau composition; (e) composition root thấy mọi vòng (nhận config và wire adapter).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Composition root có thể phình to** ("god composition"): mọi wiring dồn về một chỗ. hex_agent giảm rủi ro bằng cách *phân tán* composition theo subsystem (mỗi bootstrap một file) thay vì một `main.py` khổng lồ — nhưng đổi lại phải nhớ có nhiều điểm hội tụ.
- **Lazy import dời lỗi sang runtime**: gõ sai `module` trong config chỉ vỡ lúc `build_kernel`, không phải lúc compile. Cần test bật-tắt từng feature trong CI.
- **Manual DI vs framework DI**: hex_agent wire bằng tay (không dùng container DI). Với hàng trăm thành phần, wiring tay có thể rối; nhưng với quy mô này, nó minh bạch và không thêm phụ thuộc.
- Với một app chỉ có 1-2 feature cố định, một hàm `build()` 5 dòng hard-code là đủ; máy móc loader + config + freeze chỉ đáng khi số feature và tổ hợp bật/tắt thực sự lớn.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `build_kernel` (`core/bootstrap.py`) **import bên trong hàm** (`from features.loader import install_configured_features`) thay vì ở đầu module? Liên hệ tới việc giữ vòng `core` không phụ thuộc `features`.
2. Nếu `AgentKernel` tự `import features.rag` để gọi RAG, dependency rule bị vi phạm thế nào? Composition root giải vấn đề này ra sao?
3. `features/loader.py:15-16` bỏ qua feature có `enabled=False`. Lợi ích cụ thể nào về thời gian khởi động và dependency khi RAG (cần `qdrant_client`) bị tắt?
