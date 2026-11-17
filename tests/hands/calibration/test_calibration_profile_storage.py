"""
Tests de contrato de los estados de calibracion separados por dimension
(semantica, geometria, accion) y del almacen de perfiles SQLite
(unidades 3.8.6.8.3 a 3.8.6.8.5).

Incluye pruebas de la migracion versionada y transaccional del esquema de
data/system_inventory.sqlite3 de v5 a v6 (tablas calibration_profiles y
calibration_controls solo si no existen, aislamiento por machine_id, datos
de inventario preexistentes conservados) y de que el catalogo global
entities.json nunca almacena datos fisicos ni coordenadas.

Verifican:
- CalibrationState expone PENDIENTE, CANDIDATO, DETECTADO, VALIDADO,
  OBSOLETO, NO_VERIFICADO y BLOQUEADO.
- Cada control guarda semantic_state, geometric_state y action_state de
  forma independiente; todos empiezan en PENDIENTE.
- check_control_record: geometria VALIDADO exige procedencia de accesibilidad
  del SO o al menos dos fuentes visuales independientes; un solo modelo con
  confianza alta no basta.
- check_profile: un perfil VALIDADO exige controles, huella de ventana,
  tamano de area cliente y factor de escala.
- Almacen real sobre SQLite temporal: activacion unica de perfiles VALIDADO,
  perfiles no VALIDADO como evidencia inactiva, aislamiento por machine_id,
  base de otro equipo bloqueada, perfiles invalidos sin escritura y rollback.
- Marca de tiempo de control (calibrated_at): el registro la exige, el almacen
  la rellena si falta y no la sobrescribe si ya existe (unidad 3.8.6.8.4).
- Persistencia solo de lo que pasa la puerta de calidad 3.8.6.4: un control
  rechazado por la puerta (por ejemplo, accion VALIDADO sin metodo real) no se
  escribe ni deja rastro parcial; los controles validos se guardan con
  procedencia, version de detector, caja original y refinada, confianza por
  dimension, metodo de interaccion y marca de tiempo (unidad 3.8.6.8.4).

Todos los tests usan bases SQLite temporales (tmp_path) y nunca tocan
data/system_inventory.sqlite3 de produccion. No abren ventanas ni aplicaciones.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src.hands.calibration.calibration_profile_storage import (
    ACCESSIBILITY_PROVENANCE,
    CalibrationProfile,
    CalibrationProfileStore,
    CalibrationState,
    CalibratedControlRecord,
    CalibrationStoreBlocked,
    CalibrationStoreError,
    MIN_INDEPENDENT_VISUAL_SOURCES,
    check_control_record,
    check_profile,
    default_db_path,
)
from src.hands.inventory.system_inventory_storage import SCHEMA_VERSION, SystemInventoryStorage

ESTADOS_ESPERADOS = {
    CalibrationState.PENDIENTE,
    CalibrationState.CANDIDATO,
    CalibrationState.DETECTADO,
    CalibrationState.VALIDADO,
    CalibrationState.OBSOLETO,
    CalibrationState.NO_VERIFICADO,
    CalibrationState.BLOQUEADO,
}

MAQUINA = "maquina-prueba-1"
APP = "app_bloc_de_notas"
HUELLA = "huella-ventana-1"


def _control(
    control_id="ctrl_boton_aceptar",
    app_id=APP,
    name="Aceptar",
    semantic_state=CalibrationState.PENDIENTE,
    geometric_state=CalibrationState.PENDIENTE,
    action_state=CalibrationState.PENDIENTE,
    provenance=None,
    interaction_method="pointer",
    box=(0.10, 0.10, 0.40, 0.40),
    safe_point_normalized=None,
    calibrated_at="2026-01-15T10:30:00+00:00",
):
    return CalibratedControlRecord(
        control_id=control_id,
        app_id=app_id,
        name=name,
        control_type="button",
        semantic_state=semantic_state,
        geometric_state=geometric_state,
        action_state=action_state,
        client_box_normalized=box,
        safe_point_normalized=safe_point_normalized,
        interaction_method=interaction_method,
        provenance=list(provenance or []),
        detector_versions={"qwen3-vl": "8b"},
        original_box=None,
        refined_box=None,
        confidences={
            "detection": 0.90,
            "semantic": 0.80,
            "interactivity": 0.85,
            "geometry": 0.90,
        },
        reasons=[],
        calibrated_at=calibrated_at,
    )


def _profile(
    app_id=APP,
    status=CalibrationState.VALIDADO,
    controls=None,
    machine_id=MAQUINA,
    window_fingerprint=HUELLA,
    client_size=(1800, 950),
    scale_factor=1.25,
):
    return CalibrationProfile(
        profile_id="",
        machine_id=machine_id,
        app_id=app_id,
        topology_fingerprint="topologia-x",
        window_fingerprint=window_fingerprint,
        display_id="monitor-1",
        scale_factor=scale_factor,
        dpi=120,
        display_pixel_size=(1920, 1080),
        orientation="horizontal",
        window_state="maximizado",
        client_size=client_size,
        platform="Windows",
        status=status,
        controls=list(controls if controls is not None else [_control()]),
    )


def _abrir_store(db_path, machine_id=MAQUINA):
    store = CalibrationProfileStore(db_path=db_path, machine_id=machine_id)
    assert store.initialize() is True
    assert store.is_blocked is False
    return store


# ---------------------------------------------------------------------------
# Estados separados: semantica / geometria / accion
# ---------------------------------------------------------------------------

class TestEstadosCalibracion:
    """CalibrationState modela las siete dimensiones de estado del roadmap."""

    def test_siete_estados_definidos(self):
        assert set(CalibrationState) == ESTADOS_ESPERADOS

    def test_cada_estado_es_su_propio_texto(self):
        for estado in CalibrationState:
            assert estado.value == estado.name


class TestRegistroDeControl:
    """CalibratedControlRecord guarda los tres estados de forma independiente."""

    def test_tres_estados_independientes_empiezan_en_pendiente(self):
        control = _control()
        assert control.semantic_state == CalibrationState.PENDIENTE
        assert control.geometric_state == CalibrationState.PENDIENTE
        assert control.action_state == CalibrationState.PENDIENTE

    def test_cambiar_un_estado_no_afecta_a_los_otros(self):
        control = _control()
        control.geometric_state = CalibrationState.DETECTADO
        assert control.geometric_state == CalibrationState.DETECTADO
        assert control.semantic_state == CalibrationState.PENDIENTE
        assert control.action_state == CalibrationState.PENDIENTE

    def test_centro_normalizado_usa_punto_seguro_si_existe(self):
        control = _control(safe_point_normalized=(0.30, 0.70))
        assert control.normalized_center() == (0.30, 0.70)

    def test_centro_normalizado_es_centro_de_la_caja_sin_punto_seguro(self):
        control = _control(safe_point_normalized=None, box=(0.10, 0.20, 0.30, 0.60))
        assert control.normalized_center() == (0.20, 0.40)

    @pytest.mark.parametrize(
        "estado_accion,metodo,estado_geometria,esperado",
        [
            (CalibrationState.VALIDADO, "pointer", CalibrationState.VALIDADO, True),
            (CalibrationState.VALIDADO, "none", CalibrationState.VALIDADO, False),
            (
                CalibrationState.VALIDADO,
                "pointer",
                CalibrationState.DETECTADO,
                False,
            ),
            (CalibrationState.VALIDADO, "keyboard", CalibrationState.DETECTADO, True),
            (CalibrationState.DETECTADO, "pointer", CalibrationState.VALIDADO, False),
        ],
    )
    def test_es_accionable_exige_accion_valida_y_geometria_si_puntero(
        self, estado_accion, metodo, estado_geometria, esperado
    ):
        control = _control(
            action_state=estado_accion,
            interaction_method=metodo,
            geometric_state=estado_geometria,
        )
        assert control.is_actionable() is esperado


# ---------------------------------------------------------------------------
# Validacion de registro de control (check_control_record)
# ---------------------------------------------------------------------------

class TestCheckControlRecord:
    """check_control_record aplica las puertas de calidad por estado."""

    def test_registro_valido_no_tiene_problemas(self):
        assert check_control_record(_control()) == []

    def test_control_id_vacio(self):
        problemas = check_control_record(_control(control_id="   "))
        assert any("control_id vacio" in p for p in problemas)

    def test_app_id_vacio(self):
        problemas = check_control_record(_control(app_id="   "))
        assert any("app_id vacio" in p for p in problemas)

    def test_caja_fuera_de_rango_o_degenerada(self):
        assert any(
            "client_box_normalized" in p
            for p in check_control_record(_control(box=(0.10, 0.10, 1.10, 0.40)))
        )
        assert any(
            "client_box_normalized" in p
            for p in check_control_record(_control(box=(0.20, 0.20, 0.10, 0.40)))
        )

    def test_punto_seguro_fuera_de_la_caja(self):
        problemas = check_control_record(
            _control(safe_point_normalized=(0.90, 0.90), box=(0.10, 0.10, 0.40, 0.40))
        )
        assert any("safe_point_normalized" in p for p in problemas)

    def test_metodo_de_interaccion_desconocido(self):
        problemas = check_control_record(_control(interaction_method="telepatia"))
        assert any("interaction_method desconocido" in p for p in problemas)

    def test_geometria_validado_con_una_sola_fuente_visual_falla(self):
        problemas = check_control_record(
            _control(
                geometric_state=CalibrationState.VALIDADO,
                provenance=["qwen3-vl"],
            )
        )
        assert any("un solo modelo" in p for p in problemas)

    def test_geometria_validado_con_accesibilidad_so_pasa_sin_fuentes_visuales(self):
        assert (
            check_control_record(
                _control(
                    geometric_state=CalibrationState.VALIDADO,
                    provenance=["uia"],
                )
            )
            == []
        )
        assert (
            check_control_record(
                _control(
                    geometric_state=CalibrationState.VALIDADO,
                    provenance=["ax"],
                )
            )
            == []
        )
        assert (
            check_control_record(
                _control(
                    geometric_state=CalibrationState.VALIDADO,
                    provenance=["accessibility"],
                )
            )
            == []
        )

    def test_geometria_validado_con_dos_fuentes_visuales_independientes_pasa(self):
        assert (
            check_control_record(
                _control(
                    geometric_state=CalibrationState.VALIDADO,
                    provenance=["qwen3-vl", "omniparser"],
                )
            )
            == []
        )
        assert (
            check_control_record(
                _control(
                    geometric_state=CalibrationState.VALIDADO,
                    provenance=["uia", "qwen3-vl"],
                )
            )
            == []
        )

    def test_geometria_validado_sin_procedencia_falla(self):
        problemas = check_control_record(
            _control(geometric_state=CalibrationState.VALIDADO, provenance=[])
        )
        assert any("una sola fuente visual" in p for p in problemas)

    def test_accion_validado_sin_metodo_real_falla(self):
        problemas = check_control_record(
            _control(action_state=CalibrationState.VALIDADO, interaction_method="none")
        )
        assert any("sin metodo de interaccion real" in p for p in problemas)

    def test_accion_puntero_validado_sin_geometria_validada_falla(self):
        problemas = check_control_record(
            _control(
                action_state=CalibrationState.VALIDADO,
                interaction_method="pointer",
                geometric_state=CalibrationState.DETECTADO,
            )
        )
        assert any("geometria VALIDADO" in p for p in problemas)

    def test_semantica_validado_sin_procedencia_falla(self):
        problemas = check_control_record(
            _control(semantic_state=CalibrationState.VALIDADO, provenance=[])
        )
        assert any("procedencia" in p for p in problemas)

    def test_minimo_fuentes_visuales_es_dos(self):
        assert MIN_INDEPENDENT_VISUAL_SOURCES == 2
        assert "uia" in ACCESSIBILITY_PROVENANCE
        assert "ax" in ACCESSIBILITY_PROVENANCE
        assert "accessibility" in ACCESSIBILITY_PROVENANCE


# ---------------------------------------------------------------------------
# Validacion de perfil (check_profile)
# ---------------------------------------------------------------------------

class TestCheckProfile:
    """check_profile valida el perfil completo antes de persistirlo."""

    def test_perfil_valido_no_tiene_problemas(self):
        assert check_profile(_profile(controls=[_control()])) == []

    def test_app_id_vacio(self):
        problemas = check_profile(_profile(app_id="   ", controls=[_control()]))
        assert any("app_id vacio" in p for p in problemas)

    def test_machine_id_vacio(self):
        problemas = check_profile(_profile(machine_id="   ", controls=[_control()]))
        assert any("machine_id vacio" in p for p in problemas)

    def test_control_id_duplicado(self):
        ctrl = _control(control_id="ctrl_dup")
        problemas = check_profile(
            _profile(controls=[ctrl, _control(control_id="ctrl_dup", name="Otro")])
        )
        assert any("control_id duplicado" in p for p in problemas)

    def control_de_otra_aplicacion(self):
        problemas = check_profile(
            _profile(
                controls=[
                    _control(control_id="ctrl_a", app_id="app_otra"),
                    _control(control_id="ctrl_b"),
                ]
            )
        )
        assert any("pertenece a otra aplicacion" in p for p in problemas)

    def test_perfil_validado_exige_controles(self):
        problemas = check_profile(_profile(status=CalibrationState.VALIDADO, controls=[]))
        assert any("sin controles" in p for p in problemas)

    def test_perfil_validado_exige_huella_de_ventana(self):
        problemas = check_profile(
            _profile(status=CalibrationState.VALIDADO, window_fingerprint="", controls=[_control()])
        )
        assert any("sin window_fingerprint" in p for p in problemas)

    def test_perfil_validado_exige_tamano_de_area_cliente(self):
        perfil = _profile(status=CalibrationState.VALIDADO, client_size=None, controls=[_control()])
        problemas = check_profile(perfil)
        assert any("sin client_size" in p for p in problemas)

    def test_perfil_validado_exige_factor_de_escala(self):
        perfil = _profile(status=CalibrationState.VALIDADO, scale_factor=None, controls=[_control()])
        problemas = check_profile(perfil)
        assert any("sin scale_factor" in p for p in problemas)

    def test_metadata_con_clave_prohibida(self):
        perfil = _profile(controls=[_control()])
        perfil.metadata = {"capture_path": "C:/temp/cap.png"}
        problemas = check_profile(perfil)
        assert any("capture_path" in p for p in problemas)


# ---------------------------------------------------------------------------
# Almacen de perfiles sobre SQLite temporal real (integracion del sistema)
# ---------------------------------------------------------------------------

class TestAlmacenPerfilesSQLite:
    """CalibrationProfileStore sobre base SQLite temporal, aislada por equipo."""

    def test_inicializacion_crea_tablas_de_calibracion(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        conn = store._connect()
        try:
            filas = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                "('calibration_profiles','calibration_controls')"
            ).fetchall()
            assert len(filas) == 2
        finally:
            store.close()

    def test_guarda_y_lee_perfil_valido_con_control(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            control = _control(
                geometric_state=CalibrationState.VALIDADO,
                provenance=["uia"],
            )
            perfil = _profile(controls=[control])
            profile_id = store.save_profile(perfil)
            assert profile_id
            assert perfil.profile_id == profile_id
            assert perfil.is_active is True

            leido = store.get_active_profile(APP, HUELLA)
            assert leido is not None
            assert leido.profile_id == profile_id
            assert leido.is_active is True
            assert leido.status == CalibrationState.VALIDADO

            control_leido = store.get_control(APP, "ctrl_boton_aceptar")
            assert control_leido is not None
            assert control_leido.control_id == "ctrl_boton_aceptar"
            assert control_leido.geometric_state == CalibrationState.VALIDADO
            assert control_leido.provenance == ["uia"]
        finally:
            store.close()

    def test_solo_un_perfil_valido_activo_por_app_y_huella(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            perfil1 = _profile()
            id1 = store.save_profile(perfil1)
            assert perfil1.is_active is True

            perfil2 = _profile()
            id2 = store.save_profile(perfil2)
            assert id2 != id1
            assert perfil2.is_active is True

            activos = store.list_active_profiles(APP)
            assert len(activos) == 1
            assert activos[0].profile_id == id2

            p1 = store.get_profile(id1)
            assert p1 is not None
            assert p1.is_active is False
            assert p1.status == CalibrationState.VALIDADO
        finally:
            store.close()

    def test_perfil_no_valido_queda_inactivo_y_no_desactiva_al_valido(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            perfil_valido = _profile()
            store.save_profile(perfil_valido)
            assert store.get_active_profile(APP, HUELLA) is not None

            perfil_pendiente = _profile(status=CalibrationState.PENDIENTE)
            store.save_profile(perfil_pendiente)
            assert perfil_pendiente.is_active is False

            activo = store.get_active_profile(APP, HUELLA)
            assert activo is not None
            assert activo.status == CalibrationState.VALIDADO
            assert activo.profile_id == perfil_valido.profile_id
        finally:
            store.close()

    def test_get_control_devuelve_control_del_perfil_activo(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            control = _control(control_id="ctrl_unico", action_state=CalibrationState.DETECTADO)
            store.save_profile(_profile(controls=[control]))
            leido = store.get_control(APP, "ctrl_unico")
            assert leido is not None
            assert leido.action_state == CalibrationState.DETECTADO
            assert store.get_control(APP, "control_inexistente") is None
        finally:
            store.close()

    def test_marcar_obsoleto_desactiva_y_cambia_estado(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            store.save_profile(_profile())
            n = store.mark_obsolete(APP, "cambio de escala del monitor")
            assert n == 1
            perfil = store.get_active_profile(APP, HUELLA)
            assert perfil is None
            todos = store.list_profiles(APP)
            assert len(todos) == 1
            assert todos[0].status == CalibrationState.OBSOLETO
            assert todos[0].is_active is False
            assert todos[0].obsolete_reason == "cambio de escala del monitor"
        finally:
            store.close()

    def test_actualizar_cache_absoluta_no_toca_geometria_relativa(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            control = _control(box=(0.05, 0.10, 0.30, 0.50))
            store.save_profile(_profile(controls=[control]))
            perfil = store.get_active_profile(APP, HUELLA)
            assert perfil is not None
            assert perfil.controls[0].client_box_normalized == (0.05, 0.10, 0.30, 0.50)

            assert store.update_absolute_cache(
                perfil.profile_id, {"pantalla_x": 500, "pantalla_y": 300}
            ) is True
            perfil = store.get_profile(perfil.profile_id)
            assert perfil.absolute_cache == {"pantalla_x": 500, "pantalla_y": 300}
            assert perfil.controls[0].client_box_normalized == (0.05, 0.10, 0.30, 0.50)
        finally:
            store.close()

    def test_maquina_distinta_en_misma_base_bloquea_el_almacen(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store_a = _abrir_store(db_path, machine_id="maquina-a")
        store_a.save_profile(_profile(machine_id="maquina-a"))
        store_a.close()

        store_b = CalibrationProfileStore(db_path=db_path, machine_id="maquina-b")
        assert store_b.initialize() is False
        assert store_b.is_blocked is True
        with pytest.raises(CalibrationStoreBlocked):
            store_b.save_profile(_profile(machine_id="maquina-b"))
        store_b.close()

    def test_perfil_invalido_no_se_escribe_y_no_quedan_rastros(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            perfil_invalido = _profile(status=CalibrationState.VALIDADO, controls=[])
            with pytest.raises(CalibrationStoreError):
                store.save_profile(perfil_invalido)
            assert store.list_profiles(APP) == []
            assert store.get_active_profile(APP, HUELLA) is None
        finally:
            store.close()

    def test_aislamiento_por_machine_id_en_bases_separadas(self, tmp_path: Path):
        db_a = tmp_path / "equipo_a.sqlite3"
        db_b = tmp_path / "equipo_b.sqlite3"
        store_a = _abrir_store(db_a, machine_id="equipo-a")
        store_b = _abrir_store(db_b, machine_id="equipo-b")
        try:
            store_a.save_profile(_profile(machine_id="equipo-a"))
            store_b.save_profile(_profile(machine_id="equipo-b"))

            assert len(store_a.list_profiles(APP)) == 1
            assert store_a.list_profiles(APP)[0].machine_id == "equipo-a"
            assert len(store_b.list_profiles(APP)) == 1
            assert store_b.list_profiles(APP)[0].machine_id == "equipo-b"
            assert store_b.get_active_profile(APP, HUELLA) is not None
        finally:
            store_a.close()
            store_b.close()

    def test_base_corrupta_bloquea_almacen_sin_destruir_datos(self, tmp_path: Path):
        db_path = tmp_path / "corrupto.sqlite3"
        db_path.write_bytes(b"esto no es una base de datos sqlite valida")
        store = CalibrationProfileStore(db_path=db_path, machine_id=MAQUINA)
        assert store.initialize() is False
        assert store.is_blocked is True
        assert store.blocked_reason is not None
        store.close()

    def test_solo_se_escribe_la_base_sqlite_indicada(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            store.save_profile(_profile(controls=[_control()]))
            store.close()
            archivos = [p.name for p in tmp_path.iterdir()]
            assert db_path.name in archivos
            assert not any("entities" in nombre for nombre in archivos)
            assert not any(nombre.endswith(".json") for nombre in archivos)
        finally:
            if not store.is_blocked:
                store.close()


# ---------------------------------------------------------------------------
# Marca de tiempo y persistencia solo de lo que pasa la puerta (3.8.6.8.4)
# ---------------------------------------------------------------------------

class TestMarcaDeTiempoDeControl:
    """Cada registro de control persistido lleva su marca de tiempo de calibracion."""

    def test_to_dict_incluye_calibrated_at(self):
        control = _control(calibrated_at="2026-01-15T10:30:00+00:00")
        assert control.to_dict()["calibrated_at"] == "2026-01-15T10:30:00+00:00"

    def test_check_control_record_rechaza_sin_marca_de_tiempo(self):
        problemas = check_control_record(_control(calibrated_at=""))
        assert any("marca de tiempo" in p for p in problemas)

    def test_guardado_rellena_marca_de_tiempo_si_falta(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            control = _control(calibrated_at="")
            perfil = _profile(controls=[control])
            store.save_profile(perfil)
            leido = store.get_control(APP, "ctrl_boton_aceptar")
            assert leido is not None
            assert leido.calibrated_at != ""
            datetime.fromisoformat(leido.calibrated_at)
        finally:
            store.close()

    def test_guardado_no_sobrescribe_marca_de_tiempo_existente(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            control = _control(calibrated_at="2026-01-15T10:30:00+00:00")
            perfil = _profile(controls=[control])
            store.save_profile(perfil)
            leido = store.get_control(APP, "ctrl_boton_aceptar")
            assert leido.calibrated_at == "2026-01-15T10:30:00+00:00"
        finally:
            store.close()


class TestPersistenciaSoloLoQuePasaLaPuerta:
    """El almacen solo escribe controles que superan el contrato de calidad y los guarda
    con procedencia, version de detector, caja original y refinada, confianza por dimension,
    metodo de interaccion y marca de tiempo; nunca guarda capturas de pantalla."""

    def _registro_pasa_puerta(self):
        return CalibratedControlRecord(
            control_id="ctrl_boton_aceptar",
            app_id=APP,
            name="Aceptar",
            control_type="button",
            semantic_state=CalibrationState.VALIDADO,
            geometric_state=CalibrationState.VALIDADO,
            action_state=CalibrationState.VALIDADO,
            client_box_normalized=(0.10, 0.10, 0.40, 0.40),
            client_box_px=(180, 95, 720, 380),
            safe_point_normalized=(0.25, 0.25),
            interaction_method="pointer",
            provenance=["uia", "qwen3-vl"],
            detector_versions={"uia": "8.0", "qwen3-vl": "8b"},
            original_box=(200.0, 100.0, 740.0, 400.0),
            refined_box=(180.0, 95.0, 720.0, 380.0),
            confidences={
                "detection": 0.90,
                "semantic": 0.85,
                "interactivity": 0.95,
                "geometry": 0.92,
            },
            reasons=[],
            calibrated_at="2026-01-15T10:30:00+00:00",
        )

    def test_control_rechazado_por_puerta_no_se_escribe(self, tmp_path: Path):
        # Accion VALIDADO sin metodo de interaccion real: fallo la puerta de 3.8.6.4.
        # Nada se escribe y no queda rastro parcial.
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            rechazado = _control(action_state=CalibrationState.VALIDADO, interaction_method="none")
            perfil = _profile(controls=[rechazado], status=CalibrationState.VALIDADO)
            with pytest.raises(CalibrationStoreError):
                store.save_profile(perfil)
            assert store.list_profiles(APP) == []
            assert store.get_active_profile(APP, HUELLA) is None
        finally:
            store.close()

    def test_control_persistido_lleva_todos_los_campos_de_38684(self, tmp_path: Path):
        db_path = tmp_path / "inventario.sqlite3"
        store = _abrir_store(db_path)
        try:
            perfil = _profile(controls=[self._registro_pasa_puerta()])
            profile_id = store.save_profile(perfil)
            assert profile_id
            assert perfil.is_active is True

            ctrl = store.get_control(APP, "ctrl_boton_aceptar")
            assert ctrl is not None
            assert ctrl.provenance == ["uia", "qwen3-vl"]
            assert ctrl.detector_versions == {"uia": "8.0", "qwen3-vl": "8b"}
            assert ctrl.original_box == (200.0, 100.0, 740.0, 400.0)
            assert ctrl.refined_box == (180.0, 95.0, 720.0, 380.0)
            assert ctrl.confidences == {
                "detection": 0.90,
                "semantic": 0.85,
                "interactivity": 0.95,
                "geometry": 0.92,
            }
            assert ctrl.interaction_method == "pointer"
            assert ctrl.calibrated_at == "2026-01-15T10:30:00+00:00"
            assert ctrl.is_actionable() is True

            leido = store.get_active_profile(APP, HUELLA)
            assert leido is not None
            assert leido.status == CalibrationState.VALIDADO
            assert len(leido.controls) == 1
            assert leido.metadata == {}
        finally:
            store.close()


def test_ruta_por_defecto_apunta_a_inventario_solo_lectura():
    """default_db_path solo resuelve la ruta; este test nunca escribe alla."""
    ruta = default_db_path()
    assert ruta.name == "system_inventory.sqlite3"
    assert ruta.parent.name == "data"


# ---------------------------------------------------------------------------
# Migracion de esquema v5 -> v6 (unidad 3.8.6.8.5)
# ---------------------------------------------------------------------------


class TestMigracionEsquemaV5AV6:
    """La base de inventario se migra de esquema v5 a v6 de forma
    versionada, transaccional y solo creando las tablas de calibracion
    cuando no existen. Ninguna fila de inventario preexistente se toca."""

    def _crear_db_v5(self, db_path: Path) -> dict:
        """Crea una base SQLite temporal en esquema v5 con datos y devuelve
        los conteos esperados por tabla."""
        import sqlite3

        conteos = {
            "machines": 1,
            "volumes": 1,
            "scan_runs": 1,
            "file_entries": 3,
            "application_candidates": 2,
            "lineas_base": 0,
        }
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(
                """
                CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
                CREATE TABLE machines (machine_id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
                CREATE TABLE volumes (volume_id TEXT PRIMARY KEY, machine_id TEXT NOT NULL, volume TEXT NOT NULL, volume_type TEXT, state TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, FOREIGN KEY (machine_id) REFERENCES machines(machine_id));
                CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, machine_id TEXT NOT NULL, volume TEXT NOT NULL, mode TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, result TEXT NOT NULL, entries_count INTEGER NOT NULL DEFAULT 0, errors_count INTEGER NOT NULL DEFAULT 0, exclusions_count INTEGER NOT NULL DEFAULT 0, coverage_estimate TEXT, FOREIGN KEY (machine_id) REFERENCES machines(machine_id));
                CREATE TABLE file_entries (entry_id TEXT PRIMARY KEY, scan_id TEXT NOT NULL, machine_id TEXT NOT NULL, volume TEXT NOT NULL, absolute_path TEXT NOT NULL, normalized_path TEXT NOT NULL DEFAULT '', relative_path TEXT NOT NULL, name TEXT NOT NULL, extension TEXT NOT NULL DEFAULT '', entry_type TEXT NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0, modified_at TEXT, created_at TEXT, accessed_at TEXT, attributes TEXT NOT NULL DEFAULT '[]', excluded INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'filesystem_scan', last_checked_at TEXT NOT NULL, FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id), FOREIGN KEY (machine_id) REFERENCES machines(machine_id));
                CREATE TABLE application_candidates (candidate_id TEXT PRIMARY KEY, scan_id TEXT NOT NULL, machine_id TEXT NOT NULL, volume TEXT NOT NULL, name TEXT NOT NULL, absolute_path TEXT NOT NULL, launch_type TEXT, confidence REAL, version TEXT, producto TEXT, evidencia TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL DEFAULT 'inventory', last_checked_at TEXT NOT NULL, FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id), FOREIGN KEY (machine_id) REFERENCES machines(machine_id));
                CREATE TABLE lineas_base (linea_id TEXT PRIMARY KEY, machine_id TEXT NOT NULL, volume TEXT NOT NULL, fecha_base TEXT NOT NULL, estado_volumen TEXT NOT NULL, cobertura REAL NOT NULL, entradas_count INTEGER NOT NULL DEFAULT 0, errores_count INTEGER NOT NULL DEFAULT 0, scan_id TEXT, created_at TEXT NOT NULL, FOREIGN KEY (machine_id) REFERENCES machines(machine_id));
                """
            )
            conn.execute("INSERT INTO schema_version(version) VALUES (5)")
            conn.execute("INSERT INTO machines(machine_id, created_at) VALUES (?, ?)", (MAQUINA, "2026-01-01T00:00:00+00:00"))
            conn.execute(
                "INSERT INTO volumes(volume_id, machine_id, volume, volume_type, state, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("vol-1", MAQUINA, "C:", "fijo", "montado", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at, finished_at, result, entries_count, errors_count, exclusions_count, coverage_estimate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("scan-1", MAQUINA, "C:", "completo", "2026-01-01T00:00:00+00:00", "2026-01-01T00:01:00+00:00", "ok", 3, 0, 0, None),
            )
            for i in range(conteos["file_entries"]):
                conn.execute(
                    "INSERT INTO file_entries(entry_id, scan_id, machine_id, volume, absolute_path, normalized_path, relative_path, name, extension, entry_type, size_bytes, last_checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"e-{i+1}", "scan-1", MAQUINA, "C:", f"C:/App/app{i+1}.exe", f"c:/app/app{i+1}.exe", "app", f"app{i+1}.exe", ".exe", "fichero", 1000 + i, "2026-01-01T00:00:00+00:00"),
                )
            for i in range(conteos["application_candidates"]):
                conn.execute(
                    "INSERT INTO application_candidates(candidate_id, scan_id, machine_id, volume, name, absolute_path, launch_type, confidence, version, producto, evidencia, source, last_checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"cand-{i+1}", "scan-1", MAQUINA, "C:", f"App {i+1}", f"C:/App/app{i+1}.exe", "ejecutable", 0.9, "1.0", "Empresa", "[]", "inventory", "2026-01-01T00:00:00+00:00"),
                )
            conn.commit()
        finally:
            conn.close()
        return conteos

    def test_migracion_v5_a_v6_crea_tablas_de_calibracion_y_conserva_datos(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "inventario_v5.sqlite3"
        conteos = self._crear_db_v5(db_path)
        storage = SystemInventoryStorage(db_path)
        try:
            version = storage.initialize(machine_id_actual=MAQUINA)
            assert version == SCHEMA_VERSION
            assert storage.schema_version() == SCHEMA_VERSION
            conn = storage.connect()
            try:
                tablas = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                assert "calibration_profiles" in tablas
                assert "calibration_controls" in tablas
                indices = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
                assert "idx_calibration_profiles_unique_active" in indices
                for tabla, esperado in conteos.items():
                    actual = int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
                    assert actual == esperado, (
                        f"La tabla {tabla} cambio de filas en la migracion: {esperado} -> {actual}"
                    )
                fila = conn.execute("SELECT absolute_path FROM file_entries WHERE entry_id = 'e-1'").fetchone()
                assert fila is not None and fila[0] == "C:/App/app1.exe"
                fila = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
                assert fila is not None and int(fila[0]) == 6
            finally:
                conn.close()
        finally:
            storage.close()

    def test_migracion_v5_a_v6_idempotente(self, tmp_path: Path):
        db_path = tmp_path / "inventario_v5.sqlite3"
        self._crear_db_v5(db_path)
        storage = SystemInventoryStorage(db_path)
        try:
            assert storage.initialize(machine_id_actual=MAQUINA) == 6
            assert storage.initialize(machine_id_actual=MAQUINA) == 6
            assert storage.schema_version() == 6
        finally:
            storage.close()

    def test_base_nueva_ya_trae_tablas_de_calibracion_en_v6(self, tmp_path: Path):
        db_path = tmp_path / "inventario_nuevo.sqlite3"
        storage = SystemInventoryStorage(db_path)
        try:
            assert storage.initialize(machine_id_actual=MAQUINA) == SCHEMA_VERSION
            assert storage.schema_version() == SCHEMA_VERSION
            conn = storage.connect()
            try:
                tablas = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                assert "calibration_profiles" in tablas
                assert "calibration_controls" in tablas
                indices = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
                assert "idx_calibration_profiles_unique_active" in indices
            finally:
                conn.close()
        finally:
            storage.close()

    def test_store_sobre_base_v5_migra_y_guarda_perfil(self, tmp_path: Path):
        db_path = tmp_path / "inventario_v5.sqlite3"
        self._crear_db_v5(db_path)
        store = CalibrationProfileStore(db_path=db_path, machine_id=MAQUINA)
        try:
            assert store.initialize() is True
            assert store.is_blocked is False
            profile_id = store.save_profile(_profile())
            assert profile_id
            leido = store.get_active_profile(APP, HUELLA)
            assert leido is not None and leido.status == CalibrationState.VALIDADO
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Separacion conocimiento / coordenadas (unidad 3.8.6.8.5)
# ---------------------------------------------------------------------------


class TestSeparacionConocimientoCoordenadas:
    """El catalogo global de entidades nunca almacena datos fisicos ni
    coordenadas; la geometria de calibracion vive solo en SQLite por
    machine_id."""

    _CLAVES_FISICAS_PROHIBIDAS = frozenset({
        "x", "y", "left", "top", "right", "bottom", "center", "client_box",
        "client_box_normalized", "client_box_px", "absolute_cache",
        "screen_number", "monitor", "hwnd", "pid", "rect", "bbox",
        "coordenadas", "coordenada", "pixel", "pixeles", "display_pixel",
    })

    def _rechaza_datos_fisicos(self, objeto, camino="raiz") -> None:
        if isinstance(objeto, dict):
            for clave, valor in objeto.items():
                assert str(clave).lower() not in self._CLAVES_FISICAS_PROHIBIDAS, (
                    f"clave fisica prohibida en {camino}: {clave}"
                )
                self._rechaza_datos_fisicos(valor, f"{camino}.{clave}")
        elif isinstance(objeto, list):
            for indice, valor in enumerate(objeto):
                self._rechaza_datos_fisicos(valor, f"{camino}[{indice}]")

    def test_entities_json_no_contiene_datos_fisicos_ni_coordenadas(self) -> None:
        from src.core.config import get_project_root

        ruta = get_project_root() / "data" / "memory" / "entities.json"
        assert ruta.exists(), f"Falta el catalogo global: {ruta}"
        with ruta.open("r", encoding="utf-8") as f:
            entidades = json.load(f)
        assert isinstance(entidades, list) and len(entidades) >= 1
        for indice, entidad in enumerate(entidades):
            self._rechaza_datos_fisicos(entidad, f"entidades[{indice}]")
