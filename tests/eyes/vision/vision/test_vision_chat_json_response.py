# -*- coding: utf-8 -*-
"""Tests unitarios de extraccion de respuesta de Ollama en Vision._chat_json.

Valida el objeto/estructura real de respuesta de la version instalada del
paquete `ollama` (0.6.2): ollama.chat(stream=False) devuelve un
`ollama._types.ChatResponse` (no un dict). La extraccion debe manejar tanto
el objeto real como un dict legacy sin descartar respuestas validas ni
devolver vacio silenciosamente.

Los mocks aislan la frontera externa (ollama.chat) pero devuelven la
estructura real de respuesta; nunca deciden el resultado que se pretende
demostrar.
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


class TestChatJsonResponseStructure:
    """La version instalada de ollama devuelve ChatResponse, no dict."""

    def test_installed_ollama_returns_chat_response_not_dict(self):
        """Evidencia estructural: respuesta real no es dict, tiene atributo message."""
        resp = _make_chat_response("{}")
        assert not isinstance(resp, dict)
        assert hasattr(resp, "message")
        assert hasattr(resp.message, "content")
        assert resp.message.content == "{}"

    def test_chat_json_extrae_contenido_valido_de_chatresponse(self):
        """Extraccion real del contenido de un ChatResponse valido."""
        vision = _vision()
        resp = _make_chat_response('{"detected": true, "confidence": 0.9}')
        with patch.object(ollama, "chat", return_value=resp):
            salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == '{"detected": true, "confidence": 0.9}'

    def test_chat_json_extrae_contenido_de_dict_legacy(self):
        """Retrocompatibilidad: si una version devolviera dict, aun funciona."""
        vision = _vision()
        resp = {"message": {"content": '{"ok": true}'}}
        with patch.object(ollama, "chat", return_value=resp):
            salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == '{"ok": true}'

    def test_chat_json_contenido_vacio_no_lanza_excepcion(self):
        """Respuesta vacia: no lanza, devuelve cadena vacia (el llamador la rechaza)."""
        vision = _vision()
        resp = _make_chat_response(None)
        with patch.object(ollama, "chat", return_value=resp):
            salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == ""

    def test_chat_json_contenido_none_no_lanza_excepcion(self):
        """Content None: manejado sin caer en AttributeError."""
        vision = _vision()
        resp = _make_chat_response(None)
        with patch.object(ollama, "chat", return_value=resp):
            salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == ""

    def test_chat_json_mensaje_sin_content_devuelve_vacio(self):
        """Message sin atributo content: no explota, devuelve vacio."""
        vision = _vision()
        resp = ChatResponse(model="qwen3-vl:8b", message=Message(role="assistant", content=None, done=True))
        with patch.object(ollama, "chat", return_value=resp):
            salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == ""

    def test_chat_json_registra_razonamiento_y_salida_cortada(self, caplog):
        """Modelo con razonamiento que agota num_predict: content vacio, aviso y diagnostico."""
        vision = _vision()
        resp = ChatResponse(
            model="qwen3-vl:8b",
            done_reason="length",
            message=Message(role="assistant", content="", thinking="Primero miro la imagen. " * 40),
        )
        with patch.object(ollama, "chat", return_value=resp):
            with caplog.at_level("WARNING"):
                salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == ""
        info = vision.last_chat_info
        assert info["done_reason"] == "length"
        assert info["thinking_chars"] > 0
        assert info["content_chars"] == 0
        avisos = " ".join(r.getMessage() for r in caplog.records)
        assert "razonamiento" in avisos
        assert "num_predict" in avisos

    def test_chat_json_respuesta_completa_sin_avisos(self, caplog):
        """Respuesta normal (done_reason=stop): sin avisos y con el diagnostico relleno."""
        vision = _vision()
        resp = ChatResponse(
            model="qwen3-vl:8b-instruct",
            done_reason="stop",
            message=Message(role="assistant", content='{"elements": []}'),
        )
        with patch.object(ollama, "chat", return_value=resp):
            with caplog.at_level("WARNING"):
                salida = vision._chat_json(image_path="imagen.png", prompt="analiza")
        assert salida == '{"elements": []}'
        assert vision.last_chat_info["done_reason"] == "stop"
        assert vision.last_chat_info["content_chars"] == len(salida)
        assert not [r for r in caplog.records if r.levelname == "WARNING"]
