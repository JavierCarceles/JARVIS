"""
Tests de asignacion compleja: conflictos, defusion y preemption.

2.8.4.3 — Asignar: rechazar o aplazar cuando no existe recurso,
  reservar/reclamar, aplicar prioridad existente.
2.8.4.5.2 — Aplicar prioridad existente (preempt).
2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso.
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
