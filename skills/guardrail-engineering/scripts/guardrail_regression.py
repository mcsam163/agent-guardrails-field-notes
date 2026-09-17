#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""guardrail_regression.py — a tiny regression harness for gate/hook style guardrails.

Contract it assumes (the most common one for agent hooks):
    stdin : one JSON object  ({"tool_name": ..., "tool_input": {...}, ...})
    exit 0  = allow
    exit 2  = block  (refuse the action)
    other   = error  (a gate that crashed is NOT a gate that approved)

Scope, stated honestly: this harness checks the **exit-code contract of a single
call**. It can prove that a gate stops what it says it stops, and that your case
set can tell a working gate from a broken one. It cannot test a detector that runs
out-of-band (compare artifacts yourself), and it cannot tell you your cases are
*semantically* right — only that they are not blind.

Why `--mutate` exists: a gate without tests is a comment, and a test suite that
cannot fail is worse — it manufactures confidence. `--mutate` re-runs your cases
against two synthetic degenerate gates (always-allow, always-deny) and fails if
your case set passes both. Those two mutants can disprove a **blind case set**
(no block cases, or no allow cases). They say nothing about whether your cases
describe the right behaviour.

Usage:
    python3 guardrail_regression.py --cases cases.json --cmd 'python3 /path/to/gate.py'
    python3 guardrail_regression.py --cases cases.json --cmd '...' --mutate
    python3 guardrail_regression.py --cases cases.json --cmd '...' --json

Cases file format: see cases.example.json. A case may carry `"gap": true` when it
documents a known limitation of the gate rather than desired behaviour; gap cases
are reported but never fail the run (and never count as "blind" evidence either).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

BLOCK, ALLOW = 2, 0
EXPECT_CODE = {"block": BLOCK, "allow": ALLOW, "error": "other"}

MUTANTS = {
    "always-allow": "import sys; sys.stdin.read(); sys.exit(0)",
    "always-deny": "import sys; sys.stdin.read(); sys.exit(2)",
}


def run_case(cmd, event, timeout=20):
    try:
        p = subprocess.run(cmd, shell=True, input=json.dumps(event), text=True,
                           capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, "timeout"


def matches(expect, code):
    want = EXPECT_CODE[expect]
    return code not in (BLOCK, ALLOW) if want == "other" else code == want


def load_cases(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data["cases"] if isinstance(data, dict) else data
    for c in cases:
        if c.get("expect") not in EXPECT_CODE:
            raise SystemExit(f'case "{c.get("name")}" needs expect: block | allow | error')
    return cases


def run_suite(cmd, cases, verbose=True):
    """Returns (failures, gap_notes)."""
    failures, gaps = [], []
    for c in cases:
        code, out = run_case(cmd, c.get("event", {}))
        ok = matches(c["expect"], code)
        if c.get("gap"):
            gaps.append((c, code))
            if verbose:
                print(f'  GAP   {c["name"]:<44} exit={code} (documented limitation — never fails the run)')
            continue
        if not ok:
            failures.append((c, code, out))
        if verbose:
            print(f'  {"PASS" if ok else "FAIL"}  {c.get("kind", "?"):<11} {c["name"]:<44} exit={code} want={c["expect"]}')
    return failures, gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--mutate", action="store_true", help="canary: verify the case set can fail")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cases = load_cases(a.cases)
    judged = [c for c in cases if not c.get("gap")]
    blocked = sum(1 for c in judged if c["expect"] == "block")
    allowed = sum(1 for c in judged if c["expect"] == "allow")
    errored = len(judged) - blocked - allowed
    if not a.json:
        print(f"guardrail regression — {len(cases)} cases "
              f"({blocked} block / {allowed} allow / {errored} error, "
              f"{len(cases) - len(judged)} documented gaps)")

    failures, gaps = run_suite(a.cmd, cases, verbose=not a.json)
    result = {
        "cases": len(cases),
        "judged": len(judged),
        "failed": len(failures),
        "gaps": [{"name": c["name"], "exit": code} for c, code in gaps],
        "failures": [{"name": c["name"], "exit": code, "expect": c["expect"]} for c, code, _ in failures],
    }

    if a.mutate:
        canary = {}
        for name, cmd in MUTANTS.items():
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
                fh.write(cmd)
                path = fh.name
            try:
                mut_failures, _ = run_suite(f"python3 {path}", judged, verbose=False)
            finally:
                os.unlink(path)
            canary[name] = len(mut_failures)
            if not a.json:
                verdict = "OK (case set caught it)" if mut_failures else "CASE SET IS BLIND"
                print(f"  canary {name:<13} → {len(mut_failures)} case(s) failed   {verdict}")
        blind = [k for k, v in canary.items() if v == 0]
        result["canary"] = canary
        result["blind_to"] = blind
        if blind:
            # A failure, but never a crash: the point of this tool is that its own
            # failure path is readable. (An earlier version raised TypeError here.)
            failures.append(({"name": f"canary: case set is blind to {', '.join(blind)}",
                              "expect": "error"}, -1, ""))
            result["failed"] = len(failures)

    if a.json:
        # stdout must be *only* the JSON document when --json is asked for, and the
        # exit code must reflect reality. (An earlier version printed a human
        # "all cases behaved as specified" line here and returned 0 — i.e. a checker
        # that lied, which is precisely what this repo is about.)
        result["failures"] = [{"name": c["name"], "exit": code, "expect": c["expect"]}
                              for c, code, _ in failures]
        result["failed"] = len(failures)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if failures else 0

    if failures:
        print("\nFAILURES")
        for c, code, out in failures:
            print(f"  ✗ {c['name']}: exit={code} expected={c['expect']}")
            if out and out.strip():
                print(f"      {out.strip()[:200]}")
        return 1
    print("\nall cases behaved as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
