# -*- coding: ascii -*-
"""
Prueba de la propia aplicacion de chat de prueba (Qt sin pantalla).

Comprueba con clics reales de Qt (QTest) que la app hace lo que la prueba GUI
real espera y que su registro de eventos (la verdad independiente) es fiel:
seleccionar Manolito abre su chat, escribir "hola" y pulsar Enviar lo anade al
historial y registra el evento; "Borrar historial" registra "borrado".
Multiplataforma (QT_QPA_PLATFORM=offscreen); se salta si no hay PySide6.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from tests.fixtures.gui_chat_app.app import ChatWindow, crear_aplicacion
except ImportError as exc:  # pragma: no cover - entorno sin PySide6
    raise unittest.SkipTest("PySide6 no disponible: %s" % exc)


class TestChatFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self._tmp.name, "eventos.jsonl")
        self.app, _ = crear_aplicacion()
        self.ventana = ChatWindow(self.ruta)
        self.ventana.show()

    def tearDown(self):
        self.ventana.close()
        self._tmp.cleanup()

    def _eventos(self):
        with open(self.ruta, encoding="utf-8") as fichero:
            return [json.loads(linea) for linea in fichero if linea.strip()]

    def _clic_item(self, lista, texto):
        item = lista.findItems(texto, Qt.MatchExactly)[0]
        rect = lista.visualItemRect(item)
        QTest.mouseClick(lista.viewport(), Qt.LeftButton, pos=rect.center())

    def test_mandar_hola_a_manolito(self):
        self.assertFalse(self.ventana.panel_chat.isVisible())
        self._clic_item(self.ventana.contactos, "Manolito")
        self.assertTrue(self.ventana.panel_chat.isVisible())
        self.assertEqual(self.ventana.titulo_chat.text(), "Chat con Manolito")
        QTest.mouseClick(self.ventana.campo, Qt.LeftButton)
        QTest.keyClicks(self.ventana.campo, "hola")
        QTest.mouseClick(self.ventana.enviar, Qt.LeftButton)
        self.assertEqual(self.ventana.historial.item(0).text(), "hola")
        eventos = [{k: v for k, v in e.items() if k != "t"} for e in self._eventos()]
        self.assertIn({"tipo": "contacto_seleccionado", "contacto": "Manolito"}, eventos)
        self.assertIn({"tipo": "mensaje_enviado", "contacto": "Manolito", "texto": "hola"}, eventos)

    def test_ajustes_pestanas_y_borrar(self):
        self._clic_item(self.ventana.secciones, "Ajustes")
        self.assertEqual(self.ventana.paginas.currentIndex(), 1)
        self.ventana.pestanas.setCurrentIndex(1)
        QTest.mouseClick(self.ventana.borrar, Qt.LeftButton)
        tipos = [e["tipo"] for e in self._eventos()]
        self.assertIn("seccion", tipos)
        self.assertIn("pestana", tipos)
        self.assertIn("borrado", tipos)

    def test_enviar_vacio_no_registra_mensaje(self):
        self._clic_item(self.ventana.contactos, "Lucia")
        QTest.mouseClick(self.ventana.enviar, Qt.LeftButton)
        self.assertNotIn("mensaje_enviado", [e["tipo"] for e in self._eventos()])


if __name__ == "__main__":
    unittest.main()
