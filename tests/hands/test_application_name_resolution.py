# -*- coding: utf-8 -*-
"""Tests de resolución de nombres de aplicación (FASE 3.8, unidad 3.8.2.2).

Cubre nombres normalizados, nombres alternativos (alias dinámicos) y nombres
imperfectos (errores de escritura/variantes) procedentes de una petición ya
normalizada, sobre ApplicationManager sin modificar lógica existente.
"""

import pytest

import src.hands.applications_core as _applications_core
import src.memory.storage as _storage

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationResolutionResult,
    ApplicationState,
    RESOLUTION_FUZZY_THRESHOLD,
    UIElement,
    get_application_manager,
)


def _registrar_app(manager: ApplicationManager, name: str, aliases=None):
    """Registra una aplicación de prueba con nombre y aliases distintivos.

    Si la aplicación ya existe en el catálogo (cargada de entities.json o
    dejada por una ejecución previa), se recupera la entrada existente y se
    actualizan sus aliases para que el test sea idempotente y no dependa del
    estado previo del catálogo.
    """
    app = ApplicationKnowledge(
        name=name,
        type="test",
        executable=name.lower().replace(" ", ""),
        url=f"https://{name.lower().replace(' ', '')}.example.com",
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name=f"open_{name.lower().replace(' ', '_')}",
                description=f"Abre {name}",
                required_ui_elements=[],
                preconditions=[],
                effects=[],
                cost=1.0,
            )
        ],
        ui_elements=[
            UIElement(name="ventana_principal", type="window", description=f"Ventana de {name}")
        ],
        states=[ApplicationState.CLOSED, ApplicationState.OPEN],
        metadata={"aliases": aliases or []},
    )
    if manager.register_application(app) is True:
        return app
    # Ya existe: recuperar y actualizar aliases para el test.
    existing = manager.get_application(name)
    if existing is not None and aliases is not None:
        if existing.metadata is None:
            existing.metadata = {}
        existing.metadata["aliases"] = list(aliases)
    return existing


@pytest.fixture(autouse=True)
def _reset_singletons_compartidos():
    """Aísla cada test de los singletons globales ``ApplicationManager`` y
    ``MemoryManager`` para que los registros persistentes de pruebas previas
    (que se guardan en el gestor compartido) no contaminen esta suite.

    Esta es la contención detectada en la unidad 3.8.2.6: los tests de nombres,
    alias, errores de escritura, ambiguedad y ausencia de coincidencias deben
    verificarse juntos como suite, independientemente del orden de ejecución.
    El fixture reinicia los singletons sin debilitar ninguna aserción.
    """
    _applications_core._app_manager = None
    _storage._memory_manager = None
    yield


class TestApplicationResolutionResult:
    def test_estructura_dataclass(self):
        result = ApplicationResolutionResult(app=None, confidence=0.0, method="none", alternatives=[])
        assert result.app is None
        assert result.confidence == 0.0
        assert result.method == "none"
        assert result.alternatives == []


class TestResolveApplication:
    def setup_method(self):
        self.manager = get_application_manager()

    def test_resuelve_nombre_normalizado_exacto_chrome(self):
        result = self.manager.resolve_application("chrome")
        assert isinstance(result, ApplicationResolutionResult)
        assert result.app is not None
        assert result.app.name == "Chrome"
        assert result.confidence == 1.0
        assert result.method == "exact_normalized"
        assert result.alternatives == []

    def test_resuelve_nombre_normalizado_exacto_spotify(self):
        result = self.manager.resolve_application("spotify")
        assert result.app is not None
        assert result.app.name == "Spotify"
        assert result.confidence == 1.0
        assert result.method == "exact_normalized"

    def test_resuelve_alias_estatico_google_chrome(self):
        result = self.manager.resolve_application("google chrome")
        assert result.app is not None
        assert result.app.name == "Chrome"
        assert result.confidence == 1.0
        assert result.method == "exact_normalized"

    def test_resuelve_alias_dinámico_registrado(self):
        _registrar_app(self.manager, "App Resolucion Test", aliases=["arte", "app resolucion"])
        result = self.manager.resolve_application("arte")
        assert result.app is not None
        assert result.app.name == "App Resolucion Test"
        assert result.confidence == 1.0
        assert result.method == "dynamic_alias"

    def test_resuelve_nombre_imperfecto_typo(self):
        """'spotifiy' es una variante imperfecta de 'Spotify' (difuso sobre nombre)."""
        result = self.manager.resolve_application("spotifiy")
        assert result.app is not None
        assert result.app.name == "Spotify"
        assert result.method == "fuzzy_name"
        assert 0.7 <= result.confidence < 1.0

    def test_resuelve_nombre_imperfecto_por_alias(self):
        _registrar_app(self.manager, "Navegador Web Alternativo", aliases=["navegador web"])
        result = self.manager.resolve_application("navegador webb")  # alias con typo
        assert result.app is not None
        assert result.app.name == "Navegador Web Alternativo"
        assert result.method == "fuzzy_alias"
        assert 0.7 <= result.confidence < 1.0

    def test_nombre_desconocido_devuelve_none(self):
        result = self.manager.resolve_application("aplicacion_que_no_existe_xyz_789")
        assert result.app is None
        assert result.method == "none"
        # La confianza conserva el mejor ratio aunque esté bajo el umbral:
        # es evidencia de proximidad, no una resolución.
        assert result.confidence < RESOLUTION_FUZZY_THRESHOLD
        assert result.alternatives == []

    def test_cadena_vacia_devuelve_none(self):
        result = self.manager.resolve_application("")
        assert result.app is None
        assert result.confidence == 0.0
        assert result.method == "none"

    def test_espacios_en_blanco_devuelve_none(self):
        result = self.manager.resolve_application("   ")
        assert result.app is None
        assert result.method == "none"

    def _mejores_ratios(self, consulta: str):
        import difflib

        ratios = {}
        for app in self.manager.applications.values():
            r = difflib.SequenceMatcher(None, consulta, app.name.lower()).ratio()
            if app.metadata and isinstance(app.metadata, dict):
                for alias in app.metadata.get("aliases") or []:
                    r = max(
                        r,
                        difflib.SequenceMatcher(None, consulta, str(alias).lower()).ratio(),
                    )
            ratios[app.name] = r
        return ratios

    def test_alternativas_ordenadas_y_ganador_max_similitud(self):
        _registrar_app(self.manager, "Editor de Texto Pro", aliases=["editor texto"])
        _registrar_app(self.manager, "Calculadora Científica", aliases=["calculo"])
        consulta = "editor de texto"
        result = self.manager.resolve_application(consulta)
        assert result.app is not None
        ratios = self._mejores_ratios(consulta)
        if result.method in ("exact_normalized", "dynamic_alias"):
            assert result.confidence == 1.0
            assert result.alternatives == []
        else:
            assert result.method in ("fuzzy_name", "fuzzy_alias")
            assert RESOLUTION_FUZZY_THRESHOLD <= result.confidence < 1.0
            assert ratios[result.app.name] == max(ratios.values())
            assert result.confidence == pytest.approx(ratios[result.app.name])
            nombres_alt = [a.name for a in result.alternatives]
            assert result.app.name not in nombres_alt
            assert len(nombres_alt) <= 3
            assert nombres_alt == sorted(
                nombres_alt, key=lambda n: ratios[n], reverse=True
            )

    def test_no_devuelve_alternativas_cuando_resolucion_exacta(self):
        result = self.manager.resolve_application("chrome")
        assert result.alternatives == []


class TestCompatibilidadGetApplication:
    def test_get_application_sigue_resolviendo_exactos(self):
        manager = get_application_manager()
        app = manager.get_application("chrome")
        assert app is not None
        assert app.name == "Chrome"
