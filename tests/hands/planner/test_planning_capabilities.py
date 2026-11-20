# -*- coding: ascii -*-
"""
Tests de ``PlanningCapabilityService`` (src/hands/planner/planning_capabilities.py)
y de su uso desde ``ApplicationKnowledgeIntegrator``.

Comprueban que al Planner solo llegan capacidades sustentadas a la vez por:
una capacidad DECLARADA en el catalogo, una accion REAL registrada y habilitada
para el planificador, las capacidades del SO actual en estado DISPONIBLE y, si
actuan sobre la interfaz, recursos calibrados vigentes para la ventana actual.
Y que, si falta algo, se informa que falta con un codigo estable:

- capacidad declarada pero sin accion registrada (o deshabilitada para el
  Planner, o sin funcion): ``action_missing``;
- capacidad del SO sin permiso: ``permission_missing`` con instrucciones;
- capacidad del SO no soportada o no verificada: ``os_capability_unavailable``;
- elemento de interfaz sin calibracion vigente (sin ventana, sin recursos o sin
  el elemento requerido): ``element_not_calibrable``;
- capacidad no declarada (guardar, borrar, rellenar formularios, enviar...) o
  aplicacion fuera del catalogo: ``not_inferable`` (nunca se infiere por estar
  instalada).

Se sustituyen el ActionRegistry, los adaptadores del SO, el servicio de
vigencia de calibracion y el catalogo por dobles con datos conocidos; la logica
de decision es la de produccion. Multiplataforma, sin tocar data/.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from src.desktop.platform_contract import Capability, CapabilityReport, CapabilityStatus
from src.hands.planner.application_integration import ApplicationKnowledgeIntegrator
from src.hands.planner.planning_capabilities import (
    REASON_ACTION_MISSING,
    REASON_ELEMENT_NOT_CALIBRABLE,
    REASON_NOT_INFERABLE,
    REASON_OS_CAPABILITY_UNAVAILABLE,
    REASON_PERMISSION_MISSING,
    PlanningCapabilityService,
)

D = CapabilityStatus.DISPONIBLE


def _funcion(**_kwargs: Any) -> Any:
    return None


def _accion(name: str, capability: str, application: Optional[str] = None,
            effects: Optional[List[str]] = None, planner_enabled: bool = True, function: Any = _funcion) -> Any:
    return SimpleNamespace(
        name=name, capability=capability, application=application, effects=effects or [],
        planner_enabled=planner_enabled, function=function,
    )


class _Registro:
    def __init__(self, *acciones: Any) -> None:
        self.acciones = {a.name: a for a in acciones}

    def get_all_actions(self) -> Dict[str, Any]:
        return dict(self.acciones)


class _Capacidades:
    """Adaptador (escritorio o lanzamiento) con capacidades conocidas."""

    def __init__(self, estados: Dict[Capability, CapabilityStatus], instrucciones: str = "") -> None:
        self.estados = estados
        self.instrucciones = instrucciones

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        return {
            cap: CapabilityReport(cap, estado, "", self.instrucciones if estado == CapabilityStatus.SIN_PERMISO else "")
            for cap, estado in self.estados.items()
        }


class _Vigencia:
    def __init__(self, recursos: Optional[List[Dict[str, Any]]] = None) -> None:
        self.recursos = recursos or []
        self.llamadas: List[Any] = []

    def resources_for_planner(self, app_id: str, window_id: int) -> List[Dict[str, Any]]:
        self.llamadas.append((app_id, window_id))
        return list(self.recursos)


class _Catalogo:
    def __init__(self, *apps: Any) -> None:
        self.apps = {a.name.lower(): a for a in apps}

    def get_application(self, name: str) -> Any:
        return self.apps.get(str(name).lower())


def _cap(nombre: str, elementos: Optional[List[str]] = None) -> Any:
    return SimpleNamespace(capability=nombre, required_ui_elements=elementos or [])


def _app(nombre: str = "Bloc de notas", entity_id: str = "", capacidades: Optional[List[Any]] = None) -> Any:
    return SimpleNamespace(
        name=nombre,
        metadata={"entity_id": entity_id} if entity_id else {},
        capabilities=capacidades if capacidades is not None else [_cap("open")],
    )


ESCRITORIO_OK = {
    Capability.PROCESS_VERIFY: D, Capability.WINDOW_VERIFY: D, Capability.WINDOW_CONTROL: D,
    Capability.INPUT_CONTROL: D, Capability.SCREEN_CAPTURE: D, Capability.DISPLAY_ENUM: D,
}
LANZAMIENTO_OK = {
    Capability.DISCOVER: D, Capability.RESOLVE: D, Capability.PREFLIGHT: D,
    Capability.LAUNCH: D, Capability.PROCESS_VERIFY: D,
}


def _servicio(app: Any = None, acciones: Any = None, escritorio: Optional[Dict] = None,
              lanzamiento: Optional[Dict] = None, recursos: Optional[List[Dict[str, Any]]] = None,
              instrucciones: str = "") -> PlanningCapabilityService:
    return PlanningCapabilityService(
        registry=_Registro(*(acciones if acciones is not None else [
            _accion("open_application", "open_application", effects=["application_open"]),
            _accion("click_element", "click", effects=["element_clicked"]),
        ])),
        desktop=_Capacidades(escritorio if escritorio is not None else dict(ESCRITORIO_OK), instrucciones),
        launch_adapter=_Capacidades(lanzamiento if lanzamiento is not None else dict(LANZAMIENTO_OK)),
        validity=_Vigencia(recursos),
        app_manager=_Catalogo(app if app is not None else _app()),
    )


def _por_capacidad(exposiciones: Any) -> Dict[str, Any]:
    return {e.capability: e for e in exposiciones}


# ---------------------------------------------------------------------------
# Accion real + SO disponible
# ---------------------------------------------------------------------------


class TestCapacidadPlanificable:
    def test_open_con_accion_registrada_y_so_disponible_es_planificable(self):
        servicio = _servicio()
        expos = _por_capacidad(servicio.exposed_capabilities("Bloc de notas"))
        assert expos["open"].supported
        assert expos["open"].action_name == "open_application"
        assert expos["open"].expected_effects == ["application_open"]
        assert expos["open"].os_capability_status == {"launch": "DISPONIBLE", "process_verify": "DISPONIBLE"}
        assert [e.capability for e in servicio.plannable_capabilities("Bloc de notas")] == ["open"]
        assert servicio.explain_missing("Bloc de notas", "open") is None

    def test_accion_especifica_de_la_aplicacion_tiene_prioridad(self):
        app = _app(capacidades=[_cap("open")])
        servicio = _servicio(app, acciones=[
            _accion("open_application", "open_application"),
            _accion("abrir_bloc", "open", application="Bloc de notas"),
        ])
        assert _por_capacidad(servicio.exposed_capabilities("Bloc de notas"))["open"].action_name == "abrir_bloc"


class TestAccionInexistente:
    @pytest.mark.parametrize("acciones", [
        [],
        [_accion("open_application", "open_application", planner_enabled=False)],
        [_accion("open_application", "open_application", function=None)],
    ])
    def test_sin_accion_real_habilitada_es_action_missing(self, acciones):
        servicio = _servicio(acciones=acciones)
        expo = _por_capacidad(servicio.exposed_capabilities("Bloc de notas"))["open"]
        assert not expo.supported
        assert expo.reason_code == REASON_ACTION_MISSING
        assert servicio.plannable_capabilities("Bloc de notas") == []
        assert servicio.explain_missing("Bloc de notas", "open").reason_code == REASON_ACTION_MISSING


class TestCapacidadesDelSO:
    def test_sin_permiso_es_permission_missing_con_instrucciones(self):
        escritorio = dict(ESCRITORIO_OK)
        escritorio[Capability.INPUT_CONTROL] = CapabilityStatus.SIN_PERMISO
        app = _app(capacidades=[_cap("click", ["boton_guardar"])])
        servicio = _servicio(app, escritorio=escritorio, instrucciones="Conceder Accesibilidad",
                             recursos=[{"name": "boton_guardar"}])
        expo = _por_capacidad(servicio.exposed_capabilities("Bloc de notas", window_id=5))["click"]
        assert not expo.supported
        assert expo.reason_code == REASON_PERMISSION_MISSING
        falta = servicio.explain_missing("Bloc de notas", "click", window_id=5)
        assert falta.reason_code == REASON_PERMISSION_MISSING
        assert "Accesibilidad" in falta.instructions

    @pytest.mark.parametrize("estado", [CapabilityStatus.NO_SOPORTADO, CapabilityStatus.NO_VERIFICADO])
    def test_capacidad_del_so_no_disponible(self, estado):
        lanzamiento = dict(LANZAMIENTO_OK)
        lanzamiento[Capability.LAUNCH] = estado
        expo = _por_capacidad(_servicio(lanzamiento=lanzamiento).exposed_capabilities("Bloc de notas"))["open"]
        assert not expo.supported
        assert expo.reason_code == REASON_OS_CAPABILITY_UNAVAILABLE
        assert expo.os_capability_status["launch"] == estado.value


# ---------------------------------------------------------------------------
# Elementos de interfaz calibrados
# ---------------------------------------------------------------------------


class TestElementosCalibrados:
    def _app_click(self) -> Any:
        return _app(capacidades=[_cap("click", ["boton_guardar"])])

    def test_sin_ventana_actual_no_es_planificable(self):
        expo = _por_capacidad(_servicio(self._app_click()).exposed_capabilities("Bloc de notas"))["click"]
        assert not expo.supported
        assert expo.reason_code == REASON_ELEMENT_NOT_CALIBRABLE
        assert expo.requires_calibration

    def test_sin_recursos_vigentes_no_es_planificable(self):
        expo = _por_capacidad(_servicio(self._app_click(), recursos=[]).exposed_capabilities(
            "Bloc de notas", window_id=5))["click"]
        assert not expo.supported
        assert expo.reason_code == REASON_ELEMENT_NOT_CALIBRABLE

    def test_elemento_requerido_ausente_no_es_planificable(self):
        servicio = _servicio(self._app_click(), recursos=[{"name": "boton_abrir"}])
        expo = _por_capacidad(servicio.exposed_capabilities("Bloc de notas", window_id=5))["click"]
        assert not expo.supported
        assert expo.reason_code == REASON_ELEMENT_NOT_CALIBRABLE
        assert "boton_guardar" in expo.reason

    def test_con_el_elemento_calibrado_es_planificable(self):
        servicio = _servicio(self._app_click(), recursos=[{"name": "Boton Guardar", "control_id": "c1"}])
        expo = _por_capacidad(servicio.exposed_capabilities("Bloc de notas", window_id=5))["click"]
        assert expo.supported, expo.reason
        assert expo.action_name == "click_element"
        assert "boton_guardar" in expo.calibrated_resources

    def test_capacidad_de_interfaz_sin_elementos_declarados_exige_algun_recurso(self):
        app = _app(capacidades=[_cap("scroll")])
        servicio = _servicio(app, acciones=[_accion("scroll_window", "scroll")], recursos=[])
        expo = _por_capacidad(servicio.exposed_capabilities("Bloc de notas", window_id=5))["scroll"]
        assert not expo.supported
        assert expo.reason_code == REASON_ELEMENT_NOT_CALIBRABLE

    def test_recursos_se_piden_con_la_clave_de_calibracion_no_con_entity_id(self):
        app = _app(nombre="Google Chrome", entity_id="ent-123", capacidades=[_cap("click", ["omnibox"])])
        servicio = _servicio(app, recursos=[{"name": "omnibox"}])
        expo = _por_capacidad(servicio.exposed_capabilities("Google Chrome", window_id=9))["click"]
        assert expo.supported, expo.reason
        assert expo.app_id == "ent-123"
        assert servicio._get_validity().llamadas == [("chrome", 9)]


# ---------------------------------------------------------------------------
# Nada se infiere por estar instalada
# ---------------------------------------------------------------------------


class TestNoInferible:
    @pytest.mark.parametrize("capacidad", ["save", "delete", "fill_form", "send", "submit"])
    def test_capacidad_sensible_no_declarada_no_se_infiere(self, capacidad):
        servicio = _servicio(acciones=[
            _accion("open_application", "open_application"),
            _accion("accion_%s" % capacidad, capacidad),
        ])
        assert capacidad not in _por_capacidad(servicio.exposed_capabilities("Bloc de notas"))
        falta = servicio.explain_missing("Bloc de notas", capacidad)
        assert falta.reason_code == REASON_NOT_INFERABLE
        assert "sensible" in falta.detail

    def test_aplicacion_fuera_del_catalogo(self):
        servicio = _servicio()
        assert servicio.exposed_capabilities("Photoshop") == []
        assert servicio.plannable_capabilities("Photoshop") == []
        assert servicio.explain_missing("Photoshop", "open").reason_code == REASON_NOT_INFERABLE


# ---------------------------------------------------------------------------
# Integrador de conocimiento de aplicaciones
# ---------------------------------------------------------------------------


def _integrador() -> ApplicationKnowledgeIntegrator:
    # Sin __init__: no se carga el catalogo real ni la memoria.
    return ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)


class TestIntegrador:
    def test_get_plannable_capabilities_devuelve_solo_las_planificables(self):
        app = _app(capacidades=[_cap("open"), _cap("click", ["boton_guardar"])])
        resultado = _integrador().get_plannable_capabilities("Bloc de notas", service=_servicio(app))
        assert [r["capability"] for r in resultado] == ["open"]

    def test_explain_missing_capability_devuelve_el_motivo(self):
        motivo = _integrador().explain_missing_capability("Bloc de notas", "delete", service=_servicio())
        assert motivo["reason_code"] == REASON_NOT_INFERABLE

    def test_filter_plannable_nodes_descarta_capacidades_no_planificables_y_anota_la_accion(self):
        app = _app(capacidades=[_cap("open"), _cap("click", ["boton_guardar"])])
        nodos = [
            SimpleNamespace(metadata={"source": "application_knowledge", "capability": "open", "application": "Bloc de notas"}),
            SimpleNamespace(metadata={"source": "application_knowledge", "capability": "click", "application": "Bloc de notas"}),
            SimpleNamespace(metadata={"source": "application_knowledge", "type": "application"}),
        ]
        filtrados = _integrador().filter_plannable_nodes(nodos, service=_servicio(app))
        assert len(filtrados) == 2
        assert filtrados[0].metadata["action"] == "open_application"
        assert filtrados[0].metadata["plannable"] is True
        assert "capability" not in filtrados[1].metadata
