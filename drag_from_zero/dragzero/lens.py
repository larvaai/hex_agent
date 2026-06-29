"""Multi-lens advisory primitive — lenses ADVISE, the agent/code DECIDES (no-forge).

A lens is one short question to the same model from a different angle; a *combo* runs a set
of lenses and returns ALL their lines — raw AND any synthesis line — as plain free-text. A
combo may *cascade*: a later stage `reads` upstream lens lines and sees them in its ctx, but
its line only ever APPENDS to the raw set, never replaces it (plan Luật 1).

Two laws are STRUCTURAL here, not policy:
  * No-forge — a `LENS_RETURNED` payload is `{lens_id, line}`; there is no path that turns a
    lens line into a verdict key (`FORBIDDEN`), mirroring verifier.FORBIDDEN_VERDICT_KEYS. The
    DelegationDecision / PASS-FAIL authority stays with the agent + verifier.py.
  * No tool reach — `run_lenses` holds NO ToolRegistry, so a lens physically cannot dispatch a
    tool or consult another lens. The orchestrator's single `_run_tool` call site is the only
    door to tools, and a lens never passes through it.

Empty-by-default, like ToolRegistry: a `LensRegistry` with nothing registered changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .events import Event, EventLog, EventType

# Mirror verifier.FORBIDDEN_VERDICT_KEYS (+ routing keys) — a lens line is prose, never a verdict.
FORBIDDEN_LENS_KEYS = frozenset({"verdict", "route", "mode", "passed", "status", "score", "done"})


class LensComboError(ValueError):
    """A combo is structurally invalid: a stage reads a lens not produced by an earlier stage
    (self / forward / unknown ref), an hệ binds an unknown combo, or a lens id does not resolve.
    Raised at BUILD time (register / load), never at run time."""


@dataclass(frozen=True)
class Lens:
    """One angle: a 35B-trivial question whose answer is a single prose line."""

    id: str
    prompt: str


@dataclass(frozen=True)
class ComboStage:
    """One step of a combo. `reads` = upstream lens ids (cascade); () = independent.
    A reads-bearing stage may reference only lens ids produced by EARLIER stages."""

    lens: str
    reads: tuple = ()


@dataclass(frozen=True)
class ComboSpec:
    """An ordered set of stages. Stage order is list order; `reads` only back-ref → acyclic by
    construction. Validated at register/load, so run_lenses never meets a cycle."""

    id: str
    stages: tuple


def _validate_combo_acyclic(combo: ComboSpec) -> None:
    """Single back-ref pass: every `reads` id must already have been produced by an earlier
    stage. Catches self-ref, forward-ref and unknown-ref in one sweep."""
    produced: set = set()
    for st in combo.stages:
        for r in st.reads:
            if r not in produced:
                raise LensComboError(
                    f"combo {combo.id!r}: stage {st.lens!r} reads {r!r} not produced by an earlier "
                    "stage (self/forward/unknown ref)"
                )
        produced.add(st.lens)


class LensRegistry:
    """Empty-by-default catalog of lenses + combos + hệ→combo bindings (like ToolRegistry).

    It holds NO ToolRegistry and NO sandbox — by construction a lens it runs cannot reach tools.
    """

    def __init__(self) -> None:
        self._lenses: dict = {}
        self._combos: dict = {}
        self._he: dict = {}  # hệ -> (combo_id, enabled); see register_he (phase 3)

    # --- lenses + combos ---
    def register_lens(self, lens: Lens) -> Lens:
        self._lenses[lens.id] = lens
        return lens

    def register_combo(self, combo: ComboSpec) -> ComboSpec:
        _validate_combo_acyclic(combo)  # cycle/forward/unknown-ref rejected NOW, not at run
        self._combos[combo.id] = combo
        return combo

    def get_lens(self, lens_id: str) -> Optional[Lens]:
        return self._lenses.get(lens_id)

    def get_combo(self, combo_id: str) -> Optional[ComboSpec]:
        return self._combos.get(combo_id)

    def lens_names(self) -> list:
        return list(self._lenses)

    # --- hệ bindings (phase 3) ---
    def register_he(self, he: str, combo: str, enabled: bool = True) -> None:
        """Bind an hệ to a combo. `enabled` defaults True (the mandate is the point); a disabled
        hệ is configured-but-off. The combo must already be registered."""
        if self.get_combo(combo) is None:
            raise LensComboError(f"hệ {he!r} binds unknown combo {combo!r}")
        self._he[he] = (combo, bool(enabled))

    def combo_for_he(self, he: str) -> Optional[tuple]:
        """Return `(ComboSpec, enabled)` for an hệ, or None if the hệ is not bound."""
        binding = self._he.get(he)
        if binding is None:
            return None
        combo_id, enabled = binding
        return self.get_combo(combo_id), enabled


def load_lenses(data: dict) -> LensRegistry:
    """Build a validated LensRegistry from a plain dict (parsed from YAML/JSON upstream).

    Validation is at LOAD, never lazy at run: a catalog lens with no prompt, a combo stage that
    references an unknown lens, a cascade cycle, or an hệ bound to an unknown combo all raise
    LensComboError HERE. Shape (report §2):
        {catalog: {id: {prompt}}, combos: {id: {stages: [{lens, reads?}]}}, he: {name: {combo, enabled?}}}
    """
    data = data or {}
    reg = LensRegistry()
    for lens_id, spec in (data.get("catalog") or {}).items():
        prompt = (spec or {}).get("prompt", "")
        if not prompt:
            raise LensComboError(f"lens {lens_id!r} has no prompt")
        reg.register_lens(Lens(lens_id, prompt))
    for combo_id, spec in (data.get("combos") or {}).items():
        stages = []
        for st in (spec or {}).get("stages") or []:
            lens_id = st.get("lens")
            if reg.get_lens(lens_id) is None:  # every stage lens must resolve in the catalog
                raise LensComboError(f"combo {combo_id!r} stage references unknown lens {lens_id!r}")
            stages.append(ComboStage(lens_id, tuple(st.get("reads") or ())))
        reg.register_combo(ComboSpec(combo_id, tuple(stages)))  # acyclic + reads⊆earlier checked here
    for he, spec in (data.get("he") or {}).items():
        reg.register_he(he, (spec or {}).get("combo"), bool((spec or {}).get("enabled", True)))
    return reg


def _one_line(resp) -> str:
    """Coerce a lens response into ONE prose line. Accepts {"lens": str} or a bare str; NEVER
    parses a verdict field — a lens output is always plain text, never a structured verdict."""
    text = resp.get("lens", "") if isinstance(resp, dict) else resp
    text = str(text).strip()
    return text.splitlines()[0].strip() if text else ""


def run_lenses(registry: LensRegistry, stages, base_ctx: dict, llm, log: EventLog, *,
               agent_id: str, source: str) -> list:
    """Run a validated stage list against `llm`, emitting LENS_QUERIED/RETURNED per stage, and
    return ALL lines (raw + cascade) in stage order.

    `registry` resolves each stage's prompt (the lens object's `prompt`). The runner holds the
    registry only to read prompts — it has NO ToolRegistry, so a lens cannot reach a tool. A
    cascade stage's `upstream` is built from lines already produced (acyclic guarantees presence).
    """
    lines: dict = {}  # lens_id -> line, in stage order (dict preserves insertion order)
    for st in stages:
        lens = registry.get_lens(st.lens)
        if lens is None:  # an unregistered lens id is a build-time mistake, surfaced loud
            raise LensComboError(f"lens {st.lens!r} not registered")
        upstream = {r: lines[r] for r in st.reads}
        ctx = {
            "agent_id": agent_id, "role": "lens", "request": "lens",
            "lens_id": st.lens, "prompt": lens.prompt,
            "input": base_ctx, "upstream": upstream,
        }
        log.append(Event(EventType.LENS_QUERIED, agent_id=agent_id,
                         payload={"lens_id": st.lens, "source": source, "reads": list(st.reads)}))
        line = _one_line(llm.complete(ctx))
        log.append(Event(EventType.LENS_RETURNED, agent_id=agent_id,
                         payload={"lens_id": st.lens, "line": line}))
        lines[st.lens] = line
    return list(lines.values())
