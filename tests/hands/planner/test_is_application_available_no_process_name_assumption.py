# -*- coding: utf-8 -*-
"""Tests de la unidad 3.8.3.2.

Verifica que ``Planner.is_application_available`` resuelve la aplicación a
partir de fuentes verificables (``ApplicationPreflight``/``resolve_executable``)
sin asumir que el nombre del proceso coincide con el nombre comercial
(por ejemplo, no construir ``f"{app_name.lower()}.exe"`` como ejecutable).
"""

from unittest.mock import patch

from src.hands.planner.planner import Planner  # noqa: E402


def test_is_application_available_no_asume_nombre_proceso_igual_nombre_comercial():
    """Para "Google Chrome" no se asume que el ejecutable es
    "google chrome.exe"; se pasa el nombre real a ApplicationPreflight.check
    y no se construye un ejecutable a partir del nombre comercial."""
    planner = Planner()

    with patch(
        "src.hands.application_preflight.ApplicationPreflight.check"
    ) as mock_check:
        mock_check.return_value = {
            "allowed": True,
            "confidence": "high",
            "executable_path": "chrome.exe",
        }

        result = planner.is_application_available("Google Chrome")

        assert result is True
        call_dict = mock_check.call_args[0][0]
        assert call_dict["name"] == "Google Chrome"
        # No debe construirse un ejecutable asumiendo nombre_proceso == nombre_comercial
        assert call_dict.get("executable") != "google chrome.exe"


def test_is_application_available_nombre_comercial_con_espacio_no_genera_executable_falso():
    """Un nombre comercial con espacios ("Microsoft Edge") no se transforma en
    "microsoft edge.exe"; se respeta el nombre real como origen de resolución."""
    planner = Planner()

    with patch(
        "src.hands.application_preflight.ApplicationPreflight.check"
    ) as mock_check:
        mock_check.return_value = {
            "allowed": True,
            "confidence": "high",
            "executable_path": "msedge.exe",
        }

        result = planner.is_application_available("Microsoft Edge")

        assert result is True
        call_dict = mock_check.call_args[0][0]
        assert call_dict["name"] == "Microsoft Edge"
        assert call_dict.get("executable") != "microsoft edge.exe"
