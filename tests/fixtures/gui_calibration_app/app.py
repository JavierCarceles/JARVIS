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

Para la matriz controlada (3.8.6.10.4) soporta variantes de estado
deterministas, leidas de ``FixtureConfig`` o de variables de entorno, para
lanzar cada variante como un proceso independiente desde las pruebas:
  estado de ventana (maximizada / restaurada)
  tema (claro / oscuro)
  tamano de fuente
  zoom interno (escala las geometrias de los controles)
  menu abierto (menu desplegable visible)
  scroll desplazado (area de scrolleo movida)
  control dinamico visible / oculto
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QFont, QPalette, QPainter
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

from .controls import ACCIONES_INOCUAS, CONTROL_BY_ID, CONTROL_SPECS, CONTROL_DINAMICO_SPEC
from .truth_ground import (
    ACTION_COUNTS_PATH,
    TRUTH_GROUND_PATH,
    construir_truth_ground,
    escribir_action_counts,
    escribir_truth_ground,
)

TAMANIO_VENTANA = [1200, 800]

# Variables de entorno que configuran una variante de la matriz controlada.
ENV_ESTADO_VENTANA = "FIXTURE_ESTADO_VENTANA"
ENV_TEMA = "FIXTURE_TEMA"
ENV_TAMANIO_FUENTE = "FIXTURE_TAMANIO_FUENTE"
ENV_ZOOM_INTERNO = "FIXTURE_ZOOM_INTERNO"
ENV_MENU_ABIERTO = "FIXTURE_MENU_ABIERTO"
ENV_SCROLL_DESPLAZADO = "FIXTURE_SCROLL_DESPLAZADO"
ENV_CONTROL_DINAMICO_VISIBLE = "FIXTURE_CONTROL_DINAMICO_VISIBLE"


class FixtureConfig:
    """Configuracion de una variante de la matriz controlada (3.8.6.10.4).

    Los valores por defecto replican la linea base de las unidades
    3.8.6.10.1 a 3.8.6.10.3 (ventana maximizada, tema claro, fuente 9,
    zoom 1.0, menu cerrado, sin scroll, control dinamico oculto).
    """

    def __init__(
        self,
        estado_ventana: str = "maximizada",
        tema: str = "claro",
        tamano_fuente: int = 9,
        zoom_interno: float = 1.0,
        menu_abierto: bool = False,
        scroll_desplazado: bool = False,
        control_dinamico_visible: bool = False,
    ) -> None:
        self.estado_ventana = estado_ventana
        self.tema = tema
        self.tamano_fuente = tamano_fuente
        self.zoom_interno = zoom_interno
        self.menu_abierto = menu_abierto
        self.scroll_desplazado = scroll_desplazado
        self.control_dinamico_visible = control_dinamico_visible

    @classmethod
    def desde_entorno(cls) -> "FixtureConfig":
        """Lee la configuracion desde las variables de entorno."""

        def env_bool(nombre: str, defecto: bool) -> bool:
            valor = os.environ.get(nombre)
            if valor is None:
                return defecto
            return valor.strip().lower() in ("1", "true", "si", "yes", "on")

        def env_int(nombre: str, defecto: int) -> int:
            valor = os.environ.get(nombre)
            if valor is None:
                return defecto
            try:
                return int(valor)
            except ValueError:
                return defecto

        def env_float(nombre: str, defecto: float) -> float:
            valor = os.environ.get(nombre)
            if valor is None:
                return defecto
            try:
                return float(valor)
            except ValueError:
                return defecto

        return cls(
            estado_ventana=os.environ.get(ENV_ESTADO_VENTANA, "maximizada"),
            tema=os.environ.get(ENV_TEMA, "claro"),
            tamano_fuente=env_int(ENV_TAMANIO_FUENTE, 9),
            zoom_interno=env_float(ENV_ZOOM_INTERNO, 1.0),
            menu_abierto=env_bool(ENV_MENU_ABIERTO, False),
            scroll_desplazado=env_bool(ENV_SCROLL_DESPLAZADO, False),
            control_dinamico_visible=env_bool(ENV_CONTROL_DINAMICO_VISIBLE, False),
        )

    def a_dict(self) -> Dict[str, Any]:
        return {
            "estado_ventana": self.estado_ventana,
            "tema": self.tema,
            "tamano_fuente": self.tamano_fuente,
            "zoom_interno": self.zoom_interno,
            "menu_abierto": self.menu_abierto,
            "scroll_desplazado": self.scroll_desplazado,
            "control_dinamico_visible": self.control_dinamico_visible,
        }


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

    def __init__(self, tamanio=None, config=None):
        super().__init__()
        self.setWindowTitle("JARVIS GUI Calibration Fixture")
        if tamanio is None:
            tamanio = TAMANIO_VENTANA
        self.config = config if config is not None else FixtureConfig.desde_entorno()
        self._tamanio_base = list(tamanio)
        self._action_counts: Dict[str, int] = {accion: 0 for accion in ACCIONES_INOCUAS}
        self._control_widgets: Dict[str, object] = {}
        self._menu_widget = None
        self._scroll_widget = None
        self._dinamico_widget = None

        self._aplicar_tema()
        self._aplicar_fuente()

        self._central = QWidget()
        self._central.setObjectName("area_central")
        self._central.setAccessibleName("area_central")
        self.setCentralWidget(self._central)
        # Posicionamiento absoluto: la geometria de referencia es estable
        # independientemente del tamanio de la ventana.
        self._central.setLayout(None)

        self._construir_controles()
        self._aplicar_zoom_y_geometrias()
        # Los estados que requieren la ventana visible se aplican tras el
        # primer show() mediante un temporizador (menu abierto, scroll).
        QTimer.singleShot(100, self._aplicar_estados_post_show)
        self._escribir_archivos_estado()

    # ------------------------------------------------------------------ configuracion
    def _aplicar_tema(self):
        """Aplica el tema claro u oscuro a la aplicacion."""
        app = QApplication.instance()
        if app is None:
            return
        if self.config.tema == "oscuro":
            paleta = QPalette()
            paleta.setColor(QPalette.Window, QColor(45, 45, 45))
            paleta.setColor(QPalette.WindowText, Qt.white)
            paleta.setColor(QPalette.Base, QColor(30, 30, 30))
            paleta.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
            paleta.setColor(QPalette.ToolTipBase, Qt.white)
            paleta.setColor(QPalette.ToolTipText, Qt.white)
            paleta.setColor(QPalette.Text, Qt.white)
            paleta.setColor(QPalette.Button, QColor(45, 45, 45))
            paleta.setColor(QPalette.ButtonText, Qt.white)
            paleta.setColor(QPalette.BrightText, Qt.red)
            paleta.setColor(QPalette.Link, QColor(42, 130, 218))
            paleta.setColor(QPalette.Highlight, QColor(42, 130, 218))
            paleta.setColor(QPalette.HighlightedText, Qt.white)
            app.setPalette(paleta)
        else:
            app.setPalette(QPalette())

    def _aplicar_fuente(self):
        """Aplica el tamano de fuente configurado a la aplicacion."""
        app = QApplication.instance()
        if app is None:
            return
        fuente = app.font()
        fuente.setPointSize(max(1, int(self.config.tamano_fuente)))
        app.setFont(fuente)

    def _aplicar_zoom_y_geometrias(self):
        """Reescala las geometrias de todos los controles por el zoom interno."""
        zoom = float(self.config.zoom_interno)
        for control_id, widget in self._control_widgets.items():
            espec = CONTROL_BY_ID.get(control_id)
            if espec is None or espec.get("geometry") is None:
                continue
            geo = espec["geometry"]
            widget.setGeometry(
                int(round(geo[0] * zoom)),
                int(round(geo[1] * zoom)),
                int(round(geo[2] * zoom)),
                int(round(geo[3] * zoom)),
            )
        if self._dinamico_widget is not None and CONTROL_DINAMICO_SPEC.get("geometry"):
            geo = CONTROL_DINAMICO_SPEC["geometry"]
            self._dinamico_widget.setGeometry(
                int(round(geo[0] * zoom)),
                int(round(geo[1] * zoom)),
                int(round(geo[2] * zoom)),
                int(round(geo[3] * zoom)),
            )

    def _aplicar_estados_post_show(self):
        """Aplica estados que requieren la ventana ya visible (menu, scroll)."""
        if self.config.menu_abierto and self._menu_widget is not None:
            try:
                self._menu_widget.showMenu()
            except Exception:
                pass
        if self.config.scroll_desplazado and self._scroll_widget is not None:
            try:
                barra = self._scroll_widget.verticalScrollBar()
                barra.setValue(barra.maximum())
            except Exception:
                pass

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
        self._menu_widget = btn

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

    def _crear_control_dinamico(self):
        """Crea el control dinamico opcional solo si la variante lo pide."""
        if not self.config.control_dinamico_visible:
            return
        btn = QPushButton(CONTROL_DINAMICO_SPEC["label"], self._central)
        self._control("ctrl_dinamico", btn, CONTROL_DINAMICO_SPEC["action"])
        self._dinamico_widget = btn

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
            lay.addWidget(QLabel("Linea %d" % (i + 1)))
        scroll.setWidget(contenido)
        scroll.verticalScrollBar().valueChanged.connect(
            lambda _valor: self._disparar("accion_scr_area")
        )
        self._control("scr_area", scroll, "accion_scr_area")
        self._colocar("scr_area", x_ref["scr_area"])
        self._scroll_widget = scroll

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
        canvas.setObjectName("canvas_mano")
        self._control_widgets["canvas_mano"] = canvas
        self._colocar("canvas_mano", x_ref["canvas_mano"])

        # Control dinamico opcional
        self._crear_control_dinamico()

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

    def config_dict(self):
        return {
            "estado_ventana": self.config.estado_ventana,
            "tema": self.config.tema,
            "tamano_fuente": self.config.tamano_fuente,
            "zoom_interno": self.config.zoom_interno,
            "menu_abierto": self.config.menu_abierto,
            "scroll_desplazado": self.config.scroll_desplazado,
            "control_dinamico_visible": self.config.control_dinamico_visible,
        }

    # ------------------------------------------------------------------ estado
    def _escribir_archivos_estado(self):
        escribir_truth_ground(zoom_interno=self.config.zoom_interno,
                              incluir_dinamico=self.config.control_dinamico_visible)
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
        return get_truth_ground(zoom_interno=self.config.zoom_interno,
                                incluir_dinamico=self.config.control_dinamico_visible)


def crear_aplicacion(config=None):
    """Crea (o reutiliza) la QApplication y devuelve la ventana de la fixture."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    ventana = CalibrationAppWindow(config=config)
    return app, ventana


def main():
    app, ventana = crear_aplicacion()
    config = ventana.config
    if config.estado_ventana == "maximizada":
        ventana.showMaximized()
    else:
        ventana.resize(TAMANIO_VENTANA[0], TAMANIO_VENTANA[1])
        ventana.show()
    app.exec()


if __name__ == "__main__":
    main()
