"""
Verificación REAL de entorno de la unidad 3.8.5.1.4.8.3 (escaneo por volumen o
ruta, exclusiones de usuario y reconstrucción controlada del catálogo).

No es un test de pytest: se ejecuta directamente con Python para comprobar la
implementación de producción sobre el sistema de archivos real del equipo.

Efectos sobre el equipo:
- Lectura SOLO de metadatos de un subárbol real delimitado (nunca lee contenido
  de archivos personales, nunca modifica ni borra archivos originales).
- Base de datos SQLite del inventario en un DIRECTORIO TEMPORAL controlado
  (no toca `data/system_inventory.sqlite3` de producción).
- Proceso/hilo creado y terminado por este script.

Uso:
    python tests/hands/verificacion_real_inventario_8_3.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Asegurar imports de src/ desde cualquier CWD.
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
    escanear_ruta,
    reconstruir_catalogo,
)
from src.hands.system_inventory_storage import (  # noqa: E402
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

MACHINE_ID = "maquina-real-verificacion-8-3"

# Subárbol real delimitado para la verificación (solo lectura de metadatos).
# C:\Users\Public es típico, pequeño y ajeno al trabajo del usuario.
CANDIDATOS_REALES = [
    Path("C:/Users/Public"),
    Path("C:/Windows/Temp"),
]

REPORTE: list[str] = []


def registrar(linea: str) -> None:
    REPORTE.append(linea)
    print(linea)


def volumen_de_ruta_real(ruta: Path) -> str:
    if os.name == "nt":
        return os.path.splitdrive(str(ruta.resolve()))[0].upper()
    return os.path.sep


def main() -> int:
    registrar("=== VERIFICACIÓN REAL ENTORNO — 3.8.5.1.4.8.3 ===")
    registrar(f"Fecha: {datetime.now().isoformat()}")
    registrar(f"Python: {sys.version}")
    registrar(f"SO: {os.name} / {sys.platform}")
    registrar(f"Directorio de trabajo: {Path.cwd()}")

    # 1. Elegir subárbol real existente.
    subarbol_real: Path | None = None
    for candidato in CANDIDATOS_REALES:
        if candidato.exists() and candidato.is_dir():
            subarbol_real = candidato
            break
    if subarbol_real is None:
        registrar("ERROR: no se encontró ningún subárbol real para escanear.")
        return 1
    registrar(f"Subárbol real escaneado: {subarbol_real}")

    # 2. Base de datos temporal controlada (no producción).
    tmp_db = Path(os.environ.get("TEMP", str(Path.home()))) / (
        f"jarvis_verif_8_3_{uuid.uuid4().hex[:8]}.sqlite3"
    )
    storage = SystemInventoryStorage(tmp_db)
    storage.initialize()

    contrato = InventoryContract(machine_id=MACHINE_ID)

    # 3. Escaneo real por ruta sobre el subárbol real.
    t0 = time.perf_counter()
    recursos_antes = MedidorRecursosSistema.medir_todos(str(subarbol_real))
    resultado: ResultadoEscaneo = escanear_ruta(
        ruta_absoluta=str(subarbol_real),
        contrato=contrato,
        maquina_id=MACHINE_ID,
        storage=storage,
    )
    t1 = time.perf_counter()
    recursos_despues = MedidorRecursosSistema.medir_todos(str(subarbol_real))
    duracion = t1 - t0

    registrar("")
    registrar("--- Escaneo real por ruta (producción, SQLite real) ---")
    registrar(f"scan_id: {resultado.scan_id}")
    registrar(f"volumen: {resultado.volumen}")
    registrar(f"ruta: {resultado.ruta}")
    registrar(f"modo: {resultado.modo}")
    registrar(f"resultado: {resultado.resultado}")
    registrar(f"completado: {resultado.completado}  interrumpido: {resultado.interrumpido}")
    registrar(f"entradas: {resultado.entradas_procesadas}  "
              f"archivos: {resultado.archivos_procesados}  "
              f"directorios: {resultado.directorios_procesados}")
    registrar(f"errores: {resultado.errores}  por categoria: {resultado.errores_por_categoria}")
    registrar(f"exclusiones: {resultado.exclusiones}")
    registrar(f"cobertura: {resultado.cobertura}%")
    registrar(f"duración: {duracion:.3f}s")
    registrar(f"iniciado: {resultado.iniciado_en}  finalizado: {resultado.finalizado_en}")
    registrar(f"CPU antes/después: {recursos_antes['cpu']:.1f}% / {recursos_despues['cpu']:.1f}%")
    registrar(f"Memoria antes/después: {recursos_antes['memoria']:.1f}% / {recursos_despues['memoria']:.1f}%")
    registrar(f"Disco antes/después: {recursos_antes['disco']:.1f}% / {recursos_despues['disco']:.1f}%")

    assert resultado.resultado == SCAN_RESULT_OK, resultado.resultado
    assert resultado.entradas_procesadas > 0, "El escaneo real no produjo entradas"
    assert resultado.completado is True

    # 4. Contraste de muestra con el sistema de archivos real.
    entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
    muestra = entradas[: min(20, len(entradas))]
    verificadas = 0
    for e in muestra:
        ruta = e["absolute_path"]
        existe = os.path.exists(ruta) or os.path.islink(ruta)
        if existe:
            verificadas += 1
        registrar(f"  muestra: {'OK ' if existe else 'FALTA'} {ruta} ({e['entry_type']})")
    registrar(f"Muestra contrastada: {verificadas}/{len(muestra)} entradas existen en el SO real")
    assert verificadas == len(muestra), "Algunas entradas del inventario no existen en el SO real"

    # 5. Persistencia real: recuperar desde una NUEVA instancia del almacenamiento
    #    sobre la misma base temporal y comprobar que los datos se leen.
    storage2 = SystemInventoryStorage(tmp_db)
    count = storage2.count(MACHINE_ID)
    latest = storage2.get_latest_scan(MACHINE_ID, resultado.volumen)
    registrar("")
    registrar("--- Persistencia real (nueva instancia sobre misma base) ---")
    registrar(f"entradas totales máquina: {count}")
    registrar(f"último scan: {latest['scan_id'] if latest else None} resultado={latest['result'] if latest else None}")
    assert count == resultado.entradas_procesadas
    assert latest is not None and latest["scan_id"] == resultado.scan_id

    # 6. Exclusión de ubicación real elegida por el usuario.
    subcarpeta_excluir = next(
        (p for p in subarbol_real.iterdir() if p.is_dir()), None
    )
    if subcarpeta_excluir is not None:
        contrato2 = InventoryContract(machine_id=MACHINE_ID)
        contrato2.agregar_exclusion_usuario(str(subcarpeta_excluir))
        t2 = time.perf_counter()
        resultado_excluido = escanear_ruta(
            ruta_absoluta=str(subarbol_real),
            contrato=contrato2,
            maquina_id=MACHINE_ID,
            storage=storage,
        )
        t3 = time.perf_counter()
        entradas_excluidas = storage.obtener_entradas_escaneo(resultado_excluido.scan_id)
        rutas_dentro = [
            e["absolute_path"]
            for e in entradas_excluidas
            if e["absolute_path"] == str(subcarpeta_excluir)
            or e["absolute_path"].startswith(str(subcarpeta_excluir) + os.sep)
        ]
        registrar("")
        registrar("--- Exclusión real de ubicación elegida por el usuario ---")
        registrar(f"excluida: {subcarpeta_excluir}")
        registrar(f"scan_id exclusión: {resultado_excluido.scan_id}")
        registrar(f"entradas con exclusión: {resultado_excluido.exclusiones}")
        registrar(f"entradas bajo carpeta excluida: {len(rutas_dentro)} (esperado 0)")
        assert resultado_excluido.resultado == SCAN_RESULT_OK
        assert len(rutas_dentro) == 0
        registrar(f"duración exclusión: {t3 - t2:.3f}s")

    # 7. Reconstrucción controlada del catálogo (según 3.8.5.1.4.8.3).
    t4 = time.perf_counter()
    reconstruccion = reconstruir_catalogo(
        volumen=resultado.volumen,
        raiz=str(subarbol_real),
        contrato=contrato,
        maquina_id=MACHINE_ID,
        storage=storage,
    )
    t5 = time.perf_counter()
    run_original = storage.get_scan_run(resultado.scan_id)
    run_reconstruccion = storage.get_scan_run(reconstruccion.scan_id)
    entradas_reconstruidas = storage.obtener_entradas_escaneo(reconstruccion.scan_id)
    latest_despues = storage.get_latest_scan(MACHINE_ID, resultado.volumen)
    registrar("")
    registrar("--- Reconstrucción controlada del catálogo (no destructiva) ---")
    registrar(f"scan_id original: {resultado.scan_id} entradas={run_original['entries_count']}")
    registrar(f"scan_id reconstrucción: {reconstruccion.scan_id} entradas={run_reconstruccion['entries_count']}")
    registrar(f"ambos scan_runs conservados (historial no destruido): "
              f"{run_original is not None and run_reconstruccion is not None}")
    registrar(f"último scan del volumen es la reconstrucción: "
              f"{latest_despues['scan_id'] == reconstruccion.scan_id}")
    registrar(f"duración reconstrucción: {t5 - t4:.3f}s")
    assert run_original is not None and run_reconstruccion is not None
    assert latest_despues["scan_id"] == reconstruccion.scan_id
    assert len(entradas_reconstruidas) == resultado.entradas_procesadas

    # 8. Limpieza de recursos creados por la prueba.
    try:
        storage.close()
        storage2.close()
        tmp_db.unlink(missing_ok=True)
        for sufijo in ("-wal", "-shm", ".bak"):
            Path(str(tmp_db) + sufijo).unlink(missing_ok=True)
    except OSError:
        pass
    registrar("")
    registrar("Recursos temporales de la prueba limpiados.")
    registrar("=== FIN VERIFICACIÓN REAL — 3.8.5.1.4.8.3 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
