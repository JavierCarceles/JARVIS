# -*- coding: utf-8 -*-
"""Tests de verificación del REGISTRO en memoria con MemoryManager REAL —
unidad 3.2.4.1 (FASE 3.2.4 — CIERRE, bajo 3.2 CARGA Y REGISTRO).

Verifica el comportamiento REAL del registro de aplicaciones
(`ApplicationManager.register_application`) usando un `MemoryManager` de
respaldo en disco aislado en `tmp_path` (sandbox), en contraste con
`test_application_register_duplicates.py` (3.2.2.3) que usaba mocks.

Objetivo: confirmar que el "registro real en memoria" produce el estado
esperado en un gestor real (no mockeado):

1. `register_application` inserta la app en `manager.applications` (dict interno
   del ApplicationManager) y la expone vía `get_application`.
2. La `Entity` derivada se refleja en la CACHE en memoria del MemoryManager real:
   `get_entity` / `get_entities_by_type` devuelven la entidad registrada con id
   `app_{name.lower()}`, type `application`, name correcto y `properties` con las
   7 claves documentadas (type/executable/url/login_required/capabilities/
   ui_elements/states) y `aliases == []`.
3. La duplicación se evita contra un MM real: re-registrar la misma app devuelve
   `False`, no vuelve a llamar a `save_entity` y no duplica la entrada en caché.
4. Aplicaciones distintas se registran coexistentes en `manager.applications`
   (registro real en memoria a nivel gestor).
5. Tras el registro, `entities.json` es un JSON válido (lista): el fichero se
   "repara" escribiendo JSON válido.

HALLAZGO VERIFICADO (evidencia real; NO corregido en esta hoja — pendiente
D-ENTITIES-PERSIST-BUG): `MemoryManager.save_entity` vuelve a cargar las
entidades DESDE DISCO en cada llamada y `_process_data_for_save` para `ENTITIES`
solo procesa instancias `Entity` (no `List[dict]`), por lo que:

  - la CACHE del MemoryManager conserva SOLO la ÚLTIMA entidad registrada cuando
    la tienda parte de disco vacío (entidades previamente cacheadas se pierden en
    la siguiente `save_entity`);
  - `entities.json` en disco queda `[]` tras un registro en tienda nueva (no se
    persiste el entity);
  - una recarga fresca (nuevo `MemoryManager` sobre el mismo `tmp_path`) no
    recupera la entidad registrada.

Esto refina la afirmación de 3.2.2.1 ("la caché funciona correctamente; solo
afecta disco"): en una tienda SIN entidades preexistentes en disco, la caché SÍ
se ve afectada. En el sistema real (data/memory/entities.json con 32 apps) la
caché conserva las apps de disco + la última registrada, por lo que
`_load_custom_applications` sigue reconstruyendo las 32 apps (ver 3.2.2.4); el
dato perdido de verdad es la persistencia en disco de nuevas apps (`chrome`,
`spotify` hardcodeadas) y de apps registradas en runtime sobre tienda nueva.

Los tests de esta hoja verifican los comportamientos VERDADEROS y CORRECTOS del
registro en memoria; no afirman el comportamiento roto del disco/como un
contrato. D-ENTITIES-PERSIST-BUG está documentado y pendiente de corrección en
fases posteriores (ver registros de 3.2.2.1, 3.2.3.1, 3.2.3.4). No abren
aplicaciones, no lanzan procesos.
"""

import json
from pathlib import Path

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
)
from src.memory.storage import MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_min_manager(memory_manager):
    """ApplicationManager aislado (bypass __init__) con un MemoryManager REAL.

    No ejecuta `_initialize_applications`, por lo que `applications` parte
    vacío y `data/` de producción no se toca. Reutiliza el patrón de
    `test_application_load_correctness.py` (3.2.3.4) para aislar la lógica
    usando un MM de verdad respaldado en disco en `tmp_path`.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = memory_manager
    return manager


def _make_app(name="MyApp", app_type="utility", executable="myapp.exe"):
    """Crea una ApplicationKnowledge mínima para pruebas de registro."""
    return ApplicationKnowledge(name=name, type=app_type, executable=executable)


def _make_app_with_capabilities(name="FullApp"):
    """ApplicationKnowledge con capability + ui_element + states para
    verificar la serialización de `properties`."""
    return ApplicationKnowledge(
        name=name,
        type="browser",
        executable="full.exe",
        url="https://full.example",
        login_required=True,
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name="open_full",
                description="abrir",
                required_ui_elements=[],
                preconditions=[],
                effects=[],
                cost=5.0,
            )
        ],
        ui_elements=[],
        states=[],
    )


def _expected_properties_keys():
    return {
        "type",
        "executable",
        "url",
        "login_required",
        "capabilities",
        "ui_elements",
        "states",
    }


# ---------------------------------------------------------------------------
# 1. Registro real en memoria: manager.applications y get_application
# ---------------------------------------------------------------------------
class TestRealInMemoryRegistration:
    """register_application con MemoryManager REAL: la app queda registrada en
    memoria (manager.applications) y expuesta vía get_application."""

    def test_register_app_added_to_manager_applications(self, tmp_path):
        """La app registrada se inserta en manager.applications bajo la clave
        normalizada del nombre."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app = _make_app(name="Alpha", app_type="utility", executable="alpha.exe")

        result = manager.register_application(app)

        assert result is True
        assert "alpha" in manager.applications
        assert manager.applications["alpha"] is app

    def test_register_app_retrievable_by_get_application(self, tmp_path):
        """get_application resuelve la app registrada (name y clave normalizada)."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app = _make_app(name="Alpha", app_type="utility", executable="alpha.exe")
        manager.register_application(app)

        assert manager.get_application("Alpha") is app
        assert manager.get_application("alpha") is app
        assert manager.get_application("ALPHA") is app

    def test_register_entity_in_real_cache(self, tmp_path):
        """La Entity registrada queda en la CACHE en memoria del MemoryManager
        real (get_entity / get_entities_by_type). Registro único: el entity
        persiste en caché."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        manager.register_application(_make_app(name="Alpha"))

        entity = mm.get_entity("app_alpha")
        assert entity is not None

        entities = mm.get_entities_by_type("application")
        assert len(entities) == 1
        assert entities[0].id == "app_alpha"

    def test_register_entity_id_type_and_name(self, tmp_path):
        """La Entity cacheada tiene id `app_{name.lower()}`, type
        `application` y name preservado."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        manager.register_application(_make_app(name="Alpha"))

        entity = mm.get_entity("app_alpha")
        assert entity.id == "app_alpha"
        assert entity.type == "application"
        assert entity.name == "Alpha"

    def test_register_entity_properties_structure(self, tmp_path):
        """properties contiene exactamente las 7 claves documentadas y
        refleja los valores del ApplicationKnowledge origen."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app = _make_app_with_capabilities(name="FullApp")
        manager.register_application(app)

        entity = mm.get_entity("app_fullapp")
        assert set(entity.properties.keys()) == _expected_properties_keys()
        assert entity.properties["type"] == app.type  # "browser"
        assert entity.properties["executable"] == app.executable
        assert entity.properties["url"] == app.url
        assert entity.properties["login_required"] is True
        assert isinstance(entity.properties["capabilities"], list)
        assert isinstance(entity.properties["ui_elements"], list)
        assert isinstance(entity.properties["states"], list)

    def test_register_entity_aliases_empty(self, tmp_path):
        """register_application siempre persiste aliases == [] en la Entity."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        manager.register_application(_make_app(name="Alpha"))

        entity = mm.get_entity("app_alpha")
        assert entity.aliases == []


# ---------------------------------------------------------------------------
# 2. Evación de duplicados contra MemoryManager REAL
# ---------------------------------------------------------------------------
class TestRegisterDuplicateWithRealMemoryManager:
    """register_application evita duplicados contra un MM real (no mockeado)."""

    def test_second_registration_returns_false(self, tmp_path):
        """Registrar la misma app dos veces: segunda vez devuelve False."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app = _make_app(name="DupApp")

        assert manager.register_application(app) is True
        assert manager.register_application(app) is False

    def test_duplicate_does_not_duplicate_cache(self, tmp_path):
        """Tras dos registros del mismo app, la caché del MM real contiene una
        sola entidad con el id esperado (no se duplica)."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app = _make_app(name="DupApp")
        manager.register_application(app)
        manager.register_application(app)

        entities = mm.get_entities_by_type("application")
        assert len(entities) == 1
        assert entities[0].id == "app_dupapp"

    def test_duplicate_preserves_original_app(self, tmp_path):
        """La app registrada original no se sobreescribe con otra instancia del
        mismo nombre."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app_v1 = _make_app(name="DupApp", executable="dupapp_v1")
        app_v2 = _make_app(name="DupApp", executable="dupapp_v2")
        manager.register_application(app_v1)

        assert manager.register_application(app_v2) is False
        existing = manager.get_application("dupapp")
        assert existing is app_v1
        assert existing.executable == "dupapp_v1"

    def test_duplicate_does_not_overwrite_entity_in_cache(self, tmp_path):
        """La entidad en caché conserva los datos del registro original."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        app_v1 = _make_app(name="DupApp", app_type="browser", executable="dupapp_v1")
        app_v2 = _make_app(name="DupApp", app_type="player", executable="dupapp_v2")
        manager.register_application(app_v1)
        manager.register_application(app_v2)  # omitido (duplicado)

        entity = mm.get_entity("app_dupapp")
        assert entity is not None
        assert entity.name == "DupApp"
        assert entity.properties["type"] == "browser"
        assert entity.properties["executable"] == "dupapp_v1"


# ---------------------------------------------------------------------------
# 3. Registro real en memoria: aplicaciones distintas coexistentes
# ---------------------------------------------------------------------------
class TestRegisterMultipleDistinctApps:
    """El registro real en memoria a nivel `manager.applications` retiene apps
    distintas coexistentes."""

    def test_multiple_distinct_apps_in_manager_applications(self, tmp_path):
        """Dos apps distintas se registran simultáneamente en
        manager.applications (registro real en memoria a nivel gestor)."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        alpha = _make_app(name="Alpha", app_type="utility", executable="alpha.exe")
        beta = _make_app(name="Beta", app_type="player", executable="beta.exe")

        assert manager.register_application(alpha) is True
        assert manager.register_application(beta) is True

        assert manager.get_application("Alpha") is alpha
        assert manager.get_application("Beta") is beta
        # NOTE: con MM real sobre tienda nueva, la caché de entities conserva
        # solo la última (app_beta); app_alpha se pierde de la caché — ver
        # D-ENTITIES-PERSIST-BUG documentado en el docstring del módulo. El
        # registro en `manager.applications` (gestor) sí es real y cohonesto.


# ---------------------------------------------------------------------------
# 4. Caracterización del gap de persistencia en disco (D-ENTITIES-PERSIST-BUG)
# ---------------------------------------------------------------------------
class TestRegisterPersistenceGap:
    """Documenta (sin afirmar como contrato) el comportamiento real tras
    register_application sobre la persistencia en disco.

    VERDAD AVERIGUADA (no contrato): tras registrar una app sobre una tienda en
    `tmp_path` nueva, `entities.json` se escribe como JSON válido (lista),
    reparando cualquier contenido previo; sin embargo la entidad registrada NO
    se incluye en el fichero en disco (D-ENTITIES-PERSIST-BUG). Por tanto, un
    gestor construido de nuevo sobre el mismo `tmp_path` no recupera la app.

    Estos tests afirman hechos VERDADEROS y estables: el fichero es una lista
    JSON válida. No afirman ni que la entidad esté en disco (es mentira) ni que
    la recuperación funcione (es mentira); ese comportamiento roto se documenta
    en docstrings y en el registro de la unidad 3.2.4.1.
    """

    def test_register_repairs_file_to_valid_json(self, tmp_path):
        """Tras register_application, entities.json es una lista JSON válida."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        manager.register_application(_make_app(name="Alpha"))

        raw = (tmp_path / "entities.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_register_does_not_crash_with_existing_file(self, tmp_path):
        """register_application repara un fichero existente (no lanza)."""
        (tmp_path / "entities.json").write_text("[1, 2, 3]", encoding="utf-8")
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)

        result = manager.register_application(_make_app(name="Alpha"))

        assert result is True
        parsed = json.loads((tmp_path / "entities.json").read_text(encoding="utf-8"))
        assert isinstance(parsed, list)

    def test_register_in_memory_persists_within_session(self, tmp_path):
        """La app registrada queda en memoria del gestor ORIGINAL (registro real
        en memoria) y es recuperable tanto por `get_application` como por la
        entidad cacheada en el MemoryManager real.

        La persistencia entre SESIONES (recuperación en un gestor nuevo sobre el
        mismo `tmp_path`) NO se verifica como contrato: está fuera de esta hoja
        ("registro REAL en MEMORIA") y está cubierta por D-ENTITIES-PERSIST-BUG
        (ver registro de unidad 3.2.4.1). Este test afirma hechos verdaderos sobre
        la sesión activa."""
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        manager.register_application(_make_app(name="Alpha"))

        assert manager.get_application("alpha") is not None
        assert mm.get_entity("app_alpha") is not None
