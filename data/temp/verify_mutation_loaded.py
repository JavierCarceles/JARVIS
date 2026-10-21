#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica que la MUTACION en el fichero llega al modulo importado."""
import importlib.util
import inspect
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE = os.path.join(ROOT, "src", "utils", "contextual_adaptation_engine.py")
PROBE_PATH = os.path.join(ROOT, "tests", "utils", "contextual_adaptation_engine",
                          "corruption_criteria_real.py")

ANTES = ('        if not isinstance(fila, dict): return False\n'
         '        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {})'
         '.get("real_format", {}) or {}')
DESPUES = ('        if not isinstance(fila, dict): return False\n'
           '        if True: return True\n'
           '        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {})'
           '.get("real_format", {}) or {}')

with open(ENGINE, "r", encoding="utf-8") as handle:
    original = handle.read()
assert ANTES in original
try:
    with open(ENGINE, "w", encoding="utf-8") as handle:
        handle.write(original.replace(ANTES, DESPUES, 1))
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    print("--- fuente de _fila_valida tal y como se importa ---")
    print(inspect.getsource(ContextualAdaptationEngine._fila_valida))
    print("--- modulo cargado desde ---")
    print(ContextualAdaptationEngine.__module__,
          sys.modules[ContextualAdaptationEngine.__module__].__file__)

    spec = importlib.util.spec_from_file_location("sonda", PROBE_PATH)
    sonda = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sonda)
    caso = sonda.CASES["goal_adaptation_feedback.row_not_mapping"]
    tmp = tempfile.mkdtemp(prefix="verif_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in caso["files"]().items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as handle:
            handle.write(contenido if isinstance(contenido, str)
                         else json.dumps(contenido, ensure_ascii=False))
    motor = ContextualAdaptationEngine(data_dir=data_dir)
    print("--- estado feedback ---")
    print(motor.knowledge_base.get("goal_adaptation_feedback"))
    print("--- observado ---")
    print(sorted(caso["observe"](motor)))
finally:
    with open(ENGINE, "w", encoding="utf-8") as handle:
        handle.write(original)
    print("--- fichero restaurado ---")
