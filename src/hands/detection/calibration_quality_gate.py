"""
Puerta de seguridad y calidad de deteccion antes de calibrar o interactuar.

Cubre (referencia de localizacion en el roadmap): 3.8.6.4.3 a 3.8.6.4.7.

Responsabilidades:

* Umbrales por metodo de deteccion (accesibilidad, OmniParser, OCR, OpenCV,
  Qwen3-VL) y por tipo de control canonico (``DetectionThresholds``). Todos los
  umbrales son relativos (confianzas 0..1, IoU, errores de centro como fraccion
  de la diagonal de la caja de referencia, tamanos como fraccion de la
  ventana); nunca pixeles absolutos, para que no dependan de la resolucion ni
  de la escala. Los valores de partida salen de constantes reales del codigo y
  quedan marcados como pendientes de medicion en la fixture
  (``DEFAULT_PROVENANCE``). ``derive_from_measurements`` calcula umbrales desde
  resultados medidos y ``freeze`` los congela: un umbral congelado no se puede
  sobrescribir despues de ver un fallo salvo ``unfreeze`` explicito, que queda
  registrado en el historial.
* Cuatro dimensiones de calidad separadas (``assess_candidate``): confianza de
  deteccion, confianza semantica, evidencia de interactividad y precision
  geometrica. ``QualityAssessment.passed`` exige que pasen las cuatro; ninguna
  puntuacion agregada compensa una dimension insuficiente.
* Decision de accionabilidad (``decide_actionability``): un control
  deshabilitado, fuera de pantalla, cubierto, ambiguo, transitorio, de
  proveedor desconocido, de calidad insuficiente o sin interactividad
  verificada no se calibra como accionable, pero conserva su definicion
  logica (sin coordenadas) cuando tiene identidad util.
* Entorno de interaccion (``check_interaction_environment``): sesion
  bloqueada, escritorio seguro, elevacion/UAC, contenido o ventana protegidos,
  overlays, ventana minimizada/oculta y permisos, siempre via el contrato de
  plataforma. Nunca intenta eludirlos; devuelve motivos concretos.
* Deriva entre deteccion y accion (``take_detection_snapshot`` y
  ``verify_before_action``): PID/ventana, foco, monitor, escala/DPI,
  resolucion/topologia, geometria de ventana, caja del control, estado UI y
  antiguedad. Ante cualquier cambio se indica ``recapture`` o ``recalibrate``;
  nunca se reutiliza la deteccion anterior.

Este modulo no captura pantalla, no mueve el puntero ni envia entradas: solo
evalua evidencia ya obtenida y consulta el estado del SO a traves de
``src.desktop.platform_contract.DesktopPlatformAdapter`` (inyectable).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.core.config import get_project_root
from src.core.log import get_logger
from src.core.ui_element_model import ElementClassification
from src.desktop.platform_contract import (
    DesktopPlatformAdapter,
    DisplayInfo,
    PlatformErrorCode,
    Rect,
    WindowInfo,
)

logger = get_logger(__name__)


# ============================================================================
# CONSTANTES DE ORIGEN (valores de partida reales del codigo)
# ============================================================================

# Constantes reales usadas como valores de partida. Se replican aqui como
# literales para no importar en tiempo de carga modulos pesados (torch,
# onnxruntime, Ollama); su procedencia queda documentada en
# DEFAULT_PROVENANCE.
_QWEN_POLICY_MIN_CONFIDENCE = 0.30      # CalibrationPolicy.MIN_ELEMENT_CONFIDENCE
_OMNIPARSER_CONF_THRESHOLD = 0.25       # OmniParserAdapter(conf_threshold=0.25)
_PADDLEOCR_TEXT_SCORE_THRESH = 0.5      # PaddleOCRAdapter(text_score_thresh=0.5)
_AMBIGUOUS_IOU = 0.30                   # window_evidence_validator.IOU_SOLAPAMIENTO_AMBIGUO
_FUSION_GEOMETRY_DISAGREEMENT_IOU = 0.15  # VisualUIDetectorFusion._merge_cluster
_VISION_COORD_TOLERANCE = 0.10          # Vision._coordinates_match(tolerance=0.10)

DEFAULT_THRESHOLDS_PATH = Path(get_project_root()) / "config" / "detection_thresholds.json"

THRESHOLDS_FORMAT_VERSION = 1
WILDCARD_CONTROL_TYPE = "*"
MEASUREMENT_STATUS_PENDING = "PENDIENTE_MEDICION"
MEASUREMENT_STATUS_MEASURED = "MEDIDO"
MIN_SAMPLES_FOR_DERIVATION = 5

DEFAULT_PROVENANCE: Dict[str, str] = {
    "accessibility.min_detection_confidence": "0.30 <- CalibrationPolicy.MIN_ELEMENT_CONFIDENCE (pendiente de medicion)",
    "omniparser.min_detection_confidence": "0.25 <- OmniParserAdapter.conf_threshold (pendiente de medicion)",
    "ocr.min_detection_confidence": "0.50 <- PaddleOCRAdapter.text_score_thresh (pendiente de medicion)",
    "qwen3vl.min_detection_confidence": "0.30 <- CalibrationPolicy.MIN_ELEMENT_CONFIDENCE (pendiente de medicion)",
    "opencv.min_detection_confidence": "no detecta por si sola: solo pista geometrica (contrato de la fusion)",
    "*.min_semantic_confidence": "0.30 <- CalibrationPolicy.MIN_ELEMENT_CONFIDENCE (pendiente de medicion)",
    "*.max_ambiguous_iou": "0.30 <- IOU_SOLAPAMIENTO_AMBIGUO / IOU_MERGE_THRESHOLD (pendiente de medicion)",
    "*.min_iou_with_reference": "0.15 <- umbral de desacuerdo geometrico de la fusion (pendiente de medicion)",
    "*.max_center_error_ratio": "0.10 <- tolerancia relativa de Vision._coordinates_match (pendiente de medicion)",
    "*.min_box_size_ratio": "0.0 desactivado hasta medir en la fixture (sin valor real previo)",
}


class ThresholdsFrozenError(RuntimeError):
    """Se intento modificar o sobrescribir umbrales congelados."""


class ThresholdsIntegrityError(RuntimeError):
    """El fichero de umbrales congelados no coincide con su huella."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# METODOS DE DETECCION
# ============================================================================


class DetectionMethod(str, Enum):
    """Metodo/fuente de deteccion de un candidato."""

    ACCESSIBILITY = "accessibility"
    OMNIPARSER = "omniparser"
    OCR = "ocr"
    OPENCV = "opencv"
    QWEN3VL = "qwen3vl"

    @classmethod
    def from_source(cls, source: Any) -> Optional["DetectionMethod"]:
        """Mapea el nombre de fuente de la fusion (SOURCE_*) o del arbol AX.

        Devuelve ``None`` para fuentes desconocidas (proveedor desconocido).
        """
        if isinstance(source, DetectionMethod):
            return source
        key = str(source or "").strip().lower()
        if not key:
            return None
        return _SOURCE_TO_METHOD.get(key)

    @property
    def can_detect_alone(self) -> bool:
        """OpenCV solo aporta pistas geometricas; nunca acredita una deteccion."""
        return self is not DetectionMethod.OPENCV


_SOURCE_TO_METHOD: Dict[str, DetectionMethod] = {
    # Constantes de src.eyes.detection.visual_ui_detector_fusion
    "uia": DetectionMethod.ACCESSIBILITY,
    "omniparser_v2_icon_detect_v3": DetectionMethod.OMNIPARSER,
    "paddleocr": DetectionMethod.OCR,
    "qwen3vl": DetectionMethod.QWEN3VL,
    "opencv": DetectionMethod.OPENCV,
    # Arbol AX de macOS y alias de nombre del propio metodo
    "ax": DetectionMethod.ACCESSIBILITY,
    "accessibility": DetectionMethod.ACCESSIBILITY,
    "omniparser": DetectionMethod.OMNIPARSER,
    "ocr": DetectionMethod.OCR,
}


# ============================================================================
# UMBRALES
# ============================================================================


@dataclass
class MethodThresholds:
    """Umbrales de un metodo (y tipo de control). Todos relativos.

    Atributos:
        min_detection_confidence: confianza minima de la fuente (0..1).
            ``> 1.0`` significa que el metodo no puede acreditar deteccion solo.
        min_semantic_confidence: confianza minima de la identidad (nombre,
            etiqueta OCR, funcion aparente de Qwen3-VL) (0..1).
        max_center_error_ratio: error maximo entre el centro de la caja final y
            el de la referencia, como fraccion de la diagonal de la referencia.
        min_iou_with_reference: IoU minimo entre la caja final y la referencia.
        max_ambiguous_iou: IoU por encima del cual el solapamiento con un
            candidato de identidad distinta se considera ambiguo.
        min_box_size_ratio: lado minimo de la caja como fraccion del lado menor
            de la ventana (0.0 = desactivado).
    """

    min_detection_confidence: float = _QWEN_POLICY_MIN_CONFIDENCE
    min_semantic_confidence: float = _QWEN_POLICY_MIN_CONFIDENCE
    max_center_error_ratio: float = _VISION_COORD_TOLERANCE
    min_iou_with_reference: float = _FUSION_GEOMETRY_DISAGREEMENT_IOU
    max_ambiguous_iou: float = _AMBIGUOUS_IOU
    min_box_size_ratio: float = 0.0
    status: str = MEASUREMENT_STATUS_PENDING
    samples: int = 0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_detection_confidence": float(self.min_detection_confidence),
            "min_semantic_confidence": float(self.min_semantic_confidence),
            "max_center_error_ratio": float(self.max_center_error_ratio),
            "min_iou_with_reference": float(self.min_iou_with_reference),
            "max_ambiguous_iou": float(self.max_ambiguous_iou),
            "min_box_size_ratio": float(self.min_box_size_ratio),
            "status": self.status,
            "samples": int(self.samples),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MethodThresholds":
        base = cls()
        for key in (
            "min_detection_confidence",
            "min_semantic_confidence",
            "max_center_error_ratio",
            "min_iou_with_reference",
            "max_ambiguous_iou",
            "min_box_size_ratio",
        ):
            if key in data and data[key] is not None:
                setattr(base, key, float(data[key]))
        base.status = str(data.get("status", MEASUREMENT_STATUS_PENDING))
        base.samples = int(data.get("samples", 0) or 0)
        base.notes = str(data.get("notes", "") or "")
        return base


def _default_table() -> Dict[str, Dict[str, MethodThresholds]]:
    return {
        DetectionMethod.ACCESSIBILITY.value: {
            WILDCARD_CONTROL_TYPE: MethodThresholds(
                min_detection_confidence=_QWEN_POLICY_MIN_CONFIDENCE,
                notes=DEFAULT_PROVENANCE["accessibility.min_detection_confidence"],
            )
        },
        DetectionMethod.OMNIPARSER.value: {
            WILDCARD_CONTROL_TYPE: MethodThresholds(
                min_detection_confidence=_OMNIPARSER_CONF_THRESHOLD,
                notes=DEFAULT_PROVENANCE["omniparser.min_detection_confidence"],
            )
        },
        DetectionMethod.OCR.value: {
            WILDCARD_CONTROL_TYPE: MethodThresholds(
                min_detection_confidence=_PADDLEOCR_TEXT_SCORE_THRESH,
                min_semantic_confidence=_PADDLEOCR_TEXT_SCORE_THRESH,
                notes=DEFAULT_PROVENANCE["ocr.min_detection_confidence"],
            )
        },
        DetectionMethod.OPENCV.value: {
            WILDCARD_CONTROL_TYPE: MethodThresholds(
                min_detection_confidence=1.01,
                min_semantic_confidence=1.01,
                notes=DEFAULT_PROVENANCE["opencv.min_detection_confidence"],
            )
        },
        DetectionMethod.QWEN3VL.value: {
            WILDCARD_CONTROL_TYPE: MethodThresholds(
                min_detection_confidence=_QWEN_POLICY_MIN_CONFIDENCE,
                notes=DEFAULT_PROVENANCE["qwen3vl.min_detection_confidence"],
            )
        },
    }


def _quantile(values: Sequence[float], q: float) -> float:
    """Cuantil con interpolacion lineal (q en 0..1). ``values`` no vacio."""
    data = sorted(float(v) for v in values)
    if len(data) == 1:
        return data[0]
    q = min(1.0, max(0.0, float(q)))
    pos = q * (len(data) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return data[low]
    return data[low] + (data[high] - data[low]) * (pos - low)


class DetectionThresholds:
    """Tabla de umbrales por metodo y tipo de control, con congelado.

    ``get(method, control_type)`` busca primero el tipo concreto y despues el
    comodin ``"*"`` del metodo. La huella (``fingerprint``) cubre solo los
    valores de los umbrales: sirve para detectar cambios tras congelar.
    """

    def __init__(
        self,
        table: Optional[Dict[str, Dict[str, MethodThresholds]]] = None,
        source: str = "defaults",
    ) -> None:
        self._table: Dict[str, Dict[str, MethodThresholds]] = table or _default_table()
        self.source = source
        self.frozen = False
        self.frozen_at: Optional[str] = None
        self.frozen_reason: str = ""
        self.frozen_fingerprint: Optional[str] = None
        self.history: List[Dict[str, Any]] = []
        self.measurement_info: Dict[str, Any] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Construccion
    # ------------------------------------------------------------------

    @classmethod
    def defaults(cls) -> "DetectionThresholds":
        """Valores de partida (constantes reales del codigo, pendientes de medicion)."""
        return cls(_default_table(), source="defaults")

    @classmethod
    def derive_from_measurements(
        cls,
        measurements: Iterable[Dict[str, Any]],
        tp_quantile: float = 0.05,
        min_samples: int = MIN_SAMPLES_FOR_DERIVATION,
    ) -> "DetectionThresholds":
        """Deriva umbrales desde resultados medidos en la fixture.

        Cada medicion es un dict con: ``method`` (fuente o DetectionMethod),
        ``control_type`` (tipo canonico, opcional), ``confidence``,
        ``semantic_confidence`` (opcional), ``iou`` (con la verdad-terreno,
        opcional), ``center_error_ratio`` (opcional) e ``is_true_positive``.

        Para cada grupo (metodo, tipo) y para (metodo, ``"*"``):

        * confianza minima = cuantil ``tp_quantile`` de los verdaderos
          positivos, elevada por encima del mayor falso positivo cuando eso no
          deja fuera a todos los verdaderos positivos (si se solapan, se
          registra ``overlap`` en las notas);
        * IoU minimo = cuantil ``tp_quantile`` de los IoU de verdaderos
          positivos; error de centro maximo = cuantil ``1 - tp_quantile``.

        Un grupo con menos de ``min_samples`` verdaderos positivos conserva el
        valor de partida y queda marcado como pendiente.
        """
        rows = list(measurements or [])
        derived = cls.defaults()
        derived.source = "measured"
        groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        skipped = 0
        for row in rows:
            method = DetectionMethod.from_source(row.get("method"))
            if method is None:
                skipped += 1
                continue
            ctype = str(row.get("control_type") or WILDCARD_CONTROL_TYPE)
            groups.setdefault((method.value, ctype), []).append(row)
            if ctype != WILDCARD_CONTROL_TYPE:
                groups.setdefault((method.value, WILDCARD_CONTROL_TYPE), []).append(row)

        info: Dict[str, Any] = {
            "derived_at": _now_iso(),
            "tp_quantile": tp_quantile,
            "min_samples": min_samples,
            "rows": len(rows),
            "rows_unknown_method": skipped,
            "groups": {},
        }
        for (method_value, ctype), group in sorted(groups.items()):
            base = copy.deepcopy(derived._lookup(method_value, ctype))
            tps = [r for r in group if bool(r.get("is_true_positive"))]
            fps = [r for r in group if not bool(r.get("is_true_positive"))]
            group_info = {"true_positives": len(tps), "false_positives": len(fps)}
            if len(tps) < min_samples:
                base.status = MEASUREMENT_STATUS_PENDING
                base.samples = len(tps)
                base.notes = "muestras insuficientes (%d < %d); se conserva el valor de partida" % (
                    len(tps), min_samples)
                group_info["status"] = MEASUREMENT_STATUS_PENDING
                derived._table.setdefault(method_value, {})[ctype] = base
                info["groups"]["%s/%s" % (method_value, ctype)] = group_info
                continue
            notes: List[str] = []
            if method_value != DetectionMethod.OPENCV.value:
                base.min_detection_confidence = cls._threshold_separating(
                    [float(r.get("confidence", 0.0) or 0.0) for r in tps],
                    [float(r.get("confidence", 0.0) or 0.0) for r in fps],
                    tp_quantile, notes, "deteccion",
                )
                sem_tp = [float(r["semantic_confidence"]) for r in tps if r.get("semantic_confidence") is not None]
                sem_fp = [float(r["semantic_confidence"]) for r in fps if r.get("semantic_confidence") is not None]
                if len(sem_tp) >= min_samples:
                    base.min_semantic_confidence = cls._threshold_separating(
                        sem_tp, sem_fp, tp_quantile, notes, "semantica",
                    )
            ious = [float(r["iou"]) for r in tps if r.get("iou") is not None]
            if len(ious) >= min_samples:
                base.min_iou_with_reference = round(_quantile(ious, tp_quantile), 4)
            errors = [float(r["center_error_ratio"]) for r in tps if r.get("center_error_ratio") is not None]
            if len(errors) >= min_samples:
                base.max_center_error_ratio = round(_quantile(errors, 1.0 - tp_quantile), 4)
            base.status = MEASUREMENT_STATUS_MEASURED
            base.samples = len(tps)
            base.notes = "; ".join(notes) if notes else "derivado de mediciones"
            group_info["status"] = MEASUREMENT_STATUS_MEASURED
            group_info["notes"] = base.notes
            derived._table.setdefault(method_value, {})[ctype] = base
            info["groups"]["%s/%s" % (method_value, ctype)] = group_info
        derived.measurement_info = info
        return derived

    @staticmethod
    def _threshold_separating(
        tp_values: List[float],
        fp_values: List[float],
        tp_quantile: float,
        notes: List[str],
        label: str,
    ) -> float:
        threshold = _quantile(tp_values, tp_quantile)
        if fp_values:
            max_fp = max(fp_values)
            above_fp = max_fp + 1e-6
            if above_fp <= max(tp_values):
                if above_fp > threshold:
                    threshold = above_fp
                    notes.append("%s elevado sobre el mayor falso positivo" % label)
            else:
                notes.append("overlap %s: falsos positivos con confianza >= verdaderos positivos" % label)
        return round(float(threshold), 6)

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    def _lookup(self, method_value: str, control_type: Optional[str]) -> MethodThresholds:
        by_type = self._table.get(method_value) or {}
        if control_type and control_type in by_type:
            return by_type[control_type]
        if WILDCARD_CONTROL_TYPE in by_type:
            return by_type[WILDCARD_CONTROL_TYPE]
        return MethodThresholds(notes="metodo sin umbrales definidos; valores de partida genericos")

    def get(self, method: Any, control_type: Optional[str] = None) -> MethodThresholds:
        """Umbrales del metodo para un tipo de control (con fallback a ``"*"``).

        Devuelve una copia: modificarla no altera la tabla.
        """
        resolved = DetectionMethod.from_source(method)
        method_value = resolved.value if resolved else str(method or "")
        return copy.deepcopy(self._lookup(method_value, control_type))

    def ambiguous_iou(self, control_type: Optional[str] = None) -> float:
        """IoU de ambiguedad mas estricto entre metodos para un tipo de control."""
        values = [self._lookup(m.value, control_type).max_ambiguous_iou for m in DetectionMethod]
        return min(values) if values else _AMBIGUOUS_IOU

    def set(self, method: Any, control_type: str, thresholds: MethodThresholds) -> None:
        """Fija umbrales; prohibido si la tabla esta congelada."""
        if self.frozen:
            raise ThresholdsFrozenError(
                "Los umbrales estan congelados (%s); no se pueden cambiar tras ver resultados"
                % self.frozen_reason
            )
        resolved = DetectionMethod.from_source(method)
        if resolved is None:
            raise ValueError("Metodo de deteccion desconocido: %r" % (method,))
        with self._lock:
            self._table.setdefault(resolved.value, {})[control_type or WILDCARD_CONTROL_TYPE] = copy.deepcopy(thresholds)

    # ------------------------------------------------------------------
    # Congelado
    # ------------------------------------------------------------------

    def fingerprint(self) -> str:
        """Huella sha256 de los valores numericos de todos los umbrales."""
        canonical = {}
        for method_value in sorted(self._table):
            canonical[method_value] = {}
            for ctype in sorted(self._table[method_value]):
                t = self._table[method_value][ctype]
                canonical[method_value][ctype] = [
                    round(float(t.min_detection_confidence), 6),
                    round(float(t.min_semantic_confidence), 6),
                    round(float(t.max_center_error_ratio), 6),
                    round(float(t.min_iou_with_reference), 6),
                    round(float(t.max_ambiguous_iou), 6),
                    round(float(t.min_box_size_ratio), 6),
                ]
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("ascii")).hexdigest()

    @property
    def is_frozen(self) -> bool:
        return bool(self.frozen)

    def freeze(self, reason: str) -> str:
        """Congela los umbrales antes de la aceptacion. Devuelve la huella."""
        if not str(reason or "").strip():
            raise ValueError("freeze() exige un motivo explicito")
        self.frozen = True
        self.frozen_at = _now_iso()
        self.frozen_reason = str(reason)
        self.frozen_fingerprint = self.fingerprint()
        self.history.append({
            "event": "freeze",
            "at": self.frozen_at,
            "reason": self.frozen_reason,
            "fingerprint": self.frozen_fingerprint,
        })
        logger.info("Umbrales de deteccion congelados: %s", self.frozen_reason)
        return self.frozen_fingerprint

    def unfreeze(self, reason: str) -> None:
        """Descongela de forma explicita y registrada (nunca implicita)."""
        if not str(reason or "").strip():
            raise ValueError("unfreeze() exige un motivo explicito")
        self.history.append({
            "event": "unfreeze",
            "at": _now_iso(),
            "reason": str(reason),
            "fingerprint": self.frozen_fingerprint,
        })
        logger.warning("Umbrales de deteccion descongelados: %s", reason)
        self.frozen = False
        self.frozen_at = None
        self.frozen_reason = ""
        self.frozen_fingerprint = None

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": THRESHOLDS_FORMAT_VERSION,
            "units": "relative",
            "source": self.source,
            "frozen": bool(self.frozen),
            "frozen_at": self.frozen_at,
            "frozen_reason": self.frozen_reason,
            "fingerprint": self.frozen_fingerprint if self.frozen else self.fingerprint(),
            "measurement_info": dict(self.measurement_info),
            "history": list(self.history),
            "thresholds": {
                method_value: {ctype: t.to_dict() for ctype, t in by_type.items()}
                for method_value, by_type in self._table.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: str = "file") -> "DetectionThresholds":
        table: Dict[str, Dict[str, MethodThresholds]] = _default_table()
        for method_value, by_type in (data.get("thresholds") or {}).items():
            resolved = DetectionMethod.from_source(method_value)
            if resolved is None:
                logger.warning("Metodo desconocido ignorado en umbrales: %s", method_value)
                continue
            for ctype, values in (by_type or {}).items():
                table.setdefault(resolved.value, {})[str(ctype)] = MethodThresholds.from_dict(values or {})
        result = cls(table, source=source)
        result.measurement_info = dict(data.get("measurement_info") or {})
        result.history = list(data.get("history") or [])
        if data.get("frozen"):
            stored = str(data.get("fingerprint") or "")
            computed = result.fingerprint()
            if stored != computed:
                raise ThresholdsIntegrityError(
                    "Los umbrales congelados no coinciden con su huella (almacenada=%s, calculada=%s)"
                    % (stored[:12], computed[:12])
                )
            result.frozen = True
            result.frozen_at = data.get("frozen_at")
            result.frozen_reason = str(data.get("frozen_reason") or "")
            result.frozen_fingerprint = stored
        return result

    @classmethod
    def load(cls, path: Optional[Any] = None) -> "DetectionThresholds":
        """Carga el fichero de umbrales; si no existe devuelve los valores de partida.

        Nunca crea el fichero. Un fichero ilegible se registra y se usan los
        valores de partida; un fichero congelado alterado levanta
        ``ThresholdsIntegrityError`` (no se usa en silencio).
        """
        target = Path(path) if path else DEFAULT_THRESHOLDS_PATH
        if not target.exists():
            return cls.defaults()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("No se pudo leer %s; se usan umbrales de partida: %s", target.name, exc)
            return cls.defaults()
        return cls.from_dict(data, source=str(target))

    def save(self, path: Optional[Any] = None) -> Path:
        """Guarda la tabla de forma atomica.

        Falla con ``ThresholdsFrozenError`` si el fichero destino contiene
        umbrales congelados distintos de los actuales (no se sobrescriben
        umbrales fijados antes de la aceptacion).
        """
        target = Path(path) if path else DEFAULT_THRESHOLDS_PATH
        if target.exists():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ThresholdsFrozenError(
                    "No se puede verificar el fichero de umbrales existente; no se sobrescribe: %s" % exc
                )
            if existing.get("frozen") and str(existing.get("fingerprint") or "") != self.fingerprint():
                raise ThresholdsFrozenError(
                    "El fichero contiene umbrales congelados distintos; descongelar de forma explicita antes"
                )
        if self.frozen and self.frozen_fingerprint != self.fingerprint():
            raise ThresholdsFrozenError("La tabla congelada fue modificada despues de congelarse")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(str(tmp), str(target))
        return target


_ACTIVE_LOCK = threading.Lock()
_ACTIVE_THRESHOLDS: Optional[DetectionThresholds] = None


def get_active_thresholds() -> DetectionThresholds:
    """Umbrales activos del proceso (fichero de configuracion o valores de partida)."""
    global _ACTIVE_THRESHOLDS
    if _ACTIVE_THRESHOLDS is not None:
        return _ACTIVE_THRESHOLDS
    with _ACTIVE_LOCK:
        if _ACTIVE_THRESHOLDS is None:
            try:
                _ACTIVE_THRESHOLDS = DetectionThresholds.load()
            except ThresholdsIntegrityError:
                logger.exception("Umbrales congelados alterados; se usan los valores de partida")
                _ACTIVE_THRESHOLDS = DetectionThresholds.defaults()
        return _ACTIVE_THRESHOLDS


def set_active_thresholds(thresholds: Optional[DetectionThresholds]) -> None:
    """Fija (o borra con ``None``) los umbrales activos. Uso: inyeccion/tests."""
    global _ACTIVE_THRESHOLDS
    with _ACTIVE_LOCK:
        _ACTIVE_THRESHOLDS = thresholds


# ============================================================================
# ACCESO A CANDIDATOS (FusedCandidate o dict equivalente)
# ============================================================================


ACTIONABLE_ACCESSIBILITY_PATTERNS = frozenset({
    "Invoke", "Value", "Toggle", "Selection", "ExpandCollapse",
    "Scroll", "Window", "Transform", "SelectionItem",
})


@dataclass
class _Source:
    method: Optional[DetectionMethod]
    raw_source: str
    confidence: float
    bbox: Optional[Rect]
    raw: Dict[str, Any]
    element: Any


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _rect_of(value: Any) -> Optional[Rect]:
    rect = Rect.from_any(value)
    if rect is None or not rect.is_valid():
        return None
    return rect


def _candidate_sources(candidate: Any) -> List[_Source]:
    result: List[_Source] = []
    for ev in list(_get(candidate, "sources", None) or []):
        raw_source = str(_get(ev, "source", "") or "")
        try:
            confidence = float(_get(ev, "confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if _get(ev, "available", True) is False:
            continue
        result.append(_Source(
            method=DetectionMethod.from_source(raw_source),
            raw_source=raw_source,
            confidence=confidence,
            bbox=_rect_of(_get(ev, "bbox", None)),
            raw=dict(_get(ev, "raw", None) or {}),
            element=_get(ev, "element", None),
        ))
    return result


def _candidate_id(candidate: Any) -> str:
    return str(
        _get(candidate, "canonical_id", None)
        or _get(candidate, "node_id", None)
        or _get(candidate, "name", None)
        or "desconocido"
    )


def _classification_value(candidate: Any) -> str:
    value = _get(candidate, "classification", None)
    if isinstance(value, Enum):
        return str(value.value)
    return str(value or "")


def _accessibility_flags(sources: List[_Source]) -> Dict[str, Optional[bool]]:
    """Estado del control segun la fuente de accesibilidad (si existe)."""
    flags: Dict[str, Optional[bool]] = {"enabled": None, "visible": None, "offscreen": None}
    for src in sources:
        if src.method is not DetectionMethod.ACCESSIBILITY:
            continue
        raw = src.raw
        if "is_enabled" in raw:
            flags["enabled"] = bool(raw.get("is_enabled"))
        elif "enabled" in raw:
            flags["enabled"] = bool(raw.get("enabled"))
        elif src.element is not None and _get(src.element, "interactive", None) is not None:
            # En la fusion, element.interactive de UIA refleja IsEnabled.
            flags["enabled"] = bool(_get(src.element, "interactive", None))
        if "visible" in raw:
            flags["visible"] = bool(raw.get("visible"))
        if "is_offscreen" in raw:
            flags["offscreen"] = bool(raw.get("is_offscreen"))
        elif "offscreen" in raw:
            flags["offscreen"] = bool(raw.get("offscreen"))
    return flags


def _accessibility_patterns(sources: List[_Source]) -> List[str]:
    patterns: List[str] = []
    for src in sources:
        if src.method is not DetectionMethod.ACCESSIBILITY:
            continue
        for key in ("patterns", "native_patterns", "equivalent_patterns"):
            for p in src.raw.get(key, []) or []:
                if str(p) not in patterns:
                    patterns.append(str(p))
        for action in src.raw.get("actions", []) or []:
            mapped = _ACTION_EQUIVALENT_PATTERN.get(str(action))
            if mapped and mapped not in patterns:
                patterns.append(mapped)
    return patterns


_ACTION_EQUIVALENT_PATTERN = {
    "invoke": "Invoke",
    "toggle": "Toggle",
    "expand": "ExpandCollapse",
    "collapse": "ExpandCollapse",
    "select": "SelectionItem",
    "set_value": "Value",
    "scroll": "Scroll",
    "show_menu": "ExpandCollapse",
}


def _center_error_ratio(box: Rect, reference: Rect) -> float:
    cx, cy = box.center
    rx, ry = reference.center
    diag = math.hypot(reference.width, reference.height)
    if diag <= 0:
        return float("inf")
    return math.hypot(cx - rx, cy - ry) / diag


# ============================================================================
# EVALUACION DE CALIDAD (cuatro dimensiones separadas)
# ============================================================================

DIM_DETECTION = "detection_confidence"
DIM_SEMANTIC = "semantic_confidence"
DIM_INTERACTIVITY = "interactivity_evidence"
DIM_GEOMETRY = "geometric_precision"
ALL_DIMENSIONS = (DIM_DETECTION, DIM_SEMANTIC, DIM_INTERACTIVITY, DIM_GEOMETRY)

INTERACTIVITY_ACCESSIBILITY = "accessibility_pattern"
INTERACTIVITY_CONTROLLED_PROOF = "controlled_proof"
INTERACTIVITY_VISUAL_CANDIDATE = "visual_candidate"
INTERACTIVITY_NONE = "none"


@dataclass
class DimensionResult:
    """Resultado de una dimension de calidad (independiente de las demas)."""

    name: str
    value: Any
    threshold: Any
    passed: bool
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "threshold": self.threshold,
            "passed": bool(self.passed),
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass
class QualityAssessment:
    """Evaluacion por dimensiones. ``passed`` exige que pasen las cuatro."""

    passed: bool
    dimensions: Dict[str, DimensionResult] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    candidate_id: str = ""
    control_type: str = ""

    def dimension_passed(self, name: str) -> bool:
        dim = self.dimensions.get(name)
        return bool(dim and dim.passed)

    @property
    def detected_ok(self) -> bool:
        """Deteccion, semantica y geometria suficientes (sin exigir interactividad).

        Permite persistir el control como candidato/detectado sin habilitarlo
        para la accion.
        """
        return all(self.dimension_passed(d) for d in (DIM_DETECTION, DIM_SEMANTIC, DIM_GEOMETRY))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "detected_ok": self.detected_ok,
            "candidate_id": self.candidate_id,
            "control_type": self.control_type,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "reasons": list(self.reasons),
        }


def _assess_detection(
    sources: List[_Source], thresholds: DetectionThresholds, control_type: Optional[str]
) -> DimensionResult:
    per_source: List[Dict[str, Any]] = []
    best: Optional[Tuple[float, str, float]] = None
    for src in sources:
        if src.method is None:
            per_source.append({"source": src.raw_source, "passed": False, "reason": "proveedor desconocido"})
            continue
        thr = thresholds.get(src.method, control_type)
        ok = src.method.can_detect_alone and src.confidence >= thr.min_detection_confidence
        per_source.append({
            "source": src.raw_source,
            "method": src.method.value,
            "confidence": src.confidence,
            "threshold": thr.min_detection_confidence,
            "passed": ok,
        })
        if ok and (best is None or src.confidence > best[0]):
            best = (src.confidence, src.method.value, thr.min_detection_confidence)
    if best is None:
        reason = (
            "ninguna fuente supera su umbral de confianza de deteccion"
            if sources else "candidato sin fuentes de deteccion"
        )
        return DimensionResult(DIM_DETECTION, None, None, False, reason, {"sources": per_source})
    return DimensionResult(
        DIM_DETECTION, best[0], best[2], True,
        "fuente %s supera su umbral" % best[1], {"sources": per_source},
    )


def _assess_semantic(
    candidate: Any, sources: List[_Source], thresholds: DetectionThresholds, control_type: Optional[str]
) -> DimensionResult:
    evidence: List[Dict[str, Any]] = []
    best: Optional[Tuple[float, str, float]] = None
    for src in sources:
        if src.method is None:
            continue
        value: Optional[float] = None
        if src.method is DetectionMethod.ACCESSIBILITY:
            name = str(src.raw.get("name") or src.raw.get("automation_id") or src.raw.get("identifier")
                       or _get(src.element, "name", "") or "").strip()
            value = 1.0 if name else 0.0
        elif src.method is DetectionMethod.OCR:
            text = str(src.raw.get("text") or _get(src.element, "text", "") or "").strip()
            value = src.confidence if text else 0.0
        elif src.method is DetectionMethod.QWEN3VL:
            has_semantics = bool(
                src.raw.get("label_association") or src.raw.get("apparent_function")
                or _get(src.element, "description", "") or _get(src.element, "name", "")
            )
            value = src.confidence if has_semantics else 0.0
        if value is None:
            continue
        thr = thresholds.get(src.method, control_type).min_semantic_confidence
        ok = value >= thr
        evidence.append({"method": src.method.value, "value": value, "threshold": thr, "passed": ok})
        if ok and (best is None or value > best[0]):
            best = (value, src.method.value, thr)
    if best is None:
        return DimensionResult(
            DIM_SEMANTIC, None, None, False,
            "sin identidad semantica suficiente (nombre, etiqueta o funcion)",
            {"evidence": evidence, "name": str(_get(candidate, "name", "") or "")},
        )
    return DimensionResult(
        DIM_SEMANTIC, best[0], best[2], True,
        "identidad aportada por %s" % best[1], {"evidence": evidence},
    )


def _assess_interactivity(
    candidate: Any, sources: List[_Source], interaction_proof: Optional[Dict[str, Any]]
) -> DimensionResult:
    flags = _accessibility_flags(sources)
    patterns = _accessibility_patterns(sources)
    actionable_patterns = sorted(set(patterns) & ACTIONABLE_ACCESSIBILITY_PATTERNS)
    classification = _classification_value(candidate)
    usable_state = (
        flags["enabled"] is not False
        and flags["visible"] is not False
        and flags["offscreen"] is not True
    )
    details = {
        "patterns": patterns,
        "actionable_patterns": actionable_patterns,
        "flags": dict(flags),
        "classification": classification,
    }
    if (actionable_patterns or classification == ElementClassification.UIA_ACTIONABLE.value) and usable_state:
        return DimensionResult(
            DIM_INTERACTIVITY, INTERACTIVITY_ACCESSIBILITY, INTERACTIVITY_ACCESSIBILITY, True,
            "patron de accesibilidad utilizable en un control habilitado y visible", details,
        )
    if interaction_proof and interaction_proof.get("verified"):
        details["proof"] = {k: v for k, v in interaction_proof.items() if k != "image"}
        return DimensionResult(
            DIM_INTERACTIVITY, INTERACTIVITY_CONTROLLED_PROOF, INTERACTIVITY_ACCESSIBILITY, True,
            "interactividad demostrada por prueba controlada sobre el propio control", details,
        )
    visual = bool(_get(candidate, "interactive", False)) or any(
        s.method in (DetectionMethod.OMNIPARSER, DetectionMethod.QWEN3VL) for s in sources
    )
    value = INTERACTIVITY_VISUAL_CANDIDATE if visual else INTERACTIVITY_NONE
    if actionable_patterns and not usable_state:
        reason = "patron de accion presente pero control deshabilitado, oculto o fuera de pantalla"
    elif visual:
        reason = "solo evidencia visual: candidato sin interactividad verificada"
    else:
        reason = "sin evidencia de interactividad"
    return DimensionResult(DIM_INTERACTIVITY, value, INTERACTIVITY_ACCESSIBILITY, False, reason, details)


def _assess_geometry(
    candidate: Any,
    sources: List[_Source],
    thresholds: DetectionThresholds,
    control_type: Optional[str],
    window_rect: Optional[Rect],
    reference_box: Optional[Rect],
) -> DimensionResult:
    box = _rect_of(_get(candidate, "bbox", None))
    details: Dict[str, Any] = {"box": box.to_dict() if box else None}
    # Umbral mas estricto entre los metodos que aportan la caja.
    methods = [s.method for s in sources if s.method is not None] or [DetectionMethod.ACCESSIBILITY]
    thr_list = [thresholds.get(m, control_type) for m in methods]
    max_center = min(t.max_center_error_ratio for t in thr_list)
    min_iou = max(t.min_iou_with_reference for t in thr_list)
    min_size = max(t.min_box_size_ratio for t in thr_list)
    threshold = {"max_center_error_ratio": max_center, "min_iou_with_reference": min_iou,
                 "min_box_size_ratio": min_size}
    if box is None:
        return DimensionResult(DIM_GEOMETRY, None, threshold, False, "caja vacia o degenerada", details)
    if window_rect is not None:
        if not window_rect.contains_rect(box):
            return DimensionResult(
                DIM_GEOMETRY, None, threshold, False,
                "caja truncada o fuera de la ventana objetivo", details,
            )
        if min_size > 0:
            side = min(box.width, box.height)
            ref_side = max(1.0, min(window_rect.width, window_rect.height))
            ratio = side / ref_side
            details["box_size_ratio"] = ratio
            if ratio < min_size:
                return DimensionResult(
                    DIM_GEOMETRY, ratio, threshold, False,
                    "caja demasiado pequena respecto a la ventana", details,
                )

    references: List[Tuple[str, Rect]] = []
    if reference_box is not None:
        references.append(("reference", reference_box))
    for src in sources:
        if src.bbox is None:
            continue
        if src.method is DetectionMethod.ACCESSIBILITY:
            references.append(("accessibility", src.bbox))
    if not references:
        independent = [s for s in sources if s.bbox is not None and s.method is not None]
        if len(independent) >= 2:
            references.extend((s.method.value, s.bbox) for s in independent)  # type: ignore[union-attr]
    if not references:
        return DimensionResult(
            DIM_GEOMETRY, None, threshold, False,
            "precision geometrica no verificable con una sola fuente visual", details,
        )
    worst_center = 0.0
    worst_iou = 1.0
    for label, ref in references:
        worst_center = max(worst_center, _center_error_ratio(box, ref))
        worst_iou = min(worst_iou, box.iou(ref))
    details["references"] = [label for label, _ in references]
    details["center_error_ratio"] = worst_center
    details["iou_with_reference"] = worst_iou
    value = {"center_error_ratio": round(worst_center, 6), "iou_with_reference": round(worst_iou, 6)}
    if worst_center > max_center:
        return DimensionResult(DIM_GEOMETRY, value, threshold, False,
                               "error de centro superior al umbral relativo", details)
    if worst_iou < min_iou:
        return DimensionResult(DIM_GEOMETRY, value, threshold, False,
                               "solapamiento con la referencia inferior al umbral", details)
    return DimensionResult(DIM_GEOMETRY, value, threshold, True, "geometria consistente con la referencia", details)


def assess_candidate(
    candidate: Any,
    thresholds: Optional[DetectionThresholds] = None,
    window_rect: Any = None,
    reference_box: Any = None,
    control_type: Optional[str] = None,
    interaction_proof: Optional[Dict[str, Any]] = None,
) -> QualityAssessment:
    """Evalua un candidato (``FusedCandidate`` o dict) en cuatro dimensiones.

    Argumentos:
        candidate: candidato fusionado.
        thresholds: umbrales (por defecto ``get_active_thresholds()``).
        window_rect: rectangulo de la ventana objetivo en el mismo espacio que
            ``candidate.bbox`` (para detectar cajas truncadas).
        reference_box: caja de referencia (verdad-terreno de la fixture o caja
            refinada) en el mismo espacio.
        control_type: tipo canonico; por defecto ``candidate.type``.
        interaction_proof: ``{"verified": True, ...}`` cuando una prueba
            controlada demostro la accion sobre el propio control.
    """
    thr = thresholds or get_active_thresholds()
    ctype = control_type or str(_get(candidate, "type", "") or "") or None
    sources = _candidate_sources(candidate)
    win = _rect_of(window_rect)
    ref = _rect_of(reference_box)
    dims = {
        DIM_DETECTION: _assess_detection(sources, thr, ctype),
        DIM_SEMANTIC: _assess_semantic(candidate, sources, thr, ctype),
        DIM_INTERACTIVITY: _assess_interactivity(candidate, sources, interaction_proof),
        DIM_GEOMETRY: _assess_geometry(candidate, sources, thr, ctype, win, ref),
    }
    reasons = ["%s: %s" % (name, d.reason) for name, d in dims.items() if not d.passed]
    return QualityAssessment(
        passed=all(d.passed for d in dims.values()),
        dimensions=dims,
        reasons=reasons,
        candidate_id=_candidate_id(candidate),
        control_type=ctype or "",
    )


# ============================================================================
# ACCIONABILIDAD
# ============================================================================


class ActionabilityStatus(str, Enum):
    """Motivo por el que un control es o no accionable."""

    ACTIONABLE = "actionable"
    DISABLED = "disabled"
    OFFSCREEN = "offscreen"
    COVERED = "covered"
    AMBIGUOUS = "ambiguous"
    TRANSIENT = "transient"
    UNKNOWN_PROVIDER = "unknown_provider"
    INSUFFICIENT_QUALITY = "insufficient_quality"
    NOT_VERIFIED_INTERACTIVITY = "not_verified_interactivity"


# Roles nativos/tipos que representan elementos transitorios.
_TRANSIENT_ROLES = frozenset({
    "Menu", "ToolTip", "AXMenu", "AXHelpTag", "AXPopover", "AXSheet",
    "tooltip", "popup", "popover",
})


@dataclass
class ActionabilityDecision:
    """Decision de accionabilidad con la definicion logica a conservar."""

    actionable: bool
    status: ActionabilityStatus
    reason: str
    keep_logical_definition: bool
    logical_definition: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actionable": bool(self.actionable),
            "status": self.status.value,
            "reason": self.reason,
            "keep_logical_definition": bool(self.keep_logical_definition),
            "logical_definition": dict(self.logical_definition),
        }


def logical_definition_of(candidate: Any, status: Optional[ActionabilityStatus] = None) -> Dict[str, Any]:
    """Definicion logica del control SIN geometria fisica (apta para el catalogo)."""
    sources = _candidate_sources(candidate)
    return {
        "canonical_id": _candidate_id(candidate),
        "name": str(_get(candidate, "name", "") or ""),
        "type": str(_get(candidate, "type", "") or ""),
        "text": str(_get(candidate, "text", "") or ""),
        "description": str(_get(candidate, "description", "") or ""),
        "classification": _classification_value(candidate),
        "sources": sorted({s.method.value for s in sources if s.method is not None}),
        "accessibility_patterns": _accessibility_patterns(sources),
        "status": status.value if status else None,
        "calibration_required": True,
    }


def decide_actionability(
    candidate: Any,
    assessment: Optional[QualityAssessment] = None,
    covered: bool = False,
    transient: bool = False,
    ambiguous: bool = False,
) -> ActionabilityDecision:
    """Decide si un control puede calibrarse como accionable.

    Orden de decision (el primer motivo encontrado es el que se informa):
    deshabilitado, fuera de pantalla/oculto, cubierto, ambiguo, transitorio,
    proveedor desconocido, calidad insuficiente, interactividad no verificada.
    En todos los casos no accionables se conserva la definicion logica si el
    control tiene identidad (nombre, texto o descripcion).
    """
    sources = _candidate_sources(candidate)
    flags = _accessibility_flags(sources)
    classification = _classification_value(candidate)
    assessment = assessment or assess_candidate(candidate)

    status = ActionabilityStatus.ACTIONABLE
    reason = "control accionable con evidencia suficiente en todas las dimensiones"
    native_role = str(
        _get(candidate, "native_role", "")
        or next((s.raw.get("control_type") or s.raw.get("native_role") for s in sources
                 if s.method is DetectionMethod.ACCESSIBILITY and (s.raw.get("control_type") or s.raw.get("native_role"))), "")
        or ""
    )
    candidate_type = str(_get(candidate, "type", "") or "")

    if flags["enabled"] is False or classification == ElementClassification.DISABLED.value:
        status, reason = ActionabilityStatus.DISABLED, "control deshabilitado"
    elif (
        flags["offscreen"] is True
        or flags["visible"] is False
        or classification == ElementClassification.OFFSCREEN.value
    ):
        status, reason = ActionabilityStatus.OFFSCREEN, "control fuera de pantalla o no visible"
    elif covered:
        status, reason = ActionabilityStatus.COVERED, "control cubierto por otra ventana o elemento"
    elif ambiguous:
        status, reason = ActionabilityStatus.AMBIGUOUS, "solapamiento ambiguo con otro control"
    elif transient or native_role in _TRANSIENT_ROLES or candidate_type in _TRANSIENT_ROLES:
        status, reason = ActionabilityStatus.TRANSIENT, "elemento transitorio (menu, popup o tooltip)"
    elif not sources or all(s.method is None for s in sources):
        status, reason = ActionabilityStatus.UNKNOWN_PROVIDER, "proveedor de deteccion desconocido"
    elif not assessment.detected_ok:
        status = ActionabilityStatus.INSUFFICIENT_QUALITY
        reason = "; ".join(r for r in assessment.reasons if not r.startswith(DIM_INTERACTIVITY)) or "calidad insuficiente"
    elif not assessment.dimension_passed(DIM_INTERACTIVITY):
        status = ActionabilityStatus.NOT_VERIFIED_INTERACTIVITY
        reason = assessment.dimensions[DIM_INTERACTIVITY].reason

    actionable = status is ActionabilityStatus.ACTIONABLE
    logical = logical_definition_of(candidate, status)
    useful = bool(logical["name"] or logical["text"] or logical["description"])
    return ActionabilityDecision(
        actionable=actionable,
        status=status,
        reason=reason,
        keep_logical_definition=useful,
        logical_definition=logical if useful else {},
    )


# ============================================================================
# ENTORNO DE INTERACCION
# ============================================================================


@dataclass
class InteractionCheck:
    """Resultado de comprobar el entorno antes de capturar o enviar entradas."""

    allowed: bool
    reasons: List[str] = field(default_factory=list)
    environment: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"allowed": bool(self.allowed), "reasons": list(self.reasons), "environment": self.environment}


def check_interaction_environment(
    adapter: Optional[DesktopPlatformAdapter],
    window_id: int,
    strict_unknown: bool = True,
) -> InteractionCheck:
    """Comprueba sesion, escritorio seguro, elevacion, protecciones y overlays.

    Usa ``adapter.check_interaction_environment``. Si la comprobacion no esta
    disponible, o (con ``strict_unknown``) alguna comprobacion no se pudo
    realizar, no se permite interactuar: no se asume un entorno seguro.
    """
    if adapter is None:
        try:
            from src.desktop.platform_contract import get_desktop_platform

            adapter = get_desktop_platform()
        except Exception as exc:
            logger.warning("Sin adaptador de escritorio para comprobar el entorno: %s", exc)
            return InteractionCheck(False, ["environment_check_unavailable:no_adapter"], None)
    try:
        result = adapter.check_interaction_environment(int(window_id))
    except Exception as exc:  # el contrato no deberia levantar; se protege igualmente
        logger.warning("Fallo comprobando el entorno de interaccion: %s", exc)
        return InteractionCheck(False, ["environment_check_failed"], None)
    if not result.ok or result.value is None:
        code = result.error.code.value if result.error else "unknown"
        reasons = ["environment_check_unavailable:%s" % code]
        if result.error and result.error.code == PlatformErrorCode.WINDOW_GONE:
            reasons = ["window_gone"]
        elif result.error and result.error.code == PlatformErrorCode.SESSION_LOCKED:
            reasons = ["session_locked"]
        elif result.error and result.error.code == PlatformErrorCode.PERMISSION_DENIED:
            reasons = ["permission_missing:%s" % (result.error.details.get("permission") or "desconocido")]
        return InteractionCheck(False, reasons, result.error.to_dict() if result.error else None)
    env = result.value
    reasons = list(env.blocking_reasons())
    if strict_unknown:
        reasons.extend("check_unknown:%s" % name for name in env.unknown_checks)
    return InteractionCheck(not reasons, reasons, env.to_dict())


# ============================================================================
# DERIVA ENTRE DETECCION Y ACCION
# ============================================================================

FINGERPRINT_METHOD_TOPOLOGY = "monitor_topology"
FINGERPRINT_METHOD_INTERNAL = "internal"


def _internal_topology_fingerprint(displays: Sequence[DisplayInfo]) -> str:
    rows = sorted(
        "%s|%s|%dx%d|%.4f|%d|%d" % (
            d.display_id, d.bounds.to_tuple(), int(d.pixel_width), int(d.pixel_height),
            float(d.scale_factor), int(d.rotation), int(bool(d.is_primary)),
        )
        for d in displays
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8", "replace")).hexdigest()


def _topology_fingerprint(
    displays: Sequence[DisplayInfo], topology: Any = None, method: Optional[str] = None
) -> Tuple[Optional[str], str]:
    """Huella de topologia. Prefiere ``monitor_topology`` (B3) si existe."""
    if method == FINGERPRINT_METHOD_INTERNAL:
        return _internal_topology_fingerprint(displays), FINGERPRINT_METHOD_INTERNAL
    if topology is not None and getattr(topology, "fingerprint", None):
        return str(topology.fingerprint), FINGERPRINT_METHOD_TOPOLOGY
    try:
        from src.desktop.monitor_topology import MonitorTopology  # perezoso: bloque B3

        return str(MonitorTopology.from_displays(list(displays)).fingerprint), FINGERPRINT_METHOD_TOPOLOGY
    except Exception as exc:
        if method == FINGERPRINT_METHOD_TOPOLOGY:
            logger.debug("monitor_topology no disponible para comparar huellas: %s", exc)
            return None, FINGERPRINT_METHOD_TOPOLOGY
        return _internal_topology_fingerprint(displays), FINGERPRINT_METHOD_INTERNAL


def _display_of_window(window: WindowInfo, displays: Sequence[DisplayInfo]) -> Optional[DisplayInfo]:
    if window.display_id:
        for d in displays:
            if d.display_id == window.display_id:
                return d
    rect = window.frame_bounds or window.bounds
    if rect is None:
        return None
    best: Optional[DisplayInfo] = None
    best_area = 0.0
    for d in displays:
        area = d.bounds.intersection_area(rect)
        if area > best_area:
            best, best_area = d, area
    return best


@dataclass
class DetectionSnapshot:
    """Estado observado en el momento de detectar (para comparar antes de actuar)."""

    window_id: int
    pid: Optional[int]
    foreground_window_id: Optional[int]
    display_id: Optional[str]
    scale_factor: Optional[float]
    dpi: Optional[int]
    display_bounds: Optional[Rect]
    window_bounds: Optional[Rect]
    client_bounds: Optional[Rect]
    control_box: Optional[Rect]
    ui_state_hash: Optional[str]
    topology_fingerprint: Optional[str]
    captured_at: float
    topology_fingerprint_method: str = FINGERPRINT_METHOD_INTERNAL
    display_pixel_size: Optional[Tuple[int, int]] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "pid": self.pid,
            "foreground_window_id": self.foreground_window_id,
            "display_id": self.display_id,
            "scale_factor": self.scale_factor,
            "dpi": self.dpi,
            "display_bounds": self.display_bounds.to_dict() if self.display_bounds else None,
            "window_bounds": self.window_bounds.to_dict() if self.window_bounds else None,
            "client_bounds": self.client_bounds.to_dict() if self.client_bounds else None,
            "control_box": self.control_box.to_dict() if self.control_box else None,
            "ui_state_hash": self.ui_state_hash,
            "topology_fingerprint": self.topology_fingerprint,
            "topology_fingerprint_method": self.topology_fingerprint_method,
            "display_pixel_size": list(self.display_pixel_size) if self.display_pixel_size else None,
            "captured_at": self.captured_at,
            "errors": list(self.errors),
        }


def _resolve_adapter(adapter: Optional[DesktopPlatformAdapter]) -> DesktopPlatformAdapter:
    if adapter is not None:
        return adapter
    from src.desktop.platform_contract import get_desktop_platform

    return get_desktop_platform()


def take_detection_snapshot(
    adapter: Optional[DesktopPlatformAdapter],
    window_id: int,
    control_box: Any = None,
    ui_state_hash: Optional[str] = None,
    topology: Any = None,
    capture_ui_state: bool = False,
    clock: Any = time.monotonic,
) -> DetectionSnapshot:
    """Registra el estado de la ventana, foco, monitor, escala y topologia.

    Si ``capture_ui_state`` es True y no se da ``ui_state_hash``, se calcula
    con ``structure_hash()`` del arbol de accesibilidad de la ventana.
    """
    adp = _resolve_adapter(adapter)
    errors: List[str] = []
    window: Optional[WindowInfo] = None
    res = adp.get_window(int(window_id))
    if res.ok and res.value is not None:
        window = res.value
    else:
        errors.append("window_unreadable")
    fg_id: Optional[int] = None
    fg = adp.get_foreground_window()
    if fg.ok:
        fg_id = fg.value.window_id if fg.value is not None else None
    else:
        errors.append("foreground_unreadable")
    displays: List[DisplayInfo] = []
    disp = adp.enumerate_displays()
    if disp.ok and disp.value:
        displays = list(disp.value)
    else:
        errors.append("displays_unreadable")
    display = _display_of_window(window, displays) if window is not None else None
    dpi = window.dpi if window is not None else None
    scale = window.scale_factor if window is not None else None
    dpi_res = adp.get_window_dpi_info(int(window_id))
    if dpi_res.ok and dpi_res.value is not None:
        dpi = dpi_res.value.dpi if dpi_res.value.dpi is not None else dpi
        scale = dpi_res.value.scale_factor if dpi_res.value.scale_factor is not None else scale
    if scale is None and display is not None:
        scale = display.scale_factor
    if dpi is None and display is not None:
        dpi = display.dpi
    if ui_state_hash is None and capture_ui_state:
        tree_res = adp.get_accessibility_tree(int(window_id), pid=window.pid if window else None)
        if tree_res.ok and tree_res.value is not None and hasattr(tree_res.value, "structure_hash"):
            ui_state_hash = tree_res.value.structure_hash()
        else:
            errors.append("ui_state_unreadable")
    fingerprint, method = _topology_fingerprint(displays, topology) if displays else (None, FINGERPRINT_METHOD_INTERNAL)
    return DetectionSnapshot(
        window_id=int(window_id),
        pid=window.pid if window is not None else None,
        foreground_window_id=fg_id,
        display_id=display.display_id if display is not None else (window.display_id if window else None),
        scale_factor=scale,
        dpi=dpi,
        display_bounds=display.bounds if display is not None else None,
        window_bounds=window.bounds if window is not None else None,
        client_bounds=window.client_bounds if window is not None else None,
        control_box=_rect_of(control_box),
        ui_state_hash=ui_state_hash,
        topology_fingerprint=fingerprint,
        captured_at=float(clock()),
        topology_fingerprint_method=method,
        display_pixel_size=(int(display.pixel_width), int(display.pixel_height)) if display is not None else None,
        errors=errors,
    )


DRIFT_PROCEED = "proceed"
DRIFT_RECAPTURE = "recapture"
DRIFT_RECALIBRATE = "recalibrate"
_DRIFT_SEVERITY = {DRIFT_PROCEED: 0, DRIFT_RECAPTURE: 1, DRIFT_RECALIBRATE: 2}


@dataclass
class DriftCheck:
    """Resultado de comparar el estado actual con el de la deteccion."""

    unchanged: bool
    changes: List[str] = field(default_factory=list)
    action: str = DRIFT_PROCEED
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unchanged": bool(self.unchanged),
            "changes": list(self.changes),
            "action": self.action,
            "reason": self.reason,
            "details": dict(self.details),
        }


def _rect_changed(a: Optional[Rect], b: Optional[Rect], tolerance_ratio: float) -> bool:
    """Cambio relativo de posicion o tamano superior a ``tolerance_ratio``."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    ref = max(1e-9, min(a.width, a.height))
    ax, ay = a.center
    bx, by = b.center
    if math.hypot(ax - bx, ay - by) / ref > tolerance_ratio:
        return True
    if abs(a.width - b.width) / max(1e-9, a.width) > tolerance_ratio:
        return True
    if abs(a.height - b.height) / max(1e-9, a.height) > tolerance_ratio:
        return True
    return False


def verify_before_action(
    snapshot: DetectionSnapshot,
    adapter: Optional[DesktopPlatformAdapter] = None,
    current_control_box: Any = None,
    current_ui_state_hash: Optional[str] = None,
    max_age_seconds: Optional[float] = None,
    box_tolerance_ratio: float = 0.10,
    topology: Any = None,
    require_control_box: bool = False,
    clock: Any = time.monotonic,
) -> DriftCheck:
    """Compara el estado actual con el de la deteccion antes de actuar.

    Cualquier cambio impide reutilizar la deteccion. ``action``:
    ``recalibrate`` si cambia la identidad (ventana/PID), la escala/DPI, la
    resolucion o la topologia; ``recapture`` si cambia el foco, el monitor, la
    geometria de la ventana, la caja del control, el estado UI, la captura es
    demasiado antigua o no se pudo leer el estado; ``proceed`` sin cambios.
    """
    adp = _resolve_adapter(adapter)
    changes: List[Tuple[str, str]] = []
    details: Dict[str, Any] = {}

    def add(code: str, severity: str) -> None:
        changes.append((code, severity))

    now = float(clock())
    age = now - float(snapshot.captured_at)
    details["age_seconds"] = age
    if max_age_seconds is not None and age > float(max_age_seconds):
        add("capture_stale", DRIFT_RECAPTURE)

    res = adp.get_window(int(snapshot.window_id))
    window: Optional[WindowInfo] = res.value if (res.ok and res.value is not None) else None
    if window is None:
        add("window_gone", DRIFT_RECALIBRATE)
    else:
        if snapshot.pid is not None and int(window.pid) != int(snapshot.pid):
            add("pid_changed", DRIFT_RECALIBRATE)
        if window.is_minimized:
            add("window_minimized", DRIFT_RECAPTURE)
        if not window.is_visible:
            add("window_hidden", DRIFT_RECAPTURE)
        if _rect_changed(snapshot.window_bounds, window.bounds, 0.0):
            add("window_moved_or_resized", DRIFT_RECAPTURE)
        if snapshot.client_bounds is not None and _rect_changed(snapshot.client_bounds, window.client_bounds, 0.0):
            add("client_area_changed", DRIFT_RECAPTURE)

    fg = adp.get_foreground_window()
    if not fg.ok:
        add("foreground_unverifiable", DRIFT_RECAPTURE)
    else:
        fg_id = fg.value.window_id if fg.value is not None else None
        if fg_id != int(snapshot.window_id):
            add("focus_lost", DRIFT_RECAPTURE)

    disp = adp.enumerate_displays()
    if not disp.ok or not disp.value:
        add("displays_unverifiable", DRIFT_RECAPTURE)
    else:
        displays = list(disp.value)
        fingerprint, _method = _topology_fingerprint(
            displays, topology, method=snapshot.topology_fingerprint_method
        )
        details["topology_fingerprint"] = fingerprint
        if snapshot.topology_fingerprint is not None:
            if fingerprint is None:
                add("topology_unverifiable", DRIFT_RECAPTURE)
            elif fingerprint != snapshot.topology_fingerprint:
                add("topology_changed", DRIFT_RECALIBRATE)
        if window is not None:
            display = _display_of_window(window, displays)
            if display is None:
                add("monitor_unknown", DRIFT_RECAPTURE)
            else:
                if snapshot.display_id is not None and display.display_id != snapshot.display_id:
                    add("monitor_changed", DRIFT_RECAPTURE)
                if snapshot.display_pixel_size is not None and (
                    int(display.pixel_width), int(display.pixel_height)
                ) != tuple(snapshot.display_pixel_size):
                    add("resolution_changed", DRIFT_RECALIBRATE)
                current_scale = display.scale_factor
                current_dpi = display.dpi
                dpi_res = adp.get_window_dpi_info(int(snapshot.window_id))
                if dpi_res.ok and dpi_res.value is not None:
                    if dpi_res.value.scale_factor is not None:
                        current_scale = dpi_res.value.scale_factor
                    if dpi_res.value.dpi is not None:
                        current_dpi = dpi_res.value.dpi
                if snapshot.scale_factor is not None and current_scale is not None and \
                        abs(float(current_scale) - float(snapshot.scale_factor)) > 1e-6:
                    add("scale_changed", DRIFT_RECALIBRATE)
                if snapshot.dpi is not None and current_dpi is not None and int(current_dpi) != int(snapshot.dpi):
                    add("dpi_changed", DRIFT_RECALIBRATE)

    current_box = _rect_of(current_control_box)
    if snapshot.control_box is not None:
        if current_box is None:
            if require_control_box:
                add("control_box_unverified", DRIFT_RECAPTURE)
        elif _rect_changed(snapshot.control_box, current_box, float(box_tolerance_ratio)):
            add("control_box_changed", DRIFT_RECAPTURE)

    if snapshot.ui_state_hash is not None and current_ui_state_hash is not None and \
            current_ui_state_hash != snapshot.ui_state_hash:
        add("ui_state_changed", DRIFT_RECAPTURE)

    codes = [c for c, _ in changes]
    action = DRIFT_PROCEED
    for _code, severity in changes:
        if _DRIFT_SEVERITY[severity] > _DRIFT_SEVERITY[action]:
            action = severity
    reason = "sin cambios entre deteccion y accion" if not codes else (
        "cambios detectados (%s): %s; no se reutiliza la deteccion" % (action, ", ".join(codes))
    )
    if codes:
        logger.info("Deriva antes de actuar en ventana %s: %s", snapshot.window_id, ", ".join(codes))
    return DriftCheck(unchanged=not codes, changes=codes, action=action, reason=reason, details=details)


# ============================================================================
# FACHADA DE LA PUERTA
# ============================================================================


@dataclass
class GateResult:
    """Resultado de la puerta de calidad sobre un conjunto de candidatos."""

    accepted: List[Any] = field(default_factory=list)
    rejected: List[Tuple[Any, List[str]]] = field(default_factory=list)
    assessments: Dict[str, QualityAssessment] = field(default_factory=dict)
    decisions: Dict[str, ActionabilityDecision] = field(default_factory=dict)
    detected_not_actionable: List[Any] = field(default_factory=list)
    thresholds_fingerprint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": [_candidate_id(c) for c in self.accepted],
            "rejected": [{"candidate": _candidate_id(c), "reasons": list(r)} for c, r in self.rejected],
            "detected_not_actionable": [_candidate_id(c) for c in self.detected_not_actionable],
            "assessments": {k: v.to_dict() for k, v in self.assessments.items()},
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "thresholds_fingerprint": self.thresholds_fingerprint,
        }


def _same_identity(a: Any, b: Any) -> bool:
    ida = str(_get(a, "canonical_id", None) or _get(a, "name", None) or "").strip().lower()
    idb = str(_get(b, "canonical_id", None) or _get(b, "name", None) or "").strip().lower()
    return bool(ida) and ida == idb


def check_box_geometry(
    candidate: Any,
    others: Sequence[Any],
    window_rect: Any = None,
    image_rect: Any = None,
    max_ambiguous_iou: float = _AMBIGUOUS_IOU,
) -> Tuple[List[str], bool]:
    """Comprobacion geometrica pura (sin SO). Devuelve (motivos, ambiguo).

    Equivale a las comprobaciones de ``validate_geometria_candidato`` que no
    necesitan consultar la ventana real: caja degenerada, fuera de ventana,
    fuera de imagen y solapamiento ambiguo con otra identidad.
    """
    reasons: List[str] = []
    box = _rect_of(_get(candidate, "bbox", None))
    if box is None:
        return ["caja vacia, ausente o degenerada"], False
    win = _rect_of(window_rect)
    if win is not None and not win.contains_rect(box):
        reasons.append("caja parcialmente o totalmente fuera de la ventana objetivo")
    img = _rect_of(image_rect)
    if img is not None and not img.contains_rect(box):
        reasons.append("caja fuera de la imagen o captura")
    ambiguous = False
    for other in others:
        if other is candidate:
            continue
        obox = _rect_of(_get(other, "bbox", None))
        if obox is None:
            continue
        if box.iou(obox) > max_ambiguous_iou and not _same_identity(candidate, other):
            ambiguous = True
            reasons.append("solapamiento ambiguo con %s" % _candidate_id(other))
            break
    return reasons, ambiguous


class CalibrationQualityGate:
    """Combina geometria, calidad por dimensiones y accionabilidad.

    Argumentos:
        thresholds: umbrales (por defecto los activos del proceso).
        adapter: adaptador de escritorio para ``check_environment`` (opcional).
    """

    def __init__(
        self,
        thresholds: Optional[DetectionThresholds] = None,
        adapter: Optional[DesktopPlatformAdapter] = None,
    ) -> None:
        self.thresholds = thresholds or get_active_thresholds()
        self.adapter = adapter

    def evaluate(
        self,
        candidates: Sequence[Any],
        window_rect: Any,
        image_rect: Any = None,
        validator: Any = None,
        covered_ids: Optional[Iterable[str]] = None,
        transient_ids: Optional[Iterable[str]] = None,
        interaction_proofs: Optional[Dict[str, Dict[str, Any]]] = None,
        reference_boxes: Optional[Dict[str, Any]] = None,
    ) -> GateResult:
        """Evalua todos los candidatos de una ventana.

        ``validator`` es opcional: un ``WindowEvidenceValidator`` (Windows)
        cuyo ``validate_geometria_candidato`` se usa ademas de la comprobacion
        geometrica pura. ``covered_ids``/``transient_ids`` marcan candidatos
        cubiertos o transitorios por id canonico; ``interaction_proofs`` y
        ``reference_boxes`` se indexan tambien por id canonico.
        """
        covered = set(covered_ids or [])
        transient = set(transient_ids or [])
        proofs = dict(interaction_proofs or {})
        refs = dict(reference_boxes or {})
        candidate_list = list(candidates or [])
        result = GateResult(thresholds_fingerprint=self.thresholds.fingerprint())
        for cand in candidate_list:
            cid = _candidate_id(cand)
            ctype = str(_get(cand, "type", "") or "") or None
            max_iou = self.thresholds.ambiguous_iou(ctype)
            geo_reasons, ambiguous = check_box_geometry(
                cand, candidate_list, window_rect=window_rect, image_rect=image_rect,
                max_ambiguous_iou=max_iou,
            )
            if validator is not None:
                try:
                    v = validator.validate_geometria_candidato(
                        cand,
                        image_rect=Rect.from_any(image_rect).to_int_tuple() if _rect_of(image_rect) else None,
                        window_rect=Rect.from_any(window_rect).to_int_tuple() if _rect_of(window_rect) else None,
                        otros_candidatos=candidate_list,
                        umbral_solapamiento=max_iou,
                    )
                    if not v.valid:
                        for r in str(v.reason).split("; "):
                            if r and r not in geo_reasons:
                                geo_reasons.append(r)
                        if v.checks.get("no_solapamiento_ambiguo") is False:
                            ambiguous = True
                except Exception as exc:
                    logger.warning("Validador geometrico fallo para %s: %s", cid, exc)
                    geo_reasons.append("validador geometrico no disponible: %s" % exc)
            assessment = assess_candidate(
                cand, self.thresholds, window_rect=window_rect,
                reference_box=refs.get(cid), control_type=ctype,
                interaction_proof=proofs.get(cid),
            )
            decision = decide_actionability(
                cand, assessment, covered=cid in covered, transient=cid in transient,
                ambiguous=ambiguous,
            )
            result.assessments[cid] = assessment
            result.decisions[cid] = decision
            hard_geometry = [r for r in geo_reasons if not r.startswith("solapamiento ambiguo")]
            if decision.actionable and not hard_geometry:
                result.accepted.append(cand)
                continue
            reasons = list(geo_reasons)
            if not decision.actionable:
                reasons.append("%s: %s" % (decision.status.value, decision.reason))
            result.rejected.append((cand, reasons))
            if assessment.detected_ok and not hard_geometry and decision.status in (
                ActionabilityStatus.NOT_VERIFIED_INTERACTIVITY,
            ):
                result.detected_not_actionable.append(cand)
        return result

    def check_environment(self, window_id: int, strict_unknown: bool = True) -> InteractionCheck:
        return check_interaction_environment(self.adapter, window_id, strict_unknown=strict_unknown)

    def snapshot(self, window_id: int, control_box: Any = None, ui_state_hash: Optional[str] = None,
                 topology: Any = None, capture_ui_state: bool = False) -> DetectionSnapshot:
        return take_detection_snapshot(
            self.adapter, window_id, control_box=control_box, ui_state_hash=ui_state_hash,
            topology=topology, capture_ui_state=capture_ui_state,
        )

    def verify(self, snapshot: DetectionSnapshot, **kwargs: Any) -> DriftCheck:
        return verify_before_action(snapshot, self.adapter, **kwargs)


__all__ = [
    "DEFAULT_THRESHOLDS_PATH",
    "DEFAULT_PROVENANCE",
    "WILDCARD_CONTROL_TYPE",
    "MEASUREMENT_STATUS_PENDING",
    "MEASUREMENT_STATUS_MEASURED",
    "ThresholdsFrozenError",
    "ThresholdsIntegrityError",
    "DetectionMethod",
    "MethodThresholds",
    "DetectionThresholds",
    "get_active_thresholds",
    "set_active_thresholds",
    "DIM_DETECTION",
    "DIM_SEMANTIC",
    "DIM_INTERACTIVITY",
    "DIM_GEOMETRY",
    "DimensionResult",
    "QualityAssessment",
    "assess_candidate",
    "ActionabilityStatus",
    "ActionabilityDecision",
    "logical_definition_of",
    "decide_actionability",
    "InteractionCheck",
    "check_interaction_environment",
    "DetectionSnapshot",
    "take_detection_snapshot",
    "DRIFT_PROCEED",
    "DRIFT_RECAPTURE",
    "DRIFT_RECALIBRATE",
    "DriftCheck",
    "verify_before_action",
    "GateResult",
    "check_box_geometry",
    "CalibrationQualityGate",
]
