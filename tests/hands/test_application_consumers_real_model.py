# -*- coding: utf-8 -*-
"""Tests de verificación de consumidores con el modelo real de aplicaciones.

Verifica la hoja 3.2.4.2 — "Verificar que los consumidores existentes siguen
funcionando" — ejercitando los 6 consumidores identificados en 3.1.3.1 contra
el estado REAL del modelo (singleton ``ApplicationManager`` cargado desde
``data/memory/entities.json`` con 32 aplicaciones: Chrome/Spotify hardcodeadas
más entidades reconstruidas como YouTube, GitHub, Twitch, etc.).

Enfoque en las rutas afectadas por la serie 3.2.2.x:
  - Resolución por alias en ``get_application`` (3.2.2.5), consumida por el
    integrador, Brain, Planner, Executor y ``open_application``.
  - Normalización de claves con ``_normalize_name`` en registro y lookup (3.2.2.4).
  - Reconstrucción de ``ui_elements``/``states`` desde entities.json (3.2.2.1/3.2.2.2).

No se modifica código de producción. El modelo real se lee en modo solo-lectura:
ningún test escribe ni altera ``data/memory/entities.json`` (el singleton ya está
inicializado; ``subprocess.Popen`` se parchea en los tests de ejecución).
"""

import logging
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# SUPRESIÓN DE LOG DE SISTEMA (antes de importar src/)
# ---------------------------------------------------------------------------
# La importación de Brain, HTNManager, Planner y Executor inicializa componentes
# del sistema (PerformanceOptimizer, SelfImprovementSystem, etc.) que escriben
# JSON log messages a stdout. Se suprime antes de cualquier import de src/.
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.applications_core import (  # noqa: E402
    ApplicationCapability,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    get_application_manager,
    open_application,
    _check_application_available,
    _check_application_login,
)
from src.hands.planner.application_integration import (  # noqa: E402
    ApplicationKnowledgeIntegrator,
    get_application_knowledge_integrator,
)


@pytest.fixture(autouse=True, scope="session")
def _suppress_system_logs():
    """Mantiene logging.disable(CRITICAL) activado durante toda la sesión."""
    logging.disable(logging.CRITICAL)
    yield


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _real_manager() -> ApplicationManager:
    """ApplicationManager singleton real (cargado con entities.json)."""
    return get_application_manager()


def _real_integrator() -> ApplicationKnowledgeIntegrator:
    """ApplicationKnowledgeIntegrator singleton real."""
    return get_application_knowledge_integrator()


class _RecordingIntegrator(ApplicationKnowledgeIntegrator):
    """Wrapper del integrador real que registra llamadas get_application."""

    def __init__(self, real: ApplicationKnowledgeIntegrator) -> None:
        # No llamamos a super().__init__() para reutilizar el manager real ya
        # inicializado del singleton sin disparar re-importaciones.
        self.application_manager = real.application_manager
        self.memory_manager = real.memory_manager
        self.lookup_calls: list = []

    def _get_application(self, app_name: str) -> Any:
        self.lookup_calls.append(str(app_name))
        return super()._get_application(app_name)


# ---------------------------------------------------------------------------
# 1. ApplicationKnowledgeIntegrator — consumidor primario del modelo real
# ---------------------------------------------------------------------------

class TestIntegratorConsumesRealCatalog:
    """El integrador consume el catálogo real (Chrome + entidades reconstruidas)."""

    def test_convert_nodes_chrome_real_with_capabilities(self):
        """convert_application_to_nodes('chrome') produce nodo app + capability + ui
        usando el modelo REAL (Chrome hardcodeado con capabilities y ui_elements)."""
        integrator = _real_integrator()
        nodes = integrator.convert_application_to_nodes("chrome")
        ids = [getattr(n, "id", None) for n in nodes]
        assert "app_chrome" in ids
        # Chrome declara capability navigate → ui element address_bar
        assert "chrome_address_bar" in ids
        assert "chrome_navigate" in ids

    def test_convert_nodes_alias_through_integrator(self):
        """convert_application_to_nodes('gh') resuelve el alias a GitHub (reconstruido
        desde entities.json, sin capabilities) y produce solo el nodo app."""
        integrator = _real_integrator()
        app = integrator._get_application("gh")
        assert app is not None
        assert app.name == "GitHub"
        nodes = integrator.convert_application_to_nodes("gh")
        # GitHub reconstruido sin capabilities → solo el nodo aplicación.
        assert len(nodes) == 1
        assert nodes[0].id == "app_github"

    def test_get_application_capabilities_chrome_real(self):
        """get_application_capabilities('chrome') expone las capabilities reales."""
        integrator = _real_integrator()
        caps = integrator.get_application_capabilities("chrome")
        assert "open_chrome" in caps
        assert "navigate_to_url" in caps
        assert "search_in_google" in caps
        assert caps["open_chrome"]["capability"] == "open"

    def test_get_application_capabilities_alias_no_capabilities(self):
        """get_application_capabilities('yt') resuelve alias → YouTube (reconstruido
        sin capabilities) → dict vacío."""
        integrator = _real_integrator()
        caps = integrator.get_application_capabilities("yt")
        assert caps == {}

    def test_is_application_capable_chrome_open(self):
        """is_application_capable('chrome', OPEN) True con el modelo real."""
        integrator = _real_integrator()
        assert integrator.is_application_capable("chrome", ApplicationCapability.OPEN) is True

    def test_is_application_capable_alias_not_capable(self):
        """YouTube (reconstruido sin capabilities) no es capaz de OPEN."""
        integrator = _real_integrator()
        assert integrator.is_application_capable("yt", ApplicationCapability.OPEN) is False

    def test_get_applications_by_capability_open(self):
        """get_applications_by_capability(OPEN) incluye Chrome y Spotify (las únicas
        con la capability declarada en el modelo real). El integrador devuelve List[str]."""
        integrator = _real_integrator()
        result = integrator.get_applications_by_capability(ApplicationCapability.OPEN)
        assert isinstance(result, list)
        assert all(isinstance(n, str) for n in result)
        assert "Chrome" in result
        assert "Spotify" in result
        # YouTube/GitHub/Twitch reconstruidos sin capabilities no aparecen.
        assert "YouTube" not in result

    def test_get_ui_elements_for_capability_chrome_navigate(self):
        """get_ui_elements_for_capability('chrome', NAVIGATE) → ['address_bar']."""
        integrator = _real_integrator()
        elements = integrator.get_ui_elements_for_capability(
            "chrome", ApplicationCapability.NAVIGATE
        )
        assert elements == ["address_bar"]

    def test_get_application_ui_elements_chrome_real(self):
        """ApplicationManager.get_application_ui_elements expone los elementos UI reales
        de Chrome (consumido indirectamente por Planner.get_application_ui_requirements)."""
        manager = _real_manager()
        elems = manager.get_application_ui_elements("chrome")
        assert "address_bar" in elems
        assert "search_bar" in elems
        assert "new_tab_button" in elems

    def test_catalog_has_real_apps_beyond_hardcoded(self):
        """El modelo real carga aplicaciones reconstruidas desde entities.json."""
        manager = _real_manager()
        keys = set(manager.applications.keys())
        assert "chrome" in keys
        assert "spotify" in keys
        assert "youtube" in keys
        assert "github" in keys
        assert "twitch" in keys


# ---------------------------------------------------------------------------
# 2. Brain._get_application_knowledge() — consumidor del modelo real
# ---------------------------------------------------------------------------

class TestBrainConsumesRealCatalog:
    """Brain consume el catálogo real a través del integrador singleton."""

    @pytest.fixture(autouse=True)
    def _brain(self):
        from src.brain.llm import Brain
        self.brain = Brain(model="llama3")

    def test_returns_expected_dict_format(self):
        """El formato de salida es {applications, total_applications, supported_capabilities}."""
        result = self.brain._get_application_knowledge()
        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "applications", "total_applications", "supported_capabilities",
        }

    def test_total_applications_matches_catalog(self):
        """total_applications coincide con el número de apps del modelo real."""
        result = self.brain._get_application_knowledge()
        manager = _real_manager()
        assert result["total_applications"] == len(manager.applications)
        assert result["total_applications"] >= 2  # al menos Chrome + Spotify

    def test_chrome_entry_has_capabilities_and_availability_keys(self):
        """La entrada chrome tiene capabilities (dict), declared=True (declarada
        en el modelo) y claves de disponibilidad (available, capability_available).

        Nota: bajo el contrato 3.3.2.2, 'available' indica disponibilidad en tiempo
        de ejecución (ejecutable en PATH o URL), no simplemente si la capability
        está declarada. 'declared' refleja la capability declarada en el modelo
        (determinista: Chrome declara OPEN → True).
        """
        result = self.brain._get_application_knowledge()
        chrome = result["applications"]["chrome"]
        assert isinstance(chrome["capabilities"], dict)
        assert "open_chrome" in chrome["capabilities"]
        assert chrome["declared"] is True
        assert isinstance(chrome["available"], bool)
        assert isinstance(chrome["capability_available"], bool)
        # capability_available == declared (True) AND available (runtime)
        assert chrome["capability_available"] == (
            chrome["declared"] and chrome["available"]
        )

    def test_reconstructed_app_entry(self):
        """YouTube (reconstruido, sin capabilities) aparece con capabilities={}."""
        result = self.brain._get_application_knowledge()
        assert "youtube" in result["applications"]
        yt = result["applications"]["youtube"]
        assert yt["capabilities"] == {}
        # YouTube no declara capability OPEN → declared es determinista False.
        assert yt["declared"] is False
        # Sin capability declarada, capability_available es determinista False
        # (aunque la app pueda ser runtime-available por URL o ejecutable).
        assert yt["capability_available"] is False
        assert isinstance(yt["available"], bool)  # runtime availability (no determinista)

    def test_supported_capabilities_is_list_of_strings(self):
        """supported_capabilities es una lista de strings."""
        result = self.brain._get_application_knowledge()
        caps = result["supported_capabilities"]
        assert isinstance(caps, list)
        assert all(isinstance(c, str) for c in caps)

    def test_all_entries_have_required_keys(self):
        """Todas las entradas tienen capabilities, declared, available y capability_available."""
        result = self.brain._get_application_knowledge()
        for info in result["applications"].values():
            assert "capabilities" in info
            assert "declared" in info
            assert "available" in info
            assert "capability_available" in info
            assert isinstance(info["capabilities"], dict)
            assert isinstance(info["declared"], bool)
            assert isinstance(info["available"], bool)
            assert isinstance(info["capability_available"], bool)


# ---------------------------------------------------------------------------
# 3. Planner — consumidor del modelo real vía integrador
# ---------------------------------------------------------------------------

class TestPlannerConsumesRealCatalog:
    """Planner consume el catálogo real a través del integrador singleton."""

    @pytest.fixture(autouse=True)
    def _planner(self):
        from src.hands.planner.planner import Planner
        with patch("src.hands.planner.planner.logger"):
            self.planner = Planner()

    def test_load_application_knowledge_loads_real_nodes(self):
        """load_application_knowledge carga nodos de apps reales al catálogo del planner."""
        self.planner.load_application_knowledge()
        assert "app_chrome" in self.planner.available_nodes
        assert "app_spotify" in self.planner.available_nodes
        # Al menos un nodo de capacidad de Chrome.
        assert "chrome_open" in self.planner.available_nodes

    def test_get_applications_by_capability_open_includes_chrome(self):
        """get_applications_by_capability('open') incluye Chrome."""
        result = self.planner.get_applications_by_capability("open")
        assert "Chrome" in result

    def test_get_application_capabilities_chrome(self):
        """get_application_capabilities('chrome') devuelve open_chrome."""
        caps = self.planner.get_application_capabilities("chrome")
        assert "open_chrome" in caps
        assert caps["open_chrome"]["capability"] == "open"

    def test_get_application_capabilities_alias(self):
        """get_application_capabilities('gh') resuelve alias → GitHub → {}."""
        caps = self.planner.get_application_capabilities("gh")
        assert caps == {}

    def test_get_application_ui_requirements_chrome_navigate(self):
        """get_application_ui_requirements('chrome', 'navigate') → ['address_bar']."""
        elements = self.planner.get_application_ui_requirements("chrome", "navigate")
        assert "address_bar" in elements

    def test_get_application_ui_requirements_chrome_open_empty(self):
        """La capability 'open' de Chrome no requiere elementos UI."""
        elements = self.planner.get_application_ui_requirements("chrome", "open")
        assert elements == []


# ---------------------------------------------------------------------------
# 4. HTNManager._application_catalog_available — consumidor del modelo real
# ---------------------------------------------------------------------------

class TestHTNManagerConsumesRealCatalog:
    """HTNManager consulta disponibilidad del catálogo del integrador."""

    def test_catalog_available_with_real_integrator(self):
        """Con el integrador real y el catálogo cargado, devuelve True."""
        from src.hands.planner.htn_manager import HTNManager
        htn = HTNManager()
        assert htn._application_catalog_available() is True

    def test_catalog_available_false_when_empty(self):
        """Con applications vacío, devuelve False (compat con 3.1.3.2)."""
        from src.hands.planner.htn_manager import HTNManager
        integrator = _real_integrator()
        recording = _RecordingIntegrator(integrator)
        # Forzamos el manager a uno con catalogo vacío.
        with patch.object(
            recording, "application_manager",
            MagicMock(applications={}),
        ):
            htn = HTNManager()
            htn.application_integrator = recording
            assert htn._application_catalog_available() is False


# ---------------------------------------------------------------------------
# 5. Executor._evaluate_condition — consumidor del modelo real (catálogo)
# ---------------------------------------------------------------------------

class TestExecutorConsumesRealCatalog:
    """Executor consumir el catálogo real como fallback cuando el estado runtime está vacío."""

    @pytest.fixture
    def executor(self):
        from src.hands.executor import Executor
        with patch("src.hands.executor.logger"):
            return Executor()

    def test_browser_available_via_catalog_fallback(self, executor):
        """browser_available True vía catálogo cuando el runtime no observa apps."""
        executor.current_state.application_states = {}
        assert executor._evaluate_condition("browser_available") is True

    def test_application_available_via_catalog_fallback(self, executor):
        """application_available True vía catálogo cuando el runtime está vacío."""
        executor.current_state.application_states = {}
        assert executor._evaluate_condition("application_available") is True

    def test_browser_available_via_runtime_state(self, executor):
        """browser_available True cuando el runtime observa Chrome abierto."""
        executor.current_state.application_states = {
            "chrome": {"open": True},
        }
        assert executor._evaluate_condition("browser_available") is True

    def test_application_available_via_catalog_after_runtime_empty(self, executor):
        """application_available True vía catálogo real con manager cargado."""
        executor.current_state.application_states = {}
        assert executor._evaluate_condition("application_available") is True


# ---------------------------------------------------------------------------
# 6. Funciones internas de applications_core — consumidores del modelo real
# ---------------------------------------------------------------------------

class TestInternalFunctionsConsumeRealModel:
    """open_application, _check_application_available y _check_application_login
    consumen el modelo real resolviendo apps y aliases."""

    def test_check_available_chrome_with_executable_in_path(self):
        """_check_application_available('chrome') resuelve el ejecutable del modelo real
        vía shutil.which. Si el ejecutable está en PATH → True."""
        app = _real_manager().get_application("chrome")
        assert app.executable == "chrome"
        with patch("src.hands.applications_core.shutil.which", return_value="/usr/bin/chrome"):
            assert _check_application_available(app) is True

    def test_check_available_chrome_executable_not_in_path(self):
        """_check_application_available('chrome') False cuando el ejecutable no está en PATH."""
        app = _real_manager().get_application("chrome")
        with patch("src.hands.applications_core.shutil.which", return_value=None):
            assert _check_application_available(app) is False

    def test_check_available_url_only_fallback(self):
        """_check_application_available con app sin ejecutable pero con URL → True
        (fallback a url, consumido por open_application preflight)."""
        app = ApplicationKnowledge(
            name="UrlOnly", type="webapp", executable=None, url="https://example.com",
        )
        assert _check_application_available(app) is True

    def test_check_available_youtube_via_executable(self):
        """YouTube (reconstruido con executable='chrome.exe') se valida por ejecutable."""
        app = _real_manager().get_application("youtube")
        assert app.executable is not None
        with patch("src.hands.applications_core.shutil.which", return_value="/opt/chrome.exe"):
            assert _check_application_available(app) is True

    def test_check_login_returns_true(self):
        """_check_application_login siempre devuelve True (compat)."""
        app = _real_manager().get_application("chrome")
        assert _check_application_login(app) is True

    def test_open_application_chrome_uses_model(self):
        """open_application('chrome') resuelve desde el modelo real y lanza el ejecutable."""
        with patch("src.hands.applications_core.subprocess.Popen") as mock_popen, \
             patch(
                 "src.hands.applications_core._check_application_available",
                 return_value=True,
             ):
            mock_popen.return_value = MagicMock()
            result = open_application("chrome")
            assert "Chrome" in result
            mock_popen.assert_called_once_with(["chrome"])

    def test_open_application_alias_resolves_to_real_app(self):
        """open_application('gh') resuelve el alias a GitHub y lanza su ejecutable."""
        app = _real_manager().get_application("gh")
        executable = app.executable
        with patch("src.hands.applications_core.subprocess.Popen") as mock_popen, \
             patch(
                 "src.hands.applications_core._check_application_available",
                 return_value=True,
             ):
            mock_popen.return_value = MagicMock()
            result = open_application("gh")
            assert "GitHub" in result
            mock_popen.assert_called_once_with([executable])

    def test_open_application_not_found_raises(self):
        """open_application con app inexistente levanta ValueError."""
        with pytest.raises(ValueError, match="no encontrada"):
            open_application("nonexistent_app_xyz")

    def test_open_application_minimal_app_with_executable(self):
        """open_application con app minimal (contrato 3.1.2) y ejecutable funciona."""
        manager = ApplicationManager()
        manager.applications.clear()
        app = ApplicationKnowledge(name="MinApp", type="utility")
        app.executable = "fake_exe"
        manager.applications["minapp"] = app
        # _check_application_available: executable 'fake_exe' no existe en PATH → False,
        # pero MinApp no tiene 'application_available' en preflight_requirements,
        # así que se omite el chequeo y se lanza directamente.
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ), patch("src.hands.applications_core.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = open_application("minapp")
            assert "MinApp" in result
            mock_popen.assert_called_once_with(["fake_exe"])
