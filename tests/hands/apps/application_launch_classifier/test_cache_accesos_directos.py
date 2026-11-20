# -*- coding: utf-8 -*-
"""
Tests de la cache de destinos de accesos directos de `LaunchClassifier`
(`lnk_targets`) y de `resolver_targets_accesos_directos` (resolucion por
lotes con un solo proceso PowerShell por lote).

Ficheros temporales (tmp_path); no lanza aplicaciones.

Ejecucion (Windows):
    python -m pytest tests/hands/apps/application_launch_classifier/test_cache_accesos_directos.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import src.hands.apps.application_launch_classifier as modulo
from src.hands.apps.application_launch_classifier import (
    CONFIANZA_MEDIA,
    LaunchClassifier,
    LaunchType,
    resolver_targets_accesos_directos,
)
from src.hands.apps.application_preflight import ApplicationPreflight


def _lnk(tmp_path: Path, nombre: str = "Editor.lnk") -> Path:
    ruta = tmp_path / "Start Menu" / "Programs" / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"lnk")
    return ruta


@pytest.fixture
def llamadas_individuales(monkeypatch):
    """Registra las llamadas a la resolucion individual (un PowerShell por .lnk)."""
    llamadas: list[str] = []

    def falso(ruta):
        llamadas.append(ruta)
        return None

    monkeypatch.setattr(modulo, "resolver_target_acceso_directo", falso)
    return llamadas


class TestCacheAccesosDirectos:

    def test_con_cache_no_resuelve_uno_a_uno(self, tmp_path, llamadas_individuales):
        lnk = _lnk(tmp_path)
        destino = tmp_path / "editor.exe"
        destino.write_bytes(b"MZ")
        clasificador = LaunchClassifier(
            preflight=ApplicationPreflight(), lnk_targets={str(lnk): str(destino)}
        )
        c = clasificador.classify_candidate({"name": lnk.name, "absolute_path": str(lnk)})
        assert c.launch_type == LaunchType.ACCESO_DIRECTO.value
        assert c.es_lanzable is True
        assert c.confianza == CONFIANZA_MEDIA
        assert "acceso_directo_target_resuelto" in c.evidencia
        assert llamadas_individuales == []

    def test_cache_con_none_marca_no_lanzable_sin_resolver(self, tmp_path, llamadas_individuales):
        lnk = _lnk(tmp_path)
        clasificador = LaunchClassifier(
            preflight=ApplicationPreflight(), lnk_targets={str(lnk): None}
        )
        c = clasificador.classify_candidate({"name": lnk.name, "absolute_path": str(lnk)})
        assert c.launch_type == LaunchType.ACCESO_DIRECTO.value
        assert c.es_lanzable is False
        assert "acceso_directo_rotu_o_invalido" in c.evidencia
        assert llamadas_individuales == []

    def test_sin_cache_comportamiento_anterior(self, tmp_path, llamadas_individuales):
        lnk = _lnk(tmp_path)
        clasificador = LaunchClassifier(preflight=ApplicationPreflight())
        c = clasificador.classify_candidate({"name": lnk.name, "absolute_path": str(lnk)})
        assert llamadas_individuales == [str(lnk)]
        assert c.es_lanzable is False

    def test_lnk_fuera_de_cache_se_resuelve_uno_a_uno(self, tmp_path, llamadas_individuales):
        en_cache = _lnk(tmp_path, "A.lnk")
        fuera = _lnk(tmp_path, "B.lnk")
        clasificador = LaunchClassifier(
            preflight=ApplicationPreflight(), lnk_targets={str(en_cache): None}
        )
        clasificador.classify_candidate({"name": en_cache.name, "absolute_path": str(en_cache)})
        clasificador.classify_candidate({"name": fuera.name, "absolute_path": str(fuera)})
        assert llamadas_individuales == [str(fuera)]

    def test_cache_ignora_mayusculas_segun_el_so(self, tmp_path, llamadas_individuales):
        lnk = _lnk(tmp_path)
        clave = str(lnk).upper() if os.name == "nt" else str(lnk)
        clasificador = LaunchClassifier(
            preflight=ApplicationPreflight(), lnk_targets={clave: None}
        )
        clasificador.classify_candidate({"name": lnk.name, "absolute_path": str(lnk)})
        assert llamadas_individuales == []


class TestResolverTargetsPorLotes:

    def test_lista_vacia(self):
        assert resolver_targets_accesos_directos([]) == {}

    @pytest.mark.skipif(os.name == "nt", reason="Comportamiento fuera de Windows (excepcion (a))")
    def test_fuera_de_windows_todo_none(self, tmp_path):
        lnk = _lnk(tmp_path)
        assert resolver_targets_accesos_directos([str(lnk), "C:\\no\\existe.lnk"]) == {
            str(lnk): None, "C:\\no\\existe.lnk": None,
        }

    @pytest.mark.skipif(os.name != "nt", reason="Resolucion por lotes solo en Windows (excepcion (a))")
    def test_un_proceso_por_lote(self, tmp_path, monkeypatch):
        rutas = [str(_lnk(tmp_path, f"App{i}.lnk")) for i in range(5)]
        inexistente = str(tmp_path / "no_existe.lnk")
        lotes: list[list[str]] = []

        def falso(parte, timeout):
            lotes.append(list(parte))
            return {r: None for r in parte}

        monkeypatch.setattr(modulo, "_resolver_lote_lnk_powershell", falso)
        resultado = resolver_targets_accesos_directos(rutas + [inexistente], lote=2)
        assert lotes == [rutas[0:2], rutas[2:4], rutas[4:5]]
        assert set(resultado) == set(rutas) | {inexistente}
        assert resultado[inexistente] is None

    @pytest.mark.skipif(os.name != "nt", reason="PowerShell y WScript.Shell solo en Windows (excepcion (a))")
    def test_powershell_real_resuelve_acceso_directo_creado(self, tmp_path):
        """Crea un .lnk real con WScript.Shell hacia notepad.exe (ruta con un
        caracter no ASCII) y lo resuelve por lotes."""
        import subprocess

        notepad = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "notepad.exe")
        if not os.path.isfile(notepad):
            pytest.fail("notepad.exe no encontrado en System32")
        carpeta = tmp_path / "Men\u00fa"
        carpeta.mkdir()
        lnk = carpeta / "Bloc de notas.lnk"
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:JARVIS_LNK); "
            "$s.TargetPath = $env:JARVIS_DESTINO; $s.Save()"
        )
        env = dict(os.environ, JARVIS_LNK=str(lnk), JARVIS_DESTINO=notepad)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True, env=env, timeout=60,
        )
        assert lnk.is_file()
        resultado = resolver_targets_accesos_directos([str(lnk)])
        assert resultado[str(lnk)] is not None
        assert os.path.normcase(resultado[str(lnk)]) == os.path.normcase(notepad)
