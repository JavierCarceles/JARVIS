"""Verificacion real de 3.8.5.1.4.11.9: preservacion del catalogo entre equipos.

Lee candidatos reales de data/system_inventory.sqlite3 (solo lectura),
los convierte a DiscoveredCandidate y ejecuta auto_registrar_candidatos_inventario
contra un MemoryManager temporal (sin tocar data/memory/entities.json de
produccion). Verifica:
  - Los candidatos reales se registran (upsert) en el catalogo temporal.
  - Las entidades preexistentes se preservan (no se borran).
  - No se marca como desaparecida ninguna entidad no incluida en la muestra.
  - El machine_id del inventario real coincide con el equipo actual.
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.hands.apps.application_discovery import (
    ApplicationDiscovery,
    DiscoveredCandidate,
    FUENTE_INVENTARIO,
    calcular_identidad_estable,
    construir_registro_minimo_aplicacion,
    destino_observable,
    validar_registro_minimo_aplicacion,
)
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.apps.application_launch_classifier import LaunchClassifier, LaunchSubtype, LaunchType, CONFIANZA_ALTA
from src.hands.inventory.system_inventory import generate_machine_id
from src.memory.storage import Entity, MemoryManager
from unittest.mock import MagicMock

REAL_SQLITE = "data/system_inventory.sqlite3"
MACHINE_ID = "4de10a54-5054-515b-aa57-1b30a1feb801"


def leer_candidatos_reales():
    """Lee candidatos de application_candidates del SQLite real (solo lectura)."""
    conn = sqlite3.connect(f"file:{REAL_SQLITE}?mode=ro", uri=True)
    cur = conn.execute(
        """
        SELECT candidate_id, name, absolute_path, launch_type, source, confidence,
               version, producto, evidencia, last_checked_at
        FROM application_candidates
        WHERE machine_id = ?
        """,
        (MACHINE_ID,),
    )
    filas = cur.fetchall()
    conn.close()
    return filas


def fila_a_candidato(fila):
    """Convierte una fila de application_candidates en DiscoveredCandidate."""
    (candidate_id, name, absolute_path, launch_type, source, confidence,
     version, producto, evidencia_json, ultima_comprobacion) = fila
    try:
        evidencia = json.loads(evidencia_json or "[]")
    except (json.JSONDecodeError, TypeError):
        evidencia = []
    return DiscoveredCandidate(
        candidate_id=candidate_id,
        name=name,
        absolute_path=absolute_path,
        destination=absolute_path,
        nombre_comercial=name,
        aliases=[],
        launch_type=launch_type,
        launch_subtype=LaunchSubtype.DESCONOCIDO,
        es_lanzable=True,
        evidencia=evidencia,
        confianza=str(confidence or CONFIANZA_ALTA),
        version=version,
        producto=producto,
        fuente=source or FUENTE_INVENTARIO,
        ultima_comprobacion=ultima_comprobacion or "",
        disponible=True,
    )


def main():
    print("=== Verificacion real 3.8.5.1.4.11.9 ===")
    print(f"SQLITE real: {REAL_SQLITE}")
    print(f"machine_id: {MACHINE_ID}")

    filas = leer_candidatos_reales()
    print(f"Candidatos leidos del inventario real: {len(filas)}")
    for f in filas:
        print(f"  - {f[1]} ({f[2]}) confianza={f[5]} fuente={f[4]}")

    candidatos = [fila_a_candidato(f) for f in filas]
    assert len(candidatos) == len(filas)

    # Verificar que cada candidato tenga destino observable
    for c in candidatos:
        obs = destino_observable(c)
        print(f"  observable={obs} para {c.name}")
        assert obs, f"El candidato {c.name} no tiene destino observable"

    # Configurar MemoryManager temporal (no toca data/ de produccion)
    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis_verify_11_9_"))
    memoria_dir = tmp_dir / "data" / "memory"
    memoria_dir.mkdir(parents=True, exist_ok=True)

    # Copiar entidades reales del catalogo global para probar preservacion
    entidades_reales = json.load(
        open("data/memory/entities.json", encoding="utf-8")
    )
    entidades_path = memoria_dir / "entities.json"
    entidades_path.write_text(
        json.dumps(entidades_reales, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ids_antes = {e["id"] for e in entidades_reales}
    print(f"Entidades preexistentes en catalogo temporal: {len(ids_antes)}")

    mm = MemoryManager(str(memoria_dir))

    # Configurar discovery con storage real (solo lectura para identidad) y MM temporal
    from src.hands.inventory.system_inventory_storage import SystemInventoryStorage
    storage = SystemInventoryStorage(db_path=REAL_SQLITE)
    # No inicializar ni escribir: solo leer para verificar identidad de equipo
    informe = storage.verificar_identidad_equipo(MACHINE_ID)
    print(f"Informe aislamiento: equipo_coincide={informe.get('equipo_coincide')}, "
          f"bloqueado={informe.get('bloqueado')}")
    assert informe["equipo_coincide"] is True
    assert informe["bloqueado"] is False

    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    calib = MagicMock()
    calib.discover_applications.return_value = []
    app_manager = MagicMock()
    app_manager.memory_manager = mm

    discovery = ApplicationDiscovery(
        preflight=preflight,
        clasificador=clasificador,
        storage=storage,
        calibration=calib,
        machine_id=MACHINE_ID,
        app_manager=app_manager,
    )

    # Ejecutar auto-registro de candidatos del inventario real
    resultado = discovery.auto_registrar_candidatos_inventario(candidatos)
    print(f"\nResultado auto-registro:")
    print(f"  registrados: {resultado['registrados']}")
    print(f"  omitidos: {resultado['omitidos']}")
    print(f"  errores: {resultado['errores']}")
    print(f"  bloqueado: {resultado['bloqueado']}")

    assert resultado["bloqueado"] is False
    assert resultado["registrados"] == len(candidatos), (
        f"Esperaba {len(candidatos)} registrados, obtuvo {resultado['registrados']}"
    )
    assert resultado["errores"] == 0

    # Verificar que las entidades registradas existen en el catalogo temporal
    for e in resultado["detalle_registrados"]:
        entidad = mm.get_entity(e["id"])
        assert entidad is not None, f"Entidad {e['id']} no encontrada tras registro"
        assert entidad.type == "application"
        print(f"  Entidad registrada: {entidad.id} ({entidad.name})")

    # Verificar preservacion: entidades preexistentes no incluidas en la muestra
    # siguen estando en el catalogo (no marcadas como desaparecidas)
    ids_despues = {e.id for e in mm.get_entities_by_type("application")} | \
                  {e.id for e in mm.get_entities_by_type("streamer")}
    for eid in ids_antes:
        assert eid in ids_despues, (
            f"Entidad preexistente {eid} desaparecio del catalogo (violacion de preservacion)"
        )
    print(f"\nEntidades totales despues del registro: {len(ids_despues)}")
    print(f"Entidades preexistentes preservadas: {len(ids_antes)}")

    # Verificar que no se escribio en data/memory/entities.json de produccion
    entidades_produccion = json.load(
        open("data/memory/entities.json", encoding="utf-8")
    )
    ids_produccion = {e["id"] for e in entidades_produccion}
    assert ids_produccion == ids_antes, (
        "data/memory/entities.json de produccion fue modificado (violacion)"
    )
    print("\n data/memory/entities.json de produccion: SIN MODIFICACIONES")

    # Limpiar archivos temporales
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n=== VERIFICACION REAL 3.8.5.1.4.11.9: OK ===")


if __name__ == "__main__":
    main()
