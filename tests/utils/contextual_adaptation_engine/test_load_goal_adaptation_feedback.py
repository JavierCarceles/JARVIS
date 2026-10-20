#!/usr/bin/env python3
"""
Test de carga de feedback acumulado de adaptación de Goal (2.8.8.9.2.4 / 2.8.8.9.2.5)

Verifica que el feedback, el historial de adaptación, los resultados de
aprendizaje y las estrategias persistidos se recuperan correctamente tras
un reinicio (nueva instancia del motor).

La carga se aísla en un directorio temporal (`data_dir`), por lo que el test
no lee ni escribe sobre `data/` de producción.
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine


def _write_feedback_file(data_dir, records):
    """Escribir un archivo de feedback con los registros indicados."""
    path = os.path.join(data_dir, "goal_adaptation_feedback.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({"goal_adaptation_feedback": records, "last_updated": "2026-10-14T00:00:00"},
                  f, indent=2, ensure_ascii=False)
    return path


def _write_learning_file(data_dir, records, strategies):
    """Escribir un archivo de resultados de aprendizaje."""
    path = os.path.join(data_dir, "goal_adaptation_learning_results.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({"learning_results": records, "adaptation_strategies": strategies,
                   "last_updated": "2026-10-14T00:00:00"}, f, indent=2, ensure_ascii=False)
    return path


@pytest.fixture
def persisted_data(tmp_path):
    """Preparar datos persistidos de feedback, aprendizaje y estrategias."""
    feedback_records = [
        {
            "adaptation_id": "test_load_001",
            "analysis": {
                "performance_improvement": 15.0,
                "pattern_recognition": [
                    {
                        "pattern_type": "goal_adaptation_success",
                        "context": {"goal_type": "navigate"},
                        "metrics": {"response_time": 1.5, "accuracy": 0.98},
                        "timestamp": "2026-10-14T00:00:00",
                        "confidence": 0.9
                    }
                ],
                "strategic_insights": []
            },
            "timestamp": "2026-10-14T00:00:00",
            "status": "processed"
        },
        {
            "adaptation_id": "test_load_002",
            "analysis": {
                "performance_improvement": 8.0,
                "pattern_recognition": [
                    {
                        "pattern_type": "goal_adaptation_success",
                        "context": {"goal_type": "search"},
                        "metrics": {"response_time": 1.2, "accuracy": 0.95},
                        "timestamp": "2026-10-14T00:00:00",
                        "confidence": 0.85
                    }
                ],
                "strategic_insights": [
                    {
                        "strategy_type": "adaptation_strategy",
                        "context": {"goal_type": "search"},
                        "metrics": {"response_time": 1.2, "accuracy": 0.95},
                        "timestamp": "2026-10-14T00:00:00",
                        "confidence": 0.8
                    }
                ]
            },
            "timestamp": "2026-10-14T00:00:00",
            "status": "processed"
        }
    ]

    learning_records = [
        {
            "adaptation_id": "test_load_001",
            "learned_patterns": [
                {
                    "pattern_id": "pattern_001",
                    "pattern_type": "goal_adaptation_success",
                    "confidence": 0.9,
                    "context": {"goal_type": "navigate"},
                    "metrics": {"response_time": 1.5, "accuracy": 0.98}
                }
            ],
            "updated_strategies": {
                "strategy_001": {
                    "confidence": 0.85,
                    "success_rate": 0.9,
                    "last_updated": "2026-10-14T00:00:00"
                }
            },
            "convergence_metrics": {
                "convergence_score": 0.85,
                "learning_rate": 0.1,
                "stability": 0.8,
                "trend": "improving"
            }
        }
    ]

    strategies = {
        "strategy_001": {
            "confidence": 0.85,
            "success_rate": 0.9,
            "last_updated": "2026-10-14T00:00:00",
            "failure_count": 0
        }
    }

    _write_feedback_file(str(tmp_path), feedback_records)
    _write_learning_file(str(tmp_path), learning_records, strategies)
    return str(tmp_path)


def test_carga_feedback_acumulado(persisted_data):
    """El feedback acumulado debe cargarse con su estructura intacta."""
    engine = ContextualAdaptationEngine(data_dir=persisted_data)

    loaded_feedback = engine.knowledge_base["goal_adaptation_feedback"]
    assert len(loaded_feedback) == 2, "Deben cargarse los 2 registros de feedback"

    first_record = loaded_feedback[0]
    assert first_record["adaptation_id"] == "test_load_001"
    assert first_record["status"] == "processed"
    assert first_record["timestamp"] == "2026-10-14T00:00:00"

    analysis = first_record["analysis"]
    assert analysis["performance_improvement"] == 15.0
    assert len(analysis["pattern_recognition"]) == 1
    assert analysis["pattern_recognition"][0]["confidence"] == 0.9


def test_carga_resultados_aprendizaje(persisted_data):
    """Los resultados de aprendizaje deben cargarse con sus patrones."""
    engine = ContextualAdaptationEngine(data_dir=persisted_data)

    loaded_learning = engine.knowledge_base["learning_results"]
    assert len(loaded_learning) == 1, "Debe cargarse el resultado de aprendizaje"

    record = loaded_learning[0]
    assert record["adaptation_id"] == "test_load_001"
    assert len(record["learned_patterns"]) == 1
    assert record["learned_patterns"][0]["pattern_id"] == "pattern_001"


def test_carga_estrategias(persisted_data):
    """Las estrategias aprendidas deben cargarse completas."""
    engine = ContextualAdaptationEngine(data_dir=persisted_data)

    # El mapa `adaptation_strategies` conserva el contrato `contexto -> lista` del
    # motor (2.8.5/2.8.6); la estrategia persistida se proyecta sobre él.
    strategies = engine.knowledge_base["adaptation_strategies"]
    loaded = [row for rows in strategies.values() if isinstance(rows, list) for row in rows]
    assert len(loaded) == 1, "Debe cargarse la estrategia persistida"

    strategy = loaded[0]
    assert strategy["strategy_id"] == "strategy_001"
    for key in ("confidence", "success_rate", "last_updated", "failure_count"):
        assert key in strategy, f"Falta la clave '{key}' en la estrategia cargada"
    assert strategy["confidence"] == 0.85
    assert strategy["failure_count"] == 0


def test_inicializacion_crea_estructuras_base(persisted_data):
    """La inicialización debe crear todas las estructuras base."""
    engine = ContextualAdaptationEngine.__new__(ContextualAdaptationEngine)
    engine.data_dir = persisted_data
    engine.knowledge_base = {}
    engine.logger = ContextualAdaptationEngine(data_dir=persisted_data).logger
    engine.adaptation_history = []

    engine._initialize_goal_adaptation_persistence()

    for structure in ("goal_adaptation_feedback", "learning_results", "adaptation_strategies"):
        assert structure in engine.knowledge_base, (
            f"Debe inicializarse la estructura '{structure}'"
        )


def test_inicializacion_conserva_datos_persistidos(persisted_data):
    """Los datos persistidos deben conservarse tras la inicialización."""
    engine = ContextualAdaptationEngine(data_dir=persisted_data)

    assert len(engine.knowledge_base["goal_adaptation_feedback"]) == 2
    assert len(engine.knowledge_base["learning_results"]) == 1
    loaded = [row for rows in engine.knowledge_base["adaptation_strategies"].values()
              if isinstance(rows, list) for row in rows]
    assert len(loaded) == 1, "Debe conservarse la estrategia persistida"
    assert loaded[0]["strategy_id"] == "strategy_001"


def test_carga_adaptacion_history(persisted_data):
    """El historial de adaptación persistido debe cargarse (2.8.8.9.2.1)."""
    path = os.path.join(persisted_data, "goal_adaptation_feedback.json")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data["adaptation_history"] = [
        {
            "adaptation_id": "test_load_001",
            "performance_impact": {"performance_improvement": 15.0},
            "timestamp": "2026-10-14T00:00:00"
        }
    ]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    engine = ContextualAdaptationEngine(data_dir=persisted_data)

    assert len(engine.adaptation_history) == 1, "Debe cargarse el historial de adaptación"
    assert engine.adaptation_history[0]["adaptation_id"] == "test_load_001"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
