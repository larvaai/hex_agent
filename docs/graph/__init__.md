# Giải thích `graph/__init__.py`

File `graph/__init__.py` định nghĩa public API cấp package cho `graph`.

Nội dung:

```python
from graph.runtime import run_agent
from graph.state import AgentState

__all__ = ["run_agent", "AgentState"]
```

## Vai trò

Package `graph` hiện expose hai API chính:

- `run_agent`: chạy vòng agent đơn.
- `AgentState`: state object dùng trong vòng graph.

Nhờ file này, caller có thể import ngắn:

```python
from graph import run_agent, AgentState
```

thay vì:

```python
from graph.runtime import run_agent
from graph.state import AgentState
```

## Ý nghĩa kiến trúc

`graph` là lớp orchestration nằm trên kernel. Kernel chỉ biết nhận task và execute tool. `graph` mới là nơi tạo vòng:

```text
LLM -> action JSON -> tool/final/retry -> observation -> LLM
```

`__init__.py` giữ public surface nhỏ: muốn chạy agent thì dùng `run_agent`, muốn thao tác state thì dùng `AgentState`.

## Tóm tắt

`graph/__init__.py` là facade của package graph, export `run_agent` và `AgentState` như hai API chính của agent loop.
