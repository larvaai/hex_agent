# Giải thích `observability/__init__.py`

File `observability/__init__.py` định nghĩa public API cấp package cho observability.

Nó export các thành phần chính từ `observability.event_log`:

```python
from observability.event_log import EventLogger, attach_to_bus, runs_dir

__all__ = ["EventLogger", "attach_to_bus", "runs_dir"]
```

## Vai trò trong package

Nhờ file này, caller có thể viết:

```python
from observability import EventLogger, attach_to_bus
```

thay vì:

```python
from observability.event_log import EventLogger, attach_to_bus
```

Đây là facade nhỏ cho phần logging runtime.

## Export `EventLogger`

```python
from observability.event_log import EventLogger
```

`EventLogger` là class ghi event log JSONL, summary và metrics.

Đây là API chính mà runner dùng.

Ví dụ trong `run_smoke.py`:

```python
logger = EventLogger()
```

## Export `attach_to_bus`

```python
from observability.event_log import attach_to_bus
```

`attach_to_bus()` nối logger với `EventBus` của kernel.

Ví dụ:

```python
attach_to_bus(logger, kernel.events)
```

Sau đó kernel events sẽ được ghi vào log.

## Export `runs_dir`

```python
from observability.event_log import runs_dir
```

`runs_dir()` trả thư mục chứa run logs.

Nó hữu ích cho code cần biết log nằm ở đâu mà không hard-code path.

## Biến `__all__`

```python
__all__ = ["EventLogger", "attach_to_bus", "runs_dir"]
```

`__all__` khai báo public symbols khi dùng:

```python
from observability import *
```

Nó cũng thể hiện package observability muốn expose ba API chính này.

## Vì sao không export `inspect` ở đây?

`observability.inspect` là CLI/reader module riêng.

Không export nó ở `__init__.py` giúp package-level API tập trung vào runtime logging:

- tạo logger,
- attach vào bus,
- biết runs dir.

Muốn dùng inspect, caller có thể import trực tiếp:

```python
from observability import inspect as insp
```

hoặc chạy CLI:

```bash
python -m observability.inspect summary latest
```

## Ý nghĩa kiến trúc

File này đóng vai trò public facade cho phần observability runtime. Nó giúp runner import ngắn gọn mà không làm lộ quá nhiều chi tiết module nội bộ.

## Quan hệ với file khác

- `observability/event_log.py`: nơi implement các symbol được export.
- `observability/inspect.py`: module sibling, không export qua `__all__`.
- `run_smoke.py`: import `EventLogger`, `attach_to_bus` từ package.
- `tests/test_observability.py`: import `EventLogger` từ package.

## Tóm tắt một câu

`observability/__init__.py` là facade package, export `EventLogger`, `attach_to_bus` và `runs_dir` như API chính để gắn observability vào runtime.
