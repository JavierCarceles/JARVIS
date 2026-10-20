import sys, io, json
sys.path.insert(0, r"C:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS")

from src.utils.pattern_analyzer import PatternAnalyzer
from src.utils.log_analytics import LogAnalytics
from src.utils.log_predictor import LogPredictor

pa = PatternAnalyzer()
la = LogAnalytics()
lp = LogPredictor()

p = pa.get_pattern_analysis()
a = la.get_analytics_summary()
pr = lp.get_predictions()

for name, val in [("pattern_analysis", p), ("analytics_summary", a), ("predictions", pr)]:
    print(f"{name}: type={type(val).__name__} len={len(val) if hasattr(val,'__len__') else 'n/a'}")
    if isinstance(val, dict):
        print("   keys:", list(val.keys())[:20])
    elif isinstance(val, list):
        if val:
            print("   item0:", type(val[0]).__name__)
            if hasattr(val[0], "type"):
                print("   item0.type:", val[0].type, "value:", val[0].predicted_value)
