# -*- coding: utf-8 -*-
"""Tests para CalibrationManager.get_discovery_source_report (3.8.1.5).

Registra cobertura, permisos y limitaciones de cada fuente de descubrimiento
de aplicaciones. Es una prueba de lectura sola: no lanza, ni instala, ni
modifica ninguna aplicacion.
"""
from __future__ import annotations

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

_EXPECTED_FIELDS = {
    "source", "ok", "count", "samples", "error",
    "coverage", "permissions", "limitations",
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


def test_get_discovery_source_report_retorna_todas_las_fuentes():
    """El reporte contiene exactamente las 5 fuentes esperadas."""
    manager = _make_manager()
    report = manager.get_discovery_source_report()
    assert isinstance(report, dict)
    assert set(report.keys()) == _EXPECTED_SOURCES, report.keys()


def test_get_discovery_source_report_cada_fuente_tiene_campos_esperados():
    """Cada fuente del reporte tiene los campos requeridos."""
    manager = _make_manager()
    report = manager.get_discovery_source_report()
    for nombre, datos in report.items():
        assert isinstance(datos, dict), nombre
        assert _EXPECTED_FIELDS.issubset(set(datos.keys())), (nombre, datos.keys())
        assert isinstance(datos["ok"], bool)
        assert isinstance(datos["count"], int) and datos["count"] >= 0
        assert isinstance(datos["coverage"], str) and datos["coverage"]
        assert isinstance(datos["permissions"], str) and datos["permissions"]
        assert isinstance(datos["limitations"], str) and datos["limitations"]
        if datos["error"] is not None:
            assert isinstance(datos["error"], str)


def test_get_discovery_source_report_fuente_instaladas_retorna_resultados_reales():
    """La fuente de aplicaciones instaladas ejecuta el mecanismo real."""
    manager = _make_manager()
    report = manager.get_discovery_source_report()
    datos = report["aplicaciones_instaladas"]
    print("\n=== EVIDENCIA REAL 3.8.1.5 - aplicaciones_instaladas ===")
    print(datos)
    assert datos["ok"] is True, f"Fallo: {datos.get('error')}"
    assert datos["count"] >= 0
    assert isinstance(datos["samples"], list)


def test_get_discovery_source_report_es_lectura_sola_no_modifica_estado():
    """El reporte no modifica el cache de metadatos ni el estado del gestor."""
    manager = _make_manager()
    # Cargar metadatos primero
    _ = manager.discover_applications()
    cache_before = manager._application_metadata_loaded
    # Generar reporte
    _ = manager.get_discovery_source_report()
    assert manager._application_metadata_loaded == cache_before


def test_get_discovery_source_report_coverage_permissions_limitations_no_vacíos():
    """Coverage, permissions y limitations son strings no vacíos en cada fuente."""
    manager = _make_manager()
    report = manager.get_discovery_source_report()
    for nombre, datos in report.items():
        assert datos["coverage"], f"{nombre}: coverage vacio"
        assert datos["permissions"], f"{nombre}: permissions vacio"
        assert datos["limitations"], f"{nombre}: limitations vacio"


def test_get_discovery_source_report_imprime_resumen_completo():
    """Imprime el resumen completo del reporte para registro canonico."""
    manager = _make_manager()
    report = manager.get_discovery_source_report()
    print("\n=== EVIDENCIA REAL 3.8.1.5 - REPORTE COMPLETO ===")
    for nombre, datos in report.items():
        print(f"\n--- {nombre} ---")
        print(datos)
    assert len(report) == 5


def test_get_discovery_source_report_instaladas_por_fuente_desglosado():
    """La fuente de aplicaciones_instaladas incluye desglose by_source cuando hay datos."""
    manager = _make_manager()
    report = manager.get_discovery_source_report()
    datos = report["aplicaciones_instaladas"]
    if datos["ok"] and datos["count"] > 0:
        assert "by_source" in datos
        assert isinstance(datos["by_source"], dict)


class TestDiscoverySourceReport3815:
    """Evidencia real de 3.8.1.5: cobertura, permisos y limitaciones de cada fuente."""

    def test_todas_las_fuentes_estan_presentes(self):
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        assert set(report.keys()) == _EXPECTED_SOURCES

    def test_instaladas_ok_con_evidencia_real(self):
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        datos = report["aplicaciones_instaladas"]
        assert datos["ok"] is True

    def test_path_ok_con_coverage_y_limitations(self):
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        datos = report["rutas_registradas_path"]
        assert datos["ok"] is True
        assert datos["coverage"]
        assert datos["limitations"]

    def test_app_paths_con_coverage_y_limitations(self):
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        datos = report["rutas_registradas_app_paths"]
        assert datos["coverage"]
        assert datos["permissions"]
        assert datos["limitations"]

    def test_procesos_con_coverage_y_limitations(self):
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        datos = report["procesos_activos"]
        assert datos["coverage"]
        assert datos["permissions"]
        assert datos["limitations"]

    def test_ventanas_con_coverage_y_limitations(self):
        manager = _make_manager()
        report = manager.get_discovery_source_report()
        datos = report["ventanas_activas"]
        assert datos["coverage"]
        assert datos["permissions"]
        assert datos["limitations"]
