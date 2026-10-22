#!/usr/bin/env python3
"""
Test de olvido (2.8.8.9.11.4): verificar eliminación/expiración correcta.

AISLAMIENTO: motor instanciado SIEMPRE con `data_dir` temporal.
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, AdaptationRule


def _make_rule(rule_id):
    return AdaptationRule(
        rule_id=rule_id,
        name="rule " + rule_id,
        description="desc",
        condition_pattern="*",
        adaptation_actions=[],
        context_triggers=[],
        confidence_threshold=0.5,
        priority=1,
    )


def test_remove_adaptation_rule_forgets_and_persists(tmp_path):
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    r = _make_rule("r_forget")
    assert engine.add_adaptation_rule(r) is True
    assert engine.get_adaptation_rule("r_forget") is not None

    # Olvido por id
    assert engine.remove_adaptation_rule("r_forget") is True
    assert engine.get_adaptation_rule("r_forget") is None
    assert "r_forget" not in engine.adaptation_rules

    # Persistencia: recargar desde disco y verificar ausencia
    engine2 = ContextualAdaptationEngine(data_dir=str(tmp_path))
    assert engine2.get_adaptation_rule("r_forget") is None


def test_remove_adaptation_rule_unknown_returns_false(tmp_path):
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    assert engine.remove_adaptation_rule("no_existe") is False


def test_remove_adaptation_rule_does_not_affect_others(tmp_path):
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    engine.add_adaptation_rule(_make_rule("r1"))
    engine.add_adaptation_rule(_make_rule("r2"))
    assert engine.remove_adaptation_rule("r1") is True
    assert engine.get_adaptation_rule("r1") is None
    assert engine.get_adaptation_rule("r2") is not None
