# -*- coding: ascii -*-
"""
Calibracion en profundidad REAL en Windows sobre la app de chat propia.

Abre `tests/fixtures/gui_chat_app` (instancia propia), la coloca en el monitor
de pruebas (no principal mas a la derecha), la maximiza y:

1. Explora con CLICS REALES en coordenadas verificadas (antes de cada clic,
   el elemento bajo el puntero es el esperado): secciones, contactos y
   pestanas. Las transiciones sin vuelta (abrir un chat) vuelven a la raiz
   reiniciando la app propia.
2. Guarda el mapa JSON (estados con profundidad, elementos con coordenadas,
   transiciones con evidencia) en tests/fixtures/_tmp_ui_maps/.
3. Reproduce el camino de CADA estado desde la raiz con las coordenadas
   GUARDADAS y comprueba el estado alcanzado.
4. "Mandar hola a Manolito" con el mapa: ir al chat, escribir en el campo y
   pulsar Enviar (texto solo porque la app es propia).
5. Caso negativo: una coordenada guardada que apunta a otro contacto se
   detecta como fallo.

La verdad independiente es el registro de eventos que escribe la propia app
(contacto seleccionado, mensaje enviado, "borrado" nunca). Con -s imprime un
resumen de cada paso.

Requiere Windows, PySide6 y JARVIS_TEST_GUI_REAL=1:
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/calibration/ui_exploration/test_navegacion_chat_entorno_real.py -v -s
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, List, Optional, Tuple

from src.desktop.native_imports import is_windows

RAIZ = Path(__file__).resolve().parents[4]
RUN = RAIZ / "tests" / "fixtures" / "gui_chat_app" / "run.py"
TITULO = "JARVIS Chat Fixture"
DIR_MAPAS = RAIZ / "tests" / "fixtures" / "_tmp_ui_maps"
ESPERA_VENTANA = 30.0


def _esperar(predicado, limite: float, paso: float = 0.2) -> Any:
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        valor = predicado()
        if valor:
            return valor
        time.sleep(paso)
    return None


class TestNavegacionChatEntornoReal(unittest.TestCase):
    proc: Optional[subprocess.Popen] = None

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows (excepcion (a))")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real")
        try:
            import PySide6  # noqa: F401
        except ImportError as exc:
            raise AssertionError("PySide6 es necesario para la app de prueba: %s" % exc)
        from src.desktop.platform_contract import get_desktop_platform

        cls.adapter = get_desktop_platform()
        pantallas = cls.adapter.enumerate_displays().value
        no_principales = [p for p in pantallas if not p.is_primary]
        cls.monitor = max(no_principales, key=lambda p: p.bounds.right) if no_principales else pantallas[0]
        cls._tmp = tempfile.TemporaryDirectory()
        cls.eventos_path = os.path.join(cls._tmp.name, "eventos_chat.jsonl")
        cls.resumen: List[str] = []
        cls.window_id, cls.pid = cls._lanzar()
        try:
            cls._explorar()
        except Exception:
            cls._cerrar()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._cerrar()
        print("\n[NAVEGACION CHAT] resumen:\n  " + "\n  ".join(getattr(cls, "resumen", [])))
        tmp = getattr(cls, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    # ------------------------------------------------------------ app propia

    @classmethod
    def _ventanas_fixture(cls) -> List[Any]:
        res = cls.adapter.list_windows(visible_only=True)
        return [w for w in (res.value or []) if res.ok and (w.title or "") == TITULO]

    @classmethod
    def _lanzar(cls) -> Tuple[int, int]:
        previas = {w.window_id for w in cls._ventanas_fixture()}
        if previas:
            raise AssertionError("Ya hay una ventana '%s' abierta; cerrarla y repetir" % TITULO)
        entorno = dict(os.environ)
        entorno["JARVIS_CHAT_FIXTURE_EVENTOS"] = cls.eventos_path
        cls.proc = subprocess.Popen([sys.executable, str(RUN)], env=entorno, cwd=str(RAIZ))
        ventana = _esperar(lambda: next(iter(cls._ventanas_fixture()), None), ESPERA_VENTANA)
        if ventana is None:
            raise AssertionError("La app de chat no mostro su ventana en %.0f s" % ESPERA_VENTANA)
        wid = int(ventana.window_id)
        assert cls.adapter.move_window_to_display(wid, cls.monitor.display_id).ok, "no se pudo mover al monitor de pruebas"
        assert cls.adapter.maximize_window(wid).ok, "no se pudo maximizar"
        assert cls.adapter.activate_window(wid).ok, "no se pudo activar"
        assert _esperar(lambda: cls.adapter.is_foreground(wid), 5.0), "la app no quedo en primer plano"
        # Estabilidad minima del arbol (Qt crea la accesibilidad bajo demanda).
        _esperar(lambda: cls.adapter.get_accessibility_tree(wid, pid=ventana.pid).ok, 5.0)
        return wid, int(ventana.pid)

    @classmethod
    def _cerrar(cls) -> None:
        for ventana in cls._ventanas_fixture():
            cls.adapter.close_window(int(ventana.window_id))
        if cls.proc is not None:
            try:
                cls.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.proc.terminate()
                cls.proc.wait(timeout=10)
            cls.proc = None

    @classmethod
    def _reiniciar(cls) -> Optional[Tuple[int, int]]:
        cls._cerrar()
        cls.window_id, cls.pid = cls._lanzar()
        return cls.window_id, cls.pid

    @classmethod
    def _eventos(cls) -> List[dict]:
        if not os.path.exists(cls.eventos_path):
            return []
        with open(cls.eventos_path, encoding="utf-8") as fichero:
            return [json.loads(l) for l in fichero if l.strip()]

    # ------------------------------------------------------------ exploracion

    @classmethod
    def _explorar(cls) -> None:
        from src.hands.calibration.ui_exploration import DeepUIExplorer, ExplorationBudget, ExplorationSafetyPolicy
        from src.hands.calibration.ui_navigation_map import build_navigation_map, save_navigation_map

        cls.explorador = DeepUIExplorer(
            adapter=cls.adapter,
            policy=ExplorationSafetyPolicy(allow_navigation=True),
            budget=ExplorationBudget(max_depth=3, max_states=25, max_seconds=300, settle_timeout=2.0),
            app_id="fixture_chat",
            interaction="click",
            reset_root=cls._reiniciar,
        )
        inicio = time.monotonic()
        cls.resultado = cls.explorador.explore(cls.window_id, cls.pid)
        segundos = time.monotonic() - inicio
        window = cls.adapter.get_window(cls.window_id).value
        cls.datos = build_navigation_map(cls.resultado, "fixture_chat", "prueba_windows", window=window,
                                         display=cls.monitor)
        cls.mapa_path = save_navigation_map(cls.datos, base_dir=DIR_MAPAS)
        cls.resumen.append(
            "exploracion: %.1f s, estados=%d, transiciones=%d, acciones=%d, reinicios=%d, abortada=%s %s"
            % (segundos, len(cls.datos["states"]), len(cls.datos["transitions"]),
               cls.resultado.actions_performed, cls.resultado.resets, cls.resultado.aborted,
               cls.resultado.abort_reason)
        )
        cls.resumen.append("mapa JSON: %s" % cls.mapa_path)
        # Diagnostico: que se hizo, que no tuvo efecto y que se salto (y por que).
        for accion in cls.explorador.performed_actions():
            cls.resumen.append("  accion %s" % {k: accion.get(k) for k in sorted(accion) if k != "tree"})
        for sin_efecto in cls.resultado.no_effect:
            cls.resumen.append("  sin efecto %s" % sin_efecto)
        for saltado in cls.resultado.skipped_forbidden:
            ref = saltado.get("element_ref") or {}
            cls.resumen.append("  saltado %s/%s (%s): %s" % (
                ref.get("name"), ref.get("native_role"), saltado.get("action"), saltado.get("reason")))
        for error in cls.resultado.errors:
            cls.resumen.append("  error %s" % error)
        for state_id, estado in cls.datos["states"].items():
            camino = " -> ".join(p["element_ref"].get("name", "?") for p in (estado["path_from_root"] or []))
            cls.resumen.append("  estado %s prof=%d camino=[%s] elementos=%d"
                               % (state_id[:8], estado["depth"], camino, len(estado["elements"])))

    def _estado_tras(self, nombre: str) -> str:
        for state_id, estado in self.datos["states"].items():
            camino = estado["path_from_root"] or []
            if camino and camino[-1]["element_ref"].get("name") == nombre:
                return state_id
        self.fail("no hay estado alcanzado por '%s'; estados: %s" % (nombre, self.resumen))

    def _navegador(self):
        from src.hands.calibration.ui_navigation_map import UINavigator

        return UINavigator(self.explorador, self.datos, self.window_id, self.pid)

    # ------------------------------------------------------------ pruebas

    def test_01_mapa_con_profundidad(self):
        self.assertFalse(self.resultado.aborted, self.resultado.abort_reason)
        chat = self._estado_tras("Manolito")
        self.assertEqual(self.datos["states"][chat]["depth"], 1)
        avisos = self._estado_tras("Avisos")
        camino = [p["element_ref"]["name"] for p in self.datos["states"][avisos]["path_from_root"]]
        self.assertEqual(camino, ["Ajustes", "Avisos"])

    def test_02_evidencia_de_clics_reales(self):
        cambios = [t for t in self.datos["transitions"] if t["evidence"].get("changed")]
        self.assertTrue(cambios)
        for transicion in self.datos["transitions"]:
            self.assertEqual(transicion["evidence"]["method"], "click", transicion)
            self.assertTrue(transicion["evidence"]["pointer_ok"], transicion)
        tipos = [e["tipo"] for e in self._eventos()]
        self.assertIn("contacto_seleccionado", tipos, "la app debe registrar los clics de la exploracion")
        self.assertIn("seccion", tipos)

    def test_03_borrar_nunca_se_pulsa(self):
        self.assertNotIn("borrado", [e["tipo"] for e in self._eventos()])

    def test_04_json_con_coordenadas(self):
        guardado = json.loads(Path(self.mapa_path).read_text(encoding="utf-8"))
        chat = self._estado_tras("Manolito")
        elementos = {e["name"]: e for e in guardado["states"][chat]["elements"]}
        for nombre in ("Mensaje", "Enviar", "Manolito", "Lucia"):
            self.assertIn(nombre, elementos, sorted(elementos))
            caja = elementos[nombre]["box_client_norm"]
            self.assertTrue(0.0 <= caja[0] < caja[2] <= 1.0 and 0.0 <= caja[1] < caja[3] <= 1.0, caja)

    def test_05_todos_los_caminos_se_reproducen_con_coordenadas_guardadas(self):
        from src.hands.calibration.ui_navigation_map import save_navigation_map, verify_all_paths

        informe = verify_all_paths(self._navegador())
        save_navigation_map(self.datos, base_dir=DIR_MAPAS)
        self.resumen.append("reproduccion de caminos: ok=%d fallidos=%d" % (informe["ok"], informe["failed"]))
        self.assertEqual(informe["failed"], 0, json.dumps(informe, indent=1)[:3000])

    def test_06_mandar_hola_a_manolito(self):
        navegador = self._navegador()
        chat = self._estado_tras("Manolito")
        ida = navegador.go_to(chat)
        self.assertTrue(ida.ok, ida.to_dict())
        elementos = {e["name"]: e for e in self.datos["states"][chat]["elements"]}
        escrito = navegador.type_into(chat, elementos["Mensaje"]["key"], "hola", allow_text=True)
        self.assertTrue(escrito.pointer_ok, escrito.to_dict())
        envio = navegador.click_stored(chat, elementos["Enviar"]["key"])
        self.assertTrue(envio.pointer_ok, envio.to_dict())
        enviado = _esperar(lambda: any(
            e["tipo"] == "mensaje_enviado" and e.get("contacto") == "Manolito" and e.get("texto") == "hola"
            for e in self._eventos()), 5.0)
        self.assertTrue(enviado, "la app no registro el mensaje: %s" % self._eventos()[-5:])
        despues = navegador.observe()
        self.assertIn("hola", [n.name for n in despues.nodes()], "el historial debe mostrar 'hola'")
        self.resumen.append("mandar hola a Manolito: OK en %.1f s (%d pasos)" % (ida.seconds, len(ida.steps)))

    def _datos_con_manolito_en_la_caja_de_lucia(self):
        datos = copy.deepcopy(self.datos)
        raiz = datos["root_state_id"]
        manolito = next(e for e in datos["states"][raiz]["elements"] if e["name"] == "Manolito")
        lucia = next(e for e in datos["states"][raiz]["elements"] if e["name"] == "Lucia")
        manolito["box_client_norm"] = list(lucia["box_client_norm"])
        return datos

    def test_07_coordenada_corrompida_se_detecta_antes_del_clic(self):
        from src.hands.calibration.ui_navigation_map import COORDS_STORED, UINavigator

        datos = self._datos_con_manolito_en_la_caja_de_lucia()
        inicio = len(self._eventos())
        resultado = UINavigator(
            self.explorador, datos, self.window_id, self.pid, coordinates=COORDS_STORED
        ).go_to(self._estado_tras("Manolito"))
        self.assertFalse(resultado.ok, "una coordenada que apunta a Lucia no puede dar el chat de Manolito")
        self.assertIs(resultado.steps[-1].identity_ok, False, resultado.to_dict())
        abiertos = [e for e in self._eventos()[inicio:] if e["tipo"] == "contacto_seleccionado"]
        self.assertEqual(abiertos, [], "no debe abrirse ningun chat con la coordenada vieja")
        self.resumen.append("coordenada corrompida: detectada antes del clic (%s)" % resultado.reason)

    def test_08_en_vivo_llega_al_chat_aunque_la_coordenada_guardada_este_mal(self):
        from src.hands.calibration.ui_navigation_map import COORDS_LIVE, UINavigator

        datos = self._datos_con_manolito_en_la_caja_de_lucia()
        inicio = len(self._eventos())
        resultado = UINavigator(self.explorador, datos, self.window_id, self.pid).go_to(self._estado_tras("Manolito"))
        self.assertTrue(resultado.ok, resultado.to_dict())
        self.assertEqual(resultado.steps[-1].coordinate_source, COORDS_LIVE)
        abiertos = [e.get("contacto") for e in self._eventos()[inicio:] if e["tipo"] == "contacto_seleccionado"]
        self.assertEqual(abiertos, ["Manolito"], "el registro de la app debe confirmar el chat abierto")
        self.resumen.append("en vivo con coordenada guardada erronea: OK (desplazamiento %s px)"
                            % resultado.steps[-1].stored_offset_px)


if __name__ == "__main__":
    unittest.main()
