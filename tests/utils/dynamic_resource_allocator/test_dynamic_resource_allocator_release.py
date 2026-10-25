"""
Tests de liberacion y uso de asignaciones.

2.8.4.4 — Liberar recurso.
  2.8.4.4.1 — Liberar recurso (basico).
  2.8.4.4.2 — Restaurar disponibilidad del recurso.
  2.8.4.4.3 — Verificar liberacion.
  2.8.4.4.4 — Manejar doble liberacion.
"""

import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.dynamic_resource_allocator import (
    DynamicResourceAllocator,
    ResourceType,
    ResourcePriority,
    AllocationStatus,
    ResourceRequest,
    ResourceAllocation,
)


class TestReleaseBasic(unittest.TestCase):
    """2.8.4.4.1 — Liberar recurso (basico)"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.alloc = self.allocator.allocate(req)

    def test_2_8_4_4_1_release_exitoso(self):
        """release retorna True y cambia el status a AVAILABLE"""
        result = self.allocator.release(self.alloc.allocation_id)
        self.assertTrue(result)
        self.assertEqual(self.alloc.status, AllocationStatus.AVAILABLE)
        self.assertIsNotNone(self.alloc.released_at)

    def test_2_8_4_4_1_release_no_existe(self):
        """release retorna False para un allocation_id inexistente"""
        result = self.allocator.release("nonexistent")
        self.assertFalse(result)

    def test_2_8_4_4_1_3_release_doble(self):
        """release retorna False al liberar una asignacion ya liberada (doble lib)"""
        self.allocator.release(self.alloc.allocation_id)
        result = self.allocator.release(self.alloc.allocation_id)
        self.assertFalse(result)


class TestReleaseUnexpectedStatus(unittest.TestCase):
    """2.8.4.4.3 — Verificar liberacion con estados inesperados"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_4_3_release_status_pendiente(self):
        """release retorna False si el status es PENDING"""
        alloc = ResourceAllocation(
            allocation_id="alloc_pend",
            request_id="req_pend",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            status=AllocationStatus.PENDING,
        )
        self.allocator.allocations["alloc_pend"] = alloc
        result = self.allocator.release("alloc_pend")
        self.assertFalse(result)

    def test_2_8_4_4_3_release_status_conflict(self):
        """release retorna False si el status es CONFLICT"""
        alloc = ResourceAllocation(
            allocation_id="alloc_conf",
            request_id="req_conf",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            status=AllocationStatus.CONFLICT,
        )
        self.allocator.allocations["alloc_conf"] = alloc
        result = self.allocator.release("alloc_conf")
        self.assertFalse(result)


class TestReleaseRestoresAvailability(unittest.TestCase):
    """2.8.4.4.2 — Restaurar disponibilidad del recurso"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_4_2_release_restaura_amount(self):
        """release restaura la cantidad disponible al liberar"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.allocator.allocate(req)
        avail_before = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertAlmostEqual(avail_before.available_amount, 70.0)

        alloc_id = list(self.allocator.allocations.keys())[0]
        result = self.allocator.release(alloc_id)
        self.assertTrue(result)

        avail_after = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertAlmostEqual(avail_after.available_amount, 100.0)

    def test_2_8_4_4_2_release_restaura_disponible(self):
        """release marca el recurso como disponible=True si se agoto"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_MEMORY,
            available=True,
            available_amount=30.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=30.0,
        )
        alloc = self.allocator.allocate(req)
        avail = self.allocator.get_availability(ResourceType.SYSTEM_MEMORY)
        self.assertFalse(avail.available)  # Se agoto → no disponible

        self.allocator.release(alloc.allocation_id)
        avail = self.allocator.get_availability(ResourceType.SYSTEM_MEMORY)
        self.assertTrue(avail.available)
        self.assertAlmostEqual(avail.available_amount, 30.0)

    def test_2_8_4_4_2_release_sin_amount_no_restaura(self):
        """release no restaura cantidad si amount es None"""
        req = self.allocator.create_request(
            request_id="req_003",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=None,
        )
        alloc = self.allocator.allocate(req)
        avail_before = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertAlmostEqual(avail_before.available_amount, 100.0)  # No se dedujo

        result = self.allocator.release(alloc.allocation_id)
        self.assertTrue(result)
        avail_after = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertAlmostEqual(avail_after.available_amount, 100.0)


class TestReleaseWithCallback(unittest.TestCase):
    """Verificacion del callback on_allocation_changed en release"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.alloc = self.allocator.allocate(req)

    def test_2_8_4_4_1_release_notifica_cambio(self):
        """release llama a on_allocation_changed con (allocation_id, allocation)"""
        called = []
        self.allocator.on_allocation_changed = lambda alloc_id, alloc: called.append(alloc_id)
        self.allocator.release(self.alloc.allocation_id)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0], self.alloc.allocation_id)


class TestUpdateUsage(unittest.TestCase):
    """Actualizar uso real de una asignacion"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.alloc = self.allocator.allocate(req)

    def test_2_8_4_4_5_update_usage_exitoso(self):
        """update_usage establece actual_used y cambia status a IN_USE"""
        result = self.allocator.update_usage(self.alloc.allocation_id, 25.0)
        self.assertTrue(result)
        self.assertEqual(self.alloc.actual_used, 25.0)
        self.assertEqual(self.alloc.status, AllocationStatus.IN_USE)

    def test_2_8_4_4_5_update_usage_no_existe(self):
        """update_usage retorna False para assignment_id inexistente"""
        result = self.allocator.update_usage("nonexistent", 10.0)
        self.assertFalse(result)

    def test_2_8_4_4_5_update_usage_multiple_updates(self):
        """update_usage permite actualizaciones sucesivas"""
        self.allocator.update_usage(self.alloc.allocation_id, 10.0)
        self.assertEqual(self.alloc.actual_used, 10.0)
        self.allocator.update_usage(self.alloc.allocation_id, 20.0)
        self.assertEqual(self.alloc.actual_used, 20.0)


class TestCleanup(unittest.TestCase):
    """Limpieza de todas las asignaciones"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_4_6_cleanup_vacio(self):
        """cleanup no lanza error con allocations vacias"""
        self.assertEqual(self.allocator.allocations, {})
        self.allocator.cleanup()
        self.assertEqual(self.allocator.allocations, {})

    def test_2_8_4_4_6_cleanup_limpia_todo(self):
        """cleanup elimina todas las asignaciones"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.allocator.allocate(req)
        self.assertEqual(len(self.allocator.allocations), 1)

        self.allocator.cleanup()
        self.assertEqual(self.allocator.allocations, {})


if __name__ == '__main__':
    unittest.main()
