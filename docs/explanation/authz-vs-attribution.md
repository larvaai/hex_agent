# Authz ≠ attribution

> Epic E21 · doctrine for the control plane. Predicates: [`control/authz.py`](../../control/authz.py).
> Ported from the harness "three truths" ([`harness/rules/harness-contract.md`](../../harness/rules/harness-contract.md)) — **with the conclusion inverted**.

## The borrowed distinction, and why we invert it

The harness states three truths: *gate ≠ auth*, *actor ≠ authz*, *config ≠ proof*. It can afford a
spoofable actor because it is a **collaboration** tool — its job is to raise the cost of drift, not to
stop an adversary.

hex_agent is not that. [`control/permission.py`](../../control/permission.py) carries
`can_modify_permissions` — a real **escalation surface**: an agent that can edit permissions can grant
itself anything. So we keep the harness's *distinction* and **reverse its conclusion**: the authz
decision must live where the agent's output cannot reach it.

## (a) `issued_by` / `Actor` = attribution, not authority

[`RuntimeCommand.issued_by`](../../control/commands.py) and `Actor` ([`control/events.py`](../../control/events.py))
record **who claims to have acted**. The issuer fills them in. They are for **audit/attribution** — a
trail, not a credential. A command that says `issued_by: {type: human, user_id: alice}` proves nothing
about whether *alice* may do the thing; it only logs the claim.

## (b) The authz decision lives at the checkpoint

Authority is `requires_permission` ([`control/command_registry.py`](../../control/command_registry.py)
`:56`) resolved against the **holder's** `Permission` at a checkpoint boundary — never against the
issuer's self-description. The command-type registry declares the required permission name; the runtime
resolves it against the live `Permission` when the command is about to apply, at a safe point.

## (c) Permission-edit is human-gated even under trust-O

`trust-O` (GLOSSARY) lets an O-issued command **bypass** `requires_permission` — accepted because O is
the trusted actor inside structural rails (catalog-bound, scope-narrow, authority gate). The
[authority gate](../../supervisor/graph.py) (`graph.py:142-147`) blocks assignment to agents outside the
roster — but it does **not** block granting capability.

That leaves one hole the rails don't cover: an agent rewriting its own permission. So the doctrine carves
out an exception to trust-O: **`UpdateAgentPermission` → `can_modify_permissions` always requires a human
`RuntimeCheckpoint`** ([`control/checkpoint.py`](../../control/checkpoint.py)), even when O issued it. A
permission-edit is not self-grantable. `command_needs_human_checkpoint()` is the predicate that decides this.

## (d) Where enforcement attaches (deferred — named, not built)

`command_bridge` / `pending_commands` do **not** exist on this branch (DEC-7). So this round ships the
**doctrine and the predicates**, not the wiring. When the bridge lands it **MUST** call
`control.authz.command_needs_human_checkpoint()` (and, for direct patches, `is_permission_escalating()`)
**before** applying `UpdateAgentPermission` — routing an escalating edit to a human `RuntimeCheckpoint`
rather than auto-applying. Naming the call-site keeps `control/authz.py` an invariant-with-a-consumer,
not a speculative API.

## Known gap — boundary of the predicate

`is_permission_escalating()` inspects only the boolean `can_*` flags. Widening `allowed_tools` is **not**
caught here — that path is constrained instead by §1.4: `SessionFactory.create_child()` forces child
scope ⊆ parent scope ([`docs/code-standards.md`](../code-standards.md) §1.4). Do not read these predicates
as "full authz"; they pin the capability-flag escalation surface, and §1.4 pins the scope-widening one.
