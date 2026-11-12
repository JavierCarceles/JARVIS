# -*- coding: utf-8 -*-
"""
Verificacion de la unidad 3.8.5.1.4.10.8 (entorno real).

Desde el inventario real se localiza una aplicacion inocua no registrada
previamente, se comprueba que el candidato tiene destino y evidencia
suficientes, se pasa por ApplicationPreflight y se registra el destino
autorizado sin lanzarla.

- La lectura del candidato se hace sobre la base de inventario REAL de solo
  lectura (ruta absoluta segun __file__; el sandbox de conftest solo afecta
  rutas relativas al CWD).
- El mecanismo de registro (`insert_application_candidates` +
  `buscar_candidatos_registrados`) se verifica sobre una BD temporal para que
  la prueba sea repetible sin mutar la produccion.
- No se lanza ninguna aplicacion.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.hands.application_preflight import ApplicationPreflight, get_application_preflight
from src.hands.system_inventory import generate_machine_id
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
PROD_DB = ROOT_DIR / "data" / "system_inventory.sqlite3"
ENTIDADES_GLOBAL = ROOT_DIR / "data" / "memory" / "entities.json"

CANDIDATO_NOMBRE = "charmap.exe"            # Mapa de caracteres: herramienta del sistema inocua
NOMBRE_APPSFOLDER = "Mapa de caracteres"    # nombre real en shell:AppsFolder (Windows en espanol)
DESTINO_AUTORIZADO = r"C:\Windows\System32\charmap.exe"
MACHINE_ID = generate_machine_id()


def _crear_storage_con_scan(tmp_path) -> SystemInventoryStorage:
    """Crea una BD temporal, inicializa tablas y deja un scan_run listo (sin
    bloqueo de escaneo entre pruebas: cada prueba usa su propia BD y un solo
    conexion que se cierra al final)."""
    tmp_path = Path(tmp_path)
    db = tmp_path / "inventario_registro.sqlite3"
    storage = SystemInventoryStorage(db)
    storage.initialize()
    storage.record_machine(MACHINE_ID)
    conn = storage.connect()
    started = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at, "
        "finished_at, result, entries_count, errors_count, exclusions_count, "
        "coverage_estimate) VALUES (?,?,?,?,?,?,?,0,0,0,NULL)",
        ("scan-tmp-registro", MACHINE_ID, "C:", SCAN_MODE_FULL, started, started,
         SCAN_RESULT_OK),
    )
    conn.commit()
    return storage


def _leer_candidato_inventario_real():
    """Lee (solo lectura) la entrada de charmap.exe del inventario real."""
    conn = sqlite3.connect(str(PROD_DB))
    try:
        cur = conn.execute(
            "SELECT absolute_path, size_bytes, attributes, entry_type "
            "FROM file_entries WHERE name=? LIMIT 1",
            (CANDIDATO_NOMBRE,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _catalogo_global_no_registra(nombre):
    with open(ENTIDADES_GLOBAL, encoding="utf-8") as f:
        entidades = json.load(f)
    return nombre not in {str(e.get("name")) for e in entidades}


def _no_hay_proceso_charmap():
    import subprocess
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "Get-Process charmap -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
        capture_output=True, text=True, timeout=15,
    )
    return [x for x in r.stdout.splitlines() if x.strip()]


class TestInventarioRealLocalizaCandidatoInocuo:
    """El candidato proviene del inventario real y no esta registrado."""

    def test_existe_en_inventario_real(self):
        fila = _leer_candidato_inventario_real()
        assert fila is not None, "charmap.exe debe estar en el inventario real"
        ruta_inventario, tamano, atributos, tipo = fila
        assert tipo == "file"
        assert tamano and tamano > 0
        # El destino autorizado (resuelto por preflight) existe en disco real.
        assert os.path.isfile(DESTINO_AUTORIZADO), DESTINO_AUTORIZADO

    def test_no_esta_registrada_previamente(self):
        assert _catalogo_global_no_registra(CANDIDATO_NOMBRE)
        conn = sqlite3.connect(str(PROD_DB))
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM application_candidates WHERE name=?",
                (CANDIDATO_NOMBRE,),
            )
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()


class TestPreflightRealAutorizaSinLanzar:
    """ApplicationPreflight resuelve y autoriza el destino sin ejecutar la app."""

    def test_preflight_permitido_y_sin_proceso(self):
        assert _catalogo_global_no_registra(CANDIDATO_NOMBRE)
        assert _no_hay_proceso_charmap() == []

        pf = get_application_preflight()
        candidato = {
            "name": NOMBRE_APPSFOLDER,
            "app_id": _leer_candidato_inventario_real()[0],
            "login_required": None,
            "logged_in": None,
            "resources_available": True,
        }
        resultado = pf.check(candidato)

        assert resultado["allowed"] is True, resultado.get("reason")
        assert os.path.normcase(resultado["executable_path"]) == os.path.normcase(
            DESTINO_AUTORIZADO
        ), f"{resultado['executable_path']} != {DESTINO_AUTORIZADO}"
        assert resultado["requires_elevation"] is False
        assert resultado["blocked_by"] is None

        # Comprobacion de antes/despues: nunca se lanzo charmap.
        assert _no_hay_proceso_charmap() == []


class TestRegistroDestinoAutorizado:
    """El mecanismo de registro persiste y recupera el destino autorizado."""

    def _nuevo_candidato(self, candidate_id="cand-charmap-tmp"):
        return {
            "candidate_id": candidate_id,
            "scan_id": "scan-tmp-registro",
            "machine_id": MACHINE_ID,
            "volume": "C:",
            "name": "Mapa de caracteres",
            "absolute_path": DESTINO_AUTORIZADO,
            "launch_type": "ejecutable",
            "confidence": 0.9,
            "version": None,
            "producto": None,
            "evidencia": [{"origen": "application_preflight", "permitido": True}],
            "source": "inventory_preflight",
            "last_checked_at": "2026-01-01T00:00:00+00:00",
        }

    def test_insercion_y_recuperacion_bd_temporal(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _crear_storage_con_scan(tmp)
            try:
                insertados = storage.insert_application_candidates(
                    "scan-tmp-registro", MACHINE_ID, "C:", [self._nuevo_candidato()]
                )
                assert insertados == 1

                recuperados = storage.buscar_candidatos_registrados(
                    MACHINE_ID, limite=5
                )
                assert len(recuperados) == 1
                reg = recuperados[0]
                assert reg["absolute_path"] == DESTINO_AUTORIZADO
                assert reg["launch_type"] == "ejecutable"
                assert reg["confianza"] == 0.9
                assert reg["fuente"] == "inventory_preflight"
                assert isinstance(reg["evidencia"], list)
                assert reg["evidencia"][0]["permitido"] is True
            finally:
                storage.close()

    def test_no_duplica_candidato_mismo_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _crear_storage_con_scan(tmp)
            try:
                cand = self._nuevo_candidato()
                assert storage.insert_application_candidates(
                    "scan-tmp-registro", MACHINE_ID, "C:", [cand]
                ) == 1
                # Mismo candidate_id: la insercion debe fallar por unicidad.
                with pytest.raises(Exception):
                    storage.insert_application_candidates(
                        "scan-tmp-registro", MACHINE_ID, "C:", [cand]
                    )
            finally:
                storage.close()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
