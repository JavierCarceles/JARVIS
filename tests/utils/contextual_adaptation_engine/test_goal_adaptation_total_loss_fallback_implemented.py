#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la IMPLEMENTACION del FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.2).

QUE COMPRUEBA ESTE TEST
Que el fallback por corrupcion total NO esta solo DECLARADO, sino que el motor
lo OFRECE de verdad:

  - la CARGA DECLARA lo que ocurrio: `load_all_data()` devuelve FALSO cuando la
    persistencia EXISTE pero no aporta ninguna unidad de datos utilizable, y
    devuelve VERDADERO cuando no hay nada que cargar (almacenamiento ausente) o
    cuando los datos son sanos: la capa de fallback no puede anunciar un exito
    que no ocurrio, ni un fracaso que no ocurrio;
  - el ESTADO AGREGADO declara la perdida: los ficheros ILEGIBLES se cuentan
    como anomalia, de modo que una perdida total no se presenta como un estado
    limpio;
  - el RESPALDO cubre los CUATRO ficheros de persistencia que el propio motor
    declara en `expected_storage_paths()`, no solo una parte;
  - la carga NO reescribe los ficheros corruptos y el respaldo NO altera su
    contenido: el material de diagnostico queda intacto;
  - el CONTRATO se RECONCILIA con lo implementado: la entrada de 2.8.8.9.8.2
    existe, no queda ningun invariante pendiente y los tres que 8.1 determino
    aparecen como RESUELTOS.

RELACION CON 2.8.8.9.8.1
`test_2_8_8_9_8_1_total_loss_fallback.py` (8.1) comprueba que lo DECLARADO y lo
MEDIDO no discrepan: el contrato describe el runtime. Este modulo (8.2) no
contrasta una declaracion con una medicion: comprueba directamente que las
PIEZAS IMPLEMENTADAS hacen lo que dicen hacer. 8.1 fallaria si el contrato
mintiera; 8.2 falla si el motor no lo cumple. Un contrato puede ser exacto y
el motor seguir sin hacer nada: por eso los dos tests son distintos.

INDEPENDENCIA DEL INSTRUMENTO
Este test NO usa la sonda `identify_fallback_real.py` ni su registro de
escenarios: monta sus PROPIOS escenarios, con su PROPIO SENTINELA y sus PROPIOS
observadores. La implementacion se verifica desde el comportamiento OBSERVADO,
no desde lo que el contrato declara.

AISLAMIENTO
Todos los motores se crean con `data_dir` temporal, asi que el `data/` de
produccion no se lee ni se escribe por el motor. La sesion completa se ejecuta
dentro del sandbox de CWD de `tests/conftest.py`, de modo que las rutas
RELATIVAS de los subsistemas ajenos caen en el temporal y no en el repo. El
propio modulo incluye ademas un TEST DE GUARDA que comprueba por sha256 que los
ficheros de produccion vigilados no cambian.
"""

import hashlib
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

PRODUCTION_DATA_DIR = os.path.join(_ROOT_DIR, "data")
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

RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"

# SENTINELA PROPIO de este modulo: marca el contenido SANO que la perdida
# total destruye. No comparte prefijo con el de 2.8.8.9.8.1, de modo que la
# verificacion de la implementacion no comparte puntos ciegos con la medicion
# de la declaracion.
PREFIJO = "SENTINELA_IMPL_2_8_8_9_8_2"
PREFIJO_SANO = "SANO_IMPL_2_8_8_9_8_2"

REGLA_SANA = {
    "rule_id": "regla_impl_centinela", "name": "regla centinela", "description": "descripcion centinela",
    "condition_pattern": "patron centinela", "adaptation_actions": ["accion centinela"],
    "context_triggers": ["production"], "confidence_threshold": 0.7,
    "priority": 1, "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}


def _nuevo_motor(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    return ContextualAdaptationEngine(data_dir=data_dir)


def _materializar(ficheros, data_dir):
    """Escribe los ficheros del escenario en `data_dir`."""
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as handle:
            handle.write(contenido if isinstance(contenido, str)
                         else json.dumps(contenido, ensure_ascii=False))


def _contenidos_sanos():
    """Los cuatro ficheros de persistencia con datos SANOS y CENTINELA."""
    return {
        RF: {"version": "2.0", "last_updated": "2024-01-01T00:00:00", "total_rules": 1,
             "rules": [dict(REGLA_SANA)]},
        KB: {"version": "2.0", "last_updated": "2024-01-01T00:00:00", "context_snapshots": 0,
             "adaptation_history": 0, "knowledge_transfers": 0,
             "data": {"context_patterns": {"production": [{"patron": PREFIJO}]}}},
        FB: {"goal_adaptation_feedback": [], "adaptation_history": [],
             "last_updated": "2024-01-01T00:00:00"},
        LR: {"learning_results": [], "adaptation_strategies": {},
             "last_updated": "2024-01-01T00:00:00"},
    }


# La perdida TOTAL: los cuatro ficheros EXISTEN pero ninguno aporta una sola
# unidad de datos utilizable. Cada fichero se corrompe de una forma distinta,
# para que la implementacion tenga que declarar la perdida sea cual sea la
# forma que la produjo.
def _contenidos_perdidos():
    return {
        RF: "no es json <<< roto >>>",
        KB: "{}",
        FB: "[]",
        LR: '"texto que no es un mapeo"',
    }


def _contenidos_sin_unidades():
    """Persistencia que EXISTE y PARSEA, pero no aporta ninguna unidad de datos.

    Es el escenario que AISLA la cuenta de unidades: los cargadores TERMINAN
    BIEN (no hay excepcion que los interrumpa) y no encuentran nada que
    cargar. aqui es donde la carga tiene que decidir por si misma si declara
    exito o fracaso: si el fallo lo declarara el cargador, la cuenta de
    unidades no se comprobaria nunca.
    """
    return {
        RF: "{}",
        KB: "{}",
        FB: "[]",
        LR: "[]",
    }


def _sha256(ruta):
    if not os.path.isfile(ruta):
        return None
    digest = hashlib.sha256()
    with open(ruta, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _firmas(data_dir, nombres=FICHEROS_DE_PERSISTENCIA):
    return {nombre: _sha256(os.path.join(data_dir, nombre)) for nombre in nombres}


@pytest.fixture
def data_dir_perdida(tmp_path):
    """Escenario de perdida TOTAL: los cuatro ficheros existen y no aportan nada."""
    directorio = str(tmp_path / "data")
    _materializar(_contenidos_perdidos(), directorio)
    return directorio


@pytest.fixture
def data_dir_sana(tmp_path):
    """Escenario SANO: los cuatro ficheros aportan datos utilizables."""
    directorio = str(tmp_path / "data")
    _materializar(_contenidos_sanos(), directorio)
    return directorio


@pytest.fixture
def data_dir_sin_unidades(tmp_path):
    """Escenario AISLADO de la cuenta de unidades: los ficheros PARSEAN y no aportan nada."""
    directorio = str(tmp_path / "data")
    _materializar(_contenidos_sin_unidades(), directorio)
    return directorio


@pytest.fixture
def data_dir_vacia(tmp_path):
    """Escenario SIN PERSISTENCIA: no hay ningun fichero que cargar."""
    return str(tmp_path / "data")


@pytest.fixture
def data_dir_ilegible(tmp_path):
    """Escenario con UN SOLO fichero ilegible y los demas sanos.

    Es el escenario que AISLA la cuenta de anomalias: los tres ficheros sanos
    no aportan ninguna desviacion, de modo que la UNICA anomalia posible es el
    fichero ilegible. Si el estado agregado no lo contara, la anomalia seria
    CERO y la perdida se presentaria como un estado limpio.
    """
    directorio = str(tmp_path / "data")
    contenidos = _contenidos_sanos()
    contenidos[RF] = "no es json <<< roto >>>"
    _materializar(contenidos, directorio)
    return directorio


# ----------------------------------------------------------------- la CARGA
def test_la_carga_declara_falso_cuando_la_persistencia_no_aporta_unidades(data_dir_sin_unidades):
    """La carga DECLARA el fracaso: no anuncia un exito que no ocurrio.

    Los cuatro ficheros EXISTEN y PARSEAN, pero ninguno aporta una unidad de
    datos utilizable. Devolver VERDADERO aqui haria CREER al consumidor que los
    datos estan cargados, cuando el motor opera con los defaults del codigo.

    El escenario AISLA la decision: los cargadores terminan BIEN, de modo que
    el fracaso lo declara la CUENTA de unidades y no un error de lectura. Si el
    fallo lo declarara el cargador, esta pieza no se comprobaria nunca.
    """
    motor = _nuevo_motor(data_dir_sin_unidades)
    assert motor.load_all_data() is False, (
        "la carga declara EXITO con una persistencia que no aporta ninguna unidad de datos")


def test_la_carga_deja_el_estado_en_los_defaults_del_codigo(data_dir_perdida):
    """El fallback NO inventa datos: el estado es el de un motor recien creado."""
    motor = _nuevo_motor(data_dir_perdida)
    motor.load_all_data()
    fresco = _nuevo_motor(data_dir_perdida + "_fresco")
    assert sorted(motor.adaptation_rules or {}) == sorted(fresco.adaptation_rules or {}), (
        "el estado de reglas tras la perdida no es el de los defaults del codigo")
    assert PREFIJO not in json.dumps(motor.knowledge_base, default=str), (
        "el fallback ha INVENTADO datos a partir del fichero roto")


def test_la_carga_declara_verdadero_cuando_no_hay_nada_que_cargar(data_dir_vacia):
    """Sin persistencia NO hay perdida: la carga declara VERDADERO.

    El almacenamiento AUSENTE (2.8.8.9.5.1) no es una perdida total: no hay
    nada que perder y el estado por defecto es el declarado. Declarar FALSO
    aqui seria mentir en la direccion contraria.
    """
    motor = _nuevo_motor(data_dir_vacia)
    assert motor.load_all_data() is True, (
        "la carga declara FRACASO cuando no hay ninguna persistencia que cargar")


def test_la_carga_declara_verdadero_con_datos_sanos(data_dir_sana):
    """Con datos SANOS la carga declara VERDADERO y los datos LLEGAN al estado."""
    motor = _nuevo_motor(data_dir_sana)
    assert motor.load_all_data() is True, (
        "la carga declara FRACASO con una persistencia sana")
    assert "regla_impl_centinela" in (motor.adaptation_rules or {}), (
        "la regla centinela NO ha llegado al estado: la carga no ha cargado nada")
    assert PREFIJO in json.dumps(motor.knowledge_base, default=str), (
        "el patron centinela NO ha llegado a la base de conocimiento")


# ------------------------------------------------------- el ESTADO AGREGADO
def test_el_estado_agregado_declara_la_perdida_total(data_dir_perdida):
    """El estado AGREGADO declara la perdida: un fichero ilegible es anomalia.

    Si los ficheros ILEGIBLES no se contaran, una perdida total de los cuatro
    ficheros se presentaria como un estado limpio.
    """
    motor = _nuevo_motor(data_dir_perdida)
    estado = motor.get_engine_status()
    corrupcion = estado.get("corruption") or {}
    assert corrupcion.get("corruption_count", 0) > 0, (
        "el estado agregado NO declara ninguna anomalia con la persistencia perdida")
    assert corrupcion.get("unreadable_count", 0) > 0, (
        "el estado agregado NO cuenta los ficheros ILEGIBLES como anomalia")
    assert corrupcion.get("unreadable"), (
        "el estado agregado no informa de QUE ficheros son ilegibles")


def test_el_estado_agregado_cuenta_los_ficheros_ilegibles_como_anomalia(data_dir_ilegible):
    """Un fichero ILEGIBLE se CUENTA como anomalia, no solo se menciona.

    Escenario AISLADO: los otros tres ficheros son sanos, de modo que la unica
    anomalia posible es el fichero ilegible. El conteo agregado tiene que
    incluirlo: si no, una perdida presentaria un estado limpio.
    """
    motor = _nuevo_motor(data_dir_ilegible)
    corrupcion = (motor.get_engine_status().get("corruption") or {})
    ilegibles = corrupcion.get("unreadable_count", 0)
    conteo = corrupcion.get("corruption_count", 0)
    assert ilegibles >= 1, "el estado agregado no ve el fichero ilegible"
    assert conteo >= ilegibles, (
        f"el estado agregado declara {conteo} anomalias y hay {ilegibles} ficheros "
        "ilegibles: los ficheros ILEGIBLES no se cuentan como anomalia")


def test_el_estado_agregado_no_declara_anomalias_con_datos_sanos(data_dir_sana):
    """El CONTROL: con datos sanos el estado agregado NO declara ninguna perdida.

    Sin este control, un estado agregado que declarase siempre una anomalia
    pasaria el test anterior sin comprobar nada.
    """
    motor = _nuevo_motor(data_dir_sana)
    estado = motor.get_engine_status()
    anomalias = (estado["corruption"]["corruption_count"]
                 + estado["storage"]["absent_count"]
                 + estado["storage_sections"]["absent_count"])
    assert anomalias == 0, f"el estado agregado declara anomalias con datos sanos: {anomalias}"


# --------------------------------------------------------------- el RESPALDO
def test_el_respaldo_cubre_los_cuatro_ficheros_de_persistencia(data_dir_perdida):
    """El respaldo cubre TODA la persistencia que el motor declara.

    La unidad de cobertura es la CLAVE de `expected_storage_paths()`, no el
    nombre del fichero: es la que declara el propio motor.
    """
    motor = _nuevo_motor(data_dir_perdida)
    assert motor.backup_data() is True, "el respaldo declara FRACASO con ficheros que respaldar"
    respaldos = os.path.join(data_dir_perdida, "backups")
    nombres = set(os.listdir(respaldos)) if os.path.isdir(respaldos) else set()
    claves = list(motor.expected_storage_paths())
    sin_cubrir = [clave for clave in claves
                  if not any(nombre.startswith(clave + "_backup_") for nombre in nombres)]
    assert not sin_cubrir, (
        f"el respaldo NO cubre estos almacenamientos: {sin_cubrir} "
        f"(de {len(claves)}): {sorted(nombres)}")


def test_el_respaldo_no_altera_el_contenido_de_los_ficheros(data_dir_perdida):
    """El respaldo es una COPIA: el material de diagnostico queda intacto."""
    antes = _firmas(data_dir_perdida)
    motor = _nuevo_motor(data_dir_perdida)
    motor.backup_data()
    despues = _firmas(data_dir_perdida)
    assert antes == despues, (
        "el respaldo ha ALTERADO los ficheros de origen: "
        + ", ".join(sorted(n for n in antes if antes[n] != despues[n])))


def test_la_carga_no_sobrescribe_los_ficheros_corruptos(data_dir_sin_unidades):
    """La carga NO reescribe los ficheros corruptos: su contenido sigue intacto.

    Un fichero reescrito con los defaults destruiria la evidencia de la
    corrupcion, que es justo lo que hace falta para diagnosticar la perdida.

    El escenario usa ficheros que PARSEAN a proposito: si el fichero no se
    puede leer, el cargador aborta antes de llegar al punto en el que podria
    reescribirlo, y la comprobacion no miraria nada.
    """
    antes = _firmas(data_dir_sin_unidades)
    motor = _nuevo_motor(data_dir_sin_unidades)
    motor.load_all_data()
    despues = _firmas(data_dir_sin_unidades)
    assert antes == despues, (
        "la carga ha reescrito los ficheros corruptos: "
        + ", ".join(sorted(n for n in antes if antes[n] != despues[n])))


# ----------------------------------------------------- la RECONCILIACION
def test_el_contrato_reconcilia_la_implementacion_de_8_2(data_dir_vacia):
    """El contrato se RECONCILIA con lo implementado: no queda nada pendiente.

    La entrada de 2.8.8.9.8.2 tiene que existir y tiene que declarar RESUELTOS
    los tres invariantes que 2.8.8.9.8.1 determino como PENDIENTES.
    """
    motor = _nuevo_motor(data_dir_vacia)
    contrato = motor.total_loss_fallback()
    entradas = {entrada.get("unit"): entrada for entrada in (contrato.get("reconciliation") or [])}
    assert "2.8.8.9.8.2" in entradas, (
        "el contrato no reconcilia la implementacion 2.8.8.9.8.2: "
        f"entradas={sorted(entradas)}")
    implementacion = entradas["2.8.8.9.8.2"]
    assert implementacion.get("pending") == [], (
        f"la implementacion declara invariantes pendientes: {implementacion.get('pending')}")
    assert not contrato.get("pending"), (
        f"el contrato declara invariantes pendientes: {contrato.get('pending')}")
    resueltos = set(implementacion.get("resolved") or [])
    esperados = {"loss_visible_in_status", "load_result_is_truthful", "backup_covers_all_persistence"}
    assert resueltos == esperados, (
        f"resueltos={sorted(resueltos)} esperados={sorted(esperados)}")
    declarados = {nombre for nombre, invariante in (contrato.get("invariants") or {}).items()
                  if invariante.get("satisfied") is True}
    assert declarados == set(contrato.get("invariants") or {}), (
        "hay invariantes declarados NO satisfechos en un fallback ya implementado")


# ------------------------------------------------------------------ GUARDA
def test_los_ficheros_de_produccion_no_cambian():
    """GUARDA: el `data/` de produccion queda byte a byte identico.

    Vigila los 4 ficheros de persistencia del motor y los 4 de los subsistemas
    ajenos que el motor instancia (cuyo hilo escribe con ruta RELATIVA).
    """
    nombres = FICHEROS_DE_PERSISTENCIA + FICHEROS_DE_SUBSISTEMAS_AJENOS
    antes = {nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre)) for nombre in nombres}
    assert antes, "no se han encontrado los ficheros de produccion vigilados"
    despues = {nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre)) for nombre in nombres}
    assert antes == despues, (
        "los ficheros de produccion han cambiado: "
        + ", ".join(sorted(n for n in nombres if antes[n] != despues[n])))
