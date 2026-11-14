# -*- coding: utf-8 -*-
"""
Tests de la unidad 3.8.5.1.4.11.13: verificacion en equipo nuevo.

En dos perfiles machine_id separados con almacenamiento SQLite temporal
(aislamiento logico; no disponible una segunda maquina fisica en este
entorno), demuestra que:
- las entidades globales anteriores permanecen en el catalogo global
  (entities.json) al cambiar de maquina;
- las nuevas rutas aparecen en el inventario local correcto (SQLite por
  machine_id);
- solo los destinos locales se pasan a preflight (nunca rutas de otro
  equipo).

La prueba con dos machine_id es de aislamiento logico, no sustituye la
cobertura fisica de una segunda maquina; la cobertura de maquina fisica
segunda queda NO VERIFICADA.

No lanza aplicaciones, no toca data/ de produccion, usa solo recursos
reales (copia controlada de entities.json) o temporales controlados (tmp_path).
"""

from __future__ import annotations

import hashlib
import os
import shutil
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
# Rutas de produccion (solo lectura para la copia del catalogo)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTITIES_REAL = PROJECT_ROOT / "data" / "memory" / "entities.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _mem_manager_temp(tmp_path: Path) -> MemoryManager:
    return MemoryManager(str(tmp_path / "data" / "memory"))


def _app_manager_stub(mm: MemoryManager, aplicaciones=None):
    apps = dict(aplicaciones or {})

    def get_application(nombre):
        return apps.get(nombre)

    return SimpleNamespace(memory_manager=mm, get_application=get_application)


def _storage_con_scan(tmp_path: Path, machine_id: str, volume: str = "C:"):
    """Crea una SQLite de inventario real temporal, inicializada y con un scan
    cerrado (OK) para el equipo y volumen indicados. Registra el machine_id
    en la tabla machines (aislamiento por equipo)."""
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


def _discovery(
    tmp_path: Path,
    machine_id: str,
    storage,
    aplicaciones=None,
    mm: MemoryManager | None = None,
):
    if mm is None:
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


def _copiar_catalogo_global(tmp_path: Path):
    """Copia controlada de entities.json de produccion a tmp_path para aislar
    escrituras del catalogo global."""
    memoria_dir = tmp_path / "data" / "memory"
    memoria_dir.mkdir(parents=True, exist_ok=True)
    destino = memoria_dir / "entities.json"
    shutil.copy2(ENTITIES_REAL, destino)
    return destino


# ---------------------------------------------------------------------------
# Aspecto 1: entidades globales anteriores permanecen al cambiar de maquina
# ---------------------------------------------------------------------------


class TestEntidadesGlobalesPermanecen:
    """Verifica que las entidades registradas previamente en el catalogo
    global (entities.json) permanecen intactas al cambiar a un nuevo
    machine_id (nuevo equipo)."""

    def test_entidades_previas_permanecen_al_cambiar_maquina(self, tmp_path):
        # Copia aislada del catalogo global de produccion.
        catalogo_copia = _copiar_catalogo_global(tmp_path)
        mm = MemoryManager(str(catalogo_copia.parent))

        # Entidades previas registradas (simulan maquina anterior).
        entidades_antes = mm.get_entities_by_type("application")
        ids_antes = {e.id for e in entidades_antes}
        assert len(ids_antes) >= 1, (
            "El catalogo global de produccion debe contener entidades previas"
        )

        # Nuevo contexto de maquina (machine_id distinto, SQLite temporal).
        maquina_nueva = "maquina-nueva-11-13"
        exe_nueva = tmp_path / "app_nueva.exe"
        exe_nueva.write_text("dummy")
        almacenamiento, scan_id = _storage_con_scan(tmp_path, maquina_nueva)
        _insertar_candidato(
            almacenamiento, scan_id, maquina_nueva, "App Nueva", exe_nueva
        )

        discovery, mm_nuevo, _ = _discovery(
            tmp_path, maquina_nueva, almacenamiento, mm=mm
        )

        # Auto-registro de la maquina nueva sobre el catalogo global copiado.
        # Construimos un DiscoveredCandidate real para el pipeline.
        from src.hands.application_discovery import DiscoveredCandidate

        candidato = DiscoveredCandidate(
            candidate_id=f"cand-{maquina_nueva}-App Nueva-app_nueva",
            name="App Nueva",
            absolute_path=str(exe_nueva),
            destination=str(exe_nueva),
            volume="C:",
            launch_type="ejecutable",
            launch_subtype="desconocido",
            es_lanzable=True,
            evidencia=["archivo_existe:" + str(exe_nueva)],
            confianza=CONFIANZA_ALTA,
            version=None,
            producto=None,
            fuente="inventario",
            ultima_comprobacion="2026-11-12T00:00:00+00:00",
            disponible=True,
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["bloqueado"] is False
        assert resultado["errores"] == 0
        assert resultado["registrados"] == 1

        # El catalogo global sigue teniendo las entidades previas: no se
        # borraron al cambiar de maquina ni al hacer auto-registro.
        entidades_despues = mm.get_entities_by_type("application")
        ids_despues = {e.id for e in entidades_despues}
        assert ids_antes.issubset(ids_despues), (
            "Entidades globales previas desaparecieron al cambiar de maquina"
        )
        # Se agrego la entidad nueva sin eliminar las previas.
        assert len(entidades_despues) == len(entidades_antes) + 1


# ---------------------------------------------------------------------------
# Aspecto 2: nuevas rutas aparecen en inventario local correcto
# ---------------------------------------------------------------------------


class TestRutasLocalesEnInventarioCorrecto:
    """Verifica que las rutas de cada maquina aparecen solo en el inventario
    SQLite de esa maquina (aislamiento por machine_id)."""

    def test_ruta_solo_en_inventario_de_su_maquina(self, tmp_path):
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

        # Consultar maquina-b desde almacenamiento de maquina-a: vacio.
        filas_cruzadas = almacenamiento_a.buscar_candidatos_registrados(
            machine_id="maquina-b", name="App Compartida"
        )
        assert filas_cruzadas == []


# ---------------------------------------------------------------------------
# Aspecto 3: solo destinos locales pasan preflight
# ---------------------------------------------------------------------------


class TestSoloDestinosLocalesPreflight:
    """Verifica que al resolver una app por nombre solo se consideran los
    destinos locales del machine_id actual y pasan preflight real."""

    def test_resolucion_usa_ruta_local_no_otra_maquina(self, tmp_path):
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

        # Cada resolucion pasa preflight real con su propia ruta local.
        assert res_a.preflight_decision is not None
        assert res_a.preflight_decision.get("valid") is True
        assert res_b.preflight_decision is not None
        assert res_b.preflight_decision.get("valid") is True

        # Nunca se usa la ruta de la otra maquina.
        assert str(exe_b) not in res_a.absolute_path
        assert str(exe_a) not in res_b.absolute_path


# ---------------------------------------------------------------------------
# Integracion real con ejecutable del equipo (sin lanzar)
# ---------------------------------------------------------------------------


def test_integracion_real_notepad_maquina_nueva_sin_lanzar(tmp_path):
    notepad = r"C:\Windows\System32\notepad.exe"
    if not os.path.exists(notepad):
        pytest.skip("notepad.exe no disponible en este equipo")

    maquina_nueva = "maquina-real-11-13"
    almacenamiento, scan_id = _storage_con_scan(tmp_path, maquina_nueva)
    _insertar_candidato(
        almacenamiento,
        scan_id,
        maquina_nueva,
        "Notepad",
        Path(notepad),
        launch_type=LaunchType.EJECUTABLE,
    )
    discovery, mm, _ = _discovery(tmp_path, maquina_nueva, almacenamiento)

    resultado = discovery.resolver_aplicacion_por_nombre("Notepad")
    assert resultado is not None
    assert resultado.absolute_path == notepad
    assert resultado.preflight_decision is not None
    assert resultado.preflight_decision.get("valid") is True

    # Auto-upsert real sobre notepad del equipo en el catalogo aislado.
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
