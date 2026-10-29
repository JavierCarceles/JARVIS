# -*- coding: utf-8 -*-
"""Tests de verificación de capacidades ausentes.

Unidad 3.3.2.3: "Verificar capacidades ausentes."

Complementa la matriz de estados de capacidad del contrato (fase 3.3.2):

- 3.3.2.1: la query canónica de capacities (capacidad presente en el modelo).
- 3.3.2.2: distinción ``declared`` (declarada en el modelo) vs ``available``
  (disponible en tiempo de ejecución).
- 3.3.2.3: ``absent`` (ausente). Una capacidad está ausente cuando:

  (a) el nombre definido en una fuente de datos (``data/knowledge/*.json``)
      no corresponde a ningún miembro del ``Enum`` canónico
      ``ApplicationCapability`` — "capacidad ausente del modelo";
  (b) la aplicación existe en el catálogo pero no declara la capacidad —
      "capacidad ausente para la app".

El contrato canónico resuelve ambos casos de forma determinista: los nombres
ausentes del ``Enum`` no se mapean a ningún miembro (se omiten al reconstruir) y
``is_capable``/``get_applications_by_capability`` devuelven ``False``/``[]``;
una app cuyas ``capabilities`` son ausentes (``[]``) se distingue de una app
desconocida (``get_application_knowledge`` devuelve ``{}``).

Aislamiento: las aserciones EXACTAS (qué apps aparecen en una query) se hacen
sobre managers/controladores CONTROLADOS (``_make_minimal_manager``) para que
no dependan del estado global del singleton real, que otros tests de
``tests/hands/`` mutan registrando apps personalizadas en memoria. Las apps del
singleton real (Chrome/Spotify/YouTube) se usan solo para invariantes robustas
(presencia/ausencia), verificadas contra la evidencia de 3.3.1.2
(``TOTAL_APPS=32``; ``chrome``/``spotify`` declaran capabilities; las 30 apps
reconstruidas carecen de la clave ``capabilities``).
"""

import json

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    get_application_knowledge,
    get_application_manager,
    get_applications_by_capability,
    is_application_available,
    is_capability_available,
)
from src.hands.planner.application_integration import (
    ApplicationKnowledgeIntegrator,
    get_application_knowledge_integrator,
)
from src.utils.config import get_project_root

APPS_JSON_PATH = get_project_root() / "data" / "knowledge" / "applications.json"


# ---------------------------------------------------------------------------
# HELPERS (controlados; no dependen del singleton real)
# ---------------------------------------------------------------------------

def _make_minimal_manager():
    """ApplicationManager sin __init__ (evita registrar Chrome/Spotify; aísla del
    singleton real que otros tests pueden haber enriquecido con apps custom)."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _FakeMemoryManager:
        def __init__(self):
            self.saved = []

        def save_entity(self, entity):
            self.saved.append(entity)

        def get_entities_by_type(self, _type):
            return []

    manager.memory_manager = _FakeMemoryManager()
    return manager


def _make_integrator_with_manager(manager):
    integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
    integrator.application_manager = manager
    integrator.memory_manager = None
    return integrator


def _make_cap(capability: ApplicationCapability = ApplicationCapability.OPEN,
              name="open_app") -> ApplicationCapabilityDef:
    return ApplicationCapabilityDef(
        capability=capability,
        name=name,
        description="d",
        required_ui_elements=[],
        preconditions=[],
        effects=[],
        cost=1.0,
    )


def _app(name="Chrome", app_type="browser", executable=None, url=None,
         capabilities=None, **overrides) -> ApplicationKnowledge:
    defaults = dict(
        name=name,
        type=app_type,
        executable=executable,
        url=url,
        capabilities=capabilities or [],
        ui_elements=[],
        states=[],
    )
    defaults.update(overrides)
    return ApplicationKnowledge(**defaults)


def _enum_member_values():
    return {member.value for member in ApplicationCapability}


def _data_capability_strings():
    """Capacidades declaradas como strings en data/knowledge/applications.json."""
    data = json.loads(APPS_JSON_PATH.read_text())
    strings = []
    for app_caps in data.values():
        strings.extend(app_caps.get("capabilities", []) or [])
    return [s for s in strings if isinstance(s, str)]


# ---------------------------------------------------------------------------
# 1. Capacidades ausentes del Enum canónico (definidas en data pero no modeladas)
# ---------------------------------------------------------------------------

class TestEnumCapabilityAbsence:
    """Capacidades declaradas en data/knowledge pero ausentes del Enum."""

    def test_applications_json_exists(self):
        assert APPS_JSON_PATH.exists()

    def test_some_data_capabilities_are_absent_from_enum(self):
        """El gap D-CAP-MODEL-GAP: data define capacidades que el Enum no modela."""
        members = _enum_member_values()
        absent = {s for s in _data_capability_strings() if s.lower() not in members}
        assert absent, "No se detectaron capacidades ausentes del Enum (gap inesperado)"
        for known_absent in ("back", "forward", "zoom_in", "play", "pause",
                             "open_file", "start_stream", "like_song"):
            assert known_absent in absent, f"{known_absent} debería ser ausente del Enum"

    def test_some_data_capabilities_present_in_enum(self):
        members = _enum_member_values()
        for present in ("open", "navigate", "new_tab", "close_tab", "refresh", "search"):
            assert present in members, f"{present} debería estar en el Enum"

    def test_absent_capability_raises_value_error(self):
        """Un nombre ausente del Enum no se resuelve a ningún miembro (no se falsea)."""
        for absent_name in ("back", "zoom_in", "play", "open_file", "change_scene"):
            with pytest.raises(ValueError):
                ApplicationCapability(absent_name)

    def test_reconstruct_capabilities_omits_unknown_strings(self):
        """_reconstruct_capabilities descarta silenciosamente los strings ausentes
        del Enum (no los mapea a miembros erróneos)."""
        result = ApplicationManager._reconstruct_capabilities(["back", "forward", "zoom_in"])
        assert result == []

        # Los strings válidos se conservan; los ausentes se omiten sin reordenar.
        result = ApplicationManager._reconstruct_capabilities(["open", "back", "navigate", "play"])
        values = [cap.capability.value for cap in result]
        assert values == ["open", "navigate"]
        assert "back" not in values
        assert "play" not in values

    def test_chrome_data_declared_absent_capabilities(self):
        """Chrome declara (en data) capacidades ausentes del Enum."""
        data = json.loads(APPS_JSON_PATH.read_text())
        members = _enum_member_values()
        chrome_caps = data["chrome"]["capabilities"]
        absent = [c for c in chrome_caps if c.lower() not in members]
        assert set(absent) == {"back", "forward", "zoom_in", "zoom_out", "zoom_reset"}

    def test_spotify_data_declared_absent_capabilities(self):
        data = json.loads(APPS_JSON_PATH.read_text())
        members = _enum_member_values()
        spotify_caps = data["spotify"]["capabilities"]
        absent = [c for c in spotify_caps if c.lower() not in members]
        assert {"play", "pause", "like_song", "create_playlist"}.issubset(set(absent))


# ---------------------------------------------------------------------------
# 2. Modelo: ApplicationKnowledge con capacidades ausentes (controlado)
# ---------------------------------------------------------------------------

class TestModelAbsentCapabilities:
    """Una ApplicationKnowledge sin capabilities declaradas: todo ausente."""

    def test_app_with_no_capabilities_is_not_capable(self):
        app = _app("NoCapApp", executable="python", capabilities=[])
        assert app.capabilities == []
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.get_capability("open") is None
        assert app.is_capability_available(ApplicationCapability.OPEN) is False

    def test_app_with_partial_capabilities_lacks_others(self):
        """NAVIGATE declarada → True; OPEN ausente para esta app → False."""
        app = _app("PartialApp", executable="python",
                   capabilities=[_make_cap(capability=ApplicationCapability.NAVIGATE)])
        assert app.is_capable(ApplicationCapability.NAVIGATE) is True
        # OPEN está ausente para esta app concreta (aunque exista en el Enum).
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.is_capability_available(ApplicationCapability.OPEN) is False

    def test_absent_capability_does_not_match_get_capability(self):
        app = _app("NoCapApp", executable="python", capabilities=[])
        assert app.get_capability("navigate") is None
        assert app.get_capability("zoom") is None

    def test_available_app_without_capabilities(self):
        """App disponible pero con capabilities ausentes."""
        app = _app("AvailNoCap", executable="python", capabilities=[])
        assert app.is_available() is True
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.is_capability_available(ApplicationCapability.OPEN) is False


# ---------------------------------------------------------------------------
# 3. Apps reconstruidas: capabilities ausentes (singleton real, invariantes robustas)
# ---------------------------------------------------------------------------

class TestReconstructedAppAbsentCapabilities:
    """Las apps reconstruidas desde entities.json carecen de capabilities."""

    def setup_method(self):
        self.manager = get_application_manager()

    def test_reconstructed_apps_have_absent_capabilities(self):
        """Apps del catálogo que no declaran capabilities (reconstruidas)."""
        for name in ("YouTube", "GitHub", "Twitch"):
            app = self.manager.get_application(name)
            assert app is not None, f"{name} debería estar en el catálogo"
            assert app.capabilities == [], f"{name} debería carecer de capabilities"

    def test_youtube_has_no_capabilities(self):
        app = self.manager.get_application("YouTube")
        assert app is not None
        assert app.capabilities == []                       # capabilities ausentes
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.get_capability("open") is None

    def test_youtube_resolves_by_alias(self):
        assert self.manager.get_application("yt") is not None

    def test_reconstructed_app_capabilities_empty(self):
        assert self.manager.get_application_capabilities("YouTube") == {}
        assert self.manager.is_capability_available("YouTube", ApplicationCapability.OPEN) is False

    def test_hardcoded_apps_declare_capabilities(self):
        """Chrome y Spotify (hardcodeados) declaran capabilities; el resto no."""
        assert self.manager.get_application("Chrome").is_capable(ApplicationCapability.OPEN) is True
        assert self.manager.get_application("Spotify").is_capable(ApplicationCapability.OPEN) is True

    def test_open_query_includes_declaring_apps_excludes_absent(self):
        """Invariante robusta: Chrome/Spotify aparecen en OPEN; YouTube no."""
        names = [app.name for app in
                 self.manager.get_applications_by_capability(ApplicationCapability.OPEN)]
        assert "Chrome" in names and "Spotify" in names
        # YouTube carece de capabilities → no aparece en ninguna query.
        assert "YouTube" not in names


# ---------------------------------------------------------------------------
# 4. Distinción: app conocida (capabilities ausentes) vs app desconocida
# ---------------------------------------------------------------------------

class TestKnownAppAbsentVsUnknownApp:
    """Una app conocida con capabilities ausentes NO se confunde con una app
    desconocida."""

    def test_known_app_with_absent_capabilities(self):
        knowledge = get_application_knowledge("YouTube")
        assert knowledge != {}                                    # app conocida
        assert knowledge["declared_capabilities"] == []           # capabilities ausentes
        assert knowledge["capabilities"] == {}                    # capabilities vacías
        assert isinstance(knowledge["available"], bool)

    def test_unknown_app_returns_empty(self):
        assert get_application_knowledge("nonexistent_app_xyz_12345") == {}

    def test_known_absent_distinct_from_unknown(self):
        known = get_application_knowledge("YouTube")
        unknown = get_application_knowledge("nonexistent_app_xyz_12345")
        # La app conocida (aunque sin capabilities) devuelve metadata; la
        # desconocida devuelve {}: no se confunden.
        assert known != {}
        assert known != unknown
        assert "declared_capabilities" in known
        assert "declared_capabilities" not in unknown


# ---------------------------------------------------------------------------
# 5. Consulta inversa: invariantes EXACTAS sobre manager controlado
# ---------------------------------------------------------------------------

class TestInverseQueryExcludesAbsent:
    """get_applications_by_capability devuelve solo apps que declaran la
    capacidad. Las invariantes exactas se verifican sobre un manager aislado
    (no sobre el singleton real, que otros tests enriquecen)."""

    def setup_method(self):
        self.manager = _make_minimal_manager()

    def test_only_declaring_apps_returned(self):
        self.manager.applications["onlyopen"] = _app(
            "OnlyOpen", capabilities=[_make_cap(ApplicationCapability.OPEN)]
        )
        names = [app.name for app in
                 self.manager.get_applications_by_capability(ApplicationCapability.OPEN)]
        assert names == ["OnlyOpen"]

    def test_app_without_capability_not_listed(self):
        self.manager.applications["searchonly"] = _app(
            "SearchOnly", capabilities=[_make_cap(ApplicationCapability.SEARCH)]
        )
        names = [app.name for app in
                 self.manager.get_applications_by_capability(ApplicationCapability.OPEN)]
        assert names == []

    def test_absent_capability_returns_empty(self):
        # CLOSE no declarada por ninguna app del manager vacío.
        assert self.manager.get_applications_by_capability(ApplicationCapability.CLOSE) == []

    def test_absent_from_enum_string_does_not_raise(self):
        # Un string ausente del Enum no eleva y no devuelve apps.
        assert self.manager.get_applications_by_capability("back") == []
        assert self.manager.get_applications_by_capability("zoom_reset") == []


# ---------------------------------------------------------------------------
# 6. Funciones módulo: capacidades ausentes (strings ausentes del Enum)
# ---------------------------------------------------------------------------

class TestModuleLevelAbsentCapability:
    """Las funciones módulo-level resuelven capacidades ausentes del Enum."""

    def test_absent_enum_capability_string_returns_empty(self):
        # "back", "zoom_in", "play" no son miembros del Enum → no hay apps.
        assert get_applications_by_capability("back") == []
        assert get_applications_by_capability("zoom_in") == []
        assert get_applications_by_capability("play") == []
        assert get_applications_by_capability("start_stream") == []

    def test_present_enum_capability_string_returns_apps(self):
        result = get_applications_by_capability("navigate")
        assert isinstance(result, list)
        assert "Chrome" in result

    def test_is_capability_available_absent_for_absent_app(self):
        # YouTube carece de capabilities → capability_available es False.
        assert is_capability_available("YouTube", ApplicationCapability.OPEN) is False
        assert is_capability_available("YouTube", "open") is False

    def test_unknown_app_is_not_capable_nor_available(self):
        assert is_capability_available("nonexistent_app_xyz_12345", ApplicationCapability.OPEN) is False
        assert is_application_available("nonexistent_app_xyz_12345") is False

    def test_absent_enum_string_does_not_raise(self):
        # Una capability string ausente del Enum no eleva excepción en la query.
        assert get_applications_by_capability("change_scene") == []
        assert get_applications_by_capability("zoom_reset") == []


# ---------------------------------------------------------------------------
# 7. Integrador: capabilities ausentes (controlado + singleton real robusto)
# ---------------------------------------------------------------------------

class TestIntegratorAbsentCapability:
    """El integrador verifica capabilities ausentes de forma consistente."""

    def setup_method(self):
        self.manager = _make_minimal_manager()
        self.integrator = _make_integrator_with_manager(self.manager)

    def test_absent_capability_not_capable_on_known_app(self):
        app = _app("KnownNoCap", executable="python", capabilities=[])
        self.manager.applications["knownnocap"] = app
        assert self.integrator.is_application_capable("knownnocap", ApplicationCapability.OPEN) is False
        assert self.integrator.is_capability_available("knownnocap", ApplicationCapability.OPEN) is False
        assert self.integrator.get_application_capabilities("knownnocap") == {}

    def test_known_app_with_partial_capabilities(self):
        app = _app("Partial", executable="python",
                   capabilities=[_make_cap(ApplicationCapability.SEARCH)])
        self.manager.applications["partial"] = app
        assert self.integrator.is_application_capable("partial", ApplicationCapability.SEARCH) is True
        assert self.integrator.is_application_capable("partial", ApplicationCapability.OPEN) is False
        assert self.integrator.is_capability_available("partial", ApplicationCapability.OPEN) is False

    def test_unknown_app_is_not_capable(self):
        assert self.integrator.is_application_capable("nonexistent", ApplicationCapability.OPEN) is False
        assert self.integrator.is_capability_available("nonexistent", ApplicationCapability.OPEN) is False
        assert self.integrator.get_application_capabilities("nonexistent") == {}

    def test_inverse_query_excludes_absent_enum(self):
        # "back" ausente del Enum → el integrador no devuelve apps.
        assert self.integrator.get_applications_by_capability("back") == []
        assert self.integrator.get_applications_by_capability("zoom_in") == []

    def test_inverse_query_returns_only_declaring_apps(self):
        self.manager.applications["openapp"] = _app(
            "OpenApp", capabilities=[_make_cap(ApplicationCapability.OPEN)]
        )
        result = self.integrator.get_applications_by_capability(ApplicationCapability.OPEN)
        assert result == ["OpenApp"]

    def test_real_singleton_youtube_absent(self):
        integrator = get_application_knowledge_integrator()
        assert integrator.is_application_capable("YouTube", ApplicationCapability.OPEN) is False
        assert integrator.is_capability_available("YouTube", ApplicationCapability.OPEN) is False
        assert integrator.get_application_capabilities("YouTube") == {}
        # apps con capabilities ausentes no aparecen en la query inversa.
        assert "YouTube" not in integrator.get_applications_by_capability(ApplicationCapability.OPEN)
