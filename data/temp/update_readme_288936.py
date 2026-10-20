# -*- coding: utf-8 -*-
"""Actualiza el mapa documental de README.md con la correccion de 2.8.8.9.3.6."""
path = 'README.md'
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


rep("""  - Verificaci\u00f3n end-to-end (2.8.8.9.3.5): `tests/test_goal_adaptation_strategy_restart_verification.py` (6 tests) comprueba que la estrategia recuperada conserva el conjunto can\u00f3nico completo de la forma A (12 campos, no solo los DATOS CR\u00cdTICOS), que las estructuras anidadas (`context`, `metrics`, `applied_rules`) sobreviven intactas, que sigue siendo consumible por `get_available_strategies()` y `generate_strategy_candidates()`, y que un segundo reinicio no duplica ni degrada la entrada""",
    """  - Verificaci\u00f3n end-to-end (2.8.8.9.3.5): `tests/test_goal_adaptation_strategy_restart_verification.py` (6 tests) comprueba que la estrategia recuperada conserva el conjunto can\u00f3nico completo de la forma A (12 campos, no solo los DATOS CR\u00cdTICOS), que las estructuras anidadas (`context`, `metrics`, `applied_rules`) sobreviven intactas, que sigue siendo consumible por `get_available_strategies()` y `generate_strategy_candidates()`, y que un segundo reinicio no duplica ni degrada la entrada
  - Correcci\u00f3n del guardado (2.8.8.9.3.6): `_save_goal_adaptation_learning_results()` identifica las estrategias aprendidas por los campos identificadores y de evidencia (`strategy_id`, `confidence`, `success_rate`, `last_updated`) y normaliza `failure_count` a 0 cuando no existe, en vez de descartar la entrada por faltar ese contador; el registro persistido sigue cumpliendo el item 4 completo de DATOS CR\u00cdTICOS (los 5 campos presentes) y las formas B (registro de aplicaci\u00f3n) y C (resultado de adaptaci\u00f3n) siguen sin persistirse
  - Verificaci\u00f3n de la correcci\u00f3n (2.8.8.9.3.6): `tests/test_goal_adaptation_persistence_simple.py` 6/6 PASSED (antes 3 FAILED: `test_guardar_aprendizaje_crea_archivo`, `test_cargar_datos_persistidos`, `test_integridad_serializacion`) y `tests/test_goal_adaptation_learned_strategy_persistence.py` 6/6 PASSED (sin regresi\u00f3n del contrato 2.8.8.9.3.2)""",
    "mapa documental de persistencia")

out = norm.replace('\n', '\r\n').encode('utf-8')
open(path, 'wb').write(out)
print("ESCRITO: %d bytes (antes %d)" % (len(out), len(raw)))
