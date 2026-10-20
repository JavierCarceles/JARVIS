#!/usr/bin/env python3
"""Muestra la estructura de titulos y las lineas anadidas del diff de README.md."""

import re
import subprocess

with open("README.md", "rb") as handle:
    text = handle.read().decode("utf-8")
lines = text.replace("\r\n", "\n").split("\n")

print("===== ESTRUCTURA (h1/h2/h3) =====")
for index, line in enumerate(lines):
    if re.match(r"^#{1,3} ", line):
        print("  L%-5d %s" % (
            index + 1, line.encode("ascii", "replace").decode()))

print("===== lineas ANADIDAS por el diff =====")
diff = subprocess.run(
    ["git", "diff", "-U0", "--", "README.md"], capture_output=True, check=True)
added = [l for l in diff.stdout.decode("utf-8", "replace").split("\n")
         if l.startswith("+") and not l.startswith("+++")]
print("  total_additions=%d" % len(added))
for line in added:
    print("  " + line[:150].encode("ascii", "replace").decode())
