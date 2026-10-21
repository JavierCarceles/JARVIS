#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de DETERMINACION del FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.1).

QUE MIDE
Que comportamiento REAL ofrece el motor HOY cuando TODOS los datos de
persistencia se han perdido, y que distancia hay entre ese comportamiento y el
contrato declarado en `total_loss_fallback()`.

La medicion es sobre el RUNTIME, no sobre la declaracion: la sonda monta sus
PROPIOS escenarios, con su PROPIO SENTINELA, y los observa con sus PROPIOS
observadores. El contrato que contrasta es el del motor (la parte A lo lee), de
modo que si el contrato y el runtime discrepan, la sonda lo dice.

Partes:
  A - FORMA DEL CONTRATO DEL FALLBACK.
  B - MEDICION POR MODO DE PERDIDA TOTAL: que se cumple y que no.
  C - DETERMINACION: el inventario de invariantes NO Satisfechos.
  D - NO VACUO: los controles que demuestran que la medicion discrimina.
  E - AISLAMIENTO: el `data/` de produccion queda byte a byte identico.

Uso:
    python tests/utils/contextual_adaptation_engine/identify_fallback_real.py
"""

import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PRODUCTION_DATA_DIR = os.path.join(ROOT, "data")
STORAGE_FILES = ("goal_adaptation_feedback.json", "goal_adaptation_learning_results.json",
                 "contextual_adaptation_rules.json", "contextual_knowledge_base.json")

FAILURES = []
FINDINGS = []

# ---------------------------------------------------------------- constantes
RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"

# Los cuatro ficheros de persistencia, en el orden en que los declara
# `expected_storage_paths()`.
FICHEROS = (FB, LR, RF, KB)

# SENTINELA PROPIO de esta sonda: marca el contenido SANO que la perdida total
# destruye. No comparte prefijo con el de 2.8.8.9.7.1, de modo que la medicion
# no comparte puntos ciegos con la de la recuperacion parcial.
PREFIJO = "SENTINELA_FALLBACK_2_8_8_9_8_1"
PREFIJO_SANO = "SANO_FALLBACK_2_8_8_9_8_1"

# Fila de regla SANA: el contenido que la perdida total se lleva. Lleva el
# SENTINELA en su identidad, para que se pueda comprobar que el motor NO la
# conserva y que el estado resultante es el de los defaults.
REGLA = {
    "rule_id": "regla_sentinel", "name": "regla centinela", "description": "descripcion centinela",
    "condition_pattern": "patron centinela", "adaptation_actions": ["accion centinela"],
    "context_triggers": ["production"], "confidence_threshold": 0.7,
    "priority": 1, "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}
# Fila SANA de feedback, de resultados de aprendizaje y entrada de historial.
FILA_FB = {"adaptation_id": "fb_centinela", "success": True, "timestamp": "2024-01-01T00:00:00",
            "adaptation_context": {"context_type": "production"}}
FILA_LR = {"adaptation_id": "lr_centinela", "updated_strategies": {}, "convergence_metrics": {},
            "learned_patterns": []}
HISTORIAL = {"adaptation_id": "hb_centinela", "success": True, "timestamp": "2024-01-01T00:00:00"}


# ------------------------------------------------------------- instrumentos
def check(etiqueta, ok, detalle=""):
    if ok:
        print(f"  [OK] {etiqueta}")
    else:
        FAILURES.append(etiqueta)
        print(f"  [FALLO] {etiqueta}" + (f" :: {detalle}" if detalle else ""))


def hallazgo(etiqueta, detalle=""):
    FINDINGS.append(etiqueta)
    print(f"  [HALLAZGO] {etiqueta}" + (f" :: {detalle}" if detalle else ""))


def sha256(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            digest.update(bloque)
    return digest.hexdigest()


def nuevo_motor(data_dir):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    os.makedirs(data_dir, exist_ok=True)
    return ContextualAdaptationEngine(data_dir=data_dir)


def materializar(ficheros, data_dir):
    """Escribe los ficheros del escenario en `data_dir`."""
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as handle:
            handle.write(contenido if isinstance(contenido, str)
                         else json.dumps(contenido, ensure_ascii=False))


def firma_estado(motor):
    """Firma del ESTADO OPERATIVO del motor.

    Es la MISMA forma para todos los modos, de modo que dos estados se puedan
    comparar entre si: el conjunto de reglas, la base de conocimiento y el
    historial. La comparacion es la que sostiene el invariante
    `state_equals_fresh_defaults`.
    """
    return json.dumps({
        "adaptation_rules": sorted(motor.adaptation_rules or {}),
        "knowledge_base": motor.knowledge_base,
        "adaptation_history": [dict(entrada) for entrada in (motor.adaptation_history or [])],
    }, sort_keys=True, default=str)


def firmas_ficheros(data_dir):
    """Firma (sha256) del contenido de cada fichero de persistencia."""
    return {nombre: sha256(os.path.join(data_dir, nombre)) for nombre in FICHEROS}


# ------------------------------------------------------- contenidos por modo
def _contenidos_sanos():
    """Los cuatro ficheros de persistencia con datos SANOS y CENTINELA."""
    return {
        RF: {"version": "2.0", "last_updated": "2024-01-01T00:00:00", "total_rules": 1,
             "rules": [dict(REGLA)]},
        KB: {"version": "2.0", "last_updated": "2024-01-01T00:00:00", "context_snapshots": 0,
             "adaptation_history": 0, "knowledge_transfers": 0,
             "data": {"context_patterns": {"production": [{"patron": PREFIJO}]}}},
        FB: {"goal_adaptation_feedback": [dict(FILA_FB)], "adaptation_history": [dict(HISTORIAL)],
             "last_updated": "2024-01-01T00:00:00"},
        LR: {"learning_results": [dict(FILA_LR)], "adaptation_strategies": {},
             "last_updated": "2024-01-01T00:00:00"},
    }


# Cada modo declara COMO se corrompe cada fichero. El contenido SANO es el
# mismo en todos los modos: lo que cambia es la forma de la perdida, de modo
# que el contraste entre modos no dependa de datos distintos.
def _modo_unreadable_file(sanos):
    return {nombre: "no es json <<< roto >>>" for nombre in sanos}


def _modo_non_mapping_root(sanos):
    return {nombre: '"texto que no es un mapeo"' for nombre in sanos}


def _modo_list_root_without_valid_rows(sanos):
    return {nombre: [PREFIJO, 12345] for nombre in sanos}


def _modo_empty_mapping_root(sanos):
    return {nombre: {} for nombre in sanos}


MODOS = {
    "unreadable_file": _modo_unreadable_file,
    "non_mapping_root": _modo_non_mapping_root,
    "list_root_without_valid_rows": _modo_list_root_without_valid_rows,
    "empty_mapping_root": _modo_empty_mapping_root,
}


def escenarios():
    """ESCENARIOS PROPIOS de la sonda: uno por modo de perdida total.

    Cada escenario lleva el contenido SANO (para poder comparar contra un motor
    sano) y el contenido CORRUPTO del modo.
    """
    sanos = _contenidos_sanos()
    lista = []
    for modo, constructor in MODOS.items():
        lista.append({"id": modo, "sanos": dict(sanos), "corruptos": constructor(sanos)})
    return lista


# ------------------------------------------------------------- observadores
def _observar(modo, corruptos):
    """Monta el escenario, carga el motor y devuelve lo OBSERVADO.

    Los observadores son PROPIOS de esta sonda:
      - `estado_igual_a_fresco`: el estado tras la perdida es el de un motor
        recien creado (los defaults del codigo);
      - `operacion_continua`: capturar, analizar y ejecutar siguen funcionando;
      - `ficheros_intactos`: los ficheros conservan su contenido byte a byte;
      - `perdida_detectable`: alguna API de deteccion informa de la perdida;
      - `perdida_visible_en_status`: el estado AGREGADO la informa;
      - `carga_veraz`: `load_all_data()` devuelve FALSO si no se cargo nada;
      - `respaldo_cubre_cuatro`: el respaldo cubre los cuatro ficheros.
    """
    tmp = tempfile.mkdtemp(prefix="jarvis_fallback_")
    try:
        data_dir = os.path.join(tmp, "data")
        materializar(corruptos, data_dir)
        firmas_antes = firmas_ficheros(data_dir)

        motor = nuevo_motor(data_dir)
        fresco = nuevo_motor(os.path.join(tmp, "vacio"))
        firma_fresco = firma_estado(fresco)
        firma_perdida = firma_estado(motor)

        estado_igual_a_fresco = firma_perdida == firma_fresco

        # OPERACION CONTINUA: el ciclo completo debe funcionar con los defaults.
        try:
            instantanea = motor.capture_context_snapshot()
            reglas = motor.analyze_contextual_patterns(instantanea)
            resultado = motor.execute_adaptation(instantanea, reglas)
            operacion_continua = bool(resultado is not None and resultado.success)
        except Exception as exc:  # noqa: BLE001 - un observador que falla no observa
            operacion_continua = False
            print(f"      (el ciclo lanzo {type(exc).__name__}: {exc})")

        # FICHEROS INTACTOS: la carga NO reescribe los ficheros corruptos.
        firmas_despues = firmas_ficheros(data_dir)
        ficheros_intactos = firmas_antes == firmas_despues

        # PERDIDA DETECTABLE: las APIs de deteccion la ven.
        corrupcion = motor.detect_corruption()
        secciones = motor.detect_absent_sections()
        perdida_detectable = bool(
            corrupcion.get("corrupted") or corrupcion.get("unreadable")
            or secciones.get("absent") or secciones.get("unreadable")
            or corrupcion.get("missing_files") or secciones.get("missing_files"))

        # PERDIDA VISIBLE EN EL ESTADO AGREGADO: el consumidor la ve.
        estado = motor.get_engine_status()
        anomalias = (estado["corruption"]["corruption_count"]
                     + estado["storage"]["absent_count"]
                     + estado["storage_sections"]["absent_count"])
        perdida_visible_en_status = anomalias > 0

        # CARGA VERAZ: el retorno de la carga refleja lo que OCURRIO.
        carga = motor.load_all_data()
        # Si tras la carga el estado sigue siendo el de los defaults, no se ha
        # cargado ninguna unidad de datos: la carga no puede declarar exito.
        cargo_algo = firma_estado(motor) != firma_fresco
        carga_veraz = (carga is False) or cargo_algo

        # RESPALDO CUBRE LOS CUATRO: el backup copia los cuatro ficheros. La
        # unidad de cobertura es la CLAVE de persistencia que declara el
        # propio motor (`expected_storage_paths()`), no el nombre del fichero.
        motor.backup_data()
        respaldos = os.path.join(data_dir, "backups")
        nombres = set(os.listdir(respaldos)) if os.path.isdir(respaldos) else set()
        claves = list(motor.expected_storage_paths())
        cubiertos = {clave for clave in claves
                     if any(nombre.startswith(clave + "_backup_") for nombre in nombres)}
        respaldo_cubre_cuatro = len(cubiertos) == len(claves)

        return {
            "modo": modo,
            "estado_igual_a_fresco": estado_igual_a_fresco,
            "operacion_continua": operacion_continua,
            "ficheros_intactos": ficheros_intactos,
            "perdida_detectable": perdida_detectable,
            "perdida_visible_en_status": perdida_visible_en_status,
            "carga_veraz": carga_veraz,
            "respaldo_cubre_cuatro": respaldo_cubre_cuatro,
            "carga_devolvio": carga,
            "anomalias_status": anomalias,
            "ficheros_respaldados": sorted(cubiertos),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Los invariantes del contrato y el observador que mide cada uno. El
# VINCULO es la pieza que se puede romper: si se cambiasa el vinculo, la
# medicion mediria otra cosa y la declaracion dejaria de describir el runtime.
VINCULOS = {
    "state_equals_fresh_defaults": "estado_igual_a_fresco",
    "operation_continues": "operacion_continua",
    "files_not_overwritten": "ficheros_intactos",
    "loss_is_detectable": "perdida_detectable",
    "loss_visible_in_status": "perdida_visible_en_status",
    "load_result_is_truthful": "carga_veraz",
    "backup_covers_all_persistence": "respaldo_cubre_cuatro",
}


# ---------------------------------------------------------------- Parte A
def parte_a_contrato(motor_ref):
    print("\n== PARTE A: FORMA DEL CONTRATO DEL FALLBACK ==")
    contrato = motor_ref.total_loss_fallback()

    check("El contrato declara su version", contrato.get("version") == "2.8.8.9.8.1",
          str(contrato.get("version")))
    check("El contrato declara el principio", bool(contrato.get("principle")))
    check("El contrato declara la definicion de perdida total",
          bool((contrato.get("definition") or {}).get("total_loss")))
    check("El contrato declara los modos de perdida total",
          set(contrato.get("loss_modes") or {}) == set(MODOS),
          f"declarados={sorted(contrato.get('loss_modes') or {})}")

    capas = contrato.get("fallback_layers") or {}
    invariantes = contrato.get("invariants") or {}
    check("El contrato declara las capas de fallback", bool(capas))
    check("El contrato declara los invariantes", bool(invariantes))
    check("Todo invariante declara su CAPA, que existe",
          all(inv.get("layer") in capas for inv in invariantes.values()),
          str([k for k, v in invariantes.items() if v.get("layer") not in capas]))
    check("Todo invariante declara su ENUNCIADO", all(inv.get("statement") for inv in invariantes.values()))
    check("Todo invariante declara si lo SATISFACE el runtime",
          all(isinstance(inv.get("satisfied"), bool) for inv in invariantes.values()))

    pendientes = contrato.get("pending") or []
    check("Los PENDIENTES son invariantes declarados",
          set(pendientes) <= set(invariantes),
          str(sorted(set(pendientes) - set(invariantes))))
    check("Los PENDIENTES son exactamente los invariantes NO satisfeitos",
          set(pendientes) == {k for k, v in invariantes.items() if v.get("satisfied") is False},
          f"declarados={sorted(pendientes)}")
    check("Todo invariante tiene un OBSERVADOR en la sonda",
          set(invariantes) == set(VINCULOS),
          f"contrato={sorted(invariantes)} sonda={sorted(VINCULOS)}")

    # La API es de SOLO LECTURA y devuelve una COPIA defensiva.
    estado_previo = firma_estado(motor_ref)
    copia = motor_ref.total_loss_fallback()
    copia["invariants"].clear()
    copia["pending"].append("inventado")
    check("La API devuelve una COPIA defensiva (mutarla no toca el contrato)",
          len(motor_ref.total_loss_fallback()["invariants"]) == len(invariantes))
    check("La API no altera el estado del motor", firma_estado(motor_ref) == estado_previo)

    return contrato


# ---------------------------------------------------------------- Parte B
def parte_b_medicion(contrato):
    print("\n== PARTE B: MEDICION POR MODO DE PERDIDA TOTAL ==")
    tabla = []
    for escenario in escenarios():
        observado = _observar(escenario["id"], escenario["corruptos"])
        tabla.append(observado)
        modos_ok = [k for k in VINCULOS if observado[VINCULOS[k]]]
        modos_ko = [k for k in VINCULOS if not observado[VINCULOS[k]]]
        print(f"  -- {escenario['id']}: anomalias_status={observado['anomalias_status']} "
              f"carga={observado['carga_devolvio']} "
              f"respaldados={len(observado['ficheros_respaldados'])}/{len(FICHEROS)}")
        print(f"     cumplen={sorted(modos_ok)}")
        print(f"     NO cumplen={sorted(modos_ko)}")
    return tabla


# ---------------------------------------------------------------- Parte C
def parte_c_determinacion(contrato, tabla):
    print("\n== PARTE C: DETERMINACION (invariantes NO Satisfechos) ==")
    invariantes = contrato.get("invariants") or {}
    declarados = set(contrato.get("pending") or [])

    # Un invariante NO se satisface si ALGUN modo lo incumple: el fallback debe
    # funcionar en TODOS los modos de perdida total.
    incumplidos = set()
    for nombre in invariantes:
        for observado in tabla:
            if not observado[VINCULOS[nombre]]:
                incumplidos.add(nombre)
                break

    for nombre in sorted(incumplidos):
        modo = next(o["modo"] for o in tabla if not o[VINCULOS[nombre]])
        hallazgo(f"el invariante `{nombre}` NO se satisface en el modo `{modo}`",
                 str(invariantes[nombre].get("statement")))

    check("Los invariantes NO Satisfechos coinciden con los PENDIENTES declarados",
          incumplidos == declarados,
          f"medidos={sorted(incumplidos)} declarados={sorted(declarados)}")

    for nombre in sorted(invariantes):
        modos_fallos = [o["modo"] for o in tabla if not o[VINCULOS[nombre]]]
        if not modos_fallos:
            print(f"  [OK] el invariante `{nombre}` se satisface en TODOS los modos")
    return incumplidos


# ---------------------------------------------------------------- Parte D
# Los CONTROLES de no-vacuidad de la medicion. Cada uno se puede ejecutar por
# separado y devuelve las etiquetas de las comprobaciones que han fallado, de
# modo que la suite pytest pueda exigir el resultado control a control.
CONTROLES_NO_VACIO = ("datos sanos", "perdida real", "estado intacto")


def control_de_no_vacio(nombre):
    """Ejecuta UN control de no-vacuidad. Devuelve las etiquetas fallidas."""
    desde = len(FAILURES)

    if nombre == "datos sanos":
        # D1: con datos SANOS el motor NO está en perdida total: el estado
        # difiere del de los defaults, la carga tiene exito y el estado
        # agregado no declara anomalias. Si esto fallara, la medicion no
        # distinguiria "perdida total" de "todo en orden".
        tmp = tempfile.mkdtemp(prefix="jarvis_fallback_sano_")
        try:
            data_dir = os.path.join(tmp, "data")
            materializar(_contenidos_sanos(), data_dir)
            motor = nuevo_motor(data_dir)
            fresco = nuevo_motor(os.path.join(tmp, "vacio"))
            firma_fresco = firma_estado(fresco)
            check("CONTROL `datos sanos`: el estado NO es el de los defaults",
                  firma_estado(motor) != firma_fresco)
            estado = motor.get_engine_status()
            anomalias = (estado["corruption"]["corruption_count"]
                         + estado["storage"]["absent_count"]
                         + estado["storage_sections"]["absent_count"])
            check("CONTROL `datos sanos`: el estado agregado NO declara anomalias",
                  anomalias == 0, f"anomalias={anomalias}")
            check("CONTROL `datos sanos`: la carga declara EXITO",
                  motor.load_all_data() is True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    elif nombre == "perdida real":
        # D2: con una perdida REAL el motor cae a los defaults. Es la misma
        # comprobacion que el invariante `state_equals_fresh_defaults`, pero
        # como CONTROL: demuestra que el instrumento ve la perdida.
        observado = _observar("unreadable_file", _modo_unreadable_file(_contenidos_sanos()))
        check("CONTROL `perdida real`: el motor cae a los defaults",
              observado["estado_igual_a_fresco"])
        check("CONTROL `perdida real`: la perdida es detectable",
              observado["perdida_detectable"])

    elif nombre == "estado intacto":
        # D3: el motor con datos SANOS conserva los datos: el SENTINELA llega
        # al estado. Si esto fallara, la medicion no distinguiria "no se cargo
        # nada" de "se cargo y se perdio".
        tmp = tempfile.mkdtemp(prefix="jarvis_fallback_intacto_")
        try:
            data_dir = os.path.join(tmp, "data")
            materializar(_contenidos_sanos(), data_dir)
            motor = nuevo_motor(data_dir)
            check("CONTROL `estado intacto`: la regla centinela LLEGA al estado",
                  "regla_sentinel" in (motor.adaptation_rules or {}))
            check("CONTROL `estado intacto`: el patron centinela LLEGA a la base",
                  PREFIJO in json.dumps(motor.knowledge_base, default=str))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return FAILURES[desde:]


def parte_d_no_vacio():
    print("\n== PARTE D: NO VACUO (la medicion discrimina) ==")
    for nombre in CONTROLES_NO_VACIO:
        control_de_no_vacio(nombre)


# ---------------------------------------------------------------- Parte E
def parte_e_no_contaminacion(hashes_iniciales):
    print("\n== PARTE E: NO CONTAMINACION DEL `data/` DE PRODUCCION ==")
    hashes_finales = {ruta: sha256(ruta) for ruta in hashes_iniciales}
    iguales = hashes_iniciales == hashes_finales
    check("Los ficheros de persistencia de produccion quedan byte a byte igual", iguales,
          ", ".join(sorted(os.path.basename(ruta) for ruta in hashes_iniciales)))
    if not iguales:
        for ruta in hashes_iniciales:
            if hashes_iniciales[ruta] != hashes_finales[ruta]:
                print(f"    CONTAMINADO: {ruta}")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    hashes_iniciales = {os.path.join(PRODUCTION_DATA_DIR, f): sha256(os.path.join(PRODUCTION_DATA_DIR, f))
                         for f in STORAGE_FILES}

    # El CWD se mueve al temporal y NO se restaura: el hilo de aprendizaje de
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma
    # asincrona usando una ruta RELATIVA, y restaurarla antes de que termine
    # contaminaria el `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_fallback_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE DETERMINACION DEL FALLBACK POR CORRUPCION TOTAL (2.8.8.9.8.1)")
    _ref_dir = os.path.join(tempfile.mkdtemp(prefix="jarvis_fallback_ref_"), "data")
    motor_ref = nuevo_motor(_ref_dir)

    contrato = parte_a_contrato(motor_ref)
    tabla = parte_b_medicion(contrato)
    parte_c_determinacion(contrato, tabla)
    parte_d_no_vacio()
    parte_e_no_contaminacion(hashes_iniciales)

    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for etiqueta in FAILURES:
        print(f"    - {etiqueta}")
    print(f"  Hallazgos (invariantes no Satisfechos): {len(FINDINGS)}")
    for etiqueta in FINDINGS:
        print(f"    - {etiqueta}")
    sys.exit(1 if FAILURES else 0)
