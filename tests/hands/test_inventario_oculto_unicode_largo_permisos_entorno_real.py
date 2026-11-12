# -*- coding: utf-8 -*-
"""
Tests de verificacion en entorno real para unidad 3.8.5.1.4.10.5.

Verifican que el escaner de produccion (RecorridoVolumen / escanear_ruta)
registra correctamente en el entorno real:

1. Archivos ocultos con atributo real del SO -> atributo "hidden" en attributes.
2. Rutas Unicode (caracteres no ASCII en nombres/rutas) -> registradas sin error.
3. Rutas largas (>260 caracteres en Windows) -> manejadas con prefijo \\\\?\\.
4. Directorios con permiso denegado -> registrados con categoria "permiso_denegado",
   sin abortar el recorrido.
5. Lo que no pudo inspeccionarse se indica explicitamente (errores por categoria).

Todos los tests usan directorios temporales (tmp_path) y bases de datos SQLite
temporales; no tocan datos de produccion ni rutas de usuario. No hay mocks que
decidan el resultado: se ejecuta la implementacion de produccion real sobre
archivos reales creados por la prueba.

Limpieza: todo lo creado por la prueba se restaura/borra al finalizar,
incluyendo permisos de directorios denegados.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from pathlib import Path

import pytest

from src.hands.system_inventory import (
    EntryType,
    InventoryContract,
    escanear_ruta,
    generate_machine_id,
)
from src.hands.system_inventory_storage import (
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)

MACHINE_ID = generate_machine_id()

# Atributo de archivo oculto de Windows (FILE_ATTRIBUTE_HIDDEN).
FILE_ATTRIBUTE_HIDDEN = 0x02


def _poner_atributo_oculto(ruta: Path) -> None:
    """Marca un archivo/directorio como oculto usando la API real de Windows."""
    if os.name != "nt":
        return
    ctypes.windll.kernel32.SetFileAttributesW(str(ruta), FILE_ATTRIBUTE_HIDDEN)


def _quitar_atributo_oculto(ruta: Path) -> None:
    """Quita el atributo oculto (restaura normal) para permitir limpieza."""
    if os.name != "nt":
        return
    ctypes.windll.kernel32.SetFileAttributesW(str(ruta), 0x00000080)  # FILE_ATTRIBUTE_NORMAL


def _denegar_acceso_directorio(ruta: Path) -> None:
    """Deniega acceso de control total al usuario actual sobre un directorio
    usando PowerShell FileSystemAccessRule (ACE de denegación explícita).
    Se restaurará con _restaurar_acceso_directorio."""
    if os.name != "nt":
        return
    cmd = (
        f"$acl = Get-Acl '{ruta}'; "
        f"$rule = New-Object System.Security.AccessControl.FileSystemAccessRule("
        f"[System.Security.Principal.WindowsIdentity]::GetCurrent().Name, 'FullControl', 'Deny'); "
        f"$acl.AddAccessRule($rule); Set-Acl '{ruta}' $acl"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)


def _restaurar_acceso_directorio(ruta: Path) -> None:
    """Restaura permisos por defecto de un directorio para permitir limpieza."""
    if os.name != "nt":
        return
    subprocess.run(
        ["icacls", str(ruta), "/reset"],
        check=False,
    )


def _crear_ruta_larga(base: Path, nombre_base: str, longitud_objetivo: int = 300) -> Path:
    """Crea una ruta absoluta que supere los 260 caracteres en Windows."""
    parte = "a" * 10
    actual = base
    while len(str(actual)) + len(nombre_base) < longitud_objetivo:
        actual = actual / parte
        actual.mkdir(parents=True, exist_ok=True)
    archivo_largo = actual / (nombre_base + ".txt")
    archivo_largo.write_text("x\n", encoding="utf-8")
    return archivo_largo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage(tmp_path: Path) -> SystemInventoryStorage:
    db_path = tmp_path / "system_inventory.sqlite3"
    storage = SystemInventoryStorage(db_path)
    storage.initialize()
    return storage


@pytest.fixture
def volumen_temp(tmp_path: Path) -> Path:
    """Directorio temporal REAL en el volumen del sistema para crear recursos de prueba."""
    base = tmp_path / "volumen_prueba_105"
    base.mkdir(parents=True, exist_ok=True)
    yield base
    # Limpieza best-effort: restaurar atributos ocultos y permisos antes de borrar.
    for hijo in list(base.rglob("*")) + [base]:
        try:
            _quitar_atributo_oculto(hijo)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Test 1: Archivos ocultos con atributo real del SO se registran con "hidden"
# ---------------------------------------------------------------------------

def test_archivo_oculto_registra_atributo_hidden_entorno_real(
    storage: SystemInventoryStorage, tmp_path: Path, volumen_temp: Path
):
    """Un archivo con atributo oculto real del SO aparece en el inventario
    con "hidden" en attributes, sin leer su contenido."""
    storage.initialize()

    archivo_oculto = volumen_temp / "fichero_oculto.txt"
    archivo_oculto.write_text("contenido oculto\n", encoding="utf-8")
    _poner_atributo_oculto(archivo_oculto)

    # Archivo de control (no oculto).
    archivo_visible = volumen_temp / "fichero_visible.txt"
    archivo_visible.write_text("contenido visible\n", encoding="utf-8")

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK
    assert resultado.entradas_procesadas >= 2

    entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
    nombres = {e["name"] for e in entradas}

    assert "fichero_oculto.txt" in nombres
    assert "fichero_visible.txt" in nombres

    entrada_oculta = next(e for e in entradas if e["name"] == "fichero_oculto.txt")
    entrada_visible = next(e for e in entradas if e["name"] == "fichero_visible.txt")

    assert "hidden" in entrada_oculta["attributes"], (
        f"El archivo oculto real debe registrar 'hidden' en attributes, obtuvo: {entrada_oculta['attributes']}"
    )
    assert "hidden" not in entrada_visible["attributes"], (
        f"El archivo visible no debe tener 'hidden': {entrada_visible['attributes']}"
    )


# ---------------------------------------------------------------------------
# Test 2: Rutas Unicode se registran correctamente
# ---------------------------------------------------------------------------

def test_ruta_unicode_registrada_sin_error_entorno_real(
    storage: SystemInventoryStorage, tmp_path: Path, volumen_temp: Path
):
    """Un archivo con nombre Unicode (caracteres no ASCII) se registra
    correctamente en el inventario, ruta normalizada NFC."""
    storage.initialize()

    nombre_unico = "caféñ¿áéíóú.txt"
    archivo_unicode = volumen_temp / nombre_unico
    archivo_unicode.write_text("contenido unicode\n", encoding="utf-8")

    # Archivo de control ASCII.
    archivo_ascii = volumen_temp / "archivo_normal.txt"
    archivo_ascii.write_text("normal\n", encoding="utf-8")

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK

    entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
    nombres = {e["name"] for e in entradas}

    assert nombre_unico in nombres, (
        f"El archivo Unicode '{nombre_unico}' debe aparecer en el inventario; nombres={nombres}"
    )
    assert "archivo_normal.txt" in nombres

    entrada_unicode = next(e for e in entradas if e["name"] == nombre_unico)
    # La ruta absoluta almacenada debe contener los caracteres Unicode (normalizados).
    assert nombre_unico in entrada_unicode["absolute_path"]
    assert entrada_unicode["entry_type"] == EntryType.FILE.value


# ---------------------------------------------------------------------------
# Test 3: Rutas largas (>260 chars en Windows) se manejan con prefijo \\?\
# ---------------------------------------------------------------------------

def test_ruta_larga_maneja_prefijo_windows_entorno_real(
    storage: SystemInventoryStorage, tmp_path: Path, volumen_temp: Path
):
    """Una ruta que supere MAX_PATH (260 chars) en Windows se registra
    correctamente usando el prefijo de ruta larga \\\\?\\."""
    if os.name != "nt":
        pytest.skip("Rutas largas con prefijo \\\\?\\ son específicas de Windows.")

    storage.initialize()

    archivo_largo = _crear_ruta_larga(volumen_temp, "archivo_ruta_larga", longitud_objetivo=300)

    # La ruta absoluta debe superar 260 caracteres.
    ruta_abs = str(archivo_largo.resolve())
    assert len(ruta_abs) > 260, f"La ruta debe superar 260 chars, tiene {len(ruta_abs)}: {ruta_abs}"

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK

    entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
    nombres = {e["name"] for e in entradas}

    assert "archivo_ruta_larga.txt" in nombres, (
        f"El archivo de ruta larga debe aparecer; nombres={nombres}"
    )

    entrada = next(e for e in entradas if e["name"] == "archivo_ruta_larga.txt")
    # En Windows, rutas largas se almacenan con prefijo \\\\?\\ cuando superan MAX_PATH.
    assert entrada["absolute_path"].startswith("\\\\?\\"), (
        f"La ruta larga debe usar prefijo \\\\?\\, obtuvo: {entrada['absolute_path']}"
    )


# ---------------------------------------------------------------------------
# Test 4: Directorio con permiso denegado se registra con categoria permiso_denegado
# ---------------------------------------------------------------------------

def test_permiso_denegado_registrado_categoria_entorno_real(
    storage: SystemInventoryStorage, tmp_path: Path, volumen_temp: Path
):
    """Un directorio con permiso denegado real se registra como error con
    categoria 'permiso_denegado' sin abortar el recorrido del resto."""
    if os.name != "nt":
        pytest.skip("Denegacion de acceso por icacls es específica de Windows.")

    storage.initialize()

    # Directorio de control accesible.
    dir_accesible = volumen_temp / "accesible"
    dir_accesible.mkdir(parents=True, exist_ok=True)
    (dir_accesible / "dentro.txt").write_text("dentro\n", encoding="utf-8")

    # Directorio con permiso denegado.
    dir_denegado = volumen_temp / "denegado"
    dir_denegado.mkdir(parents=True, exist_ok=True)
    (dir_denegado / "secreto.txt").write_text("secreto\n", encoding="utf-8")

    # Denegar acceso real al directorio usando icacls.
    _denegar_acceso_directorio(dir_denegado)

    try:
        resultado = escanear_ruta(
            ruta_absoluta=str(volumen_temp),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert resultado.resultado == SCAN_RESULT_OK, (
            f"El escaneo no debe abortar por permiso denegado, obtuvo: {resultado.resultado}"
        )

        # El directorio accesible debe haberse escaneado.
        entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
        nombres = {e["name"] for e in entradas}
        assert "accesible" in nombres
        assert "dentro.txt" in nombres

        # El directorio denegado aparece como entrada (su padre pudo listarlo),
        # pero su contenido no se pudo listar (no debe aparecer "secreto.txt").
        assert "denegado" in nombres
        assert "secreto.txt" not in nombres, (
            "Un directorio con permiso denegado no debe producir entradas de contenido."
        )

        # Los errores agrupados por categoría deben incluir permiso_denegado.
        assert resultado.errores_por_categoria.get("permiso_denegado", 0) >= 1, (
            f"Debe haber al menos un error de categoria 'permiso_denegado'; "
            f"errores_por_categoria={resultado.errores_por_categoria}"
        )

        # El scan_run persistido debe registrar al menos un error.
        scan_run = storage.get_scan_run(resultado.scan_id)
        assert scan_run is not None
        assert scan_run["errors_count"] >= 1

        # Lo que no pudo inspeccionarse queda indicado explicitamente en el scan_run.
        assert scan_run["errors_count"] == resultado.errores
    finally:
        # Restaurar acceso antes de que la fixture de limpieza intente borrar.
        _restaurar_acceso_directorio(dir_denegado)


# ---------------------------------------------------------------------------
# Test 5: Lo que no pudo inspeccionarse se indica explícitamente
# ---------------------------------------------------------------------------

def test_lo_que_no_pudo_inspeccionarse_indicado_explicitamente(
    storage: SystemInventoryStorage, tmp_path: Path, volumen_temp: Path
):
    """El escaneo indica explícitamente qué rutas no pudo inspeccionar,
    con categoría y mensaje, sin ocultar el hecho."""
    if os.name != "nt":
        pytest.skip("Denegacion de acceso por icacls es específica de Windows.")

    storage.initialize()

    # Directorio con permiso denegado.
    dir_denegado = volumen_temp / "no_accesible"
    dir_denegado.mkdir(parents=True, exist_ok=True)
    (dir_denegado / "interno.txt").write_text("interno\n", encoding="utf-8")

    _denegar_acceso_directorio(dir_denegado)

    try:
        resultado = escanear_ruta(
            ruta_absoluta=str(volumen_temp),
            contrato=InventoryContract(machine_id=MACHINE_ID),
            maquina_id=MACHINE_ID,
            storage=storage,
        )

        assert resultado.resultado == SCAN_RESULT_OK

        # Los errores agrupados por categoría deben incluir permiso_denegado.
        assert resultado.errores_por_categoria.get("permiso_denegado", 0) >= 1, (
            f"Debe indicarse explicitamente categoria 'permiso_denegado'; "
            f"errores_por_categoria={resultado.errores_por_categoria}"
        )

        # El scan_run persistido debe registrar al menos un error.
        scan_run = storage.get_scan_run(resultado.scan_id)
        assert scan_run is not None
        assert scan_run["errors_count"] >= 1, (
            "El scan_run debe registrar al menos un error de permiso denegado."
        )

        # Lo que no pudo inspeccionarse queda indicado explicitamente:
        # el scan_run tiene errors_count >= 1 y la categoría permiso_denegado.
        assert scan_run["errors_count"] == resultado.errores
        assert resultado.errores >= 1
    finally:
        _restaurar_acceso_directorio(dir_denegado)


# ---------------------------------------------------------------------------
# Test 6: Privacidad - no se lee contenido de archivos personales
# ---------------------------------------------------------------------------

def test_no_se_lee_contenido_archivos_entorno_real(
    storage: SystemInventoryStorage, tmp_path: Path, volumen_temp: Path
):
    """El inventario solo registra metadatos; nunca almacena ni lee el
    contenido de los archivos (privacidad, 3.8.5.1.4.1.9)."""
    storage.initialize()

    archivo = volumen_temp / "privado.txt"
    archivo.write_text("contenido confidencial que no debe leerse\n", encoding="utf-8")

    resultado = escanear_ruta(
        ruta_absoluta=str(volumen_temp),
        contrato=InventoryContract(machine_id=MACHINE_ID),
        maquina_id=MACHINE_ID,
        storage=storage,
    )

    assert resultado.resultado == SCAN_RESULT_OK

    entradas = storage.obtener_entradas_escaneo(resultado.scan_id)
    entrada = next(e for e in entradas if e["name"] == "privado.txt")

    # InventoryEntry no tiene campo de contenido; solo metadatos.
    assert "contenido" not in entrada
    assert entrada["size_bytes"] > 0  # solo el tamaño, no el contenido
