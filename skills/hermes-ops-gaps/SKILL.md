---
name: hermes-ops-gaps
description: Use when operating a self-hosted Hermes Agent and something looks configured-but-not-working, or data quietly disappears. Three behaviours the official docs do not spell out, each with a reproduction and a check you can run.
---

# Hermes ops: three gaps the docs leave open

Short on purpose. Everything else we hit while running Hermes in production was already
written down upstream (hook matchers, the stdin JSON protocol, allowlist behaviour, the
fail-open/fail-closed matrix, `hermes hooks doctor`, curator TTLs, `hermes skills
list-modified|diff|reset`). Repeating those here would just rot.

What follows is what we could **not** find documented, verified on v0.21.x, with a
reproduction for each.

---

## 1. A configured hook is not necessarily a running hook

**Symptom.** You add a hook to `config.yaml`, restart, and everything "works" — except
that hook never fires. No error in chat. The only trace is one `WARNING` line in the
error log saying the hook was `not allowlisted — skipped`.

**Why.** Two separate things must both be true, and only the first is visible from the
config file:

1. the hook must be **allowlisted** (first-use consent, stored in
   `shell-hooks-allowlist.json`); and
2. registration happens **at process start** — a long-running gateway keeps the set of
   hooks it booted with.

Confirm-and-consent prompts need a TTY. Restart a gateway non-interactively (systemd,
a slash command, a supervisor) and there is nobody to answer the prompt, so an
*unknown* hook is skipped rather than queued.

**Reproduce.**
```bash
# 1. add any hook to config.yaml under hooks.pre_tool_call
# 2. restart via a non-interactive path (service manager / gateway restart)
grep -a 'not allowlisted' ~/.hermes/logs/errors.log   # ← the only notice you get
hermes hooks doctor                                    # ← lists consent + mtime drift
```

**Do.** After any restart, run `hermes hooks doctor` and assert three things per hook:
allowlisted, script hash/mtime matches the approved snapshot, and a canary call actually
fires it. If your deployment is non-interactive, pre-seed the allowlist entry (or set the
auto-accept option deliberately) — do not assume the config file is sufficient.

`hermes hooks doctor` also flags *script modified since approval*. Read that as
"this gate is not running the code you think it is", not as noise: the allowlist keys on
the command string, not on the script's contents, so edits are trusted silently.

---

## 2. Editing a bundled skill freezes it — permanently, and quietly

**Symptom.** Months later, your copy of a bundled skill is missing fixes that upstream has.

**Why.** Bundled skills are tracked as *user-modified* once you edit them. Upstream updates
to those files are then skipped, so your version stops advancing. Nothing tells you at edit
time, and nothing tells you later.

**Reproduce.**
```bash
hermes skills list-modified        # bundled skills you have edited
hermes skills diff <name>          # how your copy differs from stock
hermes skills reset <name>         # clears the modified flag so updates apply again
```

**Do.** Treat bundled files as read-only **source**, not as your editing surface: copy the
content you want into one of your own skills, then `reset` the bundled one. (Corollary:
when you want to add to a bundled skill, ask whether the idea really needs that file — in
our case the answer was "no, it needs its own skill".)

---

## 3. The memory-approval applier can delete records it cannot parse

**Symptom.** You enable the staged-write queue (`memory.write_approval`), stage a batch,
and later some staged records are simply gone. No error, no failed entry in the queue, no
log line.

**Why.** The applier assumes records shaped exactly like the built-in memory gate produces.
Any record it cannot parse is removed from the queue rather than surfaced — the queue
reports success for the batch. With a third-party memory provider in front, that mismatch
is easy to hit: our provider stages a different shape, and 7 records were lost this way.

**Reproduce (on a copy — this is destructive by design).**
```bash
ls ~/.hermes/pending/memory/            # staged records
# stage or hand-write one record whose shape differs from the built-in gate
# then run the approve path and compare the file list before/after
```

**Do.** Before enabling `memory.write_approval` with any non-default provider, count the
records in `~/.hermes/pending/memory/`, run one approve cycle, and count again. Keep a copy
of the staging directory until you trust it. Reported upstream (the applier's "delete what
I do not understand" behaviour is the same class of bug as the ones the project already
tracks for its own gate).

---

## The habit underneath all three

These are all the same failure shape: **the system reports success while the thing you
believe is happening is not happening.** Hook not registered, skill not updating, record
not written — each one is silent, and each one costs you the trust you placed in a green
result.

So: after any change to hooks, skills, or a queue, check the *effect*, not the config file.
For how to build gates that don't lie about themselves, see the companion skill
`guardrail-engineering`.
