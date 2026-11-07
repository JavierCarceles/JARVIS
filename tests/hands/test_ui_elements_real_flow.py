# -*- coding: utf-8 -*-
"""
Tests de flujo real de elementos UI — unidad 3.8.4.7.1 (FASE 3.8).

Verifica comportamiento REAL del sistema de elementos UI y descubrimiento
de aplicaciones, sin mocks que fuercen decisiones ni sustituyan validaciones
reales. Reutiliza contratos reales del codigo fuente:

- ApplicationManager: get_application, resolve_application, register_discovered_application,
  _normalize_name, _check_application_available
- UIElement: creacion, is_calibrated(), coordenadas, descripcion
- ApplicationCapabilityDef / ApplicationCapability: capacidades reales declaradas
- ApplicationKnowledge: is_capable, is_capability_available, get_ui_element,
  get_calibrated_elements, get_observed_facts, get_inferred_data
- _FakeMemoryManager: verifica que register_discovered_application NO llama a save_entity

No abre ventanas GUI, no lanza procesos, no modifica entities.json de produccion.
Todo el trabajo sobre ficheros usa directorios temporales (tmp_path).
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    _check_application_available,
    get_application_manager,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

class _FakeMemoryManager:
    """Memory manager simulado que registra si se llamo a save_entity."""

    def __init__(self) -> None:
        self.saved_entities: list = []

    def save_entity(self, entity: Any) -> None:
        self.saved_entities.append(entity)

    def get_entities_by_type(self, _type: str) -> list:
        return []


def _make_manager() -> ApplicationManager:
    """Crea ApplicationManager sin __init__ (evita registrar Chrome/Spotify
    ni cargar entidades de memoria) y con memory_manager falsificado."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = _FakeMemoryManager()
    return manager


def _real_app_knowledge(
    name: str,
    executable: str | None = "notepad.exe",
    url: str | None = None,
) -> ApplicationKnowledge:
    """ApplicationKnowledge con datos reales de una aplicacion inocua."""
    return ApplicationKnowledge(
        name=name,
        type="application",
        executable=executable,
        url=url,
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name=f"open_{name.lower()}",
                description=f"Abre {name}",
                required_ui_elements=[],
                preconditions=[f"{name.lower()}_closed"],
                effects=[f"{name.lower()}_open", f"{name.lower()}_active"],
                cost=10.0,
            ),
            ApplicationCapabilityDef(
                capability=ApplicationCapability.CLICK,
                name=f"click_{name.lower()}_element",
                description=f"Hace clic en un elemento de {name}",
                required_ui_elements=["main_window"],
                preconditions=[f"{name.lower()}_open", f"{name.lower()}_active"],
                effects=["element_clicked"],
                cost=2.0,
            ),
        ],
        ui_elements=[
            UIElement(
                name="main_window",
                type="window",
                description="Ventana principal de la aplicacion",
                required_capability=ApplicationCapability.OPEN,
                coordinates={"x": 100, "y": 100, "width": 800, "height": 600},
                screen=0,
            ),
            UIElement(
                name="menu_button",
                type="button",
                description="Boton de menu principal",
                required_capability=ApplicationCapability.CLICK,
                coordinates={"x": 50, "y": 50, "width": 100, "height": 40},
                screen=0,
            ),
        ],
        states=[
            ApplicationState.CLOSED,
            ApplicationState.OPEN,
            ApplicationState.ACTIVE,
        ],
        login_required=False,
        calibration_policy=["main_window", "menu_button"],
        preflight_requirements=["application_available"],
        default_state=ApplicationState.CLOSED,
    )


# ---------------------------------------------------------------------------
# TESTS: _check_application_available con ejecutables reales
# ---------------------------------------------------------------------------

class TestCheckApplicationAvailableReal:
    """Verifica que _check_application_available funciona con rutas reales."""

    def test_notepad_exe_disponible(self):
        """notepad.exe existe en el sistema y es detectable."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        assert _check_application_available(app) is True

    def test_calc_exe_disponible(self):
        """calc.exe existe en el sistema y es detectable."""
        app = _real_app_knowledge("Calculator", executable="calc.exe")
        assert _check_application_available(app) is True

    def test_ejecutable_inexistente_no_disponible(self):
        """Un ejecutable que no existe retorna False."""
        app = _real_app_knowledge("AppInexistente", executable="noexiste_12345.exe")
        assert _check_application_available(app) is False

    def test_sin_ejecutable_con_url_es_disponible(self):
        """Una app sin exe pero con URL se considera disponible."""
        app = _real_app_knowledge("WebApp", executable=None, url="https://example.com")
        assert _check_application_available(app) is True

    def test_sin_ejecutable_ni_url_no_disponible(self):
        """Una app sin exe ni URL no esta disponible."""
        app = _real_app_knowledge("Vacia", executable=None, url=None)
        assert _check_application_available(app) is False


# ---------------------------------------------------------------------------
# TESTS: UIElement con datos reales y is_calibrated()
# ---------------------------------------------------------------------------

class TestUIElementReal:
    """Verifica UIElement con coordenadas reales y calibracion."""

    def test_ui_element_con_coordenadas_reales_esta_calibrado(self):
        """UIElement con coordenadas validas (x,y) reporta is_calibrated True."""
        elem = UIElement(
            name="main_window",
            type="window",
            description="Ventana principal",
            required_capability=ApplicationCapability.OPEN,
            coordinates={"x": 100, "y": 100, "width": 800, "height": 600},
            screen=0,
        )
        assert elem.is_calibrated() is True

    def test_ui_element_sin_coordenadas_no_esta_calibrado(self):
        """UIElement sin coordenadas reporta is_calibrated False."""
        elem = UIElement(
            name="menu_button",
            type="button",
            description="Boton sin coordenadas",
            required_capability=ApplicationCapability.CLICK,
        )
        assert elem.is_calibrated() is False

    def test_ui_element_coordenadas_incompletas_no_están_calibradas(self):
        """Coordenadas sin x o sin y no son validas para calibracion."""
        elem = UIElement(
            name="partial",
            type="button",
            coordinates={"x": 100},  # falta "y"
        )
        assert elem.is_calibrated() is False

    def test_ui_element_campos_reales(self):
        """Verifica que todos los campos de UIElement se asignan correctamente."""
        elem = UIElement(
            name="btn_aceptar",
            type="button",
            description="Boton de aceptar",
            required_capability=ApplicationCapability.CLICK,
            coordinates={"x": 200, "y": 300, "width": 120, "height": 45},
            screen=1,
            calibration_data={"source": "vision", "confidence": 0.95},
        )
        assert elem.name == "btn_aceptar"
        assert elem.type == "button"
        assert elem.description == "Boton de aceptar"
        assert elem.required_capability == ApplicationCapability.CLICK
        assert elem.coordinates == {"x": 200, "y": 300, "width": 120, "height": 45}
        assert elem.screen == 1
        assert elem.calibration_data == {"source": "vision", "confidence": 0.95}

    def test_ui_element_defaults(self):
        """Valores por defecto de UIElement."""
        elem = UIElement(name="test", type="input")
        assert elem.description == ""
        assert elem.required_capability is None
        assert elem.coordinates is None
        assert elem.screen == 0
        assert elem.calibration_data is None


# ---------------------------------------------------------------------------
# TESTS: ApplicationCapabilityDef y ApplicationKnowledge con datos reales
# ---------------------------------------------------------------------------

class TestApplicationCapabilityDefReal:
    """Verifica ApplicationCapabilityDef con capacidades reales."""

    def test_capacidad_open_con_precondiciones_y_efectos(self):
        """Capacidad OPEN con precondiciones y efectos declarados."""
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_notepad",
            description="Abre el Bloc de Notas",
            required_ui_elements=[],
            preconditions=["notepad_closed"],
            effects=["notepad_open", "notepad_active"],
            cost=10.0,
            timeout=30.0,
            retry_count=3,
        )
        assert cap.capability == ApplicationCapability.OPEN
        assert cap.name == "open_notepad"
        assert cap.description == "Abre el Bloc de Notas"
        assert cap.required_ui_elements == []
        assert cap.preconditions == ["notepad_closed"]
        assert cap.effects == ["notepad_open", "notepad_active"]
        assert cap.cost == 10.0
        assert cap.timeout == 30.0
        assert cap.retry_count == 3

    def test_capacidad_click_con_ui_element_requerido(self):
        """Capacidad CLICK que requiere un elemento UI."""
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.CLICK,
            name="click_menu",
            description="Hace clic en el menu",
            required_ui_elements=["main_window", "menu_button"],
            preconditions=["app_open", "app_active", "element_visible"],
            effects=["menu_opened"],
            cost=2.0,
        )
        assert cap.capability == ApplicationCapability.CLICK
        assert cap.required_ui_elements == ["main_window", "menu_button"]


class TestApplicationKnowledgeReal:
    """Verifica ApplicationKnowledge con datos reales de aplicaciones."""

    def test_is_capable_devuelve_true_para_capacidad_declarada(self):
        """is_capable retorna True cuando la capacidad esta declarada."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_capable(ApplicationCapability.CLICK) is True
        assert app.is_capable(ApplicationCapability.SEARCH) is False

    def test_is_capable_devuelve_false_sin_capacidades(self):
        """is_capable retorna False cuando no hay capacidades declaradas."""
        app = ApplicationKnowledge(name="Vacia", type="application")
        assert app.is_capable(ApplicationCapability.OPEN) is False

    def test_is_capability_available_true_con_ejecutable_real(self):
        """is_capability_available True cuando capacidad declarada y app disponible."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        assert app.is_available() is True
        assert app.is_capability_available(ApplicationCapability.OPEN) is True
        assert app.is_capability_available(ApplicationCapability.CLICK) is True

    def test_is_capability_available_false_con_ejecutable_inexistente(self):
        """is_capability_available False cuando app no disponible en runtime."""
        app = _real_app_knowledge("Fantasma", executable="noexiste.exe")
        assert app.is_available() is False
        assert app.is_capable(ApplicationCapability.OPEN) is True  # declarada
        assert app.is_capability_available(ApplicationCapability.OPEN) is False  # no disponible

    def test_get_ui_element_por_nombre(self):
        """get_ui_element recupera un elemento por su nombre."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        elem = app.get_ui_element("main_window")
        assert elem is not None
        assert elem.name == "main_window"
        assert elem.type == "window"
        assert elem.is_calibrated() is True

    def test_get_ui_element_inexistente_retorna_none(self):
        """get_ui_element retorna None para nombre no registrado."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        assert app.get_ui_element("boton_inexistente") is None

    def test_get_calibrated_elements_vacio_sin_registro_en_coordinate_manager(self):
        """get_calibrated_elements retorna lista vacia cuando la app no tiene
        recursos registrados en el CoordinateManager (macros_coords.json).
        Esto es comportamiento real: UIElement.con coordenadas no basta;
        se requiere registro previo en el gestor de calibracion."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        calibrated = app.get_calibrated_elements()
        # Sin registro en CoordinateManager, no hay elementos calibrados
        assert calibrated == []

    def test_is_calibrated_funciona_independientemente_de_coordinate_manager(self):
        """is_calibrated() de UIElement solo verifica coordenadas locales,
        no depende del CoordinateManager. Un elemento con coordenadas validas
        reporta calibrado aunque no este en macros_coords.json."""
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        elem = app.get_ui_element("main_window")
        assert elem is not None
        assert elem.is_calibrated() is True
        # Pero get_calibrated_elements() (que consulta CoordinateManager) retorna vacio
        assert app.get_calibrated_elements() == []

    def test_get_observed_facts_vacio_sin_metadata(self):
        """get_observed_facts retorna dict vacio sin metadata de hechos observados."""
        app = ApplicationKnowledge(name="Test", type="application")
        assert app.get_observed_facts() == {}

    def test_get_inferred_data_vacio_sin_metadata(self):
        """get_inferred_data retorna dict vacio sin metadata de datos inferidos."""
        app = ApplicationKnowledge(name="Test", type="application")
        assert app.get_inferred_data() == {}

    def test_observed_facts_y_inferred_data_en_metadata(self):
        """Los hechos observados y datos inferidos se guardan en metadata."""
        app = ApplicationKnowledge(
            name="Descubierta",
            type="utility",
            executable="descubierta.exe",
            metadata={
                "observed_facts": {"exe_path": r"C:\Descubierta\app.exe", "pid": 42},
                "inferred_data": {"tipo_por_extension": "utilidad", "confianza": 0.6},
            },
        )
        assert app.get_observed_facts() == {"exe_path": r"C:\Descubierta\app.exe", "pid": 42}
        assert app.get_inferred_data() == {"tipo_por_extension": "utilidad", "confianza": 0.6}

    def test_get_unverified_capabilities(self):
        """get_unverified_capabilities retorna capacidades declaradas pero no disponibles."""
        app = _real_app_knowledge("Fantasma", executable="noexiste.exe")
        unverified = app.get_unverified_capabilities()
        # OPEN y CLICK están declaradas pero la app no está disponible
        assert len(unverified) == 2
        assert all(c.capability in (ApplicationCapability.OPEN, ApplicationCapability.CLICK) for c in unverified)


# ---------------------------------------------------------------------------
# TESTS: ApplicationManager con aplicaciones reales
# ---------------------------------------------------------------------------

class TestApplicationManagerReal:
    """Verifica ApplicationManager con nombres y aplicaciones reales."""

    def test_register_application_registra_app_real(self):
        """register_application inserta una app real en memoria y la expone."""
        manager = _make_manager()
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        result = manager.register_application(app)
        assert result is True
        assert manager.get_application("Notepad") is app
        assert manager.get_application("notepad") is app

    def test_register_application_evita_duplicados(self):
        """Re-registrar la misma app retorna False y no duplica."""
        manager = _make_manager()
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        manager.register_application(app)
        resultado2 = manager.register_application(app)
        assert resultado2 is False
        assert list(manager.applications.keys()).count("notepad") == 1

    def test_resolve_application_exacto(self):
        """resolve_application encuentra la app por nombre normalizado exacto."""
        manager = _make_manager()
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        manager.register_application(app)
        resultado = manager.resolve_application("Notepad")
        assert resultado.app is app
        assert resultado.confidence == 1.0
        assert resultado.method == "exact_normalized"

    def test_resolve_application_case_insensitive(self):
        """resolve_application distingue mayusculas/minusculas tras normalizacion."""
        manager = _make_manager()
        app = _real_app_knowledge("Notepad", executable="notepad.exe")
        manager.register_application(app)
        resultado = manager.resolve_application("NOTEPAD")
        assert resultado.app is app
        assert resultado.confidence == 1.0

    def test_resolve_application_no_encontrado(self):
        """resolve_application retorna app=None para nombre inexistente."""
        manager = _make_manager()
        resultado = manager.resolve_application("AppQueNoExiste12345")
        assert resultado.app is None
        assert resultado.confidence == 0.0
        assert resultado.method == "none"

    def test_normalize_name_apps_conocidas(self):
        """_normalize_name normaliza nombres de aplicaciones conocidas."""
        manager = _make_manager()
        assert ApplicationManager._normalize_name("Google Chrome") == "chrome"
        assert ApplicationManager._normalize_name("Microsoft Edge") == "edge"
        assert ApplicationManager._normalize_name("Bloc de Notas") == "notepad"
        assert ApplicationManager._normalize_name("Calculadora") == "calculator"

    def test_get_application_manager_global_tiene_chrome_y_spotify(self):
        """El gestor global ya tiene Chrome y Spotify cargados."""
        manager = get_application_manager()
        assert manager.get_application("Chrome") is not None
        assert manager.get_application("Spotify") is not None


# ---------------------------------------------------------------------------
# TESTS: register_discovered_application no persiste en entities.json
# ---------------------------------------------------------------------------

class TestRegisterDiscoveredNoPersist:
    """Verifica que register_discovered_application NO llama a save_entity."""

    def test_registra_solo_en_memoria_sin_save_entity(self):
        """register_discovered_application no persiste en entities.json."""
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager
        assert isinstance(mm, _FakeMemoryManager)

        app = manager.register_discovered_application(
            name="AppDescubiertaReal",
            type="utility",
            executable=r"C:\AppDescubiertaReal\app.exe",
            observed_facts={"exe_path": r"C:\AppDescubiertaReal\app.exe", "window_title": "App"},
        )

        assert app is not None
        assert app.name == "AppDescubiertaReal"
        assert "appdescubiertareal" in manager.applications
        # save_entity NO debio llamarse -> entities.json no se altera
        assert mm.saved_entities == [], (
            "register_discovered_application no debe persistir en entities.json"
        )

    def test_app_descubierta_recuperable_por_nombre_normalizado(self):
        """La app descubierta se recupera con get_application y clave normalizada."""
        manager = _make_manager()
        manager.register_discovered_application(name="Mi App Descubierta", type="browser")
        recuperada = manager.get_application("Mi App Descubierta")
        assert recuperada is not None
        assert recuperada.name == "Mi App Descubierta"
        assert recuperada.type == "browser"

    def test_metadata_marca_discovered_temporary(self):
        """La app descubierta marca discovered=True, temporary=True, source=discovery."""
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="AppDesc", type="utility",
            observed_facts={"exe": r"C:\AppDesc\app.exe"},
        )
        md = app.metadata or {}
        assert md.get("discovered") is True
        assert md.get("temporary") is True
        assert md.get("source") == "discovery"

    def test_no_sobrescribe_app_de_catalogo_existente(self):
        """Una descubierta con nombre de app de catalogo no sobrescribe la existente."""
        manager = _make_manager()
        chrome = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome.exe",
        )
        manager.register_application(chrome)
        mm: _FakeMemoryManager = manager.memory_manager
        entidades_antes = len(mm.saved_entities)

        app = manager.register_discovered_application(
            name="Chrome", type="browser",
            observed_facts={"origen": "descubrimiento_en_runtime"},
        )
        assert app is chrome  # se conserva la entrada previa
        assert manager.applications["chrome"] is chrome
        assert len(mm.saved_entities) == entidades_antes

    def test_nueva_descuberta_sin_conflicto_se_registra(self):
        """Nombre y alias nuevos sin conflicto: se registra normalmente sin save_entity."""
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager
        entidades_antes = len(mm.saved_entities)

        app = manager.register_discovered_application(
            name="AppUnicaDescubierta", type="utility",
            metadata={"aliases": ["unica_alias"]},
            observed_facts={"exe": r"C:\AppUnica\app.exe"},
        )
        assert app.name == "AppUnicaDescubierta"
        assert manager.get_application("AppUnicaDescubierta") is app
        assert manager.get_application("unica_alias") is app
        assert len(mm.saved_entities) == entidades_antes


# ---------------------------------------------------------------------------
# TESTS: Flujo completo real: descubrimiento -> resolucion -> capacidad -> elemento UI
# ---------------------------------------------------------------------------

class TestFlujoCompletoReal:
    """Verifica el flujo completo: descubre app -> resuelve -> verifica capacidad -> elemento UI calibrado."""

    def test_flujo_descubierta_a_elemento_calibrado(self):
        """Una app descubierta puede resolverse, tiene capacidad OPEN y un elemento UI calibrado."""
        manager = _make_manager()
        app = manager.register_discovered_application(
            name="AppDePrueba",
            type="utility",
            executable="notepad.exe",
            observed_facts={"exe_path": r"C:\Windows\system32\notepad.exe"},
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_app",
                    description="Abre AppDePrueba",
                    required_ui_elements=[],
                    preconditions=["app_closed"],
                    effects=["app_open"],
                    cost=5.0,
                ),
            ],
            ui_elements=[
                UIElement(
                    name="ventana_principal",
                    type="window",
                    description="Ventana principal",
                    required_capability=ApplicationCapability.OPEN,
                    coordinates={"x": 0, "y": 0, "width": 1024, "height": 768},
                    screen=0,
                ),
            ],
        )

        # 1. Se recupera por nombre normalizado
        recuperada = manager.get_application("AppDePrueba")
        assert recuperada is app

        # 2. La capacidad OPEN esta declarada
        assert app.is_capable(ApplicationCapability.OPEN) is True

        # 3. El ejecutable real (notepad.exe) esta disponible
        assert app.is_available() is True
        assert app.is_capability_available(ApplicationCapability.OPEN) is True

        # 4. Hay un elemento UI calibrado con coordenadas reales
        elem = app.get_ui_element("ventana_principal")
        assert elem is not None
        assert elem.is_calibrated() is True
        assert elem.coordinates == {"x": 0, "y": 0, "width": 1024, "height": 768}

        # 5. No se persiste en entities.json
        mm: _FakeMemoryManager = manager.memory_manager
        assert mm.saved_entities == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])