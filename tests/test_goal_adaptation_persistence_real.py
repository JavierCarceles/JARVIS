#!/usr/bin/env python3
"""
Test real de persistencia de feedback de adaptación de Goal (2.8.8.9.2.3)

Verifica el flujo completo sobre la clase real `ContextualAdaptationEngine`:
  1. Captura de feedback con datos de referencia.
  2. Bucle de aprendizaje y registro de resultados.
  3. Guardado en disco de feedback y resultados de aprendizaje.
  4. Carga posterior de los datos persistidos.

La persistencia se aísla en un directorio temporal (`data_dir`), por lo que el
test no escribe sobre `data/` de producción.
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine


def _build_feedback_data(adaptation_id="test_real_001"):
    """Datos de feedback de adaptación de Goal de ejemplo."""
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": "goal_original_real",
        "adapted_goal_id": "goal_adapted_real",
        "adaptation_context": {
            "goal_type": "navigation",
            "context_type": "browser",
            "system_resources": {"cpu": 0.5, "memory": 0.3},
            "expected_metrics": {"response_time": 2.0, "accuracy": 0.95}
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {"response_time": 1.2, "accuracy": 0.97}
        },
        "verification_result": {"verified": True, "impact_score": 0.8}
    }


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptación con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def test_captura_y_bucle_de_aprendizaje(engine):
    """La captura y el bucle de aprendizaje deben completarse con éxito."""
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())
    assert feedback_result["success"] is True, (
        f"La captura falló: {feedback_result.get('error_message')}"
    )

    learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
    assert learning_result["success"] is True, (
        f"El bucle de aprendizaje falló: {learning_result.get('error_message')}"
    )
    assert len(learning_result["learned_patterns"]) > 0, "Debe aprenderse al menos un patrón"
    assert learning_result["adaptation_strategies"], "Debe generarse al menos una estrategia"
    assert learning_result["convergence_metrics"]["convergence_status"] != "failed"


def test_bucle_registra_resultados_con_adaptation_id(engine):
    """Los resultados de aprendizaje deben correlacionarse con el adaptation_id.

    Este es el fallo que rompía la persistencia: el bucle pedía
    `feedback_result["adaptation_id"]` y el capture no lo devolvía.
    """
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())
    learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)

    assert learning_result["success"] is True, (
        f"El bucle de aprendizaje falló: {learning_result.get('error_message')}"
    )

    learning_records = engine.knowledge_base["learning_results"]
    assert len(learning_records) == 1, "El bucle de aprendizaje debe registrar un resultado"

    record = learning_records[-1]
    assert record["adaptation_id"] == "test_real_001", (
        "El resultado de aprendizaje debe conservar el adaptation_id del feedback"
    )
    assert record["status"] == "completed"
    assert record["learned_patterns"], "Debe persistir los patrones aprendidos"
    assert "convergence_metrics" in record


def test_archivos_persistidos_se_crean(engine, tmp_path):
    """El guardado debe crear los dos archivos de persistencia."""
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())
    engine._execute_goal_adaptation_learning_loop(feedback_result)

    feedback_file = tmp_path / "goal_adaptation_feedback.json"
    learning_file = tmp_path / "goal_adaptation_learning_results.json"

    assert feedback_file.exists(), "Debe crearse el archivo de feedback"
    assert learning_file.exists(), "Debe crearse el archivo de resultados de aprendizaje"

    with open(feedback_file, 'r', encoding='utf-8') as f:
        feedback_data = json.load(f)
    with open(learning_file, 'r', encoding='utf-8') as f:
        learning_data = json.load(f)

    assert len(feedback_data["goal_adaptation_feedback"]) == 1
    assert len(learning_data["learning_results"]) == 1
    assert learning_data["adaptation_strategies"], "Las estrategias deben persistirse"


def test_carga_recupera_datos_persistidos(engine, tmp_path):
    """Una nueva instancia debe recuperar el feedback y el aprendizaje persistidos."""
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())
    engine._execute_goal_adaptation_learning_loop(feedback_result)

    # Nueva instancia = reinicio simulado
    reloaded = ContextualAdaptationEngine(data_dir=str(tmp_path))

    assert len(reloaded.knowledge_base["goal_adaptation_feedback"]) == 1
    assert len(reloaded.knowledge_base["learning_results"]) == 1
    assert reloaded.knowledge_base["adaptation_strategies"], "Deben cargarse las estrategias"
    assert len(reloaded.adaptation_history) == 1, "Debe cargarse el historial de adaptación"

    reloaded_feedback = reloaded.knowledge_base["goal_adaptation_feedback"][0]
    assert reloaded_feedback["adaptation_id"] == "test_real_001"
    assert reloaded_feedback["analysis"]["performance_improvement"] > 0


def test_integridad_datos_cargados(engine, tmp_path):
    """Los datos cargados deben mantener su estructura intacta."""
    feedback_result = engine._capture_goal_adaptation_feedback(_build_feedback_data())
    engine._execute_goal_adaptation_learning_loop(feedback_result)

    reloaded = ContextualAdaptationEngine(data_dir=str(tmp_path))

    feedback_record = reloaded.knowledge_base["goal_adaptation_feedback"][0]
    for key in ("adaptation_id", "analysis", "timestamp", "status"):
        assert key in feedback_record, f"Falta la clave '{key}' en el feedback cargado"

    learning_record = reloaded.knowledge_base["learning_results"][0]
    for key in ("adaptation_id", "learned_patterns", "updated_strategies", "convergence_metrics"):
        assert key in learning_record, f"Falta la clave '{key}' en el aprendizaje cargado"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
