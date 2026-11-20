# -*- coding: ascii -*-
"""
Tests unitarios de ``UICalibrationPipeline.recover_profile``.

``recover_profile`` decide si un perfil de calibracion persistido se recupera
tras reiniciar el gestor. La decision de vigencia es de
``CalibrationValidityService.load_valid_profile`` (huella de ventana/escala,
equipo, SO, monitor); aqui se sustituye SOLO ese servicio y el adaptador de
escritorio por dobles que devuelven decisiones conocidas, para comprobar que
``recover_profile``:

- marca ``recovered`` solo con perfil, ``valid`` y accion ``use``/``recompute``;
- no recupera con ``recalibrate`` ni ``reject`` (aunque llegue un perfil);
- no recupera si el servicio de vigencia falla, e informa el error;
- normaliza la clave de aplicacion y el identificador de ventana;
- resume el perfil y la ventana sin titulo (puede contener datos del usuario);
- tolera que la ventana ya no exista (aviso, sin excepcion).

Multiplataforma: no usa APIs nativas ni toca data/.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

import pytest

from src.hands.calibration.calibration_pipeline import UICalibrationPipeline
from src.hands.calibration.calibration_validity import (
    ACTION_RECALIBRATE,
    ACTION_RECOMPUTE,
    ACTION_REJECT,
    ACTION_USE,
    ProfileValidity,
)


class _ValidezFalsa:
    """Doble de ``CalibrationValidityService`` con una decision fija."""

    def __init__(self, perfil: Any, validez: ProfileValidity, error: Optional[Exception] = None) -> None:
        self.perfil = perfil
        self.validez = validez
        self.error = error
        self.llamadas: List[Tuple[str, int]] = []

    def load_valid_profile(self, app_id: str, window_id: int) -> Tuple[Any, ProfileValidity]:
        self.llamadas.append((app_id, window_id))
        if self.error is not None:
            raise self.error
        return self.perfil, self.validez


class _AdaptadorFalso:
    def __init__(self, ventana: Any = None, error: Optional[Exception] = None) -> None:
        self.ventana = ventana
        self.error = error

    def get_window(self, window_id: int) -> Any:
        if self.error is not None:
            raise self.error
        if self.ventana is None:
            return SimpleNamespace(ok=False, value=None, error="ventana inexistente")
        return SimpleNamespace(ok=True, value=self.ventana, error=None)


def _perfil(profile_id: str = "p1") -> Any:
    return SimpleNamespace(
        profile_id=profile_id,
        topology_fingerprint="topo-1",
        window_fingerprint="win-1",
        display_id="display-2",
        scale_factor=1.5,
        dpi=144,
        status="VALIDADO",
        controls=[object(), object()],
    )


def _ventana() -> Any:
    return SimpleNamespace(
        window_id=77,
        pid=4242,
        app_identity="notepad.exe",
        title="documento privado.txt - Bloc de notas",
        bounds=None,
        client_bounds=None,
        is_maximized=True,
        is_foreground=True,
        display_id="display-2",
        scale_factor=1.5,
        dpi=144,
    )


def _pipeline(validez: _ValidezFalsa, adaptador: Any = None) -> UICalibrationPipeline:
    return UICalibrationPipeline(adapter=adaptador or _AdaptadorFalso(_ventana()), validity_service=validez)


class TestRecuperaSoloConPerfilVigente:
    @pytest.mark.parametrize("accion", [ACTION_USE, ACTION_RECOMPUTE])
    def test_recupera_con_perfil_valido_use_o_recompute(self, accion):
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(True, accion, ["monitor"] if accion == ACTION_RECOMPUTE else []))
        info = _pipeline(servicio).recover_profile("Notepad", 77)
        assert info["recovered"] is True
        assert info["validity"]["action"] == accion
        assert info["profile"]["profile_id"] == "p1"
        assert info["profile"]["topology_fingerprint"] == "topo-1"
        assert info["profile"]["window_fingerprint"] == "win-1"
        assert info["profile"]["display_id"] == "display-2"
        assert info["profile"]["controls"] == 2

    @pytest.mark.parametrize("accion", [ACTION_RECALIBRATE, ACTION_REJECT])
    def test_no_recupera_con_recalibrate_o_reject_aunque_haya_perfil(self, accion):
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(False, accion, ["huella_ventana"]))
        info = _pipeline(servicio).recover_profile("notepad", 77)
        assert info["recovered"] is False
        assert info["validity"]["action"] == accion
        assert info["profile"]["profile_id"] == "p1"

    def test_no_recupera_sin_perfil(self):
        servicio = _ValidezFalsa(None, ProfileValidity(False, ACTION_RECALIBRATE, ["sin_perfil"]))
        info = _pipeline(servicio).recover_profile("notepad", 77)
        assert info["recovered"] is False
        assert "profile" not in info

    def test_no_recupera_si_valid_es_falso_aunque_la_accion_sea_use(self):
        # Control de sensibilidad: la accion sola no basta, hace falta valid.
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(False, ACTION_USE, []))
        info = _pipeline(servicio).recover_profile("notepad", 77)
        assert info["recovered"] is False


class TestErroresYNormalizacion:
    def test_error_del_servicio_de_vigencia_no_recupera_e_informa(self):
        servicio = _ValidezFalsa(None, ProfileValidity(False, ACTION_REJECT), error=RuntimeError("sqlite bloqueada"))
        info = _pipeline(servicio).recover_profile("notepad", 77)
        assert info["recovered"] is False
        assert "sqlite bloqueada" in info["error"]
        assert "validity" not in info

    def test_normaliza_clave_de_aplicacion_y_ventana(self):
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(True, ACTION_USE))
        info = _pipeline(servicio).recover_profile("  Bloc de Notas ", "77")
        assert servicio.llamadas == [("bloc_de_notas", 77)]
        assert info["app_id"] == "bloc_de_notas"
        assert info["window_id"] == 77

    def test_resumen_de_ventana_sin_titulo(self):
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(True, ACTION_USE))
        info = _pipeline(servicio).recover_profile("notepad", 77)
        ventana = info["window"]
        assert ventana["window_id"] == 77
        assert ventana["pid"] == 4242
        assert ventana["display_id"] == "display-2"
        assert "title" not in ventana
        assert "documento privado" not in repr(info)

    def test_ventana_inexistente_no_rompe_la_recuperacion(self):
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(True, ACTION_USE))
        info = _pipeline(servicio, _AdaptadorFalso(ventana=None)).recover_profile("notepad", 77)
        assert info["recovered"] is True
        assert "window" not in info

    def test_excepcion_al_leer_la_ventana_se_avisa(self):
        servicio = _ValidezFalsa(_perfil(), ProfileValidity(True, ACTION_USE))
        info = _pipeline(servicio, _AdaptadorFalso(error=OSError("hwnd invalido"))).recover_profile("notepad", 77)
        assert info["recovered"] is True
        assert any("hwnd invalido" in aviso for aviso in info.get("warnings", []))
