# -*- coding: utf-8 -*-
"""Sonda exploratoria 3: hechos precisos del fallback ante perdida total."""
import json
import logging
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
logging.disable(logging.CRITICAL)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine

STORAGE = ["goal_adaptation_feedback.json", "goal_adaptation_learning_results.json",
           "contextual_adaptation_rules.json", "contextual_knowledge_base.json"]
CORRUPT = "{ this is not json ]]"


def scenario(nombre, contenido):
    tmp = tempfile.mkdtemp(prefix="probe3_")
    d = os.path.join(tmp, "data")
    os.makedirs(d, exist_ok=True)
    for n in STORAGE:
        with open(os.path.join(d, n), "w", encoding="utf-8") as h:
            h.write(contenido(n))
    return ContextualAdaptationEngine(data_dir=d), d


def main():
    # --- CASO 1: los 4 ficheros ILEGIBLES ---------------------------------
    m, d = scenario("ilegible", lambda n: CORRUPT)
    print("== CASO 1: 4 ficheros ILEGIBLES ==")
    print("  load_adaptation_rules():", m.load_adaptation_rules())
    print("  load_knowledge_base():", m.load_knowledge_base())
    print("  load_all_data():", m.load_all_data())
    st = m.get_engine_status()
    print("  status.corruption:", json.dumps(st["corruption"], ensure_ascii=False))
    print("  status.storage.absent_count:", st["storage"]["absent_count"])
    print("  status.storage_sections.absent_count:", st["storage_sections"]["absent_count"])
    print("  detect_corruption().unreadable:", sorted(m.detect_corruption()["unreadable"]))
    print("  detect_corruption().has_corruption:", m.detect_corruption()["has_corruption"])
    print("  detect_corruption().corruption_count:", m.detect_corruption()["corruption_count"])
    print("  recovery_report().count:", m.recovery_report()["count"])
    print("  keys de status:", sorted(st.keys()))
    print("  status NO expone unreadable:", "unreadable" not in json.dumps(st))
    print("  rules:", sorted(m.adaptation_rules), "kb keys:", len(m.knowledge_base))

    # --- CASO 2: los 4 ficheros AUSENTES ----------------------------------
    tmp = tempfile.mkdtemp(prefix="probe3_abs_")
    d2 = os.path.join(tmp, "data")
    m2 = ContextualAdaptationEngine(data_dir=d2)
    print()
    print("== CASO 2: 4 ficheros AUSENTES ==")
    st2 = m2.get_engine_status()
    print("  status.corruption:", json.dumps(st2["corruption"], ensure_ascii=False))
    print("  status.storage.absent_count:", st2["storage"]["absent_count"])
    print("  detect_corruption().unreadable:", sorted(m2.detect_corruption()["unreadable"]))
    print("  detect_corruption().missing_files:", sorted(m2.detect_corruption()["missing_files"]))
    print("  rules:", sorted(m2.adaptation_rules), "kb keys:", len(m2.knowledge_base))
    print("  MISMA firma de reglas/kb que el caso 1:",
          (sorted(m.adaptation_rules), sorted(m2.adaptation_rules)) ==
          (sorted(m2.adaptation_rules), sorted(m.adaptation_rules)))
    print("  -> la AUSENCIA es VISIBLE en status (absent_count=4); la CORRUPCION TOTAL NO")

    # --- CASO 3: JSON valido pero payload que no es mapeo -----------------
    m3, d3 = scenario("no_mapeo", lambda n: '"una cadena"')
    print()
    print("== CASO 3: 4 ficheros con payload NO MAPEABLE ==")
    print("  detect_corruption().unreadable:", sorted(m3.detect_corruption()["unreadable"]))
    print("  detect_corruption().corrupted:", json.dumps(m3.detect_corruption()["corrupted"], ensure_ascii=False)[:200])
    print("  detect_corruption().corruption_count:", m3.detect_corruption()["corruption_count"])
    print("  detect_corruption().has_corruption:", m3.detect_corruption()["has_corruption"])
    print("  status.corruption.corruption_count:", m3.get_engine_status()["corruption"]["corruption_count"])
    print("  rules:", sorted(m3.adaptation_rules))
    print("  recovery_report().count:", m3.recovery_report()["count"])

    # --- CASO 4: el motor puede seguir operando tras la perdida total -----
    print()
    print("== CASO 4: el motor sigue operativa ==")
    snap = m.capture_context_snapshot()
    print("  capture_context_snapshot():", snap is not None)
    print("  analyze_contextual_patterns():", len(m.analyze_contextual_patterns(snap)))
    print("  get_adaptation_rules():", len(m.get_adaptation_rules()))
    print("  get_available_strategies():", len(m.get_available_strategies()))
    print("  get_context_insights():", sorted(m.get_context_insights().keys())[:5])
    print("  get_adaptation_summary():", json.dumps(m.get_adaptation_summary(), ensure_ascii=False)[:80])

    # --- CASO 5: backup_data no es un fallback utilizable ------------------
    print()
    print("== CASO 5: backup_data() ==")
    print("  backup_data() copia:", sorted(os.listdir(os.path.join(d, "backups"))))
    print("  backup contiene el CONTENIDO CORRUPTO:",
          all(CORRUPT in open(os.path.join(d, "backups", b), encoding="utf-8").read()
              for b in os.listdir(os.path.join(d, "backups"))))
    print("  backup NO cubre feedback/learning_results:",
          not any("feedback" in b or "learning" in b for b in os.listdir(os.path.join(d, "backups"))))
    print("  no hay API de restauracion:",
          not [x for x in dir(m) if "restor" in x.lower() or "recover_from" in x.lower()])


if __name__ == "__main__":
    main()
