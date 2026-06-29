---
name: hs-research:security-scan
description: Scan codebase for security issues — hardcoded secrets, dependency CVEs, injection/authz gaps, STRIDE+OWASP. Use before releases, after adding auth/payment/data, or for periodic audits.
category: research
license: AGPL-3.0
keywords: [security-scan, scan, codebase, security, issues, hardcoded]
when_to_use: "Use before releases, after adding auth/payment/data, or for periodic audits."
argument-hint: "[path|glob] [--secrets-only] [--deps-only] [--red-team] [--iterations N] [--fix] [--compliance <fw>]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-research:security-scan — security audit with threat model

Structured STRIDE + OWASP scan. Detects secrets, dependency CVEs, injection
vulnerabilities, and authz gaps. With `--red-team`, runs a 4-persona attacker
loop before summarizing. Threat-model-first: identify boundaries and assets
before searching for bugs.

**Does not** replace a pentest; **does not** perform runtime analysis; **does not**
audit infrastructure (reads only code + config tracked in git).

## When to use

- Before a release or major merge
- After adding auth, payment, or data-handling code
- Periodic review (monthly/quarterly)
- Compliance prep — SOC2 / GDPR / PCI-DSS / HIPAA gap-mapping
- When the `code-reviewer` agent raises a trust-boundary concern

## When NOT to use

- Purely cosmetic changes (CSS, copy)
- No code handling user input or sensitive data

## Modes & Flags

| Invocation | Behavior |
|---|---|
| `/hs-research:security-scan` | Full audit — STRIDE + OWASP + secrets + deps |
| `/hs-research:security-scan --secrets-only` | Scan secrets/credentials only |
| `/hs-research:security-scan --deps-only` | Dependency audit using the project's tool only |
| `/hs-research:security-scan --red-team` | 4 attacker personas → STRIDE/OWASP sweep |
| `/hs-research:security-scan --red-team --iterations N` | Red-team limited to N iterations |
| `/hs-research:security-scan --fix` | Audit → iteratively fix Critical/High (with guard) |
| `/hs-research:security-scan --compliance <fw>` | Map findings to SOC2/GDPR/PCI-DSS/HIPAA (references/compliance-frameworks.md) |
| `/hs-research:security-scan <path>` | Limit scope to a path/glob |

Flags can be combined: `--red-team --fix --iterations 10`. `--compliance` with no
framework maps all four.

## Workflow

```
1. Threat-model: identify assets + boundaries + attack surface (harness/rules/verification-mechanism.md)
2. Secret scan: grep patterns (references/secret-and-dependency.md) — exclude test/example/dist
3. Dep audit: run the project's audit tool (npm audit / pip-audit / equivalent)
4. [If --red-team] Persona loop: 4 attacker lenses (references/scan-dimensions.md)
5. STRIDE + OWASP sweep: references/threat-model.md → A01-A10 + S/T/R/I/D/E
6. Code pattern analysis: injection, authz, deserialization, SSRF (references/scan-dimensions.md)
7. .env exposure check: git ls-files .env* + .gitignore coverage
8. Severity ranking: Critical → High → Medium → Low → Info
9. [If --compliance] Map findings to framework controls (references/compliance-frameworks.md) → ## Compliance section
10. [If --fix] Iterative fix: fix 1 finding → guard (test/lint) → commit → next
11. Write report → plans/reports/security-scan-<date>.md
```

## Severity

| Level | Meaning | Fix priority |
|---|---|---|
| **Critical** | Immediately exploitable, data breach or RCE | Block release |
| **High** | Exploitable with moderate effort, large impact | This sprint |
| **Medium** | Hard to exploit, limited impact | Next sprint |
| **Low** | Theoretical risk, defense-in-depth | Backlog |
| **Info** | Best practice, no direct risk | Optional |

## Credential hygiene (required)

- **DO NOT** print real secret values in the report — mask as: `<REDACTED_TOKEN>`, `<REDACTED_PASSWORD>`
- Reject any finding containing an unmasked JWT (`eyJ…`), 32+ hex chars, or `AKIA`/`ASIA` prefix
- Do not auto-edit code in `--secrets-only` mode — report only and recommend rotation

## Boundaries

- DO NOT merge or deploy automatically; scan output is input — the fix decision belongs to the human.
- `--fix` only repairs confirmed Critical/High findings; commit pattern: `security: <short description>`.
- `--fix` stops early on guard failure — report actual status rather than continuing.
- Do not edit files outside `plans/reports/` (report) unless `--fix` is active.
- Findings require a `file:line` anchor or a reproduction command — no anchor → tag `[UNVERIFIED]`.
- On exit: absolute path of the report + unresolved questions.

## HARD-GATE (real wiring)

```
harness/install/git-pre-push-hook.sh    — transport-level gate; scrubs HARNESS_*
                                          env before judging; missing python3 →
                                          fail-closed; every push goes through here
                                          (including pushes via aliases/wrappers)

harness/hooks/gate_stage.py             — stage gate push|pr|ship|deploy; reads
                                          artifacts from disk; stage `push` requires
                                          artifact `verification` (stage-policy.yaml)

harness/data/stage-policy.yaml          — stage → artifact requirements config;
                                          stages pr/ship/deploy require verification
                                          + review-decision + plan-approval

harness/plugins/hs/agents/code-reviewer.md
                                        — agent that reviews trust-boundary / auth /
                                          data-leak / input-validation; security
                                          findings from code-reviewer feed into scan

plans/reports/                          — long-term storage for security-scan reports
```

Secrets detected by the pre-push hook represent the transport layer — this scan is
an earlier layer (pre-commit / on-demand). The two layers complement each other and
neither replaces the other.

## Workflow position

Typically run: before `hs:code-review` (scan provides security context) · before `hs:git` ship
Related: `hs:code-review` (security dimension) · `hs:fix` (fix findings) · `hs:plan` (schedule Medium/Low)
