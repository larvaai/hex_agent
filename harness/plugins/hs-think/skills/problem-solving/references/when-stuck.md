# when-stuck — flowchart dispatch

Use when the type of block is unclear. Match symptoms to a technique.

## Flowchart

```
STUCK
│
├─ Complexity escalating? Same thing 5+ ways? Special cases growing?
│  └─→ simplification-cascades.md
│
├─ Conventional solutions not enough? Breakthrough needed?
│  └─→ collision-zone-thinking.md
│
├─ Same problem recurring in many places? Reinventing wheels?
│  └─→ meta-pattern-recognition.md
│
├─ Solution feels forced? "There is only one way"?
│  └─→ inversion-exercise.md
│
├─ Not sure it will scale? Edge cases unclear?
│  └─→ scale-game.md
│
└─ Broken code / failing test / wrong behavior?
   └─→ hs:debug (not this skill)
```

## Symptom -> technique table

| Type of block | Specific symptoms | Technique |
|---|---|---|
| Complexity escalating | 5+ implementations, growing special cases, ballooning if/else | simplification-cascades.md |
| Creativity needed | Conventional solutions not enough, every direction is incremental | collision-zone-thinking.md |
| Recurring pattern | Same problem in many places, deja vu, reinventing wheels | meta-pattern-recognition.md |
| Forced by assumption | "Must do it this way", unable to question the premise | inversion-exercise.md |
| Scale uncertainty | Limits unknown, "should scale fine" with no evidence | scale-game.md |

## When no technique resolves the block

1. **Reframe the problem** — is the right problem being solved?
2. **Reduce scope** — solve a smaller version first
3. **Question constraints** — are the constraints real or assumed?
4. **Combine techniques** — see the Combinations table in SKILL.md
5. **Escalate** — use `hs-think:brainstorm` to explore multiple directions with an agent
