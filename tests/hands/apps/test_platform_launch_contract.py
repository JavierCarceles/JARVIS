# -*- coding: ascii -*-
"""
Tests del contrato de lanzamiento (``src/hands/apps/platform_launch.py``) y de
su adaptador Windows (``src/hands/apps/launch_windows.py``).

Casos del contrato comunes a todos los adaptadores:
- argumentos inseguros (metacaracteres de shell, rutas en un AUMID): no se
  lanza nada (``unsafe_argument``);
- rutas inexistentes (ejecutable o acceso directo): ``target_not_localizable``;
- permiso denegado por el SO: ``permission_denied`` en la etapa ``permission``;
- URI/URL no admitida: ``unsupported_uri`` (en el lanzamiento y en el preflight
  del adaptador Windows, que el servicio unico convierte en ese codigo);
- aplicacion no instalada: ``not_installed`` sin lanzar nada;
- timeout de verificacion: el proceso existe pero no aparece ventana en el
  tiempo dado (``window_not_found``) o el proceso no existe
  (``process_not_found``);
- adaptador ausente (SO sin soporte): ``adapter_missing`` / ``not_supported``.

La frontera nativa de Windows es inyectable (``spawner``, ``startfile``,
``discovery``, contrato de escritorio); se sustituye solo esa frontera, nunca la
decision del adaptador. Las ramas que solo existen en Windows (acceso directo,
URI, AUMID, resolucion) se comprueban en Windows y, en otro SO, se comprueba
que el adaptador Windows se niega con ``adapter_missing``.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import Any, List

import pytest

from src.core.operation_errors import ErrorCode, IdempotencyRegistry, OperationStage
from src.desktop.platform_contract import Capability, CapabilityStatus
from src.hands.apps.launch_windows import WindowsLaunchAdapter
from src.hands.apps.platform_launch import (
    NOT_FOUND,
    TARGET_AUMID,
    TARGET_EXE,
    TARGET_LNK,
    TARGET_URI,
    TARGET_URL,
    ApplicationLaunchAdapter,
    ApplicationLaunchService,
    LaunchPreflight,
    LaunchTarget,
    UnsupportedLaunchAdapter,
    get_launch_adapter,
)

EN_WINDOWS = sys.platform == "win32"


def _codigo(error: Any) -> str:
    codigo = getattr(error, "code", "")
    return str(getattr(codigo, "value", codigo))


def _destino(tipo: str, valor: str, nombre: str = "App de prueba") -> LaunchTarget:
    return LaunchTarget(identity="%s:%s" % (tipo, valor), display_name=nombre, target_type=tipo,
                        target=valor, platform="windows", source="test")


class _Spawner:
    def __init__(self, error: BaseException = None) -> None:
        self.error = error
        self.llamadas: List[Any] = []

    def __call__(self, argv: Any) -> Any:
        self.llamadas.append(list(argv))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(pid=os.getpid())


class _EscritorioSinVentanas:
    def list_windows(self, pid: Any = None, app_identity: Any = None, visible_only: bool = True) -> Any:
        return SimpleNamespace(ok=True, value=[])


@pytest.fixture
def ejecutable(tmp_path):
    ruta = tmp_path / "app_prueba.exe"
    ruta.write_bytes(b"MZ")
    return str(ruta)


# ---------------------------------------------------------------------------
# Lanzamiento base (comun a los adaptadores)
# ---------------------------------------------------------------------------


class TestLanzamientoBase:
    @pytest.mark.parametrize("valor", ["calc.exe & del x", "a;b", "a|b", "a`b", "$(x)", "a>b"])
    def test_argumento_inseguro_no_lanza(self, valor):
        spawner = _Spawner()
        resultado = ApplicationLaunchAdapter().launch(_destino(TARGET_EXE, valor), spawner=spawner)
        assert not resultado.success
        assert _codigo(resultado.error) == ErrorCode.UNSAFE_ARGUMENT
        assert spawner.llamadas == []

    def test_ejecutable_inexistente(self, tmp_path):
        spawner = _Spawner()
        resultado = ApplicationLaunchAdapter().launch(
            _destino(TARGET_EXE, str(tmp_path / "no_existe.exe")), spawner=spawner)
        assert _codigo(resultado.error) == ErrorCode.TARGET_NOT_LOCALIZABLE
        assert spawner.llamadas == []

    def test_ejecutable_existente_se_lanza_con_lista_de_argumentos(self, ejecutable):
        spawner = _Spawner()
        resultado = ApplicationLaunchAdapter().launch(_destino(TARGET_EXE, ejecutable), spawner=spawner)
        assert resultado.success and resultado.launched
        assert spawner.llamadas == [[ejecutable]]
        assert resultado.evidence["mechanism"] == "process_argv"

    @pytest.mark.parametrize("error,codigo,etapa", [
        (PermissionError("acceso denegado"), ErrorCode.PERMISSION_DENIED, OperationStage.PERMISSION),
        (FileNotFoundError("borrado"), ErrorCode.TARGET_NOT_LOCALIZABLE, OperationStage.LAUNCH),
        (OSError("fallo del SO"), ErrorCode.LAUNCH_FAILED, OperationStage.LAUNCH),
    ])
    def test_errores_del_so_al_lanzar(self, ejecutable, error, codigo, etapa):
        resultado = ApplicationLaunchAdapter().launch(_destino(TARGET_EXE, ejecutable), spawner=_Spawner(error))
        assert not resultado.success
        assert _codigo(resultado.error) == codigo
        assert resultado.error.stage == etapa

    @pytest.mark.parametrize("url", ["ftp://servidor/x", "file:///C:/x", "javascript:alert(1)"])
    def test_url_no_http_no_se_abre(self, url):
        abiertas: List[str] = []
        resultado = ApplicationLaunchAdapter().launch(
            _destino(TARGET_URL, url), url_opener=lambda u: abiertas.append(u) or True)
        assert _codigo(resultado.error) == ErrorCode.UNSUPPORTED_URI
        assert abiertas == []

    def test_url_https_se_abre_y_su_fallo_se_informa(self):
        ok = ApplicationLaunchAdapter().launch(_destino(TARGET_URL, "https://example.com"), url_opener=lambda u: True)
        assert ok.success and ok.evidence["mechanism"] == "default_browser"
        fallo = ApplicationLaunchAdapter().launch(_destino(TARGET_URL, "https://example.com"), url_opener=lambda u: False)
        assert _codigo(fallo.error) == ErrorCode.LAUNCH_FAILED

    def test_tipo_de_destino_no_soportado_por_el_adaptador_base(self):
        resultado = ApplicationLaunchAdapter().launch(_destino(TARGET_AUMID, "Microsoft.App_x!App"))
        assert _codigo(resultado.error) == ErrorCode.NOT_SUPPORTED


# ---------------------------------------------------------------------------
# Verificacion con espera acotada
# ---------------------------------------------------------------------------


class TestVerificacionConTimeout:
    def test_proceso_vivo_sin_ventana_es_window_not_found_tras_el_timeout(self):
        adaptador = ApplicationLaunchAdapter(desktop=_EscritorioSinVentanas(), poll_interval=0.05)
        resultado = adaptador.verify(os.getpid(), _destino(TARGET_EXE, "x.exe"), timeout=0.2)
        assert not resultado.success
        assert resultado.process_verified and not resultado.window_verified
        assert _codigo(resultado.error) == ErrorCode.WINDOW_NOT_FOUND
        assert resultado.error.stage == OperationStage.WINDOW

    def test_proceso_inexistente_es_process_not_found(self):
        adaptador = ApplicationLaunchAdapter(desktop=_EscritorioSinVentanas(), poll_interval=0.05)
        resultado = adaptador.verify(None, _destino(TARGET_EXE, "x.exe"), timeout=0.1)
        assert not resultado.success
        assert _codigo(resultado.error) == ErrorCode.PROCESS_NOT_FOUND


# ---------------------------------------------------------------------------
# Adaptador ausente
# ---------------------------------------------------------------------------


class TestAdaptadorAusente:
    def test_so_sin_adaptador_devuelve_unsupported(self):
        adaptador = get_launch_adapter("linux")
        assert isinstance(adaptador, UnsupportedLaunchAdapter)
        assert all(r.status == CapabilityStatus.NO_SOPORTADO for r in adaptador.capabilities().values())
        resolucion = adaptador.resolve("notepad")
        assert resolucion.status == NOT_FOUND
        assert _codigo(resolucion.error) == ErrorCode.NOT_SUPPORTED
        lanzamiento = adaptador.launch(_destino(TARGET_EXE, "notepad.exe"))
        assert _codigo(lanzamiento.error) == ErrorCode.ADAPTER_MISSING

    def test_servicio_con_adaptador_ausente_no_lanza_nada(self):
        spawner = _Spawner()
        servicio = ApplicationLaunchService(
            adapter=get_launch_adapter("linux"), app_manager=SimpleNamespace(get_application=lambda n: None),
            process_spawner=spawner, registry=IdempotencyRegistry(),
        )
        resultado = servicio.open("notepad")
        assert not resultado.success
        assert spawner.llamadas == []

    @pytest.mark.parametrize("plataforma,clase", [("win32", "WindowsLaunchAdapter"), ("darwin", "MacOSLaunchAdapter")])
    def test_seleccion_del_adaptador_por_so(self, plataforma, clase):
        assert type(get_launch_adapter(plataforma)).__name__ == clase


# ---------------------------------------------------------------------------
# Adaptador Windows
# ---------------------------------------------------------------------------


class _DescubrimientoVacio:
    """Frontera de descubrimiento sin candidatos (aplicacion no instalada)."""

    def __init__(self) -> None:
        self.llamadas: List[str] = []

    def _vacio(self) -> Any:
        return SimpleNamespace(candidatos=[], alternativas=[], requiere_desambiguacion=False, ambiguo=False)

    def resolver_aplicacion_por_nombre_con_desambiguacion(self, name: str, incluir_preflight: bool = True) -> Any:
        self.llamadas.append("inventario")
        return self._vacio()

    def buscar_por_nombre_con_desambiguacion(self, name: str, incluir_inventario: bool = False) -> Any:
        self.llamadas.append("nativas")
        return self._vacio()


class _PreflightPermite:
    def check_launch_target(self, application: Any, destination: str, target_type: Any = None) -> dict:
        return {"allowed": True, "reason": "ok"}


def _windows(**kwargs: Any) -> WindowsLaunchAdapter:
    kwargs.setdefault("preflight", _PreflightPermite())
    return WindowsLaunchAdapter(app_manager=SimpleNamespace(get_application=lambda n: None), **kwargs)


class TestAdaptadorWindows:
    def test_capacidades_declaradas_segun_el_so(self):
        capacidades = _windows(desktop=_EscritorioSinVentanas()).capabilities()
        esperado = CapabilityStatus.DISPONIBLE if EN_WINDOWS else CapabilityStatus.NO_SOPORTADO
        for cap in (Capability.DISCOVER, Capability.RESOLVE, Capability.PREFLIGHT, Capability.LAUNCH):
            assert capacidades[cap].status == esperado

    def test_aplicacion_no_instalada(self):
        descubrimiento = _DescubrimientoVacio()
        resolucion = _windows(discovery=descubrimiento).resolve("AplicacionInexistente")
        assert resolucion.status == NOT_FOUND
        if EN_WINDOWS:
            assert _codigo(resolucion.error) == ErrorCode.NOT_INSTALLED
            assert descubrimiento.llamadas == ["inventario", "nativas"]
        else:
            assert _codigo(resolucion.error) == ErrorCode.ADAPTER_MISSING
            assert descubrimiento.llamadas == []

    def test_nombre_inseguro_no_se_resuelve(self):
        descubrimiento = _DescubrimientoVacio()
        resolucion = _windows(discovery=descubrimiento).resolve("notepad & calc")
        assert _codigo(resolucion.error) == ErrorCode.INVALID_ARGUMENT
        assert descubrimiento.llamadas == []

    @pytest.mark.parametrize("uri", ["ftp://x", "file:///C:/Windows/notepad.exe", "vbscript:x"])
    def test_preflight_rechaza_uri_no_admitida(self, uri):
        decision = _windows().preflight(_destino(TARGET_URI, uri))
        assert not decision.allowed
        assert decision.blocked_by == "unsupported_uri"

    def test_servicio_convierte_el_bloqueo_de_uri_en_unsupported_uri(self):
        adaptador = _windows()
        destino = _destino(TARGET_URI, "ftp://x")
        servicio = ApplicationLaunchService(adapter=adaptador, registry=IdempotencyRegistry())
        resultado = servicio._target_preflight(destino)
        assert resultado is not None and not resultado.success
        assert _codigo(resultado.error) == ErrorCode.UNSUPPORTED_URI

    def test_acceso_directo_inexistente(self, tmp_path):
        abiertos: List[str] = []
        resultado = _windows(startfile=abiertos.append).launch(_destino(TARGET_LNK, str(tmp_path / "no.lnk")))
        assert not resultado.success
        esperado = ErrorCode.TARGET_NOT_LOCALIZABLE if EN_WINDOWS else ErrorCode.ADAPTER_MISSING
        assert _codigo(resultado.error) == esperado
        assert abiertos == []

    def test_uri_no_admitida_en_el_lanzamiento(self):
        abiertos: List[str] = []
        resultado = _windows(startfile=abiertos.append).launch(_destino(TARGET_URI, "ftp://x"))
        esperado = ErrorCode.UNSUPPORTED_URI if EN_WINDOWS else ErrorCode.ADAPTER_MISSING
        assert _codigo(resultado.error) == esperado
        assert abiertos == []

    @pytest.mark.parametrize("aumid", ["Microsoft.App\\..\\x!App", "a/b!App", "Microsoft.App;calc!App"])
    def test_aumid_inseguro_no_se_lanza(self, aumid):
        spawner = _Spawner()
        resultado = _windows().launch(_destino(TARGET_AUMID, aumid), spawner=spawner)
        esperado = ErrorCode.UNSAFE_ARGUMENT if EN_WINDOWS else ErrorCode.ADAPTER_MISSING
        assert _codigo(resultado.error) == esperado
        assert spawner.llamadas == []

    @pytest.mark.skipif(not EN_WINDOWS, reason="Rama solo de Windows (excepcion (a)); en otro SO se comprueba ADAPTER_MISSING arriba")
    def test_aumid_valido_usa_shell_appsfolder_con_lista_de_argumentos(self):
        spawner = _Spawner()
        resultado = _windows(desktop=_EscritorioSinVentanas()).launch(
            _destino(TARGET_AUMID, "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"), spawner=spawner)
        assert resultado.success
        assert spawner.llamadas == [["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"]]

    @pytest.mark.skipif(not EN_WINDOWS, reason="Rama solo de Windows (excepcion (a)); en otro SO se comprueba ADAPTER_MISSING arriba")
    def test_permiso_denegado_al_abrir_un_acceso_directo(self, tmp_path):
        acceso = tmp_path / "app.lnk"
        acceso.write_bytes(b"L")

        def denegar(_ruta: str) -> None:
            raise PermissionError("acceso denegado")

        resultado = _windows(startfile=denegar, desktop=_EscritorioSinVentanas()).launch(_destino(TARGET_LNK, str(acceso)))
        assert _codigo(resultado.error) == ErrorCode.PERMISSION_DENIED
        assert resultado.error.stage == OperationStage.PERMISSION


class TestPreflightContrato:
    def test_from_preflight_dict_conserva_detalles(self):
        decision = LaunchPreflight.from_preflight_dict(
            {"allowed": False, "reason": "bloqueada", "blocked_by": "permission_denied", "x": 1})
        assert not decision.allowed
        assert decision.blocked_by == "permission_denied"
        assert decision.details == {"x": 1}


# ---------------------------------------------------------------------------
# Cierre: solo las ventanas que JARVIS abrio y verifico
# ---------------------------------------------------------------------------


class _AdaptadorAbreVentana(ApplicationLaunchAdapter):
    """Frontera de lanzamiento: 'abre' y verifica una ventana conocida."""

    def __init__(self, pid: int, window_id: int, escritorio: Any) -> None:
        super().__init__(desktop=escritorio)
        self.pid = pid
        self.window_id = window_id

    def launch(self, target, timeout=15.0, spawner=None, url_opener=None):
        from src.hands.apps.platform_launch import LaunchOutcome

        return LaunchOutcome(True, pid=self.pid, target=target, launched=True,
                             evidence={"launch_started_at": 0.0, "preexisting_pids": [], "preexisting_window_ids": []})

    def verify(self, pid, identity=None, timeout=10.0, launch_started_at=None,
               preexisting_pids=None, preexisting_window_ids=None):
        from src.hands.apps.platform_launch import LaunchOutcome

        ventana = SimpleNamespace(window_id=self.window_id, pid=self.pid)
        return LaunchOutcome(True, pid=self.pid, window=ventana, target=identity,
                             process_verified=True, window_verified=True)


class _EscritorioConVentanas:
    """Ventanas del escritorio por identificador -> PID; registra los cierres."""

    def __init__(self, ventanas: Any) -> None:
        self.ventanas = dict(ventanas)
        self.cerradas: List[int] = []

    def get_window(self, window_id: int) -> Any:
        pid = self.ventanas.get(int(window_id))
        if pid is None:
            return SimpleNamespace(ok=False, value=None, error="no existe")
        return SimpleNamespace(ok=True, value=SimpleNamespace(window_id=int(window_id), pid=pid), error=None)

    def list_windows(self, pid: Any = None, app_identity: Any = None, visible_only: bool = True) -> Any:
        valor = [SimpleNamespace(window_id=w, pid=p) for w, p in self.ventanas.items() if pid is None or p == pid]
        return SimpleNamespace(ok=True, value=valor)

    def close_window(self, window_id: int) -> Any:
        self.cerradas.append(int(window_id))
        self.ventanas.pop(int(window_id), None)
        return SimpleNamespace(ok=True)


class TestCierreSoloDeVentanasPropias:
    def _abrir(self, escritorio: Any, pid: int = 500, window_id: int = 7) -> ApplicationLaunchService:
        adaptador = _AdaptadorAbreVentana(pid, window_id, escritorio)
        servicio = ApplicationLaunchService(adapter=adaptador, registry=IdempotencyRegistry())
        destino = _destino(TARGET_AUMID, "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", "Calculadora")
        resultado = servicio._launch_and_verify("calculadora", destino, 1.0, "clave")
        assert resultado.success
        return servicio

    def test_proceso_anfitrion_compartido_solo_cierra_la_ventana_abierta(self):
        # ApplicationFrameHost (PID 500) aloja la Calculadora (7) y la
        # Configuracion del usuario (8): solo se cierra la 7.
        escritorio = _EscritorioConVentanas({7: 500, 8: 500})
        servicio = self._abrir(escritorio)
        resultado = servicio.close("calculadora")
        assert resultado.success
        assert escritorio.cerradas == [7]
        assert 8 in escritorio.ventanas

    def test_identificador_reutilizado_por_otro_proceso_no_se_cierra(self):
        escritorio = _EscritorioConVentanas({7: 500})
        servicio = self._abrir(escritorio)
        escritorio.ventanas[7] = 999  # el SO reutilizo el identificador
        resultado = servicio.close("calculadora")
        assert not resultado.success
        assert escritorio.cerradas == []

    def test_sin_aperturas_propias_no_cierra_nada(self):
        escritorio = _EscritorioConVentanas({7: 500})
        servicio = ApplicationLaunchService(adapter=_AdaptadorAbreVentana(500, 7, escritorio),
                                            registry=IdempotencyRegistry())
        resultado = servicio.close("calculadora")
        assert not resultado.success
        assert _codigo(resultado.error) == ErrorCode.NOT_FOUND
        assert escritorio.cerradas == []

    def test_tras_cerrar_se_olvida_la_apertura(self):
        escritorio = _EscritorioConVentanas({7: 500})
        servicio = self._abrir(escritorio)
        servicio.close("calculadora")
        assert servicio._owned == {} and servicio._owned_windows == {}
        assert not servicio.close("calculadora").success
