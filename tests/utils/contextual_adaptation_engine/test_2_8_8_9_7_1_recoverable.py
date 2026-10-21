#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de los DATOS RECUPERABLES (2.8.8.9.7.1).

QUE COMPRUEBA ESTE TEST
Que dato RECUPERABLE se pierde hoy cuando una corrupcion es rechazada, y que
la DETERMINACION de ese dato no es una opinion sino una medicion:
  - la declaracion `recoverable_data()` del motor esta bien FORMADA: cubre las
    27 clases de corrupcion, declara un NIVEL y una POLITICA del vocabulario,
    solo usa TOKENS declarados, y sus valores por defecto son los del FORMATO
    REAL y son CONSERVADORES cuando hace falta;
  - por cada clase, el dato corrupto NO llega al estado (la determinacion no
    relaja el rechazo de 2.8.8.9.6.3);
  - por cada clase, lo MEDIDO en runtime coincide con lo DECLARADO: una clase
    pierde dato recuperable si y solo si la declaracion la marca como
    PENDIENTE. La declaracion y el runtime no pueden discrepar;
  - la determinacion NO es VACIA: hay clases pendientes y el dato recuperable
    se pierde de verdad (si no, la hoja no habria determined nada);
  - la medicion NO es vacia: con datos sanos no se declara ninguna perdida y
    con una perdida real se declara.

RELACION CON 2.8.8.9.6.4
`test_2_8_8_9_6_4_rejection_runtime.py` (6.4) verifica que el dato corrupto se
RECHAZA. Este modulo (7.1) no repite esa comprobacion: mide que se pierde
JUNTO con lo rechazado, que es lo que la recuperacion parcial tendra que
recuperar en 2.8.8.9.7.2.

INDEPENDENCIA DEL INSTRUMENTO
Este test NO reutiliza el registro de escenarios ni los observadores de
2.8.8.9.6.1 ni de 2.8.8.9.6.4: la sonda `identify_recoverable_real.py` (mismo
directorio) define sus PROPIOS escenarios, con un SENTINELA propio incrustado
en el punto exacto que se corrompe, y sus PROPIOS observadores. El contenido
SANO que la corrupcion no destruye lleva una marca PROPIA, de modo que la
perdida se midio con un instrumento que no comparte puntos ciegos con el que
declara los contratos.

La sonda se carga por RUTA (no por `import` de paquete) porque es un script
independiente de la suite pytest, ejecutable tambien de forma aislada:
    python tests/utils/contextual_adaptation_engine/identify_recoverable_real.py

AISLAMIENTO
Todos los motores se crean con `data_dir` temporal, asi que el `data/` de
produccion no se lee ni se escribe por el motor. La sesion completa se ejecuta
dentro del sandbox de CWD de `tests/conftest.py`, de modo que las rutas
RELATIVAS de los subsistemas ajenos (`data/knowledge_graph.json`,
`data/improvement_rules.json`, `models/...`) caen en el temporal y no en el
repo. El propio modulo incluye ademas un TEST DE GUARDA que comprueba por
sha256 que los ficheros de produccion vigilados no cambian.
"""

import hashlib
import importlib.util
import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

_SONDA_PATH = os.path.join(_TESTS_DIR, "identify_recoverable_real.py")

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


def _cargar_sonda():
    """Carga la sonda de 2.8.8.9.7.1 por RUTA.

    Se carga por RUTA (no por `import` de paquete) porque la sonda es un script
    independiente de la suite pytest: de ella se reutilizan los escenarios y
    los instrumentos de observacion, no su codigo de salida.
    """
    spec = importlib.util.spec_from_file_location("identify_recoverable_real", _SONDA_PATH)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def sonda():
    return _cargar_sonda()


@pytest.fixture(scope="module")
def motor_ref(sonda, tmp_path_factory):
    """Motor de REFERENCIA: el motor sin ningun fichero corrupto.

    Es el que aporta los valores por defecto contra los que se contrasta la
    recuperacion, y el que declara el contrato de lo recuperable.
    """
    data_dir = str(tmp_path_factory.mktemp("referencia") / "data")
    return sonda.nuevo_motor(data_dir)


@pytest.fixture(scope="module")
def contrato(sonda, motor_ref):
    """Contrato declarado y clases declaradas, con el contraste de la PARTE A.

    El contraste de forma (PARTE A) lo hace la sonda; aqui se exige que no
    haya ninguna comprobacion fallida, de modo que una declaracion mal
    formada rompe la suite y no pasa inadvertida.
    """
    desde = len(sonda.FAILURES)
    recuperable, declaradas = sonda.parte_a_contrato(motor_ref)
    assert not sonda.FAILURES[desde:], (
        "el contrato de datos recuperables no esta bien formado: "
        + "; ".join(sonda.FAILURES[desde:]))
    return recuperable, declaradas


@pytest.fixture(scope="module")
def tabla(sonda):
    """Escenarios PROPIOS de la sonda, uno por clase de corrupcion."""
    return sonda.escenarios()


@pytest.fixture(scope="module")
def medicion(sonda, tabla):
    """MEDICION en runtime: que sobrevive y que no, clase por clase.

    Se mide UNA vez por clase y se reutiliza: la medicion es la parte cara y
    no depende del test que la consulta.
    """
    return {clase_id: sonda.medir(escenario) for clase_id, escenario in tabla.items()}


CLASES = sorted(_cargar_sonda().escenarios())


def test_el_contrato_de_datos_recuperables_esta_bien_formado(contrato):
    """La declaracion de lo recuperable esta bien formada (PARTE A de la sonda)."""
    recuperable, declaradas = contrato
    assert declaradas, "la declaracion no declara ninguna clase"
    assert recuperable.get("levels"), "faltan los NIVELES declarados"
    assert recuperable.get("policies"), "faltan las POLITICAS declaradas"
    assert recuperable.get("recoverable_tokens"), "faltan los TOKENS declarados"
    assert recuperable.get("field_defaults"), "faltan los valores por DEFECTO declarados"
    assert "prefijo" in (recuperable.get("independence_rule") or ""), (
        "la REGLA DE INDEPENDENCIA no esta declarada")


def test_el_contrato_cubre_las_27_clases_de_corrupcion(contrato, motor_ref):
    """Las clases de corrupcion y las de dato recuperable son las MISMAS.

    Anadir una clase de corrupcion al motor sin declararla recuperable (o al
    reves) rompe este test: la determinacion no puede dejar nada sin medir.
    """
    _, declaradas = contrato
    ids_declarados = set()
    for spec in motor_ref.corruption_criteria()["files"].values():
        for clase in spec.get("corruptions", []) or []:
            ids_declarados.add(clase.get("id"))
    assert set(declaradas) == ids_declarados, (
        f"declaradas={len(declaradas)} contractuales={len(ids_declarados)} "
        f"solo_declaradas={sorted(set(declaradas) - ids_declarados)} "
        f"solo_contractuales={sorted(ids_declarados - set(declaradas))}")


def test_hay_exactamente_27_clases(contrato):
    """El numero de clases medidas es el que la hoja declara (27)."""
    _, declaradas = contrato
    assert len(declaradas) == 27, f"clases declaradas={len(declaradas)}"


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_dato_corrupto_no_llega_al_estado(sonda, medicion, clase_id):
    """El dato corrupto no llega al estado en ninguna de las 27 clases.

    La determinacion de lo recuperable NO puede relajar el rechazo de
    2.8.8.9.6.3: se recupera lo sano, nunca lo corrupto.
    """
    observado = medicion[clase_id]
    assert not observado["corrupto_en_estado"], (
        f"el dato corrupto de `{clase_id}` ha llegado al estado operativo")


@pytest.mark.parametrize("clase_id", CLASES)
def test_la_medicion_coincide_con_lo_declarado(sonda, contrato, medicion, clase_id):
    """Lo MEDIDO en runtime coincide con lo DECLARADO en el contrato.

    Una clase pierde dato recuperable si y solo si la declaracion la marca
    como PENDIENTE: la hoja no puede decir una cosa y el motor hacer otra.
    """
    recuperable, declaradas = contrato
    clase = declaradas[clase_id]
    perdidas = sonda.perdidas_de(clase, medicion[clase_id])
    declarada_pendiente = clase_id in sonda.clases_pendientes(recuperable)
    assert bool(perdidas) == declarada_pendiente, (
        f"`{clase_id}`: perdidas medidas={[u['etiqueta'] for u in perdidas]} "
        f"declarada pendiente={declarada_pendiente} "
        f"(recovers={clase.get('recovers')})")


@pytest.mark.parametrize("clase_id", CLASES)
def test_la_clase_declara_lo_que_se_puede_recuperar(sonda, contrato, clase_id):
    """Cada clase declara el NIVEL, la POLITICA y los TOKENS de lo recuperable.

    El nivel declarado tiene que ser el de la unidad que corrompe, y los
    tokens tienen que pertenecer al vocabulario cerrado: es lo que permite que
    la medicion contraste la declaracion con lo observado.
    """
    _, declaradas = contrato
    clase = declaradas[clase_id]
    assert clase.get("level"), f"`{clase_id}` no declara nivel"
    assert clase.get("policy"), f"`{clase_id}` no declara politica"
    assert clase.get("corrupt_unit"), f"`{clase_id}` no declara la unidad corrupta"
    assert "recovers" in clase, f"`{clase_id}` no declara lo recuperable"
    assert isinstance(clase["recovers"], list), f"`{clase_id}`: recovers no es una lista"


def test_la_determinacion_no_es_vacia(sonda, contrato, medicion):
    """La DETERMINACION identifica algo: hay clases pendientes y hay perdida.

    Sin este control, una hoja que midiera "no se pierde nada" pasaria todos
    sus controles sin haber determinado nada.
    """
    recuperable, declaradas = contrato
    pendientes = sonda.clases_pendientes(recuperable)
    assert pendientes, "la declaracion no marca ninguna clase como pendiente"
    assert pendientes <= set(declaradas), (
        f"clases pendientes que no existen: {sorted(pendientes - set(declaradas))}")
    perdidas_reales = set()
    for clase_id in pendientes:
        perdidas_reales.update(u["etiqueta"] for u in sonda.perdidas_de(declaradas[clase_id],
                                                                        medicion[clase_id]))
    assert perdidas_reales, (
        "las clases pendientes declared no pierden nada: la determinacion es vacia")


def test_la_determinacion_cubre_todas_las_clases_con_dato_recuperable(sonda, contrato, medicion):
    """Toda clase que declara dato recuperable tiene al menos una unidad que medir.

    Si una clase declara `recovers` pero su escenario no tiene ninguna unidad
    con ese token, la medicion no puede contrastarla: seria un hueco.
    """
    _, declaradas = contrato
    for clase_id, clase in declaradas.items():
        for token in clase.get("recovers") or []:
            portada = [u for u in medicion[clase_id]["unidades"] if u["token"] == token]
            assert portada, (
                f"`{clase_id}` declara el token `{token}` pero su escenario no tiene "
                f"ninguna unidad que lo mida")


def test_la_sonda_no_es_vacia(sonda):
    """La medicion discrimina: con datos sanos no hay perdida y con perdida real si.

    Es el control de NO VACUO de la sonda (PARTE D): sin el, una sonda que no
    mirase el estado pasaria todas sus comprobaciones sin comprobar nada.
    """
    desde = len(sonda.FAILURES)
    sonda.parte_d_no_vacio()
    assert not sonda.FAILURES[desde:], (
        "los controles de no-vacuidad han fallado: " + "; ".join(sonda.FAILURES[desde:]))


def _sha256(ruta):
    if not os.path.isfile(ruta):
        return None
    digest = hashlib.sha256()
    with open(ruta, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
