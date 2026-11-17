"""Cerebro de JARVIS y comunicacion con Ollama.

Esta version mantiene la arquitectura existente y corrige:
- normalizacion de alias de acciones legacy;
- ejecucion coherente a traves del resultado ``[CMD: ...]``;
- uso correcto de ``context`` al guardar memoria conversacional;
- compatibilidad con nombres de accion en ingles producidos por el LLM.
"""

import copy
import json
import time
import re
from typing import Any, Dict, List, Optional, Union

import ollama

from src.hands.actions.action_registry import ActionType, get_action_registry
from src.hands.planner.node import Node, Goal, build_goal, new_goal_id, validate_goal
from src.hands.planner.preconditions_effects import get_preconditions_effects_manager
from src.hands.planner.application_integration import get_application_knowledge_integrator
from src.hands.apps.applications_core import ApplicationCapability
from src.brain.htn_integration import get_htn_integration
from src.memory.storage import get_memory_manager, Entity
from src.memory.entity_resolver import EntityResolver, ResolutionContext, EntityResolutionResult
from src.tools.os_info import get_jarvis_system_context
from src.core.config import get_timeout_config
from src.core.log import get_logger

logger = get_logger(__name__)


class Brain:
    """Cerebro de JARVIS con interpretacion, objetivos y compatibilidad legacy."""

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
        logger.info("Inicializando cerebro con modelo: " + model)
        self.model = model
        self.memory_manager = get_memory_manager()
        self.entity_resolver = EntityResolver(self.memory_manager)
        self.timeout_config = get_timeout_config()
        self.action_registry = get_action_registry()
        self.preconditions_effects_manager = get_preconditions_effects_manager()

        try:
            from src.brain.htn_integration import get_htn_integration
            self.htn_integration = get_htn_integration()
            logger.info("Sistema HTN integrado para descomposicion jerarquica de tareas")
        except ImportError:
            self.htn_integration = None
            logger.warning("Sistema HTN no disponible, FASE 4 parcialmente deshabilitada")

        logger.info("Cerebro listo con sistema de planificacion jerarquica mejorado.")
        htn_status = " + FASE 4 (HTN)" if self.htn_integration else ""
        logger.info("Cerebro inicializado con FASE 15 (Objetivos) y FASE 10 (Precondiciones y Efectos)")
        features = [
            "detecci\u00f3n de entidades",
            "creaci\u00f3n de objetivos", 
            "fallback legacy",
            "precondiciones/efectos avanzados",
        ]
        if self.htn_integration:
            features.extend(["descomposici\u00f3n jer\u00e1rquica de tareas", "ejecuci\u00f3n de tareas", "integraci\u00f3n HTN"])
        logger.info("Sistema HTN integrado correctamente")

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
            return canonical

        return candidate

    def _detect_direct_action(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Detecta comandos del sistema que deben resolverse de forma
        determinista antes de consultar entidades o al LLM.

        La calibracion global es especialmente importante: "calibrar
        aplicaciones" no identifica una aplicacion concreta y nunca debe
        terminar en ``calibrar_chrome`` ni en ``calibrate_application_ui``,
        porque esta ultima exige ``app_name``.
        """
        normalized = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
        if not normalized:
            return None

        # Detectar calibracion especifica de navegadores
        chrome_calibration = re.search(
            r"\b(calibr(?:ar|a|e|aci\u00f3n|acion|ado|ada)|calibrate)\b.*\b(chrome|cr\u00f3n|cr\u00f3n)\b",
            normalized,
            re.IGNORECASE,
        )
        edge_calibration = re.search(
            r"\b(calibr(?:ar|a|e|aci\u00f3n|acion|ado|ada)|calibrate)\b.*\b(edge|borde)\b",
            normalized,
            re.IGNORECASE,
        )
        firefox_calibration = re.search(
            r"\b(calibr(?:ar|a|e|aci\u00f3n|acion|ado|ada)|calibrate)\b.*\b(firefox|firefox)\b",
            normalized,
            re.IGNORECASE,
        )
        
        if chrome_calibration:
            canonical = self._normalize_action_name("calibrar_chrome")
            if canonical == "calibrar_chrome":
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

        # Evitar que una peticion especifica de navegador se interprete como
        # calibracion global.
        browser_specific = re.search(
            r"\b(chrome|edge|firefox)\b",
            normalized,
            re.IGNORECASE,
        )
        global_calibration = (
            re.search(r"\bcalibr(?:ar|a|e|aci\u00f3n|acion|ado|ada)\b.*\baplicacion(?:es)?\b", normalized)
            or re.search(r"\bcalibr(?:ar|a|e|aci\u00f3n|acion|ado|ada)\b.*\bprogramas?\b", normalized)
            or re.search(r"\bcalibr(?:ar|a|e|aci\u00f3n|acion)\b.*\btodo(?:s|as)?\b", normalized)
            or re.search(r"\bcalibr(?:ar|a|e|aci\u00f3n|acion)\b.*\bglobal\b", normalized)
        )

        if global_calibration and not browser_specific:
            canonical = self._normalize_action_name("calibrar_aplicaciones")
            if canonical == "calibrar_aplicaciones":
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
            logger.debug("Brain._get_system_context: %s", exc)
            return "{}"

    def _get_available_actions(self) -> List[Dict[str, Any]]:
        try:
            actions = self.action_registry.get_actions_for_llama()
            return list(actions) if actions else []
        except Exception as exc:
            logger.debug("Brain._get_available_actions: %s", exc)
            return []

    def _get_application_knowledge(self) -> Dict[str, Any]:
        try:
            app_integrator = get_application_knowledge_integrator()
            applications = {}
            for app_name in app_integrator.application_manager.applications.keys():
                capabilities = app_integrator.get_application_capabilities(app_name)
                applications[app_name] = {
                    "capabilities": capabilities,
                    "declared": app_integrator.is_application_capable(
                        app_name, ApplicationCapability.OPEN
                    ),
                    "available": app_integrator.is_application_available(app_name),
                    "capability_available": app_integrator.is_capability_available(
                        app_name, ApplicationCapability.OPEN
                    ),
                }
            return {
                "applications": applications,
                "total_applications": len(applications),
                "supported_capabilities": ["open", "navigate", "search", "play", "type", "click"],
            }
        except Exception as exc:
            logger.debug("Brain._get_application_knowledge: %s", exc)
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
            logger.debug("Brain._get_domain_entities: %s", exc)
            return []

    def _build_system_instruction(self, use_legacy_mode: bool = False) -> str:
        system_context = self._get_system_context()
        available_actions = self._get_available_actions()
        domain_entities = self._get_domain_entities()

        lines = [
            "Eres Jarvis, un asistente de IA.",
            "SOLO respondes en espa\u00f1ol.",
            "Cuando devuelvas una acci\u00f3n legacy, usa EXACTAMENTE el nombre que aparece en ACCIONES DISPONIBLES.",
            "No traduzcas ni inventes nombres de acciones.",
            "calibrar_aplicaciones = calibraci\u00f3n GLOBAL de las aplicaciones soportadas.",
            "calibrar_chrome = calibraci\u00f3n EXCLUSIVA de Google Chrome.",
            "Nunca uses calibrar_chrome para una petici\u00f3n general como 'calibrar aplicaciones'.",
            "Nunca uses calibrate_application_ui para una petici\u00f3n general: esa acci\u00f3n exige una aplicaci\u00f3n concreta.",
            "",
        ]

        if use_legacy_mode:
            lines.extend([
                "MODO COMPATIBILIDAD (acciones existentes):",
                "Cuando el usuario solicita una acci\u00f3n que puede realizar JARVIS,",
                "devuelve \u00daNICAMENTE un objeto JSON v\u00e1lido, sin Markdown ni texto adicional.",
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
                "MODO PLANIFICACI\u00d3N JER\u00c1RQUICA:",
                "Intenta interpretar la intenci\u00f3n y crear un objetivo del sistema.",
                "Si la petici\u00f3n es una acci\u00f3n concreta que ya existe, puedes usar el formato legacy.",
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
                '    "description": "Descripci\u00f3n del objetivo",',
                '    "priority": 1,',
                '    "constraints": []',
                "  }",
                "}",
                "",
                "FORMATO ACCI\u00d3N LEGACY (fallback):",
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
                raise ValueError("Ollama devolvio una respuesta sin message.content") from exc
            return str(content).strip() if content else ""
        except ollama.ResponseError as exc:
            logger.debug("Brain._chat_text: %s", exc)
            raise
        except Exception as exc:
            logger.debug("Brain._chat_text: %s", exc)
            raise

    def generate_response(self, prompt: str, use_legacy_mode: bool = False) -> str:
        if not prompt or not prompt.strip():
            return ""
        system_instruction = self._build_system_instruction(use_legacy_mode)
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt.strip()},
        ]
        logger.info("Enviando " + str(len(messages)) + " mensajes al modelo " + self.model)
        try:
            result = self._chat_text(messages, temperature=0.7, top_p=0.9, num_predict=500)
            return result
        except Exception as exc:
            logger.debug("Brain.generate_response: %s", exc)
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
            if goal_type == "navigate_stream" and target:
                return {"type": "legacy_action", "action": "navigate_to_url", "parameters": {"url": target}, "reasoning": f"Navegando a stream: {target}"}
            if goal_type == "navigate" and target:
                return {"type": "legacy_action", "action": "navigate_to_url", "parameters": {"url": target}, "reasoning": f"Navegando a: {target}"}
            if goal_type == "open_application":
                # Si existe una accion registrada especifica (p. ej. open_chrome ->
                # abrir_chrome) se conserva; en otro caso, la accion generica
                # registrada open_application, que usa el flujo unico de apertura.
                specific = f"open_{str(target).lower().replace(' ', '_')}"
                normalized = self._normalize_action_name(specific)
                if normalized and self.action_registry.get_action(normalized) is not None:
                    return {"type": "legacy_action", "action": specific, "parameters": {}, "reasoning": f"Abriendo aplicaci\u00f3n: {target}"}
                return {"type": "legacy_action", "action": "open_application", "parameters": {"app_name": str(target)}, "reasoning": f"Abriendo aplicaci\u00f3n: {target}"}
            return {"type": "error", "message": f"Objetivo '{goal_type}' a\u00fan no implementado en el sistema legacy", "goal_data": goal_dict}
        except Exception as exc:
            logger.debug("Brain.execute_goal: %s", exc)
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
                # 4.6.1: estado real disponible antes de entrar en HTN (antes {}).
                htn_state = self.capture_htn_state() if self.htn_integration else {}
                for goal in goals:
                    legacy = self.execute_goal(goal)
                    if self.htn_integration:
                        htn_result = self.htn_integration.process_goal_through_htn(goal, htn_state)
                        htn_results.append(htn_result)
                        # 4.6.2.1: el siguiente Goal parte del estado con los
                        # cambios confirmados por la ejecucion del anterior.
                        final_state = getattr(htn_result, "final_state", None)
                        if isinstance(final_state, dict):
                            htn_state = final_state
                        # El objetivo ya paso por HTN -> TaskExecutor -> accion
                        # registrada: el descriptor legado es solo informativo y
                        # no debe ejecutarse otra vez (sin doble ejecucion).
                        if isinstance(legacy, dict):
                            legacy = dict(legacy, execution_route="htn", executable=False)
                    results.append(legacy)
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
                return {"type": "legacy_execution", "action": intent_result["action"], "parameters": intent_result["parameters"], "reasoning": "Acci\u00f3n legacy lista para ejecuci\u00f3n"}
            return intent_result
        except Exception as exc:
            logger.debug("Brain.process_intent_to_execution: %s", exc)
            return {"type": "error", "message": f"Error en procesamiento: {exc}", "original_prompt": prompt}

    def process_with_htn(self, prompt: str) -> Dict[str, Any]:
        if not self.htn_integration:
            return {"type": "htn_error", "message": "Sistema HTN no disponible", "original_prompt": prompt}
        try:
            htn_result = self.htn_integration.create_and_execute_htn_goal(prompt, self.capture_htn_state())
            if htn_result.success:
                return {"type": "htn_success", "goal_id": htn_result.goal_id, "goal_type": htn_result.goal_type, "decomposed_tasks": htn_result.decomposed_tasks, "execution_results": htn_result.execution_results, "total_execution_time": htn_result.total_execution_time, "reasoning": "Objetivo procesado exitosamente con descomposici\u00f3n jer\u00e1rquica"}
            return {"type": "htn_failure", "goal_id": htn_result.goal_id, "goal_type": htn_result.goal_type, "error_message": htn_result.error_message, "reasoning": "Fallo en procesamiento con HTN"}
        except Exception as exc:
            logger.debug("Brain.process_with_htn: %s", exc)
            return {"type": "htn_error", "message": f"Error en procesamiento HTN: {exc}", "original_prompt": prompt}

    def get_htn_insights(self) -> Dict[str, Any]:
        if not self.htn_integration:
            return {"error": "Sistema HTN no disponible"}
        try:
            return self.htn_integration.get_htn_insights()
        except Exception as exc:
            logger.debug("Brain.get_htn_insights: %s", exc)
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
            logger.debug("Brain._extract_parameters_from_input: %s", exc)
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
            logger.debug("Brain.parse_model_response: %s", exc)
            return None
        if not isinstance(data, dict):
            logger.warning("[BRAIN] El JSON del modelo no contiene un objeto.")
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
            return resolved_entities
        except Exception as exc:
            logger.debug("Brain._extract_entities_from_input: %s", exc)
            return self._extract_entities_fallback(user_input)

    _FALLBACK_IGNORED_WORDS = frozenset({
        "abre", "abrir", "cierra", "cerrar", "busca", "buscar", "navega", "navegar",
        "pon", "poner", "quiero", "puedes", "favor", "pantalla", "monitor", "ahora",
    })

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
                    logger.debug("Brain._extract_entities_fallback: %s", exc)
            user_input_lower = user_input.lower()
            # Palabras con contenido (>= 4 letras, sin verbos de orden): antes
            # cualquier palabra ("de", "la", "abre") contenida en una URL o
            # propiedad hacia coincidir casi todas las entidades (4.5.2.1).
            keywords = [
                word for word in re.findall(r"\w+", user_input_lower)
                if len(word) >= 4 and word not in self._FALLBACK_IGNORED_WORDS
            ]
            name_matches: List[Entity] = []
            for entity in all_entities:
                entity_name_lower = entity.name.lower()
                if entity_name_lower == user_input_lower or entity_name_lower in user_input_lower or user_input_lower in entity_name_lower:
                    name_matches.append(entity)
                elif entity.properties and keywords:
                    properties_text = " ".join(str(v).lower() for v in entity.properties.values())
                    property_words = set(re.findall(r"\w+", properties_text))
                    if any(keyword in property_words for keyword in keywords):
                        entities.append(entity)
            # Las coincidencias por nombre van primero: la primera es la resuelta.
            entities = name_matches + entities
            unique_entities: Dict[str, Entity] = {}
            for entity in entities:
                unique_entities[entity.id] = entity
            return list(unique_entities.values())
        except Exception as exc:
            logger.debug("Brain._extract_entities_fallback: %s", exc)
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
                    description = f"Buscar informaci\u00f3n de {entity.name}"
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
                    description = f"Abrir aplicaci\u00f3n {entity.name}"
                elif any(word in input_lower for word in ["cerrar", "cierra", "terminar"]):
                    goal_type = "close_application"
                    target = entity.name
                    description = f"Cerrar aplicaci\u00f3n {entity.name}"
                else:
                    goal_type = "open_application"
                    target = entity.name
                    description = f"Abrir aplicaci\u00f3n {entity.name}"
            else:
                goal_type = "navigate"
                target = entity.properties.get("url", "")
                description = f"Realizar acci\u00f3n con {entity.name}"

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

            # 4.1.3.2: Goal desde entidad mediante el constructor validado; si no
            # cumple el contrato (p. ej. entidad sin URL) se conserva la
            # construccion legacy marcada con los errores (4.1.3.3).
            goal = build_goal(
                goal_type,
                target,
                description,
                priority=1,
                constraints=parameters.get("constraints", []),
                metadata=enhanced_metadata,
                source="entity",
                goal_id=new_goal_id(f"{goal_type}_{entity.id}"),
            )
            if goal is None:
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
                goal.metadata["source"] = "legacy_fallback"
                goal.metadata["validation_errors"] = validate_goal(goal)
            goal_id = goal.id

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
            return goal
        except Exception as exc:
            logger.debug("Brain._create_goal_from_entity: %s", exc)
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
            # Una entidad temporal/no resuelta no debe secuestrar una accion legacy.
            if resolution_result.resolution_method != "temporary_creation":
                entities = [resolution_result.entity]
                entities.extend(resolution_result.alternatives)
                resolution_results = [resolution_result]
        except Exception as exc:
            logger.debug("Brain.interpret_intent: %s", exc)
            entities = self._extract_entities_fallback(prompt)
            resolution_results = [None] * len(entities)
            logger.info("Procesando solicitud: " + str([e.name for e in entities]))

        if entities:
            # 4.5.2.3: una peticion -> un Goal con la entidad resuelta. Antes se
            # creaba un Goal por cada alternativa y process_intent_to_execution
            # los ejecutaba todos. Las alternativas quedan como dato para una
            # aclaracion (4.5.7), no como objetivos.
            goals: List[Goal] = []
            resolution_result = resolution_results[0] if resolution_results else None
            goal = self._create_goal_from_entity(entities[0], prompt, resolution_result)
            if goal:
                alternatives = [
                    {"id": getattr(e, "id", None), "name": getattr(e, "name", None), "type": getattr(e, "type", None)}
                    for e in entities[1:]
                    if getattr(e, "id", None) != getattr(entities[0], "id", None)
                ]
                if alternatives:
                    goal.metadata["entity_alternatives"] = alternatives
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
                        return {"type": "goal", "data": goal_data, "raw": raw_response, "goal": goal, "action": None}
                except Exception as exc:
                    logger.debug("Brain.interpret_intent: %s", exc)
            if "action" in parsed:
                canonical_action = self._normalize_action_name(parsed.get("action", ""))
                if canonical_action:
                    parsed["action"] = canonical_action
                return {"type": "action", "data": parsed, "raw": raw_response, "goal": None, "action": parsed}

        logger.info("[INTERPRET] Usando modo legacy como fallback")
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
                return None
            constraints = goal_data.get("constraints", [])
            # 4.1.3.1: Goal desde la intencion estructurada del LLM mediante el
            # constructor validado (ID sin espacios y unico); fallback legacy si
            # no cumple el contrato (4.1.3.3).
            goal = build_goal(
                goal_type,
                target,
                description,
                priority=goal_data.get("priority", 1),
                constraints=constraints if isinstance(constraints, list) else [constraints],
                source="intent",
            )
            if goal is None:
                goal = Goal(
                    id=f"{goal_type}_{target}_{int(time.time())}",
                    type=goal_type,
                    target=target,
                    description=description,
                    priority=goal_data.get("priority", 1),
                    constraints=constraints,
                    created_at=time.time(),
                )
                goal.metadata["source"] = "legacy_fallback"
                goal.metadata["validation_errors"] = validate_goal(goal)
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
            logger.debug("Brain._create_system_goal: %s", exc)
            return None

    def _voice_understanding_step(self, prompt: str):
        """
        Devuelve ``(respuesta, texto)``: si hay que preguntar al usuario,
        ``respuesta`` es la pregunta; si no, ``texto`` es la frase con la que
        seguir (corregida o reanudada tras una aclaracion). Desactivado o con
        error, devuelve ``(None, prompt)`` sin cambiar nada.
        """
        understanding = getattr(self, "_voice_understanding", None)
        if understanding is None:
            try:
                from src.brain.voice_understanding import get_voice_understanding

                understanding = get_voice_understanding(llm_model=getattr(self, "model", None))
            except Exception as exc:
                logger.warning("Comprension de voz no disponible: %s", exc)
                understanding = False
            self._voice_understanding = understanding
        if not understanding or not understanding.enabled:
            return None, prompt
        try:
            answer = understanding.handle_answer(prompt)
            if answer is not None:
                return (answer.reply, prompt) if answer.reply else (None, answer.text or prompt)
            from src.ear.transcription import get_last_transcription

            result = understanding.process(prompt, get_last_transcription())
            if result.reply:
                return result.reply, prompt
            return None, (result.text or prompt)
        except Exception as exc:
            logger.warning("Comprension de voz fallida; se usa el texto original: %s", exc)
            return None, prompt

    def think(self, prompt: str, use_legacy_execution: bool = False) -> str:
        if not prompt or not prompt.strip():
            return "No recib\u00ed ning\u00fan mensaje."

        # 4.5.6.12: comprension robusta de la frase (una sola vez) antes de
        # interpretar la intencion; puede devolver una pregunta (4.5.7).
        voice_reply, prompt = self._voice_understanding_step(prompt)
        if voice_reply:
            return voice_reply

        interpretation = self.interpret_intent(prompt)
        if interpretation["type"] == "goal":
            goal = interpretation["goal"]
            if isinstance(goal, list):
                goal = goal[0]
            self.memory_manager.add_conversational_memory(
                message=prompt,
                response=f"Objetivo creado: {goal.description}",
                intent=goal.type,
                entities=[goal.target] if goal.target else [],
            )
            open_command = self._open_application_command(goal)
            if open_command:
                # Abrir una aplicacion usa la misma accion registrada que el
                # ejecutor de main.py (sin ruta paralela).
                return open_command
            return f"Objetivo registrado: {goal.description}. El sistema lo procesar\u00e1 pr\u00f3ximamente."

        if interpretation["type"] == "action":
            action_data = interpretation["action"]
            action_name = self._normalize_action_name(action_data.get("action", ""))
            parameters = action_data.get("parameters", {}) or {}

            if not action_name:
                return "No entend\u00ed la acci\u00f3n solicitada."

            if use_legacy_execution:
                result = self._execute_legacy_action(action_name, parameters)
                self.memory_manager.add_conversational_memory(
                    message=prompt,
                    response=f"Acci\u00f3n ejecutada: {action_name}",
                    intent="legacy_action",
                    entities=[],
                )
                return f"\u2705 {result}"

            # Devolver un comando ejecutable por la fachada Executor de main.py.
            return f"[CMD: {action_name}]"

        return "No entend\u00ed tu solicitud. \u00bfPodr\u00edas repetirla de otra manera?"

    _SAFE_CMD_ARGUMENT = re.compile(r"^[A-Za-z0-9 ._+\-\u00c0-\u024f]{1,80}$")

    def _open_application_command(self, goal: Any) -> Optional[str]:
        """``[CMD: open_application(<nombre>)]`` para objetivos de apertura.

        Solo si el objetivo es ``open_application`` y el nombre es un argumento
        simple que el parser ``[CMD:...]`` del ejecutor no puede malinterpretar.
        La resolucion, el preflight y el lanzamiento los hace la accion
        registrada ``open_application``.
        """
        if str(getattr(goal, "type", "") or "") != "open_application":
            return None
        target = getattr(goal, "target", None)
        if not isinstance(target, str):
            return None
        name = target.strip()
        if not name or not self._SAFE_CMD_ARGUMENT.match(name):
            return None
        return f"[CMD: open_application({name})]"

    def _execute_legacy_action(self, action_name: str, parameters: Dict[str, Any]) -> str:
        try:
            action_name = self._normalize_action_name(action_name)
            is_valid = self.action_registry.validate_action(action_name, parameters)
            if not is_valid:
                return f"\u274c Acci\u00f3n no v\u00e1lida: {action_name}"
            result = self.action_registry.execute_action(action_name, parameters)
            return f"\u2705 Acci\u00f3n ejecutada: {action_name}. Resultado: {result}"
        except Exception as exc:
            logger.debug("Brain._execute_legacy_action: %s", exc)
            return f"\u274c Error ejecutando {action_name}: {exc}"

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
                return f"\u274c Par\u00e1metros incorrectos para la acci\u00f3n: {action_name}"
            return self._execute_legacy_action(action_name.strip(), parameters)
        except Exception as exc:
            logger.debug("Brain.process_action_response: %s", exc)
            return llm_response

    def think_with_image(self, prompt: str, image_path: str) -> str:
        if not prompt or not prompt.strip():
            return "No recib\u00ed instrucciones para la imagen."
        if not image_path:
            return "No se proporcion\u00f3 ninguna imagen."
        try:
            return self._perception_only(self._chat_text(
                [{"role": "user", "content": prompt.strip(), "images": [image_path]}],
                temperature=0.1,
                top_p=0.9,
                num_predict=20,
                stop=["\n"],
                repeat_penalty=1.2,
            ))
        except Exception as exc:
            logger.warning("Brain.think_with_image: %s", exc)
            return f"ERROR: {exc}"

    @staticmethod
    def _perception_only(text: str) -> str:
        """
        4.5.4.3: la salida de vision es percepcion, no una decision. Si el
        modelo devuelve un comando ``[CMD: ...]`` se neutraliza para que
        ``Executor.process_and_execute`` nunca lo ejecute; las acciones solo
        salen de la interpretacion de la orden del usuario.
        """
        value = str(text or "")
        if re.search(r"\[\s*CMD\s*:", value, re.IGNORECASE):
            logger.warning("Salida de vision con comando neutralizada: %s", value[:120])
            value = re.sub(r"\[\s*CMD\s*:", "(cmd:", value, flags=re.IGNORECASE)
        return value

    def analyze_image(self, image_path: str, analysis_prompt: str) -> str:
        if not image_path:
            return "No se proporcion\u00f3 imagen"
        if not analysis_prompt or not analysis_prompt.strip():
            return "No se proporcionaron instrucciones para el an\u00e1lisis."
        try:
            result = self._chat_text(
                [{"role": "user", "content": analysis_prompt.strip(), "images": [image_path]}],
                temperature=0.1,
                top_p=0.9,
                num_predict=500,
                stop=["\n\n", "User:", "Assistant:"],
                repeat_penalty=1.1,
            )
            logger.info("[+] Analisis de imagen completado")
            return self._perception_only(result)
        except Exception as exc:
            logger.warning("Brain.analyze_image: %s", exc)
            return f"ERROR: {exc}"

    def clear_memory(self) -> None:
        logger.info("Limpiando memoria del cerebro")
        try:
            self.memory_manager.clear_memory()
            logger.info("[+] Memoria limpia exitosamente")
        except Exception as exc:
            logger.debug("Brain.clear_memory: %s", exc)

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        try:
            memories = self.memory_manager.get_conversational_memory()
            return [m.to_dict() if hasattr(m, "to_dict") else m for m in memories]
        except Exception as exc:
            logger.debug("Brain.get_conversation_history: %s", exc)
            return []

    def get_available_actions(self) -> List[Dict[str, Any]]:
        return self._get_available_actions()

    def get_current_goals(self) -> List[Goal]:
        return []

    def capture_htn_state(self) -> Dict[str, Any]:
        """
        Instantanea del estado real disponible antes de entrar en HTN (4.6.1).

        La fuente es el WorldState de la memoria (``get_system_state``), que es
        el estado que Brain conoce; se copia para que HTN no mute el original.
        Se anotan la fuente, el momento de captura y la marca temporal del
        WorldState (4.6.1.2) con claves ``_htn_*`` que no son precondiciones
        ni se aplican al estado del Executor. Si no se puede leer, se devuelve
        un estado vacio marcado como ``unavailable``; nunca se inventan datos.
        """
        captured_at = time.time()
        try:
            state = self.get_system_state()
        except Exception as exc:
            logger.warning("Brain.capture_htn_state: estado no disponible: %s", exc)
            return {
                "_htn_state_source": "unavailable",
                "_htn_state_error": str(exc),
                "_htn_captured_at": captured_at,
            }
        if not isinstance(state, dict):
            logger.warning("Brain.capture_htn_state: estado no es un dict (%s)", type(state).__name__)
            state = {}
        try:
            snapshot = copy.deepcopy(state)
        except Exception as exc:
            logger.warning("Brain.capture_htn_state: copia superficial del estado: %s", exc)
            snapshot = dict(state)
        snapshot["_htn_state_source"] = "memory_world_state" if state else "empty"
        snapshot["_htn_captured_at"] = captured_at
        snapshot["_htn_state_timestamp"] = state.get("timestamp")
        return snapshot

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
        except Exception as exc:
            logger.debug("Brain.register_node: %s", exc)

    def register_task(self, task_config: Dict[str, Any]) -> None:
        pass


def get_jarvis_context():
    try:
        return get_jarvis_system_context()
    except Exception:
        return {}
