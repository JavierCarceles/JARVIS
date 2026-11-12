# -*- coding: utf-8 -*-
"""
Verificacion en el entorno real del escaneo completo de volumenes locales
(3.8.5.1.4.10.3).

Ejecuta el escaner de produccion (escanear_volumen) sobre el volumen C: del
equipo real y verifica que produce un scan_run finalizado con end_scan_run,
registro de entradas en SQLite real y contraste con el SO.

Es una prueba opt-in de entorno real: NO se ejecuta en la suite normal ni
al arrancar JARVIS. Requiere confirmacion explicita de alcance antes de la
primera ejecucion global (3.8.5.1.4.10.3, politica de verificacion real).

Usa el codigo de produccion real de JARVIS (src/hands/system_inventory.py
y src/hands/system_inventory_storage.py). No usa mocks que decidan el
resultado.

Por defecto guarda el escaneo en la base de datos real de JARVIS:
  data/system_inventory.sqlite3

Uso:
    # Escaneo completo de C: en la BD real de JARVIS (recomendado).
    # Requiere JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL=1 (escaneo global de raiz de volumen).
    python tests/hands/test_escaneo_volumenes_locales_completo_entorno_real.py

    # Prueba rapida en un subarbol pequeno con BD temporal (no afecta a JARVIS).
    python tests/hands/test_escaneo_volumenes_locales_completo_entorno_real.py \
        --db-path /tmp/prueba.sqlite3 --raiz C:\\Windows\\System32\\drivers\\etc
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import unittest
from pathlib import Path

# tests/hands/ -> tests -> JARVIS (raiz del proyecto, donde esta src/)
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.hands.system_inventory import (
    ProgresoRecorrido,
    default_contract,
    detectar_sistema,
    enumerar_volumenes_comun,
    generate_machine_id,
    escanear_volumen,
    escanear_ruta,
)
from src.hands.system_inventory_storage import SystemInventoryStorage


# Prueba opt-in de entorno real (3.8.5.1.4.10.14.1): se lanza unicamente de
# forma manual con `python ...` (para escaneo global de raiz de volumen, ademas
# con JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL=1). Nunca forma parte de la suite
# automatizada de pytest ni del arranque de JARVIS.
if "pytest" in sys.modules:
    __test__ = False


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
        "--raiz",
        default="C:\\",
        help="Ruta raiz a escanear (por defecto: C:\\, volumen completo).",
    )
    parser.add_argument(
        "--volumen",
        default="C:",
        help="Identificador de volumen para el scan_run (por defecto: C:).",
    )
    return parser


VAR_AUTORIZACION_GLOBAL = "JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL"
"""Variable de entorno que autoriza el escaneo global (raiz de volumen completo)."""


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


class TestEscaneoVolumenesLocalesCompletoEntornoReal(unittest.TestCase):
    """Escaneo completo de volumenes locales en el equipo real."""

    def test_escaneo_volumen_c_completo_entorno_real(self):
        """Escanear C: completo produce un scan_run finalizado con entradas reales."""
        args = _build_parser().parse_args()
        import psutil

        machine_id = generate_machine_id()
        contrato = default_contract()
        contrato.machine_id = machine_id

        # Autorizacion expresa obligatoria antes de cualquier escaneo global
        # (raiz de volumen completo). Los subarboles controlados no la requieren.
        _exigir_autorizacion_global(args.raiz)

        # Enumerar con el adaptador de produccion todos los volumenes locales
        # montados admitidos (solo lectura de metadatos).
        volumenes_detectados = enumerar_volumenes_comun()
        print(
            f"\nVOLUMENES LOCALES MONTADOS (adaptador de produccion): "
            f"{len(volumenes_detectados)}",
            flush=True,
        )
        for _v in volumenes_detectados:
            print(
                f"  identificador={_v.identificador} raiz={_v.raiz} "
                f"tipo={_v.tipo.value} disponible={_v.disponible} "
                f"estado={_v.estado.value} sistema_origen={_v.sistema_origen}",
                flush=True,
            )

        # Contrastar volumen detectado por el adaptador con el SO.
        sistema = detectar_sistema()
        self.assertEqual(sistema.sistema_operativo, "Windows")
        montados_so = set()
        for particion in psutil.disk_partitions(all=False):
            punto = particion.mountpoint or ""
            if not punto:
                continue
            if os.name == "nt":
                drive = os.path.splitdrive(punto)[0]
                if drive:
                    montados_so.add(drive.upper())
        self.assertIn("C:", montados_so, "C: debe estar montado segun el SO")

        # Base de datos real de JARVIS (o ruta alternativa para pruebas rapidas).
        db_path = Path(args.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        storage = SystemInventoryStorage(db_path)
        try:
            storage.initialize(machine_id_actual=machine_id)
            storage.connect()

            # Progreso acumulado para informes relevantes (no por fichero).
            estado = {
                "volumen": args.volumen,
                "entradas": 0,
                "archivos": 0,
                "directorios": 0,
                "errores": 0,
                "exclusiones": 0,
                "cobertura": 0.0,
                "inicio": time.time(),
                "ultimo_informe": 0.0,
            }

            def informe_progreso(progreso: ProgresoRecorrido) -> None:
                """Imprime informacion relevante cada ~5 segundos."""
                ahora = time.time()
                if ahora - estado["ultimo_informe"] < 5.0:
                    return
                estado["ultimo_informe"] = ahora
                estado["entradas"] = progreso.entradas_procesadas
                estado["archivos"] = progreso.archivos_procesados
                estado["directorios"] = progreso.directorios_procesados
                estado["errores"] = progreso.errores
                estado["exclusiones"] = progreso.exclusiones
                estado["cobertura"] = progreso.cobertura
                transcurrido = ahora - estado["inicio"]
                print(
                    f"[ESCANEO {args.volumen}:] volumen={estado['volumen']} "
                    f"entradas={estado['entradas']} "
                    f"archivos={estado['archivos']} "
                    f"directorios={estado['directorios']} "
                    f"errores={estado['errores']} "
                    f"exclusiones={estado['exclusiones']} "
                    f"cobertura={estado['cobertura']:.2f}% "
                    f"tiempo={transcurrido:.1f}s",
                    flush=True,
                )

            # Ejecutar escaneo de produccion real sobre la raiz indicada.
            t0 = time.time()
            if args.raiz == "C:\\" and len(args.raiz) <= 3:
                resultado = escanear_volumen(
                    volumen=args.volumen,
                    ruta_raiz=args.raiz,
                    contrato=contrato,
                    maquina_id=machine_id,
                    storage=storage,
                    modo="completo",
                    callback_progreso=informe_progreso,
                )
            else:
                resultado = escanear_ruta(
                    ruta_absoluta=args.raiz,
                    contrato=contrato,
                    maquina_id=machine_id,
                    storage=storage,
                    modo="completo",
                    callback_progreso=informe_progreso,
                )
            duracion = time.time() - t0

            print(
                f"\nESCANEO COMPLETO {args.volumen}: OK: "
                f"{resultado.entradas_procesadas} entradas, "
                f"{round(duracion, 3)}s, "
                f"resultado={resultado.resultado}, "
                f"cobertura={resultado.cobertura}%"
            )

            # Verificar que el scan_run se completo (no interrumpido).
            self.assertTrue(
                resultado.completado,
                f"Escaneo interrumpido: resultado={resultado.resultado}, "
                f"entradas={resultado.entradas_procesadas}",
            )
            self.assertEqual(resultado.resultado, "ok")
            self.assertGreater(resultado.entradas_procesadas, 0)
            self.assertEqual(resultado.cobertura, 100.0)
            self.assertIsNotNone(resultado.finalizado_en)
            self.assertIsNotNone(resultado.iniciado_en)
            self.assertEqual(resultado.volumen, args.volumen)

            # Verificar persistencia en la base de datos SQLite real de JARVIS.
            scan_runs = storage.listar_scan_runs_por_volumen(machine_id, args.volumen)
            self.assertGreaterEqual(len(scan_runs), 1)
            ultimo = scan_runs[-1]
            self.assertEqual(ultimo["result"], "ok")
            self.assertGreater(ultimo["entries_count"], 0)
            self.assertIsNotNone(ultimo["finished_at"])
        finally:
            storage.close()
            # La base de datos se conserva para poder reutilizar el escaneo
            # real como inventario local del equipo en futuras pruebas o como
            # punto de partida para el inventario de produccion.


if __name__ == "__main__":
    unittest.main()
