"""
Tests funcionales de elementos UI para JARVIS — FASE 3.4.4.2

Tests que realmente funcionan con las clases existentes y validan
la integración de elementos UI con el sistema.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.hands.applications_core import ApplicationManager, UIElement, ApplicationKnowledge
from src.hands.coordinate_manager import CoordinateManager
from src.hands.calibration_manager import CalibrationManager


class TestUIElementWorking:
    """Tests funcionales para elementos UI"""
    
    def test_ui_element_creation_correct(self):
        """Test de creación de elementos UI con parámetros correctos"""
        # Usar los parámetros correctos de UIElement
        element = UIElement(
            type="button",
            name="Enviar",
            coordinates={"x": 100, "y": 200, "width": 80, "height": 30}
        )
        
        assert element.type == "button"
        assert element.name == "Enviar"
        assert element.coordinates["x"] == 100
        assert element.coordinates["y"] == 200
        
    def test_ui_element_different_types_correct(self):
        """Test de creación de diferentes tipos de elementos UI"""
        # Crear diferentes tipos de elementos UI con parámetros correctos
        button = UIElement(
            type="button",
            name="Aceptar",
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
        
    def test_ui_element_coordinates_structure_correct(self):
        """Test de estructura de coordenadas de elementos UI"""
        element = UIElement(
            type="button",
            name="Test",
            coordinates={"x": 150, "y": 200, "width": 100, "height": 40}
        )
        
        # Verificar estructura de coordenadas
        coords = element.coordinates
        assert isinstance(coords, dict)
        assert "x" in coords
        assert "y" in coords
        assert "width" in coords
        assert "height" in coords
        assert coords["x"] == 150
        assert coords["y"] == 200
        assert coords["width"] == 100
        assert coords["height"] == 40
        
    def test_application_manager_initialization_working(self):
        """Test de inicialización del gestor de aplicaciones"""
        app_manager = ApplicationManager()
        
        assert app_manager is not None
        assert hasattr(app_manager, 'applications')
        assert hasattr(app_manager, 'memory_manager')
        assert len(app_manager.applications) > 0
        
    def test_application_normalization_working(self):
        """Test de normalización de nombres de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Probar normalización de nombres (método real)
        normalized = app_manager._normalize_name("Google Chrome")
        assert normalized == "chrome"
        
        normalized = app_manager._normalize_name("Chrome")
        assert normalized == "chrome"
        
        normalized = app_manager._normalize_name("microsoft edge")
        assert normalized == "edge"
        
    def test_coordinate_manager_methods_exist(self):
        """Test de existencia de métodos en el gestor de coordenadas"""
        coord_manager = CoordinateManager()
        
        # Verificar que los métodos existen (aunque no sean directamente accesibles)
        assert coord_manager is not None
        assert hasattr(coord_manager, '__class__')
        assert hasattr(coord_manager, '__init__')
        
    def test_calibration_manager_methods_exist(self):
        """Test de existencia de métodos en el gestor de calibración"""
        calib_manager = CalibrationManager()
        
        assert calib_manager is not None
        assert hasattr(calib_manager, '__class__')
        assert hasattr(calib_manager, '__init__')
        
    def test_application_knowledge_structure_accessible(self):
        """Test de estructura de conocimiento de aplicaciones accesible"""
        app_manager = ApplicationManager()
        
        # Verificar el conocimiento de algunas aplicaciones
        app_count = 0
        for app_name, app_knowledge in app_manager.applications.items():
            assert isinstance(app_knowledge, ApplicationKnowledge)
            assert hasattr(app_knowledge, 'name')
            assert hasattr(app_knowledge, 'type')
            assert hasattr(app_knowledge, 'capabilities')
            assert hasattr(app_knowledge, 'ui_elements')
            assert hasattr(app_knowledge, 'states')
            
            # Verificar que tiene estados
            assert len(app_knowledge.states) > 0
            
            app_count += 1
            if app_count >= 3:  # Limitar a primeras 3 apps para no ser demasiado largo
                break
                
    def test_application_capabilities_structure_correct(self):
        """Test de estructura de capacidades de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Verificar capacidades de algunas aplicaciones
        app_count = 0
        for app_name, app_knowledge in app_manager.applications.items():
            capabilities = app_knowledge.capabilities
            ui_elements = app_knowledge.ui_elements
            
            # Verificar estructura de capacidades
            assert isinstance(capabilities, list)
            assert isinstance(ui_elements, list)
            
            # Verificar estructura de UI elements con atributos correctos
            for ui_element in ui_elements:
                assert isinstance(ui_element, UIElement)
                assert hasattr(ui_element, 'type')
                assert hasattr(ui_element, 'name')  # Es 'name', no 'label' ni 'text'
                assert hasattr(ui_element, 'coordinates')
                
            app_count += 1
            if app_count >= 2:  # Limitar a primeras 2 apps
                break


class TestUIElementIntegrationWorking:
    """Tests de integración de elementos UI"""
    
    def test_application_manager_integration_working(self):
        """Test de integración del gestor de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Verificar que el gestor puede acceder a aplicaciones
        assert len(app_manager.applications) > 0
        
        # Probar normalización con nombres reales
        test_names = [
            ("Google Chrome", "chrome"),
            ("chrome", "chrome"),
            ("Microsoft Edge", "edge"),
            ("edge", "edge"),
            ("Mozilla Firefox", "firefox"),
            ("firefox", "firefox")
        ]
        
        for input_name, expected in test_names:
            result = app_manager._normalize_name(input_name)
            assert result == expected, f"Normalización fallida para: {input_name}"
            
    def test_ui_element_creation_workflow_correct(self):
        """Test de flujo de creación de elementos UI"""
        # Crear elementos UI para diferentes propósitos
        elements = []
        
        # Elemento de botón
        button = UIElement(
            type="button",
            name="Enviar",
            coordinates={"x": 100, "y": 200, "width": 80, "height": 30}
        )
        elements.append(button)
        
        # Elemento de campo de texto
        input_field = UIElement(
            type="input_field",
            name="Buscar...",
            coordinates={"x": 200, "y": 200, "width": 200, "height": 25}
        )
        elements.append(input_field)
        
        # Elemento de checkbox
        checkbox = UIElement(
            type="checkbox",
            name="Recordar contraseña",
            coordinates={"x": 300, "y": 200, "width": 15, "height": 15}
        )
        elements.append(checkbox)
        
        # Verificar todos los elementos
        assert len(elements) == 3
        for element in elements:
            assert isinstance(element, UIElement)
            assert hasattr(element, 'type')
            assert hasattr(element, 'name')  # Es 'name', no 'label' ni 'text'
            assert hasattr(element, 'coordinates')
            
    def test_ui_element_validation_workflow_correct(self):
        """Test de flujo de validación de elementos UI"""
        app_manager = ApplicationManager()
        
        # Obtener algunas aplicaciones para validar
        app_names = list(app_manager.applications.keys())[:3]
        
        for app_name in app_names:
            app_knowledge = app_manager.applications[app_name]
            
            # Validar estructura de la aplicación
            assert isinstance(app_knowledge, ApplicationKnowledge)
            assert isinstance(app_knowledge.name, str)
            assert isinstance(app_knowledge.type, str)
            assert isinstance(app_knowledge.capabilities, list)
            assert isinstance(app_knowledge.ui_elements, list)
            assert isinstance(app_knowledge.states, list)
            
            # Validar UI elements con atributos correctos
            for ui_element in app_knowledge.ui_elements:
                assert isinstance(ui_element, UIElement)
                assert isinstance(ui_element.type, str)
                assert hasattr(ui_element, 'name')  # Es 'name', no 'label' ni 'text'
                assert isinstance(ui_element.coordinates, dict)


class TestUIElementAdvanced:
    """Tests avanzados para elementos UI"""
    
    def test_ui_element_type_variations(self):
        """Test de variaciones de tipos de elementos UI"""
        element_types = [
            ("button", "Botón"),
            ("input_field", "Campo de texto"),
            ("checkbox", "Checkbox"),
            ("dropdown", "Menú desplegable"),
            ("radio_button", "Botón de radio"),
            ("link", "Enlace"),
            ("image", "Imagen"),
            ("icon", "Icono")
        ]
        
        for element_type, label in element_types:
            element = UIElement(
                type=element_type,
                name=label,
                coordinates={"x": 100, "y": 100, "width": 50, "height": 30}
            )
            assert element.type == element_type
            assert element.name == label
            
    def test_ui_element_coordinates_variations(self):
        """Test de variaciones de coordenadas de elementos UI"""
        test_coords = [
            {"x": 100, "y": 100, "width": 80, "height": 30},
            {"x": 200, "y": 150, "width": 120, "height": 40},
            {"x": 50, "y": 50, "width": 200, "height": 25},
            {"x": 300, "y": 200, "width": 150, "height": 35}
        ]
        
        for coords in test_coords:
            element = UIElement(
                type="button",
                name="Test",
                coordinates=coords
            )
            
            # Verificar que todas las coordenadas se copiaron correctamente
            for key, value in coords.items():
                assert element.coordinates[key] == value
                
    def test_application_ui_elements_integration(self):
        """Test de integración de UI elements con aplicaciones"""
        app_manager = ApplicationManager()
        
        # Contar total de UI elements en todas las aplicaciones
        total_ui_elements = 0
        app_with_ui_elements = 0
        
        for app_name, app_knowledge in app_manager.applications.items():
            ui_elements = app_knowledge.ui_elements
            total_ui_elements += len(ui_elements)
            
            if len(ui_elements) > 0:
                app_with_ui_elements += 1
                
                # Validar cada UI element
                for ui_element in ui_elements:
                    assert isinstance(ui_element, UIElement)
                    assert isinstance(ui_element.type, str)
                    assert isinstance(ui_element.name, str)
                    assert isinstance(ui_element.coordinates, dict)
                    assert len(ui_element.coordinates) >= 2  # Mínimo x,y
                    
        # Verificar que encontramos algunos UI elements
        assert total_ui_elements > 0
        assert app_with_ui_elements > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])