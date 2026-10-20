import sys, json
sys.path.insert(0, r"C:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS")

from src.utils.pattern_analyzer import PatternAnalyzer
from src.utils.log_analytics import LogAnalytics

pa = PatternAnalyzer()
la = LogAnalytics()

p = pa.get_pattern_analysis()
a = la.get_analytics_summary()

print("=== ANALYTICS KEYS ===")
for k, v in a.items():
    print(f"  {k}: {type(v).__name__} = {str(v)[:80]}")

print("=== PATTERN statistics ===")
print(json.dumps(p.get("statistics", {}), indent=2, default=str)[:1500])
print("=== PATTERN other ===")
for k in p:
    if k != "statistics":
        print(f"  {k}: {type(p[k]).__name__} = {str(p[k])[:100]}")
