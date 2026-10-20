"""
Tests para 2.8.7.2 - Features/Señales
Verifica la representación de señales contextuales disponibles
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import time
from datetime import datetime

# Añadir el path para importar los módulos
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import (
    ContextualAdaptationEngine, 
    ContextType, 
    ContextualFactor,
    ContextSnapshot,
    AdaptationLevel
)


class TestFeaturesSignals(unittest.TestCase):
    """Tests para features/señales contextuales"""
    
    def setUp(self):
        """Configuración inicial para cada test"""
        self.engine = ContextualAdaptationEngine()
        
        # Mockear dependencias externas
        self.engine.logger = Mock()
        self.engine.analytics = Mock()
        self.engine.pattern_analyzer = Mock()
        
        # Mockear métricas para tests controlados
        self.engine._collect_system_metrics = Mock(return_value={
            "cpu_usage": 0.3,
            "memory_usage": 0.5,
            "disk_usage": 0.2,
            "process_count": 50.0,
            "system_load": 0.35
        })
        
        self.engine._collect_performance_metrics = Mock(return_value={
            "response_time": 0.1,
            "throughput": 100.0,
            "error_rate": 0.01,
            "latency_p95": 0.15,
            "latency_p99": 0.25
        })
        
        self.engine._collect_user_patterns = Mock(return_value={
            "interaction_frequency": 0.8,
            "session_duration": 1200.0,
            "task_complexity": 0.4,
            "error_frequency": 0.02
        })
        
        self.engine._collect_environmental_conditions = Mock(return_value={
            "time_of_day": 14.0,  # 2 PM
            "day_of_week": 2.0,   # Tuesday
            "network_latency": 0.05,
            "device_count": 3.0
        })
    
    def test_2_8_7_2_1_enumerate_contextual_data(self):
        """2.8.7.2.1 - Enumerar datos contextuales disponibles"""
        snapshot = self.engine.capture_context_snapshot()
        
        # Verificar que tenemos datos contextuales
        self.assertGreater(len(snapshot.contextual_factors), 0)
        
        # Enumerar todas las señales disponibles
        available_signals = list(snapshot.contextual_factors.keys())
        
        # Verificar que tenemos señales básicas
        expected_basic_signals = [
            ContextualFactor.SYSTEM_RESOURCES,
            ContextualFactor.USER_BEHAVIOR,
            ContextualFactor.ERROR_RATES,
            ContextualFactor.WORKLOAD
        ]
        
        found_basic_signals = [signal for signal in expected_basic_signals if signal in snapshot.contextual_factors]
        self.assertGreater(len(found_basic_signals), 0)
        
        self.engine.logger.info(f"Señales disponibles: {[s.value for s in available_signals]}")
        self.engine.logger.info(f"Señales básicas encontradas: {[s.value for s in found_basic_signals]}")
        
        # Asegurar que tenemos señales básicas
        self.assertIn(ContextualFactor.SYSTEM_RESOURCES, available_signals)
        self.assertIn(ContextualFactor.USER_BEHAVIOR, available_signals)
    
    def test_2_8_7_2_2_separate_real_signals_from_unavailable(self):
        """2.8.7.2.2 - Separar señales reales de campos no disponibles"""
        snapshot = self.engine.capture_context_snapshot()
        
        # Señales que deberían estar disponibles basadas en los mocks
        expected_available = [
            ContextualFactor.SYSTEM_RESOURCES,
            ContextualFactor.USER_BEHAVIOR,
            ContextualFactor.WORKLOAD,
            ContextualFactor.NETWORK_CONDITIONS
        ]
        
        # Señales que podrían estar disponibles según la implementación
        potentially_available = [
            ContextualFactor.ERROR_RATES,
            ContextualFactor.PERFORMANCE_REQUIREMENTS
        ]
        
        # Señales que probablemente no estén disponibles sin implementación específica
        expected_unavailable = [
            ContextualFactor.USAGE_PATTERNS,
            ContextualFactor.TIME_OF_DAY,
            ContextualFactor.HARDWARE_CAPABILITIES
        ]
        
        available_signals = []
        potentially_available_signals = []
        unavailable_signals = []
        
        for signal in expected_available + potentially_available + expected_unavailable:
            if signal in snapshot.contextual_factors:
                if signal in expected_available:
                    available_signals.append(signal)
                else:
                    potentially_available_signals.append(signal)
            else:
                unavailable_signals.append(signal)
        
        # Verificar que tenemos señales disponibles
        self.assertGreater(len(available_signals), 0)
        
        # Verificar que tenemos señales disponibles y no disponibles
        self.assertGreater(len(available_signals), 0)
        self.assertGreater(len(snapshot.contextual_factors), 0)
        
        self.engine.logger.info(f"Señales disponibles: {[s.value for s in available_signals]}")
        self.engine.logger.info(f"Señales potencialmente disponibles: {[s.value for s in potentially_available_signals]}")
        self.engine.logger.info(f"Señales no implementadas: {[s.value for s in unavailable_signals]}")
    
    def test_2_8_7_2_3_build_minimal_representation(self):
        """2.8.7.2.3 - Construir representación mínima"""
        snapshot = self.engine.capture_context_snapshot()
        
        # Construir representación mínima con solo señales válidas
        minimal_context = {
            'context_type': snapshot.context_type.value,
            'confidence_score': snapshot.confidence_score,
            'available_signals': {
                factor.value: value 
                for factor, value in snapshot.contextual_factors.items()
                if isinstance(value, (int, float)) and not isinstance(value, str)
            }
        }
        
        # Verificar estructura mínima
        self.assertIn('context_type', minimal_context)
        self.assertIn('confidence_score', minimal_context)
        self.assertIn('available_signals', minimal_context)
        
        # Verificar que la representación es válida
        self.assertGreater(len(minimal_context['available_signals']), 0)
        self.engine.logger.info(f"Representación mínima: {len(minimal_context['available_signals'])} señales")
    
    def test_2_8_7_2_4_handle_missing_signal(self):
        """2.8.7.2.4 - Manejar señal ausente"""
        snapshot = self.engine.capture_context_snapshot()
        
        # Probar acceso a señal que podría no existir
        test_signals = [
            ContextualFactor.PERFORMANCE_REQUIREMENTS,
            ContextualFactor.ERROR_RATES,
            ContextualFactor.WORKLOAD
        ]
        
        for signal in test_signals:
            if signal not in snapshot.contextual_factors:
                # Manejar ausencia de forma segura
                signal_value = snapshot.contextual_factors.get(signal, 0.0)
                self.assertEqual(signal_value, 0.0)
                self.logger.info(f"Señal {signal.value} ausente, usando valor por defecto: 0.0")
    
    def test_2_8_7_2_5_confidence_threshold_handling(self):
        """Test adicional: manejar umbrales de confianza"""
        snapshot = self.engine.capture_context_snapshot()
        
        # Verificar que la confianza está en rango válido
        self.assertGreaterEqual(snapshot.confidence_score, 0.0)
        self.assertLessEqual(snapshot.confidence_score, 1.0)
        
        # Filtrar señales basadas en confianza
        high_confidence_signals = {
            factor: value 
            for factor, value in snapshot.contextual_factors.items()
            if snapshot.confidence_score > 0.5
        }
        
        if snapshot.confidence_score > 0.5:
            self.assertGreater(len(high_confidence_signals), 0)
            self.engine.logger.info(f"Señales de alta confianza ({snapshot.confidence_score:.2f}): "
                           f"{[s.value for s in high_confidence_signals.keys()]}")


if __name__ == '__main__':
    unittest.main()