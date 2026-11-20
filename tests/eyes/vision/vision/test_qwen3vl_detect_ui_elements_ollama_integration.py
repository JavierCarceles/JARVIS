# -*- coding: utf-8 -*-
"""Test de integracion real: deteccion de controles con Qwen3-VL sobre una captura grande.

Invoca al servidor y modelo Ollama configurados en el equipo real (sin mocks)
con una imagen sintetica del tamano de un monitor 4K al 225 % (3840x2000) que
contiene tres botones con texto en posiciones conocidas. Comprueba lo que
fallaba en el harness de precision: que ``Vision.detect_ui_elements``
devuelve elementos sin error, que la captura se reduce antes de enviarla al
modelo y que las cajas vuelven a pixeles de la imagen original, de modo que
el centro de cada boton cae dentro del boton dibujado.

La verdad-terreno son las cajas con las que se dibuja la imagen; el modelo no
la recibe. El LLM no es determinista: se reintenta hasta MAX_INTENTOS veces y
todas las comprobaciones deben cumplirse en un mismo intento.

Si Ollama no esta en marcha, la fixture de sesion `ollama_server` lo arranca
y lo cierra al terminar la sesion. Si no esta instalado o falta el modelo, el
test falla con el error real (NO se sustituye por un mock).
"""

import os

import cv2
import numpy as np
import pytest

from src.eyes.vision.vision import DEFAULT_VISION_MODEL, MODEL_IMAGE_MAX_PIXELS, Vision

pytestmark = pytest.mark.usefixtures("ollama_server")

MAX_INTENTOS = 2
ANCHO, ALTO = 3840, 2000

# Botones de la fixture de calibracion (geometria logica x2.25), [x1, y1, x2, y2].
BOTONES = {
    "Aceptar": [45, 45, 270, 117],
    "Cancelar": [292, 45, 517, 117],
    "Abrir popup": [540, 1260, 855, 1332],
}


def _dibujar_boton(img, caja, texto):
    x1, y1, x2, y2 = caja
    cv2.rectangle(img, (x1, y1), (x2, y2), (225, 225, 225), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (120, 120, 120), 3)
    fuente = cv2.FONT_HERSHEY_SIMPLEX
    escala, grosor = 1.4, 3
    (tw, th), _ = cv2.getTextSize(texto, fuente, escala, grosor)
    tx = x1 + max(0, (x2 - x1 - tw) // 2)
    ty = y1 + (y2 - y1 + th) // 2
    cv2.putText(img, texto, (tx, ty), fuente, escala, (20, 20, 20), grosor, cv2.LINE_AA)


@pytest.fixture
def captura_4k(tmp_path):
    """PNG 3840x2000 con tres botones en posiciones conocidas (sin datos de usuario)."""
    img = np.full((ALTO, ANCHO, 3), 245, dtype=np.uint8)
    cv2.putText(img, "Formulario de prueba", (45, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                (40, 40, 40), 3, cv2.LINE_AA)
    for texto, caja in BOTONES.items():
        _dibujar_boton(img, caja, texto)
    ruta = str(tmp_path / "captura_4k.png")
    assert cv2.imwrite(ruta, img)
    return ruta


def _centro_dentro(caja_elemento, caja_boton):
    cx = (caja_elemento[0] + caja_elemento[2]) / 2.0
    cy = (caja_elemento[1] + caja_elemento[3]) / 2.0
    return caja_boton[0] <= cx <= caja_boton[2] and caja_boton[1] <= cy <= caja_boton[3]


def _problemas(resp):
    """Lista de comprobaciones que no cumple una respuesta (vacia si todo es correcto)."""
    problemas = []
    if resp.error is not None:
        problemas.append("error: %s" % resp.error)
    if not resp.elements:
        problemas.append("ningun elemento detectado")
    if resp.image_size != [ANCHO, ALTO]:
        problemas.append("image_size=%s" % resp.image_size)
    tam = resp.model_image_size or [ANCHO, ALTO]
    if tam[0] * tam[1] > MODEL_IMAGE_MAX_PIXELS:
        problemas.append("la captura no se redujo antes de enviarla: %s" % tam)
    for elem in resp.elements:
        x1, y1, x2, y2 = elem.bbox
        if not (0 <= x1 < x2 <= ANCHO and 0 <= y1 < y2 <= ALTO):
            problemas.append("caja fuera de la imagen: %s %s" % (elem.name, elem.bbox))
    for texto, caja in BOTONES.items():
        if not any(_centro_dentro(elem.bbox, caja) for elem in resp.elements):
            problemas.append("ningun centro dentro del boton '%s' %s" % (texto, caja))
    return problemas


def test_qwen3vl_detecta_botones_en_captura_4k_entorno_real(captura_4k):
    """Llamada real: los tres botones se detectan con el centro dentro de su caja."""
    vision = Vision(model=DEFAULT_VISION_MODEL)
    resp = None
    problemas = ["sin ejecutar"]
    for _intento in range(MAX_INTENTOS):
        resp = vision.detect_ui_elements(captura_4k, application="formulario de prueba")
        problemas = _problemas(resp)
        if not problemas:
            break
    detalle = [(e.name, e.bbox) for e in (resp.elements if resp else [])]
    assert not problemas, "%s; elementos=%s; ollama=%s" % (problemas, detalle, vision.last_chat_info)
