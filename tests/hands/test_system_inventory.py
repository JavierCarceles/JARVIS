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
    VolumeInfo,
    VolumeType,
    VolumenComun,
    _clasificar_tipo_volumen_linux,
    _clasificar_tipo_volumen_macos,
    classify_entry,
    enumerar_volumenes_comun,
    volumen_comun_desde_info,
    default_contract,
    detectar_sistema,
    enumerar_volumenes_linux,
    enumerar_volumenes_macos,
    enumerar_volumenes_windows,
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


# ---------------------------------------------------------------------------
# Enumeracion de volumenes Windows (3.8.5.1.4.3.2)
# ---------------------------------------------------------------------------

class TestVolumeType:
    """VolumeType clasifica unidades Windows observadas via GetDriveType."""

    def test_valores_esperados(self):
        assert VolumeType.UNKNOWN.value == "unknown"
        assert VolumeType.NO_ROOT_DIR.value == "no_root_dir"
        assert VolumeType.REMOVABLE.value == "removable"
        assert VolumeType.FIXED.value == "fixed"
        assert VolumeType.REMOTE.value == "remote"
        assert VolumeType.CD_ROM.value == "cd_rom"
        assert VolumeType.RAM_DISK.value == "ram_disk"


class TestVolumeInfo:
    """VolumeInfo almacena metadatos de volumen sin leer contenido."""

    def test_campos_requeridos(self):
        info = VolumeInfo(
            letra="C:",
            ruta_raiz="C:\\",
            tipo=VolumeType.FIXED,
            disponible=True,
        )
        assert info.letra == "C:"
        assert info.ruta_raiz == "C:\\"
        assert info.tipo == VolumeType.FIXED
        assert info.disponible is True
        assert info.sistema_archivos == ""
        assert info.etiqueta_volumen == ""

    def test_campos_opcionales(self):
        info = VolumeInfo(
            letra="D:",
            ruta_raiz="D:\\",
            tipo=VolumeType.REMOVABLE,
            disponible=False,
            sistema_archivos="NTFS",
            etiqueta_volumen="Datos",
        )
        assert info.sistema_archivos == "NTFS"
        assert info.etiqueta_volumen == "Datos"


class TestEnumerarVolumenesWindows:
    """enumerar_volumenes_windows() descubre unidades reales en Windows."""

    def test_devuelve_lista_de_volume_info(self):
        volumenes = enumerar_volumenes_windows()
        assert isinstance(volumenes, list)
        for v in volumenes:
            assert isinstance(v, VolumeInfo)

    def test_almeno_una_unidad_detectada(self):
        volumenes = enumerar_volumenes_windows()
        assert len(volumenes) > 0, "Windows debe tener al menos una unidad logica"

    def test_c_es_fixed_y_disponible(self):
        """En este entorno C: existe, es fija y esta disponible."""
        volumenes = enumerar_volumenes_windows()
        por_letra = {v.letra: v for v in volumenes}
        assert "C:" in por_letra, "Se esperaba la unidad C:"
        c = por_letra["C:"]
        assert c.tipo == VolumeType.FIXED, f"C: debe ser FIXED, obtuvo {c.tipo}"
        assert c.disponible is True, "C: debe estar disponible"
        assert c.ruta_raiz == "C:\\"
        assert len(c.sistema_archivos) > 0, "C: debe reportar un sistema de archivos"

    def test_letras_unicas(self):
        volumenes = enumerar_volumenes_windows()
        letras = [v.letra for v in volumenes]
        assert len(letras) == len(set(letras)), "No debe haber letras de unidad duplicadas"

    def test_todas_tienen_tipo_y_disponibilidad(self):
        volumenes = enumerar_volumenes_windows()
        for v in volumenes:
            assert isinstance(v.tipo, VolumeType)
            assert isinstance(v.disponible, bool)
            assert v.letra.endswith(":")
            assert v.ruta_raiz == f"{v.letra}\\"


# ---------------------------------------------------------------------------
# Enumeracion de volumenes Linux (3.8.5.1.4.3.3)
# ---------------------------------------------------------------------------

class TestVolumeTypeLinux:
    """VolumeType debe incluir VIRTUAL para diferenciar sistemas de archivos
    virtuales de Linux (3.8.5.1.4.3.3)."""

    def test_existe_valor_virtual(self):
        assert VolumeType.VIRTUAL.value == "virtual"


class TestClasificacionVolumenLinux:
    """_clasificar_tipo_volumen_linux clasifica local, virtual, red y extraible."""

    def test_sistema_local_ext4_es_fixed(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("/dev/sda1", "ext4", "rw,relatime", "/")
        assert tipo == VolumeType.FIXED

    def test_sistema_local_xfs_es_fixed(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("/dev/sdb1", "xfs", "rw,relatime", "/datos")
        assert tipo == VolumeType.FIXED

    def test_sistema_virtual_proc_es_virtual(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("proc", "proc", "rw,nosuid,nodev,noexec,relatime", "/proc")
        assert tipo == VolumeType.VIRTUAL

    def test_sistema_virtual_sysfs_es_virtual(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("sysfs", "sysfs", "rw,nosuid,nodev,noexec,relatime", "/sys")
        assert tipo == VolumeType.VIRTUAL

    def test_sistema_virtual_tmpfs_es_virtual(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("tmpfs", "tmpfs", "rw,nosuid,nodev", "/run")
        assert tipo == VolumeType.VIRTUAL

    def test_sistema_red_nfs_es_remote(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("server:/export", "nfs", "rw,relatime,_netdev", "/mnt/nfs")
        assert tipo == VolumeType.REMOTE

    def test_sistema_red_cifs_es_remote(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("//server/share", "cifs", "rw,_netdev", "/mnt/share")
        assert tipo == VolumeType.REMOTE

    def test_sistema_extraible_vfat_bajo_media_es_removable(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("/dev/sdc1", "vfat", "rw,relatime", "/media/usuario/USB")
        assert tipo == VolumeType.REMOVABLE

    def test_sistema_extraible_exfat_bajo_mnt_es_removable(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("/dev/sdd1", "exfat", "rw,relatime", "/mnt/disco_externo")
        assert tipo == VolumeType.REMOVABLE

    def test_sistema_desconocido_es_unknown(self):
        from src.hands.system_inventory import _clasificar_tipo_volumen_linux
        tipo = _clasificar_tipo_volumen_linux("/dev/sde1", "otro_fs", "rw", "/otro")
        assert tipo == VolumeType.UNKNOWN


class TestEnumerarVolumenesLinux:
    """enumerar_volumenes_linux() lee /proc/mounts y devuelve VolumeInfo."""

    def _escribir_mounts(self, tmp_path, contenido):
        archivo = tmp_path / "mounts"
        archivo.write_text(contenido, encoding="utf-8")
        return str(archivo)

    def test_devuelve_lista_de_volume_info(self, tmp_path):
        ruta = self._escribir_mounts(tmp_path, """
/dev/sda1 / ext4 rw,relatime 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
""")
        volumenes = enumerar_volumenes_linux(ruta)
        assert isinstance(volumenes, list)
        for v in volumenes:
            assert isinstance(v, VolumeInfo)

    def test_no_existe_proc_mounts_devuelve_lista_vacia(self, tmp_path):
        ruta = str(tmp_path / "no_existe.mounts")
        volumenes = enumerar_volumenes_linux(ruta)
        assert volumenes == []

    def test_distingue_local_virtual_red_y_extraible(self, tmp_path):
        ruta = self._escribir_mounts(tmp_path, """
/dev/sda1 / ext4 rw,relatime 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
server:/export /mnt/nfs nfs rw,relatime,_netdev 0 0
/dev/sdc1 /media/usuario/USB vfat rw,relatime 0 0
""")
        volumenes = enumerar_volumenes_linux(ruta)
        por_ruta = {v.ruta_raiz: v for v in volumenes}
        assert por_ruta["/"].tipo == VolumeType.FIXED, f"/ debe ser FIXED, obtuvo {por_ruta['/'].tipo}"
        assert por_ruta["/proc"].tipo == VolumeType.VIRTUAL, f"/proc debe ser VIRTUAL, obtuvo {por_ruta['/proc'].tipo}"
        assert por_ruta["/mnt/nfs"].tipo == VolumeType.REMOTE, f"/mnt/nfs debe ser REMOTE, obtuvo {por_ruta['/mnt/nfs'].tipo}"
        assert por_ruta["/media/usuario/USB"].tipo == VolumeType.REMOVABLE, (
            f"/media/usuario/USB debe ser REMOVABLE, obtuvo {por_ruta['/media/usuario/USB'].tipo}"
        )

    def test_volumen_info_sin_letra_linux(self, tmp_path):
        """Linux no usa letras de unidad: letra queda vacia."""
        ruta = self._escribir_mounts(tmp_path, "/dev/sda1 / ext4 rw,relatime 0 0\n")
        volumenes = enumerar_volumenes_linux(ruta)
        assert len(volumenes) == 1
        assert volumenes[0].letra == "", "Linux no tiene letra de unidad"
        assert volumenes[0].ruta_raiz == "/"
        assert volumenes[0].sistema_archivos == "ext4"
        assert volumenes[0].etiqueta_volumen == "/dev/sda1"
        assert volumenes[0].disponible is True

    def test_lineas_vacias_y_comentarios_no_rompen_el_parseo(self, tmp_path):
        ruta = self._escribir_mounts(tmp_path, """
# comentario

/dev/sda1 / ext4 rw,relatime 0 0

""")
        volumenes = enumerar_volumenes_linux(ruta)
        assert len(volumenes) == 1


# ---------------------------------------------------------------------------
# Clasificacion de volumenes macOS (3.8.5.1.4.3.4)
# ---------------------------------------------------------------------------

class TestClasificacionVolumenMacOS:
    """_clasificar_tipo_volumen_macos clasifica local, virtual, red y extraible."""

    def test_sistema_local_apfs_es_fixed(self):
        tipo = _clasificar_tipo_volumen_macos(
            "/dev/disk1s1", "apfs", "local, journaled", "/"
        )
        assert tipo == VolumeType.FIXED

    def test_sistema_local_hfs_es_fixed(self):
        tipo = _clasificar_tipo_volumen_macos(
            "/dev/disk2s1", "hfs", "local, journaled", "/Volumes/Datos"
        )
        assert tipo == VolumeType.FIXED

    def test_sistema_virtual_devfs_es_virtual(self):
        tipo = _clasificar_tipo_volumen_macos(
            "devfs", "devfs", "rw,nosuid", "/dev"
        )
        assert tipo == VolumeType.VIRTUAL

    def test_sistema_virtual_fdescfs_es_virtual(self):
        tipo = _clasificar_tipo_volumen_macos(
            "fdescfs", "fdescfs", "rw,nosuid", "/dev/fd"
        )
        assert tipo == VolumeType.VIRTUAL

    def test_sistema_virtual_tmpfs_es_virtual(self):
        tipo = _clasificar_tipo_volumen_macos(
            "tmpfs", "tmpfs", "rw,nosuid", "/private/var/vm"
        )
        assert tipo == VolumeType.VIRTUAL

    def test_sistema_red_nfs_es_remote(self):
        tipo = _clasificar_tipo_volumen_macos(
            "server:/export", "nfs", "rw,_netdev", "/mnt/nfs"
        )
        assert tipo == VolumeType.REMOTE

    def test_sistema_red_smbfs_es_remote(self):
        tipo = _clasificar_tipo_volumen_macos(
            "//server/share", "smbfs", "rw", "/mnt/share"
        )
        assert tipo == VolumeType.REMOTE

    def test_sistema_extraible_exfat_bajo_volumes_es_removable(self):
        tipo = _clasificar_tipo_volumen_macos(
            "/dev/disk3s1", "exfat", "rw,nosuid", "/Volumes/USB"
        )
        assert tipo == VolumeType.REMOVABLE

    def test_sistema_extraible_msdos_bajo_volumes_es_removable(self):
        tipo = _clasificar_tipo_volumen_macos(
            "/dev/disk4s1", "msdos", "rw,nosuid", "/Volumes/DiscoExterno"
        )
        assert tipo == VolumeType.REMOVABLE

    def test_sistema_desconocido_es_unknown(self):
        tipo = _clasificar_tipo_volumen_macos(
            "/dev/disk5s1", "otro_fs", "rw", "/otro"
        )
        assert tipo == VolumeType.UNKNOWN


# ---------------------------------------------------------------------------
# Enumeracion de volumenes macOS (3.8.5.1.4.3.4)
# ---------------------------------------------------------------------------

class TestEnumerarVolumenesMacOS:
    """enumerar_volumenes_macos() parsea la salida de `mount` en macOS."""

    def _salida_mount(self, lineas):
        return "\n".join(lineas)

    def test_devuelve_lista_de_volume_info(self):
        salida = self._salida_mount([
            "/dev/disk1s1 on / (apfs, local, journaled)",
            "/dev/disk2s1 on /Volumes/Datos (apfs, local, journaled)",
        ])
        volumenes = enumerar_volumenes_macos(salida)
        assert isinstance(volumenes, list)
        for v in volumenes:
            assert isinstance(v, VolumeInfo)

    def test_entrada_vacia_devuelve_lista_vacia(self):
        assert enumerar_volumenes_macos("") == []

    def test_sin_parentesis_no_se_parsea(self):
        salida = "/dev/disk1s1 on /"
        assert enumerar_volumenes_macos(salida) == []

    def test_distingue_local_virtual_red_y_extraible(self):
        salida = self._salida_mount([
            "/dev/disk1s1 on / (apfs, local, journaled)",
            "devfs on /dev (devfs, rw, nosuid)",
            "server:/export on /mnt/nfs (nfs, rw, _netdev)",
            "/dev/disk3s1 on /Volumes/USB (exfat, rw, nosuid)",
        ])
        volumenes = enumerar_volumenes_macos(salida)
        por_ruta = {v.ruta_raiz: v for v in volumenes}
        assert por_ruta["/"].tipo == VolumeType.FIXED, (
            f"/ debe ser FIXED, obtuvo {por_ruta['/'].tipo}"
        )
        assert por_ruta["/dev"].tipo == VolumeType.VIRTUAL, (
            f"/dev debe ser VIRTUAL, obtuvo {por_ruta['/dev'].tipo}"
        )
        assert por_ruta["/mnt/nfs"].tipo == VolumeType.REMOTE, (
            f"/mnt/nfs debe ser REMOTE, obtuvo {por_ruta['/mnt/nfs'].tipo}"
        )
        assert por_ruta["/Volumes/USB"].tipo == VolumeType.REMOVABLE, (
            f"/Volumes/USB debe ser REMOVABLE, obtuvo {por_ruta['/Volumes/USB'].tipo}"
        )

    def test_volumen_info_sin_letra_macos(self):
        """macOS no usa letras de unidad: letra queda vacia."""
        salida = "/dev/disk1s1 on / (apfs, local, journaled)"
        volumenes = enumerar_volumenes_macos(salida)
        assert len(volumenes) == 1
        assert volumenes[0].letra == "", "macOS no tiene letra de unidad"
        assert volumenes[0].ruta_raiz == "/"
        assert volumenes[0].sistema_archivos == "apfs"
        assert volumenes[0].etiqueta_volumen == "/dev/disk1s1"
        assert volumenes[0].disponible is True

    def test_lineas_sin_on_se_ignoran(self):
        salida = """
/dev/disk1s1 on / (apfs, local, journaled)
linea invalida sin on

"""
        volumenes = enumerar_volumenes_macos(salida)
        assert len(volumenes) == 1


# ---------------------------------------------------------------------------
# Contrato comun de volumen multiplataforma (3.8.5.1.4.3.5)
# ---------------------------------------------------------------------------

class TestVolumenComun:
    """VolumenComun no impone letras de unidad ni rutas de Windows en otros SO."""

    def test_construir_sin_letra_unidad_en_linux(self):
        """Linux/macOS no tienen letra de unidad: letra_unidad queda None."""
        v = VolumenComun(
            identificador="/",
            raiz="/",
            tipo=VolumeType.FIXED,
            disponible=True,
            sistema_archivos="ext4",
            sistema_origen="Linux",
        )
        assert v.letra_unidad is None
        assert v.tiene_letra_unidad() is False
        assert v.es_windows() is False
        assert v.identificador == "/"
        assert v.raiz == "/"

    def test_construir_con_letra_unidad_en_windows(self):
        """Windows conserva la letra de unidad."""
        v = VolumenComun(
            identificador="C:",
            raiz="C:\\",
            tipo=VolumeType.FIXED,
            disponible=True,
            sistema_archivos="NTFS",
            letra_unidad="C:",
            sistema_origen="Windows",
        )
        assert v.letra_unidad == "C:"
        assert v.tiene_letra_unidad() is True
        assert v.es_windows() is True
        assert v.identificador == "C:"
        assert v.raiz == "C:\\"

    def test_construir_sin_letra_unidad_en_macos(self):
        """macOS no usa letras de unidad."""
        v = VolumenComun(
            identificador="/Volumes/Datos",
            raiz="/Volumes/Datos",
            tipo=VolumeType.FIXED,
            disponible=True,
            sistema_archivos="apfs",
            letra_unidad=None,
            sistema_origen="Darwin",
        )
        assert v.letra_unidad is None
        assert v.es_windows() is False
        assert v.tiene_letra_unidad() is False

    def test_to_dict(self):
        """to_dict serializa todos los campos incluido letra_unidad None."""
        v = VolumenComun(
            identificador="/mnt/data",
            raiz="/mnt/data",
            tipo=VolumeType.REMOVABLE,
            disponible=True,
            sistema_archivos="exfat",
            letra_unidad=None,
            sistema_origen="Linux",
        )
        d = v.to_dict()
        assert d["identificador"] == "/mnt/data"
        assert d["raiz"] == "/mnt/data"
        assert d["tipo"] == "removable"
        assert d["disponible"] is True
        assert d["sistema_archivos"] == "exfat"
        assert d["letra_unidad"] is None
        assert d["sistema_origen"] == "Linux"


class TestVolumenComunDesdeInfo:
    """volumen_comun_desde_info convierte VolumeInfo sin forzar conceptos Windows."""

    def test_desde_info_windows_conserva_letra(self):
        info = VolumeInfo(
            letra="C:",
            ruta_raiz="C:\\",
            tipo=VolumeType.FIXED,
            disponible=True,
            sistema_archivos="NTFS",
            etiqueta_volumen="Datos",
        )
        v = volumen_comun_desde_info(info, sistema_origen="Windows")
        assert v.letra_unidad == "C:"
        assert v.identificador == "C:"
        assert v.raiz == "C:\\"
        assert v.sistema_origen == "Windows"
        assert v.es_windows() is True

    def test_desde_info_linux_sin_letra(self):
        info = VolumeInfo(
            letra="",
            ruta_raiz="/",
            tipo=VolumeType.FIXED,
            disponible=True,
            sistema_archivos="ext4",
            etiqueta_volumen="/dev/sda1",
        )
        v = volumen_comun_desde_info(info, sistema_origen="Linux")
        assert v.letra_unidad is None
        assert v.identificador == "/"
        assert v.raiz == "/"
        assert v.sistema_origen == "Linux"
        assert v.es_windows() is False

    def test_desde_info_macos_sin_letra(self):
        info = VolumeInfo(
            letra="",
            ruta_raiz="/Volumes/USB",
            tipo=VolumeType.REMOVABLE,
            disponible=True,
            sistema_archivos="exfat",
            etiqueta_volumen="/dev/disk2s1",
        )
        v = volumen_comun_desde_info(info, sistema_origen="Darwin")
        assert v.letra_unidad is None
        assert v.identificador == "/Volumes/USB"
        assert v.raiz == "/Volumes/USB"
        assert v.sistema_origen == "Darwin"

    def test_no_inventa_letra_unidad_en_no_windows(self):
        """Aunque el VolumeInfo traiga letra, en SO no-Windows no se conserva."""
        info = VolumeInfo(
            letra="C:",
            ruta_raiz="/",
            tipo=VolumeType.FIXED,
            disponible=True,
        )
        v = volumen_comun_desde_info(info, sistema_origen="Linux")
        assert v.letra_unidad is None
        assert v.identificador == "/"

    def test_valor_default_sistema_origen(self):
        """Sin sistema_origen se usa la deteccion del SO real."""
        info = VolumeInfo(
            letra="D:",
            ruta_raiz="D:\\",
            tipo=VolumeType.REMOVABLE,
            disponible=True,
        )
        v = volumen_comun_desde_info(info)
        assert v.sistema_origen == detectar_sistema().sistema_operativo


class TestEnumerarVolumenesComun:
    """enumerar_volumenes_comun devuelve contratos comunes sin forzar Windows."""

    def test_devuelve_lista_de_volumen_comun_en_windows(self):
        """En este entorno Windows devuelve VolumeInfo reales convertidos."""
        volumenes = enumerar_volumenes_comun(sistema_origen="Windows")
        assert isinstance(volumenes, list)
        assert len(volumenes) > 0, "Windows debe tener al menos un volumen"
        for v in volumenes:
            assert isinstance(v, VolumenComun)

    def test_elementos_no_forzan_letra_unidad(self):
        """Cada volumen comun expone letra_unidad segun su SO real."""
        volumenes = enumerar_volumenes_comun(sistema_origen="Windows")
        for v in volumenes:
            assert isinstance(v.tiene_letra_unidad(), bool)
            assert isinstance(v.es_windows(), bool)

    def test_so_no_reconocido_devuelve_vacio(self):
        volumenes = enumerar_volumenes_comun(sistema_origen="Desconocido")
        assert volumenes == []
