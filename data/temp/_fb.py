import sys, io, contextlib, logging, os, tempfile, json
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    d = tempfile.mkdtemp()
    m = ContextualAdaptationEngine(data_dir=d)
    fb = m.total_loss_fallback()
out = []
out.append("FB TOP KEYS: " + str(sorted(fb.keys())))
out.append("version: " + repr(fb.get("version")))
out.append("principle: " + repr(fb.get("principle")))
out.append("definition: " + repr(fb.get("definition")))
out.append("loss_modes: " + repr(fb.get("loss_modes")))
out.append("fallback_layers: " + repr(fb.get("fallback_layers")))
out.append("pending(top): " + repr(fb.get("pending")))
out.append("invariants:")
for name, inv in (fb.get("invariants") or {}).items():
    out.append("  %s -> %s" % (name, inv))
out.append("reconciliation:")
for r in fb.get("reconciliation") or []:
    out.append("  owner=%s pending=%s resolved=%d" % (r.get("implementation_owner"), r.get("pending"), len(r.get("resolved") or [])))
with open('c:/temp/_cae_fb.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(out))

# subdir test collection check
out2 = []
for root, dirs, files in os.walk('tests/utils'):
    for f in files:
        if f.endswith('.py'):
            out2.append(os.path.join(root, f))
with open('c:/temp/_cae_subdir.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(sorted(out2)))
