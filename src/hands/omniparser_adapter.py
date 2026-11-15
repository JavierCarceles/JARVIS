"""
Adaptador de deteccion visual de OmniParser V2 (icon_detect_v3).

Capa de fallback visual para controles que UI Automation no expone.
Utiliza el detector TorchScript YOLOv9-E de OmniParser V2
(microsoft/OmniParser-v2.0, icon_detect_v3/model.pt, licencia MIT)
para detectar regiones que parecen interactivas en una captura de pantalla.

El modelo NO se descarga de forma silenciosa: la ruta del modelo (model_path)
debe proporcionarse explicitamente. Si el modelo no esta disponible, el
adaptador se degrada gracefully y reporta el error en la propiedad ``error``.
La deteccion corre en CPU por defecto (CUDA solo si esta disponible).

Adaptado de microsoft/OmniParser (util/yolov9.py), licencia MIT.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import torch
from PIL import Image

from src.utils.logger import get_logger
from src.utils.ui_element_model import UIElementData

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Detector YOLOv9-E (TorchScript) — adaptado de microsoft/OmniParser (MIT)
# ---------------------------------------------------------------------------

DEFAULT_MODEL_FILE = "icon_detect_v3/model.pt"
DEFAULT_REPO_ID = "microsoft/OmniParser-v2.0"


class _Boxes:
    __slots__ = ("xyxy", "conf")

    def __init__(self, xyxy: torch.Tensor, confidence: torch.Tensor):
        self.xyxy = xyxy
        self.conf = confidence


class _Result:
    __slots__ = ("boxes",)

    def __init__(self, boxes: _Boxes):
        self.boxes = boxes


def _batched_nms_pure(boxes: torch.Tensor, scores: torch.Tensor,
                      iou_threshold: float) -> torch.Tensor:
    """Supresion no-maxima simple (una clase) sin depender de torchvision."""
    if len(boxes) == 0:
        return torch.empty((0,), dtype=torch.long)
    scores_sorted, order = scores.sort(descending=True)
    boxes_sorted = boxes[order]
    suppressed = torch.zeros(len(boxes_sorted), dtype=torch.bool)
    keep: List[int] = []
    for i in range(len(boxes_sorted)):
        if suppressed[i]:
            continue
        keep.append(int(order[i].item()))
        if i + 1 >= len(boxes_sorted):
            break
        b1 = boxes_sorted[i:i + 1]
        b2 = boxes_sorted[i + 1:]
        ix1 = torch.maximum(b1[:, 0], b2[:, 0])
        iy1 = torch.maximum(b1[:, 1], b2[:, 1])
        ix2 = torch.minimum(b1[:, 2], b2[:, 2])
        iy2 = torch.minimum(b1[:, 3], b2[:, 3])
        inter = (ix2 - ix1).clamp(min=0) * (iy2 - iy1).clamp(min=0)
        area1 = (b1[:, 2] - b1[:, 0]) * (b1[:, 3] - b1[:, 1])
        area2 = (b2[:, 2] - b2[:, 0]) * (b2[:, 3] - b2[:, 1])
        iou = inter / (area1 + area2 - inter + 1e-7)
        suppressed[i + 1:] = suppressed[i + 1:] | (iou > iou_threshold)
    return torch.tensor(keep, dtype=torch.long)


class _YOLOv9Detector:
    """Detector TorchScript YOLOv9-E con API predecible.

    Carga un modelo .pt de icon_detect_v3 mediante torch.jit.load. No descarga
    pesos por si misma: si model_path es None, intenta descargar desde
    HuggingFace solo como ultimo recurso (comportamiento de la clase original).
    """

    strides = (8, 16, 32)

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        device: Optional[Union[str, torch.device]] = None,
        repo_id: str = DEFAULT_REPO_ID,
        revision: str = "main",
    ):
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA solicitado pero no disponible")

        from huggingface_hub import hf_hub_download

        if model_path is None:
            model_path = hf_hub_download(
                repo_id=repo_id,
                filename=DEFAULT_MODEL_FILE,
                revision=revision,
            )
        self.model_path = Path(model_path)
        self.model = torch.jit.load(str(self.model_path),
                                    map_location=self.device).eval()

    @staticmethod
    def _normalize_image_size(image_size) -> tuple:
        if isinstance(image_size, int):
            width = height = image_size
        elif len(image_size) == 2:
            height, width = image_size
        else:
            raise ValueError(
                "Se esperaba uno o dos dimensiones de imagen, "
                "se recibio: %s" % (image_size,)
            )
        width = ((int(width) + 31) // 32) * 32
        height = ((int(height) + 31) // 32) * 32
        return width, height

    @staticmethod
    def _load_image(source: Union[str, Path, Image.Image, np.ndarray]
                    ) -> Image.Image:
        if isinstance(source, Image.Image):
            return source.convert("RGB")
        if isinstance(source, np.ndarray):
            return Image.fromarray(source).convert("RGB")
        with Image.open(source) as image:
            return image.convert("RGB")

    def _preprocess(self, image: Image.Image, image_size: int):
        target_width, target_height = self._normalize_image_size(image_size)
        image_width, image_height = image.size
        scale = min(target_width / image_width,
                    target_height / image_height)
        resized_width = int(image_width * scale)
        resized_height = int(image_height * scale)
        pad_left = (target_width - resized_width) // 2
        pad_top = (target_height - resized_height) // 2

        resized = image.resize((resized_width, resized_height),
                               Image.Resampling.LANCZOS)
        padded = Image.new("RGB", (target_width, target_height),
                           (114, 114, 114))
        padded.paste(resized, (pad_left, pad_top))
        image_array = np.asarray(padded, dtype=np.float32).transpose(2, 0, 1) / 255.0
        image_tensor = torch.from_numpy(image_array).unsqueeze(0).to(
            self.device
        )
        return image_tensor, scale, pad_left, pad_top

    def _decode(self, outputs):
        class_logits: List[torch.Tensor] = []
        decoded_boxes: List[torch.Tensor] = []
        for output_index, stride in zip(range(0, len(outputs), 2),
                                        self.strides):
            layer_logits, layer_distances = outputs[
                output_index:output_index + 2
            ]
            batch_size, _, height, width = layer_logits.shape
            layer_logits = layer_logits.permute(0, 2, 3, 1).reshape(
                batch_size, -1, layer_logits.shape[1]
            )
            layer_distances = layer_distances.permute(0, 2, 3, 1).reshape(
                batch_size, -1, 4
            ) * stride

            grid_y, grid_x = torch.meshgrid(
                torch.arange(height, device=self.device),
                torch.arange(width, device=self.device),
                indexing="ij",
            )
            anchors = (torch.stack((grid_x, grid_y), dim=-1).reshape(-1, 2)
                       + 0.5) * stride
            left_top, right_bottom = layer_distances.chunk(2, dim=-1)
            decoded_boxes.append(torch.cat(
                (anchors - left_top, anchors + right_bottom), dim=-1
            ))
            class_logits.append(layer_logits)

        return (torch.cat(class_logits, dim=1).sigmoid(),
                torch.cat(decoded_boxes, dim=1))

    def _inference_context(self):
        if self.device.type == "cuda":
            return torch.autocast(device_type="cuda", dtype=torch.float16)
        from contextlib import nullcontext
        return nullcontext()

    @torch.inference_mode()
    def predict(self, source: Union[str, Path, Image.Image, np.ndarray],
                conf: float = 0.25, imgsz: int = 640,
                iou: float = 0.7, max_det: int = 300):
        image = self._load_image(source)
        image_tensor, scale, pad_left, pad_top = self._preprocess(
            image, imgsz
        )

        with self._inference_context(), torch.jit.optimized_execution(False):
            class_scores, boxes = self._decode(self.model(image_tensor))

        scores, class_ids = class_scores[0].max(dim=-1)
        valid = scores > conf
        scores = scores[valid]
        class_ids = class_ids[valid]
        boxes = boxes[0][valid]
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_left) / scale
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_top) / scale

        keep = _batched_nms_pure(boxes, scores, iou)[:max_det]
        boxes = boxes[keep]
        scores = scores[keep]
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clamp(0, image.width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clamp(0, image.height)
        return [_Result(_Boxes(boxes, scores))]


# ---------------------------------------------------------------------------
# Resultado de deteccion de OmniParser
# ---------------------------------------------------------------------------

@dataclass
class OmniParserRegion:
    """Region interactiva detectada por OmniParser V2 icon_detect_v3.

    ``coordinates`` guarda la caja en pixeles de la imagen de entrada
    [x1, y1, x2, y2]. La conversion a coordenadas de escritorio/ventana y
    el calibrado geometrico corresponden a capas superiores
    (CalibrationManager / CoordinateManager).
    """

    name: str = ""
    bbox: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    confidence: float = 0.0
    source: str = "omniparser_v2_icon_detect_v3"
    model: str = "icon_detect_v3"
    device: str = "cpu"
    screen: int = 0
    interactive: bool = True
    calibrated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve un diccionario plano serializable."""
        return {
            "name": self.name,
            "bbox": list(self.bbox),
            "confidence": float(self.confidence),
            "source": self.source,
            "model": self.model,
            "device": self.device,
            "screen": int(self.screen),
            "interactive": bool(self.interactive),
            "calibrated": bool(self.calibrated),
            "metadata": dict(self.metadata),
        }

    def to_ui_element_data(self) -> UIElementData:
        """Convierte la region en un UIElementData canonico.

        La confianza y la fuente de deteccion se conservan en
        ``calibration_data`` para trazabilidad, sin añadir campos al modelo
        canonico.
        """
        x1, y1, x2, y2 = [int(v) for v in self.bbox]
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        return UIElementData(
            name=self.name or "element",
            type="element",
            bbox=[x1, y1, x2, y2],
            center=[center_x, center_y],
            screen=int(self.screen),
            interactive=bool(self.interactive),
            confidence=float(self.confidence),
            calibrated=bool(self.calibrated),
            calibration_data={
                "source": self.source,
                "model": self.model,
                "device": self.device,
            },
        )


# ---------------------------------------------------------------------------
# Adaptador OmniParser para JARVIS
# ---------------------------------------------------------------------------

class OmniParserAdapter:
    """Adaptador de deteccion visual basado en OmniParser V2 icon_detect_v3.

    Recibe la ruta de un modelo TorchScript ya disponible localmente y
    expone ``detect()`` para obtener regiones interactivas candidatas a
    partir de una imagen (captura de pantalla, crop de ventana, etc.).

    Nunca descarga pesos silenciosamente. Si ``model_path`` es None o el
    modelo no puede cargarse, ``available`` es False y ``detect()``
    devuelve una lista vacia, registrando el motivo en ``error``.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.7,
        max_detections: int = 300,
        img_size: int = 640,
    ) -> None:
        self.model_path = model_path
        self.device = device or (
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.max_detections = int(max_detections)
        self.img_size = int(img_size)
        self._detector: Optional[_YOLOv9Detector] = None
        self._available = False
        self._error: Optional[str] = None
        self._load_time_seconds: Optional[float] = None
        self._load_model()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True si el modelo esta cargado y listo para detectar."""
        return self._available

    @property
    def error(self) -> Optional[str]:
        """Motivo de no-disponibilidad, o None si esta disponible."""
        return self._error

    @property
    def load_time_seconds(self) -> Optional[float]:
        return self._load_time_seconds

    # ------------------------------------------------------------------
    # Carga de modelo (explicita, nunca silenciosa)
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        if self.model_path is None:
            self._available = False
            self._error = ("model_path no proporcionado: OmniParser "
                           "icon_detect_v3 no disponible")
            logger.warning("[OMNIPARSER-ADAPTER] %s", self._error)
            return

        start = time.perf_counter()
        try:
            path = Path(self.model_path)
            if not path.exists():
                self._available = False
                self._error = (
                    "Modelo OmniParser no encontrado en %s" % path
                )
                logger.warning("[OMNIPARSER-ADAPTER] %s", self._error)
                return
            self._detector = _YOLOv9Detector(
                model_path=path, device=self.device
            )
            self._available = True
            self._error = None
            self._load_time_seconds = time.perf_counter() - start
            logger.info(
                "[OMNIPARSER-ADAPTER] Modelo cargado en %s en %.3fs "
                "(disponible=%s)",
                path, self._load_time_seconds, self.device,
            )
        except Exception as exc:  # noqa: BLE001
            self._available = False
            self._detector = None
            self._error = "No se pudo cargar el modelo OmniParser: %s" % exc
            self._load_time_seconds = time.perf_counter() - start
            logger.warning("[OMNIPARSER-ADAPTER] %s", self._error)

    # ------------------------------------------------------------------
    # Deteccion
    # ------------------------------------------------------------------

    def detect(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        screen: int = 0,
    ) -> List[OmniParserRegion]:
        """Detecta regiones interactivas candidatas en ``image``.

        Argumentos:
            image: ruta de archivo, PIL.Image o array numpy (HWC, RGB).
            screen: indice de pantalla asociado a la imagen.

        Retorna:
            Lista de OmniParserRegion ordenada por confianza descendente.
            Devuelve [] si el adaptador no esta disponible.
        """
        if not self._available or self._detector is None:
            logger.debug(
                "[OMNIPARSER-ADAPTER] detect() omitido: no disponible "
                "(%s)", self._error
            )
            return []

        try:
            results = self._detector.predict(
                image,
                conf=self.conf_threshold,
                imgsz=self.img_size,
                iou=self.iou_threshold,
                max_det=self.max_detections,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[OMNIPARSER-ADAPTER] Error durante la inferencia: %s", exc
            )
            return []

        regions: List[OmniParserRegion] = []
        if not results:
            return regions

        result = results[0]
        boxes = result.boxes.xyxy
        confs = result.boxes.conf
        for i in range(len(boxes)):
            box = [int(round(float(v))) for v in boxes[i].tolist()]
            conf = float(confs[i].item())
            regions.append(
                OmniParserRegion(
                    name="",
                    bbox=box,
                    confidence=conf,
                    source="omniparser_v2_icon_detect_v3",
                    model="icon_detect_v3",
                    device=self.device,
                    screen=int(screen),
                    interactive=True,
                    calibrated=False,
                    metadata={
                        "detection_index": i,
                        "width": box[2] - box[0],
                        "height": box[3] - box[1],
                    },
                )
            )

        logger.info(
            "[OMNIPARSER-ADAPTER] %d regiones detectadas "
            "(conf>=%.2f, imgsz=%d, device=%s)",
            len(regions), self.conf_threshold, self.img_size, self.device,
        )
        return regions

    # ------------------------------------------------------------------
    # Informacion de compatibilidad
    # ------------------------------------------------------------------

    def compatibility_info(self) -> Dict[str, Any]:
        """Devuelve datos de compatibilidad del adaptador (no ejecuta el SO)."""
        return {
            "source": "omniparser_v2_icon_detect_v3",
            "model": "icon_detect_v3",
            "repo_id": DEFAULT_REPO_ID,
            "model_file": DEFAULT_MODEL_FILE,
            "license": "MIT",
            "device_requested": self.device,
            "device_effective": self.device,
            "cuda_available": bool(torch.cuda.is_available()),
            "available": self._available,
            "load_time_seconds": self._load_time_seconds,
            "error": self._error,
            "conf_threshold": self.conf_threshold,
            "iou_threshold": self.iou_threshold,
            "max_detections": self.max_detections,
            "img_size": self.img_size,
        }
