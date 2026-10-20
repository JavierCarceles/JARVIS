#!/usr/bin/env python3
"""
Test de persistencia de estrategias aprendidas de Goal (2.8.8.9.3.2).

Fija el contrato que las hojas 2.8.8.9.3.3 (guardado), 2.8.8.9.3.4 (carga),
2.8.8.9.3.5 (verificación tras reinicio) y 2.8.8.9.3.6 (corrección) deben
cumplir. Esta hoja (2.8.8.9.3.2) crea únicamente el test; la implementación
corresponde a las hojas siguientes.

Fuentes del contrato:
- Roadmap 2.8.8.9.2.1, DATOS CRÍTICOS item 4:
  "ESTRATEGIAS APRENDIDAS (`adaptation_strategies`): strategy_id, confidence,
  success_rate, last_updated, failure_count".
- Roadmap 2.8.8.9.3.3/2.8.8.9.3.4: "Persistir/Recuperar únicamente estrategias
  aprendidas".
- Inspección real de 2.8.8.9.3.1 sobre `src/utils/contextual_adaptation_engine.py`.

Realidad del contenedor verificada en 2.8.8.9.3.1:
`knowledge_base["adaptation_strategies"]` sigue el contrato `contexto -> lista`
sobre los 9 contextos de `ContextType`, pero en esa lista conviven tres formas
de entrada distintas:

  A) Estrategia aprendida (canónica) — `_update_adaptive_strategies()`:
     `strategy_id, strategy_type, strategy, context{goal_type, context_type,
     expected_metrics}, pattern_id, metrics, confidence, success_rate,
     last_updated, description, applied_rules, failure_count`.
     Es la única que cumple el contrato de DATOS CRÍTICOS.
  B) Registro de aplicación — `apply_strategy()`:
     `strategy, confidence, strategy_id, description, knowledge_data`.
  C) Registro de resultado de adaptación — `_record_adaptation_result()`:
     `adaptation_id, timestamp, applied_rules, confidence` (sin `strategy_id`).

Brechas reales que este test fija (verificadas en 2.8.8.9.3.1):

  1. DUPLICACIÓN: la forma C no tiene `strategy_id`, por lo que
     `_known_strategy_ids()` no la reconoce. Al cargar, `_merge_strategies_by_context()`
     la restaura en su contexto de origen ("testing") y además
     `_project_strategies_by_context()` la re-proyecta en "idle" con un
     `strategy_id` sintetizado (`strategy_testing_0`): el mismo registro queda
     visible en dos contextos a la vez.
  2. IDENTIFICADORES SINTETIZADOS: la forma C entra en el índice plano con la
     clave `strategy_<contexto>_<posición>`, que no corresponde a ninguna
     estrategia real.
  3. PERSISTENCIA DE REGISTROS QUE NO SON ESTRATEGIAS APRENDIDAS: las formas B
     y C se aplanan al índice `strategy_id -> entrada` aunque no cumplen el
     contrato de DATOS CRÍTICOS, y la forma B pierde el contexto con el que se
     aplicó.

El motor se instancia con `data_dir` temporal, por lo que el test no lee ni
escribe sobre `data/` de producción.
"""

import json
import os
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

# Contrato de DATOS CRÍTICOS, item 4 (roadmap 2.8.8.9.2.1).
CRITICAL_FIELDS = ("strategy_id", "confidence", "success_rate", "last_updated", "failure_count")


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


def _snapshot(context_type=ContextType.TESTING, snapshot_id="snapshot_test_001"):
    """Snapshot de contexto mínimo para registrar resultados de adaptación."""
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
    """Ejecutar el bucle de aprendizaje y devolver las estrategias aprendidas.

    El mapa `adaptation_strategies` mezcla tres formas de entrada (2.8.8.9.3.1),
    así que se seleccionan solo las que cumplen el contrato de DATOS CRÍTICOS.
    """
    feedback_result = engine._capture_goal_adaptation_feedback(_feedback_data())
    assert feedback_result["success"] is True, feedback_result.get("error_message")
    learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
    assert learning_result["success"] is True, learning_result.get("error_message")
    strategies = learning_result["adaptation_strategies"]
    learned = [
        row
        for rows in strategies.values() if isinstance(rows, list)
        for row in rows
        if isinstance(row, dict) and all(field in row for field in CRITICAL_FIELDS)
    ]
    assert learned, "El bucle de aprendizaje debe generar al menos una estrategia aprendida"
    return learned


def _record_application_and_result(engine):
    """Generar en el motor las formas B (aplicación) y C (resultado)."""
    engine.apply_strategy(
        {
            "strategy_id": "cand_applied_001",
            "name": "estrategia_aplicada",
            "confidence": 0.85,
            "description": "estrategia aplicada en prueba",
            "knowledge_data": {"adaptation_strategies": [{"x": 1}]},
        },
        ContextType.DEVELOPMENT,
    )
    engine._record_adaptation_result(
        "adapt_result_001", _snapshot(ContextType.TESTING), [], 0.8)


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


def _persisted_flat_index(tmp_path):
    """Leer el índice plano persistido de estrategias."""
    path = os.path.join(str(tmp_path), "goal_adaptation_learning_results.json")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("adaptation_strategies", {})


def test_la_estrategia_aprendida_sobrevive_una_sola_vez_al_reinicio(engine, tmp_path):
    """La estrategia aprendida debe recuperarse una sola vez tras el reinicio."""
    learned = _learn_strategy(engine)[0]
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = [row for _, row in _entries_by_context(restarted)
                 if row.get("strategy_id") == strategy_id]
    assert len(recovered) == 1, (
        f"La estrategia aprendida debe recuperarse exactamente una vez, "
        f"se recuperaron {len(recovered)}"
    )


def test_la_estrategia_aprendida_conserva_su_contexto_tras_el_reinicio(engine, tmp_path):
    """La estrategia recuperada debe quedar en el contexto con el que se aprendió."""
    learned = _learn_strategy(engine)[0]
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    rows = restarted.knowledge_base["adaptation_strategies"].get(ContextType.PRODUCTION.value, [])
    assert any(row.get("strategy_id") == strategy_id for row in rows), (
        "La estrategia debe quedar disponible en su contexto de origen"
    )


def test_la_estrategia_aprendida_conserva_sus_datos_criticos(engine, tmp_path):
    """La estrategia recuperada debe conservar los DATOS CRÍTICOS intactos."""
    learned = _learn_strategy(engine)[0]
    strategy_id = learned["strategy_id"]

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = next(
        (row for _, row in _entries_by_context(restarted)
         if row.get("strategy_id") == strategy_id),
        None,
    )
    assert recovered is not None, "La estrategia aprendida debe recuperarse tras el reinicio"
    for field in CRITICAL_FIELDS:
        assert field in recovered, f"Falta el dato crítico '{field}' en la estrategia recuperada"
    assert recovered["confidence"] == learned["confidence"]
    assert recovered["success_rate"] == learned["success_rate"]
    assert recovered["failure_count"] == learned["failure_count"]
    assert recovered["last_updated"] == learned["last_updated"]


def test_la_estrategia_persistida_conserva_su_contexto(engine, tmp_path):
    """La estrategia aprendida persistida debe llevar el contexto con el que se aprendió.

    Sin `context.context_type` en la entrada persistida, la carga no puede
    restaurarla en su bucket original y acaba re-proyectada en "idle".
    """
    learned = _learn_strategy(engine)[0]

    flat = _persisted_flat_index(tmp_path)
    entry = flat.get(learned["strategy_id"])
    assert entry is not None, "La estrategia aprendida debe persistirse indexada por `strategy_id`"
    context_info = entry.get("context")
    assert isinstance(context_info, dict), (
        "La estrategia persistida debe conservar su contexto"
    )
    assert context_info.get("context_type") == ContextType.PRODUCTION.value, (
        "La estrategia persistida debe conservar el contexto con el que se aprendió"
    )


def test_el_indice_persistido_contiene_exactamente_las_estrategias_aprendidas(engine, tmp_path):
    """El índice persistido debe contener exactamente las estrategias aprendidas.

    Las formas B (registro de aplicación) y C (resultado de adaptación) no
    cumplen el contrato de DATOS CRÍTICOS, por lo que no deben persistirse
    como estrategias aprendidas. La forma C, además, se aplana con la clave
    `strategy_<contexto>_<posición>`, que no corresponde a ninguna estrategia
    y es la causa directa de la duplicación al cargar.
    """
    _record_application_and_result(engine)
    learned = _learn_strategy(engine)

    flat = _persisted_flat_index(tmp_path)
    assert flat, "Las estrategias aprendidas deben persistirse"
    persisted_ids = set(flat)
    learned_ids = {row["strategy_id"] for row in learned}
    assert persisted_ids == learned_ids, (
        f"El índice persistido debe contener solo las estrategias aprendidas "
        f"({sorted(learned_ids)}); se persistieron además {sorted(persisted_ids - learned_ids)}"
    )
    for key, entry in flat.items():
        for field in CRITICAL_FIELDS:
            assert field in entry, (
                f"La entrada persistida '{key}' no es una estrategia aprendida: "
                f"falta el dato crítico '{field}'"
            )


def test_ningun_registro_aparece_duplicado_tras_el_reinicio(engine, tmp_path):
    """Tras el reinicio ninguna entrada debe aparecer en más de un contexto.

    Sin `strategy_id`, la forma C no la reconoce `_known_strategy_ids()` y se
    re-proyecta en "idle" con un identificador sintetizado, dejando el mismo
    `adaptation_id` visible en dos contextos a la vez.
    """
    _record_application_and_result(engine)
    _learn_strategy(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    by_strategy_id = {}
    by_adaptation_id = {}
    for context, row in _entries_by_context(restarted):
        strategy_id = row.get("strategy_id")
        if strategy_id:
            by_strategy_id.setdefault(strategy_id, []).append(context)
        adaptation_id = row.get("adaptation_id")
        if adaptation_id:
            by_adaptation_id.setdefault(adaptation_id, []).append(context)

    duplicated = {sid: ctxs for sid, ctxs in by_strategy_id.items() if len(ctxs) > 1}
    assert not duplicated, f"Estrategias duplicadas tras el reinicio: {duplicated}"

    duplicated = {aid: ctxs for aid, ctxs in by_adaptation_id.items() if len(ctxs) > 1}
    assert not duplicated, (
        f"Registros de adaptación duplicados tras el reinicio: {duplicated}. "
        "El registro sin `strategy_id` se re-proyecta en el contexto 'idle'."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
