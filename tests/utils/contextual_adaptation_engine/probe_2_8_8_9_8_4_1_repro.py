#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de REPRODUCCION del defecto de 2.8.8.9.8.4.1.

Muestra que una SECCION LIST de la base de conocimiento que llega como
DICCIONARIO hace que `_recuperar_grupos_de_base` lance `AttributeError` y que
la EXCEPCION aborte la carga de las secciones SANAS del MISMO fichero.
"""

import json
import os
import sys
import tempfile
import traceback

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402

KB = "contextual_knowledge_base.json"


def _motor(contenido):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, KB), "w", encoding="utf-8") as h:
        json.dump(contenido, h, ensure_ascii=False)
    return ContextualAdaptationEngine(data_dir=data_dir)


def escenario(nombre, data):
    print("=" * 72)
    print(nombre)
    motor = _motor({"version": "2.0", "data": data})
    try:
        ok = motor.load_knowledge_base()
        print("  load_knowledge_base ->", ok)
    except Exception:
        print("  EXCEPCION PROPAGADA:")
        traceback.print_exc()
        ok = "excepcion"
    kb = motor.knowledge_base
    print("  context_patterns:", json.dumps(kb.get("context_patterns"), ensure_ascii=False, default=str)[:150])
    print("  success_patterns:", json.dumps(kb.get("success_patterns"), ensure_ascii=False, default=str)[:150])
    print("  learning_results:", json.dumps(kb.get("learning_results"), ensure_ascii=False, default=str)[:150])
    print("  unidades cargadas KB:", motor._unidades_cargadas.get("knowledge_base"))
    print("  informe:", json.dumps(motor.recovery_report(), ensure_ascii=False, default=str)[:400])
    return motor


if __name__ == "__main__":
    escenario("A: learning_results (seccion LIST) llega como DICCIONARIO", {
        "learning_results": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
        "success_patterns": {"production": [{"patron": "sano"}]},
    })
    escenario("B: goal_adaptation_feedback (seccion LIST) llega como DICCIONARIO", {
        "goal_adaptation_feedback": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
    })
    escenario("C: control: seccion LIST SANA (no hay corrupcion)", {
        "learning_results": [{"adaptation_id": "lr_ok"}],
        "context_patterns": {"production": [{"patron": "sano"}]},
    })
    escenario("D: control: seccion MAPEADA corrupta (grupo invalido)", {
        "context_patterns": {"production": {"no": "es una lista"}},
        "success_patterns": {"production": [{"patron": "sano"}]},
    })
