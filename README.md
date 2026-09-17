# Agent Guardrails: Field Notes

Two skills distilled from running Hermes Agent in production for months — and from
the mistakes we made while building its guardrails.

They are **field notes, not a framework**. Nothing here is a library you install;
it is what we wish someone had told us before we shipped a gate that looked like it
worked and quietly didn't.

## What's inside

- **`guardrail-engineering`** — how to tell whether your guardrail actually guards.
  Four rules we learned the hard way, plus a ~60-line regression harness that tests
  your gates against two classes of input: *accidental* violations (casual mistakes)
  and *deliberate* bypasses (someone — or some future model — actively trying to get
  around the rule).

- **`hermes-ops-gaps`** — three Hermes-specific behaviours that the official docs do
  not (yet) spell out, each with a reproduction. Deliberately short: everything else
  we hit is already documented upstream, so repeating it here would just rot.

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

## Using these

Both are plain `SKILL.md` folders — no install step, no runtime:

```bash
cp -r skills/guardrail-engineering ~/.hermes/skills/
cp -r skills/hermes-ops-gaps      ~/.hermes/skills/
```

Then ask your agent for the skill by name, or read them yourself. The regression
harness runs on its own:

```bash
python3 skills/guardrail-engineering/scripts/guardrail_regression.py \
  --cases skills/guardrail-engineering/scripts/cases.example.json \
  --cmd 'python3 /path/to/your/gate.py' --mutate
```

`--mutate` is the part that matters: it re-runs your cases against a deliberately
gutted gate (always-allow and always-deny) and fails if your cases don't notice.

## Provenance

Written while operating a self-hosted Hermes Agent. Every claim in these files is
something we hit, fixed, and then re-tested — the counts, the bypass list, and the
canary behaviour are from those runs, not from a plausibility argument.

## License

MIT. Use it, cut it up, ignore the parts that don't fit.
