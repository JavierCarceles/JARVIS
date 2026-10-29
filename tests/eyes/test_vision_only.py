# -*- coding: utf-8 -*-
"""Tests de vision_only.py (versión simplificada de Vision)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.eyes.vision_only import (
    UIElement,
    Vision,
    VisionNodeType,
    VisionResponse,
)


class TestVisionNodeType:
    def test_values(self):
        assert VisionNodeType.SCREEN_ANALYSIS.value == "screen_analysis"
        assert VisionNodeType.UI_DETECTON.value == "ui_detection"
        assert VisionNodeType.ELEMENT_VERIFICATION.value == "element_verification"
        assert VisionNodeType.STATE_VERIFICATION.value == "state_verification"
        assert VisionNodeType.CALIBRATION_ANALYSIS.value == "calibration_analysis"
        assert VisionNodeType.APPLICATION_DETECTION.value == "application_detection"


class TestVisionOnlyUIElement:
    def test_create_full(self):
        elem = UIElement(
            name="btn_ok",
            type="button",
            text="OK",
            bbox=[10, 20, 100, 80],
            center=[55, 50],
            interactive=True,
            confidence=0.95,
        )
        assert elem.name == "btn_ok"
        assert elem.type == "button"
        assert elem.text == "OK"
        assert elem.bbox == [10, 20, 100, 80]
        assert elem.center == [55, 50]
        assert elem.interactive is True
        assert elem.confidence == 0.95

    def test_create_minimal(self):
        elem = UIElement(
            name="btn",
            type="button",
            bbox=[0, 0, 10, 10],
            confidence=0.5,
        )
        assert elem.text == ""
        assert elem.center == []
        assert elem.interactive is True


class TestVisionOnlyResponse:
    def test_empty(self):
        resp = VisionResponse()
        assert resp.elements == []

    def test_with_elements(self):
        elem = UIElement(name="x", type="button", bbox=[0, 0, 10, 10], confidence=0.8)
        resp = VisionResponse(elements=[elem])
        assert len(resp.elements) == 1


class TestVisionOnlyInit:
    @patch("src.eyes.vision_only.ollama")
    def test_default_model(self, _mock):
        vision = Vision()
        assert vision.model == "qwen3-vl:8b"
        assert vision.temperature == 0
        assert vision.screen_capture is not None
        assert vision.memory_manager is None
        assert vision._vision_nodes == []

    @patch("src.eyes.vision_only.ollama")
    def test_custom_model(self, _mock):
        vision = Vision(model="my-model")
        assert vision.model == "my-model"


class TestVisionOnlyGetVisionCapabilities:
    @patch("src.eyes.vision_only.ollama")
    def test_capabilities(self, _mock):
        vision = Vision()
        caps = vision.get_vision_capabilities()
        assert "nodes" in caps
        assert caps["model"] == "qwen3-vl:8b"
        assert caps["total_cost"] == 10.0
        assert "available_types" in caps
        assert "ui_detection" in caps["available_types"]


class TestVisionOnlyGetTotalVisionCost:
    @patch("src.eyes.vision_only.ollama")
    def test_fixed_cost(self, _mock):
        vision = Vision()
        assert vision.get_total_vision_cost() == 10.0


class TestVisionOnlyAnalyzeImage:
    @patch("src.eyes.vision_only.ollama")
    def test_analyze_image_success(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"elements": [
                {"name": "btn", "type": "button", "bbox": [1, 2, 3, 4], "confidence": 0.9}
            ]})}
        }
        vision = Vision()
        result = vision.analyze_image("/fake/image.png", "find buttons")
        assert isinstance(result, str)
        data = json.loads(result)
        assert "elements" in data

    @patch("src.eyes.vision_only.ollama")
    def test_analyze_image_empty_response(self, mock_ollama):
        mock_ollama.chat.return_value = {"message": {"content": ""}}
        vision = Vision()
        result = vision.analyze_image("/fake/image.png", "prompt")
        assert result == ""

    @patch("src.eyes.vision_only.ollama")
    def test_analyze_image_exception(self, mock_ollama):
        mock_ollama.chat.side_effect = RuntimeError("fail")
        vision = Vision()
        result = vision.analyze_image("/fake/image.png", "prompt")
        assert "ERROR:" in result

    @patch("src.eyes.vision_only.ollama")
    def test_analyze_image_calls_ollama(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"elements": []})}
        }
        vision = Vision()
        vision.analyze_image("/fake/image.png", "prompt")
        mock_ollama.chat.assert_called_once()
        kwargs = mock_ollama.chat.call_args.kwargs
        assert kwargs["model"] == "qwen3-vl:8b"
        assert "images" in kwargs["messages"][0]
        assert kwargs["messages"][0]["content"] == "prompt"


class TestVisionOnlyVerifyActionResult:
    @patch("src.eyes.vision_only.ollama")
    def test_success_verified(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"verified": True, "confidence": 0.95, "details": "OK"})}
        }
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        result = vision.verify_action_result({"type": "url_loaded", "url": "https://x.com"})
        assert result["success"] is True
        assert result["verified"] is True
        assert result["confidence"] == 0.95

    @patch("src.eyes.vision_only.ollama")
    def test_low_confidence(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"verified": True, "confidence": 0.5})}
        }
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        result = vision.verify_action_result({"type": "custom"}, tolerance=0.9)
        assert result["verified"] is False

    @patch("src.eyes.vision_only.ollama")
    def test_no_screenshot(self, mock_ollama):
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value=None)
        result = vision.verify_action_result({"type": "url_loaded"})
        assert result["success"] is False
        assert result["verified"] is False

    @patch("src.eyes.vision_only.ollama")
    def test_invalid_json(self, mock_ollama):
        mock_ollama.chat.return_value = {"message": {"content": "not json"}}
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        result = vision.verify_action_result({"type": "url_loaded"})
        assert result["success"] is False
        assert result["verified"] is False

    @patch("src.eyes.vision_only.ollama")
    def test_exception(self, mock_ollama):
        mock_ollama.chat.side_effect = RuntimeError("fail")
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        result = vision.verify_action_result({"type": "url_loaded"})
        assert result["success"] is False
        assert result["verified"] is False
        assert "fail" in result["error"]


class TestVisionOnlyDetectApplicationState:
    @patch("src.eyes.vision_only.ollama")
    def test_app_detected_active(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"detected": True, "state": "active",
                "window_title": "Chrome", "visible_elements": ["tab"], "confidence": 0.9})}
        }
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("chrome")
        assert result.name == "chrome"
        assert result.state == ApplicationState.ACTIVE
        assert result.window_title == "Chrome"

    @patch("src.eyes.vision_only.ollama")
    def test_app_not_detected(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"detected": False})}
        }
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision_only.ollama")
    def test_empty_name(self, mock_ollama):
        vision = Vision()
        from src.eyes.screen import ApplicationState, ApplicationInfo
        result = vision.detect_application_state("")
        assert result.state == ApplicationState.CLOSED
        assert isinstance(result, ApplicationInfo)

    @patch("src.eyes.vision_only.ollama")
    def test_no_screenshot(self, mock_ollama):
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value=None)
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision_only.ollama")
    def test_unknown_state_does_not_become_valid(self, mock_ollama):
        """3.4.1.3: un estado desconocido NO se convierte en un estado valido
        por defecto. Anteriormente caia en ApplicationState.OPEN; ahora debe
        usar CLOSED como fallback seguro."""
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"detected": True, "state": "unknown"})}
        }
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision_only.ollama")
    def test_exception_returns_closed(self, mock_ollama):
        mock_ollama.chat.side_effect = RuntimeError("fail")
        vision = Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED
