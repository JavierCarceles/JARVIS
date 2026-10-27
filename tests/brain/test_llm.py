"""
Tests del módulo Brain (LLM) 2.8.13.5

Verifica el funcionamiento del cerebro de JARVIS: normalización de alias,
detección de acciones directas, ejecución de goals, generación de respuestas,
interpretación de intenciones e integración con HTN.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

from src.brain.llm import Brain, get_jarvis_context
from src.brain.htn_integration import HTNBrainIntegration


class TestBrainInit(unittest.TestCase):
    """2.8.13.5.9 — Verificar inicialización del Brain"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_9_model_asignado(self):
        """El modelo debe estar configurado correctamente."""
        self.assertEqual(self.brain.model, "llama3")

    def test_2_8_13_5_9_htn_integration_asignado(self):
        """La integración HTN debe estar inicializada."""
        self.assertIsInstance(self.brain.htn_integration, HTNBrainIntegration)

    def test_2_8_13_5_9_action_registry_asignado(self):
        """El registro de acciones debe estar inicializado."""
        self.assertIsNotNone(self.brain.action_registry)

    def test_2_8_13_5_9_entity_resolver_asignado(self):
        """El resolvedor de entidades debe estar inicializado."""
        self.assertIsNotNone(self.brain.entity_resolver)

    def test_2_8_13_5_9_memory_manager_asignado(self):
        """El gestor de memoria debe estar inicializado."""
        self.assertIsNotNone(self.brain.memory_manager)

    def test_2_8_13_5_9_preconditions_effects_asignado(self):
        """El gestor de precondiciones/efectos debe estar inicializado."""
        self.assertIsNotNone(self.brain.preconditions_effects_manager)


class TestBrainActionAliases(unittest.TestCase):
    """2.8.13.5.10 — Verificar ACTION_ALIASES"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_10_calibrar_chrome_alias(self):
        """calibrate_chrome debe mapear a calibrar_chrome."""
        self.assertEqual(self.brain.ACTION_ALIASES.get("calibrate_chrome"), "calibrar_chrome")

    def test_2_8_13_5_10_calibrar_aplicaciones_alias(self):
        """calibrate_applications debe mapear a calibrar_aplicaciones."""
        self.assertEqual(self.brain.ACTION_ALIASES.get("calibrate_applications"), "calibrar_aplicaciones")

    def test_2_8_13_5_10_calibrate_all_alias(self):
        """calibrate_all_applications debe mapear a calibrar_aplicaciones."""
        self.assertEqual(self.brain.ACTION_ALIASES.get("calibrate_all_applications"), "calibrar_aplicaciones")

    def test_2_8_13_5_10_opener_alias(self):
        """open_chrome debe mapear a abrir_chrome."""
        self.assertEqual(self.brain.ACTION_ALIASES.get("open_chrome"), "abrir_chrome")

    def test_2_8_13_5_10_aliases_dict_no_vacio(self):
        """ACTION_ALIASES debe contener múltiples entradas."""
        self.assertGreater(len(self.brain.ACTION_ALIASES), 5)


class TestNormalizeActionName(unittest.TestCase):
    """2.8.13.5.11 — Verificar _normalize_action_name"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_11_normaliza_alias_chrome(self):
        """'calibrate_chrome' no está registrado; alias debe resolver a 'calibrar_chrome'."""
        result = self.brain._normalize_action_name("calibrate_chrome")
        self.assertEqual(result, "calibrar_chrome")

    def test_2_8_13_5_11_normaliza_alias_aplicaciones(self):
        """'calibrate_applications' está registrado y debe retornarse tal cual."""
        result = self.brain._normalize_action_name("calibrate_applications")
        self.assertEqual(result, "calibrate_applications")

    def test_2_8_13_5_11_normaliza_alias_chrome_ingles(self):
        """'calibrate_chrome' NO está registrado; el alias debe resolver a 'calibrar_chrome'."""
        result = self.brain._normalize_action_name("calibrate_chrome")
        self.assertEqual(result, "calibrar_chrome")

    def test_2_8_13_5_11_normaliza_accion_registrada(self):
        """Una acción ya registrada no debe ser modificada."""
        result = self.brain._normalize_action_name("calibrar_chrome")
        self.assertEqual(result, "calibrar_chrome")

    def test_2_8_13_5_11_retorna_candidato_para_desconocida(self):
        """Una acción desconocida debe retornar el candidato sin cambios."""
        result = self.brain._normalize_action_name("accion_inventada")
        self.assertEqual(result, "accion_inventada")

    def test_2_8_13_5_11_retorna_vacio_para_no_string(self):
        """Debe retornar cadena vacía para entrada no string."""
        self.assertEqual(self.brain._normalize_action_name(None), "")
        self.assertEqual(self.brain._normalize_action_name(123), "")

    def test_2_8_13_5_11_retorna_vacio_para_vacio(self):
        """Debe retornar cadena vacía para string vacío o en blanco."""
        self.assertEqual(self.brain._normalize_action_name(""), "")
        self.assertEqual(self.brain._normalize_action_name("   "), "")


class TestCleanJsonResponse(unittest.TestCase):
    """2.8.13.5.12 — Verificar _clean_json_response"""

    def test_2_8_13_5_12_strip_markdown_fences(self):
        """Debe eliminar bloques de código markdown."""
        text = "```json\n{\"action\": \"test\"}\n```"
        result = Brain._clean_json_response(text)
        self.assertEqual(result, '{"action": "test"}')

    def test_2_8_13_5_12_extract_from_text_with_prefix(self):
        """Debe extraer JSON incrustado en texto."""
        text = 'Here is the result: {"action": "test"}'
        result = Brain._clean_json_response(text)
        self.assertTrue(result.startswith("{"))
        self.assertTrue(result.endswith("}"))

    def test_2_8_13_5_12_plain_json_unchanged(self):
        """El JSON limpio debe pasar sin cambios."""
        text = '{"action": "test", "parameters": {}}'
        result = Brain._clean_json_response(text)
        self.assertEqual(result, text)

    def test_2_8_13_5_12_empty_string(self):
        """Cadena vacía debe retornar cadena vacía."""
        self.assertEqual(Brain._clean_json_response(""), "")

    def test_2_8_13_5_12_none_input(self):
        """None debe retornar cadena vacía."""
        self.assertEqual(Brain._clean_json_response(None), "")

    def test_2_8_13_5_12_nested_json_from_text(self):
        """Debe extraer JSON anidado del texto."""
        text = 'Result: {"action": "abrir_chrome", "parameters": {"url": "http://x"}} final'
        result = Brain._clean_json_response(text)
        self.assertTrue(result.startswith("{"))
        self.assertTrue(result.endswith("}"))


class TestParseModelResponse(unittest.TestCase):
    """2.8.13.5.13 — Verificar parse_model_response"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_13_parse_valid_json(self):
        """Debe parsear JSON válido a diccionario."""
        result = self.brain.parse_model_response('{"action": "test"}')
        self.assertIsInstance(result, dict)
        self.assertEqual(result["action"], "test")

    def test_2_8_13_5_13_parse_json_con_markdown(self):
        """Debe parsear JSON envuelto en markdown."""
        text = '```json\n{"action": "test"}\n```'
        result = self.brain.parse_model_response(text)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["action"], "test")

    def test_2_8_13_5_13_parse_json_en_texto(self):
        """Debe extraer JSON de un texto con prefijo."""
        text = 'Aquí está: {"action": "abrir_chrome"}'
        result = self.brain.parse_model_response(text)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["action"], "abrir_chrome")

    def test_2_8_13_5_13_invalid_json_returns_none(self):
        """JSON inválido debe retornar None."""
        result = self.brain.parse_model_response("not json at all")
        self.assertIsNone(result)

    def test_2_8_13_5_13_empty_returns_none(self):
        """Cadena vacía debe retornar None."""
        result = self.brain.parse_model_response("")
        self.assertIsNone(result)

    def test_2_8_13_5_13_json_list_returns_none(self):
        """Un JSON que no es dict debe retornar None."""
        result = self.brain.parse_model_response('["item1", "item2"]')
        self.assertIsNone(result)


class TestDetectDirectAction(unittest.TestCase):
    """2.8.13.5.14 — Verificar _detect_direct_action"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_14_detect_chrome_calibration(self):
        """Debe detectar calibración específica de Chrome."""
        result = self.brain._detect_direct_action("calibrar chrome")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "action")
        self.assertEqual(result["action"]["action"], "calibrar_chrome")

    def test_2_8_13_5_14_detect_edge_calibration(self):
        """Debe detectar calibración específica de Edge."""
        result = self.brain._detect_direct_action("calibrar edge")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"]["action"], "calibrar_edge")

    def test_2_8_13_5_14_detect_firefox_calibration(self):
        """Debe detectar calibración específica de Firefox."""
        result = self.brain._detect_direct_action("calibrar firefox")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"]["action"], "calibrar_firefox")

    def test_2_8_13_5_14_detect_global_calibration(self):
        """Debe detectar calibración global de aplicaciones."""
        result = self.brain._detect_direct_action("calibrar aplicaciones")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"]["action"], "calibrar_aplicaciones")

    def test_2_8_13_5_14_detect_global_calibration_programas(self):
        """Debe detectar calibración global usando 'programas'."""
        result = self.brain._detect_direct_action("calibrar programas")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"]["action"], "calibrar_aplicaciones")

    def test_2_8_13_5_14_browser_specific_no_global(self):
        """'calibrar chrome' no debe interpretarse como calibración global."""
        result = self.brain._detect_direct_action("calibrar chrome")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"]["action"], "calibrar_chrome")

    def test_2_8_13_5_14_no_action_for_non_calibration(self):
        """Input sin calibración no debe detectar acción directa."""
        result = self.brain._detect_direct_action("hola que tal")
        self.assertIsNone(result)

    def test_2_8_13_5_14_no_action_for_empty(self):
        """Input vacío no debe detectar acción directa."""
        self.assertIsNone(self.brain._detect_direct_action(""))
        self.assertIsNone(self.brain._detect_direct_action(None))


class TestExecuteGoal(unittest.TestCase):
    """2.8.13.5.15 — Verificar execute_goal"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_15_navigate_stream_goal(self):
        """Un goal navigate_stream debe producir navigate_to_url."""
        goal = {"type": "navigate_stream", "target": "https://twitch.tv/test"}
        result = self.brain.execute_goal(goal)
        self.assertEqual(result["type"], "legacy_action")
        self.assertEqual(result["action"], "navigate_to_url")
        self.assertEqual(result["parameters"]["url"], "https://twitch.tv/test")

    def test_2_8_13_5_15_navigate_goal(self):
        """Un goal navigate debe producir navigate_to_url."""
        goal = {"type": "navigate", "target": "https://google.com"}
        result = self.brain.execute_goal(goal)
        self.assertEqual(result["type"], "legacy_action")
        self.assertEqual(result["action"], "navigate_to_url")
        self.assertEqual(result["parameters"]["url"], "https://google.com")

    def test_2_8_13_5_15_open_application_goal(self):
        """Un goal open_application debe producir open_{target}."""
        goal = {"type": "open_application", "target": "chrome"}
        result = self.brain.execute_goal(goal)
        self.assertEqual(result["type"], "legacy_action")
        self.assertEqual(result["action"], "open_chrome")
        self.assertIn("reasoning", result)

    def test_2_8_13_5_15_unknown_goal_type(self):
        """Un goal type desconocido debe retornar error."""
        goal = {"type": "unknown_type", "target": "test"}
        result = self.brain.execute_goal(goal)
        self.assertEqual(result["type"], "error")
        self.assertIn("unknown_type", result["message"])


class TestBrainPublicAPI(unittest.TestCase):
    """2.8.13.5.16 — Verificar API pública del Brain"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_16_get_current_goals_empty(self):
        """get_current_goals debe retornar una lista vacía."""
        self.assertEqual(self.brain.get_current_goals(), [])

    def test_2_8_13_5_16_get_system_state(self):
        """get_system_state debe retornar un estado no nulo."""
        state = self.brain.get_system_state()
        self.assertIsNotNone(state)

    def test_2_8_13_5_16_get_available_actions_is_list(self):
        """get_available_actions debe retornar una lista."""
        actions = self.brain.get_available_actions()
        self.assertIsInstance(actions, list)

    def test_2_8_13_5_16_get_jarvis_context(self):
        """get_jarvis_context debe retornar un diccionario."""
        context = get_jarvis_context()
        self.assertIsNotNone(context)

    def test_2_8_13_5_16_interpret_intent_empty(self):
        """interpret_intent con input vacío debe retornar tipo unknown."""
        result = self.brain.interpret_intent("")
        self.assertEqual(result["type"], "unknown")
        self.assertIsNone(result["goal"])
        self.assertIsNone(result["action"])

    def test_2_8_13_5_16_interpret_intent_none(self):
        """interpret_intent con None debe retornar tipo unknown."""
        result = self.brain.interpret_intent(None)
        self.assertEqual(result["type"], "unknown")

    def test_2_8_13_5_16_think_empty_prompt(self):
        """think con prompt vacío debe retornar mensaje por defecto."""
        result = self.brain.think("")
        self.assertEqual(result, "No recibí ningún mensaje.")

    def test_2_8_13_5_16_think_none_prompt(self):
        """think con None debe retornar mensaje por defecto."""
        result = self.brain.think(None)
        self.assertEqual(result, "No recibí ningún mensaje.")

    def test_2_8_13_5_16_clear_memory_no_raises(self):
        """clear_memory no debe lanzar excepción."""
        try:
            self.brain.clear_memory()
        except Exception as exc:
            self.fail(f"clear_memory lanzó excepción: {exc}")

    def test_2_8_13_5_16_get_conversation_history_is_list(self):
        """get_conversation_history debe retornar una lista."""
        history = self.brain.get_conversation_history()
        self.assertIsInstance(history, list)

    def test_2_8_13_5_16_get_domain_entities_is_list(self):
        """get_domain_entities debe retornar una lista."""
        entities = self.brain.get_domain_entities()
        self.assertIsInstance(entities, list)

    def test_2_8_13_5_16_get_planner_ready_data(self):
        """get_planner_ready_data debe retornar dict con claves esperadas."""
        data = self.brain.get_planner_ready_data()
        self.assertIsInstance(data, dict)
        self.assertIn("goals", data)
        self.assertIn("domain_entities", data)
        self.assertIn("current_state", data)
        self.assertIn("available_actions", data)


class TestBrainLLMInteraction(unittest.TestCase):
    """2.8.13.5.17 — Verificar interacción con LLM (mocked)"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_17_generate_response_empty_prompt(self):
        """generate_response con prompt vacío debe retornar cadena vacía."""
        self.assertEqual(self.brain.generate_response(""), "")

    @patch("src.brain.llm.ollama.chat")
    def test_2_8_13_5_17_generate_response_mocked(self, mock_chat):
        """generate_response debe usar ollama.chat y retornar el contenido."""
        mock_chat.return_value = {"message": {"content": "Respuesta de prueba"}}
        result = self.brain.generate_response("Hola")
        self.assertEqual(result, "Respuesta de prueba")
        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args
        self.assertIn("model", call_kwargs.kwargs)
        self.assertEqual(call_kwargs.kwargs["model"], "llama3")

    @patch("src.brain.llm.ollama.chat")
    def test_2_8_13_5_17_think_con_direct_action(self, mock_chat):
        """think debe devolver comando [CMD: ...] para acciones legacy."""
        result = self.brain.think("calibrar chrome")
        self.assertIn("[CMD:", result)
        self.assertIn("calibrar_chrome", result)

    @patch("src.brain.llm.ollama.chat")
    def test_2_8_13_5_17_think_con_goal(self, mock_chat):
        """think con goal debe registrar objetivo y retornar confirmación."""
        mock_chat.return_value = {"message": {"content": '{"type": "goal", "goal": {"type": "navigate", "target": "https://example.com", "description": "test"}}'}}
        result = self.brain.think("navega a example.com")
        self.assertIn("Objetivo registrado", result)

    @patch("src.brain.llm.ollama.chat")
    def test_2_8_13_5_17_interpret_intent_action(self, mock_chat):
        """interpret_intent debe retornar tipo goal cuando la entidad 'chrome'
        existe en entities.json como alias de 'Google Chrome'.

        Con el conjunto ampliado de entidades (35), 'chrome' se resuelve como
        entidad conocida y el sistema retorna type=goal (no action), ya que el
        entity resolver intercepta antes de consultar el LLM."""
        mock_chat.return_value = {"message": {"content": '{"action": "abrir_chrome", "parameters": {}}'}}
        result = self.brain.interpret_intent("abre chrome")
        self.assertEqual(result["type"], "goal")
        self.assertIn("goal", result)

    @patch("src.brain.llm.ollama.chat")
    def test_2_8_13_5_17_process_with_htn_disabled(self, mock_chat):
        """process_with_htn debe manejar el caso de HTN deshabilitado."""
        self.brain.htn_integration.enable_integration(False)
        try:
            result = self.brain.process_with_htn("abrir chrome")
            self.assertIn("type", result)
        finally:
            self.brain.htn_integration.enable_integration(True)


class TestBrainExtractSearchQuery(unittest.TestCase):
    """2.8.13.5.18 — Verificar _extract_search_query"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_18_extract_buscar(self):
        """Debe extraer query después de 'buscar'."""
        result = self.brain._extract_search_query("buscar gatos")
        self.assertEqual(result, "gatos")

    def test_2_8_13_5_18_extract_search_english(self):
        """Debe extraer query después de 'search'."""
        result = self.brain._extract_search_query("search for cats")
        self.assertEqual(result, "for cats")

    def test_2_8_13_5_18_extract_no_match(self):
        """Sin patrón de búsqueda debe retornar cadena vacía."""
        result = self.brain._extract_search_query("hola mundo")
        self.assertEqual(result, "")

    def test_2_8_13_5_18_extract_empty(self):
        """Input vacío debe retornar cadena vacía."""
        self.assertEqual(self.brain._extract_search_query(""), "")


class TestBrainThinkWithImage(unittest.TestCase):
    """2.8.13.5.19 — Verificar think_with_image y analyze_image"""

    @classmethod
    def setUpClass(cls):
        cls.brain = Brain(model="llama3")

    def test_2_8_13_5_19_think_with_image_empty_prompt(self):
        """think_with_image con prompt vacío debe retornar mensaje."""
        result = self.brain.think_with_image("", "/fake/path.png")
        self.assertEqual(result, "No recibí instrucciones para la imagen.")

    def test_2_8_13_5_19_think_with_image_no_image(self):
        """think_with_image sin image_path debe retornar mensaje."""
        result = self.brain.think_with_image("analiza esto", "")
        self.assertEqual(result, "No se proporcionó ninguna imagen.")

    def test_2_8_13_5_19_analyze_image_no_image(self):
        """analyze_image sin image_path debe retornar mensaje."""
        result = self.brain.analyze_image("", "descripción")
        self.assertEqual(result, "No se proporcionó imagen")

    def test_2_8_13_5_19_analyze_image_no_prompt(self):
        """analyze_image sin analysis_prompt debe retornar mensaje."""
        result = self.brain.analyze_image("/fake/path.png", "")
        self.assertEqual(result, "No se proporcionaron instrucciones para el análisis.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
