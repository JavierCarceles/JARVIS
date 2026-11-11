"""
Verificacion real de logging del inventario (unidad 3.8.5.1.4.8.5).

Objetivo: comprobar en el entorno real de Windows que:
- Los logs del inventario nunca contienen rutas completas ni listados de nombres/rutas.
- Los logs contienen resumenes agregados (conteos, errores por categoria, cobertura).
- Los errores se loguean agregados por categoria, nunca con rutas completas.
- La evidencia minima de diagnostico (scan_id, volumen, modo, resultado, conteos) esta presente.

Este script no es recolectado por pytest. Ejecuta codigo de produccion real
sobre un directorio temporal real del volumen del sistema y verifica el
comportamiento de logging contra el sistema de archivos real de Windows.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

# Asegurar que src/ esta en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.hands.system_inventory import (
    InventoryContract,
    RecorridoVolumen,
    EscanerRutaVolumen,
    escanear_ruta,
    safe_log_path,
    generate_machine_id,
)
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

MACHINE_ID = generate_machine_id()
RESULTADOS = []


def registrar(nombre, ok, detalle=""):
    estado = "OK" if ok else "FALLO"
    RESULTADOS.append((nombre, estado, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def main():
    print("=" * 70)
    print("VERIFICACION REAL: Logging del inventario (3.8.5.1.4.8.5)")
    print("=" * 70)
    print(f"Equipo: {os.environ.get('COMPUTERNAME', 'desconocido')}")
    print(f"Python: {sys.version}")
    print(f"Directorio temporal: {tempfile.gettempdir()}")
    print()

    # ------------------------------------------------------------------
    # 1. Crear directorio temporal REAL con archivos para escanear
    # ------------------------------------------------------------------
    tmp_base = Path(tempfile.gettempdir()) / "jarvis_verif_8_5"
    tmp_base.mkdir(parents=True, exist_ok=True)

    # Crear arbol real con varios archivos y subdirectorios
    (tmp_base / "documento.txt").write_text("contenido de prueba\n", encoding="utf-8")
    sub = tmp_base / "subcarpeta"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "ejecutable.exe").write_text("MZ\x90\x00", encoding="utf-8")
    (sub / "datos.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    (tmp_base / "oculto.log").write_text("log\n", encoding="utf-8")

    ruta_real = str(tmp_base)
    ruta_completa = os.path.abspath(ruta_real)
    print(f"Ruta real de prueba: {ruta_completa}")
    print()

    # ------------------------------------------------------------------
    # 2. Verificar safe_log_path acorta rutas largas
    # ------------------------------------------------------------------
    acortada = safe_log_path(ruta_completa)
    ok_safe = acortada != ruta_completa and len(acortada) < len(ruta_completa)
    registrar("safe_log_path acorta rutas largas", ok_safe,
              f"(original={len(ruta_completa)} chars, acortada={len(acortada)} chars)")

    # ------------------------------------------------------------------
    # 3. Base de datos temporal REAL (no produccion)
    # ------------------------------------------------------------------
    db_path = Path(tempfile.gettempdir()) / "jarvis_verif_8_5_storage.sqlite3"
    if db_path.exists():
        db_path.unlink()
    storage = SystemInventoryStorage(str(db_path))
    storage.initialize()

    # ------------------------------------------------------------------
    # 4. Capturar logs del modulo durante un escaneo real
    # ------------------------------------------------------------------
    mensajes_log = []

    class Capturador(logging.Handler):
        def emit(self, record):
            mensajes_log.append(record.getMessage())

    logger_mod = logging.getLogger("src.hands.system_inventory")
    logger_mod.setLevel(logging.INFO)
    h = Capturador()
    logger_mod.addHandler(h)

    try:
        contrato = InventoryContract(machine_id=MACHINE_ID)
        resultado = escanear_ruta(
            ruta_absoluta=ruta_completa,
            contrato=contrato,
            maquina_id=MACHINE_ID,
            storage=storage,
            modo="completo",
        )
    finally:
        logger_mod.removeHandler(h)

    texto_logs = "\n".join(mensajes_log)
    print(f"Capturados {len(mensajes_log)} mensajes de log durante el escaneo real.")
    print()

    # ------------------------------------------------------------------
    # 5. Verificar que NUNCA aparecen rutas completas en los logs
    # ------------------------------------------------------------------
    ok_no_ruta_completa = ruta_completa not in texto_logs
    registrar("Logs NO contienen ruta completa escaneada", ok_no_ruta_completa,
              f"(ruta={ruta_completa[:60]}...)")

    # Tambien verificar que no aparecen rutas absolutas de archivos individuales
    rutas_archivo_en_logs = any(
        str(p) in texto_logs for p in [
            str(tmp_base / "documento.txt"),
            str(sub / "ejecutable.exe"),
            str(sub / "datos.csv"),
            str(tmp_base / "oculto.log"),
        ]
    )
    registrar("Logs NO contienen rutas absolutas de archivos individuales",
              not rutas_archivo_en_logs,
              "(solo se permiten nombres acortados via safe_log_path)")

    # ------------------------------------------------------------------
    # 6. Verificar que aparecen resumenes agregados (conteos)
    # ------------------------------------------------------------------
    ok_resumen = (
        "volumen=" in texto_logs
        and "entradas=" in texto_logs
        and "errores=" in texto_logs
        and "directorios=" in texto_logs
    )
    registrar("Logs contienen resumenes agregados (conteos)", ok_resumen,
              "(volumen, entradas, errores, directorios)")

    # ------------------------------------------------------------------
    # 7. Verificar evidencia minima de diagnostico en escaneo
    # ------------------------------------------------------------------
    ok_evidencia = (
        "scan_id=" in texto_logs
        and "resultado=" in texto_logs
        and "modo=" in texto_logs
    )
    registrar("Logs contienen evidencia minima de diagnostico (scan_id, resultado, modo)",
              ok_evidencia)

    # ------------------------------------------------------------------
    # 8. Verificar errores agregados por categoria (no rutas individuales)
    # ------------------------------------------------------------------
    # Forzar un error: escanear ruta inexistente
    ruta_inexistente = str(tmp_base / "no_existe" / "nada")
    mensajes_log_error = []

    class CapturadorError(logging.Handler):
        def emit(self, record):
            mensajes_log_error.append(record.getMessage())

    logger_mod.addHandler(CapturadorError())
    logger_mod.setLevel(logging.WARNING)

    try:
        resultado_error = escanear_ruta(
            ruta_absoluta=ruta_inexistente,
            contrato=contrato,
            maquina_id=MACHINE_ID,
            storage=storage,
        )
    finally:
        logger_mod.removeHandler(CapturadorError())

    texto_logs_error = "\n".join(mensajes_log_error)

    # El error debe estar agregado por categoria, no con la ruta completa
    ok_error_agregado = (
        "categoria=" in texto_logs_error or "Error de recorrido" in texto_logs_error
    )
    ok_error_no_ruta = ruta_inexistente not in texto_logs_error

    registrar("Errores logueados agregados por categoria", ok_error_agregado,
              f"(categoria o 'Error de recorrido' presente)")
    registrar("Errores NO contienen ruta completa fallida", ok_error_no_ruta,
              f"(ruta={ruta_inexistente[:60]}...)")

    # ------------------------------------------------------------------
    # 9. Verificar que el escaneo real produjo resultados correctos
    # ------------------------------------------------------------------
    ok_escaneo = (
        resultado.resultado == SCAN_RESULT_OK
        and resultado.entradas_procesadas > 0
        and resultado.completado is True
    )
    registrar("Escaneo real produce resultados correctos", ok_escaneo,
              f"(entradas={resultado.entradas_procesadas}, resultado={resultado.resultado})")

    # ------------------------------------------------------------------
    # 10. Limpiar recursos temporales
    # ------------------------------------------------------------------
    try:
        import shutil
        shutil.rmtree(tmp_base, ignore_errors=True)
    except Exception:
        pass
    try:
        db_path.unlink(missing_ok=True)
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
