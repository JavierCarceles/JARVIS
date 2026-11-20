# -*- coding: utf-8 -*-
"""
Tests de `ApplicationDiscovery.registrar_candidatos_desde_inventario` y
`programar_registro_candidatos_inventario`: conversion de las entradas `.exe` y
`.lnk` de `file_entries` (inventario ya escaneado) en filas de
`application_candidates` del equipo actual, sin reescanear el disco.

Todo usa una SQLite temporal (tmp_path) y ficheros temporales; nunca
`data/system_inventory.sqlite3`. No lanza aplicaciones ni escribe en
`entities.json`.

Ejecucion (Windows):
    python -m pytest tests/hands/apps/application_discovery/test_registrar_candidatos_desde_inventario.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.hands.apps.application_discovery import (
    EVIDENCIA_ORIGEN_FILE_ENTRIES,
    FUENTE_INVENTARIO_SQLITE,
    ApplicationDiscovery,
)
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.inventory.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
    normalize_path,
)
from src.memory.storage import MemoryManager

MAQUINA = "maquina-registro-inventario"
OTRA_MAQUINA = "maquina-ajena-registro"
VOLUMEN = "C:"
ES_WINDOWS = os.name == "nt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pe_minimo(subsistema: int = 2) -> bytes:
    """Bytes minimos de un ejecutable PE: 'MZ', e_lfanew en 0x3C, firma
    'PE\\0\\0' y Subsystem en el offset 0x44 del Optional Header (lo que lee
    `_leer_subsistema_pe`)."""
    datos = bytearray(0x200)
    datos[0:2] = b"MZ"
    e_lfanew = 0x80
    datos[0x3C:0x40] = e_lfanew.to_bytes(4, "little")
    datos[e_lfanew:e_lfanew + 4] = b"PE\x00\x00"
    # SizeOfOptionalHeader (COFF + 16) y Magic PE32 (0x10B).
    datos[e_lfanew + 20:e_lfanew + 22] = (0xE0).to_bytes(2, "little")
    datos[e_lfanew + 24:e_lfanew + 26] = (0x10B).to_bytes(2, "little")
    datos[e_lfanew + 24 + 0x44:e_lfanew + 24 + 0x46] = subsistema.to_bytes(2, "little")
    return bytes(datos)


def _crear_fichero(raiz: Path, relativa: str, contenido: bytes) -> Path:
    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


def _entrada(ruta: Path, raiz: Path, excluded: bool = False, entry_type: str = "file",
             extension: str | None = None) -> dict:
    return {
        "entry_id": "e-" + hashlib.sha1(str(ruta).encode("utf-8")).hexdigest()[:20],
        "absolute_path": str(ruta),
        "relative_path": str(ruta.relative_to(raiz)) if str(ruta).startswith(str(raiz)) else ruta.name,
        "name": ruta.name,
        "extension": extension if extension is not None else ruta.suffix,
        "entry_type": entry_type,
        "size_bytes": 512,
        "excluded": excluded,
        "last_checked_at": "2026-11-20T00:00:00+00:00",
    }


def _escaneo(storage: SystemInventoryStorage, machine_id: str, scan_id: str,
             started_at: str, entradas: list[dict], resultado: str = SCAN_RESULT_OK) -> None:
    storage.begin_scan_run(
        scan_id=scan_id, machine_id=machine_id, volume=VOLUMEN,
        mode=SCAN_MODE_FULL, started_at=started_at,
    )
    if entradas:
        storage.insert_file_entries(scan_id, machine_id, VOLUMEN, entradas)
    storage.end_scan_run(
        scan_id=scan_id, finished_at=started_at, result=resultado,
        entries_count=len(entradas),
    )


def _discovery(storage: SystemInventoryStorage, tmp_path: Path) -> ApplicationDiscovery:
    mm = MemoryManager(str(tmp_path / "memoria"))
    app_manager = SimpleNamespace(memory_manager=mm, get_application=lambda nombre: None)
    calibracion = SimpleNamespace(discover_applications=lambda: [])
    return ApplicationDiscovery(
        preflight=ApplicationPreflight(),
        storage=storage,
        calibration=calibracion,
        machine_id=MAQUINA,
        app_manager=app_manager,
    )


def _filas(storage: SystemInventoryStorage, machine_id: str = MAQUINA) -> dict[str, dict]:
    conn = storage.connect()
    cur = conn.execute(
        "SELECT * FROM application_candidates WHERE machine_id = ?", (machine_id,)
    )
    resultado = {}
    for r in cur.fetchall():
        d = dict(r)
        d["evidencia"] = json.loads(d["evidencia"])
        resultado[d["absolute_path"]] = d
    return resultado


@pytest.fixture
def escenario(tmp_path: Path):
    """Inventario temporal con dos escaneos ok y uno interrumpido del equipo
    actual, y uno de otro equipo."""
    raiz = tmp_path / "disco"
    pe = _pe_minimo()
    app = _crear_fichero(raiz, "Program Files/Editor Prueba/editorprueba.exe", pe)
    mayus = _crear_fichero(raiz, "Program Files/Visor/VISORPRUEBA.EXE", pe)
    winsxs = _crear_fichero(raiz, "Windows/WinSxS/amd64_componente_1/notepad.exe", pe)
    excluido = _crear_fichero(raiz, "Program Files/Excluido/excluido.exe", pe)
    borrado = raiz / "Program Files/Borrado/borrado.exe"  # en file_entries, no en disco
    lnk_menu = _crear_fichero(
        raiz, "ProgramData/Microsoft/Windows/Start Menu/Programs/Editor Prueba.lnk", b"lnk"
    )
    lnk_reciente = _crear_fichero(
        raiz, "Users/persona/AppData/Roaming/Microsoft/Windows/Recent/documento.lnk", b"lnk"
    )
    vieja = _crear_fichero(raiz, "Program Files/Vieja/vieja.exe", pe)
    interrumpida = _crear_fichero(raiz, "Program Files/Interrumpida/interrumpida.exe", pe)
    ajena = _crear_fichero(raiz, "Program Files/Ajena/ajena.exe", pe)

    db = tmp_path / "inventario.sqlite3"
    storage = SystemInventoryStorage(db)
    storage.initialize(machine_id_actual=MAQUINA)

    # Escaneo antiguo ok: solo contiene vieja.exe (no debe usarse).
    _escaneo(storage, MAQUINA, "scan-antiguo", "2026-11-01T10:00:00+00:00",
             [_entrada(vieja, raiz)])
    # Ultimo escaneo ok: el que debe usarse.
    _escaneo(storage, MAQUINA, "scan-ultimo-ok", "2026-11-10T10:00:00+00:00", [
        _entrada(app, raiz),
        _entrada(mayus, raiz, extension=".EXE"),
        _entrada(winsxs, raiz),
        _entrada(excluido, raiz, excluded=True),
        _entrada(borrado, raiz),
        _entrada(lnk_menu, raiz),
        _entrada(lnk_reciente, raiz),
    ])
    # Escaneo posterior interrumpido: no cuenta como completo.
    _escaneo(storage, MAQUINA, "scan-interrumpido", "2026-11-15T10:00:00+00:00",
             [_entrada(interrumpida, raiz)], resultado=SCAN_RESULT_INTERRUPTED)
    # Escaneo ok de otro equipo en la misma base.
    _escaneo(storage, OTRA_MAQUINA, "scan-otra-maquina", "2026-11-12T10:00:00+00:00",
             [_entrada(ajena, raiz)])

    rutas = SimpleNamespace(
        raiz=raiz, app=app, mayus=mayus, winsxs=winsxs, excluido=excluido,
        borrado=borrado, lnk_menu=lnk_menu, lnk_reciente=lnk_reciente,
        vieja=vieja, interrumpida=interrumpida, ajena=ajena,
    )
    yield storage, rutas
    storage.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegistroDesdeInventario:

    def test_registra_solo_filas_validas_del_ultimo_escaneo_ok(self, escenario, tmp_path):
        storage, r = escenario
        llamadas_lnk: list[list[str]] = []

        def resolver(rutas):
            llamadas_lnk.append(list(rutas))
            return {ruta: str(r.app) for ruta in rutas}

        discovery = _discovery(storage, tmp_path)
        informe = discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=resolver
        )
        filas = _filas(storage)

        assert set(filas) == {str(r.app), str(r.mayus), str(r.lnk_menu)}
        # Fuera: escaneo antiguo, interrumpido, WinSxS, excluded=1, borrado,
        # .lnk de Recent y filas de otro equipo.
        for ruta in (r.vieja, r.interrumpida, r.winsxs, r.excluido, r.borrado,
                     r.lnk_reciente, r.ajena):
            assert str(ruta) not in filas
        assert _filas(storage, OTRA_MAQUINA) == {}

        detalle = informe["volumenes"][VOLUMEN]
        assert detalle["scan_id"] == "scan-ultimo-ok"
        # leidos = todas las .exe/.lnk file y no excluidas del escaneo.
        assert detalle["leidos"] == 6
        assert detalle["omitidos_winsxs"] == 1
        assert detalle["omitidos_lnk_fuera_de_menu"] == 1
        assert detalle["descartados_inexistentes"] == 1
        assert detalle["registrados"] == 3
        assert informe["registrados"] == 3
        assert sum(detalle["por_tipo"].values()) == 3
        assert detalle["por_tipo"].get("ejecutable") == 2
        assert detalle["por_tipo"].get("acceso_directo") == 1
        assert sum(detalle["por_subtipo"].values()) == 3
        assert detalle["segundos"] >= 0
        # El .lnk de Recent no se envia al resolutor.
        assert llamadas_lnk == [[str(r.lnk_menu)]]

    def test_contenido_de_cada_fila(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=lambda rutas: {x: str(r.app) for x in rutas}
        )
        filas = _filas(storage)
        for ruta, fila in filas.items():
            esperado = "inv-" + hashlib.sha1(
                f"{MAQUINA}|{normalize_path(ruta)}".encode("utf-8")
            ).hexdigest()[:16]
            assert fila["candidate_id"] == esperado
            assert fila["name"] == Path(ruta).name  # con extension
            assert fila["scan_id"] == "scan-ultimo-ok"  # no se crea scan_run nuevo
            assert fila["volume"] == VOLUMEN
            assert fila["source"] == FUENTE_INVENTARIO_SQLITE
            assert fila["confidence"] in (0.9, 0.7, 0.4, 0.1)
            evidencia = fila["evidencia"]
            assert EVIDENCIA_ORIGEN_FILE_ENTRIES in evidencia
            assert any(e.startswith("subtipo=") for e in evidencia)
            assert ("lanzable=true" in evidencia) != ("lanzable=false" in evidencia)

        conn = storage.connect()
        scans = {row[0] for row in conn.execute("SELECT scan_id FROM scan_runs")}
        assert scans == {"scan-antiguo", "scan-ultimo-ok", "scan-interrumpido", "scan-otra-maquina"}

    def test_lnk_del_menu_con_destino_resuelto_es_lanzable(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=lambda rutas: {x: str(r.app) for x in rutas}
        )
        fila = _filas(storage)[str(r.lnk_menu)]
        assert fila["launch_type"] == "acceso_directo"
        assert "acceso_directo_target_resuelto" in fila["evidencia"]
        assert "lanzable=true" in fila["evidencia"]
        assert fila["confidence"] == 0.7

    def test_lnk_sin_destino_se_guarda_no_lanzable(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        informe = discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=lambda rutas: {x: None for x in rutas}
        )
        fila = _filas(storage)[str(r.lnk_menu)]
        assert fila["launch_type"] == "acceso_directo"
        assert "lanzable=false" in fila["evidencia"]
        assert informe["volumenes"][VOLUMEN]["lnk_resueltos"] == 0

    def test_exe_pe_minimo_segun_so(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=lambda rutas: {x: None for x in rutas}
        )
        fila = _filas(storage)[str(r.app)]
        assert fila["launch_type"] == "ejecutable"
        assert "archivo_ejecutable_existente" in fila["evidencia"]
        if ES_WINDOWS:
            # Sin recursos de version: el encabezado PE es la evidencia.
            assert "encabezado_pel_valido" in fila["evidencia"]
            assert "lanzable=true" in fila["evidencia"]
            assert fila["confidence"] == 0.4
        else:
            # Fuera de Windows no se lee el PE: no se asume lanzable.
            assert "lanzable=false" in fila["evidencia"]

    def test_idempotente_sin_duplicados_y_actualiza_last_checked_at(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        resolver = lambda rutas: {x: str(r.app) for x in rutas}  # noqa: E731
        primero = discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=resolver
        )
        filas_1 = _filas(storage)
        time.sleep(0.02)
        segundo = discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=resolver
        )
        filas_2 = _filas(storage)

        conn = storage.connect()
        total = conn.execute(
            "SELECT COUNT(*) FROM application_candidates WHERE machine_id = ?", (MAQUINA,)
        ).fetchone()[0]
        assert total == 3
        assert set(filas_1) == set(filas_2)
        assert primero["registrados"] == segundo["registrados"] == 3
        for ruta in filas_1:
            assert filas_1[ruta]["candidate_id"] == filas_2[ruta]["candidate_id"]
            assert filas_2[ruta]["last_checked_at"] > filas_1[ruta]["last_checked_at"]

    def test_incluir_winsxs(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        informe = discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], incluir_winsxs=True,
            resolver_lnk=lambda rutas: {x: None for x in rutas},
        )
        assert str(r.winsxs) in _filas(storage)
        assert informe["volumenes"][VOLUMEN]["omitidos_winsxs"] == 0

    def test_volumen_sin_escaneo_ok(self, escenario, tmp_path):
        storage, _ = escenario
        discovery = _discovery(storage, tmp_path)
        informe = discovery.registrar_candidatos_desde_inventario(
            volumenes=["Z:"], resolver_lnk=lambda rutas: {}
        )
        detalle = informe["volumenes"]["Z:"]
        assert detalle["scan_id"] is None
        assert detalle["registrados"] == 0
        assert _filas(storage) == {}

    def test_no_escribe_en_entities_json(self, escenario, tmp_path):
        storage, r = escenario
        discovery = _discovery(storage, tmp_path)
        memoria = tmp_path / "memoria"

        def _instantanea() -> dict[str, bytes]:
            return {
                str(p.relative_to(memoria)): p.read_bytes()
                for p in memoria.rglob("*") if p.is_file()
            } if memoria.exists() else {}

        antes = _instantanea()
        discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN], resolver_lnk=lambda rutas: {x: str(r.app) for x in rutas}
        )
        # El catalogo global no se toca: el auto-registro es bajo demanda.
        assert _instantanea() == antes

    def test_progreso_se_informa(self, escenario, tmp_path):
        storage, r = escenario
        eventos: list[dict] = []
        discovery = _discovery(storage, tmp_path)
        discovery.registrar_candidatos_desde_inventario(
            volumenes=[VOLUMEN],
            resolver_lnk=lambda rutas: {x: None for x in rutas},
            progreso=eventos.append,
        )
        assert eventos
        assert eventos[-1]["registrados"] == 3
        assert eventos[-1]["volumen"] == VOLUMEN


class TestProgramarRegistro:

    def test_espera_al_inventario_y_registra_pendientes(self, escenario, tmp_path, monkeypatch):
        storage, r = escenario
        monkeypatch.setattr(
            SystemInventoryStorage, "obtener_volumes_montados", lambda self: {VOLUMEN}
        )
        # Sin .lnk para no invocar PowerShell en Windows desde el hilo.
        conn = storage.connect()
        conn.execute("DELETE FROM file_entries WHERE lower(extension) = '.lnk'")
        conn.commit()

        esperas: list[bool] = []

        class EjecucionFalsa:
            def esperar(self, timeout=None):
                esperas.append(True)
                return True

        discovery = _discovery(storage, tmp_path)
        hilo = discovery.programar_registro_candidatos_inventario(esperar_a=EjecucionFalsa())
        hilo.join(timeout=60)
        assert not hilo.is_alive()
        assert hilo.daemon
        assert esperas == [True]
        assert storage.existen_candidatos_de_escaneo(MAQUINA, "scan-ultimo-ok")
        assert set(_filas(storage)) == {str(r.app), str(r.mayus)}

        # Segunda vez: el volumen ya tiene candidatos de su ultimo escaneo.
        llamadas: list[object] = []
        monkeypatch.setattr(
            ApplicationDiscovery, "_registrar_desde_inventario",
            lambda self, *a, **k: llamadas.append(a),
        )
        hilo = discovery.programar_registro_candidatos_inventario()
        hilo.join(timeout=60)
        assert llamadas == []

    def test_excepcion_no_sale_del_hilo(self, escenario, tmp_path, monkeypatch):
        storage, _ = escenario

        class EjecucionRota:
            def esperar(self, timeout=None):
                raise RuntimeError("fallo simulado")

        excepciones: list[object] = []
        monkeypatch.setattr(
            "threading.excepthook", lambda args: excepciones.append(args)
        )
        discovery = _discovery(storage, tmp_path)
        hilo = discovery.programar_registro_candidatos_inventario(esperar_a=EjecucionRota())
        hilo.join(timeout=30)
        assert not hilo.is_alive()
        assert excepciones == []
        assert _filas(storage) == {}
