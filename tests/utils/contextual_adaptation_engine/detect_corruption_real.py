#!/usr/bin/env python3
"""
Deteccion de la CORRUPCION del subsistema de persistencia de Goal (2.8.8.9.6.3).

Script de sonda independiente de la suite pytest. NO modifica `data/` de produccion.

AISLAMIENTO: el proceso cambia su CWD a un directorio temporal ANTES de construir
ningun motor y NO lo restaura al final. Motivo (mismo hallazgo verificado en
runtime que en 2.8.8.9.5.2): `SelfImprovementSystem` usa la ruta RELATIVA fija
`data/knowledge_graph.json` y su hilo de aprendizaje la escribe de forma asincrona.
Si el CWD se restaurase antes de que ese hilo terminase, la escritura caeria sobre
el `data/` real de produccion. El `data/` de produccion solo se LEE, mediante rutas
absolutas.

Los ESCENARIOS no se duplican: se reutiliza el registro `CASES` de la sonda de
2.8.8.9.6.1 (`corruption_criteria_real.py`), que es la UNICA fuente de los ficheros
corruptos. Aqui solo se contrasta la DETECCION (2.8.8.9.6.3), no el rechazo
(2.8.8.9.6.4).

Parte A - FORMA DE LA API: `detect_corruption()` es de SOLO LECTURA, expone la
           forma declarada y no altera el estado del motor.
Parte B - DETECCION POR CLASE: las 27 clases declaradas en 2.8.8.9.6.1 se detectan
           una a una, cada una en su fichero.
Parte C - FRONTERA CON LA AUSENCIA: la corrupcion NO se reporta como fichero
           ausente (2.8.8.9.5.1) ni como fichero ilegible o seccion ausente
           (2.8.8.9.5.2): es contenido PRESENTE que se aparta del FORMATO REAL.
Parte D - NO CONTAMINACION: el `data/` de produccion queda byte a byte igual.

Uso:
    python tests/utils/contextual_adaptation_engine/detect_corruption_real.py
"""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

PRODUCTION_DATA_DIR = os.path.join(ROOT, "data")
STORAGE_FILES = ("goal_adaptation_feedback.json", "goal_adaptation_learning_results.json",
                 "contextual_adaptation_rules.json", "contextual_knowledge_base.json")

FAILURES = []
NOTES = []


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


def _cargar_sonda():
    """Carga el registro de escenarios de la sonda de 2.8.8.9.6.1."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corruption_criteria_real.py")
    spec = importlib.util.spec_from_file_location("corruption_criteria_real", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


SONDA = _cargar_sonda()
CASES = SONDA.CASES


def nuevo_motor(data_dir):
    from utils.contextual_adaptation_engine import ContextualAdaptationEngine
    os.makedirs(data_dir, exist_ok=True)
    return ContextualAdaptationEngine(data_dir=data_dir)


def materializar(caso, data_dir):
    """Escribe el escenario corrupto de un caso en `data_dir`."""
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in caso["files"]().items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as handle:
            handle.write(contenido if isinstance(contenido, str)
                         else json.dumps(contenido, ensure_ascii=False))


# ---------------------------------------------------------------- Parte A
def parte_a_forma_api():
    print("\n== PARTE A: FORMA DE LA API DE DETECCION ==")
    tmp = tempfile.mkdtemp(prefix="jarvis_detect_corruption_api_")
    data_dir = os.path.join(tmp, "data")
    motor = nuevo_motor(data_dir)

    deteccion = motor.detect_corruption()
    check("`detect_corruption()` devuelve un mapeo", isinstance(deteccion, dict), type(deteccion).__name__)
    for clave in ("expected", "checked", "corrupted", "corruption_count", "has_corruption",
                  "missing_files", "unreadable"):
        check(f"`detect_corruption()` informa la clave `{clave}`", clave in deteccion)
    check("`corrupted` es un mapeo de fichero a lista de desviaciones",
          isinstance(deteccion.get("corrupted"), dict)
          and all(isinstance(v, list) for v in deteccion.get("corrupted", {}).values()))

    # SOLO LECTURA: no crea ficheros de persistencia.
    antes = sorted(os.listdir(data_dir))
    motor.detect_corruption()
    despues = sorted(os.listdir(data_dir))
    check("La deteccion NO crea ficheros", antes == despues, f"{antes} -> {despues}")

    # SOLO LECTURA: no altera el estado del motor.
    estado_antes = json.dumps(motor.knowledge_base, sort_keys=True, default=str)
    reglas_antes = len(motor.adaptation_rules)
    motor.detect_corruption()
    check("La deteccion NO altera la base de conocimiento",
          estado_antes == json.dumps(motor.knowledge_base, sort_keys=True, default=str))
    check("La deteccion NO altera las reglas de adaptacion",
          reglas_antes == len(motor.adaptation_rules), f"{reglas_antes} -> {len(motor.adaptation_rules)}")

    # Los ids informados pertenecen al CONTRATO declarado en 2.8.8.9.6.1.
    declarados = {clase["id"] for spec in motor.corruption_criteria()["files"].values()
                  for clase in spec["corruptions"]}
    informados = {d["id"] for items in deteccion.get("corrupted", {}).values() for d in items}
    check("Los ids informados pertenecen al contrato declarado",
          informados <= declarados, ", ".join(sorted(informados - declarados)) or "sin ids fuera de contrato")

    # Cada desviacion informada lleva los datos de su clase declarada.
    contrato = {clase["id"]: clase for spec in motor.corruption_criteria()["files"].values()
                for clase in spec["corruptions"]}
    bien_documentadas = all(d.get("target") and d.get("violation") and d.get("severity")
                             and d.get("location")
                             for items in deteccion.get("corrupted", {}).values() for d in items)
    check("Cada desviacion informada lleva `target`, `violation`, `severity` y `location`",
          bien_documentadas)
    coherentes = all(d.get("target") == contrato[d["id"]]["target"]
                     and d.get("violation") == contrato[d["id"]]["violation"]
                     and d.get("severity") == contrato[d["id"]]["severity"]
                     for items in deteccion.get("corrupted", {}).values() for d in items)
    check("Los datos informados coinciden con los de la clase declarada", coherentes)

    # `get_engine_status()` expone el resultado en una clave nueva.
    status = motor.get_engine_status()
    check("`get_engine_status()` informa la clave `corruption`", "corruption" in status)
    check("`get_engine_status()['corruption']` informa `corrupted` y `corruption_count`",
          isinstance(status.get("corruption"), dict)
          and "corrupted" in status["corruption"] and "corruption_count" in status["corruption"])

    shutil.rmtree(tmp, ignore_errors=True)
    return


# ---------------------------------------------------------------- Parte B
def parte_b_deteccion_por_clase():
    print("\n== PARTE B: DETECCION POR CLASE ==")
    for clase_id in sorted(CASES):
        caso = CASES[clase_id]
        clave = clase_id.split(".")[0]
        tmp = tempfile.mkdtemp(prefix="jarvis_detect_corruption_clase_")
        data_dir = os.path.join(tmp, "data")
        materializar(caso, data_dir)
        motor = nuevo_motor(data_dir)
        deteccion = motor.detect_corruption()
        ids = [d["id"] for items in deteccion.get("corrupted", {}).values() for d in items]
        check(f"{clase_id}: la clase corrupta se informa", clase_id in ids, f"informados={ids}")
        check(f"{clase_id}: la deteccion se atribuye a su fichero",
              clase_id in [d["id"] for d in deteccion.get("corrupted", {}).get(clave, [])])
        check(f"{clase_id}: `corruption_count` cuenta la desviacion",
              deteccion.get("corruption_count", 0) >= 1)
        check(f"{clase_id}: `has_corruption` es verdadero", deteccion.get("has_corruption") is True)
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- Parte C
def parte_c_frontera_con_la_ausencia():
    print("\n== PARTE C: FRONTERA CON LA AUSENCIA ==")
    for clase_id in sorted(CASES):
        caso = CASES[clase_id]
        clave = clase_id.split(".")[0]
        tmp = tempfile.mkdtemp(prefix="jarvis_detect_corruption_frontera_")
        data_dir = os.path.join(tmp, "data")
        materializar(caso, data_dir)
        motor = nuevo_motor(data_dir)
        deteccion = motor.detect_corruption()
        check(f"{clase_id}: NO se reporta como fichero AUSENTE",
              clave not in deteccion.get("missing_files", []))
        check(f"{clase_id}: NO se reporta como fichero ILEGIBLE",
              clave not in deteccion.get("unreadable", {}))
        almacenamiento = motor.detect_absent_storage()
        check(f"{clase_id}: el fichero corrupto consta como PRESENTE",
              clave in almacenamiento.get("present", []))
        secciones = motor.detect_absent_sections()
        check(f"{clase_id}: el fichero corrupto NO consta como seccion ausente",
              clave not in secciones.get("missing_files", [])
              and clave not in secciones.get("unreadable", {}))
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- Parte D
def parte_d_no_contaminacion(hashes_iniciales):
    print("\n== PARTE D: NO CONTAMINACION DEL `data/` DE PRODUCCION ==")
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
    # `SelfImprovementSystem` escribe `data/knowledge_graph.json` de forma asincrona
    # usando una ruta RELATIVA, y restaurarla antes de que termine contaminaria el
    # `data/` de produccion.
    _workdir = tempfile.mkdtemp(prefix="jarvis_detect_corruption_cwd_")
    os.makedirs(os.path.join(_workdir, "data"), exist_ok=True)
    os.chdir(_workdir)

    print("SONDA DE DETECCION DE CORRUPCION (2.8.8.9.6.3)")
    parte_a_forma_api()
    parte_b_deteccion_por_clase()
    parte_c_frontera_con_la_ausencia()
    parte_d_no_contaminacion(hashes_iniciales)
    print("\n== RESUMEN ==")
    print(f"  Comprobaciones fallidas: {len(FAILURES)}")
    for f in FAILURES:
        print(f"    - {f}")
    print(f"  Hallazgos registrados: {len(NOTES)}")
    for n in NOTES:
        print(f"    - {n}")
    sys.exit(1 if FAILURES else 0)
