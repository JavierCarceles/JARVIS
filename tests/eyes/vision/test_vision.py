# -*- coding: utf-8 -*-
"""Tests de Vision (src/eyes/vision/vision.py)."""

import io
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.eyes.vision.vision import (
    DEFAULT_VISION_MODEL,
    MODEL_IMAGE_MAX_PIXELS,
    Vision,
    VisionNode,
    VisionNodeType,
    UIElement,
    VisionResponse,
)


def json_dumps(obj):
    return json.dumps(obj)


def _png(path, width, height, color=(240, 240, 240)):
    """Escribe una imagen PNG real de width x height y devuelve su ruta."""
    Image.new("RGB", (width, height), color).save(path, format="PNG")
    return str(path)


class TestVisionNodeType:
    def test_values(self):
        assert VisionNodeType.SCREEN_ANALYSIS.value == "screen_analysis"
        assert VisionNodeType.UI_DETECTION.value == "ui_detection"
        assert VisionNodeType.UI_DETECTON.value == "ui_detection"  # legacy alias
        assert VisionNodeType.ELEMENT_VERIFICATION.value == "element_verification"
        assert VisionNodeType.STATE_VERIFICATION.value == "state_verification"
        assert VisionNodeType.CALIBRATION_ANALYSIS.value == "calibration_analysis"
        assert VisionNodeType.APPLICATION_DETECTION.value == "application_detection"

    def test_ui_detecton_is_alias(self):
        assert VisionNodeType.UI_DETECTON.value == VisionNodeType.UI_DETECTION.value


class TestVisionNode:
    def _make(self, **overrides):
        defaults = dict(
            id="test.node",
            type=VisionNodeType.SCREEN_ANALYSIS,
            name="Test Node",
            description="desc",
            preconditions=["a"],
            effects=["b"],
            cost=5.0,
            dependencies=["dep1"],
            parameters={"k": "v"},
            application="app1",
            ui_element="elem1",
            execute_function="do_thing",
            success_criteria=["ok"],
            metadata={"meta": True},
        )
        defaults.update(overrides)
        return VisionNode(**defaults)

    def test_defaults(self):
        node = VisionNode(
            id="n1", type=VisionNodeType.UI_DETECTION, name="N", description="D"
        )
        assert node.id == "n1"
        assert node.type == VisionNodeType.UI_DETECTION
        assert node.name == "N"
        assert node.description == "D"
        assert node.preconditions == []
        assert node.effects == []
        assert node.cost == 1.0
        assert node.dependencies == []
        assert node.parameters == {}
        assert node.application is None
        assert node.ui_element is None
        assert node.execute_function is None
        assert node.success_criteria == []
        assert node.metadata == {}

    def test_to_dict_serializes_type(self):
        node = self._make()
        d = node.to_dict()
        assert d["id"] == "test.node"
        assert d["type"] == "screen_analysis"
        assert d["name"] == "Test Node"
        assert d["cost"] == 5.0
        assert d["application"] == "app1"

    def test_from_dict_roundtrip(self):
        node = self._make()
        d = node.to_dict()
        restored = VisionNode.from_dict(d)
        assert restored.id == node.id
        assert restored.type == node.type
        assert restored.name == node.name
        assert restored.cost == node.cost
        assert restored.application == node.application
        assert restored.parameters == node.parameters

    def test_from_dict_with_string_type(self):
        d = {
            "id": "x",
            "type": "ui_detection",
            "name": "X",
            "description": "d",
        }
        node = VisionNode.from_dict(d)
        assert node.type == VisionNodeType.UI_DETECTION

    def test_get_preconditions(self):
        node = self._make(preconditions=["p1", "p2"])
        assert node.get_preconditions() == ["p1", "p2"]

    def test_get_effects(self):
        node = self._make(effects=["e1"])
        assert node.get_effects() == ["e1"]

    def test_get_cost(self):
        node = self._make(cost=3.5)
        assert node.get_cost() == 3.5


class TestUIElement:
    def test_create_full(self):
        elem = UIElement(
            type="button",
            text="OK",
            bbox=[10, 20, 100, 80],
            center=[55, 50],
            interactive=True,
            confidence=0.95,
        )
        assert elem.type == "button"
        assert elem.text == "OK"
        assert elem.bbox == [10, 20, 100, 80]
        assert elem.center == [55, 50]
        assert elem.interactive is True
        assert elem.confidence == 0.95

    def test_create_minimum(self):
        elem = UIElement(
            type="input",
            text="",
            bbox=[0, 0, 1, 1],
            interactive=False,
            confidence=0.5,
        )
        assert elem.text == ""
        assert elem.center == []
        assert elem.interactive is False


class TestVisionResponse:
    def test_empty(self):
        resp = VisionResponse()
        assert resp.elements == []

    def test_with_elements(self):
        elem = UIElement(
            type="button", text="Go", bbox=[0, 0, 10, 10], confidence=0.8
        )
        resp = VisionResponse(elements=[elem])
        assert len(resp.elements) == 1
        assert resp.elements[0].type == "button"


class TestVisionInit:
    def test_default_model(self):
        # Variante sin razonamiento: la variante thinking deja content vacio.
        vision = Vision()
        assert DEFAULT_VISION_MODEL == "qwen3-vl:8b-instruct"
        assert vision.model == DEFAULT_VISION_MODEL
        assert vision.temperature == 0.0
        assert vision.screen_capture is not None

    def test_custom_model(self):
        vision = Vision(model="custom-model")
        assert vision.model == "custom-model"

    def test_vision_nodes_populated(self):
        vision = Vision()
        nodes = vision._vision_nodes
        assert len(nodes) >= 6
        ids = [n.id for n in nodes]
        assert "vision.analyze_screen" in ids
        assert "vision.detect_ui_elements" in ids
        assert "vision.verify_element" in ids


class TestVisionNodeQueries:
    def setup_method(self, _method=None):
        self.vision = Vision()

    def test_get_vision_nodes_returns_list(self):
        nodes = self.vision.get_vision_nodes()
        assert isinstance(nodes, list)
        assert len(nodes) >= 6

    def test_get_vision_node_found(self):
        node = self.vision.get_vision_node("vision.detect_ui_elements")
        assert node is not None
        assert node.type == VisionNodeType.UI_DETECTION

    def test_get_vision_node_not_found(self):
        assert self.vision.get_vision_node("nonexistent") is None

    def test_get_nodes_by_type(self):
        nodes = self.vision.get_nodes_by_type(VisionNodeType.SCREEN_ANALYSIS)
        assert len(nodes) >= 1
        assert all(n.type == VisionNodeType.SCREEN_ANALYSIS for n in nodes)

    def test_get_nodes_by_type_alias(self):
        nodes = self.vision.get_nodes_by_type(VisionNodeType.UI_DETECTON)
        assert len(nodes) >= 1

    def test_get_total_vision_cost(self):
        total = self.vision.get_total_vision_cost()
        assert total > 0
        assert total == sum(n.cost for n in self.vision._vision_nodes)

    def test_get_vision_capabilities(self):
        caps = self.vision.get_vision_capabilities()
        assert "nodes" in caps
        assert "model" in caps
        assert "total_cost" in caps
        assert "available_types" in caps
        assert caps["model"] == DEFAULT_VISION_MODEL
        assert len(caps["nodes"]) >= 6
        types = caps["available_types"]
        assert "ui_detection" in types
        assert "screen_analysis" in types


class TestVisionSafeJsonLoads:
    def setup_method(self, _method=None):
        self.vision = Vision()

    def test_valid_json(self):
        assert self.vision._safe_json_loads('{"key": "value"}') == {"key": "value"}

    def test_empty_string(self):
        assert self.vision._safe_json_loads("") is None

    def test_none(self):
        assert self.vision._safe_json_loads(None) is None

    def test_markdown_wrapped(self):
        result = self.vision._safe_json_loads("```json\n{\"a\": 1}\n```")
        assert result == {"a": 1}

    def test_embedded_json(self):
        text = 'prefix {"a": 1} suffix'
        result = self.vision._safe_json_loads(text)
        assert result == {"a": 1}

    def test_invalid_json_no_braces(self):
        assert self.vision._safe_json_loads("not json") is None

    def test_invalid_json_malformed(self):
        assert self.vision._safe_json_loads("{broken") is None


class TestVisionClampFloat:
    def test_normal_value(self):
        assert Vision._clamp_float(0.5) == 0.5

    def test_above_range(self):
        assert Vision._clamp_float(1.5) == 1.0

    def test_below_range(self):
        assert Vision._clamp_float(-0.5) == 0.0

    def test_invalid_string(self):
        assert Vision._clamp_float("abc") == 0.0

    def test_none(self):
        assert Vision._clamp_float(None) == 0.0

    def test_int_value(self):
        assert Vision._clamp_float(1) == 1.0


class TestVisionNormalizeIntList:
    def test_valid_bbox(self):
        result = Vision._normalize_int_list([100, 200, 300, 400], minimum=4, maximum=4)
        assert result == [100, 200, 300, 400]

    def test_valid_center(self):
        result = Vision._normalize_int_list([50, 75], minimum=2, maximum=2)
        assert result == [50, 75]

    def test_wrong_length_too_short(self):
        assert Vision._normalize_int_list([1, 2], minimum=4, maximum=4) is None

    def test_wrong_length_too_long(self):
        assert Vision._normalize_int_list([1, 2, 3, 4, 5], minimum=2, maximum=2) is None

    def test_invalid_items(self):
        assert Vision._normalize_int_list(["a", "b", "c", "d"], minimum=4, maximum=4) is None

    def test_float_items_rounded(self):
        result = Vision._normalize_int_list([1.4, 2.6, 3.5, 4.0], minimum=4, maximum=4)
        assert result == [1, 3, 4, 4]

    def test_none_input(self):
        assert Vision._normalize_int_list(None, minimum=4, maximum=4) is None

    def test_non_list_input(self):
        assert Vision._normalize_int_list("not a list", minimum=4, maximum=4) is None


class TestVisionCoordinatesMatch:
    def test_no_expected_coords(self):
        assert Vision._coordinates_match(None, [100, 200], [0, 0, 10, 10]) is True

    def test_no_numeric_coords(self):
        assert Vision._coordinates_match({"x": "abc", "y": None}, [100, 200], [0, 0]) is True

    def test_within_tolerance(self):
        result = Vision._coordinates_match(
            {"x": 100, "y": 200}, [100, 200], [0, 0, 10, 10], tolerance=0.10
        )
        assert result is True

    def test_outside_tolerance(self):
        result = Vision._coordinates_match(
            {"x": 100, "y": 200}, [50, 50], [0, 0, 10, 10], tolerance=0.10
        )
        assert result is False

    def test_custom_tolerance(self):
        result = Vision._coordinates_match(
            {"x": 100, "y": 200}, [95, 195], [0, 0, 10, 10], tolerance=0.10
        )
        assert result is True


class TestVisionBuildVerificationPrompt:
    def setup_method(self, _method=None):
        self.vision = Vision()

    def test_url_loaded(self):
        prompt = self.vision._build_verification_prompt(
            "url_loaded", {"url": "https://example.com"}, None
        )
        assert "https://example.com" in prompt
        assert "verified" in prompt
        assert "confidence" in prompt

    def test_element_focused(self):
        prompt = self.vision._build_verification_prompt(
            "element_focused", {"element": "login_btn"}, None
        )
        assert "login_btn" in prompt
        assert "verified" in prompt

    def test_application_opened(self):
        prompt = self.vision._build_verification_prompt(
            "application_opened", {"application": "chrome"}, None
        )
        assert "chrome" in prompt
        assert "window_title" in prompt

    def test_generic_type(self):
        expected_state = {"type": "custom", "value": 42}
        prompt = self.vision._build_verification_prompt("custom", expected_state, "chrome")
        assert "chrome" in prompt

    def test_generic_type_with_application(self):
        prompt = self.vision._build_verification_prompt(
            "unknown_type", {"foo": "bar"}, "firefox"
        )
        assert "firefox" in prompt


class TestVisionDetectUIElements:
    """Deteccion con Ollama falso sobre imagenes PNG reales.

    Qwen3-VL devuelve las cajas normalizadas 0..1000; ``detect_ui_elements``
    las convierte a pixeles de la imagen analizada, por eso cada prueba usa
    una imagen real de tamano conocido.
    """

    def setup_method(self, _method=None):
        self.vision = Vision()
        self._tmp = tempfile.TemporaryDirectory()
        self.image_path = _png(os.path.join(self._tmp.name, "captura.png"), 400, 200)

    def teardown_method(self, _method=None):
        self._tmp.cleanup()

    @staticmethod
    def _content(elements):
        return {"message": {"content": json_dumps({"elements": elements})}}

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_valid(self, mock_ollama):
        mock_ollama.chat.return_value = self._content([
            {"name": "ok", "type": "button", "text": "OK", "bbox": [100, 200, 300, 600],
             "interactive": True, "confidence": 0.95}
        ])
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.error is None
        assert resp.image_size == [400, 200]
        assert len(resp.elements) == 1
        assert resp.elements[0].type == "button"
        assert resp.elements[0].text == "OK"
        assert resp.elements[0].confidence == 0.95
        # 0..1000 -> pixeles de una imagen 400x200.
        assert resp.elements[0].bbox == [40, 40, 120, 120]
        assert resp.elements[0].center == [80, 80]

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_no_response(self, mock_ollama):
        mock_ollama.chat.return_value = {"message": {"content": ""}}
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.elements == []
        assert resp.error is not None
        assert "vacia" in resp.error

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_invalid_bbox(self, mock_ollama):
        mock_ollama.chat.return_value = self._content([
            {"type": "button", "text": "X", "bbox": [1, 2],  # wrong length
             "interactive": True, "confidence": 0.5}
        ])
        resp = self.vision.detect_ui_elements(self.image_path)
        assert len(resp.elements) == 0
        assert resp.discarded == 1
        assert resp.error is None

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_exception(self, mock_ollama):
        mock_ollama.chat.side_effect = Exception("network error")
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.elements == []
        assert resp.error is not None
        assert "network error" in resp.error

    @patch("src.eyes.vision.vision.ollama")
    def test_detect_ui_elements_with_application(self, mock_ollama):
        mock_ollama.chat.return_value = self._content([])
        resp = self.vision.detect_ui_elements(self.image_path, application="chrome")
        call_kwargs = mock_ollama.chat.call_args.kwargs
        assert "chrome" in call_kwargs["messages"][0]["content"]
        assert resp.error is None
        assert resp.elements == []

    @patch("src.eyes.vision.vision.ollama")
    def test_prompt_y_esquema_piden_cajas_normalizadas(self, mock_ollama):
        mock_ollama.chat.return_value = self._content([])
        self.vision.detect_ui_elements(self.image_path)
        call_kwargs = mock_ollama.chat.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]
        assert "NORMALIZADAS de 0 a 1000" in prompt
        schema = call_kwargs["format"]
        elements_schema = schema["properties"]["elements"]
        assert elements_schema["maxItems"] == self.vision.detection_max_elements
        assert "bbox" in elements_schema["items"]["required"]
        # El centro se calcula de la caja; no se pide al modelo.
        assert "center" not in elements_schema["items"]["properties"]
        assert call_kwargs["think"] is False

    @patch("src.eyes.vision.vision.ollama")
    def test_imagen_inexistente_devuelve_error_sin_llamar_al_modelo(self, mock_ollama):
        resp = self.vision.detect_ui_elements(os.path.join(self._tmp.name, "no_existe.png"))
        assert resp.elements == []
        assert resp.error is not None
        assert "no se pudo leer la imagen" in resp.error
        mock_ollama.chat.assert_not_called()

    @patch("src.eyes.vision.vision.ollama")
    def test_cajas_fuera_de_rango_o_invertidas_se_descartan(self, mock_ollama):
        mock_ollama.chat.return_value = self._content([
            {"name": "pixeles", "type": "button", "text": "A", "bbox": [100, 200, 1200, 600],
             "interactive": True, "confidence": 0.9},
            {"name": "invertida", "type": "button", "text": "B", "bbox": [500, 200, 100, 600],
             "interactive": True, "confidence": 0.9},
            {"name": "negativa", "type": "button", "text": "C", "bbox": [-5, 200, 100, 600],
             "interactive": True, "confidence": 0.9},
            {"name": "valida", "type": "button", "text": "D", "bbox": [0, 0, 1000, 1000],
             "interactive": True, "confidence": 0.9},
        ])
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.error is None
        assert [e.name for e in resp.elements] == ["valida"]
        assert resp.elements[0].bbox == [0, 0, 400, 200]
        assert resp.discarded == 3

    @patch("src.eyes.vision.vision.ollama")
    def test_elementos_repetidos_se_descartan(self, mock_ollama):
        repetido = {"name": "aceptar", "type": "button", "text": "Aceptar",
                    "bbox": [100, 100, 300, 300], "interactive": True, "confidence": 0.9}
        otro = dict(repetido, bbox=[600, 100, 800, 300])
        mock_ollama.chat.return_value = self._content([repetido, dict(repetido), otro])
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.error is None
        assert len(resp.elements) == 2
        assert resp.discarded == 1

    @patch("src.eyes.vision.vision.ollama")
    def test_maximo_de_elementos(self, mock_ollama):
        self.vision.detection_max_elements = 2
        mock_ollama.chat.return_value = self._content([
            {"name": "e%d" % i, "type": "button", "text": "", "bbox": [i * 100, 0, i * 100 + 50, 50],
             "interactive": True, "confidence": 0.9}
            for i in range(3)
        ])
        resp = self.vision.detect_ui_elements(self.image_path)
        assert len(resp.elements) == 2
        assert resp.discarded == 1
        assert mock_ollama.chat.call_args.kwargs["format"]["properties"]["elements"]["maxItems"] == 2

    @patch("src.eyes.vision.vision.ollama")
    def test_respuesta_cortada_recupera_elementos_completos(self, mock_ollama):
        completos = [
            {"name": "a", "type": "button", "text": "A", "bbox": [0, 0, 500, 500],
             "interactive": True, "confidence": 0.9},
            {"name": "b", "type": "link", "text": "B", "bbox": [500, 500, 1000, 1000],
             "interactive": True, "confidence": 0.8},
        ]
        cortado = json_dumps({"elements": completos})[:-2] + ', {"name": "c", "ty'
        mock_ollama.chat.return_value = {"message": {"content": cortado}, "done_reason": "length"}
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.error is None
        assert [e.name for e in resp.elements] == ["a", "b"]
        assert resp.truncated is True

    @patch("src.eyes.vision.vision.ollama")
    def test_solo_razonamiento_devuelve_error_explicito(self, mock_ollama):
        # Variante thinking: agota num_predict razonando y no devuelve contenido.
        vision = Vision(model="qwen3-vl:8b")
        mock_ollama.chat.return_value = {
            "message": {"content": "", "thinking": "Voy a analizar la imagen... " * 50},
            "done_reason": "length",
        }
        resp = vision.detect_ui_elements(self.image_path)
        assert resp.elements == []
        assert resp.truncated is True
        assert "razonamiento" in resp.error
        assert "variante sin razonamiento como %s" % DEFAULT_VISION_MODEL in resp.error

    @patch("src.eyes.vision.vision.ollama")
    def test_respuesta_sin_lista_elements_es_error(self, mock_ollama):
        mock_ollama.chat.return_value = {"message": {"content": json_dumps({"items": []})}}
        resp = self.vision.detect_ui_elements(self.image_path)
        assert resp.elements == []
        assert "elements" in resp.error

    @patch("src.eyes.vision.vision.ollama")
    def test_imagen_pequena_se_envia_sin_reducir(self, mock_ollama):
        mock_ollama.chat.return_value = self._content([])
        resp = self.vision.detect_ui_elements(self.image_path)
        call_kwargs = mock_ollama.chat.call_args.kwargs
        assert call_kwargs["messages"][0]["images"] == [self.image_path]
        assert call_kwargs["options"]["num_ctx"] == 8192
        assert resp.model_image_size == [400, 200]

    @patch("src.eyes.vision.vision.ollama")
    def test_captura_4k_se_reduce_y_las_cajas_vuelven_a_pixeles_originales(self, mock_ollama):
        grande = _png(os.path.join(self._tmp.name, "captura_4k.png"), 3840, 2000)
        mock_ollama.chat.return_value = self._content([
            {"name": "aceptar", "type": "button", "text": "Aceptar", "bbox": [500, 500, 600, 550],
             "interactive": True, "confidence": 0.9}
        ])
        resp = self.vision.detect_ui_elements(grande)
        call_kwargs = mock_ollama.chat.call_args.kwargs
        enviada = call_kwargs["messages"][0]["images"][0]
        # Se envia una copia PNG reducida en memoria, no la captura original.
        assert isinstance(enviada, bytes)
        with Image.open(io.BytesIO(enviada)) as reducida:
            ancho, alto = reducida.size
        assert ancho * alto <= MODEL_IMAGE_MAX_PIXELS
        assert abs(ancho / alto - 3840 / 2000) < 0.01
        assert resp.image_size == [3840, 2000]
        assert resp.model_image_size == [ancho, alto]
        # La caja se expresa en pixeles de la captura original.
        assert resp.error is None
        assert resp.elements[0].bbox == [1920, 1000, 2304, 1100]
        assert resp.elements[0].center == [2112, 1050]
        # La imagen reducida cabe en el contexto pedido: no se amplia.
        assert call_kwargs["options"]["num_ctx"] == 8192

    @patch("src.eyes.vision.vision.ollama")
    def test_num_ctx_se_amplia_si_la_imagen_no_cabe(self, mock_ollama):
        grande = _png(os.path.join(self._tmp.name, "captura_4k.png"), 3840, 2160)
        self.vision.max_image_pixels = 0  # sin reduccion
        mock_ollama.chat.return_value = self._content([])
        self.vision.detect_ui_elements(grande)
        call_kwargs = mock_ollama.chat.call_args.kwargs
        # 120 x 68 bloques de 32 px = 8160 tokens visuales + prompt + 4096 de salida.
        assert call_kwargs["options"]["num_ctx"] > 8160 + 4096
        assert call_kwargs["options"]["num_ctx"] % 1024 == 0
        assert call_kwargs["messages"][0]["images"] == [grande]


class TestVisionVerifyElementVisibility:
    def setup_method(self, _method=None):
        self.vision = Vision()
        self._tmp = tempfile.TemporaryDirectory()
        captura = _png(os.path.join(self._tmp.name, "monitor.png"), 1000, 500)
        self.vision.screen_capture = MagicMock()
        self.vision.screen_capture.capture_monitor = MagicMock(return_value=captura)
        self.vision.screen_capture.capture_active_window = MagicMock(return_value=None)

    def teardown_method(self, _method=None):
        self._tmp.cleanup()

    @patch("src.eyes.vision.vision.ollama")
    def test_element_found(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"elements": [
                {"name": "submit", "type": "button", "text": "Submit", "bbox": [10, 20, 100, 80],
                 "interactive": True, "confidence": 0.9}
            ]})}
        }
        result = self.vision.verify_element_visibility("submit")
        assert result["success"] is True
        assert result["verified"] is True
        assert result["found_element"]["type"] == "button"
        # Caja 0..1000 convertida a pixeles de la captura 1000x500.
        assert result["found_element"]["bbox"] == [10, 10, 100, 40]

    @patch("src.eyes.vision.vision.ollama")
    def test_fallo_de_deteccion_no_se_confunde_con_elemento_ausente(self, mock_ollama):
        mock_ollama.chat.side_effect = Exception("Ollama caido")
        result = self.vision.verify_element_visibility("submit")
        assert result["success"] is False
        assert result["verified"] is False
        assert "Ollama caido" in result["error"]

    @patch("src.eyes.vision.vision.ollama")
    def test_element_not_found(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"elements": []})}
        }
        result = self.vision.verify_element_visibility("missing_button")
        assert result["success"] is True
        assert result["verified"] is False
        assert "detectado" in result["error"].lower()

    @patch("src.eyes.vision.vision.ollama")
    def test_no_screenshot(self, mock_ollama):
        self.vision.screen_capture.capture_monitor = MagicMock(return_value=None)
        result = self.vision.verify_element_visibility("any_element")
        assert result["success"] is False
        assert result["verified"] is False
        assert "capturar" in result["error"].lower()


class TestVisionVerifyActionResult:
    def setup_method(self, _method=None):
        self.vision = Vision()
        self.vision.screen_capture = MagicMock()
        self.vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        self.vision.screen_capture.capture_active_window = MagicMock(return_value=None)

    @patch("src.eyes.vision.vision.ollama")
    def test_success_verified(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"verified": True, "confidence": 0.95, "details": "OK"})}
        }
        result = self.vision.verify_action_result({"type": "url_loaded", "url": "https://x.com"})
        assert result["success"] is True
        assert result["verified"] is True
        assert result["confidence"] == 0.95

    @patch("src.eyes.vision.vision.ollama")
    def test_not_verified_low_confidence(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"verified": True, "confidence": 0.5, "details": "low"})}
        }
        result = self.vision.verify_action_result({"type": "url_loaded"}, tolerance=0.8)
        assert result["verified"] is False
        assert result["confidence"] == 0.5

    @patch("src.eyes.vision.vision.ollama")
    def test_not_verified_false_flag(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"verified": False, "confidence": 0.9, "details": "no"})}
        }
        result = self.vision.verify_action_result({"type": "url_loaded"})
        assert result["verified"] is False

    @patch("src.eyes.vision.vision.ollama")
    def test_no_screenshot(self, mock_ollama):
        self.vision.screen_capture.capture_monitor = MagicMock(return_value=None)
        result = self.vision.verify_action_result({"type": "url_loaded"})
        assert result["success"] is False
        assert result["verified"] is False

    @patch("src.eyes.vision.vision.ollama")
    def test_invalid_response(self, mock_ollama):
        mock_ollama.chat.return_value = {"message": {"content": "not json"}}
        result = self.vision.verify_action_result({"type": "url_loaded"})
        assert result["success"] is False
        assert result["verified"] is False


class TestVisionDetectApplicationState:
    def setup_method(self, _method=None):
        self.vision = Vision()
        self.vision.screen_capture = MagicMock()
        self.vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")

    @patch("src.eyes.vision.vision.ollama")
    def test_app_detected(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"detected": True, "state": "active",
                "window_title": "Chrome", "visible_elements": ["tab"], "confidence": 0.9})}
        }
        from src.eyes.capture.screen import ApplicationInfo, ApplicationState
        result = self.vision.detect_application_state("chrome")
        assert result.name == "chrome"
        assert result.state == ApplicationState.ACTIVE
        assert result.window_title == "Chrome"

    @patch("src.eyes.vision.vision.ollama")
    def test_app_detected_open_state(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"detected": True, "state": "open",
                "window_title": None, "visible_elements": [], "confidence": 0.7})}
        }
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.OPEN

    @patch("src.eyes.vision.vision.ollama")
    def test_app_not_detected(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"detected": False, "state": "closed"})}
        }
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision.vision.ollama")
    def test_app_empty_name(self, mock_ollama):
        from src.eyes.capture.screen import ApplicationState, ApplicationInfo
        result = self.vision.detect_application_state("")
        assert result.state == ApplicationState.CLOSED
        assert isinstance(result, ApplicationInfo)

    @patch("src.eyes.vision.vision.ollama")
    def test_app_no_screenshot(self, mock_ollama):
        self.vision.screen_capture.capture_monitor = MagicMock(return_value=None)
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision.vision.ollama")
    def test_app_invalid_state_string(self, mock_ollama):
        """Un state desconocido NO se afirma como OPEN; se usa CLOSED como fallback seguro."""
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"detected": True, "state": "weird_state"})}
        }
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision.vision.ollama")
    def test_app_detected_missing_state_field(self, mock_ollama):
        """Si la vision detecta la app (detected=True) pero no incluye el campo
        'state', no se afirma OPEN por defecto. Se asume CLOSED para evitar
        creencias falsas - hoja 3.4.3.2 'No afirmar un estado solo por configuracion'."""
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"detected": True, "confidence": 0.9})}
        }
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision.vision.ollama")
    def test_app_detected_null_state_field(self, mock_ollama):
        """Si la vision detecta la app pero 'state' es null/None, no se afirma OPEN."""
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"detected": True, "state": None})}
        }
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    @patch("src.eyes.vision.vision.ollama")
    def test_app_exception_returns_closed(self, mock_ollama):
        mock_ollama.chat.side_effect = Exception("fail")
        from src.eyes.capture.screen import ApplicationState
        result = self.vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED


class TestVisionAnalyzeImage:
    def setup_method(self, _method=None):
        self.vision = Vision()

    @patch("src.eyes.vision.vision.ollama")
    def test_analyze_image_returns_json_string(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"elements": [
                {"name": "btn", "type": "button", "bbox": [1, 2, 3, 4], "confidence": 0.9}
            ]})}
        }
        result = self.vision.analyze_image("/fake/image.png", "find buttons")
        assert isinstance(result, str)
        data = json.loads(result)
        assert "elements" in data

    @patch("src.eyes.vision.vision.ollama")
    def test_analyze_image_empty_response(self, mock_ollama):
        mock_ollama.chat.return_value = {"message": {"content": ""}}
        result = self.vision.analyze_image("/fake/image.png", "find buttons")
        assert result == ""

    @patch("src.eyes.vision.vision.ollama")
    def test_analyze_image_with_calibration_target(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({"elements": [
                {"name": "chrome_button", "type": "button", "bbox": [1, 2, 3, 4], "confidence": 0.9},
                {"name": "firefox_link", "type": "link", "bbox": [5, 6, 7, 8], "confidence": 0.8}
            ]})}
        }
        result = self.vision.analyze_image("/fake/image.png", "find buttons", calibration_target="chrome")
        data = json.loads(result)
        assert len(data["elements"]) == 1
        assert "chrome" in data["elements"][0]["name"]

    @patch("src.eyes.vision.vision.ollama")
    def test_analyze_image_exception(self, mock_ollama):
        # analyze_image catches ollama.ResponseError first, then Exception.
        # The mock replaces the whole ollama module, so ResponseError must be
        # a real exception class for the except clause to work.
        import ollama as real_ollama
        mock_ollama.ResponseError = real_ollama.ResponseError
        mock_ollama.chat.side_effect = Exception("fail")
        result = self.vision.analyze_image("/fake/image.png", "prompt")
        assert "ERROR:" in result


class TestVisionAnalyzeScreenForWorldState:
    def setup_method(self, _method=None):
        self.vision = Vision()
        self.vision.screen_capture = MagicMock()
        self.vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        self.vision.memory_manager = MagicMock()
        self.vision.memory_manager.storage.load = MagicMock(return_value={})
        self.vision.memory_manager.get_entities_by_type = MagicMock(return_value=[])
        self.vision.memory_manager.save_world_state = MagicMock()

    @patch("src.eyes.vision.vision.ollama")
    def test_analyze_returns_world_state(self, mock_ollama):
        mock_ollama.chat.return_value = {
            "message": {"content": json_dumps({
                "applications": [{"name": "chrome", "state": "active", "window_title": "Google"}],
                "focused_application": "chrome",
                "visible_text": "Hello",
                "visible_elements": [{"name": "btn", "type": "button", "text": "OK", "interactive": True}]
            })}
        }
        ws = self.vision.analyze_screen_for_world_state()
        assert "chrome" in ws.applications
        assert ws.system_info["focused_application"] == "chrome"

    @patch("src.eyes.vision.vision.ollama")
    def test_analyze_no_screenshot(self, mock_ollama):
        self.vision.screen_capture.capture_monitor = MagicMock(return_value=None)
        ws = self.vision.analyze_screen_for_world_state()
        assert ws.timestamp is not None
        assert len(ws.applications) == 0
