# -*- coding: utf-8 -*-
"""
Verificacion de la unidad 3.8.5.1.4.10.9 (entorno real).

Comprueba que los candidatos identificados cubren los tipos de lanzamiento que
el adaptador del SO declara soportar y clasifica cada tipo como:
  - disponible: el adaptador soporta el tipo y hay un candidato identificado
                (real, validado por preflight) que lo cubre.
  - no verificado: el adaptador declara/detecta el tipo pero ningun candidato
                   identificado lo cubre aun en esta maquina.
  - no soportado: el tipo no aplica / no es soportado por el SO actual.

Restricciones de esta unidad (obligatorias):
- No se lanza ninguna aplicacion: solo validaciones estaticas de
  ApplicationPreflight.validate_launch_destination y lecturas de inventario.
- No se ejecuta en lote candidatos ni aplicaciones sensibles.
- No se modifica data/memory/entities.json ni data/knowledge/entities.json.
- Lectura solo-lectura de data/system_inventory.sqlite3 (tabla
  application_candidates); el mecanismo de registro se prueba sobre BD temporal.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from src.hands.application_preflight import ApplicationPreflight
from src.hands.application_launch_classifier import (
    LaunchClassifier,
    LaunchType,
)
from src.hands.system_inventory import generate_machine_id
from src.hands.system_inventory_storage import SystemInventoryStorage

# ---------------------------------------------------------------------------
# Rutas absolutas segun __file__ (el sandbox de conftest solo afecta rutas
# relativas al CWD; aqui leemos la base de produccion de solo lectura).
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]
PROD_DB = ROOT_DIR / "data" / "system_inventory.sqlite3"

MACHINE_ID = generate_machine_id()

# Destinos reales de cada tipo usados SOLO para validacion estatica de preflight
# (nunca se lanzan).
DEST_EJECUTABLE = r"C:\Windows\System32\charmap.exe"   # registrado en .10.8
DEST_URI_APLICACION = "ms-settings:"
DEST_LANZADOR = "steam://"


def _es_windows() -> bool:
    return os.name == "nt"


def _leer_candidatos_por_tipo(launch_type: str) -> list[dict]:
    """Lee (solo lectura) los candidatos registrados de un launch_type."""
    if not PROD_DB.exists():
        return []
    conn = sqlite3.connect(str(PROD_DB))
    try:
        cur = conn.execute(
            "SELECT candidate_id, name, absolute_path, launch_type, "
            "confidence AS confianza, source AS fuente "
            "FROM application_candidates WHERE machine_id=? AND launch_type=?",
            (MACHINE_ID, launch_type),
        )
        columnas = [d[0] for d in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]
    finally:
        conn.close()


def _buscar_lnk_real() -> str | None:
    """Busca (solo lectura, sin lanzar) un acceso directo .lnk real del sistema."""
    ubicaciones = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        r"C:\Users\Public\Desktop",
    ]
    for base in ubicaciones:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.casefold().endswith(".lnk"):
                    return os.path.join(root, fn)
    return None


# ---------------------------------------------------------------------------
# Componentes de produccion (instanciados una vez por modulo).
# ---------------------------------------------------------------------------
_preflight = ApplicationPreflight()
_clasificador = LaunchClassifier(preflight=_preflight)


class TestTiposDeclaradosPorAdaptador:
    """El adaptador del SO declara los seis tipos de LaunchType."""

    def test_seis_tipos_declarados(self):
        tipos = LaunchType.valores_admitidos()
        esperados = {
            "ejecutable", "acceso_directo", "uri_aplicacion",
            "paquete", "bundle", "lanzador",
        }
        assert esperados.issubset(tipos), f"tipos declarados={tipos}"


class TestEjecutableDisponible:
    """ejecutable: disponible (candidato real identificado y validado)."""

    def test_hay_candidato_registrado_ejecutable(self):
        filas = _leer_candidatos_por_tipo(LaunchType.EJECUTABLE.value)
        assert len(filas) >= 1, "debe haber al menos un candidato ejecutable registrado"
        ids = {f["candidate_id"] for f in filas}
        assert any("charmap" in (i or "").lower() for i in ids), f"ids={ids}"

    def test_preflight_valida_ejecutable_real_sin_lanzar(self):
        res = _preflight.validate_launch_destination(DEST_EJECUTABLE)
        assert res["valid"] is True, res.get("reason")
        assert res["launch_type"] == LaunchType.EJECUTABLE.value, res
        assert os.path.isfile(DEST_EJECUTABLE)

    def test_clasificador_ejecutable_es_lanzable(self):
        candidato = {
            "candidate_id": DEST_EJECUTABLE,
            "name": "Mapa de caracteres",
            "absolute_path": DEST_EJECUTABLE,
            "destination": DEST_EJECUTABLE,
            "source": "inventario",
            "volume": "C:",
            "launch_type": LaunchType.EJECUTABLE.value,
            "last_checked_at": "",
        }
        cls = _clasificador.classify_candidate(candidato)
        assert cls.launch_type == LaunchType.EJECUTABLE.value
        assert cls.es_lanzable is True
        assert cls.confianza in ("alta", "media")


class TestAccesoDirectoNoVerificado:
    """acceso_directo: no verificado (adapter soporta .lnk, 0 candidatos)."""

    def test_adaptador_soporta_lnk_real(self):
        lnk = _buscar_lnk_real()
        if lnk is None:
            pytest.skip("no se encontro ningun .lnk real para validar")
        res = _preflight.validate_launch_destination(lnk)
        assert res["valid"] is True, res.get("reason")
        assert res["launch_type"] == LaunchType.ACCESO_DIRECTO.value, res

    def test_no_hay_candidato_registrado_acceso_directo(self):
        filas = _leer_candidatos_por_tipo(LaunchType.ACCESO_DIRECTO.value)
        assert len(filas) == 0, f"candidatos acceso_directo inesperados={filas}"


class TestUriAplicacionNoVerificado:
    """uri_aplicacion: no verificado (adapter soporta esquemas, 0 candidatos)."""

    def test_adaptador_admite_uri_aplicacion_real(self):
        res = _preflight.validate_launch_destination(DEST_URI_APLICACION)
        assert res["valid"] is True, res.get("reason")
        assert res["launch_type"] == LaunchType.URI_APLICACION.value, res

    def test_no_hay_candidato_registrado_uri_aplicacion(self):
        filas = _leer_candidatos_por_tipo(LaunchType.URI_APLICACION.value)
        assert len(filas) == 0, f"candidatos uri_aplicacion inesperados={filas}"


class TestPaqueteNoVerificado:
    """paquete: no verificado (tipo detectable, sin candidato real en esta maquina)."""

    def test_no_hay_candidato_registrado_paquete(self):
        filas = _leer_candidatos_por_tipo(LaunchType.PAQUETE.value)
        assert len(filas) == 0, f"candidatos paquete inesperados={filas}"


class TestBundleNoSoportado:
    """bundle: no soportado en Windows (tipo macOS .app)."""

    @pytest.mark.skipif(not _es_windows(), reason="bundle no aplica en Windows")
    def test_bundle_no_aplica_en_windows(self):
        filas = _leer_candidatos_por_tipo(LaunchType.BUNDLE.value)
        assert len(filas) == 0, f"candidatos bundle inesperados={filas}"
        # validate_launch_destination no admite rutas .app en este SO.
        res = _preflight.validate_launch_destination("/Applications/MiApp.app")
        assert res["valid"] is False, res


class TestLanzadorNoVerificado:
    """lanzador: no verificado (detectable pero preflight no admite steam://)."""

    def test_adaptador_no_admite_lanzador_steam(self):
        res = _preflight.validate_launch_destination(DEST_LANZADOR)
        assert res["valid"] is False, res.get("reason")
        assert res["launch_type"] is None, res

    def test_no_hay_candidato_registrado_lanzador(self):
        filas = _leer_candidatos_por_tipo(LaunchType.LANZADOR.value)
        assert len(filas) == 0, f"candidatos lanzador inesperados={filas}"


class TestMatrizClasificacionFinal:
    """Matriz consolidada de clasificacion por tipo de lanzamiento."""

    def test_matriz_entrega_clasificacion_coherente(self):
        """Cada tipo declarado recibe una clasificacion justificada por evidencia
        real; ningun tipo queda sin clasificar y ninguno se asume disponible sin
        candidato que lo cubra."""
        matriz = {}
        for lt in LaunchType:
            filas = _leer_candidatos_por_tipo(lt.value)
            candidato_cubre = len(filas) > 0

            if lt == LaunchType.EJECUTABLE:
                res = _preflight.validate_launch_destination(DEST_EJECUTABLE)
                adapter_soporta = res["valid"] is True
                matriz[lt.value] = (
                    "disponible" if (adapter_soporta and candidato_cubre)
                    else "no_verificado"
                )
            elif lt == LaunchType.BUNDLE and _es_windows():
                matriz[lt.value] = "no_soportado"
            elif lt == LaunchType.LANZADOR:
                res = _preflight.validate_launch_destination(DEST_LANZADOR)
                adapter_soporta = res["valid"] is True
                matriz[lt.value] = (
                    "disponible" if (adapter_soporta and candidato_cubre)
                    else "no_verificado"
                )
            else:
                # acceso_directo, uri_aplicacion, paquete (y bundle fuera de Windows)
                adapter_soporta = False
                if lt == LaunchType.ACCESO_DIRECTO:
                    lnk = _buscar_lnk_real()
                    if lnk is not None:
                        adapter_soporta = (
                            _preflight.validate_launch_destination(lnk)["valid"]
                            is True
                        )
                elif lt == LaunchType.URI_APLICACION:
                    adapter_soporta = (
                        _preflight.validate_launch_destination(
                            DEST_URI_APLICACION
                        )["valid"]
                        is True
                    )
                matriz[lt.value] = (
                    "disponible" if (adapter_soporta and candidato_cubre)
                    else "no_verificado"
                )

        assert set(matriz.keys()) == LaunchType.valores_admitidos(), matriz
        assert matriz["ejecutable"] == "disponible", matriz
        assert matriz["acceso_directo"] == "no_verificado", matriz
        assert matriz["uri_aplicacion"] == "no_verificado", matriz
        assert matriz["paquete"] == "no_verificado", matriz
        if _es_windows():
            assert matriz["bundle"] == "no_soportado", matriz
        assert matriz["lanzador"] == "no_verificado", matriz


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
