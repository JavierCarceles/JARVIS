"""
Tests de la comprobacion de entorno de interaccion antes de capturar o
enviar entradas - unidad 3.8.6.4.6.

Pruebas para src/hands/detection/calibration_quality_gate.py:
check_interaction_environment(adapter, window_id) devuelve un motivo concreto
por cada proteccion (sesion bloqueada, escritorio seguro, elevacion/UAC,
contenido protegido, ventana protegida, overlays, ventana minimizada u
oculta, permiso faltante) y nunca intenta eludirla. Los checks desconocidos
deniegan en modo estricto. Adaptador ausente o fallido deniega.
Ventana inexistente devuelve window_gone.

Tests unitarios (sin SO ni GUI): adaptador de escritorio inyectado que
devuelve InteractionEnvironment sintetico. No se abren ventanas ni se
envian entradas.

Test de integracion real GUI (Windows, JARVIS_TEST_GUI_REAL=1): reusa la
unica ventana de Notepad compartida por sesion en el monitor secundario
derecho (TestGuiBase); el adaptador Windows real devuelve allowed=True con
el entorno concreto; un HWND inexistente devuelve window_gone.
"""

from __future__ import annotations

import unittest

from src.desktop.platform_contract import (
    DesktopPlatformAdapter,
    InteractionEnvironment,
    PlatformErrorCode,
    PlatformResult,
)
from src.hands.detection.calibration_quality_gate import (
    InteractionCheck,
    check_interaction_environment,
)

# Reusa la infraestructura de ventana compartida (una Notepad por sesion de
# pytest, monitor secundario derecho, lock de exclusion, cierre por atexit).
from tests.eyes.detection.test_visual_ui_detector_fusion import TestGuiBase  # noqa: E402


def _entorno(**sobre):
    env = InteractionEnvironment()
    for nombre, valor in (sobre or {}).items():
        setattr(env, nombre, valor)
    return env


class _FakeDesktopAdapter(DesktopPlatformAdapter):
    """Adaptador inyectado que devuelve un InteractionEnvironment fijado."""

    def __init__(self, env: InteractionEnvironment) -> None:
        super().__init__()
        self.platform_name = "fake"
        self.env = env
        self.calls = []

    def check_interaction_environment(self, window_id: int) -> PlatformResult:
        self.calls.append(int(window_id))
        return PlatformResult.success(self.env)


class TestInteractionCheckUnitario(unittest.TestCase):
    """Logica pura de check_interaction_environment con adaptador inyectado."""

    def test_entorno_despejado_esta_permitido(self):
        adapter = _FakeDesktopAdapter(_entorno())
        check = check_interaction_environment(adapter, 1234)
        self.assertTrue(check.allowed)
        self.assertEqual(check.reasons, [])
        self.assertIsNotNone(check.environment)
        self.assertTrue(check.environment["allowed"])

    def test_sesion_bloqueada_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(session_locked=True))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("session_locked", check.reasons)

    def test_escritorio_seguro_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(secure_desktop=True))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("secure_desktop", check.reasons)

    def test_objetivo_elevado_sin_jarvis_deniega(self):
        adapter = _FakeDesktopAdapter(_entorno(target_elevated=True, jarvis_elevated=False))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("target_elevated", check.reasons)

    def test_objetivo_elevado_con_jarvis_elevado_permitido(self):
        adapter = _FakeDesktopAdapter(_entorno(target_elevated=True, jarvis_elevated=True))
        check = check_interaction_environment(adapter, 1234)
        self.assertTrue(check.allowed)
        self.assertEqual(check.reasons, [])

    def test_contenido_protegido_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(protected_content=True))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("protected_content", check.reasons)

    def test_ventana_protegida_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(protected_window=True))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("protected_window", check.reasons)

    def test_overlay_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(overlay_windows=[999]))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("overlay_present", check.reasons)

    def test_ventana_minimizada_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(target_minimized=True))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("target_minimized", check.reasons)

    def test_ventana_oculta_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(target_visible=False))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("target_hidden", check.reasons)

    def test_permiso_faltante_devuelve_motivo_concreto(self):
        adapter = _FakeDesktopAdapter(_entorno(permissions_missing=["accessibility"]))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("permission_missing:accessibility", check.reasons)

    def test_check_desconocido_estricto_deniega(self):
        adapter = _FakeDesktopAdapter(_entorno(unknown_checks=["input_desktop"]))
        check = check_interaction_environment(adapter, 1234, strict_unknown=True)
        self.assertFalse(check.allowed)
        self.assertIn("check_unknown:input_desktop", check.reasons)

    def test_check_desconocido_no_estricto_permitido(self):
        adapter = _FakeDesktopAdapter(_entorno(unknown_checks=["input_desktop"]))
        check = check_interaction_environment(adapter, 1234, strict_unknown=False)
        self.assertTrue(check.allowed)
        self.assertEqual(check.reasons, [])

    def test_varias_protecciones_devuelven_todas_las_razones(self):
        adapter = _FakeDesktopAdapter(_entorno(
            session_locked=True, secure_desktop=True, protected_content=True,
            overlay_windows=[1, 2], target_minimized=True,
        ))
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        for motivo in ("session_locked", "secure_desktop", "protected_content",
                       "overlay_present", "target_minimized"):
            self.assertIn(motivo, check.reasons)

    def test_entorno_serializable(self):
        adapter = _FakeDesktopAdapter(_entorno(target_elevated=True, jarvis_elevated=False))
        check = check_interaction_environment(adapter, 1234)
        d = check.to_dict()
        self.assertEqual(d["allowed"], False)
        self.assertIsInstance(d["reasons"], list)
        self.assertIsInstance(d["environment"], dict)
        self.assertEqual(d["environment"]["target_elevated"], True)
        self.assertEqual(d["environment"]["jarvis_elevated"], False)

    def test_adapter_ausente_usa_adaptador_real_y_deniega_ventana_inexistente(self):
        check = check_interaction_environment(None, 0xBADF00D)
        self.assertFalse(check.allowed)
        self.assertEqual(check.reasons, ["window_gone"])

    def test_adapter_que_levanta_excepcion_deniega(self):
        class _Rompe(DesktopPlatformAdapter):
            def check_interaction_environment(self, window_id):
                raise RuntimeError("fallo nativo")
        adapter = _Rompe()
        adapter.platform_name = "rompe"
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertIn("environment_check_failed", check.reasons)

    def test_adapter_devuelve_fallo_deniega_con_codigo(self):
        class _Falla(DesktopPlatformAdapter):
            def check_interaction_environment(self, window_id):
                return PlatformResult.failure(
                    PlatformErrorCode.NOT_SUPPORTED, "no hay adaptador",
                    operation="check_interaction_environment", platform="fake",
                )
        adapter = _Falla()
        adapter.platform_name = "falla"
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertEqual(check.reasons, ["environment_check_unavailable:not_supported"])

    def test_resultado_sin_valor_deniega(self):
        class _Vacio(DesktopPlatformAdapter):
            def check_interaction_environment(self, window_id):
                return PlatformResult.success(None)
        adapter = _Vacio()
        adapter.platform_name = "vacio"
        check = check_interaction_environment(adapter, 1234)
        self.assertFalse(check.allowed)
        self.assertEqual(check.reasons, ["environment_check_unavailable:unknown"])


class TestInteractionEnvironmentModelo(unittest.TestCase):
    """Modelo de datos del entorno: razones de bloqueo y allowed."""

    def test_sin_bloqueos_no_tiene_razones(self):
        env = InteractionEnvironment()
        self.assertEqual(env.blocking_reasons(), [])
        self.assertTrue(env.allowed)

    def test_todas_las_banderas_devuelven_todas_las_razones(self):
        env = InteractionEnvironment(
            session_locked=True, secure_desktop=True, target_elevated=True,
            jarvis_elevated=False, protected_content=True, protected_window=True,
            overlay_windows=[111, 222], target_minimized=True, target_visible=False,
            permissions_missing=["accessibility", "screen_recording"],
        )
        razones = env.blocking_reasons()
        for motivo in ("session_locked", "secure_desktop", "target_elevated",
                       "protected_content", "protected_window", "overlay_present",
                       "target_minimized", "target_hidden",
                       "permission_missing:accessibility",
                       "permission_missing:screen_recording"):
            self.assertIn(motivo, razones)

    def test_objetivo_elevado_con_jarvis_elevado_no_bloquea(self):
        env = InteractionEnvironment(target_elevated=True, jarvis_elevated=True)
        self.assertEqual(env.blocking_reasons(), [])
        self.assertTrue(env.allowed)

    def test_objetivo_elevado_sin_jarvis_bloquea(self):
        env = InteractionEnvironment(target_elevated=True, jarvis_elevated=False)
        self.assertEqual(env.blocking_reasons(), ["target_elevated"])
        self.assertFalse(env.allowed)

    def test_to_dict_contiene_campos_concretos(self):
        env = InteractionEnvironment(session_locked=True, overlay_windows=[5])
        d = env.to_dict()
        self.assertEqual(d["allowed"], False)
        self.assertEqual(d["session_locked"], True)
        self.assertEqual(d["overlay_windows"], [5])
        self.assertIsInstance(d["blocking_reasons"], list)
        self.assertIn("session_locked", d["blocking_reasons"])


class TestInteractionEnvironmentNotepadReal(TestGuiBase):
    """Integracion real con el adaptador Windows y una ventana de Notepad.

    Reusa la unica ventana de Notepad compartida por sesion en el monitor
    secundario derecho. No se envian entradas ni se toca VS Code.
    """

    def test_adaptador_windows_real_devuelve_entorno_permitido_notepad(self):
        from src.desktop.platform_windows import WindowsDesktopAdapter

        adapter = WindowsDesktopAdapter()
        check = check_interaction_environment(adapter, int(self.hwnd))
        self.assertTrue(
            check.allowed, "Notepad normal debiera permitir interaccion: %s" % check.reasons
        )
        env = check.environment
        self.assertIsNotNone(env)
        self.assertFalse(env.get("session_locked"))
        self.assertFalse(env.get("secure_desktop"))
        self.assertFalse(env.get("target_elevated"))
        self.assertFalse(env.get("protected_content"))
        self.assertFalse(env.get("protected_window"))
        self.assertFalse(env.get("target_minimized"))
        self.assertTrue(env.get("target_visible"))
        self.assertIsInstance(env.get("overlay_windows"), list)
        self.assertIsInstance(env.get("permissions_missing"), list)
        d = check.to_dict()
        self.assertEqual(d["allowed"], True)
        self.assertEqual(d["reasons"], [])
        self.assertEqual(d["environment"]["target_visible"], True)
        self.assertEqual(d["environment"]["target_minimized"], False)

    def test_hwnd_inexistente_devuelve_window_gone(self):
        from src.desktop.platform_windows import WindowsDesktopAdapter

        adapter = WindowsDesktopAdapter()
        check = check_interaction_environment(adapter, 0xBADF00D)
        self.assertFalse(check.allowed)
        self.assertEqual(check.reasons, ["window_gone"])

