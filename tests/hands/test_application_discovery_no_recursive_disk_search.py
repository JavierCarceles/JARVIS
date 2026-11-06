# -*- coding: utf-8 -*-
"""Verifica que el descubrimiento de aplicaciones no usa busqueda recursiva por disco como mecanismo por defecto.

Cubre la unidad 3.8.1.4 del roadmap: evitar busquedas indiscriminadas o recursivas
por todo el disco como mecanismo por defecto.

Es una prueba de inspeccion de codigo fuente (lectura sola) y de ejecucion real
acotada: no lanza, no instala ni modifica ninguna aplicacion.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.hands.calibration_manager import CalibrationManager


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


def test_load_application_installation_metadata_no_usa_busqueda_recursiva_por_disco():
    """_load_application_installation_metadata no usa Get-ChildItem -Recurse ni
    ninguna busqueda recursiva por disco (os.walk / rglob / iglob) como mecanismo
    por defecto de descubrimiento de aplicaciones (requisito 3.8.1.4)."""
    import inspect

    source = inspect.getsource(CalibrationManager._load_application_installation_metadata)
    assert "-Recurse" not in source, (
        "_load_application_installation_metadata aun usa busqueda recursiva por disco (-Recurse)"
    )
    assert "os.walk" not in source
    assert "rglob" not in source
    assert "iglob" not in source


def test_descubrimiento_aplicaciones_ejecuta_mecanismo_acotado_sin_recorrer_disco():
    """discover_applications ejecuta el mecanismo real (acotado, no recursivo por
    disco) y retorna una lista de diccionarios bien formada sin fallar."""
    manager = _make_manager()
    apps = manager.discover_applications() or []
    assert isinstance(apps, list)
    for app in apps:
        assert isinstance(app, dict)
        assert "name" in app
        assert isinstance(app.get("name", ""), str)


def test_no_hay_rutas_de_disco_raiz_en_metadatos_instalacion():
    """El script de carga de metadatos no referencia rutas de disco raiz (C:, D:, etc.)
    como mecanismo por defecto de descubrimiento."""
    import inspect

    source = inspect.getsource(CalibrationManager._load_application_installation_metadata)
    for raiz in ("C:\\", "D:\\", "E:\\"):
        assert raiz not in source, (
            f"_load_application_installation_metadata referencia ruta de disco raiz {raiz}"
        )
