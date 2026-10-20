"""Ejecutor de tareas HTN integrado con las capacidades reales de JARVIS.

Convierte tareas HTN en unidades ejecutables y delega la ejecución en el
registro central de acciones o en el executor principal. No declara éxito si no
recibe confirmación explícita y no ejecuta automáticamente tareas no soportadas.
"""
from __future__ import annotations

import inspect
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.hands.planner.node import Node, NodeType, Task, TaskStatus
from src.hands.planner.htn_manager import TaskExecutionResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Dependencias diferidas para evitar ciclos durante el arranque.
_htn_manager: Optional[Any] = None
_application_integrator: Optional[Any] = None
_executor: Optional[Any] = None
_action_registry: Optional[Any] = None
_singleton_lock = threading.RLock()


def get_htn_manager() -> Any:
    """Obtiene el HTN Manager de forma diferida."""
    global _htn_manager
    if _htn_manager is None:
        with _singleton_lock:
            if _htn_manager is None:
                from src.hands.planner.htn_manager import get_htn_manager as factory
                _htn_manager = factory()
    return _htn_manager


def get_application_knowledge_integrator() -> Any:
    """Obtiene el integrador de conocimiento de aplicaciones."""
    global _application_integrator
    if _application_integrator is None:
        with _singleton_lock:
            if _application_integrator is None:
                from src.hands.planner.application_integration import (
                    get_application_knowledge_integrator as factory,
                )
                _application_integrator = factory()
    return _application_integrator


def get_executor() -> Any:
    """Obtiene el executor principal de JARVIS de forma diferida."""
    global _executor
    if _executor is None:
        with _singleton_lock:
            if _executor is None:
                from src.hands.executor import get_executor as factory
                _executor = factory()
    return _executor


def get_action_registry() -> Any:
    """Obtiene el registro central de acciones de forma diferida."""
    global _action_registry
    if _action_registry is None:
        with _singleton_lock:
            if _action_registry is None:
                from src.hands.action_registry import get_action_registry as factory
                _action_registry = factory()
    return _action_registry


class TaskExecutorStatus(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class TaskExecutionMode(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    FALLBACK = "fallback"


@dataclass
class TaskExecutionConfig:
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout_per_task: float = 30.0
    enable_fallback: bool = True
    parallel_execution: bool = False
    log_execution_details: bool = True

    def __post_init__(self) -> None:
        self.max_retries = max(0, self._safe_int(self.max_retries, 3))
        self.retry_delay = max(0.0, self._safe_float(self.retry_delay, 1.0))
        self.timeout_per_task = max(0.0, self._safe_float(self.timeout_per_task, 30.0))
        self.enable_fallback = bool(self.enable_fallback)
        self.parallel_execution = bool(self.parallel_execution)
        self.log_execution_details = bool(self.log_execution_details)

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            number = float(value)
            return number if math.isfinite(number) else default
        except (TypeError, ValueError, OverflowError):
            return default


class TaskExecutor:
    """Ejecutor HTN que delega las acciones sin simular ejecuciones."""

    def __init__(self, config: Optional[TaskExecutionConfig] = None):
        self.config = config or TaskExecutionConfig()
        self.htn_manager = self._safe_get(get_htn_manager, "HTN Manager")
        self.application_integrator = self._safe_get(
            get_application_knowledge_integrator, "integrador de aplicaciones"
        )
        self.executor: Optional[Any] = None
        self.status = TaskExecutorStatus.IDLE
        self.current_task: Optional[Task] = None
        self.execution_context: Dict[str, Any] = {}

        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        self.total_attempts = 0
        self.average_execution_time = 0.0
        self._stats_lock = threading.RLock()

        logger.info("[TASK_EXECUTOR] Ejecutor de tareas inicializado")

    @staticmethod
    def _safe_get(factory: Callable[[], Any], label: str) -> Any:
        try:
            return factory()
        except Exception as exc:
            logger.warning("[TASK_EXECUTOR] %s no disponible: %s", label, exc)
            return None

    @staticmethod
    def _task_metadata(task: Task) -> Dict[str, Any]:
        metadata = getattr(task, "metadata", None)
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _task_application(task: Task) -> Optional[str]:
        metadata = TaskExecutor._task_metadata(task)
        value = metadata.get("application", getattr(task, "application", None))
        return str(value).strip() if value else None

    @staticmethod
    def _task_parameters(task: Task) -> Dict[str, Any]:
        metadata = TaskExecutor._task_metadata(task)
        parameters: Dict[str, Any] = {}
        direct = getattr(task, "parameters", None)
        if isinstance(direct, dict):
            parameters.update(direct)
        meta_parameters = metadata.get("parameters", {})
        if isinstance(meta_parameters, dict):
            parameters.update(meta_parameters)
        return parameters

    def execute_task(self, task: Task, current_state: Dict[str, Any]) -> TaskExecutionResult:
        """Prepara y ejecuta una tarea individual.

        ``timeout_per_task`` se comprueba al volver de la ejecución: no se puede
        cancelar con seguridad una acción externa ya iniciada desde este módulo.
        """
        started = time.perf_counter()
        state = dict(current_state) if isinstance(current_state, dict) else {}
        self.status = TaskExecutorStatus.PREPARING
        self.current_task = task
        self.execution_context = {
            "task_id": getattr(task, "id", None),
            "task_name": getattr(task, "name", ""),
            "start_time": started,
            "current_state": dict(state),
            "prepared": False,
        }
        with self._stats_lock:
            self.total_executions += 1

        if self.config.log_execution_details:
            logger.info("[TASK_EXECUTOR] Ejecutando tarea: %s", getattr(task, "id", "unknown"))

        try:
            preparation = self._prepare_task_execution(task, state)
            if preparation.status == TaskStatus.FAILED:
                return self._register_failure(
                    task, preparation.error_message, started, current_state=state,
                    result={"execution_attempted": False},
                )

            node = self._convert_task_to_node(task, state)
            if node is None:
                return self._register_failure(
                    task, "No se pudo convertir la tarea en nodo ejecutable", started,
                    current_state=state, result={"execution_attempted": False},
                )

            self.status = TaskExecutorStatus.EXECUTING
            result = self._execute_node(node, state)

            elapsed = time.perf_counter() - started
            if self.config.timeout_per_task > 0 and elapsed > self.config.timeout_per_task:
                # No se lanza fallback tras una acción que pudo haber tenido efectos.
                return self._register_failure(
                    task,
                    f"Tiempo límite excedido tras retornar: {elapsed:.2f}s > "
                    f"{self.config.timeout_per_task:.2f}s",
                    started,
                    result=result,
                    current_state=state,
                )

            if not result.get("success", False) and self.config.enable_fallback:
                attempted = bool(result.get("execution_attempted", False))
                allow_after_attempt = bool(
                    self._task_metadata(task).get("fallback_after_execution_failure", False)
                )
                if not attempted or allow_after_attempt:
                    fallback = self._execute_fallback(task, state)
                    if fallback.get("success", False):
                        result = fallback
                        logger.info("[TASK_EXECUTOR] Fallback exitoso para tarea: %s", task.name)
                    elif fallback.get("error"):
                        result.setdefault("fallback_error", fallback["error"])

            elapsed = time.perf_counter() - started
            if result.get("success", False):
                with self._stats_lock:
                    self.successful_executions += 1
                self.status = TaskExecutorStatus.COMPLETED
                result_state = result.get("new_state")
                if not isinstance(result_state, dict):
                    result_state = self._apply_result_to_state(state, result)
                return TaskExecutionResult(
                    task_id=task.id,
                    status=TaskStatus.COMPLETED,
                    result=result,
                    execution_time=elapsed,
                    new_state=dict(result_state),
                )

            return self._register_failure(
                task,
                result.get("error") or result.get("error_message") or "La ejecución ha fallado",
                started,
                result=result,
                current_state=state,
            )
        except Exception as exc:
            logger.exception("[TASK_EXECUTOR] Error en ejecución de tarea %s", getattr(task, "id", "unknown"))
            return self._register_failure(
                task, f"Error en ejecución: {exc}", started,
                result={"success": False, "error": str(exc), "execution_attempted": False},
                current_state=state,
            )
        finally:
            elapsed = time.perf_counter() - started
            self._update_execution_statistics(elapsed)
            self.current_task = None
            self.status = TaskExecutorStatus.IDLE

    def _register_failure(
        self,
        task: Task,
        error_message: Optional[str],
        started: float,
        result: Optional[Dict[str, Any]] = None,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        with self._stats_lock:
            self.failed_executions += 1
        self.status = TaskExecutorStatus.FAILED
        return self._failed_result(
            task, error_message, started, result=result, current_state=current_state
        )

    def _failed_result(
        self,
        task: Task,
        error_message: Optional[str],
        started: float,
        result: Optional[Dict[str, Any]] = None,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        state = (
            dict(current_state)
            if isinstance(current_state, dict)
            else dict(self.execution_context.get("current_state", {}) or {})
        )
        return TaskExecutionResult(
            task_id=task.id,
            status=TaskStatus.FAILED,
            result=dict(result) if isinstance(result, dict) else {"success": False},
            error_message=error_message or "Ejecución fallida",
            execution_time=max(0.0, time.perf_counter() - started),
            new_state=state,
        )

    def execute_task_with_retry(
        self, task: Task, current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        """Reintenta solo cuando la tarea declara explícitamente que es segura."""
        last_result: Optional[TaskExecutionResult] = None
        metadata = self._task_metadata(task)
        retry_safe = bool(metadata.get("retry_safe", metadata.get("idempotent", False)))
        for attempt in range(self.config.max_retries + 1):
            with self._stats_lock:
                self.total_attempts += 1
            if attempt > 0:
                self.status = TaskExecutorStatus.RETRYING
                logger.info(
                    "[TASK_EXECUTOR] Reintento %s/%s para tarea: %s",
                    attempt, self.config.max_retries, task.name,
                )
                if self.config.retry_delay > 0:
                    time.sleep(self.config.retry_delay)
            last_result = self.execute_task(task, current_state)
            if last_result.status == TaskStatus.COMPLETED:
                return last_result
            logger.warning(
                "[TASK_EXECUTOR] Intento %s fallido para %s: %s",
                attempt + 1, task.name, last_result.error_message,
            )
            result_payload = last_result.result if isinstance(last_result.result, dict) else {}
            action_attempted = bool(result_payload.get("execution_attempted", False))
            if attempt >= self.config.max_retries or (action_attempted and not retry_safe):
                break
        assert last_result is not None
        return last_result

    def execute_task_hierarchy(
        self,
        tasks: List[Task],
        current_state: Dict[str, Any],
        mode: TaskExecutionMode = TaskExecutionMode.SEQUENTIAL,
    ) -> List[TaskExecutionResult]:
        if mode == TaskExecutionMode.SEQUENTIAL:
            return self._execute_sequential(tasks, current_state)
        if mode == TaskExecutionMode.PARALLEL:
            return self._execute_parallel(tasks, current_state)
        if mode == TaskExecutionMode.CONDITIONAL:
            return self._execute_conditional(tasks, current_state)
        if mode == TaskExecutionMode.FALLBACK:
            return self._execute_with_fallback(tasks, current_state)
        raise ValueError(f"Modo de ejecución no soportado: {mode}")

    def _prepare_task_execution(self, task: Task, current_state: Dict[str, Any]) -> TaskExecutionResult:
        if not self._check_task_preconditions(task, current_state):
            return TaskExecutionResult(
                task_id=task.id, status=TaskStatus.FAILED,
                error_message="Precondiciones de la tarea no satisfechas",
                new_state=dict(current_state),
            )
        self.execution_context.update({
            "task_id": task.id,
            "task_name": task.name,
            "start_time": self.execution_context.get("start_time", time.perf_counter()),
            "current_state": dict(current_state),
            "prepared": True,
        })
        return TaskExecutionResult(
            task_id=task.id, status=TaskStatus.PENDING,
            result={"message": "Tarea preparada"}, new_state=dict(current_state),
        )

    def _check_task_preconditions(self, task: Task, current_state: Dict[str, Any]) -> bool:
        metadata = self._task_metadata(task)
        completed = current_state.get("completed_tasks", [])
        completed_ids = set(completed) if isinstance(completed, (set, tuple, list)) else set()
        for dependency in getattr(task, "dependencies", []) or []:
            if dependency not in completed_ids:
                logger.warning("[TASK_EXECUTOR] Dependencia no satisfecha: %s", dependency)
                return False

        application = self._task_application(task)
        if application:
            app_key = self._normalize_key(application)
            available_keys = (f"{application.lower()}_available", f"{app_key}_available")
            for key in available_keys:
                if key in current_state and not bool(current_state[key]):
                    logger.warning("[TASK_EXECUTOR] Aplicación no disponible: %s", application)
                    return False
            app_states = current_state.get("application_states", {})
            if isinstance(app_states, dict):
                app_state = app_states.get(application, app_states.get(app_key))
                if isinstance(app_state, dict) and app_state.get("available") is False:
                    return False

        if metadata.get("requires_ui") and not current_state.get("ui_resources_ready", False):
            logger.warning("[TASK_EXECUTOR] Recursos UI no disponibles")
            return False

        for condition in metadata.get("preconditions", []) or []:
            if not self._evaluate_precondition(condition, current_state):
                return False
        state_requirements = metadata.get("state_requirements", {})
        if isinstance(state_requirements, dict):
            for key, expected in state_requirements.items():
                if current_state.get(key) != expected:
                    return False
        return True

    @staticmethod
    def _evaluate_precondition(condition: Any, state: Dict[str, Any]) -> bool:
        if callable(condition):
            try:
                return bool(condition(state))
            except Exception:
                return False
        if isinstance(condition, str):
            return bool(state.get(condition, False))
        if isinstance(condition, dict):
            key = condition.get("key", condition.get("name"))
            if not key:
                return False
            if "equals" in condition:
                return state.get(key) == condition["equals"]
            if "value" in condition:
                return state.get(key) == condition["value"]
            return bool(state.get(key, False))
        return False

    def _convert_task_to_node(self, task: Task, current_state: Dict[str, Any]) -> Optional[Node]:
        try:
            metadata = self._task_metadata(task)
            action_name = self._resolve_action_name(task)
            raw_type = metadata.get("node_type", NodeType.ACTION)
            if isinstance(raw_type, NodeType):
                node_type = raw_type
            else:
                try:
                    node_type = NodeType(str(getattr(raw_type, "value", raw_type)).lower())
                except ValueError:
                    node_type = NodeType.ACTION
            if node_type not in {NodeType.ACTION, NodeType.CONDITION}:
                node_type = NodeType.ACTION

            preconditions = self._as_list(metadata.get("preconditions", []))
            effects = self._as_list(metadata.get("effects", []))
            state_requirements = metadata.get("state_requirements", {})
            state_modifications = metadata.get("state_modifications", {})
            node = Node(
                id=task.id,
                type=node_type,
                name=task.name,
                description=task.description,
                preconditions=preconditions,
                effects=effects,
                cost=self._calculate_task_cost(task, current_state),
                dependencies=list(getattr(task, "dependencies", []) or []),
                parameters=self._task_parameters(task),
                application=self._task_application(task),
                ui_element=metadata.get("ui_element"),
                metadata={**metadata, "task_id": task.id, "action_name": action_name},
                state_requirements=dict(state_requirements) if isinstance(state_requirements, dict) else {},
                state_modifications=dict(state_modifications) if isinstance(state_modifications, dict) else {},
            )
            node.execute_callback = self._create_execution_callback(task)
            node.success_criteria = self._create_success_criteria(task)
            return node
        except Exception as exc:
            logger.exception("[TASK_EXECUTOR] Error al convertir tarea %s a nodo", getattr(task, "id", "unknown"))
            return None

    def _calculate_task_cost(self, task: Task, current_state: Dict[str, Any]) -> float:
        metadata = self._task_metadata(task)
        explicit_cost = metadata.get("cost", metadata.get("estimated_cost"))
        if explicit_cost is not None:
            try:
                value = float(explicit_cost)
                if math.isfinite(value) and value >= 0:
                    return value
            except (TypeError, ValueError, OverflowError):
                pass

        action_name = self._resolve_action_name(task)
        try:
            registry = get_action_registry()
            if registry and registry.get_action(action_name):
                value = float(registry.get_action_cost(action_name))
                if math.isfinite(value) and value >= 0:
                    return value
        except Exception:
            pass

        base_cost = max(0.0, self._safe_number(metadata.get("complexity", 1.0), 1.0))
        application = self._task_application(task)
        if application and current_state.get(f"{application.lower()}_open", False):
            base_cost *= 0.5
        if metadata.get("requires_ui") and current_state.get("ui_resources_ready", False):
            base_cost *= 0.8
        return base_cost

    def _resolve_action_name(self, task: Task) -> str:
        metadata = self._task_metadata(task)
        return str(metadata.get("action") or metadata.get("action_name") or metadata.get("capability") or task.id).strip()

    def _create_execution_callback(self, task: Task) -> Callable[..., Dict[str, Any]]:
        explicit_callback = self._task_metadata(task).get("execute_callback")
        if callable(explicit_callback):
            def explicit(**kwargs: Any) -> Dict[str, Any]:
                result = self._normalize_execution_result(self._call_callback(explicit_callback, kwargs))
                result.setdefault("execution_attempted", True)
                return result
            return explicit

        def callback(**kwargs: Any) -> Dict[str, Any]:
            return self._execute_real_capability(task, kwargs)
        return callback

    @staticmethod
    def _call_callback(callback: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            signature = inspect.signature(callback)
            if not TaskExecutor._signature_accepts(signature, (), kwargs):
                # Algunos callbacks aceptan solo el contexto como primer argumento.
                if TaskExecutor._signature_accepts(signature, (kwargs,), {}):
                    return TaskExecutor._normalize_execution_result(callback(kwargs))
                return {"success": False, "error": "La firma del callback no acepta los parámetros", "execution_attempted": False}
        except (TypeError, ValueError):
            pass
        return TaskExecutor._normalize_execution_result(callback(**kwargs))

    @staticmethod
    def _truthy_success(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "success", "completed", "ok"}
        return bool(value)

    @staticmethod
    def _normalize_execution_result(result: Any) -> Dict[str, Any]:
        """Normaliza respuestas y exige evidencia explícita de éxito."""
        if isinstance(result, TaskExecutionResult):
            normalized: Dict[str, Any] = {
                "success": result.status == TaskStatus.COMPLETED,
                "result": result.result,
                "execution_time": result.execution_time,
                "error": result.error_message,
            }
            if isinstance(result.new_state, dict):
                normalized["new_state"] = dict(result.new_state)
            return normalized
        if isinstance(result, dict):
            normalized = dict(result)
            if "success" in normalized:
                normalized["success"] = TaskExecutor._truthy_success(normalized["success"])
            else:
                raw_status = normalized.get("status", "")
                raw_status = getattr(raw_status, "value", raw_status)
                normalized["success"] = str(raw_status).strip().lower() in {"success", "completed", "ok"}
            return normalized
        if isinstance(result, bool):
            return {"success": result}
        if result is None:
            return {"success": False, "error": "La capacidad no devolvió confirmación de ejecución"}
        explicit_success = getattr(result, "success", None)
        if explicit_success is not None:
            return {"success": TaskExecutor._truthy_success(explicit_success), "result": result}
        raw_status = getattr(result, "status", "")
        raw_status = getattr(raw_status, "value", raw_status)
        status = str(raw_status).strip().lower()
        if status:
            return {"success": status in {"success", "completed", "ok"}, "status": status, "result": result}
        return {
            "success": False,
            "result": result,
            "error": "La capacidad devolvió un resultado sin estado de éxito verificable",
        }

    def _execute_real_capability(self, task: Task, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una acción registrada o la delega en el executor principal."""
        action_name = self._resolve_action_name(task)
        parameters = self._task_parameters(task)
        runtime_parameters = dict(parameters)
        runtime_parameters.update({key: value for key, value in kwargs.items() if key != "current_state"})
        state = kwargs.get("current_state", {})
        if not isinstance(state, dict):
            state = {}

        try:
            registry = get_action_registry()
        except Exception as exc:
            logger.warning("[TASK_EXECUTOR] No se pudo obtener ActionRegistry para %s: %s", action_name, exc)
            registry = None

        if registry is not None:
            try:
                registered = registry.get_action(action_name)
            except Exception as exc:
                logger.warning("[TASK_EXECUTOR] Error consultando acción %s: %s", action_name, exc)
                registered = None
            if registered:
                try:
                    if not registry.can_execute(action_name, runtime_parameters, state=state):
                        return {"success": False, "error": f"Precondiciones o parámetros no válidos para: {action_name}", "execution_attempted": False}
                    raw_result = registry.execute_action(action_name, runtime_parameters)
                    normalized = self._normalize_execution_result(raw_result)
                    normalized.setdefault("action", action_name)
                    normalized["execution_attempted"] = True
                    return normalized
                except Exception as exc:
                    logger.exception("[TASK_EXECUTOR] Error ejecutando acción registrada %s", action_name)
                    return {"success": False, "error": str(exc), "action": action_name, "execution_attempted": True}

        try:
            if self.executor is None:
                self.executor = get_executor()
            if self.executor is None:
                return {"success": False, "error": f"No existe executor para la capacidad: {action_name}", "execution_attempted": False}
            delegated = self._delegate_to_executor(self.executor, task, action_name, runtime_parameters, state)
            if delegated is None:
                return {"success": False, "error": f"El executor no soporta la capacidad: {action_name}", "execution_attempted": False}
            normalized = self._normalize_execution_result(delegated)
            normalized.setdefault("action", action_name)
            normalized["execution_attempted"] = True
            return normalized
        except Exception as exc:
            logger.exception("[TASK_EXECUTOR] Error al delegar la capacidad %s", action_name)
            return {"success": False, "error": str(exc), "action": action_name, "execution_attempted": True}

    def _delegate_to_executor(
        self,
        executor: Any,
        task: Task,
        action_name: str,
        parameters: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> Any:
        """Adapta firmas conocidas; no repite una llamada que ya fue invocada."""
        candidates = (
            "execute_action", "execute_task", "execute", "run_action", "run_task", "run"
        )
        calls = (
            ((), {"action_name": action_name, "parameters": parameters, "current_state": current_state}),
            ((action_name,), parameters),
            ((task,), {**parameters, "current_state": current_state}),
            ((task,), parameters),
            ((), {"task": task, "current_state": current_state, **parameters}),
        )
        for method_name in candidates:
            method = getattr(executor, method_name, None)
            if not callable(method):
                continue
            try:
                signature = inspect.signature(method)
            except (TypeError, ValueError):
                continue
            for args, kwargs in calls:
                if not self._signature_accepts(signature, args, kwargs):
                    continue
                # Si el método elegido falla, la excepción se propaga: reintentar
                # otra convención podría ejecutar dos veces una acción con efectos.
                return method(*args, **kwargs)
        return None

    @staticmethod
    def _signature_accepts(signature: inspect.Signature, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> bool:
        try:
            signature.bind(*args, **kwargs)
            return True
        except TypeError:
            return False

    def _create_success_criteria(self, task: Task) -> Callable[..., bool]:
        metadata = self._task_metadata(task)
        custom_checker = metadata.get("success_checker")
        if callable(custom_checker):
            def check_custom(result: Any, **kwargs: Any) -> bool:
                try:
                    return bool(custom_checker(result, **kwargs))
                except Exception:
                    return False
            return check_custom

        def success_criteria(result: Any, **kwargs: Any) -> bool:
            normalized = self._normalize_execution_result(result)
            if normalized.get("success", False):
                return True
            target_url = metadata.get("target_url") or metadata.get("url")
            if task.id.endswith("navigate_to_target") and target_url:
                return kwargs.get("current_url") == target_url
            return False
        return success_criteria

    def _execute_node(self, node: Node, current_state: Dict[str, Any]) -> Dict[str, Any]:
        if not callable(node.execute_callback):
            return {"success": False, "error": "El nodo no tiene callback de ejecución", "execution_attempted": False}
        try:
            parameters = dict(getattr(node, "parameters", {}) or {})
            parameters.pop("current_state", None)
            callback_kwargs = {"current_state": dict(current_state), **parameters}
            raw_result = node.execute_callback(**callback_kwargs)
            result = self._normalize_execution_result(raw_result)
            if result.get("success", False):
                explicit_state = result.get("new_state")
                if isinstance(explicit_state, dict):
                    new_state = dict(explicit_state)
                else:
                    new_state = self._apply_result_to_state(current_state, result)
                modifications = getattr(node, "state_modifications", {})
                if isinstance(modifications, dict):
                    new_state.update(modifications)
                result.setdefault("new_state", new_state)
                criteria = getattr(node, "success_criteria", None)
                if callable(criteria):
                    criteria_context = {
                        key: value for key, value in result.items()
                        if key not in {"result", "current_state"}
                    }
                    criteria_context["current_state"] = dict(new_state)
                    if not criteria(result, **criteria_context):
                        return {**result, "success": False, "error": "El criterio de éxito del nodo no se ha cumplido"}
            return result
        except Exception as exc:
            logger.exception("[TASK_EXECUTOR] Error al ejecutar nodo %s", getattr(node, "id", "unknown"))
            return {"success": False, "error": str(exc), "execution_attempted": True}

    def _apply_result_to_state(self, current_state: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        new_state = dict(current_state or {})
        explicit_state = result.get("state_updates")
        if isinstance(explicit_state, dict):
            new_state.update(explicit_state)
        mapping = {
            "current_url": "current_url",
            "application_open": "application_open",
            "window_active": "window_active",
            "navigator_ready": "browser_ready",
            "search_engine_ready": "search_engine_ready",
            "search_performed": "search_performed",
            "entity_resolved": "entity_resolved",
        }
        for result_key, state_key in mapping.items():
            if result_key in result:
                new_state[state_key] = result[result_key]
        completed = new_state.get("completed_tasks", [])
        completed_ids = list(completed) if isinstance(completed, (list, tuple, set)) else []
        task_id = self.execution_context.get("task_id")
        if task_id and result.get("success", False) and task_id not in completed_ids:
            completed_ids.append(task_id)
        new_state["completed_tasks"] = completed_ids
        return new_state

    def _execute_fallback(self, task: Task, current_state: Dict[str, Any]) -> Dict[str, Any]:
        fallback_action = self._task_metadata(task).get("fallback_action")
        if not fallback_action:
            return {"success": False, "error": "No hay estrategia fallback disponible"}
        try:
            registry = get_action_registry()
            if registry is not None and registry.get_action(str(fallback_action)):
                parameters = self._task_metadata(task).get("fallback_parameters", {})
                parameters = dict(parameters) if isinstance(parameters, dict) else {}
                if not registry.can_execute(str(fallback_action), parameters, state=current_state):
                    return {"success": False, "error": "Fallback no disponible en el estado actual"}
                raw_result = registry.execute_action(str(fallback_action), parameters)
                normalized = self._normalize_execution_result(raw_result)
                normalized.update({"fallback": True, "execution_attempted": True})
                return normalized
        except Exception as exc:
            return {"success": False, "error": str(exc), "fallback": True, "execution_attempted": True}
        return {"success": False, "error": f"Fallback no registrado: {fallback_action}"}

    def _execute_prepare_navigator(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("prepare_navigator", kwargs)

    def _execute_navigate_to_target(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("navigate_to_target", kwargs)

    def _execute_check_availability(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("check_availability", kwargs)

    def _execute_open_application(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("open_application", kwargs)

    def _execute_activate_window(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("activate_window", kwargs)

    def _execute_navigate_to_search_engine(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("navigate_to_search_engine", kwargs)

    def _execute_perform_search(self, **kwargs: Any) -> Dict[str, Any]:
        return self._execute_legacy_task_capability("perform_search", kwargs)

    def _execute_legacy_task_capability(self, task_id: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibilidad para IDs HTN anteriores, delegando en capacidades reales."""
        compat_task = SimpleNamespace(
            id=task_id, name=task_id, description=task_id,
            dependencies=[], metadata={}, parameters={}, application=None,
        )
        return self._execute_real_capability(compat_task, kwargs)

    def _execute_resolve_entity(self, **kwargs: Any) -> Dict[str, Any]:
        """Resuelve una entidad usando el resolver de memoria real."""
        try:
            from src.memory.entity_resolver import entity_resolver, ResolutionContext
            entity_name = kwargs.get("entity", kwargs.get("entity_name", ""))
            entity_type = kwargs.get("entity_type")
            if not entity_name:
                return {"success": False, "error": "No se ha indicado la entidad"}
            context = ResolutionContext(
                conversation_history=self._get_conversation_history(),
                current_intent=self._get_current_intent(),
                recent_entities=self._get_recent_entities(),
                user_preferences=self._get_user_preferences(),
                session_info=self._get_session_info(),
            )
            resolution = entity_resolver.resolve_entity(entity_name, context=context, entity_type=entity_type)
            entity = getattr(resolution, "entity", None)
            if entity is None:
                return {"success": False, "error": f"No se pudo resolver la entidad: {entity_name}", "execution_attempted": True}
            self._update_world_state_with_entity(resolution)
            entity_data = {
                "id": getattr(entity, "id", None),
                "name": getattr(entity, "name", entity_name),
                "type": getattr(entity, "type", entity_type),
                "confidence": getattr(resolution, "confidence", None),
            }
            response: Dict[str, Any] = {
                "success": True,
                "message": f"Entidad resuelta: {entity_data['name']}",
                "entity_resolved": True,
                "resolved_entity": entity_data,
                "resolution_method": getattr(resolution, "resolution_method", None),
                "alternatives": [],
                "execution_attempted": True,
            }
            response["alternatives"] = [
                {"id": getattr(item, "id", None), "name": getattr(item, "name", None),
                 "type": getattr(item, "type", None), "confidence": getattr(item, "confidence", None)}
                for item in (getattr(resolution, "alternatives", []) or [])
            ]
            properties = getattr(entity, "properties", {})
            if isinstance(properties, dict) and properties.get("url"):
                response["resolved_url"] = properties["url"]
            return response
        except Exception as exc:
            logger.exception("[TASK_EXECUTOR] Error en resolución de entidad")
            return {"success": False, "error": f"Error en resolución de entidad: {exc}", "execution_attempted": True}

    def _get_conversation_history(self) -> List[Dict[str, Any]]:
        try:
            from src.memory.storage import MemoryManager
            memories = MemoryManager().get_conversational_memory(limit=10)
            return [{
                "message": getattr(memory, "message", None),
                "response": getattr(memory, "response", None),
                "entities": getattr(memory, "entities", None),
                "intent": getattr(memory, "intent", None),
            } for memory in memories]
        except Exception as exc:
            logger.warning("[TASK_EXECUTOR] Error obteniendo memoria conversacional: %s", exc)
            return []

    def _get_current_intent(self) -> Optional[str]:
        return self.execution_context.get("current_intent")

    def _get_recent_entities(self) -> List[str]:
        try:
            from src.memory.storage import MemoryManager
            world_state = MemoryManager().get_world_state()
            recent = getattr(world_state, "last_actions", [])
            return list(recent) if isinstance(recent, (list, tuple, set)) else []
        except Exception as exc:
            logger.warning("[TASK_EXECUTOR] No se pudieron obtener entidades recientes: %s", exc)
            return []

    def _get_user_preferences(self) -> Dict[str, Any]:
        try:
            from src.memory.storage import MemoryManager, MemoryType
            preferences = MemoryManager().storage.load(MemoryType.DOMAIN_KNOWLEDGE)
            return dict(preferences.get("user_preferences", {})) if isinstance(preferences, dict) else {}
        except Exception as exc:
            logger.warning("[TASK_EXECUTOR] No se pudieron obtener preferencias: %s", exc)
            return {}

    def _get_session_info(self) -> Dict[str, Any]:
        return {"session_id": self.execution_context.get("session_id", "current_session"), "timestamp": time.time()}

    def _update_world_state_with_entity(self, resolution: Any) -> None:
        try:
            from src.memory.storage import MemoryManager
            manager = MemoryManager()
            entity = resolution.entity
            entity_id = getattr(entity, "id", None)
            if entity_id is None:
                return
            if not manager.get_entity(entity_id):
                manager.save_entity(entity)
            state = manager.get_world_state()
            resolved = getattr(state, "resolved_entities", None)
            if not isinstance(resolved, dict):
                resolved = {}
                setattr(state, "resolved_entities", resolved)
            resolved[entity_id] = {
                "name": getattr(entity, "name", None),
                "type": getattr(entity, "type", None),
                "resolved_at": datetime.now().isoformat(),
                "confidence": getattr(resolution, "confidence", None),
            }
            manager.save_world_state(state)
        except Exception as exc:
            logger.warning("[TASK_EXECUTOR] No se pudo actualizar WorldState: %s", exc)

    def _execute_sequential(self, tasks: List[Task], current_state: Dict[str, Any]) -> List[TaskExecutionResult]:
        results: List[TaskExecutionResult] = []
        state = dict(current_state or {})
        for task in tasks:
            result = self.execute_task(task, state)
            results.append(result)
            if result.status == TaskStatus.FAILED:
                logger.warning("[TASK_EXECUTOR] Deteniendo secuencia por fallo en: %s", task.name)
                break
            if result.new_state:
                state = dict(result.new_state)
        return results

    def _execute_parallel(self, tasks: List[Task], current_state: Dict[str, Any]) -> List[TaskExecutionResult]:
        """Ejecuta tareas independientes en paralelo con estados aislados."""
        if not tasks:
            return []
        if not self.config.parallel_execution:
            logger.warning("[TASK_EXECUTOR] Paralelismo deshabilitado; se ejecuta secuencialmente")
            return self._execute_sequential(tasks, current_state)
        task_ids = {getattr(task, "id", None) for task in tasks}
        if any(set(getattr(task, "dependencies", []) or []) & task_ids for task in tasks):
            logger.warning("[TASK_EXECUTOR] Hay dependencias entre tareas; se ejecuta secuencialmente")
            return self._execute_sequential(tasks, current_state)

        def run_isolated(task: Task) -> Tuple[TaskExecutionResult, Dict[str, Any]]:
            worker = TaskExecutor(config=self.config)
            result = worker.execute_task(task, dict(current_state or {}))
            return result, worker.get_execution_statistics()

        with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
            futures = [pool.submit(run_isolated, task) for task in tasks]
            outcomes = [future.result() for future in futures]
        results = [result for result, _ in outcomes]
        with self._stats_lock:
            self.total_executions += sum(int(stats.get("total_executions", 0)) for _, stats in outcomes)
            self.successful_executions += sum(int(stats.get("successful_executions", 0)) for _, stats in outcomes)
            self.failed_executions += sum(int(stats.get("failed_executions", 0)) for _, stats in outcomes)
            self.total_attempts += sum(int(stats.get("total_attempts", 0)) for _, stats in outcomes)
            if results:
                self.average_execution_time = sum(item.execution_time for item in results) / len(results)
        return results

    def _execute_conditional(self, tasks: List[Task], current_state: Dict[str, Any]) -> List[TaskExecutionResult]:
        results: List[TaskExecutionResult] = []
        state = dict(current_state or {})
        for task in tasks:
            if self._should_execute_conditionally(task, state):
                result = self.execute_task(task, state)
                results.append(result)
                if result.status == TaskStatus.FAILED:
                    break
                if result.new_state:
                    state = dict(result.new_state)
            else:
                # ABORTED distingue una rama omitida de una tarea realmente ejecutada.
                results.append(TaskExecutionResult(
                    task_id=task.id, status=TaskStatus.ABORTED,
                    result={"message": "Tarea omitida por condición", "skipped": True},
                    execution_time=0.0, new_state=dict(state),
                ))
        return results

    def _execute_with_fallback(self, tasks: List[Task], current_state: Dict[str, Any]) -> List[TaskExecutionResult]:
        results: List[TaskExecutionResult] = []
        state = dict(current_state or {})
        for task in tasks:
            result = self.execute_task_with_retry(task, state)
            results.append(result)
            if result.status == TaskStatus.FAILED:
                break
            if result.new_state:
                state = dict(result.new_state)
        return results

    def _should_execute_conditionally(self, task: Task, current_state: Dict[str, Any]) -> bool:
        for condition in self._task_metadata(task).get("conditions", []) or []:
            if callable(condition):
                try:
                    if not condition(current_state):
                        return False
                except Exception:
                    return False
            elif condition == "browser_ready" and not current_state.get("browser_ready", False):
                return False
            elif condition == "entity_resolved" and not current_state.get("entity_resolved", False):
                return False
            elif isinstance(condition, str) and condition not in {"browser_ready", "entity_resolved"} and not current_state.get(condition, False):
                return False
        return True

    def _update_execution_statistics(self, execution_time: float) -> None:
        with self._stats_lock:
            count = self.total_executions
            elapsed = max(0.0, execution_time)
            if count <= 1:
                self.average_execution_time = elapsed
            else:
                self.average_execution_time = ((self.average_execution_time * (count - 1)) + elapsed) / count

    def get_execution_statistics(self) -> Dict[str, Any]:
        with self._stats_lock:
            total = self.total_executions
            success_rate = self.successful_executions / total if total else 0.0
            return {
                "status": self.status.value,
                "total_executions": total,
                "total_attempts": self.total_attempts,
                "successful_executions": self.successful_executions,
                "failed_executions": self.failed_executions,
                "success_rate": success_rate,
                "average_execution_time": self.average_execution_time,
                "current_task": self.current_task.id if self.current_task else None,
            }

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        if isinstance(value, (str, bytes)):
            return [value]
        try:
            return list(value)
        except TypeError:
            return [value]

    @staticmethod
    def _normalize_key(value: Any) -> str:
        return "_".join(str(value or "").strip().lower().split())

    @staticmethod
    def _safe_number(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
            return number if math.isfinite(number) else default
        except (TypeError, ValueError, OverflowError):
            return default


_task_executor: Optional[TaskExecutor] = None
_task_executor_lock = threading.RLock()


def get_task_executor() -> TaskExecutor:
    """Obtiene el singleton de TaskExecutor con inicialización protegida."""
    global _task_executor
    if _task_executor is None:
        with _task_executor_lock:
            if _task_executor is None:
                _task_executor = TaskExecutor()
    return _task_executor


__all__ = [
    "TaskExecutor",
    "TaskExecutorStatus",
    "TaskExecutionMode",
    "TaskExecutionConfig",
    "get_task_executor",
    "get_htn_manager",
    "get_application_knowledge_integrator",
    "get_executor",
    "get_action_registry",
]
