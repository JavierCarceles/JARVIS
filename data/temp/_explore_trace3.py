"""Exploración focalizada 3: traceability sin filtro de estado."""
import logging
logging.disable(logging.CRITICAL)

from src.hands.planner.planner import Planner

planner = Planner()
nodes = planner._get_available_nodes()

def providing(cap):
    out = []
    for n in nodes.values():
        if planner._node_type_value(n) not in {"action","task"}:
            continue
        if planner._node_provides_capability(n, cap):
            out.append(n)
    return out

def exists(a):
    return planner.action_exists(a)

for cap in ["open","navigate","search"]:
    print(f"\n=== capability {cap!r} ===")
    provs = providing(cap)
    print("  providing nodes:", len(provs))
    for n in provs:
        rn = planner._resolve_node_action_name(
            {"id": getattr(n,'id',''), "action": getattr(n,'id',''),
             "metadata": getattr(n,'metadata',{}) or {}}
        )
        cat = getattr(n,'action_category',None)
        print(f"    id={n.id} cat={cat} action={rn!r} action_exists={exists(rn)} cat_exists={exists(cat)} src={(getattr(n,'metadata',{}) or {}).get('source')}")

print("\n=== abrir_chrome / open_application existen? ===")
print("  abrir_chrome:", exists("abrir_chrome"))
print("  open_application:", exists("open_application"))
print("  cerrar_chrome:", exists("cerrar_chrome"))
print("  close_application:", exists("close_application"))
print("  calibrar_chrome:", exists("calibrar_chrome"))
