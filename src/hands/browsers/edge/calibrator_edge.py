"""
Adaptador de compatibilidad para la calibracion de Microsoft Edge.

La calibracion real se realiza mediante el sistema universal:

    CalibrationManager
        -> descubrimiento de aplicacion
        -> apertura/enfoque
        -> deteccion de ventana
        -> ScreenManager
        -> captura del monitor real
        -> UniversalVisualCalibrator
        -> Qwen3-VL 8B Instruct
        -> coordenadas absolutas
        -> guardado centralizado

Este modulo NO:
- asume 1 o 2 monitores;
- calcula offsets;
- utiliza pyautogui.size() para determinar monitores;
- asume resoluciones;
- asume DPI;
- genera coordenadas manuales;
- analiza elementos uno por uno;
- escribe macros_coords.json directamente.

Se conserva unicamente para compatibilidad con codigo antiguo que pueda
importar EdgeCalibrator o calibrate_edge().
"""

from src.core.log import get_logger
from typing import Any, Dict, Optional


logger = get_logger(__name__)


# ============================================================================
# CALIBRADOR DE COMPATIBILIDAD
# ============================================================================


class EdgeCalibrator:
    """
    Adaptador legacy hacia CalibrationManager.

    La logica real de calibracion pertenece al sistema universal.
    """

    def __init__(self) -> None:
        from src.hands.calibration.calibration_manager import get_calibration_manager

        self.calibration_manager = get_calibration_manager()



    # ========================================================================
    # API LEGACY
    # ========================================================================

    def calibrate_edge_both_screens(
        self,
    ) -> Dict[str, Any]:
        """
        Mantiene la API antigua por compatibilidad.

        El nombre historico hacia referencia a dos pantallas, pero el sistema
        actual trabaja con cualquier numero de monitores.
        """



        try:
            result = self._calibrate_edge_universal()

            return {
                "edge": result,
            }

        except Exception as e:
            logger.debug("EdgeCalibrator.calibrate_edge_both_screens: %s", e)


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

        logger.info(r"Solicitada calibracion universal de Edge.")


        try:
            return self._calibrate_edge_universal()

        except Exception as e:
            logger.debug("EdgeCalibrator.calibrate_edge: %s", e)


            return {
                "success": False,
                "application": "edge",
                "error": str(e),
            }

    # ========================================================================
    # DELEGACION UNIVERSAL
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

        from src.hands.calibration.calibration_pipeline import delegate_legacy_calibration

        # Una sola delegacion: el lanzador resuelve "edge" por alias en el
        # catalogo/descubrimiento; ``success`` refleja el resultado real.
        result = delegate_legacy_calibration("edge", manager=self.calibration_manager)
        result["application"] = "edge"
        return result


# ============================================================================
# FUNCION PUBLICA LEGACY
# ============================================================================


def calibrate_edge() -> str:
    """
    Funcion publica de compatibilidad.

    No escribe macros_coords.json.
    """



    try:
        calibrator = EdgeCalibrator()

        result = calibrator.calibrate_edge()

        if not isinstance(result, dict):
            return "Calibraci\u00f3n universal de Edge ejecutada."

        if result.get("success"):
            total_elements = result.get(
                "total_elements",
                result.get(
                    "elements_detected",
                    0,
                ),
            )

            return (
                "Calibraci\u00f3n universal de Edge completada. "
                f"Elementos detectados: {total_elements}."
            )

        if result.get("error"):
            return f"Error en la calibraci\u00f3n universal de Edge: {result['error']}"

        return "Calibraci\u00f3n universal de Edge ejecutada."

    except Exception as e:
        logger.debug("calibrate_edge: %s", e)


        return f"Error en la calibraci\u00f3n universal de Edge: {str(e)}"
