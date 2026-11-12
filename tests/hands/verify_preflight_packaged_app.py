"""Verificación de ejecución real: ApplicationPreflight.check con app empaquetada (AppX/UWP).

Objetivo (unidad 3.8.5.1.1):
- Comprobar que resolve_executable devuelve None para una app UWP con app_id y sin ruta .exe.
- Comprobar que check rechaza con blocked_by="executable_not_resolved" cuando no hay URI válida.
- Registrar si alguna app empaquetada real queda bloqueada por esa causa.

No abre ninguna aplicación ni ejecuta acciones de escritorio.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Asegurar que se puede importar src desde la raíz del repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hands.application_preflight import ApplicationPreflight  # noqa: E402


def main() -> int:
    preflight = ApplicationPreflight()

    # Apps UWP/AppX reales detectadas en shell:AppsFolder (TARGET vacío, sin .exe)
    packaged_apps = [
        {
            "name": "Calculadora",
            "app_id": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
        },
        {
            "name": "Bloc de notas",
            "app_id": "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
        },
        {
            "name": "Configuración",
            "app_id": "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel",
        },
        {
            "name": "Paint",
            "app_id": "Microsoft.Paint_8wekyb3d8bbwe!App",
        },
        {
            "name": "Terminal",
            "app_id": "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App",
        },
    ]

    print("=" * 80)
    print("VERIFICACIÓN REAL: ApplicationPreflight.check con apps empaquetadas (AppX/UWP)")
    print("=" * 80)

    any_blocked = False

    for app in packaged_apps:
        name = app["name"]
        app_id = app["app_id"]

        # 1) resolve_executable directamente
        resolved = preflight.resolve_executable(name=name, app_id=app_id)

        # 2) check completo (sin URI, sin login_required)
        result = preflight.check(
            application={
                "name": name,
                "app_id": app_id,
            }
        )

        print("-" * 80)
        print(f"App: {name}")
        print(f"  app_id: {app_id}")
        print(f"  resolve_executable -> {resolved!r}")
        print(f"  check.allowed      -> {result.get('allowed')}")
        print(f"  check.blocked_by   -> {result.get('blocked_by')!r}")
        print(f"  check.reason       -> {result.get('reason')!r}")
        print(f"  check.executable_path -> {result.get('executable_path')!r}")
        print(f"  check.confidence   -> {result.get('confidence')!r}")

        if resolved is None and result.get("blocked_by") == "executable_not_resolved":
            print("  >>> COINCIDE CON EL COMPORTAMIENTO ESPERADO (3.8.3.5): rechazado por executable_not_resolved")
            any_blocked = True
        else:
            print("  >>> NO COINCIDE: revisar comportamiento real")

    print("=" * 80)
    print(f"RESULTADO: {'ALGUNA app empaquetada queda bloqueada por executable_not_resolved: SÍ' if any_blocked else 'NINGUNA app empaquetada bloqueada por esa causa'}")
    print("=" * 80)

    # Salida estructurada para registro
    summary = {
        "apps_verificadas": len(packaged_apps),
        "alguna_bloqueada_por_executable_not_resolved": any_blocked,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
