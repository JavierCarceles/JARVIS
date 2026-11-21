# -*- coding: ascii -*-
"""
Tests de contrato del adaptador de lanzamiento macOS con TextEdit y Calculadora.

Regla 3 de la cabecera del roadmap (macOS a ciegas): se sustituye SOLO la
frontera nativa ``MacLaunchBoundary`` por una frontera sintetica realista
(bundles de ``/System/Applications``, Info.plist con bundle id, nombre visible
localizado por Spotlight, cuarentena/Gatekeeper, ``open -b`` y PIDs). Todo lo
demas es codigo de produccion: ``MacOSLaunchAdapter`` (descubrimiento,
resolucion, preflight, lanzamiento), ``ApplicationPreflight`` (rama bundle),
``ApplicationLaunchService`` (flujo unico) y ``register_bundles_in_inventory``
sobre una SQLite temporal.

No son tests de otro SO: se ejecutan y deben pasar en Windows (y en macOS).

Comportamientos comprobados:
- TextEdit se descubre por nombre y se resuelve a su bundle id, sin rutas en la
  identidad; Calculadora se resuelve por el nombre visible localizado
  ("Calculadora") aunque el Info.plist diga "Calculator".
- Una aplicacion no instalada devuelve ``not_installed``.
- El preflight valida el bundle a traves de la frontera del adaptador:
  permitido sin cuarentena, bloqueado por cuarentena o por Gatekeeper (nunca se
  elude ni se llama a ``open``), bloqueado si el bundle no existe.
- El servicio unico abre TextEdit con ``open -b <bundle_id>`` (lista de
  argumentos), detecta el PID nuevo y no reutiliza PIDs preexistentes.
- Bundle id inseguro y fallo de LaunchServices devuelven errores concretos.
- El registro en el inventario local es idempotente y aislado por machine_id.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Sequence

import pytest

from src.core.operation_errors import ErrorCode, OperationStage
from src.desktop.platform_contract import Capability, CapabilityStatus
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.apps.launch_macos import (
    _SAFE_QUERY_TEXT,
    MacLaunchBoundary,
    MacOSLaunchAdapter,
    register_bundles_in_inventory,
)
from src.hands.apps.platform_launch import (
    NOT_FOUND,
    RESOLVED,
    TARGET_BUNDLE,
    ApplicationLaunchService,
    LaunchTarget,
)

TEXTEDIT = "/System/Applications/TextEdit.app"
CALCULATOR = "/System/Applications/Calculator.app"

BUNDLES: Dict[str, Dict[str, Any]] = {
    TEXTEDIT: {
        "CFBundleIdentifier": "com.apple.TextEdit",
        "CFBundleName": "TextEdit",
        "CFBundleExecutable": "TextEdit",
    },
    CALCULATOR: {
        "CFBundleIdentifier": "com.apple.calculator",
        "CFBundleName": "Calculator",
        "CFBundleExecutable": "Calculator",
    },
}
# Nombre visible que indexa Spotlight (kMDItemDisplayName), localizado.
NOMBRES_SPOTLIGHT: Dict[str, List[str]] = {
    TEXTEDIT: ["TextEdit"],
    CALCULATOR: ["Calculator", "Calculadora"],
}


def _codigo(error: Any) -> str:
    codigo = getattr(error, "code", "")
    return str(getattr(codigo, "value", codigo))


class SyntheticMacLaunchBoundary(MacLaunchBoundary):
    """Frontera de lanzamiento macOS sintetica: no toca el disco ni procesos."""

    def __init__(
        self,
        quarantined: Sequence[str] = (),
        gatekeeper: Optional[Dict[str, Optional[bool]]] = None,
        open_code: int = 0,
        running: Optional[Dict[str, List[int]]] = None,
    ) -> None:
        super().__init__()
        self.quarantined = set(quarantined)
        self.gatekeeper = dict(gatekeeper or {})
        self.open_code = int(open_code)
        self.running: Dict[str, List[int]] = {k: list(v) for k, v in (running or {}).items()}
        self.opened: List[str] = []
        self._next_pid = 5000

    def list_application_bundles(self, roots: Sequence[str] = ()) -> List[str]:
        return list(BUNDLES)

    def spotlight_by_name(self, name: str) -> List[str]:
        if not _SAFE_QUERY_TEXT.match(name or ""):
            return []
        wanted = name.casefold()
        return [p for p, nombres in NOMBRES_SPOTLIGHT.items() if any(wanted in n.casefold() for n in nombres)]

    def spotlight_by_bundle_id(self, bundle_id: str) -> List[str]:
        return [p for p, info in BUNDLES.items() if info["CFBundleIdentifier"] == bundle_id]

    def bundle_exists(self, bundle_path: str) -> bool:
        return bundle_path in BUNDLES

    def read_info_plist(self, bundle_path: str) -> Dict[str, Any]:
        return dict(BUNDLES.get(bundle_path, {}))

    def is_quarantined(self, bundle_path: str) -> Optional[bool]:
        return bundle_path in self.quarantined

    def gatekeeper_assess(self, bundle_path: str) -> Optional[bool]:
        return self.gatekeeper.get(bundle_path, True)

    def open_bundle(self, bundle_id: str) -> int:
        self.opened.append(bundle_id)
        if self.open_code == 0:
            self._next_pid += 1
            self.running.setdefault(bundle_id, []).append(self._next_pid)
        return self.open_code

    def running_pids(self, bundle_id: str, executable_path: Optional[str] = None) -> List[int]:
        return list(self.running.get(bundle_id, []))


class _CatalogoSinEntradas:
    """Catalogo global vacio: obliga a resolver por descubrimiento local sin
    leer ``data/memory/entities.json``."""

    def get_application(self, name: str) -> Any:
        raise LookupError("catalogo vacio en el test")


def _adaptador(boundary: SyntheticMacLaunchBoundary, **kwargs: Any) -> MacOSLaunchAdapter:
    kwargs.setdefault("register_inventory", False)
    return MacOSLaunchAdapter(
        app_manager=_CatalogoSinEntradas(),
        boundary=boundary,
        preflight=ApplicationPreflight(),
        machine_id="mac-sintetico",
        **kwargs,
    )


def _servicio(adapter: MacOSLaunchAdapter) -> ApplicationLaunchService:
    from src.core.operation_errors import IdempotencyRegistry  # registro propio: sin estado global

    return ApplicationLaunchService(
        adapter=adapter,
        app_manager=_CatalogoSinEntradas(),
        verify_window=False,
        registry=IdempotencyRegistry(),
    )


# ---------------------------------------------------------------------------
# Descubrimiento y resolucion
# ---------------------------------------------------------------------------


class TestResolucionTextEditYCalculadora:
    def test_textedit_se_resuelve_a_su_bundle_id_sin_rutas_en_la_identidad(self):
        resolucion = _adaptador(SyntheticMacLaunchBoundary()).resolve("TextEdit")
        assert resolucion.status == RESOLVED
        destino = resolucion.target
        assert destino.target_type == TARGET_BUNDLE
        assert destino.target == "com.apple.TextEdit"
        assert destino.app_id == "com.apple.TextEdit"
        assert destino.identity == "bundle:com.apple.TextEdit"
        assert destino.platform == "macos"
        assert destino.process_names == ["TextEdit"]
        assert "/" not in destino.identity and "/" not in destino.target
        assert destino.machine_id == "mac-sintetico"

    @pytest.mark.parametrize("nombre", ["Calculadora", "calculadora", "Calculator"])
    def test_calculadora_se_resuelve_por_nombre_visible_localizado(self, nombre):
        resolucion = _adaptador(SyntheticMacLaunchBoundary()).resolve(nombre)
        assert resolucion.status == RESOLVED, resolucion.error
        assert resolucion.target.target == "com.apple.calculator"
        assert resolucion.target.process_names == ["Calculator"]

    def test_aplicacion_no_instalada_devuelve_not_installed(self):
        resolucion = _adaptador(SyntheticMacLaunchBoundary()).resolve("Pages")
        assert resolucion.status == NOT_FOUND
        assert _codigo(resolucion.error) == ErrorCode.NOT_INSTALLED

    def test_nombre_con_caracteres_no_admitidos_no_consulta_spotlight(self):
        boundary = SyntheticMacLaunchBoundary()
        resolucion = _adaptador(boundary).resolve("TextEdit; rm -rf ~")
        assert resolucion.status != RESOLVED
        assert boundary.opened == []


# ---------------------------------------------------------------------------
# Preflight (a traves de la frontera del adaptador)
# ---------------------------------------------------------------------------


class TestPreflightBundle:
    def _destino(self, adapter: MacOSLaunchAdapter, nombre: str = "TextEdit") -> LaunchTarget:
        resolucion = adapter.resolve(nombre)
        assert resolucion.status == RESOLVED
        return resolucion.target

    def test_bundle_sin_cuarentena_se_permite_con_ejecutable_dentro_del_bundle(self):
        adapter = _adaptador(SyntheticMacLaunchBoundary())
        decision = adapter.preflight(self._destino(adapter))
        assert decision.allowed, decision.reason
        assert decision.details.get("executable_path") == TEXTEDIT + "/Contents/MacOS/TextEdit"

    def test_bundle_en_cuarentena_se_bloquea_por_gatekeeper(self):
        adapter = _adaptador(SyntheticMacLaunchBoundary(quarantined=[TEXTEDIT]))
        decision = adapter.preflight(self._destino(adapter))
        assert not decision.allowed
        assert decision.blocked_by == "gatekeeper_quarantine"

    def test_bundle_rechazado_por_spctl_se_bloquea(self):
        adapter = _adaptador(SyntheticMacLaunchBoundary(gatekeeper={CALCULATOR: False}))
        decision = adapter.preflight(self._destino(adapter, "Calculadora"))
        assert not decision.allowed
        assert decision.blocked_by == "gatekeeper_rejected"

    def test_bundle_inexistente_se_bloquea(self):
        adapter = _adaptador(SyntheticMacLaunchBoundary())
        destino = LaunchTarget(
            identity="bundle:com.example.Fantasma", display_name="Fantasma", target_type=TARGET_BUNDLE,
            target="com.example.Fantasma", platform="macos", source="test", app_id="com.example.Fantasma",
            evidence={"bundle_path": "/Applications/Fantasma.app"},
        )
        decision = adapter.preflight(destino)
        assert not decision.allowed
        assert decision.blocked_by == "bundle_not_found"


# ---------------------------------------------------------------------------
# Flujo unico de apertura
# ---------------------------------------------------------------------------


class TestAperturaPorServicioUnico:
    def test_abre_textedit_con_open_b_y_detecta_el_pid_nuevo(self):
        boundary = SyntheticMacLaunchBoundary()
        outcome = _servicio(_adaptador(boundary)).open("TextEdit")
        assert outcome.success, outcome.error
        assert outcome.launched
        assert boundary.opened == ["com.apple.TextEdit"]
        assert outcome.pid == boundary.running["com.apple.TextEdit"][-1]
        assert outcome.evidence.get("mechanism") == "open -b"

    def test_abre_calculadora_por_nombre_localizado(self):
        boundary = SyntheticMacLaunchBoundary()
        outcome = _servicio(_adaptador(boundary)).open("Calculadora")
        assert outcome.success, outcome.error
        assert boundary.opened == ["com.apple.calculator"]

    def test_pid_preexistente_no_se_toma_como_propio(self):
        boundary = SyntheticMacLaunchBoundary(running={"com.apple.TextEdit": [111]})
        adapter = _adaptador(boundary)
        destino = adapter.resolve("TextEdit").target
        outcome = adapter.launch(destino, timeout=1.0)
        assert outcome.success
        assert outcome.pid not in (None, 111)
        assert outcome.evidence["preexisting_pids"] == [111]

    def test_cuarentena_bloquea_sin_llamar_a_open(self):
        boundary = SyntheticMacLaunchBoundary(quarantined=[TEXTEDIT])
        outcome = _servicio(_adaptador(boundary)).open("TextEdit")
        assert not outcome.success
        assert _codigo(outcome.error) == ErrorCode.GATEKEEPER_BLOCKED
        assert outcome.error.stage == OperationStage.PERMISSION
        assert boundary.opened == []

    def test_fallo_de_launchservices_devuelve_launch_failed(self):
        boundary = SyntheticMacLaunchBoundary(open_code=1)
        outcome = _servicio(_adaptador(boundary)).open("TextEdit")
        assert not outcome.success
        assert _codigo(outcome.error) == ErrorCode.LAUNCH_FAILED
        # Nunca se reintenta una apertura que ya llego a ejecutarse con exito;
        # un fallo de LaunchServices no lanzo nada y no duplica instancias.
        assert "com.apple.TextEdit" not in boundary.running

    def test_bundle_id_inseguro_no_llega_a_open(self):
        boundary = SyntheticMacLaunchBoundary()
        destino = LaunchTarget(
            identity="bundle:x", display_name="x", target_type=TARGET_BUNDLE,
            target="com.apple.TextEdit; open /tmp", platform="macos", source="test",
        )
        outcome = _adaptador(boundary).launch(destino, timeout=1.0)
        assert not outcome.success
        assert _codigo(outcome.error) == ErrorCode.UNSAFE_ARGUMENT
        assert boundary.opened == []

    def test_aplicacion_no_instalada_no_abre_nada(self):
        boundary = SyntheticMacLaunchBoundary()
        outcome = _servicio(_adaptador(boundary)).open("Pages")
        assert not outcome.success
        assert _codigo(outcome.error) in (ErrorCode.NOT_INSTALLED, ErrorCode.NOT_FOUND)
        assert boundary.opened == []


# ---------------------------------------------------------------------------
# Inventario local y capacidades
# ---------------------------------------------------------------------------


class TestInventarioYCapacidades:
    def test_registro_en_inventario_idempotente_y_aislado_por_equipo(self, tmp_path):
        from src.hands.inventory.system_inventory_storage import SystemInventoryStorage

        adapter = _adaptador(SyntheticMacLaunchBoundary())
        destinos = [adapter.resolve("TextEdit").target, adapter.resolve("Calculadora").target]
        storage = SystemInventoryStorage(tmp_path / "inventario.sqlite3")

        assert register_bundles_in_inventory(destinos, storage=storage, machine_id="mac-a") == 2
        # Segunda vez: nada nuevo, sin excepcion ni duplicados.
        assert register_bundles_in_inventory(destinos, storage=storage, machine_id="mac-a") == 0

        filas = storage.buscar_candidatos_registrados("mac-a", launch_type="bundle", limite=100)
        assert sorted(f["producto"] for f in filas) == ["com.apple.TextEdit", "com.apple.calculator"]
        assert storage.buscar_candidatos_registrados("mac-b", launch_type="bundle", limite=100) == []

    def test_capacidades_declaradas_segun_el_so(self):
        capacidades = _adaptador(SyntheticMacLaunchBoundary()).capabilities()
        esperado = CapabilityStatus.NO_VERIFICADO if sys.platform == "darwin" else CapabilityStatus.NO_SOPORTADO
        for cap in (Capability.DISCOVER, Capability.RESOLVE, Capability.PREFLIGHT, Capability.LAUNCH):
            assert capacidades[cap].status == esperado
