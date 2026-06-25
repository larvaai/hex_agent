# E16 — Human Review Gate (PRD, draft)

Phase: P4 · Features: F23 (✨ mới — repo cũ chưa có UI gate)

## Problem
Hệ có nhiều agent nhưng **thiếu chốt người-trong-vòng-lặp** để duyệt plan/diff trước hành động nguy hiểm (học từ Plannotator).

## Goal
Một gate: review **plan** trước khi chạy và **diff** trước khi commit; approve/deny/annotate; feedback có cấu trúc chảy lại agent. Bắt buộc trước hành động nguy hiểm và trước khi update skill/lens.

## Scope — In
- Plan gate: hiển thị plan artifact → người annotate/approve/deny → feedback về agent.
- Diff gate: xem diff thay đổi chưa commit → annotate theo dòng → feedback.
- Bắt buộc trước: sửa nhiều file / refactor lớn / đụng kiến trúc / update skill|lens (E15).
- Tích hợp inbox user-agent (E17) + dashboard (E18). Cân nhắc dùng thẳng Plannotator.

## Scope — Out
- Cơ chế sinh plan (E13) / proposal (E15).

## Dependencies
E17 (feedback inbox), E18 (UI), E13/E15 (đối tượng review).

## Success metrics / Exit
- Gate chặn tới khi có quyết định; annotation chảy lại agent dạng cấu trúc.
- Hành động nguy hiểm không chạy nếu chưa approve.

## Open questions
- Dùng Plannotator (local, open-source) hay build gate tối giản trên dashboard?
