"""
Heurísticas para algoritmo de búsqueda A* (FASE 8).

Proporciona estimaciones configurables para StateGraph. Las estimaciones son
finitas y no negativas, la caché usa claves deterministas e incluye el contexto
del objetivo y se aplican fallbacks cuando una heurística no puede evaluarse.

A* utiliza:
    g(n): coste acumulado desde el inicio
    h(n): estimación del coste restante hasta el objetivo
    f(n): g(n) + h(n)

Nota: las heurísticas ponderadas, de similitud o basadas en capacidades no son
necesariamente admisibles. Para garantizar la optimalidad de A*, se debe usar
una heurística admisible para el dominio (por ejemplo, ZERO o una GOAL_DISTANCE
conservadora) y costes de transición no negativos.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from collections import OrderedDict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.hands.planner.node import Node, Goal
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HeuristicType(Enum):
    """Tipos de heurísticas disponibles."""

    MANHATTAN = "manhattan"
    EUCLIDEAN = "euclidean"
    UNIFORM = "uniform"
    # Alias de compatibilidad con código que utiliza este nombre.
    UNIFORM_COST = "uniform"
    ZERO = "zero"
    GOAL_DISTANCE = "goal_distance"
    CAPABILITY_BASED = "capability_based"
    STATE_SIMILARITY = "state_similarity"


CustomHeuristic = Callable[[str, Dict[str, Any], Goal], float]


def _log(level: str, message: str, method: str, line: int) -> None:
    """Emite un log sin permitir que un fallo del logger rompa la planificación."""
    try:
        printer = getattr(logger, "_print_log", None)
        if callable(printer):
            printer(level, message, "heuristic.py", method, line)
            return
        standard_method = getattr(logger, str(level).lower(), None)
        if callable(standard_method):
            standard_method(message)
        else:
            logger.info(message)
    except Exception:
        # El logging nunca debe hacer fallar una estimación heurística.
        try:
            logger.info(message)
        except Exception:
            pass


class Heuristic:
    """Heurística configurable para el algoritmo A*."""

    _DEFAULT_CACHE_SIZE = 1000

    def __init__(
        self,
        heuristic_type: HeuristicType = HeuristicType.GOAL_DISTANCE,
        weight: float = 1.0,
        custom_heuristic: Optional[CustomHeuristic] = None,
        max_cache_size: int = _DEFAULT_CACHE_SIZE,
    ) -> None:
        """Inicializa la heurística y su caché LRU acotada."""
        self.heuristic_type = self._normalize_heuristic_type(heuristic_type)
        self.weight = self._normalize_weight(weight)
        self.custom_heuristic = custom_heuristic if callable(custom_heuristic) else None
        try:
            self.max_cache_size = max(0, int(max_cache_size))
        except (TypeError, ValueError, OverflowError):
            self.max_cache_size = self._DEFAULT_CACHE_SIZE
        self.heuristic_cache: "OrderedDict[str, float]" = OrderedDict()

        _log(
            "info",
            f"Heurística inicializada: {self.heuristic_type.value} (peso: {self.weight})",
            "__init__",
            94,
        )

    # ======================================================================
    # CONFIGURACIÓN / CACHÉ
    # ======================================================================

    @staticmethod
    def _normalize_heuristic_type(value: Any) -> HeuristicType:
        """Normaliza un enum, su valor textual o su nombre simbólico."""
        if isinstance(value, HeuristicType):
            return value

        raw = str(value).strip().lower()
        aliases = {
            "astar": HeuristicType.GOAL_DISTANCE,
            "uniform_cost": HeuristicType.UNIFORM,
            "uniform-cost": HeuristicType.UNIFORM,
            "goal-distance": HeuristicType.GOAL_DISTANCE,
            "capability-based": HeuristicType.CAPABILITY_BASED,
            "state-similarity": HeuristicType.STATE_SIMILARITY,
        }
        if raw in aliases:
            return aliases[raw]

        try:
            return HeuristicType(raw)
        except ValueError:
            try:
                return HeuristicType[raw.upper()]
            except KeyError:
                _log(
                    "warning",
                    f"Tipo de heurística desconocido: {value!r}. Se utilizará GOAL_DISTANCE.",
                    "_normalize_heuristic_type",
                    125,
                )
                return HeuristicType.GOAL_DISTANCE

    @staticmethod
    def _normalize_weight(value: Any) -> float:
        """Normaliza el peso a un número finito no negativo."""
        try:
            weight = float(value)
        except (TypeError, ValueError, OverflowError):
            return 1.0

        if not math.isfinite(weight) or weight < 0.0:
            return 1.0
        return weight

    @staticmethod
    def _normalize_for_json(value: Any, active_ids: Optional[set[int]] = None) -> Any:
        """Normaliza objetos a tipos JSON, detectando referencias circulares."""
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else str(value)
        if isinstance(value, Enum):
            return Heuristic._normalize_for_json(value.value, active_ids)

        if active_ids is None:
            active_ids = set()
        object_id = id(value)
        if object_id in active_ids:
            return {"__cycle__": type(value).__qualname__}

        if isinstance(value, dict):
            active_ids.add(object_id)
            try:
                # Las claves se convierten a texto para admitir claves mixtas.
                return {
                    str(key): Heuristic._normalize_for_json(item, active_ids)
                    for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                }
            finally:
                active_ids.discard(object_id)

        if isinstance(value, (list, tuple)):
            active_ids.add(object_id)
            try:
                return [Heuristic._normalize_for_json(item, active_ids) for item in value]
            finally:
                active_ids.discard(object_id)

        if isinstance(value, (set, frozenset)):
            active_ids.add(object_id)
            try:
                normalized = [Heuristic._normalize_for_json(item, active_ids) for item in value]
                return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str))
            finally:
                active_ids.discard(object_id)

        active_ids.add(object_id)
        try:
            to_dict = getattr(value, "to_dict", None)
            if callable(to_dict):
                try:
                    return Heuristic._normalize_for_json(to_dict(), active_ids)
                except Exception:
                    pass
            try:
                attributes = vars(value)
            except (TypeError, AttributeError):
                attributes = None
            if isinstance(attributes, dict):
                return {
                    str(key): Heuristic._normalize_for_json(item, active_ids)
                    for key, item in sorted(attributes.items(), key=lambda pair: str(pair[0]))
                    if not str(key).startswith("_") and not callable(item)
                }
            return repr(value)
        finally:
            active_ids.discard(object_id)

    @staticmethod
    def _stable_serialize(value: Any) -> str:
        """Serializa datos de forma estable para claves de caché."""
        try:
            normalized = Heuristic._normalize_for_json(value)
            return json.dumps(
                normalized,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
                default=str,
            )
        except Exception:
            try:
                return repr(value)
            except Exception:
                return f"<{type(value).__module__}.{type(value).__qualname__}>"

    @staticmethod
    def _json_fallback(value: Any) -> Any:
        """Fallback compatible para serializadores JSON que lo utilicen."""
        return Heuristic._normalize_for_json(value)

    def _build_cache_key(
        self,
        node_id: str,
        current_state: Dict[str, Any],
        goal: Goal,
    ) -> str:
        """Construye una clave que separa nodo, contexto, objetivo y configuración."""
        goal_data: Any
        if hasattr(goal, "to_dict") and callable(getattr(goal, "to_dict", None)):
            try:
                goal_data = goal.to_dict()
            except Exception:
                goal_data = self._minimal_goal_data(goal)
        else:
            goal_data = self._minimal_goal_data(goal)

        custom = self.custom_heuristic
        custom_identity = None
        if custom is not None:
            custom_identity = {
                "module": getattr(custom, "__module__", type(custom).__module__),
                "qualname": getattr(custom, "__qualname__", type(custom).__qualname__),
                # Evita reutilizar entradas si la función se sustituye en runtime.
                "identity": id(custom),
            }

        payload = {
            "node_id": str(node_id),
            "state": current_state if isinstance(current_state, dict) else {},
            "goal": goal_data,
            "heuristic": self.heuristic_type.value,
            "weight": self.weight,
            "custom": custom_identity,
        }
        serialized = self._stable_serialize(payload)
        return hashlib.sha256(serialized.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _minimal_goal_data(goal: Any) -> Dict[str, Any]:
        """Obtiene los campos básicos del objetivo cuando no puede serializarse."""
        return {
            "id": getattr(goal, "id", ""),
            "type": getattr(getattr(goal, "type", ""), "value", getattr(goal, "type", "")),
            "target": getattr(goal, "target", ""),
            "metadata": getattr(goal, "metadata", {}),
        }

    def _cache_get(self, key: str) -> Optional[float]:
        """Obtiene una estimación manteniendo el orden LRU."""
        if key not in self.heuristic_cache:
            return None
        value = self.heuristic_cache.pop(key)
        self.heuristic_cache[key] = value
        return value

    def _cache_set(self, key: str, value: float) -> None:
        """Guarda una estimación y elimina las entradas menos recientes."""
        if self.max_cache_size <= 0:
            return
        self.heuristic_cache.pop(key, None)
        self.heuristic_cache[key] = value
        while len(self.heuristic_cache) > self.max_cache_size:
            self.heuristic_cache.popitem(last=False)

    # ======================================================================
    # ESTIMACIÓN PRINCIPAL
    # ======================================================================

    def estimate_cost(
        self,
        node_id: str,
        current_state: Dict[str, Any],
        goal: Goal,
        all_nodes: Dict[str, Node],
    ) -> float:
        """Estima el coste restante y siempre devuelve un float finito >= 0."""
        state = current_state if isinstance(current_state, dict) else {}
        try:
            cache_key = self._build_cache_key(node_id, state, goal)
        except Exception:
            cache_key = None

        if cache_key is not None:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        try:
            # La heurística personalizada recibe una copia para que una función
            # ajena no pueda alterar accidentalmente el estado del planificador.
            try:
                state_for_estimate = copy.deepcopy(state)
            except Exception:
                state_for_estimate = dict(state)

            if self.custom_heuristic is not None:
                estimated_cost = self.custom_heuristic(node_id, state_for_estimate, goal)
            else:
                estimated_cost = self._apply_heuristic(
                    node_id,
                    state_for_estimate,
                    goal,
                    all_nodes if isinstance(all_nodes, dict) else {},
                )
        except Exception as exc:
            _log(
                "warning",
                f"Error calculando h({node_id}): {exc}. Se usará 0.",
                "estimate_cost",
                309,
            )
            estimated_cost = 0.0

        try:
            estimated_cost = float(estimated_cost)
        except (TypeError, ValueError, OverflowError):
            estimated_cost = 0.0
        if not math.isfinite(estimated_cost) or estimated_cost < 0.0:
            estimated_cost = 0.0

        final_cost = estimated_cost * self.weight
        if not math.isfinite(final_cost) or final_cost < 0.0:
            final_cost = 0.0

        if cache_key is not None:
            self._cache_set(cache_key, final_cost)
        return final_cost

    def _apply_heuristic(
        self,
        node_id: str,
        current_state: Dict[str, Any],
        goal: Goal,
        all_nodes: Dict[str, Node],
    ) -> float:
        """Aplica la heurística seleccionada."""
        node = all_nodes.get(node_id) if isinstance(all_nodes, dict) else None

        if self.heuristic_type == HeuristicType.UNIFORM:
            # Heurística constante; la búsqueda de coste uniforme real es Dijkstra.
            return 1.0
        if self.heuristic_type == HeuristicType.ZERO:
            return 0.0
        if self.heuristic_type == HeuristicType.MANHATTAN:
            return self._manhattan_distance(node, goal, current_state)
        if self.heuristic_type == HeuristicType.EUCLIDEAN:
            return self._euclidean_distance(node, goal, current_state)
        if self.heuristic_type == HeuristicType.GOAL_DISTANCE:
            return self._goal_distance_heuristic(node, goal, current_state)
        if self.heuristic_type == HeuristicType.CAPABILITY_BASED:
            return self._capability_based_heuristic(node, goal, current_state)
        if self.heuristic_type == HeuristicType.STATE_SIMILARITY:
            return self._state_similarity_heuristic(node, goal, current_state)
        return 0.0

    # ======================================================================
    # HEURÍSTICAS CONCRETAS
    # ======================================================================

    def _manhattan_distance(
        self,
        node: Optional[Node],
        goal: Goal,
        current_state: Dict[str, Any],
    ) -> float:
        """Estimación discreta de navegación basada en el estado observable."""
        del node
        goal_type = self._goal_type(goal)
        if goal_type in {"navigate", "navigate_stream", "navigate_to_entity", "streaming"}:
            target_url = self._get_target_url(goal)
            current_url = self._get_current_url(current_state)
            if target_url and current_url and self._urls_match(current_url, target_url):
                return 0.0

            application = self._get_target_application(goal) or "chrome"
            if not self._application_flag(current_state, application, "open"):
                return 2.0
            if not self._application_flag(current_state, application, "active"):
                return 1.0
            return 1.0
        return 1.0

    def _euclidean_distance(
        self,
        node: Optional[Node],
        goal: Goal,
        current_state: Dict[str, Any],
    ) -> float:
        """Ajuste continuo de la estimación discreta disponible."""
        return self._manhattan_distance(node, goal, current_state) * 0.70710678118

    def _goal_distance_heuristic(
        self,
        node: Optional[Node],
        goal: Goal,
        current_state: Dict[str, Any],
    ) -> float:
        """Estima un límite conservador del trabajo pendiente del objetivo."""
        del node
        try:
            if callable(getattr(goal, "is_achieved", None)) and goal.is_achieved(current_state):
                return 0.0
        except Exception:
            pass

        # Para objetivos de navegación, una URL destino observada representa
        # estado alcanzado aunque el estado serializado difiera solo en la barra final.
        if self._goal_type(goal) in {"navigate", "navigate_stream", "navigate_to_entity"}:
            target_url = self._get_target_url(goal)
            current_url = self._get_current_url(current_state)
            if target_url and current_url and self._urls_match(current_url, target_url):
                return 0.0

        required_capabilities = self._get_required_capabilities(goal)
        if not required_capabilities:
            # Si se conoce una URL destino, aún podemos comprobar la navegación
            # directamente aunque el objetivo no declare capacidades.
            target_url = self._get_target_url(goal)
            current_url = self._get_current_url(current_state)
            if target_url and current_url and self._urls_match(current_url, target_url):
                return 0.0
            return 0.0

        missing = [
            capability
            for capability in required_capabilities
            if not self._capability_fulfilled(capability, current_state, goal)
        ]
        if not missing:
            return 0.0

        # El mínimo evita sumar capacidades potencialmente solapadas, manteniendo
        # una estimación más conservadora para el modo GOAL_DISTANCE por defecto.
        capability_costs = self._capability_costs()
        return min(
            self._cost_for_capability(str(capability), capability_costs)
            for capability in missing
        )

    def _capability_based_heuristic(
        self,
        node: Optional[Node],
        goal: Goal,
        current_state: Dict[str, Any],
    ) -> float:
        """Estima el coste según las capacidades requeridas que faltan."""
        del node
        required_capabilities = self._get_required_capabilities(goal)
        if not required_capabilities:
            return 0.0

        capability_costs = self._capability_costs()
        total_cost = 0.0
        for capability in required_capabilities:
            capability_name = str(capability)
            if not self._capability_fulfilled(capability_name, current_state, goal):
                total_cost += self._cost_for_capability(capability_name, capability_costs)
        return total_cost

    def _state_similarity_heuristic(
        self,
        node: Optional[Node],
        goal: Goal,
        current_state: Dict[str, Any],
    ) -> float:
        """Estima la distancia al estado objetivo usando los campos declarados."""
        del node
        expected_state = self._get_expected_state(goal)
        if not expected_state:
            return 0.0

        total_checks = len(expected_state)
        matched = sum(
            1
            for key, expected_value in expected_state.items()
            if self._values_equal(self._get_state_value(current_state, key), expected_value)
        )
        similarity_ratio = matched / total_checks
        return (1.0 - similarity_ratio) * float(total_checks)

    # ======================================================================
    # ESTADO / OBJETIVO
    # ======================================================================

    @staticmethod
    def _goal_type(goal: Any) -> str:
        value = getattr(goal, "type", "")
        value = getattr(value, "value", value)
        return str(value).strip().lower()

    @staticmethod
    def _target_mapping(goal: Any) -> Dict[str, Any]:
        target = getattr(goal, "target", None)
        return target if isinstance(target, dict) else {}

    @classmethod
    def _get_target_url(cls, goal: Any) -> str:
        """Obtiene el destino URL admitiendo objetivos legacy y estructurados."""
        target = getattr(goal, "target", None)
        metadata = getattr(goal, "metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        if isinstance(target, dict):
            candidates = (
                target.get("url"),
                target.get("target_url"),
                target.get("stream_url"),
                target.get("uri"),
            )
        elif isinstance(target, str) and cls._goal_type(goal) in {
            "navigate", "navigate_stream", "navigate_to_entity", "streaming"
        }:
            candidates = (target,)
        else:
            candidates = ()
        candidates = tuple(candidates) + (
            metadata.get("url"),
            metadata.get("target_url"),
            metadata.get("stream_url"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""

    @classmethod
    def _get_target_application(cls, goal: Any) -> str:
        """Obtiene la aplicación objetivo desde el target o los metadatos."""
        target = cls._target_mapping(goal)
        metadata = getattr(goal, "metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        for candidate in (
            target.get("app_name"),
            target.get("application"),
            target.get("application_name"),
            target.get("browser"),
            target.get("name") if cls._goal_type(goal) in {"open_application", "close_application"} else None,
            metadata.get("app_name"),
            metadata.get("application"),
            metadata.get("application_name"),
            metadata.get("browser"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip().lower()

        raw_target = getattr(goal, "target", None)
        goal_type = cls._goal_type(goal)
        if isinstance(raw_target, str) and goal_type in {"open_application", "close_application"}:
            return raw_target.strip().lower()
        # Compatibilidad con el contrato legacy de navegación de JARVIS, cuyo
        # navegador predeterminado documentado es Chrome cuando no se especifica.
        if goal_type in {"navigate", "navigate_stream", "navigate_to_entity", "streaming"}:
            return "chrome"
        return ""

    @staticmethod
    def _urls_match(actual: str, expected: str) -> bool:
        """Compara URLs sin distinguir una barra final, conservando el resto."""
        return actual.strip().rstrip("/") == expected.strip().rstrip("/")

    @staticmethod
    def _get_required_capabilities(goal: Goal) -> List[str]:
        """Obtiene capacidades requeridas y admite respuestas en formato string."""
        try:
            result = goal.get_required_capabilities()
            if result is None:
                return []
            if isinstance(result, str):
                return [result] if result.strip() else []
            return list(dict.fromkeys(str(value) for value in result if value is not None))
        except Exception:
            return []

    @staticmethod
    def _get_current_url(state: Dict[str, Any]) -> str:
        """Obtiene la URL actual desde formatos de estado compatibles."""
        if not isinstance(state, dict):
            return ""
        candidates = [state.get("current_url"), state.get("url")]
        for container_name in ("application_states", "applications"):
            container = state.get(container_name)
            if isinstance(container, dict):
                for app_name in ("chrome", "google chrome", "browser"):
                    app_state = container.get(app_name)
                    if isinstance(app_state, dict):
                        candidates.extend((app_state.get("current_url"), app_state.get("url")))
                # Estados anidados pueden usar cualquier nombre de navegador.
                for app_state in container.values():
                    if isinstance(app_state, dict):
                        candidates.extend((app_state.get("current_url"), app_state.get("url")))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""

    @staticmethod
    def _application_flag(state: Dict[str, Any], application: str, flag: str) -> bool:
        """Obtiene un flag de aplicación de estado plano o anidado."""
        if not isinstance(state, dict):
            return False
        app = str(application or "").strip().lower()
        normalized_flag = str(flag or "").strip().lower()
        if not app:
            return False

        direct_keys = (f"{app}_{normalized_flag}", f"{app.replace(' ', '_')}_{normalized_flag}")
        for direct_key in direct_keys:
            if bool(state.get(direct_key, False)):
                return True

        aliases = {app, app.replace(" ", "_"), app.replace("_", " ")}
        for container_name in ("application_states", "applications"):
            container = state.get(container_name)
            if not isinstance(container, dict):
                continue
            app_state = next(
                (value for key, value in container.items() if str(key).strip().lower() in aliases),
                None,
            )
            if not isinstance(app_state, dict):
                continue
            if bool(app_state.get(normalized_flag, False)):
                return True
            status = str(app_state.get("state", "")).strip().lower()
            if normalized_flag == "open" and status in {"open", "opened", "active", "running", "maximized", "minimized"}:
                return True
            if normalized_flag == "active" and status in {"active", "foreground", "focused"}:
                return True
        return False

    def _capability_fulfilled(
        self,
        capability: str,
        current_state: Dict[str, Any],
        goal: Optional[Goal] = None,
    ) -> bool:
        """Comprueba una capacidad usando el objetivo para evitar falsos positivos."""
        if not isinstance(current_state, dict):
            return False
        capability_lower = str(capability).strip().lower()
        target_application = self._get_target_application(goal) if goal is not None else ""

        if capability_lower in {"open_application", "open", "application_open"}:
            if target_application:
                return self._application_flag(current_state, target_application, "open")
            # Sin aplicación objetivo solo se acepta un flag explícito global o
            # una aplicación presente en el estado; no se inventa cuál interesa.
            if bool(current_state.get("application_open", False)):
                return True
            for key, value in current_state.items():
                if isinstance(key, str) and key.endswith("_open") and bool(value):
                    return True
            applications = current_state.get("applications")
            if isinstance(applications, dict):
                return any(
                    isinstance(app_state, dict)
                    and (bool(app_state.get("open", False)) or str(app_state.get("state", "")).lower() in {"open", "opened", "active", "running"})
                    for app_state in applications.values()
                )
            return False

        if capability_lower in {"activate_window", "application_active", "focus_application"}:
            if target_application:
                return self._application_flag(current_state, target_application, "active")
            if bool(current_state.get("application_active", False)):
                return True
            if any(bool(current_state.get(key, False)) for key in current_state if isinstance(key, str) and key.endswith("_active")):
                return True
            return bool(current_state.get("active_application"))

        if capability_lower in {"navigate", "navigation"}:
            target_url = self._get_target_url(goal) if goal is not None else ""
            current_url = self._get_current_url(current_state)
            if target_url:
                return bool(current_url and self._urls_match(current_url, target_url))
            return bool(current_url)

        if capability_lower in {"focus_element", "element_focused"}:
            return bool(current_state.get("focused_element") or current_state.get("element_focused"))

        if capability_lower in {"type_text", "text_typed"}:
            return bool(current_state.get("text_typed", False))

        if capability_lower in {"press_key", "key_pressed"}:
            return bool(current_state.get("key_pressed", False))

        if capability_lower in {"search", "search_performed"}:
            return bool(current_state.get("search_performed", False))

        if capability_lower == "close_application":
            if target_application:
                return not self._application_flag(current_state, target_application, "open")
            return bool(current_state.get("application_closed", False))

        if capability_lower in current_state:
            return bool(current_state.get(capability_lower))

        return False

    @staticmethod
    def _values_equal(actual: Any, expected: Any) -> bool:
        if actual == expected:
            return True
        # Mantiene una comparación estricta para bool: True no debe equivaler a 1.
        if isinstance(actual, bool) or isinstance(expected, bool):
            return type(actual) is type(expected) and actual == expected
        if isinstance(actual, (int, float)) and isinstance(expected, str):
            try:
                return math.isfinite(float(actual)) and float(actual) == float(expected)
            except (ValueError, TypeError, OverflowError):
                return False
        if isinstance(expected, (int, float)) and isinstance(actual, str):
            try:
                return math.isfinite(float(expected)) and float(actual) == float(expected)
            except (ValueError, TypeError, OverflowError):
                return False
        return False

    @staticmethod
    def _get_state_value(state: Dict[str, Any], key: str) -> Any:
        """Obtiene un valor de estado con claves directas, punteadas o anidadas."""
        if not isinstance(state, dict):
            return None
        if key in state:
            return state.get(key)

        if "." in key:
            value: Any = state
            for part in key.split("."):
                if not isinstance(value, dict) or part not in value:
                    return None
                value = value[part]
            return value

        for container_name in ("application_states", "applications", "system_info"):
            container = state.get(container_name)
            if isinstance(container, dict) and key in container:
                return container.get(key)
        return None

    @classmethod
    def _get_expected_state(cls, goal: Goal) -> Dict[str, Any]:
        """Obtiene una representación mínima y consistente del estado objetivo."""
        expected_state: Dict[str, Any] = {}
        goal_type = cls._goal_type(goal)
        target = getattr(goal, "target", None)
        app_name = cls._get_target_application(goal)
        target_url = cls._get_target_url(goal)

        if goal_type in {"navigate", "navigate_to_entity"} and target_url:
            expected_state["current_url"] = target_url
        elif goal_type == "open_application" and app_name:
            expected_state[f"{app_name}_open"] = True
        elif goal_type == "close_application" and app_name:
            expected_state[f"{app_name}_open"] = False
        elif goal_type == "search":
            expected_state["search_performed"] = True
        elif goal_type in {"navigate_stream", "streaming"} and target_url:
            expected_state["current_url"] = target_url

        metadata = getattr(goal, "metadata", {})
        if isinstance(metadata, dict):
            custom_expected = metadata.get("target_state")
            if isinstance(custom_expected, dict):
                expected_state.update(custom_expected)
        return expected_state

    @staticmethod
    def _capability_costs() -> Dict[str, float]:
        """Costes unitarios orientativos por capacidad; no sustituyen los costes de arista."""
        return {
            "open_application": 3.0,
            "activate_window": 1.0,
            "navigate": 2.0,
            "focus_element": 1.0,
            "type_text": 1.0,
            "press_key": 0.5,
            "close_application": 2.0,
            "search": 3.0,
            "wait_for_state": 2.0,
        }

    @staticmethod
    def _cost_for_capability(capability: str, costs: Dict[str, float]) -> float:
        """Resuelve alias frecuentes manteniendo un coste por defecto conservador."""
        name = str(capability).strip().lower()
        aliases = {
            "open": "open_application",
            "application_open": "open_application",
            "focus_application": "activate_window",
            "application_active": "activate_window",
            "navigation": "navigate",
            "text_typed": "type_text",
            "key_pressed": "press_key",
            "search_performed": "search",
        }
        return costs.get(aliases.get(name, name), 1.0)

    # ======================================================================
    # API PÚBLICA DE CACHÉ / ESTADÍSTICAS
    # ======================================================================

    def clear_cache(self) -> None:
        """Limpia la caché de estimaciones heurísticas."""
        self.heuristic_cache.clear()
        _log("info", "[HEURISTIC] Caché de heurísticas limpiada", "clear_cache", 627)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Devuelve estadísticas y configuración de la caché."""
        return {
            "cache_size": len(self.heuristic_cache),
            "cache_max_size": self.max_cache_size,
            "heuristic_type": self.heuristic_type.value,
            "weight": self.weight,
            "custom_heuristic": self.custom_heuristic is not None,
        }


class HeuristicFactory:
    """Factoría para crear heurísticas con configuraciones frecuentes."""

    @staticmethod
    def create_uniform_heuristic(weight: float = 1.0) -> Heuristic:
        """Crea una heurística constante."""
        return Heuristic(HeuristicType.UNIFORM, weight)

    @staticmethod
    def create_goal_distance_heuristic(weight: float = 1.0) -> Heuristic:
        """Crea una heurística basada en la distancia al objetivo."""
        return Heuristic(HeuristicType.GOAL_DISTANCE, weight)

    @staticmethod
    def create_capability_based_heuristic(weight: float = 1.0) -> Heuristic:
        """Crea una heurística basada en capacidades pendientes."""
        return Heuristic(HeuristicType.CAPABILITY_BASED, weight)

    @staticmethod
    def create_state_similarity_heuristic(weight: float = 1.0) -> Heuristic:
        """Crea una heurística basada en similitud de estado."""
        return Heuristic(HeuristicType.STATE_SIMILARITY, weight)

    @staticmethod
    def create_custom_heuristic(
        heuristic_func: CustomHeuristic,
        weight: float = 1.0,
    ) -> Heuristic:
        """Crea una heurística personalizada validando su callback."""
        if not callable(heuristic_func):
            raise TypeError("heuristic_func debe ser invocable")
        return Heuristic(HeuristicType.GOAL_DISTANCE, weight, heuristic_func)


__all__ = [
    "HeuristicType",
    "Heuristic",
    "HeuristicFactory",
]
