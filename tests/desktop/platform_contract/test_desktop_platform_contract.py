# -*- coding: ascii -*-
"""
Pruebas unitarias del contrato de plataforma de escritorio (unidad 3.8.6.5.7).

Verifica:
* Seleccion del adaptador de escritorio en tiempo de ejecucion segun el SO detectado
  y set_desktop_platform.
* Capacidades declaradas por adaptador con estados y backends normalizados.
* Errores normalizados: PlatformResult, PlatformError, PlatformNotSupportedError y
  PlatformResult.unwrap.
* Adaptador macOS con frontera nativa sintetica: Retina 2x, dos y tres monitores,
  origen negativo, monitor vertical y permisos denegados/concedidos.

Todas las pruebas se ejecutan en Windows sin GUI ni Mac real: el adaptador macOS se
instancia con una frontera nativa sintetica que sustituye a MacNativeBoundary sin
llamar a pyobjc. La verificacion real del adaptador macOS en un Mac queda registrada
como pendiente en mejora/pendientes_macos.txt (regla 3 de la cabecera del roadmap).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.desktop.native_imports import is_windows, is_macos
from src.desktop.platform_contract import (
    ACCESSIBILITY_ACTIONS,
    Capability,
    CapabilityReport,
    CapabilityStatus,
    CaptureResult,
    DesktopPlatformAdapter,
    DisplayInfo,
    InteractionEnvironment,
    LOGICAL_KEYS,
    PermissionKind,
    PlatformError,
    PlatformErrorCode,
    PlatformNotSupportedError,
    PlatformOperationError,
    PlatformResult,
    PointerPosition,
    Rect,
    WindowDpiInfo,
    WindowInfo,
    DESKTOP_PIXELS,
    DESKTOP_POINTS,
    PLATFORM_MACOS,
    PLATFORM_WINDOWS,
    create_desktop_platform,
    get_desktop_platform,
    set_desktop_platform,
)
from src.desktop.platform_macos import (
    MACOS_REAL_VERIFICATION,
    MacNativeBoundary,
    MacOSDesktopAdapter,
    _AV_AUTHORIZED,
    _AV_DENIED,
    cocoa_rect_to_quartz,
)

# ---------------------------------------------------------------------------
# Pantallas sinteticas del adaptador macOS (frontera nativa sustituida)
# ---------------------------------------------------------------------------

PANTALLA_RETINA_PRINCIPAL: Dict[str, Any] = {
    "index": 0,
    "display_id": 1,
    "frame": (0.0, 0.0, 2560.0, 1600.0),
    "visible_frame": (0.0, 44.0, 2560.0, 1556.0),
    "backing_scale": 2.0,
    "name": "Pantalla principal",
    "quartz_bounds": (0.0, 0.0, 2560.0, 1600.0),
    "rotation": 0,
    "is_main": True,
    "is_builtin": True,
    "vendor": "Apple Inc.",
    "model": "Retina",
    "serial": "SN-1",
    "mode_pixel_width": 5120,
    "mode_pixel_height": 3200,
    "refresh_rate": 60.0,
    "size_mm": (345.0, 216.0),
}

PANTALLA_RETINA_SECUNDARIA: Dict[str, Any] = {
    "index": 1,
    "display_id": 2,
    "frame": (2560.0, 0.0, 3840.0, 1600.0),
    "visible_frame": (2560.0, 0.0, 3840.0, 1600.0),
    "backing_scale": 2.0,
    "name": "Pantalla secundaria",
    "quartz_bounds": (2560.0, 0.0, 3840.0, 1600.0),
    "rotation": 0,
    "is_main": False,
    "is_builtin": False,
    "vendor": "LG",
    "model": "Ultra",
    "serial": "SN-2",
    "mode_pixel_width": 7680,
    "mode_pixel_height": 4800,
    "refresh_rate": 60.0,
}

SCREENS_RETINA_2X_DOS = [PANTALLA_RETINA_PRINCIPAL, PANTALLA_RETINA_SECUNDARIA]

SCREENS_TRES_ORIGEN_NEGATIVO = [
    PANTALLA_RETINA_PRINCIPAL,
    {
        "index": 1,
        "display_id": 2,
        "frame": (-1920.0, 0.0, 0.0, 1080.0),
        "visible_frame": (-1920.0, 0.0, 0.0, 1080.0),
        "backing_scale": 1.0,
        "name": "Pantalla izquierda",
        "quartz_bounds": (-1920.0, 0.0, 0.0, 1080.0),
        "rotation": 0,
        "is_main": False,
        "vendor": "Apple Inc.",
        "model": "Retina",
        "serial": "SN-2",
    },
    {
        "index": 2,
        "display_id": 3,
        "frame": (2560.0, 0.0, 2880.0, 3600.0),
        "visible_frame": (2560.0, 0.0, 2880.0, 3600.0),
        "backing_scale": 1.0,
        "name": "Pantalla vertical",
        "quartz_bounds": (2560.0, 0.0, 2880.0, 3600.0),
        "rotation": 0,
        "is_main": False,
        "vendor": "Apple Inc.",
        "model": "Retina",
        "serial": "SN-3",
    },
]

VENTANA_SINTETICA: Dict[str, Any] = {
    "window_id": 1001,
    "pid": 4242,
    "owner_name": "App sintetica",
    "title": "Ventana de prueba",
    "bounds": (100.0, 100.0, 400.0, 300.0),
    "layer": 0,
    "alpha": 1.0,
    "onscreen": True,
    "sharing_state": 1,
    "z_index": 0,
}

VENTANA_PROTEGIDA: Dict[str, Any] = {
    "window_id": 1002,
    "pid": 4242,
    "owner_name": "WindowServer",
    "title": "",
    "bounds": (100.0, 100.0, 400.0, 300.0),
    "layer": 0,
    "alpha": 1.0,
    "onscreen": True,
    "sharing_state": 0,
    "z_index": 0,
}


class SyntheticMacBoundary(MacNativeBoundary):
    """Frontera nativa macOS sintetica para tests de contrato en Windows.

    Sustituye a MacNativeBoundary sin importar pyobjc ni tocar un Mac real.
    """

    def __init__(
        self,
        screens: Optional[List[Dict[str, Any]]] = None,
        windows: Optional[List[Dict[str, Any]]] = None,
        ax_trusted: Optional[bool] = None,
        screen_capture_granted: Optional[bool] = None,
        microphone_authorization: Optional[int] = None,
        session_locked: Optional[bool] = None,
        frontmost_pid: Optional[int] = None,
        deps_errors: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__()
        self._screens = list(screens or [])
        self._windows = list(windows or [])
        self._ax_trusted = ax_trusted
        self._screen_capture_granted = screen_capture_granted
        self._microphone_authorization = microphone_authorization
        self._session_locked = session_locked
        self._frontmost_pid = frontmost_pid
        self._deps_errors = dict(deps_errors or {})

    def dependencies(self) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {}
        for name in ("AppKit", "Quartz", "ApplicationServices", "AVFoundation", "mss"):
            result[name] = self._deps_errors.get(name)
        return result

    def screens(self) -> List[Dict[str, Any]]:
        return list(self._screens)

    def window_list(
        self, mode: str = "on_screen", window_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if window_id is not None:
            return [
                w
                for w in self._windows
                if int(w.get("window_id", 0)) == int(window_id)
            ]
        return list(self._windows)

    def ax_is_trusted(self) -> bool:
        if self._ax_trusted is None:
            raise RuntimeError(
                "AXIsProcessTrusted no consultable en la frontera sintetica"
            )
        return bool(self._ax_trusted)

    def screen_capture_access(self) -> Optional[bool]:
        return self._screen_capture_granted

    def microphone_authorization(self) -> Optional[int]:
        return self._microphone_authorization

    def session_info(self) -> Optional[Dict[str, Any]]:
        if self._session_locked is None:
            return None
        return {"on_console": True, "screen_locked": bool(self._session_locked)}

    def frontmost_application(self) -> Optional[Dict[str, Any]]:
        if self._frontmost_pid is None:
            return None
        return {
            "pid": int(self._frontmost_pid),
            "bundle_id": "app.sintetica",
            "name": "App sintetica",
        }

    def running_application(self, pid: int) -> Optional[Dict[str, Any]]:
        for w in self._windows:
            if int(w.get("pid", 0)) == int(pid):
                return {
                    "pid": int(pid),
                    "bundle_id": "app.sintetica",
                    "name": "App sintetica",
                    "executable_name": "App sintetica",
                    "active": True,
                    "hidden": False,
                    "activation_policy": 0,
                    "terminated": False,
                }
        return None

    def process_euid(self, pid: int) -> Optional[int]:
        return 501

    def own_euid(self) -> int:
        return 501

    def ax_application_windows(self, pid: int) -> List[Dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# Seleccion del adaptador
# ---------------------------------------------------------------------------


class TestSeleccionAdaptador:
    """Seleccion del adaptador de escritorio por SO detectado."""

    def test_get_desktop_platform_devuelve_adaptador_del_so_actual(self) -> None:
        adapter = get_desktop_platform()
        assert isinstance(adapter, DesktopPlatformAdapter)
        if is_windows():
            assert adapter.platform_name == PLATFORM_WINDOWS
            assert adapter.desktop_space == DESKTOP_PIXELS
        elif is_macos():
            assert adapter.platform_name == PLATFORM_MACOS
            assert adapter.desktop_space == DESKTOP_POINTS
        else:
            assert adapter.platform_name == "otro"

    def test_get_desktop_platform_es_singleton(self) -> None:
        primero = get_desktop_platform()
        segundo = get_desktop_platform()
        assert primero is segundo

    def test_create_desktop_platform_windows_y_macos(self) -> None:
        win = create_desktop_platform("win32")
        assert win.platform_name == PLATFORM_WINDOWS
        assert win.desktop_space == DESKTOP_PIXELS

        mac = create_desktop_platform("darwin")
        assert mac.platform_name == PLATFORM_MACOS
        assert mac.desktop_space == DESKTOP_POINTS

    def test_create_desktop_platform_so_no_soportado_raise_explicito(self) -> None:
        with pytest.raises(PlatformNotSupportedError):
            create_desktop_platform("linux")

    def test_set_desktop_platform_sobrescribe_y_limpia_singleton(self) -> None:
        referencia = create_desktop_platform("win32")
        set_desktop_platform(referencia)
        assert get_desktop_platform() is referencia
        set_desktop_platform(None)
        despues = get_desktop_platform()
        assert isinstance(despues, DesktopPlatformAdapter)
        assert despues is not referencia


# ---------------------------------------------------------------------------
# Capacidades del contrato
# ---------------------------------------------------------------------------


class TestCapacidadesContrato:
    """Cada capacidad declarada por separado con estado y backend normalizados."""

    def test_todas_las_capacidades_estan_declaradas(self) -> None:
        adapter = get_desktop_platform()
        reportes = adapter.capabilities()
        assert set(reportes.keys()) == set(Capability)

    def test_cada_reporte_tiene_estado_y_backend_validos(self) -> None:
        adapter = get_desktop_platform()
        esperados = (
            CapabilityStatus.DISPONIBLE,
            CapabilityStatus.SIN_PERMISO,
            CapabilityStatus.NO_SOPORTADO,
            CapabilityStatus.NO_VERIFICADO,
        )
        for cap, reporte in adapter.capabilities().items():
            assert isinstance(reporte, CapabilityReport)
            assert reporte.capability == cap
            assert reporte.status in esperados
            assert isinstance(reporte.backend, str)

    def test_capacidad_por_nombre(self) -> None:
        adapter = get_desktop_platform()
        estado = adapter.capability_status(Capability.DISPLAY_ENUM)
        assert estado in (
            CapabilityStatus.DISPONIBLE,
            CapabilityStatus.SIN_PERMISO,
            CapabilityStatus.NO_SOPORTADO,
            CapabilityStatus.NO_VERIFICADO,
        )

    def test_capacidades_nucleo_disponibles_en_windows(self) -> None:
        if not is_windows():
            pytest.skip("Capacidades nativas de Windows")
        adapter = get_desktop_platform()
        res = adapter.enumerate_displays()
        if not res.ok:
            pytest.skip("Enumeracion de monitores no disponible en este Windows")
        reportes = adapter.capabilities()
        for cap in (
            Capability.DISPLAY_ENUM,
            Capability.WINDOW_VERIFY,
            Capability.WINDOW_CONTROL,
        ):
            assert reportes[cap].status == CapabilityStatus.DISPONIBLE
            assert reportes[cap].backend == "win32"
        for cap in (
            Capability.DISCOVER,
            Capability.RESOLVE,
            Capability.PREFLIGHT,
            Capability.LAUNCH,
        ):
            # Gestionadas por el adaptador de lanzamiento, no por el de escritorio.
            assert reportes[cap].status == CapabilityStatus.NO_SOPORTADO


# ---------------------------------------------------------------------------
# Errores normalizados
# ---------------------------------------------------------------------------


class TestErroresNormalizados:
    """PlatformResult, PlatformError, PlatformNotSupportedError y unwrap."""

    def test_platform_result_success_y_failure(self) -> None:
        ok = PlatformResult.success(42, clave="valor")
        assert ok.ok is True
        assert ok.unwrap() == 42
        assert ok.to_dict()["ok"] is True
        assert ok.to_dict()["value"] == 42
        assert ok.to_dict()["details"]["clave"] == "valor"

        mal = PlatformResult.failure(
            PlatformErrorCode.NOT_FOUND,
            "no existe",
            operation="buscar",
            platform="windows",
        )
        assert mal.ok is False
        assert mal.value is None
        assert mal.error is not None
        assert mal.error.code == PlatformErrorCode.NOT_FOUND
        assert mal.error.message == "no existe"
        assert mal.error.operation == "buscar"
        assert mal.error.platform == "windows"
        with pytest.raises(PlatformOperationError):
            mal.unwrap()
        d = mal.to_dict()
        assert d["ok"] is False
        assert d["value"] is None
        assert d["error"]["code"] == "not_found"
        assert d["error"]["message"] == "no existe"

    def test_platform_error_str_y_to_dict(self) -> None:
        err = PlatformError(
            PlatformErrorCode.PERMISSION_DENIED,
            "sin permiso",
            operation="capturar",
            platform="macos",
            instructions="concede acceso",
        )
        s = str(err)
        assert "capturar" in s
        assert "permission_denied" in s
        assert "sin permiso" in s
        d = err.to_dict()
        assert d["code"] == "permission_denied"
        assert d["message"] == "sin permiso"
        assert d["operation"] == "capturar"
        assert d["platform"] == "macos"
        assert d["instructions"] == "concede acceso"

    def test_codigos_de_error_son_estables(self) -> None:
        for code in PlatformErrorCode:
            assert isinstance(code.value, str)
            assert code.value != ""

    def test_platform_not_supported_error_mensaje(self) -> None:
        with pytest.raises(PlatformNotSupportedError) as excinfo:
            create_desktop_platform("solaris")
        mensaje = str(excinfo.value)
        assert "No hay adaptador de escritorio" in mensaje
        assert "Windows" in mensaje and "macOS" in mensaje

    def test_result_from_error(self) -> None:
        err = PlatformError(PlatformErrorCode.TIMEOUT, "se volvio el tiempo")
        res = PlatformResult.from_error(err)
        assert res.ok is False
        assert res.error is not None
        assert res.error.code == PlatformErrorCode.TIMEOUT
        with pytest.raises(PlatformOperationError):
            res.unwrap()


# ---------------------------------------------------------------------------
# Modelos de datos del contrato
# ---------------------------------------------------------------------------


class TestModelosContrato:
    def test_pointer_position(self) -> None:
        pos = PointerPosition(
            x=100.0, y=200.0, coordinate_space=DESKTOP_PIXELS, display_id="d1"
        )
        d = pos.to_dict()
        assert d["x"] == 100.0
        assert d["y"] == 200.0
        assert d["coordinate_space"] == DESKTOP_PIXELS
        assert d["display_id"] == "d1"

    def test_capture_result_to_dict(self) -> None:
        cap = CaptureResult(
            region=Rect(0, 0, 100, 100),
            pixel_width=100,
            pixel_height=100,
            backend="mss",
        )
        d = cap.to_dict()
        assert d["pixel_width"] == 100
        assert d["pixel_height"] == 100
        assert d["backend"] == "mss"
        assert d["has_image"] is False
        assert d["region"]["width"] == 100

    def test_window_info_to_dict(self) -> None:
        win = WindowInfo(
            window_id=7,
            pid=123,
            title="prueba",
            bounds=Rect(0, 0, 100, 100),
            coordinate_space=DESKTOP_PIXELS,
        )
        d = win.to_dict()
        assert d["window_id"] == 7
        assert d["pid"] == 123
        assert d["title"] == "prueba"
        assert d["coordinate_space"] == DESKTOP_PIXELS
        assert d["bounds"]["width"] == 100

    def test_window_dpi_info(self) -> None:
        dpi = WindowDpiInfo(window_id=7, dpi=144, scale_factor=1.5)
        d = dpi.to_dict()
        assert d["window_id"] == 7
        assert d["dpi"] == 144
        assert d["scale_factor"] == 1.5

    def test_interaction_environment_bloqueos(self) -> None:
        env = InteractionEnvironment(
            session_locked=True, target_minimized=True, permissions_missing=["accessibility"]
        )
        assert env.allowed is False
        razones = env.blocking_reasons()
        assert "session_locked" in razones
        assert "target_minimized" in razones
        assert "permission_missing:accessibility" in razones
        env_limpio = InteractionEnvironment()
        assert env_limpio.allowed is True
        assert env_limpio.blocking_reasons() == []

    def test_logical_keys_y_acciones_accesibilidad(self) -> None:
        assert "primary_modifier" in LOGICAL_KEYS
        assert "ctrl" in LOGICAL_KEYS
        assert "invoke" in ACCESSIBILITY_ACTIONS
        assert "toggle" in ACCESSIBILITY_ACTIONS


# ---------------------------------------------------------------------------
# Geometria: rectangulos con coordenadas negativas (espacios de escritorio)
# ---------------------------------------------------------------------------


class TestRectEspaciosEscritorio:
    def test_rect_con_origen_negativo(self) -> None:
        rect = Rect(-1920.0, 0.0, 0.0, 1080.0)
        assert rect.is_valid()
        assert rect.width == 1920.0
        assert rect.height == 1080.0
        assert rect.contains_point(-1000.0, 500.0)
        assert not rect.contains_point(100.0, 100.0)

    def test_rect_sin_solapamiento_y_iou(self) -> None:
        a = Rect(-1920.0, 0.0, 0.0, 1080.0)
        b = Rect(0.0, 0.0, 2560.0, 1600.0)
        assert a.intersection(b) is None
        assert a.iou(b) == 0.0

    def test_rect_from_any(self) -> None:
        assert Rect.from_any((0, 0, 100, 100)) == Rect(0.0, 0.0, 100.0, 100.0)
        assert Rect.from_any(
            {"left": 1, "top": 2, "width": 3, "height": 4}
        ) == Rect(1.0, 2.0, 4.0, 6.0)
        assert Rect.from_any(None) is None

    def test_cocoa_a_quartz_invierte_eje_y(self) -> None:
        rect = cocoa_rect_to_quartz((0.0, 1000.0, 200.0, 100.0), 1600.0)
        assert rect == Rect(0.0, 500.0, 200.0, 600.0)


# ---------------------------------------------------------------------------
# Adaptador macOS con frontera nativa sintetica (regla 3: sin Mac real)
# ---------------------------------------------------------------------------


class TestAdaptadorMacOSConFronteraSintetica:
    """MacOSDesktopAdapter con frontera sintetica, ejecutado en Windows."""

    def test_mac_adapter_declarado_para_macos(self) -> None:
        adapter = MacOSDesktopAdapter()
        assert adapter.platform_name == PLATFORM_MACOS
        assert adapter.desktop_space == DESKTOP_POINTS

    def test_macos_esta_implementado_a_ciegos_sin_verificar_en_mac(self) -> None:
        assert MACOS_REAL_VERIFICATION is False

    def test_macos_capacidades_tienen_nota_sin_verificar(self) -> None:
        adapter = MacOSDesktopAdapter()
        nota = "(macOS: implementado sin verificar en equipo real)"
        reportes = adapter.capabilities()
        for reporte in reportes.values():
            assert reporte.detail == "" or nota in reporte.detail

    def test_retina_2x_dos_monitores(self) -> None:
        limite = SyntheticMacBoundary(screens=SCREENS_RETINA_2X_DOS)
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.enumerate_displays()
        assert res.ok is True
        assert res.error is None
        pantallas = res.value
        assert len(pantallas) == 2
        principal = pantallas[0]
        assert principal.is_primary is True
        assert principal.coordinate_space == DESKTOP_POINTS
        assert principal.scale_factor == 2.0
        assert principal.dpi == 144
        assert principal.bounds == Rect(0.0, 0.0, 2560.0, 1600.0)
        # visible_frame es Cocoa (origen abajo-izquierda); cocoa_rect_to_quartz
        # lo convierte a Quartz (arriba-izquierda): top = 1600 - (44 + 1556) = 0.
        assert principal.work_area == Rect(0.0, 0.0, 2560.0, 1556.0)
        assert principal.pixel_width == 5120
        assert principal.pixel_height == 3200
        assert principal.orientation == "landscape"
        assert principal.native_handle == 1
        assert "stable_key" in principal.extra
        secundaria = pantallas[1]
        assert secundaria.is_primary is False
        assert secundaria.bounds.left == 2560.0  # a la derecha del principal
        assert secundaria.scale_factor == 2.0
        assert secundaria.pixel_width == 7680

    def test_tres_monitores_origen_negativo_y_vertical(self) -> None:
        limite = SyntheticMacBoundary(screens=SCREENS_TRES_ORIGEN_NEGATIVO)
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.enumerate_displays()
        assert res.ok is True
        pantallas = res.value
        assert len(pantallas) == 3
        ids = [p.display_id for p in pantallas]
        assert "1" in ids and "2" in ids and "3" in ids
        izquierda = next(p for p in pantallas if p.display_id == "2")
        assert izquierda.bounds.left == -1920.0  # origen negativo valido
        assert izquierda.coordinate_space == DESKTOP_POINTS
        vertical = next(p for p in pantallas if p.display_id == "3")
        assert vertical.bounds.height > vertical.bounds.width
        assert vertical.orientation == "portrait"
        assert vertical.pixel_width == 2880
        assert vertical.pixel_height == 3600
        principales = [p for p in pantallas if p.is_primary]
        assert len(principales) == 1
        assert all(p.scale_factor >= 1.0 for p in pantallas)

    def test_permisos_denegados_mac(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            ax_trusted=False,
            screen_capture_granted=False,
            microphone_authorization=_AV_DENIED,
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        caps = adapter.capabilities()
        assert caps[Capability.WINDOW_CONTROL].status == CapabilityStatus.SIN_PERMISO
        assert caps[Capability.INPUT_CONTROL].status == CapabilityStatus.SIN_PERMISO
        assert caps[Capability.ACCESSIBILITY_TREE].status == CapabilityStatus.SIN_PERMISO
        assert caps[Capability.SCREEN_CAPTURE].status == CapabilityStatus.SIN_PERMISO
        assert caps[Capability.DISPLAY_ENUM].status == CapabilityStatus.DISPONIBLE
        # La frontera sintetica declara todas las dependencias disponibles.
        assert caps[Capability.PROCESS_VERIFY].status == CapabilityStatus.DISPONIBLE
        perms = adapter.check_permissions()
        por_tipo = {p.kind: p for p in perms}
        assert por_tipo[PermissionKind.ACCESSIBILITY].status == CapabilityStatus.SIN_PERMISO
        assert por_tipo[PermissionKind.SCREEN_RECORDING].status == CapabilityStatus.SIN_PERMISO
        assert por_tipo[PermissionKind.MICROPHONE].status == CapabilityStatus.SIN_PERMISO

    def test_permisos_concedidos_mac(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            ax_trusted=True,
            screen_capture_granted=True,
            microphone_authorization=_AV_AUTHORIZED,
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        caps = adapter.capabilities()
        assert caps[Capability.WINDOW_CONTROL].status == CapabilityStatus.DISPONIBLE
        assert caps[Capability.INPUT_CONTROL].status == CapabilityStatus.DISPONIBLE
        assert caps[Capability.ACCESSIBILITY_TREE].status == CapabilityStatus.DISPONIBLE
        assert caps[Capability.SCREEN_CAPTURE].status == CapabilityStatus.DISPONIBLE
        assert caps[Capability.DISPLAY_ENUM].status == CapabilityStatus.DISPONIBLE
        assert caps[Capability.PROCESS_VERIFY].status == CapabilityStatus.DISPONIBLE
        perms = adapter.check_permissions()
        por_tipo = {p.kind: p for p in perms}
        assert por_tipo[PermissionKind.ACCESSIBILITY].status == CapabilityStatus.DISPONIBLE
        assert por_tipo[PermissionKind.SCREEN_RECORDING].status == CapabilityStatus.DISPONIBLE
        assert por_tipo[PermissionKind.MICROPHONE].status == CapabilityStatus.DISPONIBLE

    def test_dependencia_nativa_falta_mac(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            deps_errors={"AppKit": "No module named 'AppKit'"},
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        caps = adapter.capabilities()
        assert caps[Capability.DISPLAY_ENUM].status == CapabilityStatus.NO_SOPORTADO
        assert caps[Capability.WINDOW_VERIFY].status == CapabilityStatus.NO_SOPORTADO
        assert caps[Capability.PROCESS_VERIFY].status == CapabilityStatus.NO_VERIFICADO

    def test_list_windows_sintetico(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            windows=[VENTANA_SINTETICA],
            frontmost_pid=4242,
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.list_windows()
        assert res.ok is True
        ventanas = res.value
        assert len(ventanas) == 1
        v = ventanas[0]
        assert v.window_id == 1001
        assert v.pid == 4242
        assert v.title == "Ventana de prueba"
        assert v.bounds == Rect(100.0, 100.0, 500.0, 400.0)
        assert v.coordinate_space == DESKTOP_POINTS
        assert v.scale_factor == 2.0
        assert v.is_visible is True
        assert v.is_minimized is False
        assert v.is_foreground is True  # el pid coincide con el frontmost

    def test_get_window_desconocida_devuelve_window_gone(self) -> None:
        limite = SyntheticMacBoundary(screens=SCREENS_RETINA_2X_DOS)
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.get_window(99999)
        assert res.ok is False
        assert res.error is not None
        assert res.error.code == PlatformErrorCode.WINDOW_GONE

    def test_check_interaction_environment_sin_bloqueos(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            windows=[VENTANA_SINTETICA],
            frontmost_pid=4242,
            ax_trusted=True,
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.check_interaction_environment(1001)
        assert res.ok is True
        env = res.value
        assert env.allowed is True
        assert env.blocking_reasons() == []

    def test_check_interaction_environment_sesion_bloqueada(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            windows=[VENTANA_SINTETICA],
            session_locked=True,
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.check_interaction_environment(1001)
        assert res.ok is True
        env = res.value
        assert env.session_locked is True
        assert env.allowed is False
        assert "session_locked" in env.blocking_reasons()

    def test_check_interaction_environment_contenido_protegido(self) -> None:
        limite = SyntheticMacBoundary(
            screens=SCREENS_RETINA_2X_DOS,
            windows=[VENTANA_PROTEGIDA],
            ax_trusted=True,
        )
        adapter = MacOSDesktopAdapter(boundary=limite)
        res = adapter.check_interaction_environment(1002)
        assert res.ok is True
        env = res.value
        assert env.protected_content is True
        assert env.allowed is False


# ---------------------------------------------------------------------------
# Enumeracion de monitores reales en Windows (datos del equipo, sin GUI)
# ---------------------------------------------------------------------------


class TestEnumeracionMonitoresWindowsReal:
    def test_enumerate_displays_devuelve_geometria_real(self) -> None:
        if not is_windows():
            pytest.skip("Solo Windows")
        adapter = get_desktop_platform()
        res = adapter.enumerate_displays()
        assert res.ok is True
        pantallas = res.value
        assert len(pantallas) >= 1
        principales = [p for p in pantallas if p.is_primary]
        assert len(principales) == 1
        for p in pantallas:
            assert isinstance(p, DisplayInfo)
            assert p.display_id != ""
            assert p.name != ""
            assert p.coordinate_space == DESKTOP_PIXELS
            assert p.bounds.is_valid()
            assert p.work_area.is_valid()
            assert p.pixel_width > 0
            assert p.pixel_height > 0
            assert p.scale_factor > 0.0

    def test_enumerate_displays_todos_campos_requeridos_38661(self) -> None:
        """3.8.6.6.1: todos los campos obligatorios de DisplayInfo en enumeracion real."""
        if not is_windows():
            pytest.skip("Solo Windows")
        adapter = get_desktop_platform()
        res = adapter.enumerate_displays()
        assert res.ok is True
        pantallas = res.value
        assert len(pantallas) >= 1
        for p in pantallas:
            # Identificador estable
            assert p.display_id != ""
            assert p.native_handle is not None
            assert p.extra.get("device_name") not in (None, "")
            # Rectangulo absoluto con origen posiblemente negativo
            assert p.bounds.is_valid()
            assert isinstance(p.bounds.left, (int, float))
            assert isinstance(p.bounds.top, (int, float))
            # Area de trabajo
            assert p.work_area.is_valid()
            # Resolucion fisica
            assert p.pixel_width > 0
            assert p.pixel_height > 0
            # Escala/DPI efectivo
            assert p.scale_factor > 0.0
            assert p.dpi > 0
            # Orientacion y rotacion
            assert p.rotation in (0, 90, 180, 270)
            assert p.orientation in ("landscape", "portrait")
            # Frecuencia (puede ser None si no se pudo leer, pero si hay valor debe ser positivo)
            if p.refresh_rate is not None:
                assert p.refresh_rate > 0.0
            # Principal: exactamente uno
        principales = [p for p in pantallas if p.is_primary]
        assert len(principales) == 1

    def test_enumerate_displays_renumeracion_fresca_38661(self) -> None:
        """3.8.6.6.1: reenumerar ante cambios; nunca reutilizar dimensiones historicas."""
        if not is_windows():
            pytest.skip("Solo Windows")
        adapter = get_desktop_platform()
        res1 = adapter.enumerate_displays()
        assert res1.ok is True
        res2 = adapter.enumerate_displays()
        assert res2.ok is True
        pantallas1 = res1.value
        pantallas2 = res2.value
        assert len(pantallas1) == len(pantallas2)
        # Mismos identificadores estables, mismos datos (sin cambios de hardware entre llamadas)
        ids1 = sorted(p.display_id for p in pantallas1)
        ids2 = sorted(p.display_id for p in pantallas2)
        assert ids1 == ids2
        for p1, p2 in zip(sorted(pantallas1, key=lambda x: x.display_id),
                          sorted(pantallas2, key=lambda x: x.display_id)):
            assert p1.display_id == p2.display_id
            assert p1.bounds == p2.bounds
            assert p1.work_area == p2.work_area
            assert p1.pixel_width == p2.pixel_width
            assert p1.pixel_height == p2.pixel_height
            assert p1.scale_factor == p2.scale_factor
            assert p1.dpi == p2.dpi
            assert p1.is_primary == p2.is_primary
