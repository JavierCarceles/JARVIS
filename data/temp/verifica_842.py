#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificacion rapida de 2.8.8.9.8.4.2 (identidad inventada / colision)."""

import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402

RF = "contextual_adaptation_rules.json"

SANA = {
    "rule_id": "rr_sana_1", "name": "sana 1", "description": "d",
    "condition_pattern": "p", "adaptation_actions": ["a"], "context_triggers": ["production"],
    "confidence_threshold": 0.7, "priority": 1, "enabled": True, "success_rate": 0.5,
    "execution_count": 1, "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}


def motor(reglas):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, RF), "w", encoding="utf-8") as h:
        json.dump({"version": "2.0", "rules": reglas}, h, ensure_ascii=False)
    return ContextualAdaptationEngine(data_dir=data_dir)


def caso(titulo, reglas):
    m = motor(reglas)
    print("==", titulo)
    print("   reglas:", sorted(m.adaptation_rules))
    print("   unidades cargadas:", m._unidades_cargadas.get("adaptation_rules"))
    print("   nombres:", [r.name for r in m.adaptation_rules.values()])
    print("   informe:", json.dumps(m.recovery_report(), ensure_ascii=False, default=str)[:300])
    print()


caso("E1 LISTA: dos filas con rule_id no-string + dos sanas",
     [dict(SANA), dict(SANA, rule_id=111, name="primera"),
      dict(SANA, rule_id=222, name="segunda"), dict(SANA, rule_id="rr_sana_3", name="tercera")])

caso("E2 CONTENEDOR: el mismo contenido en forma de mapeo",
     {"k1": dict(SANA), "k2": dict(SANA, rule_id=111, name="primera"),
      "k3": dict(SANA, rule_id=222, name="segunda"), "k4": dict(SANA, rule_id="rr_sana_3", name="tercera")})

caso("COLISION: dos filas con la MISMA identidad valida",
     [dict(SANA, name="primera"), dict(SANA, name="segunda")])

caso("E3: name y rule_id corruptos a la vez",
     [dict(SANA, rule_id=111, name=999), dict(SANA, rule_id="rr_sana_3")])

caso("LISTA vs CONTENEDOR: paridad con la MISMA fila",
     [dict(SANA, rule_id=111, name="x"), dict(SANA, rule_id="rr_sana_3")])
