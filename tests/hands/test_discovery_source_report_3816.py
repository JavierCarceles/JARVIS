# -*- coding: utf-8 -*-
"""Tests para CalibrationManager.get_discovery_source_report (3.8.1.6).

Resultados reales de las fuentes, fuentes inaccesibles y resultados vacios.

Es una prueba de lectura sola: no lanza, ni instala, ni modifica ninguna
aplicacion.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.hands.calibration_manager import CalibrationManager

_EXPECTED_SOURCES = {
    "aplicaciones_instaladas",
    "rutas_registradas_path",
    "rutas_registradas_app_paths",
    "procesos_activos",
    "ventanas_activas",
}


def _make_manager() -> CalibrationManager:
    with patch(
        "src.hands.calibration_manager.get_screen_manager", return_value=None
    ), patch(
        "src.hands.calibration_manager.get_calibration_config", return_value={}
    ), patch(
        "src.hands.universal_visual_calibrator.UniversalVisualCalibrator",
        return_value=None,
    ):
        return CalibrationManager()


class TestDiscoverySourceReport3816:
    """Pruebas de 3.8.1.6: resultados reales de las fuentes, fuentes inaccesibles y resultados vacios.

    Cada fuente se prueba de forma isolada. Cuando una fuente falla, las demas
    siguen reportando porque cada una esta en su propio bloque try/except del reporte.
    El descubrimiento real (discover_applications) se mockea a [] en las pruebas que
    no lo ejercitan, para aislar cada fuente y evitar ejecuciones innecesarias de PowerShell.
    """

    # ------------------------------------------------------------------
    # Fuentes inaccesibles: la fuente ejecuta pero falla -> ok=False, error, count=0
    # ------------------------------------------------------------------

    def test_fuente_instaladas_inaccesible_reporta_ok_falso_con_error(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager,
            "discover_applications",
            side_effect=RuntimeError("PowerShell no disponible"),
        ):
            report = manager.get_discovery_source_report()
        assert set(report.keys()) == _EXPECTED_SOURCES  # independencia del reporte
        datos = report["aplicaciones_instaladas"]
        assert datos["ok"] is False
        assert datos["count"] == 0
        assert datos["samples"] == []
        assert isinstance(datos["error"], str) and datos["error"]

    def test_fuente_path_inaccesible_reporta_ok_falso_con_error(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch.object(os.path, "isdir", side_effect=OSError("acceso denegado")):
            report = manager.get_discovery_source_report()
        assert set(report.keys()) == _EXPECTED_SOURCES
        datos = report["rutas_registradas_path"]
        assert datos["ok"] is False
        assert datos["count"] == 0
        assert isinstance(datos["error"], str) and datos["error"]

    def test_fuente_app_paths_inaccesible_reporta_ok_falso_con_error(self):
        import winreg

        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch.object(winreg, "OpenKey", side_effect=OSError("clave no accesible")):
            report = manager.get_discovery_source_report()
        assert set(report.keys()) == _EXPECTED_SOURCES
        datos = report["rutas_registradas_app_paths"]
        assert datos["ok"] is False
        assert isinstance(datos["error"], str) and datos["error"]

    def test_fuente_procesos_inaccesible_reporta_ok_falso_con_error(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch(
            "src.hands.calibration_manager.subprocess.run",
            side_effect=RuntimeError("tasklist no ejecutable"),
        ):
            report = manager.get_discovery_source_report()
        assert set(report.keys()) == _EXPECTED_SOURCES
        datos = report["procesos_activos"]
        assert datos["ok"] is False
        assert isinstance(datos["error"], str) and datos["error"]

    def test_fuente_ventanas_inaccesible_reporta_ok_falso_con_error(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch(
            "src.hands.calibration_manager.gw.getAllWindows",
            side_effect=Exception("no se pueden enumerar ventanas"),
        ):
            report = manager.get_discovery_source_report()
        assert set(report.keys()) == _EXPECTED_SOURCES
        datos = report["ventanas_activas"]
        assert datos["ok"] is False
        assert isinstance(datos["error"], str) and datos["error"]

    # ------------------------------------------------------------------
    # Resultados vacios: la fuente ejecuta correctamente pero no devuelve datos
    # ------------------------------------------------------------------

    def test_fuente_instaladas_resultado_vacio(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ):
            report = manager.get_discovery_source_report()
        datos = report["aplicaciones_instaladas"]
        assert datos["ok"] is True
        assert datos["count"] == 0
        assert datos["samples"] == []
        assert datos["error"] is None

    def test_fuente_path_resultado_vacio(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch.dict("os.environ", {"PATH": ""}):
            report = manager.get_discovery_source_report()
        datos = report["rutas_registradas_path"]
        assert datos["ok"] is True
        assert datos["count"] == 0
        assert datos["samples"]["total_dirs"] == 0
        assert datos["samples"]["existing_dirs"] == 0
        assert datos["error"] is None

    def test_fuente_procesos_resultado_vacio(self):
        manager = _make_manager()
        fake_result = type(
            "FakeCompletedProcess", (), {"returncode": 0, "stdout": ""}
        )()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch(
            "src.hands.calibration_manager.subprocess.run", return_value=fake_result
        ):
            report = manager.get_discovery_source_report()
        datos = report["procesos_activos"]
        assert datos["ok"] is True
        assert datos["count"] == 0
        assert datos["samples"] == []
        assert datos["error"] is None

    def test_fuente_ventanas_resultado_vacio(self):
        manager = _make_manager()
        with patch.object(
            CalibrationManager, "discover_applications", return_value=[]
        ), patch(
            "src.hands.calibration_manager.gw.getAllWindows", return_value=[]
        ), patch(
            "src.hands.calibration_manager.gw.getActiveWindow", return_value=None
        ):
            report = manager.get_discovery_source_report()
        datos = report["ventanas_activas"]
        assert datos["ok"] is True
        assert datos["count"] == 0
        assert datos["samples"] == []
        assert datos["foreground_title"] is None
        assert datos["error"] is None

    # ------------------------------------------------------------------
    # Resultados reales: ejecucion sin mocks sobre la maquina real
    # ------------------------------------------------------------------

    def test_fuente_instaladas_resultado_real_en_maquina(self):
        """Ejecucion real (sin mocks) de aplicaciones_instaladas en esta maquina."""
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        datos = report["aplicaciones_instaladas"]
        print("\n=== EVIDENCIA REAL 3.8.1.6 - aplicaciones_instaladas ===")
        print(datos)
        assert datos["ok"] is True, f"Fallo: {datos.get('error')}"
        assert isinstance(datos["samples"], list)
        assert datos["error"] is None
