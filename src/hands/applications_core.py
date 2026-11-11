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
import ctypes
import difflib
import os
import platform
import shutil
import subprocess
import time
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.hands.calibration_manager import SW_RESTORE, SW_MAXIMIZE, USER32

from src.hands.action_registry import ActionType, get_action_registry, register_action
from src.hands.application_preflight import ApplicationPreflight, get_application_preflight
from src.hands.calibration_manager import get_calibration_manager
from src.memory.storage import Entity, get_memory_manager
from src.utils.screen_manager import get_screen_manager

logger = get_logger(__name__)

RESOLUTION_FUZZY_THRESHOLD = 0.7
_MAX_RESOLUTION_ALTERNATIVES = 3
RESOLUTION_AMBIGUITY_GAP = 0.05


@dataclass
class ApplicationResolutionResult:
    """Resultado de la resolución de una aplicación por nombre.

    Atributos:
        app: Aplicación resuelta o ``None`` si no hubo coincidencia.
        confidence: Confianza de la coincidencia (1.0 exacto/alias, ratio
            difuso para nombres imperfectos, 0.0 sin coincidencia).
        method: Método usado: ``exact_normalized``, ``dynamic_alias``,
            ``fuzzy_name``, ``fuzzy_alias`` o ``none``.
        alternatives: Otras aplicaciones candidatas ordenadas por similitud
            (solo se rellena en resolución difusa).
        is_ambiguous: ``True`` cuando la resolución difusa tiene otra
            candidata dentro del umbral de proximidad
            (``RESOLUTION_AMBIGUITY_GAP``) del mejor resultado, por lo que no
            debe seleccionarse silenciosamente una aplicación posiblemente
            incorrecta. El llamador debe pedir aclaración al usuario.
        ambiguity_reason: Descripción legible de la ambigüedad detectada o
            ``None`` si no hay ambigüedad.
    """

    app: Optional[ApplicationKnowledge]
    confidence: float
    method: str
    alternatives: List[ApplicationKnowledge]
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None


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
    """Elemento UI de una aplicación — conocimiento declarativo con calibración.

    Representa **qué** elementos de interfaz conoce la aplicación y **cuál**
    capacidad requiere. Mantiene tanto el conocimiento estructurado (nombre,
    tipo, descripción, capacidad asociada) como la información de calibración
    necesaria para localizar el elemento en pantalla en tiempo de ejecución
    (coordinates, screen, is_calibrated).
    """

    name: str
    type: str
    description: str = ""
    required_capability: Optional[ApplicationCapability] = None
    coordinates: Optional[Dict[str, Any]] = None
    screen: int = 0
    calibration_data: Optional[Dict[str, Any]] = None

    def is_calibrated(self) -> bool:
        """Indica si el elemento tiene coordenadas válidas para hacer clic."""
        if self.coordinates is None:
            return False
        if isinstance(self.coordinates, dict):
            return "x" in self.coordinates and "y" in self.coordinates
        return bool(self.coordinates)


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

    def get_observed_facts(self) -> Dict[str, Any]:
        """Devuelve los hechos observados durante el descubrimiento.

        Son datos reales obtenidos del sistema (ruta del ejecutable,
        ventana detectada, proceso activo, etc.). Devuelve dict vacio
        cuando no hay metadata o no se registraron hechos observados.
        """
        if not self.metadata:
            return {}
        return dict(self.metadata.get("observed_facts") or {})

    def get_inferred_data(self) -> Dict[str, Any]:
        """Devuelve los datos inferidos o no verificados.

        Son deducciones no verificadas (tipo por extension, suposicion
        de capacidad, etc.). Devuelve dict vacio cuando no hay metadata
        o no se registraron datos inferidos.
        """
        if not self.metadata:
            return {}
        return dict(self.metadata.get("inferred_data") or {})

    def get_unverified_capabilities(self) -> List["ApplicationCapabilityDef"]:
        """Devuelve las capacidades declaradas pero no verificadas en tiempo de ejecucion.

        Una capacidad esta verificada cuando esta declarada
        (``is_capable``) y la aplicacion esta disponible en runtime
        (``is_available``). Las no verificadas son las declaradas cuya
        disponibilidad no puede confirmarse. Esto permite al Planner
        distinguir capacidades reales de suposiciones.
        """
        result: List["ApplicationCapabilityDef"] = []
        for cap in (self.capabilities or []):
            if self.is_capable(cap.capability) and not self.is_capability_available(cap.capability):
                result.append(cap)
        return result

    def get_inferred_capabilities(self) -> List["ApplicationCapabilityDef"]:
        """Devuelve las capacidades inferidas (no confirmadas) almacenadas en
        ``inferred_data``.

        Estas capacidades NO estan en ``self.capabilities`` y por tanto
        ``is_capable`` retorna ``False`` para ellas: no se tratan como
        capacidades confirmadas de la aplicacion. Solo son deducciones no
        verificadas (tipo por extension, suposicion de capacidad, etc.).
        """
        inferred_data = self.get_inferred_data()
        caps_inferidas = inferred_data.get("capabilities_inferidas") if inferred_data else None
        if not caps_inferidas:
            return []
        result: List["ApplicationCapabilityDef"] = []
        for cap_dict in caps_inferidas:
            try:
                result.append(
                    ApplicationCapabilityDef(
                        capability=ApplicationCapability(str(cap_dict.get("capability", ""))),
                        name=str(cap_dict.get("name", "")),
                        description=str(cap_dict.get("description", "")),
                        required_ui_elements=list(cap_dict.get("required_ui_elements") or []),
                        preconditions=list(cap_dict.get("preconditions") or []),
                        effects=list(cap_dict.get("effects") or []),
                        cost=float(cap_dict.get("cost", 0.0)),
                        timeout=float(cap_dict.get("timeout", 30.0)),
                        retry_count=int(cap_dict.get("retry_count", 3)),
                        alternatives=list(cap_dict.get("alternatives") or []),
                    )
                )
            except (ValueError, KeyError, TypeError):
                # Capacidad inferida mal formada: se omite, no se asume como confirmada.
                continue
        return result

    def get_ui_element(self, element_name: str) -> Optional[UIElement]:
        """Obtiene un elemento UI por nombre."""
        target = str(element_name).strip().lower()
        return next(
            (element for element in self.ui_elements if element.name.lower() == target),
            None,
        )

    def is_capable(self, capability: ApplicationCapability) -> bool:
        """Comprueba si la aplicación posee una capacidad específica.

        Esta es una comprobación **declarativa**: verifica únicamente que la
        capacidad está registrada en el modelo de conocimiento, sin garantizar
        que la aplicación esté disponible en tiempo de ejecución. Para esa
        distinción, usar :meth:`is_capability_available`.
        """
        return any(capability_def.capability == capability for capability_def in self.capabilities)

    def is_available(self) -> bool:
        """Comprueba si la aplicación está disponible en tiempo de ejecución.

        Reúne la lógica de :func:`_check_application_available` como método de
        modelo: una aplicación está disponible si su ejecutable está en el
        PATH o en una ruta de archivo válida, o si no tiene ejecutable pero sí
        URL. No distingue mayúsculas/minúsculas del ejecutable ni resuelve
        aliases; la normalización de nombres recae sobre el gestor.
        """
        return _check_application_available(self)

    def is_capability_available(
        self, capability: ApplicationCapability
    ) -> bool:
        """Distingue una capacidad **disponible** de una sola **declarada**.

        Una capacidad está disponible cuando está declarada en el modelo
        (:meth:`is_capable`) **y** la aplicación es disponible en tiempo de
        ejecución (:meth:`is_available`). Devuelve ``False`` siempre que la
        aplicación no pueda comprobarse o la capacidad no esté declarada.
        """
        return self.is_capable(capability) and self.is_available()

    def get_calibrated_elements(self) -> List[UIElement]:
        """Obtiene los elementos UI conocidos que tienen coordenadas calibradas.

        El conocimiento declarativo (``UIElement``) no almacena coordenadas;
        la calibración se consulta en tiempo de ejecución al
        ``CoordinateManager``, que gestiona ``data/macros_coords.json``.
        Si el gestor no está disponible, devuelve una lista vacía.
        """
        try:
            from src.hands.coordinate_manager import get_coordinate_manager
            coord_manager = get_coordinate_manager()
        except Exception:
            return []

        if coord_manager is None:
            return []

        app_key = self.metadata.get("entity_id", self.name).strip().lower() if self.metadata else self.name
        result: List[UIElement] = []
        for element in self.ui_elements:
            resource_id = f"{app_key}.{element.name.strip().lower()}"
            resource = coord_manager.get_ui_resource(resource_id)
            if resource is not None and resource.is_usable:
                result.append(element)
        return result


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

    Serializa conocimiento declarativo (name, type, description,
    required_capability) y datos de calibración (coordinates, screen,
    calibration_data) para poder localizar el elemento en pantalla en tiempo
    de ejecución.
    """
    result: Dict[str, Any] = {
        "name": element.name,
        "type": element.type,
        "description": element.description,
        "required_capability": (
            element.required_capability.value
            if element.required_capability is not None
            else None
        ),
    }
    if element.coordinates is not None:
        result["coordinates"] = element.coordinates
    if element.screen != 0:
        result["screen"] = element.screen
    if element.calibration_data is not None:
        result["calibration_data"] = element.calibration_data
    return result


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
            key = self._normalize_name(app.name)
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

    def register_discovered_application(
        self,
        name: str,
        type: str = "application",
        executable: Optional[str] = None,
        url: Optional[str] = None,
        observed_facts: Optional[Dict[str, Any]] = None,
        inferred_data: Optional[Dict[str, Any]] = None,
        inferred_capabilities: Optional[List[ApplicationCapabilityDef]] = None,
        capabilities: Optional[List[ApplicationCapabilityDef]] = None,
        ui_elements: Optional[List[UIElement]] = None,
        states: Optional[List[ApplicationState]] = None,
        login_required: bool = False,
        calibration_policy: Optional[List[str]] = None,
        preflight_requirements: Optional[List[str]] = None,
        default_state: ApplicationState = ApplicationState.CLOSED,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApplicationKnowledge:
        """Registra temporalmente una aplicacion descubierta en memoria sin
        persistir en entities.json.

        La aplicacion representa un descubrimiento en tiempo de ejecucion que
        no existe en el catalogo conocido. Se almacena solo en el diccionario
        en memoria ``self.applications`` y NO se guarda mediante
        ``memory_manager.save_entity``, por lo que no altera el esquema, las
        siete entidades originales ni el contenido de
        ``data/memory/entities.json``.

        Separacion conceptual de la informacion:
        - ``observed_facts``: datos reales del descubrimiento (ruta del
          ejecutable, ventana detectada, proceso activo, etc.).
        - ``inferred_data``: deducciones no verificadas (tipo por extension,
          suposicion de capacidad, capacidades inferidas, etc.).
        - ``capabilities``: capacidades declaradas/confirmadas del modelo de
          conocimiento (no son inferencias; solo capacidades observadas o
          confirmadas).
        - Las capacidades inferidas (``inferred_capabilities``) NO se
          persisten como capacidades confirmadas en
          ``ApplicationKnowledge.capabilities``: se guardan en
          ``inferred_data`` para mantener el contrato
          ``observed_facts`` / ``inferred_data`` /
          ``unverified_capabilities`` de :class:`ApplicationKnowledge`.

        Args:
            name: Nombre de la aplicacion descubierta.
            app_type: Tipo de aplicacion (default "application").
            executable: Ruta al ejecutable, si se observo.
            url: URL de la aplicacion, si se conocio.
            observed_facts: Hechos observados durante el descubrimiento.
            inferred_data: Datos inferidos / no verificados.
            inferred_capabilities: Capacidades inferidas (no confirmadas) que
              NO se anaden a ``capabilities``; se almacenan en
              ``inferred_data`` para no tratarlas como confirmadas.
            capabilities: Capacidades declaradas/confirmadas (no inferidas).
            ui_elements: Elementos UI conocidos (sin calibracion).
            states: Estados conocidos de la aplicacion.
            login_required: Si se requiere login.
            calibration_policy: Politicas de calibracion.
            preflight_requirements: Requisitos de preflight.
            default_state: Estado por defecto.
            metadata: Metadatos adicionales (se fusionan con discovered/temporary).

        Returns:
            El objeto ApplicationKnowledge creado y registrado en memoria.
        """
        discovered_metadata: Dict[str, Any] = {
            "discovered": True,
            "temporary": True,
            "source": "discovery",
        }
        if observed_facts:
            discovered_metadata["observed_facts"] = observed_facts
        if inferred_data:
            discovered_metadata["inferred_data"] = inferred_data
        # Las capacidades inferidas NO se anaden a capabilities (no son
        # confirmadas): se almacenan en inferred_data para mantener el
        # contrato observed_facts / inferred_data / unverified_capabilities.
        if inferred_capabilities:
            if "inferred_data" not in discovered_metadata:
                discovered_metadata["inferred_data"] = {}
            descuberta_inferida = dict(discovered_metadata["inferred_data"])
            descuberta_inferida["capabilities_inferidas"] = [
                {
                    "capability": cap.capability.value,
                    "name": cap.name,
                    "description": cap.description,
                    "required_ui_elements": list(cap.required_ui_elements),
                    "preconditions": list(cap.preconditions),
                    "effects": list(cap.effects),
                    "cost": cap.cost,
                    "timeout": cap.timeout,
                    "retry_count": cap.retry_count,
                    "alternatives": list(cap.alternatives or []),
                }
                for cap in inferred_capabilities
            ]
            discovered_metadata["inferred_data"] = descuberta_inferida
        if metadata:
            discovered_metadata.update(metadata)

        app = ApplicationKnowledge(
            name=name,
            type=type,
            executable=executable,
            url=url,
            capabilities=capabilities,
            ui_elements=ui_elements,
            states=states,
            login_required=login_required,
            calibration_policy=calibration_policy,
            preflight_requirements=preflight_requirements,
            default_state=default_state,
            metadata=discovered_metadata,
        )

        key = self._normalize_name(app.name)

        # 1. Si ya existe una app bajo la clave normalizada, no reemplazar:
        #    conservar siempre la entrada previa (nunca sobrescribir una app de
        #    catálogo con una descubierta homónima).
        if key in self.applications:
            existing = self.applications[key]
            logger._print_log(
                "info",
                f"Aplicacion descubierta '{key}' ya existe en memoria por "
                f"nombre normalizado duplicado; se conserva la entrada previa "
                f"y no se reemplaza. "
                "[file:applications_core.py, method:register_discovered_application]",
                "applications_core.py", "register_discovered_application",
            )
            return existing

        # 2. Detectar conflictos por alias: el nombre normalizado de la nueva
        #    app no debe coincidir con un alias de ninguna app existente, ni los
        #    aliases de la nueva con nombres/aliases de apps existentes.
        new_aliases = []
        if app.metadata and isinstance(app.metadata, dict):
            new_aliases = [str(a).strip().lower() for a in (app.metadata.get("aliases") or [])]

        for existing_app in self.applications.values():
            existing_key = self._normalize_name(existing_app.name)
            existing_aliases = []
            if existing_app.metadata and isinstance(existing_app.metadata, dict):
                existing_aliases = [str(a).strip().lower() for a in (existing_app.metadata.get("aliases") or [])]

            # 2a. Nombre normalizado de la nueva == alias de una existente.
            if key in existing_aliases:
                logger._print_log(
                    "info",
                    f"Aplicacion descubierta '{key}' colisiona con un alias de "
                    f"la aplicacion ya registrada '{existing_key}'; se conserva "
                    f"la entrada previa y no se reemplaza. "
                    "[file:applications_core.py, method:register_discovered_application]",
                    "applications_core.py", "register_discovered_application",
                )
                return existing_app

            # 2b. Alias de la nueva == nombre normalizado de una existente.
            if existing_key in new_aliases:
                logger._print_log(
                    "info",
                    f"Aplicacion descubierta '{key}' declara un alias que "
                    f"colisiona con el nombre normalizado de '{existing_key}'; "
                    f"se conserva la entrada previa y no se reemplaza. "
                    "[file:applications_core.py, method:register_discovered_application]",
                    "applications_core.py", "register_discovered_application",
                )
                return existing_app

            # 2c. Alias de la nueva == alias de una existente.
            if any(a in existing_aliases for a in new_aliases):
                logger._print_log(
                    "info",
                    f"Aplicacion descubierta '{key}' declara un alias que "
                    f"colisiona con un alias de '{existing_key}'; se conserva "
                    f"la entrada previa y no se reemplaza. "
                    "[file:applications_core.py, method:register_discovered_application]",
                    "applications_core.py", "register_discovered_application",
                )
                return existing_app

        # 3. Sin conflictos: registrar y retornar la nueva app.
        self.applications[key] = app
        logger._print_log(
            "info",
            f"Aplicacion descubierta registrada temporalmente en memoria: '{key}' "
            "[file:applications_core.py, method:register_discovered_application]",
            "applications_core.py", "register_discovered_application",
        )
        return app

    def get_application(self, app_name: str) -> Optional[ApplicationKnowledge]:
        """Obtiene una aplicación por nombre o alias.

        Resuelve primero mediante ``_normalize_name`` (alias estáticos
        hardcodeados) y, si no encuentra nada, busca en los aliases
        dinámicos almacenados en ``metadata['aliases']`` de las
        aplicaciones ya registradas (provenientes de ``Entity.aliases``
        al materializar apps desde entities.json).
        """
        normalized = self._normalize_name(app_name)
        app = self.applications.get(normalized)
        if app is not None:
            return app
        return self._resolve_alias(normalized)

    def _resolve_alias(self, normalized_name: str) -> Optional[ApplicationKnowledge]:
        """Resuelve un alias dinámico contra las aplicaciones ya registradas.

        Busca ``normalized_name`` en ``metadata['aliases']`` de cada
        aplicación registrada. Los aliases provienen de ``Entity.aliases``
        al materializar apps desde entities.json (ver
        ``_reconstruct_metadata``).
        """
        for existing_app in self.applications.values():
            if existing_app.metadata and isinstance(existing_app.metadata, dict):
                aliases = existing_app.metadata.get("aliases")
                if aliases:
                    alias_list = [str(a).lower() for a in aliases]
                    if normalized_name in alias_list:
                        return existing_app
        return None

    def resolve_application(self, app_name: str) -> ApplicationResolutionResult:
        """Resuelve una aplicación a partir de un nombre ya normalizado.

        Orden de resolución:
        1. nombre normalizado exacto (incluye los alias estáticos de
           ``_normalize_name``);
        2. alias dinámico (``metadata['aliases']`` de las aplicaciones
           registradas, vía ``_resolve_alias``);
        3. nombre imperfecto (errores de escritura, variantes) mediante
           coincidencia difusa con ``difflib`` sobre el nombre y los aliases
           de cada aplicación registrada.

        Devuelve la mejor coincidencia con su confianza, el método usado y las
        alternativas ordenadas por similitud. Si no hay coincidencia,
        devuelve ``app=None``, ``confidence=0.0`` y ``method="none"``.

        Cuando la resolución es difusa y existe otra candidata dentro del
        umbral de proximidad (``RESOLUTION_AMBIGUITY_GAP``) del mejor
        resultado, el campo ``is_ambiguous`` se establece en ``True`` junto
        con una ``ambiguity_reason``, para que el llamador no seleccione
        silenciosamente una aplicación posiblemente incorrecta y pueda pedir
        aclaración al usuario.
        """
        normalized = self._normalize_name(app_name or "")

        # 1. Exacto: nombre normalizado (cubre alias estáticos hardcodeados).
        app = self.applications.get(normalized)
        if app is not None:
            return ApplicationResolutionResult(
                app=app, confidence=1.0, method="exact_normalized", alternatives=[]
            )

        # 2. Alias dinámico de aplicaciones ya registradas.
        app = self._resolve_alias(normalized)
        if app is not None:
            return ApplicationResolutionResult(
                app=app, confidence=1.0, method="dynamic_alias", alternatives=[]
            )

        # 3. Difuso: nombres imperfectos sobre nombre y aliases registrados.
        best_app: Optional[ApplicationKnowledge] = None
        best_ratio = 0.0
        best_method = "none"
        candidates: list = []
        for candidate in self.applications.values():
            ratios: list = []
            name_ratio = difflib.SequenceMatcher(None, normalized, candidate.name.lower()).ratio()
            ratios.append(("fuzzy_name", name_ratio))
            if candidate.metadata and isinstance(candidate.metadata, dict):
                for alias in candidate.metadata.get("aliases") or []:
                    alias_ratio = difflib.SequenceMatcher(
                        None, normalized, str(alias).lower()
                    ).ratio()
                    ratios.append(("fuzzy_alias", alias_ratio))
            method, ratio = max(ratios, key=lambda item: item[1])
            if ratio > best_ratio:
                best_ratio = ratio
                best_app = candidate
                best_method = method
            candidates.append((ratio, candidate))

        if best_app is not None and best_ratio >= RESOLUTION_FUZZY_THRESHOLD:
            sorted_candidates = sorted(
                candidates, key=lambda item: item[0], reverse=True
            )
            alternatives = [
                candidate_app
                for ratio, candidate_app in sorted_candidates
                if candidate_app is not best_app
            ][:_MAX_RESOLUTION_ALTERNATIVES]

            # Detectar coincidencias ambiguas: si otra candidata está lo
            # suficientemente cerca del mejor resultado, no se selecciona
            # silenciosamente una aplicación posiblemente incorrecta. Se marca
            # la ambigüedad para que el llamador pueda pedir aclaración.
            is_ambiguous = False
            ambiguity_reason = None
            for ratio, candidate_app in sorted_candidates:
                if candidate_app is best_app:
                    continue
                if best_ratio - ratio < RESOLUTION_AMBIGUITY_GAP:
                    is_ambiguous = True
                    ambiguity_reason = (
                        f"Coincidencia ambigua entre '{best_app.name}' y "
                        f"'{candidate_app.name}' (diferencia de similitud "
                        f"{best_ratio - ratio:.2f} < umbral "
                        f"{RESOLUTION_AMBIGUITY_GAP})"
                    )
                    break

            return ApplicationResolutionResult(
                app=best_app,
                confidence=best_ratio,
                method=best_method,
                alternatives=alternatives,
                is_ambiguous=is_ambiguous,
                ambiguity_reason=ambiguity_reason,
            )

        return ApplicationResolutionResult(
            app=None, confidence=best_ratio, method="none", alternatives=[]
        )

    def calculate_resolution_evidence(self, app_name: str) -> dict:
        """Calcula y conserva la evidencia/confianza de una resolución de aplicación.

        Utiliza :meth:`resolve_application` para obtener el resultado y
        calcula una puntuación de evidencia basada en la confianza, el método
        usado y la presencia de alternativas. La evidencia se conserva en el
        ``metadata`` de la aplicación resuelta (mecanismo existente).

        La puntuación de evidencia pondera el ``confidence`` por el método
        (exacto/alias = 1.0, difuso = 0.8) y aplica una penalización leve por
        cada alternativa candidata (máximo 0.2), de modo que una resolución
        exacta sin alternativas puntúa 1.0 y una resolución difusa ambigua
        puntúa menor.

        Argumentos:
            app_name: Nombre de la aplicación a resolver (ya normalizado o no).

        Retorna:
            Diccionario con claves: ``app_name``, ``app_name_resolved`` (si hay
            coincidencia), ``confidence``, ``method``, ``evidence_score``,
            ``has_match``, ``alternatives_count``, ``is_ambiguous`` y
            ``ambiguity_reason`` (ambigüedad de la resolución, si procede).
        """
        result = self.resolve_application(app_name)

        if result.app is None:
            return {
                "app_name": app_name,
                "app_name_resolved": None,
                "confidence": result.confidence,
                "method": result.method,
                "evidence_score": 0.0,
                "has_match": False,
                "alternatives_count": 0,
                "is_ambiguous": False,
                "ambiguity_reason": None,
            }

        confidence = result.confidence
        method_weight = {
            "exact_normalized": 1.0,
            "dynamic_alias": 1.0,
            "fuzzy_name": 0.8,
            "fuzzy_alias": 0.8,
            "none": 0.0,
        }.get(result.method, 0.5)

        alternatives_penalty = min(len(result.alternatives) * 0.05, 0.2)
        evidence_score = max(0.0, min(1.0, confidence * method_weight - alternatives_penalty))

        if result.app.metadata is None:
            result.app.metadata = {}
        result.app.metadata["resolution_evidence"] = {
            "confidence": confidence,
            "method": result.method,
            "evidence_score": evidence_score,
            "resolved_name": app_name,
            "is_ambiguous": result.is_ambiguous,
            "ambiguity_reason": result.ambiguity_reason,
        }

        return {
            "app_name": app_name,
            "app_name_resolved": result.app.name,
            "confidence": confidence,
            "method": result.method,
            "evidence_score": evidence_score,
            "has_match": True,
            "alternatives_count": len(result.alternatives),
            "is_ambiguous": result.is_ambiguous,
            "ambiguity_reason": result.ambiguity_reason,
        }

    def get_stored_resolution_evidence(self, app_name: str) -> Optional[dict]:
        """Recupera la evidencia de resolución guardada para una aplicación.

        Busca la aplicación por nombre normalizado (clave de
        ``self.applications``) y devuelve el contenido de
        ``metadata["resolution_evidence"]`` si existe.

        Argumentos:
            app_name: Nombre de la aplicación (se normaliza internamente).

        Retorna:
            Diccionario con la evidencia guardada o ``None`` si no hay nada
            registrado para esa aplicación.
        """
        normalized = self._normalize_name(app_name or "")
        app = self.applications.get(normalized)
        if app is None or not app.metadata:
            return None
        return app.metadata.get("resolution_evidence")

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
                    description=item.get("description", ""),
                    required_capability=required_capability,
                    coordinates=item.get("coordinates"),
                    screen=item.get("screen", 0),
                    calibration_data=item.get("calibration_data"),
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
                key = self._normalize_name(app.name)
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
        """Obtiene los elementos UI conocidos de una aplicación.

        Devuelve el **conocimiento declarativo** de cada elemento (type,
        description, required_capability). La información de coordenadas
        concretas se consulta por separado al ``CoordinateManager``.
        """
        app = self.get_application(app_name)
        if not app:
            return {}

        return {
            element.name: {
                "type": element.type,
                "description": element.description,
                "required_capability": (
                    element.required_capability.value
                    if element.required_capability
                    else None
                ),
            }
            for element in app.ui_elements
        }

    def is_application_available(self, app_name: str) -> bool:
        """Comprueba disponibilidad en tiempo de ejecución de una aplicación.

        Distingue **disponible** (el ejecutable está instalado o la app tiene
        URL) de **simplemente declarada** (existe en el modelo pero su
        ejecutable no está disponible). Delega en ``ApplicationKnowledge.is_available``.
        """
        app = self.get_application(app_name)
        if not app:
            return False
        try:
            return bool(app.is_available())
        except Exception as exc:
            logger._print_log(
                "info",
                f"Error comprobando disponibilidad de {app_name}: {exc} "
                "[file:applications_core.py, method:is_application_available]",
                "applications_core.py", "is_application_available", 778,
            )
            return False

    def is_capability_available(
        self, app_name: str, capability: ApplicationCapability
    ) -> bool:
        """Distingue una capacidad **disponible** de una sola **declarada**.

        Una capacidad está disponible si está declarada en el modelo
        (``ApplicationKnowledge.is_capable``) y la aplicación es disponible
        en tiempo de ejecución (``ApplicationKnowledge.is_available``).
        """
        app = self.get_application(app_name)
        if not app:
            return False
        try:
            return bool(app.is_capability_available(capability))
        except (TypeError, ValueError):
            return False
        except Exception as exc:
            logger._print_log(
                "info",
                f"Error comprobando capacidad disponible de {app_name}: {exc} "
                "[file:applications_core.py, method:is_capability_available]",
                "applications_core.py", "is_capability_available", 778,
            )
            return False

    def get_application_observed_facts(self, app_name: str) -> Dict[str, Any]:
        """Devuelve los hechos observados de una aplicacion, o dict vacio si no existe."""
        app = self.get_application(app_name)
        if not app:
            return {}
        return app.get_observed_facts()

    def get_application_inferred_data(self, app_name: str) -> Dict[str, Any]:
        """Devuelve los datos inferidos de una aplicacion, o dict vacio si no existe."""
        app = self.get_application(app_name)
        if not app:
            return {}
        return app.get_inferred_data()

    def get_application_unverified_capabilities(self, app_name: str) -> List["ApplicationCapabilityDef"]:
        """Devuelve las capacidades declaradas pero no verificadas de una aplicacion.

        Devuelve lista vacia si la aplicacion no existe o no tiene
        capacidades no verificadas.
        """
        app = self.get_application(app_name)
        if not app:
            return []
        return app.get_unverified_capabilities()


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
def _app_knowledge_to_preflight_dict(app: ApplicationKnowledge) -> Dict[str, Any]:
    """Convierte un ApplicationKnowledge a un dict compatible con ApplicationPreflight.check().

    Incluye los campos que el preflight evalúa: nombre, app_id, login_required,
    logged_in, resources_available y url. Los campos app_id, logged_in y
    resources_available se leen de metadata cuando existen; de lo contrario se
    dejan en sus valores por defecto (cadena vacía / None).
    """
    metadata = app.metadata or {}
    return {
        "name": app.name,
        "app_id": str(metadata.get("app_id", "") or ""),
        "login_required": app.login_required,
        "logged_in": metadata.get("logged_in", None),
        "resources_available": metadata.get("resources_available", None),
        "url": app.url,
    }


def open_application(app_name: str) -> str:
    """Abre una aplicación conocida y valida su disponibilidad.

    Antes de lanzar, pasa al candidato por ApplicationPreflight y las
    políticas existentes (unidad 3.8.5.1.4.7.10). Se rechazan ejecutables
    desconocidos, destinos ambiguos y rutas manipuladas.
    """
    app_manager = get_application_manager()
    app = app_manager.get_application(app_name)

    if not app:
        raise ValueError(f"Aplicación no encontrada: {app_name}")

    # 3.8.5.1.4.7.10: todo candidato que se pretenda abrir debe pasar por
    # ApplicationPreflight y las políticas existentes antes de lanzarse.
    # Se rechazan ejecutables desconocidos, destinos ambiguos y rutas manipuladas.
    preflight = get_application_preflight()
    preflight_result = preflight.check(_app_knowledge_to_preflight_dict(app))
    if not preflight_result.get("allowed", False):
        raise RuntimeError(
            f"La aplicación {app.name} no pasó el preflight: "
            f"{preflight_result.get('reason', 'sin motivo')} "
            f"(bloqueado por: {preflight_result.get('blocked_by', 'desconocido')})"
        )

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
        logger._print_log("info", f"Error abriendo aplicación: {exc} [file:applications_core.py, method:open_application, line:903]")
        raise


def _is_process_running(process_name: str) -> bool:
    """Comprueba si un proceso con el nombre dado sigue en ejecucion.

    Usa ``tasklist`` en Windows y ``pgrep`` en sistemas Unix para verificar
    la presencia del proceso por nombre de imagen/ejecutable. Devuelve ``False``
    ante cualquier error de consulta, para no bloquear el cierre por problemas
    de introspeccion del sistema.
    """
    name = os.path.basename(str(process_name or "").replace("\\", "/")).strip()
    if not name:
        return False
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout or ""
            return name.lower() in output.lower()
        unix_name = name[:-4] if name.lower().endswith(".exe") else name
        result = subprocess.run(
            ["pgrep", "-x", unix_name],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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

    # Identificar el proceso correcto a partir del conocimiento real de la
    # aplicación (ejecutable declarado), sin asumir que el nombre comercial
    # coincide con el nombre del proceso. Si no hay aplicación registrada o
    # no declara ejecutable, se conserva el comportamiento previo basado en
    # el nombre indicado.
    process_name = target
    try:
        app = get_application_manager().get_application(target)
    except Exception:
        app = None
    if app is not None and getattr(app, "executable", None):
        process_name = str(app.executable).strip()
    process_name = os.path.basename(process_name.replace("\\", "/"))
    if not process_name:
        process_name = target
    if not process_name.lower().endswith(".exe"):
        process_name = f"{process_name}.exe"

    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                check=False,
                capture_output=True,
                text=True,
            )
        elif platform.system() == "Darwin":
            unix_process_name = process_name
            if unix_process_name.lower().endswith(".exe"):
                unix_process_name = unix_process_name[:-4]
            subprocess.run(["pkill", "-x", unix_process_name.lower()], check=False)
        else:
            unix_process_name = process_name
            if unix_process_name.lower().endswith(".exe"):
                unix_process_name = unix_process_name[:-4]
            subprocess.run(["pkill", "-x", unix_process_name.lower()], check=False)

        # Verificacion de estado posterior: confirmar que el proceso ya no esta
        # en ejecucion tras enviarle la senal de cierre. Si el proceso persiste,
        # se informa que no se pudo confirmar el cierre en lugar de asumirlo.
        cerrado = not _is_process_running(process_name)
        logger._print_log("info", "Procesando solicitud", "applications_core.py", "method", 371)
        if cerrado:
            return f"Aplicación {target} cerrada exitosamente"
        return f"Aplicación {target} no pudo confirmarse cerrada"
    except Exception as exc:
        logger._print_log("info", f"Error cerrando aplicación: {str(exc)} [file:applications_core.py, method:close_application, line:556]")
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


def _executable_target_is_localizable(app: Optional[ApplicationKnowledge]) -> bool:
    """Indica si se puede localizar un ejecutable/local concreto para la app.

    Solo cuenta un destino local ejecutable (ruta absoluta v�lida a un archivo
    existente, o nombre de ejecutable resuelto en PATH mediante
    ``shutil.which``). Una URL sola hace que la app sea lan�able
    (``installed``) pero no proporciona un ejecutable local localizable, as�
    no se confunde "est� instalada" con "se sabe d�nde est� el ejecutable".
    """
    if app is None:
        return False
    executable = str(getattr(app, "executable", None) or "").strip()
    if not executable:
        return False
    if os.path.isabs(executable) or any(sep in executable for sep in ("/", "\\")):
        return os.path.isfile(executable)
    return shutil.which(executable) is not None


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
        "available": bool(app.is_available()),
        "declared_capabilities": [cap.capability.value for cap in app.capabilities],
        "metadata": dict(app.metadata),
    }


@dataclass
class ApplicationClassification:
    """Resultado de la clasificación de una aplicación en estados de descubrimiento.

    Distingue ejes independientes y no excluyentes entre sí, de modo que el
    llamador puede decidir qué hacer en cada caso sin mezclar estados:

    - ``unknown``: la aplicación no se conoce (no está registrada en
      ``ApplicationManager`` ni es resoluble como coincidencia sobre aplicaciones
      conocidas). Es una aplicación realmente desconocida.
    - ``installed``: el ejecutable está en disco (PATH o ruta absoluta) o la app
      tiene URL configurada, por lo que se puede intentar lanzar.
    - ``localizable``: se pudo determinar una ruta o ejecutable local concreto
      para la aplicación (ejecutable en PATH, ruta absoluta válida). Una app
      puede estar instalada (lançable por URL) y sin embargo no tener un
      ejecutable local localizable.
    - ``running``: un proceso con el nombre del ejecutable está activo en el
      sistema (comprobado vía tasklist/psutil).
    - ``registered``: la app está registrada en ``ApplicationManager``
      (conocimiento de aplicación, ya sea hardcodeado o cargado de memoria).
    - ``automatable``: la app pasa el preflight (no bloqueada, confidence
      disponible) y está disponible en tiempo de ejecución, por lo que JARVIS
      puede intentar automatizarla.
    """

    app_name: str
    installed: bool
    running: bool
    registered: bool
    automatable: bool
    details: Dict[str, Any]
    unknown: bool = False
    localizable: bool = False


def classify_application(app_name: str) -> ApplicationClassification:
    """Clasifica una aplicación en los cuatro estados de descubrimiento.

    Para un nombre de aplicación dado, determina si está:
    1. Instalada (ejecutable en disco o URL),
    2. En ejecución (proceso activo),
    3. Registrada en ApplicationManager (conocimiento estructurado),
    4. Disponible para automatización (preflight aprobado y disponible).

    Los cuatro ejes son independientes: una aplicación puede estar instalada
    pero no registrada, registrada pero no instalada, en ejecución sin estar
    registrada, etc.

    No lanza, instala ni modifica ninguna aplicación: es una operación de
    inspección de lectura sola.
    """
    target = str(app_name or "").strip()
    app_manager = get_application_manager()
    app = app_manager.get_application(target) if target else None

    # 1. Registrada en ApplicationManager
    registered = app is not None

    # Eje desconocida: la app no es conocida ni resoluble como coincidencia
    # sobre aplicaciones registradas (reusa el contrato de resoluci�n 3.8.2).
    resolution = app_manager.resolve_application(target)
    unknown = resolution.app is None

    # 2. Instalada (ejecutable en disco o URL, o disponible por preflight)
    installed = bool(app.is_available()) if app else False

    # Eje localizable: instalada y se determina un ejecutable/local concreto.
    localizable = installed and (app is not None) and _executable_target_is_localizable(app)

    # 3. En ejecución (proceso activo por nombre de ejecutable de la app
    # registrada). Para apps no registradas no asumimos ejecución solo por
    # coincidencia de nombre: sin conocimiento estructurado no podemos
    # confirmar que el proceso corresponde a la aplicación consultada.
    running = False
    if app is not None:
        exe = getattr(app, "executable", None)
        if exe:
            running = _is_process_running(str(exe))
        if not running and target:
            running = _is_process_running(target)

    # 4. Disponible para automatización (preflight aprobado y disponible).
    # Si el preflight falla (excepción), no se puede confirmar:
    # automatable queda False.
    automatable = False
    preflight_result = None
    if app is not None and installed:
        try:
            preflight = get_application_preflight()
            preflight_result = preflight.check(app)
            automatable = bool(
                preflight_result.allowed
                and preflight_result.confidence != "unknown"
                and installed
            )
        except Exception:
            preflight_result = None
            automatable = False

    details: Dict[str, Any] = {
        "app_name": target,
        "normalized_name": app_manager._normalize_name(target) if target else "",
        "unknown": unknown,
        "registered": registered,
        "installed": installed,
        "localizable": localizable,
        "running": running,
        "automatable": automatable,
    }
    if app is not None:
        details["executable"] = app.executable
        details["url"] = app.url
        details["type"] = app.type
        details["login_required"] = app.login_required
    if preflight_result is not None:
        details["preflight"] = preflight_result.to_dict()

    return ApplicationClassification(
        app_name=target,
        installed=installed,
        running=running,
        registered=registered,
        automatable=automatable,
        details=details,
        unknown=unknown,
        localizable=localizable,
    )


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
            # UIElement solo conserva conocimiento declarativo (name, type,
            # description, required_capability). Los campos de coordenadas
            # concretas (coordinates, screen, calibration_data) son ignorados
            # aquí: pertenecen al CoordinateManager en tiempo de ejecución.
            element_kwargs = {
                key: value
                for key, value in element_data.items()
                if key in ("name", "type", "description", "required_capability")
            }
            ui_elements.append(UIElement(**element_kwargs))
        data["ui_elements"] = ui_elements

        states = []
        for state in data.get("states", []) or []:
            if isinstance(state, str):
                try:
                    states.append(ApplicationState(state))
                except ValueError:
                    # Un estado desconocido NO se convierte en un estado valido
                    # por defecto. Se omite y se registra para evitar creencias
                    # falsas. No se fuerza ningun estado por defecto en este bucle.
                    logger._print_log(
                        "info",
                        f"Estado desconocido omitido en register_custom_application: '{state}' "
                        "[file:applications_core.py, method:register_custom_application]",
                        "applications_core.py", "register_custom_application", 1422,
                    )
            else:
                states.append(state)
        data["states"] = states

        default_state = data.get("default_state", ApplicationState.CLOSED)
        if isinstance(default_state, str):
            try:
                data["default_state"] = ApplicationState(default_state)
            except ValueError:
                # Un estado desconocido para default_state NO se convierte en
                # un estado valido por defecto. Se elimina la clave del dict para
                # que ApplicationKnowledge use su valor por defecto (CLOSED),
                # y se registra el estado desconocido.
                logger._print_log(
                    "info",
                    f"default_state desconocido omitido en register_custom_application: '{default_state}' "
                    "[file:applications_core.py, method:register_custom_application]",
                    "applications_core.py", "register_custom_application", 1426,
                )
                data.pop("default_state", None)

        app = ApplicationKnowledge(**data)
        return get_application_manager().register_application(app)
    except Exception as exc:
        logger._print_log("INFO", "Procesando solicitud", "applications_core.py", "register_custom_application", 1054)
        return False


def is_application_available(app_name: str) -> bool:
    """Comprueba disponibilidad en tiempo de ejecución de una aplicación.

    Distingue **disponible** (ejecutable instalado / app con URL) de
    **simplemente declarada** (registrada en el modelo).
    """
    try:
        return bool(get_application_manager().is_application_available(app_name))
    except Exception:
        return False


def is_capability_available(app_name: str, capability: Any) -> bool:
    """Distingue una capacidad **disponible** de una sola **declarada**.

    Una capacidad está disponible cuando está declarada en el modelo y la
    aplicación es disponible en tiempo de ejecución.
    """
    try:
        enum_capability = capability
        if isinstance(enum_capability, str):
            enum_capability = ApplicationCapability(enum_capability.strip().lower())
        return bool(
            get_application_manager().is_capability_available(app_name, enum_capability)
        )
    except (TypeError, ValueError):
        return False
    except Exception:
        return False


@register_action(
    name="verify_target_monitor",
    description="Verifica que un monitor objetivo exista antes de operar sobre el",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "monitor", "verificacion", "reusable"],
    parameters={
        "monitor_num": {
            "type": "int",
            "required": True,
            "description": "Numero de monitor a verificar (a partir de 1)",
        }
    },
    preconditions=[],
    effects=["monitor_verified"],
    cost=2.0,
    capability="verify_target_monitor",
    planner_enabled=True,
)
def verify_target_monitor(monitor_num: int) -> Dict[str, Any]:
    """
    Verifica que un monitor objetivo exista y sea valido antes de cualquier
    operacion de aplicacion que lo utilice.

    Refresca la topologia de monitores desde Windows (o fallback de config)
    y valida que el numero de monitor solicitado corresponda a un monitor
    real detectado. No mueve ni altera ninguna ventana.

    Args:
        monitor_num: Numero de monitor a verificar (a partir de 1).

    Returns:
        Dict con claves: verified (bool), monitor (dict o None),
        error (str o None).

    Raises:
        ValueError: Si monitor_num no es un entero positivo.
    """
    try:
        monitor_num = int(monitor_num)
    except (TypeError, ValueError):
        raise ValueError(f"Numero de monitor invalido: {monitor_num!r}")

    if monitor_num < 1:
        raise ValueError(f"Numero de monitor invalido: {monitor_num} (debe ser >= 1)")

    try:
        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()

        monitor = screen_manager.get_monitor(monitor_num)
    except Exception as exc:
        return {
            "verified": False,
            "monitor": None,
            "error": f"Error verificando monitor {monitor_num}: {exc}",
        }

    if monitor is None:
        return {
            "verified": False,
            "monitor": None,
            "error": f"Monitor {monitor_num} no encontrado",
        }

    return {
        "verified": True,
        "monitor": monitor.to_dict(),
        "error": None,
    }


@register_action(
    name="move_application_to_monitor",
    description="Mueve una aplicacion al monitor objetivo de forma segura",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "monitor", "movimiento", "seguro", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicacion cuya ventana debe moverse",
        },
        "monitor_num": {
            "type": "int",
            "required": True,
            "description": "Numero de monitor destino (a partir de 1)",
        },
    },
    preconditions=[],
    effects=["application_moved_to_monitor"],
    cost=8.0,
    capability="move_application_to_monitor",
    planner_enabled=True,
)
def move_application_to_monitor(app_name: str, monitor_num: int) -> Dict[str, Any]:
    """
    Mueve una aplicacion al monitor objetivo verificando el movimiento seguro.

    Flujo seguro:
    1. Valida entradas y verifica que el monitor destino exista.
    2. Identifica la ventana correcta de la aplicacion (sin mover ventanas a ciegas).
    3. Mueve la ventana usando las comprobaciones de seguridad del gestor de
       calibracion (ventana GUI valida, no elevada, posicion verificada).
    4. Verifica que la ventana quedo en el monitor destino.

    Args:
        app_name: Nombre de la aplicacion cuya ventana debe moverse.
        monitor_num: Numero de monitor destino (a partir de 1).

    Returns:
        Dict con claves: moved (bool), verified (bool), monitor (dict o None),
        window_identified (bool), error (str o None).

    Raises:
        ValueError: Si app_name esta vacio o monitor_num no es valido.
    """
    target = str(app_name or "").strip()
    if not target:
        raise ValueError("El nombre de la aplicacion no puede estar vacio")

    monitor_check = verify_target_monitor(monitor_num)
    if not monitor_check.get("verified"):
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": False,
            "error": monitor_check.get("error") or f"Monitor {monitor_num} no verificado",
        }

    try:
        monitor_num = int(monitor_num)
    except (TypeError, ValueError):
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": False,
            "error": f"Numero de monitor invalido: {monitor_num!r}",
        }

    try:
        calibration_manager = get_calibration_manager()
    except Exception as exc:
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": False,
            "error": f"Error obteniendo CalibrationManager: {exc}",
        }

    find_window = getattr(calibration_manager, "_find_existing_application_window", None)
    if not callable(find_window):
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": False,
            "error": "CalibrationManager no permite identificar ventanas de aplicacion",
        }

    try:
        window = find_window(target)
    except Exception as exc:
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": False,
            "error": f"Error identificando ventana de {target}: {exc}",
        }

    if window is None:
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": False,
            "error": f"No se encontro ventana identificable para {target}",
        }

    move_window = getattr(calibration_manager, "move_window_to_monitor", None)
    if not callable(move_window):
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": True,
            "error": "CalibrationManager no expone movimiento seguro de ventanas",
        }

    try:
        moved = bool(move_window(window, monitor_num, target))
    except Exception as exc:
        return {
            "moved": False,
            "verified": False,
            "monitor": monitor_check.get("monitor"),
            "window_identified": True,
            "error": f"Error moviendo {target} al monitor {monitor_num}: {exc}",
        }

    verified = False
    if moved:
        try:
            screen_manager = get_screen_manager()
            get_window_monitor = getattr(screen_manager, "get_monitor_for_window", None)
            if callable(get_window_monitor):
                actual_monitor = get_window_monitor(window)
                if actual_monitor is not None:
                    actual_id = getattr(actual_monitor, "monitor_id", None)
                    verified = int(actual_id) == int(monitor_num) if actual_id is not None else False
                else:
                    verified = False
            else:
                verified = True
        except Exception:
            verified = False

    return {
        "moved": moved,
        "verified": bool(moved and verified),
        "monitor": monitor_check.get("monitor"),
        "window_identified": True,
        "error": None if moved else f"No se pudo mover {target} al monitor {monitor_num}",
    }


@register_action(
    name="maximize_or_restore_application",
    description="Maximiza o restaura la ventana de una aplicacion cuando corresponda",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "ventana", "maximizar", "restaurar", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicacion cuya ventana se maximizara o restaurara",
        },
        "maximize": {
            "type": "bool",
            "required": False,
            "default": True,
            "description": "Si True, maximiza la ventana; si False, la restaura a tamano normal",
        },
    },
    preconditions=[],
    effects=["application_window_maximized", "application_window_restored"],
    cost=5.0,
    capability="maximize_or_restore_application",
    planner_enabled=True,
)
def maximize_or_restore_application(app_name: str, maximize: bool = True) -> Dict[str, Any]:
    """
    Maximiza o restaura la ventana de una aplicacion verificando el estado real.

    Flujo seguro:
    1. Valida que el nombre de la aplicacion no este vacio.
    2. Identifica la ventana de la aplicacion sin mover ventanas a ciegas.
    3. Captura el estado actual de la ventana (maximizada/restaurada/minimizada).
    4. Si se solicita maximizar y la ventana no esta maximizada, la maximiza.
    5. Si se solicita restaurar y la ventana esta maximizada, la restaura.
    6. Verifica el estado final tras la operacion.

    Args:
        app_name: Nombre de la aplicacion cuya ventana se gestionara.
        maximize: Si True se maximiza; si False se restaura a tamano normal.

    Returns:
        Dict con claves: maximized (bool), restored (bool), verified (bool),
        window_identified (bool), already_in_target_state (bool), error (str o None).

    Raises:
        ValueError: Si app_name esta vacio.
    """
    target = str(app_name or "").strip()
    if not target:
        raise ValueError("El nombre de la aplicacion no puede estar vacio")

    try:
        calibration_manager = get_calibration_manager()
    except Exception as exc:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": False,
            "already_in_target_state": False,
            "error": f"Error obteniendo CalibrationManager: {exc}",
        }

    find_window = getattr(calibration_manager, "_find_existing_application_window", None)
    if not callable(find_window):
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": False,
            "already_in_target_state": False,
            "error": "CalibrationManager no permite identificar ventanas de aplicacion",
        }

    try:
        window = find_window(target)
    except Exception as exc:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": False,
            "already_in_target_state": False,
            "error": f"Error identificando ventana de {target}: {exc}",
        }

    if window is None:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": False,
            "already_in_target_state": False,
            "error": f"No se encontro ventana identificable para {target}",
        }

    get_hwnd = getattr(calibration_manager, "_get_window_handle", None)
    if not callable(get_hwnd):
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": "CalibrationManager no permite obtener el identificador de ventana",
        }

    try:
        hwnd = get_hwnd(window)
    except Exception as exc:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": f"Error obteniendo HWND de {target}: {exc}",
        }

    if not hwnd:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": f"No se pudo obtener el HWND de la ventana de {target}",
        }

    capture_state = getattr(calibration_manager, "_capture_window_state", None)
    if not callable(capture_state):
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": "CalibrationManager no permite capturar el estado de la ventana",
        }

    try:
        snapshot = capture_state(hwnd)
    except Exception as exc:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": f"Error capturando estado de ventana de {target}: {exc}",
        }

    if snapshot is None:
        return {
            "maximized": False,
            "restored": False,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": f"No se pudo capturar el estado de la ventana de {target}",
        }

    # SW_SHOWMAXIMIZED = 3 (ventana maximizada); cualquier otro valor (1=normal) no lo esta
    is_maximized = int(snapshot.show_cmd) == 3
    want_maximized = bool(maximize)

    already_in_target_state = (is_maximized == want_maximized)
    if already_in_target_state:
        return {
            "maximized": is_maximized,
            "restored": not is_maximized,
            "verified": True,
            "window_identified": True,
            "already_in_target_state": True,
            "error": None,
        }

    # Ejecutar la operacion solicitada
    if want_maximized:
        maximize_window = getattr(calibration_manager, "_maximize_window", None)
        if not callable(maximize_window):
            return {
                "maximized": False,
                "restored": False,
                "verified": False,
                "window_identified": True,
                "already_in_target_state": False,
                "error": "CalibrationManager no permite maximizar ventanas",
            }
        try:
            success = bool(maximize_window(hwnd))
        except Exception as exc:
            return {
                "maximized": False,
                "restored": False,
                "verified": False,
                "window_identified": True,
                "already_in_target_state": False,
                "error": f"Error maximizando {target}: {exc}",
            }
        if not success:
            return {
                "maximized": False,
                "restored": False,
                "verified": False,
                "window_identified": True,
                "already_in_target_state": False,
                "error": f"No se pudo maximizar la ventana de {target}",
            }
    else:
        # Restaurar: usar SW_RESTORE para volver al tamano normal desde maximizada
        try:
            success = bool(
                USER32.ShowWindow(wintypes.HWND(hwnd), int(SW_RESTORE))
            )
        except Exception as exc:
            return {
                "maximized": False,
                "restored": False,
                "verified": False,
                "window_identified": True,
                "already_in_target_state": False,
                "error": f"Error restaurando {target}: {exc}",
            }
        if not success:
            return {
                "maximized": False,
                "restored": False,
                "verified": False,
                "window_identified": True,
                "already_in_target_state": False,
                "error": f"No se pudo restaurar la ventana de {target}",
            }

    # Pequeña pausa para que el SO aplique el cambio de estado
    time.sleep(0.5)

    # Verificar estado final
    try:
        final_snapshot = capture_state(hwnd)
    except Exception as exc:
        return {
            "maximized": want_maximized,
            "restored": not want_maximized,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": f"Operacion ejecutada pero no se pudo verificar estado final: {exc}",
        }

    if final_snapshot is None:
        return {
            "maximized": want_maximized,
            "restored": not want_maximized,
            "verified": False,
            "window_identified": True,
            "already_in_target_state": False,
            "error": "Operacion ejecutada pero no se pudo capturar el estado final",
        }

    final_is_maximized = int(final_snapshot.show_cmd) == 3
    verified = (final_is_maximized == want_maximized)

    return {
        "maximized": bool(want_maximized and final_is_maximized),
        "restored": bool(not want_maximized and not final_is_maximized),
        "verified": verified,
        "window_identified": True,
        "already_in_target_state": False,
        "error": None if verified else f"El estado final no coincide con el solicitado para {target}",
    }
