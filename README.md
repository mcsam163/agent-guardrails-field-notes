# Agent Guardrails: Field Notes

![test](https://github.com/mcsam163/agent-guardrails-field-notes/actions/workflows/test.yml/badge.svg)

Two skills distilled from running Hermes Agent in production for months — and from
the mistakes we made while building its guardrails.

They are **field notes, not a framework**. Nothing here is a library you install;
it is what we wish someone had told us before we shipped a gate that looked like it
worked and quietly didn't.

## What's inside

- **`guardrail-engineering`** — how to tell whether your guardrail actually guards.
  Four rules we learned the hard way, plus a dependency-free regression harness that tests
  your gates against two classes of input: *accidental* violations (casual mistakes)
  and *deliberate* bypasses (someone — or some future model — actively trying to get
  around the rule). Scope: gates that decide by exit code on a single call
  (shell-script hooks and friends).

- **`hermes-silent-failures`** — three Hermes behaviours that are *documented*, and that
  still cost us time, because when they bite the system looks fine. Each with the exact
  check that catches it. One entry is an **unresolved observation** (symptom real,
  mechanism not reproduced) and is labelled as such. (Previously named `hermes-ops-gaps`;
  the old framing over-claimed that these were undocumented — they are not.)

## What it looks like

```
guardrail regression — 7 cases (3 block / 3 allow / 0 error, 1 documented gaps)
  PASS  accidental  accidental: direct write to protected file   exit=2 want=block
  PASS  legitimate  legit: backup copy (source is protected, ...) exit=0 want=allow
  GAP   deliberate: path assembled at runtime (string concat)     exit=0 (documented limitation)
  canary always-allow  → 3 case(s) failed   OK (case set caught it)
  canary always-deny   → 3 case(s) failed   OK (case set caught it)

all cases behaved as specified
```

Run the same thing against a case set that cannot fail, and it says so instead of
passing:

```
  canary always-deny   → 0 case(s) failed   CASE SET IS BLIND

FAILURES
  ✗ canary: case set is blind to always-deny: exit=-1 expected=error
```

## The checklist

Three copy-pasteable checks. Each exists because the matching failure is silent — the
system keeps reporting success while nothing happens.

```bash
# 1. Are your hooks actually running? Configuring a hook is not registering it, and the
#    allowlist stores the script's mtime (not a hash) — so an edited script may be running
#    code nobody approved.
hermes hooks list && hermes hooks doctor

# 2. Has a bundled skill quietly stopped receiving upstream updates?
hermes skills list-modified

# 3. Before and after any memory-approval cycle: count, do not assume.
ls ~/.hermes/pending/memory/ | wc -l
```

## Why "does not lie" is the whole point

Our first memory-protection gate was a text-pattern matcher. It blocked the naive
write. It looked great. Then an independent reviewer wrote a three-line script using
a different API call and overwrote the protected file — passing the gate.

A gate that fails loudly is a bug report. A gate that fails silently is a **false
belief**, and it's worse than having no gate at all: you stop checking.

That asymmetry is what these notes are about.

## Who this is for

Anyone who has wired an LLM agent to something they care about (memory files, credentials,
deploy steps, money) and put a "guard" in front of it. If your guard is a regex, a prompt
instruction, or a hook that mostly works — start with `guardrail-engineering`.

> **Verified on Hermes v0.21.x, September 2026.** Commands, flags and file paths are
> version-sensitive. If you are on a different version, check before trusting them.

## Using these

Both are plain `SKILL.md` folders — no install step, no runtime:

```bash
# native install (verified on Hermes v0.21.x)
hermes skills install mcsam163/agent-guardrails-field-notes/skills/guardrail-engineering
hermes skills install mcsam163/agent-guardrails-field-notes/skills/hermes-silent-failures

# or just copy the folders anywhere your agent loads skills from
cp -r skills/guardrail-engineering skills/hermes-silent-failures ~/.hermes/skills/
```

Then ask your agent for the skill by name, or read them yourself. The regression
harness runs on its own:

```bash
python3 skills/guardrail-engineering/scripts/guardrail_regression.py \
  --cases skills/guardrail-engineering/scripts/cases.example.json \
  --cmd 'python3 /path/to/your/gate.py' --mutate
```

`--mutate` re-runs your cases against two degenerate gates it synthesises (always-allow,
always-deny) and fails if your case set passes both — i.e. if it cannot tell a working
gate from a broken one. It disproves a *blind* case set; it is not proof your cases are right.

## Provenance

Written while operating a self-hosted Hermes Agent (v0.21.x). The numbers, the bypass
list and the failure paths come from those runs. Where something did **not** hold up under
re-testing, the text says so: the memory-queue entry is an observation we could not
reproduce a mechanism for, and the harness documents its own earlier crash. Corrections
welcome as issues.

## License

MIT. Use it, cut it up, ignore the parts that don't fit.
