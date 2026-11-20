# -*- coding: utf-8 -*-
"""
Verificacion en el entorno real del escaneo completo de volumenes locales.

Ejecuta el escaner de produccion (escanear_volumen) sobre TODOS los volumenes
locales fijos y disponibles del equipo real (o solo los indicados con
--volumen) y verifica para cada uno:

- que produce un scan_run finalizado con end_scan_run y resultado "ok";
- que las entradas persistidas en SQLite coinciden con las procesadas;
- contraste con el SO: cada carpeta de primer nivel del volumen que el SO deja
  listar y que tiene contenido debe tener entradas en el inventario (detecta
  arboles enteros perdidos, por ejemplo C:\\Users o C:\\Program Files);
- informe por carpeta de primer nivel y errores agrupados por categoria.

Durante el recorrido se imprime por pantalla la carpeta que se esta escaneando
y se silencia el ruido de permisos denegados (no se tratan como errores).
Al final se muestra un resumen global de datos y los errores reales
annotados uno por uno (excluyendo los permisos denegados, que no son errores).

Es una prueba opt-in de entorno real: NO se ejecuta en la suite normal ni
al arrancar JARVIS. Usa el codigo de produccion real de JARVIS
(src/hands/inventory/system_inventory.py y
src/hands/inventory/system_inventory_storage.py). No usa mocks.

Por defecto guarda el escaneo en la base de datos real de JARVIS:
  data/system_inventory.sqlite3
Cada ejecucion anade un scan_run nuevo (no borra escaneos previos). Para
partir de cero, renombrar antes la base existente.

Uso (PowerShell, desde la raiz del proyecto):
    # Escaneo completo de todos los volumenes locales fijos en la BD real.
    $env:JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL = "1"
    python tests/hands/inventory/test_escaneo_volumenes_locales_completo_entorno_real.py

    # Solo algunos volumenes.
    python tests/hands/inventory/test_escaneo_volumenes_locales_completo_entorno_real.py --volumen C:

    # Prueba rapida en un subarbol pequeno con BD temporal (no afecta a JARVIS
    # y no necesita la variable de autorizacion).
    python tests/hands/inventory/test_escaneo_volumenes_locales_completo_entorno_real.py --db-path $env:TEMP\\prueba.sqlite3 --raiz C:\\Windows\\System32\\drivers\\etc
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import unittest
from pathlib import Path
from typing import Optional

# tests/hands/inventory/ -> tests/hands -> tests -> JARVIS (raiz del proyecto)
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.hands.inventory.system_inventory import (  # noqa: E402
    EstadoVolumen,
    InventoryContract,
    ProgresoRecorrido,
    VolumeType,
    default_contract,
    detectar_sistema,
    enumerar_volumenes_comun,
    escanear_ruta,
    escanear_volumen,
    generate_machine_id,
    tipo_enlace_entrada_windows,
)
from src.hands.inventory.system_inventory_storage import (  # noqa: E402
    SystemInventoryStorage,
    normalize_path,
)


# Prueba opt-in de entorno real: se lanza unicamente de forma manual con
# `python ...` (para escaneo global de raiz de volumen, ademas con
# JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL=1). Nunca forma parte de la suite
# automatizada de pytest ni del arranque de JARVIS.
if "pytest" in sys.modules:
    __test__ = False


VAR_AUTORIZACION_GLOBAL = "JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL"
"""Variable de entorno que autoriza el escaneo global (raiz de volumen completo)."""

ARGS: Optional[argparse.Namespace] = None
"""Argumentos propios del script; se rellenan en __main__ antes de unittest."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Escaneo real de volumenes locales con el codigo de JARVIS."
    )
    parser.add_argument(
        "--db-path",
        default=str(ROOT / "data" / "system_inventory.sqlite3"),
        help="Ruta de la base de datos SQLite (por defecto: data/system_inventory.sqlite3).",
    )
    parser.add_argument(
        "--volumen",
        nargs="*",
        default=[],
        help="Volumenes a escanear (ej. C: D:). Por defecto: todos los locales fijos disponibles.",
    )
    parser.add_argument(
        "--raiz",
        default="",
        help="Subarbol concreto a escanear en lugar de volumenes completos.",
    )
    return parser


def _args() -> argparse.Namespace:
    if ARGS is not None:
        return ARGS
    return _build_parser().parse_args([])


def _es_raiz_de_volumen(ruta: str) -> bool:
    """Devuelve True si la ruta indicada es la raiz de un volumen (ej. C:)."""
    _drive, _resto = os.path.splitdrive(os.path.abspath(ruta))
    if not _drive:
        return False
    return _resto.strip("\\/") == ""


def _exigir_autorizacion_global(raiz: str) -> None:
    """Exige autorizacion expresa antes de escanear una raiz de volumen completa.

    Si falta la variable de entorno `JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL=1`
    y `raiz` es una raiz de volumen, aborta la prueba con `SkipTest`. Los
    subarboles controlados (no raiz de volumen) no requieren esta autorizacion.
    """
    if _es_raiz_de_volumen(raiz) and os.environ.get(VAR_AUTORIZACION_GLOBAL) != "1":
        raise unittest.SkipTest(
            "Escaneo global de volumen completo requiere autorizacion expresa. "
            f"Establezca la variable de entorno {VAR_AUTORIZACION_GLOBAL}=1 y vuelva a ejecutar. "
            "Para una prueba controlada use --raiz con un subarbol (no raiz de volumen) "
            "y --db-path con una base de datos temporal."
        )


def _volumenes_a_escanear(pedidos: list[str]) -> list[tuple[str, str]]:
    """Devuelve (identificador, raiz) de los volumenes locales fijos disponibles.

    Si `pedidos` no esta vacio, se limita a esos identificadores (sin
    distinguir mayusculas) y falla si alguno no esta disponible.
    """
    volumenes = enumerar_volumenes_comun()
    print(f"\nVOLUMENES DETECTADOS (adaptador de produccion): {len(volumenes)}", flush=True)
    for v in volumenes:
        print(
            f"  identificador={v.identificador} raiz={v.raiz} tipo={v.tipo.value} "
            f"disponible={v.disponible} estado={v.estado.value} fs={v.sistema_archivos}",
            flush=True,
        )
    elegibles = [
        (v.identificador, v.raiz)
        for v in volumenes
        if v.tipo == VolumeType.FIXED
        and v.disponible
        and v.estado == EstadoVolumen.DISPONIBLE
    ]
    if not pedidos:
        return elegibles
    pedidos_norm = {p.upper().rstrip("\\/") for p in pedidos}
    elegidos = [(i, r) for i, r in elegibles if i.upper().rstrip("\\/") in pedidos_norm]
    faltan = pedidos_norm - {i.upper().rstrip("\\/") for i, _ in elegidos}
    if faltan:
        raise AssertionError(f"Volumenes pedidos no disponibles como locales fijos: {sorted(faltan)}")
    return elegidos


def _carpetas_primer_nivel(raiz: str, contrato: InventoryContract) -> list[str]:
    """Carpetas reales (no junction/enlace) de primer nivel que el SO deja
    listar y que tienen al menos una entrada no excluida."""
    carpetas: list[str] = []
    with os.scandir(raiz) as it:
        for entrada in it:
            try:
                if contrato.should_exclude_path(entrada.path):
                    continue
                stat = entrada.stat(follow_symlinks=False)
                if tipo_enlace_entrada_windows(entrada, stat) is not None:
                    continue
                if entrada.is_symlink() or not entrada.is_dir(follow_symlinks=False):
                    continue
                with os.scandir(entrada.path) as hijos:
                    if any(not contrato.should_exclude_path(h.path) for h in hijos):
                        carpetas.append(entrada.path)
            except OSError:
                # El SO tampoco deja listarla con este usuario: no es una perdida
                # del escaner, ya consta como error de permiso en el scan_run.
                continue
    return sorted(carpetas, key=str.lower)


def _contar_bajo(storage: SystemInventoryStorage, machine_id: str, scan_id: str, carpeta: str) -> int:
    """Cuenta las entradas del scan que cuelgan de `carpeta` (rango por ruta normalizada)."""
    prefijo = normalize_path(carpeta).rstrip("/") + "/"
    fin = prefijo[:-1] + "0"  # '0' es el caracter siguiente a '/'
    fila = storage.connect().execute(
        "SELECT COUNT(*) FROM file_entries WHERE machine_id = ? AND normalized_path >= ? "
        "AND normalized_path < ? AND scan_id = ?",
        (machine_id, prefijo, fin, scan_id),
    ).fetchone()
    return int(fila[0])


class TestEscaneoVolumenesLocalesCompletoEntornoReal(unittest.TestCase):
    """Escaneo completo de volumenes locales en el equipo real."""

    def _informe_progreso(self, etiqueta: str):
        """Callback de progreso: imprime la carpeta que se esta escaneando y el
        avance periodico, sin mostrar errores de permiso por pantalla."""
        estado = {
            "inicio": time.time(),
            "ultimo": 0.0,
            "ultima_entrada": None,
            "ultima_impresion_carpeta": 0.0,
        }

        def informe(progreso: ProgresoRecorrido) -> None:
            ahora = time.time()
            entrada = getattr(progreso, "entrada_actual", "") or ""

            # Imprimir la carpeta que se está escaneando (rate-limitado a ~1s
            # para no saturar la consola en volumenes grandes).
            if entrada and entrada != estado["ultima_entrada"]:
                if ahora - estado["ultima_impresion_carpeta"] >= 1.0:
                    print(f"[ESCANEANDO {etiqueta}] {entrada}", flush=True)
                    estado["ultima_entrada"] = entrada
                    estado["ultima_impresion_carpeta"] = ahora

            # Progreso periodico cada 5 segundos y al completar.
            if progreso.completado or (ahora - estado["ultimo"] >= 5.0 and not progreso.completado):
                estado["ultimo"] = ahora
                print(
                    f"[PROGRESO {etiqueta}] entradas={progreso.entradas_procesadas} "
                    f"archivos={progreso.archivos_procesados} "
                    f"directorios={progreso.directorios_procesados} "
                    f"errores={progreso.errores} exclusiones={progreso.exclusiones} "
                    f"cobertura={progreso.cobertura:.2f}% "
                    f"tiempo={ahora - estado['inicio']:.1f}s",
                    flush=True,
                )
                if progreso.completado:
                    print(
                        f"[FINALIZADO {etiqueta}] cobertura={progreso.cobertura:.2f}% "
                        f"entradas={progreso.entradas_procesadas} "
                        f"duracion={ahora - estado['inicio']:.1f}s",
                        flush=True,
                    )

        return informe

    def _verificar_resultado(self, storage, machine_id, resultado, etiqueta, duracion):
        print(
            f"\n>>> RESULTADO {etiqueta}: {resultado.resultado} | "
            f"entradas={resultado.entradas_procesadas} archivos={resultado.archivos_procesados} "
            f"directorios={resultado.directorios_procesados} "
            f"errores={resultado.errores} exclusiones={resultado.exclusiones} "
            f"cobertura={resultado.cobertura:.2f}% | duracion={duracion:.1f}s",
            flush=True,
        )
        if resultado.errores_por_categoria:
            detalle = ", ".join(f"{c}={n}" for c, n in sorted(resultado.errores_por_categoria.items()))
            print(f"    errores por categoria: {detalle}", flush=True)

        self.assertTrue(
            resultado.completado,
            f"Escaneo {etiqueta} interrumpido: resultado={resultado.resultado}",
        )
        self.assertEqual(resultado.resultado, "ok")
        self.assertGreater(resultado.entradas_procesadas, 0)
        self.assertEqual(resultado.cobertura, 100.0)
        self.assertTrue(resultado.iniciado_en)
        self.assertTrue(resultado.finalizado_en)

        run = storage.get_scan_run(resultado.scan_id)
        self.assertIsNotNone(run)
        self.assertEqual(run["result"], "ok")
        self.assertIsNotNone(run["finished_at"])
        self.assertEqual(run["entries_count"], resultado.entradas_procesadas)

        persistidas = storage.connect().execute(
            "SELECT COUNT(*) FROM file_entries WHERE scan_id = ?", (resultado.scan_id,)
        ).fetchone()[0]
        print(f"    entradas persistidas en SQLite: {persistidas}", flush=True)
        self.assertEqual(
            persistidas,
            resultado.entradas_procesadas,
            "Las entradas guardadas en SQLite no coinciden con las procesadas",
        )

    def test_escaneo_volumenes_locales_completo_entorno_real(self):
        """Escanear los volumenes locales produce scan_runs completos sin arboles perdidos."""
        args = _args()
        sistema = detectar_sistema()
        self.assertEqual(sistema.sistema_operativo, "Windows")

        machine_id = generate_machine_id()
        contrato = default_contract()
        contrato.machine_id = machine_id

        if args.raiz:
            objetivos = [("", args.raiz)]
        else:
            objetivos = _volumenes_a_escanear(args.volumen)
            self.assertTrue(objetivos, "No hay volumenes locales fijos disponibles")
        for _ident, raiz in objetivos:
            _exigir_autorizacion_global(raiz)

        db_path = Path(args.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        storage = SystemInventoryStorage(db_path)
        try:
            storage.initialize(machine_id_actual=machine_id)
            storage.connect()
            previos = storage.connect().execute(
                "SELECT COUNT(*) FROM scan_runs WHERE machine_id = ?", (machine_id,)
            ).fetchone()[0]
            print(f"\nBD: {db_path} | machine_id={machine_id} | scan_runs previos={previos}", flush=True)

            total_entradas = 0
            total_archivos = 0
            total_directorios = 0
            errores_reales = 0
            errores_por_categoria_global: dict[str, int] = {}
            permiso_denegado_total = 0

            for idx, (ident, raiz) in enumerate(objetivos, 1):
                etiqueta = ident or raiz
                print(f"\n{'='*68}")
                print(f"VOLUMEN {idx}/{len(objetivos)}: {etiqueta}")
                print(f"{'='*68}", flush=True)
                t0 = time.time()
                if ident:
                    resultado = escanear_volumen(
                        volumen=ident,
                        ruta_raiz=raiz,
                        contrato=contrato,
                        maquina_id=machine_id,
                        storage=storage,
                        modo="completo",
                        callback_progreso=self._informe_progreso(etiqueta),
                    )
                else:
                    resultado = escanear_ruta(
                        ruta_absoluta=raiz,
                        contrato=contrato,
                        maquina_id=machine_id,
                        storage=storage,
                        modo="completo",
                        callback_progreso=self._informe_progreso(etiqueta),
                    )
                self._verificar_resultado(storage, machine_id, resultado, etiqueta, time.time() - t0)

                total_entradas += resultado.entradas_procesadas
                total_archivos += resultado.archivos_procesados
                total_directorios += resultado.directorios_procesados
                for cat, cnt in (resultado.errores_por_categoria or {}).items():
                    if cat == "permiso_denegado":
                        permiso_denegado_total += cnt
                        continue
                    errores_por_categoria_global[cat] = errores_por_categoria_global.get(cat, 0) + cnt
                    errores_reales += cnt

                # Contraste con el SO: ninguna carpeta de primer nivel con
                # contenido listable puede quedar sin entradas en el inventario.
                print(f"  entradas por carpeta de primer nivel de {etiqueta}:", flush=True)
                perdidas = []
                for carpeta in _carpetas_primer_nivel(raiz, contrato):
                    n = _contar_bajo(storage, machine_id, resultado.scan_id, carpeta)
                    print(f"    {carpeta}: {n}", flush=True)
                    if n == 0:
                        perdidas.append(carpeta)
                self.assertEqual(
                    perdidas,
                    [],
                    f"Carpetas listables por el SO sin ninguna entrada en el inventario: {perdidas}",
                )

            # ---------- RESUMEN GLOBAL ----------
            print(f"\n{'#'*68}")
            print(f"RESUMEN GLOBAL DEL ESCANEO")
            print(f"{'#'*68}", flush=True)
            print(f"  Volumenes/rutas escaneadas : {len(objetivos)}", flush=True)
            print(f"  Entradas totales           : {total_entradas}", flush=True)
            print(f"  Archivos                   : {total_archivos}", flush=True)
            print(f"  Directorios                : {total_directorios}", flush=True)
            print(f"  Permisos denegados (no son errores) : {permiso_denegado_total}", flush=True)
            print(f"  Errores reales             : {errores_reales}", flush=True)
            print(f"{'#'*68}", flush=True)

            if errores_por_categoria_global:
                print("ERRORES DETECTADOS (uno por uno, sin contar permisos denegados):", flush=True)
                for cat in sorted(errores_por_categoria_global):
                    print(f"  - {cat}: {errores_por_categoria_global[cat]}", flush=True)
            else:
                print("No se detectaron errores reales (excluidos los permisos denegados).", flush=True)

        finally:
            storage.close()
            # La base de datos se conserva como inventario local del equipo.


if __name__ == "__main__":
    ARGS, _resto = _build_parser().parse_known_args()
    unittest.main(argv=[sys.argv[0]] + _resto, verbosity=2)
