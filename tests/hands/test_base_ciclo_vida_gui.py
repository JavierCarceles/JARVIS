# -*- coding: utf-8 -*-
"""
Clase base reutilizable para el control de ciclo de vida de cada test GUI.

Implementa el ciclo obligatorio de la unidad 3.8.5.6.11:
  (1) abrir la aplicacion mediante la ruta de produccion
      (CalibrationManager.launch_application, sin mockear lanzador/procesos/ventanas);
  (2) verificar proceso y ventana pertenecientes a la aplicacion lanzada
      (PID propio, HWND, visibilidad, no es Visual Studio Code, estabilidad);
  (3) cerrar solo la ventana/proceso creado por la prueba tras verificar el
      estado, sin dejar aplicaciones abiertas salvo que el usuario las haya
      abierto previamente y la prueba las reutilice (was_owned=False).

Cada test GUI que herede de CicloVidaGUITestCase obtiene:
  - setUp: captura la linea base real (procesos VS Code, ventanas previas).
  - ejecutar_ciclo_vida(app_name, app_path, app_id=""): ejecuta preflight real,
    lanzamiento real, deteccion de ventana y verificacion de estado.
  - cerrar_propio(): cierra SOLO el proceso lanzado por la prueba (por PID).
  - tearDown: cierra el proceso propio si quedara vivo y comprueba que VS Code
    y las ventanas preexistentes permanecen intactas.

No se envia teclado ni raton a ninguna ventana. No se cierran procesos ni
ventanas preexistentes del usuario.
"""

from __future__ import annotations

import subprocess
import time
import unittest
from typing import Any, Dict, Optional, Set

from src.hands.application_preflight import get_application_preflight
from src.hands.calibration_manager import get_calibration_manager
from src.utils.screen_manager import get_screen_manager


def _contar_proceso(nombre: str) -> int:
    """Cuenta procesos con el nombre dado en tasklist del SO real."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {nombre}"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if nombre.lower() in linea.lower()
    )


def _contar_vscode() -> int:
    """Cuenta procesos de Visual Studio Code (Code.exe) en tasklist."""
    return _contar_proceso("Code.exe")


def _ventanas() -> Set[int]:
    """Devuelve el conjunto de HWND de ventanas visibles del SO real."""
    return set(get_calibration_manager()._get_window_handles())


class CicloVidaGUITestCase(unittest.TestCase):
    """Clase base que controla el ciclo de vida de cada test GUI."""

    # Ruta de produccion de la aplicacion a probar (subclases la definen).
    APP_NAME: str = ""
    APP_PATH: str = ""
    APP_ID: str = ""

    def setUp(self) -> None:
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        self.sm = get_screen_manager()
        self.owned_pid: Optional[int] = None
        self.owned_hwnd: Optional[int] = None
        self.was_owned: bool = False
        self.ciclo_completado: bool = False
        self.resultados: Dict[str, Any] = {}
        # Linea base real del equipo antes de cada test.
        self.vscode_antes = _contar_vscode()
        self.ventanas_antes = _ventanas()
        self.resultados["vscode_antes"] = self.vscode_antes
        self.resultados["ventanas_antes_count"] = len(self.ventanas_antes)

    def tearDown(self) -> None:
        # Cerrar SOLO el proceso creado por esta prueba, si quedara vivo.
        # Nunca cerrar por nombre ni cerrar procesos preexistentes del usuario.
        if self.owned_pid is not None and self.cal._is_process_alive(self.owned_pid):
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(int(self.owned_pid)), "/F"],
                    capture_output=True, text=True, check=False,
                )
            except Exception:
                pass
            tiempo = time.time() + 10
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(self.owned_pid)):
                    break
                time.sleep(0.25)
            self.assertFalse(
                self.cal._is_process_alive(int(self.owned_pid)),
                "el proceso propio no se termino tras cerrar por PID en tearDown",
            )
            self.owned_pid = None

        # Verificar preservacion de Visual Studio Code y ventanas previas.
        vscode_despues = _contar_vscode()
        self.resultados["vscode_despues"] = vscode_despues
        self.assertGreaterEqual(
            vscode_despues, self.vscode_antes,
            f"Visual Studio Code no se preservo: antes={self.vscode_antes}, despues={vscode_despues}",
        )
        despues_ventanas = _ventanas()
        self.resultados["ventanas_despues_count"] = len(despues_ventanas)
        faltantes = []
        for hwnd in self.ventanas_antes:
            if hwnd not in despues_ventanas:
                faltantes.append(hwnd)
        self.assertEqual(
            faltantes, [],
            f"desaparecieron ventanas previas tras el test: {faltantes}",
        )

    def ejecutar_ciclo_vida(
        self,
        app_name: str = "",
        app_path: str = "",
        app_id: str = "",
        timeout_ventana: float = 8.0,
        estabilidad_interval: float = 1.5,
        estabilidad_checks: int = 3,
    ) -> Dict[str, Any]:
        """Ejecuta el ciclo completo de vida de una prueba GUI.

        Pasos:
          1. ApplicationPreflight real sobre el destino.
          2. Lanzamiento real via CalibrationManager.launch_application.
          3. Verificar proceso propio vivo.
          4. Detectar ventana perteneciente al proceso (PID/arbol/propietario).
          5. Verificar estado de la ventana (visible, corresponde, criterio PID, no VS Code).
          6. Estabilidad minima del proceso y la ventana.

        Retorna un diccionario con el resultado del ciclo (was_owned, root_pid,
        hwnd, ventana, preflight, lanzamiento, deteccion, verificacion,
        estabilidad).
        """
        nombre = app_name or self.APP_NAME
        ruta = app_path or self.APP_PATH
        identificador = app_id or self.APP_ID

        self.resultados["app_nombre"] = nombre
        self.resultados["app_ruta"] = ruta

        # Paso 1: Preflight real (no lanza nada, solo valida el destino).
        pf = self.preflight.check({
            "name": nombre,
            "app_id": identificador,
            "path": ruta,
        })
        self.assertTrue(
            pf.get("allowed", False),
            f"preflight rechazo {nombre}: {pf.get('reason')}",
        )
        self.assertFalse(
            pf.get("requires_elevation", True),
            f"{nombre} no deberia requerir elevacion de privilegios",
        )
        self.resultados["preflight"] = {
            "allowed": pf.get("allowed"),
            "executable_path": pf.get("executable_path"),
            "requires_elevation": pf.get("requires_elevation"),
        }

        # Paso 2: Lanzamiento real por la ruta de produccion (sin mocks).
        resultado = self.cal.launch_application({
            "name": nombre,
            "app_id": identificador,
            "path": ruta,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, f"launch_application no informo exito al abrir {nombre}")

        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        owned_pids = getattr(self.cal, "_last_launch_owned_pids", set())
        owned_hwnds = getattr(self.cal, "_last_launch_owned_hwnds", set())
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))
        launch_state = str(getattr(self.cal, "_last_launch_state", "DESCONOCIDO"))

        self.was_owned = was_owned
        self.resultados["lanzamiento"] = {
            "ok": ok,
            "was_owned": was_owned,
            "root_pid": root_pid,
            "launch_state": launch_state,
            "owned_pids": list(owned_pids),
            "owned_hwnds_count": len(owned_hwnds),
        }

        # Si la aplicacion ya estaba abierta y la API reutilizo la instancia
        # existente, no es propiedad de la prueba: no cierra nada ajeno.
        if not was_owned or root_pid is None:
            self.ciclo_completado = False
            self.resultados["escenario"] = "reutilizacion_instancia_existente"
            self.resultados["cerrado"] = False
            return self.resultados

        # Caso exito: proceso propio lanzado por la prueba.
        self.owned_pid = int(root_pid)
        self.owned_hwnd = None

        # Paso 3: verificar que el proceso lanzado este vivo.
        self.assertTrue(
            self.cal._is_process_alive(self.owned_pid),
            f"el proceso lanzado de {nombre} no esta vivo justo despues del lanzamiento",
        )
        self.assertIn(
            self.owned_pid, owned_pids,
            f"el root_pid {self.owned_pid} no esta en los PIDs propios del lanzamiento",
        )

        # Paso 4: detectar ventana perteneciente al proceso.
        espera = self.cal.wait_for_application_window(
            root_pid=self.owned_pid,
            application_name=nombre,
            app_id=identificador,
            timeout=timeout_ventana,
            poll_interval=0.4,
        )
        self.assertEqual(
            espera["status"], "VENTANA_DETECTADA",
            f"se esperaba ventana detectada para {nombre}, obtuvo: {espera}",
        )
        ventana = espera["window"]
        self.assertIsNotNone(ventana, "no se devolvio objeto de ventana")

        hwnd_creado = self.cal._get_window_handle(ventana)
        self.assertIsNotNone(hwnd_creado, "la ventana detectada no tiene HWND")
        self.owned_hwnd = hwnd_creado

        # El PID de la ventana debe coincidir con el root_pid.
        ventana_pid = self.cal._get_window_process_id(ventana)
        self.assertIsNotNone(ventana_pid, "la ventana detectada no tiene PID")
        self.assertEqual(
            ventana_pid, self.owned_pid,
            "PID de ventana distinto al root_pid",
        )

        # La ventana debe ser visible.
        self.assertTrue(
            self.cal._win32_is_visible(hwnd_creado),
            "la ventana detectada no es visible",
        )

        # No confundir con Visual Studio Code.
        es_vscode = getattr(
            self.cal, "_es_visual_studio_code", lambda hwnd: False
        )(hwnd_creado)
        self.assertFalse(
            es_vscode, "la ventana detectada se confunde con Visual Studio Code"
        )

        self.resultados["deteccion"] = {
            "status": espera["status"],
            "hwnd": hwnd_creado,
            "ventana_pid": ventana_pid,
            "root_pid": self.owned_pid,
            "visible": True,
            "es_visual_studio_code": es_vscode,
            "elapsed_seconds": espera.get("elapsed_seconds", 0.0),
        }

        # Paso 5: verificar estado de la ventana.
        ventana_obj = self.cal._get_window_by_handle(hwnd_creado)
        self.assertIsNotNone(
            ventana_obj, "no se recupero objeto de ventana desde HWND",
        )
        verificacion = self.cal.verify_visible_window_for_application(
            ventana_obj,
            application_name=nombre,
            app_id=identificador,
            root_pid=self.owned_pid,
            owned_pids=owned_pids,
        )
        self.assertTrue(
            verificacion["verificada"],
            f"ventana no verificada para {nombre}: {verificacion.get('reason')}",
        )
        self.assertTrue(verificacion["visible"], "la ventana no es visible")
        self.assertTrue(
            verificacion["corresponde_aplicacion"],
            "la ventana no corresponde a la aplicacion solicitada",
        )
        self.assertTrue(
            verificacion["criterio_pid"], "criterio PID no cumplido",
        )
        self.assertFalse(
            verificacion["es_visual_studio_code"],
            "la ventana se confunde con Visual Studio Code",
        )
        self.assertEqual(
            verificacion["pid"], self.owned_pid,
            "PID de ventana distinto al root_pid",
        )

        self.resultados["verificacion"] = {
            "verificada": verificacion["verificada"],
            "visible": verificacion["visible"],
            "corresponde_aplicacion": verificacion["corresponde_aplicacion"],
            "criterio_pid": verificacion["criterio_pid"],
            "es_visual_studio_code": verificacion["es_visual_studio_code"],
            "pid": verificacion["pid"],
            "root_pid": self.owned_pid,
            "reason": verificacion.get("reason", ""),
        }

        # Paso 6: estabilidad minima del proceso y la ventana.
        estabilidad = self.cal.verify_estabilidad_minima_proceso_ventana(
            root_pid=self.owned_pid,
            window=ventana,
            application_name=nombre,
            app_id=identificador,
            estabilidad_interval=estabilidad_interval,
            estabilidad_checks=estabilidad_checks,
        )
        self.assertEqual(
            estabilidad["status"], "ESTABLE", f"no estable: {estabilidad}",
        )
        self.assertTrue(estabilidad["process_alive"], "el proceso no estuvo vivo")
        self.assertTrue(estabilidad["window_valida"], "la ventana no estuvo valida")
        self.assertTrue(estabilidad["window_visible"], "la ventana no estuvo visible")

        self.resultados["estabilidad"] = {
            "status": estabilidad["status"],
            "process_alive": estabilidad["process_alive"],
            "window_valida": estabilidad["window_valida"],
            "window_visible": estabilidad["window_visible"],
        }

        self.ciclo_completado = True
        self.resultados["escenario"] = "propiedad_exclusiva_prueba"
        self.resultados["cerrado"] = False
        return self.resultados

    def cerrar_propio(self) -> None:
        """Cierra SOLO el proceso lanzado por esta prueba (por PID).

        Tras cerrar, marca owned_pid como None para que tearDown no intente
        cerrarlo de nuevo. Nunca cierra procesos preexistentes del usuario.
        """
        if self.owned_pid is not None:
            subprocess.run(
                ["taskkill", "/PID", str(int(self.owned_pid)), "/F"],
                capture_output=True, text=True, check=False,
            )
            tiempo = time.time() + 10
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(self.owned_pid)):
                    break
                time.sleep(0.25)
            self.assertFalse(
                self.cal._is_process_alive(int(self.owned_pid)),
                "el proceso propio no se termino tras cerrar por PID",
            )
            self.resultados["cerrado"] = True
            self.owned_pid = None
            self.owned_hwnd = None


if __name__ == "__main__":
    unittest.main()
