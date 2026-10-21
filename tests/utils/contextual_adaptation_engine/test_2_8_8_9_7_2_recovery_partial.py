#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la RECUPERACIÓN PARCIAL (2.8.8.9.7.2).

QUE COMPRUEBA ESTE TEST
Que el motor RECUPERA lo que el contrato de 2.8.8.9.7.1 declara recuperable,
y lo hace SIN inventar datos y SIN reescribir el fichero:

  - la API `recovery_report()` expone un INFORME bien formado: la lista de lo
    recuperado, el numero de recuperaciones y los ficheros afectados, y el
    numero coincide con la lista;
  - la API es de SOLO LECTURA: no crea ficheros, no altera el estado del motor
    y devuelve una COPIA defensiva (mutar lo devuelto no cambia el motor);
  - sin corrupcion NO hay nada que recuperar (CONTROL de no-vacuo): un informe
    siempre lleno no probaria nada;
  - la recuperacion se REGISTRA en la UNIDAD que corrompe, con la POLITICA que
    el contrato declara para esa clase;
  - el valor por DEFECTO que ocupa el lugar del dato corrupto es el que el
    contrato DECLARA (no un valor inventado);
  - el ESTADO guarda ese valor por DEFECTO: la recuperacion no inventa datos;
  - lo que el contrato declara RECUPERABLE LLEGA al estado: la unidad
    independiente de la unidad corrupta sobrevive;
  - el INFORME no contiene el dato corrupto.

RELACION CON 2.8.8.9.7.1
`test_2_8_8_9_7_1_recoverable.py` (7.1) MIDE la distancia entre el contrato
de lo recuperable y el runtime: exige que lo MEDIDO coincida con lo DECLARADO.
Este modulo (7.2) comprueba la IMPLEMENTACION de la recuperacion: que la
recuperacion existe, que se registra, que usa los valores por DEFECTO
declarados y que lo sano sobrevive.

INDEPENDENCIA DEL INSTRUMENTO
Este modulo reutiliza de la sonda `identify_recoverable_real.py` (mismo
directorio) sus ESCENARIOS y sus OBSERVADORES, no su codigo de salida: los
escenarios llevan su propio SENTINELA en el punto exacto que se corrompe y su
propia marca en el contenido SANO que la corrupcion no destruye. La sonda se
carga por RUTA (no por `import` de paquete) porque es un script independiente
de la suite pytest, ejecutable tambien de forma aislada:
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
import json
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
    data_dir = str(tmp_path_factory.mktemp("referencia72") / "data")
    return sonda.nuevo_motor(data_dir)


@pytest.fixture(scope="module")
def contrato(motor_ref):
    """CONTRATO declarado de lo recuperable, clase por clase."""
    recuperable = motor_ref.recoverable_data()
    declaradas = {clase_id: clase
                  for spec in recuperable["files"].values()
                  for clase_id, clase in spec["classes"].items()}
    return recuperable, declaradas


@pytest.fixture(scope="module")
def tabla(sonda):
    """Escenarios PROPIOS de la sonda, uno por clase de corrupcion."""
    return sonda.escenarios()


@pytest.fixture(scope="module")
def observado(sonda, tabla, tmp_path_factory):
    """Lo OBSERVADO en runtime, clase por clase.

    Se monta el escenario corrupto, se carga el motor y se anota:
      - `informe`:  lo que declara `recovery_report()`;
      - `reglas`:   las reglas que han sobrevivido, con sus campos;
      - `base`:     la base de conocimiento que ha sobrevivido;
      - `unidades`: si las unidades SANAS independientes han llegado al estado
                    (las observa la sonda, con su propio instrumento);
      - `corrupto`: si el SENTINELA corrupto ha llegado al estado.
    """
    base = tmp_path_factory.mktemp("recuperacion")
    resultado = {}
    for clase_id, escenario in tabla.items():
        data_dir = str(base / clase_id.replace(".", "_") / "data")
        os.makedirs(data_dir, exist_ok=True)
        sonda.materializar(escenario["files"], data_dir)
        motor = sonda.nuevo_motor(data_dir)
        estado = sonda.firma_operativa(motor)
        unidades = {}
        for unidad in escenario["unidades"]:
            try:
                presente = bool(unidad["presente"](motor))
            except Exception:  # noqa: BLE001 - un observador que falla no observa
                presente = False
            unidades[unidad["etiqueta"]] = presente
        reglas = {}
        for rule_id, regla in (motor.adaptation_rules or {}).items():
            datos = regla.to_dict() if hasattr(regla, "to_dict") else dict(regla)
            reglas[rule_id] = datos
        resultado[clase_id] = {
            "informe": motor.recovery_report(),
            "reglas": reglas,
            "base": json.loads(json.dumps(motor.knowledge_base or {}, default=str)),
            "unidades": unidades,
            "corrupto": (escenario["marca"] in estado
                         or sonda._solo_letras(escenario["marca"]) in sonda._solo_letras(estado)),
            "marca": escenario["marca"],
        }
    return resultado


CLASES = sorted(_cargar_sonda().escenarios())


# ------------------------------------------------------------- auxiliares
def _entradas_esperadas(clase):
    """Cuantas acciones de RECUPERACION declara el contrato para una clase.

    Se DERIVA del contrato declarado, no de una lista escrita a mano:
      - en el NIVEL `campo` y en el NIVEL `grupo` la unidad corrompida se
        rechaza y algo la OCUPA en su lugar: hay una recuperacion que
        registrar;
      - en el NIVEL `bloque` solo la hay si la POLITICA reconstruye el
        contenedor (`adapt_container`);
      - en los demas niveles (`seccion`, `fila`, `entrada`) la unidad
        corrompida se rechaza ENTERA y no se coloca nada en su lugar: no hay
        recuperacion que registrar, solo la supervivencia de los hermanos.
    """
    nivel = clase.get("level")
    politica = clase.get("policy")
    if nivel in ("campo", "grupo"):
        return 1
    if nivel == "bloque" and politica == "adapt_container":
        return 1
    return 0


def _campo_de_la_unidad(clase):
    """Nombre del campo corrupto declarado por el contrato (o None)."""
    unidad = clase.get("corrupt_unit", "")
    if "campo:" not in unidad:
        return None
    campo = unidad.rsplit(".", 1)[-1].split(":")[-1]
    return campo.rstrip("[]") or None


def _rule_id_de_la_entrada(entrada):
    """Identidad de la regla de la que procede una recuperacion de CAMPO."""
    unidad = str(entrada.get("unidad") or "")
    if not unidad.startswith("fila:"):
        return None
    return unidad.split(":", 1)[1]


def _valor_declarado(recuperable, entrada):
    """Valor por DEFECTO declarado por el contrato para el campo recuperado.

    `$rule_id` se resuelve con la identidad de la propia regla: es el unico
    valor por defecto que depende de la unidad recuperada.
    """
    campo = entrada.get("campo")
    declarado = (recuperable.get("field_defaults") or {}).get(campo) or {}
    valor = declarado.get("value")
    if valor == "$rule_id":
        return _rule_id_de_la_entrada(entrada)
    return valor


# =========================================================== LA API (7.2)
def test_la_api_de_recuperacion_devuelve_un_informe_bien_formado(observado):
    """`recovery_report()` expone un INFORME bien formado en las 27 clases."""
    for clase_id, obs in sorted(observado.items()):
        informe = obs["informe"]
        assert isinstance(informe, dict), f"`{clase_id}`: el informe no es un diccionario"
        assert isinstance(informe.get("recoveries"), list), (
            f"`{clase_id}`: `recoveries` no es una lista")
        assert isinstance(informe.get("count"), int), (
            f"`{clase_id}`: `count` no es un entero")
        assert isinstance(informe.get("files"), list), (
            f"`{clase_id}`: `files` no es una lista")
        assert informe["count"] == len(informe["recoveries"]), (
            f"`{clase_id}`: count={informe['count']} "
            f"recoveries={len(informe['recoveries'])}")
        assert set(informe["files"]) == {r.get("fichero") for r in informe["recoveries"]}, (
            f"`{clase_id}`: `files` no coincide con los ficheros de las recuperaciones")


def test_la_api_de_recuperacion_es_de_solo_lectura(sonda, tmp_path):
    """La API no crea ficheros, no altera el estado y devuelve una COPIA.

    Sin esto, un consumidor podria modificar el informe del motor desde fuera.
    """
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    motor = sonda.nuevo_motor(data_dir)
    antes = sorted(os.listdir(data_dir))

    primero = motor.recovery_report()
    segundo = motor.recovery_report()
    assert primero == segundo, "la API no es estable: dos llamadas difieren"

    # COPIA defensiva: mutar lo devuelto NO cambia el motor.
    primero["recoveries"].append({"fichero": "inventado", "unidad": "inventada"})
    primero["count"] = 999
    primero["files"].append("inventado")
    tercero = motor.recovery_report()
    assert tercero["count"] != 999, "la API no devuelve una COPIA: el `count` se ha filtrado"
    assert "inventado" not in tercero["files"], (
        "la API no devuelve una COPIA: se ha filtrado un fichero inventado")
    assert all(r.get("fichero") != "inventado" for r in tercero["recoveries"]), (
        "la API no devuelve una COPIA: se ha filtrado una recuperacion inventada")

    assert sorted(os.listdir(data_dir)) == antes, (
        "la API ha creado ficheros: " + str(sorted(set(os.listdir(data_dir)) - set(antes))))


def test_sin_corrupcion_no_hay_que_recuperar(motor_ref):
    """CONTROL de NO VACUO: sin corrupcion el informe esta VACIO.

    Sin este control, un informe siempre lleno no probaria nada.
    """
    informe = motor_ref.recovery_report()
    assert informe["count"] == 0, (
        f"sin corrupcion hay {informe['count']} recuperaciones: "
        + str(informe["recoveries"]))
    assert informe["recoveries"] == [], "sin corrupcion el informe no esta vacio"
    assert informe["files"] == [], "sin corrupcion el informe declara ficheros"


# ============================================== LA RECUPERACION (7.2)
@pytest.mark.parametrize("clase_id", CLASES)
def test_la_recuperacion_se_registra_en_la_unidad_que_corrompe(contrato, observado, clase_id):
    """La recuperacion se REGISTRA en la unidad que corrompe, con su POLITICA.

    El numero de acciones registradas lo DICE el contrato (derivado del NIVEL
    y de la POLITICA declarados): la hoja no puede decir una cosa y el motor
    hacer otra.
    """
    _, declaradas = contrato
    clase = declaradas[clase_id]
    entradas = observado[clase_id]["informe"]["recoveries"]
    esperadas = _entradas_esperadas(clase)
    assert len(entradas) == esperadas, (
        f"`{clase_id}`: recuperaciones registradas={len(entradas)} "
        f"declaradas={esperadas} (nivel={clase.get('level')}, "
        f"politica={clase.get('policy')}) -> {entradas}")
    for entrada in entradas:
        assert entrada.get("politica") == clase.get("policy"), (
            f"`{clase_id}`: la politica registrada {entrada.get('politica')!r} "
            f"no es la declarada {clase.get('policy')!r}")
        assert entrada.get("fichero"), f"`{clase_id}`: la recuperacion no declara fichero"
        assert entrada.get("unidad"), f"`{clase_id}`: la recuperacion no declara unidad"
        assert entrada.get("timestamp"), f"`{clase_id}`: la recuperacion no declara momento"
        campo = _campo_de_la_unidad(clase)
        if campo is not None:
            assert entrada.get("campo") == campo, (
                f"`{clase_id}`: el campo registrado {entrada.get('campo')!r} "
                f"no es el corrupto {campo!r}")


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_valor_por_defecto_registrado_es_el_declarado(contrato, observado, clase_id):
    """El valor por DEFECTO registrado es el que el contrato DECLARA.

    La recuperacion NO inventa datos: solo puede usar el valor por defecto del
    FORMATO REAL, que es lo unico que el contrato declara.
    """
    recuperable, declaradas = contrato
    clase = declaradas[clase_id]
    for entrada in observado[clase_id]["informe"]["recoveries"]:
        if entrada.get("politica") != "default_the_field":
            continue
        campo = entrada.get("campo")
        declarado = (recuperable.get("field_defaults") or {}).get(campo) or {}
        assert declarado, f"`{clase_id}`: `{campo}` no tiene valor por defecto declarado"
        assert entrada.get("valor") == _valor_declarado(recuperable, entrada), (
            f"`{clase_id}`: el valor por defecto de `{campo}` registrado es "
            f"{entrada.get('valor')!r} y el declarado es "
            f"{_valor_declarado(recuperable, entrada)!r}")


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_estado_guarda_el_valor_por_defecto(observado, clase_id):
    """El ESTADO guarda el valor por DEFECTO: la recuperacion no inventa.

    El campo corrupto no llega al estado: lo que llega es su valor por
    defecto, y el resto de la fila sobrevive intacto.
    """
    for entrada in observado[clase_id]["informe"]["recoveries"]:
        if entrada.get("politica") != "default_the_field":
            continue
        rule_id = _rule_id_de_la_entrada(entrada)
        assert rule_id, f"`{clase_id}`: la recuperacion no declara de que regla viene"
        regla = observado[clase_id]["reglas"].get(rule_id)
        assert regla is not None, (
            f"`{clase_id}`: la regla `{rule_id}` no ha sobrevivido a la recuperacion")
        assert regla.get(entrada["campo"]) == entrada.get("valor"), (
            f"`{clase_id}`: en el estado, `{entrada['campo']}` vale "
            f"{regla.get(entrada['campo'])!r} y el valor por defecto es "
            f"{entrada.get('valor')!r}")


@pytest.mark.parametrize("clase_id", CLASES)
def test_lo_recuperable_llega_al_estado(contrato, observado, tabla, clase_id):
    """Lo que el contrato declara RECUPERABLE LLEGA al estado.

    Es el CORAZON de la recuperacion parcial: la unidad INDEPENDIENTE de la
    unidad corrupta sobrevive, y la unidad corrupta se rechaza en su NIVEL.
    """
    _, declaradas = contrato
    clase = declaradas[clase_id]
    tokens = set(clase.get("recovers") or [])
    for unidad in tabla[clase_id]["unidades"]:
        if unidad["token"] not in tokens:
            continue
        assert observado[clase_id]["unidades"].get(unidad["etiqueta"]), (
            f"`{clase_id}`: no ha llegado al estado {unidad['etiqueta']!r}, "
            "que el contrato declara recuperable")


@pytest.mark.parametrize("clase_id", CLASES)
def test_el_informe_no_contiene_el_dato_corrupto(observado, clase_id):
    """El INFORME no arrastra el dato corrupto: informa, no lo usa."""
    marca = observado[clase_id]["marca"]
    for entrada in observado[clase_id]["informe"]["recoveries"]:
        assert marca not in json.dumps(entrada, default=str), (
            f"`{clase_id}`: el informe contiene el dato corrupto: {entrada}")
    assert not observado[clase_id]["corrupto"], (
        f"`{clase_id}`: el dato corrupto ha llegado al estado operativo")


# ================================================================ GUARDA
def _sha256(ruta):
    if not os.path.isfile(ruta):
        return None
    digest = hashlib.sha256()
    with open(ruta, "rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            digest.update(bloque)
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
