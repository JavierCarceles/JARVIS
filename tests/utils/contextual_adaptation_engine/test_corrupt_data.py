#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de DATOS CORRUPTOS (2.8.8.9.6.2).

Esta hoja crea UNICAMENTE el CASO DE CORRUPCION: el escenario de un fichero de
persistencia con contenido corrupto y el contrato que ese dato corrupto debe
cumplir. NO implementa la deteccion (2.8.8.9.6.3), NO verifica el rechazo en
runtime (2.8.8.9.6.4) y NO toca la recuperacion parcial (2.8.8.9.7) ni el
fallback por corrupcion total (2.8.8.9.8).

FUENTES DEL CASO
- CONTRATO DECLARADO en 2.8.8.9.6.1: `corruption_criteria()` declara las 27
  clases de corrupcion segun el FORMATO REAL de la persistencia, con su
  `target`, `violation`, `severity` y `expected`, y el vocabulario cerrado de
  efectos observables.
- ESCENARIOS Y OBSERVADORES: `corruption_criteria_real.py` (mismo directorio).
  Su registro `CASES` es la UNICA fuente de los ficheros corruptos y de los
  observadores del efecto real. Este modulo REUTILIZA ese registro y no lo
  duplica: son los mismos escenarios que contrasta la sonda de 2.8.8.9.6.1.

CONTRATO QUE ESTE MODULO FIJA
1. El CASO es REPRODUCIBLE y FIDEL: con el fichero corrupto presente, el motor
   ARRANCA sin lanzar, el contenido corrupto sigue PRESENTE y el fichero
   corrupto NO se reescribe al cargar. La corrupcion no es AUSENCIA: no puede
   reportarse como fichero ausente (2.8.8.9.5.1) ni como seccion ausente
   (2.8.8.9.5.2). Es la frontera declarada en 2.8.8.9.6.1.
2. El dato corrupto NO se usa como si fuera valido. El vocabulario de efectos
   de 2.8.8.9.6.1 separa los efectos en los que el contenido afectado NO llega
   al estado (`silently_ignored`, `rejected_whole_file`, `record_dropped`) de los
   efectos en los que SI llega (valor coercionado, estado contaminado), rompe
   una API de lectura o de escritura, o se propaga al disco. Este modulo exige
   que el segundo grupo NO aparezca: es el contrato de 2.8.8.9.6.3 (deteccion en
   la via de carga) verificado por 2.8.8.9.6.4.

   La exigencia se formula sobre el EFECTO ("el dato corrupto no llega al
   estado"), no sobre el nombre exacto del efecto ni sobre la severidad, para
   que el test siga siendo valido cuando 2.8.8.9.6.3 cambie la forma concreta
   del efecto. Los 17 casos que exigian la deteccion de 2.8.8.9.6.3 se cumplen
   con la deteccion implementada en la via de carga.

AISLAMIENTO
Todos los motores se crean con `data_dir` temporal (`tmp_path`), asi que el
`data/` de produccion no se lee ni se escribe. La sesion completa se ejecuta
dentro del sandbox de CWD de `tests/conftest.py`, de modo que las rutas
RELATIVAS de los subsistemas ajenos (`data/knowledge_graph.json`,
`data/learning_history.json`, `data/improvement_rules.json`,
`models/learning_models`) caen en el temporal y no en el repo. El propio modulo
incluye ademas un TEST DE GUARDA que comprueba por sha256 que los ficheros de
produccion vigilados no cambian.
"""

import hashlib
import importlib.util
import json
import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402


def _cargar_sonda():
    """Carga el registro de escenarios de la sonda de 2.8.8.9.6.1.

    Se carga por RUTA (no por `import` de paquete) porque la sonda es un script
    independiente de la suite pytest: de ella solo se reutiliza `CASES`.
    """
    ruta = os.path.join(_TESTS_DIR, "corruption_criteria_real.py")
    spec = importlib.util.spec_from_file_location("corruption_criteria_real", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


SONDA = _cargar_sonda()

# Registro de escenarios de la sonda: la UNICA fuente de los ficheros corruptos.
CASES = SONDA.CASES

# Efectos del vocabulario de 2.8.8.9.6.1 en los que el contenido corrupto NO
# llega al estado: la fila se descarta, el fichero se rechaza o la seccion se
# ignora. El dato corrupto, en estos casos, no se usa como si fuera valido.
EFECTOS_QUE_NO_USAN_EL_DATO_CORRUPTO = frozenset({
    "silently_ignored", "rejected_whole_file", "record_dropped"})

# Efectos en los que el dato corrupto SI llega al estado o se propaga: se
# coacciona a otro valor, se contamina el estado, se rompe una API de lectura o
# de escritura, o se vuelve a escribir al disco.
EFECTOS_QUE_SI_USAN_EL_DATO_CORRUPTO = frozenset({
    "value_coerced", "state_contaminated", "read_api_raises",
    "write_api_breaks", "corruption_persisted"})

# Ficheros de `data/` de PRODUCCION que esta suite no debe tocar: los 4 de
# persistencia del motor y los de los subsistemas ajenos que el motor instancia.
FICHEROS_DE_PERSISTENCIA = (
    "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results.json",
    "contextual_adaptation_rules.json",
    "contextual_knowledge_base.json",
)
FICHEROS_DE_SUBSISTEMAS_AJENOS = (
    "knowledge_graph.json",
    "learning_history.json",
    "improvement_rules.json",
    "adaptive_performance.json",
)
PRODUCTION_DATA_DIR = os.path.join(_ROOT_DIR, "data")

# CONTROL: los MISMOS ficheros de persistencia con payload VALIDO. Sirve para
# demostrar que el contrato discrimina: con datos sanos no hay ningun efecto
# inseguro, y con el dato corrupto si. Los payloads validos los construye la
# propia sonda de 2.8.8.9.6.1 (no se duplican aqui).
CASOS_VALIDOS = {
    "adaptation_rules": lambda: SONDA.rules_files(),
    "knowledge_base": lambda: SONDA.kb_files(),
    "goal_adaptation_feedback": lambda: SONDA.fb_files(),
    "goal_adaptation_learning_results": lambda: SONDA.lr_files(),
}

CLASES = sorted(CASES)


# ------------------------------------------------------------------ utilidades
def _materializar_caso(caso, tmp_path):
    """Escribe el escenario corrupto en un `data/` temporal y devuelve sus rutas."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    rutas = {}
    for nombre, contenido in caso["files"]().items():
        ruta = data_dir / nombre
        ruta.write_text(
            contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False),
            encoding="utf-8")
        rutas[nombre] = ruta
    return data_dir, rutas


def _motor_con_caso(caso, tmp_path):
    """Motor construido sobre un `data/` temporal con el fichero corrupto."""
    data_dir, _ = _materializar_caso(caso, tmp_path)
    return ContextualAdaptationEngine(data_dir=str(data_dir))


def _motor_sobre(data_dir):
    """Motor construido sobre un `data/` ya materializado."""
    return ContextualAdaptationEngine(data_dir=str(data_dir))


def _claves_declaradas(tmp_path):
    """Ids de las clases de corrupcion declaradas en el contrato del motor."""
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path))
    contrato = motor.corruption_criteria()
    return sorted(clase["id"] for spec in contrato["files"].values()
                  for clase in spec["corruptions"]), contrato


def _sha256(ruta):
    if not os.path.isfile(ruta):
        return None
    with open(ruta, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _hashes_de_produccion():
    return {nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre))
            for nombre in FICHEROS_DE_PERSISTENCIA + FICHEROS_DE_SUBSISTEMAS_AJENOS}


# ================================================================ EL CASO
@pytest.mark.parametrize("clase_id", CLASES)
def test_el_caso_de_corrupcion_arranca_el_motor_y_es_contenido_presente(clase_id, tmp_path):
    """El motor arranca con el fichero corrupto y el contenido sigue PRESENTE.

    La corrupcion NO es AUSENCIA: el fichero no puede reportarse como ausente
    (2.8.8.9.5.1) ni su seccion como ausente (2.8.8.9.5.2). La deteccion de
    corrupcion es de 2.8.8.9.6.3 y no puede reclasificar el dato como ausencia.
    """
    caso = CASES[clase_id]
    clave = clase_id.split(".")[0]
    motor = _motor_con_caso(caso, tmp_path)
    assert motor is not None

    almacenamiento = motor.detect_absent_storage()
    assert clave not in almacenamiento["absent"], clase_id
    assert clave in almacenamiento["present"], clase_id

    secciones = motor.detect_absent_sections()
    assert clave not in secciones["missing_files"], clase_id
    assert clave not in secciones["unreadable"], clase_id
    ausentes = secciones["absent"].get(clave, {})
    assert caso["present"] not in ausentes, f"{clase_id}: ausentes={sorted(ausentes)}"


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_caso_de_corrupcion_no_se_reescribe_al_cargar(clase_id, tmp_path):
    """Cargar el fichero corrupto no lo normaliza ni lo sobrescribe."""
    caso = CASES[clase_id]
    data_dir, rutas = _materializar_caso(caso, tmp_path)
    antes = {nombre: _sha256(str(ruta)) for nombre, ruta in rutas.items()}
    motor = _motor_sobre(data_dir)
    motor.detect_absent_storage()
    motor.detect_absent_sections()
    motor.get_engine_status()
    despues = {nombre: _sha256(str(ruta)) for nombre, ruta in rutas.items()}
    assert antes == despues, clase_id


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_dato_corrupto_no_se_usa_como_si_fuera_valido(clase_id, tmp_path):
    """El contenido corrupto no puede llegar al estado ni propagarse.

    Es el CONTRATO de 2.8.8.9.6.3 (deteccion en la via de carga) verificado por
    2.8.8.9.6.4. Con la deteccion implementada, el motor descarta la fila o la
    seccion corrupta en lugar de coercionar el valor, contaminar el estado,
    romper una API de lectura o de escritura o escribir la corrupcion de nuevo
    en disco.
    """
    caso = CASES[clase_id]
    motor = _motor_con_caso(caso, tmp_path)
    try:
        observado = set(caso["observe"](motor))
    except Exception as exc:  # noqa: BLE001 - una excepcion ES un efecto inseguro
        raise AssertionError(
            f"{clase_id}: el observador lanzo {type(exc).__name__}: {exc}") from exc
    inseguros = observado & EFECTOS_QUE_SI_USAN_EL_DATO_CORRUPTO
    assert not inseguros, f"{clase_id}: observados={sorted(observado)}"


# ================================================================ CONTRATO
def test_el_control_con_payload_valido_no_muestra_efectos_inseguros(tmp_path):
    """CONTROL: con los MISMOS ficheros de persistencia pero payload VALIDO.

    Ningun efecto inseguro puede aparecer. Si este control fallara, el
    contrato no distinguiria el dato corrupto del dato sano y el test de
    rechazo no probaria nada.
    """
    for clave, constructor in CASOS_VALIDOS.items():
        data_dir = tmp_path / clave
        data_dir.mkdir(parents=True, exist_ok=True)
        for nombre, contenido in constructor().items():
            (data_dir / nombre).write_text(json.dumps(contenido, ensure_ascii=False),
                                           encoding="utf-8")
        motor = _motor_sobre(data_dir)
        for observador in (SONDA.obs_rules_ignored, SONDA.obs_kb_ignored,
                           SONDA.obs_fb_history_not_list,
                           SONDA.obs_lr_strategies_ignored):
            observado = set(observador(motor))
            inseguros = observado & EFECTOS_QUE_SI_USAN_EL_DATO_CORRUPTO
            assert not inseguros, f"{clave}: observados={sorted(observado)}"


def test_la_sonda_y_el_contrato_cubren_las_mismas_clases(tmp_path):
    """Lo declarado en el motor y lo cubierto por los escenarios coincide."""
    declaradas, contrato = _claves_declaradas(tmp_path)
    assert declaradas == sorted(CASES)
    assert len(declaradas) == len(set(declaradas))
    assert set(contrato["effect_vocabulary"]) == (EFECTOS_QUE_NO_USAN_EL_DATO_CORRUPTO
                                                   | EFECTOS_QUE_SI_USAN_EL_DATO_CORRUPTO)


def test_el_vocabulario_de_efectos_esta_clasificado_como_usable_o_inseguro(tmp_path):
    """Cada efecto del vocabulario cerrado esta clasificado en un solo grupo."""
    _, contrato = _claves_declaradas(tmp_path)
    vocabulario = set(contrato["effect_vocabulary"])
    assert not (EFECTOS_QUE_NO_USAN_EL_DATO_CORRUPTO & EFECTOS_QUE_SI_USAN_EL_DATO_CORRUPTO)
    assert (EFECTOS_QUE_NO_USAN_EL_DATO_CORRUPTO | EFECTOS_QUE_SI_USAN_EL_DATO_CORRUPTO) == vocabulario


def test_cada_clase_declarada_tiene_escenario_y_efectos_del_vocabulario(tmp_path):
    """Todo escenario materializa una clase declarada del contrato."""
    declaradas, contrato = _claves_declaradas(tmp_path)
    vocabulario = set(contrato["effect_vocabulary"])
    for clase_id in declaradas:
        assert clase_id in CASES, clase_id
        for spec in contrato["files"].values():
            for clase in spec["corruptions"]:
                if clase["id"] != clase_id:
                    continue
                assert clase["target"] and clase["violation"] and clase["severity"]
                assert set(clase["expected"]) <= vocabulario, clase_id


# ================================================================ AISLAMIENTO
def test_los_ficheros_de_produccion_no_cambian(tmp_path):
    """El `data/` de produccion queda byte a byte identico.

    Vigila los 4 ficheros de persistencia del motor y los 4 de los subsistemas
    ajenos que el motor instancia (cuyo threaded escribe con ruta RELATIVA).
    """
    antes = _hashes_de_produccion()
    for clase_id in CLASES:
        motor = _motor_con_caso(CASES[clase_id], tmp_path)
        motor.detect_absent_storage()
        motor.detect_absent_sections()
        motor.get_engine_status()
    despues = _hashes_de_produccion()
    for nombre in FICHEROS_DE_PERSISTENCIA + FICHEROS_DE_SUBSISTEMAS_AJENOS:
        assert antes[nombre] == despues[nombre], nombre
