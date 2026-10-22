#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Segunda tanda de hallazgos de 2.8.8.9.8.4: colision de identidad y
inconsistencia entre la via LISTA y la via de CONTENEDOR de las reglas."""

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
            h.write(contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False))
    return ContextualAdaptationEngine(data_dir=data_dir)


def _titulo(t):
    print("=" * 72)
    print(t)


def e1_colision_identidad_inventada():
    """DOS filas con `rule_id` no-string: ambas se registran con la identidad
    INVENTADA None -> la segunda SOBREESCRIBE a la primera."""
    _titulo("E1: dos filas con rule_id no-string (colision de identidad)")
    a = dict(REGLA_SANA); a["rule_id"] = 111; a["name"] = "primera"
    b = dict(REGLA_SANA); b["rule_id"] = 222; b["name"] = "segunda"
    motor = _motor({RF: {"version": "2.0", "rules": [a, b]}})
    print("  reglas registradas:", list(motor.adaptation_rules))
    for rid, r in motor.adaptation_rules.items():
        print("   ", repr(rid), "name=", repr(r.name), "description=", repr(r.description))
    print("  filas del fichero: 2 ; reglas en el estado:",
          len(motor.adaptation_rules))
    print("  unidades cargadas:", motor._unidades_cargadas.get("adaptation_rules"))
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:400])


def e2_via_lista_vs_via_contenedor():
    """La MISMA fila corrupta: por la via LISTA se registra (identidad
    inventada); por la via de CONTENEDOR se descarta."""
    _titulo("E2: la misma fila corrupta por la via LISTA y por la via de CONTENEDOR")
    a = dict(REGLA_SANA); a["rule_id"] = 111; a["name"] = "primera"
    b = dict(REGLA_SANA); b["rule_id"] = 222; b["name"] = "segunda"
    motor_lista = _motor({RF: {"version": "2.0", "rules": [a, b]}})
    motor_cont = _motor({RF: {"version": "2.0", "rules": {"k1": a, "k2": b}}})
    print("  via LISTA     -> reglas:", list(motor_lista.adaptation_rules),
          "nombres:", [r.name for r in motor_lista.adaptation_rules.values()])
    print("  via CONTENEDOR-> reglas:", list(motor_cont.adaptation_rules),
          "nombres:", [r.name for r in motor_cont.adaptation_rules.values()])
    print("  informe lista:", json.dumps(motor_lista.recovery_report(), ensure_ascii=False, default=str)[:200])
    print("  informe cont :", json.dumps(motor_cont.recovery_report(), ensure_ascii=False, default=str)[:200])


def e3_name_corrupto_con_rule_id_corrupto():
    """`name` y `rule_id` ambos corruptos: el nombre se resuelve con la
    identidad INVENTADA (None)."""
    _titulo("E3: name y rule_id corruptos a la vez")
    a = dict(REGLA_SANA); a["rule_id"] = 111; a["name"] = 999
    motor = _motor({RF: {"version": "2.0", "rules": [a]}})
    for rid, r in motor.adaptation_rules.items():
        print("   id=", repr(rid), "name=", repr(r.name))
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:400])


def e4_contrato_row_missing_identity():
    """El contrato declarado dice: sin identidad la fila NO se registra y no
    se inventa una. Se comprueba lo que hace el runtime."""
    _titulo("E4: contrato declarado de `adaptation_rules.row_missing_identity`")
    motor = _motor({RF: {"version": "2.0", "rules": [dict(REGLA_SANA)]}})
    contrato = motor._RECOVERABLE_DATA["files"]["adaptation_rules"]["classes"]
    print("  clase declarada:", json.dumps(contrato["adaptation_rules.row_missing_identity"],
                                            ensure_ascii=False))
    print("  politica:", contrato["adaptation_rules.row_missing_identity"]["policy"])
    print("  recovers:", contrato["adaptation_rules.row_missing_identity"]["recovers"])
    print("  nota:", contrato["adaptation_rules.row_missing_identity"]["note"])


def e5_invariante_field_defaults():
    """`field_defaults` no declara `condition_pattern`: la recuperacion usa
    None, que no es el valor por defecto que usa el CARGADOR ("")."""
    _titulo("E5: field_defaults y los valores por defecto del CARGADOR")
    motor = _motor({RF: {"version": "2.0", "rules": [dict(REGLA_SANA)]}})
    fd = motor._RECOVERABLE_DATA.get("field_defaults", {})
    formato = motor._campos_de_formato("adaptation_rules")
    print("  campos del FORMATO REAL:", sorted(formato))
    print("  declarados en field_defaults:", sorted(fd))
    print("  en formato y SIN default declarado:",
          sorted(set(formato) - set(fd) - {"rule_id"}))
    print("  default del CARGADOR para condition_pattern: \"\" (row.get(..., \"\"))")


if __name__ == "__main__":
    e1_colision_identidad_inventada()
    e2_via_lista_vs_via_contenedor()
    e3_name_corrupto_con_rule_id_corrupto()
    e4_contrato_row_missing_identity()
    e5_invariante_field_defaults()
