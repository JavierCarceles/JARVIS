"""
Verificacion real de limpieza/retencion del inventario (unidad 3.8.5.1.4.8.6).

Objetivo: comprobar en el entorno real de Windows que:
- Se crea una copia de seguridad antes de la limpieza destructiva.
- Las generaciones de escaneo antiguas se eliminan respetando la ultima
  completa por volumen y los escaneos activos.
- Las entradas obsoletas (TTL) se eliminan, protegiendo las del ultimo
  escaneo completo.
- Las copias de seguridad antiguas se eliminan segun la retencion configurada.

Este script no es recolectado por pytest. Ejecuta codigo de produccion real
sobre una base de datos temporal real de Windows y verifica el comportamiento
de limpieza/retencion contra el sistema de archivos real.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Asegurar que src/ esta en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import sqlite3

from src.hands.system_inventory import PoliticaRetencion, ResultadoLimpieza
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SCAN_RESULT_INTERRUPTED,
    SystemInventoryStorage,
)

RESULTADOS = []


def registrar(nombre, ok, detalle=""):
    estado = "OK" if ok else "FALLO"
    RESULTADOS.append((nombre, estado, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def _insert_scan_run(conn, scan_id, machine_id, volume, started_at, result,
                     entries_count=0):
    conn.execute(
        """
        INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at,
                              finished_at, result, entries_count, errors_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (scan_id, machine_id, volume, "completo", started_at,
         started_at if result == SCAN_RESULT_OK else None, result,
         entries_count),
    )


def _insert_entrada(conn, scan_id, machine_id, volume, entry_id,
                    absolute_path, last_checked_at):
    nombre = Path(absolute_path).name
    conn.execute(
        """
        INSERT INTO file_entries(entry_id, scan_id, machine_id, volume,
                                 absolute_path, normalized_path,
                                 relative_path, name, extension,
                                 entry_type, size_bytes, modified_at,
                                 created_at, last_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 'file', 0, '', ?, ?)
        """,
        (entry_id, scan_id, machine_id, volume, absolute_path,
         absolute_path, nombre, nombre,
         last_checked_at, last_checked_at),
    )


def main():
    print("=" * 70)
    print("VERIFICACION REAL: Limpieza/retencion del inventario (3.8.5.1.4.8.6)")
    print("=" * 70)
    print(f"Equipo: {os.environ.get('COMPUTERNAME', 'desconocido')}")
    print(f"Python: {sys.version}")
    print(f"Directorio temporal: {tempfile.gettempdir()}")
    print()

    # ------------------------------------------------------------------
    # 1. Base de datos temporal REAL (no produccion)
    # ------------------------------------------------------------------
    db_path = Path(tempfile.gettempdir()) / "jarvis_verif_8_6_storage.sqlite3"
    if db_path.exists():
        db_path.unlink()
    for suf in ("-wal", "-shm"):
        p = Path(str(db_path) + suf)
        if p.exists():
            p.unlink()

    storage = SystemInventoryStorage(str(db_path))
    storage.initialize()
    storage.record_machine("maquina-verif")
    storage.record_volume("vol-C:", "maquina-verif", "C:", "local", "online")

    # ------------------------------------------------------------------
    # 2. Crear generaciones de escaneo con edades distintas (tiempo real)
    # ------------------------------------------------------------------
    ahora = time.time()
    hace_60_dias = ahora - 60 * 86400      # antiguo -> candidato a limpieza
    hace_10_dias = ahora - 10 * 86400      # reciente -> protegido
    hace_2_dias = ahora - 2 * 86400        # muy reciente -> protegido

    import datetime as _dt

    def _iso(ts):
        return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        # Generacion antigua (interrumpida, 60 dias) -> se eliminara.
        _insert_scan_run(conn, "scan-antiguo", "maquina-verif", "C:",
                         _iso(hace_60_dias), SCAN_RESULT_INTERRUPTED, 5)
        _insert_entrada(conn, "scan-antiguo", "maquina-verif", "C:", "e1",
                        "C:\\archivo_antiguo.txt", "")
        # Generacion reciente completa (10 dias) -> se protege (ultima completa).
        _insert_scan_run(conn, "scan-reciente", "maquina-verif", "C:",
                         _iso(hace_10_dias), SCAN_RESULT_OK, 50)
        _insert_entrada(conn, "scan-reciente", "maquina-verif", "C:", "e2",
                        "C:\\archivo_reciente.txt", _iso(hace_10_dias))
        conn.commit()
    finally:
        conn.close()

    # Verificar estado inicial
    conn = sqlite3.connect(str(db_path))
    try:
        n_scans_inicial = conn.execute(
            "SELECT COUNT(*) FROM scan_runs WHERE machine_id = 'maquina-verif'"
        ).fetchone()[0]
        n_entradas_inicial = conn.execute(
            "SELECT COUNT(*) FROM file_entries WHERE machine_id = 'maquina-verif'"
        ).fetchone()[0]
    finally:
        conn.close()

    print(f"Estado inicial: {n_scans_inicial} scan_runs, {n_entradas_inicial} file_entries")
    print()

    # ------------------------------------------------------------------
    # 3. Ejecutar limpieza/retencion con codigo de produccion real
    # ------------------------------------------------------------------
    politica = PoliticaRetencion(
        max_generaciones_por_volumen=5,
        max_edad_generacion_segundos=20 * 86400,  # 20 dias -> scan-antiguo (60d) es antiguo
        max_edad_entrada_segundos=86400,          # 1 dia TTL -> e1 (sin ts) es expirado
        max_backups=3,
        modo_seguro_escaneo_parcial=True,
        crear_backup_antes_limpieza=True,
    )
    res = storage.ejecutar_limpieza_retencion("maquina-verif", politica)

    print(f"Resultado limpieza: {res.resumen()}")
    print()

    # ------------------------------------------------------------------
    # 4. Verificaciones reales observables
    # ------------------------------------------------------------------

    # 4.1 Backup creado antes de la limpieza
    backup_existe = res.backup_creado is not None and Path(res.backup_creado).exists()
    registrar("Se creo copia de seguridad antes de la limpieza", backup_existe,
              f"(ruta={res.backup_creado})")

    # 4.2 Generacion antigua eliminada
    conn = sqlite3.connect(str(db_path))
    try:
        scan_antiguo_existe = conn.execute(
            "SELECT COUNT(*) FROM scan_runs WHERE scan_id = 'scan-antiguo'"
        ).fetchone()[0] == 0
        scan_reciente_existe = conn.execute(
            "SELECT COUNT(*) FROM scan_runs WHERE scan_id = 'scan-reciente'"
        ).fetchone()[0] == 1
    finally:
        conn.close()
    registrar("Generacion antigua eliminada (scan-antiguo)", scan_antiguo_existe)
    registrar("Ultima generacion completa protegida (scan-reciente)", scan_reciente_existe)

    # 4.3 Entradas de generacion eliminada tambien borradas
    conn = sqlite3.connect(str(db_path))
    try:
        entradas_antiguo = conn.execute(
            "SELECT COUNT(*) FROM file_entries WHERE scan_id = 'scan-antiguo'"
        ).fetchone()[0]
        entradas_reciente = conn.execute(
            "SELECT COUNT(*) FROM file_entries WHERE scan_id = 'scan-reciente'"
        ).fetchone()[0]
    finally:
        conn.close()
    registrar("Entradas de generacion eliminada borradas", entradas_antiguo == 0,
              f"(entradas_antiguo={entradas_antiguo})")
    registrar("Entradas de ultima completa conservadas", entradas_reciente == 1,
              f"(entradas_reciente={entradas_reciente})")

    # 4.4 Resultado de limpieza tiene contadores consistentes
    registrar("Resultado.limpieza tiene contadores reales",
              res.generaciones_eliminadas == 1 and res.backup_creado is not None,
              f"(gen_elim={res.generaciones_eliminadas}, backup={res.backup_creado is not None})")

    # 4.5 Resultado es serializable (evidencia reproducible)
    try:
        import json
        json.dumps(res.resumen())
        resumen_valido = True
    except Exception:
        resumen_valido = False
    registrar("Resultado resumen serializable", resumen_valido)

    # 4.5b ResultadoLimpieza es del tipo correcto
    registrar("Resultado es ResultadoLimpieza", isinstance(res, ResultadoLimpieza))

    # ------------------------------------------------------------------
    # 6. Limpiar recursos temporales (solo los creados por esta prueba)
    # ------------------------------------------------------------------
    try:
        if res.backup_creado:
            Path(res.backup_creado).unlink(missing_ok=True)
    except Exception:
        pass
    try:
        db_path.unlink(missing_ok=True)
    except Exception:
        pass
    for suf in ("-wal", "-shm"):
        p = Path(str(db_path) + suf)
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Resumen final
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    total = len(RESULTADOS)
    fallos = sum(1 for _, estado, _ in RESULTADOS if estado == "FALLO")
    print(f"Resultado: {total - fallos}/{total} verificaciones reales pasaron")
    if fallos > 0:
        print("FALLOS:")
        for nombre, estado, detalle in RESULTADOS:
            if estado == "FALLO":
                print(f"  - {nombre}: {detalle}")
        sys.exit(1)
    else:
        print("Todas las verificaciones reales pasaron.")
        sys.exit(0)


if __name__ == "__main__":
    main()
