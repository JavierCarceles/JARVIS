"""
Dynamic Resource Allocator v2.8.4.2
Sistema de asignación de recursos según contexto usando únicamente recursos y mecanismos que el proyecto puede observar realmente.
"""

import logging
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Set
from datetime import datetime

from .performance_monitor import PerformanceMonitor, PerformanceMetric, MetricType
from .performance_optimizer import PerformanceOptimizer, OptimizationStrategy
from .contextual_adaptation_engine import ContextualAdaptationEngine


class ResourceType(Enum):
    """Tipos de recursos gestionables"""
    SYSTEM_CPU = "system_cpu"
    SYSTEM_MEMORY = "system_memory"
    SYSTEM_DISK = "system_disk"
    SYSTEM_NETWORK = "system_network"
    PROCESS_CPU = "process_cpu"
    PROCESS_MEMORY = "process_memory"
    PROCESS_THREADS = "process_threads"
    EXECUTION_REGISTRY = "execution_registry"
    EXECUTION_HISTORY = "execution_history"
    STORAGE_DATABASE = "storage_database"
    STORAGE_CACHE = "storage_cache"
    THREAD_POOL = "thread_pool"


class ResourcePriority(Enum):
    """Prioridades de recurso"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class AllocationStatus(Enum):
    """Estados de asignación"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_USE = "in_use"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


@dataclass
class ResourceRequest:
    """
    Representa una solicitud de recurso.

    2.8.4.2.1 — Representar una solicitud de recurso.
    2.8.4.2.4 — Asociar contexto.
    2.8.4.2.5 — Validar solicitud.
    """
    request_id: str
    resource_type: ResourceType
    amount: Optional[float] = None  # Cantidad solicitada (ej. %, bytes, workers)
    context: Dict[str, Any] = field(default_factory=dict)  # 2.8.4.2.2 — Asociar contexto
    priority: ResourcePriority = ResourcePriority.MEDIUM  # 2.8.4.2.3 — Asociar prioridad solo si ya existe
    required: bool = True  # Si es requerido o solo deseado
    metadata: Dict[str, Any] = field(default_factory=dict)  # Metadatos adicionales

    def validate(self) -> tuple[bool, List[str]]:
        """
        Validar la solicitud.

        Returns:
            (valid, errors): Tupla con validación y lista de errores
        """
        errors = []

        # Validar request_id
        if not self.request_id or not isinstance(self.request_id, str):
            errors.append("request_id debe ser string no vacío")

        # Validar resource_type
        if not isinstance(self.resource_type, ResourceType):
            errors.append("resource_type debe ser de tipo ResourceType")

        # Validar prioridad
        if not isinstance(self.priority, ResourcePriority):
            errors.append("priority debe ser de tipo ResourcePriority")

        # Validar required
        if not isinstance(self.required, bool):
            errors.append("required debe ser booleano")

        # Validar contexto
        if self.context is None:
            self.context = {}
        elif not isinstance(self.context, dict):
            errors.append("context debe ser dict")

        # Validar metadata
        if self.metadata is None:
            self.metadata = {}
        elif not isinstance(self.metadata, dict):
            errors.append("metadata debe ser dict")

        # Validar cantidad para recursos numéricos
        if self.resource_type in (
            ResourceType.SYSTEM_CPU,
            ResourceType.SYSTEM_MEMORY,
            ResourceType.SYSTEM_DISK,
            ResourceType.PROCESS_CPU,
            ResourceType.PROCESS_MEMORY,
            ResourceType.STORAGE_CACHE
        ):
            if self.amount is not None:
                if not isinstance(self.amount, (int, float)):
                    errors.append(f"amount para {self.resource_type.value} debe ser numérico")
                elif self.amount < 0:
                    errors.append(f"amount para {self.resource_type.value} no debe ser negativo")

        return len(errors) == 0, errors

    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['resource_type'] = self.resource_type.value
        data['priority'] = self.priority.value
        return data


@dataclass
class ResourceAllocation:
    """
    Representa una asignación de recurso.

    2.8.4.2.4 — Asociar cantidad/uso cuando sea observable.
    """
    allocation_id: str
    request_id: str
    resource_type: ResourceType
    amount: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)
    priority: ResourcePriority = ResourcePriority.MEDIUM
    status: AllocationStatus = AllocationStatus.PENDING
    assigned_at: Optional[datetime] = field(default_factory=datetime.now)
    released_at: Optional[datetime] = None
    actual_used: Optional[float] = None  # Cantidad realmente usada
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['resource_type'] = self.resource_type.value
        data['priority'] = self.priority.value
        data['status'] = self.status.value
        data['assigned_at'] = self.assigned_at.isoformat() if self.assigned_at else None
        data['released_at'] = self.released_at.isoformat() if self.released_at else None
        return data


@dataclass
class ResourceAvailability:
    """
    Representa la disponibilidad de un recurso.

    2.8.4.2.5 — Validar solicitud.
    """
    resource_type: ResourceType
    available: bool
    available_amount: Optional[float] = None
    used_amount: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = "%"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_satisfy(self, request_amount: Optional[float]) -> bool:
        """
        Verificar si el recurso puede satisfacer la solicitud.

        Args:
            request_amount: Cantidad solicitada

        Returns:
            True si puede satisfacer
        """
        if not self.available:
            return False

        if self.available_amount is None or self.maximum is None:
            return True  # Sin límites conocidos

        if request_amount is None:
            return True  # Sin cantidad específica

        return self.available_amount >= request_amount


class DynamicResourceAllocator:
    """
    Sistema de asignación de recursos según contexto.

    2.8.4.2 — MODELO DE ALLOCACIÓN
    """

    def __init__(self, monitor: Optional[PerformanceMonitor] = None,
                 optimizer: Optional[PerformanceOptimizer] = None):
        """
        Inicializar el asignador de recursos.

        Args:
            monitor: Instancia de PerformanceMonitor (opcional)
            optimizer: Instancia de PerformanceOptimizer (opcional)
        """
        self.logger = logging.getLogger(__name__)
        self.monitor = monitor or PerformanceMonitor()
        self.optimizer = optimizer or PerformanceOptimizer()

        # Almacenamiento de asignaciones
        self.allocations: Dict[str, ResourceAllocation] = {}
        # RLock: _has_conflict() se llama desde allocate() ya dentro del lock
        self.allocations_lock = threading.RLock()

        # Almacenamiento de recursos disponibles
        self.available_resources: Dict[ResourceType, ResourceAvailability] = {}

        # Solicitudes diferidas (2.8.4.5.3 — Rechazar o aplazar)
        self.pending_requests: List[ResourceRequest] = []

        # Callbacks para notificación de cambios
        self.on_allocation_changed: Optional[Callable[[str, ResourceAllocation], None]] = None

        # Contexto actual (2.8.4.6.1 — Conectar con contexto actual)
        self.current_context: Dict[str, Any] = {}

        # 2.8.4.7.1 — Conectar ContextualAdaptationEngine
        self.contextual_adaptation_engine: Optional[ContextualAdaptationEngine] = None

        # 2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda
        self.performance_optimizer: Optional[PerformanceOptimizer] = optimizer

        # Inicializar recursos del sistema
        self.update_system_resources()

        self.logger.info("DynamicResourceAllocator inicializado")

    def register_resource(self, resource_type: ResourceType,
                          available: bool = True,
                          available_amount: Optional[float] = None,
                          maximum: Optional[float] = None,
                          unit: str = "%") -> None:
        """
        Registrar un recurso disponible.

        Args:
            resource_type: Tipo de recurso
            available: Si está disponible
            available_amount: Cantidad disponible
            maximum: Cantidad máxima
            unit: Unidad de medida
        """
        with self.allocations_lock:
            self.available_resources[resource_type] = ResourceAvailability(
                resource_type=resource_type,
                available=available,
                available_amount=available_amount,
                maximum=maximum,
                unit=unit
            )
            self.logger.debug(f"Recurso registrado: {resource_type.value}, disponible={available}")

    def create_request(self, request_id: str,
                      resource_type: ResourceType,
                      amount: Optional[float] = None,
                      context: Optional[Dict[str, Any]] = None,
                      priority: ResourcePriority = ResourcePriority.MEDIUM,
                      required: bool = True) -> ResourceRequest:
        """
        Crear una solicitud de recurso.

        Args:
            request_id: ID de la solicitud
            resource_type: Tipo de recurso
            amount: Cantidad solicitada
            context: Contexto de la solicitud
            priority: Prioridad
            required: Si es requerido

        Returns:
            ResourceRequest: Solicitud creada
        """
        request = ResourceRequest(
            request_id=request_id,
            resource_type=resource_type,
            amount=amount,
            context=context or {},
            priority=priority,
            required=required
        )

        # Validar solicitud
        is_valid, errors = request.validate()
        if not is_valid:
            self.logger.warning(f"Solicitud inválida {request_id}: {errors}")
            raise ValueError(f"Solicitud inválida: {'; '.join(errors)}")

        self.logger.debug(f"Solicitud creada: {request_id} para {resource_type.value}")
        return request

    def allocate(self, request: ResourceRequest) -> Optional[ResourceAllocation]:
        """
        Asignar un recurso.

        2.8.4.3 — Comprobar disponibilidad.
        2.8.4.3.2 — Reservar/reclamar según mecanismo real.
        2.8.4.5.2 — Aplicar prioridad existente.
        2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso.

        Args:
            request: Solicitud de recurso

        Returns:
            ResourceAllocation: Asignación creada o None si no se pudo
        """
        is_valid, errors = request.validate()
        if not is_valid:
            self.logger.error(f"Solicitud inválida: {errors}")
            return None

        allocation_id = f"alloc_{request.request_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with self.allocations_lock:
            # Verificar conflictos con asignaciones existentes
            conflicts = self.get_conflicts(request)
            if conflicts:
                # 2.8.4.5.2 — Intentar preemptión por prioridad
                preempted = self._try_preempt(conflicts, request)
                if not preempted:
                    # 2.8.4.5.3 — Rechazar si no se puede preemptar y no es requerido
                    if not request.required:
                        return self.defer_request(request)
                    self.logger.warning(f"Conflicto de asignación para {request.resource_type.value}")
                    return None

            # Verificar disponibilidad del recurso (después de manejar conflictos)
            if request.resource_type not in self.available_resources:
                self.logger.warning(f"Recurso no registrado: {request.resource_type.value}")
                return None

            availability = self.available_resources[request.resource_type]

            # Verificar si el recurso está disponible
            if not availability.available:
                # Si no es requerido, diferir la solicitud (2.8.4.5.3)
                if not request.required:
                    return self.defer_request(request)
                self.logger.warning(f"Recurso no disponible: {request.resource_type.value}")
                return None

            # Verificar si se puede satisfacer la cantidad solicitada
            if request.amount is not None and not availability.can_satisfy(request.amount):
                # Si no es requerido, diferir la solicitud (2.8.4.5.3)
                if not request.required:
                    return self.defer_request(request)
                self.logger.warning(f"Cantidad insuficiente para {request.resource_type.value}: "
                                  f"solicitado={request.amount}, disponible={availability.available_amount}")
                return None
            
            
            
            # Verificar si el recurso ya está asignado al mismo contexto (duplicado)
            with self.allocations_lock:
                for existing_allocation in self.allocations.values():
                    if (existing_allocation.resource_type == request.resource_type and 
                        existing_allocation.status in [AllocationStatus.ASSIGNED, AllocationStatus.IN_USE] and
                        self._contexts_conflict(existing_allocation.context, request.context)):
                        # Si es el mismo contexto y no se ha liberado, rechazar duplicado
                        if existing_allocation.request_id == request.request_id:
                            self.logger.warning(f"Recurso ya asignado al mismo contexto: {request.request_id}")
                            return None

            allocation = ResourceAllocation(
                allocation_id=allocation_id,
                request_id=request.request_id,
                resource_type=request.resource_type,
                amount=request.amount,
                context=request.context,
                priority=request.priority,
                status=AllocationStatus.ASSIGNED,
                assigned_at=datetime.now()
            )

            self.allocations[allocation_id] = allocation

            # Actualizar disponibilidad del recurso
            if request.amount is not None and availability.available_amount is not None:
                availability.available_amount -= request.amount
                # Marcar como no disponible si se agotó
                if availability.available_amount <= 0:
                    availability.available = False

            self.logger.info(f"Asignación creada: {allocation_id} para {request.resource_type.value}")

            # Notificar cambio
            if self.on_allocation_changed:
                self.on_allocation_changed(allocation_id, allocation)

            return allocation

    def _has_conflict(self, request: ResourceRequest) -> bool:
        """
        Verificar si hay conflictos con asignaciones existentes.

        2.8.4.5 — Prioridad / Conflictos.

        Args:
            request: Solicitud a verificar

        Returns:
            True si hay conflicto
        """
        with self.allocations_lock:
            for allocation in self.allocations.values():
                # Conflictos si mismo recurso está en uso
                if allocation.resource_type == request.resource_type and allocation.status == AllocationStatus.IN_USE:
                    # Conflictos si mismo recurso y mismo contexto crítico
                    if self._contexts_conflict(allocation.context, request.context):
                        self.logger.debug(f"Conflicto detectado: {allocation.allocation_id} vs {request.request_id}")
                        return True
        return False

    def _contexts_conflict(self, context1: Dict[str, Any], context2: Dict[str, Any]) -> bool:
        """
        Verificar si dos contextos tienen conflictos.

        Dos contextos entran en conflicto si:
        - Son idénticos (misma clave y mismo valor): compiten por el mismo
          recurso con el mismo propósito.
        - Comparten claves con valores diferentes: propósitos incompatibles
          sobre el mismo recurso.

        Args:
            context1: Primer contexto
            context2: Segundo contexto

        Returns:
            True si hay conflicto
        """
        if not context1 or not context2:
            return False

        # Contextos idénticos → conflicto (mismo recurso, mismo propósito)
        if context1 == context2:
            return True

        # Claves compartidas con valores diferentes → conflicto
        shared_keys = set(context1.keys()) & set(context2.keys())
        for key in shared_keys:
            if context1[key] != context2[key]:
                return True

        return False

    # ======================================================================
    # 2.8.4.5.1 — Identificar conflictos reales
    # ======================================================================

    def get_conflicts(self, request: ResourceRequest) -> List[tuple]:
        """
        Identificar conflictos reales con asignaciones existentes.

        2.8.4.5.1 — Identificar conflictos reales.

        Args:
            request: Solicitud a verificar

        Returns:
            Lista de tuplas (allocation_id, ResourceAllocation) en conflicto.
            Lista vacía si no hay conflictos.
        """
        conflicts = []
        with self.allocations_lock:
            for allocation in self.allocations.values():
                if allocation.resource_type == request.resource_type and allocation.status in [AllocationStatus.IN_USE, AllocationStatus.ASSIGNED]:
                    if self._contexts_conflict(allocation.context, request.context):
                        conflicts.append((allocation.allocation_id, allocation))
        return conflicts

    # ======================================================================
    # 2.8.4.5.4 — Evitar interrumpir trabajo de usuario sin contrato explícito
    # ======================================================================

    def _is_user_work(self, allocation: ResourceAllocation) -> bool:
        """
        Determinar si una asignación es trabajo de usuario.

        Una asignación se considera trabajo de usuario si su contexto
        contiene indicadores explícitos de origen humano.

        Args:
            allocation: Asignación a evaluar

        Returns:
            True si es trabajo de usuario
        """
        context = allocation.context or {}
        return (
            context.get("user") is not None
            or context.get("type") == "user"
            or context.get("source") == "user"
            or context.get("interactive") is True
        )

    def _can_preempt(self, existing_allocation: ResourceAllocation,
                     new_request: ResourceRequest) -> bool:
        """
        Verificar si una asignación existente puede ser preemptada.

        2.8.4.5.4 — Evitar interrumpir trabajo de usuario sin contrato explícito.

        Se puede preemptar si:
        - La nueva solicitud es CRITICAL (contrato explícito de prioridad máxima).
        - La nueva solicitud tiene consentimiento explícito de preemption
          en su contexto ("preempt_consent": True).
        - La asignación existente NO es trabajo de usuario Y la nueva
          solicitud tiene prioridad estrictamente mayor.

        No se puede preemptar si:
        - La asignación existente es trabajo de usuario y la nueva solicitud
          no tiene CRITICAL ni consentimiento explícito.

        Args:
            existing_allocation: Asignación existente a evaluar para preemption
            new_request: Nueva solicitud que desea preemptar

        Returns:
            True si se puede preemptar
        """
        # Si la nueva solicitud es CRITICAL, permite preemptar cualquier cosa
        if new_request.priority == ResourcePriority.CRITICAL:
            return True

        # Si hay consentimiento explícito de preemption en el contexto
        if new_request.context.get("preempt_consent") is True:
            return True

        # Si el trabajo existente NO es de usuario y la prioridad es mayor
        if not self._is_user_work(existing_allocation):
            return new_request.priority.value > existing_allocation.priority.value

        # Trabajo de usuario: solo CRITICAL o consentimiento explícito
        return False

    def _try_preempt(self, conflicts: list, new_request: ResourceRequest) -> bool:
        """
        Intentar preemptar asignaciones en conflicto según prioridad.

        2.8.4.5.2 — Aplicar prioridad existente.

        Args:
            conflicts: Lista de (allocation_id, allocation) en conflicto
            new_request: Nueva solicitud con prioridad

        Returns:
            True si se preemptió al menos una asignación
        """
        for alloc_id, allocation in conflicts:
            if self._can_preempt(allocation, new_request):
                # Preemptar: liberar la asignación existente
                self.release(alloc_id)
                self.logger.info(
                    f"Preemptada asignación {alloc_id} por prioridad "
                    f"{new_request.priority.value} (existente: {allocation.priority.value})"
                )
                return True
        return False

    # ======================================================================
    # 2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso
    # ======================================================================

    def defer_request(self, request: ResourceRequest) -> str:
        """
        Aplazar una solicitud cuando no hay recurso disponible.

        2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso.

        Args:
            request: Solicitud a diferir

        Returns:
            ID de la solicitud diferida
        """
        request_id = f"defer_{request.request_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        request.metadata["defer_id"] = request_id
        self.pending_requests.append(request)
        self.logger.info(f"Solicitud diferida: {request_id} para {request.resource_type.value}")
        return request_id

    def get_pending_requests(self) -> List[ResourceRequest]:
        """
        Obtener solicitudes diferidas.

        Returns:
            Lista de solicitudes diferidas
        """
        with self.allocations_lock:
            return list(self.pending_requests)

    def process_deferred(self) -> List[str]:
        """
        Intentar asignar solicitudes diferidas.

        Procesa las solicitudes diferidas en orden de prioridad (mayor primero).
        Las solicitudes que se asignan exitosamente se eliminan de la cola.
        Las que siguen sin asignarse permanecen diferidas.

        Returns:
            Lista de IDs de solicitudes que se asignaron exitosamente
        """
        allocated_ids = []

        with self.allocations_lock:
            # Ordenar por prioridad descendente (CRITICAL primero)
            sorted_pending = sorted(
                self.pending_requests,
                key=lambda r: r.priority.value,
                reverse=True
            )
            remaining = []

            for request in sorted_pending:
                # Intentar asignar directamente (sin validar conflictos de forma segura)
                result = self._allocate_direct(request)
                if result is not None:
                    allocated_ids.append(request.metadata.get("defer_id", request.request_id))
                else:
                    remaining.append(request)

            self.pending_requests = remaining

        return allocated_ids

    def _allocate_direct(self, request: ResourceRequest) -> Optional[ResourceAllocation]:
        """
        Intentar asignación directa sin verificación de conflictos (para deferred).

        Verifica disponibilidad básica pero permite asignación sobre
        conflictos existentes para no bloquear procesamiento diferido.
        """
        is_valid, errors = request.validate()
        if not is_valid:
            return None

        if request.resource_type not in self.available_resources:
            return None

        availability = self.available_resources[request.resource_type]

        if not availability.available:
            return None

        if request.amount is not None and not availability.can_satisfy(request.amount):
            return None

        allocation_id = f"alloc_{request.request_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        allocation = ResourceAllocation(
            allocation_id=allocation_id,
            request_id=request.request_id,
            resource_type=request.resource_type,
            amount=request.amount,
            context=request.context,
            priority=request.priority,
            status=AllocationStatus.IN_USE,
            assigned_at=datetime.now()
        )

        self.allocations[allocation_id] = allocation
        self.logger.info(f"Asignación diferida creada: {allocation_id}")

        if self.on_allocation_changed:
            self.on_allocation_changed(allocation_id, allocation)

        return allocation

    def release(self, allocation_id: str) -> bool:
        """
        Liberar una asignación.

        2.8.4.4 — Liberar recurso.
        2.8.4.4.3 — Verificar liberación.
        2.8.4.4.4 — Manejar doble liberación.

        Args:
            allocation_id: ID de la asignación

        Returns:
            True si se liberó correctamente
        """
        with self.allocations_lock:
            if allocation_id not in self.allocations:
                self.logger.warning(f"Asignación no encontrada: {allocation_id}")
                return False

            allocation = self.allocations[allocation_id]

            # Manejar doble liberación
            if allocation.status == AllocationStatus.AVAILABLE:
                self.logger.warning(f"Asignación ya liberada: {allocation_id}")
                return False

            if allocation.status not in [AllocationStatus.IN_USE, AllocationStatus.ASSIGNED]:
                self.logger.warning(f"Asignación en estado inesperado: {allocation.status}")
                return False

            allocation.status = AllocationStatus.AVAILABLE
            allocation.released_at = datetime.now()

            # Restaurar disponibilidad del recurso
            availability = self.available_resources.get(allocation.resource_type)
            if availability and allocation.amount is not None and availability.available_amount is not None:
                availability.available_amount += allocation.amount
                availability.available = True

            self.logger.info(f"Asignación liberada: {allocation_id}")

            # Notificar cambio
            if self.on_allocation_changed:
                self.on_allocation_changed(allocation_id, allocation)

            return True

    def get_availability(self, resource_type: ResourceType) -> Optional[ResourceAvailability]:
        """
        Obtener disponibilidad de un recurso.

        Args:
            resource_type: Tipo de recurso

        Returns:
            ResourceAvailability o None si no está registrado
        """
        return self.available_resources.get(resource_type)

    def get_allocation(self, allocation_id: str) -> Optional[ResourceAllocation]:
        """
        Obtener una asignación.

        Args:
            allocation_id: ID de la asignación

        Returns:
            ResourceAllocation o None si no existe
        """
        return self.allocations.get(allocation_id)

    def get_all_allocations(self) -> List[ResourceAllocation]:
        """
        Obtener todas las asignaciones.

        Returns:
            Lista de asignaciones
        """
        with self.allocations_lock:
            return list(self.allocations.values())

    def update_usage(self, allocation_id: str, used_amount: float) -> bool:
        """
        Actualizar el uso real de una asignación.

        Args:
            allocation_id: ID de la asignación
            used_amount: Cantidad usada

        Returns:
            True si se actualizó correctamente
        """
        with self.allocations_lock:
            if allocation_id not in self.allocations:
                return False

            allocation = self.allocations[allocation_id]
            allocation.actual_used = used_amount
            allocation.status = AllocationStatus.IN_USE

            return True

    def cleanup(self) -> None:
        """Limpieza de recursos."""
        with self.allocations_lock:
            self.allocations.clear()
            self.available_resources.clear()
            self.logger.info("DynamicResourceAllocator limpiado")

    def update_system_resources(self) -> None:
        """
        Actualizar recursos del sistema desde PerformanceMonitor.

        2.8.4.1.2 — Identificar cómo se mide disponibilidad.
        """
        # Obtener métricas del monitor
        metrics = self.monitor.get_performance_summary()
        metrics_data = metrics.get('metrics', {})

        # Actualizar CPU
        if isinstance(metrics_data, dict) and 'cpu_usage' in metrics_data:
            cpu_value = metrics_data['cpu_usage'].get('current_value', 0)
            self.register_resource(
                ResourceType.SYSTEM_CPU,
                available=True,
                available_amount=100.0 - cpu_value,  # Espacio libre
                maximum=100.0,
                unit="%"
            )

        # Actualizar memoria
        if isinstance(metrics_data, dict) and 'memory_usage' in metrics_data:
            memory_value = metrics_data['memory_usage'].get('current_value', 0)
            self.register_resource(
                ResourceType.SYSTEM_MEMORY,
                available=True,
                available_amount=100.0 - memory_value,  # Espacio libre
                maximum=100.0,
                unit="%"
            )

        # Actualizar disco
        if isinstance(metrics_data, dict) and 'disk_usage' in metrics_data:
            disk_value = metrics_data['disk_usage'].get('current_value', 0)
            self.register_resource(
                ResourceType.SYSTEM_DISK,
                available=True,
                available_amount=100.0 - disk_value,  # Espacio libre
                maximum=100.0,
                unit="%"
            )

        # Actualizar red
        if isinstance(metrics_data, dict) and 'network_usage' in metrics_data:
            net_value = metrics_data['network_usage'].get('current_value', 0)
            self.register_resource(
                ResourceType.SYSTEM_NETWORK,
                available=True,
                available_amount=100.0 - net_value,  # Espacio libre
                maximum=100.0,
                unit="%"
            )

    def update_execution_resources(self, registry_size: int = 0) -> None:
        """
        Actualizar recursos de ejecución.

        Args:
            registry_size: Tamaño del registro de acciones
        """
        # Registro de acciones
        self.register_resource(
            ResourceType.EXECUTION_REGISTRY,
            available=True,
            available_amount=registry_size,
            unit="actions"
        )

        # Historial de comandos (simulado)
        self.register_resource(
            ResourceType.EXECUTION_HISTORY,
            available=True,
            available_amount=1000,  # Capacidad máxima
            unit="commands"
        )

    def update_thread_pool_resources(self, max_workers: int = 4) -> None:
        """
        Actualizar recursos de pool de hilos.

        Args:
            max_workers: Máximo de workers
        """
        # Obtener hilos activos
        active_threads = threading.active_count()

        # Cantidad disponible = máximo - activos
        available_amount = max(0, max_workers - active_threads)

        self.register_resource(
            ResourceType.THREAD_POOL,
            available=available_amount >= 0,
            available_amount=available_amount,
            maximum=max_workers,
            unit="workers"
        )

    def update_storage_resources(self, cache_size: int = 0) -> None:
        """
        Actualizar recursos de almacenamiento.

        Args:
            cache_size: Tamaño del caché en bytes
        """
        # Base de datos
        self.register_resource(
            ResourceType.STORAGE_DATABASE,
            available=True,
            available_amount=100,  # Porcentaje de espacio disponible
            unit="%"
        )

        # Caché
        self.register_resource(
            ResourceType.STORAGE_CACHE,
            available=True,
            available_amount=cache_size,
            unit="bytes"
        )

    # ======================================================================
    # 2.8.4.6 — CONTEXTO
    # ======================================================================

    # 2.8.4.6.1 — Conectar con contexto actual

    def connect_context(self, context: Dict[str, Any]) -> bool:
        """
        Conectar con el contexto actual.

        Almacena el contexto recibido para su uso en ajustes de asignación.
        Solo acepta datos dict; rechaza None o tipos no soportados.

        Args:
            context: Diccionario de contexto actual

        Returns:
            True si el contexto se conectó correctamente
        """
        if not isinstance(context, dict):
            self.logger.warning(f"Contexto inválido: {type(context).__name__}")
            return False

        self.current_context = context
        self.logger.info(f"Contexto conectado: {len(context)} claves")
        return True

    # 2.8.4.6.2 — Ajustar asignación solo usando datos disponibles

    def adjust_allocation_for_context(self, allocation_id: str) -> bool:
        """
        Ajustar una asignación usando solo datos disponibles en el contexto.

        Para cada clave de contexto de la asignación, verifica si existe
        en self.current_context. Solo ajusta si el dato está presente.
        Ignora claves ausentes sin error.

        Args:
            allocation_id: ID de la asignación a ajustar

        Returns:
            True si se ajustó al menos un dato disponible
        """
        allocation = self.get_allocation(allocation_id)
        if allocation is None:
            self.logger.warning(f"Asignación no encontrada: {allocation_id}")
            return False

        alloc_context = allocation.context or {}
        if not alloc_context or not self.current_context:
            return False

        adjusted = False
        for key, value in alloc_context.items():
            if key in self.current_context:
                # Solo ajustar con datos que realmente existen en el contexto
                current_value = self.current_context[key]
                if current_value != value:
                    allocation.context[key] = current_value
                    adjusted = True
                    self.logger.debug(
                        f"Ajustado contexto {key}: {value} -> {current_value}"
                    )

        if adjusted and self.on_allocation_changed:
            self.on_allocation_changed(allocation_id, allocation)

        return adjusted

    def adjust_all_allocations_for_context(self) -> Dict[str, bool]:
        """
        Ajustar todas las asignaciones usando datos disponibles del contexto.

        Returns:
            Dict[allocation_id, bool]: Qué asignaciones fueron ajustadas
        """
        results = {}
        for allocation_id in list(self.allocations.keys()):
            results[allocation_id] = self.adjust_allocation_for_context(allocation_id)
        return results

    # 2.8.4.6.3 — Recalcular cuando el contexto cambie

    def recalculate_on_context_change(self, new_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recalcular asignaciones cuando el contexto cambia.

        Detecta qué claves cambiaron entre el contexto actual y el nuevo,
        y recalcula solo las asignaciones afectadas. Actualiza recursos
        del sistema si hay cambios en contextos de sistema.

        Args:
            new_context: Nuevo contexto a comparar

        Returns:
            Dict con: changed_keys, adjusted_allocations, resources_updated
        """
        if not isinstance(new_context, dict):
            self.logger.warning("recalculate_on_context_change: contexto no es dict")
            return {
                "changed_keys": [],
                "adjusted_allocations": [],
                "resources_updated": False,
            }

        # Detectar cambios entre contexto actual y nuevo
        changed_keys = []
        all_keys = set(list(self.current_context.keys()) + list(new_context.keys()))
        for key in all_keys:
            old_val = self.current_context.get(key)
            new_val = new_context.get(key)
            if old_val != new_val:
                changed_keys.append(key)

        # Actualizar contexto
        self.current_context = new_context

        # Determinar si recursos del sistema deben actualizarse
        resources_updated = False
        system_context_keys = {"system_resources", "cpu", "memory", "disk",
                               "network", "performance"}
        if any(key in system_context_keys for key in changed_keys):
            self.update_system_resources()
            resources_updated = True

        # Ajustar asignaciones afectadas (solo las que comparten claves cambiadas)
        adjusted_allocations = []
        for allocation_id, allocation in self.allocations.items():
            alloc_context = allocation.context or {}
            if any(key in alloc_context for key in changed_keys):
                if self.adjust_allocation_for_context(allocation_id):
                    adjusted_allocations.append(allocation_id)

        self.logger.info(
            f"Recálculo: {len(changed_keys)} claves cambiadas, "
            f"{len(adjusted_allocations)} asignaciones ajustadas, "
            f"recursos_actualizados={resources_updated}"
        )

        return {
            "changed_keys": changed_keys,
            "adjusted_allocations": adjusted_allocations,
            "resources_updated": resources_updated,
        }

    # ======================================================================
    # 2.8.4.7 — INTEGRACIÓN
    # ======================================================================

    def set_contextual_adaptation_engine(self, engine: ContextualAdaptationEngine) -> None:
        """
        Conectar con el ContextualAdaptationEngine.

        2.8.4.7.1 — Conectar ContextualAdaptationEngine.

        Args:
            engine: Instancia de ContextualAdaptationEngine
        """
        if not isinstance(engine, ContextualAdaptationEngine):
            self.logger.error("ContextualAdaptationEngine inválido")
            return

        self.contextual_adaptation_engine = engine
        self.logger.info("ContextualAdaptationEngine conectado")

    def get_contextual_adaptation_engine(self) -> Optional[ContextualAdaptationEngine]:
        """
        Obtener la instancia conectada de ContextualAdaptationEngine.

        Returns:
            Instancia de ContextualAdaptationEngine o None si no está conectada
        """
        return self.contextual_adaptation_engine

    def set_performance_optimizer(self, optimizer: PerformanceOptimizer) -> None:
        """
        Conectar con el PerformanceOptimizer.

        2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda.

        Args:
            optimizer: Instancia de PerformanceOptimizer
        """
        if not isinstance(optimizer, PerformanceOptimizer):
            self.logger.error("PerformanceOptimizer inválido")
            return

        self.performance_optimizer = optimizer
        self.logger.info("PerformanceOptimizer conectado")

    def get_performance_optimizer(self) -> Optional[PerformanceOptimizer]:
        """
        Obtener la instancia conectada de PerformanceOptimizer.

        Returns:
            Instancia de PerformanceOptimizer o None si no está conectada
        """
        return self.performance_optimizer

    def notify_allocation_to_contextual_engine(self, allocation: ResourceAllocation) -> None:
        """
        Notificar una asignación al ContextualAdaptationEngine.

        2.8.4.7.1 — Conectar ContextualAdaptationEngine.

        Args:
            allocation: Asignación notificada
        """
        if not self.contextual_adaptation_engine:
            self.logger.debug("ContextualAdaptationEngine no conectado, omitiendo notificación")
            return

        try:
            # Convertir asignación a formato compatible con el engine
            allocation_data = {
                "allocation_id": allocation.allocation_id,
                "resource_type": allocation.resource_type.value,
                "amount": allocation.amount,
                "context": allocation.context,
                "priority": allocation.priority.value,
                "status": allocation.status.value,
                "timestamp": allocation.assigned_at.isoformat() if allocation.assigned_at else None
            }

            # Notificar al engine para que adapte estrategias si es necesario
            self.contextual_adaptation_engine.record_resource_allocation(allocation_data)
            self.logger.debug(f"Asignación notificada al ContextualAdaptationEngine: {allocation.allocation_id}")

        except Exception as e:
            self.logger.error(f"Error notificando asignación al ContextualAdaptationEngine: {e}")

    def request_optimization_from_performance_optimizer(self, optimization_request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Solicitar optimización al PerformanceOptimizer.

        2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda.

        Args:
            optimization_request: Solicitud de optimización con contexto y recursos

        Returns:
            Respuesta del optimizador o None si no está disponible
        """
        if not self.performance_optimizer:
            self.logger.debug("PerformanceOptimizer no conectado, omitiendo optimización")
            return None

        try:
            # Incluir información de recursos actuales en la solicitud
            optimization_request["current_resources"] = {
                resource_type.value: {
                    "available": availability.available,
                    "available_amount": availability.available_amount,
                    "maximum": availability.maximum,
                    "unit": availability.unit
                }
                for resource_type, availability in self.available_resources.items()
            }

            # Solicitar optimización
            optimization_result = self.performance_optimizer.optimize_resources(optimization_request)
            
            if optimization_result and optimization_result.get("success"):
                self.logger.info(f"Optimización exitosa: {optimization_result.get('improvement', 0):.2f}% mejora")
            else:
                self.logger.warning(f"Optimización fallida o sin mejoras: {optimization_result}")

            return optimization_result

        except Exception as e:
            self.logger.error(f"Error solicitando optimización al PerformanceOptimizer: {e}")
            return None

    def get_resource_allocation_status_for_planner(self) -> Dict[str, Any]:
        """
        Obtener estado de asignación de recursos para el Planner/Executor.

        2.8.4.7.3 — Exponer resultado a Planner/Executor solo mediante contratos existentes.

        Returns:
            Diccionario con estado de recursos compatible con contratos existentes
        """
        status = {
            "timestamp": datetime.now().isoformat(),
            "total_allocations": len(self.allocations),
            "active_allocations": len([
                alloc for alloc in self.allocations.values() 
                if alloc.status in [AllocationStatus.ASSIGNED, AllocationStatus.IN_USE]
            ]),
            "available_resources": {},
            "resource_pressure": {},
            "optimization_recommendations": []
        }

        # Información de recursos disponibles (formato compatible con contratos existentes)
        for resource_type, availability in self.available_resources.items():
            status["available_resources"][resource_type.value] = {
                "available": availability.available,
                "available_amount": availability.available_amount,
                "maximum": availability.maximum,
                "unit": availability.unit,
                "utilization_rate": (
                    (availability.maximum - availability.available_amount) / availability.maximum * 100
                    if availability.maximum and availability.available_amount is not None
                    else 0.0
                )
            }

            # Calcular presión de recursos
            if availability.maximum and availability.available_amount is not None:
                pressure = (availability.maximum - availability.available_amount) / availability.maximum
                status["resource_pressure"][resource_type.value] = pressure

        # Recomendaciones de optimización si está disponible el optimizador
        if self.performance_optimizer and self.available_resources:
            try:
                optimization_context = {
                    "current_pressure": status["resource_pressure"],
                    "active_allocations": status["active_allocations"],
                    "timestamp": status["timestamp"]
                }
                
                optimization_result = self.request_optimization_from_performance_optimizer(optimization_context)
                if optimization_result and optimization_result.get("recommendations"):
                    status["optimization_recommendations"] = optimization_result["recommendations"]
            except Exception as e:
                self.logger.warning(f"No se pudieron generar recomendaciones de optimización: {e}")

        return status

    def integrate_with_planner_executor(self, planner_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Integrar completamente con Planner/Executor mediante contratos existentes.

        2.8.4.7.3 — Exponer resultado a Planner/Executor solo mediante contratos existentes.

        Args:
            planner_context: Contexto recibido del Planner

        Returns:
            Respuesta integrada compatible con contratos existentes
        """
        # Actualizar contexto actual
        if "context" in planner_context:
            self.connect_context(planner_context["context"])

        # Obtener estado actual de recursos
        resource_status = self.get_resource_allocation_status_for_planner()

        # Construir respuesta compatible con contratos existentes
        integrated_response = {
            "resource_status": resource_status,
            "available_capabilities": self._get_available_capabilities_for_planner(),
            "optimization_suggestions": self._get_optimization_suggestions_for_planner(),
            "integration_timestamp": datetime.now().isoformat()
        }

        # Si hay asignaciones activas, notificar al engine contextual
        active_allocations = [
            alloc for alloc in self.allocations.values() 
            if alloc.status in [AllocationStatus.ASSIGNED, AllocationStatus.IN_USE]
        ]
        
        for allocation in active_allocations:
            self.notify_allocation_to_contextual_engine(allocation)

        self.logger.info(f"Integración completada con Planner/Executor: {len(active_allocations)} asignaciones activas")

        return integrated_response

    def _get_available_capabilities_for_planner(self) -> List[Dict[str, Any]]:
        """
        Obtener capacidades disponibles para el Planner en formato compatible.

        Returns:
            Lista de capacidades disponibles
        """
        capabilities = []
        
        for resource_type, availability in self.available_resources.items():
            if availability.available:
                capability = {
                    "type": "resource_allocation",
                    "resource_type": resource_type.value,
                    "capacity": availability.available_amount,
                    "unit": availability.unit,
                    "priority_support": True,
                    "preemption_support": True,
                    "context_aware": True
                }
                capabilities.append(capability)

        return capabilities

    def _get_optimization_suggestions_for_planner(self) -> List[Dict[str, Any]]:
        """
        Obtener sugerencias de optimización para el Planner.

        Returns:
            Lista de sugerencias de optimización
        """
        suggestions = []

        # Analizar presión de recursos
        for resource_type, pressure in self.get_resource_allocation_status_for_planner()["resource_pressure"].items():
            if pressure > 0.8:  # Alta presión
                suggestions.append({
                    "type": "resource_pressure_warning",
                    "resource": resource_type,
                    "pressure": pressure,
                    "recommendation": "Considerar redistribución o escalado"
                })
            elif pressure > 0.6:  # Media presión
                suggestions.append({
                    "type": "resource_monitoring",
                    "resource": resource_type,
                    "pressure": pressure,
                    "recommendation": "Monitorear uso continuo"
                })

        return suggestions
