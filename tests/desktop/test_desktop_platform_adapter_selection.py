"""Pruebas unitarias de la unidad 3.8.6.5.3: seleccion de adaptador de escritorio.

Verifica:
* Seleccion del adaptador en tiempo de ejecucion por SO detectado.
* Error explicito (PlatformNotSupportedError) cuando no hay adaptador para el SO.
* Imports nativos perezosos (no fallan al importar el paquete en el SO "otro").
* Todo el paquete src.desktop importa sin error en el SO actual.
* Marcadores de plataforma presentes en docs/requirements/requirements.txt.

Es una prueba determinista del contrato de plataforma; no abre ventanas, no usa GUI
ni requiere dispositivos reales. La prueba de contrato completa (incluido el adaptador
macOS con frontera nativa sintetica) corresponde a la unidad 3.8.6.5.7.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.desktop.native_imports import (
    NativeDependencyUnavailable,
    LazyModule,
    LazyWinDLL,
    current_platform_name,
    is_macos,
    is_windows,
)
from src.desktop.platform_contract import (
    Capability,
    DesktopPlatformAdapter,
    PlatformNotSupportedError,
    create_desktop_platform,
    get_desktop_platform,
)

REQUIREMENTS_PATH = Path(__file__).resolve().parents[2] / "docs" / "requirements" / "requirements.txt"


class TestAdapterSelectionByOS:
    """Seleccion del adaptador segun el SO detectado."""

    def test_get_desktop_platform_returns_adapter_for_current_os(self) -> None:
        adapter = get_desktop_platform()
        assert isinstance(adapter, DesktopPlatformAdapter)
        expected_platform = "windows" if is_windows() else ("macos" if is_macos() else "otro")
        assert adapter.platform_name == expected_platform
        expected_space = "DESKTOP_PIXELS" if is_windows() else ("DESKTOP_POINTS" if is_macos() else "DESKTOP_PIXELS")
        assert adapter.desktop_space == expected_space

    def test_get_desktop_platform_is_singleton(self) -> None:
        first = get_desktop_platform()
        second = get_desktop_platform()
        assert first is second

    def test_create_desktop_platform_windows_and_macos(self) -> None:
        win = create_desktop_platform("win32")
        assert win.platform_name == "windows"
        assert win.desktop_space == "DESKTOP_PIXELS"

        mac = create_desktop_platform("darwin")
        assert mac.platform_name == "macos"
        assert mac.desktop_space == "DESKTOP_POINTS"

    def test_create_desktop_platform_unsupported_raises_explicit_error(self) -> None:
        with pytest.raises(PlatformNotSupportedError) as excinfo:
            create_desktop_platform("linux")
        mensaje = str(excinfo.value)
        assert "No hay adaptador de escritorio" in mensaje
        assert "Windows" in mensaje and "macOS" in mensaje

    def test_create_desktop_platform_none_uses_current_os(self) -> None:
        adapter = create_desktop_platform(None)
        singleton = get_desktop_platform()
        # create_desktop_platform devuelve una nueva instancia (no el singleton);
        # compara plataforma y espacio, no identidad.
        assert adapter.platform_name == singleton.platform_name
        assert adapter.desktop_space == singleton.desktop_space


class TestLazyNativeImports:
    """Imports nativos perezosos: el paquete importa sin error en ambos SO."""

    def test_desktop_package_imports(self) -> None:
        import src.desktop  # noqa: F401
        import src.desktop.platform_contract  # noqa: F401
        import src.desktop.native_imports  # noqa: F401
        import src.desktop.platform_windows  # noqa: F401
        import src.desktop.platform_macos  # noqa: F401 (imports nativas perezosas)

    def test_lazy_module_carga_sin_fallar_modulo_comun(self) -> None:
        modulo = LazyModule("os")
        assert modulo is not None
        assert hasattr(modulo, "path")

    def test_lazy_modulo_solo_platform_falla_con_error_claro_en_so_incorrecto(self) -> None:
        modulo_win = LazyModule("pygetwindow", required_platform="win32")
        if is_windows():
            # En Windows se carga sin error.
            _ = modulo_win.is_available()
        else:
            with pytest.raises(NativeDependencyUnavailable):
                modulo_win.is_available()

    def test_lazy_windll_solo_windows(self) -> None:
        dll = LazyWinDLL("user32")
        if is_windows():
            assert dll.is_available()
        else:
            with pytest.raises(NativeDependencyUnavailable):
                dll.is_available()

    def test_current_platform_name_valido(self) -> None:
        nombre = current_platform_name()
        assert nombre in ("windows", "macos", "otro")


class TestCapabilitiesDeclared:
    """Cada capacidad declarada por separado (regla 2 de la cabecera del roadmap)."""

    def test_todas_las_capacidades_estan_declaradas(self) -> None:
        adapter = get_desktop_platform()
        reportes = adapter.capabilities()
        esperadas = {
            Capability.DISCOVER,
            Capability.RESOLVE,
            Capability.PREFLIGHT,
            Capability.LAUNCH,
            Capability.PROCESS_VERIFY,
            Capability.WINDOW_VERIFY,
            Capability.WINDOW_CONTROL,
            Capability.DISPLAY_ENUM,
            Capability.SCREEN_CAPTURE,
            Capability.INPUT_CONTROL,
            Capability.ACCESSIBILITY_TREE,
            Capability.AUDIO_INPUT,
        }
        assert set(reportes.keys()) == esperadas

    def test_cada_reporte_tiene_estado_y_backend(self) -> None:
        adapter = get_desktop_platform()
        for cap, reporte in adapter.capabilities().items():
            assert reporte.status.value in ("DISPONIBLE", "SIN_PERMISO", "NO_SOPORTADO", "NO_VERIFICADO")
            assert isinstance(reporte.backend, str)


class TestPlatformMarkersInRequirements:
    """Marcadores de plataforma en requirements.txt."""

    def test_requirements_tiene_marcadores_win32_y_darwin(self) -> None:
        contenido = REQUIREMENTS_PATH.read_text(encoding="utf-8")
        assert "sys_platform == \"win32\"" in contenido
        assert "sys_platform == \"darwin\"" in contenido

    def test_requirements_marcador_afecta_a_paquetes(self) -> None:
        lineas = REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        marcadores_win = [l for l in lineas if 'sys_platform == "win32"' in l]
        marcadores_mac = [l for l in lineas if 'sys_platform == "darwin"' in l]
        assert len(marcadores_win) >= 1
        assert len(marcadores_mac) >= 1
        # Ejemplos esperados (no se debilitan por cambio de versiones)
        assert any("pywin32" in l for l in marcadores_win)
        assert any("pyobjc-core" in l for l in marcadores_mac)
