#!/usr/bin/env python3
import subprocess, sys
out = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/utils/contextual_adaptation_engine/test_goal_adaptation_pattern_restart_verification.py::test_el_patron_recuperado_conserva_los_valores_sin_perdida",
     "-v", "--tb=short", "-p", "no:cacheprovider"],
    capture_output=True, text=True
)
for line in out.stdout.splitlines():
    if any(k in line for k in ("PASSED", "FAILED", "AssertionError", "timestamp", "assert ", "cambio")):
        print(line)
print("RC:", out.returncode)