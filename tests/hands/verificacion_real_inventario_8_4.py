# -*- coding: utf-8 -*-
"""
Verificación real de la unidad 3.8.5.1.4.8.4: protección de permisos, identidad
de equipo y no-exposición por red de la base de datos del inventario.

Ejecuta la implementación de producción sobre el equipo real (Windows) con
recursos temporales controlados en %TEMP%. No toca datos de producción.

No es recolectado por pytest (nombre sin prefijo test_ al final, ejecutado
manualmente como script de verificación real).
"""

from __future__ import annotations

import os
import sys
import shutil
import sqlite3
import stat
import tempfile
from pathlib import Path

# Asegurar que src/ y la raíz del proyecto estén en sys.path (equivalente a conftest).
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))          # .../tests/hands
_HANDS_DIR = os.path.dirname(_TESTS_DIR)                          # .../tests
_ROOT_DIR = os.path.dirname(_HANDS_DIR)                           # .../JARVIS (raíz del proyecto)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _path in (_SRC_DIR, _ROOT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src.hands.system_inventory_storage import (
    InventoryIncompatibleMachineError,
    PERMISOS_BASE_DE_DATOS,
    SystemInventoryStorage,
)
from src.hands.system_inventory import generate_machine_id


def main() -> int:
    maquina_actual = generate_machine_id()
    print(f"Equipo actual (machine_id): {maquina_actual}")
    print(f"Sistema: {os.name} | Python: {os.sys.version.split()[0]}")

    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis_real_8_4_"))
    try:
        db_path = temp_dir / "system_inventory.sqlite3"

        # ------------------------------------------------------------------
        # 1. Permisos de propietario único al crear la base de datos
        # ------------------------------------------------------------------
        print("\n--- 1. Permisos al crear base de datos nueva ---")
        storage = SystemInventoryStorage(db_path)
        version = storage.initialize()
        assert version == 5, f"Esperado esquema v5, obtuvo {version}"
        assert db_path.exists(), "El fichero de base de datos debe existir"

        modo_real = stat.S_IMODE(os.stat(db_path).st_mode)
        print(f"Modo de permisos real: {oct(modo_real)} (solicitado: {oct(PERMISOS_BASE_DE_DATOS)})")

        informe = storage.aplicar_permisos_privados(db_path)
        print(f"Informe de protección: {informe}")
        assert informe["error"] is None, f"Error aplicando permisos: {informe['error']}"

        if os.name != "nt":
            # En POSIX el modo debe ser exactamente 0o600.
            assert modo_real == PERMISOS_BASE_DE_DATOS, (
                f"Permisos inesperados: {oct(modo_real)} != {oct(PERMISOS_BASE_DE_DATOS)}"
            )
            print("POSIX: permisos 0o600 verificados (solo propietario).")
        else:
            # En Windows, os.chmod solo ajusta el atributo de solo lectura;
            # el informe debe indicar que se intentó aplicar protección.
            print("Windows: informe de protección generado sin error.")

        # ------------------------------------------------------------------
        # 2. Permisos no se reaplican de forma destructiva en base existente
        # ------------------------------------------------------------------
        print("\n--- 2. Re-inicialización sobre base existente ---")
        storage.initialize()  # no debe fallar ni borrar datos
        assert storage.schema_version() == 5
        print("Re-inicialización sobre base existente: OK (no hay regresión).")

        # ------------------------------------------------------------------
        # 3. Identidad de equipo: mismo equipo no bloquea
        # ------------------------------------------------------------------
        print("\n--- 3. Identidad de equipo: mismo equipo no bloquea ---")
        storage2 = SystemInventoryStorage(db_path)
        storage2.initialize(machine_id_actual=maquina_actual)
        print("Mismo equipo: inicialización permitida. OK.")

        # ------------------------------------------------------------------
        # 4. Identidad de equipo: equipo distinto se bloquea
        # ------------------------------------------------------------------
        print("\n--- 4. Identidad de equipo: equipo distinto se bloquea ---")
        maquina_otra = "equipo-otro-inexistente-8-4"
        storage3 = SystemInventoryStorage(db_path)
        storage3.initialize(machine_id_actual=maquina_otra)
        storage3.record_machine(maquina_otra)  # graba el equipo "otro" en la base
        try:
            storage3.initialize()  # sin machine_id_actual -> generate_machine_id() != maquina_otra
            print("ERROR: debería haber bloqueado el uso desde otro equipo.")
            return 1
        except InventoryIncompatibleMachineError as exc:
            print(f"Bloqueo correcto desde equipo distinto: {exc}")

        # ------------------------------------------------------------------
        # 5. permitir_otro_equipo=True evita el bloqueo (decisión explícita)
        # ------------------------------------------------------------------
        print("\n--- 5. Decisión explícita: permitir_otro_equipo=True ---")
        storage3.initialize(machine_id_actual=maquina_otra, permitir_otro_equipo=True)
        print("permitir_otro_equipo=True: inicialización permitida. OK.")

        # ------------------------------------------------------------------
        # 6. No exposición por red: ruta local
        # ------------------------------------------------------------------
        print("\n--- 6. No exposición por red: ruta local ---")
        informe_red = storage.verificar_no_exposicion_red()
        print(f"Informe de exposición (ruta local): {informe_red}")
        assert informe_red["es_local"] is True
        assert informe_red["es_unc"] is False
        assert informe_red["es_red"] is False
        print("Ruta local: no expuesta por red. OK.")

        # ------------------------------------------------------------------
        # 7. No exposición por red: ruta UNC
        # ------------------------------------------------------------------
        print("\n--- 7. No exposición por red: ruta UNC ---")
        db_unc_path = Path("\\\\servidor\\compartido\\inventario_8_4.sqlite3")
        storage_unc = SystemInventoryStorage(temp_dir / "local.sqlite3")
        storage_unc.db_path = db_unc_path  # solo para inspección del informe, no se crea en red
        informe_unc = storage_unc.verificar_no_exposicion_red()
        print(f"Informe de exposición (ruta UNC): {informe_unc}")
        assert informe_unc["es_unc"] is True
        assert informe_unc["es_red"] is True
        assert informe_unc["es_local"] is False
        print("Ruta UNC: marcada como expuesta por red. OK.")

        # ------------------------------------------------------------------
        # 8. Verificar que SQLite puede leerse/escribirse tras protección
        # ------------------------------------------------------------------
        print("\n--- 8. Lectura/escritura real sobre la base protegida ---")
        storage.record_machine(maquina_actual)
        storage.begin_scan_run("scan-real-8-4", maquina_actual, "C:", "completo")
        storage.insert_file_entries(
            "scan-real-8-4",
            maquina_actual,
            "C:",
            [
                {
                    "entry_id": "e-real-1",
                    "absolute_path": "C:/Windows/System32/notepad.exe",
                    "relative_path": "Windows/System32/notepad.exe",
                    "name": "notepad.exe",
                    "extension": ".exe",
                    "entry_type": "file",
                    "size_bytes": 100000,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "accessed_at": "2024-01-02T08:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                }
            ],
        )
        storage.end_scan_run("scan-real-8-4", entries_count=1, errors_count=0)
        run = storage.get_scan_run("scan-real-8-4")
        assert run is not None and run["result"] == "ok"
        count = storage.get_entry_count(maquina_actual, "C:")
        assert count == 1
        print(f"Lectura/escritura real: {count} entrada persistida y recuperada. OK.")

        print("\n=== TODAS LAS VERIFICACIONES REALES PASARON ===")
        return 0
    finally:
        # Limpieza exclusiva de recursos creados por esta prueba.
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"\nRecursos temporales limpiados: {temp_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
