# E13 — Software Factory (PRD, draft)

Phase: P4 · Features: F19

## Problem
Prompt sản phẩm lớn cần được biến thành **spec có thể trace** trước khi code, thay vì code thẳng.

## Goal
Pipeline spec: prompt → vision → BRD → PRD → epics → acceptance → domain → architecture/ADR → implementation-spec → code-handoff, xuất **artifact file** ở mỗi stage.

## Scope — In
- Các stage agent (E09 roles) sinh artifact đánh số (`00_vision.md` ... `10_implementation_spec.md`).
- Validator + critic stage (kiểm spec trước khi sang domain/code).
- Code-handoff packet để đưa sang E10 coding runtime.
- Lưu `var/factory_runs/<run_id>/`.

## Scope — Out
- Thực thi code (E10); review gate người (E16).

## Dependencies
E09, E10 (handoff), E12 (được supervisor gọi cho product-build intent).

## Success metrics / Exit
- Sinh đủ chuỗi artifact + `implementation_spec.md` + handoff packet; stages có trong trace.
- Spec fail validator → dừng trước khi sang code.

## Open questions
- Bao nhiêu tự động vs chèn review gate người (E16) giữa các stage?
