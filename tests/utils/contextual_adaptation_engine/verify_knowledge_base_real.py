#!/usr/bin/env python3
"""
Verificacion de INTEGRIDAD de la base de conocimiento (unidad 2.8.12.2).

Cubre lo que NO verifican las sondas existentes (detect_absent_storage_real /
detect_absent_sections_real / check_unit):
  1. Round-trip de datos: save_knowledge_base() -> load_knowledge_base() ->
     las secciones de `data` (context_patterns, adaptation_strategies, ...) se
     conservan tras guardar y recargar.
  2. Estructura del payload escrito por save_knowledge_base:
     {version, last_updated, context_snapshots, adaptation_history,
      knowledge_transfers, data}.
  3. knowledge_base_stats expuesto por get_engine_status.
  4. expected_storage_paths declara la ruta de knowledge_base.

AISLAMIENTO: usa un data_dir temporal y NO modifica `data/` de produccion.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

FAILURES = []
NOTES = []


def check(label, condition, detail=""):
    status = "OK  " if condition else "FALLO"
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f" :: {detail}" if detail else ""))


def parte_integridad_roundtrip():
    """Guarda KB con datos reales, recarga en motor nuevo y compara contenido."""
    print("\n== ROUND-TRIP DE INTEGRIDAD DE DATOS (save -> load) ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_verify_kb_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)

    from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

    engine = ContextualAdaptationEngine(data_dir=data_dir)

    # Datos reales y representativos de la base de conocimiento.
    engine.knowledge_base["context_patterns"] = {
        ContextType.PRODUCTION.value: [{"id": "p1", "factor": "cpu"}],
        ContextType.EMERGENCY.value: [{"id": "p2", "factor": "mem"}],
    }
    engine.knowledge_base["adaptation_strategies"] = {
        ContextType.PRODUCTION.value: [{"strategy": "reduce_load", "confidence": 0.9}],
        ContextType.LEARNING.value: [{"strategy": "enable_learning", "confidence": 0.8}],
    }
    engine.knowledge_base["success_patterns"] = {"s1": [{"ctx": "prod"}]}
    engine.knowledge_base["performance_baselines"] = {"b1": {"latency": 1.0}}
    engine.knowledge_base["transfer_efficiency"] = {"t1": 0.75}
    engine.knowledge_base["applied_patterns"] = [{"pat": "a"}]
    engine.context_snapshots = [{"ts": 1}]
    engine.adaptation_history = [{"id": "h1"}]
    engine.knowledge_transfers = [{"id": "k1"}]

    ok_save = engine.save_knowledge_base()
    check("save_knowledge_base devuelve True", ok_save is True, f"devolvio {ok_save}")

    ruta_kb = engine.expected_storage_paths()["knowledge_base"]
    check("Se escribio el fichero de knowledge base", os.path.isfile(ruta_kb), ruta_kb)

    with open(ruta_kb, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    esperadas = {"version", "last_updated", "context_snapshots", "adaptation_history",
                 "knowledge_transfers", "data"}
    check("Payload tiene exactamente las claves {version, last_updated, context_snapshots, "
          "adaptation_history, knowledge_transfers, data}",
          set(payload) == esperadas, f"claves={sorted(payload)}")
    check("version == '2.0'", payload.get("version") == "2.0", f"version={payload.get('version')}")
    check("last_updated es cadena ISO", isinstance(payload.get("last_updated"), str),
          f"{payload.get('last_updated')}")
    for met in ("context_snapshots", "adaptation_history", "knowledge_transfers"):
        check(f"{met} es entero >= 0", isinstance(payload.get(met), int) and payload.get(met) >= 0,
              f"{met}={payload.get(met)}")
    check("data es un mapeo", isinstance(payload.get("data"), dict), f"tipo={type(payload.get('data')).__name__}")
    check("data contiene las secciones guardadas",
          {"context_patterns", "adaptation_strategies", "success_patterns",
           "performance_baselines", "transfer_efficiency", "applied_patterns"}.issubset(set(payload["data"])),
          f"claves data={sorted(payload['data'])}")

    # Recarga en un motor NUEVO (sin el contenido en memoria).
    engine2 = ContextualAdaptationEngine(data_dir=data_dir)
    ok_load = engine2.load_knowledge_base()
    check("load_knowledge_base devuelve True", ok_load is True, f"devolvio {ok_load}")

    kb = engine2.knowledge_base
    comparaciones = {
        "context_patterns": engine.knowledge_base["context_patterns"],
        "adaptation_strategies": engine.knowledge_base["adaptation_strategies"],
        "success_patterns": engine.knowledge_base["success_patterns"],
        "performance_baselines": engine.knowledge_base["performance_baselines"],
        "transfer_efficiency": engine.knowledge_base["transfer_efficiency"],
        "applied_patterns": engine.knowledge_base["applied_patterns"],
    }
    for clave, esperado in comparaciones.items():
        cargado = kb.get(clave)
        # Las entradas guardadas deben conservarse intactas. El motor puede
        # ANADIR entradas vacias para el resto de ContextType al normalizar
        # (lineas 1919-1921), por eso se comprueba como subconjunto, no como
        # igualdad exacta del diccionario completo.
        preservado = isinstance(cargado, type(esperado))
        if preservado and isinstance(esperado, dict):
            # Subconjunto: el motor puede anadir entradas vacias por contexto al normalizar.
            preservado = all(k in cargado and cargado[k] == v for k, v in esperado.items())
        elif preservado:
            # Listas u otros tipos: igualdad directa.
            preservado = cargado == esperado
        check(f"Round-trip conserva las entradas guardadas de {clave}", preservado,
              f"guardado={esperado!r} cargado={cargado!r}")

    shutil.rmtree(tmp, ignore_errors=True)


def parte_stats_y_rutas():
    print("\n== ESTADISTICAS Y RUTAS ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_verify_kb_stats_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType
    engine = ContextualAdaptationEngine(data_dir=data_dir)

    engine.knowledge_base["context_patterns"] = {"a": [1], "b": [2]}
    engine.knowledge_base["adaptation_strategies"] = {"c": [{"x": 1}], "d": [{"y": 2}]}
    engine.knowledge_base["transfer_efficiency"] = {"e": 0.5, "f": 0.6}
    engine.save_knowledge_base()
    engine.load_knowledge_base()

    status = engine.get_engine_status()
    stats = status.get("knowledge_base_stats", {})
    check("knowledge_base_stats expuesto", isinstance(stats, dict), f"stats={stats}")
    n_ctx = len(list(ContextType))
    # Las 2 claves guardadas ("a"/"b" y "c"/"d") mas una entrada vacia por cada
    # ContextType (normalizacion de load_knowledge_base).
    check(f"knowledge_base_stats.context_patterns == 2 guardados + {n_ctx} contextos",
          stats.get("context_patterns") == 2 + n_ctx, f"{stats.get('context_patterns')}")
    check(f"knowledge_base_stats.adaptation_strategies == 2 guardados + {n_ctx} contextos",
          stats.get("adaptation_strategies") == 2 + n_ctx, f"{stats.get('adaptation_strategies')}")
    check("knowledge_base_stats.transfer_efficiency == 2 (sin normalizacion)",
          stats.get("transfer_efficiency") == 2, f"{stats.get('transfer_efficiency')}")
    kb = engine.knowledge_base
    check("Clave guardada 'a' conservada en context_patterns tras recarga",
          kb["context_patterns"].get("a") == [1], f"cargado={kb['context_patterns']}")
    check("Clave guardada 'c' conservada en adaptation_strategies tras recarga",
          kb["adaptation_strategies"].get("c") == [{"x": 1}],
          f"cargado={kb['adaptation_strategies']}")

    rutas = engine.expected_storage_paths()
    check("expected_storage_paths declara knowledge_base", "knowledge_base" in rutas,
          f"claves={sorted(rutas)}")
    check("Ruta knowledge_base absoluta y termina en contextual_knowledge_base.json",
          os.path.isabs(rutas["knowledge_base"])
          and rutas["knowledge_base"].endswith("contextual_knowledge_base.json"),
          rutas["knowledge_base"])

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    # El CWD se mueve al temporal y NO se restaura (mismo patron que detect_absent_*_real.py)
    # para que los hilos de aprendizaje escriban knowledge_graph.json fuera de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_verify_kb_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("VERIFICACION DE INTEGRIDAD DE LA BASE DE CONOCIMIENTO (2.8.12.2)")
    parte_integridad_roundtrip()
    parte_stats_y_rutas()
    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
