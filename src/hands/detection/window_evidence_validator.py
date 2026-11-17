"""
Validador de pertenencia de evidencia de deteccion a una ventana objetivo.

Valida que una captura de pantalla, un arbol de UI Automation y unos
candidatos de deteccion fusionada pertenezcan a la ventana identificada
por HWND/PID, y rechaza evidencia de escritorio entero cuando la ventana
no puede separarse con seguridad.

Este modulo no captura pantalla, no enumera el escritorio y no ejecuta
acciones sobre controles. Solo valida identidad (HWND/PID) y geometria
(contenimiento en el rectangulo de la ventana) de evidencia ya obtenida.
Es una puerta de seguridad previa a la calibracion y la interaccion.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.hands.detection.ui_automation_adapter import UIAutomationElement, UIAutomationTree
from src.eyes.detection.visual_ui_detector_fusion import DetectedCandidate, FusedCandidate
from src.core.log import get_logger
from src.desktop.screen_manager import MonitorInfo, ScreenManager

logger = get_logger(__name__)

user32 = ctypes.windll.user32

Rect = Tuple[int, int, int, int]

# Espacios de coordenadas reconocidos por la puerta de calidad de geometria.
# Cualquier espacio fuera de este conjunto se considera una transformacion
# desconocida y las cajas se rechazan.
RECOGNIZED_COORDINATE_SPACES = frozenset({
    "absolute_desktop",
    "window_relative",
    "monitor_relative",
    "image_pixels",
    "normalized_0_1000",
})

# Umbral de solapamiento (IoU) por encima del cual dos candidatos de identidad
# distinta se consideran solapados de forma ambigua. Umbral de partida;
# la unidad de umbrales (3.8.6.4.3) lo ajusta a partir de resultados medidos.
IOU_SOLAPAMIENTO_AMBIGUO = 0.30


def _iou_rect(a: Optional[Rect], b: Optional[Rect]) -> float:
    """Interseccion sobre union de dos rectangulos (left, top, right, bottom)."""
    if not a or not b:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter_w = max(0, ix2 - ix1)
    inter_h = max(0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


@dataclass
class WindowEvidenceValidation:
    """Resultado de validar que una evidencia pertenece a una ventana objetivo.

    valid: True si todos los controles de identidad y geometria pasaron.
    accepted: sinonimo de valid, mantenido por claridad en puertas de seguridad.
    reason: motivo legible del resultado.
    checks: resultado de cada comprobacion individual.
    rejected_evidence: fuentes de evidencia rechazadas.
    details: informacion adicional para depuracion.
    """

    valid: bool
    accepted: bool
    reason: str
    checks: Dict[str, bool] = field(default_factory=dict)
    rejected_evidence: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": bool(self.valid),
            "accepted": bool(self.accepted),
            "reason": self.reason,
            "checks": dict(self.checks),
            "rejected_evidence": list(self.rejected_evidence),
            "details": dict(self.details),
        }


def _as_rect(value: Any) -> Optional[Rect]:
    """Normaliza un valor a rectangulo (left, top, right, bottom) o None."""
    if value is None:
        return None
    try:
        left, top, right, bottom = [int(v) for v in value]
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _contains_rect(inner: Optional[Rect], outer: Optional[Rect]) -> bool:
    """Devuelve True si inner queda contenido en outer (bordes incluidos)."""
    if not inner or not outer:
        return False
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    return ix1 >= ox1 and iy1 >= oy1 and ix2 <= ox2 and iy2 <= oy2


def _rect_area(rect: Optional[Rect]) -> int:
    if not rect:
        return 0
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


class WindowEvidenceValidator:
    """Valida que evidencia de deteccion pertenezca a una ventana objetivo.

    Argumentos:
        target_hwnd: HWND de la ventana objetivo ya identificada.
        target_pid: PID del proceso de la ventana objetivo (opcional).
        screen_manager: gestor de monitores (se crea si no se proporciona).
    """

    def __init__(
        self,
        target_hwnd: int,
        target_pid: Optional[int] = None,
        screen_manager: Optional[ScreenManager] = None,
    ) -> None:
        self.target_hwnd = int(target_hwnd)
        self.target_pid = int(target_pid) if target_pid is not None else None
        self._screen_manager = screen_manager or ScreenManager()
        self._window_rect_cache: Optional[Rect] = None

    # ------------------------------------------------------------------
    # Geometria de la ventana objetivo y del escritorio virtual
    # ------------------------------------------------------------------

    def _window_rect(self) -> Optional[Rect]:
        """Rectangulo de pantalla de la ventana objetivo (GetWindowRect)."""
        if self._window_rect_cache is not None:
            return self._window_rect_cache
        hwnd = self.target_hwnd
        try:
            if not bool(user32.IsWindow(ctypes.c_void_p(hwnd))):
                self._window_rect_cache = None
                return None
        except Exception:
            self._window_rect_cache = None
            return None
        rect = wintypes.RECT()
        try:
            ok = bool(
                user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
            )
        except Exception:
            ok = False
        if not ok:
            self._window_rect_cache = None
            return None
        result: Rect = (
            int(rect.left),
            int(rect.top),
            int(rect.right),
            int(rect.bottom),
        )
        self._window_rect_cache = result
        return result

    def _desktop_rect(self) -> Optional[Rect]:
        """Rectangulo del escritorio virtual (union de todos los monitores)."""
        monitors = list(getattr(self._screen_manager, "monitors", []) or [])
        if not monitors:
            return None
        left = min(int(m.left) for m in monitors)
        top = min(int(m.top) for m in monitors)
        right = max(int(m.right) for m in monitors)
        bottom = max(int(m.bottom) for m in monitors)
        return (left, top, right, bottom)

    def _monitor_containing_point(
        self, x: int, y: int
    ) -> Optional[MonitorInfo]:
        for m in list(getattr(self._screen_manager, "monitors", []) or []):
            try:
                if m.contains_point(int(x), int(y)):
                    return m
            except Exception:
                continue
        return None

    def _target_screen(self) -> Optional[int]:
        """Indice de pantalla del monitor que contiene la ventana objetivo."""
        rect = self._window_rect()
        if not rect:
            return None
        monitors = list(getattr(self._screen_manager, "monitors", []) or [])
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2
        for idx, m in enumerate(monitors):
            try:
                if m.contains_point(cx, cy):
                    return idx
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Validacion de arbol de UI Automation
    # ------------------------------------------------------------------

    def validate_ui_automation_tree(
        self, tree: UIAutomationTree
    ) -> WindowEvidenceValidation:
        """Valida que un arbol UIA pertenezca a la ventana objetivo (HWND/PID).

        Comprueba: ventana objetivo accesible, arbol presente, window_handle
        igual al HWND objetivo, handle de la raiz igual al HWND, PID del
        arbol igual al PID objetivo (si se proporciona), ausencia de elementos
        de proceso ajeno, ausencia de geometria de escritorio entero y error
        de enumeracion. Un arbol truncado por limites no invalida por si solo.
        """
        checks: Dict[str, bool] = {}
        rejected: List[str] = []
        details: Dict[str, Any] = {}
        reason_parts: List[str] = []

        window_rect = self._window_rect()
        checks["window_exists"] = window_rect is not None
        if window_rect is None:
            return WindowEvidenceValidation(
                False,
                False,
                "ventana objetivo no existe o no es accesible (HWND=%d)"
                % self.target_hwnd,
                checks,
                rejected,
                details,
            )

        details["window_rect"] = list(window_rect)
        details["target_hwnd"] = self.target_hwnd
        details["target_pid"] = self.target_pid

        if tree is None:
            checks["tree_present"] = False
            return WindowEvidenceValidation(
                False,
                False,
                "arbol de UI Automation ausente",
                checks,
                rejected,
                details,
            )
        checks["tree_present"] = True

        details["tree_window_handle"] = int(tree.window_handle or 0)
        details["tree_process_id"] = int(tree.process_id or 0)
        details["tree_error"] = tree.error
        details["tree_truncated"] = bool(tree.truncated)
        details["tree_element_count"] = int(tree.element_count or 0)
        details["tree_source"] = tree.source

        # Identidad de ventana: window_handle del arbol y handle de la raiz.
        checks["window_identity"] = bool(
            int(tree.window_handle or 0) == self.target_hwnd
        )
        if not checks["window_identity"]:
            reason_parts.append(
                "arbol UIA pertenece a HWND=%s, no al objetivo HWND=%s"
                % (tree.window_handle, self.target_hwnd)
            )
        root = tree.root_element
        checks["root_handle"] = bool(int(root.handle or 0) == self.target_hwnd)
        if not checks["root_handle"]:
            reason_parts.append(
                "elemento raiz no tiene handle de la ventana objetivo"
            )

        # Identidad de proceso (si se proporciona referencia).
        if self.target_pid is not None:
            checks["process_identity"] = bool(
                int(tree.process_id or 0) == int(self.target_pid)
            )
            if not checks["process_identity"]:
                reason_parts.append(
                    "PID del arbol (%s) no coincide con el objetivo (%s)"
                    % (tree.process_id, self.target_pid)
                )
        else:
            checks["process_identity"] = True

        # Error de enumeracion sin elementos es invalido; truncado no.
        checks["no_enumeration_error"] = bool(
            tree.error is None or int(tree.element_count or 0) > 0
        )
        if tree.error and int(tree.element_count or 0) == 0:
            reason_parts.append("arbol UIA sin elementos: %s" % tree.error)

        # Ningun elemento puede pertenecer a un proceso ajeno.
        foreign: List[Dict[str, Any]] = []
        for elem in tree.elements or []:
            pid = int(elem.process_id or 0)
            if pid and self.target_pid is not None and pid != int(self.target_pid):
                foreign.append(
                    {
                        "handle": int(elem.handle or 0),
                        "name": elem.name,
                        "control_type": elem.control_type,
                        "process_id": pid,
                        "bounding_rectangle": list(elem.bounding_rectangle),
                    }
                )
        checks["no_foreign_process"] = len(foreign) == 0
        if foreign:
            reason_parts.append(
                "%d elemento(s) de proceso ajeno a la ventana objetivo"
                % len(foreign)
            )
            rejected.append("arbol_uiA_proceso_extrano")
        details["foreign_process_elements"] = foreign

        # Ningun elemento puede declarar geometria de escritorio entero.
        desktop = self._desktop_rect()
        desktop_leak: List[int] = []
        if desktop:
            for elem in tree.elements or []:
                br = elem.bounding_rectangle
                if br and list(br) == list(desktop):
                    desktop_leak.append(int(elem.handle or 0))
        checks["no_desktop_leak"] = len(desktop_leak) == 0
        if desktop_leak:
            reason_parts.append(
                "elemento con geometria de escritorio entero (posible evidencia de escritorio no separada)"
            )
            rejected.append("arbol_uiA_escritorio_entero")
        details["desktop_leak_handles"] = desktop_leak

        valid = all(checks.values())
        accepted = valid
        reason = (
            "; ".join(reason_parts)
            if reason_parts
            else "evidencia de UI Automation valida para la ventana objetivo"
        )
        return WindowEvidenceValidation(valid, accepted, reason, checks, rejected, details)

    # ------------------------------------------------------------------
    # Validacion de region de captura
    # ------------------------------------------------------------------

    def validate_capture_region(
        self,
        region: Any,
        backend: Optional[str] = None,
        source: Optional[str] = None,
    ) -> WindowEvidenceValidation:
        """Valida que una region de captura pertenezca a la ventana objetivo.

        La region debe estar contenida en el rectangulo de la ventana objetivo
        (o ser igual a el para captura de ventana completa). Rechaza la captura
        de escritorio entero o de monitor completo cuando no puede separarse
        con seguridad la ventana de prueba dentro de ella.
        """
        checks: Dict[str, bool] = {}
        rejected: List[str] = []
        details: Dict[str, Any] = {}
        reason_parts: List[str] = []

        rect = _as_rect(region)
        checks["region_valida"] = rect is not None
        if rect is None:
            return WindowEvidenceValidation(
                False,
                False,
                "region de captura invalida o ausente",
                checks,
                rejected,
                details,
            )

        details["capture_region"] = list(rect)
        details["capture_backend"] = backend
        details["capture_source"] = source

        window_rect = self._window_rect()
        checks["window_exists"] = window_rect is not None
        if window_rect is None:
            return WindowEvidenceValidation(
                False,
                False,
                "ventana objetivo inaccesible para validar la captura",
                checks,
                rejected,
                details,
            )

        details["window_rect"] = list(window_rect)

        contained = _contains_rect(rect, window_rect)
        equal = rect == window_rect
        checks["geometria_dentro_de_ventana"] = bool(contained or equal)
        if not (contained or equal):
            reason_parts.append(
                "region de captura no contenida en el rectangulo de la ventana objetivo"
            )

        # Rechazar evidencia de escritorio entero o monitor completo cuando no
        # es exactamente la ventana objetivo (no puede separarse la ventana).
        desktop = self._desktop_rect()
        is_full_desktop = bool(desktop and list(rect) == list(desktop))
        monitors = list(getattr(self._screen_manager, "monitors", []) or [])
        is_full_monitor = any(
            list(rect) == [int(m.left), int(m.top), int(m.right), int(m.bottom)]
            for m in monitors
        )
        captures_desktop_or_monitor = bool(is_full_desktop or is_full_monitor)
        checks["no_evidencia_escritorio_entero"] = bool(
            not captures_desktop_or_monitor or equal
        )
        if captures_desktop_or_monitor and not equal:
            reason_parts.append(
                "evidencia de escritorio entero o monitor completo no separable de la ventana objetivo"
            )
            rejected.append("captura_escritorio_entero")

        # Pantalla del monitor que contiene la ventana objetivo.
        win_cx = (window_rect[0] + window_rect[2]) // 2
        win_cy = (window_rect[1] + window_rect[3]) // 2
        monitor = self._monitor_containing_point(win_cx, win_cy)
        details["ventana_monitor"] = monitor.name if monitor else None
        details["ventana_monitor_index"] = (
            monitors.index(monitor) if monitor in monitors else None
        )
        checks["ventana_visible_en_monitor"] = monitor is not None

        valid = all(checks.values())
        accepted = valid
        reason = (
            "; ".join(reason_parts)
            if reason_parts
            else "captura valida para la ventana objetivo"
        )
        return WindowEvidenceValidation(valid, accepted, reason, checks, rejected, details)

    # ------------------------------------------------------------------
    # Validacion de candidatos de deteccion
    # ------------------------------------------------------------------

    def _candidate_field(self, cand: Any, name: str) -> Any:
        return getattr(cand, name, None)

    def validate_candidates(
        self,
        candidates: List[Any],
        screen: Optional[int] = None,
    ) -> WindowEvidenceValidation:
        """Valida que candidatos de deteccion pertenezcan a la ventana objetivo.

        Para cada candidato comprueba: window_handle igual al HWND objetivo
        (si lo declara), process_id igual al PID objetivo (si se proporciona
        y lo declara), bbox contenida en el rectangulo de la ventana y pantalla
        coincidente (si se declara y se proporciona referencia). La calidad
        geometrica estricta (caja vacia/degenerada, fuera de imagen, control
        obstruido, solapamiento ambiguo, espacio de coordenadas desconocido)
        se valida de forma dedicada en validate_geometria_candidato
        (unidad 3.8.6.4.2). Un candidato que no declara un campo no falla por
        ese campo; solo se rechazan valores declarados que contradigan la
        ventana objetivo.
        """
        checks: Dict[str, bool] = {}
        rejected: List[str] = []
        details: Dict[str, Any] = {}
        reason_parts: List[str] = []

        window_rect = self._window_rect()
        checks["window_exists"] = window_rect is not None
        if window_rect is None:
            return WindowEvidenceValidation(
                False,
                False,
                "ventana objetivo inaccesible para validar candidatos",
                checks,
                rejected,
                details,
            )

        details["window_rect"] = list(window_rect)
        details["target_hwnd"] = self.target_hwnd
        details["target_pid"] = self.target_pid
        target_screen = screen if screen is not None else self._target_screen()
        if target_screen is not None:
            details["target_screen"] = int(target_screen)

        if not candidates:
            checks["candidatos_presentes"] = True
            details["candidate_count"] = 0
            return WindowEvidenceValidation(
                True,
                True,
                "sin candidatos que validar",
                checks,
                rejected,
                details,
            )
        checks["candidatos_presentes"] = True

        failed: List[Dict[str, Any]] = []
        for idx, cand in enumerate(candidates or []):
            problems: List[str] = []
            cand_handle = self._candidate_field(cand, "window_handle")
            cand_pid = self._candidate_field(cand, "process_id")
            cand_screen = self._candidate_field(cand, "screen")
            cand_bbox = self._candidate_field(cand, "bbox")
            cand_name = self._candidate_field(cand, "name")
            cand_type = self._candidate_field(cand, "type")

            if cand_handle is not None and self.target_hwnd is not None:
                if int(cand_handle) != self.target_hwnd:
                    problems.append(
                        "window_handle %s != objetivo %s"
                        % (cand_handle, self.target_hwnd)
                    )
            if cand_pid is not None and self.target_pid is not None:
                if int(cand_pid) != self.target_pid:
                    problems.append(
                        "process_id %s != objetivo %s"
                        % (cand_pid, self.target_pid)
                    )
            if cand_bbox is not None:
                br = _as_rect(cand_bbox)
                if br is not None and not _contains_rect(br, window_rect):
                    # Una bbox ausente o degenerada es un problema de calidad
                    # de geometria (unidad 3.8.6.4.2), no de pertenencia a la
                    # ventana objetivo, por lo que no se rechaza aqui.
                    problems.append("bbox fuera de la ventana objetivo")
            if cand_screen is not None and target_screen is not None:
                if int(cand_screen) != int(target_screen):
                    problems.append(
                        "screen %s != objetivo %s" % (cand_screen, target_screen)
                    )

            if problems:
                failed.append(
                    {
                        "index": int(idx),
                        "name": str(cand_name or ""),
                        "type": str(cand_type or ""),
                        "problems": problems,
                    }
                )
                rejected.append("candidato_%d" % int(idx))

        checks["todos_candidatos_pertenecen_a_ventana"] = len(failed) == 0
        details["failed_candidates"] = failed
        details["candidate_count"] = int(len(candidates or []))

        valid = all(checks.values())
        accepted = valid
        reason = (
            "; ".join(reason_parts)
            if reason_parts
            else "todos los candidatos pertenecen a la ventana objetivo"
        )
        return WindowEvidenceValidation(valid, accepted, reason, checks, rejected, details)

    # ------------------------------------------------------------------
    # Calidad de geometria de candidatos (unidad 3.8.6.4.2)
    # ------------------------------------------------------------------

    def _misma_identidad_candidato(self, a: Any, b: Any) -> bool:
        """Devuelve True si dos candidatos refieren al mismo elemento logico.

        Se considera misma identidad si comparten window_handle distinto de cero,
        o si comparten canonical_id/nombre normalizado no vacio. Se usa para no
        marcar como ambiguo el solapamiento de un candidato consigo mismo.
        """
        ca = str(
            self._candidate_field(a, "canonical_id")
            or self._candidate_field(a, "name")
            or ""
        ).strip().lower()
        cb = str(
            self._candidate_field(b, "canonical_id")
            or self._candidate_field(b, "name")
            or ""
        ).strip().lower()
        if ca and ca == cb:
            return True
        ha = int(self._candidate_field(a, "window_handle") or 0)
        hb = int(self._candidate_field(b, "window_handle") or 0)
        # Solo mismo control si comparten handle no vacio Y mismo nombre logico.
        if ha and hb and ha == hb and ca and ca == cb:
            return True
        return False

    def validate_geometria_candidato(
        self,
        cand: Any,
        image_rect: Optional[Rect] = None,
        window_rect: Optional[Rect] = None,
        otros_candidatos: Optional[List[Any]] = None,
    ) -> WindowEvidenceValidation:
        """Valida la calidad geometrica de un candidato de deteccion.

        Rechaza cajas vacias, degeneradas, fuera de imagen, parcialmente fuera
        de la ventana objetivo, obstruidas (fuera de pantalla o no visibles),
        solapadas de forma ambigua con otro candidato de identidad distinta o
        con transformacion de coordenadas desconocida.

        Argumentos:
            cand: candidato (FusedCandidate, DetectedCandidate o UIAutomationElement).
            image_rect: rectangulo de la captura/frame (left, top, right, bottom)
                en el mismo espacio de coordenadas que el bbox del candidato.
                Se omite la comprobacion si no se proporciona.
            window_rect: rectangulo de la ventana objetivo. Si no se da, se usa
                el rectangulo de la ventana objetivo del validador.
            otros_candidatos: lista de los demas candidatos para detectar
                solapamiento ambiguo.

        Retorna:
            WindowEvidenceValidation con valid=True solo si la caja supera todas
            las puertas de calidad geometricas.
        """
        checks: Dict[str, bool] = {}
        rejected: List[str] = []
        details: Dict[str, Any] = {}
        reason_parts: List[str] = []

        cand_bbox = self._candidate_field(cand, "bbox")
        br = _as_rect(cand_bbox)
        details["caja"] = list(br) if br else None
        details["caja_original"] = list(cand_bbox) if cand_bbox else None

        # 1. Caja vacia, ausente o degenerada.
        checks["caja_valida"] = br is not None
        if br is None:
            reason_parts.append("caja vacia, ausente o degenerada")
            rejected.append("candidato:caja_degenerada")

        # 2. Espacio de coordenadas desconocido.
        espacio = self._candidate_field(cand, "coordinate_space")
        details["coordinate_space"] = espacio
        if espacio is not None and espacio not in RECOGNIZED_COORDINATE_SPACES:
            checks["espacio_coordenadas_conocido"] = False
            reason_parts.append(
                "transformacion de coordenadas desconocida: %s" % espacio
            )
            rejected.append("candidato:espacio_coordenadas_desconocido")
        else:
            checks["espacio_coordenadas_conocido"] = True

        # Rectangulo de referencia de la ventana objetivo.
        if window_rect is None:
            window_rect = self._window_rect()
        details["window_rect"] = list(window_rect) if window_rect else None

        # 3. Caja dentro de la ventana objetivo (contenimiento geometrico).
        checks["caja_dentro_de_ventana"] = True
        if br is not None and window_rect is not None:
            checks["caja_dentro_de_ventana"] = _contains_rect(br, window_rect)
            if not checks["caja_dentro_de_ventana"]:
                reason_parts.append(
                    "caja parcialmente o totalmente fuera de la ventana objetivo"
                )
                rejected.append("candidato:caja_fuera_ventana")

        # 4. Caja dentro de la imagen/captura (solo si se proporciona referencia).
        checks["caja_dentro_de_imagen"] = True
        if br is not None and image_rect is not None:
            checks["caja_dentro_de_imagen"] = _contains_rect(br, image_rect)
            if not checks["caja_dentro_de_imagen"]:
                reason_parts.append("caja fuera de la imagen o captura")
                rejected.append("candidato:caja_fuera_imagen")

        # 5. Control no obstruido (fuera de pantalla o no visible).
        checks["control_no_obstruido"] = True
        is_offscreen = self._candidate_field(cand, "is_offscreen")
        visible = self._candidate_field(cand, "visible")
        details["is_offscreen"] = is_offscreen
        details["visible"] = visible
        if is_offscreen is not None or visible is not None:
            no_obstruido = bool(
                (is_offscreen is False or is_offscreen is None)
                and (visible is True or visible is None)
            )
            checks["control_no_obstruido"] = no_obstruido
            if not no_obstruido:
                reason_parts.append(
                    "control obstruido, fuera de pantalla o no visible"
                )
                rejected.append("candidato:control_obstruido")

        # 6. No solapamiento ambiguo con otro candidato de identidad distinta.
        checks["no_solapamiento_ambiguo"] = True
        if br is not None:
            for otro in list(otros_candidatos or []):
                if otro is cand:
                    continue
                otro_br = _as_rect(self._candidate_field(otro, "bbox"))
                if otro_br is None:
                    continue
                iou = _iou_rect(br, otro_br)
                if iou > IOU_SOLAPAMIENTO_AMBIGUO and not self._misma_identidad_candidato(
                    cand, otro
                ):
                    checks["no_solapamiento_ambiguo"] = False
                    otro_id = (
                        self._candidate_field(otro, "canonical_id")
                        or self._candidate_field(otro, "name")
                        or "desconocido"
                    )
                    reason_parts.append(
                        "solapamiento ambiguo con candidato %s (IoU=%.2f)"
                        % (otro_id, iou)
                    )
                    rejected.append("candidato:solapamiento_ambiguo")
                    break

        valid = all(checks.values())
        reason = (
            "; ".join(reason_parts)
            if reason_parts
            else "geometria del candidato valida"
        )
        return WindowEvidenceValidation(valid, valid, reason, checks, rejected, details)


    # ------------------------------------------------------------------
    # Validacion combinada
    # ------------------------------------------------------------------

    def validate_all(
        self,
        tree: Optional[UIAutomationTree] = None,
        capture_region: Any = None,
        candidates: Optional[List[Any]] = None,
        screen: Optional[int] = None,
        backend: Optional[str] = None,
        source: Optional[str] = None,
    ) -> WindowEvidenceValidation:
        """Valida conjuntamente arbol UIA, captura y candidatos.

        Devuelve valido solo si toda la evidencia proporcionada pertenece a la
        ventana objetivo. Si no se proporciona ninguna evidencia, devuelve
        invalido (no hay nada que validar).
        """
        results: List[tuple] = []
        if tree is not None:
            results.append(
                ("arbol_uiA", self.validate_ui_automation_tree(tree))
            )
        if capture_region is not None:
            results.append(
                ("captura", self.validate_capture_region(capture_region, backend=backend, source=source))
            )
        if candidates is not None:
            results.append(
                ("candidatos", self.validate_candidates(candidates, screen=screen))
            )

        all_checks: Dict[str, bool] = {}
        all_rejected: List[str] = []
        all_details: Dict[str, Any] = {}
        reason_parts: List[str] = []
        for name, res in results:
            for key, value in res.checks.items():
                all_checks["%s.%s" % (name, key)] = bool(value)
            all_rejected.extend(["%s:%s" % (name, r) for r in res.rejected_evidence])
            all_details[name] = res.details
            if not res.valid:
                reason_parts.append("%s: %s" % (name, res.reason))

        if not results:
            return WindowEvidenceValidation(
                False,
                False,
                "no hay evidencia que validar",
                all_checks,
                all_rejected,
                all_details,
            )

        valid = all(res.valid for _, res in results)
        accepted = valid
        reason = (
            "; ".join(reason_parts)
            if reason_parts
            else "toda la evidencia pertenece a la ventana objetivo"
        )
        return WindowEvidenceValidation(valid, accepted, reason, all_checks, all_rejected, all_details)


def validate_evidence_for_window(
    target_hwnd: int,
    tree: Optional[UIAutomationTree] = None,
    capture_region: Any = None,
    candidates: Optional[List[Any]] = None,
    target_pid: Optional[int] = None,
    screen: Optional[int] = None,
    backend: Optional[str] = None,
    source: Optional[str] = None,
) -> WindowEvidenceValidation:
    """Funcion de conveniencia para validar evidencia de una ventana objetivo.

    Crea un WindowEvidenceValidator y ejecuta validate_all con la evidencia
    proporcionada.
    """
    validator = WindowEvidenceValidator(
        target_hwnd, target_pid=target_pid
    )
    return validator.validate_all(
        tree=tree,
        capture_region=capture_region,
        candidates=candidates,
        screen=screen,
        backend=backend,
        source=source,
    )


__all__ = [
    "WindowEvidenceValidator",
    "WindowEvidenceValidation",
    "validate_evidence_for_window",
    "_as_rect",
    "_contains_rect",
]
