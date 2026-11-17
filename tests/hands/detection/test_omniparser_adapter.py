"""
Tests de integracion del adaptador OmniParser V2 (icon_detect_v3) - unidad 3.8.6.3.3.5.

Pruebas para src/hands/detection/omniparser_adapter.py.

- Tests unitarios de contrato/logica: degradacion graceful cuando el modelo no
  esta disponible, serializacion de OmniParserRegion, conversion a UIElementData
  canonico, y info de compatibilidad. Sin GUI ni modelos descargados silenciosamente.
- Test de integracion real opcional: solo se ejecuta si existe un modelo
  icon_detect_v3/model.pt proporcionado explicitamente en tests/fixtures/
  (ruta configurada mediante la variable de entorno OMNIPARSER_MODEL_PATH).
  Nunca se descargan pesos automaticamente.
"""

from __future__ import annotations

import os
import unittest
from unittest import skipIf

from src.hands.detection.omniparser_adapter import (
    OmniParserAdapter,
    OmniParserRegion,
)


# Ruta al modelo proporcionada explicitamente (nunca descargada automaticamente).
MODEL_PATH_ENV = os.environ.get("OMNIPARSER_MODEL_PATH", "")

# Busca automaticamente el modelo icon_detect_v3/model.pt en la cache de
# HuggingFace cuando no se proporciona explicitamente, para que los tests de
# integracion real no queden skippeados si el modelo esta instalado.
_MODELO_OMNIPARSER_AUTODETECTADO = None
if not MODEL_PATH_ENV:
    _hf_cache = os.path.expanduser(
        r"~\.cache\huggingface\hub\models--microsoft--OmniParser-v2.0"
    )
    if os.path.isdir(_hf_cache):
        for _raiz, _dirs, _archivos in os.walk(_hf_cache):
            for _nombre in _archivos:
                if _nombre == "model.pt" and "icon_detect_v3" in _raiz:
                    _MODELO_OMNIPARSER_AUTODETECTADO = os.path.join(
                        _raiz, _nombre
                    )
                    break
            if _MODELO_OMNIPARSER_AUTODETECTADO:
                break

MODEL_PATH = MODEL_PATH_ENV or _MODELO_OMNIPARSER_AUTODETECTADO or ""
MODEL_DISPONIBLE = bool(MODEL_PATH) and os.path.exists(MODEL_PATH)


class TestOmniParserAdapterContract(unittest.TestCase):
    """Contrato y logica pura del adaptador (sin modelo ni GUI)."""

    def test_adapter_sin_modelo_no_disponible(self):
        """Sin model_path, available es False y error explica el motivo."""
        adapter = OmniParserAdapter(model_path=None)
        self.assertFalse(adapter.available)
        self.assertIsNotNone(adapter.error)
        self.assertIn("model_path", adapter.error)

    def test_adapter_modelo_inexistente_no_disponible(self):
        """Con una ruta inexistente, available es False y no se lanza excepcion."""
        adapter = OmniParserAdapter(model_path="no_existe_modelo.pt")
        self.assertFalse(adapter.available)
        self.assertIsNotNone(adapter.error)

    def test_detect_sin_modelo_devuelve_lista_vacia(self):
        """detect() con adaptador no disponible devuelve [] y no falla."""
        adapter = OmniParserAdapter(model_path=None)
        resultado = adapter.detect("cualquier_imagen.png", screen=0)
        self.assertEqual(resultado, [])

    def test_region_serializable(self):
        """OmniParserRegion.to_dict devuelve un diccionario plano serializable."""
        region = OmniParserRegion(
            name="btn_aceptar",
            bbox=[100, 200, 220, 250],
            confidence=0.87,
            source="omniparser_v2_icon_detect_v3",
            model="icon_detect_v3",
            device="cpu",
            screen=1,
            interactive=True,
            calibrated=False,
        )
        d = region.to_dict()
        self.assertEqual(d["name"], "btn_aceptar")
        self.assertEqual(d["bbox"], [100, 200, 220, 250])
        self.assertAlmostEqual(d["confidence"], 0.87)
        self.assertEqual(d["source"], "omniparser_v2_icon_detect_v3")
        self.assertEqual(d["model"], "icon_detect_v3")
        self.assertEqual(d["device"], "cpu")
        self.assertEqual(d["screen"], 1)
        self.assertTrue(d["interactive"])
        self.assertFalse(d["calibrated"])

    def test_region_a_ui_element_data(self):
        """to_ui_element_data() convierte la region en un UIElementData canonico."""
        region = OmniParserRegion(
            name="campo_texto",
            bbox=[0, 0, 100, 40],
            confidence=0.9,
            screen=2,
        )
        ued = region.to_ui_element_data()
        self.assertEqual(ued.name, "campo_texto")
        self.assertEqual(ued.type, "element")
        self.assertEqual(ued.bbox, [0, 0, 100, 40])
        self.assertEqual(ued.center, [50, 20])
        self.assertEqual(ued.screen, 2)
        self.assertAlmostEqual(ued.confidence, 0.9)
        self.assertFalse(ued.calibrated)
        self.assertEqual(ued.calibration_data["source"],
                         "omniparser_v2_icon_detect_v3")
        self.assertEqual(ued.calibration_data["model"], "icon_detect_v3")

    def test_compatibilidad_tiene_campos_esperados(self):
        """compatibility_info() expone datos de compatibilidad sin ejecutar el SO."""
        adapter = OmniParserAdapter(model_path=None)
        info = adapter.compatibility_info()
        for clave in ("source", "model", "repo_id", "model_file", "license",
                      "device_requested", "device_effective", "cuda_available",
                      "available", "error", "conf_threshold", "iou_threshold",
                      "max_detections", "img_size"):
            self.assertIn(clave, info)
        self.assertEqual(info["source"], "omniparser_v2_icon_detect_v3")
        self.assertEqual(info["model"], "icon_detect_v3")
        self.assertEqual(info["license"], "MIT")


class TestOmniParserAdapterIntegracionReal(unittest.TestCase):
    """Integracion real con el modelo TorchScript de OmniParser V2.

    Solo se ejecuta si el usuario proporciona explicitamente la ruta al modelo
    mediante OMNIPARSER_MODEL_PATH. Nunca se descargan pesos automaticamente.
    """

    def setUp(self):
        self.adapter = OmniParserAdapter(model_path=MODEL_PATH, device="cpu")
        self.assertTrue(self.adapter.available, self.adapter.error)

    def test_cargar_modelo_real(self):
        """El modelo real carga y reporta tiempo de carga."""
        self.assertIsNotNone(self.adapter.load_time_seconds)
        self.assertGreater(self.adapter.load_time_seconds, 0)
        self.assertIsNone(self.adapter.error)

    def test_detect_sobre_imagen_fixture(self):
        """detect() sobre una imagen de prueba devuelve regiones con bbox valido."""
        # Crear una imagen sintetica simple como fixture de prueba.
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
                self.assertEqual(r.source, "omniparser_v2_icon_detect_v3")
                self.assertEqual(r.model, "icon_detect_v3")
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
