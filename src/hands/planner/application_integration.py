"""Integración declarativa del conocimiento de aplicaciones con el planificador.

Convierte aplicaciones, capacidades y elementos de interfaz conocidos en
instancias del modelo canónico ``Node``. Este módulo no abre aplicaciones,
interactúa con la interfaz ni ejecuta callbacks: únicamente representa
conocimiento y ofrece consultas para las fases posteriores de planificación.
"""

from __future__ import annotations

import copy
import math
import re
import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:  # Convención de imports del proyecto cuando la raíz está en sys.path.
    from src.utils.logger import get_logger
except ImportError:  # Compatibilidad al importar como paquete ``src``.
    from src.utils.logger import get_logger

try:
    from src.hands.planner.node import Node, NodeType
except ImportError:
    from src.hands.planner.node import Node, NodeType

try:
    from src.memory.storage import get_memory_manager
except ImportError:
    from src.memory.storage import get_memory_manager

logger = get_logger(__name__)


class ApplicationKnowledgeIntegrator:
    """Integra conocimiento estructurado de aplicaciones con el planificador."""

    def __init__(self) -> None:
        # Importación diferida: applications_core puede depender de otros módulos
        # de manos/planificador durante el arranque de JARVIS.
        self.application_manager: Any = None
        self.memory_manager: Any = None

        try:
            get_application_manager = self._import_application_manager_factory()
            if callable(get_application_manager):
                self.application_manager = get_application_manager()
        except Exception as exc:
            logger.warning(
                "[APP-INTEGRATION] No se pudo cargar application manager: %s",
                exc,
            )

        try:
            self.memory_manager = get_memory_manager()
        except Exception as exc:
            # El conocimiento del catálogo sigue siendo útil sin memoria.
            logger.warning(
                "[APP-INTEGRATION] No se pudo cargar memory manager: %s",
                exc,
            )

        logger.info(
            "[APP-INTEGRATION] Integrador de conocimiento de aplicaciones inicializado"
        )

    @staticmethod
    def _import_application_manager_factory() -> Any:
        """Carga la fábrica del gestor sin imponer una única ruta de importación."""
        errors: List[BaseException] = []
        for module_name in (
            "src.hands.applications_core",
            "hands.applications_core",
        ):
            try:
                module = __import__(module_name, fromlist=["get_application_manager"])
                factory = getattr(module, "get_application_manager", None)
                if callable(factory):
                    return factory
            except (ImportError, AttributeError) as exc:
                errors.append(exc)
        if errors:
            raise ImportError(
                "No se encontró get_application_manager en applications_core"
            ) from errors[-1]
        return None

    # ------------------------------------------------------------------
    # NORMALIZACIÓN Y ACCESO SEGURO A DATOS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        """Lee una clave tanto de diccionarios como de objetos/dataclasses."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            return getattr(obj, key)
        except Exception:
            return default

    @staticmethod
    def _safe_copy(value: Any, default: Any = None) -> Any:
        try:
            return copy.deepcopy(value)
        except Exception:
            if default is not None:
                try:
                    return copy.copy(value)
                except Exception:
                    return default
            try:
                return copy.copy(value)
            except Exception:
                return default

    @staticmethod
    def _normalize_name(value: Any) -> str:
        """Normaliza un nombre para IDs y claves de estado deterministas."""
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        # Los signos separadores se convierten en guiones bajos; se conservan
        # caracteres alfanuméricos Unicode para no inutilizar nombres localizados.
        text = re.sub(r"[^\w]+", "_", raw, flags=re.UNICODE)
        return re.sub(r"_+", "_", text).strip("_")

    @classmethod
    def _capability_value(cls, capability: Any) -> str:
        """Obtiene el valor de una capacidad Enum, objeto, diccionario o string."""
        value = cls._get_value(capability, "value", capability)
        if value is None:
            value = cls._get_value(capability, "capability", "")
        return str(value or "").strip()

    @classmethod
    def _capability_key(cls, capability: Any) -> str:
        return cls._normalize_name(cls._capability_value(capability))

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        """Normaliza un valor o colección sin dividir strings/diccionarios."""
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        # Strings y dicts pueden ser valores declarativos; no deben dividirse
        # en caracteres o claves. Otros iterables (p. ej. generadores) se consumen.
        if isinstance(value, (str, bytes, dict)):
            return [value]
        if isinstance(value, Iterable):
            try:
                return list(value)
            except Exception:
                return [value]
        return [value]

    @classmethod
    def _normalized_conditions(cls, value: Any) -> List[Any]:
        """Copia precondiciones/efectos evitando mutar el catálogo de origen."""
        items = cls._as_list(value)
        normalized: List[Any] = []
        for item in items:
            if item is None:
                continue
            copied = cls._safe_copy(item, default=item)
            normalized.append(copied)
        return normalized

    @staticmethod
    def _unique_nodes(nodes: Iterable[Node]) -> List[Node]:
        """Deduplica Nodes por ID preservando orden y datos ya recogidos."""
        output: List[Node] = []
        by_id: Dict[str, Node] = {}
        for node in nodes:
            node_id = str(getattr(node, "id", "") or "").strip()
            if not node_id:
                logger.warning("[APP-INTEGRATION] Se descartó un Node sin ID")
                continue
            existing = by_id.get(node_id)
            if existing is None:
                by_id[node_id] = node
                output.append(node)
                continue

            # Un elemento UI puede ser requisito de varias capacidades. Se
            # conserva una sola instancia y se agrega trazabilidad declarativa.
            existing_metadata = getattr(existing, "metadata", None)
            new_metadata = getattr(node, "metadata", None)
            if isinstance(existing_metadata, dict) and isinstance(new_metadata, dict):
                providers = list(existing_metadata.get("required_by_capabilities", []))
                for capability in new_metadata.get("required_by_capabilities", []):
                    if capability not in providers:
                        providers.append(capability)
                if providers:
                    existing_metadata["required_by_capabilities"] = providers
        return output

    @staticmethod
    def _safe_cost(value: Any, default: float = 1.0) -> float:
        """Convierte costes a números finitos no negativos."""
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not math.isfinite(result) or result < 0:
            return default
        return result

    def _get_application(self, app_name: str) -> Any:
        if self.application_manager is None:
            return None
        lookup_name = str(app_name or "").strip()
        if not lookup_name:
            return None
        try:
            getter = getattr(self.application_manager, "get_application", None)
            if callable(getter):
                app = getter(lookup_name)
                if app is not None:
                    return app

            # Compatibilidad con managers que exponen el catálogo directamente.
            applications = getattr(self.application_manager, "applications", None)
            if isinstance(applications, dict):
                direct = applications.get(lookup_name)
                if direct is not None:
                    return direct
                normalized = self._normalize_name(lookup_name)
                for key, candidate in applications.items():
                    candidate_name = self._get_value(candidate, "name", key)
                    if self._normalize_name(candidate_name) == normalized:
                        return candidate
        except Exception as exc:
            logger.warning(
                "[APP-INTEGRATION] Error obteniendo aplicación %s: %s",
                lookup_name,
                exc,
            )
        return None

    # ------------------------------------------------------------------
    # CONVERSIÓN A NODOS
    # ------------------------------------------------------------------

    def convert_application_to_nodes(self, app_name: str) -> List[Node]:
        """Convierte una aplicación y sus capacidades en Nodes canónicos.

        Los nodos resultantes son declarativos. No contienen una orden implícita
        de ejecución y no invocan acciones ni callbacks de la aplicación.
        """
        app = self._get_application(app_name)
        if app is None:
            logger.info(
                "[APP-INTEGRATION] No existe una aplicación registrada: %s",
                app_name,
            )
            return []

        app_node = self._create_application_node(app)
        nodes: List[Node] = [app_node]
        capability_nodes: List[Node] = []

        for capability_def in self._as_list(self._get_value(app, "capabilities", [])):
            capability_node = self._create_capability_node(app, capability_def)
            capability_nodes.append(capability_node)
            nodes.append(capability_node)

            capability_value = self._capability_value(
                self._get_value(capability_def, "capability", capability_def)
            )
            ui_nodes: List[Node] = []
            for element_name in self._as_list(
                self._get_value(capability_def, "required_ui_elements", [])
            ):
                clean_element_name = str(element_name or "").strip()
                if not clean_element_name:
                    continue
                ui_nodes.append(
                    self._create_ui_element_node(
                        app,
                        clean_element_name,
                        capability_def,
                    )
                )
            nodes.extend(ui_nodes)

            # parent/children representan jerarquía declarativa, no precedencias
            # temporales. Las precondiciones/efectos conservan esa semántica aparte.
            capability_node.parent = app_node.id
            if capability_node.id not in app_node.children:
                app_node.children.append(capability_node.id)
            for ui_node in ui_nodes:
                ui_node.parent = app_node.id
                if ui_node.id not in capability_node.children:
                    capability_node.children.append(ui_node.id)
                ui_node_metadata = getattr(ui_node, "metadata", None)
                if isinstance(ui_node_metadata, dict):
                    providers = list(
                        ui_node_metadata.get("required_by_capabilities", [])
                    )
                    if capability_value and capability_value not in providers:
                        providers.append(capability_value)
                    ui_node_metadata["required_by_capabilities"] = providers

        unique_nodes = self._unique_nodes(nodes)
        self._validate_node_references(unique_nodes)
        logger.info(
            "[APP-INTEGRATION] Convertida aplicación %s en %s Nodes",
            self._get_value(app, "name", app_name),
            len(unique_nodes),
        )
        return unique_nodes

    def _create_application_node(self, app: Any) -> Node:
        """Crea el nodo declarativo principal de la aplicación."""
        app_name = str(self._get_value(app, "name", "application") or "application").strip()
        app_key = self._normalize_name(app_name) or "application"
        current_state = self._get_application_current_state(app_name)

        parameters = {
            "executable": self._safe_copy(self._get_value(app, "executable")),
            "url": self._safe_copy(self._get_value(app, "url")),
            "type": self._safe_copy(self._get_value(app, "type")),
            "login_required": bool(self._get_value(app, "login_required", False)),
            "calibration_policy": self._safe_copy(
                self._get_value(app, "calibration_policy")
            ),
        }
        metadata = {
            "application_type": self._safe_copy(self._get_value(app, "type")),
            "preflight_requirements": self._normalized_conditions(
                self._get_value(app, "preflight_requirements", [])
            ),
            "current_state": self._safe_copy(current_state, default={}) or {},
            "login_required": parameters["login_required"],
            "source": "application_knowledge",
        }

        return Node(
            id=f"app_{app_key}",
            type=NodeType.APPLICATION,
            name=app_name,
            description=f"Aplicación {app_name}",
            parameters=parameters,
            preconditions=self._generate_application_preconditions(app, current_state),
            effects=self._generate_application_effects(app),
            cost=5.0,
            dependencies=[],
            application=app_name,
            metadata=metadata,
        )

    def _create_capability_node(self, app: Any, capability_def: Any) -> Node:
        """Crea un nodo de acción reutilizable para una capacidad declarada."""
        app_name = str(self._get_value(app, "name", "application") or "application").strip()
        app_key = self._normalize_name(app_name) or "application"
        capability_raw = self._get_value(capability_def, "capability", capability_def)
        capability = self._capability_value(capability_raw)
        capability_key = self._normalize_name(capability) or "capability"
        node_id = f"{app_key}_{capability_key}"

        required_ui_elements = [
            str(item).strip()
            for item in self._as_list(
                self._get_value(capability_def, "required_ui_elements", [])
            )
            if str(item or "").strip()
        ]
        preconditions = self._normalized_conditions(
            self._get_value(capability_def, "preconditions", [])
        )

        # Las condiciones declarativas hacen referencia a claves de estado; la
        # lista dependencies se reserva a IDs reales de nodos.
        app_open_key = f"{app_key}_open"
        if app_open_key not in preconditions:
            preconditions.append(app_open_key)

        for element_name in required_ui_elements:
            element_key = self._normalize_name(element_name)
            availability_key = f"{app_key}_{element_key}_available"
            if element_key and availability_key not in preconditions:
                preconditions.append(availability_key)

        parameters = self._safe_copy(
            self._get_value(capability_def, "parameters", {}), default={}
        )
        if not isinstance(parameters, dict):
            parameters = {}
        parameters.update(
            {
                "application": app_name,
                "capability": capability,
                "required_ui_elements": list(required_ui_elements),
            }
        )

        metadata = self._safe_copy(
            self._get_value(capability_def, "metadata", {}), default={}
        )
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.update(
            {
                "source": "application_knowledge",
                "capability": capability,
                "application": app_name,
            }
        )

        default_name = capability.replace("_", " ").strip().title() or node_id
        return Node(
            id=node_id,
            type=NodeType.ACTION,
            name=str(self._get_value(capability_def, "name", default_name) or default_name),
            description=str(self._get_value(capability_def, "description", "") or ""),
            parameters=parameters,
            preconditions=preconditions,
            effects=self._normalized_conditions(
                self._get_value(capability_def, "effects", [])
            ),
            cost=self._safe_cost(self._get_value(capability_def, "cost", 1.0)),
            dependencies=[],
            application=app_name,
            ui_element=required_ui_elements[0] if required_ui_elements else None,
            metadata=metadata,
            reusable_action=True,
            action_category=str(
                self._get_value(capability_def, "action_category", "application_capability")
                or "application_capability"
            ),
        )

    def _create_ui_element_node(
        self,
        app: Any,
        element_name: str,
        capability_def: Any,
    ) -> Node:
        """Crea un nodo declarativo para un elemento UI conocido o requerido."""
        app_name = str(self._get_value(app, "name", "application") or "application").strip()
        app_key = self._normalize_name(app_name) or "application"
        element_key = self._normalize_name(element_name) or "unknown"
        node_id = f"{app_key}_{element_key}"

        element = None
        getter = self._get_value(app, "get_ui_element")
        try:
            if callable(getter):
                element = getter(element_name)
            else:
                ui_elements = self._get_value(app, "ui_elements", {})
                if isinstance(ui_elements, dict):
                    element = ui_elements.get(element_name)
                    if element is None:
                        for key, candidate in ui_elements.items():
                            if self._normalize_name(key) == element_key:
                                element = candidate
                                break
        except Exception as exc:
            logger.debug(
                "[APP-INTEGRATION] No se pudo consultar el elemento %s de %s: %s",
                element_name,
                app_name,
                exc,
            )

        element_type = self._get_value(element, "type", "unknown") if element is not None else "unknown"
        screen = self._get_value(element, "screen") if element is not None else None
        calibrated = self._is_element_calibrated(element)
        capability_value = self._capability_value(
            self._get_value(capability_def, "capability", capability_def)
        )

        preconditions: List[Any] = [f"{app_key}_open"]
        if calibrated:
            preconditions.append(f"{app_key}_{element_key}_calibrated")

        # Este nodo representa conocimiento sobre el elemento; no se afirma que
        # haya sido enfocado. El enfoque pertenece a una acción física posterior.
        effects: List[Any] = []
        if element is not None:
            effects.append(f"{app_key}_{element_key}_available")
        if calibrated:
            effects.append(f"{app_key}_{element_key}_calibrated")

        return Node(
            id=node_id,
            type=NodeType.UI_ELEMENT if element is not None else NodeType.RESOURCE,
            name=element_name,
            description=f"Elemento UI {element_name} de {app_name}",
            parameters={
                "type": self._safe_copy(element_type),
                "screen": self._safe_copy(screen),
                "calibrated": calibrated,
                "capability": capability_value,
            },
            preconditions=preconditions,
            effects=effects,
            cost=0.0,
            dependencies=[],
            application=app_name,
            ui_element=element_name,
            metadata={
                "source": "application_knowledge",
                "known": element is not None,
                "calibrated": calibrated,
                "required_by_capabilities": [capability_value] if capability_value else [],
            },
        )

    @classmethod
    def _is_element_calibrated(cls, element: Any) -> bool:
        if element is None:
            return False
        calibrated = cls._get_value(element, "is_calibrated")
        try:
            if callable(calibrated):
                return bool(calibrated())
            if calibrated is not None:
                return bool(calibrated)
            return bool(cls._get_value(element, "calibrated", False))
        except Exception:
            return False

    def _validate_node_references(self, nodes: Sequence[Node]) -> None:
        """Comprueba las relaciones jerárquicas creadas durante la conversión."""
        node_ids = {str(getattr(node, "id", "")) for node in nodes}
        for node in nodes:
            parent = getattr(node, "parent", None)
            if parent and parent not in node_ids:
                logger.warning(
                    "[APP-INTEGRATION] Parent %s de Node %s no está en el resultado",
                    parent,
                    getattr(node, "id", "unknown"),
                )
            children = getattr(node, "children", [])
            for child_id in children or []:
                if child_id not in node_ids:
                    logger.warning(
                        "[APP-INTEGRATION] Child %s de Node %s no está en el resultado",
                        child_id,
                        getattr(node, "id", "unknown"),
                    )

    # ------------------------------------------------------------------
    # ESTADO Y REQUISITOS
    # ------------------------------------------------------------------

    def _get_application_current_state(self, app_name: str) -> Dict[str, Any]:
        """Obtiene propiedades persistidas de la aplicación si existen."""
        if self.memory_manager is None:
            return {}
        try:
            app_key = self._normalize_name(app_name)
            entity = self.memory_manager.get_entity(f"app_{app_key}")
            if entity is not None:
                properties = self._get_value(entity, "properties", {})
                return self._safe_copy(properties, default={}) if isinstance(properties, dict) else {}
        except Exception as exc:
            logger.warning(
                "[APP-INTEGRATION] Error obteniendo estado de %s: %s",
                app_name,
                exc,
            )
        return {}

    def _generate_application_preconditions(
        self,
        app: Any,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """Genera las condiciones de preparación declaradas para la aplicación."""
        del current_state  # Estado observado no debe convertirse en requisito por sí solo.
        requirements = self._normalized_conditions(
            self._get_value(app, "preflight_requirements", [])
        )
        preconditions: List[Any] = []
        seen: Set[str] = set()
        for requirement in requirements:
            if isinstance(requirement, str):
                key = requirement.strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                preconditions.append(key)
            elif isinstance(requirement, dict):
                # Las precondiciones estructuradas se conservan y se deduplican
                # por contenido estable, no por identidad de objeto.
                if requirement not in preconditions:
                    preconditions.append(requirement)
            elif requirement not in preconditions:
                preconditions.append(requirement)
        return preconditions

    def _generate_application_effects(self, app: Any) -> List[str]:
        """Declara que la aplicación está registrada/disponible, no abierta."""
        app_key = self._normalize_name(self._get_value(app, "name", "application"))
        return [f"{app_key or 'application'}_available"]

    # ------------------------------------------------------------------
    # CONSULTAS
    # ------------------------------------------------------------------

    def get_applications_by_capability(self, capability: Any) -> List[str]:
        """Devuelve las aplicaciones que declaran una capacidad."""
        if self.application_manager is None:
            return []
        capability_value = self._capability_value(capability)
        candidates: Any = None
        getter = getattr(self.application_manager, "get_applications_by_capability", None)
        if not callable(getter):
            return []

        for candidate in (capability, capability_value):
            try:
                returned = getter(candidate)
                if returned is not None:
                    returned_items = self._as_list(returned)
                    if returned_items:
                        candidates = returned_items
                        break
                    if candidates is None:
                        candidates = returned_items
            except (TypeError, ValueError, KeyError):
                continue
            except Exception as exc:
                logger.warning(
                    "[APP-INTEGRATION] Error buscando aplicaciones por capacidad: %s",
                    exc,
                )
                return []

        names: List[str] = []
        for app in self._as_list(candidates):
            name = str(self._get_value(app, "name", "") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def get_application_capabilities(self, app_name: str) -> Dict[str, Any]:
        """Obtiene capacidades en formato declarativo, con fallback al catálogo."""
        app = self._get_application(app_name)
        if app is None:
            return {}

        getter = getattr(self.application_manager, "get_application_capabilities", None)
        if callable(getter):
            try:
                result = getter(app_name)
                if isinstance(result, dict):
                    return self._safe_copy(result, default={})
            except Exception as exc:
                logger.warning(
                    "[APP-INTEGRATION] Error obteniendo capacidades de %s: %s",
                    app_name,
                    exc,
                )

        declared: Dict[str, Any] = {}
        for definition in self._as_list(self._get_value(app, "capabilities", [])):
            capability = self._capability_value(
                self._get_value(definition, "capability", definition)
            )
            key = self._normalize_name(capability)
            if not key:
                continue
            declared[key] = {
                "capability": capability,
                "name": self._get_value(definition, "name", capability),
                "description": self._get_value(definition, "description", ""),
                "preconditions": self._normalized_conditions(
                    self._get_value(definition, "preconditions", [])
                ),
                "effects": self._normalized_conditions(
                    self._get_value(definition, "effects", [])
                ),
                "required_ui_elements": [
                    str(value).strip()
                    for value in self._as_list(
                        self._get_value(definition, "required_ui_elements", [])
                    )
                    if str(value or "").strip()
                ],
                "cost": self._safe_cost(self._get_value(definition, "cost", 1.0)),
            }
        return declared

    def get_ui_elements_for_capability(
        self,
        app_name: str,
        capability: Any,
    ) -> List[str]:
        """Obtiene los elementos UI requeridos por una capacidad declarada."""
        app = self._get_application(app_name)
        if app is None:
            return []
        capability_value = self._capability_value(capability)
        wanted_key = self._normalize_name(capability_value)

        try:
            getter = self._get_value(app, "get_capability")
            definition = getter(capability_value) if callable(getter) else None
            if definition is None:
                for candidate in self._as_list(self._get_value(app, "capabilities", [])):
                    value = self._capability_value(
                        self._get_value(candidate, "capability", candidate)
                    )
                    if self._normalize_name(value) == wanted_key:
                        definition = candidate
                        break
            if definition is None:
                return []
            return [
                str(item).strip()
                for item in self._as_list(
                    self._get_value(definition, "required_ui_elements", [])
                )
                if str(item or "").strip()
            ]
        except Exception as exc:
            logger.warning(
                "[APP-INTEGRATION] Error obteniendo elementos UI de %s/%s: %s",
                app_name,
                capability_value,
                exc,
            )
            return []

    def is_application_capable(self, app_name: str, capability: Any) -> bool:
        """Comprueba una capacidad utilizando el gestor o el catálogo de la app."""
        app = self._get_application(app_name)
        if app is None:
            return False
        checker = self._get_value(app, "is_capable")
        capability_value = self._capability_value(capability)
        if callable(checker):
            for candidate in (capability, capability_value):
                try:
                    return bool(checker(candidate))
                except (TypeError, ValueError, KeyError):
                    continue
                except Exception as exc:
                    logger.warning(
                        "[APP-INTEGRATION] Error comprobando capacidad %s/%s: %s",
                        app_name,
                        capability_value,
                        exc,
                    )
                    break

        wanted_key = self._normalize_name(capability_value)
        return any(
            self._normalize_name(
                self._capability_value(
                    self._get_value(item, "capability", item)
                )
            ) == wanted_key
            for item in self._as_list(self._get_value(app, "capabilities", []))
        )

    def is_application_available(self, app_name: str) -> bool:
        """Comprueba disponibilidad en tiempo de ejecución de una aplicación.

        Distingue **disponible** (ejecutable instalado / app con URL) de
        **simplemente declarada**. Delega en ``ApplicationKnowledge.is_available``
        cuando el gestor expone el modelo, o en
        ``ApplicationManager.is_application_available`` como alternativa.
        """
        app = self._get_application(app_name)
        if app is None:
            return False

        checker = self._get_value(app, "is_available")
        if callable(checker):
            try:
                return bool(checker())
            except Exception as exc:
                logger.warning(
                    "[APP-INTEGRATION] Error comprobando disponibilidad %s: %s",
                    app_name,
                    exc,
                )
                return False

        manager = self.application_manager
        manager_checker = self._get_value(manager, "is_application_available")
        if callable(manager_checker):
            try:
                return bool(manager_checker(app_name))
            except Exception as exc:
                logger.warning(
                    "[APP-INTEGRATION] Error comprobando disponibilidad %s: %s",
                    app_name,
                    exc,
                )
        return False

    def is_capability_available(self, app_name: str, capability: Any) -> bool:
        """Distingue una capacidad **disponible** de una sola **declarada**.

        Una capacidad está disponible cuando está declarada en el modelo
        (``is_application_capable``) **y** la aplicación es disponible en
        tiempo de ejecución (``is_application_available``).
        """
        if not self.is_application_capable(app_name, capability):
            return False
        return self.is_application_available(app_name)

    def register_application_knowledge(self, app_config: Dict[str, Any]) -> bool:
        """Registra conocimiento mediante la API pública de applications_core."""
        if not isinstance(app_config, dict):
            logger.warning("[APP-INTEGRATION] La configuración de aplicación debe ser un dict")
            return False
        app_name = str(app_config.get("name", "") or "").strip()
        if not app_name:
            logger.warning("[APP-INTEGRATION] No se registra una aplicación sin nombre")
            return False

        errors: List[BaseException] = []
        for module_name in (
            "src.hands.applications_core",
            "hands.applications_core",
        ):
            try:
                module = __import__(module_name, fromlist=["register_custom_application"])
                register = getattr(module, "register_custom_application", None)
                if callable(register):
                    return bool(register(self._safe_copy(app_config, default=app_config)))
            except (ImportError, AttributeError) as exc:
                errors.append(exc)
            except Exception as exc:
                logger.warning(
                    "[APP-INTEGRATION] Error registrando aplicación %s: %s",
                    app_name,
                    exc,
                )
                return False
        if errors:
            logger.warning(
                "[APP-INTEGRATION] No está disponible register_custom_application: %s",
                errors[-1],
            )
        return False


# ============================================================================
# SINGLETON Y COMPATIBILIDAD LEGACY
# ============================================================================

_app_integrator: Optional[ApplicationKnowledgeIntegrator] = None
_app_integrator_lock = threading.Lock()


def get_application_knowledge_integrator() -> ApplicationKnowledgeIntegrator:
    """Obtiene la instancia global del integrador, inicializada una sola vez."""
    global _app_integrator
    if _app_integrator is None:
        with _app_integrator_lock:
            if _app_integrator is None:
                _app_integrator = ApplicationKnowledgeIntegrator()
    return _app_integrator


def get_applications_by_capability(capability_name: str) -> List[str]:
    """Compatibilidad legacy; utiliza ApplicationCapability cuando está disponible."""
    capability: Any = capability_name
    try:
        errors: List[BaseException] = []
        for module_name in (
            "src.hands.applications_core",
            "hands.applications_core",
        ):
            try:
                module = __import__(module_name, fromlist=["ApplicationCapability"])
                enum_type = getattr(module, "ApplicationCapability", None)
                if enum_type is not None:
                    try:
                        capability = enum_type(capability_name)
                    except (ValueError, TypeError):
                        # Algunos catálogos usan nombres Enum y otros usan sus values.
                        member = getattr(enum_type, str(capability_name), None)
                        capability = member if member is not None else capability_name
                    break
            except (ImportError, AttributeError) as exc:
                errors.append(exc)
        return get_application_knowledge_integrator().get_applications_by_capability(
            capability
        )
    except Exception as exc:
        logger.warning(
            "[APP-INTEGRATION] Error en compatibilidad de capacidad %s: %s",
            capability_name,
            exc,
        )
        return []


def get_application_knowledge(app_name: str) -> Dict[str, Any]:
    """Compatibilidad legacy para consultar conocimiento de una aplicación."""
    return get_application_knowledge_integrator().get_application_capabilities(app_name)


__all__ = [
    "ApplicationKnowledgeIntegrator",
    "get_application_knowledge_integrator",
    "get_applications_by_capability",
    "get_application_knowledge",
]
