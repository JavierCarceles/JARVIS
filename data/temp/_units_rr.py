import io, contextlib, logging, os, sys, tempfile, json
logging.disable(logging.CRITICAL)
sys.path.insert(0, "src")
sys.path.insert(0, "tests/utils/contextual_adaptation_engine")
with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

out=[]
# Show unidades for a few clases (campo, fila, bloque, seccion)
for cid in ["adaptation_rules.priority_not_castable","adaptation_rules.row_not_mapping","adaptation_rules.rules_wrong_type","knowledge_base.section_not_mapping","goal_adaptation_feedback.history_not_list","goal_adaptation_learning_results.strategy_missing_identity"]:
    esc=B.escenario_corrupto(cid, marca_prefix="INSPECT_")
    out.append("CLASE %s: unidades=%r" % (cid, [(u["etiqueta"],u["token"]) for u in esc["unidades"]]))

# recovery_report for a campo class (priority_not_castable)
d=tempfile.mkdtemp(); data=os.path.join(d,"data"); os.makedirs(data)
esc=B.escenario_corrupto("adaptation_rules.priority_not_castable", marca_prefix="RR_")
B.materializar(esc["files"], data)
with contextlib.redirect_stdout(io.StringIO()):
    m=ContextualAdaptationEngine(data_dir=data); m.load_all_data()
rep=m.recovery_report()
out.append("\nrecovery_report keys: "+str(sorted(rep.keys())))
out.append("count: "+str(rep.get("count")))
out.append("files: "+str(rep.get("files")))
out.append("recoveries[0]: "+str(rep.get("recoveries",[{}])[0]))
rec=m.recoverable_data()
fd=rec.get("field_defaults") or {}
out.append("field_defaults priority: "+str(fd.get("priority")))
# show all recoveries
out.append("ALL recoveries:\n"+json.dumps(rep.get("recoveries",[]), default=str, ensure_ascii=False, indent=1))
with open("c:/temp/_cae_units_rr.txt","w",encoding="utf-8") as f:
    f.write("\n".join(out))
print("OK")
