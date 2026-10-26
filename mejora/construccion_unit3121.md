# Construcción — Unidad 3.1.2.1
# Definir qué identifica univocamente una aplicación

## Estado
- **Fase**: 3.1.2 (Contrato mínimo)
- **Unidad**: 3.1.2.1
- **Tipo de trabajo**: DEFINICIÓN / VERIFICACIÓN / TEST

## Resumen

Esta unidad **define** el contrato mínimo de identificación de aplicaciones. No implica
modificaciones de código de producción: el modelo actual ya identifica aplicaciones por
`ApplicationKnowledge.name` (lowercased). La unidad documenta esa definición, escribe tests
que la verifican y registra las discrepancias que 3.1.2.2 y 3.1.3 resolverán.

## Definición del identificador único

| Capa | Campo/Clave | Código |
|------|------------|--------|
| Modelo (`ApplicationKnowledge`) | `name: str` (obligatorio, sin default) | `applications_core.py:140` |
| Gestor (`ApplicationManager.applications`) | clave = `app.name.lower()` | `applications_core.py:370` |
| Entidad persistida (`Entity.id`) | `f"app_{app.name.lower()}"` | `applications_core.py:355` |
| Resolución de alias | `_normalize_name()` → diccionario inline | `applications_core.py:206-232` |
| API pública | `get_application_knowledge(app_name)["name"]` | `applications_core.py:990` |

**Conclusión**: `ApplicationKnowledge.name` (case-insensitive) identifica
inequívocamente a una aplicación. No existe un campo `id` separado. El nombre
lowercased es la clave canónica usada en el dict del gestor y como base del Entity.id.

## Tests creados

**Archivo**: `tests/hands/test_application_identification.py` (19 tests, todos PASSED)

Se verificó:
1. `name` es obligatorio (TypeError si falta).
2. El gestor indexa por `name.lower()`.
3. Resolución case-insensitive (`"CHROME"` → `Chrome`).
4. `_normalize_name` resuelve 6 aliases canónicos + nombres desconocidos + `None`.
5. `get_application` resuelve alias y nombre canónico; devuelve `None` si no existe.
6. `Entity.id = app_{name.lower()}`; `aliases` persistidos siempre son `[]` (bug documentado).
7. Registro duplicado (misma clave lowercased) sobrescribe silenciosamente.
8. Nombres distintos coexisten sin conflicto.
9. `get_application_knowledge` expone `name` como identificador público.

## Cambios realizados

| Tipo | Archivo | Cambio |
|------|---------|--------|
| TEST | `tests/hands/test_application_identification.py` | Nuevo archivo — 19 tests |
| — | `src/hands/applications_core.py` | **Sin cambios** (definición/verificación) |

## Verificación

```
python -m py_compile src/hands/applications_core.py tests/hands/test_application_identification.py
  → exit 0 (OK)

python -m py_compile main.py
  → exit 0 (OK, no se modificó)

python -m pytest tests/hands/test_applications_core.py tests/hands/test_application_identification.py -v
  → 139 passed, 0 failed
```

- **Baseline no-regresión**: los 120 tests existentes de `test_applications_core.py`
  siguen PASSED.
- **Comportamiento real verificado**: el identificador `name.lower()` confirma con
  evidencia observada en tiempo de ejecución (tests `test_entity_id_matches_name_lowercased`,
  `test_name_identifies_in_manager_dict`, `test_same_name_overwrites`).

## Discrepancias documentadas (no resueltas por intuición)

- **D1**: `_normalize_name` es un diccionario hardcodeado, desconectado de `Entity.aliases`
  (`entities.json` tiene aliases como `spotify→["spoti","music"]` que no se consumen).
- **D2**: `data/knowledge/applications.json` usa keys/names que no coinciden con el modelo
  hardcoded (key `"chrome"`, `name: "Google Chrome"` vs modelo `name="Chrome"`).
- **D3**: `register_application` persiste `aliases: []` siempre vacío.
- **D4**: No hay verificación de unicidad; registro duplicado sobrescribe silenciosamente.
- **D5**: `applications.json` no es cargado por `ApplicationManager.__init__`; solo como
  dict raw en `DomainMemory`.
- **D6**: Capa de datos y modelo de código coexisten sin adaptador (heredado de 3.1.1.x).

## Comportamiento definido

```python
# El identificador único de una aplicación es `name` (case-insensitive):
#   - clave en ApplicationManager.applications = app.name.lower()
#   - Entity.id = f"app_{app.name.lower()}"
#   - resolución de alias mediante _normalize_name() (diccionario inline)
```

## Pendientes

- **3.1.2.2**: Definir qué datos son obligatorios para registrar una aplicación (verificar
  que `name` y `type` son los únicos obligatorios en `register_custom_application`).
- **3.1.2.3**: Definir qué datos son opcionales.
- **3.1.2.4**: Verificar que el contrato no duplique información.
- **3.1.3**: Compatibilidad y tests del contrato mínimo (resolver D1-D6 según decisión
  de modelo canónico).
