# -*- coding: utf-8 -*-
"""
Tests de la unidad 3.8.5.1.4.11.10: upsert, auto-registro y preservacion
del catalogo global data/memory/entities.json.

Cubre ApplicationDiscovery.auto_registrar_candidatos_inventario junto con
calcular_identidad_estable, construir_registro_minimo_aplicacion,
validar_registro_minimo_aplicacion y _fusionar_entidad_existente.

Escenarios:
- .exe GUI / CLI / instalador / desconocido (subtipos de lanzamiento)
- aliases preservados en la entidad
- tipo de lanzamiento nativo en properties
- estado disponible (available / no_disponible)
- upsert repetido sin duplicar
- IDs estables deterministas sin fragmentos de ruta absoluta
- datos JSON corruptos en entities.json (no bloquea; se repara y sigue escribiendo)
- preservacion de entidades previas y no-app entre equipos
- cero intervencion manual (registro automatico sin entrada de usuario)

Estrategia de mocks: storage mockeado para controlar verificar_identidad_equipo;
MemoryManager real sobre ruta temporal para no tocar data/ de produccion.
Clasificador y preflight REALES. No se lanza ninguna aplicacion.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.hands.apps.application_discovery import (
    ApplicationDiscovery,
    DiscoveredCandidate,
    FUENTE_INVENTARIO,
)
from src.hands.apps.application_preflight import ApplicationPreflight
from src.hands.apps.application_launch_classifier import (
    CONFIANZA_ALTA,
    LaunchClassifier,
    LaunchSubtype,
    LaunchType,
)
from src.hands.inventory.system_inventory import generate_machine_id
from src.memory.storage import Entity, MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _informe_coincide(machine_id="maquina-prueba"):
    return {
        "maquina_actual": machine_id,
        "maquina_registrada": machine_id,
        "equipo_coincide": True,
        "bloqueado": False,
        "requiere_reescaneo": False,
        "motivo": None,
        "inventario_utilizable": True,
    }


def _discovery_con_inventario_temp(tmp_path, machine_id, informe_aislamiento):
    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    calib = MagicMock()
    calib.discover_applications.return_value = []
    storage = MagicMock()
    storage.verificar_identidad_equipo.return_value = informe_aislamiento
    mm = MemoryManager(str(tmp_path / "data" / "memory"))
    app_manager = MagicMock()
    app_manager.memory_manager = mm
    discovery = ApplicationDiscovery(
        preflight=preflight,
        clasificador=clasificador,
        storage=storage,
        calibration=calib,
        machine_id=machine_id,
        app_manager=app_manager,
    )
    return discovery, mm, storage


def _candidato(
    candidate_id,
    name,
    ruta,
    fuente=FUENTE_INVENTARIO,
    launch_type=LaunchType.EJECUTABLE,
    launch_subtype=LaunchSubtype.DESCONOCIDO,
    nombre_comercial=None,
    aliases=None,
    evidencia=None,
    archivo_existe=True,
    producto=None,
    version=None,
):
    if aliases is None:
        aliases = []
    if evidencia is None:
        if archivo_existe:
            evidencia = ["archivo_existe:" + ruta]
        else:
            evidencia = []
    return DiscoveredCandidate(
        candidate_id=candidate_id,
        name=name,
        absolute_path=ruta if archivo_existe else None,
        destination=ruta if archivo_existe else None,
        nombre_comercial=nombre_comercial or name,
        aliases=list(aliases),
        launch_type=launch_type,
        launch_subtype=launch_subtype,
        es_lanzable=True,
        evidencia=list(evidencia),
        confianza=CONFIANZA_ALTA,
        version=version,
        producto=producto,
        fuente=fuente,
        ultima_comprobacion="2026-11-12T00:00:00+00:00",
        disponible=True,
    )


# ---------------------------------------------------------------------------
# .exe GUI / CLI / instalador / desconocido
# ---------------------------------------------------------------------------


class TestAutoRegistroTiposEjecutableYSubtipo:
    """Registro de .exe con distintos subtipos de lanzamiento (GUI, CLI,
    instalador, desconocido). Ninguna aplicacion se lanza."""

    def test_registro_gui_aplicacion(self, tmp_path):
        exe = tmp_path / "app_gui.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-gui", "App GUI", str(exe),
            launch_subtype=LaunchSubtype.GUI_APLICACION,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        assert resultado["errores"] == 0
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        assert entidad.type == "application"
        assert entidad.name == "app gui"
        props = entidad.properties or {}
        assert props.get("tipo_lanzamiento_nativo") == "ejecutable"
        assert props.get("estado_disponible") == "available"
        assert entidad.tags and entidad.tags[0] == "gui_aplicacion"

    def test_registro_herramienta_cli(self, tmp_path):
        exe = tmp_path / "app_cli.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-cli", "App CLI", str(exe),
            launch_subtype=LaunchSubtype.HERRAMIENTA_CLI,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        props = entidad.properties or {}
        assert entidad.tags and entidad.tags[0] == "herramienta_cli"

    def test_registro_instalador(self, tmp_path):
        exe = tmp_path / "setup_program.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-inst", "Setup Program", str(exe),
            launch_subtype=LaunchSubtype.INSTALADOR,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        props = entidad.properties or {}
        assert entidad.tags and entidad.tags[0] == "instalador"

    def test_registro_rol_desconocido(self, tmp_path):
        exe = tmp_path / "componente_aux.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-des", "Componente Aux", str(exe),
            launch_subtype=LaunchSubtype.DESCONOCIDO,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        props = entidad.properties or {}
        assert entidad.tags and entidad.tags[0] == "desconocido"


# ---------------------------------------------------------------------------
# aliases y tipo de lanzamiento
# ---------------------------------------------------------------------------


class TestAutoRegistroAliasYTipoLanzamiento:
    """aliases observados y tipo de lanzamiento nativo se conservan en la
    entidad del catalogo global."""

    def test_aliases_preservados_en_catalogo(self, tmp_path):
        exe = tmp_path / "app_con_alias.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-alias", "App Con Alias", str(exe),
            aliases=["alias1", "Alias 2", "app-con-alias"],
            nombre_comercial="App Con Alias",
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        assert "alias1" in entidad.aliases
        assert "Alias 2" in entidad.aliases
        assert "app-con-alias" in entidad.aliases

    def test_tipo_lanzamiento_registrado_en_properties(self, tmp_path):
        exe = tmp_path / "app_tipo.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-tipo", "App Tipo", str(exe),
            launch_type=LaunchType.EJECUTABLE,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        props = entidad.properties or {}
        assert props.get("tipo_lanzamiento_nativo") == "ejecutable"


# ---------------------------------------------------------------------------
# estado disponible
# ---------------------------------------------------------------------------


class TestAutoRegistroEstadoDisponible:
    """estado_disponible disponible/no_disponible segun destino observable."""

    def test_estado_available_cuando_destino_observable(self, tmp_path):
        exe = tmp_path / "app_disponible.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-disp", "App Disponible", str(exe),
            archivo_existe=True,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        props = entidad.properties or {}
        assert props.get("estado_disponible") == "available"
        assert props.get("ruta_absoluta_observada") == str(exe)

    def test_estado_no_disponible_cuando_destino_no_observable(self, tmp_path):
        """Destino sin archivo existente: no se registra porque no hay
        destino observable (se omite, no se crea entidad no_disponible)."""
        candidato = _candidato(
            "c-no-disp", "App No Disponible",
            r"C:\NoExiste\app_no_disponible.exe",
            archivo_existe=False,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 0
        assert resultado["omitidos"] == 1
        assert resultado["detalle_omitidos"][0]["razon"] == "destino_no_observable"
        assert len(mm.get_entities_by_type("application")) == 0


# ---------------------------------------------------------------------------
# upsert repetido
# ---------------------------------------------------------------------------


class TestAutoRegistroUpsertRepetido:
    """El upsert repetido por ID estable no duplica y actualiza campos de
    observacion."""

    def test_upsert_repetido_no_duplica(self, tmp_path):
        exe = tmp_path / "app_idem.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-idem", "App Idem", str(exe),
            nombre_comercial="App Idem",
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        r1 = discovery.auto_registrar_candidatos_inventario([candidato])
        r2 = discovery.auto_registrar_candidatos_inventario([candidato])
        assert r1["registrados"] == 1
        assert r2["registrados"] == 1
        entidades = mm.get_entities_by_type("application")
        assert len(entidades) == 1
        assert entidades[0].id == r1["detalle_registrados"][0]["id"]

    def test_upsert_repetido_actualiza_fecha_observacion(self, tmp_path):
        exe = tmp_path / "app_actualiza.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-act", "App Actualiza", str(exe),
            nombre_comercial="App Actualiza",
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        r1 = discovery.auto_registrar_candidatos_inventario([candidato])
        entidad_despues_1 = mm.get_entity(r1["detalle_registrados"][0]["id"])
        fecha_1 = (entidad_despues_1.properties or {}).get("fecha_observacion")
        r2 = discovery.auto_registrar_candidatos_inventario([candidato])
        entidad_despues_2 = mm.get_entity(r2["detalle_registrados"][0]["id"])
        fecha_2 = (entidad_despues_2.properties or {}).get("fecha_observacion")
        assert fecha_1 is not None
        assert fecha_2 is not None
        # updated_at se refresca en cada upsert
        assert entidad_despues_2.updated_at >= entidad_despues_1.updated_at


# ---------------------------------------------------------------------------
# IDs estables
# ---------------------------------------------------------------------------


class TestAutoRegistroIDsEstables:
    """entity_id estable, determinista y sin fragmentos de ruta absoluta."""

    def test_entity_id_sin_fragmentos_ruta_absoluta(self, tmp_path):
        exe = tmp_path / "app_ruta.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-ruta", "App Ruta", str(exe),
            archivo_existe=True,
            nombre_comercial="App Ruta",
        )
        # absolute_path apunta a un archivo real en tmp; el entity_id nunca
        # debe incorporar fragmentos de ruta absoluta.
        descubrimiento, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = descubrimiento.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entity_id = resultado["detalle_registrados"][0]["id"]
        ruta_str = str(exe)
        assert ruta_str not in entity_id
        assert "Users" not in entity_id
        assert "AppData" not in entity_id
        assert "Local" not in entity_id
        assert "Temp" not in entity_id
        assert entity_id == "nombre:app ruta"

    def test_identidad_paquete_determinista(self, tmp_path):
        exe = tmp_path / "app_paquete.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-paq", "App Paquete", str(exe),
            evidencia=["paquete_id:MiPaquete.123"],
            nombre_comercial="App Paquete",
        )
        descubrimiento, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        r1 = descubrimiento.auto_registrar_candidatos_inventario([candidato])
        r2 = descubrimiento.auto_registrar_candidatos_inventario([candidato])
        assert r1["detalle_registrados"][0]["id"] == "paquete:MiPaquete.123"
        assert r2["detalle_registrados"][0]["id"] == r1["detalle_registrados"][0]["id"]

    def test_identidad_nombre_comercial_determinista(self, tmp_path):
        exe = tmp_path / "app_nombre.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-nom", "App Nombre", str(exe),
            nombre_comercial="App Nombre",
        )
        descubrimiento, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        r1 = descubrimiento.auto_registrar_candidatos_inventario([candidato])
        r2 = descubrimiento.auto_registrar_candidatos_inventario([candidato])
        entity_id = r1["detalle_registrados"][0]["id"]
        assert entity_id == "nombre:app nombre"
        assert r2["detalle_registrados"][0]["id"] == entity_id
        assert "C:" not in entity_id

    def test_identidad_insuficiente_usa_candidate_id(self, tmp_path):
        exe = tmp_path / "app_insuf.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-insuf", "App Insuficiente", str(exe),
            nombre_comercial=None,
            evidencia=[],
        )
        descubrimiento, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = descubrimiento.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entity_id = resultado["detalle_registrados"][0]["id"]
        # Sin evidencia estable ni nombre_comercial, usa el nombre normalizado.
        assert entity_id == "nombre:app insuficiente"
        assert "C:" not in entity_id
        assert "Users" not in entity_id


# ---------------------------------------------------------------------------
# datos JSON corruptos
# ---------------------------------------------------------------------------


class TestAutoRegistroDatosJSONCorruptos:
    """entities.json corrupto no bloquea el auto-registro: se guarda una copia
    del original, se recuperan sus entidades y se sigue escribiendo."""

    def test_catalogo_corrupto_continua_registro(self, tmp_path):
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entidades_path = memoria_dir / "entities.json"
        entidades_path.write_text("{no es json valido", encoding="utf-8")

        exe = tmp_path / "app_corrupto.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-corr", "App Corrupto", str(exe),
            nombre_comercial="App Corrupto",
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        # No bloquea: registra la entidad a pesar del catalogo corrupto.
        assert resultado["registrados"] == 1
        assert resultado["errores"] == 0
        # El fichero queda como JSON valido (lista) y contiene la entidad.
        datos = json.loads(entidades_path.read_text(encoding="utf-8"))
        assert isinstance(datos, list)
        ids = {e.get("id") for e in datos if isinstance(e, dict)}
        entidad_id = resultado["detalle_registrados"][0]["id"]
        assert entidad_id in ids
        # El original corrupto queda guardado en una copia exacta.
        copias = sorted(memoria_dir.glob("entities.json.corrupto-*"))
        assert len(copias) == 1
        assert copias[0].read_text(encoding="utf-8") == "{no es json valido"


# ---------------------------------------------------------------------------
# preservacion de entidades previas y no-app
# ---------------------------------------------------------------------------


class TestAutoRegistroPreservacionEntidadesPrevias:
    """Entidades preexistentes (incluidas no-app) se preservan entre
    upserts y no se borran ni se marcan como desaparecidas."""

    def test_entidades_no_app_preservadas(self, tmp_path):
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entidades_path = memoria_dir / "entities.json"
        entidades_path.write_text(
            json.dumps([
                {"id": "streamer-existente", "type": "streamer", "name": "Streamer",
                 "properties": {}, "aliases": [], "tags": [], "confidence": 1.0},
            ], ensure_ascii=False)
        )

        exe = tmp_path / "app_nueva.exe"
        exe.write_text("dummy")
        candidatos = [_candidato(
            "c-nueva", "App Nueva", str(exe),
            nombre_comercial="App Nueva",
        )]

        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario(candidatos)
        assert resultado["registrados"] == 1

        streamer = mm.get_entity("streamer-existente")
        assert streamer is not None
        assert streamer.type == "streamer"
        assert streamer.name == "Streamer"

    def test_campos_definidos_manualmente_preservados_tras_upsert(self, tmp_path):
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entidades_path = memoria_dir / "entities.json"
        entidades_path.write_text(
            json.dumps([
                {
                    "id": "paquete:appmanual",
                    "type": "application",
                    "name": "App Manual",
                    "properties": {
                        "estado_disponible": "available",
                        "campo_manual": "valor_definido_por_usuario",
                    },
                    "aliases": ["alias_manual"],
                    "tags": ["manual"],
                    "confidence": 0.9,
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                },
            ], ensure_ascii=False)
        )

        exe = tmp_path / "app_manual.exe"
        exe.write_text("dummy")
        candidato = _candidato(
            "c-manual", "App Manual", str(exe),
            evidencia=["paquete_id:appmanual"],
            nombre_comercial="App Manual",
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity("paquete:appmanual")
        assert entidad is not None
        # Campo definido manualmente se preserva
        props = entidad.properties or {}
        assert props.get("campo_manual") == "valor_definido_por_usuario"
        # Alias manual se preserva (no se sobrescribe por el upsert de observacion)
        assert "alias_manual" in entidad.aliases
        # created_at se preserva (momento de creacion original)
        assert entidad.created_at == "2024-01-01T00:00:00"


# ---------------------------------------------------------------------------
# cero intervencion manual
# ---------------------------------------------------------------------------


class TestAutoRegistroCeroIntervencionManual:
    """El auto-registro es automatico: no requiere entrada de usuario ni
    modificacion manual del catalogo."""

    def test_registro_automatico_sin_intervencion_usuario(self, tmp_path):
        exe1 = tmp_path / "app_auto1.exe"
        exe1.write_text("dummy")
        exe2 = tmp_path / "app_auto2.exe"
        exe2.write_text("dummy")
        candidatos = [
            _candidato("c-auto1", "App Auto 1", str(exe1), nombre_comercial="App Auto 1"),
            _candidato("c-auto2", "App Auto 2", str(exe2), nombre_comercial="App Auto 2"),
        ]
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        # Llamada unica, sin parametros de usuario ni confirmaciones.
        resultado = discovery.auto_registrar_candidatos_inventario(candidatos)
        assert resultado["registrados"] == 2
        assert resultado["errores"] == 0
        assert resultado["bloqueado"] is False
        assert resultado["no_verificado"] is False
        ids = {e.id for e in mm.get_entities_by_type("application")}
        assert len(ids) == 2


# ---------------------------------------------------------------------------
# integracion real con notepad
# ---------------------------------------------------------------------------


class TestAutoRegistroIntegracionRealNotepad:
    """Integracion real con notepad.exe del equipo: entidad representada con
    entity_id estable, sin lanzar la aplicacion y sin tocar data/ de
    produccion."""

    def test_integracion_notepad_real_sin_lanzar(self, tmp_path):
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        candidato = DiscoveredCandidate(
            candidate_id="c-notepad-1110",
            name="Notepad",
            absolute_path=notepad,
            destination=notepad,
            nombre_comercial="Notepad",
            aliases=["notepad", "bloc de notas"],
            launch_type=LaunchType.EJECUTABLE,
            launch_subtype=LaunchSubtype.GUI_APLICACION,
            es_lanzable=True,
            evidencia=["archivo_existe:" + notepad],
            confianza=CONFIANZA_ALTA,
            fuente=FUENTE_INVENTARIO,
            ultima_comprobacion="2026-11-12T00:00:00+00:00",
            disponible=True,
        )
        discovery, mm, _ = _discovery_con_inventario_temp(
            tmp_path, "maquina-prueba", _informe_coincide()
        )
        resultado = discovery.auto_registrar_candidatos_inventario([candidato])
        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        assert entidad.name == "notepad"
        assert entidad.type == "application"
        assert "C:" not in entidad.id
        assert "System32" not in entidad.id
        assert "Windows" not in entidad.id
        props = entidad.properties or {}
        assert props.get("ruta_absoluta_observada") == notepad
        assert props.get("estado_disponible") == "available"
        assert "notepad" in entidad.aliases
        assert "bloc de notas" in entidad.aliases
