# -*- coding: utf-8 -*-
"""Tests unitarios de CalibrationManager.calibrate_application (unidad 3.8.6.2).

Verifica que la calibracion de la ventana real de una aplicacion objetivo
usa un flujo universal y NO depende de coordenadas o plantillas codificadas
por programa.

Todos los tests mockean las dependencias pesadas (screen manager, vision,
preflight, lanzamiento de procesos) para evitar interaccion con el SO real.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.hands.calibration.calibration_manager import (
    CalibrationManager,
    CalibrationPreflightResult,
    CalibrationResult,
    LaunchState,
)


def _make_manager():
    """Instancia CalibrationManager mockeando dependencias de __init__."""
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


class TestCalibrateApplicationNoHardcodedPerProgram:
    """3.8.6.2 - No depende de coordenadas o plantillas codificadas por programa."""

    def test_no_builtin_calibrators_registered(self):
        """_register_builtin_calibrators deja el registro vacio (flujo universal)."""
        manager = _make_manager()
        assert manager.calibrators == {}

    def test_calibrate_application_uses_universal_flow_not_per_program_code(self):
        """calibrate_application no tiene ramas especificas por nombre de programa."""
        manager = _make_manager()
        # El flujo universal es el mismo para cualquier application_info.
        # No existen condiciones tipo "if nombre == 'notepad'" ni hardcoding.
        import inspect
        source = inspect.getsource(manager.calibrate_application)
        # Verificar que no hay referencias hardcodeadas a programas especificos
        for hardcoded in ["notepad.exe", "calc.exe", "chrome.exe", "firefox.exe"]:
            assert hardcoded.lower() not in source.lower(), (
                f"Se encontro referencia hardcodeada a {hardcoded} en calibrate_application"
            )


class TestCalibrateApplicationApplicationNotFound:
    """3.8.6.2 - Aplicacion no encontrada."""

    def test_calibrate_application_not_found_returns_error(self):
        manager = _make_manager()
        with patch.object(manager, "_resolve_application", return_value=None):
            result = manager.calibrate_application("aplicacion_inexistente_xyz")
        assert result.success is False
        assert "no encontrada" in result.error.lower() or "No encontrada" in result.error


class TestCalibrateApplicationPreflightRejected:
    """3.8.6.2 - Preflight rechaza la aplicacion."""

    def test_calibrate_application_preflight_not_allowed(self):
        manager = _make_manager()
        app_info = {"name": "BlockedApp", "app_id": "blocked", "path": ""}
        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=False,
                    application_name="BlockedApp",
                    application_id="blocked",
                    reason="Aplicacion bloqueada por politica",
                ),
            ):
                result = manager.calibrate_application(app_info)
        assert result.success is False
        assert result.error is not None


class TestCalibrateApplicationLaunchFailed:
    """3.8.6.2 - Lanzamiento de aplicacion fallido."""

    def test_calibrate_application_launch_failed_returns_error(self):
        manager = _make_manager()
        app_info = {"name": "TestApp", "app_id": "test", "path": ""}
        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=True, application_name="TestApp", application_id="test"
                ),
            ):
                with patch.object(
                    manager, "launch_application", return_value=(set(), False)
                ):
                    result = manager.calibrate_application(app_info)
        assert result.success is False
        assert "ventana GUI" in result.error or "No se pudo abrir" in result.error


class TestCalibrateApplicationWindowPreparationFailed:
    """3.8.6.2 - Preparacion de ventana fallida."""

    def test_calibrate_application_prepare_window_failed_returns_error(self):
        manager = _make_manager()
        app_info = {"name": "TestApp", "app_id": "test", "path": ""}
        mock_window = MagicMock()
        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=True, application_name="TestApp", application_id="test"
                ),
            ):
                with patch.object(
                    manager,
                    "launch_application",
                    return_value=({12345}, True),
                ):
                    manager._last_launch_window = mock_window
                    manager._last_launch_owned_hwnds = set()
                    manager._last_launch_owned_pids = set()
                    manager._last_launch_was_owned = False
                    with patch.object(
                        manager, "_get_window_handle", return_value=12345
                    ):
                        with patch.object(
                            manager, "_get_window_process_id", return_value=67890
                        ):
                            with patch.object(
                                manager, "_is_process_elevated", return_value=False
                            ):
                                with patch.object(
                                    manager,
                                    "_prepare_window_for_calibration",
                                    return_value=None,
                                ):
                                    result = manager.calibrate_application(app_info)
        assert result.success is False
        assert "monitor" in result.error.lower() or "prepar" in result.error.lower()


class TestCalibrateApplicationSuccess:
    """3.8.6.2 - Calibracion exitosa mediante flujo universal."""

    def test_calibrate_application_success_flow(self):
        manager = _make_manager()
        app_info = {"name": "TestApp", "app_id": "test", "path": ""}
        mock_window = MagicMock()

        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=True, application_name="TestApp", application_id="test"
                ),
            ):
                with patch.object(
                    manager,
                    "launch_application",
                    return_value=({12345}, True),
                ):
                    manager._last_launch_window = mock_window
                    manager._last_launch_owned_hwnds = set()
                    manager._last_launch_owned_pids = set()
                    manager._last_launch_was_owned = False
                    with patch.object(
                        manager, "_get_window_handle", return_value=12345
                    ):
                        with patch.object(
                            manager, "_get_window_process_id", return_value=67890
                        ):
                            with patch.object(
                                manager, "_is_process_elevated", return_value=False
                            ):
                                mock_monitor = MagicMock()
                                mock_monitor.monitor_id = 1
                                with patch.object(
                                    manager,
                                    "_prepare_window_for_calibration",
                                    return_value=mock_monitor,
                                ):
                                    with patch.object(
                                        manager,
                                        "_get_window_by_handle",
                                        return_value=mock_window,
                                    ):
                                        mock_result = CalibrationResult(
                                            "TestApp",
                                            __import__(
                                                "src.hands.calibration.calibration_manager",
                                                fromlist=["ApplicationType"],
                                            ).ApplicationType.GENERIC,
                                            1,
                                            True,
                                            3,
                                            calibration_data={
                                                "elements": [
                                                    {"name": "btn_ok", "center": [100, 200]}
                                                ]
                                            },
                                        )
                                        with patch.object(
                                            manager,
                                            "_calibrate_open_window",
                                            return_value=mock_result,
                                        ):
                                            with patch.object(
                                                manager,
                                                "_save_application_calibration",
                                            ) as mock_save:
                                                result = manager.calibrate_application(
                                                    app_info
                                                )
        assert result.success is True
        assert result.elements_count == 3
        mock_save.assert_called_once()


class TestCalibrateApplicationScreenNumberSpecified:
    """3.8.6.2 - Calibracion en monitor especifico."""

    def test_calibrate_application_with_screen_number(self):
        manager = _make_manager()
        app_info = {"name": "TestApp", "app_id": "test", "path": ""}
        mock_window = MagicMock()

        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=True, application_name="TestApp", application_id="test"
                ),
            ):
                with patch.object(
                    manager,
                    "launch_application",
                    return_value=({12345}, True),
                ):
                    manager._last_launch_window = mock_window
                    manager._last_launch_owned_hwnds = set()
                    manager._last_launch_owned_pids = set()
                    manager._last_launch_was_owned = False
                    with patch.object(
                        manager, "_get_window_handle", return_value=12345
                    ):
                        with patch.object(
                            manager, "_get_window_process_id", return_value=67890
                        ):
                            with patch.object(
                                manager, "_is_process_elevated", return_value=False
                            ):
                                mock_monitor = MagicMock()
                                mock_monitor.monitor_id = 2
                                with patch.object(
                                    manager,
                                    "_prepare_window_for_calibration",
                                    return_value=mock_monitor,
                                ):
                                    mock_target = MagicMock()
                                    mock_target.monitor_id = 2
                                    with patch.object(
                                        manager.screen_manager,
                                        "get_monitor",
                                        return_value=mock_target,
                                    ):
                                        with patch.object(
                                            manager,
                                            "_get_window_by_handle",
                                            return_value=mock_window,
                                        ):
                                            mock_result = CalibrationResult(
                                                "TestApp",
                                                __import__(
                                                    "src.hands.calibration.calibration_manager",
                                                    fromlist=["ApplicationType"],
                                                ).ApplicationType.GENERIC,
                                                2,
                                                True,
                                                2,
                                            )
                                            with patch.object(
                                                manager,
                                                "_calibrate_open_window",
                                                return_value=mock_result,
                                            ):
                                                with patch.object(
                                                    manager,
                                                    "_save_application_calibration",
                                                ):
                                                    result = manager.calibrate_application(
                                                        app_info, screen_number=2
                                                    )
        assert result.success is True
        assert result.screen_number == 2


class TestCalibrateApplicationElevatedProcess:
    """3.8.6.2 - Proceso elevado rechazado."""

    def test_calibrate_application_elevated_process_returns_error(self):
        manager = _make_manager()
        app_info = {"name": "TestApp", "app_id": "test", "path": ""}
        mock_window = MagicMock()

        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=True, application_name="TestApp", application_id="test"
                ),
            ):
                with patch.object(
                    manager,
                    "launch_application",
                    return_value=({12345}, True),
                ):
                    manager._last_launch_window = mock_window
                    manager._last_launch_owned_hwnds = set()
                    manager._last_launch_owned_pids = set()
                    manager._last_launch_was_owned = False
                    with patch.object(
                        manager, "_get_window_handle", return_value=12345
                    ):
                        with patch.object(
                            manager, "_get_window_process_id", return_value=67890
                        ):
                            with patch.object(
                                manager, "_is_process_elevated", return_value=True
                            ):
                                result = manager.calibrate_application(app_info)
        assert result.success is False
        assert "elevado" in result.error.lower() or "privilegios" in result.error.lower()


class TestCalibrateApplicationNoElementsDetected:
    """3.8.6.2 - No se detectaron elementos interactivos."""

    def test_calibrate_application_no_elements_returns_error(self):
        manager = _make_manager()
        app_info = {"name": "TestApp", "app_id": "test", "path": ""}
        mock_window = MagicMock()

        with patch.object(manager, "_resolve_application", return_value=app_info):
            with patch.object(
                manager,
                "preflight_application",
                return_value=CalibrationPreflightResult(
                    allowed=True, application_name="TestApp", application_id="test"
                ),
            ):
                with patch.object(
                    manager,
                    "launch_application",
                    return_value=({12345}, True),
                ):
                    manager._last_launch_window = mock_window
                    manager._last_launch_owned_hwnds = set()
                    manager._last_launch_owned_pids = set()
                    manager._last_launch_was_owned = False
                    with patch.object(
                        manager, "_get_window_handle", return_value=12345
                    ):
                        with patch.object(
                            manager, "_get_window_process_id", return_value=67890
                        ):
                            with patch.object(
                                manager, "_is_process_elevated", return_value=False
                            ):
                                mock_monitor = MagicMock()
                                mock_monitor.monitor_id = 1
                                with patch.object(
                                    manager,
                                    "_prepare_window_for_calibration",
                                    return_value=mock_monitor,
                                ):
                                    with patch.object(
                                        manager,
                                        "_get_window_by_handle",
                                        return_value=mock_window,
                                    ):
                                        mock_result = CalibrationResult(
                                            "TestApp",
                                            __import__(
                                                "src.hands.calibration.calibration_manager",
                                                fromlist=["ApplicationType"],
                                            ).ApplicationType.GENERIC,
                                            1,
                                            False,
                                            0,
                                            error="No se detectaron elementos interactivos",
                                        )
                                        with patch.object(
                                            manager,
                                            "_calibrate_open_window",
                                            return_value=mock_result,
                                        ):
                                            result = manager.calibrate_application(app_info)
        assert result.success is False
        assert "elementos" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
