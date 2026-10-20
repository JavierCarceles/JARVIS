#!/usr/bin/env python3
"""
Verificacion en RUNTIME de la recuperacion de patrones tras el reinicio (2.8.8.9.4.5).

Script de sonda independiente de la suite pytest: ejecuta el ciclo real del motor
(feedback -> aprendizaje -> persistencia -> reinicio) y comprueba, con evidencia
impresa, que los patrones validados se recuperan sin perdida tras reiniciar.

No modifica `data/` de produccion: todo el trabajo se hace sobre un directorio
temporal y, para el fichero real, sobre una COPIA de solo lectura.

Uso:
    python tests/utils/contextual_adaptation_engine/verify_pattern_restart_real.py
"""

import copy
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from utils.contextual_adaptation_engine import ContextType, ContextualAdaptationEngine  # noqa: E402

LEARNING_FILE = "goal_adaptation_learning_results.json"
CANONICAL_FIELDS = ("pattern_id", "pattern_type", "context", "metrics",
                     "confidence", "timestamp", "description")

FAILURES = []


def check(label, condition, detail=""):
    status = "OK  " if condition else "FALLO"
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f" :: {detail}" if detail else ""))


def feedback(adaptation_id, success=True, verified=True, impact=0.8,
             goal_type="navigation", context_type=ContextType.PRODUCTION.value):
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
        "execution_result": {"success": success,
                             "performance_metrics": {"response_time": 1.2, "accuracy": 0.97}},
        "verification_result": {"verified": verified, "impact_score": impact},
    }


def learn(engine, count, prefix="obs"):
    produced = []
    for index in range(1, count + 1):
        captured = engine._capture_goal_adaptation_feedback(feedback(f"{prefix}_{index}"))
        assert captured["success"] is True, captured.get("error_message")
        result = engine._execute_goal_adaptation_learning_loop(captured)
        assert result["success"] is True, result.get("error_message")
        produced.extend(result["learned_patterns"])
    return produced


def patterns_of(engine):
    out = []
    for row in engine.knowledge_base.get("learning_results", []) or []:
        if isinstance(row, dict):
            out.extend(p for p in (row.get("learned_patterns") or []) if isinstance(p, dict))
    return out


def rows_of(engine):
    return [r for r in engine.knowledge_base.get("learning_results", []) or [] if isinstance(r, dict)]


def scenario_real_restart():
    """Ciclo real completo: aprender -> reiniciar -> comprobar recuperacion."""
    print("\n[1] Ciclo real de aprendizaje + reinicio (directorio temporal)")
    tmp = tempfile.mkdtemp(prefix="jarvis_pattern_restart_")
    try:
        engine = ContextualAdaptationEngine(data_dir=tmp)
        produced = learn(engine, 3)
        print(f"  patrones aprendidos: {len(produced)}")

        path = os.path.join(tmp, LEARNING_FILE)
        with open(path, "r", encoding="utf-8") as handle:
            persisted_before = handle.read()
        stat_before = os.stat(path)

        restarted = ContextualAdaptationEngine(data_dir=tmp)
        recovered = patterns_of(restarted)
        print(f"  patrones recuperados tras el reinicio: {len(recovered)}")

        check("se recupera al menos un patron validado", bool(recovered))
        by_id = {p["pattern_id"]: p for p in recovered}
        check("se recupera exactamente el conjunto aprendido",
              set(by_id) == {p["pattern_id"] for p in produced},
              f"recuperados={sorted(by_id)} aprendidos={sorted(p['pattern_id'] for p in produced)}")

        missing = {f: [p["pattern_id"] for p in recovered if f not in p] for f in CANONICAL_FIELDS}
        check("ningun patron pierde campos canonicos",
              not any(missing.values()), f"faltantes={ {k: v for k, v in missing.items() if v} }")

        lost = []
        for original in produced:
            back = by_id.get(original["pattern_id"])
            if not back:
                continue
            for field in CANONICAL_FIELDS:
                if back[field] != original[field]:
                    lost.append(f"{original['pattern_id']}.{field}")
        check("ningun campo canonico cambia de valor", not lost, f"cambios={lost}")

        nested_ok = all(isinstance(p.get("context"), dict) and isinstance(p.get("metrics"), dict)
                        for p in recovered)
        check("las estructuras anidadas siguen siendo diccionarios", nested_ok)

        rows = rows_of(restarted)
        check("se conservan las 3 filas de resultados de aprendizaje", len(rows) == 3,
              f"filas={len(rows)}")
        conv_ok = all(isinstance(r.get("convergence_metrics"), dict)
                      and all(k in r["convergence_metrics"] for k in
                              ("convergence_score", "learning_rate", "stability", "trend"))
                      for r in rows)
        check("cada fila conserva sus metricas de convergencia", conv_ok)
        strat_ok = all(isinstance(r.get("updated_strategies"), dict) and r["updated_strategies"]
                        for r in rows)
        check("cada fila conserva sus estrategias aprendidas", strat_ok)

        # La carga no debe reescribir el fichero persistido.
        with open(path, "r", encoding="utf-8") as handle:
            persisted_after = handle.read()
        stat_after = os.stat(path)
        check("la carga no reescribe el fichero persistido",
              persisted_after == persisted_before and stat_after.st_mtime_ns == stat_before.st_mtime_ns)

        # Segundo reinicio: estabilidad.
        second = ContextualAdaptationEngine(data_dir=tmp)
        second_patterns = patterns_of(second)
        check("el segundo reinicio recupera los mismos patrones",
              {p["pattern_id"] for p in second_patterns} == set(by_id),
              f"segundo={len(second_patterns)} primero={len(by_id)}")

        # Nuevo ciclo de aprendizaje tras el reinicio: no debe perder lo recuperado.
        restarted2 = ContextualAdaptationEngine(data_dir=tmp)
        learn(restarted2, 1, prefix="tras_reinicio")
        with open(path, "r", encoding="utf-8") as handle:
            persisted_final = json.load(handle)
        persisted_ids = {p["pattern_id"]
                         for row in persisted_final.get("learning_results", []) or []
                         for p in (row.get("learned_patterns") or []) if isinstance(p, dict)}
        check("un nuevo ciclo tras el reinicio conserva los patrones recuperados",
              set(by_id) <= persisted_ids,
              f"perdidos={sorted(set(by_id) - persisted_ids)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def scenario_production_copy():
    """Comportamiento real sobre una COPIA del fichero de produccion."""
    print("\n[2] Copia del fichero real de produccion (solo lectura)")
    source = os.path.join(ROOT, "data", LEARNING_FILE)
    if not os.path.isfile(source):
        print("  (no existe el fichero de produccion; escenario omitido)")
        return
    tmp = tempfile.mkdtemp(prefix="jarvis_pattern_prod_")
    try:
        copy_path = os.path.join(tmp, LEARNING_FILE)
        shutil.copy2(source, copy_path)
        with open(copy_path, "r", encoding="utf-8") as handle:
            original = handle.read()

        engine = ContextualAdaptationEngine(data_dir=tmp)
        rows = rows_of(engine)
        patterns = patterns_of(engine)
        print(f"  filas recuperadas: {len(rows)} | patrones recuperados: {len(patterns)}")

        with open(copy_path, "r", encoding="utf-8") as handle:
            after = handle.read()
        check("la copia del fichero real no se modifica", after == original)
        check("las estrategias reales siguen restaurandose",
              bool(engine.knowledge_base.get("adaptation_strategies")),
              f"estrategias={list(engine.knowledge_base.get('adaptation_strategies', {}))}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 78)
    print("VERIFICACION EN RUNTIME DE LA RECUPERACION DE PATRONES TRAS EL REINICIO")
    print("=" * 78)
    scenario_real_restart()
    scenario_production_copy()
    print("\n" + "=" * 78)
    if FAILURES:
        print(f"RESULTADO: {len(FAILURES)} COMPROBACION(ES) FALLIDA(S): {FAILURES}")
        return 1
    print("RESULTADO: TODAS LAS COMPROBACIONES DE RUNTIME OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
