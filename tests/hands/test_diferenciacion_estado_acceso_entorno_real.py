# -*- coding: utf-8 -*-
"""
Verificacion en el entorno real (Windows) de
SystemInventoryStorage.diferenciar_estado_acceso (3.8.5.1.4.6.4).

Usa archivos y carpetas temporales REALES en un volumen montado del
equipo, el identificador real de equipo (generate_machine_id), la
validacion real contra el sistema operativo (validar_destino) y el
preflight real (ApplicationPreflight.check). No usa mocks que decidan
los flags; cada valor se compara contra el estado observable del SO.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from src.hands.system_inventory import EntryType, generate_machine_id
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SystemInventoryStorage,
)
from src.hands.application_preflight import get_application_preflight

MACHINE_ID = generate_machine_id()


def _crear_entradas_reales(
    storage: SystemInventoryStorage, tmp_path: Path
) -> dict[str, Path]:
    """Crea entradas sobre objetos reales del volumen actual."""
    storage.initialize()
    storage.record_machine(MACHINE_ID)
    storage.begin_scan_run("scan-real", MACHINE_ID, "C:", SCAN_MODE_FULL)

    carpeta = tmp_path / "jarvis_real_diferenciacion"
    carpeta.mkdir()

    ejecutable_real = carpeta / "app_real.exe"
    ejecutable_real.write_bytes(b"MZplaceholder")

    documento_real = carpeta / "documento_real.txt"
    documento_real.write_text("contenido real", encoding="utf-8")

    carpeta_real = carpeta / "subcarpeta_real"
    carpeta_real.mkdir()

    inexistente = carpeta / "no_existe" / "fantasma.exe"

    # Aplicacion real del sistema si se localiza en el equipo.
    app_sistema = shutil.which("notepad") or shutil.which("cmd")

    volumen = os.path.splitdrive(str(ejecutable_real))[0] or "C:"

    entradas = [
        {
            "entry_id": "e-real-exe",
            "absolute_path": str(ejecutable_real),
            "relative_path": "jarvis_real_diferenciacion/app_real.exe",
            "name": ejecutable_real.name,
            "extension": ".exe",
            "entry_type": EntryType.FILE.value,
            "size_bytes": ejecutable_real.stat().st_size,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        },
        {
            "entry_id": "e-real-txt",
            "absolute_path": str(documento_real),
            "relative_path": "jarvis_real_diferenciacion/documento_real.txt",
            "name": documento_real.name,
            "extension": ".txt",
            "entry_type": EntryType.FILE.value,
            "size_bytes": documento_real.stat().st_size,
            "modified_at": "2024-03-01T10:00:00",
            "created_at": "2024-03-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-03-05T00:00:00",
        },
        {
            "entry_id": "e-real-dir",
            "absolute_path": str(carpeta_real),
            "relative_path": "jarvis_real_diferenciacion/subcarpeta_real",
            "name": carpeta_real.name,
            "extension": "",
            "entry_type": EntryType.DIRECTORY.value,
            "size_bytes": 0,
            "modified_at": "2024-02-01T10:00:00",
            "created_at": "2024-02-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-02-03T00:00:00",
        },
        {
            "entry_id": "e-real-inexistente",
            "absolute_path": str(inexistente),
            "relative_path": "jarvis_real_diferenciacion/no_existe/fantasma.exe",
            "name": "fantasma.exe",
            "extension": ".exe",
            "entry_type": EntryType.FILE.value,
            "size_bytes": 0,
            "modified_at": "",
            "created_at": "",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-04-01T00:00:00",
        },
    ]
    if app_sistema:
        entradas.append(
            {
                "entry_id": "e-real-sistema",
                "absolute_path": str(app_sistema),
                "relative_path": str(app_sistema),
                "name": Path(app_sistema).name,
                "extension": os.path.splitext(str(app_sistema))[1],
                "entry_type": EntryType.FILE.value,
                "size_bytes": os.path.getsize(app_sistema),
                "modified_at": "",
                "created_at": "",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            }
        )

    storage.insert_file_entries("scan-real", MACHINE_ID, volumen, entradas)
    storage.end_scan_run("scan-real", entries_count=len(entradas))
    return Path(app_sistema) if app_sistema else None


def test_diferenciacion_estado_acceso_entorno_real():
    """Ejecucion real sobre el sistema operativo: archivos temporales
    reales, machine_id real, validacion real y preflight real."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        storage = SystemInventoryStorage(tmp_path / "inventario_real.sqlite3")
        app_sistema = _crear_entradas_reales(storage, tmp_path)

        pagina = storage.diferenciar_estado_acceso(
            MACHINE_ID, machine_id_actual=MACHINE_ID
        )

        por_id = {e["entry_id"]: e for e in pagina["results"]}

        ids_esperados = {
            "e-real-exe",
            "e-real-txt",
            "e-real-dir",
            "e-real-inexistente",
        }
        if app_sistema:
            ids_esperados.add("e-real-sistema")
        assert set(por_id.keys()) == ids_esperados

        # .exe real existente: existe, accesible, ejecutable y candidato.
        dif_exe = por_id["e-real-exe"]["diferenciacion"]
        assert dif_exe["encontrado_en_inventario"] is True
        assert dif_exe["existe_ahora"] is True
        assert dif_exe["accesible_ahora"] is True
        assert dif_exe["ejecutable"] is True
        assert dif_exe["candidato_a_aplicacion"] is True
        assert isinstance(dif_exe["autorizado_para_lanzamiento"], bool)
        assert isinstance(dif_exe["preflight_permitido"], bool)
        assert isinstance(dif_exe["preflight_motivo"], str)
        assert isinstance(dif_exe["detalle"], str) and dif_exe["detalle"]

        # .txt real: no ejecutable, no candidato.
        dif_txt = por_id["e-real-txt"]["diferenciacion"]
        assert dif_txt["existe_ahora"] is True
        assert dif_txt["accesible_ahora"] is True
        assert dif_txt["ejecutable"] is False
        assert dif_txt["candidato_a_aplicacion"] is False
        assert dif_txt["autorizado_para_lanzamiento"] is False
        assert dif_txt["preflight_permitido"] is None

        # Carpeta real: no ejecutable, no candidato.
        dif_dir = por_id["e-real-dir"]["diferenciacion"]
        assert dif_dir["existe_ahora"] is True
        assert dif_dir["accesible_ahora"] is True
        assert dif_dir["ejecutable"] is False
        assert dif_dir["candidato_a_aplicacion"] is False
        assert dif_dir["autorizado_para_lanzamiento"] is False
        assert dif_dir["preflight_permitido"] is None

        # Ruta inexistente: no existe, no accesible, no candidato.
        dif_inex = por_id["e-real-inexistente"]["diferenciacion"]
        assert dif_inex["existe_ahora"] is False
        assert dif_inex["accesible_ahora"] is False
        assert dif_inex["ejecutable"] is True  # tipo/extension, independiente de existe_ahora
        assert dif_inex["candidato_a_aplicacion"] is False
        assert dif_inex["autorizado_para_lanzamiento"] is False

        # Aplicacion real del sistema, si se localizo: candidato y
        # autorizado segun decision real del preflight (valor observado,
        # sin suponer True ni False).
        if app_sistema:
            dif_sis = por_id["e-real-sistema"]["diferenciacion"]
            assert dif_sis["existe_ahora"] is True
            assert dif_sis["accesible_ahora"] is True
            assert dif_sis["ejecutable"] is True
            assert dif_sis["candidato_a_aplicacion"] is True
            assert isinstance(dif_sis["autorizado_para_lanzamiento"], bool)
            assert isinstance(dif_sis["preflight_permitido"], bool)

        print("DIFERENCIACION ENTORNO REAL (3.8.5.1.4.6.4):")
        for entry_id in sorted(por_id):
            print(entry_id, "->", por_id[entry_id]["diferenciacion"])

        # Preflight real directo sobre la aplicacion localizada (registro de evidencia).
        if app_sistema:
            preflight = get_application_preflight()
            resultado = preflight.check(
                {
                    "name": app_sistema.name,
                    "app_id": str(app_sistema),
                    "login_required": None,
                    "logged_in": None,
                    "resources_available": True,
                }
            )
            assert isinstance(resultado["allowed"], bool)
            assert isinstance(resultado["reason"], str)
            print("PREFLIGHT REAL:", resultado)

        # Preflight real sobre aplicacion inexistente: debe denegar.
        preflight = get_application_preflight()
        resultado_inexistente = preflight.check(
            {
                "name": "aplicacion-que-no-existe-en-nunca.exe",
                "app_id": str(tmp_path / "no-existe.exe"),
                "login_required": None,
                "logged_in": None,
                "resources_available": True,
            }
        )
        assert resultado_inexistente["allowed"] is False
        print("PREFLIGHT REAL INEXISTENTE:", resultado_inexistente)

        # Liberar la conexion SQLite para que el directorio temporal pueda
        # eliminarse al salir del contexto (Windows bloquea el fichero
        # mientras la conexion WAL esta abierta).
        storage.close()
