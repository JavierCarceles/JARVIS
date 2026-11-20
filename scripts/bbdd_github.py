#!/usr/bin/env python3
"""
Copia de la base de inventario de JARVIS en un repositorio PRIVADO de GitHub.

`data/system_inventory.sqlite3` puede ocupar varios GB y contiene las rutas de
todos los ficheros del equipo, asi que no se sube al repositorio publico de
JARVIS (esta en `.gitignore`). Este script la guarda comprimida como adjunto
de una release del repositorio privado `JavierCarceles/JARVIS-datos`, que
solo puede ver y descargar el propietario.

Uso (un solo fichero para todo):

    python scripts/bbdd_github.py            menu: subir o descargar
    python scripts/bbdd_github.py subir      sube la base de este equipo
    python scripts/bbdd_github.py descargar  descarga la ultima copia subida

En Windows tambien se puede abrir con doble clic.

Que hace `subir`:
  1. Comprueba que GitHub CLI (`gh`) esta instalado y con sesion iniciada; si
     no, ofrece instalarlo (winget en Windows, Homebrew en macOS) y abre el
     inicio de sesion en el navegador.
  2. Vuelca el WAL a la base (`wal_checkpoint(TRUNCATE)`) y mantiene una
     transaccion de lectura abierta mientras comprime, para que la copia sea
     coherente. Si JARVIS esta usando la base, pide cerrarlo.
  3. Comprime la base con xz (varios procesos en paralelo) en partes de como
     maximo 1900 MiB (GitHub admite hasta 2 GiB por adjunto).
  4. Sube las partes y `bbdd_manifest.json` (tamanos, SHA-256, equipo, filas)
     a la release, sustituyendo la copia anterior, y borra las partes viejas.

Que hace `descargar`:
  1. Descarga el manifiesto y las partes, comprueba su SHA-256.
  2. Descomprime, comprueba la base con `PRAGMA quick_check` y el tamano.
  3. La deja en `data/system_inventory.sqlite3`, igual que en el equipo de
     origen (si ya habia una, la renombra a `.antes_descarga` tras
     confirmarlo). Si la copia es de otro equipo, JARVIS en este equipo no la
     usa (rechaza bases de otro `machine_id`), pero sirve para consultarla.

Solo usa la biblioteca estandar de Python.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE_POR_DEFECTO = RAIZ / "data" / "system_inventory.sqlite3"
DIR_TEMPORAL = RAIZ / "data" / "_bbdd_tmp"

REPO = "JavierCarceles/JARVIS-datos"
TAG = "bbdd"
MANIFIESTO = "bbdd_manifest.json"
PREFIJO_PARTE = "system_inventory.sqlite3.xz."

TAM_BLOQUE = 256 * 1024 * 1024          # cada bloque se comprime por separado
TAM_MAX_PARTE = 1900 * 1024 * 1024      # GitHub: maximo 2 GiB por adjunto
PRESET_XZ = 9
MB = 1024 * 1024


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

class ErrorBbdd(Exception):
    """Error que se muestra al usuario sin traza."""


def preguntar(texto: str, si_por_defecto: bool, auto_si: bool) -> bool:
    if auto_si:
        return True
    opciones = "[S/n]" if si_por_defecto else "[s/N]"
    try:
        respuesta = input(f"{texto} {opciones} ").strip().lower()
    except EOFError:
        return si_por_defecto
    if not respuesta:
        return si_por_defecto
    return respuesta in ("s", "si", "y", "yes")


def machine_id_local() -> str:
    """Mismo calculo que `generate_machine_id()` de src/hands/inventory/system_inventory.py."""
    node = platform.node() or "unknown"
    system = platform.system() or "unknown"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"jarvis-local-{node}-{system}"))


def sha256_fichero(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(8 * MB), b""):
            h.update(trozo)
    return h.hexdigest()


def progreso(hecho: int, total: int, inicio: float, etiqueta: str) -> None:
    pct = 100.0 * hecho / total if total else 100.0
    seg = max(time.time() - inicio, 0.001)
    print(f"\r  {etiqueta}: {pct:5.1f}%  {hecho / MB:,.0f}/{total / MB:,.0f} MB  "
          f"({hecho / MB / seg:,.0f} MB/s)   ", end="", flush=True)


# ---------------------------------------------------------------------------
# GitHub CLI
# ---------------------------------------------------------------------------

def buscar_gh() -> str | None:
    ruta = shutil.which("gh")
    if ruta:
        return ruta
    candidatos = []
    if os.name == "nt":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                candidatos.append(Path(base) / "GitHub CLI" / "gh.exe")
                candidatos.append(Path(base) / "Programs" / "GitHub CLI" / "gh.exe")
    else:
        candidatos += [Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh")]
    for c in candidatos:
        if c.is_file():
            return str(c)
    return None


def preparar_gh(auto_si: bool) -> str:
    gh = buscar_gh()
    if not gh:
        print("No esta instalado GitHub CLI (gh), que se usa para hablar con GitHub.")
        if os.name == "nt":
            cmd = ["winget", "install", "--id", "GitHub.cli", "-e"]
        elif sys.platform == "darwin":
            cmd = ["brew", "install", "gh"]
        else:
            raise ErrorBbdd("Instala GitHub CLI (https://cli.github.com) y vuelve a ejecutar el script.")
        if not preguntar(f"Instalarlo ahora con: {' '.join(cmd)} ?", True, auto_si):
            raise ErrorBbdd("Sin GitHub CLI no se puede continuar.")
        try:
            subprocess.run(cmd, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise ErrorBbdd(f"No se pudo instalar GitHub CLI ({e}). Instalalo desde https://cli.github.com") from e
        gh = buscar_gh()
        if not gh:
            raise ErrorBbdd("GitHub CLI se instalo pero no se encuentra. Cierra esta ventana y vuelve a ejecutar el script.")

    estado = subprocess.run([gh, "auth", "status", "--hostname", "github.com"],
                            capture_output=True, text=True)
    if estado.returncode != 0:
        print("\nHay que iniciar sesion en GitHub una sola vez. Se abrira el navegador:")
        print("copia el codigo que aparece aqui, pegalo en la web y acepta.\n")
        r = subprocess.run([gh, "auth", "login", "--hostname", "github.com",
                            "--git-protocol", "https", "--web"])
        if r.returncode != 0:
            raise ErrorBbdd("No se inicio sesion en GitHub.")

    r = subprocess.run([gh, "release", "view", TAG, "-R", REPO, "--json", "tagName"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorBbdd(f"No se puede acceder a la release '{TAG}' de {REPO}. "
                        f"Comprueba que has iniciado sesion con la cuenta propietaria.\n{r.stderr.strip()}")
    return gh


def assets_release(gh: str) -> list[str]:
    r = subprocess.run([gh, "release", "view", TAG, "-R", REPO, "--json", "assets"],
                       capture_output=True, text=True, check=True)
    return [a["name"] for a in json.loads(r.stdout).get("assets", [])]


# ---------------------------------------------------------------------------
# Subir
# ---------------------------------------------------------------------------

def _comprimir_bloque(args: tuple[str, int, int, int]) -> bytes:
    ruta, inicio, tam, preset = args
    with open(ruta, "rb") as f:
        f.seek(inicio)
        datos = f.read(tam)
    return lzma.compress(datos, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=preset)


def _datos_base(conn: sqlite3.Connection) -> dict:
    def escalar(sql: str):
        try:
            return conn.execute(sql).fetchone()[0]
        except sqlite3.Error:
            return None
    maquinas = []
    try:
        maquinas = [r[0] for r in conn.execute("SELECT machine_id FROM machines")]
    except sqlite3.Error:
        pass
    return {
        "machine_ids": maquinas,
        "schema_version": escalar("SELECT max(version) FROM schema_version"),
        "filas_file_entries": escalar("SELECT count(*) FROM file_entries"),
        "filas_application_candidates": escalar("SELECT count(*) FROM application_candidates"),
    }


def subir(db: Path, auto_si: bool) -> None:
    if not db.is_file():
        raise ErrorBbdd(f"No existe la base {db}")
    gh = preparar_gh(auto_si)

    print(f"\nBase: {db} ({db.stat().st_size / MB:,.0f} MB)")
    conn = sqlite3.connect(str(db), timeout=5)
    try:
        try:
            busy, wal, copiadas = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        except sqlite3.OperationalError as e:
            raise ErrorBbdd(f"La base esta bloqueada ({e}). Cierra JARVIS y vuelve a intentarlo.") from e
        if busy or (wal > 0 and wal != copiadas):
            raise ErrorBbdd("JARVIS (u otro programa) esta usando la base. Cierralo y vuelve a intentarlo.")
        # Transaccion de lectura abierta: impide que un checkpoint modifique el
        # fichero principal mientras se comprime, asi la copia es coherente.
        conn.execute("BEGIN")
        print("  Leyendo datos de la base...")
        info = _datos_base(conn)
        tam_total = db.stat().st_size

        if DIR_TEMPORAL.exists():
            shutil.rmtree(DIR_TEMPORAL)
        DIR_TEMPORAL.mkdir(parents=True)

        trabajos = [(str(db), ini, min(TAM_BLOQUE, tam_total - ini), PRESET_XZ)
                    for ini in range(0, tam_total, TAM_BLOQUE)]
        # xz -9 usa unos 700 MB de RAM por proceso: limitamos a 4 procesos.
        procesos = max(1, min(4, os.cpu_count() or 1, len(trabajos)))
        print(f"  Comprimiendo con xz -{PRESET_XZ} en {procesos} procesos "
              f"(en una base de 10 GB tarda unos minutos)...")

        partes: list[Path] = []
        actual = None
        escrito_parte = 0
        leido = 0
        inicio = time.time()

        def nueva_parte():
            nonlocal actual, escrito_parte
            if actual:
                actual.close()
            ruta = DIR_TEMPORAL / f"{PREFIJO_PARTE}{len(partes) + 1:03d}"
            partes.append(ruta)
            actual = open(ruta, "wb")
            escrito_parte = 0

        nueva_parte()
        with ProcessPoolExecutor(max_workers=procesos) as ex:
            pendientes = []
            siguiente = 0
            while siguiente < len(trabajos) or pendientes:
                while siguiente < len(trabajos) and len(pendientes) < procesos * 2:
                    pendientes.append((trabajos[siguiente][2], ex.submit(_comprimir_bloque, trabajos[siguiente])))
                    siguiente += 1
                tam_bloque, futuro = pendientes.pop(0)
                datos = futuro.result()
                vista = memoryview(datos)
                while vista:
                    if escrito_parte >= TAM_MAX_PARTE:
                        nueva_parte()
                    n = min(len(vista), TAM_MAX_PARTE - escrito_parte)
                    actual.write(vista[:n])
                    escrito_parte += n
                    vista = vista[n:]
                leido += tam_bloque
                progreso(leido, tam_total, inicio, "Comprimiendo")
        actual.close()
        print()
    finally:
        conn.close()

    tam_comp = sum(p.stat().st_size for p in partes)
    print(f"  Comprimida: {tam_comp / MB:,.1f} MB en {len(partes)} parte(s) "
          f"({tam_total / max(tam_comp, 1):.1f} veces menos)")

    manifiesto = {
        "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equipo_origen": platform.system(),
        "machine_id_origen": machine_id_local(),
        "tamano_original": tam_total,
        "compresion": f"xz -{PRESET_XZ}, bloques de {TAM_BLOQUE // MB} MiB",
        "partes": [{"nombre": p.name, "tamano": p.stat().st_size, "sha256": sha256_fichero(p)}
                   for p in partes],
        **info,
    }
    ruta_manifiesto = DIR_TEMPORAL / MANIFIESTO
    ruta_manifiesto.write_text(json.dumps(manifiesto, indent=2), encoding="ascii")

    print(f"\nSubiendo a la release privada {REPO} ({TAG})...")
    ficheros = [str(p) for p in partes] + [str(ruta_manifiesto)]
    r = subprocess.run([gh, "release", "upload", TAG, *ficheros, "--clobber", "-R", REPO])
    if r.returncode != 0:
        raise ErrorBbdd(f"Fallo la subida. Los ficheros comprimidos siguen en {DIR_TEMPORAL}; vuelve a ejecutar el script.")

    nuevos = {p.name for p in partes} | {MANIFIESTO}
    for nombre in assets_release(gh):
        if nombre not in nuevos:
            subprocess.run([gh, "release", "delete-asset", TAG, nombre, "-y", "-R", REPO],
                           capture_output=True)
    shutil.rmtree(DIR_TEMPORAL, ignore_errors=True)
    print(f"\nListo. Copia subida a https://github.com/{REPO}/releases/tag/{TAG}")


# ---------------------------------------------------------------------------
# Descargar
# ---------------------------------------------------------------------------

class _Cadena(io.RawIOBase):
    """Lee varias partes seguidas como si fueran un solo fichero."""

    def __init__(self, rutas: list[Path]):
        self._rutas = list(rutas)
        self._f = None

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        while True:
            if self._f is None:
                if not self._rutas:
                    return 0
                self._f = open(self._rutas.pop(0), "rb")
            n = self._f.readinto(b)
            if n:
                return n
            self._f.close()
            self._f = None

    def close(self) -> None:
        if self._f:
            self._f.close()
        super().close()


def _apartar_base_existente(destino: Path, auto_si: bool) -> None:
    if not destino.exists():
        return
    respaldo = destino.with_name(destino.name + ".antes_descarga")
    print(f"\nYa existe {destino}.")
    if not preguntar(f"Renombrarla a {respaldo.name} y poner la descargada en su lugar?", False, auto_si):
        raise ErrorBbdd("Cancelado. No se ha tocado la base local.")
    conn = sqlite3.connect(str(destino), timeout=5)
    try:
        busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.OperationalError:
        busy = 1
    finally:
        conn.close()
    if busy:
        raise ErrorBbdd("La base local esta en uso. Cierra JARVIS y vuelve a intentarlo.")
    for sufijo in ("", "-wal", "-shm"):
        origen = destino.with_name(destino.name + sufijo)
        if origen.exists():
            os.replace(origen, respaldo.with_name(respaldo.name + sufijo))
    print(f"  Base anterior guardada como {respaldo.name}")


def descargar(destino_forzado: Path | None, auto_si: bool) -> None:
    gh = preparar_gh(auto_si)
    if MANIFIESTO not in assets_release(gh):
        raise ErrorBbdd(f"La release {REPO} ({TAG}) aun no tiene ninguna copia. "
                        f"Ejecuta primero 'subir' en el equipo que tiene la base.")

    if DIR_TEMPORAL.exists():
        shutil.rmtree(DIR_TEMPORAL)
    DIR_TEMPORAL.mkdir(parents=True)
    print(f"\nDescargando de {REPO} ({TAG})...")
    r = subprocess.run([gh, "release", "download", TAG, "-R", REPO, "-D", str(DIR_TEMPORAL), "--clobber"])
    if r.returncode != 0:
        raise ErrorBbdd("Fallo la descarga.")

    manifiesto = json.loads((DIR_TEMPORAL / MANIFIESTO).read_text(encoding="ascii"))
    partes = []
    for p in manifiesto["partes"]:
        ruta = DIR_TEMPORAL / p["nombre"]
        if not ruta.is_file() or sha256_fichero(ruta) != p["sha256"]:
            raise ErrorBbdd(f"La parte {p['nombre']} falta o esta danada. Vuelve a ejecutar la descarga.")
        partes.append(ruta)
    print(f"  {len(partes)} parte(s) correctas. Copia creada el {manifiesto['creado']}.")

    destino = destino_forzado or BASE_POR_DEFECTO
    if machine_id_local() not in (manifiesto.get("machine_ids") or []):
        print(f"\n  Esta copia es de OTRO equipo ({manifiesto.get('equipo_origen', '?')}). Se guarda igual que")
        print("  en el original para consultarla; JARVIS en este equipo no la usara (rechaza")
        print("  bases de otro machine_id con InventoryIncompatibleMachineError, sin borrarla).")

    temporal = DIR_TEMPORAL / "descomprimida.sqlite3"
    total = manifiesto["tamano_original"]
    hecho = 0
    inicio = time.time()
    with lzma.open(io.BufferedReader(_Cadena(partes), 8 * MB)) as src, open(temporal, "wb") as dst:
        while True:
            trozo = src.read(16 * MB)
            if not trozo:
                break
            dst.write(trozo)
            hecho += len(trozo)
            progreso(hecho, total, inicio, "Descomprimiendo")
    print()
    if hecho != total:
        raise ErrorBbdd(f"Tamano inesperado ({hecho} en vez de {total} bytes).")

    print("  Comprobando la base (quick_check)...")
    conn = sqlite3.connect(str(temporal))
    try:
        resultado = conn.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        conn.close()
    if resultado != "ok":
        raise ErrorBbdd(f"La base descargada no pasa la comprobacion: {resultado}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    _apartar_base_existente(destino, auto_si)
    os.replace(temporal, destino)
    shutil.rmtree(DIR_TEMPORAL, ignore_errors=True)
    print(f"\nListo. Base guardada en {destino}")


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Sube o descarga la base de inventario de JARVIS "
                                                 f"a/desde la release privada {REPO}.")
    parser.add_argument("accion", nargs="?", choices=["subir", "descargar"])
    parser.add_argument("--db", type=Path, default=BASE_POR_DEFECTO,
                        help="base a subir (por defecto data/system_inventory.sqlite3)")
    parser.add_argument("--destino", type=Path, help="donde dejar la base descargada")
    parser.add_argument("--si", action="store_true", help="responder si a todas las preguntas")
    args = parser.parse_args()

    accion = args.accion
    if not accion:
        print("Base de inventario de JARVIS en GitHub (repositorio privado)\n")
        print("  1) Subir la base de este equipo")
        print("  2) Descargar la ultima copia subida\n")
        eleccion = input("Elige 1 o 2: ").strip()
        accion = {"1": "subir", "2": "descargar"}.get(eleccion)
        if not accion:
            print("Opcion no valida.")
            return 1

    try:
        if accion == "subir":
            subir(args.db.resolve(), args.si)
        else:
            descargar(args.destino.resolve() if args.destino else None, args.si)
        return 0
    except ErrorBbdd as e:
        print(f"\nERROR: {e}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 1


if __name__ == "__main__":
    codigo = main()
    if os.name == "nt" and not os.environ.get("PROMPT"):
        # Abierto con doble clic: no cerrar la ventana sin dejar leer el resultado.
        input("\nPulsa Enter para cerrar...")
    sys.exit(codigo)
