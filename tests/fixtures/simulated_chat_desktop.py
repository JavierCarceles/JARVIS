# -*- coding: ascii -*-
"""
Escritorio simulado con una aplicacion de chat (solo para tests unitarios).

Es una maquina de estados que responde a CLICS EN COORDENADAS como una app
real: el clic solo tiene efecto si cae dentro de la caja del control, y el
arbol de accesibilidad y las cajas cambian segun la pantalla. Asi se prueba el
explorador y el navegador sin Windows, incluido el caso negativo (una
coordenada guardada que ya no apunta al control debe detectarse).

Pantallas: nav "Chats" / "Ajustes".
- Chats: lista de contactos (`contactos`, por defecto Manolito y Lucia; se
  conserva al reiniciar la app). Al seleccionar uno se abre su
  chat: titulo, historial, campo "Mensaje" y boton "Enviar". No se puede
  deseleccionar (solo reiniciando la app).
- Ajustes: pestanas "General" / "Avisos" y un boton "Borrar historial" que la
  politica nunca debe pulsar.
Registro de eventos (`events`): la verdad independiente de lo que ocurrio.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.desktop.accessibility_model import AccessibilityNode, AccessibilityTree
from src.desktop.platform_contract import PlatformResult, PointerPosition, Rect, WindowInfo

CLIENT = (100.0, 100.0, 1100.0, 800.0)  # area cliente (escritorio)


class SimulatedChatDesktop:
    desktop_space = "DESKTOP_PIXELS"
    platform_name = "simulado"

    def __init__(self) -> None:
        self.pid = 4242
        self.window_id = 1000
        self.pointer = (0.0, 0.0)
        self.events: List[Dict[str, Any]] = []
        self.launches = 0
        self.offset = (0.0, 0.0)  # desplazamiento de la ventana (para recalcular cajas)
        # Lista de contactos del "servidor": sobrevive a los reinicios de la app
        # (un contacto nuevo arriba desplaza a los demas, como en una app real).
        self.contactos: List[str] = ["Manolito", "Lucia"]
        self._reset_state()

    # ------------------------------------------------------------ app

    def _reset_state(self) -> None:
        self.nav = "Chats"
        self.contact: Optional[str] = None
        self.tab = "General"
        self.focused: Optional[str] = None
        self.draft = ""
        self.messages: Dict[str, List[str]] = {nombre: [] for nombre in self.contactos}

    def restart(self) -> Tuple[int, int]:
        """Reinicio de la app propia: ventana nueva en el estado inicial."""
        self.launches += 1
        self.window_id += 1
        self._reset_state()
        self.events.append({"tipo": "reinicio"})
        return self.window_id, self.pid

    def _box(self, l: float, t: float, r: float, b: float) -> Rect:
        ox, oy = self.offset
        return Rect(CLIENT[0] + l + ox, CLIENT[1] + t + oy, CLIENT[0] + r + ox, CLIENT[1] + b + oy)

    def _controls(self) -> List[Dict[str, Any]]:
        """Controles visibles: id, rol, nombre, acciones, caja (relativa al cliente), padre."""
        c: List[Dict[str, Any]] = [
            {"id": "nav", "role": "List", "name": "Secciones", "actions": [], "box": (0, 0, 200, 700), "parent": "root"},
            {"id": "nav_chats", "role": "ListItem", "name": "Chats", "actions": ["select"], "box": (10, 10, 190, 50), "parent": "nav"},
            {"id": "nav_ajustes", "role": "ListItem", "name": "Ajustes", "actions": ["select"], "box": (10, 60, 190, 100), "parent": "nav"},
        ]
        if self.nav == "Chats":
            c.append({"id": "contactos", "role": "List", "name": "Contactos", "actions": [], "box": (210, 0, 450, 700), "parent": "root"})
            for i, nombre in enumerate(self.contactos):
                c.append({"id": "contacto_%s" % nombre.lower(), "role": "ListItem", "name": nombre, "actions": ["select"],
                          "box": (220, 10 + 50 * i, 440, 50 + 50 * i), "parent": "contactos"})
            if self.contact:
                c.append({"id": "titulo_chat", "role": "Text", "name": "Chat con %s" % self.contact, "actions": [],
                          "box": (460, 10, 980, 40), "parent": "root"})
                c.append({"id": "historial", "role": "List", "name": "Historial", "actions": [], "box": (460, 50, 980, 600), "parent": "root"})
                for j, texto in enumerate(self.messages.setdefault(self.contact, [])):
                    c.append({"id": "msg_%d" % j, "role": "ListItem", "name": texto, "actions": [],
                              "box": (470, 60 + 30 * j, 970, 85 + 30 * j), "parent": "historial"})
                c.append({"id": "campo_mensaje", "role": "Edit", "name": "Mensaje", "actions": ["set_value", "focus"],
                          "box": (460, 620, 880, 660), "parent": "root"})
                c.append({"id": "boton_enviar", "role": "Button", "name": "Enviar", "actions": ["invoke"],
                          "box": (890, 620, 980, 660), "parent": "root"})
        else:
            c.append({"id": "pestanas", "role": "Tab", "name": "Pestanas", "actions": [], "box": (210, 0, 980, 40), "parent": "root"})
            c.append({"id": "tab_general", "role": "TabItem", "name": "General", "actions": ["select"], "box": (220, 5, 320, 35), "parent": "pestanas"})
            c.append({"id": "tab_avisos", "role": "TabItem", "name": "Avisos", "actions": ["select"], "box": (330, 5, 430, 35), "parent": "pestanas"})
            c.append({"id": "texto_pestana", "role": "Text", "name": "Pagina %s" % self.tab, "actions": [], "box": (220, 60, 600, 90), "parent": "root"})
            c.append({"id": "borrar", "role": "Button", "name": "Borrar historial", "actions": ["invoke"], "box": (220, 100, 400, 140), "parent": "root"})
        return c

    def _hit(self, x: float, y: float) -> Optional[Dict[str, Any]]:
        best = None
        for control in self._controls():
            box = self._box(*control["box"])
            if box.left <= x < box.right and box.top <= y < box.bottom:
                if best is None or (box.width * box.height) < best[1]:
                    best = (control, box.width * box.height)
        return best[0] if best else None

    def _activate(self, control: Dict[str, Any]) -> None:
        cid = control["id"]
        if cid == "nav_chats":
            self.nav = "Chats"
        elif cid == "nav_ajustes":
            self.nav = "Ajustes"
        elif cid.startswith("contacto_"):
            self.contact = control["name"]
            self.events.append({"tipo": "contacto_seleccionado", "contacto": self.contact})
        elif cid == "tab_general":
            self.tab = "General"
        elif cid == "tab_avisos":
            self.tab = "Avisos"
        elif cid == "campo_mensaje":
            self.focused = "campo_mensaje"
        elif cid == "boton_enviar":
            if self.contact and self.draft:
                self.messages[self.contact].append(self.draft)
                self.events.append({"tipo": "mensaje_enviado", "contacto": self.contact, "texto": self.draft})
                self.draft = ""
        elif cid == "borrar":
            self.events.append({"tipo": "borrado"})

    # ------------------------------------------------------------ contrato

    def _window(self) -> WindowInfo:
        ox, oy = self.offset
        client = Rect(CLIENT[0] + ox, CLIENT[1] + oy, CLIENT[2] + ox, CLIENT[3] + oy)
        return WindowInfo(window_id=self.window_id, pid=self.pid, title="Chat simulado", bounds=client,
                          client_bounds=client, frame_bounds=client, is_visible=True, is_foreground=True)

    def get_window(self, window_id: int) -> PlatformResult:
        if int(window_id) != self.window_id:
            return PlatformResult(False)
        return PlatformResult.success(self._window())

    def list_windows(self, pid: Any = None, visible_only: bool = True, app_identity: Any = None) -> PlatformResult:
        return PlatformResult.success([self._window()])

    def get_foreground_window(self) -> PlatformResult:
        return PlatformResult.success(self._window())

    def is_foreground(self, window_id: int) -> bool:
        return int(window_id) == self.window_id

    def get_accessibility_tree(self, window_id: int, pid: Any = None) -> PlatformResult:
        if int(window_id) != self.window_id:
            return PlatformResult(False)
        depth = {"root": 0}
        nodes = [AccessibilityNode(node_id="root", control_type="window", native_role="Window", name="Chat simulado",
                                   bbox=self._box(0, 0, 1000, 700), enabled=True, visible=True, depth=0,
                                   window_id=self.window_id, pid=self.pid, source="uia")]
        for control in self._controls():
            d = depth[control["parent"]] + 1
            depth[control["id"]] = d
            nodes.append(AccessibilityNode(
                node_id=control["id"], control_type=control["role"].lower(), native_role=control["role"],
                name=control["name"], identifier=control["id"], bbox=self._box(*control["box"]), enabled=True,
                visible=True, actions=list(control["actions"]), parent_id=control["parent"], depth=d,
                window_id=self.window_id, pid=self.pid, source="uia",
            ))
        return PlatformResult.success(AccessibilityTree(window_id=self.window_id, pid=self.pid, source="uia",
                                                        nodes=nodes, root_id="root"))

    def perform_accessibility_action(self, window_id: int, node_id: str, action: str) -> PlatformResult:
        for control in self._controls():
            if control["id"] == node_id:
                self._activate(control)
                return PlatformResult.success(None)
        return PlatformResult(False)

    def move_pointer(self, x: float, y: float) -> PlatformResult:
        self.pointer = (float(x), float(y))
        return PlatformResult.success(PointerPosition(x=x, y=y))

    def get_pointer_position(self) -> PlatformResult:
        return PlatformResult.success(PointerPosition(x=self.pointer[0], y=self.pointer[1]))

    def window_at_point(self, x: float, y: float) -> PlatformResult:
        return PlatformResult.success(self._window())

    def element_at_point(self, x: float, y: float) -> PlatformResult:
        control = self._hit(x, y)
        if control is None:
            return PlatformResult.success(None)
        return PlatformResult.success(AccessibilityNode(
            node_id=control["id"], control_type=control["role"].lower(), native_role=control["role"],
            name=control["name"], bbox=self._box(*control["box"]), enabled=True, visible=True,
        ))

    def click(self, button: str = "left", count: int = 1) -> PlatformResult:
        control = self._hit(*self.pointer)
        self.events.append({"tipo": "clic", "punto": list(self.pointer), "control": control["id"] if control else None})
        if control is not None:
            self._activate(control)
        return PlatformResult.success(None)

    def type_text(self, text: str) -> PlatformResult:
        if self.focused != "campo_mensaje":
            return PlatformResult(False)
        self.draft += str(text)
        return PlatformResult.success(None)

    def press_keys(self, keys: Any) -> PlatformResult:
        return PlatformResult.success(None)

    def close_window(self, window_id: int) -> PlatformResult:
        return PlatformResult.success(None)
