# Inspección — Unidad 3.1.2.2: Datos obligatorios para registrar una aplicación

**Fecha:** 2026-10-27
**Unidad padre:** 3.1.2.1 (registro de aplicaciones)
**Objetivo:** Definir qué datos son obligatorios (sin default) para registrar una aplicación, inspeccionando el contrato de datos del modelo `ApplicationKnowledge` y la API `register_custom_application`.

## Contrato del modelo ApplicationKnowledge

Fuente: `src/hands/applications_core.py` (clase `ApplicationKnowledge`, líneas 137-161)

Campos obligatorios (sin valor por defecto):

| Campo      | Tipo | Línea |
|------------|------|-------|
| `name`     | `str` | 140   |
| `type`     | `str` | 141   |

Los 9 campos restantes son obligatorios opcionales (tienen default explícito o se normalizan en `__post_init__`):

- `executable: Optional[str] = None`
- `url: Optional[str] = None`
- `icon: Optional[str] = None`
- `capabilities: Optional[List[...]] = None` → normalizado a `[]`
- `ui_elements: Optional[List[UIElement]] = None` → normalizado a `[]`
- `states: Optional[List[...]] = None` → normalizado a `[ApplicationState.CLOSED]`
- `login_required: bool = False`
- `calibration_policy: Optional[List[str]] = None` → normalizado a `[]`
- `preflight_requirements: Optional[List[str]] = None` → normalizado a `[]`
- `default_state: ApplicationState = ApplicationState.CLOSED`
- `metadata: Optional[Dict[str, Any]] = None` → normalizado a `{}`

Verificación: `__post_init__` (líneas 154-161) convierte `None` → `[]` o `[]` según corresponda, garantizando que los campos de lista/dict nunca sean `None` después de la construcción.

## Contrato del modelo UIElement

Fuente: `src/hands/applications_core.py` (clase `UIElement`, líneas 77-86)

Campos obligatorios:

| Campo      | Tipo | Línea |
|------------|------|-------|
| `name`     | `str` | 80    |
| `type`     | `str` | 81    |

Los 4 campos restantes son opcionales (con default):

- `coordinates: Optional[Dict[str, Any]] = None`
- `screen: int = 0`
- `calibration_data: Optional[Dict[str, Any]] = None`
- `required_capability: Optional[ApplicationCapability] = None`

## Contrato en la API externa (límite JSON/Dict)

Fuente: `src/hands/applications_core.py` (función `register_custom_application`, líneas 1016-1021)

```python
if "name" not in data or "type" not in data:
    raise ValueError("Una aplicación personalizada necesita 'name' y 'type'")
```

La validación en el límite JSON/Dict refuerza el mismo contrato que exige el dataclass: **ambos** `name` y `type` son obligatorios.

## Discrepancia documentada (D7)

El registro de la unidad 3.1.2.1 (línea 4320 de `prompt_JARVIS_fases_estado.txt`) afirma:

> "`name` es el único campo obligatorio sin default (aplicaciones_core.py:140)"

Esto es **incorrecto**. La inspección de 3.1.2.2 demuestra que `type: str` (línea 141) **también** carece de default y es obligatorio. Además, para `UIElement` ambos campos (`name` línea 80 y `type` línea 81) son obligatorios.

Se corrige en este registro: el contrato obligatorio es **`{name, type}`** para `ApplicationKnowledge` y **`{name, type}`** para `UIElement`.

## Tests

Fuente: `tests/hands/test_application_mandatory_data.py` (16 tests)

- `ApplicationKnowledge` requiere ambos campos (`name`, `type`); omite cualquiera → `TypeError`.
- `register_custom_application` lanza `ValueError` si falta `name` o `type` en el dict de entrada.
- `UIElement` requiere ambos campos (`name`, `type`); omite cualquiera → `TypeError`.
- Todos los demás campos funcionan con sus valores por defecto.
- Resultado: **16/16 PASSED**.

## Verificación

- Sintaxis: `python -m py_compile src/hands/applications_core.py tests/hands/test_application_mandatory_data.py main.py` → exit 0.
- Tests: `python -m pytest tests/hands/test_application_mandatory_data.py -q` → 16 passed.
- Regresión: 1535/1535 tests de `tests/hands/` pasan (incluye los tests preexistentes de 3.1.2.1).
- Código de producción modificado: **Ninguno**. Esta unidad es puramente analítica/verificación.
