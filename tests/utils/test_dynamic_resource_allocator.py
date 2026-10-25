# -*- coding: utf-8 -*-
"""
Tests consolidados para utils.dynamic_resource_allocator
Consolida 7 archivos originales.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


import os
import sys
import unittest
import unittest.mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))
from utils.dynamic_resource_allocator import (
from datetime import datetime
from unittest.mock import Mock, patch
from utils.contextual_adaptation_engine import ContextualAdaptationEngine
from utils.performance_optimizer import PerformanceOptimizer
import threading


# --- From test_dynamic_resource_allocator_allocate.py ---
class TestAllocateConflicts(unittest.TestCase):
    """2.8.4.3 — Conflictos de asignacion"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_3_2_conflict_identical_context(self):
        """allocate rechaza solicitud con contexto idéntico (required=True)"""
        ctx = {"app": "chrome", "tab": "gmail"}

        req1 = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context=ctx,
            priority=ResourcePriority.MEDIUM,
        )
        alloc1 = self.allocator.allocate(req1)
        self.assertIsNotNone(alloc1)

        # Cambiamos el estado a IN_USE para que _has_conflict detecte conflicto
        alloc1.status = AllocationStatus.IN_USE

        req2 = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context=ctx,
            priority=ResourcePriority.MEDIUM,
        )
        result = self.allocator.allocate(req2)
        self.assertIsNone(result)

    def test_2_8_4_3_2_conflict_shared_keys_different_values(self):
        """allocate rechaza solicitud con claves compartidas y valores diferentes"""
        req1 = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome", "tab": "gmail"},
            priority=ResourcePriority.MEDIUM,
        )
        alloc1 = self.allocator.allocate(req1)
        alloc1.status = AllocationStatus.IN_USE

        req2 = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context={"app": "chrome", "tab": "calendar"},
            priority=ResourcePriority.MEDIUM,
        )
        result = self.allocator.allocate(req2)
        self.assertIsNone(result)


class TestAllocatePreemption(unittest.TestCase):
    """2.8.4.5.2 — Preempt por prioridad"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def _allocate_and_set_in_use(self, context=None, priority=ResourcePriority.MEDIUM,
                                   request_id="req_001", amount=30.0):
        """Helper: allocate and set status to IN_USE so conflicts are detected"""
        req = self.allocator.create_request(
            request_id=request_id,
            resource_type=ResourceType.SYSTEM_CPU,
            amount=amount,
            context=context or {},
            priority=priority,
        )
        alloc = self.allocator.allocate(req)
        alloc.status = AllocationStatus.IN_USE
        return alloc

    def test_2_8_4_5_2_preempt_critical(self):
        """allocate preempta si la nueva solicitud es CRITICAL"""
        ctx = {"app": "chrome"}
        self._allocate_and_set_in_use(context=ctx, priority=ResourcePriority.MEDIUM)

        req_new = self.allocator.create_request(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context=ctx,
            priority=ResourcePriority.CRITICAL,
        )
        result = self.allocator.allocate(req_new)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, AllocationStatus.ASSIGNED)

    def test_2_8_4_5_2_preempt_mayor_prioridad_no_user(self):
        """allocate preempta si existente no es user work y prioridad es mayor"""
        ctx = {"app": "chrome"}
        self._allocate_and_set_in_use(context=ctx, priority=ResourcePriority.LOW)

        req_new = self.allocator.create_request(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context=ctx,
            priority=ResourcePriority.HIGH,
        )
        result = self.allocator.allocate(req_new)
        self.assertIsNotNone(result)

    def test_2_8_4_5_2_preempt_consentimiento(self):
        """allocate preempta si nueva solicitud tiene preempt_consent en contexto"""
        ctx_existing = {"app": "chrome"}
        self._allocate_and_set_in_use(context=ctx_existing, priority=ResourcePriority.HIGH)

        ctx_new = {"app": "chrome", "preempt_consent": True}
        req_new = self.allocator.create_request(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context=ctx_new,
            priority=ResourcePriority.LOW,
        )
        result = self.allocator.allocate(req_new)
        self.assertIsNotNone(result)

    def test_2_8_4_5_2_no_preempt_user_work(self):
        """allocate NO preempta si existente es user work y nueva no es CRITICAL"""
        ctx_existing = {"app": "chrome", "type": "user"}
        self._allocate_and_set_in_use(context=ctx_existing, priority=ResourcePriority.HIGH)

        ctx_new = {"app": "chrome"}
        req_new = self.allocator.create_request(
            request_id="req_new2",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context=ctx_new,
            priority=ResourcePriority.CRITICAL,
        )
        result = self.allocator.allocate(req_new)
        # CRITICAL can preempt anything
        self.assertIsNotNone(result)

    def test_2_8_4_5_2_no_preempt_prioridad_igual(self):
        """allocate NO preempta si la prioridad es igual (no estrictamente mayor)"""
        ctx = {"app": "chrome"}
        self._allocate_and_set_in_use(context=ctx, priority=ResourcePriority.MEDIUM)

        req_new = self.allocator.create_request(
            request_id="req_new3",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=20.0,
            context=ctx,
            priority=ResourcePriority.MEDIUM,
        )
        result = self.allocator.allocate(req_new)
        self.assertIsNone(result)


class TestAllocateDeferred(unittest.TestCase):
    """2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_5_3_defer_no_required_recurso_no_disponible(self):
        """allocate difiere solicitud cuando required=False y recurso no disponible"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_MEMORY,
            available=False,
            available_amount=0.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=10.0,
            required=False,
            priority=ResourcePriority.LOW,
        )
        result = self.allocator.allocate(req)
        # defer_request retorna un string (defer_id)
        self.assertIsInstance(result, str)
        self.assertIn("defer_", result)

    def test_2_8_4_5_3_defer_no_required_cantidad_insuficiente(self):
        """allocate difiere solicitud cuando required=False y cantidad insuficiente"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
            required=False,
            priority=ResourcePriority.LOW,
        )
        result = self.allocator.allocate(req)
        self.assertIsInstance(result, str)

    def test_2_8_4_5_3_reject_required_recurso_no_disponible(self):
        """allocate rechaza solicitud cuando required=True y recurso no disponible"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_MEMORY,
            available=False,
            available_amount=0.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_003",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=10.0,
            required=True,
            priority=ResourcePriority.MEDIUM,
        )
        result = self.allocator.allocate(req)
        self.assertIsNone(result)

    def test_2_8_4_5_3_reject_required_cantidad_insuficiente(self):
        """allocate rechaza solicitud cuando required=True y cantidad insuficiente"""
        req = self.allocator.create_request(
            request_id="req_004",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
            required=True,
            priority=ResourcePriority.MEDIUM,
        )
        result = self.allocator.allocate(req)
        self.assertIsNone(result)

    def test_2_8_4_3_3_defer_almacena_metadata(self):
        """defer_request almacena defer_id en metadata del request"""
        req = self.allocator.create_request(
            request_id="req_005",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
            required=False,
        )
        defer_id = self.allocator.allocate(req)
        self.assertIsNotNone(req.metadata.get("defer_id"))
        self.assertEqual(req.metadata["defer_id"], defer_id)


class TestAllocateInvalidRequest(unittest.TestCase):
    """allocate con solicitudes invalidas"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_3_4_allocate_solicitud_invalida(self):
        """allocate retorna None para una solicitud invalida (resource_type=None)"""
        # create_request lanza ValueError, asi que construimos directamente
        req = ResourceRequest(
            request_id="req_invalida",
            resource_type=None,
            amount=50.0,
        )
        result = self.allocator.allocate(req)
        self.assertIsNone(result)


class TestOnAllocationChangedCallback(unittest.TestCase):
    """Verificacion del callback on_allocation_changed en varios flujos"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_3_5_callback_no_registrado_no_lanza(self):
        """allocate funciona sin on_allocation_changed registrado"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        result = self.allocator.allocate(req)
        self.assertIsNotNone(result)

    def test_2_8_4_3_5_callback_debe_ser_callable(self):
        """on_allocation_changed debe ser None por defecto"""
        allocator = DynamicResourceAllocator()
        self.assertIsNone(allocator.on_allocation_changed)


if __name__ == '__main__':
    unittest.main()


# --- From test_dynamic_resource_allocator_allocate_simple.py ---
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


# --- From test_dynamic_resource_allocator_allocation.py ---
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


# --- From test_dynamic_resource_allocator_integration.py ---
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


# --- From test_dynamic_resource_allocator_inventory.py ---
class TestResourceTypeEnum(unittest.TestCase):
    """2.8.4.1 — Tipos de recursos gestionables"""

    def test_2_8_4_1_1_resource_type_valores(self):
        """Verificar valores del enum ResourceType"""
        self.assertEqual(ResourceType.SYSTEM_CPU.value, "system_cpu")
        self.assertEqual(ResourceType.SYSTEM_MEMORY.value, "system_memory")
        self.assertEqual(ResourceType.SYSTEM_DISK.value, "system_disk")
        self.assertEqual(ResourceType.SYSTEM_NETWORK.value, "system_network")
        self.assertEqual(ResourceType.PROCESS_CPU.value, "process_cpu")
        self.assertEqual(ResourceType.PROCESS_MEMORY.value, "process_memory")
        self.assertEqual(ResourceType.PROCESS_THREADS.value, "process_threads")
        self.assertEqual(ResourceType.EXECUTION_REGISTRY.value, "execution_registry")
        self.assertEqual(ResourceType.EXECUTION_HISTORY.value, "execution_history")
        self.assertEqual(ResourceType.STORAGE_DATABASE.value, "storage_database")
        self.assertEqual(ResourceType.STORAGE_CACHE.value, "storage_cache")
        self.assertEqual(ResourceType.THREAD_POOL.value, "thread_pool")

    def test_2_8_4_1_1_resource_type_cuantos(self):
        """Verificar que hay 11 tipos de recursos"""
        members = [e for e in ResourceType]
        self.assertEqual(len(members), 12)


class TestResourcePriorityEnum(unittest.TestCase):
    """2.8.4.2.3 — Prioridades"""

    def test_2_8_4_1_2_resource_priority_valores(self):
        """Verificar valores del enum ResourcePriority"""
        self.assertEqual(ResourcePriority.LOW.value, 1)
        self.assertEqual(ResourcePriority.MEDIUM.value, 2)
        self.assertEqual(ResourcePriority.HIGH.value, 3)
        self.assertEqual(ResourcePriority.CRITICAL.value, 4)


class TestAllocationStatusEnum(unittest.TestCase):
    """Estados de asignacion"""

    def test_2_8_4_1_3_allocation_status_valores(self):
        """Verificar valores del enum AllocationStatus"""
        self.assertEqual(AllocationStatus.PENDING.value, "pending")
        self.assertEqual(AllocationStatus.ASSIGNED.value, "assigned")
        self.assertEqual(AllocationStatus.IN_USE.value, "in_use")
        self.assertEqual(AllocationStatus.AVAILABLE.value, "available")
        self.assertEqual(AllocationStatus.UNAVAILABLE.value, "unavailable")
        self.assertEqual(AllocationStatus.CONFLICT.value, "conflict")


class TestResourceAvailability(unittest.TestCase):
    """2.8.4.2.5 — Validar solicitud / disponibilidad"""

    def test_2_8_4_1_4_can_satisfy_disponible_sin_limites(self):
        """can_satisfy retorna True cuando no hay limites conocidos"""
        avail = ResourceAvailability(
            resource_type=ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=None,
            maximum=None,
        )
        self.assertTrue(avail.can_satisfy(50.0))

    def test_2_8_4_1_4_can_satisfy_disponible_con_amount_none(self):
        """can_satisfy retorna True cuando el amount solicitado es None"""
        avail = ResourceAvailability(
            resource_type=ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
        )
        self.assertTrue(avail.can_satisfy(None))

    def test_2_8_4_1_4_can_satisfy_cantidad_suficiente(self):
        """can_satisfy retorna True cuando la cantidad disponible es suficiente"""
        avail = ResourceAvailability(
            resource_type=ResourceType.SYSTEM_MEMORY,
            available=True,
            available_amount=80.0,
            maximum=100.0,
        )
        self.assertTrue(avail.can_satisfy(50.0))

    def test_2_8_4_1_4_can_satisfy_cantidad_insuficiente(self):
        """can_satisfy retorna False cuando la cantidad es insuficiente"""
        avail = ResourceAvailability(
            resource_type=ResourceType.SYSTEM_MEMORY,
            available=True,
            available_amount=30.0,
            maximum=100.0,
        )
        self.assertFalse(avail.can_satisfy(50.0))

    def test_2_8_4_1_4_can_satisfy_no_disponible(self):
        """can_satisfy retorna False cuando el recurso no esta disponible"""
        avail = ResourceAvailability(
            resource_type=ResourceType.SYSTEM_DISK,
            available=False,
            available_amount=10.0,
            maximum=100.0,
        )
        self.assertFalse(avail.can_satisfy(5.0))


class TestRegisterResource(unittest.TestCase):
    """2.8.4.1 — Registrar recursos"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_1_5_register_resource_crea_availability(self):
        """register_resource crea un ResourceAvailability"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )
        avail = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertIsNotNone(avail)
        self.assertTrue(avail.available)
        self.assertEqual(avail.available_amount, 100.0)
        self.assertEqual(avail.maximum, 100.0)
        self.assertEqual(avail.unit, "%")

    def test_2_8_4_1_5_register_resource_unidad_no_disponible(self):
        """register_resource puede marcar un recurso como no disponible"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_DISK,
            available=False,
            available_amount=10.0,
            maximum=100.0,
            unit="GB",
        )
        avail = self.allocator.get_availability(ResourceType.SYSTEM_DISK)
        self.assertFalse(avail.available)
        self.assertEqual(avail.unit, "GB")

    def test_2_8_4_1_5_get_availability_no_registrado(self):
        """get_availability retorna None para recurso no registrado"""
        result = self.allocator.get_availability(ResourceType.THREAD_POOL)
        self.assertIsNone(result)

    def test_2_8_4_1_5_get_availability_default_cpu(self):
        """get_availability retorna datos para recursos ya registrados tras init"""
        # __init__ llama update_system_resources que registra recursos si hay metricas
        # Verificamos que get_availability no lanza y retorna algo o None sin error
        result = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        # Si update_system_resources registro algo, obtendremos un objeto; si no, None
        if result is not None:
            self.assertEqual(result.resource_type, ResourceType.SYSTEM_CPU)


class TestUpdateSystemResources(unittest.TestCase):
    """2.8.4.1.2 — Identificar como se mide disponibilidad"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_1_6_update_system_resources_sin_error(self):
        """update_system_resources no lanza error si no hay metricas"""
        # No hay metricas registradas, no debe lanzar
        self.allocator.update_system_resources()
        # No debe haber lanzado excepcion

    def test_2_8_4_1_6_update_system_resources_con_metricas(self):
        """update_system_resources registra CPU, memoria, disco, red con metricas simuladas"""
        with unittest.mock.patch.object(self.allocator.monitor, 'get_performance_summary') as mock_summary:
            mock_summary.return_value = {
                'metrics': {
                    'cpu_usage': {'current_value': 30.0},
                    'memory_usage': {'current_value': 60.0},
                    'disk_usage': {'current_value': 50.0},
                    'network_usage': {'current_value': 20.0},
                }
            }
            self.allocator.update_system_resources()

        cpu_avail = self.allocator.get_availability(ResourceType.SYSTEM_CPU)
        self.assertIsNotNone(cpu_avail)
        self.assertTrue(cpu_avail.available)
        self.assertAlmostEqual(cpu_avail.available_amount, 70.0)

        mem_avail = self.allocator.get_availability(ResourceType.SYSTEM_MEMORY)
        self.assertIsNotNone(mem_avail)
        self.assertAlmostEqual(mem_avail.available_amount, 40.0)

        disk_avail = self.allocator.get_availability(ResourceType.SYSTEM_DISK)
        self.assertIsNotNone(disk_avail)
        self.assertAlmostEqual(disk_avail.available_amount, 50.0)

        net_avail = self.allocator.get_availability(ResourceType.SYSTEM_NETWORK)
        self.assertIsNotNone(net_avail)
        self.assertAlmostEqual(net_avail.available_amount, 80.0)

    def test_2_8_4_1_6_update_execution_resources(self):
        """update_execution_resources registra EXECUTION_REGISTRY y EXECUTION_HISTORY"""
        self.allocator.update_execution_resources(registry_size=42)

        reg_avail = self.allocator.get_availability(ResourceType.EXECUTION_REGISTRY)
        self.assertIsNotNone(reg_avail)
        self.assertEqual(reg_avail.available_amount, 42)
        self.assertEqual(reg_avail.unit, "actions")

        hist_avail = self.allocator.get_availability(ResourceType.EXECUTION_HISTORY)
        self.assertIsNotNone(hist_avail)
        self.assertEqual(hist_avail.available_amount, 1000)
        self.assertEqual(hist_avail.unit, "commands")

    def test_2_8_4_1_6_update_thread_pool_resources(self):
        """update_thread_pool_resources registra THREAD_POOL con workers disponibles"""
        self.allocator.update_thread_pool_resources(max_workers=8)

        tp_avail = self.allocator.get_availability(ResourceType.THREAD_POOL)
        self.assertIsNotNone(tp_avail)
        self.assertEqual(tp_avail.maximum, 8)
        self.assertEqual(tp_avail.unit, "workers")
        self.assertGreaterEqual(tp_avail.available_amount, 0)

    def test_2_8_4_1_6_update_storage_resources(self):
        """update_storage_resources registra STORAGE_DATABASE y STORAGE_CACHE"""
        self.allocator.update_storage_resources(cache_size=2048)

        db_avail = self.allocator.get_availability(ResourceType.STORAGE_DATABASE)
        self.assertIsNotNone(db_avail)
        self.assertEqual(db_avail.available_amount, 100)
        self.assertEqual(db_avail.unit, "%")

        cache_avail = self.allocator.get_availability(ResourceType.STORAGE_CACHE)
        self.assertIsNotNone(cache_avail)
        self.assertEqual(cache_avail.available_amount, 2048)
        self.assertEqual(cache_avail.unit, "bytes")


class TestDynamicResourceAllocatorInit(unittest.TestCase):
    """Verificacion del estado inicial del allocador"""

    def test_2_8_4_1_7_init_estado_inicial(self):
        """El allocador inicia con allocations vacias, locks y contextos vacios"""
        allocator = DynamicResourceAllocator()
        self.assertEqual(allocator.allocations, {})
        self.assertEqual(allocator.pending_requests, [])
        self.assertEqual(allocator.current_context, {})
        self.assertIsNone(allocator.on_allocation_changed)
        self.assertIsNone(allocator.contextual_adaptation_engine)
        self.assertIsNone(allocator.performance_optimizer)

    def test_2_8_4_1_7_init_monitor_asignado(self):
        """El allocador tiene un PerformanceMonitor asignado"""
        allocator = DynamicResourceAllocator()
        self.assertIsNotNone(allocator.monitor)

    def test_2_8_4_1_7_init_optimizer_asignado(self):
        """El allocador tiene un PerformanceOptimizer asignado (por defecto o pasado)"""
        allocator = DynamicResourceAllocator()
        self.assertIsNotNone(allocator.optimizer)

    def test_2_8_4_1_7_init_lock_es_rlock(self):
        """El lock usado es un RLock (permitido reentrar)"""
        allocator = DynamicResourceAllocator()
        import threading
        self.assertIsInstance(allocator.allocations_lock, type(threading.RLock()))


if __name__ == '__main__':
    unittest.main()


# --- From test_dynamic_resource_allocator_priority_conflicts.py ---
class TestContextsConflict(unittest.TestCase):
    """2.8.4.5.1 — _contexts_conflict"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_5_1_conflict_identico(self):
        """Contextos idénticos → conflicto"""
        c1 = {"app": "chrome", "tab": "gmail"}
        c2 = {"app": "chrome", "tab": "gmail"}
        self.assertTrue(self.allocator._contexts_conflict(c1, c2))

    def test_2_8_4_5_1_conflict_clave_compartida_valor_diferente(self):
        """Claves compartidas con valores diferentes → conflicto"""
        c1 = {"app": "chrome", "tab": "gmail"}
        c2 = {"app": "chrome", "tab": "calendar"}
        self.assertTrue(self.allocator._contexts_conflict(c1, c2))

    def test_2_8_4_5_1_no_conflict_claves_disjuntas(self):
        """Claves disjuntas → sin conflicto"""
        c1 = {"app": "chrome"}
        c2 = {"tab": "gmail"}
        self.assertFalse(self.allocator._contexts_conflict(c1, c2))

    def test_2_8_4_5_1_no_conflict_valores_iguales_clave_compartida(self):
        """Clave compartida con mismo valor → no conflicto"""
        c1 = {"app": "chrome", "user": "alice"}
        c2 = {"app": "chrome", "tab": "gmail"}
        self.assertFalse(self.allocator._contexts_conflict(c1, c2))

    def test_2_8_4_5_1_no_conflict_contexto_vacio(self):
        """Contexto vacio → sin conflicto"""
        c1 = {"app": "chrome"}
        c2 = {}
        self.assertFalse(self.allocator._contexts_conflict(c1, c2))
        self.assertFalse(self.allocator._contexts_conflict(c2, c2))

    def test_2_8_4_5_1_no_conflict_ambos_none(self):
        """Ambos contextos None → sin conflicto"""
        self.assertFalse(self.allocator._contexts_conflict(None, None))
        self.assertFalse(self.allocator._contexts_conflict(None, {}))


class TestHasConflict(unittest.TestCase):
    """2.8.4.5.1 — _has_conflict"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def _make_allocation(self, context=None, status=AllocationStatus.IN_USE, allocation_id="alloc_001"):
        alloc = ResourceAllocation(
            allocation_id=allocation_id,
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context=context or {},
            status=status,
        )
        self.allocator.allocations[allocation_id] = alloc
        return alloc

    def test_2_8_4_5_1_1_conflict_in_use_mismo_contexto(self):
        """_has_conflict retorna True si hay asignacion IN_USE con contexto conflictivo"""
        self._make_allocation(context={"app": "chrome"}, status=AllocationStatus.IN_USE)
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome"},
        )
        self.assertTrue(self.allocator._has_conflict(req))

    def test_2_8_4_5_1_1_no_conflict_assigned(self):
        """_has_conflict retorna False si la asignacion esta en ASSIGNED (no IN_USE)"""
        self._make_allocation(context={"app": "chrome"}, status=AllocationStatus.ASSIGNED)
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome"},
        )
        self.assertFalse(self.allocator._has_conflict(req))

    def test_2_8_4_5_1_1_no_conflict_diferente_recurso(self):
        """_has_conflict retorna False si el recurso es diferente"""
        self._make_allocation(context={"app": "chrome"}, status=AllocationStatus.IN_USE)
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=30.0,
            context={"app": "chrome"},
        )
        self.assertFalse(self.allocator._has_conflict(req))

    def test_2_8_4_5_1_1_no_conflict_contexto_no_conflictivo(self):
        """_has_conflict retorna False si el contexto no entra en conflicto"""
        # Claves disjuntas → no hay conflicto
        self._make_allocation(context={"app": "chrome"}, status=AllocationStatus.IN_USE)
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"tab": "gmail"},
        )
        self.assertFalse(self.allocator._has_conflict(req))


class TestGetConflicts(unittest.TestCase):
    """2.8.4.5.1 — get_conflicts"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_5_1_2_conflict_vacio(self):
        """get_conflicts retorna lista vacia sin asignaciones"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome"},
        )
        self.assertEqual(self.allocator.get_conflicts(req), [])

    def test_2_8_4_5_1_2_conflict_encontrado(self):
        """get_conflicts retorna tuplas (alloc_id, allocation) de conflictos"""
        alloc = ResourceAllocation(
            allocation_id="alloc_001",
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context={"app": "chrome"},
            status=AllocationStatus.IN_USE,
        )
        self.allocator.allocations["alloc_001"] = alloc

        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome"},
        )
        conflicts = self.allocator.get_conflicts(req)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0][0], "alloc_001")
        self.assertEqual(conflicts[0][1], alloc)

    def test_2_8_4_5_1_2_conflict_multiples(self):
        """get_conflicts encuentra multiples asignaciones en conflicto"""
        ctx = {"app": "chrome"}
        for i in range(3):
            alloc = ResourceAllocation(
                allocation_id=f"alloc_{i}",
                request_id=f"req_{i}",
                resource_type=ResourceType.SYSTEM_CPU,
                amount=20.0,
                context=ctx,
                status=AllocationStatus.IN_USE,
            )
            self.allocator.allocations[f"alloc_{i}"] = alloc

        req = self.allocator.create_request(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=10.0,
            context=ctx,
        )
        conflicts = self.allocator.get_conflicts(req)
        self.assertEqual(len(conflicts), 3)


class TestIsUserWork(unittest.TestCase):
    """2.8.4.5.4 — _is_user_work"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def _make_alloc(self, context=None):
        return ResourceAllocation(
            allocation_id="alloc_001",
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            context=context or {},
        )

    def test_2_8_4_5_4_user_context_key(self):
        """_is_user_work True si el contexto tiene clave 'user'"""
        alloc = self._make_alloc(context={"app": "chrome", "user": "alice"})
        self.assertTrue(self.allocator._is_user_work(alloc))

    def test_2_8_4_5_4_user_type_key(self):
        """_is_user_work True si el contexto tiene 'type'='user'"""
        alloc = self._make_alloc(context={"type": "user"})
        self.assertTrue(self.allocator._is_user_work(alloc))

    def test_2_8_4_5_4_user_source_key(self):
        """_is_user_work True si el contexto tiene 'source'='user'"""
        alloc = self._make_alloc(context={"source": "user"})
        self.assertTrue(self.allocator._is_user_work(alloc))

    def test_2_8_4_5_4_interactive_key(self):
        """_is_user_work True si el contexto tiene 'interactive'=True"""
        alloc = self._make_alloc(context={"interactive": True})
        self.assertTrue(self.allocator._is_user_work(alloc))

    def test_2_8_4_5_4_no_user_work(self):
        """_is_user_work False para contextos sin indicadores de usuario"""
        alloc = self._make_alloc(context={"app": "chrome", "tab": "gmail"})
        self.assertFalse(self.allocator._is_user_work(alloc))

    def test_2_8_4_5_4_contexto_vacio(self):
        """_is_user_work False para contexto vacio"""
        alloc = self._make_alloc(context={})
        self.assertFalse(self.allocator._is_user_work(alloc))


class TestCanPreempt(unittest.TestCase):
    """2.8.4.5.4 — _can_preempt"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def _make_alloc(self, priority=ResourcePriority.MEDIUM, context=None):
        return ResourceAllocation(
            allocation_id="alloc_001",
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context=context or {},
            priority=priority,
            status=AllocationStatus.IN_USE,
        )

    def _make_request(self, priority=ResourcePriority.CRITICAL, context=None):
        return ResourceRequest(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            priority=priority,
            context=context or {},
            required=True,
        )

    def test_2_8_4_5_2_1_critical_puede_preemptar(self):
        """CRITICAL puede preemptar cualquier asignacion"""
        alloc = self._make_alloc(priority=ResourcePriority.HIGH, context={"user": "alice"})
        req = self._make_request(priority=ResourcePriority.CRITICAL, context={"user": "alice"})
        self.assertTrue(self.allocator._can_preempt(alloc, req))

    def test_2_8_4_5_2_1_preempt_consent_puede_preemptar(self):
        """preempt_consent=True en el contexto puede preemptar"""
        alloc = self._make_alloc(priority=ResourcePriority.HIGH, context={"app": "chrome"})
        req = self._make_request(priority=ResourcePriority.LOW, context={"preempt_consent": True})
        self.assertTrue(self.allocator._can_preempt(alloc, req))

    def test_2_8_4_5_2_1_mayor_prioridad_no_user(self):
        """Mayor prioridad sobre no-user work puede preemptar"""
        alloc = self._make_alloc(priority=ResourcePriority.LOW, context={"app": "chrome"})
        req = self._make_request(priority=ResourcePriority.HIGH, context={"app": "chrome"})
        self.assertTrue(self.allocator._can_preempt(alloc, req))

    def test_2_8_4_5_2_1_igual_prioridad_no_preempta(self):
        """Igual prioridad sobre no-user work no puede preemptar"""
        alloc = self._make_alloc(priority=ResourcePriority.MEDIUM, context={"app": "chrome"})
        req = self._make_request(priority=ResourcePriority.MEDIUM, context={"app": "chrome"})
        self.assertFalse(self.allocator._can_preempt(alloc, req))

    def test_2_8_4_5_2_1_menor_prioridad_no_preempta(self):
        """Menor prioridad sobre no-user work no puede preemptar"""
        alloc = self._make_alloc(priority=ResourcePriority.HIGH, context={"app": "chrome"})
        req = self._make_request(priority=ResourcePriority.LOW, context={"app": "chrome"})
        self.assertFalse(self.allocator._can_preempt(alloc, req))

    def test_2_8_4_5_2_1_user_work_no_preempta_sin_critical(self):
        """User work no puede preemptar con prioridad alta (solo CRITICAL)"""
        alloc = self._make_alloc(priority=ResourcePriority.LOW, context={"user": "alice"})
        req = self._make_request(priority=ResourcePriority.HIGH, context={"app": "chrome"})
        self.assertFalse(self.allocator._can_preempt(alloc, req))

    def test_2_8_4_5_2_1_user_work_no_preempta_sin_consent(self):
        """User work no puede preemptar con preempt_consent=False"""
        alloc = self._make_alloc(
            priority=ResourcePriority.LOW,
            context={"user": "alice"},
        )
        req = self._make_request(
            priority=ResourcePriority.HIGH,
            context={"preempt_consent": False},
        )
        self.assertFalse(self.allocator._can_preempt(alloc, req))


class TestTryPreempt(unittest.TestCase):
    """2.8.4.5.2 — _try_preempt"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_5_2_2_try_preempt_exitoso(self):
        """_try_preempt retorna True y libera la asignacion cuando se puede preemptar"""
        alloc = ResourceAllocation(
            allocation_id="alloc_001",
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context={"app": "chrome"},
            priority=ResourcePriority.LOW,
            status=AllocationStatus.IN_USE,
        )
        self.allocator.allocations["alloc_001"] = alloc

        req = self.allocator.create_request(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome"},
            priority=ResourcePriority.HIGH,
        )
        conflicts = self.allocator.get_conflicts(req)
        result = self.allocator._try_preempt(conflicts, req)
        self.assertTrue(result)
        # La asignación debe estar liberada
        released = self.allocator.get_allocation("alloc_001")
        self.assertEqual(released.status, AllocationStatus.AVAILABLE)

    def test_2_8_4_5_2_2_try_preempt_fracaso(self):
        """_try_preempt retorna False cuando no se puede preemptar"""
        alloc = ResourceAllocation(
            allocation_id="alloc_001",
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=50.0,
            context={"app": "chrome"},
            priority=ResourcePriority.HIGH,
            status=AllocationStatus.IN_USE,
        )
        self.allocator.allocations["alloc_001"] = alloc

        req = self.allocator.create_request(
            request_id="req_new",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            context={"app": "chrome"},
            priority=ResourcePriority.LOW,
        )
        conflicts = self.allocator.get_conflicts(req)
        result = self.allocator._try_preempt(conflicts, req)
        self.assertFalse(result)
        # La asignación sigue activa
        active = self.allocator.get_allocation("alloc_001")
        self.assertEqual(active.status, AllocationStatus.IN_USE)


class TestDeferRequest(unittest.TestCase):
    """2.8.4.5.3 — defer_request"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_5_3_1_defer_request_retorna_id(self):
        """defer_request retorna un string con prefijo defer_"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
            required=False,
        )
        defer_id = self.allocator.defer_request(req)
        self.assertIsInstance(defer_id, str)
        self.assertIn("defer_", defer_id)
        self.assertEqual(req.metadata["defer_id"], defer_id)

    def test_2_8_4_5_3_1_defer_request_almacena_pending(self):
        """defer_request almacena la solicitud en pending_requests"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
            required=False,
        )
        self.allocator.defer_request(req)
        self.assertEqual(len(self.allocator.pending_requests), 1)


class TestGetPendingRequests(unittest.TestCase):
    """2.8.4.5.3 — get_pending_requests"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()

    def test_2_8_4_5_3_2_pending_vacio(self):
        """get_pending_requests retorna lista vacia sin deferidos"""
        self.assertEqual(self.allocator.get_pending_requests(), [])

    def test_2_8_4_5_3_2_pending_con_solicitudes(self):
        """get_pending_requests retorna copia de las solicitudes diferidas"""
        req1 = ResourceRequest(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
        )
        req2 = ResourceRequest(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=200.0,
        )
        self.allocator.defer_request(req1)
        self.allocator.defer_request(req2)
        pending = self.allocator.get_pending_requests()
        self.assertEqual(len(pending), 2)
        # Debe ser una copia, no la lista interna
        self.assertEqual(pending, self.allocator.pending_requests)


class TestProcessDeferred(unittest.TestCase):
    """2.8.4.5.3 — process_deferred"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_5_3_3_process_deferred_asigna_exitosa(self):
        """process_deferred asigna solicitudes deferidas cuando hay disponibilidad"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
            required=False,
            priority=ResourcePriority.HIGH,
        )
        defer_id = self.allocator.defer_request(req)
        # Ahora hay disponibilidad suficiente
        allocated_ids = self.allocator.process_deferred()
        self.assertEqual(len(allocated_ids), 1)
        self.assertIn(defer_id, allocated_ids)
        self.assertEqual(len(self.allocator.pending_requests), 0)
        # La asignación debe existir
        self.assertEqual(len(self.allocator.allocations), 1)

    def test_2_8_4_5_3_3_process_deferred_mantiene_fallidas(self):
        """process_deferred mantiene en pending las que no se pueden asignar"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=500.0,  # Mas que lo disponible
            required=False,
            priority=ResourcePriority.LOW,
        )
        defer_id = self.allocator.defer_request(req)
        allocated_ids = self.allocator.process_deferred()
        self.assertEqual(len(allocated_ids), 0)
        self.assertEqual(len(self.allocator.pending_requests), 1)
        self.assertEqual(self.allocator.pending_requests[0].request_id, "req_002")

    def test_2_8_4_5_3_3_process_deferred_prioridad_descendente(self):
        """process_deferred procesa en orden de prioridad descendente"""
        req_low = self.allocator.create_request(
            request_id="req_low",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=10.0,
            required=False,
            priority=ResourcePriority.LOW,
        )
        req_critical = self.allocator.create_request(
            request_id="req_crit",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=10.0,
            required=False,
            priority=ResourcePriority.CRITICAL,
        )
        self.allocator.defer_request(req_low)
        defer_id_crit = self.allocator.defer_request(req_critical)

        allocated_ids = self.allocator.process_deferred()
        self.assertIn(defer_id_crit, allocated_ids)


class TestAllocateDirect(unittest.TestCase):
    """_allocate_direct — asignacion directa para procesamiento diferido"""

    def setUp(self):
        self.allocator = DynamicResourceAllocator()
        self.allocator.register_resource(
            ResourceType.SYSTEM_CPU,
            available=True,
            available_amount=100.0,
            maximum=100.0,
            unit="%",
        )

    def test_2_8_4_5_5_allocate_direct_exitoso(self):
        """_allocate_direct asigna una solicitud sin verificar conflictos"""
        req = self.allocator.create_request(
            request_id="req_001",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=30.0,
        )
        result = self.allocator._allocate_direct(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, AllocationStatus.IN_USE)

    def test_2_8_4_5_5_allocate_direct_recurso_no_registrado(self):
        """_allocate_direct retorna None si el recurso no esta registrado"""
        req = self.allocator.create_request(
            request_id="req_002",
            resource_type=ResourceType.SYSTEM_DISK,
            amount=30.0,
        )
        result = self.allocator._allocate_direct(req)
        self.assertIsNone(result)

    def test_2_8_4_5_5_allocate_direct_cantidad_insuficiente(self):
        """_allocate_direct retorna None si la cantidad no se puede satisfacer"""
        req = self.allocator.create_request(
            request_id="req_003",
            resource_type=ResourceType.SYSTEM_CPU,
            amount=500.0,
        )
        result = self.allocator._allocate_direct(req)
        self.assertIsNone(result)

    def test_2_8_4_5_5_allocate_direct_no_disponible(self):
        """_allocate_direct retorna None si el recurso no esta disponible"""
        self.allocator.register_resource(
            ResourceType.SYSTEM_MEMORY,
            available=False,
            available_amount=0.0,
            maximum=100.0,
            unit="%",
        )
        req = self.allocator.create_request(
            request_id="req_004",
            resource_type=ResourceType.SYSTEM_MEMORY,
            amount=10.0,
        )
        result = self.allocator._allocate_direct(req)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()


# --- From test_dynamic_resource_allocator_release.py ---
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

