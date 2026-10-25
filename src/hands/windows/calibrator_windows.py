"""
Adaptador de compatibilidad para la calibración de aplicaciones Windows.

La calibración real se realiza mediante el sistema universal:

    CalibrationManager
        -> descubrimiento de aplicación
        -> apertura/enfoque
        -> ScreenManager
        -> detección de monitor real
        -> captura
        -> UniversalVisualCalibrator
        -> Qwen3-VL 8B Instruct
        -> coordenadas absolutas
        -> guardado centralizado

Este módulo NO:
- asume 1 o 2 monitores;
- calcula offsets;
- utiliza pyautogui.size() para determinar monitores;
- asume resoluciones concretas;
- asume DPI;
- genera coordenadas manualmente;
- analiza elementos uno por uno con prompts independientes;
- escribe macros_coords.json directamente.

Se conserva únicamente para compatibilidad con código antiguo que todavía
pueda importar WindowsCalibrator o calibrate_app().
"""

from src.utils.logger import get_logger
from typing import Any, Dict, Optional


logger = get_logger(__name__)


# ============================================================================
# CALIBRADOR DE COMPATIBILIDAD
# ============================================================================


class WindowsCalibrator:
    """
    Adaptador legacy hacia CalibrationManager.

    No contiene lógica propia de coordenadas ni de visión.
    """

    def __init__(self) -> None:
        from src.hands.calibration_manager import CalibrationManager

        self.calibration_manager = CalibrationManager()

        logger.info(
            "[CALIBRATOR-WINDOWS] "
            "Adaptador inicializado. "
            "La calibración utiliza el flujo universal."
        )

    # ========================================================================
    # PROMPT LEGACY
    # ========================================================================

    def get_calibration_prompt(
        self,
        app_name: str,
    ) -> str:
        """
        Mantiene la API antigua por compatibilidad.

        El flujo universal actual no depende de este prompt.
        """

        return f"""
Analiza exclusivamente la interfaz visible de la aplicación
"{app_name}" presente en la captura.

Detecta elementos interactivos visibles que puedan utilizarse
mediante ratón o teclado.

No describas:
- escritorio;
- barra de tareas;
- otras aplicaciones;
- elementos no visibles;
- elementos puramente decorativos.

Para cada elemento devuelve:
- name;
- type;
- bbox;
- confidence.

Las coordenadas bbox deben estar normalizadas entre 0 y 1000
respecto a toda la imagen.

Formato:

{{
  "elements": [
    {{
      "name": "nombre_elemento",
      "type": "button",
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95
    }}
  ]
}}

Responde únicamente con JSON válido.
"""

    # ========================================================================
    # API PRINCIPAL LEGACY
    # ========================================================================

    def calibrate_app_both_screens(
        self,
        app_name: str,
    ) -> Dict[str, Any]:
        """
        Mantiene el nombre antiguo por compatibilidad.

        IMPORTANTE:
        El nombre histórico decía "both_screens", pero el sistema actual
        trabaja con cualquier número de monitores.

        No se limita a screen1/screen2.
        """
        logger.warning(
            "[CALIBRATOR-WINDOWS] "
            "calibrate_app_both_screens() es una API legacy. "
            "Delegando en CalibrationManager."
        )

        try:
            result = self._calibrate_universal(app_name)

            return {
                app_name: result,
            }

        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "calibrator_windows.py", "method", 145)


            return {
                app_name: {
                    "success": False,
                    "error": str(e),
                }
            }

    def calibrate_app(
        self,
        app_name: str,
    ) -> Dict[str, Any]:
        """
        API de compatibilidad para calibrar una aplicación concreta.

        La calibración la realiza íntegramente CalibrationManager.
        """
        logger.info(
            "[CALIBRATOR-WINDOWS] Solicitada calibración universal de %s",
            app_name,
        )

        return self._calibrate_universal(app_name)

    # ========================================================================
    # DELEGACIÓN UNIVERSAL
    # ========================================================================

    def _calibrate_universal(
        self,
        app_name: str,
    ) -> Dict[str, Any]:
        """
        Delega la calibración en CalibrationManager.

        No realiza detección, captura ni cálculo de coordenadas.
        """

        calibrate_method = getattr(
            self.calibration_manager,
            "calibrate_application",
            None,
        )

        if not callable(calibrate_method):
            raise AttributeError(
                "CalibrationManager no dispone de calibrate_application()."
            )

        logger.info(
            "[CALIBRATOR-WINDOWS] Delegando '%s' al calibrador universal",
            app_name,
        )

        result = calibrate_method(app_name)

        if isinstance(result, dict):
            return result

        return {
            "success": bool(result),
            "application": app_name,
            "result": result,
        }


# ============================================================================
# FUNCIÓN PÚBLICA LEGACY
# ============================================================================


def calibrate_app(
    app_name: str,
) -> str:
    """
    Función pública de compatibilidad.

    No escribe macros_coords.json.

    El guardado de coordenadas pertenece al flujo universal.
    """

    logger._print_log("info", "Procesando solicitud", "calibrator_windows.py", "method", 145)


    try:
        calibrator = WindowsCalibrator()

        result = calibrator.calibrate_app(app_name)

        if not isinstance(result, dict):
            return f"Calibración universal de {app_name} ejecutada."

        if result.get("success"):
            total_elements = result.get(
                "total_elements",
                result.get(
                    "elements_detected",
                    0,
                ),
            )

            return (
                f"Calibración universal de {app_name} completada. "
                f"Elementos detectados: {total_elements}."
            )

        if result.get("error"):
            return f"Error en la calibración universal de {app_name}: {result['error']}"

        return f"Calibración universal de {app_name} ejecutada."

    except Exception as e:
        logger._print_log("info", "Procesando solicitud", "calibrator_windows.py", "method", 145)


        return f"Error en calibración de {app_name}: {str(e)}"
