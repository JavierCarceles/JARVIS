#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXPLORACION: comportamiento REAL ante perdida TOTAL de datos."""
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa

RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"


def motor(data_dir):
    return ContextualAdaptationEngine(data_dir=data_dir)


def volcar(tag, m):
    print("=" * 70)
    print(tag)
    print("  adaptation_rules:", sorted(m.adaptation_rules.keys()))
    print("  kb keys:", len(m.knowledge_base))
    print("  kb context_patterns:", m.knowledge_base.get("context_patterns"))
    print("  kb goal_adaptation_feedback:", m.knowledge_base.get("goal_adaptation_feedback"))
    print("  kb learning_results:", m.knowledge_base.get("learning_results"))
    print("  adaptation_history:", len(m.adaptation_history))
    print("  recovery_report:", m.recovery_report())


# --- CASO 1: los 4 ficheros CORRUPTOS (JSON ilegible) ------------------------
d1 = tempfile.mkdtemp()
for name in (RF, KB, FB, LR):
    with open(os.path.join(d1, name), "w", encoding="utf-8") as h:
        h.write("{ESTO NO ES JSON")
try:
    m1 = motor(d1)
    print("CASO 1 arranque: NO lanza")
    volcar("CASO 1 - 4 ficheros ilegibles", m1)
    print("  load_adaptation_rules():", m1.load_adaptation_rules())
    print("  load_knowledge_base():", m1.load_knowledge_base())
    print("  load_all_data():", m1.load_all_data())
    st = m1.get_engine_status()
    print("  status.corruption:", json.dumps(st["corruption"], ensure_ascii=False)[:400])
    print("  status.storage:", st["storage"])
    print("  status.total_rules:", st["total_rules"])
    print("  detect_corruption().unreadable:", list(st and m1.detect_corruption()["unreadable"].keys()))
    print("  detect_corruption().missing_files:", m1.detect_corruption()["missing_files"])
except Exception as exc:
    print("CASO 1 arranque: LANZA", type(exc).__name__, exc)

# --- CASO 2: los 4 ficheros AUSENTES ----------------------------------------
d2 = tempfile.mkdtemp()
try:
    m2 = motor(d2)
    print("CASO 2 arranque: NO lanza")
    volcar("CASO 2 - 4 ficheros ausentes", m2)
except Exception as exc:
    print("CASO 2 arranque: LANZA", type(exc).__name__, exc)

# --- CASO 3: raiz JSON que no es la esperada (lista/dict equivocado) ---------
d3 = tempfile.mkdtemp()
with open(os.path.join(d3, RF), "w", encoding="utf-8") as h:
    json.dump(["no", "es", "el", "formato"], h)
with open(os.path.join(d3, KB), "w", encoding="utf-8") as h:
    json.dump({"data": ["no", "es", "un", "mapeo"]}, h)
with open(os.path.join(d3, FB), "w", encoding="utf-8") as h:
    json.dump(["no", "es", "un", "mapeo"], h)
with open(os.path.join(d3, LR), "w", encoding="utf-8") as h:
    json.dump(["no", "es", "un", "mapeo"], h)
try:
    m3 = motor(d3)
    print("CASO 3 arranque: NO lanza")
    volcar("CASO 3 - raiz con forma distinta", m3)
except Exception as exc:
    print("CASO 3 arranque: LANZA", type(exc).__name__, exc)

# --- CASO 4: hay una API que INFORME de la perdida total? --------------------
print("=" * 70)
print("APIs que mencionen 'total' o 'perdida':")
for nombre in dir(m1):
    if "total" in nombre.lower() or "perdida" in nombre.lower() or "fallback" in nombre.lower():
        print("   ", nombre)
print("recovery_report() con 4 ficheros ilegibles:", m1.recovery_report())
