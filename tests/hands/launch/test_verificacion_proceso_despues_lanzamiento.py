# -*- coding: utf-8 -*-
"""Tests unitarios para la unidad 3.8.5.5.1.

Cubre:
- verify_launch_process_stability: proceso vivo en todas las comprobaciones -> estable
- verify_launch_process_stability: proceso muere durante el intervalo -> no estable
- verify_launch_process_stability: sin PID -> error
- get_launch_evidence: evidencia de lanzamiento tras launch_application
- launch_application almacena ruta ejecutable y app_id para correlacion
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.hands.calibration.calibration_manager import CalibrationManager, LaunchState


class TestVerificacionProcesoDespuesLanzamiento(unittest.TestCase):
    """3.8.5.5.1 - Verificar proceso, ventana y estado posterior a la apertura."""

    def _make_manager(self):
        """Instancia CalibrationManager mockeando dependencias pesadas de __init__."""
        with patch(
            "src.hands.calibration.calibration_manager.get_screen_manager", return_value=MagicMock()
        ), patch(
            "src.hands.calibration.calibration_manager.get_calibration_config", return_value=MagicMock()
        ), patch(
            "src.hands.calibration.universal_visual_calibrator.UniversalVisualCalibrator",
            return_value=MagicMock(),
        ):
            manager = CalibrationManager()
        return manager

    def test_verificacion_estabilidad_proceso_vivo_todas_las_comprobaciones(self):
        """Proceso vivo en todas las comprobaciones -> estable."""
        manager = self._make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_was_owned = True
        manager._last_launch_owned_pids = {12345}
        manager._last_launch_owned_hwnds = {54321}

        with patch.object(manager, "_is_process_alive", return_value=True):
            resultado = manager.verify_launch_process_stability(
                pid=12345, stability_interval=2.0, stability_checks=3
            )

        self.assertTrue(resultado["alive"])
        self.assertTrue(resultado["stable"])
        self.assertEqual(resultado["pid"], 12345)
        self.assertEqual(resultado["checks_passed"], 3)
        self.assertEqual(resultado["total_checks"], 3)
        self.assertEqual(
            resultado["executable_path"], r"C:\Windows\System32\charmap.exe"
        )

    def test_verificacion_estabilidad_proceso_muere_a_mitad(self):
        """Proceso muere durante el intervalo -> no estable."""
        manager = self._make_manager()
        manager._last_launch_root_pid = 12345

        # Primera comprobacion viva, segunda y tercera muertas, cuarta muerta
        # (se llama una vez mas al final para obtener el estado actual).
        with patch.object(
            manager, "_is_process_alive", side_effect=[True, False, False, False]
        ):
            resultado = manager.verify_launch_process_stability(
                pid=12345, stability_interval=2.0, stability_checks=3
            )

        self.assertFalse(resultado["alive"])
        self.assertFalse(resultado["stable"])
        self.assertEqual(resultado["checks_passed"], 1)
        self.assertEqual(resultado["total_checks"], 3)

    def test_verificacion_estabilidad_sin_pid_retorna_error(self):
        """Sin PID para verificar -> error y no estable."""
        manager = self._make_manager()
        manager._last_launch_root_pid = None

        resultado = manager.verify_launch_process_stability()

        self.assertFalse(resultado["alive"])
        self.assertFalse(resultado["stable"])
        self.assertIsNone(resultado["pid"])
        self.assertEqual(resultado["error"], "No hay PID para verificar")

    def test_get_launch_evidence_devuelve_metadatos(self):
        """get_launch_evidence retorna los metadatos del ultimo lanzamiento."""
        manager = self._make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_owned_pids = {12345, 12346}
        manager._last_launch_owned_hwnds = {54321}
        manager._last_launch_was_owned = True
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""

        evidencia = manager.get_launch_evidence()

        self.assertEqual(evidencia["root_pid"], 12345)
        self.assertEqual(evidencia["owned_pids"], {12345, 12346})
        self.assertEqual(evidencia["owned_hwnds"], {54321})
        self.assertTrue(evidencia["was_owned"])
        self.assertEqual(
            evidencia["executable_path"], r"C:\Windows\System32\charmap.exe"
        )
        self.assertEqual(evidencia["app_id"], "")

    def test_launch_application_almacena_ruta_y_app_id(self):
        """launch_application almacena ruta ejecutable y app_id para correlacion."""
        manager = self._make_manager()
        app = {
            "name": "TestApp",
            "app_id": "TestApp.Package",
            "path": r"C:\Program Files\TestApp\testapp.exe",
            "arguments": "",
        }

        with patch.object(manager, "_should_ignore_application", return_value=False), \
             patch.object(manager, "_is_game_application", return_value=False), \
             patch.object(
                 manager, "_find_existing_application_window", return_value=None
             ), \
             patch.object(manager, "_get_window_handles", return_value=set()), \
             patch.object(manager, "_get_process_ids", return_value=set()), \
             patch("src.hands.calibration.calibration_manager.os.path.isfile", return_value=True), \
             patch("src.hands.calibration.calibration_manager.subprocess.Popen"), \
             patch.object(
                 manager, "_wait_for_application_window", return_value=None
             ):
            manager.launch_application(app)

        self.assertEqual(
            manager._last_launch_executable_path,
            r"C:\Program Files\TestApp\testapp.exe",
        )
        self.assertEqual(manager._last_launch_app_id, "TestApp.Package")

    def test_clasificar_tipo_destino_por_ruta(self):
        """Clasificacion de tipo de destino por extension de ruta."""
        manager = self._make_manager()
        self.assertEqual(
            manager._clasificar_tipo_destino_por_ruta(
                r"C:\Windows\System32\charmap.exe"
            ),
            "ejecutable",
        )
        self.assertEqual(
            manager._clasificar_tipo_destino_por_ruta(r"C:\Users\app.lnk"),
            "acceso_directo",
        )
        self.assertEqual(manager._clasificar_tipo_destino_por_ruta(""), "desconocido")
        self.assertEqual(manager._clasificar_tipo_destino_por_ruta(None), "desconocido")

    def test_guardar_evidencia_lanzamiento_escribe_json_sin_secretos(self):
        """guardar_evidencia_lanzamiento persiste evidencia JSON serializable y sin secretos."""
        manager = self._make_manager()
        manager._last_launch_root_pid = 12345
        manager._last_launch_owned_pids = {12345}
        manager._last_launch_owned_hwnds = {54321}
        manager._last_launch_was_owned = True
        manager._last_launch_executable_path = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_app_id = ""
        manager._last_launch_state = LaunchState.PROCESO_INICIADO
        manager._last_launch_tipo_destino = "ejecutable"
        manager._last_launch_fuente = "ruta_directa"
        manager._last_launch_destino_validado = r"C:\Windows\System32\charmap.exe"
        manager._last_launch_timestamps = {"inicio": 100.0}
        manager._last_launch_window_info = {"hwnd": 54321, "visible": True}

        with tempfile.TemporaryDirectory() as tmpdir:
            ruta = Path(tmpdir) / "evidencia.json"
            guardado = manager.guardar_evidencia_lanzamiento(str(ruta))
            self.assertEqual(guardado, str(ruta))
            self.assertTrue(ruta.exists(), "el archivo de evidencia no se escribio")
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            self.assertEqual(datos["root_pid"], 12345)
            self.assertEqual(datos["owned_pids"], [12345])
            self.assertEqual(datos["owned_hwnds"], [54321])
            self.assertTrue(datos["was_owned"])
            self.assertEqual(datos["tipo_destino"], "ejecutable")
            self.assertEqual(datos["fuente"], "ruta_directa")
            self.assertEqual(
                datos["destino_validado"], r"C:\Windows\System32\charmap.exe"
            )
            self.assertEqual(datos["ventana"]["hwnd"], 54321)
            self.assertIn("duracion_segundos", datos["timestamps"])
            self.assertNotIn("arguments", datos)
            self.assertNotIn("command_line", datos)


if __name__ == "__main__":
    unittest.main()
