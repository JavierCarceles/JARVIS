#!/usr/bin/env python3
"""Muestra las lineas eliminadas del diff de README.md."""

import subprocess

diff = subprocess.run(
    ["git", "diff", "-U0", "--", "README.md"], capture_output=True, check=True)
removed = [l for l in diff.stdout.decode("utf-8", "replace").split("\n")
           if l.startswith("-") and not l.startswith("---")]
print("total_deletions=%d" % len(removed))
for line in removed:
    print("  " + line[:160].encode("ascii", "replace").decode())
