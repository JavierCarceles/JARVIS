# -*- coding: utf-8 -*-
"""
Verificacion en entorno real de la unidad 3.8.5.1.4.7.11.

Ejecuta `ApplicationDiscovery` sobre el equipo Windows real y valida cada
candidato descubierto a traves del pipeline completo:
  1. Descubrimiento real de fuentes del SO (menu, PATH, App Paths, registro).
  2. Clasificacion real con `LaunchClassifier` (tipo, subtipo, lanzabilidad,
     nombre comercial, aliases, confianza, evidencia).
  3. Validacion de destino con `ApplicationPreflight.validate_launch_destination`
     (gatekeeper, sin lanzar nada).

Tipos de candidatos probados:
- Aplicaciones conocidas (ejecutables GUI del sistema: notepad, calc).
- Aplicaciones no registradas (ejecutables en disco no presentes en entities.json).
- Herramientas CLI (cmd, powershell, ping, etc.).
- Instaladores (nombres con setup/install si se encuentran en el sistema).
- Accesos directos rotos (.lnk sin target valido).
- Paquetes (.appx, .msix si existen en el sistema).
- Falsos positivos (.dll, archivos con extension engañosa, directorios).

No lanza ninguna aplicacion, no instala ni modifica datos del usuario.
Solo clasifica y valida destinos estaticamente. Cada candidato se prueba
individualmente, sin ejecucion en lote de candidatos descubiertos.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from src.hands.application_discovery import (
    ApplicationDiscovery,
    DiscoveredCandidate,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    CONFIANZA_MEDIA,
    CONFIANZA_NINGUNA,
    LaunchClassifier,
    LaunchSubtype,
)


def _existe(ruta: str) -> bool:
    return bool(ruta) and os.path.exists(ruta)


def _si_existe_o_skip(ruta: str, nombre: str = "") -> str:
    """Retorna la ruta si existe en disco; si no, salta la prueba."""
    if not _existe(ruta):
        pytest.skip(f"{nombre or ruta} no disponible en este equipo")
    return ruta


# ---------------------------------------------------------------------------
# Fixture: clasificador y preflight reales (sin mocks)
# ---------------------------------------------------------------------------

@pytest.fixture
def clasificador():
    return LaunchClassifier()


@pytest.fixture
def preflight():
    return ApplicationPreflight()


@pytest.fixture
def discovery():
    return ApplicationDiscovery(machine_id=None)


# ---------------------------------------------------------------------------
# A. Aplicaciones conocidas (GUI reales del sistema)
# ---------------------------------------------------------------------------

class TestAplicacionesConocidas:
    """Aplicaciones GUI conocidas del sistema operativo, probadas una a una."""

    def test_notepad_conocido_pipeline_completo(self, clasificador, preflight):
        """notepad.exe: conocida, GUI, lanzable, preflight admite."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\notepad.exe", "notepad.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "notepad", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.es_lanzable is True
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True
        assert decision["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE

    def test_calc_conocido_pipeline_completo(self, clasificador, preflight):
        """calc.exe: conocida, GUI, lanzable, preflight admite."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\calc.exe", "calc.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "calc", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.es_lanzable is True
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True

    def test_python_conocido_pipeline_completo(self, clasificador, preflight):
        """python.exe: conocida, lanzable, con version y nombre comercial."""
        ruta = sys.executable
        clasificacion = clasificador.classify_candidate(
            {"name": "python", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.es_lanzable is True
        assert clasificacion.version is not None
        assert clasificacion.nombre_comercial is not None
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True


# ---------------------------------------------------------------------------
# B. Aplicaciones no registradas (ejecutables en disco, no en entities.json)
# ---------------------------------------------------------------------------

class TestAplicacionesNoRegistradas:
    """Ejecutables reales encontrados en disco que no forman parte del
    catalogo conocido (entities.json), probados individualmente."""

    def test_ejecutable_sistema_no_registrado(self, clasificador, preflight):
        """Un ejecutable del sistema no en el catalogo conocido sigue
        clasificandose y validandose correctamente."""
        # tasklist.exe es un ejecutable real del sistema, tipicamente no
        # registrado como entidad conocida en entities.json.
        ruta = _si_existe_o_skip(r"C:\Windows\System32\tasklist.exe", "tasklist.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "tasklist", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.es_lanzable is True
        assert clasificacion.fuente == "sistema_real"
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True

    def test_ejecutable_no_registrado_confianza_registrada(self, clasificador):
        """Un ejecutable no registrado registra todos los campos de .7.6:
        fuente, destino, tipo, version, ultima comprobacion, evidencia, confianza."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\tasklist.exe", "tasklist.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "tasklist", "absolute_path": ruta, "source": "inventario_complementario"}
        )
        assert clasificacion.fuente == "inventario_complementario"
        assert clasificacion.absolute_path == ruta
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.ultima_comprobacion != ""
        assert isinstance(clasificacion.evidencia, list)
        assert len(clasificacion.evidencia) >= 1
        assert clasificacion.confianza in (
            CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA
        )


# ---------------------------------------------------------------------------
# C. Herramientas CLI
# ---------------------------------------------------------------------------

class TestHerramientasCLI:
    """Herramientas de linea de comando reales, clasificadas como HERRAMIENTA_CLI."""

    def test_cmd_cli_pipeline_completo(self, clasificador, preflight):
        """cmd.exe: herramienta CLI real, lanzable, preflight admite."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\cmd.exe", "cmd.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "cmd", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.launch_subtype == LaunchSubtype.HERRAMIENTA_CLI
        assert clasificacion.es_lanzable is True
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True

    def test_ping_cli_mediante_subsistema_pe(self, clasificador, preflight):
        """ping.exe: herramienta CLI detectada mediante subsistema PE (no por
        nombre en _NOMBRES_CLI), lanzable."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\ping.exe", "ping.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "ping", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.launch_subtype == LaunchSubtype.HERRAMIENTA_CLI
        assert clasificacion.es_lanzable is True
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True

    def test_powershell_cli_si_existe(self, clasificador, preflight):
        """powershell.exe: herramienta CLI si existe en el equipo."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "powershell.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "powershell", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.es_lanzable is True
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is True


# ---------------------------------------------------------------------------
# D. Instaladores (nombres con setup/install en ejecutables reales)
# ---------------------------------------------------------------------------

class TestInstaladores:
    """Ejecutables con nombres de instalador (setup, install) clasificados
    como subtipo INSTALADOR. No se lanzan, solo se clasifican y validan."""

    def test_instalador_si_se_encuentra_en_sistema(self, clasificador, preflight):
        """Busca un ejecutable con nombre de instalador en ubicaciones comunes
        del sistema y verifica que se clasifica como INSTALADOR."""
        rutas_instalador = [
            r"C:\Windows\System32\msiexec.exe",
        ]
        encontrado = False
        for ruta in rutas_instalador:
            if _existe(ruta):
                encontrado = True
                clasificacion = clasificador.classify_candidate(
                    {"name": "msiexec", "absolute_path": ruta, "source": "sistema_real"}
                )
                assert clasificacion.launch_subtype == LaunchSubtype.INSTALADOR, (
                    f"{ruta} deberia clasificarse como INSTALADOR, obtuvo "
                    f"{clasificacion.launch_subtype}"
                )
                assert clasificacion.launch_type == "ejecutable"
                decision = preflight.validate_launch_destination(ruta)
                assert isinstance(decision, dict)
                assert "valid" in decision
                break
        if not encontrado:
            pytest.skip("No se encontro ejecutable de instalador en el sistema")


# ---------------------------------------------------------------------------
# E. Accesos directos rotos
# ---------------------------------------------------------------------------

class TestAccesosDirectosRotos:
    """.lnk sin target valido: clasificados como ACCESO_DIRECTO pero no lanzables."""

    def test_acceso_directo_roto_no_lanzable(self, clasificador, preflight):
        """Un archivo .lnk fabricado (sin target valido) se clasifica como
        acceso directo pero no es lanzable."""
        with tempfile.NamedTemporaryFile(suffix=".lnk", delete=False) as f:
            ruta = f.name
        try:
            clasificacion = clasificador.classify_candidate(
                {"name": "acceso_roto", "absolute_path": ruta, "source": "temporal_prueba"}
            )
            assert clasificacion.launch_type == "acceso_directo"
            assert clasificacion.es_lanzable is False
            assert "acceso_directo_rotu_o_invalido" in (
                clasificacion.evidencia + clasificacion.advertencias
            )
            # El preflight admite el .lnk como archivo de acceso directo existente
            # (solo valida que el archivo exista, no que el target resuelva).
            # La decision de no lanzarla corresponde al clasificador.
            decision = preflight.validate_launch_destination(ruta)
            assert decision["valid"] is True
            assert decision["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_SHORTCUT
        finally:
            os.unlink(ruta)


# ---------------------------------------------------------------------------
# F. Paquetes (.appx, .msix)
# ---------------------------------------------------------------------------

class TestPaquetes:
    """Paquetes de aplicación (.appx, .msix) si existen en el sistema."""

    def test_paquete_appx_si_existe(self, clasificador, preflight):
        """Busca un archivo .appx en el sistema y verifica que se clasifica
        como PAQUETE. Si no hay ninguno, se salta."""
        rutas_paquete = [
            r"C:\Windows\SystemApps\Microsoft.Windows.Cortana_cw5n1h2txyewy\AppxManifest.xml",
        ]
        # Buscar .appx en Program Files y Windows (no recursivo masivo, solo rutas conocidas)
        found_appx = None
        for base in [r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)"]:
            if not _existe(base):
                continue
            try:
                for entry in os.listdir(base):
                    if entry.lower().endswith((".appx", ".msix", ".appxbundle", ".msixbundle")):
                        found_appx = os.path.join(base, entry)
                        break
            except (OSError, PermissionError):
                continue
            if found_appx:
                break

        if not found_appx:
            pytest.skip("No se encontro paquete .appx/.msix en el sistema")

        clasificacion = clasificador.classify_candidate(
            {"name": Path(found_appx).stem, "absolute_path": found_appx, "source": "sistema_real"}
        )
        assert clasificacion.launch_type == "paquete"
        assert isinstance(clasificacion.es_lanzable, bool)
        decision = preflight.validate_launch_destination(found_appx)
        assert isinstance(decision, dict)
        assert "valid" in decision


# ---------------------------------------------------------------------------
# G. Falsos positivos
# ---------------------------------------------------------------------------

class TestFalsosPositivos:
    """Archivos que parecen aplicaciones pero no lo son: .dll, .txt con
    extension .exe, directorios, archivos inexistentes."""

    def test_dll_no_es_aplicacion_lanzable(self, clasificador, preflight):
        """kernel32.dll: biblioteca, no lanzable."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\kernel32.dll", "kernel32.dll")
        clasificacion = clasificador.classify_candidate(
            {"name": "kernel32", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_subtype == LaunchSubtype.BIBLIOTECA
        assert clasificacion.es_lanzable is False
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is False

    def test_archivo_txt_no_es_ejecutable(self, clasificador, preflight):
        """Archivo .txt: no es un destino de lanzamiento valido."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"contenido de prueba")
            ruta = f.name
        try:
            clasificacion = clasificador.classify_candidate(
                {"name": "falso_txt", "absolute_path": ruta, "source": "temporal_prueba"}
            )
            assert clasificacion.launch_type is None
            assert clasificacion.es_lanzable is False
            decision = preflight.validate_launch_destination(ruta)
            assert decision["valid"] is False
        finally:
            os.unlink(ruta)

    def test_directorio_no_es_aplicacion(self, clasificador, preflight):
        """Un directorio no es un destino de lanzamiento valido."""
        ruta = r"C:\Windows"
        clasificacion = clasificador.classify_candidate(
            {"name": "directorio_windows", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.es_lanzable is False
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is False

    def test_ejecutable_inexistente_no_es_lanzable(self, clasificador, preflight):
        """Un ejecutable que no existe en disco es rechazado."""
        ruta = r"C:\No\Existe\aplicacion_fantasma.exe"
        clasificacion = clasificador.classify_candidate(
            {"name": "fantasma", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert clasificacion.launch_type is None
        assert clasificacion.es_lanzable is False
        assert clasificacion.confianza == CONFIANZA_NINGUNA
        decision = preflight.validate_launch_destination(ruta)
        assert decision["valid"] is False


# ---------------------------------------------------------------------------
# H. Pipeline completo: ApplicationDiscovery + clasificacion + preflight
# ---------------------------------------------------------------------------

class TestPipelineCompletoDescubrimiento:
    """El pipeline completo de descubrimiento real: descubrir, clasificar,
    validar con preflight, sin lanzar aplicaciones."""

    def test_descubrir_todos_retorna_candidatos_con_preflight(self, discovery):
        """descubrir_todos() devuelve candidatos con decision de preflight
        incluida (no None) para cada destino."""
        resultado = discovery.descubrir_todos(limite_por_fuente=30, incluir_inventario=False)
        assert isinstance(resultado, list)
        assert len(resultado) >= 1, (
            "Se esperaba al menos un candidato real de las fuentes primarias del SO"
        )
        for c in resultado:
            assert isinstance(c, DiscoveredCandidate)
            assert c.name
            assert c.ultima_comprobacion
            assert c.fuente
            assert c.confianza in (
                CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA
            )
            if c.destination:
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
                assert "launch_type" in c.preflight_decision

    def test_candidatos_lanzables_son_solo_lanzables(self, discovery):
        """candidatos_lanzables() retorna solo candidatos con es_lanzable=True."""
        lanzables = discovery.candidatos_lanzables(limite_por_fuente=30, incluir_inventario=False)
        assert isinstance(lanzables, list)
        for c in lanzables:
            assert c.es_lanzable is True

    def test_no_duplica_destinos_reales_en_pipeline(self, discovery):
        """El pipeline completo no duplica destinos reales en disco."""
        resultado = discovery.descubrir_todos(limite_por_fuente=30, incluir_inventario=False)
        destinos_reales = [
            c.destination.casefold()
            for c in resultado
            if c.destination and os.path.exists(c.destination)
        ]
        assert len(destinos_reales) == len(set(destinos_reales)), (
            "Hay destinos reales duplicados despues del pipeline completo"
        )

    def test_buscar_por_nombre_devuelve_candidato_con_preflight(self, discovery):
        """buscar_por_nombre devuelve candidatos con decision de preflight."""
        todos = discovery.descubrir_todos(limite_por_fuente=30, incluir_inventario=False)
        assert len(todos) >= 1
        nombre = todos[0].name
        resultados = discovery.buscar_por_nombre(nombre, incluir_inventario=True)
        assert len(resultados) >= 1
        for c in resultados:
            if c.destination:
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision


# ---------------------------------------------------------------------------
# I. Registro de campos .7.6 en pipeline completo
# ---------------------------------------------------------------------------

class TestRegistroCampos76Pipeline:
    """Verifica .7.6: cada candidato del pipeline registra fuente, ruta/destino,
    tipo de lanzamiento, version/producto si existen, ultima comprobacion,
    evidencia y nivel de confianza."""

    def test_candidato_real_registra_todos_campos_76(self, clasificador):
        """Un ejecutable real registra todos los campos requeridos por .7.6."""
        ruta = _si_existe_o_skip(r"C:\Windows\System32\notepad.exe", "notepad.exe")
        clasificacion = clasificador.classify_candidate(
            {"name": "notepad", "absolute_path": ruta, "source": "menu_inicio"}
        )
        assert clasificacion.fuente == "menu_inicio"
        assert clasificacion.absolute_path == ruta
        assert clasificacion.destination == ruta
        assert clasificacion.launch_type == "ejecutable"
        assert clasificacion.version is not None
        assert clasificacion.producto is not None
        assert clasificacion.ultima_comprobacion != ""
        assert isinstance(clasificacion.evidencia, list)
        assert len(clasificacion.evidencia) >= 1
        assert clasificacion.confianza in (
            CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA
        )
        d = clasificacion.to_dict()
        assert d["fuente"] == "menu_inicio"
        assert d["absolute_path"] == ruta
        assert d["launch_type"] == "ejecutable"
        assert "version" in d
        assert "producto" in d
        assert "evidencia" in d
        assert "confianza" in d
        assert "ultima_comprobacion" in d
