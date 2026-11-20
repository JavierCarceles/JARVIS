# -*- coding: ascii -*-
"""
Verificacion real en Windows del contrato de lanzamiento con una lista blanca
de aplicaciones inocuas, una por vez:

- Bloc de notas (destino ejecutable/comando).
- Calculadora (aplicacion empaquetada por AUMID; "calculadora" o "calculator"
  segun el idioma del menu Inicio).

Para cada aplicacion, por el servicio unico de produccion
(``ApplicationLaunchService``: resolucion local -> ApplicationPreflight ->
lanzamiento -> verificacion de proceso y ventana):
- la apertura tiene exito, lanza una instancia propia y verifica proceso y
  ventana visible;
- una segunda apertura no repite el lanzamiento (reutiliza la ventana abierta,
  sin ventanas nuevas);
- la evidencia devuelta no contiene la carpeta del usuario;
- ``close`` cierra solo la ventana abierta por JARVIS: ninguna otra ventana
  visible del escritorio desaparece y las de Visual Studio Code no cambian.

No escribe texto ni pulsa controles.

Precondicion: la aplicacion bajo prueba no debe tener ventanas abiertas por el
usuario; si las tiene, la prueba falla pidiendo cerrarlas (no SKIP).

Requiere Windows y JARVIS_TEST_GUI_REAL=1. Ejecutar de uno en uno:
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/apps/test_platform_launch_entorno_real.py -v -s
"""

from __future__ import annotations

import os
import time
import unittest
from typing import Any, List, Sequence, Set, Tuple

from src.core.operation_errors import IdempotencyRegistry
from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.apps.platform_launch import TARGET_AUMID, ApplicationLaunchService

ESPERA_CIERRE_SEGUNDOS = 15.0
CODIGOS_NO_ENCONTRADA = ("not_found", "not_installed")

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_lanzamiento_contrato_lock.lock"
)


def _gui_lock_activo() -> bool:
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        import psutil

        return psutil.pid_exists(int(pid_texto)) and int(pid_texto) != os.getpid()
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock() -> None:
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock() -> None:
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


def _ventanas_visibles(adapter: Any) -> Set[int]:
    resultado = adapter.list_windows(visible_only=True)
    return {int(w.window_id) for w in (resultado.value or [])} if resultado.ok else set()


def _estado_ventanas_vscode(adapter: Any) -> List[Tuple[int, Any, bool, bool]]:
    resultado = adapter.list_windows(app_identity="Code.exe", visible_only=False)
    if not resultado.ok:
        return []
    estado = []
    for ventana in resultado.value or []:
        bounds = ventana.bounds.to_dict() if ventana.bounds is not None else None
        estado.append((int(ventana.window_id), bounds, bool(ventana.is_maximized), bool(ventana.is_minimized)))
    return sorted(estado, key=lambda e: e[0])


def _codigo(outcome: Any) -> str:
    codigo = getattr(outcome.error, "code", "") if outcome.error else ""
    return str(getattr(codigo, "value", codigo) or "").lower()


class TestLanzamientoListaBlancaEntornoReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows (excepcion (a): APIs nativas de Windows)")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real")
        if _gui_lock_activo():
            raise AssertionError("Otro test GUI esta en ejecucion (lock activo); esperar a que termine")
        _adquirir_gui_lock()
        cls.adapter = get_desktop_platform()

    @classmethod
    def tearDownClass(cls):
        _liberar_gui_lock()

    def _servicio(self) -> ApplicationLaunchService:
        return ApplicationLaunchService(desktop=self.adapter, registry=IdempotencyRegistry())

    def _abrir_primera(self, servicio: ApplicationLaunchService, nombres: Sequence[str]) -> Tuple[str, Any]:
        ultimo = None
        for nombre in nombres:
            outcome = servicio.open(nombre, timeout=15.0)
            ultimo = (nombre, outcome)
            if outcome.success or _codigo(outcome) not in CODIGOS_NO_ENCONTRADA:
                return ultimo
        assert ultimo is not None
        return ultimo

    def _ciclo(self, nombres: Sequence[str], proceso_usuario: str) -> Any:
        usuario = self.adapter.list_windows(app_identity=proceso_usuario, visible_only=True)
        if usuario.ok and usuario.value:
            self.fail("%s tiene ventanas abiertas por el usuario; cerrarlas y repetir la prueba" % proceso_usuario)
        vscode_antes = _estado_ventanas_vscode(self.adapter)
        visibles_antes = _ventanas_visibles(self.adapter)
        servicio = self._servicio()

        nombre, outcome = self._abrir_primera(servicio, nombres)
        detalle = "%s: %s" % (nombre, outcome.to_dict())
        self.assertTrue(outcome.success, detalle)
        self.assertTrue(outcome.launched, "Debe lanzarse una instancia propia: " + detalle)
        self.assertFalse(outcome.reused_existing, detalle)
        self.assertTrue(outcome.process_verified and outcome.window_verified, detalle)
        self.assertIsNotNone(outcome.window, detalle)
        window_id = int(outcome.window.window_id)
        self.assertNotIn(window_id, visibles_antes, "La ventana verificada debe ser nueva: " + detalle)
        self.assertNotIn(os.path.expanduser("~"), str(outcome.to_dict()), "La evidencia no debe exponer la carpeta del usuario")

        # Segunda apertura: no se repite el lanzamiento.
        visibles_abierta = _ventanas_visibles(self.adapter)
        segunda = servicio.open(nombre, timeout=15.0)
        self.assertTrue(segunda.success, segunda.to_dict())
        self.assertTrue(segunda.reused_existing, "Una apertura con exito no debe repetirse: %s" % segunda.to_dict())
        self.assertFalse(segunda.launched, segunda.to_dict())
        self.assertEqual(_ventanas_visibles(self.adapter) - visibles_abierta, set(), "No deben aparecer ventanas nuevas")

        # Cierre solo de lo propio.
        cierre = servicio.close(nombre)
        self.assertTrue(cierre.success, cierre.to_dict())
        self.assertEqual(cierre.evidence.get("closed_windows"), [window_id], cierre.to_dict())
        limite = time.monotonic() + ESPERA_CIERRE_SEGUNDOS
        while time.monotonic() < limite and window_id in _ventanas_visibles(self.adapter):
            time.sleep(0.25)
        visibles_despues = _ventanas_visibles(self.adapter)
        self.assertNotIn(window_id, visibles_despues, "La ventana abierta por JARVIS sigue abierta")
        desaparecidas = {w for w in visibles_antes if w not in visibles_despues}
        self.assertFalse(desaparecidas, "Se cerraron ventanas que no abrio JARVIS: %s" % sorted(desaparecidas))
        self.assertEqual(_estado_ventanas_vscode(self.adapter), vscode_antes, "Visual Studio Code no debe cambiar")
        return outcome

    def test_01_bloc_de_notas_entorno_real(self):
        outcome = self._ciclo(("notepad",), "notepad.exe")
        # Windows 10: notepad.exe clasico. Windows 11: Bloc de notas es un
        # paquete y su AUMID abre la misma aplicacion; cualquier otro paquete
        # seria un error de resolucion.
        if outcome.target.target_type == TARGET_AUMID:
            self.assertTrue(
                outcome.target.target.casefold().startswith("microsoft.windowsnotepad_8wekyb3d8bbwe!"),
                outcome.to_dict(),
            )
        else:
            self.assertIn(outcome.target.target_type, ("exe", "command"), outcome.to_dict())

    def test_02_calculadora_por_aumid_entorno_real(self):
        outcome = self._ciclo(("calculadora", "calculator"), "CalculatorApp.exe")
        self.assertEqual(outcome.target.target_type, TARGET_AUMID, outcome.to_dict())

    def test_03_calculadora_en_el_otro_idioma_entorno_real(self):
        # El usuario puede pedirla en espanol o en ingles sea cual sea el
        # idioma de Windows: ambos nombres llevan al mismo paquete.
        for nombre in ("calculator", "calculadora"):
            with self.subTest(nombre=nombre):
                outcome = self._ciclo((nombre,), "CalculatorApp.exe")
                self.assertEqual(outcome.target.target_type, TARGET_AUMID, outcome.to_dict())
                self.assertTrue(
                    outcome.target.target.casefold().startswith("microsoft.windowscalculator_8wekyb3d8bbwe!"),
                    outcome.to_dict(),
                )


if __name__ == "__main__":
    unittest.main()
