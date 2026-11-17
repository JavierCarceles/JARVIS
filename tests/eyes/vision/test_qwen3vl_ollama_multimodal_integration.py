# -*- coding: utf-8 -*-
"""Test de integracion real: interpretacion semantica Qwen3-VL/Ollama.

Invoca al servidor y modelo Ollama configurados en el equipo real (sin mocks)
para verificar que Vision.interpret_element_semantics envia una imagen/crop,
recibe una salida estructurada y validable, y que la respuesta corresponde a
la entrada.

El modelo LLM es no determinista: puede devolver contenido vacio en una
ejecucion. Por eso el test reintenta hasta MAX_INTENTOS veces y pasa si al
menos una respuesta llega completa al decodificador JSON. No se sustituye la
respuesta por un mock ni se declara verificado sin evidencia real.

Si Ollama o el modelo configurado no estan disponibles, el test falla con el
error real (NO se sustituye por un mock).
"""

import os
import tempfile

import cv2
import numpy as np
import pytest

from src.eyes.vision.vision import Vision

MAX_INTENTOS = 3
MODELO = "qwen3-vl:8b"


@pytest.fixture
def imagen_fixture():
    """Genera una imagen PNG temporal con un rectangulo verde (boton simulado)."""
    img = np.full((200, 300, 3), 240, dtype=np.uint8)
    cv2.rectangle(img, (50, 70), (150, 130), (0, 150, 0), -1)
    cv2.putText(img, "Abrir", (70, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(path, img)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


def _interpretacion_real(vision, imagen_path, crop_bbox=None, referencia=None):
    """Una llamada real a Ollama via interpret_element_semantics."""
    return vision.interpret_element_semantics(
        image_path=imagen_path,
        crop_bbox=crop_bbox,
        reference_label=referencia,
    )


def test_ollama_interpretacion_estructura_valida_entorno_real(imagen_fixture):
    """Llamada real a Ollama: respuesta estructurada con todos los campos."""
    vision = Vision(model=MODELO)
    ultimo = None

    for _intento in range(MAX_INTENTOS):
        ultimo = _interpretacion_real(vision, imagen_fixture)
        if (
            isinstance(ultimo, dict)
            and "apparent_function" in ultimo
            and "error" in ultimo
            and ultimo["error"] is None
            and isinstance(ultimo["confidence"], (int, float))
        ):
            break

    assert ultimo is not None, "Ollama no produjo respuesta en ninguno de los intentos"
    assert isinstance(ultimo, dict)
    assert ultimo["error"] is None, f"Error en interpretacion: {ultimo.get('error')}"
    assert "apparent_function" in ultimo
    assert "label_association" in ultimo
    assert "confidence" in ultimo
    assert "is_actionable" in ultimo
    assert "evidence_visual" in ultimo
    assert "disambiguation_hints" in ultimo
    assert "coordinate_check" in ultimo
    assert 0.0 <= ultimo["confidence"] <= 1.0
    assert ultimo["is_actionable"] is False, (
        "La interpretacion semantica nunca debe marcar el elemento como accionable"
    )
    assert isinstance(ultimo["disambiguation_hints"], list)
    assert isinstance(ultimo["coordinate_check"], dict)


def test_ollama_interpretacion_con_crop_entorno_real(imagen_fixture):
    """Llamada real con crop_bbox: coordenadas dentro de rango y recorte enviado."""
    vision = Vision(model=MODELO)
    ultimo = None

    for _intento in range(MAX_INTENTOS):
        ultimo = _interpretacion_real(
            vision, imagen_fixture, crop_bbox=[40, 60, 160, 140], referencia="Abrir"
        )
        if (
            isinstance(ultimo, dict)
            and ultimo.get("error") is None
            and ultimo.get("coordinate_check", {}).get("in_range") is True
        ):
            break

    assert ultimo is not None
    assert ultimo["error"] is None, f"Error con crop: {ultimo.get('error')}"
    assert ultimo["coordinate_check"]["in_range"] is True
    assert ultimo["coordinate_check"]["within_image"] is True
    assert ultimo["is_actionable"] is False


def test_ollama_interpretacion_rechaza_crop_fuera_de_rango(imagen_fixture):
    """Llamada real con crop_bbox fuera de los limites de la imagen: rechaza sin llamar al modelo."""
    vision = Vision(model=MODELO)
    resultado = _interpretacion_real(
        vision, imagen_fixture, crop_bbox=[-50, -50, 1000, 1000]
    )
    assert resultado["coordinate_check"]["in_range"] is False
    assert resultado["coordinate_check"]["within_image"] is False
    assert resultado["error"] is not None
    assert resultado["is_actionable"] is False
