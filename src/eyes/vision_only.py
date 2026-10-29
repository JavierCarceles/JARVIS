# src/eyes/vision_only.py

"""
Visión por computadora usando Qwen3-VL mediante Ollama.

Versión simplificada sin dependencias circulares.
"""

from __future__ import annotations

import json
import time
from enum import Enum

from typing import List, Dict, Any

import ollama
from pydantic import BaseModel, Field

from src.eyes.screen_capture import ScreenCapture
from src.utils.logger import get_logger
from src.utils.ui_element_model import UIElementData

logger = get_logger(__name__)


class VisionNodeType(Enum):
    """Tipos de nodos de visión para el planificador."""
    SCREEN_ANALYSIS = "screen_analysis"
    UI_DETECTON = "ui_detection"
    ELEMENT_VERIFICATION = "element_verification"
    STATE_VERIFICATION = "state_verification"
    CALIBRATION_ANALYSIS = "calibration_analysis"
    APPLICATION_DETECTION = "application_detection"


class UIElement(UIElementData):
    """Elemento UI detectado por visi\u00f3n (forma can\u00f3nica unificada).

    Deriva de :class:`UIElementData`, compartiendo as\u00ed la misma forma
    can\u00f3nica que ``eyes.vision`` y ``hands.applications_core``.
    """

    model_config = {"populate_by_name": True}


class VisionResponse(BaseModel):
    """Respuesta estructurada del modelo de visión."""

    elements: List[UIElement] = Field(
        default_factory=list,
    )


class Vision:
    """
    Sistema de visión integrado con la arquitectura de planificación jerárquica.

    Capacidades principales:
    1. Análisis de pantalla completa para estado del mundo (FASE 3)
    2. Detección estructurada de elementos UI (FASE 12)
    3. Verificación de resultados de acciones (FASE 9)
    4. Análisis para calibración universal (FASE 13)
    5. Detección de aplicaciones y su estado
    6. Nodos de visión reutilizables para el planificador (FASE 1)

    La salida de analyze_image() está orientada al calibrador universal:
        name
        type
        bbox
        confidence

    Las coordenadas del modelo pueden ser normalizadas y son convertidas
    posteriormente por UniversalVisualCalibrator.
    """

    def __init__(
        self,
        model: str = "qwen3-vl:8b",
    ) -> None:
        self.model = model
        self.temperature = 0
        self.screen_capture = ScreenCapture()
        self.memory_manager = None  # Evitar circular import
        
        # Crear nodos de visión estándar para el planificador
        self._vision_nodes = self._create_vision_nodes()

        logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
        logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
    
    def _create_vision_nodes(self) -> List[Any]:
        """Crea los nodos de visión estándar para el planificador."""
        nodes = [
            # Aquí podríamos agregar nodos específicos si fuera necesario
        ]
        return nodes

    def analyze_image(self, image_path: str, prompt: str) -> str:
        """
        Analiza una imagen usando el modelo de visión.
        
        Args:
            image_path: Ruta de la imagen a analizar
            prompt: Instrucciones para el análisis
            
        Returns:
            Respuesta del modelo como string
        """
        logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
        
        try:
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
                format="json",
                options={
                    "temperature": 0.1,
                    "num_ctx": 8192,
                    "num_predict": 500,
                },
                keep_alive="5m",
            )

            result = response["message"]["content"]

            if not isinstance(result, str):
                result = str(result)

            result = result.strip()
            logger._print_log("info", r"[VISION] Análisis de imagen completado [file:vision_only.py, method:analyze_image, line:162]", "vision_only.py", "method", 162)
            logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
            logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
            
            return result
            
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
            return f"ERROR: {exc}"

    def verify_action_result(self, expected_state: Dict[str, Any], tolerance: float = 0.1) -> Dict[str, Any]:
        """
        Verifica si una acción tuvo el resultado esperado visualmente.
        
        Args:
            expected_state: Estado esperado de la acción
            tolerance: Tolerancia para la verificación
            
        Returns:
            Resultado de la verificación
        """
        try:
            # Capturar pantalla
            image_path = self.screen_capture.capture_monitor(1)
            
            if not image_path:
                return {
                    "success": False,
                    "verified": False,
                    "error": "No se pudo capturar pantalla"
                }
            
            # Construir prompt de verificación específico
            expected_type = expected_state.get("type", "unknown")
            
            if expected_type == "url_loaded":
                expected_url = expected_state.get("url", "")
                prompt = f"""
Verifica si en esta captura de pantalla:
1. El navegador está cargando/mostrando la URL: {expected_url}
2. La barra de direcciones muestra esta URL o similar
3. La página parece haber cargado (no hay spinner de carga)

Responde en JSON:
{{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "details": "descripción de lo que se ve",
  "current_url": "URL detectada si es visible"
}}
"""
            elif expected_type == "element_focused":
                element_name = expected_state.get("element", "")
                prompt = f"""
Verifica si el elemento '{element_name}' está enfocado/activo en la pantalla.
Busca indicadores visuales de foco: cursor parpadeando, borde azul, texto seleccionado, etc.

Responde en JSON:
{{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "details": "descripción"
}}
"""
            else:
                # Verificación genérica
                prompt = f"""
Analiza la pantalla y verifica si se cumple esta condición: {expected_state}

Responde en JSON:
{{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "details": "descripción"
}}
"""
            
            # Analizar con visión
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
                format="json",
                options={
                    "temperature": 0.1,
                    "num_ctx": 8192,
                    "num_predict": 1024,
                },
                keep_alive="5m",
            )

            result = response["message"]["content"]

            if not isinstance(result, str):
                result = str(result)

            result = result.strip()
            
            try:
                data = json.loads(result)
                verified = data.get("verified", False)
                confidence = data.get("confidence", 0.0)
                
                # Considerar verificado si confidence > tolerance
                success = verified and confidence >= tolerance
                
                return {
                    "success": True,
                    "verified": success,
                    "confidence": confidence,
                    "details": data.get("details", ""),
                    "expected_state": expected_state,
                    "tolerance": tolerance
                }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "verified": False,
                    "error": "Respuesta no válida del modelo de visión"
                }
            
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
            return {
                "success": False,
                "verified": False,
                "error": str(exc)
            }
    
    def detect_application_state(self, app_name: str) -> Any:
        """
        Detecta el estado de una aplicación específica visualmente.
        
        Este nodo es usado por:
        - El planificador para comprobar precondiciones (ej: chrome_open)
        - application_preflight.py antes de ejecutar rutas
        - La construcción del WorldState
        
        Args:
            app_name: Nombre de la aplicación a detectar
            
        Returns:
            ApplicationInfo con estado detectado
        """
        logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
        
        try:
            image_path = self.screen_capture.capture_monitor(1)
            if not image_path:
                # Importar aquí para evitar circular imports
                from src.eyes.screen import ApplicationInfo, ApplicationState
                return ApplicationInfo(
                    name=app_name,
                    state=ApplicationState.CLOSED
                )
            
            prompt = f"""
Analiza esta captura de pantalla y determina si la aplicación '{app_name}' está:
1. Abierta y visible
2. En primer plano (activa)
3. Minimizada o en segundo plano
4. Cerrada (no visible)

Busca indicadores visuales: título de ventana, barra de tareas, iconos, contenido característico.

Responde en JSON:
{{
  "detected": true/false,
  "state": "active/open/minimized/maximized/closed",
  "window_title": "título detectado",
  "monitor": 1,
  "visible_elements": ["elemento1", "elemento2"],
  "confidence": 0.0-1.0
}}
"""
            
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
                format="json",
                options={
                    "temperature": 0.1,
                    "num_ctx": 8192,
                    "num_predict": 1024,
                },
                keep_alive="5m",
            )

            result = response["message"]["content"]

            if not isinstance(result, str):
                result = str(result)

            result = result.strip()
            
            try:
                data = json.loads(result)
                detected = data.get("detected", False)
                
                if not detected:
                    # Importar aquí para evitar circular imports
                    from src.eyes.screen import ApplicationInfo, ApplicationState
                    return ApplicationInfo(
                        name=app_name,
                        state=ApplicationState.CLOSED
                    )
                
                state_str = data.get("state", "closed").lower()

                # Importar aquí para evitar circular imports
                from src.eyes.screen import ApplicationInfo, ApplicationState
                state_map = {
                    "active": ApplicationState.ACTIVE,
                    "open": ApplicationState.OPEN,
                    "minimized": ApplicationState.MINIMIZED,
                    "maximized": ApplicationState.MAXIMIZED,
                    "closed": ApplicationState.CLOSED
                }

                if state_str in state_map:
                    resolved_state = state_map[state_str]
                else:
                    # Un estado desconocido NO se convierte en un estado valido
                    # por defecto (anteriormente caia en ApplicationState.OPEN,
                    # lo cual podia llevar a creencias falsas sobre una app abierta).
                    # Se registra el estado desconocido y se usa CLOSED como fallback
                    # seguro: no implica que la aplicacion este abierta/activo.
                    resolved_state = ApplicationState.CLOSED
                    logger._print_log(
                        "info",
                        f"Estado desconocido omitido en vision_only: '{state_str}' "
                        "[file:vision_only.py, method:detect_application_state]",
                        "vision_only.py", "detect_application_state", 370,
                    )

                return ApplicationInfo(
                    name=app_name,
                    state=resolved_state,
                    window_title=data.get("window_title"),
                    monitor=data.get("monitor", 1),
                    visible_elements=data.get("visible_elements", [])
                )
            except json.JSONDecodeError:
                # Importar aquí para evitar circular imports
                from src.eyes.screen import ApplicationInfo, ApplicationState
                return ApplicationInfo(
                    name=app_name,
                    state=ApplicationState.CLOSED
                )
            
        except Exception as exc:
            import traceback; traceback.print_exc()
            logger._print_log("info", "Procesando solicitud", "vision_only.py", "method", 112)
            # Importar aquí para evitar circular imports
            from src.eyes.screen import ApplicationInfo, ApplicationState
            return ApplicationInfo(
                name=app_name,
                state=ApplicationState.CLOSED
            )
    
    def get_vision_capabilities(self) -> Dict[str, Any]:
        """Devuelve las capacidades de visión disponibles para el planificador."""
        return {
            "nodes": [node.to_dict() for node in self._vision_nodes],
            "model": self.model,
            "total_cost": self.get_total_vision_cost(),
            "available_types": [t.value for t in VisionNodeType]
        }

    def get_total_vision_cost(self) -> float:
        """Calcula el costo total de las capacidades de visión."""
        return 10.0  # Costo fijo para simplificar


__all__ = [
    "UIElement",
    "VisionResponse", 
    "Vision",
    "VisionNodeType"
]