#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""guardrail_regression.py — a tiny regression harness for gate/hook style guardrails.

Contract it assumes (the most common one for agent hooks):
    stdin : one JSON object  ({"tool_name": ..., "tool_input": {...}, ...})
    exit 0  = allow
    exit 2  = block  (refuse the action)
    other   = error  (the harness reports it; it does not guess)

Why it exists: a gate without tests is a comment, and a test suite that cannot fail
is worse — it manufactures confidence. `--mutate` is the antidote: it runs your
cases against a deliberately gutted gate (always-allow and always-deny) and asserts
that your suite *does* notice. If your cases pass against an always-allow gate, they
are not testing anything.

Usage:
    python3 guardrail_regression.py --cases cases.json --cmd 'python3 /path/to/gate.py'
    python3 guardrail_regression.py --cases cases.json --cmd '...' --mutate
    python3 guardrail_regression.py --cases cases.json --cmd '...' --json

Cases file format: see cases.example.json
"""
import argparse
import json
import subprocess
import sys
import tempfile
import os

BLOCK = 2
ALLOW = 0
EXPECT_CODE = {"block": BLOCK, "allow": ALLOW}

# Synthetic gates used by --mutate. They are deliberately broken in the two
# obvious ways; a real suite must fail on both.
MUTANTS = {
    "always-allow": "import sys,json; sys.stdin.read(); sys.exit(0)",
    "always-deny": "import sys,json; sys.stdin.read(); sys.exit(2)",
}


def run_case(cmd, event, timeout=20):
    try:
        p = subprocess.run(cmd, shell=True, input=json.dumps(event), text=True,
                           capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, "timeout"


def load_cases(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data["cases"] if isinstance(data, dict) else data
    for c in cases:
        if c.get("expect") not in EXPECT_CODE:
            raise SystemExit(f'case "{c.get("name")}" needs expect: "block" or "allow"')
    return cases


def run_suite(cmd, cases, verbose=True):
    failures = []
    for c in cases:
        code, out = run_case(cmd, c.get("event", {}))
        want = EXPECT_CODE[c["expect"]]
        ok = code == want
        if not ok:
            failures.append((c, code, out))
        if verbose:
            tag = f'{c.get("kind", "?"):<11}'
            print(f'  {"PASS" if ok else "FAIL"}  {tag} {c["name"]:<44} exit={code} want={want}')
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--mutate", action="store_true", help="canary: verify the suite can fail")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cases = load_cases(a.cases)
    blocked = sum(1 for c in cases if c["expect"] == "block")
    allowed = len(cases) - blocked
    if not a.json:
        print(f"guardrail regression — {len(cases)} cases "
              f"({blocked} must block, {allowed} must be allowed)")

    failures = run_suite(a.cmd, cases, verbose=not a.json)

    result = {"cases": len(cases), "failed": len(failures),
              "failures": [{"name": c["name"], "exit": code} for c, code, _ in failures]}

    if a.mutate:
        # The suite must fail against both mutants, otherwise it proves nothing.
        canary = {}
        for name, cmd in MUTANTS.items():
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
                fh.write(cmd)
                path = fh.name
            try:
                mut_failures = run_suite(f"python3 {path}", cases, verbose=False)
            finally:
                os.unlink(path)
            canary[name] = len(mut_failures)
            if not a.json:
                verdict = "OK (suite caught it)" if mut_failures else "SUITE IS BLIND"
                print(f"  canary {name:<13} → {len(mut_failures)} case(s) failed   {verdict}")
        blind = [k for k, v in canary.items() if v == 0]
        result["canary"] = canary
        result["blind_to"] = blind
        if blind:
            print(f"\nFAIL: the suite passes against {', '.join(blind)} — it cannot "
                  f"distinguish a working gate from a broken one.")
            failures = failures or [("canary", -1, "")]
            result["failed"] = result["failed"] or 1

    if a.json:
        print(json.dumps(result, ensure_ascii=False))

    if failures:
        print("\nFAILURES")
        for c, code, out in failures:
            print(f"  ✗ {c['name']}: exit={code} expected={EXPECT_CODE[c['expect']]}")
            if out.strip():
                print(f"      {out.strip()[:200]}")
        return 1
    print("\nall cases behaved as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
