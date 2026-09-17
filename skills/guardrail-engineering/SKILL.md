---
name: guardrail-engineering
description: Use when you are building or auditing a guardrail/gate that is supposed to stop an agent (or a script) from doing something — file protection, command blocking, policy enforcement. Four rules for telling whether the guardrail actually guards, plus a regression harness to prove it.
---

# Guardrail engineering: how to tell whether your gate guards anything

Written after shipping a protection gate that looked correct, passed review, and
then got bypassed in three lines by an independent reviewer.

**The core asymmetry:** a gate that fails loudly is a bug report. A gate that fails
silently is a *false belief* — and a false belief is worse than no gate at all,
because you stop checking. Almost everything below is a consequence of that sentence.

---

## Rule 1 — Know which class of violation you are defending against

Text-pattern matching (regex over the command or the script body) can stop
**accidental** violations. It cannot stop **deliberate** bypasses by a determined
actor. These are different problems and they need different answers.

Real numbers from our own gate (a memory-file protection hook, matched on
`write_file | patch | terminal`):

| | count |
|---|---|
| accidental direct writes blocked | yes, reliably (that was the actual risk) |
| deliberate bypasses found by a reviewer in 20 minutes | 16 |
| false positives that blocked legitimate work | 6 |

Bypasses that walked straight through included: assigning the path to a variable
first, `os.path.join`, `open(path, mode='w')` with a keyword argument,
`Path(p).write_text()`, `shutil.copytree`, `os.write`, `pandas.to_csv`, and one
`sed -i` inside a subprocess string.

**Do:** write down which class you're defending against, and make the gate's
documentation say so. "Stops accidental writes" is an honest, useful claim.
"Blocks writes to file X" is not, and someone will trust it and get burned.

**Don't:** add a twentieth pattern. Coverage does not converge; every round of
patching produced a new class of miss in our experience.

---

## Rule 2 — Prevention is UX; detection is truth

Keep the preventive gate: stopping damage *before* it happens is worth a lot, and
for the accidental class it works. But pair it with **post-hoc verification of the
artifact**:

- hash the protected files after every tool call;
- if a hash changed and the tool that just ran is not an approved writer → that is
  a finding, regardless of what any pattern matcher thought.

This inverts the usual approach and it's strictly better for one reason: it does
not need to understand *how* the write happened. Variable indirection, reflection,
a subprocess, another process entirely — irrelevant. Observe the artifact.

Implementation notes from ours (~120 lines total, no dependencies):

- store `{path: sha256}` in a small state file; compare after each call;
- whitelist the legitimate writers explicitly (`memory` tool, the user, a sanctioned
  CLI) — anything else that changed the file is suspicious;
- on detection, don't try to be clever: arm an alert and block **the next** tool call
  **once**, with a message naming which tool ran and which file changed. One loud
  interruption your operator actually sees beats a log line nobody reads.

Related discipline (same principle, different surface): when you want a review of
something, hand over the **artifact and the contract**, not your reasoning. A
reviewer who reads your rationale grades your rationale.

---

## Rule 3 — No silent failures: pick a failure mode and make it visible

Every gate will eventually fail (crash, timeout, missing dependency, config not
reloaded). Decide what happens, write it down, and make it observable:

- **fail-open** (failure = allow): right for convenience gates, dangerous for
  protection gates.
- **fail-closed** (failure = block): right for protection gates, but then a broken
  gate stops all work — so it must be loud and self-announcing.

Whichever you choose, three things must hold:

1. **It must be logged.** A gate that dies must leave a trace. Ours originally exited
   non-zero with an empty log — indistinguishable from "no violation found".
2. **It must fail in an unmistakable shape.** Returning a normal-looking value is
   the worst option. Our context-budget gate blocks tool calls by returning an error
   *string* that reads like a tool result; during research, an agent read it as a
   transient failure and kept going. A guardrail that changes behaviour while looking
   like ordinary output is a silent failure wearing a costume.
3. **"Is it actually running?" must be answerable.** Configuration that is read at
   process start is not configuration that is in effect. We lost a day to hooks that
   were correctly declared in config but never registered, because registration
   happens at startup and the long-running process had loaded the older config —
   with no error and no log line. Ship a health check (`<tool> doctor`-style) that
   asserts: registered, allowlisted/permitted, script hash matches, and the gate
   actually fires on a canary.

---

## Rule 4 — The guardrail needs a regression harness, and the harness needs a canary

A gate without tests is a comment. Keep it small:

- one assertion per rule;
- two sample classes per rule: **accidental** (must block) and **deliberate**
  (must at least be detected afterwards);
- assert on the *effect*, not the intent: for a preventive gate, that the call is
  refused; for a detecting gate, that the state file/alert/log changed.

Two properties that are easy to forget:

1. **Test the wiring, not just the logic.** Our self-test proved the script was
   correct while the hook was not registered at all. Assert the configuration too
   (matcher contains the expected tool, allowlist entry exists, state file is
   watched).
2. **Canary the harness.** Run it once against a deliberately gutted copy of the
   gate (always-allow, and always-deny). If the suite still passes, the suite tests
   nothing. `scripts/guardrail_regression.py --mutate` does exactly this.

---

## Using the harness

```bash
# cases.json describes your gate; see scripts/cases.example.json
python3 scripts/guardrail_regression.py --cases cases.json --cmd 'python3 /path/to/gate.py'
python3 scripts/guardrail_regression.py --cases cases.json --cmd '...' --mutate
```

The harness speaks the simplest possible contract, so it fits most hook systems:
**one JSON object on stdin, exit code 2 = block, exit 0 = allow, anything else = error.**

---

## The one-line version

> Gates that stop accidents are worth having; gates that claim more than that are
> lying to you. Verify the artifact, never fail silently, and canary the tests that
> check the gate.
