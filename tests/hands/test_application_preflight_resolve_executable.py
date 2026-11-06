# -*- coding: utf-8 -*-
"""Tests de ApplicationPreflight.resolve_executable y sus estrategias reales.

Cubre la unidad 3.8.3.1: reutilizar ApplicationPreflight.resolve_executable y
sus estrategias reales (resolución por shell:AppsFolder, target string y
_is_executable) antes de crear lógica de resolución de ejecutables nueva.
"""
import os
import tempfile
from unittest.mock import patch

import pytest

from src.hands.application_preflight import ApplicationPreflight


class TestIsExecutable:
    def test_existing_exe_returns_true(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            assert ApplicationPreflight._is_executable(path) is True
        finally:
            os.unlink(path)

    def test_nonexistent_exe_returns_false(self):
        assert ApplicationPreflight._is_executable(r"C:\No\Existe\app.exe") is False

    def test_existing_non_exe_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            assert ApplicationPreflight._is_executable(path) is False
        finally:
            os.unlink(path)

    def test_empty_path_returns_false(self):
        assert ApplicationPreflight._is_executable("") is False
        assert ApplicationPreflight._is_executable(None) is False


class TestResolveFromTargetString:
    def test_valid_target_returns_path(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            resultado = ApplicationPreflight._resolve_from_target_string(path)
            assert resultado == path
        finally:
            os.unlink(path)

    def target_with_quotes_is_stripped(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            resultado = ApplicationPreflight._resolve_from_target_string(f'"{path}"')
            assert resultado == path
        finally:
            os.unlink(path)

    def test_nonexistent_target_returns_none(self):
        assert (
            ApplicationPreflight._resolve_from_target_string(
                r"C:\No\Existe\app.exe"
            )
            is None
        )

    def test_non_exe_target_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            assert ApplicationPreflight._resolve_from_target_string(path) is None
        finally:
            os.unlink(path)

    def test_empty_target_returns_none(self):
        assert ApplicationPreflight._resolve_from_target_string("") is None
        assert ApplicationPreflight._resolve_from_target_string(None) is None


class TestResolveExecutable:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()
        self.pf.clear_cache()

    def test_uses_cache_on_repeated_call(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            with patch.object(
                self.pf, "_resolve_from_apps_folder", return_value=path
            ) as mock_resolve:
                primera = self.pf.resolve_executable("Chrome", "Google.Chrome")
                segunda = self.pf.resolve_executable("Chrome", "Google.Chrome")
                assert primera == path
                assert segunda == path
                # _resolve_from_apps_folder solo se invoca una vez por la caché.
                assert mock_resolve.call_count == 1
        finally:
            os.unlink(path)

    def test_casefold_cache_key(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            with patch.object(
                self.pf, "_resolve_from_apps_folder", return_value=path
            ) as mock_resolve:
                self.pf.resolve_executable("Chrome", "Google.Chrome")
                self.pf.resolve_executable("CHROME", "GOOGLE.CHROME")
                assert mock_resolve.call_count == 1
        finally:
            os.unlink(path)

    def test_resolve_from_apps_folder_none_returns_none(self):
        with patch.object(
            self.pf, "_resolve_from_apps_folder", return_value=None
        ):
            assert self.pf.resolve_executable("App", "App.Id") is None

    def test_resolved_path_is_abspath(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            relativo = os.path.relpath(path)
            with patch.object(
                self.pf, "_resolve_from_apps_folder", return_value=relativo
            ):
                resultado = self.pf.resolve_executable("App", "App.Id")
                assert resultado == os.path.abspath(path)
        finally:
            os.unlink(path)

    def test_resolved_path_not_a_file_returns_none(self):
        with patch.object(
            self.pf, "_resolve_from_apps_folder", return_value=r"C:\Windows"
        ):
            assert self.pf.resolve_executable("App", "App.Id") is None

    def test_resolve_from_apps_folder_exception_returns_none(self):
        with patch.object(
            self.pf, "_resolve_from_apps_folder", side_effect=OSError("boom")
        ):
            assert self.pf.resolve_executable("App", "App.Id") is None

    def test_clear_cache_removes_executable_entry(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            with patch.object(
                self.pf, "_resolve_from_apps_folder", return_value=path
            ):
                self.pf.resolve_executable("App", "App.Id")
                assert self.pf._executable_cache != {}
                self.pf.clear_cache()
                assert self.pf._executable_cache == {}
        finally:
            os.unlink(path)
