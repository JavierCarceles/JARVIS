#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda SANDBOXED para 2.8.8.9.8.4: no destruye datos validos todavia recuperables."""

import json
import os
import sys
import tempfile

# SANDBOX: el CWD se mueve a un temporal ANTES de importar el motor, de modo que
# las rutas RELATIVAS de los subsistemas ajenos caigan en el temporal.
_SANDBOX = tempfile.mkdtemp(prefix="jarvis_8_4_sandbox_")
for _sub in ("data", "models", "logs", "config"):
    os.makedirs(os.path.join(_SANDBOX, _sub), exist_ok=True)
os.chdir(_SANDBOX)

_TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_TESTS_DIR, "..", ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402

RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"

REGLA_SANA = {
    "rule_id": "regla_sana", "name": "regla sana", "description": "d",
    "condition_pattern": "patron sano", "adaptation_actions": ["enable_safe_mode"],
    "context_triggers": ["production"], "confidence_threshold": 0.7, "priority": 2,
    "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}


def _escribir(data_dir, ficheros):
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as h:
            h.write(contenido if isinstance(contenido, str)
                    else json.dumps(contenido, ensure_ascii=False))


def _escenario(nombre, ficheros, observador):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    _escribir(data_dir, ficheros)
    motor = ContextualAdaptationEngine(data_dir=data_dir)
    print("=" * 74)
    print("ESCENARIO:", nombre)
    observador(motor)


# ---------------------------------------------------------------- 1. condition_pattern
def s1():
    regla = dict(REGLA_SANA)
    regla["rule_id"] = "regla_cp"
    regla["condition_pattern"] = 12345
    return {RF: {"version": "2.0", "rules": [dict(REGLA_SANA), regla]}}


def o1(motor):
    for rid, r in motor.adaptation_rules.items():
        print(f"  {rid}: condition_pattern={r.condition_pattern!r} "
              f"type={type(r.condition_pattern).__name__}")
    print("  informe:", json.dumps(motor.recovery_report()["recoveries"], default=str)[:300])


# ---------------------------------------------------------------- 2. KB adaptacion_strategies
def s2():
    return {KB: {"version": "2.0", "data": {
        "adaptation_strategies": {"production": [{"strategy_id": "s1", "confidence": 0.9,
                                                  "success_rate": 0.5,
                                                  "last_updated": "2024-01-01T00:00:00"},
                                                 "NO_ES_UN_MAPPING"]}}}}


def o2(motor):
    print("  adaptation_strategies:",
          json.dumps(motor.knowledge_base.get("adaptation_strategies"), default=str)[:300])


# ---------------------------------------------------------------- 3. KB context_patterns grupo corrupto
def s3():
    return {KB: {"version": "2.0", "data": {
        "context_patterns": {"production": [{"patron": "sano"}],
                             "development": "grupo corrupto"}}}}


def o3(motor):
    print("  context_patterns:",
          json.dumps(motor.knowledge_base.get("context_patterns"), default=str)[:300])


# ---------------------------------------------------------------- 4. KB feedback valido + FB con filas invalidas
FB_FILA_OK = {"adaptation_id": "fb_ok", "success": True, "adaptation_context": {},
              "execution_result": {}, "verification_result": {}, "improvement_analysis": {},
              "timestamp": "2024-01-01T00:00:00"}


def s4():
    return {
        KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_FILA_OK)]}},
        FB: {"goal_adaptation_feedback": [{"adaptation_id": 999, "success": "no booleano"}],
             "adaptation_history": []},
    }


def o4(motor):
    print("  goal_adaptation_feedback:",
          json.dumps(motor.knowledge_base.get("goal_adaptation_feedback"), default=str)[:300])


# ---------------------------------------------------------------- 5. KB learning_results valido + LR vacio
def s5():
    return {
        KB: {"version": "2.0", "data": {"learning_results": [
            {"goal_id": "g1", "learned_patterns": [], "updated_strategies": {}}]}},
        LR: {"learning_results": [], "adaptation_strategies": {}},
    }


def o5(motor):
    print("  learning_results:",
          json.dumps(motor.knowledge_base.get("learning_results"), default=str)[:300])


# ---------------------------------------------------------------- 6. KB feedback valido + FB con lista VACIA
def s6():
    return {
        KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_FILA_OK)]}},
        FB: {"goal_adaptation_feedback": [], "adaptation_history": []},
    }


def o6(motor):
    print("  goal_adaptation_feedback:",
          json.dumps(motor.knowledge_base.get("goal_adaptation_feedback"), default=str)[:300])


# ---------------------------------------------------------------- 7. KB secciones: adaptacion_strategies con grupo NO lista
def s7():
    return {KB: {"version": "2.0", "data": {
        "adaptation_strategies": {"production": {"no": "es lista"},
                                  "development": [{"strategy_id": "s2", "confidence": 0.9,
                                                   "success_rate": 0.5,
                                                   "last_updated": "2024-01-01T00:00:00"}]}}}}


def o7(motor):
    print("  adaptation_strategies:",
          json.dumps(motor.knowledge_base.get("adaptation_strategies"), default=str)[:400])


if __name__ == "__main__":
    _escenario("1 condition_pattern corrupto", s1(), o1)
    _escenario("2 KB adaptation_strategies con entrada no-mapeo", s2(), o2)
    _escenario("3 KB context_patterns con grupo corrupto", s3(), o3)
    _escenario("4 KB feedback valido + FB con fila invalida", s4(), o4)
    _escenario("5 KB learning_results valido + LR vacio", s5(), o5)
    _escenario("6 KB feedback valido + FB con lista vacia", s6(), o6)
    _escenario("7 KB adaptation_strategies grupo no-lista", s7(), o7)
