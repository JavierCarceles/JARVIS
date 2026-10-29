# -*- coding: utf-8 -*-
"""Verificación de que un estado desconocido no se convierte en un estado
valido por defecto — hoja 3.4.1.3.

OBJETIVO DE LA HOJA: "Verificar que un estado desconocido no se convierta en
un estado valido por defecto."

RESOLUCIÓN DE 3.4.1.3:

Antes de esta hoja, existe una falla de seguridad de percepción: varios puntos
de la capa `eyes` (screen.py, vision_only.py) usaban
`state_map.get(state_value, ApplicationState.OPEN)`, por lo que un estado
desconocido (p. ej. "unknown", "teleport", "flying") se convertía en
`ApplicationState.OPEN` por defecto. Eso podría inducir al planificador a creer
falsamente que una aplicación está abierta cuando no se puede determinar su
estado real.

Esta hoja verifica que:
1. `vision_only.py` `detect_application_state` resuelve estados desconocidos
   a CLOSED (no OPEN), registrando el estado desconocido.
2. `screen.py` `_convert_visual_world_state` resuelve estados desconocidos
   a CLOSED (no OPEN), registrando el estado desconocido.
3. `ApplicationInfo.from_dict` (screen.py) ya resolvía estados desconocidos
   a CLOSED (comportamiento correcto, verificado).
4. `applications_core.py` `register_custom_application` omite (no lanza) estados
   desconocidos en `states` y `default_state`, registrandolos.

Capas inspeccionadas:
- `src/eyes/screen.py`: `ApplicationState` Enum (5 miembros).
- `src/eyes/vision_only.py`: `detect_application_state`.
- `src/hands/applications_core.py`: `ApplicationState` Enum (8 miembros),
  `register_custom_application`.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.eyes.screen import (
    ApplicationState as ScreenApplicationState,
    ApplicationInfo,
)
from src.hands.applications_core import (
    ApplicationState as HandsApplicationState,
    ApplicationKnowledge,
    ApplicationManager,
    register_custom_application,
    get_application_manager,
)
from src.utils.config import get_project_root


# ---------------------------------------------------------------------------
# 1. vision_only.py — detect_application_state
# ---------------------------------------------------------------------------
class TestVisionOnlyUnknownStateNotOpen:
    """3.4.1.3: un estado desconocido en vision_only no se convierte en OPEN."""

    @pytest.fixture(autouse=True)
    def _patch_ollama(self):
        with patch("src.eyes.vision_only.ollama") as mock_ollama:
            yield mock_ollama

    def _make_vision(self, mock_ollama, state_value):
        mock_ollama.chat.return_value = {
            "message": {"content": json.dumps({"detected": True, "state": state_value})}
        }
        vision = __import__("src.eyes.vision_only", fromlist=["Vision"]).Vision()
        vision.screen_capture = MagicMock()
        vision.screen_capture.capture_monitor = MagicMock(return_value="/fake/img.png")
        return vision

    def test_unknown_state_resolves_to_closed(self, _patch_ollama):
        """'unknown' no debe convertirse en ApplicationState.OPEN."""
        vision = self._make_vision(_patch_ollama, "unknown")
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    def test_garbage_state_resolves_to_closed(self, _patch_ollama):
        """Un string sin significado no debe convertirse en estado valido."""
        vision = self._make_vision(_patch_ollama, "teleportar")
        from src.eyes.screen import ApplicationState
        result = vision.detect_application_state("app")
        assert result.state == ApplicationState.CLOSED

    def test_known_states_still_resolve_correctly(self, _patch_ollama):
        """Estados conocidos deben seguir resolviendose correctamente."""
        from src.eyes.screen import ApplicationState
        for valid_state in ("open", "active", "minimized", "maximized", "closed"):
            vision = self._make_vision(_patch_ollama, valid_state)
            result = vision.detect_application_state("app")
            expected = {
                "open": ApplicationState.OPEN,
                "active": ApplicationState.ACTIVE,
                "minimized": ApplicationState.MINIMIZED,
                "maximized": ApplicationState.MAXIMIZED,
                "closed": ApplicationState.CLOSED,
            }[valid_state]
            assert result.state == expected, f"state '{valid_state}' deberia resolver a {expected}"


# ---------------------------------------------------------------------------
# 2. screen.py — ApplicationInfo.from_dict (ya corregido, se verifica)
# ---------------------------------------------------------------------------
class TestApplicationInfoFromDictUnknownState:
    """3.4.1.3: ApplicationInfo.from_dict ya resolvia estados desconocidos a
    CLOSED (no OPEN). Se verifica que el comportamiento sea correcto."""

    def test_unknown_state_from_dict_defaults_closed(self):
        info = ApplicationInfo.from_dict({"name": "app", "state": "weird"})
        assert info.state == ScreenApplicationState.CLOSED

    def test_missing_state_from_dict_defaults_closed(self):
        info = ApplicationInfo.from_dict({"name": "app"})
        assert info.state == ScreenApplicationState.CLOSED

    def test_none_input_defaults_closed(self):
        info = ApplicationInfo.from_dict(None)
        assert info.state == ScreenApplicationState.CLOSED

    def test_empty_dict_defaults_closed(self):
        info = ApplicationInfo.from_dict({})
        assert info.state == ScreenApplicationState.CLOSED

    def test_valid_states_roundtrip(self):
        """Estados validos se preservan correctamente en from_dict/to_dict."""
        for valid in ("closed", "open", "active", "minimized", "maximized"):
            original = ApplicationInfo(name="app", state=ScreenApplicationState(valid))
            restored = ApplicationInfo.from_dict(original.to_dict())
            assert restored.state == original.state


# ---------------------------------------------------------------------------
# 3. screen.py — _convert_visual_world_state (corregido)
# ---------------------------------------------------------------------------
class TestConvertVisualWorldStateUnknownState:
    """3.4.1.3: _convert_visual_world_state resuelve estados desconocidos a
    CLOSED en lugar de OPEN."""

    def test_unknown_state_in_visual_to_world_state(self):
        """Un estado 'unknown' en los datos visuales debe convertirse en CLOSED,
        no en OPEN."""
        from src.eyes.screen import ScreenAnalyzer, WorldState

        analyzer = ScreenAnalyzer()

        # Construimos un visual_state simple con mock
        visual_state = MagicMock()
        visual_state.applications = {
            "fakapp": {
                "name": "FakeApp",
                "detected": True,
                "state": "unknown_state",
            }
        }
        visual_state.system_info = {}

        world_state = analyzer._convert_visual_world_state(visual_state, [1], 0.0)

        assert "fakapp" in world_state.applications
        assert world_state.applications["fakapp"].state == ScreenApplicationState.CLOSED

    def test_garbage_state_in_visual_to_world_state(self):
        """Un estado completamente invalido tambien debe resolver a CLOSED."""
        from src.eyes.screen import ScreenAnalyzer

        analyzer = ScreenAnalyzer()

        visual_state = MagicMock()
        visual_state.applications = {
            "badapp": {
                "name": "BadApp",
                "detected": True,
                "state": "this_is_not_a_real_state",
            }
        }
        visual_state.system_info = {}

        world_state = analyzer._convert_visual_world_state(visual_state, [1], 0.0)

        assert "badapp" in world_state.applications
        assert world_state.applications["badapp"].state == ScreenApplicationState.CLOSED

    def test_known_state_preserves_correct_value(self):
        """Estados conocidos deben resolverse al enum correcto."""
        from src.eyes.screen import ScreenAnalyzer

        analyzer = ScreenAnalyzer()

        visual_state = MagicMock()
        visual_state.applications = {
            "goodapp": {
                "name": "GoodApp",
                "detected": True,
                "state": "maximized",
            }
        }
        visual_state.system_info = {}

        world_state = analyzer._convert_visual_world_state(visual_state, [1], 0.0)

        assert world_state.applications["goodapp"].state == ScreenApplicationState.MAXIMIZED


# ---------------------------------------------------------------------------
# 4. applications_core.py — register_custom_application (corregido)
# ---------------------------------------------------------------------------
class TestRegisterCustomApplicationUnknownStates:
    """3.4.1.3: register_custom_application omite (no lanza) estados
    desconocidos en 'states' y 'default_state', registrandolos."""

    def test_register_with_unknown_state_omits_it(self):
        """Un estado desconocido en 'states' debe omitirse, no causar crash."""
        config = {
            "name": "UnknownStateApp",
            "type": "utility",
            "states": ["open", "invalid_state_xyz", "active"],
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("UnknownStateApp")
        assert app is not None
        # El estado desconocido se omite; los validos se conservan.
        state_values = [s.value for s in app.states]
        assert "invalid_state_xyz" not in state_values
        assert "open" in state_values
        assert "active" in state_values

    def test_register_with_only_unknown_states_uses_default(self):
        """Si todos los estados son desconocidos, se usa el default CLOSED."""
        config = {
            "name": "AllUnknownStatesApp",
            "type": "utility",
            "states": ["completely_invalid", "nonsense"],
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("AllUnknownStatesApp")
        assert app is not None
        # Todos eran invalidos → se omite todo → no hay estados agregados
        # (el default CLOSED se aplica en __post_init__ si states es []).
        assert app.states == [] or app.states == [HandsApplicationState.CLOSED]

    def test_register_with_unknown_default_state_uses_closed(self):
        """Un default_state desconocido no debe causar crash; se usa CLOSED."""
        config = {
            "name": "UnknownDefaultApp",
            "type": "utility",
            "default_state": "impossible_state",
        }
        result = register_custom_application(config)
        assert result is True

        app = get_application_manager().get_application("UnknownDefaultApp")
        assert app is not None
        # Si default_state era invalido, el valor por defecto de ApplicationKnowledge
        # es CLOSED (no se establece un estado invalido).
        assert app.default_state == HandsApplicationState.CLOSED


# ---------------------------------------------------------------------------
# 5. Verificacion de regresion: estados validos siguen funcionando
# ---------------------------------------------------------------------------
class TestUnknownStateRegression:
    """Verifica que los cambios de 3.4.1.3 no rompen estados validos."""

    def test_hands_application_state_valid_values(self):
        """Verifica que todos los valores del Enum de applications_core son
        aceptados por ApplicationState()."""
        for member in HandsApplicationState:
            app_state = HandsApplicationState(member.value)
            assert app_state == member

    def test_screen_application_state_valid_values(self):
        """Verifica que todos los valores del Enum de screen son aceptados."""
        for member in ScreenApplicationState:
            try:
                ScreenApplicationState(member.value)
            except ValueError:
                pytest.fail(f"ScreenApplicationState({member.value!r}) no deberia fallar")
