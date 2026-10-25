import sys, io, contextlib, logging, tempfile, os
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
sys.path.insert(0, 'tests/utils/contextual_adaptation_engine')
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    import _cae_sondas_base as B


def fresh(data_dir):
    with contextlib.redirect_stdout(io.StringIO()):
        return ContextualAdaptationEngine(data_dir=str(data_dir))


# Caso 1: materializar ANTES de construir (construct-after-file)
d = tempfile.mkdtemp()
esc = B.escenario_corrupto("adaptation_rules.priority_not_castable")
B.materializar(esc["files"], d)
m = fresh(d)
with contextlib.redirect_stdout(io.StringIO()):
    rep = m.recovery_report()
print("CASE1 construct-after-file  recovery count:", len(rep["recoveries"]))

# Caso 2: construir ANTES de materializar (construct-before-file), luego acceder
d2 = tempfile.mkdtemp()
m2 = fresh(d2)
B.materializar(esc["files"], d2)
with contextlib.redirect_stdout(io.StringIO()):
    _ = m2.adaptation_rules  # disparador lazy
    rep2 = m2.recovery_report()
print("CASE2 construct-before-file lazy-access recovery count:", len(rep2["recoveries"]))
print("CASE2 rule_001 priority:", getattr(m2.adaptation_rules.get("rule_001"), "priority", None))

# Caso 3: detect_corruption sin acceso previo a atributos
d3 = tempfile.mkdtemp()
B.materializar(esc["files"], d3)
m3 = fresh(d3)
with contextlib.redirect_stdout(io.StringIO()):
    cor = m3.detect_corruption()
    rep3 = m3.recovery_report()
print("CASE3 detect_corruption-then-report recovery count:", len(rep3["recoveries"]))
