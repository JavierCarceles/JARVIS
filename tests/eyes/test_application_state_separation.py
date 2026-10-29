# -*- coding: utf-8 -*-
"""Verificación de separación de estados de ventana en
data/knowledge/applications.json — hoja 3.4.1.2.

OBJETIVO DE LA HOJA: "Separar open, active, maximized, focused cuando
correspondan."

RESOLUCIÓN DE 3.4.1.2: las flags genéricas de estado de ventana
{open, active, maximized, focused} deben estar presentes como booleans
INDEPENDIENTES (separados, no confundidos ni omitidos) en cada aplicación
para la que correspondan. Estas flags describen el estado de la ventana
independientemente de su dominio (navegador, reproductor, editor...).

Antes de 3.4.1.2, `active` aparecía SOLO para chrome (ausente en spotify,
vscode, obs_studio) y `focused` ausente en obs_studio: el modelo de datos
no separaba `active`/`focused` de `open` de forma coherente. 3.4.1.2
normaliza las flags genéricas para que coexistan como booleans separados en
todas las aplicaciones, distinguiéndolas de las flags de dominio
(específicas: playing, streaming, recording).

Las flags de dominio permanecen separadas: playing (spotify),
streaming/recording (obs_studio). chrome y vscode no tienen flags de
dominio.

Este test no modifica código de producción; verifica el modelo de datos
canónico resultante de la separación.
"""

import json

import pytest

from src.utils.config import get_project_root

APPS_JSON_PATH = get_project_root() / "data" / "knowledge" / "applications.json"

# Flags genéricas de estado de ventana, separadas e independientes.
CANONICAL_WINDOW_FLAGS = ("open", "active", "maximized", "focused")
# Flags de dominio (específicas de aplicación), separadas de las genericas.
DOMAIN_FLAGS = {"playing", "streaming", "recording"}
KNOWN_APPS = ("chrome", "spotify", "vscode", "obs_studio")


def _load_apps():
    return json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def apps_data():
    return _load_apps()


class TestCanonicalWindowFlagsSeparated:
    """Las 4 flags genericas {open, active, maximized, focused} estan
    presentes y separadas en toda aplicacion conocida."""

    def test_each_known_app_has_canonical_window_flags(self, apps_data):
        """Cada app conoce las 4 flags genericas como keys independientes."""
        for app_key in KNOWN_APPS:
            states = apps_data[app_key]["states"]
            keys = set(states.keys())
            missing = set(CANONICAL_WINDOW_FLAGS) - keys
            assert not missing, f"{app_key} le falta la flag {missing}"

    def test_canonical_flags_are_distinct_keys(self, apps_data):
        """Las 4 flags genericas no colisionan ni se fusionan en una sola key."""
        for app_key in KNOWN_APPS:
            keys = list(apps_data[app_key]["states"].keys())
            canonical = [k for k in keys if k in set(CANONICAL_WINDOW_FLAGS)]
            # Son 4 keys distintas (no fusionadas ni duplicadas).
            assert len(set(canonical)) == len(CANONICAL_WINDOW_FLAGS)

    def test_canonical_flags_are_boolean_and_independent(self, apps_data):
        """Cada flag canonica es un booleano independiente (separado de `open`).

        La separacion significa que `active` no se deduce de `open`: existe
        como key propia con valor bool, no implicado ni confundido.
        """
        for app_key in KNOWN_APPS:
            states = apps_data[app_key]["states"]
            for flag in CANONICAL_WINDOW_FLAGS:
                assert flag in states, f"{app_key} no separa '{flag}'"
                assert isinstance(states[flag], bool), f"{app_key}.{flag} no es bool"

    def test_active_exists_as_separate_flag_for_non_chrome_apps(self, apps_data):
        """`active` (foreground window) corresponde a toda app con ventana: ya
        no se confunde con `open`/ausente."""
        for app_key in ("spotify", "vscode", "obs_studio"):
            assert "active" in apps_data[app_key]["states"]

    def test_focused_exists_as_separate_flag_for_obs(self, apps_data):
        """`focused` (teclado encima de la ventana) corresponde a obs_studio."""
        assert "focused" in apps_data["obs_studio"]["states"]


class TestDomainFlagsRemainSeparated:
    """Las flags de dominio se mantienen separadas de las genericas."""

    def test_spotify_only_has_playing_as_domain_flag(self, apps_data):
        domain = set(apps_data["spotify"]["states"]) - set(CANONICAL_WINDOW_FLAGS)
        assert domain == {"playing"}

    def test_obs_only_has_streaming_recording_as_domain_flags(self, apps_data):
        domain = set(apps_data["obs_studio"]["states"]) - set(CANONICAL_WINDOW_FLAGS)
        assert domain == {"streaming", "recording"}

    def test_chrome_and_vscode_have_no_domain_flags(self, apps_data):
        for app_key in ("chrome", "vscode"):
            domain = set(apps_data[app_key]["states"]) - set(CANONICAL_WINDOW_FLAGS)
            assert domain == set(), f"{app_key} no deberia tener flags de dominio"


class TestCanonicalFlagsIntersectionAcrossApps:
    """Las 4 flags genericas son el conjunto canonico comun a todas las apps."""

    def test_canonical_union_is_exactly_the_documented_set(self, apps_data):
        union = set()
        for app_data in apps_data.values():
            union.update(app_data["states"].keys())
        assert union == set(CANONICAL_WINDOW_FLAGS) | DOMAIN_FLAGS

    def test_canonical_flags_common_to_all_apps(self, apps_data):
        common = set(CANONICAL_WINDOW_FLAGS)
        for app_data in apps_data.values():
            common &= set(app_data["states"].keys())
        assert common == set(CANONICAL_WINDOW_FLAGS)
