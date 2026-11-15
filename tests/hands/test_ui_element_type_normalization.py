# -*- coding: utf-8 -*-
"""Tests unitarios de normalizacion del tipo de elemento detectado por Vision
— unidad 3.8.6.3.2 (FASE 3.8.6 — CALIBRACION).

Objetivo: verificar que el tipo de elemento detectado por Vision (cadena libre
generada por el LLM, D-UI-TYPE-FREE-FORM) se normaliza al conjunto canonico
que ya valida ``coordinate_manager.validate_resource_for_action``, sin
inventar tipos nuevos. Un tipo desconocido se resuelve al tipo generico
``"element"``, que el contrato de validacion acepta para enfoque (``focus_``)
y clic (``click_``) y rechaza para escritura (``type_``).

No abre ventanas, no lanza procesos, no toca pantalla. Pruebas puras de
logica de datos sobre implementacion real.
"""

import pytest

from src.utils.ui_element_model import (
    CANONICAL_ELEMENT_TYPES,
    normalize_element_type,
)


# ---------------------------------------------------------------------------
# Casos canonicos: pasan sin alteracion (normalizados a minusculas)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tipo_entrada, tipo_esperado",
    [
        ("button", "button"),
        ("input", "input"),
        ("address_bar", "address_bar"),
        ("field", "field"),
        ("text", "text"),
        ("element", "element"),
        ("link", "link"),
        ("menu", "menu"),
        ("checkbox", "checkbox"),
        ("radio", "radio"),
        ("select", "select"),
        ("toolbar", "toolbar"),
    ],
)
def test_tipo_canonico_pasa_sin_alteracion(tipo_entrada, tipo_esperado):
    assert normalize_element_type(tipo_entrada) == tipo_esperado


# ---------------------------------------------------------------------------
# Insensibilidad a mayusculas/minusculas y espacios
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tipo_entrada, tipo_esperado",
    [
        ("BUTTON", "button"),
        ("BuTtOn", "button"),
        ("  Btn  ", "button"),
        ("INPUT", "input"),
        ("TEXTBOX", "input"),
        ("COMBO", "select"),
        ("TOOLBAR", "toolbar"),
        ("ADDRESS_BAR", "address_bar"),
    ],
)
def test_normalizacion_es_insensible_a_caso_y_espacios(tipo_entrada, tipo_esperado):
    assert normalize_element_type(tipo_entrada) == tipo_esperado


# ---------------------------------------------------------------------------
# Alias en espanol (el prompt de Vision esta en espanol)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tipo_entrada, tipo_esperado",
    [
        ("boton", "button"),
        ("botón", "button"),
        ("campo de texto", "input"),
        ("campo", "field"),
        ("entrada", "input"),
        ("texto", "text"),
        ("enlace", "link"),
        ("menu", "menu"),
        ("menú", "menu"),
        ("casilla", "checkbox"),
        ("casilla de verificación", "checkbox"),
        ("radio", "radio"),
        ("botón de radio", "radio"),
        ("select", "select"),
        ("desplegable", "select"),
        ("lista desplegable", "select"),
        ("barra de herramientas", "toolbar"),
    ],
)
def test_alias_en_espanol_se_normalizan(tipo_entrada, tipo_esperado):
    assert normalize_element_type(tipo_entrada) == tipo_esperado


# ---------------------------------------------------------------------------
# Tipos desconocidos -> tipo generico "element" (nunca se inventan tipos)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tipo_entrada",
    [
        "desconocido",
        "icono",
        "imagen",
        "slider",
        "switch",
        "pestaña",
        "otro",
        "other",
        "unknown",
        "",
        None,
        "   ",
        123,
        [],
    ],
)
def test_tipo_desconocido_se_resuelve_al_generico_element(tipo_entrada):
    assert normalize_element_type(tipo_entrada) == "element"


# ---------------------------------------------------------------------------
# No se inventan tipos: todo resultado pertenece al conjunto canonico
# ---------------------------------------------------------------------------
def test_siempre_devuelve_un_tipo_canonico():
    muestras = [
        "button", "Boton", "campo de texto", "desplegable", "desconocido_xyz",
        None, "", "icono", "otro", "text", "address_bar",
    ]
    for muestra in muestras:
        resultado = normalize_element_type(muestra)
        assert isinstance(resultado, str)
        assert resultado != ""
        assert resultado in CANONICAL_ELEMENT_TYPES


# ---------------------------------------------------------------------------
# Vinculacion con el contrato real de validacion (coordinate_manager)
# ---------------------------------------------------------------------------
def test_tipos_normalizados_son_validos_para_validate_resource_for_action():
    """Los tipos que Vision normaliza deben ser aceptados por
    ``validate_resource_for_action`` para las acciones correspondientes.

    ``element`` es el tipo generico: valido para focus_/click_ y rechazado
    para type_ (no se puede escribir en un elemento generico), coherente con
    el contrato real.
    """
    from src.hands.coordinate_manager import (
        CalibrationStrategy,
        CoordinateManager,
        ResourceType,
        UIResource,
    )

    manager = CoordinateManager()

    def _registrar(resource_id: str, element_type: str) -> None:
        recurso = UIResource(
            id=resource_id,
            name=resource_id,
            resource_type=ResourceType.ELEMENT,
            application="app_prueba",
            element_type=element_type,
            calibration_strategy=CalibrationStrategy.VISUAL_DETECTION,
            calibrated_coordinates={1: (100, 100)},
            calibrated_regions={},
            confidence=0.9,
            is_available=True,
            is_calibrated=True,
        )
        manager.ui_resources[resource_id] = recurso

    # focus_ acepta input/address_bar/field/text/element
    for tipo in ["input", "address_bar", "field", "text", "element"]:
        _registrar(f"foco_{tipo}", tipo)
        assert manager.validate_resource_for_action("focus_element", f"foco_{tipo}") is True

    # click_ acepta button/link/menu/checkbox/radio/select/toolbar/element
    for tipo in [
        "button", "link", "menu", "checkbox", "radio", "select", "toolbar",
        "element",
    ]:
        _registrar(f"clic_{tipo}", tipo)
        assert manager.validate_resource_for_action("click_element", f"clic_{tipo}") is True

    # type_ acepta input/address_bar/field/text; rechaza "element" (generico)
    for tipo in ["input", "address_bar", "field", "text"]:
        _registrar(f"escribe_{tipo}", tipo)
        assert manager.validate_resource_for_action("type_in_element", f"escribe_{tipo}") is True
    _registrar("escribe_element", "element")
    assert manager.validate_resource_for_action("type_in_element", "escribe_element") is False

    # Acciones fuera de foco/clic/escribir aceptan cualquier tipo (incluso generico)
    _registrar("otro_element", "element")
    assert manager.validate_resource_for_action("scroll_element", "otro_element") is True

    # Recurso inexistente o inusable -> False (contrato real)
    assert manager.validate_resource_for_action("click_element", "no_existe") is False


def test_tipo_desconocido_de_vision_pasa_a_element_y_es_aceptado_por_foco_y_clic():
    """Un tipo desconocido detectado por Vision se normaliza a "element" y,
    por tanto, el contrato de validacion lo acepta para foco y clic
    (tipo generico) sin inventar un tipo nuevo."""
    assert normalize_element_type("control_raro_de_terceros") == "element"

    from src.hands.coordinate_manager import (
        CalibrationStrategy,
        CoordinateManager,
        ResourceType,
        UIResource,
    )

    manager = CoordinateManager()
    recurso = UIResource(
        id="res_generico",
        name="res_generico",
        resource_type=ResourceType.ELEMENT,
        application="app_prueba",
        element_type=normalize_element_type("control_raro_de_terceros"),
        calibration_strategy=CalibrationStrategy.VISUAL_DETECTION,
        calibrated_coordinates={1: (50, 50)},
        calibrated_regions={},
        confidence=0.5,
        is_available=True,
        is_calibrated=True,
    )
    manager.ui_resources["res_generico"] = recurso

    assert manager.validate_resource_for_action("focus_element", "res_generico") is True
    assert manager.validate_resource_for_action("click_element", "res_generico") is True
    # Escribir en un elemento generico no esta soportado por el contrato.
    assert manager.validate_resource_for_action("type_in_element", "res_generico") is False
