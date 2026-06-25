# E06 — Acceptance Criteria (draft)

## S06.1 resolve + envelope
- Given alias `write_file`, When called, Then it resolves to the canonical tool and returns an envelope with `server`/`tool`.

## S06.2 path-jail
- Given path `../../etc/x`, When a filesystem tool is called, Then it returns `ok=false` "outside workspace"; And a symlink pointing outside is also rejected (resolve-then-check).

## S06.3 git mutation
- Given no opt-in env, When `git.git_commit` is called, Then `policy_blocked=true`; And with the opt-in env set, it is allowed.

## S06.4 terminal argv-only
- Given `terminal_run` with a shell string or destructive command, When called, Then it is blocked; And every result carries `security_risk`.

## S06.5 order of checks
- Given an invalid-schema call, When executed, Then it returns a schema error WITHOUT spawning/contacting the server.

## S06.6 persistent session
- Given two sequential calls to the same server, When executed, Then the underlying session/process is reused (no second cold start) — measured by timing/instrumentation.
