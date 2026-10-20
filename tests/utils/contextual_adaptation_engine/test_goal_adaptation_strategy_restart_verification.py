#!/usr/bin/env python3
"""
Verificacion de la estrategia recuperada tras el reinicio (2.8.8.9.3.5).

Esta hoja NO implementa persistencia (2.8.8.9.3.3) ni carga (2.8.8.9.3.4):
comprueba que la estrategia recuperada conserva los datos necesarios para
seguir siendo utilizable por el motor y por sus consumidores reales.

Alcance de la verificacion:

  1. La estrategia aprendida debe recuperar el CONJUNTO CANONICO completo de
     la forma A descrita en 2.8.8.9.3.1, no solo los DATOS CRITICOS:
     `strategy_id, strategy_type, strategy, context, pattern_id, metrics,
     confidence, success_rate, last_updated, description, applied_rules,
     failure_count`.
  2. Las estructuras anidadas (`context`, `metrics`, `applied_rules`) deben
     sobrevivir intactas: no basta con que la clave exista.
  3. Los valores deben ser identicos a los de la estrategia aprendida
     (ida y vuelta sin perdida).
  4. La estrategia recuperada debe seguir siendo CONSUMIBLE por los lectores
     reales del motor: `get_available_strategies()` y
     `generate_strategy_candidates()`.
  5. La recuperacion debe ser ESTABLE: un segundo reinicio no debe duplicar la
     entrada ni degradar sus datos.

El motor se instancia con `data_dir` temporal, por lo que el test no lee ni
escribe sobre `data/` de produccion.
"""

import os
import re
import sys
from datetime import datetime

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import (
    AdaptationLevel,
    ContextSnapshot,
    ContextType,
    ContextualAdaptationEngine,
)

# Contrato de DATOS CRITICOS, item 4 (roadmap 2.8.8.9.2.1).
CRITICAL_FIELDS = ("strategy_id", "confidence", "success_rate", "last_updated", "failure_count")

# Conjunto canonico de la estrategia aprendida (forma A de 2.8.8.9.3.1).
CANONICAL_FIELDS = (
    "strategy_id", "strategy_type", "strategy", "context", "pattern_id", "metrics",
    "confidence", "success_rate", "last_updated", "description", "applied_rules",
    "failure_count",
)

# Identificador sintetizado por `_flatten_strategy_map()` para una entrada sin
# `strategy_id`: `strategy_<contexto>_<posicion>`. El identificador real de una
# estrategia aprendida es `strategy_<timestamp>_<posicion>`, por lo que el
# componente de contexto lo distingue de forma inequivoca.
_SYNTHESIZED_ID = re.compile(
    r"^strategy_(" + "|".join(context.value for context in ContextType) + r")_\d+$"
)


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptacion con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def _feedback_data(adaptation_id="verify_restart_001"):
    """Datos de feedback de adaptacion de Goal de ejemplo."""
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": "goal_original_001",
        "adapted_goal_id": "goal_adapted_001",
        "adaptation_context": {
            "goal_type": "navigation",
            "context_type": ContextType.PRODUCTION.value,
            "system_resources": {"cpu": 0.5, "memory": 0.3},
            "expected_metrics": {"response_time": 2.0, "accuracy": 0.95},
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {"response_time": 1.2, "accuracy": 0.97},
        },
        "verification_result": {"verified": True, "impact_score": 0.8},
    }


def _snapshot(context_type=ContextType.TESTING, snapshot_id="snapshot_verify_001"):
    """Snapshot de contexto minimo para registrar resultados de adaptacion."""
    return ContextSnapshot(
        snapshot_id=snapshot_id,
        timestamp=datetime.now(),
        context_type=context_type,
        contextual_factors={},
        system_metrics={},
        performance_metrics={},
        user_interaction_patterns={},
        environmental_conditions={},
        confidence_score=0.8,
        adaptation_level=AdaptationLevel.MINIMAL,
    )


def _learn_strategy(engine):
    """Ejecutar el bucle de aprendizaje y devolver la estrategia aprendida."""
    feedback_result = engine._capture_goal_adaptation_feedback(_feedback_data())
    assert feedback_result["success"] is True, feedback_result.get("error_message")
    learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
    assert learning_result["success"] is True, learning_result.get("error_message")
    learned = [
        row
        for rows in learning_result["adaptation_strategies"].values() if isinstance(rows, list)
        for row in rows
        if isinstance(row, dict) and all(field in row for field in CRITICAL_FIELDS)
    ]
    assert learned, "El bucle de aprendizaje debe generar al menos una estrategia aprendida"
    return learned[0]


def _entries_by_context(engine):
    """Devolver las entradas de `adaptation_strategies` aplanadas con su contexto."""
    result = []
    for context, rows in engine.knowledge_base["adaptation_strategies"].items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row:
                result.append((context, row))
    return result


def _recovered(restarted, strategy_id):
    """Buscar la entrada recuperada con el `strategy_id` dado."""
    return next(
        (row for _, row in _entries_by_context(restarted) if row.get("strategy_id") == strategy_id),
        None,
    )


def test_la_estrategia_recuperada_conserva_el_conjunto_canonico_completo(engine, tmp_path):
    """Tras el reinicio deben sobrevivir todos los campos canonicos de la estrategia.

    Los DATOS CRITICOS (item 4) son un subconjunto; si el motor solo conservara
    esos cinco campos, la estrategia recuperada perderia el contexto con el que
    se aprendio, su patron de origen y su descripcion.
    """
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered(restarted, strategy_id)
    assert recovered is not None, "La estrategia aprendida debe recuperarse tras el reinicio"
    missing = [field for field in CANONICAL_FIELDS if field not in recovered]
    assert not missing, f"Faltan campos canonicos en la estrategia recuperada: {missing}"


def test_la_estrategia_recuperada_conserva_las_estructuras_anidadas(engine, tmp_path):
    """Las estructuras anidadas deben sobrevivir intactas, no solo existir."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered(restarted, strategy_id)
    assert recovered is not None, "La estrategia aprendida debe recuperarse tras el reinicio"

    context_info = recovered.get("context")
    assert isinstance(context_info, dict), "El contexto recuperado debe seguir siendo un diccionario"
    assert context_info == learned["context"], (
        f"El contexto recuperado difiere del original: {context_info!r} != {learned['context']!r}"
    )
    assert context_info.get("context_type") == ContextType.PRODUCTION.value
    assert context_info.get("goal_type") == "navigation"

    metrics = recovered.get("metrics")
    assert isinstance(metrics, dict), "Las metricas recuperadas deben seguir siendo un diccionario"
    assert metrics == learned["metrics"], (
        f"Las metricas recuperadas difieren del original: {metrics!r} != {learned['metrics']!r}"
    )

    applied_rules = recovered.get("applied_rules")
    assert isinstance(applied_rules, list), "Las reglas aplicadas deben seguir siendo una lista"
    assert applied_rules == learned["applied_rules"]


def test_la_estrategia_recuperada_conserva_los_valores_sin_perdida(engine, tmp_path):
    """La ida y vuelta debe preservar el valor de cada campo canonico."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered(restarted, strategy_id)
    assert recovered is not None, "La estrategia aprendida debe recuperarse tras el reinicio"
    for field in CANONICAL_FIELDS:
        assert recovered[field] == learned[field], (
            f"El campo '{field}' cambio al reiniciar: "
            f"{recovered[field]!r} != {learned[field]!r}"
        )


def test_la_estrategia_recuperada_sigue_disponible_para_los_consumidores(engine, tmp_path):
    """La estrategia recuperada debe seguir siendo legible por los consumidores reales."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    available = restarted.get_available_strategies(ContextType.PRODUCTION)
    offered = next((row for row in available if row.get("strategy_id") == strategy_id), None)
    assert offered is not None, (
        "La estrategia recuperada debe aparecer en `get_available_strategies()` "
        f"del contexto {ContextType.PRODUCTION.value}; se obtuvieron {len(available)}"
    )
    assert offered.get("confidence") == learned["confidence"]
    assert offered.get("name") == learned["strategy"]
    assert offered.get("source_context") == ContextType.PRODUCTION.value
    # El consumidor recibe la entrada completa mediante `knowledge_data`.
    knowledge_data = offered.get("knowledge_data", {})
    assert isinstance(knowledge_data, dict)
    payload = knowledge_data.get("adaptation_strategies")
    assert isinstance(payload, list) and payload, (
        "El consumidor debe recibir la estrategia completa a traves de `knowledge_data`"
    )
    assert payload[0].get("strategy_id") == strategy_id
    assert payload[0].get("context") == learned["context"]

    candidates = restarted.generate_strategy_candidates(ContextType.PRODUCTION)
    assert any(strategy_id in str(candidate.get("strategy_id", "")) for candidate in candidates), (
        "La estrategia recuperada debe ofrecerse como candidata"
    )


def test_la_estrategia_recuperada_es_estable_tras_un_segundo_reinicio(engine, tmp_path):
    """Un segundo reinicio no debe duplicar la entrada ni degradar sus datos."""
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]

    first_restart = ContextualAdaptationEngine(data_dir=str(tmp_path))
    second_restart = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = [
        (context, row)
        for context, row in _entries_by_context(second_restart)
        if row.get("strategy_id") == strategy_id
    ]
    assert len(recovered) == 1, (
        f"La estrategia debe seguir presente una sola vez tras el segundo reinicio, "
        f"se encontraron {len(recovered)}"
    )
    context, row = recovered[0]
    assert context == ContextType.PRODUCTION.value
    for field in CANONICAL_FIELDS:
        assert row[field] == learned[field], (
            f"El campo '{field}' se degrado tras el segundo reinicio: "
            f"{row[field]!r} != {learned[field]!r}"
        )


def test_el_reconocimiento_de_un_registro_sin_strategy_id_no_contamina_la_estrategia(engine, tmp_path):
    """Un registro de adaptacion sin `strategy_id` no debe degradar la estrategia aprendida.

    `_record_adaptation_result()` escribe entradas sin `strategy_id` en el mismo
    mapa. La brecha detectada en 2.8.8.9.3.1 era que, al reiniciar, ese registro
    reaparecia duplicado en otro contexto con un identificador sintetizado
    (`strategy_<contexto>_<posicion>`). Aqui se verifica que la brecha esta
    cerrada: el registro no se persiste, no reaparece y no altera la estrategia
    aprendida.
    """
    learned = _learn_strategy(engine)
    strategy_id = learned["strategy_id"]
    engine._record_adaptation_result("adapt_result_verify_001", _snapshot(ContextType.TESTING), [], 0.8)

    # El registro sin `strategy_id` existe en memoria, pero no cumple el contrato
    # de DATOS CRITICOS, por lo que no debe llegar al indice plano persistido.
    live = _entries_by_context(engine)
    assert any(
        row.get("adaptation_id") == "adapt_result_verify_001" for _, row in live
    ), "El registro de resultado de adaptacion debe existir en memoria"

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = _recovered(restarted, strategy_id)
    assert recovered is not None, "La estrategia aprendida debe recuperarse tras el reinicio"
    assert recovered == learned, (
        "La recuperacion no debe alterar los datos de la estrategia aprendida"
    )

    recovered_entries = _entries_by_context(restarted)
    duplicated = [
        (context, row)
        for context, row in recovered_entries
        if row.get("adaptation_id") == "adapt_result_verify_001"
    ]
    assert not duplicated, (
        "El registro sin `strategy_id` no debe reaparecer tras el reinicio; "
        f"se reencontro en {duplicated}"
    )
    synthesized = [
        (context, row)
        for context, row in recovered_entries
        if _SYNTHESIZED_ID.match(str(row.get("strategy_id", "")))
    ]
    assert not synthesized, (
        "No debe aparecer ninguna entrada con identificador sintetizado; "
        f"se reencontraron {synthesized}"
    )
    for context, row in recovered_entries:
        assert row.get("strategy_id"), (
            f"Toda entrada recuperada debe tener `strategy_id`; en '{context}' hay {row!r}"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
