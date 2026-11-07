# -*- coding: utf-8 -*-
"""Helper reutilizable para capturar y comparar el estado exacto de un
entities.json antes y despues de una operacion.

Unidad 3.8.4.4.3 (padre 3.8.4.4, FASE 3.8 — CONOCIMIENTO DINAMICO SIN ALTERAR
ENTITIES.JSON).

El helper cumple estrictamente con el requisito de la unidad:

- Trabaja SIEMPRE sobre copias en directorios temporales.
- Nunca escribe ni modifica el fichero real de datos (source).
- Captura el estado exacto (contenido bytes + hash SHA-256 + tamano) antes y
  despues de una operacion.
- Compara los snapshots y reporta si el fichero cambio o quedo intacto.

Diseno:
- Es generico: no conoce ApplicationManager, MemoryManager ni ninguna logica
  de negocio. Recibe una ruta de origen y un callable `operation(temp_path)`
  que el llamador provee.
- No depende de la CWD (conftest pone la suite en un sandbox): todas las rutas
  son absolutas y el directorio temporal se crea en la ruta temporal del
  sistema.
- Solo usa estandar de Python (hashlib, shutil, tempfile, pathlib, dataclasses).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class EntitiesJsonSnapshot:
    """Estado exacto de un fichero entities.json en un instante dado.

    Atributos:
        path: ruta absoluta resuelta del fichero capturado.
        size_bytes: tamano en bytes del contenido.
        sha256: hash SHA-256 hexadecimal del contenido.
        contenido: copia de los bytes del fichero en el instante de captura.
    """

    path: Path
    size_bytes: int
    sha256: str
    contenido: bytes


def compute_sha256(contenido: bytes) -> str:
    """Devuelve el hash SHA-256 (hexadecimal) del contenido dado."""
    return hashlib.sha256(contenido).hexdigest()


def snapshot_entities_json(path: str | Path) -> EntitiesJsonSnapshot:
    """Captura el estado exacto (hash y contenido) de un entities.json.

    Solo lectura: no modifica el fichero.
    """
    p = Path(path).resolve()
    contenido = p.read_bytes()
    return EntitiesJsonSnapshot(
        path=p,
        size_bytes=len(contenido),
        sha256=compute_sha256(contenido),
        contenido=contenido,
    )


def copy_to_temp_dir(source: str | Path, dir_prefix: str = "jarvis_entities_state_") -> Path:
    """Copia un fichero entities.json a un nuevo directorio temporal.

    Devuelve la ruta del directorio temporal creado; el fichero queda en
    ``<directorio_temporal>/<nombre_original>``.

    Nunca escribe ni modifica el fichero original de origen.
    """
    src = Path(source).resolve()
    tmp_dir = Path(tempfile.mkdtemp(prefix=dir_prefix))
    shutil.copy2(src, tmp_dir / src.name)
    return tmp_dir


def snapshots_equal(a: EntitiesJsonSnapshot, b: EntitiesJsonSnapshot) -> bool:
    """Compara dos snapshots por hash SHA-256 y contenido (el tamano queda
    implicito en el contenido). Devuelve True si representan el mismo estado."""
    return a.sha256 == b.sha256 and a.contenido == b.contenido


def verify_entities_json_unchanged(
    source: str | Path,
    operation: Callable[[Path], Any],
    *,
    dir_prefix: str = "jarvis_entities_state_",
) -> dict[str, Any]:
    """Ejecuta ``operation`` sobre una COPIA temporal de ``source`` y compara
    el estado de entities.json antes y despues.

    Nunca toca el fichero real de datos. Adicionalmente verifica que el
    fichero original no fue modificado durante la ejecucion (captura del
    original antes y despues).

    El callable ``operation`` recibe la ruta absoluta de la copia temporal
    del entities.json y puede modificarla libremente (por ejemplo, apuntando
    un MemoryManager real a ese directorio temporal y llamando a
    ``save_entity``).

    Devuelve un diccionario con:
        - changed: True si la copia temporal cambio tras la operacion.
        - source_untouched: True si el fichero real no se modifico.
        - before: snapshot de la copia temporal antes de la operacion.
        - after: snapshot de la copia temporal despues de la operacion.
        - source_before: snapshot del fichero real antes de la operacion.
        - source_after: snapshot del fichero real despues de la operacion.
        - operation_result: valor devuelto por ``operation``.
    """
    src = Path(source).resolve()

    # Estado del fichero real antes (para demostrar que no se toca).
    source_before = snapshot_entities_json(src)

    # Copia de trabajo en directorio temporal (el original nunca se escribe).
    tmp_dir = copy_to_temp_dir(src, dir_prefix=dir_prefix)
    try:
        tmp_file = tmp_dir / src.name
        before = snapshot_entities_json(tmp_file)
        operation_result = operation(tmp_file)
        after = snapshot_entities_json(tmp_file)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Estado del fichero real despues (debe igualar al de antes).
    source_after = snapshot_entities_json(src)

    changed = not snapshots_equal(before, after)
    source_untouched = snapshots_equal(source_before, source_after)

    return {
        "changed": changed,
        "source_untouched": source_untouched,
        "before": before,
        "after": after,
        "source_before": source_before,
        "source_after": source_after,
        "operation_result": operation_result,
    }
