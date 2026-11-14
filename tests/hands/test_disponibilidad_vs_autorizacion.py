# -*- coding: utf-8 -*-
"""Tests de la distincion disponible vs autorizado (unidad 3.8.5.1.4.11.8).

available significa que el destino fue observado y existe/accede en la
maquina/fuente de descubrimiento (SO, PATH, ruta valida, URL). No se confunde
con la autorizacion de ApplicationPreflight (allowlists, bloqueos, login,
recursos, elevacion). Una app puede estar disponible pero no autorizada.

Este test verifica la distincion en el entorno real de Windows usando
notepad.exe (disponible en el SO) y nombres bloqueados por ApplicationPreflight.
No lanza aplicaciones en lote ni ejecuta operaciones destructivas.
"""

from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationKnowledge,
    ApplicationState,
    get_application_manager,
    get_application_preflight,
    is_application_available,
    open_application,
)


def _make_app(name, executable=None, url=None, login_required=False):
    return ApplicationKnowledge(
        name=name,
        type="test_app",
        executable=executable,
        url=url,
        login_required=login_required,
        ui_elements=[],
        states=[ApplicationState.CLOSED],
        metadata={},
    )


def _preflight_base_dict(app):
    return {
        "name": app.name,
        "app_id": "",
        "login_required": app.login_required,
        "logged_in": None,
        "resources_available": None,
        "url": app.url,
    }


class TestDisponibilidadRealEntornoWindows:
    """available se obtiene del SO real (ejecutable en PATH o ruta valida)."""

    def test_notepad_disponible_en_so_real(self):
        """notepad.exe esta disponible en Windows (PATH)."""
        app = _make_app("Notepad", executable="notepad.exe")
        assert app.is_available() is True
        assert is_application_available("Notepad") is True

    def test_ejecutable_inexistente_no_esta_disponible(self):
        """Un ejecutable que no existe no es disponible."""
        app = _make_app("AppInexistente", executable="nonexistent_99999_xyz.exe")
        assert app.is_available() is False

    def test_sin_ejecutable_ni_url_no_esta_disponible(self):
        """Sin ejecutable ni URL, la app no esta disponible."""
        app = _make_app("Vacia", executable=None, url=None)
        assert app.is_available() is False


class TestAutorizacionPreflightEntornoReal:
    """ApplicationPreflight decide la autorizacion, independiente de available."""

    def test_nombre_bloqueado_no_esta_autorizado_incluso_si_disponible(self):
        """Un nombre bloqueado (task scheduler) no se autoriza aunque el
        ejecutable (notepad.exe) exista y la app sea available=True."""
        preflight = get_application_preflight()
        app = _make_app("Task Scheduler", executable="notepad.exe")
        # Disponible: notepad.exe existe en el SO
        assert app.is_available() is True
        # Pero NO autorizado: el nombre esta bloqueado
        resultado = preflight.check(_preflight_base_dict(app))
        assert resultado["allowed"] is False
        assert resultado["blocked_by"] == "blocked_name"
        assert "ambigua" not in resultado["reason"].lower()

    def test_disponible_no_implica_autorizado(self):
        """Contrato central: available=True no implica allowed=True."""
        preflight = get_application_preflight()
        app = _make_app("Registry Editor", executable="notepad.exe")
        assert app.is_available() is True
        resultado = preflight.check(_preflight_base_dict(app))
        assert resultado["allowed"] is False
        assert resultado["blocked_by"] == "blocked_name"


class TestOpenApplicationRespetaDisponibilidadYAutorizacion:
    """open_application combina preflight (autorizacion) y disponibilidad."""

    def test_rechaza_app_no_autorizada_incluso_si_disponible(self):
        """open_application lanza RuntimeError si la app no pasa preflight,
        aunque su ejecutable exista (disponible) pero el nombre este bloqueado."""
        manager = get_application_manager()
        app = _make_app("Task Scheduler", executable="notepad.exe")
        manager.applications["task scheduler"] = app
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ):
            with pytest.raises(RuntimeError) as excinfo:
                open_application("Task Scheduler")
        mensaje = str(excinfo.value).lower()
        assert "preflight" in mensaje
        assert "bloqueado" in mensaje

    def test_rechaza_app_no_disponible(self):
        """open_application lanza RuntimeError si la app no esta disponible."""
        manager = get_application_manager()
        app = _make_app("AppNoDisponible", executable="nonexistent_99999_xyz.exe")
        manager.applications["appnodisponible"] = app
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ):
            with pytest.raises(RuntimeError) as excinfo:
                open_application("AppNoDisponible")
        mensaje = str(excinfo.value).lower()
        assert "disponible" in mensaje


class TestNoLanzamientoEnLote:
    """open_application no lanza aplicaciones en lote (una sola a la vez,
    tras preflight y disponibilidad)."""

    def test_open_application_es_unitaria(self):
        """open_application recibe un solo nombre y gestiona una aplicacion."""
        import inspect

        sig = inspect.signature(open_application)
        assert list(sig.parameters.keys()) == ["app_name"]
