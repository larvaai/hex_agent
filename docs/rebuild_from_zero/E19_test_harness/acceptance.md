# E19 — Acceptance Criteria (draft)

## S19.1 grouped runner
- Given a group name, When `run_cases --group <g>`, Then matching cases run and a summary + per-case logs are written under `var/test_runs/<ts>/`.

## S19.2 offline smokes
- Given no LLM/network, When deterministic smokes run, Then they pass (kernel, discipline, tools policy, graph compile).

## S19.3 dev checks
- Given `dev_checks --quick`, When run, Then a curated fast subset runs and reports PASS/FAIL with timings.

## S19.4 capability suite
- Given `capability_suite`, When run, Then it executes the deterministic capability checks and exits non-zero on any failure.

## S19.5 AC → test
- Given an epic with acceptance criteria, When the harness is built, Then ≥1 test asserts each core AC (e.g. path-jail block, git-mutation block, finish-gate).
