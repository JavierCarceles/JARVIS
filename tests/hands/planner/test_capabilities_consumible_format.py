# -*- coding: utf-8 -*-
"""Tests de verificación de la hoja 3.3.3.1 — "Exponer capacidades en
formato consumible por planificacion.".

El planificador (``Planner``) debe exponer las capacidades de una aplicación en
un formato LISTA consumible por la fase de planificación, en lugar del dict de
nombres específicos de la aplicación. Reutiliza el contrato canónico
``get_application_capabilities`` (no duplica lógica) y maneja el ausente
(aplicación desconocida, integrador no disponible o aplicación conocida sin
capacidades declaradas) como ``[]``.

Se ejercita contra el modelo REAL (singleton ``ApplicationManager`` cargado desde
``data/memory/entities.json``): Chrome/Spotify declaran capabilities; YouTube,
GitHub y Twitch son apps reconstruidas sin capabilities. El modelo se lee en
modo solo-lectura: ningún test escribe ni altera ``entities.json``.
"""

import logging
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# SUPRESIÓN DE LOG DE SISTEMA (antes de importar src/)
# ---------------------------------------------------------------------------
# Importar Planner/integrador inicializa componentes del sistema
# (PerformanceOptimizer, SelfImprovementSystem, etc.) que escriben a stdout.
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.planner.planner import Planner  # noqa: E402
from src.hands.planner.node import Goal  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _suppress_system_logs():
    """Mantiene logging.disable(CRITICAL) activo durante toda la sesión."""
    logging.disable(logging.CRITICAL)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _planner() -> Planner:
    """Planificador con el integrador REAL (singleton)."""
    return Planner()


# ---------------------------------------------------------------------------
# Planner.get_application_capabilities_as_list — exposición consumible
# ---------------------------------------------------------------------------

class TestCapabilitiesConsumibleFormat:
    """``get_application_capabilities_as_list`` expone capacidades como lista
    de identificadores canónicos consumibles por el planificador."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_chrome_returns_consumible_identifier_list(self):
        """Chrome expone ['open', 'navigate', 'search'] (identificadores
        canónicos), no los nombres específicos de la aplicación."""
        result = self.planner.get_application_capabilities_as_list("chrome")
        assert isinstance(result, list)
        assert result == ["open", "navigate", "search"]
        assert all(isinstance(item, str) for item in result)

    def test_returns_list_format_not_dict(self):
        """El formato exponible es una LISTA (consumible), no el dict de
        nombres específicos que devuelve ``get_application_capabilities``."""
        as_list = self.planner.get_application_capabilities_as_list("chrome")
        as_dict = self.planner.get_application_capabilities("chrome")
        assert isinstance(as_list, list)
        assert isinstance(as_dict, dict)
        # Las claves del dict son nombres propios (open_chrome) que NO son el
        # formato consumible; la lista contiene los identificadores canónicos.
        assert "open_chrome" not in as_list
        assert "open_chrome" in as_dict

    def test_uses_consumible_identifier_not_app_specific_name(self):
        """La exposición contiene el identificador canónico ('open') y NO el
        nombre específico de la aplicación ('open_chrome')."""
        result = self.planner.get_application_capabilities_as_list("chrome")
        assert "open" in result
        assert "navigate" in result
        assert "search" in result
        assert "open_chrome" not in result
        assert "navigate_to_url" not in result
        assert "search_in_google" not in result

    def test_spotify_returns_open_and_navigate(self):
        """Spotify (hardcodeada) declara OPEN + NAVIGATE."""
        result = self.planner.get_application_capabilities_as_list("spotify")
        assert isinstance(result, list)
        assert "open" in result
        assert "navigate" in result

    def test_known_app_without_capabilities_returns_empty(self):
        """YouTube (app conocida reconstruida sin capabilities) → [] (ausente
        como []), distinto del caso de aplicación con capabilities."""
        assert self.planner.get_application_capabilities_as_list("youtube") == []
        assert self.planner.get_application_capabilities("youtube") == {}

    def test_unknown_app_returns_empty(self):
        """Aplicación desconocida → [] sin lanzar."""
        assert self.planner.get_application_capabilities_as_list(
            "nonexistent_xyz"
        ) == []

    def test_none_integrator_returns_empty(self):
        """Integrador no disponible → [] (ausente como []), sin excepción."""
        planner = Planner()
        planner.application_integrator = None
        assert planner.get_application_capabilities_as_list("chrome") == []

    def test_derives_from_canonical_contract_no_duplication(self):
        """La lista es una proyección del contrato canónico
        ``get_application_capabilities``: cada elemento proviene del campo
        ``capability`` del descriptor, en el mismo orden. Confirma que no
        duplica lógica fuente."""
        app_name = "chrome"
        caps = self.planner.get_application_capabilities(app_name)
        expected = [
            descriptor["capability"]
            for descriptor in caps.values()
            if isinstance(descriptor, dict) and descriptor.get("capability")
        ]
        assert (
            self.planner.get_application_capabilities_as_list(app_name)
            == expected
        )

    def test_deduplicates_and_skips_missing_capability(self):
        """Frente a descriptores duplicados o sin campo ``capability``, la lista
        expone identificadores únicos y omite los incompletos."""
        planner = Planner()
        planner.application_integrator = MagicMock()
        planner.application_integrator.get_application_capabilities = (
            lambda _name: {
                "a": {"capability": "open"},
                "b": {"capability": "open"},  # duplicado
                "c": {"capability": "navigate"},
                "d": {"capability": None},  # faltante
                "e": {"no_capability": True},  # sin capability
            }
        )
        result = planner.get_application_capabilities_as_list("any")
        assert result == ["open", "navigate"]

    def test_non_dict_descriptor_skipped(self):
        """Descriptores que no son dict no rompen la proyección consumible."""
        planner = Planner()
        planner.application_integrator = MagicMock()
        planner.application_integrator.get_application_capabilities = (
            lambda _name: {"a": {"capability": "open"}, "b": "opaque"}
        )
        assert planner.get_application_capabilities_as_list("any") == ["open"]


# ---------------------------------------------------------------------------
# build_application_aware_plan — exposición en la metadata del plan
# ---------------------------------------------------------------------------

class TestPlanExposesConsumibleCapabilities:
    """``build_application_aware_plan`` expone las capacidades de la app objetivo
    en formato lista consumible dentro de la metadata del plan, manejando el
    ausente como ``[]``."""

    @pytest.fixture()
    def planner(self):
        return _planner()

    def test_plan_exposes_consumible_capabilities_for_chrome(self, planner):
        """Un goal open_application sobre Chrome expone la lista canónica de
        capacidades consumibles y la app objetivo."""
        goal = Goal(
            id="g-open-chrome",
            type="open_application",
            target={"app_name": "chrome"},
            description="Abrir Chrome",
        )
        result = planner.build_application_aware_plan(goal, {})
        assert result.metadata["application_used"] == "Chrome"
        capabilities = result.metadata["application_capabilities"]
        assert isinstance(capabilities, list)
        assert capabilities == planner.get_application_capabilities_as_list(
            result.metadata["application_used"]
        )
        assert "open" in capabilities

    def test_plan_absent_app_exposes_empty_list(self, planner):
        """Cuando el goal no resuelve aplicación alguna (ausente), la metadata
        expone ``application_capabilities`` como ``[]`` (manejo del ausente) y
        ``application_used`` como None."""
        goal = Goal(
            id="g-no-app",
            type="unknown_type_xyz",
            target={},
            description="Goal sin aplicación resoluble",
        )
        result = planner.build_application_aware_plan(goal, {})
        assert result.metadata["application_used"] is None
        assert result.metadata["application_capabilities"] == []
        assert "application_capabilities" in result.metadata
