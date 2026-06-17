# Changelog

Mỗi mục = một đợt thêm/sửa, gắn với **Sprint + Epic**, để theo dõi "thêm gì, vì sao". Mục mới nhất ở trên.

## Sprint 1 — Tools/Safety + Single-agent graph · 2026-06-16
Thêm tool layer in-process có chokepoint an toàn, và vòng lặp single-agent trên graph.

- **E06 Tools & Safety** (`safety/`, `toolbox/`):
  - `safety/sandbox.py` — path-jail workspace (`resolve` + `is_relative_to`).
  - `safety/policy.py` — `ToolPolicy` (terminal argv-only, chặn shell/lệnh phá hủy/git mutation) + `SafeToolPort` (chokepoint bọc mọi tool).
  - `toolbox/filesystem.py` (`fs_read/fs_write/fs_list`, sandbox), `toolbox/terminal.py` (`terminal_run`, argv-only + timeout), `toolbox/feature.py` (đăng ký tool qua SafeToolPort).
  - Quyết định: tool **in-process** đi qua kernel (không spawn mỗi call), `core/kernel.py` KHÔNG đổi (lõi sạch).
- **E05 Single-agent graph** (`graph/`): `state.py`, `nodes.py` (agent + tool node), `runtime.py` (`run_agent`: loop agent↔tool, dùng discipline + budget + finish-gate + event log). Single = 1 agent node + 1 tool node; multi-agent (E10) tái dùng nguyên loop.
- Tests: `tests/test_{safety,toolbox,graph}.py`. Config: thêm `toolbox` vào `config/features.yaml`.
- Verify: E06 logic test cô lập PASS (sandbox escape, policy, fs jail, SafeToolPort chokepoint); mọi file mới ast-parse sạch. (Full `pytest` xác nhận trên máy bạn — sandbox đang bị glitch đọc mount.)

## Sprint 0 — Nền móng (P0) · 2026-06-16
Khởi tạo repo `core_agent` + 4 epic nền. **24/24 test xanh**, smoke `CORE_AGENT_SMOKE_OK`.

- **E01 Kernel** (`core/`): `kernel`, `registry` (+ null fallback), `schemas` (envelope CapabilityResult), `events`, `state`, `bootstrap`; feature plugin từ `config/features.yaml` (`features/loader.py`, `features/example_echo.py`).
- **E02 Output Discipline** (`discipline/`): `json_gate` (parse+repair), `condense`, `finish_gate`, `budget`.
- **E03 LLM Adapter** (`llm/adapter.py`): JSON-mode, lazy client, injectable, lỗi → final JSON.
- **E04 Observability** (`observability/`): `event_log` (JSONL+summary+metrics), `inspect` CLI.
- Tests: `tests/test_{kernel,discipline,llm_adapter,observability}.py` (24 case). Smoke: `run_smoke.py`.
- Tooling: `tools/gen_map.py` → sinh `MAP.md`.
