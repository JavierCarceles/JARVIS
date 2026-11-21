# -*- coding: ascii -*-
"""
Calibracion en profundidad verificable (multiplataforma, escritorio simulado).

Comprueba con una app de chat simulada que responde a clics en coordenadas:
- la exploracion en modo clic construye estados con profundidad y caminos
  desde la raiz, y cada transicion lleva evidencia del clic real (punto,
  elemento bajo el puntero, estado antes/despues);
- un clic sin efecto queda registrado como "sin efecto", no como transicion;
- las transiciones sin vuelta propia (abrir una conversacion) vuelven a la
  raiz reiniciando la app propia;
- el boton "Borrar historial" no se pulsa nunca;
- el JSON guarda las coordenadas de cada elemento por estado;
- reproducir cada camino con las coordenadas GUARDADAS llega al estado
  esperado; con la ventana movida tambien (cajas relativas al area cliente);
- una coordenada corrompida se detecta como fallo (no se informa exito);
- "mandar hola a Manolito" con el mapa: el registro de eventos de la app
  confirma el contacto y el mensaje, y el historial muestra "hola".
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.hands.calibration.ui_exploration import (
    ACTION_NAVIGATE,
    DeepUIExplorer,
    ExplorationBudget,
    ExplorationSafetyPolicy,
)
from src.hands.calibration.ui_navigation_map import (
    COORDS_LIVE,
    COORDS_STORED,
    UINavigator,
    build_navigation_map,
    find_elements,
    load_navigation_map,
    save_navigation_map,
    verify_all_paths,
)

from tests.fixtures.simulated_chat_desktop import SimulatedChatDesktop


def _explorador(escritorio):
    return DeepUIExplorer(
        adapter=escritorio,
        policy=ExplorationSafetyPolicy(allow_navigation=True),
        budget=ExplorationBudget(max_depth=3, max_states=20, max_seconds=60, settle_timeout=0.05, settle_poll=0.01),
        app_id="chat_simulado",
        interaction="click",
        reset_root=escritorio.restart,
    )


def _estado_con(datos, texto):
    for state_id, estado in datos["states"].items():
        if any(texto == v for v in estado["visible_elements"]) or any(
            texto == e.get("name") for e in estado["elements"]
        ):
            yield state_id, estado


def _estado_por_visible(datos, nombre_visible):
    for state_id, estado in datos["states"].items():
        if nombre_visible in estado["visible_elements"]:
            return state_id
    return None


class TestExploracionYMapa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.escritorio = SimulatedChatDesktop()
        cls.explorador = _explorador(cls.escritorio)
        cls.resultado = cls.explorador.explore(cls.escritorio.window_id, cls.escritorio.pid)
        cls.datos = build_navigation_map(cls.resultado, "chat_simulado", "maquina-prueba")

    def test_exploracion_completa_sin_abortar(self):
        self.assertFalse(self.resultado.aborted, self.resultado.abort_reason)
        self.assertGreaterEqual(len(self.datos["states"]), 5, list(self.datos["states"]))

    def test_estados_con_profundidad_y_camino_desde_la_raiz(self):
        chat = _estado_por_visible(self.datos, "titulo_chat")
        avisos = None
        for state_id, estado in self.datos["states"].items():
            if "texto_pestana" in estado["visible_elements"] and estado["depth"] == 2:
                avisos = state_id
        self.assertIsNotNone(chat)
        self.assertEqual(self.datos["states"][chat]["depth"], 1)
        self.assertIsNotNone(avisos, "debe existir un estado de profundidad 2 (Ajustes -> Avisos)")
        camino = self.datos["states"][avisos]["path_from_root"]
        self.assertEqual([p["element_ref"]["name"] for p in camino], ["Ajustes", "Avisos"])
        self.assertEqual(camino[0]["from_state"], self.datos["root_state_id"])

    def test_cada_transicion_tiene_evidencia_de_clic_real(self):
        self.assertTrue(self.datos["transitions"])
        for transicion in self.datos["transitions"]:
            evidencia = transicion["evidence"]
            self.assertEqual(evidencia["method"], "click", transicion)
            self.assertTrue(evidencia["pointer_ok"], transicion)
            self.assertEqual(len(evidencia["click_point"]), 2)
            # changed refleja lo observado: distinto estado <=> changed.
            self.assertEqual(
                evidencia["changed"], evidencia["before_state"] != evidencia["after_state"], transicion
            )
            self.assertEqual(transicion["from_state"], evidencia["before_state"])
            self.assertEqual(transicion["to_state"], evidencia["after_state"])
        self.assertTrue(any(t["evidence"]["changed"] for t in self.datos["transitions"]))

    def test_clics_reales_registrados_por_la_aplicacion(self):
        clics = [e for e in self.escritorio.events if e["tipo"] == "clic"]
        self.assertTrue(clics)
        self.assertTrue(all(e["control"] is not None for e in clics), "ningun clic debe caer fuera de un control")

    def test_clic_sin_efecto_queda_marcado_y_no_crea_estados(self):
        # "Chats" ya esta seleccionado en la raiz: clicarlo no cambia nada.
        sin_efecto = self.datos["exploration"]["no_effect"]
        self.assertTrue(any(e["element_ref"]["name"] == "Chats" for e in sin_efecto), sin_efecto)
        bucle = [t for t in self.datos["transitions"] if t["element_ref"]["name"] == "Chats"
                 and t["from_state"] == self.datos["root_state_id"]]
        self.assertTrue(bucle)
        self.assertFalse(bucle[0]["evidence"]["changed"])
        self.assertEqual(bucle[0]["to_state"], bucle[0]["from_state"])

    def test_vuelta_por_reinicio_tras_abrir_conversacion(self):
        conversaciones = [t for t in self.datos["transitions"]
                          if t["element_ref"]["name"] in ("Manolito", "Lucia")]
        self.assertTrue(conversaciones)
        for transicion in conversaciones:
            self.assertTrue(transicion["verified_return"], transicion)
            self.assertIn("reset", transicion["return_action"])
            self.assertEqual(transicion["action"], ACTION_NAVIGATE)
        self.assertGreaterEqual(self.datos["exploration"]["resets"], 2)

    def test_borrar_nunca_se_pulsa(self):
        self.assertFalse([e for e in self.escritorio.events if e["tipo"] == "borrado"])

    def test_json_guarda_coordenadas_de_los_elementos(self):
        chat = _estado_por_visible(self.datos, "titulo_chat")
        elementos = {e["name"]: e for e in self.datos["states"][chat]["elements"]}
        for nombre in ("Mensaje", "Enviar", "Manolito", "Lucia", "Chats", "Ajustes"):
            self.assertIn(nombre, elementos)
            caja = elementos[nombre]["box_client_norm"]
            self.assertTrue(0.0 <= caja[0] < caja[2] <= 1.0 and 0.0 <= caja[1] < caja[3] <= 1.0, caja)
            self.assertEqual(len(elementos[nombre]["bbox"]), 4)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = save_navigation_map(self.datos, base_dir=Path(tmp))
            cargado = load_navigation_map("chat_simulado", "maquina-prueba", base_dir=Path(tmp))
            self.assertEqual(json.loads(ruta.read_text(encoding="utf-8"))["root_state_id"], self.datos["root_state_id"])
            self.assertEqual(cargado["states"].keys(), self.datos["states"].keys())

    def test_buscar_elemento_por_nombre_en_el_mapa(self):
        encontrados = find_elements(self.datos, "manolito")
        self.assertTrue(encontrados)
        self.assertEqual(encontrados[0]["depth"], 0, "Manolito es visible desde la raiz")


class TestReproduccionConCoordenadasGuardadas(unittest.TestCase):
    def _mapa(self):
        escritorio = SimulatedChatDesktop()
        explorador = _explorador(escritorio)
        resultado = explorador.explore(escritorio.window_id, escritorio.pid)
        datos = build_navigation_map(resultado, "chat_simulado", "maquina-prueba")
        return escritorio, explorador, datos

    def test_todos_los_caminos_se_reproducen(self):
        escritorio, explorador, datos = self._mapa()
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        informe = verify_all_paths(navegador)
        self.assertEqual(informe["failed"], 0, json.dumps(informe, indent=1)[:2000])
        self.assertEqual(informe["ok"], len(datos["states"]) - 1)
        self.assertIs(datos["path_verification"], informe)

    def test_ventana_movida_las_cajas_relativas_siguen_valiendo(self):
        escritorio, explorador, datos = self._mapa()
        escritorio.offset = (500.0, 250.0)
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        self.assertEqual(verify_all_paths(navegador)["failed"], 0)

    def test_coordenada_corrompida_apuntando_a_otro_contacto_se_detecta(self):
        escritorio, explorador, datos = self._mapa()
        datos = copy.deepcopy(datos)
        raiz = datos["root_state_id"]
        manolito = next(e for e in datos["states"][raiz]["elements"] if e["name"] == "Manolito")
        lucia = next(e for e in datos["states"][raiz]["elements"] if e["name"] == "Lucia")
        manolito["box_client_norm"] = list(lucia["box_client_norm"])
        chat_manolito = next(sid for sid, est in datos["states"].items()
                             if est["path_from_root"] and est["path_from_root"][-1]["element_ref"]["name"] == "Manolito")
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid, coordinates=COORDS_STORED)
        eventos_antes = len(escritorio.events)
        resultado = navegador.go_to(chat_manolito)
        self.assertFalse(resultado.ok)
        self.assertFalse(resultado.steps[-1].reached)
        # Se detecta ANTES del clic: el punto guardado no cae en la caja actual
        # de Manolito, asi que no se pulsa (no se abre el chat de Lucia).
        self.assertIs(resultado.steps[-1].identity_ok, False, resultado.to_dict())
        self.assertIn("ya no corresponden", resultado.reason)
        self.assertFalse([e for e in escritorio.events[eventos_antes:] if e["tipo"] == "contacto_seleccionado"])

    def test_coordenada_corrompida_en_zona_vacia_se_detecta(self):
        escritorio, explorador, datos = self._mapa()
        datos = copy.deepcopy(datos)
        raiz = datos["root_state_id"]
        manolito = next(e for e in datos["states"][raiz]["elements"] if e["name"] == "Manolito")
        manolito["box_client_norm"] = [0.95, 0.95, 0.99, 0.99]
        chat_manolito = next(sid for sid, est in datos["states"].items()
                             if est["path_from_root"] and est["path_from_root"][-1]["element_ref"]["name"] == "Manolito")
        resultado = UINavigator(
            explorador, datos, escritorio.window_id, escritorio.pid, coordinates=COORDS_STORED
        ).go_to(chat_manolito)
        self.assertFalse(resultado.ok)
        self.assertIs(resultado.steps[-1].identity_ok, False, resultado.to_dict())

    def test_mandar_hola_a_manolito(self):
        escritorio, explorador, datos = self._mapa()
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        # 1) El mapa sabe donde esta Manolito y a que estado lleva.
        chat = next(sid for sid, est in datos["states"].items()
                    if est["path_from_root"] and est["path_from_root"][-1]["element_ref"]["name"] == "Manolito")
        # 2) Ir al chat por el camino verificado.
        ida = navegador.go_to(chat)
        self.assertTrue(ida.ok, ida.to_dict())
        elementos = {e["name"]: e for e in datos["states"][chat]["elements"]}
        # 3) Escribir en el campo y enviar con las coordenadas guardadas.
        paso = navegador.type_into(chat, elementos["Mensaje"]["key"], "hola", allow_text=True)
        self.assertTrue(paso.pointer_ok, paso.to_dict())
        envio = navegador.click_stored(chat, elementos["Enviar"]["key"])
        self.assertTrue(envio.pointer_ok, envio.to_dict())
        # 4) Verdad independiente: la app registro el contacto y el mensaje.
        self.assertIn({"tipo": "mensaje_enviado", "contacto": "Manolito", "texto": "hola"}, escritorio.events)
        # 5) Y el estado observado ahora muestra "hola" en el historial.
        despues = navegador.observe()
        self.assertIn("hola", [n.name for n in despues.nodes()])

    def test_escribir_sin_permiso_explicito_se_rechaza(self):
        escritorio, explorador, datos = self._mapa()
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        raiz = datos["root_state_id"]
        with self.assertRaises(PermissionError):
            navegador.type_into(raiz, "x", "hola")



class TestOpcionesDeDesplegableNoSeSeleccionan(unittest.TestCase):
    def test_listitem_dentro_de_combobox_no_se_navega(self):
        escritorio = SimulatedChatDesktop()
        original = escritorio._controls

        def con_desplegable():
            controles = original()
            controles.append({"id": "modo", "role": "ComboBox", "name": "Elige tu modo", "actions": [],
                              "box": (600, 650, 800, 690), "parent": "root"})
            controles.append({"id": "modo_oscuro", "role": "ListItem", "name": "Oscuro", "actions": ["select"],
                              "box": (600, 690, 800, 700), "parent": "modo"})
            return controles

        escritorio._controls = con_desplegable
        resultado = _explorador(escritorio).explore(escritorio.window_id, escritorio.pid)
        clics = [e for e in escritorio.events if e["tipo"] == "clic"]
        self.assertFalse([c for c in clics if c["control"] == "modo_oscuro"], "no debe pulsar la opcion")
        self.assertTrue(any("desplegable" in s["reason"] for s in resultado.skipped_forbidden),
                        resultado.skipped_forbidden)


class TestContenedoresDeNavegacion(unittest.TestCase):
    def _explorar(self, contenedores):
        escritorio = SimulatedChatDesktop()
        explorador = DeepUIExplorer(
            adapter=escritorio,
            policy=ExplorationSafetyPolicy(allow_navigation=True, navigation_containers=contenedores),
            budget=ExplorationBudget(max_depth=1, max_states=20, max_seconds=60, settle_timeout=0.05, settle_poll=0.01),
            app_id="chat_simulado", interaction="click", reset_root=escritorio.restart,
        )
        return escritorio, explorador.explore(escritorio.window_id, escritorio.pid)

    def test_solo_navega_dentro_del_contenedor_permitido(self):
        escritorio, resultado = self._explorar(["secciones"])
        nombres = {t.element_ref["name"] for t in resultado.state_map.transitions}
        self.assertIn("Ajustes", nombres)
        self.assertNotIn("Manolito", nombres, "los contactos no estan en el contenedor permitido")
        self.assertTrue(any(s["reason"] == "fuera de un contenedor de navegacion permitido"
                            for s in resultado.skipped_forbidden))
        self.assertFalse([e for e in escritorio.events if e["tipo"] == "contacto_seleccionado"])

    def test_sin_contenedor_que_coincida_no_navega(self):
        escritorio, resultado = self._explorar(["navigationview"])
        self.assertFalse([t for t in resultado.state_map.transitions if t.action == ACTION_NAVIGATE])


def _chat_de(datos, nombre):
    return next(sid for sid, est in datos["states"].items()
                if est["path_from_root"] and est["path_from_root"][-1]["element_ref"]["name"] == nombre)


class TestCoordenadasEnVivo(unittest.TestCase):
    """El navegador localiza el elemento en el arbol actual antes de pulsar."""

    def _mapa(self):
        escritorio = SimulatedChatDesktop()
        explorador = _explorador(escritorio)
        resultado = explorador.explore(escritorio.window_id, escritorio.pid)
        return escritorio, explorador, build_navigation_map(resultado, "chat_simulado", "maquina-prueba")

    def test_por_defecto_usa_la_posicion_actual_del_elemento(self):
        escritorio, explorador, datos = self._mapa()
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        self.assertEqual(navegador.coordinates, COORDS_LIVE)
        resultado = navegador.go_to(_chat_de(datos, "Manolito"))
        self.assertTrue(resultado.ok, resultado.to_dict())
        paso = resultado.steps[-1]
        self.assertEqual(paso.coordinate_source, COORDS_LIVE)
        self.assertIs(paso.identity_ok, True)
        self.assertEqual(paso.stored_offset_px, 0.0)

    def test_contacto_nuevo_arriba_desplaza_la_lista(self):
        escritorio, explorador, datos = self._mapa()
        chat = _chat_de(datos, "Manolito")
        # Despues de calibrar llega un contacto nuevo que ocupa el primer hueco:
        # la caja guardada de Manolito ahora es la de Ana.
        escritorio.contactos.insert(0, "Ana")

        guardadas = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid, coordinates=COORDS_STORED)
        inicio = len(escritorio.events)
        fallo = guardadas.go_to(chat)
        self.assertFalse(fallo.ok)
        self.assertIs(fallo.steps[-1].identity_ok, False)
        abiertos = [e["contacto"] for e in escritorio.events[inicio:] if e["tipo"] == "contacto_seleccionado"]
        self.assertEqual(abiertos, [], "con coordenadas viejas no debe abrirse ningun chat (tampoco el de Ana)")

        en_vivo = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        inicio = len(escritorio.events)
        exito = en_vivo.go_to(chat)
        self.assertTrue(exito.ok, exito.to_dict())
        self.assertEqual(exito.steps[-1].coordinate_source, COORDS_LIVE)
        self.assertGreater(exito.steps[-1].stored_offset_px, 0.0)
        abiertos = [e["contacto"] for e in escritorio.events[inicio:] if e["tipo"] == "contacto_seleccionado"]
        self.assertEqual(abiertos, ["Manolito"])
        self.assertIn("Chat con Manolito", [n.name for n in en_vivo.observe().nodes()])

    def test_verify_all_paths_usa_siempre_las_coordenadas_guardadas(self):
        escritorio, explorador, datos = self._mapa()
        navegador = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid)
        informe = verify_all_paths(navegador)
        self.assertEqual(informe["coordinates"], COORDS_STORED)
        self.assertEqual(informe["failed"], 0)
        for estado in informe["states"].values():
            for paso in estado["steps"]:
                self.assertEqual(paso["coordinate_source"], COORDS_STORED)
        self.assertEqual(navegador.coordinates, COORDS_LIVE, "debe restaurar el modo del navegador")

    def test_elemento_no_localizable_usa_la_caja_guardada_y_verifica_el_estado(self):
        escritorio, explorador, datos = self._mapa()
        chat = _chat_de(datos, "Lucia")
        # Dos entradas identicas: el arbol no permite localizar "Lucia" de forma
        # unica, asi que no hay identidad que comprobar antes del clic; se usa
        # la caja guardada y el estado alcanzado decide.
        escritorio.contactos.append("Lucia")
        inicio = len(escritorio.events)
        resultado = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid).go_to(chat)
        self.assertTrue(resultado.ok, resultado.to_dict())
        self.assertEqual(resultado.steps[-1].coordinate_source, COORDS_STORED)
        self.assertIsNone(resultado.steps[-1].identity_ok)
        abiertos = [e["contacto"] for e in escritorio.events[inicio:] if e["tipo"] == "contacto_seleccionado"]
        self.assertEqual(abiertos, ["Lucia"])

    def test_raiz_distinta_tras_reiniciar_no_se_navega(self):
        escritorio, explorador, datos = self._mapa()
        escritorio.contactos.remove("Lucia")
        inicio = len(escritorio.events)
        resultado = UINavigator(explorador, datos, escritorio.window_id, escritorio.pid).go_to(_chat_de(datos, "Manolito"))
        self.assertFalse(resultado.ok)
        self.assertIn("estado raiz", resultado.reason)
        self.assertFalse([e for e in escritorio.events[inicio:] if e["tipo"] in ("clic", "contacto_seleccionado")])

    def test_coordinates_invalido(self):
        escritorio, explorador, datos = self._mapa()
        with self.assertRaises(ValueError):
            UINavigator(explorador, datos, escritorio.window_id, escritorio.pid, coordinates="otro")


class TestBuscarSinAcentos(unittest.TestCase):
    def test_busqueda_sin_tildes_ni_mayusculas(self):
        datos = {"states": {"s0": {"depth": 0, "elements": [
            {"name": "Luc\u00eda", "identifier": "contacto_lucia"},
            {"name": "Configuraci\u00f3n", "identifier": ""},
        ]}}}
        self.assertEqual(len(find_elements(datos, "LUCIA")), 1)
        self.assertEqual(len(find_elements(datos, "luc\u00eda")), 1)
        self.assertEqual(len(find_elements(datos, "configuracion")), 1)
        self.assertEqual(find_elements(datos, "   "), [])


if __name__ == "__main__":
    unittest.main()
