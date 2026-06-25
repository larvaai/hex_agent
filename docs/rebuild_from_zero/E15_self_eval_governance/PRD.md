# E15 — Self-eval & Governance (PRD, draft)

Phase: P4 · Features: F21

## Problem
Cần biết flow lớn có thực sự tốt hơn simple answer không, và **không để hệ tự ý sửa mình**.

## Goal
Harness tự đánh giá: simple baseline + blind evaluator + flow observer + **critical auditor (bắt multi-agent theater)** + trace health + **evolution decider proposal-only** (cần người duyệt).

## Scope — In
- Luôn có simple-answer làm baseline; blind evaluator chấm A/B/C **ẩn tên nguồn**.
- Flow observer (chất lượng tiến trình), trace health (lặp/JSON fallback/loop).
- Critical auditor: phát hiện phối hợp thừa/lãng phí.
- Evolution decider: đề xuất thêm/bớt/sửa agent/flow/skill/lens — **không tự áp dụng**, cần approve (nối E16).

## Scope — Out
- Tự động apply thay đổi (cấm theo thiết kế).

## Dependencies
E04 (trace), E10 (flow), E16 (approve).

## Success metrics / Exit
- Đánh giá mù (không lộ nguồn); phát hiện theater; mọi proposal cần người duyệt.
- Có chỉ số so "flow lớn vs simple".

## Open questions
- Định nghĩa metric "đáng giá" để chấp nhận flow lớn?
