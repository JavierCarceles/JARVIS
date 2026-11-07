# -*- coding: utf-8 -*-
"""Separacion de hechos observados, datos inferidos y capacidades no verificadas (unidad 3.8.4.3).

Objetivo verificable: exponer como API consultable la separacion conceptual
ya implementada en `register_discovered_application` (3.8.4.1):
- hechos observados (datos reales del descubrimiento),
- datos inferidos (deducciones no verificadas),
- capacidades declaradas pero no verificadas en tiempo de ejecucion.

Reutiliza contratos reales:
- ApplicationKnowledge.get_observed_facts / get_inferred_data /
  get_unverified_capabilities.
- ApplicationManager.get_application_observed_facts /
  get_application_inferred_data / get_application_unverified_capabilities.
- ApplicationKnowledge.is_capable / is_capability_available / is_available.

No modifica codigo de produccion ni entities.json. Todos los tests trabajan
sobre ApplicationManager sin __init__ (sin cargar entidades de produccion) y
con un memory manager falsificado.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
)


class _FakeMemoryManager:
    """Memory manager simulado que registra si se llamo a save_entity."""

    def __init__(self) -> None:
        self.saved_entities: list = []

    def save_entity(self, entity: Any) -> None:
        self.saved_entities.append(entity)

    def get_entities_by_type(self, _type: str) -> list:
        return []


def _make_manager() -> ApplicationManager:
    """Crea ApplicationManager sin __init__ y con memory manager falsificado."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = _FakeMemoryManager()
    return manager


def _capability(
    capability: ApplicationCapability,
    name: str,
    description: str = "",
) -> ApplicationCapabilityDef:
    return ApplicationCapabilityDef(
        capability=capability,
        name=name,
        description=description,
        required_ui_elements=[],
        preconditions=[],
        effects=[f"{name}_done"],
        cost=5.0,
    )


class TestApplicationKnowledgeObservedFacts:
    """get_observed_facts expone los hechos observados almacenados en metadata."""

    def test_devuelve_hechos_observados_almacenados(self):
        manager = _make_manager()
        hechos = {
            "executable_path": r"C:\AppDesc\app.exe",
            "ventana": "AppDesc",
            "pid": 4242,
        }
        app = manager.register_discovered_application(
            name="AppDesc", type="utility", observed_facts=hechos,
        )
        assert app.get_observed_facts() == hechos

    def test_devuelve_dict_vacio_sin_metadata(self):
        manager = _make_manager()
        app = ApplicationKnowledge(name="SinMeta", type="application")
        assert app.get_observed_facts() == {}

    def test_devuelve_dict_vacio_sin_observed_facts(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="SinHechos", type="application",
            inferred_data={"tipo": "supuesto"},
        )
        assert app.get_observed_facts() == {}

    def test_devuelve_copia_no_la_referencia_interna(self):
        manager = _make_manager()
        hechos = {"exe": r"C:\X\a.exe"}
        app = manager.register_discovered_application(
            name="Copia", type="utility", observed_facts=hechos,
        )
        resultado = app.get_observed_facts()
        resultado["clave_nueva"] = "valor"
        assert app.get_observed_facts() == hechos


class TestApplicationKnowledgeInferredData:
    """get_inferred_data expone los datos inferidos almacenados en metadata."""

    def test_devuelve_datos_inferidos_almacenados(self):
        manager = _make_manager()
        inferido = {
            "tipo_por_extension": "utilidad_supuesta",
            "confianza": 0.6,
            "origen": "nombre_de_archivo",
        }
        app = manager.register_discovered_application(
            name="AppDesc", type="application", inferred_data=inferido,
        )
        assert app.get_inferred_data() == inferido

    def test_devuelve_dict_vacio_sin_metadata(self):
        manager = _make_manager()
        app = ApplicationKnowledge(name="SinMeta", type="application")
        assert app.get_inferred_data() == {}

    def test_devuelve_dict_vacio_sin_inferred_data(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="SinInferido", type="application",
            observed_facts={"exe": r"C:\X\a.exe"},
        )
        assert app.get_inferred_data() == {}

    def test_devuelve_copia_no_la_referencia_interna(self):
        manager = _make_manager()
        inferido = {"tipo": "supuesto"}
        app = manager.register_discovered_application(
            name="CopiaInf", type="application", inferred_data=inferido,
        )
        resultado = app.get_inferred_data()
        resultado["clave_nueva"] = "valor"
        assert app.get_inferred_data() == inferido


class TestApplicationKnowledgeUnverifiedCapabilities:
    """get_unverified_capabilities expone capacidades declaradas pero no verificadas en runtime."""

    def test_capacidad_declarada_sin_exe_es_no_verificada(self):
        manager = _make_manager()
        cap = _capability(ApplicationCapability.OPEN, "open_appdesc", "Abre AppDesc")
        app = manager.register_discovered_application(
            name="AppDesc", type="utility",
            capabilities=[cap],
            observed_facts={},  # sin executable valido -> no disponible en runtime
        )
        # Declarada: True
        assert app.is_capable(ApplicationCapability.OPEN) is True
        # No disponible en runtime (sin exe resoluble): False
        assert app.is_capability_available(ApplicationCapability.OPEN) is False
        # No verificada: aparece en get_unverified_capabilities
        no_verificadas = app.get_unverified_capabilities()
        assert len(no_verificadas) == 1
        assert no_verificadas[0].capability == ApplicationCapability.OPEN

    def test_capacidad_declarada_con_exe_es_verificada(self):
        manager = _make_manager()
        cap = _capability(ApplicationCapability.OPEN, "open_notepad", "Abre bloc de notas")
        app = manager.register_discovered_application(
            name="Notepad", type="utility",
            executable=r"C:\Windows\notepad.exe",
            capabilities=[cap],
        )
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_capability_available(ApplicationCapability.OPEN) is True
        no_verificadas = app.get_unverified_capabilities()
        assert no_verificadas == []

    def test_sin_capacidades_devuelve_lista_vacia(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="SinCaps", type="utility",
            observed_facts={"exe": r"C:\X\a.exe"},
        )
        assert app.get_unverified_capabilities() == []

    def test_mezcla_capacidades_verificadas_y_no_verificadas(self):
        manager = _make_manager()
        cap_abrir = _capability(ApplicationCapability.OPEN, "open_app", "Abre app")
        cap_buscar = _capability(ApplicationCapability.SEARCH, "buscar_app", "Busca en app")
        app = manager.register_discovered_application(
            name="AppMix", type="utility",
            capabilities=[cap_abrir, cap_buscar],
            observed_facts={},  # sin exe -> ninguna disponible en runtime
        )
        no_verificadas = app.get_unverified_capabilities()
        assert len(no_verificadas) == 2
        capacidades_no_verificadas = {c.capability for c in no_verificadas}
        assert capacidades_no_verificadas == {
            ApplicationCapability.OPEN,
            ApplicationCapability.SEARCH,
        }


class TestApplicationManagerSeparationQueries:
    """Metodos de consulta de ApplicationManager para la separacion 3.8.4.3."""

    def test_get_application_observed_facts(self):
        manager = _make_manager()
        hechos = {"executable_path": r"C:\MgrApp\app.exe"}
        manager.register_discovered_application(
            name="MgrApp", type="utility", observed_facts=hechos,
        )
        assert manager.get_application_observed_facts("MgrApp") == hechos
        assert manager.get_application_observed_facts("Inexistente") == {}

    def test_get_application_inferred_data(self):
        manager = _make_manager()
        inferido = {"tipo": "supuesto"}
        manager.register_discovered_application(
            name="MgrApp", type="application", inferred_data=inferido,
        )
        assert manager.get_application_inferred_data("MgrApp") == inferido
        assert manager.get_application_inferred_data("Inexistente") == {}

    def test_get_application_unverified_capabilities(self):
        manager = _make_manager()
        cap = _capability(ApplicationCapability.OPEN, "open_mgr", "Abre Mgr")
        manager.register_discovered_application(
            name="MgrApp", type="utility", capabilities=[cap],
        )
        no_verificadas = manager.get_application_unverified_capabilities("MgrApp")
        assert len(no_verificadas) == 1
        assert no_verificadas[0].capability == ApplicationCapability.OPEN
        assert manager.get_application_unverified_capabilities("Inexistente") == []


class TestSeparationCoexistsWithExistingContracts:
    """La separacion no rompe contratos existentes de 3.8.4.1 y 3.8.4.2."""

    def test_metadata_mantiene_discovered_temporary_source(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="AppDesc", type="utility",
            observed_facts={"exe": r"C:\X\a.exe"},
            inferred_data={"tipo": "supuesto"},
        )
        md = app.metadata or {}
        assert md.get("discovered") is True
        assert md.get("temporary") is True
        assert md.get("source") == "discovery"
        assert md.get("observed_facts") == {"exe": r"C:\X\a.exe"}
        assert md.get("inferred_data") == {"tipo": "supuesto"}

    def test_no_llama_save_entity_al_consultar_separacion(self):
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]
        antes = len(mm.saved_entities)
        manager.register_discovered_application(
            name="Consulta", type="utility",
            observed_facts={"exe": r"C:\X\a.exe"},
            inferred_data={"tipo": "supuesto"},
            capabilities=[_capability(ApplicationCapability.OPEN, "open_c", "Abre C")],
        )
        app = manager.get_application("Consulta")
        app.get_observed_facts()
        app.get_inferred_data()
        app.get_unverified_capabilities()
        manager.get_application_observed_facts("Consulta")
        manager.get_application_inferred_data("Consulta")
        manager.get_application_unverified_capabilities("Consulta")
        assert len(mm.saved_entities) == antes, (
            "Consultar la separacion no debe persistir en entities.json"
        )
