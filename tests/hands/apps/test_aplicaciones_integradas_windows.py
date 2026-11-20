# -*- coding: ascii -*-
"""
JARVIS con Windows en otro idioma: aplicaciones integradas, busqueda,
verificacion de ventana por AUMID y filtro de herramientas de riesgo.

El usuario puede pedir "calculadora" en un Windows en ingles (menu Inicio:
"Calculator") o "notepad" en uno en espanol ("Bloc de notas"). Multiplataforma:
las fuentes del SO se sustituyen por datos con la forma real de Get-StartApps,
y la lectura del AUMID de una ventana se inyecta.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.hands.apps.aplicaciones_integradas_windows import (
    es_ruta_del_sistema_windows,
    familia_de_aumid,
    normalizar_nombre_aplicacion,
    variantes_para,
)
from src.hands.apps.application_discovery import ApplicationDiscovery
from src.hands.apps.application_launch_classifier import LaunchClassifier
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.apps.launch_windows import WindowsLaunchAdapter
from src.hands.apps.platform_launch import TARGET_AUMID, LaunchTarget
from src.hands.calibration.calibration_manager import CalibrationManager

AUMID_CALC = "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
AUMID_NOTEPAD = "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"


class TestVariantes(unittest.TestCase):
    def test_nombre_en_cualquier_idioma_da_las_mismas_variantes(self):
        es = variantes_para("Calculadora")
        en = variantes_para("calculator")
        exe = variantes_para("calc.exe")
        self.assertIsNotNone(es)
        self.assertEqual(es, en)
        self.assertEqual(es, exe)
        self.assertTrue(es.coincide_nombre("Calculator"))
        self.assertTrue(es.coincide_nombre("Calculadora"))
        self.assertTrue(es.coincide_app_id(AUMID_CALC))
        self.assertTrue(es.coincide_ejecutable("CALC.EXE"))

    def test_tildes_y_mayusculas(self):
        self.assertEqual(normalizar_nombre_aplicacion("Configuraci\u00f3n"), "configuracion")
        self.assertIsNotNone(variantes_para("CONFIGURACI\u00d3N"))
        self.assertTrue(variantes_para("settings").coincide_nombre("Configuraci\u00f3n"))

    def test_sin_coincidencias_parciales(self):
        explorador = variantes_para("explorer")
        self.assertFalse(explorador.coincide_nombre("Internet Explorer"))
        self.assertFalse(variantes_para("calculadora").coincide_app_id(AUMID_NOTEPAD))
        # Una familia distinta con el mismo prefijo no cuenta.
        self.assertFalse(variantes_para("calculadora").coincide_app_id(
            "Microsoft.WindowsCalculatorPro_123!App"))

    def test_aplicacion_de_terceros_no_tiene_variantes(self):
        self.assertIsNone(variantes_para("spotify"))
        self.assertIsNone(variantes_para("chrome"))
        self.assertIsNone(variantes_para(""))

    def test_herramientas_de_riesgo_no_se_amplian(self):
        for nombre in ("administrador de tareas", "task manager", "lupa", "magnifier",
                       "escritorio remoto", "remote desktop"):
            self.assertIsNone(variantes_para(nombre), nombre)

    def test_familia_de_aumid(self):
        self.assertEqual(familia_de_aumid(AUMID_CALC), "Microsoft.WindowsCalculator_8wekyb3d8bbwe")
        self.assertEqual(familia_de_aumid("Microsoft.Windows.Explorer"), "")

    def test_ruta_del_sistema(self):
        self.assertTrue(es_ruta_del_sistema_windows(r"C:\WINDOWS\system32\notepad.exe", r"C:\Windows"))
        self.assertFalse(es_ruta_del_sistema_windows(r"C:\WindowsApps\x.exe", r"C:\Windows"))
        self.assertFalse(es_ruta_del_sistema_windows(r"D:\Programas\app.exe", r"C:\Windows"))


def _descubrimiento(apps_menu_inicio):
    preflight = ApplicationPreflight()
    calib = MagicMock()
    calib.discover_applications.return_value = apps_menu_inicio
    storage = MagicMock()
    storage.search.return_value = []
    return ApplicationDiscovery(
        preflight=preflight,
        clasificador=LaunchClassifier(preflight=preflight),
        storage=storage,
        calibration=calib,
        machine_id="maquina-prueba",
    )


# Entradas con la forma real de Get-StartApps en un Windows en ingles.
MENU_INGLES = [
    {"name": "Calculator", "app_id": AUMID_CALC, "source": "start_menu"},
    {"name": "Calendar", "app_id": "microsoft.windowscommunicationsapps_8wekyb3d8bbwe!microsoft.windowslive.calendar",
     "source": "start_menu"},
    {"name": "Notepad", "app_id": AUMID_NOTEPAD, "source": "start_menu"},
    {"name": "Internet Explorer", "app_id": "Microsoft.InternetExplorer.Default", "source": "start_menu"},
]
MENU_ESPANOL = [
    {"name": "Calculadora", "app_id": AUMID_CALC, "source": "start_menu"},
    {"name": "Bloc de notas", "app_id": AUMID_NOTEPAD, "source": "start_menu"},
]


class TestBusquedaEnElOtroIdioma(unittest.TestCase):
    def _nombres(self, descubrimiento, nombre):
        return [c.name for c in descubrimiento.buscar_por_nombre(nombre, incluir_inventario=False)]

    def test_calculadora_en_windows_en_ingles(self):
        candidatos = _descubrimiento(MENU_INGLES).buscar_por_nombre("calculadora", incluir_inventario=False)
        del_menu = [c for c in candidatos if c.app_id == AUMID_CALC]
        self.assertEqual([c.name for c in del_menu], ["Calculator"])
        self.assertTrue(del_menu[0].es_lanzable)
        self.assertNotIn("Calendar", [c.name for c in candidatos])

    def test_calculator_en_windows_en_espanol(self):
        self.assertIn("Calculadora", self._nombres(_descubrimiento(MENU_ESPANOL), "calculator"))

    def test_notepad_en_windows_en_espanol(self):
        self.assertIn("Bloc de notas", self._nombres(_descubrimiento(MENU_ESPANOL), "notepad"))

    def test_explorer_no_arrastra_internet_explorer(self):
        self.assertNotIn("Internet Explorer", self._nombres(_descubrimiento(MENU_INGLES), "explorador de archivos"))

    def test_subcadena_original_se_mantiene(self):
        # Comportamiento previo: el nombre pedido contenido en el del menu.
        self.assertIn("Calculator", self._nombres(_descubrimiento(MENU_INGLES), "calcul"))


class _Escritorio:
    def __init__(self, ventanas):
        self._ventanas = ventanas

    def list_windows(self, app_identity=None, visible_only=True):
        return SimpleNamespace(ok=True, value=list(self._ventanas))


class TestVerificacionPorAumid(unittest.TestCase):
    """Ventana de un paquete cuyo titulo no contiene el nombre del menu."""

    def _verificar(self, ventanas, aumids, display_name="Terminal"):
        adapter = WindowsLaunchAdapter(
            desktop=_Escritorio(ventanas),
            aumids_de_ventana=lambda v: aumids.get(int(v.window_id), []),
        )
        target = LaunchTarget(
            identity="paquete:x", display_name=display_name, target_type=TARGET_AUMID,
            target="Microsoft.WindowsTerminal_8wekyb3d8bbwe!App", platform="windows",
            source="start_menu", app_id="Microsoft.WindowsTerminal_8wekyb3d8bbwe!App",
        )
        return adapter.verify(None, identity=target, timeout=0.0, preexisting_window_ids=[1])

    def test_titulo_distinto_se_verifica_por_aumid(self):
        ventanas = [
            SimpleNamespace(window_id=1, pid=10, title="Editor", is_visible=True),
            SimpleNamespace(window_id=2, pid=20, title="Windows PowerShell", is_visible=True),
        ]
        outcome = self._verificar(ventanas, {2: ["Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"]})
        self.assertTrue(outcome.success, outcome.to_dict())
        self.assertEqual(outcome.window.window_id, 2)
        self.assertEqual(outcome.evidence.get("window_match"), "nueva_ventana_por_aumid")

    def test_ventana_preexistente_con_el_aumid_no_cuenta(self):
        ventanas = [SimpleNamespace(window_id=1, pid=10, title="Windows PowerShell", is_visible=True)]
        outcome = self._verificar(ventanas, {1: ["Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"]})
        self.assertFalse(outcome.success)

    def test_otro_aumid_no_cuenta_y_sigue_por_titulo(self):
        ventanas = [SimpleNamespace(window_id=2, pid=20, title="Terminal", is_visible=True)]
        outcome = self._verificar(ventanas, {2: ["Otra.App_123!App"]})
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.evidence.get("window_match"), "nueva_ventana_por_titulo")

    def test_sin_aumid_legible_sigue_por_titulo(self):
        ventanas = [SimpleNamespace(window_id=2, pid=20, title="Windows PowerShell", is_visible=True)]
        outcome = self._verificar(ventanas, {})
        self.assertFalse(outcome.success)


class TestFiltroDeRiesgoEnIngles(unittest.TestCase):
    """Herramientas del sistema que no deben tratarse como apps normales."""

    def test_nombres_en_ingles_se_ignoran_como_en_espanol(self):
        gestor = CalibrationManager.__new__(CalibrationManager)
        pares = [
            ("Administrador de tareas", "Task Manager"),
            ("Narrador", "Narrator"),
            ("Teclado en pantalla", "On-Screen Keyboard"),
            ("Editor del Registro", "Registry Editor"),
            ("Monitor de recursos", "Resource Monitor"),
            ("Servicios", "Services"),
            ("Lupa", "Magnifier"),
            ("Conexion a Escritorio remoto", "Remote Desktop Connection"),
            ("Seguridad de Windows", "Windows Security"),
        ]
        for es, en in pares:
            with self.subTest(es=es, en=en):
                self.assertTrue(gestor._is_elevation_risk_application(es), es)
                self.assertTrue(gestor._is_elevation_risk_application(en), en)

    def test_aplicaciones_normales_no_se_filtran(self):
        gestor = CalibrationManager.__new__(CalibrationManager)
        for nombre in ("Calculator", "Notepad", "Paint", "Spotify", "Google Chrome"):
            self.assertFalse(gestor._is_elevation_risk_application(nombre), nombre)


if __name__ == "__main__":
    unittest.main()
