"""
Fachada de ejecucion compatible para JARVIS.

Esta capa conserva la API historica de src.tools.executor, pero delega la
resolucion y ejecucion de acciones en ActionRegistry para evitar duplicar la
logica de ejecucion entre src.tools y src.hands.

Arquitectura de transicion:

    Brain / legacy [CMD:...]

            |
            v

    UnifiedExecutor
            |
            v
    ActionRegistry
            |
            +--> validacion de parametros
            +--> comprobacion opcional de precondiciones
            +--> ejecucion de la accion
            +--> verificacion opcional del resultado

La planificacion de rutas no pertenece a este modulo. En la arquitectura
objetivo sera responsabilidad del Planner.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.hands.actions.action_registry import ActionInfo, get_action_registry
from src.core.log import get_logger

logger = get_logger(__name__)


class UnifiedExecutor:
    """
    Fachada unificada para ejecutar acciones registradas.

    Mantiene compatibilidad con el formato historico [CMD:...], pero utiliza
    ActionRegistry como fuente unica de verdad para localizar y ejecutar
    acciones.
    """

    _COMMAND_PATTERN = re.compile(
        r"\[CMD:\s*([a-zA-Z0-9_]+)(?:\((.*?)\))?\]",
        re.DOTALL,
    )

    def __init__(self) -> None:
        """Inicializa la fachada de ejecucion."""
        self.registry = get_action_registry()
        self.command_history: List[Dict[str, Any]] = []
        self.logger = logger
        logger.info(r"[EXECUTOR] Fachada de ejecucion unificada inicializada.")

    # ======================================================================
    # PROCESAMIENTO LEGACY DEL LLM
    # ======================================================================

    def process_and_execute(
        self,
        llm_response: str,
        state: Any = None,
    ) -> str:
        """
        Procesa una respuesta del LLM y ejecuta el primer comando detectado.

        El parametro ``state`` es opcional y permite que la ejecucion futura o
        actual compruebe precondiciones de la accion antes de ejecutarla.

        El formato legacy sigue siendo compatible:
            [CMD:nombre]
            [CMD:nombre(arg1, arg2)]
        """
        response = str(llm_response or "")
        command_match = self._extract_command(response)
        if command_match is None:
            return response.strip()

        command_name = command_match["name"]
        args = command_match["args"]
        clean_text = command_match["clean_text"]


        try:
            action_info = self.registry.get_action(command_name)
            if action_info is None:
                # Permitir que ActionRegistry/aliases resuelvan nombres si la
                # implementacion concreta expone un resolvedor equivalente.
                normalized_name = self._normalize_action_name(command_name)
                if normalized_name != command_name:
                    action_info = self.registry.get_action(normalized_name)
                    if action_info is not None:
                        command_name = normalized_name

            if action_info is None:
                result = f"Error: Comando '{command_name}' no encontrado en el sistema."
                self._record_history(
                    command_name=command_name,
                    args=args,
                    result=result,
                    success=False,
                )
                return clean_text if clean_text else result

            parameters = self._args_to_dict(args, action_info.parameters)
            result = self.execute_action(
                command_name,
                parameters=parameters,
                state=state,
            )
            self._record_history(
                command_name=command_name,
                args=args,
                result=result,
                success=True,
            )

            if result is not None and not isinstance(result, str):
                result = str(result)
            return result if result else clean_text

        except TypeError as exc:
            logger.info("Procesando solicitud: " + str(exc))
            result = "Error en la ejecuci\u00f3n: argumentos incorrectos."
            self._record_history(
                command_name=command_name,
                args=args,
                result=result,
                success=False,
            )
            return clean_text if clean_text else result

        except ValueError as exc:
            logger.info("Procesando solicitud: " + str(exc))
            result = f"Error en los argumentos del comando: {exc}"
            self._record_history(
                command_name=command_name,
                args=args,
                result=result,
                success=False,
            )
            return clean_text if clean_text else result

        except Exception as exc:
            logger.info("Procesando solicitud: " + str(exc))
            result = f"Error en la ejecuci\u00f3n: {exc}"
            self._record_history(
                command_name=command_name,
                args=args,
                result=result,
                success=False,
            )
            return clean_text if clean_text else result

    def _extract_command(
        self,
        response: str,
    ) -> Optional[Dict[str, Any]]:
        """Extrae un comando legacy del formato [CMD:nombre(args)]."""
        if not response:
            return None

        match = self._COMMAND_PATTERN.search(response)
        if match is None:
            return None

        command_name = match.group(1).strip()
        args_str = match.group(2) or ""
        clean_text = (response[: match.start()] + response[match.end() :]).strip()

        return {
            "name": command_name,
            "args": self._parse_args(args_str),
            "clean_text": clean_text,
        }

    @staticmethod
    def _normalize_action_name(action_name: str) -> str:
        """Normaliza pequenas variaciones de nombre sin cambiar su semantica."""
        normalized = str(action_name or "").strip().lower()
        aliases = {
            "calibrate_applications": "calibrar_aplicaciones",
        }
        return aliases.get(normalized, normalized)

    # ======================================================================
    # EJECUCION CENTRALIZADA
    # ======================================================================

    def execute_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
        verify_success: bool = True,
    ) -> Any:
        """
        Ejecuta una accion registrada.

        ``state`` permite comprobar precondiciones cuando existe un estado
        explicito. La planificacion no se realiza aqui.
        """
        resolved_action_name = self._normalize_action_name(action_name)
        action_info = self.registry.get_action(resolved_action_name)
        if action_info is None:
            # Tambien aceptar exactamente el nombre recibido por si el
            # registro distingue alias de nombre canonico.
            resolved_action_name = action_name
            action_info = self.registry.get_action(resolved_action_name)

        if action_info is None:
            raise ValueError(f"Accion no encontrada: {action_name}")

        safe_parameters = dict(parameters or {})

        if not self.registry.validate_action(
            resolved_action_name,
            safe_parameters,
        ):
            raise ValueError(
                f"Parametros invalidos para la accion: {resolved_action_name}"
            )

        if state is not None and not action_info.matches_preconditions(state):
            raise ValueError(
                f"Precondiciones no satisfechas para la accion: {resolved_action_name}"
            )


        result = self.registry.execute_action(
            resolved_action_name,
            safe_parameters,
        )

        if verify_success and action_info.success_checker is not None:
            success = action_info.verify_success(
                result,
                **safe_parameters,
            )
            if not success:
                raise RuntimeError(
                    f"La accion '{resolved_action_name}' se ejecuto, pero su resultado "
                    "no supero la comprobacion de exito."
                )

        return result

    def can_execute(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
    ) -> bool:
        """Comprueba si una accion puede ejecutarse en el estado indicado."""
        resolved_action_name = self._normalize_action_name(action_name)
        if self.registry.get_action(resolved_action_name) is None:
            resolved_action_name = action_name

        return self.registry.can_execute(
            resolved_action_name,
            parameters=parameters,
            state=state,
            check_preconditions=state is not None,
        )

    def execute_plan_step(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
    ) -> Any:
        """
        Punto de entrada explicito para un futuro Planner.

        No crea planes ni decide la siguiente accion; simplemente ejecuta un
        paso ya decidido por la capa de planificacion.
        """
        return self.execute_action(
            action_name,
            parameters=parameters,
            state=state,
            verify_success=True,
        )

    # ======================================================================
    # PARSEO DE ARGUMENTOS LEGACY
    # ======================================================================

    def _parse_args(
        self,
        args_str: str,
    ) -> Tuple[Any, ...]:
        """
        Parsea argumentos legacy mediante ast.literal_eval.

        Ejemplos:
            "" -> ()
            "2" -> (2,)
            "'hola'" -> ('hola',)
            "'hola', 10" -> ('hola', 10)
            "(10, 20)" -> (10, 20)
        """
        text = str(args_str or "").strip()
        if not text:
            return ()

        try:
            expression = (
                text if text.startswith("(") and text.endswith(")") else f"({text})"
            )
            parsed = ast.literal_eval(expression)
            if isinstance(parsed, tuple):
                return parsed
            return (parsed,)
        except (ValueError, SyntaxError, TypeError) as exc:
            logger.info("Procesando solicitud: " + str(exc))
            raise ValueError(f"Argumentos no validos: {text}") from exc

    @staticmethod
    def _args_to_dict(
        args: Tuple[Any, ...],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convierte argumentos posicionales legacy a parametros nombrados.

        El orden utilizado es el orden del esquema almacenado en ActionInfo.
        """
        if not args:
            return {}

        if not parameters:
            raise ValueError("La accion no acepta parametros")

        parameter_names = list(parameters.keys())
        if len(args) > len(parameter_names):
            raise ValueError(
                "Se han recibido mas argumentos de los parametros definidos"
            )

        return {parameter_names[index]: value for index, value in enumerate(args)}

    # ======================================================================
    # SUGERENCIAS LEGACY
    # ======================================================================

    def get_command_suggestions(
        self,
        user_input: str,
        context: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Obtiene sugerencias simples a partir de acciones registradas.

        Esta funcion conserva compatibilidad con el sistema antiguo. No decide
        rutas de planificacion ni sustituye al Planner.
        """
        del context

        try:
            query = str(user_input or "").strip().lower()
            actions = self.registry.get_all_actions()

            if not query:
                return [
                    self._format_action_suggestion(action_info, 0.0)
                    for action_info in list(actions.values())[:5]
                ]

            suggestions: List[Dict[str, Any]] = []
            for action_name, action_info in actions.items():
                searchable = " ".join(
                    [
                        action_name,
                        action_info.description,
                        action_info.category,
                        " ".join(action_info.tags),
                    ]
                ).lower()

                if query not in searchable:
                    continue

                name_lower = action_name.lower()
                if query in name_lower:
                    score = len(query) / max(1, len(name_lower))
                    score = min(1.0, score + 0.25)
                else:
                    score = 0.25

                item = self._format_action_suggestion(
                    action_info,
                    score,
                )
                suggestions.append(item)

            suggestions.sort(
                key=lambda item: (
                    -float(item["score"]),
                    str(item["command"]),
                )
            )
            return suggestions[:5]

        except Exception as exc:
            logger.debug("UnifiedExecutor.get_command_suggestions: %s", exc)
            return []

    @staticmethod
    def _format_action_suggestion(
        action_info: ActionInfo,
        score: float,
    ) -> Dict[str, Any]:
        """Convierte ActionInfo al formato historico de sugerencias."""
        if score >= 0.8:
            confidence = "ALTA"
        elif score >= 0.6:
            confidence = "MEDIA"
        else:
            confidence = "BAJA"

        return {
            "command": action_info.name,
            "description": action_info.description,
            "score": round(float(score), 2),
            "type": action_info.action_type.value,
            "category": action_info.category,
            "tags": list(action_info.tags),
            "confidence": confidence,
        }

    # ======================================================================
    # HISTORIAL
    # ======================================================================

    def _record_history(
        self,
        command_name: str,
        args: Tuple[Any, ...],
        result: Any,
        success: bool,
    ) -> None:
        """Registra una ejecucion para compatibilidad y diagnostico."""
        self.command_history.append(
            {
                "command": command_name,
                "args": list(args),
                "result": result,
                "success": success,
                "timestamp": self._get_timestamp(),
            }
        )

    def get_command_history(self) -> List[Dict[str, Any]]:
        """Obtiene una copia del historial de comandos."""
        return [dict(item) for item in self.command_history]

    def clear_command_history(self) -> None:
        """Limpia el historial de comandos."""
        self.command_history.clear()
        logger.info(r"[EXECUTOR] Historial de comandos limpiado")

    # ======================================================================
    # INFORMACION DE ACCIONES
    # ======================================================================

    def list_available_commands(
        self,
        planner_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Lista las acciones disponibles con sus metadatos."""
        try:
            if planner_only:
                return self.registry.get_actions_for_planner()
            return self.registry.get_actions_for_llama()
        except Exception as exc:
            logger.debug("UnifiedExecutor.list_available_commands: %s", exc)
            return []

    def get_command_info(
        self,
        command_name: str,
    ) -> Dict[str, Any]:
        """Obtiene informacion detallada de una accion registrada."""
        try:
            resolved_name = self._normalize_action_name(command_name)
            action_info = self.registry.get_action(resolved_name)
            if action_info is None:
                action_info = self.registry.get_action(command_name)
            if action_info is None:
                return {}
            return action_info.to_dict()
        except Exception as exc:
            logger.debug("UnifiedExecutor.get_command_info: %s", exc)
            return {}

    def get_action_cost(self, action_name: str) -> float:
        """Obtiene el coste declarado de una accion para el planificador."""
        resolved_name = self._normalize_action_name(action_name)
        if self.registry.get_action(resolved_name) is None:
            resolved_name = action_name
        return self.registry.get_action_cost(resolved_name)

    def get_plannable_commands(self) -> List[Dict[str, Any]]:
        """Obtiene las acciones habilitadas para planificacion."""
        return self.registry.get_actions_for_planner()

    # ======================================================================
    # UTILIDADES
    # ======================================================================

    @staticmethod
    def _get_timestamp() -> str:
        """Obtiene la fecha/hora actual en formato ISO."""
        return datetime.now().isoformat()


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================

_executor_instance: Optional[UnifiedExecutor] = None


def get_executor() -> UnifiedExecutor:
    """Obtiene la instancia global del ejecutor unificado."""
    global _executor_instance

    if _executor_instance is None:
        _executor_instance = UnifiedExecutor()

    return _executor_instance


# ============================================================================
# COMPATIBILIDAD
# ============================================================================


def process_and_execute(
    llm_response: str,
) -> str:
    """
    Funcion de compatibilidad para codigo existente.

    Delega en la instancia global de UnifiedExecutor.
    """
    return get_executor().process_and_execute(llm_response)
