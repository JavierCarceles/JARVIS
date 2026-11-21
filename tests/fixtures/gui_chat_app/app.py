# -*- coding: ascii -*-
"""
Aplicacion de chat propia para probar la calibracion en profundidad (Qt).

Imita la navegacion de una app de mensajeria sin red ni datos reales:
- panel "Secciones": Chats / Ajustes (QListWidget: elementos seleccionables);
- Chats: lista de contactos (Manolito, Lucia, Pedro); al seleccionar uno se
  muestra su chat: titulo "Chat con <nombre>", historial, campo "Mensaje" y
  boton "Enviar";
- Ajustes: pestanas General / Avisos y un boton "Borrar historial" que la
  politica de exploracion nunca debe pulsar.

Registro de eventos (verdad independiente de JARVIS): cada evento se anade
como una linea JSON al fichero de la variable de entorno
``JARVIS_CHAT_FIXTURE_EVENTOS`` (si no esta, no se registra):
  {"tipo": "iniciada"}, {"tipo": "seccion", "seccion": "Ajustes"},
  {"tipo": "contacto_seleccionado", "contacto": "Manolito"},
  {"tipo": "mensaje_enviado", "contacto": "Manolito", "texto": "hola"},
  {"tipo": "pestana", "pestana": "Avisos"}, {"tipo": "borrado"}.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

TITULO = "JARVIS Chat Fixture"
ENV_EVENTOS = "JARVIS_CHAT_FIXTURE_EVENTOS"
CONTACTOS = ("Manolito", "Lucia", "Pedro")


def registrar_evento(evento: Dict[str, Any], ruta: Optional[str] = None) -> None:
    ruta = ruta if ruta is not None else os.environ.get(ENV_EVENTOS)
    if not ruta:
        return
    datos = dict(evento)
    datos["t"] = round(time.time(), 3)
    with open(ruta, "a", encoding="utf-8") as fichero:
        fichero.write(json.dumps(datos, ensure_ascii=True) + "\n")


class ChatWindow(QMainWindow):
    def __init__(self, ruta_eventos: Optional[str] = None) -> None:
        super().__init__()
        self.ruta_eventos = ruta_eventos
        self.setWindowTitle(TITULO)
        self.resize(1200, 800)
        self.mensajes: Dict[str, list] = {c: [] for c in CONTACTOS}
        self.contacto: Optional[str] = None

        central = QWidget()
        fila = QHBoxLayout(central)

        self.secciones = QListWidget()
        self.secciones.setObjectName("secciones")
        self.secciones.setAccessibleName("Secciones")
        self.secciones.addItems(["Chats", "Ajustes"])
        self.secciones.setCurrentRow(0)
        self.secciones.setFixedWidth(180)
        fila.addWidget(self.secciones)

        self.paginas = QStackedWidget()
        self.paginas.addWidget(self._pagina_chats())
        self.paginas.addWidget(self._pagina_ajustes())
        fila.addWidget(self.paginas, 1)
        self.setCentralWidget(central)

        self.secciones.currentRowChanged.connect(self._cambiar_seccion)
        self._evento({"tipo": "iniciada"})

    def _evento(self, evento: Dict[str, Any]) -> None:
        registrar_evento(evento, self.ruta_eventos)

    def _pagina_chats(self) -> QWidget:
        pagina = QWidget()
        fila = QHBoxLayout(pagina)
        self.contactos = QListWidget()
        self.contactos.setObjectName("contactos")
        self.contactos.setAccessibleName("Contactos")
        self.contactos.addItems(list(CONTACTOS))
        self.contactos.setFixedWidth(240)
        self.contactos.currentTextChanged.connect(self._abrir_chat)
        fila.addWidget(self.contactos)

        self.panel_chat = QWidget()
        columna = QVBoxLayout(self.panel_chat)
        self.titulo_chat = QLabel("")
        self.titulo_chat.setObjectName("titulo_chat")
        columna.addWidget(self.titulo_chat)
        self.historial = QListWidget()
        self.historial.setObjectName("historial")
        self.historial.setAccessibleName("Historial")
        columna.addWidget(self.historial, 1)
        entrada = QHBoxLayout()
        self.campo = QLineEdit()
        self.campo.setObjectName("campo_mensaje")
        self.campo.setAccessibleName("Mensaje")
        self.campo.setPlaceholderText("Escribe un mensaje")
        entrada.addWidget(self.campo, 1)
        self.enviar = QPushButton("Enviar")
        self.enviar.setObjectName("boton_enviar")
        self.enviar.clicked.connect(self._enviar)
        entrada.addWidget(self.enviar)
        columna.addLayout(entrada)
        self.panel_chat.setVisible(False)
        fila.addWidget(self.panel_chat, 1)
        return pagina

    def _pagina_ajustes(self) -> QWidget:
        pagina = QWidget()
        columna = QVBoxLayout(pagina)
        self.pestanas = QTabWidget()
        self.pestanas.setObjectName("pestanas_ajustes")
        general = QWidget()
        QVBoxLayout(general).addWidget(QLabel("Opciones generales"))
        avisos = QWidget()
        QVBoxLayout(avisos).addWidget(QLabel("Opciones de avisos"))
        self.pestanas.addTab(general, "General")
        self.pestanas.addTab(avisos, "Avisos")
        self.pestanas.currentChanged.connect(
            lambda i: self._evento({"tipo": "pestana", "pestana": self.pestanas.tabText(i)})
        )
        columna.addWidget(self.pestanas, 1)
        self.borrar = QPushButton("Borrar historial")
        self.borrar.setObjectName("boton_borrar")
        self.borrar.clicked.connect(lambda: self._evento({"tipo": "borrado"}))
        columna.addWidget(self.borrar)
        return pagina

    def _cambiar_seccion(self, fila: int) -> None:
        self.paginas.setCurrentIndex(max(0, fila))
        self._evento({"tipo": "seccion", "seccion": self.secciones.item(fila).text() if fila >= 0 else ""})

    def _abrir_chat(self, nombre: str) -> None:
        if not nombre:
            return
        self.contacto = nombre
        self.titulo_chat.setText("Chat con %s" % nombre)
        self.historial.clear()
        self.historial.addItems(self.mensajes[nombre])
        self.panel_chat.setVisible(True)
        self._evento({"tipo": "contacto_seleccionado", "contacto": nombre})

    def _enviar(self) -> None:
        texto = self.campo.text()
        if not self.contacto or not texto:
            return
        self.mensajes[self.contacto].append(texto)
        self.historial.addItem(texto)
        self.campo.clear()
        self._evento({"tipo": "mensaje_enviado", "contacto": self.contacto, "texto": texto})


def crear_aplicacion(ruta_eventos: Optional[str] = None):
    app = QApplication.instance() or QApplication([])
    ventana = ChatWindow(ruta_eventos)
    ventana.show()
    return app, ventana
