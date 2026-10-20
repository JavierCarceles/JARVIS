# -*- coding: utf-8 -*-
"""Actualiza el bloque de estado y el cierre de 2.8.8.9.2.6 en prompt_mejoraActual.txt."""
import io

path = 'prompt_mejoraActual.txt'
raw = open(path, 'rb').read()
text = raw.decode('utf-8')
assert '\r\n' in text, 'Se esperaba CRLF'
norm = text.replace('\r\n', '\n')


def rep(old, new, label):
    global norm
    count = norm.count(old)
    assert count == 1, "%s: %d coincidencias" % (label, count)
    norm = norm.replace(old, new, 1)
    print("OK:", label)


# 1) Bloque de estado persistente
rep("""CURRENT_PHASE: 2.8.8
CURRENT_WORK_UNIT: 2.8.8.9.2.6
LAST_COMPLETED_UNIT: 2.8.8.9.2.5""",
    """CURRENT_PHASE: 2.8.8
CURRENT_WORK_UNIT: 2.8.8.9.3.1
LAST_COMPLETED_UNIT: 2.8.8.9.2.6""", "estado persistente")

# 2) Marcadores del arbol de 2.8.8.9.2
rep("2.8.8.9.2 — PERSISTENCIA DE FEEDBACK\n",
    "2.8.8.9.2 — PERSISTENCIA DE FEEDBACK [IMPLEMENTADA]\n", "subfase 2.8.8.9.2")

rep("2.8.8.9.2.2 — CREAR TEST DE PERSISTENCIA DE FEEDBACK\n",
    "2.8.8.9.2.2 — CREAR TEST DE PERSISTENCIA DE FEEDBACK [IMPLEMENTADA]\n", "hoja .2")

rep("2.8.8.9.2.3 — IMPLEMENTAR GUARDADO DE FEEDBACK\n",
    "2.8.8.9.2.3 — IMPLEMENTAR GUARDADO DE FEEDBACK [IMPLEMENTADA]\n", "hoja .3")

rep("2.8.8.9.2.4 — IMPLEMENTAR CARGA DE FEEDBACK\n",
    "2.8.8.9.2.4 — IMPLEMENTAR CARGA DE FEEDBACK [IMPLEMENTADA]\n", "hoja .4")

rep("2.8.8.9.2.5 — VERIFICAR FEEDBACK TRAS REINICIO\n",
    "2.8.8.9.2.5 — VERIFICAR FEEDBACK TRAS REINICIO [IMPLEMENTADA]\n", "hoja .5")

rep("""2.8.8.9.2.6 — CORREGIR FALLO DE FEEDBACK
- Corregir únicamente fallos detectados por los tests de esta subhoja.""",
    """2.8.8.9.2.6 — CORREGIR FALLO DE FEEDBACK [IMPLEMENTADA]
- Corregir únicamente fallos detectados por los tests de esta subhoja.""", "hoja .6")

# 3) Bloque de cierre final
rep("SIGUIENTE UNIDAD: 2.8.8.9.2.6 — IMPLEMENTAR CARGA DE PATRÓN",
    """**2.8.8.9.2.6 — IMPLEMENTADA**
- ✅ Fallo real de feedback identificado y corregido (no era carga de patrón)
- ✅ Causa raíz: `_load_goal_adaptation_learning_results()` insertaba el índice plano
  persistido (`strategy_id -> entrada`) dentro de `knowledge_base["adaptation_strategies"]`,
  que en el motor sigue el contrato `contexto -> lista` (2.8.5/2.8.6)
- ✅ Consecuencia real: mapa corrupto (10 claves mezcladas) y `get_available_strategies()`
  devolvía `[]` -> la estrategia persistida NO se recuperaba tras el reinicio
- ✅ Guardado: `_save_goal_adaptation_learning_results()` persiste ahora el índice plano
  vía `_flatten_strategy_map()`
- ✅ Carga: `_project_strategies_by_context()` proyecta el índice plano sobre el mapa por
  contexto; `_merge_strategies_by_context()` restaura el contexto exacto desde
  `updated_strategies` de cada resultado de aprendizaje
- ✅ `_update_adaptive_strategies()` deja de descartar estrategias sin `strategy_id`
- ✅ Test nuevo `tests/test_goal_adaptation_strategy_persistence.py` (6 tests) — PASADO;
  FALLA en HEAD (verificado en worktree aislado), por lo que captura el fallo real
- ✅ Tests de la subhoja (4 ficheros) — 23 PASSED
- ✅ No-regresión (14 ficheros, 139 tests): 34 fallos preexistentes en HEAD -> 34 idénticos
  (0 regresiones, 0 correcciones colaterales)
- ✅ `main.py` importa OK
- ✅ Comportamiento real end-to-end verificado: capture -> learning -> reinicio ->
  estrategia recuperada en su contexto, disponible y ofrecida como candidata
- ✅ README actualizado con los métodos de persistencia de Goal

DISCREPANCIA REGISTRADA (no resuelta por intuición, regla 11)
- El árbol de la hoja 2.8.8.9.2.6 dice "CORREGIR FALLO DE FEEDBACK"; el cierre anterior
  del prompt decía "IMPLEMENTAR CARGA DE PATRÓN". Se siguió el árbol (fuente estructural)
  porque era la única lectura con trabajo verificable: existe un fallo real detectado por
  los tests de esta subhoja, y "carga de patrón" no es una hoja de 2.8.8.9.2.
- La carga de patrones pertenece a 2.8.8.9.4.4 (PERSISTENCIA DE PATRONES), que sigue PENDIENTE.
- Nota: 2.8.8.9 está marcada [IMPLEMENTADA] en el árbol pero conserva hojas pendientes
  (2.8.8.9.3 a 2.8.8.9.15). Discrepancia preexistente, conservada sin alterar.

SIGUIENTE UNIDAD: 2.8.8.9.3.1 — IDENTIFICAR ESTRUCTURA DE ESTRATEGIA""", "cierre final")

out = norm.replace('\n', '\r\n').encode('utf-8')
open(path, 'wb').write(out)
print("ESCRITO: %d bytes" % len(out))
