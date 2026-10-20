# -*- coding: utf-8 -*-
"""Limpia los artefactos de TEST de los ficheros de persistencia de Goal (2.8.8.9.4.6).

Elimina SOLO las entradas identificadas como datos de test (prefijo `test_` en
`adaptation_id`, `strategy_id` o `pattern_id`). No se toca ningun registro real.
Si no queda nada, el fichero se deja en el payload canonico que escribe el motor.
"""
import json
import os
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data')
TEST_PREFIX = 'test_'


def is_test(value):
    return isinstance(value, str) and value.startswith(TEST_PREFIX)


def clean_feedback():
    path = os.path.join(DATA, 'goal_adaptation_feedback.json')
    with open(path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    records = payload.get('goal_adaptation_feedback') or []
    kept_records = [r for r in records if not (isinstance(r, dict) and is_test(r.get('adaptation_id')))]
    history = payload.get('adaptation_history') or []
    kept_history = [h for h in history if not (isinstance(h, dict) and is_test(h.get('adaptation_id')))]
    removed = (len(records) - len(kept_records)) + (len(history) - len(kept_history))
    payload['goal_adaptation_feedback'] = kept_records
    payload['adaptation_history'] = kept_history
    payload['last_updated'] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print('feedback: %d registros y %d entradas de historial eliminados; quedan %d y %d'
          % (len(records) - len(kept_records), len(history) - len(kept_history),
             len(kept_records), len(kept_history)))
    return removed


def clean_learning():
    path = os.path.join(DATA, 'goal_adaptation_learning_results.json')
    with open(path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    rows = payload.get('learning_results') or []
    kept_rows = []
    removed = 0
    orphaned_strategy_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            kept_rows.append(row)
            continue
        if is_test(row.get('adaptation_id')):
            removed += 1
            # Las estrategias que solo existian por esa fila de test son
            # igualmente datos de test: se arrastran con la fila. El vinculo
            # es el `strategy_id` declarado en `updated_strategies` (o las
            # claves, si `updated_strategies` viene en forma de mapa).
            updated = row.get('updated_strategies') or {}
            if isinstance(updated, dict):
                declared = updated.get('strategy_id')
                if isinstance(declared, str):
                    orphaned_strategy_ids.add(declared)
                orphaned_strategy_ids.update(str(k) for k in updated)
            continue
        kept_rows.append(row)
    strategies = payload.get('adaptation_strategies') or {}
    kept_strategies = {k: v for k, v in strategies.items()
                       if not is_test(k) and str(k) not in orphaned_strategy_ids}
    removed += len(strategies) - len(kept_strategies)
    payload['learning_results'] = kept_rows
    payload['adaptation_strategies'] = kept_strategies
    payload['last_updated'] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print('learning_results: %d filas y %d estrategias eliminadas; quedan %d y %d'
          % (len(rows) - len(kept_rows), len(strategies) - len(kept_strategies),
             len(kept_rows), len(kept_strategies)))
    return removed


if __name__ == '__main__':
    total = clean_feedback() + clean_learning()
    print('TOTAL de artefactos de test eliminados: %d' % total)
