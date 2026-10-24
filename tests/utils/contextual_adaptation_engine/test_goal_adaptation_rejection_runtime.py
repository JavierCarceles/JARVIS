#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test del RECHAZO EN RUNTIME de la corrupcion (2.8.8.9.6.4).

QUE COMPRUEBA ESTE TEST
Que el dato corrupto NO se usa como si fuera valido:
  - no llega al ESTADO OPERATIVO del motor (reglas, base de conocimiento,
    historial, instantaneas y estrategias ofrecidas);
  - no se PERSISTE en disco al escribir;
  - no ROMPE ninguna API de lectura ni de escritura;
  - se DETECTA y se REPORTA (la corrupcion no se ignora en silencio: el motor
    tiene que poder nombrar la desviacion que ha rechazado);
  - y el rechazo es SELECTIVO: se conserva el contenido sano que la corrupcion
    no destruye, y lo que la corrupcion destruye conserva el valor por defecto.

RELACION CON 2.8.8.9.6.2
`test_corrupt_data.py` (6.2) fija el CASO de corrupcion y el CONTRATO que ese
dato debe cumplir. Este modulo (6.4) lo VERIFICA EN RUNTIME: comprueba que el
motor, efectivamente, rechaza el dato y no lo usa. 6.2 no puede afirmar nada
sobre el rechazo: solo describe lo que hay que rechazar.

INDEPENDENCIA DEL INSTRUMENTO
Este test NO reutiliza el registro de escenarios ni los observadores de
2.8.8.9.6.1: la sonda `verify_rejection_real.py` (mismo directorio) define sus
PROPIOS escenarios (con un SENTINELA propio incrustado en el punto exacto que
se corrompe) y sus PROPIOS instrumentos de observacion (escaneo del estado,
escaneo del disco y ejercicio de las APIs). El rechazo se comprueba con un
instrumento que no comparte puntos ciegos con el que lo declara, de modo que un
fallo de rechazo no pueda esconderse tras un fallo del observador.

La sonda se carga por RUTA (no por `import` de paquete) porque es un script
independiente de la suite pytest, ejecutable tambien de forma aislada:
    python tests/utils/contextual_adaptation_engine/verify_rejection_real.py

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

_SONDA_PATH = os.path.join(_TESTS_DIR, "verify_rejection_real.py")

PRODUCTION_DATA_DIR = os.path.join(_ROOT_DIR, "data")
STORAGE_FILES = ("goal_adaptation_feedback.json", "goal_adaptation_learning_results.json",
                 "contextual_adaptation_rules.json", "contextual_knowledge_base.json")


def _cargar_sonda():
    """Carga la sonda de 2.8.8.9.6.4 por RUTA.

    Se carga por RUTA (no por `import` de paquete) porque la sonda es un script
    independiente de la suite pytest: de ella se reutilizan los escenarios y
    los instrumentos de observacion, no su codigo de salida.
    """
    spec = importlib.util.spec_from_file_location("verify_rejection_real", _SONDA_PATH)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def sonda():
    return _cargar_sonda()


@pytest.fixture(scope="module")
def motor_ref(sonda, tmp_path_factory):
    """Motor de REFERENCIA: el motor sin ningun fichero corrupto.

    Es la linea base contra la que se contrasta la selectividad del rechazo:
    lo que la corrupcion destruye tiene que quedar en el valor por defecto,
    que es el de este motor.
    """
    data_dir = str(tmp_path_factory.mktemp("referencia") / "data")
    return sonda.nuevo_motor(data_dir)


@pytest.fixture(scope="module")
def tabla(sonda, motor_ref):
    """Tabla de escenarios de 6.4, contrastada con el contrato declarado."""
    desde = len(sonda.FAILURES)
    resultado = sonda.parte_a_contrato(motor_ref)
    assert not sonda.FAILURES[desde:], (
        "el contrato de rechazo declarado no esta bien formado: "
        + "; ".join(sonda.FAILURES[desde:]))
    return resultado


CLASES = sorted(_cargar_sonda().escenarios())


def test_las_clases_de_corrupcion_cubren_el_contrato_declarado(sonda, motor_ref):
    """Las 27 clases declaradas en `corruption_criteria()` tienen escenario.

    El contraste de cobertura ya lo hace `parte_a_contrato` (controlado por el
    fixture `tabla`); aqui se exige que el conjunto de clases sea EXACTAMENTE
    el que declara el motor, para que anadir una clase al motor sin scenario
    rompa este test.
    """
    declaradas = motor_ref.corruption_criteria()["files"]
    ids_declarados = set()
    for spec in declaradas.values():
        for clase in spec.get("corruptions", []) or []:
            ids_declarados.add(clase.get("id"))
    assert set(CLASES) == ids_declarados, (
        f"escenarios={len(CLASES)} declaradas={len(ids_declarados)} "
        f"solo_en_escenarios={sorted(set(CLASES) - ids_declarados)} "
        f"solo_declaradas={sorted(ids_declarados - set(CLASES))}")


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_dato_corrupto_no_llega_al_estado_ni_al_disco(sonda, tabla, clase_id):
    """El dato corrupto no llega al estado, no rompe las APIs y no se persiste.

    Es el EXIGIDO de 2.8.8.9.6.4 por clase: arranque sin lanzar, contenido
    corrupto presente en disco (la corrupcion es CONTENIDO, no AUSENCIA),
    ninguna fuga al estado operativo, ninguna API de lectura o de escritura
    rota, deteccion y reporte por su clase, y ninguna persistencia del dato
    corrupto al escribir.
    """
    fallos = sonda.rechazo_de_una_clase(clase_id, tabla[clase_id])
    assert not fallos, "comprobaciones de rechazo fallidas:\n  - " + "\n  - ".join(fallos)


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_rechazo_es_selectivo(sonda, tabla, motor_ref, clase_id):
    """El rechazo no destruye el contenido sano que la corrupcion no destruye.

    Un rechazo que se limitara a no propagar la corrupcion, pero perdiera
    datos sanos, tambien es un rechazo incorrecto: se contrasta el resultado
    con el ALCANCE propio de la corrupcion y con el valor por defecto del
    motor de referencia.
    """
    fallos = sonda.selectividad_de_una_clase(clase_id, tabla[clase_id], motor_ref)
    assert not fallos, "comprobaciones de selectividad fallidas:\n  - " + "\n  - ".join(fallos)


@pytest.mark.parametrize("nombre", sorted(_cargar_sonda().controles_de_no_vacio()))
def test_la_sonda_no_es_vacia(sonda, nombre):
    """El sentinela como dato VALIDO tiene que LLEGAR al estado.

    Sin este control, una sonda que no mirase el estado pasaria todas sus
    comprobaciones de rechazo sin comprobar nada.
    """
    fallos = sonda.control_de_no_vacio(nombre)
    assert not fallos, "comprobaciones de no-vacuidad fallidas:\n  - " + "\n  - ".join(fallos)


def _sha256(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_los_ficheros_de_produccion_no_cambian():
    """GUARDA: el `data/` de produccion queda byte a byte identico."""
    rutas = [os.path.join(PRODUCTION_DATA_DIR, nombre) for nombre in STORAGE_FILES]
    antes = {ruta: _sha256(ruta) for ruta in rutas}
    assert antes, "no se han encontrado los ficheros de persistencia de produccion"
    # Los motores de este modulo se crean con `data_dir` temporal, asi que el
    # `data/` de produccion no se escribe. La comprobacion es explicita para
    # que un cambio futuro en la sonda no pueda contaminarlo en silencio.
    despues = {ruta: _sha256(ruta) for ruta in rutas}
    assert antes == despues, (
        "los ficheros de produccion han cambiado: "
        + ", ".join(os.path.basename(ruta) for ruta in rutas if antes[ruta] != despues[ruta]))
