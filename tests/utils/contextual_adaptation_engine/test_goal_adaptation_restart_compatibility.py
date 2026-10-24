#!/usr/bin/env python3
"""
Verificacion de compatibilidad tras reinicio (2.8.12.5).

Verifica que la persistencia GLOBAL del motor es COMPATIBLE tras un reinicio:
los datos guardados en los cuatro ficheros de persistencia se recuperan
completos, sin perdida ni degradacion, y el motor vuelve al estado operativo
con base de conocimiento y reglas consistentes.

Esta hoja complementa las verificaciones de reinicio ya existentes (patrones de
aprendizaje 2.8.8.9.4.5 y estrategias 2.8.8.9.3.5) cubriendo la compatibilidad
GLOBAL que no estaban cubriendo:

  - Las modificaciones de reglas (regla anadida, regla deshabilitada) sobreviven
    al reinicio con su conjunto canonico de campos completo (no solo `is not
    None`).
  - La base de conocimiento (context_patterns, adaptation_strategies, ...) se
    recupera tras el reinicio.
  - `get_engine_status()` tras el reinicio con datos SANOS no declara anomalias
    de corrupcion, almacenamiento ausente o secciones ausentes.
  - `backup_data()` tras el reinicio cubre los cuatro ficheros de persistencia.
  - Multiples reinicios no duplican ni degradan los datos.
  - El motor sigue operativo (captura de contexto) tras el reinicio.
  - `load_all_data()` devuelve True al recargar datos validos.

El motor se instancia con `data_dir` temporal, por lo que el test no lee ni
escribe sobre `data/` de produccion.
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import (  # noqa: E402
    AdaptationLevel,
    AdaptationRule,
    ContextSnapshot,
    ContextType,
    ContextualAdaptationEngine,
)

CANONICAL_RULE_FIELDS = (
    "rule_id", "name", "description", "condition_pattern", "adaptation_actions",
    "context_triggers", "confidence_threshold", "priority", "enabled",
    "success_rate", "execution_count", "last_execution", "adaptation_score",
    "constraints", "metadata", "deadline",
)


def _make_rule(rule_id):
    return AdaptationRule(
        rule_id=rule_id,
        name="regla " + rule_id,
        description="descripcion " + rule_id,
        condition_pattern="contextual_factors.system_resources > 0.8",
        adaptation_actions=["enable_performance_mode"],
        context_triggers=[ContextType.PRODUCTION],
        confidence_threshold=0.75,
        priority=3,
        enabled=True,
        success_rate=0.8,
        execution_count=2,
        last_execution=None,
        adaptation_score=0.5,
        constraints=["c1"],
        metadata={"origen": "test_restart_compat"},
        deadline=None,
    )


def _feedback_data(adaptation_id="restart_compat_001"):
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": "goal_original_restart",
        "adapted_goal_id": "goal_adapted_restart",
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


def _persist_all(engine):
    """Capturar feedback, aprender y guardar los cuatro ficheros de persistencia."""
    engine.add_adaptation_rule(_make_rule("regla_compat_test"))
    engine.disable_rule("rule_001")
    feedback_result = engine._capture_goal_adaptation_feedback(_feedback_data())
    assert feedback_result["success"] is True, feedback_result.get("error_message")
    learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
    assert learning_result["success"] is True, learning_result.get("error_message")
    assert learning_result["learned_patterns"], "Debe aprenderse al menos un patron"
    engine.capture_context_snapshot()
    engine.save_all_data()


def _rules_signature(motor):
    return {
        rid: {k: v for k, v in r.to_dict().items() if k in CANONICAL_RULE_FIELDS}
        for rid, r in (motor.adaptation_rules or {}).items()
    }


@pytest.fixture
def engine(tmp_path):
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def test_modificaciones_de_reglas_sobreviven_al_reinicio(engine, tmp_path):
    """Regla anadida y regla deshabilitada: todos los campos canonicos sobreviven."""
    _persist_all(engine)
    rules_before = _rules_signature(engine)
    assert "regla_compat_test" in rules_before
    assert engine.get_adaptation_rule("rule_001") is not None
    assert engine.get_adaptation_rule("rule_001").enabled is False

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    rules_after = _rules_signature(restarted)

    assert "regla_compat_test" in rules_after, "La regla anadida debe sobrevivir al reinicio"
    assert rules_after.get("rule_001", {}).get("enabled") is False, "rule_001 debe seguir deshabilitada"
    assert rules_before == rules_after, "Las reglas deben coincidir exactamente tras el reinicio"
    for field in CANONICAL_RULE_FIELDS:
        assert field in rules_after["regla_compat_test"], (
            f"La regla anadida debe conservar el campo canonico '{field}' tras el reinicio"
        )


def test_base_de_conocimiento_completa_tras_reinicio(engine, tmp_path):
    """Todas las secciones de la base de conocimiento se recuperan tras el reinicio."""
    _persist_all(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    kb = restarted.knowledge_base
    assert kb.get("context_patterns"), "context_patterns debe recuperarse tras el reinicio"
    assert kb.get("adaptation_strategies"), "adaptation_strategies debe recuperarse tras el reinicio"
    assert kb.get("goal_adaptation_feedback"), "goal_adaptation_feedback debe recuperarse tras el reinicio"
    assert kb.get("learning_results"), "learning_results debe recuperarse tras el reinicio"
    assert kb.get("transfer_efficiency") is not None, "transfer_efficiency debe conservarse tras el reinicio"
    assert kb.get("success_patterns") is not None, "success_patterns debe conservarse tras el reinicio"
    assert kb.get("performance_baselines") is not None, "performance_baselines debe conservarse tras el reinicio"


def test_estado_motor_sin_anomalias_tras_reinicio_con_datos_sanos(engine, tmp_path):
    """Con datos sanos, get_engine_status() no declara anomalias tras el reinicio."""
    _persist_all(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    status = restarted.get_engine_status()

    assert status["corruption"]["corruption_count"] == 0, (
        f"no debe haber corrupcion con datos sanos: {status['corruption']['corruption_count']}"
    )
    assert status["corruption"]["unreadable_count"] == 0, (
        f"no debe haber ficheros ilegibles con datos sanos: {status['corruption']['unreadable_count']}"
    )
    assert status["storage"]["absent_count"] == 0, (
        f"no debe haber almacenamiento ausente con datos sanos: {status['storage']['absent_count']}"
    )
    assert status["storage_sections"]["absent_count"] == 0, (
        f"no debe haber secciones ausentes con datos sanos: {status['storage_sections']['absent_count']}"
    )
    assert status["total_rules"] == len(engine.adaptation_rules), (
        f"el numero de reglas debe coincidir tras el reinicio: "
        f"{status['total_rules']} vs {len(engine.adaptation_rules)}"
    )


def test_load_all_data_verdadero_tras_reinicio_con_datos(engine, tmp_path):
    """load_all_data() devuelve True al recargar datos validos tras el reinicio."""
    _persist_all(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    assert restarted.load_all_data() is True, (
        "load_all_data() debe devolver True cuando los ficheros aportan datos"
    )


def test_backup_data_tras_reinicio_cubre_los_cuatro_ficheros(engine, tmp_path):
    """backup_data() tras el reinicio respalda los cuatro ficheros de persistencia."""
    _persist_all(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    backup_dir = os.path.join(str(tmp_path), "backups")
    restarted.backup_data(backup_dir)

    claves = list(restarted.expected_storage_paths())
    backup_names = set(os.listdir(backup_dir)) if os.path.isdir(backup_dir) else set()
    cubiertos = {
        clave for clave in claves
        if any(nombre.startswith(clave + "_backup_") for nombre in backup_names)
    }
    assert cubiertos == set(claves), (
        f"backup_data() debe cubrir los cuatro ficheros; cubiertos={sorted(cubiertos)}"
    )


def test_multiples_reinicios_no_duplican(engine, tmp_path):
    """Un segundo reinicio no debe duplicar ni degradar los datos persistidos."""
    _persist_all(engine)

    first = ContextualAdaptationEngine(data_dir=str(tmp_path))
    rules_first = _rules_signature(first)
    fb_count_first = len(first.knowledge_base.get("goal_adaptation_feedback") or [])
    lr_count_first = len(first.knowledge_base.get("learning_results") or [])

    second = ContextualAdaptationEngine(data_dir=str(tmp_path))
    rules_second = _rules_signature(second)
    fb_count_second = len(second.knowledge_base.get("goal_adaptation_feedback") or [])
    lr_count_second = len(second.knowledge_base.get("learning_results") or [])

    assert rules_first == rules_second, "Las reglas no deben duplicarse tras el segundo reinicio"
    assert fb_count_first == fb_count_second, "El feedback no debe duplicarse tras el segundo reinicio"
    assert lr_count_first == lr_count_second, "Los resultados de aprendizaje no deben duplicarse"


def test_motor_operativo_tras_reinicio(engine, tmp_path):
    """El motor puede capturar contexto y ejecutar tras el reinicio."""
    _persist_all(engine)

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))
    snapshot = restarted.capture_context_snapshot()
    assert snapshot is not None, "El motor debe poder capturar contexto tras el reinicio"
    assert snapshot.snapshot_id is not None

    reglas = restarted.analyze_contextual_patterns(snapshot)
    assert isinstance(reglas, list), "El analisis de patrones debe devolver una lista tras el reinicio"
    resultado = restarted.execute_adaptation(snapshot, reglas)
    assert resultado is not None and resultado.success, (
        "La ejecucion de adaptacion debe tener exito tras el reinicio"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
