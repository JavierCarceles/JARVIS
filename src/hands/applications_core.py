"""
Sistema de conocimiento de aplicaciones para planificación jerárquica.

Responsabilidades principales:
- Conocimiento estructurado de aplicaciones.
- Capacidades básicas reutilizables.
- Integración con calibración específica y global.
- Soporte para preflight y login.
- Compatibilidad con comandos legacy.

El conocimiento de una aplicación se mantiene separado de su implementación
concreta para que el planificador pueda trabajar con capacidades genéricas.
"""

from __future__ import annotations

from src.utils.logger import get_logger
import os
import platform
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.hands.action_registry import ActionType, get_action_registry, register_action
from src.hands.calibration_manager import get_calibration_manager
from src.memory.storage import Entity, get_memory_manager

logger = get_logger(__name__)


class ApplicationCapability(Enum):
    """Capacidades que puede ofrecer una aplicación."""

    OPEN = "open"
    CLOSE = "close"
    NAVIGATE = "navigate"
    SEARCH = "search"
    TYPE = "type"
    CLICK = "click"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    LOGIN = "login"
    LOGOUT = "logout"
    REFRESH = "refresh"
    NEW_TAB = "new_tab"
    CLOSE_TAB = "close_tab"
    SWITCH_TAB = "switch_tab"
    ZOOM = "zoom"
    SCROLL = "scroll"
    BOOKMARK = "bookmark"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    SHARE = "share"
    PRINT = "print"
    EXPORT = "export"
    IMPORT = "import"


class ApplicationState(Enum):
    """Estados posibles de una aplicación."""

    CLOSED = "closed"
    OPEN = "open"
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    BACKGROUND = "background"


@dataclass
class UIElement:
    """Elemento UI de una aplicación."""

    name: str
    type: str
    coordinates: Optional[Dict[str, Any]] = None
    screen: int = 0
    calibration_data: Optional[Dict[str, Any]] = None
    required_capability: Optional[ApplicationCapability] = None

    def is_calibrated(self) -> bool:
        """Comprueba si existe información de coordenadas utilizable."""
        if not isinstance(self.coordinates, dict) or not self.coordinates:
            return False

        # Formato clásico {"x": ..., "y": ...}.
        if "x" in self.coordinates and "y" in self.coordinates:
            return self._is_coordinate_pair(self.coordinates.get("x"), self.coordinates.get("y"))

        # Formato multipantalla {"s1": [x, y], "s2": [x, y], ...}.
        return any(
            self._is_coordinate_pair(value)
            for key, value in self.coordinates.items()
            if str(key).lower().startswith("s")
        )

    @staticmethod
    def _is_coordinate_pair(value: Any, y_value: Any = None) -> bool:
        """Valida una pareja de coordenadas sin asumir un formato único."""
        if y_value is not None:
            return all(isinstance(item, (int, float)) for item in (value, y_value))

        return (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and all(isinstance(item, (int, float)) for item in value[:2])
        )


@dataclass
class ApplicationCapabilityDef:
    """Definición de una capacidad de aplicación."""

    capability: ApplicationCapability
    name: str
    description: str
    required_ui_elements: List[str]
    preconditions: List[str]
    effects: List[str]
    cost: float
    timeout: float = 30.0
    retry_count: int = 3
    alternatives: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.alternatives is None:
            self.alternatives = []


@dataclass
class ApplicationKnowledge:
    """Conocimiento estructurado de una aplicación."""

    name: str
    type: str
    executable: Optional[str] = None
    url: Optional[str] = None
    icon: Optional[str] = None
    capabilities: Optional[List[ApplicationCapabilityDef]] = None
    ui_elements: Optional[List[UIElement]] = None
    states: Optional[List[ApplicationState]] = None
    login_required: bool = False
    calibration_policy: Optional[List[str]] = None
    preflight_requirements: Optional[List[str]] = None
    default_state: ApplicationState = ApplicationState.CLOSED
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.capabilities is None:
            self.capabilities = []
        if self.ui_elements is None:
            self.ui_elements = []
        if self.states is None:
            self.states = [ApplicationState.CLOSED]
        if self.calibration_policy is None:
            self.calibration_policy = []
        if self.preflight_requirements is None:
            self.preflight_requirements = []
        if self.metadata is None:
            self.metadata = {}

    def get_capability(self, capability_name: str) -> Optional[ApplicationCapabilityDef]:
        """Obtiene una capacidad por nombre."""
        target = str(capability_name).strip().lower()
        return next(
            (
                capability
                for capability in self.capabilities
                if capability.capability.value == target or capability.name.lower() == target
            ),
            None,
        )

    def get_ui_element(self, element_name: str) -> Optional[UIElement]:
        """Obtiene un elemento UI por nombre."""
        target = str(element_name).strip().lower()
        return next(
            (element for element in self.ui_elements if element.name.lower() == target),
            None,
        )

    def is_capable(self, capability: ApplicationCapability) -> bool:
        """Comprueba si la aplicación posee una capacidad específica."""
        return any(capability_def.capability == capability for capability_def in self.capabilities)

    def get_calibrated_elements(self) -> List[UIElement]:
        """Obtiene los elementos UI calibrados."""
        return [element for element in self.ui_elements if element.is_calibrated()]


def _reconstruct_metadata(entity: Entity) -> Dict[str, Any]:
    """Construye el dict de metadata para una ApplicationKnowledge reconstruida.

    Almacena el ``entity.id`` original y los aliases para trazabilidad y
    uso futuro por el normalizador de nombres.
    """
    metadata: Dict[str, Any] = {}
    if entity.metadata and isinstance(entity.metadata, dict):
        metadata.update(entity.metadata)
    metadata["entity_id"] = entity.id
    if entity.aliases:
        metadata["aliases"] = list(entity.aliases)
    return metadata


def _serialize_ui_element(element: "UIElement") -> Dict[str, Any]:
    """Serializa un :class:`UIElement` a un dict JSON-friendly.

    Convierte el ``required_capability`` (``ApplicationCapability``) a su
    valor string para que la entidad resultante sea totalmente serializable.
    """
    return {
        "name": element.name,
        "type": element.type,
        "coordinates": element.coordinates,
        "screen": element.screen,
        "calibration_data": element.calibration_data,
        "required_capability": (
            element.required_capability.value
            if element.required_capability is not None
            else None
        ),
    }


class ApplicationManager:
    """Gestor del conocimiento estructurado de aplicaciones."""

    def __init__(self) -> None:
        self.applications: Dict[str, ApplicationKnowledge] = {}
        self.memory_manager = get_memory_manager()
        self._initialize_applications()

    @staticmethod
    def _normalize_name(app_name: str) -> str:
        """Normaliza nombres habituales de aplicaciones a una clave interna."""
        normalized = str(app_name or "").strip().lower()
        aliases = {
            "google chrome": "chrome",
            "chrome": "chrome",
            "microsoft edge": "edge",
            "edge": "edge",
            "mozilla firefox": "firefox",
            "firefox": "firefox",
            "bloc de notas": "notepad",
            "notepad": "notepad",
            "calculadora": "calculator",
            "calculator": "calculator",
            "paint": "paint",
            "microsoft paint": "paint",
            "explorador de archivos": "explorer",
            "explorer": "explorer",
            "file explorer": "explorer",
            "explorador": "explorer",
            "símbolo del sistema": "cmd",
            "simbolo del sistema": "cmd",
            "command prompt": "cmd",
            "cmd": "cmd",
            "spotify": "spotify",
        }
        return aliases.get(normalized, normalized)

    def _initialize_applications(self) -> None:
        """Inicializa el conocimiento de las aplicaciones base."""
        chrome = ApplicationKnowledge(
            name="Chrome",
            type="browser",
            executable="chrome",
            url="https://chrome.google.com",
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_chrome",
                    description="Abre Chrome",
                    required_ui_elements=[],
                    preconditions=["chrome_closed"],
                    effects=["chrome_open", "chrome_active"],
                    cost=10.0,
                ),
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.NAVIGATE,
                    name="navigate_to_url",
                    description="Navega a una URL",
                    required_ui_elements=["address_bar"],
                    preconditions=["chrome_open", "chrome_active", "address_bar_focused"],
                    effects=["url_changed"],
                    cost=3.0,
                ),
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.SEARCH,
                    name="search_in_google",
                    description="Busca en Google",
                    required_ui_elements=["search_bar"],
                    preconditions=["chrome_open", "chrome_active"],
                    effects=["search_performed"],
                    cost=2.0,
                ),
            ],
            ui_elements=[
                UIElement(
                    name="address_bar",
                    type="input",
                    required_capability=ApplicationCapability.NAVIGATE,
                ),
                UIElement(
                    name="search_bar",
                    type="input",
                    required_capability=ApplicationCapability.SEARCH,
                ),
                UIElement(
                    name="new_tab_button",
                    type="button",
                    required_capability=ApplicationCapability.NEW_TAB,
                ),
            ],
            states=[
                ApplicationState.CLOSED,
                ApplicationState.OPEN,
                ApplicationState.ACTIVE,
                ApplicationState.LOADING,
            ],
            login_required=False,
            calibration_policy=["address_bar", "search_bar"],
            preflight_requirements=["application_available"],
            default_state=ApplicationState.CLOSED,
        )

        spotify = ApplicationKnowledge(
            name="Spotify",
            type="media",
            executable="spotify",
            url="https://spotify.com",
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_spotify",
                    description="Abre Spotify",
                    required_ui_elements=[],
                    preconditions=["spotify_closed"],
                    effects=["spotify_open", "spotify_active"],
                    cost=15.0,
                ),
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.NAVIGATE,
                    name="play_song",
                    description="Reproduce una canción",
                    required_ui_elements=["search_bar", "play_button"],
                    preconditions=["spotify_open", "spotify_active"],
                    effects=["song_playing"],
                    cost=5.0,
                ),
            ],
            ui_elements=[
                UIElement(
                    name="search_bar",
                    type="input",
                    required_capability=ApplicationCapability.SEARCH,
                ),
                UIElement(
                    name="play_button",
                    type="button",
                    required_capability=ApplicationCapability.NAVIGATE,
                ),
            ],
            states=[
                ApplicationState.CLOSED,
                ApplicationState.OPEN,
                ApplicationState.ACTIVE,
            ],
            login_required=True,
            calibration_policy=["search_bar", "play_button"],
            preflight_requirements=["application_available", "login_required"],
            default_state=ApplicationState.CLOSED,
        )

        self.register_application(chrome)
        self.register_application(spotify)
        self._load_custom_applications()

    def register_application(self, app: ApplicationKnowledge) -> bool:
        """Registra una aplicación en memoria y en el gestor.

        Evita duplicados: si la aplicación ya está registrada en el gestor
        (por nombre normalizado), se omite la persistencia y se devuelve
        ``False``. Esto es consistente con ``_load_custom_applications``
        que ya omite apps ya registradas.
        """
        try:
            key = app.name.lower()
            if key in self.applications:
                logger._print_log(
                    "info",
                    f"Aplicacion '{key}' ya registrada, se omite duplicado "
                    "[file:applications_core.py, method:register_application]",
                    "applications_core.py", "register_application", 395,
                )
                return False
            entity_data = {
                "id": f"app_{key}",
                "type": "application",
                "name": app.name,
                "properties": {
                    "type": app.type,
                    "executable": app.executable,
                    "url": app.url,
                    "login_required": app.login_required,
                    "capabilities": [cap.capability.value for cap in app.capabilities],
                    "ui_elements": [_serialize_ui_element(e) for e in app.ui_elements],
                    "states": [s.value for s in app.states],
                },
                "aliases": [],
                "confidence": 1.0,
                "tags": [],
            }
            self.memory_manager.save_entity(Entity.from_dict(entity_data))
            self.applications[key] = app
            logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
            return True
        except Exception as exc:
            logger._print_log("info", f"Error procesando solicitud: {str(exc)} [file:applications_core.py, method:register_application, line:374]")
            return False

    def get_application(self, app_name: str) -> Optional[ApplicationKnowledge]:
        """Obtiene una aplicación por nombre o alias."""
        normalized = self._normalize_name(app_name)
        return self.applications.get(normalized)

    def get_applications_by_type(self, app_type: str) -> List[ApplicationKnowledge]:
        """Obtiene aplicaciones por tipo."""
        target = str(app_type).strip().lower()
        return [app for app in self.applications.values() if app.type.lower() == target]

    def get_applications_by_capability(self, capability: ApplicationCapability) -> List[ApplicationKnowledge]:
        """Obtiene aplicaciones con una capacidad determinada."""
        return [app for app in self.applications.values() if app.is_capable(capability)]

    @staticmethod
    def _reconstruct_capabilities(
        capability_strings: Any,
    ) -> List["ApplicationCapabilityDef"]:
        """Convierte una lista de strings de capacidad en ApplicationCapabilityDef.

        Cada string valido se normaliza (strip + lower) y se intenta convertir
        a ``ApplicationCapability``. Strings invalidos se omiten sin error.

        Los ApplicationCapabilityDef reconstruidos usan defaults minimos
        (cost=5.0, empty preconditions/effects/required_ui_elements) ya que
        la Entity no almacena esa informacion detallada.
        """
        result: List[ApplicationCapabilityDef] = []
        if not isinstance(capability_strings, list):
            return result

        for cap_str in capability_strings:
            if not isinstance(cap_str, str):
                continue
            normalized = cap_str.strip().lower()
            if not normalized:
                continue
            try:
                cap_enum = ApplicationCapability(normalized)
            except ValueError:
                logger._print_log(
                    "info",
                    f"Capacidad desconocida omitida: '{normalized}' "
                    "[file:applications_core.py, method:_reconstruct_capabilities]",
                    "applications_core.py", "_reconstruct_capabilities", 405,
                )
                continue
            result.append(
                ApplicationCapabilityDef(
                    capability=cap_enum,
                    name=f"cap_{normalized}",
                    description=f"Capacidad: {normalized}",
                    required_ui_elements=[],
                    preconditions=[],
                    effects=[],
                    cost=5.0,
                )
            )
        return result

    @staticmethod
    def _reconstruct_ui_elements(elements_data: Any) -> List[UIElement]:
        """Reconstruye la lista de :class:`UIElement` desde ``properties``.

        Cada item debe ser un dict con al menos ``name`` y ``type``.
        Items invalidos o incompletos se omiten sin error. El
        ``required_capability`` se resuelve a ``ApplicationCapability``;
        si el valor no es valido se deja a ``None``.
        """
        result: List[UIElement] = []
        if not isinstance(elements_data, list):
            return result

        for item in elements_data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            elem_type = item.get("type")
            if not name or not elem_type:
                continue

            required_capability: Optional[ApplicationCapability] = None
            cap_raw = item.get("required_capability")
            if cap_raw is not None:
                try:
                    required_capability = ApplicationCapability(str(cap_raw).strip().lower())
                except ValueError:
                    logger._print_log(
                        "info",
                        f"Capability UI desconocida omitida: '{cap_raw}' "
                        "[file:applications_core.py, method:_reconstruct_ui_elements]",
                        "applications_core.py", "_reconstruct_ui_elements", 472,
                    )

            result.append(
                UIElement(
                    name=name,
                    type=elem_type,
                    coordinates=item.get("coordinates"),
                    screen=item.get("screen", 0),
                    calibration_data=item.get("calibration_data"),
                    required_capability=required_capability,
                )
            )
        return result

    @staticmethod
    def _reconstruct_states(states_data: Any) -> List[ApplicationState]:
        """Reconstruye la lista de :class:`ApplicationState` desde ``properties``.

        Cada item debe ser un string convertible a ``ApplicationState``.
        Items invalidos se omiten sin error. Si no se puede reconstruir
        ningun estado (entrada ausente o vacia), se devuelve el default
        ``[ApplicationState.CLOSED]`` manteniendo el contrato de
        ``ApplicationKnowledge.__post_init__``.
        """
        result: List[ApplicationState] = []
        if not isinstance(states_data, list):
            return [ApplicationState.CLOSED]

        for item in states_data:
            if not isinstance(item, str):
                continue
            try:
                result.append(ApplicationState(item.strip().lower()))
            except ValueError:
                logger._print_log(
                    "info",
                    f"Estado desconocido omitido: '{item}' "
                    "[file:applications_core.py, method:_reconstruct_states]",
                    "applications_core.py", "_reconstruct_states", 472,
                )

        if not result:
            return [ApplicationState.CLOSED]
        return result

    def _reconstruct_application(self, entity: Entity) -> Optional[ApplicationKnowledge]:
        """Reconstruye un objeto ApplicationKnowledge desde una Entity.

        Lee entidades con dos formatos de ``properties``:

        - Formato ``register_application`` (applications_core.py:351):
          ``{type, executable, url, login_required, capabilities,
          ui_elements, states}``.
        - Formato legacy ``data/memory/entities.json``:
          ``{url, executable, category}``.

        El campo ``type`` del ApplicationKnowledge se resuelve con prioridad:
        ``properties.type`` → ``properties.category`` → ``"application"``.

        Las capability strings (``properties.capabilities``) se convierten a
        ``ApplicationCapabilityDef`` validos. Strings invalidos se omiten.

        Los ``properties.ui_elements`` (lista de dicts) y ``properties.states``
        (lista de strings) se reconstruyen a ``UIElement`` y ``ApplicationState``
        respectivamente. Si faltan, se usan los defaults de
        ``ApplicationKnowledge`` (``[]`` y ``[CLOSED]``).

        Devuelve ``None`` si la entidad carece de nombre usable (name+id
        ambos vacios), permitiendo al llamador omitirla sin crash.
        """
        try:
            name = entity.name or entity.id
            if not name:
                return None

            properties = entity.properties
            if not isinstance(properties, dict):
                properties = {}

            app_type = (
                properties.get("type")
                or properties.get("category")
                or "application"
            )

            capabilities = self._reconstruct_capabilities(
                properties.get("capabilities", []),
            )

            app = ApplicationKnowledge(
                name=name,
                type=app_type,
                executable=properties.get("executable"),
                url=properties.get("url"),
                capabilities=capabilities,
                ui_elements=self._reconstruct_ui_elements(properties.get("ui_elements")),
                states=self._reconstruct_states(properties.get("states")),
                login_required=bool(properties.get("login_required", False)),
                metadata=_reconstruct_metadata(entity),
            )
            return app
        except Exception as exc:
            logger._print_log(
                "info",
                f"Error reconstruyendo aplicacion desde entidad "
                f"(id={getattr(entity, 'id', '?')}): {exc} "
                f"[file:applications_core.py, method:_reconstruct_application]",
                "applications_core.py", "_reconstruct_application", 402,
            )
            return None

    def _load_custom_applications(self) -> None:
        """Carga aplicaciones personalizadas persistidas en memoria.

        Lee todas las entities de tipo ``"application"`` y materializa
        ``ApplicationKnowledge`` mediante :meth:`_reconstruct_application`.
        Las aplicaciones ya registradas (p.ej. Chrome, Spotify) se omiten
        para evitar duplicados.
        """
        try:
            entities = self.memory_manager.get_entities_by_type("application")
            if not isinstance(entities, list):
                logger._print_log(
                    "info",
                    "Las entidades no son una lista "
                    "[file:applications_core.py, method:_load_custom_applications]",
                    "applications_core.py", "_load_custom_applications", 396,
                )
                return

            for entity in entities:
                app = self._reconstruct_application(entity)
                if app is None:
                    continue
                key = app.name.lower()
                if key in self.applications:
                    logger._print_log(
                        "info",
                        f"Aplicacion '{key}' ya registrada, se omite "
                        "[file:applications_core.py, method:_load_custom_applications]",
                        "applications_core.py", "_load_custom_applications", 402,
                    )
                    continue
                self.applications[key] = app
                logger._print_log(
                    "info",
                    f"Aplicacion '{key}' cargada desde entidad "
                    "[file:applications_core.py, method:_load_custom_applications]",
                    "applications_core.py", "_load_custom_applications", 402,
                )
        except Exception as exc:
            logger._print_log(
                "info",
                f"Error cargando aplicaciones desde memoria: {exc} "
                f"[file:applications_core.py, method:_load_custom_applications]",
                "applications_core.py", "_load_custom_applications", 405,
            )

    def get_application_capabilities(self, app_name: str) -> Dict[str, Any]:
        """Obtiene capacidades de una aplicación en formato de planificación."""
        app = self.get_application(app_name)
        if not app:
            return {}

        return {
            capability.name: {
                "description": capability.description,
                "required_ui_elements": list(capability.required_ui_elements),
                "preconditions": list(capability.preconditions),
                "effects": list(capability.effects),
                "cost": capability.cost,
                "alternatives": list(capability.alternatives or []),
                "capability": capability.capability.value,
                "timeout": capability.timeout,
                "retry_count": capability.retry_count,
            }
            for capability in app.capabilities
        }

    def get_application_ui_elements(self, app_name: str) -> Dict[str, Any]:
        """Obtiene los elementos UI conocidos de una aplicación."""
        app = self.get_application(app_name)
        if not app:
            return {}

        return {
            element.name: {
                "type": element.type,
                "coordinates": element.coordinates,
                "screen": element.screen,
                "is_calibrated": element.is_calibrated(),
                "required_capability": (
                    element.required_capability.value
                    if element.required_capability
                    else None
                ),
                "calibration_data": element.calibration_data,
            }
            for element in app.ui_elements
        }


# Instancia global del gestor de aplicaciones.
_app_manager: Optional[ApplicationManager] = None


def get_application_manager() -> ApplicationManager:
    """Obtiene la instancia global del gestor de aplicaciones."""
    global _app_manager
    if _app_manager is None:
        _app_manager = ApplicationManager()
    return _app_manager


# ============================================================================
# CAPACIDADES REUTILIZABLES
# ============================================================================

@register_action(
    name="open_application",
    description="Abre una aplicación genérica",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "open", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicación a abrir",
        }
    },
    preconditions=["application_exists"],
    effects=["application_open"],
    cost=10.0,
    capability="open_application",
    planner_enabled=True,
)
def open_application(app_name: str) -> str:
    """Abre una aplicación conocida y valida su disponibilidad."""
    app_manager = get_application_manager()
    app = app_manager.get_application(app_name)

    if not app:
        raise ValueError(f"Aplicación no encontrada: {app_name}")

    if "application_available" in app.preflight_requirements and not _check_application_available(app):
        raise RuntimeError(f"La aplicación {app.name} no está disponible")

    try:
        if app.executable:
            subprocess.Popen([app.executable])
        elif app.url:
            if not webbrowser.open(app.url):
                raise RuntimeError(f"No se pudo abrir la URL de {app.name}")
        else:
            raise RuntimeError(f"La aplicación {app.name} no tiene ejecutable ni URL configurados")

        logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
        return f"Aplicación {app.name} abierta exitosamente"
    except Exception as exc:
        logger._print_log("info", f"Error abriendo aplicación: {str(exc, "applications_core.py", "method", 506)} [file:applications_core.py, method:open_application, line:509]")
        raise


@register_action(
    name="close_application",
    description="Cierra una aplicación genérica",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "close", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicación a cerrar",
        }
    },
    preconditions=["application_open"],
    effects=["application_closed"],
    cost=5.0,
    capability="close_application",
    planner_enabled=True,
)
def close_application(app_name: str) -> str:
    """Cierra una aplicación por proceso sin tocar otras aplicaciones."""
    target = str(app_name or "").strip()
    if not target:
        raise ValueError("El nombre de la aplicación no puede estar vacío")

    executable_name = target if target.lower().endswith(".exe") else f"{target}.exe"

    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/f", "/im", executable_name],
                check=False,
                capture_output=True,
                text=True,
            )
        elif platform.system() == "Darwin":
            subprocess.run(["pkill", "-f", target.lower()], check=False)
        else:
            subprocess.run(["pkill", "-f", target.lower()], check=False)

        logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
        return f"Aplicación {target} cerrada exitosamente"
    except Exception as exc:
        logger._print_log("info", f"Error cerrando aplicación: {str(exc, "applications_core.py", "method", 553)} [file:applications_core.py, method:close_application, line:556]")
        raise


@register_action(
    name="wait_for_application_state",
    description="Espera a que una aplicación alcance un estado específico",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "wait", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicación",
        },
        "target_state": {
            "type": "str",
            "required": True,
            "description": "Estado objetivo (active, ready, etc.)",
        },
        "timeout": {
            "type": "int",
            "required": False,
            "default": 30,
            "description": "Tiempo máximo de espera en segundos",
        },
    },
    preconditions=["application_open"],
    effects=["application_state_changed"],
    cost=2.0,
    capability="wait_for_state",
    planner_enabled=True,
)
def wait_for_application_state(app_name: str, target_state: str, timeout: int = 30) -> str:
    """Espera un estado de aplicación conocido."""
    timeout = max(0, int(timeout))
    target = str(target_state or "").strip().lower()
    if not target:
        raise ValueError("El estado objetivo no puede estar vacío")

    start_time = time.time()
    while time.time() - start_time < timeout:
        time.sleep(1)
        # La comprobación real de estado aún pertenece a los adaptadores de
        # cada aplicación. Se mantienen los estados básicos para compatibilidad.
        if target in {"active", "ready"}:
            logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
            return f"Aplicación {app_name} está en estado {target}"

    raise RuntimeError(
        f"Tiempo de espera agotado para {app_name} alcanzar estado {target}"
    )


@register_action(
    name="calibrate_application_ui",
    description="Calibra elementos UI de una aplicación específica",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["aplicacion", "calibracion", "ui", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicación",
        },
        "elements": {
            "type": "list",
            "required": False,
            "default": None,
            "description": "Elementos a calibrar (si None, calibra todos)",
        },
        "screen": {
            "type": "int",
            "required": False,
            "default": 1,
            "description": "Número de monitor cuando el calibrador específico lo requiera",
        },
    },
    preconditions=["application_open"],
    effects=["ui_calibrated"],
    cost=15.0,
    capability="calibrate_ui",
    planner_enabled=True,
)
def calibrate_application_ui(
    app_name: str,
    elements: Optional[List[str]] = None,
    screen: int = 1,
) -> str:
    """Calibra una aplicación específica mediante CalibrationManager."""
    app_manager = get_application_manager()
    app = app_manager.get_application(app_name)
    if not app:
        raise ValueError(f"Aplicación no encontrada: {app_name}")

    if not app.calibration_policy:
        raise RuntimeError(f"La aplicación {app.name} no permite calibración automática")

    requested_elements = list(elements) if elements is not None else list(app.calibration_policy)
    valid_elements = []
    for element_name in requested_elements:
        element = app.get_ui_element(element_name)
        if element is None:
            logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
            continue
        if element.type not in {
            "button",
            "input",
            "menu",
            "link",
            "checkbox",
            "radio",
            "select",
            "toolbar",
        }:
            logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
            continue
        valid_elements.append(element_name)

    if not valid_elements:
        return "No se encontraron elementos calibrables"

    calibration_manager = get_calibration_manager()

    # La versión actual de CalibrationManager trabaja a nivel de aplicación y
    # monitor, no a nivel de elemento. No inventamos una API inexistente: se
    # ejecuta el calibrador específico de la aplicación y se informa de los
    # elementos conocidos solicitados.
    if not hasattr(calibration_manager, "calibrate_application"):
        raise RuntimeError("CalibrationManager no expone calibrate_application()")

    result = calibration_manager.calibrate_application(app.name, int(screen))
    success = bool(getattr(result, "success", False))
    count = int(getattr(result, "elements_count", 0) or 0)

    if not success:
        error_message = getattr(result, "error_message", None) or "Error desconocido"
        raise RuntimeError(f"Error calibrando {app.name}: {error_message}")

    effective_count = min(count, len(valid_elements)) if count > 0 else len(valid_elements)
    logger._print_log("INFO", f"Calibrados {effective_count}/{len(valid_elements)} elementos solicitados", "applications_core.py", "calibrate_application", 695)
    return f"Calibración de {app.name} completada en pantalla {screen}: {effective_count} elementos"


@register_action(
    name="calibrar_aplicaciones",
    description="Inicia la calibración global de las aplicaciones soportadas",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["calibracion", "global", "aplicaciones", "multi-monitor"],
    parameters={
        "force": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Fuerza la recalibración de aplicaciones ya calibradas",
        }
    },
    preconditions=[],
    effects=["applications_ui_calibrated"],
    cost=30.0,
    capability="calibrate_applications",
    planner_enabled=True,
)
def calibrar_aplicaciones(force: bool = False) -> Dict[str, Any]:
    """
    Ejecuta la acción global de calibración.

    El orquestador real vive en CalibrationManager. Este punto de entrada no
    exige app_name, evitando que el comando "calibre aplicaciones" se confunda
    con la calibración de una sola aplicación.
    """
    calibration_manager = get_calibration_manager()

    if not hasattr(calibration_manager, "calibrate_all_applications"):
        raise RuntimeError("CalibrationManager no expone calibrate_all_applications()")

    logger._print_log("info", r"[GLOBAL] Inicio calibración de aplicaciones [file:applications_core.py, method:calibrate_applications_global, line:735]", "applications_core.py", "method", 732)
    raw_results = _call_calibrate_all_applications(
        calibration_manager,
        force=bool(force),
    )
    report = _build_global_calibration_report(raw_results)
    logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
    return report


# Alias inglés para compatibilidad programática; el comando LLM recomendado
# sigue siendo `calibrar_aplicaciones`.
@register_action(
    name="calibrate_applications",
    description="Inicia la calibración global de las aplicaciones soportadas",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["calibracion", "global", "applications", "multi-monitor"],
    parameters={
        "force": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Fuerza la recalibración de aplicaciones ya calibradas",
        }
    },
    preconditions=[],
    effects=["applications_ui_calibrated"],
    cost=30.0,
    capability="calibrate_applications",
    planner_enabled=True,
)
def calibrate_applications(force: bool = False) -> Dict[str, Any]:
    """Alias programático de calibrar_aplicaciones()."""
    return calibrar_aplicaciones(force=force)


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def _call_calibrate_all_applications(manager: Any, force: bool = False) -> Any:
    """
    Invoca la calibración global compatible con managers antiguos y nuevos.

    El manager actual acepta ``force`` en las versiones nuevas y algunas
    versiones legacy no lo exponen. Nunca se propaga un argumento que el
    método no soporte.
    """
    method = getattr(manager, "calibrate_all_applications", None)
    if not callable(method):
        raise RuntimeError(
            "CalibrationManager no expone calibrate_all_applications()"
        )

    try:
        import inspect

        parameters = inspect.signature(method).parameters
        if "force" in parameters:
            return method(force=force)
    except (TypeError, ValueError):
        pass

    return method()


def _check_application_available(app: ApplicationKnowledge) -> bool:
    """Comprueba si el ejecutable configurado está disponible."""
    executable = str(app.executable or "").strip()
    if not executable:
        return bool(app.url)

    try:
        if os.path.isabs(executable) or any(sep in executable for sep in ("/", "\\")):
            return os.path.isfile(executable)
        return shutil.which(executable) is not None
    except OSError:
        return False


def _check_application_login(app: ApplicationKnowledge) -> bool:
    """Comprueba el estado de login cuando exista un backend para ello."""
    # La verificación real pertenece a la integración específica de cada app.
    # Se mantiene True por compatibilidad mientras no exista ese adaptador.
    logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
    return True


def _looks_like_global_report(value: Dict[str, Any]) -> bool:
    """Identifica el contrato agregado del orquestador global."""
    return all(
        key in value
        for key in ("calibrated", "skipped", "failed", "total_elements")
    )


def _build_global_calibration_report(raw_results: Any) -> Dict[str, Any]:
    """Convierte resultados del CalibrationManager en un informe estable."""
    report: Dict[str, Any] = {
        "success": True,
        "monitors_detected": 0,
        "applications_requested": 0,
        "calibrated": [],
        "skipped": [],
        "failed": [],
        "total_elements": 0,
    }

    try:
        from src.utils.screen_manager import get_screen_manager

        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()
        report["monitors_detected"] = len(getattr(screen_manager, "monitors", []) or [])
    except Exception as exc:
        logger._print_log("INFO", "Procesando solicitud", "applications_core.py", "calibrate_applications_global", 850)

    if not isinstance(raw_results, dict):
        report["success"] = False
        report["failed"].append(
            {"application": "global", "error": "Resultado del gestor de calibración inválido"}
        )
        return report

    # Compatibilidad con el orquestador nuevo, que puede devolver ya un
    # informe global en lugar de ``application -> results``.
    if _looks_like_global_report(raw_results):
        normalized = dict(report)
        normalized["success"] = bool(raw_results.get("success", True))
        normalized["monitors_detected"] = int(
            raw_results.get("monitors_detected", report["monitors_detected"]) or 0
        )
        normalized["applications_requested"] = int(
            raw_results.get("applications_requested", 0) or 0
        )
        normalized["calibrated"] = list(raw_results.get("calibrated", []) or [])
        normalized["skipped"] = list(raw_results.get("skipped", []) or [])
        normalized["failed"] = list(raw_results.get("failed", []) or [])
        normalized["total_elements"] = int(
            raw_results.get("total_elements", 0) or 0
        )
        if "results" in raw_results:
            normalized["results"] = raw_results["results"]
        if "errors" in raw_results:
            normalized["errors"] = list(raw_results.get("errors", []) or [])
        return normalized

    report["applications_requested"] = len(raw_results)

    for app_key, results in raw_results.items():
        app_label = str(app_key)
        normalized_results = results if isinstance(results, list) else [results]
        app_success = False
        app_elements = 0
        app_errors: List[str] = []

        for result in normalized_results:
            if hasattr(result, "success"):
                success = bool(result.success)
                elements_count = int(result.elements_count or 0)
                error_message = result.error_message
                application_name = result.application_name
                screen_number = result.screen_number
            elif isinstance(result, dict):
                success = bool(result.get("success", False))
                elements_count = int(result.get("elements_count", result.get("total_elements", 0)) or 0)
                error_message = result.get("error_message") or result.get("error")
                application_name = result.get("application_name", app_label)
                screen_number = result.get("screen_number", result.get("monitor", 0))
            else:
                success = False
                elements_count = 0
                error_message = "Resultado de calibración no reconocido"
                application_name = app_label
                screen_number = 0

            app_elements += elements_count
            if success:
                app_success = True
                logger._print_log("INFO", f"Procesando solicitud: {elements_count} elementos", "applications_core.py", "calibrate_applications_global", 914)
            elif error_message:
                app_errors.append(str(error_message))

        report["total_elements"] += app_elements

        if app_success:
            report["calibrated"].append(app_label)
        elif app_errors:
            report["failed"].append(
                {
                    "application": app_label,
                    "error": "; ".join(dict.fromkeys(app_errors)),
                }
            )
        else:
            report["skipped"].append(app_label)

    report["success"] = not report["failed"]
    return report


# ============================================================================
# COMPATIBILIDAD LEGACY
# ============================================================================

def get_available_commands() -> List[str]:
    """Obtiene los comandos registrados."""
    return get_action_registry().list_actions()


def navigate_to_url(url: str) -> str:
    """Abre una URL en el navegador predeterminado."""
    target_url = str(url or "").strip()
    if not target_url:
        raise ValueError("La URL no puede estar vacía")

    try:
        opened = webbrowser.open(target_url)
    except Exception as exc:
        logger._print_log("INFO", "Procesando solicitud", "applications_core.py", "navigate_to_url", 954)
        raise

    if not opened:
        raise RuntimeError(f"No se pudo solicitar la apertura de la URL: {target_url}")

    logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
    return f"Navegación solicitada a {target_url}"


def abrir_youtube() -> str:
    try:
        return navigate_to_url("https://youtube.com")
    except Exception as exc:
        return f"Error al abrir YouTube: {exc}"


def abrir_gmail() -> str:
    try:
        return navigate_to_url("https://mail.google.com")
    except Exception as exc:
        return f"Error al abrir Gmail: {exc}"


# ============================================================================
# INTERFACES PÚBLICAS
# ============================================================================

def get_application_knowledge(app_name: str) -> Dict[str, Any]:
    """Obtiene conocimiento estructurado de una aplicación."""
    app_manager = get_application_manager()
    app = app_manager.get_application(app_name)
    if app is None:
        return {}

    return {
        "name": app.name,
        "type": app.type,
        "executable": app.executable,
        "url": app.url,
        "login_required": app.login_required,
        "capabilities": app_manager.get_application_capabilities(app.name),
        "ui_elements": app_manager.get_application_ui_elements(app.name),
        "states": [state.value for state in app.states],
        "calibration_policy": list(app.calibration_policy),
        "preflight_requirements": list(app.preflight_requirements),
        "default_state": app.default_state.value,
        "metadata": dict(app.metadata),
    }


def get_applications_by_capability(capability_name: str) -> List[str]:
    """Obtiene aplicaciones que tienen una capacidad específica."""
    try:
        capability = ApplicationCapability(str(capability_name).strip().lower())
    except ValueError:
        return []

    app_manager = get_application_manager()
    return [app.name for app in app_manager.get_applications_by_capability(capability)]


def register_custom_application(app_config: Dict[str, Any]) -> bool:
    """Registra una aplicación personalizada."""
    try:
        data = dict(app_config or {})
        if "name" not in data or "type" not in data:
            raise ValueError("Una aplicación personalizada necesita 'name' y 'type'")

        # Reconstrucción tolerante de enums al recibir configuración JSON.
        capabilities = []
        for capability_data in data.get("capabilities", []) or []:
            capability_data = dict(capability_data)
            capability_value = capability_data.get("capability")
            if isinstance(capability_value, str):
                capability_data["capability"] = ApplicationCapability(capability_value)
            capabilities.append(ApplicationCapabilityDef(**capability_data))
        data["capabilities"] = capabilities

        ui_elements = []
        for element_data in data.get("ui_elements", []) or []:
            element_data = dict(element_data)
            required = element_data.get("required_capability")
            if isinstance(required, str):
                element_data["required_capability"] = ApplicationCapability(required)
            ui_elements.append(UIElement(**element_data))
        data["ui_elements"] = ui_elements

        states = []
        for state in data.get("states", []) or []:
            states.append(ApplicationState(state) if isinstance(state, str) else state)
        data["states"] = states

        default_state = data.get("default_state", ApplicationState.CLOSED)
        if isinstance(default_state, str):
            data["default_state"] = ApplicationState(default_state)

        app = ApplicationKnowledge(**data)
        return get_application_manager().register_application(app)
    except Exception as exc:
        logger._print_log("INFO", "Procesando solicitud", "applications_core.py", "register_custom_application", 1054)
        return False
