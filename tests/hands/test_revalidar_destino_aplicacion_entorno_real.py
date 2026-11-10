# -*- coding: utf-8 -*-
"""
Verificacion en el entorno real (Windows) de
SystemInventoryStorage.revalidar_destino_aplicacion (3.8.5.1.4.6.5).

Usa archivos y carpetas temporales REALES en un volumen montado del
equipo, el identificador real de equipo (generate_machine_id), una
ejecucion de escaneo real y la validacion real contra el sistema
operativo (revalidar_destino_aplicacion). No usa mocks que decidan
el resultado; cada valor se compara contra el estado observable del SO.

La unidad 3.8.5.1.4.6.5 exige revalidar la existencia y el tipo del
destino ANTES de cualquier operacion de apertura; el inventario nunca
es una autorizacion para ejecutar. Este test comprueba que la
revalidacion ocurre realmente contra el SO y que un destino inexistente
o un directorio no se considera valido para abrir.
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
    storage.begin_scan_run("scan-real", MACHINE_ID, "C:", SCAN_MODE_FULL)

    carpeta = tmp_path / "jarvis_real_revalidar"
    carpeta.mkdir()

    ejecutable_real = carpeta / "app_real.exe"
    ejecutable_real.write_bytes(b"MZplaceholder")

    carpeta_real = carpeta / "subcarpeta_real"
    carpeta_real.mkdir()

    volumen = os.path.splitdrive(str(ejecutable_real))[0] or "C:"

    entradas = [
        {
            "entry_id": "e-real-exe",
            "absolute_path": str(ejecutable_real),
            "relative_path": "jarvis_real_revalidar/app_real.exe",
            "name": ejecutable_real.name,
            "extension": ".exe",
            "entry_type": EntryType.FILE.value,
            "size_bytes": ejecutable_real.stat().st_size,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        },
        {
            "entry_id": "e-real-dir",
            "absolute_path": str(carpeta_real),
            "relative_path": "jarvis_real_revalidar/subcarpeta_real",
            "name": carpeta_real.name,
            "extension": "",
            "entry_type": EntryType.DIRECTORY.value,
            "size_bytes": 0,
            "modified_at": "2024-02-01T10:00:00",
            "created_at": "2024-02-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-02-03T00:00:00",
        },
    ]

    storage.insert_file_entries("scan-real", MACHINE_ID, volumen, entradas)
    storage.end_scan_run("scan-real", entries_count=len(entradas))
    return {
        "ejecutable": ejecutable_real,
        "carpeta": carpeta_real,
        "volumen": volumen,
    }


def test_revalidar_destino_aplicacion_entorno_real_valido():
    """Revalidacion real de un ejecutable existente: valido para abrir."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_real.sqlite3")
        objetos = _escaneo_con_entradas_reales(storage, tmp_path)

        try:
            ruta = str(objetos["ejecutable"]).replace("\\", "/")
            volumen = str(objetos["volumen"])
            resultado = storage.revalidar_destino_aplicacion(
                MACHINE_ID, volumen, ruta
            )

            assert resultado["valido"] is True
            assert resultado["existe"] is True
            assert resultado["es_archivo"] is True
            assert resultado["ruta"] == ruta
            assert resultado["normalized_path"]
            assert resultado["entradas_refrescadas"] == 1
            assert resultado["razon"] is None
            assert resultado["machine_id"] == MACHINE_ID
            assert resultado["volume"] == volumen
            assert resultado["last_checked_at"] is not None
        finally:
            storage.close()


def test_revalidar_destino_aplicacion_entorno_real_no_existe():
    """Revalidacion real de una ruta inexistente: no es valida para abrir."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_real.sqlite3")
        _escaneo_con_entradas_reales(storage, tmp_path)

        try:
            ruta_inexistente = str(
                tmp_path / "no_existe" / "sub" / "fantasma.exe"
            ).replace("\\", "/")
            resultado = storage.revalidar_destino_aplicacion(
                MACHINE_ID, "C:", ruta_inexistente
            )

            assert resultado["valido"] is False
            assert resultado["existe"] is False
            assert resultado["es_archivo"] is False
            assert resultado["razon"] is not None
            assert "no existe" in resultado["razon"]
        finally:
            storage.close()


def test_revalidar_destino_aplicacion_entorno_real_directorio():
    """Revalidacion real de un directorio: existe pero no es archivo lanzable."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_real.sqlite3")
        objetos = _escaneo_con_entradas_reales(storage, tmp_path)

        try:
            ruta = str(objetos["carpeta"]).replace("\\", "/")
            resultado = storage.revalidar_destino_aplicacion(
                MACHINE_ID, "C:", ruta
            )

            assert resultado["valido"] is False
            assert resultado["existe"] is True
            assert resultado["es_archivo"] is False
            assert resultado["razon"] is not None
            assert "no es un archivo lanzable" in resultado["razon"]
        finally:
            storage.close()


def test_revalidar_destino_aplicacion_entorno_real_vacio():
    """Ruta vacia: la revalidacion rechaza con razon sin tocar el disco."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_real.sqlite3")
        storage.initialize()
        storage.record_machine(MACHINE_ID)

        try:
            resultado = storage.revalidar_destino_aplicacion(
                MACHINE_ID, "C:", ""
            )

            assert resultado["valido"] is False
            assert resultado["existe"] is False
            assert resultado["es_archivo"] is False
            assert resultado["razon"] is not None
        finally:
            storage.close()


if __name__ == "__main__":
    test_revalidar_destino_aplicacion_entorno_real_valido()
    test_revalidar_destino_aplicacion_entorno_real_no_existe()
    test_revalidar_destino_aplicacion_entorno_real_directorio()
    test_revalidar_destino_aplicacion_entorno_real_vacio()
    print("REVALIDAR DESTINO ENTORNO REAL (3.8.5.1.4.6.5): OK")
