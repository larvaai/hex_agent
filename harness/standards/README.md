# harness/standards/ — per-machine input

This directory receives the team's SHARED standards set when the harness is cloned onto a machine:

```
harness/standards/
  system-architecture.md   # system architecture the team follows
  code-standards.md        # shared code discipline (naming, testing, commits, ...)
```

The harness multi-user model: **one developer per machine, one clone, one harness** — no one shares files with anyone else. What keeps everyone moving in the same direction is these two standards files: hs:plan and hs:cook READ them before working, so plans and code on every machine follow the same architecture and the same discipline.

Missing file here → hs:plan stops and prompts you to load the standards before planning.

For this harness repo (self-hosting), the standards live at `docs/system-architecture.md` and `docs/code-standards.md` — copy (or symlink) them here when you want to run the full protocol as a target repo would.

## Structured standards tree

Beyond the two prose files above, the harness reads a structured standards tree to build the graph `rule → rule-group → STD-area → ARCH-goal → vision` (same shape as the product-spec graph, renamed to the standards domain). Flat layout:

```
harness/standards/
  vision.md                 # Engineering Vision (singleton, id VISION)
  STACK.md                  # tech-stack facts (singleton, id STACK)
  charter.md                # Architecture Charter — ARCH-G<n> goals, metrics REQUIRED
  areas/
    STD-<AREA>.md           # 1 file per standard area; rule-groups + rules declared
                            # inline in frontmatter (id STD-<AREA>-RG<n>-R<n>)
  templates/                # skeleton .md.tmpl for generate_standards_templates.py
  .snapshots/               # graph snapshots (machine-written, gitignored)
```

The `.md` files in this tree (vision/STACK/charter/areas) are per-machine input (gitignored like all other standards); only `templates/` and `README.md` are tracked.

Generate an artifact quickly via the generator (assigns parent-scoped id + renders tokens):

```bash
python3 harness/scripts/generate_standards_templates.py \
  --root . --type std_area --slug AUTH --write
```

Check the standards tree for consistency (dangling/orphan/cycle) — CI runs this automatically:

```bash
python3 harness/scripts/standards_strict_gate.py --root .   # exit 2 on error
```

The DEC ledger (`docs/decisions.md`) is also per-clone: sync + deduplicate numbers via git MR like any other tracked file (DEC number collision between two branches → renumber at MR).
