# -*- coding: ascii -*-
"""
Test unitario (offscreen) de la fixture de calibracion GUI.

Verifica que la ventana se construye con todos los controles, que cada uno
expone su identificador estable, que la geometria coincide con la referencia
declarada y que las acciones inocuas instrumentadas solo incrementan un
contador de memoria (sin efectos secundarios sobre el equipo ni datos del
usuario). Se ejecuta con el plugin offscreen de Qt, sin pantalla real.
"""

from __future__ import annotations

import os
import unittest

# Qt fuera de pantalla para no requerir display real.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.fixtures.gui_calibration_app.app import CalibrationAppWindow, crear_aplicacion
from tests.fixtures.gui_calibration_app.controls import CONTROL_SPECS


class TestCalibracionFixtureUnit(unittest.TestCase):
    """Verificacion de construccion de la fixture sin display real."""

    _app_creado = False

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:
            cls._app_creado = True
        cls.app, cls.ventana = crear_aplicacion()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.ventana.close()
        except Exception:
            pass
        if cls._app_creado:
            try:
                cls.app.quit()
            except Exception:
                pass
        cls.app = None
        cls.ventana = None

    def test_construye_todos_los_controles(self):
        for spec in CONTROL_SPECS:
            cid = spec["id"]
            self.assertIn(
                cid, self.ventana._control_widgets,
                "Falta el control %s" % cid,
            )

    def test_identificador_estable_en_todos_los_controles(self):
        for spec in CONTROL_SPECS:
            cid = spec["id"]
            w = self.ventana._control_widgets[cid]
            self.assertEqual(w.objectName(), cid,
                             "objectName de %s no es el identificador" % cid)
            # canvas_mano es el unico control dibujado a mano sin accesibilidad
            if cid == "canvas_mano":
                self.assertEqual(w.accessibleName(), "",
                                 "canvas_mano no debe exponer nombre semantico")
            else:
                self.assertEqual(w.accessibleName(), cid,
                                 "accessibleName de %s no es el identificador" % cid)

    def test_geometria_coincide_con_referencia(self):
        for spec in CONTROL_SPECS:
            ref = spec["geometry"]
            if ref is None:
                continue
            cid = spec["id"]
            geo = self.ventana.get_control_geometry(cid)
            self.assertIsNotNone(geo, "Sin geometria para %s" % cid)
            self.assertEqual(geo[0], ref[0], "x de %s" % cid)
            self.assertEqual(geo[1], ref[1], "y de %s" % cid)
            self.assertEqual(geo[2], ref[2], "ancho de %s" % cid)
            self.assertEqual(geo[3], ref[3], "alto de %s" % cid)

    def test_accion_inocua_instrumentada_sin_efectos_secundarios(self):
        antes = dict(self.ventana.action_counts())
        self.ventana._disparar("accion_btn_aceptar")
        despues = dict(self.ventana.action_counts())
        self.assertEqual(
            despues["accion_btn_aceptar"],
            antes["accion_btn_aceptar"] + 1,
            "La accion inocua debe incrementar su contador",
        )
        # Las demas acciones no cambian: efecto aislado, sin efectos secundarios
        for accion, valor in antes.items():
            if accion != "accion_btn_aceptar":
                self.assertEqual(
                    despues[accion], valor,
                    "La accion %s no debe cambiar por accion_btn_aceptar" % accion,
                )

    def test_control_sin_accesibilidad_no_tiene_identidad_semantica(self):
        canvas = self.ventana._control_widgets["canvas_mano"]
        self.assertEqual(canvas.accessibleName(), "")
        self.assertIsInstance(canvas.objectName(), str)


if __name__ == "__main__":
    unittest.main()
