# -*- coding: utf-8 -*-
"""
Tests de verificación para la conexión Application Knowledge → Goal (unidad 3.7.2.1).

Verifica que el conocimiento estructurado de aplicaciones (ApplicationKnowledge
en applications_core.py) se traduce correctamente en objetivos (Goal en node.py)
cuando el usuario pide abrir/navegar/cerrar una aplicación, incluyendo
capabilities y required_capabilities.

HALLAGOS DE VERIFICACIÓN DOCUMENTADOS:
1. Discrepancia de nomenclatura: Goal.get_required_capabilities() retorna
   "open_application", "close_application", "activate_window", "focus_element",
   "type_text", "press_key" — mientras que ApplicationCapability enum declara
   "open", "close", "navigate", "search", "type", "click". No coinciden
   directamente. Existe un mapeo parcial unidireccional en heuristic.py
   (de AppCap → nombre de Goal), pero no hay mapeo inverso.

2. is_capability_available() retorna False correctamente cuando la aplicación
   no está disponible en tiempo de ejecución (Chrome no instalado en esta
   máquina). Es comportamiento esperado, no un bug.
"""

import unittest
from unittest.mock import patch

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationManager,
    get_application_manager,
)
from src.hands.planner.application_integration import (
    ApplicationKnowledgeIntegrator,
    get_application_knowledge_integrator,
)
from src.hands.planner.node import Goal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_integrator_with_manager(manager=None) -> ApplicationKnowledgeIntegrator:
    integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
    integrator.application_manager = manager
    integrator.memory_manager = None
    return integrator


# ---------------------------------------------------------------------------
# Tests: Goal.get_required_capabilities returns expected values
# ---------------------------------------------------------------------------

class TestGoalRequiredCapabilities(unittest.TestCase):
    """Verifica que Goal.get_required_capabilities() retorna las capacidades
    esperadas para cada tipo de objetivo."""

    def test_open_application_capabilities(self):
        goal = Goal(
            id="test_open", type="open_application", target="Chrome",
            description="Abrir Chrome", priority=1, constraints=[], nodes=[], metadata={},
        )
        required = goal.get_required_capabilities()
        self.assertIn("open_application", required)
        self.assertIn("activate_window", required)

    def test_close_application_capabilities(self):
        goal = Goal(
            id="test_close", type="close_application", target="Chrome",
            description="Cerrar Chrome", priority=1, constraints=[], nodes=[], metadata={},
        )
        required = goal.get_required_capabilities()
        self.assertIn("close_application", required)
        self.assertIn("activate_window", required)

    def test_navigate_capabilities(self):
        goal = Goal(
            id="test_nav", type="navigate", target="https://example.com",
            description="Navegar", priority=1, constraints=[], nodes=[], metadata={},
        )
        required = goal.get_required_capabilities()
        self.assertIn("open_application", required)
        self.assertIn("navigate", required)


# ---------------------------------------------------------------------------
# Tests: ApplicationCapability enum values (Application Knowledge declared)
# ---------------------------------------------------------------------------

class TestApplicationCapabilityEnum(unittest.TestCase):
    """Verifica los valores declarados en ApplicationCapability enum."""

    def test_open_capability_value(self):
        self.assertEqual(ApplicationCapability.OPEN.value, "open")

    def test_close_capability_value(self):
        self.assertEqual(ApplicationCapability.CLOSE.value, "close")

    def test_navigate_capability_value(self):
        self.assertEqual(ApplicationCapability.NAVIGATE.value, "navigate")

    def test_search_capability_value(self):
        self.assertEqual(ApplicationCapability.SEARCH.value, "search")

    def test_type_capability_value(self):
        self.assertEqual(ApplicationCapability.TYPE.value, "type")


# ---------------------------------------------------------------------------
# Tests: Naming mismatch between Goal and Application Knowledge (DISCREPANCIA)
# ---------------------------------------------------------------------------

class TestGoalVsApplicationKnowledgeNaming(unittest.TestCase):
    """Documenta la discrepancia de nomenclatura entre Goal y Application Knowledge.

    Goal usa nombres como "open_application", "close_application", etc.
    Application Knowledge declara valores como "open", "close", etc.
    No hay coincidencia directa. Ver heuristic.py para mapeo parcial.
    """

    def test_goal_open_application_not_equal_appcap_open(self):
        """Goal usa 'open_application' pero ApplicationCapability.OPEN.value es 'open'.
        Esta es una discrepancia documentada de la unidad 3.7.2.1."""
        goal_cap = "open_application"
        app_cap = ApplicationCapability.OPEN.value
        self.assertNotEqual(goal_cap, app_cap)

    def test_goal_close_application_not_equal_appcap_close(self):
        """Goal usa 'close_application' pero ApplicationCapability.CLOSE.value es 'close'."""
        goal_cap = "close_application"
        app_cap = ApplicationCapability.CLOSE.value
        self.assertNotEqual(goal_cap, app_cap)

    def test_goal_capabilities_not_directly_in_appcap_values(self):
        """Ninguna de las capacidades de Goal (open_application, activate_window,
        focus_element, type_text, press_key) coincide directamente con los valores
        de ApplicationCapability enum (open, close, navigate, search, type, click)."""
        goal_caps = {"open_application", "close_application", "activate_window",
                     "focus_element", "type_text", "press_key", "navigate"}
        appcap_values = {c.value for c in ApplicationCapability}
        # 'navigate' sí coincide, pero el resto no
        non_matching = goal_caps - appcap_values
        self.assertGreaterEqual(len(non_matching), 5,
                                f"Esperaba al menos 5 capacidades de Goal sin coincidencia directa, "
                                f"encontradas: {non_matching}")


# ---------------------------------------------------------------------------
# Tests: ApplicationKnowledgeIntegrator capability availability
# ---------------------------------------------------------------------------

class TestApplicationKnowledgeIntegratorAvailability(unittest.TestCase):
    """Verifica que ApplicationKnowledgeIntegrator.is_capability_available()
    distinga correctamente entre capacidad declarada y disponible en runtime."""

    def test_is_capability_available_false_when_app_not_installed(self):
        """is_capability_available retorna False para Chrome cuando no está
        instalado en esta máquina (declarado pero no disponible en runtime)."""
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.is_capability_available("chrome", ApplicationCapability.OPEN)
        self.assertFalse(result,
            "Chrome no está instalado en esta máquina de prueba, por lo que "
            "is_capability_available debe retornar False aunque esté declarado")

    def test_is_capability_available_false_for_unknown_app(self):
        """is_capability_available retorna False para aplicación inexistente."""
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.is_capability_available("nonexistent_app_xyz", ApplicationCapability.OPEN)
        self.assertFalse(result)

    def test_get_application_capabilities_returns_dict(self):
        """get_application_capabilities retorna un dict no vacío para Chrome."""
        integrator = _make_integrator_with_manager(get_application_manager())
        caps = integrator.get_application_capabilities("chrome")
        self.assertIsInstance(caps, dict)
        self.assertGreater(len(caps), 0, "Chrome debe tener al menos una capacidad declarada")


# ---------------------------------------------------------------------------
# Tests: Brain._get_application_knowledge integration
# ---------------------------------------------------------------------------

class TestBrainApplicationKnowledgeIntegration(unittest.TestCase):
    """Verifica que Brain._get_application_knowledge exponga datos para
    creación de Goals."""

    @patch("src.brain.llm.ollama.chat")
    def test_get_application_knowledge_structure(self, mock_chat):
        from src.brain.llm import Brain
        brain = Brain(model="llama3")
        knowledge = brain._get_application_knowledge()
        self.assertIn("applications", knowledge)
        self.assertIn("total_applications", knowledge)
        self.assertIn("supported_capabilities", knowledge)
        self.assertGreaterEqual(knowledge["total_applications"], 1)

        # Cada aplicación debe tener capabilities, declared, available, capability_available
        for app_name, app_data in knowledge["applications"].items():
            self.assertIn("capabilities", app_data)
            self.assertIn("declared", app_data)
            self.assertIn("available", app_data)
            self.assertIn("capability_available", app_data)

    @patch("src.brain.llm.ollama.chat")
    def test_create_goal_from_user_input_application(self, mock_chat):
        """create_goal_from_user_input con 'abre chrome' crea un Goal válido."""
        from src.brain.llm import Brain
        brain = Brain(model="llama3")
        goal = brain.create_goal_from_user_input("abre chrome")
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "open_application")
        # El entity resolver normaliza 'chrome' a 'Google Chrome'
        self.assertEqual(goal.target, "Google Chrome")

    @patch("src.brain.llm.ollama.chat")
    def test_interpret_intent_returns_goal_for_application(self, mock_chat):
        """interpret_intent con 'abre chrome' retorna type='goal'."""
        from src.brain.llm import Brain
        brain = Brain(model="llama3")
        result = brain.interpret_intent("abre chrome")
        self.assertEqual(result["type"], "goal")
        self.assertIn("goal", result)

    @patch("src.brain.llm.ollama.chat")
    def test_goal_required_capabilities_from_interpret_intent(self, mock_chat):
        """El Goal creado por interpret_intent tiene required_capabilities vía
        get_required_capabilities(). NOTA: metadata.required_capabilities solo
        se popula para navigate/navigate_stream (no para open_application),
        ver _create_goal_from_entity en llm.py líneas 671-678."""
        from src.brain.llm import Brain
        brain = Brain(model="llama3")
        result = brain.interpret_intent("abre chrome")
        goal = result["goal"]
        if isinstance(goal, list):
            goal = goal[0]

        required = goal.get_required_capabilities()
        self.assertGreaterEqual(len(required), 1)
        self.assertIn("open_application", required)

        # get_required_capabilities() funciona correctamente para open_application
        self.assertIn("activate_window", required)


if __name__ == "__main__":
    unittest.main(verbosity=2)
