"""Cerebro de JARVIS y comunicación con Ollama.

Esta versión mantiene la arquitectura existente y corrige:
- normalización de alias de acciones legacy;
- ejecución coherente a través del resultado ``[CMD: ...]``;
- uso correcto de ``context`` al guardar memoria conversacional;
- compatibilidad con nombres de acción en inglés producidos por el LLM.
"""

import json
import time
import re
from typing import Any, Dict, List, Optional, Union

import ollama

from src.hands.action_registry import ActionType, get_action_registry
from src.hands.planner.node import Node, Goal
from src.hands.planner.preconditions_effects import get_preconditions_effects_manager
from src.hands.planner.application_integration import get_application_knowledge_integrator
from src.hands.applications_core import ApplicationCapability
from src.brain.htn_integration import get_htn_integration
from src.memory.storage import get_memory_manager, Entity
from src.memory.entity_resolver import EntityResolver, ResolutionContext, EntityResolutionResult
from src.tools.os_info import get_jarvis_system_context
from src.utils.config import get_timeout_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Brain:
    """Cerebro de JARVIS con interpretación, objetivos y compatibilidad legacy."""

    ACTION_ALIASES = {
        "calibrate_chrome": "calibrar_chrome",
        "calibrate_applications": "calibrar_aplicaciones",
        "calibrate_all_applications": "calibrar_aplicaciones",
        "calibrate_all": "calibrar_aplicaciones",
        "calibrate_everything": "calibrar_aplicaciones",
        "open_chrome": "abrir_chrome",
        "open_chrome_screen": "abrir_chrome_pantalla",
        "close_chrome": "cerrar_chrome",
        "move_chrome_screen": "mover_chrome_pantalla",
        "maximize_chrome": "maximizar_chrome",
    }

    def __init__(self, model: str = "llama3") -> None:
        logger._print_log("INFO", "Inicializando cerebro con modelo: " + model, "llm.py", "__init__", 48)
        self.model = model
        self.memory_manager = get_memory_manager()
        self.entity_resolver = EntityResolver(self.memory_manager)
        self.timeout_config = get_timeout_config()
        self.action_registry = get_action_registry()
        self.preconditions_effects_manager = get_preconditions_effects_manager()

        try:
            from src.brain.htn_integration import get_htn_integration
            self.htn_integration = get_htn_integration()
            logger._print_log("INFO", "Sistema HTN integrado para descomposición jerárquica de tareas", "llm.py", "__init__", 59)
        except ImportError:
            self.htn_integration = None
            logger._print_log("WARNING", "Sistema HTN no disponible, FASE 4 parcialmente deshabilitada", "llm.py", "__init__", 62)

        logger._print_log("INFO", "Cerebro listo con sistema de planificación jerárquica mejorado.", "llm.py", "__init__", 64)
        htn_status = " + FASE 4 (HTN)" if self.htn_integration else ""
        logger._print_log("INFO", "Cerebro inicializado con FASE 15 (Objetivos) y FASE 10 (Precondiciones y Efectos)", "llm.py", "__init__", 66)
        features = [
            "detección de entidades",
            "creación de objetivos", 
            "fallback legacy",
            "precondiciones/efectos avanzados",
        ]
        if self.htn_integration:
            features.extend(["descomposición jerárquica de tareas", "ejecución de tareas", "integración HTN"])
        logger._print_log("INFO", "Sistema HTN integrado correctamente", "llm.py", "__init__", 75)

    def _normalize_action_name(self, action_name: str) -> str:
        """Convierte nombres conocidos producidos por el LLM a nombres registrados."""
        if not isinstance(action_name, str):
            return ""

        candidate = action_name.strip()
        if not candidate:
            return ""

        if self.action_registry.get_action(candidate) is not None:
            return candidate

        canonical = self.ACTION_ALIASES.get(candidate.lower())
        if canonical and self.action_registry.get_action(canonical) is not None:
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "_normalize_action_name", 91)
            return canonical

        return candidate

    def _detect_direct_action(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Detecta comandos del sistema que deben resolverse de forma
        determinista antes de consultar entidades o al LLM.

        La calibración global es especialmente importante: "calibrar
        aplicaciones" no identifica una aplicación concreta y nunca debe
        terminar en ``calibrar_chrome`` ni en ``calibrate_application_ui``,
        porque esta última exige ``app_name``.
        """
        normalized = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
        if not normalized:
            return None

        # Detectar calibración específica de navegadores
        chrome_calibration = re.search(
            r"\b(calibr(?:ar|a|e|ación|acion|ado|ada)|calibrate)\b.*\b(chrome|crón|crón)\b",
            normalized,
            re.IGNORECASE,
        )
        edge_calibration = re.search(
            r"\b(calibr(?:ar|a|e|ación|acion|ado|ada)|calibrate)\b.*\b(edge|borde)\b",
            normalized,
            re.IGNORECASE,
        )
        firefox_calibration = re.search(
            r"\b(calibr(?:ar|a|e|ación|acion|ado|ada)|calibrate)\b.*\b(firefox|firefox)\b",
            normalized,
            re.IGNORECASE,
        )
        
        if chrome_calibration:
            canonical = self._normalize_action_name("calibrar_chrome")
            if canonical == "calibrar_chrome":
                logger._print_log("INFO", "Procesando solicitud", "llm.py", "think", 130)
                return {
                    "type": "action",
                    "data": {
                        "action": canonical,
                        "parameters": {},
                    },
                    "raw": normalized,
                    "goal": None,
                    "action": {
                        "action": canonical,
                        "parameters": {},
                    },
                }
        
        if edge_calibration:
            canonical = self._normalize_action_name("calibrar_edge")
            if canonical == "calibrar_edge":
                logger._print_log("INFO", "Procesando solicitud", "llm.py", "detect_calibration_command", 148)
                return {
                    "type": "action",
                    "data": {
                        "action": canonical,
                        "parameters": {},
                    },
                    "raw": normalized,
                    "goal": None,
                    "action": {
                        "action": canonical,
                        "parameters": {},
                    },
                }
        
        if firefox_calibration:
            canonical = self._normalize_action_name("calibrar_firefox")
            if canonical == "calibrar_firefox":
                logger._print_log("INFO", "Procesando solicitud", "llm.py", "think", 148)
                return {
                    "type": "action",
                    "data": {
                        "action": canonical,
                        "parameters": {},
                    },
                    "raw": normalized,
                    "goal": None,
                    "action": {
                        "action": canonical,
                        "parameters": {},
                    },
                }

        # Evitar que una petición específica de navegador se interprete como
        # calibración global.
        browser_specific = re.search(
            r"\b(chrome|edge|firefox)\b",
            normalized,
            re.IGNORECASE,
        )
        global_calibration = (
            re.search(r"\bcalibr(?:ar|a|e|ación|acion|ado|ada)\b.*\baplicacion(?:es)?\b", normalized)
            or re.search(r"\bcalibr(?:ar|a|e|ación|acion|ado|ada)\b.*\bprogramas?\b", normalized)
            or re.search(r"\bcalibr(?:ar|a|e|ación|acion)\b.*\btodo(?:s|as)?\b", normalized)
            or re.search(r"\bcalibr(?:ar|a|e|ación|acion)\b.*\bglobal\b", normalized)
        )

        if global_calibration and not browser_specific:
            canonical = self._normalize_action_name("calibrar_aplicaciones")
            if canonical == "calibrar_aplicaciones":
                logger._print_log("INFO", "Procesando solicitud", "llm.py", "think", 198)
                return {
                    "type": "action",
                    "data": {
                        "action": canonical,
                        "parameters": {},
                    },
                    "raw": normalized,
                    "goal": None,
                    "action": {
                        "action": canonical,
                        "parameters": {},
                    },
                }

        return None

    def _get_system_context(self) -> str:
        try:
            context = get_jarvis_system_context()
            app_context = self._get_application_knowledge()
            combined_context = {
                "system": context,
                "applications": app_context,
                "capabilities": {
                    "total_applications": app_context.get("total_applications", 0),
                    "supported_capabilities": app_context.get("supported_capabilities", []),
                },
            }
            return str(combined_context)
        except Exception as exc:
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "_build_context", 229)
            return "{}"

    def _get_available_actions(self) -> List[Dict[str, Any]]:
        try:
            actions = self.action_registry.get_actions_for_llama()
            return list(actions) if actions else []
        except Exception as exc:
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "_get_available_actions", 237)
            return []

    def _get_application_knowledge(self) -> Dict[str, Any]:
        try:
            app_integrator = get_application_knowledge_integrator()
            applications = {}
            for app_name in app_integrator.application_manager.applications.keys():
                capabilities = app_integrator.get_application_capabilities(app_name)
                applications[app_name] = {
                    "capabilities": capabilities,
                    "available": app_integrator.is_application_capable(app_name, ApplicationCapability.OPEN),
                }
            return {
                "applications": applications,
                "total_applications": len(applications),
                "supported_capabilities": ["open", "navigate", "search", "play", "type", "click"],
            }
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {"applications": {}, "total_applications": 0, "supported_capabilities": []}

    def _get_domain_entities(self) -> List[Dict[str, Any]]:
        try:
            entities = self.memory_manager.get_entities_by_type("streamer")
            platforms = self.memory_manager.get_entities_by_type("platform")
            all_entities = entities + platforms
            return [
                {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "properties": entity.properties,
                }
                for entity in all_entities
            ]
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return []

    def _build_system_instruction(self, use_legacy_mode: bool = False) -> str:
        system_context = self._get_system_context()
        available_actions = self._get_available_actions()
        domain_entities = self._get_domain_entities()

        lines = [
            "Eres Jarvis, un asistente de IA.",
            "SOLO respondes en español.",
            "Cuando devuelvas una acción legacy, usa EXACTAMENTE el nombre que aparece en ACCIONES DISPONIBLES.",
            "No traduzcas ni inventes nombres de acciones.",
            "calibrar_aplicaciones = calibración GLOBAL de las aplicaciones soportadas.",
            "calibrar_chrome = calibración EXCLUSIVA de Google Chrome.",
            "Nunca uses calibrar_chrome para una petición general como 'calibrar aplicaciones'.",
            "Nunca uses calibrate_application_ui para una petición general: esa acción exige una aplicación concreta.",
            "",
        ]

        if use_legacy_mode:
            lines.extend([
                "MODO COMPATIBILIDAD (acciones existentes):",
                "Cuando el usuario solicita una acción que puede realizar JARVIS,",
                "devuelve ÚNICAMENTE un objeto JSON válido, sin Markdown ni texto adicional.",
                "",
                "FORMATO OBLIGATORIO:",
                "{",
                '  "action": "nombre_de_la_accion_exacta",',
                '  "parameters": { "parametro": "valor" }',
                "}",
                "",
                "ACCIONES DISPONIBLES:",
            ])
        else:
            lines.extend([
                "MODO PLANIFICACIÓN JERÁRQUICA:",
                "Intenta interpretar la intención y crear un objetivo del sistema.",
                "Si la petición es una acción concreta que ya existe, puedes usar el formato legacy.",
                "",
                "ENTIDADES DE DOMINIO DISPONIBLES:",
            ])
            if domain_entities:
                for entity in domain_entities:
                    lines.append(f" - {entity['name']} ({entity['type']}): {entity['properties']}")
            else:
                lines.append(" - No hay entidades de dominio disponibles.")
            lines.extend([
                "",
                "FORMATO OBJETIVO (prioridad):",
                "{",
                '  "type": "goal",',
                '  "goal": {',
                '    "type": "navigate|open_application|navigate_stream|search|etc",',
                '    "target": "valor o entidad de dominio",',
                '    "description": "Descripción del objetivo",',
                '    "priority": 1,',
                '    "constraints": []',
                "  }",
                "}",
                "",
                "FORMATO ACCIÓN LEGACY (fallback):",
                "{",
                '  "action": "nombre_de_la_accion_exacta",',
                '  "parameters": { "parametro": "valor" }',
                "}",
                "",
                "ACCIONES DISPONIBLES (fallback):",
            ])

        if available_actions:
            for action in available_actions:
                action_name = action.get("action", "")
                description = action.get("description", "")
                if action_name:
                    lines.append(f" - {action_name}: {description}")
        else:
            lines.append(" - No hay acciones registradas actualmente.")

        lines.extend(["", f"Contexto del sistema: {system_context}"])
        return "\n".join(lines)

    def _chat_text(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        top_p: float = 0.9,
        num_predict: int = 500,
        stop: Optional[List[str]] = None,
        repeat_penalty: Optional[float] = None,
    ) -> str:
        options: Dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": num_predict,
        }
        if stop is not None:
            options["stop"] = stop
        if repeat_penalty is not None:
            options["repeat_penalty"] = repeat_penalty

        try:
            response = ollama.chat(model=self.model, messages=messages, options=options)
            try:
                content = response["message"]["content"]
            except (KeyError, TypeError) as exc:
                raise ValueError("Ollama devolvió una respuesta sin message.content") from exc
            return str(content).strip() if content else ""
        except ollama.ResponseError as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            raise
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            raise

    def generate_response(self, prompt: str, use_legacy_mode: bool = False) -> str:
        if not prompt or not prompt.strip():
            return ""
        system_instruction = self._build_system_instruction(use_legacy_mode)
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt.strip()},
        ]
        logger._print_log("INFO", "Enviando " + str(len(messages)) + " mensajes al modelo " + self.model, "llm.py", "generate_response", 398)
        try:
            result = self._chat_text(messages, temperature=0.7, top_p=0.9, num_predict=500)
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return result
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return f"ERROR: {exc}"

    def execute_goal(self, goal_data: Union[Dict[str, Any], "Goal"]) -> Dict[str, Any]:
        if hasattr(goal_data, "to_dict"):
            goal_dict = goal_data.to_dict()
        else:
            goal_dict = goal_data
        try:
            goal_type = goal_dict.get("type", "")
            target = goal_dict.get("target", "")
            description = goal_dict.get("description", "")
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "execute_goal", 416)
            if goal_type == "navigate_stream" and target:
                return {"type": "legacy_action", "action": "navigate_to_url", "parameters": {"url": target}, "reasoning": f"Navegando a stream: {target}"}
            if goal_type == "navigate" and target:
                return {"type": "legacy_action", "action": "navigate_to_url", "parameters": {"url": target}, "reasoning": f"Navegando a: {target}"}
            if goal_type == "open_application":
                return {"type": "legacy_action", "action": f"open_{target.lower().replace(' ', '_')}", "parameters": {}, "reasoning": f"Abriendo aplicación: {target}"}
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {"type": "error", "message": f"Objetivo '{goal_type}' aún no implementado en el sistema legacy", "goal_data": goal_dict}
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {"type": "error", "message": f"Error ejecutando objetivo: {exc}", "goal_data": goal_dict}

    def process_intent_to_execution(self, prompt: str) -> Dict[str, Any]:
        try:
            intent_result = self.interpret_intent(prompt)
            if intent_result["type"] == "goal":
                goals = intent_result.get("goals", [])
                if not goals:
                    goal = intent_result.get("goal")
                    goals = [goal] if goal is not None else []
                results = []
                htn_results = []
                for goal in goals:
                    if self.htn_integration:
                        htn_results.append(self.htn_integration.process_goal_through_htn(goal, {}))
                    results.append(self.execute_goal(goal))
                result_data = {
                    "type": "htn_execution_results" if self.htn_integration and htn_results else "execution_results",
                    "legacy_results": results,
                    "original_intent": intent_result,
                    "reasoning": "Objetivos interpretados y ejecutados" + (" con HTN" if self.htn_integration else ""),
                }
                if self.htn_integration and htn_results:
                    result_data["htn_results"] = [r.__dict__ for r in htn_results]
                return result_data
            if intent_result["type"] == "action":
                return {"type": "legacy_execution", "action": intent_result["action"], "parameters": intent_result["parameters"], "reasoning": "Acción legacy lista para ejecución"}
            return intent_result
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {"type": "error", "message": f"Error en procesamiento: {exc}", "original_prompt": prompt}

    def process_with_htn(self, prompt: str) -> Dict[str, Any]:
        if not self.htn_integration:
            return {"type": "htn_error", "message": "Sistema HTN no disponible", "original_prompt": prompt}
        try:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            htn_result = self.htn_integration.create_and_execute_htn_goal(prompt, {})
            if htn_result.success:
                return {"type": "htn_success", "goal_id": htn_result.goal_id, "goal_type": htn_result.goal_type, "decomposed_tasks": htn_result.decomposed_tasks, "execution_results": htn_result.execution_results, "total_execution_time": htn_result.total_execution_time, "reasoning": "Objetivo procesado exitosamente con descomposición jerárquica"}
            return {"type": "htn_failure", "goal_id": htn_result.goal_id, "goal_type": htn_result.goal_type, "error_message": htn_result.error_message, "reasoning": "Fallo en procesamiento con HTN"}
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {"type": "htn_error", "message": f"Error en procesamiento HTN: {exc}", "original_prompt": prompt}

    def get_htn_insights(self) -> Dict[str, Any]:
        if not self.htn_integration:
            return {"error": "Sistema HTN no disponible"}
        try:
            return self.htn_integration.get_htn_insights()
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {"error": str(exc)}

    def _extract_parameters_from_input(self, user_input: str, entity: Entity) -> Dict[str, Any]:
        try:
            parameters: Dict[str, Any] = {}
            input_lower = user_input.lower()
            if any(word in input_lower for word in ["pantalla", "monitor"]):
                screen_match = re.search(r'pantalla\s*(\d+)|monitor\s*(\d+)', input_lower)
                if screen_match:
                    parameters["screen"] = int(screen_match.group(1) or screen_match.group(2))
            if entity.type == "streamer":
                if "hd" in input_lower or "alta calidad" in input_lower:
                    parameters["quality"] = "hd"
                if "voz" in input_lower or "audio" in input_lower:
                    parameters["audio"] = True
            elif entity.type == "platform":
                if "buscar" in input_lower:
                    parameters["search_query"] = self._extract_search_query(user_input)
            elif entity.type == "application":
                if "ventana" in input_lower or "window" in input_lower:
                    parameters["window_mode"] = "normal"
                if "maximizar" in input_lower:
                    parameters["window_mode"] = "maximized"
                if "minimizar" in input_lower:
                    parameters["window_mode"] = "minimized"
            return parameters
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return {}

    def _extract_search_query(self, user_input: str) -> str:
        try:
            patterns = [r'buscar\s+(.+)', r'buscar\s+en\s+(.+)', r'search\s+(.+)', r'search\s+in\s+(.+)', r'find\s+(.+)']
            for pattern in patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            return ""
        except Exception:
            return ""

    @staticmethod
    def _clean_json_response(response_text: str) -> str:
        text = (response_text or "").strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3].rstrip()
        if not text.startswith("{"):
            start = text.find("{")
            if start != -1:
                text = text[start:]
        if not text.endswith("}"):
            end = text.rfind("}")
            if end != -1:
                text = text[:end + 1]
        return text.strip()

    def parse_model_response(self, llm_response: str) -> Optional[Dict[str, Any]]:
        clean_response = self._clean_json_response(llm_response)
        if not clean_response:
            return None
        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return None
        if not isinstance(data, dict):
            logger._print_log("WARNING", "[BRAIN] El JSON del modelo no contiene un objeto.", "llm.py", "parse_model_response", 549)
            return None
        return data

    def _extract_entities_from_input(self, user_input: str) -> List[Entity]:
        try:
            context = ResolutionContext(
                conversation_history=[],
                current_intent=None,
                recent_entities=[],
                user_preferences={
                    p.preference_key: p.preference_value
                    for p in self.memory_manager.get_user_preferences("default", "general")
                },
                session_info={"timestamp": time.time()},
            )
            resolution_result = self.entity_resolver.resolve_entity(user_input, context, None)
            resolved_entities = [resolution_result.entity]
            resolved_entities.extend(resolution_result.alternatives)
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "_extract_entities_from_input", 568)
            return resolved_entities
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return self._extract_entities_fallback(user_input)

    def _extract_entities_fallback(self, user_input: str) -> List[Entity]:
        try:
            entities: List[Entity] = []
            all_entities: List[Entity] = []
            for entity_type in ["streamer", "platform", "application", "website"]:
                try:
                    entities_of_type = self.memory_manager.get_entities_by_type(entity_type)
                    if isinstance(entities_of_type, list):
                        all_entities.extend(entities_of_type)
                except Exception as exc:
                    logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            user_input_lower = user_input.lower()
            for entity in all_entities:
                entity_name_lower = entity.name.lower()
                if entity_name_lower == user_input_lower or entity_name_lower in user_input_lower or user_input_lower in entity_name_lower:
                    entities.append(entity)
                elif entity.properties:
                    properties_text = " ".join(str(v).lower() for v in entity.properties.values())
                    if any(keyword in properties_text for keyword in user_input_lower.split() if keyword):
                        entities.append(entity)
            unique_entities: Dict[str, Entity] = {}
            for entity in entities:
                unique_entities[entity.id] = entity
            return list(unique_entities.values())
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return []

    def _create_goal_from_entity(self, entity: Entity, user_input: str, resolution_result: Optional[EntityResolutionResult] = None) -> Optional[Goal]:
        try:
            input_lower = user_input.lower()
            if entity.type == "streamer":
                if any(word in input_lower for word in ["abrir", "abre", "abrir stream", "stream", "ver"]):
                    goal_type = "navigate_stream"
                    target = entity.properties.get("url", "")
                    description = f"Abrir stream de {entity.name}"
                elif any(word in input_lower for word in ["buscar", "info", "datos"]):
                    goal_type = "search_streamer"
                    target = entity.name
                    description = f"Buscar información de {entity.name}"
                else:
                    goal_type = "navigate_stream"
                    target = entity.properties.get("url", "")
                    description = f"Abrir stream de {entity.name}"
            elif entity.type == "platform":
                if any(word in input_lower for word in ["abrir", "abre", "ir a", "navegar"]):
                    goal_type = "navigate"
                    target = entity.properties.get("url", "")
                    description = f"Navegar a {entity.name}"
                elif any(word in input_lower for word in ["buscar", "buscar en"]):
                    goal_type = "search_in_platform"
                    target = entity.name
                    description = f"Buscar en {entity.name}"
                else:
                    goal_type = "navigate"
                    target = entity.properties.get("url", "")
                    description = f"Navegar a {entity.name}"
            elif entity.type == "application":
                if any(word in input_lower for word in ["abrir", "abre", "iniciar", "lanzar"]):
                    goal_type = "open_application"
                    target = entity.name
                    description = f"Abrir aplicación {entity.name}"
                elif any(word in input_lower for word in ["cerrar", "cierra", "terminar"]):
                    goal_type = "close_application"
                    target = entity.name
                    description = f"Cerrar aplicación {entity.name}"
                else:
                    goal_type = "open_application"
                    target = entity.name
                    description = f"Abrir aplicación {entity.name}"
            else:
                goal_type = "navigate"
                target = entity.properties.get("url", "")
                description = f"Realizar acción con {entity.name}"

            goal_id = f"{goal_type}_{entity.id}_{int(time.time())}"
            parameters = self._extract_parameters_from_input(user_input, entity)
            enhanced_metadata = {
                "entity_id": entity.id,
                "entity_type": entity.type,
                "extracted_parameters": parameters,
                "original_input": user_input,
                "resolution_info": {
                    "resolution_method": resolution_result.resolution_method if resolution_result else "fallback",
                    "confidence": resolution_result.confidence if resolution_result else 0.7,
                    "context_used": resolution_result.context_used if resolution_result else {},
                    "timestamp": resolution_result.timestamp if resolution_result else time.time(),
                },
            }

            if goal_type in ["navigate_stream", "navigate"] and target:
                enhanced_metadata["entity_data"] = {
                    "entity_name": entity.name,
                    "entity_type": entity.type,
                    "entity_url": target,
                    "properties": entity.properties,
                }
                enhanced_metadata["required_capabilities"] = self._get_entity_capabilities(entity, goal_type)
                enhanced_metadata["base_cost"] = self._calculate_entity_goal_cost(entity, goal_type)
                enhanced_metadata["complexity"] = self._calculate_entity_complexity(entity, goal_type)

            goal = Goal(
                id=goal_id,
                type=goal_type,
                target=target,
                description=description,
                priority=1,
                constraints=parameters.get("constraints", []),
                nodes=[],
                metadata=enhanced_metadata,
            )

            self.memory_manager.add_conversational_memory(
                message=user_input,
                response=f"Objetivo creado: {description}",
                intent=goal_type,
                entities=[entity.id],
                context={
                    "goal_id": goal_id,
                    "parameters": parameters,
                    "confidence": resolution_result.confidence if resolution_result else 0.7,
                    "resolution_method": resolution_result.resolution_method if resolution_result else "fallback",
                },
            )
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "_create_goal_from_entity", 698)
            return goal
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return None

    def _get_entity_capabilities(self, entity: Entity, goal_type: str) -> List[str]:
        base_capabilities: List[str] = []
        if goal_type in ["navigate_stream", "navigate", "search_streamer"]:
            base_capabilities = ["open_application", "navigate", "focus_element", "type_text", "press_key"]
        elif goal_type == "open_application":
            base_capabilities = ["open_application", "activate_window"]
        elif goal_type == "close_application":
            base_capabilities = ["close_application", "activate_window"]
        if entity.type == "streamer":
            base_capabilities.extend(["stream_interaction", "chat_interaction"])
        elif entity.type == "platform":
            base_capabilities.extend(["platform_navigation", "search_functionality"])
        elif entity.type == "application":
            base_capabilities.extend(["application_control", "window_management"])
        return list(set(base_capabilities))

    def _calculate_entity_goal_cost(self, entity: Entity, goal_type: str) -> float:
        base_cost = 10.0
        if entity.type == "streamer":
            base_cost = 8.0
        elif entity.type == "platform":
            base_cost = 12.0
        elif entity.type == "application":
            base_cost = 15.0
        if goal_type == "search_streamer":
            base_cost *= 0.8
        elif goal_type == "close_application":
            base_cost *= 0.6
        return base_cost

    def _calculate_entity_complexity(self, entity: Entity, goal_type: str) -> float:
        complexity = 1.0
        if entity.properties:
            complexity += len(entity.properties) * 0.1
            if "url" in entity.properties:
                complexity *= 0.9
        if goal_type in ["navigate_stream", "navigate"]:
            complexity *= 1.2
        elif goal_type == "search":
            complexity *= 0.8
        return min(complexity, 2.0)

    def interpret_intent(self, prompt: str) -> Dict[str, Any]:
        if not prompt or not prompt.strip():
            return {"type": "unknown", "data": None, "raw": "", "goal": None, "action": None}

        logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)

        direct_action = self._detect_direct_action(prompt)
        if direct_action is not None:
            return direct_action

        entities: List[Entity] = []
        resolution_results: List[Optional[EntityResolutionResult]] = []
        try:
            context = ResolutionContext(
                conversation_history=[],
                current_intent=None,
                recent_entities=[],
                user_preferences={
                    p.preference_key: p.preference_value
                    for p in self.memory_manager.get_user_preferences("default", "general")
                },
                session_info={"timestamp": time.time()},
            )
            resolution_result = self.entity_resolver.resolve_entity(prompt, context, None)
            # Una entidad temporal/no resuelta no debe secuestrar una acción legacy.
            if resolution_result.resolution_method != "temporary_creation":
                entities = [resolution_result.entity]
                entities.extend(resolution_result.alternatives)
                resolution_results = [resolution_result]
            logger._print_log("INFO", "Procesando solicitud", "llm.py", "interpret_intent", 775)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            entities = self._extract_entities_fallback(prompt)
            resolution_results = [None] * len(entities)
            logger._print_log("INFO", "Procesando solicitud: " + str([e.name for e in entities]), "llm.py", "interpret_intent", 780)

        if entities:
            goals: List[Goal] = []
            for i, entity in enumerate(entities):
                resolution_result = resolution_results[i] if i < len(resolution_results) else None
                goal = self._create_goal_from_entity(entity, prompt, resolution_result)
                if goal:
                    goals.append(goal)
            if goals:
                return {
                    "type": "goal",
                    "data": [{"goal": g.to_dict()} for g in goals],
                    "raw": f"Objetivos creados desde entidades: {[g.description for g in goals]}",
                    "goal": goals[0] if len(goals) == 1 else goals,
                    "goals": goals,
                    "action": None,
                }

        raw_response = self.generate_response(prompt, use_legacy_mode=False)
        parsed = self.parse_model_response(raw_response)
        if parsed:
            if parsed.get("type") == "goal" or isinstance(parsed.get("goal"), dict):
                goal_data = parsed.get("goal", parsed)
                try:
                    goal = self._create_system_goal(goal_data, prompt)
                    if goal:
                        logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
                        return {"type": "goal", "data": goal_data, "raw": raw_response, "goal": goal, "action": None}
                except Exception as exc:
                    logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            if "action" in parsed:
                canonical_action = self._normalize_action_name(parsed.get("action", ""))
                if canonical_action:
                    parsed["action"] = canonical_action
                logger._print_log("INFO", "Procesando solicitud", "llm.py", "interpret_intent", 815)
                return {"type": "action", "data": parsed, "raw": raw_response, "goal": None, "action": parsed}

        logger._print_log("INFO", "[INTERPRET] Usando modo legacy como fallback", "llm.py", "interpret_intent", 818)
        raw_response = self.generate_response(prompt, use_legacy_mode=True)
        parsed = self.parse_model_response(raw_response)
        if parsed and "action" in parsed:
            canonical_action = self._normalize_action_name(parsed.get("action", ""))
            if canonical_action:
                parsed["action"] = canonical_action
            return {"type": "action", "data": parsed, "raw": raw_response, "goal": None, "action": parsed}

        return {"type": "unknown", "data": parsed, "raw": raw_response, "goal": None, "action": None}

    def _create_system_goal(self, goal_data: Dict[str, Any], user_input: str) -> Optional[Goal]:
        try:
            goal_type = goal_data.get("type", "")
            target = goal_data.get("target", "")
            description = goal_data.get("description", f"Realizar: {goal_type}")
            if not goal_type or not target:
                logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
                return None
            timestamp = int(time.time())
            goal_id = f"{goal_type}_{target}_{timestamp}"
            constraints = goal_data.get("constraints", [])
            goal = Goal(
                id=goal_id,
                type=goal_type,
                target=target,
                description=description,
                priority=goal_data.get("priority", 1),
                constraints=constraints,
                created_at=time.time(),
            )
            self.memory_manager.add_conversational_memory(
                message=user_input,
                response=f"Objetivo creado: {description}",
                intent=goal_type,
                entities=[],
            )
            self.memory_manager.update_world_state(
                "last_intention",
                {"user_input": user_input, "goal_type": goal_type, "target": target, "timestamp": time.time()},
            )
            return goal
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return None

    def think(self, prompt: str, use_legacy_execution: bool = False) -> str:
        logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
        if not prompt or not prompt.strip():
            return "No recibí ningún mensaje."

        interpretation = self.interpret_intent(prompt)
        if interpretation["type"] == "goal":
            goal = interpretation["goal"]
            if isinstance(goal, list):
                goal = goal[0]
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            self.memory_manager.add_conversational_memory(
                message=prompt,
                response=f"Objetivo creado: {goal.description}",
                intent=goal.type,
                entities=[goal.target] if goal.target else [],
            )
            return f"Objetivo registrado: {goal.description}. El sistema lo procesará próximamente."

        if interpretation["type"] == "action":
            action_data = interpretation["action"]
            action_name = self._normalize_action_name(action_data.get("action", ""))
            parameters = action_data.get("parameters", {}) or {}
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)

            if not action_name:
                return "No entendí la acción solicitada."

            if use_legacy_execution:
                result = self._execute_legacy_action(action_name, parameters)
                self.memory_manager.add_conversational_memory(
                    message=prompt,
                    response=f"Acción ejecutada: {action_name}",
                    intent="legacy_action",
                    entities=[],
                )
                return f"✅ {result}"

            # Devolver un comando ejecutable por la fachada Executor de main.py.
            return f"[CMD: {action_name}]"

        logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
        return "No entendí tu solicitud. ¿Podrías repetirla de otra manera?"

    def _execute_legacy_action(self, action_name: str, parameters: Dict[str, Any]) -> str:
        try:
            action_name = self._normalize_action_name(action_name)
            is_valid = self.action_registry.validate_action(action_name, parameters)
            if not is_valid:
                return f"❌ Acción no válida: {action_name}"
            result = self.action_registry.execute_action(action_name, parameters)
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return f"✅ Acción ejecutada: {action_name}. Resultado: {result}"
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return f"❌ Error ejecutando {action_name}: {exc}"

    def process_action_response(self, llm_response: str) -> str:
        try:
            action_data = self.parse_model_response(llm_response)
            if not action_data or "action" not in action_data:
                return llm_response
            action_name = self._normalize_action_name(action_data.get("action"))
            parameters = action_data.get("parameters", {}) or {}
            if not isinstance(action_name, str) or not action_name.strip():
                return llm_response
            if not isinstance(parameters, dict):
                return f"❌ Parámetros incorrectos para la acción: {action_name}"
            return self._execute_legacy_action(action_name.strip(), parameters)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return llm_response

    def think_with_image(self, prompt: str, image_path: str) -> str:
        logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
        if not prompt or not prompt.strip():
            return "No recibí instrucciones para la imagen."
        if not image_path:
            return "No se proporcionó ninguna imagen."
        try:
            return self._chat_text(
                [{"role": "user", "content": prompt.strip(), "images": [image_path]}],
                temperature=0.1,
                top_p=0.9,
                num_predict=20,
                stop=["\n"],
                repeat_penalty=1.2,
            )
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return f"ERROR: {exc}"

    def analyze_image(self, image_path: str, analysis_prompt: str) -> str:
        logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
        if not image_path:
            return "No se proporcionó imagen"
        if not analysis_prompt or not analysis_prompt.strip():
            return "No se proporcionaron instrucciones para el análisis."
        try:
            result = self._chat_text(
                [{"role": "user", "content": analysis_prompt.strip(), "images": [image_path]}],
                temperature=0.1,
                top_p=0.9,
                num_predict=500,
                stop=["\n\n", "User:", "Assistant:"],
                repeat_penalty=1.1,
            )
            logger._print_log("INFO", "[+] Análisis de imagen completado", "llm.py", "analyze_image", 971)
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return result
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return f"ERROR: {exc}"

    def clear_memory(self) -> None:
        logger._print_log("INFO", "Limpiando memoria del cerebro", "llm.py", "clear_memory", 979)
        try:
            self.memory_manager.clear_memory()
            logger._print_log("INFO", "[+] Memoria limpia exitosamente", "llm.py", "clear_memory", 982)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        try:
            memories = self.memory_manager.get_conversational_memory()
            return [m.to_dict() if hasattr(m, "to_dict") else m for m in memories]
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
            return []

    def get_available_actions(self) -> List[Dict[str, Any]]:
        return self._get_available_actions()

    def get_current_goals(self) -> List[Goal]:
        return []

    def get_system_state(self) -> Dict[str, Any]:
        state = self.memory_manager.get_world_state()
        return state.to_dict() if hasattr(state, "to_dict") else state

    def get_domain_entities(self) -> List[Entity]:
        return self.memory_manager.get_entities_by_type("streamer") + self.memory_manager.get_entities_by_type("platform")

    def create_goal_from_user_input(self, user_input: str) -> Optional[Goal]:
        entities = self._extract_entities_from_input(user_input)
        if entities:
            return self._create_goal_from_entity(entities[0], user_input)
        return None

    def get_planner_ready_data(self) -> Dict[str, Any]:
        return {
            "goals": self.get_current_goals(),
            "domain_entities": self.get_domain_entities(),
            "current_state": self.get_system_state(),
            "conversation_history": self.get_conversation_history(),
            "available_actions": self.get_available_actions(),
            "memory_stats": self.memory_manager.get_memory_stats(),
        }

    def register_node(self, node_config: Dict[str, Any]) -> None:
        try:
            node = Node.from_dict(node_config)
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "llm.py", "method", 256)

    def register_task(self, task_config: Dict[str, Any]) -> None:
        logger._print_log("INFO", "Procesando solicitud", "llm.py", "register_task", 1031)


def get_jarvis_context():
    try:
        return get_jarvis_system_context()
    except Exception:
        return {}
