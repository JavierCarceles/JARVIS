# -*- coding: ascii -*-
"""
Llamada a Qwen3-VL desde el pipeline de calibracion.

- Respuesta cortada por `num_predict`: se conservan los elementos completos.
- La imagen enviada se reduce (lado mayor acotado) y se borra despues; las
  cajas normalizadas 0..1000 se convierten con el tamano de la captura ORIGINAL.
- Espera maxima: se pasa a la vision si la admite; si no, se llama sin ella.
- `Vision.analyze_image` usa un cliente de Ollama con espera maxima y un
  presupuesto de salida suficiente para la lista de elementos.

Multiplataforma: la vision y Ollama se sustituyen por dobles en la frontera.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from src.hands.calibration.calibration_pipeline import CalibrationReport, UICalibrationPipeline
from src.hands.calibration.universal_visual_calibrator import UniversalVisualCalibrator


def _elemento(nombre, caja):
    return {"name": nombre, "type": "button", "text": nombre, "description": "",
            "bbox": caja, "confidence": 0.9, "interactive": True}


class TestRespuestaCortada(unittest.TestCase):
    def test_json_completo_sin_cambios(self):
        texto = json.dumps({"elements": [_elemento("uno", [0, 0, 10, 10])]})
        parsed = UniversalVisualCalibrator._parse_response(texto)
        self.assertEqual(len(parsed["elements"]), 1)
        self.assertNotIn("truncated", parsed)

    def test_json_cortado_conserva_los_elementos_completos(self):
        completo = json.dumps({"elements": [
            _elemento("uno", [0, 0, 10, 10]), _elemento("dos", [20, 20, 30, 30]), _elemento("tres", [40, 40, 50, 50]),
        ]})
        cortado = completo[: completo.index('"tres"') + 3]
        parsed = UniversalVisualCalibrator._parse_response(cortado)
        self.assertTrue(parsed["truncated"])
        self.assertEqual([e["name"] for e in parsed["elements"]], ["uno", "dos"])

    def test_texto_sin_elements_sigue_siendo_no_interpretable(self):
        self.assertIsNone(UniversalVisualCalibrator._parse_response('{"otra": [1, 2'))


class _VisionSinEspera:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.rutas = []

    def analyze_image(self, image_path, prompt):
        self.rutas.append(image_path)
        with Image.open(image_path) as imagen:
            self.tamano = imagen.size
        return self.respuesta


class _VisionConEspera(_VisionSinEspera):
    def analyze_image(self, image_path, prompt, timeout=None, num_predict=None):
        self.timeout = timeout
        self.num_predict = num_predict
        self.prompt = prompt
        return super().analyze_image(image_path, prompt)


class TestLlamadaDesdeElPipeline(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self._tmp.name, "captura.png")
        Image.new("RGB", (3200, 1800), "white").save(self.ruta)
        self.captura = SimpleNamespace(pixel_width=3200, pixel_height=1800)
        self.ventana = SimpleNamespace(window_id=7, pid=70)

    def tearDown(self):
        self._tmp.cleanup()

    def _pipeline(self, vision):
        calibrador = UniversalVisualCalibrator()
        calibrador.vision = vision
        return UICalibrationPipeline(vision=calibrador, vision_timeout=42.0, vision_max_side=1600)

    def _respuesta(self):
        return json.dumps({"elements": [_elemento("aceptar", [500, 500, 600, 600])]})

    def test_imagen_reducida_borrada_y_cajas_en_pixeles_originales(self):
        vision = _VisionConEspera(self._respuesta())
        report = CalibrationReport(app_id="x", app_name="x")
        candidatos = self._pipeline(vision)._qwen_candidates("x", self.captura, self.ruta, self.ventana, report)
        self.assertEqual(vision.tamano, (1600, 900))
        self.assertNotEqual(vision.rutas[0], self.ruta)
        self.assertFalse(os.path.exists(vision.rutas[0]), "la copia reducida debe borrarse")
        self.assertTrue(os.path.exists(self.ruta), "la captura original no se toca")
        self.assertEqual(vision.timeout, 42.0)
        self.assertIn("40 elementos", vision.prompt)
        self.assertGreaterEqual(vision.num_predict, 60 * 40)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0].bbox, [1600, 900, 1920, 1080])
        self.assertEqual(report.metrics["qwen3vl"]["sent_size"], [1600, 900])

    def test_vision_sin_parametro_de_espera(self):
        vision = _VisionSinEspera(self._respuesta())
        report = CalibrationReport(app_id="x", app_name="x")
        candidatos = self._pipeline(vision)._qwen_candidates("x", self.captura, self.ruta, self.ventana, report)
        self.assertEqual(len(candidatos), 1)

    def test_error_de_ollama_es_aviso_y_no_respuesta_ilegible(self):
        vision = _VisionConEspera("ERROR: timed out")
        report = CalibrationReport(app_id="x", app_name="x")
        candidatos = self._pipeline(vision)._qwen_candidates("x", self.captura, self.ruta, self.ventana, report)
        self.assertEqual(candidatos, [])
        self.assertTrue(any("timed out" in w for w in report.warnings), report.warnings)

    def test_imagen_pequena_se_envia_tal_cual(self):
        pequena = os.path.join(self._tmp.name, "pequena.png")
        Image.new("RGB", (800, 600), "white").save(pequena)
        vision = _VisionConEspera(self._respuesta())
        report = CalibrationReport(app_id="x", app_name="x")
        captura = SimpleNamespace(pixel_width=800, pixel_height=600)
        self._pipeline(vision)._qwen_candidates("x", captura, pequena, self.ventana, report)
        self.assertEqual(vision.rutas[0], pequena)
        self.assertTrue(os.path.exists(pequena))


class _Flujo:
    """Iterador de trozos de Ollama que registra si se cerro la conexion."""

    def __init__(self, trozos, reloj=None, avance=0.0):
        self._trozos = list(trozos)
        self.cerrado = False
        self._reloj = reloj
        self._avance = avance

    def __iter__(self):
        for trozo in self._trozos:
            if self._reloj is not None:
                self._reloj[0] += self._avance
            yield {"message": {"content": trozo}}

    def close(self):
        self.cerrado = True


class TestVisionOllama(unittest.TestCase):
    def test_cliente_con_espera_y_presupuesto_de_salida(self):
        from src.eyes.vision import vision_only

        flujo = _Flujo(['{"elements": ', "[]}"])
        cliente = mock.MagicMock()
        cliente.chat.return_value = flujo
        with mock.patch.object(vision_only.ollama, "Client", return_value=cliente) as fabrica:
            texto = vision_only.Vision(model="m").analyze_image("img.png", "p", timeout=30.0)
        fabrica.assert_called_once_with(timeout=30.0)
        argumentos = cliente.chat.call_args.kwargs
        self.assertTrue(argumentos["stream"])
        self.assertGreaterEqual(argumentos["options"]["num_predict"], 4096)
        self.assertEqual(texto, '{"elements": []}')
        self.assertTrue(flujo.cerrado)

    def test_tiempo_agotado_devuelve_lo_recibido_y_corta(self):
        from src.eyes.vision import vision_only

        reloj = [0.0]
        trozos = ['{"elements": [', '{"name": "a", "bbox": [1, 1, 2, 2]}', ', {"name": "b", "bb', 'ox": [3, 3, 4, 4]}]}']
        flujo = _Flujo(trozos, reloj=reloj, avance=4.0)
        cliente = mock.MagicMock()
        cliente.chat.return_value = flujo
        with mock.patch.object(vision_only.ollama, "Client", return_value=cliente), \
                mock.patch.object(vision_only.time, "monotonic", side_effect=lambda: reloj[0]):
            texto = vision_only.Vision(model="m").analyze_image("img.png", "p", timeout=10.0)
        self.assertTrue(flujo.cerrado, "debe cortarse la conexion para que Ollama deje de generar")
        parsed = UniversalVisualCalibrator._parse_response(texto)
        self.assertEqual([e["name"] for e in parsed["elements"]], ["a"])

    def test_sin_espera_llamada_unica_como_antes(self):
        from src.eyes.vision import vision_only

        with mock.patch.object(vision_only.ollama, "chat", return_value={"message": {"content": "{}"}}) as chat:
            vision_only.Vision(model="m").analyze_image("img.png", "p")
        self.assertFalse(chat.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()


class TestVisionDeLaCalibracion(unittest.TestCase):
    """`src.eyes.vision.vision.Vision`: la que usa UniversalVisualCalibrator."""

    def _vision(self):
        from src.eyes.vision import vision as modulo

        instancia = modulo.Vision.__new__(modulo.Vision)
        instancia.model = "qwen3-vl:8b-instruct"
        instancia.temperature = 0.0
        instancia.max_image_pixels = modulo.MODEL_IMAGE_MAX_PIXELS
        instancia.detection_max_elements = modulo.DETECTION_MAX_ELEMENTS
        instancia.last_chat_info = {}
        return modulo, instancia

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self._tmp.name, "captura.png")
        Image.new("RGB", (640, 360), "white").save(self.ruta)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sin_timeout_llamada_unica_como_antes(self):
        modulo, vision = self._vision()
        with mock.patch.object(modulo.ollama, "chat",
                               return_value={"message": {"content": '{"elements": []}'}}) as chat:
            texto = vision.analyze_image(self.ruta, "p")
        self.assertFalse(chat.call_args.kwargs["stream"])
        self.assertEqual(texto, '{"elements": []}')

    def test_con_timeout_streaming_corte_y_respuesta_parcial(self):
        modulo, vision = self._vision()
        reloj = [0.0]
        trozos = ['{"elements": [', '{"name": "a", "type": "button", "bbox": [1, 1, 2, 2], "confidence": 0.9}',
                  ', {"name": "b", "ty', 'pe": "button"}]}']
        flujo = _Flujo(trozos, reloj=reloj, avance=4.0)
        cliente = mock.MagicMock()
        cliente.chat.return_value = flujo
        with mock.patch.object(modulo.ollama, "Client", return_value=cliente) as fabrica, \
                mock.patch.object(modulo.time, "monotonic", side_effect=lambda: reloj[0]):
            texto = vision.analyze_image(self.ruta, "p", timeout=10.0, num_predict=2800)
        fabrica.assert_called_once_with(timeout=10.0)
        argumentos = cliente.chat.call_args.kwargs
        self.assertTrue(argumentos["stream"])
        self.assertEqual(argumentos["options"]["num_predict"], 2800)
        self.assertTrue(flujo.cerrado)
        self.assertEqual(vision.last_chat_info["done_reason"], "timeout")
        parsed = UniversalVisualCalibrator._parse_response(texto)
        self.assertEqual([e["name"] for e in parsed["elements"]], ["a"])

    def test_el_pipeline_pasa_espera_y_limite_a_la_vision_real(self):
        modulo, vision = self._vision()
        calibrador = UniversalVisualCalibrator()
        calibrador.vision = vision
        pipeline = UICalibrationPipeline(vision=calibrador, vision_timeout=33.0, vision_max_elements=40)
        with mock.patch.object(vision, "_chat_json", return_value='{"elements": []}') as chat_json:
            pipeline._qwen_candidates("x", SimpleNamespace(pixel_width=640, pixel_height=360), self.ruta,
                                      SimpleNamespace(window_id=1, pid=2),
                                      CalibrationReport(app_id="x", app_name="x"))
        argumentos = chat_json.call_args.kwargs
        self.assertEqual(argumentos["timeout"], 33.0)
        self.assertEqual(argumentos["num_predict"], 60 * 40 + 400)
        self.assertIn("40 elementos", argumentos["prompt"])
