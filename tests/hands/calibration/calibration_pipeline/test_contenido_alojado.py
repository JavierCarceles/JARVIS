# -*- coding: ascii -*-
"""
Espera al contenido real de las ventanas de ApplicationFrameHost.

Caso real (Windows 11, Configuracion): la ventana de una app empaquetada
muestra primero una pantalla de carga estable (logo sobre fondo liso); la
estabilidad de frames pasaba a los 0,3 s, la accesibilidad solo veia 4
controles del marco, el OCR y Qwen3-VL no encontraban nada y la puerta de
calidad rechazaba todo. La calibracion debe esperar (con limite) a que el
arbol tenga controles accionables. Multiplataforma (adaptador sintetico).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.hands.calibration.calibration_pipeline import CalibrationReport, UICalibrationPipeline


def _nodo(accionable=True):
    return SimpleNamespace(enabled=accionable, actions=["invoke"] if accionable else [], native_patterns=[])


class _AdaptadorArbol:
    """Devuelve en cada lectura el siguiente numero de controles accionables."""

    def __init__(self, secuencia):
        self.secuencia = list(secuencia)
        self.lecturas = 0

    def get_accessibility_tree(self, window_id, pid=None):
        indice = min(self.lecturas, len(self.secuencia) - 1)
        self.lecturas += 1
        nodos = [_nodo() for _ in range(self.secuencia[indice])] + [_nodo(False)]
        return SimpleNamespace(ok=True, value=SimpleNamespace(nodes=nodos), error=None)


def _ventana(identidad):
    return SimpleNamespace(window_id=7, pid=70, app_identity=identidad)


class TestContenidoAlojado(unittest.TestCase):
    def _pipeline(self, timeout=5.0):
        pipeline = UICalibrationPipeline(hosted_content_timeout=timeout)
        # Sin esperas reales entre sondeos.
        pipeline._wait_event = SimpleNamespace(wait=lambda _segundos: None)
        return pipeline

    def test_espera_hasta_que_aparece_el_contenido(self):
        adaptador = _AdaptadorArbol([2, 2, 3, 12])
        informe = CalibrationReport(app_id="x", app_name="configuracion")
        listo = self._pipeline()._wait_hosted_content(adaptador, _ventana("ApplicationFrameHost.exe"), informe)
        self.assertTrue(listo)
        self.assertEqual(adaptador.lecturas, 4)
        self.assertEqual(informe.metrics["hosted_content"]["actionable"], 12)
        self.assertTrue(informe.metrics["hosted_content"]["ready"])
        self.assertEqual(informe.warnings, [])

    def test_otras_ventanas_no_esperan(self):
        adaptador = _AdaptadorArbol([0])
        informe = CalibrationReport(app_id="x", app_name="notepad")
        listo = self._pipeline()._wait_hosted_content(adaptador, _ventana("notepad.exe"), informe)
        self.assertFalse(listo)
        self.assertEqual(adaptador.lecturas, 0)
        self.assertNotIn("hosted_content", informe.metrics)

    def test_sin_contenido_agota_el_limite_y_avisa(self):
        adaptador = _AdaptadorArbol([1])
        informe = CalibrationReport(app_id="x", app_name="configuracion")
        listo = self._pipeline(timeout=0.05)._wait_hosted_content(
            adaptador, _ventana("applicationframehost.exe"), informe
        )
        self.assertFalse(listo)
        self.assertFalse(informe.metrics["hosted_content"]["ready"])
        self.assertTrue(any("no mostro contenido" in aviso for aviso in informe.warnings))


if __name__ == "__main__":
    unittest.main()
