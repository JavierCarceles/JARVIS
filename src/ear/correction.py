"""Correccion determinista de transcripciones contra lo conocido (4.5.6.7).

Antes de cualquier LLM: se normaliza el texto (minusculas, sin acentos,
numeros escritos, sin puntuacion) y se buscan coincidencias foneticas y
aproximadas en espanol contra el vocabulario (aplicaciones y aliases,
terminos de monitor y verbos de orden). Devuelve candidatos con puntuacion y,
solo cuando la coincidencia es concluyente, un texto corregido. Nunca propone
nada que no este en el vocabulario y nunca altera una forma ya correcta.

El texto original no se toca: el llamador anade el texto corregido como
derivacion (``TranscriptionRecord.with_derivation``, 4.5.6.6).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.ear.vocabulary import KIND_APPLICATION, KIND_COMMAND, VocabularyEntry

logger = get_logger(__name__)

try:  # rapidfuzz es opcional: mismo resultado (ratio 0..1) con o sin el.
    from rapidfuzz.distance import Levenshtein as _RFLevenshtein  # type: ignore
except Exception:  # pragma: no cover - depende del entorno
    _RFLevenshtein = None

SOURCE_DETERMINISTIC = "correccion_determinista"
SOURCE_LEARNED = "correccion_aprendida"

# Palabras que nunca se corrigen solas (articulos, preposiciones...).
STOPWORDS = frozenset(
    "a al de del el la las los lo en y o u que me mi mis tu te se por para con un una "
    "unos unas esta este eso esa le les su sus ya no si es".split()
)
NUMBER_WORDS = {
    "uno": "1", "una": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
    "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
}
MAX_NGRAM = 3
MIN_FORM_CHARS = 3
USAGE_BONUS = 0.04
# A puntuacion casi igual se prefiere el fragmento mas largo.
SPAN_LENGTH_BONUS = 0.02


def normalize_text(text: Optional[str], numbers: bool = False) -> str:
    """Minusculas, sin acentos ni puntuacion; ``numbers`` convierte uno..diez."""
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = value.split()
    if numbers:
        tokens = [NUMBER_WORDS.get(t, t) for t in tokens]
    return " ".join(tokens)


def _phonetic_word(word: str) -> str:
    w = word
    # "es" + consonante al inicio: el espanol anade una e a "sp/st/sk..."
    # ("espotifai" -> "spotifai", "estudio" -> "studio").
    if re.match(r"^es[bcdfgklmnpqrstvz]", w):
        w = w[1:]
    w = re.sub(r"ch(?=[rl])", "k", w)       # chrome -> krome
    w = w.replace("ch", "X")
    w = w.replace("sh", "X")
    w = re.sub(r"h", "", w)                  # h muda
    w = w.replace("X", "ch")
    w = re.sub(r"qu(?=[ei])", "k", w)
    w = re.sub(r"c(?=[ei])", "s", w)
    w = re.sub(r"g(?=[ei])", "j", w)
    w = re.sub(r"gu(?=[ei])", "g", w)
    w = w.replace("c", "k").replace("q", "k").replace("kk", "k")
    w = w.replace("v", "b").replace("w", "u").replace("z", "s").replace("x", "ks")
    w = w.replace("ll", "y")
    w = re.sub(r"(?<=[aeiou])y$", "i", w)    # spotify -> spotifi
    w = re.sub(r"y(?![aeiou])", "i", w)
    w = re.sub(r"ai$", "i", w)               # spotifai -> spotifi
    w = re.sub(r"(.)\1+", r"\1", w)          # letras repetidas
    # Vocal final debil (cromo/chrome, estudio/studio se mantiene).
    if len(w) > 3:
        w = re.sub(r"[eo]$", "", w)
    return w


def phonetic_key(text: str) -> str:
    """Clave fonetica aproximada del espanol (incluye anglicismos comunes)."""
    return " ".join(_phonetic_word(t) for t in normalize_text(text).split() if t not in STOPWORDS)


def similarity(a: str, b: str) -> float:
    """Ratio 0..1 de Levenshtein normalizado."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    if _RFLevenshtein is not None:
        return float(_RFLevenshtein.normalized_similarity(a, b))
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return 1.0 - previous[-1] / max(len(a), len(b))


@dataclass
class CorrectionCandidate:
    canonical: str
    kind: str
    heard: str
    span: Tuple[int, int]  # indices de token [inicio, fin) en el texto normalizado
    score: float
    method: str  # exact | phonetic | fuzzy | learned
    matched_form: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "canonical": self.canonical, "kind": self.kind, "heard": self.heard,
            "span": list(self.span), "score": round(self.score, 4),
            "method": self.method, "matched_form": self.matched_form,
        }


@dataclass
class CorrectionResult:
    original_text: str
    normalized_text: str
    corrected_text: str
    # Mejor candidato por fragmento, solo los concluyentes se aplican.
    applied: List[CorrectionCandidate] = field(default_factory=list)
    # Fragmentos con varios candidatos cercanos o sin puntuacion suficiente.
    ambiguous: List[List[CorrectionCandidate]] = field(default_factory=list)
    candidates: List[CorrectionCandidate] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(c.method != "exact" for c in self.applied)

    @property
    def conclusive(self) -> bool:
        return not self.ambiguous

    @property
    def application_candidates(self) -> List[CorrectionCandidate]:
        return [c for c in self.candidates if c.kind == KIND_APPLICATION]

    def to_dict(self) -> Dict[str, object]:
        return {
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
            "corrected_text": self.corrected_text,
            "applied": [c.to_dict() for c in self.applied],
            "ambiguous": [[c.to_dict() for c in group] for group in self.ambiguous],
            "conclusive": self.conclusive,
        }


def _score_form(heard: str, form_norm: str, form_key: str) -> Tuple[float, str]:
    if heard == form_norm:
        return 1.0, "exact"
    textual = similarity(heard, form_norm)
    heard_key = phonetic_key(heard)
    phonetic = similarity(heard_key, form_key) if heard_key and form_key else 0.0
    if phonetic >= textual:
        return 0.35 * textual + 0.65 * phonetic, "phonetic"
    return textual, "fuzzy"


def correct_transcript(
    text: Optional[str],
    vocabulary: Sequence[VocabularyEntry],
    learned: Optional[Dict[str, str]] = None,
    candidate_min_score: float = 0.72,
    accept_score: float = 0.86,
    ambiguity_gap: float = 0.06,
) -> CorrectionResult:
    """
    Corrige ``text`` contra ``vocabulary``. ``learned`` (forma oida
    normalizada -> forma canonica, 4.5.6.8) tiene prioridad sobre el calculo.

    Un fragmento se corrige solo si su mejor candidato supera
    ``accept_score`` y le saca al menos ``ambiguity_gap`` al siguiente
    candidato distinto; si no, queda en ``ambiguous`` con sus candidatos.
    """
    original = str(text or "")
    tokens = normalize_text(original).split()
    result = CorrectionResult(original, " ".join(tokens), " ".join(tokens))
    if not tokens:
        return result

    forms: List[Tuple[VocabularyEntry, str, str, str]] = []
    for entry in vocabulary or ():
        for form in entry.forms:
            norm = normalize_text(form)
            if len(norm.replace(" ", "")) >= MIN_FORM_CHARS or entry.kind == KIND_COMMAND:
                forms.append((entry, form, norm, phonetic_key(form)))
    by_canonical = {normalize_text(e.canonical): e for e in vocabulary or ()}
    learned_norm = {normalize_text(k): v for k, v in (learned or {}).items()}

    # Candidatos por fragmento (n-gramas de hasta MAX_NGRAM tokens).
    per_span: Dict[Tuple[int, int], List[CorrectionCandidate]] = {}
    for start in range(len(tokens)):
        for end in range(start + 1, min(len(tokens), start + MAX_NGRAM) + 1):
            span_tokens = tokens[start:end]
            if span_tokens[0] in STOPWORDS or span_tokens[-1] in STOPWORDS:
                continue
            heard = " ".join(span_tokens)
            found: Dict[str, CorrectionCandidate] = {}
            learned_target = learned_norm.get(heard)
            if learned_target is not None:
                entry = by_canonical.get(normalize_text(learned_target))
                if entry is not None:
                    found[entry.canonical] = CorrectionCandidate(
                        entry.canonical, entry.kind, heard, (start, end), 1.0, "learned", learned_target
                    )
            for entry, form, norm, key in forms:
                if abs(len(norm.split()) - len(span_tokens)) > 1:
                    continue
                score, method = _score_form(heard, norm, key)
                if method != "exact" and entry.kind == KIND_APPLICATION:
                    score = min(0.999, score + USAGE_BONUS * entry.weight)
                if score < candidate_min_score:
                    continue
                current = found.get(entry.canonical)
                if current is None or score > current.score:
                    found[entry.canonical] = CorrectionCandidate(
                        entry.canonical, entry.kind, heard, (start, end), score, method, form
                    )
            if found:
                per_span[(start, end)] = sorted(found.values(), key=lambda c: -c.score)

    # Seleccion voraz sin solapes: primero los fragmentos con mejor candidato,
    # y a igualdad los mas largos ("visual studio" antes que "visual").
    order = sorted(
        per_span.items(),
        key=lambda item: (-(item[1][0].score + SPAN_LENGTH_BONUS * (item[0][1] - item[0][0])), item[0][0]),
    )
    used = [False] * len(tokens)
    replacements: Dict[int, Tuple[int, str]] = {}
    for (start, end), group in order:
        if any(used[start:end]):
            continue
        best = group[0]
        second = group[1].score if len(group) > 1 else 0.0
        result.candidates.extend(group)
        for index in range(start, end):
            used[index] = True
        conclusive = best.method in ("exact", "learned") or (
            best.score >= accept_score and best.score - second >= ambiguity_gap
        )
        if not conclusive:
            result.ambiguous.append(group)
            continue
        result.applied.append(best)
        if best.method != "exact":
            replacements[start] = (end, best.canonical)

    if replacements:
        output: List[str] = []
        index = 0
        while index < len(tokens):
            if index in replacements:
                end, canonical = replacements[index]
                output.append(canonical)
                index = end
            else:
                output.append(tokens[index])
                index += 1
        result.corrected_text = " ".join(output)
    if result.changed or result.ambiguous:
        logger.info(
            "Correccion determinista: '%s' -> '%s' (aplicadas=%s, ambiguas=%s)",
            result.normalized_text, result.corrected_text,
            [(c.heard, c.canonical, round(c.score, 3), c.method) for c in result.applied if c.method != "exact"],
            [[(c.canonical, round(c.score, 3)) for c in group] for group in result.ambiguous],
        )
    return result


__all__ = [
    "CorrectionCandidate",
    "CorrectionResult",
    "SOURCE_DETERMINISTIC",
    "SOURCE_LEARNED",
    "correct_transcript",
    "normalize_text",
    "phonetic_key",
    "similarity",
]
