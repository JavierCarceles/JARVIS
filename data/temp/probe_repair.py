"""Prueba si un reparo en memoria permite parsear todos los ficheros de src/."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BROKEN = [
    "src/eyes/screen.py", "src/eyes/screen_capture.py", "src/eyes/vision.py",
    "src/eyes/vision_only.py", "src/hands/calibrator.py",
    "src/hands/edge/calibrator_edge.py", "src/hands/edge/edge.py",
    "src/hands/firefox/calibrator_firefox.py", "src/hands/firefox/firefox.py",
    "src/hands/universal_visual_calibrator.py",
    "src/hands/windows/calibrator_windows.py", "src/hands/windows/windows.py",
    "src/utils/architectural_evolution_manager.py",
]

# patron 1: logger._print_log(a, b, "f.py", "method", N), "f.py", "method", N)
P1 = re.compile(
    r'logger\._print_log\((?P<args>[^)]*?)\)\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*\d+\s*\)'
)

for rel in BROKEN:
    p = ROOT / rel
    src = p.read_text(encoding="utf-8-sig")
    fixed = P1.sub(lambda m: f'logger._print_log({m.group("args")})', src)
    try:
        ast.parse(fixed)
        print(f"OK    {rel}  (reparado: {fixed != src})")
    except SyntaxError as e:
        print(f"FALLA {rel}  linea {e.lineno}: {e.msg}")
        lines = fixed.splitlines()
        if e.lineno and e.lineno <= len(lines):
            print("      >>", lines[e.lineno - 1].strip()[:150])
