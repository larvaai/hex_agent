<!-- generated: plugin-readme -->

# hs-devops

SDLC harness DevOps skills: hs-devops:deploy / devops / web-testing / agent-browser / chrome-profile.

**Default:** opt-in. Enable with `hs-cli components --enable devops` (or choose it at install time).
**Version:** 1.0.0

## Skills (5)

| Invoke | Purpose |
|---|---|
| `/hs-devops:agent-browser` | Automate browsers and apps with agent-browser. |
| `/hs-devops:chrome-profile` | Target a real Google Chrome profile for browser automation through Chrome DevTools MCP. |
| `/hs-devops:deploy` | Deploy projects to any platform with auto-detection. |
| `/hs-devops:devops` | Deploy to Cloudflare (Workers, R2, D1), Docker, GCP (Cloud Run, GKE), Kubernetes (kubectl, Helm). |
| `/hs-devops:web-testing` | Web testing with Playwright, Vitest, k6. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
