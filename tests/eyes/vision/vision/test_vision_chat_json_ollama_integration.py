# -*- coding: utf-8 -*-
"""Test de integracion real: extraccion de respuesta de Ollama en Vision._chat_json.

Invoca al servidor y modelo Ollama configurados en el equipo real (sin mocks)
para verificar que el contenido llega completo al decodificador/validador JSON.

El modelo LLM es no determinista: puede devolver contenido vacio en una
ejecucion. Por eso el test reintenta hasta MAX_INTENTOS veces y pasa si al
menos una respuesta llega completa al decodificador JSON. No se sustituye la
respuesta por un mock ni se declara verificado sin evidencia real.

Si Ollama no esta en marcha, la fixture de sesion `ollama_server` lo arranca
y lo cierra al terminar la sesion. Si no esta instalado o falta el modelo, el
test falla con el error real (NO se sustituye por un mock).
"""

import os
import tempfile

import cv2
import pytest

from src.eyes.vision.vision import DEFAULT_VISION_MODEL, Vision

pytestmark = pytest.mark.usefixtures("ollama_server")

MAX_INTENTOS = 3
# Modelo por defecto de Vision (variante sin razonamiento).
MODELO = DEFAULT_VISION_MODEL


@pytest.fixture
def imagen_temporal():
    """Genera una imagen PNG temporal valida (no contiene datos de usuario)."""
    img = cv2.UMat(200, 300, cv2.CV_8UC3, (255, 255, 255))
    cv2.rectangle(img, (50, 50), (250, 150), (0, 128, 0), -1)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(path, img.get() if hasattr(img, "get") else img)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


def _llama_responde_json(vision, imagen_temporal):
    """Una llamada real a Ollama. Devuelve (salida, datos_decodificados)."""
    prompt = (
        "Responde unicamente un objeto JSON valido con un solo campo "
        '"texto" de tipo string. No anadas texto fuera del JSON.'
    )
    salida = vision._chat_json(image_path=imagen_temporal, prompt=prompt)
    datos = Vision._safe_json_loads(salida)
    return salida, datos


def test_ollama_extrae_contenido_json_completo_entorno_real(imagen_temporal):
    """Llamada real a Ollama: al menos una respuesta llega completa al decodificador JSON."""
    vision = Vision(model=MODELO)
    ultimo_salida = ""
    ultimo_datos = None

    for _intento in range(MAX_INTENTOS):
        salida, datos = _llama_responde_json(vision, imagen_temporal)
        ultimo_salida = salida
        ultimo_datos = datos
        if isinstance(datos, dict) and "texto" in datos:
            break

    # Resultado observable: al menos una respuesta no vacia y decodificable.
    assert ultimo_salida is not None
    assert ultimo_salida.strip() != "", (
        f"Ollama responde vacio en {MAX_INTENTOS} intentos; ultimo contenido: {ultimo_salida!r}"
    )

    # El contenido debe ser JSON decodificable (llega completo al validador).
    assert isinstance(ultimo_datos, dict)
    assert "texto" in ultimo_datos
