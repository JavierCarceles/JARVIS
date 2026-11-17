"""Configuracion del reconocimiento de voz (4.5.6.3) y de la comprension (4.5.6.10).

La configuracion vive en ``config/config.json`` (secciones ``asr`` y
``voice_understanding``), no en el codigo. Sin esas secciones los valores por
defecto reproducen EXACTAMENTE el comportamiento anterior (faster-whisper
``medium`` en CPU ``int8``, ``beam_size=5``, idioma ``es``, sin VAD) y la
comprension robusta queda desactivada: cada mejora (``vad_filter``, modelo,
``temperature``, ``condition_on_previous_text``...) y cada umbral se activan
solo tras medirlos contra el corpus de 4.5.6.2.

Ejemplo de seccion (valores ilustrativos, no medidos)::

    "asr": {"model_size": "small", "device": "cuda", "compute_type": "float16",
            "vad_filter": true, "temperature": [0.0, 0.2, 0.4],
            "condition_on_previous_text": false},
    "voice_understanding": {"enabled": true, "high_confidence": 0.85,
                            "low_confidence": 0.55}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.core.log import get_logger

logger = get_logger(__name__)

# Lista fija anterior: solo se usa si el vocabulario dinamico (4.5.6.4) esta
# desactivado o no se puede construir.
LEGACY_INITIAL_PROMPT = (
    "Jarvis, se\u00f1or, abrir, YouTube, Google, LoL, Spotify, comando, "
    "asistente, tecnolog\u00eda."
)


@dataclass
class ASRConfig:
    model_size: str = "medium"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "es"
    beam_size: int = 5
    vad_filter: bool = False
    # None = valor por defecto de faster-whisper (no se pasa el parametro).
    temperature: Optional[Union[float, List[float]]] = None
    condition_on_previous_text: Optional[bool] = None
    word_timestamps: bool = True
    dynamic_vocabulary: bool = True
    initial_prompt_max_chars: int = 400
    max_vocabulary_apps: int = 40


@dataclass
class VoiceUnderstandingConfig:
    """
    Umbrales de la politica de decision (4.5.6.10). ``None`` significa "no
    calibrado": la politica no usa la confianza y solo decide por la
    estructura de los candidatos (ver ``src/brain/voice_understanding.py``).
    """

    enabled: bool = False
    high_confidence: Optional[float] = None
    low_confidence: Optional[float] = None
    # Correccion determinista (4.5.6.7): puntuacion minima para proponer un
    # candidato, para corregir sin dudas y distancia minima al segundo.
    candidate_min_score: float = 0.72
    accept_score: float = 0.86
    ambiguity_gap: float = 0.06
    use_llm: bool = True
    llm_model: Optional[str] = None
    llm_timeout_seconds: float = 8.0
    learned_min_evidence: int = 2
    learned_corrections_path: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def _config_path() -> Path:
    try:
        from src.core.config import CONFIG_PATH

        return Path(CONFIG_PATH)
    except Exception as exc:  # pragma: no cover - depende del arranque
        logger.warning("No se pudo resolver CONFIG_PATH: %s", exc)
        return Path("config") / "config.json"


def _read_section(name: str, path: Optional[Path]) -> Dict[str, Any]:
    target = Path(path) if path is not None else _config_path()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("Configuracion %s ilegible en %s: %s", name, target, exc)
        return {}
    section = data.get(name) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def _apply(instance: Any, section: Dict[str, Any], label: str) -> Any:
    known = {item.name: item for item in fields(instance)}
    for key, value in section.items():
        if key not in known:
            if hasattr(instance, "extra") and isinstance(getattr(instance, "extra"), dict):
                instance.extra[key] = value
            else:
                logger.warning("Clave desconocida en %s: %s", label, key)
            continue
        current = getattr(instance, key)
        try:
            if value is None:
                setattr(instance, key, None)
            elif isinstance(current, bool):
                setattr(instance, key, bool(value))
            elif isinstance(current, int):
                setattr(instance, key, int(value))
            elif isinstance(current, float):
                setattr(instance, key, float(value))
            elif key == "temperature":
                setattr(instance, key, [float(v) for v in value] if isinstance(value, list) else float(value))
            elif key in ("high_confidence", "low_confidence"):
                setattr(instance, key, float(value))
            else:
                setattr(instance, key, value)
        except (TypeError, ValueError) as exc:
            logger.warning("Valor invalido en %s.%s=%r: %s", label, key, value, exc)
    return instance


def load_asr_config(path: Optional[Path] = None) -> ASRConfig:
    return _apply(ASRConfig(), _read_section("asr", path), "asr")


def load_voice_understanding_config(path: Optional[Path] = None) -> VoiceUnderstandingConfig:
    config = _apply(VoiceUnderstandingConfig(), _read_section("voice_understanding", path), "voice_understanding")
    if (
        config.high_confidence is not None
        and config.low_confidence is not None
        and config.low_confidence > config.high_confidence
    ):
        logger.warning("voice_understanding: low_confidence > high_confidence; se ignoran los umbrales")
        config.high_confidence = None
        config.low_confidence = None
    return config


def model_kwargs(config: ASRConfig) -> Dict[str, Any]:
    """Argumentos de ``WhisperModel(...)`` salvo el tamano."""
    return {"device": config.device, "compute_type": config.compute_type}


def transcribe_kwargs(config: ASRConfig, initial_prompt: Optional[str]) -> Dict[str, Any]:
    """Argumentos de ``model.transcribe``; los ``None`` no se pasan."""
    kwargs: Dict[str, Any] = {
        "beam_size": int(config.beam_size),
        "language": config.language,
        "word_timestamps": bool(config.word_timestamps),
        "vad_filter": bool(config.vad_filter),
    }
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.condition_on_previous_text is not None:
        kwargs["condition_on_previous_text"] = bool(config.condition_on_previous_text)
    return kwargs


__all__ = [
    "ASRConfig",
    "LEGACY_INITIAL_PROMPT",
    "VoiceUnderstandingConfig",
    "load_asr_config",
    "load_voice_understanding_config",
    "model_kwargs",
    "transcribe_kwargs",
]
