# -*- coding: utf-8 -*-
"""Tests unitarios para la unidad 3.8.5.5.3.

Cubre:
- wait_for_application_window: root_pid invalido/ausente -> FALLO_APERTURA.
- wait_for_application_window: proceso no vivo al iniciar -> FALLO_APERTURA.
- wait_for_application_window: proceso muere durante la espera -> FALLO_APERTURA.
- wait_for_application_window: ventana usable detectada rapidamente -> VENTANA_DETECTADA, inicio_lento=False.
- wait_for_application_window: ventana usable detectada tarde -> VENTANA_DETECTADA, inicio_lento=True.
- wait_for_application_window: proceso vivo con ventana no visible -> APLICACION_EN_FONDO.
- wait_for_application_window: proceso vivo sin ventana -> PROCESO_SIN_INTERFAZ.
- wait_for_application_window: timeout solicitado se acota al maximo permitido.
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


def _fake_window(hwnd=1234, pid=5678, visible=True):
    """Ventana simulada con los atributos usados por CalibrationManager."""
    win = MagicMock()
    win._hWnd = hwnd
    win._hwnd = hwnd
    win.hwnd = hwnd
    win.title = "Ventana prueba"
    win.is_visible = visible
    return win


class TestEsperaVentanaTimeout(unittest.TestCase):
    """3.8.5.5.3 - Esperar ventana durante timeout acotado y configurable."""

    def _parchear_gestor(self, manager, detect_return=None, proceso_vivo=True,
                         proceso_arbol=None, ventana_visible=None,
                         ventana_pid=None, fondo_ventana=False,
                         manejador_hwnd=1234):
        """Configura los mocks de bajo nivel del gestor."""
        manager.detect_window_for_process = MagicMock(return_value=detect_return)
        manager._is_process_alive = MagicMock(return_value=proceso_vivo)
        if proceso_arbol is None:
            proceso_arbol = {1000}
        manager._get_process_tree = MagicMock(return_value=proceso_arbol)
        manager._get_window_handle = MagicMock(return_value=manejador_hwnd)
        if ventana_visible is not None:
            manager._win32_is_visible = MagicMock(return_value=ventana_visible)
        if ventana_pid is not None:
            manager._get_window_process_id = MagicMock(return_value=ventana_pid)

        def _windows():
            if fondo_ventana:
                win = MagicMock()
                win._hWnd = 4321
                win._hwnd = 4321
                win.hwnd = 4321
                return [win]
            return []
        manager._get_windows = MagicMock(side_effect=_windows)

    def test_root_pid_none_retorna_fallo_apertura(self):
        """Sin PID de proceso -> FALLO_APERTURA sin esperar."""
        manager = _make_manager()
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=None, timeout=10.0
            )
        self.assertEqual(resultado["status"], "FALLO_APERTURA")
        self.assertFalse(resultado["process_alive"])
        self.assertEqual(resultado["elapsed_seconds"], 0.0)
        self.assertEqual(resultado["timeout"], 10.0)
        self.assertIn("root_pid", resultado["reason"])

    def test_root_pid_cero_retorna_fallo_apertura(self):
        """PID cero -> FALLO_APERTURA."""
        manager = _make_manager()
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=0, timeout=10.0
            )
        self.assertEqual(resultado["status"], "FALLO_APERTURA")
        self.assertFalse(resultado["process_alive"])

    def test_proceso_no_vivo_al_iniciar_retorna_fallo_apertura(self):
        """Proceso no vivo al iniciar la espera -> FALLO_APERTURA."""
        manager = _make_manager()
        self._parchear_gestor(manager, detect_return=None, proceso_vivo=False)
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, timeout=5.0
            )
        self.assertEqual(resultado["status"], "FALLO_APERTURA")
        self.assertFalse(resultado["process_alive"])
        manager.detect_window_for_process.assert_not_called()

    def test_ventana_detectada_rapido_sin_inicio_lento(self):
        """Ventana usable detectada rapidamente -> VENTANA_DETECTADA, inicio_lento=False."""
        manager = _make_manager()
        ventana = _fake_window()
        self._parchear_gestor(
            manager, detect_return=ventana, proceso_vivo=True,
            proceso_arbol={5678}, ventana_visible=True, ventana_pid=5678,
        )
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, application_name="charmap.exe", timeout=10.0
            )
        self.assertEqual(resultado["status"], "VENTANA_DETECTADA")
        self.assertFalse(resultado["inicio_lento"])
        self.assertFalse(resultado["es_fondo"])
        self.assertTrue(resultado["process_alive"])
        self.assertEqual(resultado["hwnd"], 1234)
        self.assertEqual(resultado["pid"], 5678)
        self.assertIsNotNone(resultado["window"])
        self.assertIn("ventana usable", resultado["reason"])

    def test_ventana_detectada_tarde_es_inicio_lento(self):
        """Ventana usable detectada despues de la mitad del timeout -> inicio_lento=True."""
        manager = _make_manager()
        ventana = _fake_window()
        self._parchear_gestor(
            manager, detect_return=ventana, proceso_vivo=True,
            proceso_arbol={5678}, ventana_visible=True, ventana_pid=5678,
        )
        # monotonic se llama: inicio, condicion de bucle, restante, transcurrido.
        valores = iter([0.0, 6.0, 6.0, 6.0])
        with patch(
            "src.hands.calibration.calibration_manager.time.monotonic",
            side_effect=lambda: next(valores),
        ), patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, timeout=10.0
            )
        self.assertEqual(resultado["status"], "VENTANA_DETECTADA")
        self.assertTrue(resultado["inicio_lento"])
        self.assertAlmostEqual(resultado["elapsed_seconds"], 6.0)

    def test_proceso_muere_durante_espera_retorna_fallo_apertura(self):
        """El proceso finaliza durante la espera -> FALLO_APERTURA."""
        manager = _make_manager()
        ventana = _fake_window()
        self._parchear_gestor(
            manager, detect_return=None, proceso_vivo=True,
            proceso_arbol={1000},
        )
        manager._is_process_alive = MagicMock(side_effect=[True, False])
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, timeout=10.0
            )
        self.assertEqual(resultado["status"], "FALLO_APERTURA")
        self.assertFalse(resultado["process_alive"])
        self.assertIn("finalizo durante la espera", resultado["reason"])

    def test_proceso_vivo_con_ventana_no_visible_es_fondo(self):
        """Proceso vivo con ventana no visible -> APLICACION_EN_FONDO."""
        manager = _make_manager()
        self._parchear_gestor(
            manager, detect_return=None, proceso_vivo=True,
            proceso_arbol={4321}, fondo_ventana=True,
            ventana_visible=False, ventana_pid=4321,
        )
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, timeout=0.6, poll_interval=0.4
            )
        self.assertEqual(resultado["status"], "APLICACION_EN_FONDO")
        self.assertTrue(resultado["es_fondo"])
        self.assertTrue(resultado["process_alive"])
        self.assertIsNone(resultado["window"])

    def test_proceso_vivo_sin_ventana_es_sin_interfaz(self):
        """Proceso vivo sin ninguna ventana -> PROCESO_SIN_INTERFAZ."""
        manager = _make_manager()
        self._parchear_gestor(
            manager, detect_return=None, proceso_vivo=True,
            proceso_arbol={1000}, fondo_ventana=False,
        )
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, timeout=0.6, poll_interval=0.4
            )
        self.assertEqual(resultado["status"], "PROCESO_SIN_INTERFAZ")
        self.assertFalse(resultado["es_fondo"])
        self.assertTrue(resultado["process_alive"])
        self.assertIsNone(resultado["window"])

    def test_timeout_solicitado_se_acota_al_maximo(self):
        """Un timeout muy grande se acota a MAX_WAIT_TIMEOUT (30 segundos)."""
        manager = _make_manager()
        self._parchear_gestor(
            manager, detect_return=None, proceso_vivo=False,
            proceso_arbol={1000}, fondo_ventana=False,
        )
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, timeout=999.0
            )
        self.assertEqual(resultado["timeout"], CalibrationManager.MAX_WAIT_TIMEOUT)
        self.assertEqual(resultado["status"], "FALLO_APERTURA")


if __name__ == "__main__":
    unittest.main()
