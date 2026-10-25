"""
Adaptador de compatibilidad para la calibración de Microsoft Edge.

La calibración real se realiza mediante el sistema universal:

    CalibrationManager
        -> descubrimiento de aplicación
        -> apertura/enfoque
        -> detección de ventana
        -> ScreenManager
        -> captura del monitor real
        -> UniversalVisualCalibrator
        -> Qwen3-VL 8B Instruct
        -> coordenadas absolutas
        -> guardado centralizado

Este módulo NO:
- asume 1 o 2 monitores;
- calcula offsets;
- utiliza pyautogui.size() para determinar monitores;
- asume resoluciones;
- asume DPI;
- genera coordenadas manuales;
- analiza elementos uno por uno;
- escribe macros_coords.json directamente.

Se conserva únicamente para compatibilidad con código antiguo que pueda
importar EdgeCalibrator o calibrate_edge().
"""

from src.utils.logger import get_logger
from typing import Any, Dict, Optional


logger = get_logger(__name__)


# ============================================================================
# CALIBRADOR DE COMPATIBILIDAD
# ============================================================================


class EdgeCalibrator:
    """
    Adaptador legacy hacia CalibrationManager.

    La lógica real de calibración pertenece al sistema universal.
    """

    def __init__(self) -> None:
        from src.hands.calibration_manager import CalibrationManager

        self.calibration_manager = CalibrationManager()

        logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


    # ========================================================================
    # API LEGACY
    # ========================================================================

    def calibrate_edge_both_screens(
        self,
    ) -> Dict[str, Any]:
        """
        Mantiene la API antigua por compatibilidad.

        El nombre histórico hacía referencia a dos pantallas, pero el sistema
        actual trabaja con cualquier número de monitores.
        """

        logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


        try:
            result = self._calibrate_edge_universal()

            return {
                "edge": result,
            }

        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


            return {
                "edge": {
                    "success": False,
                    "application": "edge",
                    "error": str(e),
                }
            }

    def calibrate_edge(
        self,
    ) -> Dict[str, Any]:
        """
        API moderna de compatibilidad.

        Delega directamente en CalibrationManager.
        """

        logger._print_log("info", r"Solicitada calibración universal de Edge. [file:calibrator_edge.py, method:calibrate_edge, line:111]", "calibrator_edge.py", "method", 102)


        try:
            return self._calibrate_edge_universal()

        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


            return {
                "success": False,
                "application": "edge",
                "error": str(e),
            }

    # ========================================================================
    # DELEGACIÓN UNIVERSAL
    # ========================================================================

    def _calibrate_edge_universal(
        self,
    ) -> Dict[str, Any]:
        """
        Delega Edge en CalibrationManager.

        No selecciona monitores.
        No captura pantallas.
        No calcula coordenadas.
        No analiza elementos directamente.
        """

        calibrate_method = getattr(
            self.calibration_manager,
            "calibrate_application",
            None,
        )

        if not callable(calibrate_method):
            logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


        application_candidates = (
            "Microsoft Edge",
            "Edge",
        )

        last_error: Optional[Exception] = None

        for application_name in application_candidates:
            try:
                logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


                result = calibrate_method(application_name)

                if isinstance(result, dict):
                    result.setdefault(
                        "application",
                        "edge",
                    )

                    return result

                return {
                    "success": bool(result),
                    "application": "edge",
                    "result": result,
                }

            except Exception as e:
                last_error = e

                logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


        if last_error is not None:
            logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)

            raise last_error

        logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)

        raise RuntimeError(
            "No se pudo localizar Microsoft Edge mediante CalibrationManager."
        )


# ============================================================================
# FUNCIÓN PÚBLICA LEGACY
# ============================================================================


def calibrate_edge() -> str:
    """
    Función pública de compatibilidad.

    No escribe macros_coords.json.
    """

    logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


    try:
        calibrator = EdgeCalibrator()

        result = calibrator.calibrate_edge()

        if not isinstance(result, dict):
            return "Calibración universal de Edge ejecutada."

        if result.get("success"):
            total_elements = result.get(
                "total_elements",
                result.get(
                    "elements_detected",
                    0,
                ),
            )

            return (
                "Calibración universal de Edge completada. "
                f"Elementos detectados: {total_elements}."
            )

        if result.get("error"):
            return f"Error en la calibración universal de Edge: {result['error']}"

        return "Calibración universal de Edge ejecutada."

    except Exception as e:
        logger._print_log("info", "Procesando solicitud", "calibrator_edge.py", "method", 55)


        return f"Error en la calibración universal de Edge: {str(e)}"
