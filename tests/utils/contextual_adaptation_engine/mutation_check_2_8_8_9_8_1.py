#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MUTACION de 2.8.8.9.8.1: comprueba que la sonda y el test SIGUEN DETECTANDO.

Cada mutacion rompe UNA pieza (del MOTOR o de la DECLARACION del fallback) y
comprueba que la medicion la VE:
  - la SONDA `identify_fallback_real.py` tiene que reportar un fallo de
    contraste (una linea `[FALLO]`), porque es el instrumento que contrasta la
    declaracion contra el runtime;
  - el TEST PERMANENTE `test_2_8_8_9_8_1_total_loss_fallback.py` tiene que
    fallar, porque es la prueba que queda en la suite.

Si una mutacion NO produce fallos, la medicion es INSENSIBLE a esa pieza: no
prueba nada.

Las piezas que se rompen son de dos generos:
  - la DECLARACION del fallback queda mal formada o se contradice con lo
    observado: el contraste de forma (PARTE A) y el de determinacion (PARTE C)
    tienen que verlo;
  - el MOTOR deja de ofrecer una de las CAPAS de fallback que el contrato
    declara: el invariante correspondiente tiene que dejar de cumplirse.

La ultima mutacion ya no IMPLEMENTA una pieza pendiente: desde 2.8.8.9.8.2 el
fallback esta IMPLEMENTADO, de modo que las mutaciones del MOTOR lo ROMPEN (el
respaldo vuelve a cubrir dos ficheros, el estado agregado deja de contar lo
ilegible, la carga declara siempre VERDADERO) y las de la DECLARACION lo
CONTRADICEN (una CAPA que no existe, un invariante que declara otra CAPA).
La medicion tiene que VER cada rotura: si no la viera, el fallback
implementado no estaria verificado.

AISLAMIENTO: la mutacion se aplica a una COPIA del arbol `src/` en un
directorio temporal. El `src/` del repositorio NO se toca nunca, ni siquiera
si el proceso se interrumpe: no hay estado que restaurar.

La sonda distingue tres casos:
  - DETECTADA: la mutacion produce fallos.
  - INSEGURO:  la sonda no fallo -> no discrimina esa pieza.
  - CRASH:     la sonda termino con error y sin fallos de contraste.

No modifica `data/` de produccion: la sonda y los tests trabajan en un
directorio temporal.
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
SONDA_REL = os.path.join(TESTS_REL, "identify_fallback_real.py")
MODULO_REL = os.path.join(TESTS_REL, "test_2_8_8_9_8_1_total_loss_fallback.py")

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
    # --- la DECLARACION del fallback ---------------------------------------
    ("contrato: un invariante declarado desaparece",
     '            "files_not_overwritten": {',
     '            "files_not_overwritten_renombrado": {',
     {"test_el_contrato_del_fallback_esta_bien_formado"}),

    ("contrato: un invariante declara una CAPA que no existe",
     '"layer": "full_backup", "satisfied": True,',
     '"layer": "full_backup_inexistente", "satisfied": True,',
     {"test_todo_invariante_declara_capa_enunciado_y_veredicto"}),

    ("contrato: un invariante SATISFECHO se declara PENDIENTE",
     '"layer": "defaults_in_memory", "satisfied": True,',
     '"layer": "defaults_in_memory", "satisfied": False,',
     {"test_el_contrato_del_fallback_esta_bien_formado"}),

    ("contrato: una CAPA declarada deja de existir",
     '"full_backup": "',
     '"full_backup_renombrada": "',
     {"test_todo_invariante_declara_capa_enunciado_y_veredicto"}),

    ("contrato: la version del contrato cambia",
     '"version": "2.8.8.9.8.1",',
     '"version": "2.8.8.9.8.1-bis",',
     {"test_el_contrato_del_fallback_esta_bien_formado"}),

    ("contrato: un MODO de perdida total deja de declararse",
     '"unreadable_file": "el contenido del fichero no se puede parsear como JSON",',
     '"unreadable_file_renombrado": "el contenido del fichero no se puede parsear como JSON",',
     {"test_el_contrato_del_fallback_esta_bien_formado"}),

    # --- el MOTOR: una CAPA de fallback deja de ofrecerse ------------------
    ("motor: el motor NO conserva los defaults al cargar",
     "            if loaded: self.adaptation_rules = loaded",
     "            self.adaptation_rules = loaded",
     {"test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo"}),

    ("motor: el motor NO sigue operando tras la perdida",
     "confidence, time.time()-started, not errors,",
     "confidence, time.time()-started, False,",
     {"test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo"}),

    ("motor: la carga DECLARA siempre VERDADERO",
     "        return self._unidades_obtenidas() > 0",
     "        return True",
     {"test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo"}),

    ("motor: la carga SOBREESCRIBE los ficheros corruptos",
     "            if loaded: self.adaptation_rules = loaded\n            return True",
     "            if loaded: self.adaptation_rules = loaded\n            self.save_adaptation_rules()\n            return True",
     {"test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo"}),

    ("motor: el respaldo vuelve a cubrir SOLO dos ficheros de persistencia",
     "        for name, path in self.expected_storage_paths().items():",
     "        for name, path in list(self.expected_storage_paths().items())[:2]:",
     {"test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo"}),

    ("motor: el estado agregado deja de contar lo ILEGIBLE como anomalia",
     '"corruption_count": anomalias,',
     '"corruption_count": corruption["corruption_count"],',
     {"test_los_invariantes_declarados_satisfechos_se_cumplen_en_todo_modo"}),
]


def _fallos_de_la_sonda(salida):
    """Lineas `[FALLO]` de la sonda."""
    return [linea.strip() for linea in salida.splitlines() if "[FALLO]" in linea]


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


def _ejecutar_sonda(arbol):
    """Ejecuta la sonda en el arbol temporal. Devuelve (fallos, salida)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(arbol, "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, os.path.join(arbol, SONDA_REL)], cwd=arbol,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=1800)
    salida = (proc.stdout or "") + (proc.stderr or "")
    return _fallos_de_la_sonda(salida), salida


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

    # --- LINEA BASE: sin mutar, la sonda y los tests tienen que pasar -----
    base = tempfile.mkdtemp(prefix="mutacion_base_")
    try:
        _preparar_arbol(base)
        fallos_sonda, salida_sonda = _ejecutar_sonda(base)
        ok, fallos_test, salida_test = _ejecutar_tests(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if fallos_sonda or not ok:
        print("== MUTACION DE 2.8.8.9.8.1 ==")
        print("  [BASE-FALLA] la linea base no pasa: el arnes no demuestra nada")
        if fallos_sonda:
            print("  Fallos de la sonda: " + "; ".join(fallos_sonda))
        if not ok:
            print("  Tests que fallan sin mutar: " + (", ".join(sorted(fallos_test)) or "(sin nombre)"))
        print(salida_test[-4000:])
        return 1

    resultados = []
    for nombre, antes, despues, esperadas in MUTACIONES:
        if antes not in original:
            resultados.append((nombre, "NO-APLICA", "el texto a mutar no aparece", esperadas))
            continue
        arbol = tempfile.mkdtemp(prefix="mutacion_")
        try:
            _preparar_arbol(arbol)
            with open(os.path.join(arbol, ENGINE_REL), "w", encoding="utf-8",
                      newline="\n") as handle:
                handle.write(original.replace(antes, despues, 1))
            fallos_sonda, _ = _ejecutar_sonda(arbol)
            ok, fallos_test, _ = _ejecutar_tests(arbol)
            if not fallos_sonda and ok:
                estado = "INSEGURO"
                detalle = "ni la sonda ni los tests han fallado: no discrimina"
            elif not fallos_test:
                estado = "CRASH"
                detalle = ("los tests han terminado con error y sin fallos de contraste"
                           if not fallos_sonda else
                           "la sonda ha fallado pero los tests no: el arnes no discrimina")
            else:
                estado = "DETECTADA"
                detalle = f"sonda: {len(fallos_sonda)} fallo(s) | tests: {len(fallos_test)} fallido(s)"
                if esperadas:
                    faltantes = sorted(esperadas - fallos_test)
                    if faltantes:
                        detalle += " | no identificados: " + ", ".join(faltantes)
                    else:
                        detalle += " | identificados: " + ", ".join(sorted(esperadas))
            resultados.append((nombre, estado, detalle, esperadas))
        finally:
            shutil.rmtree(arbol, ignore_errors=True)

    print("\n== MUTACION DE 2.8.8.9.8.1 ==")
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
