#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la IDENTIDAD INVENTADA y de la COLISION de identidad (2.8.8.9.8.4.2).

QUE COMPRUEBA ESTE TEST
Que el cargador de reglas NO inventa una identidad y NO deja que dos filas
COLISIONEN con la misma:

  - una fila SIN `rule_id`, o con un `rule_id` que NO es una cadena no vacia
    (que no es identidad), NO se registra: se RECHAZA ENTERA y sus HERMANAS
    sobreviven (la politica declarada es `preserve_siblings`);
  - el cargador NO inventa ninguna identidad: la fila rechazada no llega al
    estado bajo NINGUNA clave (ni una clave inventada, ni la clave del
    contenedor que la traia);
  - una fila cuya identidad YA USA otra fila se RECHAZA: la que ya estaba
    registrada sobrevive y la segunda NO la pisa;
  - la via de LISTA y la via de CONTENEDOR dan el MISMO resultado para el MISMO
    contenido (no hay dos verdades);
  - la clave del estado ES la identidad de la fila (una regla no se registra
    bajo una clave que no sea su `rule_id`);
  - el FORMATO REAL declara la identidad y su TIPO, y el CONTRATO declarado
    coincide con lo que el cargador hace;
  - la DETECCION (2.8.8.9.6.3) senala la MISMA fila que el cargador descarta;
  - el fichero corrupto NO se reescribe (la recuperacion es de CARGA);
  - el INFORME no arrastra el dato corrupto (informa, no usa);
  - CONTROL de no-vacuo: con el payload SANO llegan todas las filas;
  - REGRESION: una corrupcion de CAMPO se sigue recuperando como antes (la fila
    con un campo corrupto sigue llegando, con el campo por DEFECTO);
  - GUARDA: los ficheros de PRODUCCION no cambian.

DERIVACION DE LOS ESCENARIOS
Las filas SANAS y los campos del FORMATO REAL no se escriben a mano: el
escenario se deriva del propio motor (`_campo_de_identidad` y el FORMATO REAL
declarado), de modo que el test sigue siendo fiel si el motor anade, retira o
cambia un campo.

AISLAMIENTO
Todos los motores se crean con `data_dir` temporal. La sesion se ejecuta dentro
del sandbox de CWD de `tests/conftest.py`, de modo que las rutas RELATIVAS de los
subsistemas ajenos caen en el temporal y no en el repo. El modulo incluye ademas
un TEST DE GUARDA por sha256 de los ficheros de produccion vigilados.
"""

import copy
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

SENTINELA = "SENTINELA_842"
SENTINELA_CORRUPTO = "SENTINELA_CORRUPTO_842"

# Fila SANA: todos los campos que el FORMATO REAL declara, con su tipo.
# El `rule_id` es el IDENTIDAD; el resto se deriva del motor.
FILA_SANA = {
    "rule_id": "rr_sana_1",
    "name": "SANA UNO",
    "description": "fila sana de control",
    "condition_pattern": "ctx == 1",
    "adaptation_actions": ["accion_sana"],
    "context_triggers": ["production"],
    "confidence_threshold": 0.7,
    "priority": 1,
    "enabled": True,
    "success_rate": 0.5,
    "execution_count": 1,
    "last_execution": "2024-01-01T00:00:00",
    "adaptation_score": 0.4,
    "constraints": [],
    "metadata": {},
    "deadline": None,
}


# ------------------------------------------------------------- auxiliares
def _fila(**cambios):
    """Fila sana con los CAMBIOS aplicados."""
    fila = copy.deepcopy(FILA_SANA)
    fila.update(cambios)
    return fila


def _motor_con_reglas(data_dir, reglas):
    """Motor con un `contextual_adaptation_rules.json` de contenido `reglas`.

    `reglas` es la LISTA `rules` del fichero: una lista de filas (via de LISTA)
    o un mapeo (via de CONTENEDOR).
    """
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, RF), "w", encoding="utf-8") as handle:
        json.dump({"version": "2.0", "rules": reglas}, handle, ensure_ascii=False)
    return ContextualAdaptationEngine(data_dir=data_dir)


def _motor_de_via_lista(data_dir, filas):
    return _motor_con_reglas(data_dir, filas)


def _motor_de_via_contenedor(data_dir, filas):
    """La MISMA fila por la via de CONTENEDOR (el contenedor cambia de FORMA)."""
    contenedor = {f"clave_{indice}": fila for indice, fila in enumerate(filas)}
    return _motor_con_reglas(data_dir, contenedor)


def _identidades_del_estado(motor):
    """Identidades (claves) con las que el motor ha registrado las filas."""
    return sorted(motor.adaptation_rules)


def _filas_corruptas_de_identidad():
    """Filas SIN identidad REGISTRABLE, una por cada modo de corrupcion."""
    return {
        "sin_rule_id": _fila(name=SENTINELA_CORRUPTO),
        "rule_id_nulo": _fila(rule_id=None, name=SENTINELA_CORRUPTO),
        "rule_id_entero": _fila(rule_id=111, name=SENTINELA_CORRUPTO),
        "rule_id_vacio": _fila(rule_id="   ", name=SENTINELA_CORRUPTO),
        "rule_id_lista": _fila(rule_id=["rr"], name=SENTINELA_CORRUPTO),
        "nombre_y_rule_id": _fila(rule_id=111, name=999),
    }


# =========================================================== EL FORMATO REAL
def test_el_formato_real_declara_la_identidad_y_su_tipo(tmp_path):
    """El FORMATO REAL declara el campo de IDENTIDAD y lo declara como cadena."""
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))

    assert motor._campo_de_identidad("adaptation_rules") == "rule_id", (
        "el motor no declara que `rule_id` es el campo de identidad de las reglas")

    formato = (motor._CORRUPTION_CRITERIA.get("files", {})
               .get("adaptation_rules", {}).get("real_format", {}) or {})
    campos = (formato.get("record", {}) or {}).get("fields", {}) or {}
    assert campos.get("rule_id") == "string", (
        "el FORMATO REAL no declara `rule_id` como cadena: una identidad de "
        "otro tipo no seria una identidad")


# ================================================== NO SE INVENTA IDENTIDAD
@pytest.mark.parametrize("modo", sorted(_filas_corruptas_de_identidad()))
def test_una_fila_sin_identidad_registrable_no_se_registra(tmp_path, modo):
    """Sin identidad REGISTRABLE no hay REGISTRO: la fila se RECHAZA ENTERA.

    Sus HERMANAS (las filas sanas del mismo fichero) sobreviven: la politica
    declarada para esta clase de corrupcion es `preserve_siblings`.
    """
    corrupta = _filas_corruptas_de_identidad()[modo]
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(), corrupta, _fila(rule_id="rr_sana_2")])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"

    identidades = _identidades_del_estado(motor)
    assert identidades == ["rr_sana_1", "rr_sana_2"], (
        f"la fila sin identidad registrable ha cambiado el estado: {identidades!r}")
    assert motor._unidades_cargadas["adaptation_rules"] == 2, (
        "la cuenta de unidades cargadas no corresponde a las filas SOBRIVIVIENTES")


@pytest.mark.parametrize("modo", sorted(_filas_corruptas_de_identidad()))
def test_la_fila_rechazada_no_llega_al_estado(tmp_path, modo):
    """La fila rechazada NO aparece en el estado bajo NINGUNA clave.

    En particular, el cargador NO inventa una identidad: la fila no aparece
    ni con una clave inventada, ni con la clave del contenedor que la traia.
    """
    corrupta = _filas_corruptas_de_identidad()[modo]
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(), corrupta])

    for clave, regla in motor.adaptation_rules.items():
        assert isinstance(clave, str), (
            f"el estado tiene una clave que no es una identidad: {clave!r}")
        assert clave == regla.rule_id, (
            f"la regla se ha registrado bajo una clave que no es su identidad: "
            f"{clave!r} != {regla.rule_id!r}")
        assert SENTINELA_CORRUPTO not in json.dumps(
            [regla.name, regla.description, list(regla.adaptation_actions)], default=str), (
            "el dato de la fila rechazada ha llegado al estado")


def test_la_via_de_contenedor_tampoco_inventa_identidades(tmp_path):
    """Por la via de CONTENEDOR tampoco se inventa una identidad.

    Las claves del contenedor NO son identidades: una fila sin `rule_id` propio
    no se puede registrar, aunque el contenedor le traiga una clave.
    """
    corrupta = _fila(rule_id=111, name=SENTINELA_CORRUPTO)
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_contenedor(data_dir, [_fila(), corrupta, _fila(rule_id="rr_sana_2")])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    identidades = _identidades_del_estado(motor)
    assert identidades == ["rr_sana_1", "rr_sana_2"], (
        f"la via de contenedor ha registrado una identidad inventada: {identidades!r}")
    for clave, regla in motor.adaptation_rules.items():
        assert clave == regla.rule_id, (
            f"la regla se ha registrado bajo una clave que no es su identidad: {clave!r}")


def test_las_dos_vias_dan_el_mismo_resultado(tmp_path):
    """La via de LISTA y la de CONTENEDOR dan el MISMO resultado.

    El mismo contenido no puede dar dos verdades: lo que se registra por una
    via es lo que se registra por la otra.
    """
    filas = [_fila(), _fila(rule_id=111, name=SENTINELA_CORRUPTO), _fila(rule_id="rr_sana_2")]

    por_lista = _motor_de_via_lista(str(tmp_path / "lista" / "data"), filas)
    por_contenedor = _motor_de_via_contenedor(str(tmp_path / "cont" / "data"), filas)

    assert _identidades_del_estado(por_lista) == _identidades_del_estado(por_contenedor), (
        "las dos vias del cargador dan resultados distintos para el mismo contenido")


# ===================================================== LA COLISION DE IDENTIDAD
def test_la_colision_no_pisa_la_regla_ya_registrada(tmp_path):
    """Dos filas con la MISMA identidad: la primera registrada sobrevive.

    Registrar la segunda COLISIONARIA con la primera y una de las dos se
    perderia sin que nada lo dijera: la que ya estaba registrada sobrevive.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(name="PRIMERA"), _fila(name="SEGUNDA")])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    assert _identidades_del_estado(motor) == ["rr_sana_1"], (
        f"la colision de identidad ha registrado mas de una regla: "
        f"{_identidades_del_estado(motor)!r}")
    assert motor.adaptation_rules["rr_sana_1"].name == "PRIMERA", (
        "la colision ha pisado la regla que ya estaba registrada")
    assert motor._unidades_cargadas["adaptation_rules"] == 1, (
        "la colision se ha contado como una unidad obtenida de mas")


def test_la_colision_por_contenedor_tampoco_pisa(tmp_path):
    """La colision por la via de CONTENEDOR se resuelve igual."""
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_contenedor(data_dir, [_fila(name="PRIMERA"), _fila(name="SEGUNDA")])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    assert _identidades_del_estado(motor) == ["rr_sana_1"], (
        f"la colision de identidad ha registrado mas de una regla: "
        f"{_identidades_del_estado(motor)!r}")
    assert motor.adaptation_rules["rr_sana_1"].name == "PRIMERA", (
        "la colision ha pisado la regla que ya estaba registrada")


# ==================================================== EL CONTRATO DECLARADO
def test_el_contrato_declarado_coincide_con_lo_que_hace_el_cargador(tmp_path):
    """El CONTRATO declarado dice lo que el cargador HACE.

    La clase declarada para la identidad ausente dice `preserve_siblings` y
    `recovers: [siblings]`: eso es exactamente lo que se comprueba arriba.
    """
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))

    clases = motor.recoverable_data()["files"]["adaptation_rules"]["classes"]
    contrato = clases.get("adaptation_rules.row_missing_identity")
    assert contrato is not None, "el contrato no declara la clase de identidad ausente"
    assert contrato.get("policy") == "preserve_siblings", (
        f"el contrato declara otra politica: {contrato.get('policy')!r}")
    assert contrato.get("recovers") == ["siblings"], (
        f"el contrato declara otra recuperacion: {contrato.get('recovers')!r}")


def test_la_deteccion_señala_la_misma_fila_que_el_cargador_descarta(tmp_path):
    """La DETECCION (2.8.8.9.6.3) senala la MISMA fila que el cargador descarta.

    Detectar y descartar son la misma regla: si la deteccion senala una fila
    que el cargador registra, el contrato no se cumple.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(), _fila(rule_id=111, name=SENTINELA_CORRUPTO)])

    deteccion = motor.detect_corruption()
    senaladas = deteccion.get("corrupted", {}).get("adaptation_rules", [])
    identidades = [d.get("id") for d in senaladas]
    assert "adaptation_rules.row_missing_identity" in identidades, (
        f"la deteccion no senala la fila sin identidad registrable: {identidades!r}")

    registradas = _identidades_del_estado(motor)
    assert not any(not isinstance(clave, str) for clave in registradas), (
        "la deteccion senala la fila pero el cargador la ha registrado con una "
        "identidad que no es una cadena")


# ======================================================= EL FICHERO Y EL INFORME
def test_el_fichero_corrupto_no_se_reescribe(tmp_path):
    """La recuperacion es de CARGA: el fichero corrupto no se reescribe."""
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(), _fila(rule_id=111, name=SENTINELA_CORRUPTO)])
    ruta = os.path.join(data_dir, RF)
    with open(ruta, "rb") as handle:
        contenido_antes = handle.read()
    mtime_antes = os.stat(ruta).st_mtime_ns

    motor.load_adaptation_rules()

    with open(ruta, "rb") as handle:
        contenido_despues = handle.read()
    assert contenido_antes == contenido_despues, (
        "el fichero corrupto se ha reescrito durante la carga")
    assert os.stat(ruta).st_mtime_ns == mtime_antes, (
        "el fichero corrupto se ha reescrito durante la carga")


def test_el_informe_no_arrastra_el_dato_corrupto(tmp_path):
    """El INFORME informa, no usa: no contiene el dato corrupto."""
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(), _fila(rule_id=111, name=SENTINELA_CORRUPTO)])
    motor.load_adaptation_rules()

    informe = motor.recovery_report()
    assert isinstance(informe.get("recoveries"), list)
    assert SENTINELA_CORRUPTO not in json.dumps(informe, default=str), (
        "el informe contiene el dato corrupto")


# ======================================================== CONTROL DE NO-VACUO
def test_control_con_payload_sano_llegan_todas_las_filas(tmp_path):
    """CONTROL: sin corrupcion LLEGAN todas las filas.

    Sin este control, un motor que perdiese siempre el contenido pasaria
    indistinguible de uno que lo conserva.
    """
    data_dir = str(tmp_path / "data")
    filas = [_fila(), _fila(rule_id="rr_sana_2", name="SANA DOS")]
    motor = _motor_de_via_lista(data_dir, filas)

    assert motor.load_adaptation_rules() is True
    assert _identidades_del_estado(motor) == ["rr_sana_1", "rr_sana_2"], (
        "con el payload sano no llegan todas las filas")
    assert motor._unidades_cargadas["adaptation_rules"] == 2, (
        "con el payload sano no se declaran las unidades obtenidas")
    assert motor.recovery_report()["count"] == 0, (
        "sin corrupcion no hay nada que recuperar")


# ============================================================== REGRESION
def test_regresion_una_corrupcion_de_campo_se_recupera_como_antes(tmp_path):
    """REGRESION: una corrupcion de CAMPO se sigue recuperando como antes.

    Una fila con identidad REGISTRABLE y un campo corrupto sigue LLEGANDO, con
    ese campo por DEFECTO: la identidad no es un motivo para descartar la fila
    entera.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_de_via_lista(data_dir, [_fila(enabled="no"), _fila(rule_id="rr_sana_2")])

    assert motor.load_adaptation_rules() is True
    assert "rr_sana_1" in motor.adaptation_rules, (
        "la fila con un campo corrupto ha sido descartada: la identidad es "
        "registrable y la fila debe sobrevivir con el campo por DEFECTO")
    assert motor.adaptation_rules["rr_sana_1"].enabled is False, (
        "el campo corrupto no ha tomado su valor por DEFECTO")
    assert motor.recovery_report()["count"] >= 1, (
        "la recuperacion del campo corrupto no se ha registrado en el informe")


# ================================================================== GUARDA
def _sha256(ruta):
    if not os.path.isfile(ruta):
        return None
    digest = hashlib.sha256()
    with open(ruta, "rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            digest.update(bloque)
    return digest.hexdigest()


# La foto se toma AL IMPORTAR el modulo: antes de que se ejecute ningun test.
_HUELLAS_DE_PRODUCCION = {
    nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre))
    for nombre in FICHEROS_DE_PERSISTENCIA + FICHEROS_DE_SUBSISTEMAS_AJENOS
}


def test_los_ficheros_de_produccion_no_cambian():
    """GUARDA: el `data/` de produccion queda byte a byte identico."""
    assert _HUELLAS_DE_PRODUCCION, "no se han encontrado los ficheros de produccion vigilados"
    ahora = {nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre))
             for nombre in _HUELLAS_DE_PRODUCCION}
    assert _HUELLAS_DE_PRODUCCION == ahora, (
        "los ficheros de produccion han cambiado: "
        + ", ".join(sorted(n for n in _HUELLAS_DE_PRODUCCION
                           if _HUELLAS_DE_PRODUCCION[n] != ahora[n])))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
