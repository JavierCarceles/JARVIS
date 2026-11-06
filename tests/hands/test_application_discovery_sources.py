# -*- coding: utf-8 -*-
"""Identificacion de fuentes reales de descubrimiento de aplicaciones en Windows.

Cubre la unidad 3.8.1.2 del roadmap: identificar fuentes reales disponibles en
Windows: aplicaciones instaladas, accesos directos, rutas registradas, PATH y
procesos/ventanas activos cuando procede.

Es una prueba de identificacion/inspeccion de lectura sola: no lanza, no
instala ni modifica ninguna aplicacion. Cada fuente se enumera de forma
independiente (un fallo en una fuente no detiene las demas) y se registra su
cobertura, permisos y limitaciones con evidencia real de ejecucion.

Reutiliza unicamente implementaciones y contratos reales:
- CalibrationManager.discover_applications (Get-StartApps, .lnk del menu Inicio,
  AppX, registro de desinstaladores) -> aplicaciones instaladas.
- os.environ["PATH"] -> rutas registradas en PATH.
- registro App Paths de Windows (HKCU/HKLM) -> rutas registradas de ejecutables.
- psutil.process_iter -> procesos activos.
- pygetwindow (getAllWindows/getActiveWindow) -> ventanas activas/foreground.
"""
from __future__ import annotations

import os
import winreg
from typing import Any, Dict, List

import psutil
import pygetwindow as gw
import pytest
from unittest.mock import patch

from src.hands.calibration_manager import CalibrationManager

_APP_PATHS_ROOTS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
]


def _make_manager() -> CalibrationManager:
    """Instancia CalibrationManager mockeando dependencias pesadas de __init__."""
    with patch(
        "src.hands.calibration_manager.get_screen_manager", return_value=None
    ), patch(
        "src.hands.calibration_manager.get_calibration_config", return_value={}
    ), patch(
        "src.hands.universal_visual_calibrator.UniversalVisualCalibrator",
        return_value=None,
    ):
        return CalibrationManager()


def _sample(items: List[Any], limit: int = 12) -> List[Any]:
    return list(items)[:limit]


def _source(source: str, ok: bool, count: int, samples: List[Any], error: str = None,
            coverage: str = "", limitations: str = "", **extra: Any) -> Dict[str, Any]:
    datos: Dict[str, Any] = {
        "source": source,
        "ok": ok,
        "count": count,
        "samples": samples,
        "error": error,
        "coverage": coverage,
        "limitations": limitations,
    }
    datos.update(extra)
    return datos


def identify_installed_applications() -> Dict[str, Any]:
    """Aplicaciones instaladas descubiertas por el mecanismo real del sistema."""
    try:
        manager = _make_manager()
        apps = manager.discover_applications() or []
        by_source: Dict[str, int] = {}
        for app in apps:
            src = str(app.get("source", "desconocido"))
            by_source[src] = by_source.get(src, 0) + 1
        samples = [
            {
                "name": app.get("name"),
                "app_id": app.get("app_id") or "",
                "path": app.get("path") or "",
                "source": app.get("source") or "",
            }
            for app in _sample(apps)
        ]
        return _source(
            "aplicaciones_instaladas",
            ok=True,
            count=len(apps),
            samples=samples,
            coverage=(
                "Get-StartApps (menu Inicio con AppID), accesos directos .lnk del "
                "menu Inicio (APPDATA y ProgramData, nivel raiz sin recursion por "
                "disco, cumple 3.8.1.4), paquetes AppX y registro de desinstaladores "
                "(HKCU/HKLM/WOW6432Node Uninstall)."
            ),
            limitations=(
                "Filtrado por _should_ignore_application; los metadatos de "
                "desinstalador/shortcut solo se anaden si el path existe en disco "
                "(os.path.isfile); fuentes sin path usable quedan excluidas; no se "
                "usa busqueda recursiva por todo el disco como mecanismo por defecto "
                "(3.8.1.4)."
            ),
        )
    except Exception as exc:  # pragma: no cover - evidencia de fallo de fuente
        return _source(
            "aplicaciones_instaladas",
            ok=False,
            count=0,
            samples=[],
            error=f"{type(exc).__name__}: {exc}",
        )


def identify_path_routes() -> Dict[str, Any]:
    """Rutas registradas en la variable de entorno PATH."""
    try:
        raw_path = os.environ.get("PATH", "")
        dirs = [d for d in raw_path.split(os.pathsep) if d]
        existing = [d for d in dirs if os.path.isdir(d)]
        missing = [d for d in dirs if not os.path.isdir(d)]
        # Muestra acotada de ejecutables .exe encontrados en PATH (sin recorrer
        # todo el disco: solo primera capa de cada carpeta PATH).
        exe_samples: List[str] = []
        for directory in existing:
            try:
                for entry in os.listdir(directory):
                    if entry.lower().endswith(".exe") and len(exe_samples) < 40:
                        exe_samples.append(entry)
            except (OSError, PermissionError):
                continue
        return _source(
            "rutas_registradas_path",
            ok=True,
            count=len(dirs),
            samples={
                "total_dirs": len(dirs),
                "existing_dirs": len(existing),
                "missing_dirs": len(missing),
                "exe_sample": _sample(sorted(set(exe_samples))),
            },
            coverage="Variable de entorno PATH del usuario/proceso actual.",
            limitations=(
                "Solo se inspecciona la primera capa de cada carpeta PATH; no se "
                "hace busqueda recursiva por el disco (evitado por diseno, 3.8.1.4)."
            ),
        )
    except Exception as exc:  # pragma: no cover - evidencia de fallo de fuente
        return _source(
            "rutas_registradas_path",
            ok=False,
            count=0,
            samples={},
            error=f"{type(exc).__name__}: {exc}",
        )


def identify_app_paths_registry() -> Dict[str, Any]:
    """Rutas registradas de ejecutables en el registro de Windows (App Paths)."""
    entries: List[Dict[str, str]] = []
    errors: List[str] = []
    for hive, root in _APP_PATHS_ROOTS:
        try:
            with winreg.OpenKey(hive, root) as key:
                index = 0
                while True:
                    try:
                        exe_name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(key, exe_name) as subkey:
                            path, _ = winreg.QueryValueEx(subkey, "")
                            exe_path, _ = winreg.QueryValueEx(subkey, "Path")
                    except OSError:
                        path = ""
                        exe_path = ""
                    entries.append(
                        {
                            "hive": "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM",
                            "exe": exe_name,
                            "path": path,
                            "path_env": exe_path,
                        }
                    )
        except OSError as exc:
            errors.append(f"{root}: {type(exc).__name__}: {exc}")
    return _source(
        "rutas_registradas_app_paths",
        ok=len(errors) == 0,
        count=len(entries),
        samples=_sample(entries),
        error="; ".join(errors) if errors else None,
        coverage="HKCU y HKLM Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\*",
        limitations=(
            "Cada entrada es un ejecutable concreto registrado por instalador; no "
            "cubre aplicaciones sin registro en App Paths."
        ),
    )


def identify_active_processes() -> Dict[str, Any]:
    """Procesos activos en el sistema."""
    processes: List[Dict[str, Any]] = []
    access_denied = 0
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                processes.append({"pid": info.get("pid"), "name": info.get("name") or ""})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                access_denied += 1
                continue
    except Exception as exc:  # pragma: no cover - evidencia de fallo de fuente
        return _source(
            "procesos_activos",
            ok=False,
            count=0,
            samples=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    return _source(
        "procesos_activos",
        ok=True,
        count=len(processes),
        samples=_sample(processes),
        coverage="psutil.process_iter sobre todos los PIDs visibles al proceso.",
        limitations=(
            f"psutil.AccessDenied en {access_denied} procesos (tipico en procesos del "
            "sistema sin privilegios elevados)."
        ),
    )


def identify_active_windows() -> Dict[str, Any]:
    """Ventanas activas y ventana foreground."""
    try:
        windows = gw.getAllWindows() or []
        foreground = gw.getActiveWindow()
        samples = [
            {"title": w.title, "pid": getattr(w, "_pid", None)}
            for w in _sample(windows)
        ]
        return _source(
            "ventanas_activas",
            ok=True,
            count=len(windows),
            samples=samples,
            coverage="pygetwindow.getAllWindows + getActiveWindow (ventana foreground).",
            limitations=(
                "Titulos pueden estar vacios para ventanas sin titulo o inaccesibles; "
                "no se lanza ninguna aplicacion."
            ),
            foreground_title=foreground.title if foreground else None,
        )
    except Exception as exc:  # pragma: no cover - evidencia de fallo de fuente
        return _source(
            "ventanas_activas",
            ok=False,
            count=0,
            samples=[],
            error=f"{type(exc).__name__}: {exc}",
        )


def identify_all_discovery_sources() -> Dict[str, Any]:
    """Ejecuta todas las fuentes de descubrimiento y devuelve su resultado."""
    return {
        "aplicaciones_instaladas": identify_installed_applications(),
        "rutas_registradas_path": identify_path_routes(),
        "rutas_registradas_app_paths": identify_app_paths_registry(),
        "procesos_activos": identify_active_processes(),
        "ventanas_activas": identify_active_windows(),
    }


class TestIdentificacionFuentesDescubrimientoWindows:
    """Evidencia real de las fuentes de descubrimiento de aplicaciones en Windows."""

    def test_todas_las_fuentes_retornan_estructura_bien_formada(self):
        """Cada fuente ejecuta sin fallar y devuelve diccionario con campos esperados."""
        resultado = identify_all_discovery_sources()
        fuentes_esperadas = {
            "aplicaciones_instaladas",
            "rutas_registradas_path",
            "rutas_registradas_app_paths",
            "procesos_activos",
            "ventanas_activas",
        }
        assert set(resultado.keys()) == fuentes_esperadas, resultado.keys()
        for fuente, datos in resultado.items():
            assert isinstance(datos, dict), fuente
            for clave in ("source", "ok", "count", "samples", "error", "coverage", "limitations"):
                assert clave in datos, (fuente, clave)
            assert isinstance(datos["ok"], bool)
            assert isinstance(datos["count"], int) and datos["count"] >= 0
            assert isinstance(datos["samples"], (list, dict))

    def test_fuente_instaladas_retorna_resultados_reales(self):
        """La fuente de aplicaciones instaladas ejecuta el mecanismo real y reporta hallazgos."""
        datos = identify_installed_applications()
        print("\n=== EVIDENCIA REAL 3.8.1.2 - aplicaciones_instaladas ===")
        print(datos)
        assert datos["ok"] is True, f"La fuente de aplicaciones instaladas fallo: {datos.get('error')}"
        assert datos["count"] >= 0
        assert "coverage" in datos and datos["coverage"]

    def test_imprime_resumen_evidencia_todas_las_fuentes(self):
        """Imprime el resumen completo de evidencia real de cada fuente (para registro canonico)."""
        resultado = identify_all_discovery_sources()
        print("\n=== EVIDENCIA REAL 3.8.1.2 - TODAS LAS FUENTES ===")
        for fuente, datos in resultado.items():
            print(f"\n--- {fuente} ---")
            print(datos)
