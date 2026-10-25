import sys, io, contextlib, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    import os, tempfile
    d = tempfile.mkdtemp()
    m = ContextualAdaptationEngine(data_dir=d)
    r = m.recoverable_data()
import json
out = []
out.append("reconciliation: " + repr(r.get("reconciliation")))
out.append("invariants: " + repr(r.get("invariants")))
out.append("conservative_defaults: " + repr(r.get("conservative_defaults")))
out.append("principle: " + repr(r.get("principle")))
out.append("--- condition por clase ---")
for g, spec in r["files"].items():
    for cid, cl in spec["classes"].items():
        out.append("%s -> condition=%r" % (cid, cl.get("condition")))
with open('c:/temp/_cae_struct2.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(out))
