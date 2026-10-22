#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tercera tanda: filas corruptas en secciones LIST de la base y vaciado
por el fichero de feedback."""

import json
import os
import sys
import tempfile

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402

KB = "contextual_knowledge_base.json"
FB = "goal_adaptation_feedback.json"
LR = "goal_adaptation_learning_results.json"

FB_SANA = {
    "adaptation_id": "fb_ok", "success": True, "adaptation_context": {},
    "execution_result": {}, "verification_result": {}, "improvement_analysis": {},
    "timestamp": "2024-01-01T00:00:00",
}
FB_CORRUPTA = {"adaptation_id": 999, "success": "no booleano", "adaptation_context": {}}


def _motor(ficheros):
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    for nombre, contenido in ficheros.items():
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as h:
            h.write(contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False))
    return ContextualAdaptationEngine(data_dir=data_dir)


def _titulo(t):
    print("=" * 72)
    print(t)


def f1_fb_todas_corruptas():
    """El FB tiene UNA fila corrupta y la KB tiene feedback VALIDO: la carga
    del FB vacia el feedback de la KB."""
    _titulo("F1: FB con una sola fila corrupta + KB con feedback sano")
    motor = _motor({
        KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_SANA, adaptation_id="fb_kb")]}},
        FB: {"goal_adaptation_feedback": [dict(FB_CORRUPTA)], "adaptation_history": []},
    })
    ids = [f.get("adaptation_id") for f in motor.knowledge_base.get("goal_adaptation_feedback", [])]
    print("  adaptation_id en el estado:", ids)
    print("  fb_kb (sano en la KB) sobrevive:", "fb_kb" in ids)


def f2_fb_ausente():
    """El FB NO existe: la KB conserva su feedback."""
    _titulo("F2: FB ausente + KB con feedback sano")
    motor = _motor({KB: {"version": "2.0", "data": {"goal_adaptation_feedback": [dict(FB_SANA, adaptation_id="fb_kb")]}}})
    ids = [f.get("adaptation_id") for f in motor.knowledge_base.get("goal_adaptation_feedback", [])]
    print("  adaptation_id en el estado:", ids)
    print("  fb_kb sobrevive:", "fb_kb" in ids)


def f3_fila_corrupta_en_seccion_lista_de_la_kb():
    """La KB tiene una seccion LIST con una fila CORRUPTA: la seccion se
    acepta EN BLOQUE (no se validan las filas) y la fila corrupta llega al
    estado y se vuelve a PERSISTIR."""
    _titulo("F3: seccion LIST de la KB con una fila corrupta")
    motor = _motor({KB: {"version": "2.0", "data": {
        "goal_adaptation_feedback": [dict(FB_SANA, adaptation_id="fb_kb"), dict(FB_CORRUPTA)],
    }}})
    ids = [f.get("adaptation_id") for f in motor.knowledge_base.get("goal_adaptation_feedback", [])]
    print("  adaptation_id en el estado:", ids)
    print("  la fila corrupta (999) llega al estado:", 999 in ids)
    motor.save_knowledge_base()
    with open(os.path.join(motor.data_dir, KB), "r", encoding="utf-8") as h:
        escrito = json.load(h)
    ids2 = [f.get("adaptation_id") for f in escrito["data"]["goal_adaptation_feedback"]]
    print("  adaptation_id PERSISTIDO:", ids2)
    print("  la corrupcion se propaga al disco:", 999 in ids2)


def f4_lr_todas_corruptas():
    """El LR tiene UNA fila corrupta y la KB tiene learning_results VALIDOS."""
    _titulo("F4: LR con una sola fila corrupta + KB con learning_results sanos")
    motor = _motor({
        KB: {"version": "2.0", "data": {"learning_results": [
            {"adaptation_id": "lr_kb", "learned_patterns": [], "updated_strategies": {}}]}},
        LR: {"learning_results": [{"adaptation_id": 999, "learned_patterns": "no es lista"}],
             "adaptation_strategies": {}},
    })
    print("  learning_results:", json.dumps(motor.knowledge_base.get("learning_results"), ensure_ascii=False, default=str)[:200])


def f5_kb_seccion_lista_como_dict_no_toca_las_hermanas():
    """El caso D1: una seccion LIST de la KB llega como DICCIONARIO. Se
    comprueba si las secciones HERMANAS validas sobreviven."""
    _titulo("F5: seccion LIST de la KB como DICCIONARIO (D1)")
    motor = _motor({KB: {"version": "2.0", "data": {
        "learning_results": {"no": "es una lista"},
        "context_patterns": {"production": [{"patron": "sano"}]},
    }}})
    print("  context_patterns:", json.dumps(motor.knowledge_base.get("context_patterns"), ensure_ascii=False, default=str)[:150])
    print("  el patron sano de 'production' sobrevive:",
          bool(motor.knowledge_base.get("context_patterns", {}).get("production")))
    print("  unidades cargadas KB:", motor._unidades_cargadas.get("knowledge_base"))


if __name__ == "__main__":
    f1_fb_todas_corruptas()
    f2_fb_ausente()
    f3_fila_corrupta_en_seccion_lista_de_la_kb()
    f4_lr_todas_corruptas()
    f5_kb_seccion_lista_como_dict_no_toca_las_hermanas()
