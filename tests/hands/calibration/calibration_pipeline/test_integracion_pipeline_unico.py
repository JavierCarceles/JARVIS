# -*- coding: ascii -*-
"""
Tests de integracion del motor de calibracion con CalibrationManager,
ApplicationManager y los calibradores heredados de navegador.

Comprueban, sin SO real (multiplataforma), el contrato de integracion:

- Via unica: ``CalibrationManager`` no conserva la via heredada paralela
  (captura de monitor + calibrador visual directo); ``calibrate_application``,
  ``calibrate_application_deep`` y ``calibrate_all_applications`` llaman al
  pipeline unico exactamente una vez por aplicacion y nunca al calibrador
  visual ni a la captura de monitor por su cuenta.
- Calibradores heredados (Chrome, Edge, Firefox y ``delegate_legacy_calibration``):
  delegan UNA sola vez en ``CalibrationManager.calibrate_application``, informan
  el resultado real (``success`` falso si la puerta de seguridad bloquea) y no
  reintentan ni calibran por otra via.
- Informe por aplicacion y elemento: fuentes, identidad, tipo, capacidad de
  interaccion, espacio de coordenadas, monitor, escala, precision, accion
  permitida, vigencia y motivo de fallo; el gestor lo conserva en
  ``calibration_data["report"]``.
- Recursos para el Planner: solo llegan recursos con metodo de interaccion real;
  ante error del servicio de vigencia no llega nada.

Solo se sustituye la ejecucion del pipeline (que toca SO, vision, puntero y
SQLite) por un doble que registra las llamadas; la resolucion, la conversion
del informe y la delegacion son las de produccion.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.hands.calibration.calibration_manager import (
    ApplicationType,
    CalibrationManager,
    CalibrationResult,
)
from src.hands.calibration.calibration_pipeline import (
    INTERACTION_NONE,
    STAGE_PREFLIGHT,
    CalibrationReport,
    ElementReport,
    UICalibrationPipeline,
    delegate_legacy_calibration,
)


def _make_manager() -> CalibrationManager:
    with patch(
        "src.hands.calibration.calibration_manager.get_screen_manager", return_value=MagicMock()
    ), patch(
        "src.hands.calibration.calibration_manager.get_calibration_config", return_value=MagicMock()
    ), patch(
        "src.hands.calibration.universal_visual_calibrator.UniversalVisualCalibrator",
        return_value=MagicMock(),
    ):
        return CalibrationManager()


def _elemento(control_id: str = "btn_guardar") -> ElementReport:
    return ElementReport(
        control_id=control_id,
        name="Guardar",
        sources=["uia", "qwen3vl"],
        identity={"automation_id": "SaveButton"},
        control_type="button",
        interaction_capability="invoke",
        coordinate_space="desktop_pixels",
        display_id="display-2",
        scale_factor=1.5,
        precision={"pointer_error_px": 0.0},
        allowed_action="accessibility",
        validity="VALIDADO",
        failure_reason="",
    )


def _informe_ok(app_name: str = "Notepad") -> CalibrationReport:
    report = CalibrationReport(app_id=app_name.lower(), app_name=app_name)
    report.success = True
    report.profile_id = "perfil-1"
    report.display = {"display_id": "display-2", "scale_factor": 1.5}
    report.elements = [_elemento()]
    report.legacy_elements = [{"name": "guardar", "center": [10, 20]}]
    return report


class _PipelineFalso:
    """Registra las llamadas al pipeline y devuelve el informe indicado."""

    def __init__(self, report: Optional[CalibrationReport] = None) -> None:
        self.report = report or _informe_ok()
        self.calls: List[Any] = []

    def calibrate(self, app_info: Any, **kwargs: Any) -> CalibrationReport:
        self.calls.append((dict(app_info), dict(kwargs)))
        return self.report

    def legacy_screen_number(self, display: Any) -> int:
        return 2

    def resources_for_planner(self, app_id: str, window_id: int) -> List[Dict[str, Any]]:
        self.calls.append(("resources_for_planner", app_id, window_id))
        return [{"control_id": "c1", "interaction_method": "accessibility"}]


def _manager_con_pipeline(report: Optional[CalibrationReport] = None):
    manager = _make_manager()
    pipeline = _PipelineFalso(report)
    manager.set_calibration_pipeline(pipeline)
    return manager, pipeline


def _resultado(success: bool, error: Optional[str] = None) -> CalibrationResult:
    return CalibrationResult(
        "app", ApplicationType.GENERIC, 0, success, 1 if success else 0, error=error,
        calibration_data={"elements": [{"name": "x", "center": [1, 2]}]} if success else {},
    )


class _GestorFalso:
    """Doble de CalibrationManager para los calibradores heredados."""

    def __init__(self, result: Any = None, exc: Optional[Exception] = None) -> None:
        self.result = result if result is not None else _resultado(True)
        self.exc = exc
        self.calls: List[Any] = []

    def calibrate_application(self, name: str, screen_number: Any = None) -> Any:
        self.calls.append((name, screen_number))
        if self.exc is not None:
            raise self.exc
        return self.result


# ---------------------------------------------------------------------------
# Via unica
# ---------------------------------------------------------------------------


class TestViaUnicaDeCalibracion:
    def test_el_gestor_no_conserva_la_via_heredada_paralela(self):
        manager = _make_manager()
        for nombre in ("_calibrate_open_window", "_get_monitors_to_calibrate",
                       "_prepare_window_for_calibration", "_extract_elements"):
            assert not hasattr(manager, nombre), nombre

    def test_calibrate_application_llama_al_pipeline_una_vez_y_no_al_calibrador_visual(self):
        manager, pipeline = _manager_con_pipeline()
        result = manager.calibrate_application("Notepad")
        assert result.success
        assert len(pipeline.calls) == 1
        app_info, kwargs = pipeline.calls[0]
        assert app_info["name"] == "Notepad"
        assert kwargs["depth"] == "surface"
        manager.visual_calibrator.calibrate.assert_not_called()
        manager.screen_manager.capture_monitor.assert_not_called()

    @pytest.mark.parametrize("branch_ref,depth", [(None, "deep"), ("menu_archivo", "branch")])
    def test_calibracion_profunda_una_sola_llamada(self, branch_ref, depth):
        manager, pipeline = _manager_con_pipeline()
        manager.calibrate_application_deep("Notepad", branch_ref=branch_ref)
        assert len(pipeline.calls) == 1
        assert pipeline.calls[0][1]["depth"] == depth
        assert pipeline.calls[0][1]["branch_ref"] == branch_ref
        manager.visual_calibrator.calibrate.assert_not_called()

    def test_calibrate_all_applications_una_llamada_por_aplicacion(self):
        manager, pipeline = _manager_con_pipeline()
        manager._resolve_application_list = lambda apps: [{"name": a} for a in apps]
        manager.is_application_calibrated = lambda name: False
        manager.calibration_config.max_applications = 0
        report = manager.calibrate_all_applications(["Notepad", "Calculadora"])
        nombres = [call[0]["name"] for call in pipeline.calls]
        assert nombres == ["Notepad", "Calculadora"]
        assert report["applications_requested"] == 2
        manager.visual_calibrator.calibrate.assert_not_called()

    def test_calibrate_all_applications_no_recalibra_las_ya_calibradas_sin_force(self):
        manager, pipeline = _manager_con_pipeline()
        manager._resolve_application_list = lambda apps: [{"name": a} for a in apps]
        manager.is_application_calibrated = lambda name: name == "Notepad"
        manager.calibration_config.max_applications = 0
        report = manager.calibrate_all_applications(["Notepad", "Calculadora"])
        assert [call[0]["name"] for call in pipeline.calls] == ["Calculadora"]
        assert len(report["skipped"]) == 1


# ---------------------------------------------------------------------------
# Calibradores heredados: una delegacion, resultado real, sin eludir puertas
# ---------------------------------------------------------------------------


class TestDelegacionHeredada:
    def test_delegate_legacy_calibration_delega_una_vez_y_es_honesto(self):
        gestor = _GestorFalso(_resultado(False, "aplicacion bloqueada para calibracion"))
        result = delegate_legacy_calibration("notepad", manager=gestor)
        assert gestor.calls == [("notepad", None)]
        assert result["success"] is False
        assert "bloqueada" in result["error"]

    def test_delegate_legacy_calibration_error_no_reintenta(self):
        gestor = _GestorFalso(exc=RuntimeError("pipeline caido"))
        result = delegate_legacy_calibration("notepad", 2, manager=gestor)
        assert gestor.calls == [("notepad", 2)]
        assert result["success"] is False
        assert "pipeline caido" in result["error"]

    def test_delegate_legacy_calibration_nombre_vacio_no_llama_al_gestor(self):
        gestor = _GestorFalso()
        result = delegate_legacy_calibration("   ", manager=gestor)
        assert gestor.calls == []
        assert result["success"] is False

    @pytest.mark.parametrize("exito", [True, False])
    def test_edge_delega_una_vez_en_el_gestor(self, exito):
        gestor = _GestorFalso(_resultado(exito, None if exito else "preflight bloqueado"))
        with patch("src.hands.calibration.calibration_manager.get_calibration_manager", return_value=gestor):
            from src.hands.browsers.edge.calibrator_edge import EdgeCalibrator

            result = EdgeCalibrator().calibrate_edge()
        assert gestor.calls == [("edge", None)]
        assert result["success"] is exito
        assert result["application"] == "edge"

    @pytest.mark.parametrize("exito", [True, False])
    def test_firefox_delega_una_vez_en_el_gestor(self, exito):
        gestor = _GestorFalso(_resultado(exito, None if exito else "preflight bloqueado"))
        with patch("src.hands.browsers.firefox.calibrator_firefox.get_calibration_manager", return_value=gestor):
            from src.hands.browsers.firefox.calibrator_firefox import FirefoxCalibrator

            result = FirefoxCalibrator().calibrate_firefox()
        assert gestor.calls == [("firefox", None)]
        assert result["success"] is exito
        assert result["application"] == "firefox"

    @pytest.mark.parametrize("exito", [True, False])
    def test_chrome_delega_una_vez_en_el_gestor(self, exito):
        gestor = _GestorFalso(_resultado(exito, None if exito else "preflight bloqueado"))
        with patch("src.hands.browsers.chrome.chrome_calibrator.get_calibration_manager", return_value=gestor):
            from src.hands.browsers.chrome.chrome_calibrator import ChromeCalibrator

            result = ChromeCalibrator().calibrate_chrome(0)
        assert gestor.calls == [("chrome", None)]
        assert result["success"] is exito

    def test_bloqueo_de_la_puerta_llega_como_fallo_por_el_gestor_real(self):
        """Con el gestor real, un fallo de preflight del pipeline se propaga como
        ``success`` falso (no hay calibracion alternativa)."""
        report = CalibrationReport(app_id="edge", app_name="edge")
        report.success = False
        report.stage_failed = STAGE_PREFLIGHT
        report.error = "aplicacion bloqueada para calibracion"
        manager, pipeline = _manager_con_pipeline(report)
        result = delegate_legacy_calibration("edge", manager=manager)
        assert len(pipeline.calls) == 1
        assert result["success"] is False
        assert "bloqueada" in result["error"]
        manager.visual_calibrator.calibrate.assert_not_called()


# ---------------------------------------------------------------------------
# Informe por aplicacion y elemento
# ---------------------------------------------------------------------------


CAMPOS_ELEMENTO = {
    "control_id", "name", "sources", "identity", "control_type", "interaction_capability",
    "coordinate_space", "display_id", "scale_factor", "precision", "allowed_action",
    "validity", "failure_reason",
}


class TestInformePorAplicacionYElemento:
    def test_informe_de_elemento_contiene_todos_los_campos(self):
        assert set(_elemento().to_dict()) == CAMPOS_ELEMENTO

    def test_el_gestor_conserva_el_informe_completo(self):
        manager, _ = _manager_con_pipeline()
        result = manager.calibrate_application("Notepad")
        report = result.calibration_data["report"]
        assert report["app_name"] == "Notepad"
        assert report["profile_id"] == "perfil-1"
        assert report["display"]["display_id"] == "display-2"
        assert len(report["elements"]) == 1
        assert set(report["elements"][0]) == CAMPOS_ELEMENTO
        assert result.calibration_data["profile_id"] == "perfil-1"
        # Compatibilidad: elementos heredados con la pantalla resuelta.
        assert result.calibration_data["elements"][0]["screen"] == 2

    def test_informe_fallido_conserva_etapa_y_motivo(self):
        report = CalibrationReport(app_id="notepad", app_name="Notepad")
        report.success = False
        report.stage_failed = STAGE_PREFLIGHT
        report.error = "bloqueada"
        manager, _ = _manager_con_pipeline(report)
        result = manager.calibrate_application("Notepad")
        assert result.success is False
        assert result.error == "bloqueada"
        assert result.calibration_data["report"]["stage_failed"] == STAGE_PREFLIGHT


# ---------------------------------------------------------------------------
# Recursos para el Planner
# ---------------------------------------------------------------------------


class _ValidezConRecursos:
    def __init__(self, resources: Any = None, exc: Optional[Exception] = None) -> None:
        self.resources = resources or []
        self.exc = exc
        self.calls: List[Any] = []

    def resources_for_planner(self, app_id: str, window_id: int) -> Any:
        self.calls.append((app_id, window_id))
        if self.exc is not None:
            raise self.exc
        return self.resources


class TestRecursosParaPlanner:
    def test_solo_llegan_recursos_con_metodo_de_interaccion_real(self):
        servicio = _ValidezConRecursos([
            {"control_id": "puntero", "interaction_method": "pointer"},
            {"control_id": "ax", "interaction_method": "accessibility"},
            {"control_id": "solo_llm", "interaction_method": INTERACTION_NONE},
            {"control_id": "caja_visual"},
        ])
        pipeline = UICalibrationPipeline(adapter=MagicMock(), validity_service=servicio)
        recursos = pipeline.resources_for_planner("Bloc de Notas", "7")
        assert [r["control_id"] for r in recursos] == ["puntero", "ax"]
        assert servicio.calls == [("bloc_de_notas", 7)]

    def test_error_del_servicio_no_publica_recursos(self):
        pipeline = UICalibrationPipeline(
            adapter=MagicMock(), validity_service=_ValidezConRecursos(exc=RuntimeError("sqlite"))
        )
        assert pipeline.resources_for_planner("notepad", 7) == []

    def test_el_gestor_pide_los_recursos_al_pipeline_unico(self):
        manager, pipeline = _manager_con_pipeline()
        recursos = manager.get_planner_resources("Notepad", 7)
        assert recursos == [{"control_id": "c1", "interaction_method": "accessibility"}]
        assert pipeline.calls[-1][0] == "resources_for_planner"
        assert pipeline.calls[-1][2] == 7
