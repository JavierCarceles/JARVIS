import sys, os, json, tempfile, shutil, logging, io, contextlib
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
sys.path.insert(0, 'tests/utils/contextual_adaptation_engine')
with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

def _entradas_esperadas(clase):
    nivel = clase.get("level"); pol = clase.get("policy")
    if nivel in ("campo", "grupo"):
        return 1
    if nivel == "bloque" and pol == "adapt_container":
        return 1
    return 0

rows = []
for clase_id, info in B.criterios().items():
    rec = B._recoverable_clase(clase_id)
    esc = B.escenario_corrupto(clase_id)
    with contextlib.redirect_stdout(io.StringIO()):
        motor, d = ContextualAdaptationEngine(data_dir=tempfile.mkdtemp()), tempfile.mkdtemp()
        B.materializar(esc["files"], motor.data_dir)
        try:
            cor = motor.detect_corruption()
            det = [x.get('id') for x in cor.get("corrupted", {}).get(info['grupo'], [])]
            marr = B.marca_presente(motor, esc["marca"])
            presentes = [u["etiqueta"] for u in esc["unidades"] if u["presente"](motor)]
            ausentes = [u["etiqueta"] for u in esc["unidades"] if not u["presente"](motor)]
            rec_count = len(motor.recovery_report()["recoveries"])
        except Exception as e:
            det = []; marr = "ERR:%s" % e; presentes=[]; ausentes=[]; rec_count=-1
        finally:
            shutil.rmtree(motor.data_dir, ignore_errors=True)
    esp = _entradas_esperadas(rec)
    rows.append((clase_id, clase_id in det, det, marr, len(esc["unidades"]),
                 len(presentes), len(ausentes), rec_count, esp))

print("TOTAL", len(rows))
for r in rows:
    print("%-55s det=%s extra=%-30s marca=%s und=%d(pres%d/aus%d) rec=%d/esp=%d"
          % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))
prob = [r for r in rows if not r[1] or r[3] or r[5] != r[4] or r[7] != r[8]]
print("PROBLEMAS (sin deteccion|marca leak|und no presente|rec_count!=esp):", len(prob))
for r in prob:
    print("  ", r[0], "det=", r[1], "marca=", r[3], "aus=", r[6], "rec=", r[7], "esp=", r[8])
