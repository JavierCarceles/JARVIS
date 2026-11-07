# -*- coding: utf-8 -*-
"""Preservacion de entities.json ante registro y consumo de conocimiento dinamico (unidad 3.8.4.4.4).

Objetivo verificable: confirmar que `register_discovered_application` y los
consumidores del conocimiento dinamico (lecturas de `ApplicationManager`) no
modifican ningun entities.json ni su esquema, y que las 7 entidades originales
de `data/knowledge/entities.json` permanecen intactas (linea base 3.8.4.4.2).

Reutiliza contratos reales:
- tests/helpers/entities_state.py (verify_entities_json_unchanged).
- src/hands/applications_core.py (ApplicationManager, register_discovered_application,
  get_application, get_application_capabilities, get_application_manager).
- Linea base 3.8.4.4.2: data/knowledge/entities.json = 7 entidades / 3231 bytes /
  SHA-256 60635AA8F64FAAD75C2C9635E483769874A60E0A98FD1244F696AC2B62A0DAB7.

No modifica codigo de produccion ni entities.json.
"""

from __future__ import annotations

import json
from pathlib import Path

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
from tests.helpers.entities_state import (
    snapshot_entities_json,
    verify_entities_json_unchanged,
)


# ---------------------------------------------------------------------------
# Rutas (calculadas desde __file__ para ser independientes de la CWD/sandbox)
# ---------------------------------------------------------------------------
_TESTS_DIR = Path(__file__).resolve().parents[1]      # tests/
_ROOT_DIR = _TESTS_DIR.parent                          # raiz del repositorio
ENTITIES_KNOWLEDGE_PATH = _ROOT_DIR / "data" / "knowledge" / "entities.json"
ENTITIES_MEMORY_PATH = _ROOT_DIR / "data" / "memory" / "entities.json"

# Linea base fijada en 3.8.4.4.2 (data/knowledge/entities.json).
ENTITIES_KNOWLEDGE_BASELINE_SHA256 = (
    "60635aa8f64faad75c2c9635e483769874a60e0a98fd1244f696ac2b62a0dab7"
)
ENTITIES_KNOWLEDGE_BASELINE_SIZE = 3231
ENTITIES_KNOWLEDGE_BASELINE_COUNT = 7
ENTITIES_KNOWLEDGE_BASELINE_IDS = {
    "nissaxter", "shroud", "pokimane", "youtube", "spotify", "github", "twitch",
}


def _discovered_app(name: str, app_type: str = "utility") -> ApplicationKnowledge:
    """Construye una ApplicationKnowledge igual a la que crearia
    register_discovered_application (3.8.4.1)."""
    return ApplicationKnowledge(
        name=name,
        type=app_type,
        executable=rf"C:\Apps\{name}\{name}.exe",
        url=f"https://{name.lower()}.example",
        login_required=False,
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name=f"open_{name.lower()}",
                description=f"Abre {name}",
                required_ui_elements=[],
                preconditions=[],
                effects=[f"{name.lower()}_open"],
                cost=5.0,
            )
        ],
        metadata={
            "discovered": True,
            "temporary": True,
            "source": "discovery",
            "observed_facts": {"executable_path": rf"C:\Apps\{name}\{name}.exe"},
            "inferred_data": {"tipo_por_extension": "utilidad_supuesta"},
        },
    )


def _operacion_registro_y_consumo(_temp_entities_path: Path) -> None:
    """Registra aplicaciones descubiertas y consume conocimiento dinamico
    mediante lecturas de ApplicationManager. Nunca invoca save_entity."""
    manager: ApplicationManager = get_application_manager()

    # Registro de aplicaciones descubiertas (solo memoria, sin save_entity).
    app_alpha = manager.register_discovered_application(
        name="AppDescAlpha38444", type="utility",
        observed_facts={"executable_path": r"C:\Apps\AppDescAlpha38444\app.exe"},
    )
    app_beta = manager.register_discovered_application(
        name="AppDescBeta38444", type="browser",
        observed_facts={"executable_path": r"C:\Apps\AppDescBeta38444\app.exe"},
        inferred_data={"tipo": "navegador_supuesto"},
    )

    # Consumidores del conocimiento dinamico (lecturas de memoria, sin escritura).
    assert manager.get_application("AppDescAlpha38444") is app_alpha
    assert manager.get_application("AppDescBeta38444") is app_beta
    assert manager.get_application("AppInexistente38444") is None

    # Capacidades de una app descubierta (lectura).
    caps = manager.get_application_capabilities("AppDescAlpha38444")
    assert isinstance(caps, dict)

    # Elementos UI de una app descubierta (lectura).
    ui = manager.get_application_ui_elements("AppDescAlpha38444")
    assert isinstance(ui, dict)


class TestPreservacionEntitiesJsonDescubrimiento:
    """register_discovered_application + consumidores no alteran entities.json."""

    def test_knowledge_entities_json_inalterable(self):
        """data/knowledge/entities.json (linea base 7 entidades) no se modifica."""
        resultado = verify_entities_json_unchanged(
            ENTITIES_KNOWLEDGE_PATH, _operacion_registro_y_consumo
        )
        assert resultado["source_untouched"] is True
        assert resultado["changed"] is False

        # La linea base de las 7 entidades originales permanece intacta.
        antes = resultado["source_before"]
        despues = resultado["source_after"]
        assert antes.sha256 == ENTITIES_KNOWLEDGE_BASELINE_SHA256
        assert antes.size_bytes == ENTITIES_KNOWLEDGE_BASELINE_SIZE
        assert despues.sha256 == ENTITIES_KNOWLEDGE_BASELINE_SHA256
        assert despues.size_bytes == ENTITIES_KNOWLEDGE_BASELINE_SIZE

    def test_memory_entities_json_inalterable(self):
        """data/memory/entities.json (usado por MemoryManager) no se modifica
        por registro/consumo de conocimiento dinamico."""
        resultado = verify_entities_json_unchanged(
            ENTITIES_MEMORY_PATH, _operacion_registro_y_consumo
        )
        assert resultado["source_untouched"] is True
        assert resultado["changed"] is False

    def test_siete_entidades_originales_intactas(self):
        """Verifica concretamente que las 7 entidades originales de
        data/knowledge/entities.json siguen presentes tras la operacion."""
        snapshot = snapshot_entities_json(ENTITIES_KNOWLEDGE_PATH)
        assert snapshot.sha256 == ENTITIES_KNOWLEDGE_BASELINE_SHA256
        assert snapshot.size_bytes == ENTITIES_KNOWLEDGE_BASELINE_SIZE

        datos = json.loads(snapshot.contenido.decode("utf-8"))
        assert isinstance(datos, list)
        assert len(datos) == ENTITIES_KNOWLEDGE_BASELINE_COUNT
        ids = {e.get("id") for e in datos if isinstance(e, dict)}
        assert ids == ENTITIES_KNOWLEDGE_BASELINE_IDS
