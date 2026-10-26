# -*- coding: utf-8 -*-
"""Tests del contrato minimo 3.1.2.3 — datos opcionales para registrar una aplicacion.

Definicion verificada por inspeccion del codigo (src/hands/applications_core.py):

  ApplicationKnowledge (dataclass, lineas 137-166) tiene DOS campos SIN default:
    - name: str   (linea 140)
    - type: str   (linea 141)

  Los 9 campos restantes son OPCIONALES. Tres grupos de defaults:

  (a) Default explicito a None (no se normaliza):
    - executable:           Optional[str] = None       (linea 142)
    - url:                  Optional[str] = None        (linea 143)
    - icon:                 Optional[str] = None         (linea 144)
    - capabilities:         Optional[List[ApplicationCapabilityDef]] = None  (linea 145)
    - ui_elements:          Optional[List[UIElement]] = None  (linea 146)
    - states:               Optional[List[ApplicationState]] = None  (linea 147)
    - calibration_policy:   Optional[List[str]] = None  (linea 149)
    - preflight_requirements: Optional[List[str]] = None  (linea 150)
    - metadata:             Optional[Dict[str, Any]] = None  (linea 152)

  (b) Default escalares:
    - login_required:       bool = False  (linea 148)
    - default_state:        ApplicationState = ApplicationState.CLOSED  (linea 151)

  (c) Normalizacion en __post_init__ (None -> [] o [CLOSED] o {}):
    - capabilities              None -> []
    - ui_elements               None -> []
    - states                    None -> [ApplicationState.CLOSED]
    - calibration_policy        None -> []
    - preflight_requirements    None -> []
    - metadata                  None -> {}

  UIElement (dataclass, lineas 77-86): DOS campos obligatorios (name, type) y
  CUATRO campos opcionales:
    - coordinates:            Optional[Dict[str, Any]] = None  (linea 82)
    - screen:                 int = 0                           (linea 83)
    - calibration_data:       Optional[Dict[str, Any]] = None  (linea 84)
    - required_capability:    Optional[ApplicationCapability] = None  (linea 85)
  UIElement NO tiene __post_init__: los defaults son los declarados.

  ApplicationCapabilityDef (dataclass, lines 117-133): SIETE campos obligatorios
  y TRES opcionales:
    - timeout:                float = 30.0   (linea 127)
    - retry_count:            int = 3        (linea 128)
    - alternatives:           Optional[List[str]] = None -> []  (linea 129, __post_init__ linea 131-133)

  register_application (lineas 351-375) persiste en la Entity SOLO:
  id, type, name, properties{type, executable, url, login_required, capabilities},
  aliases=[], confidence=1.0, tags=[].
  Campos opcionales que SE PERDERAN al registrar: icon, ui_elements, states,
  calibration_policy, preflight_requirements, default_state, metadata.

  register_custom_application (lineas 1016-1052) acepta el dict completo;
  solo exige name y type; reconstruye enums (ApplicationCapability, ApplicationCapabilityDef,
  UIElement, ApplicationState) desde strings.

  Estos tests no modifican codigo de produccion. Verifican unicamente el contrato
  existente de datos opcionales.
"""

import dataclasses
import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    get_application_manager,
    register_custom_application,
)


# ---------------------------------------------------------------------------
# ApplicationKnowledge — defaults declarados y normalizados
# ---------------------------------------------------------------------------

class TestApplicationKnowledgeOptionalDefaults:
    """Verifica el valor por defecto de CADA campo opcional de ApplicationKnowledge."""

    def test_minimal_construction_all_optionals_defaulted(self):
        """Construir con solo name+type: todos los campos opcionales toman su default."""
        app = ApplicationKnowledge(name="AppOpt", type="browser")

        # (a) Default None (no normalizado)
        assert app.executable is None
        assert app.url is None
        assert app.icon is None

        # (c) Normalizados por __post_init__
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.metadata == {}

        # (b) Defaults escalares
        assert app.login_required is False
        assert app.default_state == ApplicationState.CLOSED

        # states: __post_init__ inicializa a [CLOSED]
        assert app.states == [ApplicationState.CLOSED]

    def test_optional_fields_with_explicit_none(self):
        """Pasar explicitamente None a los campos opcionales produce el mismo default."""
        app = ApplicationKnowledge(
            name="AppNone", type="browser",
            executable=None, url=None, icon=None,
            capabilities=None, ui_elements=None,
            states=None, calibration_policy=None,
            preflight_requirements=None, metadata=None,
        )
        assert app.executable is None
        assert app.url is None
        assert app.icon is None
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.metadata == {}

    def test_optional_fields_with_explicit_values(self):
        """Los campos opcionales aceptan valores reales sin perder defaults de los demas."""
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_app",
            description="Opens the app",
            required_ui_elements=[],
            preconditions=[],
            effects=["opened"],
            cost=5.0,
        )
        element = UIElement(name="btn_ok", type="button")
        app = ApplicationKnowledge(
            name="FullApp", type="utility",
            executable="/usr/bin/fullapp",
            url="https://example.com",
            icon="icon.png",
            capabilities=[cap],
            ui_elements=[element],
            states=[ApplicationState.OPEN, ApplicationState.ACTIVE],
            login_required=True,
            calibration_policy=["s1", "s2"],
            preflight_requirements=["admin"],
            default_state=ApplicationState.ACTIVE,
            metadata={"version": "1.0"},
        )
        assert app.executable == "/usr/bin/fullapp"
        assert app.url == "https://example.com"
        assert app.icon == "icon.png"
        assert len(app.capabilities) == 1
        assert app.capabilities[0].name == "open_app"
        assert len(app.ui_elements) == 1
        assert app.ui_elements[0].name == "btn_ok"
        assert app.states == [ApplicationState.OPEN, ApplicationState.ACTIVE]
        assert app.login_required is True
        assert app.calibration_policy == ["s1", "s2"]
        assert app.preflight_requirements == ["admin"]
        assert app.default_state == ApplicationState.ACTIVE
        assert app.metadata == {"version": "1.0"}

    def test_dataclass_field_order(self):
        """Verifica el orden canonico de campos: name, type obligatorios primero."""
        fields = {f.name: f for f in __import__("dataclasses").fields(ApplicationKnowledge)}
        # Los dos primeros campos deben ser los obligatorios
        assert list(fields.keys())[0] == "name"
        assert list(fields.keys())[1] == "type"
        # Todos los demas deben tener default
        optional_names = list(fields.keys())[2:]
        for fname in optional_names:
            assert fields[fname].default is not dataclasses.MISSING or \
                   fields[fname].default_factory is not dataclasses.MISSING, \
                   f"Campo '{fname}' deberia tener default"

    def test_optional_field_count(self):
        """ApplicationKnowledge tiene exactamente 13 campos: 2 obligatorios + 11 opcionales."""
        fields = dataclasses.fields(ApplicationKnowledge)
        assert len(fields) == 13
        optional = [f for f in fields if f.name not in ("name", "type")]
        assert len(optional) == 11

    @staticmethod
    def _make_minimal_manager():
        """Crea un ApplicationManager sin __init__ (evita registrar Chrome/Spotify)."""
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}

        class _FakeMemoryManager:
            def __init__(self):
                self.saved = []

            def save_entity(self, entity):
                self.saved.append(entity)

            def get_entities_by_type(self, t):
                return []

        manager.memory_manager = _FakeMemoryManager()
        return manager

    def test_register_application_persists_optional_defaults(self):
        """register_application persiste los defaults correctos para campos opcionales."""
        manager = self._make_minimal_manager()
        app = ApplicationKnowledge(name="PersistOptApp", type="browser")
        assert manager.register_application(app) is True

        entity = manager.memory_manager.saved[-1]
        assert entity.id == "app_persistoptapp"
        assert entity.type == "application"
        assert entity.name == "PersistOptApp"

        props = entity.properties
        assert props["type"] == "browser"
        assert props["executable"] is None
        assert props["url"] is None
        assert props["login_required"] is False
        assert props["capabilities"] == []

        # Campos opcionales que register_application NO persiste (se pierden)
        assert "icon" not in props
        assert "ui_elements" not in props
        assert "states" not in props
        assert "calibration_policy" not in props
        assert "preflight_requirements" not in props
        assert "default_state" not in props
        assert "metadata" not in props

    def test_register_application_persists_optional_provided(self):
        """register_application persiste valores opcionales cuando se proveen."""
        manager = self._make_minimal_manager()
        app = ApplicationKnowledge(
            name="FullPersistApp", type="browser",
            executable="chrome", url="https://chrome.google.com",
            login_required=True,
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_chrome",
                    description="Open Chrome",
                    required_ui_elements=[],
                    preconditions=[],
                    effects=["chrome_open"],
                    cost=10.0,
                )
            ],
        )
        assert manager.register_application(app) is True

        entity = manager.memory_manager.saved[-1]
        props = entity.properties
        assert props["executable"] == "chrome"
        assert props["url"] == "https://chrome.google.com"
        assert props["login_required"] is True
        assert props["capabilities"] == ["open"]


# ---------------------------------------------------------------------------
# UIElement — defaults
# ---------------------------------------------------------------------------

class TestUIElementOptionalDefaults:
    """Verifica el valor por defecto de CADA campo opcional de UIElement."""

    def test_minimal_construction_all_optionals_defaulted(self):
        """UIElement con solo name+type: los 4 campos opcionales toman su default."""
        element = UIElement(name="btn", type="button")

        assert element.coordinates is None
        assert element.screen == 0
        assert element.calibration_data is None
        assert element.required_capability is None

    def test_optional_fields_with_explicit_none(self):
        """Pasar explicitamente None produce el mismo default."""
        element = UIElement(
            name="btn", type="button",
            coordinates=None, screen=None,
            calibration_data=None, required_capability=None,
        )
        # screen con default 0, pero pasar None sobrescribe a None (no hay __post_init__)
        assert element.coordinates is None
        assert element.screen is None
        assert element.calibration_data is None
        assert element.required_capability is None

    def test_optional_fields_with_explicit_values(self):
        """Los campos opcionales aceptan valores reales."""
        element = UIElement(
            name="address_bar", type="input",
            coordinates={"x": 100, "y": 200},
            screen=1,
            calibration_data={"method": "visual"},
            required_capability=ApplicationCapability.NAVIGATE,
        )
        assert element.coordinates == {"x": 100, "y": 200}
        assert element.screen == 1
        assert element.calibration_data == {"method": "visual"}
        assert element.required_capability == ApplicationCapability.NAVIGATE

    def test_field_count(self):
        """UIElement tiene exactamente 6 campos: 2 obligatorios + 4 opcionales."""
        fields = dataclasses.fields(UIElement)
        assert len(fields) == 6
        optional = [f for f in fields if f.name not in ("name", "type")]
        assert len(optional) == 4

    def test_is_calibrated_defaults_false(self):
        """Un UIElement con defaults es NOT calibrated (coordinates is None)."""
        element = UIElement(name="btn", type="button")
        assert element.is_calibrated() is False

    def test_is_calibrated_with_coordinates(self):
        """Un UIElement con coordenadas {x,y} validas es calibrated."""
        element = UIElement(
            name="btn", type="button",
            coordinates={"x": 100, "y": 200},
        )
        assert element.is_calibrated() is True


# ---------------------------------------------------------------------------
# ApplicationCapabilityDef — defaults
# ---------------------------------------------------------------------------

class TestApplicationCapabilityDefOptionalDefaults:
    """Verifica el valor por defecto de los campos opcionales de ApplicationCapabilityDef."""

    def test_minimal_construction(self):
        """Construir con los 7 campos obligatorios: los 3 opcionales toman default."""
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_app",
            description="Opens the app",
            required_ui_elements=[],
            preconditions=[],
            effects=["opened"],
            cost=5.0,
        )
        assert cap.timeout == 30.0
        assert cap.retry_count == 3
        assert cap.alternatives == []

    def test_alternatives_explicit_none(self):
        """alternatives=None normalizado a [] por __post_init__."""
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_app",
            description="Opens the app",
            required_ui_elements=[],
            preconditions=[],
            effects=["opened"],
            cost=5.0,
            alternatives=None,
        )
        assert cap.alternatives == []

    def test_alternatives_provided(self):
        """alternatives con valores reales se conservan."""
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_app",
            description="Opens the app",
            required_ui_elements=[],
            preconditions=[],
            effects=["opened"],
            cost=5.0,
            timeout=60.0,
            retry_count=5,
            alternatives=["open_browser", "launch_app"],
        )
        assert cap.timeout == 60.0
        assert cap.retry_count == 5
        assert cap.alternatives == ["open_browser", "launch_app"]

    def test_field_count(self):
        """ApplicationCapabilityDef tiene 10 campos: 7 obligatorios + 3 opcionales."""
        fields = __import__("dataclasses").fields(ApplicationCapabilityDef)
        optional = [f for f in fields if f.name not in
                    ("capability", "name", "description",
                     "required_ui_elements", "preconditions", "effects", "cost")]
        assert len(optional) == 3
        assert {f.name for f in optional} == {"timeout", "retry_count", "alternatives"}


# ---------------------------------------------------------------------------
# register_custom_application — contrato de datos opcionales en el API dict
# ---------------------------------------------------------------------------

class TestRegisterCustomApplicationOptionalData:
    """Verifica que register_custom_application acepta datos opcionales en el dict."""

    def test_minimal_dict_accepted(self):
        """Un dict con SOLO name y type es aceptado."""
        result = register_custom_application({"name": "OptCustomMin", "type": "utility"})
        assert result is True

    def test_dict_with_optional_fields_accepted(self):
        """Un dict con todos los campos opcionales es aceptado."""
        config = {
            "name": "OptCustomFull",
            "type": "browser",
            "executable": "custom.exe",
            "url": "https://custom.example.com",
            "icon": "icon.png",
            "login_required": True,
            "calibration_policy": ["s1"],
            "preflight_requirements": ["checked"],
            "default_state": "open",
            "metadata": {"version": "2.0"},
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("OptCustomFull")
        assert app is not None
        assert app.executable == "custom.exe"
        assert app.url == "https://custom.example.com"
        assert app.icon == "icon.png"
        assert app.login_required is True
        assert app.calibration_policy == ["s1"]
        assert app.preflight_requirements == ["checked"]
        assert app.default_state == ApplicationState.OPEN
        assert app.metadata == {"version": "2.0"}

    def test_optional_capabilities_accepted(self):
        """register_custom_application reconstruye ApplicationCapabilityDef desde dict."""
        config = {
            "name": "OptCustomCaps",
            "type": "browser",
            "capabilities": [
                {
                    "capability": "open",
                    "name": "open_app",
                    "description": "Open app",
                    "required_ui_elements": [],
                    "preconditions": [],
                    "effects": ["opened"],
                    "cost": 5.0,
                    "timeout": 45.0,
                    "retry_count": 2,
                }
            ],
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("OptCustomCaps")
        assert app is not None
        assert len(app.capabilities) == 1
        assert app.capabilities[0].capability == ApplicationCapability.OPEN
        assert app.capabilities[0].timeout == 45.0
        assert app.capabilities[0].retry_count == 2

    def test_optional_ui_elements_accepted(self):
        """register_custom_application reconstruye UIElement desde dict."""
        config = {
            "name": "OptCustomUI",
            "type": "browser",
            "ui_elements": [
                {"name": "btn_ok", "type": "button", "screen": 1},
            ],
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("OptCustomUI")
        assert app is not None
        assert len(app.ui_elements) == 1
        assert app.ui_elements[0].name == "btn_ok"
        assert app.ui_elements[0].type == "button"
        assert app.ui_elements[0].screen == 1

    def test_optional_states_accepted(self):
        """register_custom_application reconstruye ApplicationState desde strings."""
        config = {
            "name": "OptCustomStates",
            "type": "browser",
            "states": ["open", "active"],
            "default_state": "active",
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("OptCustomStates")
        assert app is not None
        assert app.states == [ApplicationState.OPEN, ApplicationState.ACTIVE]
        assert app.default_state == ApplicationState.ACTIVE
