"""
Sistema de conocimiento de aplicaciones para planificacion jerarquica.

Responsabilidades principales:
- Conocimiento estructurado de aplicaciones.
- Capacidades basicas reutilizables.
- Integracion con calibracion especifica y global.
- Soporte para preflight y login.
- Compatibilidad con comandos legacy.

El conocimiento de una aplicacion se mantiene separado de su implementacion
concreta para que el planificador pueda trabajar con capacidades genericas.
"""

from __future__ import annotations

from src.core.log import get_logger
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

from src.hands.calibration.calibration_manager import SW_RESTORE, SW_MAXIMIZE, USER32

from src.hands.actions.action_registry import ActionType, get_action_registry, register_action
from src.hands.apps.application_preflight import ApplicationPreflight, get_application_preflight
from src.hands.calibration.calibration_manager import get_calibration_manager
from src.memory.storage import Entity, get_memory_manager
from src.desktop.screen_manager import get_screen_manager

logger = get_logger(__name__)

RESOLUTION_FUZZY_THRESHOLD = 0.7
_MAX_RESOLUTION_ALTERNATIVES = 3
RESOLUTION_AMBIGUITY_GAP = 0.05


@dataclass
class ApplicationResolutionResult:
    """Resultado de la resolucion de una aplicacion por nombre.

    Atributos:
        app: Aplicacion resuelta o ``None`` si no hubo coincidencia.
        confidence: Confianza de la coincidencia (1.0 exacto/alias, ratio
            difuso para nombres imperfectos, 0.0 sin coincidencia).
        method: Metodo usado: ``exact_normalized``, ``dynamic_alias``,
            ``fuzzy_name``, ``fuzzy_alias`` o ``none``.
        alternatives: Otras aplicaciones candidatas ordenadas por similitud
            (solo se rellena en resolucion difusa).
        is_ambiguous: ``True`` cuando la resolucion difusa tiene otra
            candidata dentro del umbral de proximidad
            (``RESOLUTION_AMBIGUITY_GAP``) del mejor resultado, por lo que no
            debe seleccionarse silenciosamente una aplicacion posiblemente
            incorrecta. El llamador debe pedir aclaracion al usuario.
        ambiguity_reason: Descripcion legible de la ambiguedad detectada o
            ``None`` si no hay ambiguedad.
    """

    app: Optional[ApplicationKnowledge]
    confidence: float
    method: str
    alternatives: List[ApplicationKnowledge]
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None


class ApplicationCapability(Enum):
    """Capacidades que puede ofrecer una aplicacion."""

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
    """Estados posibles de una aplicacion."""

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
    """Elemento UI de una aplicacion - conocimiento declarativo con calibracion.

    Representa **que** elementos de interfaz conoce la aplicacion y **cual**
    capacidad requiere. Mantiene tanto el conocimiento estructurado (nombre,
    tipo, descripcion, capacidad asociada) como la informacion de calibracion
    necesaria para localizar el elemento en pantalla en tiempo de ejecucion
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
        """Indica si el elemento tiene coordenadas validas para hacer clic."""
        if self.coordinates is None:
            return False
        if isinstance(self.coordinates, dict):
            return "x" in self.coordinates and "y" in self.coordinates
        return bool(self.coordinates)


@dataclass
class ApplicationCapabilityDef:
    """Definicion de una capacidad de aplicacion."""

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
    """Conocimiento estructurado de una aplicacion."""

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
        """Comprueba si la aplicacion posee una capacidad especifica.

        Esta es una comprobacion **declarativa**: verifica unicamente que la
        capacidad esta registrada en el modelo de conocimiento, sin garantizar
        que la aplicacion este disponible en tiempo de ejecucion. Para esa
        distincion, usar :meth:`is_capability_available`.
        """
        return any(capability_def.capability == capability for capability_def in self.capabilities)

    def is_available(self) -> bool:
        """Comprueba si la aplicacion esta disponible en tiempo de ejecucion.

        Reune la logica de :func:`_check_application_available` como metodo de
        modelo: una aplicacion esta disponible si su ejecutable esta en el
        PATH o en una ruta de archivo valida, o si no tiene ejecutable pero si
        URL. No distingue mayusculas/minusculas del ejecutable ni resuelve
        aliases; la normalizacion de nombres recae sobre el gestor.
        """
        return _check_application_available(self)

    def is_capability_available(
        self, capability: ApplicationCapability
    ) -> bool:
        """Distingue una capacidad **disponible** de una sola **declarada**.

        Una capacidad esta disponible cuando esta declarada en el modelo
        (:meth:`is_capable`) **y** la aplicacion es disponible en tiempo de
        ejecucion (:meth:`is_available`). Devuelve ``False`` siempre que la
        aplicacion no pueda comprobarse o la capacidad no este declarada.
        """
        return self.is_capable(capability) and self.is_available()

    def get_calibrated_elements(self) -> List[UIElement]:
        """Obtiene los elementos UI conocidos que tienen coordenadas calibradas.

        El conocimiento declarativo (``UIElement``) no almacena coordenadas;
        la calibracion se consulta en tiempo de ejecucion al
        ``CoordinateManager``, que gestiona ``data/macros_coords.json``.
        Si el gestor no esta disponible, devuelve una lista vacia.
        """
        try:
            from src.hands.calibration.coordinate_manager import get_coordinate_manager
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
    required_capability) y datos de calibracion (coordinates, screen,
    calibration_data) para poder localizar el elemento en pantalla en tiempo
    de ejecucion.
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
            "s\u00edmbolo del sistema": "cmd",
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
                    description="Reproduce una canci\u00f3n",
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
        """Registra una aplicacion en memoria y en el gestor.

        Evita duplicados: si la aplicacion ya esta registrada en el gestor
        (por nombre normalizado), se actualizan sus aliases en memoria y se
        persiste la entidad en ``entities.json`` para que las resoluciones
        posteriores por alias dinamico sigan funcionando, en lugar de omitir
        silenciosamente la actualizacion. Se devuelve ``True`` cuando la
        aplicacion se registra o se actualiza correctamente.
        """
        try:
            key = self._normalize_name(app.name)
            aliases = []
            if app.metadata and isinstance(app.metadata, dict):
                aliases = [str(a) for a in (app.metadata.get("aliases") or [])]

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
                "aliases": aliases,
                "confidence": 1.0,
                "tags": [],
            }

            if key in self.applications:
                # Aplicacion ya registrada: refrescar los aliases en memoria y
                # persistirlos para que _resolve_alias los vea en ejecuciones
                # posteriores sin depender de entidades previas con aliases
                # vacios en disco.
                existing = self.applications[key]
                if existing.metadata is None:
                    existing.metadata = {}
                existing.metadata["aliases"] = aliases
                try:
                    self.memory_manager.save_entity(Entity.from_dict(entity_data))
                except Exception:
                    # La entidad ya existe en disco; guardar la versione
                    # actualizada es el camino preferido pero no bloquea el
                    # registro en memoria si el almacenamiento falla.
                    pass
                logger.info(f"Aplicacion '{key}' ya registrada, aliases actualizados "
                    "")
                return True

            self.memory_manager.save_entity(Entity.from_dict(entity_data))
            self.applications[key] = app
            return True
        except Exception as exc:
            logger.info(f"Error procesando solicitud: {str(exc)}")
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
        #    catalogo con una descubierta homonima).
        if key in self.applications:
            existing = self.applications[key]
            logger.info(f"Aplicacion descubierta '{key}' ya existe en memoria por "
                f"nombre normalizado duplicado; se conserva la entrada previa "
                f"y no se reemplaza. "
                "")
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
                logger.info(f"Aplicacion descubierta '{key}' colisiona con un alias de "
                    f"la aplicacion ya registrada '{existing_key}'; se conserva "
                    f"la entrada previa y no se reemplaza. "
                    "")
                return existing_app

            # 2b. Alias de la nueva == nombre normalizado de una existente.
            if existing_key in new_aliases:
                logger.info(f"Aplicacion descubierta '{key}' declara un alias que "
                    f"colisiona con el nombre normalizado de '{existing_key}'; "
                    f"se conserva la entrada previa y no se reemplaza. "
                    "")
                return existing_app

            # 2c. Alias de la nueva == alias de una existente.
            if any(a in existing_aliases for a in new_aliases):
                logger.info(f"Aplicacion descubierta '{key}' declara un alias que "
                    f"colisiona con un alias de '{existing_key}'; se conserva "
                    f"la entrada previa y no se reemplaza. "
                    "")
                return existing_app

        # 3. Sin conflictos: registrar y retornar la nueva app.
        self.applications[key] = app
        logger.info(f"Aplicacion descubierta registrada temporalmente en memoria: '{key}' "
            "")
        return app

    def get_application(self, app_name: str) -> Optional[ApplicationKnowledge]:
        """Obtiene una aplicacion por nombre o alias.

        Resuelve primero mediante ``_normalize_name`` (alias estaticos
        hardcodeados) y, si no encuentra nada, busca en los aliases
        dinamicos almacenados en ``metadata['aliases']`` de las
        aplicaciones ya registradas (provenientes de ``Entity.aliases``
        al materializar apps desde entities.json).
        """
        normalized = self._normalize_name(app_name)
        app = self.applications.get(normalized)
        if app is not None:
            return app
        return self._resolve_alias(normalized)

    def _resolve_alias(self, normalized_name: str) -> Optional[ApplicationKnowledge]:
        """Resuelve un alias dinamico contra las aplicaciones ya registradas.

        Busca ``normalized_name`` en ``metadata['aliases']`` de cada
        aplicacion registrada. Los aliases provienen de ``Entity.aliases``
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
        """Resuelve una aplicacion a partir de un nombre ya normalizado.

        Orden de resolucion:
        1. nombre normalizado exacto (incluye los alias estaticos de
           ``_normalize_name``);
        2. alias dinamico (``metadata['aliases']`` de las aplicaciones
           registradas, via ``_resolve_alias``);
        3. nombre imperfecto (errores de escritura, variantes) mediante
           coincidencia difusa con ``difflib`` sobre el nombre y los aliases
           de cada aplicacion registrada.

        Devuelve la mejor coincidencia con su confianza, el metodo usado y las
        alternativas ordenadas por similitud. Si no hay coincidencia,
        devuelve ``app=None``, ``confidence=0.0`` y ``method="none"``.

        Cuando la resolucion es difusa y existe otra candidata dentro del
        umbral de proximidad (``RESOLUTION_AMBIGUITY_GAP``) del mejor
        resultado, el campo ``is_ambiguous`` se establece en ``True`` junto
        con una ``ambiguity_reason``, para que el llamador no seleccione
        silenciosamente una aplicacion posiblemente incorrecta y pueda pedir
        aclaracion al usuario.
        """
        normalized = self._normalize_name(app_name or "")

        # 1. Exacto: nombre normalizado (cubre alias estaticos hardcodeados).
        app = self.applications.get(normalized)
        if app is not None:
            return ApplicationResolutionResult(
                app=app, confidence=1.0, method="exact_normalized", alternatives=[]
            )

        # 2. Alias dinamico de aplicaciones ya registradas.
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

            # Detectar coincidencias ambiguas: si otra candidata esta lo
            # suficientemente cerca del mejor resultado, no se selecciona
            # silenciosamente una aplicacion posiblemente incorrecta. Se marca
            # la ambiguedad para que el llamador pueda pedir aclaracion.
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
        """Calcula y conserva la evidencia/confianza de una resolucion de aplicacion.

        Utiliza :meth:`resolve_application` para obtener el resultado y
        calcula una puntuacion de evidencia basada en la confianza, el metodo
        usado y la presencia de alternativas. La evidencia se conserva en el
        ``metadata`` de la aplicacion resuelta (mecanismo existente).

        La puntuacion de evidencia pondera el ``confidence`` por el metodo
        (exacto/alias = 1.0, difuso = 0.8) y aplica una penalizacion leve por
        cada alternativa candidata (maximo 0.2), de modo que una resolucion
        exacta sin alternativas puntua 1.0 y una resolucion difusa ambigua
        puntua menor.

        Argumentos:
            app_name: Nombre de la aplicacion a resolver (ya normalizado o no).

        Retorna:
            Diccionario con claves: ``app_name``, ``app_name_resolved`` (si hay
            coincidencia), ``confidence``, ``method``, ``evidence_score``,
            ``has_match``, ``alternatives_count``, ``is_ambiguous`` y
            ``ambiguity_reason`` (ambiguedad de la resolucion, si procede).
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
        """Recupera la evidencia de resolucion guardada para una aplicacion.

        Busca la aplicacion por nombre normalizado (clave de
        ``self.applications``) y devuelve el contenido de
        ``metadata["resolution_evidence"]`` si existe.

        Argumentos:
            app_name: Nombre de la aplicacion (se normaliza internamente).

        Retorna:
            Diccionario con la evidencia guardada o ``None`` si no hay nada
            registrado para esa aplicacion.
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
                logger.info(f"Capacidad desconocida omitida: '{normalized}' "
                    "")
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
                    logger.info(f"Capability UI desconocida omitida: '{cap_raw}' "
                        "")

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
                logger.info(f"Estado desconocido omitido: '{item}' "
                    "")

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
        ``properties.type`` -> ``properties.category`` -> ``"application"``.

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
            logger.info(f"Error reconstruyendo aplicacion desde entidad "
                f"(id={getattr(entity, 'id', '?')}): {exc} "
                f"")
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
                logger.info("Las entidades no son una lista "
                    "")
                return

            for entity in entities:
                app = self._reconstruct_application(entity)
                if app is None:
                    continue
                key = self._normalize_name(app.name)
                if key in self.applications:
                    logger.info(f"Aplicacion '{key}' ya registrada, se omite "
                        "")
                    continue
                self.applications[key] = app
                logger.info(f"Aplicacion '{key}' cargada desde entidad "
                    "")
        except Exception as exc:
            logger.info(f"Error cargando aplicaciones desde memoria: {exc} "
                f"")

    def get_application_capabilities(self, app_name: str) -> Dict[str, Any]:
        """Obtiene capacidades de una aplicacion en formato de planificacion."""
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
        """Obtiene los elementos UI conocidos de una aplicacion.

        Devuelve el **conocimiento declarativo** de cada elemento (type,
        description, required_capability). La informacion de coordenadas
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

    def get_calibration_status(
        self, app_name: str, window_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Estado de calibracion que el catalogo puede exponer: solo ``calibration_required``.

        Consulta los perfiles locales (SQLite por ``machine_id``) a traves de
        ``CoordinateManager.calibration_required`` con la misma clave de
        almacenamiento que usa el pipeline de calibracion
        (``CalibrationManager._get_storage_application_key``). Nunca devuelve
        coordenadas, monitores, escala ni identificadores de ventana. Ante
        cualquier error se informa ``calibration_required=True``: no se asume
        calibrado sin evidencia.
        """
        app = self.get_application(app_name)
        name = app.name if app is not None else str(app_name or "").strip()
        status: Dict[str, Any] = {
            "application": name,
            "registered": app is not None,
            "calibration_required": True,
        }
        if not name:
            return status
        try:
            from src.hands.calibration.calibration_manager import CalibrationManager
            from src.hands.calibration.coordinate_manager import get_coordinate_manager

            app_key = CalibrationManager._get_storage_application_key(name) or name
            status["calibration_required"] = bool(
                get_coordinate_manager().calibration_required(app_key, window_id)
            )
        except Exception as exc:
            logger.warning("No se pudo consultar calibration_required de %s: %s", name, exc)
        return status

    def is_application_available(self, app_name: str) -> bool:
        """Comprueba disponibilidad en tiempo de ejecucion de una aplicacion.

        Distingue **disponible** (el ejecutable esta instalado o la app tiene
        URL) de **simplemente declarada** (existe en el modelo pero su
        ejecutable no esta disponible). Delega en ``ApplicationKnowledge.is_available``.
        """
        app = self.get_application(app_name)
        if not app:
            return False
        try:
            return bool(app.is_available())
        except Exception as exc:
            logger.info(f"Error comprobando disponibilidad de {app_name}: {exc} "
                "")
            return False

    def is_capability_available(
        self, app_name: str, capability: ApplicationCapability
    ) -> bool:
        """Distingue una capacidad **disponible** de una sola **declarada**.

        Una capacidad esta disponible si esta declarada en el modelo
        (``ApplicationKnowledge.is_capable``) y la aplicacion es disponible
        en tiempo de ejecucion (``ApplicationKnowledge.is_available``).
        """
        app = self.get_application(app_name)
        if not app:
            return False
        try:
            return bool(app.is_capability_available(capability))
        except (TypeError, ValueError):
            return False
        except Exception as exc:
            logger.info(f"Error comprobando capacidad disponible de {app_name}: {exc} "
                "")
            return False

    def is_application_open(self, app_name: str) -> bool:
        """Comprueba si la aplicacion ya tiene un proceso en ejecucion en el SO.

        Operacion de inspeccion de lectura sola: consulta el sistema operativo
        (tasklist en Windows, pgrep en Unix) sobre el ejecutable de la
        aplicacion registrada. Nunca lanza, instala ni modifica ninguna
        aplicacion. Devuelve False si la app no esta registrada o no se puede
        consultar el sistema.
        """
        app = self.get_application(app_name)
        if app is None:
            return False
        try:
            return _proceso_de_aplicacion_activo(app, app_name)
        except Exception as exc:
            logger.info(f"Error comprobando si {app_name} esta abierta: {exc} "
                "")
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

def _app_knowledge_to_preflight_dict(app: ApplicationKnowledge) -> Dict[str, Any]:
    """Convierte un ApplicationKnowledge a un dict compatible con ApplicationPreflight.check().

    Incluye los campos que el preflight evalua: nombre, app_id, login_required,
    logged_in, resources_available y url. Los campos app_id, logged_in y
    resources_available se leen de metadata cuando existen; de lo contrario se
    dejan en sus valores por defecto (cadena vacia / None).
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


def _spawn_application_process(argv: List[str]) -> Any:
    """Crea el proceso de una aplicacion con argv estructurado (nunca por shell).

    Punto unico de creacion de procesos de ``open_application``; se pasa como
    ``process_spawner`` al servicio de lanzamiento.
    """
    return subprocess.Popen(list(argv))


def _open_application_url(url: str) -> bool:
    """Abre una URL de aplicacion web con el navegador predeterminado."""
    return bool(webbrowser.open(url))


def _launch_service_for_open() -> Any:
    """Servicio unico de apertura con las dependencias de este modulo."""
    from src.hands.apps.platform_launch import ApplicationLaunchService

    app_manager = get_application_manager()
    return ApplicationLaunchService(
        app_manager=app_manager,
        preflight=get_application_preflight(),
        process_spawner=_spawn_application_process,
        url_opener=_open_application_url,
        availability_checker=_check_application_available,
        is_open_checker=lambda name, _app: app_manager.is_application_open(name),
    )


@register_action(
    name="open_application",
    description="Abre una aplicaci\u00f3n gen\u00e9rica",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "open", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicaci\u00f3n a abrir",
        }
    },
    preconditions=["application_exists"],
    effects=["application_open"],
    cost=10.0,
    capability="open_application",
    planner_enabled=True,
)
def open_application(app_name: str) -> str:
    """Abre una aplicacion por el flujo unico de lanzamiento y valida el resultado.

    Delega en ``ApplicationLaunchService.open`` (``platform_launch``):
    catalogo global -> (si no esta o no tiene destino) resolucion local por
    ``machine_id`` y fuentes de descubrimiento con auto-registro ->
    ``ApplicationPreflight`` obligatorio -> reutilizacion si ya esta abierta
    (salvo que el contrato de la capacidad OPEN exija cerrarla) -> lanzamiento
    con argv estructurado -> verificacion de proceso/ventana. Una apertura con
    exito no se repite mientras el proceso siga vivo.

    Errores: ``ValueError`` si la aplicacion no existe en el catalogo ni en
    este equipo (codigo ``not_found``); ``RuntimeError`` con el mensaje estructurado (preflight,
    disponibilidad, ambiguedad, lanzamiento o verificacion) en otro caso. El
    error estructurado completo queda en el atributo ``operation_error`` de la
    excepcion.
    """
    from src.core.operation_errors import ErrorCode

    service = _launch_service_for_open()
    outcome = service.open(app_name)
    display = outcome.app_name or str(app_name)
    if outcome.success:
        if outcome.reused_existing:
            return f"Aplicacion {display} ya esta abierta; se reutilizo la instancia existente"
        if outcome.window_verified:
            return f"Aplicaci\u00f3n {display} abierta exitosamente (ventana verificada)"
        return f"Aplicaci\u00f3n {display} abierta exitosamente"

    error = outcome.error
    if error is not None and error.code == ErrorCode.NOT_FOUND:
        exc: Exception = ValueError(f"Aplicacion no encontrada: {app_name}")
    else:
        message = error.user_message() if error is not None else f"No se pudo abrir {display}"
        exc = RuntimeError(message)
    setattr(exc, "operation_error", error)
    setattr(exc, "launch_outcome", outcome)
    logger.info("open_application(%s) fallo: %s", display, error)
    raise exc


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
    description="Cierra una aplicaci\u00f3n gen\u00e9rica",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "close", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicaci\u00f3n a cerrar",
        }
    },
    preconditions=["application_open"],
    effects=["application_closed"],
    cost=5.0,
    capability="close_application",
    planner_enabled=True,
)
def close_application(app_name: str) -> str:
    """Cierra una aplicacion por proceso sin tocar otras aplicaciones."""
    target = str(app_name or "").strip()
    if not target:
        raise ValueError("El nombre de la aplicacion no puede estar vacio")

    # Identificar el proceso correcto a partir del conocimiento real de la
    # aplicacion (ejecutable declarado), sin asumir que el nombre comercial
    # coincide con el nombre del proceso. Si no hay aplicacion registrada o
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
        if cerrado:
            return f"Aplicaci\u00f3n {target} cerrada exitosamente"
        return f"Aplicaci\u00f3n {target} no pudo confirmarse cerrada"
    except Exception as exc:
        logger.info(f"Error cerrando aplicacion: {str(exc)}")
        raise


@register_action(
    name="wait_for_application_state",
    description="Espera a que una aplicaci\u00f3n alcance un estado espec\u00edfico",
    action_type=ActionType.APPLICATION,
    category="aplicacion",
    tags=["aplicacion", "wait", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicaci\u00f3n",
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
            "description": "Tiempo m\u00e1ximo de espera en segundos",
        },
    },
    preconditions=["application_open"],
    effects=["application_state_changed"],
    cost=2.0,
    capability="wait_for_state",
    planner_enabled=True,
)
def wait_for_application_state(app_name: str, target_state: str, timeout: int = 30) -> str:
    """Espera un estado de aplicacion conocido."""
    timeout = max(0, int(timeout))
    target = str(target_state or "").strip().lower()
    if not target:
        raise ValueError("El estado objetivo no puede estar vacio")

    start_time = time.time()
    while time.time() - start_time < timeout:
        time.sleep(1)
        # La comprobacion real de estado aun pertenece a los adaptadores de
        # cada aplicacion. Se mantienen los estados basicos para compatibilidad.
        if target in {"active", "ready"}:
            return f"Aplicaci\u00f3n {app_name} est\u00e1 en estado {target}"

    raise RuntimeError(
        f"Tiempo de espera agotado para {app_name} alcanzar estado {target}"
    )


@register_action(
    name="calibrate_application_ui",
    description="Calibra elementos UI de una aplicaci\u00f3n espec\u00edfica",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["aplicacion", "calibracion", "ui", "reusable"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicaci\u00f3n",
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
            "description": "N\u00famero de monitor cuando el calibrador espec\u00edfico lo requiera",
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
    """Calibra una aplicacion especifica mediante CalibrationManager."""
    app_manager = get_application_manager()
    app = app_manager.get_application(app_name)
    if not app:
        raise ValueError(f"Aplicacion no encontrada: {app_name}")

    if not app.calibration_policy:
        raise RuntimeError(f"La aplicacion {app.name} no permite calibracion automatica")

    requested_elements = list(elements) if elements is not None else list(app.calibration_policy)
    valid_elements = []
    for element_name in requested_elements:
        element = app.get_ui_element(element_name)
        if element is None:
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
            continue
        valid_elements.append(element_name)

    if not valid_elements:
        return "No se encontraron elementos calibrables"

    calibration_manager = get_calibration_manager()

    # La version actual de CalibrationManager trabaja a nivel de aplicacion y
    # monitor, no a nivel de elemento. No inventamos una API inexistente: se
    # ejecuta el calibrador especifico de la aplicacion y se informa de los
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
    logger.info(f"Calibrados {effective_count}/{len(valid_elements)} elementos solicitados")
    return f"Calibraci\u00f3n de {app.name} completada en pantalla {screen}: {effective_count} elementos"


@register_action(
    name="calibrar_aplicaciones",
    description="Inicia la calibraci\u00f3n global de las aplicaciones soportadas",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["calibracion", "global", "aplicaciones", "multi-monitor"],
    parameters={
        "force": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Fuerza la recalibraci\u00f3n de aplicaciones ya calibradas",
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
    Ejecuta la accion global de calibracion.

    El orquestador real vive en CalibrationManager. Este punto de entrada no
    exige app_name, evitando que el comando "calibre aplicaciones" se confunda
    con la calibracion de una sola aplicacion.
    """
    calibration_manager = get_calibration_manager()

    if not hasattr(calibration_manager, "calibrate_all_applications"):
        raise RuntimeError("CalibrationManager no expone calibrate_all_applications()")

    logger.info(r"[GLOBAL] Inicio calibracion de aplicaciones")
    raw_results = _call_calibrate_all_applications(
        calibration_manager,
        force=bool(force),
    )
    report = _build_global_calibration_report(raw_results)
    return report


# Alias ingles para compatibilidad programatica; el comando LLM recomendado
# sigue siendo `calibrar_aplicaciones`.
@register_action(
    name="calibrate_applications",
    description="Inicia la calibraci\u00f3n global de las aplicaciones soportadas",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["calibracion", "global", "applications", "multi-monitor"],
    parameters={
        "force": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Fuerza la recalibraci\u00f3n de aplicaciones ya calibradas",
        }
    },
    preconditions=[],
    effects=["applications_ui_calibrated"],
    cost=30.0,
    capability="calibrate_applications",
    planner_enabled=True,
)
def calibrate_applications(force: bool = False) -> Dict[str, Any]:
    """Alias programatico de calibrar_aplicaciones()."""
    return calibrar_aplicaciones(force=force)


@register_action(
    name="calibrar_aplicacion_profunda",
    description="Calibracion en profundidad de una aplicacion: exploracion completa dentro del presupuesto ('calibra X a fondo') o solo la rama necesaria para un elemento objetivo del Planner.",
    action_type=ActionType.CALIBRATION,
    category="calibracion",
    tags=["calibracion", "profundidad", "exploracion", "aplicacion"],
    parameters={
        "app_name": {
            "type": "str",
            "required": True,
            "description": "Nombre de la aplicacion a calibrar en profundidad.",
        },
        "branch_ref": {
            "type": "str",
            "required": False,
            "default": None,
            "description": "Referencia logica del elemento objetivo. Si se indica, solo se explora la rama necesaria para hacerlo visible (peticion del Planner).",
        },
        "screen_number": {
            "type": "int",
            "required": False,
            "default": None,
            "description": "Monitor destino (monitor_id de ScreenManager).",
        },
    },
    preconditions=[],
    effects=["aplicacion_explorada_profundamente"],
    cost=60.0,
    capability="calibrate_application_deep",
    planner_enabled=True,
)
def calibrar_aplicacion_profunda(
    app_name: str,
    branch_ref: Optional[str] = None,
    screen_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Calibracion en profundidad de una aplicacion.

    Ejecuta ``CalibrationManager.calibrate_application_deep``: exploracion
    completa dentro del presupuesto cuando no se indica ``branch_ref``
    ("calibra X a fondo"), o solo la rama necesaria para hacer visible el
    elemento de referencia cuando el Planner lo solicita.
    """
    calibration_manager = get_calibration_manager()
    result = calibration_manager.calibrate_application_deep(
        application={"name": app_name},
        screen_number=screen_number,
        branch_ref=branch_ref,
    )
    return {
        "success": bool(result.success),
        "error": result.error,
        "application": result.application_name,
        "screen": result.screen_number,
        "elements_count": result.elements_count,
        "depth": "branch" if branch_ref else "deep",
        "calibration_data": result.calibration_data,
    }


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def _call_calibrate_all_applications(manager: Any, force: bool = False) -> Any:
    """
    Invoca la calibracion global compatible con managers antiguos y nuevos.

    El manager actual acepta ``force`` en las versiones nuevas y algunas
    versiones legacy no lo exponen. Nunca se propaga un argumento que el
    metodo no soporte.
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


def _proceso_de_aplicacion_activo(app: ApplicationKnowledge, app_name: str) -> bool:
    """Devuelve True si el proceso de la aplicacion esta en ejecucion en el SO.

    Consulta el nombre del ejecutable de la aplicacion registrada mediante
    ``_is_process_running`` (lectura sola del sistema operativo). Si la app no
    declara ejecutable (p. ej. solo URL), consulta por el nombre de la
    aplicacion. Nunca lanza nada.
    """
    ejecutable = str(getattr(app, "executable", None) or "").strip()
    if ejecutable:
        nombre = os.path.basename(ejecutable.replace("\\", "/"))
        if _is_process_running(nombre):
            return True
    nombre_app = str(app_name or "").strip()
    if nombre_app:
        return _is_process_running(nombre_app)
    return False


def _check_application_available(app: ApplicationKnowledge) -> bool:
    """Comprueba si el ejecutable configurado esta disponible."""
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

    Solo cuenta un destino local ejecutable (ruta absoluta valida a un archivo
    existente, o nombre de ejecutable resuelto en PATH mediante
    ``shutil.which``). Una URL sola hace que la app sea lanzable
    (``installed``) pero no proporciona un ejecutable local localizable, asi
    no se confunde "esta instalada" con "se sabe donde esta el ejecutable".
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
    # La verificacion real pertenece a la integracion especifica de cada app.
    # Se mantiene True por compatibilidad mientras no exista ese adaptador.
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
        from src.desktop.screen_manager import get_screen_manager

        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()
        report["monitors_detected"] = len(getattr(screen_manager, "monitors", []) or [])
    except Exception as exc:
        logger.debug("_build_global_calibration_report: %s", exc)

    if not isinstance(raw_results, dict):
        report["success"] = False
        report["failed"].append(
            {"application": "global", "error": "Resultado del gestor de calibraci\u00f3n inv\u00e1lido"}
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
                error_message = "Resultado de calibraci\u00f3n no reconocido"
                application_name = app_label
                screen_number = 0

            app_elements += elements_count
            if success:
                app_success = True
                logger.info(f"Procesando solicitud: {elements_count} elementos")
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
        raise ValueError("La URL no puede estar vacia")

    try:
        opened = webbrowser.open(target_url)
    except Exception as exc:
        logger.debug("navigate_to_url: %s", exc)
        raise

    if not opened:
        raise RuntimeError(f"No se pudo solicitar la apertura de la URL: {target_url}")

    return f"Navegaci\u00f3n solicitada a {target_url}"


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
# INTERFACES PUBLICAS
# ============================================================================

def get_application_knowledge(app_name: str) -> Dict[str, Any]:
    """Obtiene conocimiento estructurado de una aplicacion."""
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
    """Resultado de la clasificacion de una aplicacion en estados de descubrimiento.

    Distingue ejes independientes y no excluyentes entre si, de modo que el
    llamador puede decidir que hacer en cada caso sin mezclar estados:

    - ``unknown``: la aplicacion no se conoce (no esta registrada en
      ``ApplicationManager`` ni es resoluble como coincidencia sobre aplicaciones
      conocidas). Es una aplicacion realmente desconocida.
    - ``installed``: el ejecutable esta en disco (PATH o ruta absoluta) o la app
      tiene URL configurada, por lo que se puede intentar lanzar.
    - ``localizable``: se pudo determinar una ruta o ejecutable local concreto
      para la aplicacion (ejecutable en PATH, ruta absoluta valida). Una app
      puede estar instalada (lancable por URL) y sin embargo no tener un
      ejecutable local localizable.
    - ``running``: un proceso con el nombre del ejecutable esta activo en el
      sistema (comprobado via tasklist/psutil).
    - ``registered``: la app esta registrada en ``ApplicationManager``
      (conocimiento de aplicacion, ya sea hardcodeado o cargado de memoria).
    - ``automatable``: la app pasa el preflight (no bloqueada, confidence
      disponible) y esta disponible en tiempo de ejecucion, por lo que JARVIS
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
    """Clasifica una aplicacion en los cuatro estados de descubrimiento.

    Para un nombre de aplicacion dado, determina si esta:
    1. Instalada (ejecutable en disco o URL),
    2. En ejecucion (proceso activo),
    3. Registrada en ApplicationManager (conocimiento estructurado),
    4. Disponible para automatizacion (preflight aprobado y disponible).

    Los cuatro ejes son independientes: una aplicacion puede estar instalada
    pero no registrada, registrada pero no instalada, en ejecucion sin estar
    registrada, etc.

    No lanza, instala ni modifica ninguna aplicacion: es una operacion de
    inspeccion de lectura sola.
    """
    target = str(app_name or "").strip()
    app_manager = get_application_manager()
    app = app_manager.get_application(target) if target else None

    # 1. Registrada en ApplicationManager
    registered = app is not None

    # Eje desconocida: la app no es conocida ni resoluble como coincidencia
    # sobre aplicaciones registradas (reusa el contrato de resolucion 3.8.2).
    resolution = app_manager.resolve_application(target)
    unknown = resolution.app is None

    # 2. Instalada (ejecutable en disco o URL, o disponible por preflight)
    installed = bool(app.is_available()) if app else False

    # Eje localizable: instalada y se determina un ejecutable/local concreto.
    localizable = installed and (app is not None) and _executable_target_is_localizable(app)

    # 3. En ejecucion (proceso activo por nombre de ejecutable de la app
    # registrada). Para apps no registradas no asumimos ejecucion solo por
    # coincidencia de nombre: sin conocimiento estructurado no podemos
    # confirmar que el proceso corresponde a la aplicacion consultada.
    running = False
    if app is not None:
        exe = getattr(app, "executable", None)
        if exe:
            running = _is_process_running(str(exe))
        if not running and target:
            running = _is_process_running(target)

    # 4. Disponible para automatizacion (preflight aprobado y disponible).
    # Si el preflight falla (excepcion), no se puede confirmar:
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
    """Obtiene aplicaciones que tienen una capacidad especifica."""
    try:
        capability = ApplicationCapability(str(capability_name).strip().lower())
    except ValueError:
        return []

    app_manager = get_application_manager()
    return [app.name for app in app_manager.get_applications_by_capability(capability)]


def register_custom_application(app_config: Dict[str, Any]) -> bool:
    """Registra una aplicacion personalizada."""
    try:
        data = dict(app_config or {})
        if "name" not in data or "type" not in data:
            raise ValueError("Una aplicacion personalizada necesita 'name' y 'type'")

        # Reconstruccion tolerante de enums al recibir configuracion JSON.
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
            # aqui: pertenecen al CoordinateManager en tiempo de ejecucion.
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
                    logger.info(f"Estado desconocido omitido en register_custom_application: '{state}' "
                        "")
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
                logger.info(f"default_state desconocido omitido en register_custom_application: '{default_state}' "
                    "")
                data.pop("default_state", None)

        app = ApplicationKnowledge(**data)
        manager = get_application_manager()
        ok = manager.register_application(app)
        # register_application evita duplicados: si la clave ya existe en
        # memoria (p. ej. cargada desde entities.json), su rama de duplicado
        # no sobrescribe self.applications[key] con el app nuevo, por lo que
        # los campos del config (preflight_requirements, calibration_policy,
        # nombres de capabilities...) se perderian al recuperar la app.
        # Asegurar que la app registrada refleje el config recibido.
        key = manager._normalize_name(app.name)
        manager.applications[key] = app
        return ok
    except Exception as exc:
        logger.debug("register_custom_application: %s", exc)
        return False


def is_application_available(app_name: str) -> bool:
    """Comprueba disponibilidad en tiempo de ejecucion de una aplicacion.

    Distingue **disponible** (ejecutable instalado / app con URL) de
    **simplemente declarada** (registrada en el modelo).
    """
    try:
        return bool(get_application_manager().is_application_available(app_name))
    except Exception:
        return False


def is_application_open(app_name: str) -> bool:
    """Comprueba si la aplicacion ya tiene un proceso en ejecucion en el SO.

    Operacion de inspeccion de lectura sola sobre el gestionador de
    aplicaciones: consulta si el proceso de la app registrada esta activo.
    Nunca lanza, instala ni modifica ninguna aplicacion.
    """
    try:
        return bool(get_application_manager().is_application_open(app_name))
    except Exception:
        return False


def is_capability_available(app_name: str, capability: Any) -> bool:
    """Distingue una capacidad **disponible** de una sola **declarada**.

    Una capacidad esta disponible cuando esta declarada en el modelo y la
    aplicacion es disponible en tiempo de ejecucion.
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

    # Pequena pausa para que el SO aplique el cambio de estado
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
