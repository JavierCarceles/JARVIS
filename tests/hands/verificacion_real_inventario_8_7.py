"""
Verificacion real de medicion de rendimiento del inventario (unidad 3.8.5.1.4.8.7).

Objetivo: comprobar en el entorno real de Windows que:
- MedidorRendimientoInventario mide tiempo, CPU, memoria, lecturas de disco
  y crecimiento de SQLite sobre operaciones reales del inventario.
- El rendimiento de consultas (search_by_name, search_by_extension, etc.)
  se mede en milisegundos con implementacion de produccion real.
- Los límites de rendimiento se fijan a partir de mediciones reales observadas,
  nunca de umbrales inventados.

Este script no es recolectado por pytest. Ejecuta codigo de produccion real
sobre una base de datos temporal real de Windows y verifica el comportamiento
de medicion de rendimiento contra el sistema real.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Asegurar que src/ esta en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.hands.system_inventory import (
    EntryType,
    LimiteRecursos,
    MetricaRendimiento,
    ResultadoMedicionRendimiento,
)
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    MedidorRendimientoInventario,
    SystemInventoryStorage,
)

RESULTADOS = []


def registrar(nombre, ok, detalle=""):
    estado = "OK" if ok else "FALLO"
    RESULTADOS.append((nombre, estado, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def _hace_dias(dias):
    import time
    import datetime as _dt
    ts = time.time() - dias * 86400
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()


def _entrada(i, ts):
    return {
        "entry_id": f"e{i}",
        "absolute_path": f"C:/test/archivo_{i}.txt",
        "relative_path": f"test/archivo_{i}.txt",
        "name": f"archivo_{i}.txt",
        "extension": ".txt",
        "entry_type": EntryType.FILE.value,
        "size_bytes": i * 100,
        "modified_at": ts,
        "created_at": ts,
        "accessed_at": None,
        "attributes": [],
        "excluded": False,
        "source": "filesystem_scan",
        "last_checked_at": ts,
    }


def main():
    print("=" * 70)
    print("VERIFICACION REAL: Medicion de rendimiento del inventario (3.8.5.1.4.8.7)")
    print("=" * 70)
    print(f"Equipo: {os.environ.get('COMPUTERNAME', 'desconocido')}")
    print(f"Python: {sys.version}")
    print(f"Directorio temporal: {tempfile.gettempdir()}")
    print()

    # ------------------------------------------------------------------
    # 1. Base de datos temporal REAL (no produccion)
    # ------------------------------------------------------------------
    db_path = Path(tempfile.gettempdir()) / "jarvis_verif_8_7_storage.sqlite3"
    if db_path.exists():
        db_path.unlink()
    for suf in ("-wal", "-shm"):
        p = Path(str(db_path) + suf)
        if p.exists():
            p.unlink()

    storage = SystemInventoryStorage(str(db_path))
    storage.initialize()
    storage.record_machine("maquina-verif-8-7")
    storage.record_volume("vol-C:", "maquina-verif-8-7", "C:", "local", "online")

    medidor = MedidorRendimientoInventario(storage)

    # ------------------------------------------------------------------
    # 2. Insertar 100 entradas reales para medir crecimiento de SQLite
    # ------------------------------------------------------------------
    ts = _hace_dias(2)

    storage.begin_scan_run("scan-perf-1", "maquina-verif-8-7", "C:", SCAN_MODE_FULL)
    storage.insert_file_entries("scan-perf-1", "maquina-verif-8-7", "C:",
                                [_entrada(i, ts) for i in range(100)])
    storage.end_scan_run("scan-perf-1", result=SCAN_RESULT_OK, entries_count=100)

    # ------------------------------------------------------------------
    # 3. Medir operacion de escritura real (tiempo, CPU, memoria, disco, DB growth)
    # ------------------------------------------------------------------
    def operacion_escritura():
        storage.begin_scan_run("scan-perf-2", "maquina-verif-8-7", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries("scan-perf-2", "maquina-verif-8-7", "C:",
                                    [_entrada(i, ts) for i in range(100, 200)])
        storage.end_scan_run("scan-perf-2", result=SCAN_RESULT_OK, entries_count=100)

    metrica_escritura = medidor.medir_operacion("insert_file_entries_100", operacion_escritura)

    registrar(
        "Medir operacion: tiempo >= 0",
        metrica_escritura.tiempo_segundos >= 0,
        f"(tiempo={metrica_escritura.tiempo_segundos:.6f}s)",
    )
    registrar(
        "Medir operacion: CPU antes en [0,100]",
        0 <= metrica_escritura.cpu_antes_porcentaje <= 100,
        f"(cpu_antes={metrica_escritura.cpu_antes_porcentaje:.2f}%)",
    )
    registrar(
        "Medir operacion: CPU despues en [0,100]",
        0 <= metrica_escritura.cpu_despues_porcentaje <= 100,
        f"(cpu_despues={metrica_escritura.cpu_despues_porcentaje:.2f}%)",
    )
    registrar(
        "Medir operacion: memoria antes en [0,100]",
        0 <= metrica_escritura.memoria_antes_porcentaje <= 100,
        f"(memoria_antes={metrica_escritura.memoria_antes_porcentaje:.2f}%)",
    )
    registrar(
        "Medir operacion: memoria despues en [0,100]",
        0 <= metrica_escritura.memoria_despues_porcentaje <= 100,
        f"(memoria_despues={metrica_escritura.memoria_despues_porcentaje:.2f}%)",
    )
    registrar(
        "Medir operacion: lecturas disco antes >= 0",
        metrica_escritura.lecturas_disco_antes >= 0,
        f"(lecturas_antes={metrica_escritura.lecturas_disco_antes})",
    )
    registrar(
        "Medir operacion: crecimiento DB >= 0",
        metrica_escritura.crecimiento_db_bytes >= 0,
        f"(crecimiento={metrica_escritura.crecimiento_db_bytes} bytes)",
    )

    # ------------------------------------------------------------------
    # 4. Medir consulta real (search_by_name) con tiempo en ms
    # ------------------------------------------------------------------
    def consulta_nombre():
        return storage.search_by_name("maquina-verif-8-7", "archivo_150.txt")

    metrica_consulta = medidor.medir_consulta("search_by_name_archivo_150", consulta_nombre)

    registrar(
        "Medir consulta: nombre registrado",
        metrica_consulta.consulta_nombre == "search_by_name_archivo_150",
        f"(nombre={metrica_consulta.consulta_nombre})",
    )
    registrar(
        "Medir consulta: tiempo_ms >= 0",
        metrica_consulta.consulta_tiempo_ms is not None
        and metrica_consulta.consulta_tiempo_ms >= 0,
        f"(tiempo_ms={metrica_consulta.consulta_tiempo_ms})",
    )

    # Verificar que la consulta realmente devolvio datos (no mock)
    # Usamos search_by_extension que sabemos que tiene entradas (200 archivos .txt insertados)
    resultados_ext = storage.search_by_extension("maquina-verif-8-7", ".txt")
    resultados_nombre = storage.search_by_name("maquina-verif-8-7", "archivo_150.txt")
    print(f"DEBUG search_by_name archivo_150.txt: {len(resultados_nombre)} entradas")
    print(f"DEBUG search_by_extension .txt: {len(resultados_ext)} entradas")
    registrar(
        "Consulta real devuelve entradas de archivo",
        len(resultados_ext) > 0,
        f"(entradas_txt={len(resultados_ext)})",
    )

    # ------------------------------------------------------------------
    # 5. Medir consulta search_by_extension
    # ------------------------------------------------------------------
    def consulta_extension():
        return storage.search_by_extension("maquina-verif-8-7", ".txt")

    metrica_consulta_ext = medidor.medir_consulta("search_by_extension_txt", consulta_extension)

    registrar(
        "Medir consulta extension: tiempo_ms >= 0",
        metrica_consulta_ext.consulta_tiempo_ms is not None
        and metrica_consulta_ext.consulta_tiempo_ms >= 0,
        f"(tiempo_ms={metrica_consulta_ext.consulta_tiempo_ms})",
    )

    # ------------------------------------------------------------------
    # 6. Agregar mediciones y verificar acumulacion
    # ------------------------------------------------------------------
    resultado_inicial = ResultadoMedicionRendimiento(
        metricas=[],
        tiempo_total_segundos=0.0,
        cpu_promedio_porcentaje=0.0,
        memoria_pico_porcentaje=0.0,
        lecturas_disco_total=0,
        crecimiento_db_bytes=0,
        consultas_medidadas={},
        limites_sugeridos=[],
    )

    resultado = medidor.agregar_medicion(resultado_inicial, metrica_escritura)
    resultado = medidor.agregar_medicion(resultado, metrica_consulta)
    resultado = medidor.agregar_medicion(resultado, metrica_consulta_ext)

    registrar(
        "Agregar: 3 metricas acumuladas",
        len(resultado.metricas) == 3,
        f"(count={len(resultado.metricas)})",
    )
    registrar(
        "Agregar: tiempo total > 0",
        resultado.tiempo_total_segundos > 0,
        f"(total={resultado.tiempo_total_segundos:.6f}s)",
    )
    registrar(
        "Agregar: lecturas disco total >= 0",
        resultado.lecturas_disco_total >= 0,
        f"(total={resultado.lecturas_disco_total})",
    )
    registrar(
        "Agregar: crecimiento DB >= 0",
        resultado.crecimiento_db_bytes >= 0,
        f"(bytes={resultado.crecimiento_db_bytes})",
    )
    registrar(
        "Agregar: consultas medidas registradas",
        len(resultado.consultas_medidadas) >= 1,
        f"(consultas={list(resultado.consultas_medidadas.keys())})",
    )

    # ------------------------------------------------------------------
    # 7. Establecer limites desde mediciones REALES (no inventados)
    # ------------------------------------------------------------------
    limites = medidor.establecer_limites_desde_mediciones(
        resultado.metricas, factor_seguridad=2.0
    )

    nombres_limite = {l.nombre for l in limites}
    registrar(
        "Limites: se generan limites para todas las dimensiones",
        len(limites) >= 5,
        f"(count={len(limites)}, nombres={sorted(nombres_limite)})",
    )

    # Cada limite debe tener origen trazable a mediciones reales
    for limite in limites:
        registrar(
            f"Limite '{limite.nombre}' tiene origen real",
            "medicion" in limite.origen.lower() or "observado" in limite.origen.lower(),
            f"(origen={limite.origen})",
        )
        registrar(
            f"Limite '{limite.nombre}' valor >= 0",
            limite.valor >= 0,
            f"(valor={limite.valor}, unidad={limite.unidad})",
        )

    # El limite de tiempo debe ser derivado del maximo observado * factor
    tiempo_max_observado = max(m.tiempo_segundos for m in resultado.metricas)
    limite_tiempo = next(
        (l for l in limites if l.nombre == "tiempo_maximo_operacion_segundos"),
        None,
    )
    registrar(
        "Limite tiempo = maximo observado * factor_seguridad",
        limite_tiempo is not None
        and abs(limite_tiempo.valor - tiempo_max_observado * 2.0) < 0.001,
        f"(maximo_observado={tiempo_max_observado:.6f}s, "
        f"limite={limite_tiempo.valor if limite_tiempo else 'N/A'})",
    )

    # ------------------------------------------------------------------
    # 8. Crear LimiteRecursos desde una medicion real
    # ------------------------------------------------------------------
    limite_recursos = medidor.crear_limite_recursos_desde_medicion(
        metrica_escritura, factor_seguridad=2.0
    )

    registrar(
        "LimiteRecursos: se crea desde medicion real",
        limite_recursos is not None,
        f"(tipo={type(limite_recursos).__name__ if limite_recursos else 'None'})",
    )
    if limite_recursos is not None:
        registrar(
            "LimiteRecursos: CPU <= 100",
            0 <= limite_recursos.cpu_max_porcentaje <= 100,
            f"(cpu={limite_recursos.cpu_max_porcentaje})",
        )
        registrar(
            "LimiteRecursos: memoria <= 100",
            0 <= limite_recursos.memoria_max_porcentaje <= 100,
            f"(memoria={limite_recursos.memoria_max_porcentaje})",
        )
        registrar(
            "LimiteRecursos: disco <= 100",
            0 <= limite_recursos.disco_uso_max_porcentaje <= 100,
            f"(disco={limite_recursos.disco_uso_max_porcentaje})",
        )

    # ------------------------------------------------------------------
    # 9. Resumen serializable (evidencia reproducible)
    # ------------------------------------------------------------------
    try:
        resumen_json = json.dumps(resultado.resumen())
        resumen_serializable = True
    except Exception:
        resumen_json = ""
        resumen_serializable = False
    registrar(
        "Resumen serializable a JSON",
        resumen_serializable,
        f"(longitud={len(resumen_json)})",
    )

    # ------------------------------------------------------------------
    # 10. Limpiar recursos temporales (solo los creados por esta prueba)
    # ------------------------------------------------------------------
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
