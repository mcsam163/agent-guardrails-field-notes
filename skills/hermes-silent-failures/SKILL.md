---
name: hermes-silent-failures
description: Use when a self-hosted Hermes Agent reports success while something quietly did not happen — a hook that never fires, a bundled skill that stopped receiving updates, staged memory writes that vanished. All three are documented upstream; this is what they look like in practice and the exact checks that catch them.
---

# Three ways a Hermes Agent stays quiet while doing nothing

*Verified on Hermes v0.21.x, September 2026.*

**Read this first: all of this is documented upstream.** We are not claiming to have
found undocumented behaviour. We are claiming the opposite, and it is the whole point of
this file: the documentation is correct, we read it, and we still lost time to each of
these — because when they happen the system does not look broken. It looks fine.

That is the shared failure shape: **success is reported, nothing happened, and nothing
tells you.** For each one below: the symptom, the exact commands, and the trap that
makes it easy to miss even when you know the rule.

---

## 1. A configured hook is not necessarily a running hook

**Documented in** `user-guide/features/hooks.md` — the "non-TTY" note and the
allowlist/consent section. **Still happens**, because the config file is the only part
you look at.

**Symptom.** You add a hook, restart, everything "works" — and that hook never fires.

**Checks.**
```bash
hermes hooks list          # shows consent state per hook; look for ✗ not allowlisted
hermes hooks doctor        # exec bit, allowlist, mtime drift, JSON validity, run time
grep -a 'not allowlisted' ~/.hermes/logs/errors.log
```

**The trap.** Consent prompts need a TTY. If your gateway restarts non-interactively
(service manager, a chat slash-command, a supervisor), there is nobody to answer, and a
newly added hook is *skipped* rather than queued. The config looks right the entire time.

**Related trap, same family:** the allowlist stores the approved command string plus the
script's **mtime** — not a hash. Edits to the script are therefore trusted silently. Read
`doctor`'s "modified since approval" line as *"this gate is not running the code you
approved"*, not as cosmetic noise.

**Do.** After every restart, assert the effect, not the intent: allowlisted ✔,
no mtime drift ✔, and a canary call that actually produces the hook's output.

---

## 2. Editing a bundled skill freezes it

**Documented in** `user-guide/features/skills.md` (a changed bundled skill is treated as
user-modified and skipped by updates).

**Symptom.** Months later your copy of a shipped skill is missing upstream fixes. The
update ran, and printed something you scrolled past.

**Checks.**
```bash
hermes skills list-modified     # bundled skills you have edited
hermes skills diff <name>       # your copy vs stock
hermes skills reset <name>      # clears the modified flag so updates apply again
```

**The trap.** It is silent at the moment of the edit — the moment you would care — and
only visible later, in the output of a routine update, as a count of kept files.

**Do.** Treat bundled files as read-only source. If you want the content, copy it into
your own skill, then `reset` the bundled one.

---

## 3. Staged memory writes we lost — an unresolved observation

This one is different from the two above, and we are labelling it accordingly: **we
observed the symptom and could not reproduce a mechanism.**

**What we saw.** With the staged-write queue enabled (`memory.write_approval`, a
non-default memory provider in front), seven staged records disappeared between being
queued and being reviewed. No error surfaced to the operator.

**What we could not reproduce.** Re-running the approve path on v0.21.x with an
unparseable record did *not* delete it, and did not report success:

```
--- /memory approve all output ---
Approved 0 memory write(s).
Failed:
  dc52ab25: Unknown staged action 'None'.
pending after : ['dc52ab25.json']      RECORD KEPT? True
```

So our working theory ("the applier deletes what it cannot parse") is **wrong for this
version**, or applies to a path we did not hit. The loss was real; the mechanism is not
proven.

**The most plausible neighbour we found (not proven).** Upstream #73297 — "pending memory
write lost across reset". In the version we run, the flush lives in `gateway/run_shutdown.py`
(`_mm.flush_pending(timeout=10)`), and a regression test ships with it
(`tests/gateway/test_73297_memory_flush_on_reset.py`) whose docstring describes a
bounded-drain abandonment in which already-queued writes are dropped — matching the symptom.
We have not established causation and are not claiming a bug here, only pointing at where we
would look next. **Check your own version before assuming you are affected.**

**What we do now, regardless of the mechanism.**
- count `~/.hermes/pending/memory/` before and after any approve cycle;
- keep a copy of the staging directory until the cycle is trusted;
- never let a queue be the only copy of something you care about.

**If you are hitting this too**, that count-before/after is the reproduction; it is the
part we are confident about.

---

## The habit underneath all three

Every one of these is a lesson about *where you look*. Config files, dashboards and
success messages describe intent. Only the effect describes reality.

So: after changing hooks, skills, or a queue — check the effect. For how to build gates
that do not lie about themselves, see the companion skill `guardrail-engineering`.
