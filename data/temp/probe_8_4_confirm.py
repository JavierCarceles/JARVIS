#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Confirmacion de los defectos de 2.8.8.9.8.4 (SANDBOXED)."""

import json
import os
import sys
import tempfile

_SANDBOX = tempfile.mkdtemp(prefix="jarvis_8_4_confirm_")
for _sub in ("data", "models", "logs", "config"):
    os.makedirs(os.path.join(_SANDBOX, _sub), exist_ok=True)
os.chdir(_SANDBOX)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
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


def _motor(ficheros):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as h:
            h.write(contenido if isinstance(contenido, str)
                    else json.dumps(contenido, ensure_ascii=False))
    return ContextualAdaptationEngine(data_dir=data_dir)


def _demasiado(*_a, **_k):
    pass


import logging  # noqa: E402
logging.disable(logging.CRITICAL)


print("=" * 74)
print("F1: seccion con tipo de lista DENTRO de la base -> ¿se aborta la carga?")
regla = dict(REGLA_SANA)
regla["rule_id"] = "regla_cp"; regla["condition_pattern"] = 12345
m = _motor({RF: {"version": "2.0", "rules": [dict(REGLA_SANA), regla]},
            KB: {"version": "2.0", "data": {
                "learning_results": {"no": "es una lista"},
                "context_patterns": {"production": [{"patron": "sano"}]}}}})
print("  context_patterns (seccion VALIDA hermana):",
      json.dumps(m.knowledge_base.get("context_patterns"), default=str)[:160])
print("  -> la seccion valida ha sobrevivido?" ,
      bool(m.knowledge_base.get("context_patterns", {}).get("production")))

print("=" * 74)
print("F2: condition_pattern corrupto -> valor de recuperacion")
regla = dict(REGLA_SANA)
regla["rule_id"] = "regla_cp"; regla["condition_pattern"] = 12345
m = _motor({RF: {"version": "2.0", "rules": [dict(REGLA_SANA), regla]}})
for rid, r in m.adaptation_rules.items():
    print("  %-14s condition_pattern=%r" % (rid, r.condition_pattern))

print("=" * 74)
print("F2b: rule_id corrupto (no string) -> identidad")
regla = dict(REGLA_SANA); regla["rule_id"] = 12345
m = _motor({RF: {"version": "2.0", "rules": [dict(REGLA_SANA), regla]}})
print("  claves de adaptation_rules:", sorted(map(str, m.adaptation_rules.keys())))
for rid, r in m.adaptation_rules.items():
    print("  %-14r rule_id=%r name=%r" % (rid, r.rule_id, r.name))

print("=" * 74)
print("F3: KB con feedback valido + FB con fila invalida -> ¿se pierde el valido?")
FB_OK = {"adaptation_id": "fb_kb", "success": True, "adaptation_context": {},
         "execution_result": {}, "verification_result": {}, "improvement_analysis": {},
         "timestamp": "2024-01-01T00:00:00"}
m = _motor({KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_OK)]}},
            FB: {"goal_adaptation_feedback": [{"adaptation_id": 999, "success": "no bool"}],
                 "adaptation_history": []}})
print("  goal_adaptation_feedback:", json.dumps(m.knowledge_base.get("goal_adaptation_feedback"), default=str)[:200])

print("=" * 74)
print("F3b: KB con learning_results valido + LR con learning_results vacio")
LR_ROW = {"adaptation_id": "lr_kb", "learned_patterns": [], "updated_strategies": {},
          "convergence_metrics": {}}
m = _motor({KB: {"version": "2.0", "data": {"learning_results": [dict(LR_ROW)]}},
            LR: {"learning_results": [], "adaptation_strategies": {}}})
print("  learning_results:", json.dumps(m.knowledge_base.get("learning_results"), default=str)[:200])
