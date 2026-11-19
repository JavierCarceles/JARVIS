"""
Manifiesto local de detectores y modelos de vision.

Agrega la configuracion y la disponibilidad real de cada detector del
pipeline de deteccion de controles interactivos:
UI Automation, OmniParser V2 (icon_detect_v3), PaddleOCR, Qwen3-VL/Ollama
y OpenCV.

Para cada detector se registra: version fijada, ruta de pesos, runtime,
dispositivo CPU/GPU, precision numerica, parametros, licencia, disponibilidad
y fallback.

Nunca descarga pesos ni modelos silenciosamente. Un modelo opcional ausente
se reporta como NO_DISPONIBLE / NO_VERIFICADO, nunca como un resultado
ficticio ni una sustitucion silenciosa.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.log import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Estados de disponibilidad
# ---------------------------------------------------------------------------

STATUS_DISPONIBLE = "disponible"
STATUS_NO_DISPONIBLE = "no_disponible"
STATUS_NO_VERIFICADO = "no_verificado"

STATUS_VALIDOS = frozenset({
    STATUS_DISPONIBLE,
    STATUS_NO_DISPONIBLE,
    STATUS_NO_VERIFICADO,
})

# Identificadores canonicos de fuentes (coherentes con visual_ui_detector_fusion)
SOURCE_UIA = "uia"
SOURCE_OMNIPARSER = "omniparser_v2_icon_detect_v3"
SOURCE_PADDLEOCR = "paddleocr"
SOURCE_QWEN3VL = "qwen3vl"
SOURCE_OPENCV = "opencv"

DETECTORES_POR_DEFECTO = (
    SOURCE_UIA,
    SOURCE_OMNIPARSER,
    SOURCE_PADDLEOCR,
    SOURCE_QWEN3VL,
    SOURCE_OPENCV,
)

# Modelo Qwen3-VL por defecto: el mismo que DEFAULT_VISION_MODEL de
# src/eyes/vision/vision.py y UniversalVisualCalibrator.MODEL (variante
# "instruct", sin razonamiento). No se importa de vision.py para no cargar
# OpenCV ni Ollama al construir el manifiesto.
QWEN3VL_MODEL_DEFECTO = "qwen3-vl:8b-instruct"

# Ruta por defecto del modelo OmniParser (repositorio, no pesos locales).
OMNIPARSER_REPO_ID = "microsoft/OmniParser-v2.0"
OMNIPARSER_MODEL_FILE = "icon_detect_v3/model.pt"
OMNIPARSER_LICENSE = "MIT"

# Version de PaddleOCR declarada por su adaptador.
PADDLEOCR_VERSION = "PP-OCRv5"
PADDLEOCR_ENGINE = "onnxruntime"
PADDLEOCR_LANG = "en"

# Rutas estandar donde pueden encontrarse pesos de PaddleOCR (sin pedir al
# usuario que las pase explicitamente). Busca directorios de modelo oficiales
# de PaddleX/PaddleOCR en el perfil de usuario y en la cache de HuggingFace.
_PADDLEOCR_STANDARD_DIRS = [
    os.path.expanduser(r"~\AppData\Local\paddlex\official_models"),
    os.path.expanduser(r"~\.paddlex\official_models"),
    os.path.expanduser(r"~\AppData\Roaming\paddlex\official_models"),
]

# Rutas estandar donde puede encontrarse el modelo OmniParser icon_detect_v3.
# HF almacena los archivos bajo snapshots/<hash>/icon_detect_v3/model.pt
# y tambien puede haber copias en blobs/.
_OMNIPARSER_STANDARD_DIRS = [
    os.path.expanduser(r"~\.cache\huggingface\hub\models--microsoft--OmniParser-v2.0"),
    os.path.expanduser(r"~\AppData\Local\huggingface\hub\models--microsoft--OmniParser-v2.0"),
    os.path.expanduser(r"~\AppData\Roaming\huggingface\hub\models--microsoft--OmniParser-v2.0"),
]


def _encontrar_paddleocr_modelos() -> tuple[Optional[str], Optional[str]]:
    """Busca automaticamente directorios de modelos PaddleOCR en rutas estandar.

    Retorna (model_dir, rec_model_dir) o (None, None) si no se encuentran.
    Prioriza pares deteccion + reconocimiento de la misma version y familia,
    preferiblemente PP-OCRv6_medium (el que reporta PaddleOCR instalado).
    """
    det_dir: Optional[str] = None
    rec_dir: Optional[str] = None
    # Versiones preferidas, en orden de preferencia.
    versiones_preferidas = ["PP-OCRv6_medium", "PP-OCRv5_server", "PP-OCRv5_mobile"]
    for base in _PADDLEOCR_STANDARD_DIRS:
        if not os.path.isdir(base):
            continue
        try:
            entradas = os.listdir(base)
        except OSError:
            continue
        for version in versiones_preferidas:
            if det_dir is not None and rec_dir is not None:
                break
            for nombre in entradas:
                ruta = os.path.join(base, nombre)
                if not os.path.isdir(ruta):
                    continue
                nombre_lower = nombre.lower()
                version_lower = version.lower()
                if version_lower not in nombre_lower:
                    continue
                if not os.path.exists(os.path.join(ruta, "inference.onnx")):
                    continue
                if det_dir is None and "det" in nombre_lower:
                    det_dir = ruta
                if rec_dir is None and "rec" in nombre_lower:
                    rec_dir = ruta
    return det_dir, rec_dir


def _encontrar_omniparser_modelo() -> Optional[str]:
    """Busca automaticamente el archivo icon_detect_v3/model.pt de OmniParser.

    Retorna la ruta al .pt si se encuentra, o None si no.
    """
    for base in _OMNIPARSER_STANDARD_DIRS:
        if not os.path.isdir(base):
            continue
        try:
            for raiz, _dirs, archivos in os.walk(base):
                for nombre in archivos:
                    if nombre.endswith(".pt") and (
                        "icon_detect" in nombre.lower()
                        or "icon_detect" in raiz.lower()
                    ):
                        return os.path.join(raiz, nombre)
        except OSError:
            continue
    return None


def _ahora_iso() -> str:
    """Fecha y hora actual en ISO 8601 con zona horaria."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Entrada del manifiesto
# ---------------------------------------------------------------------------

@dataclass
class DetectorManifestEntry:
    """Una entrada del manifiesto: configuracion y estado real de un detector."""

    source: str
    model: str
    version: str
    weight_path: Optional[str]
    runtime: str
    device: str
    precision: str
    parameters: Dict[str, Any]
    license: Optional[str]
    status: str
    error: Optional[str]
    fallback: Optional[str]
    checked_at: str
    load_time_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if self.status not in STATUS_VALIDOS:
            raise ValueError(
                "Estado invalido %r para %s: use uno de %s"
                % (self.status, self.source, sorted(STATUS_VALIDOS))
            )

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve un diccionario plano serializable a JSON."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------

@dataclass
class DetectorManifest:
    """Conjunto de entradas de detectores, con estado real comprobado."""

    entries: Dict[str, DetectorManifestEntry] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detectores": {
                source: entry.to_dict()
                for source, entry in self.entries.items()
            },
            "resumen": self.summary(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializa el manifiesto a JSON (sin escribir en disco)."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def get_entry(self, source: str) -> Optional[DetectorManifestEntry]:
        """Devuelve la entrada de un detector, o None si no existe."""
        return self.entries.get(source)

    def available_sources(self) -> List[str]:
        """Fuentes cuyo estado es DISPONIBLE."""
        return sorted(
            source for source, entry in self.entries.items()
            if entry.status == STATUS_DISPONIBLE
        )

    def missing_optional_sources(self) -> List[str]:
        """Fuentes no disponibles ni verificadas (modelos opcionales ausentes)."""
        return sorted(
            source for source, entry in self.entries.items()
            if entry.status in (STATUS_NO_DISPONIBLE, STATUS_NO_VERIFICADO)
        )

    def summary(self) -> Dict[str, Any]:
        """Resumen contable del manifiesto."""
        total = len(self.entries)
        disponibles = len(self.available_sources())
        no_disponibles = sum(
            1 for entry in self.entries.values()
            if entry.status == STATUS_NO_DISPONIBLE
        )
        no_verificados = sum(
            1 for entry in self.entries.values()
            if entry.status == STATUS_NO_VERIFICADO
        )
        return {
            "total": total,
            "disponibles": disponibles,
            "no_disponibles": no_disponibles,
            "no_verificados": no_verificados,
            "fuentes_disponibles": self.available_sources(),
            "fuentes_no_disponibles": self.missing_optional_sources(),
        }

    def save_json(self, path: str, indent: int = 2) -> None:
        """Persiste el manifiesto en un archivo JSON local (ruta elegida por el llamador)."""
        ruta = Path(path)
        if ruta.parent and not ruta.parent.exists():
            ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(self.to_json(indent=indent), encoding="utf-8")
        logger.info("[DETECTOR-MANIFIESTO] Manifiesto guardado en %s", ruta)

    @staticmethod
    def load_json(path: str) -> "DetectorManifest":
        """Carga un manifiesto desde un archivo JSON local."""
        datos = json.loads(Path(path).read_text(encoding="utf-8"))
        entradas: Dict[str, DetectorManifestEntry] = {}
        for source, entrada in datos.get("detectores", {}).items():
            entradas[source] = DetectorManifestEntry(**entrada)
        return DetectorManifest(entries=entradas)


# ---------------------------------------------------------------------------
# Comprobaciones reales de disponibilidad (una por detector)
# ---------------------------------------------------------------------------

def _check_uia() -> DetectorManifestEntry:
    """UI Automation: servicio integrado del SO Windows.

    Disponible si pywinauto y comtypes se importan. No hay pesos que descargar
    ni servidor que consultar.
    """
    inicio = time.perf_counter()
    error: Optional[str] = None
    disponible = False
    try:  # noqa: BLE001
        import pywinauto  # noqa: F401
        import comtypes  # noqa: F401
        disponible = True
    except Exception as exc:  # noqa: BLE001
        error = "UI Automation no disponible: %s" % exc
    return DetectorManifestEntry(
        source=SOURCE_UIA,
        model="windows_ui_automation",
        version="os_integrado",
        weight_path=None,
        runtime="pywinauto + COM/UIAutomationCore (Windows)",
        device="n/a",
        precision="n/a",
        parameters={
            "timeout": 10.0,
            "max_depth": 60,
            "max_elements": 2000,
            "actionable_patterns": sorted([
                "Invoke", "Value", "Toggle", "Selection", "ExpandCollapse",
                "Scroll", "Window", "Transform",
            ]),
        },
        license=None,
        status=STATUS_DISPONIBLE if disponible else STATUS_NO_DISPONIBLE,
        error=error,
        fallback=None,
        checked_at=_ahora_iso(),
        load_time_seconds=round(time.perf_counter() - inicio, 6),
    )


def _check_omniparser(model_path: Optional[str] = None) -> DetectorManifestEntry:
    """OmniParser V2 icon_detect_v3 (TorchScript YOLOv9-E).

    Nunca descarga pesos: si no hay ruta local valida, reporta NO_DISPONIBLE.
    """
    inicio = time.perf_counter()
    error: Optional[str] = None
    disponible = False
    load_time: Optional[float] = None
    device = "cuda" if _torch_cuda_disponible() else "cpu"
    precision = "float16" if device == "cuda" else "float32"
    try:
        from src.hands.detection.omniparser_adapter import OmniParserAdapter  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        error = "OmniParser no verificable: %s" % exc
        return DetectorManifestEntry(
            source=SOURCE_OMNIPARSER,
            model="icon_detect_v3",
            version="v2.0 (modelo icon_detect_v3)",
            weight_path=model_path,
            runtime="torch + TorchScript (huggingface_hub opcional)",
            device=device,
            precision=precision,
            parameters={
                "conf_threshold": 0.25,
                "iou_threshold": 0.7,
                "max_detections": 300,
                "img_size": 640,
                "repo_id": OMNIPARSER_REPO_ID,
                "model_file": OMNIPARSER_MODEL_FILE,
            },
            license=OMNIPARSER_LICENSE,
            status=STATUS_NO_VERIFICADO,
            error=error,
            fallback=None,
            checked_at=_ahora_iso(),
        )
    adapter = OmniParserAdapter(model_path=model_path, device=device)
    disponible = bool(adapter.available)
    if not disponible:
        error = adapter.error
    load_time = adapter.load_time_seconds
    return DetectorManifestEntry(
        source=SOURCE_OMNIPARSER,
        model="icon_detect_v3",
        version="v2.0 (modelo icon_detect_v3)",
        weight_path=model_path,
        runtime="torch + TorchScript (huggingface_hub opcional)",
        device=device,
        precision=precision,
        parameters={
            "conf_threshold": 0.25,
            "iou_threshold": 0.7,
            "max_detections": 300,
            "img_size": 640,
            "repo_id": OMNIPARSER_REPO_ID,
            "model_file": OMNIPARSER_MODEL_FILE,
        },
        license=OMNIPARSER_LICENSE,
        status=STATUS_DISPONIBLE if disponible else STATUS_NO_DISPONIBLE,
        error=error,
        fallback=None,
        checked_at=_ahora_iso(),
        load_time_seconds=load_time,
    )


def _check_paddleocr(
    model_dir: Optional[str] = None,
    rec_model_dir: Optional[str] = None,
) -> DetectorManifestEntry:
    """PaddleOCR (reconocimiento de texto de interfaz).

    Nunca descarga pesos: si no hay ruta local valida ni el paquete instalado,
    reporta NO_DISPONIBLE.
    """
    inicio = time.perf_counter()
    error: Optional[str] = None
    disponible = False
    load_time: Optional[float] = None
    device = "cuda" if _torch_cuda_disponible() else "cpu"
    try:
        from src.hands.detection.paddleocr_adapter import PaddleOCRAdapter  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        error = "PaddleOCR no verificable: %s" % exc
        return DetectorManifestEntry(
            source=SOURCE_PADDLEOCR,
            model="paddleocr",
            version=PADDLEOCR_VERSION,
            weight_path=model_dir,
            runtime="paddlepaddle + paddleocr (%s)" % PADDLEOCR_ENGINE,
            device=device,
            precision="float32",
            parameters={
                "lang": PADDLEOCR_LANG,
                "engine": PADDLEOCR_ENGINE,
                "ocr_version": PADDLEOCR_VERSION,
                "text_score_thresh": 0.5,
                "box_thresh": 0.5,
                "unclip_ratio": 1.6,
                "det_limit_side_len": 960,
                "use_gpu": device == "cuda",
                "model_dir": model_dir,
                "rec_model_dir": rec_model_dir,
            },
            license=None,
            status=STATUS_NO_VERIFICADO,
            error=error,
            fallback=None,
            checked_at=_ahora_iso(),
        )
    adapter = PaddleOCRAdapter(
        model_dir=model_dir,
        rec_model_dir=rec_model_dir,
        device=device,
        use_gpu=(device == "cuda"),
    )
    disponible = bool(adapter.available)
    if not disponible:
        error = adapter.error
    load_time = adapter.load_time_seconds
    return DetectorManifestEntry(
        source=SOURCE_PADDLEOCR,
        model="paddleocr",
        version=PADDLEOCR_VERSION,
        weight_path=model_dir,
        runtime="paddlepaddle + paddleocr (%s)" % PADDLEOCR_ENGINE,
        device=device,
        precision="float32",
        parameters={
            "lang": PADDLEOCR_LANG,
            "engine": PADDLEOCR_ENGINE,
            "ocr_version": PADDLEOCR_VERSION,
            "text_score_thresh": 0.5,
            "box_thresh": 0.5,
            "unclip_ratio": 1.6,
            "det_limit_side_len": 960,
            "use_gpu": device == "cuda",
            "model_dir": model_dir,
            "rec_model_dir": rec_model_dir,
        },
        license=None,
        status=STATUS_DISPONIBLE if disponible else STATUS_NO_DISPONIBLE,
        error=error,
        fallback=None,
        checked_at=_ahora_iso(),
        load_time_seconds=load_time,
    )


def _check_qwen3vl(model: str = QWEN3VL_MODEL_DEFECTO) -> DetectorManifestEntry:
    """Qwen3-VL a traves de Ollama.

    Solo consulta el servidor real (listado de modelos). Nunca descarga el
    modelo. Si el servidor no esta alcanzable, reporta NO_VERIFICADO.
    """
    inicio = time.perf_counter()
    error: Optional[str] = None
    disponible = False
    try:
        import ollama  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        error = "Ollama no instalado: %s" % exc
        return DetectorManifestEntry(
            source=SOURCE_QWEN3VL,
            model=model,
            version=model,
            weight_path=None,
            runtime="ollama (servidor local/remoto)",
            device="n/a",
            precision="n/a",
            parameters={"model": model, "temperature": 0.0},
            license=None,
            status=STATUS_NO_DISPONIBLE,
            error=error,
            fallback=None,
            checked_at=_ahora_iso(),
        )
    try:
        cliente = ollama.Client(timeout=10.0)
        tags = cliente.list()
        modelos = []
        for m in getattr(tags, "models", []) or []:
            modelos.append(getattr(m, "model", str(m)))
        if any(model == m or m.split(":")[0] == model.split(":")[0]
               for m in modelos):
            disponible = True
        else:
            error = "Modelo %s no esta descargado en el servidor Ollama" % model
    except ConnectionError:
        error = "Servidor Ollama no alcanzable: no se pudo verificar el modelo"
    except Exception as exc:  # noqa: BLE001
        error = "Ollama no verificable: %s" % exc
    status = STATUS_DISPONIBLE if disponible else STATUS_NO_VERIFICADO
    return DetectorManifestEntry(
        source=SOURCE_QWEN3VL,
        model=model,
        version=model,
        weight_path=None,
        runtime="ollama (servidor local/remoto)",
        device="n/a",
        precision="n/a",
        parameters={"model": model, "temperature": 0.0},
        license=None,
        status=status,
        error=error,
        fallback=None,
        checked_at=_ahora_iso(),
        load_time_seconds=round(time.perf_counter() - inicio, 6),
    )


def _check_opencv() -> DetectorManifestEntry:
    """OpenCV: libreria de procesamiento de imagen (sin modelo propio)."""
    inicio = time.perf_counter()
    error: Optional[str] = None
    disponible = False
    version = "n/a"
    try:
        import cv2  # noqa: F401
        version = cv2.__version__
        disponible = True
    except Exception as exc:  # noqa: BLE001
        error = "OpenCV no disponible: %s" % exc
    return DetectorManifestEntry(
        source=SOURCE_OPENCV,
        model="opencv",
        version=version,
        weight_path=None,
        runtime="opencv-python",
        device="cpu",
        precision="uint8",
        parameters={},
        license=None,
        status=STATUS_DISPONIBLE if disponible else STATUS_NO_DISPONIBLE,
        error=error,
        fallback=None,
        checked_at=_ahora_iso(),
        load_time_seconds=round(time.perf_counter() - inicio, 6),
    )


def _torch_cuda_disponible() -> bool:
    """True si torch esta instalado y reporta CUDA disponible."""
    try:
        import torch  # noqa: F401
        return bool(torch.cuda.is_available())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Construccion del manifiesto completo
# ---------------------------------------------------------------------------

DETECTOR_CHECKS = {
    SOURCE_UIA: _check_uia,
    SOURCE_OMNIPARSER: lambda: _check_omniparser(),
    SOURCE_PADDLEOCR: lambda: _check_paddleocr(),
    SOURCE_QWEN3VL: lambda: _check_qwen3vl(),
    SOURCE_OPENCV: _check_opencv,
}


def build_detector_manifest(
    model_path: Optional[str] = None,
    model_dir: Optional[str] = None,
    rec_model_dir: Optional[str] = None,
    qwen3vl_model: str = QWEN3VL_MODEL_DEFECTO,
    sources: Optional[List[str]] = None,
) -> DetectorManifest:
    """Construye el manifiesto comprobando la disponibilidad real de cada detector.

    Argumentos:
        model_path: ruta local al modelo OmniParser icon_detect_v3 (None si no
            hay pesos locales; el detector queda NO_DISPONIBLE).
        model_dir: ruta local al directorio de modelos de PaddleOCR para
            deteccion (None si no hay pesos locales; el detector queda
            NO_DISPONIBLE).
        rec_model_dir: ruta local al directorio de modelos de PaddleOCR para
            reconocimiento (None si no hay pesos locales; se usara el mismo
            que model_dir si este se provee).
        qwen3vl_model: etiqueta del modelo Qwen3-VL en el servidor Ollama.
        sources: lista de fuentes a comprobar (por defecto todas).

    Retorna:
        DetectorManifest con una entrada por detector y su estado real.
    """
    # Autodeteccion de modelos en rutas estandar cuando el llamador no las
    # pasa explicitamente. Nunca descarga pesos: solo usa lo que ya esta
    # instalado en el equipo.
    if model_path is None:
        modelo_omniparser = _encontrar_omniparser_modelo()
        if modelo_omniparser is not None:
            model_path = modelo_omniparser
            logger.info(
                "[DETECTOR-MANIFIESTO] Modelo OmniParser autodetectado: %s",
                model_path,
            )
    if model_dir is None:
        det_dir, rec_dir = _encontrar_paddleocr_modelos()
        if det_dir is not None:
            model_dir = det_dir
            logger.info(
                "[DETECTOR-MANIFIESTO] Modelo PaddleOCR deteccion autodetectado: %s",
                model_dir,
            )
        if rec_model_dir is None and rec_dir is not None:
            rec_model_dir = rec_dir
            logger.info(
                "[DETECTOR-MANIFIESTO] Modelo PaddleOCR reconocimiento autodetectado: %s",
                rec_model_dir,
            )

    fuentes = list(sources) if sources else list(DETECTORES_POR_DEFECTO)
    entradas: Dict[str, DetectorManifestEntry] = {}
    for source in fuentes:
        check = DETECTOR_CHECKS.get(source)
        if check is None:
            logger.warning(
                "[DETECTOR-MANIFIESTO] Fuente desconocida ignorada: %s", source
            )
            continue
        try:
            if source == SOURCE_OMNIPARSER:
                entrada = _check_omniparser(model_path=model_path)
            elif source == SOURCE_PADDLEOCR:
                entrada = _check_paddleocr(
                    model_dir=model_dir, rec_model_dir=rec_model_dir
                )
            elif source == SOURCE_QWEN3VL:
                entrada = _check_qwen3vl(model=qwen3vl_model)
            else:
                entrada = check()
        except Exception as exc:  # noqa: BLE001
            entrada = DetectorManifestEntry(
                source=source,
                model="n/a",
                version="n/a",
                weight_path=None,
                runtime="n/a",
                device="n/a",
                precision="n/a",
                parameters={},
                license=None,
                status=STATUS_NO_VERIFICADO,
                error="Comprobacion fallo: %s" % exc,
                fallback=None,
                checked_at=_ahora_iso(),
            )
        entradas[source] = entrada
    return DetectorManifest(entries=entradas)


__all__ = [
    "STATUS_DISPONIBLE",
    "STATUS_NO_DISPONIBLE",
    "STATUS_NO_VERIFICADO",
    "STATUS_VALIDOS",
    "SOURCE_UIA",
    "SOURCE_OMNIPARSER",
    "SOURCE_PADDLEOCR",
    "SOURCE_QWEN3VL",
    "SOURCE_OPENCV",
    "DETECTORES_POR_DEFECTO",
    "QWEN3VL_MODEL_DEFECTO",
    "DetectorManifestEntry",
    "DetectorManifest",
    "build_detector_manifest",
]
