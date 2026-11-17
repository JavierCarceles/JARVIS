"""Configuracion tipada y validable del sistema de optimizacion de JARVIS.

Define parametros por subsistema, modos predefinidos y una representacion
serializable. Este modulo no ejecuta acciones ni realiza optimizaciones.
"""

from __future__ import annotations
from typing import Optional
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Type, TypeVar

from src.core.log import get_logger

logger = get_logger(__name__)


class OptimizationMode(Enum):
    """Modos de operacion del sistema de optimizacion."""

    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"
    LEARNING_ONLY = "learning_only"


def _coerce_bool(value: Any, field_name: str) -> bool:
    """Convierte booleanos habituales sin tratar cualquier texto como True."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "s\u00ed", "si", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    raise TypeError(f"'{field_name}' debe ser booleano; recibido {value!r}")


def _coerce_int(value: Any, field_name: str) -> int:
    """Convierte a entero y rechaza booleanos y valores fraccionarios."""
    if isinstance(value, bool):
        raise TypeError(f"'{field_name}' debe ser entero, no booleano")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"'{field_name}' debe ser entero; recibido {value!r}") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"'{field_name}' debe ser un entero finito; recibido {value!r}")
    return int(numeric)


def _coerce_float(value: Any, field_name: str) -> float:
    """Convierte a float; la validacion de rangos se realiza en validate_config."""
    if isinstance(value, bool):
        raise TypeError(f"'{field_name}' debe ser numerico, no booleano")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"'{field_name}' debe ser numerico; recibido {value!r}") from exc


def _coerce_string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Una cadena representa un unico patron, no una lista de caracteres.
        return [value] if value else []
    if not isinstance(value, (list, tuple, set)):
        raise TypeError(f"'{field_name}' debe ser una secuencia de cadenas")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"Todos los elementos de '{field_name}' deben ser cadenas")
        if item not in result:
            result.append(item)
    return result


def _normalize_fields(instance: Any, integers: tuple[str, ...], floats: tuple[str, ...], booleans: tuple[str, ...]) -> None:
    for name in integers:
        setattr(instance, name, _coerce_int(getattr(instance, name), name))
    for name in floats:
        setattr(instance, name, _coerce_float(getattr(instance, name), name))
    for name in booleans:
        setattr(instance, name, _coerce_bool(getattr(instance, name), name))


@dataclass
class RouteCacheConfig:
    """Configuracion del cache de rutas (FASE 17.1)."""

    max_size: int = 1000
    default_ttl: float = 3600.0
    enable_lru: bool = True
    enable_preload: bool = True
    preload_patterns: List[str] = field(
        default_factory=lambda: ["navigate_*", "open_*", "search_*"]
    )
    compression_enabled: bool = True
    enable_stats: bool = True

    def __post_init__(self) -> None:
        _normalize_fields(self, ("max_size",), ("default_ttl",), ("enable_lru", "enable_preload", "compression_enabled", "enable_stats"))
        self.preload_patterns = _coerce_string_list(self.preload_patterns, "preload_patterns")


@dataclass
class CostLearningConfig:
    """Configuracion del aprendizaje de costes (FASE 17.6)."""

    learning_rate: float = 0.1
    discount_factor: float = 0.95
    min_executions_for_model: int = 5
    max_executions_per_node: int = 1000
    enable_real_time_updates: bool = True
    cost_threshold_improvement: float = 0.1
    enable_context_aware_learning: bool = True
    success_weight: float = 2.0
    failure_penalty: float = 1.0

    def __post_init__(self) -> None:
        _normalize_fields(
            self,
            ("min_executions_for_model", "max_executions_per_node"),
            ("learning_rate", "discount_factor", "cost_threshold_improvement", "success_weight", "failure_penalty"),
            ("enable_real_time_updates", "enable_context_aware_learning"),
        )


@dataclass
class RedundancyRemovalConfig:
    """Configuracion de eliminacion de redundancias (FASE 17.3)."""

    enable_state_tracking: bool = True
    enable_effect_analysis: bool = True
    max_plan_length_for_analysis: int = 20
    redundancy_threshold: float = 0.8
    enable_alternative_finding: bool = True
    alternative_search_depth: int = 3

    def __post_init__(self) -> None:
        _normalize_fields(
            self,
            ("max_plan_length_for_analysis", "alternative_search_depth"),
            ("redundancy_threshold",),
            ("enable_state_tracking", "enable_effect_analysis", "enable_alternative_finding"),
        )


@dataclass
class ContextAwareConfig:
    """Configuracion de optimizacion basada en contexto (FASE 17.5)."""

    enable_time_patterns: bool = True
    enable_user_patterns: bool = True
    enable_application_patterns: bool = True
    pattern_history_size: int = 100
    time_window_hours: int = 24
    user_preference_weight: float = 0.3
    time_pattern_weight: float = 0.2
    success_pattern_weight: float = 0.5
    enable_adaptive_weights: bool = True

    def __post_init__(self) -> None:
        _normalize_fields(
            self,
            ("pattern_history_size", "time_window_hours"),
            ("user_preference_weight", "time_pattern_weight", "success_pattern_weight"),
            ("enable_time_patterns", "enable_user_patterns", "enable_application_patterns", "enable_adaptive_weights"),
        )


@dataclass
class AlternativeSelectionConfig:
    """Configuracion de seleccion de alternativas (FASE 17.4)."""

    enable_alternative_generation: bool = True
    max_alternatives_per_plan: int = 5
    enable_cost_comparison: bool = True
    enable_success_rate_comparison: bool = True
    enable_execution_time_comparison: bool = True
    cost_weight: float = 0.4
    success_rate_weight: float = 0.4
    execution_time_weight: float = 0.2
    min_success_rate_threshold: float = 0.7

    def __post_init__(self) -> None:
        _normalize_fields(
            self,
            ("max_alternatives_per_plan",),
            ("cost_weight", "success_rate_weight", "execution_time_weight", "min_success_rate_threshold"),
            ("enable_alternative_generation", "enable_cost_comparison", "enable_success_rate_comparison", "enable_execution_time_comparison"),
        )


@dataclass
class PerformanceMonitoringConfig:
    """Configuracion de monitoreo de rendimiento (FASE 17.7)."""

    enable_detailed_logging: bool = True
    enable_performance_metrics: bool = True
    enable_bottleneck_detection: bool = True
    enable_memory_profiling: bool = False
    metrics_collection_interval: float = 60.0
    performance_threshold_warning: float = 1.0
    performance_threshold_critical: float = 5.0
    enable_auto_adjustment: bool = True
    auto_adjustment_sensitivity: float = 0.1

    def __post_init__(self) -> None:
        _normalize_fields(
            self,
            (),
            ("metrics_collection_interval", "performance_threshold_warning", "performance_threshold_critical", "auto_adjustment_sensitivity"),
            ("enable_detailed_logging", "enable_performance_metrics", "enable_bottleneck_detection", "enable_memory_profiling", "enable_auto_adjustment"),
        )


T = TypeVar("T")


@dataclass
class OptimizationConfig:
    """Configuracion completa del sistema de optimizacion (FASE 17)."""

    mode: OptimizationMode = OptimizationMode.BALANCED
    route_cache: RouteCacheConfig = field(default_factory=RouteCacheConfig)
    cost_learning: CostLearningConfig = field(default_factory=CostLearningConfig)
    redundancy_removal: RedundancyRemovalConfig = field(default_factory=RedundancyRemovalConfig)
    context_aware: ContextAwareConfig = field(default_factory=ContextAwareConfig)
    alternative_selection: AlternativeSelectionConfig = field(default_factory=AlternativeSelectionConfig)
    performance_monitoring: PerformanceMonitoringConfig = field(default_factory=PerformanceMonitoringConfig)
    enable_optimization: bool = True
    optimization_timeout: float = 30.0
    max_memory_usage_mb: int = 512
    enable_fallback_to_normal: bool = True
    enable_graceful_degradation: bool = True
    debug_mode: bool = False
    enable_verbose_logging: bool = False
    enable_performance_tracing: bool = False

    def __post_init__(self) -> None:
        self.mode = self._coerce_mode(self.mode)
        self._coerce_nested("route_cache", RouteCacheConfig)
        self._coerce_nested("cost_learning", CostLearningConfig)
        self._coerce_nested("redundancy_removal", RedundancyRemovalConfig)
        self._coerce_nested("context_aware", ContextAwareConfig)
        self._coerce_nested("alternative_selection", AlternativeSelectionConfig)
        self._coerce_nested("performance_monitoring", PerformanceMonitoringConfig)

        _normalize_fields(
            self,
            ("max_memory_usage_mb",),
            ("optimization_timeout",),
            ("enable_optimization", "enable_fallback_to_normal", "enable_graceful_degradation", "debug_mode", "enable_verbose_logging", "enable_performance_tracing"),
        )

    @staticmethod
    def _coerce_mode(value: Any) -> OptimizationMode:
        if isinstance(value, OptimizationMode):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            try:
                return OptimizationMode(normalized)
            except ValueError:
                try:
                    return OptimizationMode[normalized.upper()]
                except KeyError as exc:
                    raise ValueError(f"Modo de optimizacion desconocido: {value!r}") from exc
        raise TypeError("mode debe ser OptimizationMode o una cadena valida")

    def _coerce_nested(self, name: str, config_type: Type[T]) -> None:
        value = getattr(self, name)
        if isinstance(value, config_type):
            return
        if isinstance(value, Mapping):
            setattr(self, name, config_type(**dict(value)))
            return
        if value is None:
            # None se interpreta como ausencia de configuracion anidada.
            setattr(self, name, config_type())
            return
        raise TypeError(f"Configuracion invalida para '{name}': {type(value)!r}")

    @classmethod
    def get_aggressive_config(cls) -> "OptimizationConfig":
        """Obtiene configuracion para modo agresivo."""
        config = cls()
        config.mode = OptimizationMode.AGGRESSIVE
        config.route_cache.max_size = 2000
        config.route_cache.enable_preload = True
        config.cost_learning.learning_rate = 0.2
        config.redundancy_removal.enable_alternative_finding = True
        config.alternative_selection.max_alternatives_per_plan = 10
        return config

    @classmethod
    def get_conservative_config(cls) -> "OptimizationConfig":
        """Obtiene configuracion para modo conservador."""
        config = cls()
        config.mode = OptimizationMode.CONSERVATIVE
        config.route_cache.max_size = 500
        config.route_cache.enable_preload = False
        config.cost_learning.learning_rate = 0.05
        config.redundancy_removal.enable_alternative_finding = False
        config.alternative_selection.max_alternatives_per_plan = 3
        return config

    @classmethod
    def get_learning_only_config(cls) -> "OptimizationConfig":
        """Obtiene configuracion para registrar aprendizaje sin aplicar optimizaciones."""
        config = cls()
        config.mode = OptimizationMode.LEARNING_ONLY
        config.route_cache.max_size = 100
        config.route_cache.enable_preload = False
        config.cost_learning.learning_rate = 0.15
        config.cost_learning.enable_real_time_updates = True
        config.redundancy_removal.enable_alternative_finding = False
        config.alternative_selection.enable_alternative_generation = False
        config.enable_optimization = False
        return config

    def get_optimization_enabled(self) -> Dict[str, bool]:
        """Devuelve el estado efectivo de cada tecnica para el modo actual."""
        global_enabled = bool(self.enable_optimization)
        learning_only = self.mode == OptimizationMode.LEARNING_ONLY
        return {
            "route_cache": global_enabled and not learning_only and self.route_cache.max_size > 0,
            "cost_learning": (
                self.cost_learning.enable_real_time_updates
                and (global_enabled or learning_only)
            ),
            "redundancy_removal": global_enabled and not learning_only and self.redundancy_removal.enable_effect_analysis,
            "context_aware": global_enabled and not learning_only and (
                self.context_aware.enable_time_patterns
                or self.context_aware.enable_user_patterns
                or self.context_aware.enable_application_patterns
            ),
            "alternative_selection": global_enabled and not learning_only and self.alternative_selection.enable_alternative_generation,
            "performance_monitoring": global_enabled and not learning_only and self.performance_monitoring.enable_performance_metrics,
        }

    def validate_config(self) -> List[str]:
        """Valida rangos y coherencia; una lista vacia indica configuracion valida."""
        warnings: List[str] = []

        def finite(name: str, value: Any, *, minimum: Optional[float] = None, maximum: Optional[float] = None, strict_minimum: bool = False) -> None:
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                warnings.append(f"{name} debe ser num\u00e9rico")
                return
            if not math.isfinite(number):
                warnings.append(f"{name} debe ser finito")
                return
            if minimum is not None and (number <= minimum if strict_minimum else number < minimum):
                comparator = "mayor que" if strict_minimum else "mayor o igual que"
                warnings.append(f"{name} debe ser {comparator} {minimum:g}")
            if maximum is not None and number > maximum:
                warnings.append(f"{name} debe ser menor o igual que {maximum:g}")

        rc = self.route_cache
        finite("El tama\u00f1o del cach\u00e9", rc.max_size, minimum=0, strict_minimum=True)
        finite("El TTL del cach\u00e9", rc.default_ttl, minimum=0)

        cl = self.cost_learning
        finite("La tasa de aprendizaje", cl.learning_rate, minimum=0, maximum=1)
        finite("El factor de descuento", cl.discount_factor, minimum=0, maximum=1)
        finite("El m\u00ednimo de ejecuciones para el modelo", cl.min_executions_for_model, minimum=0)
        finite("El m\u00e1ximo de ejecuciones por nodo", cl.max_executions_per_node, minimum=0, strict_minimum=True)
        finite("El umbral de mejora de coste", cl.cost_threshold_improvement, minimum=0)
        finite("El peso de \u00e9xito", cl.success_weight, minimum=0)
        finite("La penalizaci\u00f3n por fallo", cl.failure_penalty, minimum=0)

        rr = self.redundancy_removal
        finite("La longitud m\u00e1xima de an\u00e1lisis", rr.max_plan_length_for_analysis, minimum=0, strict_minimum=True)
        finite("El umbral de redundancia", rr.redundancy_threshold, minimum=0, maximum=1)
        finite("La profundidad de b\u00fasqueda de alternativas", rr.alternative_search_depth, minimum=0)

        ca = self.context_aware
        finite("El historial de patrones", ca.pattern_history_size, minimum=0, strict_minimum=True)
        finite("La ventana temporal", ca.time_window_hours, minimum=0, strict_minimum=True)
        context_weights = (ca.user_preference_weight, ca.time_pattern_weight, ca.success_pattern_weight)
        for name, weight in zip(("Peso de preferencia del usuario", "Peso de patr\u00f3n temporal", "Peso de patr\u00f3n de \u00e9xito"), context_weights):
            finite(name, weight, minimum=0)

        alt = self.alternative_selection
        finite("El n\u00famero m\u00e1ximo de alternativas", alt.max_alternatives_per_plan, minimum=0)
        weights = (alt.cost_weight, alt.success_rate_weight, alt.execution_time_weight)
        for name, weight in zip(("Peso de coste", "Peso de tasa de \u00e9xito", "Peso de tiempo de ejecuci\u00f3n"), weights):
            finite(name, weight, minimum=0)
        try:
            numeric_weights = [float(weight) for weight in weights]
            weights_valid = all(math.isfinite(weight) and weight >= 0 for weight in numeric_weights)
        except (TypeError, ValueError, OverflowError):
            weights_valid = False
        if weights_valid and abs(sum(numeric_weights) - 1.0) > 0.01:
            warnings.append("La suma de pesos de selecci\u00f3n de alternativas debe ser 1.0")
        finite("El umbral m\u00ednimo de \u00e9xito", alt.min_success_rate_threshold, minimum=0, maximum=1)

        perf = self.performance_monitoring
        finite("El intervalo de recopilaci\u00f3n", perf.metrics_collection_interval, minimum=0, strict_minimum=True)
        finite("El umbral de advertencia", perf.performance_threshold_warning, minimum=0)
        finite("El umbral cr\u00edtico", perf.performance_threshold_critical, minimum=0)
        try:
            warning_threshold = float(perf.performance_threshold_warning)
            critical_threshold = float(perf.performance_threshold_critical)
            if (math.isfinite(warning_threshold)
                    and math.isfinite(critical_threshold)
                    and critical_threshold <= warning_threshold):
                warnings.append("El umbral cr\u00edtico debe ser mayor que el umbral de advertencia")
        except (TypeError, ValueError, OverflowError):
            # Los errores de tipo ya se reportan en los chequeos finite anteriores.
            pass
        finite("La sensibilidad de ajuste autom\u00e1tico", perf.auto_adjustment_sensitivity, minimum=0)

        finite("El timeout de optimizaci\u00f3n", self.optimization_timeout, minimum=0, strict_minimum=True)
        finite("El l\u00edmite de memoria", self.max_memory_usage_mb, minimum=0, strict_minimum=True)
        return warnings

    def validate_or_raise(self) -> None:
        """Lanza ValueError si validate_config detecta problemas."""
        warnings = self.validate_config()
        if warnings:
            raise ValueError("Configuracion de optimizacion invalida: " + "; ".join(warnings))

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve una copia serializable de toda la configuracion."""
        data = asdict(self)
        data["mode"] = self.mode.value
        return data

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "OptimizationConfig":
        """Construye configuracion desde un diccionario parcial o completo."""
        if not isinstance(config_dict, dict):
            raise TypeError("config_dict debe ser un diccionario")

        data = dict(config_dict)
        nested_types: Dict[str, Type[Any]] = {
            "route_cache": RouteCacheConfig,
            "cost_learning": CostLearningConfig,
            "redundancy_removal": RedundancyRemovalConfig,
            "context_aware": ContextAwareConfig,
            "alternative_selection": AlternativeSelectionConfig,
            "performance_monitoring": PerformanceMonitoringConfig,
        }

        for key, config_type in nested_types.items():
            value = data.get(key)
            if value is None:
                data.pop(key, None)
            elif isinstance(value, Mapping):
                data[key] = config_type(**dict(value))
            elif not isinstance(value, config_type):
                raise TypeError(f"Configuracion invalida para '{key}': {type(value)!r}")

        return cls(**data)


__all__ = [
    "OptimizationMode",
    "RouteCacheConfig",
    "CostLearningConfig",
    "RedundancyRemovalConfig",
    "ContextAwareConfig",
    "AlternativeSelectionConfig",
    "PerformanceMonitoringConfig",
    "OptimizationConfig",
]
