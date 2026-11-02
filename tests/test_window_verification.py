"""
Tests for window verification (3.5.2.2).
Uses mocks to test _verificar_aplicacion_abierta.
"""
import unittest
from unittest.mock import patch, Mock
import sys
sys.path.insert(0, r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS')
from src.hands.windows.windows import _verificar_aplicacion_abierta


class TestWindowVerification(unittest.TestCase):
    def test_window_visible(self):
        """Mock _get_application_windows returning a visible window -> True."""
        mock_win = Mock()
        mock_win.is_visible = True
        with patch('src.hands.windows.windows._get_application_windows', return_value=[mock_win]):
            result = _verificar_aplicacion_abierta("calculator")
            self.assertTrue(result)

    def test_window_not_visible(self):
        """Mock window with is_visible=False -> False."""
        mock_win = Mock()
        mock_win.is_visible = False
        with patch('src.hands.windows.windows._get_application_windows', return_value=[mock_win]):
            result = _verificar_aplicacion_abierta("calculator")
            self.assertFalse(result)

    def test_no_windows(self):
        """Empty list -> False."""
        with patch('src.hands.windows.windows._get_application_windows', return_value=[]):
            result = _verificar_aplicacion_abierta("calculator")
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()