"""Correcciones aprendidas del usuario (4.5.6.8).

Cuando el usuario confirma o corrige ("no, Spotify"), se guarda en local el par
forma transcrita -> entidad con contador y fechas. Solo se aplican con
evidencia repetida (``min_evidence``). Se guardan en un fichero JSON propio
(por defecto ``data/ear/learned_corrections.json``), NO en el catalogo global
ni en ``data/memory/entities.json``. El usuario puede listarlas, borrar una o
borrarlas todas.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.log import get_logger
from src.ear.correction import normalize_text

logger = get_logger(__name__)

DEFAULT_MIN_EVIDENCE = 2


def default_path() -> Path:
    try:
        from src.core.config import PROJECT_ROOT

        return Path(PROJECT_ROOT) / "data" / "ear" / "learned_corrections.json"
    except Exception:  # pragma: no cover - depende del arranque
        return Path("data") / "ear" / "learned_corrections.json"


class LearnedCorrections:
    """Almacen local forma oida normalizada -> {entity, kind, count, first_seen, last_seen}."""

    def __init__(self, path: Optional[Path] = None, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> None:
        self.path = Path(path) if path is not None else default_path()
        self.min_evidence = max(1, int(min_evidence))
        self._lock = threading.RLock()
        self._data: Optional[Dict[str, Dict[str, Any]]] = None

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self._data is not None:
            return self._data
        data: Dict[str, Dict[str, Any]] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                data = {str(k): v for k, v in raw.items() if isinstance(v, dict) and v.get("entity")}
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Correcciones aprendidas ilegibles en %s: %s", self.path, exc)
        self._data = data
        return data

    def _save(self) -> bool:
        data = self._load()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".learned_", suffix=".json", dir=str(self.path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
            return True
        except Exception as exc:
            logger.warning("No se pudieron guardar las correcciones aprendidas: %s", exc)
            return False

    def record(self, heard: str, entity: str, kind: str = "application") -> Optional[Dict[str, Any]]:
        """Suma una confirmacion o correccion del usuario. Si la forma ya apuntaba a otra entidad, se reinicia."""
        key = normalize_text(heard)
        entity = str(entity or "").strip()
        if not key or not entity:
            return None
        if key == normalize_text(entity):
            return None  # la transcripcion ya era correcta
        with self._lock:
            data = self._load()
            now = time.time()
            item = data.get(key)
            if item is None or item.get("entity") != entity:
                if item is not None:
                    logger.info("Correccion aprendida '%s' cambia de %s a %s", key, item.get("entity"), entity)
                item = {"entity": entity, "kind": kind, "count": 0, "first_seen": now}
            item["count"] = int(item.get("count", 0)) + 1
            item["last_seen"] = now
            data[key] = item
            self._save()
            logger.info("Correccion aprendida: '%s' -> %s (x%s)", key, entity, item["count"])
            return dict(item)

    def lookup(self, heard: str) -> Optional[str]:
        """Entidad aprendida para la forma, solo con evidencia suficiente."""
        with self._lock:
            item = self._load().get(normalize_text(heard))
        if item and int(item.get("count", 0)) >= self.min_evidence:
            return str(item["entity"])
        return None

    def active_mapping(self) -> Dict[str, str]:
        """Pares con evidencia suficiente, para ``correct_transcript(learned=...)``."""
        with self._lock:
            return {
                key: str(item["entity"])
                for key, item in self._load().items()
                if int(item.get("count", 0)) >= self.min_evidence
            }

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(item, heard=key) for key, item in sorted(self._load().items())]

    def delete(self, heard: str) -> bool:
        with self._lock:
            removed = self._load().pop(normalize_text(heard), None) is not None
            if removed:
                self._save()
                logger.info("Correccion aprendida borrada: '%s'", normalize_text(heard))
            return removed

    def clear(self) -> int:
        with self._lock:
            count = len(self._load())
            self._data = {}
            self._save()
            logger.info("Correcciones aprendidas borradas: %s", count)
            return count


_store: Optional[LearnedCorrections] = None
_store_lock = threading.Lock()


def get_learned_corrections(path: Optional[Path] = None, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> LearnedCorrections:
    global _store
    with _store_lock:
        if _store is None:
            _store = LearnedCorrections(path, min_evidence)
        return _store


__all__ = ["DEFAULT_MIN_EVIDENCE", "LearnedCorrections", "default_path", "get_learned_corrections"]
