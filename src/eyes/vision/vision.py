# src/eyes/vision/vision.py
"""
Vision por computadora usando Qwen3-VL mediante Ollama.

La capa de vision es generica: no contiene coordenadas, offsets, resoluciones
ni logica especifica de Chrome u otra aplicacion. La geometria de monitores
pertenece a ScreenManager y la calibracion universal pertenece a
UniversalVisualCalibrator / CalibrationManager.
"""

from __future__ import annotations

import io
import json
import math
import os
import tempfile
import time
import cv2
import numpy as np
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import ollama
from PIL import Image as PILImage
from pydantic import BaseModel, Field

from src.eyes.capture.screen_capture import ScreenCapture
from src.eyes.capture.screen import ApplicationInfo, ApplicationState
from src.memory.storage import MemoryType, WorldState, get_memory_manager
from src.core.log import get_logger
from src.core.ui_element_model import UIElementData, normalize_element_type

logger = get_logger(__name__)

# Modelo por defecto: variante "instruct" de Qwen3-VL. La variante con
# razonamiento (``qwen3-vl:8b``) gasta el presupuesto de salida en
# ``message.thinking`` y deja ``message.content`` vacio, por lo que no sirve
# para respuestas JSON estructuradas.
DEFAULT_VISION_MODEL = "qwen3-vl:8b-instruct"

# Qwen3-VL codifica la imagen en parches de 16 px con fusion espacial 2x2:
# cada token visual cubre un bloque de 32x32 pixeles de la imagen enviada.
VISION_TOKEN_BLOCK_PX = 32

# Presupuesto de pixeles de la imagen que se envia al modelo. Una captura
# mayor se reduce (conservando la proporcion) antes de enviarla: una captura
# 4K completa son unos 8000 tokens visuales y desborda el contexto; 1920x1080
# son unos 2000.
MODEL_IMAGE_MAX_PIXELS = 1920 * 1080

# Qwen3-VL expresa las cajas en coordenadas relativas 0..1000 de la imagen,
# independientes de su resolucion.
NORMALIZED_COORD_MAX = 1000

# Maximo de elementos que se piden al modelo y se aceptan por deteccion.
DETECTION_MAX_ELEMENTS = 60

# Dos detecciones con el mismo nombre y una IoU igual o superior a este valor
# se consideran el mismo elemento repetido por el modelo.
DUPLICATE_IOU = 0.9


class VisionNodeType(Enum):
    """Tipos de nodos de vision disponibles para planificacion."""

    SCREEN_ANALYSIS = "screen_analysis"
    UI_DETECTION = "ui_detection"
    # Alias legacy: se mantiene el atributo antiguo sin cambiar el valor.
    UI_DETECTON = "ui_detection"
    ELEMENT_VERIFICATION = "element_verification"
    STATE_VERIFICATION = "state_verification"
    CALIBRATION_ANALYSIS = "calibration_analysis"
    APPLICATION_DETECTION = "application_detection"


@dataclass
class VisionNode:
    """Nodo de percepcion visual reutilizable por el planificador."""

    id: str
    type: VisionNodeType
    name: str
    description: str
    preconditions: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    cost: float = 1.0
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    application: Optional[str] = None
    ui_element: Optional[str] = None
    execute_function: Optional[str] = None
    success_criteria: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisionNode":
        payload = dict(data)
        if isinstance(payload.get("type"), str):
            payload["type"] = VisionNodeType(payload["type"])
        return cls(**payload)

    def get_preconditions(self) -> List[str]:
        return self.preconditions

    def get_effects(self) -> List[str]:
        return self.effects

    def get_cost(self) -> float:
        return self.cost


class UIElement(UIElementData):
    """Elemento UI detectado por el modelo de visi\u00f3n (forma can\u00f3nica).

    Deriva de :class:`UIElementData`, por lo que comparte el vocabulario
    can\u00f3nico (``name``, ``coordinates``, ``screen``, ``calibrated``...).
    Los elementos detectados visualmente aportan ``bbox``, ``center`` y
    ``confidence``; las coordenadas de calibraci\u00f3n y el estado
    ``calibrated`` se enriquecen en capas superiores (executor/calibrador).
    """

    model_config = {"populate_by_name": True}


class VisionResponse(BaseModel):
    """Respuesta estructurada de deteccion UI.

    ``bbox`` y ``center`` de cada elemento estan en pixeles de la imagen
    analizada (origen arriba-izquierda). ``error`` es ``None`` cuando la
    deteccion se completo, aunque no haya elementos, y describe el fallo en
    caso contrario. ``image_size`` y ``model_image_size`` son el tamano
    original y el tamano enviado al modelo; ``discarded`` cuenta las cajas
    rechazadas (fuera de rango, degeneradas o repetidas) y ``truncated``
    indica que la salida del modelo llego cortada.
    """

    elements: List[UIElement] = Field(default_factory=list)
    error: Optional[str] = None
    image_size: Optional[List[int]] = None
    model_image_size: Optional[List[int]] = None
    discarded: int = 0
    truncated: bool = False


class Vision:
    """Sistema de vision generico integrado con la arquitectura de Jarvis."""

    def __init__(self, model: str = DEFAULT_VISION_MODEL) -> None:
        self.model = model
        self.temperature = 0.0
        self.max_image_pixels = MODEL_IMAGE_MAX_PIXELS
        self.detection_max_elements = DETECTION_MAX_ELEMENTS
        # Datos de la ultima llamada a Ollama (tamanos, contexto,
        # done_reason, longitud del contenido y del razonamiento).
        self.last_chat_info: Dict[str, Any] = {}
        self.screen_capture = ScreenCapture()
        self.memory_manager = get_memory_manager()
        self._vision_nodes = self._create_vision_nodes()


    # ====================================================================
    # NODOS DE VISION
    # ====================================================================

    def _create_vision_nodes(self) -> List[VisionNode]:
        return [
            VisionNode(
                id="vision.analyze_screen",
                type=VisionNodeType.SCREEN_ANALYSIS,
                name="Analizar pantalla completa",
                description="Analiza las pantallas disponibles para construir el estado del mundo",
                preconditions=["screen_available"],
                effects=["world_state_updated", "applications_detected"],
                cost=5.0,
                execute_function="analyze_screen_for_world_state",
                success_criteria=["world_state_valid"],
                metadata={"captures": ["available_monitors"], "output": "WorldState"},
            ),
            VisionNode(
                id="vision.detect_ui_elements",
                type=VisionNodeType.UI_DETECTION,
                name="Detectar elementos UI",
                description="Detecta elementos interactivos en una imagen",
                preconditions=["image_available"],
                effects=["ui_elements_detected"],
                cost=3.0,
                execute_function="detect_ui_elements",
                success_criteria=["elements_valid"],
                metadata={"input": "image_path", "output": "VisionResponse"},
            ),
            VisionNode(
                id="vision.verify_element",
                type=VisionNodeType.ELEMENT_VERIFICATION,
                name="Verificar elemento UI",
                description="Verifica si un elemento UI espec\u00edfico es visible",
                preconditions=["element_name_known", "screen_available"],
                effects=["element_verified", "element_coordinates"],
                cost=2.0,
                execute_function="verify_element_visibility",
                success_criteria=["element_found", "coordinates_valid"],
                metadata={"requires": "element_name", "output": "element_info"},
            ),
            VisionNode(
                id="vision.verify_action_result",
                type=VisionNodeType.STATE_VERIFICATION,
                name="Verificar resultado de acci\u00f3n",
                description="Comprueba visualmente el efecto esperado de una acci\u00f3n",
                preconditions=["action_executed", "expected_state_known"],
                effects=["result_verified", "state_confirmed"],
                cost=2.5,
                execute_function="verify_action_result",
                success_criteria=["expected_state_matched"],
                metadata={"requires": ["expected_state", "tolerance"], "output": "verification_result"},
            ),
            VisionNode(
                id="vision.analyze_for_calibration",
                type=VisionNodeType.CALIBRATION_ANALYSIS,
                name="Analizar para calibraci\u00f3n",
                description="Analiza una captura para encontrar elementos UI calibrables",
                preconditions=["calibration_target_known", "image_available"],
                effects=["calibration_candidates_found"],
                cost=3.5,
                execute_function="analyze_image",
                success_criteria=["candidates_valid"],
                metadata={"input": ["image_path", "calibration_prompt"], "output": "calibration_data"},
            ),
            VisionNode(
                id="vision.detect_application",
                type=VisionNodeType.APPLICATION_DETECTION,
                name="Detectar aplicaci\u00f3n",
                description="Detecta visualmente una aplicaci\u00f3n y su estado en las pantallas analizadas",
                preconditions=["app_name_known", "screen_available"],
                effects=["application_state_detected"],
                cost=2.0,
                execute_function="detect_application_state",
                success_criteria=["state_determined"],
                metadata={"requires": "app_name", "output": "ApplicationInfo"},
            ),
        ]

    def get_vision_nodes(self) -> List[VisionNode]:
        return list(self._vision_nodes)

    def get_vision_node(self, node_id: str) -> Optional[VisionNode]:
        return next((node for node in self._vision_nodes if node.id == node_id), None)

    def get_nodes_by_type(self, node_type: VisionNodeType) -> List[VisionNode]:
        return [node for node in self._vision_nodes if node.type == node_type]

    def get_total_vision_cost(self) -> float:
        return sum(node.get_cost() for node in self._vision_nodes)

    # ====================================================================
    # MONITORES
    # ====================================================================

    def _get_available_monitor_numbers(self) -> List[int]:
        """Obtiene los identificadores logicos reales desde ScreenManager."""
        try:
            from src.desktop.screen_manager import get_screen_manager

            screen_manager = get_screen_manager()
            refresh = getattr(screen_manager, "refresh_monitors", None)
            if callable(refresh):
                refresh()

            monitors = list(getattr(screen_manager, "monitors", []) or [])
            numbers: List[int] = []
            for position, monitor in enumerate(monitors, start=1):
                candidate = getattr(monitor, "monitor_id", None)
                if not isinstance(candidate, int) or candidate < 1:
                    candidate = getattr(monitor, "index", None)
                    if not isinstance(candidate, int) or candidate < 1:
                        candidate = position
                if candidate not in numbers:
                    numbers.append(candidate)
            return numbers or [1]
        except Exception as exc:
            logger.debug("Vision._get_available_monitor_numbers: %s", exc)
            return [1]

    def _get_default_monitor_number(self) -> int:
        """Selecciona el monitor activo y, como fallback, el principal."""
        try:
            from src.desktop.screen_manager import get_screen_manager

            screen_manager = get_screen_manager()
            refresh = getattr(screen_manager, "refresh_monitors", None)
            if callable(refresh):
                refresh()

            active = getattr(screen_manager, "get_active_monitor", lambda: None)()
            monitor = active or getattr(screen_manager, "get_primary_monitor", lambda: None)()
            number = getattr(monitor, "monitor_id", None) if monitor else None
            if isinstance(number, int) and number > 0:
                return number
        except Exception as exc:
            logger.debug("Vision._get_default_monitor_number: %s", exc)

        monitors = self._get_available_monitor_numbers()
        return monitors[0]

    # ====================================================================
    # ESTADO DEL MUNDO
    # ====================================================================

    def analyze_screen_for_world_state(self) -> WorldState:
        """Analiza todas las pantallas disponibles y construye un WorldState valido."""
        logger.info(r"[VISION] Analizando pantallas para estado del mundo...")
        timestamp = time.time()
        monitor_numbers = self._get_available_monitor_numbers()

        applications: Dict[str, Dict[str, Any]] = {}
        ui_elements: Dict[str, Dict[str, Any]] = {}
        focused_application: Optional[str] = None
        active_monitor = self._get_default_monitor_number()
        visible_text: List[str] = []

        prompt = """
Analiza exclusivamente la interfaz visible de ESTA pantalla.

Determina:
1. Aplicaciones abiertas y visibles.
2. Cu\u00e1l parece estar en primer plano.
3. Elementos UI visibles y claramente interactivos.
4. Texto relevante visible.
5. Si una ventana parece maximizada, normal o minimizada cuando exista evidencia visual.

Devuelve \u00daNICAMENTE JSON v\u00e1lido:
{
  "applications": [
    {
      "name": "chrome",
      "state": "active|open|maximized|minimized|closed",
      "window_title": "t\u00edtulo visible",
      "visible_elements": ["address_bar", "tabs"]
    }
  ],
  "focused_application": "chrome",
  "visible_elements": [
    {"name": "address_bar", "type": "input", "text": "", "interactive": true}
  ],
  "visible_text": "texto relevante"
}
"""

        for monitor_number in monitor_numbers:
            image_path = None
            try:
                image_path = self.screen_capture.capture_monitor(monitor_number)
                if not image_path:
                    pass

                response = self._chat_json(
                    image_path=image_path,
                    prompt=prompt,
                    num_ctx=8192,
                    num_predict=4096,
                    temperature=self.temperature,
                )
                if not response:
                    continue

                data = self._safe_json_loads(response)
                if not isinstance(data, dict):
                    continue

                candidate_focus = data.get("focused_application")
                if candidate_focus:
                    focused_application = str(candidate_focus)
                    active_monitor = monitor_number

                text_value = data.get("visible_text")
                if text_value:
                    visible_text.append(str(text_value))

                for app_data in data.get("applications", []) or []:
                    if not isinstance(app_data, dict):
                        continue
                    app_name = str(app_data.get("name", "unknown") or "unknown").strip()
                    if not app_name:
                        continue
                    state = str(app_data.get("state", "closed") or "closed").lower()
                    application_record = {
                        "name": app_name,
                        "state": state,
                        "window_title": app_data.get("window_title"),
                        "monitor": monitor_number,
                        "visible_elements": list(app_data.get("visible_elements", []) or []),
                    }
                    applications[app_name] = application_record

                for index, element in enumerate(data.get("visible_elements", []) or []):
                    if not isinstance(element, dict):
                        continue
                    element_name = str(element.get("name") or element.get("text") or f"element_{index}")
                    key = f"monitor_{monitor_number}:{element_name}"
                    ui_elements[key] = {
                        "name": element_name,
                        "type": normalize_element_type(element.get("type", "other")),
                        "text": element.get("text", ""),
                        "interactive": bool(element.get("interactive", True)),
                        "monitor": monitor_number,
                    }
            except Exception as exc:
                logger.debug("Vision.analyze_screen_for_world_state: %s", exc)

        calibrated_elements: Dict[str, Any] = {}
        try:
            state_data = self.memory_manager.storage.load(MemoryType.STATE)
            if isinstance(state_data, dict):
                calibrated_elements = dict(state_data.get("calibrated_elements", {}) or {})
        except Exception as exc:
            logger.debug("Vision.analyze_screen_for_world_state: %s", exc)

        known_urls: Dict[str, str] = {}
        try:
            entities = self.memory_manager.get_entities_by_type("streamer") or []
            platforms = self.memory_manager.get_entities_by_type("platform") or []
            for entity in list(entities) + list(platforms):
                properties = getattr(entity, "properties", {}) or {}
                url = properties.get("url")
                if url:
                    known_urls[str(entity.name)] = str(url)
        except Exception as exc:
            logger.debug("Vision.analyze_screen_for_world_state: %s", exc)

        system_info = {
            "focused_application": focused_application,
            "active_monitor": active_monitor,
            "available_monitors": monitor_numbers,
            "visible_text": "\n".join(visible_text),
            "calibrated_elements": calibrated_elements,
            "known_urls": known_urls,
        }

        world_state = WorldState(
            timestamp=timestamp,
            applications=applications,
            ui_elements=ui_elements,
            system_info=system_info,
            constraints=[],
            last_actions=[],
            active_goals=[],
        )

        try:
            self.memory_manager.save_world_state(world_state.to_dict())
        except Exception as exc:
            logger.debug("Vision.analyze_screen_for_world_state: %s", exc)

        return world_state

    # ====================================================================
    # DETECCION UI
    # ====================================================================

    def detect_ui_elements(
        self,
        image_path: str,
        application: Optional[str] = None,
        refine_with_opencv: bool = False,
    ) -> VisionResponse:
        """Detecta elementos interactivos visibles en una imagen.

        Qwen3-VL devuelve cada caja en coordenadas normalizadas 0..1000 de la
        imagen; aqui se convierten a pixeles de la imagen original, de modo
        que ``bbox`` y ``center`` del resultado estan siempre en pixeles de
        ``image_path`` aunque al modelo se le envie una copia reducida (ver
        ``_prepare_model_image``). Las cajas fuera de rango o degeneradas y
        los elementos repetidos se descartan y se cuentan en ``discarded``.
        Si la salida llega cortada se recuperan los elementos completos.
        Cualquier fallo (imagen ilegible, error de Ollama, respuesta vacia o
        no interpretable) se registra como aviso y se devuelve en ``error``.

        Cuando ``refine_with_opencv`` es verdadero, se prepara un recorte
        de cada elemento detectado y se refinan sus limites con OpenCV
        (bordes/contornos). Ese refinamiento es solo una pista geometrica:
        nunca modifica el campo ``interactive`` ni constituye prueba de
        que el elemento sea interactuable.
        """

        result = VisionResponse()
        image_size = self._image_size(image_path)
        if image_size is None:
            result.error = "no se pudo leer la imagen %s" % image_path
            logger.warning("[VISION] detect_ui_elements: %s", result.error)
            return result
        width, height = image_size
        result.image_size = [width, height]
        max_elements = max(1, int(self.detection_max_elements))

        app_context = f" en {application}" if application else ""
        prompt = f"""
Analiza la captura de pantalla y detecta los elementos interactivos visibles{app_context}.

Incluye botones, campos de texto, b\u00fasquedas, enlaces, pesta\u00f1as, men\u00fas,
checkboxes, radios, selects, listas, sliders, switches, iconos pulsables y
controles de navegaci\u00f3n. No incluyas fondos, texto decorativo ni elementos
no interactivos.

Devuelve exclusivamente JSON v\u00e1lido con esta estructura:
{{
  "elements": [
    {{
      "name": "boton_abrir",
      "type": "button",
      "text": "Abrir",
      "bbox": [x1, y1, x2, y2],
      "interactive": true,
      "confidence": 0.95
    }}
  ]
}}

REGLAS:
- bbox es la caja del elemento en coordenadas NORMALIZADAS de 0 a {NORMALIZED_COORD_MAX} relativas a TODA la imagen: x sobre el ancho, y sobre el alto.
- x1 < x2 e y1 < y2. No uses pixeles ni coordenadas de pantalla.
- M\u00e1ximo {max_elements} elementos; cada elemento aparece una sola vez.
- name en min\u00fasculas y con "_" entre palabras.
- confidence entre 0.0 y 1.0.
"""

        schema = {
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "maxItems": max_elements,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "text": {"type": "string"},
                            "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                            "interactive": {"type": "boolean"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["name", "type", "text", "bbox", "interactive", "confidence"],
                    },
                }
            },
            "required": ["elements"],
        }

        try:
            raw = self._chat_json(
                image_path=image_path,
                prompt=prompt,
                response_format=schema,
                num_ctx=8192,
                num_predict=4096,
                temperature=self.temperature,
            )
        except Exception as exc:
            result.error = "fallo la llamada al modelo %s: %s" % (self.model, exc)
            logger.warning("[VISION] detect_ui_elements: %s", result.error)
            return result

        info = dict(self.last_chat_info or {})
        if info.get("model_image_size"):
            result.model_image_size = list(info["model_image_size"])
        result.truncated = info.get("done_reason") == "length"

        items, parse_error, salvaged = self._parse_detection_items(raw)
        if items is None:
            result.error = parse_error
            logger.warning("[VISION] detect_ui_elements: %s", result.error)
            return result
        if salvaged:
            result.truncated = True

        try:
            valid_elements: List[UIElement] = []
            accepted: List[Tuple[str, List[int]]] = []
            discarded = 0
            for item in items:
                if len(valid_elements) >= max_elements or not isinstance(item, dict):
                    discarded += 1
                    continue
                bbox = self._normalized_bbox_to_pixels(item.get("bbox"), width, height)
                if bbox is None:
                    discarded += 1
                    continue
                center = [(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2]
                # El nombre es la clave can\u00f3nica de direccionamiento;
                # cuando el modelo no lo devuelve se infiere de text/type.
                element_name = (
                    str(item.get("name") or "").strip()
                    or str(item.get("text") or "").strip()
                    or str(item.get("type") or "").strip()
                )
                name_key = element_name.lower()
                if any(key == name_key and self._box_iou(box, bbox) >= DUPLICATE_IOU for key, box in accepted):
                    discarded += 1
                    continue
                try:
                    element = UIElement(
                        name=element_name or f"element_{len(valid_elements)}",
                        type=normalize_element_type(str(item.get("type", "other"))),
                        text=str(item.get("text", "") or ""),
                        description=str(item.get("description", "") or ""),
                        bbox=bbox,
                        center=center,
                        interactive=bool(item.get("interactive", True)),
                        confidence=self._clamp_float(item.get("confidence", 0.0)),
                    )
                except Exception as exc:
                    logger.debug("[VISION] Elemento descartado (%s): %s", element_name, exc)
                    discarded += 1
                    continue
                valid_elements.append(element)
                accepted.append((name_key, bbox))

            result.discarded = discarded
            if discarded:
                logger.warning(
                    "[VISION] detect_ui_elements: %s de %s cajas descartadas "
                    "(fuera de 0..%s, degeneradas, repetidas o por encima del maximo)",
                    discarded,
                    len(items),
                    NORMALIZED_COORD_MAX,
                )

            if refine_with_opencv:
                image = VisionOpenCVProcessor.load_image(image_path)
                if image is not None:
                    refined_elements: List[UIElement] = []
                    for element in valid_elements:
                        bbox = list(element.bbox) if element.bbox else None
                        if bbox:
                            refinement = VisionOpenCVProcessor.refine_bounds(image, bbox)
                            if refinement["ok"] and refinement["refined_bbox"]:
                                refined_bbox = refinement["refined_bbox"]
                                element.bbox = refined_bbox
                                element.center = [
                                    (refined_bbox[0] + refined_bbox[2]) // 2,
                                    (refined_bbox[1] + refined_bbox[3]) // 2,
                                ]
                            # hint_only: contornos y bordes nunca marcan el
                            # elemento como interactivo.
                        refined_elements.append(element)
                    valid_elements = refined_elements

            result.elements = valid_elements
            return result
        except Exception as exc:
            result.elements = []
            result.error = "fallo procesando la respuesta del modelo: %s" % exc
            logger.warning("[VISION] detect_ui_elements: %s", result.error)
            return result

    def _parse_detection_items(self, raw: Any) -> Tuple[Optional[List[Any]], Optional[str], bool]:
        """Extrae la lista ``elements`` de la respuesta del modelo.

        Devuelve ``(items, error, recuperado)``. Si el JSON no es valido pero
        contiene objetos completos de ``elements`` (salida cortada por
        ``num_predict``), los recupera y marca ``recuperado``.
        """
        text = str(raw or "").strip()
        if not text:
            return None, self._empty_response_error(), False
        data = self._safe_json_loads(text)
        if isinstance(data, dict):
            elements = data.get("elements")
            if isinstance(elements, list):
                return elements, None, False
            return None, "la respuesta del modelo %s no contiene una lista 'elements'" % self.model, False
        salvaged = self._salvage_elements(text)
        if salvaged:
            logger.warning(
                "[VISION] Respuesta JSON incompleta (%s caracteres): se recuperan %s elementos completos",
                len(text),
                len(salvaged),
            )
            return salvaged, None, True
        return None, "respuesta del modelo %s no interpretable como JSON (%s caracteres)" % (self.model, len(text)), False

    def _empty_response_error(self) -> str:
        info = self.last_chat_info or {}
        done_reason = info.get("done_reason")
        thinking_chars = int(info.get("thinking_chars") or 0)
        if thinking_chars:
            return "el modelo %s no devolvio contenido (done_reason=%s, razonamiento de %s caracteres)%s" % (
                self.model,
                done_reason,
                thinking_chars,
                self._thinking_hint(),
            )
        return "el modelo %s devolvio una respuesta vacia (done_reason=%s)" % (self.model, done_reason)

    @staticmethod
    def _salvage_elements(text: str) -> List[Dict[str, Any]]:
        """Recupera los objetos completos de la lista ``elements`` de un JSON cortado."""
        decoder = json.JSONDecoder()
        key = text.find('"elements"')
        start = text.find("[", key if key >= 0 else 0)
        if start < 0:
            return []
        items: List[Dict[str, Any]] = []
        index = start + 1
        length = len(text)
        while index < length:
            while index < length and text[index] in " \t\r\n,":
                index += 1
            if index >= length or text[index] != "{":
                break
            try:
                value, index = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                break
            if isinstance(value, dict):
                items.append(value)
        return items

    @staticmethod
    def _normalized_bbox_to_pixels(values: Any, width: int, height: int) -> Optional[List[int]]:
        """Caja normalizada 0..1000 de Qwen3-VL -> ``[x1, y1, x2, y2]`` en pixeles de la imagen.

        Devuelve ``None`` si la caja no tiene 4 numeros, sale del rango
        0..1000, esta invertida o queda sin area al pasar a pixeles.
        """
        if not isinstance(values, (list, tuple)) or len(values) != 4 or width <= 0 or height <= 0:
            return None
        try:
            x1, y1, x2, y2 = [float(v) for v in values]
        except (TypeError, ValueError):
            return None
        for value in (x1, y1, x2, y2):
            if math.isnan(value) or value < 0.0 or value > NORMALIZED_COORD_MAX:
                return None
        if x2 <= x1 or y2 <= y1:
            return None
        box = [
            int(round(x1 * width / NORMALIZED_COORD_MAX)),
            int(round(y1 * height / NORMALIZED_COORD_MAX)),
            int(round(x2 * width / NORMALIZED_COORD_MAX)),
            int(round(y2 * height / NORMALIZED_COORD_MAX)),
        ]
        if box[2] <= box[0] or box[3] <= box[1]:
            return None
        return box

    @staticmethod
    def _box_iou(a: List[int], b: List[int]) -> float:
        ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        if inter <= 0:
            return 0.0
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return float(inter) / float(union) if union > 0 else 0.0

    # ====================================================================
    # CALIBRACION UNIVERSAL
    # ====================================================================

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        calibration_target: Optional[str] = None,
        timeout: Optional[float] = None,
        num_predict: int = 4096,
    ) -> str:
        """
        Analiza una captura para calibracion universal.

        ``timeout``: presupuesto total de la llamada a Ollama (ver
        ``_chat_json``); ``num_predict``: tokens maximos de la respuesta.

        IMPORTANTE: este metodo devuelve el JSON del modelo como string porque
        UniversalVisualCalibrator y los calibradores legacy ya utilizan ese
        contrato. No convierte aqui coordenadas ni aplica offsets de monitor.
        """

        schema = {
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "text": {"type": "string"},
                            "description": {"type": "string"},
                            "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                            "center": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                            "confidence": {"type": "number"},
                            "interactive": {"type": "boolean"},
                        },
                        "required": ["name", "type", "bbox", "confidence"],
                    },
                }
            },
            "required": ["elements"],
        }

        try:
            result = self._chat_json(
                image_path=image_path,
                prompt=prompt,
                response_format=schema,
                num_ctx=8192,
                num_predict=int(num_predict),
                temperature=0.0,
                timeout=timeout,
            )
            if not result:
                logger.warning(r"[VISION] Qwen devolvio una respuesta vacia")
                return ""

            # Mantener el contrato string para UVC/chrome_calibrator.
            data = self._safe_json_loads(result)
            if isinstance(data, dict) and calibration_target:
                target = calibration_target.strip().lower()
                elements = []
                for element in data.get("elements", []) or []:
                    if not isinstance(element, dict):
                        continue
                    name = str(element.get("name", "") or "").lower()
                    text = str(element.get("text", "") or "").lower()
                    if target in name or target in text:
                        elements.append(element)
                data["elements"] = elements
                result = json.dumps(data, ensure_ascii=False)

            return result
        except ollama.ResponseError as exc:
            logger.warning("[VISION] analyze_image con %s: %s", self.model, exc)
            return f"ERROR: {exc}"
        except Exception as exc:
            logger.warning("[VISION] analyze_image con %s: %s", self.model, exc)
            return f"ERROR: {exc}"

    # ====================================================================
    # VERIFICACION
    # ====================================================================

    def verify_element_visibility(
        self,
        element_name: str,
        application: Optional[str] = None,
        expected_coords: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verifica visualmente si un elemento esta presente."""

        try:
            image_path = None
            if application:
                image_path = self.screen_capture.capture_active_window()
            if not image_path:
                image_path = self.screen_capture.capture_monitor(self._get_default_monitor_number())
            if not image_path:
                return {"success": False, "element": element_name, "verified": False, "error": "No se pudo capturar pantalla"}

            ui_response = self.detect_ui_elements(image_path, application)
            if ui_response.error:
                # Un fallo de deteccion no equivale a "elemento no visible".
                return {"success": False, "element": element_name, "verified": False, "error": ui_response.error}
            target = str(element_name or "").strip().lower()

            for element in ui_response.elements:
                if target and not element.matches_name(target):
                    continue
                coords_match = self._coordinates_match(expected_coords, element.center, element.bbox)
                return {
                    "success": True,
                    "element": element_name,
                    "verified": True,
                    "found_element": {
                        "name": element.name,
                        "type": element.type,
                        "text": element.text,
                        "bbox": element.bbox,
                        "center": element.center,
                        "confidence": element.confidence,
                    },
                    "coordinates_match": coords_match,
                    "application": application,
                }

            return {
                "success": True,
                "element": element_name,
                "verified": False,
                "found_element": None,
                "error": f"Elemento '{element_name}' no detectado visualmente",
                "application": application,
            }
        except Exception as exc:
            logger.debug("Vision.verify_element_visibility: %s", exc)
            return {"success": False, "element": element_name, "verified": False, "error": str(exc)}

    def verify_action_result(
        self,
        expected_state: Dict[str, Any],
        application: Optional[str] = None,
        tolerance: float = 0.8,
    ) -> Dict[str, Any]:
        """Verifica visualmente el resultado esperado de una accion."""

        try:
            image_path = self.screen_capture.capture_active_window() if application else None
            if not image_path:
                image_path = self.screen_capture.capture_monitor(self._get_default_monitor_number())
            if not image_path:
                return {"success": False, "verified": False, "error": "No se pudo capturar pantalla"}

            expected_type = str(expected_state.get("type", "unknown") or "unknown")
            prompt = self._build_verification_prompt(expected_type, expected_state, application)

            result = self._chat_json(
                image_path=image_path,
                prompt=prompt,
                num_ctx=4096,
                num_predict=1024,
                temperature=0.1,
            )
            data = self._safe_json_loads(result)
            if not isinstance(data, dict):
                return {"success": False, "verified": False, "error": "Respuesta no v\u00e1lida del modelo de visi\u00f3n"}

            verified = bool(data.get("verified", False))
            confidence = self._clamp_float(data.get("confidence", 0.0))
            success = verified and confidence >= tolerance

            response = {
                "success": True,
                "verified": success,
                "confidence": confidence,
                "details": str(data.get("details", "") or ""),
                "expected_state": expected_state,
                "tolerance": tolerance,
            }
            if "current_url" in data:
                response["current_url"] = data.get("current_url")
            if "window_title" in data:
                response["window_title"] = data.get("window_title")
            return response
        except Exception as exc:
            logger.debug("Vision.verify_action_result: %s", exc)
            return {"success": False, "verified": False, "error": str(exc)}

    def _build_verification_prompt(
        self,
        expected_type: str,
        expected_state: Dict[str, Any],
        application: Optional[str],
    ) -> str:
        context = f" en {application}" if application else ""
        if expected_type == "url_loaded":
            expected_url = expected_state.get("url", "")
            return f"""
Verifica visualmente{context} si la pantalla muestra una p\u00e1gina cargada correspondiente a la URL:
{expected_url}

Responde \u00daNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": "", "current_url": ""}}
"""
        if expected_type == "element_focused":
            element_name = expected_state.get("element", "")
            return f"""
Verifica visualmente{context} si el elemento '{element_name}' est\u00e1 enfocado o activo.
Busca indicadores visibles de foco.

Responde \u00daNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": ""}}
"""
        if expected_type == "application_opened":
            app_name = expected_state.get("application", "")
            return f"""
Verifica visualmente si la aplicaci\u00f3n '{app_name}' est\u00e1 abierta y visible{context}.

Responde \u00daNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": "", "window_title": ""}}
"""
        return f"""
Analiza la pantalla y verifica si se cumple esta condici\u00f3n{context}:
{json.dumps(expected_state, ensure_ascii=False)}

Responde \u00daNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": ""}}
"""

    # ====================================================================
    # DETECCION DE ESTADO DE APLICACION
    # ====================================================================

    def detect_application_state(self, app_name: str) -> ApplicationInfo:
        """Busca una aplicacion en todas las pantallas disponibles.

        No afirma un estado solo por configuracion: si la vision no proporciona
        un ``state`` valido (ausente, nulo o desconocido), el fallback es
        :attr:`ApplicationState.CLOSED`, nunca ``OPEN``. Esto evita creencias
        falsas sobre una aplicacion abierta cuando no hay evidencia visual
        concluyente.
        """
        target = str(app_name or "").strip()
        if not target:
            return ApplicationInfo(name=target, state=ApplicationState.CLOSED)

        prompt = f"""
Analiza esta pantalla y determina si la aplicaci\u00f3n '{target}' aparece visualmente.
Distingue, solo con evidencia visible, entre activa, abierta, maximizada,
minimizada o cerrada.

Responde \u00daNICAMENTE JSON:
{{
  "detected": true,
  "state": "active|open|minimized|maximized|closed",
  "window_title": "",
  "visible_elements": [],
  "confidence": 0.0
}}
"""

        state_map = {
            "active": ApplicationState.ACTIVE,
            "open": ApplicationState.OPEN,
            "minimized": ApplicationState.MINIMIZED,
            "maximized": ApplicationState.MAXIMIZED,
            "closed": ApplicationState.CLOSED,
        }

        best: Optional[Tuple[float, ApplicationInfo]] = None
        for monitor_number in self._get_available_monitor_numbers():
            try:
                image_path = self.screen_capture.capture_monitor(monitor_number)
                if not image_path:
                    continue
                result = self._chat_json(
                    image_path=image_path,
                    prompt=prompt,
                    num_ctx=4096,
                    num_predict=1024,
                    temperature=0.1,
                )
                data = self._safe_json_loads(result)
                if not isinstance(data, dict) or not bool(data.get("detected", False)):
                    continue

                confidence = self._clamp_float(data.get("confidence", 0.0))
                # No afirmar un estado solo por configuracion: si la vision no
                # proporciona un state valido, no se asume OPEN. Se usa CLOSED
                # como fallback seguro, consistente con analyze_screen_for_world_state
                # y ScreenAnalyzer._fallback_detect_application_state.
                state_str = str(data.get("state", "closed") or "closed").lower()
                info = ApplicationInfo(
                    name=target,
                    state=state_map.get(state_str, ApplicationState.CLOSED),
                    window_title=data.get("window_title"),
                    monitor=monitor_number,
                    visible_elements=list(data.get("visible_elements", []) or []),
                )
                if best is None or confidence > best[0]:
                    best = (confidence, info)
            except Exception as exc:
                logger.debug("Vision.detect_application_state: %s", exc)

        return best[1] if best else ApplicationInfo(name=target, state=ApplicationState.CLOSED)

    # ====================================================================
    # OLLAMA / UTILIDADES
    # ====================================================================

    def _chat_json(
        self,
        image_path: str,
        prompt: str,
        response_format: Any = "json",
        num_ctx: int = 8192,
        num_predict: int = 4096,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
    ) -> str:
        """Envia la imagen y el prompt a Ollama y devuelve ``message.content``.

        ``timeout`` (segundos) es el presupuesto total de la llamada. Sin el,
        la llamada espera a que Ollama termine (comportamiento anterior). Con
        el, la respuesta se lee en streaming y, si se agota, se corta la
        conexion (Ollama deja de generar) y se devuelve lo recibido con
        ``done_reason="timeout"``: el llamador recupera los elementos
        completos. Sin GPU (pocos tokens por segundo) se obtiene parte de la
        lista en vez de bloquear la calibracion.

        Si la imagen supera ``max_image_pixels`` se envia una copia reducida
        (ver ``_prepare_model_image``) y ``num_ctx`` se amplia cuando los
        tokens visuales estimados, el prompt y ``num_predict`` no caben en el
        contexto pedido. Los datos de la llamada quedan en
        ``last_chat_info``; una salida cortada (``done_reason=length``) o un
        contenido vacio con razonamiento se registran como aviso.
        """
        payload, image_size, model_size = self._prepare_model_image(image_path)
        effective_ctx = self._required_num_ctx(model_size, prompt, num_ctx, num_predict)
        info: Dict[str, Any] = {
            "model": self.model,
            "image_size": list(image_size) if image_size else None,
            "model_image_size": list(model_size) if model_size else None,
            "num_ctx": effective_ctx,
            "num_predict": num_predict,
            "done_reason": None,
            "content_chars": 0,
            "thinking_chars": 0,
        }
        self.last_chat_info = info
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [payload],
            }
        ]
        options = {
            "temperature": temperature,
            "num_ctx": effective_ctx,
            "num_predict": num_predict,
        }
        if timeout:
            content, thinking, done_reason = self._chat_stream_with_deadline(
                messages, response_format, options, float(timeout)
            )
            info["timeout_s"] = float(timeout)
        else:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                stream=False,
                think=False,
                format=response_format,
                options=options,
                keep_alive="5m",
            )
            content, thinking, done_reason = self._read_chat_response(response)
        info["done_reason"] = done_reason
        info["content_chars"] = len(content)
        info["thinking_chars"] = len(thinking)
        if done_reason == "length":
            logger.warning(
                "[VISION] La respuesta de %s se corto al llegar a num_predict=%s "
                "(contenido %s caracteres, razonamiento %s caracteres)",
                self.model,
                num_predict,
                len(content),
                len(thinking),
            )
        if not content and thinking:
            logger.warning(
                "[VISION] %s devolvio solo razonamiento (%s caracteres) y ningun contenido%s",
                self.model,
                len(thinking),
                self._thinking_hint(),
            )
        return content

    def _chat_stream_with_deadline(
        self, messages: List[Dict[str, Any]], response_format: Any, options: Dict[str, Any], timeout: float
    ) -> Tuple[str, str, Optional[str]]:
        """Chat en streaming con presupuesto total; corta la conexion al agotarlo."""
        deadline = time.monotonic() + float(timeout)
        client = ollama.Client(timeout=float(timeout))
        stream = client.chat(
            model=self.model,
            messages=messages,
            stream=True,
            think=False,
            format=response_format,
            options=options,
            keep_alive="5m",
        )
        content_parts: List[str] = []
        thinking_parts: List[str] = []
        done_reason: Optional[str] = None
        try:
            for chunk in stream:
                content, thinking, reason = self._read_chat_response(chunk)
                # _read_chat_response recorta espacios: se conserva el texto
                # tal cual llega para no unir mal los trozos del JSON.
                raw_message = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", None)
                raw_content = (
                    raw_message.get("content", "") if isinstance(raw_message, dict)
                    else getattr(raw_message, "content", "")
                ) or ""
                content_parts.append(str(raw_content))
                if thinking:
                    thinking_parts.append(thinking)
                if reason:
                    done_reason = reason
                if time.monotonic() >= deadline:
                    done_reason = "timeout"
                    break
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        if done_reason == "timeout":
            logger.warning(
                "[VISION] %s: tiempo agotado (%.0f s); se usa la respuesta parcial (%s caracteres)",
                self.model, float(timeout), len("".join(content_parts)),
            )
        return "".join(content_parts).strip(), "".join(thinking_parts).strip(), done_reason

    def _thinking_hint(self) -> str:
        """Sugerencia de modelo cuando el actual responde solo con razonamiento."""
        if self.model == DEFAULT_VISION_MODEL:
            return ""
        return "; para respuestas JSON usar una variante sin razonamiento como %s" % DEFAULT_VISION_MODEL

    @staticmethod
    def _read_chat_response(response: Any) -> Tuple[str, str, Optional[str]]:
        """``(content, thinking, done_reason)`` de un ``ChatResponse`` o de un dict."""
        if isinstance(response, dict):
            message = response.get("message", {}) or {}
            done_reason = response.get("done_reason")
        else:
            message = getattr(response, "message", None) or {}
            done_reason = getattr(response, "done_reason", None)
        if isinstance(message, dict):
            content = message.get("content", "") or ""
            thinking = message.get("thinking", "") or ""
        else:
            content = getattr(message, "content", "") or ""
            thinking = getattr(message, "thinking", "") or ""
        reason = done_reason if isinstance(done_reason, str) and done_reason else None
        return str(content or "").strip(), str(thinking or "").strip(), reason

    @staticmethod
    def _image_size(image_path: Any) -> Optional[Tuple[int, int]]:
        """``(ancho, alto)`` en pixeles de una imagen en disco, o ``None`` si no se puede leer."""
        try:
            if not image_path or not os.path.isfile(str(image_path)):
                return None
            with PILImage.open(str(image_path)) as image:
                width, height = image.size
        except Exception as exc:
            logger.debug("[VISION] No se pudo leer el tamano de %s: %s", image_path, exc)
            return None
        if width <= 0 or height <= 0:
            return None
        return int(width), int(height)

    def _prepare_model_image(self, image_path: str) -> Tuple[Any, Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """Imagen que se envia al modelo: ``(ruta o bytes PNG, tamano original, tamano enviado)``.

        Si la imagen supera ``max_image_pixels`` se reduce conservando la
        proporcion y se envia como bytes PNG en memoria (sin ficheros
        temporales). Como las cajas de Qwen3-VL son relativas 0..1000, la
        reduccion no cambia su significado. Si la imagen no se puede leer se
        envia la ruta tal cual.
        """
        size = self._image_size(image_path)
        if size is None:
            return image_path, None, None
        width, height = size
        budget = int(self.max_image_pixels or 0)
        if budget <= 0 or width * height <= budget:
            return image_path, size, size
        scale = math.sqrt(float(budget) / float(width * height))
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        try:
            resample = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS")
            with PILImage.open(str(image_path)) as image:
                reduced = image.convert("RGB").resize(new_size, resample)
            buffer = io.BytesIO()
            reduced.save(buffer, format="PNG")
        except Exception as exc:
            logger.warning(
                "[VISION] No se pudo reducir la imagen %s (%sx%s); se envia sin reducir: %s",
                image_path,
                width,
                height,
                exc,
            )
            return image_path, size, size
        logger.debug(
            "[VISION] Imagen %sx%s reducida a %sx%s para %s",
            width,
            height,
            new_size[0],
            new_size[1],
            self.model,
        )
        return buffer.getvalue(), size, new_size

    @staticmethod
    def _estimate_image_tokens(size: Optional[Tuple[int, int]]) -> int:
        """Tokens visuales aproximados de una imagen (un token por bloque de 32x32 px)."""
        if not size:
            return 0
        width, height = size
        block = float(VISION_TOKEN_BLOCK_PX)
        return int(math.ceil(width / block) * math.ceil(height / block))

    def _required_num_ctx(
        self,
        model_size: Optional[Tuple[int, int]],
        prompt: str,
        num_ctx: int,
        num_predict: int,
    ) -> int:
        """``num_ctx`` pedido o, si no caben imagen, prompt y salida, el multiplo de 1024 suficiente."""
        image_tokens = self._estimate_image_tokens(model_size)
        if image_tokens <= 0:
            return int(num_ctx)
        needed = image_tokens + len(prompt or "") // 3 + 64 + int(num_predict) + 256
        if needed <= int(num_ctx):
            return int(num_ctx)
        return int(math.ceil(needed / 1024.0) * 1024)

    @staticmethod
    def _safe_json_loads(value: Any) -> Optional[Any]:
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None

    # ====================================================================
    # INTERPRETACION SEMANTICA QWEN3-VL/OLLAMA
    # ====================================================================

    def interpret_element_semantics(
        self,
        image_path: str,
        crop_bbox: Optional[List[int]] = None,
        reference_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Interpreta semanticamente un elemento visual mediante Qwen3-VL/Ollama.

        Distingue la funcion aparente de un icono, relaciona una etiqueta con
        un control y ayuda a desambiguar candidatos. NO convierte por si sola
        un candidato visual en control accionable: es una capa interpretativa
        que devuelve pistas contextuales, nunca una decision de accionabilidad.

        La salida es estructurada y validable, asociada a la misma entrada
        (imagen/crop + referencia). Rechaza coordenadas fuera de rango, cajas
        inventadas y descripciones sin evidencia visual.
        """
        coordinate_check = {"in_range": True, "within_image": True}
        effective_image_path = image_path
        temp_crop_path: Optional[str] = None

        # Validar coordenadas de entrada cuando se solicita un recorte
        if crop_bbox is not None:
            if not isinstance(crop_bbox, (list, tuple)) or len(crop_bbox) != 4:
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": {"in_range": False, "within_image": False},
                    "error": "crop_bbox debe ser [x1, y1, x2, y2] con 4 valores numericos",
                }
            try:
                x1, y1, x2, y2 = [int(round(float(v))) for v in crop_bbox]
            except (TypeError, ValueError):
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": {"in_range": False, "within_image": False},
                    "error": "crop_bbox contiene valores no numericos",
                }
            if x2 <= x1 or y2 <= y1:
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": {"in_range": False, "within_image": False},
                    "error": "crop_bbox tiene coordenadas invertidas o nulas",
                }
            # Verificar que la caja este dentro de los limites de la imagen
            image = VisionOpenCVProcessor.load_image(image_path)
            if image is None:
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": {"in_range": False, "within_image": False},
                    "error": "no se pudo cargar la imagen",
                }
            height, width = image.shape[:2]
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
                coordinate_check = {"in_range": False, "within_image": False}
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": coordinate_check,
                    "error": "coordenadas del crop fuera de los limites de la imagen",
                }
            # Preparar recorte y guardarlo como archivo temporal para enviarlo al modelo
            crop = VisionOpenCVProcessor.prepare_crop(image_path, crop_bbox, padding=0.0)
            if crop is None:
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": coordinate_check,
                    "error": "no se pudo preparar el recorte",
                }
            fd, temp_crop_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                cv2.imwrite(temp_crop_path, crop)
                effective_image_path = temp_crop_path
            except Exception:
                if temp_crop_path and os.path.exists(temp_crop_path):
                    try:
                        os.remove(temp_crop_path)
                    except OSError:
                        pass
                temp_crop_path = None

        # Construir prompt de interpretacion semantica
        ref_ctx = f"\nReferencia de etiqueta: {reference_label}" if reference_label else ""
        prompt = f"""
Analiza la imagen/capture y interpreta semanticamente el elemento visual.{ref_ctx}

Devuelve unicamente JSON valido con esta estructura:
{{
  "apparent_function": "descripcion de lo que el icono o control aparenta hacer (vacio si no se puede determinar)",
  "label_association": "etiqueta de texto asociada al control (vacio si no hay una asociada)",
  "confidence": 0.0 a 1.0 (grado de confianza en la interpretacion),
  "disambiguation_hints": ["lista de pistas para distinguir este elemento de otros similares"]
}}

No declares que el elemento sea accionable: solo describ su funcion aparente y asociaciones.
"""

        schema = {
            "type": "object",
            "properties": {
                "apparent_function": {"type": "string"},
                "label_association": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "disambiguation_hints": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["apparent_function", "label_association", "confidence", "disambiguation_hints"],
        }

        try:
            raw = self._chat_json(
                image_path=effective_image_path,
                prompt=prompt,
                response_format=schema,
                num_ctx=8192,
                num_predict=2048,
                temperature=self.temperature,
            )
            data = self._safe_json_loads(raw)
            if not isinstance(data, dict):
                return {
                    "apparent_function": "",
                    "label_association": "",
                    "confidence": 0.0,
                    "is_actionable": False,
                    "evidence_visual": False,
                    "disambiguation_hints": [],
                    "coordinate_check": coordinate_check,
                    "error": "respuesta no decodificable como objeto JSON",
                }

            confidence = self._clamp_float(data.get("confidence", 0.0))
            apparent_function = str(data.get("apparent_function", "") or "").strip()
            label_association = str(data.get("label_association", "") or "").strip()
            hints = data.get("disambiguation_hints", [])
            if not isinstance(hints, list):
                hints = []
            hints = [str(h).strip() for h in hints if str(h).strip()]

            # La interpretacion semantica nunca decide accionabilidad
            is_actionable = False
            evidence_visual = bool(apparent_function) or bool(label_association) or bool(hints)

            return {
                "apparent_function": apparent_function,
                "label_association": label_association,
                "confidence": confidence,
                "is_actionable": is_actionable,
                "evidence_visual": evidence_visual,
                "disambiguation_hints": hints,
                "coordinate_check": coordinate_check,
                "error": None,
            }
        except Exception as exc:
            return {
                "apparent_function": "",
                "label_association": "",
                "confidence": 0.0,
                "is_actionable": False,
                "evidence_visual": False,
                "disambiguation_hints": [],
                "coordinate_check": coordinate_check,
                "error": str(exc),
            }
        finally:
            # Limpiar archivo temporal de recorte si se creo
            if temp_crop_path and os.path.exists(temp_crop_path):
                try:
                    os.remove(temp_crop_path)
                except OSError:
                    pass

    @staticmethod
    def _clamp_float(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        return max(0.0, min(1.0, number))

    @staticmethod
    def _normalize_int_list(value: Any, minimum: int, maximum: int) -> Optional[List[int]]:
        if not isinstance(value, (list, tuple)) or not (minimum <= len(value) <= maximum):
            return None
        result: List[int] = []
        for item in value:
            try:
                result.append(int(round(float(item))))
            except (TypeError, ValueError):
                return None
        return result

    @staticmethod
    def _coordinates_match(
        expected_coords: Optional[Dict[str, Any]],
        center: List[int],
        bbox: List[int],
        tolerance: float = 0.10,
    ) -> bool:
        if not expected_coords:
            return True
        expected_x = expected_coords.get("x")
        expected_y = expected_coords.get("y")
        if not isinstance(expected_x, (int, float)) or not isinstance(expected_y, (int, float)):
            return True
        actual_x, actual_y = center[:2]
        for expected, actual in ((expected_x, actual_x), (expected_y, actual_y)):
            scale = max(1.0, abs(float(expected)))
            if abs(float(expected) - float(actual)) / scale > tolerance:
                return False
        return True

    def get_vision_capabilities(self) -> Dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self._vision_nodes],
            "model": self.model,
            "total_cost": self.get_total_vision_cost(),
            "available_types": list(dict.fromkeys(t.value for t in VisionNodeType)),
        }


# ====================================================================
# PROCESADOR DE IMAGEN CON OPENCV (recortes, normalizacion, cambios,
# bordes/regiones y refinamiento de limites)
# ====================================================================
class VisionOpenCVProcessor:
    """Procesamiento de imagen basado en OpenCV para el pipeline de
    vision de JARVIS.

    Proporciona utilidades para preparar recortes de elementos, normalizar
    color/tamano, detectar cambios entre frames, detectar bordes/regiones y
    refinar los limites de un elemento detectado.

    IMPORTANTE: los resultados de contornos, contraste y bordes son
    PISTAS DE REFINAMIENTO GEOMETRICO. NUNCA constituyen prueba de que un
    elemento sea interactuable y NUNCA modifican el campo ``interactive``
    de un elemento. La interactividad solo puede provenir del modelo de
    vision (Ollama/Qwen3-VL) o de un patron de interaccion real verificado.
    """

    @staticmethod
    def load_image(image_path):
        """Carga una imagen desde ruta en formato BGR (numpy array).

        Devuelve ``None`` si la ruta no existe, no es legible o no es una
        imagen valida. No lanza excepciones.
        """
        try:
            if not image_path or not os.path.exists(str(image_path)):
                return None
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                return None
            return image
        except Exception:
            return None

    @staticmethod
    def prepare_crop(image_path, bbox, padding=0.1):
        """Prepara un recorte de la imagen limitado a la caja ``bbox``.

        ``bbox`` es ``[x1, y1, x2, y2]`` en pixeles de la imagen original.
        Se agrega ``padding`` (fraccion del tamano de la caja) alrededor y
        el resultado se clampa a los limites de la imagen.

        Devuelve el recorte como array BGR de numpy, o ``None`` si no se
        puede cargar la imagen o la caja es invalida.
        """
        image = VisionOpenCVProcessor.load_image(image_path)
        if image is None:
            return None
        try:
            x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
        except (TypeError, ValueError):
            return None
        if x2 <= x1 or y2 <= y1:
            return None
        height, width = image.shape[:2]
        w = x2 - x1
        h = y2 - y1
        pad_x = int(round(w * padding))
        pad_y = int(round(h * padding))
        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(width, x2 + pad_x)
        cy2 = min(height, y2 + pad_y)
        if cx2 <= cx1 or cy2 <= cy1:
            return None
        return image[cy1:cy2, cx1:cx2]

    @staticmethod
    def normalize_image(image, target_size=None, grayscale=False):
        """Normaliza una imagen: opcionalmente la pasa a grises y la
        redimensiona a ``target_size`` (ancho, alto).

        Devuelve el array normalizado o ``None`` si la entrada es invalida.
        """
        if image is None or not isinstance(image, np.ndarray):
            return None
        try:
            result = image
            if grayscale and len(result.shape) == 3:
                result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            if target_size is not None:
                tw, th = int(target_size[0]), int(target_size[1])
                if tw > 0 and th > 0:
                    result = cv2.resize(result, (tw, th), interpolation=cv2.INTER_AREA)
            return result
        except Exception:
            return None

    @staticmethod
    def detect_changes(frame_a, frame_b):
        """Compara dos frames y detecta regiones que cambiaron.

        Devuelve un diccionario con:
        - ``changed``: bool, si hay cambios significativos
        - ``score``: float, proporcion de pixeles diferentes (0.0-1.0)
        - ``regions``: lista de cajas [x1, y1, x2, y2] de regiones cambiadas
        """
        result = {"changed": False, "score": 0.0, "regions": []}
        if frame_a is None or frame_b is None:
            return result
        try:
            a_gray = frame_a
            b_gray = frame_b
            if len(a_gray.shape) == 3:
                a_gray = cv2.cvtColor(a_gray, cv2.COLOR_BGR2GRAY)
            if len(b_gray.shape) == 3:
                b_gray = cv2.cvtColor(b_gray, cv2.COLOR_BGR2GRAY)
            if a_gray.shape != b_gray.shape:
                b_gray = cv2.resize(
                    b_gray,
                    (a_gray.shape[1], a_gray.shape[0]),
                    interpolation=cv2.INTER_AREA,
                )
            diff = cv2.absdiff(a_gray, b_gray)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            thresh = cv2.dilate(thresh, kernel, iterations=2)
            total = float(thresh.size)
            changed_pixels = float(cv2.countNonZero(thresh))
            score = changed_pixels / total if total > 0 else 0.0
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 0 and h > 0:
                    regions.append([int(x), int(y), int(x + w), int(y + h)])
            result["changed"] = score > 0.001
            result["score"] = round(score, 6)
            result["regions"] = regions
            return result
        except Exception:
            return result

    @staticmethod
    def detect_edges_regions(image):
        """Detecta bordes y regiones candidatas mediante Canny y contornos.

        Devuelve un diccionario con:
        - ``edges``: array binario de bordes (o None si falla)
        - ``regions``: lista de cajas [x1, y1, x2, y2] de contornos encontrados
        - ``count``: cantidad de regiones
        """
        result = {"edges": None, "regions": [], "count": 0}
        if image is None or not isinstance(image, np.ndarray):
            return result
        try:
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            contours, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 0 and h > 0:
                    regions.append([int(x), int(y), int(x + w), int(y + h)])
            result["edges"] = edges
            result["regions"] = regions
            result["count"] = len(regions)
            return result
        except Exception:
            return result

    @staticmethod
    def refine_bounds(image, bbox):
        """Refina los limites de un elemento usando bordes/contornos dentro
        de su caja.

        Devuelve un diccionario con:
        - ``refined_bbox``: caja [x1, y1, x2, y2] refinada dentro de la
          entrada, o None si no se pudo refinar
        - ``hint_only``: True (el resultado es una pista geometrica, nunca
          prueba de interactividad)
        - ``ok``: bool, si la refino se produjo
        """
        result = {"refined_bbox": None, "hint_only": True, "ok": False}
        if image is None or not isinstance(image, np.ndarray):
            return result
        try:
            x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
        except (TypeError, ValueError):
            return result
        if x2 <= x1 or y2 <= y1:
            return result
        height, width = image.shape[:2]
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        crop = image[y1:y2, x1:x2]
        edge_info = VisionOpenCVProcessor.detect_edges_regions(crop)
        if not edge_info["regions"]:
            result["refined_bbox"] = [x1, y1, x2, y2]
            result["ok"] = True
            return result
        # Usar el contorno mas grande como pista de ajuste de limites
        best = max(
            edge_info["regions"], key=lambda r: (r[2] - r[0]) * (r[3] - r[1])
        )
        rx1, ry1, rx2, ry2 = best
        refined = [x1 + rx1, y1 + ry1, x1 + rx2, y1 + ry2]
        # Clamp final
        refined[0] = max(0, min(refined[0], width - 1))
        refined[1] = max(0, min(refined[1], height - 1))
        refined[2] = max(refined[0] + 1, min(refined[2], width))
        refined[3] = max(refined[1] + 1, min(refined[3], height))
        result["refined_bbox"] = refined
        result["ok"] = True
        return result


__all__ = [
    "UIElement",
    "VisionResponse",
    "Vision",
    "VisionNode",
    "VisionNodeType",
    "VisionOpenCVProcessor",
]
