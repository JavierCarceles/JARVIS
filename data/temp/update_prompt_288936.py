# -*- coding: utf-8 -*-
"""Actualiza el bloque de estado, el arbol y el cierre de 2.8.8.9.3.6 en prompt_mejoraActual.txt."""
import os

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
CURRENT_WORK_UNIT: 2.8.8.9.3.6
CURRENT_WORK_STATUS: EN PROCESO
LAST_COMPLETED_UNIT: 2.8.8.9.3.5

# COMPLETADO: 2.8.8.9.3.5 - Verificación de estrategia tras reinicio
# Fecha: 2026-10-20
# Archivo modificado: tests/test_goal_adaptation_strategy_restart_verification.py (nuevo), README.md, prompt_mejoraActual.txt
# Tests: tests/test_goal_adaptation_strategy_restart_verification.py (6/6 pasados)
# Resultado: La estrategia recuperada conserva el conjunto canónico completo y sigue siendo consumible
# Problema resuelto: Brecha de duplicación de 2.8.8.9.3.1 verificada como cerrada (no hubo código roto que corregir)""",
    """CURRENT_PHASE: 2.8.8
CURRENT_WORK_UNIT: 2.8.8.9.4.1
CURRENT_WORK_STATUS: PENDIENTE
LAST_COMPLETED_UNIT: 2.8.8.9.3.6

# COMPLETADO: 2.8.8.9.3.6 - Corrección de fallo de estrategia
# Fecha: 2026-10-20
# Archivo modificado: src/utils/contextual_adaptation_engine.py, README.md, prompt_mejoraActual.txt
# Tests: tests/test_goal_adaptation_persistence_simple.py (6/6), tests/test_goal_adaptation_learned_strategy_persistence.py (6/6)
# Resultado: La estrategia aprendida ya no se descarta por no tener contador de fallos
# Problema resuelto: El guardado trataba failure_count como campo identificador y descartaba estrategias aprendidas válidas""",
    "estado persistente")

# 2) Marcadores del arbol de 2.8.8.9.3
rep("2.8.8.9.3 — PERSISTENCIA DE ESTRATEGIAS\n",
    "2.8.8.9.3 — PERSISTENCIA DE ESTRATEGIAS [IMPLEMENTADA]\n", "subfase 2.8.8.9.3")

rep("""2.8.8.9.3.2 — CREAR TEST DE PERSISTENCIA DE ESTRATEGIA
- Crear únicamente el test correspondiente.""",
    """2.8.8.9.3.2 — CREAR TEST DE PERSISTENCIA DE ESTRATEGIA ✅
- Crear únicamente el test correspondiente.
- ✅ Test `tests/test_goal_adaptation_learned_strategy_persistence.py` (6 tests) — 6 PASSED""",
    "hoja .2")

rep("""2.8.8.9.3.3 — IMPLEMENTAR GUARDADO DE ESTRATEGIA
- Persistir únicamente estrategias aprendidas.""",
    """2.8.8.9.3.3 — IMPLEMENTAR GUARDADO DE ESTRATEGIA ✅
- Persistir únicamente estrategias aprendidas.
- ✅ Índice plano `strategy_id -> entrada` escrito desde `_save_goal_adaptation_learning_results()`,
  conservando el contexto de aprendizaje de cada estrategia""",
    "hoja .3")

rep("""2.8.8.9.3.6 — CORREGIR FALLO DE ESTRATEGIA
- Corregir únicamente fallos de esta subhoja.""",
    """2.8.8.9.3.6 — CORREGIR FALLO DE ESTRATEGIA ✅
- Corregir únicamente fallos de esta subhoja.
- ✅ Causa raíz en el CÓDIGO: el guardado exigía los 5 DATOS CRÍTICOS en la entrada, tratando
  `failure_count` (un contador) como campo identificador, y descartaba estrategias aprendidas válidas
- ✅ Corrección: el guardado filtra por los campos identificadores y de evidencia (`strategy_id`,
  `confidence`, `success_rate`, `last_updated`) y normaliza `failure_count` a 0; la entrada
  persistida sigue cumpliendo el item 4 completo (los 5 DATOS CRÍTICOS presentes)
- ✅ `tests/test_goal_adaptation_persistence_simple.py`: 6/6 PASSED (antes 3 FAILED)
- ✅ Contrato 2.8.8.9.3.2 sin regresión: `tests/test_goal_adaptation_learned_strategy_persistence.py`
  6/6 PASSED (las formas B y C siguen sin persistirse)""",
    "hoja .6")

# 3) Cierre de la hoja 2.8.8.9.3.6
rep("""FALLOS PREEXISTENTES REGISTRADOS (no resueltos por intuición, regla 11)
- 3 de los 13 pertenecen a esta subhoja (2.8.8.9.3) y son el objeto de 2.8.8.9.3.6:""",
    """**2.8.8.9.3.6 — IMPLEMENTADA**
- ✅ Objetivo: corregir los fallos de la subhoja 2.8.8.9.3 (persistencia de estrategias aprendidas)
- ✅ Fallo real corregido: `_save_goal_adaptation_learning_results()` descartaba del índice plano
  cualquier estrategia aprendida a la que le faltara `failure_count`, porque el filtro exigía los
  5 DATOS CRÍTICOS (item 4 de 2.8.8.9.2.1) como si `failure_count` fuera un campo identificador
- ✅ Consecuencia real: la estrategia aprendida no se persistía (`adaptation_strategies` = `{}` en
  disco) y se perdía en el reinicio; lo detectaban 3 tests de
  `tests/test_goal_adaptation_persistence_simple.py`
- ✅ Corrección aplicada (código de producción): el guardado filtra por los campos identificadores y
  de evidencia (`strategy_id`, `confidence`, `success_rate`, `last_updated`) y normaliza
  `failure_count` a 0 cuando no existe; la entrada persistida sigue cumpliendo el item 4 completo
  (los 5 DATOS CRÍTICOS presentes), como exige
  `test_la_estrategia_aprendida_conserva_sus_datos_criticos`
- ✅ Sin regresión del contrato 2.8.8.9.3.2: las formas B (registro de aplicación) y C (resultado de
  adaptación) siguen SIN persistirse (`tests/test_goal_adaptation_learned_strategy_persistence.py`,
  6/6 PASSED)
- ✅ No se modificó ningún test: el test preexistente ya describía el comportamiento correcto
  ("las estrategias deben persistirse")
- ✅ Tests de la subhoja: `tests/test_goal_adaptation_persistence_simple.py` 6/6 PASSED
  (antes 3 FAILED) + `tests/test_goal_adaptation_learned_strategy_persistence.py` 6/6 PASSED
- ✅ No-regresión (15 ficheros de goal/adaptación, 67 tests): 11 failed / 56 passed antes de la
  corrección -> 8 failed / 59 passed después. Los 8 restantes son idénticos antes y después
  (baseline obtenido revirtiendo la corrección en el propio fichero y reejecutando el mismo lote)
- ✅ `data/goal_adaptation_learning_results.json` verificado idéntico a `git show HEAD:` (no se
  perdieron datos reales)
- ✅ README.md actualizado con la corrección del guardado

DISCREPANCIA REGISTRADA (no resuelta por intuición, regla 11)
- El cierre de 2.8.8.9.3.5 atribuyó la causa raíz de estos 3 fallos al TEST (una "pseudo-estrategia"
  sin `failure_count`), lo que implicaba corregir el test. Se corrigió el CÓDIGO en su lugar, con
  evidencia de runtime:
  - El propio motor trata `failure_count` como contador opcional: `_update_adaptive_strategies()` lo
    incrementa con `strategy.get("failure_count", 0) + 1`, es decir, su ausencia significa 0 fallos
  - La migración de datos heredados (`_update_adaptive_strategies()`, l. 2135-2143) admite entradas
    sin `failure_count`, que el filtro anterior descartaba al guardar (pérdida real en el reinicio)
  - El contrato verificado por `test_la_estrategia_aprendida_conserva_sus_datos_criticos` exige que la
    entrada RECUPERADA tenga los 5 campos; normalizar `failure_count` a 0 cumple ese requisito,
    mientras que descartar la entrada lo incumple
  - El item 4 dice que esos 5 campos "DEBEN PERSISTIR" (el registro persistido debe contenerlos), no
    que la entrada en memoria deba tenerlos para ser reconocida como estrategia aprendida
  - Consecuencia de la decisión: el filtro de guardado ya no exige `failure_count` en la entrada en
    memoria; el registro persistido siempre lo contiene
- El árbol no marcaba 2.8.8.9.3.2 ni 2.8.8.9.3.3 como implementadas (discrepancia registrada en el
  cierre de 2.8.8.9.3.5). Marcadas en esta hoja: ambas están verificadas por
  `tests/test_goal_adaptation_learned_strategy_persistence.py` (6/6) y por el filtrado del guardado.
  Con ello queda completa la subhoja 2.8.8.9.3 (las 6 hojas cerradas).
- Brecha preexistente NO resuelta en esta hoja (fuera del alcance de 2.8.8.9.3.6, que corrige
  "únicamente fallos de esta subhoja"): el umbral mínimo de confianza >= 0.7 del item 4 y la regla
  "DATOS QUE NO DEBEN PERSISTIR: confianza < 0.7" no se comprueban en
  `_save_goal_adaptation_learning_results()` (el filtro no mira `confidence`). Registrado para una
  hoja posterior; no se ha tocado porque no hay test que lo detecte en esta subhoja.

FALLOS PREEXISTENTES REGISTRADOS (no resueltos por intuición, regla 11)
- 3 de los 13 pertenecían a esta subhoja (2.8.8.9.3) y eran el objeto de 2.8.8.9.3.6:""",
    "cierre 2.8.8.9.3.6")

rep("""  - NO se ha tocado ni el test ni el código en esta hoja: corregirlos es el objeto de 2.8.8.9.3.6""",
    """  - NO se ha tocado ni el test ni el código en esta hoja: corregirlos es el objeto de 2.8.8.9.3.6
  - ✅ RESUELTOS en 2.8.8.9.3.6 (6/6 PASSED). La causa raíz se localizó en el CÓDIGO y no en el test:
    `failure_count` es un contador, no un campo identificador (ver cierre de 2.8.8.9.3.6)""",
    "fallos preexistentes marcados como resueltos")

# 4) Estado final y siguiente unidad
rep("""✅ Estado final: 2.8.8.9.3.5 IMPLEMENTADA (verificación end-to-end, sin código roto que corregir)

SIGUIENTE UNIDAD: 2.8.8.9.3.6 — CORREGIR FALLO DE ESTRATEGIA""",
    """✅ Estado final: 2.8.8.9.3.6 IMPLEMENTADA (corrección del guardado de estrategias; subhoja
2.8.8.9.3 completa, sus 6 hojas cerradas)

SIGUIENTE UNIDAD: 2.8.8.9.4.1 — IDENTIFICAR ESTRUCTURA DE PATRÓN""",
    "estado final")

out = norm.replace('\n', '\r\n').encode('utf-8')
open(path, 'wb').write(out)
print("ESCRITO: %d bytes (antes %d)" % (len(out), len(raw)))
