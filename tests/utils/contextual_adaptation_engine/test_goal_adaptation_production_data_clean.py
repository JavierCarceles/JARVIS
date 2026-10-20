#!/usr/bin/env python3
"""
Guarda de integridad de los ficheros de persistencia de Goal en `data/` (2.8.8.9.4.6).

CONTEXTO (fallo real corregido en esta hoja)
La subhoja 2.8.8.9.4 (PERSISTENCIA DE PATRONES) dejo documentada en 2.8.8.9.4.1 una
contaminacion de los datos de produccion: los ficheros de persistencia de Goal
(`data/goal_adaptation_feedback.json` y `data/goal_adaptation_learning_results.json`)
contenian EXCLUSIVAMENTE datos de test, porque los tests creaban el motor sin
`data_dir` y escribian sobre el `data/` real. Verificado en runtime antes de esta
correccion:
- `data/goal_adaptation_feedback.json`: 18 registros y 18 entradas de historial, TODOS
  con `adaptation_id` `test_adaptation_001` (100% contaminado, y crecia en cada
  ejecucion de la suite).
- `data/goal_adaptation_learning_results.json`: 1 fila `test_load_001` con el patron
  `pattern_001` y la estrategia `strategy_001`, ambos artefactos del fixture de test
  `test_load_goal_adaptation_feedback.py`.
El resultado era que la persistencia de patrones de produccion no contenia ningun
patron real, sino fixtures de test.

Este test fija la ausencia de esa contaminacion para que no pueda volver a introducirse:
1. Los ficheros de persistencia de Goal de `data/` no deben contener artefactos de test.
2. El ciclo real de persistencia de patrones, ejecutado con `data_dir` temporal, NO debe
   reescribir los ficheros de produccion.
3. Ningun test del motor que ejecute la via de escritura de Goal puede crear el motor
   sin `data_dir` (chequeo estatico, evita la reaparicion del fallo).

El test no escribe en `data/`: solo lo lee.
"""

import hashlib
import json
import os
import re
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine

TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, '..'))
PRODUCTION_DATA_DIR = os.path.join(REPO_ROOT, 'data')

GOAL_FILES = (
    "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results.json",
)

# Prefijo de los identificadores que delatan un artefacto de test.
TEST_ID_PREFIX = "test_"

# Metodos del motor que ESCRIBEN en los ficheros de persistencia de Goal.
GOAL_WRITE_METHODS = (
    "_capture_goal_adaptation_feedback",
    "_execute_goal_adaptation_learning_loop",
    "_record_learning_results",
    "_save_goal_adaptation_feedback",
    "_save_goal_adaptation_learning_results",
)


def _is_test_id(value):
    """Indicar si un identificador es un artefacto de test."""
    return isinstance(value, str) and value.startswith(TEST_ID_PREFIX)


def _load(path):
    """Cargar un JSON de produccion; `None` si no existe o no es valido."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _production_signature():
    """Huella (existencia, mtime, tamano, sha256) de los ficheros de Goal de produccion."""
    signature = {}
    for name in GOAL_FILES:
        path = os.path.join(PRODUCTION_DATA_DIR, name)
        if not os.path.isfile(path):
            signature[name] = None
            continue
        with open(path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        stat = os.stat(path)
        signature[name] = (stat.st_mtime_ns, stat.st_size, digest)
    return signature


def _feedback(adaptation_id, context_type="production", goal_type="navigation"):
    """Feedback de adaptacion de Goal de ejemplo (una observacion)."""
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": f"goal_original_{adaptation_id}",
        "adapted_goal_id": f"goal_adapted_{adaptation_id}",
        "adaptation_context": {
            "goal_type": goal_type,
            "context_type": context_type,
            "system_resources": {"cpu": 0.5, "memory": 0.3},
            "expected_metrics": {"response_time": 2.0, "accuracy": 0.95},
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {"response_time": 1.2, "accuracy": 0.97},
        },
        "verification_result": {"verified": True, "impact_score": 0.5},
    }


def test_los_ficheros_de_persistencia_de_goal_no_contienen_artefactos_de_test():
    """Los ficheros de produccion de Goal no deben contener datos de test."""
    feedback = _load(os.path.join(PRODUCTION_DATA_DIR, GOAL_FILES[0]))
    if feedback is not None:
        offenders = [
            record.get("adaptation_id")
            for record in (feedback.get("goal_adaptation_feedback") or [])
            if isinstance(record, dict) and _is_test_id(record.get("adaptation_id"))
        ]
        offenders += [
            entry.get("adaptation_id")
            for entry in (feedback.get("adaptation_history") or [])
            if isinstance(entry, dict) and _is_test_id(entry.get("adaptation_id"))
        ]
        assert offenders == [], (
            f"'{GOAL_FILES[0]}' contiene artefactos de test: {offenders}. "
            "La persistencia de Goal de produccion esta contaminada."
        )

    learning = _load(os.path.join(PRODUCTION_DATA_DIR, GOAL_FILES[1]))
    if learning is not None:
        offenders = []
        for row in (learning.get("learning_results") or []):
            if not isinstance(row, dict):
                continue
            if _is_test_id(row.get("adaptation_id")):
                offenders.append(row.get("adaptation_id"))
            for pattern in (row.get("learned_patterns") or []):
                if isinstance(pattern, dict) and _is_test_id(pattern.get("pattern_id")):
                    offenders.append(pattern.get("pattern_id"))
        for strategy_id in (learning.get("adaptation_strategies") or {}):
            if _is_test_id(str(strategy_id)):
                offenders.append(strategy_id)
        assert offenders == [], (
            f"'{GOAL_FILES[1]}' contiene artefactos de test: {offenders}. "
            "La persistencia de patrones de produccion esta contaminada."
        )


def test_el_ciclo_de_patrones_no_reescribe_los_ficheros_de_produccion(tmp_path):
    """El ciclo real de persistencia, aislado, no toca los ficheros de produccion."""
    before = _production_signature()

    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    for index in range(1, 4):
        feedback_result = engine._capture_goal_adaptation_feedback(
            _feedback(f"guard_obs_{index}")
        )
        assert feedback_result["success"] is True, feedback_result.get("error_message")
        learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
        assert learning_result["success"] is True, learning_result.get("error_message")

    # El ciclo debe haber persistido de verdad en el directorio temporal: si no,
    # la comprobacion siguiente seria vacua.
    persisted = os.path.join(str(tmp_path), "goal_adaptation_learning_results.json")
    assert os.path.isfile(persisted), "El motor debe persistir en su `data_dir` temporal"
    with open(persisted, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    patterns = [
        pattern
        for row in (payload.get("learning_results") or [])
        if isinstance(row, dict)
        for pattern in (row.get("learned_patterns") or [])
        if isinstance(pattern, dict)
    ]
    assert patterns, "Tras 3 observaciones similares debe persistirse un patron validado"

    after = _production_signature()
    assert before == after, (
        f"El ciclo de persistencia modifico los ficheros de produccion: "
        f"antes={before}, despues={after}"
    )


def _engine_calls_without_data_dir(source):
    """Devolver las llamadas al constructor del motor sin `data_dir`."""
    offenders = []
    # El nombre se concatena para que este fichero no se detecte a si mismo.
    class_name = "ContextualAdaptationEngine"
    marker = class_name + "("
    index = source.find(marker)
    while index != -1:
        cursor = index + len(marker)
        depth = 1
        while cursor < len(source) and depth:
            if source[cursor] == "(":
                depth += 1
            elif source[cursor] == ")":
                depth -= 1
            cursor += 1
        arguments = source[index + len(marker):cursor - 1]
        if "data_dir" not in arguments:
            offenders.append("%s(%s)" % (class_name, arguments.strip()))
        index = source.find(marker, cursor)
    return offenders


def test_los_tests_del_motor_aislan_el_data_dir_de_produccion():
    """Ningun test que escriba en Goal puede crear el motor sin `data_dir`."""
    offenders = {}
    for base, dirs, names in os.walk(TESTS_DIR):
        dirs[:] = [name for name in dirs if name not in ("__pycache__",)]
        for name in sorted(names):
            if not (name.startswith("test_") and name.endswith(".py")):
                continue
            path = os.path.join(base, name)
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            if not any(method in source for method in GOAL_WRITE_METHODS):
                continue
            calls = _engine_calls_without_data_dir(source)
            if calls:
                offenders[os.path.relpath(path, REPO_ROOT)] = calls

    assert offenders == {}, (
        "Estos tests ejecutan la via de escritura de Goal sin aislar el `data_dir` "
        "y contaminan los ficheros de persistencia de produccion: %s" % offenders
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
