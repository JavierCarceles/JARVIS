"""
Tests para ContextualPatternRecognizer
"""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from src.utils.contextual_pattern_recognizer import ContextualPatternRecognizer, ContextualPatternType
from src.utils.contextual_adaptation_engine import ContextSnapshot, ContextualFactor, ContextType
from src.utils.pattern_analyzer import PatternSeverity


class TestContextualPatternRecognizer(unittest.TestCase):
    
    def setUp(self):
        """Configuración inicial para cada test."""
        self.recognizer = ContextualPatternRecognizer()
        
        # Crear un mock snapshot para pruebas
        self.mock_snapshot = Mock(spec=ContextSnapshot)
        self.mock_snapshot.contextual_factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.9,
            ContextualFactor.USER_BEHAVIOR: 0.8,
            ContextualFactor.NETWORK_CONDITIONS: 0.7,
            ContextualFactor.ERROR_RATES: 0.05
        }
        self.mock_snapshot.context_type = ContextType.PRODUCTION
        self.mock_snapshot.timestamp = datetime.now()
    
    def test_detect_contextual_anomaly(self):
        """Test de detección de anomalías contextuales."""
        pattern = self.recognizer._detect_contextual_anomaly(self.mock_snapshot)
        
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.type, ContextualPatternType.CONTEXTUAL_ANOMALY)
        self.assertEqual(pattern.severity.value, "medium")
        self.assertIn('SYSTEM_RESOURCES', pattern.pattern_data['anomalies'][0]['factor'])
    
    def test_detect_contextual_trend(self):
        """Test de detección de tendencias contextuales."""
        pattern = self.recognizer._detect_contextual_trend(self.mock_snapshot)
        
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.type, ContextualPatternType.CONTEXTUAL_TREND)
        self.assertEqual(pattern.severity.value, "medium")
    
    def test_detect_contextual_correlation(self):
        """Test de detección de correlaciones contextuales."""
        # Modificar snapshot para tener correlación
        self.mock_snapshot.contextual_factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.9,
            ContextualFactor.USER_BEHAVIOR: 0.85,
            ContextualFactor.NETWORK_CONDITIONS: 0.3,
            ContextualFactor.ERROR_RATES: 0.05
        }
        
        pattern = self.recognizer._detect_contextual_correlation(self.mock_snapshot)
        
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.type, ContextualPatternType.CONTEXTUAL_CORRELATION)
        self.assertEqual(pattern.severity.value, "medium")
    
    def test_detect_contextual_seasonal(self):
        """Test de detección de patrones estacionales."""
        # Mockear la hora actual
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 10, 3, 8, 0, 0)  # 8 AM
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            self.mock_snapshot.timestamp = datetime(2026, 10, 3, 8, 0, 0)
            
            pattern = self.recognizer._detect_contextual_seasonal(self.mock_snapshot)
            
            self.assertIsNotNone(pattern)
            self.assertEqual(pattern.type, ContextualPatternType.CONTEXTUAL_SEASONAL)
            self.assertEqual(pattern.severity.value, "low")
    
    def test_detect_contextual_burst(self):
        """Test de detección de patrones de burst."""
        pattern = self.recognizer._detect_contextual_burst(self.mock_snapshot)
        
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.type, ContextualPatternType.CONTEXTUAL_BURST)
        self.assertEqual(pattern.severity.value, "high")
    
    def test_detect_contextual_changepoint(self):
        """Test de detección de puntos de cambio."""
        # Modificar snapshot para tener cambios extremos
        self.mock_snapshot.contextual_factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.95,
            ContextualFactor.USER_BEHAVIOR: 0.1,
            ContextualFactor.NETWORK_CONDITIONS: 0.7,
            ContextualFactor.ERROR_RATES: 0.05
        }
        
        pattern = self.recognizer._detect_contextual_changepoint(self.mock_snapshot)
        
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.type, ContextualPatternType.CONTEXTUAL_CHANGEPOINT)
        self.assertEqual(pattern.severity.value, "high")
    
    def test_add_contextual_pattern(self):
        """Test de añadir patrón contextual."""
        pattern = self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        self.assertIsNotNone(pattern)
        self.assertEqual(len(self.recognizer.contextual_patterns), 1)
        self.assertEqual(self.recognizer.pattern_history[0]['pattern_id'], pattern.id)
    
    def test_get_contextual_patterns(self):
        """Test de obtener patrones por tipo."""
        # Añadir varios patrones
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        # Modificar snapshot para otro patrón
        self.mock_snapshot.contextual_factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.7,
            ContextualFactor.USER_BEHAVIOR: 0.6,
            ContextualFactor.NETWORK_CONDITIONS: 0.5,
            ContextualFactor.ERROR_RATES: 0.02
        }
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        # Obtener todos los patrones
        all_patterns = self.recognizer.get_contextual_patterns()
        self.assertEqual(len(all_patterns), 2)
        
        # Obtener patrones por tipo
        anomaly_patterns = self.recognizer.get_contextual_patterns(ContextualPatternType.CONTEXTUAL_ANOMALY)
        self.assertEqual(len(anomaly_patterns), 1)
    
    def test_get_patterns_by_severity(self):
        """Test de obtener patrones por severidad."""
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        medium_severity_patterns = self.recognizer.get_patterns_by_severity(PatternSeverity.MEDIUM)
        self.assertEqual(len(medium_severity_patterns), 1)
    
    def test_get_high_compatibility_patterns(self):
        """Test de obtener patrones con alta compatibilidad."""
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        high_compat_patterns = self.recognizer.get_high_compatibility_patterns(0.5)
        self.assertEqual(len(high_compat_patterns), 1)
    
    def test_get_pattern_summary(self):
        """Test de obtener resumen de patrones."""
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        summary = self.recognizer.get_pattern_summary()
        self.assertEqual(summary['total_patterns'], 1)
        self.assertIn('by_type', summary)
        self.assertIn('by_severity', summary)
    
    def test_clear_patterns(self):
        """Test de limpiar patrones."""
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        self.assertEqual(len(self.recognizer.contextual_patterns), 1)
        
        self.recognizer.clear_patterns(older_than_hours=0)
        self.assertEqual(len(self.recognizer.contextual_patterns), 0)
    
    def test_export_patterns(self):
        """Test de exportar patrones."""
        self.recognizer.add_contextual_pattern(self.mock_snapshot)
        
        # Mockear la función open para evitar escritura real
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.write = Mock()
            
            self.recognizer.export_patterns("test_export.json")
            
            mock_open.assert_called_once_with("test_export.json", 'w', encoding='utf-8')
    
    def test_no_patterns_detected(self):
        """Test cuando no se detectan patrones."""
        # Crear snapshot sin patrones
        low_usage_snapshot = Mock(spec=ContextSnapshot)
        low_usage_snapshot.contextual_factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.25,
            ContextualFactor.USER_BEHAVIOR: 0.35,
            ContextualFactor.NETWORK_CONDITIONS: 0.15,
            ContextualFactor.ERROR_RATES: 0.12
        }
        low_usage_snapshot.context_type = ContextType.PRODUCTION
        # Use a time that won't trigger seasonal patterns (avoid night hours)
        test_time = datetime(2026, 10, 23, 12, 0, 0)  # noon
        low_usage_snapshot.timestamp = test_time
        
        pattern = self.recognizer.add_contextual_pattern(low_usage_snapshot)
        
        self.assertIsNone(pattern)
        self.assertEqual(len(self.recognizer.contextual_patterns), 0)


if __name__ == '__main__':
    unittest.main()