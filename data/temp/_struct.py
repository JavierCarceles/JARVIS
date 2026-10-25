import sys, io, contextlib, logging, os, tempfile, json
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    d = tempfile.mkdtemp()
    m = ContextualAdaptationEngine(data_dir=d)
    r = m.recoverable_data()

out = []
out.append("TOP KEYS: " + str(sorted(r.keys())))
out.append("independence_rule: " + repr(r.get('independence_rule')))
out.append("levels: " + repr(r.get('levels')))
out.append("policies: " + repr(r.get('policies')))
out.append("recoverable_tokens: " + repr(r.get('recoverable_tokens')))
out.append("pending(top): " + repr(r.get('pending')))
out.append("field_defaults keys: " + str(sorted((r.get('field_defaults') or {}).keys())))
for fid, v in (r.get('field_defaults') or {}).items():
    out.append("  fd %s -> %s" % (fid, v))
for g, spec in r.get('files', {}).items():
    out.append("GRUPO %s file=%s keys=%s" % (g, spec.get('file'), sorted(spec.keys())))
    for cid, cl in spec.get('classes', {}).items():
        out.append("  CLASS %s keys=%s" % (cid, sorted(cl.keys())))
        vals = {k: cl[k] for k in ('level', 'policy', 'corrupt_unit', 'recovers', 'pending', 'status') if k in cl}
        out.append("     " + repr(vals))
with open('c:/temp/_cae_struct.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(out))
