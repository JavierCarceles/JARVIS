#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MUTACION DEL RECHAZO (2.8.8.9.6.4): comprobar que el test NO ES VACUO.

Este script ROMPE el rechazo de la corrupcion en el motor, uno a uno, y exige
que el test de 2.8.8.9.6.4 DETECTE cada rotura. Si una mutacion no rompe el
test, el test no esta comprobando lo que dice comprobar.

MUTACIONES
  M1: `_desviaciones_de_regla` no detecta ninguna desviacion -> la fila
      corrupta de `contextual_adaptation_rules.json` llega al estado.
  M2: `_seccion_de_conocimiento_valida` acepta cualquier seccion -> la
      seccion corrupta de `contextual_knowledge_base.json` llega al estado.
  M3: `detect_corruption` no informa de nada -> la corrupcion se ignora en
      silencio y no se puede nombrar la desviacion rechazada.

Uso:
    python tests/utils/contextual_adaptation_engine/mutation_check_2_8_8_9_6_4.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "..", ".."))
ENGINE = os.path.join(ROOT_DIR, "src", "utils", "contextual_adaptation_engine.py")
TEST_FILE = os.path.join(TESTS_DIR, "test_2_8_8_9_6_4_rejection_runtime.py")

MUTACIONES = {
    "M1_las_deviaciones_de_regla_no_se_detectan": (
        "        desviaciones: List[Tuple[str, str]] = []",
        "        desviaciones: List[Tuple[str, str]] = []\n"
        "        return []  # MUTACION M1: la fila corrupta NO se descarta",
    ),
    "M2_cualquier_seccion_de_conocimiento_es_valida": (
        "        por_defecto = self._valores_por_defecto.get(clave)",
        "        return True  # MUTACION M2: la seccion corrupta NO se descarta\n"
        "        por_defecto = self._valores_por_defecto.get(clave)",
    ),
    "M3_la_corrupcion_no_se_informa": (
        "            if detections: corrupted[name] = detections",
        "            if detections: corrupted[name] = []  # MUTACION M3: no se informa",
    ),
}


def _leer(ruta):
    """Lee el fichero conservando sus finales de linea."""
    with open(ruta, encoding="utf-8", newline="") as handle:
        return handle.read()


def _escribir(ruta, codigo):
    with open(ruta, "w", encoding="utf-8", newline="") as handle:
        handle.write(codigo)


def aplicar(motor, mutacion):
    """Devuelve el codigo del motor con la mutacion aplicada."""
    codigo = _leer(motor)
    original, sustituto = mutacion
    if original not in codigo:
        raise SystemExit(f"la mutacion no encuentra su ancla:\n{original!r}")
    # La sustitucion se hace con el MISMO final de linea que usa el fichero.
    separador = "\r\n" if "\r\n" in codigo else "\n"
    return codigo.replace(original, sustituto.replace("\n", separador), 1)


def ejecutar_test():
    """Ejecuta el test de 6.4 y devuelve el codigo de salida de pytest."""
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_FILE, "-q", "-p", "no:cacheprovider",
         "--no-header", "-x"],
        cwd=ROOT_DIR, capture_output=True, text=True, timeout=1800)
    return proceso.returncode, proceso.stdout[-3000:]


def main():
    print("MUTACION DEL RECHAZO (2.8.8.9.6.4): el test tiene que DETECTAR cada rotura\n")
    codigo_original = _leer(ENGINE)
    backup_dir = tempfile.mkdtemp(prefix="jarvis_mut_")
    with open(os.path.join(backup_dir, "engine.py"), "w", encoding="utf-8", newline="") as handle:
        handle.write(codigo_original)

    fallos = []
    try:
        for nombre, mutacion in MUTACIONES.items():
            # El codigo mutado se calcula ANTES de abrir el motor en modo
            # escritura: abrirlo truncaria el fichero que hay que leer.
            codigo_mutado = aplicar(ENGINE, mutacion)
            _escribir(ENGINE, codigo_mutado)
            codigo, salida = ejecutar_test()
            detectado = codigo != 0
            print(f"  [{'OK  ' if detectado else 'FALLO'}] {nombre}: "
                  f"el test {'DETECTA' if detectado else 'NO detecta'} la rotura "
                  f"(pytest={codigo})")
            if not detectado:
                fallos.append(nombre)
                print(salida)
    finally:
        _escribir(ENGINE, codigo_original)
        shutil.rmtree(backup_dir, ignore_errors=True)

    print(f"\n  Mutaciones que el test NO ha detectado: {len(fallos)}")
    for nombre in fallos:
        print(f"    - {nombre}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
