# src/ear/transcription.py
"""
Resultado de una transcripcion de voz y su confianza real.

Este modulo no depende del microfono ni de Whisper: recibe los segmentos
que devuelve ``faster_whisper.WhisperModel.transcribe`` (cualquier objeto con
los mismos atributos) y construye un registro inmutable.

Confianza (unidad 4.5.6.5):
- ``info.language_probability`` mide lo seguro que esta Whisper del IDIOMA, no
  de haber entendido bien las palabras. Se conserva aparte como
  ``language_probability`` y ya no se usa como confianza.
- La confianza de la transcripcion se calcula con lo que Whisper da por
  segmento y por palabra:
    * con probabilidades por palabra (``word_timestamps=True``): media de
      ``Word.probability``;
    * si no hay palabras: ``exp(avg_logprob)`` de cada segmento, ponderado por
      su numero de tokens.
- ``no_speech_prob`` y ``compression_ratio`` se devuelven tal cual (maximo de
  los segmentos y detalle por segmento). Los umbrales para decidir ejecutar,
  confirmar o aclarar NO se fijan aqui: los fija la unidad 4.5.6.10 con el
  corpus de 4.5.6.2.

Texto original (unidad 4.5.6.6):
- ``original_text`` es el texto tal como lo reconocio Whisper (segmentos
  concatenados sin tocar) y no se puede modificar.
- ``text`` es solo ese mismo texto sin espacios en los extremos.
- Cualquier correccion posterior (determinista, aprendida o del LLM) se anade
  como ``TextDerivation`` con su procedencia mediante ``with_derivation``, que
  devuelve un registro nuevo y deja intacto el original.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class WordInfo:
    """Palabra reconocida con su probabilidad y tiempos (segundos)."""

    word: str
    probability: Optional[float]
    start: Optional[float]
    end: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "probability": self.probability,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class SegmentInfo:
    """Metricas de un segmento tal como las devuelve Whisper."""

    text: str
    start: Optional[float]
    end: Optional[float]
    avg_logprob: Optional[float]
    no_speech_prob: Optional[float]
    compression_ratio: Optional[float]
    token_count: int
    words: Tuple[WordInfo, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "avg_logprob": self.avg_logprob,
            "no_speech_prob": self.no_speech_prob,
            "compression_ratio": self.compression_ratio,
            "token_count": self.token_count,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass(frozen=True)
class TextDerivation:
    """
    Representacion derivada del texto original.

    ``source`` identifica quien la produjo (por ejemplo la correccion
    determinista o el LLM) y ``detail`` guarda los datos que la justifican.
    """

    text: str
    source: str
    detail: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "detail": dict(self.detail),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class TranscriptionRecord:
    """Transcripcion reconocida, su confianza y sus derivaciones."""

    original_text: str
    confidence: float
    confidence_method: str
    language: Optional[str]
    language_probability: Optional[float]
    avg_logprob: Optional[float]
    max_no_speech_prob: Optional[float]
    max_compression_ratio: Optional[float]
    min_word_probability: Optional[float]
    segments: Tuple[SegmentInfo, ...] = ()
    derivations: Tuple[TextDerivation, ...] = ()
    created_at: float = field(default_factory=time.time)

    @property
    def text(self) -> str:
        """Texto original sin espacios en los extremos (no es una correccion)."""
        return self.original_text.strip()

    @property
    def words(self) -> Tuple[WordInfo, ...]:
        return tuple(w for s in self.segments for w in s.words)

    @property
    def current_text(self) -> str:
        """Ultima derivacion o, si no hay ninguna, el texto original."""
        if self.derivations:
            return self.derivations[-1].text
        return self.text

    def with_derivation(
        self, text: str, source: str, detail: Optional[Dict[str, Any]] = None
    ) -> "TranscriptionRecord":
        """Devuelve un registro nuevo con una derivacion mas; el original no cambia."""
        if not source:
            raise ValueError("Una derivacion necesita su procedencia (source)")
        derivation = TextDerivation(text=text, source=source, detail=dict(detail or {}))
        return replace(self, derivations=self.derivations + (derivation,))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_text": self.original_text,
            "text": self.text,
            "current_text": self.current_text,
            "confidence": self.confidence,
            "confidence_method": self.confidence_method,
            "language": self.language,
            "language_probability": self.language_probability,
            "avg_logprob": self.avg_logprob,
            "max_no_speech_prob": self.max_no_speech_prob,
            "max_compression_ratio": self.max_compression_ratio,
            "min_word_probability": self.min_word_probability,
            "segments": [s.to_dict() for s in self.segments],
            "derivations": [d.to_dict() for d in self.derivations],
            "created_at": self.created_at,
        }


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _segment_from_whisper(segment: Any) -> SegmentInfo:
    words: List[WordInfo] = []
    for word in getattr(segment, "words", None) or ():
        words.append(
            WordInfo(
                word=str(getattr(word, "word", "")),
                probability=_as_float(getattr(word, "probability", None)),
                start=_as_float(getattr(word, "start", None)),
                end=_as_float(getattr(word, "end", None)),
            )
        )
    tokens = getattr(segment, "tokens", None) or ()
    return SegmentInfo(
        text=str(getattr(segment, "text", "") or ""),
        start=_as_float(getattr(segment, "start", None)),
        end=_as_float(getattr(segment, "end", None)),
        avg_logprob=_as_float(getattr(segment, "avg_logprob", None)),
        no_speech_prob=_as_float(getattr(segment, "no_speech_prob", None)),
        compression_ratio=_as_float(getattr(segment, "compression_ratio", None)),
        token_count=len(tokens),
        words=tuple(words),
    )


def _weighted_avg_logprob(segments: Iterable[SegmentInfo]) -> Optional[float]:
    total = 0.0
    weight = 0
    for segment in segments:
        if segment.avg_logprob is None:
            continue
        w = max(segment.token_count, 1)
        total += segment.avg_logprob * w
        weight += w
    if weight == 0:
        return None
    return total / weight


def compute_confidence(segments: Tuple[SegmentInfo, ...]) -> Tuple[float, str]:
    """
    Confianza de la transcripcion en [0, 1] y el metodo usado.

    Metodos: ``word_probability_mean``, ``avg_logprob`` o ``sin_datos``.
    """
    probabilities = [
        w.probability for s in segments for w in s.words if w.probability is not None
    ]
    if probabilities:
        value = sum(probabilities) / len(probabilities)
        return min(max(value, 0.0), 1.0), "word_probability_mean"

    total = 0.0
    weight = 0
    for segment in segments:
        if segment.avg_logprob is None:
            continue
        w = max(segment.token_count, 1)
        total += math.exp(min(segment.avg_logprob, 0.0)) * w
        weight += w
    if weight:
        return min(max(total / weight, 0.0), 1.0), "avg_logprob"

    return 0.0, "sin_datos"


def build_transcription_record(
    whisper_segments: Iterable[Any], info: Any = None
) -> TranscriptionRecord:
    """
    Construye el registro a partir de la salida de ``WhisperModel.transcribe``.

    Consume el generador de segmentos (la transcripcion ocurre al iterarlo).
    """
    segments = tuple(_segment_from_whisper(s) for s in whisper_segments)
    confidence, method = compute_confidence(segments)

    no_speech = [s.no_speech_prob for s in segments if s.no_speech_prob is not None]
    ratios = [s.compression_ratio for s in segments if s.compression_ratio is not None]
    word_probs = [
        w.probability for s in segments for w in s.words if w.probability is not None
    ]

    language = getattr(info, "language", None) if info is not None else None
    language_probability = (
        _as_float(getattr(info, "language_probability", None)) if info is not None else None
    )

    return TranscriptionRecord(
        original_text="".join(s.text for s in segments),
        confidence=confidence,
        confidence_method=method,
        language=str(language) if language is not None else None,
        language_probability=language_probability,
        avg_logprob=_weighted_avg_logprob(segments),
        max_no_speech_prob=max(no_speech) if no_speech else None,
        max_compression_ratio=max(ratios) if ratios else None,
        min_word_probability=min(word_probs) if word_probs else None,
        segments=segments,
    )


# ----------------------------------------------------------------------
# Ultima transcripcion entregada (4.5.6.12)
# ----------------------------------------------------------------------
# Ear la publica al devolver una frase; Brain la consulta para conocer la
# confianza real de esa misma frase sin que ``main.py`` tenga que pasarla.
_last_record: Optional[TranscriptionRecord] = None


def set_last_transcription(record: Optional[TranscriptionRecord]) -> None:
    global _last_record
    _last_record = record


def get_last_transcription() -> Optional[TranscriptionRecord]:
    return _last_record
