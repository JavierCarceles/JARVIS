#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MUTACION de 2.8.8.9.8.2: comprueba que el test de la IMPLEMENTACION SIGUE DETECTANDO.

Cada mutacion rompe UNA de las PIEZAS que 2.8.8.9.8.2 implemento y comprueba
que el TEST PERMANENTE `test_2_8_8_9_8_2_total_loss_fallback_implemented.py` la
VE.

Las piezas que se rompen son las TRES que 2.8.8.9.8.1 determino como
PENDIENTES, mas las que las sostienen:
  - la CARGA declara lo que ocurrio: si volviera a declarar siempre VERDADERO
    (o siempre FALSO) el test tiene que ver la mentira;
  - el ESTADO AGREGADO declara la perdida: si volviera a NO contar los
    ficheros ilegibles, el test tiene que verlo;
  - el RESPALDO cubre la persistencia: si volviera a cubrir solo dos ficheros,
    el test tiene que verlo;
  - el fallback NO inventa datos y NO destruye el material de diagnostico: si
    fabricase una regla o reescribiese los ficheros corruptos, el test tiene
    que verlo;
  - la RECONCILIACION del contrato declara lo implementado: si el contrato
    volviera a declarar un invariante pendiente, el test tiene que verlo.

Si una mutacion NO produce fallos, la verificacion es INSENSIBLE a esa pieza:
no prueba nada.

AISLAMIENTO: la mutacion se aplica a una COPIA del arbol `src/` en un
directorio temporal. El `src/` del repositorio NO se toca nunca, ni siquiera
si el proceso se interrumpe: no hay estado que restaurar.

El banco distingue tres casos:
  - DETECTADA: el test esperado ha fallado.
  - INSEGURO:  ningun test ha fallado -> no discrimina esa pieza.
  - CRASH:     pytest ha terminado con error y sin fallos nombrados.

No modifica `data/` de produccion: los tests trabajan en un directorio
temporal.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ENGINE_REL = os.path.join("src", "utils", "contextual_adaptation_engine.py")
TESTS_REL = os.path.join("tests", "utils", "contextual_adaptation_engine")
MODULO_REL = os.path.join(TESTS_REL, "test_2_8_8_9_8_2_total_loss_fallback_implemented.py")

FICHEROS_DE_PRODUCCION = (
    "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results.json",
    "contextual_adaptation_rules.json",
    "contextual_knowledge_base.json",
    "knowledge_graph.json",
    "learning_history.json",
    "improvement_rules.json",
    "adaptive_performance.json",
)

# (nombre, texto_original, texto_mutado, tests que deben fallar)
MUTACIONES = [
    # --- la CARGA declara lo que ocurrio -----------------------------------
    ("motor: la carga DECLARA siempre VERDADERO",
     "        return self._unidades_obtenidas() > 0",
     "        return True",
     {"test_la_carga_declara_falso_cuando_la_persistencia_no_aporta_unidades"}),

    ("motor: la carga DECLARA siempre FALSO",
     "        return self._unidades_obtenidas() > 0",
     "        return False",
     {"test_la_carga_declara_verdadero_con_datos_sanos"}),

    ("motor: el fallback INVENTA una regla a partir del fichero roto",
     '        except Exception as exc: self.logger.error("Error cargando reglas: %s", exc); return False',
     '        except Exception as exc: self.logger.error("Error cargando reglas: %s", exc); '
     'self.adaptation_rules = {"regla_fabricada": AdaptationRule("regla_fabricada", "fabricada", '
     '"", "", [], [], .5, 1, True, 0., 0, None, 0., [], {}, None)}; return False',
     {"test_la_carga_deja_el_estado_en_los_defaults_del_codigo"}),

    ("motor: la carga SOBREESCRIBE los ficheros corruptos",
     "            if loaded: self.adaptation_rules = loaded\n            return True",
     "            if loaded: self.adaptation_rules = loaded\n            self.save_adaptation_rules()\n            return True",
     {"test_la_carga_no_sobrescribe_los_ficheros_corruptos"}),

    # --- el ESTADO AGREGADO declara la perdida ----------------------------
    ("motor: el estado agregado deja de contar lo ILEGIBLE como anomalia",
     '"corruption_count": anomalias,',
     '"corruption_count": corruption["corruption_count"],',
     {"test_el_estado_agregado_cuenta_los_ficheros_ilegibles_como_anomalia"}),

    # --- el RESPALDO cubre la persistencia --------------------------------
    ("motor: el respaldo vuelve a cubrir SOLO dos ficheros de persistencia",
     "        for name, path in self.expected_storage_paths().items():",
     "        for name, path in list(self.expected_storage_paths().items())[:2]:",
     {"test_el_respaldo_cubre_los_cuatro_ficheros_de_persistencia"}),

    ("motor: el respaldo ALTERA el fichero de origen",
     'shutil.copy2(path, os.path.join(backup_dir, f"{name}_backup_{stamp}.json")); copied = True',
     'shutil.copy2(path, os.path.join(backup_dir, f"{name}_backup_{stamp}.json")); '
     'open(path, "w", encoding="utf-8").write(""); copied = True',
     {"test_el_respaldo_no_altera_el_contenido_de_los_ficheros"}),

    # --- la RECONCILIACION del contrato -----------------------------------
    ("contrato: el contrato vuelve a declarar un invariante PENDIENTE",
     '        "pending": [],\n        "reconciliation": [',
     '        "pending": ["load_result_is_truthful"],\n        "reconciliation": [',
     {"test_el_contrato_reconcilia_la_implementacion_de_8_2"}),

    ("contrato: la entrada de 8.2 declara un invariante PENDIENTE",
     '             "pending": [],\n             "resolved": ["loss_visible_in_status"',
     '             "pending": ["load_result_is_truthful"],\n             "resolved": ["loss_visible_in_status"',
     {"test_el_contrato_reconcilia_la_implementacion_de_8_2"}),

    ("contrato: la entrada de 8.2 deja de declarar un invariante RESUELTO",
     '"resolved": ["loss_visible_in_status", "load_result_is_truthful", "backup_covers_all_persistence"],',
     '"resolved": ["loss_visible_in_status"],',
     {"test_el_contrato_reconcilia_la_implementacion_de_8_2"}),
]


def _fallos_de_pytest(salida):
    """Tests que han fallado o han ERROR, por nombre de funcion."""
    fallidos = set()
    for linea in salida.splitlines():
        match = re.match(r"^(?:FAILED|ERROR)\s+\S+::([A-Za-z0-9_]+)", linea.strip())
        if match:
            fallidos.add(match.group(1))
    return fallidos


def _preparar_arbol(destino):
    """Copia `src/`, los tests y el `data/` de produccion a un temporal.

    El `data/` se copia para que los tests de GUARDA tengan algo que vigilar:
    sin el, la guarda fallaria en todas las mutaciones y el banco no
    distinguiria una rotura real de un arnes roto.
    """
    os.makedirs(destino, exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "src"), os.path.join(destino, "src"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    destino_tests = os.path.join(destino, TESTS_REL)
    os.makedirs(destino_tests, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "tests", "conftest.py"),
                 os.path.join(destino, "tests", "conftest.py"))
    origen_tests = os.path.join(ROOT, TESTS_REL)
    for nombre in os.listdir(origen_tests):
        origen = os.path.join(origen_tests, nombre)
        if os.path.isfile(origen) and nombre.endswith(".py"):
            shutil.copy2(origen, os.path.join(destino_tests, nombre))
    destino_data = os.path.join(destino, "data")
    os.makedirs(destino_data, exist_ok=True)
    for nombre in FICHEROS_DE_PRODUCCION:
        origen = os.path.join(ROOT, "data", nombre)
        if os.path.isfile(origen):
            shutil.copy2(origen, os.path.join(destino_data, nombre))
    return destino


def _ejecutar_tests(arbol):
    """Ejecuta el modulo de test permanente en el arbol temporal.

    Devuelve (ok, fallos, salida).
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(arbol, "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # `-rEf`: se piden los RESUMENES de los tests FALLIDOS y de los ERROR
    # (un error de FIXTURE es un ERROR, no un FAILED: sin `-rE` el nombre del
    # test no apareceria y el banco no podria atribuir la deteccion).
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header",
                           "-p", "no:cacheprovider", "--tb=no", "-rEf",
                           os.path.join(arbol, MODULO_REL)],
                          cwd=arbol, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=3600)
    salida = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, _fallos_de_pytest(salida), salida


def main():
    with open(os.path.join(ROOT, ENGINE_REL), "r", encoding="utf-8") as handle:
        original = handle.read()

    # --- LINEA BASE: sin mutar, los tests tienen que pasar ----------------
    base = tempfile.mkdtemp(prefix="mutacion_82_base_")
    try:
        _preparar_arbol(base)
        ok, fallos_test, salida_test = _ejecutar_tests(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if not ok:
        print("== MUTACION DE 2.8.8.9.8.2 ==")
        print("  [BASE-FALLA] la linea base no pasa: el arnes no demuestra nada")
        print("  Tests que fallan sin mutar: " + (", ".join(sorted(fallos_test)) or "(sin nombre)"))
        print(salida_test[-4000:])
        return 1

    resultados = []
    for nombre, antes, despues, esperadas in MUTACIONES:
        if antes not in original:
            resultados.append((nombre, "NO-APLICA", "el texto a mutar no aparece", esperadas))
            continue
        arbol = tempfile.mkdtemp(prefix="mutacion_82_")
        try:
            _preparar_arbol(arbol)
            with open(os.path.join(arbol, ENGINE_REL), "w", encoding="utf-8",
                      newline="\n") as handle:
                handle.write(original.replace(antes, despues, 1))
            ok, fallos_test, _ = _ejecutar_tests(arbol)
            if ok:
                estado = "INSEGURO"
                detalle = "ningun test ha fallado: no discrimina"
            elif not fallos_test:
                estado = "CRASH"
                detalle = "los tests han terminado con error y sin fallos nombrados"
            else:
                estado = "DETECTADA"
                detalle = f"tests: {len(fallos_test)} fallido(s)"
                if esperadas:
                    faltantes = sorted(esperadas - fallos_test)
                    if faltantes:
                        detalle += " | no identificados: " + ", ".join(faltantes)
                    else:
                        detalle += " | identificados: " + ", ".join(sorted(esperadas))
            resultados.append((nombre, estado, detalle, esperadas))
        finally:
            shutil.rmtree(arbol, ignore_errors=True)

    print("\n== MUTACION DE 2.8.8.9.8.2 ==")
    print("  [BASE-OK   ] la linea base pasa: el arnes discrimina")
    for nombre, estado, detalle, _ in resultados:
        print(f"  [{estado:9s}] {nombre} :: {detalle}")
    problemas = [r for r in resultados if r[1] != "DETECTADA"]
    print(f"\n  Mutaciones NO detectadas: {len(problemas)}")
    for nombre, estado, detalle, _ in problemas:
        print(f"    - {nombre} :: {estado} :: {detalle}")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
