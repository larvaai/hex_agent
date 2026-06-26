---
phase: {{NUM}}
title: "{{PHASE_TITLE}}"
status: pending
plan: {{PLAN_ID}}
created: {{CREATED}}
---

# Phase {{NUM}} — {{PHASE_TITLE}}

## Overview
TBD — phase này làm gì, vì sao, phụ thuộc phase nào.

## Files
TBD — **Create** / **Modify** từng path (qua staging-cp nếu file guarded).

## TDD
- **Tests-before (RED)** TBD — test gì fail trước.
- **Implement** → xanh. **Regression** `pytest -q` + `verify_install --strict`.
  `git add` shipped files TRƯỚC `build_manifest.py`, rồi `git add` manifest.

## Success
- [ ] TBD — tiêu chí đo được (output thật, không "commit là xong").

## Risks
TBD — rủi ro phase + cách xử.
