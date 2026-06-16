# Changelog

Mỗi mục = một đợt thêm/sửa, gắn với **Sprint + Epic**, để theo dõi "thêm gì, vì sao". Mục mới nhất ở trên.

## Sprint 0 — Nền móng (P0) · 2026-06-16
Khởi tạo repo `core_agent` + 4 epic nền. **24/24 test xanh**, smoke `CORE_AGENT_SMOKE_OK`.

- **E01 Kernel** (`core/`): `kernel`, `registry` (+ null fallback), `schemas` (envelope CapabilityResult), `events`, `state`, `bootstrap`; feature plugin từ `config/features.yaml` (`features/loader.py`, `features/example_echo.py`).
- **E02 Output Discipline** (`discipline/`): `json_gate` (parse+repair), `condense`, `finish_gate`, `budget`.
- **E03 LLM Adapter** (`llm/adapter.py`): JSON-mode, lazy client, injectable, lỗi → final JSON.
- **E04 Observability** (`observability/`): `event_log` (JSONL+summary+metrics), `inspect` CLI.
- Tests: `tests/test_{kernel,discipline,llm_adapter,observability}.py` (24 case). Smoke: `run_smoke.py`.
- Tooling: `tools/gen_map.py` → sinh `MAP.md`.

<!-- Mẫu cho lần sau:
## Sprint 1 — E06 MCP Tools & Safety, E05 Single-agent Graph · <ngày>
- E06 (`tools_mcp/`): client một-cửa, policy chokepoint, sandbox. Tests: ...
- E05 (`graph/`): single-agent graph 1 node, tái dùng discipline. Tests: ...
-->
