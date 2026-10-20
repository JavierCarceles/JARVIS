#!/usr/bin/env python3
"""
Deteccion del ALMACENAMIENTO AUSENTE del subsistema de persistencia de Goal (2.8.8.9.5.1).

Script de sonda independiente de la suite pytest. NO modifica `data/` de produccion.

AISLAMIENTO: el proceso cambia su CWD a un directorio temporal ANTES de construir
ningun motor y NO lo restaura al final. Motivo (hallazgo verificado en runtime):
`SelfImprovementSystem` usa la ruta RELATIVA fija `data/knowledge_graph.json` y su
hilo de aprendizaje la escribe de forma asincrona. Si el CWD se restaurase antes de
que ese hilo terminase, la escritura caeria sobre el `data/` real de produccion.
El `data/` de produccion solo se LEE, mediante rutas absolutas.

Parte A - INVENTARIO REAL: que almacenamiento espera el motor, de donde sale cada ruta
         y si existe o falta en el `data/` de produccion.
Parte B - AUSENCIA EN RUNTIME: que hace el motor cuando ese almacenamiento NO existe
         (arranque, carga, estado, creacion de ficheros).
Parte C - API DE DETECCION: la deteccion de almacenamiento ausente expuesta por el
         motor (`detect_absent_storage` / `expected_storage_paths` / `get_engine_status`).

Uso:
    python tests/utils/contextual_adaptation_engine/detect_absent_storage_real.py
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PRODUCTION_DATA_DIR = os.path.join(ROOT, "data")
GOAL_FILES = ("goal_adaptation_feedback.json", "goal_adaptation_learning_results.json")
ENGINE_FILES = ("contextual_adaptation_rules.json", "contextual_knowledge_base.json")

FAILURES = []
NOTES = []


def check(label, condition, detail=""):
    status = "OK  " if condition else "FALLO"
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f" :: {detail}" if detail else ""))


def note(text):
    NOTES.append(text)
    print(f"  [NOTA] {text}")


# ---------------------------------------------------------------- Parte A
def parte_a_inventario():
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

    print("\n== PARTE A: INVENTARIO REAL DEL ALMACENAMIENTO ESPERADO ==")
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)
    engine = ContextualAdaptationEngine(data_dir=data_dir)

    esperado = [
        ("feedback de Goal", "goal_adaptation_feedback",
         "_save_goal_adaptation_feedback / _load_goal_adaptation_feedback"),
        ("resultados de aprendizaje de Goal", "goal_adaptation_learning_results",
         "_save_goal_adaptation_learning_results / _load_goal_adaptation_learning_results"),
        ("reglas de adaptacion", "adaptation_rules",
         "load_adaptation_rules / _save_adaptation_rules"),
        ("base de conocimiento", "knowledge_base",
         "load_knowledge_base / save_knowledge_base"),
    ]
    rutas = engine.expected_storage_paths()
    for nombre, clave, simbolo in esperado:
        print(f"  - {nombre}")
        print(f"      clave:    {clave}")
        print(f"      ruta:     {rutas[clave]}")
        print(f"      simbolo: {simbolo}")

    print("\n  Estado en el `data/` de PRODUCCION (solo lectura):")
    for file_name in GOAL_FILES + ENGINE_FILES:
        ruta = os.path.join(PRODUCTION_DATA_DIR, file_name)
        presente = os.path.isfile(ruta)
        tam = os.path.getsize(ruta) if presente else 0
        print(f"  - {file_name}: {'PRESENTE' if presente else 'AUSENTE'} ({tam} bytes)")
        if not presente:
            note(f"ALMACENAMIENTO AUSENTE en produccion: {file_name}")
    return


# ---------------------------------------------------------------- Parte B
def parte_b_ausencia_runtime():
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

    print("\n== PARTE B: COMPORTAMIENTO EN RUNTIME SIN ALMACENAMIENTO ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_detect_absent_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)

    # 1) data_dir vacio (sin ningun fichero de persistencia).
    engine = ContextualAdaptationEngine(data_dir=data_dir)
    check("El motor arranca con el almacenamiento ausente", True)

    kb = engine.knowledge_base
    check("`goal_adaptation_feedback` conserva la lista vacia por defecto",
          kb.get("goal_adaptation_feedback") == [], repr(kb.get("goal_adaptation_feedback")))
    check("`learning_results` conserva la lista vacia por defecto",
          kb.get("learning_results") == [], repr(kb.get("learning_results")))
    check("`adaptation_strategies` conserva la forma normalizada por contexto",
          isinstance(kb.get("adaptation_strategies"), dict)
          and all(isinstance(v, list) for v in kb.get("adaptation_strategies", {}).values()),
          f"{len(kb.get('adaptation_strategies', {}))} contextos")
    check("`adaptation_history` queda vacio", engine.adaptation_history == [],
          f"{len(engine.adaptation_history)} entradas")

    check("`load_adaptation_rules` devuelve True sin fichero",
          engine.load_adaptation_rules() is True)
    check("`load_knowledge_base` devuelve True sin fichero",
          engine.load_knowledge_base() is True)
    check("Se conservan las reglas por defecto del motor",
          len(engine.adaptation_rules) == 5, f"{len(engine.adaptation_rules)} reglas")

    status = engine.get_engine_status()
    check("`get_engine_status` funciona sin almacenamiento",
          isinstance(status, dict) and status.get("total_adaptations") == 0,
          json.dumps(status.get("knowledge_base_stats", {}), ensure_ascii=False))

    for file_name in GOAL_FILES:
        ruta = os.path.join(data_dir, file_name)
        check(f"La carga NO crea `{file_name}` (la ausencia se mantiene)",
              not os.path.isfile(ruta))
    check("El data_dir vacio sigue sin ficheros de persistencia",
          not any(os.path.isfile(os.path.join(data_dir, f)) for f in GOAL_FILES))

    # 2) data_dir inexistente: el motor debe crearlo sin fallar.
    data_dir2 = os.path.join(tmp, "data_nested", "sub")
    engine2 = ContextualAdaptationEngine(data_dir=data_dir2)
    check("El motor crea un `data_dir` inexistente", os.path.isdir(data_dir2))
    check("El arranque con `data_dir` inexistente no deja datos cargados",
          engine2.knowledge_base.get("learning_results") == []
          and engine2.knowledge_base.get("goal_adaptation_feedback") == [])

    shutil.rmtree(tmp, ignore_errors=True)
    return


# ---------------------------------------------------------------- Parte C
def parte_c_api_deteccion():
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

    print("\n== PARTE C: API DE DETECCION DE ALMACENAMIENTO AUSENTE ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_detect_api_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    engine = ContextualAdaptationEngine(data_dir=data_dir)

    rutas = engine.expected_storage_paths()
    check("`expected_storage_paths` devuelve las 4 rutas esperadas",
          set(rutas) == {"goal_adaptation_feedback", "goal_adaptation_learning_results",
                         "adaptation_rules", "knowledge_base"},
          ", ".join(sorted(rutas)))
    check("Las rutas son absolutas y apuntan al `data_dir` configurado",
          all(os.path.isabs(p) for p in rutas.values())
          and all(p.startswith(os.path.abspath(data_dir)) for p in rutas.values()),
          os.path.abspath(data_dir))

    deteccion = engine.detect_absent_storage()
    check("Con el almacenamiento ausente se detectan las 4 ausencias",
          deteccion["absent_count"] == 4 and deteccion["has_absent"] is True,
          f"absent_count={deteccion['absent_count']}")
    check("La deteccion no reporta almacenamientos presentes",
          deteccion["present"] == [], repr(deteccion["present"]))
    check("Cada ausencia informa su ruta y su motivo",
          all(set(v) == {"path", "reason"} and v["reason"] == "file_not_found"
              for v in deteccion["absent"].values()),
          json.dumps({k: v["reason"] for k, v in deteccion["absent"].items()}, ensure_ascii=False))

    status = engine.get_engine_status()
    check("`get_engine_status` expone la deteccion en `storage`",
          status.get("storage", {}).get("absent_count") == 4
          and set(status.get("storage", {}).get("absent", {})) == set(rutas),
          json.dumps(status.get("storage", {}), ensure_ascii=False))

    # La deteccion NO debe crear ficheros (es de solo lectura).
    check("La deteccion NO crea ficheros de persistencia",
          not any(os.path.isfile(p) for p in rutas.values()))

    # Con el almacenamiento presente, la deteccion no reporta ausencias.
    engine._save_goal_adaptation_feedback()
    engine._save_goal_adaptation_learning_results()
    engine._save_adaptation_rules()
    engine.save_knowledge_base()
    deteccion_presente = engine.detect_absent_storage()
    check("Con el almacenamiento presente no se reporta ninguna ausencia",
          deteccion_presente["absent_count"] == 0 and deteccion_presente["has_absent"] is False,
          f"present={deteccion_presente['present']}")

    # Ausencia parcial: solo se crea el fichero de feedback.
    shutil.rmtree(tmp, ignore_errors=True)
    data_dir2 = os.path.join(tmp, "data")
    os.makedirs(data_dir2, exist_ok=True)
    engine2 = ContextualAdaptationEngine(data_dir=data_dir2)
    engine2._save_goal_adaptation_feedback()
    deteccion_parcial = engine2.detect_absent_storage()
    check("Con almacenamiento parcial se detectan solo las 3 ausencias restantes",
          deteccion_parcial["absent_count"] == 3
          and "goal_adaptation_feedback" in deteccion_parcial["present"],
          f"present={deteccion_parcial['present']} absent={sorted(deteccion_parcial['absent'])}")

    # Una ruta que existe pero no es un fichero se distingue de "no existe".
    ruta_no_fichero = os.path.join(data_dir2, "knowledge_base_dir")
    os.makedirs(ruta_no_fichero, exist_ok=True)
    engine2.config["knowledge_base_file"] = ruta_no_fichero
    deteccion_no_fichero = engine2.detect_absent_storage()
    check("Una ruta que existe pero no es un fichero se marca `not_a_file`",
          deteccion_no_fichero["absent"].get("knowledge_base", {}).get("reason") == "not_a_file",
          json.dumps({k: v["reason"] for k, v in deteccion_no_fichero["absent"].items()}, ensure_ascii=False))

    shutil.rmtree(tmp, ignore_errors=True)
    return


if __name__ == "__main__":
    # El CWD se mueve al temporal y NO se restaura: el hilo de aprendizaje de
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma asincrona
    # usando una ruta RELATIVA, y restaurarla antes de que termine contaminaria el
    # `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_detect_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE DETECCION DE ALMACENAMIENTO AUSENTE (2.8.8.9.5.1)")
    parte_a_inventario()
    parte_b_ausencia_runtime()
    parte_c_api_deteccion()
    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
