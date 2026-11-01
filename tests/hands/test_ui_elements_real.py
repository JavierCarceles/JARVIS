"""
Tests realistas de elementos UI para JARVIS — FASE 3.4.4.2

Tests basados en las clases y métodos realmente existentes en el sistema.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.hands.applications_core import ApplicationManager, UIElement, ApplicationKnowledge
from src.hands.coordinate_manager import CoordinateManager
from src.hands.calibration_manager import CalibrationManager


class TestUIElementReal:
    """Tests realistas para elementos UI"""
    
    def test_ui_element_creation_real(self):
        """Test de creación real de elementos UI"""
        # Usar la estructura real de UIElement
        element = UIElement(
            type="button",
            name="Aceptar",
            coordinates={"x": 100, "y": 200, "width": 80, "height": 30}
        )
        
        assert element.type == "button"
        assert element.name == "Aceptar"
        assert element.coordinates["x"] == 100
        assert element.coordinates["y"] == 200
        
    def test_application_manager_initialization(self):
        """Test de inicialización real del gestor de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Verificar que se inicializa correctamente
        assert app_manager is not None
        assert hasattr(app_manager, 'applications')
        assert hasattr(app_manager, 'memory_manager')
        
        # Verificar que tiene aplicaciones cargadas
        assert len(app_manager.applications) > 0
        
    def test_application_knowledge_structure(self):
        """Test de estructura de conocimiento de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Verificar el conocimiento de cada aplicación
        for app_name, app_knowledge in app_manager.applications.items():
            assert isinstance(app_knowledge, ApplicationKnowledge)
            assert hasattr(app_knowledge, 'name')
            assert hasattr(app_knowledge, 'type')
            assert hasattr(app_knowledge, 'capabilities')
            assert len(app_knowledge.capabilities) > 0
            
    def test_application_capabilities(self):
        """Test de capacidades de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Probar normalización de nombres (método real)
        normalized = app_manager._normalize_name("Google Chrome")
        assert normalized == "chrome"
        
        normalized = app_manager._normalize_name("Chrome")
        assert normalized == "chrome"
        
        normalized = app_manager._normalize_name("microsoft edge")
        assert normalized == "edge"
        
    def test_coordinate_manager_initialization(self):
        """Test de inicialización real del gestor de coordenadas"""
        coord_manager = CoordinateManager()
        
        assert coord_manager is not None
        # Verificar que tiene los métodos esperados
        assert hasattr(coord_manager, 'get_calibration')
        assert hasattr(coord_manager, 'save_calibration')
        
    @patch('src.hands.coordinate_manager.get_calibration')
    def test_coordinate_retrieval_real(self, mock_get):
        """Test real de recuperación de coordenadas"""
        # Simular datos de calibración reales
        mock_coords = {
            "x": 200, 
            "y": 300, 
            "width": 80, 
            "height": 40,
            "application": "chrome"
        }
        mock_get.return_value = mock_coords
        
        coord_manager = CoordinateManager()
        
        # Probar la recuperación
        coords = coord_manager.get_calibration("test_button")
        
        # Verificar que se llamó correctamente
        mock_get.assert_called_once_with("test_button")
        assert coords == mock_coords
        
    @patch('src.hands.coordinate_manager.save_calibration')
    def test_coordinate_saving_real(self, mock_save):
        """Test real de guardado de coordenadas"""
        test_coords = {
            "x": 150, 
            "y": 250, 
            "width": 100, 
            "height": 50,
            "application": "chrome"
        }
        element_name = "save_button"
        
        coord_manager = CoordinateManager()
        
        # Llamar al método de guardado
        coord_manager.save_calibration(element_name, test_coords)
        
        # Verificar que se llamó correctamente
        mock_save.assert_called_once_with(element_name, test_coords)
        
    def test_calibration_manager_initialization(self):
        """Test de inicialización real del gestor de calibración"""
        calib_manager = CalibrationManager()
        
        assert calib_manager is not None
        # Verificar que tiene los métodos esperados
        assert hasattr(calib_manager, 'get_calibration_manager')
        
    def test_ui_element_types(self):
        """Test de tipos de elementos UI existentes"""
        # Crear diferentes tipos de elementos UI
        button = UIElement(
            type="button",
            name="Enviar",
            coordinates={"x": 100, "y": 100, "width": 80, "height": 30}
        )
        
        input_field = UIElement(
            type="input_field",
            name="Buscar",
            coordinates={"x": 200, "y": 100, "width": 200, "height": 25}
        )
        
        checkbox = UIElement(
            type="checkbox",
            name="Recordar",
            coordinates={"x": 300, "y": 100, "width": 15, "height": 15}
        )
        
        assert button.type == "button"
        assert input_field.type == "input_field"
        assert checkbox.type == "checkbox"
        
    def test_application_capabilities_existence(self):
        """Test de existencia de capacidades en aplicaciones"""
        app_manager = ApplicationManager()
        
        # Verificar que algunas aplicaciones tienen capacidades esperadas
        for app_name, app_knowledge in app_manager.applications.items():
            capabilities = app_knowledge.capabilities
            assert len(capabilities) > 0
            
            # Verificar que las capacidades tienen la estructura esperada
            for cap in capabilities:
                assert hasattr(cap, 'capability')
                assert hasattr(cap, 'name')
                assert hasattr(cap, 'description')
                assert hasattr(cap, 'required_ui_elements')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])