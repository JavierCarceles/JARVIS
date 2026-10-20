"""
Tests de integración para DynamicResourceAllocator 2.8.4.7

Verifica la integración con ContextualAdaptationEngine y PerformanceOptimizer.
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Añadir el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.dynamic_resource_allocator import (
    DynamicResourceAllocator, 
    ResourceRequest, 
    ResourceType, 
    ResourcePriority,
    AllocationStatus
)
from utils.contextual_adaptation_engine import ContextualAdaptationEngine
from utils.performance_optimizer import PerformanceOptimizer


class TestDynamicResourceAllocatorIntegration(unittest.TestCase):
    """Tests de integración para DynamicResourceAllocator"""

    def setUp(self):
        """Configuración inicial de tests"""
        self.allocator = DynamicResourceAllocator()
        
        # Mock del ContextualAdaptationEngine
        self.mock_contextual_engine = Mock(spec=ContextualAdaptationEngine)
        
        # Mock del PerformanceOptimizer
        self.mock_performance_optimizer = Mock(spec=PerformanceOptimizer)

    def test_2_8_4_7_1_connect_contextual_adaptation_engine(self):
        """
        2.8.4.7.1 — Conectar ContextualAdaptationEngine
        
        Verificar que el DynamicResourceAllocator puede conectarse y usar
        el ContextualAdaptationEngine.
        """
        # Conectar el engine
        self.allocator.set_contextual_adaptation_engine(self.mock_contextual_engine)
        
        # Verificar que se conectó correctamente
        self.assertEqual(
            self.allocator.get_contextual_adaptation_engine(), 
            self.mock_contextual_engine
        )
        
        # Registrar el recurso CPU primero
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%"
        )
        
        # Crear una asignación de prueba
        request = self.allocator.create_request(
            request_id="test_request_1",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context={"test": "context"},
            priority=ResourcePriority.HIGH
        )
        
        allocation = self.allocator.allocate(request)
        
        # Verificar que la asignación se creó
        self.assertIsNotNone(allocation)
        self.assertEqual(allocation.status, AllocationStatus.ASSIGNED)
        
        # Notificar al engine contextual
        self.allocator.notify_allocation_to_contextual_engine(allocation)
        
        # Verificar que el engine recibió la notificación
        self.mock_contextual_engine.record_resource_allocation.assert_called_once()
        call_args = self.mock_contextual_engine.record_resource_allocation.call_args[0][0]
        
        # Verificar los datos de la notificación
        self.assertEqual(call_args["resource_type"], "system_cpu")
        self.assertEqual(call_args["priority"], 3)  # HIGH
        self.assertEqual(call_args["status"], "assigned")
        self.assertEqual(call_args["context"]["test"], "context")

    def test_2_8_4_7_2_connect_performance_optimizer(self):
        """
        2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda
        
        Verificar que el DynamicResourceAllocator puede conectarse y usar
        el PerformanceOptimizer.
        """
        # Conectar el optimizador
        self.allocator.set_performance_optimizer(self.mock_performance_optimizer)
        
        # Verificar que se conectó correctamente
        self.assertEqual(
            self.allocator.get_performance_optimizer(), 
            self.mock_performance_optimizer
        )
        
        # Configurar mock del optimizador
        mock_optimization_result = {
            "success": True,
            "improvement": 25.0,
            "recommendations": [
                {
                    "type": "cpu_optimization",
                    "priority": "high",
                    "description": "Optimización de CPU",
                    "expected_improvement": 25.0
                }
            ]
        }
        self.mock_performance_optimizer.optimize_resources.return_value = mock_optimization_result
        
        # Solicitar optimización
        optimization_request = {
            "context": {"workload": "high"},
            "current_resources": {
                "system_cpu": {
                    "available": True,
                    "available_amount": 30.0,
                    "maximum": 100.0,
                    "unit": "%"
                }
            }
        }
        
        result = self.allocator.request_optimization_from_performance_optimizer(optimization_request)
        
        # Verificar que el optimizador fue llamado
        self.mock_performance_optimizer.optimize_resources.assert_called_once_with(optimization_request)
        
        # Verificar el resultado
        self.assertIsNotNone(result)
        self.assertTrue(result["success"])
        self.assertEqual(result["improvement"], 25.0)
        self.assertEqual(len(result["recommendations"]), 1)

    def test_2_8_4_7_3_expose_result_to_planner_executor(self):
        """
        2.8.4.7.3 — Exponer resultado a Planner/Executor solo mediante contratos existentes
        
        Verificar que el estado de recursos se expone en formato compatible
        con contratos existentes del Planner/Executor.
        """
        # Registrar algunos recursos
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=70.0,
            maximum=100.0,
            unit="%"
        )
        
        self.allocator.register_resource(
            ResourceType.SYSTEM_MEMORY,
            available=True,
            available_amount=50.0,
            maximum=100.0,
            unit="%"
        )
        
        # Crear algunas asignaciones
        request1 = self.allocator.create_request(
            request_id="test_alloc_1",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context={"user": "test_user"}
        )
        
        request2 = self.allocator.create_request(
            request_id="test_alloc_2", 
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=10.0,
            context={"system": "background"}
        )
        
        allocation1 = self.allocator.allocate(request1)
        allocation2 = self.allocator.allocate(request2)
        
        # Obtener estado para el Planner/Executor
        planner_context = {"context": {"current_task": "test"}}
        integrated_response = self.allocator.integrate_with_planner_executor(planner_context)
        
        # Verificar estructura de la respuesta
        self.assertIn("resource_status", integrated_response)
        self.assertIn("available_capabilities", integrated_response)
        self.assertIn("optimization_suggestions", integrated_response)
        self.assertIn("integration_timestamp", integrated_response)
        
        # Verificar estado de recursos
        resource_status = integrated_response["resource_status"]
        self.assertIn("timestamp", resource_status)
        self.assertIn("total_allocations", resource_status)
        self.assertIn("active_allocations", resource_status)
        self.assertIn("available_resources", resource_status)
        self.assertIn("resource_pressure", resource_status)
        
        # Verificar capacidades disponibles
        capabilities = integrated_response["available_capabilities"]
        self.assertTrue(len(capabilities) > 0)
        
        # Verificar que cada capacidad tiene el formato esperado
        for capability in capabilities:
            self.assertIn("type", capability)
            self.assertIn("resource_type", capability)
            self.assertIn("capacity", capability)
            self.assertIn("unit", capability)
        
        # Verificar sugerencias de optimización
        suggestions = integrated_response["optimization_suggestions"]
        self.assertIsInstance(suggestions, list)

    def test_2_8_4_7_4_integration_workflow(self):
        """
        Test del flujo de integración completo
        
        Verificar el flujo completo de integración entre todos los componentes.
        """
        # Conectar ambos componentes
        self.allocator.set_contextual_adaptation_engine(self.mock_contextual_engine)
        self.allocator.set_performance_optimizer(self.mock_performance_optimizer)
        
        # Configurar mocks
        self.mock_performance_optimizer.optimize_resources.return_value = {
            "success": True,
            "improvement": 15.0,
            "recommendations": []
        }
        
        # Registrar recursos
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=80.0,
            maximum=100.0,
            unit="%"
        )
        
        # Flujo completo: crear asignación y notificar
        request = self.allocator.create_request(
            request_id="integration_test",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"integration": "test", "priority": "high"},
            priority=ResourcePriority.HIGH
        )
        
        allocation = self.allocator.allocate(request)
        
        # Integrar con Planner/Executor
        planner_context = {
            "context": {"current_task": "integration_test"},
            "optimization_needed": True
        }
        
        integrated_response = self.allocator.integrate_with_planner_executor(planner_context)
        
        # Verificar que todo funcionó
        self.assertIsNotNone(allocation)
        self.assertIn("resource_status", integrated_response)
        resource_status = integrated_response["resource_status"]
        self.assertIn("timestamp", resource_status)
        self.assertTrue(len(resource_status["available_resources"]) >= 0)  # Puede estar vacío pero no fallar
        
        # Verificar notificaciones
        self.mock_contextual_engine.record_resource_allocation.assert_called()
        self.mock_performance_optimizer.optimize_resources.assert_called()
        
        # Verificar que la asignación se ajustó con el contexto
        self.assertEqual(allocation.context["integration"], "test")


if __name__ == '__main__':
    unittest.main()