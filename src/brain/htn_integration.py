"""
Integración de HTN con el Brain de JARVIS - FASE 4.

Integra la descomposición jerárquica de objetivos con HTNManager y
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
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class HTNIntegrationResult:
    """Resultado de la integración HTN-Brain."""

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
    """Integra interpretación de objetivos, HTN y ejecución de tareas."""

    def __init__(self) -> None:
        self.htn_manager = get_htn_manager()
        self.task_executor = get_task_executor()
        self.application_integrator = get_application_knowledge_integrator()
        self.memory_manager = get_memory_manager()

        self.is_enabled = True
        self.last_execution_time = 0.0
        self.total_integrations = 0
        self.successful_integrations = 0

        logger._print_log("INFO", "Integración HTN-Brain inicializada", "htn_integration.py", "__init__", 54)

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
                message="Integración HTN deshabilitada",
                error_message="HTN integration is disabled",
                final_state=dict(current_state or {}),
            )

        start_time = time.time()
        logger._print_log("INFO", "[HTN_INTEGRATION] Procesando objetivo HTN: " + goal.id + " (" + goal.type + ")", "htn_integration.py", "process_goal_through_htn", 80)

        try:
            state = dict(current_state or {})

            logger._print_log("INFO", "Fase 1: Descomposición de objetivo", "htn_integration.py", "process_goal_through_htn", 87)
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
            logger._print_log("INFO", "Objetivo descompuesto en " + str(len(tasks)) + " tareas", "htn_integration.py", "execute_htn", 104)

            logger._print_log("INFO", "Fase 2: Ejecución de jerarquía", "htn_integration.py", "execute_htn", 106)
            execution_result = self.htn_manager.execute_goal_hierarchy(goal, state)
            execution_results = [self._serialize_execution_result(execution_result)]

            logger._print_log("INFO", "Fase 3: Procesamiento de resultados", "htn_integration.py", "execute_htn", 110)
            final_state = self._process_execution_results(
                goal,
                execution_result,
                state,
            )

            execution_time = time.time() - start_time
            completed = execution_result.status == TaskStatus.COMPLETED
            self._record_integration(execution_time, completed)

            message = (
                "Integración HTN completada exitosamente"
                if completed
                else "Integración HTN completada con fallo de ejecución"
            )
            logger._print_log("INFO", "Integración completada: " + execution_result.status.value + " (" + str(execution_time) + "s)", "htn_integration.py", "execute_htn", 126)

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
            logger._print_log("ERROR", "[HTN_INTEGRATION] Error en integración: " + str(exc), "htn_integration.py", "execute_htn", 147)
            return HTNIntegrationResult(
                success=False,
                goal_id=goal.id,
                goal_type=goal.type,
                decomposed_tasks=[],
                execution_results=[],
                total_execution_time=execution_time,
                message="Error en integración HTN",
                error_message=str(exc),
                final_state=dict(current_state or {}),
            )

    def create_and_execute_htn_goal(
        self,
        user_input: str,
        current_state: Dict[str, Any],
    ) -> HTNIntegrationResult:
        """Crea un objetivo básico desde texto y lo procesa mediante HTN."""
        start_time = time.time()
        try:
            logger._print_log("INFO", "Interpretando input del usuario", "htn_integration.py", "interpret_user_input", 168)
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
            logger._print_log("ERROR", "Error en flujo completo: " + str(exc), "htn_integration.py", "interpret_user_input", 187)
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
    # CREACIÓN DE OBJETIVOS
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
                description=f"Objetivo genérico: {text}",
                priority=1,
            )

        except Exception as exc:
            logger._print_log("ERROR", "[HTN_INTEGRATION] Error creando objetivo: " + str(exc), "htn_integration.py", "create_goal_from_input", 284)
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
            logger._print_log("DEBUG", "[HTN_INTEGRATION] No se pudo persistir last_htn_result: " + str(exc), "htn_integration.py", "persist_htn_result", 326)

        return new_state

    def _register_goal_completion(self, goal: Goal, execution_result: Any) -> None:
        """Registra la finalización exitosa en la memoria conversacional."""
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
            logger._print_log("ERROR", "[HTN_INTEGRATION] Error registrando resultado del objetivo: " + str(exc), "htn_integration.py", "persist_htn_result", 372)

    # ====================================================================
    # SERIALIZACIÓN / ESTADÍSTICAS
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
    # API PÚBLICA
    # ====================================================================

    def get_integration_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas de la integración HTN-Brain."""
        success_rate = (
            self.successful_integrations / self.total_integrations
            if self.total_integrations > 0
            else 0.0
        )

        try:
            htn_stats = self.htn_manager.get_execution_statistics()
        except Exception as exc:
            logger._print_log("DEBUG", "Error obteniendo stats HTN: " + str(exc), "htn_integration.py", "get_htn_stats", 424)
            htn_stats = {}

        try:
            executor_stats = self.task_executor.get_execution_statistics()
        except Exception as exc:
            logger._print_log("DEBUG", "Error obteniendo stats Executor: " + str(exc), "htn_integration.py", "get_executor_stats", 430)
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
        """Habilita o deshabilita la integración HTN."""
        self.is_enabled = bool(enabled)
        logger._print_log("INFO", "Integración " + ("habilitada" if self.is_enabled else "deshabilitada"), "htn_integration.py", "is_htn_integration_enabled", 446)

    def get_htn_insights(self) -> Dict[str, Any]:
        """Obtiene información agregada del sistema HTN."""
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
    """Obtiene la instancia global de la integración HTN-Brain."""
    global _htn_integration
    if _htn_integration is None:
        _htn_integration = HTNBrainIntegration()
    return _htn_integration


__all__ = [
    "HTNBrainIntegration",
    "HTNIntegrationResult",
    "get_htn_integration",
]
