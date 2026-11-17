"""
Adaptador de compatibilidad para la calibracion de Mozilla Firefox.

IMPORTANTE:
La calibracion real ya NO se realiza mediante logica especifica de Firefox.

El flujo oficial es:

    CalibrationManager
        -> deteccion de aplicacion
        -> apertura/enfoque
        -> ScreenManager
        -> captura del monitor
        -> UniversalVisualCalibrator
        -> Qwen3-VL 8B Instruct
        -> coordenadas absolutas
        -> guardado centralizado

Este modulo existe unicamente para mantener compatibilidad con codigo
antiguo que pudiera importar FirefoxCalibrator o calibrate_firefox().

NO:
- detecta coordenadas manualmente;
- calcula offsets de monitores;
- asume dos pantallas;
- asume resoluciones;
- asume DPI;
- genera coordenadas artificiales;
- escribe macros_coords.json directamente.
"""

from src.core.log import get_logger
from typing import Any, Dict

from src.hands.calibration.calibration_manager import get_calibration_manager


logger = get_logger(__name__)


# ============================================================================
# CALIBRADOR LEGACY
# ============================================================================


class FirefoxCalibrator:
    """
    Adaptador legacy hacia CalibrationManager.

    No contiene logica visual especifica de Firefox.
    """

    def __init__(self) -> None:
        self.calibration_manager = get_calibration_manager()



    # ========================================================================
    # API LEGACY
    # ========================================================================

    def calibrate_firefox_both_screens(
        self,
    ) -> Dict[str, Any]:
        """
        Mantiene el nombre antiguo por compatibilidad.

        El nombre historico hablaba de "ambas pantallas", pero esa logica
        ya no existe. El sistema actual debe trabajar con cualquier numero
        de monitores.

        Esta funcion delega la calibracion exclusivamente en el sistema
        universal.
        """


        try:
            result = self._calibrate_firefox_universal()

            return {
                "firefox": result,
            }

        except Exception as e:
            logger.error("FirefoxCalibrator.calibrate_firefox_both_screens: %s", e)


            return {
                "firefox": {
                    "error": str(e),
                }
            }

    def calibrate_firefox(
        self,
    ) -> Dict[str, Any]:
        """
        API moderna de compatibilidad.

        Delegacion directa al flujo universal.
        """


        try:
            return self._calibrate_firefox_universal()

        except Exception as e:
            logger.error("FirefoxCalibrator.calibrate_firefox: %s", e)


            return {
                "success": False,
                "application": "firefox",
                "error": str(e),
            }

    # ========================================================================
    # DELEGACION UNIVERSAL
    # ========================================================================

    def _calibrate_firefox_universal(
        self,
    ) -> Dict[str, Any]:
        """
        Delega Firefox al CalibrationManager universal.

        No realiza ninguna operacion de pantalla directamente.
        """

        from src.hands.calibration.calibration_pipeline import delegate_legacy_calibration

        # Una sola delegacion: el lanzador resuelve "firefox" por alias en el
        # catalogo/descubrimiento; ``success`` refleja el resultado real.
        result = delegate_legacy_calibration("firefox", manager=self.calibration_manager)
        result["application"] = "firefox"
        return result


# ============================================================================
# FUNCION PUBLICA LEGACY
# ============================================================================


def calibrate_firefox() -> str:
    """
    Funcion publica de compatibilidad.

    IMPORTANTE:
    No escribe macros_coords.json.

    El guardado de coordenadas pertenece al flujo universal.
    """



    try:
        calibrator = FirefoxCalibrator()

        result = calibrator.calibrate_firefox()

        if not isinstance(result, dict):
            return "Calibraci\u00f3n universal de Firefox ejecutada."

        if result.get("success"):
            total_elements = result.get(
                "total_elements",
                result.get("elements_detected", 0),
            )

            return (
                "Calibraci\u00f3n universal de Firefox completada. "
                f"Elementos detectados: {total_elements}."
            )

        if result.get("error"):
            return f"Error en la calibraci\u00f3n universal de Firefox: {result['error']}"

        return "Calibraci\u00f3n universal de Firefox ejecutada."

    except Exception as e:
        logger.error("calibrate_firefox: %s", e)


        return f"Error en la calibraci\u00f3n universal de Firefox: {str(e)}"
