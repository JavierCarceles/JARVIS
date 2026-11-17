# -*- coding: utf-8 -*-
"""Tests unitarios de CalibrationManager.calibrate_application (unidad 3.8.6.2).

Verifica que la calibracion de la ventana real de una aplicacion objetivo
usa un flujo universal y NO depende de coordenadas o plantillas codificadas
por programa.

Contrato vigente: ``calibrate_application`` resuelve el nombre y la clave de
almacenamiento de la aplicacion (``_pipeline_application``) y delega toda la
calibracion en el pipeline unico (``UICalibrationPipeline.calibrate``); el
informe resultante (``CalibrationReport``) se convierte a
``CalibrationResult`` (``_report_to_result``). La politica de calibracion, el
lanzamiento, la preparacion de ventana, la deteccion y la verificacion del
puntero son etapas del pipeline.

Dos tipos de prueba:
- Con el ``UICalibrationPipeline`` REAL y adaptador/lanzador simulados que no
  deben recibir ninguna llamada: la etapa de politica (preflight) real rechaza
  la aplicacion antes de tocar el SO.
- Con un pipeline falso que devuelve un ``CalibrationReport`` concreto: se
  verifica la delegacion (argumentos) y la conversion real del informe en el
  gestor. El pipeline falso no decide nada que el test pretenda probar.

Ningun test interactua con el SO real ni escribe en ``data/``.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.hands.calibration.calibration_manager import (
    CalibrationManager,
    CalibrationResult,
)
from src.hands.calibration.calibration_pipeline import (
    STAGE_LAUNCH,
    STAGE_POINTER,
    STAGE_PREFLIGHT,
    STAGE_WINDOW,
    CalibrationReport,
    UICalibrationPipeline,
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


class _PipelineFalso:
    """Pipeline falso: registra las llamadas y devuelve el informe indicado.

    Solo sustituye la ejecucion del pipeline (SO, vision, puntero, SQLite).
    La resolucion de la aplicacion y la conversion del informe a
    ``CalibrationResult`` son las reales de ``CalibrationManager``.
    """

    def __init__(self, report=None, exc=None, legacy_screen=0):
        self.report = report
        self.exc = exc
        self.legacy_screen = legacy_screen
        self.calls = []

    def calibrate(self, app_info, **kwargs):
        self.calls.append((dict(app_info), dict(kwargs)))
        if self.exc is not None:
            raise self.exc
        return self.report

    def legacy_screen_number(self, display):
        return self.legacy_screen


def _informe_fallido(stage, error):
    report = CalibrationReport(app_id="testapp", app_name="TestApp")
    report.success = False
    report.stage_failed = stage
    report.error = error
    return report


def _manager_con_pipeline_falso(report=None, exc=None, legacy_screen=0):
    manager = _make_manager()
    pipeline = _PipelineFalso(report=report, exc=exc, legacy_screen=legacy_screen)
    manager.set_calibration_pipeline(pipeline)
    return manager, pipeline


def _manager_con_pipeline_real_vigilado():
    """Gestor con el UICalibrationPipeline real cableado como en produccion
    (filtros de calibracion del gestor) y con adaptador de escritorio,
    lanzador y almacen simulados para detectar cualquier acceso al SO."""
    manager = _make_manager()
    adapter = MagicMock(name="adapter")
    launcher = MagicMock(name="launcher")
    store = MagicMock(name="store")
    pipeline = UICalibrationPipeline(
        adapter=adapter,
        launcher=launcher,
        store=store,
        # Sin atributo ``policy``: el pipeline usa la CalibrationPolicy real.
        vision=SimpleNamespace(),
        calibration_policy_checker=manager._calibration_policy_check,
    )
    manager.set_calibration_pipeline(pipeline)
    return manager, adapter, launcher, store


class TestCalibrateApplicationNoHardcodedPerProgram:
    """3.8.6.2 - No depende de coordenadas o plantillas codificadas por programa."""

    def test_no_builtin_calibrators_registered(self):
        """_register_builtin_calibrators deja el registro vacio (flujo universal)."""
        manager = _make_manager()
        assert manager.calibrators == {}

    def test_calibrate_application_uses_universal_flow_not_per_program_code(self):
        """calibrate_application y el camino que usa no tienen ramas
        especificas por nombre de programa."""
        manager = _make_manager()
        # El flujo universal es el mismo para cualquier application_info.
        # No existen condiciones tipo "if nombre == 'notepad'" ni hardcoding.
        for method in (
            manager.calibrate_application,
            manager._run_calibration_pipeline,
            manager._pipeline_application,
            manager._report_to_result,
        ):
            source = inspect.getsource(method)
            for hardcoded in ["notepad.exe", "calc.exe", "chrome.exe", "firefox.exe"]:
                assert hardcoded.lower() not in source.lower(), (
                    f"Se encontro referencia hardcodeada a {hardcoded} en {method.__name__}"
                )

    def test_calibrate_application_delega_en_el_pipeline_unico(self):
        """El gestor crea un unico UICalibrationPipeline con sus filtros de
        calibracion y su calibrador visual, y lo reutiliza."""
        manager = _make_manager()
        pipeline = manager.get_calibration_pipeline()
        assert isinstance(pipeline, UICalibrationPipeline)
        assert pipeline.calibration_policy_checker == manager._calibration_policy_check
        assert manager.get_calibration_pipeline() is pipeline


class TestCalibrateApplicationApplicationNotFound:
    """3.8.6.2 - Aplicacion no encontrada (nombre vacio o ausente)."""

    @pytest.mark.parametrize("application", ["", "   ", None, {"name": ""}, {"app_id": "x"}])
    def test_calibrate_application_not_found_returns_error(self, application):
        manager, pipeline = _manager_con_pipeline_falso(
            report=_informe_fallido(STAGE_LAUNCH, "no debe usarse")
        )
        result = manager.calibrate_application(application)
        assert isinstance(result, CalibrationResult)
        assert result.success is False
        assert "no encontrada" in result.error.lower()
        assert result.elements_count == 0
        # Sin aplicacion no se invoca el pipeline (no se abre ni calibra nada).
        assert pipeline.calls == []


class TestCalibrateApplicationPreflightRejected:
    """3.8.6.2 - La politica de calibracion (etapa preflight real) rechaza la
    aplicacion antes de tocar el SO."""

    def test_calibrate_application_preflight_not_allowed(self):
        manager, adapter, launcher, store = _manager_con_pipeline_real_vigilado()
        # "League of Legends" esta en CalibrationPolicy.BLOCKED_APPLICATIONS.
        result = manager.calibrate_application({"name": "League of Legends", "app_id": ""})
        assert result.success is False
        assert "bloqueada" in result.error.lower()
        assert result.elements_count == 0
        assert result.calibration_data["report"]["stage_failed"] == STAGE_PREFLIGHT
        # No se consulto el SO, no se lanzo nada y no se persistio nada.
        assert adapter.mock_calls == []
        assert launcher.mock_calls == []
        assert store.mock_calls == []


class TestCalibrateApplicationLaunchFailed:
    """3.8.6.2 - Lanzamiento de aplicacion fallido."""

    def test_calibrate_application_launch_failed_returns_error(self):
        error = "la aplicacion se abrio pero no se verifico ninguna ventana GUI"
        manager, pipeline = _manager_con_pipeline_falso(
            report=_informe_fallido(STAGE_LAUNCH, error)
        )
        result = manager.calibrate_application({"name": "TestApp", "app_id": "test", "path": ""})
        assert result.success is False
        assert result.error == error
        assert result.elements_count == 0
        assert result.calibration_data["report"]["stage_failed"] == STAGE_LAUNCH
        # Delegacion: una sola llamada con la aplicacion resuelta y la
        # calibracion de superficie con la politica de producto.
        assert len(pipeline.calls) == 1
        app_info, kwargs = pipeline.calls[0]
        assert app_info["name"] == "TestApp"
        assert app_info["app_id"] == "test"
        assert app_info["app_key"]
        assert kwargs == {
            "monitor_reference": None,
            "policy": "product",
            "depth": "surface",
            "branch_ref": None,
        }


class TestCalibrateApplicationWindowPreparationFailed:
    """3.8.6.2 - Preparacion de ventana fallida."""

    def test_calibrate_application_prepare_window_failed_returns_error(self):
        error = "no se pudo mover la ventana al monitor destino: acceso denegado"
        manager, pipeline = _manager_con_pipeline_falso(
            report=_informe_fallido(STAGE_WINDOW, error)
        )
        result = manager.calibrate_application({"name": "TestApp", "app_id": "test", "path": ""})
        assert result.success is False
        assert result.error == error
        assert "monitor" in result.error.lower()
        assert result.elements_count == 0
        assert result.calibration_data["report"]["stage_failed"] == STAGE_WINDOW
        assert len(pipeline.calls) == 1


class TestCalibrateApplicationSuccess:
    """3.8.6.2 - Calibracion exitosa mediante flujo universal."""

    def test_calibrate_application_success_flow(self):
        report = CalibrationReport(app_id="testapp", app_name="TestApp")
        report.success = True
        report.profile_id = "perfil-1"
        report.display = {"bounds": {"left": 0, "top": 0, "right": 1920, "bottom": 1080}}
        report.legacy_elements = [
            {"name": "btn_ok", "center": [100, 200]},
            {"name": "btn_cancel", "center": [180, 200]},
            {"name": "campo_texto", "center": [140, 120]},
        ]
        manager, pipeline = _manager_con_pipeline_falso(report=report, legacy_screen=1)
        result = manager.calibrate_application({"name": "TestApp", "app_id": "test", "path": ""})
        assert result.success is True
        assert result.error is None
        assert result.elements_count == 3
        assert result.screen_number == 1
        assert result.application_name == "TestApp"
        assert result.calibration_data["profile_id"] == "perfil-1"
        nombres = [e["name"] for e in result.calibration_data["elements"]]
        assert nombres == ["btn_ok", "btn_cancel", "campo_texto"]
        assert all(e["screen"] == 1 for e in result.calibration_data["elements"])
        # El informe original no se modifica al anadir la pantalla.
        assert all("screen" not in e for e in report.legacy_elements)
        assert len(pipeline.calls) == 1


class TestCalibrateApplicationScreenNumberSpecified:
    """3.8.6.2 - Calibracion en monitor especifico."""

    @pytest.mark.parametrize(
        "legacy_screen",
        [2, 0],
        ids=["monitor_resuelto_por_geometria", "sin_coincidencia_usa_el_solicitado"],
    )
    def test_calibrate_application_with_screen_number(self, legacy_screen):
        report = CalibrationReport(app_id="testapp", app_name="TestApp")
        report.success = True
        report.display = {"bounds": {"left": 1920, "top": 0, "right": 3840, "bottom": 1080}}
        report.legacy_elements = [{"name": "btn_ok", "center": [2000, 200]}]
        manager, pipeline = _manager_con_pipeline_falso(report=report, legacy_screen=legacy_screen)
        result = manager.calibrate_application(
            {"name": "TestApp", "app_id": "test", "path": ""}, screen_number=2
        )
        assert result.success is True
        assert result.screen_number == 2
        assert result.calibration_data["elements"][0]["screen"] == 2
        # El monitor pedido llega al pipeline como referencia de monitor.
        assert len(pipeline.calls) == 1
        assert pipeline.calls[0][1]["monitor_reference"] == 2


class TestCalibrateApplicationElevatedProcess:
    """3.8.6.2 - Aplicacion con riesgo de elevacion rechazada antes de abrirla.

    El filtro de calibracion del gestor (``_calibration_policy_check``), que el
    pipeline aplica en su etapa preflight, rechaza las herramientas
    administrativas que piden privilegios elevados; no se llega a lanzar el
    proceso.
    """

    def test_calibrate_application_elevated_process_returns_error(self):
        manager, adapter, launcher, store = _manager_con_pipeline_real_vigilado()
        # "Event Viewer" no esta en CalibrationPolicy.BLOCKED_APPLICATIONS pero
        # si en ELEVATION_RISK_NAME_PARTS del gestor.
        nombre = "Event Viewer"
        # Precondiciones: la politica general la permite y es el filtro de
        # riesgo de elevacion del gestor el que la rechaza.
        from src.hands.calibration.universal_visual_calibrator import CalibrationPolicy

        assert CalibrationPolicy.can_calibrate_application(nombre)[0] is True
        assert manager._is_elevation_risk_application(nombre) is True

        result = manager.calibrate_application({"name": nombre, "app_id": ""})
        assert result.success is False
        assert "bloqueada para calibraci" in result.error.lower()
        assert result.calibration_data["report"]["stage_failed"] == STAGE_PREFLIGHT
        assert adapter.mock_calls == []
        assert launcher.mock_calls == []
        assert store.mock_calls == []

    def test_filtro_de_calibracion_permite_aplicacion_normal(self):
        """Control positivo: una aplicacion GUI normal pasa el filtro."""
        manager = _make_manager()
        decision = manager._calibration_policy_check({"name": "Notepad", "app_id": ""})
        assert decision.allowed is True
        assert manager._is_elevation_risk_application("Notepad") is False


class TestCalibrateApplicationNoElementsDetected:
    """3.8.6.2 - No se detectaron elementos interactivos."""

    def test_calibrate_application_no_elements_returns_error(self):
        error = "ningun control supero la verificacion geometrica"
        report = _informe_fallido(STAGE_POINTER, error)
        manager, pipeline = _manager_con_pipeline_falso(report=report, legacy_screen=1)
        result = manager.calibrate_application({"name": "TestApp", "app_id": "test", "path": ""})
        assert result.success is False
        assert result.error == error
        assert result.elements_count == 0
        assert result.calibration_data["elements"] == []
        assert result.calibration_data["report"]["stage_failed"] == STAGE_POINTER

    def test_informe_fallido_sin_mensaje_no_se_presenta_como_exito(self):
        """Un informe sin exito y sin error explicito produce un error generico."""
        report = _informe_fallido(STAGE_POINTER, None)
        manager, _pipeline = _manager_con_pipeline_falso(report=report)
        result = manager.calibrate_application("TestApp")
        assert result.success is False
        assert result.error


class TestCalibrateApplicationPipelineException:
    """3.8.6.2 - Una excepcion del pipeline se convierte en resultado fallido."""

    def test_excepcion_del_pipeline_devuelve_error(self):
        manager, pipeline = _manager_con_pipeline_falso(exc=RuntimeError("fallo interno del pipeline"))
        result = manager.calibrate_application({"name": "TestApp", "app_id": "test"}, screen_number=3)
        assert result.success is False
        assert result.error == "fallo interno del pipeline"
        assert result.screen_number == 3
        assert result.elements_count == 0
        assert len(pipeline.calls) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
