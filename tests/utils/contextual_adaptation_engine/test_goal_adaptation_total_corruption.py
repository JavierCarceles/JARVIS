import os
import sys
import tempfile

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "..", ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine  # noqa: E402


FICHEROS = (
    "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results.json",
    "contextual_adaptation_rules.json",
    "contextual_knowledge_base.json",
)


def _corromper(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    for nombre in FICHEROS:
        with open(os.path.join(data_dir, nombre), "w", encoding="utf-8") as handle:
            handle.write("{esto no es json valido")


def test_jarvis_continua_sin_datos_validos():
    tmp = tempfile.mkdtemp()
    data_dir = os.path.join(tmp, "data")
    _corromper(data_dir)

    motor = ContextualAdaptationEngine(data_dir=data_dir)

    instantanea = motor.capture_context_snapshot()
    assert instantanea is not None

    reglas = motor.analyze_contextual_patterns(instantanea)
    assert reglas is not None

    resultado = motor.execute_adaptation(instantanea, reglas)
    assert resultado is not None
    assert getattr(resultado, "success", True) is True

    status = motor.get_engine_status()
    assert isinstance(status, dict)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))