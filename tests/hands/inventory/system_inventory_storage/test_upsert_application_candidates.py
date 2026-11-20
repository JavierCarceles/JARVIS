# -*- coding: utf-8 -*-
"""
Tests de `SystemInventoryStorage.upsert_application_candidates`,
`iterar_entradas_lanzables_escaneo` y `existen_candidatos_de_escaneo`.

SQLite temporal (tmp_path); nunca `data/system_inventory.sqlite3`.

Ejecucion (Windows):
    python -m pytest tests/hands/inventory/system_inventory_storage/test_upsert_application_candidates.py -v
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.hands.inventory.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

MAQUINA = "maquina-upsert"
OTRA = "maquina-upsert-ajena"
VOLUMEN = "C:"


@pytest.fixture
def storage(tmp_path: Path):
    s = SystemInventoryStorage(tmp_path / "inventario.sqlite3")
    s.initialize(machine_id_actual=MAQUINA)
    for machine_id, scan_id, inicio in (
        (MAQUINA, "scan-a", "2026-11-10T10:00:00+00:00"),
        (MAQUINA, "scan-b", "2026-11-11T10:00:00+00:00"),
        (OTRA, "scan-otra", "2026-11-12T10:00:00+00:00"),
    ):
        s.begin_scan_run(scan_id=scan_id, machine_id=machine_id, volume=VOLUMEN,
                         mode=SCAN_MODE_FULL, started_at=inicio)
        s.end_scan_run(scan_id=scan_id, result=SCAN_RESULT_OK)
    yield s
    s.close()


def _candidato(candidate_id: str, ruta: str = r"C:\Apps\app.exe", **extra) -> dict:
    datos = {
        "candidate_id": candidate_id,
        "name": "app.exe",
        "absolute_path": ruta,
        "launch_type": "ejecutable",
        "confidence": 0.4,
        "version": None,
        "producto": None,
        "evidencia": ["archivo_ejecutable_existente", "lanzable=true"],
        "source": "inventario_sqlite",
        "last_checked_at": "2026-11-20T10:00:00+00:00",
    }
    datos.update(extra)
    return datos


def _fila(storage: SystemInventoryStorage, candidate_id: str) -> dict:
    row = storage.connect().execute(
        "SELECT * FROM application_candidates WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()
    return dict(row) if row is not None else {}


def _total(storage: SystemInventoryStorage) -> int:
    return storage.connect().execute("SELECT COUNT(*) FROM application_candidates").fetchone()[0]


class TestUpsertApplicationCandidates:

    def test_inserta_y_actualiza_sin_duplicar(self, storage):
        assert storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, [
            _candidato("inv-1"), _candidato("inv-2", ruta=r"C:\Apps\otra.exe"),
        ]) == 2
        assert _total(storage) == 2

        escritas = storage.upsert_application_candidates("scan-b", MAQUINA, "D:", [
            _candidato("inv-1", ruta=r"D:\Apps\app.exe", name="App.exe",
                       launch_type="acceso_directo", confidence=0.9, version="1.2",
                       producto="Prod", evidencia=["lanzable=false"],
                       source="otra_fuente", last_checked_at="2026-11-21T10:00:00+00:00"),
        ])
        assert escritas == 1
        assert _total(storage) == 2
        fila = _fila(storage, "inv-1")
        assert fila["scan_id"] == "scan-b"
        assert fila["volume"] == "D:"
        assert fila["name"] == "App.exe"
        assert fila["absolute_path"] == r"D:\Apps\app.exe"
        assert fila["launch_type"] == "acceso_directo"
        assert fila["confidence"] == 0.9
        assert fila["version"] == "1.2"
        assert fila["producto"] == "Prod"
        assert json.loads(fila["evidencia"]) == ["lanzable=false"]
        assert fila["source"] == "otra_fuente"
        assert fila["last_checked_at"] == "2026-11-21T10:00:00+00:00"
        assert fila["machine_id"] == MAQUINA
        # La otra fila no cambia.
        assert _fila(storage, "inv-2")["scan_id"] == "scan-a"

    def test_no_reescribe_candidato_de_otro_equipo(self, storage):
        storage.upsert_application_candidates("scan-otra", OTRA, VOLUMEN, [
            _candidato("inv-compartido", ruta=r"C:\Ajena\app.exe"),
        ])
        escritas = storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, [
            _candidato("inv-compartido", ruta=r"C:\Propia\app.exe"),
        ])
        assert escritas == 0
        fila = _fila(storage, "inv-compartido")
        assert fila["machine_id"] == OTRA
        assert fila["absolute_path"] == r"C:\Ajena\app.exe"
        assert fila["scan_id"] == "scan-otra"

    def test_lote_atomico(self, storage):
        storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, [_candidato("inv-1")])
        with pytest.raises(sqlite3.IntegrityError):
            storage.upsert_application_candidates("scan-b", MAQUINA, VOLUMEN, [
                _candidato("inv-1", ruta=r"C:\Cambiada\app.exe"),
                _candidato("inv-nueva"),
                _candidato("inv-mala", name=None),  # name NOT NULL
            ])
        assert _total(storage) == 1
        assert _fila(storage, "inv-1")["absolute_path"] == r"C:\Apps\app.exe"
        assert _fila(storage, "inv-nueva") == {}

    def test_lista_vacia(self, storage):
        assert storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, []) == 0

    def test_insert_simple_sigue_rechazando_duplicados(self, storage):
        storage.insert_application_candidates("scan-a", MAQUINA, VOLUMEN, [_candidato("dup")])
        with pytest.raises(sqlite3.IntegrityError):
            storage.insert_application_candidates("scan-a", MAQUINA, VOLUMEN, [_candidato("dup")])

    def test_existen_candidatos_de_escaneo(self, storage):
        assert storage.existen_candidatos_de_escaneo(MAQUINA, "scan-a") is False
        storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, [_candidato("inv-1")])
        assert storage.existen_candidatos_de_escaneo(MAQUINA, "scan-a") is True
        assert storage.existen_candidatos_de_escaneo(MAQUINA, "scan-b") is False
        assert storage.existen_candidatos_de_escaneo(OTRA, "scan-a") is False


class TestBuscarCandidatosSinAcentos:

    @pytest.fixture
    def con_nombres(self, storage):
        storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, [
            _candidato("n1", ruta=r"C:\Menu\Musica.lnk", name="M\u00fasica.lnk"),
            _candidato("n2", ruta=r"C:\Apps\MUSICA.exe", name="MUSICA.exe"),
            _candidato("n3", ruta=r"C:\Apps\espana.exe", name="Espa\u00f1a Viajes.exe"),
            _candidato("n4", ruta=r"C:\Apps\camara.exe", name="C\u00c1MARA.exe"),
            _candidato("n5", ruta=r"C:\Apps\notepad.exe", name="notepad.exe"),
        ])
        return storage

    @staticmethod
    def _nombres(storage, nombre):
        return sorted(f["name"] for f in storage.buscar_candidatos_registrados(MAQUINA, name=nombre))

    def test_sin_tilde_encuentra_con_tilde_y_al_reves(self, con_nombres):
        esperado = sorted(["M\u00fasica.lnk", "MUSICA.exe"])
        assert self._nombres(con_nombres, "musica") == esperado
        assert self._nombres(con_nombres, "M\u00fasica") == esperado
        assert self._nombres(con_nombres, "M\u00daSICA") == esperado

    def test_enye_y_mayusculas_no_ascii(self, con_nombres):
        assert self._nombres(con_nombres, "espana") == ["Espa\u00f1a Viajes.exe"]
        assert self._nombres(con_nombres, "ESPA\u00d1A") == ["Espa\u00f1a Viajes.exe"]
        # La mayuscula acentuada (no ASCII) tambien se ignora.
        assert self._nombres(con_nombres, "c\u00e1mara") == ["C\u00c1MARA.exe"]
        assert self._nombres(con_nombres, "camara") == ["C\u00c1MARA.exe"]

    def test_subcadena_y_sin_coincidencias(self, con_nombres):
        assert self._nombres(con_nombres, "PAD") == ["notepad.exe"]
        assert self._nombres(con_nombres, "no_existe_xyz") == []

    def test_funcion_sql_disponible_en_la_conexion(self, con_nombres):
        conn = con_nombres.connect()
        assert conn.execute("SELECT jarvis_sin_acentos(?)", ("\u00c1rbol \u00d1and\u00fa",)).fetchone()[0] == "arbol nandu"
        assert conn.execute("SELECT jarvis_sin_acentos(NULL)").fetchone()[0] is None


def _entrada(entry_id: str, ruta: str, extension: str, entry_type: str = "file",
             excluded: bool = False) -> dict:
    nombre = ruta.replace("\\", "/").rsplit("/", 1)[-1]
    return {
        "entry_id": entry_id,
        "absolute_path": ruta,
        "relative_path": ruta[3:],
        "name": nombre,
        "extension": extension,
        "entry_type": entry_type,
        "size_bytes": 10,
        "excluded": excluded,
        "last_checked_at": "2026-11-20T10:00:00+00:00",
    }


class TestIterarEntradasLanzables:

    def test_filtra_por_escaneo_extension_tipo_y_exclusion(self, storage):
        storage.insert_file_entries("scan-a", MAQUINA, VOLUMEN, [
            _entrada("e1", r"C:\Apps\uno.exe", ".exe"),
            _entrada("e2", r"C:\Apps\DOS.EXE", ".EXE"),
            _entrada("e3", r"C:\Apps\tres.Exe", ".Exe"),
            _entrada("e4", r"C:\Menu\cuatro.lnk", ".lnk"),
            _entrada("e5", r"C:\Menu\CINCO.LNK", ".LNK"),
            _entrada("e6", r"C:\Apps\seis.dll", ".dll"),
            _entrada("e7", r"C:\Apps\excluido.exe", ".exe", excluded=True),
            _entrada("e8", r"C:\Apps\carpeta.exe", ".exe", entry_type="directory"),
        ])
        storage.insert_file_entries("scan-b", MAQUINA, VOLUMEN, [
            _entrada("e9", r"C:\Apps\otro_escaneo.exe", ".exe"),
        ])
        storage.insert_file_entries("scan-otra", OTRA, VOLUMEN, [
            _entrada("e10", r"C:\Apps\ajeno.exe", ".exe"),
        ])
        lotes = list(storage.iterar_entradas_lanzables_escaneo("scan-a", MAQUINA, lote=2))
        assert all(1 <= len(lote) <= 2 for lote in lotes)
        ids = sorted(fila["entry_id"] for lote in lotes for fila in lote)
        assert ids == ["e1", "e2", "e3", "e4", "e5"]
        fila = next(f for lote in lotes for f in lote if f["entry_id"] == "e2")
        assert set(fila) == {
            "entry_id", "absolute_path", "normalized_path", "name", "extension",
            "volume", "last_checked_at",
        }
        assert fila["absolute_path"] == r"C:\Apps\DOS.EXE"
        assert fila["volume"] == VOLUMEN

        assert list(storage.iterar_entradas_lanzables_escaneo("scan-a", OTRA)) == []
        assert [f["entry_id"] for lote in storage.iterar_entradas_lanzables_escaneo(
            "scan-b", MAQUINA) for f in lote] == ["e9"]

    def test_permite_escribir_entre_lotes(self, storage):
        storage.insert_file_entries("scan-a", MAQUINA, VOLUMEN, [
            _entrada(f"e{i}", rf"C:\Apps\app{i}.exe", ".exe") for i in range(5)
        ])
        vistos = 0
        for lote in storage.iterar_entradas_lanzables_escaneo("scan-a", MAQUINA, lote=2):
            storage.upsert_application_candidates("scan-a", MAQUINA, VOLUMEN, [
                _candidato("inv-" + f["entry_id"], ruta=f["absolute_path"]) for f in lote
            ])
            vistos += len(lote)
        assert vistos == 5
        assert _total(storage) == 5
