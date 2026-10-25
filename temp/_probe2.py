import sys, tempfile, os, json, io, contextlib, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
sys.path.insert(0, 'tests/utils/contextual_adaptation_engine')
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    import _cae_sondas_base as B

d = tempfile.mkdtemp()
# construct FIRST (empty dir)
with contextlib.redirect_stdout(io.StringIO()):
    m = ContextualAdaptationEngine(data_dir=d)
    reglas_antes = list(m.adaptation_rules.keys())
# then materialize files
esc = B.escenario_corrupto("adaptation_rules.priority_not_castable")
B.materializar(esc["files"], d)
with contextlib.redirect_stdout(io.StringIO()):
    m2 = ContextualAdaptationEngine(data_dir=d)
    rep = m2.recovery_report()
    print("construct-after-load recovery count:", len(rep["recoveries"]))
    print("rule ids after lazy access:", list(m2.adaptation_rules.keys()))
    print("priority of rule_001:", getattr(m2.adaptation_rules.get("rule_001"),"priority",None))
# Now: construct BEFORE files, then access lazily
d2 = tempfile.mkdtemp()
with contextlib.redirect_stdout(io.StringIO()):
    m3 = ContextualAdaptationEngine(data_dir=d2)
B.materializar(esc["files"], d2)
with contextlib.redirect_stdout(io.StringIO()):
    # trigger lazy load by accessing adaptation_rules
    _ = m3.adaptation_rules
    rep3 = m3.recovery_report()
    print("construct-before-files-then-lazy recovery count:", len(rep3["recoveries"]))
