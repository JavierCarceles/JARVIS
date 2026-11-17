# -*- coding: utf-8 -*-
"""Tests unitarios para la unidad 3.8.5.5.4.

Cubre:
- verify_visible_window_for_application: ventana ausente -> no verificada.
- verify_visible_window_for_application: HWND no valido -> no verificada.
- verify_visible_window_for_application: ventana no visible -> visible=False.
- verify_visible_window_for_application: visible + PID en arbol + nombre de proceso esperado -> verificada.
- verify_visible_window_for_application: ventana de Visual Studio Code no se confunde con la solicitada.
- verify_visible_window_for_application: coincidencia solo por titulo no es suficiente.
- verify_visible_window_for_application: ventana en monitor no primario (segunda pantalla).
- verify_visible_window_for_application: ventana en monitor primario.
- verify_visible_window_for_application: no llama ShowWindow/SetForegroundWindow/SetWindowPos (no fuerza foco, maximizar ni mover).
"""

import unittest
from unittest.mock import MagicMock, patch

from src.hands.calibration.calibration_manager import CalibrationManager, WS_VISIBLE


def _make_manager():
    """Instancia CalibrationManager mockeando dependencias pesadas de __init__."""
    with patch(
        "src.hands.calibration.calibration_manager.get_screen_manager", return_value=MagicMock()
    ), patch(
        "src.hands.calibration.calibration_manager.get_calibration_config", return_value=MagicMock()
    ), patch(
        "src.hands.calibration.universal_visual_calibrator.UniversalVisualCalibrator",
        return_value=MagicMock(),
    ):
        manager = CalibrationManager()
    return manager


def _fake_window(hwnd=1234, visible=True, title="Ventana prueba"):
    win = MagicMock()
    win._hWnd = hwnd
    win._hwnd = hwnd
    win.hwnd = hwnd
    win.title = title
    win.is_visible = visible
    return win


def _fake_monitor(monitor_id=2, is_primary=False):
    m = MagicMock()
    m.monitor_id = monitor_id
    m.is_primary = is_primary
    return m


class TestVerificarVentanaVisibleAplicacion(unittest.TestCase):
    """3.8.5.5.4 - Verificar ventana visible y correspondiente a la aplicacion."""

    def _configurar_base(
        self,
        manager,
        visible=True,
        hwnd=1234,
        pid=5678,
        process_name="charmap.exe",
        window_title="Mapa de caracteres",
        window_valida=True,
        proceso_arbol=None,
        expected_processes=None,
        monitor_id=2,
        is_primary=False,
    ):
        if proceso_arbol is None:
            proceso_arbol = {1000, 5678}
        if expected_processes is None:
            expected_processes = {"charmap.exe"}
        manager._get_window_handle = MagicMock(return_value=hwnd)
        manager._win32_is_window = MagicMock(return_value=window_valida)
        manager._win32_is_visible = MagicMock(return_value=visible)
        manager._win32_get_style = MagicMock(return_value=WS_VISIBLE)
        manager._get_window_process_id = MagicMock(return_value=pid)
        manager._get_window_process_name = MagicMock(return_value=process_name)
        manager._win32_get_window_title = MagicMock(return_value=window_title)
        manager._get_process_tree = MagicMock(return_value=proceso_arbol)
        manager._expected_process_names = MagicMock(return_value=expected_processes)
        manager._is_vscode_application = MagicMock(return_value=False)
        manager.screen_manager.get_monitor_for_window.return_value = _fake_monitor(
            monitor_id=monitor_id, is_primary=is_primary
        )

    def test_ventana_none_no_verificada(self):
        manager = _make_manager()
        resultado = manager.verify_visible_window_for_application(
            None, application_name="Mapa de caracteres", root_pid=1000
        )
        self.assertFalse(resultado["verificada"])
        self.assertFalse(resultado["visible"])
        self.assertFalse(resultado["corresponde_aplicacion"])
        self.assertIsNone(resultado["hwnd"])
        self.assertIn("ausente", resultado["reason"])

    def test_hwnd_nulo_no_verificada(self):
        manager = _make_manager()
        ventana = _fake_window()
        manager._get_window_handle = MagicMock(return_value=None)
        resultado = manager.verify_visible_window_for_application(
            ventana, application_name="Mapa de caracteres", root_pid=1000
        )
        self.assertFalse(resultado["verificada"])
        self.assertIsNone(resultado["hwnd"])
        self.assertIn("HWND", resultado["reason"])

    def test_hwnd_no_es_ventana_valida_no_verificada(self):
        manager = _make_manager()
        ventana = _fake_window()
        manager._get_window_handle = MagicMock(return_value=1234)
        manager._win32_is_window = MagicMock(return_value=False)
        resultado = manager.verify_visible_window_for_application(
            ventana, application_name="Mapa de caracteres", root_pid=1000
        )
        self.assertFalse(resultado["verificada"])
        self.assertFalse(resultado["visible"])
        self.assertIn("valida", resultado["reason"])

    def test_ventana_no_visible_no_verificada(self):
        manager = _make_manager()
        self._configurar_base(manager, visible=False)
        resultado = manager.verify_visible_window_for_application(
            _fake_window(), application_name="Mapa de caracteres", root_pid=1000
        )
        self.assertFalse(resultado["verificada"])
        self.assertFalse(resultado["visible"])
        self.assertIn("no es visible", resultado["reason"])

    def test_ventana_visible_y_correspondente_por_pid_es_verificada(self):
        manager = _make_manager()
        self._configurar_base(manager)
        resultado = manager.verify_visible_window_for_application(
            _fake_window(),
            application_name="Mapa de caracteres",
            app_id="",
            root_pid=1000,
        )
        self.assertTrue(resultado["verificada"])
        self.assertTrue(resultado["visible"])
        self.assertTrue(resultado["corresponde_aplicacion"])
        self.assertTrue(resultado["criterio_pid"])
        self.assertTrue(resultado["criterio_nombre_proceso"])
        self.assertFalse(resultado["es_visual_studio_code"])
        self.assertEqual(resultado["pid"], 5678)
        self.assertEqual(resultado["process_name"], "charmap.exe")
        self.assertEqual(resultado["hwnd"], 1234)
        self.assertIn("correspondiente", resultado["reason"])

    def test_ventana_de_visual_studio_code_no_se_confunde(self):
        manager = _make_manager()
        self._configurar_base(
            manager,
            process_name="code.exe",
            window_title="Visual Studio Code",
            expected_processes={"charmap.exe"},
        )
        manager._get_window_process_id = MagicMock(return_value=9999)
        manager._get_process_tree = MagicMock(return_value={1000, 5678})
        manager._expected_process_names = MagicMock(return_value={"charmap.exe"})
        manager._is_vscode_application = MagicMock(return_value=False)
        manager.screen_manager.get_monitor_for_window.return_value = _fake_monitor(
            monitor_id=2, is_primary=False
        )
        resultado = manager.verify_visible_window_for_application(
            _fake_window(),
            application_name="Mapa de caracteres",
            app_id="",
            root_pid=1000,
        )
        self.assertFalse(resultado["verificada"])
        self.assertTrue(resultado["visible"])
        self.assertFalse(resultado["corresponde_aplicacion"])
        self.assertTrue(resultado["es_visual_studio_code"])
        self.assertIn("Visual Studio Code", resultado["reason"])

    def test_coincidencia_solo_por_titulo_no_es_suficiente(self):
        manager = _make_manager()
        self._configurar_base(
            manager,
            pid=9999,
            process_name="otro.exe",
            expected_processes={"charmap.exe"},
        )
        manager._get_process_tree = MagicMock(return_value={1000, 5678})
        manager._expected_process_names = MagicMock(return_value={"charmap.exe"})
        manager.screen_manager.get_monitor_for_window.return_value = _fake_monitor(
            monitor_id=1, is_primary=True
        )
        resultado = manager.verify_visible_window_for_application(
            _fake_window(title="Mapa de caracteres"),
            application_name="Mapa de caracteres",
            app_id="",
            root_pid=1000,
        )
        self.assertFalse(resultado["verificada"])
        self.assertTrue(resultado["visible"])
        self.assertFalse(resultado["corresponde_aplicacion"])
        self.assertFalse(resultado["criterio_pid"])
        self.assertFalse(resultado["criterio_nombre_proceso"])
        self.assertTrue(resultado["criterio_titulo"])
        self.assertIn("no coinciden", resultado["reason"])

    def test_ventana_en_monitor_no_primario_segunda_pantalla(self):
        manager = _make_manager()
        self._configurar_base(manager, monitor_id=2, is_primary=False)
        resultado = manager.verify_visible_window_for_application(
            _fake_window(),
            application_name="Mapa de caracteres",
            app_id="",
            root_pid=1000,
        )
        self.assertTrue(resultado["verificada"])
        self.assertEqual(resultado["monitor_id"], 2)
        self.assertFalse(resultado["monitor_primario"])
        self.assertTrue(resultado["en_segunda_pantalla"])

    def test_ventana_en_monitor_primario_no_es_segunda_pantalla(self):
        manager = _make_manager()
        self._configurar_base(manager, monitor_id=1, is_primary=True)
        resultado = manager.verify_visible_window_for_application(
            _fake_window(),
            application_name="Mapa de caracteres",
            app_id="",
            root_pid=1000,
        )
        self.assertTrue(resultado["verificada"])
        self.assertEqual(resultado["monitor_id"], 1)
        self.assertTrue(resultado["monitor_primario"])
        self.assertFalse(resultado["en_segunda_pantalla"])

    def test_no_forza_foco_ni_maximiza_ni_mueve(self):
        manager = _make_manager()
        self._configurar_base(manager)
        with patch(
            "src.hands.calibration.calibration_manager.USER32.ShowWindow"
        ) as show_window, patch(
            "src.hands.calibration.calibration_manager.USER32.SetForegroundWindow"
        ) as set_foreground, patch(
            "src.hands.calibration.calibration_manager.USER32.SetWindowPos"
        ) as set_window_pos:
            resultado = manager.verify_visible_window_for_application(
                _fake_window(),
                application_name="Mapa de caracteres",
                app_id="",
                root_pid=1000,
            )
        show_window.assert_not_called()
        set_foreground.assert_not_called()
        set_window_pos.assert_not_called()
        self.assertTrue(resultado["verificada"])


if __name__ == "__main__":
    unittest.main()
