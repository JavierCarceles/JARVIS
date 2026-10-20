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

import ast
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.hands import applications_core as applications
from src.hands import keyboard, mouse
from src.hands.action_registry import ActionInfo, ActionRegistry, get_action_registry
# from hands.planner import Planner, Goal  # Temporalmente comentado para evitar importación circular
from src.utils.config import get_predictive_config, get_timeout_config
from src.utils.logger import get_logger
from src.memory.storage import get_memory_manager

logger = get_logger(__name__)

# Importar sistema de aprendizaje (FASE 18)
try:
    from src.hands.planner.learning_system import LearningSystem
    LEARNING_AVAILABLE = True
except ImportError:
    LEARNING_AVAILABLE = False
    logger._print_log("WARNING", "Sistema de aprendizaje no disponible, FASE 18 parcialmente deshabilitada", "executor.py", "__init__", 43)


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
    alternatives_tried: List[str] = None
    
    def __post_init__(self):
        if self.alternatives_tried is None:
            self.alternatives_tried = []


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
        """Actualiza el estado con nueva información."""
        for key, value in update_data.items():
            if key in self.__dict__:
                if isinstance(self.__dict__[key], dict) and isinstance(value, dict):
                    self.__dict__[key].update(value)
                else:
                    self.__dict__[key] = value
        self.timestamp = time.time()


class Executor:
    """Ejecutor mejorado con soporte para planificación jerárquica y replanificación."""

    _COMMAND_PATTERN = re.compile(
        r"\[CMD:\s*([a-zA-Z0-9_]+)(?:\((.*?)\))?\]",
        flags=re.DOTALL,
    )

    def __init__(self, action_registry: Optional[ActionRegistry] = None):
        """Inicializa el ejecutor mejorado."""
        self.action_registry = action_registry or get_action_registry()
        self.memory_manager = get_memory_manager()

        self.modules = {
            "apps": applications,
            "key": keyboard,
            "mouse": mouse,
        }

        self.timeout_config = get_timeout_config()
        self.predictive_config = get_predictive_config()
        self.last_predictions: List[Dict[str, Any]] = []
        
        # Estado del mundo
        self.current_state = self._initialize_state()
        
        # Ejecuciones activas
        self.active_executions: Dict[str, ExecutionResult] = {}
        
        # Planificador integrado
        self.planner = Planner(self)
        
        # Sistema de aprendizaje (FASE 18)
        self.learning_system = LearningSystem() if LEARNING_AVAILABLE else None
        
        logger._print_log("info", r"Ejecutor mejorado inicializado [file:executor.py, method:__init__, line:129]", "executor.py", "method", 129)
        logger._print_log("info", f"Total de {len(actions, "executor.py", "method", 130)} acciones [file:executor.py, method:__init__, line:130]")
        if LEARNING_AVAILABLE:
            logger._print_log("info", r"Sistema de aprendizaje FASE 18 habilitado [file:executor.py, method:__init__, line:135]", "executor.py", "method", 132)

    # Instancia global del ejecutor
    _executor_instance = None

    def get_executor() -> Executor:
        """Obtiene la instancia global del ejecutor."""
        global _executor_instance
        if _executor_instance is None:
            _executor_instance = Executor()
        return _executor_instance

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
        timeout_per_node: Optional[float] = None
    ) -> ExecutionResult:
        """
        Ejecuta un plan completo (lista de nodos) con replanificación.
        
        Args:
            plan: Lista de nodos a ejecutar
            plan_id: Identificador del plan
            max_retries: Máximo de reintentos por nodo
            timeout_per_node: Timeout por nodo en segundos
            
        Returns:
            Resultado completo de la ejecución del plan
        """
        if not plan:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Plan vacío",
                plan_id=plan_id
            )
        
        logger._print_log("info", f"Plan con {len(plan.nodes, "executor.py", "method", 185)} nodos [file:executor.py, method:execute_plan, line:185]")
        
        plan_result = ExecutionResult(
            status=ExecutionStatus.PENDING,
            plan_id=plan_id
        )
        
        for i, node in enumerate(plan):
            node_id = node.get("id", f"node_{i}")
            node_result = self._execute_node(
                node,
                node_id,
                max_retries,
                timeout_per_node
            )
            
            plan_result.execution_time += node_result.execution_time
            
            if node_result.status == ExecutionStatus.SUCCESS:
                # Actualizar estado del mundo
                self._update_world_state(node, node_result)
                plan_result.last_actions.append(node_id)
            else:
                # Nodo falló, intentar alternativa o fallar completo
                alternative_result = self._try_alternative(node, node_result)
                if alternative_result.status == ExecutionStatus.SUCCESS:
                    plan_result.execution_time += alternative_result.execution_time
                    plan_result.alternatives_tried.append(alternative_result.node_id or "unknown")
                else:
                    plan_result.status = ExecutionStatus.FAILED
                    plan_result.error = f"Nodo {node_id} falló sin alternativa"
                    plan_result.result = node_result
                    break
        
        if plan_result.status == ExecutionStatus.PENDING:
            plan_result.status = ExecutionStatus.SUCCESS
        
        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
        return plan_result

    def _execute_node(
        self,
        node: Dict[str, Any],
        node_id: str,
        max_retries: int,
        timeout: Optional[float]
    ) -> ExecutionResult:
        """Ejecuta un nodo individual con reintentos y replanificación (FASE 9)."""
        
        start_time = time.time()
        result = ExecutionResult(
            status=ExecutionStatus.PENDING,
            node_id=node_id
        )
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                result.status = ExecutionStatus.RETRYING
                result.retries = attempt
                logger._print_log("info", f"Intento {attempt} de {max_retries} [file:executor.py, method:execute_node, line:244]", "executor.py", "method", 244)
            
            try:
                # Verificar precondiciones
                if not self._check_node_preconditions(node):
                    result.status = ExecutionStatus.FAILED
                    result.error = "Precondiciones no satisfechas"
                    break
                
                # Ejecutar el nodo
                result.status = ExecutionStatus.RUNNING
                node_result = self._execute_node_action(node, timeout)
                
                if node_result is not None:
                    # Verificar éxito de la ejecución (FASE 9 - comprobación del estado)
                    success_verified = self._verify_node_success(node, node_result)
                    
                    if success_verified:
                        result.result = node_result
                        result.status = ExecutionStatus.SUCCESS
                        break
                    else:
                        # La ejecución falló la verificación, intentar alternativa
                        logger._print_log("warning", r"[EXECUTOR] Nodo %s ejecutado pero verificado fallida [file:executor.py, method:_execute_node, line:267]", "executor.py", "method", 267)
                        alternative_result = self._try_alternative(node, result)
                        if alternative_result.status == ExecutionStatus.SUCCESS:
                            result = alternative_result
                            break
                        else:
                            result.status = ExecutionStatus.FAILED
                            result.error = "Verificación de éxito fallada sin alternativa"
                else:
                    result.status = ExecutionStatus.FAILED
                    result.error = "Ejecución devolvió None"
                    
            except Exception as exc:
                logger._print_log("info", f"Error en ejecución: {str(exc, "executor.py", "method", 280)} [file:executor.py, method:execute_node, line:280]")
                result.error = str(exc)
                if attempt == max_retries:
                    result.status = ExecutionStatus.FAILED
                    break
            
            # Si no es el último intento, esperar antes de reintentar
            if attempt < max_retries:
                time.sleep(1)
        
        result.execution_time = time.time() - start_time
        
        # Registrar ejecución del nodo en sistema de aprendizaje (FASE 18)
        if self.learning_system and result.status != ExecutionStatus.PENDING:
            self.learning_system.record_node_execution(
                node_id=node_id,
                success=result.status == ExecutionStatus.SUCCESS,
                execution_time=result.execution_time,
                estimated_cost=node.get("cost", 1.0),
                context={
                    "attempts": result.retries + 1,
                    "alternatives_tried": result.alternatives_tried
                },
                application=node.get("application")
            )
        
        return result

    def _verify_node_success(self, node: Dict[str, Any], result: Any) -> bool:
        """Verifica si la ejecución de un nodo fue exitosa (FASE 9)."""
        
        # Si hay un verificador específico en el nodo, usarlo
        if "success_checker" in node:
            try:
                checker = node["success_checker"]
                if callable(checker):
                    return checker(result)
            except Exception as exc:
                logger._print_log("warning", r"[EXECUTOR] Error en verificador personalizado: %s [file:executor.py, method:_verify_node_success, line:318]", "executor.py", "method", 318)
        
        # Verificación basada en efectos esperados
        expected_effects = node.get("effects", [])
        if not expected_effects:
            return True  # Sin efectos esperados, asumir éxito
        
        # Verificar efectos en el estado actual
        for effect in expected_effects:
            if effect == "app_open":
                app_name = node.get("application")
                if app_name and not self.current_state.application_states.get(app_name, {}).get("open", False):
                    logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
                    return False
            
            elif effect == "app_active":
                app_name = node.get("application")
                if app_name and not self.current_state.application_states.get(app_name, {}).get("active", False):
                    logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
                    return False
            
            elif effect == "address_bar_focused":
                ui_element = node.get("ui_element")
                if ui_element and not self.current_state.ui_elements.get(ui_element, {}).get("focused", False):
                    logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
                    return False
            
            elif effect == "url_typed":
                app_name = node.get("application")
                if app_name and not self.current_state.application_states.get(app_name, {}).get("url_typed", False):
                    logger._print_log("warning", r"[EXECUTOR] Efecto url_typed no verificado para %s [file:executor.py, method:_verify_node_success, line:348]", "executor.py", "method", 348)
                    return False
            
            elif effect == "destination_loaded":
                app_name = node.get("application")
                if app_name and not self.current_state.application_states.get(app_name, {}).get("destination_loaded", False):
                    logger._print_log("warning", r"[EXECUTOR] Efecto destination_loaded no verificado para %s [file:executor.py, method:_verify_node_success, line:354]", "executor.py", "method", 354)
                    return False
            
            # Efecto genérico: verificar que el resultado no es None ni un error
            elif effect == "success":
                if result is None:
                    return False
                if isinstance(result, dict) and result.get("error"):
                    return False
        
        # Si todos los efectos se verificaron, asumir éxito
        return True

    def _replan_after_failure(self, 
                            plan: List[Dict[str, Any]], 
                            failed_node_index: int, 
                            current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Realiza replanificación después de un fallo en un nodo (FASE 9).
        
        Args:
            plan: Plan original que falló
            failed_node_index: Índice del nodo que falló
            current_state: Estado actualizado después del fallo
            
        Returns:
            Nuevo plan o el plan original si no hay alternativas
        """
        
        if failed_node_index >= len(plan):
            logger._print_log("error", r"[EXECUTOR] Índice de nodo fallido fuera de rango [file:executor.py, method:_replan_after_failure, line:384]", "executor.py", "method", 384)
            return plan
        
        failed_node = plan[failed_node_index]
        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
        
        # Intentar encontrar alternativa para el nodo fallido
        alternatives = failed_node.get("alternatives", [])
        if not alternatives:
            logger._print_log("info", r"[EXECUTOR] No hay alternativas definidas para el nodo fallido [file:executor.py, method:replan_after_failure, line:393]", "executor.py", "method", 393)
            return plan
        
        # Buscar nodos alternativos que proporcionen la misma capacidad
        alternative_nodes = self._find_alternative_nodes(failed_node, current_state)
        
        if not alternative_nodes:
            logger._print_log("warning", r"No se encontraron nodos alternativos [file:executor.py, method:_try_alternative, line:400]", "executor.py", "method", 400)
            return plan
        
        # Crear nuevo plan con la primera alternativa encontrada
        new_plan = plan.copy()
        alternative_node = alternative_nodes[0]  # Usar la primera alternativa
        
        # Reemplazar el nodo fallido con la alternativa
        new_plan[failed_node_index] = alternative_node
        
        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
        
        # Registrar replanificación en sistema de aprendizaje (FASE 18)
        if self.learning_system:
            original_plan_ids = [node.get("id", f"node_{i}") for i, node in enumerate(plan)]
            new_plan_ids = [node.get("id", f"node_{i}") for i, node in enumerate(new_plan)]
            self.learning_system.record_replanification(
                original_plan=original_plan_ids,
                new_plan=new_plan_ids,
                reason=f"failed_node_{failed_node['id']}",
                success=True,
                execution_time=0.1  # Tiempo estimado de replanificación
            )
        
        return new_plan

    def _find_alternative_nodes(self, failed_node: Dict[str, Any], current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Encuentra nodos alternativos que proporcionen la misma capacidad que el nodo fallido."""
        
        alternatives = []
        action_name = failed_node.get("action", "")
        capability = self._extract_capability_from_action(action_name)
        
        # Obtener todas las acciones disponibles
        available_actions = self.action_registry.get_all_actions()
        
        # Buscar acciones que proporcionen la misma capacidad
        for action_name, action_info in available_actions.items():
            if action_name == failed_node.get("action"):
                continue  # Saltar la acción original
            
            # Verificar si la acción alternativa puede ejecutarse en el estado actual
            if action_info.matches_preconditions(current_state):
                # Verificar si proporciona la misma capacidad
                if self._action_provides_capability(action_info, capability):
                    alternative_node = {
                        "id": f"alt_{action_name}",
                        "name": action_info.description,
                        "action": action_name,
                        "parameters": failed_node.get("parameters", {}),
                        "preconditions": action_info.preconditions,
                        "effects": action_info.effects,
                        "cost": action_info.cost * 0.9,  # Ligeramente más barata
                        "application": action_info.application,
                        "ui_element": action_info.requires_ui_element,
                        "alternatives": []  # No recursivo
                    }
                    alternatives.append(alternative_node)
        
        # Limitar a 3 alternativas para no sobrecargar
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
        """Verifica si una acción proporciona una capacidad específica."""
        
        # Por nombre de acción
        if capability in action_info.name.lower():
            return True
        
        # Por tipo de acción
        if action_info.action_type.value == capability:
            return True
        
        # Por categoría
        if capability in action_info.category.lower():
            return True
        
        # Por capacidades declaradas
        if hasattr(action_info, 'capabilities') and capability in action_info.capabilities:
            return True
        
        return False

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

    def execute_plan_with_replan(self, 
                               plan: List[Dict[str, Any]], 
                               goal: Optional[Dict[str, Any]] = None,
                               max_replan_attempts: int = 2) -> Dict[str, Any]:
        """
        Ejecuta un plan completo con replanificación dinámica (FASE 9).
        
        Args:
            plan: Plan a ejecutar
            goal: Objetivo original (para verificación final)
            max_replan_attempts: Máximo de intentos de replanificación
            
        Returns:
            Resultado completo de la ejecución
        """
        
        if not plan:
            return {
                "status": "failed",
                "error": "Plan vacío",
                "execution_time": 0.0,
                "replan_attempts": 0
            }
        
        logger._print_log("info", f"Plan con {len(plan.nodes, "executor.py", "method", 185)} nodos [file:executor.py, method:execute_plan_with_replan, line:543]")
        
        start_time = time.time()
        successful_nodes = []
        failed_nodes = []
        replan_attempts = 0
        
        for i, node in enumerate(plan):
            node_id = node.get("id", f"node_{i}")
            
            # Ejecutar nodo con verificación de éxito
            node_result = self._execute_node(
                node,
                node_id,
                max_retries=1,  # Reducir reintentos ya que tenemos replanificación
                timeout_per_node=30.0
            )
            
            if node_result.status == ExecutionStatus.SUCCESS:
                # Actualizar estado del mundo
                self._update_world_state(node, node_result)
                successful_nodes.append(node_id)
                
                # Verificar si el objetivo se alcanzó
                if goal and self._goal_achieved(goal, self.current_state.__dict__):
                    logger._print_log("info", r"[EXECUTOR] Objetivo alcanzado durante ejecución [file:executor.py, method:execute_plan_with_replan, line:568]", "executor.py", "method", 568)
                    break
                    
            else:
                # Nodo falló, intentar replanificación
                failed_nodes.append((node_id, node_result.error))
                
                if replan_attempts < max_replan_attempts and self._should_replan(plan, i):
                    logger._print_log("info", f"Intento de replanificación {replan_attempts} [file:executor.py, method:execute_plan_with_replan, line:576]", "executor.py", "method", 576)
                    
                    # Actualizar estado antes de replanificar
                    self._update_world_state_after_failure(node, node_result)
                    
                    # Replanificar
                    new_plan = self._replan_after_failure(plan, i, self.current_state.__dict__)
                    
                    if new_plan != plan:  # Si hay cambios en el plan
                        plan = new_plan
                        replan_attempts += 1
                        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
                        continue  # Reintentar el mismo índice con el nuevo plan
                    else:
                        logger._print_log("warning", r"[EXECUTOR] Replanificación no generó cambios, continuando [file:executor.py, method:execute_plan_with_replan, line:590]", "executor.py", "method", 590)
                else:
                    logger._print_log("error", r"[EXECUTOR] Nodo %s falló sin más intentos de replanificación [file:executor.py, method:execute_plan_with_replan, line:592]", "executor.py", "method", 592)
                    break
        
        execution_time = time.time() - start_time
        
        # Registrar ejecución del plan en sistema de aprendizaje (FASE 18)
        if self.learning_system:
            plan_success = len(successful_nodes) == len(plan)
            self.learning_system.record_plan_execution(
                plan_id=f"plan_{int(start_time)}",
                goal_id="unknown",  # Podría pasarse como parámetro
                plan=[node.get("id", f"node_{i}") for i, node in enumerate(plan)],
                success=plan_success,
                execution_time=execution_time,
                total_estimated_cost=sum(node.get("cost", 1.0) for node in plan),
                context={
                    "successful_nodes": successful_nodes,
                    "failed_nodes": failed_nodes,
                    "replan_attempts": replan_attempts
                }
            )
        
        return {
            "status": "success" if successful_nodes else "failed",
            "successful_nodes": successful_nodes,
            "failed_nodes": failed_nodes,
            "execution_time": execution_time,
            "replan_attempts": replan_attempts,
            "total_nodes": len(plan),
            "world_state": self.current_state.__dict__
        }

    def _update_world_state_after_failure(self, node: Dict[str, Any], result: ExecutionResult) -> None:
        """Actualiza estado del mundo después de un fallo (FASE 9)."""
        
        # Marcar que la acción falló para evitar intentos redundantes
        app_name = node.get("application")
        if app_name and app_name in self.current_state.application_states:
            self.current_state.application_states[app_name]["last_action_failed"] = True
        
        # Actualizar timestamp
        self.current_state.timestamp = time.time()
        
        # Guardar información de fallo para aprendizaje
        failure_data = {
            "failure_info": {
                "node_id": result.node_id,
                "error": result.error,
                "timestamp": result.execution_time,
                "status": result.status.value
            },
            "world_state": {
                "application_states": self.current_state.application_states,
                "ui_elements": self.current_state.ui_elements,
                "timestamp": self.current_state.timestamp
            }
        }
        
        self.memory_manager.update_world_state(failure_data)

    def _goal_achieved(self, goal: Dict[str, Any], current_state: Dict[str, Any]) -> bool:
        """Verifica si un objetivo ha sido alcanzado en el estado actual."""
        
        goal_type = goal.get("type")
        target = goal.get("target")
        
        if goal_type == "navigate":
            if isinstance(target, str):
                return current_state.get("current_url", "") == target
            elif isinstance(target, dict):
                return current_state.get("current_url", "") == target.get("url", "")
        
        elif goal_type == "open_application":
            app_key = f"{target}_open"
            return current_state.get(app_key, False)
        
        elif goal_type == "close_application":
            app_key = f"{target}_open"
            return not current_state.get(app_key, True)
        
        return False

    def _execute_node_action(self, node: Dict[str, Any], timeout: Optional[float]) -> Any:
        """Ejecuta la acción específica de un nodo."""
        
        action_name = node.get("action")
        if not action_name:
            raise ValueError("Nodo sin acción definida")
        
        parameters = node.get("parameters", {})
        verify = node.get("verify", True)
        
        # Usar el método existente de ejecución de acciones
        return self.execute_action(
            action_name,
            parameters,
            state=self.current_state,
            verify=verify,
            timeout=timeout
        )

    def _check_node_preconditions(self, node: Dict[str, Any]) -> bool:
        """Verifica si las precondiciones de un nodo se cumplen."""
        preconditions = node.get("preconditions", [])
        
        for precondition in preconditions:
            if not self._evaluate_condition(precondition):
                logger._print_log("warning", r"[EXECUTOR] Precondición no cumplida: %s [file:executor.py, method:_check_node_preconditions, line:699]", "executor.py", "method", 699)
                return False
        
        return True

    def _evaluate_condition(self, condition: str) -> bool:
        """Evalúa una condición simple contra el estado actual."""
        # Implementar evaluación de condiciones basada en estado actual
        # Por ahora, implementar algunas condiciones básicas
        condition_lower = condition.lower()
        
        if condition_lower.startswith("app_"):
            app_name = condition_lower[4:]
            return app_name in self.current_state.application_states
        
        if condition_lower.startswith("ui_"):
            element_name = condition_lower[3:]
            return element_name in self.current_state.ui_elements
        
        # Si no reconocemos la condición, asumir que es cierta
        return True

    def _try_alternative(self, node: Dict[str, Any], failed_result: ExecutionResult) -> ExecutionResult:
        """Intenta una alternativa cuando un nodo falla (FASE 9)."""
        
        alternatives = node.get("alternatives", [])
        if not alternatives:
            logger._print_log("info", "No hay alternativas para replanificación [file:executor.py, method:replan_after_failure, line:726]", "executor.py", "method", 726)
            return failed_result
        
        logger._print_log("info", f"Replanificando con {len(alternatives, "executor.py", "method", 729)} alternativas [file:executor.py, method:replan_after_failure, line:729]")
        
        for alternative_action in alternatives:
            try:
                logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
                
                # Crear nodo de alternativa
                alternative_node = {
                    "action": alternative_action,
                    "parameters": node.get("parameters", {}),
                    "preconditions": node.get("preconditions", []),
                    "effects": node.get("effects", []),
                    "application": node.get("application"),
                    "ui_element": node.get("ui_element"),
                    "cost": node.get("cost", 1.0) * 0.8  # Alternativas suelen ser más rápidas
                }
                
                # Ejecutar alternativa
                alternative_result = self._execute_node_action(alternative_node, timeout=None)
                
                if alternative_result is not None:
                    # Verificar éxito de la alternativa
                    alternative_success = self._verify_node_success(alternative_node, alternative_result)
                    
                    if alternative_success:
                        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
                        return ExecutionResult(
                            status=ExecutionStatus.SUCCESS,
                            result=alternative_result,
                            execution_time=time.time() - failed_result.execution_time,
                            node_id=f"alternative_{alternative_action}",
                            alternatives_tried=[alternative_action]
                        )
                    else:
                        logger._print_log("warning", r"[EXECUTOR] Alternativa %s ejecutada pero falló verificación [file:executor.py, method:_try_alternative, line:763]", "executor.py", "method", 763)
                        continue
                        
            except Exception as exc:
                logger._print_log("warning", r"[EXECUTOR] Alternativa %s también falló: %s [file:executor.py, method:_try_alternative, line:767]", "executor.py", "method", 767)
                continue
        
        logger._print_log("warning", r"[EXECUTOR] Ninguna alternativa funcionó para nodo %s [file:executor.py, method:_try_alternative, line:770]", "executor.py", "method", 770)
        return failed_result

    def _update_world_state(self, node: Dict[str, Any], result: ExecutionResult) -> None:
        """Actualiza el estado del mundo después de una ejecución exitosa (FASE 9)."""
        
        # Actualizar estado de aplicaciones
        app_name = node.get("application")
        if app_name:
            if app_name not in self.current_state.application_states:
                self.current_state.application_states[app_name] = {}
            
            # Actualizar estado basado en efectos del nodo
            effects = node.get("effects", [])
            for effect in effects:
                if effect == "app_open":
                    self.current_state.application_states[app_name]["open"] = True
                elif effect == "app_active":
                    self.current_state.application_states[app_name]["active"] = True
                elif effect == "app_closed":
                    self.current_state.application_states[app_name]["open"] = False
                elif effect == "app_minimized":
                    self.current_state.application_states[app_name]["active"] = False
                elif effect == "address_bar_focused":
                    self.current_state.application_states[app_name]["address_bar_focused"] = True
                elif effect == "url_typed":
                    self.current_state.application_states[app_name]["url_typed"] = True
                elif effect == "destination_loaded":
                    self.current_state.application_states[app_name]["destination_loaded"] = True
        
        # Actualizar elementos UI
        ui_element = node.get("ui_element")
        if ui_element:
            if ui_element not in self.current_state.ui_elements:
                self.current_state.ui_elements[ui_element] = {}
            
            # Actualizar estado del elemento UI basado en efectos
            effects = node.get("effects", [])
            if "focused" in effects:
                self.current_state.ui_elements[ui_element]["focused"] = True
            if "clicked" in effects:
                self.current_state.ui_elements[ui_element]["clicked"] = True
            if "typed" in effects:
                self.current_state.ui_elements[ui_element]["typed"] = True
        
        # Actualizar estado general del sistema
        self.current_state.timestamp = time.time()
        self.current_state.last_actions.append(result.node_id or "unknown")
        
        # Guardar en memoria con información detallada para replanificación
        execution_data = {
            "last_execution": {
                "node_id": result.node_id,
                "timestamp": result.execution_time,
                "status": result.status.value,
                "node_effects": node.get("effects", []),
                "application": node.get("application"),
                "ui_element": node.get("ui_element")
            },
            "world_state": {
                "application_states": self.current_state.application_states,
                "ui_elements": self.current_state.ui_elements,
                "timestamp": self.current_state.timestamp
            }
        }
        
        self.memory_manager.update_world_state(execution_data)

    # ========================================================================
    # EJECUCIÓN DE ACCIONES INDIVIDUALES (MANTENIDO Y MEJORADO)
    # ========================================================================

    def execute_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
        verify: bool = True,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Ejecuta una acción registrada con mejoras de estado y verificación.
        """
        start_time = time.time()
        
        action_info = self.action_registry.get_action(action_name)
        if action_info is None:
            raise ValueError(f"Acción no encontrada: {action_name}")

        safe_parameters = parameters or {}

        # Verificar precondiciones con estado actual
        if state is not None and not action_info.matches_preconditions(state):
            logger._print_log("warning", r"[EXECUTOR] Precondiciones no satisfechas para %s [file:executor.py, method:execute_action, line:863]", "executor.py", "method", 863)
            raise ValueError(f"Precondiciones no satisfechas para: {action_name}")

        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)

        try:
            # Ejecutar con timeout si se especifica
            if timeout:
                import signal
                
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Acción {action_name} excedió timeout de {timeout}s")
                
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout))
                
                try:
                    result = self.action_registry.execute_action(
                        action_name,
                        safe_parameters,
                    )
                finally:
                    signal.alarm(0)
            else:
                result = self.action_registry.execute_action(
                    action_name,
                    safe_parameters,
                )

            # Verificar éxito
            if verify and not action_info.verify_success(result, **safe_parameters):
                logger._print_log("error", r"[EXECUTOR] Verificación de éxito falló para %s [file:executor.py, method:execute_action, line:894]", "executor.py", "method", 894)
                raise RuntimeError(f"Acción ejecutada pero no verificada: {action_name}")

            execution_time = time.time() - start_time
            logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
            
            # Guardar estadística
            self._record_action_execution(action_name, True, execution_time)
            
            # Registrar en sistema de aprendizaje (FASE 18)
            if self.learning_system:
                self.learning_system.record_action_execution(
                    action_name=action_name,
                    success=True,
                    execution_time=execution_time,
                    estimated_cost=action_info.cost,
                    context={"verify": verify, "parameters": safe_parameters},
                    application=action_info.application,
                    screen_state=self._get_screen_state()
                )
            
            return result

        except Exception as exc:
            execution_time = time.time() - start_time
            logger._print_log("info", f"Error en acción: {str(exc, "executor.py", "method", 919)} [file:executor.py, method:execute_action, line:919]")
            self._record_action_execution(action_name, False, execution_time)
            
            # Registrar fallo en sistema de aprendizaje (FASE 18)
            if self.learning_system:
                self.learning_system.record_action_execution(
                    action_name=action_name,
                    success=False,
                    execution_time=execution_time,
                    estimated_cost=action_info.cost,
                    context={"verify": verify, "parameters": safe_parameters},
                    application=action_info.application,
                    screen_state=self._get_screen_state()
                )
            
            raise

    def can_execute(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
    ) -> bool:
        """Comprueba si una acción puede ejecutarse en el estado actual."""
        action_info = self.action_registry.get_action(action_name)
        if action_info is None:
            return False

        safe_parameters = parameters or {}
        if not self.action_registry.validate_action(action_name, safe_parameters):
            return False

        if state is not None and not action_info.matches_preconditions(state):
            return False

        return True

    # ========================================================================
    # COMPATIBILIDAD LEGACY (MANTENIDO)
    # ========================================================================

    def process_and_execute(self, llm_response: str) -> str:
        """Procesa respuesta LLM y ejecuta comando (mantenido para compatibilidad)."""
        if not isinstance(llm_response, str):
            return str(llm_response)

        match = self._COMMAND_PATTERN.search(llm_response)
        if not match:
            return llm_response.strip()

        command_name = match.group(1)
        args_str = match.group(2)

        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)

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
            logger._print_log("error", r"[EXECUTOR] Error ejecutando comando legacy %s: %s [file:executor.py, method:execute_command, line:988]", "executor.py", "method", 988)
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
                logger._print_log("debug", r"[EXECUTOR] Error buscando %s en módulo %s: %s [file:executor.py, method:_get_legacy_function, line:1055]", "executor.py", "method", 1055)

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
            logger._print_log("error", r"[EXECUTOR] Error obteniendo estadísticas: %s [file:executor.py, method:get_action_stats, line:1076]", "executor.py", "method", 1076)
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
            logger._print_log("error", r"[EXECUTOR] Error registrando ejecución: %s [file:executor.py, method:_record_action_execution, line:1088]", "executor.py", "method", 1088)
    
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
            logger._print_log("info", f"Error obteniendo estado de pantalla: {str(e, "executor.py", "method", 1102)} [file:executor.py, method:_get_screen_state, line:1102]")
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
            logger._print_log("warning", r"Sistema de aprendizaje no disponible para exportar [file:executor.py, method:export_learning_data, line:1156]", "executor.py", "method", 1156)
            return
        
        self.learning_system.export_learning_data(filepath)
    
    def import_learning_data(self, filepath: str) -> None:
        """
        Importa datos de aprendizaje (FASE 18).
        
        Args:
            filepath: Ruta del archivo de importación
        """
        if not self.learning_system:
            logger._print_log("warning", r"Sistema de aprendizaje no disponible para importar [file:executor.py, method:import_learning_data, line:1169]", "executor.py", "method", 1169)
            return
        
        self.learning_system.import_learning_data(filepath)
    
    def clear_learning_data(self) -> None:
        """Limpia datos de aprendizaje (FASE 18)."""
        if not self.learning_system:
            logger._print_log("warning", r"Sistema de aprendizaje no disponible para limpiar [file:executor.py, method:clear_learning_data, line:1177]", "executor.py", "method", 1177)
            return
        
        self.learning_system.clear_learning_data()
    
    def enable_learning(self, enabled: bool = True) -> None:
        """
        Habilita o deshabilita el aprendizaje (FASE 18).
        
        Args:
            enabled: Si se debe habilitar el aprendizaje
        """
        if not self.learning_system:
            logger._print_log("warning", r"Sistema de aprendizaje no disponible [file:executor.py, method:enable_learning, line:1190]", "executor.py", "method", 1190)
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
            logger._print_log("error", r"[EXECUTOR] Error registrando comando legacy: %s [file:executor.py, method:_record_command_execution, line:1204]", "executor.py", "method", 1204)

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
        enable_learning: bool = True
    ) -> Dict[str, Any]:
        """
        Ejecuta un objetivo usando el planificador integrado.
        
        Args:
            goal: Objetivo a alcanzar
            max_planning_time: Tiempo máximo para planificar
            find_alternatives: Si se deben buscar rutas alternativas
            plan_id: Identificador del plan
            
        Returns:
            Resultado completo de la ejecución del objetivo
        """
        start_time = time.time()
        
        logger._print_log("info", f"Iniciando ejecución de objetivo: {goal_id} [file:executor.py, method:execute_goal, line:1264]", "executor.py", "method", 1264)
        
        # Habilitar/deshabilitar aprendizaje si se especifica
        if self.learning_system:
            old_learning_state = self.learning_system.learning_enabled
            self.learning_system.enable_learning(enable_learning)
        
        # Planificar el objetivo
        planning_result = self.planner.plan(
            goal=goal,
            current_state=self._get_state_for_planning(),
            max_planning_time=max_planning_time,
            find_alternatives=find_alternatives,
            use_optimization=enable_learning  # Usar optimización si el aprendizaje está habilitado
        )
        
        # Restaurar estado de aprendizaje
        if self.learning_system and 'old_learning_state' in locals():
            self.learning_system.enable_learning(old_learning_state)
        
        if planning_result.status.value != "completed":
            logger._print_log("error", r"[EXECUTOR] Planificación fallida para objetivo %s: %s [file:executor.py, method:execute_goal, line:1285]", "executor.py", "method", 1285)
            return {
                "success": False,
                "error": "Planificación fallida",
                "goal_id": goal.id,
                "planning_time": planning_result.execution_time,
                "warnings": planning_result.warnings,
                "plan": None
            }
        
        # Ejecutar el plan generado
        execution_result = self.planner.execute_plan(
            planning_result.plan,
            plan_id or f"goal_{goal.id}_{int(time.time())}"
        )
        
        total_time = time.time() - start_time
        
        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
        
        return {
            "success": execution_result["success"],
            "goal_id": goal.id,
            "goal_type": goal.type,
            "plan_id": execution_result["plan_id"],
            "plan_length": len(planning_result.plan),
            "planning_time": planning_result.execution_time,
            "execution_time": execution_result["execution_time"],
            "total_time": total_time,
            "quality": planning_result.quality.value,
            "alternatives_found": len(planning_result.alternatives),
            "plan": planning_result.plan,
            "execution_status": execution_result["execution_status"],
            "error": execution_result["error"]
        }

    def _get_state_for_planning(self) -> Dict[str, Any]:
        """Obtiene estado actual en formato para planificación."""
        exec_state = self.get_current_state()
        return {
            "timestamp": exec_state.timestamp,
            "application_states": exec_state.application_states,
            "ui_elements": exec_state.ui_elements,
            "available_actions": exec_state.available_actions,
            "last_actions": exec_state.last_actions,
            "constraints": exec_state.constraints
        }

    def create_goal_from_command(self, command_name: str, parameters: Dict[str, Any]) -> Optional[Goal]:
        """
        Crea un objetivo a partir de un comando legacy.
        
        Args:
            command_name: Nombre del comando
            parameters: Parámetros del comando
            
        Returns:
            Goal creado o None si no se puede crear
        """
        logger._print_log("info", "Procesando solicitud", "executor.py", "method", 222)
        
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


__all__ = ["Executor", "ExecutionResult", "ExecutionStatus", "ExecutionState"]