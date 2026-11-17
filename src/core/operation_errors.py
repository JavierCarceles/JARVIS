"""
Errores estructurados, evidencia redactada y reintentos acotados.

Contrato comun para propagar fallos concretos de deteccion, resolucion,
preflight, lanzamiento, proceso, ventana, permisos, calibracion, entrada y
verificacion (roadmap 3.8.8.1-3.8.8.4) sin exponer rutas privadas ni secretos.

Piezas:

* ``OperationStage``: etapa en la que fallo la operacion.
* ``ErrorCode``: codigos estables (cadenas) reutilizables por todos los modulos.
* ``OperationError``: error con etapa, codigo, mensaje, si es reintentable, si
  necesita aclaracion del usuario (con candidatos), evidencia ya redactada e
  instrucciones. ``needs_clarification`` no abre ningun dialogo: el canal de
  aclaracion/confirmacion con el usuario es el de la FASE 4 (4.5.7).
* ``redact_evidence(obj)``: sustituye carpeta de usuario, nombre de usuario,
  credenciales y tokens por marcadores. Se aplica a toda evidencia antes de
  registrarla o devolverla.
* ``RetryPolicy``: reintentos acotados (nunca ilimitados) con espera
  exponencial limitada y registro de operaciones idempotentes ya exitosas, para
  no repetir una apertura que ya tuvo exito.
* ``OperationOutcome``: resultado ``ok``/``error`` con numero de intentos y el
  siguiente paso sugerido (``none``, ``retry``, ``clarify``, ``abort``).

Este modulo no depende de ningun SO ni de modulos de manos/ojos.
"""

from __future__ import annotations

import getpass
import os
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core.log import get_logger

logger = get_logger(__name__)


class OperationStage(str, Enum):
    """Etapa del flujo en la que se produjo el error."""

    DETECTION = "detection"
    RESOLUTION = "resolution"
    PREFLIGHT = "preflight"
    LAUNCH = "launch"
    PROCESS = "process"
    WINDOW = "window"
    PERMISSION = "permission"
    CALIBRATION = "calibration"
    INPUT = "input"
    VERIFICATION = "verification"


class ErrorCode:
    """Codigos estables de error (cadenas) compartidos por los modulos."""

    NOT_INSTALLED = "not_installed"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    TARGET_NOT_LOCALIZABLE = "target_not_localizable"
    PREFLIGHT_BLOCKED = "preflight_blocked"
    UNSUPPORTED_URI = "unsupported_uri"
    UNSAFE_ARGUMENT = "unsafe_argument"
    INVALID_ARGUMENT = "invalid_argument"
    PERMISSION_DENIED = "permission_denied"
    GATEKEEPER_BLOCKED = "gatekeeper_blocked"
    ELEVATION_REQUIRED = "elevation_required"
    ADAPTER_MISSING = "adapter_missing"
    NOT_SUPPORTED = "not_supported"
    LAUNCH_FAILED = "launch_failed"
    PROCESS_NOT_FOUND = "process_not_found"
    WINDOW_NOT_FOUND = "window_not_found"
    TIMEOUT = "timeout"
    ALREADY_OPEN_REQUIRES_CLOSED = "already_open_requires_closed"
    NOT_CALIBRABLE = "not_calibrable"
    CALIBRATION_FAILED = "calibration_failed"
    VERIFICATION_FAILED = "verification_failed"
    RETRY_LIMIT = "retry_limit"
    INTERNAL = "internal"


# ============================================================================
# REDACCION DE EVIDENCIA
# ============================================================================

REDACTED = "<REDACTADO>"
HOME_MARKER = "<HOME>"
USER_MARKER = "<USUARIO>"

_SECRET_KEY_PATTERN = re.compile(
    r"(pass(word)?|passwd|secret|token|api[_-]?key|apikey|auth|cookie|credential|session[_-]?id|bearer)",
    re.IGNORECASE,
)
_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(pass(?:word)?|passwd|secret|token|api[_-]?key|apikey|auth|bearer)\b(\s*[=:]\s*|\s+)([^\s&;,'\"]+)"
)
_WINDOWS_USER_PATH = re.compile(r"(?i)([a-z]:[\\/]+users[\\/]+)([^\\/]+)")
_POSIX_USER_PATH = re.compile(r"(/(?:Users|home)/)([^/\s]+)")


def _home_variants() -> List[str]:
    variants: List[str] = []
    try:
        home = os.path.expanduser("~")
        if home and home not in ("~", "/", "\\"):
            variants.append(home)
            variants.append(home.replace("\\", "/"))
    except Exception as exc:  # pragma: no cover - entorno sin HOME
        logger.debug("No se pudo resolver la carpeta de usuario: %s", exc)
    return sorted(set(variants), key=len, reverse=True)


def _current_user() -> str:
    try:
        return getpass.getuser() or ""
    except Exception as exc:  # pragma: no cover - entorno sin usuario
        logger.debug("No se pudo resolver el usuario actual: %s", exc)
        return ""


def redact_text(text: str) -> str:
    """Redacta rutas de usuario, nombre de usuario y secretos en un texto."""
    if not text:
        return text
    result = str(text)
    for home in _home_variants():
        result = result.replace(home, HOME_MARKER)
    result = _WINDOWS_USER_PATH.sub(lambda m: m.group(1) + USER_MARKER, result)
    result = _POSIX_USER_PATH.sub(lambda m: m.group(1) + USER_MARKER, result)
    user = _current_user()
    if user and len(user) >= 3:
        result = re.sub(r"(?i)\b%s\b" % re.escape(user), USER_MARKER, result)
    result = _INLINE_SECRET_PATTERN.sub(lambda m: m.group(1) + m.group(2) + REDACTED, result)
    return result


def redact_evidence(obj: Any, _depth: int = 0) -> Any:
    """Devuelve una copia de ``obj`` sin rutas privadas, usuario ni secretos.

    Recorre diccionarios, listas, tuplas y conjuntos. Las claves con aspecto de
    secreto (password, token, api_key, cookie...) se sustituyen por completo.
    Las cadenas se redactan con ``redact_text``. Otros tipos se devuelven tal
    cual (numeros, booleanos, None) o como su ``repr`` redactado.
    """
    if _depth > 20:
        return REDACTED
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        clean: Dict[Any, Any] = {}
        for key, value in obj.items():
            key_text = str(key)
            if _SECRET_KEY_PATTERN.search(key_text):
                clean[key] = REDACTED
            else:
                clean[key] = redact_evidence(value, _depth + 1)
        return clean
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [redact_evidence(v, _depth + 1) for v in obj]
        return items if not isinstance(obj, tuple) else tuple(items)
    if hasattr(obj, "to_dict"):
        try:
            return redact_evidence(obj.to_dict(), _depth + 1)
        except Exception as exc:
            logger.debug("redact_evidence: to_dict fallo: %s", exc)
    return redact_text(repr(obj))


# ============================================================================
# ERROR Y RESULTADO
# ============================================================================


@dataclass
class OperationError:
    """Error estructurado de una operacion.

    ``evidence`` se guarda siempre redactado. ``candidates`` lista alternativas
    (nombres visibles, nunca rutas) cuando ``needs_clarification`` es True.
    """

    stage: OperationStage
    code: str
    message: str
    retryable: bool = False
    needs_clarification: bool = False
    candidates: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    instructions: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.stage, OperationStage):
            try:
                self.stage = OperationStage(str(self.stage))
            except ValueError:
                self.stage = OperationStage.VERIFICATION
        self.message = redact_text(str(self.message or ""))
        self.instructions = redact_text(str(self.instructions or ""))
        self.candidates = [redact_text(str(c)) for c in (self.candidates or [])]
        self.evidence = redact_evidence(dict(self.evidence or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "needs_clarification": self.needs_clarification,
            "candidates": list(self.candidates),
            "evidence": dict(self.evidence),
            "instructions": self.instructions,
        }

    def user_message(self) -> str:
        """Mensaje legible para el usuario (sin rutas ni secretos)."""
        text = self.message
        if self.needs_clarification and self.candidates:
            text += " Opciones: " + ", ".join(self.candidates[:5]) + "."
        if self.instructions:
            text += " " + self.instructions
        return text

    def __str__(self) -> str:
        return "[%s:%s] %s" % (self.stage.value, self.code, self.message)

    @classmethod
    def from_platform_error(
        cls,
        error: Any,
        stage: OperationStage,
        retryable: bool = False,
    ) -> "OperationError":
        """Convierte un ``PlatformError`` del contrato de escritorio."""
        code_value = getattr(getattr(error, "code", None), "value", None) or str(
            getattr(error, "code", ErrorCode.INTERNAL)
        )
        mapped = {
            "not_supported": ErrorCode.NOT_SUPPORTED,
            "permission_denied": ErrorCode.PERMISSION_DENIED,
            "dependency_missing": ErrorCode.ADAPTER_MISSING,
            "not_found": ErrorCode.NOT_FOUND,
            "window_gone": ErrorCode.WINDOW_NOT_FOUND,
            "timeout": ErrorCode.TIMEOUT,
        }.get(code_value, code_value)
        return cls(
            stage=stage,
            code=mapped,
            message=str(getattr(error, "message", "") or str(error)),
            retryable=retryable or code_value == "timeout",
            instructions=str(getattr(error, "instructions", "") or ""),
            evidence={
                "operation": getattr(error, "operation", ""),
                "platform": getattr(error, "platform", ""),
                "platform_code": code_value,
            },
        )


class OperationFailed(RuntimeError):
    """Excepcion que transporta un ``OperationError`` (para APIs que lanzan)."""

    def __init__(self, error: OperationError) -> None:
        super().__init__(error.user_message())
        self.error = error


NEXT_STEP_NONE = "none"
NEXT_STEP_RETRY = "retry"
NEXT_STEP_CLARIFY = "clarify"
NEXT_STEP_ABORT = "abort"


@dataclass
class OperationOutcome:
    """Resultado de una operacion con reintentos acotados."""

    ok: bool
    value: Any = None
    error: Optional[OperationError] = None
    attempts: int = 0
    next_step: str = NEXT_STEP_NONE
    from_idempotency_cache: bool = False

    def to_dict(self) -> Dict[str, Any]:
        value = self.value
        if hasattr(value, "to_dict"):
            try:
                value = value.to_dict()
            except Exception as exc:
                logger.debug("OperationOutcome.to_dict: %s", exc)
        return {
            "ok": self.ok,
            "value": redact_evidence(value),
            "error": self.error.to_dict() if self.error else None,
            "attempts": self.attempts,
            "next_step": self.next_step,
            "from_idempotency_cache": self.from_idempotency_cache,
        }

    @classmethod
    def failure(cls, error: OperationError, attempts: int = 0) -> "OperationOutcome":
        if error.needs_clarification:
            step = NEXT_STEP_CLARIFY
        elif error.retryable:
            step = NEXT_STEP_RETRY
        else:
            step = NEXT_STEP_ABORT
        return cls(False, None, error, attempts, step)


def next_step_for(error: Optional[OperationError]) -> str:
    """Siguiente paso recomendado para un error (o ``none`` si no hay error)."""
    if error is None:
        return NEXT_STEP_NONE
    if error.needs_clarification:
        return NEXT_STEP_CLARIFY
    if error.retryable:
        return NEXT_STEP_RETRY
    return NEXT_STEP_ABORT


# ============================================================================
# REINTENTOS ACOTADOS E IDEMPOTENCIA
# ============================================================================


class IdempotencyRegistry:
    """Registro en memoria de operaciones idempotentes que ya tuvieron exito.

    Cada entrada guarda el valor devuelto, el instante y un validador opcional
    (por ejemplo "el proceso sigue vivo"). Si el validador dice que el efecto
    ya no existe, la entrada se descarta y la operacion puede repetirse.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[str, Tuple[float, Any, Optional[float], Optional[Callable[[Any], bool]]]] = {}

    def mark_success(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        still_valid: Optional[Callable[[Any], bool]] = None,
    ) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), value, ttl_seconds, still_valid)

    def get(self, key: str) -> Tuple[bool, Any]:
        """Devuelve ``(True, valor)`` si la operacion ya tuvo exito y sigue vigente."""
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return False, None
        created, value, ttl, still_valid = entry
        if ttl is not None and time.monotonic() - created > ttl:
            self.forget(key)
            return False, None
        if still_valid is not None:
            try:
                if not still_valid(value):
                    self.forget(key)
                    return False, None
            except Exception as exc:
                logger.debug("Validador de idempotencia fallo para %s: %s", key, exc)
                self.forget(key)
                return False, None
        return True, value

    def forget(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._entries.keys())


_GLOBAL_IDEMPOTENCY = IdempotencyRegistry()


def get_idempotency_registry() -> IdempotencyRegistry:
    """Registro de idempotencia compartido por el proceso."""
    return _GLOBAL_IDEMPOTENCY


class RetryPolicy:
    """Reintentos acotados con espera exponencial limitada.

    ``max_attempts`` es un limite duro (minimo 1, maximo 10). Nunca hay
    reintentos ilimitados. Si se da ``idempotency_key`` y la operacion ya tuvo
    exito vigente, no se vuelve a ejecutar.
    """

    MAX_ATTEMPTS_HARD_LIMIT = 10

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 5.0,
        registry: Optional[IdempotencyRegistry] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.max_attempts = max(1, min(int(max_attempts), self.MAX_ATTEMPTS_HARD_LIMIT))
        self.base_delay = max(0.0, float(base_delay))
        self.max_delay = max(self.base_delay, float(max_delay))
        self.registry = registry or get_idempotency_registry()
        self._sleep = sleep or time.sleep

    def delay_for(self, attempt: int) -> float:
        """Espera antes del intento ``attempt`` (1 = primer reintento)."""
        if attempt <= 0:
            return 0.0
        return min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))

    def run(
        self,
        fn: Callable[[], Any],
        is_success: Callable[[Any], bool],
        is_retryable: Optional[Callable[[Any], bool]] = None,
        idempotency_key: Optional[str] = None,
        to_error: Optional[Callable[[Any], OperationError]] = None,
        success_ttl_seconds: Optional[float] = None,
        still_valid: Optional[Callable[[Any], bool]] = None,
        stage: OperationStage = OperationStage.VERIFICATION,
    ) -> OperationOutcome:
        """Ejecuta ``fn`` hasta ``max_attempts`` veces.

        ``is_retryable(resultado_o_excepcion)`` decide si un fallo admite otro
        intento (por defecto: solo excepciones de timeout). ``to_error``
        convierte el ultimo resultado fallido en ``OperationError``.
        """
        if idempotency_key:
            done, value = self.registry.get(idempotency_key)
            if done:
                logger.info("Operacion idempotente ya realizada; no se repite: %s", redact_text(idempotency_key))
                return OperationOutcome(True, value, None, 0, NEXT_STEP_NONE, from_idempotency_cache=True)

        retryable = is_retryable or (lambda r: isinstance(r, TimeoutError))
        last: Any = None
        attempts = 0
        for attempt in range(self.max_attempts):
            if attempt > 0:
                self._sleep(self.delay_for(attempt))
            attempts = attempt + 1
            try:
                last = fn()
            except Exception as exc:  # el fallo se convierte en resultado
                logger.warning("Intento %s/%s fallo: %s", attempts, self.max_attempts, redact_text(str(exc)))
                last = exc
            else:
                if is_success(last):
                    if idempotency_key:
                        self.registry.mark_success(
                            idempotency_key, last, success_ttl_seconds, still_valid
                        )
                    return OperationOutcome(True, last, None, attempts, NEXT_STEP_NONE)
            try:
                can_retry = bool(retryable(last))
            except Exception as exc:
                logger.debug("is_retryable fallo: %s", exc)
                can_retry = False
            if not can_retry:
                break

        error = self._build_error(last, to_error, stage)
        if attempts >= self.max_attempts and error.retryable:
            error = OperationError(
                stage=error.stage,
                code=ErrorCode.RETRY_LIMIT,
                message="Se alcanzo el limite de %s intentos: %s" % (self.max_attempts, error.message),
                retryable=False,
                needs_clarification=error.needs_clarification,
                candidates=error.candidates,
                evidence=dict(error.evidence, last_code=error.code),
                instructions=error.instructions,
            )
        return OperationOutcome.failure(error, attempts)

    @staticmethod
    def _build_error(
        last: Any,
        to_error: Optional[Callable[[Any], OperationError]],
        stage: OperationStage,
    ) -> OperationError:
        if to_error is not None:
            try:
                return to_error(last)
            except Exception as exc:
                logger.debug("to_error fallo: %s", exc)
        if isinstance(last, OperationError):
            return last
        error = getattr(last, "error", None)
        if isinstance(error, OperationError):
            return error
        if isinstance(last, TimeoutError):
            return OperationError(stage, ErrorCode.TIMEOUT, str(last) or "tiempo agotado", retryable=True)
        if isinstance(last, Exception):
            return OperationError(stage, ErrorCode.INTERNAL, "%s: %s" % (type(last).__name__, last))
        return OperationError(stage, ErrorCode.VERIFICATION_FAILED, "la operacion no tuvo exito")


__all__ = [
    "OperationStage",
    "ErrorCode",
    "OperationError",
    "OperationFailed",
    "OperationOutcome",
    "IdempotencyRegistry",
    "RetryPolicy",
    "get_idempotency_registry",
    "redact_evidence",
    "redact_text",
    "next_step_for",
    "NEXT_STEP_NONE",
    "NEXT_STEP_RETRY",
    "NEXT_STEP_CLARIFY",
    "NEXT_STEP_ABORT",
    "REDACTED",
    "HOME_MARKER",
    "USER_MARKER",
]
