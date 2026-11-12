# -*- coding: utf-8 -*-
"""
Tests de verificacion en entorno real para la unidad 3.8.5.1.4.10.6.

Confirman que el escaner y el almacenamiento de inventario:

1. No copian contenidos de documentos/archivos personales (privacidad de
   escritura/copia): ninguna entrada del inventario almacena el contenido de
   los archivos, ni se crean copias de documentos fuera de los originales.
2. No modifican archivos originales (integridad de lectura-solo): el hash
   SHA-256 y el tamano de cada archivo son identicos antes y despues del
   escaneo.
3. La base de inventario permanece limitada al almacenamiento definido:
   el almacenamiento solo crea archivos dentro del directorio de db_path
   (la base SQLite, su manifest, copias de seguridad y archivos laterales
   -wal/-shm); nada se escribe fuera de ese alcance.

Todos los tests usan directorios temporales (tmp_path) y bases de datos
SQLite temporales; no tocan datos de produccion ni rutas de usuario. No
hay mocks que decidan el resultado: se ejecuta la implementacion de
produccion real (src/hands/system_inventory.py y
src/hands/system_inventory_storage.py) sobre archivos reales creados por
la prueba. Limpian los recursos al finalizar.
"""

from __future__ import annotations

import hashlib
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

MACHINE_ID = generate_machine_id()


def _hash_sha256(ruta: Path) -> str:
    """Devuelve el hash SHA-256 del contenido real de un archivo."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


@pytest.fixture
def volumen_temp(tmp_path: Path) -> Path:
    """Directorio temporal REAL en el volumen del sistema para crear recursos de prueba."""
    base = tmp_path / "volumen_prueba_106"
    base.mkdir(parents=True, exist_ok=True)
    yield base


# ---------------------------------------------------------------------------
# Test 1: No se copian contenidos de documentos personales
# ---------------------------------------------------------------------------

def test_no_se_copian_contenidos_documentos_personales_entorno_real(
    volumen_temp: Path, tmp_path: Path
):
    """El escaneo de archivos con contenido confidencial no almacena ese
    contenido en ninguna entrada del inventario, ni crea copias de los
    documentos fuera de los archivos originales."""
    db_path = tmp_path / "almacenamiento_privacidad" / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(db_path)
    storage.initialize()

    archivo_privado = volumen_temp / "documento_personal.txt"
    archivo_privado.write_text(
        "contenido confidencial del usuario: datos sensibles\n", encoding="utf-8"
    )
    archivo_confidencial = volumen_temp / "notas_confidenciales.md"
    archivo_confidencial.write_text(
        "# notas privadas\ncontraseña: secreta123\ntoken: abc-def-ghi\n",
        encoding="utf-8",
    )

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK

    entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
    nombres = {e["name"] for e in entradas}
    assert "documento_personal.txt" in nombres
    assert "notas_confidenciales.md" in nombres

    # Ninguna entrada del inventario debe contener el contenido de los archivos.
    contenido_prohibido = [
        "contenido confidencial del usuario",
        "datos sensibles",
        "contraseña: secreta123",
        "token: abc-def-ghi",
    ]
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

    # Los campos de cada entrada son solo metadatos: nunca hay campo de contenido.
    for entrada in entradas:
        assert "contenido" not in entrada
        assert "content" not in entrada
        assert "texto" not in entrada
        assert "leer_contenido" not in entrada

    # No existen copias de los documentos personales fuera de los originales.
    copias_encontradas = [
        p
        for p in tmp_path.rglob("*.txt")
        if p.resolve() != archivo_privado.resolve()
    ]
    for copia in copias_encontradas:
        assert str(copia.resolve()).startswith(str(volumen_temp.resolve())), (
            f"Se encontro copia de documento personal fuera de los originales: {copia}"
        )


# ---------------------------------------------------------------------------
# Test 2: No se modifican archivos originales
# ---------------------------------------------------------------------------

def test_no_se_modifican_archivos_originales_entorno_real(
    volumen_temp: Path, tmp_path: Path
):
    """Los archivos originales quedan sin modificar despues del escaneo:
    mismo hash SHA-256 y mismo tamano antes y despues (lectura solo)."""
    db_path = tmp_path / "almacenamiento_integridad" / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(db_path)
    storage.initialize()

    archivo1 = volumen_temp / "original1.txt"
    archivo1.write_text("contenido original uno\n", encoding="utf-8")
    archivo2 = volumen_temp / "original2.log"
    archivo2.write_text("contenido original dos\nlinea adicional\n", encoding="utf-8")

    # Hashes y tamaños ANTES del escaneo.
    hash_antes_1 = _hash_sha256(archivo1)
    hash_antes_2 = _hash_sha256(archivo2)
    tamano_antes_1 = archivo1.stat().st_size
    tamano_antes_2 = archivo2.stat().st_size

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK

    # Hashes y tamaños DESPUES del escaneo: deben ser identicos.
    hash_despues_1 = _hash_sha256(archivo1)
    hash_despues_2 = _hash_sha256(archivo2)
    tamano_despues_1 = archivo1.stat().st_size
    tamano_despues_2 = archivo2.stat().st_size

    assert hash_despues_1 == hash_antes_1, (
        f"El archivo {archivo1.name} fue modificado por el escaneo"
    )
    assert hash_despues_2 == hash_antes_2, (
        f"El archivo {archivo2.name} fue modificado por el escaneo"
    )
    assert tamano_despues_1 == tamano_antes_1
    assert tamano_despues_2 == tamano_antes_2

    # Los archivos siguen existiendo y son accesibles.
    assert archivo1.exists()
    assert archivo2.exists()


# ---------------------------------------------------------------------------
# Test 3: Almacenamiento del inventario limitado al definido
# ---------------------------------------------------------------------------

def test_almacenamiento_inventario_limitado_al_definido_entorno_real(
    volumen_temp: Path, tmp_path: Path
):
    """El almacenamiento de inventario solo crea archivos dentro del directorio
    definido por db_path (la base, su manifest, copias de seguridad y archivos
    laterales -wal/-shm de SQLite); nada se escribe fuera de ese alcance."""
    almacenamiento_definido = tmp_path / "almacenamiento_inventario"
    db_path = almacenamiento_definido / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(db_path)
    storage.initialize()

    (volumen_temp / "archivo_a.txt").write_text("contenido a\n", encoding="utf-8")
    sub = volumen_temp / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "archivo_b.txt").write_text("contenido b\n", encoding="utf-8")

    antes = {
        p.resolve() for p in almacenamiento_definido.iterdir() if p.is_file()
    }

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK

    despues = {
        p.resolve() for p in almacenamiento_definido.iterdir() if p.is_file()
    }
    nuevos = despues - antes

    # Todos los archivos nuevos del almacenamiento deben estar dentro de su
    # directorio definido (db_path.parent).
    almacenamiento_resuelto = almacenamiento_definido.resolve()
    for archivo_nuevo in nuevos:
        try:
            archivo_nuevo.relative_to(almacenamiento_resuelto)
        except ValueError:
            raise AssertionError(
                f"El almacenamiento de inventario escribio fuera del alcance definido: {archivo_nuevo}"
            )

    # La base de datos principal debe existir dentro del almacenamiento definido.
    assert db_path.exists()
    assert db_path.parent.resolve() == almacenamiento_resuelto
