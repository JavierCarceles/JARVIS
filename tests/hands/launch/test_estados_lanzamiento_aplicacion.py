# -*- coding: utf-8 -*-
"""Tests unitarios para la unidad 3.8.5.5.6.

Cubre:
- LaunchState enum: 7 estados definidos (ABRIENDO, PROCESO_INICIADO,
  VENTANA_DETECTADA, ABIERTA_VERIFICADA, ABIERTA_SIN_VENTANA, FALLO, TIMEOUT).
- get_launch_state(): devuelve None inicialmente y el estado tras cada operacion.
- launch_application(): establece ABRIENDO al iniciar, FALLO en fallo,
  ABIERTA_VERIFICADA al reutilizar ventana existente, PROCESO_INICIADO al lanzar.
- wait_for_application_window(): establece VENTANA_DETECTADA, FALLO,
  ABIERTA_SIN_VENTANA y TIMEOUT segun el resultado.
- verify_visible_window_for_application(): establece ABIERTA_VERIFICADA o FALLO.
- verify_estabilidad_minima_proceso_ventana(): establece ABIERTA_VERIFICADA o FALLO.
- get_launch_evidence(): incluye launch_state.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.hands.calibration.calibration_manager import CalibrationManager, LaunchState


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


class TestLaunchStateEnum(unittest.TestCase):
    """3.8.5.5.6 - Enum LaunchState con los 7 estados requeridos."""

    def test_siete_estados_definidos(self):
        """Existen exactamente los 7 estados del roadmap."""
        nombres = {s.name for s in LaunchState}
        esperados = {
            "ABRIENDO", "PROCESO_INICIADO", "VENTANA_DETECTADA",
            "ABIERTA_VERIFICADA", "ABIERTA_SIN_VENTANA", "FALLO", "TIMEOUT",
        }
        self.assertEqual(nombres, esperados)

    def test_valores_son_strings_minusculas(self):
        """Cada estado tiene un valor de string en minusculas sin tildes."""
        for estado in LaunchState:
            self.assertIsInstance(estado.value, str)
            self.assertEqual(estado.value, estado.value.lower())
            self.assertNotIn("\u00e1", estado.value)
            self.assertNotIn("\u00e9", estado.value)
            self.assertNotIn("\u00ed", estado.value)
            self.assertNotIn("\u00f3", estado.value)
            self.assertNotIn("\u00fa", estado.value)
            self.assertNotIn("\u00f1", estado.value)

    def test_estado_inicial_es_none(self):
        """get_launch_state() devuelve None antes de cualquier lanzamiento."""
        manager = _make_manager()
        self.assertIsNone(manager.get_launch_state())


class TestLaunchApplicationEstado(unittest.TestCase):
    """3.8.5.5.6 - Estados establecidos por launch_application()."""

    def test_launch_aplica_abriendo_al_iniciar(self):
        """Al iniciar launch_application se establece ABRIENDO."""
        manager = _make_manager()
        with patch.object(manager, "_should_ignore_application", return_value=False), \
             patch.object(manager, "_is_game_application", return_value=False), \
             patch.object(manager, "_find_existing_application_window", return_value=None), \
             patch.object(manager, "_get_window_handles", return_value=set()), \
             patch.object(manager, "_get_process_ids", return_value=set()), \
             patch("src.hands.calibration.calibration_manager.subprocess.Popen"), \
             patch.object(manager, "_wait_for_application_window", return_value=None), \
             patch("src.hands.calibration.calibration_manager.os.path.isfile", return_value=False), \
             patch.object(manager, "_get_application_metadata", return_value=[]):
            manager.launch_application({"name": "test_app", "path": "C:\\test.exe"})
            self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)

    def test_launch_fallo_quando_app_vacia(self):
        """Nombre de app vacio -> FALLO."""
        manager = _make_manager()
        manager.launch_application({"name": "", "path": ""})
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)

    def test_launch_abierta_verificada_ventana_existente(self):
        """Reutilizar ventana existente -> ABIERTA_VERIFICADA."""
        manager = _make_manager()
        ventana = _fake_window(hwnd=100, pid=200, visible=True)
        with patch.object(manager, "_should_ignore_application", return_value=False), \
             patch.object(manager, "_is_game_application", return_value=False), \
             patch.object(manager, "_find_existing_application_window", return_value=ventana), \
             patch.object(manager, "_get_window_handle", return_value=100), \
             patch.object(manager, "_get_window_process_id", return_value=200), \
             patch.object(manager, "_is_process_elevated", return_value=False), \
             patch.object(manager, "_get_window_handles", return_value=set()), \
             patch.object(manager, "_get_process_ids", return_value=set()):
            import ctypes
            with patch.object(ctypes.windll.user32, "IsIconic", return_value=0):
                manager.launch_application({"name": "test_app", "path": ""})
            self.assertEqual(manager.get_launch_state(), LaunchState.ABIERTA_VERIFICADA)

    def test_launch_proceso_iniciado_al_lanzar(self):
        """Lanzamiento exitoso de ejecutable -> PROCESO_INICIADO."""
        manager = _make_manager()
        ventana = _fake_window(hwnd=100, pid=200, visible=True)
        with patch.object(manager, "_should_ignore_application", return_value=False), \
             patch.object(manager, "_is_game_application", return_value=False), \
             patch.object(manager, "_find_existing_application_window", return_value=None), \
             patch.object(manager, "_get_window_handles", return_value=set()), \
             patch.object(manager, "_get_process_ids", return_value=set()), \
             patch("src.hands.calibration.calibration_manager.subprocess.Popen"), \
             patch("src.hands.calibration.calibration_manager.os.path.isfile", return_value=True), \
             patch.object(manager, "_wait_for_application_window", return_value=ventana), \
             patch.object(manager, "_get_window_handle", return_value=100), \
             patch.object(manager, "_get_window_process_id", return_value=200), \
             patch.object(manager, "_is_process_elevated", return_value=False), \
             patch.object(manager, "_get_process_tree", return_value={200}):
            manager.launch_application({"name": "test_app", "path": "C:\\test.exe"})
            self.assertEqual(manager.get_launch_state(), LaunchState.PROCESO_INICIADO)

    def test_launch_fallo_en_excepcion(self):
        """Excepcion durante lanzamiento -> FALLO."""
        manager = _make_manager()
        with patch.object(manager, "_should_ignore_application", return_value=False), \
             patch.object(manager, "_is_game_application", return_value=False), \
             patch.object(manager, "_find_existing_application_window", return_value=None), \
             patch.object(manager, "_get_window_handles", return_value=set()), \
             patch.object(manager, "_get_process_ids", return_value=set()), \
             patch("src.hands.calibration.calibration_manager.subprocess.Popen", side_effect=RuntimeError("boom")):
            manager.launch_application({"name": "test_app", "path": "C:\\test.exe"})
            self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)


class TestWaitForApplicationWindowEstado(unittest.TestCase):
    """3.8.5.5.6 - Estados establecidos por wait_for_application_window()."""

    def test_ventana_detectada(self):
        """Ventana usable detectada -> VENTANA_DETECTADA."""
        manager = _make_manager()
        ventana = _fake_window()
        manager.detect_window_for_process = MagicMock(return_value=ventana)
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_window_handle = MagicMock(return_value=1234)
        manager._win32_is_visible = MagicMock(return_value=True)
        manager._get_window_process_id = MagicMock(return_value=5678)
        manager._get_windows = MagicMock(return_value=[])

        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, application_name="test", app_id="", timeout=2.0
            )
        self.assertEqual(manager.get_launch_state(), LaunchState.VENTANA_DETECTADA)
        self.assertEqual(resultado["status"], "VENTANA_DETECTADA")

    def test_fallo_pid_invalido(self):
        """PID invalido -> FALLO."""
        manager = _make_manager()
        resultado = manager.wait_for_application_window(
            root_pid=None, application_name="test", app_id="", timeout=2.0
        )
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)
        self.assertEqual(resultado["status"], "FALLO_APERTURA")

    def test_fallo_proceso_no_vivo(self):
        """Proceso no vivo al iniciar -> FALLO."""
        manager = _make_manager()
        manager._is_process_alive = MagicMock(return_value=False)
        resultado = manager.wait_for_application_window(
            root_pid=9999, application_name="test", app_id="", timeout=2.0
        )
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)

    def test_abierta_sin_ventana_proceso_en_fondo(self):
        """Proceso vivo con ventana no visible -> ABIERTA_SIN_VENTANA."""
        manager = _make_manager()
        manager.detect_window_for_process = MagicMock(return_value=None)
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={1000})

        def _windows():
            win = MagicMock()
            win._hWnd = 4321
            win._hwnd = 4321
            win.hwnd = 4321
            return [win]
        manager._get_windows = MagicMock(side_effect=_windows)
        manager._get_window_handle = MagicMock(return_value=4321)
        manager._get_window_process_id = MagicMock(return_value=1000)
        manager._win32_is_visible = MagicMock(return_value=False)

        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, application_name="test", app_id="", timeout=0.5
            )
        self.assertEqual(manager.get_launch_state(), LaunchState.ABIERTA_SIN_VENTANA)
        self.assertEqual(resultado["status"], "APLICACION_EN_FONDO")

    def test_timeout_proceso_vivo_sin_ventana(self):
        """Timeout con proceso vivo y sin ventana -> TIMEOUT."""
        manager = _make_manager()
        manager.detect_window_for_process = MagicMock(return_value=None)
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_windows = MagicMock(return_value=[])

        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.wait_for_application_window(
                root_pid=1000, application_name="test", app_id="", timeout=0.5
            )
        self.assertEqual(manager.get_launch_state(), LaunchState.TIMEOUT)
        self.assertEqual(resultado["status"], "PROCESO_SIN_INTERFAZ")


class TestVerifyVisibleWindowEstado(unittest.TestCase):
    """3.8.5.5.6 - Estados establecidos por verify_visible_window_for_application()."""

    def test_ventana_verificada(self):
        """Ventana visible y correspondiente -> ABIERTA_VERIFICADA."""
        manager = _make_manager()
        ventana = _fake_window(hwnd=100, pid=200, visible=True)
        with patch.object(manager, "_get_window_handle", return_value=100), \
             patch.object(manager, "_win32_is_window", return_value=True), \
             patch.object(manager, "_win32_is_visible", return_value=True), \
             patch.object(manager, "_win32_get_style", return_value=0x10000000), \
             patch.object(manager, "_get_window_process_id", return_value=200), \
             patch.object(manager, "_get_window_process_name", return_value="test_app"), \
             patch.object(manager, "_win32_get_window_title", return_value="Test App"), \
             patch.object(manager, "_expected_process_names", return_value=["test_app"]), \
             patch.object(manager, "_is_vscode_application", return_value=False), \
             patch.object(manager, "_get_process_tree", return_value={200}), \
             patch.object(manager.screen_manager, "get_monitor_for_window", return_value=None):
            resultado = manager.verify_visible_window_for_application(
                window=ventana, application_name="test_app", app_id="", root_pid=200
            )
        self.assertEqual(manager.get_launch_state(), LaunchState.ABIERTA_VERIFICADA)
        self.assertTrue(resultado["verificada"])

    def test_ventana_no_verificada(self):
        """Ventana no visible -> FALLO."""
        manager = _make_manager()
        ventana = _fake_window(hwnd=100, pid=200, visible=False)
        with patch.object(manager, "_get_window_handle", return_value=100), \
             patch.object(manager, "_win32_is_window", return_value=True), \
             patch.object(manager, "_win32_is_visible", return_value=False):
            resultado = manager.verify_visible_window_for_application(
                window=ventana, application_name="test_app", app_id="", root_pid=200
            )
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)
        self.assertFalse(resultado["verificada"])

    def test_ventana_none_es_fallo(self):
        """Ventana None -> FALLO."""
        manager = _make_manager()
        resultado = manager.verify_visible_window_for_application(
            window=None, application_name="test_app", app_id="", root_pid=200
        )
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)


class TestVerifyEstabilidadEstado(unittest.TestCase):
    """3.8.5.5.6 - Estados establecidos por verify_estabilidad_minima_proceso_ventana()."""

    def test_estabilidad_ok_proceso_solo(self):
        """Proceso estable durante intervalo -> ABIERTA_VERIFICADA."""
        manager = _make_manager()
        manager._is_process_alive = MagicMock(return_value=True)
        manager._get_process_tree = MagicMock(return_value={1000})
        with patch("src.hands.calibration.calibration_manager.time.sleep"):
            resultado = manager.verify_estabilidad_minima_proceso_ventana(
                root_pid=1000, window=None, estabilidad_interval=0.3, estabilidad_checks=3
            )
        self.assertEqual(manager.get_launch_state(), LaunchState.ABIERTA_VERIFICADA)
        self.assertTrue(resultado["estable"])

    def test_estabilidad_proceso_cerrado(self):
        """Proceso muere durante intervalo -> FALLO."""
        manager = _make_manager()
        manager._is_process_alive = MagicMock(return_value=False)
        manager._get_process_tree = MagicMock(return_value={1000})
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=1000, window=None, estabilidad_interval=0.3, estabilidad_checks=3
        )
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)
        self.assertFalse(resultado["estable"])

    def test_estabilidad_sin_pid(self):
        """Sin PID -> FALLO."""
        manager = _make_manager()
        resultado = manager.verify_estabilidad_minima_proceso_ventana(
            root_pid=None, window=None, estabilidad_interval=0.3, estabilidad_checks=3
        )
        self.assertEqual(manager.get_launch_state(), LaunchState.FALLO)


class TestGetLaunchEvidenceEstado(unittest.TestCase):
    """3.8.5.5.6 - get_launch_evidence incluye launch_state."""

    def test_evidence_incluye_launch_state(self):
        """get_launch_evidence() incluye la clave launch_state."""
        manager = _make_manager()
        manager._last_launch_state = LaunchState.ABRIENDO
        manager._last_launch_root_pid = 1234
        manager._last_launch_owned_pids = {1234}
        manager._last_launch_owned_hwnds = {5678}
        manager._last_launch_was_owned = True
        manager._last_launch_executable_path = "C:\\test.exe"
        manager._last_launch_app_id = "test.app"

        evidence = manager.get_launch_evidence()
        self.assertEqual(evidence["launch_state"], "abriendo")
        self.assertEqual(evidence["root_pid"], 1234)

    def test_evidence_launch_state_none_cuando_no_hay_lanzamiento(self):
        """Sin lanzamiento previo, launch_state es None en la evidencia."""
        manager = _make_manager()
        evidence = manager.get_launch_evidence()
        self.assertIsNone(evidence["launch_state"])


if __name__ == "__main__":
    unittest.main()
