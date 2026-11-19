"""Punto de entrada principal del sistema Jarvis."""

import os
import re
import sys

from src.ear import Ear
from src.brain import Brain
from src.tools.executor import get_executor
from src.memory import Memory
from src.core.log import get_logger, setup_logging
from src.core.config import get_macros_coords_path, get_voice_config
from src.core.ollama_server import OllamaServerError, ensure_ollama_server

try:
    from src.mouth import Mouth

    MOUTH_AVAILABLE = True
except ImportError:
    MOUTH_AVAILABLE = False
    Mouth = None

logger = get_logger("jarvis")
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
        value.replace("\u00e1", "a")
        .replace("\u00e9", "e")
        .replace("\u00ed", "i")
        .replace("\u00f3", "o")
        .replace("\u00fa", "u")
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
            logger.info("No encuentro voces disponibles.")
            return True
        voice_id = _resolve_voice_id(normalized, available_voices)
        if voice_id is None:
            logger.info(
                f"No he encontrado esa voz. Las voces disponibles son: {', '.join(available_voices)}"
            )
            return True
        if mouth.set_voice(voice_id):
            logger.info(f"Voz cambiada a {voice_id}.")
        else:
            logger.info(f"No he podido cambiar a {voice_id}.")
        return True
    except Exception as e:
        logger.error(f"Error cambiando voz: {e}")
        return False


def _preparar_ollama():
    """Asegura que Ollama responde antes de crear Brain y Vision.

    Si no responde, arranca `ollama serve`; ese servidor se cierra al salir
    de JARVIS (o lo cierra su vigilante si JARVIS muere de golpe). Un servidor
    que ya estaba en marcha se reutiliza y no se cierra.
    """
    try:
        servidor = ensure_ollama_server()
    except OllamaServerError as e:
        logger.warning(
            "Ollama no disponible: %s. Brain y Vision fallaran hasta que se arranque.", e
        )
        return None
    if servidor.started_by_us:
        logger.info(
            "Ollama arrancado por JARVIS en %s (PID %s); se cerrara al salir.",
            servidor.host,
            servidor.pid,
        )
    else:
        logger.info("Ollama ya estaba en marcha en %s.", servidor.host)
    return servidor


def main():
    setup_logging()
    logger.info("=" * 40)
    logger.info("   SISTEMA JARVIS - INTEGRACION TOTAL   ")
    logger.info("=" * 40)
    try:
        logger.info("[*] Inicializando componentes...")
        _preparar_ollama()
        jarvis_ear = Ear(model_size="medium")
        jarvis_brain = Brain(model="llama3")
        jarvis_executor = get_executor()
        jarvis_memory = Memory()

        # ------------------------------------------------------------------
        # Primer inventario del sistema de archivos (3.8.5.1.4.8.1).
        # Se decide si es necesario, se informa su alcance y se ejecuta en
        # segundo plano sin bloquear el arranque ni la conversacion de JARVIS.
        # ------------------------------------------------------------------
        try:
            from src.hands.inventory.system_inventory import (
                GestorPrimerInventario,
                default_contract,
                generate_machine_id,
            )
            from src.hands.inventory.system_inventory_storage import SystemInventoryStorage

            _jarvis_machine_id = generate_machine_id()
            _jarvis_inventory_storage = SystemInventoryStorage()
            _jarvis_inventory_storage.initialize()
            _jarvis_gestor_inventario = GestorPrimerInventario(
                machine_id=_jarvis_machine_id,
                storage=_jarvis_inventory_storage,
                contrato=default_contract(),
            )
            _debe_inventario, _motivo_inventario = (
                _jarvis_gestor_inventario.debe_ejecutar_primer_inventario()
            )
            if _debe_inventario:
                _alcance_inventario = _jarvis_gestor_inventario.reportar_alcance()
                logger.info(
                    "Primer inventario del sistema de archivos: %s. "
                    "Alcance: %d volumen(es) a escanear (%s).",
                    _motivo_inventario,
                    _alcance_inventario.total_volumenes,
                    _alcance_inventario.sistema_operativo,
                )

                def _reportar_progreso_inventario(progreso):
                    logger.info(
                        "Progreso inventario: %.1f%% (%d entradas, %d/%d volumenes)",
                        progreso.cobertura_global,
                        progreso.entradas_procesadas,
                        progreso.volumenes_completados,
                        progreso.total_volumenes,
                    )

                _jarvis_ejecucion_inventario = (
                    _jarvis_gestor_inventario.ejecutar_primera_vez(
                        callback_progreso=_reportar_progreso_inventario
                    )
                )
                logger.info(
                    "Primer inventario iniciado en segundo plano (no bloqueante)."
                )
            else:
                logger.info(
                    "Inventario del sistema de archivos no requerido: %s",
                    _motivo_inventario,
                )
        except Exception as e:
            logger.warning(
                "No se pudo programar el primer inventario del sistema de archivos: %s",
                e,
            )

        calibration_path = get_macros_coords_path()
        calibration_exists = calibration_path.exists()

        jarvis_mouth = None
        if MOUTH_AVAILABLE:
            try:
                jarvis_mouth = Mouth()
                voice_config = get_voice_config()
                default_voice_id = voice_config.default_voice_id
                if not jarvis_mouth.has_voice(jarvis_mouth.get_current_voice()):
                    logger.warning(
                        f"La voz configurada '{jarvis_mouth.get_current_voice()}' no existe en {jarvis_mouth.STYLE_VECTOR_FILE}"
                    )
                    if jarvis_mouth.has_voice(default_voice_id):
                        jarvis_mouth.set_voice(default_voice_id)
                logger.info("Sistema de voz inicializado correctamente")
            except Exception as e:
                logger.error(f"No se pudo inicializar el sistema de voz: {e}")
                logger.info("Continuando sin capacidad de voz (modo texto)")
        else:
            logger.info("Componente de voz no disponible (modo texto)")

        logger.info("SISTEMA OPERATIVO: ONLINE")
        if jarvis_mouth:
            logger.info(f"Voz actual: {jarvis_mouth.get_current_voice()}")
            logger.info(
                f"Voces disponibles: {len(jarvis_mouth.get_available_voices())}"
            )
        else:
            logger.info("Modo: texto (sin voz)")
        logger.info(
            f"Sistema predictivo cargado: {jarvis_memory.predictive_config.enabled}"
        )
        logger.info(
            f"Sistema de calibracion {'cargado' if calibration_exists else 'listo para calibrar'}"
        )
        logger.info(
            f"Aliases estaticos cargados: {len(jarvis_memory.command_aliases)}"
        )
        logger.info(
            f"Aliases aprendidos cargados: {len(jarvis_memory.learned_aliases)}"
        )
        logger.info("Escuchando continuamente...")
    except Exception as e:
        logger.exception("[FALLO CRITICO] Error al inicializar: %s", e)
        sys.exit(1)

    try:
        logger.info("Sistema Jarvis listo. Esperando comandos de voz...")
        while True:
            texto_escuchado = jarvis_ear.listen()
            if not texto_escuchado:
                logger.info("No se detecto audio, continuando espera...")
                continue

            logger.info(f"TU DIJISTE: '{texto_escuchado}'")
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
            if comando_detectado and not jarvis_executor.get_command_info(
                comando_detectado
            ):
                # El alias apunta a una accion que no esta registrada: se
                # ignora y la frase sigue el camino normal (prediccion y Brain).
                logger.warning(
                    "Alias ignorado: la accion '%s' no esta registrada",
                    comando_detectado,
                )
                comando_detectado = None

            if comando_detectado:
                logger.info(f"Comando reconocido directamente: {comando_detectado}")
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
                    logger.error(
                        f"Error ejecutando alias '{comando_detectado}': {e}"
                    )
                    texto_para_hablar = f"Error en ejecuci\u00f3n: {e}"
            else:
                predictions = jarvis_executor.get_command_suggestions(
                    texto_procesado, jarvis_memory.get_conversation_history()
                )
                prediction_accepted = False

                if predictions and predictions[0]["score"] >= 0.8:
                    pred_command = predictions[0]["command"]
                    logger.info(
                        f"Prediccion detectada: {pred_command} (score={predictions[0]['score']})"
                    )
                    if jarvis_mouth:
                        jarvis_mouth.speak(
                            f"\u00bfQuieres ejecutar {pred_command.replace('_', ' ')}?"
                        )
                    confirmacion = jarvis_ear.listen()
                    if confirmacion and any(
                        word in confirmacion.lower()
                        for word in ["s\u00ed", "si", "claro", "ok", "vale", "dale", "hazlo"]
                    ):
                        logger.info(f"Prediccion aceptada: {pred_command}")
                        respuesta_ia = f"[CMD: {pred_command}]"
                        prediction_accepted = True
                        jarvis_memory.record_command_usage(
                            texto_escuchado, pred_command, True
                        )
                    else:
                        logger.info("Prediccion rechazada")
                        jarvis_memory.record_command_usage(
                            texto_escuchado, pred_command, False
                        )

                if not prediction_accepted:
                    logger.info(f"Enviando al cerebro: {texto_escuchado}")
                    try:
                        # Brain interpreta; Executor es el unico punto de ejecucion.
                        respuesta_ia = jarvis_brain.think(
                            texto_escuchado, use_legacy_execution=False
                        )
                        logger.info(f"Respuesta del cerebro: {respuesta_ia}")
                    except Exception as e:
                        logger.error(f"Error procesando con Brain: {e}")
                        texto_para_hablar = f"Error procesando la petici\u00f3n: {e}"

                elif respuesta_ia:
                    logger.info(f"Ejecutando comando aceptado: {respuesta_ia}")
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
                            texto_para_hablar = "Error en ejecuci\u00f3n del comando."
                    except Exception as e:
                        logger.error(f"Error ejecutando prediccion: {e}")
                        texto_para_hablar = f"Error en ejecuci\u00f3n: {e}"

            # Ejecutar unicamente comandos explicitos devueltos por Brain/Alias/Prediccion.
            if (
                not comando_detectado
                and respuesta_ia
                and "[CMD:" in respuesta_ia
                and not texto_para_hablar
            ):
                logger.info(f"Comando detectado en respuesta: {respuesta_ia}")
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
                    logger.error(f"Error ejecutando comando de Brain: {e}")
                    texto_para_hablar = f"Error en ejecuci\u00f3n: {e}"

            elif (
                not comando_detectado
                and respuesta_ia
                and "[CMD:" not in respuesta_ia
                and not texto_para_hablar
            ):
                # Las respuestas conversacionales no deberian pasar por Executor.
                texto_para_hablar = respuesta_ia

            if texto_para_hablar:
                if jarvis_mouth:
                    try:
                        jarvis_mouth.speak(texto_para_hablar)
                    except Exception as e:
                        logger.error(f"Error al hablar: {e}")
                logger.info(f"JARVIS: {texto_para_hablar}")
                jarvis_memory.save_conversation(
                    texto_escuchado, texto_para_hablar, None, None, None
                )
            else:
                logger.info("Jarvis ejecuto la accion en silencio.")

    except KeyboardInterrupt:
        logger.info("Apagando sistemas de Jarvis... Adios.")
    except Exception as e:
        logger.exception("[FALLO CRITICO] Error en el bucle principal: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
