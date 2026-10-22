#!/usr/bin/env python3
"""
Test de conservacion (2.8.8.9.11.5): verificar que no se eliminan datos
validos prematuramente.

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


def test_remove_one_rule_keeps_other_valid_rules(tmp_path):
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    engine.add_adaptation_rule(_make_rule("r_keep"))
    engine.add_adaptation_rule(_make_rule("r_drop"))
    assert engine.remove_adaptation_rule("r_drop") is True
    assert engine.get_adaptation_rule("r_keep") is not None
    engine2 = ContextualAdaptationEngine(data_dir=str(tmp_path))
    assert engine2.get_adaptation_rule("r_keep") is not None


def test_all_valid_rules_survive_reload(tmp_path):
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    for i in range(5):
        engine.add_adaptation_rule(_make_rule("r%d" % i))
    engine2 = ContextualAdaptationEngine(data_dir=str(tmp_path))
    for i in range(5):
        assert engine2.get_adaptation_rule("r%d" % i) is not None


def test_remove_unknown_does_not_delete_any(tmp_path):
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    engine.add_adaptation_rule(_make_rule("r1"))
    assert engine.remove_adaptation_rule("no_existe") is False
    assert engine.get_adaptation_rule("r1") is not None
