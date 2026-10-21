#!/usr/bin/env python3
"""
CRITERIOS DE CORRUPCIÓN del subsistema de persistencia de Goal (2.8.8.9.6.1).

Script de sonda independiente de la suite pytest. NO modifica `data/` de producción.

AISLAMIENTO: el proceso cambia su CWD a un directorio temporal ANTES de construir
ningún motor y NO lo restaura al final. Motivo (hallazgo verificado en runtime):
`SelfImprovementSystem` usa la ruta RELATIVA fija `data/knowledge_graph.json` y su
hilo de aprendizaje la escribe de forma asíncrona. Si el CWD se restaurase antes de
que ese hilo terminase, la escritura caería sobre el `data/` real de producción.
El `data/` de producción solo se LEE, mediante rutas absolutas.

QUÉ COMPRUEBA ESTA SONDA:
El motor DECLARA qué constituye corrupción según el FORMATO REAL en
`corruption_criteria()` (contrato NORMATIVO, de solo lectura). Esta sonda contrasta
esa DECLARACIÓN contra el comportamiento OBSERVADO en runtime: para cada clase de
corrupción declarada se inyecta el fichero corrupto de verdad y se comprueba que el
motor se comporta como el contrato dice. La sonda se guía por el propio contrato: no
reimplementa la lista de clases, la lee del motor.

Partes:
  A - FORMA DEL CONTRATO: el contrato es coherente y es una copia defensiva.
  B - CONTRASTE POR CLASE: lo OBSERVADO coincide con lo DECLARADO.
  C - COBERTURA: toda clase declarada tiene caso, todo caso está declarado, y toda
      corrupción es contenido PRESENTE (no ausencia, que es de 2.8.8.9.5.1/5.2).
  D - INVARIANTES: los invariantes declarados se cumplen.

Uso:
    python tests/utils/contextual_adaptation_engine/corruption_criteria_real.py
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

RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"

VALID_RULE = {"rule_id": "ok1", "name": "valida", "description": "d", "condition_pattern": "c",
               "adaptation_actions": ["a"], "context_triggers": ["production"],
               "confidence_threshold": .7, "priority": 1, "enabled": True, "success_rate": .5,
               "execution_count": 3, "last_execution": "2024-01-01T00:00:00",
               "adaptation_score": .4, "constraints": [], "metadata": {}, "deadline": None}


def check(label, condition, detail=""):
    status = "OK  " if condition else "FALLO"
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f" :: {detail}" if detail else ""))


def note(text):
    NOTES.append(text)
    print(f"  [NOTA] {text}")


def build_engine(files):
    """Construye un motor sobre un `data/` temporal con los ficheros indicados."""
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    tmp = tempfile.mkdtemp(prefix="jarvis_corrupt_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(data_dir, name), "w", encoding="utf-8") as handle:
            handle.write(content if isinstance(content, str)
                         else json.dumps(content, ensure_ascii=False))
    return ContextualAdaptationEngine(data_dir=data_dir), tmp


def raises(call):
    try:
        call()
        return False
    except Exception:  # noqa: BLE001 - la sonda DEBE detectar la excepcion
        return True


# ---------------------------------------------------------------- constructores
def rules_files(**over):
    """Fichero de reglas con UNA regla válida (`ok1`) y UNA corrupta (`bad1`)."""
    bad = dict(VALID_RULE, rule_id="bad1")
    bad.update(over)
    return {RF: {"version": "2.0", "last_updated": "2024-01-01T00:00:00", "total_rules": 2,
                 "rules": [dict(VALID_RULE), bad]}}


def rules_files_raw(rows):
    return {RF: {"version": "2.0", "last_updated": "2024-01-01T00:00:00",
                 "total_rules": len(rows), "rules": rows}}


def kb_files(**data):
    base = {"context_snapshots": 0, "adaptation_history": 0, "knowledge_transfers": 0}
    base.update(data)
    return {KB: {"version": "2.0", "last_updated": "2024-01-01T00:00:00",
                 "context_snapshots": 0, "adaptation_history": 0, "knowledge_transfers": 0,
                 "data": base}}


def fb_files(**payload):
    base = {"goal_adaptation_feedback": [], "adaptation_history": [], "last_updated": "2024-01-01T00:00:00"}
    base.update(payload)
    return {FB: base}


def lr_files(**payload):
    base = {"learning_results": [], "adaptation_strategies": {}, "last_updated": "2024-01-01T00:00:00"}
    base.update(payload)
    return {LR: base}


# ---------------------------------------------------------------- observadores
def obs_rules_ignored(engine):
    """Ninguna regla del fichero llega al motor y el cargador no reporta fallo."""
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: F401
    efectos = set()
    if "ok1" not in engine.adaptation_rules and engine.load_adaptation_rules() is not False:
        efectos.add("silently_ignored")
    return efectos


def obs_rules_record_dropped(engine):
    """La fila inválida se descarta y la válida del mismo fichero sí se carga."""
    efectos = set()
    if "ok1" in engine.adaptation_rules and "bad1" not in engine.adaptation_rules:
        efectos.add("record_dropped")
    if engine.load_adaptation_rules() is False:
        efectos.add("rejected_whole_file")
    return efectos


def obs_rules_rejected(engine):
    """La carga del fichero entero se aborta: también se pierde la fila válida."""
    efectos = set()
    if "ok1" not in engine.adaptation_rules:
        efectos.add("rejected_whole_file")
    return efectos


def _regla(engine):
    return engine.adaptation_rules.get("bad1")


def obs_enabled_string(engine):
    """El fichero decía `enabled: "false"`; el motor acaba con la regla ACTIVADA."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and regla.enabled is True:
        efectos.add("value_coerced")
    return efectos


def obs_actions_string(engine):
    """El fichero decía `adaptation_actions: "abc"`; el motor lo trocea."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and list(regla.adaptation_actions) == ["a", "b", "c"]:
        efectos.add("value_coerced")
    return efectos


def obs_threshold_not_numeric(engine):
    """El umbral ilegible se degrada a 0.0."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and regla.confidence_threshold == 0.0:
        efectos.add("value_coerced")
    return efectos


def obs_success_rate_not_numeric(engine):
    """La tasa de éxito ilegible se degrada a 0.0."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and regla.success_rate == 0.0:
        efectos.add("value_coerced")
    return efectos


def obs_triggers_not_list(engine):
    """Una cadena de disparadores deja la regla sin ningún disparador."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and list(regla.context_triggers) == []:
        efectos.add("value_coerced")
    return efectos


def obs_trigger_invalid_value(engine):
    """Un disparador fuera de `ContextType` se filtra en silencio."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and list(regla.context_triggers) == []:
        efectos.add("value_coerced")
    return efectos


def obs_last_execution_not_iso(engine):
    """Una marca de tiempo ilegible se degrada a None."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and regla.last_execution is None:
        efectos.add("value_coerced")
    return efectos


def obs_name_not_string(engine):
    """El nombre corrupto se conserva tal cual en la regla."""
    efectos = set()
    regla = _regla(engine)
    if regla is not None and isinstance(regla.name, dict):
        efectos.add("state_contaminated")
    return efectos


def obs_kb_ignored(engine):
    """La base conserva sus valores por defecto y el cargador no reporta fallo."""
    efectos = set()
    kb = engine.knowledge_base
    intacta = (isinstance(kb.get("context_patterns"), dict)
               and len(kb.get("context_patterns", {})) == 9
               and isinstance(kb.get("adaptation_strategies"), dict))
    if intacta and engine.load_knowledge_base() is not False:
        efectos.add("silently_ignored")
    return efectos


def obs_kb_section_not_mapping(engine):
    """La sección corrupta queda en la base y la carga se aborta."""
    efectos = set()
    if engine.knowledge_base.get("context_patterns") == "corrupto":
        efectos.add("state_contaminated")
    if engine.load_knowledge_base() is False:
        efectos.add("rejected_whole_file")
    return efectos


def obs_kb_strategies_not_mapping(engine):
    """El mapa de estrategias corrupto rompe la API pública de lectura."""
    from utils.contextual_adaptation_engine import ContextType
    efectos = set()
    if engine.knowledge_base.get("adaptation_strategies") == "corrupto":
        efectos.add("state_contaminated")
    if engine.load_knowledge_base() is False:
        efectos.add("rejected_whole_file")
    if raises(lambda: engine.get_available_strategies(ContextType.PRODUCTION)):
        efectos.add("read_api_raises")
    return efectos


def obs_kb_unexpected_key(engine):
    """La clave desconocida entra en la base de conocimiento."""
    efectos = set()
    if "clave_desconocida" in engine.knowledge_base:
        efectos.add("state_contaminated")
    return efectos


def obs_kb_section_partial(engine):
    """El contexto corrupto se conserva; los que faltan se rellenan."""
    efectos = set()
    patrones = engine.knowledge_base.get("context_patterns")
    if isinstance(patrones, dict) and patrones.get("production") == "no-lista":
        efectos.add("state_contaminated")
    return efectos


def obs_fb_section_not_list(engine):
    """La sección corrupta queda en la base y la escritura posterior revienta."""
    efectos = set()
    if engine.knowledge_base.get("goal_adaptation_feedback") == "corrupto":
        efectos.add("state_contaminated")
    if raises(lambda: engine._capture_feedback({"adaptation_id": "a1"})):
        efectos.add("write_api_breaks")
    return efectos


def obs_fb_row_not_mapping(engine):
    """La fila no válida se copia tal cual a la base."""
    efectos = set()
    if engine.knowledge_base.get("goal_adaptation_feedback") == ["basura"]:
        efectos.add("state_contaminated")
    return efectos


def obs_fb_history_not_list(engine):
    """El historial se pierde entero y sin aviso."""
    efectos = set()
    if engine.adaptation_history == []:
        efectos.add("silently_ignored")
    return efectos


def obs_lr_results_not_list(engine):
    """El valor corrupto queda en la base y al guardar se propaga al disco."""
    efectos = set()
    if engine.knowledge_base.get("learning_results") == {"k": "v"}:
        efectos.add("state_contaminated")
    engine._save_goal_adaptation_learning_results()
    ruta = os.path.join(engine.data_dir, LR)
    if os.path.isfile(ruta):
        with open(ruta, encoding="utf-8") as handle:
            guardado = json.load(handle)
        if guardado.get("learning_results") == ["k"]:
            efectos.add("corruption_persisted")
    return efectos


def obs_lr_row_not_mapping(engine):
    """La fila no válida se conserva y se vuelve a escribir."""
    efectos = set()
    if engine.knowledge_base.get("learning_results") == ["basura"]:
        efectos.add("state_contaminated")
    engine._save_goal_adaptation_learning_results()
    ruta = os.path.join(engine.data_dir, LR)
    if os.path.isfile(ruta):
        with open(ruta, encoding="utf-8") as handle:
            guardado = json.load(handle)
        if guardado.get("learning_results") == ["basura"]:
            efectos.add("corruption_persisted")
    return efectos


def obs_lr_strategies_ignored(engine):
    """No se restaura ninguna estrategia aprendida, sin aviso."""
    efectos = set()
    estrategias = engine.knowledge_base.get("adaptation_strategies")
    if isinstance(estrategias, dict) and estrategias and all(
            isinstance(v, list) and not v for v in estrategias.values()):
        efectos.add("silently_ignored")
    return efectos


def obs_lr_strategy_value_not_mapping(engine):
    """La entrada con valor inválido no se restaura."""
    efectos = set()
    estrategias = engine.knowledge_base.get("adaptation_strategies")
    if isinstance(estrategias, dict) and estrategias and all(
            isinstance(v, list) and not v for v in estrategias.values()):
        efectos.add("silently_ignored")
    return efectos


def obs_lr_strategy_missing_identity(engine):
    """La estrategia sin evidencia se restaura y se ofrece con confianza inventada."""
    from utils.contextual_adaptation_engine import ContextType
    efectos = set()
    estrategias = engine.knowledge_base.get("adaptation_strategies")
    if isinstance(estrategias, dict) and estrategias.get("idle") == [{"strategy_id": "s1"}]:
        efectos.add("state_contaminated")
    disponibles = engine.get_available_strategies(ContextType.IDLE)
    if disponibles and disponibles[0].get("confidence") == 0.5:
        efectos.add("value_coerced")
    return efectos


# ---------------------------------------------------------------- casos
# Cada caso declara el fichero corrupto, la clave de sección que SIGUE PRESENTE
# (para demostrar que es corrupción y no ausencia) y el observador del efecto real.
CASES = {
    "adaptation_rules.rules_wrong_type": {
        "files": lambda: {RF: {"version": "2.0", "last_updated": "x", "total_rules": 1,
                               "rules": {"a": 1}}},
        "present": "rules", "observe": obs_rules_ignored},
    "adaptation_rules.row_not_mapping": {
        "files": lambda: rules_files_raw([dict(VALID_RULE), "basura"]),
        "present": "rules", "observe": obs_rules_record_dropped},
    "adaptation_rules.row_missing_identity": {
        "files": lambda: rules_files_raw([dict(VALID_RULE), {"name": "sin identidad"}]),
        "present": "rules", "observe": obs_rules_record_dropped},
    "adaptation_rules.priority_not_castable": {
        "files": lambda: rules_files(priority="abc"),
        "present": "rules", "observe": obs_rules_rejected},
    "adaptation_rules.execution_count_not_castable": {
        "files": lambda: rules_files(execution_count="abc"),
        "present": "rules", "observe": obs_rules_rejected},
    "adaptation_rules.metadata_not_mapping": {
        "files": lambda: rules_files(metadata="texto"),
        "present": "rules", "observe": obs_rules_rejected},
    "adaptation_rules.actions_string": {
        "files": lambda: rules_files(adaptation_actions="abc"),
        "present": "rules", "observe": obs_actions_string},
    "adaptation_rules.enabled_string": {
        "files": lambda: rules_files(enabled="false"),
        "present": "rules", "observe": obs_enabled_string},
    "adaptation_rules.threshold_not_numeric": {
        "files": lambda: rules_files(confidence_threshold="abc"),
        "present": "rules", "observe": obs_threshold_not_numeric},
    "adaptation_rules.success_rate_not_numeric": {
        "files": lambda: rules_files(success_rate="abc"),
        "present": "rules", "observe": obs_success_rate_not_numeric},
    "adaptation_rules.triggers_not_list": {
        "files": lambda: rules_files(context_triggers="production"),
        "present": "rules", "observe": obs_triggers_not_list},
    "adaptation_rules.trigger_invalid_value": {
        "files": lambda: rules_files(context_triggers=["NO_EXISTE"]),
        "present": "rules", "observe": obs_trigger_invalid_value},
    "adaptation_rules.last_execution_not_iso": {
        "files": lambda: rules_files(last_execution="no-es-iso"),
        "present": "rules", "observe": obs_last_execution_not_iso},
    "adaptation_rules.name_not_string": {
        "files": lambda: rules_files(name={"x": 1}),
        "present": "rules", "observe": obs_name_not_string},

    "knowledge_base.data_not_mapping": {
        "files": lambda: {KB: {"version": "2.0", "last_updated": "x", "context_snapshots": 0,
                               "adaptation_history": 0, "knowledge_transfers": 0, "data": [1, 2]}},
        "present": "data", "observe": obs_kb_ignored},
    "knowledge_base.section_not_mapping": {
        "files": lambda: kb_files(context_patterns="corrupto"),
        "present": "data", "observe": obs_kb_section_not_mapping},
    "knowledge_base.strategies_not_mapping": {
        "files": lambda: kb_files(adaptation_strategies="corrupto"),
        "present": "data", "observe": obs_kb_strategies_not_mapping},
    "knowledge_base.unexpected_key": {
        "files": lambda: kb_files(clave_desconocida=1),
        "present": "data", "observe": obs_kb_unexpected_key},
    "knowledge_base.section_partial": {
        "files": lambda: kb_files(context_patterns={"production": "no-lista"}),
        "present": "data", "observe": obs_kb_section_partial},

    "goal_adaptation_feedback.section_not_list": {
        "files": lambda: fb_files(goal_adaptation_feedback="corrupto"),
        "present": "goal_adaptation_feedback", "observe": obs_fb_section_not_list},
    "goal_adaptation_feedback.row_not_mapping": {
        "files": lambda: fb_files(goal_adaptation_feedback=["basura"]),
        "present": "goal_adaptation_feedback", "observe": obs_fb_row_not_mapping},
    "goal_adaptation_feedback.history_not_list": {
        "files": lambda: fb_files(adaptation_history={"a": 1}),
        "present": "adaptation_history", "observe": obs_fb_history_not_list},

    "goal_adaptation_learning_results.learning_results_not_list": {
        "files": lambda: lr_files(learning_results={"k": "v"}),
        "present": "learning_results", "observe": obs_lr_results_not_list},
    "goal_adaptation_learning_results.row_not_mapping": {
        "files": lambda: lr_files(learning_results=["basura"]),
        "present": "learning_results", "observe": obs_lr_row_not_mapping},
    "goal_adaptation_learning_results.strategies_not_mapping": {
        "files": lambda: lr_files(adaptation_strategies="corrupto"),
        "present": "adaptation_strategies", "observe": obs_lr_strategies_ignored},
    "goal_adaptation_learning_results.strategy_value_not_mapping": {
        "files": lambda: lr_files(adaptation_strategies={"s1": "basura"}),
        "present": "adaptation_strategies", "observe": obs_lr_strategy_value_not_mapping},
    "goal_adaptation_learning_results.strategy_missing_identity": {
        "files": lambda: lr_files(adaptation_strategies={"s1": {"strategy_id": "s1"}}),
        "present": "adaptation_strategies", "observe": obs_lr_strategy_missing_identity},
}


# ---------------------------------------------------------------- Parte A
def parte_a_forma_contrato(engine):
    print("\n== PARTE A: FORMA DEL CONTRATO DECLARADO ==")
    contrato = engine.corruption_criteria()

    check("`corruption_criteria()` devuelve un diccionario",
          isinstance(contrato, dict), type(contrato).__name__)
    check("El contrato declara su version",
          contrato.get("version") == "2.8.8.9.6.1", repr(contrato.get("version")))
    check("El contrato declara un principio",
          isinstance(contrato.get("principle"), str) and len(contrato["principle"]) > 20)
    for seccion in ("boundary", "effect_vocabulary", "severity_vocabulary",
                    "violation_vocabulary", "files", "invariants"):
        check(f"El contrato declara la seccion `{seccion}`", seccion in contrato)

    check("El contrato declara la frontera con 2.8.8.9.5.1/5.2",
          isinstance(contrato.get("boundary"), dict)
          and isinstance(contrato["boundary"].get("not_corruption"), list)
          and len(contrato["boundary"]["not_corruption"]) > 0)
    check("Todo caso de la frontera tiene dueño (2.8.8.9.5.1/5.2)",
          all(c.get("owner", "").startswith("2.8.8.9.5.") and c.get("reason")
              for c in contrato["boundary"].get("not_corruption", [])))

    check("`files` es un diccionario no vacio",
          isinstance(contrato.get("files"), dict) and len(contrato["files"]) > 0)
    for clave, spec in contrato.get("files", {}).items():
        check(f"`files.{clave}` declara fichero, escritor y cargador",
              bool(spec.get("file")) and bool(spec.get("writer")) and bool(spec.get("loader")))
        check(f"`files.{clave}.real_format` declara el formato real",
              isinstance(spec.get("real_format"), dict)
              and "root" in spec["real_format"] and "sections" in spec["real_format"])
        check(f"`files.{clave}.corruptions` es una lista no vacia",
              isinstance(spec.get("corruptions"), list) and len(spec["corruptions"]) > 0)

    # La seccion que se corrompe tiene que existir de verdad en el formato real.
    for clave, spec in contrato.get("files", {}).items():
        secciones = set(spec.get("real_format", {}).get("sections", {}))
        for clase in spec.get("corruptions", []):
            objetivo = str(clase.get("target", "")).split(".")[0].split("[")[0]
            check(f"La clase `{clase.get('id')}` apunta a una seccion del formato real",
                  objetivo in secciones, f"target={clase.get('target')} secciones={sorted(secciones)}")

    efectos = set(contrato.get("effect_vocabulary", {}))
    severidades = set(contrato.get("severity_vocabulary", {}))
    violaciones = set(contrato.get("violation_vocabulary", {}))
    check("El vocabulario de efectos es no vacio", bool(efectos))
    check("El vocabulario de severidad es no vacio", bool(severidades))
    check("El vocabulario de violaciones es no vacio", bool(violaciones))

    for clave, spec in contrato.get("files", {}).items():
        for clase in spec.get("corruptions", []):
            check(f"La clase `{clase.get('id')}` declara target, violation, severity y expected",
                  all(clase.get(k) not in (None, "") for k in ("target", "violation", "severity", "expected"))
                  and isinstance(clase.get("expected"), list) and len(clase["expected"]) > 0)
            check(f"La clase `{clase.get('id')}` usa un efecto declarado",
                  bool(clase.get("expected")) and set(clase["expected"]) <= efectos,
                  f"efectos={sorted(clase.get('expected', []))}")
            check(f"La clase `{clase.get('id')}` usa una severidad declarada",
                  clase.get("severity") in severidades, repr(clase.get("severity")))
            check(f"La clase `{clase.get('id')}` usa una violacion declarada",
                  clase.get("violation") in violaciones, repr(clase.get("violation")))

    # Los identificadores de clase son unicos en todo el contrato.
    ids = [c.get("id") for spec in contrato.get("files", {}).values()
           for c in spec.get("corruptions", [])]
    check("Los identificadores de clase son unicos", len(ids) == len(set(ids)),
          f"{len(ids)} clases, {len(set(ids))} unicas")

    # COPIA DEFENSIVA: mutar lo devuelto no debe alterar el contrato de la clase.
    mutado = engine.corruption_criteria()
    mutado["files"]["adaptation_rules"]["corruptions"].clear()
    mutado["invariants"].append("MUTADO")
    limpio = engine.corruption_criteria()
    check("`corruption_criteria()` devuelve una COPIA defensiva",
          len(limpio["files"]["adaptation_rules"]["corruptions"]) == len(
              contrato["files"]["adaptation_rules"]["corruptions"])
          and "MUTADO" not in limpio["invariants"])

    # El contrato es de SOLO LECTURA: consultarlo no crea ficheros.
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    tmp = tempfile.mkdtemp(prefix="jarvis_corrupt_ro_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    solo_lectura = ContextualAdaptationEngine(data_dir=data_dir)
    rutas = solo_lectura.expected_storage_paths()
    solo_lectura.corruption_criteria()
    check("`corruption_criteria()` no crea ficheros",
          not any(os.path.isfile(p) for p in rutas.values()))
    shutil.rmtree(tmp, ignore_errors=True)

    return contrato


# ---------------------------------------------------------------- Parte B
def parte_b_contraste(contrato):
    print("\n== PARTE B: CONTRASTE POR CLASE (DECLARADO vs OBSERVADO) ==")
    for clave, spec in contrato.get("files", {}).items():
        for clase in spec.get("corruptions", []):
            cid = clase.get("id")
            caso = CASES.get(cid)
            if caso is None:
                check(f"La clase `{cid}` tiene caso en la sonda", False, "sin caso")
                continue
            engine, tmp = build_engine(caso["files"]())
            try:
                observado = caso["observe"](engine)
            except Exception as exc:  # noqa: BLE001 - la sonda DEBE detectar la excepcion
                observado = {f"EXCEPCION:{type(exc).__name__}"}
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            esperado = set(clase.get("expected", []))
            check(f"`{cid}`: lo observado coincide con lo declarado",
                  observado == esperado,
                  f"declarado={sorted(esperado)} observado={sorted(observado)}")


# ---------------------------------------------------------------- Parte C
def parte_c_cobertura(contrato):
    print("\n== PARTE C: COBERTURA ==")
    declarados = [c.get("id") for spec in contrato.get("files", {}).values()
                  for c in spec.get("corruptions", [])]
    sin_caso = [cid for cid in declarados if cid not in CASES]
    check("Toda clase declarada tiene caso en la sonda", not sin_caso, ", ".join(sin_caso))
    sin_declarar = [cid for cid in CASES if cid not in declarados]
    check("Todo caso de la sonda esta declarado en el contrato", not sin_declarar, ", ".join(sin_declarar))

    # La corrupcion es contenido PRESENTE: la seccion no puede reportarse ausente.
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    for clave, spec in contrato.get("files", {}).items():
        for clase in spec.get("corruptions", []):
            cid = clase.get("id")
            caso = CASES.get(cid)
            if caso is None:
                continue
            engine, tmp = build_engine(caso["files"]())
            try:
                secciones = engine.detect_absent_sections()
                ausentes = secciones.get("absent", {}).get(clave, {})
                check(f"`{cid}`: el contenido corrupto esta PRESENTE (no es ausencia)",
                      caso["present"] not in ausentes,
                      f"seccion={caso['present']} ausentes={sorted(ausentes)}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- Parte D
def parte_d_invariantes(contrato):
    print("\n== PARTE D: INVARIANTES ==")
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    tmp = tempfile.mkdtemp(prefix="jarvis_corrupt_inv_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    engine = ContextualAdaptationEngine(data_dir=data_dir)
    rutas = engine.expected_storage_paths()

    for invariante in contrato["invariants"]:
        if invariante == "corruption_is_never_absence":
            fallos = []
            for clave, spec in contrato.get("files", {}).items():
                for clase in spec.get("corruptions", []):
                    caso = CASES.get(clase.get("id"))
                    if caso is None:
                        continue
                    motor, tmp2 = build_engine(caso["files"]())
                    try:
                        ausentes = motor.detect_absent_sections().get("absent", {}).get(clave, {})
                        if caso["present"] in ausentes:
                            fallos.append(clase.get("id"))
                    finally:
                        shutil.rmtree(tmp2, ignore_errors=True)
            check("`corruption_is_never_absence`", not fallos, ", ".join(fallos))
        elif invariante == "every_corruption_declares_target_violation_severity_and_effects":
            fallos = [c.get("id") for spec in contrato.get("files", {}).values()
                      for c in spec.get("corruptions", [])
                      if not all(c.get(k) not in (None, "") for k in
                                 ("target", "violation", "severity", "expected"))]
            check("`every_corruption_declares_target_violation_severity_and_effects`",
                  not fallos, ", ".join(fallos))
        elif invariante == "every_expected_effect_belongs_to_the_effect_vocabulary":
            vocabulario = set(contrato.get("effect_vocabulary", {}))
            fallos = [c.get("id") for spec in contrato.get("files", {}).values()
                      for c in spec.get("corruptions", [])
                      if not set(c.get("expected", [])) <= vocabulario]
            check("`every_expected_effect_belongs_to_the_effect_vocabulary`",
                  not fallos, ", ".join(fallos))
        elif invariante == "every_corruption_is_covered_by_the_runtime_probe":
            declarados = [c.get("id") for spec in contrato.get("files", {}).values()
                          for c in spec.get("corruptions", [])]
            fallos = [cid for cid in declarados if cid not in CASES]
            check("`every_corruption_is_covered_by_the_runtime_probe`", not fallos, ", ".join(fallos))
        elif invariante == "detection_is_read_only":
            engine.corruption_criteria()
            check("`detection_is_read_only`",
                  not any(os.path.isfile(p) for p in rutas.values()))
        else:
            note(f"Invariante declarado sin verificacion automatica: {invariante}")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    # El CWD se mueve al temporal y NO se restaura: el hilo de aprendizaje de
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma asincrona
    # usando una ruta RELATIVA, y restaurarla antes de que termine contaminaria el
    # `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_corrupt_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE CRITERIOS DE CORRUPCION (2.8.8.9.6.1)")

    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    _tmp_engine = ContextualAdaptationEngine(data_dir=os.path.join(_workdir, "data"))
    _contrato = parte_a_forma_contrato(_tmp_engine)
    parte_b_contraste(_contrato)
    parte_c_cobertura(_contrato)
    parte_d_invariantes(_contrato)

    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
