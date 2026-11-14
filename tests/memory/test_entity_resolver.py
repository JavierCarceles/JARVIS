# -*- coding: utf-8 -*-
"""
Pruebas unitarias de `src.memory.entity_resolver.EntityResolver` con la
integración del catálogo global de aplicaciones (unidad 3.8.5.1.4.11.7).

Objetivo verificable:
- `resolve_entity` consulta el catálogo global
  (`ApplicationManager` / `entities.json`) PRIMERO para obtener la identidad,
  nombres y aliases de una aplicación, antes de buscar en la memoria de dominio.
- Cuando no hay aplicación registrada en el catálogo, se conserva el
  comportamiento habitual de búsqueda en entidades de memoria.
- Nunca se incorporan rutas absolutas como base de la identidad de la entidad.

Trabaja SIEMPRE sobre directorios temporales (tmp_path). No escribe ni
modifica el `data/memory/entities.json` real del repositorio. No lanza
aplicaciones ni abre ventanas.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.memory.entity_resolver import EntityResolver, ResolutionContext
from src.memory.storage import Entity, MemoryManager
from src.hands.applications_core import ApplicationKnowledge, ApplicationState


def _nueva_entidad_memoria(entity_id: str, nombre: str, tipo: str) -> Entity:
    return Entity(
        id=entity_id,
        type=tipo,
        name=nombre,
        properties={},
        aliases=[],
        tags=[],
        confidence=1.0,
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )


def _app_conocimiento(nombre: str = "Chrome", tipo: str = "browser") -> ApplicationKnowledge:
    app = ApplicationKnowledge(name=nombre, type=tipo)
    app.metadata = {"aliases": [f"{nombre.lower()} alias"]}
    return app


class TestEntityResolverCatalogoGlobalPrimero:
    """`resolve_entity` consulta el catálogo global (ApplicationManager) antes
    que la memoria de dominio para referencias de aplicación."""

    def _resolver_con_app_manager(self, tmp_path, app_conocimiento=None):
        memoria_dir = tmp_path / "memory"
        mm = MemoryManager(str(memoria_dir))
        app_manager = MagicMock()
        app_manager.memory_manager = mm
        if app_conocimiento is not None:
            app_manager.get_application.return_value = app_conocimiento
        else:
            app_manager.get_application.return_value = None
        return EntityResolver(memory_manager=mm, app_manager=app_manager), mm, app_manager

    def test_resolve_entity_aplicacion_resuelve_catalogo_global_primero(self, tmp_path):
        """Referencia de aplicación: se resuelve desde el catálogo global con
        método catalogo_global_aplicacion y confianza 1.0."""
        resolver, _, app_manager = self._resolver_con_app_manager(
            tmp_path, _app_conocimiento("Chrome", "browser")
        )

        resultado = resolver.resolve_entity("google chrome", entity_type="application")

        assert resultado.entity is not None
        assert resultado.entity.name == "Chrome"
        assert resultado.entity.type == "application"
        assert resultado.confidence == 1.0
        assert resultado.resolution_method == "catalogo_global_aplicacion"
        assert resultado.alternatives == []
        # El catálogo global fue consultado con la referencia normalizada.
        app_manager.get_application.assert_called()
        # La identidad es estable (`app_<clave normalizada>`) y no incorpora
        # la ruta del ejecutable.
        assert resultado.entity.id == "app_chrome"
        assert "system32" not in resultado.entity.id
        assert "windows" not in resultado.entity.id
        # Los aliases del catálogo global se conservan en la entidad.
        assert "chrome alias" in resultado.entity.aliases

    def test_resolve_entity_sin_tipo_declarado_con_app_consulta_catalogo(self, tmp_path):
        """Sin entity_type declarado, una referencia de aplicación conocida en
        el catálogo global se resuelve desde ahí primero."""
        resolver, _, app_manager = self._resolver_con_app_manager(
            tmp_path, _app_conocimiento("Spotify", "media")
        )

        resultado = resolver.resolve_entity("spotify")

        assert resultado.entity is not None
        assert resultado.entity.name == "Spotify"
        assert resultado.resolution_method == "catalogo_global_aplicacion"
        app_manager.get_application.assert_called()

    def test_resolve_entity_no_app_en_catalogo_usa_memoria_de_dominio(self, tmp_path):
        """No hay aplicación en el catálogo: se conserva la búsqueda en la
        memoria de dominio (no regresión)."""
        memoria_dir = tmp_path / "memory"
        mm = MemoryManager(str(memoria_dir))
        mm.save_entity(_nueva_entidad_memoria("nissaxter", "Nissaxter", "streamer"))

        app_manager = MagicMock()
        app_manager.memory_manager = mm
        app_manager.get_application.return_value = None  # no app en catálogo

        resolver = EntityResolver(memory_manager=mm, app_manager=app_manager)
        resultado = resolver.resolve_entity("nissaxter", entity_type=None)

        assert resultado.entity is not None
        assert resultado.entity.name == "Nissaxter"
        assert resultado.entity.type == "streamer"
        assert resultado.resolution_method != "catalogo_global_aplicacion"
        # El catálogo se consultó (entity_type None) y devolvió None, por lo
        # que se siguió con la búsqueda en memoria de dominio.
        app_manager.get_application.assert_called()

    def test_resolve_entity_app_no_en_catalogo_ni_memoria_entidad_temporal(self, tmp_path):
        """No hay aplicación en catálogo ni entidad en memoria: entidad temporal
        con confianza reducida, sin fallar."""
        resolver, _, app_manager = self._resolver_con_app_manager(tmp_path, None)

        resultado = resolver.resolve_entity("AppQueNoExisteEnCatalogoXYZ", entity_type="application")

        assert resultado.entity is not None
        assert resultado.entity.name == "appquenoexisteencatalogoxyz"
        assert resultado.confidence == 0.5
        assert resultado.resolution_method == "temporary_creation"
        app_manager.get_application.assert_called()

    def test_resolver_funciona_sin_app_manager_inyectado(self, tmp_path):
        """Por defecto se obtiene el ApplicationManager real (singleton) y el
        resolutor se construye sin error."""
        resolver = EntityResolver(memory_manager=MemoryManager(str(tmp_path / "memory")))
        # La resolución perezosa obtiene el ApplicationManager real al usarlo.
        ctx = ResolutionContext([], None, [], {}, {})
        resultado = resolver.resolve_entity("cualquier cosa", context=ctx)
        assert resolver.app_manager is not None
        assert resultado.entity is not None


class TestEntityResolverInicializacion:
    def test_acepta_app_manager_inyectado(self, tmp_path):
        mm = MemoryManager(str(tmp_path / "memory"))
        app_manager = MagicMock()
        resolver = EntityResolver(memory_manager=mm, app_manager=app_manager)
        assert resolver.app_manager is app_manager
        assert resolver.memory_manager is mm
