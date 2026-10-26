# -*- coding: utf-8 -*-
"""Tests del contrato minimo 3.1.2.2 — datos obligatorios para registrar una aplicacion.

Definicion verificada por inspeccion del codigo (src/hands/applications_core.py):

  ApplicationKnowledge (dataclass, lineas 137-166) tiene dos campos SIN default:
    - name: str   (linea 140)
    - type: str   (linea 141)

Todos los demas campos tienen un default explicito (None, False, CLOSED) o se
inicializan en __post_init__ a listas/diccionarios vacios. Por tanto, los datos
obligatorios para registrar una aplicacion son EXACTAMENTE `name` y `type`.

  register_application (lineas 351-375) recibe un ApplicationKnowledge ya construido
  (el dataclass constructor impone la obligatoriedad de name+type con TypeError).
  No realiza una validacion adicional de campos obligatorios: confia en el contrato
  del dataclass.

  register_custom_application (lineas 1016-1052) valida EXPLICITAMENTE que el
  diccionario de configuracion contenga "name" y "type" (lineas 1020-1021),
  lanzando ValueError si falta alguno.

Estos tests no modifican codigo de produccion. Verifican unicamente el contrato
existente.
"""

import pytest

from src.hands.applications_core import (
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    get_application_manager,
    register_custom_application,
)


class TestNameIsMandatory:
    """`name` es el primer campo requerido del dataclass ApplicationKnowledge."""

    def test_name_missing_raises_type_error(self):
        """Construir ApplicationKnowledge sin `name` lanza TypeError (dataclass)."""
        with pytest.raises(TypeError):
            ApplicationKnowledge(type="browser")

    def test_name_only_is_not_enough(self):
        """Ni siquiera pasando type como kwarg: falta name completamente."""
        with pytest.raises(TypeError):
            type_only = {"type": "browser"}
            ApplicationKnowledge(**type_only)


class TestTypeIsMandatory:
    """`type` es el segundo campo requerido del dataclass ApplicationKnowledge."""

    def test_type_missing_raises_type_error(self):
        """Construir ApplicationKnowledge sin `type` lanza TypeError (dataclass)."""
        with pytest.raises(TypeError):
            ApplicationKnowledge(name="MyApp")

    def test_type_only_is_not_enough(self):
        """Ni siquiera pasando name como kwarg: falta type completamente."""
        with pytest.raises(TypeError):
            name_only = {"name": "MyApp"}
            ApplicationKnowledge(**name_only)


class TestMinimalConstruction:
    """Construir ApplicationKnowledge con SOLO los datos obligatorios funciona."""

    def test_construct_with_only_name_and_type(self):
        """name + type son suficientes: no se requiere ningun otro campo."""
        app = ApplicationKnowledge(name="MinimalApp", type="utility")
        assert app is not None
        assert app.name == "MinimalApp"
        assert app.type == "utility"

    def test_minimal_construction_all_optionals_defaulted(self):
        """Verifica el valor por defecto de CADA campo opcional."""
        app = ApplicationKnowledge(name="MinApp", type="browser")

        # Campos con default explicito = None
        assert app.executable is None
        assert app.url is None
        assert app.icon is None

        # Campos inicializados por __post_init__ a listas/dict vacios
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.metadata == {}

        # Campos con defaults escalares
        assert app.login_required is False
        assert app.default_state == ApplicationState.CLOSED

        # states: __post_init__ inicializa a [CLOSED]
        assert app.states == [ApplicationState.CLOSED]


class TestRegisterApplicationWithMinimalData:
    """register_application acepta un ApplicationKnowledge con solo name+type."""

    def _make_minimal_manager(self):
        """Crea un ApplicationManager sin __init__ (evita registrar Chrome/Spotify)."""
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}

        class _FakeMemoryManager:
            def save_entity(self, entity):
                pass

        manager.memory_manager = _FakeMemoryManager()
        return manager

    def test_register_minimal_app_succeeds(self):
        """register_application con solo name+type retorna True."""
        manager = self._make_minimal_manager()
        app = ApplicationKnowledge(name="BareApp", type="utility")
        assert manager.register_application(app) is True
        assert "bareapp" in manager.applications

    def test_register_minimal_app_entity_has_defaults(self):
        """La Entity persistida refleja los defaults de register_application."""
        manager = self._make_minimal_manager()
        saved = {}

        class _FakeMM:
            def save_entity(self, entity):
                saved["entity"] = entity

        manager.memory_manager = _FakeMM()

        app = ApplicationKnowledge(name="BareApp", type="utility")
        manager.register_application(app)

        entity = saved["entity"]
        assert entity.id == "app_bareapp"
        assert entity.type == "application"
        assert entity.name == "BareApp"
        # properties con valores por defecto
        props = entity.properties
        assert props["type"] == "utility"
        assert props["executable"] is None
        assert props["url"] is None
        assert props["login_required"] is False
        assert props["capabilities"] == []

    def test_register_minimal_app_case_insensitive_key(self):
        """La clave del dict usa name.lower() (coherente con 3.1.2.1)."""
        manager = self._make_minimal_manager()
        app = ApplicationKnowledge(name="My Mixed Case App", type="utility")
        manager.register_application(app)
        assert "my mixed case app" in manager.applications


class TestRegisterCustomApplicationMandatoryData:
    """register_custom_application valida name+type en el dict de config."""

    def test_minimal_config_accepted(self):
        """Un config con SOLO name y type es aceptado y registrado."""
        result = register_custom_application({"name": "MinimalCustom", "type": "utility"})
        assert result is True

    def test_minimal_config_registered_in_manager(self):
        """La aplicacion registrada con config minima aparece en el gestor."""
        register_custom_application({"name": "MinimalCustomCheck", "type": "browser"})
        app = get_application_manager().get_application("MinimalCustomCheck")
        assert app is not None
        assert app.name == "MinimalCustomCheck"
        assert app.type == "browser"

    def test_missing_name_rejected(self):
        """Falta name -> retorna False (ValueError interno)."""
        result = register_custom_application({"type": "utility"})
        assert result is False

    def test_missing_type_rejected(self):
        """Falta type -> retorna False (ValueError interno)."""
        result = register_custom_application({"name": "NoTypeApp"})
        assert result is False

    def test_empty_config_rejected(self):
        """Config vacio -> retorna False por falta de name y type."""
        result = register_custom_application({})
        assert result is False

    def test_none_config_rejected(self):
        """None -> retorna False."""
        result = register_custom_application(None)
        assert result is False

    def test_config_extra_fields_still_requires_name_type(self):
        """Incluso con campos extra, name y type siguen siendo obligatorios."""
        result = register_custom_application({"executable": "x", "url": "y"})
        assert result is False
