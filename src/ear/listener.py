# src/ear/listener.py
"""
Percepcion auditiva y transcripcion de voz usando Whisper.
Integrado con el nuevo sistema de planificacion jerarquica.
"""
import queue
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from src.core.config import get_timeout_config
from src.core.log import get_logger
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
    
    def __init__(self, name: str, model_size: str = "medium", language: str = "es"):
        super().__init__(name)
        self.model_size = model_size
        self.language = language
        self.model = None
        self._load_model()
        
    def _load_model(self):
        """
        Carga el modelo Whisper.
        """
        try:
            logger.info(r"Intentando cargar modelo Whisper...")
            self.model = WhisperModel(
                self.model_size,
                device="cpu",  # Usar CPU en lugar de CUDA para evitar problemas
                compute_type="int8"
            )
            logger.info(r"Modelo Whisper listo")
        except Exception as e:
            logger.debug("TranscriptionNode._load_model: %s", e)
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
            
            segments, info = self.model.transcribe(
                audio,
                beam_size=5,
                language=self.language,
                initial_prompt=(
                    "Jarvis, se\u00f1or, abrir, YouTube, Google, LoL, Spotify, comando, "
                    "asistente, tecnolog\u00eda."
                ),
            )
            
            texto_final = ""
            for segment in segments:
                texto_final += segment.text
            
            result = texto_final.strip()
            
            return {
                "node": self.name,
                "success": True,
                "text": result,
                "confidence": info.language_probability if hasattr(info, 'language_probability') else 0.0
            }
        
        except Exception as e:
            logger.debug("TranscriptionNode.execute: %s", e)
            return {
                "node": self.name,
                "success": False,
                "error": str(e),
                "text": ""
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
    
    def __init__(self, model_size: str = "medium", language: str = "es"):
        """
        Inicializa el sistema auditivo con capacidades modulares.
        
        Args:
            model_size: Tamano del modelo Whisper (tiny, base, small, medium, large)
            language: Idioma para transcripcion
        """
        self.model_size = model_size
        self.language = language
        self.conversation_memory = ConversationMemory()
        
        # Crear nodos del pipeline de procesamiento
        self.calibration_node = CalibrationNode("audio_calibration")
        self.detection_node = DetectionNode("speech_detection")
        self.recording_node = RecordingNode("audio_recording")
        self.transcription_node = TranscriptionNode(
            "speech_transcription", 
            model_size, 
            language
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
                        logger.debug(r"Comando procesado, volviendo a modo alerta...")
                        return texto_final
                    
                    except Exception as e:
                        logger.debug("Ear.listen: %s", e)
                        continue
                    
        except Exception as e:
            logger.info("Procesando solicitud: " + str(e))
            return None
    
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
        try:
            # Combinar chunks
            audio = np.concatenate(audio_chunks)
            
            # Transcribir directamente
            transcription_result = self.transcription_node.execute(audio)
            
            if transcription_result["success"]:
                return transcription_result["text"]
            else:
                return None
        
        except Exception as e:
            logger.info("Procesando solicitud: " + str(e))
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