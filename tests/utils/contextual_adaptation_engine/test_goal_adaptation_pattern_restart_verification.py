#!/usr/bin/env python3
"""
Verificacion de los patrones recuperados tras el reinicio (2.8.8.9.4.5).

Esta hoja NO implementa persistencia (2.8.8.9.4.3) ni carga (2.8.8.9.4.4):
comprueba que los patrones de aprendizaje recuperados siguen siendo correctos
y utilizables por el motor y por sus consumidores reales.

Alcance de la verificacion:

  1. El patron recuperado debe conservar el CONJUNTO CANONICO completo de los
     7 campos que produce `_analyze_learning_patterns()`, no solo los DATOS
     CRITICOS (item 5): `pattern_id, pattern_type, context, metrics,
     confidence, timestamp, description`.
  2. Las estructuras anidadas (`context`, `metrics`) deben sobrevivir intactas:
     no basta con que la clave exista.
  3. Los valores deben ser identicos a los del patron aprendido (ida y vuelta
     sin perdida).
  4. La fila que contiene el patron debe conservar su contexto completo
     (`adaptation_id`, `updated_strategies`, `convergence_metrics`, ...): de
     ella depende la restauracion de estrategias (2.8.8.9.3) y la convergencia
     del aprendizaje (item 6 de DATOS CRITICOS).
  5. El patron recuperado debe seguir siendo CONSUMIBLE por los lectores
     reales del motor: `_update_adaptive_strategies()` y el enlace
     `strategy["pattern_id"] -> pattern["pattern_id"]`.
  6. La recuperacion debe ser ESTABLE: un segundo reinicio no debe duplicar
     los patrones ni degradar sus datos, y un nuevo ciclo de aprendizaje
     posterior al reinicio no debe perder los patrones ya recuperados.
  7. Un patron no validado no debe contaminar a los patrones validados ni
     reaparecer tras el reinicio.

El motor se instancia con `data_dir` temporal, por lo que el test no lee ni
escribe sobre `data/` de produccion.
"""

import collections
import json
import os
import sys
import time

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextType, ContextualAdaptationEngine

# Contrato de DATOS CRITICOS, item 5 (roadmap 2.8.8.9.2.1).
CRITICAL_PATTERN_FIELDS = ("pattern_id", "pattern_type", "context", "metrics", "confidence")

# Conjunto canonico del patron de aprendizaje: los 7 campos que produce
# `_analyze_learning_patterns()` en `src/utils/contextual_adaptation_engine.py`.
CANONICAL_PATTERN_FIELDS = (
    "pattern_id", "pattern_type", "context", "metrics", "confidence", "timestamp", "description",
)

# Campos de la fila de resultado de aprendizaje que la carga debe conservar.
ROW_FIELDS = (
    "adaptation_id", "learned_patterns", "updated_strategies",
    "convergence_metrics", "timestamp", "status",
)

# Campos de la convergencia del aprendizaje (item 6 de DATOS CRITICOS).
CONVERGENCE_FIELDS = ("convergence_score", "learning_rate", "stability", "trend")

LEARNING_FILE = "goal_adaptation_learning_results.json"

MIN_SIMILAR_OBSERVATIONS = 3


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptacion con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def _feedback(adaptation_id, success=True, verified=True, impact=0.8,
              goal_type="navigation", context_type=ContextType.PRODUCTION.value,
              response_time=1.2, accuracy=0.97):
    """Datos de feedback de adaptacion de Goal de ejemplo."""
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
            "success": success,
            "performance_metrics": {"response_time": response_time, "accuracy": accuracy},
        },
        "verification_result": {"verified": verified, "impact_score": impact},
    }


def _learn(engine, count, prefix="obs", **kwargs):
    """Ejecutar `count` ciclos de aprendizaje y devolver los patrones producidos."""
    produced = []
    for index in range(1, count + 1):
        data = _feedback(f"{prefix}_{index}", **kwargs)
        feedback_result = engine._capture_goal_adaptation_feedback(data)
        assert feedback_result["success"] is True, feedback_result.get("error_message")
        learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
        assert learning_result["success"] is True, learning_result.get("error_message")
        produced.extend(learning_result["learned_patterns"])
    return produced


def _recovered_rows(engine):
    """Filas de resultados de aprendizaje presentes en la base de conocimiento."""
    return [row for row in engine.knowledge_base.get("learning_results", []) or []
            if isinstance(row, dict)]


def _recovered_patterns(engine):
    """Patrones presentes en el contenedor canonico tras la carga."""
    patterns = []
    for row in _recovered_rows(engine):
        patterns.extend(p for p in (row.get("learned_patterns") or []) if isinstance(p, dict))
    return patterns


def _pattern_key(pattern):
    """Clave multiconjunto para comparar patrones sin colapsar IDs repetidos.

    Un mismo `pattern_id` puede aparecer en varias filas de aprendizaje (una
    por ciclo de observacion); al comparar solo por `pattern_id` se pierden
    esas entradas distintas. Esta clave incluye el `timestamp`, unico por
    observacion, para que dos conjuntos de patrones se consideren iguales
    cuando contengan los mismos elementos con la misma frecuencia.
    """
    return tuple(sorted((pattern.get("pattern_id"), pattern.get("timestamp"))))


def _assert_pattern_multiset_equal(left, right, label="patrones"):
    """Comprobar que dos listas de patrones contienen los mismos elementos.

    Comparar por `pattern_id` solo serviria cuando cada ID aparece una unica
    vez; el motor puede registrar varias observaciones con el mismo ID (una
    por ciclo de aprendizaje), por lo que la comparacion debe ser de
    multiconjunto: mismos elementos con la misma frecuencia.
    """
    assert len(left) == len(right), (
        f"{label}: se esperaban {len(left)} patrones, se encontraron {len(right)}"
    )
    remaining = collections.Counter(_pattern_key(p) for p in right)
    for pattern in left:
        key = _pattern_key(pattern)
        assert remaining[key] > 0, (
            f"{label}: el patron {key} no aparece en el conjunto recuperado"
        )
        remaining[key] -= 1


def _pattern(pattern_id="pattern_001", confidence=0.9, pattern_type="goal_adaptation_success",
             goal_type="navigation", context_type="production"):
    """Patron de aprendizaje con la estructura real de 7 campos."""
    return {
        "pattern_id": pattern_id,
        "pattern_type": pattern_type,
        "context": {"goal_type": goal_type, "context_type": context_type,
                    "system_resources": {"cpu": 0.5, "memory": 0.3},
                    "expected_metrics": {"response_time": 2.0, "accuracy": 0.95}},
        "metrics": {"response_time": 1.5, "accuracy": 0.98, "success": True,
                    "verified": True, "impact_score": 0.8},
        "confidence": confidence,
        "timestamp": "2026-10-20T00:00:00",
        "description": "Patron de ejemplo",
    }


def _row(adaptation_id, patterns, updated_strategies=None):
    """Fila de resultado de aprendizaje."""
    return {
        "adaptation_id": adaptation_id,
        "learned_patterns": patterns,
        "updated_strategies": updated_strategies or {},
        "convergence_metrics": {"convergence_score": 0.85, "learning_rate": 0.1,
                                "stability": 0.8, "trend": "improving"},
        "timestamp": "2026-10-20T00:00:00",
        "status": "completed",
    }


def _write_learning_file(tmp_path, learning_results, strategies=None):
    """Escribir a mano un fichero de resultados de aprendizaje."""
    path = os.path.join(str(tmp_path), LEARNING_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"learning_results": learning_results,
                   "adaptation_strategies": strategies or {},
                   "last_updated": "2026-10-20T00:00:00"}, handle, indent=2, ensure_ascii=False)
    return path


def test_el_patron_recuperado_conserva_el_conjunto_canonico_completo(engine, tmp_path):
    """Tras el reinicio deben sobrevivir todos los campos canonicos del patron.

    Los DATOS CRITICOS (item 5) son un subconjunto de 5 campos; si el motor
    solo conservara esos, el patron recuperado perderia su `timestamp` y su
    `description`, que son los que lo describen a un lector humano.
    """
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    assert recovered, "Los patrones validados deben recuperarse tras el reinicio"
    for pattern in recovered:
        missing = [field for field in CANONICAL_PATTERN_FIELDS if field not in pattern]
        assert not missing, f"Faltan campos canonicos en el patron recuperado: {missing}"
        assert pattern["pattern_id"], "El patron recuperado debe conservar su `pattern_id`"


def test_el_patron_recuperado_conserva_las_estructuras_anidadas(engine, tmp_path):
    """Las estructuras anidadas deben sobrevivir intactas, no solo existir."""
    produced = _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    assert recovered, "Los patrones validados deben recuperarse tras el reinicio"
    _assert_pattern_multiset_equal(recovered, produced, "patrones recuperados")
    by_key = {_pattern_key(pattern): pattern for pattern in recovered}
    for original in produced:
        pattern = by_key.get(_pattern_key(original))
        assert pattern is not None, (
            f"El patron '{original['pattern_id']}' debe recuperarse tras el reinicio"
        )
        context = pattern.get("context")
        assert isinstance(context, dict), "El contexto recuperado debe seguir siendo un diccionario"
        assert context == original["context"], (
            f"El contexto recuperado difiere del original: {context!r} != {original['context']!r}"
        )
        assert context.get("goal_type") == "navigation"
        assert context.get("context_type") == ContextType.PRODUCTION.value
        assert isinstance(context.get("system_resources"), dict), (
            "Los recursos del sistema deben sobrevivir dentro del contexto"
        )
        assert isinstance(context.get("expected_metrics"), dict), (
            "Las metricas esperadas deben sobrevivir dentro del contexto"
        )
        metrics = pattern.get("metrics")
        assert isinstance(metrics, dict), "Las metricas recuperadas deben seguir siendo un diccionario"
        assert metrics == original["metrics"], (
            f"Las metricas recuperadas difieren del original: {metrics!r} != {original['metrics']!r}"
        )


def test_el_patron_recuperado_conserva_los_valores_sin_perdida(engine, tmp_path):
    """La ida y vuelta debe preservar el valor de cada campo canonico.

    La comparacion es de multiconjunto: el mismo `pattern_id` puede aparecer
    en varias observaciones (una por ciclo de aprendizaje), y cada una tiene
    su propio `timestamp`. Comparar solo por `pattern_id` colapsaria esas
    entradas y haria imposible comprobar que el `timestamp` se conserva.
    """
    produced = _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    assert recovered, "Los patrones validados deben recuperarse tras el reinicio"
    _assert_pattern_multiset_equal(recovered, produced, "patrones recuperados")

    by_key = {_pattern_key(pattern): pattern for pattern in recovered}
    for original in produced:
        pattern = by_key.get(_pattern_key(original))
        assert pattern is not None, (
            f"El patron '{original['pattern_id']}' debe recuperarse tras el reinicio"
        )
        for field in CANONICAL_PATTERN_FIELDS:
            assert pattern[field] == original[field], (
                f"El campo '{field}' cambio al reiniciar: "
                f"{pattern[field]!r} != {original[field]!r}"
            )


def test_la_fila_recuperada_conserva_su_contexto_y_su_convergencia(engine, tmp_path):
    """La fila que contiene el patron debe conservarse integra.

    De la fila dependen la restauracion de estrategias aprendidas
    (`updated_strategies`, 2.8.8.9.3) y la convergencia del aprendizaje
    (item 6 de DATOS CRITICOS).
    """
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    rows = _recovered_rows(restarted)
    assert len(rows) == MIN_SIMILAR_OBSERVATIONS, (
        f"Las filas de resultados de aprendizaje deben conservarse; "
        f"se recuperaron {len(rows)}"
    )
    for row in rows:
        missing = [field for field in ROW_FIELDS if field not in row]
        assert not missing, f"Faltan campos en la fila recuperada: {missing}"
        assert row["adaptation_id"], "La fila recuperada debe conservar su `adaptation_id`"
        convergence = row["convergence_metrics"]
        assert isinstance(convergence, dict), "La convergencia debe seguir siendo un diccionario"
        for field in CONVERGENCE_FIELDS:
            assert field in convergence, f"Falta el dato de convergencia '{field}'"
        assert isinstance(row["updated_strategies"], dict), (
            "Las estrategias actualizadas de la fila deben conservarse"
        )
        assert row["updated_strategies"], (
            "La fila debe conservar las estrategias aprendidas que la carga no debe vaciar"
        )


def test_el_patron_recuperado_sigue_disponible_para_los_consumidores(engine, tmp_path):
    """El patron recuperado debe seguir siendo legible por los consumidores reales.

    `_update_adaptive_strategies()` es el consumidor real de `learned_patterns`
    y las estrategias aprendidas enlazan con su patron via `pattern_id`.
    """
    produced = _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    pattern_ids = {pattern["pattern_id"] for pattern in produced}

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    assert recovered, "Los patrones validados deben recuperarse tras el reinicio"
    assert {pattern["pattern_id"] for pattern in recovered} == pattern_ids, (
        "Los patrones recuperados deben ser los mismos que se aprendieron"
    )

    # Consumidor real: el motor convierte los patrones recuperados en estrategias.
    updated = restarted._update_adaptive_strategies(
        recovered, restarted.knowledge_base.get("adaptation_strategies", {})
    )
    produced_strategies = [
        row for rows in updated.values() if isinstance(rows, list)
        for row in rows if isinstance(row, dict)
    ]
    assert produced_strategies, (
        "Los patrones recuperados deben producir estrategias en el motor reiniciado"
    )
    linked = [row for row in produced_strategies if row.get("pattern_id") in pattern_ids]
    assert linked, (
        "Las estrategias producidas deben enlazar con los patrones recuperados via `pattern_id`"
    )
    for strategy in linked:
        assert strategy.get("context", {}).get("context_type") == ContextType.PRODUCTION.value, (
            "La estrategia debe conservar el contexto del patron recuperado"
        )
        assert strategy.get("metrics"), "La estrategia debe conservar las metricas del patron"


def test_el_patron_recuperado_es_estable_tras_un_segundo_reinicio(engine, tmp_path):
    """Un segundo reinicio no debe duplicar ni degradar los patrones.

    La comparacion es de multiconjunto: el mismo `pattern_id` puede aparecer
    en varias observaciones (una por ciclo de aprendizaje), y cada una tiene
    su propio `timestamp`. Comparar solo por `pattern_id` colapsaria esas
    entradas y haria imposible comprobar que el `timestamp` se conserva.
    """
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    first = ContextualAdaptationEngine(data_dir=str(tmp_path))
    first_patterns = _recovered_patterns(first)
    assert first_patterns, "Los patrones validados deben recuperarse"

    second = ContextualAdaptationEngine(data_dir=str(tmp_path))
    second_patterns = _recovered_patterns(second)

    assert len(second_patterns) == len(first_patterns), (
        f"El segundo reinicio debe recuperar los mismos patrones; "
        f"primero {len(first_patterns)}, segundo {len(second_patterns)}"
    )
    assert {p["pattern_id"] for p in second_patterns} == {p["pattern_id"] for p in first_patterns}
    _assert_pattern_multiset_equal(second_patterns, first_patterns, "patrones del segundo reinicio")

    by_key = {_pattern_key(pattern): pattern for pattern in first_patterns}
    for pattern in second_patterns:
        original = by_key[_pattern_key(pattern)]
        for field in CANONICAL_PATTERN_FIELDS:
            assert pattern[field] == original[field], (
                f"El campo '{field}' se degrado tras el segundo reinicio: "
                f"{pattern[field]!r} != {original[field]!r}"
            )


def test_un_nuevo_ciclo_de_aprendizaje_no_pierde_los_patrones_recuperados(engine, tmp_path):
    """Aprender de nuevo tras el reinicio no debe perder lo ya recuperado.

    El motor reiniciado sigue las filas cargadas en su base de conocimiento y
    las vuelve a persistir: los patrones recuperados deben sobrevivir al ciclo
    de guardado posterior al reinicio.
    """
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    recovered_before = {p["pattern_id"] for p in _recovered_patterns(
        ContextualAdaptationEngine(data_dir=str(tmp_path)))}

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    _learn(restarted, 1, prefix="after_restart")

    with open(os.path.join(str(tmp_path), LEARNING_FILE), "r", encoding="utf-8") as handle:
        persisted = json.load(handle)
    persisted_ids = {
        pattern["pattern_id"]
        for row in persisted.get("learning_results", []) or []
        for pattern in (row.get("learned_patterns") or []) if isinstance(pattern, dict)
    }

    assert recovered_before <= persisted_ids, (
        f"Los patrones recuperados antes del nuevo ciclo deben seguir persistidos; "
        f"se perdieron {sorted(recovered_before - persisted_ids)}"
    )


def test_un_patron_no_validado_no_contamina_a_los_patrones_recuperados(tmp_path):
    """Un patron no validado no debe reaparecer ni degradar a los validados.

    El fichero contiene 3 observaciones validadas de una identidad y una
    observacion no validada de otra identidad distinta.
    """
    valid_ids = {f"pattern_{index:03d}" for index in range(MIN_SIMILAR_OBSERVATIONS)}
    rows = [_row(f"obs_{index}", [_pattern(pattern_id=f"pattern_{index:03d}")])
            for index in range(MIN_SIMILAR_OBSERVATIONS)]
    rows.append(_row("obs_invalid",
                      [_pattern(pattern_id="pattern_invalid", confidence=0.4, goal_type="other")]))
    _write_learning_file(tmp_path, rows)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    recovered_ids = {pattern["pattern_id"] for pattern in recovered}
    assert recovered_ids == valid_ids, (
        f"Solo deben recuperarse los patrones validados; se recuperaron {sorted(recovered_ids)}"
    )
    assert "pattern_invalid" not in recovered_ids, (
        "Un patron no validado no debe reaparecer tras el reinicio"
    )
    for pattern in recovered:
        assert float(pattern.get("confidence", 0.)) >= restarted.config["confidence_threshold"], (
            "Un patron no validado no debe degradar la confianza de los validados"
        )
        assert pattern["context"].get("goal_type") == "navigation", (
            "Un patron no validado no debe contaminar el contexto de los validados"
        )


def test_la_carga_no_escribe_en_el_fichero_persistido(engine, tmp_path):
    """La carga debe ser una operacion de solo lectura sobre el fichero.

    Si la carga reescribiera el fichero, el reinicio alteraria los datos
    persistidos y la recuperacion dejaria de ser verificable.
    """
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    path = os.path.join(str(tmp_path), LEARNING_FILE)
    with open(path, "r", encoding="utf-8") as handle:
        before = handle.read()
    before_stat = os.stat(path)
    # La marca de tiempo debe tener granularidad suficiente para distinguir
    # una reescritura posterior de la lectura original.
    time.sleep(0.05)

    ContextualAdaptationEngine(data_dir=str(tmp_path))

    with open(path, "r", encoding="utf-8") as handle:
        after = handle.read()
    after_stat = os.stat(path)
    assert after == before, "La carga no debe modificar el contenido del fichero persistido"
    assert after_stat.st_size == before_stat.st_size, (
        "La carga no debe alterar el tamano del fichero persistido"
    )
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns, (
        "La carga no debe reescribir el fichero persistido"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
