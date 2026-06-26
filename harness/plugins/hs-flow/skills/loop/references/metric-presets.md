# Metric presets — Direction / Noise / Guard rubric

A loop optimizes ONE numeric metric across iterations. Every metric declares three
properties so the loop can read its trend honestly:

- **Direction** — is `lower` better (errors, ms, bytes) or `higher` better (coverage,
  accuracy)? The loop cannot tell improvement from regression without this.
- **Noise** — `low` = deterministic, trust a single run; `high` = varies run-to-run
  (latency, accuracy), take 3–5 runs and compare medians, never one sample.
- **Guard** — a pass/fail check that MUST stay green while the metric moves. Optimizing
  the number while the guard breaks (coverage up, tests failing) is a false win.

## Presets (harness / Python stack)

| Metric | Command (prints one number) | Direction | Noise | Guard |
|---|---|---|---|---|
| Test coverage % | `pytest --cov=src --cov-report=term-missing -q \| grep TOTAL \| awk '{print $NF}' \| tr -d '%'` | higher | low | `pytest` |
| Lint errors | `ruff check src --output-format=json \| python3 -c "import json,sys;print(len(json.load(sys.stdin)))"` | lower | low | `pytest` |
| Type errors | `mypy src --ignore-missing-imports 2>&1 \| tail -1 \| awk '{print $1}'` | lower | low | `pytest` |
| Lines of code | `find src -name '*.py' \| xargs wc -l \| tail -1 \| awk '{print $1}'` | lower | low | `pytest` |

Other stacks (Node/Go/Rust, latency, bundle size) follow the same shape — the rubric is
the portable part; the command is per-project.

## Custom metric — template + rules

```bash
# Print exactly one numeric value as the last stdout line; exit 0 on success.
YOUR_MEASURE_COMMAND | YOUR_EXTRACT_COMMAND
```

| Rule | Detail |
|---|---|
| One number | stdout's last line is a bare integer/float — nothing else |
| Exit code | 0 = valid measurement; non-zero = crash (logged, iteration discarded) |
| Runtime | under ~30s; sample expensive workloads rather than running them whole |
| Determinism | if it varies run-to-run, set noise `high` and average 3–5 runs |
| Units | consistent for the whole loop; never change units mid-run |
| Direction | declare `lower` or `higher` explicitly — never leave it implicit |

A metric without a guard is a metric you can game. Pair every optimization target with the
test that must not break while you chase it.
