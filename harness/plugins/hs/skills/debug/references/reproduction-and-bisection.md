# reproduction-and-bisection — reproducing failures and finding the causing commit

Load when: the `--bisect` flag is used, or it is unclear which commit caused the regression.

## Stable reproduction first

Before bisecting, the failure must be reproduced consistently:

1. Record the exact steps to trigger the failure.
2. Run ≥ 3 times to confirm it is not flaky.
3. Cannot reproduce → add instrumentation (`instrumentation.md`) to collect more data.

**Do not bisect a flaky failure** — results will be misleading.

## git bisect — find the commit that caused the regression

Use when you know: "commit A works, commit B fails, but it is unclear which intermediate commit is the cause."

```bash
git bisect start
git bisect bad                    # current commit: failing
git bisect good <commit-hash>     # known-good commit

# Git automatically checks out the midpoint commit
# Run tests / verification
python3 -m pytest harness/tests/test_feature.py -q

git bisect good   # if it passes
git bisect bad    # if it fails

# Repeat until git reports the first bad commit
git bisect reset  # end session, return to HEAD
```

Automate with a script:
```bash
git bisect run python3 -m pytest harness/tests/test_feature.py -q
```

## Finding the test that pollutes others (test isolation)

When a test passes in isolation but fails when run with the suite → shared state is leaking:

```bash
# Run tests one by one, stop when the polluter is found
# Adjust the glob pattern to match the project's runner
python3 -m pytest harness/tests/ -q --tb=no -p no:randomly 2>&1 | grep -E 'FAILED|ERROR'

# Or use pytest-randomly with a fixed seed to reproduce
python3 -m pytest harness/tests/ -q -p randomly --randomly-seed=1234
```

Pattern for finding the polluter: run progressively smaller subsets (manual binary search) until
the test causing the state leak is isolated.

## Failing repro test — required output of hs:debug

After the root cause is identified, write a test that reproduces the failure
(rule `harness/rules/tdd-discipline.md`):

```python
# Python/pytest example — test must FAIL before the fix
def test_reproduces_root_cause():
    """Reproduces: <one-line description of root cause>."""
    # Arrange: set up the conditions that cause the bug
    # Act: trigger the failure
    # Assert: confirm current wrong behavior
    #         (this test MUST fail to prove the root cause)
    assert result == expected_wrong_value  # <- intentional failure
```

Checklist before handing off to `hs:fix`:
- [ ] Test fails intentionally when run with `python3 -m pytest <path> -q`.
- [ ] Test is as simple as possible — does not test unrelated behavior.
- [ ] Test name describes the root cause, not just the symptom.
- [ ] Test path is recorded in the report at `plans/reports/<slug>-debug-report.md`.

## Connection to hs:fix

The failing repro test is the **primary input** for `hs:fix`:

```
/hs:fix <path-to-failing-test>
```

`hs:fix` implements the fix to turn the test from red to green, then runs the full suite.
