"""

Ejecutor mejorado de JARVIS con arquitectura de planificación jerárquica.

Responsabilidades mejoradas:

- Ejecutar acciones individuales con verificación de precondiciones y efectos

- Ejecutar planes completos (listas de nodos)

- Manejar estado del mundo y actualizaciones

- Soportar replanificación cuando una acción falla

- Integrarse con el sistema de nodos y objetivos

- Mantener compatibilidad con acciones legacy

El Executor ahora es el corazón del sistema de ejecución que:

1. Recibe un plan (lista de nodos)

2. Ejecuta nodo por nodo

3. Verifica resultados y actualiza estado

4. Si falla, intenta replanificación o alternativa

5. Devuelve el resultado completo de la ejecución

"""

from __future__ import annotations

import ast
import copy
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.hands import applications_core as applications

from src.hands import keyboard, mouse

from src.hands.action_registry import ActionInfo, ActionRegistry, get_action_registry

from src.hands.planner.node import Goal
from src.utils.config import get_predictive_config, get_timeout_config

from src.utils.logger import get_logger

from src.memory.storage import get_memory_manager

logger = get_logger(__name__)

def _log(level: str, message: Any, *_context: Any) -> None:
    """Compatibilidad con llamadas antiguas al logger que incluían metadatos de línea."""
    text = str(message)
    text = re.sub(r"\s*\[file:executor\.py,\s*method:.*?\]", "", text)
    if text.strip() == "Procesando solicitud":
        return
    method = getattr(logger, str(level).lower(), logger.info)
    try:
        method("%s", text)
    except Exception:
        # El logging nunca debe interrumpir la ejecución de una acción.
        pass

try:
    from src.hands.planner.learning_system import get_learning_system
    LEARNING_AVAILABLE = True
except ImportError:
    get_learning_system = None
    LEARNING_AVAILABLE = False
    logger.warning("Sistema de aprendizaje no disponible; FASE 18 parcialmente deshabilitada")

class ExecutionStatus(Enum):

    """Estados de ejecución de un nodo o plan."""

    PENDING = "pending"

    RUNNING = "running"

    SUCCESS = "success"

    FAILED = "failed"

    RETRYING = "retrying"

    ALTERNATIVE = "alternative"

@dataclass
class ExecutionResult:
    """Resultado de ejecución de un nodo o plan."""
    status: ExecutionStatus
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    node_id: Optional[str] = None
    plan_id: Optional[str] = None
    retries: int = 0
    alternatives_tried: List[str] = field(default_factory=list)
    last_actions: List[str] = field(default_factory=list)
    successful_nodes: List[str] = field(default_factory=list)
    failed_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Permite que los adaptadores legacy respeten el estado real del resultado."""
        return self.status == ExecutionStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "result": copy.deepcopy(self.result),
            "error": self.error,
            "execution_time": self.execution_time,
            "node_id": self.node_id,
            "plan_id": self.plan_id,
            "retries": self.retries,
            "alternatives_tried": list(self.alternatives_tried),
            "last_actions": list(self.last_actions),
            "successful_nodes": list(self.successful_nodes),
            "failed_nodes": copy.deepcopy(self.failed_nodes),
        }

@dataclass
class ExecutionState:
    """Estado actual del mundo para ejecución."""
    timestamp: float
    application_states: Dict[str, Dict[str, Any]]
    ui_elements: Dict[str, Dict[str, Any]]
    available_actions: List[str]
    last_actions: List[str]
    constraints: List[str]

    def update(self, update_data: Dict[str, Any]) -> None:
        """Actualiza el estado y fusiona los diccionarios anidados."""
        if not isinstance(update_data, dict):
            raise TypeError("update_data debe ser un diccionario")
        for key, value in update_data.items():
            if key.startswith("_") or key == "timestamp":
                continue
            current = self.__dict__.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                current.update(copy.deepcopy(value))
            elif isinstance(current, list) and isinstance(value, list):
                setattr(self, key, copy.deepcopy(value))
            else:
                self.__dict__[key] = copy.deepcopy(value)
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve una instantánea independiente del estado, incluidos campos extendidos."""
        return copy.deepcopy(self.__dict__)

class Executor:

    """Ejecutor mejorado con soporte para planificación jerárquica y replanificación."""

    _COMMAND_PATTERN = re.compile(
        r"\[CMD:\s*([a-zA-Z0-9_]+)(?:\((.*?)\))?\]",
        flags=re.DOTALL,
    )

    def __init__(self, action_registry: Optional[ActionRegistry] = None):
        """Inicializa el ejecutor sin importar Planner durante la carga del módulo."""
        self.action_registry = action_registry or get_action_registry()
        self.memory_manager = get_memory_manager()
        self.modules = {"apps": applications, "key": keyboard, "mouse": mouse}
        self.timeout_config = get_timeout_config()
        self.predictive_config = get_predictive_config()
        self.last_predictions: List[Dict[str, Any]] = []
        self.current_state = self._initialize_state()
        self.active_executions: Dict[str, ExecutionResult] = {}
        self._execution_lock = threading.RLock()

        try:
            # Importación diferida para romper el ciclo Executor <-> Planner.
            from src.hands.planner.planner import Planner
            self.planner = Planner(self)
        except Exception as exc:
            self.planner = None
            logger.warning("[EXECUTOR] Planner no disponible durante la inicialización: %s", exc)

        self.learning_system = get_learning_system() if LEARNING_AVAILABLE and callable(get_learning_system) else None
        _log("info", "Ejecutor mejorado inicializado")
        try:
            logger.info("[EXECUTOR] Total de %s acciones disponibles", len(self.action_registry.list_actions()))
        except Exception:
            logger.info("[EXECUTOR] Ejecutor inicializado")
        if self.learning_system is not None:
            logger.info("[EXECUTOR] Sistema de aprendizaje FASE 18 habilitado")

    def _initialize_state(self) -> ExecutionState:

        """Inicializa el estado del mundo."""

        return ExecutionState(

            timestamp=time.time(),

            application_states={},

            ui_elements={},

            available_actions=list(self.action_registry.list_actions()),

            last_actions=[],

            constraints=[]

        )

    # ========================================================================

    # EJECUCIÓN DE PLANES COMPLETOS (FASE 7-9)

    # ========================================================================

    def execute_plan(
        self,
        plan: List[Dict[str, Any]],
        plan_id: Optional[str] = None,
        max_retries: int = 3,
        timeout_per_node: Optional[float] = None,
    ) -> ExecutionResult:
        """Ejecuta un plan de forma secuencial; no declara éxito ante un fallo."""
        with self._execution_lock:
            return self._execute_plan_serial(plan, plan_id, max_retries, timeout_per_node)

    def _execute_plan_serial(
        self,
        plan: List[Dict[str, Any]],
        plan_id: Optional[str],
        max_retries: int,
        timeout_per_node: Optional[float],
    ) -> ExecutionResult:
        started = time.perf_counter()
        if not isinstance(plan, list) or not plan:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Plan vacío o con formato no válido",
                plan_id=plan_id,
                execution_time=0.0,
            )

        effective_plan_id = plan_id or f"plan_{int(time.time() * 1000)}"
        result = ExecutionResult(status=ExecutionStatus.PENDING, plan_id=effective_plan_id)
        self.active_executions[effective_plan_id] = result
        logger.info("[EXECUTOR] Ejecutando plan %s con %s pasos", effective_plan_id, len(plan))
        try:
            for index, raw_node in enumerate(plan):
                node = self._normalize_plan_node(raw_node, index)
                if node is None:
                    result.status = ExecutionStatus.FAILED
                    result.error = f"Nodo {index} no válido"
                    result.failed_nodes.append({"id": f"node_{index}", "error": result.error})
                    break

                node_id = str(node.get("id") or node.get("action") or f"node_{index}")
                node_result = self._execute_node(node, node_id, max(0, int(max_retries)), timeout_per_node)
                result.execution_time += max(0.0, node_result.execution_time)

                if node_result.status != ExecutionStatus.SUCCESS:
                    alternative_result = self._try_alternative(node, node_result)
                    if alternative_result.status == ExecutionStatus.SUCCESS:
                        node_result = alternative_result
                        result.execution_time += max(0.0, alternative_result.execution_time)
                        result.alternatives_tried.extend(alternative_result.alternatives_tried or [alternative_result.node_id or "unknown"])
                    else:
                        result.status = ExecutionStatus.FAILED
                        result.error = f"Nodo {node_id} falló sin alternativa válida: {node_result.error or 'error desconocido'}"
                        result.result = node_result.to_dict()
                        result.failed_nodes.append({"id": node_id, "error": node_result.error or result.error})
                        break

                self._update_world_state(node, node_result)
                result.last_actions.append(node_result.node_id or node_id)
                result.successful_nodes.append(node_result.node_id or node_id)

            if result.status == ExecutionStatus.PENDING:
                result.status = ExecutionStatus.SUCCESS
                result.result = {"message": "Plan ejecutado correctamente", "world_state": self._get_state_for_planning()}
            result.execution_time = max(result.execution_time, time.perf_counter() - started)
            return result
        except Exception as exc:
            result.status = ExecutionStatus.FAILED
            result.error = f"Error ejecutando plan: {exc}"
            result.execution_time = max(result.execution_time, time.perf_counter() - started)
            logger.exception("[EXECUTOR] Fallo no controlado durante el plan %s", effective_plan_id)
            return result
        finally:
            result.execution_time = max(result.execution_time, time.perf_counter() - started)
            if self.learning_system is not None and result.status != ExecutionStatus.PENDING:
                try:
                    plan_ids = [
                        str(item.get("id", item.get("action", ""))) if isinstance(item, dict)
                        else str(getattr(item, "id", ""))
                        for item in plan
                    ]
                    total_cost = sum(
                        self._safe_cost(item.get("cost", 1.0) if isinstance(item, dict) else getattr(item, "cost", 1.0))
                        for item in plan
                    )
                    self.learning_system.record_plan_execution(
                        plan_id=effective_plan_id,
                        goal_id="unknown",
                        plan=plan_ids,
                        success=result.status == ExecutionStatus.SUCCESS,
                        execution_time=result.execution_time,
                        total_estimated_cost=total_cost,
                        context={
                            "successful_nodes": list(result.successful_nodes),
                            "failed_nodes": copy.deepcopy(result.failed_nodes),
                            "alternatives_tried": list(result.alternatives_tried),
                        },
                    )
                except Exception:
                    logger.exception("[EXECUTOR] No se pudo registrar el resultado del plan %s", effective_plan_id)
            self.active_executions.pop(effective_plan_id, None)

    @staticmethod
    def _normalize_plan_node(raw_node: Any, index: int) -> Optional[Dict[str, Any]]:
        if isinstance(raw_node, dict):
            node = copy.deepcopy(raw_node)
        elif hasattr(raw_node, "id"):
            node = {
                "id": getattr(raw_node, "id", f"node_{index}"),
                "name": getattr(raw_node, "name", ""),
                "action": getattr(raw_node, "action", None) or getattr(raw_node, "id", None),
                "description": getattr(raw_node, "description", ""),
                "type": getattr(raw_node, "type", None),
                "parameters": copy.deepcopy(getattr(raw_node, "parameters", {}) or {}),
                "preconditions": copy.deepcopy(getattr(raw_node, "preconditions", []) or []),
                "effects": copy.deepcopy(getattr(raw_node, "effects", []) or []),
                "cost": getattr(raw_node, "cost", 1.0),
                "application": getattr(raw_node, "application", None),
                "ui_element": getattr(raw_node, "ui_element", None),
                "metadata": copy.deepcopy(getattr(raw_node, "metadata", {}) or {}),
            }
        else:
            return None
        node.setdefault("id", node.get("action") or f"node_{index}")
        node.setdefault("parameters", {})
        node.setdefault("preconditions", [])
        node.setdefault("effects", [])
        node.setdefault("alternatives", [])
        if not isinstance(node["parameters"], dict):
            return None
        if not isinstance(node["preconditions"], (list, tuple)):
            return None
        if not isinstance(node["effects"], (list, tuple)):
            return None
        node["preconditions"] = list(node["preconditions"])
        node["effects"] = list(node["effects"])
        return node

    def _execute_node(
        self,
        node: Dict[str, Any],
        node_id: str,
        max_retries: int,
        timeout: Optional[float],
    ) -> ExecutionResult:
        """Ejecuta un paso y solo reintenta cuando se declara seguro."""
        started = time.perf_counter()
        result = ExecutionResult(status=ExecutionStatus.PENDING, node_id=node_id)
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        retry_safe = bool(node.get("retry_safe", metadata.get("retry_safe", metadata.get("idempotent", False))))
        attempts_allowed = max(0, int(max_retries)) if retry_safe else 0

        for attempt in range(attempts_allowed + 1):
            result.retries = attempt
            if attempt:
                result.status = ExecutionStatus.RETRYING
                logger.warning("[EXECUTOR] Reintento seguro %s/%s para %s", attempt, attempts_allowed, node_id)
                time.sleep(min(1.0, 0.25 * attempt))

            if not self._check_node_preconditions(node):
                result.status = ExecutionStatus.FAILED
                result.error = "Precondiciones no satisfechas"
                break

            try:
                result.status = ExecutionStatus.RUNNING
                raw_result = self._execute_node_action(node, timeout)
                if raw_result is None:
                    result.status = ExecutionStatus.FAILED
                    result.error = "La ejecución devolvió None"
                    break
                if self._verify_node_success(node, raw_result):
                    result.status = ExecutionStatus.SUCCESS
                    result.result = raw_result
                    result.error = None
                    break
                result.status = ExecutionStatus.FAILED
                result.result = raw_result
                result.error = "La verificación del resultado falló"
                # Una acción pudo producir efectos aunque la verificación falle.
                break
            except Exception as exc:
                result.status = ExecutionStatus.FAILED
                result.error = str(exc)
                logger.warning("[EXECUTOR] Fallo en el nodo %s: %s", node_id, exc)
                # A timed-out physical action has an uncertain outcome and is never retried here.
                if isinstance(exc, TimeoutError) or attempt >= attempts_allowed:
                    break

        result.execution_time = max(0.0, time.perf_counter() - started)
        if self.learning_system is not None:
            try:
                self.learning_system.record_node_execution(
                    node_id=node_id,
                    success=result.status == ExecutionStatus.SUCCESS,
                    execution_time=result.execution_time,
                    estimated_cost=self._safe_cost(node.get("cost", 1.0)),
                    context={"attempts": result.retries + 1, "alternatives_tried": list(result.alternatives_tried)},
                    application=node.get("application"),
                )
            except Exception:
                logger.exception("[EXECUTOR] No se pudo registrar el aprendizaje del nodo %s", node_id)
        return result

    @staticmethod
    def _safe_cost(value: Any, default: float = 1.0) -> float:
        try:
            number = float(value)
            return max(0.0, number) if math.isfinite(number) else default
        except (TypeError, ValueError):
            return default

    def _verify_node_success(self, node: Dict[str, Any], result: Any) -> bool:
        """Verifica confirmaciones explícitas sin confundir el estado previo con el posterior."""
        checker = node.get("success_checker")
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        checker = checker or metadata.get("success_checker")
        if callable(checker):
            try:
                return bool(checker(result))
            except Exception:
                logger.exception("[EXECUTOR] El verificador personalizado falló para %s", node.get("id"))
                return False

        if result is None or result is False:
            return False
        if isinstance(result, dict):
            if result.get("error") or result.get("error_message"):
                return False
            if "success" in result:
                return result["success"] is True or result["success"] == 1
            status = result.get("status")
            status = getattr(status, "value", status)
            if status is not None:
                return str(status).lower() in {"success", "completed", "ok"}
            # execute_action ya ejecuta ActionInfo.verify_success antes de retornar.
            return True
        if isinstance(result, bool):
            return result
        status = getattr(result, "status", None)
        status = getattr(status, "value", status)
        if status is not None:
            return str(status).lower() in {"success", "completed", "ok"}
        explicit_success = getattr(result, "success", None)
        if explicit_success is not None:
            return explicit_success is True or explicit_success == 1
        return True

    def _replan_after_failure(
        self,
        plan: List[Dict[str, Any]],
        failed_node_index: int,
        current_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Construye un plan alternativo sin tocar el plan original."""
        if failed_node_index < 0 or failed_node_index >= len(plan):
            logger.error("[EXECUTOR] Índice de nodo fallido fuera de rango: %s", failed_node_index)
            return plan

        failed_node = plan[failed_node_index]
        candidates: List[Dict[str, Any]] = []
        for alternative in failed_node.get("alternatives", []) or []:
            if isinstance(alternative, dict):
                candidate = copy.deepcopy(alternative)
                candidate.setdefault("parameters", copy.deepcopy(failed_node.get("parameters", {}) or {}))
                candidate.setdefault("preconditions", copy.deepcopy(failed_node.get("preconditions", []) or []))
                candidate.setdefault("effects", copy.deepcopy(failed_node.get("effects", []) or []))
                candidate.setdefault("application", failed_node.get("application"))
                candidate.setdefault("ui_element", failed_node.get("ui_element"))
                candidates.append(candidate)
            elif isinstance(alternative, str) and alternative.strip():
                candidates.append({
                    "id": f"alternative_{alternative.strip()}",
                    "action": alternative.strip(),
                    "parameters": copy.deepcopy(failed_node.get("parameters", {}) or {}),
                    "preconditions": copy.deepcopy(failed_node.get("preconditions", []) or []),
                    "effects": copy.deepcopy(failed_node.get("effects", []) or []),
                    "application": failed_node.get("application"),
                    "ui_element": failed_node.get("ui_element"),
                    "cost": self._safe_cost(failed_node.get("cost", 1.0)) * 0.9,
                    "alternatives": [],
                })

        if not candidates:
            candidates = self._find_alternative_nodes(failed_node, current_state)
        if not candidates:
            logger.warning("[EXECUTOR] No se encontró alternativa para %s", failed_node.get("id"))
            return plan

        new_plan = copy.deepcopy(plan)
        new_plan[failed_node_index] = candidates[0]
        if self.learning_system is not None:
            try:
                self.learning_system.record_replanification(
                    original_plan=[str(item.get("id", "")) for item in plan],
                    new_plan=[str(item.get("id", item.get("action", ""))) for item in new_plan],
                    reason=f"failed_node_{failed_node.get('id', failed_node_index)}",
                    success=True,
                    execution_time=0.0,
                )
            except Exception:
                logger.exception("[EXECUTOR] No se pudo registrar la replanificación")
        return new_plan

    def _find_alternative_nodes(self, failed_node: Dict[str, Any], current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Encuentra hasta tres acciones registradas que ofrezcan capacidad compatible."""
        action_name = str(failed_node.get("action") or failed_node.get("id") or "")
        capability = self._extract_capability_from_action(action_name)
        try:
            getter = getattr(self.action_registry, "get_all_actions", None)
            available_actions = getter() if callable(getter) else None
            if not isinstance(available_actions, dict):
                names = self.action_registry.list_actions()
                available_actions = {name: self.action_registry.get_action(name) for name in names}
        except Exception as exc:
            logger.warning("[EXECUTOR] No se pudieron enumerar acciones alternativas: %s", exc)
            return []

        alternatives: List[Dict[str, Any]] = []
        for candidate_name, action_info in available_actions.items():
            if not candidate_name or candidate_name == action_name or action_info is None:
                continue
            try:
                matches = getattr(action_info, "matches_preconditions", None)
                if callable(matches) and not matches(current_state):
                    continue
                if not self._action_provides_capability(action_info, capability):
                    continue
                parameters = copy.deepcopy(failed_node.get("parameters", {}) or {})
                alternatives.append({
                    "id": f"alt_{candidate_name}",
                    "name": getattr(action_info, "description", candidate_name),
                    "action": candidate_name,
                    "parameters": parameters,
                    "preconditions": copy.deepcopy(getattr(action_info, "preconditions", []) or []),
                    "effects": copy.deepcopy(getattr(action_info, "effects", []) or []),
                    "cost": self._safe_cost(getattr(action_info, "cost", 1.0)) * 0.9,
                    "application": getattr(action_info, "application", None),
                    "ui_element": getattr(action_info, "requires_ui_element", None),
                    "alternatives": [],
                })
            except Exception:
                logger.debug("[EXECUTOR] Se omitió una posible alternativa %s", candidate_name, exc_info=True)
        return alternatives[:3]

    def _extract_capability_from_action(self, action_name: str) -> str:

        """Extrae la capacidad principal de un nombre de acción."""

        capability_mapping = {

            "focus_address_bar": "focus_element",

            "click_address_bar": "focus_element",

            "hotkey_ctrl_l": "focus_element",

            "type_url": "type_text",

            "press_enter": "press_key",

            "open_chrome": "open_application",

            "activate_chrome": "activate_window",

            "minimize_chrome": "minimize_window"

        }

        return capability_mapping.get(action_name, action_name)

    def _action_provides_capability(self, action_info: ActionInfo, capability: str) -> bool:
        """Comprueba compatibilidad por nombre, tipo, categoría o capacidad declarada."""
        capability = str(capability or "").strip().lower()
        if not capability:
            return False
        name = str(getattr(action_info, "name", "") or "").lower()
        action_type = getattr(action_info, "action_type", None)
        action_type = str(getattr(action_type, "value", action_type) or "").lower()
        category = str(getattr(action_info, "category", "") or "").lower()
        declared_capability = str(getattr(action_info, "capability", None) or "").strip().lower()
        return (
            capability in name
            or capability == action_type
            or capability in category
            or capability == declared_capability
        )

    def _should_replan(self, plan: List[Dict[str, Any]], failed_node_index: int) -> bool:

        """Determina si se debe replanificar después de un fallo."""

        if failed_node_index >= len(plan):

            return False

        failed_node = plan[failed_node_index]

        # Si el nodo tiene alternativas definidas, replanificar

        if failed_node.get("alternatives"):

            return True

        # Si el nodo es crítico (alta prioridad o sin alternativas), no replanificar

        cost = failed_node.get("cost", 1.0)

        if cost > 5.0:  # Nodos caros son más críticos

            return False

        # Replanificar para nodos de bajo coste que tienen alternativas

        return cost <= 3.0

    def execute_plan_with_replan(
        self,
        plan: List[Dict[str, Any]],
        goal: Optional[Dict[str, Any]] = None,
        max_replan_attempts: int = 2,
    ) -> Dict[str, Any]:
        """Ejecuta un plan con replanificación local y registro del resultado real."""
        started = time.perf_counter()
        if not isinstance(plan, list) or not plan:
            return {"status": "failed", "success": False, "error": "Plan vacío", "execution_time": 0.0, "replan_attempts": 0}

        active_plan: List[Dict[str, Any]] = []
        for index, raw_node in enumerate(plan):
            normalized = self._normalize_plan_node(raw_node, index)
            if normalized is None:
                return {"status": "failed", "success": False, "error": f"Nodo {index} no válido", "execution_time": 0.0, "replan_attempts": 0}
            active_plan.append(normalized)

        successful_nodes: List[str] = []
        failed_nodes: List[Dict[str, Any]] = []
        replan_attempts = 0
        index = 0
        goal_achieved = False

        while index < len(active_plan):
            current_state = self._get_state_for_planning()
            if goal is not None and self._goal_achieved(goal, current_state):
                goal_achieved = True
                break

            node = active_plan[index]
            node_id = str(node.get("id") or node.get("action") or f"node_{index}")
            node_result = self._execute_node(node, node_id, max_retries=0, timeout=30.0)
            if node_result.status == ExecutionStatus.SUCCESS:
                self._update_world_state(node, node_result)
                successful_nodes.append(node_result.node_id or node_id)
                index += 1
                if goal is not None and self._goal_achieved(goal, self._get_state_for_planning()):
                    goal_achieved = True
                    break
                continue

            failed_nodes.append({"id": node_id, "error": node_result.error})
            self._update_world_state_after_failure(node, node_result)
            if replan_attempts >= max(0, int(max_replan_attempts)) or not self._should_replan(active_plan, index):
                break

            new_plan = self._replan_after_failure(active_plan, index, self._get_state_for_planning())
            if new_plan == active_plan:
                break
            # Keep already completed prefix unchanged; only replace current/future steps.
            active_plan = copy.deepcopy(active_plan[:index]) + copy.deepcopy(new_plan[index:])
            replan_attempts += 1
            # Same index: execute the replacement, rather than skipping it via a for-loop.

        success = goal_achieved or index >= len(active_plan)
        elapsed = max(0.0, time.perf_counter() - started)
        if self.learning_system is not None:
            try:
                goal_id = getattr(goal, "id", None) if goal is not None else None
                if isinstance(goal, dict):
                    goal_id = goal.get("id", goal_id)
                self.learning_system.record_plan_execution(
                    plan_id=f"plan_{int(started * 1000)}",
                    goal_id=str(goal_id or "unknown"),
                    plan=[str(item.get("id", item.get("action", ""))) for item in active_plan],
                    success=success,
                    execution_time=elapsed,
                    total_estimated_cost=sum(self._safe_cost(item.get("cost", 1.0)) for item in active_plan),
                    context={"successful_nodes": successful_nodes, "failed_nodes": failed_nodes, "replan_attempts": replan_attempts, "goal_achieved": goal_achieved},
                )
            except Exception:
                logger.exception("[EXECUTOR] No se pudo registrar la ejecución del plan")

        return {
            "status": "success" if success else "failed",
            "success": success,
            "successful_nodes": successful_nodes,
            "failed_nodes": failed_nodes,
            "execution_time": elapsed,
            "replan_attempts": replan_attempts,
            "total_nodes": len(active_plan),
            "goal_achieved": goal_achieved,
            "world_state": self._get_state_for_planning(),
        }

    def _update_world_state_after_failure(self, node: Dict[str, Any], result: ExecutionResult) -> None:
        """Registra el fallo y su timestamp sin alterar estados de éxito."""
        application = str(node.get("application") or "").strip()
        if application:
            self.current_state.application_states.setdefault(application, {})["last_action_failed"] = True
        self.current_state.timestamp = time.time()
        failure_data = {
            "failure_info": {
                "node_id": result.node_id or node.get("id"),
                "error": result.error,
                "timestamp": self.current_state.timestamp,
                "execution_time": result.execution_time,
                "status": result.status.value,
            },
            "world_state": self._get_state_for_planning(),
        }
        try:
            self.memory_manager.update_world_state(failure_data)
        except Exception:
            logger.exception("[EXECUTOR] No se pudo persistir el fallo del nodo %s", node.get("id"))

    def _goal_achieved(self, goal: Dict[str, Any], current_state: Dict[str, Any]) -> bool:
        """Comprueba objetivos conocidos usando tanto estado plano como estado anidado."""
        if not isinstance(goal, dict):
            goal = {
                "type": getattr(goal, "type", None),
                "target": getattr(goal, "target", None),
                "metadata": getattr(goal, "metadata", {}) or {},
            }
        goal_type = str(goal.get("type", "")).lower()
        target = goal.get("target")
        if goal_type in {"navigate", "navigate_stream"}:
            target_url = target if isinstance(target, str) else target.get("url") if isinstance(target, dict) else None
            if not target_url:
                return False
            current_url = current_state.get("current_url")
            return isinstance(current_url, str) and current_url.rstrip("/") == str(target_url).rstrip("/")
        if goal_type in {"open_application", "close_application"}:
            target_name = str(target or "").strip().lower().replace(" ", "_")
            if not target_name:
                return False
            opened = current_state.get(f"{target_name}_open")
            app_states = current_state.get("application_states", {})
            nested = app_states.get(target_name, {}) if isinstance(app_states, dict) else {}
            if opened is None and isinstance(nested, dict):
                opened = nested.get("open")
            opened = bool(opened) if opened is not None else False
            return opened if goal_type == "open_application" else not opened
        if goal_type == "search":
            return bool(current_state.get("search_performed"))
        metadata = goal.get("metadata", {})
        target_state = metadata.get("target_state") if isinstance(metadata, dict) else None
        if isinstance(target_state, dict) and target_state:
            return all(self._get_nested_value(current_state, str(k)) == v for k, v in target_state.items())
        return False

    def _execute_node_action(self, node: Dict[str, Any], timeout: Optional[float]) -> Any:
        """Ejecuta callback explícito o acción registrada vinculada al nodo."""
        parameters = node.get("parameters", {}) or {}
        if not isinstance(parameters, dict):
            raise TypeError("Los parámetros del nodo deben ser un diccionario")
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        callback = node.get("execute_callback") or metadata.get("execute_callback")
        if callable(callback):
            result = callback(current_state=self._get_state_for_planning(), **copy.deepcopy(parameters))
            return result

        action_name = node.get("action")
        node_id = node.get("id")
        explicit_action = metadata.get("action_name") or metadata.get("action")
        if explicit_action and (not action_name or action_name == node_id):
            action_name = explicit_action
        action_name = action_name or node_id
        if not action_name:
            raise ValueError("Nodo sin acción definida")
        node_type = str(getattr(node.get("type"), "value", node.get("type", ""))).lower()
        if node_type in {"state", "resource", "goal", "application", "ui_element", "result", "plan"}:
            raise ValueError(f"El nodo {node_id} es declarativo y no se puede ejecutar como acción")
        verify = node.get("verify", metadata.get("verify", True))
        return self.execute_action(str(action_name), dict(parameters), state=self.current_state, verify=bool(verify), timeout=timeout)

    def _check_node_preconditions(self, node: Dict[str, Any]) -> bool:
        """Evalúa todas las precondiciones; las desconocidas no se consideran verdaderas."""
        preconditions = node.get("preconditions", []) or []
        for condition in preconditions:
            if not self._evaluate_condition(condition):
                logger.warning("[EXECUTOR] Precondición no satisfecha para nodo %s: %s", node.get("id"), condition)
                return False
        return True

    def _evaluate_condition(self, condition: Any) -> bool:
        """Evalúa condiciones tipadas, callbacks, diccionarios o claves de estado."""
        state = self._get_state_for_planning()
        if isinstance(condition, bool):
            return condition
        if callable(condition):
            try:
                return bool(condition(state))
            except Exception:
                logger.exception("[EXECUTOR] Error evaluando precondición callable")
                return False
        if not isinstance(condition, (str, dict)):
            # Compatibilidad con objetos Condition del módulo preconditions_effects_types.
            for method_name in ("evaluate", "is_satisfied", "check", "matches"):
                evaluator = getattr(condition, method_name, None)
                if callable(evaluator):
                    try:
                        return bool(evaluator(state))
                    except TypeError:
                        try:
                            return bool(evaluator())
                        except Exception:
                            return False
                    except Exception:
                        return False
            converter = getattr(condition, "to_dict", None)
            if callable(converter):
                try:
                    converted = converter()
                    if isinstance(converted, dict):
                        return self._evaluate_condition(converted)
                except Exception:
                    return False
            return False

        if isinstance(condition, dict):
            key = condition.get("key", condition.get("state", condition.get("path")))
            if key is None:
                return all(self._evaluate_condition({"key": k, "value": v}) for k, v in condition.items())
            expected = condition.get("equals", condition.get("value", condition.get("expected", True)))
            actual = self._get_nested_value(state, str(key))
            operator = str(condition.get("operator", "eq")).lower()
            try:
                if operator in {"eq", "=="}:
                    return actual == expected
                if operator in {"ne", "!="}:
                    return actual != expected
                if operator in {"gt", ">"}:
                    return actual > expected
                if operator in {"gte", ">="}:
                    return actual >= expected
                if operator in {"lt", "<"}:
                    return actual < expected
                if operator in {"lte", "<="}:
                    return actual <= expected
                if operator == "exists":
                    return actual is not None
            except (TypeError, ValueError):
                return False
            return False

        key = condition.strip()
        if not key:
            return True
        actual = self._get_nested_value(state, key)
        if actual is not None:
            return bool(actual)

        lowered = key.lower()
        app_states = self.current_state.application_states
        normalized_apps = {
            str(name).strip().lower().replace(" ", "_"): details
            for name, details in app_states.items()
        }
        if lowered.startswith("app_"):
            requested = lowered[4:]
            return requested in normalized_apps or requested in {
                str(name).strip().lower().replace(" ", "_") for name in normalized_apps
            }
        if lowered.startswith("ui_"):
            requested = lowered[3:]
            return any(str(name).lower() == requested for name in self.current_state.ui_elements)

        # Generic application/browser conditions can be satisfied by the canonical nested state.
        if lowered in {"application_open", "application_active", "browser_open", "browser_active"}:
            target_field = "active" if lowered.endswith("active") else "open"
            browser_only = lowered.startswith("browser_")
            for app_name, details in normalized_apps.items():
                if not isinstance(details, dict):
                    continue
                if browser_only and not any(browser in app_name for browser in ("chrome", "edge", "firefox", "browser")):
                    continue
                if bool(details.get(target_field, False)):
                    return True
            return False

        for suffix, field_name in (("_open", "open"), ("_active", "active"), ("_closed", "open")):
            if lowered.endswith(suffix):
                app_name = lowered[:-len(suffix)]
                app_state = normalized_apps.get(app_name, {})
                if isinstance(app_state, dict) and field_name in app_state:
                    value = bool(app_state[field_name])
                    return not value if suffix == "_closed" else value

        if lowered in {"application_available", "browser_available"}:
            browser_only = lowered == "browser_available"
            if any(
                not browser_only or any(browser in name for browser in ("chrome", "edge", "firefox", "browser"))
                for name in normalized_apps
            ):
                return True
            # If the runtime hasn't observed an application yet, consult the declarative catalog.
            manager_factory = getattr(applications, "get_application_manager", None)
            if callable(manager_factory):
                try:
                    manager = manager_factory()
                    catalog = getattr(manager, "applications", {}) or {}
                    if isinstance(catalog, dict):
                        if not browser_only and catalog:
                            return True
                        return any(any(browser in str(name).lower() for browser in ("chrome", "edge", "firefox", "browser")) for name in catalog)
                except Exception:
                    pass
            if not browser_only:
                return bool(state.get("available_actions"))
            return False
        if lowered == "resources_available":
            return bool(state.get("resources_available", state.get("available_actions")))
        return False

    @staticmethod
    def _get_nested_value(state: Dict[str, Any], key: str) -> Any:
        if key in state:
            return state[key]
        current: Any = state
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _try_alternative(self, node: Dict[str, Any], failed_result: ExecutionResult) -> ExecutionResult:
        """Prueba alternativas declaradas, sin repetir la acción original."""
        alternatives = node.get("alternatives", []) or []
        if not alternatives:
            return failed_result

        started = time.perf_counter()
        tried: List[str] = []
        for raw_alternative in alternatives:
            if isinstance(raw_alternative, dict):
                alternative_node = copy.deepcopy(raw_alternative)
                action_name = alternative_node.get("action") or alternative_node.get("id")
                alternative_node.setdefault("parameters", copy.deepcopy(node.get("parameters", {}) or {}))
                alternative_node.setdefault("preconditions", copy.deepcopy(node.get("preconditions", []) or []))
                alternative_node.setdefault("effects", copy.deepcopy(node.get("effects", []) or []))
                alternative_node.setdefault("application", node.get("application"))
                alternative_node.setdefault("ui_element", node.get("ui_element"))
                alternative_node.setdefault("cost", self._safe_cost(node.get("cost", 1.0)) * 0.9)
                alternative_node["action"] = action_name
                alternative_label = str(alternative_node.get("id") or action_name or "unknown")
            else:
                action_name = str(raw_alternative or "").strip()
                alternative_label = action_name
                alternative_node = {
                    "id": f"alternative_{action_name}",
                    "action": action_name,
                    "parameters": copy.deepcopy(node.get("parameters", {}) or {}),
                    "preconditions": copy.deepcopy(node.get("preconditions", []) or []),
                    "effects": copy.deepcopy(node.get("effects", []) or []),
                    "application": node.get("application"),
                    "ui_element": node.get("ui_element"),
                    "cost": self._safe_cost(node.get("cost", 1.0)) * 0.9,
                    "alternatives": [],
                }
            if not action_name or action_name == node.get("action"):
                continue
            tried.append(alternative_label)
            try:
                if not self._check_node_preconditions(alternative_node):
                    continue
                raw = self._execute_node_action(alternative_node, timeout=None)
                if raw is not None and self._verify_node_success(alternative_node, raw):
                    return ExecutionResult(
                        status=ExecutionStatus.SUCCESS,
                        result=raw,
                        execution_time=max(0.0, time.perf_counter() - started),
                        node_id=alternative_label,
                        retries=failed_result.retries,
                        alternatives_tried=tried,
                    )
            except Exception as exc:
                logger.warning("[EXECUTOR] Alternativa %s falló: %s", alternative_label, exc)

        failed_result.alternatives_tried = list(dict.fromkeys((failed_result.alternatives_tried or []) + tried))
        return failed_result

    def _update_world_state(self, node: Dict[str, Any], result: ExecutionResult) -> None:
        """Actualiza el mundo únicamente tras confirmar el éxito del nodo."""
        if result.status != ExecutionStatus.SUCCESS:
            return
        app_name = str(node.get("application") or "").strip()
        app_key = app_name.lower().replace(" ", "_")
        app_state = self.current_state.application_states.setdefault(app_name, {}) if app_name else None
        effects = [str(effect).strip().lower() for effect in (node.get("effects", []) or [])]
        for effect in effects:
            if effect in {"app_open", "application_open", f"{app_key}_open"} or effect.endswith("_open"):
                if app_state is not None:
                    app_state["open"] = True
                if app_key:
                    state_key = effect if effect.endswith("_open") and effect != "application_open" else f"{app_key}_open"
                    setattr(self.current_state, "timestamp", time.time())
                    # Keep flattened keys in sync for old precondition consumers.
                    self.current_state.constraints = [c for c in self.current_state.constraints if c != state_key]
                    self.current_state.__dict__[state_key] = True
            elif effect in {"app_active", "application_active", f"{app_key}_active"} or effect.endswith("_active"):
                if app_state is not None:
                    app_state["active"] = True
                if app_key:
                    self.current_state.__dict__[f"{app_key}_active"] = True
            elif effect in {"app_closed", "application_closed", f"{app_key}_closed"} or effect.endswith("_closed"):
                if app_state is not None:
                    app_state["open"] = False
                if app_key:
                    self.current_state.__dict__[f"{app_key}_open"] = False
            elif effect in {"app_minimized", "window_minimized"}:
                if app_state is not None:
                    app_state["active"] = False
            elif effect in {"address_bar_focused", "element_focused", "focused"} or effect.endswith("_focused"):
                element = node.get("ui_element") or effect.removesuffix("_focused")
                if element:
                    self.current_state.ui_elements.setdefault(str(element), {})["focused"] = True
            elif effect in {"url_typed", "text_typed", "typed"}:
                if app_state is not None:
                    app_state["url_typed" if effect == "url_typed" else "typed"] = True
            elif effect in {"destination_loaded", "page_loaded", "url_changed"}:
                if app_state is not None:
                    app_state["destination_loaded"] = True
                self.current_state.__dict__["destination_loaded"] = True
            elif effect in {"search_performed", "results_displayed"}:
                self.current_state.__dict__["search_performed"] = True

        raw_result = result.result
        if isinstance(raw_result, dict):
            updates = raw_result.get("state_updates") or raw_result.get("new_state_updates")
            if isinstance(updates, dict):
                self._apply_state_updates(updates)
            if isinstance(raw_result.get("new_state"), dict):
                self._apply_state_updates(raw_result["new_state"])
            for key in ("current_url", "resolved_url", "entity_resolved", "search_performed", "browser_ready"):
                if key in raw_result:
                    self.current_state.__dict__[key] = raw_result[key]

        ui_element = node.get("ui_element")
        if ui_element:
            ui_state = self.current_state.ui_elements.setdefault(str(ui_element), {})
            for effect in effects:
                if "focus" in effect:
                    ui_state["focused"] = True
                if "click" in effect:
                    ui_state["clicked"] = True
                if "typed" in effect or effect == "text_typed":
                    ui_state["typed"] = True

        self.current_state.timestamp = time.time()
        executed_id = result.node_id or str(node.get("id") or node.get("action") or "unknown")
        if executed_id not in self.current_state.last_actions:
            self.current_state.last_actions.append(executed_id)
        self.current_state.last_actions = self.current_state.last_actions[-100:]
        try:
            self.memory_manager.update_world_state({"last_execution": {
                "node_id": executed_id,
                "timestamp": self.current_state.timestamp,
                "status": result.status.value,
                "node_effects": effects,
                "application": app_name or None,
                "ui_element": ui_element,
            }, "world_state": self._get_state_for_planning()})
        except Exception:
            logger.exception("[EXECUTOR] No se pudo persistir el estado tras %s", executed_id)

    def _apply_state_updates(self, updates: Dict[str, Any]) -> None:
        """Fusiona actualizaciones explícitas con el estado runtime."""
        if not isinstance(updates, dict):
            return
        for key, value in updates.items():
            if key == "application_states" and isinstance(value, dict):
                for app, app_data in value.items():
                    if isinstance(app_data, dict):
                        self.current_state.application_states.setdefault(str(app), {}).update(copy.deepcopy(app_data))
            elif key == "ui_elements" and isinstance(value, dict):
                for element, element_data in value.items():
                    if isinstance(element_data, dict):
                        self.current_state.ui_elements.setdefault(str(element), {}).update(copy.deepcopy(element_data))
            elif key in {"available_actions", "last_actions", "constraints"} and isinstance(value, list):
                setattr(self.current_state, key, list(value))
            elif key != "timestamp":
                self.current_state.__dict__[key] = copy.deepcopy(value)

    def execute_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
        verify: bool = True,
        timeout: Optional[float] = None,
    ) -> Any:
        """Ejecuta una acción registrada y verifica su resultado antes de confirmarlo."""
        started = time.perf_counter()
        if not isinstance(action_name, str) or not action_name.strip():
            raise ValueError("action_name debe ser un nombre no vacío")
        safe_parameters = dict(parameters or {})
        if not isinstance(parameters, (dict, type(None))):
            raise TypeError("parameters debe ser un diccionario")

        action_info = self.action_registry.get_action(action_name)
        if action_info is None:
            raise ValueError(f"Acción no encontrada: {action_name}")
        state_value = state.__dict__ if hasattr(state, "__dict__") and not isinstance(state, dict) else state

        try:
            validate = getattr(self.action_registry, "validate_action", None)
            if callable(validate) and not validate(action_name, safe_parameters):
                raise ValueError(f"Parámetros no válidos para: {action_name}")
            checker = getattr(action_info, "matches_preconditions", None)
            if state_value is not None and callable(checker) and not checker(state_value):
                raise ValueError(f"Precondiciones no satisfechas para: {action_name}")

            def invoke() -> Any:
                return self.action_registry.execute_action(action_name, safe_parameters)

            if timeout is not None and float(timeout) > 0:
                pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-action")
                future = pool.submit(invoke)
                try:
                    result = future.result(timeout=float(timeout))
                except FuturesTimeoutError as exc:
                    future.cancel()
                    # Una acción física ya iniciada no se puede cancelar de forma segura.
                    # No se reintenta automáticamente tras este resultado incierto.
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise TimeoutError(
                        f"Acción {action_name} superó {float(timeout):.2f}s; el resultado externo puede ser incierto"
                    ) from exc
                except BaseException:
                    pool.shutdown(wait=True)
                    raise
                else:
                    pool.shutdown(wait=True)
            else:
                result = invoke()

            verifier = getattr(action_info, "verify_success", None)
            if verify and callable(verifier) and not verifier(result, **safe_parameters):
                raise RuntimeError(f"Acción ejecutada pero no verificada: {action_name}")
        except Exception as exc:
            elapsed = max(0.0, time.perf_counter() - started)
            self._record_action_execution(action_name, False, elapsed)
            self._record_learning_action(action_name, False, elapsed, action_info, verify, safe_parameters)
            logger.warning("[EXECUTOR] La acción %s falló: %s", action_name, exc)
            raise

        elapsed = max(0.0, time.perf_counter() - started)
        self._record_action_execution(action_name, True, elapsed)
        self._record_learning_action(action_name, True, elapsed, action_info, verify, safe_parameters)
        return result

    def _record_learning_action(
        self,
        action_name: str,
        success: bool,
        execution_time: float,
        action_info: Any,
        verify: bool,
        parameters: Dict[str, Any],
    ) -> None:
        """Registra aprendizaje sin convertir un fallo de telemetría en fallo de acción."""
        if self.learning_system is None:
            return
        try:
            self.learning_system.record_action_execution(
                action_name=action_name,
                success=bool(success),
                execution_time=max(0.0, execution_time),
                estimated_cost=self._safe_cost(getattr(action_info, "cost", 1.0)),
                context={"verify": verify, "parameters": copy.deepcopy(parameters)},
                application=getattr(action_info, "application", None),
                screen_state=self._get_screen_state(),
            )
        except Exception:
            logger.exception("[EXECUTOR] No se pudo registrar el aprendizaje de %s", action_name)

    def can_execute(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
    ) -> bool:
        """Comprueba si una acción registrada puede ejecutarse ahora."""
        try:
            action_info = self.action_registry.get_action(action_name)
            if action_info is None:
                return False
            safe_parameters = dict(parameters or {})
            validate = getattr(self.action_registry, "validate_action", None)
            if callable(validate) and not validate(action_name, safe_parameters):
                return False
            state_value = state.__dict__ if hasattr(state, "__dict__") and not isinstance(state, dict) else state
            checker = getattr(action_info, "matches_preconditions", None)
            return state_value is None or not callable(checker) or bool(checker(state_value))
        except Exception:
            return False

    def process_and_execute(self, llm_response: str) -> str:

        """Procesa respuesta LLM y ejecuta comando (mantenido para compatibilidad)."""

        if not isinstance(llm_response, str):

            return str(llm_response)

        match = self._COMMAND_PATTERN.search(llm_response)

        if not match:

            return llm_response.strip()

        command_name = match.group(1)

        args_str = match.group(2)

        _log("info", "Procesando solicitud", "executor.py", "method", 222)

        clean_text = (

            llm_response[:match.start()] + llm_response[match.end():]

        ).strip()

        try:

            parsed_args = self._parse_args(args_str)

            result = self._execute_legacy_or_registered(command_name, parsed_args)

            if result is not None and not isinstance(result, str):

                result = str(result)

            return result or clean_text

        except Exception as exc:

            _log("error", r"[EXECUTOR] Error ejecutando comando legacy %s: %s [file:executor.py, method:execute_command, line:988]", "executor.py", "method", 988)

            return f"Error en ejecución: {exc}"

    def _execute_legacy_or_registered(self, command_name: str, positional_args: tuple) -> Any:

        """Ejecuta mediante ActionRegistry o fallback legacy."""

        action_info = self.action_registry.get_action(command_name)

        if action_info is not None:

            parameters = self._positional_to_named_parameters(action_info, positional_args)

            return self.execute_action(command_name, parameters)

        func = self._get_legacy_function(command_name)

        if func is None:

            raise ValueError(f"Comando no reconocido: {command_name}")

        try:

            result = func(*positional_args)

            self._record_command_execution(command_name, True)

            return result

        except Exception:

            self._record_command_execution(command_name, False)

            raise

    def _positional_to_named_parameters(self, action_info: ActionInfo, positional_args: tuple) -> Dict[str, Any]:

        """Convierte argumentos posicionales a nombrados."""

        if not positional_args:

            return {}

        parameter_names = list(action_info.parameters.keys())

        if len(positional_args) > len(parameter_names):

            raise ValueError(

                f"Demasiados argumentos para {action_info.name}: "

                f"esperados {len(parameter_names)}, recibidos {len(positional_args)}"

            )

        return {

            parameter_names[index]: value for index, value in enumerate(positional_args)

        }

    def _parse_args(self, args_str: Optional[str]) -> tuple:

        """Parsea argumentos mediante ast.literal_eval."""

        if args_str is None:

            return ()

        args_str = args_str.strip()

        if not args_str:

            return ()

        try:

            parsed_args = ast.literal_eval(f"({args_str})")

            return parsed_args if isinstance(parsed_args, tuple) else (parsed_args,)

        except (ValueError, SyntaxError, TypeError) as exc:

            raise ValueError(f"Argumentos no válidos: {args_str}") from exc

    def _get_legacy_function(self, command_name: str):

        """Busca función legacy en módulos."""

        if not command_name:

            return None

        for module_name, module in self.modules.items():

            try:

                if hasattr(module, command_name):

                    function = getattr(module, command_name)

                    if callable(function):

                        return function

            except Exception as exc:

                _log("debug", r"[EXECUTOR] Error buscando %s en módulo %s: %s [file:executor.py, method:_get_legacy_function, line:1055]", "executor.py", "method", 1055)

        return None

    # ========================================================================

    # ESTADO Y ESTADÍSTICAS

    # ========================================================================

    def get_current_state(self) -> ExecutionState:

        """Obtiene el estado actual del mundo."""

        return self.current_state

    def update_state(self, update_data: Dict[str, Any]) -> None:

        """Actualiza el estado del mundo."""

        self.current_state.update(update_data)

    def get_action_stats(self) -> Dict[str, Any]:

        """Obtiene estadísticas de ejecución de acciones."""

        try:

            return self.memory_manager.get_action_stats()

        except Exception as exc:

            _log("error", r"[EXECUTOR] Error obteniendo estadísticas: %s [file:executor.py, method:get_action_stats, line:1076]", "executor.py", "method", 1076)

            return {}

    def _record_action_execution(self, action_name: str, success: bool, execution_time: float) -> None:

        """Registra ejecución de acción para estadísticas."""

        try:

            self.memory_manager.record_action_execution(

                action_name,

                success,

                execution_time

            )

        except Exception as exc:

            _log("error", r"[EXECUTOR] Error registrando ejecución: %s [file:executor.py, method:_record_action_execution, line:1088]", "executor.py", "method", 1088)

    def _get_screen_state(self) -> Dict[str, Any]:

        """Obtiene estado actual de la pantalla para aprendizaje."""

        try:

            # Obtener estado actual del mundo

            exec_state = self.get_current_state()

            return {

                "application_states": exec_state.application_states,

                "ui_elements": exec_state.ui_elements,

                "timestamp": exec_state.timestamp,

                "last_actions": exec_state.last_actions

            }

        except Exception as e:

            _log("info", f"Error obteniendo estado de pantalla: {e}")

            return {}

    # ========================================================================

    # INTERFACES DE APRENDIZAJE (FASE 18)

    # ========================================================================

    def get_learning_insights(self) -> Dict[str, Any]:

        """

        Obtiene insights del sistema de aprendizaje (FASE 18).

        Returns:

            Insights detallados del sistema de aprendizaje

        """

        if not self.learning_system:

            return {"error": "Sistema de aprendizaje no disponible"}

        return self.learning_system.get_system_insights()

    def get_action_learning_insights(self, action_name: str) -> Dict[str, Any]:

        """

        Obtiene insights específicos de una acción (FASE 18).

        Args:

            action_name: Nombre de la acción

        Returns:

            Insights detallados de la acción

        """

        if not self.learning_system:

            return {"error": "Sistema de aprendizaje no disponible"}

        return self.learning_system.get_action_insights(action_name)

    def get_cost_adjustments(self) -> Dict[str, float]:

        """

        Obtiene ajustes de coste aprendidos (FASE 18).

        Returns:

            Ajustes de coste por acción

        """

        if not self.learning_system:

            return {}

        return self.learning_system.get_cost_adjustments()

    def export_learning_data(self, filepath: str) -> None:

        """

        Exporta datos de aprendizaje (FASE 18).

        Args:

            filepath: Ruta del archivo de exportación

        """

        if not self.learning_system:

            _log("warning", r"Sistema de aprendizaje no disponible para exportar [file:executor.py, method:export_learning_data, line:1156]", "executor.py", "method", 1156)

            return

        self.learning_system.export_learning_data(filepath)

    def import_learning_data(self, filepath: str) -> None:

        """

        Importa datos de aprendizaje (FASE 18).

        Args:

            filepath: Ruta del archivo de importación

        """

        if not self.learning_system:

            _log("warning", r"Sistema de aprendizaje no disponible para importar [file:executor.py, method:import_learning_data, line:1169]", "executor.py", "method", 1169)

            return

        self.learning_system.import_learning_data(filepath)

    def clear_learning_data(self) -> None:

        """Limpia datos de aprendizaje (FASE 18)."""

        if not self.learning_system:

            _log("warning", r"Sistema de aprendizaje no disponible para limpiar [file:executor.py, method:clear_learning_data, line:1177]", "executor.py", "method", 1177)

            return

        self.learning_system.clear_learning_data()

    def enable_learning(self, enabled: bool = True) -> None:

        """

        Habilita o deshabilita el aprendizaje (FASE 18).

        Args:

            enabled: Si se debe habilitar el aprendizaje

        """

        if not self.learning_system:

            _log("warning", r"Sistema de aprendizaje no disponible [file:executor.py, method:enable_learning, line:1190]", "executor.py", "method", 1190)

            return

        self.learning_system.enable_learning(enabled)

    def _record_command_execution(self, command_name: str, success: bool) -> None:

        """Registra ejecución de comando legacy."""

        try:

            self.memory_manager.record_command_usage(

                "comando ejecutado",

                command_name,

                success,

            )

        except Exception as exc:

            _log("error", r"[EXECUTOR] Error registrando comando legacy: %s [file:executor.py, method:_record_command_execution, line:1204]", "executor.py", "method", 1204)

    # ========================================================================

    # INTERFACES PÚBLICAS

    # ========================================================================

    def list_commands(self) -> List[str]:

        """Lista todas las acciones conocidas."""

        commands = set(self.action_registry.list_actions())

        for module in self.modules.values():

            try:

                for name in dir(module):

                    if name.startswith("_"):

                        continue

                    try:

                        attribute = getattr(module, name)

                        if callable(attribute):

                            commands.add(name)

                    except Exception:

                        continue

            except Exception:

                continue

        return sorted(commands)

    def get_plannable_actions(self) -> Dict[str, ActionInfo]:

        """Obtiene acciones disponibles para planificación."""

        return self.action_registry.get_plannable_actions()

    def get_action_info(self, action_name: str) -> Optional[ActionInfo]:

        """Obtiene información de una acción específica."""

        return self.action_registry.get_action(action_name)

    # ========================================================================

    # EJECUCIÓN DE OBJETIVOS (FASE 7 - INTEGRACIÓN CON PLANIFICADOR)

    # ========================================================================

    def execute_goal(
        self,
        goal: Goal,
        max_planning_time: float = 30.0,
        find_alternatives: bool = True,
        plan_id: Optional[str] = None,
        enable_learning: bool = True,
    ) -> Dict[str, Any]:
        """Planifica y ejecuta un objetivo, devolviendo el resultado confirmado."""
        started = time.perf_counter()
        if goal is None or not getattr(goal, "id", None):
            return {"success": False, "error": "Objetivo inválido", "goal_id": None}
        if self.planner is None:
            return {"success": False, "error": "Planner no disponible", "goal_id": goal.id}

        old_learning_state = getattr(self.learning_system, "learning_enabled", None) if self.learning_system else None
        try:
            if self.learning_system is not None:
                self.learning_system.enable_learning(bool(enable_learning))
            planning_result = self.planner.plan(
                goal=goal,
                current_state=self._get_state_for_planning(),
                max_planning_time=max(0.01, float(max_planning_time)),
                find_alternatives=bool(find_alternatives),
                use_optimization=bool(enable_learning),
            )
            status = getattr(getattr(planning_result, "status", None), "value", getattr(planning_result, "status", None))
            if str(status).lower() != "completed":
                return {
                    "success": False,
                    "error": "Planificación fallida",
                    "goal_id": goal.id,
                    "planning_time": getattr(planning_result, "execution_time", 0.0),
                    "warnings": list(getattr(planning_result, "warnings", []) or []),
                    "plan": None,
                    "total_time": max(0.0, time.perf_counter() - started),
                }

            actual_plan_id = plan_id or f"goal_{goal.id}_{int(time.time() * 1000)}"
            planned_steps = list(getattr(planning_result, "plan", []) or [])
            if not planned_steps:
                # El Planner utiliza un plan vacío cuando el objetivo ya está satisfecho.
                quality = getattr(getattr(planning_result, "quality", None), "value", getattr(planning_result, "quality", None))
                return {
                    "success": True,
                    "goal_id": goal.id,
                    "goal_type": getattr(goal, "type", None),
                    "plan_id": actual_plan_id,
                    "plan_length": 0,
                    "planning_time": max(0.0, float(getattr(planning_result, "execution_time", 0.0) or 0.0)),
                    "execution_time": 0.0,
                    "total_time": max(0.0, time.perf_counter() - started),
                    "quality": quality,
                    "alternatives_found": len(getattr(planning_result, "alternatives", []) or []),
                    "plan": [],
                    "execution_status": "success",
                    "error": None,
                    "world_state": self._get_state_for_planning(),
                    "message": "Objetivo ya alcanzado; no se requiere ejecución",
                }
            execution_result = self.execute_plan(planned_steps, plan_id=actual_plan_id)
            quality = getattr(getattr(planning_result, "quality", None), "value", getattr(planning_result, "quality", None))
            success = execution_result.status == ExecutionStatus.SUCCESS
            return {
                "success": success,
                "goal_id": goal.id,
                "goal_type": getattr(goal, "type", None),
                "plan_id": actual_plan_id,
                "plan_length": len(getattr(planning_result, "plan", []) or []),
                "planning_time": max(0.0, float(getattr(planning_result, "execution_time", 0.0) or 0.0)),
                "execution_time": execution_result.execution_time,
                "total_time": max(0.0, time.perf_counter() - started),
                "quality": quality,
                "alternatives_found": len(getattr(planning_result, "alternatives", []) or []),
                "plan": getattr(planning_result, "plan", []),
                "execution_status": execution_result.status.value,
                "error": execution_result.error,
                "execution_result": execution_result.to_dict(),
                "world_state": self._get_state_for_planning(),
            }
        except Exception as exc:
            logger.exception("[EXECUTOR] Error ejecutando el objetivo %s", getattr(goal, "id", None))
            return {"success": False, "error": str(exc), "goal_id": getattr(goal, "id", None), "total_time": max(0.0, time.perf_counter() - started)}
        finally:
            if self.learning_system is not None and old_learning_state is not None:
                try:
                    self.learning_system.enable_learning(bool(old_learning_state))
                except Exception:
                    logger.exception("[EXECUTOR] No se pudo restaurar la configuración de aprendizaje")

    def _get_state_for_planning(self) -> Dict[str, Any]:
        """Devuelve una instantánea independiente y compatible del estado actual."""
        state = self.current_state.to_dict()
        # Include dynamic keys written by confirmed action results (e.g. current_url).
        for key, value in self.current_state.__dict__.items():
            if key not in state:
                state[key] = copy.deepcopy(value)
        state["applications"] = copy.deepcopy(self.current_state.application_states)
        for application, details in self.current_state.application_states.items():
            if not isinstance(details, dict):
                continue
            key = str(application).strip().lower().replace(" ", "_")
            if "open" in details:
                state[f"{key}_open"] = bool(details["open"])
            if "active" in details:
                state[f"{key}_active"] = bool(details["active"])
        for element, details in self.current_state.ui_elements.items():
            if isinstance(details, dict):
                for property_name, value in details.items():
                    state[f"ui_{element}_{property_name}"] = copy.deepcopy(value)
        return state

    def create_goal_from_command(self, command_name: str, parameters: Dict[str, Any]) -> Optional[Goal]:

        """

        Crea un objetivo a partir de un comando legacy.

        Args:

            command_name: Nombre del comando

            parameters: Parámetros del comando

        Returns:

            Goal creado o None si no se puede crear

        """

        from src.hands.planner.node import Goal

        # Mapeo básico de comandos a tipos de objetivo

        command_goal_mapping = {

            "abrir_youtube": ("open_application", "youtube"),

            "abrir_chrome": ("open_application", "chrome"),

            "navegar_a": ("navigate", parameters.get("url", "")),

            "buscar_en_google": ("search", parameters.get("query", "")),

            "cerrar_chrome": ("close_application", "chrome"),

        }

        if command_name in command_goal_mapping:

            goal_type, target = command_goal_mapping[command_name]

            return Goal(

                id=f"goal_{command_name}_{int(time.time())}",

                type=goal_type,

                target=target,

                description=f"Objetivo desde comando: {command_name}",

                metadata={

                    "original_command": command_name,

                    "parameters": parameters,

                    "created_from_legacy": True

                }

            )

        return None

_executor_instance: Optional[Executor] = None
_executor_instance_lock = threading.Lock()

def get_executor() -> Executor:
    """Obtiene el singleton global de Executor de manera segura ante concurrencia."""
    global _executor_instance
    if _executor_instance is None:
        with _executor_instance_lock:
            if _executor_instance is None:
                _executor_instance = Executor()
    return _executor_instance

__all__ = ["Executor", "ExecutionResult", "ExecutionStatus", "ExecutionState", "get_executor"]
