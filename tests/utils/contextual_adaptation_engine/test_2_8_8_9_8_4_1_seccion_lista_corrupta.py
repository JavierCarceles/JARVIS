#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la SECCION LISTA corrupta de la base de conocimiento (2.8.8.9.8.4.1).

QUE COMPRUEBA ESTE TEST
Que una SECCION de la base de conocimiento cuyo FORMATO REAL es una LISTA (por
ejemplo `learning_results`) y que llega como MAPEO no ABORTA la carga del
fichero. La seccion se rechaza ENTERA en el NIVEL de la SECCION (su valor por
DEFECTO es el que la conserva) y el resto de secciones SANAS del MISMO fichero
sobreviven: la corrupcion de una seccion no puede determinar el valor de otra.

  - la carga NO lanza y DECLARA lo que ocurrio (`load_knowledge_base()`);
  - las secciones sanas del MISMO fichero LLEGAN al estado, con su SENTINELA;
  - la seccion corrupta NO llega al estado: conserva su valor por DEFECTO;
  - el contenido corrupto no aparece en NINGUN sitio del estado;
  - el fichero corrupto NO se reescribe (la recuperacion es de CARGA);
  - el INFORME de recuperacion no arrastra el dato corrupto (informa, no usa);
  - CONTROL de no-vacuo: con el payload SANO las mismas secciones LLEGAN todas;
  - REGRESION: una seccion MAPEADA con un GRUPO corrupto sigue recuperandose
    como antes (el camino de los grupos no se ha tocado);
  - GUARDA: los ficheros de PRODUCCION no cambian.

DERIVACION DE LOS ESCENARIOS
Las secciones de tipo LISTA no se escriben a mano: se DERIVAN del FORMATO REAL
que el propio motor declara en `_valores_por_defecto`, de modo que el test
sigue siendo fiel si el motor anade o retira secciones.

AISLAMIENTO
Todos los motores se crean con `data_dir` temporal. La sesion se ejecuta dentro
del sandbox de CWD de `tests/conftest.py`, de modo que las rutas RELATIVAS de los
subsistemas ajenos caen en el temporal y no en el repo. El modulo incluye ademas
un TEST DE GUARDA por sha256 de los ficheros de produccion vigilados.
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

KB = "contextual_knowledge_base.json"

SENTINELA = "SENTINELA_841"
SENTINELA_CORRUPTO = "SENTINELA_CORRUPTO_841"

# Secciones MAPEADAS y SANAS que se usan como referencia de supervivencia.
SECCIONES_SANAS = {
    "context_patterns": {"production": [{"patron": SENTINELA}]},
    "success_patterns": {"production": [{"patron": SENTINELA}]},
    "adaptation_strategies": {"production": [{"strategy_id": SENTINELA}]},
}


# ------------------------------------------------------------- auxiliares
def _motor_con_base(data_dir, data):
    """Motor con un `contextual_knowledge_base.json` de contenido `data`."""
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, KB), "w", encoding="utf-8") as handle:
        json.dump({"version": "2.0", "data": data}, handle, ensure_ascii=False)
    return ContextualAdaptationEngine(data_dir=data_dir)


def _secciones_de_tipo_lista(motor):
    """Secciones de la base cuyo FORMATO REAL es una LISTA.

    Se derivan del propio motor (`_valores_por_defecto`), no de una lista
    escrita a mano: si el motor anade o retira secciones, el test sigue siendo
    fiel al FORMATO REAL.
    """
    return sorted(clave for clave, valor in motor._valores_por_defecto.items()
                  if isinstance(valor, list))


def _contenido_corrupto(seccion):
    """Payload en el que `seccion` llega como MAPEO (corrupcion de TIPO)."""
    datos = dict(SECCIONES_SANAS)
    datos[seccion] = {"no_es_una_lista": SENTINELA_CORRUPTO}
    return datos


@pytest.fixture(scope="module")
def motor_ref(tmp_path_factory):
    """Motor de REFERENCIA: sin ningun fichero corrupto."""
    data_dir = str(tmp_path_factory.mktemp("referencia841") / "data")
    return ContextualAdaptationEngine(data_dir=data_dir)


@pytest.fixture(scope="module")
def secciones_de_tipo_lista(motor_ref):
    return _secciones_de_tipo_lista(motor_ref)


# ============================================================ EL CONTRATO
def test_la_base_declara_secciones_de_tipo_lista(secciones_de_tipo_lista):
    """El FORMATO REAL declara secciones de tipo LISTA (y son varias)."""
    assert secciones_de_tipo_lista, (
        "el motor no declara ninguna seccion de tipo LISTA: el escenario de "
        "esta unidad no se puede construir")
    assert "learning_results" in secciones_de_tipo_lista, (
        "`learning_results` deberia ser una seccion de tipo LISTA")


# ================================================== LA CARGA NO SE ABORTA
@pytest.mark.parametrize("seccion", [
    "goal_adaptation_feedback", "learning_results", "goal_adaptation_proposals",
    "goal_validations", "failure_patterns", "applied_patterns",
    "applied_strategies", "batch_transfer_summary", "auto_transfer_stats",
    "transfer_recommendations", "integration_records",
])
def test_una_seccion_lista_corrupta_no_aborta_la_carga(tmp_path, seccion):
    """La seccion corrupta NO aborta la carga del fichero entero.

    La EXCEPCION que abortaba el fichero entero (al iterar los grupos de un
    valor por defecto de tipo LISTA) hacia perder las secciones SANAS del mismo
    fichero. Aqui se exige que la carga termine, que DECLARE lo que ocurrio y
    que las secciones sanas LLEGUEN al estado.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_con_base(data_dir, _contenido_corrupto(seccion))

    assert motor.load_knowledge_base() is True, (
        "la carga ha fallado: una seccion corrupta ha abortado el fichero")

    base = motor.knowledge_base
    assert base["context_patterns"]["production"] == [{"patron": SENTINELA}], (
        "la seccion sana `context_patterns` se ha perdido por culpa de la "
        "seccion corrupta")
    assert base["success_patterns"]["production"] == [{"patron": SENTINELA}], (
        "la seccion sana `success_patterns` se ha perdido por culpa de la "
        "seccion corrupta")
    assert base["adaptation_strategies"]["production"] == [{"strategy_id": SENTINELA}], (
        "la seccion sana `adaptation_strategies` se ha perdido por culpa de la "
        "seccion corrupta")


@pytest.mark.parametrize("seccion", [
    "goal_adaptation_feedback", "learning_results", "goal_adaptation_proposals",
    "goal_validations", "failure_patterns", "applied_patterns",
    "applied_strategies", "batch_transfer_summary", "auto_transfer_stats",
    "transfer_recommendations", "integration_records",
])
def test_la_seccion_corrupta_no_llega_al_estado(tmp_path, seccion):
    """La seccion corrupta se RECHAZA ENTERA: no llega al estado.

    Conserva el valor por DEFECTO que declara el FORMATO REAL (una lista
    vacia): la recuperacion no inventa datos y el dato corrupto no se usa.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_con_base(data_dir, _contenido_corrupto(seccion))
    motor.load_knowledge_base()

    assert motor.knowledge_base[seccion] == [], (
        f"la seccion corrupta `{seccion}` ha llegado al estado: "
        f"{motor.knowledge_base[seccion]!r}")
    assert SENTINELA_CORRUPTO not in json.dumps(motor.knowledge_base, default=str), (
        f"el contenido corrupto de `{seccion}` ha llegado al estado")


def test_la_carga_no_aborta_con_varias_secciones_corruptas(tmp_path):
    """Varias secciones corruptas a la vez: la carga sigue,Y las sanas sobreviven."""
    data_dir = str(tmp_path / "data")
    datos = dict(SECCIONES_SANAS)
    datos["learning_results"] = {"no_es_una_lista": SENTINELA_CORRUPTO}
    datos["integration_records"] = {"no_es_una_lista": SENTINELA_CORRUPTO}
    motor = _motor_con_base(data_dir, datos)

    assert motor.load_knowledge_base() is True
    base = motor.knowledge_base
    assert base["context_patterns"]["production"] == [{"patron": SENTINELA}]
    assert base["success_patterns"]["production"] == [{"patron": SENTINELA}]
    assert base["learning_results"] == []
    assert base["integration_records"] == []


def test_la_carga_declara_las_unidades_que_ha_obtenido(tmp_path):
    """La carga DECLARA lo que ha obtenido: la seccion corrupta NO cuenta.

    `_unidades_cargadas` es la cuenta de las unidades de datos utilizables
    que la carga ha obtenido: una seccion que se ha rechazado no es una
    unidad obtenida.
    """
    data_dir = str(tmp_path / "data")
    motor = _motor_con_base(data_dir, _contenido_corrupto("learning_results"))
    motor.load_knowledge_base()

    assert motor._unidades_cargadas["knowledge_base"] == len(SECCIONES_SANAS), (
        "la cuenta de unidades cargadas incluye la seccion corrupta o "
        "excluye alguna seccion sana")


# ======================================================= EL FICHERO Y EL INFORME
def test_el_fichero_corrupto_no_se_reescribe(tmp_path):
    """La recuperacion es de CARGA: el fichero corrupto no se reescribe."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_base(data_dir, _contenido_corrupto("learning_results"))
    ruta = os.path.join(data_dir, KB)
    with open(ruta, "rb") as handle:
        contenido_antes = handle.read()
    mtime_antes = os.stat(ruta).st_mtime_ns

    motor.load_knowledge_base()

    with open(ruta, "rb") as handle:
        contenido_despues = handle.read()
    assert contenido_antes == contenido_despues, (
        "el fichero corrupto se ha reescrito durante la carga")
    assert os.stat(ruta).st_mtime_ns == mtime_antes, (
        "el fichero corrupto se ha reescrito durante la carga")


def test_el_informe_no_arrastra_el_dato_corrupto(tmp_path):
    """El INFORME informa, no usa: no contiene el contenido corrupto."""
    data_dir = str(tmp_path / "data")
    motor = _motor_con_base(data_dir, _contenido_corrupto("learning_results"))
    motor.load_knowledge_base()

    informe = motor.recovery_report()
    assert isinstance(informe.get("recoveries"), list)
    assert SENTINELA_CORRUPTO not in json.dumps(informe, default=str), (
        "el informe contiene el dato corrupto")


# ======================================================== CONTROL DE NO-VACUO
def test_control_con_payload_sano_llegan_todas_las_secciones(tmp_path):
    """CONTROL: sin corrupcion TODAS las secciones LLEGAN.

    Sin este control, un motor que perdiese siempre el contenido pasaria
    indistinguible de uno que lo conserva.
    """
    data_dir = str(tmp_path / "data")
    datos = dict(SECCIONES_SANAS)
    datos["learning_results"] = [{"adaptation_id": SENTINELA}]
    motor = _motor_con_base(data_dir, datos)

    assert motor.load_knowledge_base() is True
    base = motor.knowledge_base
    assert base["context_patterns"]["production"] == [{"patron": SENTINELA}]
    assert base["success_patterns"]["production"] == [{"patron": SENTINELA}]
    assert base["adaptation_strategies"]["production"] == [{"strategy_id": SENTINELA}]
    assert base["learning_results"] == [{"adaptation_id": SENTINELA}]
    assert motor._unidades_cargadas["knowledge_base"] == len(datos)
    assert motor.recovery_report()["count"] == 0, (
        "sin corrupcion no hay nada que recuperar")


# ============================================================== REGRESION
def test_regresion_un_grupo_corrupto_de_una_seccion_mapeada_se_recupera(tmp_path):
    """REGRESION: el camino de los GRUPOS no se ha tocado.

    Una seccion MAPEADA con un grupo (contexto) corrupto sigue recuperandose
    como antes: el grupo corrupto se descarta y sus HERMANOS sobreviven.
    """
    data_dir = str(tmp_path / "data")
    datos = dict(SECCIONES_SANAS)
    datos["context_patterns"] = {"production": {"no_es_una_lista": SENTINELA_CORRUPTO},
                                 "idle": [{"patron": SENTINELA}]}
    motor = _motor_con_base(data_dir, datos)

    assert motor.load_knowledge_base() is True
    base = motor.knowledge_base
    assert base["context_patterns"]["idle"] == [{"patron": SENTINELA}], (
        "el grupo hermano de la seccion mapeada se ha perdido")
    assert SENTINELA_CORRUPTO not in json.dumps(base, default=str), (
        "el grupo corrupto ha llegado al estado")

    informe = motor.recovery_report()
    recuperaciones = informe["recoveries"]
    assert recuperaciones, "el grupo corrupto no se ha registrado en el informe"
    assert any(entry.get("grupo") == "production" for entry in recuperaciones), (
        "el informe no nombra el grupo corrupto")
    assert all(entry.get("politica") == "preserve_siblings"
               for entry in recuperaciones), (
        "el informe no declara la politica declarada por el contrato")


# ================================================================== GUARDA
def _sha256(ruta):
    if not os.path.isfile(ruta):
        return None
    digest = hashlib.sha256()
    with open(ruta, "rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            digest.update(bloque)
    return digest.hexdigest()


def test_los_ficheros_de_produccion_no_cambian():
    """GUARDA: el `data/` de produccion queda byte a byte identico."""
    nombres = FICHEROS_DE_PERSISTENCIA + FICHEROS_DE_SUBSISTEMAS_AJENOS
    antes = {nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre)) for nombre in nombres}
    assert antes, "no se han encontrado los ficheros de produccion vigilados"
    despues = {nombre: _sha256(os.path.join(PRODUCTION_DATA_DIR, nombre)) for nombre in nombres}
    assert antes == despues, (
        "los ficheros de produccion han cambiado: "
        + ", ".join(sorted(n for n in nombres if antes[n] != despues[n])))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
