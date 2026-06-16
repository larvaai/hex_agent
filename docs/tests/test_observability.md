# Giải thích `tests/test_observability.py`

File `tests/test_observability.py` kiểm tra hệ thống ghi và đọc event log trong package `observability`.

Nói ngắn gọn: test này đảm bảo `EventLogger` ghi đúng file run và inspector đọc lại được.

## Import

```python
from observability import EventLogger
from observability import inspect as insp
```

Test import `EventLogger` từ facade package `observability`.

`inspect` được import như module để gọi:

- `insp.list_runs()`,
- `insp.read_summary()`,
- `insp.read_events()`.

## `test_run_writes_events_and_summary`

```python
def test_run_writes_events_and_summary(tmp_path, monkeypatch):
```

Test dùng hai fixture của pytest:

- `tmp_path`: thư mục tạm riêng cho test.
- `monkeypatch`: set environment variable tạm thời.

### Set runs dir sang temp path

```python
monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
```

Đảm bảo logger ghi vào temp dir thay vì `var/agent_runs` thật.

Hợp đồng: `EventLogger` và `inspect` đều phải dùng `runs_dir()` nên cùng đọc/ghi ở path này.

### Tạo logger

```python
logger = EventLogger(run_id="testrun")
```

Tạo logger với run id cố định để test dễ assert.

Constructor tự emit `run_started`.

### Emit event và metric

```python
logger.emit("ActionEvent", action="tool", tool="echo")
logger.count("tool_calls")
summary = logger.finish("completed")
```

Test ghi một event custom, tăng metric `tool_calls`, rồi finish run.

`finish()` ghi:

- event `run_finished`,
- `summary.json`,
- `index.jsonl`.

### Assert file tồn tại

```python
assert (tmp_path / "testrun" / "events.jsonl").exists()
assert (tmp_path / "testrun" / "summary.json").exists()
```

Hợp đồng: khi logging enabled, logger phải tạo file event và summary.

### Assert metric

```python
assert summary["metrics"]["tool_calls"] == 1
```

Metric được count phải xuất hiện trong summary.

### Assert inspector đọc được

```python
assert "testrun" in insp.list_runs()
assert insp.read_summary("testrun")["status"] == "completed"
events = insp.read_events("testrun", kind="ActionEvent")
assert len(events) == 1 and events[0]["tool"] == "echo"
```

Kiểm tra:

- `list_runs()` thấy run id,
- `read_summary()` đọc đúng status,
- `read_events(kind="ActionEvent")` lọc đúng event custom.

## `test_disabled_logging_writes_nothing`

```python
def test_disabled_logging_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    logger = EventLogger(run_id="off", enabled=False)
    logger.emit("StateEvent", status="x")
    logger.finish("completed")
    assert not (tmp_path / "off").exists()
```

Kiểm tra logging disabled.

Khi `enabled=False`:

- constructor không tạo run dir,
- `emit()` không ghi file,
- `finish()` không ghi summary/index,
- thư mục run không tồn tại.

Hợp đồng: có thể tắt file logging hoàn toàn.

## Nếu file test này đỏ nghĩa là gì?

- Logger có thể không ghi `events.jsonl` hoặc `summary.json`.
- Metrics có thể không vào summary.
- Inspector có thể không đọc đúng runs dir.
- Lọc event theo kind có thể hỏng.
- `enabled=False` có thể vẫn ghi file.

## Tóm tắt một câu

`tests/test_observability.py` bảo vệ observability layer: event log ghi được, summary đọc được, inspector hoạt động và logging có thể tắt hoàn toàn.
