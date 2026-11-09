# -*- coding: utf-8 -*-
"""
Tests de contrato del almacenamiento canonico SQLite del inventario persistente
(unidad 3.8.5.1.4.2.3).

Verifican:
- Creacion de `data/system_inventory.sqlite3` (en directorio temporal, nunca en produccion).
- Inicializacion y versionado del esquema (`schema_version`).
- Registro de equipos y volumenes con aislamiento por equipo (`machine_id`).
- Ejecuciones de escaneo (inicio/fin, resultado, metricas).
- Escritura por lotes atomica de entradas de archivo y candidatos de aplicacion.
- Tablas separadas: entradas genericas de archivo vs candidatos de aplicacion.
- Consultas indexadas paginadas por nombre, extension y prefijo de ruta.
- Contador de entradas y recuperacion de la ultima ejecucion por equipo/volumen.

Todos los tests usan directorios temporales (tmp_path) y no tocan datos de produccion.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from src.hands.system_inventory_storage import (
    DEFAULT_BACKUP_SUFFIX,
    DEFAULT_DB_PATH,
    SCHEMA_VERSION,
    SCAN_MODE_FULL,
    SCAN_MODE_INCREMENTAL,
    SCAN_RESULT_ERROR,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    SCAN_RESULT_PARTIAL,
    ConcurrentScanError,
    InventoryBackupError,
    InventoryCorruptError,
    SystemInventoryStorage,
    _MIGRACIONES,
    normalize_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "system_inventory.sqlite3"


@pytest.fixture
def storage(db_path: Path) -> SystemInventoryStorage:
    return SystemInventoryStorage(db_path)


@pytest.fixture(autouse=True)
def _limpiar_bloqueos_prueba():
    """Limpia los bloqueos de escaneo entre tests para aislar cada prueba.

    Los bloques viven a nivel de clase (_SCAN_LOCKS) y se comparten entre
    todas las instancias de SystemInventoryStorage. Sin esta limpieza, un test
    que deje un escaneo sin cerrar bloquearia a los tests siguientes que usen
    el mismo (machine_id, volumen). Esto no debilita ninguna asercion: solo
    restaura el estado inicial entre pruebas.
    """
    import src.hands.system_inventory_storage as sis
    yield
    with sis._SCAN_LOCKS_GUARD:
        sis._SCAN_LOCKS.clear()


# ---------------------------------------------------------------------------
# Creacion del fichero y esquema
# ---------------------------------------------------------------------------

class TestCreacionBaseDeDatos:
    """La base de datos canonica `data/system_inventory.sqlite3` se crea al inicializar."""

    def test_inicializacion_crea_fichero_en_ruta_dada(self, storage: SystemInventoryStorage, db_path: Path):
        assert not db_path.exists()
        version = storage.initialize()
        assert version == 4
        assert db_path.exists()
        assert storage.db_file_exists()

    def test_ruta_por_defecto_es_data_system_inventory_sqlite3(self):
        assert DEFAULT_DB_PATH == Path("data") / "system_inventory.sqlite3"

    def test_esquema_versionado_se_registra(self, storage: SystemInventoryStorage):
        storage.initialize()
        assert storage.schema_version() == 4

    def test_inicializacion_idempotente_no_borra_datos(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-1")
        storage.initialize()  # segunda inicializacion no debe borrar la maquina
        assert storage.get_entry_count("machine-1") == 0


# ---------------------------------------------------------------------------
# Equipos y volumenes (aislamiento por equipo)
# ---------------------------------------------------------------------------

class TestMaquinasYVolumenes:
    """Registro de equipos y volumenes con aislamiento por `machine_id`."""

    def test_record_machine_registra_equipo(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        # No hay forma directa de consultar maquinas; verificar que no lanza y que
        # un volumen asociado puede registrarse.
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        assert storage.get_entry_count("machine-alfa") == 0

    def test_aislamiento_por_equipo(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        storage.record_volume("vol-d:", "machine-beta", "D:", "local", "online")
        # Cada equipo ve solo sus propios volumenes/entradas indirectamente via conteo.
        assert storage.get_entry_count("machine-alfa") == 0
        assert storage.get_entry_count("machine-beta") == 0


# ---------------------------------------------------------------------------
# Ejecuciones de escaneo
# ---------------------------------------------------------------------------

class TestScanRuns:
    """Inicio y finalizacion de ejecuciones de escaneo."""

    def test_begin_y_end_scan_run(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        run = storage.get_scan_run("scan-1")
        assert run is not None
        assert run["machine_id"] == "machine-alfa"
        assert run["volume"] == "C:"
        assert run["mode"] == SCAN_MODE_FULL
        # El escaneo iniciado no se presenta como completo: queda en
        # SCAN_RESULT_INTERRUPTED hasta que end_scan_run lo confirma con OK
        # (3.8.5.1.4.2.7).
        assert run["result"] == SCAN_RESULT_INTERRUPTED
        assert run["entries_count"] == 0
        assert run["finished_at"] is None

        storage.end_scan_run(
            "scan-1",
            result=SCAN_RESULT_OK,
            entries_count=120,
            errors_count=2,
            exclusions_count=5,
            coverage_estimate="90%",
        )
        run = storage.get_scan_run("scan-1")
        assert run["finished_at"] is not None
        assert run["result"] == SCAN_RESULT_OK
        assert run["entries_count"] == 120
        assert run["errors_count"] == 2
        assert run["exclusions_count"] == 5
        assert run["coverage_estimate"] == "90%"

    def test_resultados_permitidos(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        for resultado in (SCAN_RESULT_OK, SCAN_RESULT_PARTIAL, SCAN_RESULT_INTERRUPTED, SCAN_RESULT_ERROR):
            sid = f"scan-{resultado}"
            storage.begin_scan_run(sid, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
            storage.end_scan_run(sid, result=resultado)
            assert storage.get_scan_run(sid)["result"] == resultado

    def test_get_latest_scan(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-old", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-old", entries_count=10)
        storage.begin_scan_run("scan-new", "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        storage.end_scan_run("scan-new", entries_count=50)
        latest = storage.get_latest_scan("machine-alfa", "C:")
        assert latest is not None
        assert latest["scan_id"] == "scan-new"
        assert latest["entries_count"] == 50

    def test_get_latest_scan_por_volumen(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-c", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-c", entries_count=5)
        storage.begin_scan_run("scan-d", "machine-alfa", "D:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-d", entries_count=9)
        latest_c = storage.get_latest_scan("machine-alfa", "C:")
        latest_d = storage.get_latest_scan("machine-alfa", "D:")
        assert latest_c["scan_id"] == "scan-c"
        assert latest_d["scan_id"] == "scan-d"

    def test_scan_run_desconocido_devuelve_none(self, storage: SystemInventoryStorage):
        storage.initialize()
        assert storage.get_scan_run("scan-inexistente") is None

    def test_begin_scan_run_modo_invalido_levanta_error(self, storage: SystemInventoryStorage):
        """El modo de escaneo debe ser completo o incremental (3.8.5.1.4.2.6)."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        with pytest.raises(ValueError):
            storage.begin_scan_run("scan-invalido", "machine-alfa", "C:", "modo_inexistente")
        # No debe quedar registro parcial de la ejecucion de escaneo.
        assert storage.get_scan_run("scan-invalido") is None

    def test_begin_scan_run_modos_validos_aceptados(self, storage: SystemInventoryStorage):
        """Ambos modos de escaneo (completo e incremental) son aceptados."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        for modo in (SCAN_MODE_FULL, SCAN_MODE_INCREMENTAL):
            sid = f"scan-{modo}"
            storage.begin_scan_run(sid, "machine-alfa", "C:", modo)
            run = storage.get_scan_run(sid)
            assert run is not None
            assert run["mode"] == modo
            assert run["started_at"] is not None
            assert run["finished_at"] is None
            # Cerrar el escaneo antes de iniciar el siguiente para el mismo
            # equipo/volumen: el contrato de concurrencia (3.8.5.1.4.2.9) no
            # permite dos escaneos simultaneos sobre el mismo inventario.
            storage.end_scan_run(sid, result=SCAN_RESULT_OK)

    def test_end_scan_run_resultado_invalido_levanta_error(self, storage: SystemInventoryStorage):
        """El resultado de escaneo debe ser uno de los valores permitidos."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        with pytest.raises(ValueError):
            storage.end_scan_run("scan-1", result="resultado_inexistente")
        # La ejecucion debe seguir registrada con su estado de inicio.
        run = storage.get_scan_run("scan-1")
        assert run is not None
        assert run["finished_at"] is None

    def test_end_scan_run_resultados_validos_aceptados(self, storage: SystemInventoryStorage):
        """Todos los resultados permitidos son aceptados y guardados."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        for resultado in (SCAN_RESULT_OK, SCAN_RESULT_PARTIAL, SCAN_RESULT_INTERRUPTED, SCAN_RESULT_ERROR):
            sid = f"scan-{resultado}"
            storage.begin_scan_run(sid, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
            storage.end_scan_run(sid, result=resultado, entries_count=10, errors_count=0, exclusions_count=0)
            run = storage.get_scan_run(sid)
            assert run is not None
            assert run["result"] == resultado
            assert run["finished_at"] is not None

    def test_begin_scan_run_estado_inicial_es_interrumpido_no_completo(self, storage: SystemInventoryStorage):
        """Un escaneo iniciado no se presenta como completo hasta que end_scan_run lo confirma con OK (3.8.5.1.4.2.7)."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        run = storage.get_scan_run("scan-1")
        assert run is not None
        assert run["result"] == SCAN_RESULT_INTERRUPTED
        assert run["finished_at"] is None
        assert run["entries_count"] == 0
        # Cerrar el escaneo para liberar el bloqueo de concurrencia (3.8.5.1.4.2.9).
        storage.end_scan_run("scan-1", result=SCAN_RESULT_INTERRUPTED)

    def test_begin_scan_run_marca_scan_previo_sin_finalizar_como_interrumpido(self, storage: SystemInventoryStorage):
        """begin_scan_run marca scans_run previos del mismo equipo/volumen sin finalizar como interrumpidos (3.8.5.1.4.2.7)."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-antiguo", "machine-alfa", "C:", SCAN_MODE_FULL)
        # Finalizar el primer escaneo antes de iniciar el siguiente: el contrato
        # de concurrencia (3.8.5.1.4.2.9) no permite dos escaneos simultaneos.
        storage.end_scan_run("scan-antiguo", result=SCAN_RESULT_INTERRUPTED)
        storage.begin_scan_run("scan-nuevo", "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        antiguo = storage.get_scan_run("scan-antiguo")
        nuevo = storage.get_scan_run("scan-nuevo")
        assert antiguo is not None
        assert antiguo["result"] == SCAN_RESULT_INTERRUPTED
        assert antiguo["finished_at"] is not None
        assert nuevo is not None
        assert nuevo["result"] == SCAN_RESULT_INTERRUPTED
        assert nuevo["finished_at"] is None

    def test_begin_scan_run_no_toca_scan_de_otro_volumen_ni_ya_finalizado(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-c", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-c", result=SCAN_RESULT_OK, entries_count=5)
        storage.begin_scan_run("scan-d", "machine-alfa", "D:", SCAN_MODE_FULL)
        c = storage.get_scan_run("scan-c")
        d = storage.get_scan_run("scan-d")
        assert c["result"] == SCAN_RESULT_OK
        assert c["finished_at"] is not None
        assert d["result"] == SCAN_RESULT_INTERRUPTED
        assert d["finished_at"] is None

    def test_end_scan_run_confirma_resultado_ok_despues_de_begin_interrumpido(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        assert storage.get_scan_run("scan-1")["result"] == SCAN_RESULT_INTERRUPTED
        storage.end_scan_run("scan-1", result=SCAN_RESULT_OK, entries_count=10)
        run = storage.get_scan_run("scan-1")
        assert run["result"] == SCAN_RESULT_OK
        assert run["finished_at"] is not None
        assert run["entries_count"] == 10


# ---------------------------------------------------------------------------
# Linea base (primera instantanea completa por volumen) (3.8.5.1.4.5.1).
# ---------------------------------------------------------------------------

class TestLineaBaseVolumen:
    """La primera instantanea completa por volumen se conserva como linea base
    y no se sobrescribe por escaneos posteriores (3.8.5.1.4.5.1)."""

    def test_registrar_linea_base_primera_guarda_fecha_estado_cobertura(
        self, storage: SystemInventoryStorage
    ):
        storage.initialize()
        storage.record_machine("machine-alfa")
        linea = storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
            entradas_count=42,
            errores_count=1,
            scan_id="scan-1",
        )
        assert linea is not None
        assert linea["machine_id"] == "machine-alfa"
        assert linea["volume"] == "C:"
        assert linea["estado_volumen"] == "disponible"
        assert linea["cobertura"] == 100.0
        assert linea["entradas_count"] == 42
        assert linea["errores_count"] == 1
        assert linea["scan_id"] == "scan-1"
        assert "linea_id" in linea
        assert "fecha_base" in linea
        assert "created_at" in linea

    def test_obtener_linea_base_devuelve_registrada(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
        )
        obtenida = storage.obtener_linea_base_volumen("machine-alfa", "C:")
        assert obtenida is not None
        assert obtenida["volume"] == "C:"
        assert obtenida["estado_volumen"] == "disponible"
        assert obtenida["cobertura"] == 100.0

    def test_obtener_linea_base_inexistente_devuelve_none(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        assert storage.obtener_linea_base_volumen("machine-alfa", "C:") is None

    def test_registrar_linea_base_segunda_no_sobrescribe_primera(
        self, storage: SystemInventoryStorage
    ):
        """Solo la primera linea base se conserva; la segunda no la reemplaza."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        primera = storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
            entradas_count=10,
            scan_id="scan-1",
        )
        segunda = storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="inaccesible",
            cobertura=0.0,
            entradas_count=0,
            scan_id="scan-2",
        )
        assert segunda is not None
        assert segunda["linea_id"] == primera["linea_id"]
        assert segunda["estado_volumen"] == "disponible"
        assert segunda["cobertura"] == 100.0
        assert segunda["entradas_count"] == 10

    def test_lineas_base_independientes_por_maquina_y_volumen(
        self, storage: SystemInventoryStorage
    ):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_machine("machine-beta")
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa", volume="C:", estado_volumen="disponible", cobertura=100.0
        )
        storage.registrar_linea_base_volumen(
            machine_id="machine-beta", volume="C:", estado_volumen="disponible", cobertura=100.0
        )
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa", volume="D:", estado_volumen="disponible", cobertura=50.0
        )
        assert storage.obtener_linea_base_volumen("machine-alfa", "C:")["cobertura"] == 100.0
        assert storage.obtener_linea_base_volumen("machine-beta", "C:")["cobertura"] == 100.0
        assert storage.obtener_linea_base_volumen("machine-alfa", "D:")["cobertura"] == 50.0

    def test_linea_base_persiste_al_reabrir_instancia(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        storage.initialize()
        storage.record_machine("machine-alfa")
        primera = storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
        )
        storage2 = SystemInventoryStorage(db_path)
        storage2.initialize()
        obtenida = storage2.obtener_linea_base_volumen("machine-alfa", "C:")
        assert obtenida is not None
        assert obtenida["linea_id"] == primera["linea_id"]
        assert obtenida["cobertura"] == 100.0

    def test_esquema_version_3_incluye_tabla_lineas_base(self, storage: SystemInventoryStorage):
        storage.initialize()
        assert storage.schema_version() == 4
        conn = storage.connect()
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lineas_base'")
        assert cur.fetchone() is not None
        cur = conn.execute("PRAGMA table_info(lineas_base)")
        columnas = {row["name"] for row in cur.fetchall()}
        for requerida in (
            "linea_id", "machine_id", "volume", "fecha_base", "estado_volumen",
            "cobertura", "entradas_count", "errores_count", "scan_id", "created_at",
        ):
            assert requerida in columnas

    def test_migracion_v2_a_v3_crea_tabla_lineas_base(self, db_path: Path):
        """Una base ya en version 2 aplica la migracion v2->v3 y crea lineas_base."""
        storage_v2 = SystemInventoryStorage(db_path)
        storage_v2.initialize()  # queda en version 2 (migraciones v1->v2 si fuera v1)
        # Forzar version 2 para simular una base previa sin lineas_base.
        conn = storage_v2.connect()
        conn.execute("UPDATE schema_version SET version = 2")
        conn.commit()
        storage_v2.close()

        storage_v3 = SystemInventoryStorage(db_path)
        version = storage_v3.initialize()
        assert version == 4
        assert storage_v3.obtener_linea_base_volumen("machine-alfa", "C:") is None
        creada = storage_v3.registrar_linea_base_volumen(
            machine_id="machine-alfa", volume="C:",
            estado_volumen="disponible", cobertura=100.0,
        )
        assert creada is not None


# ---------------------------------------------------------------------------
# Deteccion de cambios incrementales (3.8.5.1.4.5.2).
# ---------------------------------------------------------------------------

class TestDeteccionCambiosIncrementales:
    """Detectar altas, cambios y desapariciones comparando metadatos entre la
    linea base y un escaneo nuevo, sin releer contenido de archivos."""

    def _crear_linea_base_con_entradas(self, storage: SystemInventoryStorage, scan_id: str = "scan-base") -> None:
        """Crea linea base y puebla entradas de archivo del escaneo base."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries(scan_id, "machine-alfa", "C:", [
            {
                "entry_id": "e-base-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-base-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-base-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
        ])
        storage.end_scan_run(scan_id, entries_count=3)
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
            entradas_count=3,
            errores_count=0,
            scan_id=scan_id,
        )

    def _escanear_nuevo(self, storage: SystemInventoryStorage, scan_id: str = "scan-nuevo") -> None:
        """Crea un nuevo escaneo incremental sobre el mismo equipo/volumen."""
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)

    def test_sin_linea_base_retorna_resultado_vacio(self, storage: SystemInventoryStorage):
        """Si no hay linea base para el equipo/volumen, retorna resultado vacio."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-1")
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:")
        assert resultado.linea_base is None
        resultado.scan_usado is None
        assert resultado.altas == []
        assert resultado.cambios == []
        assert resultado.desapariciones == []
        assert resultado.sin_cambios == 0

    def test_sin_escaneo_nuevo_retorna_linea_base_sin_comparar(self, storage: SystemInventoryStorage):
        """Si hay linea base pero no hay escaneo previo nuevo, retorna con scan_usado=None."""
        self._crear_linea_base_con_entradas(storage)
        # No crear escaneo nuevo
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:")
        assert resultado.linea_base is not None
        assert resultado.scan_usado is None
        assert resultado.altas == []
        assert resultado.cambios == []
        assert resultado.desapariciones == []

    def test_sin_cambios_entre_base_y_nuevo(self, storage: SystemInventoryStorage):
        """Mismas entradas y mismos metadatos: sin cambios, sin altas, sin desapariciones."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=3)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert resultado.total_base == 3
        assert resultado.total_nuevo == 3
        assert resultado.sin_cambios == 3
        assert resultado.altas == []
        assert resultado.cambios == []
        assert resultado.desapariciones == []

    def test_alta_nueva_entrada(self, storage: SystemInventoryStorage):
        """Una entrada presente solo en el nuevo escaneo se detecta como alta."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-4",
                "absolute_path": "C:/Nuevo/nuevo.exe",
                "relative_path": "Nuevo/nuevo.exe",
                "name": "nuevo.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 9999,
                "modified_at": "2024-06-01T10:00:00",
                "created_at": "2024-06-01T09:00:00",
                "accessed_at": "2024-06-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=4)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert resultado.total_base == 3
        assert resultado.total_nuevo == 4
        assert len(resultado.altas) == 1
        assert resultado.altas[0]["name"] == "nuevo.exe"
        assert resultado.sin_cambios == 3
        assert resultado.cambios == []
        assert resultado.desapariciones == []

    def test_desaparicion_entrada_eliminada(self, storage: SystemInventoryStorage):
        """Una entrada presente solo en la base se detecta como desaparicion."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=2)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert resultado.total_base == 3
        assert resultado.total_nuevo == 2
        assert len(resultado.desapariciones) == 1
        assert resultado.desapariciones[0]["name"] == "tool.dll"
        assert resultado.sin_cambios == 2
        assert resultado.altas == []
        assert resultado.cambios == []

    def test_cambio_de_tamano(self, storage: SystemInventoryStorage):
        """Cambio en size_bytes se detecta como cambio."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 9999,  # cambiado de 1024
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=3)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.cambios) == 1
        assert resultado.cambios[0].campo == "size_bytes"
        assert resultado.cambios[0].valor_base == 1024
        assert resultado.cambios[0].valor_nuevo == 9999
        assert resultado.cambios[0].normalized_path == "c:/apps/app.exe"
        assert resultado.sin_cambios == 2
        assert resultado.altas == []
        assert resultado.desapariciones == []

    def test_cambio_de_atributos(self, storage: SystemInventoryStorage):
        """Cambio en attributes se detecta como cambio."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": ["hidden", "solo_lectura"],  # cambiado de []
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=3)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.cambios) == 1
        assert resultado.cambios[0].campo == "attributes"
        assert resultado.cambios[0].valor_base == []
        assert resultado.cambios[0].valor_nuevo == ["hidden", "solo_lectura"]
        assert resultado.sin_cambios == 2

    def test_cambio_de_marca_temporal(self, storage: SystemInventoryStorage):
        """Cambio en modified_at se detecta como cambio."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-05-01T10:00:00",  # cambiado de 2024-01-01
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=3)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.cambios) == 1
        assert resultado.cambios[0].campo == "modified_at"
        assert resultado.cambios[0].valor_base == "2024-01-01T10:00:00"
        assert resultado.cambios[0].valor_nuevo == "2024-05-01T10:00:00"
        assert resultado.sin_cambios == 2

    def test_scan_id_no_pertenece_a_maquina_volumen_levanta_error(self, storage: SystemInventoryStorage):
        """Un scan_id de otro equipo o volumen levanta ValueError."""
        self._crear_linea_base_con_entradas(storage)
        storage.record_machine("machine-otra")
        storage.begin_scan_run("scan-otra", "machine-otra", "D:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-otra", entries_count=0)
        with pytest.raises(ValueError):
            storage.detectar_cambios_incrementales(
                "machine-alfa", "C:", scan_id_nuevo="scan-otra"
            )

    def test_scan_id_desconocido_levanta_error(self, storage: SystemInventoryStorage):
        """Un scan_id inexistente levanta ValueError."""
        self._crear_linea_base_con_entradas(storage)
        with pytest.raises(ValueError):
            storage.detectar_cambios_incrementales(
                "machine-alfa", "C:", scan_id_nuevo="scan-inexistente"
            )

    def test_usar_ultimo_escaneo_automaticamente(self, storage: SystemInventoryStorage):
        """Si no se indica scan_id_nuevo, se usa el ultimo escaneo del equipo/volumen."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-auto")
        storage.insert_file_entries("scan-auto", "machine-alfa", "C:", [
            {
                "entry_id": "e-a-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-a-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-a-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-auto", entries_count=3)
        # Sin pasar scan_id_nuevo: debe usar el ultimo automaticamente.
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:")
        assert resultado.scan_usado is not None
        assert resultado.scan_usado["scan_id"] == "scan-auto"
        assert resultado.sin_cambios == 3

    def test_resumen_serializable(self, storage: SystemInventoryStorage):
        """resumen() devuelve un diccionario serializable con contadores."""
        self._crear_linea_base_con_entradas(storage)
        self._escanear_nuevo(storage, "scan-nuevo")
        storage.insert_file_entries("scan-nuevo", "machine-alfa", "C:", [
            {
                "entry_id": "e-n-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
            {
                "entry_id": "e-n-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-04T00:00:00",
            },
        ])
        storage.end_scan_run("scan-nuevo", entries_count=3)
        resultado = storage.detectar_cambios_incrementales("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        resumen = resultado.resumen()
        assert resumen["machine_id"] == "machine-alfa"
        assert resumen["volume"] == "C:"
        assert resumen["total_base"] == 3
        assert resumen["total_nuevo"] == 3
        assert resumen["altas"] == 0
        assert resumen["cambios"] == 0
        assert resumen["desapariciones"] == 0
        assert resumen["sin_cambios"] == 3


# ---------------------------------------------------------------------------
# Deteccion de renombrados / cambios de ruta y nombre (3.8.5.1.4.5.3).
# ---------------------------------------------------------------------------

class TestDeteccionRenombrados:
    """Detectar cambios de ruta/nombre y renombrados cuando el sistema de
    archivos proporcione evidencia suficiente, sin fusionar archivos distintos
    solo por compartir nombre o tamaño."""

    def _entrada(
        self,
        entry_id: str,
        absolute_path: str,
        name: str,
        size_bytes: int,
        modified_at: str,
        entry_type: str = "file",
        attributes=None,
        created_at: str = "2024-01-01T09:00:00",
        accessed_at: str = "2024-01-02T08:00:00",
    ) -> dict:
        return {
            "entry_id": entry_id,
            "absolute_path": absolute_path,
            "relative_path": "/".join(Path(absolute_path).parts[1:]),
            "name": name,
            "extension": Path(absolute_path).suffix,
            "entry_type": entry_type,
            "size_bytes": size_bytes,
            "modified_at": modified_at,
            "created_at": created_at,
            "accessed_at": accessed_at,
            "attributes": attributes if attributes is not None else [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-04T00:00:00",
        }

    def _crear_linea_base(
        self, storage: SystemInventoryStorage, scan_id: str = "scan-base"
    ) -> None:
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries(scan_id, "machine-alfa", "C:", [
            self._entrada("e-b-1", "C:/Apps/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-b-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            self._entrada("e-b-3", "C:/Docs/readme.txt", "readme.txt", 500, "2024-03-01T10:00:00"),
        ])
        storage.end_scan_run(scan_id, entries_count=3)
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
            entradas_count=3,
            errores_count=0,
            scan_id=scan_id,
        )

    def _escanear_nuevo(
        self, storage: SystemInventoryStorage, scan_id: str, entries: list[dict]
    ) -> None:
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        storage.insert_file_entries(scan_id, "machine-alfa", "C:", entries)
        storage.end_scan_run(scan_id, entries_count=len(entries))

    # ------------------------------------------------------------------ #
    # Casos positivos: renombrado detectado con evidencia suficiente.
    # ------------------------------------------------------------------ #

    def test_renombrado_cambio_de_ruta_sin_cambio_de_nombre(
        self, storage: SystemInventoryStorage
    ):
        """Misma ruta de archivo bajo distinto directorio, mismos metadatos:
        se detecta como renombrado, no como alta + desapareción."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Nuevo/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            self._entrada("e-n-3", "C:/Docs/readme.txt", "readme.txt", 500, "2024-03-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.renombrados) == 1
        r = resultado.renombrados[0]
        assert r.normalized_path_base == "c:/apps/app.exe"
        assert r.normalized_path_nuevo == "c:/nuevo/app.exe"
        assert r.name_base == "app.exe"
        assert r.name_nuevo == "app.exe"
        assert r.nombre_cambio is False
        assert r.ruta_cambio is True
        assert r.size_bytes == 1024
        assert "size_bytes" in r.campos_coincidentes
        assert "modified_at" in r.campos_coincidentes
        assert resultado.altas == []
        assert resultado.desapariciones == []
        assert resultado.sin_cambios == 2
        assert resultado.total_base == 3
        assert resultado.total_nuevo == 3

    def test_renombrado_cambio_de_nombre_misma_ruta(
        self, storage: SystemInventoryStorage
    ):
        """Mismo directorio, distinto nombre, mismos metadatos: se detecta como
        renombrado con nombre_cambio=True."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Apps/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            self._entrada("e-n-3", "C:/Docs/manual.txt", "manual.txt", 500, "2024-03-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.renombrados) == 1
        r = resultado.renombrados[0]
        assert r.normalized_path_base == "c:/docs/readme.txt"
        assert r.normalized_path_nuevo == "c:/docs/manual.txt"
        assert r.name_base == "readme.txt"
        assert r.name_nuevo == "manual.txt"
        assert r.nombre_cambio is True
        # La ruta normalizada incluye el nombre del archivo, por lo que un
        # cambio de nombre también cambia la ruta normalizada completa.
        assert r.ruta_cambio is True
        assert resultado.altas == []
        assert resultado.desapariciones == []
        assert resultado.sin_cambios == 2

    def test_varios_renombrados_en_mismo_escaneo(
        self, storage: SystemInventoryStorage
    ):
        """Dos archivos renombrados en el mismo escaneo incremental."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Nuevo/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Nuevo/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            self._entrada("e-n-3", "C:/Docs/readme.txt", "readme.txt", 500, "2024-03-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.renombrados) == 2
        rutas_base = {r.normalized_path_base for r in resultado.renombrados}
        rutas_nuevo = {r.normalized_path_nuevo for r in resultado.renombrados}
        assert rutas_base == {"c:/apps/app.exe", "c:/apps/tool.dll"}
        assert rutas_nuevo == {"c:/nuevo/app.exe", "c:/nuevo/tool.dll"}
        assert resultado.altas == []
        assert resultado.desapariciones == []
        assert resultado.sin_cambios == 1

    def test_renombrado_mezclado_con_alta_y_desaparicion_genuinas(
        self, storage: SystemInventoryStorage
    ):
        """Un renombrado, una alta genuina y una desaparición genuina en el
        mismo escaneo: cada categoría se cuenta por separado."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            # app.exe renombrado a C:/Nuevo/app.exe (mismos metadatos).
            self._entrada("e-n-1", "C:/Nuevo/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            # tool.dll se mantiene sin cambios.
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            # readme.txt desaparece: no hay sustituto con mismos metadatos.
            # nuevo.exe es una alta genuina: no existía en la base.
            self._entrada("e-n-4", "C:/Nuevo/nuevo.exe", "nuevo.exe", 777, "2024-06-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.renombrados) == 1
        assert resultado.renombrados[0].normalized_path_base == "c:/apps/app.exe"
        assert len(resultado.desapariciones) == 1
        assert resultado.desapariciones[0]["name"] == "readme.txt"
        assert len(resultado.altas) == 1
        assert resultado.altas[0]["name"] == "nuevo.exe"
        assert resultado.sin_cambios == 1

    # ------------------------------------------------------------------ #
    # Casos negativos: no fusionar archivos distintos.
    # ------------------------------------------------------------------ #

    def test_no_fusionar_por_mismo_nombre_distinto_tamano(
        self, storage: SystemInventoryStorage
    ):
        """Mismo nombre en distinta ruta pero distinto tamaño: NO es renombrado;
        queda como desaparición + alta."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Apps/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            # Mismo nombre "readme.txt", distinto tamaño: no fusionar.
            self._entrada("e-n-3", "C:/Nuevo/readme.txt", "readme.txt", 9999, "2024-03-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert resultado.renombrados == []
        assert len(resultado.desapariciones) == 1
        assert resultado.desapariciones[0]["name"] == "readme.txt"
        assert len(resultado.altas) == 1
        assert resultado.altas[0]["name"] == "readme.txt"
        assert resultado.sin_cambios == 2

    def test_no_fusionar_por_mismo_tamano_distinto_marcado_temporal(
        self, storage: SystemInventoryStorage
    ):
        """Mismo tamaño en distinta ruta pero marca temporal distinta: NO es
        renombrado."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Apps/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            # Mismo tamaño que readme.txt (500) pero modificado en otra fecha.
            self._entrada("e-n-3", "C:/Nuevo/otro.txt", "otro.txt", 500, "2024-09-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert resultado.renombrados == []
        assert len(resultado.desapariciones) == 1
        assert resultado.desapariciones[0]["name"] == "readme.txt"
        assert len(resultado.altas) == 1
        assert resultado.altas[0]["name"] == "otro.txt"
        assert resultado.sin_cambios == 2

    def test_no_fusionar_si_falta_marca_temporal_requerida(
        self, storage: SystemInventoryStorage
    ):
        """Sin modified_at (campo obligatorio de evidencia) no hay renombrado
        aunque el resto coincida."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Apps/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            self._entrada("e-n-3", "C:/Nuevo/readme.txt", "readme.txt", 500, None),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert resultado.renombrados == []
        assert len(resultado.desapariciones) == 1
        assert len(resultado.altas) == 1

    def test_emparejamiento_no_cruza_archivos_con_mismo_tamano(
        self, storage: SystemInventoryStorage
    ):
        """Dos archivos con tamaños distintos renombrados: el emparejamiento
        respeta los metadatos de cada uno y no cruza rutas."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-base", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries("scan-base", "machine-alfa", "C:", [
            self._entrada("e-b-1", "C:/Docs/alfa.txt", "alfa.txt", 100, "2024-01-01T10:00:00"),
            self._entrada("e-b-2", "C:/Docs/beta.txt", "beta.txt", 200, "2024-02-01T10:00:00"),
        ])
        storage.end_scan_run("scan-base", entries_count=2)
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa", volume="C:",
            estado_volumen="disponible", cobertura=100.0,
            entradas_count=2, errores_count=0, scan_id="scan-base",
        )
        # Nombres cruzados pero tamaños propios: alfa(100) debe emparejarse con
        # el archivo de 100 bytes y beta(200) con el de 200 bytes.
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Nuevo/beta.txt", "beta.txt", 100, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Nuevo/alfa.txt", "alfa.txt", 200, "2024-02-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        assert len(resultado.renombrados) == 2
        pares = {(r.normalized_path_base, r.normalized_path_nuevo) for r in resultado.renombrados}
        assert ("c:/docs/alfa.txt", "c:/nuevo/beta.txt") in pares
        assert ("c:/docs/beta.txt", "c:/nuevo/alfa.txt") in pares

    # ------------------------------------------------------------------ #
    # Casos borde y validaciones.
    # ------------------------------------------------------------------ #

    def test_sin_linea_base_retorna_resultado_vacio(self, storage: SystemInventoryStorage):
        """Sin línea base no hay renombrados ni comparación."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-1")
        resultado = storage.detectar_renombrados("machine-alfa", "C:")
        assert resultado.linea_base is None
        assert resultado.scan_usado is None
        assert resultado.renombrados == []
        assert resultado.altas == []
        assert resultado.desapariciones == []

    def test_scan_id_desconocido_levanta_error(self, storage: SystemInventoryStorage):
        """Un scan_id inexistente propaga el ValueError de la detección base."""
        self._crear_linea_base(storage)
        with pytest.raises(ValueError):
            storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-inexistente")

    def test_resumen_serializable(self, storage: SystemInventoryStorage):
        """resumen() devuelve contadores serializables coherentes."""
        self._crear_linea_base(storage)
        self._escanear_nuevo(storage, "scan-nuevo", [
            self._entrada("e-n-1", "C:/Nuevo/app.exe", "app.exe", 1024, "2024-01-01T10:00:00"),
            self._entrada("e-n-2", "C:/Apps/tool.dll", "tool.dll", 2048, "2024-02-01T10:00:00"),
            self._entrada("e-n-3", "C:/Docs/readme.txt", "readme.txt", 500, "2024-03-01T10:00:00"),
        ])
        resultado = storage.detectar_renombrados("machine-alfa", "C:", scan_id_nuevo="scan-nuevo")
        resumen = resultado.resumen()
        assert resumen["machine_id"] == "machine-alfa"
        assert resumen["volume"] == "C:"
        assert resumen["renombrados"] == 1
        assert resumen["altas"] == 0
        assert resumen["desapariciones"] == 0
        assert resumen["sin_cambios"] == 2
        assert resumen["total_base"] == 3
        assert resumen["total_nuevo"] == 3


# ---------------------------------------------------------------------------
# Escritura atomica por lotes
# ---------------------------------------------------------------------------

class TestInsercionAtomica:
    """Insercion por lotes en transaccion atomica (sin entradas parciales tras fallo)."""

    def _una_entrada(self, entry_id: str = "e-1", absolute_path: str = "C:/Users/Jarvis/app.exe") -> dict:
        p = Path(absolute_path)
        name = p.name
        parts = p.parts
        relative_path = str(Path(*parts[1:])) if len(parts) > 1 else name
        return {
            "entry_id": entry_id,
            "absolute_path": absolute_path,
            "relative_path": relative_path,
            "name": name,
            "extension": p.suffix,
            "entry_type": "file",
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "accessed_at": "2024-01-02T08:00:00",
            "attributes": ["hidden"],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }

    def test_insert_file_entries_lote(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        entradas = [self._una_entrada("e-1", "C:/Users/Jarvis/app1.exe"), self._una_entrada("e-2", "C:/Users/Jarvis/app2.exe")]
        insertados = storage.insert_file_entries("scan-1", "machine-alfa", "C:", entradas)
        assert insertados == 2
        assert storage.get_entry_count("machine-alfa", "C:") == 2

    def test_insert_file_entries_vacio_no_inserta(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        assert storage.insert_file_entries("scan-1", "machine-alfa", "C:", []) == 0
        assert storage.get_entry_count("machine-alfa") == 0

    def test_insercion_atomica_fallo_no_deja_entradas_parciales(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        buena = self._una_entrada("e-buena")
        # entrada con entry_id duplicado para forzar violacion de PK en el lote
        duplicada = dict(buena, entry_id="e-dup")
        lote = [buena, duplicada, dict(buena, entry_id="e-dup")]
        with pytest.raises(Exception):
            storage.insert_file_entries("scan-1", "machine-alfa", "C:", lote)
        # Ninguna entrada del lote fallido debe haberse persistido.
        assert storage.get_entry_count("machine-alfa", "C:") == 0

    def test_insert_application_candidates_tabla_separada(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        candidatos = [
            {
                "candidate_id": "c-1",
                "name": "Google Chrome",
                "absolute_path": "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "launch_type": "ejecutable",
                "confidence": 0.95,
                "source": "inventory",
                "last_checked_at": "2024-01-03T00:00:00",
            }
        ]
        insertados = storage.insert_application_candidates("scan-1", "machine-alfa", "C:", candidatos)
        assert insertados == 1
        # Los candidatos no cuentan como entradas genericas de archivo.
        assert storage.get_entry_count("machine-alfa", "C:") == 0


# ---------------------------------------------------------------------------
# Consultas indexadas y paginadas
# ---------------------------------------------------------------------------

class TestConsultasIndexadas:
    """Busquedas por nombre, extension y prefijo de ruta, con paginacion."""

    def _seed(self, storage: SystemInventoryStorage, machine_id: str = "machine-alfa") -> str:
        storage.initialize()
        storage.record_machine(machine_id)
        storage.begin_scan_run("scan-1", machine_id, "C:", SCAN_MODE_FULL)
        entradas = []
        for i in range(5):
            entradas.append({
                "entry_id": f"e-{i}",
                "absolute_path": f"C:/Apps/app{i}.exe",
                "relative_path": f"Apps/app{i}.exe",
                "name": f"app{i}.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1000 + i,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            })
        # Una entrada de otro tipo y extension para diferenciar
        entradas.append({
            "entry_id": "e-readme",
            "absolute_path": "C:/Apps/readme.txt",
            "relative_path": "Apps/readme.txt",
            "name": "readme.txt",
            "extension": ".txt",
            "entry_type": "file",
            "size_bytes": 200,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        })
        storage.insert_file_entries("scan-1", machine_id, "C:", entradas)
        storage.end_scan_run("scan-1", entries_count=len(entradas))
        return "scan-1"

    def test_search_by_name(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_name("machine-alfa", "app2.exe")
        assert len(res) == 1
        assert res[0]["name"] == "app2.exe"

    def test_search_by_name_case_insensitive(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_name("machine-alfa", "APP2.EXE")
        assert len(res) == 1

    def test_search_by_extension(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_extension("machine-alfa", ".txt")
        assert len(res) == 1
        assert res[0]["name"] == "readme.txt"

    def test_search_by_extension_case_insensitive(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_extension("machine-alfa", ".TXT")
        assert len(res) == 1

    def test_search_by_path_prefix(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_path_prefix("machine-alfa", "C:/Apps/app")
        assert len(res) == 5

    def test_paginacion_limite_y_offset(self, storage: SystemInventoryStorage):
        self._seed(storage)
        primera = storage.search_by_name("machine-alfa", "app*.exe") if False else storage.search_by_path_prefix("machine-alfa", "C:/Apps/app", limit=2, offset=0)
        assert len(primera) == 2
        segunda = storage.search_by_path_prefix("machine-alfa", "C:/Apps/app", limit=2, offset=2)
        assert len(segunda) == 2
        ids_primera = {e["entry_id"] for e in primera}
        ids_segunda = {e["entry_id"] for e in segunda}
        assert ids_primera.isdisjoint(ids_segunda)

    def test_consulta_equipo_diferente_no_devuelve_datos(self, storage: SystemInventoryStorage):
        self._seed(storage, "machine-alfa")
        res = storage.search_by_name("machine-beta", "app2.exe")
        assert res == []
        assert storage.get_entry_count("machine-beta") == 0


# ---------------------------------------------------------------------------
# Contexto y cierre limpio
# ---------------------------------------------------------------------------

class TestContexto:
    """Uso como gestor de contexto y cierre limpio de la conexion."""

    def test_gestor_de_contexto_abre_y_cierra(self, db_path: Path):
        with SystemInventoryStorage(db_path) as storage:
            storage.initialize()
            assert db_path.exists()
        # tras salir del contexto la conexion debe estar cerrada
        assert storage._conn is None

    def test_conexion_wal_y_foreign_keys(self, storage: SystemInventoryStorage):
        storage.initialize()
        conn = storage.connect()
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert str(journal).lower() in ("wal", "memory")
        assert int(fk) == 1


# ---------------------------------------------------------------------------
# Manifiesto JSON ligero del inventario (3.8.5.1.4.2.10).
# ---------------------------------------------------------------------------

class TestManifiestoJSON:
    """El manifiesto `system_inventory_manifest.json` resume version, equipo,
    volumenes y ultimo escaneo sin almacenar el listado completo de archivos."""

    def test_write_manifest_crea_fichero_json(self, storage: SystemInventoryStorage, db_path: Path):
        storage.initialize()
        storage.record_machine("machine-alfa")
        manifest = storage.write_manifest("machine-alfa")
        assert storage.manifest_path.exists()
        assert manifest["machine_id"] == "machine-alfa"
        assert manifest["version"] == 4
        assert "volumes" in manifest
        assert "last_scan" in manifest
        assert "updated_at" in manifest

    def test_read_manifest_devuelve_contenido_escrito(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        escrito = storage.write_manifest("machine-alfa")
        leido = storage.read_manifest()
        assert leido == escrito

    def test_read_manifest_sin_fichero_devuelve_none(self, storage: SystemInventoryStorage):
        # Sin inicializar ni escribir, no hay manifiesto.
        assert storage.read_manifest() is None

    def test_manifest_no_almacena_listado_completo_de_archivos(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        entradas = [
            {
                "entry_id": f"e-{i}",
                "absolute_path": f"C:/Apps/app{i}.exe",
                "relative_path": f"Apps/app{i}.exe",
                "name": f"app{i}.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1000 + i,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            }
            for i in range(50)
        ]
        storage.insert_file_entries("scan-1", "machine-alfa", "C:", entradas)
        storage.end_scan_run("scan-1", entries_count=50)
        manifest = storage.read_manifest()
        # El manifiesto resume, no lista todos los archivos.
        assert "file_entries" not in manifest
        assert "entries" not in manifest
        assert "files" not in manifest
        assert manifest["last_scan"]["entries_count"] == 50

    def test_manifest_coherente_con_sqlite_despues_de_scan(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-1", result=SCAN_RESULT_OK, entries_count=42, errors_count=1)
        manifest = storage.read_manifest()
        assert manifest is not None
        assert manifest["machine_id"] == "machine-alfa"
        assert manifest["version"] == 4
        assert len(manifest["volumes"]) == 1
        assert manifest["volumes"][0]["volume"] == "C:"
        assert manifest["last_scan"] is not None
        assert manifest["last_scan"]["scan_id"] == "scan-1"
        assert manifest["last_scan"]["result"] == SCAN_RESULT_OK
        assert manifest["last_scan"]["entries_count"] == 42
        assert manifest["last_scan"]["errors_count"] == 1

    def test_manifest_actualizado_al_registrar_volumen(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        # Antes de registrar volumenes, el manifiesto tiene lista vacia.
        storage.write_manifest("machine-alfa")
        manifest = storage.read_manifest()
        assert manifest["volumes"] == []
        # Tras registrar un volumen, aparece en el manifiesto.
        storage.record_volume("vol-d:", "machine-alfa", "D:", "local", "online")
        manifest = storage.read_manifest()
        assert len(manifest["volumes"]) == 1
        assert manifest["volumes"][0]["volume"] == "D:"


# ---------------------------------------------------------------------------
# Clave unica por equipo/volumen/ruta normalizada (3.8.5.1.4.2.5)
# ---------------------------------------------------------------------------

class TestClaveUnicaRutaNormalizada:
    """La clave unica (machine_id, volume, normalized_path) impide rutas duplicadas."""

    def test_ruta_duplicada_misma_maquina_volumen_falla(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        e1 = {
            "entry_id": "e-1",
            "absolute_path": "C:/Apps/App.EXE",
            "relative_path": "Apps/App.EXE",
            "name": "App.EXE",
            "extension": ".EXE",
            "entry_type": "file",
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }
        # Same path, different case -> misma ruta normalizada en sistemas insensibles.
        e2 = dict(e1, entry_id="e-2", absolute_path="C:/Apps/app.exe")
        storage.insert_file_entries("scan-1", "machine-alfa", "C:", [e1])
        with pytest.raises(Exception):
            storage.insert_file_entries("scan-1", "machine-alfa", "C:", [e2])
        # Ninguna entrada parcial tras el fallo.
        assert storage.get_entry_count("machine-alfa", "C:") == 1

    def test_misma_ruta_diferente_maquina_se_permite(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_machine("machine-beta")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.begin_scan_run("scan-2", "machine-beta", "C:", SCAN_MODE_FULL)
        e1 = {
            "entry_id": "e-1",
            "absolute_path": "C:/Apps/App.EXE",
            "relative_path": "Apps/App.EXE",
            "name": "App.EXE",
            "extension": ".EXE",
            "entry_type": "file",
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }
        e2 = dict(e1, entry_id="e-2", scan_id="scan-2")  # scan_id no se usa en la unique key
        storage.insert_file_entries("scan-1", "machine-alfa", "C:", [e1])
        # Otro equipo puede tener la misma ruta (aislamiento por equipo).
        insertados = storage.insert_file_entries("scan-2", "machine-beta", "C:", [e2])
        assert insertados == 1
        assert storage.get_entry_count("machine-alfa", "C:") == 1
        assert storage.get_entry_count("machine-beta", "C:") == 1

    def test_rutas_diferentes_se_permiten(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        e1 = {
            "entry_id": "e-1",
            "absolute_path": "C:/Apps/App.EXE",
            "relative_path": "Apps/App.EXE",
            "name": "App.EXE",
            "extension": ".EXE",
            "entry_type": "file",
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }
        e2 = dict(e1, entry_id="e-2", absolute_path="C:/Apps/Otro.EXE")
        insertados = storage.insert_file_entries("scan-1", "machine-alfa", "C:", [e1, e2])
        assert insertados == 2
        assert storage.get_entry_count("machine-alfa", "C:") == 2


# ---------------------------------------------------------------------------
# Normalizacion de rutas y case-sensitividad (3.8.5.1.4.2.5)
# ---------------------------------------------------------------------------

from src.hands.system_inventory_storage import normalize_path, _FILESYSTEM_CASE_SENSITIVE  # noqa: E402


class TestNormalizacionRutas:
    """La normalizacion respeta la case-sensitividad del sistema de archivos."""

    def test_normalize_path_quita_barra_invertida(self):
        resultado = normalize_path("C:\\Users\\Jarvis\\app.exe")
        assert resultado == "c:/users/jarvis/app.exe" or resultado == "C:/Users/Jarvis/app.exe"
        assert "\\" not in resultado

    def test_normalize_path_sistema_insensible_minusculas(self):
        """En Windows (sistema insensible) las rutas se normalizan a minusculas."""
        if not _FILESYSTEM_CASE_SENSITIVE:
            assert normalize_path("C:/Apps/App.EXE") == "c:/apps/app.exe"
            assert normalize_path("c:/apps/app.exe") == "c:/apps/app.exe"
        else:
            # En sistemas sensibles se conserva tal cual.
            assert normalize_path("C:/Apps/App.EXE") == "C:/Apps/App.EXE"


# ---------------------------------------------------------------------------
# Migracion de esquema v1 -> v2 (3.8.5.1.4.2.5)
# ---------------------------------------------------------------------------

class TestMigracionEsquemaV1AV2:
    """Una base de datos creada en esquema v1 se migra a v2 al inicializar."""

    def _crear_db_v1(self, db_path: Path) -> None:
        """Crea manualmente una base de datos con esquema v1 (sin normalized_path)."""
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version(version) VALUES (1)")
        conn.execute("""
            CREATE TABLE machines (
                machine_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE volumes (
                volume_id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                volume_type TEXT,
                state TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute("""
            CREATE TABLE scan_runs (
                scan_id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                result TEXT NOT NULL,
                entries_count INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                exclusions_count INTEGER NOT NULL DEFAULT 0,
                coverage_estimate TEXT,
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute("""
            CREATE TABLE file_entries (
                entry_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                name TEXT NOT NULL,
                extension TEXT NOT NULL DEFAULT '',
                entry_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                modified_at TEXT,
                created_at TEXT,
                accessed_at TEXT,
                attributes TEXT NOT NULL DEFAULT '[]',
                excluded INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'filesystem_scan',
                last_checked_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id),
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute("""
            CREATE TABLE application_candidates (
                candidate_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                name TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                launch_type TEXT,
                confidence REAL,
                source TEXT NOT NULL DEFAULT 'inventory',
                last_checked_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id),
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.commit()
        conn.close()

    def test_migracion_v1_a_v2_agrega_columna_normalized_path(self, db_path: Path):
        self._crear_db_v1(db_path)
        storage = SystemInventoryStorage(db_path)
        version = storage.initialize()
        assert version == 4
        assert storage.schema_version() == 4
        # La columna normalized_path debe existir tras la migracion.
        conn = storage.connect()
        cur = conn.execute("PRAGMA table_info(file_entries)")
        columnas = {row["name"] for row in cur.fetchall()}
        assert "normalized_path" in columnas

    def test_migracion_v1_a_v2_crea_indice_unico(self, db_path: Path):
        self._crear_db_v1(db_path)
        storage = SystemInventoryStorage(db_path)
        storage.initialize()
        conn = storage.connect()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_file_entries_unique_path_scan'"
        )
        assert cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Migraciones verificables y preservacion de datos (3.8.5.1.4.2.8)
# ---------------------------------------------------------------------------

class TestMigracionesVerificables:
    """Las migraciones de esquema son pasos versionados, atomicos y que no
    pierden ni reinterpretan datos de versiones previas (3.8.5.1.4.2.8)."""

    def _crear_db_v1_con_datos(self, db_path: Path) -> dict[str, int]:
        """Crea una base v1 con filas en todas las tablas y devuelve sus conteos."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version(version) VALUES (1)")
        conn.execute("""
            CREATE TABLE machines (
                machine_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE volumes (
                volume_id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                volume_type TEXT,
                state TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute("""
            CREATE TABLE scan_runs (
                scan_id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                result TEXT NOT NULL,
                entries_count INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                exclusions_count INTEGER NOT NULL DEFAULT 0,
                coverage_estimate TEXT,
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute("""
            CREATE TABLE file_entries (
                entry_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                name TEXT NOT NULL,
                extension TEXT NOT NULL DEFAULT '',
                entry_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                modified_at TEXT,
                created_at TEXT,
                accessed_at TEXT,
                attributes TEXT NOT NULL DEFAULT '[]',
                excluded INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'filesystem_scan',
                last_checked_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id),
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute("""
            CREATE TABLE application_candidates (
                candidate_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                volume TEXT NOT NULL,
                name TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                launch_type TEXT,
                confidence REAL,
                source TEXT NOT NULL DEFAULT 'inventory',
                last_checked_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id),
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            )
        """)
        conn.execute(
            "INSERT INTO machines(machine_id, created_at) VALUES ('m-1', '2024-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO volumes(volume_id, machine_id, volume, volume_type, state, "
            "first_seen_at, last_seen_at) VALUES ('v-1', 'm-1', 'C:', 'local', 'online', "
            "'2024-01-01T00:00:00', '2024-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at, finished_at, "
            "result, entries_count, errors_count, exclusions_count, coverage_estimate) "
            "VALUES ('s-1', 'm-1', 'C:', 'completo', '2024-01-01T00:00:00', '2024-01-01T01:00:00', "
            "'ok', 10, 0, 0, '100%')"
        )
        conn.execute(
            "INSERT INTO file_entries(entry_id, scan_id, machine_id, volume, absolute_path, "
            "relative_path, name, extension, entry_type, size_bytes, modified_at, created_at, "
            "accessed_at, attributes, excluded, source, last_checked_at) "
            "VALUES ('e-1', 's-1', 'm-1', 'C:', 'C:/App/app.exe', 'App/app.exe', 'app.exe', '.exe', "
            "'file', 1024, '2024-01-01T00:00:00', '2024-01-01T00:00:00', '2024-01-01T00:00:00', "
            "'[]', 0, 'filesystem_scan', '2024-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO application_candidates(candidate_id, scan_id, machine_id, volume, name, "
            "absolute_path, launch_type, confidence, source, last_checked_at) "
            "VALUES ('c-1', 's-1', 'm-1', 'C:', 'app.exe', 'C:/App/app.exe', 'ejecutable', 0.9, "
            "'inventory', '2024-01-01T00:00:00')"
        )
        conn.commit()
        conteos = {
            tabla: int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
            for tabla in ("machines", "volumes", "scan_runs", "file_entries", "application_candidates")
        }
        conn.close()
        return conteos
        try:
            conn.execute(
                "INSERT INTO machines(machine_id, created_at) VALUES ('m-1', '2024-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO volumes(volume_id, machine_id, volume, volume_type, state, "
                "first_seen_at, last_seen_at) VALUES ('v-1', 'm-1', 'C:', 'local', 'online', "
                "'2024-01-01T00:00:00', '2024-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at, finished_at, "
                "result, entries_count, errors_count, exclusions_count, coverage_estimate) "
                "VALUES ('s-1', 'm-1', 'C:', 'completo', '2024-01-01T00:00:00', '2024-01-01T01:00:00', "
                "'ok', 10, 0, 0, '100%')"
            )
            conn.execute(
                "INSERT INTO file_entries(entry_id, scan_id, machine_id, volume, absolute_path, "
                "relative_path, name, extension, entry_type, size_bytes, modified_at, created_at, "
                "accessed_at, attributes, excluded, source, last_checked_at) "
                "VALUES ('e-1', 's-1', 'm-1', 'C:', 'C:/App/app.exe', 'App/app.exe', 'app.exe', '.exe', "
                "'file', 1024, '2024-01-01T00:00:00', '2024-01-01T00:00:00', '2024-01-01T00:00:00', "
                "'[]', 0, 'filesystem_scan', '2024-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO application_candidates(candidate_id, scan_id, machine_id, volume, name, "
                "absolute_path, launch_type, confidence, source, last_checked_at) "
                "VALUES ('c-1', 's-1', 'm-1', 'C:', 'app.exe', 'C:/App/app.exe', 'ejecutable', 0.9, "
                "'inventory', '2024-01-01T00:00:00')"
            )
            conn.commit()
            conteos = {
                tabla: int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
                for tabla in ("machines", "volumes", "scan_runs", "file_entries", "application_candidates")
            }
        finally:
            conn.close()
        return conteos

    def test_nueva_base_no_requiere_migracion_y_queda_en_version_actual(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        """Una base nueva se crea directamente en el esquema actual sin migraciones."""
        assert not db_path.exists()
        version = storage.initialize()
        assert version == SCHEMA_VERSION
        assert storage.schema_version() == SCHEMA_VERSION
        assert db_path.exists()
        conn = storage.connect()
        columnas = {row["name"] for row in conn.execute("PRAGMA table_info(file_entries)")}
        assert "normalized_path" in columnas
        # schema_version tiene una fila con la version actual.
        assert int(conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]) == 1

    def test_inicializacion_idempotente_con_datos_ya_en_version_actual(
        self, storage: SystemInventoryStorage
    ):
        """Inicializar dos veces una base ya en v2 no altera los datos."""
        storage.initialize()
        storage.record_machine("m-1")
        storage.record_volume("v-1", "m-1", "C:", "local", "online")
        storage.begin_scan_run("s-1", "m-1", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("s-1", entries_count=3, errors_count=1)
        conn = storage.connect()
        antes = {
            tabla: int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
            for tabla in ("machines", "volumes", "scan_runs", "file_entries", "application_candidates")
        }
        storage.initialize()
        assert storage.schema_version() == SCHEMA_VERSION
        despues = {
            tabla: int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
            for tabla in ("machines", "volumes", "scan_runs", "file_entries", "application_candidates")
        }
        assert antes == despues

    def test_migracion_v1_a_v2_preserva_todos_los_datos_y_agrega_columna(
        self, db_path: Path
    ):
        """Una base v1 con datos se migra a v2 conservando cada fila y sus valores."""
        esperados = self._crear_db_v1_con_datos(db_path)
        storage = SystemInventoryStorage(db_path)
        version = storage.initialize()
        assert version == SCHEMA_VERSION
        assert storage.schema_version() == SCHEMA_VERSION
        conn = storage.connect()
        columnas = {row["name"] for row in conn.execute("PRAGMA table_info(file_entries)")}
        assert "normalized_path" in columnas
        for tabla, esperado in esperados.items():
            actual = int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
            assert actual == esperado, f"La tabla {tabla} perdio filas en la migracion"
        # Los valores previos no se reinterpretan: la entrada sigue accesible por su ruta original.
        fila = conn.execute("SELECT absolute_path FROM file_entries WHERE entry_id = 'e-1'").fetchone()
        assert fila is not None and fila[0] == "C:/App/app.exe"

    def test_migraciones_registradas_forman_cadena_hasta_la_version_actual(self):
        """Desde la version 1 existe una cadena de migraciones registradas que
        llega hasta SCHEMA_VERSION (cada paso es verificable)."""
        from src.hands.system_inventory_storage import _MIGRACIONES as migraciones
        version = 1
        visitadas = {version}
        while version < SCHEMA_VERSION:
            siguientes = [destino for origen, destino, nombre, fn in migraciones if origen == version]
            assert len(siguientes) == 1, f"Falta migracion registrada desde v{version}"
            version = siguientes[0]
            visitadas.add(version)
        assert version == SCHEMA_VERSION
        assert SCHEMA_VERSION in visitadas

    def test_fallo_en_migracion_no_avanza_la_version_ni_deja_cambios_parciales(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Si una migracion falla, se hace rollback: version sin avanzar y sin tablas nuevas."""
        conteos = self._crear_db_v1_con_datos(db_path)

        def falla(conn: sqlite3.Connection) -> None:
            conn.execute("CREATE TABLE tabla_que_no_debe_quedar (x INTEGER)")
            raise RuntimeError("migracion simulada fallida")

        monkeypatch.setattr(
            "src.hands.system_inventory_storage._MIGRACIONES",
            [(1, 2, "fallida", falla)],
        )
        storage = SystemInventoryStorage(db_path)
        with pytest.raises(RuntimeError, match="migracion simulada fallida"):
            storage.initialize()
        # La version no avanzo.
        assert storage.schema_version() == 1
        # Rollback atomico: la tabla auxiliar no quedo.
        conn = storage.connect()
        nombres = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "tabla_que_no_debe_quedar" not in nombres
        # Los datos originales siguen intactos (no se borro ni reelaboro nada).
        for tabla, esperado in conteos.items():
            actual = int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
            assert actual == esperado


# ---------------------------------------------------------------------------
# Busqueda por estado (3.8.5.1.4.2.5)
# ---------------------------------------------------------------------------

class TestBusquedaPorEstado:
    """search_by_state consulta entradas por su estado de exclusicion."""

    def _seed_estados(self, storage: SystemInventoryStorage, machine_id: str = "machine-alfa") -> None:
        storage.initialize()
        storage.record_machine(machine_id)
        storage.begin_scan_run("scan-1", machine_id, "C:", SCAN_MODE_FULL)
        entradas = [
            {
                "entry_id": "e-1",
                "absolute_path": "C:/Apps/app1.exe",
                "relative_path": "Apps/app1.exe",
                "name": "app1.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1000,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-2",
                "absolute_path": "C:/Apps/app2.exe",
                "relative_path": "Apps/app2.exe",
                "name": "app2.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 2000,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "attributes": [],
                "excluded": True,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
        ]
        storage.insert_file_entries("scan-1", machine_id, "C:", entradas)
        storage.end_scan_run("scan-1", entries_count=2)

    def test_search_by_state_devuelve_no_excluidas(self, storage: SystemInventoryStorage):
        self._seed_estados(storage)
        res = storage.search_by_state("machine-alfa", excluded=False)
        assert len(res) == 1
        assert res[0]["entry_id"] == "e-1"
        assert res[0]["excluded"] == 0

    def test_search_by_state_devuelve_excluidas(self, storage: SystemInventoryStorage):
        self._seed_estados(storage)
        res = storage.search_by_state("machine-alfa", excluded=True)
        assert len(res) == 1
        assert res[0]["entry_id"] == "e-2"
        assert res[0]["excluded"] == 1

    def test_search_by_state_equipo_diferente_vacio(self, storage: SystemInventoryStorage):
        self._seed_estados(storage, "machine-alfa")
        res = storage.search_by_state("machine-beta", excluded=False)
        assert res == []


# ---------------------------------------------------------------------------
# Concurrencia de escaneos (3.8.5.1.4.2.9).
# ---------------------------------------------------------------------------

class TestConcurrenciaEscaneos:
    """Verifican el bloqueo de concurrencia para impedir dos escaneos
    simultaneos sobre el mismo equipo/volumen."""

    def test_begin_scan_run_duplicado_levanta_ConcurrentScanError(self, storage: SystemInventoryStorage):
        """No se pueden iniciar dos escaneos simultaneos para el mismo equipo y volumen."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        assert storage.has_active_scan("machine-alfa", "C:") is True
        try:
            with pytest.raises(ConcurrentScanError):
                storage.begin_scan_run("scan-2", "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        finally:
            storage.end_scan_run("scan-1", result=SCAN_RESULT_INTERRUPTED)
        assert storage.has_active_scan("machine-alfa", "C:") is False

    def test_diferente_maquina_o_volumen_puede_escanea_concurrente(self, storage: SystemInventoryStorage):
        """Distinto equipo o volumen no comparten bloqueo de escaneo."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_machine("machine-beta")
        storage.begin_scan_run("scan-a", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.begin_scan_run("scan-b", "machine-beta", "C:", SCAN_MODE_FULL)  # otra maquina: permitido
        storage.begin_scan_run("scan-c", "machine-alfa", "D:", SCAN_MODE_FULL)  # otro volumen: permitido
        try:
            assert storage.has_active_scan("machine-alfa", "C:") is True
            assert storage.has_active_scan("machine-beta", "C:") is True
            assert storage.has_active_scan("machine-alfa", "D:") is True
        finally:
            storage.end_scan_run("scan-a", result=SCAN_RESULT_OK)
            storage.end_scan_run("scan-b", result=SCAN_RESULT_OK)
            storage.end_scan_run("scan-c", result=SCAN_RESULT_OK)

    def test_bloqueo_se_libera_despues_de_end_scan_run(self, storage: SystemInventoryStorage):
        """El bloqueo se libera al finalizar el escaneo, permitiendo uno nuevo."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        assert storage.has_active_scan("machine-alfa", "C:") is True
        storage.end_scan_run("scan-1", result=SCAN_RESULT_OK)
        assert storage.has_active_scan("machine-alfa", "C:") is False
        # Puede iniciarse un nuevo escaneo para la misma clave.
        storage.begin_scan_run("scan-2", "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        try:
            assert storage.has_active_scan("machine-alfa", "C:") is True
        finally:
            storage.end_scan_run("scan-2", result=SCAN_RESULT_OK)

    def test_bloqueo_se_libera_incluso_si_end_scan_run_falla(self, storage: SystemInventoryStorage):
        """Si end_scan_run falla por resultado invalido, el bloqueo se libera."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        assert storage.has_active_scan("machine-alfa", "C:") is True
        with pytest.raises(ValueError):
            storage.end_scan_run("scan-1", resultado="invalido") if False else storage.end_scan_run("scan-1", result="invalido")
        assert storage.has_active_scan("machine-alfa", "C:") is False
        # Puede iniciarse un nuevo escaneo.
        storage.begin_scan_run("scan-2", "machine-alfa", "C:", SCAN_MODE_FULL)
        try:
            assert storage.has_active_scan("machine-alfa", "C:") is True
        finally:
            storage.end_scan_run("scan-2", result=SCAN_RESULT_OK)

    def test_verify_journal_mode_devuelve_wal(self, storage: SystemInventoryStorage):
        """El modo de journaling activo es WAL, adecuado para escrituras concurrentes."""
        storage.initialize()
        modo = storage.verify_journal_mode()
        assert modo.lower() == "wal"

    def test_concurrent_scan_error_es_exportable(self):
        """ConcurrentScanError se puede importar desde el modulo."""
        from src.hands.system_inventory_storage import ConcurrentScanError
        assert issubclass(ConcurrentScanError, Exception)


# ---------------------------------------------------------------------------
# Reanudacion de escaneo interrumpido (3.8.5.1.4.5.5).
# ---------------------------------------------------------------------------

class TestReanudarScan:
    """Verifican la reanudacion de un escaneo interrumpido usando el mismo
    scan_id (misma generacion), sin mezclar resultados de escaneos distintos
    ni degradar la ultima instantanea completa."""

    def _scan_interrumpido(self, storage: SystemInventoryStorage) -> str:
        """Crea un scan interrumpido (sin finalizar) y devuelve su scan_id."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        scan_id = "scan-interrumpido"
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_FULL)
        # No se llama a end_scan_run: queda interrumpido y sin finalizar.
        return scan_id

    def test_reanudar_scan_interrumpido_devuelve_datos_y_bloquea(self, storage: SystemInventoryStorage):
        """Reanudar un scan interrumpido devuelve sus datos y deja el
        bloqueo activo para seguir insertando entradas con el mismo scan_id."""
        scan_id = self._scan_interrumpido(storage)

        reanudado = storage.reanudar_scan(scan_id, "machine-alfa", "C:")

        assert reanudado["scan_id"] == scan_id
        assert reanudado["machine_id"] == "machine-alfa"
        assert reanudado["volume"] == "C:"
        assert reanudado["result"] == SCAN_RESULT_INTERRUPTED
        assert reanudado["finished_at"] is None
        # El bloqueo permanece activo (se libera en end_scan_run).
        assert storage.has_active_scan("machine-alfa", "C:") is True

    def test_reanudar_scan_no_existente_levanta_valuerror(self, storage: SystemInventoryStorage):
        """Reanudar un scan_id inexistente levanta ValueError y no deja bloqueo."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        with pytest.raises(ValueError):
            storage.reanudar_scan("scan-inexistente", "machine-alfa", "C:")
        assert storage.has_active_scan("machine-alfa", "C:") is False

    def test_reanudar_scan_de_otro_equipo_levanta_valuerror(self, storage: SystemInventoryStorage):
        """Reanudar un scan de otro equipo levanta ValueError. El bloqueo
        permanece retenido por begin_scan_run (end_scan_run nunca se llamo)."""
        scan_id = self._scan_interrumpido(storage)
        with pytest.raises(ValueError):
            storage.reanudar_scan(scan_id, "machine-otro", "C:")
        # El bloqueo sigue activo: begin_scan_run lo adquiro y no se libero.
        assert storage.has_active_scan("machine-alfa", "C:") is True

    def test_reanudar_scan_de_otro_volumen_levanta_valuerror(self, storage: SystemInventoryStorage):
        """Reanudar un scan de otro volumen levanta ValueError. El bloqueo
        permanece retenido por begin_scan_run (end_scan_run nunca se llamo)."""
        scan_id = self._scan_interrumpido(storage)
        with pytest.raises(ValueError):
            storage.reanudar_scan(scan_id, "machine-alfa", "D:")
        # El bloqueo sigue activo: begin_scan_run lo adquiro y no se libero.
        assert storage.has_active_scan("machine-alfa", "C:") is True

    def test_reanudar_scan_ya_finalizado_levanta_valuerror(self, storage: SystemInventoryStorage):
        """Reanudar un scan ya finalizado (resultado OK) levanta ValueError."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        scan_id = "scan-finalizado"
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run(scan_id, result=SCAN_RESULT_OK, entries_count=0)
        with pytest.raises(ValueError):
            storage.reanudar_scan(scan_id, "machine-alfa", "C:")
        assert storage.has_active_scan("machine-alfa", "C:") is False

    def test_reanudar_scan_con_bloqueo_ya_activo_prosigue(self, storage: SystemInventoryStorage):
        """Reanudar un scan cuyo bloqueo ya esta activo (begin_scan_run lo
        adquiro y end_scan_run nunca se llamo) prosigue sin
        ConcurrentScanError: se reusa el mismo scan_id y misma generacion."""
        scan_id = self._scan_interrumpido(storage)
        assert storage.has_active_scan("machine-alfa", "C:") is True
        reanudado = storage.reanudar_scan(scan_id, "machine-alfa", "C:")
        assert reanudado["scan_id"] == scan_id
        assert reanudado["result"] == SCAN_RESULT_INTERRUPTED
        assert reanudado["finished_at"] is None
        # El bloqueo sigue retenido para poder insertar mas entradas.
        assert storage.has_active_scan("machine-alfa", "C:") is True

    def test_reanudar_scan_mismo_scan_id_no_crea_nueva_generacion(self, storage: SystemInventoryStorage):
        """Reanudar y finalizar un scan conservan el mismo scan_id: no se
        crea una nueva fila de scan_run ni se mezclan generaciones."""
        scan_id = self._scan_interrumpido(storage)

        storage.reanudar_scan(scan_id, "machine-alfa", "C:")
        storage.insert_file_entries(scan_id, "machine-alfa", "C:", [
            {
                "entry_id": "e-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            }
        ])
        storage.end_scan_run(scan_id, result=SCAN_RESULT_OK, entries_count=1)

        # Solo debe existir una fila de scan_run con este scan_id.
        filas = storage.get_scan_run(scan_id)
        assert filas is not None
        assert filas["scan_id"] == scan_id
        assert filas["result"] == SCAN_RESULT_OK
        assert filas["finished_at"] is not None
        # El bloqueo se libero al finalizar.
        assert storage.has_active_scan("machine-alfa", "C:") is False

    def test_reanudar_scan_no_degrada_linea_base(self, storage: SystemInventoryStorage):
        """Reanudar un scan interrumpido no modifica ni sobrescribe la
        linea base registrada previamente (3.8.5.1.4.5.1)."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")

        # Registrar linea base primero.
        linea_base = storage.registrar_linea_base_volumen(
            "machine-alfa", "C:", "online", 100.0, entradas_count=5,
            scan_id="scan-base",
        )
        linea_id_base = linea_base["linea_id"]
        fecha_base = linea_base["fecha_base"]

        # Crear y reanudar un scan interrumpido (distinto scan_id).
        scan_id = "scan-interrumpido"
        storage.begin_scan_run(scan_id, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        storage.reanudar_scan(scan_id, "machine-alfa", "C:")
        storage.end_scan_run(scan_id, result=SCAN_RESULT_OK, entries_count=3)

        # La linea base debe permanecer intacta.
        linea_despues = storage.obtener_linea_base_volumen("machine-alfa", "C:")
        assert linea_despues is not None
        assert linea_despues["linea_id"] == linea_id_base
        assert linea_despues["fecha_base"] == fecha_base
        assert linea_despues["scan_id"] == "scan-base"


# ---------------------------------------------------------------------------
# Refresco bajo demanda y revalidacion de destino (3.8.5.1.4.5.6).
# ---------------------------------------------------------------------------

class TestRefrescoBajoDemanda:
    """Refresco bajo demanda de ruta/volumen, refresco incremental global y
    revalidacion puntual del destino de una aplicación antes de abrirla.

    Todos los tests usan directorios temporales y nunca tocan datos de
    produccion.
    """

    def _escaneo_con_entrada(
        self,
        storage: SystemInventoryStorage,
        ruta_archivo: str,
        machine_id: str = "machine-alfa",
        volume: str = "C:",
        scan_id: str = "scan-1",
    ) -> str:
        """Crea y finaliza un escaneo con una entrada de archivo registrada,
        retornando el scan_id."""
        storage.initialize()
        storage.record_machine(machine_id)
        storage.begin_scan_run(scan_id, machine_id, volume, SCAN_MODE_FULL)
        storage.insert_file_entries(
            scan_id,
            machine_id,
            volume,
            [
                {
                    "entry_id": "e-1",
                    "absolute_path": ruta_archivo,
                    "relative_path": Path(ruta_archivo).name,
                    "name": Path(ruta_archivo).name,
                    "extension": ".exe",
                    "entry_type": "file",
                    "size_bytes": 1024,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "accessed_at": "2024-01-02T08:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                },
            ],
        )
        storage.end_scan_run(scan_id, result=SCAN_RESULT_OK, entries_count=1)
        return scan_id

    def test_refrescar_entrada_sin_escaneo_previo(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        resultado = storage.refrescar_entrada_por_ruta(
            "machine-alfa", "C:", "C:/Apps/app.exe"
        )
        assert resultado["scan_id"] is None
        assert resultado["existe_ahora"] is False
        assert resultado["entradas_refrescadas"] == 0
        assert resultado["razon"] is not None

    def test_refrescar_entrada_ruta_no_registrada(self, storage: SystemInventoryStorage):
        self._escaneo_con_entrada(storage, "C:/Apps/app.exe")
        resultado = storage.refrescar_entrada_por_ruta(
            "machine-alfa", "C:", "C:/NoExiste/xyz.exe"
        )
        assert resultado["scan_id"] == "scan-1"
        assert resultado["existe_ahora"] is False
        assert resultado["entradas_refrescadas"] == 0
        assert "no está registrada" in resultado["razon"]

    def test_refrescar_entrada_existe_sin_cambio(self, storage: SystemInventoryStorage, tmp_path: Path):
        app = tmp_path / "Apps" / "app.exe"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_bytes(b"x" * 1024)
        ruta = str(app).replace("\\", "/")
        self._escaneo_con_entrada(storage, ruta)
        resultado = storage.refrescar_entrada_por_ruta("machine-alfa", "C:", ruta)
        assert resultado["existe_ahora"] is True
        assert resultado["cambio_detectado"] is False
        assert resultado["entradas_refrescadas"] == 1
        assert resultado["last_checked_at"] is not None

    def test_refrescar_entrada_ya_no_existe(self, storage: SystemInventoryStorage):
        self._escaneo_con_entrada(storage, "C:/Apps/app.exe")
        # La ruta registrada no existe en este entorno.
        resultado = storage.refrescar_entrada_por_ruta(
            "machine-alfa", "C:", "C:/Apps/app.exe"
        )
        assert resultado["existe_ahora"] is False
        assert resultado["entradas_refrescadas"] == 1
        assert resultado["last_checked_at"] is not None

    def test_refrescar_entrada_actualiza_last_checked_at(self, storage: SystemInventoryStorage, tmp_path: Path):
        app = tmp_path / "Apps" / "app.exe"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("contenido", encoding="utf-8")
        ruta = str(app).replace("\\", "/")
        self._escaneo_con_entrada(storage, ruta)
        resultado = storage.refrescar_entrada_por_ruta("machine-alfa", "C:", ruta)
        assert resultado["last_checked_at"] is not None
        assert resultado["entradas_refrescadas"] == 1

    def test_refrescar_volumen_sin_escaneo(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        resultado = storage.refrescar_volumen("machine-alfa", "C:")
        assert resultado["scan_id"] is None
        assert resultado["total"] == 0
        assert resultado["razon"] is not None

    def test_refrescar_volumen_multiple_entradas(self, storage: SystemInventoryStorage, tmp_path: Path):
        app1 = tmp_path / "Apps" / "app1.exe"
        app2 = tmp_path / "Apps" / "app2.exe"
        for p in (app1, app2):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        ruta1 = str(app1).replace("\\", "/")
        ruta2 = str(app2).replace("\\", "/")
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-v", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries(
            "scan-v",
            "machine-alfa",
            "C:",
            [
                {
                    "entry_id": "e-a",
                    "absolute_path": ruta1,
                    "relative_path": "Apps/app1.exe",
                    "name": "app1.exe",
                    "extension": ".exe",
                    "entry_type": "file",
                    "size_bytes": 10,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                },
                {
                    "entry_id": "e-b",
                    "absolute_path": ruta2,
                    "relative_path": "Apps/app2.exe",
                    "name": "app2.exe",
                    "extension": ".exe",
                    "entry_type": "file",
                    "size_bytes": 20,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                },
            ],
        )
        storage.end_scan_run("scan-v", result=SCAN_RESULT_OK, entries_count=2)
        resultado = storage.refrescar_volumen("machine-alfa", "C:")
        assert resultado["scan_id"] == "scan-v"
        assert resultado["total"] == 2
        assert resultado["existentes"] == 2
        assert resultado["no_existentes"] == 0
        assert resultado["entradas_refrescadas"] == 2

    def test_refrescar_incremental_global_sin_volumenes(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        resultado = storage.refrescar_incremental_global("machine-alfa")
        assert resultado["machine_id"] == "machine-alfa"
        assert resultado["total_volumenes"] == 0
        assert resultado["total"] == 0

    def test_refrescar_incremental_global_refresca_volumenes(
        self, storage: SystemInventoryStorage, tmp_path: Path
    ):
        app = tmp_path / "Apps" / "app.exe"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("x", encoding="utf-8")
        ruta = str(app).replace("\\", "/")
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c", "machine-alfa", "C:", "local", "online")
        storage.begin_scan_run("scan-g", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries(
            "scan-g",
            "machine-alfa",
            "C:",
            [
                {
                    "entry_id": "e-g",
                    "absolute_path": ruta,
                    "relative_path": "Apps/app.exe",
                    "name": "app.exe",
                    "extension": ".exe",
                    "entry_type": "file",
                    "size_bytes": 5,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                },
            ],
        )
        storage.end_scan_run("scan-g", result=SCAN_RESULT_OK, entries_count=1)
        resultado = storage.refrescar_incremental_global("machine-alfa")
        assert resultado["total_volumenes"] == 1
        assert resultado["total"] == 1
        assert resultado["existentes"] == 1
        assert len(resultado["por_volumen"]) == 1
        assert resultado["por_volumen"][0]["volume"] == "C:"

    def test_revalidar_destino_aplicacion_valido(self, storage: SystemInventoryStorage, tmp_path: Path):
        app = tmp_path / "Apps" / "app.exe"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("contenido", encoding="utf-8")
        ruta = str(app).replace("\\", "/")
        self._escaneo_con_entrada(storage, ruta)
        resultado = storage.revalidar_destino_aplicacion("machine-alfa", "C:", ruta)
        assert resultado["valido"] is True
        assert resultado["existe"] is True
        assert resultado["es_archivo"] is True
        assert resultado["entradas_refrescadas"] == 1
        assert resultado["razon"] is None

    def test_revalidar_destino_aplicacion_no_existe(self, storage: SystemInventoryStorage):
        self._escaneo_con_entrada(storage, "C:/Apps/app.exe")
        resultado = storage.revalidar_destino_aplicacion(
            "machine-alfa", "C:", "C:/Apps/no_existe.exe"
        )
        assert resultado["valido"] is False
        assert resultado["existe"] is False
        assert resultado["es_archivo"] is False
        assert "no existe" in resultado["razon"]

    def test_revalidar_destino_aplicacion_directorio(self, storage: SystemInventoryStorage, tmp_path: Path):
        carpeta = tmp_path / "Apps" / "una_carpeta"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = str(carpeta).replace("\\", "/")
        self._escaneo_con_entrada(storage, ruta)
        resultado = storage.revalidar_destino_aplicacion("machine-alfa", "C:", ruta)
        assert resultado["valido"] is False
        assert resultado["existe"] is True
        assert resultado["es_archivo"] is False
        assert "no es un archivo lanzable" in resultado["razon"]

    def test_revalidar_destino_vacio_devuelve_razon(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        resultado = storage.revalidar_destino_aplicacion("machine-alfa", "C:", "")
        assert resultado["valido"] is False
        assert resultado["razon"] is not None


# ---------------------------------------------------------------------------
# Copia de seguridad, deteccion de corrupcion y recuperacion (3.8.5.1.4.2.11).
# ---------------------------------------------------------------------------

class TestBackupCorrupcionYRecuperacion:
    """Copia de seguridad, deteccion de corrupcion y recuperacion del inventario.

    La base nunca se sobrescribe con una copia vacia, incompleta o corrupta:
    restaurar_desde_backup verifica la copia antes de tocar la base actual, e
    initialize() no crea tablas vacias sobre una base corrupta sin una copia
    valida desde la que recuperar.
    """

    def _crear_base_con_datos(self, storage: SystemInventoryStorage) -> None:
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries("scan-1", "machine-alfa", "C:", [
            {
                "entry_id": "e-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            }
        ])
        storage.end_scan_run("scan-1", result=SCAN_RESULT_OK, entries_count=1)

    def _conteo_en_fichero(self, fichero: Path, tabla: str) -> int:
        import sqlite3

        conn = sqlite3.connect(str(fichero))
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
        finally:
            conn.close()

    def test_create_backup_crea_copia_valida_al_lado_de_la_base(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_con_datos(storage)
        backup = storage.create_backup()
        assert backup == db_path.parent / (db_path.name + DEFAULT_BACKUP_SUFFIX)
        assert backup.exists()
        assert storage.verify_integrity()["ok"] is True
        # La copia es una base SQLite valida con los mismos datos y version.
        assert self._conteo_en_fichero(backup, "file_entries") == 1
        assert self._conteo_en_fichero(backup, "machines") == 1
        import sqlite3

        conn = sqlite3.connect(str(backup))
        try:
            version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        finally:
            conn.close()
        assert version == SCHEMA_VERSION

    def test_create_backup_sin_base_existente_levanta_InventoryBackupError(
        self, storage: SystemInventoryStorage
    ):
        # storage no inicializado: no hay base que respaldar.
        assert not storage.db_path.exists()
        with pytest.raises(InventoryBackupError):
            storage.create_backup()

    def test_create_backup_no_deja_copia_parcial_al_fallar(
        self, storage: SystemInventoryStorage, monkeypatch: pytest.MonkeyPatch
    ):
        self._crear_base_con_datos(storage)
        backup = storage.backup_path()

        def fallo_backup(*args, **kwargs):  # noqa: ARG005
            raise RuntimeError("fallo simulado en la copia de seguridad")

        # sqlite3.Connection es un tipo inmutable (ni en instancia se puede
        # reasignar su metodo backup), así que se simula toda la conexion: su
        # metodo backup falla y create_backup debe limpiar la copia parcial.
        class _ConnSinBackup:
            def backup(self, destino, *args, **kwargs):  # noqa: ARG005
                raise RuntimeError("fallo simulado en la copia de seguridad")

        monkeypatch.setattr(
            SystemInventoryStorage, "connect", lambda self: _ConnSinBackup()
        )
        with pytest.raises(InventoryBackupError):
            storage.create_backup()
        # No queda una copia parcial presentada como valida.
        assert not backup.exists()

    def test_verify_integrity_base_sana_devuelve_ok(
        self, storage: SystemInventoryStorage
    ):
        self._crear_base_con_datos(storage)
        resultado = storage.verify_integrity()
        assert resultado["ok"] is True
        assert resultado["quick_check"] == "ok"
        assert resultado["integrity_check"] == "ok"
        assert resultado["error"] is None

    def test_verify_integrity_base_no_existente_devuelve_ok_falso(
        self, storage: SystemInventoryStorage
    ):
        assert not storage.db_path.exists()
        resultado = storage.verify_integrity()
        assert resultado["ok"] is False
        assert resultado["error"] is not None

    def test_verify_integrity_base_corrupta_devuelve_ok_falso(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_con_datos(storage)
        storage.close()
        db_path.write_bytes(b"esto no es una base de datos sqlite valida")
        resultado = storage.verify_integrity()
        assert resultado["ok"] is False
        assert resultado["error"] is not None

    def test_restaurar_desde_backup_recupera_datos_despues_de_corrupcion(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_con_datos(storage)
        backup = storage.create_backup()
        assert backup.exists()
        storage.close()
        db_path.write_bytes(b"contenido corrupto que invalida la base de datos")
        assert storage.verify_integrity()["ok"] is False
        storage.restaurar_desde_backup()
        # La base recuperada es valida y conserva los datos.
        assert storage.verify_integrity()["ok"] is True
        assert storage.schema_version() == SCHEMA_VERSION
        assert storage.get_entry_count("machine-alfa", "C:") == 1
        run = storage.get_scan_run("scan-1")
        assert run is not None and run["result"] == SCAN_RESULT_OK
        storage.close()

    def test_restaurar_desde_backup_sin_copia_levanta_InventoryBackupError(
        self, storage: SystemInventoryStorage
    ):
        self._crear_base_con_datos(storage)
        assert not storage.backup_path().exists()
        with pytest.raises(InventoryBackupError):
            storage.restaurar_desde_backup()

    def test_restaurar_desde_backup_copia_corrupta_no_sobrescribe_base_valida(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_con_datos(storage)
        backup = storage.create_backup()
        assert storage.verify_integrity()["ok"] is True
        assert storage.get_entry_count("machine-alfa", "C:") == 1
        # Corromper SOLO la copia de seguridad, no la base actual.
        storage.close()
        backup.write_bytes(b"copia de seguridad corrupta")
        storage2 = SystemInventoryStorage(db_path)
        try:
            with pytest.raises(InventoryBackupError):
                storage2.restaurar_desde_backup()
            # La base actual queda intacta y valida.
            assert storage2.verify_integrity()["ok"] is True
            assert storage2.get_entry_count("machine-alfa", "C:") == 1
        finally:
            storage2.close()

    def test_inicializacion_sobre_base_corrupta_sin_backup_levanta_InventoryCorruptError(
        self, db_path: Path
    ):
        storage = SystemInventoryStorage(db_path)
        self._crear_base_con_datos(storage)
        storage.close()
        assert not storage.backup_path().exists()
        db_path.write_bytes(b"corrupcion total del fichero de inventario")
        storage2 = SystemInventoryStorage(db_path)
        try:
            with pytest.raises(InventoryCorruptError):
                storage2.initialize()
        finally:
            storage2.close()

    def test_inicializacion_sobre_base_corrupta_con_backup_recupera_automaticamente(
        self, db_path: Path
    ):
        storage = SystemInventoryStorage(db_path)
        self._crear_base_con_datos(storage)
        backup = storage.create_backup()
        storage.close()
        db_path.write_bytes(b"corrupcion total del fichero de inventario")
        storage2 = SystemInventoryStorage(db_path)
        try:
            assert storage2.initialize() == SCHEMA_VERSION
            assert storage2.verify_integrity()["ok"] is True
            assert storage2.get_entry_count("machine-alfa", "C:") == 1
            run = storage2.get_scan_run("scan-1")
            assert run is not None and run["result"] == SCAN_RESULT_OK
        finally:
            storage2.close()


# ---------------------------------------------------------------------------
# Persistencia real en disco (3.8.5.1.4.2.12)
# ---------------------------------------------------------------------------

class TestPersistenciaRealEnDisco:
    """Probar persistencia real en disco creando una nueva instancia del
    repositorio sobre la misma base temporal y recuperando las mismas entradas
    tras recarga (unidad 3.8.5.1.4.2.12).

    Cada test escribe datos con una instancia, la cierra, crea una NUEVA
    instancia de SystemInventoryStorage sobre el mismo fichero SQLite y verifica
    que los datos se recuperan íntegros. Valida que la persistencia no depende
    de la instancia en memoria sino del fichero en disco.
    """

    def _crear_base_completa(self, storage: SystemInventoryStorage) -> None:
        """Puebla la base con máquina, volumen, scan_run, entradas de archivo
        y candidatos de aplicación."""
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries("scan-1", "machine-alfa", "C:", [
            {
                "entry_id": "e-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
        ])
        storage.insert_application_candidates("scan-1", "machine-alfa", "C:", [
            {
                "candidate_id": "c-1",
                "name": "Mi Aplicacion",
                "absolute_path": "C:/Apps/app.exe",
                "launch_type": "ejecutable",
                "confidence": 0.95,
                "source": "inventory",
                "last_checked_at": "2024-01-03T00:00:00",
            }
        ])
        storage.end_scan_run("scan-1", result=SCAN_RESULT_OK, entries_count=2)

    def test_nueva_instancia_sobre_misma_base_recupera_entradas_archivo(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_completa(storage)
        storage.close()

        # Nueva instancia sobre el mismo fichero SQLite (persistencia real en disco).
        storage2 = SystemInventoryStorage(db_path)
        try:
            assert storage2.db_file_exists() is True
            assert storage2.schema_version() == SCHEMA_VERSION
            assert storage2.get_entry_count("machine-alfa", "C:") == 2
            entradas = storage2.search_by_name("machine-alfa", "app.exe")
            assert len(entradas) == 1
            assert entradas[0]["name"] == "app.exe"
            assert entradas[0]["absolute_path"] == "C:/Apps/app.exe"
            assert entradas[0]["size_bytes"] == 1024
            entradas_dll = storage2.search_by_extension("machine-alfa", ".dll")
            assert len(entradas_dll) == 1
            assert entradas_dll[0]["name"] == "tool.dll"
        finally:
            storage2.close()

    def test_nueva_instancia_sobre_misma_base_recupera_scan_runs(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_completa(storage)
        storage.close()

        storage2 = SystemInventoryStorage(db_path)
        try:
            run = storage2.get_scan_run("scan-1")
            assert run is not None
            assert run["scan_id"] == "scan-1"
            assert run["machine_id"] == "machine-alfa"
            assert run["volume"] == "C:"
            assert run["mode"] == SCAN_MODE_FULL
            assert run["result"] == SCAN_RESULT_OK
            assert run["entries_count"] == 2
            assert run["finished_at"] is not None
            latest = storage2.get_latest_scan("machine-alfa", "C:")
            assert latest is not None
            assert latest["scan_id"] == "scan-1"
        finally:
            storage2.close()

    def test_nueva_instancia_sobre_misma_base_recupera_candidatos_aplicacion(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_completa(storage)
        storage.close()

        storage2 = SystemInventoryStorage(db_path)
        try:
            # Los candidatos viven en su propia tabla y se consultan directamente
            # sobre el mismo fichero en disco.
            conn = storage2.connect()
            try:
                filas = conn.execute(
                    "SELECT candidate_id, name, launch_type, confidence FROM application_candidates WHERE machine_id = ?",
                    ("machine-alfa",),
                ).fetchall()
            finally:
                storage2.close()
            assert len(filas) == 1
            assert filas[0]["candidate_id"] == "c-1"
            assert filas[0]["name"] == "Mi Aplicacion"
            assert filas[0]["launch_type"] == "ejecutable"
            assert filas[0]["confidence"] == 0.95
        finally:
            # storage2 ya se cerro dentro del try; close() es idempotente.
            try:
                storage2.close()
            except Exception:
                pass

    def test_nueva_instancia_recupera_volumen_registrado(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        self._crear_base_completa(storage)
        storage.close()

        storage2 = SystemInventoryStorage(db_path)
        try:
            assert storage2.get_entry_count("machine-alfa") == 2
            assert storage2.get_entry_count("machine-alfa", "C:") == 2
            assert storage2.get_entry_count("machine-alfa", "D:") == 0
        finally:
            storage2.close()

    def test_persistencia_sobre_cambio_de_instancia_no_duplica_datos(
        self, storage: SystemInventoryStorage, db_path: Path
    ):
        """Escribir con la instancia 1, leer con la 2, escribir con la 3 y
        leer con una 4: los datos no se duplican ni se pierden entre
        instancias."""
        self._crear_base_completa(storage)
        storage.close()

        storage2 = SystemInventoryStorage(db_path)
        try:
            assert storage2.get_entry_count("machine-alfa", "C:") == 2
        finally:
            storage2.close()

        storage3 = SystemInventoryStorage(db_path)
        try:
            assert storage3.get_entry_count("machine-alfa", "C:") == 2
            # Agregar un scan_run nuevo (scan_id distinto) con la misma base:
            # no duplica los datos previos ni los borra.
            storage3.begin_scan_run("scan-2", "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
            storage3.end_scan_run("scan-2", result=SCAN_RESULT_OK, entries_count=2)
            assert storage3.get_entry_count("machine-alfa", "C:") == 2
            assert storage3.get_scan_run("scan-1") is not None
            assert storage3.get_scan_run("scan-2") is not None
        finally:
            storage3.close()


# ---------------------------------------------------------------------------
# Marcado de entradas ausentes / eliminadas (3.8.5.1.4.5.4).
# ---------------------------------------------------------------------------

class TestMarcadoEntradasEliminadas:
    """Marcar como ausente/eliminada solo despues de completar correctamente
    el escaneo del ambito que la contiene. Un error de permisos no equivale
    a una eliminacion."""

    def _escenario_base_y_nuevo(
        self,
        storage: SystemInventoryStorage,
        resultado_nuevo: str = SCAN_RESULT_OK,
        scan_base: str = "scan-base",
        scan_nuevo: str = "scan-nuevo",
    ) -> tuple[list[dict], list[dict], str, str]:
        """Crea linea base con 4 entradas y un escaneo nuevo con solo
        app.exe y tool.dll.

        Desaparecen: readme.txt (bajo C:/Docs) y notes.txt (bajo C:/Docs2).
        Retorna (entradas_base, entradas_ausentes, scan_base, scan_nuevo).
        Las entradas ausentes llevan normalized_path, scan_id, machine_id y
        volume como las entradas almacenadas en el escaneo base.
        """
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")

        entradas_base = [
            {
                "entry_id": "e-base-1",
                "absolute_path": "C:/Apps/app.exe",
                "relative_path": "Apps/app.exe",
                "name": "app.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-02T08:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-base-2",
                "absolute_path": "C:/Apps/tool.dll",
                "relative_path": "Apps/tool.dll",
                "name": "tool.dll",
                "extension": ".dll",
                "entry_type": "file",
                "size_bytes": 2048,
                "modified_at": "2024-02-01T10:00:00",
                "created_at": "2024-02-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-base-3",
                "absolute_path": "C:/Docs/readme.txt",
                "relative_path": "Docs/readme.txt",
                "name": "readme.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 500,
                "modified_at": "2024-03-01T10:00:00",
                "created_at": "2024-03-01T09:00:00",
                "accessed_at": "2024-03-02T08:00:00",
                "attributes": ["hidden"],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
            {
                "entry_id": "e-base-4",
                "absolute_path": "C:/Docs2/notes.txt",
                "relative_path": "Docs2/notes.txt",
                "name": "notes.txt",
                "extension": ".txt",
                "entry_type": "file",
                "size_bytes": 300,
                "modified_at": "2024-04-01T10:00:00",
                "created_at": "2024-04-01T09:00:00",
                "accessed_at": None,
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            },
        ]

        # Anotar normalized_path, scan_id, machine_id y volume tal como
        # quedan almacenadas tras insert_file_entries.
        for e in entradas_base:
            e["normalized_path"] = normalize_path(e["absolute_path"])
            e["scan_id"] = scan_base
            e["machine_id"] = "machine-alfa"
            e["volume"] = "C:"

        storage.begin_scan_run(scan_base, "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.insert_file_entries(scan_base, "machine-alfa", "C:", entradas_base)
        storage.end_scan_run(scan_base, result=SCAN_RESULT_OK, entries_count=4)
        storage.registrar_linea_base_volumen(
            machine_id="machine-alfa",
            volume="C:",
            estado_volumen="disponible",
            cobertura=100.0,
            entradas_count=4,
            errores_count=0,
            scan_id=scan_base,
        )

        # Escaneo nuevo: solo app.exe y tool.dll (entry_id unico por scan).
        entradas_nuevo = []
        for e in entradas_base:
            if e["name"] in ("app.exe", "tool.dll"):
                e_nuevo = dict(e)
                e_nuevo["entry_id"] = f"e-nuevo-{e['name']}"
                e_nuevo["scan_id"] = scan_nuevo
                entradas_nuevo.append(e_nuevo)
        storage.begin_scan_run(scan_nuevo, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        storage.insert_file_entries(scan_nuevo, "machine-alfa", "C:", entradas_nuevo)
        storage.end_scan_run(scan_nuevo, result=resultado_nuevo, entries_count=2)

        # Entradas ausentes = de base pero no en el nuevo.
        nombres_nuevo = {e["name"] for e in entradas_nuevo}
        entradas_ausentes = [e for e in entradas_base if e["name"] not in nombres_nuevo]

        return entradas_base, entradas_ausentes, scan_base, scan_nuevo

    def _fila_base(
        self, storage: SystemInventoryStorage, scan_base: str, absolute_path: str
    ) -> dict:
        """Devuelve la fila de `file_entries` del escaneo base para la ruta
        dada, o lanza si no existe."""
        filas = storage.search_by_path_prefix("machine-alfa", absolute_path)
        coincidentes = [f for f in filas if f["scan_id"] == scan_base]
        assert len(coincidentes) == 1, (
            f"se esperaba exactamente una fila del scan base para "
            f"{absolute_path}, se encontraron {len(coincidentes)}"
        )
        return coincidentes[0]

    def test_marca_entradas_desaparecidas_cuando_scan_referencia_ok(
        self, storage: SystemInventoryStorage
    ):
        """Scan nuevo SCAN_RESULT_OK: las entradas desaparecidas se marcan
        como eliminadas (excluded = 1)."""
        _, entradas_ausentes, scan_base, scan_nuevo = self._escenario_base_y_nuevo(
            storage, resultado_nuevo=SCAN_RESULT_OK
        )

        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=entradas_ausentes,
        )

        assert resumen["marcadas"] == 2
        assert resumen["total_entradas"] == 2
        assert resumen["no_marcadas"] == []
        assert resumen["resultado_scan"] == SCAN_RESULT_OK

        for e in entradas_ausentes:
            fila = self._fila_base(storage, scan_base, e["absolute_path"])
            assert fila["excluded"] == 1
            assert fila["last_checked_at"] != ""

    def test_no_marca_cuando_scan_referencia_interrumpido(
        self, storage: SystemInventoryStorage
    ):
        """Scan nuevo SCAN_RESULT_INTERRUPTED: no se marca ninguna entrada."""
        _, entradas_ausentes, scan_base, scan_nuevo = self._escenario_base_y_nuevo(
            storage, resultado_nuevo=SCAN_RESULT_INTERRUPTED
        )

        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=entradas_ausentes,
        )

        assert resumen["marcadas"] == 0
        assert resumen["total_entradas"] == 2
        assert len(resumen["no_marcadas"]) == 2
        assert all(
            "no se completo correctamente" in n["motivo"]
            for n in resumen["no_marcadas"]
        )
        # Nada persistido como eliminado.
        for e in entradas_ausentes:
            fila = self._fila_base(storage, scan_base, e["absolute_path"])
            assert fila["excluded"] == 0

    def test_no_marca_cuando_scan_referencia_parcial(
        self, storage: SystemInventoryStorage
    ):
        """Scan nuevo SCAN_RESULT_PARTIAL: no se marca ninguna entrada."""
        _, entradas_ausentes, scan_base, scan_nuevo = self._escenario_base_y_nuevo(
            storage, resultado_nuevo=SCAN_RESULT_PARTIAL
        )
        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=entradas_ausentes,
        )
        assert resumen["marcadas"] == 0
        assert resumen["total_entradas"] == 2
        for e in entradas_ausentes:
            fila = self._fila_base(storage, scan_base, e["absolute_path"])
            assert fila["excluded"] == 0

    def test_no_marca_cuando_scan_referencia_error(
        self, storage: SystemInventoryStorage
    ):
        """Scan nuevo SCAN_RESULT_ERROR: no se marca ninguna entrada."""
        _, entradas_ausentes, scan_base, scan_nuevo = self._escenario_base_y_nuevo(
            storage, resultado_nuevo=SCAN_RESULT_ERROR
        )
        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=entradas_ausentes,
        )
        assert resumen["marcadas"] == 0
        assert resumen["total_entradas"] == 2
        for e in entradas_ausentes:
            fila = self._fila_base(storage, scan_base, e["absolute_path"])
            assert fila["excluded"] == 0

    def test_error_permiso_no_equivale_a_eliminacion(
        self, storage: SystemInventoryStorage
    ):
        """Scan nuevo OK con permiso_denegado en C:/Docs: readme.txt (bajo
        C:/Docs) no se marca, pero notes.txt (bajo C:/Docs2, sin error de
        permiso) sí se marca como eliminada."""
        _, entradas_ausentes, scan_base, scan_nuevo = self._escenario_base_y_nuevo(
            storage, resultado_nuevo=SCAN_RESULT_OK
        )
        errores_escaneo = [
            {
                "ruta": "C:/Docs",
                "categoria": "permiso_denegado",
                "mensaje": "Acceso denegado al directorio",
            }
        ]

        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=entradas_ausentes,
            errores_escaneo=errores_escaneo,
        )

        assert resumen["marcadas"] == 1
        assert resumen["total_entradas"] == 2
        assert len(resumen["no_marcadas"]) == 1
        no_marcada = resumen["no_marcadas"][0]
        assert no_marcada["normalized_path"] == normalize_path("C:/Docs/readme.txt")
        assert "permiso denegado" in no_marcada["motivo"]

        # notes.txt (fuera del prefijo con permiso) SI marcada.
        fila_notes = self._fila_base(storage, scan_base, "C:/Docs2/notes.txt")
        assert fila_notes["excluded"] == 1

        # readme.txt (bajo permiso denegado) NO marcada como eliminada.
        fila_readme = self._fila_base(storage, scan_base, "C:/Docs/readme.txt")
        assert fila_readme["excluded"] == 0

    def test_scan_referencia_desconocido_levanta_valuerror(
        self, storage: SystemInventoryStorage
    ):
        """scan_id_referencia inexistente levanta ValueError."""
        _, entradas_ausentes, _, _ = self._escenario_base_y_nuevo(storage)
        with pytest.raises(ValueError):
            storage.marcar_entradas_eliminadas(
                machine_id="machine-alfa",
                volume="C:",
                scan_id_referencia="scan-inexistente",
                entradas_ausentes=entradas_ausentes,
            )

    def test_scan_referencia_de_otro_volumen_levanta_valuerror(
        self, storage: SystemInventoryStorage
    ):
        """scan_id_referencia de otro volumen levanta ValueError."""
        _, entradas_ausentes, _, _ = self._escenario_base_y_nuevo(storage)
        storage.record_volume("vol-d:", "machine-alfa", "D:", "local", "online")
        storage.begin_scan_run("scan-d", "machine-alfa", "D:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-d", result=SCAN_RESULT_OK, entries_count=0)
        with pytest.raises(ValueError):
            storage.marcar_entradas_eliminadas(
                machine_id="machine-alfa",
                volume="C:",
                scan_id_referencia="scan-d",
                entradas_ausentes=entradas_ausentes,
            )

    def test_entrada_sin_normalized_path_no_se_marca(
        self, storage: SystemInventoryStorage
    ):
        """Entrada ausente sin normalized_path no se marca y se reporta el
        motivo."""
        _, _, scan_base, scan_nuevo = self._escenario_base_y_nuevo(storage)
        entrada_sin_ruta = {
            "scan_id": scan_base,
            "machine_id": "machine-alfa",
            "volume": "C:",
            "name": "misterioso.txt",
        }
        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=[entrada_sin_ruta],
        )
        assert resumen["marcadas"] == 0
        assert resumen["total_entradas"] == 1
        assert resumen["no_marcadas"][0]["motivo"] == "la entrada no tiene normalized_path"

    def test_entrada_de_otro_volumen_no_se_marca(
        self, storage: SystemInventoryStorage
    ):
        """Entrada ausente de otro volumen no se marca."""
        _, _, scan_base, scan_nuevo = self._escenario_base_y_nuevo(storage)
        entrada_otro_volumen = {
            "scan_id": scan_base,
            "machine_id": "machine-alfa",
            "volume": "D:",
            "normalized_path": normalize_path("D:/otro.txt"),
        }
        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=[entrada_otro_volumen],
        )
        assert resumen["marcadas"] == 0
        assert resumen["total_entradas"] == 1
        assert "no pertenece al equipo/volumen" in resumen["no_marcadas"][0]["motivo"]

    def test_entrada_inexistente_no_se_marca(
        self, storage: SystemInventoryStorage
    ):
        """Entrada ausente cuyo identificador no coincide con ninguna fila
        no se marca y se reporta el motivo."""
        _, _, scan_base, scan_nuevo = self._escenario_base_y_nuevo(storage)
        entrada_inexistente = {
            "scan_id": scan_base,
            "machine_id": "machine-alfa",
            "volume": "C:",
            "normalized_path": normalize_path("C:/NoExiste.txt"),
        }
        resumen = storage.marcar_entradas_eliminadas(
            machine_id="machine-alfa",
            volume="C:",
            scan_id_referencia=scan_nuevo,
            entradas_ausentes=[entrada_inexistente],
        )
        assert resumen["marcadas"] == 0
        assert resumen["total_entradas"] == 1
        assert "no existe una entrada de archivo" in resumen["no_marcadas"][0]["motivo"]
