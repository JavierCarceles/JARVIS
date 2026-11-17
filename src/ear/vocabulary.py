"""Vocabulario conocido para el reconocimiento y la correccion de voz (4.5.6.4).

Una sola fuente de vocabulario para dos usos:
- ``build_initial_prompt``: el ``initial_prompt`` de Whisper, generado desde el
  catalogo de aplicaciones (nombres y aliases, priorizando las mas usadas),
  terminos de monitor y verbos de orden, con longitud limitada. Sustituye a la
  lista fija anterior (``LEGACY_INITIAL_PROMPT``).
- ``src/ear/correction.py``: los candidatos de la correccion determinista
  (4.5.6.7) salen SOLO de este vocabulario.

Este modulo no escribe nada ni lanza aplicaciones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from src.core.log import get_logger

logger = get_logger(__name__)

KIND_APPLICATION = "application"
KIND_MONITOR = "monitor"
KIND_COMMAND = "command"

# Terminos canonicos de monitor: la correccion solo repara la palabra
# deformada ("ezquierda" -> "izquierda"); la frase la resuelve
# ``src/desktop/monitor_topology.py`` (3.8.6.6.3).
MONITOR_TERMS: Dict[str, List[str]] = {
    "izquierda": ["izquierdo"],
    "derecha": ["derecho"],
    "arriba": [],
    "abajo": [],
    "principal": [],
    "secundaria": ["secundario"],
    "centro": ["central"],
    "pantalla": [],
    "monitor": [],
}

# Verbos y palabras de orden. Tambien sirven para que la correccion no
# confunda un verbo con una aplicacion parecida.
COMMAND_TERMS: Dict[str, List[str]] = {
    "jarvis": [],
    "abre": ["abrir"],
    "cierra": ["cerrar"],
    "busca": ["buscar"],
    "navega": ["navegar"],
    "mueve": ["mover"],
    "pon": ["poner"],
    "minimiza": ["minimizar"],
    "maximiza": ["maximizar"],
}


@dataclass
class VocabularyEntry:
    canonical: str
    kind: str
    aliases: List[str] = field(default_factory=list)
    # Uso relativo 0..1 (perfil de uso); pondera la correccion y el orden del prompt.
    weight: float = 0.0

    @property
    def forms(self) -> List[str]:
        seen: List[str] = []
        for item in [self.canonical] + list(self.aliases):
            text = str(item or "").strip()
            if text and text.lower() not in (s.lower() for s in seen):
                seen.append(text)
        return seen


def _usage_weights(usage: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    if not usage:
        return {}
    counts: Dict[str, float] = {}
    for name, value in usage.items():
        try:
            count = float(value)
        except (TypeError, ValueError):
            continue
        if count > 0:
            counts[str(name).strip().lower()] = count
    top = max(counts.values()) if counts else 0.0
    return {name: count / top for name, count in counts.items()} if top else {}


def build_vocabulary(
    applications: Iterable[Any] = (),
    usage: Optional[Mapping[str, Any]] = None,
    monitor_terms: Optional[Mapping[str, Sequence[str]]] = None,
    command_terms: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[VocabularyEntry]:
    """
    ``applications``: objetos con ``name`` y ``metadata["aliases"]``
    (``ApplicationKnowledge``) o dicts ``{"name", "aliases"}``.
    ``usage``: nombre -> numero de usos (perfil de uso), opcional.
    """
    weights = _usage_weights(usage)
    entries: List[VocabularyEntry] = []
    seen_apps = set()
    for app in applications or ():
        if isinstance(app, Mapping):
            name = app.get("name")
            aliases = app.get("aliases") or []
        else:
            name = getattr(app, "name", None)
            metadata = getattr(app, "metadata", None) or {}
            aliases = metadata.get("aliases") if isinstance(metadata, dict) else []
        name = str(name or "").strip()
        if not name or name.lower() in seen_apps:
            continue
        seen_apps.add(name.lower())
        alias_list = [str(a).strip() for a in (aliases or []) if str(a).strip()]
        weight = max(
            [weights.get(name.lower(), 0.0)] + [weights.get(a.lower(), 0.0) for a in alias_list]
        )
        entries.append(VocabularyEntry(name, KIND_APPLICATION, alias_list, weight))
    for canonical, aliases in (monitor_terms if monitor_terms is not None else MONITOR_TERMS).items():
        entries.append(VocabularyEntry(canonical, KIND_MONITOR, list(aliases)))
    for canonical, aliases in (command_terms if command_terms is not None else COMMAND_TERMS).items():
        entries.append(VocabularyEntry(canonical, KIND_COMMAND, list(aliases)))
    return entries


def build_initial_prompt(
    entries: Sequence[VocabularyEntry],
    max_chars: int = 400,
    max_apps: int = 40,
) -> str:
    """
    Prompt de Whisper: verbos de orden, aplicaciones (mas usadas primero, con
    sus aliases si caben) y terminos de monitor, cortado en ``max_chars`` sin
    partir palabras. Vacio si no hay vocabulario.
    """
    apps = sorted(
        (e for e in entries if e.kind == KIND_APPLICATION),
        key=lambda e: (-e.weight, e.canonical.lower()),
    )[: max(0, int(max_apps))]
    commands = [e.canonical for e in entries if e.kind == KIND_COMMAND]
    monitors = [e.canonical for e in entries if e.kind == KIND_MONITOR]
    words: List[str] = []
    for name in [c.capitalize() if c == "jarvis" else c for c in commands]:
        words.append(name)
    for entry in apps:
        words.append(entry.canonical)
    for entry in apps:
        words.extend(a for a in entry.aliases if a.lower() != entry.canonical.lower())
    words.extend(monitors)
    prompt = ""
    used = set()
    for word in words:
        key = word.lower()
        if key in used:
            continue
        candidate = f"{prompt}, {word}" if prompt else word
        if len(candidate) + 1 > max_chars:
            break
        prompt = candidate
        used.add(key)
    return f"{prompt}." if prompt else ""


def collect_vocabulary(usage: Optional[Mapping[str, Any]] = None) -> List[VocabularyEntry]:
    """
    Vocabulario del equipo: catalogo de ``ApplicationManager`` (carga perezosa;
    si no esta disponible se usan solo monitores y verbos) y, si se pasa, el
    perfil de uso.
    """
    applications: List[Any] = []
    try:
        from src.hands.apps.applications_core import get_application_manager

        manager = get_application_manager()
        catalog = getattr(manager, "applications", None) or {}
        applications = list(catalog.values()) if isinstance(catalog, dict) else list(catalog)
    except Exception as exc:
        logger.warning("Catalogo de aplicaciones no disponible para el vocabulario: %s", exc)
    return build_vocabulary(applications, usage=usage)


__all__ = [
    "COMMAND_TERMS",
    "KIND_APPLICATION",
    "KIND_COMMAND",
    "KIND_MONITOR",
    "MONITOR_TERMS",
    "VocabularyEntry",
    "build_initial_prompt",
    "build_vocabulary",
    "collect_vocabulary",
]
