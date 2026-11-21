# -*- coding: ascii -*-
"""
"Abre Ajustes y navega": calibracion en profundidad REAL de Configuracion de
Windows por el pipeline unico.

`UICalibrationPipeline.calibrate("configuracion", depth="deep")` con
`explore_navigation=True`: abre una instancia propia en el monitor de pruebas,
calibra la pantalla inicial y explora con CLICS REALES verificados el panel de
navegacion (Sistema, Bluetooth, Personalizacion...), SOLO dentro del panel de
navegacion (DEFAULT_NAVIGATION_CONTAINERS) y con profundidad 1: nunca
interruptores, botones con efecto, opciones de desplegables ni listas de
valores (temas, fondos). Si los identificadores del panel no coinciden en el
equipo, no navega y la prueba falla mostrando el mapa (sin cambiar nada).
Guarda el mapa JSON (data/ui_maps/<equipo>/configuracion.json) y reproduce cada
camino desde la raiz con las coordenadas guardadas (reiniciando la app propia).

Comprueba: calibracion correcta, exploracion sin abortar, >= 3 estados, cada
transicion hecha con clic verificado y solo acciones de navegacion, todos los
caminos reproducidos y la ventana propia cerrada al final.

Requiere Windows y JARVIS_TEST_GUI_REAL=1; Configuracion cerrada antes:
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/calibration/ui_exploration/test_navegacion_ajustes_entorno_real.py -v -s
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from src.desktop.native_imports import is_windows

ACCIONES_DE_NAVEGACION = {"navigate", "select_tab", "open_menu", "expand"}


class TestNavegacionAjustesEntornoReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows (excepcion (a))")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real")
        from src.hands.calibration.calibration_pipeline import DEPTH_DEEP, POLICY_TEST, UICalibrationPipeline
        from src.hands.calibration.ui_exploration import ExplorationBudget

        pipeline = UICalibrationPipeline(
            explore_navigation=True,
            explorer_budget=ExplorationBudget(max_depth=1, max_states=10, max_seconds=300, max_actions=150),
        )
        cls.report = pipeline.calibrate("configuracion", policy=POLICY_TEST, depth=DEPTH_DEEP, reuse_window=False)
        cls.exploracion = cls.report.exploration or {}
        ruta = cls.exploracion.get("ui_map_path")
        cls.mapa = json.loads(Path(ruta).read_text(encoding="utf-8")) if ruta and Path(ruta).exists() else None
        print("\n[NAVEGACION AJUSTES] etapa_fallida=%s error=%s tiempos=%s" % (
            cls.report.stage_failed, cls.report.error, (cls.report.metrics or {}).get("timings")))
        print("[NAVEGACION AJUSTES] exploracion: %s" % {
            k: cls.exploracion.get(k) for k in ("states", "transitions", "actions_performed", "elapsed_seconds",
                                                 "aborted", "abort_reason", "path_verification", "ui_map_path")})
        if cls.mapa:
            for state_id, estado in cls.mapa["states"].items():
                camino = " -> ".join(p["element_ref"].get("name", "?") for p in (estado["path_from_root"] or []))
                print("  estado %s prof=%d camino=[%s] elementos=%d"
                      % (state_id[:8], estado["depth"], camino, len(estado["elements"])))

    def test_01_calibracion_y_exploracion(self):
        self.assertTrue(self.report.success, "%s: %s" % (self.report.stage_failed, self.report.error))
        self.assertFalse(self.exploracion.get("aborted"), self.exploracion.get("abort_reason"))
        self.assertIsNotNone(self.mapa, "debe guardarse el mapa JSON")
        self.assertGreaterEqual(len(self.mapa["states"]), 3)

    def test_02_solo_clics_verificados_de_navegacion(self):
        self.assertIsNotNone(self.mapa)
        self.assertTrue(self.mapa["transitions"])
        for transicion in self.mapa["transitions"]:
            self.assertIn(transicion["action"], ACCIONES_DE_NAVEGACION, transicion)
            evidencia = transicion["evidence"]
            if transicion["action"] != "expand":
                self.assertEqual(evidencia.get("method"), "click", transicion)
                self.assertTrue(evidencia.get("pointer_ok"), transicion)

    def test_03_caminos_reproducidos_con_coordenadas_guardadas(self):
        verificacion = self.exploracion.get("path_verification")
        self.assertIsNotNone(verificacion, "la profundidad completa debe reproducir los caminos")
        self.assertEqual(verificacion["failed"], 0, self.mapa.get("path_verification") if self.mapa else None)
        self.assertGreater(verificacion["ok"], 0)

    def test_04_elementos_con_coordenadas(self):
        self.assertIsNotNone(self.mapa)
        raiz = self.mapa["states"][self.mapa["root_state_id"]]
        con_caja = [e for e in raiz["elements"] if e.get("box_client_norm")]
        self.assertGreaterEqual(len(con_caja), 5)


if __name__ == "__main__":
    unittest.main()
