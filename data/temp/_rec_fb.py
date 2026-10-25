import io, contextlib, logging, os, tempfile, json, hashlib, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, "src")
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

def sha(p):
    if not os.path.isfile(p): return None
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(65536),b""): h.update(c)
    return h.hexdigest()
def _solo(t):
    return "".join(ch.lower() for ch in t if ch.isalpha())

out=[]
with contextlib.redirect_stdout(io.StringIO()):
    d=tempfile.mkdtemp()
    m=ContextualAdaptationEngine(data_dir=d)
    rec=m.recoverable_data()
    out.append("RECOVERABLE TOP KEYS: "+str(sorted(rec.keys())))
    out.append("levels: "+str(rec.get("levels")))
    out.append("policies: "+str(rec.get("policies")))
    out.append("recoverable_tokens: "+str(rec.get("recoverable_tokens")))
    out.append("field_defaults keys: "+str(sorted((rec.get("field_defaults") or {}).keys())))
    out.append("independence_rule: "+str(rec.get("independence_rule")))
    cnt=0
    for spec in (rec.get("files") or {}).values():
        for cid,c in (spec.get("classes") or {}).items():
            out.append("CLASE %s: level=%s policy=%s corrupt_unit=%r recovers=%r"%(cid,c.get("level"),c.get("policy"),c.get("corrupt_unit"),c.get("recovers")))
            cnt+=1
            if cnt>=8: break
        if cnt>=8: break

RF,KB,FB,LR="contextual_adaptation_rules.json","contextual_knowledge_base.json","goal_adaptation_feedback.json","goal_adaptation_learning_results.json"
def loadmotor(files):
    dd=tempfile.mkdtemp(); data=os.path.join(dd,"data"); os.makedirs(data)
    for n,c in files.items():
        with open(os.path.join(data,n),"w",encoding="utf-8") as f:
            f.write(c if isinstance(c,str) else json.dumps(c))
    sb={n:sha(os.path.join(data,n)) for n in files}
    with contextlib.redirect_stdout(io.StringIO()):
        mot=ContextualAdaptationEngine(data_dir=data); mot.load_all_data()
    sa={n:sha(os.path.join(data,n)) for n in files}
    return mot,sb,sa

def firma(m):
    kb=json.dumps(m.knowledge_base or {},default=str,sort_keys=True)
    reglas=sorted((m.adaptation_rules or {}).keys())
    his=json.dumps(getattr(m,"adaptation_history",{}) or {},default=str,sort_keys=True)
    return "|".join([str(reglas),_solo(kb),_solo(his)])

MARCA="FBINS_TL_"
with contextlib.redirect_stdout(io.StringIO()):
    # fresh (no files)
    dd2=tempfile.mkdtemp()
    mf=ContextualAdaptationEngine(data_dir=os.path.join(dd2,"data"))
    fresco=firma(mf)
    # unreadable_file: todos los 4 no parsean
    f1={RF:MARCA+"roto1",KB:MARCA+"roto2",FB:MARCA+"roto3",LR:MARCA+"roto4"}
    m1,sb,sa=loadmotor(f1)
es=m1.get_engine_status()
out.append("\n=== MODO unreadable_file ===")
out.append("sha unchanged: "+str(sb==sa))
out.append("load_all_data: "+str(m1.load_all_data()))
cor=m1.detect_corruption()
out.append("detect_corruption keys: "+str(sorted((cor or {}).keys())))
out.append("corrupted groups: "+str({k:len(v) for k,v in (cor.get("corrupted") or {}).items()}))
sec=m1.detect_absent_sections()
out.append("detect_absent_sections keys: "+str(sorted((sec or {}).keys())) if sec else "None")
corr=es.get("corruption") or {}
out.append("engine_status.corruption keys: "+str(sorted(corr.keys())))
out.append("corruption_count: "+str(corr.get("corruption_count")))
out.append("unreadable_count: "+str(corr.get("unreadable_count")))
out.append("expected_storage_paths: "+str(sorted(list(m1.expected_storage_paths()))))
out.append("backup_data: "+str(m1.backup_data()))
out.append("firma lost == fresco: "+str(firma(m1)==fresco))
out.append("recuperable_tokens: "+str(rec.get("recoverable_tokens")))

with open("c:/temp/_cae_rec_fb.txt","w",encoding="utf-8") as f:
    f.write("\n".join(out))
print("OK written")
