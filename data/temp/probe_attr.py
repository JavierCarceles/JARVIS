import json, os, sys, tempfile, logging
sys.path.insert(0, "src")
from utils.contextual_adaptation_engine import ContextualAdaptationEngine

tmp = tempfile.mkdtemp(); d = os.path.join(tmp,"data"); os.makedirs(d, exist_ok=True)
kb = {"version":"2.0","data":{
  "learning_results": {"no":"es una lista"},
  "context_patterns": {"production":[{"patron":"sano"}]}}}
with open(os.path.join(d,"contextual_knowledge_base.json"),"w",encoding="utf-8") as h:
    json.dump(kb,h)

m = ContextualAdaptationEngine(data_dir=d)
print("context_patterns.production:", m.knowledge_base.get("context_patterns",{}).get("production"))
print("unidades KB:", m._unidades_cargadas.get("knowledge_base"))
try:
    m._recuperar_grupos_de_base("learning_results", {"no":"es una lista"})
except Exception as e:
    print("EXCEPCION en _recuperar_grupos_de_base:", type(e).__name__, e)
print("_valores_por_defecto learning_results tipo:", type(m._valores_por_defecto.get("learning_results")).__name__)
print("_valores_por_defecto context_patterns tipo:", type(m._valores_por_defecto.get("context_patterns")).__name__)
