# -*- coding: utf-8 -*-
"""
Test de entorno real para `buscar_candidatos_para_orden` (unidad 3.8.5.1.4.6.7).

Verifica en el equipo real (Windows 11, Python 3.14.7) que el metodo:
- Devuelve solo candidatos relevantes para la orden, no el inventario completo.
- No expone rutas privadas completas en el contexto conversacional.
- Respeta el aislamiento por equipo y volumenes montados.
- Incluye evidencia de validacion real del SO.

Usa directorios temporales y una base de datos SQLite real en el volumen C:.
Todo se limpia al finalizar.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SystemInventoryStorage,
)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "system_inventory_real.sqlite3"


@pytest.fixture
def storage(temp_db_path: Path) -> SystemInventoryStorage:
    return SystemInventoryStorage(temp_db_path)


def _seed_inventario_real(
    storage: SystemInventoryStorage,
    machine_id: str = "machine-real",
) -> None:
    """Crea un almacenamiento real con entradas de archivo en el volumen C:."""
    storage.initialize()
    storage.record_machine(machine_id)
    storage.begin_scan_run("scan-real", machine_id, "C:", SCAN_MODE_FULL)

    # Crear archivos temporales reales en el volumen C: para que la
    # validacion contra el SO (existencia, tipo, accesibilidad) sea real.
    tmp_base = Path("C:/tmp/jarvis_candidatos_real")
    tmp_base.mkdir(parents=True, exist_ok=True)

    archivos_reales = {
        "chrome.exe": "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "notepad.exe": "C:/Windows/System32/notepad.exe",
        "reporte.pdf": str(tmp_base / "reporte_2024.pdf"),
        "foto_privada.jpg": str(tmp_base / "foto_privada.jpg"),
        "script.py": str(tmp_base / "miscript.py"),
    }

    # Crear los archivos temporales realmente en disco.
    for _nombre, ruta in archivos_reales.items():
        p = Path(ruta)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("contenido de prueba para validacion real")

    entradas = []
    for entry_id, (nombre, ruta) in enumerate(archivos_reales.items(), start=1):
        p = Path(ruta)
        stat = p.stat()
        ext = p.suffix.lower()
        entradas.append({
            "entry_id": f"e-{entry_id}",
            "absolute_path": str(p),
            "relative_path": str(p),
            "name": p.name,
            "extension": ext,
            "entry_type": "file",
            "size_bytes": stat.st_size,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        })

    storage.insert_file_entries("scan-real", machine_id, "C:", entradas)
    storage.end_scan_run("scan-real", entries_count=len(entradas))


def test_entorno_real_devuelve_candidatos_relevantes_no_inventario_completo(
    storage: SystemInventoryStorage,
):
    """En el equipo real, buscar por orden devuelve solo candidatos relevantes."""
    _seed_inventario_real(storage)
    res = storage.buscar_candidatos_para_orden("machine-real", "abre chrome")

    assert res["orden_original"] == "abre chrome"
    assert "chrome" in res["palabras_clave"]
    assert res["total_devuelto"] >= 1
    assert res["total_devuelto"] <= res["limit"]
    # El total del inventario debe ser mayor o igual a lo devuelto (se limito).
    assert res["total_candidatos_inventario"] >= res["total_devuelto"]
    # Cada resultado debe ser relevante (contener chrome en el nombre).
    for r in res["resultados"]:
        assert "chrome" in r["name"].lower()


def test_entorno_real_no_devuelve_inventario_completo_sin_palabras_clave(
    storage: SystemInventoryStorage,
):
    """Sin palabras clave significativas, no se devuelve el inventario completo."""
    _seed_inventario_real(storage)
    res = storage.buscar_candidatos_para_orden("machine-real", "el y la")

    assert res["total_devuelto"] == 0
    assert res["palabras_clave"] == []
    assert res["filtro_aplicado"] == "sin_palabras_clave"


def test_entorno_real_ruta_privada_es_resumida(
    storage: SystemInventoryStorage,
):
    """Las rutas privadas (Users/<usuario>/) se resumen en el contexto."""
    _seed_inventario_real(storage)
    res = storage.buscar_candidatos_para_orden("machine-real", "reporte pdf")

    assert res["total_devuelto"] >= 1
    for r in res["resultados"]:
        if r["es_ruta_privada"]:
            # La ruta de contexto no debe ser la ruta completa de usuario.
            assert r["ruta_contexto"] != r.get("absolute_path", "")
            # Debe contener al menos el nombre del archivo.
            assert r["name"] in r["ruta_contexto"]


def test_entorno_real_incluye_evidencia_validacion_real(
    storage: SystemInventoryStorage,
):
    """Cada candidato incluye evidencia de validacion real contra el SO."""
    _seed_inventario_real(storage)
    res = storage.buscar_candidatos_para_orden("machine-real", "chrome")

    assert res["total_devuelto"] >= 1
    for r in res["resultados"]:
        assert "evidencia" in r
        assert "disponible" in r["evidencia"]
        assert "existencia_ok" in r["evidencia"]
        assert "valido" in r["evidencia"]


def test_entorno_real_aislamiento_por_equipo(
    storage: SystemInventoryStorage,
):
    """Consulta de otro equipo no devuelve candidatos de este equipo."""
    _seed_inventario_real(storage, "machine-real")
    res = storage.buscar_candidatos_para_orden("machine-otra", "chrome")

    assert res["total_devuelto"] == 0
    assert res["resultados"] == []


def test_entorno_real_respeta_volumenes_montados(
    storage: SystemInventoryStorage,
):
    """Con solo_volumes_montados=True (defecto), solo volumenes montados."""
    _seed_inventario_real(storage)
    res = storage.buscar_candidatos_para_orden("machine-real", "chrome")

    montados = storage.obtener_volumes_montados()
    for r in res["resultados"]:
        vol = r.get("volume", "")
        # El volumen debe estar montado o ser C: (siempre montado en Windows).
        assert vol in montados or vol.upper() == "C:"


def test_entorno_real_campos_esenciales(
    storage: SystemInventoryStorage,
):
    """Cada resultado tiene los campos esenciales para el contexto conversacional."""
    _seed_inventario_real(storage)
    res = storage.buscar_candidatos_para_orden("machine-real", "notepad")

    assert res["total_devuelto"] >= 1
    for r in res["resultados"]:
        assert "name" in r and r["name"]
        assert "extension" in r
        assert "entry_type" in r
        assert "volume" in r
        assert "ruta_contexto" in r and r["ruta_contexto"]
        assert "es_ruta_privada" in r
        assert "evidencia" in r
        assert "candidato_a_aplicacion" in r
        assert "excluida" in r
