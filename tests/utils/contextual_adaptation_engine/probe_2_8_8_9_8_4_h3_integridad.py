#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprobaciones de integridad de 2.8.8.9.8.4: excepcion exacta de H1 y
NO-REESCRITURA de los ficheros de persistencia originales."""

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

KB = "contextual_knowledge_base.json"
RF = "contextual_adaptation_rules.json"


def _motor(ficheros):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as h:
            h.write(json.dumps(contenido, ensure_ascii=False))
    return ContextualAdaptationEngine(data_dir=data_dir), data_dir


def h1_excepcion_exacta():
    print("=" * 72)
    print("H1: excepcion exacta de _recuperar_grupos_de_base")
    motor, _ = _motor({KB: {"version": "2.0", "data": {"learning_results": {"no": "es una lista"}}}})
    try:
        motor._recuperar_grupos_de_base("learning_results", {"no": "es una lista"})
        print("  sin excepcion")
    except Exception as exc:
        print("  EXCEPCION:", type(exc).__name__, "-", exc)


def h1_perdida_de_hermanos_sanos():
    print("=" * 72)
    print("H1: hermanos sanos del MISMO fichero tras una seccion corrupta")
    motor, _ = _motor({KB: {"version": "2.0", "data": {
        "learning_results": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
    }}})
    print("  context_patterns.production:", motor.knowledge_base.get("context_patterns", {}).get("production"))
    print("  unidades cargadas KB:", motor._unidades_cargadas.get("knowledge_base"))
    print("  load_knowledge_base() devolvio:", motor.load_knowledge_base())


def no_reescritura_de_ficheros():
    print("=" * 72)
    print("NO-REESCRITURA: sha256 de los ficheros antes y despues de cargar")
    contenido_kb = {"version": "2.0", "data": {
        "learning_results": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
    }}
    contenido_rf = {"version": "2.0", "rules": [{"rule_id": 111, "name": "x"}]}
    motor, data_dir = _motor({KB: contenido_kb, RF: contenido_rf})
    antes = {n: hashlib.sha256(open(os.path.join(data_dir, n), "rb").read()).hexdigest()
             for n in (KB, RF)}
    motor.load_all_data()
    despues = {n: hashlib.sha256(open(os.path.join(data_dir, n), "rb").read()).hexdigest()
               for n in (KB, RF)}
    for n in antes:
        print(f"  {n}: intacto={antes[n] == despues[n]}")


if __name__ == "__main__":
    h1_excepcion_exacta()
    h1_perdida_de_hermanos_sanos()
    no_reescritura_de_ficheros()
