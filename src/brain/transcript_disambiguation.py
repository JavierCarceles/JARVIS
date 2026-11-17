"""Segunda inferencia LLM para transcripciones dudosas (4.5.6.9 y 4.5.6.11).

Solo se usa cuando la correccion determinista no es concluyente segun
criterios verificables (``llm_reasons``). La entrada es el texto original, los
candidatos deterministas y el vocabulario conocido; la salida es un JSON
validado: la entidad debe ser UNO de los candidatos o ``"desconocida"``.
Nunca ejecuta acciones. Ante salida invalida, timeout o modelo no disponible
devuelve ``None`` con el motivo y el llamador vuelve a la correccion
determinista y, si no basta, pide aclaracion (4.5.6.11).
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.core.log import get_logger

logger = get_logger(__name__)

UNKNOWN_ENTITY = "desconocida"
# Mismo modelo por defecto que ``Brain`` (llama3); Brain pasa el suyo.
DEFAULT_LLM_MODEL = "llama3"
ALLOWED_INTENTS = ("abrir", "cerrar", "buscar", "navegar", "mover", "otra")
# Orden compuesta: varias acciones encadenadas.
_COMPOUND_RE = re.compile(r"\b(y luego|y despues|despues|luego|y tambien|ademas)\b")
# Texto cortado: termina en articulo/preposicion o es demasiado corto.
_INCOMPLETE_END = {"el", "la", "los", "las", "de", "del", "en", "a", "al", "y", "con", "para", "un", "una"}


@dataclass
class LLMDisambiguation:
    intent: str
    entity: str  # uno de los candidatos o UNKNOWN_ENTITY
    parameters: Dict[str, Any] = field(default_factory=dict)
    ambiguities: List[str] = field(default_factory=list)
    raw: str = ""

    @property
    def resolved(self) -> bool:
        return self.entity != UNKNOWN_ENTITY


def llm_reasons(
    normalized_text: str,
    confidence: Optional[float],
    low_confidence: Optional[float],
    application_candidates: Sequence[str],
    deterministic_conclusive: bool,
) -> List[str]:
    """
    Criterios verificables para pedir la segunda inferencia (lista vacia = no):
    confianza por debajo de ``low_confidence`` (si esta calibrado), varios
    candidatos cercanos, correccion no concluyente, orden compuesta o texto
    incompleto.
    """
    reasons: List[str] = []
    tokens = normalized_text.split()
    if not tokens:
        return reasons
    if confidence is not None and low_confidence is not None and confidence < low_confidence:
        reasons.append("confianza_baja")
    if len(set(application_candidates)) > 1:
        reasons.append("varios_candidatos")
    if not deterministic_conclusive:
        reasons.append("correccion_no_concluyente")
    if _COMPOUND_RE.search(normalized_text):
        reasons.append("orden_compuesta")
    if tokens[-1] in _INCOMPLETE_END or len(tokens) == 1:
        reasons.append("texto_incompleto")
    return reasons


def build_prompt(original_text: str, candidates: Sequence[str], vocabulary: Sequence[str]) -> str:
    payload = {
        "texto_original": original_text,
        "candidatos": list(candidates),
        "vocabulario_conocido": list(vocabulary)[:60],
    }
    return (
        "Eres el modulo de comprension de ordenes de voz de JARVIS. La transcripcion "
        "puede tener errores. NO ejecutes nada. Responde SOLO con un objeto JSON con "
        "las claves: intent (una de %s), entity (EXACTAMENTE uno de los candidatos o "
        "\"%s\"), parameters (objeto con monitor, accion, objeto si aparecen) y "
        "ambiguities (lista de textos). Si dudas, entity=\"%s\".\nDatos: %s"
        % (", ".join(ALLOWED_INTENTS), UNKNOWN_ENTITY, UNKNOWN_ENTITY, json.dumps(payload, ensure_ascii=True))
    )


def parse_response(raw: str, candidates: Sequence[str]) -> Optional[LLMDisambiguation]:
    """Valida la salida; una entidad fuera de los candidatos se rechaza."""
    text = str(raw or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.warning("Desambiguacion LLM: respuesta sin JSON")
        return None
    try:
        data = json.loads(match.group(0))
    except (TypeError, ValueError) as exc:
        logger.warning("Desambiguacion LLM: JSON invalido: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    intent = str(data.get("intent") or "").strip().lower()
    entity = str(data.get("entity") or "").strip()
    parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
    ambiguities = data.get("ambiguities") if isinstance(data.get("ambiguities"), list) else []
    if intent not in ALLOWED_INTENTS:
        logger.warning("Desambiguacion LLM: intencion no valida %r", intent)
        return None
    by_lower = {str(c).strip().lower(): str(c) for c in candidates}
    if entity.lower() == UNKNOWN_ENTITY:
        entity = UNKNOWN_ENTITY
    elif entity.lower() in by_lower:
        entity = by_lower[entity.lower()]
    else:
        logger.warning("Desambiguacion LLM: entidad inventada rechazada: %r", entity)
        return None
    return LLMDisambiguation(intent, entity, dict(parameters), [str(a) for a in ambiguities], text)


def _default_generate(model: Optional[str]) -> Callable[[str], str]:
    def generate(prompt: str) -> str:
        import ollama  # infraestructura LLM existente de Brain

        response = ollama.chat(
            model=model or DEFAULT_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0, "num_predict": 200},
        )
        return str(response["message"]["content"])

    return generate


def disambiguate(
    original_text: str,
    candidates: Sequence[str],
    vocabulary: Sequence[str],
    generate: Optional[Callable[[str], str]] = None,
    model: Optional[str] = None,
    timeout_seconds: float = 8.0,
) -> Dict[str, Any]:
    """
    Ejecuta la segunda inferencia con limite de tiempo. Devuelve
    ``{"result": LLMDisambiguation | None, "status": ok|sin_candidatos|
    timeout|no_disponible|salida_invalida}``.
    """
    if not candidates:
        return {"result": None, "status": "sin_candidatos"}
    generator = generate or _default_generate(model)
    prompt = build_prompt(original_text, candidates, vocabulary)
    holder: Dict[str, Any] = {}

    def run() -> None:
        try:
            holder["raw"] = generator(prompt)
        except Exception as exc:  # modelo caido, no instalado...
            holder["error"] = exc

    worker = threading.Thread(target=run, name="jarvis-llm-disambiguation", daemon=True)
    worker.start()
    worker.join(max(0.1, float(timeout_seconds)))
    if worker.is_alive():
        logger.warning("Desambiguacion LLM: timeout tras %.1fs", timeout_seconds)
        return {"result": None, "status": "timeout"}
    if "error" in holder:
        logger.warning("Desambiguacion LLM: modelo no disponible: %s", holder["error"])
        return {"result": None, "status": "no_disponible"}
    parsed = parse_response(holder.get("raw", ""), candidates)
    if parsed is None:
        return {"result": None, "status": "salida_invalida"}
    logger.info("Desambiguacion LLM: intent=%s entity=%s", parsed.intent, parsed.entity)
    return {"result": parsed, "status": "ok"}


__all__ = [
    "ALLOWED_INTENTS",
    "LLMDisambiguation",
    "UNKNOWN_ENTITY",
    "build_prompt",
    "disambiguate",
    "llm_reasons",
    "parse_response",
]
