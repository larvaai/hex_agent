# How-to: thêm một feature (tool plugin)

Mục tiêu: thêm một tool mới vào kernel **không sửa kernel** — đúng pattern hexagonal (ports & adapters). Nguồn: `features/loader.py`, `features/example_echo.py`, `config/features.yaml`.

## Pattern (3 mảnh)

Một feature = một module Python expose hàm `install(kernel)`. Loader đọc `config/features.yaml`, import module enabled, gọi `install(kernel)`.

### 1. Viết module feature
Theo mẫu `features/example_echo.py`:

```python
"""<mục đích 1 dòng>. Epic Exx."""   # docstring dòng đầu → tự vào MAP.md
from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor, ToolRequest

FEATURE = FeatureDescriptor(
    name="my_feature",
    capabilities=("my_tool",),
    description="...",
)

class MyTool:
    name = "my_tool_impl"
    def execute(self, request: ToolRequest) -> dict:
        return {"ok": True, "data": ...}      # PHẢI trả dict (kernel normalize)

def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, MyTool(), feature_name=FEATURE.name)
```

### 2. Đăng ký trong `config/features.yaml`
```yaml
features:
  my_feature:
    enabled: true
    module: features.my_feature   # đường import tới module ở bước 1
```
Loader (`features/loader.py:10`) duyệt `config['features']`, **bỏ qua** mục `enabled: false`, import `module`, và gọi `install(kernel)`. Thiếu `module` hoặc thiếu `install` → `ValueError` (fail-fast).

### 3. Gọi tool qua chokepoint
Tool tự động chạy qua `AgentKernel.execute_tool` (`core/kernel.py:63`) — không có đường tắt. Kernel bọc kết quả thành `CapabilityResult`, phát event `tool.requested/completed/failed` cho observability.

## Quy ước bắt buộc
- **Docstring dòng đầu** dạng `"""<mục đích>. Epic Exx."""` → MAP.md tự sinh (`python tools/gen_map.py`).
- `execute()` **luôn trả `dict`** — kernel coi non-dict là lỗi và normalize.
- Tool mới có test map tới acceptance (xem [getting-started.md](../getting-started.md) §convention).
- Feature experimental → đặt ở `features/labs/` với `enabled: false` mặc định (xem roadmap [E20](../roadmap/future/E20-labs.md)).

## Kiểm tra
```bash
python run_smoke.py        # kernel bootstrap + load feature
python -m pytest           # test feature mới
python tools/gen_map.py    # MAP.md thấy module mới
```
