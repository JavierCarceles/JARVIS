# Inspección — Unidad 3.1.2.1
# Definir qué identifica univocamente una aplicación

## Estado
- **Fase**: 3.1.2 (Contrato mínimo)
- **Unidad**: 3.1.2.1
- **Objetivo**: Definir qué identifica inequívocamente una aplicación en el modelo `ApplicationKnowledge`.

## Análisis del código actual

### Estructura `ApplicationKnowledge` (`src/hands/applications_core.py:137`)
- `ApplicationKnowledge` es un `@dataclass` cuyo primer campo es `name: str` (sin valor por
  defecto). No existe campo `id`. El `name` es el **único campo obligatorio** que identifica
  a la aplicación.

### Registro en `ApplicationManager` (`src/hands/applications_core.py:197`)
- `ApplicationManager.applications: Dict[str, ApplicationKnowledge]` (:201) almacena las
  aplicaciones con **clave `app.name.lower()`** (:370).
- `register_application(app)` (:351-375) persiste un `Entity` con `id = f"app_{app.name.lower()}"`
  (:355) y la inserta en el dict con clave `app.name.lower()`.
- **No hay verificación de unicidad**: registrar dos apps con el mismo `name` (a juego de
  mayúsculas/minúsculas) **sobrescribe** la entrada anterior.

### Resolución de nombres (`src/hands/applications_core.py:206`)
- `ApplicationManager._normalize_name(app_name)` (:206-232) es un diccionario *inline*
  que mapea nombres habituales/alias a la clave canónica (lowercased name). Ejemplos:
  `"google chrome" -> "chrome"`, `"microsoft edge" -> "edge"`, `"file explorer" -> "explorer"`,
  `"command prompt" -> "cmd"`.
- `get_application(app_name)` (:377-380) aplica `_normalize_name` y busca en
  `self.applications[normalized]`.

### Persistencia (`src/hands/applications_core.py:354-368`)
- El `Entity` guardado usa:
  - `id = f"app_{app.name.lower()}"` (ej. `"app_chrome"`)
  - `"aliases": []` — **siempre vacío**. `_normalize_name` nunca transfiere alias al Entity.

### Capa de entidades (`src/memory/storage.py:45`)
- `Entity` dispone de un campo `aliases: List[str]` (`:56`) y método `matches_query`
  (`:83-91`). `data/knowledge/entities.json` contiene aliases para apps como `spotify`
  (`["spoti", "music"]`), `youtube` (`["yt", "you"]`), `github` (`["gh", "git"]`),
  pero `_normalize_name` **no consulta** `Entity.aliases`.

## Definición del contrato (3.1.2.1)

**El campo `ApplicationKnowledge.name` (case-insensitive) es el identificador único de una
aplicación.** Concretamente:

1. **Clave del gestor**: `app.name.lower()` es la clave en
   `ApplicationManager.applications` (`Dict[str, ApplicationKnowledge]`).
2. **ID de la entidad persistida**: `f"app_{app.name.lower()}"` es el `id` del `Entity`
   guardado en memoria.
3. **Resolución de alias**: `_normalize_name()` mapea nombres alternativos a la clave
   canónica (`name.lower()`). Es el único mecanismo de alias en el modelo de
   Application Knowledge.

## Discrepancias detectadas

| ID | Descripción | Evidencia |
|----|-------------|-----------|
| D1 | `_normalize_name` es un diccionario hardcodeado, desconectado de `Entity.aliases` | `applications_core.py:206-232` vs `storage.py:56`; `entities.json` tiene aliases no consultados |
| D2 | `data/knowledge/applications.json` usa keys JSON y `name` que no coinciden con el modelo hardcoded | JSON: key `"chrome"`, `name: "Google Chrome"`; modelo: `name="Chrome"`, key `"chrome"` |
| D3 | `register_application` persiste `aliases: []` siempre vacío | `applications_core.py:365` |
| D4 | No hay verificación de unicidad: registro duplicado sobrescribe silenciosamente | `applications_core.py:370` (dict assignment sin check previo) |
| D5 | `applications.json` no es cargado por `ApplicationManager.__init__`; solo se usa como dict raw en `DomainMemory` | `conversation.py:170-178`; registro 3.1.1.1 |
| D6 | La capa de datos (`applications.json`) y el modelo de código coexisten sin adaptador | Documentado en 3.1.1.1 (discrepancia A), 3.1.1.6 (G2), 3.1.1.2 (D) |

## Tests creados

**Archivo**: `tests/hands/test_application_identification.py`

| Clase de test | Qué verifica |
|---------------|-------------|
| `TestApplicationNameIsIdentifier` | `name` es obligatorio; el gestor indexa por `name.lower()`; resolución case-insensitive |
| `TestNormalizeName` | Alias resueltos a clave canónica; nombres desconocidos pasan thru; `None` seguro |
| `TestGetApplicationByAlias` | `get_application` resuelve alias y nombre canónico; devuelve `None` si no existe |
| `TestEntityIdUsesName` | Entity.id = `app_{name.lower()}`; `aliases` siempre `[]` |
| `TestNameUniquenessBehavior` | Registro duplicado sobrescribe; nombres distintos coexisten |
| `TestNameInKnowledgeOutput` | `get_application_knowledge` expone `name` como identificador público |

## Resultados de tests

```
tests/hands/test_application_identification.py: 19 PASSED
tests/hands/test_applications_core.py:         120 PASSED (baseline, sin cambios)
Total combinado:                              139 PASSED / 0 FAILED
```

## Verificación
- **Sintaxis**: `python -m py_compile src/hands/applications_core.py tests/hands/test_application_identification.py` → exit 0 (OK)
- **main.py**: `python -m py_compile main.py` → exit 0 (OK, no se modificó)
- **No regresión**: 120 tests existentes de `test_applications_core.py` siguen PASSED
