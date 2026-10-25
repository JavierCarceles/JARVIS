import sys, io, contextlib, logging, os, tempfile
logging.disable(logging.CRITICAL)
sys.path.insert(0, 'src')
with contextlib.redirect_stdout(io.StringIO()):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    d = tempfile.mkdtemp()
    m = ContextualAdaptationEngine(data_dir=d)
    c = m.corruption_criteria()
out = []
out.append("TOP: " + str(sorted(c.keys())))
out.append("effect_vocabulary: " + repr(c.get("effect_vocabulary")))
for g, spec in c.get("files", {}).items():
    out.append("GRUPO %s file=%s keys=%s" % (g, spec.get("file"), sorted(spec.keys())))
    for clase in spec.get("corruptions", []) or []:
        out.append("  %s -> target=%r violation=%r severity=%r expected=%r"
                   % (clase.get("id"), clase.get("target"), clase.get("violation"),
                      clase.get("severity"), clase.get("expected")))

# utils subdir __init__.py check + syntax
for p in ["tests/utils/adaptive_learning_engine", "tests/utils/dynamic_resource_allocator",
          "tests/utils/contextual_adaptation_engine"]:
    out.append("__init__ in %s: %s" % (p, os.path.exists(p + "/__init__.py")))
for f in ["tests/utils/test_adaptive_learning_engine.py",
          "tests/utils/test_contextual_pattern_recognizer.py",
          "tests/utils/test_dynamic_resource_allocator.py"]:
    head = open(f, encoding="utf-8", errors="replace").read(1200)
    out.append("=== HEAD %s ===" % f)
    out.append(head)
with open('c:/temp/_cae_cc.txt', 'w', encoding='utf-8') as fh:
    fh.write("\n".join(out))
