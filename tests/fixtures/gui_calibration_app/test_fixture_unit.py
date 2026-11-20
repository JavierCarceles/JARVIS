# -*- coding: ascii -*-
"""
Test unitario (offscreen) de la fixture de calibracion GUI.

Verifica que la ventana se construye con todos los controles, que cada uno
expone su identificador estable, que la geometria coincide con la referencia
declarada y que las acciones inocuas instrumentadas solo incrementan un
contador de memoria (sin efectos secundarios sobre el equipo ni datos del
usuario). Tambien verifica las variantes de la matriz controlada (3.8.6.10.4):
tema claro/oscuro, tamano de fuente, zoom interno y control dinamico visible/
oculto. Se ejecuta con el plugin offscreen de Qt, sin pantalla real.
"""

from __future__ import annotations

import os
import unittest

# Qt fuera de pantalla para no requerir display real.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.fixtures.gui_calibration_app.app import CalibrationAppWindow, crear_aplicacion, FixtureConfig
from tests.fixtures.gui_calibration_app.controls import CONTROL_SPECS, CONTROL_DINAMICO_SPEC


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

    # ------------------------------------------------------------------ variantes 3.8.6.10.4

    def test_config_defecto_es_linea_base(self):
        """La configuracion por defecto replica la linea base: maximizada,
        claro, fuente 9, zoom 1.0, menu cerrado, sin scroll, dinamico oculto."""
        cfg = FixtureConfig()
        self.assertEqual(cfg.estado_ventana, "maximizada")
        self.assertEqual(cfg.tema, "claro")
        self.assertEqual(cfg.tamano_fuente, 9)
        self.assertEqual(cfg.zoom_interno, 1.0)
        self.assertFalse(cfg.menu_abierto)
        self.assertFalse(cfg.scroll_desplazado)
        self.assertFalse(cfg.control_dinamico_visible)

    def test_ventana_restaurada(self):
        cfg = FixtureConfig(estado_ventana="restaurada")
        app, ventana = crear_aplicacion(config=cfg)
        self.assertEqual(ventana.config.estado_ventana, "restaurada")
        ventana.close()

    def test_tema_oscuro(self):
        cfg = FixtureConfig(tema="oscuro")
        app, ventana = crear_aplicacion(config=cfg)
        self.assertEqual(ventana.config.tema, "oscuro")
        ventana.close()

    def test_tamano_fuente(self):
        cfg = FixtureConfig(tamano_fuente=16)
        app, ventana = crear_aplicacion(config=cfg)
        self.assertEqual(ventana.config.tamano_fuente, 16)
        fuente = app.font()
        self.assertEqual(fuente.pointSize(), 16)
        ventana.close()

    def test_zoom_escala_geometrias(self):
        cfg = FixtureConfig(zoom_interno=1.25)
        app, ventana = crear_aplicacion(config=cfg)
        self.assertEqual(ventana.config.zoom_interno, 1.25)
        # btn_aceptar: nominal [20, 20, 100, 32] -> [25, 25, 125, 40] a zoom 1.25
        geo = ventana.get_control_geometry("btn_aceptar")
        self.assertEqual(geo, [25, 25, 125, 40], "Geometria no escalada por el zoom")
        ventana.close()

    def test_control_dinamico_visible(self):
        cfg = FixtureConfig(control_dinamico_visible=True)
        app, ventana = crear_aplicacion(config=cfg)
        self.assertTrue(ventana.config.control_dinamico_visible)
        self.assertIn("ctrl_dinamico", ventana._control_widgets,
                      "El control dinamico debe crearse cuando se solicita")
        geo = ventana.get_control_geometry("ctrl_dinamico")
        self.assertEqual(geo, [900, 440, 140, 32])
        ventana.close()

    def test_control_dinamico_oculto_por_defecto(self):
        cfg = FixtureConfig()
        app, ventana = crear_aplicacion(config=cfg)
        self.assertFalse(ventana.config.control_dinamico_visible)
        self.assertNotIn("ctrl_dinamico", ventana._control_widgets,
                         "El control dinamico no debe crearse por defecto")
        ventana.close()

    def test_truth_ground_incluye_dinamico(self):
        cfg = FixtureConfig(control_dinamico_visible=True)
        app, ventana = crear_aplicacion(config=cfg)
        tg = ventana.get_truth_ground()
        ids = [c["id"] for c in tg["controles"]]
        self.assertIn("ctrl_dinamico", ids,
                      "La verdad-terreno debe incluir el control dinamico cuando es visible")
        ventana.close()
        cfg2 = FixtureConfig()
        app2, ventana2 = crear_aplicacion(config=cfg2)
        tg2 = ventana2.get_truth_ground()
        ids2 = [c["id"] for c in tg2["controles"]]
        self.assertNotIn("ctrl_dinamico", ids2,
                         "La verdad-terreno no debe incluir el control dinamico oculto")
        ventana2.close()

    def test_zoom_reflejado_en_truth_ground(self):
        cfg = FixtureConfig(zoom_interno=1.5)
        app, ventana = crear_aplicacion(config=cfg)
        tg = ventana.get_truth_ground()
        ref = {c["id"]: c["geometry"] for c in tg["controles"] if c["geometry"] is not None}
        # btn_aceptar nominal [20, 20, 100, 32] -> [30, 30, 150, 48] a zoom 1.5
        self.assertEqual(ref["btn_aceptar"], [30, 30, 150, 48])
        ventana.close()


if __name__ == "__main__":
    unittest.main()
