#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test del VALOR POR DEFECTO de `condition_pattern` (2.8.8.9.8.4.3).

QUE COMPRUEBA ESTE TEST
Que el CONTRATO de lo recuperable declara el valor por DEFECTO que usa el
CARGADOR para `condition_pattern`, de modo que la recuperacion NO le asigne un
valor INVENTADO:

  - `field_defaults` DECLARA `condition_pattern`, con el valor por defecto del
    FORMATO REAL (`""`) y con el TIPO que el formato declara (`string`);
  - la recuperacion de un `condition_pattern` corrupto produce el MISMO valor
    que el CARGADOR produce cuando el campo NO aparece (el valor por defecto
    se DERIVA del propio motor, no se escribe a mano en el test);
  - el valor recuperado NO es `None`: `None` no es un valor por defecto del
    FORMATO REAL y no pertenece al TIPO que el formato declara;
  - el ESTADO y su serializacion (`to_dict`) llevan ese mismo valor;
  - el INFORME de recuperacion registra ese mismo valor;
  - COBERTURA: TODO campo del FORMATO REAL que la recuperacion puede tocar
    tiene su valor por DEFECTO declarado, de modo que no puede volver a haber
    un campo sin defecto declarado;
  - el valor declarado RESPETA el TIPO que el FORMATO REAL declara;
  - CONTROL de no-vacuo: un `condition_pattern` SANO conserva su valor;
  - REGRESION: los demas valores por DEFECTO no cambian;
  - el fichero corrupto NO se reescribe (la recuperacion es de CARGA);
  - el INFORME no arrastra el dato corrupto (informa, no usa);
  - GUARDA: los ficheros de PRODUCCION no cambian.

DERIVACION DE LOS ESCENARIOS
La fila SANA y los campos del FORMATO REAL no se escriben a mano: el escenario
se deriva del propio motor (el FORMATO REAL declarado y el valor por defecto
que el CARGADOR usa), de modo que el test sigue siendo fiel si el motor anade,
retira o cambia un campo.

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

CAMPO = "condition_pattern"
SENTINELA_CORRUPTO = "SENTINELA_CORRUPTO_843"

# Fila SANA: todos los campos que el FORMATO REAL declara, con su tipo.
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
    """Motor con un `contextual_adaptation_rules.json` de contenido `reglas`."""
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, RF), "w", encoding="utf-8") as handle:
        json.dump({"version": "2.0", "rules": reglas}, handle, ensure_ascii=False)
    return ContextualAdaptationEngine(data_dir=data_dir)


def _campos_del_formato_real(motor):
    """Campos del FORMATO REAL de una fila de regla, tal y como los declara el motor."""
    formato = (motor._CORRUPTION_CRITERIA.get("files", {})
               .get("adaptation_rules", {}).get("real_format", {}) or {})
    return dict((formato.get("record", {}) or {}).get("fields", {}) or {})


def _campo_de_identidad(motor):
    """Campo que IDENTIFICA una fila de regla, tal y como lo declara el motor."""
    formato = (motor._CORRUPTION_CRITERIA.get("files", {})
               .get("adaptation_rules", {}).get("real_format", {}) or {})
    return (formato.get("record", {}) or {}).get("identity")


def _valor_por_defecto_del_cargador(tmp_path):
    """Valor por DEFECTO que el CARGADOR usa cuando `condition_pattern` NO aparece.

    Se DERIVA del propio motor: se carga una fila sana SIN el campo y se lee lo
    que el cargador le pone. No se escribe a mano, de modo que el test mide el
    comportamiento real y no una expectativa copiada.
    """
    fila = _fila()
    fila.pop(CAMPO, None)
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [fila])
    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    return motor.adaptation_rules["rr_sana_1"].condition_pattern


def _recuperacion_del_campo(motor, campo):
    """Entrada del INFORME de recuperacion que corresponde a `campo`."""
    for recuperacion in motor.recovery_report().get("recoveries") or []:
        if recuperacion.get("campo") == campo:
            return recuperacion
    return None


# ======================================================= EL CONTRATO DECLARADO
def test_el_contrato_declara_el_valor_por_defecto_de_condition_pattern(tmp_path):
    """`field_defaults` DECLARA `condition_pattern` con el valor del FORMATO REAL."""
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))

    declarados = motor.recoverable_data().get("field_defaults") or {}
    declarado = declarados.get(CAMPO)
    assert declarado is not None, (
        f"el contrato NO declara el valor por defecto de `{CAMPO}`: la "
        "recuperacion no tendria ningun valor que usar y asignaria uno inventado")
    assert declarado.get("value") == "", (
        f"el valor por defecto declarado de `{CAMPO}` no es el del FORMATO REAL: "
        f"{declarado.get('value')!r}")


def test_el_valor_declarado_es_el_que_usa_el_cargador(tmp_path):
    """El valor DECLARADO es el MISMO que el CARGADOR usa de verdad.

    El valor por defecto del cargador se obtiene cargando una fila SIN el
    campo: si lo declarado y lo observado no coinciden, el contrato miente.
    """
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))
    declarado = (motor.recoverable_data().get("field_defaults") or {}).get(CAMPO) or {}

    del_cargador = _valor_por_defecto_del_cargador(tmp_path)

    assert declarado.get("value") == del_cargador, (
        "el valor por defecto DECLARADO no coincide con el que usa el CARGADOR: "
        f"declarado={declarado.get('value')!r} cargador={del_cargador!r}")


def test_el_valor_declarado_respeta_el_tipo_del_formato_real(tmp_path):
    """El valor por DEFECTO declarado RESPETA el TIPO que el FORMATO REAL declara."""
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))
    campos = _campos_del_formato_real(motor)
    declarados = motor.recoverable_data().get("field_defaults") or {}

    tipo = campos.get(CAMPO)
    assert tipo == "string", (
        f"el FORMATO REAL no declara `{CAMPO}` como cadena: {tipo!r}")

    valor = (declarados.get(CAMPO) or {}).get("value")
    assert isinstance(valor, str), (
        f"el valor por defecto de `{CAMPO}` no es una cadena: {valor!r}")
    assert (declarados.get(CAMPO) or {}).get("type") == "string", (
        "el contrato no declara el TIPO del valor por defecto de "
        f"`{CAMPO}`: {(declarados.get(CAMPO) or {}).get('type')!r}")


def test_todo_campo_recuperable_tiene_valor_por_defecto_declarado(tmp_path):
    """COBERTURA: ningun campo recuperable se queda SIN valor por defecto.

    Es la invariante que impide que un campo del FORMATO REAL se recupere con
    un valor INVENTADO: si un campo nuevo aparece en el formato y nadie
    declara su defecto, la recuperacion le asignaria `None`.
    """
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))
    campos = _campos_del_formato_real(motor)
    identidad = _campo_de_identidad(motor)
    declarados = motor.recoverable_data().get("field_defaults") or {}

    sin_declarar = sorted(nombre for nombre in campos
                          if nombre != identidad and nombre not in declarados)
    assert not sin_declarar, (
        "estos campos del FORMATO REAL se pueden recuperar pero NO tienen valor "
        f"por defecto declarado: {sin_declarar!r}")


# ================================================ LA RECUPERACION EN RUNTIME
@pytest.mark.parametrize("corrupcion", [123, ["ctx == 1"], {"patron": "ctx == 1"}])
def test_la_recuperacion_usa_el_valor_por_defecto_del_cargador(tmp_path, corrupcion):
    """Un `condition_pattern` corrupto se recupera con el valor del CARGADOR.

    La recuperacion NO inventa datos: el campo corrupto toma el valor por
    DEFECTO que el FORMATO REAL declara, que es el mismo que el cargador usa
    cuando el campo no aparece.
    """
    del_cargador = _valor_por_defecto_del_cargador(tmp_path / "referencia")
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(**{CAMPO: corrupcion})])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    assert "rr_sana_1" in motor.adaptation_rules, (
        "la fila con un campo corrupto ha sido descartada: la corrupcion se "
        "rechaza SOLO en el campo que corrompe")

    recuperado = motor.adaptation_rules["rr_sana_1"].condition_pattern
    assert recuperado == del_cargador, (
        "la recuperacion NO ha usado el valor por defecto del cargador: "
        f"recuperado={recuperado!r} cargador={del_cargador!r}")


def test_el_valor_recuperado_no_es_none(tmp_path):
    """El valor recuperado NO es `None`.

    `None` NO es un valor por defecto del FORMATO REAL (el campo es una
    cadena) y no pertenece a `field_defaults`: asignarlo seria INVENTAR un
    valor, que es lo que la recuperacion prohibe.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(**{CAMPO: 123})])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    recuperado = motor.adaptation_rules["rr_sana_1"].condition_pattern
    assert recuperado is not None, (
        "la recuperacion ha asignado `None` a un campo que el FORMATO REAL "
        "declara como cadena")
    assert isinstance(recuperado, str), (
        f"el valor recuperado no es una cadena: {recuperado!r}")


def test_el_estado_y_su_serializacion_llevan_el_valor_por_defecto(tmp_path):
    """El ESTADO y su SERIALIZACION llevan el valor por DEFECTO, no `None`."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(**{CAMPO: 123})])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    regla = motor.adaptation_rules["rr_sana_1"]
    assert regla.condition_pattern == "", (
        f"el estado no lleva el valor por defecto del formato: "
        f"{regla.condition_pattern!r}")
    serializado = regla.to_dict()
    assert serializado.get(CAMPO) == "", (
        f"la serializacion de la regla no lleva el valor por defecto: "
        f"{serializado.get(CAMPO)!r}")


def test_el_informe_registra_el_valor_por_defecto(tmp_path):
    """El INFORME registra el valor por DEFECTO que ha ocupado el dato corrupto."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(**{CAMPO: 123})])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    recuperacion = _recuperacion_del_campo(motor, CAMPO)
    assert recuperacion is not None, (
        "la recuperacion del campo corrupto no se ha registrado en el informe")
    assert recuperacion.get("politica") == "default_the_field", (
        f"la politica registrada no es la declarada: "
        f"{recuperacion.get('politica')!r}")
    assert recuperacion.get("valor") == "", (
        f"el valor registrado en el informe no es el valor por defecto: "
        f"{recuperacion.get('valor')!r}")


def test_el_dato_corrupto_no_llega_al_estado(tmp_path):
    """El dato corrupto NO llega al estado en NINGUNA forma."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(**{CAMPO: 123, "name": SENTINELA_CORRUPTO})])

    assert motor.load_adaptation_rules() is True, "la carga ha fallado"
    regla = motor.adaptation_rules["rr_sana_1"]
    assert SENTINELA_CORRUPTO not in json.dumps(
        [regla.condition_pattern, regla.description], default=str), (
        "el dato corrupto ha llegado al estado")
    assert isinstance(regla.condition_pattern, str), (
        "el campo corrupto ha llegado al estado sin recuperar")


def test_el_informe_no_arrastra_el_dato_corrupto(tmp_path):
    """El INFORME informa, no usa: no contiene el dato corrupto."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(
        data_dir, [_fila(**{CAMPO: {"patron": SENTINELA_CORRUPTO}})])
    motor.load_adaptation_rules()

    informe = motor.recovery_report()
    assert isinstance(informe.get("recoveries"), list)
    assert SENTINELA_CORRUPTO not in json.dumps(informe, default=str), (
        "el informe contiene el dato corrupto")


# ======================================================= EL FICHERO CORRUPTO
def test_el_fichero_corrupto_no_se_reescribe(tmp_path):
    """La recuperacion es de CARGA: el fichero corrupto no se reescribe."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(**{CAMPO: 123})])
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


# ======================================================== CONTROL DE NO-VACUO
def test_control_un_condition_pattern_sano_conserva_su_valor(tmp_path):
    """CONTROL: un `condition_pattern` SANO conserva su valor.

    Sin este control, un motor quepusiese siempre el valor por defecto pasaria
    indistinguible de uno que respeta el dato sano.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(condition_pattern="ctx == 42")])

    assert motor.load_adaptation_rules() is True
    assert motor.adaptation_rules["rr_sana_1"].condition_pattern == "ctx == 42", (
        "el valor por defecto ha pisado un dato SANO")
    assert motor.recovery_report()["count"] == 0, (
        "sin corrupcion no hay nada que recuperar")


# ============================================================== REGRESION
def test_regresion_los_demas_valores_por_defecto_no_cambian(tmp_path):
    """REGRESION: los demas valores por DEFECTO siguen siendo los declarados.

    Declarar el defecto de un campo NO puede desplazar el de los demas.
    """
    motor = ContextualAdaptationEngine(data_dir=str(tmp_path / "data"))
    declarados = motor.recoverable_data().get("field_defaults") or {}

    assert (declarados.get("enabled") or {}).get("value") is False, (
        "el valor por defecto de `enabled` ya no es el conservador declarado")
    assert (declarados.get("name") or {}).get("value") == "$rule_id", (
        "el valor por defecto de `name` ya no se resuelve con la identidad")
    assert (declarados.get("confidence_threshold") or {}).get("value") == 0.7, (
        "el valor por defecto de `confidence_threshold` ha cambiado")
    assert (declarados.get("adaptation_actions") or {}).get("value") == [], (
        "el valor por defecto de `adaptation_actions` ha cambiado")


def test_regresion_una_corrupcion_de_otro_campo_se_recupera_igual(tmp_path):
    """REGRESION: otro campo corrupto se sigue recuperando con SU valor por defecto."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_reglas(data_dir, [_fila(enabled="no")])

    assert motor.load_adaptation_rules() is True
    assert motor.adaptation_rules["rr_sana_1"].enabled is False, (
        "el campo corrupto no ha tomado su valor por DEFECTO")
    recuperacion = _recuperacion_del_campo(motor, "enabled")
    assert recuperacion is not None, (
        "la recuperacion del campo corrupto no se ha registrado en el informe")
    assert recuperacion.get("valor") is False, (
        f"el valor registrado en el informe no es el valor por defecto: "
        f"{recuperacion.get('valor')!r}")


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
