# -*- coding: utf-8 -*-
"""Registro temporal en memoria de aplicaciones descubiertas (unidad 3.8.4.1).

Define como representar temporalmente una aplicacion descubierta que no exista
en el catalogo conocido, SIN alterar data/memory/entities.json.

Reutiliza contratos reales:
- ApplicationKnowledge (dataclass, name+type obligatorios, resto opcional).
- ApplicationManager.applications (dict en memoria, clave normalizada).
- ApplicationManager._normalize_name (clave case-insensitive).
- register_application (persiste en entities.json: NO se usa aqui).

No modifica codigo de produccion ni entities.json. Verifica que:
- La app descubierta queda solo en memoria (no se llama a save_entity).
- Es recuperable via get_application con clave normalizada.
- El metadata marca discovered=True, temporary=True, source="discovery".
- Se separan observed_facts, inferred_data y capabilities no verificadas.
- No entra en conflicto con aplicaciones ya registradas.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    get_application_manager,
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
    """Crea ApplicationManager sin __init__ (evita registrar Chrome/Spotify
    ni cargar entidades de memoria) y con memory_manager falsificado."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = _FakeMemoryManager()
    return manager


class TestRegisterDiscoveredApplicationInMemoryOnly:
    """La aplicacion descubierta queda solo en memoria; no toca entities.json."""

    def test_registra_solo_en_memoria_sin_llamar_save_entity(self):
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]
        assert isinstance(mm, _FakeMemoryManager)

        app = manager.register_discovered_application(
            name="NuevaAppDescubierta", type="utility",
            observed_facts={"executable_path": r"C:\NuevaApp\nuevaapp.exe"},
        )

        assert app is not None
        assert app.name == "NuevaAppDescubierta"
        assert app.type == "utility"
        assert "nuevaappdescubierta" in manager.applications
        # save_entity NO debio llamarse -> entities.json no se altera
        assert mm.saved_entities == [], (
            "register_discovered_application no debe persistir en entities.json"
        )

    def test_es_recuperable_via_get_application_clave_normalizada(self):
        manager = _make_manager()
        manager.register_discovered_application(name="Mi App X", type="browser")

        recuperada = manager.get_application("Mi App X")
        assert recuperada is not None
        assert recuperada.name == "Mi App X"
        assert recuperada.type == "browser"

    def test_clave_case_insensitive(self):
        manager = _make_manager()
        manager.register_discovered_application(name="Nueva App", type="utility")
        assert "nueva app" in manager.applications
        assert manager.get_application("NUEVA APP") is not None
        assert manager.get_application("nueva app") is not None


class TestDiscoveredMetadataSeparation:
    """Separacion de hechos observados, datos inferidos y capacidades no verificadas."""

    def test_metadata_marca_discovered_temporary_source(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="AppDesc", type="utility",
            observed_facts={"exe": r"C:\AppDesc\app.exe"},
        )
        md = app.metadata or {}
        assert md.get("discovered") is True
        assert md.get("temporary") is True
        assert md.get("source") == "discovery"

    def test_observed_facts_guardados_en_metadata(self):
        manager = _make_manager()
        hechos = {"executable_path": r"C:\AppDesc\app.exe", "pid": 1234}
        app = manager.register_discovered_application(
            name="AppDesc", type="utility", observed_facts=hechos,
        )
        md = app.metadata or {}
        assert md.get("observed_facts") == hechos

    def test_inferred_data_guardado_por_separado(self):
        manager = _make_manager()
        inferido = {"tipo_por_extension": "utilidad_supuesta", "confianza": 0.6}
        app = manager.register_discovered_application(
            name="AppDesc", type="application", inferred_data=inferido,
        )
        md = app.metadata or {}
        assert md.get("inferred_data") == inferido

    def test_capacidades_no_verificadas_aceptadas(self):
        manager = _make_manager()
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_appdesc",
            description="Abre AppDesc",
            required_ui_elements=[],
            preconditions=[],
            effects=["appdesc_open"],
            cost=5.0,
        )
        app = manager.register_discovered_application(
            name="AppDesc", type="utility", capabilities=[cap],
        )
        assert app.is_capable(ApplicationCapability.OPEN) is True
        # Declarada pero no verificada en runtime (is_available False por no tener exe valido)
        assert app.is_capability_available(ApplicationCapability.OPEN) is False


class TestDiscoveredAppDoesNotOverrideRegistered:
    """No entra en conflicto con aplicaciones ya registradas (Chrome, Spotify)."""

    def test_no_sobrescribe_app_existente_en_memoria(self):
        manager = _make_manager()
        chrome = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
        )
        manager.register_application(chrome)
        # Contar entidades ya guardadas por register_application
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]
        entidades_antes = len(mm.saved_entities)
        # register_discovered_application con el mismo nombre: no debe llamar
        # a save_entity (no duplica en entities.json aunque colisione) y NO
        # debe sobrescribir la app de catalogo existente.
        app = manager.register_discovered_application(
            name="Chrome", type="browser",
            observed_facts={"origen": "descubrimiento_en_runtime"},
        )
        assert app.name == "Chrome"
        # Se conserva la entrada previa: la app devuelta es la de catalogo,
        # no la descubierta.
        assert app is chrome
        assert manager.applications["chrome"] is chrome
        assert len(mm.saved_entities) == entidades_antes, (
            "register_discovered_application no debe persistir en entities.json"
        )

    def test_no_sobrescribe_por_alias_de_app_existente(self):
        """Nombre normalizado de descubierta colisiona con alias de app registrada."""
        manager = _make_manager()
        existing = ApplicationKnowledge(
            name="MiApp", type="utility", executable="miapp.exe",
            metadata={"aliases": ["miapp_alias", "mi app"]},
        )
        manager.register_application(existing)
        mm: _FakeMemoryManager = manager.memory_manager
        entidades_antes = len(mm.saved_entities)

        app = manager.register_discovered_application(
            name="miapp_alias", type="utility",
            observed_facts={"origen": "descubrimiento"},
        )
        # Se conserva la entrada previa: devuelve la existente.
        assert app is existing
        assert manager.get_application("miapp_alias") is existing
        assert len(mm.saved_entities) == entidades_antes

    def test_no_sobrescribe_por_alias_de_descubierta_que_colisiona_con_nombre(self):
        """Alias de la descubierta colisiona con nombre normalizado de app registrada."""
        manager = _make_manager()
        existing = ApplicationKnowledge(
            name="OtraApp", type="utility", executable="otraapp.exe",
        )
        manager.register_application(existing)
        mm: _FakeMemoryManager = manager.memory_manager
        entidades_antes = len(mm.saved_entities)

        app = manager.register_discovered_application(
            name="NuevaDescubierta", type="utility",
            metadata={"aliases": ["otraapp"]},
            observed_facts={"origen": "descubrimiento"},
        )
        assert app is existing
        assert manager.get_application("otraapp") is existing
        assert len(mm.saved_entities) == entidades_antes

    def test_no_sobrescribe_por_alias_compartido_entre_descubiertas(self):
        """Dos descubiertas comparten un alias: la primera se conserva."""
        manager = _make_manager()
        primera = manager.register_discovered_application(
            name="AppA", type="utility",
            metadata={"aliases": ["alias_compartido"]},
            observed_facts={"origen": "descubrimiento"},
        )
        mm: _FakeMemoryManager = manager.memory_manager
        entidades_antes = len(mm.saved_entities)

        app = manager.register_discovered_application(
            name="AppB", type="utility",
            metadata={"aliases": ["alias_compartido"]},
            observed_facts={"origen": "descubrimiento"},
        )
        assert app is primera
        assert manager.get_application("appb") is None  # AppB no se registro
        assert manager.get_application("alias_compartido") is primera
        assert len(mm.saved_entities) == entidades_antes

    def test_registro_nuevo_sin_conflicto_registra_ok(self):
        """Nombre y alias nuevos sin conflicto: se registra normalmente."""
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager
        entidades_antes = len(mm.saved_entities)

        app = manager.register_discovered_application(
            name="AppUnica", type="utility",
            metadata={"aliases": ["unica_alias"]},
            observed_facts={"exe": r"C:\AppUnica\app.exe"},
        )
        assert app.name == "AppUnica"
        assert manager.get_application("AppUnica") is app
        assert manager.get_application("unica_alias") is app
        assert len(mm.saved_entities) == entidades_antes

    def test_app_descubierta_no_afecta_get_de_app_registrada(self):
        manager = _make_manager()
        manager.register_discovered_application(
            name="NuevaApp", type="utility", observed_facts={"exe": r"C:\NuevaApp\a.exe"},
        )
        # Una app distinta no registrada sigue sin encontrarse
        assert manager.get_application("AppInexistente") is None


class TestMinimalConstruction:
    """Construccion minima: solo name (type default "application")."""

    def test_solo_name_es_suficiente(self):
        manager = _make_manager()
        app = manager.register_discovered_application(name="SoloNombre")
        assert app.name == "SoloNombre"
        assert app.type == "application"
        assert app.metadata.get("discovered") is True
        assert manager.get_application("SoloNombre") is app


class TestGlobalManagerIntegration:
    """Integracion con la instancia global get_application_manager (no persiste)."""

    def test_global_manager_puede_registrar_descubierta(self):
        manager = get_application_manager()
        # Nota: el global ya tiene Chrome/Spotify cargados. Usamos nombre unico.
        app = manager.register_discovered_application(
            name="AppDescGlobalTest", type="utility",
            observed_facts={"exe": r"C:\AppDescGlobalTest\app.exe"},
        )
        assert app is not None
        assert manager.get_application("AppDescGlobalTest") is app
        # No debe haber persistido nada en entities.json (no podemos verificar
        # el disco directamente, pero el metodo no llama a save_entity por diseño).
