# -*- coding: utf-8 -*-
"""Tests unitarios para la unidad 3.8.5.5.5.

Cubre verify_estabilidad_minima_proceso_ventana:
- proceso vivo + ventana valida/visible/pertenece durante el intervalo -> ESTABLE.
- proceso muere durante el intervalo -> PROCESO_CERRADO.
- ventana deja de ser valida -> VENTANA_CERRADA.
- ventana deja de ser visible -> VENTANA_NO_VISIBLE.
- ventana deja de pertenecer al proceso -> VENTANA_NO_PERTENECE.
- sin PID -> ERROR.
- solo proceso (sin ventana) -> estabilidad de proceso solamente.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.hands.calibration.calibration_manager import CalibrationManager


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


def _fake_window(hwnd=9876):
    win = MagicMock()
    win._hWnd = hwnd
    win._hwnd = hwnd
    win.hwnd = hwnd
    return win


class TestEstabilidadMinimaProcesoVentana(unittest.TestCase):
    """3.8.5.5.5 - Estabilidad minima del proceso/ventana durante un intervalo."""

    def _configurar_proceso_estable(self, manager, pid=12345, window_pid=12345):
        manager._last_launch_root_pid = pid
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={pid})
        if window_pid is not None:
            manager._get_window_handle = MagicMock(return_value=9876)
            manager._win32_is_window = MagicMock(return_value=True)
            manager._win32_is_visible = MagicMock(return_value=True)
            manager._get_window_process_id = MagicMock(return_value=window_pid)

    def test_estabilidad_proceso_y_ventana_estables(self):
        """Proceso vivo y ventana valida/visible/pertenece -> ESTABLE."""
        manager = _make_manager()
        self._configurar_proceso_estable(manager)
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=_fake_window(),
            application_name="Mapa de caracteres",
            app_id="",
            estabilidad_interval=0.6,
            estabilidad_checks=3,
        )
        self.assertEqual(resultado["status"], "ESTABLE", f"resultado: {resultado}")
        self.assertTrue(resultado["estable"])
        self.assertEqual(resultado["checks_passed"], 3)
        self.assertEqual(resultado["total_checks"], 3)
        self.assertTrue(resultado["process_alive"])
        self.assertTrue(resultado["window_valida"])
        self.assertTrue(resultado["window_visible"])
        self.assertTrue(resultado["ventana_pertenece_proceso"])
        self.assertEqual(resultado["pid"], 12345)
        self.assertIn("estables", resultado["reason"])

    def test_estabilidad_proceso_muere_a_mitad(self):
        """Proceso muere durante el intervalo -> PROCESO_CERRADO."""
        manager = _make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        # Primera comprobacion viva, las siguientes muertas.
        manager._is_process_alive = MagicMock(side_effect=[True, False, False])
        manager._get_process_tree = MagicMock(return_value={12345})
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=None,
            estabilidad_interval=0.6,
            estabilidad_checks=3,
        )
        self.assertEqual(resultado["status"], "PROCESO_CERRADO", f"resultado: {resultado}")
        self.assertFalse(resultado["estable"])
        self.assertEqual(resultado["checks_passed"], 1)
        self.assertFalse(resultado["process_alive"])
        self.assertIn("proceso", resultado["reason"])

    def test_estabilidad_ventana_se_cierra(self):
        """Ventana deja de ser valida -> VENTANA_CERRADA."""
        manager = _make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={12345})
        manager._get_window_handle = MagicMock(return_value=9876)
        # Primera comprobacion valida, segunda cerrada.
        # El primer True se consume en la inicializacion de window_valida;
        # el segundo en iteracion 1; el tercero (False) corta en iteracion 2.
        manager._win32_is_window = MagicMock(side_effect=[True, True, False])
        manager._win32_is_visible = MagicMock(return_value=True)
        manager._get_window_process_id = MagicMock(return_value=12345)
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=_fake_window(),
            estabilidad_interval=0.6,
            estabilidad_checks=3,
        )
        self.assertEqual(resultado["status"], "VENTANA_CERRADA", f"resultado: {resultado}")
        self.assertFalse(resultado["estable"])
        self.assertEqual(resultado["checks_passed"], 1)
        self.assertTrue(resultado["window_valida"])

    def test_estabilidad_ventana_no_visible(self):
        """Ventana deja de ser visible -> VENTANA_NO_VISIBLE."""
        manager = _make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={12345})
        manager._get_window_handle = MagicMock(return_value=9876)
        manager._win32_is_window = MagicMock(return_value=True)
        # Primera visible, segunda no.
        # El primer True se consume en la inicializacion de window_visible;
        # el segundo en iteracion 1; el tercero (False) corta en iteracion 2.
        manager._win32_is_visible = MagicMock(side_effect=[True, True, False])
        manager._get_window_process_id = MagicMock(return_value=12345)
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=_fake_window(),
            estabilidad_interval=0.6,
            estabilidad_checks=3,
        )
        self.assertEqual(resultado["status"], "VENTANA_NO_VISIBLE", f"resultado: {resultado}")
        self.assertFalse(resultado["estable"])
        self.assertEqual(resultado["checks_passed"], 1)
        self.assertTrue(resultado["window_visible"])

    def test_estabilidad_ventana_no_pertenece_al_proceso(self):
        """Ventana con PID ajeno al arbol -> VENTANA_NO_PERTENECE."""
        manager = _make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={12345})
        manager._get_window_handle = MagicMock(return_value=9876)
        manager._win32_is_window = MagicMock(return_value=True)
        manager._win32_is_visible = MagicMock(return_value=True)
        # PID de ventana ajeno al proceso lanzado.
        manager._get_window_process_id = MagicMock(return_value=55555)
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=_fake_window(),
            estabilidad_interval=0.6,
            estabilidad_checks=3,
        )
        self.assertEqual(resultado["status"], "VENTANA_NO_PERTENECE", f"resultado: {resultado}")
        self.assertFalse(resultado["estable"])
        self.assertEqual(resultado["checks_passed"], 0)
        self.assertFalse(resultado["ventana_pertenece_proceso"])

    def test_estabilidad_sin_pid_retorna_error(self):
        """Sin PID para verificar -> ERROR y no estable."""
        manager = _make_manager()
        manager._last_launch_root_pid = None
        resultado = manager.verify_estabilidad_minima_proceso_ventana()
        self.assertEqual(resultado["status"], "ERROR", f"resultado: {resultado}")
        self.assertFalse(resultado["estable"])
        self.assertIsNone(resultado["pid"])
        self.assertEqual(resultado["error"], "No hay PID para verificar")
        self.assertIsNone(resultado["root_pid"])

    def test_estabilidad_solo_proceso_sin_ventana(self):
        """Solo proceso (sin ventana) -> estabilidad de proceso solamente."""
        manager = _make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={12345})
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=None,
            estabilidad_interval=0.6,
            estabilidad_checks=3,
        )
        self.assertEqual(resultado["status"], "ESTABLE", f"resultado: {resultado}")
        self.assertTrue(resultado["estable"])
        self.assertEqual(resultado["checks_passed"], 3)
        self.assertTrue(resultado["process_alive"])
        self.assertFalse(resultado["window_valida"])
        self.assertIn("proceso estable", resultado["reason"])

    def test_estabilidad_registra_intervalo_y_checks(self):
        """El resultado registra el intervalo y el total de comprobaciones."""
        manager = _make_manager()
        manager._last_launch_root_pid = 12345
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={12345})
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=12345,
            window=None,
            estabilidad_interval=2.5,
            estabilidad_checks=5,
        )
        self.assertEqual(resultado["estabilidad_interval"], 2.5)
        self.assertEqual(resultado["total_checks"], 5)
        self.assertGreaterEqual(resultado["elapsed_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()
