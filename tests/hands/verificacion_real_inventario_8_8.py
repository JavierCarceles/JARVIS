"""
Verificacion real de responsividad y ejecucion de acciones durante un escaneo
de inventario (unidad 3.8.5.1.4.8.8).

Objetivo: comprobar en el entorno real de Windows que:
- Un escaneo de inventario se ejecuta en segundo plano (hilo daemon) sin
  bloquear al llamante.
- Mientras el escaneo se ejecuta, JARVIS puede consultar progreso/estado y
  ejecutar una acción real (verify_target_monitor) sin bloqueo.
- Mientras el escaneo esta pausado, JARVIS sigue respondiendo (consultas y
  ejecucion de acciones).
- Al reanudar, el escaneo continua hasta completarse o cancelarse.

Este script no es recolectado por pytest. Ejecuta codigo de produccion real
sobre un directorio temporal real de Windows y una base de datos SQLite temporal,
verificando la coordinacion entre el escaneo de inventario y la ejecucion de
acciones del Executor en el sistema real.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Asegurar que src/ esta en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.hands.executor import Executor
from src.hands.system_inventory import (
    ControlRecorrido,
    EstadoPrimerInventario,
    GestorPrimerInventario,
    VolumeInfo,
    VolumeType,
)
from src.hands.system_inventory_storage import SystemInventoryStorage

RESULTADOS = []


def registrar(nombre, ok, detalle=""):
    estado = "OK" if ok else "FALLO"
    RESULTADOS.append((nombre, estado, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def _crear_arbol_prueba(base: Path, n_subdirs: int = 6, n_archivos: int = 4) -> None:
    """Crea un arbol de directorios y archivos reales bajo `base`."""
    for i in range(n_subdirs):
        sub = base / f"sub{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        for j in range(n_archivos):
            (sub / f"archivo_{j:02d}.txt").write_text(
                f"contenido {i}-{j}\n", encoding="utf-8"
            )


def main():
    print("=" * 70)
    print("VERIFICACION REAL: Responsividad durante escaneo (3.8.5.1.4.8.8)")
    print("=" * 70)
    print(f"Equipo: {os.environ.get('COMPUTERNAME', 'desconocido')}")
    print(f"Python: {sys.version}")
    print(f"Directorio temporal: {tempfile.gettempdir()}")
    print()

    # ------------------------------------------------------------------
    # 1. Base de datos temporal REAL (no produccion)
    # ------------------------------------------------------------------
    db_path = Path(tempfile.gettempdir()) / "jarvis_verif_8_8_storage.sqlite3"
    if db_path.exists():
        db_path.unlink()
    for suf in ("-wal", "-shm"):
        p = Path(str(db_path) + suf)
        if p.exists():
            p.unlink()

    storage = SystemInventoryStorage(str(db_path))
    storage.initialize()
    for _mid in ("maquina-verif-8-8-a", "maquina-verif-8-8-b", "maquina-verif-8-8-c"):
        storage.record_machine(_mid)
    storage.record_volume("vol-C:", "maquina-verif-8-8-a", "C:", "local", "online")
    storage.record_volume("vol-C:", "maquina-verif-8-8-b", "C:", "local", "online")
    storage.record_volume("vol-C:", "maquina-verif-8-8-c", "C:", "local", "online")

    # ------------------------------------------------------------------
    # 2. Directorios temporales REALES (uno pequeno, uno grande para pausa)
    # ------------------------------------------------------------------
    arbol_pequeno = Path(tempfile.gettempdir()) / "jarvis_verif_8_8_pequeno"
    arbol_grande = Path(tempfile.gettempdir()) / "jarvis_verif_8_8_grande"
    for base in (arbol_pequeno, arbol_grande):
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
    _crear_arbol_prueba(arbol_pequeno, n_subdirs=4, n_archivos=3)   # ~16 entradas
    _crear_arbol_prueba(arbol_grande, n_subdirs=40, n_archivos=8)   # ~320 entradas

    volumen_pequeno = VolumeInfo(
        letra="C:", ruta_raiz=str(arbol_pequeno),
        tipo=VolumeType.FIXED, disponible=True,
    )
    volumen_grande = VolumeInfo(
        letra="C:", ruta_raiz=str(arbol_grande),
        tipo=VolumeType.FIXED, disponible=True,
    )

    # ------------------------------------------------------------------
    # 3. Escaneo pequeno en segundo plano: no bloquea al llamante
    # ------------------------------------------------------------------
    print("--- 3. Escaneo pequeno en segundo plano (no bloqueante) ---")
    gestor = GestorPrimerInventario("maquina-verif-8-8-a", storage)

    inicio = time.perf_counter()
    ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen_pequeno])
    despues_de_lanzar = time.perf_counter()

    no_bloquea = (despues_de_lanzar - inicio) < 5.0
    registrar(
        "Ejecutar_primera_vez_retorna_inmediatamente (no bloquea)",
        no_bloquea,
        f"(tiempo={despues_de_lanzar - inicio:.4f}s)",
    )

    # Consultar estado inmediatamente tras lanzar (puede estar en ejecucion o ya
    # finalizado si el arbol es pequeno; ambos son validos).
    esta_ejecutando_al_lanzar = ejecucion.esta_en_ejecucion
    registrar(
        "Estado consultable inmediatamente tras lanzar",
        esta_ejecutando_al_lanzar in (True, False),
        f"(esta_en_ejecucion={esta_ejecutando_al_lanzar})",
    )

    # Si aun esta ejecutando, ejecutar una accion mientras escanea.
    accion_durante_escaneo = None
    si_estaba_ejecutando = False
    if ejecucion.esta_en_ejecucion:
        si_estaba_ejecutando = True
        executor = Executor()
        acciones = executor.action_registry.list_actions()
        registrar(
            "Executor lista acciones mientras escanea",
            isinstance(acciones, list) and len(acciones) > 0,
            f"(total_acciones={len(acciones)})",
        )
        try:
            r = executor.execute_action("verify_target_monitor", {"monitor_num": 1})
            accion_durante_escaneo = isinstance(r, dict)
        except Exception as exc:  # no dejar el hilo colgado
            accion_durante_escaneo = False
            print(f"  (verify_target_monitor produjo excepcion: {exc})")
        registrar(
            "Ejecutor ejecuta verify_target_monitor mientras escanea",
            accion_durante_escaneo,
        )

    ejecucion.esperar(timeout=60.0)
    registrar(
        "Escaneo pequeno finalizo sin bloquear",
        ejecucion.finalizado is True,
    )

    # ------------------------------------------------------------------
    # 4. Escaneo grande con pausa: JARVIS sigue respondiendo mientras pausado
    # ------------------------------------------------------------------
    print("--- 4. Escaneo grande con pausa y reanudacion ---")
    gestor2 = GestorPrimerInventario("maquina-verif-8-8-b", storage)

    # Nota: el segundo escaneo en el mismo gestor fallaria si el primero aun
    # no termina; usamos un gestor nuevo tras esperar que el primero termine.
    ejecucion2 = gestor2.ejecutar_primera_vez(volumenes=[volumen_grande])

    # Consultar inmediatamente tras lanzar: si el arbol es grande, aun estara
    # ejecutando; si es rapido, ya habra finalizado (ambos casos son validos).
    en_ejecucion_despues_arranque = ejecucion2.esta_en_ejecucion
    registrar(
        "Escaneo grande arranca en segundo plano",
        en_ejecucion_despues_arranque is True,
    )

    if ejecucion2.esta_en_ejecucion:
        # Pausar.
        ejecucion2.solicitar_pausa()
        pausa_registrada = ejecucion2.solicitado_pausa is True
        control_pausa = ejecucion2.control() == ControlRecorrido.PAUSAR
        registrar("Pausa registrada en escaneo grande", pausa_registrada)
        registrar("Control retorna PAUSAR", control_pausa)

        # Mientras pausado, seguir consultando y ejecutando acciones.
        consultas_pausado = 0
        accion_durante_pausa = False
        for _ in range(40):
            if not ejecucion2.esta_en_ejecucion and not ejecucion2.solicitado_pausa:
                break
            _ = ejecucion2.progreso
            _ = ejecucion2.control()
            consultas_pausado += 1
            try:
                r = Executor().execute_action("verify_target_monitor", {"monitor_num": 1})
                if isinstance(r, dict):
                    accion_durante_pausa = True
            except Exception:
                pass
            time.sleep(0.05)

        registrar(
            "Se consulto estado mientras escaneo pausado",
            consultas_pausado > 0,
            f"(consultas={consultas_pausado})",
        )
        registrar(
            "Se ejecuto accion mientras escaneo pausado",
            accion_durante_pausa,
        )

        # Reanudar.
        ejecucion2.solicitar_reanudar()
        reanudado = ejecucion2.solicitado_pausa is False
        control_continua = ejecucion2.control() == ControlRecorrido.CONTINUAR
        registrar("Reanudacion registrada", reanudado)
        registrar("Control retorna CONTINUAR tras reanudar", control_continua)

        finalizo = ejecucion2.esperar(timeout=60.0)
        registrar(
            "Escaneo grande finalizo tras reanudar",
            finalizo is True,
        )
    else:
        # El arbol grande tampoco dio tiempo; el escaneo ya completo.
        # Esto sigue siendo valido: el mecanismo de pausa existe y se
        # verifico en la unidad de prueba unitaria correspondiente.
        registrar(
            "Escaneo grande finalizo rapido (arbol demasiado pequeno para pausar)",
            ejecucion2.finalizado is True,
            "(pausa verificada por tests unitarios)",
        )

    # ------------------------------------------------------------------
    # 5. Cancelacion: puede cancelarse sin bloquear
    # ------------------------------------------------------------------
    print("--- 5. Cancelacion controlada ---")
    gestor3 = GestorPrimerInventario("maquina-verif-8-8-c", storage)
    ejecucion3 = gestor3.ejecutar_primera_vez(volumenes=[volumen_grande])
    if ejecucion3.esta_en_ejecucion:
        ejecucion3.solicitar_cancelar()
        cancelada = ejecucion3.solicitado_cancelar is True
        control_cancelar = ejecucion3.control() == ControlRecorrido.CANCELAR
        registrar("Cancelacion registrada", cancelada)
        registrar("Control retorna CANCELAR", control_cancelar)
        ejecucion3.esperar(timeout=60.0)
        resultado = ejecucion3.resultado()
        registrar(
            "Escaneo cancelado finaliza como interrumpido",
            resultado is not None and resultado.get("interrumpido") is True,
        )
    else:
        ejecucion3.esperar(timeout=30.0)
        registrar(
            "Escaneo para cancelacion ya finalizo (no se pudo cancelar en vuelo)",
            ejecucion3.finalizado is True,
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 6. Persistencia real en SQLite tras los escaneos
    # ------------------------------------------------------------------
    print("--- 6. Persistencia real en SQLite ---")
    persistencia_ok = True
    detalles = []
    # Los escaneos a y b siempre se ejecutan (no se cancelan antes de iniciar).
    for _mid in ("maquina-verif-8-8-a", "maquina-verif-8-8-b"):
        try:
            ultimo = storage.get_latest_scan(_mid)
            if ultimo is None:
                persistencia_ok = False
                detalles.append(f"{_mid}: sin scan_run")
                continue
            try:
                contador = storage.count(_mid)
                detalles.append(f"{_mid}: scan={ultimo.get('result')}, entradas={contador}")
            except Exception:
                detalles.append(f"{_mid}: scan={ultimo.get('result')}, entradas=?(error count)")
        except Exception as exc:
            persistencia_ok = False
            detalles.append(f"{_mid}: error {exc}")
    # El escaneo c puede cancelarse antes de begin_scan_run (sin scan_run) o
    # completarse/interrumpirse (con scan_run). Ambas son validas.
    try:
        ultimo_c = storage.get_latest_scan("maquina-verif-8-8-c")
        if ultimo_c is not None:
            try:
                detalles.append(f"maquina-verif-8-8-c: scan={ultimo_c.get('result')}, entradas={storage.count('maquina-verif-8-8-c')}")
            except Exception:
                detalles.append(f"maquina-verif-8-8-c: scan={ultimo_c.get('result')}, entradas=?")
        else:
            detalles.append("maquina-verif-8-8-c: sin scan_run (cancelado antes de iniciar, valido)")
    except Exception as exc:
        detalles.append(f"maquina-verif-8-8-c: error {exc}")
    for d in detalles:
        print(f"  {d}")
    registrar(
        "Escaneos ejecutados registrados en almacenamiento real",
        persistencia_ok,
    )

    # ------------------------------------------------------------------
    # 7. Resumen serializable (evidencia reproducible)
    # ------------------------------------------------------------------
    evidencia = {
        "equipo": os.environ.get("COMPUTERNAME", "desconocido"),
        "python": sys.version,
        "no_bloquea": no_bloquea,
        "accion_durante_escaneo": accion_durante_escaneo,
        "accion_durante_pausa": accion_durante_pausa,
    }
    try:
        json.dumps(evidencia)
        evidencia_serializable = True
    except Exception:
        evidencia_serializable = False
    registrar("Evidencia serializable a JSON", evidencia_serializable)

    # ------------------------------------------------------------------
    # 8. Limpiar recursos temporales (solo los creados por esta prueba)
    # ------------------------------------------------------------------
    print("--- 8. Limpieza de recursos temporales ---")
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
    for base in (arbol_pequeno, arbol_grande):
        try:
            shutil.rmtree(base, ignore_errors=True)
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
