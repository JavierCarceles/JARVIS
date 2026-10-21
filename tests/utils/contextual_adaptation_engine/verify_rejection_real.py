#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFICACION DEL RECHAZO de la corrupcion (2.8.8.9.6.4).

Script de sonda independiente de la suite pytest. NO modifica `data/` de produccion.

QUE COMPRUEBA ESTA SONDA
Que el dato corrupto NO se usa como si fuera valido:
  - no llega al ESTADO OPERATIVO del motor (reglas, base de conocimiento,
    historial, instantaneas y estrategias ofrecidas);
  - no se PERSISTE en disco al escribir;
  - no ROMPE ninguna API de lectura ni de escritura;
  - se DETECTA y se REPORTA (la corrupcion no se ignora en silencio: el motor
    tiene que poder nombrar la desviacion que ha rechazado);
  - y el rechazo es SELECTIVO: se conserva el contenido sano que la corrupcion
    no destruye, y lo que la corrupcion destruye conserva el valor por defecto.

INDEPENDENCIA DEL INSTRUMENTO
Esta sonda NO reutiliza el registro de escenarios ni los observadores de
2.8.8.9.6.1: define sus PROPIOS escenarios (con un SENTINELA propio incrustado
en el punto exacto que se corrompe) y sus PROPIOS instrumentos de observacion
(escaneo del estado, escaneo del disco y ejercicio de las APIs). El rechazo se
comprueba con un instrumento que no comparte puntos ciegos con el que lo
declara, de modo que un fallo de rechazo no pueda esconderse tras un fallo del
observador.

COMO SE MODELA EL ALCANCE DE LA CORRUPCION
Cada escenario declara el `alcance` de lo que la corrupcion destruye y donde
vive el contenido sano que lo acompana:
  - `fila`:      la corrupcion afecta a UNA fila; el resto del fichero se carga.
  - `contenedor`: la corrupcion afecta al CONTENEDOR que la aloja (la seccion
                 `rules`, el bloque `data`, la seccion de feedback...); el resto
                 del fichero se carga.
  - `fichero`:   la corrupcion ABORTA la carga del fichero entero.
De `alcance` y de la posicion del contenido sano se DERIVA si ese contenido sano
debe sobrevivir, y el modelo propio se CONTRASTA con el efecto declarado por el
motor en `corruption_criteria()`: un rechazo que seLimitara a no propagar la
corrupcion, pero perdiera datos sanos, tambien es un rechazo incorrecto.

Partes:
  A - FORMA DEL CONTRATO DE RECHAZO: cobertura de clases y coherencia del modelo.
  B - RECHAZO POR CLASE: el dato corrupto no llega al estado ni al disco.
  C - SELECTIVIDAD: el rechazo es el correcto y no se pierde contenido sano.
  D - NO VACUO: los controles con el sentinela como dato VALIDO.
  E - AISLAMIENTO: el `data/` de produccion queda byte a byte identico.

Uso:
    python tests/utils/contextual_adaptation_engine/verify_rejection_real.py
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PRODUCTION_DATA_DIR = os.path.join(ROOT, "data")
STORAGE_FILES = ("goal_adaptation_feedback.json", "goal_adaptation_learning_results.json",
                 "contextual_adaptation_rules.json", "contextual_knowledge_base.json")

FAILURES = []
NOTES = []

# ---------------------------------------------------------------- constantes
RF = "contextual_adaptation_rules.json"
KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"

PREFIJO = "SENTINELA_RECHAZO_2_8_8_9_6_4"

# Regla SANA: la regla valida de referencia que acompaña a la fila corrupta.
REGLA_SANA = {
    "rule_id": "ok1", "name": "regla sana", "description": "d", "condition_pattern": "c",
    "adaptation_actions": ["a"], "context_triggers": ["production"], "confidence_threshold": 0.7,
    "priority": 1, "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4, "constraints": [],
    "metadata": {}, "deadline": None,
}
# Fila SANA de feedback y de resultados de aprendizaje.
FILA_FB_SANA = {"adaptation_id": "fb_ok", "success": True, "timestamp": "2024-01-01T00:00:00"}
FILA_LR_SANA = {"adaptation_id": "lr_ok", "updated_strategies": {}, "convergence_metrics": {},
                "learned_patterns": []}
# Entrada SANA del historial.
HISTORIAL_SANO = {"adaptation_id": "hb_ok", "success": True, "timestamp": "2024-01-01T00:00:00"}
# Estrategia aprendida SANA (aporta la evidencia que exige 2.8.8.9.2.1).
ESTRATEGIA_SANA = {"strategy_id": "st_ok", "confidence": 0.8, "success_rate": 0.5,
                   "last_updated": "2024-01-01T00:00:00",
                   "context": {"context_type": "production", "goal_type": "g"}}


def sentinela(clase_id):
    """Marca unica incrustada en el punto que se corrompe."""
    return f"{PREFIJO}_{clase_id.replace('.', '_')}"


def marca_sana(clase_id):
    """Marca del contenido SANO que acompaña a la corrupcion."""
    return f"SANO_{clase_id.replace('.', '_')}"


# ---------------------------------------------------------------- escenarios
def _reglas(filas):
    return {RF: {"version": "2.0", "last_updated": "2024-01-01T00:00:00",
                 "total_rules": len(filas), "rules": filas}}


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


def escenarios():
    """Escenarios PROPIOS de 2.8.8.9.6.4, con el sentinela en el punto corrupto.

    Cada entrada declara:
      - `alcance`:  la UNIDAD que la corrupcion destruye ("bloque", "seccion",
        "grupo", "fila", "entrada" o "campo").
      - `politica`: COMO se rechaza esa unidad ("adapt_container",
        "preserve_siblings", "default_the_field", "keep_valid_elements" o
        "none").
      - `hermano`:  el contenido SANO que acompana a la corrupcion y donde vive.
      - `unidad`:   que unidad se descarta y con que valor debe quedar.
      - `files`:    el fichero corrupto tal y como se escribe en disco.

    El SENTINELA se incrusta en el PUNTO EXACTO que se corrompe: en el CAMPO
    cuando la corrupcion es de campo, en la CLAVE o en el ELEMENTO cuando la
    corrupcion es de seccion, grupo o entrada. Asi el sentinela no puede
    llegar al estado por una via INOCUA (por ejemplo, como identidad de la
    fila, que es un dato VALIDO del formato).
    """
    tabla = {}

    def anota(clase_id, alcance, politica, hermano, unidad, ficheros):
        tabla[clase_id] = {"id": clase_id, "alcance": alcance, "politica": politica,
                           "hermano": hermano, "unidad": unidad, "files": ficheros}

    # --- adaptation_rules: el contenedor es la lista `rules` ---------------
    anota("adaptation_rules.rules_wrong_type", "bloque", "adapt_container", None, None,
          _reglas({sentinela("adaptation_rules.rules_wrong_type"): 1,
                   "ok2": dict(REGLA_SANA, rule_id="ok2")}))
    anota("adaptation_rules.row_not_mapping", "fila", "preserve_siblings",
          ("regla", "ok1", "mismo"), None,
          _reglas([dict(REGLA_SANA), sentinela("adaptation_rules.row_not_mapping")]))
    anota("adaptation_rules.row_missing_identity", "fila", "preserve_siblings",
          ("regla", "ok1", "mismo"), None,
          _reglas([dict(REGLA_SANA), {"name": sentinela("adaptation_rules.row_missing_identity")}]))
    # CAMPOS: el SENTINELA va EN EL CAMPO que se corrompe y la identidad de la
    # fila es SANA, para que el sentinela no pueda llegar al estado por una via
    # inocente. El valor por DEFECTO es el que declara el FORMATO REAL.
    for clase_id, campo, forma, defecto in (
            ("adaptation_rules.priority_not_castable", "priority", "texto", 1),
            ("adaptation_rules.execution_count_not_castable", "execution_count", "texto", 0),
            ("adaptation_rules.metadata_not_mapping", "metadata", "texto", {}),
            ("adaptation_rules.actions_string", "adaptation_actions", "texto", []),
            ("adaptation_rules.enabled_string", "enabled", "texto", False),
            ("adaptation_rules.threshold_not_numeric", "confidence_threshold", "texto", 0.7),
            ("adaptation_rules.success_rate_not_numeric", "success_rate", "texto", 0.0),
            ("adaptation_rules.triggers_not_list", "context_triggers", "texto", []),
            ("adaptation_rules.last_execution_not_iso", "last_execution", "texto", None),
            ("adaptation_rules.name_not_string", "name", "mapeo", "bad1")):
        fila = dict(REGLA_SANA, rule_id="bad1")
        fila[campo] = (sentinela(clase_id) if forma == "texto"
                       else {sentinela(clase_id): 1})
        anota(clase_id, "campo", "default_the_field", ("regla", "ok1", "mismo"),
              ("campo", "bad1", campo, defecto), _reglas([dict(REGLA_SANA), fila]))
    # El disparador invalido: se conserva el VALIDO y se descarta el invalido.
    anota("adaptation_rules.trigger_invalid_value", "campo", "keep_valid_elements",
          ("regla", "ok1", "mismo"), ("campo", "bad1", "context_triggers", ["production"]),
          _reglas([dict(REGLA_SANA),
                   dict(REGLA_SANA, rule_id="bad1",
                        context_triggers=["production",
                                          sentinela("adaptation_rules.trigger_invalid_value")])]))

    # --- knowledge_base: el contenedor es el bloque `data` ------------------
    anota("knowledge_base.data_not_mapping", "bloque", "none", None, ("base",),
          _base([sentinela("knowledge_base.data_not_mapping")]))
    anota("knowledge_base.section_not_mapping", "seccion", "preserve_siblings",
          ("seccion", "success_patterns", "otro", marca_sana("knowledge_base.section_not_mapping")),
          ("seccion", "context_patterns"),
          _base({"context_patterns": sentinela("knowledge_base.section_not_mapping"),
                 "success_patterns": {"production": [{"patron": marca_sana("knowledge_base.section_not_mapping")}]}}))
    anota("knowledge_base.strategies_not_mapping", "seccion", "preserve_siblings",
          ("seccion", "success_patterns", "otro", marca_sana("knowledge_base.strategies_not_mapping")),
          ("seccion", "adaptation_strategies"),
          _base({"adaptation_strategies": sentinela("knowledge_base.strategies_not_mapping"),
                 "success_patterns": {"production": [{"patron": marca_sana("knowledge_base.strategies_not_mapping")}]}}))
    anota("knowledge_base.unexpected_key", "seccion", "preserve_siblings",
          ("seccion", "success_patterns", "otro", marca_sana("knowledge_base.unexpected_key")),
          ("clave", None, sentinela("knowledge_base.unexpected_key")),
          _base({sentinela("knowledge_base.unexpected_key"): 1,
                 "success_patterns": {"production": [{"patron": marca_sana("knowledge_base.unexpected_key")}]}}))
    anota("knowledge_base.section_partial", "grupo", "preserve_siblings",
          ("seccion", "context_patterns", "otro", marca_sana("knowledge_base.section_partial")),
          ("grupo", "context_patterns", "production"),
          _base({"context_patterns": {
                     "production": sentinela("knowledge_base.section_partial"),
                     "idle": [{"patron": marca_sana("knowledge_base.section_partial")}]},
                 "success_patterns": {"production": [{"patron": marca_sana("knowledge_base.section_partial")}]}}))

    # --- goal_adaptation_feedback: secciones `goal_adaptation_feedback` y
    #     `adaptation_history` ----------------------------------------------
    anota("goal_adaptation_feedback.section_not_list", "seccion", "preserve_siblings",
          ("historial", "hb_ok", "otro"), ("seccion", "goal_adaptation_feedback"),
          _feedback(goal_adaptation_feedback={sentinela("goal_adaptation_feedback.section_not_list"): 1},
                    adaptation_history=[dict(HISTORIAL_SANO)]))
    anota("goal_adaptation_feedback.row_not_mapping", "fila", "preserve_siblings",
          ("fila_feedback", "fb_ok", "mismo"), None,
          _feedback(goal_adaptation_feedback=[dict(FILA_FB_SANA),
                                              sentinela("goal_adaptation_feedback.row_not_mapping")]))
    anota("goal_adaptation_feedback.history_not_list", "seccion", "preserve_siblings",
          ("fila_feedback", "fb_ok", "otro"), ("historial",),
          _feedback(goal_adaptation_feedback=[dict(FILA_FB_SANA)],
                    adaptation_history={sentinela("goal_adaptation_feedback.history_not_list"): 1}))

    # --- goal_adaptation_learning_results: secciones `learning_results` y
    #     `adaptation_strategies` ------------------------------------------
    anota("goal_adaptation_learning_results.learning_results_not_list", "seccion", "preserve_siblings",
          ("estrategia", "st_ok", "otro"), ("seccion", "learning_results"),
          _aprendizaje(learning_results={sentinela("goal_adaptation_learning_results.learning_results_not_list"): 1},
                       adaptation_strategies={"st_ok": dict(ESTRATEGIA_SANA)}))
    anota("goal_adaptation_learning_results.row_not_mapping", "fila", "preserve_siblings",
          ("fila_lr", "lr_ok", "mismo"), None,
          _aprendizaje(learning_results=[dict(FILA_LR_SANA),
                                         sentinela("goal_adaptation_learning_results.row_not_mapping")]))
    anota("goal_adaptation_learning_results.strategies_not_mapping", "seccion", "preserve_siblings",
          ("fila_lr", "lr_ok", "otro"), ("seccion", "adaptation_strategies"),
          _aprendizaje(learning_results=[dict(FILA_LR_SANA)],
                       adaptation_strategies=sentinela("goal_adaptation_learning_results.strategies_not_mapping")))
    anota("goal_adaptation_learning_results.strategy_value_not_mapping", "entrada", "preserve_siblings",
          ("fila_lr", "lr_ok", "otro"),
          ("clave", "adaptation_strategies", sentinela("goal_adaptation_learning_results.strategy_value_not_mapping")),
          _aprendizaje(learning_results=[dict(FILA_LR_SANA)],
                       adaptation_strategies={sentinela("goal_adaptation_learning_results.strategy_value_not_mapping"): "basura"}))
    anota("goal_adaptation_learning_results.strategy_missing_identity", "entrada", "preserve_siblings",
          ("fila_lr", "lr_ok", "otro"),
          ("clave", "adaptation_strategies", sentinela("goal_adaptation_learning_results.strategy_missing_identity")),
          _aprendizaje(learning_results=[dict(FILA_LR_SANA)],
                       adaptation_strategies={sentinela("goal_adaptation_learning_results.strategy_missing_identity"): {"strategy_id": sentinela("goal_adaptation_learning_results.strategy_missing_identity")}}))
    return tabla


# ---------------------------------------------------------------- utilidades
def check(label, condition, detail=""):
    status = "OK  " if condition else "FALLO"
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f" :: {detail}" if detail else ""))


def note(text):
    NOTES.append(text)
    print(f"  [NOTA] {text}")


def sha256(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
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


# ------------------------------------------------- instrumentos de observacion
def firma_reglas(motor):
    return json.dumps({rid: regla.to_dict() for rid, regla in (motor.adaptation_rules or {}).items()},
                      sort_keys=True, default=str)


def firma_base(motor):
    return json.dumps(motor.knowledge_base, sort_keys=True, default=str)


def firma_historial(motor):
    return json.dumps([dict(entrada) for entrada in (motor.adaptation_history or [])],
                      sort_keys=True, default=str)


def _firma_coleccion(coleccion):
    """Firma de una coleccion indexada por clave (dict) o por posicion (list)."""
    if isinstance(coleccion, dict):
        return {str(clave): getattr(valor, "to_dict", lambda: valor)()
                for clave, valor in coleccion.items()}
    return [getattr(valor, "to_dict", lambda: valor)() for valor in (coleccion or [])]


def firma_operativa(motor):
    """Firma del ESTADO OPERATIVO del motor: lo que el motor usa de verdad."""
    return json.dumps({
        "adaptation_rules": {rid: regla.to_dict() for rid, regla in (motor.adaptation_rules or {}).items()},
        "knowledge_base": motor.knowledge_base,
        "adaptation_history": [dict(entrada) for entrada in (motor.adaptation_history or [])],
        "context_snapshots": _firma_coleccion(motor.context_snapshots),
        "knowledge_transfers": _firma_coleccion(motor.knowledge_transfers),
    }, sort_keys=True, default=str)


def hermano_presente(motor, hermano):
    """El contenido SANO que acompana a la corrupcion sigue en el estado?"""
    if hermano is None:
        return None
    tipo = hermano[0]
    if tipo == "regla":
        return hermano[1] in (motor.adaptation_rules or {})
    if tipo == "seccion":
        valores = (motor.knowledge_base.get(hermano[1]) or {})
        marca = hermano[3]
        for lista in valores.values():
            if not isinstance(lista, list):
                continue
            for entrada in lista:
                if isinstance(entrada, dict) and entrada.get("patron") == marca:
                    return True
        return False
    if tipo == "marca":
        return hermano[1] in json.dumps(motor.knowledge_base, default=str)
    if tipo == "fila_feedback":
        return any(isinstance(fila, dict) and fila.get("adaptation_id") == hermano[1]
                   for fila in (motor.knowledge_base.get("goal_adaptation_feedback") or []))
    if tipo == "fila_lr":
        return any(isinstance(fila, dict) and fila.get("adaptation_id") == hermano[1]
                   for fila in (motor.knowledge_base.get("learning_results") or []))
    if tipo == "historial":
        return any(isinstance(entrada, dict) and entrada.get("adaptation_id") == hermano[1]
                   for entrada in (motor.adaptation_history or []))
    if tipo == "estrategia":
        for lista in (motor.knowledge_base.get("adaptation_strategies") or {}).values():
            for entrada in lista or []:
                if isinstance(entrada, dict) and entrada.get("strategy_id") == hermano[1]:
                    return True
        return False
    return None


def unidad_intacta(motor, motor_ref, unidad):
    """La unidad descartada por la corrupcion conserva el valor por defecto."""
    if unidad is None:
        return True
    tipo = unidad[0]
    if tipo == "reglas":
        return firma_reglas(motor) == firma_reglas(motor_ref)
    if tipo == "base":
        return firma_base(motor) == firma_base(motor_ref)
    if tipo == "historial":
        return firma_historial(motor) == firma_historial(motor_ref)
    if tipo == "campo":
        # La corrupcion se rechaza en el CAMPO: el campo toma su valor por
        # DEFECTO y la fila sobrevive con el resto de sus campos intactos.
        rule_id, campo, esperado = unidad[1], unidad[2], unidad[3]
        regla = (motor.adaptation_rules or {}).get(rule_id)
        if regla is None:
            return False
        datos = regla.to_dict() if hasattr(regla, "to_dict") else dict(regla)
        if datos.get(campo) != esperado:
            return False
        # La IDENTIDAD de la fila es la de la regla sana salvo en `rule_id`:
        # se compara el resto de los campos con los de la regla de referencia.
        return all(datos.get(otro) == REGLA_SANA[otro]
                   for otro in ("description", "condition_pattern",
                                "adaptation_score", "constraints", "deadline"))
    if tipo == "grupo":
        # La corrupcion se rechaza en el GRUPO: el grupo toma su valor por
        # DEFECTO (la lista vacia) y sus grupos HERMANOS sobreviven.
        seccion, grupo = unidad[1], unidad[2]
        valores = motor.knowledge_base.get(seccion) or {}
        return valores.get(grupo) == []
    if tipo == "seccion":
        return (motor.knowledge_base.get(unidad[1])
                == motor_ref.knowledge_base.get(unidad[1]))
    if tipo == "clave":
        seccion, clave = unidad[1], unidad[2]
        if seccion is None:
            return clave not in (motor.knowledge_base or {})
        valores = (motor.knowledge_base.get(seccion) or {})
        for lista in valores.values():
            if not isinstance(lista, list):
                continue
            for entrada in lista:
                if isinstance(entrada, dict) and entrada.get("strategy_id") == clave:
                    return False
        return True
    return True


def hermano_debe_sobrevivir(alcance, hermano):
    """DERIVA, desde el modelo propio de 6.4, si el contenido sano sobrevive."""
    if hermano is None:
        return None
    if alcance in ("campo", "grupo", "fila"):
        return True
    if alcance in ("bloque", "seccion", "entrada"):
        return hermano[2] == "otro"
    return False


def efecto_del_alcance(alcance, politica=None):
    """El efecto declarado que le corresponde a un ALCANCE y una POLITICA.

    El efecto depende de la UNIDAD que se rechaza, no solo de la politica: un
    CAMPO o un GRUPO se recuperan (la unidad corrupta toma su valor por
    defecto y el resto sobrevive), una FILA se descarta y una SECCION o una
    ENTRADA se ignoran con su seccion.
    """
    if alcance == "campo":
        return "value_recovered"
    if alcance == "grupo":
        return "value_recovered"
    if alcance == "fila":
        return "record_dropped"
    if alcance in ("seccion", "entrada"):
        return "silently_ignored"
    if alcance == "bloque":
        return "value_recovered" if politica == "adapt_container" else "silently_ignored"
    if alcance == "fichero":
        return "rejected_whole_file"
    raise KeyError(alcance)


def ficheros_del_disco(data_dir):
    contenido = {}
    for raiz, _dirs, files in os.walk(data_dir):
        for nombre in files:
            ruta = os.path.join(raiz, nombre)
            try:
                with open(ruta, encoding="utf-8") as handle:
                    contenido[os.path.relpath(ruta, data_dir)] = handle.read()
            except Exception:  # noqa: BLE001 - un fichero ilegible no se puede escanear
                contenido[os.path.relpath(ruta, data_dir)] = ""
    return contenido


def leer_fichero(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _sin_ubicaciones(valor):
    """Copia del valor de una API sin las `location` del informe de corrupcion.

    El informe NOMBRA la desviacion encontrada y para eso puede incluir el
    identificador de la clave o de la fila corrupta. Eso es informar, no usar:
    para comprobar que la API no USA el dato corrupto se ignoran esas
    `location` y se busca el sentinela en el resto del informe.
    """
    if isinstance(valor, dict):
        return {clave: _sin_ubicaciones(contenido)
                for clave, contenido in valor.items() if clave != "location"}
    if isinstance(valor, (list, tuple)):
        return [_sin_ubicaciones(elemento) for elemento in valor]
    return valor


# ---------------------------------------------------------------- Parte A
def parte_a_contrato(motor_ref):
    print("\n== PARTE A: FORMA DEL CONTRATO DE RECHAZO ==")
    contrato = motor_ref.corruption_criteria()
    declaradas = {clase["id"]: clase for spec in contrato["files"].values()
                  for clase in spec["corruptions"]}
    tabla = escenarios()
    check("Los escenarios de 6.4 cubren EXACTAMENTE las clases declaradas",
          sorted(tabla) == sorted(declaradas),
          f"propias={len(tabla)} declaradas={len(declaradas)}")

    # El modelo propio (alcance + politica) tiene que ser COHERENTE con el
    # efecto que el motor declara para cada clase: un alcance de "campo" o de
    # "grupo" exige `value_recovered`, uno de "fila" exige `record_dropped`,
    # uno de "seccion" o de "entrada" exige `silently_ignored` y uno de
    # "fichero" exige `rejected_whole_file`.
    incoherentes = []
    for clase_id, escenario in sorted(tabla.items()):
        esperado = efecto_del_alcance(escenario["alcance"], escenario["politica"])
        declarados = set(declaradas.get(clase_id, {}).get("expected", []))
        if declarados != {esperado}:
            incoherentes.append(f"{clase_id}: alcance={escenario['alcance']} "
                                 f"politica={escenario['politica']} "
                                 f"esperado={esperado} declarados={sorted(declarados)}")
    check("El ALCANCE del modelo propio concuerda con el efecto declarado",
          not incoherentes, "; ".join(incoherentes))

    # El vocabulario de efectos es el cerrado de 2.8.8.9.6.1 y esta hoja solo
    # admite los efectos que NO usan el dato corrupto.
    vocabulario = set(contrato["effect_vocabulary"])
    seguros = {"silently_ignored", "record_dropped", "rejected_whole_file",
               "value_recovered"}
    check("El vocabulario de efectos incluye los cuatro efectos de rechazo",
          seguros <= vocabulario, f"vocabulario={sorted(vocabulario)}")
    # Ningun efecto declarado puede ser uno de los que CONSUMEN el dato
    # corrupto: esos serian "el motor se trago la basura".
    inseguros = {"value_coerced", "state_contaminated", "read_api_raises",
                 "write_api_breaks", "corruption_persisted"}
    filtrados = []
    for clase_id, clase in sorted(declaradas.items()):
        for efecto in clase.get("expected", []):
            if efecto in inseguros:
                filtrados.append(f"{clase_id}:{efecto}")
    check("Ningun efecto declarado por el motor consume el dato corrupto",
          not filtrados, "; ".join(filtrados))
    check("Todo alcance del modelo propio deriva a un efecto que NO usa el dato corrupto",
          all(efecto_del_alcance(alcance, politica) in seguros
              for alcance, politica in (("campo", "default_the_field"),
                                        ("grupo", "preserve_siblings"),
                                        ("fila", "preserve_siblings"),
                                        ("seccion", "preserve_siblings"),
                                        ("entrada", "preserve_siblings"),
                                        ("bloque", "adapt_container"),
                                        ("bloque", "none"),
                                        ("fichero", "none"))))
    return tabla


# ---------------------------------------------------------------- Parte B
def rechazo_de_una_clase(clase_id, escenario):
    """Ejecuta TODAS las comprobaciones de rechazo de UNA clase de corrupcion.

    Devuelve la lista de etiquetas de las comprobaciones que han fallado, de
    modo que la suite pytest pueda exigir el resultado clase a clase y la
    sonda pueda ejecutarse como script independiente.
    """
    from utils.contextual_adaptation_engine import ContextType

    desde = len(FAILURES)
    marca = sentinela(clase_id)
    tmp = tempfile.mkdtemp(prefix="jarvis_rechazo_")
    try:
        data_dir = os.path.join(tmp, "data")
        materializar(escenario["files"], data_dir)
        hashes_antes = {nombre: sha256(os.path.join(data_dir, nombre))
                         for nombre in os.listdir(data_dir)}

        # --- ARRANQUE: el motor arranca con el fichero corrupto ---------
        try:
            motor = nuevo_motor(data_dir)
            check(f"`{clase_id}`: el motor ARRANCA con el fichero corrupto", True)
        except Exception as exc:  # noqa: BLE001
            check(f"`{clase_id}`: el motor ARRANCA con el fichero corrupto", False,
                  f"{type(exc).__name__}: {exc}")
            return FAILURES[desde:]

        # --- CONTENIDO PRESENTE: la corrupcion es contenido, no ausencia
        hashes_despues = {nombre: sha256(os.path.join(data_dir, nombre))
                          for nombre in os.listdir(data_dir)}
        check(f"`{clase_id}`: el fichero corrupto NO se reescribe al cargar",
              hashes_antes == hashes_despues,
              ", ".join(sorted(os.listdir(data_dir))))
        presentes = [nombre for nombre, ruta in
                     ((n, os.path.join(data_dir, n)) for n in os.listdir(data_dir))
                     if marca in leer_fichero(ruta)]
        check(f"`{clase_id}`: el contenido corrupto sigue PRESENTE en disco",
              bool(presentes), ", ".join(presentes))

        # --- NO FUGA AL ESTADO -----------------------------------------
        estado = firma_operativa(motor)
        check(f"`{clase_id}`: el dato corrupto NO llega al ESTADO del motor",
              marca not in estado,
              "el sentinela aparece en el estado" if marca in estado else "")

        # --- APIS DE LECTURA: ninguna lanza ni devuelve la corrupcion ---
        for nombre, llamada in _lecturas(motor, ContextType):
            try:
                valor = llamada()
            except Exception as exc:  # noqa: BLE001
                check(f"`{clase_id}`: la API de lectura `{nombre}` NO lanza", False,
                      f"{type(exc).__name__}: {exc}")
                continue
            check(f"`{clase_id}`: la API de lectura `{nombre}` NO lanza", True)
            texto = json.dumps(_sin_ubicaciones(valor), default=str, ensure_ascii=False)
            check(f"`{clase_id}`: la API de lectura `{nombre}` NO devuelve el dato corrupto",
                  marca not in texto)

        # --- DETECTADO Y REPORTADO -------------------------------------
        # El informe de deteccion NOMBRA la desviacion encontrada: la
        # `location` puede contener el identificador de la clave o de la
        # fila corrupta. Eso es INFORMAR, no USAR: por eso la comprobacion
        # de "no devuelve el dato corrupto" ignora las `location` y este
        # bloque comprueba que la clase se nombra y se localiza.
        deteccion = motor.detect_corruption()
        ids = [d.get("id") for items in (deteccion.get("corrupted") or {}).values()
               for d in items]
        check(f"`{clase_id}`: la corrupcion se DETECTA y se REPORTA por su clase",
              clase_id in ids, f"informados={ids}")

        # --- APIS DE ESCRITURA: ninguna rompe --------------------------
        for nombre, llamada in _escrituras(motor):
            try:
                llamada()
                check(f"`{clase_id}`: la API de escritura `{nombre}` NO rompe", True)
            except Exception as exc:  # noqa: BLE001
                check(f"`{clase_id}`: la API de escritura `{nombre}` NO rompe", False,
                      f"{type(exc).__name__}: {exc}")

        # --- NO FUGA AL ESTADO TRAS ESCRIBIR ---------------------------
        estado = firma_operativa(motor)
        check(f"`{clase_id}`: el dato corrupto NO llega al estado tras escribir",
              marca not in estado)

        # --- NO FUGA AL DISCO ------------------------------------------
        persistido = [nombre for nombre, texto in ficheros_del_disco(data_dir).items()
                      if marca in texto]
        check(f"`{clase_id}`: el dato corrupto NO se PERSISTE en disco",
              not persistido, ", ".join(persistido))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return FAILURES[desde:]


def parte_b_rechazo_por_clase(tabla, motor_ref):
    print("\n== PARTE B: RECHAZO POR CLASE ==")
    for clase_id in sorted(tabla):
        rechazo_de_una_clase(clase_id, tabla[clase_id])


def _lecturas(motor, ContextType):
    """APIs de LECTURA que el propio motor declara en `no_data_behavior()`."""
    contrato = motor.no_data_behavior()
    llamadas = []
    for spec in contrato.get("read_apis", []):
        nombre = spec["api"]
        if nombre == "get_available_strategies":
            llamadas.append((nombre, lambda: motor.get_available_strategies(ContextType.PRODUCTION)))
        else:
            llamadas.append((nombre, lambda n=nombre: getattr(motor, n)()))
    llamadas.append(("detect_corruption", lambda: motor.detect_corruption()))
    llamadas.append(("detect_absent_storage", lambda: motor.detect_absent_storage()))
    llamadas.append(("detect_absent_sections", lambda: motor.detect_absent_sections()))
    return llamadas


def _escrituras(motor):
    """APIs de ESCRITURA que el propio motor declara en `no_data_behavior()`."""
    contrato = motor.no_data_behavior()
    llamadas = []
    for spec in contrato.get("write_apis", []):
        nombre = spec["api"]
        llamadas.append((nombre, lambda n=nombre: getattr(motor, n)()))
    # La escritura de feedback es la que el contrato de corrupcion nombra como
    # la que reventaba cuando la seccion corrupta llegaba al estado.
    llamadas.append(("_capture_feedback",
                     lambda: motor._capture_feedback({"adaptation_id": "verificacion_rechazo"})))
    return llamadas


# ---------------------------------------------------------------- Parte C
def selectividad_de_una_clase(clase_id, escenario, motor_ref):
    """Comprueba que el rechazo de UNA clase es SELECTIVO.

    Un rechazo correcto no solo impide que la corrupcion llegue al estado:
    tampoco debe destruir el contenido sano que la corrupcion no destruye, y
    lo que si destruye debe quedar en su valor por defecto.

    Devuelve las etiquetas de las comprobaciones que han fallado.
    """
    desde = len(FAILURES)
    tmp = tempfile.mkdtemp(prefix="jarvis_rechazo_sel_")
    try:
        data_dir = os.path.join(tmp, "data")
        materializar(escenario["files"], data_dir)
        motor = nuevo_motor(data_dir)

        esperado = hermano_debe_sobrevivir(escenario["alcance"], escenario["hermano"])
        if esperado is None:
            return FAILURES[desde:]
        observed = hermano_presente(motor, escenario["hermano"])
        check(f"`{clase_id}`: el contenido sano {'SOBREVIVE' if esperado else 'NO sobrevive'} "
              f"al rechazo", observed is esperado,
              f"alcance={escenario['alcance']} observado={observed}")

        if alcance_afecta_a_unidad(escenario):
            check(f"`{clase_id}`: la unidad descartada conserva el VALOR POR DEFECTO",
                  unidad_intacta(motor, motor_ref, escenario["unidad"]),
                  str(escenario["unidad"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return FAILURES[desde:]


def parte_c_selectividad(tabla, motor_ref):
    print("\n== PARTE C: SELECTIVIDAD DEL RECHAZO ==")
    for clase_id in sorted(tabla):
        selectividad_de_una_clase(clase_id, tabla[clase_id], motor_ref)


def alcance_afecta_a_unidad(escenario):
    """La unidad descartada se comprueba siempre que el alcance la declara."""
    return escenario["unidad"] is not None


# ---------------------------------------------------------------- Parte D
def controles_de_no_vacio():
    """Los controles que demuestran que la sonda NO es vacua.

    En cada control el sentinela es un dato VALIDO: tiene que LLEGAR al
    estado. Si el escaneo del rechazo no lo ve, el escaneo no discrimina y la
    comprobacion del rechazo no prueba nada.
    """
    return {
        "regla sana": (
            _reglas([dict(REGLA_SANA, rule_id=sentinela("CONTROL_regla"))]),
            lambda motor: sentinela("CONTROL_regla") in (motor.adaptation_rules or {})),
        "seccion sana": (
            _base({"success_patterns": {"production": [{"patron": sentinela("CONTROL_seccion")}]}}),
            lambda motor: sentinela("CONTROL_seccion") in json.dumps(motor.knowledge_base, default=str)),
        "fila de feedback sana": (
            _feedback(goal_adaptation_feedback=[dict(FILA_FB_SANA, adaptation_id=sentinela("CONTROL_feedback"))]),
            lambda motor: sentinela("CONTROL_feedback") in json.dumps(motor.knowledge_base, default=str)),
        "fila de aprendizaje sana": (
            _aprendizaje(learning_results=[dict(FILA_LR_SANA, adaptation_id=sentinela("CONTROL_aprendizaje"))]),
            lambda motor: sentinela("CONTROL_aprendizaje") in json.dumps(motor.knowledge_base, default=str)),
    }


def control_de_no_vacio(nombre):
    """Ejecuta UN control de no-vacuidad. Devuelve las etiquetas fallidas."""
    desde = len(FAILURES)
    ficheros, comprobacion = controles_de_no_vacio()[nombre]
    tmp = tempfile.mkdtemp(prefix="jarvis_rechazo_control_")
    try:
        data_dir = os.path.join(tmp, "data")
        materializar(ficheros, data_dir)
        motor = nuevo_motor(data_dir)
        check(f"CONTROL `{nombre}`: el sentinela como dato VALIDO SI llega al estado",
              comprobacion(motor),
              "el escaneo no ve el dato valido: la sonda no discrimina")
        # Y el dato sano se ofrece por la API de lectura: las comprobaciones
        # de rechazo no se apoyan en APIs que devuelven siempre vacio.
        if nombre == "regla sana":
            offered = [r.get("rule_id") for r in motor.get_adaptation_rules()]
            check("CONTROL `regla sana`: la API de lectura ofrece la regla sana",
                  sentinela("CONTROL_regla") in offered, f"ofrecidas={offered}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return FAILURES[desde:]


def parte_d_no_vacio():
    print("\n== PARTE D: NO VACUO (el sentinela como dato VALIDO) ==")
    for nombre in controles_de_no_vacio():
        control_de_no_vacio(nombre)


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
    hashes_iniciales = {os.path.join(PRODUCTION_DATA_DIR, f): sha256(os.path.join(PRODUCTION_DATA_DIR, f))
                         for f in STORAGE_FILES}

    # El CWD se mueve al temporal y NO se restaura: el hilo de aprendizaje de
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma
    # asincrona usando una ruta RELATIVA, y restaurarla antes de que termine
    # contaminaria el `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_rechazo_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE VERIFICACION DEL RECHAZO (2.8.8.9.6.4)")
    _ref_dir = os.path.join(tempfile.mkdtemp(prefix="jarvis_rechazo_ref_"), "data")
    motor_ref = nuevo_motor(_ref_dir)
    tabla = parte_a_contrato(motor_ref)
    parte_b_rechazo_por_clase(tabla, motor_ref)
    parte_c_selectividad(tabla, motor_ref)
    parte_d_no_vacio()
    parte_e_no_contaminacion(hashes_iniciales)
    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
