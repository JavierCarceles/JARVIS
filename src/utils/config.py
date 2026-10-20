from __future__ import annotations

"""
Configuración centralizada del sistema Jarvis.

Este módulo proporciona:
- Configuración unificada para todos los componentes de Jarvis
- Validación automática de configuraciones
- Sistema de herencia de configuraciones
- Gestión de perfiles de usuario
- Integración con sistema de calibración
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.utils.logger import get_logger

logger = get_logger(__name__)
"""""
IMPORTANTE SOBRE MONITORES:
- Este módulo NO determina la topología física del sistema.
- En Windows, la geometría real de los monitores la obtiene
  src.utils.screen_manager mediante Win32.
- Los campos de pantalla de este archivo se mantienen por compatibilidad
  con módulos antiguos y como configuración auxiliar.
- No se utilizan resoluciones, posiciones ni escalas concretas de una
  máquina como valores de verdad del sistema.
"""

logger = get_logger(__name__)


# ============================================================================
# RUTAS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"

VOICE_PREFERENCE_PATH = PROJECT_ROOT / "data" / "voice_preference.json"


# ============================================================================
# CONFIGURACIONES ESPECÍFICAS
# ============================================================================


@dataclass
class SystemConfig:
    """Configuración general del sistema Jarvis."""

    name: str = "Jarvis"
    version: str = "1.0.0"
    debug_mode: bool = False
    coordinate_system: str = "native_pixels"


@dataclass
class LoggingConfig:
    """Configuración del sistema de logging."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(location)s - %(levelname)s - %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    log_file: str = "logs/jarvis.log"


@dataclass
class KeyboardConfig:
    """Configuración de teclas de atajo."""

    fail_safe_enabled: bool = False
    pause_between_actions: float = 0.05


@dataclass
class VoiceConfig:
    """Configuración de voz."""

    default_voice_id: str = "am_eric"
    model_dir: str = "models"
    onnx_model_file: str = "model_fp16.onnx"
    voice_styles_dir: str = "models/voices"
    tokenizer_file: str = "models/tokenizer.json"
    config_file: str = "models/config.json"


@dataclass
class MemoryConfig:
    """Configuración de memoria."""

    chat_memory_file: str = "data/jarvis_memory.json"
    alias_memory_file: str = "config/command_aliases.json"
    max_history_length: int = 12


@dataclass
class PredictiveConfig:
    """Configuración del sistema predictivo."""

    enabled: bool = True
    learning_rate: float = 0.1
    prediction_threshold: float = 0.7
    max_predictions: int = 3
    min_usage_count: int = 3
    pattern_analysis_window: int = 50
    prediction_memory_file: str = "data/prediction_memory.json"
    time_window_hours: int = 24


@dataclass
class MonitorConfig:
    """
    Configuración compatible de un monitor.

    IMPORTANTE:
    Los valores físicos reales del monitor no deben utilizarse como fuente
    de verdad en Windows. ScreenManager los obtiene directamente del sistema.

    Estos campos existen para compatibilidad con config.json y módulos
    antiguos que todavía puedan consumir MonitorConfig.
    """

    id: int = 1
    name: str = "Monitor"
    width: int = 0
    height: int = 0
    scaled_width: int = 0
    scaled_height: int = 0
    x: int = 0
    y: int = 0
    scale_factor: float = 1.0
    is_primary: bool = False
    dpi: int = 96
    device_name: str = ""
    native_resolution: str = ""
    scaled_resolution: str = ""
    coordinate_system: str = "native_pixels"

    @property
    def right(self) -> int:
        """Coordenada X final del monitor."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Coordenada Y final del monitor."""
        return self.y + self.height


@dataclass
class ScreenConfig:
    """
    Configuración auxiliar de pantallas.

    La topología física real se obtiene de ScreenManager.
    """

    primary_screen_width: int = 0
    primary_screen_height: int = 0

    multi_screen_enabled: bool = True

    # Compatibilidad con código antiguo.
    # No debe utilizarse para determinar la posición de monitores.
    multi_screen_offset: int = 0

    capture_quality: float = 0.9

    screen_boundaries: Dict[str, int] = field(default_factory=dict)

    monitors: List[MonitorConfig] = field(default_factory=list)

    total_resolution: Dict[str, int] = field(default_factory=dict)

    setup_type: str = "unknown"

    scale_factor: float = 1.0

    use_scaled_coordinates: bool = False

    coordinate_conversion: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            "to_native": {
                "method": "identity",
                "factor": 1.0,
            },
            "from_native": {
                "method": "identity",
                "factor": 1.0,
            },
        }
    )

    @property
    def monitor_count(self) -> int:
        """Número de monitores configurados en el JSON."""
        return len(self.monitors)

    def get_monitor(
        self,
        monitor_id: int,
    ) -> Optional[MonitorConfig]:
        """Obtiene un monitor por ID."""
        for monitor in self.monitors:
            if monitor.id == monitor_id:
                return monitor

        return None

    def get_primary_monitor(
        self,
    ) -> Optional[MonitorConfig]:
        """Obtiene el monitor marcado como principal."""

        for monitor in self.monitors:
            if monitor.is_primary:
                return monitor

        return self.monitors[0] if self.monitors else None


@dataclass
class TimeoutConfig:
    """Configuración de timeouts."""

    ollama_call: float = 30.0
    screen_capture: float = 5.0
    click_delay: float = 1.5
    typing_interval: float = 0.005


@dataclass
class CalibrationConfig:
    """Configuración del sistema de calibración."""

    enabled: bool = True
    max_applications: int = 3
    max_attempts_per_element: int = 10
    screen_analysis_delay: float = 2.0
    element_detection_confidence: float = 0.7
    save_calibration_data: bool = True
    auto_backup_existing_data: bool = True
    use_native_coordinates: bool = True

    # Ya no representa la escala física de un monitor concreto.
    scale_factor: float = 1.0

    coordinate_system: str = "native_pixels"
    calibration_screen: int = 1

    # Compatibilidad con configuraciones antiguas.
    monitor_offset: Dict[str, int] = field(default_factory=dict)


@dataclass
class ChromeConfig:
    """Configuración de Google Chrome para aperturas automáticas."""

    default_width: int = 1200
    default_height: int = 800
    maximized: bool = False

    position: Dict[str, int] = field(
        default_factory=lambda: {
            "x": 100,
            "y": 100,
        }
    )


# ============================================================================
# CONFIGURACIÓN PRINCIPAL
# ============================================================================


@dataclass
class Config:
    """Configuración principal del sistema."""

    system: SystemConfig = field(default_factory=SystemConfig)

    logging: LoggingConfig = field(default_factory=LoggingConfig)

    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)

    voice: VoiceConfig = field(default_factory=VoiceConfig)

    memory: MemoryConfig = field(default_factory=MemoryConfig)

    screen: ScreenConfig = field(default_factory=ScreenConfig)

    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)

    predictive: PredictiveConfig = field(default_factory=PredictiveConfig)

    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)

    chrome: ChromeConfig = field(default_factory=ChromeConfig)

    element_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ============================================================================
# HELPERS DE VOZ
# ============================================================================


def _voice_file_exists(
    voice_id: str,
    voice_styles_dir: str,
) -> bool:
    """
    Comprueba si existe el archivo .bin de una voz.
    """

    voice_id = str(voice_id).strip()

    if not voice_id:
        return False

    voice_path = PROJECT_ROOT / voice_styles_dir / f"{voice_id}.bin"

    return voice_path.exists()


def load_saved_voice_preference() -> Optional[str]:
    """
    Carga la última voz seleccionada por el usuario.
    """

    try:
        if not VOICE_PREFERENCE_PATH.exists():
            return None

        with open(
            VOICE_PREFERENCE_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(
            data,
            dict,
        ):
            return None

        voice_id = str(
            data.get(
                "voice_id",
                "",
            )
        ).strip()

        return voice_id or None

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None


def save_voice_preference(
    voice_id: str,
) -> bool:
    """
    Guarda la voz actualmente seleccionada.
    """

    voice_id = str(voice_id).strip()

    if not voice_id:
        return False

    try:
        VOICE_PREFERENCE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = VOICE_PREFERENCE_PATH.with_suffix(".json.tmp")

        with open(
            temp_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    "voice_id": voice_id,
                },
                file,
                indent=2,
                ensure_ascii=False,
            )

        temp_path.replace(
            VOICE_PREFERENCE_PATH,
        )

        return True

    except OSError:
        return False


# ============================================================================
# HELPERS DE CARGA
# ============================================================================


def _load_monitor(
    monitor_data: Dict[str, Any],
) -> MonitorConfig:
    """
    Convierte el bloque JSON de un monitor en MonitorConfig.

    Los defaults son neutros; no contienen geometría de una máquina concreta.
    """

    monitor_id = int(
        monitor_data.get(
            "id",
            1,
        )
    )

    width = int(
        monitor_data.get(
            "width",
            0,
        )
    )

    height = int(
        monitor_data.get(
            "height",
            0,
        )
    )

    scaled_width = int(
        monitor_data.get(
            "scaled_width",
            0,
        )
    )

    scaled_height = int(
        monitor_data.get(
            "scaled_height",
            0,
        )
    )

    scale_factor = float(
        monitor_data.get(
            "scale_factor",
            1.0,
        )
        or 1.0
    )

    dpi = int(
        monitor_data.get(
            "dpi",
            round(96 * scale_factor),
        )
        or round(96 * scale_factor)
    )

    native_resolution = str(
        monitor_data.get(
            "native_resolution",
            (f"{width}x{height}" if width > 0 and height > 0 else ""),
        )
    )

    scaled_resolution = str(
        monitor_data.get(
            "scaled_resolution",
            (
                f"{scaled_width}x{scaled_height}"
                if scaled_width > 0 and scaled_height > 0
                else ""
            ),
        )
    )

    return MonitorConfig(
        id=monitor_id,
        name=str(
            monitor_data.get(
                "name",
                f"Monitor {monitor_id}",
            )
        ),
        width=width,
        height=height,
        scaled_width=scaled_width,
        scaled_height=scaled_height,
        x=int(
            monitor_data.get(
                "x",
                0,
            )
        ),
        y=int(
            monitor_data.get(
                "y",
                0,
            )
        ),
        scale_factor=scale_factor,
        is_primary=bool(
            monitor_data.get(
                "is_primary",
                False,
            )
        ),
        dpi=dpi,
        device_name=str(
            monitor_data.get(
                "device_name",
                "",
            )
        ),
        native_resolution=native_resolution,
        scaled_resolution=scaled_resolution,
        coordinate_system=str(
            monitor_data.get(
                "coordinate_system",
                "native_pixels",
            )
        ),
    )


def _load_default_monitors() -> List[MonitorConfig]:
    """
    No inventa monitores.

    La detección real se realiza en ScreenManager.
    """

    return []


# ============================================================================
# CARGA DE CONFIGURACIÓN
# ============================================================================


def load_config() -> Config:
    """
    Carga la configuración desde config/config.json.

    Si el fichero no existe o contiene JSON inválido, se utiliza la
    configuración neutral por defecto.
    """

    try:
        with open(
            CONFIG_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            config_data = json.load(file)

        if not isinstance(
            config_data,
            dict,
        ):
            config_data = {}

        config = Config()

        # --------------------------------------------------------------------
        # SYSTEM
        # --------------------------------------------------------------------

        system_data = config_data.get("system")

        if isinstance(
            system_data,
            dict,
        ):
            config.system.name = str(
                system_data.get(
                    "name",
                    config.system.name,
                )
            )

            config.system.version = str(
                system_data.get(
                    "version",
                    config.system.version,
                )
            )

            config.system.debug_mode = bool(
                system_data.get(
                    "debug_mode",
                    config.system.debug_mode,
                )
            )

            config.system.coordinate_system = str(
                system_data.get(
                    "coordinate_system",
                    config.system.coordinate_system,
                )
            )

        # --------------------------------------------------------------------
        # LOGGING
        # --------------------------------------------------------------------

        logging_data = config_data.get("logging")

        if isinstance(
            logging_data,
            dict,
        ):
            config.logging.level = str(
                logging_data.get(
                    "level",
                    config.logging.level,
                )
            )

            config.logging.format = str(
                logging_data.get(
                    "format",
                    config.logging.format,
                )
            )

            config.logging.datefmt = str(
                logging_data.get(
                    "datefmt",
                    config.logging.datefmt,
                )
            )

            config.logging.log_file = str(
                logging_data.get(
                    "log_file",
                    config.logging.log_file,
                )
            )

        # --------------------------------------------------------------------
        # KEYBOARD
        # --------------------------------------------------------------------

        keyboard_data = config_data.get("keyboard")

        if isinstance(
            keyboard_data,
            dict,
        ):
            config.keyboard.fail_safe_enabled = bool(
                keyboard_data.get(
                    "fail_safe_enabled",
                    config.keyboard.fail_safe_enabled,
                )
            )

            config.keyboard.pause_between_actions = float(
                keyboard_data.get(
                    "pause_between_actions",
                    config.keyboard.pause_between_actions,
                )
            )

        # --------------------------------------------------------------------
        # VOICE
        # --------------------------------------------------------------------

        voice_data = config_data.get("voice")

        if isinstance(
            voice_data,
            dict,
        ):
            config.voice.default_voice_id = str(
                voice_data.get(
                    "default_voice_id",
                    config.voice.default_voice_id,
                )
            )

            config.voice.model_dir = str(
                voice_data.get(
                    "model_dir",
                    config.voice.model_dir,
                )
            )

            config.voice.onnx_model_file = str(
                voice_data.get(
                    "onnx_model_file",
                    config.voice.onnx_model_file,
                )
            )

            config.voice.voice_styles_dir = str(
                voice_data.get(
                    "voice_styles_dir",
                    config.voice.voice_styles_dir,
                )
            )

            config.voice.tokenizer_file = str(
                voice_data.get(
                    "tokenizer_file",
                    config.voice.tokenizer_file,
                )
            )

            config.voice.config_file = str(
                voice_data.get(
                    "config_file",
                    config.voice.config_file,
                )
            )

        # --------------------------------------------------------------------
        # PREFERENCIA DE VOZ PERSISTENTE
        # --------------------------------------------------------------------

        saved_voice_id = load_saved_voice_preference()

        if saved_voice_id and _voice_file_exists(
            saved_voice_id,
            config.voice.voice_styles_dir,
        ):
            config.voice.default_voice_id = saved_voice_id

        elif not _voice_file_exists(
            config.voice.default_voice_id,
            config.voice.voice_styles_dir,
        ):
            if _voice_file_exists(
                "am_eric",
                config.voice.voice_styles_dir,
            ):
                config.voice.default_voice_id = "am_eric"

        # --------------------------------------------------------------------
        # MEMORY
        # --------------------------------------------------------------------

        memory_data = config_data.get("memory")

        if isinstance(
            memory_data,
            dict,
        ):
            config.memory.chat_memory_file = str(
                memory_data.get(
                    "chat_memory_file",
                    config.memory.chat_memory_file,
                )
            )

            config.memory.alias_memory_file = str(
                memory_data.get(
                    "alias_memory_file",
                    config.memory.alias_memory_file,
                )
            )

            config.memory.max_history_length = int(
                memory_data.get(
                    "max_history_length",
                    config.memory.max_history_length,
                )
            )

        # --------------------------------------------------------------------
        # PREDICTIVE
        # --------------------------------------------------------------------

        predictive_data = config_data.get("predictive")

        if isinstance(
            predictive_data,
            dict,
        ):
            config.predictive.enabled = bool(
                predictive_data.get(
                    "enabled",
                    config.predictive.enabled,
                )
            )

            config.predictive.learning_rate = float(
                predictive_data.get(
                    "learning_rate",
                    config.predictive.learning_rate,
                )
            )

            config.predictive.prediction_threshold = float(
                predictive_data.get(
                    "prediction_threshold",
                    config.predictive.prediction_threshold,
                )
            )

            config.predictive.max_predictions = int(
                predictive_data.get(
                    "max_predictions",
                    config.predictive.max_predictions,
                )
            )

            config.predictive.min_usage_count = int(
                predictive_data.get(
                    "min_usage_count",
                    config.predictive.min_usage_count,
                )
            )

            config.predictive.pattern_analysis_window = int(
                predictive_data.get(
                    "pattern_analysis_window",
                    config.predictive.pattern_analysis_window,
                )
            )

            config.predictive.prediction_memory_file = str(
                predictive_data.get(
                    "prediction_memory_file",
                    config.predictive.prediction_memory_file,
                )
            )

            config.predictive.time_window_hours = int(
                predictive_data.get(
                    "time_window_hours",
                    config.predictive.time_window_hours,
                )
            )

        # --------------------------------------------------------------------
        # CALIBRATION
        # --------------------------------------------------------------------

        calibration_data = config_data.get("calibration")

        if isinstance(
            calibration_data,
            dict,
        ):
            config.calibration.enabled = bool(
                calibration_data.get(
                    "enabled",
                    config.calibration.enabled,
                )
            )

            config.calibration.max_applications = int(
                calibration_data.get(
                    "max_applications",
                    config.calibration.max_applications,
                )
            )

            config.calibration.max_attempts_per_element = int(
                calibration_data.get(
                    "max_attempts_per_element",
                    config.calibration.max_attempts_per_element,
                )
            )

            config.calibration.screen_analysis_delay = float(
                calibration_data.get(
                    "screen_analysis_delay",
                    config.calibration.screen_analysis_delay,
                )
            )

            config.calibration.element_detection_confidence = float(
                calibration_data.get(
                    "element_detection_confidence",
                    config.calibration.element_detection_confidence,
                )
            )

            config.calibration.save_calibration_data = bool(
                calibration_data.get(
                    "save_calibration_data",
                    config.calibration.save_calibration_data,
                )
            )

            config.calibration.auto_backup_existing_data = bool(
                calibration_data.get(
                    "auto_backup_existing_data",
                    config.calibration.auto_backup_existing_data,
                )
            )

            config.calibration.use_native_coordinates = bool(
                calibration_data.get(
                    "use_native_coordinates",
                    config.calibration.use_native_coordinates,
                )
            )

            config.calibration.scale_factor = float(
                calibration_data.get(
                    "scale_factor",
                    config.calibration.scale_factor,
                )
                or 1.0
            )

            config.calibration.coordinate_system = str(
                calibration_data.get(
                    "coordinate_system",
                    config.calibration.coordinate_system,
                )
            )

            config.calibration.calibration_screen = int(
                calibration_data.get(
                    "calibration_screen",
                    config.calibration.calibration_screen,
                )
            )

            monitor_offset = calibration_data.get("monitor_offset")

            if isinstance(
                monitor_offset,
                dict,
            ):
                config.calibration.monitor_offset = {
                    str(key): int(value)
                    for key, value in monitor_offset.items()
                    if isinstance(
                        value,
                        (int, float),
                    )
                }

        # --------------------------------------------------------------------
        # SCREEN
        # --------------------------------------------------------------------

        screen_data = config_data.get("screen")

        if isinstance(
            screen_data,
            dict,
        ):
            config.screen.primary_screen_width = int(
                screen_data.get(
                    "primary_screen_width",
                    config.screen.primary_screen_width,
                )
                or 0
            )

            config.screen.primary_screen_height = int(
                screen_data.get(
                    "primary_screen_height",
                    config.screen.primary_screen_height,
                )
                or 0
            )

            config.screen.multi_screen_enabled = bool(
                screen_data.get(
                    "multi_screen_enabled",
                    config.screen.multi_screen_enabled,
                )
            )

            config.screen.multi_screen_offset = int(
                screen_data.get(
                    "multi_screen_offset",
                    config.screen.multi_screen_offset,
                )
                or 0
            )

            config.screen.capture_quality = float(
                screen_data.get(
                    "capture_quality",
                    config.screen.capture_quality,
                )
            )

            screen_boundaries = screen_data.get("screen_boundaries")

            if isinstance(
                screen_boundaries,
                dict,
            ):
                config.screen.screen_boundaries = {
                    str(key): int(value)
                    for key, value in screen_boundaries.items()
                    if isinstance(
                        value,
                        (int, float),
                    )
                }

            monitors_data = screen_data.get("monitors")

            if isinstance(
                monitors_data,
                list,
            ):
                monitors: List[MonitorConfig] = []

                for monitor_data in monitors_data:
                    if not isinstance(
                        monitor_data,
                        dict,
                    ):
                        continue

                    try:
                        monitors.append(_load_monitor(monitor_data))
                    except (
                        TypeError,
                        ValueError,
                    ):
                        continue

                config.screen.monitors = monitors

            else:
                config.screen.monitors = _load_default_monitors()

            total_resolution = screen_data.get("total_resolution")

            if isinstance(
                total_resolution,
                dict,
            ):
                config.screen.total_resolution = {
                    str(key): int(value)
                    for key, value in total_resolution.items()
                    if isinstance(
                        value,
                        (int, float),
                    )
                }

            config.screen.setup_type = str(
                screen_data.get(
                    "setup_type",
                    config.screen.setup_type,
                )
            )

            config.screen.scale_factor = float(
                screen_data.get(
                    "scale_factor",
                    config.screen.scale_factor,
                )
                or 1.0
            )

            config.screen.use_scaled_coordinates = bool(
                screen_data.get(
                    "use_scaled_coordinates",
                    config.screen.use_scaled_coordinates,
                )
            )

            coordinate_conversion = screen_data.get("coordinate_conversion")

            if isinstance(
                coordinate_conversion,
                dict,
            ):
                config.screen.coordinate_conversion = coordinate_conversion

        # --------------------------------------------------------------------
        # TIMEOUT
        # --------------------------------------------------------------------

        timeout_data = config_data.get("timeout")

        if isinstance(
            timeout_data,
            dict,
        ):
            config.timeout.ollama_call = float(
                timeout_data.get(
                    "ollama_call",
                    config.timeout.ollama_call,
                )
            )

            config.timeout.screen_capture = float(
                timeout_data.get(
                    "screen_capture",
                    config.timeout.screen_capture,
                )
            )

            config.timeout.click_delay = float(
                timeout_data.get(
                    "click_delay",
                    config.timeout.click_delay,
                )
            )

            config.timeout.typing_interval = float(
                timeout_data.get(
                    "typing_interval",
                    config.timeout.typing_interval,
                )
            )

        # --------------------------------------------------------------------
        # CHROME
        # --------------------------------------------------------------------

        chrome_data = config_data.get("chrome")

        if isinstance(
            chrome_data,
            dict,
        ):
            config.chrome.default_width = int(
                chrome_data.get(
                    "default_width",
                    config.chrome.default_width,
                )
            )

            config.chrome.default_height = int(
                chrome_data.get(
                    "default_height",
                    config.chrome.default_height,
                )
            )

            config.chrome.maximized = bool(
                chrome_data.get(
                    "maximized",
                    config.chrome.maximized,
                )
            )

            position = chrome_data.get("position")

            if isinstance(
                position,
                dict,
            ):
                config.chrome.position = {
                    str(key): int(value)
                    for key, value in position.items()
                    if isinstance(
                        value,
                        (int, float),
                    )
                }

        # --------------------------------------------------------------------
        # ELEMENT TYPES
        # --------------------------------------------------------------------

        element_types = config_data.get("element_types")

        if isinstance(
            element_types,
            dict,
        ):
            config.element_types = element_types

        return config

    except FileNotFoundError:
        logger._print_log("info", "Procesando solicitud", "config.py", "method", 1195)
        return Config()

    except json.JSONDecodeError as exc:
        logger._print_log("info", "Procesando solicitud", "config.py", "method", 1195)
        return Config()

    except OSError as exc:
        logger._print_log("info", "Procesando solicitud", "config.py", "method", 1195)
        return Config()


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================


config = load_config()


# ============================================================================
# GETTERS GENERALES
# ============================================================================


def get_project_root() -> Path:
    """Retorna la ruta raíz del proyecto."""
    return PROJECT_ROOT


def get_config_path() -> Path:
    """Retorna la ruta del archivo de configuración."""
    return CONFIG_PATH


# ============================================================================
# GETTERS DE RUTAS
# ============================================================================


def get_models_path() -> Path:
    """Retorna la ruta al directorio de modelos."""
    return PROJECT_ROOT / config.voice.model_dir


def get_voices_path() -> Path:
    """Retorna la ruta al directorio de voces."""
    return PROJECT_ROOT / config.voice.voice_styles_dir


def get_macros_coords_path() -> Path:
    """Retorna la ruta al archivo de coordenadas de macros."""
    return PROJECT_ROOT / "data" / "macros_coords.json"


def get_voice_preference_path() -> Path:
    """Retorna la ruta de la preferencia persistente de voz."""
    return VOICE_PREFERENCE_PATH


# ============================================================================
# GETTERS DE CONFIGURACIÓN
# ============================================================================


def get_system_config() -> SystemConfig:
    """Retorna la configuración general del sistema."""
    return config.system


def get_logging_config() -> LoggingConfig:
    """Retorna la configuración de logging."""
    return config.logging


def get_keyboard_config() -> KeyboardConfig:
    """Retorna la configuración del teclado."""
    return config.keyboard


def get_voice_config() -> VoiceConfig:
    """Retorna la configuración de voz."""
    return config.voice


def get_memory_config() -> MemoryConfig:
    """Retorna la configuración de memoria."""
    return config.memory


def get_screen_config() -> ScreenConfig:
    """
    Retorna la configuración auxiliar de pantallas.

    La geometría real en Windows debe obtenerse mediante ScreenManager.
    """
    return config.screen


def get_timeout_config() -> TimeoutConfig:
    """Retorna la configuración de timeouts."""
    return config.timeout


def get_predictive_config() -> PredictiveConfig:
    """Retorna la configuración predictiva."""
    return config.predictive


def get_calibration_config() -> CalibrationConfig:
    """Retorna la configuración de calibración."""
    return config.calibration


def get_chrome_config() -> ChromeConfig:
    """Retorna la configuración de Chrome."""
    return config.chrome


def get_element_types() -> Dict[str, Dict[str, Any]]:
    """Retorna los tipos de elementos configurados."""
    return config.element_types


# ============================================================================
# GETTERS COMPATIBLES DE MONITORES
# ============================================================================


def get_monitors() -> List[MonitorConfig]:
    """
    Retorna los monitores definidos en config.json.

    Para obtener los monitores reales actuales debe utilizarse
    src.utils.screen_manager.get_screen_manager().
    """
    return config.screen.monitors


def get_monitor_config(
    monitor_id: int,
) -> Optional[MonitorConfig]:
    """Retorna un monitor concreto del JSON."""
    return config.screen.get_monitor(monitor_id)


def get_primary_monitor_config() -> Optional[MonitorConfig]:
    """Retorna el monitor principal definido en el JSON."""
    return config.screen.get_primary_monitor()


def get_monitor_count() -> int:
    """Retorna el número de monitores definidos en el JSON."""
    return config.screen.monitor_count
