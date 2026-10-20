#!/usr/bin/env python3
"""Contexto de 'unidad'/'unidades'/'iteracion' en README.md + busqueda de otros README."""

import os
import re

with open("README.md", "rb") as handle:
    text = handle.read().decode("utf-8")
lines = text.replace("\r\n", "\n").split("\n")

print("===== unidad / iteracion =====")
for index, line in enumerate(lines):
    if re.search(r"unidad|iteraci", line, re.IGNORECASE):
        print("  L%-5d %s" % (
            index + 1, line.strip()[:165].encode("ascii", "replace").decode()))

print("===== otros ficheros README/readme en el repo =====")
skip = {".git", "__pycache__", ".cache", "logs", "data"}
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
    for name in files:
        if name.lower().startswith("readme"):
            full = os.path.join(root, name)
            try:
                body = open(full, "rb").read().decode("utf-8", "replace").lower()
            except Exception:
                body = ""
            print("  %-60s fase=%d" % (full, body.count("fase")))
