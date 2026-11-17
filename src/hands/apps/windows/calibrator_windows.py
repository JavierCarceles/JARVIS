"""
Adaptador de compatibilidad para la calibracion de aplicaciones Windows.

La calibracion real se realiza mediante el sistema universal:

    CalibrationManager
        -> descubrimiento de aplicacion
        -> apertura/enfoque
        -> ScreenManager
        -> deteccion de monitor real
        -> captura
        -> UniversalVisualCalibrator
        -> Qwen3-VL 8B Instruct
        -> coordenadas absolutas
        -> guardado centralizado

Este modulo NO:
- asume 1 o 2 monitores;
- calcula offsets;
- utiliza pyautogui.size() para determinar monitores;
- asume resoluciones concretas;
- asume DPI;
- genera coordenadas manualmente;
- analiza elementos uno por uno con prompts independientes;
- escribe macros_coords.json directamente.

Se conserva unicamente para compatibilidad con codigo antiguo que todavia
pueda importar WindowsCalibrator o calibrate_app().
"""

from src.core.log import get_logger
from typing import Any, Dict, Optional


logger = get_logger(__name__)


# ============================================================================
# CALIBRADOR DE COMPATIBILIDAD
# ============================================================================


class WindowsCalibrator:
    """
    Adaptador legacy hacia CalibrationManager.

    No contiene logica propia de coordenadas ni de vision.
    """

    def __init__(self) -> None:
        from src.hands.calibration.calibration_manager import CalibrationManager

        self.calibration_manager = CalibrationManager()

        logger.info(
            "[CALIBRATOR-WINDOWS] "
            "Adaptador inicializado. "
            "La calibracion utiliza el flujo universal."
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
Analiza exclusivamente la interfaz visible de la aplicaci\u00f3n
"{app_name}" presente en la captura.

Detecta elementos interactivos visibles que puedan utilizarse
mediante rat\u00f3n o teclado.

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

Responde \u00fanicamente con JSON v\u00e1lido.
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
        El nombre historico decia "both_screens", pero el sistema actual
        trabaja con cualquier numero de monitores.

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
            logger.debug("WindowsCalibrator.calibrate_app_both_screens: %s", e)


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
        API de compatibilidad para calibrar una aplicacion concreta.

        La calibracion la realiza integramente CalibrationManager.
        """
        logger.info(
            "[CALIBRATOR-WINDOWS] Solicitada calibracion universal de %s",
            app_name,
        )

        return self._calibrate_universal(app_name)

    # ========================================================================
    # DELEGACION UNIVERSAL
    # ========================================================================

    def _calibrate_universal(
        self,
        app_name: str,
    ) -> Dict[str, Any]:
        """
        Delega la calibracion en CalibrationManager.

        No realiza deteccion, captura ni calculo de coordenadas.
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
# FUNCION PUBLICA LEGACY
# ============================================================================


def calibrate_app(
    app_name: str,
) -> str:
    """
    Funcion publica de compatibilidad.

    No escribe macros_coords.json.

    El guardado de coordenadas pertenece al flujo universal.
    """



    try:
        calibrator = WindowsCalibrator()

        result = calibrator.calibrate_app(app_name)

        if not isinstance(result, dict):
            return f"Calibraci\u00f3n universal de {app_name} ejecutada."

        if result.get("success"):
            total_elements = result.get(
                "total_elements",
                result.get(
                    "elements_detected",
                    0,
                ),
            )

            return (
                f"Calibraci\u00f3n universal de {app_name} completada. "
                f"Elementos detectados: {total_elements}."
            )

        if result.get("error"):
            return f"Error en la calibraci\u00f3n universal de {app_name}: {result['error']}"

        return f"Calibraci\u00f3n universal de {app_name} ejecutada."

    except Exception as e:
        logger.debug("calibrate_app: %s", e)


        return f"Error en calibraci\u00f3n de {app_name}: {str(e)}"
