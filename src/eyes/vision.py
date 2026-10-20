# src/eyes/vision.py
"""
Visión por computadora usando Qwen3-VL mediante Ollama.

La capa de visión es genérica: no contiene coordenadas, offsets, resoluciones
ni lógica específica de Chrome u otra aplicación. La geometría de monitores
pertenece a ScreenManager y la calibración universal pertenece a
UniversalVisualCalibrator / CalibrationManager.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import ollama
from pydantic import BaseModel, Field

from src.eyes.screen_capture import ScreenCapture
from src.eyes.screen import ApplicationInfo, ApplicationState
from src.memory.storage import MemoryType, WorldState, get_memory_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VisionNodeType(Enum):
    """Tipos de nodos de visión disponibles para planificación."""

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
    """Nodo de percepción visual reutilizable por el planificador."""

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


class UIElement(BaseModel):
    """Elemento UI detectado por el modelo de visión."""

    type: str = Field(..., description="Tipo de elemento interactivo.")
    text: str = Field("", description="Texto o descripción del elemento.")
    bbox: List[int] = Field(..., description="Bounding box [x1, y1, x2, y2].")
    center: List[int] = Field(default_factory=list, description="Centro [x, y].")
    interactive: bool = Field(True, description="Indica si es interactivo.")
    confidence: float = Field(..., description="Confianza entre 0.0 y 1.0.")


class VisionResponse(BaseModel):
    """Respuesta estructurada de detección UI."""

    elements: List[UIElement] = Field(default_factory=list)


class Vision:
    """Sistema de visión genérico integrado con la arquitectura de Jarvis."""

    def __init__(self, model: str = "qwen3-vl:8b") -> None:
        self.model = model
        self.temperature = 0.0
        self.screen_capture = ScreenCapture()
        self.memory_manager = get_memory_manager()
        self._vision_nodes = self._create_vision_nodes()

        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111)
        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111),
            "vision.py", "__init__", 113
        )

    # ====================================================================
    # NODOS DE VISIÓN
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
                description="Verifica si un elemento UI específico es visible",
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
                name="Verificar resultado de acción",
                description="Comprueba visualmente el efecto esperado de una acción",
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
                name="Analizar para calibración",
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
                name="Detectar aplicación",
                description="Detecta visualmente una aplicación y su estado en las pantallas analizadas",
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
        """Obtiene los identificadores lógicos reales desde ScreenManager."""
        try:
            from src.utils.screen_manager import get_screen_manager

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
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "_get_available_monitor_numbers", 236)
            return [1]

    def _get_default_monitor_number(self) -> int:
        """Selecciona el monitor activo y, como fallback, el principal."""
        try:
            from src.utils.screen_manager import get_screen_manager

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
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "_get_active_monitor_number", 255)

        monitors = self._get_available_monitor_numbers()
        return monitors[0]

    # ====================================================================
    # ESTADO DEL MUNDO
    # ====================================================================

    def analyze_screen_for_world_state(self) -> WorldState:
        """Analiza todas las pantallas disponibles y construye un WorldState válido."""
        logger._print_log("info", r"[VISION] Analizando pantallas para estado del mundo... [file:vision.py, method:analyze_screen_for_world_state, line:266]", "vision.py", "method", 264)
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
2. Cuál parece estar en primer plano.
3. Elementos UI visibles y claramente interactivos.
4. Texto relevante visible.
5. Si una ventana parece maximizada, normal o minimizada cuando exista evidencia visual.

Devuelve ÚNICAMENTE JSON válido:
{
  "applications": [
    {
      "name": "chrome",
      "state": "active|open|maximized|minimized|closed",
      "window_title": "título visible",
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
                    logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "analyze_screen_for_world_state", 309)
                    continue

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
                        "type": element.get("type", "other"),
                        "text": element.get("text", ""),
                        "interactive": bool(element.get("interactive", True)),
                        "monitor": monitor_number,
                    }
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111) + ": " + str(exc),
                    "vision.py", "build_world_state", 364
                )

        calibrated_elements: Dict[str, Any] = {}
        try:
            state_data = self.memory_manager.storage.load(MemoryType.STATE)
            if isinstance(state_data, dict):
                calibrated_elements = dict(state_data.get("calibrated_elements", {}) or {})
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "build_world_state", 376)

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
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "build_world_state", 388)

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
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "build_world_state", 412)

        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111) + " aplicaciones=" + str(len(applications)) + " elementos=" + str(len(ui_elements)),
            "vision.py", "build_world_state", 414
        )
        return world_state

    # ====================================================================
    # DETECCIÓN UI
    # ====================================================================

    def detect_ui_elements(
        self,
        image_path: str,
        application: Optional[str] = None,
    ) -> VisionResponse:
        """Detecta elementos interactivos visibles en una imagen."""
        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111) + ")",
            "vision.py", "detect_ui_elements", 431
        )

        app_context = f" en {application}" if application else ""
        prompt = f"""
Analiza la captura de pantalla y detecta los elementos interactivos visibles{app_context}.

Incluye botones, campos de texto, búsquedas, enlaces, pestañas, menús,
checkboxes, radios, selects, sliders, switches, iconos pulsables y controles
de navegación. No incluyas fondos, texto decorativo ni elementos no interactivos.

Devuelve exclusivamente JSON válido con esta estructura:
{{
  "elements": [
    {{
      "type": "button",
      "text": "Abrir",
      "bbox": [100, 200, 200, 250],
      "center": [150, 225],
      "interactive": true,
      "confidence": 0.95
    }}
  ]
}}
"""

        schema = {
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "text": {"type": "string"},
                            "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                            "center": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                            "interactive": {"type": "boolean"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["type", "text", "bbox", "center", "interactive", "confidence"],
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
            data = self._safe_json_loads(raw)
            if not isinstance(data, dict):
                return VisionResponse(elements=[])

            valid_elements: List[UIElement] = []
            for item in data.get("elements", []) or []:
                if not isinstance(item, dict):
                    continue
                try:
                    bbox = self._normalize_int_list(item.get("bbox"), minimum=4, maximum=4)
                    center = self._normalize_int_list(item.get("center"), minimum=2, maximum=2)
                    if bbox is None or center is None:
                        continue
                    confidence = self._clamp_float(item.get("confidence", 0.0))
                    valid_elements.append(
                        UIElement(
                            type=str(item.get("type", "other")),
                            text=str(item.get("text", "") or ""),
                            bbox=bbox,
                            center=center,
                            interactive=bool(item.get("interactive", True)),
                            confidence=confidence,
                        )
                    )
                except Exception:
                    continue

            return VisionResponse(elements=valid_elements)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "detect_ui_elements", 518)
            return VisionResponse(elements=[])

    # ====================================================================
    # CALIBRACIÓN UNIVERSAL
    # ====================================================================

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        calibration_target: Optional[str] = None,
    ) -> str:
        """
        Analiza una captura para calibración universal.

        IMPORTANTE: este método devuelve el JSON del modelo como string porque
        UniversalVisualCalibrator y los calibradores legacy ya utilizan ese
        contrato. No convierte aquí coordenadas ni aplica offsets de monitor.
        """
        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111) + ")", "vision.py", "analyze_image", 538)

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
                num_predict=4096,
                temperature=0.0,
            )
            if not result:
                logger._print_log("warning", r"[VISION] Qwen devolvió una respuesta vacía [file:vision.py, method:analyze_image, line:575]", "vision.py", "method", 568)
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

            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111)) + " caracteres)", "vision.py", "detect_ui_elements", 593)
            return result
        except ollama.ResponseError as exc:
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "detect_ui_elements", 596)
            return f"ERROR: {exc}"
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "detect_ui_elements", 599)
            return f"ERROR: {exc}"

    # ====================================================================
    # VERIFICACIÓN
    # ====================================================================

    def verify_element_visibility(
        self,
        element_name: str,
        application: Optional[str] = None,
        expected_coords: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verifica visualmente si un elemento está presente."""
        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111)

        try:
            image_path = None
            if application:
                image_path = self.screen_capture.capture_active_window()
            if not image_path:
                image_path = self.screen_capture.capture_monitor(self._get_default_monitor_number())
            if not image_path:
                return {"success": False, "element": element_name, "verified": False, "error": "No se pudo capturar pantalla"}

            ui_response = self.detect_ui_elements(image_path, application)
            target = str(element_name or "").strip().lower()

            for element in ui_response.elements:
                haystack = f"{element.type} {element.text}".lower()
                if target and (target == element.type.lower() or target in haystack):
                    coords_match = self._coordinates_match(expected_coords, element.center, element.bbox)
                    return {
                        "success": True,
                        "element": element_name,
                        "verified": True,
                        "found_element": {
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
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "is_element_visible", 655)
            return {"success": False, "element": element_name, "verified": False, "error": str(exc)}

    def verify_action_result(
        self,
        expected_state: Dict[str, Any],
        application: Optional[str] = None,
        tolerance: float = 0.8,
    ) -> Dict[str, Any]:
        """Verifica visualmente el resultado esperado de una acción."""
        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "verify_action_result", 665)
        tolerance = self._clamp_float(tolerance)

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
                return {"success": False, "verified": False, "error": "Respuesta no válida del modelo de visión"}

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
            logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111), "vision.py", "_verify_action_result", 707)
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
Verifica visualmente{context} si la pantalla muestra una página cargada correspondiente a la URL:
{expected_url}

Responde ÚNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": "", "current_url": ""}}
"""
        if expected_type == "element_focused":
            element_name = expected_state.get("element", "")
            return f"""
Verifica visualmente{context} si el elemento '{element_name}' está enfocado o activo.
Busca indicadores visibles de foco.

Responde ÚNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": ""}}
"""
        if expected_type == "application_opened":
            app_name = expected_state.get("application", "")
            return f"""
Verifica visualmente si la aplicación '{app_name}' está abierta y visible{context}.

Responde ÚNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": "", "window_title": ""}}
"""
        return f"""
Analiza la pantalla y verifica si se cumple esta condición{context}:
{json.dumps(expected_state, ensure_ascii=False)}

Responde ÚNICAMENTE JSON:
{{"verified": true, "confidence": 0.0, "details": ""}}
"""

    # ====================================================================
    # DETECCIÓN DE ESTADO DE APLICACIÓN
    # ====================================================================

    def detect_application_state(self, app_name: str) -> ApplicationInfo:
        """Busca una aplicación en todas las pantallas disponibles."""
        logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111)
        target = str(app_name or "").strip()
        if not target:
            return ApplicationInfo(name=target, state=ApplicationState.CLOSED)

        prompt = f"""
Analiza esta pantalla y determina si la aplicación '{target}' aparece visualmente.
Distingue, solo con evidencia visible, entre activa, abierta, maximizada,
minimizada o cerrada.

Responde ÚNICAMENTE JSON:
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
                state_str = str(data.get("state", "open") or "open").lower()
                info = ApplicationInfo(
                    name=target,
                    state=state_map.get(state_str, ApplicationState.OPEN),
                    window_title=data.get("window_title"),
                    monitor=monitor_number,
                    visible_elements=list(data.get("visible_elements", []) or []),
                )
                if best is None or confidence > best[0]:
                    best = (confidence, info)
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "vision.py", "method", 111) + ": " + str(exc),
                    "vision.py", "detect_application_state", 815
                )

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
    ) -> str:
        response = ollama.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_path],
                }
            ],
            stream=False,
            think=False,
            format=response_format,
            options={
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
            keep_alive="5m",
        )
        message = response.get("message", {}) if isinstance(response, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        return str(content or "").strip()

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


__all__ = [
    "UIElement",
    "VisionResponse",
    "Vision",
    "VisionNode",
    "VisionNodeType",
]
