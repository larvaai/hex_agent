# Validation — checklist and grep patterns

## Grep clean check (required before DONE)

```bash
# Get patterns from TestOwnershipBoundary in test_bug_class_invariants.py
# then run: grep -rnE '<pattern>' harness/plugins/hs/skills/<name>/
python3 -m pytest harness/tests/test_bug_class_invariants.py::TestOwnershipBoundary -q
```

Patterns checked: dot-claude path refs + external brand names + old invoke prefixes + dev-trace labels.
For full pattern details see `harness/tests/test_bug_class_invariants.py` -> `banned` regex.
Grep output **must be empty** and pytest **must be green** before reporting DONE.

## Quick checklist

### Frontmatter
- [ ] `name: hs:<name>` — matches dir name (segment after `/`)
- [ ] `description` <=200 chars, has trigger phrase, third-person
- [ ] `user-invocable: true`
- [ ] `metadata.owner: harness`
- [ ] `metadata.compliance-tier` correct tier

### Size and structure
- [ ] SKILL.md <=150 lines (harness standard; upstream source allows <=300)
- [ ] Each references file <=300 lines
- [ ] No content duplicated between SKILL.md and references (no-duplication)
- [ ] Dir name = kebab-case, matching `name:` suffix

### Thin-core blocks
- [ ] Has **Boundaries** block (what NOT to do, what is returned on completion)
- [ ] Has **HARD-GATE** or **Backing** block (points to a real file, not phantom)
- [ ] Process with numbered steps
- [ ] Quick reference table pointing to drawers

### Backing-or-cut
- [ ] Every directive has named backing (gate/script/rule/schema)
- [ ] Directives without backing -> cut or moved to advisory in references

### Brand / path leaks (see TestOwnershipBoundary)
- [ ] No path references of the form `dot-claude/skills/` or `dot-claude/hooks/` (only lines with `# learn:` are whitelisted)
- [ ] No external brand names (source toolset name)
- [ ] No old invoke prefix (namespace `ck` instead of `hs`) — all frontmatter `name:` and invocations must use the `hs` namespace
- [ ] No dev-trace labels of the form DEC followed by digits

### Catalog resolve
- [ ] `load_catalog()['owned']` contains the new dir after file creation

```bash
python3 -c "
import sys; sys.path.insert(0, 'harness/scripts')
from catalog import load_catalog
c = load_catalog()
print('owned:', sorted(c['owned']))
"
```

### STANDARDIZE row
- [ ] Line added to `docs/STANDARDIZE.md`:

```
| ADAPT | hs:<name> skill (native thin-core + references) | <source> (origin, MIT) | harness/plugins/hs/skills/<name>/ | <notes> | grep-clean invariant + SKILL.md |
```

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| Skill not in `owned` | `name:` has wrong prefix or wrong dir | Change to `name: hs:<dir>` matching the directory name |
| Grep finds old invoke prefix | Copied from upstream source without renaming | Change to `/hs:X` and `name: hs:X` in all files |
| Grep finds dot-claude path ref | Path referenced instead of skill name | Replace with `hs:<name>` |
| SKILL.md > 150 lines | Too much detail in the core | Move to references drawer |
| Phantom backing | No real file referenced | Find a real gate/script/rule or cut the directive |

## Validate mode

When using `hs-create:skill-creator validate`:

1. Read the target skill's SKILL.md
2. Run the grep clean check
3. Check `load_catalog()['owned']`
4. Count lines in SKILL.md and each references file
5. Report pass/fail for each checklist item above
6. Do not edit files — report only
