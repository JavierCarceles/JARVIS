# -*- coding: utf-8 -*-
"""
Verificacion en entorno real de la unidad 3.8.5.1.4.10.4:
Contrastar una muestra representativa de rutas del inventario con el sistema
de archivos real y demostrar que altas, cambios y eliminaciones se reflejan
correctamente.

Opera exclusivamente sobre un directorio temporal real (tmp_path) y una base
de datos SQLite temporal. No toca datos de produccion ni rutas de usuario.
No usa mocks que decidan el resultado: toda la evidencia proviene de codigo
de produccion (src/hands/system_inventory.py y
src/hands/system_inventory_storage.py) ejecutado contra el sistema operativo
real.

Cubre:
  1. Contraste inicial: cada entrada del inventario se valida contra el SO
     real (search_con_evidencia -> validar_destino) y debe reportar
     existencia, tipo, volumen, identidad y accesibilidad correctos.
  2. Alta: se agrega un archivo, se vuelve a escanear y aparece en el ultimo
     inventario.
  3. Cambio: se modifica un archivo (tamano), se refresca su ruta y se
     detecta el cambio real contra el SO.
  4. Eliminacion: se borra un archivo, se vuelve a escanear y deja de
     aparecer en el ultimo inventario.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.hands.system_inventory import (
    EntryType,
    InventoryContract,
    escanear_ruta,
    generate_machine_id,
    InventoryEntry,
    validar_destino,
)
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    ResultadoValidacionDestino,
    SystemInventoryStorage,
)

MAQUINA = generate_machine_id()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "system_inventory.sqlite3"


@pytest.fixture
def storage(db_path: Path) -> SystemInventoryStorage:
    storage = SystemInventoryStorage(db_path)
    storage.initialize(machine_id_actual=MAQUINA)
    return storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_arbol_prueba(base: Path) -> dict[str, str]:
    """Crea archivos reales representativos y devuelve sus rutas absolutas."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "documento.txt").write_text("contenido inicial\n", encoding="utf-8")
    (base / "datos.csv").write_text("a,b,c\n", encoding="utf-8")
    subcarpeta = base / "subcarpeta"
    subcarpeta.mkdir(parents=True, exist_ok=True)
    (subcarpeta / "ejecutable.exe").write_text("MZ\x90\x00", encoding="utf-8")
    return {
        "documento": str(base / "documento.txt"),
        "datos": str(base / "datos.csv"),
        "ejecutable": str(subcarpeta / "ejecutable.exe"),
    }


def _escaneo_volumen(
    base: Path, storage: SystemInventoryStorage, maquina_id: str
):
    """Ejecuta un escaneo de produccion sobre el arbol real y lo valida."""
    contrato = InventoryContract(machine_id=maquina_id)
    resultado = escanear_ruta(
        ruta_absoluta=str(base),
        contrato=contrato,
        maquina_id=maquina_id,
        storage=storage,
    )
    assert resultado is not None
    assert resultado.resultado == SCAN_RESULT_OK
    assert resultado.completado is True
    assert resultado.interrumpido is False
    assert resultado.entradas_procesadas > 0
    return resultado


def _nombres_ultimo_scan(
    storage: SystemInventoryStorage, maquina_id: str, volumen: str
) -> set[str]:
    scan = storage.get_latest_scan(maquina_id, volumen)
    assert scan is not None
    entradas = storage.obtener_entradas_escaneo(scan["scan_id"])
    return {e["name"] for e in entradas}


def _entradas_con_evidencia_so(
    storage: SystemInventoryStorage, maquina_id: str, volumen: str
) -> list[dict]:
    """Devuelve las entradas del inventario con su evidencia de validacion
    real contra el sistema operativo (validar_destino)."""
    pagina = storage.search_con_evidencia(
        machine_id=maquina_id,
        volume=volumen,
        machine_id_actual=maquina_id,
        solo_volumes_montados=True,
        limit=200,
    )
    assert pagina is not None
    assert pagina["results"] is not None
    return pagina["results"]


def _assert_entrada_valida_contra_so(entrada: dict) -> None:
    """Cada entrada del inventario debe coincidir con el SO real."""
    evidencia = entrada.get("evidencia") or {}
    nombre = entrada.get("name")
    assert bool(evidencia.get("existencia_ok")) is True, (
        f"{nombre}: la ruta no existe en el sistema operativo"
    )
    assert bool(evidencia.get("tipo_ok")) is True, (
        f"{nombre}: el tipo de entrada no coincide con el SO"
    )
    assert bool(evidencia.get("volumen_ok")) is True, (
        f"{nombre}: el volumen no coincide con el SO"
    )
    assert bool(evidencia.get("identidad_ok")) is True, (
        f"{nombre}: la identidad de equipo no coincide"
    )
    assert bool(evidencia.get("accesible_ok")) is True, (
        f"{nombre}: la ruta no es accesible en el SO"
    )
    assert bool(evidencia.get("valido")) is True, (
        f"{nombre}: destino no valido ({evidencia.get('errores')})"
    )


# ---------------------------------------------------------------------------
# Pruebas de verificacion real (unidad 3.8.5.1.4.10.4)
# ---------------------------------------------------------------------------

def test_contraste_inventario_contra_sistema_archivos_real(
    tmp_path: Path, storage: SystemInventoryStorage
):
    """Contraste inicial: el inventario refleja el estado real del SO."""
    base = tmp_path / "arbol_contraste"
    rutas = _crear_arbol_prueba(base)
    storage.initialize(machine_id_actual=MAQUINA)

    escaneo = _escaneo_volumen(base, storage, MAQUINA)
    volumen = escaneo.volumen

    # Muestra representativa: todas las entradas del ultimo inventario se
    # contrastan contra el sistema de archivos real mediante validacion
    # de produccion (search_con_evidencia -> validar_destino).
    resultados = _entradas_con_evidencia_so(storage, MAQUINA, volumen)
    nombres_encontrados = {e["name"] for e in resultados}
    nombres_esperados = {Path(ruta).name for ruta in rutas.values()}
    assert nombres_esperados <= nombres_encontrados

    for entrada in resultados:
        _assert_entrada_valida_contra_so(entrada)


def test_alta_reflejada_en_inventario_real(
    tmp_path: Path, storage: SystemInventoryStorage
):
    """Un archivo agregado al arbol real aparece en el siguiente inventario."""
    base = tmp_path / "arbol_alta"
    _crear_arbol_prueba(base)
    storage.initialize(machine_id_actual=MAQUINA)

    escaneo = _escaneo_volumen(base, storage, MAQUINA)
    volumen = escaneo.volumen

    # Alta real: crear un archivo nuevo en el sistema de archivos.
    (base / "nuevo.txt").write_text("archivo recien creado\n", encoding="utf-8")

    escaneo_despues = _escaneo_volumen(base, storage, MAQUINA)
    assert escaneo_despues.scan_id != escaneo.scan_id

    nombres = _nombres_ultimo_scan(storage, MAQUINA, volumen)
    assert "nuevo.txt" in nombres
    assert "documento.txt" in nombres
    assert "datos.csv" in nombres
    assert "ejecutable.exe" in nombres

    # Contraste tras la alta: el nuevo registro tambien se valida contra el SO.
    resultados = _entradas_con_evidencia_so(storage, MAQUINA, volumen)
    nombres_resultados = {e["name"] for e in resultados}
    assert "nuevo.txt" in nombres_resultados
    for entrada in resultados:
        _assert_entrada_valida_contra_so(entrada)


def test_cambio_reflejado_en_inventario_real(
    tmp_path: Path, storage: SystemInventoryStorage
):
    """Un archivo modificado (tamano) se detecta al refrescar su ruta."""
    base = tmp_path / "arbol_cambio"
    rutas = _crear_arbol_prueba(base)
    storage.initialize(machine_id_actual=MAQUINA)

    escaneo = _escaneo_volumen(base, storage, MAQUINA)
    volumen = escaneo.volumen

    # Cambio real: agrandar el archivo para modificar su tamano.
    documento = rutas["documento"]
    tamano_antes = os.path.getsize(documento)
    with open(documento, "a", encoding="utf-8") as f:
        f.write("linea añadida para cambiar el tamano real del archivo\n")
    tamano_despues = os.path.getsize(documento)
    assert tamano_despues > tamano_antes

    # Refresco puntual de la ruta contra el SO real (sin nuevo escaneo),
    # usando el metodo de almacenamiento de produccion.
    refresco = storage.refrescar_entrada_por_ruta(machine_id=MAQUINA, volume=volumen, ruta_absoluta=documento)

    assert refresco["existe_ahora"] is True
    assert refresco["cambio_detectado"] is True, (
        "el cambio de tamano no se detectó al refrescar la ruta"
    )
    assert refresco["entradas_refrescadas"] == 1
    assert refresco["last_checked_at"] is not None


def test_eliminacion_reflejada_en_inventario_real(
    tmp_path: Path, storage: SystemInventoryStorage
):
    """Un archivo borrado del arbol real deja de estar en el inventario."""
    base = tmp_path / "arbol_eliminacion"
    rutas = _crear_arbol_prueba(base)
    storage.initialize(machine_id_actual=MAQUINA)

    escaneo = _escaneo_volumen(base, storage, MAQUINA)
    volumen = escaneo.volumen

    # Eliminacion real del archivo.
    os.remove(rutas["datos"])
    assert not os.path.exists(rutas["datos"])

    _escaneo_volumen(base, storage, MAQUINA)
    nombres = _nombres_ultimo_scan(storage, MAQUINA, volumen)

    assert "datos.csv" not in nombres
    assert "documento.txt" in nombres
    assert "ejecutable.exe" in nombres


def test_validar_destino_ruta_eliminada_reporta_invalido_entorno_real(
    tmp_path: Path, storage: SystemInventoryStorage
):
    """validar_destino contra el SO real rechaza una ruta que ya no existe."""
    base = tmp_path / "arbol_validacion"
    rutas = _crear_arbol_prueba(base)
    storage.initialize(machine_id_actual=MAQUINA)

    escaneo = _escaneo_volumen(base, storage, MAQUINA)
    volumen = escaneo.volumen

    # Eliminacion real del archivo.
    os.remove(rutas["datos"])
    assert not os.path.exists(rutas["datos"])

    # Construir la entrada tal como estaba en el inventario y validarla contra
    # el SO real: debe reportar existencia falsa y destino invalido.
    entrada = InventoryEntry(
        machine_id=MAQUINA,
        volume=volumen,
        absolute_path=rutas["datos"],
        relative_path="datos.csv",
        name="datos.csv",
        extension=".csv",
        entry_type=EntryType.FILE,
        size_bytes=0,
        modified_at="",
        created_at="",
        accessed_at=None,
        attributes=[],
        last_checked_at="",
    )
    validacion = validar_destino(entrada, machine_id_actual=MAQUINA)
    assert isinstance(validacion, ResultadoValidacionDestino)
    assert validacion.existencia_ok is False
    assert validacion.valido is False
    assert len(validacion.errores) >= 1
