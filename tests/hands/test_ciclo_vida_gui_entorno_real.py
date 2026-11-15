# -*- coding: utf-8 -*-
"""
Verificacion real de entorno para la unidad 3.8.5.6.11.

Control de ciclo de vida de cada test GUI usando la clase base reutilizable
CicloVidaGUITestCase:
  (1) abrir la aplicacion mediante la ruta de produccion
      (CalibrationManager.launch_application, sin mocks);
  (2) verificar proceso y ventana pertenecientes a la aplicacion lanzada;
  (3) cerrar solo la ventana/proceso creado por la prueba tras verificar el
      estado.

Se ejecuta con charmap.exe (Mapa de caracteres), una aplicacion GUI inocua de
la allowlist del equipo, una aplicacion a la vez, nunca en lote ni en paralelo.
No se envia teclado ni raton. No se cierra Visual Studio Code ni ventanas
preexistentes del usuario.
"""

import unittest

from tests.hands.test_base_ciclo_vida_gui import CicloVidaGUITestCase


_CHARMAP_NOMBRE = "Mapa de caracteres"
_CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"


class TestCicloVidaGUIEntornoReal(CicloVidaGUITestCase):
    """3.8.5.6.11: ciclo de vida GUI real con charmap.exe via clase base."""

    APP_NAME = _CHARMAP_NOMBRE
    APP_PATH = _CHARMAP_PATH
    APP_ID = ""

    def test_3_8_5_6_11_ciclo_vida_gui_charmap(self):
        """Ciclo completo: preflight -> lanzamiento -> verificar proceso y
        ventana -> estabilidad -> cerrar solo lo propio -> preservar baseline."""
        ciclo = self.ejecutar_ciclo_vida()

        if not ciclo["lanzamiento"]["was_owned"]:
            # charmap ya estaba abierto; la API reutilizo la instancia
            # existente. No cierra nada ajeno: escenario de reutilizacion.
            self.skipTest(
                "charmap.exe ya estaba abierto en el SO; la API reutilizo la "
                "instancia existente (was_owned=False). No se cierra nada ajeno. "
                "Escenario de reutilizacion registrado; la verificacion de "
                "propiedad exclusiva requiere que charmap no este abierto."
            )

        # Propiedad exclusiva de la prueba: verificar campos del ciclo.
        self.assertTrue(self.ciclo_completado, "el ciclo de vida no se completo")
        self.assertIsNotNone(
            ciclo["lanzamiento"].get("root_pid"), "no se obtuvo root_pid"
        )
        self.assertIsNotNone(
            ciclo["deteccion"].get("hwnd"), "no se obtuvo HWND de la ventana"
        )
        self.assertTrue(ciclo["preflight"]["allowed"], "preflight no permiso charmap")
        self.assertTrue(ciclo["lanzamiento"]["ok"], "lanzamiento no informo exito")
        self.assertEqual(
            ciclo["deteccion"]["status"], "VENTANA_DETECTADA",
            "no se detecto la ventana de charmap",
        )
        self.assertTrue(ciclo["verificacion"]["verificada"], "ventana no verificada")
        self.assertEqual(
            ciclo["verificacion"]["pid"], ciclo["lanzamiento"]["root_pid"],
            "PID de ventana distinto al root_pid",
        )
        self.assertFalse(
            ciclo["verificacion"]["es_visual_studio_code"],
            "la ventana se confunde con Visual Studio Code",
        )
        self.assertEqual(ciclo["estabilidad"]["status"], "ESTABLE",
                         "proceso/ventana no estables")

        # Paso 3: cerrar solo la ventana/proceso creado por la prueba.
        self.cerrar_propio()

        # Verificar que el proceso propio termino y no hay residuales.
        self.assertFalse(
            self.cal._is_process_alive(
                int(ciclo["lanzamiento"]["root_pid"])),
            "el proceso propio de charmap siguio vivo tras el cierre",
        )
        self.assertTrue(ciclo["cerrado"], "el cierre propio no se registro")


if __name__ == "__main__":
    unittest.main()
