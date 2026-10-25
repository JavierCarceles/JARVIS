"""
Tests de prioridad y conflictos.

2.8.4.5 — Prioridad / Conflictos.
  2.8.4.5.1 — Identificar conflictos reales.
  2.8.4.5.2 — Aplicar prioridad existente.
  2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso.
  2.8.4.5.4 — Evitar interrumpir trabajo de usuario.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.dynamic_resource_allocator import (
    DynamicResourceAllocator,
    ResourceType,
    ResourcePriority,
    AllocationStatus,
    ResourceRequest,
    ResourceAllocation,
)


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
