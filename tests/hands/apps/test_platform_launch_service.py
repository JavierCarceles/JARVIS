# -*- coding: utf-8 -*-
"""
Tests del servicio de apertura (`ApplicationLaunchService`) y de la
verificacion del adaptador (`ApplicationLaunchAdapter.verify`) en los casos de
aplicaciones de instancia unica o con proceso residente.

La frontera del SO (lista de procesos y de ventanas) se sustituye por dobles
que devuelven datos fijos; la decision que se prueba (que ventana se acepta,
que destino se lanza, que proceso pasa a ser propio) la toma el codigo real.
Se ejecutan en cualquier SO.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from src.core.operation_errors import IdempotencyRegistry
from src.desktop.platform_contract import WindowInfo
from src.hands.apps.platform_launch import (
    TARGET_EXE,
    ApplicationLaunchAdapter,
    ApplicationLaunchService,
    LaunchOutcome,
    LaunchTarget,
)


class _Resultado:
    def __init__(self, value: Any, ok: bool = True) -> None:
        self.value = value
        self.ok = ok


class _EscritorioFalso:
    """Escritorio con ventanas fijas por PID."""

    def __init__(self, ventanas_por_pid: Dict[int, List[WindowInfo]]) -> None:
        self.ventanas_por_pid = ventanas_por_pid

    def list_windows(self, pid: Optional[int] = None, visible_only: bool = True) -> _Resultado:
        if pid is None:
            todas = [v for vs in self.ventanas_por_pid.values() for v in vs]
            return _Resultado(todas)
        return _Resultado(list(self.ventanas_por_pid.get(int(pid), [])))

    def get_window(self, window_id: int) -> _Resultado:
        for ventanas in self.ventanas_por_pid.values():
            for ventana in ventanas:
                if int(ventana.window_id) == int(window_id):
                    return _Resultado(ventana)
        return _Resultado(None, ok=False)


def _ventana(window_id: int, pid: int) -> WindowInfo:
    return WindowInfo(window_id=window_id, pid=pid, is_visible=True)


def _destino(nombre_proceso: str = "navegador.exe") -> LaunchTarget:
    return LaunchTarget(
        identity="prueba", display_name="Navegador", target_type=TARGET_EXE,
        target="C:/Prueba/navegador.exe", platform="windows", source="prueba",
        process_names=[nombre_proceso],
    )


class TestVerificarVentanaNuevaDeProcesoExistente:
    """Instancia unica: la ventana nueva pertenece a un proceso que ya existia."""

    def _adaptador(self, monkeypatch, escritorio, pids_existentes):
        adaptador = ApplicationLaunchAdapter(desktop=escritorio, poll_interval=0.01)
        monkeypatch.setattr(
            ApplicationLaunchAdapter, "_pids_by_names", staticmethod(lambda names: set(pids_existentes))
        )
        monkeypatch.setattr(
            ApplicationLaunchAdapter, "_new_pids_by_names", staticmethod(lambda names, before, started: [])
        )
        return adaptador

    def test_acepta_solo_la_ventana_que_no_existia(self, monkeypatch):
        escritorio = _EscritorioFalso({100: [_ventana(1, 100), _ventana(2, 100)]})
        adaptador = self._adaptador(monkeypatch, escritorio, {100})
        resultado = adaptador.verify(
            None, _destino(), timeout=0.05,
            preexisting_pids=[100], preexisting_window_ids=[1],
        )
        assert resultado.success is True
        assert resultado.window.window_id == 2
        assert resultado.evidence["window_match"] == "nueva_ventana_de_proceso_existente"

    def test_sin_ventana_nueva_no_reutiliza_las_del_usuario(self, monkeypatch):
        escritorio = _EscritorioFalso({100: [_ventana(1, 100)]})
        adaptador = self._adaptador(monkeypatch, escritorio, {100})
        resultado = adaptador.verify(
            None, _destino(), timeout=0.05,
            preexisting_pids=[100], preexisting_window_ids=[1],
        )
        assert resultado.success is False
        assert resultado.window is None

    def test_sin_instantanea_previa_no_acepta_ventanas_de_procesos_existentes(self, monkeypatch):
        escritorio = _EscritorioFalso({100: [_ventana(2, 100)]})
        adaptador = self._adaptador(monkeypatch, escritorio, {100})
        resultado = adaptador.verify(
            None, _destino(), timeout=0.05,
            preexisting_pids=[100], preexisting_window_ids=None,
        )
        assert resultado.success is False


class _AdaptadorLanzamientoFalso(ApplicationLaunchAdapter):
    """Lanza sin crear procesos y verifica con una ventana fija."""

    def __init__(self, pid_lanzado: int, preexistentes: List[int], ventana: WindowInfo) -> None:
        super().__init__(desktop=_EscritorioFalso({ventana.pid: [ventana]}))
        self.pid_lanzado = pid_lanzado
        self.preexistentes = preexistentes
        self.ventana = ventana

    def launch(self, target, timeout=15.0, spawner=None, url_opener=None):
        return LaunchOutcome(
            True, pid=self.pid_lanzado, target=target, launched=True,
            evidence={"launch_started_at": 0.0, "preexisting_pids": list(self.preexistentes),
                      "preexisting_window_ids": []},
        )

    def verify(self, pid, identity=None, timeout=10.0, launch_started_at=None,
               preexisting_pids=None, preexisting_window_ids=None):
        return LaunchOutcome(
            True, pid=self.ventana.pid, window=self.ventana, target=identity,
            process_verified=True, window_verified=True,
        )


class TestProcesosPropios:
    """Solo un proceso creado por la apertura pasa a ser propio de JARVIS."""

    def test_proceso_preexistente_no_se_registra_como_propio(self):
        adaptador = _AdaptadorLanzamientoFalso(100, [100], _ventana(7, 100))
        servicio = ApplicationLaunchService(adapter=adaptador, registry=IdempotencyRegistry())
        resultado = servicio._launch_and_verify("navegador", _destino(), 1.0, "clave")
        assert resultado.success is True
        assert servicio._owned == {}

    def test_proceso_nuevo_se_registra_como_propio(self):
        adaptador = _AdaptadorLanzamientoFalso(200, [100], _ventana(7, 200))
        servicio = ApplicationLaunchService(adapter=adaptador, registry=IdempotencyRegistry())
        resultado = servicio._launch_and_verify("navegador", _destino(), 1.0, "clave")
        assert resultado.success is True
        assert servicio._owned == {"navegador": [200]}


class TestReaperturaTrasCerrarVentana:
    """La apertura recordada deja de valer si su ventana ya no existe."""

    def test_ventana_cerrada_invalida_la_apertura_previa(self, monkeypatch):
        ventana = _ventana(7, 300)
        adaptador = _AdaptadorLanzamientoFalso(300, [], ventana)
        registro = IdempotencyRegistry()
        servicio = ApplicationLaunchService(adapter=adaptador, registry=registro)
        monkeypatch.setattr(ApplicationLaunchAdapter, "_pid_alive", staticmethod(lambda pid: True))
        servicio._launch_and_verify("calc", _destino("calc.exe"), 1.0, "open_application:calc")
        hecho, _valor = registro.get("open_application:calc")
        assert hecho is True
        # La ventana se cierra; el proceso (p. ej. ApplicationFrameHost) sigue vivo.
        adaptador._desktop.ventanas_por_pid[300] = []
        hecho, _valor = registro.get("open_application:calc")
        assert hecho is False


class TestCatalogoComandoFueraDePath:
    """Un comando del catalogo que no esta en PATH se lanza por la ruta del preflight."""

    def _app(self, ejecutable: str) -> Any:
        return SimpleNamespace(
            name="Navegador", metadata={}, executable=ejecutable, url=None,
            login_required=False, preflight_requirements=["application_available"],
            get_capability=lambda nombre: None,
        )

    def _servicio(self, ruta_preflight: Optional[str]) -> ApplicationLaunchService:
        decision = {"allowed": True, "reason": "ok", "blocked_by": None,
                    "executable_path": ruta_preflight}
        preflight = SimpleNamespace(check=lambda datos: decision)
        return ApplicationLaunchService(
            adapter=ApplicationLaunchAdapter(desktop=None),
            preflight=preflight,
            is_open_checker=lambda nombre, app: False,
            registry=IdempotencyRegistry(),
        )

    def test_usa_la_ruta_resuelta_por_el_preflight(self, tmp_path):
        ejecutable = tmp_path / "navegador.exe"
        ejecutable.write_bytes(b"MZ")
        plan = self._servicio(str(ejecutable))._plan_catalog_app(
            "navegador", self._app("comando_que_no_existe_en_path_xyz")
        )
        assert isinstance(plan, LaunchTarget)
        assert plan.target_type == TARGET_EXE
        assert plan.target == str(ejecutable)
        assert plan.process_names[0] == "navegador.exe"

    def test_sin_ruta_del_preflight_no_esta_disponible(self):
        plan = self._servicio(None)._plan_catalog_app(
            "navegador", self._app("comando_que_no_existe_en_path_xyz")
        )
        assert isinstance(plan, LaunchOutcome)
        assert plan.success is False


class TestProcesoResidenteSinVentana:
    """`_running_without_window` solo es True con procesos reales y sin ventana."""

    def _servicio(self, escritorio) -> ApplicationLaunchService:
        return ApplicationLaunchService(
            adapter=ApplicationLaunchAdapter(desktop=escritorio), registry=IdempotencyRegistry()
        )

    def test_procesos_sin_ventana(self, monkeypatch):
        monkeypatch.setattr(ApplicationLaunchAdapter, "_pids_by_names", staticmethod(lambda names: {100}))
        servicio = self._servicio(_EscritorioFalso({100: []}))
        assert servicio._running_without_window(SimpleNamespace(executable="navegador.exe")) is True

    def test_procesos_con_ventana(self, monkeypatch):
        monkeypatch.setattr(ApplicationLaunchAdapter, "_pids_by_names", staticmethod(lambda names: {100}))
        servicio = self._servicio(_EscritorioFalso({100: [_ventana(1, 100)]}))
        assert servicio._running_without_window(SimpleNamespace(executable="navegador.exe")) is False

    def test_sin_procesos_no_decide_lanzar(self, monkeypatch):
        monkeypatch.setattr(ApplicationLaunchAdapter, "_pids_by_names", staticmethod(lambda names: set()))
        servicio = self._servicio(_EscritorioFalso({}))
        assert servicio._running_without_window(SimpleNamespace(executable="navegador.exe")) is False
