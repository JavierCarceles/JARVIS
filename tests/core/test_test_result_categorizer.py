# -*- coding: utf-8 -*-
"""Tests unitarios para TestResultCategorizer (unidad 3.8.5.6.5).

Verifica que los resultados de prueba se registren por categoria separada
(SIMULADO, UNIT_MOCKS, INTEGRACION_OS, APERTURA_GUI) y que los conteos nunca
se mezclen entre categorias.
"""

import os
import sys
import unittest

# Asegurar que src/ este en el path
_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
_SRC_DIR = os.path.abspath(_SRC_DIR)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

_ROOT_DIR = os.path.abspath(os.path.join(_SRC_DIR, ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from src.core.test_result_categorizer import (
    CategoriaResultadoTest,
    ResultadoTest,
    TestResultCategorizer as _Categorizer,
    categorizar_archivo_test,
)


class TestCategorizerRegistroSeparado(unittest.TestCase):
    """Verifica que cada categoria lleve su propio contador independiente."""

    def setUp(self):
        self.cat = _Categorizer()

    def test_registro_unit_mocks_incrementa_solo_esa_categoria(self):
        self.cat.registrar("test_preflight_check", CategoriaResultadoTest.UNIT_MOCKS, "PASSED", tiene_mock=True)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.UNIT_MOCKS, "PASSED"), 1)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.INTEGRACION_OS, "PASSED"), 0)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.APERTURA_GUI, "PASSED"), 0)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.SIMULADO, "PASSED"), 0)

    def test_registro_integracion_os_no_afecta_unit_mocks(self):
        self.cat.registrar("test_apertura_charmap", CategoriaResultadoTest.INTEGRACION_OS, "PASSED", usa_recursos_reales=True)
        self.cat.registrar("test_preflight_mock", CategoriaResultadoTest.UNIT_MOCKS, "PASSED", tiene_mock=True)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.INTEGRACION_OS, "TOTAL"), 1)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.UNIT_MOCKS, "TOTAL"), 1)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.APERTURA_GUI, "TOTAL"), 0)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.SIMULADO, "TOTAL"), 0)

    def test_registro_apertura_gui_contador_independiente(self):
        self.cat.registrar("test_notepad_gui", CategoriaResultadoTest.APERTURA_GUI, "PASSED", verificacion_visual=True)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.APERTURA_GUI, "PASSED"), 1)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.APERTURA_GUI, "TOTAL"), 1)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.INTEGRACION_OS, "TOTAL"), 0)

    def test_registro_simulado_separado_de_reales(self):
        self.cat.registrar("test_fabricado", CategoriaResultadoTest.SIMULADO, "PASSED")
        self.cat.registrar("test_real", CategoriaResultadoTest.INTEGRACION_OS, "PASSED", usa_recursos_reales=True)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.SIMULADO, "TOTAL"), 1)
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.INTEGRACION_OS, "TOTAL"), 1)
        self.assertTrue(self.cat.tiene_resultados_simulados())
        self.assertTrue(self.cat.tiene_resultados_reales())

    def test_conteo_estado_desconocido_retorna_cero(self):
        self.cat.registrar("test_x", CategoriaResultadoTest.UNIT_MOCKS, "PASSED")
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.UNIT_MOCKS, "ERROR"), 0)

    def test_conteo_sin_estado_retorna_total(self):
        self.cat.registrar("test_a", CategoriaResultadoTest.INTEGRACION_OS, "PASSED")
        self.cat.registrar("test_b", CategoriaResultadoTest.INTEGRACION_OS, "FAILED")
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.INTEGRACION_OS), 2)


class TestCategorizerSeparacionConteos(unittest.TestCase):
    """Verifica que los conteos nunca se mezclan entre categorias."""

    def setUp(self):
        self.cat = _Categorizer()

    def test_no_existe_contador_global_mezclado(self):
        self.cat.registrar("t1", CategoriaResultadoTest.UNIT_MOCKS, "PASSED")
        self.cat.registrar("t2", CategoriaResultadoTest.INTEGRACION_OS, "PASSED")
        self.cat.registrar("t3", CategoriaResultadoTest.APERTURA_GUI, "PASSED")
        self.cat.registrar("t4", CategoriaResultadoTest.SIMULADO, "PASSED")
        # Cada categoria debe tener exactamente 1 resultado
        for cat in CategoriaResultadoTest:
            self.assertEqual(self.cat.conteo(cat, "TOTAL"), 1)
        # La suma de categorias debe igualar el total de registros
        self.assertTrue(self.cat.verificar_separacion())

    def test_reporte_muestra_lineas_separadas_por_categoria(self):
        self.cat.registrar("t1", CategoriaResultadoTest.UNIT_MOCKS, "PASSED")
        self.cat.registrar("t2", CategoriaResultadoTest.INTEGRACION_OS, "FAILED")
        reporte = self.cat.reporte()
        self.assertIn("UNIT_MOCKS", reporte)
        self.assertIn("INTEGRACION_OS", reporte)
        self.assertIn("APERTURA_GUI", reporte)
        self.assertIn("SIMULADO", reporte)
        # Cada categoria aparece en su propia linea con sus propios conteos
        self.assertIn("UNIT_MOCKS: PASSED=1 / FAILED=0", reporte)
        self.assertIn("INTEGRACION_OS: PASSED=0 / FAILED=1", reporte)

    def test_resultados_por_categoria_devuelve_solo_esa_categoria(self):
        self.cat.registrar("t1", CategoriaResultadoTest.UNIT_MOCKS, "PASSED")
        self.cat.registrar("t2", CategoriaResultadoTest.INTEGRACION_OS, "PASSED")
        self.cat.registrar("t3", CategoriaResultadoTest.UNIT_MOCKS, "FAILED")
        unit_results = self.cat.resultados_por_categoria(CategoriaResultadoTest.UNIT_MOCKS)
        os_results = self.cat.resultados_por_categoria(CategoriaResultadoTest.INTEGRACION_OS)
        self.assertEqual(len(unit_results), 2)
        self.assertEqual(len(os_results), 1)
        for r in unit_results:
            self.assertEqual(r.categoria, CategoriaResultadoTest.UNIT_MOCKS)
        for r in os_results:
            self.assertEqual(r.categoria, CategoriaResultadoTest.INTEGRACION_OS)

    def test_conteo_todas_categorias_devuelve_copias_independientes(self):
        self.cat.registrar("t1", CategoriaResultadoTest.UNIT_MOCKS, "PASSED")
        copias = self.cat.conteo_todas_categorias()
        # Modificar la copia no debe afectar al original
        copias[CategoriaResultadoTest.UNIT_MOCKS]["PASSED"] = 999
        self.assertEqual(self.cat.conteo(CategoriaResultadoTest.UNIT_MOCKS, "PASSED"), 1)


class TestCategorizerHeuristicaArchivo(unittest.TestCase):
    """Verifica la heuristica de categorizacion de archivos de prueba."""

    def test_archivo_entorno_real_apertura_se_categoriza_como_apertura_gui(self):
        # Usar un archivo existente de la suite si esta disponible
        ruta = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "tests",
            "hands", "test_apertura_aplicacion_cerrada_entorno_real.py",
        )
        ruta = os.path.abspath(ruta)
        if os.path.exists(ruta):
            cat = categorizar_archivo_test(ruta)
            self.assertIn(cat, (CategoriaResultadoTest.INTEGRACION_OS, CategoriaResultadoTest.APERTURA_GUI))

    def test_categorizar_archivo_inexistente_retorna_unit_mocks(self):
        cat = categorizar_archivo_test("ruta/que/no/existe.py")
        self.assertEqual(cat, CategoriaResultadoTest.UNIT_MOCKS)


if __name__ == "__main__":
    unittest.main()
