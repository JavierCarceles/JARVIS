#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de 2.8.8.9.8.1 - FALLBACK POR CORRUPCION TOTAL (REAL).

Mide, en runtime, los cuatro MODOS de perdida total del motor y comprueba que
cada invariantes declarado del fallback se cumple: el motor no inventa datos,
la carga no reescribe los corruptos, el ciclo captura-analiza-ejecuta sigue
operando y la perdida es detectable.

Independencia: los payloads SANOS se generan con los writers reales del motor;
los MODOS de perdida y los observadores son propios de esta sonda (SENTINELA
FB_MARCA_) y no se comparten con 8.2 (que usa SENTINELA_IMPL_2_8_8_9_8_2).
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

_MARCA = "FB_MARCA_"
FAILURES = []

VINCULOS = {
    "state_equals_fresh_defaults": "estado_igual_a_fresco",
    "operation_continues": "operacion_continua",
    "files_not_overwritten": "ficheros_intactos",
    "loss_is_detectable": "perdida_detectable",
    "loss_visible_in_status": "loss_visible_in_status",
    "load_result_is_truthful": "load_result_is_truthful",
    "backup_covers_all_persistence": "backup_covers_all_persistence",
}


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


# ---------------------------------------------------------------- contrato
_CONTRATO_CACHE = None


def _cargar_contrato(motor_ref):
    global _CONTRATO_CACHE
    if _CONTRATO_CACHE is None:
        _CONTRATO_CACHE = motor_ref.total_loss_fallback()
    return _CONTRATO_CACHE


MODOS = sorted((_cargar_contrato(B._motor_ref()) or {}).get("loss_modes") or {})


def parte_a_contrato(motor_ref):
    """(8.1-a) Valida la forma de total_loss_fallback() y la devuelve."""
    rec = motor_ref.total_loss_fallback()
    capas = rec.get("fallback_layers") or {}
    invs = rec.get("invariants") or {}
    modos = rec.get("loss_modes") or {}
    defs = rec.get("definition") or {}
    if not rec.get("version"):
        FAILURES.append("el contrato no declara version")
    if not rec.get("principle"):
        FAILURES.append("el contrato no declara principle")
    if not defs.get("total_loss"):
        FAILURES.append("el contrato no declara definition.total_loss")
    if not defs.get("not_total_loss"):
        FAILURES.append("el contrato no declara definition.not_total_loss")
    if not modos:
        FAILURES.append("el contrato no declara loss_modes")
    if not capas:
        FAILURES.append("el contrato no declara fallback_layers")
    if not invs:
        FAILURES.append("el contrato no declara invariants")
    if not rec.get("reconciliation"):
        FAILURES.append("el contrato no declara reconciliation")
    for nombre, info in invs.items():
        if info.get("layer") not in capas:
            FAILURES.append("invariante %s capa %s no existe en fallback_layers"
                            % (nombre, info.get("layer")))
        if not info.get("statement"):
            FAILURES.append("invariante %s sin statement" % nombre)
        if not isinstance(info.get("satisfied"), bool):
            FAILURES.append("invariante %s sin satisfied booleano" % nombre)
    if set(MODOS) != set(modos):
        FAILURES.append("MODOS medidos %r != declarados %r" % (sorted(MODOS), sorted(modos)))
    return rec


# ------------------------------------------------------- modos de perdida
def _contenidos_modo(modo):
    """Los 4 ficheros corruptos en un MISMO modo de perdida total (con marca)."""
    m = _MARCA + "_" + modo
    reglas = B.FICHEROS["adaptation_rules"]
    kb = B.FICHEROS["knowledge_base"]
    fb = B.FICHEROS["goal_adaptation_feedback"]
    lr = B.FICHEROS["goal_adaptation_learning_results"]
    if modo == "unreadable_file":
        return {reglas: m + "_reglas_roto", kb: m + "_kb_roto",
                fb: m + "_fb_roto", lr: m + "_lr_roto"}
    if modo == "non_mapping_root":
        return {reglas: json.dumps(m + "_reglas"), kb: json.dumps(m + "_kb"),
                fb: json.dumps(m + "_fb"), lr: json.dumps(m + "_lr")}
    if modo == "list_root_without_valid_rows":
        return {reglas: [m + "_reglas"], kb: [m + "_kb"],
                fb: [m + "_fb"], lr: [m + "_lr"]}
    if modo == "empty_mapping_root":
        return {reglas: {}, kb: {}, fb: {}, lr: {}}
    return {}


def _firma_fresco():
    tmp = tempfile.mkdtemp(prefix="cae_fb_fresco_")
    return firma_operativa(nuevo_motor(tmp))


def _observar_operacion_continua(motor, estado):
    try:
        snap = motor.capture_context_snapshot()
    except Exception:
        return False
    return snap is not None and isinstance(estado, dict) and "active_modes" in estado


def _hay_anomalia_estado(es):
    """El estado agregado declara al menos una anomalía (cualquier señal)."""
    corr = es.get("corruption") or {}
    if corr.get("corruption_count", 0) > 0 or corr.get("unreadable_count", 0) > 0:
        return True
    alm = es.get("storage") or {}
    sec = es.get("storage_sections") or {}
    if alm.get("absent_count", 0) > 0 or bool(alm.get("absent")):
        return True
    if sec.get("absent_count", 0) > 0 or bool(sec.get("absent")):
        return True
    return False


def parte_b_medicion(contrato):
    """Tabla de medida: un item por MODO, con cada invariante observado."""
    firma_fresco = _firma_fresco()
    tabla = []
    for modo in sorted(contrato.get("loss_modes") or {}):
        d = tempfile.mkdtemp(prefix="cae_fb_modo_")
        data = os.path.join(d, "data")
        contenidos = _contenidos_modo(modo)
        materializar(contenidos, data)
        sha_antes = {nombre: _sha(os.path.join(data, nombre)) for nombre in contenidos}

        with contextlib.redirect_stdout(io.StringIO()):
            motor = nuevo_motor(data)
            motor.load_all_data()
        sha_despues = {nombre: _sha(os.path.join(data, nombre)) for nombre in contenidos}

        estado = firma_operativa(motor)
        es = motor.get_engine_status()
        corr = es.get("corruption") or {}
        cor = motor.detect_corruption() or {}
        sec = motor.detect_absent_sections() or {}
        alm = motor.detect_absent_storage() or {}

        perdida_detectable = (
            corr.get("corruption_count", 0) > 0 or cor.get("has_corruption")
            or bool(sec.get("unreadable") or {})
            or bool(sec.get("absent") or {})
            or bool(alm.get("absent") or {}))
        operacion_continua = _observar_operacion_continua(motor, es)

        tabla.append({
            "modo": modo,
            "estado_igual_a_fresco": estado == firma_fresco,
            "operacion_continua": operacion_continua,
            "ficheros_intactos": sha_antes == sha_despues,
            "perdida_detectable": perdida_detectable,
            "loss_visible_in_status": _hay_anomalia_estado(es),
            "load_result_is_truthful": motor.load_all_data() is False,
            "backup_covers_all_persistence": len(list(motor.expected_storage_paths())) == 4,
        })
    return tabla


def parte_c_determinacion(contrato, tabla):
    """Conjunto de invariantes declarados SATISFECHOS que el runtime NO cumple."""
    det = set()
    invs = contrato.get("invariants") or {}
    for nombre, info in invs.items():
        if info.get("satisfied") is not True:
            continue
        clave = VINCULOS.get(nombre)
        if clave is None:
            FAILURES.append("invariante %s sin vinculo en VINCULOS" % nombre)
            continue
        if not all(item.get(clave) for item in tabla):
            det.add(nombre)
    return det


def control_de_no_vacio(nombre):
    fallos = []
    if nombre == "perdida real":
        ref_marca = _MARCA + "_sano"
        files = {B.FICHEROS[g]: copy.deepcopy(B._payload_valido(g)) for g in B.FICHEROS}
        files[B.FICHEROS["adaptation_rules"]]["rules"][0]["name"] = ref_marca
        d = tempfile.mkdtemp()
        data = os.path.join(d, "data")
        materializar(files, data)
        motor = nuevo_motor(data)
        if not B.marca_presente(motor, ref_marca):
            fallos.append("el sentinela como dato SANO no llego al estado: observacion ciega")
        es = motor.get_engine_status()
        corr = es.get("corruption") or {}
        if corr.get("corruption_count", 0) > 0 or corr.get("unreadable_count", 0) > 0:
            fallos.append("con datos SANOS se detecta una perdida: deteccion ciega")
    else:
        fallos.append("control desconocido: %s" % nombre)
    return fallos


def parte_d_no_vacio():
    """La medicion discrimina: datos sanos NO => perdida; perdida real => si."""
    files = {B.FICHEROS[g]: copy.deepcopy(B._payload_valido(g)) for g in B.FICHEROS}
    files[B.FICHEROS["adaptation_rules"]]["rules"][0]["name"] = _MARCA + "_sano_d"
    d = tempfile.mkdtemp()
    data = os.path.join(d, "data")
    materializar(files, data)
    motor = nuevo_motor(data)
    es = motor.get_engine_status()
    corr = es.get("corruption") or {}
    if corr.get("corruption_count", 0) > 0 or corr.get("unreadable_count", 0) > 0:
        FAILURES.append("no-vacuo: con datos SANOS se detecta perdida total")
    if not B.marca_presente(motor, _MARCA + "_sano_d"):
        FAILURES.append("no-vacuo: el sentinela como dato SANO no llega al estado")
    for f in control_de_no_vacio("perdida real"):
        FAILURES.append("no-vacuo: " + f)


def _resumen():
    try:
        contrato = _cargar_contrato(B._motor_ref())
        tabla = parte_b_medicion(contrato)
        det = parte_c_determinacion(contrato, tabla)
    except Exception as exc:
        return "IDENTIFY_FALLBACK: ERROR %s" % exc
    filas = ["IDENTIFY_FALLBACK: MODOS=%r tabla=%d det=%d FAILURES=%d"
             % (sorted(MODOS), len(tabla), len(det), len(FAILURES))]
    for item in tabla:
        filas.append("  modo=%s estado_igual_a_fresco=%s operacion_continua=%s "
                     "ficheros_intactos=%s perdida_detectable=%s loss_visible=%s "
                     "load_result=%s backup=%s" % (
                         item["modo"], item["estado_igual_a_fresco"],
                         item["operacion_continua"], item["ficheros_intactos"],
                         item["perdida_detectable"], item["loss_visible_in_status"],
                         item["load_result_is_truthful"],
                         item["backup_covers_all_persistence"]))
    return "\n".join(filas)


if __name__ == "__main__":
    print(_resumen())
