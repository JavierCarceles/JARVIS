"""
Adaptador de compatibilidad para la calibración de Mozilla Firefox.

IMPORTANTE:
La calibración real ya NO se realiza mediante lógica específica de Firefox.

El flujo oficial es:

    CalibrationManager
        -> detección de aplicación
        -> apertura/enfoque
        -> ScreenManager
        -> captura del monitor
        -> UniversalVisualCalibrator
        -> Qwen3-VL 8B Instruct
        -> coordenadas absolutas
        -> guardado centralizado

Este módulo existe únicamente para mantener compatibilidad con código
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

from src.utils.logger import get_logger
from typing import Any, Dict

from src.hands.calibration_manager import CalibrationManager


logger = get_logger(__name__)


# ============================================================================
# CALIBRADOR LEGACY
# ============================================================================


class FirefoxCalibrator:
    """
    Adaptador legacy hacia CalibrationManager.

    No contiene lógica visual específica de Firefox.
    """

    def __init__(self) -> None:
        self.calibration_manager = CalibrationManager()

        logger._print_log("info", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 56)


    # ========================================================================
    # API LEGACY
    # ========================================================================

    def calibrate_firefox_both_screens(
        self,
    ) -> Dict[str, Any]:
        """
        Mantiene el nombre antiguo por compatibilidad.

        El nombre histórico hablaba de "ambas pantallas", pero esa lógica
        ya no existe. El sistema actual debe trabajar con cualquier número
        de monitores.

        Esta función delega la calibración exclusivamente en el sistema
        universal.
        """
        logger._print_log("warning", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 76)


        try:
            result = self._calibrate_firefox_universal()

            return {
                "firefox": result,
            }

        except Exception as e:
            logger._print_log("error", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 87)


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

        Delegación directa al flujo universal.
        """
        logger._print_log("info", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 104)


        try:
            return self._calibrate_firefox_universal()

        except Exception as e:
            logger._print_log("error", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 111)


            return {
                "success": False,
                "application": "firefox",
                "error": str(e),
            }

    # ========================================================================
    # DELEGACIÓN UNIVERSAL
    # ========================================================================

    def _calibrate_firefox_universal(
        self,
    ) -> Dict[str, Any]:
        """
        Delega Firefox al CalibrationManager universal.

        No realiza ninguna operación de pantalla directamente.
        """

        manager = self.calibration_manager

        # El método universal previsto por CalibrationManager es
        # calibrate_application().
        calibrate_method = getattr(
            manager,
            "calibrate_application",
            None,
        )

        if not callable(calibrate_method):
            raise AttributeError(
                "CalibrationManager no dispone de calibrate_application()"
            )

        # Firefox puede aparecer en Get-StartApps como Mozilla Firefox.
        application_candidates = (
            "Mozilla Firefox",
            "Firefox",
        )

        last_error = None

        for application_name in application_candidates:
            try:
                logger._print_log("info", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 158)


                result = calibrate_method(application_name)

                if isinstance(result, dict):
                    result.setdefault(
                        "application",
                        "firefox",
                    )

                    return result

                return {
                    "success": bool(result),
                    "application": "firefox",
                    "result": result,
                }

            except Exception as e:
                last_error = e

                logger._print_log("debug", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 180)


        if last_error is not None:
            raise last_error

        raise RuntimeError("No se pudo localizar Firefox mediante CalibrationManager.")


# ============================================================================
# FUNCIÓN PÚBLICA LEGACY
# ============================================================================


def calibrate_firefox() -> str:
    """
    Función pública de compatibilidad.

    IMPORTANTE:
    No escribe macros_coords.json.

    El guardado de coordenadas pertenece al flujo universal.
    """

    logger._print_log("info", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 204)


    try:
        calibrator = FirefoxCalibrator()

        result = calibrator.calibrate_firefox()

        if not isinstance(result, dict):
            return "Calibración universal de Firefox ejecutada."

        if result.get("success"):
            total_elements = result.get(
                "total_elements",
                result.get("elements_detected", 0),
            )

            return (
                "Calibración universal de Firefox completada. "
                f"Elementos detectados: {total_elements}."
            )

        if result.get("error"):
            return f"Error en la calibración universal de Firefox: {result['error']}"

        return "Calibración universal de Firefox ejecutada."

    except Exception as e:
        logger._print_log("error", "procesando solicitud", "src\hands\firefox\calibrator_firefox.py", "method", 232)


        return f"Error en la calibración universal de Firefox: {str(e)}"
