#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test del FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.1).

QUE COMPRUEBA ESTE TEST
Que comportamiento real ofrece el motor HOY cuando TODOS los datos de
persistencia se han perdido, y que distancia hay entre ese comportamiento y el
contrato declarado:
  - la declaracion `total_loss_fallback()` del motor esta bien FORMADA: declara
    su version, su principio, la definicion de perdida total, los MODOS de
    perdida, las CAPAS de fallback y los INVARIANTES, y cada invariante declara
    a que CAPA pertenece, que ENUNCIADO tiene y si el runtime lo SATISFACE;
  - los MODOS que la sonda mide en runtime son EXACTAMENTE los que el contrato
    declara: ni uno de mas ni uno de menos;
  - todo invariante declarado SATISFECHO se cumple en TODOS los modos de
    perdida total, y todo invariante declarado PENDIENTE falla de VERDAD en al
    menos un modo: la declaracion y el runtime no pueden discrepar;
  - la determinacion NO es vacia: hay invariantes pendientes y el motor
    EFFECTIVAMENTE no los cumple (si no, la hoja no habria determinado nada);
  - la medicion NO es vacia: con datos sanos no se declara ninguna perdida y
    con una perdida real se declara.

RELACION CON 2.8.8.9.7.1
`test_2_8_8_9_7_1_recoverable.py` (7.1) mide lo que se PIERDE cuando una
corrupcion PARCIAL es rechazada. Este modulo (8.1) mide lo que queda cuando la
perdida es TOTAL: el motor NO tiene datos que recuperar, solo defaults. No
repite, por tanto, la comprobacion de 7.1.

INDEPENDENCIA DEL INSTRUMENTO
Este test NO reutiliza el registro de escenarios ni los observadores de
2.8.8.9.6.1, 6.4 ni 7.1: la sonda `identify_fallback_real.py` (mismo
directorio) define sus PROPIOS cuatro modos de perdida total, con su PROPIO
SENTINELA, y sus PROPIOS observadores. El contenido SANO que la perdida total
destruye lleva una marca PROPIA, de modo que la perdida se midio con un
instrumento que no comparte puntos ciegos con el que declara los contratos.

La sonda se carga por RUTA (no por `import` de paquete) porque es un script
independiente de la suite pytest, ejecutable tambien de forma aislada:
    python tests/utils/contextual_adaptation_engine/identify_fallback_real.py

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

_SONDA_PATH = os.path.join(_TESTS_DIR, "identify_fallback_real.py")

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
    """Carga la sonda de 2.8.8.9.8.1 por RUTA.

    Se carga por RUTA (no por `import` de paquete) porque la sonda es un script
    independiente de la suite pytest: de ella se reutilizan los modos de
    perdida y los instrumentos de observacion, no su codigo de salida.
    """
    spec = importlib.util.spec_from_file_location("identify_fallback_real", _SONDA_PATH)
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
    perdida total, y el que declara el contrato del fallback.
    """
    data_dir = str(tmp_path_factory.mktemp("referencia") / "data")
    return sonda.nuevo_motor(data_dir)


@pytest.fixture(scope="module")
def contrato(sonda, motor_ref):
    """Contrato declarado, con el contraste de la PARTE A de la sonda.

    El contraste de forma (PARTE A) lo hace la sonda; aqui se exige que no
    haya ninguna comprobacion fallida, de modo que una declaracion mal
    formada rompe la suite y no pasa inadvertida.
    """
    desde = len(sonda.FAILURES)
    declarado = sonda.parte_a_contrato(motor_ref)
    assert not sonda.FAILURES[desde:], (
        "el contrato del fallback no esta bien formado: "
        + "; ".join(sonda.FAILURES[desde:]))
    return declarado


@pytest.fixture(scope="module")
def tabla(sonda, contrato):
    """MEDICION en runtime: que se cumple y que no, modo de perdida por modo.

    Se mide UNA vez y se reutiliza: la medicion es la parte cara y no depende
    del test que la consulta.
    """
    return sonda.parte_b_medicion(contrato)


@pytest.fixture(scope="module")
def deteccion(sonda, contrato, tabla):
    """DETERMINACION: el conjunto de invariantes NO Satisfechos en runtime."""
    return sonda.parte_c_determinacion(contrato, tabla)


# Los MODOS de perdida total que la sonda mide, y los INVARIANTES con su
# OBSERVADOR. Se calculan al importar el modulo para que la parametrizacion
# sea explicita: cada modo y cada invariante tienen su propio test.
MODOS = sorted(_cargar_sonda().MODOS)
VINCULOS = dict(_cargar_sonda().VINCULOS)


def test_el_contrato_del_fallback_esta_bien_formado(contrato):
    """La declaracion del fallback esta bien formada (PARTE A de la sonda)."""
    assert contrato.get("version"), "el contrato no declara su version"
    assert contrato.get("principle"), "el contrato no declara su principio"
    assert (contrato.get("definition") or {}).get("total_loss"), (
        "el contrato no declara que es una perdida total")
    assert (contrato.get("definition") or {}).get("not_total_loss"), (
        "el contrato no declara que NO es una perdida total")
    assert contrato.get("loss_modes"), "faltan los MODOS de perdida total"
    assert contrato.get("fallback_layers"), "faltan las CAPAS de fallback"
    assert contrato.get("invariants"), "faltan los INVARIANTES"
    assert contrato.get("reconciliation"), "falta el REGISTRO de reconciliacion"


def test_los_modos_de_perdida_declarados_son_los_medidos(sonda, contrato):
    """Los MODOS que se miden son EXACTAMENTE los que el contrato declara.

    Anadir un modo a la sonda sin declararlo (o al reves) rompe este test: la
    medicion no puede medir una cosa y el contrato describir otra.
    """
    declarados = set(contrato.get("loss_modes") or {})
    medidos = set(sonda.MODOS)
    assert declarados == medidos, (
        f"declarados={sorted(declarados)} medidos={sorted(medidos)} "
        f"solo_declarados={sorted(declarados - medidos)} "
        f"solo_medidos={sorted(medidos - declarados)}")


def test_todo_invariante_declara_capa_enunciado_y_veredicto(contrato):
    """Cada invariante declara su CAPA (que existe), su ENUNCIADO y su veredicto.

    Sin el CAPA no se puede saber que pieza del fallback se esta midiendo; sin
    el ENUNCIADO el invariante no dice nada; sin el veredicto no se puede
    contrastar la declaracion con el runtime.
    """
    capas = contrato.get("fallback_layers") or {}
    invariantes = contrato.get("invariants") or {}
    for nombre, invariante in invariantes.items():
        assert invariante.get("layer") in capas, (
            f"`{nombre}` declara la capa `{invariante.get('layer')}`, que no existe")
        assert invariante.get("statement"), f"`{nombre}` no declara su enunciado"
        assert isinstance(invariante.get("satisfied"), bool), (
            f"`{nombre}` no declara si el runtime lo satisface")


def test_los_pendientes_declarados_son_los_invariantes_no_satisfechos(contrato, deteccion):
    """Lo MEDIDO en runtime coincide con lo DECLARADO como pendiente.

    La hoja no puede decir una cosa y el motor hacer otra: los PENDIENTES
    declarados son EXACTAMENTE los invariantes que el runtime NO satisface.
    """
    declarados = set(contrato.get("pending") or [])
    medidos = set(deteccion)
    assert declarados == medidos, (
        f"declarados pendientes={sorted(declarados)} "
        f"medidos no satisfeitos={sorted(medidos)} "
        f"solo_declarados={sorted(declarados - medidos)} "
        f"solo_medidos={sorted(medidos - declarados)}")


@pytest.mark.parametrize("modo", MODOS)
def test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo(contrato, tabla, modo):
    """Todo invariante declarado SATISFECHO se cumple en el modo indicado.

    El fallback debe funcionar en TODOS los modos de perdida total: basta un
    modo en el que no se cumpla para que el invariante no se satisfaga.
    """
    declarados = {nombre for nombre, invariante in (contrato.get("invariants") or {}).items()
                  if invariante.get("satisfied") is True}
    observado = next(item for item in tabla if item["modo"] == modo)
    incumplidos = sorted(nombre for nombre in declarados
                          if not observado[VINCULOS[nombre]])
    assert not incumplidos, (
        f"en el modo `{modo}` NO se cumplen los invariantes declarados: {incumplidos}")


@pytest.mark.parametrize("modo", MODOS)
def test_la_perdida_es_detectable_y_el_estado_es_continuo_en_todo_modo(tabla, modo):
    """La perdida es DETECTABLE y el motor SIGUE OPERANDO en cada modo.

    Son los dos invariantes que el fallback NO puede negociar: si la perdida
    no se ve o si el motor se detiene, JARVIS no puede continuar.
    """
    observado = next(item for item in tabla if item["modo"] == modo)
    assert observado["perdida_detectable"], (
        f"en el modo `{modo}` la perdida total NO es detectable por las APIs de deteccion")
    assert observado["operacion_continua"], (
        f"en el modo `{modo}` el motor NO puede capturar, analizar y ejecutar")
    assert observado["ficheros_intactos"], (
        f"en el modo `{modo}` la carga ha reescrito los ficheros corruptos")
    assert observado["estado_igual_a_fresco"], (
        f"en el modo `{modo}` el estado NO es el de los defaults del codigo")


def test_la_determinacion_no_es_vacia(sonda, contrato, deteccion):
    """La DETERMINACION identifica algo: hay invariantes pendientes y fallan.

    La hoja no puede declarar que el fallback esta completo y que a la vez el
    runtime no lo cumpla: una de las dos tiene que hablar. Y lo que habla tiene
    que ser el RUNTIME: el CONTROL de la sonda ve una perdida REAL.
    """
    pendientes = set(contrato.get("pending") or [])
    assert pendientes, "no hay ningun invariante pendiente: la determinacion seria vacia"
    assert set(deteccion) == pendientes, (
        f"pendientes declarados={sorted(pendientes)} "
        f"medidos={sorted(deteccion)}")
    fallos = sonda.control_de_no_vacio("perdida real")
    assert not fallos, (
        "el control de perdida real no ve la perdida: la medicion no discrimina\n  - "
        + "\n  - ".join(fallos))


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
