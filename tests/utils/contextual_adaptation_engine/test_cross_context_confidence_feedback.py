"""
Tests para 2.8.5.6 — CONFIDENCIA/FEEDBACK
Tests de confianza en transferencias de conocimiento y feedback
"""

import pytest
from datetime import datetime, timedelta
from src.utils.contextual_adaptation_engine import (
    ContextualAdaptationEngine,
    ContextType,
    KnowledgeTransfer,
    AdaptationRule
)


class TestTransferConfidence:
    """Tests para obtener confianza en transferencias de conocimiento"""

    @pytest.fixture
    def engine(self):
        """Fixture con motor de adaptación contextual"""
        return ContextualAdaptationEngine()

    def test_get_transfer_confidence_basic(self, engine):
        """Test: Obtener confianza básica de una transferencia"""
        # Crear una transferencia simulada
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_1",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            knowledge_data={},
            transfer_efficiency=0.85,
            success_rate=0.8,
            last_transfer=datetime.now()
        )

        # Registrar transferencia
        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Obtener confianza
        confidence = engine.get_transfer_confidence(transfer.transfer_id)

        # Verificar que la confianza está en rango válido
        assert 0.0 <= confidence <= 1.0
        assert confidence == 0.85  # Debería ser igual a transfer_efficiency por defecto

    def test_get_transfer_confidence_with_result(self, engine):
        """Test: Obtener confianza con resultado de transferencia"""
        # Crear transferencia
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_2",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.LEARNING,
            knowledge_type="patterns",
            knowledge_data={},
            transfer_efficiency=0.6,
            success_rate=0.7,
            last_transfer=datetime.now()
        )

        # Registrar resultado simulado
        result = {
            "success_rate": 0.9,
            "success": True,
            "metrics": {
                "performance_improvement": 0.15
            }
        }

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Obtener confianza con resultado
        confidence = engine.get_transfer_confidence(transfer.transfer_id, result)

        # Verificar que la confianza pondera múltiples factores
        assert 0.0 <= confidence <= 1.0
        # Debería ser mayor que transfer_efficiency por sí solo debido al resultado exitoso
        assert confidence > 0.6

    def test_get_transfer_confidence_nonexistent(self, engine):
        """Test: Obtener confianza de transferencia inexistente"""
        confidence = engine.get_transfer_confidence("nonexistent_transfer")

        # Debería devolver 0.0 para transferencia no encontrada
        assert confidence == 0.0

    def test_get_transfer_confidence_zero_efficiency(self, engine):
        """Test: Obtener confianza con eficiencia cero"""
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_3",
            source_context=ContextType.PRODUCTION,
            target_context=ContextType.OPTIMIZATION,
            knowledge_type="baselines",
            transfer_efficiency=0.0,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer
        confidence = engine.get_transfer_confidence(transfer.transfer_id)

        assert confidence == 0.0


class TestTransferFeedback:
    """Tests para registrar feedback en transferencias de conocimiento"""

    @pytest.fixture
    def engine(self):
        """Fixture con motor de adaptación contextual"""
        return ContextualAdaptationEngine()

    def test_register_feedback_basic(self, engine):
        """Test: Registrar feedback básico en una transferencia"""
        # Crear transferencia
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_4",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            transfer_efficiency=0.75,
            success_rate=0.7,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Registrar feedback
        feedback_data = {
            "quality": 0.85,
            "useful": True,
            "content_quality": "high"
        }

        result = engine.register_feedback(transfer.transfer_id, feedback_data)

        # Verificar que se registró correctamente
        assert result is True

        # Verificar que la transferencia se actualizó
        updated_transfer = engine.knowledge_transfers[transfer.transfer_id]
        assert updated_transfer.confidence_score == 0.85
        assert updated_transfer.last_feedback is not None

    def test_register_feedback_with_result(self, engine):
        """Test: Registrar feedback con resultado de aplicación"""
        # Crear transferencia
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_5",
            source_context=ContextType.TESTING,
            target_context=ContextType.PRODUCTION,
            knowledge_type="patterns",
            transfer_efficiency=0.65,
            success_rate=0.6,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Registrar resultado de aplicación
        result = {
            "success_rate": 0.95,
            "success": True,
            "metrics": {
                "performance_improvement": 0.25
            }
        }

        feedback_data = {
            "quality": 0.9,
            "useful": True
        }

        result = engine.register_feedback(transfer.transfer_id, feedback_data, result)

        assert result is True

        # Verificar que se actualizaron las métricas
        updated_transfer = engine.knowledge_transfers[transfer.transfer_id]
        assert updated_transfer.success_rate == 0.95
        assert updated_transfer.confidence_score == 0.9

    def test_register_feedback_nonexistent(self, engine):
        """Test: Registrar feedback en transferencia inexistente"""
        feedback_data = {
            "quality": 0.8,
            "useful": True
        }

        result = engine.register_feedback("nonexistent_transfer", feedback_data)

        # Debería devolver False
        assert result is False

    def test_register_feedback_quality_update(self, engine):
        """Test: Actualizar calidad del conocimiento transferido"""
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_6",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.LEARNING,
            knowledge_type="strategies",
            transfer_efficiency=0.5,
            confidence_score=0.5,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        feedback_data = {
            "quality": 0.95,
            "useful": True
        }

        engine.register_feedback(transfer.transfer_id, feedback_data)

        updated_transfer = engine.knowledge_transaptors[transfer.transfer_id]

        # Verificar que la calidad se actualizó correctamente
        assert updated_transfer.confidence_score == 0.95


class TestTransferResultEvaluation:
    """Tests para evaluar resultados de transferencias de conocimiento"""

    @pytest.fixture
    def engine(self):
        """Fixture con motor de adaptación contextual"""
        return ContextualAdaptationEngine()

    def test_evaluate_transfer_result_success(self, engine):
        """Test: Evaluar resultado exitoso de transferencia"""
        # Crear transferencia
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_7",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            transfer_efficiency=0.8,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Evaluar resultado exitoso
        result = {
            "success_rate": 0.95,
            "success": True,
            "metrics": {
                "performance_improvement": 0.3
            }
        }

        is_successful, score, message = engine.evaluate_transfer_result(
            transfer.transfer_id,
            result
        )

        # Verificar resultado
        assert is_successful is True
        assert score >= 0.7
        assert "successful" in message
        assert "0.95" in message

    def test_evaluate_transfer_result_partial(self, engine):
        """Test: Evaluar resultado parcial de transferencia"""
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_8",
            source_context=ContextType.PRODUCTION,
            target_context=ContextType.OPTIMIZATION,
            knowledge_type="baselines",
            transfer_efficiency=0.6,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Evaluar resultado parcial
        result = {
            "success_rate": 0.5,
            "success": True,
            "metrics": {
                "performance_improvement": 0.1
            }
        }

        is_successful, score, message = engine.evaluate_transfer_result(
            transfer.transfer_id,
            result
        )

        # Verificar resultado
        assert is_successful is False
        assert score < 0.7
        assert "partial" in message

    def test_evaluate_transfer_result_failure(self, engine):
        """Test: Evaluar resultado fallido de transferencia"""
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_9",
            source_context=ContextType.TESTING,
            target_context=ContextType.PRODUCTION,
            knowledge_type="patterns",
            transfer_efficiency=0.4,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Evaluar resultado fallido
        result = {
            "success_rate": 0.2,
            "success": False,
            "metrics": {
                "performance_improvement": 0.0
            }
        }

        is_successful, score, message = engine.evaluate_transfer_result(
            transfer.transfer_id,
            result
        )

        # Verificar resultado
        assert is_successful is False
        assert score < 0.7
        assert "failed" in message

    def test_evaluate_transfer_result_nonexistent(self, engine):
        """Test: Evaluar resultado de transferencia inexistente"""
        result = {
            "success_rate": 0.8,
            "success": True
        }

        is_successful, score, message = engine.evaluate_transfer_result(
            "nonexistent_transfer",
            result
        )

        # Debería devolver False y mensaje de error
        assert is_successful is False
        assert score == 0.0
        assert "not found" in message


class TestFeedbackIntegrationWithExistingMechanisms:
    """Tests de integración de feedback con mecanismos existentes"""

    @pytest.fixture
    def engine(self):
        """Fixture con motor de adaptación contextual"""
        return ContextualAdaptationEngine()

    def test_feedback_updates_transfer_patterns(self, engine):
        """Test: Feedback exitoso actualiza patrones de transferencia"""
        # Ejecutar transferencia exitosa con feedback
        transfer = engine.transfer_knowledge(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            transfer_strategy="adaptive"
        )

        if transfer:
            # Registrar resultado exitoso
            result = {
                "success_rate": 0.95,
                "success": True,
                "metrics": {
                    "performance_improvement": 0.25
                }
            }

            feedback_data = {
                "quality": 0.9,
                "useful": True
            }

            engine.register_feedback(transfer.transfer_id, feedback_data, result)

            # Verificar que se actualizó el patrón de transferencia
            pattern_key = f"{transfer.source_context.value}->{transfer.target_context.value}"
            assert pattern_key in engine.knowledge_base["transfer_patterns"]
            pattern = engine.knowledge_base["transfer_patterns"][pattern_key]
            assert pattern["success_count"] > 0
            assert pattern["avg_success_rate"] >= 0.7

    def test_feedback_does_not_modify_critical_data(self, engine):
        """Test: Feedback no modifica datos críticos de la transferencia"""
        transfer = KnowledgeTransfer(
            transfer_id="test_transfer_10",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            transfer_efficiency=0.7,
            success_rate=0.6,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer.transfer_id] = transfer

        # Registrar feedback
        feedback_data = {
            "quality": 0.95,
            "useful": True
        }

        engine.register_feedback(transfer.transfer_id, feedback_data)

        # Verificar que datos críticos no se modificaron
        updated_transfer = engine.knowledge_transfers[transfer.transfer_id]
        assert updated_transfer.transfer_efficiency == 0.7  # Sin cambios
        assert updated_transfer.knowledge_type == "strategies"  # Sin cambios
        assert updated_transfer.source_context == transfer.source_context  # Sin cambios

        # Solo se modificaron datos de feedback
        assert updated_transfer.confidence_score == 0.95
        assert updated_transfer.last_feedback is not None

    def test_confidence_calculation_uses_existing_mechanisms(self, engine):
        """Test: Cálculo de confianza usa mecanismos existentes"""
        # Crear transferencia con diferentes eficiencias
        transfer1 = KnowledgeTransfer(
            transfer_id="test_transfer_11",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            transfer_efficiency=0.3,
            last_transfer=datetime.now()
        )

        transfer2 = KnowledgeTransfer(
            transfer_id="test_transfer_12",
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="strategies",
            transfer_efficiency=0.9,
            last_transfer=datetime.now()
        )

        engine.knowledge_transfers[transfer1.transfer_id] = transfer1
        engine.knowledge_transfers[transfer2.transfer_id] = transfer2

        # Obtener confianzas
        confidence1 = engine.get_transfer_confidence(transfer1.transfer_id)
        confidence2 = engine.get_transfer_confidence(transfer2.transfer_id)

        # Verificar que la confianza refleja la eficiencia
        assert confidence1 < confidence2
        assert abs(confidence1 - 0.3) < 0.01
        assert abs(confidence2 - 0.9) < 0.01
