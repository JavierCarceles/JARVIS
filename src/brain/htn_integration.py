"""
Integracion de HTN con el Brain de JARVIS - FASE 4.

Integra la descomposicion jerarquica de objetivos con HTNManager y
TaskExecutor, manteniendo compatibilidad con el Brain existente.
"""

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.hands.planner.node import Goal, TaskStatus, build_goal, new_goal_id, validate_goal
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
                # 4.5.3.3: motivo real de la falta de metodo (4.3.2.3).
                failure = getattr(self.htn_manager, "last_decomposition_failure", None) or {}
                if callable(getattr(goal, "record_result", None)):
                    goal.record_result(False, error=failure.get("message") or "Goal decomposition failed")
                return HTNIntegrationResult(
                    success=False,
                    goal_id=goal.id,
                    goal_type=goal.type,
                    decomposed_tasks=[],
                    execution_results=[{"decomposition_failure": dict(failure)}] if failure else [],
                    total_execution_time=execution_time,
                    message="No se pudo descomponer el objetivo en tareas",
                    error_message=(
                        "Goal decomposition failed: %s" % failure["message"]
                        if failure.get("message") else "Goal decomposition failed"
                    ),
                    final_state=state,
                )

            logger.info("Objetivo descompuesto en " + str(len(tasks)) + " tareas")

            logger.info("Fase 2: Ejecucion de jerarquia")
            # 4.5.3.2: se ejecutan exactamente las Tasks descompuestas (antes
            # execute_goal_hierarchy volvia a descomponer el Goal).
            execution_result = self.htn_manager.execute_goal_hierarchy(goal, state, tasks=tasks)
            # Serializadas despues de ejecutar: reflejan el estado final de cada Task.
            decomposed_tasks = [self._serialize_task(task) for task in tasks]
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

    @staticmethod
    def _make_goal(
        goal_type: str,
        target: Any,
        description: str,
        legacy_id: str,
    ) -> Goal:
        """
        Crea el Goal con el constructor validado (4.1.3.1, origen ``text``).
        Si no cumple el contrato se mantiene la construccion legacy, marcada
        con ``source="legacy_fallback"`` y sus errores (4.1.3.3).
        """
        # Se conserva el prefijo historico del ID (``open_chrome``,
        # ``generic_goal``...) con el sufijo unico de ``new_goal_id``.
        prefix = legacy_id.rsplit("_", 1)[0] if "_" in legacy_id else goal_type
        goal = build_goal(
            goal_type, target, description, priority=1, source="text",
            goal_id=new_goal_id(prefix),
        )
        if goal is not None:
            return goal
        goal = Goal(
            id=legacy_id,
            type=goal_type,
            target=target,
            description=description,
            priority=1,
        )
        goal.metadata["source"] = "legacy_fallback"
        goal.metadata["validation_errors"] = validate_goal(goal)
        return goal

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
                return self._make_goal(
                    "calibrate_applications",
                    "applications",
                    "Calibrar aplicaciones",
                    legacy_id=f"calibrate_applications_{int(time.time())}",
                )

            if any(word in input_lower for word in ("abrir", "abre ", "open", "launch")):
                if "chrome" in input_lower or "navegador" in input_lower:
                    return self._make_goal(
                        "open_application",
                        "chrome",
                        "Abrir Google Chrome",
                        legacy_id=f"open_chrome_{int(time.time())}",
                    )
                if "youtube" in input_lower:
                    return self._make_goal(
                        "open_application",
                        "youtube",
                        "Abrir YouTube",
                        legacy_id=f"open_youtube_{int(time.time())}",
                    )
                # Cualquier otra aplicacion: el nombre se resuelve despues por el
                # flujo unico (catalogo -> resolucion local -> preflight); aqui no
                # se decide si existe ni se lanza nada.
                app_match = re.search(
                    r"\b(?:abrir|abre|open|launch)\s+(?:la\s+|el\s+)?"
                    r"(?:aplicaci(?:o|\u00f3)n\s+|app\s+|programa\s+)?(.+)",
                    text,
                    re.IGNORECASE,
                )
                if app_match:
                    app_target = app_match.group(1).strip().rstrip(".,;:!?\"'")
                    if app_target:
                        return self._make_goal(
                            "open_application",
                            app_target,
                            f"Abrir aplicaci\u00f3n {app_target}",
                            legacy_id=f"open_application_{int(time.time())}",
                        )

            if any(word in input_lower for word in ("navegar", "navigate", "ir a")):
                url_match = re.search(r"https?://[^\s]+", text)
                if url_match:
                    target = url_match.group(0).rstrip(".,);:!?\"")
                    return self._make_goal(
                        "navigate",
                        target,
                        f"Navegar a {target}",
                        legacy_id=f"navigate_{int(time.time())}",
                    )
                return self._make_goal(
                    "navigate_stream",
                    "default_streamer",
                    "Navegar a stream predeterminado",
                    legacy_id=f"navigate_entity_{int(time.time())}",
                )

            if any(word in input_lower for word in ("buscar", "search")):
                query_match = re.search(r"(?:buscar|search)(?:\s+en\s+google)?\s+(.+)", text, re.IGNORECASE)
                if query_match:
                    query = query_match.group(1).strip()
                    if query:
                        return self._make_goal(
                            "search",
                            query,
                            f"Buscar: {query}",
                            legacy_id=f"search_{int(time.time())}",
                        )

            return self._make_goal(
                "generic",
                text,
                f"Objetivo gen\u00e9rico: {text}",
                legacy_id=f"generic_goal_{int(time.time())}",
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
        base_state = dict(current_state or {})
        new_state = dict(base_state)
        completed = execution_result.status == TaskStatus.COMPLETED

        # 4.6.2.1-4.6.2.2: solo se aplican los cambios confirmados. El
        # ``new_state`` de HTNManager acumula unicamente el estado devuelto por
        # hojas COMPLETED; la hoja que falla no aporta cambios. Antes, ante un
        # fallo se descartaban tambien los cambios ya confirmados.
        result_value = getattr(execution_result, "result", None)
        confirmed_state = getattr(execution_result, "new_state", None)
        if not isinstance(confirmed_state, dict) and isinstance(result_value, dict):
            confirmed_state = result_value.get("new_state")
        if isinstance(confirmed_state, dict):
            new_state.update(confirmed_state)
        state_changes: List[str] = []
        for key, value in new_state.items():
            if str(key).startswith("_"):
                continue
            try:
                changed = key not in base_state or base_state[key] != value
            except Exception:
                changed = True
            if changed:
                state_changes.append(str(key))

        state_key = f"{goal.type}_{'completed' if completed else 'failed'}"
        new_state[state_key] = True
        payload = result_value if isinstance(result_value, dict) else {}
        # 4.6.2.3: registro del resultado con la Task responsable y los
        # cambios de estado aplicados.
        new_state["last_htn_goal"] = {
            "goal_id": goal.id,
            "goal_type": goal.type,
            "target": goal.target,
            "success": completed,
            "execution_time": getattr(execution_result, "execution_time", 0.0),
            "failed_task_id": payload.get("failed_task_id"),
            "error_message": getattr(execution_result, "error_message", None),
            "state_changes": sorted(state_changes),
            "state_source": base_state.get("_htn_state_source"),
            "timestamp": time.time(),
        }

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
