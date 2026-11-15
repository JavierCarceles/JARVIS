# -*- coding: utf-8 -*-
"""Tests unitarios de preservacion del campo description en elementos UI
detectados por Vision — unidad 3.8.6.3.1 (FASE 3.8.6 — CALIBRACION).

Objetivo: verificar que un elemento detectado por Vision conserva su
`description` a traves del flujo Vision -> UIElement -> serializacion ->
registro, sin perder datos.

No abre ventanas, no lanza procesos, no toca pantalla. Pruebas puras de
logica de datos sobre implementacion real.
"""

import pytest

from src.eyes.vision import UIElement as VisionUIElement
from src.hands.applications_core import UIElement as CoreUIElement
from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    get_application_manager,
    register_custom_application,
    _serialize_ui_element,
)
from src.utils.ui_element_model import UIElementData


# ---------------------------------------------------------------------------
# UIElementData (modelo canonico) conserva description
# ---------------------------------------------------------------------------
def test_ui_element_data_tiene_description_con_default_vacio():
    elemento = UIElementData(name="btn_aceptar", type="button")
    assert elemento.description == ""
    assert elemento.name == "btn_aceptar"
    assert elemento.type == "button"


def test_ui_element_data_acepta_description_no_vacio():
    elemento = UIElementData(
        name="btn_aceptar",
        type="button",
        description="Boton para aceptar terminos y condiciones",
    )
    assert elemento.description == "Boton para aceptar terminos y condiciones"


def test_ui_element_data_to_dict_incluye_description():
    elemento = UIElementData(
        name="campo_usuario", type="input", description="Ingresa tu nombre de usuario"
    )
    data = elemento.to_dict()
    assert data["description"] == "Ingresa tu nombre de usuario"


def test_ui_element_data_from_dict_conserva_description():
    origen = {
        "name": "btn_cancelar",
        "type": "button",
        "description": "Cancela la operacion actual",
        "text": "Cancelar",
    }
    elemento = UIElementData.from_dict(origen)
    assert elemento.description == "Cancela la operacion actual"


# ---------------------------------------------------------------------------
# UIElement de applications_core (dataclass) conserva description
# ---------------------------------------------------------------------------
def test_core_ui_element_tiene_description_con_default_vacio():
    elemento = CoreUIElement(name="menu_archivo", type="menu")
    assert elemento.description == ""
    assert elemento.name == "menu_archivo"
    assert elemento.type == "menu"


def test_core_ui_element_acepta_description_no_vacio():
    elemento = CoreUIElement(
        name="menu_archivo",
        type="menu",
        description="Menu principal con opciones de archivo",
    )
    assert elemento.description == "Menu principal con opciones de archivo"


# ---------------------------------------------------------------------------
# UIElement de vision.py (hereda de UIElementData) conserva description
# ---------------------------------------------------------------------------
def test_vision_ui_element_hereda_de_ui_element_data():
    assert issubclass(VisionUIElement, UIElementData)


def test_vision_ui_element_acepta_description():
    elemento = VisionUIElement(
        name="btn_enviar",
        type="button",
        description="Envia el formulario de contacto",
        text="Enviar",
        bbox=[100, 200, 200, 250],
        center=[150, 225],
        interactive=True,
        confidence=0.9,
    )
    assert elemento.description == "Envia el formulario de contacto"
    assert elemento.name == "btn_enviar"
    assert elemento.type == "button"
    assert elemento.confidence == 0.9


def test_vision_ui_element_description_default_vacio():
    elemento = VisionUIElement(
        name="btn_x", type="button", text="X", bbox=[0, 0, 10, 10], center=[5, 5]
    )
    assert elemento.description == ""


# ---------------------------------------------------------------------------
# Serializacion y reconstruccion conservan description
# ---------------------------------------------------------------------------
def test_serialize_ui_element_conserva_description():
    elemento = CoreUIElement(
        name="lbl_estado",
        type="label",
        description="Muestra el estado actual de la aplicacion",
    )
    data = _serialize_ui_element(elemento)
    assert data["description"] == "Muestra el estado actual de la aplicacion"
    assert data["name"] == "lbl_estado"
    assert data["type"] == "label"


def test_reconstruct_ui_elements_conserva_description():
    items = [
        {
            "name": "chk_terminos",
            "type": "checkbox",
            "description": "Acepto los terminos y condiciones",
            "text": "Acepto terminos",
        },
        {
            "name": "btn_continuar",
            "type": "button",
            "description": "Avanza al siguiente paso",
            "text": "Continuar",
        },
    ]
    elementos = ApplicationManager._reconstruct_ui_elements(items)
    assert len(elementos) == 2
    assert elementos[0].description == "Acepto los terminos y condiciones"
    assert elementos[1].description == "Avanza al siguiente paso"


def test_reconstruct_ui_elements_sin_description_devuelve_vacio():
    items = [{"name": "lbl_foo", "type": "label", "text": "Foo"}]
    elementos = ApplicationManager._reconstruct_ui_elements(items)
    assert len(elementos) == 1
    assert elementos[0].description == ""


# ---------------------------------------------------------------------------
# register_custom_application no falla en silencio con description
# ---------------------------------------------------------------------------
def test_register_custom_application_preserva_description_en_ui_elements():
    manager = get_application_manager()

    app_config = {
        "name": "AppPruebaDesc",
        "type": "utilidad",
        "ui_elements": [
            {
                "name": "btn_principal",
                "type": "button",
                "description": "Boton principal de la aplicacion de prueba",
                "required_capability": "open",
            }
        ],
    }

    ok = register_custom_application(app_config)
    assert ok is True

    clave = manager._normalize_name("AppPruebaDesc")
    app = manager.applications[clave]
    assert app is not None
    assert len(app.ui_elements) == 1
    assert app.ui_elements[0].description == "Boton principal de la aplicacion de prueba"
    assert app.ui_elements[0].name == "btn_principal"
    assert app.ui_elements[0].type == "button"


def test_register_custom_application_ui_element_sin_description_default_vacio():
    manager = get_application_manager()

    app_config = {
        "name": "AppSinDesc",
        "type": "utilidad",
        "ui_elements": [
            {
                "name": "btn_x",
                "type": "button",
                "text": "X",
            }
        ],
    }

    ok = register_custom_application(app_config)
    assert ok is True

    clave = manager._normalize_name("AppSinDesc")
    app = manager.applications[clave]
    assert app.ui_elements[0].description == ""


# ---------------------------------------------------------------------------
# Schema del modelo de vision incluye description
# ---------------------------------------------------------------------------
def test_vision_ui_element_model_fields_incluye_description():
    campos = VisionUIElement.model_fields
    assert "description" in campos
    assert campos["description"].default == ""
