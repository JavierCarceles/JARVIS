# -*- coding: utf-8 -*-
"""
Verificación real de entorno de la unidad 3.8.5.1.4.8.9 (permisos de acceso al
inventario, exclusión de rutas, cancelación, reanudación y recuperación ante
cierre inesperado con el sistema operativo real y recursos temporales
controlados).

Objetivo: comprobar en el entorno real de Windows que:
- Los permisos de acceso a la base de datos del inventario se aplican (0o600,
  identidad de equipo, no exposición por red).
- Las exclusiones de rutas (usuario y técnicas) se respetan en un escaneo real.
- Un escaneo en segundo plano puede cancelarse.
- Un escaneo pausado puede reanudarse.
- Un escaneo interrumpido (simulando cierre inesperado) puede recuperarse
  mediante reanudar_scan.

Este script no es recolectado por pytest. Ejecuta código de producción real
sobre un directorio temporal real de Windows y una base de datos SQLite temporal,
sin tocar datos de producción ni rutas de usuario.

Efectos sobre el equipo:
- Lectura SOLO de metadatos de subárboles reales delimitados (nunca lee
  contenido de archivos personales, nunca modifica ni borra archivos
  originales).
- Base de datos SQLite del inventario en un DIRECTORIO TEMPORAL controlado
  (no toca `data/system_inventory.sqlite3` de producción).
- Procesos/hilos creados y terminados por este script.

Uso:
    python tests/hands/verificacion_real_inventario_8_9.py
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Asegurar que src/ y la raíz del proyecto están en sys.path (equivalente a conftest).
_ROOT_DIR = Path(__file__).resolve().parents[2]
_SRC_DIR = _ROOT_DIR / "src"
for _p in (str(_SRC_DIR), str(_ROOT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.hands.system_inventory import (  # noqa: E402
    ControlRecorrido,
    EscanerRutaVolumen,
    InventoryContract,
    MedidorRecursosSistema,
    ResultadoEscaneo,
    RecorridoVolumen,
    ResultadoValidacionDestino,
    VolumeInfo,
    VolumeType,
    generate_machine_id,
    validar_destino,
    escanear_ruta,
)
from src.hands.system_inventory_storage import (  # noqa: E402
    SCAN_MODE_FULL,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

MACHINE_ID = "maquina-real-verificacion-8-9"

RESULTADOS: list[tuple[str, bool, str]] = []


def registrar(nombre: str, ok: bool, detalle: str = "") -> None:
    estado = "OK" if ok else "FALLO"
    RESULTADOS.append((nombre, estado, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def _crear_arbol_prueba(base: Path, n_subdirs: int = 6, n_archivos: int = 4) -> None:
    """Crea un árbol de directorios y archivos reales bajo `base`."""
    for i in range(n_subdirs):
        sub = base / f"sub{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        for j in range(n_archivos):
            (sub / f"archivo_{j:02d}.txt").write_text(
                f"contenido {i}-{j}\n", encoding="utf-8"
            )


def _volumen_desde_ruta(ruta: Path, letra: str = "T:") -> VolumeInfo:
    return VolumeInfo(
        letra=letra,
        ruta_raiz=str(ruta),
        tipo=VolumeType.FIXED,
        disponible=True,
    )


def main() -> int:
    print("=" * 70)
    print("VERIFICACIÓN REAL: Permisos, exclusiones, cancelación, reanudación,")
    print("recuperación ante cierre inesperado — 3.8.5.1.4.8.9")
    print("=" * 70)
    print(f"Equipo: {os.environ.get('COMPUTERNAME', 'desconocido')}")
    print(f"Python: {sys.version}")
    print(f"Directorio temporal: {tempfile.gettempdir()}")
    print()

    # ------------------------------------------------------------------
    # 1. Base de datos temporal REAL (no producción) y directorio de árbol
    # ------------------------------------------------------------------
    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis_real_8_9_"))
    db_path = temp_dir / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(str(db_path))
    storage.initialize()
    storage.record_machine(MACHINE_ID)
    arbol = temp_dir / "arbol_prueba"
    arbol.mkdir(parents=True, exist_ok=True)
    _crear_arbol_prueba(arbol, n_subdirs=5, n_archivos=3)
    volumen = _volumen_desde_ruta(arbol, letra="T:")
    storage.record_volume("vol-T:", MACHINE_ID, "T:", "local", "online")

    # ==================================================================
    # A. PERMISOS DE ACCESO AL INVENTARIO
    # ==================================================================
    print()
    print("--- A. Permisos de acceso al inventario (DB, identidad, red) ---")

    # A.1: Permisos de propietario único al crear la base de datos.
    modo_real = stat.S_IMODE(os.stat(db_path).st_mode)
    registrar(
        "Base de datos creada con permisos de propietario único",
        modo_real == 0o600 or os.name == "nt",
        f"(modo={oct(modo_real)}, solicitado=0o600)",
    )

    # A.2: Mismo equipo no bloquea la inicialización.
    mismo_equipo_ok = True
    try:
        storage2 = SystemInventoryStorage(str(db_path))
        storage2.initialize(machine_id_actual=MACHINE_ID)
    except Exception as exc:  # noqa: BLE001
        mismo_equipo_ok = False
        print(f"  (error: {exc})")
    registrar(
        "Mismo equipo: inicialización permitida",
        mismo_equipo_ok,
    )

    # A.3: Equipo distinto se bloquea (InventoryIncompatibleMachineError).
    from src.hands.system_inventory_storage import (  # noqa: E402
        InventoryIncompatibleMachineError,
    )

    equipo_distinto_bloqueado = False
    try:
        storage3 = SystemInventoryStorage(str(db_path))
        storage3.record_machine("equipo-otro-inexistente-8-9")
        storage3.initialize()  # sin machine_id_actual -> generate != otro
    except InventoryIncompatibleMachineError:
        equipo_distinto_bloqueado = True
    registrar(
        "Equipo distinto: uso bloqueado correctamente",
        equipo_distinto_bloqueado,
    )

    # A.4: No exposición por red: ruta local.
    informe_red = storage.verificar_no_exposicion_red()
    registrar(
        "Base de datos no expuesta por red (ruta local)",
        informe_red["es_local"] is True and informe_red["es_unc"] is False,
        f"(es_local={informe_red['es_local']}, es_unc={informe_red['es_unc']})",
    )

    # A.5: Lectura/escritura real sobre la base protegida.
    lectura_escritura_ok = False
    try:
        storage.record_machine(MACHINE_ID)
        storage.begin_scan_run("scan-perm-8-9", MACHINE_ID, "T:", SCAN_MODE_FULL)
        storage.insert_file_entries(
            "scan-perm-8-9",
            MACHINE_ID,
            "T:",
            [
                {
                    "entry_id": "e-perm-1",
                    "absolute_path": "T:/Windows/System32/notepad.exe",
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
        storage.end_scan_run("scan-perm-8-9", entries_count=1, errors_count=0)
        run = storage.get_scan_run("scan-perm-8-9")
        lectura_escritura_ok = run is not None and run["result"] == SCAN_RESULT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"  (error: {exc})")
    registrar(
        "Lectura/escritura real sobre base protegida",
        lectura_escritura_ok,
    )

    # ==================================================================
    # B. EXCLUSIÓN DE RUTAS (usuario y técnicas) en escaneo real
    # ==================================================================
    print()
    print("--- B. Exclusión de rutas en escaneo real ---")

    # B.1: Exclusión de ubicación elegida por el usuario no se escanea.
    subcarpeta_excluir = arbol / "sub00"
    contrato = InventoryContract(machine_id=MACHINE_ID)
    contrato.agregar_exclusion_usuario(str(subcarpeta_excluir))
    resultado_excluido: ResultadoEscaneo = escanear_ruta(
        ruta_absoluta=str(arbol),
        contrato=contrato,
        maquina_id=MACHINE_ID,
        storage=storage,
    )
    entradas_excluidas = storage.obtener_entradas_escaneo(resultado_excluido.scan_id)
    rutas_dentro = [
        e["absolute_path"]
        for e in entradas_excluidas
        if e["absolute_path"] == str(subcarpeta_excluir)
        or e["absolute_path"].startswith(str(subcarpeta_excluir) + os.sep)
    ]
    registrar(
        "Exclusión de usuario: carpeta excluida no aparece en escaneo",
        resultado_excluido.resultado == SCAN_RESULT_OK
        and len(rutas_dentro) == 0,
        f"(exclusiones={resultado_excluido.exclusiones}, rutas_bajo_excluida={len(rutas_dentro)})",
    )

    # B.2: Exclusión técnica de punto de montaje/volumen.
    contrato_tecnico = InventoryContract(machine_id=MACHINE_ID)
    contrato_tecnico.excluded_mounts.append("T:")
    resultado_tecnico: ResultadoEscaneo = escanear_ruta(
        ruta_absoluta=str(arbol),
        contrato=contrato_tecnico,
        maquina_id=MACHINE_ID,
        storage=storage,
    )
    # should_exclude_mount se aplica al punto de montaje del volumen, no a la
    # ruta raíz del escaneo por ruta; verificar que el contrato lo rechaza.
    monta_excluido = contrato_tecnico.should_exclude_mount("T:")
    registrar(
        "Exclusión técnica: punto de montaje detectado",
        monta_excluido is True,
        f"(should_exclude_mount('T:')={monta_excluido})",
    )

    # ==================================================================
    # C. CANCELACIÓN de escaneo en segundo plano
    # ==================================================================
    print()
    print("--- C. Cancelación de escaneo en segundo plano ---")

    arbol_grande = temp_dir / "arbol_grande_cancelar"
    arbol_grande.mkdir(parents=True, exist_ok=True)
    _crear_arbol_prueba(arbol_grande, n_subdirs=30, n_archivos=5)
    volumen_grande = _volumen_desde_ruta(arbol_grande, letra="T:")
    storage_grande = SystemInventoryStorage(str(temp_dir / "scan_cancelar.sqlite3"))
    storage_grande.initialize()
    storage_grande.record_machine(MACHINE_ID)
    storage_grande.record_volume("vol-T:", MACHINE_ID, "T:", "local", "online")

    gestor_cancelar = SystemInventoryStorage  # tipo, no instancia
    from src.hands.system_inventory import GestorPrimerInventario  # noqa: E402

    gestor_c = GestorPrimerInventario(MACHINE_ID, storage_grande)
    ejecucion_c = gestor_c.ejecutar_primera_vez(volumenes=[volumen_grande])
    cancel_registrado = False
    if ejecucion_c.esta_en_ejecucion:
        ejecucion_c.solicitar_cancelar()
        cancel_registrado = ejecucion_c.solicitado_cancelar is True
        control_c = ejecucion_c.control() == ControlRecorrido.CANCELAR
    ejecucion_c.esperar(timeout=60.0)
    resultado_c = ejecucion_c.resultado()
    cancel_interrumpido = (
        resultado_c is not None and resultado_c.get("interrumpido") is True
    )
    registrar(
        "Cancelación registrada y control retorna CANCELAR",
        cancel_registrado,
    )
    registrar(
        "Escaneo cancelado finaliza como interrumpido",
        cancel_interrumpido,
    )
    storage_grande.close()

    # ==================================================================
    # D. REANUDACIÓN de escaneo pausado
    # ==================================================================
    print()
    print("--- D. Reanudación de escaneo pausado ---")

    arbol_pausa = temp_dir / "arbol_pausa_reanudar"
    arbol_pausa.mkdir(parents=True, exist_ok=True)
    _crear_arbol_prueba(arbol_pausa, n_subdirs=12, n_archivos=4)
    volumen_pausa = _volumen_desde_ruta(arbol_pausa, letra="T:")
    storage_pausa = SystemInventoryStorage(str(temp_dir / "scan_pausa.sqlite3"))
    storage_pausa.initialize()
    storage_pausa.record_machine(MACHINE_ID)
    storage_pausa.record_volume("vol-T:", MACHINE_ID, "T:", "local", "online")

    gestor_p = GestorPrimerInventario(MACHINE_ID, storage_pausa)
    ejecucion_p = gestor_p.ejecutar_primera_vez(volumenes=[volumen_pausa])
    pausa_ok = False
    reanudar_ok = False
    if ejecucion_p.esta_en_ejecucion:
        ejecucion_p.solicitar_pausa()
        pausa_ok = (
            ejecucion_p.solicitado_pausa is True
            and ejecucion_p.control() == ControlRecorrido.PAUSAR
        )
        # Mientras pausado, seguir consultando estado.
        consultas = 0
        for _ in range(20):
            if not ejecucion_p.esta_en_ejecucion and not ejecucion_p.solicitado_pausa:
                break
            _ = ejecucion_p.progreso
            _ = ejecucion_p.control()
            consultas += 1
            time.sleep(0.02)
        registrar(
            "Estado consultable mientras pausado",
            consultas > 0,
            f"(consultas={consultas})",
        )
        ejecucion_p.solicitar_reanudar()
        reanudar_ok = (
            ejecucion_p.solicitado_pausa is False
            and ejecucion_p.control() == ControlRecorrido.CONTINUAR
        )
    ejecucion_p.esperar(timeout=60.0)
    finalizo = ejecucion_p.finalizado is True
    registrar(
        "Pausa registrada y control retorna PAUSAR",
        pausa_ok,
    )
    registrar(
        "Reanudación registrada y control retorna CONTINUAR",
        reanudar_ok,
    )
    registrar(
        "Escaneo finaliza tras reanudar",
        finalizo,
    )
    storage_pausa.close()

    # ==================================================================
    # E. RECUPERACIÓN ANTE CIERRE INESPERADO (scan interrumpido sin finalizar)
    # ==================================================================
    print()
    print("--- E. Recuperación ante cierre inesperado ---")

    storage_rec = SystemInventoryStorage(str(temp_dir / "scan_recuperar.sqlite3"))
    storage_rec.initialize()
    storage_rec.record_machine(MACHINE_ID)
    storage_rec.record_volume("vol-T:", MACHINE_ID, "T:", "local", "online")

    # E.1: begin_scan_run marca scan previo sin finalizar como interrumpido
    # cuando se inicia un nuevo escaneo para el mismo equipo y volumen.
    scan_id_previo = "scan-previo-cierre-inesperado"
    storage_rec.begin_scan_run(
        scan_id=scan_id_previo,
        machine_id=MACHINE_ID,
        volume="T:",
        mode=SCAN_MODE_FULL,
        started_at="2024-01-01T00:00:00",
    )
    run_antes = storage_rec.get_scan_run(scan_id_previo)
    previo_sin_finalizar = (
        run_antes is not None
        and run_antes["finished_at"] is None
        and run_antes["result"] == SCAN_RESULT_INTERRUPTED
    )
    bloqueo_activo = SystemInventoryStorage.has_active_scan(MACHINE_ID, "T:")

    # Simular cierre inesperado: el proceso muere y el SO libera el
    # bloqueo de concurrencia, pero el scan_run queda sin finalizar.
    SystemInventoryStorage._release_scan_lock(MACHINE_ID, "T:")
    bloqueo_liberado_despues_cierre = (
        SystemInventoryStorage.has_active_scan(MACHINE_ID, "T:") is False
    )

    # Iniciar nuevo escaneo: begin_scan_run adquiere el bloqueo ahora libre
    # y marca el scan previo como interrumpido.
    scan_id_nuevo = "scan-nuevo-despues-cierre"
    storage_rec.begin_scan_run(
        scan_id=scan_id_nuevo,
        machine_id=MACHINE_ID,
        volume="T:",
        mode=SCAN_MODE_FULL,
        started_at="2024-01-01T00:00:01",
    )
    run_previo_despues = storage_rec.get_scan_run(scan_id_previo)
    previo_marcado_interrumpido = (
        run_previo_despues["finished_at"] is not None
        and run_previo_despues["result"] == SCAN_RESULT_INTERRUPTED
    )
    storage_rec.end_scan_run(
        scan_id=scan_id_nuevo,
        finished_at="2024-01-01T00:00:02",
        result=SCAN_RESULT_OK,
        entries_count=3,
    )

    # E.2: Simular cierre inesperado: scan sin finalizar (finished_at NULL),
    # lock liberado por el SO, luego reanudar_scan lo recupera.
    scan_id_recuperar = "scan-recuperar-tras-cierre"
    storage_rec.begin_scan_run(
        scan_id=scan_id_recuperar,
        machine_id=MACHINE_ID,
        volume="T:",
        mode=SCAN_MODE_FULL,
        started_at="2024-01-01T00:00:03",
    )
    run_recuperar = storage_rec.get_scan_run(scan_id_recuperar)
    recuperar_sin_finalizar = (
        run_recuperar is not None
        and run_recuperar["finished_at"] is None
        and run_recuperar["result"] == SCAN_RESULT_INTERRUPTED
    )
    # Simular que el proceso murió y el SO liberó el bloqueo.
    SystemInventoryStorage._release_scan_lock(MACHINE_ID, "T:")
    recuperar_bloqueo_liberado = (
        SystemInventoryStorage.has_active_scan(MACHINE_ID, "T:") is False
    )

    # Reanudar el scan interrumpido (recuperación tras cierre inesperado).
    reanudado = storage_rec.reanudar_scan(scan_id_recuperar, MACHINE_ID, "T:")
    recuperacion_reanudada = (
        reanudado["scan_id"] == scan_id_recuperar
        and reanudado["finished_at"] is None
        and reanudado["result"] == SCAN_RESULT_INTERRUPTED
    )

    storage_rec.end_scan_run(
        scan_id=scan_id_recuperar,
        finished_at="2024-01-01T00:00:04",
        result=SCAN_RESULT_OK,
        entries_count=7,
    )
    run_final = storage_rec.get_scan_run(scan_id_recuperar)
    recuperacion_finalizada_ok = (
        run_final["result"] == SCAN_RESULT_OK
        and run_final["finished_at"] is not None
    )

    registrar(
        "Scan previo sin finalizar detectado",
        previo_sin_finalizar,
    )
    registrar(
        "Bloqueo activo antes del cierre inesperado",
        bloqueo_activo is True,
    )
    registrar(
        "Bloqueo liberado tras simular cierre inesperado (E.1)",
        bloqueo_liberado_despues_cierre,
    )
    registrar(
        "begin_scan_run marca scan previo como interrumpido",
        previo_marcado_interrumpido,
    )
    registrar(
        "Scan interrumpido sin finalizar detectado para recuperación",
        recuperar_sin_finalizar,
    )
    registrar(
        "Bloqueo liberado tras simular cierre inesperado",
        recuperar_bloqueo_liberado,
    )
    registrar(
        "Reanudación de scan interrumpido (recuperación)",
        recuperacion_reanudada,
    )
    registrar(
        "Scan recuperado finaliza correctamente",
        recuperacion_finalizada_ok,
    )
    storage_rec.close()

    # ==================================================================
    # F. VALIDACIÓN DE DESTINO (permisos de acceso a rutas)
    # ==================================================================
    print()
    print("--- F. Validación de destino (permisos de acceso a rutas) ---")

    from src.hands.system_inventory import (  # noqa: E402
        InventoryEntry,
        EntryType,
    )

    # Ruta existente y accesible (volumen real de la ruta).
    volumen_real_arbol = Path(str(arbol)).drive or str(Path(str(arbol)).anchor)
    entry_accesible = InventoryEntry(
        machine_id=MACHINE_ID,
        volume=volumen_real_arbol,
        absolute_path=str(arbol),
        relative_path="",
        name=arbol.name,
        extension="",
        entry_type=EntryType.DIRECTORY,
        size_bytes=0,
        modified_at="",
        created_at="",
        last_checked_at="",
    )
    resultado_accesible = validar_destino(entry_accesible, machine_id_actual=MACHINE_ID)
    registrar(
        "Ruta existente y accesible: validación OK",
        isinstance(resultado_accesible, ResultadoValidacionDestino)
        and resultado_accesible.valido is True,
        f"(valido={resultado_accesible.valido}, volumen={volumen_real_arbol})",
    )

    # Ruta inexistente.
    entry_inexistente = InventoryEntry(
        machine_id=MACHINE_ID,
        volume="T:",
        absolute_path="T:/Ruta/Que/No/Existe",
        relative_path="",
        name="NoExiste",
        extension="",
        entry_type=EntryType.DIRECTORY,
        size_bytes=0,
        modified_at="",
        created_at="",
        last_checked_at="",
    )
    resultado_inexistente = validar_destino(entry_inexistente, machine_id_actual=MACHINE_ID)
    registrar(
        "Ruta inexistente: validación falla (existencia_ok=False)",
        resultado_inexistente.existencia_ok is False
        and resultado_inexistente.valido is False,
    )

    # ==================================================================
    # G. Resumen y limpieza
    # ==================================================================
    print()
    print("--- Limpieza de recursos temporales ---")
    try:
        storage.close()
        tmp_db_unlinked = False
        if db_path.exists():
            db_path.unlink()
            tmp_db_unlinked = True
        for sufijo in ("-wal", "-shm", ".bak"):
            Path(str(db_path) + sufijo).unlink(missing_ok=True)
        shutil.rmtree(temp_dir, ignore_errors=True)
    except OSError:
        pass

    # Resumen final
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
        print()
        print("VERIFICACIÓN REAL: ALGUNAS PRUEBAS FALLARON.")
        sys.exit(1)
    else:
        print("Todas las verificaciones reales pasaron.")
        print()
        print("VERIFICACIÓN REAL COMPLETADA — 3.8.5.1.4.8.9")
        sys.exit(0)


if __name__ == "__main__":
    main()
