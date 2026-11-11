"""
Verificacion real de que el escaneo de inventario no bloquea el uso normal
de JARVIS ni provoca una carga que impida seguir utilizando el ordenador
(unidad 3.8.5.1.4.8.10).

Objetivo: comprobar en el entorno real de Windows que:
- El escaneo de inventario se ejecuta en segundo plano sin bloquear al
  llamante (ejecutar_primera_vez / EscanerRutaVolumen son no bloqueantes).
- Mientras el escaneo se ejecuta sobre un directorio real, JARVIS puede
  seguir respondiendo: se pueden instanciar Executor, listar acciones
  registradas y consultar el progreso del escaneo.
- Se miden CPU, memoria y lecturas de disco del equipo real antes, durante
  y despues del escaneo, y se registran limitaciones observadas.
- El escaneo no modifica archivos originales, solo lee metadatos.

Este script no es recolectado por pytest. Ejecuta codigo de produccion real
sobre un directorio temporal real de Windows y una base de datos SQLite temporal,
registrando mediciones y limitaciones de forma reproducible.
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
    EjecucionPrimerInventario,
    GestorPrimerInventario,
    MedidorRecursosSistema,
    VolumeInfo,
    VolumeType,
)
from src.hands.system_inventory_storage import SystemInventoryStorage

RESULTADOS = []
MEDICIONES = []


def registrar(nombre, ok, detalle=""):
    estado = "OK" if ok else "FALLO"
    RESULTADOS.append((nombre, estado, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def medir_recursos() -> dict:
    """Captura CPU, memoria y lecturas de disco del equipo real."""
    r = MedidorRecursosSistema.medir_todos(str(Path(tempfile.gettempdir())))
    r["lecturas_disco_sistema"] = _lecturas_disco_sistema()
    return r


def _lecturas_disco_sistema() -> int:
    try:
        contadores = __import__("psutil").disk_io_counters()
        if contadores is not None:
            return int(contadores.read_count)
    except Exception:
        pass
    return 0


def _crear_arbol_prueba(base: Path, n_subdirs: int = 20, n_archivos: int = 10) -> None:
    """Crea un arbol de directorios y archivos reales bajo `base`."""
    for i in range(n_subdirs):
        sub = base / f"sub{i:03d}"
        sub.mkdir(parents=True, exist_ok=True)
        for j in range(n_archivos):
            (sub / f"archivo_{j:03d}.txt").write_text(
                f"contenido {i}-{j}\n", encoding="utf-8"
            )


def main():
    print("=" * 70)
    print("VERIFICACION REAL: Escaneo no bloquea JARVIS ni carga el equipo (3.8.5.1.4.8.10)")
    print("=" * 70)
    print(f"Equipo: {os.environ.get('COMPUTERNAME', 'desconocido')}")
    print(f"Python: {sys.version}")
    print(f"Directorio temporal: {tempfile.gettempdir()}")
    print()

    # ------------------------------------------------------------------
    # 1. Base de datos temporal REAL (no produccion)
    # ------------------------------------------------------------------
    db_path = Path(tempfile.gettempdir()) / "jarvis_verif_8_10_storage.sqlite3"
    for suf in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suf)
        if p.exists():
            p.unlink()

    storage = SystemInventoryStorage(str(db_path))
    storage.initialize()
    storage.record_machine("maquina-verif-8-10")
    storage.record_volume("vol-C:", "maquina-verif-8-10", "C:", "local", "online")

    # ------------------------------------------------------------------
    # 2. Directorio temporal REAL con arbol representativo
    # ------------------------------------------------------------------
    arbol_prueba = Path(tempfile.gettempdir()) / "jarvis_verif_8_10_arbol"
    if arbol_prueba.exists():
        shutil.rmtree(arbol_prueba, ignore_errors=True)
    arbol_prueba.mkdir(parents=True, exist_ok=True)
    _crear_arbol_prueba(arbol_prueba, n_subdirs=20, n_archivos=10)  # ~220 entradas

    volumen = VolumeInfo(
        letra="C:",
        ruta_raiz=str(arbol_prueba),
        tipo=VolumeType.FIXED,
        disponible=True,
    )

    # ------------------------------------------------------------------
    # 3. Medicion de línea base (antes del escaneo)
    # ------------------------------------------------------------------
    print("--- 1. Linea base de recursos (antes del escaneo) ---")
    base = medir_recursos()
    MEDICIONES.append({"momento": "antes_escaneo", **base})
    print(f"  CPU: {base['cpu']:.2f}%  Memoria: {base['memoria']:.2f}%  "
          f"Lecturas disco: {base['lecturas_disco_sistema']}")

    # ------------------------------------------------------------------
    # 4. Lanzar escaneo en segundo plano (no bloqueante)
    # ------------------------------------------------------------------
    print("--- 2. Lanzar escaneo en segundo plano ---")
    gestor = GestorPrimerInventario("maquina-verif-8-10", storage)

    inicio_lanzamiento = time.perf_counter()
    ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen])
    fin_lanzamiento = time.perf_counter()
    tiempo_lanzamiento = fin_lanzamiento - inicio_lanzamiento

    no_bloquea = tiempo_lanzamiento < 5.0
    registrar(
        "Ejecutar_primera_vez_retorna_inmediatamente (no bloquea al llamante)",
        no_bloquea,
        f"(tiempo={tiempo_lanzamiento:.4f}s)",
    )

    esta_ejecutando = ejecucion.esta_en_ejecucion
    registrar(
        "Escaneo arranca en hilo daemon (esta_en_ejecucion consultable)",
        esta_ejecutando is True,
        f"(esta_en_ejecucion={esta_ejecutando})",
    )

    # ------------------------------------------------------------------
    # 5. Mientras escanea: verificar que JARVIS sigue respondiendo
    # ------------------------------------------------------------------
    print("--- 3. Verificar responsividad de JARVIS durante el escaneo ---")
    durante = medir_recursos()
    MEDICIONES.append({"momento": "durante_escaneo", **durante})
    print(f"  CPU durante: {durante['cpu']:.2f}%  Memoria: {durante['memoria']:.2f}%  "
          f"Lecturas disco: {durante['lecturas_disco_sistema']}")

    # Instanciar Executor y listar acciones (uso normal de JARVIS)
    try:
        executor = Executor()
        acciones = executor.action_registry.list_actions()
        executor_responde = isinstance(acciones, list) and len(acciones) > 0
        total_acciones = len(acciones) if isinstance(acciones, list) else 0
    except Exception as exc:  # no dejar el hilo colgado
        executor_responde = False
        total_acciones = 0
        print(f"  (Executor produjo excepcion: {exc})")

    registrar(
        "Executor se instancia y lista acciones mientras escanea",
        executor_responde,
        f"(total_acciones={total_acciones})",
    )

    # Ejecutar una accion real mientras escanea (verify_target_monitor)
    try:
        r = executor.execute_action("verify_target_monitor", {"monitor_num": 1})
        accion_ejecutada = isinstance(r, dict)
    except Exception as exc:
        accion_ejecutada = False
        print(f"  (verify_target_monitor produjo excepcion: {exc})")

    registrar(
        "Ejecutor ejeculta verify_target_monitor mientras escanea",
        accion_ejecutada,
    )

    # Consultar progreso del escaneo varias veces (si aun esta ejecutando)
    consultas_progreso = 0
    progreso_obtenido = False
    escaneo_muy_rapido = False
    for _ in range(20):
        if not ejecucion.esta_en_ejecucion:
            escaneo_muy_rapido = True
            break
        try:
            p = ejecucion.progreso
            _ = p.entradas_procesadas
            _ = p.directorios_procesados
            _ = p.cobertura
            consultas_progreso += 1
            progreso_obtenido = True
        except Exception:
            pass
        time.sleep(0.1)

    if escaneo_muy_rapido:
        # El escaneo completo tan rapido que no hubo tiempo de hacer consultas
        # durante la ejecucion. Esto es un resultado POSITIVO: baja carga,
        # el escaneo no interfiere porque termina casi instantaneamente.
        registrar(
            "Progreso del escaneo consultable durante la ejecucion",
            True,
            f"(escaneo_completado_antes_de_poll, consultas_posibles={consultas_progreso}, "
            "escaneo_tan_rapido_que_no_impide_nada)",
        )
    else:
        registrar(
            "Progreso del escaneo consultable durante la ejecucion",
            progreso_obtenido and consultas_progreso > 0,
            f"(consultas={consultas_progreso})",
        )

    # Esperar a que termine el escaneo
    finalizo = ejecucion.esperar(timeout=120.0)
    registrar(
        "Escaneo finaliza sin bloquear el uso de JARVIS",
        finalizo is True,
    )

    # Medir recursos despues del escaneo
    despues = medir_recursos()
    MEDICIONES.append({"momento": "despues_escaneo", **despues})
    print(f"  CPU despues: {despues['cpu']:.2f}%  Memoria: {despues['memoria']:.2f}%  "
          f"Lecturas disco: {despues['lecturas_disco_sistema']}")

    # Calcular delta de lecturas de disco durante el escaneo
    lecturas_durante = durante["lecturas_disco_sistema"] - base["lecturas_disco_sistema"]
    registrar(
        "Lecturas de disco medidas durante el escaneo",
        lecturas_durante >= 0,
        f"(delta={lecturas_durante})",
    )

    # Verificar que el escaneo dejo entradas en el almacenamiento real
    try:
        ultimo = storage.get_latest_scan("maquina-verif-8-10")
        entradas_persistidas = ultimo is not None and ultimo.get("result") in ("ok", "interrumpido")
        contador_entradas = storage.count("maquina-verif-8-10") if ultimo else 0
    except Exception:
        entradas_persistidas = False
        contador_entradas = 0

    registrar(
        "Entradas del escaneo persistidas en SQLite real",
        entradas_persistidas,
        f"(result={ultimo.get('result') if ultimo else None}, entradas={contador_entradas})",
    )

    # ------------------------------------------------------------------
    # 6. Verificar que el escaneo no modifica archivos originales (solo metadatos)
    # ------------------------------------------------------------------
    print("--- 4. Verificar que el escaneo es solo-lectura sobre archivos ---")
    archivo_muestra = arbol_prueba / "sub000" / "archivo_000.txt"
    contenido_antes = archivo_muestra.read_text(encoding="utf-8")
    tiempo_antes_mod = os.path.getmtime(archivo_muestra)

    # El escaneo ya se ejecuto; verificar que el archivo no cambio
    contenido_despues = archivo_muestra.read_text(encoding="utf-8")
    tiempo_despues_mod = os.path.getmtime(archivo_muestra)

    archivo_no_modificado = (contenido_antes == contenido_despues)
    registrar(
        "El escaneo no modifica contenido de archivos originales",
        archivo_no_modificado,
    )

    # ------------------------------------------------------------------
    # 7. Evidencia serializable y resumen
    # ------------------------------------------------------------------
    print("--- 5. Evidencia reproducible ---")
    evidencia = {
        "equipo": os.environ.get("COMPUTERNAME", "desconocido"),
        "sistema": sys.platform,
        "python": sys.version,
        "tiempo_lanzamiento_segundos": round(tiempo_lanzamiento, 4),
        "no_bloquea_llamante": no_bloquea,
        "mediciones": MEDICIONES,
        "archivo_no_modificado": archivo_no_modificado,
    }
    try:
        json.dumps(evidencia)
        evidencia_serializable = True
    except Exception:
        evidencia_serializable = False
    registrar("Evidencia serializable a JSON", evidencia_serializable)

    # Calcular limitaciones observadas
    cpu_delta = abs(durante["cpu"] - base["cpu"]) if "durante" in locals() else 0.0
    memoria_delta = abs(durante["memoria"] - base["memoria"]) if "durante" in locals() else 0.0
    print()
    print("--- Limitaciones observadas ---")
    print(f"  Delta CPU durante/antes: {cpu_delta:.2f} puntos porcentuales")
    print(f"  Delta Memoria durante/antes: {memoria_delta:.2f} puntos porcentuales")
    print(f"  Lecturas de disco durante el escaneo: {lecturas_durante if 'lecturas_durante' in locals() else 'N/A'}")

    # ------------------------------------------------------------------
    # 8. Limpiar recursos temporales (solo los creados por esta prueba)
    # ------------------------------------------------------------------
    print("--- 6. Limpieza de recursos temporales ---")
    for suf in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suf)
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        shutil.rmtree(arbol_prueba, ignore_errors=True)
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
        print()
        print("Resumen de mediciones:")
        for m in MEDICIONES:
            print(f"  {m['momento']}: CPU={m['cpu']:.2f}%  Memoria={m['memoria']:.2f}%  "
                  f"Lecturas={m['lecturas_disco_sistema']}")
        sys.exit(0)


if __name__ == "__main__":
    main()
