"""
Tests de integracion del adaptador PaddleOCR - unidad 3.8.6.3.3.6.

Pruebas para src/hands/paddleocr_adapter.py.

- Tests unitarios de contrato/logica pura: degradacion graceful cuando
  paddlepaddle/PaddleOCR no estan disponibles, serializacion de
  PaddleOCRRegion, conversion a UIElementData canonico, info de compatibilidad
  y asociacion de etiquetas OCR con candidatos visuales. Sin GUI ni modelos
  descargados silenciosamente.
- Test de integracion real opcional: solo se ejecuta si existe un modelo
  PaddleOCR proporcionado explicitamente en tests/fixtures/ (ruta configurada
  mediante la variable de entorno PADDLEOCR_MODEL_DIR). Nunca se descargan
  pesos automaticamente.
"""

from __future__ import annotations

import os
import unittest
from unittest import skipIf

from src.hands.paddleocr_adapter import (
    PaddleOCRAdapter,
    PaddleOCRRegion,
    DEFAULT_LANG,
)

# Ruta al directorio de modelos proporcionada explicitamente (nunca
# descargada automaticamente).
MODEL_DIR = os.environ.get("PADDLEOCR_MODEL_DIR", "")
PADDLEOCR_DISPONIBLE = bool(MODEL_DIR) and os.path.isdir(MODEL_DIR)


class TestPaddleOCRAdapterContract(unittest.TestCase):
    """Contrato y logica pura del adaptador (sin motor PaddleOCR real)."""

    def test_adapter_sin_modelo_no_disponible(self):
        """Sin model_dir, available es False y error explica el motivo."""
        adapter = PaddleOCRAdapter(model_dir=None)
        self.assertFalse(adapter.available)
        self.assertIsNotNone(adapter.error)

    def test_adapter_modelo_inexistente_no_disponible(self):
        """Con una ruta inexistente, available es False y no se lanza excepcion."""
        adapter = PaddleOCRAdapter(model_dir="no_existe_modelo_dir")
        self.assertFalse(adapter.available)
        self.assertIsNotNone(adapter.error)

    def test_detect_sin_motor_devuelve_lista_vacia(self):
        """detect() con adaptador no disponible devuelve [] y no falla."""
        adapter = PaddleOCRAdapter(model_dir=None)
        resultado = adapter.detect("cualquier_imagen.png", screen=0)
        self.assertEqual(resultado, [])

    def test_region_serializable(self):
        """PaddleOCRRegion.to_dict devuelve un diccionario plano serializable."""
        region = PaddleOCRRegion(
            text="Aceptar",
            bbox=[100, 200, 220, 250],
            polygon=[[100, 200], [220, 200], [220, 250], [100, 250]],
            confidence=0.87,
            source="paddleocr",
            model="paddleocr",
            device="cpu",
            screen=1,
            language="en",
        )
        d = region.to_dict()
        self.assertEqual(d["text"], "Aceptar")
        self.assertEqual(d["bbox"], [100, 200, 220, 250])
        self.assertEqual(d["polygon"], [[100, 200], [220, 200], [220, 250], [100, 250]])
        self.assertAlmostEqual(d["confidence"], 0.87)
        self.assertEqual(d["source"], "paddleocr")
        self.assertEqual(d["model"], "paddleocr")
        self.assertEqual(d["device"], "cpu")
        self.assertEqual(d["screen"], 1)
        self.assertEqual(d["language"], "en")

    def test_region_a_ui_element_data(self):
        """to_ui_element_data() convierte la region en un UIElementData canonico."""
        region = PaddleOCRRegion(
            text="Campo de texto",
            bbox=[0, 0, 100, 40],
            confidence=0.9,
            screen=2,
        )
        ued = region.to_ui_element_data()
        self.assertEqual(ued.name, "Campo de texto")
        self.assertEqual(ued.type, "text")
        self.assertEqual(ued.text, "Campo de texto")
        self.assertEqual(ued.bbox, [0, 0, 100, 40])
        self.assertEqual(ued.center, [50, 20])
        self.assertEqual(ued.screen, 2)
        self.assertAlmostEqual(ued.confidence, 0.9)
        self.assertFalse(ued.interactive)  # una region OCR no implica boton
        self.assertFalse(ued.calibrated)
        self.assertEqual(ued.calibration_data["source"], "paddleocr")
        self.assertEqual(ued.calibration_data["model"], "paddleocr")

    def test_default_lang(self):
        """DEFAULT_LANG tiene un valor sensato."""
        self.assertIsInstance(DEFAULT_LANG, str)
        self.assertGreater(len(DEFAULT_LANG), 0)

    def test_compatibilidad_tiene_campos_esperados(self):
        """compatibility_info() expone datos de compatibilidad sin ejecutar el SO."""
        adapter = PaddleOCRAdapter(model_dir=None)
        info = adapter.compatibility_info()
        for clave in ("source", "model", "device_requested", "device_effective",
                      "available", "error", "lang", "text_score_thresh",
                      "box_thresh", "unclip_ratio", "det_limit_side_len",
                      "use_gpu", "show_log", "model_dir"):
            self.assertIn(clave, info)
        self.assertEqual(info["source"], "paddleocr")
        self.assertEqual(info["model"], "paddleocr")
        self.assertFalse(info["available"])

    def test_associar_etiqueta_por_contenimiento(self):
        """Una region OCR dentro de un candidato se asocia mediante contencion."""
        regiones = [
            PaddleOCRRegion(text="Aceptar", bbox=[110, 210, 210, 240], confidence=0.9, screen=0),
        ]
        candidatos = [
            {"name": "btn_aceptar", "bbox": [100, 200, 230, 260], "type": "button"},
        ]
        resultado = PaddleOCRAdapter.associate_with_candidates(regiones, candidatos)
        self.assertEqual(len(resultado), 1)
        self.assertIn("ocr", resultado[0])
        self.assertEqual(resultado[0]["ocr"]["text"], "Aceptar")
        self.assertAlmostEqual(resultado[0]["ocr"]["confidence"], 0.9)

    def test_associar_no_convierte_texto_en_boton(self):
        """La asociacion solo adjunta texto; no cambia el tipo ni marca interactivo."""
        regiones = [
            PaddleOCRRegion(text="Etiqueta estatica", bbox=[300, 100, 420, 130], confidence=0.8, screen=0),
        ]
        candidatos = [
            {"name": "lbl_estatico", "bbox": [290, 90, 430, 140], "type": "text"},
        ]
        resultado = PaddleOCRAdapter.associate_with_candidates(regiones, candidatos)
        self.assertEqual(resultado[0]["type"], "text")
        self.assertIn("ocr", resultado[0])
        self.assertEqual(resultado[0]["ocr"]["text"], "Etiqueta estatica")

    def test_associar_sin_solapamiento_no_asigna(self):
        """Una region OCR lejos de un candidato no se asocia."""
        regiones = [
            PaddleOCRRegion(text="Texto lejano", bbox=[900, 900, 980, 930], confidence=0.9, screen=0),
        ]
        candidatos = [
            {"name": "btn_cerca", "bbox": [100, 200, 230, 260], "type": "button"},
        ]
        resultado = PaddleOCRAdapter.associate_with_candidates(regiones, candidatos)
        self.assertNotIn("ocr", resultado[0])


@skipIf(not PADDLEOCR_DISPONIBLE,
        "Directorio de modelos PaddleOCR no proporcionado (PADDLEOCR_MODEL_DIR). "
        "Prueba de integracion real omitida.")
class TestPaddleOCRAdapterIntegracionReal(unittest.TestCase):
    """Integracion real con el motor PaddleOCR.

    Solo se ejecuta si el usuario proporciona explicitamente la ruta al
    directorio de modelos mediante PADDLEOCR_MODEL_DIR. Nunca se descargan
    pesos automaticamente.
    """

    def setUp(self):
        self.adapter = PaddleOCRAdapter(model_dir=MODEL_DIR, device="cpu")
        self.assertTrue(self.adapter.available, self.adapter.error)

    def test_cargar_motor_real(self):
        """El motor PaddleOCR carga y reporta tiempo de carga."""
        self.assertIsNotNone(self.adapter.load_time_seconds)
        self.assertGreater(self.adapter.load_time_seconds, 0)
        self.assertIsNone(self.adapter.error)

    def test_detect_sobre_imagen_fixture(self):
        """detect() sobre una imagen de prueba devuelve regiones con texto y bbox."""
        from PIL import Image
        import tempfile
        img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        img.save(tmp.name)
        try:
            regiones = self.adapter.detect(tmp.name, screen=0)
            self.assertIsInstance(regiones, list)
            for r in regiones:
                self.assertEqual(len(r.bbox), 4)
                self.assertGreaterEqual(r.confidence, 0.0)
                self.assertLessEqual(r.confidence, 1.0)
                self.assertEqual(r.source, "paddleocr")
        finally:
            import os as _os
            _os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
