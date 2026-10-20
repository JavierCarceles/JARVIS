#!/usr/bin/env python3
"""
Test de persistencia de patrones de aprendizaje (2.8.8.9.4.2).

Fija el contrato que las hojas 2.8.8.9.4.3 (guardado), 2.8.8.9.4.4 (carga),
2.8.8.9.4.5 (verificacion tras reinicio) y 2.8.8.9.4.6 (correccion) deben
cumplir. Esta hoja (2.8.8.9.4.2) crea unicamente el test; la implementacion
corresponde a las hojas siguientes.

FUENTES DEL CONTRATO
- Roadmap 2.8.8.9.2.1, DATOS CRITICOS item 5:
  "PATRONES DE APRENDIZAJE VALIDADOS (`learning_results`): pattern_id,
  pattern_type, context, metrics, confidence >= 0.7. Requiere minimo 3
  observaciones similares".
- Roadmap 2.8.8.9.2.1, DATOS QUE NO DEBEN PERSISTIR:
  "Patrones no validados (confianza < 0.7)".
- Roadmap 2.8.8.9.4.2: el umbral a usar es `self.config["confidence_threshold"]`
  (0.7), ya presente en el motor.

CONTENEDOR CANONICO (verificado en 2.8.8.9.4.1)
`knowledge_base["learning_results"][i]["learned_patterns"]`, persistido en
`goal_adaptation_learning_results.json` y recuperado por
`_load_goal_adaptation_learning_results()`.

BRECHAS REALES QUE ESTE TEST FIJA (verificadas en runtime en 2.8.8.9.4.1)
- Brecha 1 - SIN FILTRO DE VALIDACION: `_save_goal_adaptation_learning_results()`
  escribe `learning_results` verbatim, sin filtrar por `confidence >= 0.7`.
  Verificado: un patron de fallo (confidence 0.64) queda escrito en disco.
- Brecha 2 - SIN "MINIMO 3 OBSERVACIONES SIMILARES": no existe ningun contador
  de soporte. Verificado: una unica observacion ya se persiste. Ademas el
  `pattern_id` actual no es estable (`f"pattern_{n}_{int(time.time()*1000)}"`),
  por lo que no puede usarse para agrupar observaciones: la agrupacion debe
  apoyarse en la identidad real del patron (`pattern_type` + `context`).

AISLAMIENTO
El motor se instancia siempre con `data_dir` temporal
(`ContextualAdaptationEngine(data_dir=str(tmp_path))`), por lo que el test no
lee ni escribe sobre `data/` de produccion. El test
`test_el_test_no_escribe_en_los_ficheros_de_persistencia_de_produccion` lo
verifica de forma explicita.
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextType, ContextualAdaptationEngine

# Item 5 de DATOS CRITICOS: un patron validado requiere "minimo 3
# observaciones similares".
MIN_SIMILAR_OBSERVATIONS = 3

# Item 5 de DATOS CRITICOS: campos que debe conservar todo patron persistido.
CRITICAL_PATTERN_FIELDS = ("pattern_id", "pattern_type", "context", "metrics", "confidence")

# Ficheros de persistencia de Goal en el `data/` de produccion: el test no
# debe tocarlos nunca (contrato de 2.8.8.9.4.1).
PRODUCTION_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))
PRODUCTION_GOAL_FILES = (
    "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results.json",
)


@pytest.fixture
def engine(tmp_path):
    """Motor de adaptacion con persistencia aislada."""
    return ContextualAdaptationEngine(data_dir=str(tmp_path))


def _feedback(adaptation_id, success=True, verified=True, impact=0.5,
              context_type=ContextType.PRODUCTION.value, goal_type="navigation",
              response_time=1.2, accuracy=0.97):
    """Datos de feedback de adaptacion de Goal de ejemplo.

    El `adaptation_context` se mantiene identico entre observaciones: es la
    identidad del contexto del patron. Solo varian las metricas de ejecucion,
    que son las que distinguen una observacion de otra.
    """
    return {
        "adaptation_id": adaptation_id,
        "original_goal_id": f"goal_original_{adaptation_id}",
        "adapted_goal_id": f"goal_adapted_{adaptation_id}",
        "adaptation_context": {
            "goal_type": goal_type,
            "context_type": context_type,
            "system_resources": {"cpu": 0.5, "memory": 0.3},
            "expected_metrics": {"response_time": 2.0, "accuracy": 0.95},
        },
        "execution_result": {
            "success": success,
            "performance_metrics": {"response_time": response_time, "accuracy": accuracy},
        },
        "verification_result": {"verified": verified, "impact_score": impact},
    }


def _learn(engine, count, prefix="obs", **kwargs):
    """Ejecutar `count` ciclos de aprendizaje y devolver los patrones producidos.

    Cada ciclo es una observacion independiente (feedback capturado + bucle de
    aprendizaje), con metricas de ejecucion ligeramente distintas.
    """
    produced = []
    for index in range(1, count + 1):
        data = _feedback(
            f"{prefix}_{index}",
            response_time=1.0 + index * 0.1,
            accuracy=0.90 + index * 0.01,
            **kwargs,
        )
        feedback_result = engine._capture_goal_adaptation_feedback(data)
        assert feedback_result["success"] is True, feedback_result.get("error_message")
        learning_result = engine._execute_goal_adaptation_learning_loop(feedback_result)
        assert learning_result["success"] is True, learning_result.get("error_message")
        produced.extend(learning_result["learned_patterns"])
    return produced


def _persisted_payload(tmp_path):
    """Leer el payload persistido de resultados de aprendizaje."""
    path = os.path.join(str(tmp_path), "goal_adaptation_learning_results.json")
    assert os.path.isfile(path), "El motor debe persistir los resultados de aprendizaje"
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _persisted_patterns(tmp_path):
    """Devolver todos los patrones presentes en el contenedor canonico persistido."""
    payload = _persisted_payload(tmp_path)
    patterns = []
    for row in payload.get("learning_results", []) or []:
        if not isinstance(row, dict):
            continue
        for pattern in row.get("learned_patterns", []) or []:
            if isinstance(pattern, dict):
                patterns.append(pattern)
    return patterns


def _production_signature():
    """Huella (existencia, mtime, tamano) de los ficheros de Goal de produccion."""
    signature = {}
    for name in PRODUCTION_GOAL_FILES:
        path = os.path.join(PRODUCTION_DATA_DIR, name)
        if not os.path.isfile(path):
            signature[name] = None
            continue
        stat = os.stat(path)
        signature[name] = (stat.st_mtime_ns, stat.st_size)
    return signature


def test_una_observacion_aislada_no_se_persiste(engine, tmp_path):
    """Una sola observacion no debe persistir ningun patron.

    El item 5 de DATOS CRITICOS exige "minimo 3 observaciones similares" para
    dar por validado un patron.
    """
    _learn(engine, 1)

    patterns = _persisted_patterns(tmp_path)
    assert patterns == [], (
        f"Una observacion aislada no debe persistir patrones; se persistieron "
        f"{len(patterns)}: {[p.get('pattern_id') for p in patterns]}"
    )


def test_un_patron_validado_tras_tres_observaciones_similares_se_persiste(engine, tmp_path):
    """Con tres observaciones similares el patron debe persistirse."""
    produced = _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    assert produced, "El bucle de aprendizaje debe producir patrones"

    patterns = _persisted_patterns(tmp_path)
    assert patterns, (
        f"Tras {MIN_SIMILAR_OBSERVATIONS} observaciones similares el patron "
        "validado debe persistirse"
    )
    threshold = engine.config["confidence_threshold"]
    assert any(
        pattern.get("pattern_type") == "goal_adaptation_success"
        and float(pattern.get("confidence", 0.)) >= threshold
        for pattern in patterns
    ), (
        f"El patron persistido debe conservar su tipo y superar el umbral "
        f"{threshold}; se persistieron {patterns}"
    )


def test_un_patron_por_debajo_del_umbral_de_confianza_no_se_persiste(engine, tmp_path):
    """Un patron con confianza inferior al umbral no debe persistirse.

    Es la regla "DATOS QUE NO DEBEN PERSISTIR: Patrones no validados
    (confianza < 0.7)". El patron de fallo se produce con `impact_score` 0.1,
    lo que baja su confianza a 0.64 (0.8 x 0.8).
    """
    threshold = engine.config["confidence_threshold"]
    produced = _learn(engine, MIN_SIMILAR_OBSERVATIONS, prefix="low",
                      success=False, verified=False, impact=0.1)
    assert produced, "El bucle de aprendizaje debe producir patrones"
    assert all(float(p.get("confidence", 0.)) < threshold for p in produced), (
        f"El patron de prueba debe quedar por debajo del umbral {threshold}; "
        f"confianzas {[p.get('confidence') for p in produced]}"
    )

    patterns = _persisted_patterns(tmp_path)
    assert patterns == [], (
        f"Los patrones con confianza < {threshold} no deben persistirse; se "
        f"persistieron {len(patterns)}: {[p.get('confidence') for p in patterns]}"
    )


def test_ningun_patron_persistido_esta_por_debajo_del_umbral(engine, tmp_path):
    """Todo patron persistido debe superar el umbral de confianza configurado."""
    threshold = engine.config["confidence_threshold"]
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    _learn(engine, MIN_SIMILAR_OBSERVATIONS, prefix="low",
           success=False, verified=False, impact=0.1)

    invalid = [
        pattern for pattern in _persisted_patterns(tmp_path)
        if float(pattern.get("confidence", 0.)) < threshold
    ]
    assert invalid == [], (
        f"Hay patrones persistidos por debajo del umbral {threshold}: "
        f"{[(p.get('pattern_id'), p.get('confidence')) for p in invalid]}"
    )


def test_el_umbral_aplicado_es_el_configurado_en_el_motor(engine, tmp_path):
    """El umbral de confianza debe ser el configurado, no uno fijo en el codigo.

    Con `confidence_threshold` 0.95, el patron de exito (confianza 0.9) queda
    por debajo del umbral y no debe persistirse.
    """
    config_path = os.path.join(str(tmp_path), "engine_config.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump({"confidence_threshold": 0.95}, handle)

    tuned = ContextualAdaptationEngine(config_path=config_path, data_dir=str(tmp_path))
    assert tuned.config["confidence_threshold"] == 0.95

    produced = _learn(tuned, MIN_SIMILAR_OBSERVATIONS)
    assert produced, "El bucle de aprendizaje debe producir patrones"
    assert all(float(p.get("confidence", 0.)) < 0.95 for p in produced), (
        f"El patron de prueba debe quedar por debajo de 0.95; "
        f"confianzas {[p.get('confidence') for p in produced]}"
    )

    patterns = _persisted_patterns(tmp_path)
    assert patterns == [], (
        f"Con `confidence_threshold` 0.95 no debe persistirse ningun patron; "
        f"se persistieron {len(patterns)}"
    )


def test_observaciones_de_contextos_distintos_no_se_agrupan(engine, tmp_path):
    """Observaciones de contextos distintos no son observaciones similares.

    Dos observaciones en "production" y dos en "development" no alcanzan el
    minimo de 3 observaciones similares para ningun patron.
    """
    _learn(engine, 2, prefix="prod", context_type=ContextType.PRODUCTION.value)
    _learn(engine, 2, prefix="dev", context_type=ContextType.DEVELOPMENT.value)

    patterns = _persisted_patterns(tmp_path)
    assert patterns == [], (
        f"Observaciones de contextos distintos no deben agruparse; se "
        f"persistieron {len(patterns)}: "
        f"{[(p.get('pattern_type'), (p.get('context') or {}).get('context_type')) for p in patterns]}"
    )


def test_el_patron_persistido_conserva_los_datos_criticos(engine, tmp_path):
    """El patron persistido debe conservar los campos del item 5 de DATOS CRITICOS."""
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)

    patterns = _persisted_patterns(tmp_path)
    assert patterns, "El patron validado debe persistirse"
    for pattern in patterns:
        for field in CRITICAL_PATTERN_FIELDS:
            assert field in pattern, (
                f"Falta el dato critico '{field}' en el patron persistido "
                f"{pattern.get('pattern_id')}"
            )
        assert pattern["pattern_id"], "El patron persistido debe tener `pattern_id`"
        assert isinstance(pattern["context"], dict), (
            "El patron persistido debe conservar su contexto"
        )
        assert isinstance(pattern["metrics"], dict), (
            "El patron persistido debe conservar sus metricas"
        )


def test_el_patron_persistido_sobrevive_al_reinicio(engine, tmp_path):
    """El patron validado debe recuperarse tras el reinicio del motor."""
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    persisted = _persisted_patterns(tmp_path)
    assert persisted, "El patron validado debe persistirse"
    expected_ids = {pattern["pattern_id"] for pattern in persisted}

    restarted = ContextualAdaptationEngine(data_dir=str(tmp_path))

    recovered = []
    for row in restarted.knowledge_base.get("learning_results", []) or []:
        if not isinstance(row, dict):
            continue
        recovered.extend(
            pattern for pattern in row.get("learned_patterns", []) or []
            if isinstance(pattern, dict)
        )
    recovered_ids = {pattern.get("pattern_id") for pattern in recovered}
    assert expected_ids & recovered_ids, (
        f"El patron persistido debe recuperarse tras el reinicio; "
        f"persistidos {sorted(expected_ids)}, recuperados {sorted(recovered_ids)}"
    )


def test_el_test_no_escribe_en_los_ficheros_de_persistencia_de_produccion(engine, tmp_path):
    """El test no debe tocar los ficheros de persistencia de Goal de `data/`.

    `tests/test_goal_adaptation_feedback.py` creo el motor sin `data_dir` y
    contamino `data/goal_adaptation_feedback.json` con 42 registros de test
    (ver 2.8.8.9.4.1). Este test debe permanecer aislado.
    """
    before = _production_signature()
    _learn(engine, MIN_SIMILAR_OBSERVATIONS)
    after = _production_signature()
    assert before == after, (
        f"El test modifico los ficheros de produccion: antes={before}, despues={after}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
