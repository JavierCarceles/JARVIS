# -*- coding: ascii -*-
"""
Harness de precision de calibracion UI (unidad 3.8.6.10.3).

Ejecuta el pipeline de produccion sobre la fixture de calibracion maximizada
en el monitor de pruebas (monitor no principal mas a la derecha) y mide, por
fuente de deteccion (accesibilidad UIA, vision Qwen3-VL y fusion), precision,
recall, F1, IoU, error de centro, click correcto, falsos accionables, latencia
y recursos (CPU/RAM/VRAM).

Los criterios de aceptacion estan FIJADOS ANTES de ejecutar (constantes
CRITERIO_* al inicio de este archivo). Ninguna metrica se ajusta a posteriori
para forzar un resultado positivo.

Espacio de medida: pixeles fisicos del area cliente de la fixture. La
geometria de referencia de la fixture es [x, y, ancho, alto] en pixeles
logicos de Qt; se convierte a [x1, y1, x2, y2] multiplicando por la escala
DPI real de la ventana (GetDpiForWindow / 96, leida del adaptador de
escritorio, no de un detector). Las cajas de UIA se pasan a coordenadas del
area cliente restando su origen en pantalla y las de vision ya estan en
pixeles de la captura del area cliente.

Ambito de la medida: las detecciones fuera del area cliente (barra de titulo),
fuera de pantalla o que cubren casi toda la ventana (contenedores) no se
evaluan; las que caen dentro de un control de referencia sin emparejarse
(filas de una lista, pestanas, lineas del scroll, controles internos del
grupo) cuentan como subelementos, no como falsos positivos. Una deteccion
accionable sobre el control dibujado sin accesibilidad siempre es un falso
accionable.

Aserciones de la parte real: ninguna fuente termina con error; UIA cumple
recall, IoU, error de centro y click correcto contra la referencia (valida la
conversion de coordenadas de la medida); Qwen3-VL devuelve elementos, todas
sus cajas caen dentro de la captura, la captura se reduce antes de enviarla al
modelo y el centro de cada boton con texto (Aceptar, Cancelar, Abrir popup)
cae dentro del boton; ninguna fuente supera la latencia maxima. El
cumplimiento del resto de criterios por fuente se calcula y se guarda en el
informe JSON (``criterios_cumplidos``) y en la salida de consola.

La parte GUI real lanza UNA sola instancia de la fixture (proceso propio,
controlado por la prueba) en el monitor no principal situado mas a la derecha
segun la enumeracion real, la maximiza, espera a que su geometria y su escala
sean estables, captura su area cliente y ejecuta los tres pipelines de
deteccion sobre esa captura. Compara los resultados contra la verdad-terreno
de la fixture sin que el detector la consuma.

Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable, la parte real
se salta; la parte offscreen (logica de metricas con datos sinteticos) siempre
se ejecuta, tambien fuera de Windows.

Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de la fixture que esta prueba abrio.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import subprocess
import sys
import time
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import psutil

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.detection.ui_automation_adapter import (
    UIAutomationAdapter,
    UIAutomationElement,
    UIAutomationTree,
)
from src.hands.detection.calibration_quality_gate import assess_candidate
from src.hands.detection.calibration_quality_gate import DetectionThresholds
from src.eyes.capture.screen_capture import ScreenCapture
from src.eyes.vision.vision import DEFAULT_VISION_MODEL, MODEL_IMAGE_MAX_PIXELS, Vision
from src.eyes.detection.visual_ui_detector_fusion import (
    VisualUIDetectorFusion,
    DetectedCandidate,
    SOURCE_UIA,
    SOURCE_QWEN3VL,
)
from src.core.ui_element_model import UIElementData

from tests.fixtures.gui_calibration_app.controls import (
    CONTROL_SPECS,
    CONTROLES_SIN_ACCESIBILIDAD,
    TAMANIO_NOMINAL,
)
from tests.fixtures.gui_calibration_app.truth_ground import (
    TRUTH_GROUND_PATH,
    ACTION_COUNTS_PATH,
    construir_truth_ground,
    get_truth_ground,
)
from tests.helpers.ollama_session import servidor_ollama_de_sesion

TITULO_FIXTURE = "JARVIS GUI Calibration Fixture"
FIXTURE_RUN = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "fixtures",
        "gui_calibration_app", "run.py",
    )
)
GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "_gui_accuracy_harness_lock.lock")

# ---------------------------------------------------------------------------
# Criterios de aceptacion FIJADOS ANTES de ejecutar (unidad 3.8.6.10.3).
# Ninguna metrica se ajusta despues de la ejecucion para forzar un PASS.
# ---------------------------------------------------------------------------
CRITERIO_IOU_MEDIO_MIN = 0.50          # IoU medio minimo para emparejamiento correcto
CRITERIO_ERROR_CENTRO_MAX_PX = 45.0    # Error de centro maximo (pixeles del area cliente)
CRITERIO_PRECISION_MIN = 0.80
CRITERIO_RECALL_MIN = 0.80
CRITERIO_F1_MIN = 0.80
CRITERIO_CLICK_CORRECTO_MIN = 0.90     # Fraccion de controles con centro dentro de la referencia
CRITERIO_FALSOS_ACCIONABLES_MAX = 0    # canvas_mano nunca debe marcarse accionable sin evidencia
CRITERIO_LATENCIA_MAX_S = 300.0        # Tiempo maximo por fuente de deteccion
IOU_EMPAREJAMIENTO = 0.50              # Umbral de IoU para considerar deteccion como verdadero positivo

# Botones con texto visible que cualquier detector visual debe localizar.
BOTONES_CON_TEXTO = ("btn_aceptar", "btn_cancelar", "popup_info")
# Una deteccion no emparejada con al menos esta fraccion de su area dentro de
# un control de referencia es un subelemento de ese control.
CONTENCION_SUBELEMENTO = 0.80
# Una deteccion que cubre al menos esta fraccion del area cliente es un
# contenedor de la ventana (raiz, area central), no un control.
FRACCION_CONTENEDOR_VENTANA = 0.90


def _gui_lock_activo() -> bool:
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        pid = int(pid_texto)
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock() -> None:
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock() -> None:
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


def _iou(a: Optional[List[int]], b: Optional[List[int]]) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    try:
        ax1, ay1, ax2, ay2 = [float(v) for v in a]
        bx1, by1, bx2, by2 = [float(v) for v in b]
    except (TypeError, ValueError):
        return 0.0
    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1); inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _centro(bbox: Optional[List[int]]) -> Optional[Tuple[float, float]]:
    if not bbox or len(bbox) != 4:
        return None
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _distancia_centro(a: Optional[List[int]], b: Optional[List[int]]) -> Optional[float]:
    ca = _centro(a); cb = _centro(b)
    if ca is None or cb is None:
        return None
    return ((cb[0] - ca[0]) ** 2 + (cb[1] - ca[1]) ** 2) ** 0.5


def _cliente_offset_pantalla(hwnd: int) -> Tuple[int, int]:
    """Devuelve (left, top) del area cliente de la ventana en coordenadas de pantalla."""
    import ctypes.wintypes  # solo Windows

    user32 = ctypes.windll.user32
    punto = ctypes.wintypes.POINT(0, 0)
    if not user32.ClientToScreen(ctypes.c_void_p(int(hwnd)), ctypes.byref(punto)):
        return (0, 0)
    return (int(punto.x), int(punto.y))


def _area_cliente_pantalla(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Devuelve (left, top, right, bottom) del area cliente en coordenadas de pantalla."""
    import ctypes.wintypes  # solo Windows

    user32 = ctypes.windll.user32
    rect = ctypes.wintypes.RECT()
    if not user32.GetClientRect(ctypes.c_void_p(int(hwnd)), ctypes.byref(rect)):
        return None
    cl, ct = _cliente_offset_pantalla(hwnd)
    return (cl, ct, cl + (rect.right - rect.left), ct + (rect.bottom - rect.top))


def _recursos_proceso() -> Dict[str, float]:
    """CPU (%), RAM (MB) del proceso actual y del proceso Ollama si existe."""
    resultado: Dict[str, float] = {}
    try:
        p = psutil.Process()
        resultado["cpu_actual_percent"] = float(p.cpu_percent(interval=0.1))
        resultado["ram_actual_mb"] = float(p.memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        resultado["cpu_actual_percent"] = -1.0
        resultado["ram_actual_mb"] = -1.0
    # Proceso Ollama (servidor de modelos de vision)
    ollama_ram = 0.0
    ollama_cpu = 0.0
    encontrado = False
    try:
        for proc in psutil.process_iter(["name", "memory_info", "cpu_percent"]):
            try:
                nombre = (proc.info.get("name") or "").lower()
                if "ollama" in nombre:
                    encontrado = True
                    mem = proc.info.get("memory_info")
                    if mem is not None:
                        ollama_ram += float(mem.rss) / (1024.0 * 1024.0)
                    cpu = proc.info.get("cpu_percent")
                    if cpu is not None:
                        ollama_cpu += float(cpu)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        encontrado = False
    resultado["ollama_encontrado"] = 1.0 if encontrado else 0.0
    resultado["ollama_ram_mb"] = ollama_ram
    resultado["ollama_cpu_percent"] = ollama_cpu
    resultado["vram_mb"] = -1.0  # No se puede medir VRAM sin controlador GPU especifico
    return resultado


def _elemento_a_candidato_uia(elem: UIAutomationElement, hwnd: int, pid: int) -> DetectedCandidate:
    """Convierte un UIAutomationElement en un DetectedCandidate (fuente UIA)."""
    cx, cy = _centro(elem.bounding_rectangle) if elem.bounding_rectangle else (0, 0)
    patrones = set(elem.patterns or [])
    interactivo = bool(
        elem.visible and elem.is_enabled and not elem.is_offscreen
        and any(p in patrones for p in ("Invoke", "Value", "Toggle", "Selection", "ExpandCollapse", "Scroll", "Window", "Transform"))
    )
    nombre = (elem.automation_id or "").split(".")[-1] if elem.automation_id else (elem.name or "element")
    element = UIElementData(
        name=nombre,
        type=str(elem.control_type or "unknown"),
        text=str(elem.name or ""),
        description="",
        bbox=list(elem.bounding_rectangle) if elem.bounding_rectangle else None,
        center=[int(round(cx)), int(round(cy))] if elem.bounding_rectangle else [],
        screen=0,
        interactive=interactivo,
        confidence=0.9,
        calibrated=False,
        calibration_data={"source": SOURCE_UIA, "automation_id": elem.automation_id, "control_type": elem.control_type},
        visible=bool(elem.visible),
        enabled=bool(elem.is_enabled),
        actions=list(elem.patterns or []),
    )
    return DetectedCandidate(
        source=SOURCE_UIA,
        element=element,
        confidence=0.9,
        bbox=list(elem.bounding_rectangle) if elem.bounding_rectangle else None,
        center=[int(round(cx)), int(round(cy))] if elem.bounding_rectangle else None,
        screen=0,
        window_handle=hwnd,
        process_id=pid,
        raw={
            "automation_id": elem.automation_id,
            "name": elem.name,
            "control_type": elem.control_type,
            "patterns": list(elem.patterns or []),
            "is_enabled": bool(elem.is_enabled),
            "visible": bool(elem.visible),
            "is_offscreen": bool(elem.is_offscreen),
            "handle": int(elem.handle or 0),
        },
    )


def _elemento_a_candidato_vision(element: Any, hwnd: int, pid: int) -> DetectedCandidate:
    """Convierte un UIElement (vision) en un DetectedCandidate (fuente QWEN3VL)."""
    cx, cy = _centro(element.bbox) if element.bbox else (0.0, 0.0)
    element_data = UIElementData(
        name=str(element.name or ""),
        type=str(getattr(element, "type", "unknown") or "unknown"),
        text=str(getattr(element, "text", "") or ""),
        description=str(getattr(element, "description", "") or ""),
        bbox=list(element.bbox) if element.bbox else None,
        center=[int(round(cx)), int(round(cy))] if element.bbox else [],
        screen=0,
        interactive=bool(getattr(element, "interactive", True)),
        confidence=float(getattr(element, "confidence", 0.0) or 0.0),
        calibrated=False,
        calibration_data={"source": SOURCE_QWEN3VL},
        visible=True,
        enabled=True,
        actions=[],
    )
    return DetectedCandidate(
        source=SOURCE_QWEN3VL,
        element=element_data,
        confidence=float(getattr(element, "confidence", 0.0) or 0.0),
        bbox=list(element.bbox) if element.bbox else None,
        center=[int(round(cx)), int(round(cy))] if element.bbox else None,
        screen=0,
        window_handle=hwnd,
        process_id=pid,
        raw={"type": str(getattr(element, "type", "") or ""), "text": str(getattr(element, "text", "") or "")},
    )


@dataclass
class ResultadoMetrica:
    fuente: str
    total_referencia: int = 0
    total_detectados: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    iou_medio: float = 0.0
    error_centro_medio_px: float = 0.0
    click_correcto: float = 0.0
    falsos_accionables: List[str] = field(default_factory=list)
    fuera_de_ambito: int = 0
    subelementos: int = 0
    latencia_s: float = 0.0
    cpu_actual_percent: float = -1.0
    ram_actual_mb: float = -1.0
    ollama_ram_mb: float = -1.0
    ollama_cpu_percent: float = -1.0
    vram_mb: float = -1.0
    error: Optional[str] = None
    detalle: Dict[str, Any] = field(default_factory=dict)
    criterios_cumplidos: Dict[str, bool] = field(default_factory=dict)

    def a_dict(self) -> Dict[str, Any]:
        return {
            "fuente": self.fuente,
            "total_referencia": self.total_referencia,
            "total_detectados": self.total_detectados,
            "fuera_de_ambito": self.fuera_de_ambito,
            "subelementos": self.subelementos,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "iou_medio": round(self.iou_medio, 4),
            "error_centro_medio_px": round(self.error_centro_medio_px, 2),
            "click_correcto": round(self.click_correcto, 4),
            "falsos_accionables": list(self.falsos_accionables),
            "latencia_s": round(self.latencia_s, 3),
            "cpu_actual_percent": self.cpu_actual_percent,
            "ram_actual_mb": round(self.ram_actual_mb, 2),
            "ollama_ram_mb": round(self.ollama_ram_mb, 2),
            "ollama_cpu_percent": round(self.ollama_cpu_percent, 2),
            "vram_mb": self.vram_mb,
            "error": self.error,
            "detalle": dict(self.detalle),
            "criterios_cumplidos": dict(self.criterios_cumplidos),
        }


def _referencia_en_pixeles(controles: List[Dict[str, Any]], escala: float) -> List[Dict[str, Any]]:
    """Copia los controles de referencia anadiendo ``bbox`` [x1, y1, x2, y2].

    ``geometry`` de la fixture es [x, y, ancho, alto] en pixeles logicos de Qt
    relativos al area cliente; ``bbox`` es esa misma caja en pixeles fisicos
    (``escala`` = DPI real de la ventana / 96). Sin geometria, ``bbox`` es None.
    """
    resultado: List[Dict[str, Any]] = []
    for control in controles:
        copia = dict(control)
        geo = control.get("geometry")
        if geo is not None and len(geo) == 4:
            x, y, ancho, alto = [float(v) for v in geo]
            copia["bbox"] = [
                int(round(x * escala)),
                int(round(y * escala)),
                int(round((x + ancho) * escala)),
                int(round((y + alto) * escala)),
            ]
        else:
            copia["bbox"] = None
        resultado.append(copia)
    return resultado


def _centro_en_zona_util(caja: Optional[List[int]], ref_bbox: Optional[List[int]]) -> bool:
    """El centro de ``caja`` cae dentro de ``ref_bbox`` dejando un 10% de margen interno."""
    centro = _centro(caja)
    if centro is None or not ref_bbox or len(ref_bbox) != 4:
        return False
    cx, cy = centro
    rx1, ry1, rx2, ry2 = ref_bbox
    margen_x = (rx2 - rx1) * 0.10
    margen_y = (ry2 - ry1) * 0.10
    return (rx1 + margen_x <= cx <= rx2 - margen_x) and (ry1 + margen_y <= cy <= ry2 - margen_y)


def _fuera_de_ambito(det: DetectedCandidate, tamano_cliente: Optional[Tuple[int, int]]) -> bool:
    """Deteccion que no se evalua: sin caja, fuera de pantalla, fuera del area cliente o contenedor de la ventana."""
    if not det.bbox or len(det.bbox) != 4:
        return True
    if bool((det.raw or {}).get("is_offscreen")):
        return True
    if tamano_cliente is None:
        return False
    ancho, alto = tamano_cliente
    cx, cy = _centro(det.bbox)
    if not (0 <= cx < ancho and 0 <= cy < alto):
        return True
    x1, y1, x2, y2 = det.bbox
    area = max(0, x2 - x1) * max(0, y2 - y1)
    return area >= FRACCION_CONTENEDOR_VENTANA * ancho * alto


def _referencia_contenedora(caja: List[int], referencia: List[Dict[str, Any]]) -> Optional[int]:
    """Indice del control de referencia mas pequeno que contiene la caja (>= CONTENCION_SUBELEMENTO)."""
    x1, y1, x2, y2 = caja
    area = max(0, x2 - x1) * max(0, y2 - y1)
    if area <= 0:
        return None
    mejor: Optional[Tuple[int, int]] = None
    for j, ref in enumerate(referencia):
        rb = ref.get("bbox")
        if not rb:
            continue
        ix = max(0, min(x2, rb[2]) - max(x1, rb[0]))
        iy = max(0, min(y2, rb[3]) - max(y1, rb[1]))
        if ix * iy >= CONTENCION_SUBELEMENTO * area:
            area_ref = (rb[2] - rb[0]) * (rb[3] - rb[1])
            if mejor is None or area_ref < mejor[1]:
                mejor = (j, area_ref)
    return mejor[0] if mejor else None


def _emparejar(
    detectados: List[DetectedCandidate],
    referencia: List[Dict[str, Any]],
    iou_umbral: float,
) -> Tuple[List[Tuple[int, int, float]], List[int], List[int]]:
    """Empareja detectados con referencia uno a uno (``bbox`` de la referencia).

    Primero por nombre (automation_id ultimo componente == id de referencia),
    luego por IoU >= umbral para los restantes, asignando de mayor a menor IoU.

    Retorna (pares (idx_det, idx_ref, iou), idx_det_no_emparejados, idx_ref_no_emparejados).
    """
    n_det = len(detectados)
    n_ref = len(referencia)
    det_usados: set = set()
    ref_usados: set = set()
    pares: List[Tuple[int, int, float]] = []

    # Paso 1: emparejar por nombre exacto (robusto a jerarquia de automation_id).
    for i, det in enumerate(detectados):
        det_nombre = str(det.element.name or "")
        if not det_nombre:
            continue
        for j, ref in enumerate(referencia):
            if j in ref_usados:
                continue
            if det_nombre == str(ref.get("id", "")):
                pares.append((i, j, _iou(det.bbox, ref.get("bbox"))))
                det_usados.add(i)
                ref_usados.add(j)
                break

    # Paso 2: emparejar por IoU los restantes, de mayor a menor IoU.
    candidatos: List[Tuple[float, int, int]] = []
    for i, det in enumerate(detectados):
        if i in det_usados:
            continue
        for j, ref in enumerate(referencia):
            if j in ref_usados or not ref.get("bbox"):
                continue
            iou = _iou(det.bbox, ref["bbox"])
            if iou >= iou_umbral:
                candidatos.append((iou, i, j))
    for iou, i, j in sorted(candidatos, key=lambda c: (-c[0], c[1], c[2])):
        if i in det_usados or j in ref_usados:
            continue
        pares.append((i, j, iou))
        det_usados.add(i)
        ref_usados.add(j)

    det_no = [i for i in range(n_det) if i not in det_usados]
    ref_no = [j for j in range(n_ref) if j not in ref_usados]
    return pares, det_no, ref_no


def _evaluar_criterios(r: "ResultadoMetrica") -> Dict[str, bool]:
    """Cumplimiento de cada criterio fijado para una fuente."""
    hay_pares = r.tp > 0
    return {
        "precision": r.precision >= CRITERIO_PRECISION_MIN,
        "recall": r.recall >= CRITERIO_RECALL_MIN,
        "f1": r.f1 >= CRITERIO_F1_MIN,
        "iou_medio": hay_pares and r.iou_medio >= CRITERIO_IOU_MEDIO_MIN,
        "error_centro": hay_pares and r.error_centro_medio_px <= CRITERIO_ERROR_CENTRO_MAX_PX,
        "click_correcto": hay_pares and r.click_correcto >= CRITERIO_CLICK_CORRECTO_MIN,
        "falsos_accionables": len(r.falsos_accionables) <= CRITERIO_FALSOS_ACCIONABLES_MAX,
        "latencia": r.latencia_s <= CRITERIO_LATENCIA_MAX_S,
    }


def _calcular_metrica(
    fuente: str,
    detectados: List[DetectedCandidate],
    referencia: List[Dict[str, Any]],
    iou_umbral: float,
    latencia_s: float,
    recursos: Dict[str, float],
    controles_sin_accesibilidad: List[str],
    tamano_cliente: Optional[Tuple[int, int]] = None,
) -> ResultadoMetrica:
    """Metricas de una fuente contra la referencia en pixeles (``bbox``).

    Las detecciones fuera de ambito no se evaluan; las no emparejadas que caen
    dentro de un control de referencia son subelementos; el resto de no
    emparejadas son falsos positivos.
    """
    pares, det_no, ref_no = _emparejar(detectados, referencia, iou_umbral)
    fuera: List[int] = []
    subelementos: List[Tuple[int, int]] = []
    falsos_positivos: List[int] = []
    for i in det_no:
        det = detectados[i]
        if _fuera_de_ambito(det, tamano_cliente):
            fuera.append(i)
            continue
        contenedor = _referencia_contenedora(det.bbox, referencia)
        if contenedor is not None:
            subelementos.append((i, contenedor))
        else:
            falsos_positivos.append(i)

    tp = len(pares)
    fp = len(falsos_positivos)
    fn = len(ref_no)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    ious = [iou for (_, _, iou) in pares]
    iou_medio = (sum(ious) / len(ious)) if ious else 0.0

    errores_centro: List[float] = []
    click_ok = 0
    for (i, j, _iou_par) in pares:
        det = detectados[i]
        ref_bbox = referencia[j].get("bbox")
        d = _distancia_centro(det.bbox, ref_bbox)
        if d is not None:
            errores_centro.append(d)
            if _centro_en_zona_util(det.bbox, ref_bbox):
                click_ok += 1
    error_centro_medio = (sum(errores_centro) / len(errores_centro)) if errores_centro else 0.0
    click_correcto = (click_ok / tp) if tp > 0 else 0.0

    # Falsos accionables: falsos positivos marcados como interactivos y
    # cualquier deteccion interactiva sobre un control sin accesibilidad
    # (canvas_mano), emparejada o como subelemento.
    falsos: List[str] = []
    for i in falsos_positivos:
        det = detectados[i]
        if bool(det.element.interactive):
            falsos.append(str(det.element.name or det.element.type or "desconocido"))
    sobre_referencia = [(i, j) for (i, j, _) in pares] + subelementos
    for (i, j) in sobre_referencia:
        ref_id = str(referencia[j].get("id", ""))
        if ref_id in controles_sin_accesibilidad and bool(detectados[i].element.interactive):
            if ref_id not in falsos:
                falsos.append(ref_id)

    return ResultadoMetrica(
        fuente=fuente,
        total_referencia=len(referencia),
        total_detectados=len(detectados),
        fuera_de_ambito=len(fuera),
        subelementos=len(subelementos),
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        iou_medio=iou_medio,
        error_centro_medio_px=error_centro_medio,
        click_correcto=click_correcto,
        falsos_accionables=falsos,
        latencia_s=latencia_s,
        cpu_actual_percent=recursos.get("cpu_actual_percent", -1.0),
        ram_actual_mb=recursos.get("ram_actual_mb", -1.0),
        ollama_ram_mb=recursos.get("ollama_ram_mb", -1.0),
        ollama_cpu_percent=recursos.get("ollama_cpu_percent", -1.0),
        vram_mb=recursos.get("vram_mb", -1.0),
    )


_RECURSOS_VACIOS = {
    "cpu_actual_percent": 0.0, "ram_actual_mb": 0.0, "ollama_ram_mb": 0.0,
    "ollama_cpu_percent": 0.0, "vram_mb": -1.0,
}


def _det(nombre: str, caja: List[int], interactivo: bool = True, fuente: str = SOURCE_UIA,
         raw: Optional[Dict[str, Any]] = None) -> DetectedCandidate:
    centro = [(caja[0] + caja[2]) // 2, (caja[1] + caja[3]) // 2]
    return DetectedCandidate(
        source=fuente,
        element=UIElementData(name=nombre, type="button", bbox=list(caja), center=centro,
                              interactive=interactivo, confidence=0.9),
        confidence=0.9, bbox=list(caja), center=centro, screen=0, raw=dict(raw or {}),
    )


class TestLogicaMetricasOffscreen(unittest.TestCase):
    """Valida la logica de precision/recall/F1/IoU con datos sinteticos (sin GUI real)."""

    def test_referencia_xywh_logica_a_caja_fisica(self):
        """[x, y, ancho, alto] logicos x escala DPI -> [x1, y1, x2, y2] fisicos."""
        ref = _referencia_en_pixeles(
            [{"id": "btn_aceptar", "geometry": [20, 20, 100, 32]}, {"id": "menu", "geometry": None}], 2.25)
        self.assertEqual(ref[0]["bbox"], [45, 45, 270, 117])
        self.assertEqual(ref[0]["geometry"], [20, 20, 100, 32])
        self.assertIsNone(ref[1]["bbox"])
        self.assertEqual(_referencia_en_pixeles([{"id": "a", "geometry": [10, 5, 30, 20]}], 1.0)[0]["bbox"],
                         [10, 5, 40, 25])

    def test_emparejamiento_uno_a_uno_y_metricas(self):
        ref = _referencia_en_pixeles([
            {"id": "btn_a", "geometry": [0, 0, 100, 50]},
            {"id": "btn_b", "geometry": [200, 0, 100, 50]},
        ], 1.0)
        det_ok = _det("btn_a", [10, 5, 90, 45])
        det_fp = _det("fantasma", [900, 900, 950, 930])
        pares, det_no, ref_no = _emparejar([det_ok, det_fp], ref, IOU_EMPAREJAMIENTO)
        self.assertEqual(len(pares), 1)
        self.assertEqual(len(det_no), 1)
        self.assertEqual(len(ref_no), 1)

        metrica = _calcular_metrica(
            "uia", [det_ok, det_fp], ref, IOU_EMPAREJAMIENTO, 1.0, _RECURSOS_VACIOS, [],
            tamano_cliente=(1000, 1000),
        )
        self.assertEqual(metrica.tp, 1)
        self.assertEqual(metrica.fp, 1)
        self.assertEqual(metrica.fn, 1)
        self.assertAlmostEqual(metrica.precision, 0.5)
        self.assertAlmostEqual(metrica.recall, 0.5)
        self.assertAlmostEqual(metrica.f1, 0.5)
        self.assertAlmostEqual(metrica.iou_medio, (80 * 40) / (100 * 50))
        self.assertEqual(metrica.falsos_accionables, ["fantasma"])

    def test_cajas_exactas_casan_con_la_referencia_convertida(self):
        """Cajas UIA exactas a escala 2.25: IoU 1, error 0 y click correcto (el informe
        anterior daba IoU 0 y ~626 px de error al tratar [x, y, ancho, alto] como esquinas
        y omitir la escala)."""
        controles = construir_truth_ground().a_dict()["controles"]
        ref = _referencia_en_pixeles(controles, 2.25)
        detectados = [_det(r["id"], r["bbox"]) for r in ref]
        metrica = _calcular_metrica(
            "uia", detectados, ref, IOU_EMPAREJAMIENTO, 0.1, _RECURSOS_VACIOS, [],
            tamano_cliente=(3840, 2001),
        )
        self.assertEqual(metrica.tp, len(controles))
        self.assertEqual((metrica.fp, metrica.fn), (0, 0))
        self.assertAlmostEqual(metrica.iou_medio, 1.0)
        self.assertAlmostEqual(metrica.error_centro_medio_px, 0.0)
        self.assertAlmostEqual(metrica.click_correcto, 1.0)
        # Sensibilidad: la referencia sin escalar no casa con las cajas fisicas.
        sin_escala = _calcular_metrica(
            "uia", detectados, _referencia_en_pixeles(controles, 1.0), IOU_EMPAREJAMIENTO, 0.1,
            _RECURSOS_VACIOS, [], tamano_cliente=(3840, 2001),
        )
        self.assertLess(sin_escala.iou_medio, CRITERIO_IOU_MEDIO_MIN)
        self.assertGreater(sin_escala.error_centro_medio_px, CRITERIO_ERROR_CENTRO_MAX_PX)

    def test_ambito_subelementos_y_contenedores(self):
        ref = _referencia_en_pixeles([
            {"id": "lst_items", "geometry": [20, 300, 200, 120]},
            {"id": "btn_ok", "geometry": [20, 20, 100, 30]},
        ], 1.0)
        detectados = [
            _det("lst_items", [20, 300, 220, 420]),          # emparejado por nombre
            _det("Item 1", [22, 302, 218, 330]),             # fila dentro de la lista
            _det("Cerrar", [950, -30, 990, -2]),            # barra de titulo (fuera del cliente)
            _det("ventana", [-8, -31, 1008, 808]),          # contenedor de la ventana
            _det("oculto", [600, 600, 650, 640], raw={"is_offscreen": True}),
            _det("inventado", [600, 100, 700, 140]),        # falso positivo
        ]
        metrica = _calcular_metrica(
            "uia", detectados, ref, IOU_EMPAREJAMIENTO, 0.1, _RECURSOS_VACIOS, [],
            tamano_cliente=(1000, 800),
        )
        self.assertEqual(metrica.tp, 1)
        self.assertEqual(metrica.subelementos, 1)
        self.assertEqual(metrica.fuera_de_ambito, 3)
        self.assertEqual(metrica.fp, 1)
        self.assertEqual(metrica.fn, 1)
        self.assertEqual(metrica.falsos_accionables, ["inventado"])

    def test_control_sin_accesibilidad_marcado_accionable_es_falso(self):
        ref = _referencia_en_pixeles([{"id": "canvas_mano", "geometry": [900, 20, 200, 200]}], 1.0)
        dentro = _det("dibujo", [950, 60, 1050, 160], fuente=SOURCE_QWEN3VL)
        metrica = _calcular_metrica(
            "qwen", [dentro], ref, IOU_EMPAREJAMIENTO, 1.0, _RECURSOS_VACIOS, ["canvas_mano"],
            tamano_cliente=(1200, 800),
        )
        self.assertEqual(metrica.subelementos, 1)
        self.assertEqual(metrica.falsos_accionables, ["canvas_mano"])
        no_accionable = _calcular_metrica(
            "qwen", [_det("dibujo", [950, 60, 1050, 160], interactivo=False)], ref, IOU_EMPAREJAMIENTO,
            1.0, _RECURSOS_VACIOS, ["canvas_mano"], tamano_cliente=(1200, 800),
        )
        self.assertEqual(no_accionable.falsos_accionables, [])

    def test_emparejamiento_por_iou_no_deja_referencias_sin_par_evitables(self):
        ref = _referencia_en_pixeles([
            {"id": "a", "geometry": [0, 0, 100, 100]},
            {"id": "b", "geometry": [20, 0, 100, 100]},
        ], 1.0)
        # det0 es la mejor deteccion para "a" y para "b" (IoU 0.82 con ambas);
        # det1 solo solapa lo suficiente con "b" (0.74). Una asignacion por
        # referencia dejaria "b" sin pareja; la voraz global empareja las dos.
        det0 = _det("x", [10, 0, 110, 100], fuente=SOURCE_QWEN3VL)
        det1 = _det("y", [35, 0, 135, 100], fuente=SOURCE_QWEN3VL)
        pares, det_no, ref_no = _emparejar([det0, det1], ref, IOU_EMPAREJAMIENTO)
        asignados = {referencia_j: det_i for det_i, referencia_j, _ in pares}
        self.assertEqual(asignados, {0: 0, 1: 1})
        self.assertEqual((det_no, ref_no), ([], []))

    def test_criterios_sin_pares_no_se_cumplen(self):
        r = ResultadoMetrica(fuente="qwen3vl_vision", latencia_s=1.0)
        criterios = _evaluar_criterios(r)
        self.assertFalse(criterios["iou_medio"])
        self.assertFalse(criterios["error_centro"])
        self.assertFalse(criterios["click_correcto"])
        self.assertFalse(criterios["recall"])
        self.assertTrue(criterios["latencia"])

    def test_centro_en_zona_util(self):
        self.assertTrue(_centro_en_zona_util([45, 45, 270, 117], [45, 45, 270, 117]))
        self.assertTrue(_centro_en_zona_util([100, 60, 200, 100], [45, 45, 270, 117]))
        self.assertFalse(_centro_en_zona_util([300, 45, 400, 117], [45, 45, 270, 117]))
        self.assertFalse(_centro_en_zona_util(None, [45, 45, 270, 117]))


class TestHarnessCalibracionPrecisionReal(unittest.TestCase):
    """Ejecuta el pipeline real de produccion sobre la fixture y mide precision."""

    adapter = None
    proc = None
    hwnd = None
    monitor_id = None
    cliente_offset = (0, 0)
    cliente_rect = None
    tamano_cliente = (0, 0)
    escala_ventana = None
    escala_monitor = None

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este harness GUI real")
        if _gui_lock_activo():
            raise unittest.SkipTest("Otra prueba GUI esta ejecutandose. Esperar a que termine.")
        _adquirir_gui_lock()
        cls.adapter = get_desktop_platform()
        cls.proc = None
        cls.hwnd = None
        cls.monitor_id = None
        cls.cliente_offset = (0, 0)
        cls.cliente_rect = None
        cls.tamano_cliente = (0, 0)
        cls.escala_ventana = None
        cls.escala_monitor = None
        try:
            cls._lanzar_fixture_propietaria()
        except Exception:
            try:
                cls._cerrar_fixture_propietaria()
            except Exception:
                pass
            _liberar_gui_lock()
            raise

    @classmethod
    def _lanzar_fixture_propietaria(cls):
        """Lanza la fixture y se queda con la ventana que esta prueba creo."""
        from pywinauto import Desktop  # solo Windows

        cls.proc = subprocess.Popen([sys.executable, FIXTURE_RUN])
        deadline = time.time() + 25
        cls.hwnd = None
        escritorio = Desktop(backend="uia")
        while time.time() < deadline:
            try:
                cand = escritorio.window(title=TITULO_FIXTURE)
                if cand.exists() and cand.handle is not None:
                    cls.hwnd = int(cand.handle)
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if cls.hwnd is None:
            raise RuntimeError("No se detecto una ventana propia de la fixture tras lanzarla")

        # Monitor destino: el no principal situado mas a la derecha (enumeracion real).
        disp = cls.adapter.enumerate_displays()
        assert disp.ok is True, "No se pudieron enumerar monitores: %s" % disp.error
        pantallas = disp.value
        no_principales = [p for p in pantallas if not p.is_primary]
        objetivo = max(no_principales, key=lambda p: p.bounds.left) if no_principales else pantallas[0]
        cls.monitor_id = objetivo.display_id

        mv = cls.adapter.move_window_to_display(cls.hwnd, cls.monitor_id)
        assert mv.ok is True, "No se pudo mover la fixture al monitor de pruebas: %s" % mv.error
        mx = cls.adapter.maximize_window(cls.hwnd)
        assert mx.ok is True, "No se pudo maximizar la fixture: %s" % mx.error
        ac = cls.adapter.activate_window(cls.hwnd)
        assert ac.ok is True, "No se pudo activar la fixture: %s" % ac.error

        # La ventana se registra para el cierre en cuanto existe, aunque falle
        # una comprobacion posterior.
        atexit.register(cls._cerrar_fixture_propietaria)

        # Esperar (sin sleep fijo) a que la ventana este en el monitor
        # objetivo con su escala DPI y su area cliente estables: Qt reajusta
        # la geometria al recibir WM_DPICHANGED tras el cambio de monitor.
        cls.escala_monitor = float(objetivo.scale_factor)
        win = None
        rect_anterior = None
        deadline = time.time() + 10
        while time.time() < deadline:
            win = cls.adapter.get_window(cls.hwnd)
            rect = _area_cliente_pantalla(cls.hwnd)
            estable = (
                win.ok is True
                and win.value.display_id == cls.monitor_id
                and win.value.scale_factor is not None
                and abs(float(win.value.scale_factor) - cls.escala_monitor) < 0.01
                and rect is not None
                and rect == rect_anterior
            )
            if estable:
                break
            rect_anterior = rect
            time.sleep(0.25)
        assert win is not None and win.ok is True, "No se pudo leer la ventana de la fixture"
        assert win.value.display_id == cls.monitor_id, "La fixture no quedo en el monitor objetivo"
        assert win.value.scale_factor is not None, "El adaptador no devolvio la escala DPI de la ventana"
        cls.escala_ventana = float(win.value.scale_factor)
        assert abs(cls.escala_ventana - cls.escala_monitor) < 0.01, (
            "La escala DPI de la ventana (%.4f) no coincide con la del monitor (%.4f): la referencia "
            "logica de Qt no se puede convertir a pixeles fisicos" % (cls.escala_ventana, cls.escala_monitor)
        )

        # Offset del area cliente en pantalla (para convertir coordenadas).
        cls.cliente_offset = _cliente_offset_pantalla(cls.hwnd)
        cls.cliente_rect = _area_cliente_pantalla(cls.hwnd)
        if cls.cliente_rect is not None:
            cl, ct, cr, cb = cls.cliente_rect
            cls.tamano_cliente = (cr - cl, cb - ct)

    def test_harness_precision_accesibilidad_vision_fusion(self):
        """Pipeline real: UIA + Qwen3-VL + fusion, metrica contra verdad-terreno."""
        self.assertIsNotNone(self.hwnd, "La fixture no se lanzo")
        self.assertIsNotNone(self.escala_ventana, "Escala DPI de la fixture desconocida")
        self.assertIsNotNone(self.cliente_rect, "Area cliente de la fixture no disponible")
        referencia = _referencia_en_pixeles(
            construir_truth_ground().a_dict()["controles"], self.escala_ventana
        )
        self.assertGreaterEqual(len(referencia), 1, "La verdad-terreno no tiene controles")
        tamano_cliente = tuple(self.tamano_cliente)

        recursos_iniciales = _recursos_proceso()
        resultados: List[ResultadoMetrica] = []

        # ---------------- 1. Accesibilidad (UI Automation) ----------------
        t0 = time.perf_counter()
        det_uia: List[DetectedCandidate] = []
        error_uia = None
        try:
            adapter = UIAutomationAdapter(timeout=8.0)
            tree: UIAutomationTree = adapter.enumerate_window(self.hwnd)
            if tree.error is not None:
                error_uia = tree.error
            else:
                for elem in tree.elements:
                    # Convertir coordenadas de pantalla a area cliente (restar offset).
                    det = _elemento_a_candidato_uia(elem, self.hwnd, tree.process_id)
                    if det.bbox is not None and len(det.bbox) == 4:
                        cl, ct = self.cliente_offset
                        det.bbox = [det.bbox[0] - cl, det.bbox[1] - ct, det.bbox[2] - cl, det.bbox[3] - ct]
                        det.center = [det.bbox[0] + (det.bbox[2] - det.bbox[0]) // 2,
                                      det.bbox[1] + (det.bbox[3] - det.bbox[1]) // 2]
                        det.element.bbox = list(det.bbox)
                        det.element.center = list(det.center)
                    det_uia.append(det)
        except Exception as exc:
            error_uia = str(exc)
        latencia_uia = time.perf_counter() - t0
        res_uia = _calcular_metrica(
            "uia_accesibilidad", det_uia, referencia, IOU_EMPAREJAMIENTO, latencia_uia,
            _recursos_proceso(), CONTROLES_SIN_ACCESIBILIDAD, tamano_cliente=tamano_cliente,
        )
        res_uia.error = error_uia
        resultados.append(res_uia)

        # ---------------- 2. Vision (Qwen3-VL sobre captura real) ----------------
        det_vision: List[DetectedCandidate] = []
        error_vision = None
        latencia_vision = 0.0
        t0_vision = 0.0
        respuesta = None
        tamano_captura = None
        ruta_captura = None
        servidor_ollama = None
        try:
            # Servidor Ollama de la sesion: se arranca si no responde y se
            # cierra al terminar la sesion (nunca uno que ya estuviera en marcha).
            servidor_ollama = servidor_ollama_de_sesion()
            cl, ct, cr, cb = self.cliente_rect
            capturador = ScreenCapture()
            ruta_captura = capturador.capture_region(cl, ct, cr - cl, cb - ct)
            if ruta_captura is None:
                raise RuntimeError("ScreenCapture.capture_region devolvio None")
            vision = Vision(model=DEFAULT_VISION_MODEL)
            tamano_captura = Vision._image_size(ruta_captura)
            t0_vision = time.perf_counter()
            respuesta = vision.detect_ui_elements(ruta_captura, application="fixture", refine_with_opencv=False)
            latencia_vision = time.perf_counter() - t0_vision
            # detect_ui_elements nunca lanza: los fallos llegan en respuesta.error.
            error_vision = respuesta.error
            for elem in respuesta.elements:
                det = _elemento_a_candidato_vision(elem, self.hwnd, 0)
                det_vision.append(det)
        except Exception as exc:
            error_vision = str(exc)
            if t0_vision > 0:
                latencia_vision = time.perf_counter() - t0_vision
        finally:
            if ruta_captura and os.path.exists(str(ruta_captura)):
                try:
                    os.remove(str(ruta_captura))
                except OSError:
                    pass
        res_vision = _calcular_metrica(
            "qwen3vl_vision", det_vision, referencia, IOU_EMPAREJAMIENTO, latencia_vision,
            _recursos_proceso(), CONTROLES_SIN_ACCESIBILIDAD, tamano_cliente=tamano_cliente,
        )
        res_vision.error = error_vision
        res_vision.detalle = {
            "modelo": DEFAULT_VISION_MODEL,
            "servidor_ollama_arrancado_por_la_sesion": (
                servidor_ollama.started_by_us if servidor_ollama is not None else None
            ),
            "tamano_captura": list(tamano_captura) if tamano_captura else None,
            "tamano_imagen_modelo": (respuesta.model_image_size if respuesta is not None else None),
            "cajas_descartadas": (respuesta.discarded if respuesta is not None else None),
            "salida_cortada": (respuesta.truncated if respuesta is not None else None),
            "ollama": dict(vision.last_chat_info) if respuesta is not None else {},
            "detecciones": [
                {"name": d.element.name, "type": d.element.type, "bbox": d.bbox,
                 "interactive": bool(d.element.interactive)}
                for d in det_vision
            ],
        }
        resultados.append(res_vision)

        # ---------------- 3. Fusion (UIA + Vision) ----------------
        det_fusion_entradas = list(det_uia) + list(det_vision)
        error_fusion = None
        latencia_fusion = 0.0
        t0_fusion = 0.0
        det_fusion: List[DetectedCandidate] = []
        try:
            t0_fusion = time.perf_counter()
            fusion = VisualUIDetectorFusion()
            resultado_fusion = fusion.fuse(
                det_fusion_entradas,
                window_handle=self.hwnd,
                process_id=0,
                screen=0,
            )
            latencia_fusion = time.perf_counter() - t0_fusion
            for fc in resultado_fusion.candidates:
                det = DetectedCandidate(
                    source="fusion",
                    element=fc.sources[0].element if fc.sources else UIElementData(name=fc.name, type=fc.type),
                    confidence=fc.merged_confidence,
                    bbox=list(fc.bbox) if fc.bbox else None,
                    center=list(fc.center) if fc.center else None,
                    screen=fc.screen,
                    window_handle=fc.window_handle,
                    process_id=fc.process_id,
                    raw={"fusion": True, "agreement": fc.agreement, "disagreements": list(fc.disagreements)},
                )
                det_fusion.append(det)
        except Exception as exc:
            error_fusion = str(exc)
            if t0_fusion > 0:
                latencia_fusion = time.perf_counter() - t0_fusion
        res_fusion = _calcular_metrica(
            "fusion_uia_vision", det_fusion, referencia, IOU_EMPAREJAMIENTO, latencia_fusion,
            _recursos_proceso(), CONTROLES_SIN_ACCESIBILIDAD, tamano_cliente=tamano_cliente,
        )
        res_fusion.error = error_fusion
        resultados.append(res_fusion)

        for r in resultados:
            r.criterios_cumplidos = _evaluar_criterios(r)

        # ---------------- Informe y aserciones contra criterios fijados ----------------
        informe = {
            "unidad": "3.8.6.10.3",
            "fixture": TITULO_FIXTURE,
            "monitor_id": self.monitor_id,
            "tamano_cliente": list(self.tamano_cliente),
            "escala_ventana": self.escala_ventana,
            "escala_monitor": self.escala_monitor,
            "espacio_coordenadas": "pixeles fisicos del area cliente",
            "total_controles_referencia": len(referencia),
            "controles_referencia": referencia,
            "criterios": {
                "iou_medio_min": CRITERIO_IOU_MEDIO_MIN,
                "error_centro_max_px": CRITERIO_ERROR_CENTRO_MAX_PX,
                "precision_min": CRITERIO_PRECISION_MIN,
                "recall_min": CRITERIO_RECALL_MIN,
                "f1_min": CRITERIO_F1_MIN,
                "click_correcto_min": CRITERIO_CLICK_CORRECTO_MIN,
                "falsos_accionables_max": CRITERIO_FALSOS_ACCIONABLES_MAX,
                "latencia_max_s": CRITERIO_LATENCIA_MAX_S,
                "iou_emparejamiento": IOU_EMPAREJAMIENTO,
            },
            "resultados_por_fuente": [r.a_dict() for r in resultados],
        }
        informe_path = os.path.join(os.path.dirname(__file__), "informe_ui_calibracion_accuracy.json")
        try:
            with open(informe_path, "w", encoding="utf-8") as f:
                json.dump(informe, f, ensure_ascii=True, indent=2)
        except Exception:
            pass

        # Imprimir resumen para visibilidad en consola.
        print("\n=== HARNESS PRECISION CALIBRACION UI (escala %.2f, cliente %sx%s) ===" % (
            self.escala_ventana, self.tamano_cliente[0], self.tamano_cliente[1]))
        for r in resultados:
            print("[%s] tp=%d fp=%d fn=%d sub=%d fuera=%d precision=%.2f recall=%.2f f1=%.2f iou=%.2f err_centro=%.1fpx click=%.2f falsos=%s lat=%.2fs cpu=%s ram=%.1fMB ollama_ram=%.1fMB vram=%s err=%s" % (
                r.fuente, r.tp, r.fp, r.fn, r.subelementos, r.fuera_de_ambito, r.precision, r.recall,
                r.f1, r.iou_medio, r.error_centro_medio_px, r.click_correcto, r.falsos_accionables,
                r.latencia_s, r.cpu_actual_percent, r.ram_actual_mb, r.ollama_ram_mb, r.vram_mb, r.error,
            ))
            print("    criterios cumplidos: %s" % r.criterios_cumplidos)
        print("    vision: %s" % {k: v for k, v in res_vision.detalle.items() if k != "detecciones"})

        self.assertTrue(os.path.exists(informe_path), "El informe de precision no se genero")

        # Ninguna fuente puede fallar en silencio.
        for r in resultados:
            self.assertIsNone(r.error, "%s produjo un error: %s" % (r.fuente, r.error))

        # UIA da la geometria exacta de Qt: si no casa con la referencia, la
        # conversion de coordenadas de la medida es incorrecta.
        self.assertGreaterEqual(
            res_uia.recall, CRITERIO_RECALL_MIN,
            "UIA no detecta suficientes controles de referencia (recall=%.2f)" % res_uia.recall,
        )
        self.assertGreaterEqual(
            res_uia.iou_medio, CRITERIO_IOU_MEDIO_MIN,
            "IoU medio UIA %.2f: la referencia convertida no casa con la geometria real" % res_uia.iou_medio,
        )
        self.assertLessEqual(
            res_uia.error_centro_medio_px, CRITERIO_ERROR_CENTRO_MAX_PX,
            "Error de centro UIA %.1f px" % res_uia.error_centro_medio_px,
        )
        self.assertGreaterEqual(
            res_uia.click_correcto, CRITERIO_CLICK_CORRECTO_MIN,
            "Click correcto UIA %.2f" % res_uia.click_correcto,
        )

        # Qwen3-VL detecta controles con coordenadas en pixeles de la captura.
        self.assertGreaterEqual(res_vision.total_detectados, 1, "Qwen3-VL no detecto ningun elemento")
        ancho_captura, alto_captura = tamano_captura
        for d in det_vision:
            x1, y1, x2, y2 = d.bbox
            self.assertTrue(
                0 <= x1 < x2 <= ancho_captura and 0 <= y1 < y2 <= alto_captura,
                "Caja de vision fuera de la captura %sx%s: %s %s" % (ancho_captura, alto_captura, d.element.name, d.bbox),
            )
        tam_modelo = respuesta.model_image_size or list(tamano_captura)
        self.assertLessEqual(
            tam_modelo[0] * tam_modelo[1], MODEL_IMAGE_MAX_PIXELS,
            "La captura %s no se redujo antes de enviarla al modelo (%s)" % (tamano_captura, tam_modelo),
        )
        ref_por_id = {r["id"]: r for r in referencia}
        for control_id in BOTONES_CON_TEXTO:
            ref_bbox = ref_por_id[control_id]["bbox"]
            self.assertTrue(
                any(_centro_en_zona_util(d.bbox, ref_bbox) for d in det_vision),
                "Qwen3-VL no localiza %s %s; detecciones: %s" % (
                    control_id, ref_bbox, [(d.element.name, d.bbox) for d in det_vision]),
            )

        for r in resultados:
            self.assertLessEqual(
                r.latencia_s, CRITERIO_LATENCIA_MAX_S,
                "Latencia excede el limite (%s): %.2f s > %.2f s" % (r.fuente, r.latencia_s, CRITERIO_LATENCIA_MAX_S),
            )

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_fixture_propietaria()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.monitor_id = None
            cls.adapter = None
            _liberar_gui_lock()

    @classmethod
    def _cerrar_fixture_propietaria(cls):
        if cls.hwnd is not None and cls.adapter is not None:
            from pywinauto import Desktop  # solo Windows

            try:
                cls.adapter.close_window(cls.hwnd)
                deadline = time.time() + 10
                while time.time() < deadline:
                    escritorio = Desktop(backend="uia")
                    try:
                        aun_existe = escritorio.window(handle=cls.hwnd).exists()
                    except Exception:
                        aun_existe = False
                    if not aun_existe:
                        break
                    time.sleep(0.25)
            except Exception:
                pass
            cls.hwnd = None
        if cls.proc is not None and cls.proc.poll() is None:
            try:
                cls.proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
