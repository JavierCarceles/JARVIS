import io, contextlib, logging, os, sys, tempfile, json
logging.disable(logging.CRITICAL)
sys.path.insert(0, "src")
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine as E
out=[]
RF,KB,FB,LR="contextual_adaptation_rules.json","contextual_knowledge_base.json","goal_adaptation_feedback.json","goal_adaptation_learning_results.json"
MARCA="FBINS_INS_"
files={RF:MARCA+"roto1",KB:MARCA+"roto2",FB:MARCA+"roto3",LR:MARCA+"roto4"}
d=tempfile.mkdtemp(); data=os.path.join(d,"data"); os.makedirs(data)
for n,c in files.items():
    with open(os.path.join(data,n),"w") as f: f.write(c if isinstance(c,str) else json.dumps(c))
with contextlib.redirect_stdout(io.StringIO()):
    m=E(data_dir=data); m.load_all_data()
es=m.get_engine_status()
out.append("STATUS KEYS: "+str(sorted(es.keys())))
out.append("status.subkeys: "+str({k:sorted((v or {}).keys()) if isinstance(v,dict) else type(v).__name__ for k,v in es.items()}))
out.append("storage: "+str(json.dumps(es.get("storage"),default=str,ensure_ascii=False)))
out.append("storage_sections: "+str(json.dumps(es.get("storage_sections"),default=str,ensure_ascii=False)[:400]))
out.append("corruption: "+str(json.dumps(es.get("corruption"),default=str,ensure_ascii=False)))
alm=m.detect_absent_storage(); out.append("detect_absent_storage: "+str({k:(v if not isinstance(v,list) else sorted(v)) for k,v in alm.items()}))
sec=m.detect_absent_sections(); out.append("detect_absent_sections: "+str({k:(v if not isinstance(v,(list,dict)) else (sorted(v) if isinstance(v,list) else {kk:vv for kk,vv in v.items()})) for k,v in sec.items()}))
cor=m.detect_corruption(); out.append("detect_corruption top: "+str({k:(v if not isinstance(v,(list,dict)) else (v if isinstance(v,list) else {kk:(vv if not isinstance(vv,(list,dict)) else sorted(vv) if isinstance(vv,list) else '...') for kk,vv in v.items()})) for k,v in cor.items()})[:600])
out.append("absent_storage keys: "+str(sorted(alm.keys())))
out.append("absent_sections keys: "+str(sorted((sec or {}).keys())))
# cycle APIs
for name in ["run_cycle","capture_context_snapshot","execute","analyze_context","capturar_contexto","ejecutar","run_step"]:
    out.append("has %s: %s"%(name, hasattr(m,name)))
# expected_storage_paths
out.append("expected_storage_paths: "+str(sorted(list(m.expected_storage_paths()))))
# recovery_report empty?
out.append("recovery_report count: "+str((m.recovery_report()).get("count")))
with open("c:/temp/_cae_tl_inspect.txt","w",encoding="utf-8") as f:
    f.write("\n".join(out))
print("OK")
