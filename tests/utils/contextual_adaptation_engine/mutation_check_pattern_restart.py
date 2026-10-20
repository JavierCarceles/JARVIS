#!/usr/bin/env python3
"""
Comprobacion por mutacion del test de verificacion de patrones tras el reinicio
(2.8.8.9.4.5).

Este script NO es un test de pytest (no se recoge con el patron `test_*.py`).
Muta temporalmente `src/utils/contextual_adaptation_engine.py` para comprobar
que los tests de `test_goal_adaptation_pattern_restart_verification.py` detectan
cada tipo de rotura. Al terminar restaura SIEMPRE el fichero original.

Uso:
    python tests/utils/contextual_adaptation_engine/mutation_check_pattern_restart.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TARGET = os.path.join(ROOT, "src", "utils", "contextual_adaptation_engine.py")
TEST_FILE = os.path.join(
    "tests", "utils", "contextual_adaptation_engine",
    "test_goal_adaptation_pattern_restart_verification.py",
)

# (nombre, texto original, texto mutado)
MUTATIONS = [
    (
        "carga verbatim (sin filtro de validacion)",
        "        if not isinstance(learning_results, list): return learning_results\n"
        "        recovered = self._filter_validated_learning_results(learning_results)\n",
        "        if not isinstance(learning_results, list): return learning_results\n"
        "        recovered = list(learning_results)\n",
    ),
    (
        "patron recortado a los DATOS CRITICOS (5 campos)",
        "            row[\"learned_patterns\"] = [pattern for pattern in (row.get(\"learned_patterns\") or [])\n"
        "                                       if isinstance(pattern, dict) and self._is_validated_pattern(pattern, observations)]\n",
        "            row[\"learned_patterns\"] = [dict((k, v) for k, v in pattern.items()\n"
        "                                           if k in (\"pattern_id\", \"pattern_type\", \"context\", \"metrics\", \"confidence\"))\n"
        "                                       for pattern in (row.get(\"learned_patterns\") or [])\n"
        "                                       if isinstance(pattern, dict) and self._is_validated_pattern(pattern, observations)]\n",
    ),
    (
        "contexto del patron vaciado (estructuras anidadas)",
        "            row = copy.deepcopy(row)\n",
        "            row = copy.deepcopy(row)\n"
        "            for _p in (row.get(\"learned_patterns\") or []):\n"
        "                if isinstance(_p, dict):\n"
        "                    _p[\"context\"] = {} if isinstance(_p.get(\"context\"), dict) else _p.get(\"context\")\n",
    ),
    (
        "filas de aprendizaje sin metricas de convergencia",
        "            row = copy.deepcopy(row)\n",
        "            row = copy.deepcopy(row)\n"
        "            row.pop(\"convergence_metrics\", None)\n",
    ),
    (
        "la carga reescribe el fichero persistido",
        "            loaded_results = payload.get(\"learning_results\", self.knowledge_base.get(\"learning_results\", []))\n",
        "            loaded_results = payload.get(\"learning_results\", self.knowledge_base.get(\"learning_results\", []))\n"
        "            payload[\"last_updated\"] = \"2099-01-01T00:00:00\"\n"
        "            with open(path, \"w\", encoding=\"utf-8\") as _h: json.dump(payload, _h, indent=2, ensure_ascii=False)\n",
    ),
]


def _run_tests():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_FILE, "-q", "-p", "no:cacheprovider",
         "--tb=no", "-p", "no:logging"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    failed = []
    for line in out.splitlines():
        if line.startswith("FAILED ") or " FAILED" in line:
            name = line.split("::")[-1].split(" ")[0].strip()
            if name and name not in failed:
                failed.append(name)
    return proc.returncode, failed, out


def main():
    with open(TARGET, "r", encoding="utf-8") as handle:
        original = handle.read()

    backup = os.path.join(tempfile.mkdtemp(prefix="mutcheck_"), "engine_backup.py")
    shutil.copy2(TARGET, backup)

    results = []
    try:
        for name, old, new in MUTATIONS:
            if old not in original:
                results.append((name, "NO APLICABLE (ancla no encontrada)", []))
                continue
            with open(TARGET, "w", encoding="utf-8") as handle:
                handle.write(original.replace(old, new, 1))
            code, failed, out = _run_tests()
            results.append((name, "DETECTADA" if failed else "NO DETECTADA", failed))
            with open(TARGET, "w", encoding="utf-8") as handle:
                handle.write(original)
    finally:
        shutil.copy2(backup, TARGET)
        with open(TARGET, "r", encoding="utf-8") as handle:
            assert handle.read() == original, "No se pudo restaurar el fichero original"

    print("=" * 78)
    print("COMPROBACION POR MUTACION - test_goal_adaptation_pattern_restart_verification.py")
    print("=" * 78)
    undetected = []
    for name, verdict, failed in results:
        print(f"- {name}: {verdict}")
        for test in failed:
            print(f"    fallo detectado en: {test}")
        if verdict == "NO DETECTADA":
            undetected.append(name)
    print("-" * 78)
    if undetected:
        print(f"MUTACIONES NO DETECTADAS: {len(undetected)}")
        for name in undetected:
            print(f"    - {name}")
        return 1
    print("TODAS LAS MUTACIONES APLICABLES HAN SIDO DETECTADAS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
