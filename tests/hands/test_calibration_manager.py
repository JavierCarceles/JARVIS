# -*- coding: utf-8 -*-
"""Tests de calibration_manager (src/hands/calibration_manager.py).

Cubre la unidad 3.6.3.2 (Lanzamiento con parametros):
- 3.6.3.2.1 Verificar soporte de argumentos en launch_application.
- 3.6.3.2.2 Verificar ejecucion con argumentos.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.hands.calibration_manager import CalibrationManager


class TestLaunchApplicationArguments:
    """3.6.3.2.1 — Verificar soporte de argumentos en launch_application."""

    def _make_manager(self):
        """Instancia CalibrationManager mockeando dependencias pesadas de __init__."""
        with patch(
            "src.hands.calibration_manager.get_screen_manager", return_value=MagicMock()
        ), patch(
            "src.hands.calibration_manager.get_calibration_config", return_value=MagicMock()
        ), patch(
            "src.hands.universal_visual_calibrator.UniversalVisualCalibrator",
            return_value=MagicMock(),
        ):
            manager = CalibrationManager()
        return manager

    def _mock_launch_flow(self, manager):
        """Mockea las dependencias internas de launch_application para controlar el flujo."""
        patcher_ignore = patch.object(manager, "_should_ignore_application", return_value=False)
        patcher_game = patch.object(manager, "_is_game_application", return_value=False)
        patcher_existing = patch.object(
            manager, "_find_existing_application_window", return_value=None
        )
        patcher_handles = patch.object(manager, "_get_window_handles", return_value=set())
        patcher_pids = patch.object(manager, "_get_process_ids", return_value=set())
        patcher_isfile = patch(
            "src.hands.calibration_manager.os.path.isfile", return_value=True
        )
        patcher_popen = patch("src.hands.calibration_manager.subprocess.Popen")
        patcher_wait = patch.object(
            manager, "_wait_for_application_window", return_value=MagicMock()
        )
        patcher_hwnd = patch.object(manager, "_get_window_handle", return_value=12345)
        patcher_pid = patch.object(manager, "_get_window_process_id", return_value=67890)
        patcher_elevated = patch.object(manager, "_is_process_elevated", return_value=False)

        patcher_ignore.start()
        patcher_game.start()
        patcher_existing.start()
        patcher_handles.start()
        patcher_pids.start()
        patcher_isfile.start()
        mock_popen = patcher_popen.start()
        patcher_wait.start()
        patcher_hwnd.start()
        patcher_pid.start()
        patcher_elevated.start()

        return mock_popen

    def _stop_patchers(self):
        patch.stopall()

    def test_launch_application_pasa_argumentos_a_popen(self):
        """launch_application debe pasar los argumentos al comando via shlex.split."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose --port 8080",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert result[1] is True, "launch_application debe reportar exito"
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd[0] == "/fake/path/testapp.exe"
            assert "--verbose" in cmd
            assert "--port" in cmd
            assert "8080" in cmd
        finally:
            self._stop_patchers()

    def test_launch_application_sin_argumentos(self):
        """launch_application sin argumentos lanza solo el ejecutable."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert result[1] is True, "launch_application debe reportar exito"
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == ["/fake/path/testapp.exe"]
        finally:
            self._stop_patchers()

    def test_launch_application_argument_vacio_no_anade_nada(self):
        """launch_application con arguments vacio no anade elementos al comando."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert result[1] is True
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == ["/fake/path/testapp.exe"]
        finally:
            self._stop_patchers()

    def test_launch_application_argument_con_espacios(self):
        """shlex.split debe separar correctamente argumentos con espacios."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--file 'C:\\ruta con espacios\\archivo.txt' --mode read",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert result[1] is True
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd[0] == "/fake/path/testapp.exe"
            assert "--file" in cmd
            assert "--mode" in cmd
            assert "read" in cmd
            # shlex.split con posix=False respeta comillas simples
            assert any("ruta con espacios" in c for c in cmd)
        finally:
            self._stop_patchers()


class TestLaunchApplicationEjecucionConArgumentos:
    """3.6.3.2.2 — Verificar ejecucion con argumentos a traves de launch_application."""

    def _make_manager(self):
        with patch(
            "src.hands.calibration_manager.get_screen_manager", return_value=MagicMock()
        ), patch(
            "src.hands.calibration_manager.get_calibration_config", return_value=MagicMock()
        ), patch(
            "src.hands.universal_visual_calibrator.UniversalVisualCalibrator",
            return_value=MagicMock(),
        ):
            manager = CalibrationManager()
        return manager

    def _mock_launch_flow(self, manager):
        patcher_ignore = patch.object(manager, "_should_ignore_application", return_value=False)
        patcher_game = patch.object(manager, "_is_game_application", return_value=False)
        patcher_existing = patch.object(
            manager, "_find_existing_application_window", return_value=None
        )
        patcher_handles = patch.object(manager, "_get_window_handles", return_value=set())
        patcher_pids = patch.object(manager, "_get_process_ids", return_value=set())
        patcher_isfile = patch(
            "src.hands.calibration_manager.os.path.isfile", return_value=True
        )
        patcher_popen = patch("src.hands.calibration_manager.subprocess.Popen")
        patcher_wait = patch.object(
            manager, "_wait_for_application_window", return_value=MagicMock()
        )
        patcher_hwnd = patch.object(manager, "_get_window_handle", return_value=12345)
        patcher_pid = patch.object(manager, "_get_window_process_id", return_value=67890)
        patcher_elevated = patch.object(manager, "_is_process_elevated", return_value=False)

        patcher_ignore.start()
        patcher_game.start()
        patcher_existing.start()
        patcher_handles.start()
        patcher_pids.start()
        patcher_isfile.start()
        mock_popen = patcher_popen.start()
        patcher_wait.start()
        patcher_hwnd.start()
        patcher_pid.start()
        patcher_elevated.start()

        return mock_popen

    def _stop_patchers(self):
        patch.stopall()

    def test_ejecucion_con_argumentos_retorna_exito(self):
        """Ejecutar launch_application con argumentos debe retornar (hwnds, True)."""
        app = {
            "name": "Calc",
            "executable": "calc.exe",
            "arguments": "",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert isinstance(result, tuple)
            assert len(result) == 2
            assert result[1] is True
            mock_popen.assert_called_once()
        finally:
            self._stop_patchers()

    def test_ejecucion_con_argumentos_llama_popen_con_lista(self):
        """subprocess.Popen debe recibirse como lista (no string) con argumentos incluidos."""
        app = {
            "name": "Notepad",
            "executable": "notepad.exe",
            "arguments": "mi_archivo.txt",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            manager.launch_application(app)

            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert isinstance(cmd, list)
            assert cmd == ["notepad.exe", "mi_archivo.txt"]
        finally:
            self._stop_patchers()
