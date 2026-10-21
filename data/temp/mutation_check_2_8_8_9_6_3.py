#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MUTACION de 2.8.8.9.6.3: comprueba que la sonda SIGUE DETECTANDO la regres.

Cada mutacion desactiva UNA parte de la deteccion de corrupcion del motor y
comprueba que la sonda de 2.8.8.9.6.1 (PARTE B: contraste declarado vs
observado) FALLA para las clases afectadas. Si una mutacion NO produce fallos,
la sonda es INSENSIBLE a esa parte de la deteccion: no prueba nada.

AISLAMIENTO: la mutacion se aplica a una COPIA del arbol `src/` en un
directorio temporal. El `src/` del repositorio NO se toca nunca, ni siquiera
si el proceso se interrumpe: no hay estado que restaurar.

La sonda distingue tres casos:
  - DETECTADA: la mutacion produce fallos de contraste en las clases previstas.
  - INSEGURO:  la sonda no fallo -> no discrimina esa parte de la deteccion.
  - CRASH:     la sonda termino con error sin fallos de contraste.

No modifica `data/` de produccion: la sonda trabaja en un directorio temporal.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE_REL = os.path.join("src", "utils", "contextual_adaptation_engine.py")
PROBE_REL = os.path.join("tests", "utils", "contextual_adaptation_engine",
                          "corruption_criteria_real.py")

# (nombre, texto_original, texto_mutado, clases_que_deben_fallar)
MUTACIONES = [
    ("reglas: sin desviaciones de formato",
     "                desviaciones = self._desviaciones_de_regla(row)",
     "                desviaciones = []",
     {"adaptation_rules.actions_string", "adaptation_rules.enabled_string",
      "adaptation_rules.last_execution_not_iso", "adaptation_rules.name_not_string",
      "adaptation_rules.success_rate_not_numeric", "adaptation_rules.threshold_not_numeric",
      "adaptation_rules.trigger_invalid_value", "adaptation_rules.triggers_not_list"}),

    ("reglas: sin guarda de identidad",
     '                if not isinstance(row, dict) or not row.get("rule_id"): continue',
     "                if False: continue",
     {"adaptation_rules.row_not_mapping", "adaptation_rules.row_missing_identity"}),

    ("reglas: los campos estrictos ya no abortan el fichero",
     '    _CAMPOS_ESTRICTOS_DE_REGLA = ("priority", "execution_count", "metadata")',
     "    _CAMPOS_ESTRICTOS_DE_REGLA = ()",
     {"adaptation_rules.priority_not_castable",
      "adaptation_rules.execution_count_not_castable",
      "adaptation_rules.metadata_not_mapping"}),

    ("reglas: la seccion `rules` corrupta se aplica al estado",
     "            for row in rows if isinstance(rows, list) else []:\n"
     '                if not isinstance(row, dict) or not row.get("rule_id"): continue',
     "            for row in (rows if isinstance(rows, list) else list(rows)):\n"
     '                if not row.get("rule_id"): continue',
     {"adaptation_rules.rules_wrong_type"}),

    ("base: toda seccion se aplica a la base",
     "                    if not self._seccion_de_conocimiento_valida(clave, valor):",
     "                    if False:",
     {"knowledge_base.section_not_mapping", "knowledge_base.strategies_not_mapping",
      "knowledge_base.unexpected_key", "knowledge_base.section_partial"}),

    ("base: un `data` que no es mapping se aplica",
     "            if isinstance(data, dict):",
     "            if True:",
     {"knowledge_base.data_not_mapping"}),

    ("filas: toda fila se acepta",
     "        if not isinstance(fila, dict): return False\n"
     '        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {})'
     '.get("real_format", {}) or {}',
     "        if True: return True\n"
     "        if not isinstance(fila, dict): return False\n"
     '        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {})'
     '.get("real_format", {}) or {}',
     {"goal_adaptation_feedback.row_not_mapping",
      "goal_adaptation_learning_results.row_not_mapping"}),

    ("estrategia aprendida: sin evidencia se restaura",
     "        if not isinstance(entrada, dict): return False\n"
     "        for campo in self._EVIDENCIA_DE_ESTRATEGIA:\n"
     "            if entrada.get(campo) is None: return False\n"
     '        if not _cumple_tipo(entrada.get("confidence"), "number"): return False\n'
     '        if not _cumple_tipo(entrada.get("success_rate"), "number"): return False\n'
     "        return True",
     "        return True",
     {"goal_adaptation_learning_results.strategy_missing_identity"}),

    ("feedback: una seccion que no es lista se aplica",
     "            if isinstance(rows, list):\n"
     '                self.knowledge_base["goal_adaptation_feedback"] = '
     '[row for row in rows if self._fila_valida(row, "goal_adaptation_feedback")]',
     "            if True:\n"
     '                self.knowledge_base["goal_adaptation_feedback"] = list(rows)',
     {"goal_adaptation_feedback.section_not_list"}),

    ("feedback: un historial que no es lista se aplica",
     "            if isinstance(history, list) and history:\n"
     "                self.adaptation_history = [_AdaptationHistoryEntry(row) for row in history"
     " if isinstance(row, dict)]",
     "            if True:\n"
     "                self.adaptation_history = list(history)",
     {"goal_adaptation_feedback.history_not_list"}),

    ("aprendizaje: una seccion que no es lista se aplica",
     "            if isinstance(loaded_results, list):\n"
     '                filas = [row for row in loaded_results if self._fila_valida(row, '
     '"goal_adaptation_learning_results")]',
     "            if True:\n"
     '                filas = list(loaded_results)',
     {"goal_adaptation_learning_results.learning_results_not_list"}),
]


def _fallos_de_contraste(salida):
    """Ids de las clases cuyo contraste DECLARADO vs OBSERVADO fallo."""
    ids = []
    for linea in salida.splitlines():
        if "[FALLO]" not in linea:
            continue
        match = re.search(r"`([a-z_]+\.[a-z_]+)`", linea)
        if match:
            ids.append(match.group(1))
    return sorted(set(ids))


def _copiar_arbol(destino):
    """Copia `src/` y la sonda a un directorio temporal autonomous."""
    os.makedirs(destino, exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "src"), os.path.join(destino, "src"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    destino_sonda = os.path.join(destino, "tests", "utils", "contextual_adaptation_engine")
    os.makedirs(destino_sonda, exist_ok=True)
    for nombre in os.listdir(os.path.join(ROOT, os.path.dirname(PROBE_REL))):
        origen = os.path.join(ROOT, os.path.dirname(PROBE_REL), nombre)
        if os.path.isfile(origen):
            shutil.copy2(origen, os.path.join(destino_sonda, nombre))
    return os.path.join(destino, PROBE_REL)


def main():
    with open(os.path.join(ROOT, ENGINE_REL), "r", encoding="utf-8") as handle:
        original = handle.read()

    resultados = []
    for nombre, antes, despues, esperadas in MUTACIONES:
        if antes not in original:
            resultados.append((nombre, "NO-APLICA", "el texto a mutar no aparece", esperadas))
            continue
        arbol = tempfile.mkdtemp(prefix="mutacion_")
        try:
            sonda = _copiar_arbol(arbol)
            ruta_engine = os.path.join(arbol, ENGINE_REL)
            with open(ruta_engine, "w", encoding="utf-8") as handle:
                handle.write(original.replace(antes, despues, 1))
            proc = subprocess.run([sys.executable, sonda], cwd=arbol, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=900)
            salida = (proc.stdout or "") + (proc.stderr or "")
            fallos = _fallos_de_contraste(salida)
            if not fallos and proc.returncode != 0:
                estado = "CRASH"
                detalle = f"la sonda termino con codigo {proc.returncode}"
            elif not fallos:
                estado = "INSEGURO"
                detalle = "la sonda no fallo: no discrimina"
            else:
                estado = "DETECTADA"
                faltantes = sorted(set(esperadas) - set(fallos))
                extra = sorted(set(fallos) - set(esperadas))
                detalle = f"fallaron={', '.join(fallos)}"
                if faltantes:
                    detalle += f" | NO detectadas: {', '.join(faltantes)}"
                if extra:
                    detalle += f" | extra: {', '.join(extra)}"
            resultados.append((nombre, estado, detalle, esperadas))
        finally:
            shutil.rmtree(arbol, ignore_errors=True)

    print("\n== MUTACION DE 2.8.8.9.6.3 ==")
    for nombre, estado, detalle, _ in resultados:
        print(f"  [{estado:9s}] {nombre} :: {detalle}")
    problemas = [r for r in resultados if r[1] != "DETECTADA"]
    print(f"\n  Mutaciones NO detectadas: {len(problemas)}")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
