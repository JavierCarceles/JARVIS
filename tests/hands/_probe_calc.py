import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from src.hands.application_preflight import get_application_preflight

_CALC_PATH = r"C:\Windows\System32\calc.exe"

print("1) calc.exe existe en disco:", os.path.isfile(_CALC_PATH))

preflight = get_application_preflight()

print("2) resolve_executable(calc.exe, ''):", repr(preflight.resolve_executable(name="calc.exe", app_id="")))

pf = preflight.check({
    "name": "calc.exe",
    "app_id": "",
    "path": _CALC_PATH,
})
print("3) preflight.check(calc.exe):")
for k, v in pf.items():
    print(f"   {k} = {v!r}")
