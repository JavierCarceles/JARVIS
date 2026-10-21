#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MUTACION de 2.8.8.9.7.1: comprueba que la sonda SIGUE DETECTANDO la regres.

Cada mutacion rompe UNA pieza (del MOTOR o de la DECLARACION de lo
recuperable) y comprueba que la sonda de 2.8.8.9.7.1 FALLA. Si una mutacion
NO produce fallos, la sonda es INSENSIBLE a esa pieza: no prueba nada.

Las piezas que se rompen son de dos generos:
  - el DATO CORRUPTO vuelve al estado: la sonda tiene que verlo (PARTE B);
  - la DECLARACION de lo recuperable queda mal formada: la sonda tiene que
    verlo al contrastar la forma del contrato (PARTE A).

AISLAMIENTO: la mutacion se aplica a una COPIA del arbol `src/` en un
directorio temporal. El `src/` del repositorio NO se toca nunca, ni siquiera
si el proceso se interrumpe: no hay estado que restaurar.

La sonda distingue tres casos:
  - DETECTADA: la mutacion produce fallos de la sonda.
  - INSEGURO:  la sonda no fallo -> no discrimina esa pieza.
  - CRASH:     la sonda termino con error y sin fallos de contraste.

No modifica `data/` de produccion: la sonda trabaja en un directorio temporal.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ENGINE_REL = os.path.join("src", "utils", "contextual_adaptation_engine.py")
PROBE_REL = os.path.join("tests", "utils", "contextual_adaptation_engine",
                          "identify_recoverable_real.py")

# (nombre, texto_original, texto_mutado, clases_que_deben_fallar)
MUTACIONES = [
    # --- la DECLARACION de lo recuperable --------------------------------
    ("contrato: una clase de corrupcion queda sin declarar",
     '                    "adaptation_rules.name_not_string": {',
     '                    "adaptation_rules.name_not_string_renombrada": {',
     {"adaptation_rules.name_not_string"}),

    ("contrato: el valor por defecto de `enabled` deja de ser conservador",
     '            "enabled": {"value": False, "type": "boolean",',
     '            "enabled": {"value": True, "type": "boolean",',
     set()),

    ("contrato: la REGLA DE INDEPENDENCIA deja de estar declarada",
     '            "dos unidades son independientes si la ruta de una NO es un prefijo de la ruta "',
     '            "dos unidades son independientes si la ruta de una NO es un antecesor de la ruta "',
     set()),

    ("contrato: un valor por defecto deja de respetar el TIPO del formato",
     '            "confidence_threshold": {"value": 0.7, "type": "number",',
     '            "confidence_threshold": {"value": "0.7", "type": "number",',
     {"adaptation_rules.threshold_not_numeric"}),

    # --- el MOTOR: el dato corrupto vuelve al estado ----------------------
    ("motor: las reglas dejan de detectar la desviacion de formato",
     "                desviaciones = self._desviaciones_de_regla(row)",
     "                desviaciones = []",
     {"adaptation_rules.actions_string", "adaptation_rules.enabled_string",
      "adaptation_rules.last_execution_not_iso", "adaptation_rules.name_not_string",
      "adaptation_rules.success_rate_not_numeric", "adaptation_rules.threshold_not_numeric",
      "adaptation_rules.trigger_invalid_value", "adaptation_rules.triggers_not_list"}),

    ("motor: una seccion corrupta de la base se aplica al estado",
     "                    if not self._seccion_de_conocimiento_valida(clave, valor):",
     "                    if False:",
     {"knowledge_base.section_not_mapping", "knowledge_base.strategies_not_mapping",
      "knowledge_base.unexpected_key", "knowledge_base.section_partial"}),
]


def _fallos_de_la_sonda(salida):
    """Lineas `[FALLO]` de la sonda y clases a las que se atribuyen."""
    fallos = [linea.strip() for linea in salida.splitlines() if "[FALLO]" in linea]
    clases = set()
    for linea in fallos:
        for match in re.finditer(r"`([a-z_]+\.[a-z_]+)`", linea):
            clases.add(match.group(1))
    return fallos, clases


def _copiar_arbol(destino):
    """Copia `src/` y la sonda a un directorio temporal autonomo."""
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
                                  text=True, encoding="utf-8", errors="replace", timeout=1800)
            salida = (proc.stdout or "") + (proc.stderr or "")
            fallos, clases = _fallos_de_la_sonda(salida)
            if not fallos and proc.returncode != 0:
                estado = "CRASH"
                detalle = f"la sonda termino con codigo {proc.returncode} sin fallos"
            elif not fallos:
                estado = "INSEGURO"
                detalle = "la sonda no fallo: no discrimina"
            else:
                estado = "DETECTADA"
                detalle = f"{len(fallos)} comprobacion(es) fallida(s)"
                if clases:
                    detalle += f" | clases: {', '.join(sorted(clases))}"
                    if esperadas:
                        faltantes = sorted(esperadas - clases)
                        if faltantes:
                            detalle += f" | no identificadas: {', '.join(faltantes)}"
                else:
                    detalle += " | fallo GLOBAL (sin clase atribuible)"
            resultados.append((nombre, estado, detalle, esperadas))
        finally:
            shutil.rmtree(arbol, ignore_errors=True)

    print("\n== MUTACION DE 2.8.8.9.7.1 ==")
    for nombre, estado, detalle, _ in resultados:
        print(f"  [{estado:9s}] {nombre} :: {detalle}")
    problemas = [r for r in resultados if r[1] != "DETECTADA"]
    print(f"\n  Mutaciones NO detectadas: {len(problemas)}")
    for nombre, estado, detalle, _ in problemas:
        print(f"    - {nombre} :: {estado} :: {detalle}")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
