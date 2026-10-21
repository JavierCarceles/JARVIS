#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DETERMINACION DE LOS DATOS RECUPERABLES (2.8.8.9.7.1).

Script de sonda independiente de la suite pytest. NO modifica `data/` de
produccion.

QUE COMPRUEBA ESTA SONDA
Que dato RECUPERABLE se pierde hoy cuando una corrupcion es rechazada:
  - la declaracion `recoverable_data()` del motor cubre las 27 clases de
    corrupcion y es COHERENTE con el FORMATO REAL y con el contrato de
    corrupcion que ya existe (`corruption_criteria()`);
  - por cada clase, MIDIE en runtime que unidades independientes sobreviven al
    rechazo y cuales NO, distinguiendo el nivel al que se pierde el dato;
  - el dato corrupto NO llega al estado en ninguna clase (la determinacion no
    puede relajar el rechazo de 2.8.8.9.6.3);
  - la medicion NO es vacua: con datos sanos no declara perdida ninguna, y con
    una perdida REAL la declara.

INDEPENDENCIA DEL INSTRUMENTO
Esta sonda define sus PROPIOS escenarios y sus PROPIOS observadores: no
reutiliza el registro de escenarios ni los observadores de 2.8.8.9.6.1 ni de
2.8.8.9.6.4. El SENTINELA de cada clase se incrusta en el punto exacto que se
corrompe, y el contenido SANO que la corrupcion no destruye lleva una marca
PROPIA, de modo que la perdida se midió con un instrumento que no comparte
puntos ciegos con el que declara los contratos.

COMO SE MODELA LA RECUPERABILIDAD
Cada escenario declara la RUTA de la unidad corrupta (`corrupt_unit`) y las
unidades SANAS e INDEPENDIENTES que la acompanan. La independencia se
resuelve con la regla declarada: dos unidades son independientes si la ruta de
una no es un prefijo de la ruta de la otra. La sonda mide, para cada clase:
  - que el valor corrupto NO llega al estado;
  - que unidades independientes sobreviven;
  - que unidades del nivel INFERIOR (los campos validos de la fila corrupta)
    sobreviven.
El contraste contra lo DECLARADO en `recoverable_data()` produce la
DETERMINACION: las clases en las que el dato recuperable NO sobrevive son el
trabajo de 2.8.8.9.7.2.

Partes:
  A - FORMA DEL CONTRATO DE DATOS RECUPERABLES.
  B - MEDICION POR CLASE: que se pierde y que sobrevive.
  C - DETERMINACION: el inventario de dato recuperable perdido.
  D - NO VACUO: los controles que demuestran que la medicion discrimina.
  E - AISLAMIENTO: el `data/` de produccion queda byte a byte identico.

Uso:
    python tests/utils/contextual_adaptation_engine/identify_recoverable_real.py
"""

import hashlib
import json
import logging
import os
import re
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

PREFIJO = "SENTINELA_RECUPERABLE_2_8_8_9_7_1"
PREFIJO_SANO = "SANO_RECUPERABLE_2_8_8_9_7_1"

# Fila de regla SANA: la referencia valida que acompana a la fila corrupta.
REGLA = {
    "rule_id": "rr", "name": "regla sana", "description": "descripcion sana",
    "condition_pattern": "patron sano", "adaptation_actions": ["accion sana"],
    "context_triggers": ["production"], "confidence_threshold": 0.7,
    "priority": 1, "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4,
    "constraints": [], "metadata": {}, "deadline": None,
}
# Fila SANA de feedback, de resultados de aprendizaje y entrada de historial.
FILA_FB = {"adaptation_id": "fb_sano", "success": True, "timestamp": "2024-01-01T00:00:00",
            "adaptation_context": {"context_type": "production"}}
FILA_LR = {"adaptation_id": "lr_sano", "updated_strategies": {}, "convergence_metrics": {},
            "learned_patterns": []}
HISTORIAL = {"adaptation_id": "hb_sano", "success": True, "timestamp": "2024-01-01T00:00:00"}
# Estrategia aprendida SANA: aporta la EVIDENCIA que exige 2.8.8.9.2.1.
ESTRATEGIA = {"strategy_id": "st_sano", "confidence": 0.8, "success_rate": 0.5,
               "last_updated": "2024-01-01T00:00:00",
               "context": {"context_type": "production", "goal_type": "g"}}


def marca(clase_id):
    """SENTINELA unico de la corrupcion, incrustado en el punto que se corrompe."""
    return f"{PREFIJO}_{clase_id.replace('.', '_')}"


def marca_sana(clase_id):
    """Marca del contenido SANO que la corrupcion no destruye."""
    return f"{PREFIJO_SANO}_{clase_id.replace('.', '_')}"


# ---------------------------------------------------------------- escenarios
def _reglas(filas):
    total = len(filas) if isinstance(filas, list) else len(filas)
    return {RF: {"version": "2.0", "last_updated": "2024-01-01T00:00:00",
                 "total_rules": total, "rules": filas}}


def _base(data):
    return {KB: {"version": "2.0", "last_updated": "2024-01-01T00:00:00",
                 "context_snapshots": 0, "adaptation_history": 0,
                 "knowledge_transfers": 0, "data": data}}


def _feedback(**payload):
    base = {"goal_adaptation_feedback": [], "adaptation_history": [],
            "last_updated": "2024-01-01T00:00:00"}
    base.update(payload)
    return {FB: base}


def _aprendizaje(**payload):
    base = {"learning_results": [], "adaptation_strategies": {},
            "last_updated": "2024-01-01T00:00:00"}
    base.update(payload)
    return {LR: base}


# ------------------------------------------------------------- observadores
def _regla_en(motor, rule_id, esperado=None):
    """La regla existe y, si se exige, sus campos validos siguen intactos."""
    regla = (motor.adaptation_rules or {}).get(rule_id)
    if regla is None:
        return False
    if not esperado:
        return True
    datos = regla.to_dict() if hasattr(regla, "to_dict") else dict(regla)
    return all(datos.get(campo) == valor for campo, valor in esperado.items())


def unidad_regla(etiqueta, token, rule_id, esperado=None):
    def presente(motor):
        return _regla_en(motor, rule_id, esperado)
    return {"etiqueta": etiqueta, "token": token, "presente": presente}


def unidad_seccion(etiqueta, token, seccion, marcador):
    def presente(motor):
        valor = (motor.knowledge_base or {}).get(seccion)
        if valor is None:
            return False
        return marcador in json.dumps(valor, default=str, ensure_ascii=False)
    return {"etiqueta": etiqueta, "token": token, "presente": presente}


def unidad_grupo(etiqueta, token, seccion, grupo, marcador):
    def presente(motor):
        valor = (motor.knowledge_base or {}).get(seccion)
        if not isinstance(valor, dict):
            return False
        return marcador in json.dumps(valor.get(grupo), default=str, ensure_ascii=False)
    return {"etiqueta": etiqueta, "token": token, "presente": presente}


def unidad_lista(etiqueta, token, seccion, marcador):
    def presente(motor):
        valor = (motor.knowledge_base or {}).get(seccion)
        if valor is None:
            return False
        return marcador in json.dumps(valor, default=str, ensure_ascii=False)
    return {"etiqueta": etiqueta, "token": token, "presente": presente}


def unidad_historial(etiqueta, token, marcador):
    def presente(motor):
        return marcador in json.dumps([dict(entrada) for entrada in (motor.adaptation_history or [])],
                                      default=str, ensure_ascii=False)
    return {"etiqueta": etiqueta, "token": token, "presente": presente}


def _datos_sanos(clase_id, excluir=None):
    """Secciones SANAS de la base de conocimiento, con marca propia.

    `excluir` es la seccion (o el grupo) que la corrupcion ocupa: su contenido
    NO es una unidad independiente, asi que no se declara sana.
    """
    m = marca_sana(clase_id)
    secciones = {
        "context_patterns": {"production": [{"patron": m + "_CP"}],
                             "idle": [{"patron": m + "_CP_IDLE"}]},
        "success_patterns": {"production": [{"patron": m + "_SP"}]},
        "performance_baselines": {"production": {"baseline": m + "_PB"}},
        "adaptation_strategies": {"production": [{"strategy_id": m + "_AS"}]},
        "integration_records": [{"record": m + "_IR"}],
        "transfer_efficiency": {"production": m + "_TE"},
        "failure_patterns": [{"pattern": m + "_FP"}],
    }
    if excluir:
        secciones.pop(excluir, None)
    return secciones


def _unidades_de_base(clase_id, excluir=None):
    """Unidades SANAS independientes de la seccion corrupta de la base."""
    m = marca_sana(clase_id)
    candidatas = [
        ("success_patterns", m + "_SP"),
        ("performance_baselines", m + "_PB"),
        ("adaptation_strategies", m + "_AS"),
        ("integration_records", m + "_IR"),
        ("transfer_efficiency", m + "_TE"),
        ("failure_patterns", m + "_FP"),
    ]
    return [unidad_seccion(f"seccion `{clave}`", "siblings", clave, marca_sano)
            for clave, marca_sano in candidatas if clave != excluir]


# Clases de corrupcion de un CAMPO de una fila de regla: el campo y como se
# viola su tipo declarado en el FORMATO REAL.
CORRUPCIONES_DE_CAMPO = (
    ("adaptation_rules.priority_not_castable", "priority"),
    ("adaptation_rules.execution_count_not_castable", "execution_count"),
    ("adaptation_rules.metadata_not_mapping", "metadata"),
    ("adaptation_rules.actions_string", "adaptation_actions"),
    ("adaptation_rules.enabled_string", "enabled"),
    ("adaptation_rules.threshold_not_numeric", "confidence_threshold"),
    ("adaptation_rules.success_rate_not_numeric", "success_rate"),
    ("adaptation_rules.triggers_not_list", "context_triggers"),
    ("adaptation_rules.last_execution_not_iso", "last_execution"),
    ("adaptation_rules.name_not_string", "name"),
)


def escenarios():
    """Escenarios PROPIOS de 2.8.8.9.7.1, uno por clase de corrupcion.

    Cada entrada declara:
      - `files`:    el fichero corrupto tal y como se escribe en disco.
      - `marca`:    el SENTINELA incrustado en el punto que se corrompe.
      - `unidades`: las unidades SANAS independientes que la acompanan, con el
                    TOKEN que las declara recuperables.
    """
    tabla = {}

    def anota(clase_id, ficheros, unidades, sentinel=None):
        tabla[clase_id] = {"id": clase_id, "files": ficheros, "unidades": unidades,
                           "marca": sentinel if sentinel is not None else marca(clase_id)}

    # --- adaptation_rules -------------------------------------------------
    # El contenedor `rules` con otra FORMA: un mapeo. Los valores que sean
    # filas validas son recuperables (politica `adapt_container`).
    anota("adaptation_rules.rules_wrong_type",
          _reglas({"clave_1": dict(REGLA, rule_id="rr_sano_1"),
                   "clave_2": {"marca": marca("adaptation_rules.rules_wrong_type")}}),
          [unidad_regla("valor valido del mapeo `rules`", "container_values", "rr_sano_1")])

    # Una fila que no es un mapeo y una fila sin identidad: la unidad corrupta
    # no contiene dato recuperable, pero las filas hermanas si.
    anota("adaptation_rules.row_not_mapping",
          _reglas([dict(REGLA, rule_id="rr_sano_1"),
                   marca("adaptation_rules.row_not_mapping"),
                   dict(REGLA, rule_id="rr_sano_3")]),
          [unidad_regla("fila `rr_sano_1`", "siblings", "rr_sano_1"),
           unidad_regla("fila `rr_sano_3`", "siblings", "rr_sano_3")])
    anota("adaptation_rules.row_missing_identity",
          _reglas([dict(REGLA, rule_id="rr_sano_1"),
                   {"name": marca("adaptation_rules.row_missing_identity")},
                   dict(REGLA, rule_id="rr_sano_3")]),
          [unidad_regla("fila `rr_sano_1`", "siblings", "rr_sano_1"),
           unidad_regla("fila `rr_sano_3`", "siblings", "rr_sano_3")])

    # Una fila con un CAMPO corrupto: la fila entera es la unidad recuperable
    # (sus campos validos) y las filas hermanas tambien.
    for clase_id, campo in CORRUPCIONES_DE_CAMPO:
        valor = marca(clase_id)
        if campo == "name":
            valor = {"marca": valor}  # un mapeo no es una cadena
        esperado = {k: v for k, v in REGLA.items() if k not in ("rule_id", campo)}
        anota(clase_id,
              _reglas([dict(REGLA, rule_id="rr_sano_1"),
                       dict(REGLA, rule_id="rr_corrupto", **{campo: valor}),
                       dict(REGLA, rule_id="rr_sano_3")]),
              [unidad_regla("fila `rr_sano_1`", "siblings", "rr_sano_1"),
               unidad_regla("fila `rr_sano_3`", "siblings", "rr_sano_3"),
               unidad_regla("campos validos de la fila corrupta", "row_fields", "rr_corrupto", esperado)])

    # Un DISPARADOR invalido dentro de una lista valida: la clase mas fina.
    esperado_disparadores = {k: v for k, v in REGLA.items() if k not in ("rule_id", "context_triggers")}
    anota("adaptation_rules.trigger_invalid_value",
          _reglas([dict(REGLA, rule_id="rr_sano_1"),
                   dict(REGLA, rule_id="rr_corrupto",
                        context_triggers=["production", marca("adaptation_rules.trigger_invalid_value")]),
                   dict(REGLA, rule_id="rr_sano_3")]),
          [unidad_regla("fila `rr_sano_1`", "siblings", "rr_sano_1"),
           unidad_regla("fila `rr_sano_3`", "siblings", "rr_sano_3"),
           unidad_regla("campos validos de la fila corrupta", "row_fields", "rr_corrupto", esperado_disparadores),
           unidad_regla("disparadores validos de la fila", "elements", "rr_corrupto",
                        {"context_triggers": ["production"]})])

    # --- knowledge_base ---------------------------------------------------
    # El bloque `data` entero: su contenido es opaco para el motor.
    anota("knowledge_base.data_not_mapping",
          _base(marca("knowledge_base.data_not_mapping")), [])

    # Una SECCION que no es un mapeo: las demas secciones son independientes.
    for clase_id, seccion in (("knowledge_base.section_not_mapping", "context_patterns"),
                              ("knowledge_base.strategies_not_mapping", "adaptation_strategies")):
        datos = _datos_sanos(clase_id, excluir=seccion)
        datos[seccion] = marca(clase_id)
        anota(clase_id, _base(datos), _unidades_de_base(clase_id, excluir=seccion))

    # Una clave que el motor nunca escribe.
    clase_id = "knowledge_base.unexpected_key"
    datos = _datos_sanos(clase_id)
    datos[marca(clase_id)] = 1
    anota(clase_id, _base(datos), _unidades_de_base(clase_id))

    # Un GRUPO (contexto) corrupto dentro de una seccion: los grupos hermanos
    # de la MISMA seccion son independientes del grupo corrupto (pero la
    # seccion que los contiene NO lo es: su ruta es un prefijo de la del grupo).
    clase_id = "knowledge_base.section_partial"
    m = marca_sana(clase_id)
    datos = _datos_sanos(clase_id, excluir="context_patterns")
    datos["context_patterns"] = {"production": marca(clase_id),
                                 "idle": [{"patron": m + "_CP_IDLE"}]}
    anota(clase_id, _base(datos),
          _unidades_de_base(clase_id, excluir="context_patterns") +
          [unidad_grupo("grupo `idle` de `context_patterns`", "siblings",
                        "context_patterns", "idle", m + "_CP_IDLE")])

    # --- goal_adaptation_feedback -----------------------------------------
    clase_id = "goal_adaptation_feedback.section_not_list"
    anota(clase_id,
          _feedback(goal_adaptation_feedback={marca(clase_id): 1},
                    adaptation_history=[dict(HISTORIAL)]),
          [unidad_historial("entrada sana del historial", "siblings", "hb_sano")])

    clase_id = "goal_adaptation_feedback.row_not_mapping"
    anota(clase_id,
          _feedback(goal_adaptation_feedback=[dict(FILA_FB), marca(clase_id)],
                    adaptation_history=[dict(HISTORIAL)]),
          [unidad_lista("fila sana de feedback", "siblings", "goal_adaptation_feedback", "fb_sano"),
           unidad_historial("entrada sana del historial", "siblings", "hb_sano")])

    clase_id = "goal_adaptation_feedback.history_not_list"
    anota(clase_id,
          _feedback(goal_adaptation_feedback=[dict(FILA_FB)],
                    adaptation_history={marca(clase_id): 1}),
          [unidad_lista("fila sana de feedback", "siblings", "goal_adaptation_feedback", "fb_sano")])

    # --- goal_adaptation_learning_results ---------------------------------
    clase_id = "goal_adaptation_learning_results.learning_results_not_list"
    anota(clase_id,
          _aprendizaje(learning_results={marca(clase_id): 1},
                       adaptation_strategies={"st_sano": dict(ESTRATEGIA)}),
          [unidad_lista("entrada sana de estrategias", "siblings", "adaptation_strategies", "st_sano")])

    clase_id = "goal_adaptation_learning_results.row_not_mapping"
    anota(clase_id,
          _aprendizaje(learning_results=[dict(FILA_LR), marca(clase_id)],
                       adaptation_strategies={"st_sano": dict(ESTRATEGIA)}),
          [unidad_lista("fila sana de aprendizaje", "siblings", "learning_results", "lr_sano"),
           unidad_lista("entrada sana de estrategias", "siblings", "adaptation_strategies", "st_sano")])

    clase_id = "goal_adaptation_learning_results.strategies_not_mapping"
    anota(clase_id,
          _aprendizaje(learning_results=[dict(FILA_LR)],
                       adaptation_strategies=marca(clase_id)),
          [unidad_lista("fila sana de aprendizaje", "siblings", "learning_results", "lr_sano")])

    clase_id = "goal_adaptation_learning_results.strategy_value_not_mapping"
    anota(clase_id,
          _aprendizaje(learning_results=[dict(FILA_LR)],
                       adaptation_strategies={"st_sano": dict(ESTRATEGIA),
                                              "st_roto": marca(clase_id)}),
          [unidad_lista("fila sana de aprendizaje", "siblings", "learning_results", "lr_sano"),
           unidad_lista("entrada sana de estrategias", "siblings", "adaptation_strategies", "st_sano")])

    clase_id = "goal_adaptation_learning_results.strategy_missing_identity"
    anota(clase_id,
          _aprendizaje(learning_results=[dict(FILA_LR)],
                       adaptation_strategies={"st_sano": dict(ESTRATEGIA),
                                              "st_roto": {"strategy_id": "st_roto"}}),
          [unidad_lista("fila sana de aprendizaje", "siblings", "learning_results", "lr_sano"),
           unidad_lista("entrada sana de estrategias", "siblings", "adaptation_strategies", "st_sano")])

    return tabla


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


def firma_operativa(motor):
    """Firma del ESTADO OPERATIVO del motor: lo que el motor usa de verdad."""
    return json.dumps({
        "adaptation_rules": {rid: regla.to_dict() for rid, regla in (motor.adaptation_rules or {}).items()},
        "knowledge_base": motor.knowledge_base,
        "adaptation_history": [dict(entrada) for entrada in (motor.adaptation_history or [])],
    }, sort_keys=True, default=str)


def _solo_letras(texto):
    """PROYECCION del texto: solo letras, digitos y guion bajo.

    El SENTINELA corrupto se comprueba en el estado con dos formas: la literal
    y la PROYECTADA. La proyeccion es lo que permite ver una corrupcion que
    el cargador COERCIONO troceandola (por ejemplo `list("SENTINELA...")`
    deja los caracteres sueltos en el estado: la marca literal ya no aparece,
    pero su proyeccion si). Sin la proyeccion, esa clase de corrupcion pasaria
    inadvertida.
    """
    return re.sub(r"[^A-Za-z0-9_]", "", texto)


def medir(escenario):
    """Monta el escenario, carga el motor y devuelve lo OBSERVADO.

    Devuelve:
      - `corrupto_en_estado`: el SENTINELA corrupto aparecio en el estado.
      - `unidades`: lista de (etiqueta, token, presente).
    """
    tmp = tempfile.mkdtemp(prefix="jarvis_recuperable_")
    try:
        data_dir = os.path.join(tmp, "data")
        materializar(escenario["files"], data_dir)
        motor = nuevo_motor(data_dir)
        estado = firma_operativa(motor)
        corrupto = (escenario["marca"] in estado
                    or _solo_letras(escenario["marca"]) in _solo_letras(estado))
        unidades = []
        for unidad in escenario["unidades"]:
            try:
                presente = bool(unidad["presente"](motor))
            except Exception as exc:  # noqa: BLE001 - un observador que falla no observa
                presente = False
                print(f"      (observador de {unidad['etiqueta']} fallo: {type(exc).__name__}: {exc})")
            unidades.append({"etiqueta": unidad["etiqueta"], "token": unidad["token"],
                             "presente": presente})
        return {"corrupto_en_estado": corrupto, "unidades": unidades}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- Parte A
def parte_a_contrato(motor_ref):
    print("\n== PARTE A: FORMA DEL CONTRATO DE DATOS RECUPERABLES ==")
    recuperable = motor_ref.recoverable_data()
    corrupcion = motor_ref.corruption_criteria()

    declaradas = {clase_id: clase
                  for spec in recuperable["files"].values()
                  for clase_id, clase in spec["classes"].items()}
    contractual = {clase["id"]: clase
                   for spec in corrupcion["files"].values()
                   for clase in spec["corruptions"]}
    check("El contrato de datos recuperables cubre las 27 clases de corrupcion",
          set(declaradas) == set(contractual),
          f"declaradas={len(declaradas)} contractuales={len(contractual)}")

    niveles = set(recuperable["levels"])
    politicas = set(recuperable["policies"])
    tokens = set(recuperable["recoverable_tokens"])
    for clase_id, clase in sorted(declaradas.items()):
        check(f"`{clase_id}`: declara un NIVEL declarado en el vocabulario",
              clase.get("level") in niveles, str(clase.get("level")))
        check(f"`{clase_id}`: declara una POLITICA declarada en el vocabulario",
              clase.get("policy") in politicas, str(clase.get("policy")))
        check(f"`{clase_id}`: declara solo TOKENS de lo recuperable declarados",
              set(clase.get("recovers") or []) <= tokens, str(clase.get("recovers")))

    # La POLITICA y el NIVEL tienen que ser coherentes con la UNIDAD corrupta.
    for clase_id, clase in sorted(declaradas.items()):
        unit = clase.get("corrupt_unit", "")
        nivel = clase.get("level")
        # El nivel es el del ULTIMO segmento de la ruta: la unidad corrupta de
        # `fila:<rule_id>.campo:priority` es el CAMPO, no la fila.
        esperado = unit.rsplit(".", 1)[-1].split(":")[0]
        check(f"`{clase_id}`: el NIVEL declarado corresponde a la UNIDAD corrupta",
              esperado == nivel, f"unidad={unit} nivel={nivel}")

    # Los valores por defecto de RECUPERACION tienen que existir en el
    # FORMATO REAL y tener el tipo que ese formato declara.
    campos_formato = (corrupcion["files"]["adaptation_rules"]["real_format"]
                      .get("record", {}).get("fields", {}))
    for clase_id, clase in sorted(declaradas.items()):
        if clase.get("policy") != "default_the_field":
            continue
        campo = clase["corrupt_unit"].rsplit(".", 1)[-1].split(":")[-1]
        default = (recuperable["field_defaults"] or {}).get(campo)
        check(f"`{clase_id}`: el valor por defecto de `{campo}` esta declarado",
              default is not None, str(clase.get("field_default")))
        if default is None:
            continue
        check(f"`{clase_id}`: el valor por defecto de `{campo}` coincide con el declarado",
              clase.get("field_default") == default.get("value"),
              f"clase={clase.get('field_default')!r} contrato={default.get('value')!r}")
        tipo = campos_formato.get(campo)
        check(f"`{clase_id}`: el valor por defecto de `{campo}` respeta el TIPO del formato",
              _cumple_tipo(default.get("value"), tipo), f"tipo={tipo}")

    # Los valores por defecto CONSERVADORES tienen que ser MAS restrictivos
    # que los del cargador: recuperar con un valor mas permisivo activaria
    # datos que el motor no puede saber.
    check("El contrato declara los valores por defecto CONSERVADORES",
          set(recuperable.get("conservative_defaults") or []) == {"enabled"},
          str(recuperable.get("conservative_defaults")))
    check("El valor por defecto de recuperacion de `enabled` es CONSERVADOR (False)",
          (recuperable["field_defaults"]["enabled"]["value"]) is False,
          str(recuperable["field_defaults"]["enabled"]["value"]))

    # La REGLA DE INDEPENDENCIA tiene que ser la que la sonda aplica.
    check("El contrato declara la REGLA DE INDEPENDENCIA",
          "prefijo" in (recuperable.get("independence_rule") or ""),
          str(recuperable.get("independence_rule")))

    return recuperable, declaradas


def _cumple_tipo(valor, tipo):
    """El mismo criterio de tipo que usa el motor en su FORMATO REAL."""
    if tipo is None:
        return True
    if tipo == "string":
        return isinstance(valor, str)
    if tipo == "number":
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    if tipo == "list":
        return isinstance(valor, list)
    if tipo == "mapping":
        return isinstance(valor, dict)
    if tipo == "boolean":
        return isinstance(valor, bool)
    if tipo == "string|null":
        return valor is None or isinstance(valor, str)
    return True


# ---------------------------------------------------------------- Parte B
def parte_b_medicion(tabla, declaradas):
    print("\n== PARTE B: MEDICION POR CLASE ==")
    medicion = {}
    for clase_id in sorted(tabla):
        escenario = tabla[clase_id]
        observado = medir(escenario)
        medicion[clase_id] = observado

        check(f"`{clase_id}`: el dato corrupto NO llega al ESTADO",
              not observado["corrupto_en_estado"])

        esperado = (declaradas.get(clase_id, {}) or {}).get("recovers") or []
        for token in esperado:
            portadas = [u for u in observado["unidades"] if u["token"] == token]
            for unidad in portadas:
                if not unidad["presente"]:
                    hallazgo(f"`{clase_id}`: se pierde {unidad['etiqueta']} (token `{token}`)",
                             "dato recuperable declarado y NO observado en el estado")
    return medicion


# ---------------------------------------------------------------- Parte C
def parte_c_determinacion(tabla, declaradas, medicion):
    print("\n== PARTE C: DETERMINACION DEL DATO RECUPERABLE ==")
    resumen = []
    for clase_id in sorted(tabla):
        clase = declaradas.get(clase_id, {}) or {}
        observado = medicion[clase_id]
        esperado = clase.get("recovers") or []
        perdidos = [u["etiqueta"] for u in observado["unidades"]
                    if u["token"] in esperado and not u["presente"]]
        if not hay_esperables(esperado, observado):
            estado = "SIN RECUPERABLE"
        elif perdidos:
            estado = "PERDIDO"
        else:
            estado = "RECUPERADO"
        resumen.append((clase_id, clase.get("level"), clase.get("policy"),
                        ",".join(esperado) or "-", estado, "; ".join(perdidos) or "-"))
    print(f"  {'clase':<58} {'nivel':<8} {'politica':<20} {'recuperable':<28} estado")
    for clase_id, nivel, politica, esperado, estado, perdidos in resumen:
        print(f"  {clase_id:<58} {nivel:<8} {politica:<20} {esperado:<28} {estado}")
        if perdidos:
            print(f"      perdido: {perdidos}")
    con_perdida = [r for r in resumen if r[4] == "PERDIDO"]
    print(f"\n  Clases con dato recuperable PERDIDO: {len(con_perdida)} de {len(resumen)}")
    return resumen


def hay_esperables(tokens, observado):
    """Hay alguna unidad declarada como recuperable en el escenario."""
    return any(u["token"] in tokens for u in observado["unidades"])


def perdidas_de(clase, observado):
    """Unidades declaradas RECUPERABLES que NO sobreviven a la carga.

    Devuelve la lista de unidades perdidas (las que la declaracion exige
    conservar y el runtime no conserva). Una clase sin perdidas tiene la
    lista vacia: su dato recuperable sobrevive entero.
    """
    esperados = set(clase.get("recovers") or [])
    return [u for u in observado["unidades"] if u["token"] in esperados and not u["presente"]]


def clases_pendientes(recuperable):
    """Clases que la DECLARACION reconoce como PENDIENTES de recuperar.

    El `pending` de la conciliacion es la lista de clases en las que el
    runtime todavia NO satisface el contrato declarado. Es el trabajo de
    2.8.8.9.7.2.
    """
    pendientes = set()
    for entrada in recuperable.get("reconciliation") or []:
        pendientes.update(entrada.get("pending") or [])
    return pendientes


# ---------------------------------------------------------------- Parte D
def parte_d_no_vacio():
    print("\n== PARTE D: NO VACUO (la medicion discrimina) ==")

    # D1: con datos SANOS, la medicion no declara ninguna perdida.
    clase_id = "adaptation_rules.row_not_mapping"
    sana = _reglas([dict(REGLA, rule_id="rr_sano_1"), dict(REGLA, rule_id="rr_sano_3")])
    observado = medir({"id": "control", "files": sana, "marca": "MARCA_INEXISTENTE",
                       "unidades": [unidad_regla("fila `rr_sano_1`", "siblings", "rr_sano_1"),
                                    unidad_regla("fila `rr_sano_3`", "siblings", "rr_sano_3")]})
    check("CONTROL `datos sanos`: NO se declara ninguna perdida",
          all(u["presente"] for u in observado["unidades"]),
          str([u["etiqueta"] for u in observado["unidades"] if not u["presente"]]))
    check("CONTROL `datos sanos`: el sentinela inexistente no aparece en el estado",
          not observado["corrupto_en_estado"])

    # D2: con una perdida REAL, la medicion la declara. Se ensancha la
    # corrupcion hasta que el contenedor entero se pierde.
    clave = "adaptation_rules.rules_wrong_type"
    marca_control = marca(clave)
    ancho = _reglas({"clave_1": dict(REGLA, rule_id="rr_sano_1"),
                     "clave_2": {"marca": marca_control}})
    observado = medir({"id": "control", "files": ancho, "marca": marca_control,
                       "unidades": [unidad_regla("valor valido del mapeo `rules`", "container_values", "rr_sano_1")]})
    check("CONTROL `perdida real`: la medicion DECLARA la unidad perdida",
          not observado["unidades"][0]["presente"],
          "el instrumento no ve la perdida: la medicion no discrimina")

    # D3: el instrumento distingue "la fila existe" de "la fila no existe", de
    # modo que la perdida a NIVEL DE CAMPO se puede ver.
    intacta = _reglas([dict(REGLA, rule_id="rr_corrupto")])
    observado = medir({"id": "control", "files": intacta, "marca": "MARCA_INEXISTENTE",
                       "unidades": [unidad_regla("fila intacta", "row_fields", "rr_corrupto",
                                                 {k: v for k, v in REGLA.items() if k != "rule_id"})]})
    check("CONTROL `fila intacta`: la fila y sus campos validos se observan",
          all(u["presente"] for u in observado["unidades"]),
          "el instrumento no ve una fila valida: no puede medir su perdida")


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
    _workdir = tempfile.mkdtemp(prefix="jarvis_recuperable_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE DETERMINACION DE DATOS RECUPERABLES (2.8.8.9.7.1)")
    _ref_dir = os.path.join(tempfile.mkdtemp(prefix="jarvis_recuperable_ref_"), "data")
    motor_ref = nuevo_motor(_ref_dir)
    recuperable, declaradas = parte_a_contrato(motor_ref)
    tabla = escenarios()
    medicion = parte_b_medicion(tabla, declaradas)
    parte_c_determinacion(tabla, declaradas, medicion)
    parte_d_no_vacio()
    parte_e_no_contaminacion(hashes_iniciales)

    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos (dato recuperable perdido): {len(FINDINGS)}")
    for n in FINDINGS:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
