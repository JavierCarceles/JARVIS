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

from src.eyes.vision import Vision


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
