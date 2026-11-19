"""
Tests unitarios del manifiesto local de detectores y modelos - unidad 3.8.6.3.3.12.

Pruebas para src/hands/detection/detector_manifest.py.

- Tests unitarios de contrato/logica: estados validos, serializacion a JSON,
  resumen contable, lista de fuentes disponibles y no disponibles, y persistencia
  en archivo JSON. Sin GUI ni modelos descargados silenciosamente.
- Test de comprobacion real de disponibilidad: ejecuta build_detector_manifest()
  sobre los componentes realmente instalados del entorno (UI Automation, OpenCV,
  OmniParser sin pesos, PaddleOCR sin directorio de modelos y Ollama/qwen3vl
  contra el servidor real si esta arrancado). Nunca sustituye una respuesta por
  un mock; reporta el estado real observado.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from src.hands.detection.detector_manifest import (
    DetectorManifest,
    DetectorManifestEntry,
    build_detector_manifest,
    SOURCE_UIA,
    SOURCE_OMNIPARSER,
    SOURCE_PADDLEOCR,
    SOURCE_QWEN3VL,
    SOURCE_OPENCV,
    STATUS_DISPONIBLE,
    STATUS_NO_DISPONIBLE,
    STATUS_NO_VERIFICADO,
    STATUS_VALIDOS,
    QWEN3VL_MODEL_DEFECTO,
)
from src.eyes.vision.vision import DEFAULT_VISION_MODEL


class TestDetectorManifestEstados(unittest.TestCase):
    """Estados de disponibilidad y serializacion de entradas."""

    def test_estados_validos(self):
        """Solo los tres estados canonicos son validos."""
        self.assertEqual(
            STATUS_VALIDOS,
            frozenset({
                STATUS_DISPONIBLE,
                STATUS_NO_DISPONIBLE,
                STATUS_NO_VERIFICADO,
            }),
        )

    def test_entrada_serializable_a_json(self):
        """DetectorManifestEntry.to_dict() produce un diccionario plano serializable."""
        entrada = DetectorManifestEntry(
            source="test_detector",
            model="modelo_test",
            version="1.0",
            weight_path=None,
            runtime="runtime_test",
            device="cpu",
            precision="float32",
            parameters={"umbral": 0.5},
            license="MIT",
            status=STATUS_DISPONIBLE,
            error=None,
            fallback=None,
            checked_at="2026-01-01T00:00:00+00:00",
            load_time_seconds=0.123,
        )
        d = entrada.to_dict()
        self.assertEqual(d["source"], "test_detector")
        self.assertEqual(d["status"], STATUS_DISPONIBLE)
        self.assertEqual(d["precision"], "float32")
        self.assertEqual(d["load_time_seconds"], 0.123)
        json.dumps(d)  # debe ser serializable sin excepcion

    def test_entrada_estado_invalido_raise(self):
        """Un estado fuera del conjunto canonico lanza ValueError."""
        with self.assertRaises(ValueError):
            DetectorManifestEntry(
                source="x",
                model="x",
                version="1.0",
                weight_path=None,
                runtime="x",
                device="x",
                precision="x",
                parameters={},
                license=None,
                status="estado_inexistente",
                error=None,
                fallback=None,
                checked_at="2026-01-01T00:00:00+00:00",
            )

    def test_manifest_serializacion_y_resumen(self):
        """DetectorManifest.to_dict/to_json y summary() son consistentes."""
        m = DetectorManifest(entries={
            SOURCE_UIA: DetectorManifestEntry(
                source=SOURCE_UIA,
                model="uia",
                version="os_integrado",
                weight_path=None,
                runtime="pywinauto",
                device="n/a",
                precision="n/a",
                parameters={},
                license=None,
                status=STATUS_DISPONIBLE,
                error=None,
                fallback=None,
                checked_at="2026-01-01T00:00:00+00:00",
            ),
            SOURCE_OMNIPARSER: DetectorManifestEntry(
                source=SOURCE_OMNIPARSER,
                model="icon_detect_v3",
                version="v2.0",
                weight_path=None,
                runtime="torch",
                device="cpu",
                precision="float32",
                parameters={},
                license="MIT",
                status=STATUS_NO_DISPONIBLE,
                error="sin pesos",
                fallback=None,
                checked_at="2026-01-01T00:00:00+00:00",
            ),
        })
        d = m.to_dict()
        self.assertEqual(d["resumen"]["total"], 2)
        self.assertEqual(d["resumen"]["disponibles"], 1)
        self.assertEqual(d["resumen"]["no_disponibles"], 1)
        self.assertEqual(d["resumen"]["no_verificados"], 0)
        self.assertIn(SOURCE_UIA, d["resumen"]["fuentes_disponibles"])
        self.assertIn(SOURCE_OMNIPARSER, d["resumen"]["fuentes_no_disponibles"])
        json.dumps(d)  # serializable

    def test_manifest_guardar_y_cargar_json(self):
        """save_json y load_json persisten y recuperan el manifiesto sin perdida."""
        m = DetectorManifest(entries={
            SOURCE_OPENCV: DetectorManifestEntry(
                source=SOURCE_OPENCV,
                model="opencv",
                version="4.10.0",
                weight_path=None,
                runtime="opencv-python",
                device="cpu",
                precision="uint8",
                parameters={},
                license=None,
                status=STATUS_DISPONIBLE,
                error=None,
                fallback=None,
                checked_at="2026-01-01T00:00:00+00:00",
            ),
        })
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "manifiesto.json")
            m.save_json(ruta)
            self.assertTrue(os.path.exists(ruta))
            cargado = DetectorManifest.load_json(ruta)
            self.assertEqual(cargado.get_entry(SOURCE_OPENCV).status, STATUS_DISPONIBLE)
            self.assertEqual(cargado.get_entry(SOURCE_OPENCV).version, "4.10.0")
            self.assertEqual(cargado.available_sources(), [SOURCE_OPENCV])
            self.assertEqual(cargado.missing_optional_sources(), [])


class TestDetectorManifestComprobacionReal(unittest.TestCase):
    """Comprobacion real de disponibilidad de los detectores del entorno."""

    def test_build_detector_manifest_devuelve_entradas_reales(self):
        """build_detector_manifest() construye una entrada por detector con estado real."""
        m = build_detector_manifest()
        fuentes = {
            SOURCE_UIA, SOURCE_OMNIPARSER, SOURCE_PADDLEOCR,
            SOURCE_QWEN3VL, SOURCE_OPENCV,
        }
        self.assertEqual(set(m.entries.keys()), fuentes)
        for source, entrada in m.entries.items():
            self.assertEqual(entrada.source, source)
            self.assertIn(entrada.status, STATUS_VALIDOS)
            # error solo puede tener sentido si no esta disponible
            if entrada.status == STATUS_DISPONIBLE:
                self.assertIsNone(entrada.error)
            self.assertIsInstance(entrada.checked_at, str)
            self.assertGreater(len(entrada.checked_at), 0)

    def test_uia_disponible_en_entorno_real(self):
        """UI Automation esta disponible porque pywinauto/comtypes estan instalados."""
        m = build_detector_manifest()
        uia = m.get_entry(SOURCE_UIA)
        self.assertIsNotNone(uia)
        self.assertEqual(uia.status, STATUS_DISPONIBLE)
        self.assertIsNone(uia.error)
        self.assertIsNotNone(uia.runtime)

    def test_opencv_disponible_en_entorno_real(self):
        """OpenCV esta disponible porque opencv-python esta instalado."""
        m = build_detector_manifest()
        opencv = m.get_entry(SOURCE_OPENCV)
        self.assertIsNotNone(opencv)
        self.assertEqual(opencv.status, STATUS_DISPONIBLE)
        self.assertIsNotNone(opencv.version)

    def test_omniparser_disponible_con_pesos_descargados(self):
        """OmniParser reporta DISPONIBLE porque el modelo icon_detect_v3 se
        descargo y esta en la cache de HuggingFace. Nunca un resultado ficticio."""
        m = build_detector_manifest()
        om = m.get_entry(SOURCE_OMNIPARSER)
        self.assertIsNotNone(om)
        self.assertEqual(om.status, STATUS_DISPONIBLE)
        self.assertIsNone(om.error)
        self.assertIsNotNone(om.weight_path)
        self.assertIn("icon_detect_v3", om.weight_path)
        self.assertEqual(om.model, "icon_detect_v3")
        self.assertEqual(om.license, "MIT")

    def test_paddleocr_disponible_con_modelos_instalados(self):
        """PaddleOCR reporta DISPONIBLE porque los modelos PP-OCRv6_medium
        estan instalados en .paddlex\\official_models. Nunca un resultado
        ficticio ni descarga silenciosa."""
        m = build_detector_manifest()
        po = m.get_entry(SOURCE_PADDLEOCR)
        self.assertIsNotNone(po)
        self.assertEqual(po.status, STATUS_DISPONIBLE)
        self.assertIsNone(po.error)
        self.assertIsNotNone(po.weight_path)
        self.assertIn("paddlex", po.weight_path)
        self.assertEqual(po.model, "paddleocr")
        self.assertEqual(po.version, "PP-OCRv5")

    def test_qwen3vl_reporta_estado_real_del_servidor_ollama(self):
        """Qwen3-VL/Ollama consulta el servidor real; si no arrancado, NO_VERIFICADO."""
        m = build_detector_manifest()
        qw = m.get_entry(SOURCE_QWEN3VL)
        self.assertIsNotNone(qw)
        # Estado real observado: disponible (servidor arrancado y modelo presente)
        # o no_verificado (servidor no alcanzable o modelo ausente).
        self.assertIn(qw.status, (STATUS_DISPONIBLE, STATUS_NO_VERIFICADO))
        if qw.status == STATUS_NO_VERIFICADO:
            self.assertIsNotNone(qw.error)
        # El manifiesto comprueba el mismo modelo que usan Vision y el
        # calibrador universal.
        self.assertEqual(qw.model, QWEN3VL_MODEL_DEFECTO)
        self.assertEqual(QWEN3VL_MODEL_DEFECTO, DEFAULT_VISION_MODEL)

    def test_resumen_contable_coherente_con_entradas(self):
        """El resumen contable coincide con el conteo real de entradas por estado."""
        m = build_detector_manifest()
        resumen = m.summary()
        total = sum(1 for _ in m.entries)
        disponibles = sum(1 for e in m.entries.values()
                        if e.status == STATUS_DISPONIBLE)
        no_disponibles = sum(1 for e in m.entries.values()
                             if e.status == STATUS_NO_DISPONIBLE)
        no_verificados = sum(1 for e in m.entries.values()
                             if e.status == STATUS_NO_VERIFICADO)
        self.assertEqual(resumen["total"], total)
        self.assertEqual(resumen["disponibles"], disponibles)
        self.assertEqual(resumen["no_disponibles"], no_disponibles)
        self.assertEqual(resumen["no_verificados"], no_verificados)
        self.assertEqual(len(resumen["fuentes_disponibles"]), disponibles)
        self.assertEqual(len(resumen["fuentes_no_disponibles"]),
                         no_disponibles + no_verificados)
