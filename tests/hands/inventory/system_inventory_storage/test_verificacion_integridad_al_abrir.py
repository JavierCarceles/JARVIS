# -*- coding: ascii -*-
"""
Verificacion de integridad al abrir el inventario.

Con el inventario real (millones de entradas) `PRAGMA quick_check` +
`integrity_check` tardaban decenas de minutos en cada apertura (por ejemplo al
guardar un perfil de calibracion). Bases pequenas: verificacion completa como
antes. Bases grandes: cada tabla con sus indices salvo `file_entries`.
Multiplataforma (SQLite real en un directorio temporal).
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from src.hands.inventory.system_inventory_storage import SystemInventoryStorage


class TestVerificacionAlAbrir(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.db = Path(self._tmp.name) / "inventario.sqlite3"
        storage = SystemInventoryStorage(self.db)
        storage.initialize(machine_id_actual="maquina-prueba")
        storage.close()

    def tearDown(self):
        self._tmp.cleanup()

    def _abrir(self):
        return SystemInventoryStorage(self.db)

    def test_base_pequena_verificacion_completa(self):
        storage = self._abrir()
        try:
            resultado = storage.verify_integrity_al_abrir()
        finally:
            storage.close()
        self.assertTrue(resultado["ok"], resultado)
        self.assertEqual(resultado["modo"], "completa")
        self.assertEqual(resultado["integrity_check"], "ok")

    def test_base_grande_verificacion_ligera_sin_file_entries(self):
        storage = self._abrir()
        try:
            with mock.patch.object(SystemInventoryStorage, "INTEGRIDAD_COMPLETA_MAX_BYTES", 0), \
                    mock.patch.object(storage, "verify_integrity",
                                      side_effect=AssertionError("no debe ejecutarse")):
                resultado = storage.verify_integrity_al_abrir()
        finally:
            storage.close()
        self.assertTrue(resultado["ok"], resultado)
        self.assertEqual(resultado["modo"], "ligera")
        self.assertNotIn("file_entries", resultado["tablas_comprobadas"])
        self.assertIn("calibration_profiles", resultado["tablas_comprobadas"])
        self.assertIn("machines", resultado["tablas_comprobadas"])

    def test_variable_de_entorno_fuerza_la_completa(self):
        storage = self._abrir()
        try:
            with mock.patch.object(SystemInventoryStorage, "INTEGRIDAD_COMPLETA_MAX_BYTES", 0), \
                    mock.patch.dict("os.environ", {SystemInventoryStorage.ENV_VERIFICACION_COMPLETA: "1"}):
                resultado = storage.verify_integrity_al_abrir()
        finally:
            storage.close()
        self.assertEqual(resultado["modo"], "completa")
        self.assertTrue(resultado["ok"], resultado)

    def test_initialize_usa_la_verificacion_al_abrir(self):
        storage = self._abrir()
        try:
            with mock.patch.object(SystemInventoryStorage, "INTEGRIDAD_COMPLETA_MAX_BYTES", 0), \
                    mock.patch.object(storage, "verify_integrity",
                                      side_effect=AssertionError("no debe ejecutarse")):
                version = storage.initialize(machine_id_actual="maquina-prueba")
        finally:
            storage.close()
        self.assertGreater(version, 0)

    def test_fichero_que_no_es_sqlite_falla_en_ligera(self):
        roto = Path(self._tmp.name) / "roto.sqlite3"
        roto.write_bytes(b"esto no es una base sqlite" * 100)
        storage = SystemInventoryStorage(roto)
        try:
            with mock.patch.object(SystemInventoryStorage, "INTEGRIDAD_COMPLETA_MAX_BYTES", 0):
                resultado = storage.verify_integrity_al_abrir()
        except sqlite3.DatabaseError:
            resultado = {"ok": False}
        finally:
            try:
                storage.close()
            except Exception:
                pass
        self.assertFalse(resultado["ok"])


if __name__ == "__main__":
    unittest.main()
