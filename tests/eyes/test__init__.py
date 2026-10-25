# -*- coding: utf-8 -*-
"""Tests de inicialización del paquete eyes (src/eyes/__init__.py)."""

import unittest


class TestEyesPackageInit(unittest.TestCase):
    def test_vision_exported(self):
        from src.eyes import Vision
        self.assertTrue(callable(Vision))

    def test_screen_capture_exported(self):
        from src.eyes import ScreenCapture
        self.assertTrue(callable(ScreenCapture))

    def test_get_screen_capture_exported(self):
        from src.eyes import get_screen_capture
        self.assertTrue(callable(get_screen_capture))


if __name__ == "__main__":
    unittest.main()
