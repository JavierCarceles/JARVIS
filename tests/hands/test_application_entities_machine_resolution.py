# -*- coding: utf-8 -*-
"""
Tests de la unidad 3.8.5.1.4.11.11: resolucion entre catalogo global e inventario local.

Cubre ApplicationDiscovery.resolver_aplicacion_por_nombre y
resolver_aplicacion_por_nombre_con_desambiguacion, que integran:
- catalogo global (stub de ApplicationManager con MemoryManager real sobre ruta temporal);
- inventario local (SystemInventoryStorage real sobre SQLite temporal por machine_id);
- revalidacion de destino en el SO (revalidar_destino_aplicacion);
- preflight real (ApplicationPreflight / LaunchClassifier, sin lanzar);
- auto-upsert del catalogo global cuando la entidad no existe (3.8.5.1.4.11.5/11.6/11.7).

Escenarios del roadmap para 3.8.5.1.4.11.11:
1. Catalogo global conoce la app pero su ruta es de otra maquina -> se resuelve la ruta
   local solo desde SQLite del machine_id actual, nunca la ruta del catalogo.
2. Entidad inexistente global pero candidato local -> auto-upsert en entities.json y
   resolucion con ruta local.
3. Ruta obsoleta / volumen desmontado -> no lanzar (resolucion vacia).
4. Coincidencias multiples -> desambiguacion (ambiguo=True, requiere_desambiguacion=True).
5. Preflight negativo -> no lanzar (preflight_decision.valido False / sin candidatos validos).
6. Dos machine_id distintos con SQLite temporal real -> nunca se cruza una ruta.

No lanza aplicaciones, no toca data/ de produccion, usa solo recursos temporales (tmp_path).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.hands.application_discovery import (
    ApplicationDiscovery,
    FUENTE_CATALOGO,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    LaunchClassifier,
    LaunchType,
)
from src.hands.applications_core import ApplicationKnowledge
from src.hands.system_inventory_storage import (
    SCAN_MODE_INCREMENTAL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)
from src.memory.storage import MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mem_manager_temp(tmp_path: Path) -> MemoryManager:
    return MemoryManager(str(tmp_path / "data" / "memory"))


def _app_manager_stub(mm: MemoryManager, aplicaciones=None):
    """Stub del catalogo global: controla si una app esta en entities.json sin
    tocar el singleton de produccion. La resolucion real (SQLite, revalidacion,
    preflight, auto-upsert) sigue siendo codigo de produccion."""
    apps = dict(aplicaciones or {})

    def get_application(nombre):
        return apps.get(nombre)

    return SimpleNamespace(memory_manager=mm, get_application=get_application)


def _storage_con_scan(tmp_path: Path, machine_id: str, volume: str = "C:"):
    """Crea una SQLite de inventario real temporal, inicializada y con un scan
    cerrado (OK) para el equipo y volumen indicados."""
    db_path = tmp_path / "inventario" / f"inventario_{machine_id}.sqlite3"
    storage = SystemInventoryStorage(db_path=db_path)
    storage.initialize(machine_id_actual=machine_id)
    scan_id = f"scan-{machine_id}"
    storage.begin_scan_run(
        scan_id=scan_id,
        machine_id=machine_id,
        volume=volume,
        mode=SCAN_MODE_INCREMENTAL,
    )
    storage.end_scan_run(scan_id=scan_id, result=SCAN_RESULT_OK)
    return storage, scan_id


def _insertar_candidato(
    storage: SystemInventoryStorage,
    scan_id: str,
    machine_id: str,
    nombre: str,
    ruta: Path,
    volume: str = "C:",
    fuente: str = "inventario",
    launch_type=LaunchType.EJECUTABLE,
):
    launch_type_val = str(getattr(launch_type, "value", launch_type))
    candidatos = [
        {
            "candidate_id": f"cand-{machine_id}-{nombre}-{Path(ruta).stem}",
            "scan_id": scan_id,
            "machine_id": machine_id,
            "volume": volume,
            "name": nombre,
            "absolute_path": str(ruta),
            "launch_type": launch_type_val,
            "confianza": CONFIANZA_ALTA,
            "version": None,
            "producto": None,
            "evidencia": ["archivo_existe:" + str(ruta)],
            "source": fuente,
            "last_checked_at": "2026-11-12T00:00:00+00:00",
        }
    ]
    storage.insert_application_candidates(
        scan_id=scan_id, machine_id=machine_id, volume=volume, candidates=candidatos
    )


def _discovery(tmp_path: Path, machine_id: str, storage, aplicaciones=None):
    mm = _mem_manager_temp(tmp_path)
    app_manager = _app_manager_stub(mm, aplicaciones)
    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    return (
        ApplicationDiscovery(
            preflight=preflight,
            clasificador=clasificador,
            storage=storage,
            calibration=None,
            machine_id=machine_id,
            app_manager=app_manager,
        ),
        mm,
        app_manager,
    )


# ---------------------------------------------------------------------------
# Escenario 1: catalogo conoce la app pero su ruta es de otra maquina
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_catalogo_conoce_app_ruta_otra_maquina_resuelve_ruta_local(
    tmp_path: Path,
):
    exe_local = tmp_path / "app_remota_local.exe"
    exe_local.write_text("dummy")
    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-actual")
    _insertar_candidato(
        almacenamiento, scan_id, "maquina-actual", "App Remota", exe_local
    )
    aplicaciones = {
        "App Remota": ApplicationKnowledge(
            name="App Remota",
            type="application",
            executable=r"\\otro-equipo\apps\app_remota.exe",
        )
    }
    discovery, _, _ = _discovery(
        tmp_path, "maquina-actual", almacenamiento, aplicaciones
    )

    resultado = discovery.resolver_aplicacion_por_nombre("App Remota")

    assert resultado is not None
    assert resultado.absolute_path == str(exe_local)
    assert resultado.destination == str(exe_local)
    # Nunca se usa la ruta del catalogo (otra maquina).
    assert r"\\otro-equipo" not in resultado.absolute_path
    assert resultado.fuente == FUENTE_CATALOGO
    assert resultado.preflight_decision is not None
    assert resultado.preflight_decision.get("valid") is True


# ---------------------------------------------------------------------------
# Escenario 2: entidad inexistente global pero candidato local -> auto-upsert
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_entidad_inexistente_global_candidato_local_auto_upsert(
    tmp_path: Path,
):
    exe_local = tmp_path / "app_nueva_local.exe"
    exe_local.write_text("dummy")
    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-actual")
    _insertar_candidato(
        almacenamiento, scan_id, "maquina-actual", "App Nueva Local", exe_local
    )
    discovery, mm, _ = _discovery(tmp_path, "maquina-actual", almacenamiento)

    resultado = discovery.resolver_aplicacion_por_nombre("App Nueva Local")

    assert resultado is not None
    assert resultado.absolute_path == str(exe_local)
    assert resultado.preflight_decision is not None
    assert resultado.preflight_decision.get("valid") is True

    # Auto-upsert en el catalogo global (entities.json temporal).
    entidades = mm.get_entities_by_type("application")
    assert len(entidades) == 1
    entidad = entidades[0]
    assert entidad.type == "application"
    props = entidad.properties or {}
    assert props.get("estado_disponible") == "available"
    assert props.get("ruta_absoluta_observada") == str(exe_local)
    assert props.get("tipo_lanzamiento_nativo") == "ejecutable"
    # entity_id estable y sin fragmentos de ruta absoluta.
    ruta_str = str(exe_local)
    assert ruta_str not in entidad.id
    assert "Users" not in entidad.id
    assert "Temp" not in entidad.id


# ---------------------------------------------------------------------------
# Escenario 3: ruta obsoleta / volumen desmontado -> no lanzar
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_ruta_obsoleta_no_lanza(tmp_path: Path):
    # App no en catalogo: candidato con ruta inexistente -> no hay lanzable.
    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-actual")
    _insertar_candidato(
        almacenamiento,
        scan_id,
        "maquina-actual",
        "App Obsoleta",
        Path(r"C:\NoExiste\Volumen\Desmontado\app_obsoleta.exe"),
    )
    discovery, _, _ = _discovery(tmp_path, "maquina-actual", almacenamiento)

    resultado = discovery.resolver_aplicacion_por_nombre("App Obsoleta")
    assert resultado is None


def test_3_8_5_1_4_11_11_catalogo_conoce_app_ruta_sqlite_obsoleta_no_lanza(
    tmp_path: Path,
):
    # Catalogo conoce la app, pero su unica ruta en SQLite es obsoleta -> None.
    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-actual")
    _insertar_candidato(
        almacenamiento,
        scan_id,
        "maquina-actual",
        "App Con Ruta Obsoleta",
        Path(r"D:\VolumenDesmontado\app_obsoleta.exe"),
    )
    aplicaciones = {
        "App Con Ruta Obsoleta": ApplicationKnowledge(
            name="App Con Ruta Obsoleta",
            type="application",
            executable=r"\\otro-equipo\apps\app_obsoleta.exe",
        )
    }
    discovery, _, _ = _discovery(
        tmp_path, "maquina-actual", almacenamiento, aplicaciones
    )

    resultado = discovery.resolver_aplicacion_por_nombre("App Con Ruta Obsoleta")
    assert resultado is None


# ---------------------------------------------------------------------------
# Escenario 4: coincidencias multiples -> desambiguacion
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_coincidencias_multiples_desambiguacion(tmp_path: Path):
    exe_a = tmp_path / "app_ambigua_a.exe"
    exe_a.write_text("dummy")
    exe_b = tmp_path / "app_ambigua_b.exe"
    exe_b.write_text("dummy")
    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-actual")
    _insertar_candidato(
        almacenamiento, scan_id, "maquina-actual", "App Ambigua", exe_a
    )
    _insertar_candidato(
        almacenamiento, scan_id, "maquina-actual", "App Ambigua", exe_b
    )
    discovery, _, _ = _discovery(tmp_path, "maquina-actual", almacenamiento)

    resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
        "App Ambigua"
    )

    assert resultado.ambiguo is True
    assert resultado.requiere_desambiguacion is True
    assert len(resultado.alternativas) == 2
    rutas = {c.absolute_path for c in resultado.alternativas}
    assert rutas == {str(exe_a), str(exe_b)}
    # Ninguna ruta se elige silenciosamente; el llamador debe desambiguar.


# ---------------------------------------------------------------------------
# Escenario 5: preflight negativo -> no lanzar
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_preflight_negativo_no_lanza(tmp_path: Path):
    # Archivo existente pero no lanzable (no .exe): preflight lo rechaza.
    archivo_texto = tmp_path / "app_texto.txt"
    archivo_texto.write_text("hola")
    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-actual")
    _insertar_candidato(
        almacenamiento,
        scan_id,
        "maquina-actual",
        "App Texto",
        archivo_texto,
    )
    discovery, _, _ = _discovery(tmp_path, "maquina-actual", almacenamiento)

    # Resolucion simple: devuelve el candidato pero el preflight es negativo.
    resultado = discovery.resolver_aplicacion_por_nombre("App Texto")
    assert resultado is not None
    assert resultado.preflight_decision is not None
    assert resultado.preflight_decision.get("valid") is False

    # Resolucion con desambiguacion: no hay candidatos validos tras preflight.
    resultado_des = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
        "App Texto"
    )
    assert resultado_des.ambiguo is False
    assert resultado_des.requiere_desambiguacion is False
    assert len(resultado_des.candidatos) == 0


# ---------------------------------------------------------------------------
# Escenario 6: dos machine_id distintos, SQLite real, nunca se cruza una ruta
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_dos_machine_ids_nunca_se_cruza_ruta(tmp_path: Path):
    exe_a = tmp_path / "maquina_a" / "app_compartida.exe"
    exe_a.parent.mkdir(parents=True, exist_ok=True)
    exe_a.write_text("dummy")
    exe_b = tmp_path / "maquina_b" / "app_compartida.exe"
    exe_b.parent.mkdir(parents=True, exist_ok=True)
    exe_b.write_text("dummy")

    almacenamiento_a, scan_a = _storage_con_scan(tmp_path, "maquina-a")
    _insertar_candidato(
        almacenamiento_a, scan_a, "maquina-a", "App Compartida", exe_a
    )
    almacenamiento_b, scan_b = _storage_con_scan(tmp_path, "maquina-b")
    _insertar_candidato(
        almacenamiento_b, scan_b, "maquina-b", "App Compartida", exe_b
    )

    discovery_a, _, _ = _discovery(tmp_path, "maquina-a", almacenamiento_a)
    discovery_b, _, _ = _discovery(tmp_path, "maquina-b", almacenamiento_b)

    res_a = discovery_a.resolver_aplicacion_por_nombre("App Compartida")
    res_b = discovery_b.resolver_aplicacion_por_nombre("App Compartida")

    assert res_a is not None
    assert res_b is not None
    assert res_a.absolute_path == str(exe_a)
    assert res_b.absolute_path == str(exe_b)
    assert res_a.absolute_path != res_b.absolute_path

    # Consulta directa de SQLite: aislamiento por machine_id.
    filas_a = almacenamiento_a.buscar_candidatos_registrados(
        machine_id="maquina-a", name="App Compartida"
    )
    filas_b = almacenamiento_b.buscar_candidatos_registrados(
        machine_id="maquina-b", name="App Compartida"
    )
    assert len(filas_a) == 1
    assert filas_a[0]["absolute_path"] == str(exe_a)
    assert len(filas_b) == 1
    assert filas_b[0]["absolute_path"] == str(exe_b)

    # Consultar maquina-b desde el almacenamiento de maquina-a no devuelve ruta de b.
    filas_cruzadas = almacenamiento_a.buscar_candidatos_registrados(
        machine_id="maquina-b", name="App Compartida"
    )
    assert filas_cruzadas == []


# ---------------------------------------------------------------------------
# Integracion real con un ejecutable del equipo (sin lanzar, sin data/ de produccion)
# ---------------------------------------------------------------------------


def test_3_8_5_1_4_11_11_integracion_real_notepad_sin_lanzar(tmp_path: Path):
    notepad = r"C:\Windows\System32\notepad.exe"
    if not os.path.exists(notepad):
        pytest.skip("notepad.exe no disponible en este equipo")

    almacenamiento, scan_id = _storage_con_scan(tmp_path, "maquina-real")
    _insertar_candidato(
        almacenamiento,
        scan_id,
        "maquina-real",
        "Notepad",
        Path(notepad),
        launch_type=LaunchType.EJECUTABLE,
    )
    discovery, mm, _ = _discovery(tmp_path, "maquina-real", almacenamiento)

    resultado = discovery.resolver_aplicacion_por_nombre("Notepad")
    assert resultado is not None
    assert resultado.absolute_path == notepad
    assert resultado.preflight_decision is not None
    assert resultado.preflight_decision.get("valid") is True

    # Auto-upsert real sobre notepad del equipo.
    entidades = mm.get_entities_by_type("application")
    assert len(entidades) == 1
    entidad = entidades[0]
    assert entidad.name == "notepad"
    assert entidad.type == "application"
    props = entidad.properties or {}
    assert props.get("ruta_absoluta_observada") == notepad
    assert props.get("estado_disponible") == "available"
    assert "C:" not in entidad.id
    assert "System32" not in entidad.id
    assert "Windows" not in entidad.id
