# -*- coding: utf-8 -*-
"""
Tests de `ApplicationDiscovery._candidatos_locales_por_nombre`: seleccion de
candidatos de `application_candidates` por nombre sin falsas ambiguedades
cuando la tabla esta llena (nombre exacto, filas `lanzable=false`, duplicados
del mismo fichero resueltos con la semantica de PATH).

SQLite temporal (tmp_path) y PATH controlado con monkeypatch; nunca
`data/system_inventory.sqlite3`.

Ejecucion (Windows):
    python -m pytest tests/hands/apps/application_discovery/test_candidatos_locales_por_nombre.py -v
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.hands.apps.application_discovery import ApplicationDiscovery
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.inventory.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)
from src.memory.storage import MemoryManager

MAQUINA = "maquina-candidatos-nombre"
VOLUMEN = "C:"
SCAN = "scan-candidatos-nombre"


@pytest.fixture
def entorno(tmp_path: Path):
    storage = SystemInventoryStorage(tmp_path / "inventario.sqlite3")
    storage.initialize(machine_id_actual=MAQUINA)
    storage.begin_scan_run(
        scan_id=SCAN, machine_id=MAQUINA, volume=VOLUMEN, mode=SCAN_MODE_FULL,
        started_at="2026-11-20T10:00:00+00:00",
    )
    storage.end_scan_run(scan_id=SCAN, result=SCAN_RESULT_OK)
    mm = MemoryManager(str(tmp_path / "memoria"))
    discovery = ApplicationDiscovery(
        preflight=ApplicationPreflight(),
        storage=storage,
        calibration=SimpleNamespace(discover_applications=lambda: []),
        machine_id=MAQUINA,
        app_manager=SimpleNamespace(memory_manager=mm, get_application=lambda n: None),
    )
    yield discovery, storage
    storage.close()


def _insertar(storage: SystemInventoryStorage, ruta: Path, evidencia: list[str],
              confianza: float = 0.8, nombre: str | None = None) -> None:
    storage.insert_application_candidates(
        scan_id=SCAN, machine_id=MAQUINA, volume=VOLUMEN,
        candidates=[{
            "candidate_id": f"c-{ruta}",
            "name": nombre or ruta.name,
            "absolute_path": str(ruta),
            "launch_type": "ejecutable",
            "confidence": confianza,
            "evidencia": evidencia,
            "source": "inventario_sqlite",
            "last_checked_at": "2026-11-20T10:00:00+00:00",
        }],
    )


def _rutas(filas: list[dict]) -> list[str]:
    return [str(f["absolute_path"]) for f in filas]


class TestCandidatosLocalesPorNombre:

    def test_nombre_exacto_descarta_coincidencias_parciales(self, entorno, tmp_path):
        discovery, storage = entorno
        chrome = tmp_path / "Google" / "Chrome" / "chrome.exe"
        proxy = tmp_path / "Google" / "Chrome" / "chrome_proxy.exe"
        _insertar(storage, chrome, ["lanzable=true"])
        _insertar(storage, proxy, ["lanzable=true"], confianza=0.9)
        assert _rutas(discovery._candidatos_locales_por_nombre("chrome")) == [str(chrome)]
        # Con extension en la peticion tambien es exacto.
        assert _rutas(discovery._candidatos_locales_por_nombre("Chrome.exe")) == [str(chrome)]

    def test_sin_coincidencia_exacta_se_conservan_las_parciales(self, entorno, tmp_path):
        discovery, storage = entorno
        proxy = tmp_path / "Google" / "Chrome" / "chrome_proxy.exe"
        _insertar(storage, proxy, ["lanzable=true"])
        assert _rutas(discovery._candidatos_locales_por_nombre("chrome")) == [str(proxy)]

    def test_nombre_exacto_sin_mayusculas_ni_acentos(self, entorno, tmp_path):
        discovery, storage = entorno
        # Tanto la busqueda SQL como la comparacion exacta posterior ignoran
        # mayusculas y acentos.
        musica = tmp_path / "Accesos" / "M\u00fasica.lnk"
        otra = tmp_path / "Accesos" / "Musica Studio.lnk"
        _insertar(storage, musica, ["lanzable=true"])
        _insertar(storage, otra, ["lanzable=true"])
        assert _rutas(discovery._candidatos_locales_por_nombre("MUSICA")) == [str(musica)]
        assert _rutas(discovery._candidatos_locales_por_nombre("m\u00fasica")) == [str(musica)]
        assert _rutas(discovery._candidatos_locales_por_nombre("M\u00daSICA.lnk")) == [str(musica)]

    def test_descarta_lanzable_false_y_conserva_filas_antiguas(self, entorno, tmp_path):
        discovery, storage = entorno
        no_lanzable = tmp_path / "A" / "visor.exe"
        antigua = tmp_path / "B" / "visor.exe"
        _insertar(storage, no_lanzable, ["subtipo=desconocido", "lanzable=false"], confianza=0.9)
        # Fila antigua: sin marca lanzable (lista JSON de evidencias antigua).
        _insertar(storage, antigua, ["archivo_existe"], confianza=0.8)
        assert _rutas(discovery._candidatos_locales_por_nombre("visor")) == [str(antigua)]

    def test_duplicados_resueltos_por_orden_de_path(self, entorno, tmp_path, monkeypatch):
        discovery, storage = entorno
        system32 = tmp_path / "Windows" / "System32"
        windows = tmp_path / "Windows"
        en_system32 = system32 / "notepad.exe"
        en_windows = windows / "notepad.exe"
        _insertar(storage, en_windows, ["lanzable=true"], confianza=0.9)
        _insertar(storage, en_system32, ["lanzable=true"], confianza=0.8)

        monkeypatch.setenv("PATH", os.pathsep.join([str(system32), str(windows)]))
        assert _rutas(discovery._candidatos_locales_por_nombre("notepad")) == [str(en_system32)]

        monkeypatch.setenv("PATH", os.pathsep.join([str(windows), str(system32)]))
        assert _rutas(discovery._candidatos_locales_por_nombre("notepad")) == [str(en_windows)]

    def test_duplicados_fuera_de_path_son_ambiguedad_real(self, entorno, tmp_path, monkeypatch):
        discovery, storage = entorno
        uno = tmp_path / "Programas1" / "editor.exe"
        dos = tmp_path / "Programas2" / "editor.exe"
        _insertar(storage, uno, ["lanzable=true"])
        _insertar(storage, dos, ["lanzable=true"])
        monkeypatch.setenv("PATH", str(tmp_path / "otra_carpeta"))
        assert sorted(_rutas(discovery._candidatos_locales_por_nombre("editor"))) == sorted(
            [str(uno), str(dos)]
        )

    def test_ficheros_distintos_con_mismo_nombre_logico_no_se_fusionan(self, entorno, tmp_path,
                                                                       monkeypatch):
        discovery, storage = entorno
        original = tmp_path / "Sistema" / "notepad.exe"
        copia = tmp_path / "Copias" / "notepad_copia.exe"
        _insertar(storage, original, ["lanzable=true"], nombre="App Duplicada")
        _insertar(storage, copia, ["lanzable=true"], nombre="App Duplicada")
        monkeypatch.setenv("PATH", str(tmp_path / "Sistema"))
        # Nombres de fichero distintos: la semantica de PATH no aplica.
        assert len(discovery._candidatos_locales_por_nombre("App Duplicada")) == 2

    def test_limite_y_aislamiento_por_equipo(self, entorno, tmp_path, monkeypatch):
        discovery, storage = entorno
        monkeypatch.setenv("PATH", str(tmp_path / "vacio"))
        for i in range(5):
            _insertar(storage, tmp_path / f"Dir{i}" / "herramienta.exe", ["lanzable=true"])
        storage.begin_scan_run(
            scan_id="scan-ajeno", machine_id="otra-maquina", volume=VOLUMEN,
            mode=SCAN_MODE_FULL, started_at="2026-11-20T11:00:00+00:00",
        )
        storage.end_scan_run(scan_id="scan-ajeno", result=SCAN_RESULT_OK)
        storage.insert_application_candidates(
            scan_id="scan-ajeno", machine_id="otra-maquina", volume=VOLUMEN,
            candidates=[{
                "candidate_id": "c-ajeno", "name": "herramienta.exe",
                "absolute_path": str(tmp_path / "Ajeno" / "herramienta.exe"),
                "launch_type": "ejecutable", "confidence": 0.9, "evidencia": [],
                "last_checked_at": "2026-11-20T11:00:00+00:00",
            }],
        )
        filas = discovery._candidatos_locales_por_nombre("herramienta", limite=3)
        assert len(filas) == 3
        assert all(f["machine_id"] == MAQUINA for f in filas)
        todas = discovery._candidatos_locales_por_nombre("herramienta", limite=10)
        assert len(todas) == 5
