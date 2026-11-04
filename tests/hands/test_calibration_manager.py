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

    def test_ejecucion_con_argumentos_popen_devnull_y_contexto(self):
        """3.6.3.2.2: Popen recibe stdout/stderr DEVNULL; el contexto marca ventana/proceso propios."""
        import subprocess

        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose --port 8080",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert result == (set(), True)
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            kwargs = mock_popen.call_args[1]
            assert cmd == ["/fake/path/testapp.exe", "--verbose", "--port", "8080"]
            assert kwargs.get("stdout") is subprocess.DEVNULL
            assert kwargs.get("stderr") is subprocess.DEVNULL
            # Contexto de lanzamiento: ventana nueva (hwnd 12345 no estaba antes) y proceso nuevo
            assert manager._last_launch_window is not None
            assert manager._last_launch_was_owned is True
            assert manager._last_launch_root_pid == 67890
            assert manager._last_launch_owned_hwnds == {12345}
        finally:
            self._stop_patchers()

    def test_ejecucion_sin_ventana_retorna_falso(self):
        """3.6.3.2.2: si _wait_for_application_window no detecta ventana, el lanzamiento falla."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch.object(manager, "_wait_for_application_window", return_value=None):
                result = manager.launch_application(app)

            assert result[1] is False
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == ["/fake/path/testapp.exe", "--verbose"]
        finally:
            self._stop_patchers()

    def test_ejecucion_sin_hwnd_retorna_falso(self):
        """3.6.3.2.2: ventana detectada pero sin HWND utilizable => (before, False)."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch.object(manager, "_get_window_handle", return_value=None):
                result = manager.launch_application(app)

            assert result == (set(), False)
            mock_popen.assert_called_once()
        finally:
            self._stop_patchers()

    def test_ejecucion_popen_lanza_excepcion_retorna_falso(self):
        """3.6.3.2.2: si Popen lanza (ejecutable no ejecutable), el fallo se captura y retorna False."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            mock_popen.side_effect = OSError("No such file or directory")
            result = manager.launch_application(app)

            assert result == (set(), False)
        finally:
            self._stop_patchers()

    def test_ejecucion_proceso_elevado_retorna_falso_y_cierra_propios(self):
        """3.6.3.2.2: proceso elevado tras lanzar => False y se cierran solo las ventanas propias."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch.object(manager, "_is_process_elevated", return_value=True), patch.object(
                manager, "_close_all_owned_windows"
            ) as mock_close:
                result = manager.launch_application(app)

            assert result == (set(), False)
            mock_popen.assert_called_once()
            mock_close.assert_called_once()
        finally:
            self._stop_patchers()

    def test_ejecucion_por_metadatos_con_argumentos(self):
        """3.6.3.2.2: sin ejecutable directo, los argumentos de los metadatos llegan a Popen."""
        app = {"name": "TestApp"}  # sin executable ni app_id => rama de metadatos
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch(
                "src.hands.calibration_manager.os.path.isfile", return_value=True
            ), patch.object(
                manager,
                "_get_application_metadata",
                return_value=[
                    {"path": "/fake/meta/metadata_app.exe", "arguments": "--data file.txt"}
                ],
            ):
                result = manager.launch_application(app)

            assert result[1] is True
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == ["/fake/meta/metadata_app.exe", "--data", "file.txt"]
        finally:
            self._stop_patchers()

    def test_ejecucion_por_metadatos_sin_ruta_valida_retorna_falso(self):
        """3.6.3.2.2: metadatos sin ruta valida => no se ejecuta nada y retorna False."""
        app = {"name": "TestApp"}
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch(
                "src.hands.calibration_manager.os.path.isfile", return_value=False
            ), patch.object(
                manager,
                "_get_application_metadata",
                return_value=[{"path": "/inexistente/app.exe", "arguments": "--x"}],
            ):
                result = manager.launch_application(app)

            assert result[1] is False
            mock_popen.assert_not_called()
        finally:
            self._stop_patchers()

    def test_ejecucion_por_app_id_ignora_argumentos(self):
        """3.6.3.2.2: con app_id se lanza via explorer shell:AppsFolder; arguments no se adjuntan."""
        app = {
            "name": "TestApp",
            "app_id": "FakePublisher.TestApp",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            result = manager.launch_application(app)

            assert result[1] is True
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert cmd == ["explorer.exe", "shell:AppsFolder\\FakePublisher.TestApp"]
        finally:
            self._stop_patchers()

    def test_ejecucion_reutiliza_ventana_existente_sin_popen(self):
        """3.6.3.2.2: ventana existente reutilizable => True sin ejecutar Popen (argumentos no se aplican)."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch.object(
                manager, "_find_existing_application_window", return_value=MagicMock()
            ), patch.object(manager, "_get_window_handles", return_value={12345}), patch.object(
                manager, "_get_process_ids", return_value={67890}
            ):
                result = manager.launch_application(app)

            assert result[1] is True
            mock_popen.assert_not_called()
            assert manager._last_launch_was_owned is False
        finally:
            self._stop_patchers()

    def test_ejecucion_app_vacia_o_sin_nombre_no_ejecuta(self):
        """3.6.3.2.2: app nula/vacia o sin nombre => (set(), False) sin Popen."""
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            for app in ({}, {"executable": "/fake/path/testapp.exe", "arguments": "--x"}, {"name": "   "}):
                result = manager.launch_application(app)
                assert result == (set(), False)
            mock_popen.assert_not_called()
        finally:
            self._stop_patchers()

    def test_ejecucion_sin_ejecutable_ni_metadatos_retorna_falso(self):
        """3.6.3.2.2: nombre valido pero sin ejecutable/app_id/metadatos => False sin Popen."""
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch.object(manager, "_get_application_metadata", return_value=[]):
                result = manager.launch_application({"name": "TestApp", "arguments": "--verbose"})
            assert result[1] is False
            mock_popen.assert_not_called()
        finally:
            self._stop_patchers()

    def test_ejecucion_permiso_denegado_retorna_falso(self):
        """3.6.3.2.2: permisos insuficientes al lanzar => PermissionError capturado => False."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            mock_popen.side_effect = PermissionError(13, "Permission denied")
            result = manager.launch_application(app)
            assert result == (set(), False)
        finally:
            self._stop_patchers()

    def test_ejecucion_app_bloqueada_o_juego_no_ejecuta(self):
        """3.6.3.2.2: aplicacion ignorada/juego => (set(), False) sin Popen ni argumentos."""
        app = {
            "name": "TestApp",
            "executable": "/fake/path/testapp.exe",
            "arguments": "--verbose",
        }
        manager = self._make_manager()
        mock_popen = self._mock_launch_flow(manager)
        try:
            with patch.object(manager, "_should_ignore_application", return_value=True):
                result = manager.launch_application(app)

            assert result == (set(), False)
            mock_popen.assert_not_called()
            assert manager._last_launch_window is None
        finally:
            self._stop_patchers()
