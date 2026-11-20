# -*- coding: utf-8 -*-
"""
Tests de la unidad 3.8.5.1.4.11.12: verificacion real de auto-registro
desde el SQLite existente `data/system_inventory.sqlite3`.

Lee candidatos `.exe` ya persistidos en el inventario real (conexion
read-only), comprueba la resolucion/clasificacion y ejecuta el pipeline
de auto-registro `auto_registrar_candidatos_inventario` sin iniciar
`RecorridoVolumen` ni ningun escaneo. Aisla las escrituras del catalogo
global mediante una copia controlada de `data/memory/entities.json` en
una ruta temporal; nunca modifica la SQLite real ni repite el escaneo
completo. Compara los candidatos efectivamente leidos con las entidades
generadas y documenta exclusiones/errores.

No lanza aplicaciones, no toca data/ de produccion, usa solo recursos
reales (SQLite real) o temporales controlados (copia del catalogo).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.hands.apps.application_discovery import (
    ApplicationDiscovery,
    DiscoveredCandidate,
    FUENTE_INVENTARIO,
)
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.apps.application_launch_classifier import (
    CONFIANZA_ALTA,
    LaunchClassifier,
    LaunchSubtype,
    LaunchType,
)
from src.hands.inventory.system_inventory import generate_machine_id
from src.memory.storage import Entity, MemoryManager


# ---------------------------------------------------------------------------
# Rutas de produccion (solo lectura para SQLite, copia controlada para catalogo)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SQLITE_REAL = PROJECT_ROOT / "data" / "system_inventory.sqlite3"


def _ruta_catalogo_global() -> Path:
    """entities.json que MemoryManager usa por defecto (catalogo global); en la
    suite es el catalogo de prueba aislado por tests/conftest.py."""
    import src.memory.storage as storage_mod

    return storage_mod.get_project_root() / "data" / "memory" / "entities.json"


# Umbral de confianza para considerar un candidato valido (desde el clasificador real).
CONFIANZA_ESPERADA = CONFIANZA_ALTA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_archivo(ruta: Path) -> str:
    """Devuelve el hash SHA-256 de un fichero para detectar modificaciones."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _informe_aislamiento_coincide(machine_id: str) -> dict:
    """Informe de aislamiento que indica que el equipo coincide (sin tocar la
    SQLite real: la verificacion de identidad se hace manualmente con una
    conexion read-only fuera de este metodo)."""
    return {
        "maquina_actual": machine_id,
        "maquina_registrada": machine_id,
        "maquinas_registradas": [machine_id],
        "equipo_coincide": True,
        "bloqueado": False,
        "requiere_reescaneo": False,
        "motivo": None,
        "inventario_utilizable": True,
    }


def _leer_candidatos_exe_sqlite_real(
    db_path: Path, machine_id: str
) -> list[dict]:
    """Lee candidatos `.exe` de `application_candidates` en la SQLite real
    mediante una conexion read-only (URI mode=ro). Nunca modifica la base de
    datos."""
    uri = "file:" + str(db_path) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT candidate_id, name, absolute_path, launch_type, confidence,
                   version, producto, source, last_checked_at, evidencia
            FROM application_candidates
            WHERE machine_id = ?
              AND lower(absolute_path) LIKE '%.exe'
            ORDER BY confidence DESC, last_checked_at DESC
            """,
            (machine_id,),
        )
        filas = [dict(r) for r in cur.fetchall()]
        for fila in filas:
            evidencia_raw = fila.get("evidencia") or "[]"
            try:
                fila["evidencia"] = (
                    json.loads(evidencia_raw)
                    if isinstance(evidencia_raw, str)
                    else list(evidencia_raw or [])
                )
            except (json.JSONDecodeError, TypeError):
                fila["evidencia"] = []
        return filas
    finally:
        conn.close()


def _construir_candidatos_desde_filas(
    filas: list[dict],
) -> list[DiscoveredCandidate]:
    """Convierte filas leidas de la SQLite real en objetos
    `DiscoveredCandidate` listos para el pipeline de auto-registro."""
    candidatos: list[DiscoveredCandidate] = []
    for f in filas:
        ruta = str(f.get("absolute_path") or "").strip()
        fuente = str(f.get("source") or FUENTE_INVENTARIO)
        candidatos.append(
            DiscoveredCandidate(
                candidate_id=str(f.get("candidate_id") or ""),
                name=str(f.get("name") or ""),
                nombre_comercial=None,
                aliases=[],
                absolute_path=ruta if os.path.isfile(ruta) else None,
                destination=ruta if os.path.isfile(ruta) else None,
                launch_type=str(f.get("launch_type") or LaunchType.EJECUTABLE),
                launch_subtype=LaunchSubtype.DESCONOCIDO.value,
                es_lanzable=os.path.isfile(ruta),
                evidencia=list(f.get("evidencia") or []),
                confianza=str(f.get("confianza") or CONFIANZA_ALTA),
                version=str(f.get("version")) if f.get("version") else None,
                producto=str(f.get("producto")) if f.get("producto") else None,
                fuente=fuente,
                ultima_comprobacion=str(f.get("last_checked_at") or ""),
                fuentes_consultadas=[fuente],
                esta_en_inventario=True,
                disponible=True,
            )
        )
    return candidatos


def _discovery_con_catalogo_isolado(
    tmp_path: Path, machine_id: str, informe_aislamiento: dict
) -> tuple[ApplicationDiscovery, MemoryManager]:
    """Crea una `ApplicationDiscovery` con codigo de produccion real
    (preflight, clasificador) pero con:
      - storage mockeado (verificar_identidad_equipo devuelve el informe
        pasado; no se conecta a la SQLite real).
      - MemoryManager real sobre una COPIA de data/memory/entities.json en
        tmp_path, de modo que las escrituras del catalogo global queden
        aisladas de produccion.
    """
    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    storage = MagicMock()
    storage.verificar_identidad_equipo.return_value = informe_aislamiento

    # Copia controlada del catalogo de produccion para aislar escrituras.
    memoria_dir = tmp_path / "data" / "memory"
    memoria_dir.mkdir(parents=True, exist_ok=True)
    entidades_copia = memoria_dir / "entities.json"
    shutil.copy2(_ruta_catalogo_global(), entidades_copia)

    mm = MemoryManager(str(memoria_dir))
    app_manager = SimpleNamespace(memory_manager=mm, get_application=lambda nombre: None)

    discovery = ApplicationDiscovery(
        preflight=preflight,
        clasificador=clasificador,
        storage=storage,
        machine_id=machine_id,
        app_manager=app_manager,
    )
    return discovery, mm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSqliteRealSoloLecturaYAislamiento:
    """Verifica que la lectura del SQLite real es solo lectura, que el
    machine_id coincide y que se obtienen candidatos .exe reales."""

    def test_sqlite_real_no_se_modifica(self):
        """El hash SHA-256 de data/system_inventory.sqlite3 es identico
        antes y despues de la lectura read-only: comprobacion de que nunca
        se modifica la base de datos real."""
        if not SQLITE_REAL.exists():
            pytest.skip("data/system_inventory.sqlite3 no disponible")
        antes = _sha256_archivo(SQLITE_REAL)
        # Lectura real (misma conexion read-only que usan los tests siguientes).
        _ = _leer_candidatos_exe_sqlite_real(SQLITE_REAL, generate_machine_id())
        despues = _sha256_archivo(SQLITE_REAL)
        assert antes == despues, "La SQLite real fue modificada durante la lectura"

    def test_machine_id_coincide_con_sqlite_real(self):
        """El machine_id generado por el equipo coincide con el registrado
        en la SQLite real (aislamiento por equipo, 3.8.5.1.4.1.3)."""
        if not SQLITE_REAL.exists():
            pytest.skip("data/system_inventory.sqlite3 no disponible")
        uri = "file:" + str(SQLITE_REAL) + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT machine_id FROM machines")
            registrados = [str(r["machine_id"]) for r in cur.fetchall()]
        finally:
            conn.close()
        actual = generate_machine_id()
        assert actual in registrados, (
            f"machine_id actual {actual} no registrado en la SQLite real"
        )

    def test_existen_candidatos_exe_en_sqlite_real(self):
        """Hay al menos un candidato .exe persistido en la SQLite real para
        el machine_id actual (verificacion real de inventario existente)."""
        if not SQLITE_REAL.exists():
            pytest.skip("data/system_inventory.sqlite3 no disponible")
        machine_id = generate_machine_id()
        filas = _leer_candidatos_exe_sqlite_real(SQLITE_REAL, machine_id)
        assert len(filas) >= 1, (
            "No se encontraron candidatos .exe en la SQLite real para el equipo actual"
        )
        # Cada fila debe tener los campos esenciales.
        for f in filas:
            assert f.get("candidate_id")
            assert f.get("name")
            assert f.get("absolute_path")
            assert os.path.isfile(f["absolute_path"]), (
                f"Ruta no accesible en el equipo: {f['absolute_path']}"
            )


class TestAutoRegistroDesdeSqliteReal:
    """Ejecuta el pipeline de auto-registro sobre candidatos reales leidos
    de la SQLite y compara candidatos leidos con entidades generadas."""

    def test_auto_registro_candidatos_reales_sqlite(self, tmp_path):
        """Lee candidatos .exe de la SQLite real, ejecuta
        auto_registrar_candidatos_inventario y verifica que se generan
        entidades en el catalogo aislado sin tocar produccion."""
        if not SQLITE_REAL.exists():
            pytest.skip("data/system_inventory.sqlite3 no disponible")

        machine_id = generate_machine_id()
        informe = _informe_aislamiento_coincide(machine_id)

        # Lectura real de la SQLite (read-only).
        filas = _leer_candidatos_exe_sqlite_real(SQLITE_REAL, machine_id)
        candidatos = _construir_candidatos_desde_filas(filas)
        assert len(candidatos) >= 1

        # Pipeline de auto-registro con catalogo aislado (copia de entities.json).
        discovery, mm = _discovery_con_catalogo_isolado(tmp_path, machine_id, informe)
        resultado = discovery.auto_registrar_candidatos_inventario(candidatos)

        # El pipeline no debe estar bloqueado por identidad de equipo.
        assert resultado["bloqueado"] is False
        assert resultado["no_verificado"] is False
        assert resultado["errores"] == 0

        # Al menos un candidato registrado (charmap.exe existe y es .exe).
        assert resultado["registrados"] >= 1, (
            f"Se esperaban registros, obtenidos: {resultado}"
        )

        # Comparacion 1:1 candidatos leidos vs entidades generadas.
        ids_registrados = {
            d["id"] for d in resultado["detalle_registrados"]
        }
        entidades_app = mm.get_entities_by_type("application")
        ids_entidades = {e.id for e in entidades_app}
        nombres_registrados = {
            d["name"] for d in resultado["detalle_registrados"]
        }

        # Cada candidato leido y registrable debe tener una entidad en el catalogo aislado.
        nombres_registrados_lower = {n.lower() for n in nombres_registrados}
        for c in candidatos:
            if c.es_lanzable:
                # La entidad debe existir con ID estable (sin fragmentos de ruta absoluta).
                entity_id_calculado = None
                for d in resultado["detalle_registrados"]:
                    if d.get("name", "").lower() == c.name.lower():
                        entity_id_calculado = d["id"]
                        break
                assert entity_id_calculado is not None, (
                    f"Candidato {c.candidate_id} ({c.name}) no tuvo entidad registrada"
                )
                assert entity_id_calculado in ids_entidades, (
                    f"Entidad {entity_id_calculado} no presente en entidades de aplicacion"
                )
                assert c.name.lower() in nombres_registrados_lower, (
                    f"Nombre {c.name} no aparece entre registros (case-insensitive)"
                )
                # El entity_id nunca debe incluir fragmentos de ruta absoluta.
                ruta = c.absolute_path or ""
                for fragmento in (ruta, os.path.dirname(ruta), os.path.basename(ruta)):
                    if fragmento:
                        assert fragmento not in entity_id_calculado, (
                            f"entity_id {entity_id_calculado} incluye fragmento de ruta {fragmento}"
                        )

    def test_catalogo_produccion_sin_modificaciones(self, tmp_path):
        """data/memory/entities.json de produccion permanece intacto: todas
        las escrituras van a la copia isolada en tmp_path."""
        if not SQLITE_REAL.exists() or not _ruta_catalogo_global().exists():
            pytest.skip("Recursos de produccion no disponibles")

        antes = _sha256_archivo(_ruta_catalogo_global())

        machine_id = generate_machine_id()
        filas = _leer_candidatos_exe_sqlite_real(SQLITE_REAL, machine_id)
        candidatos = _construir_candidatos_desde_filas(filas)

        informe = _informe_aislamiento_coincide(machine_id)
        discovery, mm = _discovery_con_catalogo_isolado(tmp_path, machine_id, informe)
        discovery.auto_registrar_candidatos_inventario(candidatos)

        despues = _sha256_archivo(_ruta_catalogo_global())
        assert antes == despues, (
            "data/memory/entities.json de produccion fue modificado"
        )

        # El catalogo aislado en tmp_path SI tiene las nuevas entidades.
        entidades_aislado = mm.get_entities_by_type("application")
        assert len(entidades_aislado) >= 1

    def test_sqlite_real_sin_modificaciones_despues_de_registro(self, tmp_path):
        """La SQLite real no se modifica ni se repite el escaneo completo:
        su hash es identico antes y despues de ejecutar el pipeline."""
        if not SQLITE_REAL.exists():
            pytest.skip("data/system_inventory.sqlite3 no disponible")

        antes = _sha256_archivo(SQLITE_REAL)

        machine_id = generate_machine_id()
        filas = _leer_candidatos_exe_sqlite_real(SQLITE_REAL, machine_id)
        candidatos = _construir_candidatos_desde_filas(filas)

        informe = _informe_aislamiento_coincide(machine_id)
        discovery, mm = _discovery_con_catalogo_isolado(tmp_path, machine_id, informe)
        discovery.auto_registrar_candidatos_inventario(candidatos)

        despues = _sha256_archivo(SQLITE_REAL)
        assert antes == despues, "La SQLite real fue modificada por el pipeline de auto-registro"


class TestRegistroMinimoAplicacionDesdeSqlite:
    """Verifica que las entidades generadas desde candidatos de la SQLite
    cumplen el registro minimo de aplicacion (3.8.5.1.4.11.3)."""

    def test_entidades_tienen_campos_obligatorios_registro_minimo(self, tmp_path):
        """Cada entidad generada desde un candidato real de la SQLite tiene
        los campos obligatorios del registro minimo de aplicacion."""
        if not SQLITE_REAL.exists():
            pytest.skip("data/system_inventory.sqlite3 no disponible")

        machine_id = generate_machine_id()
        filas = _leer_candidatos_exe_sqlite_real(SQLITE_REAL, machine_id)
        candidatos = _construir_candidatos_desde_filas(filas)
        candidatos_lanzables = [c for c in candidatos if c.es_lanzable]
        assert len(candidatos_lanzables) >= 1

        informe = _informe_aislamiento_coincide(machine_id)
        discovery, mm = _discovery_con_catalogo_isolado(tmp_path, machine_id, informe)
        resultado = discovery.auto_registrar_candidatos_inventario(candidatos)

        for d in resultado["detalle_registrados"]:
            entidad = mm.get_entity(d["id"])
            assert entidad is not None, f"Entidad {d['id']} no encontrada en catalogo aislado"
            assert entidad.type == "application", f"Tipo no es application: {entidad.type}"
            assert entidad.id == d["id"], f"ID no coincide: {entidad.id} vs {d['id']}"
            assert entidad.name, f"Nombre vacio en entidad {entidad.id}"
            assert isinstance(entidad.aliases, list), f"aliases no es lista en {entidad.id}"

            props = entidad.properties or {}
            # Campos del registro minimo de aplicacion (3.8.5.1.4.11.3).
            assert "categoria_rol" in props or entidad.tags, (
                f"categoria_rol faltante en {entidad.id}"
            )
            assert props.get("estado_disponible") in (
                "available", "no_disponible"
            ), f"estado_disponible invalido en {entidad.id}"
            assert props.get("fecha_observacion"), (
                f"fecha_observacion vacia en {entidad.id}"
            )
            assert props.get("fuente_observacion"), (
                f"fuente_observacion vacia en {entidad.id}"
            )
            assert isinstance(props.get("evidencia_observacion"), list), (
                f"evidencia_observacion no es lista en {entidad.id}"
            )
            assert len(props.get("evidencia_observacion", [])) >= 1, (
                f"evidencia_observacion vacia en {entidad.id}"
            )
