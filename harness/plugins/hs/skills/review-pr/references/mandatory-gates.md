# review-pr — mandatory gates

Run these before the verdict (step 3 of the workflow). They produce findings even when
the code itself is correct.

## Duplicate / prior-work gate

Extract 3–7 search terms from the title, changed files, and new symbol/route/config names.
Search for an existing implementation:

```bash
gh pr list --state all --search "<terms>" --json number,title,state,mergedAt,url
gh issue list --state all --search "<terms>" --json number,title,state,url
git log --all --grep="<terms>" --oneline -20
```

Exclude the current PR. Also grep the codebase for touched symbols/routes/config keys.

- A merged PR already satisfies the outcome → **Important**: request closing or retargeting this PR.
- An open PR overlaps materially → **Important**, unless this PR is the chosen successor and says why.
- Partial prior art → check the PR extends it instead of forking a parallel implementation.

## Strategic-necessity gate

Review as the product owner, not only as a code reviewer: does the PR create clear value
(user outcome, roadmap alignment, security, reliability, maintainer-toil reduction)? Bug/
security/cleanup fixes count — not every PR must make money.

- Correct but unnecessary, duplicates roadmap work, or expands scope away from the product
  direction → **Important** product-risk finding.
- Value depends on a business call the code cannot answer → list it under open questions.

(Project standards are already loaded in workflow step 2 — no separate standards gate needed.)
