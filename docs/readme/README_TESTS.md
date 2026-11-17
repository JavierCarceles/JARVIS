# Tests de JARVIS (`tests/`)

Este documento explica como esta organizada la bateria de tests, como ejecutarla sin riesgos, que prueba cada fichero y que ficheros tocan el equipo real (aplicaciones, pantalla, inventario, modelos).

## Indice

1. [Antes de ejecutar nada](#1-antes-de-ejecutar-nada)
2. [Configuracion comun (`conftest.py`)](#2-configuracion-comun-conftestpy)
3. [Tipos de test y como reconocerlos](#3-tipos-de-test-y-como-reconocerlos)
4. [Como ejecutar cada grupo](#4-como-ejecutar-cada-grupo)
5. [Variables de entorno](#5-variables-de-entorno)
6. [Tests que tocan el equipo real](#6-tests-que-tocan-el-equipo-real)
7. [`tests/brain`](#7-testsbrain)
8. [`tests/ear`](#8-testsear)
9. [`tests/eyes`](#9-testseyes)
10. [`tests/memory` y `tests/helpers`](#10-testsmemory-y-testshelpers)
11. [`tests/hands`](#11-testshands)
12. [`tests/core` y `tests/experimental`](#12-testscore-y-testsexperimental)
13. [Scripts manuales (no los recoge pytest)](#13-scripts-manuales-no-los-recoge-pytest)
14. [Problemas conocidos de la bateria](#14-problemas-conocidos-de-la-bateria)

---

## 1. Antes de ejecutar nada

- **Ejecuta siempre desde la raiz del proyecto** (`JARVIS/`) con `python -m pytest ...`.
- **Un `pytest` sin filtros en Windows abre aplicaciones reales.** Los tests `*_entorno_real.py` de `tests/hands` no estan protegidos por ninguna variable: abren y cierran Mapa de caracteres, Bloc de notas, Calculadora, Edge o Discord, y algunos escriben en la base real `data/system_inventory.sqlite3`. Mira la [seccion 6](#6-tests-que-tocan-el-equipo-real) antes de lanzar la bateria completa.
- **Los tests GUI se ejecutan de uno en uno.** Nunca en paralelo (no uses `pytest-xdist` con ellos).
- **Nunca ejecutes un escaneo completo del disco.** `test_escaneo_volumenes_locales_completo_entorno_real.py` esta desactivado para pytest y ademas exige una variable explicita.
- **Muchos tests son solo de Windows.** En macOS fallan al importar (`pywinauto`, `win32con`, `ctypes.windll`, `dxcam`) o porque usan rutas `C:\Windows\...`.

## 2. Configuracion comun (`conftest.py`)

No hay `pytest.ini`, `setup.cfg` ni `pyproject.toml`. Toda la configuracion esta en `tests/conftest.py`:

| Que hace | Detalle |
|---|---|
| Rutas de importacion | Anade `JARVIS/src` y `JARVIS/` a `sys.path`. Todos los tests importan con el prefijo `src.` (`from src.hands.apps.applications_core import ...`) y las utilidades con `from tests.helpers... import ...`. |
| Ficheros ignorados | `collect_ignore` excluye `brain/`, `ear/`, `eyes/` y `hands/test__init__.py` (para evitar choques de nombres) |
| Carpeta aislada | Crea una carpeta temporal `jarvis_pytest_sandbox_*` con `data/`, `models/`, `logs/` y `config/`, y cambia el directorio de trabajo a ella durante toda la sesion. Las rutas **relativas** que escriba el codigo acaban ahi y no en el proyecto. Las rutas **absolutas** (calculadas con `__file__` o `get_project_root()`) siguen apuntando a los datos reales. |
| Rutas de los argumentos | Convierte en absolutas las rutas que pasas a pytest antes de cambiar de carpeta, asi que `pytest tests/memory` funciona desde la raiz. |
| Singletons | Un fixture automatico pone a `None` antes y despues de cada test el gestor de aplicaciones (`src.hands.apps.applications_core`), el `MemoryManager` (`src.memory.storage`) y el integrador de aplicaciones del planificador. |

No hay marcadores propios: los saltos se hacen en tiempo de ejecucion con `pytest.skip`, `unittest.skipUnless` o `unittest.SkipTest`.

`tests/` replica la estructura de `src/` (por ejemplo, `src/hands/apps/` -> `tests/hands/apps/`). Las pruebas de lanzamiento, proceso y ventana estan juntas en `tests/hands/launch/`.

## 3. Tipos de test y como reconocerlos

| Tipo | Que significa | Como reconocerlo |
|---|---|---|
| Unitario | Logica aislada; las dependencias externas son falsas (mocks) | Nombre normal `test_*.py`, usa `patch`/`MagicMock` |
| Integracion | Codigo real con ficheros o SQLite temporales (`tmp_path`) | Usa `tmp_path`, `tempfile` |
| Sistema real | Lee el sistema operativo o los datos reales del equipo, sin abrir ventanas | Suele llamarse `*_entorno_real.py` o `*_real.py` |
| GUI real | Abre aplicaciones, mueve ventanas, captura la pantalla | `*_entorno_real.py` de lanzamiento, o clases `...Real` con `JARVIS_TEST_GUI_REAL` |
| Modelo real | Llama a Ollama o carga Whisper | Nombre con `ollama_integration` / `ollama_multimodal` |
| Script manual | No lo recoge pytest; se ejecuta con `python fichero.py` | Nombres `verificacion_*`, `verify_*`, `_probe_*`, `_tmp_*` y las sondas `*_real.py` de `contextual_adaptation_engine/` |

Un `PASSED` de un test con mocks no demuestra que el componente real funcione. `src/core/test_result_categorizer.py` separa los resultados en `SIMULADO`, `UNIT_MOCKS`, `INTEGRACION_OS` y `APERTURA_GUI` para no mezclarlos.

## 4. Como ejecutar cada grupo

Desde `JARVIS/`:

```bash
python -m pytest tests/core tests/experimental tests/memory tests/helpers tests/brain
```

Seguros en cualquier sistema: no abren ventanas ni usan modelos.

```bash
python -m pytest tests/hands/planner
```

Planificador: solo logica.

```bash
python -m pytest tests/eyes --ignore=tests/eyes/capture/test_dxcam_capture_core.py --ignore=tests/eyes/capture/test_adaptive_capture_gui_real.py --ignore=tests/eyes/vision/test_qwen3vl_ollama_multimodal_integration.py --ignore=tests/eyes/vision/test_vision_chat_json_ollama_integration.py
```

Vision sin hardware especial ni Ollama.

```bash
python -m pytest tests/ear
```

Oido. No usa el microfono, pero cada `Ear()` intenta cargar el modelo Whisper `medium` real (puede tardar o descargarlo).

```bash
python -m pytest tests/eyes/vision/test_qwen3vl_ollama_multimodal_integration.py tests/eyes/vision/test_vision_chat_json_ollama_integration.py
```

Modelo real: necesita Ollama arrancado y `qwen3-vl:8b` descargado. Si no, **fallan** (no se saltan).

GUI real en Windows (abre un Bloc de notas en el monitor secundario de la derecha). En PowerShell, primero:

```powershell
$env:JARVIS_TEST_GUI_REAL = "1"
```

y despues, de uno en uno:

```bash
python -m pytest tests/eyes/detection/test_visual_ui_detector_fusion.py
```

Para `tests/hands`, elige ficheros concretos segun la [seccion 11](#11-testshands). Ejecutar la carpeta entera en Windows abre aplicaciones reales.

Muchos ficheros tienen bloque `__main__` y se pueden lanzar con `python fichero.py`, pero entonces **no se aplica la carpeta aislada de `conftest.py`** y las rutas relativas escriben en el proyecto.

## 5. Variables de entorno

| Variable | Efecto |
|---|---|
| `JARVIS_TEST_GUI_REAL=1` | Activa las clases GUI reales de `tests/eyes/detection/test_visual_ui_detector_fusion.py`, `tests/eyes/detection/test_element_classification_integration.py` y `tests/hands/detection/test_window_evidence_validator.py` (sin ella se saltan). En `tests/eyes/capture/test_adaptive_capture_gui_real.py` es obligatoria: sin ella el test da **error**, no se salta. |
| `JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL=1` | Necesaria para que el script manual `test_escaneo_volumenes_locales_completo_entorno_real.py` recorra la raiz de un volumen. Las reglas del proyecto prohiben usarla. |
| `OMNIPARSER_MODEL_PATH` | Ruta a `icon_detect_v3/model.pt` para la integracion real de OmniParser. Si no se da, se busca en la cache de Hugging Face. |
| `PADDLEOCR_MODEL_DIR` | Carpeta de modelos de PaddleOCR. Si no se da, se busca en `~/.paddlex/official_models`. |

Ningun test usa variables para activar Ollama, Whisper o el microfono.

## 6. Tests que tocan el equipo real

**Abren aplicaciones (Windows, sin variable que los proteja):**

- Mapa de caracteres (`charmap.exe`): todos los `*_entorno_real.py` de lanzamiento/proceso/ventana y `test_ciclo_vida_gui_entorno_real.py`.
- Bloc de notas, Calculadora y Edge: `test_apertura_aplicaciones_inocuas_entorno_real.py`.
- Bloc de notas: `test_aplicacion_ya_abierta_entorno_real.py`, `test_ui_automation_adapter.py`, `test_ui_automation_framework.py` (los dos ultimos lo maximizan en el monitor secundario).
- Discord: `test_lanzamiento_discord_entorno_real.py` (ruta de usuario fija).

Todos cierran solo el proceso que abrieron y comprueban que VS Code y las ventanas previas siguen igual. No envian teclado ni raton.

**Escriben en datos reales:**

- `test_registrar_aplicaciones_desde_inventario_entorno_real.py`: inserta candidatos en `data/system_inventory.sqlite3` y no los borra.
- `test_lanzamiento_discord_entorno_real.py`: puede insertar Discord como candidato en la misma base.
- `test_visual_ui_detector_fusion.py` (con GUI real): sobrescribe `tests/eyes/fixtures/informe_integracion_uia_visual_fixture_real.json` y anade lineas a `tests/eyes/fixtures/gui_tests.log`.
- Unos 15 tests de `tests/experimental/contextual_adaptation_engine/` crean el motor sin `data_dir` y usan la carpeta real `data/` (ruta absoluta). `test_goal_adaptation_production_data_clean.py` vigila que no queden restos de tests ahi.

**Leen datos reales (solo lectura):** varios tests de `tests/eyes` y `tests/hands` comprueban el contenido real de `data/knowledge/applications.json`, `data/knowledge/capabilities.json`, `data/macros_coords.json` y `data/memory/entities.json`, o leen `data/system_inventory.sqlite3`. Si esos datos cambian, esos tests fallan.

**Cierran ventanas del usuario:** `test_element_classification_integration.py` y `test_visual_ui_detector_fusion.py` cierran, antes de empezar, cualquier ventana con titulo "Bloc de notas"/"Notepad". No tengas un Bloc de notas con trabajo sin guardar al ejecutarlos.

## 7. `tests/brain`

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_llm.py` | `Brain` (`src/brain/llm.py`): aliases de acciones, limpieza y parseo del JSON del modelo, deteccion de accion directa, ejecucion de objetivos, generacion de respuestas, guardas de imagen. | Unitario/integracion. El `Brain` es real (memoria, resolutor de entidades, registro de acciones) pero `ollama.chat` es falso: no conecta con Ollama. |
| `test_htn_integration.py` | `HTNBrainIntegration`: creacion y proceso de objetivos, estadisticas, serializacion, singleton. | Unitario; HTN real, ejecutor falso. |
| `test__init__.py` | Exportaciones del paquete `src.brain`. | Nunca se ejecuta (ignorado en `conftest.py`). |

## 8. `tests/ear`

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_listener.py` | `src/ear/listener.py`: nodos de audio, calibracion, deteccion, grabacion y transcripcion; `Ear` (palabra de activacion, `listen`, procesado por lotes). | Unitario. El microfono es falso (`sd.InputStream` parcheado). Solo `TestTranscriptionNode` falsea Whisper (y comprueba que sin modelo se devuelve un fallo, no un texto inventado); el resto de `Ear()` intenta cargar el modelo `medium` real. |
| `test__init__.py` | Exportacion de `Ear`. | Nunca se ejecuta (ignorado). |

No hay ninguna prueba con microfono real.

## 9. `tests/eyes`

Subcarpetas: `capture/`, `vision/` y `detection/`, como `src/eyes/`. Las pruebas del modelo de elementos de interfaz estan en `tests/core/` y la de separacion entre conocimiento y coordenadas en `tests/hands/calibration/`.

| Fichero | Que prueba | Tipo |
|---|---|---|
| `capture/test_screen.py` | `src/eyes/capture/screen.py`: `ApplicationState`, `ApplicationInfo`, `WorldState`, numeros de monitor, `ScreenAnalyzer`. | Unitario (algunos se saltan sin `pygetwindow`) |
| `capture/test_screen_capture.py` | `ScreenCapture` y `get_screen_capture`. | Unitario |
| `capture/test_dxcam_capture_core.py` | `DXcamCapture`, `MssCapture`, paso de DXcam a mss, `AdaptiveCapture` y `evaluate_dxcam_backends`. | Unitario + hardware real. **Falla al cargarse si `dxcam` no esta instalado** (macOS). Las pruebas reales esperan un monitor principal 4K (3840x2160) y un segundo monitor. |
| `capture/test_dxcam_capture_integration.py` | Lo mismo, con camara falsa para el contrato y clases reales que se saltan si falta `dxcam`/`mss`. | Unitario + hardware real |
| `capture/test_adaptive_capture_gui_real.py` | Captura adaptativa real: rafaga al ocultar/restaurar un Bloc de notas en el monitor secundario. | GUI real, Windows. Requiere `JARVIS_TEST_GUI_REAL=1` (si no, error). Usa su propio fichero de bloqueo. |
| `vision/test_vision.py` | `src/eyes/vision/vision.py`: tipos de nodo, `VisionNode`, `UIElement`, `VisionResponse`, metodos de `Vision`. | Unitario (Ollama falso) |
| `vision/test_vision_only.py` | `src/eyes/vision/vision_only.py` (vision simplificada). | Unitario |
| `vision/test_vision_opencv.py` | `VisionOpenCVProcessor` (recortes, normalizacion, cambios, bordes, ajuste de cajas) y deteccion con OpenCV; una prueba real captura el monitor 1. | Unitario + sistema real (se salta si no hay monitor) |
| `vision/test_vision_chat_json_response.py` | Extraccion de la respuesta de Ollama en `Vision._chat_json`. | Unitario |
| `vision/test_vision_chat_json_ollama_integration.py` | `Vision._chat_json` contra Ollama real (`qwen3-vl:8b`), hasta 3 intentos. | Modelo real; falla si no hay Ollama |
| `vision/test_qwen3vl_semantic_interpretation.py` | `Vision.interpret_element_semantics` con Ollama falso. | Unitario |
| `vision/test_qwen3vl_ollama_multimodal_integration.py` | La misma funcion con `qwen3-vl:8b` real. | Modelo real; falla si no hay Ollama |
| `vision/test_vision_calibration_integration.py` | Vision -> `CoordinateManager`/`UniversalVisualCalibrator`: los elementos de Chrome se resuelven a coordenadas calibradas validas para el planificador. | Integracion; lee `data/macros_coords.json` |
| `detection/test_visual_ui_detector_fusion.py` | `VisualUIDetectorFusion`: fusion sin duplicados de UIA, OmniParser, OCR, OpenCV y Qwen3-VL; la interactividad solo con evidencia real. | Unitario (20 tests) + GUI real y Ollama real con `JARVIS_TEST_GUI_REAL=1`. Comparte un unico Bloc de notas por sesion y usa `tests/eyes/fixtures/_gui_lock.lock`. |
| `detection/test_element_classification_integration.py` | Clasificacion de elementos sobre el arbol UIA real del Bloc de notas. | GUI real, Windows; se salta sin `JARVIS_TEST_GUI_REAL=1` |
| `capture/test_application_state_enumeration.py` | Compara los enums `ApplicationState` de `screen.py` (5 valores) y `applications_core.py` (8 valores) y los estados de los JSON de conocimiento. | Inspeccion de datos reales |
| `capture/test_application_state_separation.py` | En `applications.json` los estados de ventana (`open`, `active`, `maximized`, `focused`) son booleanos independientes de los del dominio. | Datos reales |
| `capture/test_application_state_unknown.py` | Un estado desconocido nunca se trata como abierto. | Unitario |
| `capture/test_state_comparison.py` | Comparacion y reconciliacion entre estado declarado y observado (`screen.py`). | Unitario + datos reales |
| `tests/core/test_ui_element_behavior.py` | `UIElement`, `UIElementData` (calibrado, geometria, nombres, serializacion) y su uso en `ApplicationKnowledge` y el planificador. | Unitario/integracion; lee datos reales |
| `tests/core/test_ui_element_type_description.py` | Tipo y descripcion de los elementos en todas las capas. | Comprueba el comportamiento actual, que pierde la descripcion: fallara cuando se corrija ese defecto |
| `tests/core/test_ui_elements_structure.py` | Estructura real de `ui_elements` en `applications.json` y su reconstruccion. | Datos reales |
| `tests/hands/calibration/test_ui_knowledge_coordinate_separation.py` | En `macros_coords.json`, el conocimiento UI va sin coordenadas y las coordenadas van en `calibraciones`. | Datos reales; desactiva el logging durante todo el modulo |
| `test__init__.py` | Exportaciones de `src.eyes`. | Nunca se ejecuta (ignorado) |

`tests/eyes/fixtures/` contiene el informe JSON que genera la prueba de fusion, su log y los ficheros de bloqueo GUI.

## 10. `tests/memory` y `tests/helpers`

Todos trabajan sobre un `MemoryManager` en carpeta temporal; nunca tocan `data/memory/entities.json`.

| Fichero | Que prueba |
|---|---|
| `memory/test_entity_resolver.py` | `EntityResolver` consulta primero el catalogo global de aplicaciones, despues la memoria de dominio y, si no hay nada, crea una entidad temporal. |
| `memory/test_memory_entities_json_estado_inicial.py` | `save_entity` acepta un `entities.json` ausente o vacio y rechaza uno corrupto sin modificarlo. |
| `memory/test_memory_persistencia_admitida_catalogo.py` | Las entidades se guardan de verdad en disco, sobreviven a un reinicio del gestor y se actualizan sin duplicar. |
| `memory/test_conversation_aliases_historial.py` | Aliases (carga, normalizacion, nunca devuelve objetivos, `save_alias` persistente) e historial (sin duplicados, recorte, limpieza de ficheros antiguos duplicados). |
| `memory/test_memory_save_entity_persist_bug.py` | Regresion de un fallo antiguo de persistencia (su docstring dice que debe fallar, pero el fallo ya esta corregido). |
| `helpers/entities_state.py` | Utilidad: copia `entities.json` a una carpeta temporal, opera sobre la copia y demuestra con SHA-256 que el original no cambio (`verify_entities_json_unchanged`). |
| `helpers/test_entities_state_helper.py` | Tests de esa utilidad. |

## 11. `tests/hands`

La carpeta mas grande. Esta agrupada por area.

### 11.1 Descubrimiento de aplicaciones (`apps/`)

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_application_discovery.py` | `ApplicationDiscovery`, clasificador y preflight: fuentes, candidatos, registro en SQLite temporal. | Integracion (se salta si falta `notepad.exe`) |
| `test_application_discovery_sources.py` | Fuentes de Windows (menu Inicio, PATH, App Paths, ventanas abiertas). | Sistema real, Windows |
| `test_application_discovery_no_recursive_disk_search.py` | El descubrimiento no recorre el disco de forma recursiva por defecto. | Unitario |
| `test_discovery_source_report.py`, `test_discovery_source_report_3816.py` | `CalibrationManager.get_discovery_source_report`. | Unitario |
| `test_descubrimiento_fuentes_existentes_entorno_real.py` | Descubrimiento real + clasificacion + validacion del destino (inventario temporal). No lanza nada. | Sistema real, Windows |
| `test_candidatos_reales_entorno_real.py` | Cadena real descubrir -> clasificar -> preflight. No lanza nada. | Sistema real |
| `test_clasificacion_candidatos_lanzamiento_entorno_real.py` | Clasificador y preflight con `notepad`, `cmd`, `ping`, `kernel32.dll` reales. | Sistema real, Windows |
| `test_clasificacion_tipos_lanzamiento_entorno_real.py` | Tipos de lanzamiento con la base real de inventario (solo lectura). | Sistema real |
| `test_application_launch_classifier.py` | `ApplicationLaunchClassifier`. | Unitario (parte solo Windows) |

### 11.2 Inventario del sistema (`inventory/`)

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_system_inventory_storage.py` | Contrato completo de `SystemInventoryStorage`: esquema, retencion, caducidad, bloqueos de escaneo, busqueda y paginacion, privacidad. | Integracion (SQLite temporal) |
| `test_system_inventory.py` | Primer inventario, control de recorrido, medicion de recursos, politica de refresco. | Integracion |
| `test_filesystem_observer.py` | Observador opcional de cambios (`watchdog`). | Unitario |
| `test_buscar_candidatos_para_orden_entorno_real.py` | `buscar_candidatos_para_orden`. | Integracion real (unidad `C:`) |
| `test_inventario_volumen_significativo_entorno_real.py` | Busqueda, paginacion y rendimiento con miles de ficheros temporales. | Integracion real |
| `test_diferenciacion_estado_acceso_entorno_real.py` | Diferenciar estados de acceso de ficheros reales. | Integracion, Windows |
| `test_revalidar_destino_aplicacion_entorno_real.py` | Revalidar el destino de una aplicacion. | Integracion |
| `test_volumes_montados_entorno_real.py` | Solo se consultan volumenes montados. | Integracion, Windows |
| `test_inventario_integridad_privacidad_almacenamiento_entorno_real.py` | Integridad, privacidad y almacenamiento. | Integracion |
| `test_inventario_no_altera_entidades_entorno_real.py` | Escanear no modifica las entidades. | Integracion |
| `test_inventario_no_alteracion_ejecucion_completa_entorno_real.py` | SHA-256 antes/despues de ficheros de muestra y de los JSON reales del proyecto. | Sistema real (solo lectura) |
| `test_inventario_oculto_unicode_largo_permisos_entorno_real.py` | Ficheros ocultos, Unicode, rutas largas y acceso denegado. | Integracion, Windows |
| `test_inventario_vs_sistema_archivos_entorno_real.py` | El inventario coincide con el sistema de ficheros. | Integracion |
| `test_persistencia_recuperacion_inventario_entorno_real.py` | Persistencia, reapertura, migracion de esquema, base corrupta o ausente. | Integracion |
| `test_escaneo_volumenes_locales_completo_entorno_real.py` | Escaneo completo de un volumen. | **Manual y prohibido por las reglas** (ver seccion 13) |

### 11.3 Preflight (`apps/`)

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_application_preflight.py` | `ApplicationPreflight`: comprobaciones, bloqueos, elevacion. | Unitario |
| `test_application_preflight_availability.py` | Disponibilidad. | Unitario |
| `test_application_preflight_launch_destination.py` | `validate_launch_destination`. | Unitario |
| `test_application_preflight_resolve_executable.py` | Estrategias de `resolve_executable`. | Unitario |
| `test_preflight_gatekeeper_entorno_real.py` | Rechaza destinos desconocidos, ambiguos o manipulados y acepta los reales. No lanza nada. | Sistema real |
| `test_matriz_sistemas_operativos_adaptadores_entorno_real.py` | Deteccion del SO y adaptador Windows para `.exe`, `.lnk`, `ms-settings:`, `https:`. | Sistema real; espera Windows |

### 11.4 Catalogo de aplicaciones y entidades (`apps/`)

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_application_entities_auto_registration.py` | Auto-registro (upsert) de aplicaciones descubiertas y preservacion de las existentes. | Integracion |
| `test_application_entities_machine_resolution.py` | Catalogo global frente a inventario local por `machine_id`. | Integracion |
| `test_application_entities_equipo_nuevo.py` | Dos `machine_id` aislados (equipo nuevo). | Integracion |
| `test_application_entities_sqlite_registro_real.py` | Lectura de la base real; comprueba que no cambia (SHA-256). | Sistema real (solo lectura) |
| `test_registrar_aplicaciones_desde_inventario_entorno_real.py` | Registra como candidatos los `.exe` del inventario. | **Escribe en la base real sin limpiar** |
| `test_registro_candidato_autorizado_entorno_real.py` | Registro de un candidato autorizado. | Sistema real (escritura en base temporal) |
| `test_disponibilidad_vs_autorizacion.py` | "Disponible" no significa "autorizado". | Unitario |
| `test_duplicados_y_preservacion_entities_json.py`, `test_entities_json_preservation_discovery.py` | No hay duplicados y `entities.json` se conserva. | Integracion / unitario |

### 11.5 Modelo y contrato de aplicaciones (`apps/`)

Todos unitarios o de integracion con memoria temporal:

- **Contrato y datos:** `test_application_identification.py`, `test_application_mandatory_data.py`, `test_application_optional_data.py`, `test_application_minimal_contract.py`, `test_application_contract_no_duplication.py` (lee `applications.json` real), `test_application_data_format.py`, `test_application_data_incomplete.py`, `test_application_invalid_json.py`, `test_application_source_missing.py`.
- **Carga y registro:** `test_application_load.py`, `test_application_load_correctness.py`, `test_application_read.py`, `test_application_register_duplicates.py`, `test_application_register_in_memory.py`.
- **Resolucion por nombre:** `test_application_name_resolution.py`, `test_application_alias_resolution.py`, `test_application_resolution_evidence.py`, `test_application_resolution_ambiguity.py`.
- **Clasificacion y conocimiento dinamico:** `test_application_classification.py` (instalada/en ejecucion/disponible), `test_application_discovered_temporary.py`, `test_application_discovery_persistence_contract.py`, `test_application_discovery_separation.py` (observado frente a inferido).
- **Capacidades:** `test_capability_absent_verification.py`, `test_capability_availability_distinction.py`, `test_capability_query_contract.py`.
- **Consumidores:** `test_application_consumers_real_model.py` y `test_consumer_api_compatibility.py` (casi duplicados): el modelo real usado por Executor, Planner, HTN y Brain.
- **Gestor de aplicaciones:** `test_applications_core.py`.

### 11.6 Lanzamiento, proceso y ventana (`launch/`)

Cada comportamiento tiene una version unitaria (con mocks) y una real (`*_entorno_real.py`) que abre Mapa de caracteres (`C:\Windows\System32\charmap.exe`), verifica y cierra solo su propio proceso. Si Mapa de caracteres ya estaba abierto, lo reutiliza y no lo cierra.

| Comportamiento | Unitario | Real (Windows, abre apps) |
|---|---|---|
| Proceso tras lanzar | `test_verificacion_proceso_despues_lanzamiento.py` | `test_verificacion_proceso_despues_lanzamiento_entorno_real.py` |
| Ventana del proceso | `test_detectar_ventana_por_proceso.py` | `test_detectar_ventana_por_proceso_entorno_real.py` |
| Espera con timeout | `test_espera_ventana_timeout.py` | `test_espera_ventana_timeout_entorno_real.py` |
| Ventana visible | `test_verificar_ventana_visible_aplicacion.py` | `test_verificar_ventana_visible_aplicacion_entorno_real.py` |
| Estabilidad minima | `test_estabilidad_minima_proceso_ventana.py` | - |
| Estados de lanzamiento | `test_estados_lanzamiento_aplicacion.py` | `test_estados_lanzamiento_aplicacion_entorno_real.py` |

Otros:

- `test_apertura_aplicacion_cerrada_entorno_real.py`: abrir una aplicacion cerrada, incluida una ruta inexistente.
- `test_casos_edge_lanzamiento_entorno_real.py`: ya abierta, ruta obsoleta, timeout, el proceso termina, sin ventana, nombre que pediria elevacion.
- `test_ciclo_completo_apertura_cerrar_entorno_real.py`: ciclo completo en un solo test.
- `test_ciclo_vida_gui_entorno_real.py`: ciclo de vida con la clase base de `test_base_ciclo_vida_gui.py` (utilidad; no tiene tests propios).
- `test_apertura_aplicaciones_inocuas_entorno_real.py`: Bloc de notas, Calculadora y Edge reales.
- `test_aplicacion_ya_abierta_entorno_real.py`: detecta una instancia ya abierta sin tocar la del usuario.
- `test_lanzamiento_discord_entorno_real.py`: Discord real.
- `test_restore_window_state.py`: restaurar el estado de una ventana (necesita `pywin32`; solo Windows).
- `apps/windows/test_window_verification.py`: verificacion de aplicacion abierta.

### 11.7 Calibracion (`calibration/`)

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_calibration_manager.py` | `CalibrationManager` (lanzamiento simulado). | Unitario |
| `test_calibrate_application_universal.py` | `calibrate_application` universal. | Unitario |
| `test_calibration_requirements.py` | Requisitos de calibracion y su uso en el planificador. | Unitario |
| `test_calibracion_descubrimiento_requisitos.py` | Del descubrimiento a los requisitos de calibracion. | Unitario |
| `test_calibrator.py` | - | Vacio |
| `test_coordinate_spaces.py` | Espacios de coordenadas formales (FRAME_PIXELS, MONITOR_PIXELS, DESKTOP_PIXELS, DESKTOP_POINTS, WINDOW_RECT, WINDOW_CLIENT, CLIENT_NORMALIZED), transformaciones entre espacios, punto seguro dentro de un control y redondeo de entrada; geometria sintetica de Windows y macOS, sin SO ni GUI. | Unitario |

### 11.8 Deteccion de interfaz y evidencia (`detection/`)

| Fichero | Que prueba | Tipo |
|---|---|---|
| `test_ui_automation_adapter.py` | `UIAutomationAdapter`: contrato, enumeracion del arbol con elementos falsos y arbol real de un Bloc de notas maximizado en el monitor secundario. | Unitario + GUI real **sin variable que lo proteja**; solo Windows |
| `test_ui_automation_framework.py` | Clasificacion por framework (Win32, WPF, Qt, Chromium...) y cobertura; parte real con Bloc de notas. | Igual que el anterior |
| `test_detector_manifest.py` | `DetectorManifest`: estados y persistencia; una clase real exige que UIA y OpenCV esten disponibles. | Unitario + sistema real |
| `test_omniparser_adapter.py` | `OmniParserAdapter` (`icon_detect_v3`). | Unitario + modelo real. Sin el modelo, la parte real **falla** en vez de saltarse |
| `test_paddleocr_adapter.py` | `PaddleOCRAdapter`. | Igual que el anterior |
| `test_window_evidence_validator.py` | `WindowEvidenceValidator`: la evidencia pertenece al PID/ventana objetivo y se rechaza una captura del escritorio entero. | Unitario + GUI real con `JARVIS_TEST_GUI_REAL=1` |
| `test_detection_thresholds.py` | `DetectionThresholds` de `src.hands.detection.calibration_quality_gate`: umbrales por metodo y tipo de control, derivacion desde mediciones, congelado antes de la aceptacion y persistencia. Unitario determinista, sin SO ni GUI. | Unitario |
| `test_calibration_quality_gate_dimensions.py` | `assess_candidate` y `decide_actionability` de `src.hands.detection.calibration_quality_gate`: las cuatro dimensiones de calidad (deteccion, semantica, interactividad y precision geometrica) evaluadas de forma independiente; `QualityAssessment.passed` exige que pasen las cuatro y ninguna puntuacion agregada compensa una dimension insuficiente; decision de accionabilidad para controles deshabilitados, fuera de pantalla, cubiertos, ambiguos, transitorios, de proveedor desconocido o con calidad insuficiente, conservando la definicion logica. Unitario determinista, sin SO ni GUI. | Unitario |
| `test_interaction_environment.py` | `check_interaction_environment` y `InteractionEnvironment` de `src.hands.detection.calibration_quality_gate`: sesion bloqueada, escritorio seguro, elevacion/UAC, contenido protegido, ventana protegida, overlays, minimizada/oculta y permisos; adaptador Windows real sobre Notepad en el monitor secundario derecho. | Unitario + GUI real con `JARVIS_TEST_GUI_REAL=1` |
| `test_verify_before_action.py` | `take_detection_snapshot` y `verify_before_action` de `src.hands.detection.calibration_quality_gate`: deriva entre deteccion y accion (PID/ventana, foco, monitor, escala/DPI, resolucion, caja del control, estado UI, captura obsoleta) con accion proceed/recapture/recalibrate; nunca reusa la deteccion previa. Adaptador de escritorio inyectado. Unitario determinista, sin SO ni GUI. | Unitario |
| `test_ui_calibration_quality_gate.py` | Puerta de calidad y calibracion UI de `src.hands.detection.calibration_quality_gate`: confianza insuficiente, identidad incorrecta, ventana oculta, control deshabilitado/fuera de pantalla, captura obsoleta, caja truncada o fuera de ventana/imagen, solapamiento ambiguo y deriva entre deteccion y accion; incluida la fachada `CalibrationQualityGate.evaluate`. Unitario determinista, sin SO ni GUI. | Unitario |

### 11.9 Elementos de interfaz y coordenadas (`calibration/`)

- `test_ui_elements_real_flow.py`: comportamiento real de `UIElement` y `ApplicationManager` (sin GUI, a pesar del nombre).
- `test_ui_element_description_preservation.py`, `test_ui_element_type_normalization.py`: la descripcion se conserva y el tipo se normaliza al conjunto valido de `CoordinateManager`.
- `test_ui_elements.py`, `test_ui_elements_final.py`, `test_ui_elements_minimal.py`, `test_ui_elements_real.py`, `test_ui_elements_simple.py`, `test_ui_elements_working.py`: seis versiones sucesivas de la misma bateria, todas con mocks. Candidatas a unificarse.

### 11.10 Acciones y ejecutor (`actions/`)

| Fichero | Que prueba |
|---|---|
| `test_action_registry.py` | `ActionRegistry` y `ActionType`. |
| `test_executor.py` | `Executor`, `ExecutionResult`, `ExecutionState`. |
| `test_executor_state.py` | Actualizacion del estado del mundo por el ejecutor y comparacion con `screen.py`; lee `applications.json` real. |

### 11.11 Planificador (`tests/hands/planner/`)

Todos unitarios, sin aplicaciones ni disco real:

| Fichero | Que prueba |
|---|---|
| `test_node.py`, `test_graph_node.py` | `Node` y nodos del grafo. |
| `test_graph_edge.py`, `test_graph_helpers.py`, `test_graph_builder.py` | Aristas, utilidades y construccion del grafo. |
| `test_state_graph.py`, `test_advanced_state_graph.py` | Grafo de estados y busqueda. |
| `test_route_result.py` | Resultado de una ruta. |
| `test_cache_performance.py` | Cache y metricas de rendimiento. |
| `test_application_integration.py` | `ApplicationKnowledgeIntegrator`. |
| `test_application_knowledge_to_goal.py` | Del conocimiento de aplicaciones a un `Goal`. |
| `test_capabilities_consumible_format.py`, `test_planner_find_nodes_for_capability.py` | Formato de capacidades y busqueda de nodos por capacidad. |
| `test_planner_action_verification.py`, `test_planner_capability_action_traceability.py` | Verificacion de acciones y trazabilidad capacidad -> accion. |
| `test_is_application_available_no_process_name_assumption.py` | La disponibilidad no supone el nombre del proceso. |
| `test_task_executor.py` | `TaskExecutor` (HTN). |

### 11.12 Otros

- `test__init__.py`: exportaciones de `src.hands`. Nunca se ejecuta (ignorado).

### 11.13 Pruebas de plataforma de escritorio (tests/desktop/)

- `test_desktop_platform_adapter_selection.py`: seleccion del adaptador de escritorio por SO detectado, error explicito sin adaptador, imports nativos perezosos, importacion del paquete en Windows y macOS, capacidades declaradas y marcadores de plataforma en requirements. Unitario, determinista, sin GUI ni SO real.
- `test_desktop_platform_contract.py`: contrato de plataforma (seleccion de adaptador, capacidades, errores normalizados y modelos de geometria) y adaptador macOS con frontera nativa sintetica (Retina 2x, dos y tres monitores, origen negativo, monitor vertical, permisos denegados y concedidos), ejecutado en Windows. Incluye enumeracion real de monitores Windows con todos los campos de DisplayInfo (identificador estable, rectangulo, origen, resolucion, area de trabajo, escala/DPI, rotacion, orientacion, frecuencia, principal) y reenumeracion fresca sin dimensiones historicas. La verificacion real del adaptador macOS queda pendiente en `mejora/pendientes_macos.txt` (regla 3 del roadmap).
- `test_monitor_topology.py`: modelo de topologia de monitores (relaciones izquierda/derecha/arriba/abajo, monitores centrales, tamano relativo, orientacion, principal, huella digital de topologia y consultas de punto/rectangulo/orden visual) con topologias sinteticas (1, 2, 3 y 4 monitores, origenes negativos, retrato/paisaje). Incluye integracion real en Windows que lee la topologia real via `get_current_topology()` sin modificar el equipo. Unitario, determinista, sin GUI.
- `test_monitor_policies.py`: politicas de monitor destino: `TargetMonitorPolicy` (producto: usuario, aplicacion ya abierta, preferencia configurada, ventana activa, puntero, principal; orden configurable) y `TestMonitorPolicy` (pruebas GUI: monitor no principal mas a la derecha por geometria real; con un solo monitor, ese). Ninguna usa indices fijos. Unitarias con geometria sintetica e integracion real en Windows que solo lee la topologia del equipo.
- `test_topology_watcher.py`: deteccion de conexion/desconexion de monitores y cambios de escala en ejecucion: `TopologyWatcher` con baseline, check, assert_unchanged, start/stop de listener y diff_topologies; comprobacion de fingerprint antes de cada accion espacial. Unitarias con adaptador mockeado (20) e integracion real en Windows (3) sobre get_current_topology() sin modificar el equipo.
- `test_monitor_topology_selection.py`: `resolve_monitor_reference` con topologias sinteticas (1, 2, 3 y 4 monitores, origenes negativos, vertical, escalas mixtas, referencias resueltas y ambiguas) e integracion real de solo lectura en Windows. Unitario, determinista, sin GUI.
- `test_window_dpi_info_entorno_real.py`: GUI real en Windows, requiere `JARVIS_TEST_GUI_REAL=1`. Abre una unica instancia de Notepad, la mueve al monitor no principal mas a la derecha (politica de pruebas de `TestMonitorPolicy`) y verifica que `get_window_dpi_info` devuelve el DPI real de la ventana (`GetDpiForWindow`), el DPI del monitor (`GetDpiForMonitor`), la awareness de la ventana, la awareness del proceso y la awareness de JARVIS, sin tocar Visual Studio Code ni ventanas preexistentes del usuario. Cierra solo la ventana que abrio. Integracion real sobre ventana propia.

## 12. `tests/core` y `tests/experimental`

`tests/core/` prueba `src/core/`; `tests/experimental/` prueba los modulos de `src/experimental/`.

| Fichero o carpeta | Que prueba |
|---|---|
| `tests/core/test_log.py` | Sistema unico de logs: `get_logger`, fichero y consola de `setup_logging`, nombres sin prefijo `src.`, sin handlers duplicados. Se puede ejecutar en cualquier sistema. |
| `tests/core/test_ui_element_behavior.py`, `tests/core/test_ui_element_type_description.py`, `tests/core/test_ui_elements_structure.py` | Modelo de elementos de interfaz (descritos en la seccion 9). |
| `tests/experimental/test_jarvis_logging_format.py` | Las funciones `log_jarvis_*` aceptan argumentos posicionales al estilo de `logging` y no fallan si el formato no encaja. |
| `tests/core/test_element_classification.py` | `classify_element` y sus 8 categorias; solo `UIA_ACTIONABLE` acredita interactividad verificada. |
| `tests/core/test_test_result_categorizer.py` | `TestResultCategorizer`: las categorias nunca se mezclan. |
| `test_contextual_pattern_recognizer.py` | `ContextualPatternRecognizer` (bateria actual). |
| `test_contextual_pattern_recognizer_legacy.py` | La misma clase (bateria antigua). |
| `test_meta_learning_system.py` | `MetaLearningSystem`. |
| `test_pattern_analyzer.py` | `PatternAnalyzer`. |
| `test_performance_optimizer.py` | `PerformanceOptimizer` (psutil y scikit-learn reales). |
| `test_adaptive_learning_engine.py` y `adaptive_learning_engine/` (`test_adaptive_learning_engine_original.py`, `test_goal_adaptation_learning_loop.py`) | `AdaptiveLearningEngine` con modelos reales de scikit-learn. **El fichero suelto repite los tests de la carpeta.** |
| `test_dynamic_resource_allocator.py` y `dynamic_resource_allocator/` (`test_dynamic_resource_allocator_allocate_simple.py`, `test_dynamic_resource_allocator_allocate.py`, `test_dynamic_resource_allocator_allocation.py`, `test_dynamic_resource_allocator_inventory.py`, `test_dynamic_resource_allocator_priority_conflicts.py`, `test_dynamic_resource_allocator_release.py`, `test_dynamic_resource_allocator_integration.py`) | `DynamicResourceAllocator`. **El fichero suelto repite los tests de la carpeta.** |
| `test_adaptive_goal_system.py`, `test_architectural_evolution_manager.py`, `test_auto_improvement_system.py`, `test_self_improvement_system.py` | Vacios. |

### `tests/experimental/contextual_adaptation_engine/`

Prueba `ContextualAdaptationEngine` con el motor real y ficheros reales. Si no se le pasa `data_dir`, el motor usa la carpeta real `data/`.

- **Transferencia entre contextos:** `test_cross_context_knowledge_transfer.py`, `test_cross_context_units.py`, `test_cross_context_confidence_feedback.py`, `test_context_compatibility.py`, `test_context_model_origin_destination.py`, `test_transfer_recommendations.py`, `test_contextual_features_signals.py`.
- **Adaptacion de objetivos:** `test_goal_adaptation_proposal.py`, `test_goal_adaptation_representation.py`, `test_adapted_goal_validation.py`, `test_goal_adaptation_feedback.py`, `test_goal_adaptation_evidence_valid.py`, `test_goal_adaptation_evidence_insufficient.py`, `test_adaptation_does_not_break_planner_executor.py`, `test_evolutionary_strategy_optimizer.py`.
- **Persistencia y reinicio:** `test_goal_adaptation_feedback_persistence.py`, `test_goal_adaptation_persistence_simple.py`, `test_goal_adaptation_persistence_real.py`, `test_load_goal_adaptation_feedback.py`, `test_goal_adaptation_strategy_persistence.py`, `test_goal_adaptation_learned_strategy_persistence.py`, `test_goal_adaptation_strategy_restart_verification.py`, `test_goal_adaptation_pattern_persistence.py`, `test_goal_adaptation_pattern_load.py`, `test_goal_adaptation_pattern_restart_verification.py`, `test_goal_adaptation_restart_compatibility.py`, `test_goal_adaptation_conservation.py`, `test_goal_adaptation_forgetting.py`.
- **Datos corruptos y recuperacion:** `test_corrupt_data.py`, `test_absent_storage_and_sections.py`, `test_goal_adaptation_corrupted_list_section.py`, `test_goal_adaptation_fabricated_identity.py`, `test_goal_adaptation_condition_pattern_default.py`, `test_goal_adaptation_recoverable.py`, `test_goal_adaptation_recovery_partial.py`, `test_goal_adaptation_rejection_runtime.py`, `test_goal_adaptation_total_loss_fallback.py`, `test_goal_adaptation_total_loss_fallback_implemented.py`, `test_goal_adaptation_total_corruption.py`. Varios comprueban con un hash que la carpeta real `data/` no cambia.
- **Guardia:** `test_goal_adaptation_production_data_clean.py` comprueba que no quedan restos de tests en `data/` y que los tests que escriben pasan `data_dir`.
- **Sin aserciones (depuracion antigua):** `test_direct.py`, `test_final.py` (identicos) y `test_simple.py`.
- **Sondas manuales:** `_cae_sondas_base.py` (biblioteca comun), `corruption_criteria_real.py`, `identify_recoverable_real.py`, `identify_fallback_real.py`, `verify_rejection_real.py`. Se ejecutan con `python <fichero>.py` y trabajan en carpetas temporales. Algunos tests las cargan por ruta.

## 13. Scripts manuales (no los recoge pytest)

En `tests/hands/apps/`, `tests/hands/inventory/` y `tests/hands/launch/`:

| Fichero | Que hace |
|---|---|
| `_probe_calc.py` | Resuelve y valida `calc.exe` con el preflight e imprime el resultado. |
| `_probe_inventario.py` | Lee (solo lectura) maquinas, volumenes y candidatos de `data/system_inventory.sqlite3`. Ejecutar desde la raiz. |
| `_tmp_all_windows.py`, `_tmp_vscode_windows.py`, `_tmp_vscode_rect.py` | Listados de ventanas para depurar. `_tmp_vscode_rect.py` usa un PID fijo ya invalido. |
| `_tmp_ciclo_3_8_5_6_6.py` | Ciclo completo de lanzamiento; sustituido por `test_ciclo_completo_apertura_cerrar_entorno_real.py`. |
| `verificacion_real_inventario_8_3.py`, `verificacion_real_inventario_8_4.py`, `verificacion_real_inventario_8_5.py`, `verificacion_real_inventario_8_6.py`, `verificacion_real_inventario_8_7.py`, `verificacion_real_inventario_8_8.py`, `verificacion_real_inventario_8_9.py`, `verificacion_real_inventario_8_10.py` | Verificaciones reales del inventario (escaneo acotado, permisos, logs, retencion, rendimiento, respuesta durante el escaneo). Usan bases temporales. |
| `verify_38514119_real.py` | Lee la base real y registra candidatos en una memoria temporal. |
| `verify_preflight_packaged_app.py` | Preflight de una aplicacion empaquetada (AppX). No abre nada. |
| `test_escaneo_volumenes_locales_completo_entorno_real.py` | Escaneo completo de un volumen hacia la base real. Desactivado en pytest (`__test__ = False`) y prohibido por las reglas del proyecto. |

## 14. Problemas conocidos de la bateria

1. **Tests reales sin variable que los proteja:** todos los `*_entorno_real.py` de lanzamiento, `test_ui_automation_adapter.py` y `test_ui_automation_framework.py` se ejecutan en cualquier `pytest` en Windows.
2. **Escrituras en datos reales:** `test_registrar_aplicaciones_desde_inventario_entorno_real.py` y `test_lanzamiento_discord_entorno_real.py` modifican `data/system_inventory.sqlite3`; los tests del motor de adaptacion creados sin `data_dir` usan `data/`.
3. **Fallan en vez de saltarse:** `test_omniparser_adapter.py` y `test_paddleocr_adapter.py` importan `skipIf` pero no lo usan; los tests de Ollama real; `test_adaptive_capture_gui_real.py` sin la variable.
4. **`test_dxcam_capture_core.py`** no se puede cargar sin `dxcam` y supone un monitor 4K.
5. **Tests que nunca se ejecutan:** los `test__init__.py` de `brain`, `ear` y `eyes` tienen tests reales, pero estan en `collect_ignore` para evitar el choque de nombres entre ficheros iguales.
6. **Duplicados:** `test_adaptive_learning_engine.py` y `test_dynamic_resource_allocator.py` repiten sus carpetas; seis variantes de `test_ui_elements*.py`; `test_direct.py` y `test_final.py` son identicos; `test_application_consumers_real_model.py` y `test_consumer_api_compatibility.py` casi iguales; dos ficheros de `get_discovery_source_report`.
7. **Ficheros vacios:** `hands/calibration/test_calibrator.py` y cuatro en `tests/experimental`.
8. **Rutas fijas de un equipo:** Discord y Edge en `test_lanzamiento_discord_entorno_real.py` y `test_apertura_aplicaciones_inocuas_entorno_real.py`; un `sys.path` a `c:\Informatica\...` en `windows/test_window_verification.py`.
9. **Tests atados a un defecto:** `test_ui_element_type_description.py` comprueba que la descripcion se pierde; fallara cuando se corrija.
10. **`tests/experimental/test_adaptive_learning_engine.py`** empieza con una marca BOM UTF-8.
11. **`test_visual_ui_detector_fusion.py`** define dos veces las funciones de bloqueo GUI (la segunda anula a la primera).
12. **Un test ensucio datos reales:** `data/memory/world_state.json` contiene un `MagicMock` escrito por un test (ver `README_DATA.md`).
