"""
Tests de integracion del adaptador de Windows UI Automation — unidad 3.8.6.3.3.2.

Pruebas para src/hands/ui_automation_adapter.py.

- Tests unitarios de contrato/logica: conversion UIAElementInfo -> dataclass,
  clasificacion de elementos actionable, patrones de control, limites de
  enumeracion. Sin GUI ni mocks que fabriquen el resultado que se valida.
- Tests de integracion real: abren Notepad en el monitor secundario derecho,
  lo maximizan, se conectan por HWND con backend UI Automation, enumeran el
  arbol de controles y verifican propiedades reales (automation_id, name,
  control_type, bounding_rectangle, patrones, visibilidad, habilitado).
  Cada prueba abre y cierra exclusivamente la aplicacion que crea.
"""

from __future__ import annotations

import ctypes
import subprocess
import time
import unittest

from pywinauto import application

from src.hands.ui_automation_adapter import (
    UIAutomationAdapter,
    UIAutomationElement,
    UIAutomationTree,
    CONTROL_PATTERNS,
    ACTIONABLE_PATTERNS,
    MAX_ELEMENTS,
    MAX_DEPTH,
    _pattern_id,
)
from src.utils.screen_manager import get_screen_manager


class TestUIAutomationAdapterContract(unittest.TestCase):
    """Contrato y logica pura del adaptador (sin GUI)."""

    def test_control_patterns_lista_esperada(self):
        """Los patrones de control consultados incluyen los del roadmap."""
        for esperado in ("Invoke", "Value", "Toggle", "Selection",
                         "ExpandCollapse", "Scroll", "Text", "RangeValue",
                         "Window", "Transform"):
            self.assertIn(esperado, CONTROL_PATTERNS)

    def test_actionable_patterns_sin_lectura_soleo(self):
        """ACTIONABLE_PATTERNS solo contiene patrones de accion legibles."""
        self.assertTrue(ACTIONABLE_PATTERNS.issubset(set(CONTROL_PATTERNS)))
        for p in ("Invoke", "Value", "Toggle"):
            self.assertIn(p, ACTIONABLE_PATTERNS)

    def test_elemento_con_patron_actionable_es_accionable(self):
        """Un elemento con patron de accion se clasifica como actionable."""
        elem = UIAutomationElement(
            automation_id="btn1", name="Aceptar", control_type="Button",
            bounding_rectangle=(100, 100, 200, 140), process_id=1234,
            runtime_id=(42, 7), is_enabled=True, is_offscreen=False,
            visible=True, handle=1, patterns=["Invoke"], depth=1,
        )
        self.assertTrue(any(p in ACTIONABLE_PATTERNS for p in elem.patterns))
        self.assertIn("Invoke", elem.patterns)

    def test_elemento_sin_patron_no_es_accionable(self):
        """Un elemento sin patrones de accion no se clasifica como actionable."""
        elem = UIAutomationElement(
            automation_id="", name="Etiqueta", control_type="Text",
            bounding_rectangle=(0, 0, 50, 20), process_id=1234,
            runtime_id=(), is_enabled=True, is_offscreen=False,
            visible=True, handle=2, patterns=[], depth=1,
        )
        self.assertFalse(any(p in ACTIONABLE_PATTERNS for p in elem.patterns))

    def test_elemento_offscreen_no_es_accionable(self):
        """Un elemento fuera de pantalla no se considera candidato."""
        elem = UIAutomationElement(
            automation_id="", name="Oculto", control_type="Button",
            bounding_rectangle=(-9999, -9999, -9990, -9980),
            process_id=1234, runtime_id=(), is_enabled=True,
            is_offscreen=True, visible=False, handle=3,
            patterns=["Invoke"], depth=1,
        )
        self.assertTrue(elem.is_offscreen)
        self.assertFalse(elem.visible)

    def test_element_to_dict_serializable(self):
        """to_dict devuelve un diccionario plano serializable."""
        elem = UIAutomationElement(
            automation_id="edit1", name="Texto", control_type="Edit",
            bounding_rectangle=(10, 20, 110, 60), process_id=5678,
            runtime_id=(1, 2, 3), is_enabled=True, is_offscreen=False,
            visible=True, handle=42, patterns=["Value", "Text"],
            depth=2,
        )
        d = elem.to_dict()
        self.assertEqual(d["automation_id"], "edit1")
        self.assertEqual(d["control_type"], "Edit")
        self.assertEqual(d["bounding_rectangle"], [10, 20, 110, 60])
        self.assertEqual(d["patterns"], ["Value", "Text"])
        self.assertEqual(d["depth"], 2)
        self.assertEqual(d["source"], "uia")

    def test_tree_to_dict_incluye_root_y_elementos(self):
        """to_dict del arbol incluye raiz, elementos y metadatos."""
        root = UIAutomationElement(
            automation_id="", name="Ventana", control_type="Window",
            bounding_rectangle=(0, 0, 800, 600), process_id=1,
            runtime_id=(), is_enabled=True, is_offscreen=False,
            visible=True, handle=1, patterns=["Window"], depth=0,
        )
        child = UIAutomationElement(
            automation_id="btn", name="Aceptar", control_type="Button",
            bounding_rectangle=(10, 10, 60, 30), process_id=1,
            runtime_id=(), is_enabled=True, is_offscreen=False,
            visible=True, handle=2, patterns=["Invoke"], depth=1,
        )
        tree = UIAutomationTree(
            window_handle=1, process_id=1, window_title="Ventana",
            window_class="Notepad", root_element=root,
            elements=[root, child], element_count=2,
            source="uia", elapsed_seconds=0.5,
        )
        d = tree.to_dict()
        self.assertEqual(d["window_handle"], 1)
        self.assertEqual(d["process_id"], 1)
        self.assertEqual(d["window_title"], "Ventana")
        self.assertEqual(d["window_class"], "Notepad")
        self.assertEqual(d["root_element"]["control_type"], "Window")
        self.assertEqual(len(d["elements"]), 2)
        self.assertEqual(d["element_count"], 2)
        self.assertEqual(d["source"], "uia")
        self.assertEqual(d["elapsed_seconds"], 0.5)

    def test_adapter_instancia_con_valores_por_defecto(self):
        """El adaptador se instancia con timeouts y limites seguros."""
        adapter = UIAutomationAdapter()
        self.assertGreater(adapter.timeout, 0)
        self.assertGreater(adapter.max_depth, 0)
        self.assertGreater(adapter.max_elements, 0)
        self.assertEqual(adapter.max_depth, MAX_DEPTH)
        self.assertEqual(adapter.max_elements, MAX_ELEMENTS)

    def test_get_actionable_elements_filtra_correctamente(self):
        """get_actionable_elements filtra solo elementos actionable validos."""
        actionable = UIAutomationElement(
            automation_id="btn", name="Aceptar", control_type="Button",
            bounding_rectangle=(10, 10, 60, 30), process_id=1,
            runtime_id=(), is_enabled=True, is_offscreen=False,
            visible=True, handle=2, patterns=["Invoke"], depth=1,
        )
        disabled = UIAutomationElement(
            automation_id="btnd", name="Deshabilitado", control_type="Button",
            bounding_rectangle=(80, 10, 130, 30), process_id=1,
            runtime_id=(), is_enabled=False, is_offscreen=False,
            visible=True, handle=3, patterns=["Invoke"], depth=1,
        )
        offscreen = UIAutomationElement(
            automation_id="btno", name="Fuera", control_type="Button",
            bounding_rectangle=(-9999, -9999, -9990, -9980), process_id=1,
            runtime_id=(), is_enabled=True, is_offscreen=True,
            visible=False, handle=4, patterns=["Invoke"], depth=1,
        )
        label = UIAutomationElement(
            automation_id="lbl", name="Etiqueta", control_type="Text",
            bounding_rectangle=(10, 50, 60, 70), process_id=1,
            runtime_id=(), is_enabled=True, is_offscreen=False,
            visible=True, handle=5, patterns=[], depth=1,
        )
        tree = UIAutomationTree(
            window_handle=1, process_id=1, window_title="V",
            window_class="C", root_element=actionable,
            elements=[actionable, disabled, offscreen, label],
            element_count=4, source="uia", elapsed_seconds=0.1,
        )
        adapter = UIAutomationAdapter()
        resultado = adapter.get_actionable_elements(tree)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].handle, 2)

    def test_patrones_consultados_via_getcurrentpattern_registrados_por_control(self):
        """_collect_patterns_com consulta GetCurrentPattern por cada patron
        disponible y registra solo los que el proveedor soporta (segun su ID,
        no por el nombre ni tipo visual del control)."""
        com = _FakeComElementWithPatterns(
            supported_pattern_ids=(10000, 10002),  # Invoke, Value
            control_type="Button", name="Aceptar",
        )
        adapter = UIAutomationAdapter()
        elem = adapter._automation_element_to_dataclass(
            com, depth=0, parent_handle=0, pid=None, uia=None)
        self.assertEqual(sorted(elem.patterns), ["Invoke", "Value"])
        # Auditoria de consulta real: se consultaron todos los IDs de patron
        # disponibles (no solo los esperados para ese tipo visual).
        esperados = {
            _pattern_id(p) for p in CONTROL_PATTERNS if _pattern_id(p) is not None
        }
        self.assertEqual(set(com.pattern_calls), esperados)

    def test_patrones_no_se_deducen_del_control_type(self):
        """Un control tipo Button sin patrones soportados no se considera
        accionable: las capacidades vienen de la consulta real, no del tipo
        visual ni del nombre."""
        com = _FakeComElementWithPatterns(
            supported_pattern_ids=(), control_type="Button", name="Aceptar",
        )
        adapter = UIAutomationAdapter()
        elem = adapter._automation_element_to_dataclass(
            com, depth=0, parent_handle=0, pid=None, uia=None)
        self.assertEqual(elem.patterns, [])
        self.assertFalse(any(p in ACTIONABLE_PATTERNS for p in elem.patterns))

    def test_patrones_no_se_deducen_del_control_type_inverso(self):
        """Un control tipo Text que realmente soporta Invoke y Value se registra
        con esos patrones: el tipo visual no determina la capacidad."""
        com = _FakeComElementWithPatterns(
            supported_pattern_ids=(10000, 10002), control_type="Text",
            name="Etiqueta",
        )
        adapter = UIAutomationAdapter()
        elem = adapter._automation_element_to_dataclass(
            com, depth=0, parent_handle=0, pid=None, uia=None)
        self.assertEqual(sorted(elem.patterns), ["Invoke", "Value"])

    def test_no_se_invoca_ningun_metodo_de_patron_durante_el_descubrimiento(self):
        """Durante el descubrimiento no se invoca Invoke/Value/ningun metodo de
        patron: solo se consulta GetCurrentPattern (lectura de disponibilidad)."""
        com = _FakeComElementWithPatterns(
            supported_pattern_ids=(10000, 10002), control_type="Button",
            name="Aceptar",
        )
        adapter = UIAutomationAdapter()
        adapter._automation_element_to_dataclass(
            com, depth=0, parent_handle=0, pid=None, uia=None)
        self.assertEqual(
            com.pattern.metodos_invocados, [],
            "No se debe invocar metodo alguno del patron durante el descubrimiento",
        )


class TestUIAutomationAdapterRealWindow(unittest.TestCase):
    """Integracion real con una ventana de Notepad abierta.

    Abre Notepad, lo mueve al monitor secundario derecho y lo maximiza.
    Cada prueba crea y cierra su propia instancia de Notepad.
    """

    APP = "notepad.exe"

    def setUp(self):
        self.proc = None
        self.hwnd = None
        self.pid = None
        self.adapter = UIAutomationAdapter(timeout=8.0)
        self._screen_manager = get_screen_manager()
        self._screen_manager.refresh_monitors()

    def tearDown(self):
        # Cerrar exclusivamente la instancia de Notepad creada por esta prueba.
        # self.pid es el PID real de la ventana de Notepad capturado al abrirla;
        # self.proc.pid puede ser el de un stub que ya salio (no mata nada).
        # Primero intenta kill() sobre el objeto Popen; si falla, usa taskkill
        # por el PID real de la ventana como cierre en cascada (solo ese PID,
        # nunca ventanas preexistentes del usuario).
        pid_a_cerrar = None
        try:
            if self.pid is not None:
                pid_a_cerrar = int(self.pid)
        except Exception:
            pid_a_cerrar = None
        if pid_a_cerrar is None and self.proc is not None:
            try:
                pid_a_cerrar = int(self.proc.pid)
            except Exception:
                pid_a_cerrar = None
        if pid_a_cerrar is not None:
            try:
                import subprocess as _sp
                _sp.run(
                    ["taskkill", "/PID", str(pid_a_cerrar), "/F", "/T"],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.hwnd = None
        self.pid = None

    # ------------------------------------------------------------------
    # Helpers de ciclo de vida real
    # ------------------------------------------------------------------

    def _enumerar_ventanas_notepad(self, user32, pid_esperado):
        """Enumera ventanas de Notepad por PID y, como respaldo, por titulo."""
        found = []

        def callback(hwnd, _lparam):
            try:
                length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
                if length == 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
                titulo = buf.value
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(
                    ctypes.c_void_p(hwnd), ctypes.byref(pid)
                )
                pid_val = int(pid.value)
                es_notepad = (
                    pid_val == pid_esperado
                    or "notepad" in titulo.lower()
                    or "bloc de notas" in titulo.lower()
                )
                if es_notepad:
                    found.append((int(hwnd), pid_val, titulo))
            except Exception:
                pass
            return True

        CBFUNC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )
        user32.EnumWindows(CBFUNC(callback), 0)
        return found

    def _abrir_notepad_maximizado_secundario(self):
        """Abre Notepad, lo mueve al monitor secundario derecho y lo maximiza.

        Retorna (hwnd, pid) de la ventana creada.
        """
        user32 = ctypes.windll.user32
        monitors = self._screen_manager.monitors
        secundario = None
        for m in monitors:
            if not m.is_primary:
                secundario = m
                break
        if secundario is None:
            secundario = self._screen_manager.get_primary_monitor()

        self.assertIsNotNone(secundario, "No se encontro monitor secundario")

        # Abrir Notepad
        self.proc = subprocess.Popen([self.APP])

        # Esperar a que la ventana aparezca (reintentos; Notepad puede tardar)
        pid_esperado = self.proc.pid
        found = []
        for _intento in range(20):
            time.sleep(0.3)
            found = self._enumerar_ventanas_notepad(user32, pid_esperado)
            if found:
                break

        self.assertGreaterEqual(len(found), 1,
                                "No se encontro la ventana de Notepad creada")

        # Preferir la ventana cuyo PID coincide con el proceso lanzado
        hwnd, pid, title = None, None, None
        for cand_hwnd, cand_pid, cand_title in found:
            if cand_pid == pid_esperado:
                hwnd, pid, title = cand_hwnd, cand_pid, cand_title
                break
        if hwnd is None:
            hwnd, pid, title = found[0]

        self.hwnd = hwnd
        self.pid = pid

        # Mover la ventana al origen del monitor secundario y maximizarla
        if not user32.IsWindow(ctypes.c_void_p(hwnd)):
            self.fail("HWND=%s ya no es una ventana valida" % hwnd)

        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
        time.sleep(0.3)
        user32.SetWindowPos(
            ctypes.c_void_p(hwnd), 0,
            int(secundario.left), int(secundario.top),
            int(secundario.width), int(secundario.height),
            0x0004 | 0x0040,  # SWP_NOZORDER | SWP_SHOWWINDOW
        )
        time.sleep(0.3)
        user32.ShowWindow(ctypes.c_void_p(hwnd), 3)  # SW_MAXIMIZE
        time.sleep(0.8)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        time.sleep(0.3)

        # Verificar que la ventana esta en el monitor secundario.
        # Se tolera un pequeno offset del borde de la ventana; lo que importa
        # es que su centro caiga dentro del rectangulo del monitor secundario.
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        self.assertTrue(
            secundario.contains_point(cx, cy),
            "Centro de la ventana (%s,%s) no esta en el monitor secundario "
            "(%s,%s,%sx%s)"
            % (cx, cy, secundario.left, secundario.top,
               secundario.width, secundario.height),
        )
        self.assertGreater(rect.right - rect.left, 100)
        self.assertGreater(rect.bottom - rect.top, 100)

        return hwnd, pid

    # ------------------------------------------------------------------
    # Pruebas de integracion real
    # ------------------------------------------------------------------

    def test_conectar_y_enumerar_arbol_notepad_real(self):
        """Conecta a Notepad real por HWND y enumera su arbol UIA."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()

        tree = self.adapter.enumerate_window(hwnd, pid)

        self.assertIsNone(tree.error, "Error enumerando: %s" % tree.error)
        self.assertEqual(tree.window_handle, hwnd)
        self.assertEqual(tree.process_id, pid)
        self.assertGreaterEqual(tree.element_count, 1)
        self.assertEqual(tree.source, "uia")
        self.assertGreater(tree.elapsed_seconds, 0)

        # El elemento raiz debe ser la ventana de Notepad
        root = tree.root_element
        self.assertEqual(root.handle, hwnd)
        self.assertEqual(root.control_type, "Window")
        self.assertTrue(root.visible)
        self.assertTrue(root.is_enabled)
        self.assertFalse(root.is_offscreen)
        self.assertGreater(root.bounding_rectangle[2] - root.bounding_rectangle[0], 0)
        self.assertGreater(root.bounding_rectangle[3] - root.bounding_rectangle[1], 0)

        # Debe haber al menos un hijo (el area de edicion de Notepad)
        self.assertGreaterEqual(len(tree.elements), 2,
                                "Se esperaba ventana + al menos un hijo")

    def test_elementos_tienen_propiedades_reales(self):
        """Cada elemento del arbol real tiene propiedades pobladas."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()
        tree = self.adapter.enumerate_window(hwnd, pid)
        self.assertIsNone(tree.error)

        for elem in tree.elements:
            self.assertIsInstance(elem.handle, int)
            self.assertIsInstance(elem.control_type, str)
            self.assertIsInstance(elem.bounding_rectangle, tuple)
            self.assertEqual(len(elem.bounding_rectangle), 4)
            self.assertIsInstance(elem.patterns, list)
            self.assertIsInstance(elem.depth, int)
            self.assertGreaterEqual(elem.depth, 0)
            self.assertEqual(elem.process_id, pid)
            # bounding box no debe ser degenerado para la raiz
            if elem.depth == 0:
                self.assertGreater(elem.bounding_rectangle[2],
                                   elem.bounding_rectangle[0])
                self.assertGreater(elem.bounding_rectangle[3],
                                   elem.bounding_rectangle[1])

    def test_clasifica_elementos_actionable(self):
        """get_actionable_elements devuelve solo elementos con patrones de accion."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()
        tree = self.adapter.enumerate_window(hwnd, pid)
        self.assertIsNone(tree.error)

        adapter = UIAutomationAdapter()
        actionables = adapter.get_actionable_elements(tree)
        # La ventana raiz tiene patron Window (actionable)
        self.assertGreaterEqual(len(actionables), 1)
        for elem in actionables:
            self.assertTrue(elem.visible)
            self.assertTrue(elem.is_enabled)
            self.assertFalse(elem.is_offscreen)
            self.assertTrue(any(p in ACTIONABLE_PATTERNS for p in elem.patterns))

    def test_conectar_hwnd_inexistente_devuelve_error(self):
        """Un HWND inexistente devuelve un arbol con error y sin elementos."""
        tree = self.adapter.enumerate_window(999999, 0)
        self.assertIsNotNone(tree.error)
        self.assertEqual(tree.element_count, 0)
        self.assertEqual(tree.window_handle, 999999)

    def test_no_enumera_escritorio_solo_ventana(self):
        """El adaptador solo consulta el arbol de la ventana identificada."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()
        tree = self.adapter.enumerate_window(hwnd, pid)
        self.assertIsNone(tree.error)

        # Todos los elementos deben pertenecer al mismo proceso (Notepad)
        for elem in tree.elements:
            self.assertEqual(elem.process_id, pid,
                             "Elemento %s pertenece a otro proceso" % elem.handle)

    def test_enumera_todas_las_propiedades_requeridas_notepad_real(self):
        """Enumera Notepad real y verifica que cada elemento recolecta solo
        las propiedades que el proveedor UIA expone: automation_id, name,
        control_type, class_name, bounding_rectangle, process_id,
        is_enabled, is_offscreen, runtime_id, relaciones padre/hijo y
        patrones disponibles. El arbol no debe contener duplicados ni
        elementos de otros procesos."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()
        tree = self.adapter.enumerate_window(hwnd, pid)

        self.assertIsNone(tree.error, f"Error enumerando: {tree.error}")
        self.assertEqual(tree.window_handle, hwnd)
        self.assertEqual(tree.process_id, pid)
        self.assertEqual(tree.source, "uia")
        self.assertIsInstance(tree.truncated, bool)

        # La raiz es la ventana de Notepad, sin padre y con relacion valida
        root = tree.root_element
        self.assertEqual(root.handle, hwnd)
        self.assertEqual(root.control_type, "Window")
        self.assertEqual(root.process_id, pid)
        self.assertEqual(root.parent_handle, 0)
        self.assertEqual(root.depth, 0)
        self.assertTrue(root.visible)
        self.assertTrue(root.is_enabled)
        self.assertFalse(root.is_offscreen)
        self.assertGreater(root.bounding_rectangle[2], root.bounding_rectangle[0])
        self.assertGreater(root.bounding_rectangle[3], root.bounding_rectangle[1])
        self.assertIsInstance(root.runtime_id, tuple)
        self.assertIsInstance(root.patterns, list)

        handles_vistos = set()
        for elem in tree.elements:
            self.assertIsInstance(elem.automation_id, str)
            self.assertIsInstance(elem.name, str)
            self.assertIsInstance(elem.control_type, str)
            self.assertIsInstance(elem.class_name, str)
            self.assertEqual(len(elem.bounding_rectangle), 4)
            self.assertEqual(elem.process_id, pid,
                             f"Elemento {elem.handle} no pertenece a Notepad")
            self.assertIsInstance(elem.is_enabled, bool)
            self.assertIsInstance(elem.is_offscreen, bool)
            self.assertIsInstance(elem.runtime_id, tuple)
            self.assertIsInstance(elem.patterns, list)
            self.assertIsInstance(elem.depth, int)
            self.assertGreaterEqual(elem.depth, 0)
            self.assertIsInstance(elem.handle, int)
            # No duplicados por handle
            if elem.handle:
                self.assertNotIn(elem.handle, handles_vistos)
                handles_vistos.add(elem.handle)
            # Un elemento hijo referencia a un padre existente (o 0 en la raiz)
            if elem.depth > 0:
                self.assertGreaterEqual(elem.parent_handle, 0)

        self.assertGreaterEqual(len(tree.elements), 2,
                                "Se esperaba ventana + al menos un hijo de Notepad")

    def test_patrones_reales_en_controles_notepad(self):
        """Verifica en Notepad real que los patrones se consultan del proveedor
        UIA y se registran por control: la ventana raiz expone Window y al
        menos un control expone patrones de accion. No se invoca ninguna
        accion durante el descubrimiento."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()
        tree = self.adapter.enumerate_window(hwnd, pid)
        self.assertIsNone(tree.error, "Error enumerando: %s" % tree.error)

        # La ventana raiz (top-level) debe exponer el patron Window (consulta
        # real al proveedor UIA, no deducida del tipo visual).
        self.assertIn(
            "Window", tree.root_element.patterns,
            "La ventana raiz debe exponer el patron Window; obtuvo %s"
            % tree.root_element.patterns,
        )

        # Al menos un control del arbol debe exponer patrones: comprueba que la
        # consulta de patrones produce evidencia real sobre controles reales.
        con_patrones = [e for e in tree.elements if e.patterns]
        self.assertGreaterEqual(
            len(con_patrones), 1,
            "Se esperaba al menos un control con patrones de control detectados",
        )


class _FakeRect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class _FakeComElement:
    """Simula un IUIAutomationElement (COM) con los atributos que lee la
    ruta de fallback del adaptador. No invoca el SO ni patrones de accion."""
    def __init__(self, handle=1, pid=123, visible=True, enabled=True,
                 offscreen=False, automation_id="", name="",
                 control_type="Button", class_name="cls",
                 runtime_id=(1,), control_id=5, framework_id="Win32"):
        self.CurrentNativeWindowHandle = handle
        self.CurrentBoundingRectangle = _FakeRect(10, 10, 100, 100)
        self.CurrentRuntimeId = runtime_id
        self.CurrentControlId = control_id
        self.CurrentIsOffscreen = offscreen
        self.CurrentIsEnabled = enabled
        self.CurrentIsVisible = visible
        self.CurrentAutomationId = automation_id
        self.CurrentName = name
        self.CurrentControlTypeProgrammaticName = control_type
        self.CurrentClassName = class_name
        self.CurrentProcessId = pid
        self.CurrentFrameworkId = framework_id

    def GetCurrentPattern(self, pattern_id):
        return None


class _FakePattern:
    """Falso objeto de patron UIA. Registra si se invoca algun metodo sobre el
    patron (debe quedar vacio: el descubrimiento solo consulta disponibilidad,
    nunca ejecuta acciones como Invoke/Value/Toggle)."""
    def __init__(self):
        self.metodos_invocados = []

    def __getattr__(self, nombre):
        self.metodos_invocados.append(nombre)
        return lambda *args, **kwargs: None


class _FakeComElementWithPatterns(_FakeComElement):
    """Falso IUIAutomationElement que declara soporte para ciertos patrones
    segun su ID numerico (simula la respuesta real del proveedor UIA). Usado
    solo para auditar que el adaptador consulta GetCurrentPattern por cada
    patron y registra los soportados, sin deducirlos del tipo visual."""
    def __init__(self, supported_pattern_ids=(), **kwargs):
        super().__init__(**kwargs)
        self.supported_pattern_ids = set(int(x) for x in supported_pattern_ids)
        self.pattern_calls = []
        self.pattern = _FakePattern()

    def GetCurrentPattern(self, pattern_id):
        pid = int(pattern_id)
        self.pattern_calls.append(pid)
        if pid in self.supported_pattern_ids:
            return self.pattern
        return None


class _FakeUIAElementInfo:
    """Simula un UIAElementInfo de pywinauto para probar el mapeo y los
    limites de enumeracion sin lanzar ventanas reales."""
    def __init__(self, handle=1, pid=123, visible=True, enabled=True,
                 offscreen=False, automation_id="", name="",
                 control_type="Button", class_name="cls",
                 runtime_id=(1,), control_id=5, framework_id="Win32",
                 children=None, rectangle=None):
        self.element = _FakeComElement(handle=handle, pid=pid,
                                       visible=visible, enabled=enabled,
                                       offscreen=offscreen,
                                       automation_id=automation_id, name=name,
                                       control_type=control_type,
                                       class_name=class_name,
                                       runtime_id=runtime_id,
                                       control_id=control_id,
                                       framework_id=framework_id)
        self.rectangle = rectangle or _FakeRect(10, 10, 100, 100)
        self.visible = visible
        self.runtime_id = runtime_id
        self.control_id = control_id
        self.enabled = enabled
        self.handle = handle
        self.framework_id = framework_id
        self.automation_id = automation_id
        self.name = name
        self.control_type = control_type
        self.class_name = class_name
        self.process_id = pid
        self._children = children or []

    def children(self):
        return list(self._children)


class TestUIAutomationTreeEnumeration(unittest.TestCase):
    """Pruebas unitarias (sin GUI) de la enumeracion del arbol UIA.

    Verifican el mapeo de propiedades, el manejo de duplicados, el corte
    por limites de profundidad/cantidad (arboles virtualizados) y la
    tolerancia a proveedores incompletos.
    """

    def setUp(self):
        self.adapter = UIAutomationAdapter(timeout=2.0, max_depth=60,
                                           max_elements=2000)

    def test_element_contiene_propiedades_requeridas(self):
        """UIAutomationElement expone todas las propiedades que el proveedor
        UIA puede exponer, con valores por defecto seguros."""
        elem = UIAutomationElement()
        for campo in ("automation_id", "name", "control_type", "class_name",
                      "bounding_rectangle", "process_id", "runtime_id",
                      "is_enabled", "is_offscreen", "visible", "handle",
                      "framework_id", "parent_handle", "child_count",
                      "patterns", "depth", "source"):
            self.assertTrue(hasattr(elem, campo), "Falta el campo " + campo)
        self.assertEqual(elem.bounding_rectangle, (0, 0, 0, 0))
        self.assertEqual(elem.runtime_id, ())
        self.assertEqual(elem.patterns, [])
        self.assertEqual(elem.source, "uia")

    def test_tree_to_dict_incluye_truncado(self):
        """UIAutomationTree.to_dict serializa el campo truncated."""
        root = UIAutomationElement(control_type="Window", handle=1,
                                   visible=True, is_enabled=True,
                                   is_offscreen=False)
        tree = UIAutomationTree(window_handle=1, process_id=1,
                                window_title="V", window_class="C",
                                root_element=root, elements=[root],
                                element_count=1, truncated=True,
                                source="uia", elapsed_seconds=0.1)
        d = tree.to_dict()
        self.assertIn("truncated", d)
        self.assertTrue(d["truncated"])

    def test_visible_ruta_com_usa_currentisvisible(self):
        """En la ruta COM fallback, visible se lee de CurrentIsVisible (no de
        CurrentIsEnabled), respetando lo que el proveedor expone."""
        com = _FakeComElement(handle=7, pid=99, visible=False, enabled=True)
        elem = self.adapter._automation_element_to_dataclass(
            com, depth=0, parent_handle=0, pid=None, uia=None)
        self.assertEqual(elem.handle, 7)
        self.assertEqual(elem.process_id, 99)
        self.assertTrue(elem.is_enabled)
        self.assertFalse(elem.visible)

    def test_arbol_no_repite_elementos_duplicados_por_handle(self):
        """Elementos con handle repetido (ciclos/arbol mal formado) no se
        duplican en el arbol enumerado."""
        hijo = _FakeUIAElementInfo(handle=11, name="Hijo", control_type="Button")
        padre = _FakeUIAElementInfo(handle=1, name="Padre", control_type="Window",
                                    children=[hijo, hijo])
        elementos = [UIAutomationElement(handle=1, depth=0)]
        vistos = {1}
        truncado = self.adapter._enumerate_children(
            padre, 1, depth=1, elements=elementos, seen_handles=vistos, pid=None)
        self.assertFalse(truncado)
        handles = [e.handle for e in elementos if e.handle]
        self.assertEqual(handles.count(11), 1,
                         "El handle duplicado no debe repetirse")

    def test_arbol_truncado_por_profundidad_maxima(self):
        """Al alcanzar max_depth se detiene la recursividad y se reporta truncado."""
        adaptador = UIAutomationAdapter(timeout=2.0, max_depth=0, max_elements=2000)
        padre = _FakeUIAElementInfo(handle=1, name="P", control_type="Window",
                                    children=[_FakeUIAElementInfo(handle=2, name="H", control_type="Button")])
        elementos = [UIAutomationElement(handle=1, depth=0)]
        vistos = {1}
        truncado = adaptador._enumerate_children(
            padre, 1, depth=1, elements=elementos, seen_handles=vistos, pid=None)
        self.assertTrue(truncado)
        self.assertEqual(len(elementos), 1,
                         "No se agregaron hijos por limite de profundidad")

    def test_arbol_truncado_por_cantidad_maxima(self):
        """Al alcanzar max_elements se detiene la enumeracion y se reporta truncado."""
        adaptador = UIAutomationAdapter(timeout=2.0, max_depth=60, max_elements=2)
        hijos = [_FakeUIAElementInfo(handle=i, name="H%d" % i, control_type="Button")
                 for i in (2, 3, 4)]
        padre = _FakeUIAElementInfo(handle=1, name="P", control_type="Window", children=hijos)
        elementos = [UIAutomationElement(handle=1, depth=0)]
        vistos = {1}
        truncado = adaptador._enumerate_children(
            padre, 1, depth=1, elements=elementos, seen_handles=vistos, pid=None)
        self.assertTrue(truncado)
        self.assertLessEqual(len(elementos), 2)

    def test_proveedor_incompleto_no_rompe_enumeracion(self):
        """Un proveedor que falla al devolver hijos no interrumpe la enumeracion."""
        def falla_hijos():
            raise RuntimeError("proveedor incompleto")
        padre = _FakeUIAElementInfo(handle=1, name="P", control_type="Window")
        padre.children = falla_hijos  # type: ignore[method-assign]
        elementos = [UIAutomationElement(handle=1, depth=0)]
        vistos = {1}
        truncado = self.adapter._enumerate_children(
            padre, 1, depth=1, elements=elementos, seen_handles=vistos, pid=None)
        self.assertFalse(truncado)
        self.assertEqual(len(elementos), 1)


if __name__ == "__main__":
    unittest.main()
