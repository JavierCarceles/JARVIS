#!/usr/bin/env python3
"""
Registra en `application_candidates` las aplicaciones del inventario ya escaneado.

`data/system_inventory.sqlite3` puede tener millones de filas en `file_entries`
(escaneo completo de los volumenes) y ninguna en `application_candidates`: la
resolucion de aplicaciones por nombre no encuentra entonces nada en la SQLite.
Este script convierte, UNA vez y sin reescanear el disco, las entradas `.exe`
(fuera de WinSxS) y los `.lnk` del menu Inicio y del escritorio del ultimo
escaneo completo de cada volumen montado en candidatos de aplicacion del
equipo actual (`machine_id`), con su clasificacion (tipo, subtipo, lanzable,
confianza y evidencia). Usa `ApplicationDiscovery.registrar_candidatos_desde_inventario`.

Uso:

    python scripts/registrar_candidatos_inventario.py
    python scripts/registrar_candidatos_inventario.py --volumen C:
    python scripts/registrar_candidatos_inventario.py --incluir-winsxs

En Windows tambien se puede abrir con doble clic. Es idempotente: si se
ejecuta otra vez, actualiza las filas existentes sin duplicarlas. No escribe
en `data/memory/entities.json` ni lanza ninguna aplicacion.

Solo usa la biblioteca estandar de Python y el codigo de JARVIS.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _mostrar_informe(informe: dict) -> None:
    print("")
    print(f"Equipo (machine_id): {informe.get('machine_id')}")
    volumenes = informe.get("volumenes") or {}
    if not volumenes:
        print("No hay volumenes montados que procesar.")
    for volumen, d in volumenes.items():
        print("")
        print(f"Volumen {volumen}")
        if not d.get("scan_id"):
            print(f"  Sin escaneo completo ok para este equipo ({d.get('motivo')}).")
            continue
        print(f"  Escaneo de origen:           {d.get('scan_id')}")
        print(f"  Entradas .exe/.lnk leidas:   {d.get('leidos')}")
        print(f"  Omitidas WinSxS:             {d.get('omitidos_winsxs')}")
        print(f"  .lnk fuera de menu/escrit.:  {d.get('omitidos_lnk_fuera_de_menu')}")
        print(f"  Ficheros que ya no existen:  {d.get('descartados_inexistentes')}")
        print(f"  .lnk con destino resuelto:   {d.get('lnk_resueltos')}")
        print(f"  Candidatos registrados:      {d.get('registrados')}")
        print(f"  Lanzables:                   {d.get('lanzables')}")
        print("  Por tipo:")
        for clave, valor in sorted((d.get("por_tipo") or {}).items()):
            print(f"    {clave}: {valor}")
        print("  Por subtipo:")
        for clave, valor in sorted((d.get("por_subtipo") or {}).items()):
            print(f"    {clave}: {valor}")
        print(f"  Segundos:                    {d.get('segundos')}")
    print("")
    print(
        f"TOTAL: {informe.get('registrados')} registrados, "
        f"{informe.get('lanzables')} lanzables, {informe.get('segundos')} s"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Registra candidatos de aplicacion desde el inventario SQLite ya escaneado."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=RAIZ / "data" / "system_inventory.sqlite3",
        help="Ruta de la base de inventario (por defecto data/system_inventory.sqlite3).",
    )
    parser.add_argument(
        "--volumen",
        action="append",
        default=None,
        help="Volumen a procesar (por ejemplo C:). Se puede repetir. Por defecto, los montados.",
    )
    parser.add_argument(
        "--incluir-winsxs",
        action="store_true",
        help="Incluir tambien los ejecutables del almacen de componentes WinSxS.",
    )
    args = parser.parse_args()

    db = args.db.resolve()
    if not db.is_file():
        print(f"ERROR: no existe la base de inventario {db}")
        return 1

    os.chdir(RAIZ)
    from src.hands.apps.application_discovery import ApplicationDiscovery
    from src.hands.apps.applications_core import get_application_manager
    from src.hands.calibration.calibration_manager import get_calibration_manager
    from src.hands.inventory.system_inventory import generate_machine_id
    from src.hands.inventory.system_inventory_storage import SystemInventoryStorage

    storage = SystemInventoryStorage(db)
    discovery = ApplicationDiscovery(
        storage=storage,
        calibration=get_calibration_manager(),
        machine_id=generate_machine_id(),
        app_manager=get_application_manager(),
    )
    volumenes = [v.strip().upper() if os.name == "nt" else v.strip() for v in args.volumen] if args.volumen else None

    print("Registrando candidatos de aplicacion desde el inventario (sin reescanear)...")
    print("Puede tardar unos minutos con un escaneo completo de C:.")
    inicio = time.monotonic()

    def _progreso(p: dict) -> None:
        print(
            f"\r  {p.get('volumen')}: {p.get('leidos')} leidas, "
            f"{p.get('registrados')} registradas, {p.get('lanzables')} lanzables "
            f"({time.monotonic() - inicio:.0f} s)",
            end="",
            flush=True,
        )

    try:
        informe = discovery.registrar_candidatos_desde_inventario(
            volumenes=volumenes,
            incluir_winsxs=args.incluir_winsxs,
            progreso=_progreso,
        )
    except KeyboardInterrupt:
        print("\nCancelado. Los lotes ya confirmados quedan guardados.")
        return 1
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            storage.close()
        except Exception as e:
            print(f"Aviso: no se pudo cerrar la base: {e}")

    _mostrar_informe(informe)
    return 0


if __name__ == "__main__":
    codigo = main()
    if os.name == "nt" and not os.environ.get("PROMPT"):
        # Abierto con doble clic: no cerrar la ventana sin dejar leer el resultado.
        input("\nPulsa Enter para cerrar...")
    sys.exit(codigo)
