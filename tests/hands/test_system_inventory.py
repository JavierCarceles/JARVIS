# -*- coding: utf-8 -*-
"""
Tests del primer inventario del equipo (unidad 3.8.5.1.4.8.1).

Cubren:
- Decisión de cuándo se ejecuta el primer inventario (ningún previo vs. previo
  completado vs. previo interrumpido).
- Informe de alcance (volúmenes a escanear, exclusiones, privacidad).
- Ejecución en segundo plano no bloqueante con progreso real, persistencia en
  SQLite y persistencia de entradas, usando `RecorridoVolumen` y
  `SystemInventoryStorage` de producción sobre un directorio temporal REAL.

Todos los tests usan directorios temporales (tmp_path) y bases de datos
temporales; no tocan datos de producción ni rutas de usuario.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.hands.system_inventory import (
    AlcanceInventario,
    ConfigRefresco,
    ControlRecorrido,
    EntryType,
    EstadoCaducidad,
    EstadoPrimerInventario,
    GestorPrimerInventario,
    InventoryContract,
    ModoRefresco,
    PoliticaRefresco,
    PrimerInventarioYaEnEjecucionError,
    ProgresoInventario,
    ProgresoRecorrido,
    RecorridoVolumen,
    ResultadoRefresco,
    VolumeInfo,
    VolumeType,
    generate_machine_id,
)
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

MACHINE_ID = "machine-test-primer-inventario"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "system_inventory.sqlite3"


@pytest.fixture
def storage(db_path: Path) -> SystemInventoryStorage:
    storage = SystemInventoryStorage(db_path)
    storage.initialize()
    return storage


@pytest.fixture(autouse=True)
def _limpiar_bloqueos_prueba():
    """Limpia los bloqueos de escaneo entre tests (están a nivel de clase)."""
    import src.hands.system_inventory_storage as sis

    yield
    with sis._SCAN_LOCKS_GUARD:
        sis._SCAN_LOCKS.clear()


# ---------------------------------------------------------------------------
# Volumen de prueba (directorio temporal REAL en el volumen del sistema)
# ---------------------------------------------------------------------------

def _volumen_temporal(tmp_path: Path, nombre: str = "volumen_prueba") -> VolumeInfo:
    """Crea un directorio temporal REAL con archivos y devuelve su VolumeInfo."""
    base = tmp_path / nombre
    base.mkdir(parents=True, exist_ok=True)
    (base / "documento.txt").write_text("contenido de prueba\n", encoding="utf-8")
    sub = base / "subcarpeta"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "ejecutable.exe").write_text("MZ\x90\x00", encoding="utf-8")
    (sub / "datos.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    (base / "oculto.log").write_text("log\n", encoding="utf-8")
    return VolumeInfo(
        letra="T:",
        ruta_raiz=str(base),
        tipo=VolumeType.FIXED,
        disponible=True,
        sistema_archivos="NTFS",
        etiqueta_volumen="prueba",
    )


# ---------------------------------------------------------------------------
# Decisión: cuándo se ejecuta el primer inventario
# ---------------------------------------------------------------------------

class TestDecisionPrimerInventario:
    def test_ejecutar_si_no_hay_scan_previo(self, storage: SystemInventoryStorage):
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        debe, motivo = gestor.debe_ejecutar_primer_inventario()
        assert debe is True
        assert motivo
        assert "No existe ningún escaneo previo" in motivo

    def test_no_ejecutar_si_ya_existe_scan_completado(
        self, storage: SystemInventoryStorage
    ):
        storage.begin_scan_run("scan-ok", MACHINE_ID, "C:", SCAN_MODE_FULL)
        storage.end_scan_run(
            "scan-ok", result=SCAN_RESULT_OK, entries_count=10, errors_count=0
        )
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        debe, motivo = gestor.debe_ejecutar_primer_inventario()
        assert debe is False
        assert "Ya existe un inventario previo completado" in motivo

    def test_ejecutar_si_ultimo_scan_interrumpido(
        self, storage: SystemInventoryStorage
    ):
        storage.begin_scan_run("scan-interrumpido", MACHINE_ID, "C:", SCAN_MODE_FULL)
        storage.end_scan_run(
            "scan-interrumpido",
            result=SCAN_RESULT_INTERRUPTED,
            entries_count=3,
            errors_count=1,
        )
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        debe, motivo = gestor.debe_ejecutar_primer_inventario()
        assert debe is True
        assert "sin finalizar" in motivo or "interrumpido" in motivo


# ---------------------------------------------------------------------------
# Informe de alcance
# ---------------------------------------------------------------------------

class TestAlcanceInventario:
    def test_alcance_estructura_y_privacidad(self, storage: SystemInventoryStorage):
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        alcance = gestor.reportar_alcance()

        assert isinstance(alcance, AlcanceInventario)
        assert alcance.machine_id == MACHINE_ID
        assert alcance.sistema_operativo
        assert alcance.modo == "completo"
        assert isinstance(alcance.volumenes_a_escanear, list)
        assert alcance.total_volumenes >= 0
        assert isinstance(alcance.volumenes_excluidos, list)
        assert isinstance(alcance.exclusiones_rutas, list)
        assert alcance.incluir_ocultos is True
        assert alcance.incluir_sistema is True
        assert alcance.leer_contenido_archivos is False  # privacidad (3.8.5.1.4.1.9)
        assert alcance.es_primer_inventario is True
        assert alcance.motivo
        assert alcance.generado_en

        # Cada volumen a escanear debe ser disponible y no excluido.
        for volumen in alcance.volumenes_a_escanear:
            assert volumen.disponible is True
            raiz = volumen.ruta_raiz or volumen.letra
            assert gestor.contrato.should_exclude_mount(raiz) is False


# ---------------------------------------------------------------------------
# Ejecución en segundo plano no bloqueante (scanner y almacenamiento reales)
# ---------------------------------------------------------------------------

class TestEjecucionPrimerInventario:
    def test_no_bloquea_y_progresa_hasta_completado(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        volumen = _volumen_temporal(tmp_path)
        gestor = GestorPrimerInventario(MACHINE_ID, storage)

        progresos = []

        def callback(p: ProgresoInventario):
            progresos.append(p)

        inicio = time.perf_counter()
        ejecucion = gestor.ejecutar_primera_vez(
            callback_progreso=callback, volumenes=[volumen]
        )
        despues_de_lanzar = time.perf_counter()

        # Devuelve inmediatamente: no bloquea el llamante.
        assert despues_de_lanzar - inicio < 5.0

        # Espera a que termine de verdad en el hilo de fondo.
        assert ejecucion.esperar(timeout=60.0) is True
        assert ejecucion.finalizado is True
        assert ejecucion.esta_en_ejecucion is False

        resultado = ejecucion.resultado()
        assert resultado is not None
        assert resultado["interrumpido"] is False
        assert resultado["volumenes_completados"] == 1
        assert resultado["entradas_procesadas"] >= 4  # 2 archivos + 2 directorios
        assert len(resultado["scan_ids"]) == 1

        assert ejecucion.progreso.estado == EstadoPrimerInventario.COMPLETADO
        assert ejecucion.progreso.completado is True
        assert ejecucion.progreso.interrumpido is False
        assert ejecucion.progreso.cobertura_global == 100.0
        assert ejecucion.progreso.finished_at is not None

        # Progreso real recibido por callbacks durante la ejecución.
        assert len(progresos) >= 1
        assert any(p.cobertura_global == 100.0 for p in progresos)
        assert any(p.volumen_actual == str(volumen.ruta_raiz) for p in progresos)
        assert any(p.entradas_procesadas > 0 for p in progresos)

        # Persistencia real en SQLite: las entradas están almacenadas.
        assert storage.count(MACHINE_ID) >= 4
        ultimo = storage.get_latest_scan(MACHINE_ID)
        assert ultimo is not None
        assert ultimo["result"] == SCAN_RESULT_OK
        assert ultimo["entries_count"] >= 4

    def test_cancelar_interrumpe_la_ejecucion(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        # Árbol suficientemente grande para que el escaneo tarde un poco y la
        # cancelación se procese antes de recorrer todos los directorios.
        base = tmp_path / "volumen_cancelar"
        for i in range(20):
            sub = base / f"sub{i:02d}"
            sub.mkdir(parents=True, exist_ok=True)
            for j in range(5):
                (sub / f"archivo_{j:02d}.txt").write_text(
                    f"contenido {i}-{j}\n", encoding="utf-8"
                )
        volumen = VolumeInfo(
            letra="U:",
            ruta_raiz=str(base),
            tipo=VolumeType.FIXED,
            disponible=True,
        )
        gestor = GestorPrimerInventario(MACHINE_ID, storage)

        ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen])
        assert ejecucion.esta_en_ejecucion is True

        # Cancelar inmediatamente.
        ejecucion.solicitar_cancelar()
        assert ejecucion.solicitado_cancelar is True

        assert ejecucion.esperar(timeout=60.0) is True
        resultado = ejecucion.resultado()
        assert resultado is not None
        assert resultado["interrumpido"] is True
        assert ejecucion.progreso.estado == EstadoPrimerInventario.INTERRUMPIDO
        assert ejecucion.progreso.interrumpido is True

    def test_ya_en_ejecucion_levanta_error(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "volumen_ejecucion"
        for i in range(15):
            sub = base / f"sub{i:02d}"
            sub.mkdir(parents=True, exist_ok=True)
            for j in range(5):
                (sub / f"archivo_{j:02d}.txt").write_text(
                    f"contenido {i}-{j}\n", encoding="utf-8"
                )
        volumen = VolumeInfo(
            letra="V:", ruta_raiz=str(base), tipo=VolumeType.FIXED, disponible=True
        )
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        ejecucion1 = gestor.ejecutar_primera_vez(volumenes=[volumen])

        # Debe seguir ejecutándose (árbol grande, no termina al instante).
        assert ejecucion1.esta_en_ejecucion is True

        # Un segundo intento mientras hay uno en curso debe rechazarse.
        with pytest.raises(PrimerInventarioYaEnEjecucionError):
            gestor.ejecutar_primera_vez(volumenes=[volumen])

        ejecucion1.esperar(timeout=60.0)

    def test_ya_completado_no_se_ejecuta_de_nuevo(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        volumen = _volumen_temporal(tmp_path)
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen])
        ejecucion.esperar(timeout=60.0)
        assert ejecucion.progreso.estado == EstadoPrimerInventario.COMPLETADO

        # Un segundo intento debe rechazarse (ya existe scan "ok").
        with pytest.raises(RuntimeError):
            gestor.ejecutar_primera_vez(volumenes=[volumen])

    def test_control_retorna_continuar_por_defecto(self, storage: SystemInventoryStorage):
        gestor = GestorPrimerInventario(MACHINE_ID, storage)
        ejecucion = gestor.ejecutar_primera_vez(volumenes=[])
        # Sin volúmenes, el hilo finaliza casi de inmediato; el control por
        # defecto es CONTINUAR mientras no se pida pausa/cancelar.
        assert ejecucion.control() == ControlRecorrido.CONTINUAR
        ejecucion.solicitar_pausa()
        assert ejecucion.control() == ControlRecorrido.PAUSAR
        ejecucion.solicitar_reanudar()
        assert ejecucion.control() == ControlRecorrido.CONTINUAR
        ejecucion.solicitar_cancelar()
        assert ejecucion.control() == ControlRecorrido.CANCELAR
        ejecucion.esperar(timeout=30.0)


# ---------------------------------------------------------------------------
# Política configurable de refresco y actualizaciones incrementales bajo
# demanda del inventario (unidad 3.8.5.1.4.8.2).
#
# Todos los tests usan bases de datos temporales y rutas reales bajo tmp_path;
# no tocan datos de producción ni rutas de usuario.
# ---------------------------------------------------------------------------

def _entrada_archivo(
    indice: int, ruta_absoluta: str, last_checked_at: str, size_bytes: int = 100
) -> dict:
    return {
        "entry_id": f"e-{indice}-{uuid.uuid4().hex[:8]}",
        "absolute_path": ruta_absoluta,
        "relative_path": Path(ruta_absoluta).name,
        "name": Path(ruta_absoluta).name,
        "extension": Path(ruta_absoluta).suffix,
        "entry_type": EntryType.FILE.value,
        "size_bytes": size_bytes,
        "modified_at": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
        "accessed_at": datetime.now().isoformat(),
        "attributes": [],
        "excluded": False,
        "exclusion_reason": None,
        "source": "filesystem_scan",
        "last_checked_at": last_checked_at,
    }


def _crear_scan_con_entradas(
    storage: SystemInventoryStorage,
    machine_id: str,
    volume: str,
    scan_id: str,
    entradas: list[dict],
) -> None:
    storage.begin_scan_run(scan_id, machine_id, volume, SCAN_MODE_FULL)
    storage.insert_file_entries(scan_id, machine_id, volume, entradas)
    storage.end_scan_run(
        scan_id,
        result=SCAN_RESULT_OK,
        entries_count=len(entradas),
        errors_count=0,
    )


# ---------------------------------------------------------------------------
# Configuración de la política
# ---------------------------------------------------------------------------

class TestPoliticaRefrescoConfig:
    def test_config_por_defecto_es_bajo_demanda(self, storage: SystemInventoryStorage):
        politica = PoliticaRefresco(storage, MACHINE_ID)
        cfg = politica.config_actual()
        assert cfg.modo == ModoRefresco.BAJO_DEMANDA
        assert cfg.ttl_segundos is None
        assert cfg.intervalo_segundos is None
        assert cfg.volumenes_incluir is None
        assert cfg.volumenes_excluir == []
        assert cfg.rutas_incluir is None
        assert cfg.rutas_excluir == []
        assert cfg.max_entradas_por_refresco is None
        assert cfg.refrescar_solo_caducadas is True

    def test_configurar_actualiza_modo_y_ttl(
        self, storage: SystemInventoryStorage
    ):
        politica = PoliticaRefresco(storage, MACHINE_ID)
        politica.configurar(
            ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=7200.0)
        )
        cfg = politica.config_actual()
        assert cfg.modo == ModoRefresco.POR_CADUCIDAD
        assert cfg.ttl_segundos == 7200.0

    def test_config_actual_retorna_copia_independiente(
        self, storage: SystemInventoryStorage
    ):
        politica = PoliticaRefresco(storage, MACHINE_ID)
        cfg = politica.config_actual()
        cfg.modo = ModoRefresco.DESACTIVADO  # mutar la copia devuelta
        assert politica.config_actual().modo == ModoRefresco.BAJO_DEMANDA


# ---------------------------------------------------------------------------
# Decisión de refresco por volumen
# ---------------------------------------------------------------------------

class TestPoliticaRefrescoDecisionVolumen:
    def test_modo_desactivado_nunca_refresca(
        self, storage: SystemInventoryStorage
    ):
        politica = PoliticaRefresco(
            storage, MACHINE_ID, ConfigRefresco(modo=ModoRefresco.DESACTIVADO)
        )
        necesita, motivo, info = politica.necesita_refresco_volumen("C:")
        assert necesita is False
        assert "desactivado" in motivo.lower()
        assert info["modo"] == ModoRefresco.DESACTIVADO.value

    def test_sin_escaneo_previo_no_refresca(
        self, storage: SystemInventoryStorage
    ):
        politica = PoliticaRefresco(storage, MACHINE_ID)
        necesita, motivo, info = politica.necesita_refresco_volumen("C:")
        assert necesita is False
        assert "No hay escaneo previo" in motivo

    def test_volumen_excluido_no_es_elegible(
        self, storage: SystemInventoryStorage
    ):
        politica = PoliticaRefresco(
            storage, MACHINE_ID, ConfigRefresco(volumenes_excluir=["D:"])
        )
        necesita, motivo, info = politica.necesita_refresco_volumen("D:")
        assert necesita is False
        assert "no elegible" in motivo.lower()

    def test_modo_bajo_demanda_nunca_refresca_automaticamente(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_bd"
        base.mkdir()
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        viejo = (datetime.now() - timedelta(seconds=200)).isoformat()
        entradas = [_entrada_archivo(0, str(base / "a.txt"), viejo)]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-bd", entradas)

        politica = PoliticaRefresco(
            storage,
            MACHINE_ID,
            ConfigRefresco(modo=ModoRefresco.BAJO_DEMANDA, ttl_segundos=60.0),
        )
        necesita, motivo, info = politica.necesita_refresco_volumen("C:")
        assert necesita is False
        assert "bajo demanda" in motivo.lower()
        assert info["entradas_caducadas"] == 1  # caducidad detectada, pero sin disparar

    def test_por_caducidad_con_entradas_caducadas_refresca(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_cad"
        base.mkdir()
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        ttl = 60.0
        viejo = (datetime.now() - timedelta(seconds=ttl * 2)).isoformat()
        entradas = [_entrada_archivo(0, str(base / "a.txt"), viejo)]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-cad", entradas)

        politica = PoliticaRefresco(
            storage,
            MACHINE_ID,
            ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=ttl),
        )
        necesita, motivo, info = politica.necesita_refresco_volumen("C:")
        assert necesita is True
        assert info["entradas_caducadas"] == 1
        assert info["entradas_totales"] == 1

    def test_por_caducidad_con_entradas_vigentes_no_refresca(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_vig"
        base.mkdir()
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        ttl = 60.0
        reciente = datetime.now().isoformat()
        entradas = [_entrada_archivo(0, str(base / "a.txt"), reciente)]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-vig", entradas)

        politica = PoliticaRefresco(
            storage,
            MACHINE_ID,
            ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=ttl),
        )
        necesita, motivo, info = politica.necesita_refresco_volumen("C:")
        assert necesita is False
        assert info["entradas_caducadas"] == 0


# ---------------------------------------------------------------------------
# Operaciones de refresco incremental
# ---------------------------------------------------------------------------

class TestPoliticaRefrescoOperaciones:
    def test_refrescar_volumen_si_necesario_no_toca_storage_bajo_demanda(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_nod"
        base.mkdir()
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        recientes = datetime.now().isoformat()
        entradas = [_entrada_archivo(0, str(base / "a.txt"), recientes)]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-nod", entradas)

        politica = PoliticaRefresco(
            storage, MACHINE_ID, ConfigRefresco(modo=ModoRefresco.BAJO_DEMANDA)
        )
        resultado = politica.refrescar_volumen_si_necesario("C:")
        assert resultado.modo == ModoRefresco.BAJO_DEMANDA.value
        assert resultado.entradas_refrescadas == 0
        assert resultado.escaneo_completo_evitado is True
        assert resultado.volume == "C:"

    def test_refrescar_volumen_si_necesario_por_caducidad_actualiza(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_act"
        base.mkdir()
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        ttl = 60.0
        viejo = (datetime.now() - timedelta(seconds=ttl * 2)).isoformat()
        entradas = [_entrada_archivo(0, str(base / "a.txt"), viejo)]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-act", entradas)

        politica = PoliticaRefresco(
            storage,
            MACHINE_ID,
            ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=ttl),
        )
        resultado = politica.refrescar_volumen_si_necesario("C:")
        assert resultado.modo == ModoRefresco.POR_CADUCIDAD.value
        assert resultado.entradas_refrescadas == 1
        assert resultado.escaneo_completo_evitado is True
        assert resultado.last_checked_at is not None
        assert len(politica.historial()) == 1

        # Tras el refresco las entradas están vigentes: no hay que refrescar de nuevo.
        necesita, _, _ = politica.necesita_refresco_volumen("C:")
        assert necesita is False

    def test_refrescar_ruta_bajo_demanda_actualiza_una_ruta(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_ruta"
        base.mkdir()
        ruta = str(base / "a.txt")
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        viejo = (datetime.now() - timedelta(seconds=200)).isoformat()
        entradas = [_entrada_archivo(0, ruta, viejo)]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-ruta", entradas)

        politica = PoliticaRefresco(storage, MACHINE_ID)
        resultado = politica.refrescar_ruta_bajo_demanda(ruta, "C:")
        assert resultado.modo == ModoRefresco.BAJO_DEMANDA.value
        assert resultado.ruta == ruta
        assert resultado.volume == "C:"
        assert resultado.entradas_refrescadas == 1
        assert resultado.escaneo_completo_evitado is True
        assert resultado.detalle.get("existe_ahora") is True  # el archivo real existe
        assert len(politica.historial()) == 1

    def test_refrescar_ruta_excluida_no_refresca(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_excl"
        base.mkdir()
        ruta = str(base / "a.txt")
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        entradas = [
            _entrada_archivo(0, ruta, datetime.now().isoformat())
        ]
        _crear_scan_con_entradas(storage, MACHINE_ID, "C:", "scan-excl", entradas)

        politica = PoliticaRefresco(
            storage, MACHINE_ID, ConfigRefresco(rutas_excluir=[ruta])
        )
        resultado = politica.refrescar_ruta_bajo_demanda(ruta, "C:")
        assert resultado.entradas_refrescadas == 0
        assert "excluida" in (resultado.razon or "").lower()

    def test_refrescar_incremental_selectivo_no_refresca_todos_bajo_demanda(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        for letra, nombre_carpeta in (("C:", "vol_c"), ("D:", "vol_d")):
            base = tmp_path / nombre_carpeta
            base.mkdir()
            (base / "a.txt").write_text("x\n", encoding="utf-8")
            entradas = [
                _entrada_archivo(
                    0, str(base / "a.txt"), datetime.now().isoformat()
                )
            ]
            _crear_scan_con_entradas(storage, MACHINE_ID, letra, f"scan-{letra}", entradas)

        politica = PoliticaRefresco(storage, MACHINE_ID)
        resumen = politica.refrescar_incremental_selectivo(["C:", "D:"])
        assert resumen["modo"] == ModoRefresco.BAJO_DEMANDA.value
        assert resumen["total_volumenes_evaluados"] == 2
        assert resumen["volumenes_refrescados"] == 0
        assert resumen["volumenes_no_necesitaban_refresco"] == 2
        assert resumen["entradas_refrescadas_total"] == 0
        for entrada in resumen["por_volumen"]:
            assert entrada["escaneo_completo_evitado"] is True

    def test_decidir_volumenes_a_refrescar_solo_caducados(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base_c = tmp_path / "vol_c"
        base_c.mkdir()
        (base_c / "a.txt").write_text("x\n", encoding="utf-8")
        viejo = (datetime.now() - timedelta(seconds=200)).isoformat()
        _crear_scan_con_entradas(
            storage,
            MACHINE_ID,
            "C:",
            "scan-c",
            [_entrada_archivo(0, str(base_c / "a.txt"), viejo)],
        )
        base_d = tmp_path / "vol_d"
        base_d.mkdir()
        (base_d / "a.txt").write_text("x\n", encoding="utf-8")
        _crear_scan_con_entradas(
            storage,
            MACHINE_ID,
            "D:",
            "scan-d",
            [_entrada_archivo(0, str(base_d / "a.txt"), datetime.now().isoformat())],
        )

        politica = PoliticaRefresco(
            storage,
            MACHINE_ID,
            ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=60.0),
        )
        a_refrescar = politica.decidir_volumenes_a_refrescar(["C:", "D:"])
        assert a_refrescar == ["C:"]

    def test_historial_registra_operaciones(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        base = tmp_path / "vol_hist"
        base.mkdir()
        (base / "a.txt").write_text("x\n", encoding="utf-8")
        viejo = (datetime.now() - timedelta(seconds=200)).isoformat()
        _crear_scan_con_entradas(
            storage,
            MACHINE_ID,
            "C:",
            "scan-h",
            [_entrada_archivo(0, str(base / "a.txt"), viejo)],
        )

        politica = PoliticaRefresco(
            storage,
            MACHINE_ID,
            ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=60.0),
        )
        assert len(politica.historial()) == 0
        politica.refrescar_volumen_si_necesario("C:")
        assert len(politica.historial()) == 1
        politica.refrescar_ruta_bajo_demanda(str(base / "a.txt"), "C:")
        assert len(politica.historial()) == 2
        ultimo = politica.ultimo_refresco_por_volumen()
        assert "C:" in ultimo
