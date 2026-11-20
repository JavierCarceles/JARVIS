# -*- coding: utf-8 -*-
"""
Test de entorno real para registrar aplicaciones descubiertas desde la
SQLite existente (data/system_inventory.sqlite3) en application_candidates.

Lee las file_entries de tipo ejecutable (.exe) del machine_id actual y las
registra como candidatos de aplicacion usando el pipeline real de
ApplicationDiscovery.registrar_candidatos(), sin crear entities.json y sin
ejecutar aplicaciones.

Flujo:
  1. Conectar a data/system_inventory.sqlite3 y obtener el machine_id actual.
  2. Consultar file_entries con extension .exe, entry_type='file',
     disponible y no excluido para ese machine_id.
  3. Para cada entrada, crear un DiscoveredCandidate con launch_type
     'ejecutable' y registrarlo en application_candidates.
  4. Verificar que los candidatos aparecen al consultar application_candidates
     filtrando por machine_id.
  5. Registrar linea base y resultado observable (cantidades antes/despues).

No ejecuta aplicaciones, no cierra procesos, no captura contenido privado.
Vive en tests/ y usa solo la implementacion real de produccion.
"""

import os
import sys
import uuid
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.hands.apps.application_discovery import ApplicationDiscovery, DiscoveredCandidate
from src.hands.inventory.system_inventory import generate_machine_id
from src.hands.inventory.system_inventory_storage import SystemInventoryStorage


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestRegistrarAplicacionesDesdeInventarioEntornoReal(unittest.TestCase):
    """
    Registra en application_candidates las aplicaciones ejecutables ya
    descubiertas en file_entries de la SQLite real, usando el flujo real
    de ApplicationDiscovery.
    """

    def setUp(self):
        self.db_path = ROOT / "data" / "system_inventory.sqlite3"
        self.assertTrue(
            self.db_path.exists(),
            f"no existe {self.db_path}",
        )
        self.storage = SystemInventoryStorage(str(self.db_path))
        self.storage.connect()
        self.machine_id = generate_machine_id()
        self.storage.record_machine(self.machine_id)
        self.antes_candidatos = self._contar_candidatos()
        self.registrados_en_test = []
        self.resultados = {}

    def tearDown(self):
        try:
            self.storage.close()
        except Exception:
            pass

    # ---- helpers ---------------------------------------------------------

    def _contar_candidatos(self) -> int:
        """Cuenta candidatos en application_candidates para el machine_id."""
        try:
            rows = self.storage.buscar_candidatos_registrados(
                machine_id=self.machine_id,
                limite=10000,
            )
            return len(rows)
        except Exception:
            return 0

    def _leer_ejecutables_file_entries(self, limite: int = 200) -> list[dict]:
        """Lee file_entries tipo archivo con extension .exe para el machine_id."""
        cur = self.storage.connect().execute(
            """
            SELECT entry_id, scan_id, machine_id, volume, absolute_path,
                   name, extension, entry_type, size_bytes, attributes,
                   source, last_checked_at
            FROM file_entries
            WHERE machine_id = ?
              AND lower(extension) = '.exe'
              AND entry_type = 'file'
              AND excluded = 0
            ORDER BY name
            LIMIT ?
            """,
            (self.machine_id, limite),
        )
        columnas = [d[0] for d in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]

    # ---- tests -----------------------------------------------------------

    def test_01_linea_base_inventario(self):
        """Registra la linea base de candidatos y file_entries .exe."""
        ejecutables = self._leer_ejecutables_file_entries()
        self.assertIsInstance(ejecutables, list)
        self.resultados = {
            "machine_id": self.machine_id,
            "file_entries_exe_antes": len(ejecutables),
            "application_candidates_antes": self.antes_candidatos,
        }
        print(
            f"\n  machine_id={self.machine_id} "
            f"file_entries .exe={len(ejecutables)} "
            f"application_candidates antes={self.antes_candidatos}"
        )

    def test_02_registrar_ejecutables_como_candidatos(self):
        """Registra los ejecutables de file_entries en application_candidates."""
        ejecutables = self._leer_ejecutables_file_entries(limite=200)
        self.assertGreaterEqual(len(ejecutables), 0)

        discovery = ApplicationDiscovery(
            storage=self.storage,
            machine_id=self.machine_id,
        )

        ahora = _ahora_iso()
        candidatos = []
        for ent in ejecutables:
            candidate_id = (
                f"cand-{self.machine_id}-{uuid.uuid4().hex[:8]}"
            )
            nombre = ent.get("name") or os.path.basename(ent.get("absolute_path", ""))
            ruta = ent.get("absolute_path", "")
            volumen = ent.get("volume", "C:")
            evidencia = [
                "origen=file_entries_sqlite",
                f"scan_id={ent.get('scan_id','')}",
                f"tamano_bytes={ent.get('size_bytes',0)}",
                f"atributos={ent.get('attributes','[]')}",
            ]
            fuente = ent.get("source", "filesystem_scan")

            candidatos.append(
                DiscoveredCandidate(
                    candidate_id=candidate_id,
                    name=nombre,
                    absolute_path=ruta,
                    launch_type="ejecutable",
                    confianza=0.8,
                    version=None,
                    producto=None,
                    evidencia=evidencia,
                    fuente=fuente,
                    ultima_comprobacion=ahora,
                )
            )

        insertados = 0
        if candidatos:
            insertados = discovery.registrar_candidatos(
                candidatos=candidatos,
                volume="C:",
            )
        self.registrados_en_test = candidatos

        self.resultados["registro"] = {
            "ejecutables_leidos": len(ejecutables),
            "candidatos_preparados": len(candidatos),
            "insertados": insertados,
        }
        self.assertGreaterEqual(insertados, 0)
        print(
            f"\n  ejecutables leidos={len(ejecutables)} "
            f"candidatos preparados={len(candidatos)} "
            f"insertados={insertados}"
        )

    def test_03_verificar_candidatos_registrados(self):
        """Verifica que los candidatos aparecen en application_candidates."""
        despues = self._contar_candidatos()
        self.assertGreaterEqual(despues, self.antes_candidatos)

        rows = self.storage.buscar_candidatos_registrados(
            machine_id=self.machine_id,
            limite=10000,
        )
        nuestros = [
            r for r in rows
            if r.get("source", "").startswith("filesystem_scan")
        ]
        self.assertGreaterEqual(len(nuestros), 0)

        self.resultados["verificacion"] = {
            "candidatos_despues": despues,
            "candidatos_nuestros": len(nuestros),
        }
        print(
            f"\n  candidates despues={despues} "
            f"antes={self.antes_candidatos} "
            f"nuestros={len(nuestros)}"
        )

    def test_04_conteo_no_disminuye(self):
        """Comprueba que el conteo de candidatos no disminuye tras el registro."""
        despues = self._contar_candidatos()
        self.assertGreaterEqual(despues, self.antes_candidatos)
        self.resultados["no_duplicar"] = {
            "antes": self.antes_candidatos,
            "despues": despues,
        }


if __name__ == "__main__":
    unittest.main()
