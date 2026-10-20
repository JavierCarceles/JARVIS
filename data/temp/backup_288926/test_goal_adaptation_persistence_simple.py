#!/usr/bin/env python3
"""
Test simple de persistencia de feedback de adaptación de Goal (2.8.8.9.2.3)

Verifica de forma directa el guardado y la carga del feedback y de los
resultados de aprendizaje, sobre la clase real `ContextualAdaptationEngine`
con persistencia aislada en un directorio temporal.
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptación con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def test_estructuras_base_inicializadas(engine):
    """El motor debe inicializar las estructuras de conocimiento requeridas."""
    for structure in ("goal_adaptation_feedback", "learning_results", "adaptation_strategies",
                      "goal_adaptation_strategies"):
        assert structure in engine.knowledge_base, (
            f"Debe inicializarse la estructura '{structure}'"
        )
    assert engine.knowledge_base["goal_adaptation_feedback"] == []
    assert engine.knowledge_base["learning_results"] == []
    assert engine.knowledge_base["goal_adaptation_strategies"] == {}
    # `adaptation_strategies` mantiene el contrato `contexto -> lista` del motor
    # (2.8.5/2.8.6): puede estar precreado, pero sin estrategias aprendidas.
    assert all(not rows for rows in engine.knowledge_base["adaptation_strategies"].values())


def test_guardar_feedback_crea_archivo(engine, tmp_path):
    """Guardar el feedback debe crear el archivo JSON con su contenido."""
    engine.knowledge_base["goal_adaptation_feedback"] = [
        {
            "adaptation_id": "test_001",
            "analysis": {"performance_improvement": 0.15},
            "timestamp": "2026-10-14T00:00:00",
            "status": "processed"
        }
    ]
    engine._save_goal_adaptation_feedback()

    feedback_file = tmp_path / "goal_adaptation_feedback.json"
    assert feedback_file.exists(), "Debe crearse el archivo de feedback"

    with open(feedback_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert len(data["goal_adaptation_feedback"]) == 1
    assert data["goal_adaptation_feedback"][0]["adaptation_id"] == "test_001"
    assert "last_updated" in data


def test_guardar_aprendizaje_crea_archivo(engine, tmp_path):
    """Guardar los resultados de aprendizaje debe crear su archivo JSON."""
    engine.knowledge_base["learning_results"] = [
        {
            "adaptation_id": "test_001",
            "learned_patterns": [
                {
                    "pattern_id": "pattern_001",
                    "pattern_type": "goal_adaptation_success",
                    "confidence": 0.85,
                    "context": {"goal_type": "navigate"},
                    "metrics": {"response_time": 1.5}
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
                "stability": 0.8
            },
            "timestamp": "2026-10-14T00:00:00",
            "status": "completed"
        }
    ]
    engine.knowledge_base["goal_adaptation_strategies"] = {
        "strategy_001": {
            "confidence": 0.85,
            "success_rate": 0.9,
            "last_updated": "2026-10-14T00:00:00"
        }
    }
    engine._save_goal_adaptation_learning_results()

    learning_file = tmp_path / "goal_adaptation_learning_results.json"
    assert learning_file.exists(), "Debe crearse el archivo de aprendizaje"

    with open(learning_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert len(data["learning_results"]) == 1
    assert data["adaptation_strategies"], "Las estrategias deben persistirse"


def test_cargar_datos_persistidos(engine, tmp_path):
    """Cargar debe recuperar feedback, aprendizaje y estrategias desde disco."""
    engine.knowledge_base["goal_adaptation_feedback"] = [
        {"adaptation_id": "test_001", "analysis": {"performance_improvement": 0.15},
         "timestamp": "2026-10-14T00:00:00", "status": "processed"}
    ]
    engine.knowledge_base["learning_results"] = [
        {"adaptation_id": "test_001", "learned_patterns": [], "updated_strategies": {},
         "convergence_metrics": {}, "timestamp": "2026-10-14T00:00:00", "status": "completed"}
    ]
    engine.knowledge_base["goal_adaptation_strategies"] = {
        "strategy_001": {"confidence": 0.85, "success_rate": 0.9,
                         "last_updated": "2026-10-14T00:00:00"}
    }
    engine._save_goal_adaptation_feedback()
    engine._save_goal_adaptation_learning_results()

    # Cargar en una instancia nueva (equivalente a reinicio)
    target = ContextualAdaptationEngine.__new__(ContextualAdaptationEngine)
    target.data_dir = str(tmp_path)
    target.knowledge_base = {"goal_adaptation_feedback": [], "learning_results": [],
                             "adaptation_strategies": {}}
    target.logger = engine.logger
    target.adaptation_history = []

    target._load_goal_adaptation_feedback()
    target._load_goal_adaptation_learning_results()

    assert len(target.knowledge_base["goal_adaptation_feedback"]) == 1
    assert len(target.knowledge_base["learning_results"]) == 1
    assert len(target.knowledge_base["goal_adaptation_strategies"]) == 1
    # La estrategia recuperada debe quedar disponible en el mapa por contexto.
    projected = [row for rows in target.knowledge_base["adaptation_strategies"].values()
                  if isinstance(rows, list) for row in rows]
    assert any(row.get("strategy_id") == "strategy_001" for row in projected)


def test_inicializacion_persistencia_estructuras(engine):
    """La inicialización debe garantizar todas las estructuras base."""
    engine.knowledge_base = {}
    engine._initialize_goal_adaptation_persistence()

    for structure in ("goal_adaptation_feedback", "learning_results", "adaptation_strategies",
                      "goal_adaptation_strategies"):
        assert structure in engine.knowledge_base, (
            f"La inicialización debe crear la estructura '{structure}'"
        )


def test_integridad_serializacion(engine, tmp_path):
    """Los datos cargados deben sobrevivir un round-trip de serialización."""
    engine.knowledge_base["goal_adaptation_feedback"] = [
        {"adaptation_id": "test_001", "analysis": {"performance_improvement": 0.15},
         "timestamp": "2026-10-14T00:00:00", "status": "processed"}
    ]
    engine.knowledge_base["learning_results"] = [
        {"adaptation_id": "test_001", "learned_patterns": [], "updated_strategies": {},
         "convergence_metrics": {}, "timestamp": "2026-10-14T00:00:00", "status": "completed"}
    ]
    engine.knowledge_base["goal_adaptation_strategies"] = {
        "strategy_001": {"confidence": 0.85, "success_rate": 0.9,
                         "last_updated": "2026-10-14T00:00:00"}
    }
    engine._save_goal_adaptation_feedback()
    engine._save_goal_adaptation_learning_results()

    with open(tmp_path / "goal_adaptation_feedback.json", 'r', encoding='utf-8') as f:
        feedback_data = json.load(f)
    with open(tmp_path / "goal_adaptation_learning_results.json", 'r', encoding='utf-8') as f:
        learning_data = json.load(f)

    payload = {
        "goal_adaptation_feedback": feedback_data["goal_adaptation_feedback"],
        "learning_results": learning_data["learning_results"],
        "adaptation_strategies": learning_data["adaptation_strategies"]
    }
    deserialized = json.loads(json.dumps(payload, indent=2, ensure_ascii=False))

    assert len(deserialized["goal_adaptation_feedback"]) > 0
    assert len(deserialized["learning_results"]) > 0
    assert len(deserialized["adaptation_strategies"]) > 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
