#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de HALLAZGOS para 2.8.8.9.8.4 (NO SOBRESCRITURA INDEBIDA).

Cada bloque monta un escenario minimo y COMPRUEBA una hypothesis concreta sobre
lo que la recuperacion hace con los datos validos. No afirma nada: informa.
"""

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

REGLA_SANA = {
    "rule_id": "regla_sana", "name": "regla sana", "description": "d",
    "condition_pattern": "patron sano", "adaptation_actions": ["enable_safe_mode"],
    "context_triggers": ["production"], "confidence_threshold": 0.7, "priority": 2,
    "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}

FB_SANA = {
    "adaptation_id": "fb_ok", "success": True, "adaptation_context": {},
    "execution_result": {}, "verification_result": {}, "improvement_analysis": {},
    "timestamp": "2024-01-01T00:00:00",
}


def _motor(ficheros):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as h:
            h.write(contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False))
    return ContextualAdaptationEngine(data_dir=data_dir)


def _titulo(t):
    print("=" * 72)
    print(t)


# ---------------------------------------------------------------- D1
def d1_kb_lista_vuelta_dict():
    """Una SECCION LIST de la base (learning_results) que llega como DICCIONARIO.

    `_seccion_de_conocimiento_valida` la rechaza (no es una lista) y
    `_recuperar_grupos_de_base` la trata como grupo. La seccion es lista, sus
    "grupos" no existen: la seccion entera se pierde, y con ella sus HERMANOS
    validos (que si se han leido bien del mismo fichero).
    """
    _titulo("D1: seccion LIST de la base que llega como DICCIONARIO")
    motor = _motor({KB: {"version": "2.0", "data": {
        "learning_results": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
        "success_patterns": {"production": [{"patron": "sano"}]},
    }}})
    kb = motor.knowledge_base
    print("  context_patterns:", json.dumps(kb.get("context_patterns"), ensure_ascii=False, default=str)[:120])
    print("  success_patterns:", json.dumps(kb.get("success_patterns"), ensure_ascii=False, default=str)[:120])
    print("  learning_results:", json.dumps(kb.get("learning_results"), ensure_ascii=False, default=str)[:120])
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:300])
    print("  unidades cargadas KB:", motor._unidades_cargadas.get("knowledge_base"))


# ---------------------------------------------------------------- D1b
def d1b_otra_seccion_lista():
    """La MISMA clase de defecto con OTRA seccion lista (goal_adaptation_feedback)."""
    _titulo("D1b: otra seccion LIST de la base (goal_adaptation_feedback) como DICCIONARIO")
    motor = _motor({KB: {"version": "2.0", "data": {
        "goal_adaptation_feedback": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
    }}})
    kb = motor.knowledge_base
    print("  context_patterns:", json.dumps(kb.get("context_patterns"), ensure_ascii=False, default=str)[:120])
    print("  goal_adaptation_feedback:", json.dumps(kb.get("goal_adaptation_feedback"), ensure_ascii=False, default=str)[:120])
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:300])


# ---------------------------------------------------------------- D2
def d2_condition_pattern():
    """`condition_pattern` es un campo del FORMATO REAL, pero NO esta declarado
    en `field_defaults`: su valor por defecto de recuperacion es None, no "".
    El valor None LLEGA al estado (el campo deja de ser string)."""
    _titulo("D2: condition_pattern corrupto -> valor de recuperacion")
    regla = dict(REGLA_SANA); regla["rule_id"] = "regla_cp"; regla["condition_pattern"] = 12345
    motor = _motor({RF: {"version": "2.0", "rules": [regla]}})
    for rid, r in motor.adaptation_rules.items():
        print("  regla", rid, "condition_pattern=", repr(r.condition_pattern), type(r.condition_pattern).__name__)
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:300])
    print("  field_defaults declara condition_pattern:",
          "condition_pattern" in motor._RECOVERABLE_DATA.get("field_defaults", {}))


# ---------------------------------------------------------------- D2b
def d2b_rule_id_no_string():
    """`rule_id` corrupto (no string): la fila se registra con identidad
    INVENTADA, que en el caso de `name` ausente da un nombre del id corrupto."""
    _titulo("D2b: rule_id no-string")
    regla = dict(REGLA_SANA); regla["rule_id"] = 12345
    motor = _motor({RF: {"version": "2.0", "rules": [regla]}})
    print("  reglas:", list(motor.adaptation_rules))
    for rid, r in motor.adaptation_rules.items():
        print("   ", repr(rid), "name=", repr(r.name))
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:300])


# ---------------------------------------------------------------- D3
def d3_feedback_cruza_ficheros():
    """La KB tiene feedback VALIDO y el fichero FB tiene una fila corrupta.
    La carga del FB SOBREESCRIBE el feedback sano de la KB."""
    _titulo("D3: KB con feedback sano + FB con fila corrupta")
    motor = _motor({
        KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_SANA, adaptation_id="fb_kb")]}},
        FB: {"goal_adaptation_feedback": [dict(FB_SANA, adaptation_id="fb_fichero"),
                                          {"adaptation_id": 999, "success": "no booleano"}],
             "adaptation_history": []},
    })
    ids = [f.get("adaptation_id") for f in motor.knowledge_base.get("goal_adaptation_feedback", [])]
    print("  adaptation_id en el estado:", ids)
    print("  fb_kb (sano en la KB) sobrevive:", "fb_kb" in ids)
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:300])


# ---------------------------------------------------------------- D3b
def d3b_learning_results_cruza_ficheros():
    """La KB tiene learning_results VALIDOS y el fichero LR tiene la SECCION
    ausente: la carga del LR debe CONSERVAR los de la KB (o no?)."""
    _titulo("D3b: KB con learning_results sanos + LR sin seccion learning_results")
    motor = _motor({
        KB: {"version": "2.0", "data": {"learning_results": [
            {"adaptation_id": "lr_kb", "learned_patterns": [], "updated_strategies": {}}]}},
        LR: {"adaptation_strategies": {}},
    })
    print("  learning_results:", json.dumps(motor.knowledge_base.get("learning_results"), ensure_ascii=False, default=str)[:200])


# ---------------------------------------------------------------- D4
def d4_fb_seccion_no_lista():
    """El FB tiene la seccion `goal_adaptation_feedback` corrupta (no lista):
    la carga del FB deja el valor por defecto y la KB ya habia cargado."""
    _titulo("D4: FB con seccion goal_adaptation_feedback no-lista")
    motor = _motor({
        KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_SANA, adaptation_id="fb_kb")]}},
        FB: {"goal_adaptation_feedback": "no es una lista", "adaptation_history": []},
    })
    ids = [f.get("adaptation_id") for f in motor.knowledge_base.get("goal_adaptation_feedback", [])]
    print("  adaptation_id en el estado:", ids)
    print("  fb_kb (sano en la KB) sobrevive:", "fb_kb" in ids)
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:300])


if __name__ == "__main__":
    d1_kb_lista_vuelta_dict()
    d1b_otra_seccion_lista()
    d2_condition_pattern()
    d2b_rule_id_no_string()
    d3_feedback_cruza_ficheros()
    d3b_learning_results_cruza_ficheros()
    d4_fb_seccion_no_lista()
