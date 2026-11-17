# src/ear/listener.py
"""
Percepcion auditiva y transcripcion de voz usando Whisper.
Integrado con el nuevo sistema de planificacion jerarquica.
"""
import queue
import time
import numpy as np
from typing import Optional, Dict, Any, List

# Captura y ASR son opcionales al importar (4.5.6.13): sin ellos Ear informa
# del motivo en lugar de romper la importacion de todo el paquete.
try:
    import sounddevice as sd
    _SD_IMPORT_ERROR: Optional[Exception] = None
except Exception as _exc:  # pragma: no cover - depende del entorno
    sd = None
    _SD_IMPORT_ERROR = _exc
try:
    from faster_whisper import WhisperModel
except Exception as _exc:  # pragma: no cover - depende del entorno
    WhisperModel = None
from dataclasses import dataclass

from src.core.config import get_timeout_config
from src.core.log import get_logger
from src.ear.asr_config import (
    ASRConfig,
    LEGACY_INITIAL_PROMPT,
    load_asr_config,
    model_kwargs,
    transcribe_kwargs,
)
from src.ear.transcription import (
    TranscriptionRecord,
    build_transcription_record,
    set_last_transcription,
)
from src.memory.conversation import ConversationMemory

logger = get_logger(__name__)


@dataclass
class AudioCapabilities:
    """
    Capacidades del sistema de audio.
    """
    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "float32"
    block_duration: float = 0.03
    max_recording_time: float = 10.0
    silence_threshold: float = 0.8
    sensitivity_multiplier: float = 3.0
    

class AudioNode:
    """
    Nodo basico para procesamiento de audio.
    """
    
    def __init__(self, name: str):
        logger.info("Initializing " + name + " audio node")
        self.name = name
        self.capabilities = AudioCapabilities()
        
    def execute(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """
        Ejecuta el procesamiento de audio.
        
        Args:
            audio_data: Datos de audio
            
        Returns:
            Resultado del procesamiento
        """
        return {
            "node": self.name,
            "success": True,
            "data": audio_data
        }
        
    def get_preconditions(self) -> List[str]:
        """
        Devuelve las precondiciones necesarias para ejecutar este nodo.
        """
        return ["audio_available"]
        
    def get_effects(self) -> List[str]:
        """
        Devuelve los efectos de ejecutar este nodo.
        """
        return ["audio_processed"]
        
    def get_cost(self) -> float:
        """
        Devuelve el coste estimado de ejecutar este nodo.
        """
        return 1.0


class CalibrationNode(AudioNode):
    """
    Nodo para calibracion de audio.
    """
    
    def execute(self, audio_queue: queue.Queue) -> Dict[str, Any]:
        """
        Calibra el umbral de deteccion de voz.
        
        Args:
            audio_queue: Cola de audio
            
        Returns:
            Resultado de calibracion
        """
        logger.debug("Calibrando umbral de deteccion de voz...")
        levels = []
        
        for _ in range(20):
            if audio_queue.empty():
                break
            chunk = audio_queue.get()
            levels.append(self._rms(chunk.flatten()))
        
        if not levels:
            logger.debug("No se detecto audio durante calibracion, usando valor por defecto")
            threshold = 0.01
        else:
            noise_level = np.median(levels)
            threshold = max(noise_level * self.capabilities.sensitivity_multiplier, 0.01)
        
        
        return {
            "node": self.name,
            "success": True,
            "threshold": threshold,
            "noise_level": noise_level if levels else 0.0
        }
        
    def _rms(self, audio: np.ndarray) -> float:
        """
        Calcula el nivel de amplitud RMS del audio.
        """
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio))))


class TranscriptionNode(AudioNode):
    """
    Nodo para transcripcion de audio a texto.
    """
    
    def __init__(
        self,
        name: str,
        model_size: Optional[str] = None,
        language: Optional[str] = None,
        asr_config: Optional[ASRConfig] = None,
    ):
        super().__init__(name)
        # Configuracion en fichero (4.5.6.3); los argumentos explicitos mandan.
        self.asr_config = asr_config or load_asr_config()
        if model_size:
            self.asr_config.model_size = model_size
        if language:
            self.asr_config.language = language
        self.model_size = self.asr_config.model_size
        self.language = self.asr_config.language
        self.model = None
        self._initial_prompt: Optional[str] = None
        self._load_model()

    def get_initial_prompt(self) -> str:
        """
        ``initial_prompt`` de Whisper (4.5.6.4): vocabulario dinamico del
        catalogo, monitores y verbos, limitado en longitud; la lista fija
        anterior solo si el vocabulario dinamico esta desactivado o vacio.
        Se calcula una vez; ``refresh_vocabulary()`` lo recalcula.
        """
        if self._initial_prompt is None:
            prompt = ""
            if self.asr_config.dynamic_vocabulary:
                try:
                    from src.ear.vocabulary import build_initial_prompt, collect_vocabulary

                    prompt = build_initial_prompt(
                        collect_vocabulary(),
                        max_chars=self.asr_config.initial_prompt_max_chars,
                        max_apps=self.asr_config.max_vocabulary_apps,
                    )
                except Exception as exc:
                    logger.warning("Vocabulario dinamico no disponible: %s", exc)
            self._initial_prompt = prompt or LEGACY_INITIAL_PROMPT
            logger.info("initial_prompt de Whisper (%s caracteres)", len(self._initial_prompt))
        return self._initial_prompt

    def refresh_vocabulary(self) -> None:
        self._initial_prompt = None
        
    def _load_model(self):
        """
        Carga el modelo Whisper.
        """
        try:
            if WhisperModel is None:
                raise RuntimeError("faster_whisper no instalado")
            logger.info(r"Intentando cargar modelo Whisper...")
            # Valores por defecto: CPU int8 (como antes); se cambian en config.
            self.model = WhisperModel(self.model_size, **model_kwargs(self.asr_config))
            logger.info("Modelo Whisper listo (%s, %s)", self.model_size, model_kwargs(self.asr_config))
        except Exception as e:
            logger.warning("TranscriptionNode._load_model: %s", e)
            # Si falla el modelo, crear un modelo nulo para testing
            self.model = None
            logger.warning(r"Usando modo de prueba sin modelo Whisper")
    
    def execute(self, audio: np.ndarray) -> Dict[str, Any]:
        """
        Transcribe el audio a texto.
        
        Args:
            audio: Array de audio
            
        Returns:
            Resultado de transcripcion
        """
        try:
            if self.model is None:
                self._load_model()
                if self.model is None:
                    # Sin modelo Whisper no se puede transcribir: se informa del
                    # fallo en lugar de inventar un texto que se ejecutaria
                    # como si el usuario lo hubiera dicho.
                    return {
                        "node": self.name,
                        "success": False,
                        "text": "",
                        "confidence": 0.0,
                        "error": "Modelo Whisper no disponible",
                    }
            
            # Parametros desde config (4.5.6.3); word_timestamps=True por
            # defecto para la confianza real (4.5.6.5).
            segments, info = self.model.transcribe(
                audio, **transcribe_kwargs(self.asr_config, self.get_initial_prompt())
            )

            # Iterar los segmentos es lo que ejecuta la transcripcion.
            record = build_transcription_record(segments, info)
            logger.debug(
                "Transcripcion: confianza=%.3f (%s) avg_logprob=%s "
                "no_speech_max=%s compression_max=%s idioma_prob=%s",
                record.confidence,
                record.confidence_method,
                record.avg_logprob,
                record.max_no_speech_prob,
                record.max_compression_ratio,
                record.language_probability,
            )

            return {
                "node": self.name,
                "success": True,
                "text": record.text,
                "original_text": record.original_text,
                # Confianza de la transcripcion, no del idioma.
                "confidence": record.confidence,
                "confidence_method": record.confidence_method,
                "language_probability": record.language_probability,
                "record": record,
            }

        except Exception as e:
            logger.debug("TranscriptionNode.execute: %s", e)
            return {
                "node": self.name,
                "success": False,
                "error": str(e),
                "text": "",
                "confidence": 0.0,
            }


class DetectionNode(AudioNode):
    """
    Nodo para deteccion de voz en audio.
    """
    
    def execute(self, audio_queue: queue.Queue, threshold: float) -> Dict[str, Any]:
        """
        Detecta voz en la cola de audio.
        
        Args:
            audio_queue: Cola de audio
            threshold: Umbral de deteccion
            
        Returns:
            Resultado de deteccion
        """
        logger.info(r"Buscando voz en audio...")
        
        # Esperar a detectar voz con timeout
        start_time = time.time()
        timeout = 30  # 30 segundos timeout para mayor tolerancia
        
        while True:
            if audio_queue.empty():
                time.sleep(0.01)
                # Verificar timeout
                if time.time() - start_time > timeout:
                    logger.info(r"Timeout esperando voz")
                    return {
                        "node": self.name,
                        "success": False,
                        "speech_detected": False,
                        "error": "Timeout esperando voz"
                    }
                continue
            
            chunk = audio_queue.get().flatten()
            if self._rms(chunk) > threshold:
                logger.info(r"Habla detectada")
                return {
                    "node": self.name,
                    "success": True,
                    "speech_detected": True,
                    "chunk": chunk
                }
    
    def _rms(self, audio: np.ndarray) -> float:
        """
        Calcula el nivel de amplitud RMS del audio.
        """
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio))))


class RecordingNode(AudioNode):
    """
    Nodo para grabacion de audio.
    """
    
    def execute(self, audio_queue: queue.Queue, threshold: float) -> Dict[str, Any]:
        """
        Graba el audio detectado.
        
        Args:
            audio_queue: Cola de audio
            threshold: Umbral de deteccion
            
        Returns:
            Resultado de grabacion
        """
        speech_chunks = []
        silence_time = 0
        recording_time = 0
        
        while True:
            if audio_queue.empty():
                # Wait for audio data instead of breaking immediately
                time.sleep(0.01)
                recording_time += self.capabilities.block_duration
                timeout_check = recording_time >= self.capabilities.max_recording_time
                if timeout_check:
                    break
                continue
            
            chunk = audio_queue.get().flatten()
            volume = self._rms(chunk)
            speech_chunks.append(chunk)
            recording_time += self.capabilities.block_duration
            
            if volume < threshold:
                silence_time += self.capabilities.block_duration
            else:
                silence_time = 0
            
            if silence_time >= self.capabilities.silence_threshold or \
               recording_time >= self.capabilities.max_recording_time:
                break
        
        audio = np.concatenate(speech_chunks)
        
        return {
            "node": self.name,
            "success": True,
            "audio": audio,
            "duration": recording_time,
            "chunks_count": len(speech_chunks)
        }
    
    def _rms(self, audio: np.ndarray) -> float:
        """
        Calcula el nivel de amplitud RMS del audio.
        """
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio))))


class Ear:
    """
    Sistema de percepcion auditiva integrado con la arquitectura de planificacion jerarquica.
    """
    
    def __init__(self, model_size: Optional[str] = None, language: Optional[str] = None):
        """
        Inicializa el sistema auditivo con capacidades modulares.
        
        Args:
            model_size: Tamano del modelo Whisper (tiny, base, small, medium, large)
            language: Idioma para transcripcion
        """
        self.asr_config = load_asr_config()
        self.model_size = model_size or self.asr_config.model_size
        self.language = language or self.asr_config.language
        self.conversation_memory = ConversationMemory()
        # Estado de la entrada de audio (4.5.6.13): DISPONIBLE, SIN_PERMISO,
        # NO_SOPORTADO o NO_VERIFICADO con detalle e instrucciones.
        self.last_audio_status: Optional[Dict[str, Any]] = None
        # Registro completo (texto original, confianza, metricas) de la ultima
        # frase devuelta por listen() o process_audio_batch(). listen() sigue
        # devolviendo solo el texto para no romper a sus consumidores.
        self.last_transcription: Optional[TranscriptionRecord] = None

        # Crear nodos del pipeline de procesamiento
        self.calibration_node = CalibrationNode("audio_calibration")
        self.detection_node = DetectionNode("speech_detection")
        self.recording_node = RecordingNode("audio_recording")
        self.transcription_node = TranscriptionNode(
            "speech_transcription",
            self.model_size,
            self.language,
            asr_config=self.asr_config,
        )
        
        logger.info(r"Sistema auditivo inicializado")
    
    def _load_model(self):
        """Carga el modelo Whisper."""
        try:
            self.model = WhisperModel(
                self.model_size,
                device="cuda",
                compute_type="float16"
            )
            logger.info(r"Oido listo")
        except Exception as e:
            logger.debug("Ear._load_model: %s", e)
            raise
    
    def get_audio_pipeline(self) -> List[AudioNode]:
        """
        Devuelve el pipeline de procesamiento de audio.
        """
        return [
            self.calibration_node,
            self.detection_node,
            self.recording_node,
            self.transcription_node
        ]
    
    def get_pipeline_cost(self) -> float:
        """
        Calcula el coste total del pipeline de audio.
        """
        return sum(node.get_cost() for node in self.get_audio_pipeline())
    
    def get_pipeline_preconditions(self) -> List[str]:
        """
        Devuelve las precondiciones del pipeline de audio.
        """
        preconditions = []
        for node in self.get_audio_pipeline():
            preconditions.extend(node.get_preconditions())
        return list(set(preconditions))
    
    def get_pipeline_effects(self) -> List[str]:
        """
        Devuelve los efectos del pipeline de audio.
        """
        effects = []
        for node in self.get_audio_pipeline():
            effects.extend(node.get_effects())
        return list(set(effects))
    
    def _load_model(self):
        """
        Carga el modelo Whisper (metodo heredado para compatibilidad).
        """
        try:
            self.model = WhisperModel(
                self.model_size,
                device="cuda",
                compute_type="float16"
            )
            logger.info(r"[+] Oido listo.")
        except Exception as e:
            logger.debug("Ear._load_model: %s", e)
            raise
    
    def listen(self, activation_word: bool = False) -> Optional[str]:
        """
        Escucha el audio del usuario y transcribe usando el pipeline de nodos.
        
        Args:
            activation_word: Si es True, requiere que se mencione "Jarvis"
            
        Returns:
            Texto transcrito o None si hay error
        """
        audio_queue = queue.Queue()
        self.last_transcription = None
        set_last_transcription(None)
        if not self.check_audio_input().get("available"):
            return None

        def callback(indata, frames, time_info, status):
            """Callback para captura de audio."""
            if status:
                pass
            audio_queue.put(indata.copy())
        
        logger.info(r"Escuchando continuamente... (procesando todo audio detectado)")
        
        try:
            with sd.InputStream(
                samplerate=self.calibration_node.capabilities.sample_rate,
                channels=self.calibration_node.capabilities.channels,
                dtype=self.calibration_node.capabilities.dtype,
                blocksize=int(self.calibration_node.capabilities.sample_rate * 
                           self.calibration_node.capabilities.block_duration),
                callback=callback,
            ):
                # Paso 1: Calibracion (solo una vez al inicio)
                logger.info(r"Calibrando umbral de audio...")
                calibration_result = self.calibration_node.execute(audio_queue)
                if not calibration_result["success"]:
                    logger.error(r"Fallo en calibracion de audio")
                    return None
                
                threshold = calibration_result["threshold"]
                noise_level = calibration_result.get("noise_level", 0.0)
                
                # Bucle infinito de escucha continua - Jarvis siempre alerta
                logger.info("Sistema listo para recibir comandos de voz (modo alerta continua)...")
                
                while True:
                    try:
                        # Paso 2: Deteccion de voz
                        logger.debug(r"Esperando deteccion de voz...")
                        detection_result = self.detection_node.execute(audio_queue, threshold)
                        if not detection_result["success"]:
                            continue
                        
                        # Paso 3: Grabacion de audio
                        logger.info(r"Voz detectada, grabando audio...")
                        recording_result = self.recording_node.execute(audio_queue, threshold)
                        if not recording_result["success"]:
                            continue
                        
                        # Paso 4: Transcripcion
                        logger.info(r"Audio grabado, transcribiendo...")
                        transcription_result = self.transcription_node.execute(recording_result["audio"])
                        if not transcription_result["success"]:
                            logger.error(
                                "Transcripcion fallida: %s",
                                transcription_result.get("error", "error desconocido"),
                            )
                            continue
                        
                        texto_final = transcription_result["text"]
                        
                        if not texto_final:
                            logger.warning(r"Transcripcion vacia, continuando...")
                            continue
                        
                        
                        # Verificacion de palabra de activacion si esta habilitada
                        if activation_word:
                            if not self._check_activation_word(texto_final):
                                logger.debug(r"Ignorado: No se escucho el nombre de Jarvis en la frase.")
                                continue
                        
                        # Guardar en memoria conversacional
                        try:
                            self.conversation_memory.add_user_message(texto_final)
                        except Exception as e:
                            logger.debug("Ear.listen: %s", e)
                            # Continuar igualmente, no es critico
                        
                        # Devolver el texto transcrito y volver a empezar para seguir escuchando
                        self.last_transcription = transcription_result.get("record")
                        set_last_transcription(self.last_transcription)
                        logger.debug(r"Comando procesado, volviendo a modo alerta...")
                        return texto_final
                    
                    except Exception as e:
                        logger.debug("Ear.listen: %s", e)
                        continue
                    
        except Exception as e:
            logger.error("Captura de audio fallida: %s", e)
            return None

    def check_audio_input(self, refresh: bool = False) -> Dict[str, Any]:
        """
        Comprueba la entrada de audio antes de abrir el microfono (4.5.6.13).

        Usa la capacidad ``audio_input`` del adaptador de escritorio (Windows:
        consentimiento de microfono y dispositivos de sounddevice; macOS:
        ``AVCaptureDevice``, el permiso pertenece a la app anfitriona). Si falta
        el permiso devuelve ``SIN_PERMISO`` con instrucciones y no se abre el
        microfono. Un estado disponible se cachea; los demas se recalculan.
        """
        if not refresh and self.last_audio_status and self.last_audio_status.get("available"):
            return self.last_audio_status
        if sd is None:
            status = {
                "available": False, "status": "NO_SOPORTADO",
                "detail": "sounddevice no disponible: %s" % _SD_IMPORT_ERROR,
                "instructions": "Instalar sounddevice (pip install sounddevice).",
            }
        else:
            status = {"available": True, "status": "NO_VERIFICADO", "detail": "", "instructions": ""}
            try:
                from src.desktop.platform_contract import Capability, get_desktop_platform

                report = get_desktop_platform().capabilities().get(Capability.AUDIO_INPUT)
                if report is not None:
                    value = getattr(report.status, "value", str(report.status))
                    status = {
                        "available": value in ("DISPONIBLE", "NO_VERIFICADO"),
                        "status": value,
                        "detail": report.detail,
                        "instructions": report.instructions,
                    }
            except Exception as exc:
                # Sin adaptador se intenta abrir el microfono igualmente.
                logger.warning("No se pudo consultar la capacidad audio_input: %s", exc)
        if not status["available"]:
            logger.error(
                "Entrada de audio no disponible (%s): %s. %s",
                status["status"], status["detail"], status["instructions"],
            )
        self.last_audio_status = status
        return status

    def _check_activation_word(self, text: str) -> bool:
        """
        Verifica si el texto contiene una variante de "Jarvis".
        
        Args:
            text: Texto a verificar
            
        Returns:
            True si se encontro una palabra de activacion
        """
        texto_minusculas = text.lower()
        variantes_jarvis = [
            "jarvis", "jarves", "jarbez",
            "garbez", "garves", "jarbes"
        ]
        
        return any(variante in texto_minusculas for variante in variantes_jarvis)
    
    def process_audio_batch(self, audio_chunks: List[np.ndarray]) -> Optional[str]:
        """
        Procesa un lote de audios pregrabados.
        
        Args:
            audio_chunks: Lista de chunks de audio
            
        Returns:
            Texto transcrito o None si hay error
        """
        self.last_transcription = None
        try:
            # Combinar chunks
            audio = np.concatenate(audio_chunks)

            # Transcribir directamente
            transcription_result = self.transcription_node.execute(audio)

            if transcription_result["success"]:
                self.last_transcription = transcription_result.get("record")
                set_last_transcription(self.last_transcription)
                return transcription_result["text"]
            else:
                logger.error(
                    "Transcripcion fallida: %s",
                    transcription_result.get("error", "error desconocido"),
                )
                return None
        
        except Exception as e:
            logger.error("Procesamiento de audio por lotes fallido: %s", e)
            return None
    
    def get_audio_status(self) -> Dict[str, Any]:
        """
        Devuelve el estado actual del sistema de audio.
        """
        return {
            "model_size": self.model_size,
            "language": self.language,
            "pipeline_cost": self.get_pipeline_cost(),
            "pipeline_preconditions": self.get_pipeline_preconditions(),
            "pipeline_effects": self.get_pipeline_effects(),
            "nodes": [
                {
                    "name": node.name,
                    "cost": node.get_cost(),
                    "preconditions": node.get_preconditions(),
                    "effects": node.get_effects()
                }
                for node in self.get_audio_pipeline()
            ]
        }