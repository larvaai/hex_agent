# Deploy — Post-Deploy & Troubleshooting

### 6. Post-Deploy: docs/deployment.md

After first successful deploy, create `docs/deployment.md`:
```markdown
# Deployment
## Platform: [name]
## URL: [production-url]
## Deploy Command: [command]
## Environment Variables: [list]
## Custom Domain: [setup steps if applicable]
## Rollback: [instructions]
```

On subsequent deploys, update if config changed.

### 7. Troubleshooting

1. Check error output, attempt auto-fix for common issues
2. If unresolvable → activate `/hs-devops:devops` skill
3. Update `docs/deployment.md` with troubleshooting notes
