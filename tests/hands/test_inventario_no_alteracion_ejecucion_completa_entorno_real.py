# -*- coding: utf-8 -*-
"""
Verificacion en entorno real de la unidad 3.8.5.1.4.10.15.

Comprueba que la ejecucion completa del escaneo de inventario de produccion
(`escanear_ruta` / `RecorridoVolumen` de src.hands.system_inventory) NO altera:

1. Los archivos originales: hash SHA-256 y tamano de cada archivo de muestra
   identicos antes y despues del escaneo real (solo lectura de metadatos).
2. Los datos persistentes protegidos: hash y tamano de
   `data/memory/entities.json`, `data/knowledge/entities.json` y
   `data/macros_coords.json` identicos antes y despues del escaneo real.
3. La configuracion de pantalla/ventanas del usuario: `data/macros_coords.json`
   (calibracion/coordenadas UI de los monitores reales) inalterado, y el modulo
   del escanador no importa dependencias de GUI
   (pyautogui, pygetwindow, mss, cv2, ScreenManager, coordinate_manager,
   calibration_manager, calibrator); la topologia de monitores se documenta
   mediante enumeracion real (ScreenManager) sin modificar ninguna ventana ni
   la disposicion de pantallas.

Estrategia: captura de linea base real ANTES, ejecucion de produccion real sobre
un arbol de archivos reales en directorio temporal con almacenamiento SQLite
temporal, captura de linea base real DESPUES y asserts de identidad.

No hay mocks que decidan el resultado. No se toca
`data/system_inventory.sqlite3` de produccion, no se leen documentos personales
del usuario, no se lanza ninguna aplicacion, no se crea ni mueve ventana alguna
y no se modifica la configuracion de pantalla ni de ventanas.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path

import pytest

from src.hands.system_inventory import (
    InventoryContract,
    escanear_ruta,
    generate_machine_id,
)
from src.hands.system_inventory_storage import (
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)
from src.utils.screen_manager import ScreenManager

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _PROJECT_ROOT / "data"
MEMORY_ENTITIES = DATA_DIR / "memory" / "entities.json"
KNOWLEDGE_ENTITIES = DATA_DIR / "knowledge" / "entities.json"
MACROS_COORDS = DATA_DIR / "macros_coords.json"

MACHINE_ID = generate_machine_id()

CONTENIDO_MUESTRAS = {
    "documento_normal.txt": "contenido de muestra del archivo normal\nlinea dos\n",
    "archivo_unicode.txt": "contenido unicode: cafe¿ ¡áéíóú ñ\n",
    "archivo_registro.log": "registro de evento 001\nevento 002\n",
}

GUI_IMPORTS_PROHIBIDOS = (
    "pyautogui",
    "pygetwindow",
    "mss",
    "cv2",
    "ScreenManager",
    "coordinate_manager",
    "calibration_manager",
    "calibrator",
)


def _hash_sha256(ruta: Path) -> str:
    """Devuelve el hash SHA-256 del contenido real de un archivo."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _info(ruta: Path) -> tuple[str, int]:
    """Devuelve (hash SHA-256, tamano en bytes) reales de un archivo."""
    return _hash_sha256(ruta), ruta.stat().st_size


def _linea_base_protegidos() -> dict[str, tuple[str, int]]:
    """Captura la linea base real (hash + tamano) de los archivos protegidos
    de produccion ANTES de cualquier operacion de inventario."""
    base: dict[str, tuple[str, int]] = {}
    for ruta in (MEMORY_ENTITIES, KNOWLEDGE_ENTITIES, MACROS_COORDS):
        assert ruta.exists(), f"Falta archivo de produccion protegido: {ruta}"
        base[str(ruta)] = _info(ruta)
    return base


def _afirmar_protegidos_inmutables(
    linea_base: dict[str, tuple[str, int]],
) -> None:
    """Comprueba que los archivos protegidos conservan hash y tamano de la
    linea base tras la ejecucion real del escaneo."""
    for ruta_str, (hash_antes, tamano_antes) in linea_base.items():
        ruta = Path(ruta_str)
        assert ruta.exists(), f"El archivo protegido desaparecio: {ruta}"
        hash_despues, tamano_despues = _info(ruta)
        assert hash_despues == hash_antes, (
            f"El archivo protegido fue alterado por el escaneo: {ruta}"
        )
        assert tamano_despues == tamano_antes, (
            f"El archivo protegido cambio de tamano: {ruta}"
        )


def _codigo_escanea_sin_gui() -> None:
    """Verifica estaticamente que el modulo del escanador de produccion no
    importa dependencias de GUI (no interactua con pantalla ni ventanas)."""
    ruta_modulo = Path(inspect.getfile(escanear_ruta))
    texto = ruta_modulo.read_text(encoding="utf-8")
    for nombre in GUI_IMPORTS_PROHIBIDOS:
        assert nombre not in texto, (
            f"El escaner de inventario importa una dependencia de GUI ({nombre}); "
            "no debe interactuar con pantalla ni ventanas"
        )


def _enumera_monitores_reales() -> list[dict]:
    """Documenta (sin modificar) la topologia real de monitores del equipo."""
    gestor = ScreenManager()
    return [m.to_dict() for m in gestor.monitors]


@pytest.fixture
def volumen_temp(tmp_path: Path) -> Path:
    """Directorio temporal REAL en el volumen del sistema con archivos de
    muestra creados por la prueba (incluido nombre Unicode y subcarpeta)."""
    base = tmp_path / "volumen_prueba_1015"
    base.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in CONTENIDO_MUESTRAS.items():
        (base / nombre).write_text(contenido, encoding="utf-8")
    sub = base / "subcarpeta"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "anidado.txt").write_text("contenido anidado\n", encoding="utf-8")
    return base


@pytest.fixture
def almacenamiento_temp(tmp_path: Path) -> SystemInventoryStorage:
    """Base SQLite temporal REAL para el inventario de esta prueba (no toca
    data/system_inventory.sqlite3 de produccion)."""
    db_path = tmp_path / "almacenamiento_1015" / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(db_path)
    storage.initialize()
    return storage


def test_ejecucion_completa_no_altera_archivos_originales_ni_protegidos_entorno_real(
    volumen_temp: Path,
    almacenamiento_temp: SystemInventoryStorage,
) -> None:
    """Ejecuta el escaneo real de produccion sobre archivos reales y verifica
    que no altera archivos originales, datos persistentes protegidos ni la
    configuracion de pantalla/ventanas del usuario."""
    # Linea base de archivos de muestra ANTES del escaneo.
    info_antes = {
        str(ruta): _info(ruta)
        for ruta in volumen_temp.rglob("*")
        if ruta.is_file()
    }
    contenido_prohibido = set(CONTENIDO_MUESTRAS.values())

    # Linea base de datos persistentes protegidos y config de pantalla/ventanas ANTES.
    linea_base_protegidos = _linea_base_protegidos()

    # Codigo del escanador sin dependencias de GUI (verificacion estatica del
    # archivo de produccion real).
    _codigo_escanea_sin_gui()

    # Ejecucion real de produccion: escaneo de lectura-solo sobre arbol real.
    contrato = InventoryContract(machine_id=MACHINE_ID)
    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=contrato,
        maquina_id=MACHINE_ID,
        storage=almacenamiento_temp,
        modo="completo",
    )
    assert resultado.resultado == SCAN_RESULT_OK
    assert resultado.completado
    assert resultado.entradas_procesadas > 0
    assert resultado.archivos_procesados > 0

    # Archivos originales sin modificar despues del escaneo (hash y tamano).
    for ruta in volumen_temp.rglob("*"):
        if not ruta.is_file():
            continue
        clave = str(ruta)
        hash_despues, tamano_despues = _info(ruta)
        hash_antes, tamano_antes = info_antes[clave]
        assert hash_despues == hash_antes, (
            f"El archivo original fue modificado por el escaneo: {ruta}"
        )
        assert tamano_despues == tamano_antes, (
            f"El archivo original cambio de tamano: {ruta}"
        )

    # Ninguna entrada del inventario almacena contenido de archivos.
    entradas = almacenamiento_temp.obtener_entradas_escaneo(resultado.scan_id)
    assert entradas, "Se esperaba al menos una entrada de inventario real"
    for entrada in entradas:
        for _campo, valor in entrada.items():
            if isinstance(valor, str):
                for token in contenido_prohibido:
                    assert token not in valor
            elif isinstance(valor, list):
                for elemento in valor:
                    if isinstance(elemento, str):
                        for token in contenido_prohibido:
                            assert token not in elemento
        assert "contenido" not in entrada
        assert "content" not in entrada
        assert "texto" not in entrada

    # Datos persistentes protegidos y configuracion de pantalla/ventanas sin cambios.
    _afirmar_protegidos_inmutables(linea_base_protegidos)

    # Topologia de monitores documentada mediante enumeracion real del SO
    # (lectura sola; ninguna ventana se crea, mueve, cierra ni modifica).
    monitores = _enumera_monitores_reales()
    assert len(monitores) >= 1
    for m in monitores:
        assert m["width"] > 0 and m["height"] > 0
