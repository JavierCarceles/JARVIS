import sys, os, copy, contextlib, io
ROOT=r"C:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS"
sys.path.insert(0, os.path.join(ROOT, "tests/utils/contextual_adaptation_engine"))
sys.path.insert(0, os.path.join(ROOT, "src"))
with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    import identify_recoverable_real as S
rec, decl = S._declaraciones()
esc = S.ESCENARIOS["adaptation_rules.row_not_mapping"]
payload = copy.deepcopy(esc["files"][esc["filename"]])  # ya corrupto fila (row_not_mapping)
rid_b = None
for u in esc["unidades"]:
    if u["token"] == "siblings" and u["etiqueta"].startswith("regla:"):
        rid_b = u["etiqueta"].split(":",1)[1]
print("rid_b:", rid_b)
for r in payload["rules"]:
    if isinstance(r, dict) and r.get("rule_id") == rid_b:
        r["rule_id"] = esc["marca"]  # doble perdida: hermano roto
dup = {"files": {esc["filename"]: payload}, "marca": esc["marca"], "unidades": esc["unidades"]}
m = S.medir(dup)
print("unidades:", m["unidades"], "corrupto_estado:", m["corrupto_en_estado"])
print("perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m)])
# also verify sanos: valid payload -> no perdida
san = copy.deepcopy(B._payload_valido("adaptation_rules"))
dup2 = {"files": {esc["filename"]: san}, "marca": esc["marca"], "unidades": esc["unidades"]}
m2 = S.medir(dup2)
print("sanos perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m2)])
