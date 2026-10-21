# -*- coding: utf-8 -*-
"""Sonda exploratoria: comportamiento REAL ante perdida total de datos."""
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


def construir(data_dir, contenido):
    os.makedirs(data_dir, exist_ok=True)
    for nombre in STORAGE:
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as h:
            h.write(contenido)
    return ContextualAdaptationEngine(data_dir=data_dir)


def main():
    tmp = tempfile.mkdtemp(prefix="probe_total_loss_")
    data_dir = os.path.join(tmp, "data")

    # --- CASO A: los 4 ficheros ILEGIBLES (corrupcion total) ---------------
    motor = construir(data_dir, CORRUPT)
    print("== CASO A: 4 ficheros ILEGIBLES ==")
    print("  arranque: NO lanza")
    print("  adaptation_rules:", sorted(motor.adaptation_rules))
    print("  knowledge_base claves:", len(motor.knowledge_base))
    status = motor.get_engine_status()
    print("  status.corruption:", json.dumps(status.get("corruption"), ensure_ascii=False))
    print("  status.storage.absent_count:", status["storage"]["absent_count"])
    print("  status.storage_sections.absent_count:", status["storage_sections"]["absent_count"])
    print("  status.total_rules:", status["total_rules"])
    print("  status.total_adaptations:", status["total_adaptations"])
    det = motor.detect_corruption()
    print("  detect_corruption.corrupted:", list(det["corrupted"]))
    print("  detect_corruption.unreadable:", list(det["unreadable"]))
    print("  detect_corruption.corruption_count:", det["corruption_count"])
    print("  detect_corruption.has_corruption:", det["has_corruption"])
    print("  detect_corruption.missing_files:", det["missing_files"])
    print("  load_adaptation_rules():", motor.load_adaptation_rules())
    print("  load_knowledge_base():", motor.load_knowledge_base())
    print("  load_all_data():", motor.load_all_data())
    print("  recovery_report().count:", motor.recovery_report()["count"])
    print("  read APIs ->",
          type(motor.get_adaptation_summary()).__name__,
          type(motor.get_context_insights()).__name__,
          type(motor.get_adaptation_rules()).__name__,
          type(motor.list_adaptation_rules()).__name__,
          type(motor.get_available_strategies(motor.current_context.context_type
                                              if motor.current_context else list(motor.knowledge_base["context_patterns"])[0])).__name__)

    # --- CASO B: los 4 ficheros CON CONTENIDO pero TODOS corruptos segun formato
    print()
    print("== CASO B: 4 ficheros con payload NO MAPA (corrupcion de contenido) ==")
    tmp2 = tempfile.mkdtemp(prefix="probe_total_loss2_")
    data_dir2 = os.path.join(tmp2, "data")
    os.makedirs(data_dir2, exist_ok=True)
    for nombre in STORAGE:
        with open(os.path.join(data_dir2, nombre), "w", encoding="utf-8") as h:
            json.dump({"rules": "no soy una lista", "data": "no soy un mapa"}, h)
    motor2 = ContextualAdaptationEngine(data_dir=data_dir2)
    print("  adaptation_rules:", sorted(motor2.adaptation_rules))
    print("  knowledge_base claves:", len(motor2.knowledge_base))
    st2 = motor2.get_engine_status()
    print("  status.corruption.corruption_count:", st2["corruption"]["corruption_count"])
    print("  detect_corruption.corrupted:", {k: len(v) for k, v in motor2.detect_corruption()["corrupted"].items()})
    print("  recovery_report().count:", motor2.recovery_report()["count"])
    print("  recovery_report().files:", motor2.recovery_report()["files"])

    # --- CASO C: escritura tras la perdida total ---------------------------
    print()
    print("== CASO C: escritura tras la perdida total ==")
    antes = open(os.path.join(data_dir, "contextual_adaptation_rules.json"), encoding="utf-8").read()
    ok = motor.save_all_data()
    despues = open(os.path.join(data_dir, "contextual_adaptation_rules.json"), encoding="utf-8").read()
    print("  save_all_data():", ok)
    print("  fichero ANTES era ilegible:", antes == CORRUPT)
    print("  fichero DESPUES parseable:", json.loads(despues).keys())
    print("  nº de reglas escritas:", len(json.loads(despues)["rules"]))
    print("  se han sobrescrito datos corruptos (no recuperables):", True)

    # --- CASO D: hay backup? ------------------------------------------------
    print()
    print("== CASO D: mecanismos de respaldo existentes ==")
    print("  backup_data disponible:", hasattr(motor, "backup_data"))
    print("  metodos con 'restore':", [m for m in dir(motor) if "restore" in m.lower() or "recover" in m.lower()])
    print("  metodos con 'backup':", [m for m in dir(motor) if "backup" in m.lower()])
    print("  metodos con 'export':", [m for m in dir(motor) if "export" in m.lower() or "import" in m.lower()])


if __name__ == "__main__":
    main()
