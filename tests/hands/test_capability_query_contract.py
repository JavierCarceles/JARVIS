# -*- coding: utf-8 -*-
"""Tests del contrato canónico de la consulta de capacidades (hoja 3.3.2.1).

Unidad 3.3.2.1: "Definir una consulta de capacidades sin duplicar APIs existentes."

El "contrato" (fase 3.3.2) establece qué es la **consulta canónica de capacidades**
y qué comportamiento debe tener, reutilizando las APIs existentes sin duplicar su
lógica. La capa canónica es ``ApplicationManager``/``ApplicationKnowledge``
(src/hands/applications_core.py); ``ApplicationKnowledgeIntegrator`` y ``Planner``
DEBEN delegar a esa capa, no reimplementarla.

La consulta canónica se compone de:

1. Consulta por aplicación (lista de capacidades):
   ``ApplicationManager.get_application_capabilities(app_name) -> Dict[str, Any]``
   Devuelve un dict cuyas claves son los *names* de las capability definitions y
   cuyos valores contienen al menos ``capability`` (string del Enum.value),
   ``description``, ``preconditions``, ``effects``, ``required_ui_elements``,
   ``cost``. Devuelve ``{}`` para apps desconocidas o sin capabilities.

2. Búsqueda de una capability concreta (definición):
   ``ApplicationKnowledge.get_capability(name) -> Optional[ApplicationCapabilityDef]``
   Acepta el *name* de la capability o su *value* (string). No distingue mayúsculas.
   Devuelve ``None`` si no existe.

3. Verificación booleana:
   ``ApplicationKnowledge.is_capable(capability) -> bool``
   Exige el Enum ``ApplicationCapability`` (no acepta string).

4. Consulta inversa (apps con una capability):
   ``ApplicationManager.get_applications_by_capability(capability) -> List[ApplicationKnowledge]``
   Exige el Enum ``ApplicationCapability``.

5. Funciones módulo (compatibilidad): ``get_application_knowledge``,
   ``get_applications_by_capability`` (acepta string).

``ApplicationKnowledgeIntegrator`` y ``Planner`` delegan a (1)-(5) sin reimplementar
la lógica de la capa modelo. Estos tests verifican el contrato y la no duplicación.

No se modifica código de producción.
"""

import logging
from unittest.mock import MagicMock, patch

# Se supprime el log del sistema antes de importar src/.
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.applications_core import (  # noqa: E402
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    UIElement,
    get_application_knowledge,
    get_applications_by_capability,
    get_application_manager,
)
from src.hands.planner.application_integration import (  # noqa: E402
    ApplicationKnowledgeIntegrator,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_minimal_manager():
    """ApplicationManager sin __init__ (evita registrar Chrome/Spotify)."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _FakeMemoryManager:
        def __init__(self):
            self.saved = []

        def save_entity(self, entity):
            self.saved.append(entity)

        def get_entities_by_type(self, t):
            return []

    manager.memory_manager = _FakeMemoryManager()
    return manager


def _make_integrator_with_manager(manager):
    """ApplicationKnowledgeIntegrator con un gestor inyectado."""
    integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
    integrator.application_manager = manager
    integrator.memory_manager = None
    return integrator


def _make_cap_def(
    capability: ApplicationCapability = ApplicationCapability.OPEN,
    name: str = "open_app",
    **overrides,
) -> ApplicationCapabilityDef:
    defaults = dict(
        capability=capability,
        name=name,
        description="Desc",
        required_ui_elements=[],
        preconditions=[],
        effects=["effect_x"],
        cost=1.0,
    )
    defaults.update(overrides)
    return ApplicationCapabilityDef(**defaults)


def _make_app(
    name: str = "TestApp",
    app_type: str = "utility",
    capabilities=None,
) -> ApplicationKnowledge:
    return ApplicationKnowledge(
        name=name,
        type=app_type,
        executable=f"{name.lower()}_exe",
        url="https://example.com",
        capabilities=capabilities or [],
        ui_elements=[],
        states=[],
    )


# ---------------------------------------------------------------------------
# 1. CONTRATO CANÓNICO DE LA CAPABILITY QUERY (capa modelo)
# ---------------------------------------------------------------------------

class TestCanonicalCapabilityQueryContract:
    """Define el contrato canónico de la capability query en ApplicationManager."""

    def setup_method(self, _method=None):
        self.manager = _make_minimal_manager()
        self.chrome = _make_app(
            "Chrome", "browser",
            capabilities=[
                _make_cap_def(ApplicationCapability.OPEN, "open_chrome",
                              description="Abre Chrome",
                              preconditions=["chrome_closed"],
                              effects=["chrome_open"],
                              cost=10.0),
                _make_cap_def(ApplicationCapability.NAVIGATE, "navigate_to_url",
                              required_ui_elements=["address_bar"],
                              preconditions=["chrome_open"],
                              effects=["url_changed"],
                              cost=3.0),
            ],
        )
        self.manager.applications["chrome"] = self.chrome

    # --- 1a. get_application_capabilities: consulta por aplicación ---

    def test_get_application_capabilities_is_canonical_query(self):
        """get_application_capabilities es la consulta canónica por aplicación.

        Devuelve un dict cuyas claves son los *names* de las capability defs."""
        caps = self.manager.get_application_capabilities("chrome")
        assert isinstance(caps, dict)
        assert "open_chrome" in caps
        assert "navigate_to_url" in caps

    def test_get_application_capabilities_structure(self):
        """Cada entrada de la capability query contiene los campos canónicos."""
        caps = self.manager.get_application_capabilities("chrome")
        for key, value in caps.items():
            assert "capability" in value  # string del Enum.value
            assert isinstance(value["capability"], str)
            assert "description" in value
            assert "preconditions" in value
            assert "effects" in value
            assert "required_ui_elements" in value
            assert "cost" in value

    def test_get_application_capabilities_capability_field_matches_enum(self):
        """El campo ``capability`` dentro del dict es el ``value`` del Enum."""
        caps = self.manager.get_application_capabilities("chrome")
        assert caps["open_chrome"]["capability"] == "open"
        assert caps["navigate_to_url"]["capability"] == "navigate"

    def test_get_application_capabilities_not_found_returns_empty(self):
        """Apps desconocidas → {} (no lanza)."""
        assert self.manager.get_application_capabilities("nonexistent") == {}

    def test_get_application_capabilities_no_capabilities_returns_empty(self):
        """Apps sin capabilities declaradas → {}."""
        app = _make_app("NoCapApp", "utility")
        self.manager.applications["nocapapp"] = app
        assert self.manager.get_application_capabilities("nocapapp") == {}

    def test_get_application_capabilities_resolves_alias(self):
        """La query resuelve aliases de aplicación (Google Chrome → chrome)."""
        real_manager = ApplicationManager()
        caps = real_manager.get_application_capabilities("Google Chrome")
        assert isinstance(caps, dict)
        assert "open_chrome" in caps

    # --- 1b. get_capability: búsqueda de una capability concreta ---

    def test_get_capability_returns_def_by_name(self):
        """get_capability(name) devuelve la ApplicationCapabilityDef completa."""
        cap_def = self.chrome.get_capability("open_chrome")
        assert cap_def is not None
        assert cap_def.capability == ApplicationCapability.OPEN
        assert cap_def.name == "open_chrome"

    def test_get_capability_returns_def_by_value(self):
        """get_capability acepta también el *value* del Enum (string)."""
        cap_def = self.chrome.get_capability("open")
        assert cap_def is not None
        assert cap_def.name == "open_chrome"

    def test_get_capability_case_insensitive(self):
        """get_capability no distingue mayúsculas/minúsculas."""
        assert self.chrome.get_capability("OPEN_CHROME") is not None
        assert self.chrome.get_capability("Open_Chrome") is not None

    def test_get_capability_not_found_returns_none(self):
        """Capability inexistente → None."""
        assert self.chrome.get_capability("missing_cap") is None
        assert self.chrome.get_capability("") is None

    def test_get_capability_returns_none_for_app_without_capabilities(self):
        """App sin capabilities → get_capability siempre devuelve None."""
        app = _make_app("NoCap", "utility")
        assert app.get_capability("open") is None

    # --- 1c. is_capable: verificación booleana (tipo Enum) ---

    def test_is_capable_true_with_enum(self):
        """is_capable(enum) devuelve True cuando la capability está declarada."""
        assert self.chrome.is_capable(ApplicationCapability.OPEN) is True

    def test_is_capable_false_with_enum(self):
        """is_capable(enum) devuelve False cuando la capability no está declarada."""
        assert self.chrome.is_capable(ApplicationCapability.CLOSE) is False

    def test_is_capable_false_with_string(self):
        """is_capable NO acepta strings: compara enums directamente."""
        assert self.chrome.is_capable("open") is False

    def test_is_capable_false_empty_capabilities(self):
        """App sin capabilities → is_capable siempre False."""
        app = _make_app("NoCap", "utility")
        assert app.is_capable(ApplicationCapability.OPEN) is False

    # --- 1d. get_applications_by_capability: consulta inversa ---

    def test_get_applications_by_capability_returns_matching_apps(self):
        """Devuelve las apps que declaran la capability (List[ApplicationKnowledge])."""
        apps = self.manager.get_applications_by_capability(ApplicationCapability.OPEN)
        assert any(a.name == "Chrome" for a in apps)

    def test_get_applications_by_capability_open_excludes_others(self):
        """Solo las apps con la capability aparecen en el resultado."""
        spotify = _make_app(
            "Spotify", "media",
            capabilities=[_make_cap_def(ApplicationCapability.OPEN, "open_spotify")],
        )
        self.manager.applications["spotify"] = spotify
        apps = self.manager.get_applications_by_capability(ApplicationCapability.OPEN)
        names = [a.name for a in apps]
        assert "Chrome" in names
        assert "Spotify" in names

    def test_get_applications_by_capability_close_no_match(self):
        """Ninguna app declara CLOSE → lista vacía."""
        apps = self.manager.get_applications_by_capability(ApplicationCapability.CLOSE)
        assert apps == []

    # --- 1e. Funciones módulo (compatibilidad) ---

    def test_module_get_application_knowledge_returns_dict(self):
        """get_application_knowledge(app_name) serializa el modelo a dict."""
        knowledge = get_application_knowledge("chrome")
        assert isinstance(knowledge, dict)
        assert knowledge["name"] == "Chrome"
        assert "capabilities" in knowledge
        assert "open_chrome" in knowledge["capabilities"]

    def test_module_get_applications_by_capability_returns_names(self):
        """get_applications_by_capability(name) devuelve List[str] de nombres."""
        apps = get_applications_by_capability("open")
        assert isinstance(apps, list)
        assert all(isinstance(n, str) for n in apps)
        assert "Chrome" in apps


# ---------------------------------------------------------------------------
# 2. NO DUPLICACIÓN: la capa integradora delega a la capa modelo
# ---------------------------------------------------------------------------

class TestNoDuplicationIntegratorDelegatesToModel:
    """ApplicationKnowledgeIntegrator DEBE delegar a ApplicationManager,
    no reimplementar la query."""

    def test_get_application_capabilities_delegates_to_manager(self):
        """El integrador llama a manager.get_application_capabilities."""
        manager = _make_minimal_manager()
        manager.applications["chrome"] = _make_app(
            "Chrome", "browser",
            capabilities=[_make_cap_def(ApplicationCapability.OPEN, "open_chrome")],
        )
        spy = MagicMock(wraps=manager.get_application_capabilities)
        with patch.object(type(manager), "get_application_capabilities", spy):
            integrator = _make_integrator_with_manager(manager)
            caps = integrator.get_application_capabilities("chrome")
        spy.assert_called_once_with("chrome")
        assert "open_chrome" in caps

    def test_is_application_capable_delegates_to_app_knowledge(self):
        """is_application_capable delega a ApplicationKnowledge.is_capable,
        no reimplementa la comparación de enums."""
        manager = _make_minimal_manager()
        cap_def = _make_cap_def(ApplicationCapability.OPEN, "open_chrome")
        app = ApplicationKnowledge(
            name="Chrome", type="browser",
            capabilities=[cap_def],
        )
        app.is_capable = MagicMock(wraps=app.is_capable)  # spy
        manager.applications["chrome"] = app
        integrator = _make_integrator_with_manager(manager)
        result = integrator.is_application_capable("chrome", ApplicationCapability.OPEN)
        app.is_capable.assert_called_once_with(ApplicationCapability.OPEN)
        assert result is True

    def test_get_applications_by_capability_delegates_to_manager(self):
        """get_applications_by_capability del integrador delega a manager."""
        manager = _make_minimal_manager()
        manager.applications["chrome"] = _make_app(
            "Chrome", "browser",
            capabilities=[_make_cap_def(ApplicationCapability.OPEN, "open_chrome")],
        )
        spy = MagicMock(wraps=manager.get_applications_by_capability)
        with patch.object(type(manager), "get_applications_by_capability", spy):
            integrator = _make_integrator_with_manager(manager)
            result = integrator.get_applications_by_capability(ApplicationCapability.OPEN)
        spy.assert_called_once()
        assert "Chrome" in result


# ---------------------------------------------------------------------------
# 3. CONSISTENCIA ENTRE CAPAS: misma query → mismo resultado estructural
# ---------------------------------------------------------------------------

class TestQueryConsistencyAcrossLayers:
    """La query canónica devuelve resultados consistentes a través de las capas."""

    def setup_method(self, _method=None):
        self.real_manager = ApplicationManager()

    def test_manager_and_integrator_return_same_capability_keys(self):
        """Manager.get_application_capabilities e Integrator.get_application_capabilities
        devuelven las mismas claves para la misma app."""
        integrator = _make_integrator_with_manager(self.real_manager)
        manager_caps = self.real_manager.get_application_capabilities("chrome")
        integrator_caps = integrator.get_application_capabilities("chrome")
        assert set(manager_caps.keys()) == set(integrator_caps.keys())
        assert manager_caps["open_chrome"]["capability"] == integrator_caps["open_chrome"]["capability"]

    def test_manager_and_integrator_is_capable_consistent(self):
        """is_capable (enum) es consistente entre ApplicationKnowledge y el integrador."""
        integrator = _make_integrator_with_manager(self.real_manager)
        app = self.real_manager.get_application("chrome")
        assert app is not None
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert integrator.is_application_capable("chrome", ApplicationCapability.OPEN) is True
        assert app.is_capable(ApplicationCapability.LOGIN) is False
        assert integrator.is_application_capable("chrome", ApplicationCapability.LOGIN) is False

    def test_planner_delegates_to_integrator(self):
        """Planner.get_application_capabilities delega al integrador (no duplica)."""
        from src.hands.planner.planner import Planner
        integrator = _make_integrator_with_manager(self.real_manager)
        spy = MagicMock(wraps=integrator.get_application_capabilities)
        planner = Planner()
        planner.application_integrator = integrator
        with patch.object(type(integrator), "get_application_capabilities", spy):
            planner_caps = planner.get_application_capabilities("chrome")
        spy.assert_called_once_with("chrome")
        assert "open_chrome" in planner_caps

    def test_planner_get_applications_by_capability_delegates(self):
        """Planner.get_applications_by_capability delega al integrador."""
        from src.hands.planner.planner import Planner
        integrator = _make_integrator_with_manager(self.real_manager)
        spy = MagicMock(wraps=integrator.get_applications_by_capability)
        planner = Planner()
        planner.application_integrator = integrator
        with patch.object(type(integrator), "get_applications_by_capability", spy):
            result = planner.get_applications_by_capability("open")
        spy.assert_called_once()
        assert "Chrome" in result

    def test_planner_and_integrator_consistent_for_unknown_app(self):
        """App desconocida → {} en todas las capas."""
        integrator = _make_integrator_with_manager(self.real_manager)
        assert integrator.get_application_capabilities("nonexistent") == {}
        from src.hands.planner.planner import Planner
        planner = Planner()
        planner.application_integrator = integrator
        assert planner.get_application_capabilities("nonexistent") == {}


# ---------------------------------------------------------------------------
# 4. CASOS CONTRA EL MODELO REAL: gap documentado (D-CAP-MODEL-GAP)
# ---------------------------------------------------------------------------

class TestCanonicalQueryWithRealModel:
    """Verifica el contrato de la capability query contra el modelo real."""

    def setup_method(self, _method=None):
        self.manager = get_application_manager()

    def test_chrome_has_open_capability(self):
        """Chrome (hardcodeado) declara capability OPEN."""
        assert self.manager.get_application("chrome").is_capable(
            ApplicationCapability.OPEN
        ) is True

    def test_youtube_has_no_capabilities(self):
        """YouTube (reconstruido desde entities.json) no declara capabilities.

        Gap documentado en 3.3.1.1 (D-CAP-MODEL-GAP): las apps reconstruidas
        desde entities.json carecen de la clave 'capabilities'."""
        app = self.manager.get_application("youtube")
        assert app is not None
        assert app.capabilities == []
        assert app.is_capable(ApplicationCapability.OPEN) is False

    def test_get_applications_by_capability_open_only_hardcoded(self):
        """Solo Chrome y Spotify (hardcodeadas) aparecen para OPEN."""
        apps = self.manager.get_applications_by_capability(ApplicationCapability.OPEN)
        names = [a.name for a in apps]
        assert "Chrome" in names
        assert "Spotify" in names

    def test_query_for_unknown_capability(self):
        """Una capability válida del Enum pero no declarada por ninguna app
        devuelve lista vacía en la consulta inversa."""
        apps = self.manager.get_applications_by_capability(ApplicationCapability.CLOSE)
        assert apps == []

    def test_capability_query_returns_real_definitions(self):
        """La capability query devuelve definiciones reales con estructura completa."""
        caps = self.manager.get_application_capabilities("chrome")
        assert "open_chrome" in caps
        open_cap = caps["open_chrome"]
        assert open_cap["capability"] == "open"
        assert open_cap["cost"] == 10.0
        assert "chrome_closed" in open_cap["preconditions"]
        assert "chrome_open" in open_cap["effects"]
        assert open_cap["required_ui_elements"] == []
