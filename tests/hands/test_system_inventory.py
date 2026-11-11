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
from pathlib import Path

import pytest

from src.hands.system_inventory import (
    AlcanceInventario,
    ControlRecorrido,
    EntryType,
    EstadoPrimerInventario,
    GestorPrimerInventario,
    InventoryContract,
    PrimerInventarioYaEnEjecucionError,
    ProgresoInventario,
    ProgresoRecorrido,
    RecorridoVolumen,
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
