import sys, os, copy, contextlib, io
ROOT=r"C:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS"
sys.path.insert(0, os.path.join(ROOT, "tests/utils/contextual_adaptation_engine"))
sys.path.insert(0, os.path.join(ROOT, "src"))
with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    import identify_recoverable_real as S
with contextlib.redirect_stdout(io.StringIO()):
    motor_ref = B._motor_ref()
rec, decl = S._declaraciones()
pend = S.clases_pendientes(rec)
print("clases_pendientes:", sorted(pend))
real = {}
for cid, esc in S.ESCENARIOS.items():
    med = S.medir(copy.deepcopy(esc))
    real[cid] = med
    p = S.perdidas_de(decl[cid], med)
    print(cid, "recovers=", decl[cid].get("recovers"), "pend=", cid in pend, "perdidas=", [u["etiqueta"] for u in p])
esc = S.ESCENARIOS["adaptation_rules.row_not_mapping"]
m1 = S.medir(esc); m2 = S.medir(copy.deepcopy(esc))
print("row_not_mapping live perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m1)])
print("row_not_mapping dd  perdidas:", [u["etiqueta"] for u in S.perdidas_de(decl["adaptation_rules.row_not_mapping"], m2)])
