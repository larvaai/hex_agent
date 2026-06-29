# When visuals help

This is the decision gate — read it before generating any diagram.
A visual is only justified when it enables faster understanding than prose.

## Visual HAS VALUE when

| Situation | Appropriate diagram type |
|---|---|
| Multiple components interacting in time order | Sequence diagram |
| Data flowing through multiple layers/services | Data-flow / flowchart |
| Module structure and dependencies | Architecture diagram |
| Before/after change (refactor, migration) | Before-after side-by-side |
| Phases of a plan or workflow | Flowchart with gates |
| Explaining an abstract concept (state machine, lifecycle) | State diagram / flowchart |

## Visual HAS NO VALUE when

- There are <=2 components -> prose is sufficient.
- The content is simply a list of files/functions -> use a bullet list.
- The change is a single simple logic line -> prose + code snippet.
- The diagram only repeats the code without adding abstraction -> skip it.
- The topic has not been read from real code -> STOP; read the code first.

## Decision

```
Are there >=2 COMPLEX interacting components that need explanation?
  No  -> write prose, no diagram needed.
  Yes -> choose a diagram type from the table above -> continue.
```

If unsure -> ask via `AskUserQuestion`:
"I can explain this in plain text. Would you like a diagram as well?"

## Output location rule

- Visual tied to an active plan -> `plans/<slug>/visuals/`
- Standalone visual -> `plans/visuals/`
- Durable architecture visual -> `docs/` (via `hs-mem:docs`)
- Do NOT create anywhere else (CLAUDE.md rule #5).
