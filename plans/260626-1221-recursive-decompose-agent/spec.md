---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Decompose-until-trivial agent — v2 design spec

> Memory + execution architecture for a **local 35B** LLM agent.
> Context: this is **v2** of the design started in a prior session. v1 established
> the Navigator(code)/Worker(35B) split, the tree-on-disk memory, the 4-cell
> context, and the machine-checkable `done_when` gate. v2 integrates the user's
> guiding principle:
>
> *"If a task is HARD, it means it hasn't been broken down into small-enough
> logic and simulated as a GRAPH of steps that feed into each other. If small
> enough, the 35B WILL solve it. I don't care how many loops it takes."*
>
> => **Recursion becomes the primary mechanism.** A hard node is split into an
> ordered DAG of strictly-smaller sub-nodes until every leaf is trivially
> solvable. Loops are free; only **correctness** (gates) and **convergence** (a
> well-founded measure) are enforced.

Navigator = deterministic CODE (owns tree, cursor, gates, dataflow). Worker = the 35B (thinks LOCALLY on one node, proposes only).

## Architecture delta from v1

- **Recursion is the main loop, not an escape hatch.** v1's "attempt → gate → advance/retry" becomes `solve(node)` = *attempt as leaf K times, and on K-th FAIL decompose into children and recurse*. Leaf-ness is **discovered by trying**, never asserted by the 35B (estimate-first would trust the model's weakest faculty — planning — and is unfalsifiable by the `done_when` rule).
- **A well-founded measure `μ` makes termination a theorem, not a hope.** Every child must be strictly smaller than its parent on `μ = (done_when_count, scope_token_len)` under lex order. `(ℕ,ℕ)` is well-ordered ⇒ no infinite descent. This is the single load-bearing convergence guarantee; a per-root step budget is the measure-independent backstop.
- **Dataflow is first-class and code-owned.** Nodes gain `depends_on` (DAG edges) + `inputs` (`{from,out}` wires) + `outputs` (path contract). The Navigator's pure `resolve_inputs()` turns declarations into absolute paths at activation; the 35B sees only resolved paths and a `read(given)→write(given)` contract. It never sees the graph.
- **Compose is a real node, not a special case.** A synthetic `kind: reduce` child is auto-inserted as the last sibling, `depends_on` = all siblings, `outputs` = parent's artifact. Parent is DONE iff its reduce is DONE. If compose is hard, the reduce node decomposes like any node.
- **Decomposition is content-addressed and transactional.** `decomp_id = sha256(node_id ‖ canonical_spec ‖ decomposer_version)`, temp-0 sampling, written to `decompositions/<id>.yaml`, two-phase committed into `tree.yaml`. Retry/resume = same `decomp_id` = same children ⇒ idempotent, resumable, version-stable. Kills tree-thrash, partial-subtree loss, and version drift in one move.

## Roles & invariants

**Navigator (deterministic CODE).** Owns `tree.yaml`, the cursor, all three gates, all dataflow wiring, all budgets/detectors, the decomposition cache, the node state machine. Writes *every* PASS/FAIL and *every* Accept/Reject. Schedules dependencies. Never reasons about node content.

**Worker (the 35B).** A pure local proposer on ONE node. Two call types:
- `propose(ctx) → action` — given the minimal 4-cell context, propose the next action for THIS node only.
- `decompose(node, failure_evidence) → children` — propose `{id, title, done_when, depends_on, inputs, outputs}` triples + structure.

Context is always exactly 4 cells: `IDENTITY` (fixed preamble) / `breadcrumb root→node` / `NODE: title+done_when+resolved input paths+notes` / `journal tail (last 1–3 lines of THIS node)`.

**Hard invariants (code-enforced):**
1. **One active node at a time.** Single cursor; DFS left→right; never climb until a subtree is wholly DONE.
2. **Code owns all gates & dataflow.** The 35B never writes a verdict, never resolves a path, never mutates the tree. The schema has **no** `passed`/`status`/`score` field the model can set.
3. **The 35B only proposes** `{check, params, artifact}` triples + child structure. Everything global (identity, termination, resumability, gate integrity, wiring) lives in Navigator code.
4. **No artifact ⇒ FAIL.** Every criterion names a mandatory, path-jailed artifact; missing/empty/stale (`mtime < activated_at`) = auto-FAIL before the check even runs.
5. **Every child strictly smaller** on `μ` (lex). Non-negotiable; the termination proof.

## Node schema

```yaml
# tree.yaml — one shared schema for leaves, internal nodes, and reduce nodes
- id: ai.rag.eval                     # stable, dotted, unique
  parent: ai.rag                      # null for a root ("neuro" / "ai")
  kind: work                          # work | reduce  (reduce = synthetic compose node)
  status: pending                     # pending|active|decomposed|done|blocked
  order: 2                            # sibling order (tiebreak for the topo sort)

  depends_on: [ai.rag.index, ai.rag.queries]   # DAG edges; acyclic, topo-sortable
  inputs:                             # wires resolved by Navigator at activation
    - { name: index,   from: ai.rag.index,   out: faiss }
    - { name: queries, from: ai.rag.queries, out: qset }
  outputs:                            # path contract (relative to node artifact dir, jailed)
    - { name: recall,  path: recall.json }
    - { name: log,     path: run.log }

  done_when:                          # structured, machine-checkable; 35B authored, NO verdict field
    - { check: file_exists,         params: { path: recall.json } }
    - { check: json_len_gte,        params: { path: recall.json, ptr: /queries, n: 50 } }
    - { check: json_field_in_range, params: { path: recall.json, ptr: /recall_at_5, min: 0.80, max: 1.0 } }
    - { check: grep_absent,         params: { path: run.log, pattern: "Traceback|ERROR" } }

  attempts: 0                         # leaf attempts so far
  max_attempts: 3                     # K (=5 when dwc==1, the leaf floor)
  decomp_id: null                     # sha256(id ‖ canonical_spec ‖ decomposer_version); cache key
  decomposer_version: 3               # pinned per subtree
  decomp_history: []                  # list[sig] across retries (D4 thrash detector)
  redecomp_count: 0                   # structure-creation meter (≤ R)
  depth: 1                            # ≤ MAX_DEPTH
  see_also: [neuro.embeddings]        # cross-tree note ONLY; cursor never auto-jumps
```

Annotation: `recall_at_5 ≥ 0.80` is the real metric gate; `json_len_gte /queries 50` forces ≥50 queries actually evaluated (anti "evaluate on 2 queries"); `grep_absent Traceback` catches a silent error run. `μ(this) = (4, len(title+done_when+notes))`. Referential integrity (`from ∈ depends_on`, `out ∈ dep.outputs`) is load-time checked in CODE.

## The three gates

### Gate 1 — done-gate (check vocabulary)

Every criterion is `{check, params, artifact}`; `check` MUST be a registry key (unknown ⇒ auto-reject at acceptance, auto-FAIL at run). Each check is a pure `(params, artifact) → PASS | FAIL(reason)` over disk. **Node DONE ⇔ every criterion PASS (AND, no partial credit).**

| `check` | params | PASS iff |
|---|---|---|
| `file_exists` | `path` | exists ∧ size>0 (empty = FAIL) |
| `file_nonempty_lines` | `path, min` | line count ≥ min |
| `json_field_equals` | `path, ptr, value` | `JSONPointer(ptr) == value` |
| `json_field_in_range` | `path, ptr, min, max` | `min ≤ num(ptr) ≤ max` (metric gate) |
| `json_field_exists` | `path, ptr` | pointer resolves |
| `json_len_gte` | `path, ptr, n` | `len(array@ptr) ≥ n` |
| `row_count_gte` | `path, n` | CSV/JSONL rows ≥ n |
| `grep_matches` | `path, pattern, min` | regex hits ≥ min (default 1) |
| `grep_absent` | `path, pattern` | regex hits == 0 |
| `test_passes` | `cmd_id, expect_code` | subprocess exit == code; `cmd_id` whitelisted, sandboxed, timeout, no-net |
| `cmd_stdout_json_field` | `cmd_id, ptr, op, value` | run whitelisted cmd, parse stdout JSON, compare |
| `sha256_equals` | `path, digest` | file hash matches |
| `numeric_delta` | `path_a, ptr_a, path_b, ptr_b, op, eps` | cross-artifact compare ("new ≥ old") |
| `all_children_done` | (implicit) | every child `status==done` (reduce/internal closure) |

Runner rules: artifact mandatory + path-jailed (no `..`, no abs escape); `mtime ≥ activated_at` (no stale reuse); read-only except `test_passes`/`cmd_*` which need a registered `cmd_id` template (raw cmd strings rejected). Verdict object is Navigator-written only:

```json
{"node":"ai.rag.eval","results":[
  {"check":"json_field_in_range","verdict":"FAIL","reason":"/recall_at_5=0.71 < 0.80"}],
 "node_verdict":"FAIL"}
```

### Gate 2 — decomposition-acceptance gate

Pure function on proposed children **before** any tree mutation. Any violation ⇒ reject with exact reason; re-prompt with the reason injected. (Idempotency: on cache hit by `decomp_id`, return cached children verbatim — never re-validate, never re-sample.)

```python
def accept_decomposition(parent, children) -> Accept | Reject:
    V = []
    if len(children) < 2:                       V += ["SINGLETON: need ≥2 children (1-child split = rename)"]
    if len(children) > MAX_FANOUT:              V += ["FANOUT: >8 children"]
    ids, titles, sp = set(), set(), mu(parent)
    for c in children:
        if c.id == parent.id or norm(c.title)==norm(parent.title): V += [f"{c.id}: child==parent"]
        if c.id in ids:                         V += [f"dup id {c.id}"]
        if norm(c.title) in titles:             V += [f"dup title {c.title}"]
        ids.add(c.id); titles.add(norm(c.title))
        if not lex_lt(mu(c), sp):               V += [f"{c.id}: NOT_SMALLER than parent"]      # D2
        if jaccard(tok(parent), tok(c)) > 0.80: V += [f"{c.id}: RENAME of parent"]             # D3
        if not c.done_when:                     V += [f"{c.id}: empty done_when (PROSE_CHILD)"] # D11
        for crit in c.done_when:
            if crit.check not in CHECK_VOCAB:   V += [f"{c.id}: unknown check '{crit.check}' (prose)"]
            elif not params_valid(crit):        V += [f"{c.id}: bad params for {crit.check}"]
            elif not crit.artifact or unsafe(crit.artifact): V += [f"{c.id}: missing/unsafe artifact"]
            elif crit.check in CMD_CHECKS and crit.params.cmd_id not in CMD_TEMPLATES:
                                                V += [f"{c.id}: cmd not whitelisted"]
            if has_verdict_field(crit):         V += [f"{c.id}: self-grade verdict field forbidden"]
        for d in c.depends_on:                  # referential + no self-dep
            if d==c.id:                         V += [f"{c.id}: self-dependency"]
            if d not in ids and d not in {x.id for x in children} and d not in parent.visible_deps:
                                                V += [f"{c.id}: depends_on unknown {d}"]
    if criteria_coverage(children) < parent.dwc: V += ["UNDERCOVER: children don't cover parent done_when"]  # D6
    if has_cycle(children) or not topo_sortable(children): V += ["dep cycle / not topo-orderable"]
    if any(weaker_than_ancestor(c, parent) for c in children): V += ["metric loosened vs ancestor"]
    return Reject(V) if V else Accept(topo_sort(children))

def mu(n):  return (len(n.done_when), scope_token_len(n))   # lex; well-ordered ⇒ terminates
```

Anti-gaming: no verdict field exists (self-"done" impossible) · prose has no `check` to name · missing/empty/stale artifact = FAIL · raw `cmd` rejected (whitelist only) · child==parent / <2 children / non-shrinking μ rejected · loosened metric rejected vs ancestor · cycles rejected.

### Gate 3 — convergence gate (budgets + non-progress detectors)

`sig(node) = sha256(sorted(frozenset(c.done_when_criteria) for c in children))`. Persist `decomp_history` (across retries) and `path_sigs` (ancestors on current DFS path).

| # | Detector | Code signal | Action |
|---|---|---|---|
| D1 | Singleton split | `len(children)<2` | reject → 1 re-decompose → BLOCKED(SINGLETON) |
| D2 | Non-shrinking child | `¬ lex_lt(μ(c),μ(parent))` | reject → 1 re-decompose → BLOCKED(NOT_SMALLER) |
| D3 | Rename | `jaccard(tok)>0.80` | reject → 1 re-decompose → BLOCKED(RENAME) |
| D4 | Identical re-decomp | `sig ∈ decomp_history` (≥2) | **BLOCKED(STUCK_DECOMP)** |
| D5 | Oscillation | `sig ∈ path_sigs` (ancestor) | **BLOCKED(CYCLE)** |
| D6 | Coverage drift | `coverage(children) < parent.dwc` | reject → 1 re-decompose → BLOCKED(UNDERCOVER) |
| D7 | Fan-out explosion | `len(children)>MAX_FANOUT` | reject → 1 re-decompose → BLOCKED(FANOUT) |
| D8 | Depth runaway | `depth>MAX_DEPTH` | **BLOCKED(MAX_DEPTH)** |
| D9 | Unsolvable leaf | `attempts≥K_leaf ∧ dwc==1` | **BLOCKED(UNSOLVABLE_LEAF)** |
| D10 | Global budget | `steps≥cap ∨ tokens≥cap` | **BLOCKED(BUDGET)** at active node |
| D11 | Prose child | any child `dwc==0` | reject → 1 re-decompose → BLOCKED(PROSE_CHILD) |
| D12 | Compose-fail vs too-hard | children all DONE but parent gate FAIL | **freeze → BLOCKED(COMPOSE_FAIL)** — wiring bug, do NOT re-decompose |

Budgets: `K=3` · `K_leaf=5` (dwc==1 floor, non-decomposable) · `MAX_DEPTH=6` · `MAX_FANOUT=8` · per-root step budget `200` worker calls (the real terminator, measure-independent) · per-root token budget `~1.5M` · `redecomp_count ≤ R=2`. **Split-rejections (D1/D2/D3/D6/D7/D11) get exactly one re-decompose with the reason injected; a second rejection → BLOCKED. Hard blocks (D4/D5/D8/D9/D10/D12) surface immediately.** The single charged re-decompose can't spin because D4 catches an identical retry at once.

## Navigator loop

```python
def solve(node, depth, budget):
    # ---- circuit breakers (deterministic, first) ----
    if budget.exhausted():  return block(node, "BUDGET")          # D10
    if depth > MAX_DEPTH:   return block(node, "MAX_DEPTH")       # D8

    activate(node)                                 # status=active; node.activated_at = now()
    resolve_inputs(node)                           # wire {from,out} -> absolute paths (pure, code)

    # ---- LEAF-ATTEMPT path: discover leaf-ness by trying ----
    K = K_leaf if node.dwc == 1 else K
    while node.attempts < K:
        node.attempts += 1; budget.charge_step()
        action = worker.propose(assemble_4cell(node))    # 35B, LOCAL, one node
        result = run(action)                             # writes artifact(s) on disk
        gate   = run_checks(node, result)                # Gate 1; no/empty/stale artifact => FAIL
        journal_append(node, action, gate)
        if gate.all_pass:
            return mark_done(node)                       # advance_cursor_dfs() inside

    if node.dwc == 1:                                     # leaf floor: cannot split an atomic criterion
        return block(node, "UNSOLVABLE_LEAF")            # D9

    # ---- DECOMPOSE path: content-addressed, transactional ----
    node.decomp_id = sha256(node.id, canonical_spec(node), node.decomposer_version)
    children = cache.get(node.decomp_id)                 # idempotent resume (#1/#2/#8)
    if children is None:
        rejections = 0
        while True:
            raw = worker.decompose(node, failure_evidence=node.journal_tail(K), reason=last_reason)
            children = order_as_dag(sanitize(parse(raw)))
            insert_reduce_node(node, children)           # synthetic kind:reduce, depends_on=all sibs
            v = accept_decomposition(node, children)     # Gate 2
            sig = decomp_sig(children)
            if sig in node.decomp_history:  return block(node, "STUCK_DECOMP")   # D4
            if sig in budget.path_sigs:     return block(node, "CYCLE")          # D5
            if v.ok: break
            node.decomp_history.append(sig); rejections += 1; last_reason = v.reason
            if rejections >= 2 or node.redecomp_count >= R:
                return block(node, v.hard_reason)        # second rejection => BLOCKED
            node.redecomp_count += 1; budget.charge_step()
        write_staging(node, children); fsync()           # two-phase commit (#2)
        atomic_flip(node, status="decomposed")
        cache.put(node.decomp_id, children)              # version-pinned (#8)
    else:
        atomic_flip(node, status="decomposed")
    node.decomp_history.append(decomp_sig(children))
    budget.path_sigs.add(decomp_sig(children))

    # ---- recurse DFS, left->right; output[c_i] feeds c_{i+1} via inputs ----
    for c in topo_order(node.children):                  # reduce is last (deps on all sibs)
        solve(c, depth+1, budget)
        if c.status == "blocked":                        # BLOCKED propagates up
            return block(node, f"CHILD_BLOCKED:{c.id}")

    # ---- COMPOSE path: parent done IFF its reduce child done ----
    budget.path_sigs.discard(decomp_sig(children))       # leave this DFS path
    if not all_children_done(node):                      # only if reduce failed
        return block(node, "COMPOSE_FAIL")               # D12 — wiring bug, freeze, do NOT re-split
    return mark_done(node)

def block(node, reason):
    node.status = "blocked"
    surface_to_human(node.breadcrumb, node.done_when, reason,
                     node.journal_tail(K), node.decomp_history)   # human: write children | relax done_when | raise budget
```

`next_node()` (cursor) is equivalently: pick the leftmost `pending` node whose `depends_on` are all `done`, by `(depth, order)`. The reduce node can't be ready until every sibling is done ⇒ the topo sort **is** the "don't climb early" rule, for free.

## Worked example — "build a RAG retrieval eval harness"

Top-down split into leaves each solvable locally by the 35B, with `inputs` wired to upstream `outputs`. `ai.rag._reduce` (synthetic) folds the leaves into the parent artifact. Dataflow: `corpus → {index, queries} → eval → _reduce`.

```yaml
- id: ai.rag
  parent: ai
  kind: work
  status: decomposed
  done_when:
    - { check: all_children_done }
  children: [ai.rag.corpus, ai.rag.index, ai.rag.queries, ai.rag.eval, ai.rag._reduce]

- id: ai.rag.corpus            # leaf 1: produce a document corpus
  parent: ai.rag
  depends_on: []
  outputs: [{ name: docs, path: corpus.jsonl }]
  done_when:
    - { check: row_count_gte, params: { path: corpus.jsonl, n: 200 } }   # ≥200 docs
    - { check: grep_absent,   params: { path: corpus.jsonl, pattern: "^\\s*$" } }
  max_attempts: 3

- id: ai.rag.index             # leaf 2: embed + build FAISS index over the corpus
  parent: ai.rag
  depends_on: [ai.rag.corpus]
  inputs:  [{ name: docs, from: ai.rag.corpus, out: docs }]
  outputs: [{ name: faiss, path: index.faiss }, { name: meta, path: index_meta.json }]
  done_when:                                                         # STRUCTURED done_when (1 of 2)
    - { check: file_exists,         params: { path: index.faiss } }
    - { check: json_field_equals,   params: { path: index_meta.json, ptr: /metric, value: "cosine" } }
    - { check: json_field_in_range, params: { path: index_meta.json, ptr: /ntotal, min: 200, max: 100000 } }
  max_attempts: 3

- id: ai.rag.queries           # leaf 3: build a labeled eval query set (q -> gold doc id)
  parent: ai.rag
  depends_on: [ai.rag.corpus]
  inputs:  [{ name: docs, from: ai.rag.corpus, out: docs }]
  outputs: [{ name: qset, path: queries.jsonl }]
  done_when:
    - { check: row_count_gte, params: { path: queries.jsonl, n: 50 } }    # ≥50 queries
    - { check: grep_matches,  params: { path: queries.jsonl, pattern: "\"gold_id\"", min: 50 } }
  max_attempts: 3

- id: ai.rag.eval              # leaf 4: run retrieval, compute recall@5
  parent: ai.rag
  depends_on: [ai.rag.index, ai.rag.queries]
  inputs:
    - { name: index,   from: ai.rag.index,   out: faiss }
    - { name: queries, from: ai.rag.queries, out: qset }
  outputs: [{ name: recall, path: recall.json }, { name: log, path: run.log }]
  done_when:                                                         # STRUCTURED done_when (2 of 2)
    - { check: file_exists,         params: { path: recall.json } }
    - { check: json_len_gte,        params: { path: recall.json, ptr: /queries, n: 50 } }
    - { check: json_field_in_range, params: { path: recall.json, ptr: /recall_at_5, min: 0.80, max: 1.0 } }
    - { check: grep_absent,         params: { path: run.log, pattern: "Traceback|ERROR" } }
  max_attempts: 3

- id: ai.rag._reduce           # synthetic compose: manifest of leaf artifacts -> parent output
  parent: ai.rag
  kind: reduce
  reduce_op: manifest          # pure code (no 35B); merge_json|concat|pick|manifest
  depends_on: [ai.rag.corpus, ai.rag.index, ai.rag.queries, ai.rag.eval]
  outputs: [{ name: report, path: rag_eval_report.json }]
  done_when:
    - { check: json_field_exists,   params: { path: rag_eval_report.json, ptr: /recall_at_5 } }
    - { check: json_field_in_range, params: { path: rag_eval_report.json, ptr: /recall_at_5, min: 0.80, max: 1.0 } }
```

If `eval` is too hard (recall logic + metric both nontrivial) it decomposes further (`eval.retrieve` → `eval.score`) under the same rules — no special case. If `_reduce` keeps FAILing while all leaves are DONE, that's `COMPOSE_FAIL` (D12, wiring bug), not "split more."

## Failure modes → guards

| # | Failure mode | Root cause | Deterministic guard |
|---|---|---|---|
| 1 | Tree thrash on retry/resume | decomposition sampled & written straight to tree | **Content-addressed decomp**: `decomp_id`, temp-0, cache hit ⇒ reuse verbatim. Idempotent. |
| 2 | Partial-subtree loss after restart | resume state didn't record which children passed | **Two-phase commit** + per-child persisted `status`; resume = leftmost non-done leaf; never re-decompose a `decomposed` node. |
| 3 | Gate-gaming / un-checkable criteria | prose accepted, or artifact empty/stale | **Criterion typing at author time** (must compile to `CHECK_VOCAB`) + **artifact assertion** (`size>0 ∧ mtime≥activated_at`); no verdict field exists. |
| 4 | Degenerate split (1 child = parent restated) | worker re-emits parent to fake progress | **Structural gate**: ≥2 children, μ strictly shrinks, Jaccard<0.80, coverage≥dwc, unique ids, DAG acyclic. |
| 5 | Infinite re-decompose on compose failure | compose-fail mis-read as "too hard" | **FAIL taxonomy**: `CHECK_FAIL`(retry) / `COMPOSE_FAIL`(freeze, D12) / `DECOMP_FAIL`; `redecomp_count ≤ R`. |
| 6 | Unbounded cost/depth | "loops free" taken literally; no meter | **Meter structure, not loops**: `MAX_DEPTH/MAX_FANOUT/max_nodes` + per-root step/token budget (D8/D10). Leaf loops stay free. |
| 7 | DFS starves a cross-tree dependency | strict DFS; cross-links are inert `see_also` | **Blocking dep edge** (`needs(artifact)`), code-scheduled: gate emits `BLOCKED_ON(Y)`, Navigator services Y, resumes. No 35B auto-jump; cycle-check on `needs`. |

## What to build first

Minimal vertical slice proving the loop end-to-end (no DAG, no reduce, no decomposition yet):

1. **Node + tree.yaml loader** with referential-integrity + path-jail checks (load-time CODE).
2. **Gate 1 runner** for 4 checks only: `file_exists`, `json_field_in_range`, `grep_absent`, `all_children_done`. Verdict written by code; no-artifact ⇒ FAIL.
3. **`solve()` leaf-attempt path only**: activate → `propose` → `run` → `run_checks` → DONE | retry up to K → `BLOCKED(UNSOLVABLE_LEAF)`. Journal append each attempt.
4. **One hand-written 2-level tree** (`ai.rag` + the 5 leaves above, decomposition pre-baked by a human) so cursor/DFS/`all_children_done` closure runs without invoking `decompose()`.
5. **Per-root step budget (D10)** wired as the single backstop.

Proves: 4-cell context assembly, gate as sole verdict authority, no-artifact=FAIL, DFS cursor + parent-done-by-children. **Then** add Gate 2 (`accept_decomposition`) + real `decompose()` recursion, **then** `inputs`/`outputs` wiring + `reduce`, **then** detectors D4/D5 + content-addressed cache.

## Open questions

- **`scope_token_len` normalization** — tokenizer drift across `decomposer_version` could make μ's tiebreak non-comparable across versions. Pin a tokenizer in `decomposer_version`, or drop the tiebreak and make `done_when_count` the sole measure (cleaner well-order, but ties can stall)?
- **`criteria_coverage` semantics** — exact partition vs. superset? A child may legitimately need a scaffolding criterion the parent didn't list. Define coverage as "each parent criterion is implied by ≥1 child" rather than set-equality.
- **Metric-tightening across decomposition** — `weaker_than_ancestor` needs a partial order over checks (`range[0.8,1] ⊑ range[0.7,1]` is trivial; undefined across check *kinds*, e.g. child swapping `json_field_in_range` for `grep_matches`).
- **`reduce_op: worker` budget** — a worker-driven reduce can itself decompose; share the parent's step budget (risks starving leaves) or give it its own (risks unbounded compose cost)?
- **`needs` (cross-tree) vs `depends_on` (in-subtree)** — both code-scheduled, but `needs` can point anywhere in either root. Confirm the union graph stays acyclic under *live* decomposition (a new child could introduce a `needs` that closes a cycle mid-run).
- **K tuning** — flat `K=3`, or scale `K` with `dwc` (more criteria ⇒ more attempts before splitting)?
- **Human-in-the-loop latency** — in a fully-local unattended run, is there a degraded auto-mode (relax the *weakest* `done_when`, log it, continue) or is BLOCKED always terminal?
