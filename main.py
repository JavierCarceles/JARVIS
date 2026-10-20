"""Punto de entrada principal del sistema Jarvis."""

import os
import re
import sys

from src.ear import Ear
from src.brain import Brain
from src.tools.executor import get_executor
from src.memory import Memory
from src.utils.logger import get_logger
from src.utils.jarvis_logging_system import (
    get_jarvis_logger,
    log_jarvis_info,
    log_jarvis_error,
    log_jarvis_warning,
)
from src.utils.config import get_voice_config, get_project_root, get_logging_config

try:
    from src.mouth import Mouth

    MOUTH_AVAILABLE = True
except ImportError:
    MOUTH_AVAILABLE = False
    Mouth = None

logging_config = get_logging_config()
logger = get_logger("Jarvis")
# Iniciar sistema de logging avanzado
jarvis_logger = get_jarvis_logger()
jarvis_logger.start()
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

try:
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _normalize_voice_text(text: str) -> str:
    if not text:
        return ""
    value = text.lower().strip()
    value = (
        value.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    value = re.sub(r"[^a-z0-9_ ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _resolve_voice_id(request: str, available_voices):
    normalized = _normalize_voice_text(request)
    if not normalized:
        return None
    available_normalized = {
        _normalize_voice_text(voice): voice for voice in available_voices
    }
    if normalized in available_normalized:
        return available_normalized[normalized]
    for normalized_voice, original_voice in available_normalized.items():
        if normalized_voice in normalized:
            return original_voice
    words = normalized.split()
    for gender_prefix in ("af", "am", "bf", "bm"):
        for word in words:
            candidate = f"{gender_prefix}_{word}"
            if candidate in available_normalized:
                return available_normalized[candidate]
    return None


def _try_change_voice(text: str, mouth) -> bool:
    if mouth is None:
        return False
    normalized = _normalize_voice_text(text)
    if not normalized:
        return False
    trigger_patterns = (
        "cambia la voz",
        "cambiar la voz",
        "cambia voz",
        "cambiar voz",
        "usa la voz",
        "usar la voz",
        "pon la voz",
        "pon voz",
        "utiliza la voz",
        "utilizar la voz",
        "cambia a la voz",
        "cambiar a la voz",
    )
    if not any(pattern in normalized for pattern in trigger_patterns):
        return False
    try:
        available_voices = mouth.get_available_voices()
        if not available_voices:
            log_jarvis_info("No encuentro voces disponibles.")
            return True
        voice_id = _resolve_voice_id(normalized, available_voices)
        if voice_id is None:
            log_jarvis_info(
                f"No he encontrado esa voz. Las voces disponibles son: {', '.join(available_voices)}"
            )
            return True
        if mouth.set_voice(voice_id):
            log_jarvis_info(f"Voz cambiada a {voice_id}.")
        else:
            log_jarvis_info(f"No he podido cambiar a {voice_id}.")
        return True
    except Exception as e:
        log_jarvis_error(f"Error cambiando voz: {e}")
        return False


def main():
    log_jarvis_info("=" * 40)
    log_jarvis_info("   SISTEMA JARVIS - INTEGRACIÓN TOTAL   ")
    log_jarvis_info("=" * 40)
    try:
        log_jarvis_info("[*] Inicializando componentes...")
        jarvis_ear = Ear(model_size="medium")
        jarvis_brain = Brain(model="llama3")
        jarvis_executor = get_executor()
        jarvis_memory = Memory()

        calibration_path = get_project_root() / "macros_coords.json"
        calibration_exists = calibration_path.exists()

        jarvis_mouth = None
        if MOUTH_AVAILABLE:
            try:
                jarvis_mouth = Mouth()
                voice_config = get_voice_config()
                default_voice_id = voice_config.default_voice_id
                if not jarvis_mouth.has_voice(jarvis_mouth.get_current_voice()):
                    log_jarvis_warning(
                        f"La voz configurada '{jarvis_mouth.get_current_voice()}' no existe en {jarvis_mouth.STYLE_VECTOR_FILE}"
                    )
                    if jarvis_mouth.has_voice(default_voice_id):
                        jarvis_mouth.set_voice(default_voice_id)
                log_jarvis_info("Sistema de voz inicializado correctamente")
            except Exception as e:
                log_jarvis_error(f"No se pudo inicializar el sistema de voz: {e}")
                log_jarvis_info("Continuando sin capacidad de voz (modo texto)")
        else:
            log_jarvis_info("Componente de voz no disponible (modo texto)")

        log_jarvis_info("SISTEMA OPERATIVO: ONLINE")
        if jarvis_mouth:
            log_jarvis_info(f"Voz actual: {jarvis_mouth.get_current_voice()}")
            log_jarvis_info(
                f"Voces disponibles: {len(jarvis_mouth.get_available_voices())}"
            )
        else:
            log_jarvis_info("Modo: texto (sin voz)")
        log_jarvis_info(
            f"Sistema predictivo cargado: {jarvis_memory.predictive_config.enabled}"
        )
        log_jarvis_info(
            f"Sistema de calibración {'cargado' if calibration_exists else 'listo para calibrar'}"
        )
        log_jarvis_info(
            f"Aliases estáticos cargados: {len(jarvis_memory.command_aliases)}"
        )
        log_jarvis_info(
            f"Aliases aprendidos cargados: {len(jarvis_memory.learned_aliases)}"
        )
        log_jarvis_info("Escuchando continuamente...")
    except Exception as e:
        log_jarvis_error(f"[FALLO CRÍTICO] Error al inicializar: {e}")
        import traceback

        log_jarvis_error(f"Traceback completo: {traceback.format_exc()}")
        sys.exit(1)

    try:
        log_jarvis_info("Sistema Jarvis listo. Esperando comandos de voz...")
        while True:
            texto_escuchado = jarvis_ear.listen()
            if not texto_escuchado:
                log_jarvis_info("No se detectó audio, continuando espera...")
                continue

            log_jarvis_info(f"TÚ DIJISTE: '{texto_escuchado}'")
            texto_procesado = texto_escuchado.strip()

            if jarvis_mouth and _try_change_voice(texto_procesado, jarvis_mouth):
                jarvis_memory.save_conversation(
                    texto_escuchado,
                    f"Voz actual: {jarvis_mouth.get_current_voice()}",
                    None,
                    None,
                    None,
                )
                continue

            respuesta_ia = ""
            texto_para_hablar = ""
            comando_detectado = jarvis_memory.get_alias(texto_procesado)

            if comando_detectado:
                log_jarvis_info(f"Comando reconocido directamente: {comando_detectado}")
                respuesta_ia = f"[CMD: {comando_detectado}]"
                try:
                    texto_para_hablar = jarvis_executor.process_and_execute(
                        respuesta_ia
                    )
                    jarvis_memory.record_command_usage(
                        texto_escuchado, comando_detectado, True
                    )
                    jarvis_memory.save_alias(texto_escuchado, comando_detectado)
                except Exception as e:
                    log_jarvis_error(
                        f"Error ejecutando alias '{comando_detectado}': {e}"
                    )
                    texto_para_hablar = f"Error en ejecución: {e}"
            else:
                predictions = jarvis_executor.get_command_suggestions(
                    texto_procesado, jarvis_memory.get_conversation_history()
                )
                prediction_accepted = False

                if predictions and predictions[0]["score"] >= 0.8:
                    pred_command = predictions[0]["command"]
                    log_jarvis_info(
                        f"Predicción detectada: {pred_command} (score={predictions[0]['score']})"
                    )
                    if jarvis_mouth:
                        jarvis_mouth.speak(
                            f"¿Quieres ejecutar {pred_command.replace('_', ' ')}?"
                        )
                    confirmacion = jarvis_ear.listen()
                    if confirmacion and any(
                        word in confirmacion.lower()
                        for word in ["sí", "si", "claro", "ok", "vale", "dale", "hazlo"]
                    ):
                        log_jarvis_info(f"Predicción aceptada: {pred_command}")
                        respuesta_ia = f"[CMD: {pred_command}]"
                        prediction_accepted = True
                        jarvis_memory.record_command_usage(
                            texto_escuchado, pred_command, True
                        )
                    else:
                        log_jarvis_info("Predicción rechazada")
                        jarvis_memory.record_command_usage(
                            texto_escuchado, pred_command, False
                        )

                if not prediction_accepted:
                    log_jarvis_info(f"Enviando al cerebro: {texto_escuchado}")
                    try:
                        # Brain interpreta; Executor es el único punto de ejecución.
                        respuesta_ia = jarvis_brain.think(
                            texto_escuchado, use_legacy_execution=False
                        )
                        log_jarvis_info(f"Respuesta del cerebro: {respuesta_ia}")
                    except Exception as e:
                        log_jarvis_error(f"Error procesando con Brain: {e}")
                        texto_para_hablar = f"Error procesando la petición: {e}"

                elif respuesta_ia:
                    log_jarvis_info(f"Ejecutando comando aceptado: {respuesta_ia}")
                    try:
                        texto_para_hablar = jarvis_executor.process_and_execute(
                            respuesta_ia
                        )
                        if texto_para_hablar and "Error" not in str(texto_para_hablar):
                            jarvis_memory.save_alias(
                                texto_escuchado,
                                respuesta_ia.replace("[CMD: ", "").replace("]", ""),
                            )
                        else:
                            texto_para_hablar = "Error en ejecución del comando."
                    except Exception as e:
                        log_jarvis_error(f"Error ejecutando predicción: {e}")
                        texto_para_hablar = f"Error en ejecución: {e}"

            # Ejecutar únicamente comandos explícitos devueltos por Brain/Alias/Predicción.
            if (
                not comando_detectado
                and respuesta_ia
                and "[CMD:" in respuesta_ia
                and not texto_para_hablar
            ):
                log_jarvis_info(f"Comando detectado en respuesta: {respuesta_ia}")
                try:
                    texto_para_hablar = jarvis_executor.process_and_execute(
                        respuesta_ia
                    )
                    comando_brain = (
                        respuesta_ia.replace("[CMD: ", "").replace("]", "").strip()
                    )
                    if texto_para_hablar and "Error" not in str(texto_para_hablar):
                        jarvis_memory.save_alias(texto_escuchado, comando_brain)
                        jarvis_memory.record_command_usage(
                            texto_escuchado, comando_brain, True
                        )
                except Exception as e:
                    log_jarvis_error(f"Error ejecutando comando de Brain: {e}")
                    texto_para_hablar = f"Error en ejecución: {e}"

            elif (
                not comando_detectado
                and respuesta_ia
                and "[CMD:" not in respuesta_ia
                and not texto_para_hablar
            ):
                # Las respuestas conversacionales no deberían pasar por Executor.
                texto_para_hablar = respuesta_ia

            if texto_para_hablar:
                if jarvis_mouth:
                    try:
                        jarvis_mouth.speak(texto_para_hablar)
                    except Exception as e:
                        log_jarvis_error(f"Error al hablar: {e}")
                log_jarvis_info(f"JARVIS: {texto_para_hablar}")
                jarvis_memory.save_conversation(
                    texto_escuchado, texto_para_hablar, None, None, None
                )
            else:
                log_jarvis_info("Jarvis ejecutó la acción en silencio.")

    except KeyboardInterrupt:
        log_jarvis_info("Apagando sistemas de Jarvis... Adiós.")
    except Exception as e:
        log_jarvis_error(f"[FALLO CRÍTICO] Error en el bucle principal: {e}")
        import traceback

        log_jarvis_error(f"Traceback completo: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        # Asegurarse de detener el sistema de logging al salir
        try:
            jarvis_logger.stop()
        except:
            pass
