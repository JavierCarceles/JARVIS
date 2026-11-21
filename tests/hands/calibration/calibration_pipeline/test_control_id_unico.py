# -*- coding: ascii -*-
"""
`control_id` unico en el perfil de calibracion.

Caso real (Windows, Calculadora): PaddleOCR devolvio varios textos "0", "x" y
sin nombre; todos daban el mismo id base (`text:0`...) y el almacen rechazo el
perfil ("control_id duplicado"). Multiplataforma.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.hands.calibration.calibration_pipeline import UICalibrationPipeline


def _item(nombre, top, left, tipo="text", automation_id=""):
    fuentes = []
    if automation_id:
        fuentes = [SimpleNamespace(source="uia", raw={"automation_id": automation_id, "native_role": ""})]
    candidato = SimpleNamespace(type=tipo, name=nombre, sources=fuentes, canonical_id="")
    caja = SimpleNamespace(top=float(top), left=float(left))
    return (candidato, caja, None, (None, None))


class TestControlIdUnico(unittest.TestCase):
    def test_repetidos_reciben_sufijo_en_orden_de_lectura(self):
        items = [
            _item("0", 500, 200),   # boton 0 (abajo)
            _item("0", 100, 900),   # pantalla (arriba)
            _item("", 300, 50),
            _item("", 300, 10),
            _item("x", 10, 10),
            _item("x", 10, 20),
            _item("igual", 50, 50),
        ]
        ids = UICalibrationPipeline._unique_control_ids(items)
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertEqual(ids[1], "text:0#1")
        self.assertEqual(ids[0], "text:0#2")
        self.assertEqual(ids[3], "text:sin_nombre#1")
        self.assertEqual(ids[2], "text:sin_nombre#2")
        self.assertEqual(ids[6], "text:igual", "un id que no se repite se conserva")

    def test_identificador_de_accesibilidad_unico_sin_cambios(self):
        items = [
            _item("Cero", 500, 200, tipo="button", automation_id="num0Button"),
            _item("Uno", 400, 200, tipo="button", automation_id="num1Button"),
        ]
        self.assertEqual(
            UICalibrationPipeline._unique_control_ids(items),
            ["id:num0Button", "id:num1Button"],
        )

    def test_sufijo_no_choca_con_un_id_existente(self):
        items = [_item("a", 0, 0), _item("a", 10, 0), _item("a#1", 20, 0)]
        ids = UICalibrationPipeline._unique_control_ids(items)
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_mismo_resultado_en_otra_ejecucion(self):
        items = [_item("0", 500, 200), _item("0", 100, 900)]
        self.assertEqual(
            UICalibrationPipeline._unique_control_ids(items),
            UICalibrationPipeline._unique_control_ids(list(reversed(items)))[::-1],
        )


if __name__ == "__main__":
    unittest.main()
