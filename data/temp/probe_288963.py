#!/usr/bin/env python3
"""Sonda de diagnostico: estado observable tras la DETECCION (2.8.8.9.6.3)."""
import importlib.util, json, os, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

ruta = os.path.join(ROOT, "tests", "utils", "contextual_adaptation_engine", "corruption_criteria_real.py")
spec = importlib.util.spec_from_file_location("ccr", ruta)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
CASES = m.CASES

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

OBJETIVO = [
    "adaptation_rules.actions_string", "adaptation_rules.enabled_string",
    "adaptation_rules.last_execution_not_iso", "adaptation_rules.name_not_string",
    "adaptation_rules.success_rate_not_numeric", "adaptation_rules.threshold_not_numeric",
    "adaptation_rules.trigger_invalid_value", "adaptation_rules.triggers_not_list",
    "goal_adaptation_feedback.row_not_mapping", "goal_adaptation_feedback.section_not_list",
    "goal_adaptation_learning_results.learning_results_not_list",
    "goal_adaptation_learning_results.row_not_mapping",
    "goal_adaptation_learning_results.strategy_missing_identity",
    "knowledge_base.section_not_mapping", "knowledge_base.section_partial",
    "knowledge_base.strategies_not_mapping", "knowledge_base.unexpected_key",
]

for cid in OBJETIVO:
    caso = CASES[cid]
    tmp = tempfile.mkdtemp(prefix="diag_")
    dd = os.path.join(tmp, "data"); os.makedirs(dd, exist_ok=True)
    for nombre, contenido in caso["files"]().items():
        with open(os.path.join(dd, nombre), "w", encoding="utf-8") as h:
            h.write(contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False))
    eng = ContextualAdaptationEngine(data_dir=dd)
    print("=" * 70)
    print(cid)
    print("  rules keys      :", sorted(eng.adaptation_rules.keys()))
    bad = eng.adaptation_rules.get("bad1")
    if bad is not None:
        print("  bad1            :", {k: getattr(bad, k, None) for k in
              ("name", "enabled", "adaptation_actions", "context_triggers", "confidence_threshold",
               "success_rate", "last_execution")})
    kb = eng.knowledge_base
    print("  kb.context_patterns prod:", repr(kb.get("context_patterns", {}).get("production"))[:90])
    print("  kb.adaptation_strategies prod:", repr(kb.get("adaptation_strategies", {}).get("production"))[:90])
    print("  kb.adaptation_strategies idle:", repr(kb.get("adaptation_strategies", {}).get("idle"))[:90])
    print("  kb.goal_adaptation_feedback:", repr(kb.get("goal_adaptation_feedback"))[:90])
    print("  kb.learning_results:", repr(kb.get("learning_results"))[:90])
    print("  kb.clave_desconocida present:", "clave_desconocida" in kb)
    try:
        s = eng.get_available_strategies(ContextType.PRODUCTION)
        print("  strategies(PRODUCTION) n=", len(s), "conf=", [x.get("confidence") for x in s][:3])
    except Exception as exc:
        print("  strategies(PRODUCTION) RAISES:", type(exc).__name__, exc)
    try:
        s = eng.get_available_strategies(ContextType.IDLE)
        print("  strategies(IDLE) n=", len(s), "conf=", [x.get("confidence") for x in s][:3])
    except Exception as exc:
        print("  strategies(IDLE) RAISES:", type(exc).__name__, exc)
    try:
        eng._capture_feedback({"adaptation_id": "a1"})
        print("  _capture_feedback: OK")
    except Exception as exc:
        print("  _capture_feedback RAISES:", type(exc).__name__, exc)
    print("  load_adaptation_rules ->", eng.load_adaptation_rules())
    print("  load_knowledge_base   ->", eng.load_knowledge_base())
    eng._save_goal_adaptation_learning_results()
    p = os.path.join(dd, "goal_adaptation_learning_results.json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as h:
            g = json.load(h)
        print("  guardado learning_results:", repr(g.get("learning_results"))[:90])
        print("  guardado adaptation_strategies idle:", repr(g.get("adaptation_strategies", {}).get("idle"))[:90])
