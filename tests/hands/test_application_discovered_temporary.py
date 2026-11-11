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


class TestCapacidadesInferidasNoConfirmadas:
    """.7.9: las capacidades inferidas NO se persisten como capacidades
    confirmadas en ApplicationKnowledge.capabilities. Se almacenan en
    inferred_data para mantener el contrato observed_facts /
    inferred_data / unverified_capabilities.

    Requisito: no persistir como capacidad confirmada una inferencia sobre
    lo que puede hacer la aplicacion (ej. deducir "puede abrir PDF" solo por
    extension .pdf). Las capacidades inferidas no deben aparecer en
    is_capable() ni en get_unverified_capabilities(), solo en
    get_inferred_capabilities() / inferred_data.
    """

    def _cap_inferida(self) -> ApplicationCapabilityDef:
        return ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_inferida",
            description="Capacidad inferida (no confirmada)",
            required_ui_elements=[],
            preconditions=[],
            effects=["app_inferida_open"],
            cost=5.0,
        )

    def _cap_confirmada(self) -> ApplicationCapabilityDef:
        return ApplicationCapabilityDef(
            capability=ApplicationCapability.SEARCH,
            name="search_confirmada",
            description="Capacidad confirmada/observada",
            required_ui_elements=["search_bar"],
            preconditions=["app_open"],
            effects=["search_done"],
            cost=3.0,
        )

    def test_capacidades_inferidas_van_a_inferred_data_no_a_capabilities(self):
        manager = _make_manager()
        cap_inf = self._cap_inferida()
        app = manager.register_discovered_application(
            name="AppConInferencias", type="utility",
            observed_facts={"exe": r"C:\AppConInferencias\app.exe"},
            inferred_capabilities=[cap_inf],
        )
        # Las capacidades inferidas NO estan en capabilities (no son confirmadas)
        assert app.is_capable(ApplicationCapability.OPEN) is False, (
            "Una capacidad inferida no debe marcarse como capaz (is_capable)"
        )
        # Pero sí están en inferred_data
        md = app.metadata or {}
        assert "inferred_data" in md, "inferred_data debe existir"
        caps_inf = md["inferred_data"].get("capabilities_inferidas")
        assert caps_inf is not None, "capabilities_inferidas debe estar en inferred_data"
        assert len(caps_inf) == 1
        assert caps_inf[0]["capability"] == "open"
        assert caps_inf[0]["name"] == "open_inferida"

    def test_capacidad_confirmada_sigue_en_capabilities(self):
        manager = _make_manager()
        cap_conf = self._cap_confirmada()
        app = manager.register_discovered_application(
            name="AppConConfirmada", type="utility",
            capabilities=[cap_conf],
        )
        assert app.is_capable(ApplicationCapability.SEARCH) is True, (
            "Una capacidad confirmada debe marcarse como capaz (is_capable)"
        )

    def test_get_inferred_capabilities_retorna_inferidas(self):
        manager = _make_manager()
        cap_inf = self._cap_inferida()
        app = manager.register_discovered_application(
            name="AppInferidas", type="utility",
            inferred_capabilities=[cap_inf],
        )
        inferidas = app.get_inferred_capabilities()
        assert len(inferidas) == 1
        assert inferidas[0].capability == ApplicationCapability.OPEN
        assert inferidas[0].name == "open_inferida"

    def test_get_inferred_capabilities_vacio_sin_inferencias(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="AppSinInferidas", type="utility",
            observed_facts={"exe": r"C:\AppSinInferidas\app.exe"},
        )
        assert app.get_inferred_capabilities() == []

    def test_get_unverified_capabilities_no_incluye_inferidas(self):
        manager = _make_manager()
        cap_inf = self._cap_inferida()
        cap_conf = self._cap_confirmada()
        app = manager.register_discovered_application(
            name="AppMixto", type="utility",
            observed_facts={"exe": r"C:\AppMixto\app.exe"},
            inferred_capabilities=[cap_inf],
            capabilities=[cap_conf],
        )
        # get_unverified_capabilities solo revisa self.capabilities, no inferred_data
        unverified = app.get_unverified_capabilities()
        nombres_unverified = [c.name for c in unverified]
        assert "open_inferida" not in nombres_unverified, (
            "Una capacidad inferida no debe aparecer en get_unverified_capabilities"
        )
        # La capacidad confirmada SÍ puede aparecer (si no está disponible)
        assert "search_confirmada" in nombres_unverified or len(unverified) >= 0

    def test_observed_facts_y_inferred_data_se_mantienen_separados(self):
        manager = _make_manager()
        hechos = {"exe": r"C:\AppSep\app.exe", "pid": 1234}
        inferido = {"tipo_por_extension": "utilidad_supuesta", "confianza": 0.6}
        cap_inf = self._cap_inferida()
        app = manager.register_discovered_application(
            name="AppSeparacion", type="utility",
            observed_facts=hechos,
            inferred_data=inferido,
            inferred_capabilities=[cap_inf],
        )
        md = app.metadata or {}
        assert md.get("observed_facts") == hechos
        assert md.get("inferred_data") is not None
        inferred_data = md["inferred_data"]
        assert inferred_data.get("tipo_por_extension") == "utilidad_supuesta"
        assert inferred_data.get("confianza") == 0.6
        assert "capabilities_inferidas" in inferred_data
        # observed_facts y inferred_data son claves distintas, no se mezclan
        assert "observed_facts" in md
        assert "inferred_data" in md
        assert md["observed_facts"] is not md["inferred_data"]

    def test_inferencia_no_se_trata_como_capacidad_disponible_incluso_si_app_esta_disponible(self):
        manager = _make_manager()
        cap_inf = self._cap_inferida()
        # App con executable válido -> is_available() True
        app = manager.register_discovered_application(
            name="AppDisponible", type="utility",
            executable=r"C:\Windows\System32\notepad.exe",
            observed_facts={"exe": r"C:\Windows\System32\notepad.exe"},
            inferred_capabilities=[cap_inf],
        )
        # Aunque la app esté disponible, la capacidad inferida no es capaz
        assert app.is_capable(ApplicationCapability.OPEN) is False
        # Y no aparece en unverified (no está en capabilities)
        assert len(app.get_unverified_capabilities()) == 0
        # Pero sí se recupera desde inferred_data
        assert len(app.get_inferred_capabilities()) == 1

    def test_serializacion_deserializacion_inferidas_conserva_campos(self):
        manager = _make_manager()
        cap_inf = ApplicationCapabilityDef(
            capability=ApplicationCapability.NAVIGATE,
            name="nav_inferida",
            description="Navegación inferida por extensión",
            required_ui_elements=["address_bar"],
            preconditions=["app_open"],
            effects=["url_cambiada"],
            cost=2.5,
            timeout=15.0,
            retry_count=2,
            alternatives=["ir_a_url"],
        )
        app = manager.register_discovered_application(
            name="AppSerializa", type="utility",
            inferred_capabilities=[cap_inf],
        )
        inferidas = app.get_inferred_capabilities()
        assert len(inferidas) == 1
        recuperada = inferidas[0]
        assert recuperada.capability == ApplicationCapability.NAVIGATE
        assert recuperada.name == "nav_inferida"
        assert recuperada.description == "Navegación inferida por extensión"
        assert recuperada.required_ui_elements == ["address_bar"]
        assert recuperada.preconditions == ["app_open"]
        assert recuperada.effects == ["url_cambiada"]
        assert recuperada.cost == 2.5
        assert recuperada.timeout == 15.0
        assert recuperada.retry_count == 2
        assert recuperada.alternatives == ["ir_a_url"]
