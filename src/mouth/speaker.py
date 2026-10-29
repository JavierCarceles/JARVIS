"""
Síntesis de voz usando motor Kokoro ONNX.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import onnxruntime as rt
import soundfile as sf
import winsound

try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except Exception:
    _PYTTSX3_AVAILABLE = False

from src.utils.config import (
    get_project_root,
    get_timeout_config,
    get_voice_config,
    save_voice_preference,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Mouth:
    """
    Controla la síntesis de voz utilizando el motor Kokoro ONNX.
    """

    GROUP_VOICE_IDS = {
        "af",
        "am",
        "bf",
        "bm",
    }

    def __init__(self):
        """
        Inicializa el motor de síntesis de voz.
        """

        config = get_voice_config()
        timeout_config = get_timeout_config()

        self.PROJECT_ROOT = get_project_root()

        self.MODEL_DIR = self.PROJECT_ROOT / config.model_dir

        self.ONNX_MODEL_PATH = self.MODEL_DIR / "ONNX" / config.onnx_model_file

        self.STYLE_VECTOR_FILE = self.PROJECT_ROOT / config.voice_styles_dir

        self.TOKEN_MAP_FILE = self.PROJECT_ROOT / config.config_file

        self.tokenizer_path = self.PROJECT_ROOT / config.tokenizer_file

        self.session = None

        self.pyttsx3_engine = None

        self.tts_engine = "onnx"

        self.style_vector: Optional[np.ndarray] = None

        self.token_map = None

        self.current_voice_id = str(config.default_voice_id).strip()

        self._voice_cache: Dict[
            str,
            np.ndarray,
        ] = {}

        self._initialize_session()
        self._load_parameters()

    # ========================================================================
    # INICIALIZACIÓN
    # ========================================================================

    def _initialize_session(self):
        """Inicializa la sesión ONNX, con fallback a pyttsx3 si falla."""

        try:
            self.session = rt.InferenceSession(str(self.ONNX_MODEL_PATH))
            self.tts_engine = "onnx"
            logger._print_log("INFO", "[VOICE] Sesión ONNX inicializada correctamente: " + str(self.ONNX_MODEL_PATH), "speaker.py", "_initialize_session", 88)

        except FileNotFoundError as e:
            logger._print_log("ERROR", "[VOICE] No se encontró el modelo ONNX: " + str(self.ONNX_MODEL_PATH) + " (" + str(e) + ")", "speaker.py", "_initialize_session", 92)
            self.session = None
            self._init_pyttsx3_fallback()

        except Exception as e:
            logger._print_log("ERROR", "[VOICE] Error inicializando sesión ONNX: " + str(e), "speaker.py", "_initialize_session", 96)
            self.session = None
            self._init_pyttsx3_fallback()

    def _init_pyttsx3_fallback(self):
        """Inicializa pyttsx3 como motor TTS de respaldo cuando ONNX no está disponible."""
        if not _PYTTSX3_AVAILABLE:
            logger._print_log("ERROR", "[VOICE] pyttsx3 no está instalado. No hay motor TTS disponible.", "speaker.py", "_init_pyttsx3_fallback", 100)
            self.tts_engine = None
            return
        try:
            self.pyttsx3_engine = pyttsx3.init()
            self.tts_engine = "pyttsx3"
            logger._print_log("INFO", "[VOICE] Motor pyttsx3 inicializado como respaldo.", "speaker.py", "_init_pyttsx3_fallback", 106)
        except Exception as e:
            logger._print_log("ERROR", "[VOICE] No se pudo inicializar pyttsx3: " + str(e), "speaker.py", "_init_pyttsx3_fallback", 110)
            self.pyttsx3_engine = None
            self.tts_engine = None

    def _load_parameters(self):
        """Carga los parámetros necesarios del motor."""

        if self.session is None and self.tts_engine != "pyttsx3":
            logger._print_log("error", "[!] ADVERTENCIA: No se pudo iniciar el motor. Revisa las rutas.", "speaker.py", "method", 102)
            return

        self.token_map = self._load_token_map()

        if self.token_map is None:
            logger._print_log("warning", "[VOICE] No se pudo cargar el mapa de tokens.", "speaker.py", "method", 108)
            return

        available_voices = self.get_available_voices()

        if not available_voices:
            logger._print_log("info", "Procesando solicitud", "speaker.py", "method", 93)
            return

        requested_voice = self.current_voice_id

        if requested_voice not in available_voices:
            logger.warning(
                "[VOICE] La voz configurada '%s' no existe en %s",
                requested_voice,
                self.STYLE_VECTOR_FILE,
            )

            if "am_eric" in available_voices:
                requested_voice = "am_eric"

            else:
                requested_voice = available_voices[0]

        if self._load_voice(
            requested_voice,
            persist=False,
        ):
            logger._print_log("INFO", "Procesando solicitud", "speaker.py", "get_available_voices", 136)

        else:
            logger._print_log("ERROR", "[VOICE] No se pudo cargar ninguna voz", "speaker.py", "get_available_voices", 139)

    # ========================================================================
    # VOCES
    # ========================================================================

    def get_available_voices(self) -> List[str]:
        """
        Devuelve los IDs de voz disponibles en models/voices.

        Los archivos de grupo af.bin, am.bin, bf.bin y bm.bin no son
        considerados voces individuales.
        """

        try:
            if not self.STYLE_VECTOR_FILE.exists():
                logger.warning(
                    "[VOICE] No existe el directorio de voces: %s",
                    self.STYLE_VECTOR_FILE,
                )
                return []

            voices: List[str] = []

            for path in self.STYLE_VECTOR_FILE.glob("*.bin"):
                voice_id = path.stem.strip()

                if not voice_id:
                    continue

                if voice_id.casefold() in (self.GROUP_VOICE_IDS):
                    continue

                voices.append(voice_id)

            voices.sort(key=str.casefold)

            return voices

        except Exception as exc:
            logger._print_log("INFO", "Error obteniendo voces disponibles: " + str(exc), "speaker.py", "get_available_voices", 179)
            return []

    def has_voice(
        self,
        voice_id: str,
    ) -> bool:
        """
        Comprueba si existe una voz concreta.
        """

        if not voice_id:
            return False

        voice_id = str(voice_id).strip()

        if not voice_id:
            return False

        if voice_id.casefold() in (self.GROUP_VOICE_IDS):
            return False

        voice_path = self.STYLE_VECTOR_FILE / f"{voice_id}.bin"

        return voice_path.is_file()

    def _load_voice_style_vector(
        self,
        voice_id: str,
    ) -> np.ndarray:
        """
        Carga el vector de estilo correspondiente a voice_id.
        """

        normalized_voice_id = str(voice_id).strip()

        if not normalized_voice_id:
            raise ValueError("El ID de voz está vacío")

        if normalized_voice_id.casefold() in (self.GROUP_VOICE_IDS):
            raise ValueError(
                f"'{normalized_voice_id}' "
                "es un archivo de grupo y no "
                "una voz seleccionable"
            )

        if normalized_voice_id in (self._voice_cache):
            return self._voice_cache[normalized_voice_id]

        voice_path = self.STYLE_VECTOR_FILE / f"{normalized_voice_id}.bin"

        if not voice_path.is_file():
            raise FileNotFoundError(f"No existe la voz: {voice_path}")

        voice_np = np.fromfile(
            str(voice_path),
            dtype=np.float32,
        )

        if voice_np.size == 0:
            raise ValueError(f"La voz está vacía: {voice_path}")

        if voice_np.size % 256 != 0:
            raise ValueError(
                f"El vector de voz no tiene un tamaño compatible con 256: {voice_path}"
            )

        style_vector = voice_np.reshape(
            -1,
            1,
            256,
        )

        self._voice_cache[normalized_voice_id] = style_vector

        logger._print_log("info", f"Voice style loaded: {voice_id} | path={voice_path} | shape={style_vector.shape}", "speaker.py", "method", 254)

        return style_vector

    def _load_voice(
        self,
        voice_id: str,
        persist: bool = False,
    ) -> bool:
        """
        Carga una voz y la establece como voz actual.
        """

        try:
            style_vector = self._load_voice_style_vector(voice_id)

            self.style_vector = style_vector

            self.current_voice_id = str(voice_id).strip()

            if persist:
                saved = save_voice_preference(self.current_voice_id)

                if not saved:
                    logger.warning(
                        "[VOICE] "
                        "La voz se cambió correctamente, "
                        "pero no se pudo guardar la preferencia: %s",
                        self.current_voice_id,
                    )

            return True

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "speaker.py", "method", 93)
            return False

    def set_voice(
        self,
        voice_id: str,
    ) -> bool:
        """
        Cambia la voz actualmente utilizada.

        El cambio se realiza en caliente y no requiere
        reiniciar Jarvis.
        """

        normalized_voice_id = str(voice_id).strip()

        if not normalized_voice_id:
            logger._print_log("warning", "[VOICE] ID de voz vacío", "speaker.py", "method", 305)
            return False

        if not self.has_voice(normalized_voice_id):
            logger.warning(
                "[VOICE] La voz '%s' no existe en %s",
                normalized_voice_id,
                self.STYLE_VECTOR_FILE,
            )
            return False

        if not self._load_voice(
            normalized_voice_id,
            persist=True,
        ):
            return False

        logger._print_log("INFO", "Voz configurada: " + voice_name, "speaker.py", "set_voice", 322)

        return True

    def get_current_voice(self) -> str:
        """Devuelve el ID de la voz actualmente activa."""
        return self.current_voice_id

    # ========================================================================
    # TOKENIZACIÓN
    # ========================================================================

    def _load_token_map(
        self,
    ) -> Optional[dict]:
        """
        Carga el mapa de tokens.
        """

        try:
            with open(
                self.TOKEN_MAP_FILE,
                "r",
                encoding="utf-8",
            ) as f:
                logger.debug(
                    "[VOICE] Mapa de tokens cargado de: %s",
                    self.TOKEN_MAP_FILE,
                )

                return json.load(f)

        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "speaker.py", "method", 93)
            return None

    def _text_to_tokens(
        self,
        text: str,
        voice_id: str,
    ) -> Optional[np.ndarray]:
        """
        Convierte texto a tokens para el modelo.
        """

        logger.debug(
            "[DEBUG TTS] Texto original recibido: '%s'",
            text,
        )

        if not text or text.strip() == "":
            logger._print_log("DEBUG", "[DEBUG TTS] El texto está vacío", "speaker.py", "_text_to_tokens", 373)
            return None

        if not self.tokenizer_path or not self.tokenizer_path.exists():
            logger._print_log("info", "Procesando solicitud", "speaker.py", "method", 93)
            return None

        try:
            with open(
                self.tokenizer_path,
                "r",
                encoding="utf-8",
            ) as f:
                tokenizer_data = json.load(f)

            vocab = tokenizer_data.get(
                "model",
                {},
            ).get(
                "vocab",
                {},
            )

            pad_id = vocab.get(
                "$",
                0,
            )

            text_norm = text.lower()

            text_norm = "".join(
                c
                for c in unicodedata.normalize(
                    "NFD",
                    text_norm,
                )
                if unicodedata.category(c) != "Mn"
            )

            text_norm = text_norm.replace(
                "qu",
                "k",
            )

            text_norm = text_norm.replace(
                "ce",
                "se",
            ).replace(
                "ci",
                "si",
            )

            text_norm = text_norm.replace(
                "c",
                "k",
            )

            text_norm = text_norm.replace(
                "z",
                "s",
            )

            text_norm = text_norm.replace(
                "v",
                "b",
            )

            text_norm = text_norm.replace(
                "j",
                "h",
            )

            text_norm = text_norm.replace(
                "ll",
                "j",
            ).replace(
                "y",
                "j",
            )

            text_norm = text_norm.replace(
                "ñ",
                "nj",
            )

            text_norm = text_norm.replace(
                "g",
                "\u0261",
            )

            text_norm = text_norm.replace(
                "r",
                "\u0279",
            )

            text_norm = text_norm.replace(
                "h",
                "",
            )

            text_norm = text_norm.replace(
                "¿",
                "",
            ).replace(
                "¡",
                "",
            )

            words = text_norm.split()

            phoneme_words = []

            for word in words:
                match = re.search(
                    r"[a-z\u0261\u0279]",
                    word,
                )

                if match:
                    idx = match.start()

                    word = word[:idx] + "\u02c8" + word[idx:]

                phoneme_words.append(word)

            text_phonemes = " ".join(phoneme_words)

            token_ids = [pad_id]

            for char in text_phonemes:
                if char in vocab:
                    token_ids.append(vocab[char])

            token_ids.append(pad_id)

            if len(token_ids) <= 2:
                logger._print_log("debug", "[DEBUG TTS] No se generó ningún token válido.", "speaker.py", "method", 509)
                return None

            return np.array(
                [token_ids],
                dtype=np.int64,
            )

        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "speaker.py", "method", 93)
            return None

    # ========================================================================
    # SÍNTESIS
    # ========================================================================

    def speak(
        self,
        text: str,
        voice_id: Optional[str] = None,
        output_file: str = "output.wav",
    ) -> Optional[str]:
        """
        Convierte texto a voz y lo reproduce.

        Si voice_id es None se utiliza la voz actualmente seleccionada.
        """

        if self.tts_engine is None:
            logger.ERROR(r"[ERROR] Motor no cargado. Imposible hablar.  [file:speaker.py, method:speak, line:573]")
            return None

        if not text or not text.strip():
            logger.DEBUG(r"[DEBUG] Texto vacío, no generando audio.  [file:speaker.py, method:speak, line:542]")
            return None

        # Si ONNX no está disponible, usar pyttsx3
        if self.tts_engine == "pyttsx3" and self.pyttsx3_engine is not None:
            return self._speak_pyttsx3(text, voice_id)

        selected_voice = str(voice_id).strip() if voice_id else self.current_voice_id

        if not selected_voice:
            logger.ERROR(r"[VOICE] No hay una voz seleccionada.  [file:speaker.py, method:speak, line:568]")
            return None

        if selected_voice != self.current_voice_id:
            if not self.set_voice(selected_voice):
                return None

        if self.style_vector is None:
            logger._print_log("error", "[VOICE] No hay vector de estilo cargado.", "speaker.py", "method", 556)
            return None

        tokens_input = self._text_to_tokens(
            text,
            selected_voice,
        )

        if tokens_input is None:
            logger._print_log("warning", "[FALLO] No se pueden generar tokens.", "speaker.py", "method", 565)
            return None

        try:
            num_tokens = tokens_input.shape[1] - 2

            max_style_index = self.style_vector.shape[0] - 1

            max_tokens = min(
                510,
                max_style_index,
            )

            if num_tokens > max_tokens:
                logger.WARNING(r"[ADVERTENCIA] El texto es demasiado largo. Kokoro lo truncará.  [file:speaker.py, method:speak, line:579]")

                num_tokens = max_tokens

                pad_id = tokens_input[0][-1]

                token_ids = list(tokens_input[0][: num_tokens + 1])

                if not token_ids or token_ids[-1] != pad_id:
                    token_ids.append(pad_id)

                tokens_input = np.array(
                    [token_ids],
                    dtype=np.int64,
                )

            num_tokens = min(
                num_tokens,
                max_style_index,
            )

            ref_s = self.style_vector[num_tokens]

            audio = self.session.run(
                None,
                {
                    "input_ids": tokens_input,
                    "style": ref_s,
                    "speed": np.ones(
                        1,
                        dtype=np.float32,
                    ),
                },
            )[0]

            temp_file = tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            )

            temp_path = temp_file.name
            temp_file.close()

            sf.write(
                temp_path,
                audio[0],
                24000,
            )

            logger.debug(
                "[+] Audio temporal generado: %s | voz=%s",
                temp_path,
                selected_voice,
            )

            winsound.PlaySound(
                temp_path,
                winsound.SND_FILENAME,
            )

            logger.DEBUG(r"[+] Audio reproducido  [file:speaker.py, method:speak, line:639]")

            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                    logger._print_log("debug", "[-] Archivo de audio temporal eliminado", "speaker.py", "method", 645)

            except Exception as e:
                logger._print_log("info", "Procesando solicitud", "speaker.py", "method", 93)

            return temp_path

        except Exception as e:
            logger._print_log("error", f"[VOICE] Error en _synthesize_onnx: {e}", "speaker.py", "method", 653)
            return None

    def _speak_pyttsx3(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Sintetiza y reproduce texto usando pyttsx3 (fallback de Windows SAPI).
        """
        try:
            selected_voice = str(voice_id).strip() if voice_id else self.current_voice_id

            if selected_voice:
                voices = self.pyttsx3_engine.getProperty("voices")
                for v in voices:
                    if selected_voice.lower() in v.id.lower() or selected_voice.lower() in v.name.lower():
                        self.pyttsx3_engine.setProperty("voice", v.id)
                        break

            self.pyttsx3_engine.say(text)
            self.pyttsx3_engine.runAndWait()
            return text

        except Exception as e:
            logger._print_log("error", f"[VOICE] Error en _speak_pyttsx3: {e}", "speaker.py", "method", 700)
            return None

    def speak_async(
        self,
        text: str,
        voice_id: Optional[str] = None,
        output_file: str = "output.wav",
    ):
        """
        Versión async de speak que no bloquea.
        """

        def _speak():
            self.speak(
                text,
                voice_id,
                output_file,
            )

        thread = threading.Thread(
            target=_speak,
            daemon=True,
        )

        thread.start()

        return thread
