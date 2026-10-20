#!/usr/bin/env python3
"""
Test de carga de patrones de aprendizaje (2.8.8.9.4.4).

Verifica que `_load_goal_adaptation_learning_results()` recupera únicamente
los patrones que cumplen el contrato de DATOS CRITICOS (item 5) y que la
carga es la inversa exacta del guardado.

CONTRATO
- Un patron persistido solo se recupera si su `confidence` alcanza el umbral
  configurado en el motor (`confidence_threshold`, 0.7 por defecto) y si tiene
  un minimo de `min_similar_observations` (3) observaciones similares.
- La identidad de un patron es `pattern_type` + `context` (`goal_type` y
  `context_type`); el `pattern_id` se regenera en cada llamada y no agrupa.
- Las filas de resultados de aprendizaje se conservan siempre: de ellas depende
  la restauracion de estrategias aprendidas (2.8.8.9.3).
- El ciclo guardar/cargar no puede perder un patron validado: el guardado y la
  carga cuentan las mismas observaciones (las que superan el umbral).

AISLAMIENTO
El motor se instancia siempre con `data_dir` temporal
(`ContextualAdaptationEngine(data_dir=str(tmp_path))`), por lo que el test no
lee ni escribe sobre `data/` de produccion.
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextType, ContextualAdaptationEngine

MIN_SIMILAR_OBSERVATIONS = 3
CRITICAL_PATTERN_FIELDS = ("pattern_id", "pattern_type", "context", "metrics", "confidence")

LEARNING_FILE = "goal_adaptation_learning_results.json"


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptacion con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def _feedback(adaptation_id, success=True, verified=True, impact=0.8,
              context_type=ContextType.PRODUCTION.value, goal_type="navigation",
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
        data = _feedback(f"{prefix}_{index}", response_time=1.0 + index * 0.1,
                         accuracy=0.90 + index * 0.01, **kwargs)
        feedback_result = engine._capture_goal_adaptation_feedback(data)
        assert feedback_result["success"] is True, feedback_result.get("error_message")
        learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
        assert learning_result["success"] is True, learning_result.get("error_message")
        produced.extend(learning_result["learned_patterns"])
    return produced


def _write_learning_file(tmp_path, learning_results, strategies=None):
    """Escribir a mano un fichero de resultados de aprendizaje."""
    path = os.path.join(str(tmp_path), LEARNING_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"learning_results": learning_results,
                   "adaptation_strategies": strategies or {},
                   "last_updated": "2026-10-20T00:00:00"}, handle, indent=2, ensure_ascii=False)
    return path


def _pattern(pattern_id="pattern_001", confidence=0.9, pattern_type="goal_adaptation_success",
             goal_type="navigate", context_type="production"):
    """Patron de aprendizaje con la estructura real de 7 campos."""
    return {
        "pattern_id": pattern_id,
        "pattern_type": pattern_type,
        "context": {"goal_type": goal_type, "context_type": context_type,
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
        "convergence_metrics": {"convergence_score": 0.85, "learning_rate": 0.1, "stability": 0.8},
        "timestamp": "2026-10-20T00:00:00",
        "status": "completed",
    }


def _recovered_patterns(engine):
    """Patrones presentes en el contenedor canonico tras la carga."""
    patterns = []
    for row in engine.knowledge_base.get("learning_results", []) or []:
        if not isinstance(row, dict):
            continue
        patterns.extend(p for p in (row.get("learned_patterns") or []) if isinstance(p, dict))
    return patterns


def test_la_carga_recupera_el_patron_validado(engine, tmp_path):
    """Tras el reinicio deben recuperarse los patrones validados."""
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    persisted = os.path.join(str(tmp_path), LEARNING_FILE)
    assert os.path.isfile(persisted), "El motor debe persistir los resultados de aprendizaje"

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    assert recovered, "Los patrones validados deben recuperarse tras el reinicio"
    assert all(p.get("pattern_type") == "goal_adaptation_success" for p in recovered)
    assert all(float(p.get("confidence", 0.)) >= restarted.config["confidence_threshold"]
               for p in recovered)


def test_la_carga_preserva_los_datos_criticos_y_las_estructuras_anidadas(engine, tmp_path):
    """El patron recuperado debe conservar los datos criticos y sus estructuras."""
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered_patterns(restarted)
    assert recovered, "Los patrones validados deben recuperarse tras el reinicio"
    for pattern in recovered:
        for field in CRITICAL_PATTERN_FIELDS:
            assert field in pattern, f"Falta el dato critico '{field}'"
        assert pattern["pattern_id"], "El patron recuperado debe conservar su `pattern_id`"
        assert isinstance(pattern["context"], dict), "Debe conservar su contexto"
        assert isinstance(pattern["metrics"], dict), "Debe conservar sus metricas"
        assert pattern["context"].get("goal_type"), "El contexto debe conservar su `goal_type`"


def test_la_carga_no_recupera_un_patron_por_debajo_del_umbral_de_confianza(tmp_path):
    """Un patron persistido con confianza insuficiente no debe recuperarse.

    Es la regla "DATOS QUE NO DEBEN PERSISTIR: Patrones no validados
    (confianza < 0.7)".
    """
    _write_learning_file(tmp_path, [_row("obs_001", [_pattern(confidence=0.5)])])

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    assert _recovered_patterns(restarted) == [], (
        "Un patron por debajo del umbral no debe recuperarse; "
        f"se recuperaron {_recovered_patterns(restarted)}"
    )


def test_la_carga_no_recupera_un_patron_con_observaciones_insuficientes(tmp_path):
    """Un patron persistido con una sola observacion no debe recuperarse.

    El item 5 de DATOS CRITICOS exige un minimo de 3 observaciones similares.
    Este caso reproduce el fichero real de produccion, que contiene un patron
    de una sola observacion.
    """
    _write_learning_file(tmp_path, [_row("obs_001", [_pattern(confidence=0.9)])])

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    assert _recovered_patterns(restarted) == [], (
        "Un patron con observaciones insuficientes no debe recuperarse; "
        f"se recuperaron {_recovered_patterns(restarted)}"
    )


def test_la_carga_usa_el_umbral_configurado_en_el_motor(tmp_path):
    """El umbral de la carga debe ser el configurado en el motor."""
    config_path = os.path.join(str(tmp_path), "engine_config.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump({"confidence_threshold": 0.95}, handle)

    rows = [_row(f"obs_{index}", [_pattern(pattern_id=f"pattern_{index:03d}", confidence=0.9)])
            for index in range(MIN_SIMILAR_OBSERVATIONS)]
    _write_learning_file(tmp_path, rows)

    tuned = ContextualAdaptationEngine(config_path=config_path, data_dir=str(tmp_path))
    assert tuned.config["confidence_threshold"] == 0.95

    assert _recovered_patterns(tuned) == [], (
        "Con `confidence_threshold` 0.95 no debe recuperarse ningun patron; "
        f"se recuperaron {_recovered_patterns(tuned)}"
    )


def test_la_carga_conserva_las_filas_para_restaurar_las_estrategias(tmp_path):
    """Descartar un patron no debe impedir restaurar las estrategias aprendidas.

    Las filas de resultados de aprendizaje son las que conservan el contexto
    exacto de cada estrategia aprendida (2.8.8.9.3).
    """
    strategies = {
        "strategy_001": {
            "strategy_id": "strategy_001",
            "confidence": 0.85,
            "success_rate": 0.9,
            "last_updated": "2026-10-20T00:00:00",
            "failure_count": 0,
            "context": {"goal_type": "navigation", "context_type": "production"},
        }
    }
    row = _row("obs_001", [_pattern(confidence=0.5)], updated_strategies={"production": [strategies["strategy_001"]]})
    _write_learning_file(tmp_path, [row], strategies=strategies)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    assert len(restarted.knowledge_base.get("learning_results", [])) == 1, (
        "La fila de resultados de aprendizaje debe conservarse"
    )
    projected = [entry for rows in restarted.knowledge_base["adaptation_strategies"].values()
                 if isinstance(rows, list) for entry in rows]
    assert len(projected) == 1, "La estrategia aprendida debe restaurarse"
    assert projected[0].get("strategy_id") == "strategy_001"


def test_la_carga_es_estable_tras_un_segundo_reinicio(engine, tmp_path):
    """Un segundo reinicio no debe duplicar ni degradar los patrones."""
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
    assert {p.get("pattern_id") for p in second_patterns} == {p.get("pattern_id") for p in first_patterns}


def test_la_carga_es_la_inversa_exacta_del_guardado(engine, tmp_path):
    """Lo que el guardado escribe es exactamente lo que la carga recupera.

    Este test fija que el ciclo guardar/cargar no puede perder un patron
    validado: el guardado y la carga cuentan las mismas observaciones.
    """
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    with open(os.path.join(str(tmp_path), LEARNING_FILE), "r", encoding="utf-8") as handle:
        persisted = json.load(handle)
    persisted_patterns = [p for row in persisted.get("learning_results", []) or []
                          for p in (row.get("learned_patterns") or []) if isinstance(p, dict)]
    assert persisted_patterns, "El patron validado debe estar persistido"

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    recovered = _recovered_patterns(restarted)

    assert len(recovered) == len(persisted_patterns), (
        f"La carga debe recuperar exactamente los patrones persistidos; "
        f"persistidos {len(persisted_patterns)}, recuperados {len(recovered)}"
    )
    assert {p.get("pattern_id") for p in recovered} == {p.get("pattern_id") for p in persisted_patterns}


def test_el_ciclo_guardar_cargar_no_pierde_ningun_patron(engine, tmp_path):
    """El ciclo guardar/cargar no puede perder ningun patron persistido.

    Caso de confianza mixta en el mismo contexto: dos observaciones de fallo
    con confianza 0.64 y una de fallo con confianza 0.96. Solo las
    observaciones que superan el umbral cuentan como evidencia, y el guardado
    y la carga aplican el mismo criterio; por eso ningun patron persistido
    puede desaparecer en el reinicio.
    """
    _learn(engine, 2, prefix="low", success=False, verified=False, impact=0.1)
    _learn(engine, 1, prefix="high", success=False, verified=False, impact=0.8)

    with open(os.path.join(str(tmp_path), LEARNING_FILE), "r", encoding="utf-8") as handle:
        persisted = json.load(handle)
    persisted_patterns = [p for row in persisted.get("learning_results", []) or []
                          for p in (row.get("learned_patterns") or []) if isinstance(p, dict)]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    recovered = _recovered_patterns(restarted)

    assert {p.get("pattern_id") for p in recovered} == {p.get("pattern_id") for p in persisted_patterns}, (
        f"La carga no puede perder patrones persistidos; "
        f"persistidos {[p.get('pattern_id') for p in persisted_patterns]}, "
        f"recuperados {[p.get('pattern_id') for p in recovered]}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
