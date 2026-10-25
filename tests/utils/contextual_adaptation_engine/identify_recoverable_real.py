#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de 2.8.8.9.7 — IDENTIFICACIÓN (6.1) + RECOVERY PARCIAL (7.2).

Esta sonda construye el CASO DE RECUPERACIÓN para cada una de las 27 clases de
corrupción y provee la observación REAL de qué unidades del estado sobreviven.

Se reutiliza con idéntica interfaz por:
    * test_goal_adaptation_recoverable.py  (7.1 — identificación REAL)
    * test_goal_adaptation_recovery_partial.py (7.2 — recuperación parcial REAL)

Independencia del instrumento
-----------------------------
Los payloads SANOS válidos se GENERAN con los writers reales del motor, sobre
un motor temporal, garantizando el formato real. La observación de "qué sobrevive"
usa observadores PROPIOS de esta sonda (`presente`) sobre los contenedores del
estado (`adaptation_rules`, `knowledge_base`, `adaptation_history`), y un
SENTINELA propio (`REC_MARCA_`) que no se comparte con la hoja de tests.

Ejecutable de forma aislada:
    python tests/utils/contextual_adaptation_engine/identify_recoverable_real.py
"""
import copy
import io
import contextlib
import logging
import os
import sys
import tempfile

logging.disable(logging.CRITICAL)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

with contextlib.redirect_stdout(io.StringIO()):
    import _cae_sondas_base as B
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine

# SENTINELA propio de esta sonda (diferente del de 6.2 / 6.4 / 8.x para aislar
# observaciones entre sondas).
_MARCA = "REC_MARCA_"

# Lista de fallos de contrato detectados por esta sonda (la hoja las inspecciona).
FAILURES = []

# Escenarios construidos UNA SOLA VEZ sobre el motor real.
ESCENARIOS = {cid: B.escenario_corrupto(cid, marca_prefix=_MARCA)
              for cid in B.criterios()}
CLASES = sorted(ESCENARIOS)


# ----------------------------------------------------------------- utilidades
def nuevo_motor(data_dir):
    """Construye un motor apuntando a `data_dir` (carga eager si hay ficheros)."""
    return B.nuevo_motor(data_dir)


def materializar(files, data_dir):
    """Escribe el dict `files` {filename: payload} dentro de `data_dir`."""
    return B.materializar(files, data_dir)


def firma_operativa(motor):
    """Firma canónica del estado operativo (reglas+base+history) del motor."""
    return B.firma_operativa(motor)


def _solo_letras(texto):
    """Texto con solo letras/minúsculas: normaliza marcas en la firma."""
    return B._solo_letras(texto)


# ----------------------------------------------------------- contrato (7.1 a)
def _declaraciones(motor_ref=None):
    """Lee el contrato REAL de recovery de `motor_ref` sin validar (sin mutar).

    Si no se pasa `motor_ref`, crea uno de producción (comportamiento legacy para CLI).
    En tests se debe pasar el `motor_ref` del fixture para usar el mismo data_dir temporal.
    """
    if motor_ref is None:
        motor_ref = B._motor_ref()
    rec = motor_ref.recoverable_data()
    decl = {}
    for spec in (rec.get("files") or {}).values():
        for cid, c in (spec.get("classes") or {}).items():
            decl[cid] = c
    return rec, decl


def parte_a_contrato(motor_ref):
    """(7.1-a) Valida el contrato `recoverable_data()` del motor y lo devuelve.

    Devuelve (recuperable, declaradas) y APPEND a `FAILURES` por cada anomalía
    de estructura encontrada (clausura, level, recovers, file/...).
    """
    rec = motor_ref.recoverable_data()
    files = rec.get("files") or {}
    levels = set((rec.get("levels") or {}).keys())
    policies = set((rec.get("policies") or {}).keys())
    tokens = set((rec.get("recoverable_tokens") or {}).keys())
    decl = {}
    for fname, spec in files.items():
        if not isinstance(spec, dict):
            FAILURES.append("recoverable.files['%s'] no es mapa" % fname)
            continue
        classes = spec.get("classes")
        if not isinstance(classes, dict):
            FAILURES.append("recoverable.files['%s'].classes no es mapa" % fname)
            continue
        for cid, c in classes.items():
            decl[cid] = c
            if not isinstance(c, dict):
                FAILURES.append("clase '%s' no es mapa" % cid)
                continue
            level = c.get("level")
            if level not in levels:
                FAILURES.append("clase '%s' level inesperado: %r" % (cid, level))
            policy = c.get("policy")
            if policy not in policies:
                FAILURES.append("clase '%s' policy inesperada: %r" % (cid, policy))
            if "corrupt_unit" not in c:
                FAILURES.append("clase '%s' sin 'corrupt_unit'" % cid)
            recovers = c.get("recovers")
            if not isinstance(recovers, list):
                FAILURES.append("clase '%s' recupera de forma no lista" % cid)
                continue
            for token in recovers:
                if token not in tokens:
                    FAILURES.append("clase '%s' recover token desconocido: %r" % (cid, token))
    # cobertura total: declaradas == contrato de corrupcion declarado por el motor
    ids_hoja = set()
    for spec in (motor_ref.corruption_criteria().get("files") or {}).values():
        for clase in (spec.get("corruptions") or []):
            ids_hoja.add(clase.get("id"))
    if set(decl) != ids_hoja:
        FAILURES.append("declaradas %r != hoja %r" % (sorted(decl), sorted(ids_hoja)))
    return rec, decl


# --------------------------------------------------------------------- escenarios
def escenarios():
    """{clase_id: escenario} con `files`, `marca`, `unidades{etiqueta,token,presente}`."""
    return copy.deepcopy(ESCENARIOS)


# ------------------------------------------------------------------ medición
def medir(escenario):
    """Ejecuta el caso (materializa ENTONCES construye) y mide qué sobrevive."""
    d = tempfile.mkdtemp()
    data_dir = os.path.join(d, "data")
    materializar(escenario["files"], data_dir)
    motor = nuevo_motor(data_dir)        # construct-AFTER-materialize: eager load ve el corrupto
    estado = firma_operativa(motor)
    unidades = []
    for u in escenario["unidades"]:
        try:
            presente = bool(u["presente"](motor))
        except Exception:
            presente = False
        unidades.append({"etiqueta": u["etiqueta"], "token": u["token"], "presente": presente})
    solo_estado = _solo_letras(estado)
    corrupto_en_estado = (escenario["marca"] in estado
                          or _solo_letras(escenario["marca"]) in solo_estado
                          or B.marca_presente(motor, escenario["marca"]))
    return {"unidades": unidades, "corrupto_en_estado": bool(corrupto_en_estado)}


def perdidas_de(clase, medicion):
    """Unidades de la clase cuyo token es RECUPERABLE y que NO sobrevivieron."""
    tokens = set(clase.get("recovers") or [])
    return [u for u in medicion["unidades"] if u["token"] in tokens and not u["presente"]]


def clases_pendientes(recuperable):
    """Conjunto de clases que el contrato declara PENDIENTES (no resueltas)."""
    pend = set()
    for r in recuperable.get("reconciliation") or []:
        pend |= set(r.get("pending") or [])
    return pend


# -------------------------------------------------- no-vacuidad
def _payload_sano(grupo):
    """Payload SANO válido (escrito por el writer real del motor)."""
    return copy.deepcopy(B._payload_valido(grupo))


def _escenario_doble_perdida(escenario):
    """Doble pérdida: el dato corrompido (ya materializado) + su HERMANO
    recuperable también corrompido (identidad rota del sibling).

    El motor RECUPERA el hermano cuando el fichero es un JSON válido, de modo
    que una corrupción que solo toque la fila objetivo deja vivo al sibling y la
    medición no ve pérdida alguna (la recuperación parcial la tendrá que materializar
    en 2.8.8.9.7.2). Para comprobar que la medición REACCIONA a una pérdida REAL
    hay que corromper también el hermano: al romper su identidad el motor lo
    rechaza y no lo puede recuperar, por lo que la unidad recuperable desaparece.
    """
    payload = copy.deepcopy(escenario["files"][escenario["filename"]])
    grupo = escenario["grupo"]
    rid_hermano = None
    for u in escenario["unidades"]:
        if u.get("token") == "siblings" and u["etiqueta"].startswith("regla:"):
            rid_hermano = u["etiqueta"].split(":", 1)[1]
    if rid_hermano is not None and grupo == "adaptation_rules":
        for regla in payload.get("rules", []):
            if isinstance(regla, dict) and regla.get("rule_id") == rid_hermano:
                regla["rule_id"] = escenario["marca"]  # identity rota -> rechazado
    return {"files": {escenario["filename"]: payload}, "marca": escenario["marca"],
            "unidades": escenario["unidades"]}


def control_de_no_vacio(nombre, motor_ref=None):
    """Control de no-vacuidad. Devuelve [] si pasa, [msg] si falla.

    Si se pasa `motor_ref`, usa ese motor (del fixture de test) en lugar de
    crear uno de producción. Esto garantiza que bajo pytest se use el mismo
    data_dir temporal que el resto de la suite.
    """
    fallos = []
    if nombre == "pérdida real":
        rec, decl = _declaraciones(motor_ref)
        esc = ESCENARIOS["adaptation_rules.row_not_mapping"]
        med = medir(_escenario_doble_perdida(esc))
        perdidas = perdidas_de(decl["adaptation_rules.row_not_mapping"], med)
        if not perdidas:
            fallos.append("la medición no detecta una pérdida real "
                          "(al corromperse el hermano recuperable 'rule_002' debería "
                          "perderse)")
    else:
        fallos.append("control desconocido: %s" % nombre)
    return fallos


def parte_d_no_vacio(motor_ref=None):
    """Verifica que la medición distingue datos SANOS (sin pérdida) de pérdida real."""
    rec, decl = _declaraciones(motor_ref)
    # (a) datos sanos: el hermano recuperable sobrevive -> sin pérdidas.
    esc = ESCENARIOS["adaptation_rules.row_not_mapping"]
    sanos = {"files": {esc["filename"]: _payload_sano(esc["grupo"])},
             "marca": esc["marca"], "unidades": esc["unidades"]}
    med = medir(sanos)
    perdidas = perdidas_de(decl["adaptation_rules.row_not_mapping"], med)
    if perdidas:
        FAILURES.append("no-vacuo: con datos SANOS se midieron pérdidas: %r"
                        % [u["etiqueta"] for u in perdidas])
    # (b) con una pérdida REAL la medición reacciona.
    for f in control_de_no_vacio("pérdida real", motor_ref):
        FAILURES.append("no-vacuo: " + f)


# --------------------------------------------------------------------- CLI
def _resumen():
    with contextlib.redirect_stdout(io.StringIO()):
        motor_ref = B._motor_ref()
        rec, decl = parte_a_contrato(motor_ref)
    lineas = ["IDENTIFY_RECOVERABLE: %d clases declaradas, FAILURES=%d"
              % (len(decl), len(FAILURES))]
    pend = clases_pendientes(rec)
    lineas.append("clases_pendientes (debe ser vacío): %r" % sorted(pend))
    return "\n".join(lineas)


if __name__ == "__main__":
    print(_resumen())
