# -*- coding: utf-8 -*-
"""
Test de entorno real para la unidad 3.8.5.1.4.6.8.

Genera una base de datos SQLite de inventario con un volumen significativo
de entradas (miles de archivos REALES creados en un directorio temporal) y
verifica, sobre la implementacion de produccion de
`src.hands.system_inventory_storage.SystemInventoryStorage`:

- busquedas por nombre exacto, extension, prefijo de ruta y tipo de entrada;
- paginacion (offset y cursor) sin cargar toda la base de datos en memoria,
  recorriendo todas las entradas sin duplicados ni omisiones;
- ordenacion por distintos campos (nombre, extension, tamano);
- rendimiento (tiempos reales de consulta sobre miles de entradas);
- revalidacion real contra el sistema operativo (existencia, tipo, volumen,
  identidad y accesibilidad) vía `search_con_evidencia`.

Todo se ejecuta en directorios temporales (tmp_path) y se limpia al finalizar.
No toca datos de produccion ni rutas de usuario.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SystemInventoryStorage,
)

# Volumen significativo de entradas para esta verificacion. Supera claramente
# las 500 entradas de los tests de escala existentes y ejerce paginacion,
# orden y revalidacion sobre una base de datos de tamano no trivial.
TOTAL_ENTRADAS = 3000
MACHINE_ID = "machine-significativo"
SCAN_ID = "scan-significativo"
EXTENSIONES = (".exe", ".dll", ".pdf", ".txt")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "system_inventory_significativo.sqlite3"


@pytest.fixture
def storage(db_path: Path) -> SystemInventoryStorage:
    return SystemInventoryStorage(db_path)


def _volumen_de_ruta(ruta: str) -> str:
    """Devuelve el identificador de volumen de una ruta absoluta (ej. "C:")."""
    return Path(ruta).drive


def _crear_archivos_reales(tmp_path: Path, n: int = TOTAL_ENTRADAS) -> list[dict]:
    """Crea n archivos reales en disco bajo tmp_path y devuelve sus metadatos.

    Cada archivo se escribe realmente en el sistema de archivos para que la
    revalidacion posterior (`validar_destino` vía `search_con_evidencia`) se
    ejecute contra el SO real y no contra rutas inventadas.
    """
    base = tmp_path / "inventario_significativo"
    base.mkdir(parents=True, exist_ok=True)
    entradas: list[dict] = []
    for i in range(n):
        ext = EXTENSIONES[i % len(EXTENSIONES)]
        sub = base / f"grupo{i % 10}"
        sub.mkdir(parents=True, exist_ok=True)
        nombre = f"archivo_{i:06d}{ext}"
        ruta = sub / nombre
        ruta.write_text(f"contenido de prueba archivo {i}\n", encoding="utf-8")
        stat = ruta.stat()
        entradas.append({
            "entry_id": f"e-{i:06d}",
            "absolute_path": str(ruta),
            "relative_path": str(ruta.relative_to(tmp_path)),
            "name": nombre,
            "extension": ext,
            "entry_type": "file",
            "size_bytes": int(stat.st_size),
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "accessed_at": "",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        })
    return entradas


def _indexar(storage: SystemInventoryStorage, entradas: list[dict]) -> None:
    """Inicializa el almacenamiento e indexa las entradas en un escaneo real."""
    volumen = _volumen_de_ruta(entradas[0]["absolute_path"])
    storage.initialize()
    storage.begin_scan_run(SCAN_ID, MACHINE_ID, volumen, SCAN_MODE_FULL)
    try:
        storage.insert_file_entries(SCAN_ID, MACHINE_ID, volumen, entradas)
        storage.end_scan_run(SCAN_ID, entries_count=len(entradas))
    except Exception:
        storage.end_scan_run(SCAN_ID, result="interrumpido")
        raise


def test_volumen_significativo_almacenado_y_contado(storage, tmp_path):
    """Todas las entradas se almacenan y count devuelve el total real."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    assert storage.count(MACHINE_ID) == TOTAL_ENTRADAS
    assert storage.count(MACHINE_ID, extension=".exe") == TOTAL_ENTRADAS // 4
    assert storage.count(MACHINE_ID, extension=".dll") == TOTAL_ENTRADAS // 4
    assert storage.count(MACHINE_ID, extension=".pdf") == TOTAL_ENTRADAS // 4
    assert storage.count(MACHINE_ID, extension=".txt") == TOTAL_ENTRADAS // 4


def test_busqueda_por_nombre_exacto_devuelve_coincidentes(storage, tmp_path):
    """La busqueda por nombre exacto devuelve solo la entrada que coincide."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    resultado = storage.search(MACHINE_ID, name="archivo_000000.exe")
    assert len(resultado) == 1
    assert resultado[0]["name"] == "archivo_000000.exe"
    assert resultado[0]["extension"] == ".exe"

    # Un nombre que no existe no devuelve resultados.
    assert storage.search(MACHINE_ID, name="no_existe_xyz.exe") == []


def test_busqueda_por_extension_devuelve_subconjunto(storage, tmp_path):
    """La busqueda por extension devuelve solo entradas de esa extension."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    resultado = storage.search(MACHINE_ID, extension=".exe", limit=100)
    assert 1 <= len(resultado) <= 100
    for entrada in resultado:
        assert entrada["extension"] == ".exe"


def test_busqueda_por_prefijo_ruta_y_tipo(storage, tmp_path):
    """La busqueda por prefijo de ruta y tipo filtra correctamente."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    prefijo_grupo = str(tmp_path / "inventario_significativo" / "grupo0")
    resultado = storage.search(MACHINE_ID, ruta=prefijo_grupo, tipo="file", limit=50)
    assert len(resultado) > 0
    for entrada in resultado:
        assert entrada["entry_type"] == "file"
        assert entrada["absolute_path"].startswith(prefijo_grupo)


def test_paginacion_offset_recorre_todos_sin_duplicados(storage, tmp_path):
    """La paginacion por offset recorre todas las entradas sin duplicados."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    vistos: set[str] = set()
    offset = 0
    paginas = 0
    while True:
        pagina = storage.search_paginated(
            MACHINE_ID, limit=200, offset=offset,
            solo_volumes_montados=True,
        )
        for entrada in pagina["results"]:
            assert entrada["entry_id"] not in vistos
            vistos.add(entrada["entry_id"])
        paginas += 1
        assert pagina["total"] == TOTAL_ENTRADAS
        if not pagina["has_more"]:
            break
        offset += 200

    assert len(vistos) == TOTAL_ENTRADAS
    assert paginas * 200 >= TOTAL_ENTRADAS


def test_paginacion_cursor_recorre_todos_sin_duplicados(storage, tmp_path):
    """La paginacion por cursor recorre todas las entradas sin duplicados."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    vistos: set[str] = set()
    cursor = None
    paginas = 0
    while True:
        pagina = storage.search_paginated(
            MACHINE_ID, limit=200, cursor=cursor,
            solo_volumes_montados=True,
        )
        for entrada in pagina["results"]:
            assert entrada["entry_id"] not in vistos
            vistos.add(entrada["entry_id"])
        paginas += 1
        assert pagina["total"] == TOTAL_ENTRADAS
        if not pagina["has_more"]:
            break
        cursor = pagina["next_cursor"]

    assert len(vistos) == TOTAL_ENTRADAS


def test_orden_por_nombre_y_extension(storage, tmp_path):
    """Los resultados se ordenan segun el campo solicitado."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    por_nombre = storage.search(
        MACHINE_ID, extension=".exe", limit=60, order_by="name",
        solo_volumes_montados=True,
    )
    nombres = [e["name"] for e in por_nombre]
    assert nombres == sorted(nombres)

    por_extension = storage.search(
        MACHINE_ID, limit=60, order_by="extension",
        solo_volumes_montados=True,
    )
    extensiones = [e["extension"] for e in por_extension]
    assert extensiones == sorted(extensiones)


def test_rendimiento_busqueda_indexada(storage, tmp_path):
    """Una busqueda indexada sobre miles de entradas completa en tiempo razonable."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    inicio = time.perf_counter()
    resultado = storage.search(MACHINE_ID, extension=".exe", limit=50)
    duracion = time.perf_counter() - inicio

    assert 1 <= len(resultado) <= 50
    # Umbral generoso para evitar flakiness por carga del equipo; se registra
    # el tiempo real como evidencia de rendimiento.
    assert duracion < 10.0, f"Busqueda indexada demasiado lenta: {duracion:.3f}s"
    print(f"\n[rendimiento] busqueda indexada (extension=.exe, {TOTAL_ENTRADAS} entradas): {duracion:.4f}s")


def test_rendimiento_recorrido_paginado_completo(storage, tmp_path):
    """Recorrer toda la base paginada completa en tiempo razonable."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    inicio = time.perf_counter()
    vistos: set[str] = set()
    offset = 0
    while True:
        pagina = storage.search_paginated(
            MACHINE_ID, limit=200, offset=offset,
            solo_volumes_montados=True,
        )
        for entrada in pagina["results"]:
            vistos.add(entrada["entry_id"])
        if not pagina["has_more"]:
            break
        offset += 200
    duracion = time.perf_counter() - inicio

    assert len(vistos) == TOTAL_ENTRADAS
    assert duracion < 60.0, f"Recorrido paginado completo demasiado lento: {duracion:.3f}s"
    print(f"\n[rendimiento] recorrido paginado completo ({TOTAL_ENTRADAS} entradas): {duracion:.4f}s")


def test_revalidacion_real_archivos_existentes(storage, tmp_path):
    """search_con_evidencia adjunta evidencia real de validacion contra el SO."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    volumen = _volumen_de_ruta(entradas[0]["absolute_path"])
    pagina = storage.search_con_evidencia(
        MACHINE_ID, extension=".exe", limit=10,
        machine_id_actual=MACHINE_ID,
        solo_volumes_montados=True,
    )

    assert pagina["total"] >= 1
    assert len(pagina["results"]) >= 1
    for entrada in pagina["results"]:
        evidencia = entrada["evidencia"]
        assert evidencia["disponible"] is True
        assert evidencia["existencia_ok"] is True, entrada["absolute_path"]
        assert evidencia["tipo_ok"] is True, entrada["absolute_path"]
        assert evidencia["volumen_ok"] is True, entrada["absolute_path"]
        assert evidencia["identidad_ok"] is True, entrada["absolute_path"]
        assert evidencia["accesible_ok"] is True, entrada["absolute_path"]
        assert evidencia["valido"] is True, entrada["absolute_path"]
        # Campos planos de conveniencia rellenados por el consumidor.
        assert entrada["procedencia"] == "filesystem_scan"
        assert entrada["volumen"] == volumen
        assert entrada["fecha_ultima_comprobacion"]


def test_revalidacion_ruta_inexistente_reporta_no_existe(storage, tmp_path):
    """Una ruta indexada que ya no existe en el SO reporta existencia_ok=False."""
    # Unica entrada apuntando a una ruta que no se crea en disco.
    ruta_inexistente = str(tmp_path / "no_debe_existir.exe")
    entradas = [{
        "entry_id": "e-inexistente",
        "absolute_path": ruta_inexistente,
        "relative_path": "no_debe_existir.exe",
        "name": "no_debe_existir.exe",
        "extension": ".exe",
        "entry_type": "file",
        "size_bytes": 0,
        "modified_at": "2024-01-01T10:00:00",
        "created_at": "2024-01-01T09:00:00",
        "accessed_at": "",
        "attributes": [],
        "excluded": False,
        "source": "filesystem_scan",
        "last_checked_at": "2024-01-03T00:00:00",
    }]
    _indexar(storage, entradas)

    pagina = storage.search_con_evidencia(
        MACHINE_ID, name="no_debe_existir.exe", limit=10,
        machine_id_actual=MACHINE_ID,
        solo_volumes_montados=True,
    )

    assert pagina["total"] == 1
    evidencia = pagina["results"][0]["evidencia"]
    assert evidencia["disponible"] is True
    assert evidencia["existencia_ok"] is False
    assert evidencia["valido"] is False
    assert "no existe" in str(evidencia.get("errores", ""))


def test_diferenciacion_estado_acceso_ejecutables(storage, tmp_path):
    """Los archivos .exe existentes se marcan como ejecutables candidatas."""
    entradas = _crear_archivos_reales(tmp_path)
    _indexar(storage, entradas)

    pagina = storage.diferenciar_estado_acceso(
        MACHINE_ID, extension=".exe", limit=20,
        machine_id_actual=MACHINE_ID,
        solo_volumes_montados=True,
    )

    assert pagina["total"] >= 1
    for entrada in pagina["results"]:
        diff = entrada["diferenciacion"]
        assert diff["encontrado_en_inventario"] is True
        assert diff["existe_ahora"] is True
        assert diff["accesible_ahora"] is True
        assert diff["ejecutable"] is True
        assert diff["candidato_a_aplicacion"] is True
