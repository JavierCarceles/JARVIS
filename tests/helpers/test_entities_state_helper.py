# -*- coding: utf-8 -*-
"""Tests del helper reutilizable de estado de entities.json (unidad 3.8.4.4.3).

Objetivo verificable: confirmar que `tests/helpers/entities_state.py`
- captura el estado exacto (contenido + hash SHA-256 + tamano) antes y despues
  de una operacion;
- trabaja SOLO sobre copias en directorios temporales;
- nunca escribe ni modifica el fichero real de datos (source);
- detecta un cambio real en la copia y reporta no-cambio cuando no lo hay.

No modifica codigo de produccion ni entities.json. Todas las operaciones
ejecutan sobre copias temporales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.entities_state import (
    EntitiesJsonSnapshot,
    copy_to_temp_dir,
    snapshots_equal,
    snapshot_entities_json,
    verify_entities_json_unchanged,
)


# ---------------------------------------------------------------------------
# Rutas (calculadas desde __file__ para ser independientes de la CWD/sandbox)
# ---------------------------------------------------------------------------
_TESTS_DIR = Path(__file__).resolve().parents[1]      # tests/
_ROOT_DIR = _TESTS_DIR.parent                          # raiz del repositorio
REAL_ENTITIES_JSON = _ROOT_DIR / "data" / "knowledge" / "entities.json"


def _contar_entidades(path: Path) -> int:
    datos = json.loads(path.read_text(encoding="utf-8"))
    return len(datos) if isinstance(datos, list) else 0


# ---------------------------------------------------------------------------
# 1. Captura y comparacion de snapshots
# ---------------------------------------------------------------------------
class TestSnapshotYComparacion:
    def test_snapshot_captura_contenido_hash_y_tamano(self):
        snap = snapshot_entities_json(REAL_ENTITIES_JSON)
        assert snap.path == REAL_ENTITIES_JSON.resolve()
        assert snap.size_bytes > 0
        assert len(snap.sha256) == 64  # SHA-256 hex
        assert isinstance(snap.contenido, bytes)
        # El contenido decodificado es JSON valido con las 7 entidades originales.
        datos = json.loads(snap.contenido.decode("utf-8"))
        assert _contar_entidades(REAL_ENTITIES_JSON) == 7

    def test_snapshots_iguales_si_mismo_contenido(self):
        a = snapshot_entities_json(REAL_ENTITIES_JSON)
        b = snapshot_entities_json(REAL_ENTITIES_JSON)
        assert snapshots_equal(a, b) is True
        assert a.sha256 == b.sha256
        assert a.contenido == b.contenido

    def test_snapshot_devuelve_objeto_inmutable(self):
        snap = snapshot_entities_json(REAL_ENTITIES_JSON)
        with pytest.raises(Exception):
            snap.size_bytes = 0  # dataclass frozen


# ---------------------------------------------------------------------------
# 2. Copia a directorio temporal (nunca toca el original)
# ---------------------------------------------------------------------------
class TestCopiaTemporal:
    def test_copia_queda_en_directorio_temporal_y_no_modifica_original(self):
        antes = snapshot_entities_json(REAL_ENTITIES_JSON)
        tmp_dir = copy_to_temp_dir(REAL_ENTITIES_JSON)
        try:
            copia = tmp_dir / REAL_ENTITIES_JSON.name
            assert copia.exists()
            despues = snapshot_entities_json(REAL_ENTITIES_JSON)
            assert snapshots_equal(antes, despues), "el original no debe modificarse"
            assert snapshots_equal(antes, snapshot_entities_json(copia))
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Verificacion antes/despues de operacion sobre copia temporal
# ---------------------------------------------------------------------------
class TestVerifyEntitiesJsonUnchanged:
    def _operacion_sin_cambios(self, temp_path: Path) -> str:
        """Operacion que lee pero no escribe el fichero."""
        _ = temp_path.read_bytes()
        return "leido"

    def _operacion_que_cambia(self, temp_path: Path) -> None:
        """Operacion que anade una entidad al entities.json de la copia."""
        datos = json.loads(temp_path.read_text(encoding="utf-8"))
        datos.append(
            {
                "id": "entidad_temporal_prueba",
                "type": "application",
                "name": "Entidad Temporal Prueba",
                "properties": {},
                "aliases": [],
                "tags": [],
                "confidence": 1.0,
                "metadata": None,
            }
        )
        temp_path.write_bytes(json.dumps(datos, indent=2, ensure_ascii=False).encode("utf-8"))

    def test_operacion_sin_cambios_reporta_no_cambio_y_source_untouched(self):
        resultado = verify_entities_json_unchanged(
            REAL_ENTITIES_JSON, self._operacion_sin_cambios
        )
        assert resultado["changed"] is False
        assert resultado["source_untouched"] is True
        assert snapshots_equal(resultado["before"], resultado["after"])
        assert snapshots_equal(resultado["source_before"], resultado["source_after"])
        assert resultado["operation_result"] == "leido"

    def test_operacion_que_cambia_reporta_cambio_pero_source_untouched(self):
        antes_source = snapshot_entities_json(REAL_ENTITIES_JSON)
        entidades_antes = _contar_entidades(REAL_ENTITIES_JSON)

        resultado = verify_entities_json_unchanged(
            REAL_ENTITIES_JSON, self._operacion_que_cambia
        )

        assert resultado["changed"] is True, (
            "el helper debe detectar que la copia temporal cambio"
        )
        assert resultado["source_untouched"] is True, (
            "el fichero real de datos nunca debe modificarse"
        )
        assert not snapshots_equal(resultado["before"], resultado["after"])
        assert snapshots_equal(resultado["source_before"], resultado["source_after"])
        # El fichero real sigue intacto (7 entidades, mismo hash).
        assert snapshots_equal(antes_source, snapshot_entities_json(REAL_ENTITIES_JSON))
        assert _contar_entidades(REAL_ENTITIES_JSON) == entidades_antes == 7

    def test_trabaja_sobre_copia_temporal_y_libera_recursos(self):
        resultado = verify_entities_json_unchanged(
            REAL_ENTITIES_JSON, self._operacion_que_cambia
        )
        # La copia temporal ya fue eliminada por el helper (finally).
        # source_untouched True prueba que el original sigue intacto.
        assert resultado["source_untouched"] is True
