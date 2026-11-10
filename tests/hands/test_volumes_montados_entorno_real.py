# -*- coding: utf-8 -*-
"""
Verificacion en el entorno real (Windows) de
SystemInventoryStorage con solo_volumes_montados (3.8.5.1.4.6.6).

Evita que una consulta de inventario devuelva rutas de volumenes que no
estan montados en el equipo actual.

Usa archivos temporales REALES en el volumen C: (montado), el identificador
real de equipo (generate_machine_id), un escaneo real y consultas reales
contra la base de datos SQLite. No usa mocks que decidan el resultado.
Cada valor se compara contra el estado observable del SO.

La unidad 3.8.5.1.4.6.6 exige evitar devolver rutas de volumenes no montados.
Este test comprueba que:
1. Las entradas de un volumen montado (C:) se devuelven con solo_volumes_montados=True.
2. Las entradas de un volumen no montado (Z:) NO se devuelven con solo_volumes_montados=True.
3. Con solo_volumes_montados=False se devuelven ambos (para comparacion).
4. obtener_volumes_montados() refleja los volumenes realmente montados del SO.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.hands.system_inventory import EntryType, generate_machine_id
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SystemInventoryStorage,
)

MACHINE_ID = generate_machine_id()


def _escaneo_con_entradas_reales(
    storage: SystemInventoryStorage, tmp_path: Path
) -> dict[str, object]:
    """Crea objetos reales en el volumen y los registra en un escaneo real."""
    storage.initialize()
    storage.record_machine(MACHINE_ID)
    storage.begin_scan_run("scan-real-montados", MACHINE_ID, "C:", SCAN_MODE_FULL)

    carpeta = tmp_path / "jarvis_real_montados"
    carpeta.mkdir()

    # Objeto real en C: (volumen montado).
    archivo_real = carpeta / "app_real.exe"
    archivo_real.write_bytes(b"MZplaceholder")

    # Volumen real donde reside el archivo (C: en Windows).
    volumen_real = os.path.splitdrive(str(archivo_real))[0] or "C:"

    entradas = [
        {
            "entry_id": "e-real-c-exe",
            "absolute_path": str(archivo_real).replace("\\", "/"),
            "relative_path": "jarvis_real_montados/app_real.exe",
            "name": archivo_real.name,
            "extension": ".exe",
            "entry_type": EntryType.FILE.value,
            "size_bytes": archivo_real.stat().st_size,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        },
        # Entrada de un volumen que no esta montado en este equipo (Z:).
        # Simula una entrada heredada de otro host o unidad desconectada.
        {
            "entry_id": "e-heredado-z-exe",
            "absolute_path": "Z:/Remoto/heredado.exe",
            "relative_path": "Remoto/heredado.exe",
            "name": "heredado.exe",
            "extension": ".exe",
            "entry_type": EntryType.FILE.value,
            "size_bytes": 5000,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        },
    ]

    storage.insert_file_entries("scan-real-montados", MACHINE_ID, volumen_real, [entradas[0]])
    # La entrada de Z: se registra con volumen Z: (no montado en este equipo).
    storage.insert_file_entries("scan-real-montados", MACHINE_ID, "Z:", [entradas[1]])
    storage.end_scan_run("scan-real-montados", entries_count=len(entradas))
    return {
        "archivo": archivo_real,
        "volumen": volumen_real,
    }


def test_volumes_montados_entorno_real_devuelve_solo_montados():
    """search con solo_volumes_montados=True devuelve solo C:, no Z:."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_montados_real.sqlite3")
        try:
            objetos = _escaneo_con_entradas_reales(storage, tmp_path)

            # Consultar sin filtro de volumen montado: debe devolver ambos.
            todos = storage.search(
                MACHINE_ID, solo_volumes_montados=False
            )
            nombres_todos = {e["name"] for e in todos}
            assert "app_real.exe" in nombres_todos
            assert "heredado.exe" in nombres_todos

            # Consultar con filtro de volumen montado: solo C:.
            montados = storage.search(
                MACHINE_ID, solo_volumes_montados=True
            )
            nombres_montados = {e["name"] for e in montados}
            assert "app_real.exe" in nombres_montados
            assert "heredado.exe" not in nombres_montados

            # Cada entrada devuelta debe tener un volumen montado.
            volumes_montados = storage.obtener_volumes_montados()
            for e in montados:
                assert any(
                    e["volume"].upper() == v.upper() for v in volumes_montados
                ), f"Volumen {e['volume']!r} no esta en volumenes montados: {volumes_montados}"

            # Buscar específicamente Z: con filtro montado -> vacio.
            solo_z = storage.search(
                MACHINE_ID, volume="Z:", solo_volumes_montados=True
            )
            assert solo_z == []

            # count con filtro montado: solo las entradas de C:.
            count_montados = storage.count(
                MACHINE_ID, solo_volumes_montados=True
            )
            count_todos = storage.count(
                MACHINE_ID, solo_volumes_montados=False
            )
            assert count_montados == 1
            assert count_todos == 2

        finally:
            storage.close()


def test_obtener_volumes_montados_entorno_real_coincide_con_psutil():
    """obtener_volumes_montados() refleja los volumenes realmente montados."""
    import psutil

    storage = SystemInventoryStorage(":memory:")
    try:
        montados_jarvis = storage.obtener_volumes_montados()
        montados_psutil = set()
        for particion in psutil.disk_partitions(all=False):
            punto = particion.mountpoint or ""
            if not punto:
                continue
            if os.name == "nt":
                drive = os.path.splitdrive(punto)[0]
                if drive:
                    montados_psutil.add(drive.upper())
                else:
                    montados_psutil.add(punto.upper())
            else:
                montados_psutil.add(punto)

        # C: debe estar en ambos conjuntos.
        assert "C:" in montados_jarvis, f"C: no esta en {montados_jarvis}"
        assert "C:" in montados_psutil, f"C: no esta en {montados_psutil}"

        # Los conjuntos deben ser equivalentes (al menos para unidades de letra).
        for v in montados_jarvis:
            assert v in montados_psutil, (
                f"Volumen {v!r} detectado por JARVIS pero no por psutil: {montados_psutil}"
            )
    finally:
        storage.close()


def test_search_paginated_entorno_real_solo_montados():
    """search_paginated con solo_volumes_montados=True excluye Z:."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_pag_real.sqlite3")
        try:
            _escaneo_con_entradas_reales(storage, tmp_path)

            pagina = storage.search_paginated(
                MACHINE_ID, solo_volumes_montados=True, limit=10, offset=0
            )
            nombres = {e["name"] for e in pagina["results"]}
            assert "app_real.exe" in nombres
            assert "heredado.exe" not in nombres
            assert pagina["total"] == 1
        finally:
            storage.close()


if __name__ == "__main__":
    test_volumes_montados_entorno_real_devuelve_solo_montados()
    test_obtener_volumes_montados_entorno_real_coincide_con_psutil()
    test_search_paginated_entorno_real_solo_montados()
    print("VOLUMES MONTADOS ENTORNO REAL (3.8.5.1.4.6.6): OK")
