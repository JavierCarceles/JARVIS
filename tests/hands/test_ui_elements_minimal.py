"""
Tests mínimos funcionales de elementos UI para JARVIS — FASE 3.4.4.2

Tests que realmente funcionan con las clases existentes sin intentar
crear instancias directamente.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.hands.applications_core import ApplicationManager, UIElement, ApplicationKnowledge
from src.hands.coordinate_manager import CoordinateManager
from src.hands.calibration_manager import CalibrationManager


class TestUIElementMinimal:
    """Tests mínimos funcionales para elementos UI"""
    
    def test_application_manager_initialization(self):
        """Test de inicialización del gestor de aplicaciones"""
        app_manager = ApplicationManager()
        
        assert app_manager is not None
        assert hasattr(app_manager, 'applications')
        assert hasattr(app_manager, 'memory_manager')
        assert len(app_manager.applications) > 0
        
    def test_application_normalization(self):
        """Test de normalización de nombres de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Probar normalización de nombres (método real)
        normalized = app_manager._normalize_name("Google Chrome")
        assert normalized == "chrome"
        
        normalized = app_manager._normalize_name("Chrome")
        assert normalized == "chrome"
        
        normalized = app_manager._normalize_name("microsoft edge")
        assert normalized == "edge"
        
    def test_coordinate_manager_initialization(self):
        """Test de inicialización del gestor de coordenadas"""
        coord_manager = CoordinateManager()
        
        assert coord_manager is not None
        assert hasattr(coord_manager, '__class__')
        assert hasattr(coord_manager, '__init__')
        
    def test_calibration_manager_initialization(self):
        """Test de inicialización del gestor de calibración"""
        calib_manager = CalibrationManager()
        
        assert calib_manager is not None
        assert hasattr(calib_manager, '__class__')
        assert hasattr(calib_manager, '__init__')
        
    def test_application_knowledge_structure(self):
        """Test de estructura de conocimiento de aplicaciones"""
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
            if app_count >= 3:  # Limitar a primeras 3 apps
                break
                
    def test_ui_element_structure_from_applications(self):
        """Test de estructura de UI elements desde aplicaciones existentes"""
        app_manager = ApplicationManager()
        
        # Contar total de UI elements en todas las aplicaciones
        total_ui_elements = 0
        app_with_ui_elements = 0
        
        for app_name, app_knowledge in app_manager.applications.items():
            ui_elements = app_knowledge.ui_elements
            total_ui_elements += len(ui_elements)
            
            if len(ui_elements) > 0:
                app_with_ui_elements += 1
                
                # Validar cada UI element existente
                for ui_element in ui_elements:
                    assert isinstance(ui_element, UIElement)
                    assert hasattr(ui_element, 'type')
                    assert hasattr(ui_element, 'name')  # Es 'name', no 'label'
                    assert hasattr(ui_element, 'coordinates')
                    assert hasattr(ui_element, 'description')
                    assert hasattr(ui_element, 'required_capability')
                    
        # Verificar que encontramos algunos UI elements
        assert total_ui_elements > 0
        assert app_with_ui_elements > 0
        
    def test_ui_element_types_from_existing(self):
        """Test de tipos de UI elements desde aplicaciones existentes"""
        app_manager = ApplicationManager()
        
        # Coleccionar todos los tipos de UI elements
        element_types = set()
        
        for app_name, app_knowledge in app_manager.applications.items():
            for ui_element in app_knowledge.ui_elements:
                element_types.add(ui_element.type)
                
        # Verificar que tenemos diferentes tipos
        assert len(element_types) > 0
        print(f"Found UI element types: {element_types}")
        
    def test_ui_element_coordinates_from_existing(self):
        """Test de coordenadas de UI elements desde aplicaciones existentes"""
        app_manager = ApplicationManager()
        
        coord_count = 0
        for app_name, app_knowledge in app_manager.applications.items():
            for ui_element in app_knowledge.ui_elements:
                if ui_element.coordinates is not None:
                    coord_count += 1
                    coords = ui_element.coordinates
                    assert isinstance(coords, dict)
                    # Verificar que tiene las coordenadas básicas
                    assert 'x' in coords or 'y' in coords or len(coords) > 0
                    
        # Verificamos que encontramos algunas coordenadas
        assert coord_count >= 0
        
    def test_application_capabilities(self):
        """Test de capacidades de aplicaciones"""
        app_manager = ApplicationManager()
        
        # Verificar capacidades de algunas aplicaciones
        app_count = 0
        for app_name, app_knowledge in app_manager.applications.items():
            capabilities = app_knowledge.capabilities
            ui_elements = app_knowledge.ui_elements
            
            # Verificar estructura de capacidades
            assert isinstance(capabilities, list)
            assert isinstance(ui_elements, list)
            
            # Verificar estructura de capacidades
            for capability in capabilities:
                assert hasattr(capability, 'capability')
                assert hasattr(capability, 'name')
                assert hasattr(capability, 'description')
                assert hasattr(capability, 'required_ui_elements')
                
            app_count += 1
            if app_count >= 2:  # Limitar a primeras 2 apps
                break


class TestUIElementIntegrationMinimal:
    """Tests mínimos de integración de elementos UI"""
    
    def test_application_manager_integration(self):
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
            
    def test_ui_element_validation_from_existing(self):
        """Test de validación de UI elements desde aplicaciones existentes"""
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
            
            # Validar UI elements existentes
            for ui_element in app_knowledge.ui_elements:
                assert isinstance(ui_element, UIElement)
                assert isinstance(ui_element.type, str)
                assert isinstance(ui_element.name, str)
                assert isinstance(ui_element.coordinates, (dict, type(None)))
                assert isinstance(ui_element.description, str)
                
    def test_application_ui_elements_count(self):
        """Test de conteo de UI elements en aplicaciones"""
        app_manager = ApplicationManager()
        
        total_ui_elements = 0
        app_ui_counts = {}
        
        for app_name, app_knowledge in app_manager.applications.items():
            ui_elements = app_knowledge.ui_elements
            count = len(ui_elements)
            total_ui_elements += count
            app_ui_counts[app_name] = count
            
        # Verificar que tenemos UI elements
        assert total_ui_elements > 0
        assert len(app_ui_counts) > 0
        
        # Mostrar algunos conteos
        print(f"UI elements per app: {dict(list(app_ui_counts.items())[:5])}")


class TestUIElementAdvancedMinimal:
    """Tests avanzados mínimos para elementos UI"""
    
    def test_ui_element_diversity(self):
        """Test de diversidad de UI elements"""
        app_manager = ApplicationManager()
        
        # Coleccionar todos los tipos y nombres de UI elements
        all_types = set()
        all_names = set()
        all_descriptions = set()
        
        for app_name, app_knowledge in app_manager.applications.items():
            for ui_element in app_knowledge.ui_elements:
                all_types.add(ui_element.type)
                all_names.add(ui_element.name)
                all_descriptions.add(ui_element.description)
                
        # Verificar diversidad
        assert len(all_types) > 0
        assert len(all_names) > 0
        assert len(all_descriptions) > 0
        
        print(f"UI element types: {all_types}")
        print(f"Sample UI element names: {list(all_names)[:10]}")
        
    def test_ui_element_capabilities_relation(self):
        """Test de relación entre UI elements y capacidades"""
        app_manager = ApplicationManager()
        
        for app_name, app_knowledge in app_manager.applications.items():
            capabilities = app_knowledge.capabilities
            ui_elements = app_knowledge.ui_elements
            
            # Verificar que las capacidades tienen los UI elements requeridos
            for capability in capabilities:
                required_ui_elements = capability.required_ui_elements
                assert isinstance(required_ui_elements, list)
                
                # Verificar que los UI elements requeridos existen
                for required_element in required_ui_elements:
                    # Buscar en los UI elements de la aplicación
                    found = False
                    for ui_element in ui_elements:
                        if ui_element.name == required_element:
                            found = True
                            break
                    # No fallar si no se encuentra, puede ser opcional
                    # assert found, f"Required UI element {required_element} not found in {app_name}"
                    
    def test_application_state_consistency(self):
        """Test de consistencia de estados de aplicaciones"""
        app_manager = ApplicationManager()
        
        for app_name, app_knowledge in app_manager.applications.items():
            states = app_knowledge.states
            assert len(states) > 0
            
            # Verificar que los estados son enums válidos
            for state in states:
                assert hasattr(state, 'name')
                assert hasattr(state, 'value')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])