# -*- coding: utf-8 -*-
"""Tests de compatibilidad de APIs consumidas por el modelo ApplicationKnowledge.

Verifica (unidad 3.1.3.2 — Mantener compatibilidad con APIs ya utilizadas) que
los consumidores actuales del modelo pueden usar las APIs existentes sin
romperse, y que el contrato minimo (name + type) es compatible con todos los
consumidores identificados en 3.1.3.1.

Consumidores verificados:
  1. Brain._get_application_knowledge()      — accede integrator.applications.keys(),
                                               get_application_capabilities(),
                                               is_application_capable()
  2. HTNManager._application_catalog_available() — accede integrator.application_manager.applications
  3. Planner.load_application_knowledge()   — accede integrator.applications,
                                               convert_application_to_nodes()
  4. Executor._evaluate_condition()         — aplicações_core.get_application_manager().applications
  5. _check_application_available()         — accede app.executable, app.url
  6. open_application()                     — accede app.name, app.executable, app.url,
                                               app.preflight_requirements

No se modifica codigo de produccion.
"""

import logging
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# SUPRESION DE LOG DE SISTEMA (antes de importar src/)
# ---------------------------------------------------------------------------
# La importacion de Brain, HTNManager, Planner y Executor inicializa componentes
# del sistema (PerformanceOptimizer, SelfImprovementSystem, etc.) que escriben
# JSON log messages a stdout durante la inicializacion y el apagado (teardown).
# Esto genera ruido en la salida de los tests sin aportar informacion de test.
# Se suprime con logging.disable(CRITICAL) antes de cualquier import de src/,
# y se mantiene desactivado durante toda la sesion via fixture session-scoped.
# Ningun test de este archivo usa caplog, por lo que no hay perdida de cobertura.
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.applications_core import (  # noqa: E402
    ApplicationCapability,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    open_application,
    _check_application_available,
    _check_application_login,
    get_application_manager,
)
from src.hands.planner.application_integration import (  # noqa: E402
    ApplicationKnowledgeIntegrator,
    get_application_knowledge_integrator,
)


@pytest.fixture(autouse=True, scope="session")
def _suppress_system_logs():
    """Mantiene logging.disable(CRITICAL) activado durante toda la sesion de test
    para suprimir el ruido de inicializacion y teardown de los componentes del sistema.
    No se restaura el nivel al finalizar: el proceso de test esta a punto de terminar
    y los singletons del sistema (__del__/stop) emiten logs durante el apagado que
    tambien deben suprimirse. logging.disable(NOSET) al final permitiria ese ruido."""
    logging.disable(logging.CRITICAL)
    yield


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_minimal_app(name="MinApp", app_type="utility"):
    """ApplicationKnowledge con SOLO los campos obligatorios del contrato minimo (3.1.2)."""
    return ApplicationKnowledge(name=name, type=app_type)


def _make_integrator_with_manager(manager=None):
    """Instancia de integrador para testing con un gestor inyectado."""
    integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
    integrator.application_manager = manager
    integrator.memory_manager = None
    return integrator


def _make_minimal_manager(name="MinApp", app_type="utility"):
    """ApplicationManager con una app minimal (solo name + type) en el dict de applications.

    No persiste nada: se asigna directamente en self.applications para evitar
    efectos secundarios en entities.json.
    """
    manager = ApplicationManager()
    manager.applications.clear()
    app = _make_minimal_app(name=name, app_type=app_type)
    manager.applications[app.name.lower()] = app
    return manager


# ---------------------------------------------------------------------------
# 1. Brain consumer API compatibility
# ---------------------------------------------------------------------------

class TestBrainApplicationKnowledgeConsumer:
    """Brain._get_application_knowledge() consume el API del integrador."""

    @pytest.fixture(autouse=True)
    def _brain(self):
        from src.brain.llm import Brain
        self.brain = Brain(model="llama3")

    def test_returns_expected_dict_format(self):
        """El resultado tiene las claves que Brain expone al LLM: applications, total_applications, supported_capabilities."""
        result = self.brain._get_application_knowledge()
        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "applications", "total_applications", "supported_capabilities",
        }

    def test_applications_entries_have_capabilities_and_available(self):
        """Cada entrada de applications tiene capabilities (dict) y available (bool)."""
        result = self.brain._get_application_knowledge()
        apps = result["applications"]
        assert isinstance(apps, dict)
        assert result["total_applications"] == len(apps)
        for app_name, info in apps.items():
            assert "capabilities" in info
            assert "available" in info
            assert isinstance(info["capabilities"], dict)
            assert isinstance(info["available"], bool)

    def test_chrome_present_and_open_capable(self):
        """Chrome esta en el catalogo y es capaz de OPEN (api usada por Brain)."""
        result = self.brain._get_application_knowledge()
        assert "chrome" in result["applications"]
        chrome_info = result["applications"]["chrome"]
        assert chrome_info["available"] is True
        assert "open_chrome" in chrome_info["capabilities"]

    def test_spotify_present(self):
        """Spotify esta en el catalogo."""
        result = self.brain._get_application_knowledge()
        assert "spotify" in result["applications"]

    def test_supported_capabilities_constant(self):
        """supported_capabilities es una lista de strings."""
        result = self.brain._get_application_knowledge()
        caps = result["supported_capabilities"]
        assert isinstance(caps, list)
        assert all(isinstance(c, str) for c in caps)


# ---------------------------------------------------------------------------
# 2. HTNManager consumer API compatibility
# ---------------------------------------------------------------------------

class TestHTNManagerCatalogConsumer:
    """HTNManager._application_catalog_available() consume el API del integrador."""

    def test_catalog_available_with_real_integrator(self):
        """Devuelve True cuando el integrador tiene un manager con aplicaciones registradas."""
        from src.hands.planner.htn_manager import HTNManager
        htn = HTNManager()
        assert htn._application_catalog_available() is True

    def test_catalog_available_false_when_manager_none(self):
        """Devuelve False cuando application_manager es None."""
        from src.hands.planner.htn_manager import HTNManager
        integrator = _make_integrator_with_manager(None)
        htn = HTNManager()
        htn.application_integrator = integrator
        assert htn._application_catalog_available() is False

    def test_catalog_available_false_when_applications_empty(self):
        """Devuelve False cuando applications es un dict vacio."""
        from src.hands.planner.htn_manager import HTNManager
        integrator = _make_integrator_with_manager(get_application_manager())
        integrator.application_manager = MagicMock()
        integrator.application_manager.applications = {}
        htn = HTNManager()
        htn.application_integrator = integrator
        assert htn._application_catalog_available() is False


# ---------------------------------------------------------------------------
# 3. Planner consumer API compatibility
# ---------------------------------------------------------------------------

class TestPlannerApplicationKnowledgeConsumer:
    """Planner consume el API del integrador via load_application_knowledge y wrappers."""

    @pytest.fixture(autouse=True)
    def _planner(self):
        from src.hands.planner.planner import Planner
        self.planner = Planner()

    def test_load_application_knowledge_loads_nodes(self):
        """load_application_knowledge carga nodes de todas las apps al catalogo del planner."""
        initial = len(self.planner.available_nodes)
        self.planner.load_application_knowledge()
        assert len(self.planner.available_nodes) > initial
        assert "app_chrome" in self.planner.available_nodes
        assert "app_spotify" in self.planner.available_nodes

    def test_get_applications_by_capability(self):
        """get_applications_by_capability devuelve nombres de apps con la capacidad."""
        result = self.planner.get_applications_by_capability("open")
        assert isinstance(result, list)
        assert "Chrome" in result

    def test_get_applications_by_capability_invalid_returns_empty(self):
        """Una capacidad invalida devuelve lista vacia (no lanza)."""
        result = self.planner.get_applications_by_capability("nonexistent_xyz")
        assert result == []

    def test_get_application_capabilities(self):
        """get_application_capabilities devuelve dict de capacidades para chrome."""
        caps = self.planner.get_application_capabilities("chrome")
        assert isinstance(caps, dict)
        assert "open_chrome" in caps
        assert caps["open_chrome"]["capability"] == "open"

    def test_get_application_capabilities_not_found(self):
        """get_application_capabilities devuelve {} para una app inexistente."""
        caps = self.planner.get_application_capabilities("nonexistent_xyz")
        assert caps == {}

    def test_get_application_ui_requirements(self):
        """get_application_ui_requirements devuelve elementos UI requeridos."""
        elements = self.planner.get_application_ui_requirements("chrome", "navigate")
        assert isinstance(elements, list)
        assert "address_bar" in elements

    def test_get_application_ui_requirements_no_ui_for_open(self):
        """Una capacidad sin elementos UI (open) devuelve lista vacia."""
        elements = self.planner.get_application_ui_requirements("chrome", "open")
        assert elements == []


# ---------------------------------------------------------------------------
# 4. Executor consumer API compatibility (catalog fallback)
# ---------------------------------------------------------------------------

class TestExecutorCatalogFallbackConsumer:
    """Executor._evaluate_condition consume el catalogo declarativo via
    applications_core.get_application_manager() cuando el estado runtime esta vacio."""

    @pytest.fixture
    def executor(self):
        from src.hands.executor import Executor
        with patch("src.hands.executor.logger"):
            return Executor()

    def test_browser_available_via_catalog_fallback(self, executor):
        """browser_available es True via catalogo cuando el estado runtime no observa apps.
        Ejerce: applications_core.get_application_manager().applications keys con 'chrome'."""
        executor.current_state.application_states = {}
        assert executor._evaluate_condition("browser_available") is True

    def test_application_available_via_catalog_fallback(self, executor):
        """application_available es True via catalogo cuando el estado runtime esta vacio."""
        executor.current_state.application_states = {}
        assert executor._evaluate_condition("application_available") is True

    def test_browser_available_via_runtime_state(self, executor):
        """browser_available es True cuando el estado runtime tiene un navegador abierto."""
        executor.current_state.application_states = {
            "chrome": {"open": True},
        }
        assert executor._evaluate_condition("browser_available") is True

    def test_browser_available_runtime_non_browser_still_true_via_catalog(self, executor):
        """browser_available sigue True via catalogo aunque el runtime observe apps no-navegador."""
        executor.current_state.application_states = {
            "spotify": {"open": True},
        }
        assert executor._evaluate_condition("browser_available") is True


# ---------------------------------------------------------------------------
# 5. Internal functions consumer API compatibility
# ---------------------------------------------------------------------------

class TestInternalFunctionsConsumerCompatibility:
    """Funciones internas en applications_core.py consumen el modelo ApplicationKnowledge."""

    def test_check_application_available_field_access_executable(self):
        """_check_application_available accede app.executable (campo opcional del contrato)."""
        app = _make_minimal_app(name="FakeApp", app_type="utility")
        # Con executable=None y url=None -> False
        assert _check_application_available(app) is False

    def test_check_application_available_with_url(self):
        """_check_application_available usa app.url cuando executable esta vacio."""
        app = ApplicationKnowledge(
            name="UrlApp", type="webapp", executable=None, url="https://example.com",
        )
        assert _check_application_available(app) is True

    def test_check_application_login_returns_true(self):
        """_check_application_login siempre devuelve True por compatibilidad."""
        app = _make_minimal_app(name="LoginApp", app_type="media")
        assert _check_application_login(app) is True

    def test_open_application_resolves_from_model(self):
        """open_application resuelve la app desde el modelo y accede app.name, app.executable,
        app.preflight_requirements — API consumida por el executor/accion registrada."""
        with patch("src.hands.applications_core.subprocess.Popen") as mock_popen, \
             patch(
                 "src.hands.applications_core._check_application_available",
                 return_value=True,
             ):
            mock_popen.return_value = MagicMock()
            result = open_application("chrome")
            assert isinstance(result, str)
            assert "Chrome" in result
            mock_popen.assert_called_once_with(["chrome"])

    def test_open_application_not_found_raises(self):
        """open_application levanta ValueError cuando la app no esta en el modelo."""
        with pytest.raises(ValueError, match="no encontrada"):
            open_application("nonexistent_app_xyz")

    def test_open_application_minimal_app_with_executable(self):
        """open_application accede app.executable, app.name y app.preflight_requirements;
        una app minimal (contrato 3.1.2) con ejecutable funciona correctamente.
        Se parchea subprocess.Popen para evitar ejecucion real."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        manager.applications["minapp"].executable = "fake_exe"
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ), patch(
            "src.hands.applications_core.subprocess.Popen"
        ) as mock_popen:
            mock_popen.return_value = MagicMock()
            result = open_application("minapp")
            assert isinstance(result, str)
            assert "MinApp" in result
            mock_popen.assert_called_once_with(["fake_exe"])

    def test_open_application_minimal_app_no_executable_no_url(self):
        """open_application accede app.executable y app.url; con ambos None levanta RuntimeError.

        NOTA: el except block en applications_core.py:506 tiene un bug de produccion:
        str(exc, "applications_core.py", "method", 506) usa str() con 4 argumentos lo cual
        es invalido en Python, causando TypeError que enmascara el RuntimeError original.
        Este test documenta el comportamiento actual (TypeError) como discrepancia de produccion.
        La compatibilidad del API modelo no se ve afectada: open_application accede correctamente
        a app.executable y app.url; el bug esta unicamente en el manejador de errores."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ):
            with pytest.raises(TypeError):
                open_application("minapp")


# ---------------------------------------------------------------------------
# 6. Contrato minimo compatibility con todas las APIs consumidas
# ---------------------------------------------------------------------------

class TestMinimalContractConsumerCompatibility:
    """Verifica que una ApplicationKnowledge con SOLO name + type (contrato minimo
    definido en 3.1.2) es compatible con todas las APIs consumidas por los
    consumidores reales identificados en 3.1.3.1."""

    def test_minimal_app_satisfies_dataclass_contract(self):
        """ApplicationKnowledge(name, type) crea instancia con todos los defaults correctos."""
        app = _make_minimal_app(name="MinApp", app_type="utility")
        assert app.name == "MinApp"
        assert app.type == "utility"
        # Campos obligatorios
        assert app.executable is None
        assert app.url is None
        assert app.icon is None
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]
        assert app.login_required is False
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.default_state == ApplicationState.CLOSED
        assert app.metadata == {}

    def test_convert_application_to_nodes_with_minimal_app(self):
        """convert_application_to_nodes funciona con una app minimal (solo name+type)."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        integrator = _make_integrator_with_manager(manager)
        nodes = integrator.convert_application_to_nodes("minapp")
        assert len(nodes) >= 1  # al menos el nodo de aplicacion
        app_node = next((n for n in nodes if n.id == "app_minapp"), None)
        assert app_node is not None
        assert app_node.name == "MinApp"

    def test_get_application_capabilities_with_minimal_app(self):
        """get_application_capabilities devuelve {} para una app sin capacidades declaradas."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        integrator = _make_integrator_with_manager(manager)
        caps = integrator.get_application_capabilities("minapp")
        assert caps == {}

    def test_get_ui_elements_for_capability_with_minimal_app(self):
        """get_ui_elements_for_capability devuelve [] para una app sin elementos UI."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        integrator = _make_integrator_with_manager(manager)
        result = integrator.get_ui_elements_for_capability("minapp", ApplicationCapability.OPEN)
        assert result == []

    def test_is_application_capable_with_minimal_app(self):
        """is_application_capable devuelve False para una app sin capacidades."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        integrator = _make_integrator_with_manager(manager)
        assert integrator.is_application_capable("minapp", ApplicationCapability.OPEN) is False

    def test_get_applications_by_capability_with_minimal_app(self):
        """get_applications_by_capability funciona con una app minimal sin capacidades."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        integrator = _make_integrator_with_manager(manager)
        result = integrator.get_applications_by_capability(ApplicationCapability.OPEN)
        assert result == []

    def test_get_application_with_minimal_app(self):
        """get_application resuelve la app minimal por nombre normalizado."""
        manager = _make_minimal_manager(name="MinApp", app_type="utility")
        app = manager.get_application("minapp")
        assert app is not None
        assert app.name == "MinApp"
        assert app.type == "utility"

    def test_brain_consumer_with_minimal_app_in_catalog(self):
        """Brain._get_application_knowledge() consume correctamente una app minimal
        registrada en el catalogo del singleton."""
        # Registramos temporalmente una app minimal en el singleton y luego la quitamos.
        app = _make_minimal_app(name="TestMinApp", app_type="utility")
        original_applications = dict(get_application_manager().applications)
        try:
            get_application_manager().applications["testminapp"] = app
            from src.brain.llm import Brain
            brain = Brain(model="llama3")
            result = brain._get_application_knowledge()
            assert "testminapp" in result["applications"]
            info = result["applications"]["testminapp"]
            assert info["capabilities"] == {}
            assert info["available"] is False
            assert result["total_applications"] == len(result["applications"])
        finally:
            get_application_manager().applications = original_applications
