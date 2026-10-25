#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers COMPARTIDOS por las sondas de 2.8.8.9.6.x/.7/.8.

Este modulo NO es una sonda de test (no se carga nunca con `importlib` por los
tests): es una biblioteca de infraestructura que las propias sondas importan
para construir sus escenarios sobre el motor REAL y observadores INDEPENDIENTES.

Proporciona:
  - puesta a punto de `sys.path` (repo `src` + este directorio);
  - `nuevo_motor`, `materializar`, `firma_operatica`, `marca_*` (instrumentos
    de observacion independientes, NO declarados por el motor);
  - generacion de los *payloads validos* reales del motor (escribiendolos con
    los propios *writers* del motor y leyendolos de vuelta);
  - construccion del escenario CORRUPT de cada una de las 27 clases, totalmente
    IMPULSADA POR el contrato declarado por el propio motor
    (`corruption_criteria()` y `recoverable_data()`): asi la sonda no puede
    desviarse del formato real.

La clave de independencia: el contenido SANO de referencia lo escribe el MOTOR
(por tanto es el FORMATO REAL de verdad); la corrupcion y los observadores son
propios de la sonda.
"""
import os
import sys
import json
import copy
import shutil
import tempfile
import logging

logging.disable(logging.CRITICAL)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from utils.contextual_adaptation_engine import (  # noqa: E402
    ContextualAdaptationEngine, ContextType,
    _tipo_de_valor, _cumple_tipo,
)

# Mapeo grupo -> nombre de fichero de persistencia real del motor.
FICHEROS = {
    "adaptation_rules": "contextual_adaptation_rules.json",
    "knowledge_base": "contextual_knowledge_base.json",
    "goal_adaptation_feedback": "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results": "goal_adaptation_learning_results.json",
}

# Un trigger de contexto VALIDO (para el caso de elementos).
_TRIGGER_VALIDO = ContextType.PRODUCTION.value  # "production"

# ---------------------------------------------------------------- instrumentos
def nuevo_motor(data_dir):
    """Motor sobre un `data/` temporal: solo defaults (builtin). Vacío."""
    os.makedirs(data_dir, exist_ok=True)
    return ContextualAdaptationEngine(data_dir=str(data_dir))


def materializar(files, data_dir):
    """Escribe los ficheros `{nombre: payload|texto}` dentro de `data_dir`."""
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in files.items():
        path = os.path.join(data_dir, nombre)
        texto = contenido if isinstance(contenido, str) else json.dumps(
            contenido, ensure_ascii=False)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(texto)


def _solo_letras(texto):
    if not isinstance(texto, str):
        texto = str(texto)
    return "".join(c for c in texto if c.isalpha())


def firma_operativa(motor):
    """Snapshot OPERATIVO del estado: reglas + base + historia.

    Es el texto que usan las sondas para comprobar si una MARCA (sentinela)
    ha llegado al estado operativo. Es una observacion independiente: solo
    mira el estado, no la deteccion de corrupcion del motor.
    """
    try:
        reglas = [r.to_dict() for r in (motor.adaptation_rules or {}).values()]
        payload = {"rules": reglas, "knowledge_base": motor.knowledge_base,
                   "history": motor.adaptation_history}
        return json.dumps(payload, default=str, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensivo
        return json.dumps({"error": str(exc)})


def marca_presente(motor, marca):
    """¿La marca ha llegado al estado operativo? (True = contamación)."""
    estado = firma_operativa(motor)
    return (marca in estado or _solo_letras(marca) in _solo_letras(estado))


# ----------------------------------------------------------- payloads validos
# Filas/entradas de ejemplo que ACTÚAN como "hermanos sanos" survivientes.
_FB_HERMANO_A = {"adaptation_id": "fb_sibling_a", "success": True,
                 "original_goal_id": "g1", "adapted_goal_id": "g2",
                 "adaptation_context": {}, "execution_result": {},
                 "verification_result": {}, "improvement_analysis": {},
                 "timestamp": "2024-01-01T00:00:00"}
_FB_HERMANO_B = {"adaptation_id": "fb_sibling_b", "success": False,
                 "original_goal_id": "g3", "adapted_goal_id": "g4",
                 "adaptation_context": {}, "execution_result": {},
                 "verification_result": {}, "improvement_analysis": {},
                 "timestamp": "2024-01-02T00:00:00"}
_HISTORIA_HERMANA = {"adaptation_id": "fb_hist_sibling", "success": True,
                     "performance_impact": {}, "confidence_score": 0.9,
                     "timestamp": "2024-01-01T00:00:00"}

_LR_HERMANO_A = {"adaptation_id": "lr_sibling_a", "updated_strategies": {},
                 "convergence_metrics": {}, "learned_patterns": []}
_LR_HERMANO_B = {"adaptation_id": "lr_sibling_b", "updated_strategies": {},
                 "convergence_metrics": {}, "learned_patterns": []}
_ESTRAT_HERMANO_A = {"strategy_id": "s_sibling_a", "confidence": 0.8,
                     "success_rate": 0.9, "last_updated": "2024-01-01T00:00:00",
                     "goal_type": "g1", "expected_metrics": {}}
_ESTRAT_HERMANO_B = {"strategy_id": "s_sibling_b", "confidence": 0.95,
                     "success_rate": 0.8, "last_updated": "2024-01-01T00:00:00",
                     "goal_type": "g2", "expected_metrics": {}}

_PAYLOADS_CACHE = {}


def _payload_valido(grupo):
    """Payload VALID real (dict ya parseado) para un fichero de persistencia.

    Se genera CON LOS WRITERS DEL MOTOR sobre un motor temporal, inyectando una
    fila/entrada hermana de ejemplo en feedback y learning_results para que las
    clases de fila tengan un hermano recuperable.
    """
    if grupo in _PAYLOADS_CACHE:
        return copy.deepcopy(_PAYLOADS_CACHE[grupo])
    d = tempfile.mkdtemp(prefix="cae_base_")
    try:
        m = ContextualAdaptationEngine(data_dir=d)
        if grupo == "adaptation_rules":
            m._save_adaptation_rules()
        elif grupo == "knowledge_base":
            m.save_knowledge_base()
        elif grupo == "goal_adaptation_feedback":
            m.knowledge_base["goal_adaptation_feedback"].append(_FB_HERMANO_A)
            m.knowledge_base["goal_adaptation_feedback"].append(_FB_HERMANO_B)
            m.adaptation_history.append(_HISTORIA_HERMANA)
            m._save_goal_adaptation_feedback()
        elif grupo == "goal_adaptation_learning_results":
            m.knowledge_base["learning_results"].append(_LR_HERMANO_A)
            m.knowledge_base["learning_results"].append(_LR_HERMANO_B)
            m.knowledge_base["adaptation_strategies"]["production"].append(_ESTRAT_HERMANO_A)
            m.knowledge_base["adaptation_strategies"]["production"].append(_ESTRAT_HERMANO_B)
            m._save_goal_adaptation_learning_results()
        path = os.path.join(d, FICHEROS[grupo])
        with open(path, "r", encoding="utf-8") as handle:
            base = json.load(handle)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    _PAYLOADS_CACHE[grupo] = copy.deepcopy(base)
    return copy.deepcopy(base)


# ------------------------------------------------------ contrato por clase
_CRITERIOS_CACHE = None
_MOTOR_REF_CACHE = None


def _motor_ref():
    """Motor de referencia vacío (solo defaults). Cached: es SOLO DE LECTURA."""
    global _MOTOR_REF_CACHE
    if _MOTOR_REF_CACHE is None:
        _MOTOR_REF_CACHE = nuevo_motor(tempfile.mkdtemp(prefix="cae_ref_"))
    return _MOTOR_REF_CACHE


def criterios():
    """Dict {id: {grupo, target, violation, expected, severity, filename}} (27)."""
    global _CRITERIOS_CACHE
    if _CRITERIOS_CACHE is None:
        m = _motor_ref()
        out = []
        contrato = m.corruption_criteria()
        for grupo, spec in contrato["files"].items():
            for clase in spec.get("corruptions", []) or []:
                out.append({"id": clase["id"], "grupo": grupo,
                            "target": clase["target"], "violation": clase["violation"],
                            "expected": list(clase.get("expected", [])),
                            "severity": clase.get("severity"),
                            "filename": spec["file"]})
        _CRITERIOS_CACHE = {c["id"]: c for c in out}
    return _CRITERIOS_CACHE


def _corromper(grupo, target, violation, base, marca):
    """Devuelve una COPIA corrupta de `base` según (target, violation).

    La corrupción se construye incrustando `marca` en el punto exacto del
    FORMATO REAL (target) que exige la violación declarada. El contenido SANO
    que la corrupción no destruye se conserva íntegro.
    """
    payload = copy.deepcopy(base)

    if grupo == "adaptation_rules":
        rules = payload["rules"]
        rA = copy.deepcopy(rules[0])
        rB = copy.deepcopy(rules[1])
        rid_b = rB.get("rule_id")
        if target == "rules":
            # contenedor cambiado de forma (mapa) con un valor corrupto
            payload["rules"] = {rid_b: rB, "zzz_" + marca: marca}
        elif target == "rules[]":
            payload["rules"] = [marca, rB]
        elif target == "rules[].rule_id":
            rA.pop("rule_id", None)
            rA["description"] = marca  # valor válido (string) para no añadir más
            payload["rules"] = [rA, rB]
        elif target == "rules[].context_triggers[]":
            rA["context_triggers"] = [_TRIGGER_VALIDO, marca]
            payload["rules"] = [rA, rB]
        else:
            campo = target.rsplit(".", 1)[-1]
            if campo == "name":
                rA[campo] = [marca]  # lista en vez de string
            else:
                rA[campo] = marca
            payload["rules"] = [rA, rB]
        return payload

    if grupo == "knowledge_base":
        data = payload["data"]
        if target == "data":
            payload["data"] = marca
        elif target.endswith(".<contexto>"):
            # section_partial de context_patterns.<contexto>
            ctxo = ContextType.PRODUCTION.value
            data.setdefault("context_patterns", {})[ctxo] = marca
        elif target.startswith("data."):
            section = target[len("data."):]
            data[section] = marca  # section_not_mapping / strategies_not_mapping
        else:
            # data.<clave_desconocida> -> inesperada
            data["zzz_" + marca] = marca
        return payload

    if grupo == "goal_adaptation_feedback":
        rows = payload["goal_adaptation_feedback"]
        if target == "goal_adaptation_feedback":
            payload["goal_adaptation_feedback"] = marca
        elif target == "goal_adaptation_feedback[]":
            payload["goal_adaptation_feedback"] = [marca, copy.deepcopy(rows[1])]
        elif target == "adaptation_history":
            payload["adaptation_history"] = marca
        return payload

    if grupo == "goal_adaptation_learning_results":
        rows = payload["learning_results"]
        strategies = payload["adaptation_strategies"]
        if target == "learning_results":
            payload["learning_results"] = marca
        elif target == "learning_results[]":
            payload["learning_results"] = [marca, copy.deepcopy(rows[1])]
        elif target == "adaptation_strategies":
            payload["adaptation_strategies"] = marca
        elif target.startswith("adaptation_strategies."):
            sid = target[len("adaptation_strategies."):]
            sid = sid.split(".")[0]
            # si el primer valor es el corrupto:
            primero = next(iter(strategies)) if strategies else sid
            if violation == "missing_identity":
                strategies[primero] = {"strategy_id": primero}
            else:
                strategies[primero] = marca
        return payload

    # Fallback: deja el payload intacto (no debería ocurrir).
    return payload


def _unidades_para(grupo, recuperable_clase, base, payload):
    """Lista de unidades INDEPENDIENTES que deben sobrevivir a la corrupción.

    Cada unidad: {etiqueta, token, presente(motor)->bool}. El token pertenece
    al vocabulario cerrado de `recoverable_data()`.
    """
    recovers = recuperable_clase.get("recovers") or []
    unidades = []

    def _regla_presente(motor, rid):
        return rid in (motor.adaptation_rules or {})

    if grupo == "adaptation_rules":
        rules = base["rules"]
        rid_a = rules[0].get("rule_id")
        rid_b = rules[1].get("rule_id")
        if "container_values" in recovers:
            unidades.append({"etiqueta": "regla:%s" % rid_b, "token": "container_values",
                             "presente": lambda m, rid=rid_b: _regla_presente(m, rid)})
        if "siblings" in recovers:
            unidades.append({"etiqueta": "regla:%s" % rid_b, "token": "siblings",
                             "presente": lambda m, rid=rid_b: _regla_presente(m, rid)})
        if "row_fields" in recovers:
            # la fila corrupta se recupera con su campo por defecto: rA sobrevive
            unidades.append({"etiqueta": "fila:%s campos sanos" % rid_a, "token": "row_fields",
                             "presente": lambda m, rid=rid_a: _regla_presente(m, rid)})
        if "elements" in recovers:
            def _elems(m, rid=rid_a):
                regla = (m.adaptation_rules or {}).get(rid)
                if regla is None:
                    return False
                triggers = getattr(regla, "context_triggers", []) or []
                return any(isinstance(t, ContextType) for t in triggers)
            unidades.append({"etiqueta": "trigger valido en %s" % rid_a, "token": "elements",
                             "presente": lambda m: _elems(m)})
        return unidades

    if grupo == "knowledge_base":
        if not recovers:
            return []
        # hermano: una sección distinta a la corrompida suele sobrevivir.
        corrupt_section = None
        if target := recuperable_clase.get("_target"):
            corrupt_section = target.split(".")[1] if "." in target else None
        hermano = "success_patterns" if corrupt_section == "context_patterns" else "context_patterns"
        unidades.append({"etiqueta": "seccion:%s" % hermano, "token": "siblings",
                         "presente": lambda m, s=hermano: s in (m.knowledge_base or {})})
        return unidades

    if grupo == "goal_adaptation_feedback":
        target = recuperable_clase.get("_target", "")
        rows = base.get("goal_adaptation_feedback", [])
        hermano_id = (rows[1].get("adaptation_id") if len(rows) > 1
                      else rows[0]["adaptation_id"])
        if target == "goal_adaptation_feedback":
            # section_not_list: la sección feedback es marca; el hermano salvado
            # es adaptation_history.
            unidades.append({"etiqueta": "historia adaptativa", "token": "siblings",
                             "presente": lambda m: _hist_presente(m)})
        else:
            unidades.append({"etiqueta": "fila feedback:%s" % hermano_id, "token": "siblings",
                             "presente": lambda m, hid=hermano_id: _fb_presente(m, hid)})
        return unidades

    if grupo == "goal_adaptation_learning_results":
        target = recuperable_clase.get("_target", "")
        rows = base.get("learning_results", [])
        lr_id = (rows[1].get("adaptation_id") if len(rows) > 1
                 else rows[0]["adaptation_id"])
        if target == "learning_results":
            # learning_results_not_list: la sección es marca; el hermano salvado
            # es una estrategia aprendida.
            sid = _ESTRAT_HERMANO_B["strategy_id"]
            unidades.append({"etiqueta": "estrategia:%s" % sid, "token": "siblings",
                             "presente": lambda m, s=sid: _strategy_presente(m, s)})
        else:
            unidades.append({"etiqueta": "fila learning:%s" % lr_id, "token": "siblings",
                             "presente": lambda m, hid=lr_id: _lr_presente(m, hid)})
        return unidades

    return unidades


def _hist_presente(motor):
    hist = getattr(motor, "adaptation_history", []) or []
    return any(isinstance(x, dict) and x.get("adaptation_id") == _HISTORIA_HERMANA["adaptation_id"]
               for x in hist)


def _strategy_presente(motor, strategy_id):
    strategies = getattr(motor, "knowledge_base", {}).get("adaptation_strategies", {})
    if not isinstance(strategies, dict):
        return False
    for ctxo in strategies.values():
        if not isinstance(ctxo, list):
            continue
        for entry in ctxo:
            if isinstance(entry, dict) and entry.get("strategy_id") == strategy_id:
                return True
    return False

    return unidades


def _fb_presente(motor, adaptation_id):
    fb = motor.knowledge_base.get("goal_adaptation_feedback", [])
    if not isinstance(fb, list):
        return False
    return any(isinstance(r, dict) and r.get("adaptation_id") == adaptation_id for r in fb)


def _lr_presente(motor, adaptation_id):
    lr = motor.knowledge_base.get("learning_results", [])
    if not isinstance(lr, list):
        return False
    return any(isinstance(r, dict) and r.get("adaptation_id") == adaptation_id for r in lr)


def _secion_hermana_presente(motor, section):
    return section in (motor.knowledge_base or {})


def escenario_corrupto(clase_id, marca_prefix="MARCA"):
    """Construye el escenario corrupto INDEPENDIENTE para una clase de la queja."""
    info = criterios()[clase_id]  # dict con id, grupo, target, violation, expected
    grupo = info["grupo"]
    base = _payload_valido(grupo)
    marca = "%s_%s" % (marca_prefix, clase_id.replace(".", "_"))
    payload = _corromper(grupo, info["target"], info["violation"], base, marca)
    recup = _recoverable_clase(clase_id)
    recup_with_target = dict(recup)
    recup_with_target["_target"] = info["target"]
    unidades = _unidades_para(grupo, recup_with_target, base, payload)
    return {
        "clase_id": clase_id,
        "grupo": grupo,
        "filename": info["filename"],
        "target": info["target"],
        "violation": info["violation"],
        "expected": info["expected"],
        "severity": info["severity"],
        "marca": marca,
        "files": {info["filename"]: payload},
        "present": _seccion_presente(grupo, payload),
        "unidades": unidades,
    }


def _recoverable_clases():
    """Dict {id: clase} de `recoverable_data()` (27). Cached."""
    global _RECUPERABLE_CACHE
    if _RECUPERABLE_CACHE is None:
        m = _motor_ref()
        rec = m.recoverable_data()
        _RECUPERABLE_CACHE = {clase_id: clase
                              for spec in rec["files"].values()
                              for clase_id, clase in spec.get("classes", {}).items()}
    return _RECUPERABLE_CACHE


_RECUPERABLE_CACHE = None


def _recoverable_clase(clase_id):
    return _recoverable_clases().get(clase_id, {})


def _seccion_presente(grupo, payload):
    # una sección que está PRESENTE (clave) en el fichero corrupto.
    keys = {"adaptation_rules": "rules", "knowledge_base": "data",
            "goal_adaptation_feedback": "goal_adaptation_feedback",
            "goal_adaptation_learning_results": "learning_results"}
    return keys.get(grupo)


# ----------------------------------------------------------- utilidad de test
EFECTOS_INSEGUROS = ("value_coerced", "state_contaminated", "read_api_raises",
                     "write_api_breaks", "corruption_persisted")
