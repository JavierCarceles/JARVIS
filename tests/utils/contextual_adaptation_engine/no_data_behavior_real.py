#!/usr/bin/env python3
"""
COMPORTAMIENTO SIN DATOS del subsistema de persistencia de Goal (2.8.8.9.5.3).

Script de sonda independiente de la suite pytest. NO modifica `data/` de produccion.

AISLAMIENTO: el proceso cambia su CWD a un directorio temporal ANTES de construir
ningun motor y NO lo restaura al final. Motivo (hallazgo verificado en runtime):
`SelfImprovementSystem` usa la ruta RELATIVA fija `data/knowledge_graph.json` y su
hilo de aprendizaje la escribe de forma asincrona. Si el CWD se restaurase antes de
que ese hilo terminase, la escritura caeria sobre el `data/` real de produccion.
El `data/` de produccion solo se LEE, mediante rutas absolutas.

QUE COMPRUEBA ESTA SONDA:
El motor DECLARA su comportamiento sin datos en `no_data_behavior()` (contrato
NORMATIVO, de solo lectura). Esta sonda contrasta esa DECLARACION contra el
comportamiento OBSERVADO en runtime. La sonda se guia por el propio contrato:
no reimplementa la lista de APIs, la lee del motor.

Partes:
  A - FORMA DEL CONTRATO: el contrato es coherente y es una copia defensiva.
  B - AUSENCIA TOTAL: almacenamiento inexistente -> arranque, lectura, deteccion.
  C - AUSENCIA PARCIAL: fichero sin una seccion -> deteccion y lectura.
  D - ESCRITURA Y RECUPERACION: escribir recrea el almacenamiento ausente.
  E - INVARIANTES: los invariantes declarados se cumplen.

Uso:
    python tests/utils/contextual_adaptation_engine/no_data_behavior_real.py
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


def note(text):
    NOTES.append(text)
    print(f"  [NOTA] {text}")


def resolve_args(engine, names):
    """Resuelve los argumentos declarados en el contrato a valores reales."""
    from utils.contextual_adaptation_engine import ContextType
    resolved = []
    for name in names or []:
        if name == "context":
            resolved.append(ContextType.PRODUCTION)
        else:
            resolved.append(name)
    return resolved


def call_api(engine, spec):
    """Invoca una API declarada en el contrato. Devuelve (ok, valor)."""
    method = getattr(engine, spec["api"], None)
    if method is None:
        return False, "API inexistente"
    try:
        value = method(*resolve_args(engine, spec.get("args", [])))
        return True, value
    except Exception as exc:  # noqa: BLE001 - la sonda DEBE detectar la excepcion
        return False, f"{type(exc).__name__}: {exc}"


def matches_kind(value, kind):
    if kind == "none":
        return value is None
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "dict":
        return isinstance(value, dict)
    if kind == "list":
        return isinstance(value, list)
    return False


# ---------------------------------------------------------------- Parte A
def parte_a_forma_contrato(engine):
    print("\n== PARTE A: FORMA DEL CONTRATO DECLARADO ==")
    contrato = engine.no_data_behavior()

    check("`no_data_behavior()` devuelve un diccionario",
          isinstance(contrato, dict), type(contrato).__name__)
    check("El contrato declara su version",
          contrato.get("version") == "2.8.8.9.5.3", repr(contrato.get("version")))
    check("El contrato declara un principio",
          isinstance(contrato.get("principle"), str) and len(contrato["principle"]) > 20)
    for seccion in ("startup", "read_apis", "write_apis", "detection", "recovery", "invariants"):
        check(f"El contrato declara la seccion `{seccion}`", seccion in contrato)

    check("`read_apis` es una lista no vacia de especificaciones",
          isinstance(contrato.get("read_apis"), list) and len(contrato["read_apis"]) > 0)
    check("Cada API de lectura declara `api` y `returns`",
          all(isinstance(s, dict) and s.get("api") and s.get("returns")
              for s in contrato.get("read_apis", [])))
    check("Cada API de escritura declara `api` y `creates`",
          all(isinstance(s, dict) and s.get("api") and s.get("creates")
              for s in contrato.get("write_apis", [])))
    check("Los invariantes declarados son una lista no vacia",
          isinstance(contrato.get("invariants"), list) and len(contrato["invariants"]) > 0)

    # Las APIs declaradas tienen que EXISTIR de verdad en el motor.
    faltan = [s["api"] for s in contrato.get("read_apis", []) + contrato.get("write_apis", [])
              if not hasattr(engine, s["api"])]
    check("Todas las APIs declaradas existen en el motor", not faltan, ", ".join(faltan))

    # COPIA DEFENSIVA: mutar lo devuelto no debe alterar el contrato de la clase.
    mutado = engine.no_data_behavior()
    mutado["startup"]["raises"] = "MUTADO"
    mutado["invariants"].append("MUTADO")
    limpio = engine.no_data_behavior()
    check("`no_data_behavior()` devuelve una COPIA defensiva",
          limpio["startup"]["raises"] is False and "MUTADO" not in limpio["invariants"])

    # El contrato es de SOLO LECTURA: consultarlo no crea ficheros.
    rutas = engine.expected_storage_paths()
    check("Consultar el contrato NO crea ficheros de persistencia",
          not any(os.path.isfile(p) for p in rutas.values()))
    return contrato


# ---------------------------------------------------------------- Parte B
def parte_b_ausencia_total(contrato):
    print("\n== PARTE B: AUSENCIA TOTAL DEL ALMACENAMIENTO ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_nodata_total_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

    # --- ARRANQUE ---
    # El arranque se OBSERVA (puede lanzar) y se contrasta con lo declarado.
    startup = contrato["startup"]
    engine = None
    excepcion_arranque = None
    try:
        engine = ContextualAdaptationEngine(data_dir=data_dir)
    except Exception as exc:  # noqa: BLE001 - la sonda DEBE detectar la excepcion
        excepcion_arranque = f"{type(exc).__name__}: {exc}"
    observado_raises = engine is None
    check("El arranque se comporta como declara `startup.raises`",
          observado_raises == bool(startup["raises"]),
          f"observado_raises={observado_raises} declarado={startup['raises']} {excepcion_arranque or ''}")
    if engine is None:
        check("El motor se puede construir con el almacenamiento ausente", False, excepcion_arranque or "")
        shutil.rmtree(tmp, ignore_errors=True)
        return None, None

    check("El arranque crea el `data_dir` si el contrato lo declara",
          os.path.isdir(data_dir) == bool(startup["creates_data_dir"]), data_dir)
    rutas = engine.expected_storage_paths()
    creados = [n for n, p in rutas.items() if os.path.isfile(p)]
    check("El arranque respeta `startup.creates_persistence_files`",
          bool(creados) == bool(startup["creates_persistence_files"]),
          f"creados={creados} declarado={startup['creates_persistence_files']}")

    # --- VALORES POR DEFECTO ---
    defaults = startup["defaults"]
    check("El default de `adaptation_rules` son las reglas integradas",
          defaults["adaptation_rules"] == "builtin_rules"
          and len(engine.adaptation_rules) == 5,
          f"adaptation_rules={len(engine.adaptation_rules)}")
    check("El default de `knowledge_base` son secciones vacias (no nulas)",
          defaults["knowledge_base"] == "empty_sections"
          and engine.knowledge_base.get("goal_adaptation_feedback") == []
          and engine.knowledge_base.get("learning_results") == []
          and isinstance(engine.knowledge_base.get("adaptation_strategies"), dict)
          and all(v == [] for v in engine.knowledge_base.get("adaptation_strategies", {}).values()))
    check("El default de `adaptation_history` es vacio",
          defaults["adaptation_history"] == "empty" and engine.adaptation_history == [])
    check("El default de `knowledge_transfers` es vacio",
          defaults["knowledge_transfers"] == "empty" and engine.knowledge_transfers == {})

    # --- API DE LECTURA ---
    print("  -- API de lectura declaradas --")
    for spec in contrato["read_apis"]:
        ok, value = call_api(engine, spec)
        check(f"`{spec['api']}` no lanza excepcion sin datos", ok, str(value)[:160])
        if ok:
            check(f"`{spec['api']}` devuelve `{spec['returns']}`",
                  matches_kind(value, spec["returns"]),
                  f"tipo={type(value).__name__}")
            if spec["api"] == "load_all_data":
                check("`load_all_data` devuelve True con el almacenamiento ausente", value is True)
            if spec["api"] == "get_engine_status":
                check("`get_engine_status` no reporta datos corruptos",
                      value.get("total_rules") == 5 and value.get("total_adaptations") == 0)

    # --- DETECCION ---
    print("  -- API de deteccion declaradas --")
    deteccion = contrato["detection"]
    ausente = engine.detect_absent_storage()
    check("`detect_absent_storage` reporta la ausencia",
          deteccion["detect_absent_storage"] == "reports_absent"
          and ausente["has_absent"] is True and ausente["absent_count"] == 4,
          f"absent_count={ausente['absent_count']}")
    secciones = engine.detect_absent_sections()
    check("`detect_absent_sections` reporta los FICHEROS ausentes",
          deteccion["detect_absent_sections_missing_files"] == "reports_absent_files"
          and set(secciones["missing_files"]) == set(rutas)
          and secciones["checked"] == [],
          f"missing_files={sorted(secciones['missing_files'])} checked={secciones['checked']}")
    check("`detect_absent_sections` no inventa secciones ausentes en ficheros inexistentes",
          deteccion["detect_absent_sections"] == "reports_missing_sections_in_existing_files"
          and secciones["absent"] == {} and secciones["absent_count"] == 0,
          f"absent={secciones['absent']} absent_count={secciones['absent_count']}")
    status = engine.get_engine_status()
    check("`get_engine_status` expone la deteccion en las claves declaradas",
          all(k in status for k in deteccion["get_engine_status"]),
          ", ".join(deteccion["get_engine_status"]))
    check("La deteccion NO escribe (no crea ficheros)",
          deteccion["detection_writes"] is False
          and not any(os.path.isfile(p) for p in rutas.values()))

    shutil.rmtree(tmp, ignore_errors=True)
    return engine, rutas


# ---------------------------------------------------------------- Parte C
def parte_c_ausencia_parcial(contrato):
    print("\n== PARTE C: AUSENCIA PARCIAL (FICHERO SIN UNA SECCION) ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_nodata_parcial_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    engine = ContextualAdaptationEngine(data_dir=data_dir)

    # Un fichero de feedback EXISTE pero le falta la seccion de datos principal.
    ruta_feedback = engine.expected_storage_paths()["goal_adaptation_feedback"]
    with open(ruta_feedback, "w", encoding="utf-8") as handle:
        json.dump({"adaptation_history": [], "last_updated": "2020-01-01T00:00:00"}, handle)

    secciones = engine.detect_absent_sections()
    ausentes = secciones["absent"].get("goal_adaptation_feedback", {})
    check("Se detecta la seccion ausente dentro de un fichero existente",
          "goal_adaptation_feedback" in ausentes
          and ausentes["goal_adaptation_feedback"].get("reason") == "section_not_found",
          json.dumps(ausentes, ensure_ascii=False))
    check("La seccion `adaptation_history` presente NO se reporta como ausente",
          "adaptation_history" not in ausentes,
          json.dumps(sorted(ausentes), ensure_ascii=False))

    # Con una seccion ausente, la lectura sigue siendo SEGURA.
    for spec in contrato["read_apis"]:
        ok, value = call_api(engine, spec)
        if not ok:
            check(f"`{spec['api']}` no lanza excepcion con una seccion ausente", False, str(value)[:160])
    check("Todas las APIs de lectura siguen siendo seguras con una seccion ausente", True)

    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- Parte D
def parte_d_escritura_y_recuperacion(contrato):
    print("\n== PARTE D: ESCRITURA Y RECUPERACION DEL ALMACENAMIENTO AUSENTE ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_nodata_write_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    engine = ContextualAdaptationEngine(data_dir=data_dir)
    rutas = engine.expected_storage_paths()

    for spec in contrato["write_apis"]:
        # Cada API de escritura se prueba sobre un motor NUEVO, con el
        # almacenamiento ausente. Asi se puede afirmar que el fichero declarado
        # lo CREA ESA MISMA llamada, y no que simplemente "ya existia".
        tmp_api = tempfile.mkdtemp(prefix="jarvis_nodata_write_api_")
        data_api = os.path.join(tmp_api, "data")
        os.makedirs(data_api, exist_ok=True)
        engine_api = ContextualAdaptationEngine(data_dir=data_api)
        rutas_api = engine_api.expected_storage_paths()

        ok, value = call_api(engine_api, spec)
        check(f"`{spec['api']}` se ejecuta sin excepcion con el almacenamiento ausente", ok, str(value)[:160])
        if ok and spec["returns"] != "none":
            check(f"`{spec['api']}` devuelve `{spec['returns']}`",
                  matches_kind(value, spec["returns"]), f"tipo={type(value).__name__}")
        crea = spec["creates"]
        esperados = crea if isinstance(crea, list) else [crea]
        for nombre in esperados:
            existe = os.path.isfile(rutas_api[nombre])
            check(f"`{spec['api']}` CREA el fichero `{nombre}` declarado",
                  existe, f"existe={existe} ruta={rutas_api[nombre]}")
        shutil.rmtree(tmp_api, ignore_errors=True)

    # Con TODAS las APIs de escritura aplicadas, el almacenamiento se recrea.
    for spec in contrato["write_apis"]:
        call_api(engine, spec)

    recuperacion = contrato["recovery"]
    despues = engine.detect_absent_storage()
    check("Tras escribir, el almacenamiento deja de reportarse como ausente",
          recuperacion["detect_absent_storage_after_write"] == "no_absent"
          and despues["has_absent"] is False and despues["absent_count"] == 0,
          f"present={despues['present']} absent_count={despues['absent_count']}")
    check("Tras escribir, el almacenamiento se detecta como presente",
          recuperacion["recreates_storage_on_write"] is True
          and set(despues["present"]) == set(rutas))

    # Los ficheros escritos son JSON VALIDO (no se escribe a medias).
    for nombre, ruta in rutas.items():
        try:
            with open(ruta, "r", encoding="utf-8") as handle:
                json.load(handle)
            check(f"El fichero `{nombre}` escrito es JSON valido", True)
        except Exception as exc:  # noqa: BLE001
            check(f"El fichero `{nombre}` escrito es JSON valido", False, str(exc)[:160])

    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- Parte E
def parte_e_invariantes(contrato):
    print("\n== PARTE E: INVARIANTES DECLARADOS ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_nodata_inv_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    engine = ContextualAdaptationEngine(data_dir=data_dir)
    rutas = engine.expected_storage_paths()

    for invariante in contrato["invariants"]:
        if invariante == "read_apis_never_raise":
            fallos = []
            for spec in contrato["read_apis"]:
                ok, value = call_api(engine, spec)
                if not ok:
                    fallos.append(f"{spec['api']}: {value}")
            check("`read_apis_never_raise`", not fallos, "; ".join(fallos))
        elif invariante == "detection_never_writes":
            engine.detect_absent_storage()
            engine.detect_absent_sections()
            engine.get_engine_status()
            check("`detection_never_writes`",
                  not any(os.path.isfile(p) for p in rutas.values()))
        elif invariante == "defaults_are_empty_not_null":
            kb = engine.knowledge_base
            # Las secciones COLECCION se vacian; las secciones MAPA se indexan por
            # contexto y sus valores por contexto quedan vacios. Ninguna es None.
            secciones_coleccion = (kb.get("goal_adaptation_feedback") == []
                                   and kb.get("learning_results") == []
                                   and kb.get("goal_adaptation_proposals") == []
                                   and kb.get("goal_validations") == [])
            secciones_mapa = (isinstance(kb.get("adaptation_strategies"), dict)
                               and isinstance(kb.get("context_patterns"), dict)
                               and all(v == [] for v in kb.get("adaptation_strategies", {}).values())
                               and all(v == [] for v in kb.get("context_patterns", {}).values()))
            vacios = (secciones_coleccion and secciones_mapa
                      and engine.adaptation_history == []
                      and engine.knowledge_transfers == {}
                      and all(kb.get(k) is not None for k in
                              ("goal_adaptation_feedback", "learning_results",
                               "adaptation_strategies", "context_patterns",
                               "success_patterns", "failure_patterns",
                               "performance_baselines", "transfer_efficiency")))
            check("`defaults_are_empty_not_null`", vacios)
        elif invariante == "writes_recreate_missing_storage":
            engine.save_adaptation_rules()
            engine.save_knowledge_base()
            engine._save_goal_adaptation_feedback()
            engine._save_goal_adaptation_learning_results()
            check("`writes_recreate_missing_storage`",
                  all(os.path.isfile(p) for p in rutas.values()),
                  ", ".join(sorted(os.path.basename(p) for p in rutas.values())))
        else:
            note(f"Invariante declarado sin verificacion automatica: {invariante}")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    # El CWD se mueve al temporal y NO se restaura: el hilo de aprendizaje de
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma asincrona
    # usando una ruta RELATIVA, y restaurarla antes de que termine contaminaria el
    # `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_nodata_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE COMPORTAMIENTO SIN DATOS (2.8.8.9.5.3)")

    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    _tmp_engine = ContextualAdaptationEngine(data_dir=os.path.join(_workdir, "data"))
    _contrato = parte_a_forma_contrato(_tmp_engine)
    parte_b_ausencia_total(_contrato)
    parte_c_ausencia_parcial(_contrato)
    parte_d_escritura_y_recuperacion(_contrato)
    parte_e_invariantes(_contrato)

    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
