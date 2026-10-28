# -*- coding: utf-8 -*-
"""Investigacion rapida: verificar el 'registro real en memoria' del flujo
register_application -> persistencia -> recarga. Objetivo de unidad 3.2.4.1."""
import json
import tempfile
from pathlib import Path

from src.hands.applications_core import (
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationCapability,
    ApplicationCapabilityDef,
)
from src.memory.storage import MemoryManager, get_memory_manager


def fresh_manager(tmp: Path):
    mm = MemoryManager(tmp)
    m = ApplicationManager.__new__(ApplicationManager)
    m.applications = {}
    m.memory_manager = mm
    return m, mm


def main():
    tmp = Path(tempfile.mkdtemp())
    m, mm = fresh_manager(tmp)

    app = ApplicationKnowledge(
        name="TestApp",
        type="utility",
        executable="testapp.exe",
        url="https://test.example",
        login_required=False,
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name="open_testapp",
                description="Abre TestApp",
                required_ui_elements=[],
                preconditions=["testapp_closed"],
                effects=["testapp_open"],
                cost=10.0,
            )
        ],
    )

    # 1. registro en memoria
    res = m.register_application(app)
    print("register_application devuelve:", res)
    print("manager.applications tiene 'testapp':", "testapp" in m.applications)

    # 2. en cache (get_entities_by_type)
    ents = mm.get_entities_by_type("application")
    print("get_entities_by_type(application) cuenta:", len(ents))
    found_in_cache = any(
        isinstance(e, type(ents[0])) if ents else False for e in ents
    )
    ids_in_cache = [getattr(e, "id", None) for e in ents]
    print("ids en cache tras register:", ids_in_cache)

    # 3. en disco
    disk = json.loads((tmp / "entities.json").read_text(encoding="utf-8"))
    print("entities.json en disco (lista):", disk)
    disk_ids = [e.get("id") for e in disk if isinstance(e, dict)]
    print("ids en disco tras register:", disk_ids)

    # 4. recarga desde disco con un MemoryManager nuevo
    mm2 = MemoryManager(tmp)
    ents2 = mm2.get_entities_by_type("application")
    ids2 = [getattr(e, "id", None) for e in ents2]
    print("ids tras recarga desde disco:", ids2)
    print("TEST: entidad persistida en disco:", "app_testapp" in disk_ids)
    print("TEST: entidad disponible tras recarga:", "app_testapp" in ids2)


if __name__ == "__main__":
    main()
