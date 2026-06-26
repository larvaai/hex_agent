---
phase: 2
title: "TS Contract Generation + drift-guard"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — TS Contract Generation + drift-guard

## Overview

Sinh **TypeScript types từ dataclass** (single source of truth = `control/`), không
hand-write TS (drift im lặng → R4). Junior reader: TS types khớp Python contract nghĩa
là IDE bắt sai field ngay khi gõ. Phụ thuộc **Phase 1** (cần đủ 5 shape tồn tại).

Vì sao **direct `.d.ts`** (D2, không JSON-Schema trung gian): dataclass không pydantic
([events.py:3-4](../../../control/events.py)) → không có `.model_json_schema()`; nhưng
mỗi dataclass đã có `as_dict` liệt kê field **tường minh** → introspect là đủ. Thêm
JSON-Schema + `json-schema-to-typescript` = thêm dep + 1 lớp trung gian cho cùng kết
quả (vi phạm YAGNI/KISS).

## Files

**Create:**
- `tools/gen_ts_contracts.py` — generator + cờ `--check` (drift-guard). `argparse` 2 mode: mặc định = ghi file; `--check` = regenerate vào buffer + so file đĩa, exit 1 nếu lệch. (KHÔNG mượn `gen_map.py` — nó không có argparse/`--check`, red-team F10.)
- `ui/control-plane/src/contracts/generated.d.ts` — **output** (generated, committed; generator tự tạo dir nếu chưa có — file types phải có trước để Phase 4 import).
- `tests/test_gen_ts_contracts.py` — test generator + `--check`.

**Modify:** (none — generator đọc `control/` read-only)

### Hợp đồng generator
- Input: introspect 5 shape (gồm nested): `RuntimeEvent`+`Actor`/`TraceContext`/`RedactionInfo`
  ([events.py](../../../control/events.py)), `RuntimeCommand`+`IssuedBy`+`CommandAck`
  ([commands.py](../../../control/commands.py)), `RuntimeCheckpoint` ([checkpoint.py](../../../control/checkpoint.py)),
  `Permission` ([permission.py](../../../control/permission.py)), `TaskLoopSnapshot`+`AgentView`
  (`control/snapshot.py` — Phase 1).
- Map type Python→TS: `str→string`, `int/float→number`, `bool→boolean`, `X|None→X|null`,
  `tuple[str,...]/list→T[]`, `dict[str,Any]→Record<string, unknown>`, nested dataclass→interface ref.
- Output: `export interface RuntimeEvent { … }` cho mỗi shape, + header
  `// GENERATED from control/*.py — do not edit; run tools/gen_ts_contracts.py`.
- `--check`: regenerate vào buffer, so với file trên đĩa; **khác** → in diff + exit **1**.

## TDD

### Tests Before (RED)
- [ ] `test_generated_has_all_five_shapes`: chạy generator → output chứa `interface RuntimeEvent`, `RuntimeCommand`, `CommandAck`, `RuntimeCheckpoint`, `Permission`, `TaskLoopSnapshot`. **Khoá:** không sót shape.
- [ ] `test_field_names_match_as_dict`: với `RuntimeCheckpoint`, field trong `.d.ts` == key của `RuntimeCheckpoint(...).as_dict()` ([checkpoint.py:70](../../../control/checkpoint.py)). **Khoá:** TS field == Python contract.
- [ ] `test_check_flag_exit_code`: generate xong → `--check` exit **0**; rồi mô phỏng drift (ghi file đĩa thêm 1 dòng field) → `--check` exit **1**. **Khoá:** drift-guard thật sự đỏ.
- [ ] Run → FAIL (chưa có `tools/gen_ts_contracts.py`).

### Implement
1. `tools/gen_ts_contracts.py`: docstring `"""Generate TS types from control/ dataclasses. Epic E21."""`; `dataclasses.fields()` để liệt kê; map type theo bảng; `--check` so sánh + exit code. Stdlib-only (`argparse`, `dataclasses`, `typing`), không dep ngoài.
2. Chạy 1 lần ghi `ui/control-plane/src/contracts/generated.d.ts` (commit file này).
3. Min code 3 test xanh.

### Tests After (xanh)
- [ ] 3 test trên xanh.
- [ ] Chạy thật `python tools/gen_ts_contracts.py --check` → exit 0 (đồng bộ).

### Regression Gate
`python -m pytest tests/ tests_audit/ -q && python tools/gen_ts_contracts.py --check`
→ pytest PASS + check exit 0.

## Success
- [ ] `generated.d.ts` tồn tại, chứa cả 6+ interface (5 top-level + nested), header "do not edit".
- [ ] `--check` exit 0 khi đồng bộ; exit 1 + in field lệch khi mô phỏng đổi 1 dataclass field.
- [ ] Không thêm dependency Python (pyproject `dependencies` không đổi).

## Risks
- **Type-map thiếu case** (tb): chỉ map kiểu thật có trong 5 shape. Kiểu ngoài whitelist → generator **raise rõ ràng**, không sinh `any` mù. Mitigation: `test_field_names_match_as_dict` bắt; whitelist kiểu.
- **CI chưa wire `--check`** (thấp, ngoài scope plan): để lệnh sẵn trong Regression Gate; wiring CI là việc ops, ghi BACKLOG.
