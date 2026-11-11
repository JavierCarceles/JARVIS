# -*- coding: utf-8 -*-
"""Tests de evidencia/confianza de resolución de aplicación (FASE 3.8, unidad 3.8.2.3).

Calcula y conserva evidencia/confianza de la coincidencia de resolución
usando mecanismos existentes (metadata de ApplicationKnowledge) sin crear
mecanismos nuevos ni APIs ficticias.
"""

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationResolutionResult,
    ApplicationState,
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


class TestCalculateResolutionEvidence:
    def setup_method(self):
        self.manager = get_application_manager()

    def test_evidencia_resolucion_exacta_sin_alternativas(self):
        """Resolución exacta (chrome) debe dar evidence_score 1.0."""
        evidence = self.manager.calculate_resolution_evidence("chrome")
        assert evidence["has_match"] is True
        assert evidence["app_name_resolved"] == "Chrome"
        assert evidence["confidence"] == 1.0
        assert evidence["method"] == "exact_normalized"
        assert evidence["evidence_score"] == 1.0
        assert evidence["alternatives_count"] == 0

    def test_evidencia_resolucion_alias_estatico(self):
        """Alias estático (google chrome) debe dar evidence_score 1.0."""
        evidence = self.manager.calculate_resolution_evidence("google chrome")
        assert evidence["has_match"] is True
        assert evidence["confidence"] == 1.0
        assert evidence["method"] == "exact_normalized"
        assert evidence["evidence_score"] == 1.0

    def test_evidencia_resolucion_difusa_con_alternativas(self):
        """Resolución difusa con typo puntúa menor que 1.0 y tiene alternativas."""
        evidence = self.manager.calculate_resolution_evidence("spotifiy")
        assert evidence["has_match"] is True
        assert evidence["app_name_resolved"] == "Spotify"
        assert evidence["method"] == "fuzzy_name"
        assert 0.7 <= evidence["confidence"] < 1.0
        # Difuso con peso 0.8 y posible penalización por alternativas -> < 1.0
        assert evidence["evidence_score"] < 1.0
        assert evidence["evidence_score"] > 0.0

    def test_evidencia_sin_coincidencia(self):
        """Nombre desconocido debe devolver has_match False y evidence_score 0.0."""
        evidence = self.manager.calculate_resolution_evidence("aplicacion_que_no_existe_xyz_789")
        assert evidence["has_match"] is False
        assert evidence["app_name_resolved"] is None
        assert evidence["confidence"] < 0.7
        assert evidence["method"] == "none"
        assert evidence["evidence_score"] == 0.0
        assert evidence["alternatives_count"] == 0

    def test_evidencia_cadena_vacia(self):
        """Cadena vacía no debe coincidir."""
        evidence = self.manager.calculate_resolution_evidence("")
        assert evidence["has_match"] is False
        assert evidence["evidence_score"] == 0.0

    def test_evidencia_conservada_en_metadata(self):
        """La evidencia debe conservarse en metadata de la aplicación resuelta."""
        self.manager.calculate_resolution_evidence("chrome")
        app = self.manager.get_application("chrome")
        assert app is not None
        ev = app.metadata.get("resolution_evidence")
        assert ev is not None
        assert ev["confidence"] == 1.0
        assert ev["method"] == "exact_normalized"
        assert ev["evidence_score"] == 1.0

    def test_evidencia_difusa_conservada_en_metadata(self):
        """La evidencia de resolución difusa también se conserva."""
        self.manager.calculate_resolution_evidence("spotifiy")
        app = self.manager.get_application("spotify")
        assert app is not None
        ev = app.metadata.get("resolution_evidence")
        assert ev is not None
        assert ev["method"] == "fuzzy_name"
        assert 0.7 <= ev["confidence"] < 1.0
        assert ev["evidence_score"] < 1.0

    def test_evidencia_alias_dinamico_conservada(self):
        """La evidencia de alias dinámico se conserva."""
        _registrar_app(self.manager, "App Evidencia Test", aliases=["evidencia app"])
        self.manager.calculate_resolution_evidence("evidencia app")
        app = self.manager.get_application("App Evidencia Test")
        assert app is not None
        ev = app.metadata.get("resolution_evidence")
        assert ev is not None
        assert ev["method"] == "dynamic_alias"
        assert ev["confidence"] == 1.0
        assert ev["evidence_score"] == 1.0


class TestGetStoredResolutionEvidence:
    def setup_method(self):
        self.manager = get_application_manager()

    def test_recupera_evidencia_guardada(self):
        """Se puede recuperar la evidencia guardada por nombre de aplicación."""
        self.manager.calculate_resolution_evidence("chrome")
        ev = self.manager.get_stored_resolution_evidence("chrome")
        assert ev is not None
        assert ev["confidence"] == 1.0
        assert ev["method"] == "exact_normalized"
        assert ev["evidence_score"] == 1.0

    def test_no_hay_evidencia_si_no_se_calculo(self):
        """Si no se calculó evidencia, devuelve None (app nunca resuelta)."""
        ev = self.manager.get_stored_resolution_evidence("edge")
        assert ev is None

    def test_nombre_desconocido_no_guarda_evidencia(self):
        """Un nombre desconocido no guarda evidencia recuperable."""
        self.manager.calculate_resolution_evidence("no_existe_xyz")
        ev = self.manager.get_stored_resolution_evidence("no_existe_xyz")
        assert ev is None

    def test_evidencia_sobreescrita_en_calculo_posterior(self):
        """Un nuevo cálculo sobrescribe la evidencia previa."""
        self.manager.calculate_resolution_evidence("chrome")
        ev1 = self.manager.get_stored_resolution_evidence("chrome")
        assert ev1["evidence_score"] == 1.0
        # Volver a calcular (misma app, mismo resultado)
        self.manager.calculate_resolution_evidence("chrome")
        ev2 = self.manager.get_stored_resolution_evidence("chrome")
        assert ev2 is not None
        assert ev2["evidence_score"] == 1.0

    def test_cadena_vacia_devuelve_none(self):
        """Cadena vacía no debe recuperar evidencia."""
        ev = self.manager.get_stored_resolution_evidence("")
        assert ev is None


class TestCompatibilidadResolveApplication:
    def setup_method(self):
        self.manager = get_application_manager()

    def test_resolve_application_sigue_funcionando(self):
        """resolve_application sigue devolviendo ApplicationResolutionResult sin cambios."""
        result = self.manager.resolve_application("chrome")
        assert isinstance(result, ApplicationResolutionResult)
        assert result.app is not None
        assert result.confidence == 1.0
        assert result.method == "exact_normalized"
