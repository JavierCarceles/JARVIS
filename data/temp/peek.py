import io, json, os

for name in ("contextual_knowledge_base.json", "goal_adaptation_feedback.json",
             "goal_adaptation_learning_results.json", "contextual_adaptation_rules.json"):
    path = os.path.join("data", name)
    if not os.path.isfile(path):
        print(name, "-> NO EXISTE")
        continue
    try:
        payload = json.load(io.open(path, encoding="utf-8"))
    except Exception as exc:
        print(name, "-> ILEGIBLE", exc)
        continue
    if isinstance(payload, dict):
        print("==", name, "claves raiz:", sorted(payload.keys()))
        data = payload.get("data")
        if isinstance(data, dict):
            print("   data.claves:", sorted(data.keys()))
            for k in ("goal_adaptation_feedback", "learning_results"):
                if k in data:
                    v = data[k]
                    print("   data.%s: %s filas=%s" % (k, type(v).__name__, len(v) if isinstance(v, list) else "-"))
        for k in ("goal_adaptation_feedback", "learning_results"):
            if k in payload and not isinstance(data, dict):
                v = payload[k]
                print("   raiz.%s: %s filas=%s" % (k, type(v).__name__, len(v) if isinstance(v, list) else "-"))
    else:
        print("==", name, "raiz", type(payload).__name__)
