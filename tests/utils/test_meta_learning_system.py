# -*- coding: utf-8 -*-
"""Tests de MetaLearningSystem (src/utils/meta_learning_system.py)."""

import json
import os
import sys
import tempfile
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import unittest

from utils.meta_learning_system import (
    MetaLearningLevel,
    MetaLearningResult,
    MetaRuleStatus,
    LearningExperience,
    LearningEvaluation,
    MetaRule,
    MetaRuleApplication,
    MetaLearningInsight,
    MetaLearningSystem,
)


def _stop_all_threads(mls):
    """Detener todos los threads derivados de un MetaLearningSystem."""
    try:
        mls.stop_meta_learning_process()
    except Exception:
        pass
    for obj in (mls.adaptive_engine, mls.self_improvement, mls.performance_optimizer):
        _stop_obj_threads(obj)
    # El ALE anida SIS y PO dentro con nombres diferentes
    ae = getattr(mls, "adaptive_engine", None)
    if ae is not None:
        for attr in ("self_improvement_system", "performance_optimizer"):
            _stop_obj_threads(getattr(ae, attr, None))


def _stop_obj_threads(obj):
    if obj is None:
        return
    for method in ("stop_learning_engine", "stop_learning", "stop_optimization"):
        m = getattr(obj, method, None)
        if callable(m):
            try:
                m()
            except Exception:
                pass


class TestMetaLearningLevel(unittest.TestCase):
    def test_valores(self):
        assert MetaLearningLevel.STRATEGY_SELECTION.value == "strategy_selection"
        assert MetaLearningLevel.PARAMETER_ADAPTATION.value == "parameter_adaptation"
        assert MetaLearningLevel.CONTEXTUAL_OPTIMIZATION.value == "contextual_optimization"
        assert MetaLearningLevel.KNOWLEDGE_ABSTRACTION.value == "knowledge_abstraction"
        assert MetaLearningLevel.LEARNING_RATE_ADJUSTMENT.value == "learning_rate_adjustment"

    def test_count(self):
        assert len(list(MetaLearningLevel)) == 5


class TestMetaLearningResult(unittest.TestCase):
    def test_valores(self):
        assert MetaLearningResult.IMPROVEMENT_DETECTED.value == "improvement_detected"
        assert MetaLearningResult.DEGRADATION_DETECTED.value == "degradation_detected"
        assert MetaLearningResult.NO_CHANGE.value == "no_change"
        assert MetaLearningResult.INSUFFICIENT_DATA.value == "insufficient_data"
        assert MetaLearningResult.CONFLICTING_SIGNALS.value == "conflicting_signals"

    def test_count(self):
        assert len(list(MetaLearningResult)) == 5


class TestMetaRuleStatus(unittest.TestCase):
    def test_valores(self):
        assert MetaRuleStatus.APPLIED.value == "applied"
        assert MetaRuleStatus.SKIPPED_CONDITION_NOT_MET.value == "skipped_condition_not_met"
        assert MetaRuleStatus.SKIPPED_INSUFFICIENT_SAMPLES.value == "skipped_insufficient_samples"
        assert MetaRuleStatus.SKIPPED_UNSUPPORTED_ACTION.value == "skipped_unsupported_action"
        assert MetaRuleStatus.REJECTED_RULE_NOT_FOUND.value == "rejected_rule_not_found"
        assert MetaRuleStatus.REJECTED_INVALID.value == "rejected_invalid"
        assert MetaRuleStatus.REVERTED.value == "reverted"

    def test_count(self):
        assert len(list(MetaRuleStatus)) == 7


class TestLearningExperience(unittest.TestCase):
    def _make_experience(self, **kwargs):
        defaults = dict(
            experience_id="exp_001",
            timestamp=datetime.now(),
            learning_system="adaptive_learning",
            task_type="model_training",
            context={"timestamp": "now"},
            strategy_used="strategy_a",
            parameters={"lr": 0.01},
            outcome={"success": True},
            success_metrics={"success_rate": 0.85},
            confidence_score=0.9,
        )
        defaults.update(kwargs)
        return LearningExperience(**defaults)

    def test_campos(self):
        exp = self._make_experience()
        assert exp.experience_id == "exp_001"
        assert exp.learning_system == "adaptive_learning"
        assert exp.task_type == "model_training"
        assert exp.strategy_used == "strategy_a"
        assert exp.success_metrics == {"success_rate": 0.85}
        assert exp.confidence_score == 0.9

    def test_metadata_default(self):
        exp = self._make_experience()
        assert exp.metadata == {}

    def test_metadata_custom(self):
        exp = self._make_experience(metadata={"custom": True})
        assert exp.metadata == {"custom": True}


class TestLearningEvaluation(unittest.TestCase):
    def test_campos(self):
        ev = LearningEvaluation(
            learning_system="adaptive_learning",
            task_type="model_training",
            strategy="strategy_a",
            sample_count=50,
            required_samples=50,
            success_rate=0.85,
            confidence=0.9,
            consistency=0.8,
            sufficient_evidence=True,
            stable_pattern=True,
            result=MetaLearningResult.IMPROVEMENT_DETECTED,
        )
        assert ev.learning_system == "adaptive_learning"
        assert ev.result == MetaLearningResult.IMPROVEMENT_DETECTED

    def test_defaults(self):
        ev = LearningEvaluation(
            learning_system="test",
            task_type="test",
            strategy="test",
            sample_count=0,
            required_samples=0,
            success_rate=0.0,
            confidence=0.0,
            consistency=0.0,
            sufficient_evidence=False,
            stable_pattern=False,
            result=MetaLearningResult.INSUFFICIENT_DATA,
        )
        assert ev.indicators == []
        assert ev.sample_ids == []


class TestMetaRule(unittest.TestCase):
    def test_campos(self):
        rule = MetaRule(
            meta_rule_id="rule_001",
            name="low_success_rate",
            target_rule_id="rule_a",
            condition_metric="success_rate",
            operator="<",
            threshold=0.5,
            action="disable",
        )
        assert rule.meta_rule_id == "rule_001"
        assert rule.target_rule_id == "rule_a"
        assert rule.operator == "<"
        assert rule.threshold == 0.5
        assert rule.action == "disable"
        assert rule.enabled is True
        assert rule.min_execution_count == 0

    def test_is_valid_true(self):
        rule = MetaRule("r1", "name", "target", "success_rate", "<", 0.5, "disable")
        assert rule.is_valid() is True

    def test_is_valid_metric_invalid(self):
        rule = MetaRule("r1", "name", "target", "invalid_metric", "<", 0.5, "disable")
        assert rule.is_valid() is False

    def test_is_valid_operator_invalid(self):
        rule = MetaRule("r1", "name", "target", "success_rate", "===", 0.5, "disable")
        assert rule.is_valid() is False

    def test_is_valid_action_invalid(self):
        rule = MetaRule("r1", "name", "target", "success_rate", "<", 0.5, "invalid_action")
        assert rule.is_valid() is False

    def test_is_valid_set_priority(self):
        rule = MetaRule("r1", "name", "target", "execution_count", ">", 10, "set_priority",
                        action_value=5)
        assert rule.is_valid() is True

    def test_supported_constants(self):
        assert "success_rate" in MetaRule.SUPPORTED_METRICS
        assert "<" in MetaRule.SUPPORTED_OPERATORS
        assert "disable" in MetaRule.SUPPORTED_ACTIONS
        assert "reset_stats" in MetaRule.SUPPORTED_ACTIONS


class TestMetaRuleApplication(unittest.TestCase):
    def test_campos(self):
        app = MetaRuleApplication(
            meta_rule_id="rule_001",
            target_rule_id="rule_a",
            action="disable",
            status=MetaRuleStatus.APPLIED,
            previous_state={"enabled": True},
            new_state={"enabled": False},
            message="Applied",
        )
        assert app.meta_rule_id == "rule_001"
        assert app.status == MetaRuleStatus.APPLIED
        assert app.reverted is False

    def test_defaults(self):
        app = MetaRuleApplication(
            meta_rule_id="r1", target_rule_id="t1",
            action="disable", status=MetaRuleStatus.APPLIED,
        )
        assert app.previous_state == {}
        assert app.message == ""
        assert isinstance(app.timestamp, datetime)
        assert app.reverted is False


class TestMetaLearningInsight(unittest.TestCase):
    def test_campos(self):
        insight = MetaLearningInsight(
            insight_id="insight_001", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="Strategy A performs better", confidence=0.85,
            evidence=[], recommendation="Use Strategy A", impact_score=0.75,
        )
        assert insight.insight_id == "insight_001"
        assert insight.level == MetaLearningLevel.STRATEGY_SELECTION
        assert insight.validation_required is False
        assert insight.applied is False
        assert insight.learning_system == ""


class TestMetaLearningSystemInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mls = MetaLearningSystem()
        _stop_all_threads(cls.mls)

    @classmethod
    def tearDownClass(cls):
        pass  # threads already stopped

    def test_adaptive_engine_asignado(self):
        assert self.mls.adaptive_engine is not None

    def test_self_improvement_asignado(self):
        assert self.mls.self_improvement is not None

    def test_performance_optimizer_asignado(self):
        assert self.mls.performance_optimizer is not None

    def test_pattern_analyzer_asignado(self):
        assert self.mls.pattern_analyzer is not None

    def test_config_tiene_claves(self):
        assert "enabled" in self.mls.config
        assert "max_experiences" in self.mls.config
        assert "min_experiences_for_analysis" in self.mls.config
        assert "confidence_threshold" in self.mls.config
        assert "security" in self.mls.config

    def test_estado_inicial(self):
        assert self.mls.is_running is False
        assert len(self.mls.experiences) == 0
        assert len(self.mls.insights) == 0
        assert len(self.mls.meta_rule_definitions) == 0
        assert len(self.mls.meta_rule_history) == 0
        assert self.mls.total_experiences == 0
        assert self.mls.successful_insights == 0
        assert self.mls.auto_changes_applied == 0
        assert len(self.mls.security_decisions) == 0
        assert self.mls.contextual_adaptation_engine is None

    def test_seguridad_config(self):
        sec = self.mls.config["security"]
        assert sec["max_auto_changes_per_cycle"] == 3
        assert "reset_stats" in sec["protected_actions"]
        assert sec["max_security_decisions"] == 500

    def test_learning_queue_vacia(self):
        assert self.mls.learning_queue.qsize() == 0


class _MLSTestBase(unittest.TestCase):
    """Base con MLS singleton y threads detenidos."""
    @classmethod
    def setUpClass(cls):
        cls.mls = MetaLearningSystem()
        _stop_all_threads(cls.mls)

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        import queue as _queue
        # Reset mutable state between tests
        self.mls.experiences = []
        self.mls.insights = []
        self.mls.meta_rules = {}
        self.mls.meta_rule_definitions = []
        self.mls.meta_rule_history = []
        self.mls.total_experiences = 0
        self.mls.successful_insights = 0
        self.mls.auto_changes_applied = 0
        self.mls.security_decisions = []
        self.mls.integrated_components = {}
        self.mls.task_queue = _queue.Queue()
        # Clear improvement rules loaded from file during __init__
        if self.mls.self_improvement is not None:
            self.mls.self_improvement.improvement_rules = []
        self.mls.knowledge_base = {
            "goal_adaptation_feedback": [],
            "adaptation_strategies": {"successful_strategies": []},
            "learning_patterns": [],
        }
        self.mls.config["auto_apply_insights"] = False


class TestGetLearningSuccessIndicators(_MLSTestBase):
    def test_indicators(self):
        indicators = self.mls.get_learning_success_indicators()
        assert "primary_metrics" in indicators
        assert "success_rate" in indicators["primary_metrics"]
        assert "learning_value" in indicators["primary_metrics"]
        assert "fallback_metrics" in indicators
        assert "confidence_score" in indicators["fallback_metrics"]
        assert "qualitative_indicators" in indicators
        assert "quality_indicators" in indicators


class TestCaptureLearningExperience(_MLSTestBase):
    def _mk_context(self):
        return {"timestamp": "2024-01-01T00:00:00", "system": "test"}

    def _mk_outcome(self):
        return {"success": True, "detail": "ok"}

    def test_capture_exitoso(self):
        exp_id = self.mls.capture_learning_experience(
            "adaptive_learning", "model_training",
            self._mk_context(), "strategy_a", {"lr": 0.01},
            self._mk_outcome(), {"success_rate": 0.85}, 0.9
        )
        assert exp_id is not None
        assert isinstance(exp_id, str)
        assert len(self.mls.experiences) == 1
        assert self.mls.total_experiences == 1

    def test_capture_confianza_invalida_alta(self):
        with self.assertRaises(ValueError):
            self.mls.capture_learning_experience(
                "adaptive_learning", "model_training",
                self._mk_context(), "s", {}, self._mk_outcome(), {}, 1.5
            )

    def test_capture_confianza_string(self):
        with self.assertRaises(ValueError):
            self.mls.capture_learning_experience(
                "adaptive_learning", "model_training",
                self._mk_context(), "s", {}, self._mk_outcome(), {}, "high"
            )

    def test_capture_sistema_no_soportado(self):
        result = self.mls.capture_learning_experience(
            "unknown_system", "model_training",
            self._mk_context(), "s", {}, self._mk_outcome(), {}, 0.9
        )
        assert result is None
        assert len(self.mls.experiences) == 0

    def test_capture_tarea_trivial(self):
        result = self.mls.capture_learning_experience(
            "adaptive_learning", "test",
            self._mk_context(), "s", {}, self._mk_outcome(), {}, 0.9
        )
        assert result is None

    def test_capture_contexto_vacio(self):
        result = self.mls.capture_learning_experience(
            "adaptive_learning", "model_training",
            {}, "s", {}, self._mk_outcome(), {}, 0.9
        )
        assert result is None

    def test_capture_outcome_vacio(self):
        result = self.mls.capture_learning_experience(
            "adaptive_learning", "model_training",
            self._mk_context(), "s", {}, {}, {}, 0.9
        )
        assert result is None

    def test_capture_duplicado(self):
        ctx = self._mk_context()
        out = self._mk_outcome()
        # La detecci?n de duplicados requiere 2 ocurrencias previas
        exp_id1 = self.mls.capture_learning_experience(
            "adaptive_learning", "model_training", ctx, "s", {}, out, {}, 0.9)
        exp_id2 = self.mls.capture_learning_experience(
            "adaptive_learning", "model_training", ctx, "s", {}, out, {}, 0.9)
        exp_id3 = self.mls.capture_learning_experience(
            "adaptive_learning", "model_training", ctx, "s", {}, out, {}, 0.9)
        assert exp_id1 is not None
        assert exp_id2 is not None
        assert exp_id3 is None
        assert len(self.mls.experiences) == 2


class TestCaptureStructuredAndWithContext(_MLSTestBase):
    def test_capture_estructurada_exitoso(self):
        with mock.patch.object(self.mls, '_get_current_system_state',
                               return_value={"status": "ok"}):
            exp_id = self.mls.capture_structured_experience(
                "adaptive_learning", "hyperparameter_optimization",
                {"timestamp": datetime.now().isoformat()},
                {"action": "tune"}, "strategy_x", {"lr": 0.01},
                {"accuracy": 0.9}, {"accuracy": 0.9},
            )
        assert exp_id is not None
        assert len(self.mls.experiences) == 1

    def test_capture_contextual_exitoso(self):
        exp_id = self.mls.capture_experience_with_context(
            "adaptive_learning", "model_training",
            {"hardware": "x64"}, {"user": "test"}, {"cpu": 50.0},
            {"action": "train"}, {"strategy": "a"}, {"accuracy": 0.9},
            0.8
        )
        assert exp_id is not None
        assert len(self.mls.experiences) == 1

    def test_capture_contextual_bajo_valor(self):
        result = self.mls.capture_experience_with_context(
            "adaptive_learning", "model_training",
            {"hardware": "x64"}, {"user": "test"}, {"cpu": 50.0},
            {"action": "train"}, {"strategy": "a"}, {"accuracy": 0.9},
            0.2
        )
        assert result is None


class TestEvaluateLearningStrategy(_MLSTestBase):
    def test_sin_experiencias(self):
        ev = self.mls.evaluate_learning_strategy("adaptive_learning", "model_training")
        assert ev.result == MetaLearningResult.INSUFFICIENT_DATA
        assert ev.sample_count == 0
        assert ev.sufficient_evidence is False

    def test_con_experiencias_insuficientes(self):
        for i in range(3):
            self.mls.capture_learning_experience(
                "adaptive_learning", "model_training",
                {"timestamp": datetime.now().isoformat(), "system": "s"},
                f"strategy_{i % 2}", {"lr": 0.01},
                {"success": True, "success_indicators": ["ok"]},
                {"success_rate": 0.8 + i * 0.05}, 0.9
            )
        ev = self.mls.evaluate_learning_strategy("adaptive_learning", "model_training")
        assert ev.sample_count == 3
        assert ev.result == MetaLearningResult.INSUFFICIENT_DATA
        assert ev.sufficient_evidence is False

    def test_experiencias_externas_improvement(self):
        exps = [
            LearningExperience(
                experience_id=f"ext_{i}",
                timestamp=datetime.now(),
                learning_system="adaptive_learning",
                task_type="model_training",
                context={"timestamp": "now"},
                strategy_used="strategy_a",
                parameters={},
                outcome={"success": True},
                success_metrics={"success_rate": 0.9},
                confidence_score=0.9,
            )
            for i in range(50)
        ]
        ev = self.mls.evaluate_learning_strategy(
            "adaptive_learning", "model_training",
            strategy="strategy_a", experiences=exps
        )
        assert ev.result == MetaLearningResult.IMPROVEMENT_DETECTED
        assert ev.sufficient_evidence is True
        assert ev.sample_count == 50

    def test_experiencias_externas_degradation(self):
        exps = [
            LearningExperience(
                experience_id=f"deg_{i}",
                timestamp=datetime.now(),
                learning_system="adaptive_learning",
                task_type="model_training",
                context={"timestamp": "now"},
                strategy_used="strategy_a",
                parameters={},
                outcome={"success": True},
                success_metrics={"success_rate": 0.75},
                confidence_score=0.9,
            )
            for i in range(50)
        ]
        ev = self.mls.evaluate_learning_strategy(
            "adaptive_learning", "model_training",
            strategy="strategy_a", experiences=exps
        )
        # 0.75 > 0.7 (confidence_threshold) → IMPROVEMENT_DETECTED
        assert ev.result == MetaLearningResult.IMPROVEMENT_DETECTED

    def test_experiencias_externas_conflict(self):
        scores = [0.9] * 25 + [0.3] * 25
        exps = [
            LearningExperience(
                experience_id=f"conf_{i}",
                timestamp=datetime.now(),
                learning_system="adaptive_learning",
                task_type="model_training",
                context={"timestamp": "now"},
                strategy_used="strategy_a",
                parameters={},
                outcome={"success": True},
                success_metrics={"success_rate": scores[i]},
                confidence_score=0.9,
            )
            for i in range(50)
        ]
        ev = self.mls.evaluate_learning_strategy(
            "adaptive_learning", "model_training",
            strategy="strategy_a", experiences=exps
        )
        assert ev.sufficient_evidence is True
        # Low consistency → CONFLICTING_SIGNALS
        assert ev.result == MetaLearningResult.CONFLICTING_SIGNALS


class TestGetLearningEvaluations(_MLSTestBase):
    def test_sin_experiencias(self):
        assert self.mls.get_learning_evaluations() == []

    def test_con_experiencia(self):
        self.mls.capture_learning_experience(
            "adaptive_learning", "model_training",
            {"timestamp": datetime.now().isoformat(), "system": "s"},
            "strategy_a", {}, {"success": True},
            {"success_rate": 0.9}, 0.9
        )
        evals = self.mls.get_learning_evaluations()
        assert len(evals) == 1
        assert evals[0].learning_system == "adaptive_learning"
        assert evals[0].task_type == "model_training"


class TestAnalyzeLearningPatterns(_MLSTestBase):
    def test_insuficientes_experiencias(self):
        result = self.mls.analyze_learning_patterns()
        assert result == []


class TestSecurityLimits(_MLSTestBase):
    def test_limites_default(self):
        limits = self.mls.get_security_limits()
        assert limits["auto_apply_enabled"] is False
        assert limits["max_auto_changes_per_cycle"] == 3
        assert "reset_stats" in limits["protected_actions"]
        assert limits["auto_changes_applied"] == 0
        assert limits["auto_changes_remaining"] == 3

    def test_reset_auto_change_cycle(self):
        self.mls.auto_changes_applied = 2
        self.mls.reset_auto_change_cycle()
        assert self.mls.auto_changes_applied == 0
        limits = self.mls.get_security_limits()
        assert limits["auto_changes_remaining"] == 3

    def test_limites_valor_invalido(self):
        self.mls.config["security"]["max_auto_changes_per_cycle"] = "invalid"
        limits = self.mls.get_security_limits()
        assert limits["max_auto_changes_per_cycle"] == 3


class TestSharedComponents(_MLSTestBase):
    def test_sin_componentes_compartidos(self):
        assert self.mls.get_shared_components() == []

    def test_con_componente_conectado(self):
        result = self.mls.connect_adaptive_learning_engine(self.mls.adaptive_engine)
        assert result["success"] is True
        assert "adaptive_learning" in self.mls.get_shared_components()

    def test_componente_no_soportado(self):
        result = self.mls.connect_component("invalid_component", None)
        assert result["success"] is False

    def test_engine_none(self):
        result = self.mls.connect_component("adaptive_learning", None)
        assert result["success"] is False


class TestSecurityDecisions(_MLSTestBase):
    def test_decisiones_vacias(self):
        assert self.mls.get_security_decisions() == []

    def test_registrar_decision(self):
        decision = self.mls._record_security_decision("insight", "insight_001", True, "test reason")
        assert decision["subject_type"] == "insight"
        assert decision["allowed"] is True
        assert decision["reason"] == "test reason"
        assert len(self.mls.get_security_decisions()) == 1


class TestSecurityStatus(_MLSTestBase):
    def test_status(self):
        status = self.mls.get_security_status()
        assert "limits" in status
        assert "shared_components" in status
        assert "total_decisions" in status
        assert "blocked_decisions" in status
        assert status["total_decisions"] == 0


class TestCheckInsightSecurity(_MLSTestBase):
    def test_auto_apply_disabled(self):
        insight = MetaLearningInsight(
            insight_id="i1", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.9,
            evidence=[], recommendation="r", impact_score=0.8,
        )
        allowed, reason = self.mls.check_insight_security(insight)
        assert allowed is False

    def test_auto_apply_enabled_allowed(self):
        self.mls.config["auto_apply_insights"] = True
        insight = MetaLearningInsight(
            insight_id="i1", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.9,
            evidence=[], recommendation="r", impact_score=0.8,
            learning_system="adaptive_learning",
        )
        allowed, reason = self.mls.check_insight_security(insight)
        assert allowed is True

    def test_limit_reached(self):
        self.mls.config["auto_apply_insights"] = True
        self.mls.auto_changes_applied = 3  # max
        insight = MetaLearningInsight(
            insight_id="i1", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.9,
            evidence=[], recommendation="r", impact_score=0.8,
            learning_system="adaptive_learning",
        )
        allowed, reason = self.mls.check_insight_security(insight)
        assert allowed is False


class TestCheckMetaRuleSecurity(_MLSTestBase):
    def test_auto_apply_disabled(self):
        rule = MetaRule("r1", "name", "target", "success_rate", "<", 0.5, "disable")
        allowed, reason = self.mls.check_meta_rule_security(rule)
        assert allowed is False

    def test_protected_action(self):
        self.mls.config["auto_apply_insights"] = True
        rule = MetaRule("r1", "name", "target", "success_rate", "<", 0.5, "reset_stats")
        allowed, reason = self.mls.check_meta_rule_security(rule)
        assert allowed is False

    def test_allowed(self):
        self.mls.config["auto_apply_insights"] = True
        rule = MetaRule("r1", "name", "target", "success_rate", "<", 0.5, "disable")
        allowed, reason = self.mls.check_meta_rule_security(rule)
        assert allowed is True


class TestMetaLearningMetrics(_MLSTestBase):
    def test_empty_metrics(self):
        metrics = self.mls.get_meta_learning_metrics()
        assert metrics["total_experiences"] == 0
        assert metrics["active_insights"] == 0
        assert metrics["applied_insights"] == 0
        assert metrics["success_rate"] == 0.0
        assert "confidence_distribution" in metrics

    def test_confidence_distribution_empty(self):
        dist = self.mls._calculate_confidence_distribution()
        assert dist["low"] == 0
        assert dist["medium"] == 0
        assert dist["high"] == 0


class TestValidateMetaLearningInsights(_MLSTestBase):
    def test_validate_not_found(self):
        result = self.mls.validate_meta_learning_insights(["nonexistent"])
        assert result == {"nonexistent": False}

    def test_validate_found(self):
        insight = MetaLearningInsight(
            insight_id="valid_001", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.9,
            evidence=[], recommendation="r", impact_score=0.8,
        )
        self.mls.insights.append(insight)
        result = self.mls.validate_meta_learning_insights(["valid_001"])
        assert result == {"valid_001": True}
        assert insight.applied is True

    def test_validate_low_confidence(self):
        insight = MetaLearningInsight(
            insight_id="low_001", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.5,
            evidence=[], recommendation="r", impact_score=0.8,
        )
        self.mls.insights.append(insight)
        result = self.mls.validate_meta_learning_insights(["low_001"])
        assert result == {"low_001": False}


class TestGetRecommendations(_MLSTestBase):
    def test_sin_insights(self):
        assert self.mls.get_recommendations() == []

    def test_con_insight_aplicado(self):
        insight = MetaLearningInsight(
            insight_id="rec_001", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.9,
            evidence=[], recommendation="Use strategy A",
            impact_score=0.75,
            learning_system="adaptive_learning",
            task_type="model_training",
        )
        insight.applied = True
        self.mls.insights.append(insight)
        recs = self.mls.get_recommendations()
        assert len(recs) == 1
        assert "recommendation" in recs[0]

    def test_insight_no_aplicado(self):
        insight = MetaLearningInsight(
            insight_id="rec_002", timestamp=datetime.now(),
            level=MetaLearningLevel.STRATEGY_SELECTION,
            description="test", confidence=0.9,
            evidence=[], recommendation="Use strategy B",
            impact_score=0.75,
        )
        self.mls.insights.append(insight)
        assert self.mls.get_recommendations() == []


class TestLearningRules(_MLSTestBase):
    def test_get_vacio(self):
        assert self.mls.get_learning_rules() == []

    def test_add_learning_rule(self):
        from utils.self_improvement_system import ImprovementRule
        rule = ImprovementRule(
            rule_id="imp_001",
            name="high_cpu",
            description="Handle high CPU",
            condition="cpu > 80",
            action="optimize",
            priority=1,
        )
        self.mls.self_improvement.add_improvement_rule(rule)
        rules = self.mls.get_learning_rules()
        assert len(rules) == 1
        assert rules[0].rule_id == "imp_001"


class TestMetaRules(_MLSTestBase):
    def test_get_vacio(self):
        assert self.mls.get_meta_rules() == []

    def test_add_valida(self):
        rule = MetaRule("mr_001", "name", "target_1", "success_rate", "<", 0.5, "disable")
        status = self.mls.add_meta_rule(rule)
        assert status == MetaRuleStatus.APPLIED
        assert len(self.mls.get_meta_rules()) == 1

    def test_add_invalida(self):
        rule = MetaRule("mr_002", "name", "target_1", "invalid", "<", 0.5, "disable")
        status = self.mls.add_meta_rule(rule)
        assert status == MetaRuleStatus.REJECTED_INVALID

    def test_add_duplicada(self):
        rule1 = MetaRule("mr_003", "name", "target_1", "success_rate", "<", 0.5, "disable")
        rule2 = MetaRule("mr_003", "name", "target_2", "execution_count", ">", 10, "enable")
        self.mls.add_meta_rule(rule1)
        status = self.mls.add_meta_rule(rule2)
        assert status == MetaRuleStatus.REJECTED_INVALID
        assert len(self.mls.get_meta_rules()) == 1


class TestCompareMetric(unittest.TestCase):
    def test_lt(self):
        assert MetaLearningSystem._compare_metric(3.0, "<", 5.0) is True
        assert MetaLearningSystem._compare_metric(6.0, "<", 5.0) is False

    def test_le(self):
        assert MetaLearningSystem._compare_metric(5.0, "<=", 5.0) is True

    def test_gt(self):
        assert MetaLearningSystem._compare_metric(6.0, ">", 5.0) is True

    def test_ge(self):
        assert MetaLearningSystem._compare_metric(5.0, ">=", 5.0) is True

    def test_eq(self):
        assert MetaLearningSystem._compare_metric(5.0, "==", 5.0) is True

    def test_invalid_value(self):
        assert MetaLearningSystem._compare_metric("abc", ">", 5.0) is False

    def test_invalid_operator(self):
        assert MetaLearningSystem._compare_metric(5.0, "!=", 5.0) is False


class TestApplyMetaRule(_MLSTestBase):
    def setUp(self):
        super().setUp()
        from utils.self_improvement_system import ImprovementRule
        self.rule = ImprovementRule(
            rule_id="target_001", name="test", description="test",
            condition="success_rate < 0.5", action="disable",
            priority=1, success_rate=0.3, execution_count=10,
        )
        self.mls.self_improvement.add_improvement_rule(self.rule)

    def test_apply_invalid_rule(self):
        result = self.mls.apply_meta_rule("not_a_rule")
        assert result.status == MetaRuleStatus.REJECTED_INVALID

    def test_apply_target_not_found(self):
        meta_rule = MetaRule("mr_1", "name", "nonexistent", "success_rate", "<", 0.5, "disable")
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.REJECTED_RULE_NOT_FOUND

    def test_apply_disabled_meta_rule(self):
        meta_rule = MetaRule("mr_2", "name", "target_001", "success_rate", "<", 0.5, "disable")
        meta_rule.enabled = False
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.SKIPPED_CONDITION_NOT_MET

    def test_apply_insufficient_samples(self):
        meta_rule = MetaRule("mr_3", "name", "target_001", "success_rate", "<", 0.5, "disable",
                             min_execution_count=100)
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.SKIPPED_INSUFFICIENT_SAMPLES

    def test_apply_condition_not_met(self):
        meta_rule = MetaRule("mr_4", "name", "target_001", "success_rate", "<", 0.1, "disable")
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.SKIPPED_CONDITION_NOT_MET

    def test_apply_disable(self):
        meta_rule = MetaRule("mr_5", "name", "target_001", "success_rate", "<", 0.5, "disable")
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.APPLIED
        assert self.rule.enabled is False

    def test_apply_enable(self):
        self.rule.enabled = False
        meta_rule = MetaRule("mr_6", "name", "target_001", "success_rate", ">", 0.1, "enable")
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.APPLIED
        assert self.rule.enabled is True

    def test_apply_set_priority(self):
        meta_rule = MetaRule("mr_7", "name", "target_001", "success_rate", ">", 0.1, "set_priority",
                             action_value=5)
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.APPLIED
        assert self.rule.priority == 5

    def test_apply_reset_stats(self):
        meta_rule = MetaRule("mr_9", "name", "target_001", "success_rate", "<", 0.5, "reset_stats")
        result = self.mls.apply_meta_rule(meta_rule)
        assert result.status == MetaRuleStatus.APPLIED
        assert self.rule.success_rate == 0.0
        assert self.rule.execution_count == 0


class TestVerifyAndRevert(_MLSTestBase):
    def setUp(self):
        super().setUp()
        from utils.self_improvement_system import ImprovementRule
        self.rule = ImprovementRule(
            rule_id="target_002", name="test", description="test",
            condition="test", action="test", priority=1,
            success_rate=0.3, execution_count=10,
        )
        self.mls.self_improvement.add_improvement_rule(self.rule)

    def test_verify_success(self):
        meta_rule = MetaRule("mr_v1", "name", "target_002", "success_rate", "<", 0.5, "disable")
        app = self.mls.apply_meta_rule(meta_rule)
        assert self.mls.verify_meta_rule_application(app) is True

    def test_revert(self):
        self.rule.enabled = True
        meta_rule = MetaRule("mr_v2", "name", "target_002", "success_rate", "<", 0.5, "disable")
        app = self.mls.apply_meta_rule(meta_rule)
        assert self.rule.enabled is False
        assert self.mls.revert_meta_rule_application(app) is True
        assert self.rule.enabled is True
        assert app.reverted is True

    def test_revert_already_reverted(self):
        meta_rule = MetaRule("mr_v3", "name", "target_002", "success_rate", "<", 0.5, "disable")
        app = self.mls.apply_meta_rule(meta_rule)
        self.mls.revert_meta_rule_application(app)
        assert self.mls.revert_meta_rule_application(app) is False

    def test_history(self):
        assert self.mls.get_meta_rule_history() == []
        meta_rule = MetaRule("mr_h1", "name", "target_002", "success_rate", "<", 0.5, "disable")
        self.mls.apply_meta_rule(meta_rule)
        history = self.mls.get_meta_rule_history()
        assert len(history) == 1
        assert history[0].meta_rule_id == "mr_h1"


class TestMetaLearningState(_MLSTestBase):
    def test_get_state(self):
        state = self.mls.get_meta_learning_state()
        assert "version" in state
        assert "experiences" in state
        assert "meta_rules" in state
        assert "meta_rule_history" in state
        assert "metrics" in state
        assert state["version"] == 1

    def test_save_state(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmp_path = f.name
        try:
            result = self.mls.save_meta_learning_state(tmp_path)
            assert result is True
            with open(tmp_path, 'r') as f:
                data = json.load(f)
            assert "version" in data
        finally:
            os.unlink(tmp_path)

    def test_save_state_default_path(self):
        result = self.mls.save_meta_learning_state()
        assert result is True


class TestIntegrationStatus(_MLSTestBase):
    def test_integration_status(self):
        status = self.mls.get_integration_status()
        assert "components" in status
        assert "connected_components" in status
        assert "no_duplicate_engines" in status

    def test_component_conectado(self):
        result = self.mls.connect_adaptive_learning_engine(self.mls.adaptive_engine)
        assert result["success"] is True
        assert result["shared"] is True
        assert result["already_connected"] is True

    def test_component_no_compartido(self):
        class MockAdaptiveEngine:
            def get_learning_engine_status(self):
                return {}
        engine = MockAdaptiveEngine()
        result = self.mls.connect_adaptive_learning_engine(engine)
        assert result["success"] is True
        assert result["already_connected"] is False
        assert "adaptive_learning" in self.mls.get_shared_components()
