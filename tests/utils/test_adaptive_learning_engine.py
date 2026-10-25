# -*- coding: utf-8 -*-
"""
Tests consolidados para utils.adaptive_learning_engine.
Consolida 2 archivos originales: test_adaptive_learning_engine.py y test_goal_adaptation_learning_loop.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
import json
import tempfile
from datetime import datetime
import unittest
from utils.adaptive_learning_engine import (
    LearningTask,
    NeuralArchitecture,
    LearningTaskConfig,
    ModelPerformance,
    AdaptiveLearningEngine,
)


# --- From test_adaptive_learning_engine.py ---
class TestLearningTask(unittest.TestCase):
    def test_valores(self):
        assert LearningTask.HYPERPARAMETER_OPTIMIZATION.value == "hyperparameter_optimization"
        assert LearningTask.MODEL_TRAINING.value == "model_training"
        assert LearningTask.FEATURE_SELECTION.value == "feature_selection"
        assert LearningTask.ARCHITECTURE_SEARCH.value == "architecture_search"
        assert LearningTask.KNOWLEDGE_TRANSFER.value == "knowledge_transfer"
        assert LearningTask.ONLINE_LEARNING.value == "online_learning"
        assert LearningTask.BATCH_LEARNING.value == "batch_learning"
        assert LearningTask.REINFORCEMENT_LEARNING.value == "reinforcement_learning"

    def test_count(self):
        assert len(list(LearningTask)) == 8


class TestNeuralArchitecture(unittest.TestCase):
    def test_valores(self):
        assert NeuralArchitecture.MLP.value == "mlp"
        assert NeuralArchitecture.CNN.value == "cnn"
        assert NeuralArchitecture.LSTM.value == "lstm"
        assert NeuralArchitecture.TRANSFORMER.value == "transformer"
        assert NeuralArchitecture.ATTENTION.value == "attention"
        assert NeuralArchitecture.RESNET.value == "resnet"
        assert NeuralArchitecture.GAN.value == "gan"

    def test_count(self):
        assert len(list(NeuralArchitecture)) == 7


class TestLearningTaskConfig(unittest.TestCase):
    def test_campos_obligatorios(self):
        config = LearningTaskConfig(
            task_id="task_001",
            task_type=LearningTask.MODEL_TRAINING,
            model_name="random_forest",
            hyperparameters={"n_estimators": 100},
        )
        assert config.task_id == "task_001"
        assert config.task_type == LearningTask.MODEL_TRAINING
        assert config.model_name == "random_forest"
        assert config.hyperparameters == {"n_estimators": 100}

    def test_defaults(self):
        config = LearningTaskConfig(
            task_id="task_002",
            task_type=LearningTask.HYPERPARAMETER_OPTIMIZATION,
            model_name="mlp",
            hyperparameters={},
        )
        assert config.training_data is None
        assert config.validation_data is None
        assert config.test_data is None
        assert config.target_variable == "efficiency_score"
        assert config.optimization_metric == "r2_score"
        assert config.max_epochs == 100
        assert config.batch_size == 32
        assert config.learning_rate == 0.001
        assert config.patience == 10
        assert config.early_stopping is True
        assert config.save_best_model is True
        assert config.cross_validation_folds == 5
        assert config.search_iterations == 50
        assert config.random_state == 42

    def test_custom_values(self):
        config = LearningTaskConfig(
            task_id="task_003",
            task_type=LearningTask.ONLINE_LEARNING,
            model_name="lstm",
            hyperparameters={"lr": 0.01},
            max_epochs=200,
            batch_size=64,
            learning_rate=0.01,
            early_stopping=False,
            random_state=99,
        )
        assert config.max_epochs == 200
        assert config.batch_size == 64
        assert config.learning_rate == 0.01
        assert config.early_stopping is False
        assert config.random_state == 99


class TestModelPerformance(unittest.TestCase):
    def test_defaults(self):
        mp = ModelPerformance(
            model_name="test_model",
            task_type=LearningTask.MODEL_TRAINING,
        )
        assert mp.model_name == "test_model"
        assert mp.task_type == LearningTask.MODEL_TRAINING
        assert mp.training_loss == 0.0
        assert mp.validation_loss == 0.0
        assert mp.test_loss == 0.0
        assert mp.training_score == 0.0
        assert mp.validation_score == 0.0
        assert mp.test_score == 0.0
        assert mp.convergence_rate == 0.0
        assert mp.overfitting_indicator == 0.0
        assert mp.training_time == 0.0
        assert mp.inference_time == 0.0
        assert mp.model_size == 0.0
        assert isinstance(mp.timestamp, datetime)

    def test_custom_values(self):
        mp = ModelPerformance(
            model_name="model_x",
            task_type=LearningTask.ARCHITECTURE_SEARCH,
            test_score=0.95,
            training_time=12.5,
            model_size=1.2,
        )
        assert mp.test_score == 0.95
        assert mp.training_time == 12.5
        assert mp.model_size == 1.2


class TestAdaptiveLearningEngineInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.stop_learning_engine()
        cls.engine.performance_optimizer.stop_optimization()

    def test_performance_optimizer_asignado(self):
        assert self.engine.performance_optimizer is not None

    def test_self_improvement_system_asignado(self):
        assert self.engine.self_improvement_system is not None

    def test_pattern_analyzer_asignado(self):
        assert self.engine.pattern_analyzer is not None

    def test_analytics_asignado(self):
        assert self.engine.analytics is not None

    def test_config_tiene_claves(self):
        assert "learning_enabled" in self.engine.config
        assert "auto_learning" in self.engine.config
        assert "engine_interval" in self.engine.config
        assert "max_concurrent_tasks" in self.engine.config
        assert "model_save_path" in self.engine.config
        assert "hyperparameter_config" in self.engine.config
        assert "neural_architectures" in self.engine.config

    def test_estado_inicial(self):
        assert self.engine.is_running is True  # _start_learning_engine
        assert len(self.engine.learning_tasks) == 0
        assert len(self.engine.torch_models) == 0
        assert len(self.engine.sklearn_models) == 0
        assert len(self.engine.performance_history) == 0
        assert len(self.engine.hyperparameter_tuning_history) == 0
        assert "goal_adaptation_feedback" in self.engine.knowledge_base
        assert "adaptation_strategies" in self.engine.knowledge_base
        assert "learning_patterns" in self.engine.knowledge_base

    def test_model_registry_inicializado(self):
        assert "mlp" in self.engine.model_registry
        assert "random_forest" in self.engine.model_registry
        assert "gradient_boosting" in self.engine.model_registry

    def test_knowledge_base_estructura(self):
        kb = self.engine.knowledge_base
        assert "goal_adaptation_feedback" in kb
        assert "adaptation_strategies" in kb
        assert "successful_strategies" in kb["adaptation_strategies"]
        assert "learning_patterns" in kb


class TestGetLearningEngineStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()
        cls.engine.stop_learning_engine()  # stop background thread

    @classmethod
    def tearDownClass(cls):
        cls.engine.performance_optimizer.stop_optimization()

    def test_status_contiene_claves(self):
        status = self.engine.get_learning_engine_status()
        assert "is_running" in status
        assert "learning_enabled" in status
        assert "auto_learning" in status
        assert "active_tasks" in status
        assert "queued_tasks" in status
        assert "total_models" in status
        assert "performance_history_size" in status
        assert "hyperparameter_tuning_history_size" in status
        assert "best_model" in status
        assert "average_performance" in status

    def test_status_is_running_false(self):
        self.engine.stop_learning_engine()
        status = self.engine.get_learning_engine_status()
        assert status["is_running"] is False

    def test_status_is_running_true(self):
        self.engine.start_learning_engine()
        status = self.engine.get_learning_engine_status()
        assert status["is_running"] is True
        assert status["learning_enabled"] is True


class TestAddLearningTask(unittest.TestCase):
    def setUp(self):
        self.engine = AdaptiveLearningEngine()
        self.engine.stop_learning_engine()

    def tearDown(self):
        self.engine.stop_learning_engine()
        self.engine.performance_optimizer.stop_optimization()

    def test_add_task_to_queue(self):
        task = LearningTaskConfig(
            task_id="task_001",
            task_type=LearningTask.MODEL_TRAINING,
            model_name="random_forest",
            hyperparameters={"n_estimators": 100},
        )
        assert self.engine.task_queue.qsize() == 0
        self.engine.add_learning_task(task)
        assert self.engine.task_queue.qsize() == 1

    def test_add_multiple_tasks(self):
        for i in range(3):
            task = LearningTaskConfig(
                task_id=f"task_{i}",
                task_type=LearningTask.FEATURE_SELECTION,
                model_name="mlp",
                hyperparameters={},
            )
            self.engine.add_learning_task(task)
        assert self.engine.task_queue.qsize() == 3


class TestGetModelInfo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()
        cls.engine.stop_learning_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.performance_optimizer.stop_optimization()

    def test_model_not_found(self):
        result = self.engine.get_model_info("nonexistent_model")
        assert result is None

    def test_sklearn_model_info(self):
        from sklearn.linear_model import LinearRegression
        model = LinearRegression()
        model_name = "test_ml_model"
        self.engine.sklearn_models[model_name] = model
        # get_model_info also accesses model_registry, so add a registry entry
        self.engine.model_registry[model_name] = {
            'hyperparameters': {"test": True},
            'scaler': None,
        }
        result = self.engine.get_model_info(model_name)
        assert result is not None
        assert result["model_type"] == "sklearn"
        assert result["model"] is model
        assert result["hyperparameters"] == {"test": True}

    def test_torch_model_info(self):
        import torch
        import torch.nn as nn
        fake_model = nn.Linear(10, 1)
        self.engine.torch_models["test_torch_model"] = fake_model
        result = self.engine.get_model_info("test_torch_model")
        assert result is not None
        assert result["model_type"] == "torch"
        assert result["model"] is fake_model
        assert "device" in result


class TestExportLearningReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()
        cls.engine.stop_learning_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.performance_optimizer.stop_optimization()

    def test_export_report(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmp_path = f.name
        try:
            self.engine.export_learning_report(tmp_path)
            with open(tmp_path, 'r') as f:
                data = json.load(f)
            assert "timestamp" in data
            assert "learning_engine_status" in data
            assert "performance_history" in data
            assert "hyperparameter_tuning_history" in data
            assert "model_registry" in data
            assert "active_tasks" in data
            assert "best_model" in data
            assert "average_performance" in data
        finally:
            os.unlink(tmp_path)


class TestStopStartLearningEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.performance_optimizer.stop_optimization()

    def test_stop(self):
        self.engine.stop_learning_engine()
        assert self.engine.is_running is False
        assert self.engine.config["learning_enabled"] is False

    def test_start(self):
        self.engine.stop_learning_engine()
        self.engine.start_learning_engine()
        assert self.engine.is_running is True
        assert self.engine.config["learning_enabled"] is True
        self.engine.stop_learning_engine()


class TestSafeFloat(unittest.TestCase):
    def test_safe_float_normal(self):
        assert AdaptiveLearningEngine._safe_float(3.14) == 3.14

    def test_safe_float_int(self):
        assert AdaptiveLearningEngine._safe_float(42) == 42.0

    def test_safe_float_none(self):
        assert AdaptiveLearningEngine._safe_float(None) == 0.0

    def test_safe_float_invalid(self):
        assert AdaptiveLearningEngine._safe_float("abc") == 0.0

    def test_safe_float_custom_default(self):
        assert AdaptiveLearningEngine._safe_float(None, default=-1.0) == -1.0


class TestCaptureFeedback(unittest.TestCase):
    def setUp(self):
        self.engine = AdaptiveLearningEngine()
        self.engine.stop_learning_engine()
        # Clear any accumulated feedback from background thread activity
        self.engine.knowledge_base["goal_adaptation_feedback"] = []

    def tearDown(self):
        self.engine.stop_learning_engine()
        self.engine.performance_optimizer.stop_optimization()

    def test_feedback_exitoso(self):
        feedback = {
            "adaptation_id": "adapt_001",
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 800.0,
                    "accuracy": 0.92,
                },
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.85,
            },
            "adaptation_context": {
                "expected_metrics": {
                    "response_time": 1000.0,
                    "accuracy": 0.80,
                },
                "context_type": "test",
            },
        }
        result = self.engine._capture_feedback(feedback)
        assert result["success"] is True
        assert result["adaptation_id"] == "adapt_001"
        assert "feedback_metrics" in result
        assert "improvement_analysis" in result
        assert len(self.engine.knowledge_base["goal_adaptation_feedback"]) == 1

    def test_feedback_error_sin_excepcion(self):
        feedback = {}
        result = self.engine._capture_feedback(feedback)
        assert result["success"] is True
        assert result["adaptation_id"] is None

    def test_feedback_non_dict(self):
        result = self.engine._capture_feedback("not a dict")
        assert result["success"] is True  # data becomes {}

    def test_feedback_almacenado(self):
        feedback = {
            "adaptation_id": "adapt_002",
            "execution_result": {"success": False, "performance_metrics": {}},
            "verification_result": {"verified": False, "impact_score": 0.1},
            "adaptation_context": {},
        }
        result = self.engine._capture_feedback(feedback)
        assert result["success"] is True
        feedbacks = self.engine.knowledge_base["goal_adaptation_feedback"]
        assert any(f["adaptation_id"] == "adapt_002" for f in feedbacks)


class TestAnalyzeGoalLearningPatterns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()
        cls.engine.stop_learning_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.performance_optimizer.stop_optimization()

    def test_analiza_patrones(self):
        patterns = [
            {"pattern_type": "goal_adaptation_success", "confidence": 0.8,
             "context": {"context_type": "test"}, "metrics": {"impact_score": 0.8}},
        ]
        metrics = {"impact_score": 0.8}
        result = self.engine._analyze_goal_learning_patterns(patterns, metrics)
        assert len(result) == 1
        assert result[0]["pattern_type"] == "goal_adaptation_success"
        assert "pattern_id" in result[0]
        assert "description" in result[0]

    def test_empty_patterns(self):
        result = self.engine._analyze_goal_learning_patterns([], {"impact_score": 0.5})
        assert result == []

    def test_non_dict_pattern(self):
        result = self.engine._analyze_goal_learning_patterns(["not a dict"], {"impact_score": 0.5})
        assert result == []


class TestDescribeGoalLearningPattern(unittest.TestCase):
    def test_describe(self):
        pattern = {"pattern_type": "goal_adaptation_success", "context": {"context_type": "test_ctx"}}
        desc = AdaptiveLearningEngine._describe_goal_learning_pattern(pattern)
        assert "goal_adaptation_success" in desc
        assert "test_ctx" in desc

    def test_describe_default_context(self):
        pattern = {"pattern_type": "unknown"}
        desc = AdaptiveLearningEngine._describe_goal_learning_pattern(pattern)
        assert "unknown" in desc


class TestCalculateGoalLearningConvergence(unittest.TestCase):
    def test_converged(self):
        metrics = {"impact_score": 0.7, "verified": True, "success": True}
        result = AdaptiveLearningEngine._calculate_goal_learning_convergence(metrics, 0.5)
        assert result["converged"] is True
        assert result["impact_score"] == 0.7
        assert result["stability"] == 0.7

    def test_no_verified(self):
        metrics = {"impact_score": 0.7, "verified": False, "success": True}
        result = AdaptiveLearningEngine._calculate_goal_learning_convergence(metrics, 0.5)
        assert result["converged"] is False

    def test_low_impact(self):
        metrics = {"impact_score": 0.3, "verified": True, "success": True}
        result = AdaptiveLearningEngine._calculate_goal_learning_convergence(metrics, 0.5)
        assert result["converged"] is False  # impact < 0.5

    def test_zero_improvement(self):
        metrics = {"impact_score": 0.0, "verified": False, "success": False}
        result = AdaptiveLearningEngine._calculate_goal_learning_convergence(metrics, 0.0)
        assert result["converged"] is False
        assert result["improvement"] == 0.0


class TestExecuteLearningLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AdaptiveLearningEngine()
        cls.engine.stop_learning_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.performance_optimizer.stop_optimization()

    def test_execute_con_feedback_exitoso(self):
        # Clear any prior feedback/patterns
        self.engine.knowledge_base["goal_adaptation_feedback"] = []
        self.engine.knowledge_base["learning_patterns"] = []
        feedback = {
            "success": True,
            "adaptation_id": "test_001",
            "improvement_analysis": {
                "pattern_recognition": [
                    {"pattern_type": "goal_adaptation_success", "confidence": 0.8,
                     "context": {"context_type": "test"},
                     "metrics": {"impact_score": 0.8, "success": True, "verified": True}}
                ],
            },
            "feedback_metrics": {"impact_score": 0.8, "success": True, "verified": True},
        }
        result = self.engine._execute_learning_loop(feedback)
        assert result["success"] is True
        assert "learned_patterns" in result
        assert "adaptation_strategies" in result
        assert "convergence_metrics" in result
        assert result["adaptation_id"] == "test_001"

    def test_execute_con_feedback_fallido(self):
        feedback = {"success": False, "adaptation_id": "test_002"}
        result = self.engine._execute_learning_loop(feedback)
        assert result["success"] is False
        assert "message" in result

    def test_execute_non_dict(self):
        result = self.engine._execute_learning_loop("not a dict")
        assert result["success"] is False



# --- From test_goal_adaptation_learning_loop.py ---
def test_goal_adaptation_learning_loop():
    """Test del bucle de aprendizaje continuo para adaptaciÃ³n de Goal"""
    
    print("=== Test 2.8.8.8: Bucle de Aprendizaje Continuo de AdaptaciÃ³n de Goal ===")
    
    # Crear instancia del motor
    engine = AdaptiveLearningEngine()
    
    # Simular mÃºltiples ciclos de feedback acumulado
    feedback_cycles = [
        {
            "adaptation_id": "learning_cycle_001",
            "original_goal_id": "goal_original_001",
            "adapted_goal_id": "goal_adapted_001",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 2.0,
                    "accuracy": 0.95
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 1.8,  # Ligera mejora
                    "accuracy": 0.96
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.7
            }
        },
        {
            "adaptation_id": "learning_cycle_002",
            "original_goal_id": "goal_original_001",
            "adapted_goal_id": "goal_adapted_002",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 1.8,  # Esperando mejorÃ­a
                    "accuracy": 0.96
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 1.5,  # Mejora significativa
                    "accuracy": 0.98
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.9
            }
        },
        {
            "adaptation_id": "learning_cycle_003",
            "original_goal_id": "goal_original_001",
            "adapted_goal_id": "goal_adapted_003",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 1.5,  # Esperando mantener
                    "accuracy": 0.98
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 1.4,  # ContinÃºa mejorando
                    "accuracy": 0.99
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.95
            }
        }
    ]
    
    # Ejecutar bucle de aprendizaje continuo
    learning_results = []
    for i, feedback_data in enumerate(feedback_cycles):
        print(f"\n--- Ciclo de Aprendizaje {i+1} ---")
        
        # Capturar feedback individual
        feedback_result = engine._capture_feedback(feedback_data)
        learning_results.append(feedback_result)
        
        print(f"Feedback capturado: {feedback_result.get('success', False)}")
        print(f"AnÃ¡lisis de mejora: {feedback_result.get('improvement_analysis', {})}")
        
        # Ejecutar bucle de aprendizaje continuo
        learning_loop_result = engine._execute_learning_loop(feedback_result)
        learning_results.append(learning_loop_result)
        
        print(f"Bucle de aprendizaje ejecutado: {learning_loop_result.get('success', False)}")
        print(f"Patrones aprendidos: {learning_loop_result.get('learned_patterns', [])}")
    
    # Verificar acumulaciÃ³n de aprendizaje
    print("\n=== VerificaciÃ³n de Aprendizaje Acumulado ===")
    
    # Verificar patrones de Ã©xito acumulados
    if "goal_adaptation_feedback" in engine.knowledge_base:
        feedback_records = engine.knowledge_base["goal_adaptation_feedback"]
        print(f"Registros de feedback acumulados: {len(feedback_records)}")
        
        if feedback_records:
            # Calcular tendencia de mejora
            response_times = []
            accuracies = []
            
            for record in feedback_records:
                exec_result = record.get("execution_result", {})
                metrics = exec_result.get("performance_metrics", {})
                
                if "response_time" in metrics:
                    response_times.append(metrics["response_time"])
                if "accuracy" in metrics:
                    accuracies.append(metrics["accuracy"])
            
            if response_times:
                print(f"Tendencia de tiempo de respuesta: {response_times[0]:.2f} -> {response_times[-1]:.2f}")
            if accuracies:
                print(f"Tendencia de precisiÃ³n: {accuracies[0]:.2f} -> {accuracies[-1]:.2f}")
    
    # Verificar estrategias adaptativas aprendidas
    if "adaptation_strategies" in engine.knowledge_base:
        strategies = engine.knowledge_base["adaptation_strategies"]
        if "successful_strategies" in strategies:
            print(f"Estrategias exitosas aprendidas: {len(strategies['successful_strategies'])}")
            
            for strategy in strategies["successful_strategies"]:
                print(f"  - {strategy.get('strategy_name', 'unknown')}: {strategy.get('success_rate', 0.0):.2f}")
    
    # Verificar patrones de aprendizaje
    if "learning_patterns" in engine.knowledge_base:
        patterns = engine.knowledge_base["learning_patterns"]
        print(f"Patrones de aprendizaje: {len(patterns)}")
        
        for pattern in patterns:
            print(f"  - {pattern.get('pattern_type', 'unknown')}: {pattern.get('confidence', 0.0):.2f}")
    
    print("âœ… Test de bucle de aprendizaje continuo completado")
    return True

def test_learning_convergence():
    """Test de convergencia del aprendizaje"""
    
    print("\n=== Test: Convergencia del Aprendizaje ===")
    
    engine = AdaptiveLearningEngine()
    
    # Simular mÃºltiples ciclos con el mismo objetivo para ver convergencia
    goal_id = "convergence_test_goal"
    
    for cycle in range(5):
        feedback_data = {
            "adaptation_id": f"convergence_cycle_{cycle}",
            "original_goal_id": goal_id,
            "adapted_goal_id": f"adapted_goal_{cycle}",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 2.0 - (cycle * 0.2),  # Mejora progresiva
                    "accuracy": 0.90 + (cycle * 0.02)
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 2.0 - (cycle * 0.3),  # Mejora mayor
                    "accuracy": 0.90 + (cycle * 0.03)
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.6 + (cycle * 0.08)
            }
        }
        
        # Ejecutar bucle de aprendizaje
        feedback_result = engine._capture_feedback(feedback_data)
        learning_result = engine._execute_learning_loop(feedback_result)
        
        print(f"Ciclo {cycle+1}: Impacto = {learning_result.get('impact_score', 0.0):.2f}")
    
    # Verificar convergencia
    if "goal_adaptation_feedback" in engine.knowledge_base:
        records = engine.knowledge_base["goal_adaptation_feedback"]
        if len(records) >= 2:
            first_impact = records[0].get("verification_result", {}).get("impact_score", 0.0)
            last_impact = records[-1].get("verification_result", {}).get("impact_score", 0.0)
            
            improvement = last_impact - first_impact
            print(f"Mejora total en convergencia: {improvement:.2f}")
            
            if improvement > 0.3:
                print("âœ… Convergencia exitosa detectada")
                return True
            else:
                print("âš ï¸ Convergencia parcial o no detectada")
                return False
    
    return False

def test_learning_adaptation_strategies():
    """Test de estrategias de adaptaciÃ³n aprendidas"""
    
    print("\n=== Test: Estrategias de AdaptaciÃ³n Aprendidas ===")
    
    engine = AdaptiveLearningEngine()
    
    # Simular diferentes tipos de adaptaciÃ³n
    adaptation_scenarios = [
        {
            "adaptation_id": "strategy_test_1",
            "goal_type": "navigate",
            "adaptation_context": {"complexity": "low"},
            "execution_result": {"success": True, "performance_metrics": {"response_time": 1.0}},
            "verification_result": {"verified": True, "impact_score": 0.8}
        },
        {
            "adaptation_id": "strategy_test_2", 
            "goal_type": "navigate",
            "adaptation_context": {"complexity": "medium"},
            "execution_result": {"success": True, "performance_metrics": {"response_time": 1.5}},
            "verification_result": {"verified": True, "impact_score": 0.7}
        },
        {
            "adaptation_id": "strategy_test_3",
            "goal_type": "navigate", 
            "adaptation_context": {"complexity": "high"},
            "execution_result": {"success": True, "performance_metrics": {"response_time": 2.0}},
            "verification_result": {"verified": True, "impact_score": 0.6}
        }
    ]
    
    for scenario in adaptation_scenarios:
        feedback_data = {
            "adaptation_id": scenario["adaptation_id"],
            "original_goal_id": "test_goal",
            "adapted_goal_id": f"adapted_{scenario['adaptation_id']}",
            "adaptation_context": scenario["adaptation_context"],
            "execution_result": scenario["execution_result"],
            "verification_result": scenario["verification_result"]
        }
        
        feedback_result = engine._capture_feedback(feedback_data)
        learning_result = engine._execute_learning_loop(feedback_result)
        
        print(f"Estrategia para {scenario['adaptation_context']['complexity']}: "
              f"impacto = {learning_result.get('impact_score', 0.0):.2f}")
    
    # Verificar estrategias aprendidas
    if "adaptation_strategies" in engine.knowledge_base:
        strategies = engine.knowledge_base["adaptation_strategies"]
        if "successful_strategies" in strategies:
            print(f"Estrategias aprendidas: {len(strategies['successful_strategies'])}")
            
            for strategy in strategies["successful_strategies"]:
                context = strategy.get("context", {})
                strategy_name = strategy.get("strategy_name", "unknown")
                success_rate = strategy.get("success_rate", 0.0)
                
                print(f"  - {strategy_name} para {context}: {success_rate:.2f}")
    
    return True

if __name__ == "__main__":
    # Ejecutar tests
    test_goal_adaptation_learning_loop()
    test_learning_convergence()
    test_learning_adaptation_strategies()
    
    print("\nðŸŽ‰ Todos los tests del bucle de aprendizaje continuo completados")



