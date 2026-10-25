import sys, os, copy, contextlib, io
ROOT=r"C:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS"
sys.path.insert(0, os.path.join(ROOT, "tests/utils/contextual_adaptation_engine"))
sys.path.insert(0, os.path.join(ROOT, "src"))
with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    import identify_recoverable_real as S

rec, decl = S._declaraciones()
base = B._payload_valido("adaptation_rules")
print("base rules rule_ids:", [r.get("rule_id") for r in base["rules"]])
esc = S.ESCENARIOS["adaptation_rules.row_not_mapping"]
print("esc marca:", esc["marca"])
print("esc unidades:", [(u["etiqueta"], u["token"]) for u in esc["unidades"]])

# (1) OLD doble-corrupto: rules = [marca_A, marca_B]
p1 = copy.deepcopy(base)
p1["rules"] = [esc["marca"]+"_A", esc["marca"]+"_B"]
dup1 = {"files": {esc["filename"]: p1}, "marca": esc["marca"], "unidades": esc["unidades"]}
m1 = S.medir(dup1)
print("(1) doble str rules -> unidades:", m1["unidades"], "corrupto_en_estado:", m1["corrupto_en_estado"])
print("(1) perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m1)])

# (2) corrupt ONLY the sibling (rules[1] -> string mark, keep rules[0] valid)
p2 = copy.deepcopy(base)
rid_a = p2["rules"][0]["rule_id"]
rid_b = p2["rules"][1]["rule_id"]
p2["rules"][1]["rule_id"] = esc["marca"]+"_B"  # break sibling identity
dup2 = {"files": {esc["filename"]: p2}, "marca": esc["marca"], "unidades": esc["unidades"]}
m2 = S.medir(dup2)
print("(2) sibling rule_id broken -> unidades:", m2["unidades"])
print("(2) perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m2)])

# (3) corrupt sibling by turning rules[1] into a string outright
p3 = copy.deepcopy(base)
p3["rules"][1] = esc["marca"]+"_B"
dup3 = {"files": {esc["filename"]: p3}, "marca": esc["marca"], "unidades": esc["unidades"]}
m3 = S.medir(dup3)
print("(3) sibling->string -> unidades:", m3["unidades"])
print("(3) perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m3)])
