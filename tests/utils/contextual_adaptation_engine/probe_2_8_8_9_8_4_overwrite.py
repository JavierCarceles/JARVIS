#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de observacion para 2.8.8.9.8.4 (NO SOBRESCRITURA INDEBIDA).

Monta escenarios propios y OBSERVA el runtime: que sobrevive a una carga con
recuperacion y que se sobrescribe. No afirma nada: solo informa.
"""

import hashlib
import json
import os
import sys
import tempfile

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402

RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"


def _escribir(data_dir, ficheros):
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as handle:
            handle.write(contenido if isinstance(contenido, str)
                         else json.dumps(contenido, ensure_ascii=False))


def _sha(ruta):
    if not os.path.isfile(ruta):
        return None
    return hashlib.sha256(open(ruta, "rb").read()).hexdigest()


def _firmas(data_dir):
    return {n: _sha(os.path.join(data_dir, n)) for n in (RF, KB, FB, LR)}


REGLA_SANA = {
    "rule_id": "regla_sana", "name": "regla sana", "description": "d",
    "condition_pattern": "patron sano", "adaptation_actions": ["enable_safe_mode"],
    "context_triggers": ["production"], "confidence_threshold": 0.7, "priority": 2,
    "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}


def escenario_campo_corrupto():
    regla = dict(REGLA_SANA)
    regla["rule_id"] = "regla_corrupta"
    regla["priority"] = "no es un numero"
    otra = dict(REGLA_SANA); otra["rule_id"] = "regla_hermana"
    return {RF: {"version": "2.0", "rules": [dict(REGLA_SANA), regla, otra]}}


def escenario_condition_pattern():
    regla = dict(REGLA_SANA)
    regla["rule_id"] = "regla_cp"
    regla["condition_pattern"] = 12345
    return {RF: {"version": "2.0", "rules": [regla]}}


def escenario_contenedor():
    return {RF: {"version": "2.0", "rules": {"k1": dict(REGLA_SANA),
                                             "k2": "no es una fila"}}}


def escenario_grupo_kb():
    return {KB: {"version": "2.0", "data": {
        "context_patterns": {"production": [{"patron": "sano"}],
                             "development": "grupo corrupto"},
        "success_patterns": {"production": [{"patron": "sano"}]}}}}


def escenario_feedback_cruzado():
    return {
        KB: {"version": "2.0", "data": {
            "goal_adaptation_feedback": [{"adaptation_id": "fb_kb", "success": True,
                                          "adaptation_context": {}, "execution_result": {},
                                          "verification_result": {}, "improvement_analysis": {},
                                          "timestamp": "2024-01-01T00:00:00"}]}},
        FB: {"goal_adaptation_feedback": [{"adaptation_id": "fb_ok", "success": True,
                                           "adaptation_context": {}, "execution_result": {},
                                           "verification_result": {}, "improvement_analysis": {},
                                           "timestamp": "2024-01-01T00:00:00"},
                                          {"adaptation_id": 999, "success": "no booleano"}],
             "adaptation_history": []},
    }


def ejecutar(nombre, ficheros, observador):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    _escribir(data_dir, ficheros)
    antes = _firmas(data_dir)
    motor = ContextualAdaptationEngine(data_dir=data_dir)
    despues = _firmas(data_dir)
    print("=" * 70)
    print("ESCENARIO:", nombre)
    print("  ficheros reescritos por la carga:",
          sorted(n for n in antes if antes[n] != despues[n]))
    observador(motor)
    print("  informe de recuperacion:",
          json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:400])
    # tras guardar
    motor.save_all_data()
    print("  ficheros reescritos tras save_all_data:",
          sorted(n for n in antes if antes[n] != _firmas(data_dir)[n]))


def obs_campo(motor):
    for rid, regla in motor.adaptation_rules.items():
        print("  regla", rid, "priority=", repr(regla.priority),
              "condition_pattern=", repr(regla.condition_pattern),
              "actions=", regla.adaptation_actions,
              "triggers=", [t.value for t in regla.context_triggers],
              "success_rate=", regla.success_rate,
              "execution_count=", regla.execution_count)


def obs_cp(motor):
    for rid, regla in motor.adaptation_rules.items():
        print("  regla", rid, "condition_pattern=", repr(regla.condition_pattern))


def obs_contenedor(motor):
    print("  reglas:", sorted(motor.adaptation_rules))


def obs_kb(motor):
    kb = motor.knowledge_base
    print("  context_patterns:", json.dumps(kb.get("context_patterns"), ensure_ascii=False, default=str))
    print("  success_patterns:", json.dumps(kb.get("success_patterns"), ensure_ascii=False, default=str))


def obs_feedback(motor):
    print("  goal_adaptation_feedback:",
          json.dumps(motor.knowledge_base.get("goal_adaptation_feedback"), ensure_ascii=False, default=str))


if __name__ == "__main__":
    ejecutar("campo corrupto (priority)", escenario_campo_corrupto(), obs_campo)
    ejecutar("campo corrupto (condition_pattern)", escenario_condition_pattern(), obs_cp)
    ejecutar("contenedor rules con otra forma", escenario_contenedor(), obs_contenedor)
    ejecutar("grupo corrupto en la base", escenario_grupo_kb(), obs_kb)
    ejecutar("feedback: KB sana + fichero con fila invalida", escenario_feedback_cruzado(), obs_feedback)
