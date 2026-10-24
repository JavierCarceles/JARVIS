#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificacion en RUNTIME de la COMPATIBILIDAD TRAS REINICIO (2.8.12.5).

Verifica que la persistencia GLOBAL del motor es COMPATIBLE tras un reinicio:
los datos guardados en los cuatro ficheros de persistencia se recuperan
completos, sin perdida ni degradacion, y el motor vuelve al estado operativo
con base de conocimiento y reglas consistentes.

Escenarios:
  1. Real restart round-trip: guardar los cuatro ficheros, reiniciar y
     comprobar que cada uno se recupera con su datos canonico completo.
  2. Reglas modificadas (regla anadida, regla deshabilitada) sobreviven al
     reinicio con todos sus campos.
  3. `get_engine_status()` tras el reinicio con datos sanos no declara
     anomalias de corrupcion, almacenamiento ausente o secciones ausentes.
  4. `backup_data()` tras el reinicio cubre los cuatro ficheros de persistencia.
  5. Multiples reinicios no duplican ni degradan los datos.
  6. El motor sigue operativo (captura de contexto) tras el reinicio.

No modifica `data/` de produccion: todo el trabajo se hace sobre un directorio
temporal y, para el fichero real, sobre una COPIA de solo lectura.

Uso:
    python tests/utils/contextual_adaptation_engine/verify_restart_compatibility_real.py
"""

import copy
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

# NOTA: la importacion de `utils.contextual_adaptation_engine` se retrasa hasta
# dentro de `main()`, DESPUES de cambiar el CWD al sandbox. El modulo arranca
# singletons (SelfImprovementSystem, PerformanceOptimizer) con hilos que
# escriben rutas RELATIVAS ('data/knowledge_graph.json'); importarlo antes del
# sandbox contaminaria `data/` de produccion.

LEARNING_FILE = "goal_adaptation_learning_results.json"
RULES_FILE = "contextual_adaptation_rules.json"
KB_FILE = "contextual_knowledge_base.json"
FB_FILE = "goal_adaptation_feedback.json"

STORAGE_FILES = (FB_FILE, LEARNING_FILE, RULES_FILE, KB_FILE)

CANONICAL_RULE_FIELDS = (
    "rule_id", "name", "description", "condition_pattern", "adaptation_actions",
    "context_triggers", "confidence_threshold", "priority", "enabled",
    "success_rate", "execution_count", "last_execution", "adaptation_score",
    "constraints", "metadata", "deadline",
)

FAILURES = []
FINDINGS = []


def check(label, condition, detail=""):
    status = "OK  " if condition else "FALLO"
    if not condition:
        FAILURES.append(label)
        logging.disable(logging.NOTSET)
    print(f"  [{status}] {label}" + (f" :: {detail}" if detail else ""))


def hallazgo(label, detail=""):
    FINDINGS.append(label)
    print(f"  [HALLAZGO] {label}" + (f" :: {detail}" if detail else ""))


def sha256(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            digest.update(bloque)
    return digest.hexdigest()


def nuevo_motor(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    return ContextualAdaptationEngine(data_dir=data_dir)


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


def _snapshot(context_type=None, snapshot_id="snap_restart_001"):
    if context_type is None:
        context_type = ContextType.PRODUCTION
    return ContextSnapshot(
        snapshot_id=snapshot_id,
        timestamp=None,
        context_type=context_type,
        contextual_factors={},
        system_metrics={},
        performance_metrics={},
        user_interaction_patterns={},
        environmental_conditions={},
        confidence_score=0.85,
        adaptation_level=AdaptationLevel.MINIMAL,
    )


def _rules_signature(motor):
    """Firma canonica de las reglas: rule_id -> dict con campos completos."""
    return {
        rid: {k: v for k, v in r.to_dict().items() if k in CANONICAL_RULE_FIELDS}
        for rid, r in (motor.adaptation_rules or {}).items()
    }


def _kb_signature(motor):
    """Firma canonica de la base de conocimiento relevante para compatibilidad."""
    kb = motor.knowledge_base or {}
    context_patterns = kb.get("context_patterns", {})
    adaptation_strategies = kb.get("adaptation_strategies", {})
    total_patterns = sum(len(v) if isinstance(v, list) else 0 for v in context_patterns.values())
    total_strategies = sum(len(v) if isinstance(v, list) else 0 for v in adaptation_strategies.values())
    return {
        "context_patterns_total": total_patterns,
        "context_patterns_contexts": sorted(context_patterns.keys()) if isinstance(context_patterns, dict) else [],
        "adaptation_strategies_contexts": sorted(adaptation_strategies.keys()) if isinstance(adaptation_strategies, dict) else [],
        "adaptation_strategies_total": total_strategies,
        "goal_adaptation_feedback_count": len(kb.get("goal_adaptation_feedback", []) or []),
        "learning_results_count": len(kb.get("learning_results", []) or []),
    }


def _feedback_ids(motor):
    return [
        row.get("adaptation_id")
        for row in (motor.knowledge_base.get("goal_adaptation_feedback") or [])
        if isinstance(row, dict)
    ]


def _learning_ids(motor):
    return [
        row.get("adaptation_id")
        for row in (motor.knowledge_base.get("learning_results") or [])
        if isinstance(row, dict)
    ]


# ---------------------------------------------------------------------------
# Scenario 1: compatibilidad global tras reinicio (los cuatro ficheros)
# ---------------------------------------------------------------------------
def scenario_restart_compatibility():
    print("\n[1] Compatibilidad global tras reinicio (los cuatro ficheros)")
    tmp = tempfile.mkdtemp(prefix="jarvis_restart_compat_")
    try:
        engine = nuevo_motor(tmp)

        # 1a. Modificaciones de reglas
        custom_rule = AdaptationRule(
            rule_id="regla_compat_reinicio",
            name="regla de compatibilidad",
            description="regla anadida para verificar compatibilidad tras reinicio",
            condition_pattern="contextual_factors.system_resources > 0.8",
            adaptation_actions=["enable_performance_mode", "cache_optimization"],
            context_triggers=[ContextType.PRODUCTION],
            confidence_threshold=0.75,
            priority=5,
            enabled=True,
            success_rate=0.9,
            execution_count=3,
            last_execution=None,
            adaptation_score=0.6,
            constraints=["constraint_1"],
            metadata={"origen": "verify_restart_compatibility"},
            deadline=None,
        )
        engine.add_adaptation_rule(custom_rule)
        engine.disable_rule("rule_001")
        engine.disable_rule("rule_002")

        # 1b. Captura de feedback + bucle de aprendizaje (persiste FB + LR)
        feedback_result = engine._capture_goal_adaptation_feedback(_feedback_data())
        assert feedback_result["success"] is True, feedback_result.get("error_message")
        learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
        assert learning_result["success"] is True, learning_result.get("error_message")
        assert learning_result["learned_patterns"], "Debe aprenderse al menos un patron"

        # 1c. Captura de contexto (anade context_patterns a la base de conocimiento)
        snapshot = engine.capture_context_snapshot()

        # 1d. Guardado completo de los cuatro ficheros
        engine.save_all_data()

        # 1e. Verificar que los cuatro ficheros existen en disco
        paths = engine.expected_storage_paths()
        for name in ("adaptation_rules", "knowledge_base",
                     "goal_adaptation_feedback", "goal_adaptation_learning_results"):
            check(f"el fichero {name} existe tras el guardado",
                  os.path.isfile(paths[name]), f"path={paths[name]}")

        # 1f. Firma del estado antes del reinicio
        rules_before = _rules_signature(engine)
        kb_before = _kb_signature(engine)
        fb_ids_before = _feedback_ids(engine)
        lr_ids_before = _learning_ids(engine)
        assert "regla_compat_reinicio" in rules_before, "La regla personalizada debe estar en memoria"
        assert engine.get_adaptation_rule("rule_001") is not None
        assert engine.get_adaptation_rule("rule_001").enabled is False, "rule_001 debe estar deshabilitada"

        # 1g. REINICIO: nueva instancia con el mismo data_dir
        restarted = ContextualAdaptationEngine(data_dir=tmp)

        # 1h. Verificar las reglas
        rules_after = _rules_signature(restarted)
        check("la regla personalizada sobrevive al reinicio",
              "regla_compat_reinicio" in rules_after)
        check("rule_001 conserva enabled=False tras el reinicio",
              rules_after.get("rule_001", {}).get("enabled") is False)
        check("rule_002 conserva enabled=False tras el reinicio",
              rules_after.get("rule_002", {}).get("enabled") is False)
        check("las reglas coinciden exactamente tras el reinicio",
              rules_before == rules_after,
              f"before_keys={sorted(rules_before)} after_keys={sorted(rules_after)}")
        if "regla_compat_reinicio" in rules_after:
            regla = rules_after["regla_compat_reinicio"]
            for field in CANONICAL_RULE_FIELDS:
                check(f"la regla personalizada conserva el campo canonico '{field}' tras el reinicio",
                      field in regla, f"regla={regla}")

        # 1i. Verificar la base de conocimiento
        kb_after = _kb_signature(restarted)
        check("context_patterns se recuperan tras el reinicio",
              kb_after["context_patterns_total"] > 0, f"total={kb_after['context_patterns_total']}")
        check("adaptation_strategies se recuperan tras el reinicio",
              kb_after["adaptation_strategies_total"] > 0, f"total={kb_after['adaptation_strategies_total']}")
        check("goal_adaptation_feedback se recupera tras el reinicio",
              kb_after["goal_adaptation_feedback_count"] == kb_before["goal_adaptation_feedback_count"]
              and kb_after["goal_adaptation_feedback_count"] > 0,
              f"before={kb_before['goal_adaptation_feedback_count']} after={kb_after['goal_adaptation_feedback_count']}")
        check("learning_results se recuperan tras el reinicio",
              kb_after["learning_results_count"] == kb_before["learning_results_count"]
              and kb_after["learning_results_count"] > 0,
              f"before={kb_before['learning_results_count']} after={kb_after['learning_results_count']}")

        # 1j. Verificar IDs conservados
        fb_ids_after = _feedback_ids(restarted)
        lr_ids_after = _learning_ids(restarted)
        check("los adaptation_id de feedback coinciden tras el reinicio",
              fb_ids_before == fb_ids_after, f"before={fb_ids_before} after={fb_ids_after}")
        check("los adaptation_id de learning_results coinciden tras el reinicio",
              lr_ids_before == lr_ids_after, f"before={lr_ids_before} after={lr_ids_after}")

        # 1k. Estado del motor: datos sanos no deben declarar anomalias
        status = restarted.get_engine_status()
        check("get_engine_status tras reinicio con datos sanos: corruption_count == 0",
              status["corruption"]["corruption_count"] == 0,
              f"corruption_count={status['corruption']['corruption_count']}")
        check("get_engine_status tras reinicio con datos sanos: unreadable_count == 0",
              status["corruption"]["unreadable_count"] == 0,
              f"unreadable_count={status['corruption']['unreadable_count']}")
        check("get_engine_status tras reinicio con datos sanos: absent_count == 0",
              status["storage"]["absent_count"] == 0,
              f"absent_count={status['storage']['absent_count']}")
        check("get_engine_status tras reinicio con datos sanos: absent_sections_count == 0",
              status["storage_sections"]["absent_count"] == 0,
              f"absent_count={status['storage_sections']['absent_count']}")
        check("get_engine_status tras reinicio: total_rules coincide",
              status["total_rules"] == len(rules_before),
              f"status_total_rules={status['total_rules']} expected={len(rules_before)}")

        # 1l. load_all_data declara exito al haber cargado datos
        restarted2 = ContextualAdaptationEngine(data_dir=tmp)
        carga = restarted2.load_all_data()
        check("load_all_data() devuelve True al recargar datos validos",
              carga is True, f"returned={carga}")

        # 1m. backup_data tras el reinicio cubre los cuatro ficheros
        backup_dir = os.path.join(tmp, "backups")
        restarted.backup_data(backup_dir)
        claves = list(restarted.expected_storage_paths())
        cubiertos = {clave for clave in claves
                     if any(nombre.startswith(clave + "_backup_")
                            for nombre in os.listdir(backup_dir))}
        check("backup_data() tras reinicio respalda los cuatro ficheros",
              cubiertos == set(claves), f"cubiertos={sorted(cubiertos)} expected={sorted(claves)}")

        # 1n. El motor sigue operativo tras el reinicio
        new_snapshot = restarted.capture_context_snapshot()
        check("el motor captura contexto tras el reinicio",
              new_snapshot is not None and new_snapshot.snapshot_id is not None)

        # 1o. Estabilidad: segundo reinicio sin duplicacion
        second = ContextualAdaptationEngine(data_dir=tmp)
        rules_second = _rules_signature(second)
        check("el segundo reinicio mantiene las mismas reglas (sin duplicacion)",
              rules_second == rules_after)
        kb_second = _kb_signature(second)
        check("el segundo reinicio mantiene los mismos learning_results (sin duplicacion)",
              kb_second["learning_results_count"] == kb_before["learning_results_count"])
        fb_second = _feedback_ids(second)
        check("el segundo reinicio mantiene el mismo feedback (sin duplicacion)",
              fb_second == fb_ids_before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scenario 2: compatibilidad de produccion (no contaminacion)
# ---------------------------------------------------------------------------
def scenario_production_isolation():
    print("\n[2] Aislamiento del data/ de produccion")
    source = os.path.join(ROOT, "data")
    hashes_before = {
        os.path.join(source, f): sha256(os.path.join(source, f))
        for f in STORAGE_FILES
        if os.path.isfile(os.path.join(source, f))
    }
    if not hashes_before:
        print("  (no hay ficheros de produccion para comparar; escenario omitido)")
        return
    tmp = tempfile.mkdtemp(prefix="jarvis_restart_prod_")
    try:
        # Copiar los ficheros reales a un temporario y reiniciar sobre la copia.
        data_tmp = os.path.join(tmp, "data")
        os.makedirs(data_tmp, exist_ok=True)
        for f in STORAGE_FILES:
            src = os.path.join(source, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(data_tmp, f))
        # El motor se instancia sobre la COPIA, nunca sobre data/ real.
        engine = ContextualAdaptationEngine(data_dir=data_tmp)
        status = engine.get_engine_status()
        present_in_prod = [f for f in STORAGE_FILES if os.path.isfile(os.path.join(source, f))]
        absent_in_prod = [f for f in STORAGE_FILES if not os.path.isfile(os.path.join(source, f))]
        check("el motor sobre la copia no declara corrupto datos sanos",
              status["corruption"]["corruption_count"] == 0,
              f"corruption_count={status['corruption']['corruption_count']}")
        # El motor DEBE declarar ausente EXACTAMENTE los ficheros que no existen
        # en produccion: no inventa ausencias ni las oculta.
        expected_absent = len(absent_in_prod)
        check("el motor declara ausente el Numero correcto de ficheros (coincide con produccion)",
              status["storage"]["absent_count"] == expected_absent,
              f"absent_count={status['storage']['absent_count']} expected={expected_absent} "
              f"absent={sorted(absent_in_prod)} present={sorted(present_in_prod)}")

        hashes_after = {
            os.path.join(source, f): sha256(os.path.join(source, f))
            for f in STORAGE_FILES
            if os.path.isfile(os.path.join(source, f))
        }
        check("los ficheros de produccion quedan byte a byte intactos",
              hashes_before == hashes_after)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    logging.disable(logging.CRITICAL)
    # Sandbox del CWD: `utils` instancia singletons (SelfImprovementSystem,
    # PerformanceOptimizer) cuyos hilos escriben con rutas RELATIVAS
    # ('data/knowledge_graph.json', 'data/improvement_rules.json'). Sin un
    # sandbox, la sonda contaminaria `data/` de PRODUCCION. Se cambia al CWD
    # temporal ANTES de importar el motor, como hace identify_fallback_real.py.
    _sandbox = tempfile.mkdtemp(prefix="jarvis_restart_sandbox_")
    for _sub in ("data", "models", "logs", "config"):
        os.makedirs(os.path.join(_sandbox, _sub), exist_ok=True)
    os.chdir(_sandbox)

    # Importacion TRAS el sandbox: los singletons se inicializan contra el CWD
    # temporal y sus hilos escriben dentro del sandbox, no en produccion.
    global AdaptationLevel, ContextSnapshot, ContextType, AdaptationRule, ContextualAdaptationEngine
    from utils.contextual_adaptation_engine import (
        AdaptationLevel,
        ContextSnapshot,
        ContextType,
        AdaptationRule,
        ContextualAdaptationEngine,
    )

    print("=" * 78)
    print("VERIFICACION EN RUNTIME DE LA COMPATIBILIDAD TRAS REINICIO (2.8.12.5)")
    print("=" * 78)
    scenario_restart_compatibility()
    scenario_production_isolation()
    print("\n" + "=" * 78)
    if FAILURES:
        print(f"RESULTADO: {len(FAILURES)} COMPROBACION(ES) FALLIDA(S): {FAILURES}")
        return 1
    print("RESULTADO: TODAS LAS COMPROBACIONES DE RUNTIME OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
