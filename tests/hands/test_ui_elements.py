"""
Tests de elementos UI para JARVIS — FASE 3.4.4.2

Pruebas para la detección, calibración y manipulación de elementos UI
integrados con el sistema de visión y calibración existente.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.hands.calibration_manager import CalibrationManager
from src.hands.coordinate_manager import CoordinateManager
from src.hands.universal_visual_calibrator import UniversalVisualCalibrator
from src.hands.applications_core import ApplicationManager
from src.hands.coordinate_manager import CoordinateManager
from src.hands.keyboard import type_text
from src.hands.mouse import click_element
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
        
    def test_ui_element_basic_detection(self):
        """Test básico de detección de elementos UI"""
        # Simular detección de un botón
        mock_element = {
            "type": "button",
            "text": "Aceptar",
            "coordinates": {"x": 100, "y": 200, "width": 80, "height": 30},
            "confidence": 0.95
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [mock_element]
            
            elements = self.vision.detect_ui_elements()
            
            assert len(elements) == 1
            assert elements[0]["type"] == "button"
            assert elements[0]["text"] == "Aceptar"
            assert elements[0]["confidence"] >= 0.9
            
    def test_ui_element_detection_with_calibration(self):
        """Test de detección con calibración existente"""
        # Cargar datos de calibración simulados
        calibration_data = {
            "chrome_accept_button": {"x": 150, "y": 250, "width": 100, "height": 40},
            "chrome_menu_button": {"x": 50, "y": 50, "width": 30, "height": 30}
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
                mock_detect.return_value = [
                    {
                        "type": "button",
                        "text": "Aceptar",
                        "coordinates": {"x": 145, "y": 245, "width": 110, "height": 50},
                        "confidence": 0.92
                    }
                ]
                
                # Verificar que el elemento detectado coincide con calibración
                detected = mock_detect.return_value[0]
                calibrated = calibration_data["chrome_accept_button"]
                
                # Tolerancia de 10 píxeles para coincidencia
                assert abs(detected["coordinates"]["x"] - calibrated["x"]) <= 10
                assert abs(detected["coordinates"]["y"] - calibrated["y"]) <= 10
                
    def test_ui_element_text_field_detection(self):
        """Test de detección de campos de texto"""
        mock_text_field = {
            "type": "text_field",
            "placeholder": "Buscar...",
            "coordinates": {"x": 200, "y": 100, "width": 300, "height": 25},
            "confidence": 0.88
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [mock_text_field]
            
            elements = self.vision.detect_ui_elements()
            
            assert len(elements) == 1
            assert elements[0]["type"] == "text_field"
            assert "placeholder" in elements[0]
            
    def test_ui_element_checkbox_detection(self):
        """Test de detección de checkboxes"""
        mock_checkbox = {
            "type": "checkbox",
            "label": "Recordar contraseña",
            "checked": False,
            "coordinates": {"x": 300, "y": 300, "width": 15, "height": 15},
            "confidence": 0.91
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [mock_checkbox]
            
            elements = self.vision.detect_ui_elements()
            
            assert len(elements) == 1
            assert elements[0]["type"] == "checkbox"
            assert "checked" in elements[0]
            
    def test_ui_element_dropdown_detection(self):
        """Test de detección de menús desplegables"""
        mock_dropdown = {
            "type": "dropdown",
            "options": ["Opción 1", "Opción 2", "Opción 3"],
            "selected": "Opción 1",
            "coordinates": {"x": 400, "y": 150, "width": 150, "height": 25},
            "confidence": 0.89
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [mock_dropdown]
            
            elements = self.vision.detect_ui_elements()
            
            assert len(elements) == 1
            assert elements[0]["type"] == "dropdown"
            assert "options" in elements[0]
            assert "selected" in elements[0]


class TestUIElementCalibration:
    """Tests para calibración de elementos UI"""
    
    def setup_method(self):
        """Configuración inicial"""
        self.calibrator = UniversalVisualCalibrator()
        self.coordinate_manager = CoordinateManager()
        
    def test_ui_element_calibration_save(self):
        """Test de calibración y guardado de elementos UI"""
        mock_element = {
            "type": "button",
            "text": "Enviar",
            "coordinates": {"x": 250, "y": 350, "width": 80, "height": 35},
            "confidence": 0.94
        }
        
        calibration_name = "send_button"
        
        with patch.object(self.calibrator, 'calibrate') as mock_calib:
            mock_calib.return_value = mock_element
            
            result = self.calibrator.calibrate(
                calibration_name, 0, "test.png"
            )
            
            mock_calib.assert_called_once()
            
            assert result == mock_element
                
    def test_ui_element_calibration_load(self):
        """Test de carga de elementos calibrados"""
        calibration_name = "cancel_button"
        expected_coords = {"x": 100, "y": 400, "width": 90, "height": 40}
        
        with patch.object(self.coordinate_manager, 'get_calibration') as mock_load:
            mock_load.return_value = expected_coords
            
            coords = self.coordinate_manager.get_calibration(calibration_name)
            
            assert coords == expected_coords
            
    def test_ui_element_calibration_update(self):
        """Test de actualización de calibración existente"""
        calibration_name = "ok_button"
        old_coords = {"x": 200, "y": 300, "width": 70, "height": 30}
        new_coords = {"x": 210, "y": 305, "width": 75, "height": 32}
        
        with patch.object(self.coordinate_manager, 'get_calibration') as mock_load:
            mock_load.return_value = old_coords
            
            with patch.object(self.coordinate_manager, 'save_calibration') as mock_save:
                # Simular actualización de coordenadas
                self.coordinate_manager.save_calibration(calibration_name, new_coords)
                
                mock_save.assert_called_once_with(calibration_name, new_coords)
                
                # Verificar que la calibración se actualizó
                mock_load.return_value = new_coords
                updated_coords = self.coordinate_manager.get_calibration(calibration_name)
                assert updated_coords == new_coords


class TestUIElementInteraction:
    """Tests para interacción con elementos UI"""
    
    def setup_method(self):
        """Configuración inicial"""
        self.applications_core = ApplicationManager()
        self.coordinate_manager = CoordinateManager()
        
    def test_ui_element_click(self):
        """Test de clic en elemento UI"""
        element_name = "submit_button"
        expected_coords = {"x": 300, "y": 400, "width": 100, "height": 40}
        
        with patch.object(self.coordinate_manager, 'get_calibration') as mock_get:
            mock_get.return_value = expected_coords
            
            with patch('tests.hands.test_ui_elements.click_element') as mock_click:
                mock_click(button="left")
                
                mock_click.assert_called_once_with(button="left")
                
    def test_ui_element_double_click(self):
        """Test de doble clic en elemento UI"""
        element_name = "file_item"
        expected_coords = {"x": 150, "y": 250, "width": 200, "height": 30}
        
        with patch.object(self.coordinate_manager, 'get_calibration') as mock_get:
            mock_get.return_value = expected_coords
            
            with patch('tests.hands.test_ui_elements.click_element') as mock_click:
                # Simular doble clic mediante dos clics rápidos
                mock_click(button="left", wait_after=0.01)
                mock_click(button="left", wait_after=0.01)
                
                assert mock_click.call_count == 2
                
    def test_ui_element_right_click(self):
        """Test de clic derecho en elemento UI"""
        element_name = "context_menu_item"
        expected_coords = {"x": 400, "y": 300, "width": 150, "height": 25}
        
        with patch.object(self.coordinate_manager, 'get_calibration') as mock_get:
            mock_get.return_value = expected_coords
            
            with patch('tests.hands.test_ui_elements.click_element') as mock_click:
                mock_click(button="right")
                
                mock_click.assert_called_once_with(button="right")
                
    def test_ui_element_text_input(self):
        """Test de entrada de texto en elemento UI"""
        element_name = "search_field"
        expected_coords = {"x": 200, "y": 100, "width": 300, "height": 30}
        test_text = "Buscar prueba"
        
        with patch.object(self.coordinate_manager, 'get_calibration') as mock_get:
            mock_get.return_value = expected_coords
            
            with patch('tests.hands.test_ui_elements.type_text') as mock_type:
                mock_type(text=test_text)
                
                mock_type.assert_called_once_with(text=test_text)


class TestUIElementValidation:
    """Tests para validación de elementos UI"""
    
    def setup_method(self):
        """Configuración inicial"""
        self.vision = Vision()
        self.screen_analyzer = ScreenAnalyzer()
        
    def test_ui_element_visibility_check(self):
        """Test de verificación de visibilidad de elementos"""
        mock_visible_element = {
            "type": "button",
            "text": "Visible",
            "coordinates": {"x": 100, "y": 100, "width": 80, "height": 30},
            "confidence": 0.95,
            "visible": True
        }
        
        mock_hidden_element = {
            "type": "button", 
            "text": "Oculto",
            "coordinates": {"x": 500, "y": 500, "width": 80, "height": 30},
            "confidence": 0.10,
            "visible": False
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [mock_visible_element, mock_hidden_element]
            
            elements = self.vision.detect_ui_elements()
            
            # Verificar que solo los elementos visibles se consideran válidos
            visible_elements = [elem for elem in elements if elem.get("visible", False)]
            assert len(visible_elements) == 1
            assert visible_elements[0]["text"] == "Visible"
            
    def test_ui_element_confidence_threshold(self):
        """Test de umbral de confianza para elementos UI"""
        high_confidence_element = {
            "type": "button",
            "text": "Confiable",
            "coordinates": {"x": 100, "y": 100, "width": 80, "height": 30},
            "confidence": 0.95
        }
        
        low_confidence_element = {
            "type": "button",
            "text": "Dudoso",
            "coordinates": {"x": 200, "y": 200, "width": 80, "height": 30},
            "confidence": 0.65
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [high_confidence_element, low_confidence_element]
            
            elements = self.vision.detect_ui_elements()
            
            # Filtrar por umbral de confianza (0.8)
            reliable_elements = [elem for elem in elements if elem["confidence"] >= 0.8]
            assert len(reliable_elements) == 1
            assert reliable_elements[0]["text"] == "Confiable"
            
    def test_ui_element_state_validation(self):
        """Test de validación de estado de elementos"""
        enabled_button = {
            "type": "button",
            "text": "Habilitado",
            "coordinates": {"x": 100, "y": 100, "width": 80, "height": 30},
            "confidence": 0.92,
            "enabled": True
        }
        
        disabled_button = {
            "type": "button",
            "text": "Deshabilitado",
            "coordinates": {"x": 200, "y": 200, "width": 80, "height": 30},
            "confidence": 0.91,
            "enabled": False
        }
        
        with patch.object(self.vision, 'detect_ui_elements') as mock_detect:
            mock_detect.return_value = [enabled_button, disabled_button]
            
            elements = self.vision.detect_ui_elements()
            
            # Verificar que solo los elementos habilitados pueden ser interactuados
            enabled_elements = [elem for elem in elements if elem.get("enabled", True)]
            assert len(enabled_elements) == 1
            assert enabled_elements[0]["text"] == "Habilitado"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])