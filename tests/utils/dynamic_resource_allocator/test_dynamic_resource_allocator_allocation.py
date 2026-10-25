"""
Tests del modelo de asignacion (ResourceAllocation) y contexto.

2.8.4.2 — ResourceAllocation dataclass y to_dict.
2.8.4.6 — Contexto: connect_context, adjust_allocation_for_context,
  adjust_all_allocations_for_context, recalculate_on_context_change.
"""

import os
import sys
import unittest
import unittest.mock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.dynamic_resource_allocator import (
    DynamicResourceAllocator,
    ResourceType,
    ResourcePriority,
    AllocationStatus,
    ResourceRequest,
    ResourceAllocation,
)


class TestResourceAllocationDataclass(unittest.TestCase):
    """2.8.4.2 — ResourceAllocation es el modelo de asignacion"""

    def test_2_8_4_2_4_allocation_campos(self):
        """ResourceAllocation tiene los campos esperados"""
        alloc = ResourceAllocation(
            allocation_id="alloc_001",
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context={"app": "test"},
            priority=ResourcePriority.HIGH,
            status=AllocationStatus.ASSIGNED,
            actual_used=25.0,
            metadata={"extra": "data"},
        )
        self.assertEqual(alloc.allocation_id, "alloc_001")
        self.assertEqual(alloc.request_id, "req_001")
        self.assertEqual(alloc.resource_type, ResourceType.SYSTEM_CPU)
        self.assertEqual(alloc.amount, 50.0)
        self.assertEqual(alloc.context, {"app": "test"})
        self.assertEqual(alloc.priority, ResourcePriority.HIGH)
        self.assertEqual(alloc.status, AllocationStatus.ASSIGNED)
        self.assertEqual(alloc.actual_used, 25.0)
        self.assertEqual(alloc.metadata, {"extra": "data"})

    def test_2_8_4_2_4_allocation_defaults(self):
        """ResourceAllocation tiene valores por defecto"""
        alloc = ResourceAllocation(
            allocation_id="alloc_002",
            request_id="req_002",
            resource_type=ResourceType.STORAGE_CACHE,
        )
        self.assertIsNone(alloc.amount)
        self.assertEqual(alloc.context, {})
        self.assertEqual(alloc.priority, ResourcePriority.MEDIUM)
        self.assertEqual(alloc.status, AllocationStatus.PENDING)
        self.assertIsNone(alloc.released_at)
        self.assertIsNone(alloc.actual_used)
        self.assertEqual(alloc.metadata, {})

    def test_2_8_4_2_4_allocation_assigned_at_default(self):
        """ResourceAllocation asigna assigned_at por defecto a datetime.now()"""
        before = datetime.now()
        alloc = ResourceAllocation(
            allocation_id="alloc_003",
            request_id="req_003",
            resource_type=ResourceType.THREAD_POOL,
        )
        after = datetime.now()
        self.assertIsNotNone(alloc.assigned_at)
        self.assertGreaterEqual(alloc.assigned_at, before)
        self.assertLessEqual(alloc.assigned_at, after)

    def test_2_8_4_2_4_allocation_to_dict(self):
        """ResourceAllocation.to_dict serializa y convierte enums a valores"""
        alloc = ResourceAllocation(
            allocation_id="alloc_004",
            request_id="req_004",
            resource_type=ResourceType.SYSTEM_DISK,
            amount=500.0,
            context={"app": "test"},
            priority=ResourcePriority.CRITICAL,
            status=AllocationStatus.IN_USE,
            actual_used=300.0,
        )
        d = alloc.to_dict()
        self.assertEqual(d["allocation_id"], "alloc_004")
        self.assertEqual(d["request_id"], "req_004")
        self.assertEqual(d["resource_type"], "system_disk")
        self.assertEqual(d["amount"], 500.0)
        self.assertEqual(d["priority"], 4)
        self.assertEqual(d["status"], "in_use")
        self.assertEqual(d["actual_used"], 300.0)
        self.assertIsNotNone(d["assigned_at"])
        self.assertIsNone(d["released_at"])

    def test_2_8_4_2_4_allocation_to_dict_released(self):
        """to_dict incluye released_at cuando se libera"""
        alloc = ResourceAllocation(
            allocation_id="alloc_005",
            request_id="req_005",
            resource_type=ResourceType.SYSTEM_CPU,
            status=AllocationStatus.AVAILABLE,
            released_at=datetime(2025, 1, 15, 12, 0, 0),
        )
        d = alloc.to_dict()
        self.assertIsNotNone(d["released_at"])
        self.assertEqual(d["released_at"], "2025-01-15T12:00:00")


class TestGetAllocation(unittest.TestCase):
    """Obtener asignaciones"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        self.req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.alloc = self.allocator.allocate(self.req)

    def test_2_8_4_2_5_get_allocation_existente(self):
        """get_allocation retorna la asignacion por ID"""
        result = self.allocator.get_allocation(self.alloc.allocation_id)
        self.assertEqual(result, self.alloc)

    def test_2_8_4_2_5_get_allocation_no_existente(self):
        """get_allocation retorna None para un ID inexistente"""
        self.assertIsNone(self.allocator.get_allocation("nonexistent"))

    def test_2_8_4_2_5_get_all_allocations(self):
        """get_all_allocations retorna todas las asignaciones"""
        all_allocs = self.allocator.get_all_allocations()
        self.assertEqual(len(all_allocs), 1)
        self.assertIn(self.alloc, all_allocs)


class TestConnectContext(unittest.TestCase):
    """2.8.4.6 — Contexto: connect_context"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_6_1_connect_context_valido(self):
        """connect_context almacena el contexto y retorna True"""
        context = {"app": "chrome", "url": "https://example.com", "user": "alice"}
        result = self.allocator.connect_context(context)
        self.assertTrue(result)
        self.assertEqual(self.allocator.current_context, context)

    def test_2_8_4_6_1_connect_context_none(self):
        """connect_context rechaza None y retorna False"""
        result = self.allocator.connect_context(None)
        self.assertFalse(result)

    def test_2_8_4_6_1_connect_context_no_dict(self):
        """connect_context rechaza tipos no dict y retorna False"""
        result = self.allocator.connect_context("not a dict")
        self.assertFalse(result)
        result = self.allocator.connect_context([1, 2, 3])
        self.assertFalse(result)

    def test_2_8_4_6_1_connect_context_vacio(self):
        """connect_context acepta un dict vacio"""
        result = self.allocator.connect_context({})
        self.assertTrue(result)
        self.assertEqual(self.allocator.current_context, {})

    def test_2_8_4_6_1_connect_context_reemplaza(self):
        """connect_context reemplaza el contexto anterior"""
        self.allocator.connect_context({"app": "old"})
        result = self.allocator.connect_context({"app": "new"})
        self.assertTrue(result)
        self.assertEqual(self.allocator.current_context, {"app": "new"})


class TestAdjustAllocationForContext(unittest.TestCase):
    """2.8.4.6.2 — Ajustar asignacion usando datos disponibles"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        self.req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome", "tab": "gmail"},
        )
        self.alloc = self.allocator.allocate(self.req)

    def test_2_8_4_6_2_ajustar_con_datos_disponibles(self):
        """adjust_allocation_for_context actualiza claves presentes en el contexto"""
        self.allocator.connect_context({"app": "firefox", "tab": "inbox", "user": "alice"})
        result = self.allocator.adjust_allocation_for_context(self.alloc.allocation_id)
        self.assertTrue(result)
        self.assertEqual(self.alloc.context["app"], "firefox")
        self.assertEqual(self.alloc.context["tab"], "inbox")
        # "user" no estaba en el contexto de la asignacion, no se agrega
        self.assertNotIn("user", self.alloc.context)

    def test_2_8_4_6_2_ajustar_sin_cambios(self):
        """adjust_allocation_for_context retorna False si los valores coinciden"""
        self.allocator.connect_context({"app": "chrome", "tab": "gmail"})
        result = self.allocator.adjust_allocation_for_context(self.alloc.allocation_id)
        self.assertFalse(result)

    def test_2_8_4_6_2_ajustar_asignacion_no_existente(self):
        """adjust_allocation_for_context retorna False para asignacion inexistente"""
        self.allocator.connect_context({"app": "firefox"})
        result = self.allocator.adjust_allocation_for_context("nonexistent")
        self.assertFalse(result)

    def test_2_8_4_6_2_ajustar_sin_contexto_global(self):
        """adjust_allocation_for_context retorna False si no hay contexto global conectado"""
        result = self.allocator.adjust_allocation_for_context(self.alloc.allocation_id)
        self.assertFalse(result)

    def test_2_8_4_6_2_ajustar_sin_contexto_asignacion(self):
        """adjust_allocation_for_context retorna False si la asignacion tiene contexto vacio"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=10.0,
            context={},
        )
        # allocate fallara por conflicto duplicado, usar allocate directamente
        # registrar un contexto distinto
        self.allocator.connect_context({"app": "test"})
        # Crear asignacion manualmente para tener contexto vacio
        alloc = ResourceAllocation(
            allocation_id="alloc_manual",
            request_id="req_manual",
            resource_type=ResourceType.SYSTEM_CPU,
            context={},
            status=AllocationStatus.ASSIGNED,
        )
        self.allocator.allocations["alloc_manual"] = alloc
        result = self.allocator.adjust_allocation_for_context("alloc_manual")
        self.assertFalse(result)

    def test_2_8_4_6_2_ajustar_notifica_cambio(self):
        """adjust_allocation_for_context llama on_allocation_changed cuando hay ajuste"""
        called = []
        self.allocator.on_allocation_changed = lambda alloc_id, alloc: called.append(alloc_id)
        self.allocator.connect_context({"app": "firefox"})
        self.allocator.adjust_allocation_for_context(self.alloc.allocation_id)
        self.assertEqual(len(called), 1)


class TestAdjustAllAllocationsForContext(unittest.TestCase):
    """2.8.4.6.2 — Ajustar todas las asignaciones"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        self.req1 = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=10.0,
            context={"app": "chrome"},
        )
        self.alloc1 = self.allocator.allocate(self.req1)

    def test_2_8_4_6_2_adjust_all_vacio(self):
        """adjust_all_allocations_for_context retorna {} cuando no hay asignaciones"""
        allocator = DynamicResourceAllocator()
        self.assertEqual(allocator.adjust_all_allocations_for_context(), {})

    def test_2_8_4_6_2_adjust_all_con_cambios(self):
        """adjust_all_allocations_for_context ajusta asignaciones afectadas"""
        self.allocator.connect_context({"app": "firefox"})
        results = self.allocator.adjust_all_allocations_for_context()
        self.assertIn(self.alloc1.allocation_id, results)
        self.assertTrue(results[self.alloc1.allocation_id])
        self.assertEqual(self.alloc1.context["app"], "firefox")


class TestRecalculateOnContextChange(unittest.TestCase):
    """2.8.4.6.3 — Recalcular cuando el contexto cambie"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        self.req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context={"app": "chrome", "tab": "gmail"},
        )
        self.alloc = self.allocator.allocate(self.req)

    def test_2_8_4_6_3_recalculate_cambio_claves(self):
        """recalculate_on_context_change detecta claves cambiadas"""
        self.allocator.connect_context({"app": "chrome", "tab": "gmail", "user": "alice"})
        result = self.allocator.recalculate_on_context_change(
            {"app": "firefox", "tab": "inbox", "user": "bob"}
        )
        self.assertEqual(set(result["changed_keys"]), {"app", "tab", "user"})
        self.assertTrue(len(result["adjusted_allocations"]) > 0)

    def test_2_8_4_6_3_recalculate_sin_cambios(self):
        """recalculate_on_context_change con contexto idéntico: changed_keys vacia"""
        self.allocator.connect_context({"app": "chrome", "tab": "gmail"})
        result = self.allocator.recalculate_on_context_change(
            {"app": "chrome", "tab": "gmail"}
        )
        self.assertEqual(result["changed_keys"], [])
        self.assertEqual(result["adjusted_allocations"], [])
        self.assertFalse(result["resources_updated"])

    def test_2_8_4_6_3_recalculate_no_dict(self):
        """recalculate_on_context_change rechaza contexto no dict"""
        result = self.allocator.recalculate_on_context_change("not a dict")
        self.assertEqual(result["changed_keys"], [])
        self.assertEqual(result["adjusted_allocations"], [])
        self.assertFalse(result["resources_updated"])

    def test_2_8_4_6_3_recalculate_actualiza_recursos_sistema(self):
        """recalculate_on_context_change llama update_system_resources para claves de sistema"""
        with unittest.mock.patch.object(self.allocator, 'update_system_resources') as mock_update:
            self.allocator.connect_context({"cpu": 30.0})
            self.allocator.recalculate_on_context_change({"cpu": 50.0})
        mock_update.assert_called_once()


if __name__ == '__main__':
    unittest.main()
