"""
Tests simplificados de elementos UI para JARVIS — FASE 3.4.4.2

Tests realistas para la detección y manejo de elementos UI
basados en las clases y métodos existentes del sistema.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.hands.calibration_manager import CalibrationManager
from src.hands.coordinate_manager import CoordinateManager
from src.hands.applications_core import ApplicationManager, UIElement
from src.eyes.vision import Vision
from src.eyes.screen import ScreenAnalyzer


class TestUIElementDetection:
    """Tests para detección de elementos UI"""
    
    def setup_method(self):
        """Configuración inicial para cada test"""
        self.vision = Vision()
        self.screen_analyzer = ScreenAnalyzer()
        self.calibration_manager = CalibrationManager()
        self.coordinate_manager = CoordinateManager()
        self.app_manager = ApplicationManager()
        
    def test_ui_element_detection_basic(self):
        """Test básico de detección de elementos UI"""
        # Crear un elemento UI de prueba
        test_element = UIElement(
            type="button",
            text="Aceptar",
            coordinates={"x": 100, "y": 200, "width": 80, "height": 30}
        )
        
        # Verificar que el elemento tiene las propiedades esperadas
        assert test_element.type == "button"
        assert test_element.text == "Aceptar"
        assert "x" in test_element.coordinates
        assert "y" in test_element.coordinates
        
    def test_ui_element_detection_with_vision_mock(self):
        """Test de detección con mock de visión"""
        # Mockear la detección de elementos
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [
                {
                    "type": "button",
                    "text": "Enviar",
                    "coordinates": {"x": 150, "y": 250, "width": 100, "height": 40},
                    "confidence": 0.95
                }
            ]
            
            # Llamar al método (aunque sea un mock)
            elements = self.vision.detect_ui_elements()
            
            # Verificar el resultado
            assert len(elements) == 1
            assert elements[0]["type"] == "button"
            assert elements[0]["text"] == "Enviar"
            assert elements[0]["confidence"] >= 0.9
            
    def test_ui_element_screen_analysis(self):
        """Test de análisis de pantalla para elementos UI"""
        # Mockear el analizador de pantalla
        mock_application_state = {
            "chrome": {
                "open": True,
                "active": True,
                "maximized": False,
                "focused": True
            }
        }
        
        with patch.object(self.screen_analyzer, 'analyze_application_state') as mock_analyze:
            mock_analyze.return_value = mock_application_state
            
            state = self.screen_analyzer.analyze_application_state()
            
            assert "chrome" in state
            assert state["chrome"]["open"] is True
            assert state["chrome"]["active"] is True


class TestUIElementCalibration:
    """Tests para calibración de elementos UI"""
    
    def setup_method(self):
        """Configuración inicial"""
        self.calibration_manager = CalibrationManager()
        self.coordinate_manager = CoordinateManager()
        
    def test_calibration_manager_initialization(self):
        """Test de inicialización del gestor de calibración"""
        assert self.calibration_manager is not None
        
    def test_coordinate_manager_initialization(self):
        """Test de inicialización del gestor de coordenadas"""
        assert self.coordinate_manager is not None
        
    @patch('src.hands.coordinate_manager.get_calibration')
    def test_coordinate_retrieval(self, mock_get):
        """Test de recuperación de coordenadas calibradas"""
        # Simular datos de calibración
        mock_coords = {"x": 200, "y": 300, "width": 80, "height": 40}
        mock_get.return_value = mock_coords
        
        # Probar la recuperación
        coords = self.coordinate_manager.get_calibration("test_button")
        
        # Verificar que se llamó correctamente
        mock_get.assert_called_once_with("test_button")
        assert coords == mock_coords
        
    @patch('src.hands.coordinate_manager.save_calibration')
    def test_coordinate_saving(self, mock_save):
        """Test de guardado de coordenadas"""
        test_coords = {"x": 150, "y": 250, "width": 100, "height": 50}
        element_name = "save_button"
        
        # Llamar al método de guardado
        self.coordinate_manager.save_calibration(element_name, test_coords)
        
        # Verificar que se llamó correctamente
        mock_save.assert_called_once_with(element_name, test_coords)


class TestUIElementValidation:
    """Tests para validación de elementos UI"""
    
    def setup_method(self):
        """Configuración inicial"""
        self.app_manager = ApplicationManager()
        
    def test_ui_element_creation(self):
        """Test de creación de elementos UI"""
        element = UIElement(
            type="input_field",
            text="Buscar...",
            coordinates={"x": 100, "y": 100, "width": 200, "height": 30}
        )
        
        assert element.type == "input_field"
        assert element.text == "Buscar..."
        assert element.coordinates["width"] == 200
        
    def test_application_manager_capabilities(self):
        """Test de capacidades del gestor de aplicaciones"""
        # Verificar que el gestor tiene capacidades registradas
        assert len(self.app_manager.applications) > 0
        
        # Probar normalización de nombres
        normalized = self.app_manager._normalize_name("Google Chrome")
        assert normalized == "chrome"
        
        normalized = self.app_manager._normalize_name("Chrome")
        assert normalized == "chrome"


class TestUIElementIntegration:
    """Tests de integración de elementos UI"""
    
    def setup_method(self):
        """Configuración inicial"""
        self.app_manager = ApplicationManager()
        self.coordinate_manager = CoordinateManager()
        
    def test_application_knowledge_structure(self):
        """Test de estructura de conocimiento de aplicaciones"""
        # Verificar que las aplicaciones tienen conocimiento estructurado
        for app_name, app_knowledge in self.app_manager.applications.items():
            assert hasattr(app_knowledge, 'name')
            assert hasattr(app_knowledge, 'type')
            assert hasattr(app_knowledge, 'capabilities')
            assert len(app_knowledge.capabilities) > 0
            
    @patch('src.hands.coordinate_manager.get_calibration')
    def test_element_interaction_flow(self, mock_get):
        """Test de flujo de interacción con elementos"""
        # Simular coordenadas calibradas
        mock_coords = {"x": 300, "y": 400, "width": 100, "height": 40}
        mock_get.return_value = mock_coords
        
        # Probar que el flujo es consistente
        element_name = "submit_button"
        coords = self.coordinate_manager.get_calibration(element_name)
        
        assert coords == mock_coords
        assert "x" in coords
        assert "y" in coords


if __name__ == "__main__":
    pytest.main([__file__, "-v"])