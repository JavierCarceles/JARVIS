"""Comprension robusta de ordenes de voz (4.5.6.10 - 4.5.6.12).

Cadena: texto de Ear -> correccion determinista (4.5.6.7, con correcciones
aprendidas 4.5.6.8) -> LLM solo si hace falta (4.5.6.9, con fallback 4.5.6.11)
-> decision (continuar / confirmar / aclarar, 4.5.6.10). Se ejecuta UNA vez
por frase dentro de ``Brain.think`` antes de interpretar la intencion
(4.5.6.12) y nunca ejecuta acciones: solo devuelve el texto con el que seguir
o la pregunta para el usuario, que pasa por el canal unico de 4.5.7.

Esta desactivada por defecto (``voice_understanding.enabled`` en
``config/config.json``) hasta medirla con el corpus de 4.5.6.2. Sin umbrales
calibrados la politica no usa la confianza, solo la estructura de candidatos.
Las acciones con efectos externos o destructivos se confirman al ejecutarlas
(``confirmation_for_action`` de 4.5.7), no aqui: esta capa no sabe que accion
saldra.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.brain.clarification import (
    ClarificationChannel,
    ClarificationRequest,
    get_clarification_channel,
)
from src.brain.transcript_disambiguation import UNKNOWN_ENTITY, disambiguate, llm_reasons
from src.core.log import get_logger
from src.ear.asr_config import VoiceUnderstandingConfig, load_voice_understanding_config
from src.ear.correction import (
    SOURCE_DETERMINISTIC,
    CorrectionCandidate,
    correct_transcript,
    normalize_text,
)
from src.ear.vocabulary import KIND_APPLICATION, VocabularyEntry, collect_vocabulary

logger = get_logger(__name__)

SOURCE_LLM = "desambiguacion_llm"
SOURCE_USER = "aclaracion_usuario"

DECISION_CONTINUE = "continue"
DECISION_CONFIRM = "confirm"
DECISION_CLARIFY = "clarify"
DECISION_DROPPED = "dropped"
DECISION_EMPTY = "empty"


@dataclass
class UnderstandingResult:
    decision: str
    text: str
    original_text: str
    reply: Optional[str] = None  # lo que hay que decir al usuario
    record: Any = None  # TranscriptionRecord con derivaciones, si lo hay
    request: Optional[ClarificationRequest] = None
    reasons: List[str] = field(default_factory=list)
    llm_status: Optional[str] = None
    correction: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision, "text": self.text, "original_text": self.original_text,
            "reply": self.reply, "reasons": list(self.reasons), "llm_status": self.llm_status,
            "correction": self.correction,
            "request": self.request.to_dict() if self.request else None,
        }


def _replace_span(tokens: Sequence[str], span: Sequence[int], value: str) -> str:
    start, end = int(span[0]), int(span[1])
    return " ".join(list(tokens[:start]) + [value] + list(tokens[end:]))


class VoiceUnderstanding:
    def __init__(
        self,
        config: Optional[VoiceUnderstandingConfig] = None,
        vocabulary_provider: Optional[Callable[[], Sequence[VocabularyEntry]]] = None,
        learned: Any = None,
        channel: Optional[ClarificationChannel] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
        llm_model: Optional[str] = None,
    ) -> None:
        self.config = config or load_voice_understanding_config()
        self._vocabulary_provider = vocabulary_provider or collect_vocabulary
        self._learned = learned
        self._channel = channel
        self._llm_generate = llm_generate
        self._llm_model = self.config.llm_model or llm_model

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    @property
    def channel(self) -> ClarificationChannel:
        if self._channel is None:
            self._channel = get_clarification_channel()
        return self._channel

    def _learned_store(self) -> Any:
        if self._learned is None:
            from src.ear.learned_corrections import LearnedCorrections

            self._learned = LearnedCorrections(
                self.config.learned_corrections_path, self.config.learned_min_evidence
            )
        return self._learned

    # ------------------------------------------------------------------

    def process(self, text: Optional[str], record: Any = None) -> UnderstandingResult:
        """Procesa una frase nueva (no una respuesta a una aclaracion)."""
        original = str(text or "")
        if record is not None and str(getattr(record, "text", "")).strip() != original.strip():
            record = None  # el registro no corresponde a esta frase
        if not normalize_text(original):
            return UnderstandingResult(DECISION_EMPTY, original, original, record=record)

        try:
            vocabulary = list(self._vocabulary_provider())
        except Exception as exc:
            logger.warning("Vocabulario no disponible; se sigue con el texto original: %s", exc)
            return UnderstandingResult(DECISION_CONTINUE, original, original, record=record)
        try:
            learned = self._learned_store().active_mapping()
        except Exception as exc:
            logger.warning("Correcciones aprendidas no disponibles: %s", exc)
            learned = {}

        correction = correct_transcript(
            original, vocabulary, learned=learned,
            candidate_min_score=self.config.candidate_min_score,
            accept_score=self.config.accept_score,
            ambiguity_gap=self.config.ambiguity_gap,
        )
        tokens = correction.corrected_text.split()
        working_tokens = list(tokens)
        sources: List[str] = [SOURCE_DETERMINISTIC] if correction.changed else []
        confidence = getattr(record, "confidence", None) if record is not None else None
        app_names = sorted({c.canonical for c in correction.candidates if c.kind == KIND_APPLICATION})
        reasons = llm_reasons(
            correction.normalized_text, confidence, self.config.low_confidence,
            app_names, correction.conclusive,
        )
        pending = list(correction.ambiguous)
        llm_status: Optional[str] = None

        # 4.5.6.9 / 4.5.6.11: LLM solo para fragmentos no concluyentes.
        if pending and reasons and self.config.use_llm:
            group = pending[0]
            outcome = disambiguate(
                original, [c.canonical for c in group],
                [e.canonical for e in vocabulary if e.kind == KIND_APPLICATION],
                generate=self._llm_generate, model=self._llm_model,
                timeout_seconds=self.config.llm_timeout_seconds,
            )
            llm_status = outcome["status"]
            chosen = outcome.get("result")
            if chosen is not None and chosen.entity != UNKNOWN_ENTITY:
                working_tokens = _replace_span(working_tokens, group[0].span, chosen.entity).split()
                pending = pending[1:]
                sources.append(SOURCE_LLM)
            else:
                logger.info("Desambiguacion LLM sin resultado (%s): se mantiene la correccion determinista", llm_status)

        proposed = " ".join(working_tokens)
        result = UnderstandingResult(
            DECISION_CONTINUE, original, original, record=record, reasons=reasons,
            llm_status=llm_status, correction=correction.to_dict(),
        )

        # 4.5.6.10: politica de decision.
        if pending:
            group: List[CorrectionCandidate] = pending[0]
            names = [c.canonical for c in group][:3]
            resume = {"tokens": working_tokens, "span": list(group[0].span), "heard": group[0].heard,
                      "original_text": original}
            if len(names) > 1:
                request = ClarificationRequest(
                    kind="clarification", reason="varios candidatos cercanos",
                    question="Te refieres a %s?" % " o ".join(names), candidates=names, resume=resume,
                )
                return self._ask(result, DECISION_CLARIFY, request)
            resume["choice"] = names[0]
            request = ClarificationRequest(
                kind="confirmation", reason="candidato unico sin puntuacion suficiente",
                question="%s?" % names[0], resume=resume,
            )
            return self._ask(result, DECISION_CONFIRM, request)

        high, low = self.config.high_confidence, self.config.low_confidence
        if confidence is not None and high is not None and low is not None and confidence < high:
            changed = proposed != correction.normalized_text
            if confidence < low or changed:
                label = proposed if confidence < low else ", ".join(
                    c.canonical for c in correction.applied if c.method != "exact"
                ) or proposed
                request = ClarificationRequest(
                    kind="confirmation",
                    reason="confianza baja" if confidence < low else "confianza media con correccion",
                    question="%s?" % label,
                    resume={"text": proposed, "original_text": original},
                )
                return self._ask(result, DECISION_CONFIRM, request)

        if sources:
            result.text = proposed
            result.record = self._derive(record, proposed, sources[-1], result.correction)
        return result

    def _ask(self, result: UnderstandingResult, decision: str, request: ClarificationRequest) -> UnderstandingResult:
        self.channel.ask(request)
        result.decision = decision
        result.request = request
        result.reply = request.question
        result.text = ""
        return result

    @staticmethod
    def _derive(record: Any, text: str, source: str, detail: Any) -> Any:
        derive = getattr(record, "with_derivation", None)
        if not callable(derive):
            return record
        try:
            return derive(text, source, {"correction": detail} if detail else None)
        except Exception as exc:
            logger.warning("No se pudo anadir la derivacion al registro: %s", exc)
            return record

    def handle_answer(self, text: Optional[str]) -> Optional[UnderstandingResult]:
        """
        Si hay una aclaracion pendiente, interpreta ``text`` como respuesta.
        Devuelve None si no habia nada pendiente o si la respuesta es una
        peticion nueva (el llamador la procesa como frase normal).
        """
        if not self.channel.has_pending:
            return None
        outcome = self.channel.respond(text)
        request = outcome.request
        original = str(text or "")
        if outcome.status in ("no_pending", "replaced_by_new_request"):
            return None
        if outcome.status == "reask":
            return UnderstandingResult(DECISION_CLARIFY, "", original, reply=outcome.question, request=request)
        if outcome.status != "resolved":
            messages = {
                "rejected": "De acuerdo, no hago nada.",
                "cancelled": "Cancelado.",
                "exhausted": "No te he entendido; no hago nada.",
                "expired": "La pregunta ha caducado; repite la orden, por favor.",
            }
            return UnderstandingResult(DECISION_DROPPED, "", original, reply=messages.get(outcome.status, "No hago nada."))
        resume = outcome.resume or {}
        choice = outcome.choice or resume.get("choice")
        if "tokens" in resume and choice:
            final_text = _replace_span(resume["tokens"], resume["span"], choice)
            heard = resume.get("heard")
            if heard:
                try:
                    self._learned_store().record(heard, choice)
                except Exception as exc:
                    logger.warning("No se pudo guardar la correccion aprendida: %s", exc)
        else:
            final_text = str(resume.get("text") or "")
        if not final_text:
            return UnderstandingResult(DECISION_DROPPED, "", original, reply="No hago nada.")
        logger.info("Orden reanudada tras %s: %s", request.kind if request else "respuesta", final_text)
        return UnderstandingResult(
            DECISION_CONTINUE, final_text, str(resume.get("original_text") or original),
            reasons=[SOURCE_USER],
        )


_instance: Optional[VoiceUnderstanding] = None
_instance_lock = threading.Lock()


def get_voice_understanding(llm_model: Optional[str] = None) -> VoiceUnderstanding:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = VoiceUnderstanding(llm_model=llm_model)
        return _instance


__all__ = [
    "DECISION_CLARIFY",
    "DECISION_CONFIRM",
    "DECISION_CONTINUE",
    "DECISION_DROPPED",
    "DECISION_EMPTY",
    "UnderstandingResult",
    "VoiceUnderstanding",
    "get_voice_understanding",
]
