# -*- coding: utf-8 -*-
"""Contrato de persistencia para aplicaciones descubiertas — unidad 3.8.4.2.

Objetivo verificable: confirmar que el conocimiento dinamico de aplicaciones
descubiertas (`ApplicationKnowledge`/`ApplicationManager`, unidad 3.8.4.1)
se mantiene solo en memoria y NO se persiste mediante los mecanismos
existentes (`MemoryManager.save_entity` -> `data/memory/entities.json`),
porque su contrato real no es apto para ellas:

1. `register_application` persiste solo 7 claves en `Entity.properties`
   (`type`, `executable`, `url`, `login_required`, `capabilities`,
   `ui_elements`, `states`) y descarta `metadata` (incluido
   `discovered`/`temporary`/`source` y `observed_facts`/`inferred_data`),
   por lo que una app descubierta perderia su identidad de descubrimiento
   si se registrara como entidad.
2. `register_discovered_application` por diseno NO invoca `save_entity`
   (verificado en 3.8.4.1).
3. `3.8.4.4` prohibe alterar el esquema, las entidades originales ni el
   contenido de `data/memory/entities.json` como parte de esta
   funcionalidad.

Conclusion: se reutilizan `ApplicationKnowledge` y `ApplicationManager` en
memoria para las apps descubiertas; la persistencia via `save_entity` se
reserva a registros explicitos de catalogo (`register_application`) y nunca
se aplica automaticamente a apps descubiertas/temporales.

No modifica codigo de produccion ni entities.json.
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
)


class _FakeMemoryManager:
    """Memory manager simulado que registra las entidades pasadas a save_entity."""

    def __init__(self) -> None:
        self.saved: list = []

    def save_entity(self, entity: Any) -> None:
        self.saved.append(entity)

    def get_entities_by_type(self, _type: str) -> list:
        return []


def _make_manager() -> ApplicationManager:
    """Crea ApplicationManager sin __init__ (evita cargar Chrome/Spotify ni
    entities.json de produccion) con un memory manager falsificado."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = _FakeMemoryManager()
    return manager


def _discovered_app() -> ApplicationKnowledge:
    """ApplicationKnowledge tal como la construiria
    register_discovered_application (3.8.4.1): con metadata de descubrimiento."""
    return ApplicationKnowledge(
        name="AppDescubierta",
        type="utility",
        executable=r"C:\AppDescubierta\app.exe",
        url="https://appdescubierta.example",
        login_required=False,
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name="open_appdescubierta",
                description="Abre AppDescubierta",
                required_ui_elements=[],
                preconditions=[],
                effects=["appdescubierta_open"],
                cost=5.0,
            )
        ],
        ui_elements=[
            UIElement(name="btn_iniciar", type="button", required_capability=ApplicationCapability.OPEN),
        ],
        states=[ApplicationState.CLOSED, ApplicationState.OPEN],
        metadata={
            "discovered": True,
            "temporary": True,
            "source": "discovery",
            "observed_facts": {"executable_path": r"C:\AppDescubierta\app.exe", "ventana": "AppDescubierta"},
            "inferred_data": {"tipo_por_extension": "utilidad_supuesta", "confianza": 0.6},
        },
    )


# ---------------------------------------------------------------------------
# 1. El contrato de save_entity no conserva la metadata de descubrimiento
# ---------------------------------------------------------------------------
class TestSaveEntityDescartaMetadataDeDescubrimiento:
    """Persistir una app descubierta mediante register_application/save_entity
    descarta todos los campos que la identifican como descubierta/temporal."""

    def test_registro_persiste_solo_siete_claves_y_descarta_metadata(self):
        manager = _make_manager()
        app = _discovered_app()

        assert manager.register_application(app) is True
        assert len(manager.memory_manager.saved) == 1

        entity = manager.memory_manager.saved[-1]
        props = entity.properties

        # Exactamente las 7 claves del contrato de registro, nada mas.
        assert set(props.keys()) == {
            "type", "executable", "url", "login_required",
            "capabilities", "ui_elements", "states",
        }
        # La metadata de descubrimiento NO se guarda: se perderia.
        assert "metadata" not in props
        assert "discovered" not in props
        assert "temporary" not in props
        assert "source" not in props
        assert "observed_facts" not in props
        assert "inferred_data" not in props
        # El id derivado la trata como entidad de catalogo conocida, no como descubrimiento.
        assert entity.id == "app_appdescubierta"
        assert entity.type == "application"

    def test_capacidades_se_reducen_a_nombres_y_pierden_detalle(self):
        """Las ApplicationCapabilityDef se reducen a capability.value en la Entity;
        preconditions/efectos/coste/tiempo de espera de la capacidad no se
        persisten, por lo que la estructura completa del contrato no sobrevive."""
        manager = _make_manager()
        app = _discovered_app()
        manager.register_application(app)

        props = manager.memory_manager.saved[-1].properties
        assert props["capabilities"] == ["open"]
        assert props["ui_elements"] == [
            {"name": "btn_iniciar", "type": "button", "description": "", "required_capability": "open"},
        ]


# ---------------------------------------------------------------------------
# 2. Las apps descubiertas nunca tocan save_entity (decisión de 3.8.4.2)
# ---------------------------------------------------------------------------
class TestDescubiertasNuncaSePersisten:
    """register_discovered_application mantiene la app solo en memoria; no
    invoca save_entity, por lo que entities.json no se altera."""

    def test_registra_solo_en_memoria_sin_llamar_save_entity(self):
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]

        app = manager.register_discovered_application(
            name="AppDesc", type="utility",
            observed_facts={"executable_path": r"C:\AppDesc\app.exe"},
        )

        assert app is not None
        assert "appdesc" in manager.applications
        assert manager.get_application("AppDesc") is app
        assert mm.saved == [], (
            "register_discovered_application no debe persistir en entities.json"
        )

    def test_metadata_de_descubierta_se_conserva_solo_en_memoria(self):
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="AppDesc", type="utility",
            observed_facts={"exe": r"C:\AppDesc\app.exe"},
            inferred_data={"tipo": "supuesto"},
        )

        md = app.metadata or {}
        assert md.get("discovered") is True
        assert md.get("temporary") is True
        assert md.get("source") == "discovery"
        assert md.get("observed_facts") == {"exe": r"C:\AppDesc\app.exe"}
        assert md.get("inferred_data") == {"tipo": "supuesto"}
        # Nada de lo anterior llega a save_entity.
        assert manager.memory_manager.saved == []


# ---------------------------------------------------------------------------
# 3. Sin duplicados ni escritura accidental de entities.json
# ---------------------------------------------------------------------------
class TestNoDuplicacionNiEscrituraDeEntitiesJson:
    """Re-registrar una app descubierta no escribe en save_entity ni duplica."""

    def test_registro_repetido_no_llama_save_entity(self):
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]

        manager.register_discovered_application(name="AppX", type="utility")
        manager.register_discovered_application(name="AppX", type="utility")

        assert mm.saved == []
        assert manager.get_application("AppX") is not None

    def test_app_descubierta_no_sobrescribe_catalogo_persistido(self):
        """Una app descubierta con nombre de app conocida (p.ej. Chrome)
        se guarda solo en memoria y no genera entidad de persistencia."""
        manager = _make_manager()
        chrome = ApplicationKnowledge(name="Chrome", type="browser", executable="chrome")
        manager.register_application(chrome)
        entidades_antes = len(manager.memory_manager.saved)

        manager.register_discovered_application(
            name="Chrome", type="utility",
            observed_facts={"origen": "descubrimiento_en_runtime"},
        )

        assert len(manager.memory_manager.saved) == entidades_antes, (
            "register_discovered_application no debe persistir en entities.json"
        )
        assert manager.applications["chrome"].type == "utility"  # memoria: la descubierta reemplaza
