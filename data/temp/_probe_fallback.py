#!/usr/bin/env python3
import os, sys, json, hashlib, tempfile, shutil, logging
sys.path.insert(0, "src")
logging.getLogger().setLevel(logging.CRITICAL + 1)
from utils.contextual_adaptation_engine import ContextualAdaptationEngine

FILES = ["goal_adaptation_feedback.json","goal_adaptation_learning_results.json","contextual_adaptation_rules.json","contextual_knowledge_base.json"]

def sha(p):
    if not os.path.isfile(p): return None
    return hashlib.sha256(open(p,'rb').read()).hexdigest()

def scenario(mode):
    return {
        "unreadable_file": "no es json <<< roto >>>",
        "non_mapping_root": "[42, 13]",
        "list_root_without_valid_rows": "[]",
        "empty_mapping_root": "{}",
    }[mode]

def measure(mode):
    d = tempfile.mkdtemp()
    for f in FILES:
        open(os.path.join(d,f),"w").write(scenario(mode))
    before = {f: sha(os.path.join(d,f)) for f in FILES}
    motor = ContextualAdaptationEngine(data_dir=d)
    load_result = motor.load_all_data()
    status = motor.get_engine_status()
    corr = status.get("corruption") or {}
    after = {f: sha(os.path.join(d,f)) for f in FILES}
    intact = before == after
    d2 = tempfile.mkdtemp()
    fresh = ContextualAdaptationEngine(data_dir=d2)
    reglas_iguales = sorted((motor.adaptation_rules or {}).keys()) == sorted((fresh.adaptation_rules or {}).keys())
    kb_igual = json.dumps(motor.knowledge_base, default=str, sort_keys=True) == json.dumps(fresh.knowledge_base, default=str, sort_keys=True)
    try:
        snap = motor.capture_context_snapshot(); rules = motor.analyze_contextual_patterns(snap); res = motor.execute_adaptation(snap, rules); op_ok = res is not None
    except Exception as e:
        op_ok = False
    backup_ok = motor.backup_data()
    # backup covers
    respaldos = set(os.listdir(os.path.join(d,"backups")) if os.path.isdir(os.path.join(d,"backups")) else [])
    keys = list(motor.expected_storage_paths())
    backup_covers = all(any(n.startswith(k+"_backup_") for n in respaldos) for k in keys)
    total_anom = corr.get("corruption_count",0) + corr.get("unreadable_count",0) + status.get("storage",{}).get("absent_count",0) + status.get("storage_sections",{}).get("absent_count",0)
    perdida = total_anom > 0
    shutil.rmtree(d, ignore_errors=True); shutil.rmtree(d2, ignore_errors=True)
    return load_result, total_anom, intact, reglas_iguales, kb_igual, op_ok, backup_ok, backup_covers, perdida

for mode in ["unreadable_file","non_mapping_root","list_root_without_valid_rows","empty_mapping_root"]:
    r = measure(mode)
    print(f"MODE={mode}: load={r[0]} anomalies={r[1]} intact={r[2]} reglas={r[3]} kb={r[4]} op={r[5]} backup={r[6]} covers={r[7]} perdida={r[8]}")

# clean data
d = tempfile.mkdtemp()
motor = ContextualAdaptationEngine(data_dir=d)
load_result = motor.load_all_data()
status = motor.get_engine_status()
corr = status.get("corruption") or {}
total_anom = corr.get("corruption_count",0)+corr.get("unreadable_count",0)+status.get("storage",{}).get("absent_count",0)+status.get("storage_sections",{}).get("absent_count",0)
print(f"CLEAN: load={load_result} anomalies={total_anom}")
shutil.rmtree(d, ignore_errors=True)
