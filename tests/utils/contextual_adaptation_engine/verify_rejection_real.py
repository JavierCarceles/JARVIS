#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de 2.8.8.9.6.4 — RECHAZO EN RUNTIME (REAL).

Verifica que el motor, efectivamente, RECHAZA el dato corrupto: no llega al
estado operativo, no se persiste en disco al escribir, no rompe las APIs de
lectura ni de escritura, se DETECTA y REPORTA por su clase, y el rechazo es
SELECTIVO (sobrevive lo sano; lo corrupto toma su valor por DEFECTO).

INDEPENDENCIA: los payloads SANOS se generan con los writers reales del motor;
la corrupción, los observadores (escaneo de estado / disco / ejercicio de API)
y el SENTINELA (`RECH_MARCA_`) son propios de esta sonda.

Ejecutable de forma aislada:
    python tests/utils/contextual_adaptation_engine/verify_rejection_real.py
"""
import copy
import io
import contextlib
import hashlib
import json
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

# SENTINELA PROPIO de esta sonda.
_MARCA = "RECH_MARCA_"
RF = B.FICHEROS["adaptation_rules"]

# Fallos de contrato detectados por la sonda (la hoja los inspecciona).
FAILURES = []

ESCENARIOS = {cid: B.escenario_corrupto(cid, marca_prefix=_MARCA)
              for cid in B.criterios()}
CLASES = sorted(ESCENARIOS)


# ---------------------------------------------------------------- instrumentos
def _sha(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nuevo_motor(data_dir):
    with contextlib.redirect_stdout(io.StringIO()):
        return B.nuevo_motor(data_dir)


def materializar(files, data_dir):
    B.materializar(files, data_dir)


def firma_operativa(motor):
    return B.firma_operativa(motor)


def _solo_letras(texto):
    return B._solo_letras(texto)


def escenarios():
    """{clase_id: escenario} propios de esta sonda (SENTINELA RECH_MARCA_)."""
    return copy.deepcopy(ESCENARIOS)


def _clase_declarada(motor_ref, clase_id):
    rec = motor_ref.recoverable_data()
    for spec in (rec.get("files") or {}).values():
        classes = spec.get("classes") or {}
        if clase_id in classes:
            return classes[clase_id]
    return {}


def parte_a_contrato(motor_ref):
    """Valida cobertura: los 27 escenarios cubren EXACTAMENTE las 27 clases declaradas."""
    contrato = motor_ref.corruption_criteria()
    ids = set()
    for spec in (contrato.get("files") or {}).values():
        for clase in (spec.get("corruptions") or []):
            ids.add(clase.get("id"))
    esc = escenarios()
    if set(esc) != ids:
        FAILURES.append("escenarios %r != hoja declarada %r" % (sorted(esc), sorted(ids)))
    for cid, e in esc.items():
        if not e.get("files"):
            FAILURES.append("escenario '%s' sin `files`" % cid)
        # `unidades` puede ser legítimamente [] cuando el dato corrupto es un
        # fichero/sección completa (policy=none / silently_ignored): no hay nada
        # que recuperar. Por eso no se exige.
        if not e.get("marca"):
            FAILURES.append("escenario '%s' sin marca" % cid)
    return esc


# ------------------------------------------------------------- rechazo (6.4)
def rechazo_de_una_clase(clase_id, escenario):
    """Exige: rechazo, contenido presente en disco, no propaga, no rompe APIs."""
    fallos = []
    d = tempfile.mkdtemp()
    data = os.path.join(d, "data")
    materializar(escenario["files"], data)
    path = os.path.join(data, escenario["filename"])
    sha_antes = _sha(path)

    with contextlib.redirect_stdout(io.StringIO()):
        motor = nuevo_motor(data)
    sha_post = _sha(path)
    if sha_antes != sha_post:
        fallos.append("la carga reescribió el fichero corrupto: la carga no es no destructiva")

    # DETECCIÓN (2.8.8.9.6.3) + reporte: la corrupción se nombra.
    try:
        cor = motor.detect_corruption()
    except Exception as exc:  # noqa: BLE001 - el motor no puede romper al detectar
        fallos.append("detect_corruption lanza: %s" % exc)
        cor = {}
    grp = escenario["grupo"]
    ids = {c.get("id") for c in (cor.get("corrupted", {}).get(grp, []) or [])}
    detectado = (cor.get("corruption_count", 0) > 0 or cor.get("has_corruption")
                 or escenario["clase_id"] in ids)
    if not detectado:
        fallos.append("la corrupción no se detecta por detect_corruption para `%s`" % clase_id)

    # El dato corrupto NO llega al estado operativo.
    if B.marca_presente(motor, escenario["marca"]):
        fallos.append("el dato corrupto ha llegado al estado operativo (no se rechazó)")

    # Ninguna API de LECTURA rompe.
    for fn, nombre in [
        (motor.detect_absent_storage, "detect_absent_storage"),
        (motor.detect_absent_sections, "detect_absent_sections"),
        (motor.get_engine_status, "get_engine_status"),
        (motor.recovery_report, "recovery_report"),
    ]:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            fallos.append("la API %s lanza: %s" % (nombre, exc))

    # Ninguna ESCRITURA persiste el dato corrupto (respaldo no destructivo).
    sha_previo = _sha(path)
    try:
        motor.backup_data()
    except Exception as exc:  # noqa: BLE001 - el respaldo no puede romper
        fallos.append("backup_data lanza: %s" % exc)
    sha_post_esc = _sha(path)
    if sha_previo != sha_post_esc:
        fallos.append("la escritura (backup) persistió el dato corrupto en disco")
    return fallos


# ------------------------------------------------------- selectividad (6.4 b)
def selectividad_de_una_clase(clase_id, escenario, motor_ref):
    """Exige: se conserva el sano, el corrupto toma su valor por DEFECTO."""
    fallos = []
    d = tempfile.mkdtemp()
    data = os.path.join(d, "data")
    materializar(escenario["files"], data)
    with contextlib.redirect_stdout(io.StringIO()):
        motor = nuevo_motor(data)

    # (a) el dato corrupto NO llega al estado.
    if B.marca_presente(motor, escenario["marca"]):
        fallos.append("el dato corrupto llegó al estado (rechazo no selectivo)")

    # (b) lo SANO que la corrupción no destruye sobrevive.
    decl = _clase_declarada(motor_ref, clase_id)
    tokens = set(decl.get("recovers") or [])
    for unidad in escenario["unidades"]:
        if unidad["token"] not in tokens:
            continue
        try:
            presente = bool(unidad["presente"](motor))
        except Exception:  # noqa: BLE001 - observador robusto
            presente = False
        if not presente:
            fallos.append("lo sano no sobrevive: %s" % unidad["etiqueta"])

    # (c) lo que la corrupción destruye conserva su valor por DEFECTO (no inventado).
    _comprobar_default(motor, escenario, decl, motor_ref, fallos)

    # (d) el informe de recuperación no arrastra el dato corrupto.
    try:
        rep = motor.recovery_report()
        if escenario["marca"] in json.dumps(rep, default=str):
            fallos.append("el informe de recuperación arrastra el dato corrupto")
    except Exception as exc:  # noqa: BLE001
        fallos.append("recovery_report lanza: %s" % exc)
    return fallos


def _comprobar_default(motor, escenario, decl, motor_ref, fallos):
    """Solo para NIVEL `campo` con política `default_the_field`: el campo recuperado
    vale EXACTAMENTE el default declarado (ni inventado ni corrupto)."""
    if decl.get("policy") != "default_the_field":
        return
    target = escenario.get("target", "")
    if "." not in target:
        return
    campo = target.rsplit(".", 1)[-1].rstrip("[]")
    payload = escenario["files"][escenario["filename"]]
    rules = payload.get("rules", [])
    rid = rules[0].get("rule_id") if rules else None
    regla = (motor.adaptation_rules or {}).get(rid or "")
    if regla is None:
        return  # la fila se rechazó enterita: no hay default a contrastar
    datos = regla.to_dict() if hasattr(regla, "to_dict") else dict(regla)
    fd = (motor_ref.recoverable_data().get("field_defaults") or {}).get(campo) or {}
    esperado = fd.get("value")
    if esperado == "$rule_id":
        esperado = rid
    if datos.get(campo) != esperado:
        fallos.append("campo `%s` recuperado con valor %r en vez del default declarado %r"
                      % (campo, datos.get(campo), esperado))


# --------------------------------------------------------------- no-vacuidad
def controles_de_no_vacio():
    """Nombres de los controles de no-vacuidad que la sonda expone."""
    return ["sentinela como dato valido llega al estado"]


def control_de_no_vacio(nombre):
    """Control de no-vacuidad. Devuelve [] si pasa, [msg] si falla."""
    fallos = []
    if nombre == "sentinela como dato valido llega al estado":
        # El SENTINELA como dato SANO (un `name` legítimo) DEBE llegar al estado:
        # solo así la observación "marca no en estado" de la sonda discrimina.
        ref = ESCENARIOS["adaptation_rules.priority_not_castable"]["marca"]
        payload = copy.deepcopy(B._payload_valido("adaptation_rules"))
        payload["rules"][0]["name"] = ref
        d = tempfile.mkdtemp()
        data = os.path.join(d, "data")
        materializar({RF: payload}, data)
        with contextlib.redirect_stdout(io.StringIO()):
            motor = nuevo_motor(data)
        if not B.marca_presente(motor, ref):
            fallos.append("el sentinela como dato SANO no llegó al estado: "
                           "la observación de estado es ciega")
    else:
        fallos.append("control desconocido: %s" % nombre)
    return fallos


# --------------------------------------------------------------------- CLI
def _resumen():
    return ("VERIFY_REJECTION: %d escenarios, FAILURES=%d, controles=%s"
            % (len(ESCENARIOS), len(FAILURES), controles_de_no_vacio()))


if __name__ == "__main__":
    print(_resumen())
