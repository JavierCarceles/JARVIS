# -*- coding: utf-8 -*-
"""Sonda exploratoria 2: hechos observables ante perdida total de datos."""
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


def motor_con(data_dir):
    return ContextualAdaptationEngine(data_dir=data_dir)


def firma(m):
    return {
        "rules": sorted(m.adaptation_rules),
        "kb_keys": sorted(m.knowledge_base),
        "kb": json.dumps(m.knowledge_base, sort_keys=True, default=str),
        "hist": len(m.adaptation_history),
        "transfers": len(m.knowledge_transfers),
    }


def main():
    # --- Motor NUEVO (sin ficheros): la referencia de "sin datos" ------------
    tmp0 = tempfile.mkdtemp(prefix="probe2_ref_")
    ref = motor_con(os.path.join(tmp0, "data"))
    print("== REFERENCIA: motor sin ningun fichero ==")
    print("  rules:", sorted(ref.adaptation_rules))
    print("  kb_keys:", len(ref.knowledge_base))
    print("  status.corruption:", json.dumps(ref.get_engine_status()["corruption"], ensure_ascii=False))
    print("  status.storage.absent_count:", ref.get_engine_status()["storage"]["absent_count"])

    # --- Motor con 4 ficheros ILEGIBLES -------------------------------------
    tmp = tempfile.mkdtemp(prefix="probe2_loss_")
    d = os.path.join(tmp, "data")
    os.makedirs(d, exist_ok=True)
    for n in STORAGE:
        with open(os.path.join(d, n), "w", encoding="utf-8") as h:
            h.write(CORRUPT)
    m = motor_con(d)
    print()
    print("== PERDIDA TOTAL (4 ilegibles) ==")
    print("  MISMA firma que el motor sin ficheros:",
          firma(m) == firma(ref))
    st = m.get_engine_status()
    print("  status.corruption:", json.dumps(st["corruption"], ensure_ascii=False))
    print("  status.storage:", json.dumps(st["storage"], ensure_ascii=False)[:120])
    print("  status.storage_sections.absent_count:", st["storage_sections"]["absent_count"])
    print("  detect_corruption.unreadable:", list(m.detect_corruption()["unreadable"]))
    print("  detect_corruption.corrupted:", m.detect_corruption()["corrupted"])
    print("  detect_absent_storage.present:", m.detect_absent_storage()["present"])
    print("  detect_absent_sections.unreadable:", list(m.detect_absent_sections()["unreadable"]))
    print("  detect_absent_sections.absent:", m.detect_absent_sections()["absent"])
    print("  recovery_report:", json.dumps(m.recovery_report(), ensure_ascii=False))
    print("  active_modes:", st["active_modes"])
    print("  NO hay API de 'perdida total':",
          [m2 for m2 in dir(m) if "total_loss" in m2 or "fallback" in m2 or "degrad" in m2])

    # --- backup_data con fichero corrupto -----------------------------------
    print()
    print("== backup_data() con fichero corrupto ==")
    ok = m.backup_data()
    backups = os.listdir(os.path.join(d, "backups")) if os.path.isdir(os.path.join(d, "backups")) else []
    print("  backup_data():", ok, "->", backups)
    print("  el backup contiene el contenido CORRUPTO:",
          any(CORRUPT in open(os.path.join(d, "backups", b), encoding="utf-8").read() for b in backups))
    print("  hay API de restauracion en el motor:",
          [x for x in dir(m) if "restor" in x.lower()])

    # --- escritura tras la perdida total ------------------------------------
    print()
    print("== escritura tras la perdida total ==")
    m.save_all_data()
    with open(os.path.join(d, "contextual_adaptation_rules.json"), encoding="utf-8") as h:
        nuevo = json.load(h)
    print("  reglas escritas:", len(nuevo["rules"]), "(las BUILTIN)")
    print("  el contenido corrupto se ha SOBRESCRITO: no queda rastro")

    # --- el motor sigue PODIENDO operar -------------------------------------
    print()
    print("== el motor sigue operando ==")
    snap = m.capture_context_snapshot()
    print("  capture_context_snapshot():", snap.snapshot_id is not None)
    reglas = m.analyze_contextual_patterns(snap)
    print("  analyze_contextual_patterns():", len(reglas), "reglas aplicables")
    print("  get_engine_status() no lanza: OK")
    print("  get_adaptation_summary():", json.dumps(m.get_adaptation_summary(), ensure_ascii=False)[:100])


if __name__ == "__main__":
    main()
