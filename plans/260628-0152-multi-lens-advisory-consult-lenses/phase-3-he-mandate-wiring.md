---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — hệ mandate + Agent.he + wiring (tim của slice)

**Mục tiêu:** agent thuộc hệ X (enabled) → CODE **ép** chạy combo X lúc vào task, lines seed vào observations TRƯỚC step đầu. Agent không skip; toggle chỉ user.

## Touchpoints
- `drag_from_zero/dragzero/agent.py` — `Agent` thêm field `he: Optional[str] = None`.
- `drag_from_zero/dragzero/lens.py` — `LensRegistry` thêm binding hệ→combo+enabled.
- `drag_from_zero/dragzero/orchestrator.py` — seed mandate observations trong `_react_until_terminal` ([orchestrator.py:220](../../drag_from_zero/dragzero/orchestrator.py)).
- `drag_from_zero/dragzero/wiring.py` — `build_runtime` nhận `lenses=None`, truyền vào Orchestrator + dựng `Agent(..., he=n.attrs.get("he"))` ([wiring.py:77](../../drag_from_zero/dragzero/wiring.py)).
- `drag_from_zero/tests/test_lens.py` — thêm test hệ.

## Thiết kế

### `Agent.he` ([agent.py:34](../../drag_from_zero/dragzero/agent.py))
```
@dataclass
class Agent:
    id: str; role: str; llm: object
    he: Optional[str] = None        # keyword-default → additive, dựng cũ Agent(id,role,llm) không đổi
```

### `LensRegistry` binding
```
register_he(he: str, combo: str, enabled: bool = True)   # default True (bắt buộc)
combo_for_he(he) -> Optional[tuple[ComboSpec, bool]]      # (combo, enabled) | None
```

### Mandate — seed combo MỘT LẦN/task, áp CẢ HAI caller (orchestrator.py:250 ungated + :366 gated)

> **[red-team F2/F3 fix]** `_react_until_terminal` NHẬN `observations` làm param (orchestrator.py:255-261) — **không** có dòng init bên trong nó. Init `observations = []` nằm ở **2 caller**: `_process_one` (orchestrator.py:250, ungated) và `_solve_gated` (orchestrator.py:366, mỗi attempt). Mandate phải seed ở cả 2, qua **1 lần tính** (không per-attempt).

1. `_WorkRec` (orchestrator.py:48) thêm field `lens_seed: list = field(default_factory=list)`.
2. `_process_one` (orchestrator.py:221), **sau** hook check **trước** nhánh `if rec.task.done_when` (orchestrator.py:246) — tính 1 lần:
```
rec.lens_seed = self._mandatory_lens(rec, agent)   # [] nếu he=None/lenses=None → byte-identical
```
3. Ungated caller (orchestrator.py:250): `observations = list(rec.lens_seed)`  (was `observations: list = []`).
4. Gated caller (orchestrator.py:366, trong vòng attempt): `observations: list = list(rec.lens_seed)`  (was `= []`). → combo **KHÔNG** chạy lại mỗi attempt; seed tính 1 lần ở (2), mỗi attempt chỉ copy lại ⇒ **once-per-task**, tránh K× blow-up (red-team F3).

```
def _mandatory_lens(self, rec, agent) -> list:
    if self.lenses is None or not getattr(agent, "he", None):
        return []                                          # he=None / no registry → byte-identical []
    binding = self.lenses.combo_for_he(agent.he)
    if binding is None or not binding[1]:                  # unknown hệ HOẶC enabled=False → không chạy
        return []
    combo, _ = binding
    lines = run_lenses(combo.stages, {"task": rec.task.description}, agent.llm, self.log,
                       agent_id=agent.id, source="combo")
    return [{"tool": "lens:" + agent.he, "ok": True, "output": ln, "error": ""} for ln in lines]
```
Agent thấy lines từ `observations[0..]` — **CODE ép, agent không emit consult**. Agent vẫn gọi THÊM consult_lenses mid-loop (phase 2). `enabled` ở config frozen → agent không flip được (Luật 2). `_mandatory_lens` chạy **trước** `activated_at` (set trong `_solve_gated` orchestrator.py:358) — lens không ghi artifact nên freshness không đổi; **KHÔNG** chuyển mandate xuống dưới `activated_at`. he=None → `[]` → cả 2 caller init y hệt cũ (byte-identical).

> **[red-team F4]** FakeLLM dùng chung cho `agent.step` VÀ `run_lenses`. Responder seed-test **phải branch `ctx.get("request")=="lens"` TRƯỚC** khi chạm `ctx["observations"]` (lens ctx không có key đó → KeyError). Mẫu: `def r(ctx): return {"lens": "..."} if ctx.get("request")=="lens" else <agent step>`.

### `wiring.build_runtime` ([wiring.py:77](../../drag_from_zero/dragzero/wiring.py))
```
def build_runtime(topology, llm, *, ..., lenses=None):
    ...
    roster = Roster([Agent(n.id, n.attrs["role"], llm, he=n.attrs.get("he")) for n in ordered])
    orch = Orchestrator(roster, ..., lenses=lenses)
```

## Tests Before (đỏ trước) — `tests/test_lens.py`
1. `test_he_mandate_autoruns` — Agent("w","worker",FakeLLM,he="thanh_tra"); reg.register_he("thanh_tra","inspect_v1"); FakeLLM agent responder = SOLO ngay. Sau run: log có LENS_QUERIED (source=combo) dù agent KHÔNG emit consult; observations step-0 có lines.
2. `test_he_disabled_no_run` — `register_he(...,enabled=False)` → KHÔNG LENS_QUERIED; agent chạy như không hệ.
3. `test_he_plus_adhoc` — agent he=thanh_tra + step-0 cũng gọi consult_lenses{lenses:[x]} → log có source=combo VÀ source=adhoc.
4. `test_no_he_byte_identical` (LUẬT 3) — Agent he=None, lenses=reg → 0 LENS event; stream y hệt baseline.
5. `test_wiring_passes_he` — topology agent node `{"id":"a","type":"agent","role":"worker","he":"thanh_tra"}` → `build_runtime(...,lenses=reg)` → `roster.get("a").he == "thanh_tra"`.

## Implement After
Thêm `Agent.he` + `register_he`/`combo_for_he` + `_mandatory_lens` + wiring. Đổi 1 dòng khởi tạo observations.

## Tests After / Regression Gate
- `python -m pytest drag_from_zero/tests/test_lens.py -q` → xanh.
- `python -m pytest drag_from_zero -q` → **toàn suite xanh** (`test_slice5_topology` không đổi: thêm attr `he` không phá round-trip; `test_invariants` không đổi: he=None mặc định).

## Done-when phase
5 test xanh; hệ-mandate ép combo (đỏ-rồi-xanh), enabled=false tắt được, agent thêm lens được, he=None byte-identical, wiring truyền he; suite cũ nguyên.
