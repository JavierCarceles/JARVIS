# -*- coding: utf-8 -*-
"""Tests para la comparación de estado declarado vs. estado observable — hoja 3.4.3.1.

OBJETIVO DE LA HOJA: "Comparar estado declarado con estado observable."

RESOLUCIÓN DE 3.4.3.1: se añaden dos funciones a ``src/eyes/screen.py``:

1. ``observable_state_to_flags(state)`` — convierte un ``ApplicationState``
   observable (producido por la capa Vision) a las 4 flags genéricas
   booleanas canónicas ``{open, active, maximized, focused}`` que el modelo
   declarado utiliza.

2. ``compare_declared_and_observable_state(declared, observable_state)`` —
   compara el diccionario de flags declaradas (de ``applications.json`` o de
   ``Executor.current_state.application_states``) con el estado observable,
   reportando coincidencias o discrepancias flag a flag.

Los tests verifican el comportamiento REAL de ambas funciones sin mocks de
lógica de negocio.
"""

import pytest

from src.eyes.screen import (
    ApplicationState,
    CANONICAL_WINDOW_FLAGS,
    APPLICATION_STATE_TO_WINDOW_FLAGS,
    observable_state_to_flags,
    compare_declared_and_observable_state,
    reconcile_observable_with_declared_state,
)


# ---------------------------------------------------------------------------
# EXPECTATIVAS CANÓNICAS: mapping ApplicationState -> flags genéricas
# ---------------------------------------------------------------------------

EXPECTED_FLAGS = {
    ApplicationState.CLOSED: {"open": False, "active": False, "maximized": False, "focused": False},
    ApplicationState.OPEN: {"open": True, "active": False, "maximized": False, "focused": False},
    ApplicationState.MINIMIZED: {"open": True, "active": False, "maximized": False, "focused": False},
    ApplicationState.ACTIVE: {"open": True, "active": True, "maximized": False, "focused": True},
    ApplicationState.MAXIMIZED: {"open": True, "active": True, "maximized": True, "focused": True},
}


class TestCanonicalWindowFlagsConstant:
    """La constante CANONICAL_WINDOW_FLAGS define exactamente las 4 flags genericas."""

    def test_has_exactly_four_flags(self):
        assert len(CANONICAL_WINDOW_FLAGS) == 4

    def test_flags_are_the_documented_set(self):
        assert set(CANONICAL_WINDOW_FLAGS) == {"open", "active", "maximized", "focused"}

    def test_application_state_to_window_flags_covers_all_states(self):
        """El mapping cubre todos los valores del enum ApplicationState."""
        assert set(APPLICATION_STATE_TO_WINDOW_FLAGS.keys()) == set(ApplicationState)


class TestObservableStateToFlags:
    """``observable_state_to_flags`` mapea cada ApplicationState a las flags canonicas."""

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_returns_all_four_canonical_flags(self, state):
        flags = observable_state_to_flags(state)
        assert set(flags.keys()) == set(CANONICAL_WINDOW_FLAGS)

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_all_values_are_boolean(self, state):
        flags = observable_state_to_flags(state)
        for flag in CANONICAL_WINDOW_FLAGS:
            assert isinstance(flags[flag], bool), f"{state}.{flag} no es booleano"

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_matches_expected_mapping(self, state):
        assert observable_state_to_flags(state) == EXPECTED_FLAGS[state]

    def test_closed_all_false(self):
        flags = observable_state_to_flags(ApplicationState.CLOSED)
        assert flags == {"open": False, "active": False, "maximized": False, "focused": False}

    def test_active_implies_active_flag(self):
        flags = observable_state_to_flags(ApplicationState.ACTIVE)
        assert flags["open"] is True
        assert flags["active"] is True
        assert flags["focused"] is True
        assert flags["maximized"] is False

    def test_maximized_implies_maximized_and_active(self):
        flags = observable_state_to_flags(ApplicationState.MAXIMIZED)
        assert flags["open"] is True
        assert flags["active"] is True
        assert flags["maximized"] is True
        assert flags["focused"] is True

    def test_minimized_open_true_rest_false(self):
        flags = observable_state_to_flags(ApplicationState.MINIMIZED)
        assert flags == {"open": True, "active": False, "maximized": False, "focused": False}

    def test_returns_copy_not_shared_reference(self):
        """La función no debe retornar una referencia al dict interno del mapping."""
        flags1 = observable_state_to_flags(ApplicationState.ACTIVE)
        flags2 = observable_state_to_flags(ApplicationState.ACTIVE)
        assert flags1 == flags2
        flags1["open"] = False
        assert flags2["open"] is True


class TestCompareDeclaredAndObservable:
    """``compare_declared_and_observable_state`` reporta coincidencias y discrepancias."""

    # --- Casos de coincidencia perfecta ---

    def test_exact_match_closed(self):
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.CLOSED)
        assert result["match"] is True
        assert result["discrepancies"] == {}
        assert result["observable_state"] == ApplicationState.CLOSED

    def test_exact_match_open(self):
        declared = {"open": True, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.OPEN)
        assert result["match"] is True
        assert result["discrepancies"] == {}

    def test_exact_match_active(self):
        declared = {"open": True, "active": True, "maximized": False, "focused": True}
        result = compare_declared_and_observable_state(declared, ApplicationState.ACTIVE)
        assert result["match"] is True
        assert result["discrepancies"] == {}

    def test_exact_match_maximized(self):
        declared = {"open": True, "active": True, "maximized": True, "focused": True}
        result = compare_declared_and_observable_state(declared, ApplicationState.MAXIMIZED)
        assert result["match"] is True
        assert result["discrepancies"] == {}

    def test_exact_match_minimized(self):
        declared = {"open": True, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.MINIMIZED)
        assert result["match"] is True
        assert result["discrepancies"] == {}

    def test_match_with_domain_flags_ignored(self):
        """Flags de dominio (playing, streaming, recording) no afectan el match."""
        declared = {
            "open": False, "active": False, "maximized": False, "focused": False,
            "playing": True,
        }
        result = compare_declared_and_observable_state(declared, ApplicationState.CLOSED)
        assert result["match"] is True
        assert result["discrepancies"] == {}

    # --- Casos de discrepancia ---

    def test_discrepancy_open_flag(self):
        """Declared dice cerrado (open=False) pero vision ve OPEN (open=True)."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.OPEN)
        assert result["match"] is False
        assert "open" in result["discrepancies"]
        assert result["discrepancies"]["open"] == {"declared": False, "observable": True}
        assert "active" not in result["discrepancies"]

    def test_discrepancy_active_flag(self):
        """Declared tiene active=False pero vision ve ACTIVE (active=True)."""
        declared = {"open": True, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.ACTIVE)
        assert result["match"] is False
        assert "active" in result["discrepancies"]
        assert result["discrepancies"]["active"] == {"declared": False, "observable": True}
        assert "focused" in result["discrepancies"]
        assert result["discrepancies"]["focused"] == {"declared": False, "observable": True}

    def test_discrepancy_maximized_flag(self):
        """Declared no tiene maximized=True pero vision ve MAXIMIZED."""
        declared = {"open": True, "active": True, "maximized": False, "focused": True}
        result = compare_declared_and_observable_state(declared, ApplicationState.MAXIMIZED)
        assert result["match"] is False
        assert "maximized" in result["discrepancies"]
        assert result["discrepancies"]["maximized"] == {"declared": False, "observable": True}

    def test_multiple_discrepancies(self):
        """Varias flags discrepantes a la vez."""
        declared = {"open": True, "active": True, "maximized": True, "focused": True}
        result = compare_declared_and_observable_state(declared, ApplicationState.CLOSED)
        assert result["match"] is False
        assert set(result["discrepancies"].keys()) == {"open", "active", "maximized", "focused"}
        for flag in CANONICAL_WINDOW_FLAGS:
            assert result["discrepancies"][flag] == {"declared": True, "observable": False}

    def test_discrepancy_focused_flag(self):
        """Declared tiene focused=False pero vision ve ACTIVE (focused=True)."""
        declared = {"open": True, "active": True, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.ACTIVE)
        assert result["match"] is False
        assert "focused" in result["discrepancies"]
        assert result["discrepancies"]["focused"] == {"declared": False, "observable": True}

    # --- Casos edge ---

    def test_empty_declared_dict_all_assumed_false(self):
        """Si el diccionario declarado está vacío, todas las flags se asumen False."""
        result = compare_declared_and_observable_state({}, ApplicationState.CLOSED)
        assert result["match"] is True
        assert result["declared_flags"] == {"open": False, "active": False, "maximized": False, "focused": False}

    def test_empty_declared_dict_vs_open_all_discrepant(self):
        result = compare_declared_and_observable_state({}, ApplicationState.OPEN)
        assert result["match"] is False
        assert set(result["discrepancies"].keys()) == {"open"}
        assert result["discrepancies"]["open"] == {"declared": False, "observable": True}

    def test_missing_canonical_flag_assumed_false(self):
        """Una flag canónica faltante en declared se asume False."""
        declared = {"open": True, "active": False, "maximized": False}
        # 'focused' falta → se asume False; OPEN no requiere focused=True
        result = compare_declared_and_observable_state(declared, ApplicationState.OPEN)
        assert result["match"] is True
        assert result["declared_flags"]["focused"] is False

    def test_missing_flag_vs_state_requiring_it(self):
        """Si falta una flag y el estado observable la requiere en True, hay discrepancia."""
        declared = {"open": True, "active": False, "maximized": False}  # falta focused
        result = compare_declared_and_observable_state(declared, ApplicationState.ACTIVE)
        assert result["match"] is False
        assert "focused" in result["discrepancies"]

    def test_non_boolean_values_coerced_to_bool(self):
        """Valores no booleanos en declared se convierten con bool()."""
        declared = {"open": 1, "active": 0, "maximized": None, "focused": ""}
        result = compare_declared_and_observable_state(declared, ApplicationState.OPEN)
        # OPEN: open=True, rest False
        # declared: open=bool(1)=True, active=bool(0)=False, maximized=bool(None)=False, focused=bool("")=False
        assert result["match"] is True
        assert result["declared_flags"] == {"open": True, "active": False, "maximized": False, "focused": False}

    def test_result_structura_con_campos_requeridos(self):
        """El resultado siempre contiene las 5 claves requeridas."""
        result = compare_declared_and_observable_state(
            {"open": True, "active": False, "maximized": False, "focused": False},
            ApplicationState.OPEN,
        )
        assert set(result.keys()) == {"match", "observable_state", "observable_flags", "declared_flags", "discrepancies"}

    def test_observable_flags_en_resultado(self):
        """El resultado incluye las flags derivadas del estado observable."""
        result = compare_declared_and_observable_state({}, ApplicationState.MAXIMIZED)
        assert result["observable_flags"] == EXPECTED_FLAGS[ApplicationState.MAXIMIZED]

    def test_declared_flags_solo_canonical(self):
        """declared_flags en el resultado solo contiene las 4 flags canónicas."""
        declared = {
            "open": True, "active": True, "maximized": True, "focused": True,
            "playing": True, "streaming": True, "recording": True,
        }
        result = compare_declared_and_observable_state(declared, ApplicationState.MAXIMIZED)
        assert set(result["declared_flags"].keys()) == set(CANONICAL_WINDOW_FLAGS)
        assert result["match"] is True


class TestCompareWithApplicationsJsonModel:
    """Verifica el comportamiento contra el modelo real de applications.json."""

    KNOWN_APPS = ("chrome", "spotify", "vscode", "obs_studio")

    def _load_app_states(self, app_key):
        import json
        from src.utils.config import get_project_root
        path = get_project_root() / "data" / "knowledge" / "applications.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[app_key]["states"]

    @pytest.mark.parametrize("app_key", KNOWN_APPS)
    def test_all_apps_start_with_all_false_flags(self, app_key):
        """Las aplicaciones conocidas inicialmente declaran todas las flags a False (CLOSED)."""
        states = self._load_app_states(app_key)
        result = compare_declared_and_observable_state(states, ApplicationState.CLOSED)
        assert result["match"] is True

    @pytest.mark.parametrize("app_key", KNOWN_APPS)
    def test_domain_flags_do_not_break_closed_match(self, app_key):
        """Las flags de dominio coexistiendo no rompen el match con CLOSED."""
        states = self._load_app_states(app_key)
        result = compare_declared_and_observable_state(states, ApplicationState.CLOSED)
        assert result["match"] is True
        assert result["discrepancies"] == {}


class TestReconcileObservableWithDeclared:
    """``reconcile_observable_with_declared_state`` resuelve discrepancias priorizando la visión."""

    # --- Sin discrepancia: no hay reconciliación ---

    def test_match_true_returns_reconciled_false(self):
        """Si match es True, reconciled=False y las flags no cambian."""
        declared = {"open": True, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        assert result["match"] is True
        assert result["reconciled"] is False
        assert result["reconciled_flags"] == declared
        assert result["discrepancies"] == {}

    def test_match_true_preserves_domain_flags(self):
        """Flags de dominio se conservan cuando no hay discrepancia."""
        declared = {
            "open": True, "active": False, "maximized": False, "focused": False,
            "playing": True, "streaming": False,
        }
        result = reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        assert result["match"] is True
        assert result["reconciled_flags"]["playing"] is True
        assert result["reconciled_flags"]["streaming"] is False

    def test_original_declared_not_mutated_on_match(self):
        """El diccionario declarado original no se muta aunque match sea True."""
        declared = {"open": True, "active": False, "maximized": False, "focused": False}
        original = dict(declared)
        reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        assert declared == original

    # --- Con discrepancia: reconciliación aplica flags observables ---

    def test_reconciled_true_when_discrepancy(self):
        """Si hay discrepancia, reconciled=True."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        assert result["match"] is False
        assert result["reconciled"] is True

    def test_reconciled_flags_update_canonical_to_observable(self):
        """Las 4 flags canónicas se actualizan al estado observable."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.ACTIVE)
        # ACTIVE -> open=True, active=True, maximized=False, focused=True
        assert result["reconciled_flags"]["open"] is True
        assert result["reconciled_flags"]["active"] is True
        assert result["reconciled_flags"]["maximized"] is False
        assert result["reconciled_flags"]["focused"] is True

    def test_reconciled_preserves_domain_flags(self):
        """Flags de dominio se conservan intactas durante la reconciliación."""
        declared = {
            "open": False, "active": False, "maximized": False, "focused": False,
            "playing": True, "streaming": True, "recording": False,
        }
        result = reconcile_observable_with_declared_state(declared, ApplicationState.ACTIVE)
        assert result["reconciled_flags"]["playing"] is True
        assert result["reconciled_flags"]["streaming"] is True
        assert result["reconciled_flags"]["recording"] is False

    def test_reconciled_preserves_other_keys(self):
        """Claves no canónicas no estándar se conservan."""
        declared = {
            "open": False, "active": False, "maximized": False, "focused": False,
            "custom_field": "value", "another": 123,
        }
        result = reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        assert result["reconciled_flags"]["custom_field"] == "value"
        assert result["reconciled_flags"]["another"] == 123

    def test_original_declared_not_mutated_on_reconcile(self):
        """El diccionario declarado original no se muta durante reconciliación."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        original = dict(declared)
        reconcile_observable_with_declared_state(declared, ApplicationState.MAXIMIZED)
        assert declared == original

    def test_reconciled_flags_is_new_dict(self):
        """reconciled_flags es un dict nuevo, no referencia al original."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        assert result["reconciled_flags"] is not declared
        result["reconciled_flags"]["open"] = False
        assert declared["open"] is False  # original intacto

    # --- Discrepancias reportadas ---

    def test_discrepancies_included_in_result(self):
        """El resultado incluye el detalle de discrepancias flag a flag."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.ACTIVE)
        # ACTIVE requiere open=True, active=True, focused=True
        assert "open" in result["discrepancies"]
        assert result["discrepancies"]["open"] == {"declared": False, "observable": True}
        assert "active" in result["discrepancies"]
        assert result["discrepancies"]["active"] == {"declared": False, "observable": True}
        assert "focused" in result["discrepancies"]
        assert result["discrepancies"]["focused"] == {"declared": False, "observable": True}
        assert "maximized" not in result["discrepancies"]

    def test_all_five_keys_in_result(self):
        """El resultado siempre contiene las 7 claves requeridas."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.OPEN)
        expected_keys = {
            "match", "observable_state", "observable_flags",
            "declared_flags", "reconciled_flags", "discrepancies", "reconciled"
        }
        assert set(result.keys()) == expected_keys

    def test_observable_state_preserved(self):
        """El estado observable original se incluye en el resultado."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.MAXIMIZED)
        assert result["observable_state"] == ApplicationState.MAXIMIZED

    def test_declared_flags_reflects_pre_reconcile_state(self):
        """declared_flags muestra el estado ANTES de la reconciliación."""
        declared = {"open": False, "active": True, "maximized": False, "focused": False}
        result = reconcile_observable_with_declared_state(declared, ApplicationState.MAXIMIZED)
        # declared_flags es lo que había antes: active=True, resto False
        assert result["declared_flags"]["open"] is False
        assert result["declared_flags"]["active"] is True
        assert result["declared_flags"]["maximized"] is False
        assert result["declared_flags"]["focused"] is False
        # reconciled_flags refleja MAXIMIZED
        assert result["reconciled_flags"]["open"] is True
        assert result["reconciled_flags"]["active"] is True
        assert result["reconciled_flags"]["maximized"] is True
        assert result["reconciled_flags"]["focused"] is True

    # --- Edge cases ---

    def test_empty_declared_dict_reconciles_to_observable(self):
        """Diccionario vacío se reconcilia completamente al observable."""
        result = reconcile_observable_with_declared_state({}, ApplicationState.CLOSED)
        assert result["match"] is True
        assert result["reconciled"] is False
        assert result["reconciled_flags"] == {
            "open": False, "active": False, "maximized": False, "focused": False
        }

    def test_missing_canonical_flags_assumed_false_then_reconciled(self):
        """Flags canónicas faltantes se asumen False y luego se actualizan si observables difieren."""
        declared = {"open": True}  # solo open, resto faltan -> False
        result = reconcile_observable_with_declared_state(declared, ApplicationState.ACTIVE)
        # declared_flags: open=True, active=False, maximized=False, focused=False
        assert result["declared_flags"]["open"] is True
        assert result["declared_flags"]["active"] is False
        # reconciled_flags: ACTIVE
        assert result["reconciled_flags"]["open"] is True
        assert result["reconciled_flags"]["active"] is True
        assert result["reconciled_flags"]["focused"] is True
