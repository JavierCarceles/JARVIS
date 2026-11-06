# -*- coding: utf-8 -*-
"""Tests de ApplicationPreflight.validate_launch_destination.

Cubre la unidad 3.8.3.3: validar que la ruta o destino resuelto exista y
corresponda a un tipo de lanzamiento admitido (ejecutable .exe, acceso
directo .lnk o URI de aplicación con esquema conocido), sin lanzar nada.
"""
import os
import tempfile
from unittest.mock import patch

import pytest

from src.hands.application_preflight import ApplicationPreflight


class TestValidateLaunchDestination:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_existing_exe_is_valid_executable(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            result = self.pf.validate_launch_destination(path)
            assert result["valid"] is True
            assert result["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE
            assert result["destination"] == os.path.abspath(path)
            assert "Ejecutable existente admitido" in result["reason"]
        finally:
            os.unlink(path)

    def test_existing_lnk_is_valid_shortcut(self):
        with tempfile.NamedTemporaryFile(suffix=".lnk", delete=False) as f:
            path = f.name
        try:
            result = self.pf.validate_launch_destination(path)
            assert result["valid"] is True
            assert result["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_SHORTCUT
            assert result["destination"] == os.path.abspath(path)
            assert "Acceso directo existente admitido" in result["reason"]
        finally:
            os.unlink(path)

    def test_admitted_uri_is_valid(self):
        for uri in ("ms-settings:", "microsoft-edge:", "https://example.com", "mailto:a@b.c"):
            result = self.pf.validate_launch_destination(uri)
            assert result["valid"] is True, uri
            assert result["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_URI, uri
            assert result["destination"] == uri, uri

    def test_unknown_uri_scheme_is_invalid(self):
        result = self.pf.validate_launch_destination("custom-app:algo")
        assert result["valid"] is False
        assert result["launch_type"] is None
        assert "no admitido" in result["reason"]

    def test_nonexistent_exe_is_invalid(self):
        result = self.pf.validate_launch_destination(r"C:\No\Existe\app.exe")
        assert result["valid"] is False
        assert result["launch_type"] is None
        assert "no existe" in result["reason"]

    def test_existing_txt_file_is_invalid(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            result = self.pf.validate_launch_destination(path)
            assert result["valid"] is False
            assert result["launch_type"] is None
            assert "no admitido" in result["reason"]
        finally:
            os.unlink(path)

    def test_existing_directory_is_invalid(self):
        with tempfile.TemporaryDirectory() as dirpath:
            result = self.pf.validate_launch_destination(dirpath)
            assert result["valid"] is False
            assert result["launch_type"] is None
            assert "directorio" in result["reason"]

    def test_empty_string_is_invalid(self):
        result = self.pf.validate_launch_destination("")
        assert result["valid"] is False
        assert result["launch_type"] is None

    def test_none_is_invalid(self):
        result = self.pf.validate_launch_destination(None)
        assert result["valid"] is False
        assert result["launch_type"] is None

    def test_whitespace_only_is_invalid(self):
        result = self.pf.validate_launch_destination("   ")
        assert result["valid"] is False
        assert result["launch_type"] is None

    def test_relative_exe_path_is_normalized_and_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            relativo = os.path.relpath(path)
            result = self.pf.validate_launch_destination(relativo)
            assert result["valid"] is True
            assert result["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE
            assert result["destination"] == os.path.abspath(path)
        finally:
            os.unlink(path)
