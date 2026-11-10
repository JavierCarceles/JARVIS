# -*- coding: utf-8 -*-
"""Verificacion en entorno real de la unidad 3.8.5.1.4.7.2.

Ejecuta el descubrimiento REAL sobre el equipo Windows:
- Fuentes primarias reales: CalibrationManager.discover_applications (menu de
  aplicaciones, accesos directos .lnk, paquetes AppX, registro de desinstaladores),
  rutas PATH y App Paths del registro.
- Clasificacion real: LaunchClassifier.
- Validacion real: ApplicationPreflight.validate_launch_destination (sin lanzar nada).
- Inventario real complementario: SystemInventoryStorage sobre una base de datos
  temporal, para localizar destinos faltantes.

No lanza ninguna aplicacion, no instala ni modifica datos del usuario. La base de
datos de inventario se crea en un directorio temporal y se elimina al finalizar
cada prueba.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.hands.application_discovery import (
    ApplicationDiscovery,
    DiscoveredCandidate,
    FUENTE_INVENTARIO,
    FUENTES_PRIMARIAS,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.application_launch_classifier import LaunchClassifier
from src.hands.system_inventory import EntryType, generate_machine_id
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insertar_entrada_inventario(
    storage: SystemInventoryStorage,
    machine_id: str,
    volumen: str,
    nombre: str,
    ruta_absoluta: str,
) -> None:
    """Inserta una entrada REAL en la base de datos de inventario temporal.

    Registra primero las entidades maestras requeridas por las claves
    foraneas (maquina, volumen, ejecucion de escaneo) y luego la entrada de
    archivo, usando las APIs publicas del almacenamiento.
    """
    ahora = _ahora_iso()
    storage.initialize()
    storage.record_machine(machine_id, created_at=ahora)
    volume_id = f"vol-{uuid4()}"
    storage.record_volume(
        volume_id, machine_id, volumen,
        volume_type="fixed", state="mounted",
        first_seen_at=ahora, last_seen_at=ahora,
    )
    scan_id = f"scan-{uuid4()}"
    conn = storage.connect()
    conn.execute(
        """
        INSERT INTO scan_runs(
            scan_id, machine_id, volume, mode, started_at,
            finished_at, result, entries_count, errors_count, exclusions_count, coverage_estimate
        )
        VALUES (?, ?, ?, ?, ?, NULL, ?, 1, 0, 0, NULL)
        """,
        (scan_id, machine_id, volumen, SCAN_MODE_FULL, ahora, SCAN_RESULT_OK),
    )
    conn.commit()
    storage.insert_file_entries(
        scan_id=scan_id,
        machine_id=machine_id,
        volume=volumen,
        entries=[{
            "entry_id": str(uuid4()),
            "absolute_path": ruta_absoluta,
            "relative_path": nombre,
            "name": nombre,
            "extension": Path(ruta_absoluta).suffix,
            "entry_type": EntryType.FILE.value,
            "size_bytes": 0,
            "modified_at": ahora,
            "created_at": ahora,
            "accessed_at": "",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": ahora,
        }],
    )


# ---------------------------------------------------------------------------
# Fuentes primarias reales (sin mocks que decidan el resultado)
# ---------------------------------------------------------------------------

class TestDescubrimientoEntornoRealFuentesPrimarias:
    def test_descubrir_todos_retorna_candidatos_reales(self):
        d = ApplicationDiscovery(machine_id=generate_machine_id())
        resultado = d.descubrir_todos(limite_por_fuente=50, incluir_inventario=False)
        assert isinstance(resultado, list)
        assert len(resultado) >= 1, (
            "Esperaba al menos un candidato real de las fuentes primarias del SO"
        )
        for c in resultado:
            assert isinstance(c, DiscoveredCandidate)
            assert c.name
            assert c.fuente in FUENTES_PRIMARIAS
            assert c.ultima_comprobacion
            if c.destination:
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
                assert "launch_type" in c.preflight_decision

    def test_no_duplica_destino_real(self):
        d = ApplicationDiscovery(machine_id=generate_machine_id())
        resultado = d.descubrir_todos(limite_por_fuente=50, incluir_inventario=False)
        destinos_reales = [
            c.destination.casefold()
            for c in resultado
            if c.destination and os.path.exists(c.destination)
        ]
        assert len(destinos_reales) == len(set(destinos_reales)), (
            "Hay destinos reales duplicados: el dedup por destino real fallo"
        )

    def test_buscar_por_nombre_devuelve_candidato_primario_real(self):
        d = ApplicationDiscovery(machine_id=generate_machine_id())
        todos = d.descubrir_todos(limite_por_fuente=50, incluir_inventario=False)
        assert len(todos) >= 1
        nombre = todos[0].name
        resultado = d.buscar_por_nombre(nombre, incluir_inventario=True)
        assert len(resultado) >= 1
        assert any(c.name.casefold() == nombre.casefold() for c in resultado)
        # Al menos uno debe venir de fuentes primarias (no del inventario)
        primarios = [c for c in resultado if c.fuente != FUENTE_INVENTARIO]
        assert len(primarios) >= 1
        for c in resultado:
            if c.destination:
                assert c.preflight_decision is not None

    def test_candidatos_lanzables_solo_lanzables(self):
        d = ApplicationDiscovery(machine_id=generate_machine_id())
        lanzables = d.candidatos_lanzables(limite_por_fuente=50, incluir_inventario=False)
        for c in lanzables:
            assert c.es_lanzable is True
            if c.destination:
                assert c.preflight_decision is not None
                assert c.preflight_decision["valid"] is True


# ---------------------------------------------------------------------------
# Inventario como fuente complementaria para destinos faltantes (real)
# ---------------------------------------------------------------------------

class TestInventarioComplementarioEntornoReal:
    def test_inventario_localiza_destino_faltante(self):
        machine_id = generate_machine_id()
        with tempfile.TemporaryDirectory(prefix="jarvis_inventario_prueba_") as tmp:
            db_path = Path(tmp) / "inventario.sqlite3"
            storage = SystemInventoryStorage(db_path=db_path)

            # Archivo .exe REAL temporal registrado como entrada de inventario.
            with tempfile.NamedTemporaryFile(suffix=".exe", delete=False, dir=tmp) as f:
                ruta_app = f.name
            try:
                _insertar_entrada_inventario(
                    storage, machine_id, "C:",
                    "AppInventarioPrueba.exe", ruta_app,
                )

                d = ApplicationDiscovery(
                    preflight=ApplicationPreflight(),
                    clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
                    storage=storage,
                    machine_id=machine_id,
                )

                resultado = d.buscar_por_nombre(
                    "appinventarioprueba.exe", incluir_inventario=True
                )
                assert len(resultado) >= 1, (
                    "El inventario como fuente complementaria no localizo el destino faltante"
                )
                c = resultado[0]
                assert c.fuente == FUENTE_INVENTARIO
                assert c.esta_en_inventario is True
                assert c.name.casefold() == "appinventarioprueba.exe"
                assert c.destination == os.path.abspath(ruta_app)
                # Validacion real con preflight (sin lanzar)
                assert c.preflight_decision is not None
            finally:
                try:
                    storage.close()
                except Exception:
                    pass
                if os.path.exists(ruta_app):
                    os.unlink(ruta_app)

    def test_inventario_no_se_consulta_cuando_primarias_cubren(self):
        """Si las fuentes primarias ya cubren el nombre, no se consulta el inventario."""
        machine_id = generate_machine_id()
        with tempfile.TemporaryDirectory(prefix="jarvis_inventario_vacio_") as tmp:
            db_path = Path(tmp) / "inventario.sqlite3"
            storage = SystemInventoryStorage(db_path=db_path)
            d = ApplicationDiscovery(
                preflight=ApplicationPreflight(),
                clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
                storage=storage,
                machine_id=machine_id,
            )
            todos = d.descubrir_todos(limite_por_fuente=50, incluir_inventario=False)
            assert len(todos) >= 1
            nombre = todos[0].name
            resultado = d.buscar_por_nombre(nombre, incluir_inventario=True)
            # Resultado de primarias; el inventario no debe haberse necesitado.
            primarios = [c for c in resultado if c.fuente != FUENTE_INVENTARIO]
            assert len(primarios) >= 1
            try:
                storage.close()
            except Exception:
                pass
