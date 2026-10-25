"""
Tests del modelo de solicitud (ResourceRequest) y asignacion simple.

2.8.4.2 Modelo de asignacion — ResourceRequest.validate(), create_request.
2.8.4.3 Asignar — camino basico sin conflictos.
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
)


class TestResourceRequestDataclass(unittest.TestCase):
    """2.8.4.2 — ResourceRequest es el modelo de solicitud"""

    def test_2_8_4_2_1_request_campos(self):
        """ResourceRequest tiene los campos esperados"""
        req = ResourceRequest(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context={"app": "test"},
            priority=ResourcePriority.HIGH,
            required=True,
            metadata={"key": "val"},
        )
        self.assertEqual(req.request_id, "req_001")
        self.assertEqual(req.resource_type, ResourceType.SYSTEM_CPU)
        self.assertEqual(req.amount, 50.0)
        self.assertEqual(req.context, {"app": "test"})
        self.assertEqual(req.priority, ResourcePriority.HIGH)
        self.assertTrue(req.required)
        self.assertEqual(req.metadata, {"key": "val"})

    def test_2_8_4_2_1_request_defaults(self):
        """ResourceRequest tiene valores por defecto"""
        req = ResourceRequest(
            request_id="req_002",
            resource_type=ResourceType.STORAGE_CACHE,
            amount=100.0,
        )
        self.assertEqual(req.priority, ResourcePriority.MEDIUM)
        self.assertEqual(req.context, {})
        self.assertTrue(req.required)
        self.assertEqual(req.amount, 100.0)
        self.assertEqual(req.metadata, {})

    def test_2_8_4_2_1_request_to_dict(self):
        """ResourceRequest.to_dict serializa todos los campos"""
        req = ResourceRequest(
            request_id="req_003",
            resource_type=ResourceType.PROCESS_THREADS,
            amount=4,
            priority=ResourcePriority.LOW,
            context={"app": "test"},
            required=False,
        )
        d = req.to_dict()
        self.assertEqual(d["request_id"], "req_003")
        self.assertEqual(d["resource_type"], "process_threads")
        self.assertEqual(d["amount"], 4)
        self.assertEqual(d["priority"], 1)
        self.assertEqual(d["context"], {"app": "test"})
        self.assertFalse(d["required"])


class TestResourceRequestValidate(unittest.TestCase):
    """2.8.4.2.5 — Validar solicitud"""

    def test_2_8_4_2_2_validate_valida(self):
        """validate retorna (True, []) para una solicitud correcta"""
        req = ResourceRequest(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
        )
        valid, errors = req.validate()
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_2_8_4_2_2_validate_sin_resource_type(self):
        """validate retorna (False, [errors]) si resource_type es None"""
        req = ResourceRequest(
            request_id="req_002",
            resource_type=None,
            amount=50.0,
        )
        valid, errors = req.validate()
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)

    def test_2_8_4_2_2_validate_request_id_vacio(self):
        """validate retorna (False, [errors]) si request_id es None"""
        req = ResourceRequest(
            request_id=None,
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
        )
        valid, errors = req.validate()
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)

    def test_2_8_4_2_2_validate_amount_negativo(self):
        """validate retorna (False, [errors]) si amount es negativo"""
        req = ResourceRequest(
            request_id="req_004",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=-10.0,
        )
        valid, errors = req.validate()
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)

    def test_2_8_4_2_2_validate_amount_cero_valido(self):
        """amount=0 es valido (solo < 0 es invalido)"""
        req = ResourceRequest(
            request_id="req_005",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=0,
        )
        valid, errors = req.validate()
        self.assertTrue(valid)

    def test_2_8_4_2_2_validate_amount_none_valido(self):
        """amount=None es valido"""
        req = ResourceRequest(
            request_id="req_006",
            resource_type=ResourceType.THREAD_POOL,
            amount=None,
        )
        valid, _ = req.validate()
        self.assertTrue(valid)

    def test_2_8_4_2_2_validate_priority_invalida(self):
        """validate retorna (False, [errors]) si priority no es ResourcePriority"""
        req = ResourceRequest(
            request_id="req_007",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            priority="HIGH",
        )
        valid, errors = req.validate()
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)


class TestCreateRequest(unittest.TestCase):
    """2.8.4.2 — create_request construye un ResourceRequest"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_2_3_create_request(self):
        """create_request genera un ResourceRequest con todos los campos"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=200.0,
            context={"app": "firefox"},
            priority=ResourcePriority.HIGH,
            required=True,
        )
        self.assertIsInstance(req, ResourceRequest)
        self.assertEqual(req.resource_type, ResourceType.SYSTEM_MEMORY)
        self.assertEqual(req.amount, 200.0)
        self.assertEqual(req.priority, ResourcePriority.HIGH)
        self.assertEqual(req.context, {"app": "firefox"})
        self.assertTrue(req.required)
        valid, _ = req.validate()
        self.assertTrue(valid)

    def test_2_8_4_2_3_create_request_defaults(self):
        """create_request usa valores por defecto si no se especifican"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.THREAD_POOL,
            amount=4,
        )
        self.assertEqual(req.priority, ResourcePriority.MEDIUM)
        self.assertEqual(req.context, {})
        self.assertTrue(req.required)

    def test_2_8_4_2_3_create_request_id_unico(self):
        """create_request mantiene IDs unicos al pasar request_id explicito"""
        req1 = self.allocator.create_request(
            request_id="req_a",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=10.0,
        )
        req2 = self.allocator.create_request(
            request_id="req_b",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=20.0,
        )
        self.assertEqual(req1.request_id, "req_a")
        self.assertEqual(req2.request_id, "req_b")
        self.assertNotEqual(req1.request_id, req2.request_id)

    def test_2_8_4_2_3_create_request_invalido_lanza(self):
        """create_request levanta ValueError para una solicitud invalida"""
        with self.assertRaises(ValueError):
            self.allocator.create_request(
                request_id="req_invalido",
                resource_type=None,
                amount=50.0,
            )


class TestAllocateSimple(unittest.TestCase):
    """2.8.4.3 — Asignar (camino basico sin conflictos)"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_3_1_allocate_exitoso(self):
        """allocate asigna correctamente un recurso disponible"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            priority=ResourcePriority.MEDIUM,
            context={"app": "test_simple"},
        )
        result = self.allocator.allocate(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, AllocationStatus.ASSIGNED)
        self.assertEqual(result.resource_type, ResourceType.SYSTEM_CPU)
        self.assertEqual(result.amount, 30.0)

    def test_2_8_4_3_1_allocate_deduce_disponibilidad(self):
        """allocate reduce la cantidad disponible tras la asignacion"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        self.allocator.allocate(req)
        avail = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertAlmostEqual(avail.available_amount, 70.0)

    def test_2_8_4_3_1_allocate_registra_en_allocations(self):
        """allocate registra la asignacion en el dict allocations"""
        req = self.allocator.create_request(
            request_id="req_003",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        result = self.allocator.allocate(req)
        self.assertIn(result.allocation_id, self.allocator.allocations)

    def test_2_8_4_3_1_allocate_callback_on_changed(self):
        """allocate llama a on_allocation_changed con (allocation_id, allocation)"""
        called = []
        self.allocator.on_allocation_changed = lambda alloc_id, alloc: called.append((alloc_id, alloc))

        req = self.allocator.create_request(
            request_id="req_004",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=40.0,
        )
        result = self.allocator.allocate(req)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0][0], result.allocation_id)
        self.assertEqual(called[0][1], result)

    def test_2_8_4_3_1_allocate_sin_amount(self):
        """allocate funciona con amount=None (solo marca disponible True)"""
        req = self.allocator.create_request(
            request_id="req_005",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=None,
        )
        result = self.allocator.allocate(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, AllocationStatus.ASSIGNED)

    def test_2_8_4_3_1_allocate_recurso_no_registrado(self):
        """allocate retorna None si el recurso no esta registrado"""
        req = self.allocator.create_request(
            request_id="req_006",
            resource_type=ResourceType.SYSTEM_DISK,
            amount=10.0,
        )
        result = self.allocator.allocate(req)
        self.assertIsNone(result)

    def test_2_8_4_3_1_allocate_cantidad_insuficiente(self):
        """allocate retorna None si la cantidad solicitada excede la disponible"""
        req = self.allocator.create_request(
            request_id="req_007",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
        )
        result = self.allocator.allocate(req)
        self.assertIsNone(result)

    def test_2_8_4_3_1_allocate_recurso_no_disponible(self):
        """allocate retorna None si el recurso esta marcado como no disponible"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_MEMORY,
            available=False,
            available_amount=0.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_008",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=10.0,
        )
        result = self.allocator.allocate(req)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
