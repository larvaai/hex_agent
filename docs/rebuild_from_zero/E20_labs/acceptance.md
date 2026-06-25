# E20 — Acceptance Criteria (draft)

## S20.1 single entrypoint
- Given a registered lab, When `app lab <name>` runs, Then the lab's script executes with forwarded args.

## S20.2 mock offline
- Given `--mock`, When a lab runs with no LLM/network, Then it completes and writes structured output.

## S20.3 evidence-bounded answer
- Given a repo question, When the repo-understanding lab answers, Then claims come only from the context pack (no invented facts), with unknowns stated.

## S20.4 defect detection
- Given a repo with BOM/parse issues, When scanned, Then those files are reported as parse errors.

## S20.5 shared utils
- Given the labs, When inspected, Then they import shared discipline/llm/tools (no copy-paste of core logic).
