"""
Tests de inventario y modelo para DynamicResourceAllocator 2.8.4.1.

Verifica la identificacion de recursos gestionables, la representacion de
disponibilidad, los enums y los metodos de registro/consulta.
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
    ResourceAvailability,
)


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
