# -*- coding: ascii -*-
"""
Ventana principal de la fixture de calibracion GUI.

Construye una ventana real (Qt/PySide6) con uno de cada tipo de control
relevante para calibracion (boton, enlace, etiqueta, campo, casilla, radio,
desplegable, lista, pestanas, scroll, menu, popup, grupo, dibujo a mano).
Cada control expone identificador estable, geometria de referencia y una
accion inocua instrumentada que solo incrementa un contador de memoria.
Incluye un control dibujado a mano SIN accesibilidad para probar que los
detectores no lo marcan como accionable por falso positivo.
"""

from __future__ import annotations

import os
from typing import Dict

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QToolButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .controls import ACCIONES_INOCUAS, CONTROL_BY_ID, CONTROL_SPECS
from .truth_ground import (
    ACTION_COUNTS_PATH,
    TRUTH_GROUND_PATH,
    escribir_action_counts,
    escribir_truth_ground,
)

TAMANIO_VENTANA = [1200, 800]


class HandDrawnControl(QWidget):
    """Control dibujado a mano SIN accesibilidad (no se fija accessibleName).

    Se usa para verificar que los detectores no lo reportan como un control
    accionable con identificador, ya que no expone nombre ni rol semantico.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(200, 200))
        self._presionado = False

    def paintEvent(self, event):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        fondo = QColor("#2d6a4f") if self._presionado else QColor("#52b788")
        pintor.fillRect(self.rect(), fondo)
        pintor.setPen(Qt.white)
        pintor.drawText(self.rect(), Qt.AlignCenter, "Dibujo\nsin\naccesibilidad")

    def mousePressEvent(self, event):
        self._presionado = True
        self.update()
        ventana = self.window()
        if isinstance(ventana, CalibrationAppWindow):
            ventana._disparar("accion_canvas_mano")
        super().mousePressEvent(event)


class CalibrationAppWindow(QMainWindow):
    """Ventana de prueba con todos los controles de calibracion."""

    def __init__(self, tamanio=None):
        super().__init__()
        self.setWindowTitle("JARVIS GUI Calibration Fixture")
        if tamanio is None:
            tamanio = TAMANIO_VENTANA
        self.resize(tamanio[0], tamanio[1])

        self._action_counts: Dict[str, int] = {accion: 0 for accion in ACCIONES_INOCUAS}
        self._control_widgets: Dict[str, object] = {}

        self._central = QWidget()
        self._central.setObjectName("area_central")
        self._central.setAccessibleName("area_central")
        self.setCentralWidget(self._central)
        # Posicionamiento absoluto: la geometria de referencia es estable
        # independientemente del tamanio de la ventana.
        self._central.setLayout(None)

        self._construir_controles()
        self._escribir_archivos_estado()

    # ------------------------------------------------------------------ UI
    def _construir_menu_archivo(self):
        """menu_archivo es un QToolButton con menu desplegable (QMenu).

        Es un widget real con identificador, geometria y accion; al hacer clic
        se dispara la accion inocua y ademas se abre un menu desplegable real
        para cubrir el tipo de control "menu".
        """
        btn = QToolButton(self._central)
        btn.setText("Menu: Archivo")
        btn.setObjectName("menu_archivo")
        btn.setAccessibleName("menu_archivo")
        menu = QMenu(btn)
        accion = menu.addAction("Acerca de")
        accion.triggered.connect(lambda: self._disparar("accion_menu_archivo"))
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        btn.clicked.connect(lambda: self._disparar("accion_menu_archivo"))
        self._control("menu_archivo", btn, "accion_menu_archivo")

    def _control(self, control_id, widget, action=None):
        widget.setObjectName(control_id)
        widget.setAccessibleName(control_id)
        self._control_widgets[control_id] = widget
        widget.setParent(self._central)
        widget.show()
        if action is not None:
            self._conectar_accion(widget, action)
        return widget

    def _conectar_accion(self, widget, action):
        """Conecta la senal natural de cada control a su accion inocua."""
        try:
            if isinstance(widget, QPushButton):
                widget.clicked.connect(lambda _chk=False: self._disparar(action))
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(lambda _estado: self._disparar(action))
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(lambda _texto: self._disparar(action))
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(lambda _idx: self._disparar(action))
            elif isinstance(widget, QListWidget):
                widget.itemClicked.connect(lambda _item: self._disparar(action))
            elif isinstance(widget, QTabWidget):
                widget.currentChanged.connect(lambda _idx: self._disparar(action))
            else:
                widget.mousePressEvent = self._hacer_presion(widget, action)
        except Exception:
            pass

    def _hacer_presion(self, widget, action):
        original = widget.mousePressEvent

        def presion(event):
            self._disparar(action)
            if original is not None:
                original(event)

        return presion

    def _colocar(self, control_id, geometria):
        """Coloca un widget ya creado en su geometria de referencia."""
        item = CONTROL_BY_ID[control_id]
        widget = self._control_widgets[control_id]
        if geometria is None:
            return
        widget.setGeometry(geometria[0], geometria[1], geometria[2], geometria[3])

    def _construir_controles(self):
        x_ref = {item["id"]: item["geometry"] for item in CONTROL_SPECS}
        self._construir_menu_archivo()
        self._colocar("menu_archivo", x_ref["menu_archivo"])

        # Botones
        btn_aceptar = QPushButton("Aceptar", self._central)
        self._control("btn_aceptar", btn_aceptar, "accion_btn_aceptar")
        self._colocar("btn_aceptar", x_ref["btn_aceptar"])

        btn_cancelar = QPushButton("Cancelar", self._central)
        self._control("btn_cancelar", btn_cancelar, "accion_btn_cancelar")
        self._colocar("btn_cancelar", x_ref["btn_cancelar"])

        # Etiqueta
        lbl = QLabel("Estado de la prueba", self._central)
        self._control("lbl_estado", lbl)
        self._colocar("lbl_estado", x_ref["lbl_estado"])

        # Enlace (QLabel con vinculo)
        lnk = QLabel("<a href='#'>Ayuda</a>", self._central)
        lnk.setOpenExternalLinks(False)
        lnk.linkActivated.connect(lambda _url: self._disparar("accion_lnk_ayuda"))
        self._control("lnk_ayuda", lnk, "accion_lnk_ayuda")
        self._colocar("lnk_ayuda", x_ref["lnk_ayuda"])

        # Campo de texto
        txt = QLineEdit(self._central)
        self._control("txt_nombre", txt, "accion_txt_nombre")
        self._colocar("txt_nombre", x_ref["txt_nombre"])

        # Casilla
        chk = QCheckBox("Aceptar terminos", self._central)
        self._control("chk_terminos", chk, "accion_chk_terminos")
        self._colocar("chk_terminos", x_ref["chk_terminos"])

        # Radios (grupo de exclusion mutua)
        grupo_radios = QButtonGroup(self)
        grupo_radios.setExclusive(True)
        rdo_a = QRadioButton("Opcion A", self._central)
        rdo_b = QRadioButton("Opcion B", self._central)
        grupo_radios.addButton(rdo_a)
        grupo_radios.addButton(rdo_b)
        rdo_a.toggled.connect(lambda activado: self._disparar("accion_rdo_opcion_a") if activado else None)
        rdo_b.toggled.connect(lambda activado: self._disparar("accion_rdo_opcion_b") if activado else None)
        self._control("rdo_opcion_a", rdo_a, "accion_rdo_opcion_a")
        self._control("rdo_opcion_b", rdo_b, "accion_rdo_opcion_b")
        self._colocar("rdo_opcion_a", x_ref["rdo_opcion_a"])
        self._colocar("rdo_opcion_b", x_ref["rdo_opcion_b"])

        # Desplegable
        cbo = QComboBox(self._central)
        cbo.addItems(["Categoria 1", "Categoria 2", "Categoria 3"])
        self._control("cbo_categoria", cbo, "accion_cbo_categoria")
        self._colocar("cbo_categoria", x_ref["cbo_categoria"])

        # Lista
        lst = QListWidget(self._central)
        lst.addItems(["Item 1", "Item 2", "Item 3", "Item 4"])
        self._control("lst_items", lst, "accion_lst_items")
        self._colocar("lst_items", x_ref["lst_items"])

        # Pestanas
        tabs = QTabWidget(self._central)
        tabs.addTab(QWidget(), "Pestana 1")
        tabs.addTab(QWidget(), "Pestana 2")
        self._control("tab_principal", tabs, "accion_tab_principal")
        self._colocar("tab_principal", x_ref["tab_principal"])

        # Area con scroll
        scroll = QScrollArea(self._central)
        scroll.setWidgetResizable(True)
        contenido = QWidget()
        contenido.setFixedSize(QSize(300, 600))
        lay = QVBoxLayout(contenido)
        for i in range(15):
            lay.addWidget(QLabel(f"Linea {i + 1}"))
        scroll.setWidget(contenido)
        scroll.verticalScrollBar().valueChanged.connect(
            lambda _valor: self._disparar("accion_scr_area")
        )
        self._control("scr_area", scroll, "accion_scr_area")
        self._colocar("scr_area", x_ref["scr_area"])

        # Popup (boton que abre un dialogo modal)
        btn_popup = QPushButton("Abrir popup", self._central)
        btn_popup.clicked.connect(self._abrir_popup)
        self._control("popup_info", btn_popup, "accion_popup_info")
        self._colocar("popup_info", x_ref["popup_info"])

        # Grupo anidado (contiene controles dentro)
        grupo = QGroupBox("Grupo anidado", self._central)
        self._control("grp_anidado", grupo)
        self._colocar("grp_anidado", x_ref["grp_anidado"])
        lay_grupo = QVBoxLayout(grupo)
        chk_interno = QCheckBox("Opcion interna", grupo)
        chk_interno.setObjectName("chk_interno")
        chk_interno.setAccessibleName("chk_interno")
        btn_interno = QPushButton("Interno", grupo)
        btn_interno.setObjectName("btn_interno")
        btn_interno.setAccessibleName("btn_interno")
        btn_interno.clicked.connect(lambda: self._disparar("accion_btn_interno"))
        lay_grupo.addWidget(chk_interno)
        lay_grupo.addWidget(btn_interno)
        self._action_counts["accion_btn_interno"] = 0

        # Dibujo a mano SIN accesibilidad
        canvas = HandDrawnControl(self._central)
        # No se establece accessibleName ni objectName con el id del control,
        # para que no exporte identificacion semantica al arbol de accesibilidad.
        canvas.setObjectName("canvas_mano")
        self._control_widgets["canvas_mano"] = canvas
        self._colocar("canvas_mano", x_ref["canvas_mano"])

    def _abrir_popup(self):
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Popup de prueba")
        dialogo.setModal(True)
        botones = QDialogButtonBox(QDialogButtonBox.Ok, dialogo)
        botones.accepted.connect(lambda: (self._disparar("accion_popup_info"), dialogo.accept()))
        lay = QVBoxLayout(dialogo)
        lay.addWidget(QLabel("Este es un popup inofensivo de la fixture."))
        lay.addWidget(botones)
        dialogo.exec()

    # ------------------------------------------------------------------ acciones
    def _disparar(self, action):
        """Ejecuta una accion inocua instrumentada: solo cuenta la llamada."""
        if action in self._action_counts:
            self._action_counts[action] += 1
        escribir_action_counts(self._action_counts)

    def action_counts(self):
        return dict(self._action_counts)

    # ------------------------------------------------------------------ estado
    def _escribir_archivos_estado(self):
        escribir_truth_ground()
        escribir_action_counts(self._action_counts)

    def get_control_geometry(self, control_id):
        """Devuelve la geometria real (x,y,ancho,alto) de un control."""
        widget = self._control_widgets.get(control_id)
        if widget is None:
            return None
        rect = widget.geometry()
        return [rect.x(), rect.y(), rect.width(), rect.height()]

    def get_truth_ground(self):
        from .truth_ground import get_truth_ground
        return get_truth_ground()


def crear_aplicacion():
    """Crea (o reutiliza) la QApplication y devuelve la ventana de la fixture."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    ventana = CalibrationAppWindow()
    return app, ventana


def main():
    app, ventana = crear_aplicacion()
    ventana.show()
    app.exec()


if __name__ == "__main__":
    main()
