#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""example_gate.py — a deliberately *ordinary* text-pattern gate, used as the fixture
for the regression harness and for CI.

It is here to be tested, not to be good: it implements the naive approach (match the
literal protected path together with a write verb) so that the example case set has a
real gate to pass or fail. The interesting cases are the ones it does NOT catch — see
`cases.example.json`, where the deliberate-bypass case is marked `"gap": true`.

Protected path is a placeholder (/srv/protected). Exit 2 = block, 0 = allow.
"""
import json
import re
import sys

PROTECTED = "/srv/protected/"
WRITE = re.compile(r"open\s*\([^)]*['\"](?:w|a|x)", re.I)
SHELL = re.compile(r"(?:^|[\s;&|])(?:>>?|tee|cp|mv|rm|sed\s+-i)(?=\s|$)")


def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0                      # fail open on garbage input; say so in your own gate
    tool = ev.get("tool_name") or ""
    ti = ev.get("tool_input") or {}
    path = str(ti.get("path") or "")
    code = str(ti.get("code") or "")
    cmd = str(ti.get("command") or "")

    if tool == "write_file" and PROTECTED in path:
        return 2
    if tool == "execute_code" and PROTECTED in code and WRITE.search(code):
        return 2
    if tool == "terminal" and PROTECTED in cmd and SHELL.search(cmd):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
