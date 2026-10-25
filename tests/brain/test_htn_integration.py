"""
Tests de integración HTN-Brain 2.8.13.5

Verifica la integración entre el sistema Brain y el planificador
jerárquico HTN, cubriendo creación de goals, descomposición,
ejecución, estadísticas y manejo de estados.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.brain.htn_integration import HTNBrainIntegration, HTNIntegrationResult, get_htn_integration
from src.hands.planner.htn_manager import HTNManager, TaskExecutionResult, TaskStatus, get_htn_manager
from src.hands.planner.node import Goal, Task


class TestHTNBrainIntegrationInit(unittest.TestCase):
    """2.8.13.5.2 — Verificar inicialización de HTNBrainIntegration"""

    def test_2_8_13_5_2_htn_manager_asignado(self):
        """El gestor HTN debe estar inicializado (singleton)."""
        integration = HTNBrainIntegration()
        self.assertIsInstance(integration.htn_manager, HTNManager)

    def test_2_8_13_5_2_task_executor_asignado(self):
        """El ejecutor de tareas debe estar inicializado."""
        integration = HTNBrainIntegration()
        self.assertIsNotNone(integration.task_executor)

    def test_2_8_13_5_2_memory_manager_asignado(self):
        """El gestor de memoria debe estar inicializado."""
        integration = HTNBrainIntegration()
        self.assertIsNotNone(integration.memory_manager)

    def test_2_8_13_5_2_application_integrator_asignado(self):
        """El integrador de aplicaciones debe estar inicializado."""
        integration = HTNBrainIntegration()
        self.assertIsNotNone(integration.application_integrator)

    def test_2_8_13_5_2_is_enabled_por_defecto(self):
        """La integración debe estar habilitada por defecto."""
        integration = HTNBrainIntegration()
        self.assertTrue(integration.is_enabled)

    def test_2_8_13_5_2_total_integrations_inicia_en_cero(self):
        """El contador de integraciones debe iniciar en cero."""
        integration = HTNBrainIntegration()
        self.assertEqual(integration.total_integrations, 0)


class TestHTNGGoalCreation(unittest.TestCase):
    """2.8.13.5.3 — Verificar _create_goal_from_input"""

    def setUp(self):
        self.integration = HTNBrainIntegration()

    def test_2_8_13_5_3_goal_calibracion(self):
        """Input con 'calibrar' debe crear un Goal de calibración."""
        goal = self.integration._create_goal_from_input("necesito calibrar el navegador", {})
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "calibrate_applications")
        self.assertIn("calibrate", goal.id)

    def test_2_8_13_5_3_goal_open_chrome(self):
        """Input con 'abrir' y 'chrome' debe crear un Goal de apertura."""
        goal = self.integration._create_goal_from_input("Abrir chrome", {})
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "open_application")
        self.assertEqual(goal.target, "chrome")

    def test_2_8_13_5_3_goal_open_youtube(self):
        """Input con 'abrir' y 'youtube' debe crear un Goal de apertura de youtube."""
        goal = self.integration._create_goal_from_input("abrir youtube", {})
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "open_application")
        self.assertEqual(goal.target, "youtube")

    def test_2_8_13_5_3_goal_navegar_url(self):
        """Input con 'navegar' y URL debe crear un Goal de navegación."""
        goal = self.integration._create_goal_from_input(
            "navegar a https://www.google.com", {}
        )
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "navigate")
        self.assertEqual(goal.target, "https://www.google.com")

    def test_2_8_13_5_3_goal_navegar_entity(self):
        """Input con 'navegar' sin URL debe crear un Goal de navegación de stream."""
        goal = self.integration._create_goal_from_input(
            "navegar al streamer", {}
        )
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "navigate_stream")

    def test_2_8_13_5_3_goal_search(self):
        """Input con 'buscar' debe crear un Goal de búsqueda."""
        goal = self.integration._create_goal_from_input(
            "buscar qué es el machine learning", {}
        )
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "search")
        self.assertIn("machine learning", goal.target)

    def test_2_8_13_5_3_goal_generic_sin_palabras_clave(self):
        """Input sin palabras clave debe crear un Goal genérico."""
        goal = self.integration._create_goal_from_input(
            "hola que tal", {}
        )
        self.assertIsNotNone(goal)
        self.assertEqual(goal.type, "generic")

    def test_2_8_13_5_3_goal_input_vacio_retorna_none(self):
        """Input vacío debe retornar None."""
        self.assertIsNone(self.integration._create_goal_from_input("", {}))
        self.assertIsNone(self.integration._create_goal_from_input("   ", {}))
        self.assertIsNone(self.integration._create_goal_from_input(None, {}))

    def test_2_8_13_5_3_goal_tiene_id_unico(self):
        """Los goals creados deben tener IDs basados en el tipo y timestamp."""
        goal1 = self.integration._create_goal_from_input("abrir chrome", {})
        goal2 = self.integration._create_goal_from_input("abrir youtube", {})
        self.assertIsNotNone(goal1)
        self.assertIsNotNone(goal2)
        self.assertNotEqual(goal1.id, goal2.id)


class TestHTNIntegrationStatistics(unittest.TestCase):
    """2.8.13.5.4 — Verificar estadísticas e integración"""

    def setUp(self):
        self.integration = HTNBrainIntegration()

    def test_2_8_13_5_4_get_integration_statistics(self):
        """get_integration_statistics debe retornar un diccionario con claves esperadas."""
        stats = self.integration.get_integration_statistics()
        self.assertIn("integration_enabled", stats)
        self.assertIn("total_integrations", stats)
        self.assertIn("successful_integrations", stats)
        self.assertIn("success_rate", stats)
        self.assertIn("last_execution_time", stats)
        self.assertIn("htn_manager_stats", stats)
        self.assertIn("task_executor_stats", stats)

    def test_2_8_13_5_4_success_rate_inicia_en_cero(self):
        """Con cero integraciones, success_rate debe ser 0.0."""
        stats = self.integration.get_integration_statistics()
        self.assertEqual(stats["total_integrations"], 0)
        self.assertEqual(stats["success_rate"], 0.0)

    def test_2_8_13_5_4_enable_disable_integration(self):
        """enable_integration debe alternar el estado de habilitación."""
        self.assertTrue(self.integration.is_enabled)
        self.integration.enable_integration(False)
        self.assertFalse(self.integration.is_enabled)
        self.integration.enable_integration(True)
        self.assertTrue(self.integration.is_enabled)

    def test_2_8_13_5_4_record_integration_actualiza_contadores(self):
        """_record_integration debe incrementar contadores correctamente."""
        self.assertEqual(self.integration.total_integrations, 0)
        self.assertEqual(self.integration.successful_integrations, 0)

        self.integration._record_integration(0.5, True)
        self.assertEqual(self.integration.total_integrations, 1)
        self.assertEqual(self.integration.successful_integrations, 1)

        self.integration._record_integration(0.3, False)
        self.assertEqual(self.integration.total_integrations, 2)
        self.assertEqual(self.integration.successful_integrations, 1)
        stats = self.integration.get_integration_statistics()
        self.assertAlmostEqual(stats["success_rate"], 0.5)

    def test_2_8_13_5_4_record_integration_tiempo(self):
        """_record_integration debe actualizar last_execution_time."""
        self.integration._record_integration(2.5, True)
        self.assertAlmostEqual(self.integration.last_execution_time, 2.5, places=1)

    def test_2_8_13_5_4_get_htn_insights(self):
        """get_htn_insights debe retornar insights agregados del sistema HTN."""
        insights = self.integration.get_htn_insights()
        self.assertIsInstance(insights, dict)
        self.assertIn("htn_overview", insights)
        self.assertIn("executor_overview", insights)
        self.assertIn("integration_overview", insights)
        self.assertIn("system_health", insights)
        self.assertIn("status", insights["htn_overview"])
        self.assertIn("total_executions", insights["htn_overview"])
        self.assertIn("htn_available", insights["system_health"])
        self.assertTrue(insights["system_health"]["htn_available"])
        self.assertTrue(insights["system_health"]["integration_enabled"])


class TestHTNIntegrationSingleton(unittest.TestCase):
    """2.8.13.5.5 — Verificar singleton get_htn_integration"""

    def test_2_8_13_5_5_get_htn_integration_retorna_instancia(self):
        """get_htn_integration debe retornar una instancia de HTNBrainIntegration."""
        instance = get_htn_integration()
        self.assertIsInstance(instance, HTNBrainIntegration)

    def test_2_8_13_5_5_get_htn_integration_singleton(self):
        """get_htn_integration debe retornar siempre la misma instancia."""
        instance1 = get_htn_integration()
        instance2 = get_htn_integration()
        self.assertIs(instance1, instance2)


class TestHTNIntegrationSerialization(unittest.TestCase):
    """2.8.13.5.6 — Verificar serialización de tareas y resultados"""

    def setUp(self):
        self.integration = HTNBrainIntegration()

    def test_2_8_13_5_6_serialize_task(self):
        """_serialize_task debe convertir una Task a diccionario correctamente."""
        task = Task(id="t1", name="test_task", description="una tarea", dependencies=[])
        serialized = self.integration._serialize_task(task)
        self.assertIsInstance(serialized, dict)
        self.assertEqual(serialized["id"], "t1")
        self.assertEqual(serialized["name"], "test_task")
        self.assertEqual(serialized["description"], "una tarea")
        self.assertEqual(serialized["dependencies"], [])
        self.assertEqual(serialized["status"], "pending")

    def test_2_8_13_5_6_serialize_task_none(self):
        """_serialize_task debe manejar None con valores por defecto."""
        serialized = self.integration._serialize_task(None)
        self.assertIsInstance(serialized, dict)
        self.assertEqual(serialized["id"], "")
        self.assertEqual(serialized["name"], "")
        self.assertEqual(serialized["status"], None)

    def test_2_8_13_5_6_serialize_execution_result(self):
        """_serialize_execution_result debe convertir TaskExecutionResult a dict."""
        result = TaskExecutionResult(
            task_id="root",
            status=TaskStatus.COMPLETED,
            result={"message": "OK"},
            execution_time=1.5,
            subtask_results=[],
            error_message=None,
            new_state={"key": "value"},
        )
        serialized = self.integration._serialize_execution_result(result)
        self.assertIsInstance(serialized, dict)
        self.assertEqual(serialized["task_id"], "root")
        self.assertEqual(serialized["status"], "completed")
        self.assertTrue(serialized["success"])
        self.assertEqual(serialized["result"], {"message": "OK"})
        self.assertAlmostEqual(serialized["execution_time"], 1.5)
        self.assertIsNone(serialized["error_message"])


class TestHTNIntegrationProcessGoal(unittest.TestCase):
    """2.8.13.5.7 — Verificar process_goal_through_htn"""

    @classmethod
    def setUpClass(cls):
        cls._htn = get_htn_manager()

    def setUp(self):
        self.integration = HTNBrainIntegration()
        self.mock_executor = Mock()
        self.mock_executor.execute_task = Mock(return_value=TaskExecutionResult(
            task_id="t1",
            status=TaskStatus.COMPLETED,
            result={"message": "OK"},
            execution_time=0.1,
            subtask_results=[],
            new_state={"completed_tasks": ["t1"], "browser_available": True},
        ))
        self.mock_executor.get_execution_statistics = Mock(return_value={
            "status": "idle",
            "total_executions": 1,
            "total_attempts": 1,
            "successful_executions": 1,
            "failed_executions": 0,
            "success_rate": 1.0,
            "average_execution_time": 0.1,
            "current_task": None,
        })

    def test_2_8_13_5_7_process_goal_disabled(self):
        """Si la integración está deshabilitada, debe retornar resultado de fallo."""
        self.integration.enable_integration(False)
        result = self.integration.process_goal_through_htn(
            SimpleNamespace(id="test_goal", type="generic", target="test"),
            {}
        )
        self.assertFalse(result.success)
        self.assertIn("deshabilitada", result.message.lower())

    def test_2_8_13_5_7_process_goal_none(self):
        """Si el goal es None y está deshabilitado, el acceso a goal.id produce error."""
        self.integration.enable_integration(False)
        with self.assertRaises(AttributeError):
            self.integration.process_goal_through_htn(None, {})

    def test_2_8_13_5_7_process_goal_success(self):
        """Un Goal navegable válido debe descomponer y ejecutar exitosamente."""
        goal = Goal(
            id="test_navigate_goal",
            type="navigate",
            target="https://example.com",
            description="Navegar a example.com",
            priority=1,
        )
        with patch.object(self._htn, "_task_executor", self.mock_executor), \
             patch.object(self._htn, "_get_task_executor", return_value=self.mock_executor):
            result = self.integration.process_goal_through_htn(goal, {"browser_available": True})
        self.assertTrue(result.success)
        self.assertEqual(result.goal_id, "test_navigate_goal")
        self.assertEqual(result.goal_type, "navigate")
        self.assertGreater(len(result.decomposed_tasks), 0)

    def test_2_8_13_5_7_process_goal_invalid_type(self):
        """Un Goal con id vacío debe fallar."""
        goal = SimpleNamespace(id="", type="generic", target="test")
        result = self.integration.process_goal_through_htn(goal, {})
        self.assertFalse(result.success)

    def test_2_8_13_5_7_create_and_execute_empty_input(self):
        """create_and_execute_htn_goal con input vacío debe retornar fracaso."""
        result = self.integration.create_and_execute_htn_goal("", {})
        self.assertFalse(result.success)
        self.assertIn("objetivo", result.message.lower())

    def test_2_8_13_5_7_create_and_execute_none_input(self):
        """create_and_execute_htn_goal con input None debe retornar fracaso."""
        result = self.integration.create_and_execute_htn_goal(None, {})
        self.assertFalse(result.success)

    def test_2_8_13_5_7_create_and_execute_valid_input(self):
        """create_and_execute_htn_goal con input válido debe procesar el goal."""
        goal = Goal(
            id="test_valid_goal",
            type="navigate",
            target="https://example.com",
            description="Navegar a example.com",
            priority=1,
        )
        with patch.object(self.integration, "_create_goal_from_input", return_value=goal), \
             patch.object(self._htn, "_task_executor", self.mock_executor), \
             patch.object(self._htn, "_get_task_executor", return_value=self.mock_executor):
            result = self.integration.create_and_execute_htn_goal("navegar example.com", {"browser_available": True})
        self.assertTrue(result.success)
        self.assertEqual(result.goal_id, "test_valid_goal")


class TestHTNIntegrationResultDataclass(unittest.TestCase):
    """2.8.13.5.8 — Verificar HTNIntegrationResult dataclass"""

    def test_2_8_13_5_8_result_defaults(self):
        """HTNIntegrationResult debe retornar los valores provistos correctamente."""
        result = HTNIntegrationResult(
            success=True,
            goal_id="test",
            goal_type="generic",
            decomposed_tasks=[],
            execution_results=[],
            total_execution_time=0.0,
            message="",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.goal_id, "test")
        self.assertEqual(result.goal_type, "generic")
        self.assertEqual(result.decomposed_tasks, [])
        self.assertEqual(result.execution_results, [])
        self.assertAlmostEqual(result.total_execution_time, 0.0)
        self.assertEqual(result.message, "")
        self.assertIsNone(result.error_message)
        self.assertIsNone(result.final_state)

    def test_2_8_13_5_8_result_with_values(self):
        """HTNIntegrationResult debe almacenar todos los valores provistos."""
        result = HTNIntegrationResult(
            success=False,
            goal_id="goal_1",
            goal_type="open_application",
            decomposed_tasks=[{"id": "t1"}],
            execution_results=[{"id": "r1"}],
            total_execution_time=2.5,
            message="mensaje",
            error_message="error",
            final_state={"key": "value"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.goal_id, "goal_1")
        self.assertEqual(result.goal_type, "open_application")
        self.assertEqual(len(result.decomposed_tasks), 1)
        self.assertEqual(len(result.execution_results), 1)
        self.assertAlmostEqual(result.total_execution_time, 2.5)
        self.assertEqual(result.message, "mensaje")
        self.assertEqual(result.error_message, "error")
        self.assertEqual(result.final_state, {"key": "value"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
