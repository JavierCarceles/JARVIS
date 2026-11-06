# -*- coding: utf-8 -*-
"""Tests de detección de coincidencias ambiguas (FASE 3.8, unidad 3.8.2.4).

Verifica que ``resolve_application`` marca ``is_ambiguous=True`` cuando existe
otra candidata dentro del umbral de proximidad del mejor resultado difuso, de
modo que no se seleccione silenciosamente una aplicación posiblemente
incorrecta, y que ``calculate_resolution_evidence`` propague la ambigüedad.

Las aplicaciones de prueba se registran de forma idempotente: si ya existen
(en el gestor compartido o persistido) se reutilizan, ya que los tests de esta
clase comparten la instancia singleton de ``ApplicationManager``.
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
    RESOLUTION_AMBIGUITY_GAP,
    RESOLUTION_FUZZY_THRESHOLD,
    UIElement,
    get_application_manager,
)


def _registrar_app(manager: ApplicationManager, name: str, aliases=None):
    """Registra una aplicación de prueba (idempotente).

    Devuelve la aplicación ya registrada, ya sea la recién creada o la
    previamente existente (el gestor omite duplicados por nombre normalizado).
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
    manager.register_application(app)
    registrada = manager.get_application(name)
    assert registrada is not None
    return registrada


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


class TestResolveApplicationAmbiguity:
    def setup_method(self):
        self.manager = get_application_manager()

    def test_estructura_dataclass_con_campos_ambiguedad(self):
        result = ApplicationResolutionResult(
            app=None, confidence=0.0, method="none", alternatives=[]
        )
        assert result.is_ambiguous is False
        assert result.ambiguity_reason is None

    def test_resolucion_exacta_no_es_ambigua(self):
        result = self.manager.resolve_application("chrome")
        assert result.app is not None
        assert result.app.name == "Chrome"
        assert result.confidence == 1.0
        assert result.method == "exact_normalized"
        assert result.is_ambiguous is False
        assert result.ambiguity_reason is None

    def test_alias_dinamico_no_es_ambiguo(self):
        _registrar_app(self.manager, "App Prueba Ambiguedad", aliases=["prueba ambigua"])
        result = self.manager.resolve_application("prueba ambigua")
        assert result.app is not None
        assert result.app.name == "App Prueba Ambiguedad"
        assert result.method == "dynamic_alias"
        assert result.confidence == 1.0
        assert result.is_ambiguous is False
        assert result.ambiguity_reason is None

    def test_difusa_con_ganador_claro_no_es_ambigua(self):
        """'spotifiy' gana claramente sobre el resto: no es ambigua."""
        result = self.manager.resolve_application("spotifiy")
        assert result.app is not None
        assert result.app.name == "Spotify"
        assert result.method == "fuzzy_name"
        assert RESOLUTION_FUZZY_THRESHOLD <= result.confidence < 1.0
        assert result.is_ambiguous is False
        assert result.ambiguity_reason is None

    def test_difusa_con_coincidencia_cercana_es_ambigua(self):
        """Dos nombres muy cercanos ('... Pro' y '... Lite') generan ambigüedad."""
        _registrar_app(self.manager, "Navegador Web Pro")
        _registrar_app(self.manager, "Navegador Web Lite")
        result = self.manager.resolve_application("navegador web")
        assert result.app is not None
        assert result.method in ("fuzzy_name", "fuzzy_alias")
        assert RESOLUTION_FUZZY_THRESHOLD <= result.confidence < 1.0
        assert result.is_ambiguous is True
        assert result.ambiguity_reason is not None
        assert "ambigua" in result.ambiguity_reason
        # Ambas aplicaciones candidatas deben aparecer entre la ganadora y las alternativas.
        nombres = {result.app.name} | {a.name for a in result.alternatives}
        assert "Navegador Web Pro" in nombres
        assert "Navegador Web Lite" in nombres

    def test_nombre_desconocido_no_es_ambiguo(self):
        result = self.manager.resolve_application("aplicacion_que_no_existe_xyz_789")
        assert result.app is None
        assert result.method == "none"
        assert result.is_ambiguous is False
        assert result.ambiguity_reason is None

    def test_cadena_vacia_no_es_ambigua(self):
        result = self.manager.resolve_application("")
        assert result.app is None
        assert result.is_ambiguous is False

    def test_calcular_evidencia_propaga_ambiguedad(self):
        _registrar_app(self.manager, "Navegador Web Pro")
        _registrar_app(self.manager, "Navegador Web Lite")
        evidence = self.manager.calculate_resolution_evidence("navegador web")
        assert evidence["has_match"] is True
        assert evidence["is_ambiguous"] is True
        assert evidence["ambiguity_reason"] is not None
        assert "ambigua" in evidence["ambiguity_reason"]

    def test_calcular_evidencia_exacta_no_es_ambigua(self):
        evidence = self.manager.calculate_resolution_evidence("chrome")
        assert evidence["has_match"] is True
        assert evidence["is_ambiguous"] is False
        assert evidence["ambiguity_reason"] is None

    def test_ambiguidad_conservada_en_metadata(self):
        _registrar_app(self.manager, "Navegador Web Pro")
        _registrar_app(self.manager, "Navegador Web Lite")
        self.manager.calculate_resolution_evidence("navegador web")
        app = self.manager.get_application("Navegador Web Pro")
        if app is None:
            app = self.manager.get_application("Navegador Web Lite")
        assert app is not None
        ev = app.metadata.get("resolution_evidence")
        assert ev is not None
        assert ev["is_ambiguous"] is True
        assert ev["ambiguity_reason"] is not None
