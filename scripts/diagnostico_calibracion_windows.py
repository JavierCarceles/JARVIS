# -*- coding: ascii -*-
"""
Diagnostico previo a la calibracion real en Windows (solo lectura).

No abre, mueve ni cierra aplicaciones y no envia teclado ni raton. Comprueba en
segundos lo que suele hacer fallar o alargar `test_calibracion_aplicaciones_
entorno_real.py`, para no descubrirlo tras minutos de prueba GUI:

1. Python, SQLite (>= 3.33 para la verificacion por tabla) y SO.
2. Adaptador de escritorio: capacidades y monitores (monitor de pruebas).
3. Ollama: servidor, modelo qwen3-vl:8b-instruct y una llamada corta con
   imagen pequena y tiempo maximo (mide la latencia real del equipo).
4. Inventario: tamano y tiempo de la verificacion de integridad al abrir.
5. PowerShell: tiempo de enumerar shell:AppsFolder (preflight por AUMID).
6. Resolucion sin lanzar: "calculadora", "calculator" y "notepad".

Uso (desde la raiz del proyecto):
    python scripts/diagnostico_calibracion_windows.py
Devuelve 0 si todo lo imprescindible esta bien y 1 si algo lo impide.
"""

from __future__ import annotations

import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

MODELO = "qwen3-vl:8b-instruct"
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_problemas = []


def _linea(estado: str, texto: str) -> None:
    print("[%s] %s" % (estado, texto), flush=True)


def _ok(texto: str) -> None:
    _linea("OK", texto)


def _aviso(texto: str) -> None:
    _linea("AVISO", texto)


def _fallo(texto: str) -> None:
    _problemas.append(texto)
    _linea("FALLO", texto)


def comprobar_entorno() -> None:
    _ok("Python %s, SQLite %s, %s" % (platform.python_version(), sqlite3.sqlite_version, platform.platform()))
    partes = tuple(int(p) for p in sqlite3.sqlite_version.split(".")[:2])
    if partes < (3, 33):
        _fallo("SQLite %s < 3.33: no admite PRAGMA quick_check(tabla)" % sqlite3.sqlite_version)
    if sys.platform != "win32":
        _fallo("este diagnostico es para Windows (sys.platform=%s)" % sys.platform)


def comprobar_escritorio() -> None:
    try:
        from src.desktop.platform_contract import CapabilityStatus, get_desktop_platform

        adaptador = get_desktop_platform()
        capacidades = adaptador.capabilities()
        for capacidad, informe in capacidades.items():
            estado = getattr(informe, "status", None)
            nombre = getattr(capacidad, "value", str(capacidad))
            if estado == CapabilityStatus.DISPONIBLE:
                _ok("capacidad %s disponible" % nombre)
            else:
                _aviso("capacidad %s: %s %s" % (nombre, getattr(estado, "value", estado),
                                                 getattr(informe, "instructions", "")))
        pantallas = adaptador.enumerate_displays()
        if not pantallas.ok:
            _fallo("no se pudieron enumerar los monitores: %s" % pantallas.error)
            return
        no_principales = [p for p in pantallas.value if not p.is_primary]
        destino = max(no_principales, key=lambda p: p.bounds.right) if no_principales else pantallas.value[0]
        for p in pantallas.value:
            marca = " <- monitor de pruebas" if p.display_id == destino.display_id else ""
            _ok("monitor %s %s escala %.2f%s%s" % (
                p.display_id, p.bounds.to_int_tuple(), float(p.scale_factor or 1.0),
                " (principal)" if p.is_primary else "", marca))
    except Exception as exc:
        _fallo("adaptador de escritorio no disponible: %s" % exc)


def comprobar_ollama() -> None:
    try:
        import ollama
    except ImportError:
        _aviso("paquete ollama no instalado: la calibracion seguira solo con accesibilidad")
        return
    try:
        cliente = ollama.Client(timeout=10)
        modelos = [getattr(m, "model", None) or m.get("model") or m.get("name") for m in cliente.list()["models"]]
    except Exception as exc:
        _aviso("Ollama no responde (%s): arrancarlo oculto con "
               "Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden" % exc)
        return
    if MODELO not in modelos:
        _aviso("modelo %s no descargado (hay: %s): `ollama pull %s`" % (MODELO, modelos, MODELO))
        return
    _ok("Ollama responde y tiene %s" % MODELO)
    try:
        from PIL import Image

        from src.eyes.vision.vision_only import Vision

        fd, ruta = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        Image.new("RGB", (640, 360), "white").save(ruta)
        inicio = time.monotonic()
        respuesta = Vision(model=MODELO).analyze_image(
            ruta, 'Devuelve {"elements": []} en JSON.', num_predict=64, timeout=180.0,
        )
        segundos = time.monotonic() - inicio
        os.unlink(ruta)
        if str(respuesta).startswith("ERROR"):
            _aviso("llamada a Qwen3-VL fallida en %.1f s: %s" % (segundos, respuesta[:200]))
        elif segundos > 60:
            _aviso("Qwen3-VL respondio en %.1f s (carga del modelo incluida): sin GPU la deteccion "
                   "visual sera lenta; el pipeline la corta a los 300 s y usa lo recibido" % segundos)
        else:
            _ok("Qwen3-VL respondio en %.1f s (carga del modelo incluida)" % segundos)
    except Exception as exc:
        _aviso("prueba de Qwen3-VL no ejecutada: %s" % exc)


def comprobar_inventario() -> None:
    try:
        from src.hands.calibration.calibration_profile_storage import default_db_path
        from src.hands.inventory.system_inventory_storage import SystemInventoryStorage

        ruta = default_db_path()
        if not ruta.exists():
            _aviso("no existe %s: se creara vacio al guardar el primer perfil" % ruta.name)
            return
        storage = SystemInventoryStorage(ruta)
        inicio = time.monotonic()
        try:
            resultado = storage.verify_integrity_al_abrir()
        finally:
            storage.close()
        segundos = time.monotonic() - inicio
        texto = "inventario %.0f MB: verificacion al abrir %s en %.2f s (%s)" % (
            ruta.stat().st_size / (1024 * 1024), resultado.get("modo"), segundos,
            "ok" if resultado.get("ok") else resultado.get("error"))
        (_ok if resultado.get("ok") else _fallo)(texto)
    except Exception as exc:
        _fallo("inventario no verificable: %s" % exc)


def comprobar_powershell() -> None:
    script = ("$s = New-Object -ComObject Shell.Application; "
              "$n = @($s.Namespace('shell:AppsFolder').Items()).Count; Write-Output $n")
    inicio = time.monotonic()
    try:
        proceso = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=60, creationflags=_SIN_VENTANA,
        )
    except Exception as exc:
        _fallo("PowerShell no disponible: %s" % exc)
        return
    segundos = time.monotonic() - inicio
    elementos = (proceso.stdout or "").strip()
    texto = "shell:AppsFolder: %s elementos en %.1f s" % (elementos, segundos)
    if segundos > 25:
        _aviso(texto + " (el preflight espera hasta 30 s)")
    else:
        _ok(texto)


def comprobar_resolucion() -> None:
    try:
        from src.hands.apps.platform_launch import ApplicationLaunchService

        adaptador = ApplicationLaunchService().adapter
        for nombre in ("calculadora", "calculator", "notepad"):
            inicio = time.monotonic()
            resultado = adaptador.resolve(nombre)
            segundos = time.monotonic() - inicio
            destino = getattr(resultado, "target", None)
            texto = "resolver '%s': %s %s en %.1f s" % (
                nombre, getattr(resultado, "status", "?"),
                "%s:%s" % (destino.target_type, destino.target) if destino is not None else "", segundos)
            (_ok if destino is not None else _aviso)(texto)
            if destino is None:
                for alternativa in getattr(resultado, "candidates", None) or []:
                    print("        alternativa %s:%s (fuente %s, confianza %s)" % (
                        alternativa.target_type, alternativa.target, alternativa.source,
                        (alternativa.evidence or {}).get("confianza", "")), flush=True)
                error = getattr(resultado, "error", None)
                if error is not None:
                    print("        motivo: %s" % getattr(error, "message", error), flush=True)
    except Exception as exc:
        _aviso("resolucion no comprobada: %s" % exc)


def main() -> int:
    print("Diagnostico de calibracion (solo lectura; no abre aplicaciones)\n", flush=True)
    comprobar_entorno()
    comprobar_escritorio()
    comprobar_ollama()
    comprobar_inventario()
    comprobar_powershell()
    comprobar_resolucion()
    print("", flush=True)
    if _problemas:
        print("Resultado: %d problema(s) que impiden calibrar:" % len(_problemas))
        for problema in _problemas:
            print("  - %s" % problema)
        return 1
    print("Resultado: nada impide calibrar (revisar los AVISO).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
