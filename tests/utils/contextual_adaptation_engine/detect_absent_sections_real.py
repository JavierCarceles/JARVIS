#!/usr/bin/env python3
"""
Deteccion de la SECCION AUSENTE del subsistema de persistencia de Goal (2.8.8.9.5.2).

Script de sonda independiente de la suite pytest. NO modifica `data/` de produccion.

AISLAMIENTO: el proceso cambia su CWD a un directorio temporal ANTES de construir
ningun motor y NO lo restaura al final. Motivo (hallazgo verificado en runtime):
`SelfImprovementSystem` usa la ruta RELATIVA fija `data/knowledge_graph.json` y su
hilo de aprendizaje la escribe de forma asincrona. Si el CWD se restaurase antes de
que ese hilo terminase, la escritura caeria sobre el `data/` real de produccion.
El `data/` de produccion solo se LEE, mediante rutas absolutas.

Parte A - INVENTARIO REAL: que seccion espera el motor en cada fichero de
          persistencia, de donde sale cada una y de que clase es (datos o metadata).
Parte B - DETECCION EN RUNTIME: comportamiento con la seccion ausente, con la
          seccion vacia, con el formato heredado y con ficheros ilegibles.
Parte C - API DE DETECCION: la API expuesta por el motor
          (`expected_storage_sections` / `detect_absent_sections` / `get_engine_status`).
Parte D - NO CONTAMINACION: el `data/` de produccion queda byte a byte igual.

Uso:
    python tests/utils/contextual_adaptation_engine/detect_absent_sections_real.py
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PRODUCTION_DATA_DIR = os.path.join(ROOT, "data")
STORAGE_FILES = ("goal_adaptation_feedback.json", "goal_adaptation_learning_results.json",
                 "contextual_adaptation_rules.json", "contextual_knowledge_base.json")

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


def sha256(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def nuevo_motor(data_dir):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    os.makedirs(data_dir, exist_ok=True)
    return ContextualAdaptationEngine(data_dir=data_dir)


# ---------------------------------------------------------------- Parte A
def parte_a_inventario():
    print("\n== PARTE A: INVENTARIO REAL DE LAS SECCIONES ESPERADAS ==")
    engine = nuevo_motor(os.path.join(os.getcwd(), "data"))

    secciones = engine.expected_storage_sections()
    rutas = engine.expected_storage_paths()
    print(f"  Almacenamiento esperado: {len(secciones)} ficheros")
    for nombre in sorted(secciones):
        print(f"  - {nombre}  ({os.path.basename(rutas[nombre])})")
        for seccion, clase in secciones[nombre].items():
            marca = "DATOS  " if clase == "data" else "metadata"
            print(f"      {marca} {seccion}")

    check("`expected_storage_sections` cubre los 4 ficheros de persistencia",
          set(secciones) == {"goal_adaptation_feedback", "goal_adaptation_learning_results",
                             "adaptation_rules", "knowledge_base"},
          ", ".join(sorted(secciones)))
    check("Toda seccion declarada tiene clase `data` o `metadata`",
          all(clase in ("data", "metadata")
              for secciones_fichero in secciones.values() for clase in secciones_fichero.values()))

    origen = {
        "goal_adaptation_feedback": ("_save_goal_adaptation_feedback", "_load_goal_adaptation_feedback"),
        "goal_adaptation_learning_results": ("_save_goal_adaptation_learning_results", "_load_goal_adaptation_learning_results"),
        "adaptation_rules": ("_save_adaptation_rules", "load_adaptation_rules"),
        "knowledge_base": ("save_knowledge_base", "load_knowledge_base"),
    }
    check("Cada almacenamiento declara su origen real en el motor",
          all(hasattr(engine, simbolo[0]) and hasattr(engine, simbolo[1])
              for simbolo in origen.values()),
          "; ".join(f"{k}: {v[0]}/{v[1]}" for k, v in origen.items()))

    # La seccion de DATOS debe ser la que consume el cargador real.
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    fuente = open(os.path.join(ROOT, "src", "utils", "contextual_adaptation_engine.py"),
                   "r", encoding="utf-8").read()
    for nombre, (escritor, cargador) in origen.items():
        for seccion, clase in secciones[nombre].items():
            if clase != "data":
                continue
            check(f"La seccion de DATOS `{seccion}` la consume `{cargador}`",
                  f'"{seccion}"' in fuente and cargador in fuente,
                  f"{nombre} -> {seccion}")

    print("\n  Secciones realmente presentes en el `data/` de PRODUCCION (solo lectura):")
    for file_name in STORAGE_FILES:
        ruta = os.path.join(PRODUCTION_DATA_DIR, file_name)
        if not os.path.isfile(ruta):
            print(f"  - {file_name}: AUSENTE")
            note(f"FICHERO AUSENTE en produccion: {file_name}")
            continue
        try:
            payload = read_json(ruta)
        except Exception as exc:
            print(f"  - {file_name}: ILEGIBLE ({exc})")
            note(f"FICHERO ILEGIBLE en produccion: {file_name}")
            continue
        claves = sorted(payload) if isinstance(payload, dict) else f"<{type(payload).__name__}>"
        print(f"  - {file_name}: {claves}")
    return


# ---------------------------------------------------------------- Parte B
def parte_b_runtime():
    print("\n== PARTE B: DETECCION DE SECCION AUSENTE EN RUNTIME ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_detect_sections_")
    data_dir = os.path.join(tmp, "data")
    engine = nuevo_motor(data_dir)

    # 1) Almacenamiento completo, escrito por los escritores REALES del motor.
    engine._save_goal_adaptation_feedback()
    engine._save_goal_adaptation_learning_results()
    engine._save_adaptation_rules()
    engine.save_knowledge_base()
    deteccion = engine.detect_absent_sections()
    check("Con el almacenamiento completo no se reporta ninguna seccion ausente",
          deteccion["absent_count"] == 0 and deteccion["has_absent"] is False,
          f"checked={deteccion['checked']}")
    check("La deteccion examina los 4 ficheros existentes",
          set(deteccion["checked"]) == set(engine.expected_storage_paths()),
          ", ".join(deteccion["checked"]))

    # 2) Seccion de DATOS ausente: se quita una clave del payload real.
    ruta_feedback = engine.expected_storage_paths()["goal_adaptation_feedback"]
    payload = read_json(ruta_feedback)
    payload.pop("goal_adaptation_feedback", None)
    write_json(ruta_feedback, payload)
    deteccion = engine.detect_absent_sections()
    ausente = deteccion["absent"].get("goal_adaptation_feedback", {})
    check("Se detecta la seccion de DATOS ausente",
          "goal_adaptation_feedback" in ausente,
          f"absent={ {k: sorted(v) for k, v in deteccion['absent'].items()} }")
    check("La seccion ausente informa su ruta, su motivo y su clase",
          ausente.get("goal_adaptation_feedback", {}).get("reason") == "section_not_found"
          and ausente.get("goal_adaptation_feedback", {}).get("kind") == "data"
          and ausente.get("goal_adaptation_feedback", {}).get("path") == ruta_feedback,
          json.dumps(ausente.get("goal_adaptation_feedback", {}), ensure_ascii=False))
    check("Solo se reporta la seccion ausente, no el resto del fichero",
          set(ausente) == {"goal_adaptation_feedback"}, ", ".join(sorted(ausente)))

    # 3) Seccion de METADATA ausente: se quita `last_updated`.
    payload = read_json(ruta_feedback)
    payload.pop("last_updated", None)
    write_json(ruta_feedback, payload)
    deteccion = engine.detect_absent_sections()
    ausente = deteccion["absent"].get("goal_adaptation_feedback", {})
    check("Se detecta la seccion de METADATA ausente",
          "last_updated" in ausente and ausente["last_updated"]["kind"] == "metadata",
          json.dumps(ausente, ensure_ascii=False))

    # 4) Seccion presente pero VACIA: no es ausencia.
    write_json(ruta_feedback, {"goal_adaptation_feedback": [], "adaptation_history": [], "last_updated": "2026-01-01T00:00:00"})
    deteccion = engine.detect_absent_sections()
    check("Una seccion presente pero VACIA no se reporta como ausente",
          "goal_adaptation_feedback" not in deteccion["absent"],
          json.dumps({k: sorted(v) for k, v in deteccion["absent"].items()}, ensure_ascii=False))
    check("Una seccion de DATOS vacia se considera presente",
          deteccion["absent_count"] == 0, f"absent_count={deteccion['absent_count']}")

    # 5) Varias secciones ausentes a la vez en el mismo fichero.
    write_json(ruta_feedback, {"adaptation_history": []})
    deteccion = engine.detect_absent_sections()
    ausente = deteccion["absent"].get("goal_adaptation_feedback", {})
    check("Se detectan varias secciones ausentes en el mismo fichero",
          set(ausente) == {"goal_adaptation_feedback", "last_updated"}, ", ".join(sorted(ausente)))
    check("El recuento total suma las secciones ausentes de todos los ficheros",
          deteccion["absent_count"] == sum(len(v) for v in deteccion["absent"].values()),
          f"absent_count={deteccion['absent_count']}")

    # 6) Formato heredado: la lista de reglas en la raiz del fichero.
    ruta_reglas = engine.expected_storage_paths()["adaptation_rules"]
    reglas = [r.to_dict() for r in engine.adaptation_rules.values()]
    write_json(ruta_reglas, reglas)
    deteccion = engine.detect_absent_sections()
    ausente = deteccion["absent"].get("adaptation_rules", {})
    check("Con el formato heredado la seccion de DATOS `rules` se considera presente",
          "rules" not in ausente, json.dumps(ausente, ensure_ascii=False))
    check("Con el formato heredado las secciones de METADATA se reportan ausentes",
          set(ausente) == {"version", "last_updated", "total_rules"}, ", ".join(sorted(ausente)))
    check("El formato heredado sigue siendo legible por `load_adaptation_rules`",
          engine.load_adaptation_rules() is True and len(engine.adaptation_rules) == 5,
          f"{len(engine.adaptation_rules)} reglas")

    # 7) Fichero ILEGIBLE (contenido corrupto): no se reporta como seccion ausente.
    engine._save_adaptation_rules()
    with open(ruta_reglas, "w", encoding="utf-8") as handle:
        handle.write("{esto no es json")
    deteccion = engine.detect_absent_sections()
    check("Un fichero ilegible NO se reporta como seccion ausente",
          "adaptation_rules" not in deteccion["absent"],
          json.dumps({k: sorted(v) for k, v in deteccion["absent"].items()}, ensure_ascii=False))
    check("Un fichero ilegible se informa en `unreadable`",
          deteccion["unreadable"].get("adaptation_rules", {}).get("reason") == "unreadable_file",
          json.dumps(deteccion["unreadable"], ensure_ascii=False))
    note("La CORRUPCION del contenido se detecta en 2.8.8.9.6; aqui solo se marca como ilegible")

    # 8) Payload que no es un diccionario.
    write_json(ruta_reglas, "no soy un mapeo")
    deteccion = engine.detect_absent_sections()
    check("Un payload que no es un mapeo se informa en `unreadable`",
          deteccion["unreadable"].get("adaptation_rules", {}).get("reason") == "not_a_mapping",
          json.dumps(deteccion["unreadable"], ensure_ascii=False))

    # 9) Payload que es una LISTA en un fichero que no admite formato heredado.
    ruta_kb = engine.expected_storage_paths()["knowledge_base"]
    write_json(ruta_kb, [1, 2, 3])
    deteccion = engine.detect_absent_sections()
    check("Una lista en un fichero sin formato heredado reporta la seccion de DATOS ausente",
          "data" in deteccion["absent"].get("knowledge_base", {}),
          json.dumps({k: sorted(v) for k, v in deteccion["absent"].items()}, ensure_ascii=False))

    # 10) Fichero AUSENTE: es deteccion de 2.8.8.9.5.1, no de seccion ausente.
    shutil.rmtree(tmp, ignore_errors=True)
    data_dir2 = os.path.join(tmp, "data")
    engine2 = nuevo_motor(data_dir2)
    deteccion = engine2.detect_absent_sections()
    check("Con el almacenamiento ausente no se reportan secciones ausentes",
          deteccion["absent_count"] == 0 and deteccion["has_absent"] is False,
          f"absent_count={deteccion['absent_count']}")
    check("Los ficheros ausentes se listan en `missing_files`",
          set(deteccion["missing_files"]) == set(engine2.expected_storage_paths()),
          ", ".join(deteccion["missing_files"]))
    check("Los ficheros ausentes NO se listan en `absent`",
          deteccion["absent"] == {}, json.dumps(deteccion["absent"], ensure_ascii=False))

    # 11) La deteccion NO crea ni modifica ficheros.
    engine2._save_goal_adaptation_feedback()
    rutas = engine2.expected_storage_paths()
    hashes_antes = {ruta: sha256(ruta) for ruta in rutas.values()}
    ficheros_antes = {ruta for ruta in rutas.values() if os.path.isfile(ruta)}
    engine2.detect_absent_sections()
    engine2.get_engine_status()
    hashes_despues = {ruta: sha256(ruta) for ruta in rutas.values()}
    ficheros_despues = {ruta for ruta in rutas.values() if os.path.isfile(ruta)}
    check("La deteccion NO modifica los ficheros de persistencia",
          hashes_antes == hashes_despues,
          ", ".join(sorted(os.path.basename(r) for r in rutas.values())))
    check("La deteccion NO crea ficheros de persistencia",
          ficheros_antes == ficheros_despues,
          f"antes={sorted(os.path.basename(r) for r in ficheros_antes)} "
          f"despues={sorted(os.path.basename(r) for r in ficheros_despues)}")

    # 12) El motor sigue funcionando con una seccion ausente.
    ruta_fb = rutas["goal_adaptation_feedback"]
    payload = read_json(ruta_fb)
    payload.pop("goal_adaptation_feedback", None)
    write_json(ruta_fb, payload)
    check("El motor carga sin fallar con una seccion de DATOS ausente",
          engine2.load_adaptation_rules() is True and engine2.load_knowledge_base() is True)
    check("El motor mantiene su estado tras la carga",
          isinstance(engine2.get_engine_status(), dict)
          and engine2.get_engine_status().get("total_rules") == 5,
          f"total_rules={engine2.get_engine_status().get('total_rules')}")

    shutil.rmtree(tmp, ignore_errors=True)
    return


# ---------------------------------------------------------------- Parte C
def parte_c_api():
    print("\n== PARTE C: API DE DETECCION DE SECCION AUSENTE ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_detect_sections_api_")
    data_dir = os.path.join(tmp, "data")
    engine = nuevo_motor(data_dir)

    secciones = engine.expected_storage_sections()
    check("`expected_storage_sections` devuelve una COPIA (no muta el motor)",
          engine.expected_storage_sections() is not secciones
          and engine.expected_storage_sections()["adaptation_rules"] is not secciones["adaptation_rules"])
    secciones["adaptation_rules"]["reglas"] = "contaminado"
    check("La copia devuelta es independiente",
          "reglas" not in engine.expected_storage_sections()["adaptation_rules"])

    deteccion = engine.detect_absent_sections()
    check("`detect_absent_sections` devuelve las claves esperadas",
          set(deteccion) == {"expected", "checked", "absent", "absent_count", "has_absent",
                             "missing_files", "unreadable"},
          ", ".join(sorted(deteccion)))
    check("`detect_absent_sections` es de SOLO LECTURA: no crea ficheros",
          not any(os.path.isfile(ruta) for ruta in engine.expected_storage_paths().values()))

    engine._save_goal_adaptation_feedback()
    engine._save_goal_adaptation_learning_results()
    engine._save_adaptation_rules()
    engine.save_knowledge_base()
    deteccion = engine.detect_absent_sections()
    check("Con el almacenamiento completo no hay ausencias",
          deteccion["absent_count"] == 0 and deteccion["has_absent"] is False)

    status = engine.get_engine_status()
    check("`get_engine_status` expone la deteccion en `storage_sections`",
          isinstance(status.get("storage_sections"), dict)
          and status["storage_sections"].get("absent_count") == 0
          and "absent" in status["storage_sections"],
          json.dumps(status.get("storage_sections", {}), ensure_ascii=False))
    check("`get_engine_status` conserva intacta la clave previa `storage`",
          set(status.get("storage", {})) == {"absent", "absent_count"},
          json.dumps({k: (len(v) if isinstance(v, dict) else v) for k, v in status.get("storage", {}).items()},
                     ensure_ascii=False))
    check("`get_engine_status` conserva el resto de claves previas",
          {"adaptation_enabled", "is_adapting", "current_context", "adaptation_level", "total_snapshots",
           "total_rules", "total_adaptations", "total_knowledge_transfers", "active_modes",
           "knowledge_base_stats", "storage"}.issubset(set(status)),
          ", ".join(sorted(status)))

    # Con una seccion ausente, `get_engine_status` la refleja.
    ruta_fb = engine.expected_storage_paths()["goal_adaptation_feedback"]
    payload = read_json(ruta_fb)
    payload.pop("adaptation_history", None)
    write_json(ruta_fb, payload)
    status = engine.get_engine_status()
    check("`get_engine_status` refleja la seccion ausente",
          status["storage_sections"]["absent_count"] == 1
          and "adaptation_history" in status["storage_sections"]["absent"].get("goal_adaptation_feedback", {}),
          json.dumps(status["storage_sections"], ensure_ascii=False))

    shutil.rmtree(tmp, ignore_errors=True)
    return


# ---------------------------------------------------------------- Parte D
def parte_d_no_contaminacion(hashes_iniciales):
    print("\n== PARTE D: NO CONTAMINACION DEL `data/` DE PRODUCCION ==")
    hashes_finales = {ruta: sha256(ruta) for ruta in hashes_iniciales}
    iguales = hashes_iniciales == hashes_finales
    check("Los ficheros de persistencia de produccion quedan byte a byte igual", iguales,
          ", ".join(sorted(os.path.basename(ruta) for ruta in hashes_iniciales)))
    if not iguales:
        for ruta in hashes_iniciales:
            if hashes_iniciales[ruta] != hashes_finales[ruta]:
                print(f"    CONTAMINADO: {ruta}")
    return


if __name__ == "__main__":
    hashes_iniciales = {os.path.join(PRODUCTION_DATA_DIR, f): sha256(os.path.join(PRODUCTION_DATA_DIR, f))
                         for f in STORAGE_FILES}

    # El CWD se mueve al temporal y NO se restaura: el hilo de aprendizaje de
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma asincrona
    # usando una ruta RELATIVA, y restaurarla antes de que termine contaminaria el
    # `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_detect_sections_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE DETECCION DE SECCION AUSENTE (2.8.8.9.5.2)")
    parte_a_inventario()
    parte_b_runtime()
    parte_c_api()
    parte_d_no_contaminacion(hashes_iniciales)
    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
