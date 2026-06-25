# E06 — MCP Tool Layer & Safety (PRD, draft)

Phase: P2 · Features: F09, F10

## Problem
Cần ranh giới tool "một cửa" + **một chokepoint an toàn**. Repo cũ: guard rải rác mỗi server, và spawn process MỚI mỗi call (overhead).

## Goal
Một client tool: `resolve → validate schema → policy → execute(persistent session) → envelope`; sandbox path; policy tập trung (git-mutation block, terminal argv-only, docker opt-in).

## Scope — In
- `call_tool(name, args)`: alias/`server.tool` resolve, validate args, policy check, gọi, chuẩn hóa envelope.
- Path-jail: `resolve()` + `is_relative_to(workspace)` (chống `../` + symlink).
- Policy chokepoint: chặn git mutation (env opt-in), terminal chỉ `argv` + risk metadata, docker mutation opt-in.
- **Persistent session** theo server (không spawn mỗi call); cân nhắc in-process cho tool Python nội bộ.

## Scope — Out
- Skills (E07), RAG (E08).

## Dependencies
E01 (registry/envelope). Dùng bởi E05/E10.

## Success metrics / Exit
- Ghi `../../etc` → bị chặn "outside workspace".
- `git_commit` → policy_blocked; `terminal` chặn shell/lệnh phá hủy.
- Session tái dùng (đo: không spawn lại mỗi call).

## Open questions
- In-process registry cho tool Python nội bộ vs MCP stdio cho external — ranh giới ở đâu?
