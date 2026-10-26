# Estado de Fase — Estandarización de la forma de los elementos UI

> **Fase:** UI Element Shape Standardization
> **Estado actual:** Parcialmente completada (3 de 8 tareas terminadas)
> **Autor (sesión):** ASI (estación de trabajo)
> **Nota:** Este documento existe para que la IA siguiente retome el trabajo sin
> perder contexto. No borres las secciones "Hecho" ni "Por hacer".

## 🎯 Objetivo de la fase

Unificar la representación de los **elementos de interfaz de usuario (UI element)**
a lo largo de toda la base de código. Hasta ahora existían **4+ representaciones
incompatibles** del mismo concepto:

| Módulo | Clase | Tipo | Campos clave |
| --- | --- | --- | --- |
| `src/eyes/vision.py` | `UIElement` (pydantic) | Detectados visualmente | `type, text, bbox, center, interactive, confidence` (**sin `name`**) |
| `src/eyes/vision_only.py` | `UIElement` (dataclass) | Detección simplificada | `name, type, bbox, confidence, text=None, center, interactive` |
| `src/hands/applications_core.py` | `UIElement` (dataclass) | Catálogo declarativo | `name, type, coordinates, screen, calibration_data, required_capability, is_calibrated()` |
| `src/hands/calibrator.py` | `CalibrationElement` (dataclass) | Calibración | `id, name, application, element_type, coordinates, calibration_status, ...` |
| `src/hands/universal_visual_calibrator.py` | `UICapability` | Calibración runtime | `name, element_type, center, bbox, screen, confidence` |

Problemas concretos que motivan la estandarización:
1. `vision.py.UIElement` **no tiene `name`**, el identificador canónico que el
   planificador/ejecutor usan para dirigirse a un elemento. La visión detecta
   elementos que luego no pueden referenciarse por nombre.
2. Vocabulario inconsistente: `element_type` vs `type`, `coordinates` vs `bbox`/
   `center`, ausencia de `description`, `calibrated`, `calibration_data` en la
   visión, etc.

## ✅ Hecho (3 tareas)

### 1. Modelo canónico creado — `src/utils/ui_element_model.py` 🟢
Nuevo módulo **sin dependencias internas** (solo `pydantic` + `typing`) que define
`UIElementData(BaseModel)`, el único modelo de verdad con todos los campos:

```
name, type, description, text,
bbox: Optional[List[int]], center: List[int], coordinates: Optional[Dict],
screen: int, interactive: bool, confidence: float,
calibrated: bool, calibration_data: Optional[Dict], required_capability: Optional[str]
```

Métodos incluidos: `is_calibrated()`, `has_valid_geometry()`, `matches_name()`,
`to_dict()`, `from_dict()`, `from_compact_dict()`, `normalize_name()`.

> Ubicación neutral (`src/utils/`) para evitar import-cycles: ya es dependencia de
> `eyes` y `hands`. **No importa de `hands` ni `eyes`** (solo pydantic/typing).

### 2. `src/eyes/vision.py` alineado al modelo canónico 🟢
- `class UIElement(BaseModel)` → `class UIElement(UIElementData)` (pydantic).
  Ahora hereda `name`, `description`, `coordinates`, `screen`, `calibrated`,
  `calibration_data`, `required_capability` con defaults, manteniendo
  `bbox/center/text/interactive/confidence`.
- `detect_ui_elements()`:
  - El prompt y el esquema JSON ya solicitan `name`.
  - La construcción de `UIElement` ahora pasa `name` (inferido de
    `name`/`text`/`type` si el modelo no lo devuelve; fallback
    `element_{n}`).
- `verify_element_visibility()`: usa `element.matches_name(target)` (vocabulario
  canónico) y el `found_element` incluye ahora `name`.
- Import añadido: `from src.utils.ui_element_model import UIElementData`.

### 3. `src/eyes/vision_only.py` alineado al modelo canónico 🟢
- `@dataclass class UIElement` → `class UIElement(UIElementData)` (pydantic).
  Ya comparte la misma forma canónica que `vision.py`.
- `VisionResponse.elements: List[UIElement]` sigue funcionando (pydantic valida).
- Imports limpiados: se eliminaron `dataclass, field, Optional` (ya no usados);
  se conserva `Enum`, `List, Dict, Any`, `BaseModel, Field`.
- Test actualizado: `tests/eyes/test_vision_only.py` → `elem.text` ahora es `""`
  (canónico) en lugar de `None`; aserción cambiada a `assert elem.text == ""`.

### Verificación ejecutada
```
python -m pytest tests/eyes/test_vision.py tests/eyes/test_vision_only.py -q
→ 104 passed in 9.63s
python -m py_compile src/utils/ui_element_model.py src/eyes/vision.py src/eyes/vision_only.py (y tests) → ok
```

## ⏳ Por hacer (5 tareas — para la IA siguiente)

### 4. `src/hands/applications_core.py` UIElement (dataclass) 🟡 pendiente
Alinear el vocabulario añadiendo fields canónicos al `dataclass` `UIElement`
(que hoy solo tiene `name, type, coordinates, screen, calibration_data,
required_capability`):
- Añadir con defaults: `description=""`, `text=""`, `bbox=None`,
  `center` (`field(default_factory=list)`), `interactive=True`,
  `confidence=0.0`, `calibrated=False`.
- `is_calibrated()` debe considerar también `self.calibrated` (OR con la
  lógica de coordenadas existente).
- Importar `field` del dataclasses (`from dataclasses import dataclass, field`).
- **Test que debe seguir pasando:** `tests/hands/test_applications_core.py`
  (`TestUIElement`, `TestUIElementCoordinateVariants`) — no cambian constructores.
- Enriquecer `get_application_ui_elements()` (líneas ~425-445) para incluir los
  nuevos campos canónicos en el dict retornado (`description, text, bbox, center,
  interactive, confidence, calibrated`).

### 5. `src/hands/planner/application_integration.py` 🟡 pendiente
- `_create_ui_element_node()` (líneas ~437-513): leer `bbox`, `center`,
  `description`, `text`, `interactive`, `confidence`, `calibrated` del elemento
  (dataclass o dict) vía `self._get_value(...)` y añadirlos a `parameters`.
- Mantener la lógica existente de `is_calibrated`/`known` (tests en
  `tests/hands/planner/test_application_integration.py` `TestCreateUIElementNode`
  y `TestIsElementCalibrated` deben seguir pasando).

### 6. `src/hands/executor.py` — estado runtime de ui_elements 🟡 pendiente
- `ExecutionState.ui_elements: Dict[str, Dict[str, Any]]` guarda estado runtime
  (`focused`, `clicked`, `typed`). El vocabulario canónico esperado por
  `preconditions_effects_types.py` incluye `available`, `calibrated`, `focused`,
  `visible`.
- En `_record_success()` (~líneas 1042-1045 y 1067-1076): cuando se marca
  `focused`/`clicked`/`typed`, también establecer `available=True` (el elemento
  fue actuado → está disponible).
- Verificar tests de executor (`tests/hands/test_executor*.py`) que asartan el
  estado de `ui_elements`.

### 7. `src/hands/calibrator.py` CalibrationElement 🟡 pendiente (bajo)
- Alinear nombres: exponer `type` como alias de `element_type` (o añadir campo
  `type`), y campos `bbox`, `center`, `description` con defaults.
- Bajo prioridad: `CalibrationElement` tiene su propio ciclo de vida; la
  estandarización de vocabulario (`type`/`bbox`/`center`) es el objetivo.

### 8. Tests + suite completa 🟡 pendiente
- Revisar/actualizar tests de `applications_core`, `application_integration`,
  `executor` si cambian shapes.
- Añadir tests canónicos: `tests/utils/test_ui_element_model.py` para
  `UIElementData` (`is_calibrated`, `from_dict`, `from_compact_dict`,
  `matches_name`, `has_valid_geometry`).
- Ejecutar **suite completa**: `python -m pytest -q` y confirmar 0 regresiones.

## 📁 Archivos modificados esta sesión
- `src/utils/ui_element_model.py` (**nuevo**)
- `src/eyes/vision.py`
- `src/eyes/vision_only.py`
- `tests/eyes/test_vision_only.py`

## ⚙️ Comandos de verificación (para la IA siguiente)
```bash
cd c:\Users\FO TARDA\Documents\VSC_JC\JARVIS
# syntax
python -m py_compile src/utils/ui_element_model.py src/eyes/vision.py src/eyes/vision_only.py \
  src/hands/applications_core.py src/hands/planner/application_integration.py \
  src/hands/executor.py tests/eyes/test_vision_only.py
# tests de visión
python -m pytest tests/eyes/test_vision.py tests/eyes/test_vision_only.py -q
# tests afectados
python -m pytest tests/hands/test_applications_core.py tests/hands/planner/test_application_integration.py -q
# suite completa
python -m pytest -q
```

## 🔑 Decisiones de diseño
- **Pydantic v2** (instalado: `pydantic-2.13.5`). Usar `model_dump()`/`__init__`
  directo. La base canónica vive en `src/utils/` (neutro) para evitar ciclos.
- **Backward-compat:** todos los campos nuevos tienen defaults; constructores
  existentes (tests incluidos) siguen funcionando. Solo cambió `text` en
  `vision_only` (`None` → `""`) por uniformidad con `vision.py`.
- **`name` es la clave canónica** de direccionamiento; la visión ahora siempre la
  emite (inferida si el modelo no la devuelve).
- No se tocó `vision_only.py`'s `Vision`/`VisionNodeType` (fuera de alcance).
