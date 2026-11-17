"""Canal unico de aclaracion y confirmacion con el usuario (4.5.7).

El canal NO ejecuta acciones ni habla ni escucha: guarda la solicitud pendiente
(una sola a la vez), interpreta la respuesta del usuario y devuelve al llamador
el dato con el que reanudar el Goal o la Task. Ear, Mouth y Brain siguen siendo
quienes preguntan, escuchan y ejecutan.

- Vocabulario de confirmacion: el mismo de ``main.py`` (si, claro, ok, vale,
  dale, hazlo), comparado por palabras completas y sin acentos.
- Aclaracion: los candidatos salen de ``ApplicationResolutionResult``
  (``app`` + ``alternatives``, ``is_ambiguous``, ``ambiguity_reason``).
- Confirmacion: no existe una politica de acciones destructivas en el
  proyecto; solo se consumen campos existentes: ``PreflightResult.
  requires_elevation`` y ``ActionInfo.tags`` (``CONFIRMATION_TAGS``).
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.core.log import get_logger

logger = get_logger(__name__)

# Vocabulario de main.py (prediccion aceptada), sin acentos.
CONFIRMATION_WORDS = ("si", "claro", "ok", "vale", "dale", "hazlo")
REJECTION_WORDS = ("no", "nop", "negativo")
CANCEL_WORDS = ("cancela", "cancelar", "cancelalo", "olvidalo", "olvida", "anula", "anulalo", "dejalo")
ORDINALS = {
    "primera": 0, "primero": 0, "uno": 0, "1": 0,
    "segunda": 1, "segundo": 1, "dos": 1, "2": 1,
    "tercera": 2, "tercero": 2, "tres": 2, "3": 2,
}
# Etiquetas de ActionInfo que exigen confirmacion. Hoy ninguna accion
# registrada las declara: solo ``requires_elevation`` provoca confirmacion.
CONFIRMATION_TAGS = frozenset({"requires_confirmation", "destructive"})

DEFAULT_TTL_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 2
# Una respuesta sin vocabulario conocido y con mas palabras se trata como una
# peticion nueva (fuera de contexto) y no como respuesta.
NEW_REQUEST_MIN_WORDS = 4


def normalize_answer(text: Optional[str]) -> str:
    """Minusculas, sin acentos ni puntuacion y con espacios simples."""
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _name_of(candidate: Any) -> str:
    for attr in ("name", "display_name", "app_name"):
        value = getattr(candidate, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(candidate).strip()


@dataclass
class ClarificationRequest:
    """Solicitud pendiente (4.5.7.2 aclaracion / 4.5.7.3 confirmacion)."""

    kind: str  # "clarification" | "confirmation"
    reason: str
    question: str
    candidates: List[str] = field(default_factory=list)
    # Dato con el que el llamador reanuda (Goal, Task, accion y parametros).
    resume: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    attempts: int = 0

    def __post_init__(self) -> None:
        if self.kind not in ("clarification", "confirmation"):
            raise ValueError(f"Tipo de solicitud no valido: {self.kind}")
        if self.kind == "clarification" and not self.candidates:
            raise ValueError("Una aclaracion necesita al menos un candidato")

    @property
    def expires_at(self) -> float:
        return self.created_at + max(0.0, float(self.ttl_seconds))

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (time.time() if now is None else now) >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "kind": self.kind,
            "reason": self.reason,
            "question": self.question,
            "candidates": list(self.candidates),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "resume_keys": sorted(self.resume.keys()),
        }


@dataclass
class AnswerInterpretation:
    """``kind``: accept | reject | cancel | choice | silence | ambiguous | new_request."""

    kind: str
    choice: Optional[str] = None
    normalized: str = ""


@dataclass
class ClarificationOutcome:
    """
    Resultado de ``ClarificationChannel.respond``.

    ``status``: resolved (aclaracion elegida o confirmacion aceptada), rejected,
    cancelled, reask, exhausted, expired, replaced_by_new_request, no_pending.
    ``resume`` solo viene con ``resolved``; el canal ya no guarda la solicitud,
    por lo que no se puede resolver dos veces (4.5.7.6).
    """

    status: str
    request: Optional[ClarificationRequest] = None
    choice: Optional[str] = None
    question: Optional[str] = None
    resume: Optional[Dict[str, Any]] = None

    @property
    def should_resume(self) -> bool:
        return self.status == "resolved"


def clarification_from_resolution(
    resolution: Any,
    resume: Dict[str, Any],
    question: Optional[str] = None,
    max_candidates: int = 3,
) -> Optional[ClarificationRequest]:
    """
    Crea una aclaracion desde un ``ApplicationResolutionResult`` ambiguo.
    Devuelve None si la resolucion no es ambigua o no hay candidatos.
    """
    if resolution is None or not getattr(resolution, "is_ambiguous", False):
        return None
    names: List[str] = []
    for candidate in [getattr(resolution, "app", None)] + list(getattr(resolution, "alternatives", None) or []):
        if candidate is None:
            continue
        name = _name_of(candidate)
        if name and name not in names:
            names.append(name)
    names = names[: max(1, int(max_candidates))]
    if not names:
        return None
    text = question or "Te refieres a %s?" % (" o ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " o " + names[-1])
    return ClarificationRequest(
        kind="clarification",
        reason=str(getattr(resolution, "ambiguity_reason", None) or "resolucion ambigua"),
        question=text,
        candidates=names,
        resume=dict(resume or {}),
    )


def confirmation_reason(action_info: Any = None, preflight: Any = None) -> Optional[str]:
    """Motivo de confirmacion segun campos existentes, o None si no hace falta."""
    if preflight is not None and bool(getattr(preflight, "requires_elevation", False)):
        return "requiere elevacion de privilegios"
    tags = {str(tag).strip().lower() for tag in (getattr(action_info, "tags", None) or [])}
    marked = sorted(tags & CONFIRMATION_TAGS)
    if marked:
        return "accion marcada: %s" % ", ".join(marked)
    return None


def confirmation_for_action(
    action_label: str,
    resume: Dict[str, Any],
    action_info: Any = None,
    preflight: Any = None,
    reason: Optional[str] = None,
    question: Optional[str] = None,
) -> Optional[ClarificationRequest]:
    """
    Crea una confirmacion si la accion la exige (4.5.7.3) o si el llamador da
    un ``reason`` explicito (p. ej. confianza media de transcripcion, 4.5.6.10).
    """
    motive = reason or confirmation_reason(action_info, preflight)
    if not motive:
        return None
    return ClarificationRequest(
        kind="confirmation",
        reason=motive,
        question=question or "Quieres que %s?" % str(action_label).strip(),
        resume=dict(resume or {}),
    )


def interpret_answer(request: ClarificationRequest, text: Optional[str]) -> AnswerInterpretation:
    """Interpreta la respuesta del usuario (4.5.7.5) sin conjeturas."""
    normalized = normalize_answer(text)
    if not normalized:
        return AnswerInterpretation("silence", normalized=normalized)
    tokens = normalized.split()
    token_set = set(tokens)
    if token_set & set(CANCEL_WORDS):
        return AnswerInterpretation("cancel", normalized=normalized)
    confirm = bool(token_set & set(CONFIRMATION_WORDS))
    reject = bool(token_set & set(REJECTION_WORDS))

    if request.kind == "clarification":
        padded = f" {normalized} "
        matches = [
            name for name in request.candidates
            if normalize_answer(name) and f" {normalize_answer(name)} " in padded
        ]
        # "visual studio code" contiene "visual studio": gana el nombre mas largo.
        matches = [
            name for name in matches
            if not any(
                other != name and f" {normalize_answer(name)} " in f" {normalize_answer(other)} "
                for other in matches
            )
        ]
        ordinal = [ORDINALS[t] for t in tokens if t in ORDINALS and ORDINALS[t] < len(request.candidates)]
        for index in ordinal:
            if request.candidates[index] not in matches:
                matches.append(request.candidates[index])
        if len(matches) == 1 and not reject:
            return AnswerInterpretation("choice", choice=matches[0], normalized=normalized)
        if len(matches) > 1:
            return AnswerInterpretation("ambiguous", normalized=normalized)
        if confirm and not reject and len(request.candidates) == 1:
            return AnswerInterpretation("choice", choice=request.candidates[0], normalized=normalized)
        if reject and not confirm and not matches:
            return AnswerInterpretation("reject", normalized=normalized)
    else:
        if confirm and not reject:
            return AnswerInterpretation("accept", normalized=normalized)
        if reject and not confirm:
            return AnswerInterpretation("reject", normalized=normalized)
        if confirm and reject:
            return AnswerInterpretation("ambiguous", normalized=normalized)

    if len(tokens) >= NEW_REQUEST_MIN_WORDS and not confirm and not reject:
        return AnswerInterpretation("new_request", normalized=normalized)
    return AnswerInterpretation("ambiguous", normalized=normalized)


class ClarificationChannel:
    """
    Una unica solicitud pendiente a la vez (4.5.7.4). Mientras espera no se
    ejecuta nada: el canal solo devuelve ``resume`` cuando la respuesta es
    valida. Una solicitud nueva reemplaza a la pendiente; una respuesta que es
    una orden nueva cancela la pendiente y se devuelve al llamador.
    """

    def __init__(
        self,
        conversation_memory: Any = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._memory = conversation_memory
        self._clock = clock
        self._pending: Optional[ClarificationRequest] = None
        self._lock = threading.RLock()

    def _persist(self, request: Optional[ClarificationRequest]) -> None:
        """Refleja la solicitud pendiente en la memoria de conversacion existente."""
        update = getattr(self._memory, "update_world_state", None)
        if not callable(update):
            return
        try:
            update({"pending_clarification": request.to_dict() if request else None})
        except Exception as exc:
            logger.warning("No se pudo guardar la aclaracion pendiente en memoria: %s", exc)

    def ask(self, request: ClarificationRequest) -> Optional[ClarificationRequest]:
        """Registra la solicitud; devuelve la que reemplaza, si habia una."""
        with self._lock:
            previous = self._pending
            request.created_at = self._clock()
            self._pending = request
            if previous is not None:
                logger.info(
                    "Aclaracion %s reemplazada por %s", previous.request_id, request.request_id
                )
            logger.info(
                "Solicitud de %s %s: %s (motivo: %s)",
                request.kind, request.request_id, request.question, request.reason,
            )
            self._persist(request)
            return previous

    def get_pending(self) -> Optional[ClarificationRequest]:
        with self._lock:
            if self._pending is not None and self._pending.is_expired(self._clock()):
                logger.info("Aclaracion %s caducada", self._pending.request_id)
                self._pending = None
                self._persist(None)
            return self._pending

    @property
    def has_pending(self) -> bool:
        return self.get_pending() is not None

    def cancel_pending(self, reason: str = "cancelada") -> Optional[ClarificationRequest]:
        with self._lock:
            previous = self._pending
            self._pending = None
            if previous is not None:
                logger.info("Aclaracion %s descartada: %s", previous.request_id, reason)
                self._persist(None)
            return previous

    def respond(self, text: Optional[str]) -> ClarificationOutcome:
        with self._lock:
            request = self._pending
            if request is None:
                return ClarificationOutcome("no_pending")
            if request.is_expired(self._clock()):
                self.cancel_pending("caducada")
                return ClarificationOutcome("expired", request=request)
            answer = interpret_answer(request, text)
            logger.info(
                "Respuesta a %s %s: %s (%s)",
                request.kind, request.request_id, answer.kind, answer.choice,
            )
            if answer.kind in ("choice", "accept"):
                self._pending = None
                self._persist(None)
                return ClarificationOutcome(
                    "resolved", request=request, choice=answer.choice, resume=dict(request.resume)
                )
            if answer.kind == "reject":
                self.cancel_pending("rechazada")
                return ClarificationOutcome("rejected", request=request)
            if answer.kind == "cancel":
                self.cancel_pending("cancelada por el usuario")
                return ClarificationOutcome("cancelled", request=request)
            if answer.kind == "new_request":
                self.cancel_pending("reemplazada por una peticion nueva")
                return ClarificationOutcome("replaced_by_new_request", request=request)
            request.attempts += 1
            if request.attempts >= request.max_attempts:
                self.cancel_pending("sin respuesta valida tras %s intentos" % request.attempts)
                return ClarificationOutcome("exhausted", request=request)
            self._persist(request)
            return ClarificationOutcome("reask", request=request, question=request.question)


_channel: Optional[ClarificationChannel] = None
_channel_lock = threading.Lock()


def get_clarification_channel() -> ClarificationChannel:
    global _channel
    with _channel_lock:
        if _channel is None:
            _channel = ClarificationChannel()
        return _channel


__all__ = [
    "CONFIRMATION_WORDS",
    "CONFIRMATION_TAGS",
    "AnswerInterpretation",
    "ClarificationChannel",
    "ClarificationOutcome",
    "ClarificationRequest",
    "clarification_from_resolution",
    "confirmation_for_action",
    "confirmation_reason",
    "get_clarification_channel",
    "interpret_answer",
    "normalize_answer",
]
