"""
Fusion de deteccion de elementos UI de multiples fuentes.

Une resultados de UI Automation, OmniParser V2, PaddleOCR, OpenCV y Qwen3-VL
sin duplicar el mismo elemento. Asocia candidatos por solapamiento (IoU),
centro, texto, tipo, jerarquia y ventana. Preserva por separado cada fuente,
su confianza y sus desacuerdos. Una coincidencia entre fuentes aumenta la
evidencia pero no oculta que dependen del mismo frame/modelo.

La salida de Qwen3-VL solo se incorpora tras verificar las unidades
3.8.6.3.3.8.1 y 3.8.6.3.3.8.2 (extraccion e interpretacion semantica).
Este modulo no descarga modelos, no captura pantalla y no ejecuta acciones
sobre controles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.log import get_logger
from src.core.ui_element_model import (
    UIElementData,
    ElementClassification,
    classify_element,
    normalize_element_type,
)

logger = get_logger(__name__)

# Umbrales de asociacion iniciales (unidad 3.8.6.3.3.9).
# Valores de partida documentados; la unidad de umbrales (3.8.6.4.3) los ajusta
# a partir de resultados medidos sobre una fixture real. Ninguna puntuacion
# agregada compensa una dimension insuficiente con otra.
IOU_MERGE_THRESHOLD = 0.30
CENTER_MERGE_THRESHOLD_PIX = 45.0
CONTAINMENT_IOU_THRESHOLD = 0.50
TEXT_PROXIMITY_MAX_CENTER_DIST_PIX = 60.0

SOURCE_UIA = "uia"
SOURCE_OMNIPARSER = "omniparser_v2_icon_detect_v3"
SOURCE_PADDLEOCR = "paddleocr"
SOURCE_QWEN3VL = "qwen3vl"
SOURCE_OPENCV = "opencv"

ALL_SOURCES = (
    SOURCE_UIA,
    SOURCE_OMNIPARSER,
    SOURCE_PADDLEOCR,
    SOURCE_QWEN3VL,
    SOURCE_OPENCV,
)

# Patrones UIA que indican capacidad de interaccion. Solo se consulta su
# disponibilidad durante el descubrimiento; nunca se invocan.
ACTIONABLE_PATTERNS = frozenset({
    "Invoke", "Value", "Toggle", "Selection", "ExpandCollapse",
    "Scroll", "Window", "Transform",
})


def _box_center(bbox: Optional[List[int]]) -> Optional[Tuple[float, float]]:
    """Centro de una caja [x1, y1, x2, y2], o None si invalida."""
    if not bbox or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _box_area(bbox: Optional[List[int]]) -> float:
    if not bbox or len(bbox) != 4:
        return 0.0
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _iou(a: Optional[List[int]], b: Optional[List[int]]) -> float:
    """Interseccion sobre union de dos cajas."""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    try:
        ax1, ay1, ax2, ay2 = [float(v) for v in a]
        bx1, by1, bx2, by2 = [float(v) for v in b]
    except (TypeError, ValueError):
        return 0.0
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _center_distance(a: Optional[List[int]], b: Optional[List[int]]) -> Optional[float]:
    ca = _box_center(a)
    cb = _box_center(b)
    if ca is None or cb is None:
        return None
    return math.hypot(cb[0] - ca[0], cb[1] - ca[1])


def _contains(inner: Optional[List[int]], outer: Optional[List[int]]) -> bool:
    if not inner or not outer or len(inner) != 4 or len(outer) != 4:
        return False
    try:
        ix1, iy1, ix2, iy2 = [float(v) for v in inner]
        ox1, oy1, ox2, oy2 = [float(v) for v in outer]
    except (TypeError, ValueError):
        return False
    return ix1 >= ox1 and iy1 >= oy1 and ix2 <= ox2 and iy2 <= oy2


def _merge_bboxes(bboxes: List[Optional[List[int]]]) -> Optional[List[int]]:
    """Caja union de todas las cajas validas, o None si no hay ninguna."""
    valid = [b for b in bboxes if b and len(b) == 4]
    if not valid:
        return None
    try:
        x1 = min(float(b[0]) for b in valid)
        y1 = min(float(b[1]) for b in valid)
        x2 = max(float(b[2]) for b in valid)
        y2 = max(float(b[3]) for b in valid)
    except (TypeError, ValueError):
        return None
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


def _source_priority(source: str) -> int:
    """Orden de preferencia para elegir la fuente primaria de un cluster."""
    order = {
        SOURCE_UIA: 0,
        SOURCE_QWEN3VL: 1,
        SOURCE_OMNIPARSER: 2,
        SOURCE_PADDLEOCR: 3,
        SOURCE_OPENCV: 4,
    }
    return order.get(source, 99)


@dataclass
class SourceEvidence:
    """Evidencia de una unica fuente de deteccion para un candidato fusionado."""

    source: str
    confidence: float
    bbox: Optional[List[int]] = None
    center: Optional[List[int]] = None
    element: Optional[UIElementData] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    available: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "confidence": float(self.confidence),
            "bbox": list(self.bbox) if self.bbox else None,
            "center": list(self.center) if self.center else None,
            "element": self.element.to_dict() if self.element else None,
            "raw": dict(self.raw),
            "available": bool(self.available),
            "error": self.error,
        }


@dataclass
class FusedCandidate:
    """Elemento UI resultante de fusionar evidencias de varias fuentes."""

    canonical_id: str
    name: str
    type: str
    text: str
    description: str
    bbox: Optional[List[int]] = None
    center: Optional[List[int]] = None
    screen: int = 0
    window_handle: Optional[int] = None
    process_id: Optional[int] = None
    sources: List[SourceEvidence] = field(default_factory=list)
    merged_confidence: float = 0.0
    agreement: bool = True
    disagreements: List[str] = field(default_factory=list)
    interactive: bool = False
    interactive_evidence: List[str] = field(default_factory=list)
    calibrated: bool = False
    classification: ElementClassification = ElementClassification.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "name": self.name,
            "type": self.type,
            "text": self.text,
            "description": self.description,
            "bbox": list(self.bbox) if self.bbox else None,
            "center": list(self.center) if self.center else None,
            "screen": int(self.screen),
            "window_handle": self.window_handle,
            "process_id": self.process_id,
            "sources": [s.to_dict() for s in self.sources],
            "merged_confidence": float(self.merged_confidence),
            "agreement": bool(self.agreement),
            "disagreements": list(self.disagreements),
            "interactive": bool(self.interactive),
            "interactive_evidence": list(self.interactive_evidence),
            "calibrated": bool(self.calibrated),
            "classification": str(self.classification.value),
        }


@dataclass
class FusionResult:
    """Resultado de una fusion de detecciones para una ventana/pantalla."""

    window_handle: Optional[int]
    process_id: Optional[int]
    screen: int
    candidates: List[FusedCandidate] = field(default_factory=list)
    candidate_count: int = 0
    sources_used: List[str] = field(default_factory=list)
    sources_available: Dict[str, bool] = field(default_factory=dict)
    duplicates_removed: int = 0
    disagreements_total: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_handle": self.window_handle,
            "process_id": self.process_id,
            "screen": int(self.screen),
            "candidates": [c.to_dict() for c in self.candidates],
            "candidate_count": int(self.candidate_count),
            "sources_used": list(self.sources_used),
            "sources_available": dict(self.sources_available),
            "duplicates_removed": int(self.duplicates_removed),
            "disagreements_total": int(self.disagreements_total),
            "error": self.error,
        }


@dataclass
class DetectedCandidate:
    """Candidato detectado por una unica fuente, listo para fusionar."""

    source: str
    element: UIElementData
    confidence: float
    bbox: Optional[List[int]] = None
    center: Optional[List[int]] = None
    screen: int = 0
    window_handle: Optional[int] = None
    process_id: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)


class VisualUIDetectorFusion:
    """Fusiona candidatos de UI Automation, OmniParser, PaddleOCR, OpenCV y Qwen3-VL.

    No crea candidatos nuevos a partir de heuristicas geometricas solas:
    OpenCV aporta pistas de refinamiento de limites, nunca interactividad.
    """

    def __init__(self) -> None:
        self.iou_threshold = IOU_MERGE_THRESHOLD
        self.center_threshold_pix = CENTER_MERGE_THRESHOLD_PIX
        self.containment_iou_threshold = CONTAINMENT_IOU_THRESHOLD
        self.text_proximity_max_center_dist_pix = TEXT_PROXIMITY_MAX_CENTER_DIST_PIX

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------
    def fuse(
        self,
        candidates: List[DetectedCandidate],
        qwen3vl_evidence: Optional[List[Dict[str, Any]]] = None,
        image_path: Optional[str] = None,
        window_handle: Optional[int] = None,
        process_id: Optional[int] = None,
        screen: int = 0,
    ) -> FusionResult:
        """Fusiona una lista de candidatos detectados en candidatos unicos.

        Argumentos:
            candidates: candidatos detectados por cada fuente.
            qwen3vl_evidence: lista de dicts de interpretacion semantica
                Qwen3-VL con clave "reference" (nombre/etiqueta para asociar)
                y, opcionalmente, "bbox".
            image_path: ruta de la captura sobre la que OpenCV refina limites
                (pista geometrica solamente).
            window_handle / process_id: ventana a la que pertenecen los
                candidatos (para no fusionar elementos de ventanas distintas).
            screen: indice de pantalla asociado.

        Retorna:
            FusionResult con los candidatos fusionados, fuentes usadas,
            duplicados eliminados y desacuerdos detectados.
        """
        result = FusionResult(
            window_handle=window_handle,
            process_id=process_id,
            screen=int(screen),
        )
        if not candidates:
            result.candidate_count = 0
            return result

        # Agrupar por ventana/pantalla para no fusionar elementos de ventanas distintas
        groups: Dict[Tuple[Optional[int], Optional[int], int], List[DetectedCandidate]] = {}
        for c in candidates:
            key = (c.window_handle, c.process_id, c.screen)
            groups.setdefault(key, []).append(c)

        fused: List[FusedCandidate] = []
        duplicates_removed = 0
        disagreements_total = 0
        cluster_index = 0

        for key, group in groups.items():
            clusters = self._cluster(group)
            duplicates_removed += len(group) - len(clusters)
            for cluster in clusters:
                fc = self._merge_cluster(
                    cluster,
                    cluster_index=cluster_index,
                    qwen3vl_evidence=qwen3vl_evidence,
                    image_path=image_path,
                    window_handle=key[0],
                    process_id=key[1],
                    screen=key[2],
                )
                cluster_index += 1
                if fc is not None:
                    fused.append(fc)
                    disagreements_total += len(fc.disagreements)

        # Recomputar fuentes usadas a partir de los candidatos fusionados, de
        # modo que fuentes anadidas durante el merge (p.ej. Qwen3-VL) queden
        # reflejadas en el resultado.
        sources_used: List[str] = []
        sources_available: Dict[str, bool] = {s: False for s in ALL_SOURCES}
        for fc in fused:
            for ev in fc.sources:
                src = ev.source
                if src not in sources_used:
                    sources_used.append(src)
                if ev.available:
                    sources_available[src] = True
        # Una fuente declarada en la evidencia de Qwen3-VL se considera
        # disponible si aporto al menos un candidato.
        if qwen3vl_evidence and sources_available.get(SOURCE_QWEN3VL):
            sources_available[SOURCE_QWEN3VL] = True

        result.candidates = fused
        result.candidate_count = len(fused)
        result.duplicates_removed = duplicates_removed
        result.disagreements_total = disagreements_total
        result.sources_available = sources_available
        result.sources_used = sources_used
        return result

    # ------------------------------------------------------------------
    # Agrupacion (clustering) de candidatos de una misma ventana
    # ------------------------------------------------------------------
    def _cluster(
        self, candidates: List[DetectedCandidate]
    ) -> List[List[DetectedCandidate]]:
        n = len(candidates)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(n):
            for j in range(i + 1, n):
                if self._should_merge(candidates[i], candidates[j]):
                    union(i, j)

        clusters: Dict[int, List[DetectedCandidate]] = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(candidates[i])
        return list(clusters.values())

    def _should_merge(self, a: DetectedCandidate, b: DetectedCandidate) -> bool:
        """Decide si dos candidatos son el mismo elemento visual."""
        # Mismo identificador estable de UI Automation (automation_id)
        a_id = self._raw_id(a)
        b_id = self._raw_id(b)
        if a_id and b_id and a_id == b_id:
            return True

        # Solapamiento significativo (IoU)
        if _iou(a.bbox, b.bbox) >= self.iou_threshold:
            return True

        # Uno contiene al otro con solapamiento relevante sobre el menor
        if _contains(a.bbox, b.bbox) or _contains(b.bbox, a.bbox):
            smaller = a.bbox if _box_area(a.bbox) <= _box_area(b.bbox) else b.bbox
            larger = b.bbox if smaller is a.bbox else a.bbox
            if _iou(smaller, larger) >= self.containment_iou_threshold:
                return True

        # Centros cercanos
        dist = _center_distance(a.bbox, b.bbox)
        if dist is not None and dist <= self.center_threshold_pix:
            return True

        # Asociacion por texto: texto OCR coincide con nombre/texto del otro
        if self._text_association(a, b):
            return True

        return False

    def _raw_id(self, c: DetectedCandidate) -> Optional[str]:
        if not c.raw:
            return None
        for key in ("automation_id", "runtime_id", "name"):
            v = c.raw.get(key)
            if v:
                return str(v)
        return None

    def _text_association(self, a: DetectedCandidate, b: DetectedCandidate) -> bool:
        """True si el texto de uno parece etiquetar al otro (cercania + coincidencia)."""
        dist = _center_distance(a.bbox, b.bbox)
        if dist is None or dist > self.text_proximity_max_center_dist_pix:
            return False
        texts_a = self._candidate_texts(a)
        texts_b = self._candidate_texts(b)
        for ta in texts_a:
            if not ta:
                continue
            for tb in texts_b:
                if tb and (ta == tb or ta in tb or tb in ta):
                    return True
        return False

    @staticmethod
    def _candidate_texts(c: DetectedCandidate) -> List[str]:
        out: List[str] = []
        if c.element:
            if c.element.name:
                out.append(str(c.element.name))
            if c.element.text:
                out.append(str(c.element.text))
        if c.raw and c.raw.get("text"):
            out.append(str(c.raw["text"]))
        return out

    # ------------------------------------------------------------------
    # Fusion de un cluster en un candidato unico
    # ------------------------------------------------------------------
    def _merge_cluster(
        self,
        cluster: List[DetectedCandidate],
        cluster_index: int = 0,
        qwen3vl_evidence: Optional[List[Dict[str, Any]]] = None,
        image_path: Optional[str] = None,
        window_handle: Optional[int] = None,
        process_id: Optional[int] = None,
        screen: int = 0,
    ) -> Optional[FusedCandidate]:
        if not cluster:
            return None

        source_evidence: List[SourceEvidence] = []
        source_by_name: Dict[str, SourceEvidence] = {}
        for c in cluster:
            ev = SourceEvidence(
                source=c.source,
                confidence=float(c.confidence or 0.0),
                bbox=list(c.bbox) if c.bbox else None,
                center=list(c.center) if c.center else None,
                element=c.element,
                raw=dict(c.raw or {}),
                available=True,
            )
            source_evidence.append(ev)
            source_by_name[c.source] = ev

        # Fuente primaria: UIA primero (propiedades reales de control), luego
        # la de mayor confianza entre las restantes.
        primary = self._select_primary(cluster)

        # Nombre, tipo y texto fusionados (sin inventar tipos nuevos)
        name = self._merged_name(cluster, primary)
        fused_type = self._merged_type(cluster, primary)
        text = self._merged_text(cluster, primary)
        description = self._merged_description(cluster, primary)

        # Geometria: union de cajas (cubre toda la evidencia); centro derivado
        merged_bbox = _merge_bboxes([ev.bbox for ev in source_evidence])
        merged_center = _box_center(merged_bbox) if merged_bbox else None

        # Confianza fusionada: media de fuentes disponibles, sin dejar que una
        # fuente con alta confianza compense la ausencia de otra.
        confidences = [ev.confidence for ev in source_evidence if ev.available]
        merged_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        # Interactividad solo con evidencia real (patron UIA o Qwen3-VL +
        # evidencia visual). OpenCV y OmniParser solos no la establecen.
        interactive = False
        interactive_evidence: List[str] = []
        disagreements: List[str] = []

        uia_ev = source_by_name.get(SOURCE_UIA)
        if uia_ev and uia_ev.element:
            patterns = uia_ev.raw.get("patterns", []) or []
            enabled = bool(uia_ev.element.interactive)
            visible = uia_ev.raw.get("visible", True)
            offscreen = uia_ev.raw.get("is_offscreen", False)
            has_actionable = bool(
                set(str(p) for p in patterns) & ACTIONABLE_PATTERNS
            )
            if has_actionable and enabled and visible and not offscreen:
                interactive = True
                interactive_evidence.append(SOURCE_UIA)
            elif has_actionable and not (enabled and visible and not offscreen):
                disagreements.append(
                    "UIA reporta patron de accion pero el control no esta "
                    "habilitado/visible o esta fuera de pantalla"
                )

        # Qwen3-VL semantica: asociar evidencia por referencia o solapamiento
        extra_refs: List[str] = []
        for c in cluster:
            if c.raw:
                for key in ("name", "automation_id"):
                    v = c.raw.get(key)
                    if v and str(v).strip():
                        extra_refs.append(str(v).strip())
        qwen_match = self._match_qwen3vl(
            name, text, merged_bbox, qwen3vl_evidence or [],
            extra_refs=extra_refs,
        )
        if qwen_match is not None:
            qwen_evidence, qwen_meta = qwen_match
            qwen_el = UIElementData(
                name=qwen_meta.get("label_association") or name or "element",
                type="element",
                text=str(qwen_meta.get("label_association") or ""),
                description=str(qwen_meta.get("apparent_function") or ""),
                confidence=float(qwen_meta.get("confidence", 0.0) or 0.0),
                calibrated=False,
            )
            qwen_source_ev = SourceEvidence(
                source=SOURCE_QWEN3VL,
                confidence=qwen_el.confidence,
                bbox=list(qwen_meta.get("bbox")) if qwen_meta.get("bbox") else None,
                center=_box_center(qwen_meta.get("bbox")) if qwen_meta.get("bbox") else None,
                element=qwen_el,
                raw=dict(qwen_meta),
                available=True,
            )
            source_evidence.append(qwen_source_ev)
            source_by_name[SOURCE_QWEN3VL] = qwen_source_ev

            if qwen_meta.get("is_actionable") and qwen_meta.get("evidence_visual"):
                interactive = True
                interactive_evidence.append(SOURCE_QWEN3VL)
            if qwen_meta.get("is_actionable") and not qwen_meta.get("evidence_visual"):
                disagreements.append(
                    "Qwen3-VL marca el elemento como accionable sin evidencia visual"
                )
            if qwen_meta.get("apparent_function"):
                if not description:
                    description = str(qwen_meta["apparent_function"])
                elif str(qwen_meta["apparent_function"]) not in description:
                    description = description + " | " + str(qwen_meta["apparent_function"])

        # Clasificacion del candidato segun la evidencia de interactividad.
        # Solo UIA_ACTIONABLE acredita interactividad verificada (patron UIA
        # utilizable, habilitado, visible y dentro de pantalla). Un icono
        # detectado solo visualmente queda como candidato sin verificar.
        fused_element = UIElementData(
            name=name,
            type=fused_type,
            text=text,
            description=description,
            bbox=merged_bbox,
            center=[int(round(c)) for c in merged_center] if merged_center else None,
            confidence=merged_confidence,
        )
        uia_ev = source_by_name.get(SOURCE_UIA)
        uia_raw = uia_ev.raw if (uia_ev is not None and uia_ev.raw) else {}
        classification = classify_element(
            fused_element,
            uia_patterns=uia_raw.get("patterns", []),
            enabled=uia_raw.get("is_enabled"),
            visible=uia_raw.get("visible"),
            offscreen=uia_raw.get("is_offscreen"),
        )

        # Desacuerdos de geometria entre fuentes del mismo cluster
        bboxes = [ev.bbox for ev in source_evidence if ev.bbox and len(ev.bbox) == 4]
        if len(bboxes) >= 2:
            base = bboxes[0]
            for other in bboxes[1:]:
                if _iou(base, other) < 0.15:
                    disagreements.append(
                        "Fuentes discrepan sobre la geometria del elemento "
                        "(solapamiento bajo entre cajas)"
                    )
                    break

        # Desacuerdo de tipo entre fuentes
        types = [
            ev.element.type for ev in source_evidence
            if ev.element and ev.element.type not in ("element", "unknown", "")
        ]
        if len(set(types)) > 1:
            disagreements.append(
                "Fuentes discrepan sobre el tipo del elemento: %s" % ", ".join(sorted(set(types)))
            )

        # Refinamiento OpenCV (pista geometrica solamente, nunca interactividad)
        opencv_hint: Optional[Dict[str, Any]] = None
        if image_path and merged_bbox:
            try:
                from src.eyes.vision.vision import VisionOpenCVProcessor
                image = VisionOpenCVProcessor.load_image(image_path)
                refinement = None
                if image is not None:
                    refinement = VisionOpenCVProcessor.refine_bounds(image, merged_bbox)
            except Exception:
                image = None
                refinement = None
            if refinement and refinement.get("ok") and refinement.get("refined_bbox"):
                opencv_hint = refinement
                opencv_el = UIElementData(
                    name=name or "element",
                    type=fused_type,
                    text=text,
                    bbox=list(refinement["refined_bbox"]),
                    center=_box_center(refinement["refined_bbox"]),
                    confidence=merged_confidence,
                    calibrated=False,
                )
                source_evidence.append(
                    SourceEvidence(
                        source=SOURCE_OPENCV,
                        confidence=merged_confidence,
                        bbox=list(refinement["refined_bbox"]),
                        center=_box_center(refinement["refined_bbox"]),
                        element=opencv_el,
                        raw={"refinement": refinement, "hint_only": True},
                        available=True,
                    )
                )
                source_by_name[SOURCE_OPENCV] = source_evidence[-1]

        canonical_id = self._canonical_id(name, fused_type, screen, cluster_index)

        return FusedCandidate(
            canonical_id=canonical_id,
            name=name,
            type=fused_type,
            text=text,
            description=description,
            bbox=merged_bbox,
            center=list(merged_center) if merged_center else None,
            screen=int(screen),
            window_handle=window_handle,
            process_id=process_id,
            sources=source_evidence,
            merged_confidence=round(float(merged_confidence), 4),
            agreement=len(disagreements) == 0,
            disagreements=disagreements,
            interactive=interactive,
            interactive_evidence=interactive_evidence,
            calibrated=False,
            classification=classification,
        )

    # ------------------------------------------------------------------
    # Helpers de fusion de atributos
    # ------------------------------------------------------------------
    def _select_primary(self, cluster: List[DetectedCandidate]) -> DetectedCandidate:
        return min(cluster, key=lambda c: (_source_priority(c.source), -float(c.confidence or 0.0)))

    def _merged_name(self, cluster: List[DetectedCandidate], primary: DetectedCandidate) -> str:
        if primary.element and str(primary.element.name or "").strip():
            return str(primary.element.name).strip()
        for c in cluster:
            if c.source == SOURCE_PADDLEOCR and c.element and str(c.element.text or "").strip():
                return str(c.element.text).strip()
        if primary.raw and str(primary.raw.get("name", "")).strip():
            return str(primary.raw["name"]).strip()
        return ""

    def _merged_type(self, cluster: List[DetectedCandidate], primary: DetectedCandidate) -> str:
        # Tipo canonico de la fuente primaria si es valido y no generico
        if primary.element:
            t = normalize_element_type(primary.element.type)
            if t not in ("element", "unknown", ""):
                return t
        # Cualquier fuente con tipo especifico valido
        for c in cluster:
            if c.element:
                t = normalize_element_type(c.element.type)
                if t not in ("element", "unknown", ""):
                    return t
        return "element"

    def _merged_text(self, cluster: List[DetectedCandidate], primary: DetectedCandidate) -> str:
        for c in cluster:
            if c.source == SOURCE_PADDLEOCR and c.element and str(c.element.text or "").strip():
                return str(c.element.text).strip()
        if primary.element and str(primary.element.text or "").strip():
            return str(primary.element.text).strip()
        if primary.element and str(primary.element.name or "").strip():
            return str(primary.element.name).strip()
        return ""

    def _merged_description(self, cluster: List[DetectedCandidate], primary: DetectedCandidate) -> str:
        parts: List[str] = []
        if primary.element and str(primary.element.description or "").strip():
            parts.append(str(primary.element.description).strip())
        for c in cluster:
            raw_desc = (c.raw or {}).get("apparent_function")
            if raw_desc and str(raw_desc).strip() and str(raw_desc).strip() not in parts:
                parts.append(str(raw_desc).strip())
        return " | ".join(parts)

    def _match_qwen3vl(
        self,
        name: str,
        text: str,
        bbox: Optional[List[int]],
        evidence: List[Dict[str, Any]],
        extra_refs: Optional[List[str]] = None,
    ) -> Optional[tuple]:
        """Asocia una evidencia Qwen3-VL al candidato por referencia o bbox.

        ``extra_refs`` permite pasar identificadores adicionales del candidato
        (nombre bruto, automation_id) que el nombre normalizado puede no
        conservar (por ejemplo, cuando la ventana no expone nombre en UIA).
        """
        if not evidence:
            return None
        target_refs = {r for r in (name, text) if r}
        if extra_refs:
            target_refs.update(r for r in extra_refs if r)
        for ev in evidence:
            ref = str(ev.get("reference", "") or "").strip()
            if not ref:
                continue
            if ref in target_refs:
                return ev, ev
            if target_refs and any(
                t and (ref == t or ref in t or t in ref) for t in target_refs
            ):
                return ev, ev
            ev_bbox = ev.get("bbox")
            if bbox and ev_bbox and _iou(bbox, ev_bbox) >= self.containment_iou_threshold:
                return ev, ev
        return None

    def _canonical_id(
        self, name: str, fused_type: str, screen: int, cluster_index: int
    ) -> str:
        norm_name = UIElementData.normalize_name(name) or "element"
        norm_type = normalize_element_type(fused_type) or "element"
        return "fusion:%s:%s:s%d:c%d" % (norm_type, norm_name, int(screen), int(cluster_index))


__all__ = [
    "VisualUIDetectorFusion",
    "DetectedCandidate",
    "SourceEvidence",
    "FusedCandidate",
    "FusionResult",
    "SOURCE_UIA",
    "SOURCE_OMNIPARSER",
    "SOURCE_PADDLEOCR",
    "SOURCE_QWEN3VL",
    "SOURCE_OPENCV",
    "ALL_SOURCES",
    "ACTIONABLE_PATTERNS",
    "IOU_MERGE_THRESHOLD",
    "CENTER_MERGE_THRESHOLD_PIX",
    "CONTAINMENT_IOU_THRESHOLD",
    "TEXT_PROXIMITY_MAX_CENTER_DIST_PIX",
]
