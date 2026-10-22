#!/usr/bin/env python3
"""
Test de persistencia de feedback de adaptación de Goal (2.8.8.9.2.2)

Verifica que el feedback capturado por el motor:
  1. Se registra en la base de conocimiento.
  2. Se persiste en disco (JSON).
  3. Incluye el historial de adaptación (dato crítico de 2.8.8.9.2.1).
  4. Respeta los límites de persistencia definidos.

Nota: este test usa la clase real `ContextualAdaptationEngine` con un
`data_dir` temporal, de modo que nunca escribe sobre los datos de producción
y nunca depende de imports a nivel de módulo inexistentes.
"""

import json
import os
import sys
from datetime import datetime

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine


def _build_feedback_data(adaptation_id="test_persistence_001"):
    """Construir datos de feedback de adaptación de Goal de ejemplo."""
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": "goal_original_persistence",
        "adapted_goal_id": "goal_adapted_persistence",
        "adaptation_context": {
            "goal_type": "navigate",
            "context_type": "development",
            "expected_metrics": {
                "response_time": 2.0,
                "accuracy": 0.95
            }
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {
                "response_time": 1.5,
                "accuracy": 0.98
            }
        },
        "verification_result": {
            "verified": True,
            "impact_score": 0.8
        }
    }


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptación con persistencia aislada en un directorio temporal."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def test_capture_feedback_registra_en_knowledge_base(engine):
    """El feedback capturado debe registrarse en el knowledge_base."""
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())

    assert feedback_result["success"] is True, (
        f"La captura de feedback falló: {feedback_result.get('error_message')}"
    )

    feedback_records = engine.knowledge_base["goal_adaptation_feedback"]
    assert len(feedback_records) == 1, "El feedback debe registrarse en el knowledge_base"

    record = feedback_records[-1]
    assert record["adaptation_id"] == "test_persistence_001"
    assert record["status"] == "processed"
    assert "analysis" in record, "El registro debe contener el análisis de mejora"
    assert record["timestamp"], "El registro debe tener timestamp"


def test_capture_feedback_devuelve_adaptation_id(engine):
    """El resultado de la captura debe incluir adaptation_id.

    El bucle de aprendizaje lo necesita para correlacionar los resultados;
    sin él, el registro de aprendizaje falla.
    """
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())

    assert feedback_result["success"] is True
    assert feedback_result.get("adaptation_id") == "test_persistence_001"


def test_performance_improvement_se_calcula(engine):
    """La mejora de rendimiento debe calcularse con las métricas de referencia.

    Referencia: response_time 2.0 -> 1.5 (25% mejora)
                 accuracy    0.95 -> 0.98 (3.157...% mejora)
    """
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())
    analysis = feedback_result["improvement_analysis"]

    assert analysis["response_time_improvement"] == pytest.approx(25.0)
    assert analysis["accuracy_improvement"] == pytest.approx(3.157894, rel=1e-5)
    assert analysis["performance_improvement"] == pytest.approx(14.078947, rel=1e-5)
    assert analysis["performance_improvement"] > 0, "Una adaptación mejorada debe reportar mejora positiva"


def test_performance_improvement_detecta_degradacion(engine):
    """Una adaptación peor que la referencia debe reportar mejora negativa."""
    feedback_data = _build_feedback_data("test_degradation_001")
    feedback_data["adaptation_context"]["expected_metrics"] = {
        "response_time": 1.0,
        "accuracy": 0.98
    }
    feedback_data["execution_result"]["performance_metrics"] = {
        "response_time": 2.5,
        "accuracy": 0.92
    }

    feedback_result = engine._capture_goal_adaptation_feedback(feedback_data)
    analysis = feedback_result["improvement_analysis"]

    assert analysis["performance_improvement"] < 0, "Una adaptación degradada debe reportar mejora negativa"


def test_adaptation_history_se_registra_y_persiste(engine, tmp_path):
    """El historial de adaptación debe poblarse y persistirse (2.8.8.9.2.1)."""
    engine._capture_goal_adaptation_feedback(_build_feedback_data())

    assert len(engine.adaptation_history) == 1, "El historial de adaptación debe registrar la entrada"

    entry = engine.adaptation_history[-1]
    assert entry["adaptation_id"] == "test_persistence_001"
    assert "performance_impact" in entry
    assert entry["timestamp"], "La entrada del historial debe tener timestamp"

    feedback_file = tmp_path / "goal_adaptation_feedback.json"
    assert feedback_file.exists(), "El archivo de feedback debe existir en disco"

    with open(feedback_file, 'r', encoding='utf-8') as f:
        persisted = json.load(f)

    assert "adaptation_history" in persisted, "El historial de adaptación debe persistirse"
    assert len(persisted["adaptation_history"]) == 1
    assert persisted["adaptation_history"][0]["adaptation_id"] == "test_persistence_001"


def test_feedback_persiste_en_disco(engine, tmp_path):
    """El feedback capturado debe quedar persistido en el archivo JSON."""
    engine._capture_goal_adaptation_feedback(_build_feedback_data())

    feedback_file = tmp_path / "goal_adaptation_feedback.json"
    assert feedback_file.exists(), "El archivo de feedback debe crearse al capturar feedback"

    with open(feedback_file, 'r', encoding='utf-8') as f:
        persisted = json.load(f)

    assert len(persisted["goal_adaptation_feedback"]) == 1
    assert persisted["goal_adaptation_feedback"][0]["adaptation_id"] == "test_persistence_001"
    assert "last_updated" in persisted


def test_limite_persistencia_feedback(engine, monkeypatch):
    """El historial de feedback debe respetar el límite de 1000 registros."""
    # Se aísla el I/O a disco: el objetivo es validar la lógica de recorte,
    # no el rendimiento de escritura.
    monkeypatch.setattr(engine, "_save_goal_adaptation_feedback", lambda: None)
    monkeypatch.setattr(engine, "_save_goal_adaptation_learning_results", lambda: None)

    for index in range(1005):
        engine._capture_goal_adaptation_feedback(
            _build_feedback_data(f"test_limit_{index}")
        )

    assert len(engine.knowledge_base["goal_adaptation_feedback"]) == 1000, (
        "El feedback no debe superar el límite de 1000 registros"
    )
    assert len(engine.adaptation_history) == 1000, (
        "El historial de adaptación no debe superar el límite de 1000 registros"
    )

    # El registro más reciente debe seguir presente tras el recorte
    assert engine.knowledge_base["goal_adaptation_feedback"][-1]["adaptation_id"] == "test_limit_1004"


def test_persistencia_serializa_a_json(engine, tmp_path):
    """Los datos persistidos deben ser serializables y deserializables."""
    engine._capture_goal_adaptation_feedback(_build_feedback_data())

    feedback_file = tmp_path / "goal_adaptation_feedback.json"
    with open(feedback_file, 'r', encoding='utf-8') as f:
        persisted = json.load(f)

    required_keys = {
        "goal_adaptation_feedback",
        "adaptation_history",
        "last_updated"
    }
    assert required_keys.issubset(persisted.keys()), (
        f"Faltan claves en la persistencia: {required_keys - set(persisted.keys())}"
    )

    # Round-trip de serialización
    round_trip = json.loads(json.dumps(persisted, ensure_ascii=False))
    assert round_trip["goal_adaptation_feedback"] == persisted["goal_adaptation_feedback"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
