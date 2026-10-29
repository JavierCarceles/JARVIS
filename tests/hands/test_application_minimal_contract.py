# -*- coding: utf-8 -*-
"""Tests del contrato minimo consolidado — unidad 3.1.3.3 (FASE 3.1.3 — Compatibilidad).

Tema de la unidad: "Crear tests del contrato minimo" de `ApplicationKnowledge`.

Este archivo es el test AUTHORITATIVE del contrato minimo de `ApplicationKnowledge`
(src/hands/applications_core.py:137-166) tal como se definio en 3.1.2:

  - Obligatorios (sin default): name (str), type (str). El dataclass constructor
    impone su ausencia con TypeError (ver 3.1.2.2).
  - Opcionales (13 campos) con defaults escalares o inicializados en __post_init__:

      executable: Optional[str]            = None
      url: Optional[str]                   = None
      icon: Optional[str]                  = None
      capabilities: Optional[List[CapabilityDef]] = None  -> []  (en __post_init__)
      ui_elements: Optional[List[UIElement]]        = None  -> []  (en __post_init__)
      states: Optional[List[ApplicationState]]      = None  -> [CLOSED]  (en __post_init__)
      login_required: bool                 = False
      calibration_policy: Optional[List[str]]       = None  -> []  (en __post_init__)
      preflight_requirements: Optional[List[str]]  = None  -> []  (en __post_init__)
      default_state: ApplicationState      = ApplicationState.CLOSED
      metadata: Optional[Dict[str, Any]]   = None  -> {}  (en __post_init__)

DIFERENCIAS RESPECTO A UNIDADES PREVIAS (no se duplican aqui):
  - 3.1.2.1 (test_application_identification.py): normalizacion de nombres/claves.
  - 3.1.2.2 (test_application_mandatory_data.py): name+type obligatorios + register.
  - 3.1.2.3 (test_application_optional_data.py): defaults de campos opcionales.
  - 3.1.2.4 (test_application_contract_no_duplication.py): registro idempotente.
  - 3.1.3.2 (test_consumer_api_compatibility.py): contrato consumido POR APIs
    (Brain/HTN/Planner/Executor/_check_application_available/open_application).

Este archivo (3.1.3.3) verifica el contrato minimo en el MODELO, como spec
autoritativo e invariantes que las unidades anteriores NO cubren:

  1. Spec consolidado del contrato minimo (campos, orden, defaults exactos).
  2. **Aislamiento de defaults mutables** [GAP]: dos instancias minimas no comparten
     objetos de coleccion (capabilities, ui_elements, states, calibration_policy,
     preflight_requirements, metadata). Mutar una instancia no afecta a la otra.
     Esta invariante critica —clasico bug de "mutable default"— no esta verificada
     en ninguna unidad anterior, aunque __post_init__ la satisface creando nuevos
     objetos por instancia. El test la hace EXPLICITA y regresiva.
  3. Invariantes de modelo con app minimal/empty (get_capability, is_capable,
     get_ui_element, get_calibrated_elements).
  4. Round-trip register -> retrieve -> verify contract usando un manager aislado
     (ApplicationManager.__new__ + memory_manager falso): sin persistir a produccion.
  5. Round-trip in-memory a traves del singleton REAL (inyeccion directa en
     `applications` + restauracion): verifica que el catalogo real reconoce una app
     minimal, sin tocar entities.json.
  6. Contrato minimo de UIElement (name, type obligatorios; coordinates/
     screen/calibration_data/required_capability/description opcionales).

No modifica codigo de produccion.
"""

import copy
import dataclasses
from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    get_application_manager,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_minimal_app(name="MinApp", app_type="utility"):
    """ApplicationKnowledge con SOLO los campos obligatorios del contrato minimo."""
    return ApplicationKnowledge(name=name, type=app_type)


def _make_minimal_manager():
    """ApplicationManager aislado (bypass __init__) con memory_manager falso.

    Evita registrar Chrome/Spotify y evita toda persistencia a entities.json:
    `save_entity` es un no-op y `applications` parte vacio. Ideal para testear
    register_application / get_application sin efectos secundarios.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _FakeMemoryManager:
        def save_entity(self, entity):
            pass

    manager.memory_manager = _FakeMemoryManager()
    return manager


# Campos de coleccion cuyo default se inicializa en __post_init__ a un nuevo
# objeto por instancia. Son los que required aislamiento de defaults mutables.
_COLLECTION_ATTRS = [
    "capabilities",
    "ui_elements",
    "states",
    "calibration_policy",
    "preflight_requirements",
    "metadata",
]


# ---------------------------------------------------------------------------
# 1. Spec consolidado del contrato minimo (modelo)
# ---------------------------------------------------------------------------

class TestMinimalContractSpec:
    """Spec autoritativo del contrato minimo: campos obligatorios, orden, defaults."""

    def test_exactly_two_mandatory_fields_without_default(self):
        """Solo `name` y `type` carecen de default; el resto es opcional."""
        fields = dataclasses.fields(ApplicationKnowledge)
        optional = {
            f.name for f in fields
            if f.default is not dataclasses.MISSING
            or f.default_factory is not dataclasses.MISSING
        }
        mandatory_names = [f.name for f in fields if f.name not in optional]
        assert mandatory_names == ["name", "type"]

    def test_field_count(self):
        """ApplicationKnowledge define exactamente 13 campos (2 obligatorios + 11 opcionales)."""
        assert len(dataclasses.fields(ApplicationKnowledge)) == 13

    def test_field_order_is_name_then_type(self):
        """name precede a type como primeros campos (contrato minimo)."""
        names = [f.name for f in dataclasses.fields(ApplicationKnowledge)]
        assert names[0] == "name"
        assert names[1] == "type"

    def test_all_optional_fields_default_to_expected_values(self):
        """Construir con name+type deja CUALQUIER campo opcional en su valor por defecto."""
        app = _make_minimal_app("Min", "utility")

        # Defaults escalares / None
        assert app.executable is None
        assert app.url is None
        assert app.icon is None
        assert app.login_required is False
        assert app.default_state == ApplicationState.CLOSED

        # Defaults inicializados por __post_init__
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.metadata == {}

    def test_none_passed_explicitly_yields_same_defaults(self):
        """Pasar explicitamente None a los campos de coleccion produce el mismo
        default que no pasarlos (el __post_init__ normaliza None -> coleccion nueva)."""
        app = ApplicationKnowledge(
            name="ExplicitNone", type="utility",
            capabilities=None, ui_elements=None, states=None,
            calibration_policy=None, preflight_requirements=None, metadata=None,
        )
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.metadata == {}

    def test_states_default_is_closed_not_shared_singleton(self):
        """El default de states es [CLOSED] pero NO un singleton global: dos apps
        pueden mutar su `states` independientemente (aislamento mutable, 3.1.3.3)."""
        a = _make_minimal_app("A", "utility")
        b = _make_minimal_app("B", "utility")
        assert a.states == [ApplicationState.CLOSED]
        a.states.append(ApplicationState.OPEN)
        assert a.states == [ApplicationState.CLOSED, ApplicationState.OPEN]
        assert b.states == [ApplicationState.CLOSED]  # no se ve la mutacion de A


# ---------------------------------------------------------------------------
# 2. Aislamiento de defaults mutables [GAP] — la invariante no verificada antes
# ---------------------------------------------------------------------------

class TestMutableDefaultIsolation:
    """GAP 3.1.3.3: dos ApplicationKnowledge minimas no comparten objetos de
    coleccion. Evita el clasico bug 'mutable default shared across instances'."""

    @pytest.mark.parametrize("attr", _COLLECTION_ATTRS)
    def test_collection_objects_are_distinct_instances(self, attr):
        """getattr(a, attr) is not getattr(b, attr) para toda coleccion."""
        a = _make_minimal_app("A", "utility")
        b = _make_minimal_app("B", "utility")
        assert getattr(a, attr) is not getattr(b, attr)

    @pytest.mark.parametrize("attr", _COLLECTION_ATTRS)
    def test_mutation_does_not_leak_between_instances(self, attr):
        """Mutar la coleccion de una instancia no altera la de otra.

        Este es el test regresivo del bug de defaults mutables: si __post_init__
        usara un objeto compartido/singleton, este test fallaria. La invariante
        verificada es: B conserva su valor ORIGINAL pese a mutar A (no necesariamente
        vacio, pues `states` defaultea a [CLOSED]).
        """
        a = _make_minimal_app("A", "utility")
        b = _make_minimal_app("B", "utility")
        sentinel = object()

        # Valor original de B antes de tocar A (referencia de la invariante).
        original_b = list(getattr(b, attr)) if isinstance(getattr(b, attr), list) else dict(getattr(b, attr))

        collection_a = getattr(a, attr)
        # Mutacion generica sobre list/dict
        if isinstance(collection_a, list):
            collection_a.append("MARKER")
        elif isinstance(collection_a, dict):
            collection_a["__marker__"] = sentinel

        collection_b = getattr(b, attr)
        if isinstance(collection_b, list):
            assert collection_b == original_b
            assert "MARKER" not in collection_b
        elif isinstance(collection_b, dict):
            assert collection_b == original_b
            assert "__marker__" not in collection_b

    def test_states_single_element_is_new_list_each_time(self):
        """states se inicializa a una NUEVA lista [CLOSED] por instancia, no a una
        lista compartida entre defaults del dataclass."""
        a = _make_minimal_app("A", "utility")
        b = _make_minimal_app("B", "utility")
        assert a.states is not b.states
        assert a.states is not _make_minimal_app("C", "utility").states

    def test_metadata_deep_isolation(self):
        """metadata es un dict privado: mutarlo (incluso anidado) en una instancia
        no afecta a otra."""
        a = _make_minimal_app("A", "utility")
        b = _make_minimal_app("B", "utility")
        a.metadata["outer"] = {"inner": 1}
        assert b.metadata == {}
        # deepcopy de a no debe compartir referencias con b
        a_copy = copy.deepcopy(a)
        a_copy.metadata["outer"]["inner"] = 999
        assert a.metadata["outer"]["inner"] == 1  # b y a no se ven afectados


# ---------------------------------------------------------------------------
# 3. Invariantes de modelo con app minimal/empty
# ---------------------------------------------------------------------------

class TestModelInvariantsMinimalApp:
    """El modelo ApplicationKnowledge responde coherente con una app minimal
    (sin capabilities declaradas, sin ui_elements)."""

    def test_get_capability_returns_none(self):
        """get_capability devuelve None cuando no hay capabilities declaradas."""
        app = _make_minimal_app("Min", "utility")
        assert app.get_capability("open") is None
        assert app.get_capability(ApplicationCapability.OPEN) is None

    def test_is_capable_false_with_no_capabilities(self):
        """is_capable devuelve False para una app minimal (cualquier capability)."""
        app = _make_minimal_app("Min", "utility")
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.is_capable(ApplicationCapability.CLOSE) is False

    def test_is_capable_true_when_capability_present(self):
        """is_capable devuelve True cuando la capability esta declarada.

        Verifica que el contrato minimo no quiebra el metodo: una app que declara
        OPEN es capaz de OPEN y no de CLOSE.
        """
        open_def = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_min",
            description="Abre",
            required_ui_elements=[],
            preconditions=[],
            effects=[],
            cost=1.0,
        )
        app = ApplicationKnowledge(
            name="Min", type="utility", capabilities=[open_def],
        )
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_capable(ApplicationCapability.CLOSE) is False

    def test_get_ui_element_returns_none(self):
        """get_ui_element devuelve None cuando no hay ui_elements."""
        app = _make_minimal_app("Min", "utility")
        assert app.get_ui_element("address_bar") is None

    def test_get_calibrated_elements_empty(self):
        """get_calibrated_elements devuelve [] para una app sin ui_elements."""
        app = _make_minimal_app("Min", "utility")
        assert app.get_calibrated_elements() == []


# ---------------------------------------------------------------------------
# 4. Round-trip register -> retrieve con manager aislado (sin persistencia)
# ---------------------------------------------------------------------------

class TestMinimalAppEndToEndIsolatedManager:
    """register -> retrieve -> verificacion del contrato minimo usando un manager
    aislado (no persiste, no inicializa Chrome/Spotify)."""

    def test_register_minimal_app(self):
        """register_application con solo name+type retorna True y la registra."""
        manager = _make_minimal_manager()
        app = _make_minimal_app("BareApp", "utility")
        assert manager.register_application(app) is True
        assert "bareapp" in manager.applications

    def test_register_minimal_app_case_insensitive_key(self):
        """La clave usa name.lower() (coherente con 3.1.2.1)."""
        manager = _make_minimal_manager()
        manager.register_application(_make_minimal_app("My Mixed Case App", "utility"))
        assert "my mixed case app" in manager.applications

    def test_retrieve_minimal_app_preserves_contract(self):
        """Recuperar la app registrada conserva name, type y todos los defaults."""
        manager = _make_minimal_manager()
        manager.register_application(_make_minimal_app("RecoverableApp", "browser"))
        app = manager.get_application("recoverableapp")
        assert app is not None
        assert app.name == "RecoverableApp"
        assert app.type == "browser"
        assert app.executable is None
        assert app.capabilities == []
        assert app.states == [ApplicationState.CLOSED]

    def test_get_application_capabilities_minimal_empty(self):
        """get_application_capabilities devuelve {} para una app sin capabilities."""
        manager = _make_minimal_manager()
        manager.register_application(_make_minimal_app("EmptyCapsApp", "utility"))
        assert manager.get_application_capabilities("emptycapsapp") == {}

    def test_get_application_ui_elements_minimal_empty(self):
        """get_application_ui_elements devuelve {} para una app sin ui_elements."""
        manager = _make_minimal_manager()
        manager.register_application(_make_minimal_app("EmptyUiApp", "utility"))
        assert manager.get_application_ui_elements("emptyuiapp") == {}

    def test_get_applications_by_capability_minimal_empty(self):
        """get_applications_by_capability devuelve [] para una app minimal (sin caps)."""
        manager = _make_minimal_manager()
        manager.register_application(_make_minimal_app("NoCapsApp", "utility"))
        assert manager.get_applications_by_capability(ApplicationCapability.OPEN) == []


# ---------------------------------------------------------------------------
# 5. Round-trip in-memory a traves del singleton REAL (sin persistencia)
# ---------------------------------------------------------------------------

class TestMinimalAppSingletonInMemInjection:
    """Verifica que el singleton real reconoce una app minimal inyectada
    directamente en `applications` (sin pasar por register_application, por lo
    que no se persiste a entities.json). Se salva/restaura el dict del singleton."""

    def test_minimal_app_recognized_by_real_singleton(self):
        """get_application resuelve una app minimal inyectada en el singleton."""
        singleton = get_application_manager()
        original = dict(singleton.applications)
        try:
            singleton.applications["injectedminimalapp"] = _make_minimal_app(
                "InjectedMinimalApp", "utility",
            )
            app = singleton.get_application("injectedminimalapp")
            assert app is not None
            assert app.name == "InjectedMinimalApp"
            assert app.type == "utility"
            assert app.is_capable(ApplicationCapability.OPEN) is False
        finally:
            singleton.applications = original

    def test_brain_query_sees_minimal_app_in_singleton(self):
        """Brain._get_application_knowledge expone la app minimal inyectada con
        capabilities={} y available=False (consistente con 3.1.3.2)."""
        singleton = get_application_manager()
        original = dict(singleton.applications)
        try:
            singleton.applications["injectedminimalapp"] = _make_minimal_app(
                "InjectedMinimalApp", "utility",
            )
            from src.brain.llm import Brain
            brain = Brain(model="llama3")
            result = brain._get_application_knowledge()
            assert "injectedminimalapp" in result["applications"]
            info = result["applications"]["injectedminimalapp"]
            assert info["capabilities"] == {}
            assert info["available"] is False
        finally:
            singleton.applications = original


# ---------------------------------------------------------------------------
# 6. Contrato minimo de UIElement
# ---------------------------------------------------------------------------

class TestUIElementMinimalContract:
    """UIElement es el segundo bloque del contrato minimo: name y type son
    obligatorios; description/coordinates/screen/calibration_data/
    required_capability son opcionales."""

    def test_minimal_construction(self):
        """UIElement(name, type) construye instancia con name y type."""
        el = UIElement(name="address_bar", type="boton")
        assert el.name == "address_bar"
        assert el.type == "boton"

    def test_optional_fields_default(self):
        """Los campos opcionales de UIElement toman sus defaults al construir minimal."""
        el = UIElement(name="btn", type="boton")
        assert el.coordinates is None
        assert el.screen == 0
        assert el.calibration_data is None
        assert el.required_capability is None
        assert el.description == ""

    def test_is_calibrated_false_when_no_coordinates(self):
        """is_calibrated() devuelve False con coordinates por defecto (None)."""
        assert UIElement(name="btn", type="boton").is_calibrated() is False

    def test_is_calibrated_false_with_empty_coordinates(self):
        """is_calibrated() devuelve False con coordinates={}."""
        el = UIElement(name="btn", type="boton", coordinates={})
        assert el.is_calibrated() is False

    def test_is_calibrated_true_with_xy_pair(self):
        """is_calibrated() devuelve True con el formato claseico {x, y}."""
        el = UIElement(name="btn", type="boton", coordinates={"x": 100, "y": 200})
        assert el.is_calibrated() is True
