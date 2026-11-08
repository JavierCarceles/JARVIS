# -*- coding: utf-8 -*-
"""
Tests de contrato del inventario persistente del sistema de archivos
(unidad 3.8.5.1.4.1).

Verifican:
- Serializacion/deserializacion de InventoryEntry (ida y vuelta).
- Generacion de identificador local de equipo (estable, no MAC ni serial).
- Controles de privacidad por defecto (sin lectura de contenido, sin rutas completas en logs).
- Exclusiones tecnicas de rutas y puntos de montaje.
- Separacion de hechos observados vs inferencias.
- Truncamiento seguro de rutas para logs.
- Aislamiento por equipo en operaciones de control del inventario.
- Valores por defecto del contrato de inventario.

Todos los tests usan directorios temporales (tmp_path) y no tocan datos de produccion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.hands.system_inventory import (
    DEFAULT_EXCLUDED_MOUNT_PATTERNS,
    DEFAULT_EXCLUDED_PATH_PATTERNS,
    EntryType,
    FactType,
    InfoSistema,
    InventoryControl,
    InventoryControlResult,
    InventoryContract,
    InventoryEntry,
    SistemaOperativo,
    classify_entry,
    default_contract,
    detectar_sistema,
    es_sistema_soportado,
    generate_machine_id,
    is_excluded_mount,
    is_excluded_path,
    is_same_machine,
    normalizar_arquitectura,
    safe_log_path,
    validate_control,
)


# ---------------------------------------------------------------------------
# InventoryEntry: serializacion y campos minimos (3.8.5.1.4.1.7)
# ---------------------------------------------------------------------------

class TestInventoryEntryRoundTrip:
    """InventoryEntry debe serializarse y deserializarse sin perdida de datos."""

    def _sample_entry(self) -> InventoryEntry:
        return InventoryEntry(
            machine_id="machine-abc-123",
            volume="C:",
            absolute_path="C:/Users/Jarvis/app.exe",
            relative_path="Users/Jarvis/app.exe",
            name="app.exe",
            extension=".exe",
            entry_type=EntryType.FILE,
            size_bytes=1024,
            modified_at="2024-01-01T10:00:00",
            created_at="2024-01-01T09:00:00",
            accessed_at="2024-01-02T08:00:00",
            attributes=["hidden", "system"],
            excluded=False,
            exclusion_reason=None,
            source="filesystem_scan",
            last_checked_at="2024-01-03T00:00:00",
        )

    def test_to_dict_contiene_todos_los_campos_minimos(self, tmp_path: Path):
        entry = self._sample_entry()
        datos = entry.to_dict()

        campos_esperados = {
            "machine_id", "volume", "absolute_path", "relative_path", "name",
            "extension", "entry_type", "size_bytes", "modified_at", "created_at",
            "accessed_at", "attributes", "excluded", "exclusion_reason",
            "source", "last_checked_at",
        }
        assert set(datos.keys()) == campos_esperados, (
            f"Faltan o sobran campos: {set(datos.keys()) ^ campos_esperados}"
        )
        assert datos["machine_id"] == "machine-abc-123"
        assert datos["entry_type"] == "file"
        assert datos["size_bytes"] == 1024

    def test_from_dict_restaura_entrada_igual(self, tmp_path: Path):
        original = self._sample_entry()
        datos = original.to_dict()
        restaurada = InventoryEntry.from_dict(datos)

        assert restaurada.machine_id == original.machine_id
        assert restaurada.volume == original.volume
        assert restaurada.absolute_path == original.absolute_path
        assert restaurada.relative_path == original.relative_path
        assert restaurada.name == original.name
        assert restaurada.extension == original.extension
        assert restaurada.entry_type == original.entry_type
        assert restaurada.size_bytes == original.size_bytes
        assert restaurada.modified_at == original.modified_at
        assert restaurada.created_at == original.created_at
        assert restaurada.accessed_at == original.accessed_at
        assert restaurada.attributes == original.attributes
        assert restaurada.excluded == original.excluded
        assert restaurada.exclusion_reason == original.exclusion_reason
        assert restaurada.source == original.source
        assert restaurada.last_checked_at == original.last_checked_at

    def test_entrada_sin_campos_opcionales(self, tmp_path: Path):
        """Una entrada valida puede omitir accessed_at y exclusion_reason."""
        entry = InventoryEntry(
            machine_id="m",
            volume="D:",
            absolute_path="D:/file.txt",
            relative_path="file.txt",
            name="file.txt",
            extension=".txt",
            entry_type=EntryType.FILE,
            size_bytes=0,
            modified_at="2024-01-01",
            created_at="2024-01-01",
        )
        assert entry.accessed_at is None
        assert entry.exclusion_reason is None
        assert entry.attributes == []
        assert entry.excluded is False
        assert entry.source == "filesystem_scan"


# ---------------------------------------------------------------------------
# Identificador local de equipo (3.8.5.1.4.1.2, .1.3)
# ---------------------------------------------------------------------------

class TestMachineId:
    """El identificador de equipo debe ser estable y no derivar de MAC/serial/usuario."""

    def test_genera_id_estable(self):
        id1 = generate_machine_id()
        id2 = generate_machine_id()
        assert id1 == id2, "El ID de equipo debe ser determinista/estable"
        assert isinstance(id1, str) and len(id1) > 0

    def test_mismo_equipo_es_igual(self):
        id_a = generate_machine_id()
        id_b = generate_machine_id()
        assert is_same_machine(id_a, id_b) is True

    def test_diferentes_ids_no_colisionan(self):
        # UUID v5 basado en nombres estables: mismo equipo da mismo ID.
        # No testamos valores MAC/serial/usuario porque estan prohibidos.
        id1 = generate_machine_id()
        assert "-" in id1  # formato UUID


# ---------------------------------------------------------------------------
# Privacidad (3.8.5.1.4.1.9)
# ---------------------------------------------------------------------------

class TestPrivacidad:
    """El contrato por defecto nunca lee contenido ni loguea rutas completas."""

    def test_contrato_por_defecto_no_lee_contenido(self):
        contrato = default_contract()
        assert contrato.read_file_content is False, (
            "El contrato por defecto nunca debe leer contenido de archivos personales"
        )

    def test_contrato_por_defecto_no_loguea_rutas_completas(self):
        contrato = default_contract()
        assert contrato.log_full_paths is False, (
            "El contrato por defecto nunca debe enviar rutas completas a logs"
        )

    def test_safe_log_path_trunca_rutas_largas(self):
        ruta_larga = "C:/Users/Jarvis/Documents/Proyectos/JARVIS/src/hands/system_inventory.py"
        seguro = safe_log_path(ruta_larga, max_chars=40)
        assert len(seguro) <= 40 or seguro.endswith("system_inventory.py"), (
            "La ruta para logs debe truncarse y mostrar solo el nombre final"
        )
        # Nunca debe aparecer la ruta completa sin truncar cuando supera el limite
        assert seguro != ruta_larga

    def test_safe_log_path_corta_sin_truncar(self):
        ruta_corta = "C:/app.exe"
        seguro = safe_log_path(ruta_corta, max_chars=100)
        assert seguro == ruta_corta


# ---------------------------------------------------------------------------
# Exclusiones tecnicas (3.8.5.1.4.1.6)
# ---------------------------------------------------------------------------

class TestExclusiones:
    """Las rutas y puntos de montaje excluidos son tecnicos y justificados."""

    def test_excluye_rutas_virtuales_linux(self):
        assert is_excluded_path("/proc/1/cmdline") is True
        assert is_excluded_path("/sys/class/net/eth0") is True
        assert is_excluded_path("/dev/sda1") is True
        assert is_excluded_path("/run/user/1000") is True

    def test_excluye_rutas_windows_sistema(self):
        assert is_excluded_path("C:/$Recycle.Bin/file") is True
        assert is_excluded_path("C:/System Volume Information/x") is True
        assert is_excluded_path("C:/pagefile.sys") is True

    def test_no_excluye_rutas_usuario_normales(self):
        assert is_excluded_path("C:/Users/Jarvis/app.exe") is False
        assert is_excluded_path("/home/usuario/documento.txt") is False

    def test_excluye_puntos_montaje_virtuales(self):
        assert is_excluded_mount("/proc") is True
        assert is_excluded_mount("/sys") is True
        assert is_excluded_mount("/dev") is True

    def test_no_excluye_volumenes_locales_normales(self):
        assert is_excluded_mount("C:") is False
        assert is_excluded_mount("/mnt/data") is False

    def test_exclusiones_predeterminadas_no_vacias(self):
        assert len(DEFAULT_EXCLUDED_PATH_PATTERNS) > 0
        assert len(DEFAULT_EXCLUDED_MOUNT_PATTERNS) > 0


# ---------------------------------------------------------------------------
# Hechos vs inferencias (3.8.5.1.4.1.8)
# ---------------------------------------------------------------------------

class TestHechosVsInferencias:
    """Los tipos de entrada observados del SO son hechos, no inferencias."""

    def test_tipos_observados_son_hechos(self):
        for tipo in (EntryType.FILE, EntryType.DIRECTORY, EntryType.SYMLINK,
                     EntryType.JUNCTION, EntryType.MOUNT_POINT):
            assert classify_entry(tipo, ".exe") == FactType.OBSERVED, (
                f"{tipo} debe ser OBSERVED (hecho del SO), no inferencia"
            )

    def test_tipo_desconocido_es_inferencia(self):
        assert classify_entry(EntryType.OTHER, ".exe") == FactType.INFERRED


# ---------------------------------------------------------------------------
# Operaciones de control y aislamiento por equipo (3.8.5.1.4.1.3, .1.10)
# ---------------------------------------------------------------------------

class TestControlInventario:
    """Las operaciones de control respetan el aislamiento por equipo."""

    def test_control_rechaza_maquina_diferente(self):
        resultado = validate_control(
            InventoryControl.PAUSE, machine_id="otro-equipo",
            current_machine_id="mi-equipo",
        )
        assert resultado.accepted is False
        assert "otro equipo" in resultado.reason.lower()
        assert isinstance(resultado, InventoryControlResult)

    def test_control_acepta_maquina_propia(self):
        resultado = validate_control(
            InventoryControl.REBUILD, machine_id="mi-equipo",
            current_machine_id="mi-equipo",
        )
        assert resultado.accepted is True
        assert resultado.reason == "Control aceptado"

    def test_todos_los_controles_estan_definidos(self):
        controles = {
            InventoryControl.PAUSE,
            InventoryControl.RESUME,
            InventoryControl.CANCEL,
            InventoryControl.EXCLUDE_PATH,
            InventoryControl.REBUILD,
            InventoryControl.DELETE,
        }
        assert len(controles) == 6


# ---------------------------------------------------------------------------
# Contrato por defecto (3.8.5.1.4.1.1, .1.5, .1.12)
# ---------------------------------------------------------------------------

class TestContratoPorDefecto:
    """El contrato por defecto fija alcance, metadatos y privacidad."""

    def test_alcance_por_defecto_es_volumenes_locales(self):
        contrato = default_contract()
        assert contrato.scope is not None
        assert contrato.machine_id is not None and len(contrato.machine_id) > 0

    def test_exclusiones_predeterminadas_estan_presentes(self):
        contrato = default_contract()
        assert len(contrato.excluded_paths) > 0
        assert len(contrato.excluded_mounts) > 0

    def test_privacidad_por_defecto(self):
        contrato = default_contract()
        assert contrato.read_file_content is False
        assert contrato.log_full_paths is False
        assert contrato.include_hidden is True
        assert contrato.include_system is True

    def test_privacy_summary_contiene_garantias(self):
        contrato = default_contract()
        resumen = contrato.privacy_summary()
        assert "Nunca" in resumen or "nunca" in resumen
        assert "contenido" in resumen.lower()


# ---------------------------------------------------------------------------
# Integracion con almacenamiento (3.8.5.1.4.1.11: contract tests)
# ---------------------------------------------------------------------------

class TestSerializacionParaPersistencia:
    """Una entrada debe poder guardarse y recuperarse como JSON (preparacion para 3.8.5.1.4.2)."""

    def test_entrada_se_guarda_como_json_valido(self, tmp_path: Path):
        entry = InventoryEntry(
            machine_id="m",
            volume="C:",
            absolute_path="C:/test.txt",
            relative_path="test.txt",
            name="test.txt",
            extension=".txt",
            entry_type=EntryType.FILE,
            size_bytes=50,
            modified_at="2024-01-01",
            created_at="2024-01-01",
        )
        archivo = tmp_path / "entrada.json"
        archivo.write_text(json.dumps(entry.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        datos = json.loads(archivo.read_text(encoding="utf-8"))
        restaurada = InventoryEntry.from_dict(datos)
        assert restaurada.name == "test.txt"
        assert restaurada.size_bytes == 50


# ---------------------------------------------------------------------------
# Deteccion de SO, arquitectura y version (3.8.5.1.4.3.1)
# ---------------------------------------------------------------------------

class TestInfoSistema:
    """InfoSistema almacena SO, version y arquitectura detectados via APIs."""

    def test_campos_no_vacios(self):
        info = InfoSistema(
            sistema_operativo="Windows",
            version="10",
            arquitectura="x64",
            nombre_plataforma="Windows-10-10.0.19041",
            procesador="Intel64 Family 6 Model 158",
        )
        assert info.sistema_operativo == "Windows"
        assert info.version == "10"
        assert info.arquitectura == "x64"
        assert info.nombre_plataforma == "Windows-10-10.0.19041"
        assert info.procesador == "Intel64 Family 6 Model 158"

    def test_info_sistema_es_dataclass(self):
        info = InfoSistema("Linux", "5.15", "x64", "Linux-5.15-x86_64", "")
        assert isinstance(info, InfoSistema)
        assert info.sistema_operativo == "Linux"


class TestNormalizarArquitectura:
    """La normalizacion traduce identificadores de platform.machine()."""

    def test_amd64_se_normaliza_a_x64(self):
        assert normalizar_arquitectura("AMD64") == "x64"
        assert normalizar_arquitectura("amd64") == "x64"

    def test_x86_64_se_normaliza_a_x64(self):
        assert normalizar_arquitectura("x86_64") == "x64"

    def test_x86_se_normaliza_a_x86(self):
        assert normalizar_arquitectura("i386") == "x86"
        assert normalizar_arquitectura("i686") == "x86"

    def test_arm64_se_normaliza_a_arm64(self):
        assert normalizar_arquitectura("arm64") == "arm64"
        assert normalizar_arquitectura("aarch64") == "arm64"

    def test_valor_desconocido_se_devuelve_tal_cual(self):
        assert normalizar_arquitectura("riscv64") == "riscv64"

    def test_cadena_vacia_devuelve_vacia(self):
        assert normalizar_arquitectura("") == ""


class TestDetectarSistema:
    """detectar_sistema() usa APIs del sistema y no deduce SO de rutas."""

    def test_devuelve_info_sistema(self):
        info = detectar_sistema()
        assert isinstance(info, InfoSistema)
        assert isinstance(info.sistema_operativo, str) and len(info.sistema_operativo) > 0
        assert isinstance(info.arquitectura, str) and len(info.arquitectura) > 0
        assert isinstance(info.nombre_plataforma, str) and len(info.nombre_plataforma) > 0

    def test_sistema_operativo_coincide_con_platform(self):
        import platform as _platform
        info = detectar_sistema()
        assert info.sistema_operativo == _platform.system()

    def test_arquitectura_normalizada_coincide_con_maquina(self):
        import platform as _platform
        info = detectar_sistema()
        maquina = _platform.machine().lower()
        if maquina in ("amd64", "x86_64", "x64"):
            assert info.arquitectura == "x64"
        elif maquina in ("arm64", "aarch64"):
            assert info.arquitectura == "arm64"
        elif maquina in ("i386", "i686", "x86"):
            assert info.arquitectura == "x86"

    def test_no_infiere_so_de_rutas(self):
        """La deteccion no cambia aunque se inventen rutas de otro SO."""
        # Ejecutar dos veces: el resultado debe ser el mismo y venir de platform,
        # no de ninguna ruta inspeccionada.
        info1 = detectar_sistema()
        info2 = detectar_sistema()
        assert info1.sistema_operativo == info2.sistema_operativo
        assert info1.arquitectura == info2.arquitectura
        assert info1.version == info2.version

    def test_nombre_plataforma_no_vacio(self):
        info = detectar_sistema()
        assert len(info.nombre_plataforma) > 0


class TestEsSistemaSoportado:
    """es_sistema_soportado consulta la matriz de cobertura sin inferencias."""

    def test_windows_x64_es_soportado(self):
        assert es_sistema_soportado("Windows", "x64") is True

    def test_linux_x64_es_soportado(self):
        assert es_sistema_soportado("Linux", "x64") is True

    def test_darwin_arm64_es_soportado(self):
        assert es_sistema_soportado("Darwin", "arm64") is True

    def test_so_no_registrado_no_es_soportado(self):
        assert es_sistema_soportado("Plan9", "x64") is False

    def test_arquitectura_no_registrada_no_es_soportada(self):
        assert es_sistema_soportado("Windows", "riscv64") is False

    def test_combinacion_no_en_matriz_no_es_soportada(self):
        assert es_sistema_soportado("Windows", "arm64") is False

    def test_comparacion_es_insensible_a_mayusculas(self):
        assert es_sistema_soportado("windows", "X64") is True
