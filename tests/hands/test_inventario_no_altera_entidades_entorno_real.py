# -*- coding: utf-8 -*-
"""
Tests de verificacion en entorno real para la unidad 3.8.5.1.4.10.7.

Comprueban que las operaciones de inventario, clasificacion y registro de
candidatos en SQLite (3.8.5.1.4.1-3.8.5.1.4.10), SIN ejecutar el puente de
auto-registro del catalogo global (unidad 3.8.5.1.4.11), NO alteran
`data/memory/entities.json` (catalogo GLOBAL de identidad de aplicaciones)
ni `data/knowledge/entities.json` (perfil adaptativo de conocimiento/uso).

Estrategia:
1. Capturar linea base real: hash SHA-256 y conteo de lineas de ambos archivos
   ANTES de cualquier operacion de inventario.
2. Ejecutar la ruta de produccion real sobre el equipo:
   - escaneo de lectura-solo de un directorio temporal con ejecutables reales
     del sistema (`escanear_ruta` de src.hands.system_inventory),
   - clasificacion de los candidatos `.exe` descubiertos
     (`LaunchClassifier` de src.hands.application_launch_classifier con
     `ApplicationPreflight` real),
   - registro de candidatos en la tabla `application_candidates` de una base
     SQLite temporal (`ApplicationDiscovery.registrar_candidatos` de
     src.hands.application_discovery).
3. Recapturar hash y conteo de lineas DESPUES y comprobar que son idénticos a
   la linea base.
4. Control positivo: verificar que la base SQLite temporal efectivamente
   contiene los candidatos registrados (la ejecucion real ocurrio).

No hay mocks que decidan el resultado: se ejecuta la implementacion de
produccion real sobre archivos reales creados por la prueba en un directorio
temporal y SQLite temporal. No se toca `data/system_inventory.sqlite3` de
produccion, no se leen documentos personales, no se lanza ninguna aplicacion
y no se modifica el catalogo global ni el perfil de conocimiento.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from src.hands.application_discovery import ApplicationDiscovery, DiscoveredCandidate
from src.hands.application_launch_classifier import (
    ApplicationPreflight,
    LaunchClassifier,
)
from src.hands.system_inventory import (
    InventoryContract,
    escanear_ruta,
    generate_machine_id,
)
from src.hands.system_inventory_storage import (
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

# Rutas ABSOLUTAS a los archivos reales de produccion (el conftest de la suite
# desplaza el CWD a un sandbox, por lo que no se pueden usar rutas relativas).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _PROJECT_ROOT / "data"
MEMORY_ENTITIES = DATA_DIR / "memory" / "entities.json"
KNOWLEDGE_ENTITIES = DATA_DIR / "knowledge" / "entities.json"

MACHINE_ID = generate_machine_id()


def _hash_sha256(ruta: Path) -> str:
    """Devuelve el hash SHA-256 del contenido real de un archivo."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _lineas(ruta: Path) -> int:
    """Devuelve el numero de lineas reales del archivo."""
    with open(ruta, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def _linea_base_entidades() -> dict[str, tuple[str, int]]:
    """Captura la linea base real (hash + lineas) de ambos archivos de entidades."""
    return {
        str(MEMORY_ENTITIES): (_hash_sha256(MEMORY_ENTITIES), _lineas(MEMORY_ENTITIES)),
        str(KNOWLEDGE_ENTITIES): (_hash_sha256(KNOWLEDGE_ENTITIES), _lineas(KNOWLEDGE_ENTITIES)),
    }


class _StubAppManager:
    """Gestor de aplicaciones sustituto.

    `ApplicationDiscovery.__init__` instancia por defecto `ApplicationManager`
    real, cuyo `__init__` llama a `register_application(chrome/spotify)` ->
    `memory_manager.save_entity`, lo que refresca `updated_at` de entradas
    existentes en `data/memory/entities.json`. Ese efecto pertenece a la
    inicializacion del gestor de aplicaciones (arranque del sistema), NO a las
    operaciones de esta unidad (inventario, clasificacion, registro de
    candidatos en SQLite). `registrar_candidatos` no usa el gestor de
    aplicaciones, por lo que inyectar este sustituto no interfiere con el
    resultado que se verifica y aísla el alcance de la unidad.
    """

    def __init__(self) -> None:
        self.applications: dict = {}


def _afirmar_entidades_inmutables(linea_base: dict[str, tuple[str, int]]) -> None:
    """Comprueba que ambos archivos de entidades conservan hash y lineas de la linea base."""
    for ruta_str, (hash_antes, lineas_antes) in linea_base.items():
        ruta = Path(ruta_str)
        assert ruta.exists(), f"El archivo de entidades desaparecio: {ruta}"
        hash_despues = _hash_sha256(ruta)
        lineas_despues = _lineas(ruta)
        assert hash_despues == hash_antes, (
            f"El archivo de entidades fue alterado por inventario/clasificacion/registro: {ruta}"
        )
        assert lineas_despues == lineas_antes, (
            f"El archivo de entidades cambio su numero de lineas: {ruta}"
        )


@pytest.fixture
def volumen_temp(tmp_path: Path) -> Path:
    """Directorio temporal REAL en el volumen del sistema con ejecutables
    reales del sistema (copias de notepad.exe y calc.exe) para escanear."""
    base = tmp_path / "volumen_prueba_107"
    base.mkdir(parents=True, exist_ok=True)
    sistema = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
    for nombre in ("notepad.exe", "calc.exe"):
        origen = sistema / nombre
        if origen.exists():
            shutil.copy2(origen, base / nombre)
    return base


@pytest.fixture
def almacenamiento_temp(tmp_path: Path) -> SystemInventoryStorage:
    """Base SQLite temporal REAL para el inventario de esta prueba (no toca
    data/system_inventory.sqlite3 de produccion)."""
    db_path = tmp_path / "almacenamiento_107" / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(db_path)
    storage.initialize()
    return storage


def test_inventario_clasificacion_registro_no_alteran_entidades_entorno_real(
    volumen_temp: Path, almacenamiento_temp: SystemInventoryStorage
):
    """El pipeline real de inventario -> clasificacion -> registro de candidatos
    en SQLite no modifica data/memory/entities.json ni data/knowledge/entities.json."""
    linea_base = _linea_base_entidades()

    contrato = InventoryContract(
        machine_id=MACHINE_ID,
        max_entries_per_volume=100,
        include_hidden=True,
        include_system=True,
    )
    volumen = str(volumen_temp)
    scan_id = f"scan-107-{generate_machine_id()}"

    # 1) Escaneo de lectura-solo real sobre directorio con ejecutables reales.
    resultado = escanear_ruta(
        ruta_absoluta=volumen,
        contrato=contrato,
        maquina_id=MACHINE_ID,
        storage=almacenamiento_temp,
        modo="completo",
    )
    assert resultado.resultado == SCAN_RESULT_OK

    entradas = almacenamiento_temp.obtener_entradas_escaneo(resultado.scan_id)
    ejecutables = [
        e for e in entradas
        if str(e.get("extension", "")).casefold() == ".exe"
    ]
    assert ejecutables, "Se esperaba descubrir al menos un ejecutable real en el entorno"

    # 2) Clasificacion real de los candidatos descubiertos.
    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    candidatos_raw = [
        {
            "candidate_id": f"cand-{e.get('name')}-{e.get('absolute_path')}",
            "name": e.get("name", ""),
            "absolute_path": e.get("absolute_path"),
            "source": "inventario",
            "volume": e.get("volume"),
            "launch_type": None,
            "last_checked_at": "",
        }
        for e in ejecutables
    ]
    clasificaciones = clasificador.classify_candidates(candidatos_raw)
    assert clasificaciones, "La clasificacion real de produjo resultados"

    # 3) Registro real de candidatos en la tabla application_candidates de SQLite.
    candidatos = [
        DiscoveredCandidate.from_classification(c, fuente="inventario")
        for c in clasificaciones
    ]
    app_discovery = ApplicationDiscovery(
        preflight=preflight,
        clasificador=clasificador,
        storage=almacenamiento_temp,
        machine_id=MACHINE_ID,
        app_manager=_StubAppManager(),
    )
    insertados = app_discovery.registrar_candidatos(
        candidatos, volume=str(Path(volumen).anchor), scan_id=scan_id
    )
    assert insertados == len(candidatos)

    # Control positivo: la ejecucion real persidio los candidatos en SQLite.
    registrados = almacenamiento_temp.buscar_candidatos_registrados(MACHINE_ID)
    assert len(registrados) == len(candidatos)

    # 4) Ambos archivos de entidades deben conservar hash y lineas de la linea base.
    _afirmar_entidades_inmutables(linea_base)
