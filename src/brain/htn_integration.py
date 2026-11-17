"""
Integracion de HTN con el Brain de JARVIS - FASE 4.

Integra la descomposicion jerarquica de objetivos con HTNManager y
TaskExecutor, manteniendo compatibilidad con el Brain existente.
"""

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.hands.planner.node import Goal, TaskStatus
from src.hands.planner.htn_manager import get_htn_manager, HTNManager
from src.hands.planner.task_executor import get_task_executor, TaskExecutor
from src.hands.planner.application_integration import (
    get_application_knowledge_integrator,
)
from src.memory.storage import get_memory_manager, Entity
from src.core.log import get_logger

logger = get_logger(__name__)


@dataclass
class HTNIntegrationResult:
    """Resultado de la integracion HTN-Brain."""

    success: bool
    goal_id: str
    goal_type: str
    decomposed_tasks: List[Dict[str, Any]]
    execution_results: List[Dict[str, Any]]
    total_execution_time: float
    message: str
    error_message: Optional[str] = None
    final_state: Optional[Dict[str, Any]] = None


class HTNBrainIntegration:
    """Integra interpretacion de objetivos, HTN y ejecucion de tareas."""

    def __init__(self) -> None:
        self.htn_manager = get_htn_manager()
        self.task_executor = get_task_executor()
        self.application_integrator = get_application_knowledge_integrator()
        self.memory_manager = get_memory_manager()

        self.is_enabled = True
        self.last_execution_time = 0.0
        self.total_integrations = 0
        self.successful_integrations = 0

        logger.info("Integracion HTN-Brain inicializada")

    # ====================================================================
    # FLUJO PRINCIPAL
    # ====================================================================

    def process_goal_through_htn(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
    ) -> HTNIntegrationResult:
        """Descompone y ejecuta un objetivo completo mediante HTN."""
        if not self.is_enabled:
            return HTNIntegrationResult(
                success=False,
                goal_id=goal.id,
                goal_type=goal.type,
                decomposed_tasks=[],
                execution_results=[],
                total_execution_time=0.0,
                message="Integraci\u00f3n HTN deshabilitada",
                error_message="HTN integration is disabled",
                final_state=dict(current_state or {}),
            )

        start_time = time.time()
        logger.info("[HTN_INTEGRATION] Procesando objetivo HTN: " + goal.id + " (" + goal.type + ")")

        try:
            state = dict(current_state or {})

            logger.info("Fase 1: Descomposicion de objetivo")
            tasks = self.htn_manager.decompose_goal(goal, state)

            if not tasks:
                execution_time = time.time() - start_time
                self._record_integration(execution_time, False)
                return HTNIntegrationResult(
                    success=False,
                    goal_id=goal.id,
                    goal_type=goal.type,
                    decomposed_tasks=[],
                    execution_results=[],
                    total_execution_time=execution_time,
                    message="No se pudo descomponer el objetivo en tareas",
                    error_message="Goal decomposition failed",
                    final_state=state,
                )

            decomposed_tasks = [self._serialize_task(task) for task in tasks]
            logger.info("Objetivo descompuesto en " + str(len(tasks)) + " tareas")

            logger.info("Fase 2: Ejecucion de jerarquia")
            execution_result = self.htn_manager.execute_goal_hierarchy(goal, state)
            execution_results = [self._serialize_execution_result(execution_result)]

            logger.info("Fase 3: Procesamiento de resultados")
            final_state = self._process_execution_results(
                goal,
                execution_result,
                state,
            )

            execution_time = time.time() - start_time
            completed = execution_result.status == TaskStatus.COMPLETED
            self._record_integration(execution_time, completed)

            message = (
                "Integraci\u00f3n HTN completada exitosamente"
                if completed
                else "Integraci\u00f3n HTN completada con fallo de ejecuci\u00f3n"
            )
            logger.info("Integracion completada: " + execution_result.status.value + " (" + str(execution_time) + "s)")

            return HTNIntegrationResult(
                success=completed,
                goal_id=goal.id,
                goal_type=goal.type,
                decomposed_tasks=decomposed_tasks,
                execution_results=execution_results,
                total_execution_time=execution_time,
                message=message,
                error_message=(
                    execution_result.error_message
                    if not completed
                    else None
                ),
                final_state=final_state,
            )

        except Exception as exc:
            execution_time = time.time() - start_time
            self._record_integration(execution_time, False)
            logger.error("[HTN_INTEGRATION] Error en integracion: " + str(exc))
            return HTNIntegrationResult(
                success=False,
                goal_id=goal.id,
                goal_type=goal.type,
                decomposed_tasks=[],
                execution_results=[],
                total_execution_time=execution_time,
                message="Error en integraci\u00f3n HTN",
                error_message=str(exc),
                final_state=dict(current_state or {}),
            )

    def create_and_execute_htn_goal(
        self,
        user_input: str,
        current_state: Dict[str, Any],
    ) -> HTNIntegrationResult:
        """Crea un objetivo basico desde texto y lo procesa mediante HTN."""
        start_time = time.time()
        try:
            logger.info("Interpretando input del usuario")
            goal = self._create_goal_from_input(user_input, current_state)

            if not goal:
                return HTNIntegrationResult(
                    success=False,
                    goal_id="unknown",
                    goal_type="unknown",
                    decomposed_tasks=[],
                    execution_results=[],
                    total_execution_time=time.time() - start_time,
                    message="No se pudo crear objetivo desde el input",
                    error_message="Goal creation failed",
                    final_state=dict(current_state or {}),
                )

            return self.process_goal_through_htn(goal, current_state)

        except Exception as exc:
            logger.error("Error en flujo completo: " + str(exc))
            return HTNIntegrationResult(
                success=False,
                goal_id="unknown",
                goal_type="unknown",
                decomposed_tasks=[],
                execution_results=[],
                total_execution_time=time.time() - start_time,
                message="Error en flujo completo HTN",
                error_message=str(exc),
                final_state=dict(current_state or {}),
            )

    # ====================================================================
    # CREACION DE OBJETIVOS
    # ====================================================================

    def _create_goal_from_input(
        self,
        user_input: str,
        current_state: Dict[str, Any],
    ) -> Optional[Goal]:
        """Crea un objetivo compatible con los tipos usados por HTNManager."""
        try:
            text = str(user_input or "").strip()
            input_lower = text.lower()
            if not text:
                return None

            if any(word in input_lower for word in ("calibrar", "calibre", "calibration")):
                return Goal(
                    id=f"calibrate_applications_{int(time.time())}",
                    type="calibrate_applications",
                    target="applications",
                    description="Calibrar aplicaciones",
                    priority=1,
                )

            if any(word in input_lower for word in ("abrir", "open", "launch")):
                if "chrome" in input_lower or "navegador" in input_lower:
                    return Goal(
                        id=f"open_chrome_{int(time.time())}",
                        type="open_application",
                        target="chrome",
                        description="Abrir Google Chrome",
                        priority=1,
                    )
                if "youtube" in input_lower:
                    return Goal(
                        id=f"open_youtube_{int(time.time())}",
                        type="open_application",
                        target="youtube",
                        description="Abrir YouTube",
                        priority=1,
                    )

            if any(word in input_lower for word in ("navegar", "navigate", "ir a")):
                url_match = re.search(r"https?://[^\s]+", text)
                if url_match:
                    target = url_match.group(0).rstrip(".,);:!?\"")
                    return Goal(
                        id=f"navigate_{int(time.time())}",
                        type="navigate",
                        target=target,
                        description=f"Navegar a {target}",
                        priority=1,
                    )
                return Goal(
                    id=f"navigate_entity_{int(time.time())}",
                    type="navigate_stream",
                    target="default_streamer",
                    description="Navegar a stream predeterminado",
                    priority=1,
                )

            if any(word in input_lower for word in ("buscar", "search")):
                query_match = re.search(r"(?:buscar|search)(?:\s+en\s+google)?\s+(.+)", text, re.IGNORECASE)
                if query_match:
                    query = query_match.group(1).strip()
                    if query:
                        return Goal(
                            id=f"search_{int(time.time())}",
                            type="search",
                            target=query,
                            description=f"Buscar: {query}",
                            priority=1,
                        )

            return Goal(
                id=f"generic_goal_{int(time.time())}",
                type="generic",
                target=text,
                description=f"Objetivo gen\u00e9rico: {text}",
                priority=1,
            )

        except Exception as exc:
            logger.error("[HTN_INTEGRATION] Error creando objetivo: " + str(exc))
            return None

    # ====================================================================
    # ESTADO / MEMORIA
    # ====================================================================

    def _process_execution_results(
        self,
        goal: Goal,
        execution_result: Any,
        current_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Procesa el resultado, actualiza el estado y registra memoria."""
        new_state = dict(current_state or {})
        completed = execution_result.status == TaskStatus.COMPLETED

        state_key = f"{goal.type}_{'completed' if completed else 'failed'}"
        new_state[state_key] = True
        new_state["last_htn_goal"] = {
            "goal_id": goal.id,
            "goal_type": goal.type,
            "target": goal.target,
            "success": completed,
            "execution_time": getattr(execution_result, "execution_time", 0.0),
            "timestamp": time.time(),
        }

        result_value = getattr(execution_result, "result", None)
        if isinstance(result_value, dict):
            nested_state = result_value.get("new_state")
            if isinstance(nested_state, dict):
                new_state.update(nested_state)

        if completed:
            self._register_goal_completion(goal, execution_result)
        else:
            self._register_goal_failure(goal, execution_result)

        try:
            self.memory_manager.update_world_state("last_htn_result", new_state["last_htn_goal"])
        except Exception as exc:
            logger.debug("[HTN_INTEGRATION] No se pudo persistir last_htn_result: " + str(exc))

        return new_state

    def _register_goal_completion(self, goal: Goal, execution_result: Any) -> None:
        """Registra la finalizacion exitosa en la memoria conversacional."""
        self._register_goal_memory(goal, execution_result, success=True)

    def _register_goal_failure(self, goal: Goal, execution_result: Any) -> None:
        """Registra el fallo en la memoria conversacional."""
        self._register_goal_memory(goal, execution_result, success=False)

    def _register_goal_memory(
        self,
        goal: Goal,
        execution_result: Any,
        *,
        success: bool,
    ) -> None:
        try:
            result_value = getattr(execution_result, "result", None)
            error_message = getattr(execution_result, "error_message", None)
            execution_time = float(getattr(execution_result, "execution_time", 0.0) or 0.0)
            context = {
                "goal_id": goal.id,
                "goal_type": goal.type,
                "target": goal.target,
                "execution_details": result_value,
                "error_message": error_message,
                "timestamp": time.time(),
            }

            self.memory_manager.add_conversational_memory(
                message=goal.description,
                response=(
                    f"Objetivo completado: {goal.description}"
                    if success
                    else f"Objetivo fallido: {goal.description}"
                ),
                intent=goal.type,
                entities=[],
                context=context,
                success=success,
                execution_time=execution_time,
            )
        except Exception as exc:
            logger.error("[HTN_INTEGRATION] Error registrando resultado del objetivo: " + str(exc))

    # ====================================================================
    # SERIALIZACION / ESTADISTICAS
    # ====================================================================

    @staticmethod
    def _serialize_task(task: Any) -> Dict[str, Any]:
        status = getattr(task, "status", None)
        return {
            "id": getattr(task, "id", ""),
            "name": getattr(task, "name", ""),
            "description": getattr(task, "description", ""),
            "status": getattr(status, "value", status),
            "parent": getattr(task, "parent", None),
            "children": list(getattr(task, "children", []) or []),
            "dependencies": list(getattr(task, "dependencies", []) or []),
        }

    @staticmethod
    def _serialize_execution_result(result: Any) -> Dict[str, Any]:
        status = getattr(result, "status", None)
        return {
            "task_id": getattr(result, "task_id", ""),
            "status": getattr(status, "value", status),
            "execution_time": float(getattr(result, "execution_time", 0.0) or 0.0),
            "success": status == TaskStatus.COMPLETED,
            "error_message": getattr(result, "error_message", None),
            "result": getattr(result, "result", None),
        }

    def _record_integration(self, execution_time: float, success: bool) -> None:
        self.last_execution_time = execution_time
        self.total_integrations += 1
        if success:
            self.successful_integrations += 1

    # ====================================================================
    # API PUBLICA
    # ====================================================================

    def get_integration_statistics(self) -> Dict[str, Any]:
        """Obtiene estadisticas de la integracion HTN-Brain."""
        success_rate = (
            self.successful_integrations / self.total_integrations
            if self.total_integrations > 0
            else 0.0
        )

        try:
            htn_stats = self.htn_manager.get_execution_statistics()
        except Exception as exc:
            logger.debug("Error obteniendo stats HTN: " + str(exc))
            htn_stats = {}

        try:
            executor_stats = self.task_executor.get_execution_statistics()
        except Exception as exc:
            logger.debug("Error obteniendo stats Executor: " + str(exc))
            executor_stats = {}

        return {
            "integration_enabled": self.is_enabled,
            "total_integrations": self.total_integrations,
            "successful_integrations": self.successful_integrations,
            "success_rate": success_rate,
            "last_execution_time": self.last_execution_time,
            "htn_manager_stats": htn_stats,
            "task_executor_stats": executor_stats,
        }

    def enable_integration(self, enabled: bool = True) -> None:
        """Habilita o deshabilita la integracion HTN."""
        self.is_enabled = bool(enabled)
        logger.info("Integracion " + ("habilitada" if self.is_enabled else "deshabilitada"))

    def get_htn_insights(self) -> Dict[str, Any]:
        """Obtiene informacion agregada del sistema HTN."""
        try:
            htn_insights = self.htn_manager.get_execution_statistics()
        except Exception as exc:
            htn_insights = {"error": str(exc)}

        try:
            executor_insights = self.task_executor.get_execution_statistics()
        except Exception as exc:
            executor_insights = {"error": str(exc)}

        return {
            "htn_overview": htn_insights,
            "executor_overview": executor_insights,
            "integration_overview": self.get_integration_statistics(),
            "system_health": {
                "htn_available": not bool(isinstance(htn_insights, dict) and htn_insights.get("error")),
                "executor_available": not bool(isinstance(executor_insights, dict) and executor_insights.get("error")),
                "integration_enabled": self.is_enabled,
            },
        }


_htn_integration: Optional[HTNBrainIntegration] = None


def get_htn_integration() -> HTNBrainIntegration:
    """Obtiene la instancia global de la integracion HTN-Brain."""
    global _htn_integration
    if _htn_integration is None:
        _htn_integration = HTNBrainIntegration()
    return _htn_integration


__all__ = [
    "HTNBrainIntegration",
    "HTNIntegrationResult",
    "get_htn_integration",
]
