"""
Adaptador de reconocimiento de texto de interfaz basado en PaddleOCR.

Capa de deteccion de texto (OCR) para controles de interfaz que expone
poligonos/cajas y confianza por region de texto detectada, e incluye un
metodo para asociar etiquetas OCR con candidatos visuales (UIA, OmniParser,
Vision) mediante proximidad, alineacion y contencion, sin convertir una
region de texto en boton por el mero hecho de tener texto.

El modelo NO se descarga de forma silenciosa: la ruta del modelo (model_dir)
y los archivos de deteccion/reconocimiento deben proporcionarse explicitamente.
Si PaddleOCR / paddlepaddle no estan disponibles o el modelo no puede cargarse,
el adaptador se degrada graceful y reporta el motivo en la propiedad ``error``.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.utils.logger import get_logger
from src.utils.ui_element_model import UIElementData

logger = get_logger(__name__)

# Ruta por defecto del directorio de modelos de PaddleOCR (si se proporciona).
DEFAULT_MODEL_DIR: Optional[str] = None
DEFAULT_LANG = "en"


@dataclass
class PaddleOCRRegion:
    """Region de texto detectada por PaddleOCR.

    ``bbox`` guarda la caja en pixeles de la imagen de entrada [x1, y1, x2, y2].
    ``polygon`` guarda el poligono de contorno cuando PaddleOCR lo expone
    (una lista de puntos [[x,y], ...]); puede estar vacia si la version del
    motor no lo proporciona. La conversion a coordenadas de escritorio/ventana
    y el calibrado geometrico corresponden a capas superiores
    (CalibrationManager / CoordinateManager).
    """

    text: str = ""
    bbox: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    polygon: List[List[int]] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "paddleocr"
    model: str = "paddleocr"
    device: str = "cpu"
    screen: int = 0
    language: str = DEFAULT_LANG
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve un diccionario plano serializable."""
        return {
            "text": self.text,
            "bbox": list(self.bbox),
            "polygon": [list(p) for p in self.polygon],
            "confidence": float(self.confidence),
            "source": self.source,
            "model": self.model,
            "device": self.device,
            "screen": int(self.screen),
            "language": self.language,
            "metadata": dict(self.metadata),
        }

    def to_ui_element_data(self) -> UIElementData:
        """Convierte la region en un UIElementData canonico.

        El texto detectado se guarda en ``text`` y la confianza/fuente en
        ``calibration_data`` para trazabilidad, sin anadir campos al modelo
        canonico. El tipo se deja como ``"text"`` (etiqueta de texto), no como
        boton, pues una region OCR por si sola no implica interactividad.
        """
        x1, y1, x2, y2 = [int(v) for v in self.bbox]
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        return UIElementData(
            name=self.text or "text",
            type="text",
            text=self.text,
            bbox=[x1, y1, x2, y2],
            center=[center_x, center_y],
            screen=int(self.screen),
            interactive=False,
            confidence=float(self.confidence),
            calibrated=False,
            calibration_data={
                "source": self.source,
                "model": self.model,
                "device": self.device,
                "language": self.language,
            },
        )


# ---------------------------------------------------------------------------
# Utilidades geometricas para asociacion OCR <-> candidatos visuales
# ---------------------------------------------------------------------------

def _box_center(bbox: Union[List[int], Tuple[int, int, int, int]]) -> Tuple[float, float]:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _box_area(bbox: Union[List[int], Tuple[int, int, int, int]]) -> float:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    w = max(0.0, x2 - x1)
    h = max(0.0, y2 - y1)
    return w * h


def _iou(a: Union[List[int], Tuple[int, int, int, int]],
         b: Union[List[int], Tuple[int, int, int, int]]) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in a]
    bx1, by1, bx2, by2 = [float(v) for v in b]
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = _box_area(a)
    area_b = _box_area(b)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _center_distance(a: Union[List[int], Tuple[int, int, int, int]],
                     b: Union[List[int], Tuple[int, int, int, int]]) -> float:
    cx1, cy1 = _box_center(a)
    cx2, cy2 = _box_center(b)
    return math.hypot(cx2 - cx1, cy2 - cy1)


def _is_contained(inner: Union[List[int], Tuple[int, int, int, int]],
                  outer: Union[List[int], Tuple[int, int, int, int]],
                  tolerance: float = 0.0) -> bool:
    ix1, iy1, ix2, iy2 = [float(v) for v in inner]
    ox1, oy1, ox2, oy2 = [float(v) for v in outer]
    return (ix1 >= ox1 - tolerance and iy1 >= oy1 - tolerance
            and ix2 <= ox2 + tolerance and iy2 <= oy2 + tolerance)


def _is_horizontally_aligned(a: Union[List[int], Tuple[int, int, int, int]],
                             b: Union[List[int], Tuple[int, int, int, int]],
                             max_vertical_offset: float = 0.3) -> bool:
    """True si los centros Y estan dentro de una fraccion de la altura media."""
    (cx1, cy1) = _box_center(a)
    (cx2, cy2) = _box_center(b)
    ha = max(1.0, float(a[3] - a[1]))
    hb = max(1.0, float(b[3] - b[1]))
    mean_h = (ha + hb) / 2.0
    return abs(cy2 - cy1) <= max_vertical_offset * mean_h


# ---------------------------------------------------------------------------
# Adaptador PaddleOCR para JARVIS
# ---------------------------------------------------------------------------

class PaddleOCRAdapter:
    """Adaptador de reconocimiento de texto de interfaz basado en PaddleOCR.

    Recibe la ruta de un directorio de modelos ya disponible localmente y
    expone ``detect()`` para obtener regiones de texto con caja, poligono y
    confianza a partir de una imagen (captura de pantalla, crop de ventana,
    etc.). Tambien expone ``associate_with_candidates()`` para vincular
    etiquetas OCR con candidatos visuales existentes.

    Nunca descarga pesos ni modelos silenciosamente. Si ``model_dir`` es None,
    paddlepaddle/paddleocr no estan instalados o el modelo no puede cargarse,
    ``available`` es False y ``detect()`` devuelve una lista vacia, registrando
    el motivo en ``error``.
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        rec_model_dir: Optional[str] = None,
        lang: str = DEFAULT_LANG,
        device: Optional[str] = None,
        use_gpu: bool = False,
        text_score_thresh: float = 0.5,
        box_thresh: float = 0.5,
        unclip_ratio: float = 1.6,
        det_limit_side_len: int = 960,
        show_log: bool = False,
        engine: str = "onnxruntime",
        ocr_version: str = "PP-OCRv5",
    ) -> None:
        self.model_dir = model_dir
        self.rec_model_dir = rec_model_dir
        self.lang = lang
        self.device = device or ("cuda" if use_gpu else "cpu")
        self.use_gpu = bool(use_gpu)
        self.text_score_thresh = float(text_score_thresh)
        self.box_thresh = float(box_thresh)
        self.unclip_ratio = float(unclip_ratio)
        self.det_limit_side_len = int(det_limit_side_len)
        self.show_log = bool(show_log)
        self.engine = engine
        self.ocr_version = ocr_version

        self._ocr: Optional[Any] = None
        self._available = False
        self._error: Optional[str] = None
        self._load_time_seconds: Optional[float] = None

        self._load_ocr()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True si PaddleOCR esta cargado y listo para reconocer texto."""
        return self._available

    @property
    def error(self) -> Optional[str]:
        """Motivo de no-disponibilidad, o None si esta disponible."""
        return self._error

    @property
    def load_time_seconds(self) -> Optional[float]:
        return self._load_time_seconds

    @property
    def device_effective(self) -> str:
        return self.device

    # ------------------------------------------------------------------
    # Carga del motor (explicita, nunca silenciosa)
    # ------------------------------------------------------------------

    def _load_ocr(self) -> None:
        start = time.perf_counter()
        try:
            # Importar paddleocr solo cuando se construye el adaptador.
            from paddleocr import PaddleOCR as _PaddleOCR  # type: ignore

            # Construir kwargs solo con parametros que la version instalada
            # acepte, inspeccionando la firma del constructor.
            import inspect
            sig = inspect.signature(_PaddleOCR.__init__)
            kwargs: Dict[str, Any] = {}
            if "lang" in sig.parameters:
                kwargs["lang"] = self.lang
            if "use_gpu" in sig.parameters:
                kwargs["use_gpu"] = self.use_gpu
            if "show_log" in sig.parameters:
                kwargs["show_log"] = self.show_log
            # device, engine y ocr_version viajan a traves de **kwargs hasta
            # PaddleXPipelineWrapper.parse_common_args, que los acepta.
            kwargs["device"] = self.device
            kwargs["engine"] = self.engine
            kwargs["ocr_version"] = self.ocr_version
            if self.model_dir is not None:
                if "text_detection_model_dir" in sig.parameters:
                    kwargs["text_detection_model_dir"] = self.model_dir
                if self.rec_model_dir is not None:
                    if "text_recognition_model_dir" in sig.parameters:
                        kwargs["text_recognition_model_dir"] = self.rec_model_dir
                else:
                    # Si solo se proporciona model_dir, usarlo tambien para
                    # reconocimiento (PaddleOCR validara que coincida).
                    if "text_recognition_model_dir" in sig.parameters:
                        kwargs["text_recognition_model_dir"] = self.model_dir
            else:
                # Sin model_dir proporcionado: no se intenta descarga silenciosa
                # de pesos. El adaptador queda no disponible.
                self._available = False
                self._ocr = None
                self._error = (
                    "model_dir no proporcionado: PaddleOCR requiere una ruta "
                    "explicita al directorio de modelos de deteccion (y opcionalmente "
                    "rec_model_dir para reconocimiento). No se descargaran pesos "
                    "silenciosamente"
                )
                self._load_time_seconds = time.perf_counter() - start
                logger.warning("[PADDLEOCR-ADAPTER] %s", self._error)
                return

            self._ocr = _PaddleOCR(**kwargs)
            self._available = True
            self._error = None
            self._load_time_seconds = time.perf_counter() - start
            logger.info(
                "[PADDLEOCR-ADAPTER] Motor PaddleOCR listo en %.3fs "
                "(disponible=%s, dispositivo=%s, idioma=%s, engine=%s, version=%s)",
                self._load_time_seconds, self._available, self.device, self.lang,
                self.engine, self.ocr_version,
            )
        except ImportError as exc:
            self._available = False
            self._ocr = None
            self._error = (
                "PaddleOCR no esta instalado (pip install paddleocr) o "
                "faltan dependencias: %s" % exc
            )
            self._load_time_seconds = time.perf_counter() - start
            logger.warning("[PADDLEOCR-ADAPTER] %s", self._error)
        except Exception as exc:  # noqa: BLE001
            self._available = False
            self._ocr = None
            self._error = "No se pudo inicializar PaddleOCR: %s" % exc
            self._load_time_seconds = time.perf_counter() - start
            logger.warning("[PADDLEOCR-ADAPTER] %s", self._error)

    # ------------------------------------------------------------------
    # Deteccion de texto
    # ------------------------------------------------------------------

    def detect(
        self,
        image: Union[str, Path, "ImageLike"],
        screen: int = 0,
    ) -> List[PaddleOCRRegion]:
        """Detecta regiones de texto en ``image``.

        Argumentos:
            image: ruta de archivo, objeto compatible con PIL/numpy o similar.
            screen: indice de pantalla asociado a la imagen.

        Retorna:
            Lista de PaddleOCRRegion ordenada por confianza descendente.
            Devuelve [] si el adaptador no esta disponible.
        """
        if not self._available or self._ocr is None:
            logger.debug(
                "[PADDLEOCR-ADAPTER] detect() omitido: no disponible (%s)",
                self._error,
            )
            return []

        try:
            raw = self._ocr.predict(image)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[PADDLEOCR-ADAPTER] Error durante el OCR: %s", exc
            )
            return []

        regions: List[PaddleOCRRegion] = []
        if not raw:
            return regions

        # PaddleOCR 3.x devuelve una lista de OCRResult, uno por pagina.
        # Cada page.json es un dict con clave "res" que contiene
        # rec_texts, rec_boxes, rec_scores (listas paralelas).
        for page in raw:
            if page is None:
                continue
            try:
                page_data = page.json if hasattr(page, "json") else {}
            except Exception:  # noqa: BLE001
                page_data = {}
            if not isinstance(page_data, dict):
                continue
            res = page_data.get("res", {})
            if not isinstance(res, dict):
                continue
            texts = res.get("rec_texts", []) or []
            boxes = res.get("rec_boxes", []) or []
            scores = res.get("rec_scores", []) or []
            n = min(len(texts), len(boxes), len(scores))
            for i in range(n):
                try:
                    text = str(texts[i])
                    box = boxes[i]
                    score = float(scores[i])
                    if len(box) >= 4:
                        x1, y1, x2, y2 = [int(round(float(v))) for v in box[:4]]
                    else:
                        continue
                    regions.append(
                        PaddleOCRRegion(
                            text=text,
                            bbox=[x1, y1, x2, y2],
                            polygon=[],
                            confidence=score,
                            source="paddleocr",
                            model="paddleocr",
                            device=self.device,
                            screen=int(screen),
                            language=self.lang,
                            metadata={"engine": self.engine, "version": self.ocr_version},
                        )
                    )
                except Exception:  # noqa: BLE001
                    continue

        # Filtrar por umbral de confianza del texto configurado en el adaptador.
        regions = [
            r for r in regions if r.confidence >= self.text_score_thresh
        ]

        regions.sort(key=lambda r: r.confidence, reverse=True)
        logger.info(
            "[PADDLEOCR-ADAPTER] %d regiones de texto detectadas "
            "(conf>=%.2f, dispositivo=%s, idioma=%s)",
            len(regions), self.text_score_thresh, self.device, self.lang,
        )
        return regions

    @staticmethod
    def _parse_line(
        line: Any,
        screen: int,
    ) -> Optional[PaddleOCRRegion]:
        """Parsea una linea de salida de PaddleOCR a PaddleOCRRegion.

        Soporta:
          - (puntos, (texto, confianza))  -> puntos = [[x,y], ...]
          - (bbox, (texto, confianza))    -> bbox = [x1, y1, x2, y2]
          - dict con claves reconocidas
        """
        points = None
        text = ""
        confidence = 0.0

        if isinstance(line, (list, tuple)) and len(line) >= 2:
            first, second = line[0], line[1]
            # Segundo elemento suele ser (texto, confianza) o dict.
            if isinstance(second, (list, tuple)) and len(second) >= 1:
                text = str(second[0])
                if len(second) >= 2:
                    try:
                        confidence = float(second[1])
                    except (TypeError, ValueError):
                        confidence = 0.0
            elif isinstance(second, dict):
                text = str(second.get("text", ""))
                try:
                    confidence = float(second.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0

            # Primer elemento: poligono de puntos o bbox.
            if isinstance(first, (list, tuple)) and len(first) >= 4:
                # Detectar si es poligono (lista de puntos) o caja recta.
                if len(first) >= 4 and all(
                    isinstance(p, (list, tuple)) and len(p) >= 2 for p in first[:4]
                ):
                    pts = [[int(round(float(p[0]))), int(round(float(p[1])))]
                           for p in first if isinstance(p, (list, tuple)) and len(p) >= 2]
                    if len(pts) >= 4:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        bbox = [min(xs), min(ys), max(xs), max(ys)]
                        points = pts
                    else:
                        bbox = [int(round(float(v))) for v in first[:4]]
                else:
                    bbox = [int(round(float(v))) for v in first[:4]]
            else:
                bbox = [0, 0, 0, 0]
        elif isinstance(line, dict):
            text = str(line.get("text", ""))
            try:
                confidence = float(line.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            box = line.get("bbox") or line.get("box") or line.get("points")
            if isinstance(box, (list, tuple)) and len(box) >= 4:
                if all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in box[:4]):
                    pts = [[int(round(float(p[0]))), int(round(float(p[1])))]
                           for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                    if len(pts) >= 4:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        bbox = [min(xs), min(ys), max(xs), max(ys)]
                        points = pts
                    else:
                        bbox = [int(round(float(v))) for v in box[:4]]
                else:
                    bbox = [int(round(float(v))) for v in box[:4]]
            else:
                bbox = [0, 0, 0, 0]
        else:
            return None

        # Normalizar confianza a [0, 1].
        if confidence < 0.0 or confidence > 1.0:
            confidence = max(0.0, min(1.0, confidence))
        if text.strip() == "":
            return None

        return PaddleOCRRegion(
            text=text,
            bbox=bbox,
            polygon=points if points else [],
            confidence=confidence,
            source="paddleocr",
            model="paddleocr",
            device="cpu",
            screen=int(screen),
            language=DEFAULT_LANG,
            metadata={"detection_index": len(points) if points else 0},
        )

    # ------------------------------------------------------------------
    # Asociacion de etiquetas OCR con candidatos visuales
    # ------------------------------------------------------------------

    @staticmethod
    def associate_with_candidates(
        regions: List[PaddleOCRRegion],
        candidates: List[Dict[str, Any]],
        proximity_threshold: float = 60.0,
        iou_threshold: float = 0.3,
        containment_tolerance: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """Asocia regiones de texto OCR con candidatos visuales.

        Cada candidato es un diccionario que debe contener al menos una de las
        claves ``bbox`` (lista [x1, y1, x2, y2]) o ``center`` ([x, y]).
        Se anade al candidato una clave ``ocr`` con la mejor region asociada
        (texto, confianza, caja, poligono) cuando se cumple alguno de estos
        criterios:

        * contencion: la caja OCR esta dentro del candidato (o viceversa);
        * solapamiento: IoU >= iou_threshold;
        * proximidad: distancia entre centros <= proximity_threshold y
          alineacion horizontal.

        Una region de texto por si sola NO implica que el candidato sea un
        boton o elemento accionable; solo se adjunta como etiqueta de texto
        asociada para trazabilidad. El llamador decide la interactividad.

        Retorna la lista de candidatos (los mismos objetos, enriquecidos).
        """
        for candidate in candidates:
            cand_bbox = candidate.get("bbox")
            cand_center = candidate.get("center")
            if cand_bbox is None and cand_center is not None:
                cx, cy = [float(v) for v in cand_center[:2]]
                # Construir una caja minima alrededor del centro.
                cand_bbox = [int(cx), int(cy), int(cx), int(cy)]
            if cand_bbox is None or len(cand_bbox) != 4:
                continue

            best: Optional[PaddleOCRRegion] = None
            best_score = -1.0

            for region in regions:
                score = 0.0
                matched = False

                # Contencion mutua (pista fuerte).
                if _is_contained(region.bbox, cand_bbox, containment_tolerance):
                    score = 0.9
                    matched = True
                elif _is_contained(cand_bbox, region.bbox, containment_tolerance):
                    score = 0.8
                    matched = True
                else:
                    # Solapamiento.
                    iou_val = _iou(region.bbox, cand_bbox)
                    if iou_val >= iou_threshold:
                        score = 0.6 + 0.3 * iou_val
                        matched = True
                    else:
                        # Proximidad + alineacion horizontal.
                        dist = _center_distance(region.bbox, cand_bbox)
                        if dist <= proximity_threshold and _is_horizontally_aligned(
                            region.bbox, cand_bbox
                        ):
                            score = 0.4 + 0.2 * (1.0 - dist / proximity_threshold)
                            matched = True

                if matched and score > best_score:
                    best_score = score
                    best = region

            if best is not None:
                candidate["ocr"] = {
                    "text": best.text,
                    "confidence": best.confidence,
                    "bbox": list(best.bbox),
                    "polygon": [list(p) for p in best.polygon],
                    "source": best.source,
                    "association_score": best_score,
                }

        return candidates

    # ------------------------------------------------------------------
    # Informacion de compatibilidad
    # ------------------------------------------------------------------

    def compatibility_info(self) -> Dict[str, Any]:
        """Devuelve datos de compatibilidad del adaptador (no ejecuta el SO)."""
        return {
            "source": "paddleocr",
            "model": "paddleocr",
            "device_requested": self.device,
            "device_effective": self.device,
            "available": self._available,
            "error": self._error,
            "load_time_seconds": self._load_time_seconds,
            "lang": self.lang,
            "text_score_thresh": self.text_score_thresh,
            "box_thresh": self.box_thresh,
            "unclip_ratio": self.unclip_ratio,
            "det_limit_side_len": self.det_limit_side_len,
            "use_gpu": self.use_gpu,
            "show_log": self.show_log,
            "model_dir": self.model_dir,
            "rec_model_dir": self.rec_model_dir,
            "engine": self.engine,
            "ocr_version": self.ocr_version,
        }


# Alias de tipo para evitar importar PIL/numpy solo en la firma.
ImageLike = Any

__all__ = [
    "PaddleOCRRegion",
    "PaddleOCRAdapter",
    "DEFAULT_LANG",
    "DEFAULT_MODEL_DIR",
]
