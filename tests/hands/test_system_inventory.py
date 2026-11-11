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

import os
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
    EscanerRutaVolumen,
    GestorPrimerInventario,
    InventoryContract,
    LimiteRecursos,
    LimiteRendimiento,
    MedidorRecursosSistema,
    MetricaRendimiento,
    ModoRefresco,
    PoliticaRefresco,
    PrimerInventarioYaEnEjecucionError,
    ProgresoInventario,
    ProgresoRecorrido,
    RecorridoVolumen,
    ResultadoEscaneo,
    ResultadoLimpieza,
    ResultadoMedicionRendimiento,
    VolumeInfo,
    VolumeType,
    generate_machine_id,
)
from src.hands.system_inventory import escanear_ruta, escanear_volumen, reconstruir_catalogo
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_MODE_INCREMENTAL,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    MedidorRendimientoInventario,
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


# ---------------------------------------------------------------------------
# Escaneo por volumen o ruta, exclusiones de usuario y reconstruccion
# controlada del catalogo (unidad 3.8.5.1.4.8.3).
#
# Todos los tests usan directorios temporales (tmp_path) y bases de datos
# temporales; no tocan datos de produccion ni rutas de usuario.
# ---------------------------------------------------------------------------

def _arbol_temporal(
    tmp_path: Path, nombre: str = "arbol_scan", nivel_subcarpetas: int = 3
) -> Path:
    """Crea un árbol REAL de directorios y archivos bajo tmp_path."""
    base = tmp_path / nombre
    base.mkdir(parents=True, exist_ok=True)
    (base / "raiz.txt").write_text("raiz\n", encoding="utf-8")
    for i in range(nivel_subcarpetas):
        sub = base / f"sub{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"archivo_{i}.txt").write_text(f"contenido {i}\n", encoding="utf-8")
        profundo = sub / "profundo"
        profundo.mkdir(parents=True, exist_ok=True)
        (profundo / f"anidado_{i}.log").write_text(f"anidado {i}\n", encoding="utf-8")
    (base / "notas.unicode").write_text("caféñ¿\n", encoding="utf-8")
    return base


def _volumen_para_scan(
    tmp_path: Path, letra: str = "T:", nombre: str = "volumen_scan"
) -> tuple[VolumeInfo, Path]:
    base = _arbol_temporal(tmp_path, nombre)
    return (
        VolumeInfo(
            letra=letra,
            ruta_raiz=str(base),
            tipo=VolumeType.FIXED,
            disponible=True,
            sistema_archivos="NTFS",
            etiqueta_volumen="scan",
        ),
        base,
    )


# ---------------------------------------------------------------------------
# Escaneo por volumen o ruta
# ---------------------------------------------------------------------------

class TestEscanerRutaOVolumen:
    """Verifican escaneo por ruta y por volumen sobre almacenamiento real."""

    def test_escanear_ruta_crea_scan_run_e_entradas_reales(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        volumen, base = _volumen_para_scan(tmp_path)
        resultado = escanear_ruta(
            ruta_absoluta=str(base),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert isinstance(resultado, ResultadoEscaneo)
        assert resultado.volumen == os.path.splitdrive(os.path.abspath(str(base)))[0]
        assert resultado.ruta == os.path.abspath(str(base))
        assert resultado.modo == SCAN_MODE_FULL
        assert resultado.resultado == SCAN_RESULT_OK
        assert resultado.completado is True
        assert resultado.interrumpido is False
        assert resultado.entradas_procesadas > 0
        assert resultado.archivos_procesados > 0
        assert resultado.directorios_procesados > 0
        assert resultado.iniciado_en and resultado.finalizado_en

        # Persistencia real: el scan_run y las entradas están en SQLite.
        scan_run = storage.get_scan_run(resultado.scan_id)
        assert scan_run is not None
        assert scan_run["machine_id"] == MACHINE_ID
        assert scan_run["volume"] == os.path.splitdrive(os.path.abspath(str(base)))[0]
        assert scan_run["result"] == SCAN_RESULT_OK
        assert scan_run["entries_count"] == resultado.entradas_procesadas
        assert storage.count(MACHINE_ID) == resultado.entradas_procesadas
        assert storage.get_latest_scan(MACHINE_ID)["scan_id"] == resultado.scan_id

        # Las entradas reflejan el árbol real: archivos .txt y .log existen.
        entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
        nombres = {e["name"] for e in entradas}
        assert "raiz.txt" in nombres
        assert "archivo_0.txt" in nombres
        assert "anidado_0.log" in nombres
        assert "notas.unicode" in nombres  # rutas Unicode registradas

    def test_escanear_volumen_por_raiz_de_volumen(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        volumen, base = _volumen_para_scan(tmp_path, letra="U:")
        resultado = escanear_volumen(
            volumen=volumen.letra,
            ruta_raiz=str(base),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert resultado.resultado == SCAN_RESULT_OK
        assert resultado.volumen == "U:"
        assert resultado.entradas_procesadas > 0
        assert storage.get_scan_run(resultado.scan_id)["volume"] == "U:"

    def test_scan_por_ruta_respeta_exclusiones_de_usuario(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="V:")
        excluida = base / "sub00"
        (excluida / "dentro.txt").write_text("dentro\n", encoding="utf-8")

        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario(str(excluida))

        resultado = escanear_ruta(
            ruta_absoluta=str(base),
            contrato=contrato,
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert resultado.resultado == SCAN_RESULT_OK
        assert resultado.exclusiones >= 1

        # Ninguna entrada dentro de la carpeta excluida por el usuario.
        entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
        rutas = [e["absolute_path"] for e in entradas]
        assert not any(
            r == str(excluida) or r.startswith(str(excluida) + os.sep) for r in rutas
        )
        # Las entradas excluidas llevan el motivo de exclusión de usuario.
        excluidas_db = [e for e in entradas if e["excluded"]]
        assert all(e["exclusion_reason"] == "exclusion_usuario" for e in excluidas_db)
        # Fuera de la exclusión las entradas siguen registradas.
        nombres = {e["name"] for e in entradas}
        assert "raiz.txt" in nombres

    def test_exclusion_usuario_no_desactiva_exclusiones_tecnicas(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="W:")
        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario(str(base / "sub00"))

        resultado = escanear_ruta(
            ruta_absoluta=str(base),
            contrato=contrato,
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert resultado.resultado == SCAN_RESULT_OK
        # $Recycle.Bin (exclusión técnica) sigue estando fuera si estuviera presente;
        # aquí verificamos que el contrato sigue exponiendo ambas listas.
        assert contrato.should_exclude_path(str(base / "sub00" / "dentro.txt"))
        assert contrato.should_exclude_path("C:\\$Recycle.Bin\\algo")
        assert contrato.razon_exclusion(str(base / "sub00" / "dentro.txt")) == (
            "exclusion_usuario"
        )
        assert contrato.razon_exclusion("C:\\$Recycle.Bin\\algo") == (
            "exclusion_tecnica"
        )
        assert contrato.razon_exclusion(str(base / "raiz.txt")) is None

    def test_cancelar_escaneo_por_ruta_preserva_entradas_emitidas(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        # Árbol grande para que el recorrido tarde lo suficiente.
        base = tmp_path / "volumen_cancelar_ruta"
        for i in range(30):
            sub = base / f"sub{i:02d}"
            sub.mkdir(parents=True, exist_ok=True)
            for j in range(8):
                (sub / f"archivo_{j:02d}.txt").write_text(
                    f"contenido {i}-{j}\n", encoding="utf-8"
                )

        llamadas = {"n": 0}

        def control() -> ControlRecorrido:
            llamadas["n"] += 1
            if llamadas["n"] >= 6:
                return ControlRecorrido.CANCELAR
            return ControlRecorrido.CONTINUAR

        resultado = escanear_ruta(
            ruta_absoluta=str(base),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
            callback_control=control,
        )

        # El scan_run se registra con resultado interrumpido y conserva las
        # entradas emitidas antes de la cancelación (no se descartan).
        assert resultado.resultado == SCAN_RESULT_INTERRUPTED
        assert resultado.interrumpido is True
        assert resultado.completado is False
        assert resultado.entradas_procesadas > 0
        scan_run = storage.get_scan_run(resultado.scan_id)
        assert scan_run["result"] == SCAN_RESULT_INTERRUPTED
        assert scan_run["entries_count"] == resultado.entradas_procesadas

    def test_ruta_inexistente_no_aborta_y_registra_error(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        inexistente = str(tmp_path / "no_existe" / "nada")

        resultado = escanear_ruta(
            ruta_absoluta=inexistente,
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert resultado.resultado == SCAN_RESULT_OK
        assert resultado.entradas_procesadas == 0
        assert resultado.errores >= 1
        assert "ruta_eliminada" in resultado.errores_por_categoria

    def test_aislamiento_por_maquina_no_mezcla_inventarios(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="X:")

        escanear_ruta(
            ruta_absoluta=str(base),
            contrato=InventoryContract(machine_id="maquina-a"),
            maquina_id="maquina-a",
            storage=storage,
        )

        # Otra máquina no ve las entradas de la primera.
        assert storage.count("maquina-a") > 0
        assert storage.count("maquina-b") == 0
        assert storage.get_latest_scan("maquina-b") is None

    def test_reconstruir_catalogo_genera_nuevo_scan_run_sin_borrar_historial(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="Y:")

        primera = reconstruir_catalogo(
            volumen="Y:",
            raiz=str(base),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )
        assert primera.resultado == SCAN_RESULT_OK
        assert primera.completado is True

        # Añadir un archivo y reconstruir de nuevo.
        (base / "nuevo_despues.txt").write_text("nuevo\n", encoding="utf-8")
        segunda = reconstruir_catalogo(
            volumen="Y:",
            raiz=str(base),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )
        assert segunda.resultado == SCAN_RESULT_OK
        assert segunda.scan_id != primera.scan_id

        # Ambos scan_runs existen y conservan sus entradas (no destructivo).
        run1 = storage.get_scan_run(primera.scan_id)
        run2 = storage.get_scan_run(segunda.scan_id)
        assert run1["result"] == SCAN_RESULT_OK
        assert run2["result"] == SCAN_RESULT_OK
        assert run2["entries_count"] >= run1["entries_count"]

        # El más reciente es el de la reconstrucción: define el catálogo actual.
        assert storage.get_latest_scan(MACHINE_ID, "Y:")["scan_id"] == segunda.scan_id
        entradas_segunda = storage.obtener_entradas_escaneo(segunda.scan_id)
        nombres = {e["name"] for e in entradas_segunda}
        assert "nuevo_despues.txt" in nombres


# ---------------------------------------------------------------------------
# Exclusiones de ubicaciones elegidas por el usuario (contrato)
# ---------------------------------------------------------------------------

class TestExclusionesUsuarioContrato:
    """Verifican la gestión de exclusiones de usuario en InventoryContract."""

    def test_contrato_inicia_sin_exclusiones_de_usuario(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        assert contrato.obtener_exclusiones_usuario() == []

    def test_agregar_exclusion_usuario_registra_ruta(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario("C:\\Datos del usuario\\Privado")
        assert "C:\\Datos del usuario\\Privado" in contrato.obtener_exclusiones_usuario()

    def test_agregar_exclusion_duplicada_no_se_repite(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        ruta = "C:\\Datos del usuario\\Privado"
        contrato.agregar_exclusion_usuario(ruta)
        contrato.agregar_exclusion_usuario(ruta)
        assert contrato.obtener_exclusiones_usuario().count(ruta) == 1

    def test_quitar_exclusion_usuario_elimina_ruta(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        ruta = "C:\\Datos del usuario\\Privado"
        contrato.agregar_exclusion_usuario(ruta)
        contrato.quitar_exclusion_usuario(ruta)
        assert contrato.obtener_exclusiones_usuario() == []

    def test_limpiar_exclusiones_usuario(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario("C:\\Uno")
        contrato.agregar_exclusion_usuario("C:\\Dos")
        contrato.limpiar_exclusiones_usuario()
        assert contrato.obtener_exclusiones_usuario() == []

    def test_should_exclude_path_detecta_carpeta_excluida_y_contenido(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario("C:\\Excluida")
        assert contrato.should_exclude_path("C:\\Excluida")
        assert contrato.should_exclude_path("C:\\Excluida\\subcarpeta\\archivo.txt")
        assert contrato.should_exclude_path("C:\\Excluida2\\archivo.txt") is False

    def test_should_exclude_path_respeta_mayusculas_segun_so(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario("c:\\excluida")
        assert contrato.should_exclude_path("C:\\Excluida\\archivo.txt")

    def test_razon_exclusion_devuelve_motivo_usuario_o_tecnica(self):
        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario("C:\\Privado")
        assert (
            contrato.razon_exclusion("C:\\Privado\\archivo.txt") == "exclusion_usuario"
        )
        assert (
            contrato.razon_exclusion("C:\\$Recycle.Bin\\algo") == "exclusion_tecnica"
        )
        assert contrato.razon_exclusion("C:\\Público\\archivo.txt") is None

    def test_recorrido_volumen_respeta_exclusion_de_usuario(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="Z:")
        excluida = base / "sub00"
        (excluida / "dentro.txt").write_text("dentro\n", encoding="utf-8")

        contrato = InventoryContract(machine_id=MACHINE_ID)
        contrato.agregar_exclusion_usuario(str(excluida))

        recorrido = RecorridoVolumen(
            volumen="Z:",
            raiz=str(base),
            contrato=contrato,
            maquina_id=MACHINE_ID,
        )
        entradas = list(recorrido.recorrer())

        rutas = [e.absolute_path for e in entradas]
        assert not any(
            r == str(excluida) or r.startswith(str(excluida) + os.sep) for r in rutas
        )
        assert recorrido.progreso.exclusiones >= 1
        for e in entradas:
            if e.excluded:
                assert e.exclusion_reason == "exclusion_usuario"


# ---------------------------------------------------------------------------
# Logs: sin listados completos de nombres/rutas; solo resumenes y errores
# agregados (unidad 3.8.5.1.4.8.5).
# ---------------------------------------------------------------------------

class TestLogsSinRutasCompletas:
    """Verifica que los logs nunca contienen rutas completas ni listados
    de nombres, sino resumenes agregados y evidencia minima para diagnostico."""

    def _capturar_logs(self, accion):
        """Ejecuta `accion` capturando los registros emitidos por el logger
        del modulo y devuelve la lista de mensajes de log."""
        import logging

        registros = []

        class Capturador(logging.Handler):
            def emit(self, record):
                registros.append(record.getMessage())

        logger_mod = logging.getLogger("src.hands.system_inventory")
        logger_mod.setLevel(logging.INFO)
        h = Capturador()
        logger_mod.addHandler(h)
        try:
            accion()
        finally:
            logger_mod.removeHandler(h)
        return registros

    def test_recorrido_log_resumen_no_rutas_completas(self, storage, tmp_path):
        """El recorrido de volumen loguea resumenes (conteos) y nunca la ruta
        completa de la raiz ni listados de entradas."""
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="L:")

        def accion():
            contrato = InventoryContract(machine_id=MACHINE_ID)
            recorrido = RecorridoVolumen(
                volumen="L:",
                raiz=str(base),
                contrato=contrato,
                maquina_id=MACHINE_ID,
            )
            list(recorrido.recorrer())

        registros = self._capturar_logs(accion)
        texto_logs = "\n".join(registros)

        # Debe haber registros de inicio y fin de recorrido.
        assert "Inicio de recorrido" in texto_logs or "Fin de recorrido" in texto_logs

        # Nunca debe aparecer la ruta completa de la raiz en los logs.
        assert str(base) not in texto_logs

        # Debe aparecer el volumen y conteos agregados, no rutas individuales.
        assert "volumen=L:" in texto_logs
        assert "directorios=" in texto_logs
        assert "entradas=" in texto_logs
        assert "errores=" in texto_logs

    def test_errores_log_agregados_por_categoria_no_ruta_completa(
        self, storage, tmp_path
    ):
        """Los errores se loguean agregados por categoria, nunca con la ruta
        completa del archivo/directorio que fallo."""
        storage.initialize()
        # Ruta inexistente: genera un error de tipo "ruta_eliminada".
        inexistente = str(tmp_path / "no_existe" / "nada")

        def accion():
            contrato = InventoryContract(machine_id=MACHINE_ID)
            escanear_ruta(
                ruta_absoluta=inexistente,
                contrato=contrato,
                maquina_id=MACHINE_ID,
                storage=storage,
            )

        registros = self._capturar_logs(accion)
        texto_logs = "\n".join(registros)

        # Debe haber registro de error agregado por categoria.
        assert "categoria=" in texto_logs or "Error de recorrido" in texto_logs

        # Nunca la ruta completa inexistente en los logs.
        assert inexistente not in texto_logs

    def test_escanear_ruta_log_inicio_y_fin_con_evidencia_minima(
        self, storage, tmp_path
    ):
        """escanear_ruta loguea inicio y fin con evidencia minima (scan_id,
        volumen, modo, resultado, conteos) y nunca rutas completas."""
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="M:")

        def accion():
            contrato = InventoryContract(machine_id=MACHINE_ID)
            escanear_ruta(
                ruta_absoluta=str(base),
                contrato=contrato,
                maquina_id=MACHINE_ID,
                storage=storage,
            )

        registros = self._capturar_logs(accion)
        texto_logs = "\n".join(registros)

        # Evidencia minima de diagnostico.
        assert "scan_id=" in texto_logs
        assert "volumen=" in texto_logs
        assert "resultado=" in texto_logs
        assert "entradas=" in texto_logs

        # Nunca la ruta completa escaneada.
        assert str(base) not in texto_logs

    def test_politica_refresco_log_resumen_no_rutas(
        self, storage, tmp_path
    ):
        """La politica de refresco loguea resumenes agregados (volumen, modo,
        entradas_refrescadas, cambios) y nunca rutas completas."""
        storage.initialize()
        _, base = _volumen_para_scan(tmp_path, letra="N:")

        # Crear un escaneo previo para que la politica tenga algo que evaluar.
        escanear_volumen(
            volumen="N:",
            ruta_raiz=str(base),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
            modo="completo",
        )

        from src.hands.system_inventory import PoliticaRefresco, ModoRefresco, ConfigRefresco

        def accion():
            politica = PoliticaRefresco(
                storage=storage,
                machine_id=MACHINE_ID,
                config=ConfigRefresco(modo=ModoRefresco.POR_CADUCIDAD, ttl_segundos=1),
            )
            politica.refrescar_volumen_si_necesario("N:")

        registros = self._capturar_logs(accion)
        texto_logs = "\n".join(registros)

        # Debe haber registro de decision de refresco.
        assert "Refresco no necesario" in texto_logs or "Refresco volumen" in texto_logs

        # Nunca rutas completas en los logs de refresco.
        assert str(base) not in texto_logs

    def test_safe_log_path_acorta_rutas_largas(self):
        """safe_log_path devuelve una version acortada de rutas largas para
        logs, nunca la ruta completa."""
        from src.hands.system_inventory import safe_log_path

        ruta_larga = "C:\\Usuarios\\Usuario\\Documentos\\Proyectos\\JARVIS\\src\\hands\\system_inventory.py"
        acortada = safe_log_path(ruta_larga)

        assert acortada != ruta_larga
        assert len(acortada) < len(ruta_larga)
        assert "system_inventory.py" in acortada

        # Rutas cortas no se truncan.
        ruta_corta = "C:\\temp.txt"
        assert safe_log_path(ruta_corta) == ruta_corta


# ---------------------------------------------------------------------------
# Politica de retencion y limpieza (3.8.5.1.4.8.6).
# ---------------------------------------------------------------------------

class TestPoliticaRetencion:
    """PoliticaRetencion: valores por defecto y validaciones de entrada."""

    def test_valores_por_defecto(self):
        from src.hands.system_inventory import PoliticaRetencion

        p = PoliticaRetencion()
        assert p.max_generaciones_por_volumen == 5
        assert p.max_edad_generacion_segundos is None
        assert p.max_edad_entrada_segundos is None
        assert p.max_backups == 3
        assert p.modo_seguro_escaneo_parcial is True
        assert p.crear_backup_antes_limpieza is True

    def test_max_generaciones_debe_ser_al_menos_uno(self):
        from src.hands.system_inventory import PoliticaRetencion

        with pytest.raises(ValueError):
            PoliticaRetencion(max_generaciones_por_volumen=0)
        with pytest.raises(ValueError):
            PoliticaRetencion(max_generaciones_por_volumen=-1)

    def test_max_backups_debe_ser_al_menos_uno(self):
        from src.hands.system_inventory import PoliticaRetencion

        with pytest.raises(ValueError):
            PoliticaRetencion(max_backups=0)

    def test_edades_deben_ser_positivas_o_none(self):
        from src.hands.system_inventory import PoliticaRetencion

        with pytest.raises(ValueError):
            PoliticaRetencion(max_edad_generacion_segundos=0)
        with pytest.raises(ValueError):
            PoliticaRetencion(max_edad_entrada_segundos=-5)
        # None y positivos son validos.
        PoliticaRetencion(max_edad_generacion_segundos=None)
        PoliticaRetencion(max_edad_entrada_segundos=None)
        PoliticaRetencion(max_edad_generacion_segundos=3600, max_edad_entrada_segundos=7200)

    def test_valores_personalizados(self):
        from src.hands.system_inventory import PoliticaRetencion

        p = PoliticaRetencion(
            max_generaciones_por_volumen=2,
            max_edad_generacion_segundos=86400,
            max_edad_entrada_segundos=172800,
            max_backups=1,
            modo_seguro_escaneo_parcial=False,
            crear_backup_antes_limpieza=False,
        )
        assert p.max_generaciones_por_volumen == 2
        assert p.max_edad_generacion_segundos == 86400
        assert p.max_edad_entrada_segundos == 172800
        assert p.max_backups == 1
        assert p.modo_seguro_escaneo_parcial is False
        assert p.crear_backup_antes_limpieza is False


class TestResultadoLimpieza:
    """ResultadoLimpieza: estructura de resumen y contadores."""

    def test_valores_por_defecto(self):
        from src.hands.system_inventory import ResultadoLimpieza

        r = ResultadoLimpieza(machine_id="maquina-1")
        assert r.machine_id == "maquina-1"
        assert r.generaciones_eliminadas == 0
        assert r.entradas_eliminadas == 0
        assert r.backups_eliminados == 0
        assert r.backup_creado is None
        assert r.generaciones_protegidas == []
        assert r.entradas_protegidas == 0
        assert r.errores == []

    def test_resumen_incluye_total_eliminado(self):
        from src.hands.system_inventory import ResultadoLimpieza

        r = ResultadoLimpieza(machine_id="maquina-1")
        r.generaciones_eliminadas = 2
        r.entradas_eliminadas = 5
        r.backups_eliminados = 1
        res = r.resumen()
        assert res["machine_id"] == "maquina-1"
        assert res["total_eliminado"] == 8
        assert res["backup_creado"] is None
        assert res["errores"] == []

    def test_resumen_serializable(self):
        from src.hands.system_inventory import ResultadoLimpieza
        import json

        r = ResultadoLimpieza(machine_id="maquina-1")
        r.generaciones_protegidas = ["scan-1", "scan-2"]
        r.errores = ["error de ejemplo"]
        json.dumps(r.resumen())  # no debe lanzar


# ---------------------------------------------------------------------------
# Medición de rendimiento del inventario (3.8.5.1.4.8.7)
# ---------------------------------------------------------------------------

class TestMedicionRendimientoInventario:
    """Tests de la medición de rendimiento del inventario.

    Verifican que MedidorRendimientoInventario mide tiempo, CPU, memoria,
    lecturas de disco, crecimiento de SQLite y rendimiento de consultas
    usando implementación real sobre bases de datos temporales.
    """

    def test_medir_operacion_registra_tiempo_y_recursos(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        medidor = MedidorRendimientoInventario(storage)

        def operacion():
            # Operación real: escribir entradas en SQLite
            storage.begin_scan_run("scan-test-1", MACHINE_ID, "C:", SCAN_MODE_FULL)
            storage.insert_file_entries(
                "scan-test-1",
                MACHINE_ID,
                "C:",
                [
                    {
                        "entry_id": "e1",
                        "absolute_path": "C:/test/archivo.txt",
                        "relative_path": "test/archivo.txt",
                        "name": "archivo.txt",
                        "extension": ".txt",
                        "entry_type": EntryType.FILE.value,
                        "size_bytes": 100,
                        "modified_at": "2026-01-01T00:00:00",
                        "created_at": "2026-01-01T00:00:00",
                        "accessed_at": None,
                        "attributes": [],
                        "excluded": False,
                        "source": "filesystem_scan",
                        "last_checked_at": "2026-01-01T00:00:00",
                    }
                ],
            )
            storage.end_scan_run("scan-test-1", result=SCAN_RESULT_OK, entries_count=1)

        metrica = medidor.medir_operacion("insert_file_entries", operacion)

        assert metrica.operacion == "insert_file_entries"
        assert metrica.tiempo_segundos >= 0
        assert 0 <= metrica.cpu_antes_porcentaje <= 100
        assert 0 <= metrica.cpu_despues_porcentaje <= 100
        assert 0 <= metrica.memoria_antes_porcentaje <= 100
        assert 0 <= metrica.memoria_despues_porcentaje <= 100
        assert metrica.lecturas_disco_antes >= 0
        assert metrica.lecturas_disco_despues >= 0
        assert metrica.tamaño_db_antes_bytes >= 0
        assert metrica.tamaño_db_despues_bytes >= 0
        # La base de datos debe haber crecido al insertar entradas
        assert metrica.crecimiento_db_bytes >= 0

    def test_medir_operacion_propiedades_calculadas(
        self, storage: SystemInventoryStorage
    ):
        medidor = MedidorRendimientoInventario(storage)

        def operacion():
            pass

        metrica = medidor.medir_operacion("no_op", operacion)

        # cpu_delta = despues - antes
        assert metrica.cpu_delta_porcentaje == (
            metrica.cpu_despues_porcentaje - metrica.cpu_antes_porcentaje
        )
        # memoria_delta = despues - antes
        assert metrica.memoria_delta_porcentaje == (
            metrica.memoria_despues_porcentaje - metrica.memoria_antes_porcentaje
        )
        # lecturas_disco_delta = max(0, despues - antes)
        assert metrica.lecturas_disco_delta == max(
            0, metrica.lecturas_disco_despues - metrica.lecturas_disco_antes
        )
        # crecimiento_db = max(0, despues - antes)
        assert metrica.crecimiento_db_bytes == max(
            0, metrica.tamaño_db_despues_bytes - metrica.tamaño_db_antes_bytes
        )

    def test_medir_consulta_registra_tiempo_ms(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        medidor = MedidorRendimientoInventario(storage)

        storage.begin_scan_run("scan-test-2", MACHINE_ID, "C:", SCAN_MODE_FULL)
        storage.insert_file_entries(
            "scan-test-2",
            MACHINE_ID,
            "C:",
            [
                {
                    "entry_id": "e1",
                    "absolute_path": "C:/test/documento.pdf",
                    "relative_path": "test/documento.pdf",
                    "name": "documento.pdf",
                    "extension": ".pdf",
                    "entry_type": EntryType.FILE.value,
                    "size_bytes": 200,
                    "modified_at": "2026-01-01T00:00:00",
                    "created_at": "2026-01-01T00:00:00",
                    "accessed_at": None,
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2026-01-01T00:00:00",
                }
            ],
        )
        storage.end_scan_run("scan-test-2", result=SCAN_RESULT_OK, entries_count=1)

        def consulta():
            return storage.search_by_name(MACHINE_ID, "documento.pdf")

        metrica = medidor.medir_consulta("search_by_name_documento", consulta)

        assert metrica.operacion == "consulta:search_by_name_documento"
        assert metrica.consulta_nombre == "search_by_name_documento"
        assert metrica.consulta_tiempo_ms is not None
        assert metrica.consulta_tiempo_ms >= 0
        assert metrica.tiempo_segundos >= 0

    def test_agregar_medicion_acumula_resultados(
        self, storage: SystemInventoryStorage
    ):
        medidor = MedidorRendimientoInventario(storage)

        resultado_inicial = ResultadoMedicionRendimiento(
            metricas=[],
            tiempo_total_segundos=0.0,
            cpu_promedio_porcentaje=0.0,
            memoria_pico_porcentaje=0.0,
            lecturas_disco_total=0,
            crecimiento_db_bytes=0,
            consultas_medidadas={},
            limites_sugeridos=[],
        )

        m1 = MetricaRendimiento(
            operacion="op1",
            tiempo_segundos=1.5,
            cpu_antes_porcentaje=10.0,
            cpu_despues_porcentaje=20.0,
            memoria_antes_porcentaje=30.0,
            memoria_despues_porcentaje=40.0,
            lecturas_disco_antes=100,
            lecturas_disco_despues=150,
            tamaño_db_antes_bytes=1000,
            tamaño_db_despues_bytes=1200,
        )

        resultado = medidor.agregar_medicion(resultado_inicial, m1)

        assert len(resultado.metricas) == 1
        assert resultado.tiempo_total_segundos == 1.5
        assert resultado.cpu_promedio_porcentaje == 20.0
        assert resultado.memoria_pico_porcentaje == 40.0
        assert resultado.lecturas_disco_total == 50
        assert resultado.crecimiento_db_bytes == 200

        m2 = MetricaRendimiento(
            operacion="op2",
            tiempo_segundos=0.5,
            cpu_antes_porcentaje=5.0,
            cpu_despues_porcentaje=15.0,
            memoria_antes_porcentaje=25.0,
            memoria_despues_porcentaje=35.0,
            lecturas_disco_antes=200,
            lecturas_disco_despues=210,
            tamaño_db_antes_bytes=1200,
            tamaño_db_despues_bytes=1250,
            consulta_nombre="consulta_x",
            consulta_tiempo_ms=5.0,
        )

        resultado2 = medidor.agregar_medicion(resultado, m2)

        assert len(resultado2.metricas) == 2
        assert resultado2.tiempo_total_segundos == 2.0
        assert resultado2.cpu_promedio_porcentaje == 17.5  # (20+15)/2
        assert resultado2.memoria_pico_porcentaje == 40.0  # max(40, 35)
        assert resultado2.lecturas_disco_total == 60  # 50 + 10
        assert resultado2.crecimiento_db_bytes == 250  # 200 + 50
        assert resultado2.consultas_medidadas == {"consulta_x": 5.0}

    def test_establecer_limites_desde_mediciones_no_son_inventados(
        self, storage: SystemInventoryStorage
    ):
        medidor = MedidorRendimientoInventario(storage)

        metricas = [
            MetricaRendimiento(
                operacion="op1",
                tiempo_segundos=0.5,
                cpu_antes_porcentaje=10.0,
                cpu_despues_porcentaje=15.0,
                memoria_antes_porcentaje=20.0,
                memoria_despues_porcentaje=25.0,
                lecturas_disco_antes=100,
                lecturas_disco_despues=110,
                tamaño_db_antes_bytes=1000,
                tamaño_db_despues_bytes=1050,
                consulta_nombre="c1",
                consulta_tiempo_ms=2.0,
            ),
            MetricaRendimiento(
                operacion="op2",
                tiempo_segundos=1.0,
                cpu_antes_porcentaje=12.0,
                cpu_despues_porcentaje=18.0,
                memoria_antes_porcentaje=22.0,
                memoria_despues_porcentaje=28.0,
                lecturas_disco_antes=200,
                lecturas_disco_despues=230,
                tamaño_db_antes_bytes=1050,
                tamaño_db_despues_bytes=1100,
                consulta_nombre="c2",
                consulta_tiempo_ms=5.0,
            ),
        ]

        limites = medidor.establecer_limites_desde_mediciones(
            metricas, factor_seguridad=2.0
        )

        nombres = {l.nombre for l in limites}
        assert "tiempo_maximo_operacion_segundos" in nombres
        assert "cpu_maximo_operacion_porcentaje" in nombres
        assert "memoria_maxima_operacion_porcentaje" in nombres
        assert "lecturas_disco_maximo_por_operacion" in nombres
        assert "crecimiento_sqlite_maximo_bytes_por_operacion" in nombres
        assert "tiempo_maximo_consulta_ms" in nombres

        # Cada límite debe tener un origen que referencia mediciones reales
        for limite in limites:
            assert limite.valor > 0
            assert limite.unidad
            assert "mediciones reales" in limite.origen or "observado" in limite.origen

        # El límite de tiempo debe ser 2x el máximo observado (1.0s)
        limite_tiempo = next(l for l in limites if l.nombre == "tiempo_maximo_operacion_segundos")
        assert limite_tiempo.valor == 2.0  # 1.0 * 2.0

        # El límite de consulta debe ser 2x el máximo observado (5.0ms)
        limite_consulta = next(l for l in limites if l.nombre == "tiempo_maximo_consulta_ms")
        assert limite_consulta.valor == 10.0  # 5.0 * 2.0

    def test_establecer_limites_lista_vacia_retorna_vacia(
        self, storage: SystemInventoryStorage
    ):
        medidor = MedidorRendimientoInventario(storage)
        assert medidor.establecer_limites_desde_mediciones([]) == []

    def test_crear_limite_recursos_desde_medicion(
        self, storage: SystemInventoryStorage
    ):
        medidor = MedidorRendimientoInventario(storage)

        metrica = MetricaRendimiento(
            operacion="op",
            tiempo_segundos=0.3,
            cpu_antes_porcentaje=10.0,
            cpu_despues_porcentaje=20.0,
            memoria_antes_porcentaje=30.0,
            memoria_despues_porcentaje=40.0,
            lecturas_disco_antes=100,
            lecturas_disco_despues=110,
            tamaño_db_antes_bytes=1000,
            tamaño_db_despues_bytes=1050,
        )

        limite = medidor.crear_limite_recursos_desde_medicion(
            metrica, factor_seguridad=2.0
        )

        assert limite is not None
        assert limite.cpu_max_porcentaje == 40.0  # 20.0 * 2.0
        assert limite.memoria_max_porcentaje == 80.0  # 40.0 * 2.0
        assert 0 <= limite.disco_uso_max_porcentaje <= 100
        assert limite.concurrencia_maxima == 1
        assert limite.intervalo_medicion_segundos == 1.0

    def test_resultado_medicion_resumen_serializable(
        self, storage: SystemInventoryStorage
    ):
        import json

        medidor = MedidorRendimientoInventario(storage)

        resultado = ResultadoMedicionRendimiento(
            metricas=[],
            tiempo_total_segundos=0.0,
            cpu_promedio_porcentaje=0.0,
            memoria_pico_porcentaje=0.0,
            lecturas_disco_total=0,
            crecimiento_db_bytes=0,
            consultas_medidadas={},
            limites_sugeridos=[
                LimiteRendimiento(
                    nombre="test_limite",
                    valor=1.5,
                    unidad="segundos",
                    origen="medicion real de prueba",
                )
            ],
        )

        resumen = resultado.resumen()
        json.dumps(resumen)  # no debe lanzar
        assert resumen["operaciones_medidas"] == 0
        assert len(resumen["limites_sugeridos"]) == 1
        assert resumen["limites_sugeridos"][0]["nombre"] == "test_limite"


# ---------------------------------------------------------------------------
# Responsividad y ejecucion de acciones durante un escaneo (unidad 3.8.5.1.4.8.8).
#
# Verifica que JARVIS puede seguir respondiendo y ejecutar acciones mientras
# un escaneo esta pausado, limitado o ejecutandose en segundo plano controlado.
# Todos los tests usan directorios temporales y bases de datos temporales;
# no tocan datos de produccion ni rutas de usuario.
# ---------------------------------------------------------------------------

class TestAccionRespuestaDuranteEscaneo:
    """JARVIS sigue respondiendo durante un escaneo de inventario."""

    def test_escaneo_segundo_plano_permite_consultas_estado(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        """Mientras un escaneo corre en segundo plano (hilo daemon, no bloqueante),
        se puede consultar progreso, control y estado sin bloquear."""
        volumen = _volumen_temporal(tmp_path)
        gestor = GestorPrimerInventario(MACHINE_ID, storage)

        ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen])
        assert ejecucion.esta_en_ejecucion is True

        # Mientras el escaneo corre, JARVIS puede consultar estado repetidamente.
        consultas = 0
        for _ in range(50):
            if not ejecucion.esta_en_ejecucion:
                break
            prog = ejecucion.progreso
            ctrl = ejecucion.control()
            assert ctrl in (
                ControlRecorrido.CONTINUAR,
                ControlRecorrido.PAUSAR,
                ControlRecorrido.CANCELAR,
            )
            assert prog.estado == EstadoPrimerInventario.EJECUTANDOSE
            consultas += 1
            time.sleep(0.02)

        assert consultas > 0, "No se pudo consultar estado durante el escaneo en segundo plano"

        ejecucion.esperar(timeout=60.0)
        assert ejecucion.finalizado is True
        assert ejecucion.progreso.completado is True

    def test_pausa_reanudar_durante_escaneo_permite_responder(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        """Con el escaneo pausado, JARVIS sigue respondiendo (consultas y control);
        al reanudar, el escaneo continua."""
        base = tmp_path / "volumen_pausa"
        for i in range(8):
            sub = base / f"sub{i:02d}"
            sub.mkdir(parents=True, exist_ok=True)
            for j in range(3):
                (sub / f"archivo_{j:02d}.txt").write_text(
                    f"contenido {i}-{j}\n", encoding="utf-8"
                )
        volumen = VolumeInfo(
            letra="P:", ruta_raiz=str(base), tipo=VolumeType.FIXED, disponible=True
        )
        gestor = GestorPrimerInventario(MACHINE_ID, storage)

        ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen])
        assert ejecucion.esta_en_ejecucion is True

        # Pausar el escaneo.
        ejecucion.solicitar_pausa()
        assert ejecucion.solicitado_pausa is True
        assert ejecucion.control() == ControlRecorrido.PAUSAR

        # Mientras esta pausado, sigue respondiendo a consultas de estado.
        consultas_pausado = 0
        for _ in range(20):
            prog = ejecucion.progreso
            ctrl = ejecucion.control()
            assert ctrl == ControlRecorrido.PAUSAR
            assert prog.estado == EstadoPrimerInventario.EJECUTANDOSE
            consultas_pausado += 1
            time.sleep(0.02)
        assert consultas_pausado > 0

        # Reanudar y verificar que continua.
        ejecucion.solicitar_reanudar()
        assert ejecucion.solicitado_pausa is False
        assert ejecucion.control() == ControlRecorrido.CONTINUAR

        ejecucion.esperar(timeout=60.0)
        assert ejecucion.finalizado is True

    def test_recorrido_volumen_con_limite_recursos_completa_recorrido(
        self, tmp_path: Path
    ):
        """RecorridoVolumen acepta un LimiteRecursos y completa el recorrido
        sobre un directorio temporal real, permitiendo consultar progreso."""
        from src.hands.system_inventory import (
            ControlRecorrido,
            InventoryContract,
            LimiteRecursos,
            MedidorRecursosSistema,
            RecorridoVolumen,
            generate_machine_id,
        )

        base = tmp_path / "volumen_limite"
        for i in range(4):
            sub = base / f"sub{i:02d}"
            sub.mkdir(parents=True, exist_ok=True)
            (sub / f"archivo_{i:02d}.txt").write_text(f"contenido {i}\n")

        contrato = InventoryContract(machine_id=generate_machine_id())
        maquina_id = generate_machine_id()
        limite = LimiteRecursos(
            cpu_max_porcentaje=None,
            memoria_max_porcentaje=None,
            disco_uso_max_porcentaje=None,
            concurrencia_maxima=1,
            intervalo_medicion_segundos=0.05,
        )

        decisiones_control: list[ControlRecorrido] = []

        def callback_control() -> ControlRecorrido:
            decisiones_control.append(ControlRecorrido.CONTINUAR)
            return ControlRecorrido.CONTINUAR

        progresos: list = []

        def callback_progreso(progreso) -> None:
            progresos.append(progreso)

        recorrido = RecorridoVolumen(
            volumen="C:",
            raiz=str(base),
            contrato=contrato,
            maquina_id=maquina_id,
            callback_progreso=callback_progreso,
            callback_control=callback_control,
            limite_recursos=limite,
            medidor_recursos=MedidorRecursosSistema(),
        )

        entradas = list(recorrido.recorrer())
        assert len(entradas) > 0
        assert recorrido.progreso.completado is True
        assert recorrido.progreso.interrumpido is False
        assert len(decisiones_control) > 0, "El callback de control se invoco durante el recorrido"
        assert len(progresos) > 0, "Se recibio progreso durante el recorrido"

    def test_ejecutor_responde_durante_escaneo_segundo_plano(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        """Mientras un escaneo corre en segundo plano, el Executor puede
        crearse y responder consultas (listar acciones) sin bloqueo."""
        from src.hands.executor import Executor

        volumen = _volumen_temporal(tmp_path)
        gestor = GestorPrimerInventario(MACHINE_ID, storage)

        ejecucion = gestor.ejecutar_primera_vez(volumenes=[volumen])
        assert ejecucion.esta_en_ejecucion is True

        # Mientras el escaneo corre, crear un Executor y consultar acciones
        # disponibles demuestra que JARVIS sigue respondiendo.
        executor = Executor()
        acciones = executor.action_registry.list_actions()
        assert isinstance(acciones, list)
        assert len(acciones) > 0

        # El ejecutor puede consultar si una acción existe sin ejecutarla.
        nombre = acciones[0]
        info = executor.action_registry.get_action(nombre)
        assert info is not None
        assert info.name == nombre

        ejecucion.esperar(timeout=60.0)
        assert ejecucion.finalizado is True
