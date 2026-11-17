"""Tests del procesador OpenCV de Vision (src/eyes/vision/vision.py).

Cubre la preparacion de recortes, normalizacion de color/tamano, deteccion
de cambios, deteccion de bordes/regiones y refinamiento de limites, asi
como la integracion opcional en detect_ui_elements. Todos los resultados de
contornos/bordes son pistas geometricas: nunca prueban interactividad.
"""

import os
import tempfile
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from src.eyes.capture.screen_capture import ScreenCapture
from src.eyes.vision.vision import (
    UIElement,
    Vision,
    VisionOpenCVProcessor,
    VisionResponse,
)


def _make_solid_image(size, color):
    height, width = size
    return np.full((height, width, 3), color, dtype=np.uint8)


def _write_png(path, image):
    cv2.imwrite(path, image)


class TestVisionOpenCVProcessorLoadImage:
    def test_load_image_missing_file_returns_none(self):
        assert VisionOpenCVProcessor.load_image("/ruta/que/no/existe.png") is None

    def test_load_image_none_returns_none(self):
        assert VisionOpenCVProcessor.load_image(None) is None

    def test_load_image_valid_returns_bgr_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            image = _make_solid_image((100, 150), (10, 20, 30))
            _write_png(path, image)
            loaded = VisionOpenCVProcessor.load_image(path)
            assert loaded is not None
            assert loaded.shape == (100, 150, 3)
            assert int(loaded[0, 0, 0]) == 10
            assert int(loaded[0, 0, 1]) == 20
            assert int(loaded[0, 0, 2]) == 30


class TestVisionOpenCVProcessorPrepareCrop:
    def test_prepare_crop_returns_expected_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            image = _make_solid_image((200, 300), (50, 60, 70))
            _write_png(path, image)
            crop = VisionOpenCVProcessor.prepare_crop(path, [50, 40, 150, 140], padding=0.0)
            assert crop is not None
            assert crop.shape[0] == 100
            assert crop.shape[1] == 100

    def test_prepare_crop_padding_expands(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            image = _make_solid_image((200, 300), (50, 60, 70))
            _write_png(path, image)
            crop = VisionOpenCVProcessor.prepare_crop(path, [100, 100, 120, 120], padding=0.5)
            assert crop is not None
            assert crop.shape == (40, 40, 3)

    def test_prepare_crop_clamps_to_image_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            image = _make_solid_image((100, 100), (50, 60, 70))
            _write_png(path, image)
            crop = VisionOpenCVProcessor.prepare_crop(path, [80, 80, 200, 200], padding=0.0)
            assert crop is not None
            assert crop.shape[0] <= 100
            assert crop.shape[1] <= 100

    def test_prepare_crop_invalid_bbox_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            image = _make_solid_image((100, 100), (50, 60, 70))
            _write_png(path, image)
            assert VisionOpenCVProcessor.prepare_crop(path, [100, 100, 90, 90]) is None
            assert VisionOpenCVProcessor.prepare_crop(path, [10, 10]) is None
            assert VisionOpenCVProcessor.prepare_crop("/no/existe.png", [10, 10, 20, 20]) is None


class TestVisionOpenCVProcessorNormalizeImage:
    def test_normalize_image_grayscale_returns_2d(self):
        image = _make_solid_image((50, 50), (10, 20, 30))
        result = VisionOpenCVProcessor.normalize_image(image, grayscale=True)
        assert result is not None
        assert len(result.shape) == 2

    def test_normalize_image_resize_changes_size(self):
        image = _make_solid_image((100, 100), (10, 20, 30))
        result = VisionOpenCVProcessor.normalize_image(image, target_size=(10, 20))
        assert result is not None
        assert result.shape == (20, 10, 3)

    def test_normalize_image_none_returns_none(self):
        assert VisionOpenCVProcessor.normalize_image(None) is None


class TestVisionOpenCVProcessorDetectChanges:
    def test_detect_changes_identical_frames_no_change(self):
        image = _make_solid_image((100, 100), (10, 20, 30))
        result = VisionOpenCVProcessor.detect_changes(image, image.copy())
        assert result["changed"] is False
        assert result["score"] == 0.0
        assert result["regions"] == []

    def test_detect_changes_different_frames_change_detected(self):
        a = _make_solid_image((100, 100), (10, 20, 30))
        b = _make_solid_image((100, 100), (200, 200, 200))
        result = VisionOpenCVProcessor.detect_changes(a, b)
        assert result["changed"] is True
        assert result["score"] > 0.0
        assert len(result["regions"]) >= 1

    def test_detect_changes_none_frame_no_change(self):
        image = _make_solid_image((100, 100), (10, 20, 30))
        assert VisionOpenCVProcessor.detect_changes(None, image)["changed"] is False
        assert VisionOpenCVProcessor.detect_changes(image, None)["changed"] is False
        assert VisionOpenCVProcessor.detect_changes(None, None)["changed"] is False


class TestVisionOpenCVProcessorDetectEdgesRegions:
    def test_detect_edges_regions_returns_regions_for_rectangle(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.rectangle(image, (50, 50), (150, 150), (255, 255, 255), -1)
        result = VisionOpenCVProcessor.detect_edges_regions(image)
        assert result["edges"] is not None
        assert result["count"] >= 1
        assert len(result["regions"]) >= 1
        for region in result["regions"]:
            assert len(region) == 4

    def test_detect_edges_regions_none_returns_empty(self):
        result = VisionOpenCVProcessor.detect_edges_regions(None)
        assert result["edges"] is None
        assert result["regions"] == []
        assert result["count"] == 0


class TestVisionOpenCVProcessorRefineBounds:
    def test_refine_bounds_returns_hint_only_true(self):
        image = _make_solid_image((100, 100), (10, 20, 30))
        result = VisionOpenCVProcessor.refine_bounds(image, [10, 10, 90, 90])
        assert result["hint_only"] is True
        assert result["ok"] is True
        assert result["refined_bbox"] is not None

    def test_refine_bounds_refines_within_original(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.rectangle(image, (60, 60), (140, 140), (255, 255, 255), -1)
        result = VisionOpenCVProcessor.refine_bounds(image, [50, 50, 150, 150])
        assert result["ok"] is True
        refined = result["refined_bbox"]
        assert refined is not None
        x1, y1, x2, y2 = refined
        assert x1 >= 50 and y1 >= 50
        assert x2 <= 150 and y2 <= 150
        assert x2 > x1 and y2 > y1

    def test_refine_bounds_invalid_returns_not_ok(self):
        image = _make_solid_image((100, 100), (10, 20, 30))
        assert VisionOpenCVProcessor.refine_bounds(None, [10, 10, 90, 90])["ok"] is False
        assert VisionOpenCVProcessor.refine_bounds(image, [100, 100, 90, 90])["ok"] is False
        assert VisionOpenCVProcessor.refine_bounds(image, [10, 10])["ok"] is False

    def test_refine_bounds_never_marks_interactive(self):
        image = _make_solid_image((100, 100), (10, 20, 30))
        result = VisionOpenCVProcessor.refine_bounds(image, [10, 10, 90, 90])
        assert "interactive" not in result
        assert result["hint_only"] is True


class TestVisionDetectUIElementsOpenCVRefine:
    def setup_method(self, _method=None):
        self.vision = Vision()

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_default_no_refine(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": '{"elements": [{"type": "button", "text": "OK", "bbox": [10, 20, 100, 80], "center": [55, 50], "interactive": true, "confidence": 0.95}]}'}
        }
        resp = self.vision.detect_ui_elements("/fake/image.png")
        assert len(resp.elements) == 1
        assert resp.elements[0].bbox == [10, 20, 100, 80]
        assert resp.elements[0].interactive is True

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_refine_with_opencv_interactive_unchanged(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": '{"elements": [{"type": "button", "text": "OK", "bbox": [10, 20, 100, 80], "center": [55, 50], "interactive": true, "confidence": 0.95}]}'}
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "img.png")
            image = np.zeros((200, 200, 3), dtype=np.uint8)
            cv2.rectangle(image, (15, 25, 95, 75), (255, 255, 255), -1)
            cv2.imwrite(path, image)
            resp = self.vision.detect_ui_elements(path, refine_with_opencv=True)
            assert len(resp.elements) == 1
            assert resp.elements[0].interactive is True
            assert resp.elements[0].bbox is not None
            assert len(resp.elements[0].bbox) == 4


class TestVisionOpenCVRealEnvironment:
    def test_real_screen_capture_and_opencv_preprocessing(self):
        """Verifica el procesador OpenCV sobre una captura real de pantalla
        del equipo (sin entrada de teclado/raton y sin activar ventanas)."""
        screen_capture = ScreenCapture()
        monitor_info = None
        try:
            from src.desktop.screen_manager import get_monitor_info
            monitor_info = get_monitor_info(1)
        except Exception:
            monitor_info = None
        if monitor_info is None:
            pytest.skip("No hay monitor 1 disponible para captura real")
        image_path = screen_capture.capture_monitor(1)
        if not image_path:
            pytest.skip("No se pudo capturar el monitor 1 en el equipo real")
        try:
            image = VisionOpenCVProcessor.load_image(image_path)
            assert image is not None
            assert len(image.shape) == 3
            height, width = image.shape[:2]
            cx, cy = width // 2, height // 2
            crop = VisionOpenCVProcessor.prepare_crop(
                image_path, [cx - 100, cy - 100, cx + 100, cy + 100], padding=0.0
            )
            assert crop is not None
            assert crop.shape == (200, 200, 3)
            gray = VisionOpenCVProcessor.normalize_image(crop, grayscale=True)
            assert gray is not None and len(gray.shape) == 2
            edges = VisionOpenCVProcessor.detect_edges_regions(crop)
            assert edges["edges"] is not None
            assert edges["count"] >= 0
            same = VisionOpenCVProcessor.detect_changes(crop, crop.copy())
            assert same["changed"] is False
            assert same["score"] == 0.0
            refined = VisionOpenCVProcessor.refine_bounds(crop, [10, 10, 190, 190])
            assert refined["hint_only"] is True
            assert refined["ok"] is True
        finally:
            try:
                os.remove(image_path)
            except OSError:
                pass
