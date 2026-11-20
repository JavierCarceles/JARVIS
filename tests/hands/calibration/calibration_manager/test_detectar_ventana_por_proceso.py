# -*- coding: utf-8 -*-
"""Tests unitarios para la unidad 3.8.5.5.2.

Cubre:
- detect_window_for_process: ventana cuyo PID esta en el arbol de procesos
  del objetivo -> detectada.
- detect_window_for_process: ventana cuyo owner HWND pertenece a una
  ventana del arbol de procesos -> detectada.
- detect_window_for_process: coincidencia solo por titulo (proceso distinto)
  -> NO detectada (rechazada).
- detect_window_for_process: sin ventana candidata -> None.
- detect_window_for_process: root_pid None o invalido -> None.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.hands.calibration.calibration_manager import CalibrationManager


def _make_manager():
    """Instancia CalibrationManager mockeando dependencias pesadas de __init__."""
    with patch(
        "src.hands.calibration.calibration_manager.get_screen_manager",
        return_value=MagicMock(),
    ), patch(
        "src.hands.calibration.calibration_manager.get_calibration_config",
        return_value=MagicMock(),
    ), patch(
        "src.hands.calibration.universal_visual_calibrator.UniversalVisualCalibrator",
        return_value=MagicMock(),
    ):
        manager = CalibrationManager()
    return manager


def _make_window(hwnd, title, pid, owner_hwnd=None, visible=True, enabled=True):
    """Crea un objeto ventana simulado con los atributos usados por CalibrationManager."""
    win = MagicMock()
    win._hWnd = hwnd
    win._hwnd = hwnd
    win.hwnd = hwnd
    win.title = title
    win.is_visible = visible
    return win


class TestDetectarVentanaPorProceso(unittest.TestCase):
    """3.8.5.5.2 - Detectar ventana perteneciente al proceso/aplicacion
    objetivo mediante identificadores y propietario, sin coincidencia solo
    por titulo."""

    def test_ventana_con_pid_en_arbol_de_procesos_es_detectada(self):
        """PID de ventana en el arbol de procesos del objetivo -> detectada."""
        manager = _make_manager()

        manager._get_process_tree = MagicMock(return_value={1000, 1001})
        manager._get_windows = MagicMock(
            return_value=[
                _make_window(hwnd=101, title="Otra app", pid=999),
                _make_window(hwnd=102, title="Objetivo", pid=1000),
            ]
        )
        manager._get_window_handle = MagicMock(side_effect=lambda w: w._hWnd)
        manager._get_window_process_id = MagicMock(
            side_effect=lambda w: 999 if w._hWnd == 101 else 1000
        )
        manager._win32_get_owner = MagicMock(return_value=None)
        manager._window_is_usable = MagicMock(return_value=True)
        manager._normalize_application_name = MagicMock(side_effect=lambda s: s or "")
        manager._get_window_process_name = MagicMock(return_value="objetivo.exe")

        resultado = manager.detect_window_for_process(root_pid=1000, timeout=0.1)

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado._hWnd, 102)

    def test_ventana_con_owner_en_arbol_de_procesos_es_detectada(self):
        """Owner HWND perteneciente al arbol de procesos -> detectada."""
        manager = _make_manager()

        # El proceso raiz es 1000. La ventana 102 tiene PID 2000 (no en arbol)
        # pero su owner es la ventana 101 (PID 1000, si en arbol).
        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_windows = MagicMock(
            return_value=[
                _make_window(hwnd=101, title="Owner", pid=1000),
                _make_window(hwnd=102, title="Owned", pid=2000, owner_hwnd=101),
            ]
        )
        manager._get_window_handle = MagicMock(side_effect=lambda w: w._hWnd)
        manager._get_window_process_id = MagicMock(
            side_effect=lambda w: 1000 if w._hWnd == 101 else 2000
        )
        manager._win32_get_owner = MagicMock(
            side_effect=lambda hwnd: 101 if hwnd == 102 else None
        )
        manager._get_window_by_handle = MagicMock(
            side_effect=lambda hwnd: _make_window(hwnd=hwnd, title="x", pid=1000)
            if hwnd == 101
            else None
        )
        manager._window_is_usable = MagicMock(return_value=True)
        manager._normalize_application_name = MagicMock(side_effect=lambda s: s or "")
        manager._get_window_process_name = MagicMock(return_value="owned.exe")

        resultado = manager.detect_window_for_process(root_pid=1000, timeout=0.1)

        self.assertIsNotNone(resultado)
        # La ventana con PID directo en el arbol (score 300) se prefiere
        # sobre la ventana solo por owner (score 150).
        self.assertEqual(resultado._hWnd, 101)

    def test_solo_owner_match_sin_pid_directo_es_detectada(self):
        """Solo hay una ventana por owner (ninguna con PID en arbol) -> detectada."""
        manager = _make_manager()

        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_windows = MagicMock(
            return_value=[
                _make_window(hwnd=101, title="Owner", pid=1000, visible=True),
                _make_window(hwnd=102, title="Owned", pid=2000, owner_hwnd=101, visible=True),
            ]
        )
        manager._get_window_handle = MagicMock(side_effect=lambda w: w._hWnd)
        manager._get_window_process_id = MagicMock(
            side_effect=lambda w: 1000 if w._hWnd == 101 else 2000
        )
        manager._win32_get_owner = MagicMock(
            side_effect=lambda hwnd: 101 if hwnd == 102 else None
        )
        manager._get_window_by_handle = MagicMock(
            side_effect=lambda hwnd: _make_window(hwnd=hwnd, title="x", pid=1000, visible=False)
            if hwnd == 101
            else None
        )
        # Window 101 (dueno) no es usable (p.ej. minimizada/oculta), por lo que
        # no compite como candidato directo; solo window 102 (owner match) queda.
        manager._window_is_usable = MagicMock(
            side_effect=lambda w, allow_console=False: w._hWnd == 102
        )
        manager._normalize_application_name = MagicMock(side_effect=lambda s: s or "")
        manager._get_window_process_name = MagicMock(return_value="owned.exe")

        resultado = manager.detect_window_for_process(root_pid=1000, timeout=0.1)

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado._hWnd, 102)

    def test_coincidencia_solo_por_titulo_no_es_detectada(self):
        """Ventana con titulo coincidente pero proceso distinto -> NO detectada."""
        manager = _make_manager()

        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_windows = MagicMock(
            return_value=[
                _make_window(hwnd=101, title="Objetivo App", pid=999),
            ]
        )
        manager._get_window_handle = MagicMock(side_effect=lambda w: w._hWnd)
        manager._get_window_process_id = MagicMock(return_value=999)
        manager._win32_get_owner = MagicMock(return_value=None)
        manager._window_is_usable = MagicMock(return_value=True)
        manager._normalize_application_name = MagicMock(side_effect=lambda s: s or "")
        manager._get_window_process_name = MagicMock(return_value="otra.exe")

        resultado = manager.detect_window_for_process(
            root_pid=1000, application_name="Objetivo App", timeout=0.1
        )

        self.assertIsNone(resultado)

    def test_sin_ventana_candidata_retorna_none(self):
        """No hay ventana que pertenezca al proceso -> None."""
        manager = _make_manager()

        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_windows = MagicMock(return_value=[])
        manager._get_window_handle = MagicMock(return_value=None)
        manager._get_window_process_id = MagicMock(return_value=None)
        manager._win32_get_owner = MagicMock(return_value=None)
        manager._window_is_usable = MagicMock(return_value=False)
        manager._normalize_application_name = MagicMock(side_effect=lambda s: s or "")

        resultado = manager.detect_window_for_process(root_pid=1000, timeout=0.1)

        self.assertIsNone(resultado)

    def test_root_pid_none_retorna_none(self):
        """root_pid None -> None sin consultar ventanas."""
        manager = _make_manager()
        manager._get_windows = MagicMock(return_value=[])

        resultado = manager.detect_window_for_process(root_pid=None, timeout=0.1)

        self.assertIsNone(resultado)

    def test_root_pid_cero_retorna_none(self):
        """root_pid 0 -> None."""
        manager = _make_manager()
        manager._get_windows = MagicMock(return_value=[])

        resultado = manager.detect_window_for_process(root_pid=0, timeout=0.1)

        self.assertIsNone(resultado)

    def test_ventana_no_usable_no_es_candidata(self):
        """Ventana no usable (no visible/habilitada) -> no es candidata."""
        manager = _make_manager()

        manager._get_process_tree = MagicMock(return_value={1000})
        manager._get_windows = MagicMock(
            return_value=[_make_window(hwnd=101, title="Inutil", pid=1000)]
        )
        manager._get_window_handle = MagicMock(side_effect=lambda w: w._hWnd)
        manager._get_window_process_id = MagicMock(return_value=1000)
        manager._win32_get_owner = MagicMock(return_value=None)
        manager._window_is_usable = MagicMock(return_value=False)
        manager._normalize_application_name = MagicMock(side_effect=lambda s: s or "")

        resultado = manager.detect_window_for_process(root_pid=1000, timeout=0.1)

        self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()
