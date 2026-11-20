# -*- coding: utf-8 -*-
"""Conexion de descubrimiento con requisitos de calibracion (3.8.6.1.2).

Cubre:
- CalibrationManager.get_aplicaciones_con_requisito_de_calibracion: el
  requisito de calibracion (calibration_policy del catalogo, fase 3.5)
  separado del resultado (ya_calibrada segun CalibrationManager).
- ApplicationDiscovery.registrar_requisitos_de_calibracion_descubiertos:
  registra CalibrationElement en el calibrador mejorado para que el
  planificador vea requisitos reales de aplicaciones descubiertas.
- Planner.get_calibration_requirements expone esos requisitos.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.hands.apps.application_discovery import ApplicationDiscovery, DiscoveredCandidate
from src.hands.apps.applications_core import ApplicationKnowledge, ApplicationManager
from src.hands.calibration.calibration_manager import CalibrationManager
from src.hands.calibration.calibrator import (
    CalibrationElement,
    CalibrationStatus,
    EnhancedCalibrator,
)
from src.hands.planner.planner import Planner


# ---------------------------------------------------------------------------
# Helpers de construccion aislada (sin mutar data/ ni ejecutar descubrimiento real)
# ---------------------------------------------------------------------------

def _minimal_app_manager(*apps: ApplicationKnowledge) -> ApplicationManager:
    """ApplicationManager sin __init__ (no carga entities.json ni registra
    Chrome/Spotify reales) y con memory_manager que no persiste en disco."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _MemoryManager:
        def save_entity(self, entity):
            return None

    manager.memory_manager = _MemoryManager()
    for app in apps:
        manager.register_application(app)
    return manager


def _calibration_manager_mocked():
    """CalibrationManager con dependencias pesadas mockeadas."""
    with patch(
        "src.hands.calibration.calibration_manager.get_screen_manager", return_value=MagicMock()
    ), patch(
        "src.hands.calibration.calibration_manager.get_calibration_config", return_value=MagicMock()
    ), patch(
        "src.hands.calibration.universal_visual_calibrator.UniversalVisualCalibrator",
        return_value=MagicMock(),
    ):
        return CalibrationManager()


def _discovery(app_manager, calibration):
    return ApplicationDiscovery(
        preflight=MagicMock(),
        clasificador=MagicMock(),
        storage=MagicMock(),
        calibration=calibration,
        machine_id="test-machine-38612",
        app_manager=app_manager,
    )


# ---------------------------------------------------------------------------
# CalibrationManager.get_aplicaciones_con_requisito_de_calibracion
# ---------------------------------------------------------------------------

class TestCalibrationManagerRequisitoResultado:
    def test_requisito_separado_de_resultado(self):
        """Una app con calibration_policy tiene requisito; ya_calibrada viene
        de CalibrationManager.is_application_calibrated (resultado), no del
        requisito."""
        mgr = _calibration_manager_mocked()
        app_manager = _minimal_app_manager(
            ApplicationKnowledge(name="Chrome", type="browser", calibration_policy=["address_bar"]),
            ApplicationKnowledge(name="AppPendiente", type="test", calibration_policy=["btn_ok"]),
            ApplicationKnowledge(name="Notepad", type="editor", calibration_policy=[]),
        )
        apps = [
            {"name": "Chrome", "source": "start_menu"},
            {"name": "AppPendiente", "source": "start_menu"},
            {"name": "Notepad", "source": "start_menu"},
            {"name": "Nada", "source": "start_menu"},
        ]

        def fake_is_calibrated(app):
            name = str(app.get("name", "")) if isinstance(app, dict) else str(app)
            return name == "Chrome"

        with patch.object(mgr, "is_application_calibrated", side_effect=fake_is_calibrated):
            resultado = mgr.get_aplicaciones_con_requisito_de_calibracion(
                aplicaciones=apps, app_manager=app_manager
            )

        por_nombre = {r["name"]: r for r in resultado}
        assert por_nombre["Chrome"]["requiere_calibracion"] is True
        assert por_nombre["Chrome"]["elementos_requeridos"] == ["address_bar"]
        assert por_nombre["Chrome"]["ya_calibrada"] is True
        assert por_nombre["Chrome"]["estado"] == "calibrada"

        assert por_nombre["AppPendiente"]["requiere_calibracion"] is True
        assert por_nombre["AppPendiente"]["elementos_requeridos"] == ["btn_ok"]
        assert por_nombre["AppPendiente"]["ya_calibrada"] is False
        assert por_nombre["AppPendiente"]["estado"] == "pendiente"

        assert por_nombre["Notepad"]["requiere_calibracion"] is False
        assert por_nombre["Notepad"]["elementos_requeridos"] == []
        assert por_nombre["Notepad"]["ya_calibrada"] is False
        assert por_nombre["Notepad"]["estado"] == "sin_requisito"

        assert por_nombre["Nada"]["requiere_calibracion"] is False
        assert por_nombre["Nada"]["estado"] == "sin_requisito"

    def test_lista_vacia(self):
        mgr = _calibration_manager_mocked()
        assert mgr.get_aplicaciones_con_requisito_de_calibracion(aplicaciones=[]) == []

    def test_elementos_varios_y_nombre_caso_insensible(self):
        mgr = _calibration_manager_mocked()
        app_manager = _minimal_app_manager(
            ApplicationKnowledge(
                name="Spotify", type="media", calibration_policy=["search_bar", "play_button"]
            )
        )
        apps = [{"name": "spotify", "source": "start_menu"}]
        with patch.object(mgr, "is_application_calibrated", return_value=False):
            resultado = mgr.get_aplicaciones_con_requisito_de_calibracion(aplicaciones=apps)
        assert len(resultado) == 1
        assert resultado[0]["estado"] == "pendiente"
        assert set(resultado[0]["elementos_requeridos"]) == {"search_bar", "play_button"}


# ---------------------------------------------------------------------------
# ApplicationDiscovery.registrar_requisitos_de_calibracion_descubiertos
# ---------------------------------------------------------------------------

class TestDiscoveryRegistraRequisitos:
    def _app_con_politica(self):
        return ApplicationKnowledge(
            name="AppTest", type="test", calibration_policy=["btn_ok", "menu_principal"]
        )

    def _calib_con_is_calibrated(self, value):
        calib = _calibration_manager_mocked()
        patch.object(calib, "is_application_calibrated", return_value=value).start()
        return calib

    def test_registra_calibration_elements_para_apps_con_politica(self):
        app = self._app_con_politica()
        app_manager = _minimal_app_manager(app)
        calib = self._calib_con_is_calibrated(False)
        disc = _discovery(app_manager, calib)
        cand = DiscoveredCandidate(candidate_id="c1", name="AppTest")
        with patch.object(disc, "descubrir_todos", return_value=[cand]):
            cal = EnhancedCalibrator()
            resultado = disc.registrar_requisitos_de_calibracion_descubiertos(
                calibrador=cal
            )

        assert "AppTest.btn_ok" in cal.elements
        assert "AppTest.menu_principal" in cal.elements
        el_ok = cal.elements["AppTest.btn_ok"]
        assert el_ok.application == "AppTest"
        assert el_ok.element_type == "btn_ok"
        assert el_ok.calibration_status == CalibrationStatus.NOT_CALIBRATED
        assert len(resultado) == 1
        assert resultado[0]["estado"] == "pendiente"

    def test_no_registra_app_sin_politica(self):
        app = ApplicationKnowledge(name="SinPolitica", type="test", calibration_policy=[])
        app_manager = _minimal_app_manager(app)
        calib = self._calib_con_is_calibrated(False)
        disc = _discovery(app_manager, calib)
        cand = DiscoveredCandidate(candidate_id="c2", name="SinPolitica")
        with patch.object(disc, "descubrir_todos", return_value=[cand]):
            cal = EnhancedCalibrator()
            disc.registrar_requisitos_de_calibracion_descubiertos(calibrador=cal)
        assert cal.elements == {}

    def test_elemento_ya_calibrada_tiene_estado_calibrado(self):
        app = self._app_con_politica()
        app_manager = _minimal_app_manager(app)
        calib = self._calib_con_is_calibrated(True)
        disc = _discovery(app_manager, calib)
        cand = DiscoveredCandidate(candidate_id="c3", name="AppTest")
        with patch.object(disc, "descubrir_todos", return_value=[cand]):
            cal = EnhancedCalibrator()
            disc.registrar_requisitos_de_calibracion_descubiertos(calibrador=cal)
        assert cal.elements["AppTest.btn_ok"].calibration_status == CalibrationStatus.CALIBRATED

    def test_no_registra_app_no_vinculada_al_catalogo(self):
        app_manager = _minimal_app_manager()  # sin aplicaciones registradas
        calib = self._calib_con_is_calibrated(False)
        disc = _discovery(app_manager, calib)
        cand = DiscoveredCandidate(candidate_id="c4", name="Desconocida")
        with patch.object(disc, "descubrir_todos", return_value=[cand]):
            cal = EnhancedCalibrator()
            disc.registrar_requisitos_de_calibracion_descubiertos(calibrador=cal)
        assert cal.elements == {}


# ---------------------------------------------------------------------------
# Planner expone requisitos registrados por el descubrimiento
# ---------------------------------------------------------------------------

class TestPlanificadorVeRequisitosDescubiertos:
    def test_get_calibration_requirements_retorna_elementos_registrados(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", calibration_policy=["address_bar", "search_bar"]
        )
        app_manager = _minimal_app_manager(app)
        calib = _calibration_manager_mocked()
        patch.object(calib, "is_application_calibrated", return_value=False).start()
        calib.get_aplicaciones_con_requisito_de_calibracion = MagicMock(return_value=[])
        disc = _discovery(app_manager, calib)
        cand = DiscoveredCandidate(candidate_id="c5", name="Chrome")
        cal = EnhancedCalibrator()
        with patch.object(disc, "descubrir_todos", return_value=[cand]):
            disc.registrar_requisitos_de_calibracion_descubiertos(calibrador=cal)

        planner = Planner.__new__(Planner)
        planner.calibrator = cal
        goal = SimpleNamespace(type="navigate", target="Chrome")
        requisitos = planner.get_calibration_requirements(goal)
        assert "Chrome.address_bar" in requisitos
        assert "Chrome.search_bar" in requisitos

    def test_goal_sin_elementos_registrados_retorna_vacia(self):
        planner = Planner.__new__(Planner)
        planner.calibrator = EnhancedCalibrator()
        goal = SimpleNamespace(type="navigate", target="Nada")
        assert planner.get_calibration_requirements(goal) == []
