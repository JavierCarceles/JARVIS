# -*- coding: utf-8 -*-
"""Tests de inicialización del paquete ear (src/ear/__init__.py)."""

import unittest

from src.ear import Ear


class TestEarPackageInit(unittest.TestCase):
    def test_ear_exported(self):
        self.assertTrue(callable(Ear))

    def test_ear_importable_from_listener(self):
        from src.ear.listener import Ear as EarFromListener
        self.assertIs(EarFromListener, Ear)


if __name__ == "__main__":
    unittest.main()
