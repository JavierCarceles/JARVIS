#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MUTACION de 2.8.8.9.7.2: comprueba que los tests DETECTAN la regres.

Cada mutacion rompe UNA pieza de la RECUPERACION PARCIAL y comprueba que los
tests de 2.8.8.9.7.1 y de 2.8.8.9.7.2 FALLAN. Si una mutacion NO produce
fallos, los tests son INSENSIBLES a esa pieza: no prueban nada.

Las piezas que se rompen son:
  - la DETECCION de la unidad que corrompe: si no se detecta, la corrupcion
    aborta el fichero entero y se pierde todo lo recuperable;
  - la RECUPERACION en el nivel de la UNIDAD: si el campo corrupto conserva su
    valor, la fila se descarta entera, los disparadores validos se pierden, el
    contenedor no se reconstruye o el grupo sano no sobrevive, se pierde justo
    el dato que el contrato declara recuperable;
  - el INFORME de la recuperacion: si no se informa, o si no es una COPIA, el
    motor no declara lo que ha recuperado.

AISLAMIENTO: la mutacion se aplica a una COPIA del arbol `src/` en un
directorio temporal. El `src/` del repositorio NO se toca nunca, ni siquiera
si el proceso se interrumpe: no hay estado que restaurar.

Primero se ejecuta una LINEA BASE sin mutar: si esa no pasa, el arnes no
demuestra nada y todas las mutaciones se darian por detectadas.

La sonda distingue cuatro casos:
  - DETECTADA: los tests fallan por la mutacion.
  - INSEGURO:  los tests no fallan -> no discriminan esa pieza.
  - CRASH:     los tests termineron con error y sin fallos de contraste.
  - BASE-FALLA: la linea base no pasa -> el arnes no es valido.

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

# Ficheros de `data/` de produccion que los tests de guarda vigilan: se
# copian al temporal para que la guarda tenga algo que vigilar.
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

# Modulos de test que tienen que DETECTAR la rotura.
MODULOS_DE_TEST = (
    "test_2_8_8_9_7_1_recoverable.py",
    "test_2_8_8_9_7_2_recovery_partial.py",
)

# (nombre, texto_original, texto_mutado, tests_que_deben_fallar)
MUTACIONES = [
    # --- la DETECCION de la unidad que corrompe ---------------------------
    ("motor: los campos de conversion ESTRICTA dejan de detectarse",
     "            elif not self._es_convertible_a_entero(valor):",
     "            elif False:",
     {"test_la_medicion_coincide_con_lo_declarado"}),

    # --- la RECUPERACION en el nivel de la UNIDAD -------------------------
    ("motor: el campo corrupto conserva su valor en vez del valor por DEFECTO",
     "                nuevo = self._valor_por_defecto_de_recuperacion(campo, recuperada.get(\"rule_id\"))",
     "                nuevo = valor",
     {"test_el_dato_corrupto_no_llega_al_estado",
      "test_el_estado_guarda_el_valor_por_defecto",
      "test_el_informe_no_contiene_el_dato_corrupto"}),

    ("motor: la fila de regla no se recupera: se descarta entera",
     "                    fila, recuperadas = self._recuperar_fila_de_regla(row, desviaciones)",
     "                    fila, recuperadas = row, []",
     {"test_la_medicion_coincide_con_lo_declarado",
      "test_la_recuperacion_se_registra_en_la_unidad_que_corrompe"}),

    ("motor: al recuperar el campo se pierden los disparadores validos",
     "                nuevo = [bruto for bruto in valor if self._coerce_context(bruto) is not None]",
     "                nuevo = []",
     {"test_la_determinacion_no_es_vacia",
      "test_la_medicion_coincide_con_lo_declarado",
      "test_lo_recuperable_llega_al_estado"}),

    ("motor: el contenedor de reglas no se reconstruye",
     "            if not self._fila_valida(valor, \"adaptation_rules\"): continue",
     "            continue",
     {"test_la_medicion_coincide_con_lo_declarado",
      "test_la_recuperacion_se_registra_en_la_unidad_que_corrompe"}),

    ("motor: el grupo corrupto de la base se aplica al estado",
     "            if not _cumple_tipo(contenido, tipo_grupo):",
     "            if False:",
     {"test_la_determinacion_no_es_vacia",
      "test_la_medicion_coincide_con_lo_declarado",
      "test_la_recuperacion_se_registra_en_la_unidad_que_corrompe",
      "test_lo_recuperable_llega_al_estado"}),

    ("motor: la seccion de la base se descarta entera en vez de recuperar sus grupos",
     "                        recuperado, recuperadas = self._recuperar_grupos_de_base(clave, valor)",
     "                        recuperado, recuperadas = None, []",
     {"test_la_medicion_coincide_con_lo_declarado",
      "test_la_recuperacion_se_registra_en_la_unidad_que_corrompe"}),

    # --- el INFORME de la recuperacion -------------------------------------
    ("motor: lo recuperado no se informa",
     "        for recuperacion in recuperaciones:",
     "        for recuperacion in []:",
     {"test_la_recuperacion_se_registra_en_la_unidad_que_corrompe"}),

    ("motor: el informe no es una COPIA defensiva",
     '        return {"recoveries": copy.deepcopy(self._recovery_report),',
     '        return {"recoveries": self._recovery_report,',
     {"test_la_api_de_recuperacion_es_de_solo_lectura"}),
]


def _fallos_de_pytest(salida):
    """Tests que han fallado, por nombre de funcion."""
    fallidos = set()
    for linea in salida.splitlines():
        match = re.match(r"^FAILED\s+\S+::([A-Za-z0-9_]+)", linea.strip())
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
    destino_tests = os.path.join(destino, "tests", "utils", "contextual_adaptation_engine")
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
    """Ejecuta los modulos de test en el arbol temporal. Devuelve (ok, fallos)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(arbol, "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    objetivos = [os.path.join(arbol, TESTS_REL, modulo) for modulo in MODULOS_DE_TEST]
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header",
                           "-p", "no:cacheprovider", "--tb=no", "-rf"] + objetivos,
                          cwd=arbol, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=3600)
    salida = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, _fallos_de_pytest(salida), salida


def main():
    with open(os.path.join(ROOT, ENGINE_REL), "r", encoding="utf-8") as handle:
        original = handle.read()

    # --- LINEA BASE: sin mutar, los tests tienen que pasar ----------------
    base = tempfile.mkdtemp(prefix="mutacion_base_")
    try:
        _preparar_arbol(base)
        ok, fallos, salida = _ejecutar_tests(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if not ok:
        print("== MUTACION DE 2.8.8.9.7.2 ==")
        print("  [BASE-FALLA] la linea base no pasa: el arnes no demuestra nada")
        print("  Tests que fallan sin mutar: " + (", ".join(sorted(fallos)) or "(sin nombre)"))
        print(salida[-4000:])
        return 1

    resultados = []
    for nombre, antes, despues, esperadas in MUTACIONES:
        if antes not in original:
            resultados.append((nombre, "NO-APLICA", "el texto a mutar no aparece", esperadas))
            continue
        arbol = tempfile.mkdtemp(prefix="mutacion_")
        try:
            _preparar_arbol(arbol)
            with open(os.path.join(arbol, ENGINE_REL), "w", encoding="utf-8") as handle:
                handle.write(original.replace(antes, despues, 1))
            ok, fallos, salida = _ejecutar_tests(arbol)
            if ok:
                estado = "INSEGURO"
                detalle = "los tests NO han fallado: no discriminan"
            elif not fallos:
                estado = "CRASH"
                detalle = "los tests han terminado con error y sin fallos de contraste"
            else:
                estado = "DETECTADA"
                detalle = f"{len(fallos)} test(s) fallido(s)"
                if esperadas:
                    faltantes = sorted(esperadas - fallos)
                    if faltantes:
                        detalle += " | no identificados: " + ", ".join(faltantes)
                    else:
                        detalle += " | identificados: " + ", ".join(sorted(esperadas))
            resultados.append((nombre, estado, detalle, esperadas))
        finally:
            shutil.rmtree(arbol, ignore_errors=True)

    print("\n== MUTACION DE 2.8.8.9.7.2 ==")
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
