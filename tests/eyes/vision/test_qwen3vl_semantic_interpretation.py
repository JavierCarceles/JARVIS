# -*- coding: utf-8 -*-
"""Tests unitarios de interpretacion semantica Qwen3-VL/Ollama (Vision.interpret_element_semantics).

Valida el contrato de entrada/salida, la asociacion con la imagen/crop, la
validacion del esquema, el rechazo de coordenadas/cajas invalidas y la gestion
de respuestas incompletas.

Los mocks aislan la frontera externa (ollama.chat) pero devuelven la
estructura real de respuesta; nunca deciden el resultado que se pretende
demostrar. La interpretacion semantica nunca decide accionabilidad:
is_actionable siempre es False.
"""

from unittest.mock import patch

import ollama
from ollama._types import ChatResponse, Message

import pytest

from src.eyes.vision.vision import Vision


def _make_chat_response(content):
    return ChatResponse(
        model="qwen3-vl:8b",
        message=Message(role="assistant", content=content, done=True),
    )


def _vision():
    return Vision(model="qwen3-vl:8b")


class TestSemanticInterpretationContract:
    """Contrato de entrada/salida de interpretacion semantica."""

    def test_retorna_dict_con_todos_los_campos_requeridos(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton para abrir archivo", '
            '"label_association": "Abrir", '
            '"confidence": 0.85, '
            '"disambiguation_hints": ["icono de carpeta", "texto Acciones"]}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(
                image_path="imagen.png",
                reference_label="Abrir",
            )
        assert isinstance(resultado, dict)
        assert "apparent_function" in resultado
        assert "label_association" in resultado
        assert "confidence" in resultado
        assert "is_actionable" in resultado
        assert "evidence_visual" in resultado
        assert "disambiguation_hints" in resultado
        assert "coordinate_check" in resultado
        assert "error" in resultado

    def test_is_actionable_siempre_false(self):
        """La interpretacion semantica nunca decide accionabilidad."""
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton de envio", '
            '"label_association": "Enviar", '
            '"confidence": 0.9, '
            '"disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["is_actionable"] is False

    def test_confidence_rango_0_a_1(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "campo de texto", '
            '"label_association": "Nombre", '
            '"confidence": 0.5, '
            '"disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert 0.0 <= resultado["confidence"] <= 1.0

    def test_evidence_visual_verdadero_con_contenido(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "icono de lupa", '
            '"label_association": "Buscar", '
            '"confidence": 0.8, '
            '"disambiguation_hints": ["lupa al lado del campo"]}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["evidence_visual"] is True

    def test_evidence_visual_falso_sin_contenido(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "", '
            '"label_association": "", '
            '"confidence": 0.0, '
            '"disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["evidence_visual"] is False


class TestSemanticInterpretacionConCrop:
    """Asociacion con imagen y recorte (crop_bbox)."""

    def test_con_crop_bbox_valido_usa_recorte(self, tmp_path):
        vision = _vision()
        import cv2
        import numpy as np

        # Crear imagen fixture
        img = np.full((200, 300, 3), 255, dtype=np.uint8)
        img_path = str(tmp_path / "fixture.png")
        cv2.imwrite(img_path, img)

        resp = _make_chat_response(
            '{"apparent_function": "region recortada", '
            '"label_association": "", '
            '"confidence": 0.7, '
            '"disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp) as mock_chat:
            resultado = vision.interpret_element_semantics(
                image_path=img_path,
                crop_bbox=[10, 10, 100, 100],
            )
        # Ollama recibio una ruta (posiblemente temporal del recorte) dentro de messages[0]["images"]
        assert mock_chat.call_count == 1
        call_kwargs = mock_chat.call_args.kwargs
        mensajes = call_kwargs["messages"]
        assert isinstance(mensajes, list) and len(mensajes) == 1
        assert "images" in mensajes[0]
        assert isinstance(mensajes[0]["images"], list)
        assert len(mensajes[0]["images"]) == 1
        assert resultado["coordinate_check"]["in_range"] is True
        assert resultado["coordinate_check"]["within_image"] is True

    def test_crop_bbox_longitud_incorrecta(self):
        vision = _vision()
        resultado = vision.interpret_element_semantics(
            image_path="imagen.png",
            crop_bbox=[10, 10, 100],
        )
        assert resultado["coordinate_check"]["in_range"] is False
        assert resultado["coordinate_check"]["within_image"] is False
        assert resultado["error"] is not None
        assert resultado["is_actionable"] is False

    def test_crop_bbox_valores_no_numericos(self):
        vision = _vision()
        resultado = vision.interpret_element_semantics(
            image_path="imagen.png",
            crop_bbox=["a", "b", "c", "d"],
        )
        assert resultado["coordinate_check"]["in_range"] is False
        assert resultado["error"] is not None

    def test_crop_bbox_coordenadas_invertidas(self):
        vision = _vision()
        resultado = vision.interpret_element_semantics(
            image_path="imagen.png",
            crop_bbox=[100, 100, 10, 10],
        )
        assert resultado["coordinate_check"]["in_range"] is False
        assert resultado["error"] is not None

    def test_crop_bbox_fuera_de_rango_negativo(self):
        vision = _vision()
        resultado = vision.interpret_element_semantics(
            image_path="imagen.png",
            crop_bbox=[-10, -10, 100, 100],
        )
        assert resultado["coordinate_check"]["in_range"] is False
        assert resultado["coordinate_check"]["within_image"] is False
        assert resultado["error"] is not None


class TestSemanticInterpretacionRespuestaIncompleta:
    """Gestion de respuestas incompletas o malformadas."""

    def test_respuesta_no_dict_devuelve_campos_vacios(self):
        vision = _vision()
        resp = _make_chat_response("no es json")
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["apparent_function"] == ""
        assert resultado["label_association"] == ""
        assert resultado["confidence"] == 0.0
        assert resultado["is_actionable"] is False
        assert resultado["error"] is not None

    def test_respuesta_vacia_devuelve_campos_vacios(self):
        vision = _vision()
        resp = _make_chat_response("")
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["apparent_function"] == ""
        assert resultado["error"] is not None

    def test_respuesta_faltan_campos_opcionales(self):
        """Respuesta con solo campos requeridos, sin disambiguation_hints."""
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton", "label_association": "", "confidence": 0.6}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["apparent_function"] == "boton"
        assert resultado["confidence"] == 0.6
        assert resultado["disambiguation_hints"] == []

    def test_sin_crop_bbox_envia_imagen_original(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton", "label_association": "", "confidence": 0.5, "disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp) as mock_chat:
            vision.interpret_element_semantics(image_path="imagen_original.png")
        call_kwargs = mock_chat.call_args.kwargs
        mensajes = call_kwargs["messages"]
        assert isinstance(mensajes, list) and len(mensajes) == 1
        assert mensajes[0]["images"] == ["imagen_original.png"]

    def test_con_reference_label_incluida_en_prompt(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton", "label_association": "Guardar", "confidence": 0.9, "disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp) as mock_chat:
            vision.interpret_element_semantics(
                image_path="imagen.png",
                reference_label="Guardar",
            )
        call_kwargs = mock_chat.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]
        assert "Guardar" in prompt
        assert "Referencia de etiqueta" in prompt


class TestSemanticInterpretacionEstructuraSalida:
    """Validacion de la salida estructurada."""

    def test_disambiguation_hints_es_lista_de_cadenas(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton", "label_association": "Abrir", "confidence": 0.8, "disambiguation_hints": ["pista1", "pista2"]}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert isinstance(resultado["disambiguation_hints"], list)
        assert all(isinstance(h, str) for h in resultado["disambiguation_hints"])

    def test_coordinate_check_sin_crop_es_valido(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton", "label_association": "", "confidence": 0.5, "disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["coordinate_check"]["in_range"] is True
        assert resultado["coordinate_check"]["within_image"] is True

    def test_error_none_cuando_es_exitoso(self):
        vision = _vision()
        resp = _make_chat_response(
            '{"apparent_function": "boton", "label_association": "Abrir", "confidence": 0.8, "disambiguation_hints": []}'
        )
        with patch.object(ollama, "chat", return_value=resp):
            resultado = vision.interpret_element_semantics(image_path="imagen.png")
        assert resultado["error"] is None
