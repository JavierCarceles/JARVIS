#!/usr/bin/env python3
"""
Test de persistencia de estrategias aprendidas de Goal (2.8.8.9.2.6).

Verifica que una estrategia aprendida sobrevive al reinicio del motor y que
vuelve a estar disponible para el resto del sistema.

Contexto del fallo corregido: la carga anterior insertaba el índice plano
persistido (`strategy_id -> entrada`) dentro del mapa `adaptation_strategies`,
que en el motor sigue el contrato `contexto -> lista` (2.8.5/2.8.6). El
resultado era un mapa corrupto y `get_available_strategies()` devolvía una
lista vacía: la estrategia persistida no se recuperaba.

El motor se instancia con `data_dir` temporal, por lo que el test no lee ni
escribe sobre `data/` de producción.
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptación con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def _feedback_data(adaptation_id="test_strategy_001"):
    """Datos de feedback de adaptación de Goal de ejemplo."""
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": "goal_original_001",
        "adapted_goal_id": "goal_adapted_001",
        "adaptation_context": {
            "goal_type": "navigation",
            "context_type": ContextType.PRODUCTION.value,
            "system_resources": {"cpu": 0.5, "memory": 0.3},
            "expected_metrics": {"response_time": 2.0, "accuracy": 0.95}
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {"response_time": 1.2, "accuracy": 0.97}
        },
        "verification_result": {"verified": True, "impact_score": 0.8}
    }


def _learn_strategy(engine):
    """Ejecutar el bucle de aprendizaje y devolver la estrategia generada."""
    feedback_result = engine._capture_goal_adaptation_feedback(_feedback_data())
    assert feedback_result["success"] is True, feedback_result.get("error_message")
    learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
    assert learning_result["success"] is True, learning_result.get("error_message")
    strategies = learning_result["adaptation_strategies"]
    learned = [row for rows in strategies.values() if isinstance(rows, list) for row in rows]
    assert learned, "El bucle de aprendizaje debe generar al menos una estrategia"
    return learned[0]


def test_mapa_por_contexto_conserva_el_contrato_del_motor(engine):
    """`adaptation_strategies` debe seguir el contrato `contexto -> lista`."""
    _learn_strategy(engine)

    strategies = engine.knowledge_base["adaptation_strategies"]
    assert isinstance(strategies, dict)
    for context, rows in strategies.items():
        assert isinstance(rows, list), (
            f"El contexto '{context}' debe mapear a una lista de estrategias"
        )


def test_estrategia_aprendida_sobrevive_al_reinicio(engine, tmp_path):
    """La estrategia aprendida debe recuperarse tras crear un motor nuevo."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = [
        row
        for rows in restarted.knowledge_base["adaptation_strategies"].values()
        if isinstance(rows, list)
        for row in rows
    ]
    assert any(row.get("strategy_id") == strategy_id for row in recovered), (
        "La estrategia aprendida debe recuperarse tras el reinicio"
    )


def test_estrategia_recuperada_conserva_su_contexto(engine, tmp_path):
    """La estrategia recuperada debe quedar en el contexto con el que se aprendió."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    rows = restarted.knowledge_base["adaptation_strategies"].get(ContextType.PRODUCTION.value, [])
    assert any(row.get("strategy_id") == strategy_id for row in rows), (
        "La estrategia debe quedar disponible en su contexto de origen"
    )


def test_estrategia_recuperada_es_utilizable(engine, tmp_path):
    """La estrategia recuperada debe ofrecerse a los consumidores del motor."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    available = restarted.get_available_strategies(ContextType.PRODUCTION)
    assert any(row.get("strategy_id") == strategy_id for row in available), (
        "La estrategia recuperada debe aparecer en `get_available_strategies`"
    )
    candidates = restarted.generate_strategy_candidates(ContextType.PRODUCTION, max_candidates=5,
                                                        min_confidence=0.5)
    assert any(strategy_id in str(candidate.get("strategy_id", "")) for candidate in candidates), (
        "La estrategia recuperada debe ofrecerse como candidata"
    )


def test_archivo_persistido_usa_indice_plano(engine, tmp_path):
    """El archivo de aprendizaje persiste el índice plano `strategy_id -> entrada`."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    path = os.path.join(str(tmp_path), "goal_adaptation_learning_results.json")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    assert "adaptation_strategies" in payload
    assert strategy_id in payload["adaptation_strategies"], (
        "La estrategia debe persistirse indexada por `strategy_id`"
    )
    entry = payload["adaptation_strategies"][strategy_id]
    for key in ("confidence", "success_rate", "last_updated", "failure_count"):
        assert key in entry, f"Falta la clave '{key}' en la estrategia persistida"


def test_carga_no_ensucia_el_mapa_por_contexto(engine, tmp_path):
    """Cargar no debe mezclar el índice plano en el mapa `contexto -> lista`."""
    _learn_strategy(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    strategies = restarted.knowledge_base["adaptation_strategies"]
    for context, rows in strategies.items():
        assert isinstance(rows, list), (
            f"La carga no debe dejar entradas planas bajo la clave '{context}'"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
