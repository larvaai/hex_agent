# E07 — Acceptance Criteria (draft)

## S07.1 declared tools
- Given a skill, When loaded, Then its Allowed/Forbidden sections reference canonical `server.tool` names (lint can verify they exist in the registry).

## S07.2 contract mode
- Given `mode="contract"`, When building the prompt, Then only frontmatter description + Allowed + Forbidden are injected (text before `## Steps`).

## S07.3 full mode
- Given a skill chosen for the active step, When loaded with `mode="full"`, Then Steps + Report are included.

## S07.4 derive allowlist
- Given a role with skills S, When deriving tools, Then role `allowed_tools` ⊇ union of tools declared by S (+ role-core tools).

## S07.5 frontmatter validation
- Given a SKILL.md without `name` or `description`, When loaded, Then a clear ValueError is raised.
