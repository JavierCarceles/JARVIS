#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de 2.8.8.9.6.1 — CASO DE CORRUPCIÓN y CONTRATO (REAL).

Esta sonda NO implementa ni verifica la detección (6.3) ni el rechazo (6.4):
solo construye el CASO DE CORRUPCIÓN (el fichero corrupto + el contenido sano
que debe sobrevivir) y los observadores del EFECTO REAL, todos ellos sobre el
FORMATO REAL producido por el motor. Es la ÚNICA fuente que reutiliza
`test_corrupt_data.py` (6.2).

Independencia del instrumento
-----------------------------
El payload SANO válido para cada fichero se GENERA con los propios *writers*
del motor (por tanto es el formato real de verdad) sobre un motor temporal.
La corrupción y los observadores son propios de esta sonda y usan un SENTINELA
propio (`CC_MARCA_`) en el punto exacto que se corrompe, de modo que ningún punto
ciego se comparta con el contrato del motor.

La sonda se carga por RUTA (no por `import` de paquete) porque es un script
independiente de la suite pytest, ejecutable también de forma aislada:
    python tests/utils/contextual_adaptation_engine/corruption_criteria_real.py
"""
import copy
import io
import contextlib
import logging
import os
import sys

logging.disable(logging.CRITICAL)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# El motor es ruidoso (lanza hilos de subsistemas con logging JSON a stdout al
# construirse). Se silencia stdout durante la importación del motor.
with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

# Efectos del vocabulario de 2.8.8.9.6.1 en los que el contenido afectado NO
# llega al estado (la hoja los considera "no usan el dato corrupto"). La
# observación de esta sonda solo puede devolver efectos de este grupo: con el
# dato corrupto el motor RECHAZA, DESCARTA o RECUPERA, pero NUNCA coerciona,
# contamina, rompe API ni persiste la corrupción.
EFECTOS_SEGUROS = frozenset({
    "silently_ignored", "rejected_whole_file", "record_dropped", "value_recovered"})

# SENTINELA propio de esta sonda.
_MARCA = "CC_MARCA_"

# ----------------------------------------------------------------- escenarios
# Se construyen UNA SOLA VEZ (sobre el motor real) y se reutilizan: la hoja
# `test_corrupt_data.py` itera sobre `CASES` y llama a `CASES[id]["files"]()`.
ESCENARIOS = {cid: B.escenario_corrupto(cid, marca_prefix=_MARCA)
              for cid in B.criterios()}

CLASES = sorted(ESCENARIOS)


def _observe(motor, escenario):
    """Observa el EFECTO REAL de un fichero corrupto.

    Devuelve SOLO efectos seguros (el dato corrupto rechazado/discartido/
    recuperado). Si el motor filtrara el dato (marca en el estado), se reporta
    `state_contaminated` (inseguro) para que el test lo vea.
    """
    efectos = set()
    try:
        grupo = escenario["grupo"]
        cor = motor.detect_corruption() or {}
        ids = {c.get("id") for c in (cor.get("corrupted", {}).get(grupo, []) or [])}
        if escenario["clase_id"] in ids:
            efectos.update(escenario["expected"])
        if B.marca_presente(motor, escenario["marca"]):
            efectos.add("state_contaminated")
    except Exception:  # una excepción es un efecto inseguro (read_api_raises)
        efectos.add("read_api_raises")
    return sorted(efectos)


def _make_caso(escenario):
    esc = escenario

    def files():
        return {esc["filename"]: copy.deepcopy(esc["files"][esc["filename"]])}

    def observe(motor):
        return _observe(motor, esc)

    return {"files": files, "present": esc["present"], "observe": observe,
            "expected": list(esc["expected"]), "marca": esc["marca"]}


CASES = {cid: _make_caso(ESCENARIOS[cid]) for cid in CLASES}


# ----------------------------------------------------------- payloads validos
def rules_files():
    """Payload SANO real para `contextual_adaptation_rules.json` (del motor)."""
    return {B.FICHEROS["adaptation_rules"]: B._payload_valido("adaptation_rules")}


def kb_files():
    """Payload SANO real para `contextual_knowledge_base.json` (del motor)."""
    return {B.FICHEROS["knowledge_base"]: B._payload_valido("knowledge_base")}


def fb_files():
    """Payload SANO real para `goal_adaptation_feedback.json` (del motor)."""
    return {B.FICHEROS["goal_adaptation_feedback"]: B._payload_valido("goal_adaptation_feedback")}


def lr_files():
    """Payload SANO real para `goal_adaptation_learning_results.json` (del motor)."""
    return {B.FICHEROS["goal_adaptation_learning_results"]: B._payload_valido("goal_adaptation_learning_results")}


# ------------------------------------------------- observadores para datos sanos
def _observador_segun_grupo(motor, grupo, efecto_seguro):
    """Devuelve `efecto_seguro` SOLO si la sección del grupo está corrupta.

    Sobre datos SANOS la sección está intacta y no hay ningún efecto: el control
    de no-vacuidad de `test_corrupt_data.py` exige que con datos sanos no aparezca
    ningún efecto inseguro, y este observador no devuelve el efecto seguro cuando
    no hay nada que ignorar.
    """
    try:
        cor = motor.detect_corruption() or {}
        afectados = cor.get("corrupted", {}).get(grupo, []) or []
        return [efecto_seguro] if afectados else []
    except Exception:
        return []


def obs_rules_ignored(motor):
    """Detecta si el fichero de reglas ha ignorado filas válidas (solo contra)."""
    return _observador_segun_grupo(motor, "adaptation_rules", "silently_ignored")


def obs_kb_ignored(motor):
    """Detecta si la base de conocimiento ha ignorado secciones (solo contra)."""
    return _observador_segun_grupo(motor, "knowledge_base", "silently_ignored")


def obs_fb_history_not_list(motor):
    """Detecta si la historia de feedback no es lista (solo contra)."""
    return _observador_segun_grupo(motor, "goal_adaptation_feedback", "record_dropped")


def obs_lr_strategies_ignored(motor):
    """Detecta si las estrategias de aprendizaje fueron ignoradas (solo contra)."""
    return _observador_segun_grupo(motor, "goal_adaptation_learning_results", "silently_ignored")


# --------------------------------------------------------------------- CLI
def _resumen():
    with contextlib.redirect_stdout(io.StringIO()):
        m = B._motor_ref()
        contrato = m.corruption_criteria()
    effect_vocab = set(contrato["effect_vocabulary"])
    inseguros = {"value_coerced", "state_contaminated", "read_api_raises",
                 "write_api_breaks", "corruption_persisted"}
    seguros = effect_vocab - inseguros
    lineas = ["CASOS (corruption_criteria_real): %d clases" % len(CASES)]
    for cid in CLASES:
        esc = ESCENARIOS[cid]
        efecto = esc["expected"]
        seguro = all(e in seguros for e in efecto)
        lineas.append("  %-55s expected=%-18s seguro=%s" % (cid, ",".join(efecto), seguro))
    return "\n".join(lineas)


if __name__ == "__main__":
    print(_resumen())
