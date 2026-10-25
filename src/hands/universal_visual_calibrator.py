"""
Calibrador visual universal para la arquitectura de planificación jerárquica.

Esta capa realiza exclusivamente percepción/calibración visual. No abre ni
mueve aplicaciones y no persiste macros_coords.json directamente.

El resultado de `calibrate()` utiliza coordenadas absolutas del escritorio
virtual y asocia cada elemento al monitor físico real (`s1`, `s2`, ...).
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from src.eyes.vision import Vision
from src.memory.conversation import ConversationMemory
from src.utils.logger import get_logger
from src.utils.screen_manager import get_monitor_info

logger = get_logger(__name__)


class CalibrationPolicy:
    """Política centralizada de seguridad, no una allowlist de aplicaciones.

    La calibración visual es universal: una aplicación GUI no bloqueada puede
    ser analizada. Las aplicaciones peligrosas/protegidas se rechazan aquí y
    en el preflight del CalibrationManager cuando corresponde.
    """

    BLOCKED_APPLICATIONS = {
        "league of legends",
        "valorant",
        "teamfight tactics",
        "legends of runeterra",
        "counter strike 2",
        "counter strike",
        "dota 2",
        "apex legends",
        "fortnite",
        "overwatch",
        "overwatch 2",
        "minecraft",
        "rocket league",
        "fall guys",
        "pubg",
        "destiny 2",
        "warframe",
        "gta v",
        "grand theft auto",
        "grand theft auto v",
        "red dead redemption 2",
        "elden ring",
        "dark souls",
        "cyberpunk 2077",
        "administracion de equipos",
        "administrador de tareas",
        "editor del registro",
        "visor de eventos",
        "programador de tareas",
        "servicios",
        "directiva de seguridad",
        "monitor de recursos",
        "diagnostico de memoria",
        "configuracion del sistema",
        "visual studio code",
        "vs code",
        "visual studio",
        "intellij",
        "eclipse",
        "pycharm",
        "webstorm",
        "rider",
        "jetbrains",
        "android studio",
        "command prompt",
        "powershell",
        "cmd",
        "terminal",
        "consola",
        "task manager",
        "resource monitor",
        "browser safe mode",
        "firefox safe mode",
        "chrome safe mode",
    }

    # Aplicaciones conocidas de referencia. Esta lista es informativa y NO
    # limita la calibración universal a estas aplicaciones.
    ALLOWED_APPLICATIONS = {
        "chrome",
        "google chrome",
        "edge",
        "microsoft edge",
        "firefox",
        "mozilla firefox",
        "spotify",
        "notepad",
        "bloc de notas",
        "calculator",
        "calculadora",
        "paint",
        "microsoft paint",
        "photos",
        "fotos",
        "mail",
        "correo",
        "calendar",
        "calendario",
        "media player",
        "reproductor multimedia",
        "word",
        "excel",
        "powerpoint",
        "discord",
        "telegram",
        "slack",
        "whatsapp",
        "zoom",
        "teams",
        "meet",
        "obs studio",
        "vlc",
        "potplayer",
    }

    BLOCKED_ELEMENT_TYPES = {
        "background",
        "desktop",
        "wallpaper",
        "taskbar",
        "start_menu",
        "system_tray",
        "notification_area",
        "minimized",
        "inactive",
        "non_interactive",
        "static",
        "decoration",
    }

    MIN_ELEMENT_CONFIDENCE = 0.30

    @classmethod
    def can_calibrate_application(
        cls, application_name: str
    ) -> Tuple[bool, Optional[str]]:
        normalized = cls._normalize_name(application_name)

        if not normalized:
            return False, "Nombre de aplicación vacío"

        if normalized in {cls._normalize_name(x) for x in cls.BLOCKED_APPLICATIONS}:
            return False, f"Aplicación bloqueada por política: {application_name}"

        # La calibración universal no depende de una lista cerrada de
        # aplicaciones. Cualquier aplicación GUI puede llegar hasta aquí;
        # las restricciones de seguridad (juegos, herramientas sensibles,
        # terminales, etc.) se aplican en las capas de preflight/política.
        return True, None

    @classmethod
    def can_calibrate_element(
        cls, element_type: str, confidence: float
    ) -> Tuple[bool, Optional[str]]:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if not 0.0 <= confidence <= 1.0:
            return False, "Confianza fuera del rango 0..1"

        if confidence < cls.MIN_ELEMENT_CONFIDENCE:
            return False, "Confianza demasiado baja"

        normalized_type = cls._normalize_name(element_type)
        if normalized_type in {
            cls._normalize_name(x) for x in cls.BLOCKED_ELEMENT_TYPES
        }:
            return False, f"Tipo de elemento bloqueado: {element_type}"

        return True, None

    @staticmethod
    def _normalize_name(name: Any) -> str:
        value = str(name or "").strip().casefold()
        value = unicodedata.normalize("NFKD", value)
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[^a-z0-9 _-]", "", value)
        return value.strip()


class UICapability:
    """Representa un elemento UI calibrado y consumible por acciones."""

    def __init__(
        self,
        name: str,
        element_type: str,
        center: Tuple[int, int],
        bbox: Tuple[int, int, int, int],
        screen: int,
        confidence: float = 0.8,
    ) -> None:
        self.name = name
        self.element_type = element_type
        self.center = (int(center[0]), int(center[1]))
        self.bbox = tuple(int(value) for value in bbox)
        self.screen = int(screen)
        self.confidence = float(confidence)
        self.calibrated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.element_type,
            "center": list(self.center),
            "bbox": list(self.bbox),
            "screen": self.screen,
            "confidence": self.confidence,
            "calibrated_at": self.calibrated_at,
        }


class CalibrationState:
    """Estado en memoria de los elementos calibrados."""

    def __init__(self) -> None:
        # API histórica: app -> element -> capability.
        self.calibrated_elements: Dict[str, Dict[str, UICapability]] = {}
        # Estado correcto para multipantalla: app -> sN -> element -> capability.
        self.calibrated_elements_by_screen: Dict[
            str, Dict[str, Dict[str, UICapability]]
        ] = {}
        self.last_calibration_time: Dict[str, float] = {}
        self.calibration_history: List[Dict[str, Any]] = []

    def get_element(
        self,
        application: str,
        element_name: str,
        monitor_number: Optional[int] = None,
    ) -> Optional[UICapability]:
        app = self._normalize_application(application)
        element = self._normalize_element(element_name)

        if monitor_number is not None:
            screen = f"s{int(monitor_number)}"
            capability = (
                self.calibrated_elements_by_screen
                .get(app, {})
                .get(screen, {})
                .get(element)
            )
            if capability is not None:
                return capability

        return self.calibrated_elements.get(app, {}).get(element)

    def get_application_elements(
        self,
        application: str,
        monitor_number: Optional[int] = None,
    ) -> Dict[str, UICapability]:
        app = self._normalize_application(application)
        if monitor_number is not None:
            return dict(
                self.calibrated_elements_by_screen
                .get(app, {})
                .get(f"s{int(monitor_number)}", {})
            )
        return dict(self.calibrated_elements.get(app, {}))

    def add_element(
        self,
        application: str,
        element: UICapability,
        monitor_number: Optional[int] = None,
    ) -> None:
        app = self._normalize_application(application)
        element_name = self._normalize_element(element.name)

        self.calibrated_elements.setdefault(app, {})[element_name] = element

        screen_number = monitor_number if monitor_number is not None else element.screen
        screen_key = f"s{int(screen_number)}"
        self.calibrated_elements_by_screen.setdefault(app, {}).setdefault(
            screen_key, {}
        )[element_name] = element

        self.last_calibration_time[app] = time.time()
        self.calibration_history.append(
            {
                "timestamp": time.time(),
                "application": app,
                "monitor": int(screen_number),
                "element": element.to_dict(),
                "action": "calibrate",
            }
        )

    def is_element_calibrated(
        self,
        application: str,
        element_name: str,
        monitor_number: Optional[int] = None,
    ) -> bool:
        return self.get_element(application, element_name, monitor_number) is not None

    def get_calibration_age(self, application: str) -> Optional[float]:
        value = self.last_calibration_time.get(self._normalize_application(application))
        return time.time() - value if value else None

    @staticmethod
    def _normalize_application(value: Any) -> str:
        return CalibrationPolicy._normalize_name(value)

    @staticmethod
    def _normalize_element(value: Any) -> str:
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9áéíóúüñ]+", "_", str(value or "").strip().lower())).strip("_")


class UniversalVisualCalibrator:
    """Calibrador visual universal integrado con las capas superiores."""

    MODEL = "qwen3-vl:8b-instruct"
    NORMALIZED_MAX = 1000
    MAX_ELEMENTS = 80
    MIN_CONFIDENCE = 0.20

    def __init__(self, memory: Optional[ConversationMemory] = None) -> None:
        self.vision = Vision(model=self.MODEL)
        self.policy = CalibrationPolicy()
        self.state = CalibrationState()
        self.memory = memory or ConversationMemory()
        logger.info(
            "[UNIVERSAL-CALIBRATOR] Inicializado con Qwen=%s",
            self.MODEL,
        )

    def get_ui_capability(
        self,
        application: str,
        element_name: str,
        monitor_number: int,
        screenshot_path: str,
    ) -> Optional[UICapability]:
        logger.info(
            "[UNIVERSAL-CALIBRATOR] Solicitud UI capability: %s.%s en s%s",
            application,
            element_name,
            monitor_number,
        )

        allowed, reason = self.policy.can_calibrate_application(application)
        if not allowed:
            logger._print_log("warning", "[UNIVERSAL-CALIBRATOR] Aplicación no calibrable: %s", "universal_visual_calibrator.py", "method", 366)

            return None

        cached = self.state.get_element(application, element_name, monitor_number)
        if cached is not None:
            return cached

        capability = self._calibrate_element(
            application=application,
            monitor_number=monitor_number,
            screenshot_path=screenshot_path,
            required_element=element_name,
        )
        if capability is not None:
            self.state.add_element(application, capability, monitor_number)
        return capability

    def calibrate_application_elements(
        self,
        application: str,
        monitor_number: int,
        screenshot_path: str,
    ) -> Dict[str, UICapability]:
        allowed, reason = self.policy.can_calibrate_application(application)
        if not allowed:
            logger._print_log("warning", "[UNIVERSAL-CALIBRATOR] Aplicación no calibrable", "universal_visual_calibrator.py", "method", 392)

            return {}

        result = self.calibrate(
            application_name=application,
            monitor_number=monitor_number,
            screenshot_path=screenshot_path,
        )
        if not result.get("success"):
            logger._print_log("info", "Procesando solicitud", "universal_visual_calibrator.py", "method", 400)

            return {}

        capabilities: Dict[str, UICapability] = {}
        for element_data in result.get("elements", []):
            if not isinstance(element_data, dict):
                continue

            confidence = self._normalize_confidence(element_data.get("confidence"))
            allowed_element, reason = self.policy.can_calibrate_element(
                element_data.get("type", "other"), confidence
            )
            if not allowed_element:
                logger._print_log("debug", "[UNIVERSAL-CALIBRATOR] Elemento filtrado", "universal_visual_calibrator.py", "method", 416)

                continue

            try:
                capability = UICapability(
                    name=str(element_data["name"]),
                    element_type=str(element_data["type"]),
                    center=tuple(element_data["center"]),
                    bbox=tuple(element_data["bbox"]),
                    screen=int(element_data["screen"]),
                    confidence=confidence,
                )
            except (KeyError, TypeError, ValueError):
                continue

            capabilities[capability.name] = capability
            self.state.add_element(application, capability, monitor_number)

        logger.info(
            "[UNIVERSAL-CALIBRATOR] %s: %s elementos calibrados en s%s",
            application,
            len(capabilities),
            monitor_number,
        )
        return capabilities

    def calibrate(
        self,
        application_name: str,
        monitor_number: int,
        screenshot_path: str,
    ) -> Dict[str, Any]:
        application_name = str(application_name or "unknown").strip()

        allowed, reason = self.policy.can_calibrate_application(application_name)
        if not allowed:
            return {"success": False, "error": reason, "elements": []}

        try:
            monitor_number = int(monitor_number)
        except (TypeError, ValueError):
            return {"success": False, "error": "Número de monitor inválido", "elements": []}

        if monitor_number < 1:
            return {
                "success": False,
                "error": "El número de monitor debe ser mayor que 0",
                "elements": [],
            }

        screenshot = Path(str(screenshot_path or ""))
        if not screenshot_path:
            return {"success": False, "error": "Ruta de captura vacía", "elements": []}
        if not screenshot.exists():
            return {
                "success": False,
                "error": f"La captura no existe: {screenshot}",
                "elements": [],
            }

        monitor = get_monitor_info(monitor_number)
        if monitor is None:
            return {
                "success": False,
                "error": f"Monitor {monitor_number} no encontrado",
                "elements": [],
            }

        try:
            image_width, image_height = self._get_image_size(screenshot)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "universal_visual_calibrator.py", "method", 400)

            return {"success": False, "error": str(exc), "elements": []}

        prompt = self._build_prompt(application_name)
        try:
            raw_response = self.vision.analyze_image(str(screenshot), prompt)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "universal_visual_calibrator.py", "method", 400)

            return {"success": False, "error": str(exc), "elements": []}

        if not raw_response:
            return {
                "success": False,
                "error": "Qwen3-VL devolvió una respuesta vacía",
                "elements": [],
            }

        parsed = self._parse_response(str(raw_response))
        if parsed is None:
            return {
                "success": False,
                "error": "No se pudo interpretar el JSON devuelto por Qwen",
                "elements": [],
                "raw_response": str(raw_response),
            }

        raw_elements = parsed.get("elements", [])
        if not isinstance(raw_elements, list):
            return {
                "success": False,
                "error": "El campo 'elements' no es una lista",
                "elements": [],
                "raw_response": parsed,
            }

        filtered_elements: List[Dict[str, Any]] = []
        for raw_element in raw_elements:
            if not isinstance(raw_element, dict):
                continue
            if raw_element.get("interactive", True) is False:
                continue
            element_type = str(raw_element.get("type", "other") or "other")
            confidence = self._normalize_confidence(raw_element.get("confidence"))
            ok, reason = self.policy.can_calibrate_element(element_type, confidence)
            if ok:
                filtered_elements.append(raw_element)
            else:
                logger._print_log("debug", "[UNIVERSAL-CALIBRATOR] Elemento filtrado", "universal_visual_calibrator.py", "method", 416)


        elements = self._normalize_elements(
            raw_elements=filtered_elements,
            monitor=monitor,
            image_width=image_width,
            image_height=image_height,
        )

        return {
            "success": True,
            "application": application_name,
            "monitor": monitor_number,
            "screen_key": monitor.screen_key,
            "elements": elements,
            "total_elements": len(elements),
            "image_size": {"width": image_width, "height": image_height},
            "monitor_geometry": {
                "left": monitor.left,
                "top": monitor.top,
                "right": monitor.right,
                "bottom": monitor.bottom,
                "width": monitor.width,
                "height": monitor.height,
                "dpi": monitor.dpi,
                "scale_factor": monitor.scale_factor,
            },
            "image_to_monitor_scale": {
                "x": monitor.width / image_width,
                "y": monitor.height / image_height,
            },
            "coordinate_system": "absolute_desktop_native_pixels",
            "model": self.MODEL,
            "raw_response": parsed,
        }

    def _calibrate_element(
        self,
        application: str,
        monitor_number: int,
        screenshot_path: str,
        required_element: str,
    ) -> Optional[UICapability]:
        result = self.calibrate(application, monitor_number, screenshot_path)
        if not result.get("success"):
            return None

        target = self._normalize_element_name(required_element)
        for element_data in result.get("elements", []):
            if self._normalize_element_name(element_data.get("name")) != target:
                continue
            try:
                return UICapability(
                    name=element_data["name"],
                    element_type=element_data["type"],
                    center=tuple(element_data["center"]),
                    bbox=tuple(element_data["bbox"]),
                    screen=int(element_data["screen"]),
                    confidence=float(element_data["confidence"]),
                )
            except (KeyError, TypeError, ValueError):
                return None
        return None

    def _build_prompt(self, application_name: str) -> str:
        return f"""
Analiza exclusivamente la interfaz visible de esta aplicación:

APLICACIÓN: {application_name}

Detecta elementos visibles que sean realmente interactivos y útiles para
automatización mediante ratón o teclado.

No inventes elementos, no describas el escritorio ni otras aplicaciones y no
incluyas contenido puramente decorativo.

Tipos válidos: button, input, link, menu, icon, checkbox, radio, select, tab,
switch, slider, navigation, other.

Devuelve ÚNICAMENTE JSON válido con esta estructura:
{{
  "elements": [
    {{
      "name": "nombre_elemento",
      "type": "button",
      "text": "texto visible",
      "description": "descripción breve",
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95,
      "interactive": true
    }}
  ]
}}

REGLAS:
- Máximo {self.MAX_ELEMENTS} elementos.
- bbox relativo a TODA la imagen.
- Coordenadas NORMALIZADAS de 0 a {self.NORMALIZED_MAX}.
- x1 < x2 y y1 < y2.
- confidence entre 0.0 y 1.0.
- name en minúsculas y con "_" entre palabras.
- No utilices coordenadas absolutas ni datos de otro monitor.
"""

    @staticmethod
    def _parse_response(response: str) -> Optional[Dict[str, Any]]:
        text = str(response or "").strip()
        if not text:
            return None

        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()

        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _get_image_size(screenshot_path: Path) -> Tuple[int, int]:
        with Image.open(screenshot_path) as image:
            width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("La imagen tiene dimensiones inválidas")
        return int(width), int(height)

    def _normalize_elements(
        self,
        raw_elements: List[Any],
        monitor: Any,
        image_width: int,
        image_height: int,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw_element in raw_elements:
            if len(normalized) >= self.MAX_ELEMENTS:
                break
            if not isinstance(raw_element, dict):
                continue
            element = self._normalize_single_element(
                raw_element,
                monitor,
                image_width,
                image_height,
            )
            if element is not None:
                normalized.append(element)
        return self._deduplicate_elements(normalized)

    def _normalize_single_element(
        self,
        raw_element: Dict[str, Any],
        monitor: Any,
        image_width: int,
        image_height: int,
    ) -> Optional[Dict[str, Any]]:
        name = self._normalize_element_name(
            raw_element.get("name")
            or raw_element.get("text")
            or raw_element.get("description")
        )
        if not name:
            return None

        element_type = str(raw_element.get("type", "other") or "other").strip().lower()
        confidence = self._normalize_confidence(raw_element.get("confidence"))
        if confidence < self.MIN_CONFIDENCE:
            return None

        image_bbox = self._extract_image_bbox(raw_element, image_width, image_height)
        if image_bbox is None:
            return None

        monitor_bbox = self._image_bbox_to_monitor_bbox(
            image_bbox,
            monitor,
            image_width,
            image_height,
        )
        x1, y1, x2, y2 = monitor_bbox
        if x2 <= x1 or y2 <= y1:
            return None

        local_center_x = int(round((x1 + x2) / 2.0))
        local_center_y = int(round((y1 + y2) / 2.0))

        absolute_center = (
            int(monitor.left + local_center_x),
            int(monitor.top + local_center_y),
        )

        if not monitor.contains_point(*absolute_center):
            return None

        absolute_bbox = [
            int(max(monitor.left, min(monitor.right - 1, round(monitor.left + x1)))),
            int(max(monitor.top, min(monitor.bottom - 1, round(monitor.top + y1)))),
            int(max(monitor.left + 1, min(monitor.right, round(monitor.left + x2)))),
            int(max(monitor.top + 1, min(monitor.bottom, round(monitor.top + y2)))),
        ]
        if absolute_bbox[2] <= absolute_bbox[0] or absolute_bbox[3] <= absolute_bbox[1]:
            return None

        return {
            "name": name,
            "type": element_type,
            "text": str(raw_element.get("text", "") or "").strip(),
            "center": [absolute_center[0], absolute_center[1]],
            "bbox": absolute_bbox,
            "relative_center": [local_center_x, local_center_y],
            "relative_bbox": [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
            "image_center": [
                int(round((image_bbox[0] + image_bbox[2]) / 2.0)),
                int(round((image_bbox[1] + image_bbox[3]) / 2.0)),
            ],
            "image_bbox": [int(round(value)) for value in image_bbox],
            "interactive": bool(raw_element.get("interactive", True)),
            "confidence": confidence,
            "screen": int(monitor.monitor_id),
            "screen_key": monitor.screen_key,
            "description": str(raw_element.get("description", "") or "").strip(),
        }

    def _extract_image_bbox(
        self,
        raw_element: Dict[str, Any],
        image_width: int,
        image_height: int,
    ) -> Optional[Tuple[float, float, float, float]]:
        bbox = raw_element.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                values = [float(bbox[index]) for index in range(4)]
                return self._bbox_to_image_pixels(values, image_width, image_height)
            except (TypeError, ValueError):
                pass

        # El contrato universal exige bbox normalizado. No se fabrican
        # dimensiones a partir de un centro ni se reinterpretan s1/s2 como
        # esquinas del elemento.
        return None

    def _bbox_to_image_pixels(
        self,
        values: List[float],
        image_width: int,
        image_height: int,
    ) -> Optional[Tuple[float, float, float, float]]:
        x1, y1, x2, y2 = values
        if not self._looks_normalized(values):
            return None

        x1 = x1 / self.NORMALIZED_MAX * image_width
        y1 = y1 / self.NORMALIZED_MAX * image_height
        x2 = x2 / self.NORMALIZED_MAX * image_width
        y2 = y2 / self.NORMALIZED_MAX * image_height

        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    @staticmethod
    def _image_bbox_to_monitor_bbox(
        image_bbox: Tuple[float, float, float, float],
        monitor: Any,
        image_width: int,
        image_height: int,
    ) -> Tuple[float, float, float, float]:
        scale_x = float(monitor.width) / float(image_width)
        scale_y = float(monitor.height) / float(image_height)
        x1, y1, x2, y2 = image_bbox
        return (
            max(0.0, min(float(monitor.width), x1 * scale_x)),
            max(0.0, min(float(monitor.height), y1 * scale_y)),
            max(0.0, min(float(monitor.width), x2 * scale_x)),
            max(0.0, min(float(monitor.height), y2 * scale_y)),
        )

    @staticmethod
    def _looks_normalized(values: List[float]) -> bool:
        return all(0.0 <= value <= 1000.0 for value in values)

    @staticmethod
    def _normalize_element_name(value: Any) -> str:
        value = str(value or "").strip().lower()
        value = unicodedata.normalize("NFKD", value)
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"[^a-z0-9]+", "_", value)
        return re.sub(r"_+", "_", value).strip("_")

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def _deduplicate_elements(
        elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        best: Dict[Tuple[str, Tuple[int, int], str], Dict[str, Any]] = {}
        order: List[Tuple[str, Tuple[int, int], str]] = []
        for element in elements:
            key = (
                str(element.get("name", "")),
                tuple(element.get("center", [])),
                str(element.get("type", "")),
            )
            current = best.get(key)
            if current is None:
                best[key] = element
                order.append(key)
                continue
            if float(element.get("confidence", 0.0)) > float(current.get("confidence", 0.0)):
                best[key] = element
        return [best[key] for key in order]


_calibrator_instance: Optional[UniversalVisualCalibrator] = None


def get_calibrator(
    memory: Optional[ConversationMemory] = None,
) -> UniversalVisualCalibrator:
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = UniversalVisualCalibrator(memory)
    return _calibrator_instance


def get_ui_capability(
    application: str,
    element_name: str,
    monitor_number: int,
    screenshot_path: str,
) -> Optional[UICapability]:
    return get_calibrator().get_ui_capability(
        application=application,
        element_name=element_name,
        monitor_number=monitor_number,
        screenshot_path=screenshot_path,
    )


__all__ = [
    "UniversalVisualCalibrator",
    "CalibrationPolicy",
    "UICapability",
    "CalibrationState",
    "get_calibrator",
    "get_ui_capability",
]
