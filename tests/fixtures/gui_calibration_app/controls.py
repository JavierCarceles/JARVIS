# -*- coding: ascii -*-
"""
Declaracion de los controles de la fixture de calibracion GUI.

Cada entrada de CONTROL_SPECS define un control expuesto por la ventana:
  id        : identificador estable (objectName y accessibleName del control).
  kind      : tipo de control (button, link, label, field, checkbox, radio,
              dropdown, list, tabs, scroll, menu, popup, group, drawing).
  label     : texto visible del control (cadena ASCII; sin acentos por regla
              del proyecto).
  geometry  : geometria de referencia [x, y, ancho, alto] en pixeles del area
              cliente de la ventana, en el tamanio nominal (1200x800). None
              para controles sin geometria fija (menus, popups).
  action    : nombre de la accion inocua instrumentada que se dispara al
              interactuar con el control (None si no tiene accion propia).

Ninguna accion escribe en disco, ni abre procesos, ni modifica datos del
usuario: todas solo incrementan un contador de memoria.
"""

TAMANIO_NOMINAL = [1200, 800]

CONTROL_SPECS = [
    {"id": "btn_aceptar", "kind": "button", "label": "Aceptar",
     "geometry": [20, 20, 100, 32], "action": "accion_btn_aceptar"},
    {"id": "btn_cancelar", "kind": "button", "label": "Cancelar",
     "geometry": [130, 20, 100, 32], "action": "accion_btn_cancelar"},
    {"id": "lbl_estado", "kind": "label", "label": "Estado de la prueba",
     "geometry": [20, 70, 200, 24], "action": None},
    {"id": "lnk_ayuda", "kind": "link", "label": "Ayuda",
     "geometry": [20, 105, 60, 24], "action": "accion_lnk_ayuda"},
    {"id": "txt_nombre", "kind": "field", "label": "",
     "geometry": [20, 145, 200, 32], "action": "accion_txt_nombre"},
    {"id": "chk_terminos", "kind": "checkbox", "label": "Aceptar terminos",
     "geometry": [20, 190, 150, 28], "action": "accion_chk_terminos"},
    {"id": "rdo_opcion_a", "kind": "radio", "label": "Opcion A",
     "geometry": [20, 228, 90, 24], "action": "accion_rdo_opcion_a"},
    {"id": "rdo_opcion_b", "kind": "radio", "label": "Opcion B",
     "geometry": [120, 228, 90, 24], "action": "accion_rdo_opcion_b"},
    {"id": "cbo_categoria", "kind": "dropdown", "label": "",
     "geometry": [20, 265, 180, 32], "action": "accion_cbo_categoria"},
    {"id": "lst_items", "kind": "list", "label": "",
     "geometry": [20, 310, 200, 120], "action": "accion_lst_items"},
    {"id": "tab_principal", "kind": "tabs", "label": "",
     "geometry": [240, 20, 320, 250], "action": "accion_tab_principal"},
    {"id": "scr_area", "kind": "scroll", "label": "",
     "geometry": [570, 20, 320, 400], "action": "accion_scr_area"},
    {"id": "menu_archivo", "kind": "menu", "label": "Menu: Archivo",
     "geometry": [20, 440, 140, 32], "action": "accion_menu_archivo"},
    {"id": "popup_info", "kind": "popup", "label": "Abrir popup",
     "geometry": [240, 560, 140, 32], "action": "accion_popup_info"},
    {"id": "grp_anidado", "kind": "group", "label": "Grupo anidado",
     "geometry": [240, 310, 320, 230], "action": None},
    {"id": "canvas_mano", "kind": "drawing", "label": "",
     "geometry": [900, 20, 200, 200], "action": "accion_canvas_mano"},
]

CONTROL_BY_ID = {item["id"]: item for item in CONTROL_SPECS}

ACCIONES_INOCUAS = sorted(
    {item["action"] for item in CONTROL_SPECS if item["action"]}
)

# IDs de controles que NO deben ser reportados como accionables por los
# detectores (dibujado a mano sin accesibilidad).
CONTROLES_SIN_ACCESIBILIDAD = ["canvas_mano"]
