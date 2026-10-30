# 📖 README — JARVIS (documentación exhaustiva del código fuente)

> **Alcance:** documentación generada a partir del **código fuente real** (`src/`, 94 archivos, ~87 000 líneas).
> Cada entrada se deriva de firmas y docstrings extraídos mediante AST; las descripciones largas provienen de los propios docstrings del proyecto cuando existen.

## 🗺️ Índice

- [Arquitectura por capas y flujo de ejecución](#arquitectura-por-capas-y-flujo-de-ejecución)
- [Modelo de fases (FASE)](#modelo-de-fases-fase)
- [Cómo ejecutar](#cómo-ejecutar)
- [Documentación por módulo](#documentación-por-módulo)
<!-- sección por directorio -->
- [`src/__init__.py` (1 líneas)](#src-_init_-py)
- [`src/brain/__init__.py` (10 líneas)](#src-brain-_init_-py)
- [`src/brain/htn_integration.py` (487 líneas)](#src-brain-htn_integration-py)
- [`src/brain/llm.py` (1039 líneas)](#src-brain-llm-py)
- [`src/ear/__init__.py` (4 líneas)](#src-ear-_init_-py)
- [`src/ear/listener.py` (587 líneas)](#src-ear-listener-py)
- [`src/eyes/__init__.py` (5 líneas)](#src-eyes-_init_-py)
- [`src/eyes/screen.py` (997 líneas)](#src-eyes-screen-py)
- [`src/eyes/screen_capture.py` (368 líneas)](#src-eyes-screen_capture-py)
- [`src/eyes/vision.py` (924 líneas)](#src-eyes-vision-py)
- [`src/eyes/vision_only.py` (417 líneas)](#src-eyes-vision_only-py)
- [`src/hands/__init__.py` (30 líneas)](#src-hands-_init_-py)
- [`src/hands/action_registry.py` (1272 líneas)](#src-hands-action_registry-py)
- [`src/hands/application_preflight.py` (894 líneas)](#src-hands-application_preflight-py)
- [`src/hands/applications_core.py` (1357 líneas)](#src-hands-applications_core-py)
- [`src/hands/calibration_manager.py` (2343 líneas)](#src-hands-calibration_manager-py)
- [`src/hands/calibrator.py` (1059 líneas)](#src-hands-calibrator-py)
- [`src/hands/chrome/__init__.py` (75 líneas)](#src-hands-chrome-_init_-py)
- [`src/hands/chrome/chrome.py` (500 líneas)](#src-hands-chrome-chrome-py)
- [`src/hands/chrome/chrome_calibrator.py` (56 líneas)](#src-hands-chrome-chrome_calibrator-py)
- [`src/hands/coordinate_manager.py` (1113 líneas)](#src-hands-coordinate_manager-py)
- [`src/hands/edge/__init__.py` (3 líneas)](#src-hands-edge-_init_-py)
- [`src/hands/edge/calibrator_edge.py` (237 líneas)](#src-hands-edge-calibrator_edge-py)
- [`src/hands/edge/edge.py` (568 líneas)](#src-hands-edge-edge-py)
- [`src/hands/executor.py` (1861 líneas)](#src-hands-executor-py)
- [`src/hands/firefox/__init__.py` (3 líneas)](#src-hands-firefox-_init_-py)
- [`src/hands/firefox/calibrator_firefox.py` (235 líneas)](#src-hands-firefox-calibrator_firefox-py)
- [`src/hands/firefox/firefox.py` (638 líneas)](#src-hands-firefox-firefox-py)
- [`src/hands/keyboard.py` (901 líneas)](#src-hands-keyboard-py)
- [`src/hands/mouse.py` (129 líneas)](#src-hands-mouse-py)
- [`src/hands/planner/__init__.py` (235 líneas)](#src-hands-planner-_init_-py)
- [`src/hands/planner/application_integration.py` (864 líneas)](#src-hands-planner-application_integration-py)
- [`src/hands/planner/goal_state_mapper.py` (1485 líneas)](#src-hands-planner-goal_state_mapper-py)
- [`src/hands/planner/graph.py` (1871 líneas)](#src-hands-planner-graph-py)
- [`src/hands/planner/heuristic.py` (893 líneas)](#src-hands-planner-heuristic-py)
- [`src/hands/planner/htn_manager.py` (1100 líneas)](#src-hands-planner-htn_manager-py)
- [`src/hands/planner/learning_system.py` (899 líneas)](#src-hands-planner-learning_system-py)
- [`src/hands/planner/node.py` (1137 líneas)](#src-hands-planner-node-py)
- [`src/hands/planner/optimization.py` (951 líneas)](#src-hands-planner-optimization-py)
- [`src/hands/planner/optimization_config.py` (475 líneas)](#src-hands-planner-optimization_config-py)
- [`src/hands/planner/planner.py` (3129 líneas)](#src-hands-planner-planner-py)
- [`src/hands/planner/planner_integration.py` (1923 líneas)](#src-hands-planner-planner_integration-py)
- [`src/hands/planner/preconditions_effects.py` (1076 líneas)](#src-hands-planner-preconditions_effects-py)
- [`src/hands/planner/preconditions_effects_types.py` (821 líneas)](#src-hands-planner-preconditions_effects_types-py)
- [`src/hands/planner/task_executor.py` (1097 líneas)](#src-hands-planner-task_executor-py)
- [`src/hands/universal_visual_calibrator.py` (922 líneas)](#src-hands-universal_visual_calibrator-py)
- [`src/hands/windows/__init__.py` (3 líneas)](#src-hands-windows-_init_-py)
- [`src/hands/windows/calibrator_windows.py` (263 líneas)](#src-hands-windows-calibrator_windows-py)
- [`src/hands/windows/windows.py` (694 líneas)](#src-hands-windows-windows-py)
- [`src/memory/__init__.py` (78 líneas)](#src-memory-_init_-py)
- [`src/memory/conversation.py` (1129 líneas)](#src-memory-conversation-py)
- [`src/memory/entity_resolver.py` (825 líneas)](#src-memory-entity_resolver-py)
- [`src/memory/prediction.py` (1081 líneas)](#src-memory-prediction-py)
- [`src/memory/storage.py` (1984 líneas)](#src-memory-storage-py)
- [`src/mouth/__init__.py` (4 líneas)](#src-mouth-_init_-py)
- [`src/mouth/speaker.py` (680 líneas)](#src-mouth-speaker-py)
- [`src/tools/__init__.py` (30 líneas)](#src-tools-_init_-py)
- [`src/tools/executor.py` (559 líneas)](#src-tools-executor-py)
- [`src/tools/os_info.py` (533 líneas)](#src-tools-os_info-py)
- [`src/tools/registry.py` (1072 líneas)](#src-tools-registry-py)
- [`src/utils/__init__.py` (333 líneas)](#src-utils-_init_-py)
- [`src/utils/adaptive_learning_engine.py` (1269 líneas)](#src-utils-adaptive_learning_engine-py)
- [`src/utils/advanced_logger.py` (1577 líneas)](#src-utils-advanced_logger-py)
- [`src/utils/alert_system.py` (620 líneas)](#src-utils-alert_system-py)
- [`src/utils/app_utils.py` (1030 líneas)](#src-utils-app_utils-py)
- [`src/utils/architectural_evolution_manager.py` (10766 líneas)](#src-utils-architectural_evolution_manager-py)
- [`src/utils/circuit_breaker.py` (197 líneas)](#src-utils-circuit_breaker-py)
- [`src/utils/config.py` (1348 líneas)](#src-utils-config-py)
- [`src/utils/contextual_adaptation_audit.py` (444 líneas)](#src-utils-contextual_adaptation_audit-py)
- [`src/utils/contextual_adaptation_engine.py` (4958 líneas)](#src-utils-contextual_adaptation_engine-py)
- [`src/utils/contextual_pattern_recognizer.py` (509 líneas)](#src-utils-contextual_pattern_recognizer-py)
- [`src/utils/dynamic_resource_allocator.py` (1336 líneas)](#src-utils-dynamic_resource_allocator-py)
- [`src/utils/error_dashboard.py` (592 líneas)](#src-utils-error_dashboard-py)
- [`src/utils/error_recovery.py` (522 líneas)](#src-utils-error_recovery-py)
- [`src/utils/get_coords.py` (456 líneas)](#src-utils-get_coords-py)
- [`src/utils/health_checker.py` (498 líneas)](#src-utils-health_checker-py)
- [`src/utils/health_monitor.py` (418 líneas)](#src-utils-health_monitor-py)
- [`src/utils/jarvis_logging_system.py` (487 líneas)](#src-utils-jarvis_logging_system-py)
- [`src/utils/log_analytics.py` (966 líneas)](#src-utils-log_analytics-py)
- [`src/utils/log_dashboard.py` (887 líneas)](#src-utils-log_dashboard-py)
- [`src/utils/log_integration.py` (810 líneas)](#src-utils-log_integration-py)
- [`src/utils/log_predictor.py` (749 líneas)](#src-utils-log_predictor-py)
- [`src/utils/logger.py` (180 líneas)](#src-utils-logger-py)
- [`src/utils/meta_learning_system.py` (2401 líneas)](#src-utils-meta_learning_system-py)
- [`src/utils/metrics_collector.py` (592 líneas)](#src-utils-metrics_collector-py)
- [`src/utils/monitoring_dashboard.py` (417 líneas)](#src-utils-monitoring_dashboard-py)
- [`src/utils/optimization_orchestrator.py` (892 líneas)](#src-utils-optimization_orchestrator-py)
- [`src/utils/pattern_analyzer.py` (650 líneas)](#src-utils-pattern_analyzer-py)
- [`src/utils/performance_monitor.py` (856 líneas)](#src-utils-performance_monitor-py)
- [`src/utils/performance_optimizer.py` (1099 líneas)](#src-utils-performance_optimizer-py)
- [`src/utils/recovery_strategies.py` (514 líneas)](#src-utils-recovery_strategies-py)
- [`src/utils/screen_manager.py` (1958 líneas)](#src-utils-screen_manager-py)
- [`src/utils/self_improvement_system.py` (1261 líneas)](#src-utils-self_improvement_system-py)
- [`src/utils/ui_element_model.py` (181 líneas)](#src-utils-ui_element_model-py)

## 🏗️ Arquitectura por capas y flujo de ejecución

JARVIS se organiza en capas de bajo a alto nivel: `utils` → `brain` → `memory` → `hands` (planner+executor+actuación) y los sentidos `eyes`/`ear`/`mouth`.

```
microphone ──► ear/listener.py  (VAD + Whisper) ──► texto
screen   ──► eyes/{screen,vision}.py (mss + OpenCV/Qwen-VL) ──► estado visual
                                                          │
                         brain/llm.py  ──► intención + entidad
                        memory/{prediction,entity_resolver}.py
                                                          │  Goal
                         hands/planner/planner.py  (HTN/A*) ──► Plan (Node[])
                                                          │  plan
                         hands/executor.py  (precond → acción → verify → effects → replan)
                                                          │  acciones
     hands/{mouse,keyboard,applications_core,chrome/*,edge/*,firefox/*,windows/*,calibration_manager}
                                                          │
     eyes/screen.py ──► feedback visual ──► mouth/speaker.py
```

Puntos de integración clave:
- `action_registry.ActionRegistry` es el **contrato** entre planificador y actuador; `register_action` (decorador o función) registra cada capacidad como `ActionInfo` con `preconditions`/`effects`/`cost`/`success_checker`.
- El planificador (`hands/planner/*`) y el ejecutor (`hands/executor.py`) comparten el **mismo modelo** de precondiciones/efectos (`preconditions_effects.py` / `preconditions_effects_types.py` / `action_registry._match_condition`/`_apply_effect_value`), garantizando coherencia entre planificación y ejecución.
- `Executor` construye `Planner(self)` mediante **importación diferida** para romper el ciclo Executor↔Planner.
- La memoria (`memory/storage.py` `MemoryManager`) persiste todo bajo JSON indexado por `MemoryType`; `ConversationMemory` la unifica con el histórico de chat y el dominio.

## 📊 Modelo de fases (FASE)

| FASE | Concern | Dónde |
|---|---|---|
| 1–4 | Primitivas legacy directas | `memory/conversation.py`, `hands/mouse.py`, `tools/*` |
| 5 | Domain Memory (entidades/apps/capacidades/objetivos) | `memory/conversation.py` `DomainMemory`, `knowledge/*.json` |
| 6 | Redes de tareas HTN | `brain/htn_integration.py`, `hands/planner/htn_manager.py` |
| 7–9 | Compilación plan → ejecución con estado | `hands/planner/*`, `hands/executor.py` |
| 10 | Calibración de percepción | `calibration_manager`, `calibrator*` |
| 13 | Gestor unificado de coordenadas | `hands/coordinate_manager.py` |
| 15 | Comandos de alto nivel | `memory/prediction.py` |
| 16 | Compatibilidad (aliases, formatos legacy) | `command_aliases.json`, `jarvis_learned_aliases.json`, ramas compat |
| 17 | Optimización | `hands/planner/optimization.py`, `optimization_orchestrator.py` |
| 18 | Aprendizaje / meta-aprendizaje | `hands/planner/learning_system.py`, `meta_learning_system.py`, `prediction.py` |

## ▶️ Cómo ejecutar

```bash
pip install -r requirements.txt   # pyautogui, mss, opencv-python, pygetwindow,
                                  # torch/transformers ó ollama, openai, etc.
python main.py                  # punto de entrada real (ver sección de bucle principal)
```
Windows‑only: ratón/teclado (`pyautogui`), gestión de ventanas (`pygetwindow`) y utilidades del registro requieren Windows. Visión (`OpenCV`+`mss`) y razonamiento (`LLM`) son multi‑plataforma.

## 🚪 Punto de entrada y bucle principal (`main.py`)

`main.py` (raíz del repositorio, **353 líneas**) es el punto de arranque real de JARVIS. Lo invocas con **`python main.py`** y orquesta los componentes de alto nivel mediante un **bucle de escucha → ejecución → habla**.

**Wiring de componentes (importaciones):**
- `src.ear.Ear` — entrada de voz (ASR Whisper).
- `src.brain.Brain` — LLM de razonamiento (Ollama; modelo `llama3`).
- `src.memory.Memory` — memoria conversacional *legacy* (aliases, histórico, estadísticas de uso).
- `src.tools.executor.UnifiedExecutor` (vía `get_executor()`) — **fachada de ejecución** que despacha comandos `[CMD: nombre(args)]`.
- `src.mouth.Mouth` — TTS (opcional; si no está disponible pasa al **modo texto**).
- `src.utils.jarvis_logging_system` (`JarvisLoggingSystem`) — logging estructurado.
- DPI awareness vía `ctypes` (`SetProcessDpiAwareness` / `SetProcessDPIAware`).

**Arquitectura *legacy* vs. *nueva* (importante):** `main.py` utiliza la **API legacy** (`Brain`/`Memory`/`UnifiedExecutor`) basada en comandos `[CMD: …]` y aliases. Paralelamente existe la **arquitectura nueva** documentada en `src/hands/` (`ActionRegistry`/`ActionInfo`, `hands/executor.Executor` con planificación A*, y `hands/planner/*`). Ambas conviven: `UnifiedExecutor.execute_action` y `Executor.execute_plan` validan precondiciones/efectos contra los mismos modelos (`action_registry` / `preconditions_effects`). `Brain.interpret_intent` puede delegar a `HTNBrainIntegration` (FASE 4/6) cuando está disponible, y `UnifiedExecutor` expone `execute_plan_step` como punto de entrada explícito hacia un planificador futuro.

**Bucle principal (`main()`):**
1. Inicializa `Ear(model_size="medium")`, `Brain(model="llama3")`, `get_executor()`, `Memory()` y, opcionalmente, `Mouth()`; selecciona la voz por defecto desde `get_voice_config()` y verifica calibración (`macros_coords.json`).
2. Bucle infinito:
   a. `jarvis_ear.listen()` → texto con wake-word `jarvis`.
   b. Si el texto dispara un cambio de voz (`cambia la voz`, `usa la voz…`, etc.) → cambia voz en `Mouth` y guarda la conversación; continúa.
   c. `jarvis_memory.get_alias(texto)` → si hay alias → ejecuta `[CMD: alias]` vía `UnifiedExecutor.process_and_execute` y registra uso (`record_command_usage`).
   d. Si no, `UnifiedExecutor.get_command_suggestions(text, history)` → si `score ≥ 0.8`: propone vía voz, escucha confirmación (`sí`/`si`/`claro`/`ok`/`vale`/`dale`/`hazlo`) → ejecuta o rechaza (registrando el rechazo).
   e. Si no se acepta predicción: `Brain.think(texto, use_legacy_execution=False)` → si la respuesta contiene `[CMD: x]` → `process_and_execute`; si no, es respuesta conversacional → se habla tal cual.
   f. Registra aliases aprendidos (`save_alias`) y estadísticas de uso.
   g. Habla la respuesta con `Mouth.speak()`, registra `JARVIS: …` y persiste la conversación (`save_conversation`).
3. En `KeyboardInterrupt` apaga los subsistemas guardando logs (`jarvis_logger.stop()`).

**Ejecutores (no confundir):**
- `tools/executor.UnifiedExecutor` / `get_executor()` — fachata *legacy* de despacho de comandos `[CMD:…]`; usado por `main.py`.
- `src/hands/executor.Executor` — motor de planificación HTN/A*: recibe un `Plan` (lista de `Node`) y ejecuta con precondiciones, verificación, efectos, alternativas y replanificación (FASE 7–9 + FASE 18).
## 📚 Documentación por módulo

## 📁 `src/`

<!-- src -->

<a name="src-__init__-py"></a>
### `src/__init__.py` [1 líneas] — Inicialización del Directorio Principal

**Descripción:** Archivo marcador de posición que establece el paquete `src` raíz e importa los subpaquetes `brain`, `memory`, `hands`, `eyes`, `ear`, `mouth`, `tools` y `utils`.

**Características:**

- Punto de entrada principal del sistema
- Organización jerárquica de módulos
- Base para importaciones de alto nivel
- Estructura modular escalable

**Importaciones:** 0.

_Archivo de marcador de posición / inicialización de paquete._

## 🧠 `src/brain/`

<!-- src/brain -->

<a name="src-brain-__init__-py"></a>
### `src/brain/__init__.py` [10 líneas] — Inicialización del módulo Cerebro

**Descripción:** Inicializa el paquete `brain` y expone `Brain`, `HTNBrainIntegration`, `get_htn_integration`.

**Importaciones:** 2.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-brain-htn_integration-py"></a>
### `src/brain/htn_integration.py` [487 líneas] — Integración HTN con Brain

**Descripción:** Integra la descomposición jerárquica de objetivos (HTN) con `HTNManager` y `TaskExecutor`, manteniendo compatibilidad con el `Brain` legacy. Convierte la intención en un objetivo, lo descompone mediante HTN, ejecuta nodo a nodo y persiste resultados/completado/fallo en memoria conversacional.

**Características:**

- Descomposición y ejecución de objetivos HTN
- Serialización de tareas y resultados
- Registro de métricas de integración (FASE 18)
- Toggle y observabilidad de la integración

**Importaciones:** 10.

`class HTNIntegrationResult`  (línea 26) — Resultado de la integración HTN-Brain.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class HTNBrainIntegration`  (línea 40) — Integra interpretación de objetivos, HTN y ejecución de tareas.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def process_goal_through_htn(goal, current_state)` | Descompone y ejecuta un objetivo completo mediante HTN. |
| `def create_and_execute_htn_goal(user_input, current_state)` | Crea un objetivo básico desde texto y lo procesa mediante HTN. |
| `def _create_goal_from_input(user_input, current_state)` | Crea un objetivo compatible con los tipos usados por HTNManager. |
| `def _process_execution_results(goal, execution_result, current_state)` | Procesa el resultado, actualiza el estado y registra memoria. |
| `def _register_goal_completion(goal, execution_result)` | Registra la finalización exitosa en la memoria conversacional. |
| `def _register_goal_failure(goal, execution_result)` | Registra el fallo en la memoria conversacional. |
| `def _register_goal_memory(goal, execution_result)` |  |
| `def _serialize_task(task)` |  |
| `def _serialize_execution_result(result)` |  |
| `def _record_integration(execution_time, success)` |  |
| `def get_integration_statistics()` | Obtiene estadísticas de la integración HTN-Brain. |
| `def enable_integration(enabled)` | Habilita o deshabilita la integración HTN. |
| `def get_htn_insights()` | Obtiene información agregada del sistema HTN. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_htn_integration()`  (L475) | Obtiene la instancia global de la integración HTN-Brain. |

<a name="src-brain-llm-py"></a>
### `src/brain/llm.py` [1039 líneas] — Cerebro principal y comunicación con LLM

**Descripción:** Cerebro de JARVIS: interpretación de intenciones, extracción de entidades, creación de objetivos y comunicación con el modelo LLM (Ollama) vía API de chat. Normaliza aliases de acción, detecta acciones directas (p. ej. calibración), construye contexto del sistema y, cuando HTN está disponible, delega la planificación compleja a `HTNBrainIntegration`.

**Características:**

- Action aliases / normalización de nombres del LLM
- Detección de acciones directas (calibrar Chrome, etc.)
- Extracción de entidades (streamers/plataformas/aplicaciones)
- Construcción del contexto del sistema para el LLM
- Integración con HTN para objetivos complejos
- Soporte multimodal (think_with_image/analyze_image)

**Importaciones:** 17.

`class Brain`  (línea 32) — Cerebro de JARVIS con interpretación, objetivos y compatibilidad legacy.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(model)` |  |
| `def _normalize_action_name(action_name)` | Convierte nombres conocidos producidos por el LLM a nombres registrados. |
| `def _detect_direct_action(prompt)` | Detecta comandos del sistema que deben resolverse de forma |
| `def _get_system_context()` |  |
| `def _get_available_actions()` |  |
| `def _get_application_knowledge()` |  |
| `def _get_domain_entities()` |  |
| `def _build_system_instruction(use_legacy_mode)` |  |
| `def _chat_text(messages)` |  |
| `def generate_response(prompt, use_legacy_mode)` |  |
| `def execute_goal(goal_data)` |  |
| `def process_intent_to_execution(prompt)` |  |
| `def process_with_htn(prompt)` |  |
| `def get_htn_insights()` |  |
| `def _extract_parameters_from_input(user_input, entity)` |  |
| `def _extract_search_query(user_input)` |  |
| `def _clean_json_response(response_text)` |  |
| `def parse_model_response(llm_response)` |  |
| `def _extract_entities_from_input(user_input)` |  |
| `def _extract_entities_fallback(user_input)` |  |
| `def _create_goal_from_entity(entity, user_input, resolution_result)` |  |
| `def _get_entity_capabilities(entity, goal_type)` |  |
| `def _calculate_entity_goal_cost(entity, goal_type)` |  |
| `def _calculate_entity_complexity(entity, goal_type)` |  |
| `def interpret_intent(prompt)` |  |
| `def _create_system_goal(goal_data, user_input)` |  |
| `def think(prompt, use_legacy_execution)` |  |
| `def _execute_legacy_action(action_name, parameters)` |  |
| `def process_action_response(llm_response)` |  |
| `def think_with_image(prompt, image_path)` |  |
| `def analyze_image(image_path, analysis_prompt)` |  |
| `def clear_memory()` |  |
| `def get_conversation_history()` |  |
| `def get_available_actions()` |  |
| `def get_current_goals()` |  |
| `def get_system_state()` |  |
| `def get_domain_entities()` |  |
| `def create_goal_from_user_input(user_input)` |  |
| `def get_planner_ready_data()` |  |
| `def register_node(node_config)` |  |
| `def register_task(task_config)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_jarvis_context()`  (L1035) |  |

## 👂 `src/ear/`

<!-- src/ear -->

<a name="src-ear-__init__-py"></a>
### `src/ear/__init__.py` [4 líneas] — Módulo de sistema

**Descripción:** Módulo de sistema.

**Importaciones:** 1.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-ear-listener-py"></a>
### `src/ear/listener.py` [587 líneas] — Percepción auditiva y transcripción

**Descripción:** Pipeline de audio con nodos (`AudioNode`): calibración de umbral (RMS), grabación con detección de voz, transcripción Whisper a texto, y wake-word detection para “Jarvis”.

**Características:**

- Pipeline de nodos de audio
- Whisper ASR
- Wake-word
- Detección/grabación con VAD

**Importaciones:** 10.

`class AudioCapabilities`  (línea 22) — Capacidades del sistema de audio.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class AudioNode`  (línea 35) — Nodo básico para procesamiento de audio.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name)` |  |
| `def execute(audio_data)` | Ejecuta el procesamiento de audio. |
| `def get_preconditions()` | Devuelve las precondiciones necesarias para ejecutar este nodo. |
| `def get_effects()` | Devuelve los efectos de ejecutar este nodo. |
| `def get_cost()` | Devuelve el coste estimado de ejecutar este nodo. |

`class CalibrationNode(AudioNode)`  (línea 80) — Nodo para calibración de audio.

Métodos:

| Firma | Docstring |
|---|---|
| `def execute(audio_queue)` | Calibra el umbral de detección de voz. |
| `def _rms(audio)` | Calcula el nivel de amplitud RMS del audio. |

`class TranscriptionNode(AudioNode)`  (línea 129) — Nodo para transcripción de audio a texto.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, model_size, language)` |  |
| `def _load_model()` |  |
| `def execute(audio)` | Transcribe el audio a texto. |

`class DetectionNode(AudioNode)`  (línea 217) — Nodo para detección de voz en audio.

Métodos:

| Firma | Docstring |
|---|---|
| `def execute(audio_queue, threshold)` | Detecta voz en la cola de audio. |
| `def _rms(audio)` | Calcula el nivel de amplitud RMS del audio. |

`class RecordingNode(AudioNode)`  (línea 272) — Nodo para grabación de audio.

Métodos:

| Firma | Docstring |
|---|---|
| `def execute(audio_queue, threshold)` | Graba el audio detectado. |
| `def _rms(audio)` | Calcula el nivel de amplitud RMS del audio. |

`class Ear`  (línea 329) — Sistema de percepción auditiva integrado con la arquitectura de planificación jerárquica.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(model_size, language)` |  |
| `def _load_model()` |  |
| `def get_audio_pipeline()` | Devuelve el pipeline de procesamiento de audio. |
| `def get_pipeline_cost()` | Calcula el coste total del pipeline de audio. |
| `def get_pipeline_preconditions()` | Devuelve las precondiciones del pipeline de audio. |
| `def get_pipeline_effects()` | Devuelve los efectos del pipeline de audio. |
| `def _load_model()` | Carga el modelo Whisper (método heredado para compatibilidad). |
| `def listen(activation_word)` | Escucha el audio del usuario y transcribe usando el pipeline de nodos. |
| `def _check_activation_word(text)` | Verifica si el texto contiene una variante de "Jarvis". |
| `def process_audio_batch(audio_chunks)` | Procesa un lote de audios pregrabados. |
| `def get_audio_status()` | Devuelve el estado actual del sistema de audio. |

## 👁️ `src/eyes/`

<!-- src/eyes -->

<a name="src-eyes-__init__-py"></a>
### `src/eyes/__init__.py` [5 líneas] — Módulo de sistema

**Descripción:** Módulo de sistema.

**Importaciones:** 2.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-eyes-screen-py"></a>
### `src/eyes/screen.py` [1157 líneas] — Captura de pantalla y análisis para JARVIS con arquitectura de planificación.

**Descripción:** Captura de pantalla y análisis para JARVIS con arquitectura de planificación.

**Importaciones:** 21.

`class ApplicationState(Enum)`  (línea 41) — Estados conocidos de una aplicación.

_Sin métodos definidos en el AST._

`class ApplicationInfo`  (línea 52) — Información de una aplicación detectada.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def to_dict()` |  |
| `def from_dict(cls, data)` |  |

Constantes y funciones a nivel módulo para la comparación de estado declarado
con estado observable:

| Firma | Finalidad |
|---|---|
| `CANONICAL_WINDOW_FLAGS` (`Tuple[str, ...]`) | Las 4 flags genéricas de estado de ventana: `("open", "active", "maximized", "focused")`. Conjunto común a toda aplicación conocida en `applications.json`. |
| `APPLICATION_STATE_TO_WINDOW_FLAGS` (`Dict[ApplicationState, Dict[str, bool]]`) | Mapeo determinista de cada `ApplicationState` observable a las 4 flags canónicas booleanas. |
| `def observable_state_to_flags(state)` | Convierte un `ApplicationState` observado por visión (`Vision.detect_application_state` / `ScreenAnalyzer.analyze_application_state`) a las 4 flags canónicas `{open, active, maximized, focused}`. `CLOSED` → todas `False`; `OPEN`/`MINIMIZED` → `open=True` resto `False`; `ACTIVE` → `open=True, active=True, focused=True`; `MAXIMIZED` → todas `True`. |
| `def compare_declared_and_observable_state(declared, observable_state)` | Compara el diccionario de flags declaradas (de `applications.json` `states` o `Executor.current_state.application_states[app]`) con un `ApplicationState` observable. Solo compara las 4 flags canónicas (ignora flags de dominio como `playing`/`streaming`/`recording`). Flag faltante en `declared` se asume `False`. Valores no booleanos se convierten con `bool()`. Retorna `{match, observable_state, observable_flags, declared_flags, discrepancies}`. |

`class WorldState`  (línea 119) — Estado del mundo usado por las APIs legacy de este módulo.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def to_dict()` |  |
| `def from_dict(cls, data)` |  |

`class ScreenAnalyzer`  (línea 253) — Analizador de pantallas integrado con la capa Vision.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _get_vision()` | Inicializa Vision de forma diferida para evitar importaciones circulares. |
| `def analyze_application_state(app_name)` | Analiza una aplicación en todos los monitores disponibles. |
| `def _fallback_detect_application_state(app_name)` | Fallback no visual usando la ventana foreground cuando sea posible. |
| `def build_world_state()` | Construye el estado del mundo usando la capa Vision cuando está disponible. |
| `def _convert_visual_world_state(visual_state, monitor_numbers, timestamp)` | Adapta el WorldState de memoria de Vision a la API legacy de este módulo. |
| `def _get_known_applications()` | Obtiene aplicaciones conocidas desde memoria y descubrimiento global. |
| `def _detect_focused_application(applications)` | Detecta la aplicación enfocada mediante la ventana foreground. |
| `def _get_active_monitor()` | Obtiene el monitor de la ventana foreground desde ScreenManager. |
| `def _get_calibrated_elements()` | Obtiene elementos calibrados desde memoria. |
| `def _get_known_urls()` | Obtiene URLs conocidas desde memoria de dominio. |
| `def _get_system_resources()` | Obtiene recursos básicos del sistema. |

`class ScreenCapture`  (línea 659) — Sistema de captura con geometría delegada a ScreenManager.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _get_analyzer()` |  |
| `def capture_monitor(monitor_num, save_path)` | Captura exactamente el monitor indicado mediante ScreenManager. |
| `def capture_region(x, y, width, height, save_path)` | Captura una región expresada en coordenadas absolutas del escritorio. |
| `def capture_element(element_coords, save_path)` | Captura una región descrita por x/y/width/height. |
| `def capture_active_window(save_path)` | Captura la ventana foreground actual. |
| `def _prepare_output_path(save_path, prefix)` | Prepara la ruta de salida para una captura. |
| `def capture_desktop(save_path)` | Captura el rectángulo completo del escritorio virtual. |
| `def get_world_state()` |  |
| `def get_application_state(app_name)` |  |
| `def check_element_visibility(element_name)` | Comprueba visibilidad a partir del estado visual disponible. |
| `def clean_temp_files(pattern)` | Elimina capturas temporales del directorio actual. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _get_available_monitor_numbers()`  (L200) | Obtiene todos los monitores reales detectados por ScreenManager. |
| `def _get_monitor_number(monitor)`  (L230) | Obtiene el identificador lógico de un MonitorInfo sin asumir un campo único. |
| `def capture_screen(filepath)`  (L944) | Captura el escritorio virtual completo. |
| `def capture_captcha_area(pantalla, region_captcha, img_captcha_path)`  (L951) | Captura una región del escritorio para compatibilidad legacy. |
| `def get_screen_capture()`  (L979) | Obtiene la instancia global de captura. |

<a name="src-eyes-screen_capture-py"></a>
### `src/eyes/screen_capture.py` [368 líneas] — Sistema de captura de pantalla sin dependencias del cerebro.

**Descripción:** Sistema de captura de pantalla sin dependencias del cerebro.

**Importaciones:** 12.

`class ScreenCapture`  (línea 25) — Sistema de captura de pantalla con soporte multipantalla.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` | Inicializa el sistema de captura. |
| `def _get_analyzer()` | Lazy initialization of ScreenAnalyzer to avoid circular imports. |
| `def capture_monitor(monitor_num, save_path)` | Captura un monitor específico. |
| `def capture_region(x, y, width, height, save_path)` | Captura una región del escritorio virtual. |
| `def capture_element(element_coords, save_path)` | Captura un elemento a partir de sus coordenadas absolutas. |
| `def capture_active_window(save_path)` | Captura la ventana activa actualmente. |
| `def get_world_state()` | Obtiene el estado actual del mundo. |
| `def get_application_state(app_name)` | Obtiene el estado de una aplicación específica. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_screen_capture()`  (L361) | Obtiene la instancia global del sistema de captura. |

<a name="src-eyes-vision-py"></a>
### `src/eyes/vision.py` [924 líneas] — Visión por computadora (Qwen3-VL/Ollama)

**Descripción:** Sistema de visión basado en modelo VL vía Ollama. Analiza pantallas, detecta elementos UI, verifica visibilidad y resultados de acciones, detecta estado de aplicaciones y genera nodos de visión para el planificador.

**Características:**

- Detección de elementos UI
- Verificación visual de resultados
- Nodos de visión para el planificador
- Multi-monitor

**Importaciones:** 15.

`class VisionNodeType(Enum)`  (línea 31) — Tipos de nodos de visión disponibles para planificación.

_Sin métodos definidos en el AST._

`class VisionNode`  (línea 45) — Nodo de percepción visual reutilizable por el planificador.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |
| `def from_dict(cls, data)` |  |
| `def get_preconditions()` |  |
| `def get_effects()` |  |
| `def get_cost()` |  |

`class UIElement(UIElementData)`  (línea 85) — Elemento UI detectado por el modelo de visión (forma canónica).

_Sin métodos definidos en el AST._

`class VisionResponse(BaseModel)`  (línea 98) — Respuesta estructurada de detección UI.

_Sin métodos definidos en el AST._

`class Vision`  (línea 104) — Sistema de visión genérico integrado con la arquitectura de Jarvis.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(model)` |  |
| `def _create_vision_nodes()` |  |
| `def get_vision_nodes()` |  |
| `def get_vision_node(node_id)` |  |
| `def get_nodes_by_type(node_type)` |  |
| `def get_total_vision_cost()` |  |
| `def _get_available_monitor_numbers()` | Obtiene los identificadores lógicos reales desde ScreenManager. |
| `def _get_default_monitor_number()` | Selecciona el monitor activo y, como fallback, el principal. |
| `def analyze_screen_for_world_state()` | Analiza todas las pantallas disponibles y construye un WorldState válido. |
| `def detect_ui_elements(image_path, application)` | Detecta elementos interactivos visibles en una imagen. |
| `def analyze_image(image_path, prompt, calibration_target)` | Analiza una captura para calibración universal. |
| `def verify_element_visibility(element_name, application, expected_coords)` | Verifica visualmente si un elemento está presente. |
| `def verify_action_result(expected_state, application, tolerance)` | Verifica visualmente el resultado esperado de una acción. |
| `def _build_verification_prompt(expected_type, expected_state, application)` |  |
| `def detect_application_state(app_name)` | Busca una aplicación en todas las pantallas disponibles. |
| `def _chat_json(image_path, prompt, response_format, num_ctx, num_predict, temperature)` |  |
| `def _safe_json_loads(value)` |  |
| `def _clamp_float(value)` |  |
| `def _normalize_int_list(value, minimum, maximum)` |  |
| `def _coordinates_match(expected_coords, center, bbox, tolerance)` |  |
| `def get_vision_capabilities()` |  |

<a name="src-eyes-vision_only-py"></a>
### `src/eyes/vision_only.py` [417 líneas] — Visión por computadora usando Qwen3-VL mediante Ollama.

**Descripción:** Visión por computadora usando Qwen3-VL mediante Ollama.

**Importaciones:** 16.

`class VisionNodeType(Enum)`  (línea 27) — Tipos de nodos de visión para el planificador.

_Sin métodos definidos en el AST._

`class UIElement(UIElementData)`  (línea 37) — Elemento UI detectado por visión (forma canónica unificada).

_Sin métodos definidos en el AST._

`class VisionResponse(BaseModel)`  (línea 47) — Respuesta estructurada del modelo de visión.

_Sin métodos definidos en el AST._

`class Vision`  (línea 55) — Sistema de visión integrado con la arquitectura de planificación jerárquica.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(model)` |  |
| `def _create_vision_nodes()` | Crea los nodos de visión estándar para el planificador. |
| `def analyze_image(image_path, prompt)` | Analiza una imagen usando el modelo de visión. |
| `def verify_action_result(expected_state, tolerance)` | Verifica si una acción tuvo el resultado esperado visualmente. |
| `def detect_application_state(app_name)` | Detecta el estado de una aplicación específica visualmente. |
| `def get_vision_capabilities()` | Devuelve las capacidades de visión disponibles para el planificador. |
| `def get_total_vision_cost()` | Calcula el costo total de las capacidades de visión. |

## 🖐️ `src/hands/`

<!-- src/hands -->

<a name="src-hands-__init__-py"></a>
### `src/hands/__init__.py` [30 líneas] — Módulo de sistema

**Descripción:** Módulo de sistema.

**Importaciones:** 9.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-hands-action_registry-py"></a>
### `src/hands/action_registry.py` [1272 líneas] — Registro centralizado de acciones

**Descripción:** Contrato entre capacidades ejecutables y el planificador. `ActionInfo` modela una acción con parámetros, precondiciones/efectos (modelo canónico `Condition`/`Effect`), coste, dependencias, recursos, verificador de éxito y metadatos; `ActionRegistry` registra (decorador o llamada), valida tipos, comprueba precondiciones y ejecuta. Las funciones/callbacks no se serializan; las reglas declarativas sí.

**Características:**

- Modelo declarativo `ActionInfo` con precondiciones/efectos
- Evaluador canónico de condiciones y efectos
- Validación de tipos de parámetros
- Singleton `ActionRegistry` + decorador `register_action`

**Importaciones:** 16.

`class ActionType(Enum)`  (línea 46)

_Sin métodos definidos en el AST._

`class ActionInfo`  (línea 471) — Metadatos y contrato ejecutable de una acción registrada.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def to_dict()` | Devuelve metadatos serializables; nunca expone callbacks ejecutables. |
| `def matches_preconditions(state)` | Comprueba todas las precondiciones declarativas y funcionales. |
| `def verify_success(result)` | Ejecuta el verificador configurado sin invocarlo más de una vez. |
| `def apply_effects(current_state, execution_result)` | Aplica efectos de forma acumulativa o devuelve el estado original. |

`class ActionRegistry`  (línea 721) — Registro central, thread-safe, de acciones/capacidades disponibles.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _extract_parameters(func)` | Extrae tipo, valor por defecto y obligatoriedad de la firma real. |
| `def register_action(name, description, action_type, category, tags, parameters, confidence_threshold, preconditions, effects, cost, dependencies, capability, application, required_resources, requires_ui_element, success_checker, planner_enabled, preconditions_functions, effects_functions)` | Devuelve un decorador que registra una función como acción. |
| `def register_module(module_path)` | Importa un módulo y registra sus funciones decoradas una sola vez. |
| `def _store_action_info(action_info)` | Guarda la acción y conserva la coherencia entre acciones y categorías. |
| `def get_action(name)` |  |
| `def get_actions_by_category(category)` |  |
| `def get_all_actions()` |  |
| `def get_plannable_actions()` |  |
| `def get_actions_for_planner()` |  |
| `def get_actions_for_llama()` |  |
| `def _validate_value_type(value, expected_type)` | Valida tipos Python y anotaciones parametrizadas habituales. |
| `def validate_action(action_name, parameters)` | Comprueba presencia, nombres y tipos de parámetros sin ejecutar la acción. |
| `def can_execute(action_name, parameters, state, check_preconditions)` | Determina si una acción registrada se puede ejecutar en el estado dado. |
| `def get_action_cost(action_name)` |  |
| `def _record_execution(success)` |  |
| `def _record_prediction(prediction_memory, action_name, success)` |  |
| `def execute_action(action_name, parameters)` | Ejecuta la función registrada y propaga sus excepciones originales. |
| `def list_actions(category)` |  |
| `def get_action_categories()` |  |
| `def get_optimization_stats()` | Devuelve estadísticas del registro a partir de contadores reales. |
| `def optimize_logging()` | Punto de compatibilidad para configurar logging sin cambiar el contrato. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _log(level, message)`  (L61) | Usa el logger del proyecto sin hacer que un fallo de logging rompa JARVIS. |
| `def _call_compatible(callback, candidates)`  (L79) | Elige una firma compatible antes de invocar, sin repetir callbacks. |
| `def _state_to_mapping(state)`  (L109) | Obtiene una vista de estado compatible con los evaluadores declarativos. |
| `def _format_type_name(value)`  (L140) | Devuelve un nombre legible de tipo y apto para serialización JSON. |
| `def _serialize_rule(value, _seen)`  (L162) | Serializa reglas sin intentar serializar callbacks ni ciclos de objetos. |
| `def _get_state_value(state, key, default)`  (L261) | Obtiene un valor de un mapping, un objeto con ``get`` o un atributo. |
| `def _condition_from_dict(condition)`  (L285) | Convierte un diccionario tipado al modelo canónico ``Condition``. |
| `def _evaluate_condition_object(state, condition)`  (L328) |  |
| `def _match_condition(state, condition)`  (L336) | Evalúa una condición simple, compuesta, funcional o canónica. |
| `def _matches_conditions(state, conditions)`  (L392) | Evalúa una colección de precondiciones con semántica AND por defecto. |
| `def _apply_effect_value(effect, current_state, execution_result)`  (L403) | Aplica un efecto canónico, funcional o legacy sobre una copia del estado. |
| `def _normalize_cost(cost)`  (L599) |  |
| `def _normalize_confidence(value)`  (L609) |  |
| `def _resolve_action_type(raw_type)`  (L619) |  |
| `def _parse_type_string(type_name)`  (L629) | Resuelve formas habituales de anotaciones expresadas como texto. |
| `def _split_type_arguments(value)`  (L695) | Divide argumentos de tipo respetando corchetes anidados. |
| `def get_action_registry()`  (L1204) | Obtiene el singleton de ActionRegistry con inicialización segura. |
| `def register_action(name, description, action_type, category, tags, parameters, confidence_threshold, preconditions, effects, cost, dependencies, capability, application, required_resources, requires_ui_element, success_checker, planner_enabled, preconditions_functions, effects_functions)`  (L1213) | Decorador de conveniencia para registrar acciones en el singleton. |
| `def register_module(module_path)`  (L1258) | Registra acciones decoradas que se encuentren en el módulo indicado. |

<a name="src-hands-application_preflight-py"></a>
### `src/hands/application_preflight.py` [894 líneas] — Preflight de aplicaciones para JARVIS.

**Descripción:** Preflight de aplicaciones para JARVIS.

**Importaciones:** 12.

`class PreflightResult`  (línea 41) — Resultado estructurado del preflight.

**Decoradores:** `@dataclass(frozen=True)`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |

`class ApplicationPreflight`  (línea 70) — Analiza una aplicación antes de que CalibrationManager la abra.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def check(application)` | Analiza una aplicación sin ejecutarla. |
| `def check_application(application)` | Versión tipada del chequeo principal. |
| `def is_safe_to_calibrate(application)` | Indica si el resultado actual permite iniciar una calibración. |
| `def check_login_state(application)` | Evalúa únicamente el conocimiento explícito de login disponible. |
| `def check_resources(application)` | Evalúa recursos explícitamente conocidos por la aplicación. |
| `def _name_is_blocked(name)` |  |
| `def _app_id_is_blocked(app_id)` |  |
| `def _resolve_resources_status(application)` |  |
| `def _optional_bool(value)` |  |
| `def resolve_executable(name, app_id)` |  |
| `def _resolve_from_apps_folder(name, app_id)` |  |
| `def _resolve_from_target_string(target)` |  |
| `def _is_executable(path)` |  |
| `def inspect_executable_manifest(executable_path)` |  |
| `def _parse_manifest_file(path)` |  |
| `def _parse_manifest_xml(raw)` |  |
| `def _extract_embedded_manifest(executable_path)` | Extrae RT_MANIFEST del PE sin ejecutar el binario. |
| `def _result(allowed, reason, executable_path, requires_elevation, confidence, availability, login_required, logged_in, resources_available, blocked_by)` |  |
| `def clear_cache()` | Limpia resultados de resolución y manifest. |
| `def _normalized_values(values)` |  |
| `def _normalize(value)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_application_preflight()`  (L888) |  |

<a name="src-hands-applications_core-py"></a>
### `src/hands/applications_core.py` [1522 líneas] — Sistema de conocimiento de aplicaciones para planificación jerárquica.

**Descripción:** Sistema de conocimiento de aplicaciones para planificación jerárquica. Incluye el campo `description` en el modelo `UIElement` y lo propaga en serialización, reconstrucción, consulta de elementos y registro de aplicaciones personalizadas.

**Importaciones:** 16.

`class ApplicationCapability(Enum)`  (línea 35) — Capacidades que puede ofrecer una aplicación.

_Sin métodos definidos en el AST._

`class ApplicationState(Enum)`  (línea 63) — Estados posibles de una aplicación.

_Sin métodos definidos en el AST._

`class UIElement`  (línea 77) — Elemento UI de una aplicación.

**Decoradores:** `@dataclass`

**Campos:** `name`, `type`, `description` (str, vacío por defecto), `required_capability`, `coordinates`, `screen`, `calibration_data`.

Métodos:

| Firma | Docstring |
|---|---|
| `def is_calibrated()` | Comprueba si existe información de coordenadas utilizable. |
| `def _is_coordinate_pair(value, y_value)` | Valida una pareja de coordenadas sin asumir un formato único. |

`class ApplicationCapabilityDef`  (línea 117) — Definición de una capacidad de aplicación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class ApplicationKnowledge`  (línea 137) — Conocimiento estructurado de una aplicación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def get_capability(capability_name)` | Obtiene una capacidad por nombre. |
| `def get_ui_element(element_name)` | Obtiene un elemento UI por nombre. |
| `def is_capable(capability)` | Comprueba si la aplicación posee una capacidad específica. |
| `def get_calibrated_elements()` | Obtiene los elementos UI calibrados. |

`class ApplicationManager`  (línea 232) — Gestor del conocimiento estructurado de aplicaciones.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _normalize_name(app_name)` | Normaliza nombres habituales de aplicaciones a una clave interna. |
| `def _initialize_applications()` | Inicializa el conocimiento de las aplicaciones base. |
| `def register_application(app)` | Registra una aplicación en memoria y en el gestor. |
| `def get_application(app_name)` | Obtiene una aplicación por nombre o alias. |
| `def _resolve_alias(normalized_name)` | Resuelve un alias dinámico contra las aplicaciones ya registradas. |
| `def get_applications_by_type(app_type)` | Obtiene aplicaciones por tipo. |
| `def get_applications_by_capability(capability)` | Obtiene aplicaciones con una capacidad determinada. |
| `def _reconstruct_capabilities(capability_strings)` | Convierte una lista de strings de capacidad en ApplicationCapabilityDef. |
| `def _reconstruct_ui_elements(elements_data)` | Reconstruye la lista de :class:`UIElement` desde ``properties``, capturando el campo ``description`` cuando está presente. |
| `def _reconstruct_states(states_data)` | Reconstruye la lista de :class:`ApplicationState` desde ``properties``. |
| `def _reconstruct_application(entity)` | Reconstruye un objeto ApplicationKnowledge desde una Entity. |
| `def _load_custom_applications()` | Carga aplicaciones personalizadas persistidas en memoria. |
| `def get_application_capabilities(app_name)` | Obtiene capacidades de una aplicación en formato de planificación. |
| `def get_application_ui_elements(app_name)` | Obtiene los elementos UI conocidos de una aplicación, incluyendo el campo ``description`` de cada uno. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _reconstruct_metadata(entity)`  (L197) | Construye el dict de metadata para una ApplicationKnowledge reconstruida. |
| `def _serialize_ui_element(element)`  (L212) | Serializa un :class:`UIElement` a un dict JSON-friendly, incluyendo siempre el campo ``description``. |
| `def get_application_manager()`  (L754) | Obtiene la instancia global del gestor de aplicaciones. |
| `def open_application(app_name)`  (L785) | Abre una aplicación conocida y valida su disponibilidad. |
| `def close_application(app_name)`  (L831) | Cierra una aplicación por proceso sin tocar otras aplicaciones. |
| `def wait_for_application_state(app_name, target_state, timeout)`  (L889) | Espera un estado de aplicación conocido. |
| `def calibrate_application_ui(app_name, elements, screen)`  (L941) | Calibra una aplicación específica mediante CalibrationManager. |
| `def calibrar_aplicaciones(force)`  (L1021) | Ejecuta la acción global de calibración. |
| `def calibrate_applications(force)`  (L1066) | Alias programático de calibrar_aplicaciones(). |
| `def _call_calibrate_all_applications(manager, force)`  (L1075) | Invoca la calibración global compatible con managers antiguos y nuevos. |
| `def _check_application_available(app)`  (L1101) | Comprueba si el ejecutable configurado está disponible. |
| `def _check_application_login(app)`  (L1115) | Comprueba el estado de login cuando exista un backend para ello. |
| `def _looks_like_global_report(value)`  (L1123) | Identifica el contrato agregado del orquestador global. |
| `def _build_global_calibration_report(raw_results)`  (L1131) | Convierte resultados del CalibrationManager en un informe estable. |
| `def get_available_commands()`  (L1242) | Obtiene los comandos registrados. |
| `def navigate_to_url(url)`  (L1247) | Abre una URL en el navegador predeterminado. |
| `def abrir_youtube()`  (L1266) |  |
| `def abrir_gmail()`  (L1273) |  |
| `def get_application_knowledge(app_name)`  (L1284) | Obtiene conocimiento estructurado de una aplicación. |
| `def get_applications_by_capability(capability_name)`  (L1307) | Obtiene aplicaciones que tienen una capacidad específica. |
| `def register_custom_application(app_config)`  (L1318) | Registra una aplicación personalizada, aceptando ``description`` en cada elemento de ``ui_elements``. |

<a name="src-hands-calibration_manager-py"></a>
### `src/hands/calibration_manager.py` [2343 líneas] — Gestor universal de calibración de aplicaciones para JARVIS.

**Descripción:** Gestor universal de calibración de aplicaciones para JARVIS.

**Importaciones:** 27.

`class WINDOWPLACEMENT(ctypes.Structure)`  (línea 73)

_Sin métodos definidos en el AST._

`class ApplicationType(Enum)`  (línea 89)

_Sin métodos definidos en el AST._

`class CalibrationPreflightResult`  (línea 103)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |

`class CalibrationResult`  (línea 123)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def get(key, default)` |  |
| `def to_dict()` |  |

`class _WindowStateSnapshot`  (línea 152)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class CalibrationManager`  (línea 170) — Coordinador universal de calibración multiaplicación y multimonitor.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _register_builtin_calibrators()` | Prepara el registro de extensiones específicas sin usarlas como flujo principal. |
| `def register_calibrator(application_name, calibrator)` |  |
| `def get_available_applications()` |  |
| `def get_supported_applications()` |  |
| `def set_preflight_checker(checker)` |  |
| `def _normalize_preflight_result(result, application, source)` |  |
| `def preflight_application(application)` |  |
| `def get_application_calibration_capability(application)` |  |
| `def _reset_application_metadata_cache()` |  |
| `def _normalize_filesystem_path(path)` |  |
| `def _normalize_executable_name(path)` |  |
| `def _register_application_metadata(metadata)` |  |
| `def _load_application_installation_metadata()` |  |
| `def _get_application_metadata(name, app_id)` |  |
| `def discover_applications()` | Descubre aplicaciones GUI sin limitarse a una lista de apps conocidas. |
| `def _is_vscode_application(name, app_id)` |  |
| `def _is_game_launcher_application(name, app_id)` |  |
| `def _is_game_launcher_executable(path)` |  |
| `def _looks_like_game_launch_arguments(name, arguments)` |  |
| `def _is_game_installation_path(path)` |  |
| `def _is_game_application(name, app_id)` |  |
| `def _is_elevation_risk_application(name, app_id)` |  |
| `def _looks_like_console_or_cli_launcher(normalized_name)` |  |
| `def _should_ignore_application(name, app_id)` |  |
| `def _get_windows()` |  |
| `def _get_window_handle(window)` |  |
| `def _get_window_handles()` |  |
| `def _win32_is_window(hwnd)` |  |
| `def _win32_is_visible(hwnd)` |  |
| `def _win32_is_enabled(hwnd)` |  |
| `def _win32_get_class_name(hwnd)` |  |
| `def _win32_get_window_title(hwnd)` |  |
| `def _win32_get_window_rect(hwnd)` |  |
| `def _win32_get_owner(hwnd)` |  |
| `def _win32_get_style(hwnd)` |  |
| `def _win32_get_exstyle(hwnd)` |  |
| `def _win32_is_gui_window(cls, hwnd, allow_console)` |  |
| `def _window_is_usable(cls, window, allow_console)` |  |
| `def _get_window_geometry(window)` | Devuelve geometría utilizable incluso cuando la ventana está minimizada. |
| `def _capture_window_state(hwnd)` |  |
| `def _restore_window_state(hwnd, snapshot)` |  |
| `def _get_window_by_handle(hwnd)` |  |
| `def _get_window_process_id(window)` |  |
| `def _get_window_process_name(cls, window)` |  |
| `def _get_process_ids()` |  |
| `def _get_process_tree(root_pid, before_pids)` |  |
| `def _is_process_alive(pid)` |  |
| `def _is_process_elevated(pid)` |  |
| `def _expected_process_names(application_name, app_id)` | Obtiene nombres de proceso esperados para una aplicación. |
| `def _score_window_for_application(window, application_name, app_id)` |  |
| `def _find_existing_application_window(application_name, app_id)` |  |
| `def _reset_launch_context()` |  |
| `def launch_application(application)` | Reutiliza una ventana existente o lanza la aplicación de forma genérica. |
| `def _wait_for_application_window(application_name, app_id, before_hwnds, before_pids, timeout)` |  |
| `def _set_window_position(hwnd, x, y)` |  |
| `def _maximize_window(hwnd)` |  |
| `def _window_center(hwnd)` |  |
| `def _window_is_on_monitor(hwnd, monitor)` |  |
| `def _is_browser_application(application_name)` |  |
| `def _open_temporary_browser_tab(window, application_name)` | Abre una pestaña temporal en una ventana de navegador existente. |
| `def _close_temporary_browser_tab()` | Cierra únicamente la pestaña temporal creada por JARVIS. |
| `def _prepare_window_for_calibration(window, application_name)` | Restaura/maximiza una ventana y devuelve su monitor real. |
| `def move_window_to_monitor(window, monitor_number, application_name)` | Mueve temporalmente cualquier ventana calibrable al monitor indicado. |
| `def _post_close_message(hwnd)` |  |
| `def _post_system_close(hwnd)` |  |
| `def close_application_window(window, owned_hwnds)` |  |
| `def _get_visible_windows_for_pids(pids)` |  |
| `def _force_terminate_process(pid)` |  |
| `def _close_all_owned_windows(primary_window, owned_hwnds, owned_pids)` |  |
| `def is_application_calibrated(application)` |  |
| `def _get_registered_calibrator(application_name)` |  |
| `def _instantiate_registered_calibrator(entry)` |  |
| `def _invoke_registered_calibrator(calibrator, monitor_number)` | Ejecuta una API de calibrador registrado sin acoplar el gestor a una app. |
| `def _normalize_registered_result(application_name, screen_number, raw_result)` |  |
| `def _calibrate_registered_application(application_name, screen_number)` |  |
| `def calibrate_application(application, screen_number)` | Calibra cualquier aplicación mediante un único flujo universal. |
| `def _get_monitors_to_calibrate(screen_number)` |  |
| `def _calibrate_open_window(application_name, window, screen_number)` |  |
| `def calibrate_all_applications(applications, force)` |  |
| `def _extract_elements(analysis)` |  |
| `def _extract_element_center(element)` |  |
| `def _build_application_coordinates(application_results)` |  |
| `def _save_application_calibration(application_name, calibration_results)` |  |
| `def _save_coordinate_map(application_name, coordinates)` |  |
| `def _resolve_application(application)` |  |
| `def _resolve_application_list(applications)` |  |
| `def _get_application_type(application_name)` |  |
| `def _get_storage_application_key(cls, application_name)` |  |
| `def _normalize_application_name(name)` |  |
| `def _normalize_element_name(name)` |  |
| `def get_calibration_statistics()` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_calibration_manager()`  (L2339) |  |

<a name="src-hands-calibrator-py"></a>
### `src/hands/calibrator.py` [1059 líneas] — Fachada y capacidades de calibración para JARVIS.

**Descripción:** Fachada y capacidades de calibración para JARVIS.

**Importaciones:** 21.

`class CalibrationPolicy(Enum)`  (línea 36)

_Sin métodos definidos en el AST._

`class CalibrationStatus(Enum)`  (línea 43)

_Sin métodos definidos en el AST._

`class CalibrationElement`  (línea 52)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class CalibrationCapability`  (línea 67)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class CalibrationStrategy(ABC)`  (línea 78)

Métodos:

| Firma | Docstring |
|---|---|
| `def can_calibrate(element)` |  |
| `def calibrate(element)` |  |
| `def get_applicable_applications()` |  |

`class UniversalVisualCalibrationStrategy(CalibrationStrategy)`  (línea 92) — Estrategia visual delegada por completo al CalibrationManager.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def can_calibrate(element)` |  |
| `def calibrate(element)` |  |
| `def _resolve_monitor_number(element)` |  |
| `def get_applicable_applications()` |  |
| `def _result_to_dict(result)` |  |
| `def _find_element_coordinates(result, element_name, monitor_number)` |  |
| `def _find_element_confidence(cls, result, element_name)` |  |
| `def _normalize_element_name(value)` |  |
| `def _get_calibration_manager()` |  |

`class KeyboardShortcutStrategy(CalibrationStrategy)`  (línea 340) — Estrategia alternativa basada en atajos de teclado.

Métodos:

| Firma | Docstring |
|---|---|
| `def can_calibrate(element)` |  |
| `def calibrate(element)` |  |
| `def get_applicable_applications()` |  |

`class EnhancedCalibrator`  (línea 361) — Sistema de capacidades de calibración compatible con el planner.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _initialize_capabilities()` |  |
| `def get_calibration_capability(capability_id)` |  |
| `def get_available_capabilities()` |  |
| `def check_element_calibration(element_id)` |  |
| `def can_use_element(element_id, current_state)` |  |
| `def calibrate_element_if_needed(element_id, current_state)` |  |
| `def _find_alternative_strategy(element)` |  |
| `def register_element(element)` |  |
| `def get_element_coordinates(element_id)` |  |
| `def create_calibration_node(element_id)` |  |
| `def get_calibration_requirements_for_goal(goal)` |  |
| `def calibrate_applications(app_name, force)` | Entrada legacy y global compatible con CalibrationManager. |
| `def _calibrate_single_application(manager, app_name, force)` |  |
| `def _build_single_application_report(app_name, results, monitor_count)` |  |
| `def _call_global_manager(method, force)` |  |
| `def _normalize_global_result(result)` |  |
| `def _looks_like_global_report(value)` |  |
| `def _result_to_dict(result)` |  |
| `def _extract_element_count(result)` |  |
| `def calibrate_chrome_both_screens()` | Compatibilidad legacy; delega en la misma API de aplicación. |
| `def _verify_system()` |  |
| `def get_calibration_statistics()` |  |
| `def _is_already_calibrated(app_name)` |  |
| `def _save_organized_results(app_name, results)` | Compatibilidad legacy; la persistencia pertenece al manager. |
| `def _build_setup_info()` |  |
| `def _has_calibration_command(app_name)` |  |
| `def _open_app_on_monitor(app_name, monitor_num)` | Compatibilidad legacy con flujo genérico del CalibrationManager. |
| `def _close_app(app_name)` | Solo cierra recursos creados por el flujo de calibración, nunca una app del usuario por nombre. |
| `def _get_calibration_manager()` |  |
| `def _normalize_name(value)` |  |
| `def _single_failure_report(app_name, error)` |  |
| `def _failure_report(error)` |  |

`class Calibrator`  (línea 1023) — Fachada de compatibilidad para el sistema mejorado.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def calibrate_applications(app_name, force)` |  |
| `def calibrate_chrome_both_screens()` |  |
| `def _build_setup_info()` |  |
| `def _verify_system()` |  |
| `def _has_calibration_command(app_name)` |  |
| `def _open_app_on_monitor(app_name, monitor_num)` |  |
| `def _close_app(app_name)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_enhanced_calibrator()`  (L1016) |  |
| `def calibrate_chrome_both_screens()`  (L1057) | Función global legacy. |

## 🌐 `src/hands/chrome/`

<!-- src/hands/chrome -->

<a name="src-hands-chrome-__init__-py"></a>
### `src/hands/chrome/__init__.py` [75 líneas] — Módulo específico para Google Chrome con sistema de acciones registrado.

**Descripción:** Módulo específico para Google Chrome con sistema de acciones registrado.

**Importaciones:** 4.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def abrir_chrome_action()`  (L31) | Acción wrapper para abrir Chrome. |
| `def abrir_chrome_pantalla_action(pantalla)`  (L42) | Acción wrapper para abrir Chrome en pantalla específica. |
| `def calibrar_chrome_action()`  (L53) | Acción wrapper para calibrar Chrome. |

<a name="src-hands-chrome-chrome-py"></a>
### `src/hands/chrome/chrome.py` [500 líneas] — Funciones específicas para Google Chrome.

**Descripción:** Funciones específicas para Google Chrome.

**Importaciones:** 13.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def abrir_chrome()`  (L39) | Abre específicamente Google Chrome, sin depender del navegador predeterminado. |
| `def abrir_chrome_pantalla(pantalla)`  (L66) | Abre Chrome en un monitor específico. |
| `def cerrar_chrome()`  (L110) | Cierra las ventanas de Google Chrome. |
| `def calibrar_chrome(pantalla)`  (L151) | Calibra Chrome usando el flujo universal de aplicaciones. |
| `def mover_chrome_pantalla(pantalla)`  (L203) | Mueve una ventana de Chrome al monitor solicitado. |
| `def maximizar_chrome()`  (L260) | Maximiza la ventana de Chrome preferentemente la que está en primer plano. |
| `def _get_chrome_executable()`  (L291) | Busca chrome.exe en ubicaciones habituales de Windows. |
| `def _abrir_chrome_desde_ruta()`  (L313) | Abre Chrome directamente; solo usa webbrowser como último fallback. |
| `def _get_chrome_windows(screen_manager)`  (L338) | Obtiene ventanas de Chrome mediante ScreenManager, si está disponible. |
| `def _select_preferred_chrome_window(screen_manager, chrome_windows)`  (L352) | Selecciona la ventana Chrome en primer plano cuando sea posible. |
| `def _verificar_chrome_abierto()`  (L371) | Verifica si existe al menos una ventana visible de Chrome. |
| `def _verificar_chrome_instalado()`  (L394) | Verifica si Chrome está instalado o resoluble en el sistema. |
| `def _capturar_chrome()`  (L416) | Captura una ventana de Chrome. |
| `def get_chrome_commands()`  (L459) | Obtiene los comandos específicos de Chrome. |
| `def get_chrome_action_commands()`  (L471) | Escanea el módulo y devuelve las funciones registradas como acciones. |

<a name="src-hands-chrome-chrome_calibrator-py"></a>
### `src/hands/chrome/chrome_calibrator.py` [56 líneas] — Compatibilidad para Chrome sobre el calibrador universal de aplicaciones.

**Descripción:** Compatibilidad para Chrome sobre el calibrador universal de aplicaciones.

**Importaciones:** 4.

`class ChromeCalibrator`  (línea 23) — Adaptador legacy que usa exactamente el flujo universal.

Métodos:

| Firma | Docstring |
|---|---|
| `def calibrate_chrome(monitor_num)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def calibrar_chrome()`  (L13) | Compatibilidad legacy: delega en el flujo universal. |

## 🖐️ `src/hands/`

<!-- src/hands -->

<a name="src-hands-coordinate_manager-py"></a>
### `src/hands/coordinate_manager.py` [1113 líneas] — Gestor unificado de coordenadas (FASE 13)

**Descripción:** Fuente única de verdad de coordenadas UI calibradas. Lee `data/macros_coords.json` construyendo `UIResource`s por monitor `sN`; gestiona capacidades UI (`focus_element`/`click_element`/`type_in_element`) con precondiciones/efectos/alternativas; convierte entre `RELATIVE_SCREEN`, `ABSOLUTE_DESKTOP` y `WINDOW_RELATIVE`.

**Características:**

- FASE 13: coordinación multi-monitor
- `UIResource` con coordenadas/regiones por monitor
- Capacidades UI pre/e post-condicionadas
- Lectura de `macros_coords.json` + formato legacy

**Importaciones:** 12.

`class ResourceType(Enum)`  (línea 37) — Tipos de recursos UI gestionados por el coordinate manager.

_Sin métodos definidos en el AST._

`class CalibrationStrategy(Enum)`  (línea 47) — Estrategias de calibración disponibles.

_Sin métodos definidos en el AST._

`class UIResource`  (línea 58) — Recurso UI calibrado utilizable por acciones del planificador.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def is_usable()` |  |
| `def get_coordinates_for_screen(screen_number)` |  |
| `def get_region_for_screen(screen_number)` |  |
| `def get_best_coordinates()` | Devuelve coordenadas del monitor activo o, en su defecto, de cualquier monitor calibrado. |
| `def get_alternatives()` |  |
| `def can_use_fallback_strategy(strategy_name)` |  |

`class UICapability`  (línea 148) — Capacidad UI que puede ser utilizada por una acción.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, description, required_resources)` |  |
| `def can_execute_with_resources(available_resources)` |  |

`class CoordinateSystem(Enum)`  (línea 166) — Sistemas de coordenadas soportados por JARVIS.

_Sin métodos definidos en el AST._

`class BoundingBox`  (línea 175) — Rectángulo delimitador de un elemento.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def right()` |  |
| `def bottom()` |  |
| `def center_x()` |  |
| `def center_y()` |  |
| `def center()` |  |
| `def to_dict()` |  |

`class ElementInfo`  (línea 215) — Información de un elemento calibrado (compatibilidad).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def get_absolute_coordinates()` |  |

`class CoordinateManager`  (línea 254) — Gestor centralizado de conocimiento UI y coordenadas calibradas.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _initialize_base_capabilities()` |  |
| `def macros_coords_path()` |  |
| `def _load_ui_knowledge()` |  |
| `def _process_ui_knowledge()` |  |
| `def _create_resource_from_knowledge(resource_id, app_name, element_name, element_data)` |  |
| `def _resource_type_for_element(element_type)` |  |
| `def _parse_screen_data(element_data)` |  |
| `def register_ui_resource(resource)` |  |
| `def get_ui_resource(resource_id)` |  |
| `def get_available_resources(application)` |  |
| `def find_resources_by_type(resource_type, application)` |  |
| `def has_resource(resource_id)` |  |
| `def get_resource_alternatives(resource_id)` |  |
| `def get_fallback_strategies(resource_id)` |  |
| `def get_capabilities_for_resources(resource_ids)` |  |
| `def can_execute_capability(capability_name, resource_ids)` |  |
| `def get_capability_alternatives(capability_name)` |  |
| `def get_calibration_strategy(application, element_type)` | Devuelve la estrategia permitida para una aplicación/elemento. |
| `def is_application_calibrable(application)` |  |
| `def can_calibrate_element(application, element_type)` |  |
| `def get_execution_strategy_for_action(action_id, resource_id)` |  |
| `def get_resource_coordinates(resource_id, screen_number)` |  |
| `def validate_resource_for_action(action_id, resource_id)` |  |
| `def load_from_macros_coords(calibration_data)` | Carga recursos desde ``calibraciones`` o, para compatibilidad, desde ``legacy_data.macros``. |
| `def _create_legacy_resource(resource_id, app_name, element_name, element_data)` |  |
| `def _infer_element_type(element_name)` |  |
| `def get_calibrated_coordinate(calibration_data, application_name, element_name, screen_number)` |  |
| `def _get_legacy_calibrated_coordinate(calibration_data, application_name, element_name, screen_number)` |  |
| `def _case_insensitive_dict_get(data, key)` |  |
| `def monitor_number_from_object(monitor)` | Extrae un número de monitor sin asumir un atributo concreto. |
| `def get_screen_key(screen_number)` |  |
| `def screen_number_from_key(screen_key)` |  |
| `def get_screen_number_from_key(screen_key)` |  |
| `def _read_coordinate_value(value)` |  |
| `def validate_coordinates(x, y, screen_width, screen_height)` |  |
| `def validate_bounding_box(bbox, screen_width, screen_height)` |  |
| `def get_window_bounding_box(window_title)` | Compatibilidad legacy: obtiene una ventana por título. |
| `def _get_window_rect(window)` | Obtiene geometría de ventana priorizando el rectángulo normal de Win32. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_coordinate_manager()`  (L1095) | Obtiene la instancia global del gestor de coordenadas. |

## 🌐 `src/hands/edge/`

<!-- src/hands/edge -->

<a name="src-hands-edge-__init__-py"></a>
### `src/hands/edge/__init__.py` [3 líneas] — Módulo específico para Microsoft Edge.

**Descripción:** Módulo específico para Microsoft Edge.

**Importaciones:** 0.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-hands-edge-calibrator_edge-py"></a>
### `src/hands/edge/calibrator_edge.py` [237 líneas] — Adaptador de compatibilidad para la calibración de Microsoft Edge.

**Descripción:** Adaptador de compatibilidad para la calibración de Microsoft Edge.

**Importaciones:** 3.

`class EdgeCalibrator`  (línea 43) — Adaptador legacy hacia CalibrationManager.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def calibrate_edge_both_screens()` | Mantiene la API antigua por compatibilidad. |
| `def calibrate_edge()` | API moderna de compatibilidad. |
| `def _calibrate_edge_universal()` | Delega Edge en CalibrationManager. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def calibrate_edge()`  (L196) | Función pública de compatibilidad. |

<a name="src-hands-edge-edge-py"></a>
### `src/hands/edge/edge.py` [568 líneas] — Funciones específicas para Microsoft Edge.

**Descripción:** Funciones específicas para Microsoft Edge.

**Importaciones:** 11.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _get_edge_windows()`  (L32) | Obtiene las ventanas visibles/localizables de Microsoft Edge. |
| `def _get_edge_window_info(window)`  (L61) | Obtiene metadatos y geometría actual de una ventana de Edge. |
| `def _find_edge_window_on_monitor(pantalla)`  (L86) | Busca una ventana de Edge cuyo centro esté dentro del monitor indicado. |
| `def _select_edge_window(preferred_monitor)`  (L110) | Selecciona una ventana Edge, priorizando el monitor indicado. |
| `def abrir_edge_pantalla(pantalla)`  (L131) | Abre Microsoft Edge y lo posiciona en la pantalla solicitada. |
| `def abrir_edge_pestana(pantalla)`  (L189) | Abre una nueva pestaña de Edge en la pantalla solicitada. |
| `def _candidate_edge_paths()`  (L257) | Devuelve rutas habituales donde puede estar instalado Edge. |
| `def _abrir_edge_desde_ruta()`  (L285) | Abre Edge desde una instalación local conocida. |
| `def _verificar_edge_abierto()`  (L318) | Verifica si Edge está abierto y visible. |
| `def _verificar_edge_instalado()`  (L336) | Verifica si Microsoft Edge está instalado. |
| `def _move_edge_window(window, monitor)`  (L385) | Mueve una ventana Edge al origen del monitor y trata de maximizarla. |
| `def _mover_edge_a_pantalla(pantalla_num)`  (L402) | Mueve una ventana de Edge al monitor solicitado. |
| `def _cerrar_edge()`  (L444) | Cierra una ventana visible de Edge. |
| `def _calibrar_edge()`  (L466) | Compatibilidad con la implementación antigua. |
| `def _generar_coordenadas_edge(tipo_elemento)`  (L497) | Compatibilidad con código antiguo; no genera coordenadas artificiales. |
| `def _capturar_edge()`  (L512) | Captura la ventana visible de Edge. |
| `def get_edge_commands()`  (L554) | Obtiene los comandos legacy de Edge. |

## 🖐️ `src/hands/`

<!-- src/hands -->

<a name="src-hands-executor-py"></a>
### `src/hands/executor.py` [1861 líneas] — Ejecutor mejorado con HTN

**Descripción:** Corazón de la ejecución: recibe un plan (lista de nodos), ejecuta nodo a nodo (timeout vía `ThreadPoolExecutor`), verifica éxito (success_checker o `ActionInfo.verify_success`), aplica efectos a `ExecutionState`, y re-planifica o intenta alternativas tras fallo. Registra nodo/plan en `LearningSystem` (FASE 18).

**Características:**

- Ejecución serial con bloqueo reentrante
- Verificación de precondiciones/efectos consensuados con el planificador
- Timeout por nodo vía `ThreadPoolExecutor`
- Alternativas + replanificación por fallo
- Integración con `LearningSystem` (FASE 18)
- Compatibilidad legacy (FASE 16)

**Importaciones:** 21.

`class ExecutionStatus(Enum)`  (línea 82) — Estados de ejecución de un nodo o plan.

_Sin métodos definidos en el AST._

`class ExecutionResult`  (línea 99) — Resultado de ejecución de un nodo o plan.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __bool__()` | Permite que los adaptadores legacy respeten el estado real del resultado. |
| `def to_dict()` |  |

`class ExecutionState`  (línea 133) — Estado actual del mundo para ejecución.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def update(update_data)` | Actualiza el estado y fusiona los diccionarios anidados. |
| `def to_dict()` | Devuelve una instantánea independiente del estado, incluidos campos extendidos. |

`class Executor`  (línea 162) — Ejecutor mejorado con soporte para planificación jerárquica y replanificación.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(action_registry)` | Inicializa el ejecutor sin importar Planner durante la carga del módulo. |
| `def _initialize_state()` | Inicializa el estado del mundo. |
| `def execute_plan(plan, plan_id, max_retries, timeout_per_node)` | Ejecuta un plan de forma secuencial; no declara éxito ante un fallo. |
| `def _execute_plan_serial(plan, plan_id, max_retries, timeout_per_node)` |  |
| `def _normalize_plan_node(raw_node, index)` |  |
| `def _execute_node(node, node_id, max_retries, timeout)` | Ejecuta un paso y solo reintenta cuando se declara seguro. |
| `def _safe_cost(value, default)` |  |
| `def _verify_node_success(node, result)` | Verifica confirmaciones explícitas sin confundir el estado previo con el posterior. |
| `def _replan_after_failure(plan, failed_node_index, current_state)` | Construye un plan alternativo sin tocar el plan original. |
| `def _find_alternative_nodes(failed_node, current_state)` | Encuentra hasta tres acciones registradas que ofrezcan capacidad compatible. |
| `def _extract_capability_from_action(action_name)` | Extrae la capacidad principal de un nombre de acción. |
| `def _action_provides_capability(action_info, capability)` | Comprueba compatibilidad por nombre, tipo, categoría o capacidades declaradas. |
| `def _should_replan(plan, failed_node_index)` | Determina si se debe replanificar después de un fallo. |
| `def execute_plan_with_replan(plan, goal, max_replan_attempts)` | Ejecuta un plan con replanificación local y registro del resultado real. |
| `def _update_world_state_after_failure(node, result)` | Registra el fallo y su timestamp sin alterar estados de éxito. |
| `def _goal_achieved(goal, current_state)` | Comprueba objetivos conocidos usando tanto estado plano como estado anidado. |
| `def _execute_node_action(node, timeout)` | Ejecuta callback explícito o acción registrada vinculada al nodo. |
| `def _check_node_preconditions(node)` | Evalúa todas las precondiciones; las desconocidas no se consideran verdaderas. |
| `def _evaluate_condition(condition)` | Evalúa condiciones tipadas, callbacks, diccionarios o claves de estado. |
| `def _get_nested_value(state, key)` |  |
| `def _try_alternative(node, failed_result)` | Prueba alternativas declaradas, sin repetir la acción original. |
| `def _update_world_state(node, result)` | Actualiza el mundo únicamente tras confirmar el éxito del nodo. |
| `def _apply_state_updates(updates)` | Fusiona actualizaciones explícitas con el estado runtime. |
| `def execute_action(action_name, parameters, state, verify, timeout)` | Ejecuta una acción registrada y verifica su resultado antes de confirmarlo. |
| `def _record_learning_action(action_name, success, execution_time, action_info, verify, parameters)` | Registra aprendizaje sin convertir un fallo de telemetría en fallo de acción. |
| `def can_execute(action_name, parameters, state)` | Comprueba si una acción registrada puede ejecutarse ahora. |
| `def process_and_execute(llm_response)` | Procesa respuesta LLM y ejecuta comando (mantenido para compatibilidad). |
| `def _execute_legacy_or_registered(command_name, positional_args)` | Ejecuta mediante ActionRegistry o fallback legacy. |
| `def _positional_to_named_parameters(action_info, positional_args)` | Convierte argumentos posicionales a nombrados. |
| `def _parse_args(args_str)` | Parsea argumentos mediante ast.literal_eval. |
| `def _get_legacy_function(command_name)` | Busca función legacy en módulos. |
| `def get_current_state()` | Obtiene el estado actual del mundo. |
| `def update_state(update_data)` | Actualiza el estado del mundo. |
| `def get_action_stats()` | Obtiene estadísticas de ejecución de acciones. |
| `def _record_action_execution(action_name, success, execution_time)` | Registra ejecución de acción para estadísticas. |
| `def _get_screen_state()` | Obtiene estado actual de la pantalla para aprendizaje. |
| `def get_learning_insights()` | Obtiene insights del sistema de aprendizaje (FASE 18). |
| `def get_action_learning_insights(action_name)` | Obtiene insights específicos de una acción (FASE 18). |
| `def get_cost_adjustments()` | Obtiene ajustes de coste aprendidos (FASE 18). |
| `def export_learning_data(filepath)` | Exporta datos de aprendizaje (FASE 18). |
| `def import_learning_data(filepath)` | Importa datos de aprendizaje (FASE 18). |
| `def clear_learning_data()` | Limpia datos de aprendizaje (FASE 18). |
| `def enable_learning(enabled)` | Habilita o deshabilita el aprendizaje (FASE 18). |
| `def _record_command_execution(command_name, success)` | Registra ejecución de comando legacy. |
| `def list_commands()` | Lista todas las acciones conocidas. |
| `def get_plannable_actions()` | Obtiene acciones disponibles para planificación. |
| `def get_action_info(action_name)` | Obtiene información de una acción específica. |
| `def execute_goal(goal, max_planning_time, find_alternatives, plan_id, enable_learning)` | Planifica y ejecuta un objetivo, devolviendo el resultado confirmado. |
| `def _get_state_for_planning()` | Devuelve una instantánea independiente y compatible del estado actual. |
| `def create_goal_from_command(command_name, parameters)` | Crea un objetivo a partir de un comando legacy. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _log(level, message)`  (L61) | Compatibilidad con llamadas antiguas al logger que incluían metadatos de línea. |
| `def get_executor()`  (L1852) | Obtiene el singleton global de Executor de manera segura ante concurrencia. |

## 🦊 `src/hands/firefox/`

<!-- src/hands/firefox -->

<a name="src-hands-firefox-__init__-py"></a>
### `src/hands/firefox/__init__.py` [3 líneas] — Módulo específico para Mozilla Firefox.

**Descripción:** Módulo específico para Mozilla Firefox.

**Importaciones:** 0.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-hands-firefox-calibrator_firefox-py"></a>
### `src/hands/firefox/calibrator_firefox.py` [235 líneas] — Adaptador de compatibilidad para la calibración de Mozilla Firefox.

**Descripción:** Adaptador de compatibilidad para la calibración de Mozilla Firefox.

**Importaciones:** 3.

`class FirefoxCalibrator`  (línea 46) — Adaptador legacy hacia CalibrationManager.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def calibrate_firefox_both_screens()` | Mantiene el nombre antiguo por compatibilidad. |
| `def calibrate_firefox()` | API moderna de compatibilidad. |
| `def _calibrate_firefox_universal()` | Delega Firefox al CalibrationManager universal. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def calibrate_firefox()`  (L194) | Función pública de compatibilidad. |

<a name="src-hands-firefox-firefox-py"></a>
### `src/hands/firefox/firefox.py` [638 líneas] — Funciones específicas para Mozilla Firefox.

**Descripción:** Funciones específicas para Mozilla Firefox.

**Importaciones:** 12.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _get_firefox_windows()`  (L36) | Obtiene las ventanas localizables de Mozilla Firefox. |
| `def _get_firefox_window_info(window)`  (L65) | Obtiene metadatos y geometría actual de una ventana de Firefox. |
| `def _find_firefox_window_on_monitor(pantalla)`  (L94) | Busca una ventana de Firefox cuyo centro esté dentro del monitor indicado. |
| `def _select_firefox_window(preferred_monitor)`  (L119) | Selecciona una ventana Firefox, priorizando el monitor indicado. |
| `def abrir_youtube()`  (L142) | Abre YouTube en el navegador predeterminado. |
| `def abrir_spotify()`  (L152) | Abre Spotify Web en el navegador predeterminado. |
| `def abrir_firefox_pantalla(pantalla)`  (L167) | Abre Mozilla Firefox y lo posiciona en la pantalla solicitada. |
| `def abrir_firefox_pestana(pantalla)`  (L223) | Abre una nueva pestaña de Firefox en la pantalla solicitada. |
| `def _candidate_firefox_paths()`  (L292) | Devuelve rutas habituales donde puede estar instalado Firefox. |
| `def _abrir_firefox_desde_ruta()`  (L323) | Abre Firefox desde una instalación local conocida. |
| `def _verificar_firefox_abierto()`  (L358) | Verifica si Firefox está abierto y visible. |
| `def _verificar_firefox_instalado()`  (L376) | Verifica si Mozilla Firefox está instalado. |
| `def _move_firefox_window(window, monitor)`  (L432) | Mueve una ventana Firefox al origen del monitor y trata de maximizarla. |
| `def _mover_firefox_a_pantalla(pantalla_num)`  (L455) | Mueve una ventana de Firefox al monitor solicitado. |
| `def _cerrar_firefox()`  (L504) | Cierra una ventana visible de Firefox. |
| `def _calibrar_firefox()`  (L526) | Compatibilidad con la implementación antigua. |
| `def _generar_coordenadas_firefox(tipo_elemento)`  (L554) | Compatibilidad con código legacy; no genera coordenadas artificiales. |
| `def _capturar_firefox()`  (L569) | Captura la ventana visible de Firefox. |
| `def get_firefox_commands()`  (L622) | Obtiene los comandos legacy de Firefox. |

## 🖐️ `src/hands/`

<!-- src/hands -->

<a name="src-hands-keyboard-py"></a>
### `src/hands/keyboard.py` [901 líneas] — Control del teclado

**Descripción:** Capa de capacidades migrada sobre `pyautogui` (`FAILSAFE`/`PAUSE` desde config). Cada acción (`type_text`, `press_key`, `hotkey`, ops de texto, navegación, shortcuts) es un `@keyboard_capability` con precondiciones/efectos/coste y se registra en `ActionRegistry`.

**Características:**

- Decorator `@keyboard_capability`
- Configuración de pyautogui desde config
- Integración con ActionRegistry

**Importaciones:** 9.

`class KeyModifier(Enum)`  (línea 69) — Modificadores de tecla soportados.

_Sin métodos definidos en el AST._

`class KeyboardCapabilities`  (línea 78) — Capacidades del teclado para el sistema de planificación.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class KeyboardCapabilitySystem`  (línea 734) — Sistema de capacidades del teclado para la planificación jerárquica.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` | Inicializar el sistema de capacidades. |
| `def _initialize_capabilities()` | Inicializar el catálogo de capacidades. |
| `def get_capabilities_for_context(context)` | Obtener capacidades que se pueden ejecutar con el contexto dado. |
| `def _check_conditions(conditions, context)` | Verificar si las condiciones se cumplen en el contexto dado. |
| `def can_execute_capability(capability_name, context)` | ¿Se puede ejecutar una capacidad con el contexto dado? |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def keyboard_capability(name, description, preconditions, effects, cost, required_resources, application, success_checker, planner_enabled, keyboard_action)`  (L99) | Decorador para registrar capacidades del teclado en el sistema de planificación. |
| `def type_text(text, interval, field_id)`  (L184) | Escribir texto en el campo activo o en un campo específico. |
| `def press_key(key, hold_time)`  (L230) | Presionar una tecla individual. |
| `def execute_hotkey()`  (L272) | Ejecutar combinación de teclas (hotkeys). |
| `def copy_text()`  (L321) | Copiar texto seleccionado al portapapeles. |
| `def paste_text()`  (L344) | Pegar texto desde el portapapeles. |
| `def cut_text()`  (L367) | Cortar texto seleccionado al portapapeles. |
| `def select_all_text()`  (L391) | Seleccionar todo el texto en el campo activo. |
| `def navigate_tab(forward)`  (L415) | Navegar entre campos con Tabulador. |
| `def navigate_enter()`  (L448) | Confirmar acción con la tecla Enter. |
| `def switch_window()`  (L473) | Cambiar a la siguiente ventana con Alt+Tab. |
| `def close_window()`  (L496) | Cerrar la ventana activa con Alt+F4. |
| `def open_start_menu()`  (L519) | Abrir el menú de inicio de Windows. |
| `def _get_typing_interval(interval)`  (L540) | Obtiene el intervalo de escritura (mantenido por compatibilidad). |
| `def escribir_texto(texto, interval)`  (L553) | Escribe texto en el campo activo (mantenido por compatibilidad). |
| `def presionar_enter()`  (L573) | Presiona la tecla Enter (mantenido por compatibilidad). |
| `def presionar_tecla(tecla)`  (L588) | Presiona una tecla específica (mantenido por compatibilidad). |
| `def copiar()`  (L609) | Ejecuta Ctrl+C (Copiar) (mantenido por compatibilidad). |
| `def pegar()`  (L624) | Ejecuta Ctrl+V (Pegar) (mantenido por compatibilidad). |
| `def cortar()`  (L639) | Ejecuta Ctrl+X (Cortar) (mantenido por compatibilidad). |
| `def seleccionar_todo()`  (L654) | Ejecuta Ctrl+A (Seleccionar todo) (mantenido por compatibilidad). |
| `def cambiar_ventana()`  (L669) | Ejecuta Alt+Tab (Cambiar ventana) (mantenido por compatibilidad). |
| `def cerrar_ventana()`  (L684) | Ejecuta Alt+F4 (Cerrar ventana) (mantenido por compatibilidad). |
| `def tecla_super()`  (L700) | Presiona la tecla Windows (Super) (mantenido por compatibilidad). |
| `def abrir_menu_inicio()`  (L713) | Abre el menú de inicio de Windows (mantenido por compatibilidad). |
| `def get_keyboard_capability_system()`  (L894) | Obtener la instancia global del sistema de capacidades del teclado. |

<a name="src-hands-mouse-py"></a>
### `src/hands/mouse.py` [129 líneas] — Control del ratón

**Descripción:** Primitivas `pyautogui` para mover, hacer clic y hacer scroll; auto-registradas como capacidades al importar.

**Características:**

- pyautogui
- registro automático de capacidades

**Importaciones:** 8.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def move_to_position(x, y, duration)`  (L16) | Mueve el ratón a una posición específica. |
| `def click_element(button, wait_after)`  (L44) | Realiza un clic con el ratón. |
| `def scroll_at_position(x, y, clicks, wait_after)`  (L74) | Realiza scroll en una posición específica. |
| `def register_mouse_capabilities()`  (L110) | Registra las capacidades del ratón en el sistema. |

## 🗺️ `src/hands/planner/`

<!-- src/hands/planner -->

<a name="src-hands-planner-__init__-py"></a>
### `src/hands/planner/__init__.py` [235 líneas] — Paquete de planificación de JARVIS.

**Descripción:** Paquete de planificación de JARVIS.

**Importaciones:** 11.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_htn_manager()`  (L128) | Obtiene el singleton HTN sin importar el gestor al cargar el paquete. |
| `def get_application_knowledge_integrator()`  (L135) | Obtiene el singleton del integrador de aplicaciones. |
| `def get_applications_by_capability(capability_name)`  (L144) | Busca aplicaciones por capacidad mediante el módulo correspondiente. |
| `def get_application_knowledge(app_name)`  (L151) | Obtiene las capacidades declaradas de una aplicación. |
| `def get_task_executor()`  (L158) | Obtiene el singleton TaskExecutor mediante importación diferida. |
| `def get_learning_system()`  (L165) | Obtiene el singleton del sistema de aprendizaje cuando se necesita. |
| `def get_preconditions_effects_manager()`  (L172) | Obtiene el singleton del gestor de precondiciones y efectos. |
| `def __getattr__(name)`  (L179) | Carga un componente bajo demanda y conserva el atributo en el paquete. |
| `def __dir__()`  (L200) | Incluye los componentes de carga perezosa en dir(paquete). |

<a name="src-hands-planner-application_integration-py"></a>
### `src/hands/planner/application_integration.py` [864 líneas] — Integración declarativa del conocimiento de aplicaciones con el planificador.

**Descripción:** Integración declarativa del conocimiento de aplicaciones con el planificador.

**Importaciones:** 12.

`class ApplicationKnowledgeIntegrator`  (línea 35) — Integra conocimiento estructurado de aplicaciones con el planificador.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _import_application_manager_factory()` | Carga la fábrica del gestor sin imponer una única ruta de importación. |
| `def _get_value(obj, key, default)` | Lee una clave tanto de diccionarios como de objetos/dataclasses. |
| `def _safe_copy(value, default)` |  |
| `def _normalize_name(value)` | Normaliza un nombre para IDs y claves de estado deterministas. |
| `def _capability_value(cls, capability)` | Obtiene el valor de una capacidad Enum, objeto, diccionario o string. |
| `def _capability_key(cls, capability)` |  |
| `def _as_list(value)` | Normaliza un valor o colección sin dividir strings/diccionarios. |
| `def _normalized_conditions(cls, value)` | Copia precondiciones/efectos evitando mutar el catálogo de origen. |
| `def _unique_nodes(nodes)` | Deduplica Nodes por ID preservando orden y datos ya recogidos. |
| `def _safe_cost(value, default)` | Convierte costes a números finitos no negativos. |
| `def _get_application(app_name)` |  |
| `def convert_application_to_nodes(app_name)` | Convierte una aplicación y sus capacidades en Nodes canónicos. |
| `def _create_application_node(app)` | Crea el nodo declarativo principal de la aplicación. |
| `def _create_capability_node(app, capability_def)` | Crea un nodo de acción reutilizable para una capacidad declarada. |
| `def _create_ui_element_node(app, element_name, capability_def)` | Crea un nodo declarativo para un elemento UI conocido o requerido. |
| `def _is_element_calibrated(cls, element)` |  |
| `def _validate_node_references(nodes)` | Comprueba las relaciones jerárquicas creadas durante la conversión. |
| `def _get_application_current_state(app_name)` | Obtiene propiedades persistidas de la aplicación si existen. |
| `def _generate_application_preconditions(app, current_state)` | Genera las condiciones de preparación declaradas para la aplicación. |
| `def _generate_application_effects(app)` | Declara que la aplicación está registrada/disponible, no abierta. |
| `def get_applications_by_capability(capability)` | Devuelve las aplicaciones que declaran una capacidad. |
| `def get_application_capabilities(app_name)` | Obtiene capacidades en formato declarativo, con fallback al catálogo. |
| `def get_ui_elements_for_capability(app_name, capability)` | Obtiene los elementos UI requeridos por una capacidad declarada. |
| `def is_application_capable(app_name, capability)` | Comprueba una capacidad utilizando el gestor o el catálogo de la app. |
| `def register_application_knowledge(app_config)` | Registra conocimiento mediante la API pública de applications_core. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_application_knowledge_integrator()`  (L810) | Obtiene la instancia global del integrador, inicializada una sola vez. |
| `def get_applications_by_capability(capability_name)`  (L820) | Compatibilidad legacy; utiliza ApplicationCapability cuando está disponible. |
| `def get_application_knowledge(app_name)`  (L854) | Compatibilidad legacy para consultar conocimiento de una aplicación. |

<a name="src-hands-planner-goal_state_mapper-py"></a>
### `src/hands/planner/goal_state_mapper.py` [1485 líneas] — Responsabilidades:

**Descripción:** Responsabilidades:

**Importaciones:** 9.

`class MappingType(Enum)`  (línea 30) — Tipos de mapeo soportados.

_Sin métodos definidos en el AST._

`class MappingResult`  (línea 40) — Resultado de una operación de mapeo.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class GoalStateMapper`  (línea 51) — Mapea Goal y World State al StateGraph.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(state_graph)` |  |
| `def map_goal_to_graph(goal, world_state)` | Mapea un objetivo y su contexto al grafo sin ejecutar acciones. |
| `def map_world_state_to_graph(world_state)` | Mapea el estado del mundo, tanto en formato canónico como legacy. |
| `def map_capabilities_to_graph(capabilities)` | Mapea capacidades declaradas a nodos reutilizables conocidos. |
| `def map_goal_and_world_state_to_graph(goal, world_state)` | Realiza el mapeo híbrido y agrega sus resultados sin duplicados. |
| `def get_mapping_history()` | Devuelve una copia del historial de mapeos. |
| `def clear_mapping_history()` | Limpia el historial de mapeos. |
| `def _create_goal_node(goal, world_state)` | Crea el nodo raíz de un objetivo con metadatos normalizados. |
| `def _create_capability_nodes(capabilities)` | Crea una única instancia de cada capacidad base reconocida. |
| `def _build_capability_node(capability, template)` | Construye una acción reutilizable a partir de una plantilla validada. |
| `def _create_goal_specific_nodes(goal, world_state)` | Crea acciones concretas según la intención y el tipo de objetivo. |
| `def _create_navigation_nodes(goal, world_state)` | Crea la secuencia lógica de abrir el navegador y navegar a un destino. |
| `def _create_open_app_nodes(goal, world_state)` | Crea los nodos de abrir y activar la aplicación objetivo. |
| `def _create_close_app_nodes(goal, world_state)` | Crea la acción para cerrar la aplicación indicada por el objetivo. |
| `def _create_search_nodes(goal, world_state)` | Crea la secuencia genérica de preparar navegador y realizar búsqueda. |
| `def _map_goal_specific_nodes(goal, world_state)` | Añade una secuencia específica para búsquedas de plataformas conocidas. |
| `def _create_youtube_specific_nodes(goal)` | Crea abrir navegador, acceder a YouTube y buscar en ese servicio. |
| `def _create_browser_specific_nodes(goal)` | Compatibilidad para crear una secuencia genérica de navegador. |
| `def _create_spotify_specific_nodes(goal)` | Crea abrir Spotify y buscar el contenido solicitado. |
| `def _create_application_state_nodes(world_state)` | Crea nodos STATE por aplicación, aceptando objetos y diccionarios. |
| `def _create_resource_nodes(world_state)` | Crea nodos RESOURCE para monitores y recursos declarados. |
| `def _create_calibrated_element_nodes(world_state)` | Crea nodos UI_ELEMENT para elementos calibrados y su monitor. |
| `def _establish_goal_transitions(goal_node_id, capability_nodes, specific_nodes, goal)` | Crea enlaces dirigidos de descomposición sin introducir ciclos. |
| `def _find_relevant_capability(node_id, goal)` | Relaciona una acción concreta con la capacidad declarativa adecuada. |
| `def _establish_state_transitions(app_nodes, resource_nodes, calibrated_nodes, world_state)` | Relaciona estado y recursos solo con identificadores semánticamente asociados. |
| `def _calculate_mapping_quality(goal, created_nodes)` | Calcula cobertura del mapeo de Goal sin puntuar ejecución. |
| `def _calculate_state_mapping_quality(world_state, created_nodes)` | Calcula cobertura de los elementos del estado realmente declarados. |
| `def _add_node(node, result)` | Inserta un nodo solo si falta y registra el nodo usado por el mapeo. |
| `def _add_edge(source_id, target_id)` | Añade una arista válida y reporta únicamente las transiciones nuevas. |
| `def _get_graph_node(node_id)` |  |
| `def _iter_graph_edges()` | Devuelve pares fuente/destino desde las representaciones de grafo conocidas. |
| `def _update_graph_with_nodes(goal_node, capability_nodes, specific_nodes)` | Compatibilidad: asegura que los nodos indicados están en el grafo. |
| `def _update_graph_with_state_nodes(app_nodes, resource_nodes, calibrated_nodes)` | Compatibilidad: los nodos ya se agregan al crearse. |
| `def _get_required_capabilities(goal)` | Obtiene capacidades declaradas y añade las necesarias por intención. |
| `def _capability_exists(capability)` |  |
| `def _get_goal_metadata(goal)` |  |
| `def _get_goal_base_cost(goal)` | Devuelve un coste finito y no negativo para representar el objetivo. |
| `def _get_goal_name(goal, goal_type)` | Devuelve un nombre legible aun cuando Goal no incluya el campo name. |
| `def _get_state_value(app_info)` | Normaliza el estado de aplicación cuando llega como enum, objeto o dict. |
| `def _extract_screen_id(node)` | Busca identificadores de monitor en los metadatos del nodo. |
| `def _is_action_node(node_id)` |  |
| `def _unique_preserve_order(values)` |  |
| `def _unique_edges(values)` |  |
| `def _record_history()` |  |
| `def _update_last_history_execution_time(result)` | Actualiza un registro coincidente sin corromper operaciones anteriores. |
| `def _safe_getattr(obj, attribute, default)` | Lee atributos o claves de diccionario sin propagar errores externos. |
| `def _get_required_id(obj, kind)` | Valida y normaliza el identificador requerido para un objeto. |
| `def _as_dict(value)` |  |
| `def _safe_iterable(value)` | Convierte valores iterables a lista sin dividir cadenas en caracteres. |
| `def _normalize_target_name(value)` | Extrae un nombre de aplicación razonable de cadenas o targets estructurados. |
| `def _safe_id_component(value)` |  |
| `def _create_generic_state_nodes(world_state)` | Representa hechos libres del estado canónico que no son colecciones. |
| `def _get_generic_state_entries(world_state)` | Obtiene el diccionario de hechos del WorldState canónico, si existe. |
| `def _world_state_field(world_state, key, default)` | Lee primero modelos legacy con atributos y luego WorldState.state. |
| `def _get_goal_target_value(goal, target_keys)` | Extrae datos de Goal.target (str/dict) y de metadata sin perder contexto. |
| `def _normalize_goal_type(value)` | Normaliza tipos de goal que puedan llegar como Enum o texto. |
| `def _read_field(value, key, default)` | Lee una clave en dict o atributo en objeto. |
| `def _first_present()` | Retorna el primer valor no nulo/no vacío. |
| `def _safe_copy(value)` | Copia datos de metadatos con fallback cuando un objeto no se puede copiar. |
| `def _safe_nonnegative_float(value, default)` | Convierte a float finito no negativo. |
| `def _safe_unit_float(cls, value)` | Normaliza una confianza al intervalo [0, 1]. |
| `def _normalize_conditions(value)` | Normaliza condiciones preservando dicts y cadenas como elementos únicos. |

<a name="src-hands-planner-graph-py"></a>
### `src/hands/planner/graph.py` [1871 líneas] — Grafo de estados y búsqueda de rutas para la planificación de JARVIS.

**Descripción:** Grafo de estados y búsqueda de rutas para la planificación de JARVIS.

**Importaciones:** 21.

`class SearchStrategy(Enum)`  (línea 39) — Estrategias de búsqueda soportadas por el grafo.

_Sin métodos definidos en el AST._

`class GraphNode`  (línea 52) — Estado auxiliar de búsqueda asociado a un nodo canónico.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __lt__(other)` |  |

`class GraphEdge`  (línea 101) — Transición entre dos nodos, con condiciones y efectos declarativos.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def _values_equal(actual, expected)` | Compara valores de estado sin confundir True con 1. |
| `def _evaluate_raw_condition(condition, state)` | Evalúa una condición compatible sin depender de una API única. |
| `def can_traverse(current_state)` | Indica si se pueden satisfacer todas las condiciones de la arista. |
| `def apply_effects(current_state)` | Aplica efectos a una copia del estado, registrando los fallos reales. |
| `def get_total_cost(current_state)` | Calcula coste de transición y sobrecoste declarativo determinista. |

`class RouteResult`  (línea 296) — Resultado estructurado de una búsqueda de ruta.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def length()` |  |
| `def edge_count()` |  |
| `def to_dict()` |  |

`class StateGraph`  (línea 411) — Grafo de estados con búsqueda de rutas condicionada por el estado.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(heuristic)` |  |
| `def graph_revision()` | Versión monotónica del grafo, usada para invalidar cachés. |
| `def _invalidate_search_cache()` |  |
| `def add_node(node)` |  |
| `def get_node(node_id)` |  |
| `def has_node(node_id)` |  |
| `def add_edge(source_id, target_id, cost, conditions, transition_type, preconditions, effects)` |  |
| `def _conditions_equivalent(left, right)` |  |
| `def get_edges_from(node_id)` |  |
| `def get_edge(source_id, target_id)` |  |
| `def find_route(start_node_id, goal_node_id, current_state, strategy, max_iterations, find_alternatives, alternative_count)` |  |
| `def _route_error(start_node_id, goal_node_id, strategy, state, message, started)` |  |
| `def _normalize_max_iterations(value)` |  |
| `def _normalize_alternative_count(value)` |  |
| `def build_route()` | Alias compatible con las integraciones que usan `build_route`. |
| `def find_path_astar(start_node_id, goal_node_id, current_state, max_iterations, find_alternatives, alternative_count)` |  |
| `def _find_path_astar_internal(start_node_id, goal_node_id, current_state, max_iterations, blocked_edges)` |  |
| `def _reconstruct_state_path(current_key, parent)` |  |
| `def find_path_dijkstra(start_node_id, goal_node_id, current_state, max_iterations, find_alternatives, alternative_count)` |  |
| `def find_path_bfs(start_node_id, goal_node_id, current_state, max_iterations, find_alternatives, alternative_count)` |  |
| `def find_path_dfs(start_node_id, goal_node_id, current_state, max_iterations, find_alternatives, alternative_count)` |  |
| `def find_path_greedy(start_node_id, goal_node_id, current_state, max_iterations, find_alternatives, alternative_count)` |  |
| `def get_edges_for_path(path, current_state)` | Obtiene una arista por salto; con paralelas elige la primera válida. |
| `def apply_path_effects(path, current_state)` |  |
| `def get_node_path_cost(path)` |  |
| `def get_neighbors(node_id, current_state)` |  |
| `def add_edge_with_preconditions(source_id, target_id, cost, transition_type)` |  |
| `def create_conditional_edge(source_id, target_id, cost, condition_type)` |  |
| `def create_effect_edge(source_id, target_id, cost, effect_type)` |  |
| `def validate_graph()` |  |
| `def validate_graph_advanced()` |  |
| `def _has_circular_path(start_node_id, max_depth)` |  |
| `def get_graph_stats()` |  |
| `def clear_search_cache()` |  |
| `def export_to_json()` |  |
| `def import_from_json(data)` | Importa de manera transaccional: un documento inválido no borra el grafo actual. |
| `def export_graph(file_path, format)` |  |
| `def import_graph(file_path, format)` |  |
| `def _serialize_node(node)` |  |
| `def _serialize_edge(edge)` |  |
| `def _serialize_condition(condition)` |  |
| `def _serialize_effect(effect)` |  |
| `def _deserialize_node(node_data)` |  |
| `def _deserialize_condition(data)` |  |
| `def _deserialize_effect(data)` |  |
| `def _json_safe(value)` | Alias histórico para la conversión JSON segura. |
| `def _normalize_strategy(strategy)` |  |
| `def _create_goal_from_node(node_id)` |  |
| `def _estimate_heuristic(node_id, current_state, goal)` |  |
| `def _state_signature(state)` |  |

`class GraphBuilder`  (línea 1489) — Constructores de grafos básicos de navegación y estado de aplicación.

Métodos:

| Firma | Docstring |
|---|---|
| `def build_navigation_graph(nodes)` |  |
| `def build_application_graph(nodes)` |  |

`class CacheEntry`  (línea 1546) — Entrada de caché con contexto, resultado y contador de accesos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(path, cost, state, timestamp, final_state, strategy, alternative_paths, graph_revision)` |  |
| `def is_expired(max_age_seconds)` |  |
| `def increment_access()` |  |

`class PerformanceMetrics`  (línea 1579) — Métricas acumuladas de búsqueda y caché.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def record_search(success, path_length, cost, search_time, iterations)` |  |
| `def record_cache_hit()` |  |
| `def record_cache_miss()` |  |
| `def get_hit_rate()` |  |
| `def get_average_search_time()` |  |
| `def to_dict()` |  |

`class AdvancedStateGraph(StateGraph)`  (línea 1635) — StateGraph con caché acotada y métricas de rendimiento.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(heuristic, cache_size, max_cache_age)` |  |
| `def find_path_with_strategy(start_node_id, goal_node_id, current_state, strategy, max_iterations, find_alternatives, alternative_count)` |  |
| `def _execute_strategy(start_node_id, goal_node_id, current_state, strategy, max_iterations, find_alternatives, alternative_count)` |  |
| `def find_route(start_node_id, goal_node_id, current_state, strategy, max_iterations, find_alternatives, alternative_count)` |  |
| `def build_route()` |  |
| `def _build_cache_key(start_node_id, goal_node_id, current_state, strategy, find_alternatives, alternative_count, max_iterations)` |  |
| `def _get_from_cache(cache_key, current_state)` |  |
| `def _add_to_cache(cache_key, entry)` |  |
| `def _cleanup_cache()` |  |
| `def get_advanced_stats()` |  |
| `def optimize_graph_for_performance()` | Limpia caché y ajusta su límite sin cambiar semántica de búsqueda. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _safe_float(value, default)`  (L73) | Convierte a float finito y usa *default* ante datos no válidos. |
| `def _copy_state(state)`  (L82) | Crea una copia defensiva y tolera objetos no copiables. |
| `def _type_value(value)`  (L95) | Devuelve el valor estable de un Enum sin modificar otros objetos. |
| `def _json_safe(value, _active)`  (L357) | Convierte valores habituales a JSON sin romper ante ciclos u objetos raros. |

<a name="src-hands-planner-heuristic-py"></a>
### `src/hands/planner/heuristic.py` [893 líneas] — Heurísticas para algoritmo de búsqueda A* (FASE 8).

**Descripción:** Heurísticas para algoritmo de búsqueda A* (FASE 8).

**Importaciones:** 11.

`class HeuristicType(Enum)`  (línea 36) — Tipos de heurísticas disponibles.

_Sin métodos definidos en el AST._

`class Heuristic`  (línea 73) — Heurística configurable para el algoritmo A*.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(heuristic_type, weight, custom_heuristic, max_cache_size)` | Inicializa la heurística y su caché LRU acotada. |
| `def _normalize_heuristic_type(value)` | Normaliza un enum, su valor textual o su nombre simbólico. |
| `def _normalize_weight(value)` | Normaliza el peso a un número finito no negativo. |
| `def _normalize_for_json(value, active_ids)` | Normaliza objetos a tipos JSON, detectando referencias circulares. |
| `def _stable_serialize(value)` | Serializa datos de forma estable para claves de caché. |
| `def _json_fallback(value)` | Fallback compatible para serializadores JSON que lo utilicen. |
| `def _build_cache_key(node_id, current_state, goal)` | Construye una clave que separa nodo, contexto, objetivo y configuración. |
| `def _minimal_goal_data(goal)` | Obtiene los campos básicos del objetivo cuando no puede serializarse. |
| `def _cache_get(key)` | Obtiene una estimación manteniendo el orden LRU. |
| `def _cache_set(key, value)` | Guarda una estimación y elimina las entradas menos recientes. |
| `def estimate_cost(node_id, current_state, goal, all_nodes)` | Estima el coste restante y siempre devuelve un float finito >= 0. |
| `def _apply_heuristic(node_id, current_state, goal, all_nodes)` | Aplica la heurística seleccionada. |
| `def _manhattan_distance(node, goal, current_state)` | Estimación discreta de navegación basada en el estado observable. |
| `def _euclidean_distance(node, goal, current_state)` | Ajuste continuo de la estimación discreta disponible. |
| `def _goal_distance_heuristic(node, goal, current_state)` | Estima un límite conservador del trabajo pendiente del objetivo. |
| `def _capability_based_heuristic(node, goal, current_state)` | Estima el coste según las capacidades requeridas que faltan. |
| `def _state_similarity_heuristic(node, goal, current_state)` | Estima la distancia al estado objetivo usando los campos declarados. |
| `def _goal_type(goal)` |  |
| `def _target_mapping(goal)` |  |
| `def _get_target_url(cls, goal)` | Obtiene el destino URL admitiendo objetivos legacy y estructurados. |
| `def _get_target_application(cls, goal)` | Obtiene la aplicación objetivo desde el target o los metadatos. |
| `def _urls_match(actual, expected)` | Compara URLs sin distinguir una barra final, conservando el resto. |
| `def _get_required_capabilities(goal)` | Obtiene capacidades requeridas y admite respuestas en formato string. |
| `def _get_current_url(state)` | Obtiene la URL actual desde formatos de estado compatibles. |
| `def _application_flag(state, application, flag)` | Obtiene un flag de aplicación de estado plano o anidado. |
| `def _capability_fulfilled(capability, current_state, goal)` | Comprueba una capacidad usando el objetivo para evitar falsos positivos. |
| `def _values_equal(actual, expected)` |  |
| `def _get_state_value(state, key)` | Obtiene un valor de estado con claves directas, punteadas o anidadas. |
| `def _get_expected_state(cls, goal)` | Obtiene una representación mínima y consistente del estado objetivo. |
| `def _capability_costs()` | Costes unitarios orientativos por capacidad; no sustituyen los costes de arista. |
| `def _cost_for_capability(capability, costs)` | Resuelve alias frecuentes manteniendo un coste por defecto conservador. |
| `def clear_cache()` | Limpia la caché de estimaciones heurísticas. |
| `def get_cache_stats()` | Devuelve estadísticas y configuración de la caché. |

`class HeuristicFactory`  (línea 855) — Factoría para crear heurísticas con configuraciones frecuentes.

Métodos:

| Firma | Docstring |
|---|---|
| `def create_uniform_heuristic(weight)` | Crea una heurística constante. |
| `def create_goal_distance_heuristic(weight)` | Crea una heurística basada en la distancia al objetivo. |
| `def create_capability_based_heuristic(weight)` | Crea una heurística basada en capacidades pendientes. |
| `def create_state_similarity_heuristic(weight)` | Crea una heurística basada en similitud de estado. |
| `def create_custom_heuristic(heuristic_func, weight)` | Crea una heurística personalizada validando su callback. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _log(level, message, method, line)`  (L53) | Emite un log sin permitir que un fallo del logger rompa la planificación. |

<a name="src-hands-planner-htn_manager-py"></a>
### `src/hands/planner/htn_manager.py` [1100 líneas] — Gestor de descomposición jerárquica de tareas (HTN) de JARVIS.

**Descripción:** Gestor de descomposición jerárquica de tareas (HTN) de JARVIS.

**Importaciones:** 17.

`class HTNStatus(Enum)`  (línea 37)

_Sin métodos definidos en el AST._

`class TaskDecompositionStrategy(Enum)`  (línea 46)

_Sin métodos definidos en el AST._

`class TaskExecutionResult`  (línea 54)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class HTNDecompositionRule`  (línea 65)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class HTNManager`  (línea 76) — Gestor central de reglas HTN y jerarquías de tareas.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(planner)` |  |
| `def initialize_decomposition_rules()` |  |
| `def set_planner(planner)` |  |
| `def set_state_graph(state_graph)` |  |
| `def enable_graph_decomposition(enabled, threshold)` |  |
| `def decompose_and_execute(goal, current_state)` | Compatibilidad pública: descompone y procesa la jerarquía resultante. |
| `def _decompose_and_execute_with_graph(goal, current_state)` |  |
| `def _decompose_with_graph_advanced(goal, htn_tasks, current_state)` | Usa las dependencias para ordenar tareas y delega ejecución a TaskExecutor. |
| `def _convert_htn_tasks_to_graph_nodes(htn_tasks, goal)` | Convierte tareas HTN en nodos y mantiene las dependencias internas. |
| `def _optimize_task_sequence_with_graph(graph_tasks, current_state, goal)` |  |
| `def _convert_graph_sequence_to_execution_plan(graph_sequence, goal)` |  |
| `def _node_to_execution_dict(node, goal)` |  |
| `def _convert_tasks_to_execution_plan(tasks, goal)` |  |
| `def _execute_optimized_plan(execution_plan, current_state, goal)` | Consulta al Planner cuando no hay tareas concretas que ejecutar. |
| `def _call_planner(goal, current_state)` |  |
| `def _execute_with_graph_only(goal, current_state)` |  |
| `def _estimate_task_cost(task)` |  |
| `def _execute_plan_directly(execution_plan, current_state, goal)` | Fallback de planificación que no ejecuta ni simula acciones. |
| `def load_task_library()` |  |
| `def decompose_goal(goal, current_state)` |  |
| `def execute_goal_hierarchy(goal, current_state)` |  |
| `def _find_decomposition_rule(goal, current_state)` |  |
| `def _application_catalog_available()` |  |
| `def _check_preconditions(rule, current_state)` |  |
| `def _browser_available(state)` |  |
| `def _entity_available(state)` |  |
| `def _task_from_pattern(goal, pattern_id, parent)` |  |
| `def _decompose_sequential(goal, rule)` |  |
| `def _decompose_parallel(goal, rule)` |  |
| `def _decompose_conditional(goal, rule, current_state)` |  |
| `def _decompose_iterative(goal, rule)` |  |
| `def _establish_hierarchy(tasks, goal)` |  |
| `def _order_tasks_by_dependencies(tasks)` |  |
| `def _validate_task_dependencies(tasks)` |  |
| `def _get_task_executor()` | Carga TaskExecutor de manera perezosa para evitar importaciones circulares. |
| `def _execute_task_hierarchy(tasks, current_state)` |  |
| `def _execute_single_task(task, current_state)` |  |
| `def _result_to_dict(result)` | Serializa el resultado de una subtarea sin exponer referencias mutables. |
| `def _normalize_task_result(raw, task, current_state, started)` |  |
| `def _normalize_task_status(status)` |  |
| `def _simulate_task_execution(task, current_state)` |  |
| `def _record_execution(goal, tasks, result, elapsed)` |  |
| `def get_execution_statistics()` |  |
| `def get_task_execution_history()` |  |
| `def _valid_goal(goal)` |  |
| `def _goal_type(goal)` |  |
| `def _normalize_state(state)` |  |
| `def _status_value(status)` |  |
| `def _safe_cost(value, default)` |  |
| `def _as_dict(value)` |  |
| `def _as_list(value)` |  |
| `def _evaluate_precondition(precondition, state)` |  |
| `def _failed_result(task_id, message, state)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_htn_manager()`  (L1077) | Obtiene la instancia global de HTNManager de forma segura. |

<a name="src-hands-planner-learning_system-py"></a>
### `src/hands/planner/learning_system.py` [899 líneas] — Sistema de aprendizaje de JARVIS (FASE 18).

**Descripción:** Sistema de aprendizaje de JARVIS (FASE 18).

**Importaciones:** 13.

`class LearningEventType(Enum)`  (línea 27)

_Sin métodos definidos en el AST._

`class LearningEvent`  (línea 39)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |
| `def from_dict(cls, data)` |  |
| `def _coerce_bool(value)` |  |
| `def _optional_string(value)` |  |

`class LearningStatistics`  (línea 130)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class LearningSystem`  (línea 142) — Sistema centralizado, acotado y thread-safe de aprendizaje histórico.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(max_memory_size, learning_rate)` |  |
| `def record_action_execution(action_name, success, execution_time, estimated_cost, context, application, screen_state, actual_cost)` |  |
| `def record_plan_execution(plan_id, goal_id, plan, success, execution_time, total_estimated_cost, context, actual_cost)` | Registra el resultado real del plan; el caller debe aportar ``success`` observado. |
| `def record_node_execution(node_id, success, execution_time, estimated_cost, context, application, actual_cost)` |  |
| `def record_replanification(original_plan, new_plan, reason, success, execution_time)` |  |
| `def record_goal_result(goal_id, success, context, execution_time)` | Registra explícitamente el resultado observado de un objetivo. |
| `def get_action_insights(action_name)` |  |
| `def get_system_insights()` |  |
| `def get_cost_adjustments()` | Devuelve deltas respecto al último coste estimado (no costes absolutos). |
| `def get_learned_costs()` | Devuelve los costes absolutos aprendidos por acción. |
| `def get_route_performance(goal_id)` |  |
| `def export_learning_data(filepath)` |  |
| `def import_learning_data(filepath)` |  |
| `def clear_learning_data()` |  |
| `def enable_learning(enabled)` |  |
| `def enable_cost_learning(enabled)` |  |
| `def enable_pattern_learning(enabled)` |  |
| `def enable_route_learning(enabled)` |  |
| `def _build_event(event_type)` |  |
| `def _store_event(event)` | Almacena evento e incrementa contadores agregados en la misma sección crítica. |
| `def _update_statistics(stats, event)` |  |
| `def _learn_action_cost(action_name, event)` |  |
| `def _discover_patterns(event)` |  |
| `def _update_route_performance(route_key, plan, event)` |  |
| `def _register_optimal_route(goal_id, plan, event)` |  |
| `def _learn_from_replanification(event)` |  |
| `def _calculate_improvement_trend(events)` |  |
| `def _count_events_by_type()` |  |
| `def _assess_system_health(events)` |  |
| `def _generate_health_recommendations(status, success_rate, cost_accuracy)` |  |
| `def _build_application_insights(events)` |  |
| `def _build_action_insights_summary(events)` |  |
| `def _rebuild_statistics_from_events()` |  |
| `def _count_unique_patterns()` |  |
| `def _safe_float(value, default)` |  |
| `def _cost_error(event)` |  |
| `def _empty_route_performance()` |  |
| `def _load_pattern_dict(value)` |  |
| `def _load_temporal_patterns(value)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_learning_system()`  (L883) | Obtiene la instancia global del sistema de aprendizaje con inicialización segura. |

<a name="src-hands-planner-node-py"></a>
### `src/hands/planner/node.py` [1137 líneas] — Única fuente de verdad para:

**Descripción:** Única fuente de verdad para:

**Importaciones:** 8.

`class NodeType(Enum)`  (línea 31) — Tipos de nodos en el sistema de planificación.

_Sin métodos definidos en el AST._

`class TaskStatus(Enum)`  (línea 47) — Estado de ejecución de tareas.

_Sin métodos definidos en el AST._

`class Node`  (línea 121) — Modelo conceptual común para todos los elementos del sistema.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def _evaluate_precondition(precondition, current_state)` | Evalúa una precondición declarativa o funcional sin acoplarse a otro módulo. |
| `def can_execute(current_state)` | Verifica las precondiciones declarativas, funcionales y de estado del nodo. |
| `def _apply_effect(effect, state, execution_result)` | Aplica un efecto declarativo/objeto manteniendo compatibilidad con Effect. |
| `def execute()` | Ejecuta el callback y devuelve el resultado y el estado candidato actualizado. |
| `def _update_learning_metrics(execution_record)` | Recalcula métricas desde los registros válidos del histórico acumulado. |
| `def verify_success(result)` | Verifica el éxito mediante el criterio configurado. |
| `def to_dict()` | Convierte el nodo a un diccionario serializable. |
| `def from_dict(cls, data)` | Reconstruye un nodo desde datos serializados, sin restaurar callbacks. |
| `def add_edge(target_node_id, cost)` | Añade o actualiza una transición saliente y su coste finito no negativo. |
| `def add_in_edge(source_node_id, cost)` | Registra una transición entrante; el coste canónico reside en el emisor. |
| `def get_edge_cost(target_node_id)` | Obtiene el coste de una transición. |
| `def get_valid_transitions(current_state, all_nodes)` | Devuelve transiciones de salida cuyo nodo destino puede ejecutarse. |
| `def add_precondition_function(precond_func)` | Añade una precondición funcional. |
| `def add_effect_function(effect_func)` | Añade un efecto funcional. |
| `def set_state_requirement(key, value)` | Define un requisito de estado. |
| `def set_state_modification(key, value)` | Define una modificación de estado esperada. |
| `def mark_as_reusable_action(category)` | Marca el nodo como acción reutilizable. |
| `def get_execution_stats()` | Devuelve estadísticas agregadas sin fallar ante entradas históricas malformadas. |

`class Goal`  (línea 674) — Objetivo de alto nivel alcanzable mediante planificación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def _target_value(key, default)` |  |
| `def is_achieved(current_state)` | Comprueba si el estado actual satisface el objetivo conocido. |
| `def get_required_capabilities()` | Obtiene capacidades necesarias para el objetivo preservando el orden. |
| `def estimate_cost(current_state)` | Estima el coste restante del objetivo. |
| `def is_expired()` | Indica si se ha superado el deadline válido del objetivo. |
| `def to_dict()` | Convierte el objetivo a un diccionario serializable. |
| `def from_dict(cls, data)` | Reconstruye un objetivo desde un diccionario serializado. |

`class Task`  (línea 837) — Tarea jerárquica descomponible en otras tareas o nodos.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def _dependency_satisfied(dependency_id, all_nodes, current_state)` | Comprueba una dependencia usando la semántica disponible en el modelo. |
| `def can_execute(current_state, all_nodes)` | Verifica dependencias y disponibilidad de hijos, evitando ciclos jerárquicos. |
| `def decompose_task(all_nodes)` | Descompone recursivamente la tarea en hojas sin quedar atrapada en ciclos. |
| `def get_execution_plan(current_state, all_nodes)` | Obtiene candidatos ejecutables en el orden declarado y sin recursión cíclica. |
| `def estimate_task_cost(current_state, all_nodes)` | Estima el coste de los hijos ejecutables sin contar ramas cíclicas. |
| `def to_dict()` | Convierte la tarea a un diccionario serializable. |
| `def from_dict(cls, data)` | Reconstruye una tarea desde un diccionario serializado. |

`class WorldState`  (línea 1080) — Estado del mundo canónico para planificación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` | Asegura que el estado interno siempre sea un diccionario independiente. |
| `def get(key, default)` | Obtiene un valor del estado. |
| `def set(key, value)` | Establece un valor evitando retener referencias mutables externas. |
| `def update(other)` | Actualiza el estado con otro estado o diccionario. |
| `def copy()` | Devuelve una copia independiente del estado. |
| `def to_dict()` | Convierte el estado a una representación serializable. |
| `def from_dict(cls, data)` | Reconstruye el estado desde un diccionario serializado. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _copy_state(state)`  (L58) | Copia el estado sin permitir que los efectos muten accidentalmente el original. |
| `def _safe_float(value, default)`  (L71) | Convierte un valor a float finito y devuelve el valor por defecto si no es válido. |
| `def _serialize_value(value, _seen)`  (L80) | Convierte valores habituales a datos serializables y evita ciclos de referencias. |
| `def create_action_node(id, name, application, ui_element, cost)`  (L1033) | Crea un nodo de acción reutilizable. |
| `def create_application_node(id, name, app_name)`  (L1055) | Crea un nodo que representa una aplicación. |
| `def create_state_node(id, name, state_key, state_value)`  (L1060) | Crea un nodo que representa un requisito de estado. |
| `def create_condition_node(id, name, condition_func)`  (L1067) | Crea un nodo de condición mediante callback. |

<a name="src-hands-planner-optimization-py"></a>
### `src/hands/planner/optimization.py` [951 líneas] — Sistema de optimización del planificador de JARVIS.

**Descripción:** Sistema de optimización del planificador de JARVIS.

**Importaciones:** 19.

`class OptimizationType(Enum)`  (línea 40) — Tipos de optimización disponibles.

_Sin métodos definidos en el AST._

`class RouteCacheEntry`  (línea 75) — Entrada del caché de rutas/planes.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |
| `def from_dict(cls, data)` |  |

`class CostLearningData`  (línea 125) — Muestra individual de aprendizaje de coste.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |
| `def from_dict(cls, data)` |  |

`class ContextData`  (línea 156) — Datos contextuales usados por la optimización.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class OptimizationManager`  (línea 165) — Gestor de optimización que opera sobre un Planner ya existente.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(planner, max_cache_size)` |  |
| `def set_learning_system(learning_system)` |  |
| `def optimize_planning(goal, current_state, available_nodes, max_planning_time)` |  |
| `def _check_route_cache(goal, current_state)` |  |
| `def _add_to_route_cache(goal, current_state, result)` |  |
| `def record_route_execution(goal_id, current_state, success, execution_time)` | Actualiza métricas de la ruta cacheada después de observar su ejecución. |
| `def _build_cache_key(goal, state_hash)` |  |
| `def _safe_goal_capabilities(goal)` |  |
| `def _hash_state(state)` |  |
| `def _stable_hash(cls, value)` |  |
| `def _normalize_for_json(cls, value)` |  |
| `def _strip_volatile_state(state)` |  |
| `def _remove_redundancies(plan, current_state)` | Elimina repeticiones evidentes, preservando acciones observables. |
| `def _select_optimal_alternatives(alternatives, current_state)` |  |
| `def _apply_context_optimization(plan, current_state)` | Ajusta metadatos/costes contextuales sin alterar el plan de entrada. |
| `def _create_optimized_node(original_id, optimized_method, original_node)` | Compatibilidad legacy para generar una variante de nodo. |
| `def _calculate_state_compatibility(plan, current_state)` |  |
| `def _evaluate_condition_with_state(condition, state)` |  |
| `def _get_nested_state_value(state, key, default)` |  |
| `def _get_learned_cost_for_plan(plan)` |  |
| `def record_execution_result(plan, execution_time, success, context)` | Registra un resultado observado; este método no ejecuta el plan. |
| `def _update_cost_model(node_id, learning_data)` |  |
| `def _update_context_patterns(plan, success, context)` |  |
| `def get_optimization_stats()` |  |
| `def clear_cache()` |  |
| `def invalidate_cache_for_goal(goal_id)` | Invalida las entradas cacheadas de un objetivo tras cambios de dominio. |
| `def enable_optimization(optimization_type, enabled)` |  |
| `def export_optimization_data(filepath)` |  |
| `def import_optimization_data(filepath)` |  |
| `def _node_identifier(node)` |  |
| `def _node_cost(node)` |  |
| `def _plan_signature(cls, plan)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _finite_float(value, default, minimum)`  (L51) | Convierte a float finito y aplica un límite inferior opcional. |
| `def _string_list(value)`  (L64) |  |

<a name="src-hands-planner-optimization_config-py"></a>
### `src/hands/planner/optimization_config.py` [475 líneas] — Configuración tipada y validable del sistema de optimización de JARVIS.

**Descripción:** Configuración tipada y validable del sistema de optimización de JARVIS.

**Importaciones:** 7.

`class OptimizationMode(Enum)`  (línea 19) — Modos de operación del sistema de optimización.

_Sin métodos definidos en el AST._

`class RouteCacheConfig`  (línea 93) — Configuración del caché de rutas (FASE 17.1).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class CostLearningConfig`  (línea 112) — Configuración del aprendizaje de costes (FASE 17.6).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class RedundancyRemovalConfig`  (línea 135) — Configuración de eliminación de redundancias (FASE 17.3).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class ContextAwareConfig`  (línea 155) — Configuración de optimización basada en contexto (FASE 17.5).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class AlternativeSelectionConfig`  (línea 178) — Configuración de selección de alternativas (FASE 17.4).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class PerformanceMonitoringConfig`  (línea 201) — Configuración de monitoreo de rendimiento (FASE 17.7).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class OptimizationConfig`  (línea 227) — Configuración completa del sistema de optimización (FASE 17).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def _coerce_mode(value)` |  |
| `def _coerce_nested(name, config_type)` |  |
| `def get_aggressive_config(cls)` | Obtiene configuración para modo agresivo. |
| `def get_conservative_config(cls)` | Obtiene configuración para modo conservador. |
| `def get_learning_only_config(cls)` | Obtiene configuración para registrar aprendizaje sin aplicar optimizaciones. |
| `def get_optimization_enabled()` | Devuelve el estado efectivo de cada técnica para el modo actual. |
| `def validate_config()` | Valida rangos y coherencia; una lista vacía indica configuración válida. |
| `def validate_or_raise()` | Lanza ValueError si validate_config detecta problemas. |
| `def to_dict()` | Devuelve una copia serializable de toda la configuración. |
| `def from_dict(cls, config_dict)` | Construye configuración desde un diccionario parcial o completo. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _coerce_bool(value, field_name)`  (L28) | Convierte booleanos habituales sin tratar cualquier texto como True. |
| `def _coerce_int(value, field_name)`  (L43) | Convierte a entero y rechaza booleanos y valores fraccionarios. |
| `def _coerce_float(value, field_name)`  (L56) | Convierte a float; la validación de rangos se realiza en validate_config. |
| `def _coerce_string_list(value, field_name)`  (L66) |  |
| `def _normalize_fields(instance, integers, floats, booleans)`  (L83) |  |

<a name="src-hands-planner-planner-py"></a>
### `src/hands/planner/planner.py` [3129 líneas] — Planificador principal de JARVIS.

**Descripción:** Planificador principal de JARVIS.

**Importaciones:** 34.

`class PlannerStatus(Enum)`  (línea 60)

_Sin métodos definidos en el AST._

`class PlanQuality(Enum)`  (línea 69)

_Sin métodos definidos en el AST._

`class PlanningResult`  (línea 77) — Resultado estructurado de una solicitud de planificación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class Planner`  (línea 117) — Planificador central de JARVIS; no ejecuta físicamente sus planes.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(executor)` |  |
| `def get_learning_insights()` |  |
| `def get_action_learning_insights(action_name)` |  |
| `def get_cost_adjustments()` |  |
| `def export_learning_data(filepath)` |  |
| `def import_learning_data(filepath)` |  |
| `def clear_learning_data()` |  |
| `def enable_learning(enabled)` |  |
| `def initialize_htn_manager()` |  |
| `def set_htn_manager(htn_manager)` |  |
| `def plan_with_htn_integration(goal, current_state, available_nodes, max_planning_time, use_graph_optimization, htn_decomposition_threshold)` |  |
| `def _plan_with_graph_optimized(goal, current_state, available_nodes, max_planning_time, htn_threshold)` |  |
| `def _plan_with_htn_traditional(goal, current_state, available_nodes, max_planning_time)` |  |
| `def _plan_complex_htn_graph(goal, current_state, available_nodes, max_planning_time)` |  |
| `def _invoke_planner_method(method, goal, current_state, available_nodes, max_planning_time)` | Invoca una API HTN legacy sin repetirla si falla dentro de su cuerpo. |
| `def _coerce_htn_result(raw, goal, current_state)` |  |
| `def _normalize_dict_plan(raw_plan)` | Normaliza listas de nodos/diccionarios a pasos declarativos de plan. |
| `def _convert_htn_result_to_plan(htn_result)` |  |
| `def set_state_graph(state_graph)` |  |
| `def get_state_graph()` |  |
| `def create_graph_from_nodes(nodes)` |  |
| `def _build_graph_edges(graph, nodes)` | Genera solo transiciones respaldadas por dependencias o semántica. |
| `def _should_create_edge(source_node, target_node)` | No conecta nodos solo por compartir tipo o aplicación. |
| `def _calculate_edge_cost_for_graph(source_node, target_node)` |  |
| `def _get_edge_conditions(source_node, target_node)` |  |
| `def integrate_graph_with_htn(graph, htn_manager)` |  |
| `def validate_graph_integration()` |  |
| `def get_graph_integration_status()` |  |
| `def configure_astar_planning(heuristic_type, heuristic_weight, graph_type)` |  |
| `def _create_graph_edges_from_nodes()` |  |
| `def set_custom_graph(graph)` |  |
| `def plan(goal, current_state, available_nodes, max_planning_time, find_alternatives, use_optimization)` |  |
| `def _plan_with_optional_optimization(goal, current_state, available_nodes, max_planning_time, use_optimization)` |  |
| `def _create_plan_astar(goal, current_state, available_nodes, max_planning_time)` |  |
| `def _create_plan(goal, current_state, available_nodes, max_planning_time)` |  |
| `def _get_available_nodes()` |  |
| `def _create_compatibility_nodes()` | Nodos mínimos de compatibilidad; no representan ejecución ya realizada. |
| `def _get_start_node_for_goal(goal, current_state)` |  |
| `def _get_goal_node_for_goal(goal)` |  |
| `def _convert_path_to_plan(path, available_nodes)` |  |
| `def _convert_node_to_execution_node(node)` |  |
| `def _build_hierarchical_plan(goal, current_state, available_nodes, required_capabilities)` |  |
| `def _find_nodes_for_capability(capability, available_nodes, current_state)` |  |
| `def _node_provides_capability(node, capability)` |  |
| `def _select_best_node(nodes, current_state)` |  |
| `def _optimize_plan(plan, current_state)` |  |
| `def validate_ui_resources_for_plan(plan, current_state)` |  |
| `def get_optimal_ui_strategy(action_id, resource_id)` |  |
| `def resolve_ui_conflicts(plan, current_state)` |  |
| `def check_ui_readiness(goal, current_state, available_nodes)` |  |
| `def _find_alternative_plans_astar(goal, current_state, available_nodes, original_plan)` |  |
| `def _find_alternatives_for_node(goal, current_state, available_nodes, original_plan, original_node, position)` |  |
| `def _select_best_alternative(alternatives, current_state, goal, original_plan)` |  |
| `def _calculate_plan_similarity(alt_plan, original_plan)` |  |
| `def _calculate_state_compatibility(plan, current_state)` |  |
| `def _evaluate_condition_with_state(condition, state)` |  |
| `def replan(goal, current_state, failed_plan, failed_node_index)` |  |
| `def _evaluate_plan_quality(plan, current_state, goal)` |  |
| `def _optimize_integrated_plan(result, current_state, goal)` |  |
| `def _remove_redundancies(plan)` |  |
| `def _apply_learned_cost_adjustments(plan)` |  |
| `def _ensure_optimization_systems()` |  |
| `def load_application_knowledge()` |  |
| `def get_applications_by_capability(capability_name)` |  |
| `def get_application_capabilities(app_name)` |  |
| `def get_application_capabilities_as_list(app_name)` | Expone capacidades como lista de identificadores canónicos consumibles por el planificador; reutiliza `get_application_capabilities` y devuelve `[]` si la app está ausente o no declara capacidades. |
| `def trace_application_capability_to_action(app_name, capability)` | Trazabilidad aplicacion -> capability -> accion: para cada capability expuesta por la app documenta los nodos que la proporcionan y verifica (via `action_exists`) si la accion efectiva esta registrada; reutiliza `get_application_capabilities_as_list`, `_node_provides_capability`, `_resolve_node_action_name` y `action_exists`. No filtra por estado (`can_execute`) y restringe nodos a la app solicitada. |
| `def find_application_for_goal(goal)` |  |
| `def build_application_aware_plan(goal, current_state)` |  |
| `def _get_action_registry()` | Obtiene el ActionRegistry disponible a través del executor o directamente; devuelve ``None`` si no está disponible (modo paso seguro). |
| `def action_exists(action_name)` | Verifica si *action_name* está registrada en el ActionRegistry. |
| `def _resolve_node_action_name(node)` (estático) | Determina el nombre de acción efectivo de un paso de plan, replicando la resolución del Executor. |
| `def validate_plan_actions(plan)` | Verifica que las acciones de *plan* existen en el ActionRegistry; devuelve un reporte estructurado con ``nonexistent_actions``, ``existing_actions``, ``valid``, etc. |
| `def filter_existing_actions(plan)` | Filtra los pasos de *plan* cuyas acciones no existen en el ActionRegistry, conservando pasos con ``execute_callback``. |
| `def _filter_plan_actions(plan)` | Filtra pasos con acciones inexistentes; retorna ``(plan_filtrado, acciones_eliminadas)``. |
| `def is_application_available(app_name)` |  |
| `def get_application_ui_requirements(app_name, capability)` |  |
| `def get_planning_stats()` |  |
| `def execute_plan(plan, plan_id)` | Delegación explícita legacy. Nunca ejecuta acciones dentro del Planner. |
| `def record_execution_result(plan, execution_time, success, context)` | Registra feedback tras una ejecución externa real; plan() no lo simula. |
| `def get_optimization_stats()` |  |
| `def clear_optimization_cache()` |  |
| `def enable_optimization(optimization_type, enabled)` |  |
| `def export_optimization_data(filepath)` |  |
| `def import_optimization_data(filepath)` |  |
| `def get_optimization_recommendations()` |  |
| `def _record_planning_history(goal, current_state, result, method)` |  |
| `def _get_default_state()` |  |
| `def _safe_required_capabilities(goal)` |  |
| `def _is_goal_expired(goal)` |  |
| `def _is_goal_achieved(goal, current_state)` |  |
| `def _node_type_value(node)` |  |
| `def _status_value(status)` |  |
| `def _normalize_identifier(value)` |  |
| `def _state_node_matches_context(node, current_state)` |  |
| `def _node_can_satisfy_goal(node, goal)` |  |
| `def _goal_satisfied_by_effects(effects, goal)` |  |
| `def _effects_support_preconditions(effects, preconditions)` |  |
| `def _facts_support_conditions(facts, conditions)` |  |
| `def _normalize_route_result(raw_result)` | Normaliza RouteResult, diccionarios, tuplas y listas legacy. |
| `def _create_sequential_navigation_edges()` | Añade secuencia legacy únicamente cuando los nodos existen. |
| `def _validate_goal_request(goal, max_planning_time)` |  |
| `def _failure_result(message, goal, state, started)` |  |
| `def _new_plan_id()` |  |
| `def _normalize_state(value)` |  |
| `def _goal_target_string(goal)` |  |
| `def _node_effect_facts(node)` |  |
| `def _node_state_facts(node)` |  |
| `def _has_incoming_edge(node_id)` |  |
| `def _edge_pairs()` |  |
| `def _time_budget_to_iterations(max_planning_time)` |  |
| `def _normalize_alternative_plans(alternatives, nodes)` |  |
| `def _candidate_preconditions_compatible(node, current_state, preceding_plan)` |  |
| `def _same_capability_or_category(candidate, original_node)` |  |
| `def _capability_already_satisfied(capability, state)` |  |
| `def _apply_declared_effects(state, effects)` |  |
| `def _calculate_goal_complexity(goal, current_state)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _normalize_text(value)`  (L3074) |  |
| `def _slug(value)`  (L3084) | Normaliza nombres de capacidades sin perder el separador de palabras. |
| `def _finite_float(value, default)`  (L3089) |  |
| `def _finite_nonnegative(value, default)`  (L3097) |  |
| `def _as_values(value)`  (L3102) |  |
| `def _normalize_alternative_paths(value)`  (L3117) |  |

<a name="src-hands-planner-planner_integration-py"></a>
### `src/hands/planner/planner_integration.py` [1923 líneas] — Responsabilidades:

**Descripción:** Responsabilidades:

**Importaciones:** 14.

`class IntegrationMode(Enum)`  (línea 37)

_Sin métodos definidos en el AST._

`class GraphPlanningResult`  (línea 44)

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class GraphPlannerIntegration`  (línea 57) — Puente entre Goal/estado actual y StateGraph.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(use_astar, integration_mode)` | Inicializa el puente de planificación sin ejecutar acciones. |
| `def initialize_graph(nodes, edges_config)` | Construye un grafo nuevo y rechaza identificadores ambiguos. |
| `def _configure_advanced_edges(edges_config)` |  |
| `def _create_compatibility_edges()` |  |
| `def _create_sequence_edges(sequences)` |  |
| `def _prepare_planning_edges()` | Deriva aristas solo de dependencias o efectos que aportan evidencia. |
| `def _connect_if_plannable(source_node, target_node, current_state)` |  |
| `def _add_planning_edge(source_node, target_node)` |  |
| `def _add_edge_if_missing(source_id, target_id, cost, transition_type, preconditions, effects)` |  |
| `def create_plan_with_graph(goal, current_state, available_nodes, max_planning_time, start_node_id, goal_node_id)` | Planifica una ruta y devuelve metadatos; nunca ejecuta acciones. |
| `def _validate_planning_input(goal, current_state, available_nodes)` |  |
| `def _determine_search_strategy(goal, current_state)` |  |
| `def _calculate_goal_complexity(goal, current_state)` |  |
| `def _execute_search(start_node_id, goal_node_id, current_state, strategy, max_planning_time)` | Invoca la API de búsqueda compatible y normaliza el resultado. |
| `def _select_search_method()` |  |
| `def _build_search_kwargs(method, start_node_id, goal_node_id, current_state, strategy, max_iterations)` |  |
| `def _call_search_positionally(method, start_node_id, goal_node_id, current_state, strategy, max_iterations)` |  |
| `def _normalize_route_result(raw_result, strategy)` | Adapta RouteResult, dict, tupla y lista sin convertir errores en éxitos. |
| `def _normalize_edge_ids(edges, path)` |  |
| `def _prepare_contextual_planning_edges(start_node_id, goal_node_id, current_state, goal)` | Añade enlaces temporales para esta búsqueda según el estado observado. |
| `def _get_start_node_for_goal(goal, current_state)` |  |
| `def _score_state_node(node, current_state)` |  |
| `def _get_goal_node_for_goal(goal)` |  |
| `def _node_can_satisfy_goal(action_node, goal_node, current_state, goal)` | Comprueba compatibilidad con evidencia, priorizando el target exacto. |
| `def _goal_type_matches_effects(goal_type, effects)` |  |
| `def _calculate_path_cost(path, current_state)` |  |
| `def _find_edge(source_id, target_id, state)` |  |
| `def _get_edges_used_in_path(path)` |  |
| `def _convert_path_to_plan_metadata(path, available_nodes)` |  |
| `def _update_performance_metrics(plan_entries, execution_time, total_cost)` |  |
| `def _preconditions_satisfied(preconditions, state)` |  |
| `def _effects_support_preconditions(effects, preconditions)` | Indica si todos los requisitos podrían quedar garantizados por los efectos. |
| `def _condition_supported_by_effects(condition, effects)` | Comprueba compatibilidad declarativa; no adivina el efecto de callbacks. |
| `def _has_effect_key(key, effects)` |  |
| `def _key_value_supported(key, expected, effects, stringify)` |  |
| `def _goal_satisfied_by_effects(current_state, effects)` |  |
| `def _calculate_graph_metrics()` |  |
| `def get_integration_statistics()` |  |
| `def export_graph_state(filepath)` |  |
| `def import_graph_state(filepath)` |  |
| `def validate_graph_consistency()` |  |
| `def _as_sequence(value)` | Normaliza colecciones sin separar strings ni diccionarios en sus partes. |
| `def _normalize_path(value)` | Normaliza una ruta y descarta entradas vacías/no textuales. |
| `def _normalize_text(value)` |  |
| `def _goal_target_terms(target)` | Extrae términos de target manteniendo las claves/valores existentes. |
| `def _effect_fields(effect)` |  |
| `def _condition_numeric_supported(key, kind, expected, effects)` |  |
| `def _evaluate_condition_like(condition, state)` | Evalúa condiciones declarativas compatibles, fallando de forma segura. |
| `def _copy_state(state)` |  |
| `def _add_contextual_edge_if_missing(source_id, target_id, cost, transition_type, preconditions, effects)` |  |
| `def _remove_contextual_planning_edges()` |  |
| `def _invalidate_graph_caches()` |  |
| `def _validate_route_path(path, start_node_id, goal_node_id, initial_state)` |  |
| `def _record_integration_search(success, path_length, cost, elapsed)` |  |
| `def build_route()` |  |
| `def _safe_float(value, default)` |  |

<a name="src-hands-planner-preconditions_effects-py"></a>
### `src/hands/planner/preconditions_effects.py` [1076 líneas] — Sistema avanzado de precondiciones y efectos para planificación jerárquica.

**Descripción:** Sistema avanzado de precondiciones y efectos para planificación jerárquica.

**Importaciones:** 7.

`class PreconditionsEffectsManager`  (línea 90) — Gestor centralizado de precondiciones y efectos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _initialize_templates()` | Inicializa plantillas comunes de condiciones y efectos. |
| `def create_condition(condition_type, key, expected_value, function, description, parameters)` | Crea una condición y la registra para reutilización. |
| `def create_effect(effect_type, key, value, function, description, parameters, cumulative)` | Crea un efecto y lo registra para reutilización. |
| `def _make_registry_key(kind, key)` |  |
| `def create_composite_condition(conditions, operator, description)` | Crea una condición compuesta AND u OR. |
| `def verify_action_preconditions(action_info, current_state)` | Devuelve True cuando todas las precondiciones de la acción se cumplen. |
| `def evaluate_condition(condition, current_state)` | Evalúa una condición individual o funcional de forma segura. |
| `def _dict_condition_matches(condition, state)` |  |
| `def _dict_to_condition(condition_dict)` |  |
| `def _resolve_condition_type(raw_type)` |  |
| `def apply_action_effects(action_info, current_state, execution_result)` | Aplica los efectos de la acción y devuelve un nuevo estado. |
| `def apply_effect(effect, current_state, execution_result)` | Aplica un efecto individual. |
| `def _dict_to_effect(effect_dict)` |  |
| `def get_state_requirements_for_action(action_info)` | Extrae solo precondiciones representables como requisitos escalares. |
| `def get_state_modifications_from_action(action_info)` | Extrae modificaciones de estado estáticas de los efectos. |
| `def create_action_with_preconditions_effects(name, description, preconditions, effects, cost)` | Crea un ActionInfo compatible con el registro central de acciones. |
| `def _normalize_sequence(value)` | Normaliza una colección sin alterar el orden de listas y tuplas. |
| `def _ensure_condition(condition)` |  |
| `def _resolve_action_type(raw_type)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _safe_copy(value, memo)`  (L38) | Copia datos incluyendo contenedores cíclicos y valores no copiables. |
| `def _safe_state_copy(state)`  (L82) | Devuelve una copia independiente del estado recibido. |
| `def get_preconditions_effects_manager()`  (L968) | Obtiene la instancia global del gestor. |
| `def create_application_open_condition(app_name)`  (L976) | Crea una condición que representa una aplicación abierta. |
| `def create_application_active_condition(app_name)`  (L998) | Crea una condición que representa una aplicación activa. |
| `def create_ui_element_calibrated_condition(app_name, element_name)`  (L1020) | Crea una condición que representa un elemento UI calibrado. |
| `def create_application_open_effect(app_name)`  (L1044) | Crea un efecto que representa una aplicación abierta. |
| `def create_ui_element_calibrate_effect(app_name, element_name)`  (L1056) | Crea un efecto que representa un elemento UI calibrado. |

<a name="src-hands-planner-preconditions_effects_types-py"></a>
### `src/hands/planner/preconditions_effects_types.py` [821 líneas] — Tipos base para el sistema de precondiciones y efectos.

**Descripción:** Tipos base para el sistema de precondiciones y efectos.

**Importaciones:** 7.

`class ConditionType(Enum)`  (línea 31) — Tipos de condiciones de precondición/efecto.

_Sin métodos definidos en el AST._

`class Condition`  (línea 334) — Representa una condición que debe cumplirse para ejecutar una acción.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def evaluate(state)` | Evalúa la condición contra el estado actual sin mutarlo. |
| `def _evaluate(state, active_conditions, depth)` |  |

`class Effect`  (línea 484) — Representa un efecto que modifica el estado tras ejecutar una acción.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def apply(state, execution_result)` | Aplica el efecto y devuelve un estado nuevo sin mutar la entrada. |
| `def _apply_internal(state, execution_result, active_effects, depth)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _safe_copy(value, memo)`  (L48) | Copia valores comunes de forma defensiva, tolerando objetos no copiables. |
| `def _normalize_name(value)`  (L120) | Normaliza nombres usados como claves de estado. |
| `def _is_mapping(value)`  (L127) |  |
| `def _safe_number(value)`  (L131) | Convierte a float únicamente valores numéricos finitos. |
| `def _as_bool(value)`  (L142) | Interpreta flags comunes sin tratar la cadena ``'false'`` como cierta. |
| `def _get_nested_state_value(state, key, default)`  (L170) | Obtiene una clave directa o una ruta sencilla separada por puntos. |
| `def _get_application_state(state, app_name)`  (L196) | Busca el estado de una aplicación en varios formatos compatibles. |
| `def _get_boolean_application_flag(state, app_name, flag)`  (L220) | Obtiene un flag de aplicación desde estado plano o anidado. |
| `def _get_ui_element_state(state, app_name, element_name)`  (L248) | Busca el estado de un elemento UI sin confundir aplicaciones distintas. |
| `def _resolve_condition_type(value)`  (L303) | Convierte un enum, valor textual o alias histórico a ``ConditionType``. |
| `def _coerce_condition(value)`  (L681) | Convierte una condición soportada a ``Condition`` de forma segura. |
| `def _coerce_effect(value)`  (L719) | Convierte un efecto soportado a ``Effect``. |
| `def _update_application_state(state, app_name, changes)`  (L747) | Actualiza, cuando existe, el formato anidado ``applications``. |
| `def _update_ui_element_state(state, app_name, element_name, changes)`  (L770) | Actualiza, cuando existe, el formato ``ui_elements`` compatible. |

<a name="src-hands-planner-task_executor-py"></a>
### `src/hands/planner/task_executor.py` [1097 líneas] — Ejecutor de tareas HTN integrado con las capacidades reales de JARVIS.

**Descripción:** Ejecutor de tareas HTN integrado con las capacidades reales de JARVIS.

**Importaciones:** 23.

`class TaskExecutorStatus(Enum)`  (línea 80)

_Sin métodos definidos en el AST._

`class TaskExecutionMode(Enum)`  (línea 89)

_Sin métodos definidos en el AST._

`class TaskExecutionConfig`  (línea 97)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |
| `def _safe_int(value, default)` |  |
| `def _safe_float(value, default)` |  |

`class TaskExecutor`  (línea 129) — Ejecutor HTN que delega las acciones sin simular ejecuciones.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config)` |  |
| `def _safe_get(factory, label)` |  |
| `def _task_metadata(task)` |  |
| `def _task_application(task)` |  |
| `def _task_parameters(task)` |  |
| `def execute_task(task, current_state)` | Prepara y ejecuta una tarea individual. |
| `def _register_failure(task, error_message, started, result, current_state)` |  |
| `def _failed_result(task, error_message, started, result, current_state)` |  |
| `def execute_task_with_retry(task, current_state)` | Reintenta solo cuando la tarea declara explícitamente que es segura. |
| `def execute_task_hierarchy(tasks, current_state, mode)` |  |
| `def _prepare_task_execution(task, current_state)` |  |
| `def _check_task_preconditions(task, current_state)` |  |
| `def _evaluate_precondition(condition, state)` |  |
| `def _convert_task_to_node(task, current_state)` |  |
| `def _calculate_task_cost(task, current_state)` |  |
| `def _resolve_action_name(task)` |  |
| `def _create_execution_callback(task)` |  |
| `def _call_callback(callback, kwargs)` |  |
| `def _truthy_success(value)` |  |
| `def _normalize_execution_result(result)` | Normaliza respuestas y exige evidencia explícita de éxito. |
| `def _execute_real_capability(task, kwargs)` | Ejecuta una acción registrada o la delega en el executor principal. |
| `def _delegate_to_executor(executor, task, action_name, parameters, current_state)` | Adapta firmas conocidas; no repite una llamada que ya fue invocada. |
| `def _signature_accepts(signature, args, kwargs)` |  |
| `def _create_success_criteria(task)` |  |
| `def _execute_node(node, current_state)` |  |
| `def _apply_result_to_state(current_state, result)` |  |
| `def _execute_fallback(task, current_state)` |  |
| `def _execute_prepare_navigator()` |  |
| `def _execute_navigate_to_target()` |  |
| `def _execute_check_availability()` |  |
| `def _execute_open_application()` |  |
| `def _execute_activate_window()` |  |
| `def _execute_navigate_to_search_engine()` |  |
| `def _execute_perform_search()` |  |
| `def _execute_legacy_task_capability(task_id, kwargs)` | Compatibilidad para IDs HTN anteriores, delegando en capacidades reales. |
| `def _execute_resolve_entity()` | Resuelve una entidad usando el resolver de memoria real. |
| `def _get_conversation_history()` |  |
| `def _get_current_intent()` |  |
| `def _get_recent_entities()` |  |
| `def _get_user_preferences()` |  |
| `def _get_session_info()` |  |
| `def _update_world_state_with_entity(resolution)` |  |
| `def _execute_sequential(tasks, current_state)` |  |
| `def _execute_parallel(tasks, current_state)` | Ejecuta tareas independientes en paralelo con estados aislados. |
| `def _execute_conditional(tasks, current_state)` |  |
| `def _execute_with_fallback(tasks, current_state)` |  |
| `def _should_execute_conditionally(task, current_state)` |  |
| `def _update_execution_statistics(execution_time)` |  |
| `def get_execution_statistics()` |  |
| `def _as_list(value)` |  |
| `def _normalize_key(value)` |  |
| `def _safe_number(value, default)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_htn_manager()`  (L34) | Obtiene el HTN Manager de forma diferida. |
| `def get_application_knowledge_integrator()`  (L45) | Obtiene el integrador de conocimiento de aplicaciones. |
| `def get_executor()`  (L58) | Obtiene el executor principal de JARVIS de forma diferida. |
| `def get_action_registry()`  (L69) | Obtiene el registro central de acciones de forma diferida. |
| `def get_task_executor()`  (L1077) | Obtiene el singleton de TaskExecutor con inicialización protegida. |

## 🖐️ `src/hands/`

<!-- src/hands -->

<a name="src-hands-universal_visual_calibrator-py"></a>
### `src/hands/universal_visual_calibrator.py` [922 líneas] — Calibrador visual universal para la arquitectura de planificación jerárquica.

**Descripción:** Calibrador visual universal para la arquitectura de planificación jerárquica.

**Importaciones:** 12.

`class CalibrationPolicy`  (línea 30) — Política centralizada de seguridad, no una allowlist de aplicaciones.

Métodos:

| Firma | Docstring |
|---|---|
| `def can_calibrate_application(cls, application_name)` |  |
| `def can_calibrate_element(cls, element_type, confidence)` |  |
| `def _normalize_name(name)` |  |

`class UICapability`  (línea 202) — Representa un elemento UI calibrado y consumible por acciones.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, element_type, center, bbox, screen, confidence)` |  |
| `def to_dict()` |  |

`class CalibrationState`  (línea 234) — Estado en memoria de los elementos calibrados.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def get_element(application, element_name, monitor_number)` |  |
| `def get_application_elements(application, monitor_number)` |  |
| `def add_element(application, element, monitor_number)` |  |
| `def is_element_calibrated(application, element_name, monitor_number)` |  |
| `def get_calibration_age(application)` |  |
| `def _normalize_application(value)` |  |
| `def _normalize_element(value)` |  |

`class UniversalVisualCalibrator`  (línea 332) — Calibrador visual universal integrado con las capas superiores.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(memory)` |  |
| `def get_ui_capability(application, element_name, monitor_number, screenshot_path)` |  |
| `def calibrate_application_elements(application, monitor_number, screenshot_path)` |  |
| `def calibrate(application_name, monitor_number, screenshot_path)` |  |
| `def _calibrate_element(application, monitor_number, screenshot_path, required_element)` |  |
| `def _build_prompt(application_name)` |  |
| `def _parse_response(response)` |  |
| `def _get_image_size(screenshot_path)` |  |
| `def _normalize_elements(raw_elements, monitor, image_width, image_height)` |  |
| `def _normalize_single_element(raw_element, monitor, image_width, image_height)` |  |
| `def _extract_image_bbox(raw_element, image_width, image_height)` |  |
| `def _bbox_to_image_pixels(values, image_width, image_height)` |  |
| `def _image_bbox_to_monitor_bbox(image_bbox, monitor, image_width, image_height)` |  |
| `def _looks_normalized(values)` |  |
| `def _normalize_element_name(value)` |  |
| `def _normalize_confidence(value)` |  |
| `def _deduplicate_elements(elements)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_calibrator(memory)`  (L892) |  |
| `def get_ui_capability(application, element_name, monitor_number, screenshot_path)`  (L901) |  |

## 🪟 `src/hands/windows/`

<!-- src/hands/windows -->

<a name="src-hands-windows-__init__-py"></a>
### `src/hands/windows/__init__.py` [3 líneas] — Módulo específico para aplicaciones de Windows.

**Descripción:** Módulo específico para aplicaciones de Windows.

**Importaciones:** 0.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-hands-windows-calibrator_windows-py"></a>
### `src/hands/windows/calibrator_windows.py` [263 líneas] — Adaptador de compatibilidad para la calibración de aplicaciones Windows.

**Descripción:** Adaptador de compatibilidad para la calibración de aplicaciones Windows.

**Importaciones:** 3.

`class WindowsCalibrator`  (línea 43) — Adaptador legacy hacia CalibrationManager.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def get_calibration_prompt(app_name)` | Mantiene la API antigua por compatibilidad. |
| `def calibrate_app_both_screens(app_name)` | Mantiene el nombre antiguo por compatibilidad. |
| `def calibrate_app(app_name)` | API de compatibilidad para calibrar una aplicación concreta. |
| `def _calibrate_universal(app_name)` | Delega la calibración en CalibrationManager. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def calibrate_app(app_name)`  (L218) | Función pública de compatibilidad. |

<a name="src-hands-windows-windows-py"></a>
### `src/hands/windows/windows.py` [694 líneas] — Funciones auxiliares para aplicaciones de Windows.

**Descripción:** Funciones auxiliares para aplicaciones de Windows.

**Importaciones:** 16.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def actualizar_api_key_riot()`  (L51) | Abre Riot Developer Portal y solicita un análisis visual. |
| `def _capturar_pantalla(filepath)`  (L120) | Captura el escritorio completo. |
| `def _abrir_aplicacion_windows(nombre_app)`  (L163) | Intenta abrir una aplicación de Windows. |
| `def _get_window_search_patterns(nombre_app)`  (L231) | Devuelve patrones de título compatibles con aplicaciones comunes. |
| `def _get_application_windows(nombre_app)`  (L271) | Busca ventanas de una aplicación por título. |
| `def _verificar_aplicacion_abierta(nombre_app)`  (L296) | Verifica si una aplicación tiene al menos una ventana visible. |
| `def _mover_aplicacion_a_pantalla(nombre_app, pantalla_num)`  (L329) | Mueve una aplicación a un monitor concreto. |
| `def _cerrar_aplicacion_windows(nombre_app)`  (L428) | Cierra una ventana de la aplicación. |
| `def _get_default_calibration_screen_number(screen_manager)`  (L486) | Obtiene un monitor real de referencia para una API legacy. |
| `def _calibrar_aplicacion_windows(nombre_app)`  (L521) | API legacy. |
| `def _obtener_elementos_aplicacion(nombre_app)`  (L578) | API legacy. |
| `def _generar_coordenadas_aplicacion(nombre_app, tipo_elemento)`  (L593) | API legacy. |
| `def _capturar_aplicacion_windows(nombre_app)`  (L616) | Captura la ventana de una aplicación. |
| `def _safe_filename(value)`  (L667) | Convierte un nombre de aplicación en un nombre de archivo seguro. |
| `def get_windows_commands()`  (L681) | Devuelve las funciones públicas/legacy asociadas a Windows. |

## 🧠 `src/memory/`

<!-- src/memory -->

<a name="src-memory-__init__-py"></a>
### `src/memory/__init__.py` [78 líneas] — Módulo de memoria mejorado para soportar planificación jerárquica.

**Descripción:** Módulo de memoria mejorado para soportar planificación jerárquica.

**Importaciones:** 4.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-memory-conversation-py"></a>
### `src/memory/conversation.py` [1129 líneas] — Memoria conversacional y del dominio

**Descripción:** Modelo de planificación en memoria (`Goal`/`Node`/`Task`) y gestor unificado `ConversationMemory`. `DomainMemory` (FASE 5) carga `knowledge/entities.json`, `applications.json`, `capabilities.json` y mantiene interacciones/preferencias; `ConversationMemory` combina chat, predictivo y dominio, y gestiona aliases estáticos y aprendidos (FASE 16).

**Características:**

- FASE 5: Domain Memory
- Jerarquía Goal/Node/Task para planificación
- Carga de conocimiento de dominio estático
- Aliases estáticos + aprendidos (FASE 16 compat)
- Insights de aprendizaje y stats de uso

**Importaciones:** 13.

`class NodeType(Enum)`  (línea 34) — Tipos de nodos en el sistema de planificación.

_Sin métodos definidos en el AST._

`class TaskStatus(Enum)`  (línea 49) — Estado de ejecución de tareas.

_Sin métodos definidos en el AST._

`class Node`  (línea 59) — Modelo básico de nodo para memoria.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class Goal`  (línea 76) — Modelo básico de objetivo para memoria.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class Task`  (línea 88) — Modelo básico de tarea para memoria.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class Task`  (línea 104) — Tarea jerárquica (FASE 2).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def can_execute(current_state, all_nodes)` | Verifica si la tarea puede ejecutarse. |

`class DomainMemory`  (línea 130) — Memoria de conocimiento del dominio (FASE 5).

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def load_domain_knowledge()` | Carga conocimiento del dominio desde archivos. |
| `def load_user_preferences()` | Carga preferencias del usuario desde archivo persistente. |
| `def save_user_preferences()` | Guarda preferencias del usuario de forma persistente. |
| `def get_entity(entity_name)` | Obtiene una entidad por nombre o alias. |
| `def get_application_capabilities(app_name)` | Obtiene capacidades de una aplicación. |
| `def get_capability_definition(category, capability)` | Obtiene definición detallada de una capacidad. |
| `def record_user_interaction(user_input, entity_used, action_taken, success)` | Registra interacción del usuario para aprendizaje y preferencias. |
| `def _update_preferences_from_interaction(interaction)` | Actualiza preferencias basadas en interacciones exitosas. |
| `def get_user_preferences()` | Obtiene preferencias del usuario. |
| `def get_preferred_entities(entity_type)` | Obtiene entidades preferidas por el usuario. |
| `def get_preferred_application(action_type)` | Obtiene aplicación preferida para un tipo de acción. |
| `def add_knowledge_update(update_type, content)` | Añade actualización de conocimiento para persistencia futura. |
| `def get_suggested_entities(partial_name, limit)` | Obtiene sugerencias de entidades basadas en nombre parcial y preferencias. |
| `def reason_about_entities(context)` | Realiza razonamiento básico sobre entidades basado en contexto y preferencias. |
| `def _normalize_text(text)` | Normaliza texto para búsqueda. |

`class ConversationMemory`  (línea 408) — Sistema de memoria transformado para planificación jerárquica.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _normalize_text(text)` | Normaliza texto para búsqueda. |
| `def _remove_wake_word(text)` | Elimina 'jarvis' inicial. |
| `def _load_aliases()` | Carga aliases (mantener compatibilidad FASE 16). |
| `def parse_user_input(user_input)` | Transforma entrada de usuario en objetivo (FASE 15). |
| `def _extract_intention(normalized_text)` | Extrae intención del texto normalizado. |
| `def _create_goal_from_intention(intention)` | Crea objetivo a partir de intención. |
| `def create_plan_from_goal(goal)` | Crea un plan a partir de un objetivo (FASE 6, 7). |
| `def update_world_state(state_update)` | Actualiza el estado del mundo. |
| `def add_user_message(user_text)` | Añade mensaje de usuario a la memoria conversacional (compatibilidad). |
| `def get_current_state()` | Obtiene estado actual del mundo. |
| `def _check_achieved_goals()` | Verifica si algún objetivo ha sido alcanzado. |
| `def create_node(node_config)` | Crea un nodo en el sistema de planificación. |
| `def create_task(task_config)` | Crea una tarea jerárquica. |
| `def get_applicable_nodes(current_state)` | Obtiene nodos aplicables en el estado actual. |
| `def get_alias(transcribed_text)` | Método de compatibilidad para aliases antiguos. |
| `def record_command_usage(user_input, command_executed, success)` | Registra uso de comando para análisis predictivo (compatibilidad). |
| `def save_conversation(user_text, assistant_text, goal, plan, execution_result)` | Guarda conversación con información de planificación. |
| `def get_conversation_history()` | Obtiene historial con información de planificación. |
| `def clear_history()` | Borra historial de conversaciones. |
| `def clear_predictive_data()` | Borra datos predictivos. |
| `def get_learning_insights()` | Obtiene insights de aprendizaje del nuevo sistema. |
| `def save_domain_knowledge_persistence()` | Guarda el estado completo del conocimiento de dominio para persistencia. |
| `def _get_most_used_entities()` | Obtiene las entidades más usadas basadas en interacciones. |
| `def _get_most_used_actions()` | Obtiene las acciones más usadas basadas en interacciones. |
| `def load_domain_knowledge_persistence()` | Carga conocimiento de dominio persistido. |

<a name="src-memory-entity_resolver-py"></a>
### `src/memory/entity_resolver.py` [825 líneas] — Resolución avanzada de entidades

**Descripción:** Resolución de entidades con contexto: extracción de URLs (twitch/youtube/github/spotify → plataforma e ID de canal), creación de entidades desde URL, coincidencia difusa (`difflib`) y manejo de ambigüedades con alternativas y umbral de confianza (0.7).

**Características:**

- Extracción y parseo de URLs
- Creación de entidades desde URL
- Coincidencia difusa y ambigüedades
- Conteo de interacciones y scores de preferencia (FASE 18)

**Importaciones:** 11.

`class EntityResolutionResult`  (línea 28) — Resultado de la resolución de entidad.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ResolutionContext`  (línea 39) — Contexto para resolución de entidades.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class EntityResolver`  (línea 48) — Sistema avanzado de resolución de entidades.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(memory_manager)` |  |
| `def resolve_entity(entity_reference, context, entity_type)` | Resuelve una referencia de entidad a una entidad específica. |
| `def resolve_entities_batch(entity_references, context)` | Resuelve múltiples entidades en lote. |
| `def _normalize_reference(reference)` | Normaliza una referencia de entidad. |
| `def _find_exact_matches(reference, entity_type)` | Busca coincidencias exactas. |
| `def _find_fuzzy_matches(reference, entity_type)` | Busca coincidencias difusas. |
| `def _find_by_properties(reference, entity_type)` | Busca entidades por propiedades. |
| `def _select_best_match(matches, reference, context)` | Selecciona la mejor coincidencia basada en contexto. |
| `def _disambiguate_with_context(matches, reference, context)` | Usa contexto para desambiguar entre múltiples entidades. |
| `def _create_temporary_entity(reference, entity_type)` | Crea una entidad temporal para referencias no encontradas. |
| `def get_entity_suggestions(partial_text, entity_type, limit)` | Obtiene sugerencias de entidades basadas en texto parcial. |
| `def resolve_url(url_input, context)` | Resuelve una URL a una entidad específica del sistema. |
| `def extract_urls_from_text(text)` | Extrae todas las URLs de un texto. |
| `def _normalize_url(url_input)` | Normaliza una URL de entrada. |
| `def _parse_url(url)` | Parsea una URL y extrae información estructurada. |
| `def _create_entity_from_url(url_info, url, context)` | Crea una entidad basada en información de URL. |
| `def get_url_suggestions(partial_url, limit)` | Obtiene sugerencias de entidades basadas en URL parcial. |
| `def learn_from_resolution(result, user_feedback)` | Aprende de los resultados de resolución para mejorar futuras resoluciones. |
| `def set_user_preference(entity_id, preference_type, preference_value, context)` | Establece una preferencia de usuario para una entidad. |
| `def get_user_preferences_for_entity(entity_id)` | Obtiene todas las preferencias del usuario para una entidad específica. |
| `def get_preferred_entities(preference_type)` | Obtiene entidades preferidas por el usuario. |
| `def set_entity_attribute(entity_id, attribute_name, attribute_value, attribute_type, source, metadata)` | Establece un atributo extendido para una entidad. |
| `def get_entity_attributes(entity_id)` | Obtiene todos los atributos extendidos de una entidad. |
| `def get_entities_with_attribute(attribute_name, attribute_value)` | Busca entidades que tienen un atributo específico. |
| `def learn_entity_interaction(entity_id, interaction_type, success, metadata)` | Aprende de interacciones con entidades y actualiza atributos. |

<a name="src-memory-prediction-py"></a>
### `src/memory/prediction.py` [1081 líneas] — Memoria predictiva

**Descripción:** Inferencia predictiva de objetivos/acciones desde histórico de uso (FASE 15/17/18) e integración con `ConversationMemory`. Registra eventos de ejecución y mantiene `ExecutionMetrics` para el aprendizaje.

**Características:**

- FASE 15: comandos de alto nivel
- FASE 17: optimización predictiva
- FASE 18: métricas de ejecución
- Compat con estadísticas legacy + formato nuevo

**Importaciones:** 18.

`class PredictionResult`  (línea 32) — Resultado de predicción para planificación.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ExecutionMetrics`  (línea 44) — Métricas de ejecución para aprendizaje (FASE 18).

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class EnhancedPredictionMemory`  (línea 56) — Memoria predictiva mejorada que integra:

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(filepath)` |  |
| `def _load()` | Carga datos con migración a nuevo formato. |
| `def _initialize_goal_templates()` | Inicializa plantillas de objetivos para predicción rápida. |
| `def _migrate_enhanced_data(loaded)` | Migra datos al nuevo formato mejorado. |
| `def _can_migrate_to_goal(event)` | Verifica si un evento puede migrarse a goal. |
| `def _migrate_event_to_goal(event)` | Migra evento a formato goal. |
| `def _infer_goal_type_from_command(command)` | Infiere tipo de goal desde comando legacy. |
| `def predict_goal_from_input(user_input, current_state)` | Predice objetivo basado en entrada de usuario (FASE 15). |
| `def _normalize_input(text)` | Normaliza texto para análisis. |
| `def _analyze_historical_patterns(normalized_input)` | Analiza patrones históricos para predicción. |
| `def _analyze_state_influence(current_state, normalized_input)` | Analiza cómo el estado actual influye en la predicción. |
| `def _predict_entity_usage(normalized_input)` | Predice uso de entidades basado en entrada. |
| `def _combine_predictions(normalized_input, historical, state, entity)` | Combina diferentes predicciones para crear goal. |
| `def _determine_goal_type(normalized_input, historical, state, entity)` | Determina el tipo de goal más probable. |
| `def _extract_goal_target(normalized_input, entity)` | Extrae target del goal basado en entrada y entidades. |
| `def _calculate_prediction_confidence(goal, historical, state, entity)` | Calcula confianza en la predicción. |
| `def _find_alternative_goals(normalized_input, current_state)` | Busca goals alternativos basados en entrada. |
| `def _generate_synonym_goals(normalized_input)` | Genera goals alternativos usando sinónimos. |
| `def _generate_state_based_goals(normalized_input, current_state)` | Genera goals alternativos basados en estado actual. |
| `def _estimate_goal_cost(goal, current_state)` | Estima coste de ejecución del goal. |
| `def _estimate_execution_probability(goal, current_state)` | Estima probabilidad de éxito del goal. |
| `def _get_historical_success_rate(goal_type)` | Obtiene tasa de éxito histórica para tipo de goal. |
| `def _get_command_success_rate(command)` | Obtiene tasa de éxito para comando legacy. |
| `def _generate_prediction_reasoning(goal, historical, state)` | Genera explicación de la predicción. |
| `def record_goal_execution(goal, success, execution_time, actual_cost, context, error_message, replanifications)` | Registra ejecución de goal para aprendizaje (FASE 18). |
| `def _update_success_patterns(goal, success)` | Actualiza patrones de éxito por tipo de goal. |
| `def _update_cost_estimations(goal, actual_cost)` | Actualiza estimaciones de coste. |
| `def _update_path_cache(goal, success, execution_time, actual_cost)` | Actualiza caché de rutas exitosas. |
| `def _update_entity_usage(goal, context)` | Actualiza estadísticas de uso de entidades. |
| `def get_goal_prediction_history(goal_type)` | Obtiene historial de predicciones de goals. |
| `def get_cached_path(goal_type, target)` | Obtiene ruta cacheada para goal específico. |
| `def get_cost_estimation(goal_type)` | Obtiene estimación de coste para tipo de goal. |
| `def get_success_rate(goal_type)` | Obtiene tasa de éxito para tipo de goal. |
| `def record_command(command, success, source)` | Método legacy para registrar comandos (FASE 16). |
| `def _create_legacy_event(command, success, source)` | Crea evento en formato legacy. |
| `def _get_open_windows()` | Obtiene ventanas abiertas (legacy). |
| `def _get_active_window()` | Obtiene ventana activa (legacy). |
| `def _get_system_state(open_windows, active_window)` | Obtiene estado del sistema (legacy). |
| `def _get_idle_seconds()` | Obtiene segundos de inactividad (legacy). |
| `def _save()` | Guarda datos en archivo. |

`class PredictionMemory(EnhancedPredictionMemory)`  (línea 1070) — Clase legacy para compatibilidad (FASE 16).

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(filepath)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_enhanced_prediction_memory()`  (L1055) | Obtiene instancia singleton de memoria predictiva mejorada. |
| `def get_prediction_memory()`  (L1079) | Función singleton legacy para compatibilidad. |

<a name="src-memory-storage-py"></a>
### `src/memory/storage.py` [1984 líneas] — Sistema de almacenamiento y gestión de memoria

**Descripción:** Núcleo duradero de JARVIS. `JSONStorage` guarda/carga JSON thread-safe con cache y retención; `MemoryManager` (singleton) lo abstrae indexando por `MemoryType` y añade CRUD de entidades/atributos/relaciones/preferencias y stats de aprendizaje, cache, locking y estadísticas.

**Características:**

- Soporte de todos los `MemoryType` del sistema
- CRUD de entidades, atributos y relaciones con semántica de grafo
- Gestión de preferencias de usuario y estadísticas de aprendizaje
- Cache multi-nivel con coherencia (`cache_lock`)
- Singleton vía `get_memory_manager()`

**Importaciones:** 14.

`class MemoryType(Enum)`  (línea 30) — Tipos de memoria en el sistema mejorado.

_Sin métodos definidos en el AST._

`class Entity`  (línea 46) — Entidad mejorada para memoria de dominio (FASE 5).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |
| `def matches_query(query)` | Verifica si la entidad coincide con una búsqueda. |

`class ConversationalMemory`  (línea 95) — Memoria conversacional mejorada.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |

`class WorldState`  (línea 123) — Estado del mundo mejorado (FASE 3).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |
| `def get_application_state(app_name)` | Obtiene el estado de una aplicación específica. |
| `def get_ui_element_state(element_name)` | Obtiene el estado de un elemento UI específico. |

`class Plan`  (línea 153) — Plan de ejecución (FASE 6-7).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |

`class ExecutionRecord`  (línea 188) — Registro de ejecución para aprendizaje (FASE 18).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |

`class LearningStat`  (línea 220) — Estadística de aprendizaje (FASE 18).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def update(success, execution_time)` | Actualiza estadísticas con nueva ejecución. |

`class UserPreference`  (línea 255) — Preferencia de usuario (SUBFASE 5.4).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |

`class EntityAttribute`  (línea 291) — Atributo extendido de entidad (SUBFASE 5.4).

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |
| `def from_dict(cls, data)` | Crea desde diccionario. |

`class MemoryStorage(ABC)`  (línea 324) — Interfaz abstracta para almacenamiento de memoria.

Métodos:

| Firma | Docstring |
|---|---|
| `def save(data, memory_type)` | Guarda datos. |
| `def load(memory_type)` | Carga datos. |
| `def exists(memory_type)` | Verifica si existe. |

`class JSONStorage(MemoryStorage)`  (línea 343) — Almacenamiento en archivos JSON con manejo avanzado.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(base_path)` |  |
| `def get_file_path(memory_type)` | Obtiene la ruta del archivo para un tipo de memoria. |
| `def save(data, memory_type)` | Guarda datos en archivo JSON con manejo inteligente. |
| `def _load_existing_data(file_path)` | Carga datos existentes del archivo. |
| `def _process_data_for_save(new_data, existing_data, memory_type)` | Procesa datos según el tipo de memoria. |
| `def load(memory_type)` | Carga datos desde archivo JSON. |
| `def _get_default_value(memory_type)` | Obtiene valor por defecto para un tipo de memoria. |
| `def exists(memory_type)` | Verifica si el archivo existe. |

`class MemoryManager`  (línea 581) — Gestor de memoria mejorado con caché y soporte completo para arquitectura.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(storage_path)` |  |
| `def _warm_cache()` | Inicializa el caché con datos frecuentes. |
| `def _get_from_cache(key, memory_type)` | Obtiene datos del caché si están frescos. |
| `def _update_cache(key, data, memory_type)` | Actualiza el caché con nuevos datos. |
| `def save_entity(entity)` | Guarda una entidad en la memoria de dominio. |
| `def get_entity(entity_id)` | Obtiene una entidad por su ID. |
| `def get_entities_by_type(entity_type)` | Obtiene todas las entidades de un tipo específico. |
| `def find_entities(query, entity_type)` | Busca entidades por texto en nombre, aliases, tags y propiedades. |
| `def find_entities_by_property(property_name, property_value)` | Busca entidades por propiedad específica. |
| `def add_conversational_memory(message, response, context, intent, entities, success, execution_time, confidence)` | Añade un registro mejorado a la memoria conversacional. |
| `def get_conversational_memory(limit, intent)` | Obtiene la memoria conversacional con filtros. |
| `def save_world_state(state)` | Guarda el estado actual del mundo. |
| `def get_world_state()` | Obtiene el estado actual del mundo. |
| `def update_world_state(key, value)` | Actualiza una propiedad del estado del mundo. |
| `def save_plan(plan)` | Guarda un plan. |
| `def get_plan(plan_id)` | Obtiene un plan por su ID. |
| `def save_execution_record(record)` | Guarda un registro de ejecución. |
| `def update_learning_stats(action_name, success, execution_time)` | Actualiza estadísticas de aprendizaje para una acción. |
| `def get_learning_stats(action_name)` | Obtiene estadísticas de aprendizaje. |
| `def clear_memory(memory_type)` | Limpia la memoria especificada o toda la memoria. |
| `def get_memory_stats()` | Obtiene estadísticas detalladas de la memoria. |
| `def save_user_preference(preference)` | Guarda una preferencia de usuario. |
| `def get_user_preference(user_id, preference_type, preference_key)` | Obtiene una preferencia específica del usuario. |
| `def get_user_preferences(user_id, preference_type)` | Obtiene todas las preferencias de un usuario. |
| `def update_user_preference(user_id, preference_type, preference_key, value, context)` | Actualiza o crea una preferencia de usuario. |
| `def learn_user_preference(user_id, entity_id, interaction_type, success)` | Aprende preferencias de usuario basadas en interacciones. |
| `def save_entity_attribute(attribute)` | Guarda un atributo extendido de entidad. |
| `def get_entity_attribute(entity_id, attribute_name)` | Obtiene un atributo específico de una entidad. |
| `def get_entity_attributes(entity_id)` | Obtiene todos los atributos extendidos de una entidad. |
| `def update_entity_attribute(entity_id, attribute_name, value, attribute_type, source, metadata)` | Actualiza o crea un atributo extendido de entidad. |
| `def get_entities_by_attribute(attribute_name, attribute_value)` | Busca entidades por atributo y valor. |
| `def export_memory(export_path)` | Exporta toda la memoria a un archivo JSON. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_memory_manager()`  (L1650) | Obtiene la instancia global del gestor de memoria. |
| `def save_entity(entity)`  (L1660) | Guarda una entidad. |
| `def get_entity(entity_id)`  (L1665) | Obtiene una entidad. |
| `def get_entities_by_type(entity_type)`  (L1670) | Obtiene entidades. |
| `def find_entities(query, entity_type)`  (L1675) | Busca entidades. |
| `def add_conversational_memory(message, response)`  (L1686) | Añade memoria conversacional. |
| `def get_world_state()`  (L1699) | Obtiene el estado del mundo. |
| `def update_world_state(key, value)`  (L1704) | Actualiza el estado del mundo. |
| `def save_plan(plan)`  (L1712) | Guarda un plan. |
| `def get_plan(plan_id)`  (L1717) | Obtiene un plan. |
| `def update_learning_stats(action_name, success, execution_time)`  (L1722) | Actualiza estadísticas de aprendizaje. |
| `def resolve_entity_to_url(entity)`  (L1735) | Resuelve una entidad a una URL. |
| `def get_entity_attributes(entity)`  (L1775) | Obtiene atributos extendidos de una entidad. |
| `def create_goal_from_entity(entity, user_input)`  (L1831) | Integración entidad -> Goal. |
| `def verify_entity_integrity(entity)`  (L1898) | Verifica la integridad de una entidad. |

## 🗣️ `src/mouth/`

<!-- src/mouth -->

<a name="src-mouth-__init__-py"></a>
### `src/mouth/__init__.py` [4 líneas] — Módulo de sistema

**Descripción:** Módulo de sistema.

**Importaciones:** 1.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-mouth-speaker-py"></a>
### `src/mouth/speaker.py` [680 líneas] — Síntesis de voz

**Descripción:** Síntesis de voz (TTS) multi-backend con control asíncrono, voz, velocidad y cancelación.

**Características:**

- TTS multi-backend
- Habla asíncrona
- Control de voz/velocidad

**Importaciones:** 15.

`class Mouth`  (línea 32) — Controla la síntesis de voz utilizando el motor Kokoro ONNX.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` | Inicializa el motor de síntesis de voz. |
| `def _initialize_session()` | Inicializa la sesión ONNX. |
| `def _load_parameters()` | Carga los parámetros necesarios del motor. |
| `def get_available_voices()` | Devuelve los IDs de voz disponibles en models/voices. |
| `def has_voice(voice_id)` | Comprueba si existe una voz concreta. |
| `def _load_voice_style_vector(voice_id)` | Carga el vector de estilo correspondiente a voice_id. |
| `def _load_voice(voice_id, persist)` | Carga una voz y la establece como voz actual. |
| `def set_voice(voice_id)` | Cambia la voz actualmente utilizada. |
| `def get_current_voice()` | Devuelve el ID de la voz actualmente activa. |
| `def _load_token_map()` | Carga el mapa de tokens. |
| `def _text_to_tokens(text, voice_id)` | Convierte texto a tokens para el modelo. |
| `def speak(text, voice_id, output_file)` | Convierte texto a voz y lo reproduce. |
| `def speak_async(text, voice_id, output_file)` | Versión async de speak que no bloquea. |

## 🔧 `src/tools/`

<!-- src/tools -->

<a name="src-tools-__init__-py"></a>
### `src/tools/__init__.py` [30 líneas] — Paquete de herramientas de Jarvis.

**Descripción:** Paquete de herramientas de Jarvis.

**Importaciones:** 2.

_Archivo de marcador de posición / inicialización de paquete._

<a name="src-tools-executor-py"></a>
### `src/tools/executor.py` [559 líneas] — Fachada de ejecución compatible para JARVIS.

**Descripción:** Fachada de ejecución compatible para JARVIS.

**Importaciones:** 7.

`class UnifiedExecutor`  (línea 42) — Fachada unificada para ejecutar acciones registradas.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` | Inicializa la fachada de ejecución. |
| `def process_and_execute(llm_response, state)` | Procesa una respuesta del LLM y ejecuta el primer comando detectado. |
| `def _extract_command(response)` | Extrae un comando legacy del formato [CMD:nombre(args)]. |
| `def _normalize_action_name(action_name)` | Normaliza pequeñas variaciones de nombre sin cambiar su semántica. |
| `def execute_action(action_name, parameters, state, verify_success)` | Ejecuta una acción registrada. |
| `def can_execute(action_name, parameters, state)` | Comprueba si una acción puede ejecutarse en el estado indicado. |
| `def execute_plan_step(action_name, parameters, state)` | Punto de entrada explícito para un futuro Planner. |
| `def _parse_args(args_str)` | Parsea argumentos legacy mediante ast.literal_eval. |
| `def _args_to_dict(args, parameters)` | Convierte argumentos posicionales legacy a parámetros nombrados. |
| `def get_command_suggestions(user_input, context)` | Obtiene sugerencias simples a partir de acciones registradas. |
| `def _format_action_suggestion(action_info, score)` | Convierte ActionInfo al formato histórico de sugerencias. |
| `def _record_history(command_name, args, result, success)` | Registra una ejecución para compatibilidad y diagnóstico. |
| `def get_command_history()` | Obtiene una copia del historial de comandos. |
| `def clear_command_history()` | Limpia el historial de comandos. |
| `def list_available_commands(planner_only)` | Lista las acciones disponibles con sus metadatos. |
| `def get_command_info(command_name)` | Obtiene información detallada de una acción registrada. |
| `def get_action_cost(action_name)` | Obtiene el coste declarado de una acción para el planificador. |
| `def get_plannable_commands()` | Obtiene las acciones habilitadas para planificación. |
| `def _get_timestamp()` | Obtiene la fecha/hora actual en formato ISO. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_executor()`  (L536) | Obtiene la instancia global del ejecutor unificado. |
| `def process_and_execute(llm_response)`  (L551) | Función de compatibilidad para código existente. |

<a name="src-tools-os_info-py"></a>
### `src/tools/os_info.py` [533 líneas] — Información del sistema para Jarvis con arquitectura de planificación.

**Descripción:** Información del sistema para Jarvis con arquitectura de planificación.

**Importaciones:** 11.

`class SystemHealth(Enum)`  (línea 36) — Estados de salud del sistema.

_Sin métodos definidos en el AST._

`class ApplicationWindow`  (línea 45) — Información de una ventana de aplicación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |

`class SystemResources`  (línea 73) — Recursos del sistema.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario. |

`class SystemContext`  (línea 103) — Contexto completo del sistema para planificación.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte a diccionario para estado del mundo. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _get_system_drive()`  (L124) | Obtiene la unidad del sistema. |
| `def _calculate_system_health(cpu_percent, ram_percent, disk_percent)`  (L139) | Calcula la salud del sistema basada en recursos. |
| `def get_system_stats()`  (L151) | Lee el estado de CPU, memoria RAM y disco. |
| `def get_battery_info()`  (L211) | Obtiene información de la batería. |
| `def get_open_windows()`  (L227) | Obtiene información detallada de ventanas visibles. |
| `def _get_monitor_from_position(x, y)`  (L313) | Determina qué monitor contiene la posición dada. |
| `def _get_process_name(window)`  (L330) | Obtiene el nombre del proceso de una ventana. |
| `def get_focused_window()`  (L364) | Obtiene la ventana actualmente enfocada. |
| `def get_running_processes()`  (L380) | Obtiene lista de procesos en ejecución. |
| `def get_system_resources()`  (L395) | Obtiene recursos del sistema con estado de salud. |
| `def get_jarvis_system_context()`  (L437) | Empaqueta la información del sistema en un texto para el contexto |
| `def get_system_context()`  (L469) | Obtiene el contexto completo del sistema para planificación. |

<a name="src-tools-registry-py"></a>
### `src/tools/registry.py` [1072 líneas] — Registro unificado de acciones para Jarvis - VERSIÓN INTEGRADA.

**Descripción:** Registro unificado de acciones para Jarvis - VERSIÓN INTEGRADA.

**Importaciones:** 8.

`class ActionType(Enum)`  (línea 27) — Tipos de acciones disponibles.

_Sin métodos definidos en el AST._

`class ActionInfo`  (línea 125) — Metadatos completos de una acción ejecutable y planificable.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Devuelve una representación serializable de los metadatos. |
| `def matches_preconditions(state)` | Comprueba las precondiciones de la acción contra un estado. |
| `def verify_success(result)` | Comprueba el éxito de la acción mediante su verificador opcional. |

`class ActionRegistry`  (línea 192) — Registro unificado de acciones para Jarvis.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` | Inicializa el registro de acciones. |
| `def _normalize_name(name)` | Normaliza el nombre de una acción. |
| `def _normalize_description(description)` | Normaliza la descripción de una acción. |
| `def _normalize_confidence(value)` | Normaliza el umbral de confianza al rango [0.0, 1.0]. |
| `def _normalize_action_type(action_type)` | Convierte un ActionType o su valor textual a ActionType. |
| `def _extract_parameters(func)` | Extrae un esquema básico de parámetros desde la firma de una función. |
| `def register_action(name, description, action_type, category, tags, parameters, confidence_threshold, preconditions, effects, cost, dependencies, capability, application, required_resources, requires_ui_element, success_checker, planner_enabled)` | Decorador para registrar una acción. |
| `def get_action(name)` | Obtiene información de una acción por nombre. |
| `def get_available_actions(action_type)` | Obtiene acciones disponibles en formato para el LLM. |
| `def get_actions_for_planner()` | Genera metadatos serializables de las acciones para el planificador. |
| `def get_plannable_actions()` | Obtiene las acciones habilitadas para la capa de planificación. |
| `def get_actions_by_category(category)` | Obtiene todas las acciones de una categoría. |
| `def list_all_actions()` | Lista todas las acciones organizadas por tipo. |
| `def get_action_names_by_type(action_type)` | Obtiene nombres de acciones por tipo. |
| `def register_module(module_path)` | Registra todas las acciones decoradas de un módulo. |
| `def _store_action_info(action_info)` | Almacena una acción manteniendo sus índices internos. |
| `def get_action_suggestions(partial_name, limit)` | Obtiene sugerencias de acciones a partir de un nombre parcial. |
| `def _validate_value_type(value, expected_type)` | Valida de forma segura un tipo de parámetro. |
| `def validate_action(action_name, parameters)` | Valida si una acción y sus parámetros son válidos. |
| `def can_execute(action_name, parameters, state, check_preconditions)` | Comprueba si una acción puede ejecutarse según parámetros y estado. |
| `def get_action_cost(action_name)` | Obtiene el coste declarado de una acción. |
| `def execute_action(action_name, parameters)` | Ejecuta una acción registrada con parámetros nombrados. |
| `def execute_action_legacy(name)` | Ejecuta una acción por su nombre (compatibilidad legacy). |
| `def validate_parameters(name, parameters)` | Valida los nombres de parámetros definidos por la acción. |
| `def clear_actions()` | Limpia todas las acciones registradas. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _get_state_value(state, key, default)`  (L46) | Obtiene un valor de estado desde dicts u objetos con atributos/get. |
| `def _match_condition(state, condition)`  (L65) | Comprueba una única condición de estado. |
| `def _matches_conditions(state, conditions)`  (L106) | Comprueba un conjunto de condiciones de estado. |
| `def get_action_registry()`  (L966) | Obtiene la instancia global única del registro de acciones. |
| `def register_action(name, description, action_type, category, tags, parameters, confidence_threshold, preconditions, effects, cost, dependencies, capability, application, required_resources, requires_ui_element, success_checker, planner_enabled)`  (L981) | Atajo para registrar una acción usando la instancia global. |
| `def register_action_legacy(name, description, action_type, parameters, confidence_threshold)`  (L1030) | Atajo para registrar una acción usando la instancia global. |
| `def get_available_actions(action_type)`  (L1055) | Atajo para obtener las acciones disponibles desde el registro global. |
| `def get_action(name)`  (L1065) | Atajo para obtener una acción desde el registro global. |

## 🛠️ `src/utils/`

<!-- src/utils -->

<a name="src-utils-__init__-py"></a>
### `src/utils/__init__.py` [333 líneas] — Utils Package v2.7.0 - Sistema de optimización y automejora

**Descripción:** Utils Package v2.7.0 - Sistema de optimización y automejora

**Importaciones:** 14.

`class OptimizationSystem`  (línea 60) — Sistema completo de optimización y automejora

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path)` | Inicializar el sistema de optimización completo |
| `def get_system_status()` | Obtener estado completo del sistema de optimización |
| `def _calculate_system_health()` | Calcular salud general del sistema |
| `def optimize_system(strategy, level)` | Optimizar el sistema manualmente |
| `def start_auto_optimization()` | Iniciar optimización automática |
| `def stop_auto_optimization()` | Detener optimización automática |
| `def export_system_report(filepath)` | Exportar reporte completo del sistema |
| `def get_optimization_recommendations()` | Obtener recomendaciones de optimización del sistema |
| `def emergency_optimization()` | Optimización de emergencia para situaciones críticas |
| `def __del__()` | Destructor |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_system_status()`  (L306) | Obtener estado del sistema de optimización |
| `def optimize_system(strategy, level)`  (L310) | Optimizar el sistema |
| `def start_auto_optimization()`  (L314) | Iniciar optimización automática |
| `def stop_auto_optimization()`  (L318) | Detener optimización automática |
| `def get_optimization_recommendations()`  (L322) | Obtener recomendaciones de optimización |
| `def emergency_optimization()`  (L326) | Optimización de emergencia |

<a name="src-utils-adaptive_learning_engine-py"></a>
### `src/utils/adaptive_learning_engine.py` [1269 líneas] — Adaptive Learning Engine v2.7.0

**Descripción:** Adaptive Learning Engine v2.7.0

**Importaciones:** 32.

`class LearningTask(Enum)`  (línea 39) — Tareas de aprendizaje

_Sin métodos definidos en el AST._

`class NeuralArchitecture(Enum)`  (línea 50) — Arquitecturas neuronales

_Sin métodos definidos en el AST._

`class LearningTaskConfig`  (línea 61) — Configuración de tarea de aprendizaje

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ModelPerformance`  (línea 83) — Rendimiento del modelo

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class AdaptiveLearningEngine`  (línea 100) — Motor de aprendizaje adaptativo con deep learning y optimización de hiperparámetros

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path)` |  |
| `def _load_config(config_path)` | Cargar configuración del motor de aprendizaje |
| `def _initialize_model_registry()` | Inicializar registro de modelos |
| `def _load_trained_models()` | Cargar modelos pre-entrenados |
| `def _save_trained_models()` | Guardar modelos entrenados |
| `def _start_learning_engine()` | Iniciar motor de aprendizaje |
| `def _learning_engine_loop()` | Bucle principal del motor de aprendizaje |
| `def _process_learning_queue()` | Procesar cola de tareas de aprendizaje |
| `def _execute_learning_task(task_config)` | Ejecutar tarea de aprendizaje |
| `def _optimize_hyperparameters_task(task_config)` | Optimizar hiperparámetros de un modelo |
| `def _train_model_task(task_config)` | Entrenar un modelo |
| `def _select_features_task(task_config)` | Seleccionar características para un modelo |
| `def _search_architecture_task(task_config)` | Buscar arquitectura neural óptima |
| `def _online_learning_task(task_config)` | Aprendizaje online incremental |
| `def _batch_learning_task(task_config)` | Aprendizaje por lotes |
| `def _prepare_training_data(task_config)` | Preparar datos para entrenamiento |
| `def _create_neural_model(architecture_name, config)` | Crear modelo neural según arquitectura |
| `def _create_mlp_model(config)` | Crear modelo MLP |
| `def _create_lstm_model(config)` | Crear modelo LSTM |
| `def _train_neural_model(model, train_dataset, test_dataset, task_config)` | Entrenar modelo neural |
| `def _evaluate_model(model, X, y, task_config)` | Evaluar rendimiento de un modelo |
| `def _auto_detect_learning_opportunities()` | Detectar automáticamente oportunidades de aprendizaje |
| `def _optimize_hyperparameters()` | Optimizar hiperparámetros automáticamente |
| `def _evaluate_model_performance()` | Evaluar rendimiento de todos los modelos |
| `def _get_last_model_performance(model_name)` | Obtener último rendimiento de un modelo |
| `def _safe_float(value, default)` | Convertir un valor a float de forma segura. |
| `def _capture_feedback(feedback_data)` | Capturar y analizar el feedback de una adaptación de Goal. |
| `def _execute_learning_loop(feedback_result)` | Ejecutar el bucle de aprendizaje continuo sobre un feedback capturado. |
| `def _analyze_goal_learning_patterns(patterns, metrics)` | Normalizar los patrones detectados a partir del análisis de feedback. |
| `def _describe_goal_learning_pattern(pattern)` | Descripción legible de un patrón de aprendizaje. |
| `def _update_goal_adaptation_strategies(learned_patterns, current_strategies)` | Actualizar las estrategias aprendidas a partir de los patrones de éxito. |
| `def _calculate_goal_learning_convergence(metrics, improvement)` | Calcular las métricas de convergencia del aprendizaje. |
| `def get_learning_engine_status()` | Obtener estado del motor de aprendizaje |
| `def _get_best_model()` | Obtener mejor modelo |
| `def _get_average_performance()` | Obtener rendimiento promedio |
| `def add_learning_task(task_config)` | Añadir tarea de aprendizaje |
| `def get_model_info(model_name)` | Obtener información de un modelo |
| `def export_learning_report(filepath)` | Exportar reporte de aprendizaje |
| `def stop_learning_engine()` | Detener motor de aprendizaje |
| `def start_learning_engine()` | Iniciar motor de aprendizaje |
| `def __del__()` | Destructor |

<a name="src-utils-advanced_logger-py"></a>
### `src/utils/advanced_logger.py` [1577 líneas] — Sistema avanzado de logging y análisis de patrones para Jarvis.

**Descripción:** Sistema avanzado de logging y análisis de patrones para Jarvis.

**Importaciones:** 23.

`class LogLevel(Enum)`  (línea 28) — Niveles de log extendidos.

_Sin métodos definidos en el AST._

`class LogCategory(Enum)`  (línea 39) — Categorías de logs para análisis.

_Sin métodos definidos en el AST._

`class PatternType(Enum)`  (línea 51) — Tipos de patrones detectables.

_Sin métodos definidos en el AST._

`class LogEntry`  (línea 62) — Estructura de entrada de log enriquecida.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario para almacenamiento. |
| `def from_dict(cls, data)` | Crear desde diccionario. |

`class LogAnalyzer`  (línea 95) — Analizador de logs avanzado con machine learning y detección de patrones complejos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(window_size, pattern_threshold, ml_enabled, anomaly_detection)` |  |
| `def _initialize_ml_models()` | Inicializar modelos de machine learning para análisis avanzado. |
| `def analyze_log_entry(entry)` | Analizar una entrada de log y detectar patrones con ML. |
| `def _collect_performance_metrics(entry)` | Recopilar métricas de rendimiento. |
| `def _detect_patterns()` | Detectar patrones básicos en los logs. |
| `def _detect_patterns_with_ml()` | Detectar patrones con machine learning y análisis avanzado. |
| `def _detect_error_spike()` | Detectar picos de errores. |
| `def _detect_performance_degradation()` | Detectar degradación de rendimiento. |
| `def _detect_anomaly()` | Detectar anomalías básicas en los logs. |
| `def _detect_error_spike_ml()` | Detectar picos de errores con ML. |
| `def _detect_performance_degradation_ml()` | Detectar degradación de rendimiento con ML. |
| `def _detect_anomaly_ml()` | Detectar anomalías con ML. |
| `def _detect_sequential_patterns()` | Detectar patrones secuenciales. |
| `def _detect_correlations()` | Detectar correlaciones entre diferentes tipos de logs. |
| `def _detect_advanced_anomalies()` | Detección avanzada de anomalías. |
| `def _detect_frequency_anomaly()` | Detectar anomalías de frecuencia. |
| `def _detect_context_anomaly()` | Detectar anomalías de contexto. |
| `def get_statistics()` | Obtener estadísticas del analizador. |

`class AdvancedLogger`  (línea 568) — Logger avanzado con capacidades de análisis y patrón detection.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, level, log_dir, db_path, ml_enabled, anomaly_detection)` |  |
| `def _setup_logging_infrastructure()` | Configurar infraestructura de logging. |
| `def _create_database()` | Crear base de datos para logs. |
| `def _setup_handlers()` | Configurar handlers del logger. |
| `def _log_worker()` | Worker asíncrono para procesamiento de logs. |
| `def _store_log_entry(entry)` | Almacenar entrada de log en base de datos. |
| `def _store_pattern(pattern)` | Almacenar patrón detectado. |
| `def _generate_alerts(patterns, entry)` | Generar alertas basadas en patrones detectados. |
| `def log(_level, category, message)` | Método principal de logging - soporta ambas interfaces: |
| `def log_simple(message, level, category)` | Interfaz simple de logging compatible con código existente. |
| `def _format_message(message, args)` | Aplicar formato estilo printf a un mensaje de log (compatibilidad con logging estándar). |
| `def debug(message)` | Log de nivel DEBUG. |
| `def info(message)` | Log de nivel INFO. |
| `def warning(message)` | Log de nivel WARNING. |
| `def error(message)` | Log de nivel ERROR. |
| `def exception(message)` | Log de nivel ERROR incluyendo la excepción activa. |
| `def critical(message)` | Log de nivel CRITICAL. |
| `def success(message)` | Log de nivel SUCCESS. |
| `def performance(message)` | Log de nivel PERFORMANCE. |
| `def log_with_trace(message, category, trace_id)` | Log con trace ID para seguimiento distribuido. |
| `def log_with_span(message, category, span_id, parent_span_id)` | Log con span ID para microservicios. |
| `def query_logs(start_time, end_time, level, category, module, limit)` | Consultar logs desde la base de datos. |
| `def get_patterns(acknowledged, limit)` | Obtener patrones detectados. |
| `def acknowledge_pattern(pattern_id)` | Marcar patrón como reconocido. |
| `def get_statistics()` | Obtener estadísticas del sistema de logging. |
| `def export_logs(start_time, end_time, format)` | Exportar logs en formato especificado. |
| `def shutdown()` | Detener el logger de forma graceful. |
| `def add_custom_filter(filter_name, filter_func)` | Añadir filtro personalizado. |
| `def add_custom_formatter(formatter_name, formatter)` | Añadir formateador personalizado. |
| `def add_custom_handler(handler)` | Añadir handler personalizado. |
| `def log_with_metrics(level, category, message, metrics)` | Log con métricas asociadas. |
| `def log_with_context(level, category, message, context)` | Log con contexto enriquecido. |
| `def log_batch(entries)` | Logear múltiples entradas de forma eficiente. |
| `def search_logs(query, start_time, end_time, limit)` | Buscar logs usando consulta de texto completo. |
| `def get_real_time_metrics()` | Obtener métricas en tiempo real. |
| `def set_alert_threshold(pattern_type, threshold)` | Establecer umbral de alerta para un tipo de patrón. |
| `def get_alerts(active_only)` | Obtener alertas activas. |
| `def acknowledge_alert(alert_id)` | Marcar alerta como reconocida. |
| `def export_analytics(start_time, end_time, format)` | Exportar análisis avanzado de logs. |
| `def _get_top_errors(logs)` | Obtener errores más frecuentes. |
| `def _analyze_performance_logs(logs)` | Analizar logs de rendimiento. |
| `def log_context(context)` | Context manager para logging con contexto temporal. |
| `def log_with_trace_context(message, trace_data)` | Log con contexto de trazado distribuido. |

`class JsonFormatter(logging.Formatter)`  (línea 1354) — Formateador JSON mejorado.

Métodos:

| Firma | Docstring |
|---|---|
| `def format(record)` | Formatear log record como JSON. |

`class StatisticalAnomalyDetector`  (línea 1393) — Detector de anomalías usando métodos estadísticos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(window_size, threshold)` |  |
| `def add_data_point(metric_name, value)` | Añadir punto de datos y detectar anomalía. |

`class PatternRecognizer`  (línea 1435) — Reconocedor de patrones usando métodos de secuencia.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(min_pattern_length, max_pattern_length)` |  |
| `def add_log_sequence(category, level, module)` | Añadir secuencia de logs y detectar patrones. |
| `def _detect_repetitive_pattern(sequence_key)` | Detectar patrones repetitivos en secuencias. |

`class AdvancedLogMetrics`  (línea 1489) — Métricas avanzadas de logging y análisis de rendimiento.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def add_metric(name, value, tags)` | Añadir métrica con análisis de tendencias. |
| `def get_trend_analysis(metric_name, window_size)` | Análisis de tendencias para una métrica. |
| `def _calculate_volatility(values)` | Calcular volatilidad de una serie de valores. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_advanced_logger(name, level, log_dir, db_path)`  (L1387) | Obtener un logger avanzado. |

<a name="src-utils-alert_system-py"></a>
### `src/utils/alert_system.py` [620 líneas] — Sistema de alertas integrado para JARVIS.

**Descripción:** Sistema de alertas integrado para JARVIS.

**Importaciones:** 13.

`class AlertSeverity(Enum)`  (línea 22) — Severidad de las alertas.

_Sin métodos definidos en el AST._

`class AlertStatus(Enum)`  (línea 30) — Estado de las alertas.

_Sin métodos definidos en el AST._

`class AlertRule`  (línea 39) — Regla de alerta configurada.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte la regla a un diccionario. |

`class AlertAction`  (línea 62) — Acción a realizar ante una alerta.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte la acción a un diccionario. |

`class Alert`  (línea 79) — Alerta generada por el sistema.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte la alerta a un diccionario. |

`class AlertSystem`  (línea 113) — Sistema de alertas integrado para JARVIS.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` | Inicializa el sistema de alertas. |
| `def _create_default_rules()` | Crea reglas de alerta por defecto. |
| `def _create_default_actions()` | Crea acciones de alerta por defecto. |
| `def start_monitoring()` | Inicia el monitoreo de alertas. |
| `def stop_monitoring()` | Detiene el monitoreo de alertas. |
| `def _monitoring_loop()` | Bucle principal de monitoreo de alertas. |
| `def _evaluate_alert_rules()` | Evalúa todas las reglas de alerta activas. |
| `def _evaluate_condition(condition)` | Evalúa una condición de alerta (simplificado). |
| `def _process_alert(alert, rule)` | Procesa una alerta y ejecuta acciones. |
| `def _get_action(action_name)` | Obtiene una acción por nombre. |
| `def _execute_action(action, alert)` | Ejecuta una acción de alerta. |
| `def _execute_log_action(action, alert)` | Ejecuta acción de logging. |
| `def _execute_email_action(action, alert)` | Ejecuta acción de email. |
| `def _execute_webhook_action(action, alert)` | Ejecuta acción de webhook. |
| `def _execute_command_action(action, alert)` | Ejecuta acción de comando. |
| `def _cleanup_old_alerts()` | Limpia alertas antiguas resueltas. |
| `def acknowledge_alert(alert_id, acknowledged_by)` | Acepta una alerta. |
| `def resolve_alert(alert_id, resolved_by)` | Resuelve una alerta. |
| `def get_alerts(severity, status, source, limit)` | Obtiene alertas filtradas. |
| `def get_alert_statistics()` | Obtiene estadísticas de alertas. |
| `def add_alert_callback(callback)` | Agrega un callback para recibir alertas. |
| `def add_acknowledgement_callback(callback)` | Agrega un callback para recibir aceptaciones de alertas. |
| `def add_resolution_callback(callback)` | Agrega un callback para recibir resoluciones de alertas. |
| `def add_alert_rule(rule)` | Agrega una regla de alerta. |
| `def add_alert_action(action)` | Agrega una acción de alerta. |
| `def export_alerts(filepath, severity, status, source)` | Exporta alertas a un archivo JSON. |
| `def clear_resolved_alerts()` | Limpia alertas resueltas. |
| `def __enter__()` | Context manager entry. |
| `def __exit__(exc_type, exc_val, exc_tb)` | Context manager exit. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_alert_system()`  (L603) | Obtiene la instancia global del sistema de alertas. |
| `def start_alert_monitoring()`  (L611) | Inicia el monitoreo de alertas global. |
| `def stop_alert_monitoring()`  (L617) | Detiene el monitoreo de alertas global. |

<a name="src-utils-app_utils-py"></a>
### `src/utils/app_utils.py` [1030 líneas] — Utilidades comunes para aplicaciones y automatización.

**Descripción:** Utilidades comunes para aplicaciones y automatización.

**Importaciones:** 12.

`class AppManager`  (línea 54) — Gestor general de aplicaciones.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def open_app(app_name, screen_num)` | Abre una aplicación y, cuando es posible, la coloca en el monitor |
| `def close_app(app_name)` | Cierra una ventana encontrada para la aplicación. |
| `def move_window_to_screen(window_title, screen_num)` | Mueve una ventana a un monitor concreto mediante ScreenManager. |
| `def center_window(window_title)` | Centra una ventana en el monitor donde está situada actualmente. |
| `def verify_app_open(app_name)` | Comprueba si existe una ventana visible asociada a la aplicación. |
| `def _find_monitor_for_window(window)` | Determina el monitor en el que se encuentra el centro de una ventana. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_app_manager()`  (L460) | Obtiene una instancia del gestor de aplicaciones. |
| `def analyze_elements_in_screenshot(screenshot_path, app_name)`  (L477) | Analiza una captura mediante Vision/Qwen3-VL. |
| `def _extract_json(response)`  (L717) | Extrae JSON incluso si Vision devuelve un bloque Markdown. |
| `def _normalize_bbox(bbox)`  (L812) | Valida bbox normalizada 0..1000. |
| `def _safe_confidence(value)`  (L858) | Normaliza confidence a 0..1. |
| `def _find_application_windows(app_name)`  (L892) | Busca ventanas mediante varios nombres/patrones comunes. |
| `def open_app_on_screen(app_name, screen_num)`  (L977) | Abre una aplicación en un monitor. |
| `def close_app(app_name)`  (L993) | Cierra una aplicación. |
| `def move_window_to_screen(window_title, screen_num)`  (L1005) | Mueve una ventana a un monitor. |
| `def center_window(window_title)`  (L1021) | Centra una ventana dentro de su monitor actual. |

<a name="src-utils-architectural_evolution_manager-py"></a>
### `src/utils/architectural_evolution_manager.py` [10766 líneas] — ArchitecturalEvolutionManager v2.8.0

**Descripción:** ArchitecturalEvolutionManager v2.8.0

**Importaciones:** 29.

`class EvolutionStatus(Enum)`  (línea 32) — Estados posibles de una propuesta de evolución

_Sin métodos definidos en el AST._

`class ChangeType(Enum)`  (línea 44) — Tipos de cambios arquitectónicos permitidos

_Sin métodos definidos en el AST._

`class RiskLevel(Enum)`  (línea 57) — Niveles de riesgo asociados a cambios arquitectónicos

_Sin métodos definidos en el AST._

`class ComponentInfo`  (línea 65) — Información sobre un componente de la arquitectura

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class InterfaceInfo`  (línea 81) — Información sobre interfaces entre componentes

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class ArchitecturalChange`  (línea 97) — Representación de un cambio arquitectónico

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class EvolutionProposal`  (línea 123) — Propuesta de evolución arquitectónica

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

`class ArchitecturalEvolutionManager`  (línea 151) — Gestor de evolución de arquitectura interna que permite modificar

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config, logger, performance_optimizer, self_improvement_system, adaptive_learning_engine, pattern_analyzer)` | Inicializa el gestor de evolución arquitectónica. |
| `def get_component_info(component_name)` | Obtiene información detallada de un componente específico. |
| `def list_components(component_type)` | Lista todos los componentes del sistema, filtrados por tipo opcional. |
| `def get_component_dependencies(component_name)` | Obtiene las dependencias de un componente específico. |
| `def get_component_interfaces(component_name)` | Obtiene las interfaces de un componente específico. |
| `def get_available_operations()` | Obtiene las operaciones de modificación arquitectónica soportadas. |
| `def validate_component_existence(component_name)` | Verifica si un componente existe en la arquitectura actual. |
| `def get_architecture_state()` | Obtiene el estado actual de la arquitectura del sistema. |
| `def _count_components_by_type()` | Cuenta componentes por tipo. |
| `def get_proposal_input_requirements()` | Define la entrada mínima requerida para una propuesta de evolución. |
| `def get_proposal_output_requirements()` | Define la salida mínima esperada de una propuesta de evolución. |
| `def get_proposal_states()` | Define los estados posibles de una propuesta de evolución. |
| `def validate_proposal_contract(proposal_data)` | Valida que una propuesta cumple con el contrato mínimo. |
| `def register_component(component)` | Registra un nuevo componente en la arquitectura. |
| `def update_component_status(component_name, status)` | Actualiza el estado de un componente. |
| `def get_interface_info(interface_name)` | Obtiene información detallada de una interfaz específica. |
| `def register_interface(interface)` | Registra una nueva interfaz en la arquitectura. |
| `def get_architecture_inspection_report()` | Genera un reporte completo de inspección de la arquitectura actual. |
| `def _count_components_by_status()` | Cuenta componentes por estado. |
| `def _count_interfaces_by_status()` | Cuenta interfaces por estado. |
| `def _count_proposals_by_status()` | Cuenta propuestas por estado. |
| `def _count_changes_by_type()` | Cambia históricos por tipo. |
| `def _get_recently_modified_components()` | Obtiene componentes modificados recientemente. |
| `def _get_top_dependencies()` | Obtiene los componentes con más dependencias. |
| `def _get_most_used_interfaces()` | Obtiene las interfaces más utilizadas. |
| `def _get_recent_proposals()` | Obtiene propuestas recientes. |
| `def validate_compatibility_with_existing_apis(proposal)` | Verifica la compatibilidad de una propuesta con APIs existentes. |
| `def get_minimum_proposal_input()` | Define la entrada mínima requerida para una propuesta (2.8.2.1.6). |
| `def get_minimum_proposal_output()` | Define la salida mínima esperada de una propuesta (2.8.2.1.7). |
| `def get_proposal_states()` | Define los estados posibles de una propuesta (2.8.2.1.8). |
| `def run_minimum_tests()` | Ejecuta tests mínimos del contrato (2.8.2.1.10). |
| `def test_application_methods()` | Tests de la aplicación controlada (2.8.2.5.7). |
| `def prepare_change(change)` | Prepara el cambio antes de su aplicación (2.8.2.5.1). |
| `def apply_change(change)` | Aplica un único cambio verificable (2.8.2.5.2). |
| `def detect_application_failure(change, execution_result)` | Detecta fallo durante la aplicación del cambio (2.8.2.5.3). |
| `def register_application_result(change, execution_result)` | Registra el resultado de la aplicación del cambio (2.8.2.5.4). |
| `def verify_change_structure(change)` | Verifica la estructura resultante después de aplicar el cambio (2.8.2.5.5). |
| `def verify_no_side_effects(change)` | Verifica que no se modificaron componentes ajenos al cambio (2.8.2.5.6). |
| `def test_application_methods()` | Tests de la aplicación controlada (2.8.2.5.7). |
| `def _verify_precondition(precondition)` | Verifica una precondición específica. |
| `def _prepare_change_resources(change)` | Prepara recursos necesarios para el cambio. |
| `def _execute_change_by_type(change)` | Ejecuta el cambio según su tipo específico. |
| `def _execute_component_addition(change)` | Ejecuta adición de componente. |
| `def _execute_component_modification(change)` | Ejecuta modificación de componente. |
| `def _execute_component_removal(change)` | Ejecuta remoción de componente. |
| `def _execute_interface_addition(change)` | Ejecuta adición de interfaz. |
| `def _execute_interface_modification(change)` | Ejecuta modificación de interfaz. |
| `def _execute_interface_removal(change)` | Ejecuta remoción de interfaz. |
| `def _execute_flow_modification(change)` | Ejecuta modificación de flujo. |
| `def _execute_configuration_change(change)` | Ejecuta cambio de configuración. |
| `def _execute_integration_addition(change)` | Ejecuta adición de integración. |
| `def _execute_integration_removal(change)` | Ejecuta remoción de integración. |
| `def _verify_effect(effect, execution_result)` | Verifica si un efecto específico se alcanzó. |
| `def _verify_component_structure(component, change)` | Verifica la estructura de un componente después del cambio. |
| `def _verify_architectural_consistency(change, execution_result)` | Verifica consistencia arquitectónica general. |
| `def _register_change_execution(change, result)` | Registra la ejecución de un cambio en el historial. |
| `def _notify_systems_of_change(change, result)` | Notifica sistemas relacionados sobre el cambio aplicado. |
| `def _has_configuration_permissions()` | Verifica si se tienen permisos para cambios de configuración. |
| `def _generate_rollback_plan(change)` | Genera un plan de rollback para un cambio de alto riesgo. |
| `def _get_system_state_before_change(change)` | Obtiene el estado del sistema antes del cambio. |
| `def _get_current_system_state()` | Obtiene el estado actual del sistema. |
| `def _detect_unexpected_changes(previous_state, current_state, change)` | Detecta cambios no esperados entre estados. |
| `def _component_changed_unexpectedly(previous_component, current_component)` | Verifica si un componente cambió inesperadamente. |
| `def _interface_changed_unexpectedly(previous_interface, current_interface)` | Verifica si una interfaz cambió inesperadamente. |
| `def _detect_circular_dependencies()` | Detecta dependencias circulares. |
| `def _verify_interface_consistency()` | Verifica consistencia de interfaces. |
| `def _verify_change_application(change)` | Verifica que el cambio se aplicó correctamente. |
| `def _verify_component_dependencies(component)` | Verifica dependencias de un componente. |
| `def _detect_circular_dependencies_for_component(component_name, visited, path)` | Detecta dependencias circulares para un componente específico. |
| `def _verify_component_interfaces(component)` | Verifica interfaces de un componente. |
| `def _verify_component_capabilities(component)` | Verifica capacidades de un componente. |
| `def _create_test_change()` | Crea un cambio de prueba para tests. |
| `def _create_invalid_test_change()` | Crea un cambio inválido para tests. |
| `def validate_component_dependencies(change)` | Verificar dependencias del componente (2.8.2.4.1). |
| `def validate_component_apis(change)` | Verificar APIs utilizadas por el componente (2.8.2.4.2). |
| `def validate_required_capabilities(change)` | Verificar que el cambio no elimina una capacidad requerida (2.8.2.4.3). |
| `def _are_capabilities_related(capability1, capability2)` | Verifica si dos capacidades están relacionadas (una depende de la otra). |
| `def validate_state_compatibility(change)` | Verificar compatibilidad con State (2.8.2.4.4). |
| `def _validate_state_precondition(precond)` | Valida una precondición de estado. |
| `def _validate_state_effect(effect)` | Valida un efecto de estado. |
| `def _validate_state_transition(transition)` | Valida una transición de estado. |
| `def validate_planner_executor_compatibility(change)` | Verificar compatibilidad con Planner/Executor cuando afecte al flujo (2.8.2.4.5). |
| `def _is_interface_executor_compatible(interface_info)` | Verifica si una interfaz es compatible con el Executor. |
| `def _is_interface_planner_compatible(interface_info)` | Verifica si una interfaz es compatible con el Planner. |
| `def _validate_planning_dependency(dependency)` | Valida una dependencia de planificación. |
| `def _validate_planner_configuration(config)` | Valida una configuración del Planner. |
| `def _validate_executor_configuration(config)` | Valida una configuración del Executor. |
| `def validate_known_interfaces(change)` | Verificar que el cambio no rompe interfaces conocidas (2.8.2.4.6). |
| `def _is_interface_in_known_contract(interface_name)` | Verifica si una interfaz es parte de un contrato conocido. |
| `def _is_interface_modification_backward_compatible(interface_name, change)` | Verifica si una modificación de interfaz es compatible hacia atrás. |
| `def validate_change_rejectability(change)` | Rechazar cambios que no puedan validarse (2.8.2.4.7). |
| `def _has_circular_dependencies(change)` | Verifica si un cambio tiene dependencias circulares. |
| `def _check_circular_dependencies_recursive(component_name, visited)` | Verifica recursivamente dependencias circulares. |
| `def _violates_security_constraints(change)` | Verifica si un cambio viola restricciones de seguridad. |
| `def validate_proposal_previa(proposal)` | Validación previa completa de una propuesta de evolución. |
| `def test_validation_previa_methods()` | Ejecuta tests de validación previa (2.8.2.4.8). |
| `def execute_syntax_check(change)` | Ejecuta comprobación sintáctica (2.8.2.6.1). |
| `def execute_component_tests(change)` | Ejecuta tests del componente afectado (2.8.2.6.2). |
| `def check_direct_integrations(change)` | Comprueba integraciones directas (2.8.2.6.3). |
| `def check_configuration_state(change)` | Comprueba estado de configuración (2.8.2.6.4). |
| `def check_application_startup(change)` | Comprueba que la aplicación sigue arrancando si el cambio lo requiere (2.8.2.6.5). |
| `def register_real_evidence(change, verification_results)` | Registra evidencia real (2.8.2.6.6). |
| `def test_post_verification_methods()` | Tests de verificación posterior (2.8.2.6.7). |
| `def _test_component_integrity(component)` | Verifica integridad básica de un componente. |
| `def _test_component_dependencies(component)` | Verifica dependencias de un componente. |
| `def _test_component_interfaces(component)` | Verifica interfaces de un componente. |
| `def _test_component_capabilities(component)` | Verifica capacidades de un componente. |
| `def _test_component_status(component)` | Verifica estado de un componente. |
| `def _test_component_modification_applied(change, component)` | Verifica que la modificación se aplicó correctamente. |
| `def _check_component_integrations(component)` | Verifica integraciones de un componente. |
| `def _check_component_interfaces_functionality(component)` | Verifica funcionalidad de interfaces de un componente. |
| `def _check_component_dependencies_satisfiable(component)` | Verifica que las dependencias del componente son satisfacibles. |
| `def _check_flows_functionality_after_change(change)` | Verifica funcionalidad de flujos después del cambio. |
| `def _check_system_configuration()` | Verifica configuración del sistema. |
| `def _check_new_configuration_valid(change)` | Verifica que la nueva configuración es válida. |
| `def _check_affected_components_configuration(change)` | Verifica configuración de componentes afectados. |
| `def _check_interfaces_configuration(change)` | Verifica configuración de interfaces. |
| `def _check_configuration_conflicts(change)` | Verifica conflictos de configuración. |
| `def _determines_if_change_requires_startup_check(change)` | Determina si el cambio requiere verificación de arrancabilidad. |
| `def _simulate_application_startup_check(change)` | Simula verificación de arrancabilidad de la aplicación. |
| `def _check_critical_components_functionality(change)` | Verifica funcionalidad de componentes críticos. |
| `def _check_essential_services_availability(change)` | Verifica disponibilidad de servicios esenciales. |
| `def _get_current_system_state()` | Obtiene estado actual del sistema. |
| `def _get_components_status_summary()` | Obtiene resumen de estado de componentes. |
| `def _get_interfaces_status_summary()` | Obtiene resumen de estado de interfaces. |
| `def _get_configuration_status_summary()` | Obtiene resumen de estado de configuración. |
| `def _get_current_performance_metrics()` | Obtiene métricas de rendimiento actuales. |
| `def _notify_systems_of_verification_results(change, results)` | Notifica sistemas de resultados de verificación. |
| `def _has_circular_dependency(component_name, visited)` | Verifica si hay dependencias circulares. |
| `def _verify_effect_applied(effect, component)` | Verifica si un efecto se aplicó correctamente. |
| `def _create_test_change()` | Crea un cambio de prueba. |
| `def _has_configuration_permissions()` | Verifica permisos de configuración. |
| `def process_adaptation_need(adaptation_need)` | Procesa una necesidad de adaptación y la convierte en una propuesta (2.8.2.3.1). |
| `def validate_adaptation_need(adaptation_need)` | Valida que una necesidad de adaptación tenga el formato correcto. |
| `def create_concrete_proposal(adaptation_need)` | Traduce una necesidad de adaptación a una propuesta concreta (2.8.2.3.2). |
| `def _generate_expected_benefits(adaptation_need)` | Genera beneficios esperados basados en el tipo de necesidad. |
| `def _generate_potential_risks(adaptation_need)` | Genera riesgos potenciales basados en el tipo de necesidad. |
| `def validate_change_in_proposal_scope(change, proposal)` | Valida que un cambio esté dentro del scope de la propuesta (2.8.2.3.3). |
| `def is_change_type_compatible_with_proposal(change_type, proposal)` | Verifica si un tipo de cambio es compatible con una propuesta. |
| `def is_change_type_supported(change_type)` | Verifica si un tipo de cambio es soportado por el sistema (2.8.2.3.5). |
| `def validate_change_type(change_type_str)` | Valida y convierte un string a tipo de cambio soportado. |
| `def validate_change_in_proposal_scope_method(change, proposal)` | Método público para validar que un cambio está dentro del scope de la propuesta. |
| `def get_current_change_representation()` | Identifica cómo se representa actualmente un cambio de arquitectura (2.8.2.2.1). |
| `def create_minimal_change_representation(change_type, component_affected, description, rationale)` | Representa un cambio mínimo sin aplicarlo (2.8.2.2.2). |
| `def associate_change_with_component(change)` | Asocia el cambio con su componente afectado (2.8.2.2.3). |
| `def associate_context_with_change(change, context)` | Asocia motivo/contexto solo si existe soporte real (2.8.2.2.4). |
| `def associate_constraints_with_change(change, constraints)` | Asocia restricciones existentes al cambio (2.8.2.2.5). |
| `def associate_risk_with_change(change, risk_level, risk_details)` | Asocia riesgo solo si existe modelo real para expresarlo (2.8.2.2.6). |
| `def associate_reversibility_with_change(change, is_reversible, rollback_plan)` | Asocia reversibilidad si existe soporte (2.8.2.2.7). |
| `def verify_change_serialization(change)` | Verifica serialización del cambio arquitectónico (2.8.2.2.8). |
| `def serialize_change_to_json(change)` | Serializa un cambio arquitectónico a formato JSON. |
| `def deserialize_change_from_json(json_str)` | Deserializa un cambio arquitectónico desde formato JSON. |
| `def test_change_representation_methods()` | Ejecuta tests de representación de cambios (2.8.2.2.9). |
| `def detect_when_rollback_is_needed(change, execution_result)` | Detecta cuándo un cambio debe revertirse (2.8.2.7.1). |
| `def recover_previous_version(change)` | Recupera la versión previa de un componente o sistema (2.8.2.7.2). |
| `def avoid_partial_rollback(change)` | Evita rollback parcial asegurando que todas las operaciones se reviertan completamente (2.8.2.7.3). |
| `def verify_state_after_rollback(change)` | Verifica el estado del sistema después del rollback (2.8.2.7.4). |
| `def register_rollback_reason(change, reason, details)` | Registra el motivo del rollback (2.8.2.7.5). |
| `def test_rollback_methods()` | Ejecuta tests de rollback (2.8.2.7.6). |
| `def _rollback_component_addition(change)` | Revierte la adición de un componente. |
| `def _rollback_component_removal(change)` | Revierte la remoción de un componente. |
| `def _rollback_component_modification(change)` | Revierte la modificación de un componente. |
| `def _rollback_interface_addition(change)` | Revierte la adición de una interfaz. |
| `def _rollback_interface_removal(change)` | Revierte la remoción de una interfaz. |
| `def _rollback_interface_modification(change)` | Revierte la modificación de una interfaz. |
| `def _rollback_flow_modification(change)` | Revierte la modificación de flujo. |
| `def _rollback_configuration_change(change)` | Revierte el cambio de configuración. |
| `def _rollback_integration_addition(change)` | Revierte la adición de integración. |
| `def _rollback_integration_removal(change)` | Revierte la remoción de integración. |
| `def _get_operations_from_change(change)` | Obtiene las operaciones realizadas por un cambio. |
| `def _has_rollback_counterpart(operation)` | Verifica si una operación tiene contraparte de rollback. |
| `def _check_intermediate_state_consistency(change)` | Verifica consistencia del estado intermedio. |
| `def _check_dependencies_reversibility(change)` | Verifica reversibilidad de dependencias. |
| `def _verify_system_integrity_after_rollback(change)` | Verifica integridad del sistema después de rollback. |
| `def _verify_components_consistency_after_rollback(change)` | Verifica consistencia de componentes después de rollback. |
| `def _verify_interfaces_consistency_after_rollback(change)` | Verifica consistencia de interfaces después de rollback. |
| `def _verify_configuration_consistency_after_rollback(change)` | Verifica consistencia de configuración después de rollback. |
| `def _verify_performance_restored(change)` | Verifica si el rendimiento se restauró después de rollback. |
| `def _verify_critical_services_available(change)` | Verifica disponibilidad de servicios críticos después de rollback. |
| `def _verify_data_integrity_after_rollback(change)` | Verifica integridad de datos después de rollback. |
| `def _verify_original_state_restored(change)` | Verifica si el estado original se restauró completamente. |
| `def _register_rollback_in_history(change)` | Registra rollback en el historial de cambios. |
| `def _notify_rollback_to_systems(change, reason, details)` | Notifica sistemas sobre el rollback. |
| `def _create_test_change_for_rollback()` | Crea un cambio de prueba para tests de rollback. |
| `def execute_syntax_check(change)` | Ejecuta comprobación sintáctica del cambio aplicado (2.8.2.6.1). |
| `def execute_component_tests(change)` | Ejecuta tests del componente afectado (2.8.2.6.2). |
| `def check_direct_integrations(change)` | Comprobar integraciones directas (2.8.2.6.3). |
| `def check_configuration_state(change)` | Comprobar estado de configuración (2.8.2.6.4). |
| `def check_application_startup(change)` | Comprobar que la aplicación sigue arrancando si el cambio lo requiere (2.8.2.6.5). |
| `def register_verification_evidence(change, verification_results)` | Registrar evidencia real de verificación (2.8.2.6.6). |
| `def test_post_verification_methods()` | Tests de verificación posterior (2.8.2.6.7). |
| `def _test_component_integrity(component)` | Verifica integridad de un componente. |
| `def _test_component_interfaces(component)` | Verifica interfaces de un componente. |
| `def _test_component_dependencies(component)` | Verifica dependencias de un componente. |
| `def _test_component_capabilities(component)` | Verifica capacidades de un componente. |
| `def _check_circular_dependencies(component_name, warnings)` | Verifica dependencias circulares. |
| `def _check_system_configuration()` | Verifica configuración del sistema. |
| `def _check_component_configuration(component_name)` | Verifica configuración de un componente específico. |
| `def _check_interfaces_configuration()` | Verifica configuración de interfaces. |
| `def _check_dependencies_configuration()` | Verifica configuración de dependencias. |
| `def _determine_if_change_affects_startup(change)` | Determina si un cambio afecta el arranque del sistema. |
| `def _get_startup_dependencies()` | Obtiene dependencias de arranque. |
| `def _has_circular_dependencies(dependencies)` | Verifica si hay dependencias circulares. |
| `def _notify_verification_results(change, evidence_entry)` | Notifica resultados de verificación a sistemas relacionados. |
| `def detect_rollback_need(change, execution_result)` | Detecta cuándo un cambio debe revertirse basado en el resultado de ejecución. |
| `def create_backup_for_rollback(change)` | Crea una copia de seguridad de los componentes afectados antes de aplicar un cambio. |
| `def perform_rollback(change, backup_data)` | Realiza el rollback de un cambio arquitectónico. |
| `def verify_rollback_success(change, rollback_result)` | Verifica que el rollback se realizó correctamente. |
| `def _check_dependencies_after_rollback(change, rollback_result)` | Verifica dependencias después de un rollback. |
| `def register_rollback_reason(change, reason, additional_info)` | Registra el motivo por el cual se realizó un rollback. |
| `def test_rollback_mechanism()` | Prueba el mecanismo de rollback con un cambio de prueba. |
| `def test_rollback_failure_scenarios()` | Prueba escenarios de fallo durante el rollback. |
| `def execute_syntax_check(component_name)` | Ejecuta comprobación sintáctica del componente afectado. |
| `def execute_component_tests(component_name)` | Ejecuta tests del componente afectado. |
| `def check_direct_integrations(component_name)` | Comprueba integraciones directas del componente afectado. |
| `def check_configuration_state()` | Comprueba estado de configuración del sistema. |
| `def check_application_startup(component_name)` | Comprueba que la aplicación sigue arrancando si el cambio lo requiere. |
| `def register_real_evidence(verification_id, evidence_data)` | Registra evidencia real de la verificación. |
| `def execute_post_verification_tests()` | Ejecuta tests de verificación posterior completos. |
| `def _get_component_files(component)` | Obtiene archivos asociados a un componente. |
| `def _find_component_test_files(component)` | Busca archivos de test para un componente. |
| `def _execute_test_file(test_file, component_name)` | Ejecuta un archivo de test individual. |
| `def _get_required_interfaces(component_name)` | Obtiene interfaces requeridas por un componente. |
| `def _check_external_integrations(component_name)` | Verifica integraciones con sistemas externos. |
| `def _get_config_files()` | Obtiene archivos de configuración. |
| `def _validate_config_file(config_file, config_data)` | Valida un archivo de configuración específico. |
| `def _validate_config_settings(config)` | Valida configuración en memoria. |
| `def _get_contextual_config()` | Obtiene configuración del sistema contextual. |
| `def _get_improvement_config()` | Obtiene configuración del sistema de automejora. |
| `def _requires_startup_verification(component_name)` | Determina si se requiere verificación de arranque. |
| `def _get_component_module_path(component)` | Obtiene la ruta del módulo de un componente. |
| `def _check_critical_errors()` | Verifica errores críticos que impiden el arranque. |
| `def _measure_startup_performance()` | Mide métricas de rendimiento durante el arranque. |
| `def _mark_verification_as_verified(verification_id)` | Marca una verificación como verificada. |
| `def _store_persistent_evidence(verification_id, evidence_data)` | Almacena evidencia de forma persistente. |
| `def _notify_evidence_registration(verification_id, evidence_record)` | Notifica sistemas conectados sobre el registro de evidencia. |
| `def _log_verification_event(event_type, result)` | Registra eventos de verificación. |
| `def connect_contextual_adaptation_engine(contextual_engine, integration_config)` | Conecta el ContextualAdaptationEngine con el ArchitecturalEvolutionManager. |
| `def connect_self_improvement_system(self_improvement_system, integration_config)` | Conecta el SelfImprovementSystem solo donde ya exista contrato. |
| `def reuse_existing_configuration(config_path)` | Reutiliza mecanismos existentes de configuración. |
| `def avoid_double_evolution_logic()` | Evita doble lógica de evolución entre sistemas conectados. |
| `def propagate_result(result, source_system, target_systems)` | Propaga resultados entre sistemas conectados. |
| `def run_integration_tests()` | Ejecuta tests de integración entre sistemas. |
| `def _sync_contextual_state()` | Sincroniza estado con ContextualAdaptationEngine. |
| `def _sync_improvement_rules()` | Sincroniza reglas de mejora con SelfImprovementSystem. |
| `def _coordinate_evolution_systems(systems)` | Coordina múltiples sistemas de evolución para evitar conflictos. |
| `def _propagate_to_contextual_engine(result, source_system)` | Propaga resultado a ContextualAdaptationEngine. |
| `def _propagate_to_self_improvement(result, source_system)` | Propaga resultado a SelfImprovementSystem. |
| `def _log_propagation_event(result, source, targets, success)` | Registra evento de propagación. |
| `def _test_contextual_engine_connection()` | Test de conexión con ContextualAdaptationEngine. |
| `def _test_self_improvement_connection()` | Test de conexión con SelfImprovementSystem. |
| `def _test_result_propagation()` | Test de propagación de resultados. |
| `def _test_configuration_reuse()` | Test de reutilización de configuración. |
| `def identify_persistence_locations()` | Identifica dónde se persisten reglas/cambios (2.8.2.9.1). |
| `def persist_evolution(evolution)` | Persiste una evolución válida (2.8.2.9.2). |
| `def recover_evolution(evolution_id)` | Recupera una evolución persistida (2.8.2.9.3). |
| `def handle_corrupted_or_missing_data(evolution_id)` | Maneja datos corruptos o ausentes (2.8.2.9.4). |
| `def prevent_duplicates(evolution)` | Evita duplicados en la persistencia (2.8.2.9.5). |
| `def maintain_change_traceability(change)` | Mantiene trazabilidad de cambios (2.8.2.9.6). |
| `def run_persistence_and_audit_tests()` | Ejecuta tests de persistencia y auditoría (2.8.2.9.7). |
| `def _get_directory_size_mb(directory_path)` | Obtiene el tamaño de un directorio en MB. |
| `def _validate_change_for_persistence(change)` | Valida un cambio para persistencia. |
| `def _validate_proposal_for_persistence(proposal)` | Valida una propuesta para persistencia. |
| `def _is_duplicate_evolution(evolution)` | Verifica si una evolución es duplicada. |
| `def _serialize_evolution_for_persistence(evolution)` | Serializa una evolución para persistencia. |
| `def _deserialize_evolution_from_persistence(evolution_data)` | Deserializa una evolución desde datos persistidos. |
| `def _update_evolution_index(evolution_id, evolution_file)` | Actualiza el índice de evoluciones. |
| `def _add_audit_record(audit_record)` | Agrega un registro al auditoría. |
| `def _validate_evolution_data_integrity(evolution_data)` | Valida la integridad de datos de evolución. |
| `def _attempt_recovery_from_backup(evolution_id)` | Intenta recuperar desde backup. |
| `def _check_data_corruption(file_path)` | Verifica si un archivo de datos está corrupto. |
| `def _attempt_data_repair(file_path)` | Intenta reparar datos corruptos. |
| `def _backup_corrupted_file(file_path)` | Crea backup de archivo corrupto. |
| `def _are_evolution_data_equivalent(data1, data2)` | Verifica si dos conjuntos de datos de evolución son equivalentes. |
| `def _is_evolution_update(old_data, new_data)` | Verifica si una evolución es una actualización válida. |
| `def _find_similar_evolutions(evolution)` | Encuentra evoluciones similares. |
| `def _calculate_evolution_similarity(evolution1, evolution2)` | Calcula similitud entre dos evoluciones. |
| `def _generate_trace_id()` | Genera un ID de trazabilidad único. |
| `def _categorize_change(change)` | Categoriza un cambio. |
| `def _update_traceability_index(change_id, trace_id)` | Actualiza el índice de trazabilidad. |
| `def _cleanup_test_evolution(evolution_id)` | Limpia datos de prueba de evolución. |
| `def _create_test_change()` | Crea un cambio de prueba. |
| `def run_unit_tests()` | Ejecuta tests unitarios del ArchitecturalEvolutionManager. |
| `def run_integration_tests()` | Ejecuta tests de integración con sistemas conectados. |
| `def verify_real_system_functionality()` | Realiza verificación real del sistema en ejecución. |
| `def update_documentation()` | Actualiza la documentación del sistema. |
| `def mark_completion()` | Marca la tarea 2.8.2.10 como completada y verifica que todas las hojas estén completas. |
| `def run_closure_tests()` | Ejecuta todos los tests de cierre de forma coordinada. |

<a name="src-utils-circuit_breaker-py"></a>
### `src/utils/circuit_breaker.py` [197 líneas] — Circuit Breaker Pattern Implementation

**Descripción:** Circuit Breaker Pattern Implementation

**Importaciones:** 8.

`class CircuitState(Enum)`  (línea 14) — Circuit breaker states

_Sin métodos definidos en el AST._

`class CircuitBreakerConfig`  (línea 21) — Configuration for circuit breaker

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class CircuitBreaker`  (línea 29) — Circuit breaker implementation

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, config)` |  |
| `def call(func)` | Execute function with circuit breaker protection |
| `def _should_attempt_reset()` | Check if circuit should attempt reset |
| `def _on_success()` | Handle successful call |
| `def _on_failure()` | Handle failed call |
| `def _open_circuit()` | Open the circuit breaker |
| `def _reset_circuit()` | Reset circuit breaker to closed state |
| `def force_open()` | Force circuit breaker to open state |
| `def force_close()` | Force circuit breaker to closed state |
| `def get_state()` | Get current circuit breaker state |
| `def get_stats()` | Get circuit breaker statistics |

`class CircuitBreakerOpenError(Exception)`  (línea 146) — Exception raised when circuit is open

_Sin métodos definidos en el AST._

`class CircuitBreakerManager`  (línea 150) — Manages multiple circuit breakers

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def get_breaker(name, config)` | Get or create circuit breaker |
| `def get_all_stats()` | Get statistics for all circuit breakers |
| `def reset_all()` | Reset all circuit breakers |
| `def cleanup_stale(max_age_hours)` | Clean up stale circuit breakers |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def circuit_breaker(name, config)`  (L189) | Decorator for circuit breaker protection |

<a name="src-utils-config-py"></a>
### `src/utils/config.py` [1348 líneas] — Módulo de sistema

**Descripción:** Módulo de sistema.

**Importaciones:** 8.

`class SystemConfig`  (línea 55) — Configuración general del sistema Jarvis.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class LoggingConfig`  (línea 65) — Configuración del sistema de logging.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class KeyboardConfig`  (línea 75) — Configuración de teclas de atajo.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class VoiceConfig`  (línea 83) — Configuración de voz.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class MemoryConfig`  (línea 95) — Configuración de memoria.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class PredictiveConfig`  (línea 104) — Configuración del sistema predictivo.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class MonitorConfig`  (línea 118) — Configuración compatible de un monitor.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def right()` | Coordenada X final del monitor. |
| `def bottom()` | Coordenada Y final del monitor. |

`class ScreenConfig`  (línea 158) — Configuración auxiliar de pantallas.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def monitor_count()` | Número de monitores configurados en el JSON. |
| `def get_monitor(monitor_id)` | Obtiene un monitor por ID. |
| `def get_primary_monitor()` | Obtiene el monitor marcado como principal. |

`class TimeoutConfig`  (línea 230) — Configuración de timeouts.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class CalibrationConfig`  (línea 240) — Configuración del sistema de calibración.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ChromeConfig`  (línea 263) — Configuración de Google Chrome para aperturas automáticas.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class Config`  (línea 284) — Configuración principal del sistema.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _voice_file_exists(voice_id, voice_styles_dir)`  (L315) | Comprueba si existe el archivo .bin de una voz. |
| `def load_saved_voice_preference()`  (L333) | Carga la última voz seleccionada por el usuario. |
| `def save_voice_preference(voice_id)`  (L371) | Guarda la voz actualmente seleccionada. |
| `def _load_monitor(monitor_data)`  (L420) | Convierte el bloque JSON de un monitor en MonitorConfig. |
| `def _load_default_monitors()`  (L547) | No inventa monitores. |
| `def load_config()`  (L562) | Carga la configuración desde config/config.json. |
| `def get_project_root()`  (L1220) | Retorna la ruta raíz del proyecto. |
| `def get_config_path()`  (L1225) | Retorna la ruta del archivo de configuración. |
| `def get_models_path()`  (L1235) | Retorna la ruta al directorio de modelos. |
| `def get_voices_path()`  (L1240) | Retorna la ruta al directorio de voces. |
| `def get_macros_coords_path()`  (L1245) | Retorna la ruta al archivo de coordenadas de macros. |
| `def get_voice_preference_path()`  (L1250) | Retorna la ruta de la preferencia persistente de voz. |
| `def get_system_config()`  (L1260) | Retorna la configuración general del sistema. |
| `def get_logging_config()`  (L1265) | Retorna la configuración de logging. |
| `def get_keyboard_config()`  (L1270) | Retorna la configuración del teclado. |
| `def get_voice_config()`  (L1275) | Retorna la configuración de voz. |
| `def get_memory_config()`  (L1280) | Retorna la configuración de memoria. |
| `def get_screen_config()`  (L1285) | Retorna la configuración auxiliar de pantallas. |
| `def get_timeout_config()`  (L1294) | Retorna la configuración de timeouts. |
| `def get_predictive_config()`  (L1299) | Retorna la configuración predictiva. |
| `def get_calibration_config()`  (L1304) | Retorna la configuración de calibración. |
| `def get_chrome_config()`  (L1309) | Retorna la configuración de Chrome. |
| `def get_element_types()`  (L1314) | Retorna los tipos de elementos configurados. |
| `def get_monitors()`  (L1324) | Retorna los monitores definidos en config.json. |
| `def get_monitor_config(monitor_id)`  (L1334) | Retorna un monitor concreto del JSON. |
| `def get_primary_monitor_config()`  (L1341) | Retorna el monitor principal definido en el JSON. |
| `def get_monitor_count()`  (L1346) | Retorna el número de monitores definidos en el JSON. |

<a name="src-utils-contextual_adaptation_audit-py"></a>
### `src/utils/contextual_adaptation_audit.py` [444 líneas] — Auditoría del Objetivo Real - Sistema de Autoevolución y Adaptación Contextual (Unidad 2.8.1)

**Descripción:** Auditoría del Objetivo Real - Sistema de Autoevolución y Adaptación Contextual (Unidad 2.8.1)

**Importaciones:** 8.

`class ComponentStatus`  (línea 16) — Estado de un componente del sistema

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class AuditFinding`  (línea 29) — Hallazgo de auditoría

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class SystemGap`  (línea 40) — Brecha en el sistema

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ContextualAdaptationAuditor`  (línea 49) — Auditoría del objetivo real para Sistema de Autoevolución y Adaptación Contextual

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def audit_existing_components()` | Auditar componentes existentes relacionados con adaptación y evolución |
| `def _audit_component(name, path, expected_functionality, expected_capabilities)` | Auditar un componente específico |
| `def _assess_functionality(content, expected)` | Evaluar funcionalidad implementada |
| `def _assess_capabilities(content, expected_capabilities)` | Evaluar capacidades implementadas |
| `def _assess_integration(content)` | Evaluar nivel de integración |
| `def _extract_dependencies(content)` | Extraer dependencias del componente |
| `def _identify_issues(content)` | Identificar posibles issues en el componente |
| `def _add_audit_finding(category, severity, component, description, evidence, recommendation, impact)` | Agregar hallazgo de auditoría |
| `def identify_system_gaps()` | Identificar brechas en el sistema de autoevolución contextual |
| `def _add_system_gap(area, missing_component, required_functionality, priority, estimated_effort, dependencies)` | Agregar brecha identificada |
| `def generate_audit_report()` | Generar reporte completo de auditoría |
| `def _generate_recommendations()` | Generar recomendaciones basadas en la auditoría |
| `def _generate_next_steps()` | Generar pasos siguientes para implementación |
| `def _is_fully_integrated()` | Verificar si el sistema está completamente integrado |
| `def save_audit_report(output_path)` | Guardar reporte de auditoría a archivo |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def main()`  (L414) | Ejecutar auditoría completa |

<a name="src-utils-contextual_adaptation_engine-py"></a>
### `src/utils/contextual_adaptation_engine.py` [4958 líneas] — Motor de adaptación contextual revisado de JARVIS.

**Descripción:** Motor de adaptación contextual revisado de JARVIS.

**Importaciones:** 38.

`class ContextType(Enum)`  (línea 107)

_Sin métodos definidos en el AST._

`class AdaptationLevel(Enum)`  (línea 119)

_Sin métodos definidos en el AST._

`class ContextualFactor(Enum)`  (línea 126)

_Sin métodos definidos en el AST._

`class ContextSnapshot`  (línea 140)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |

`class AdaptationRule`  (línea 165)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |

`class KnowledgeTransfer`  (línea 198)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |

`class TransferEvaluation(dict)`  (línea 220) — Evaluación de una transferencia.

Métodos:

| Firma | Docstring |
|---|---|
| `def __iter__()` |  |

`class AdaptationResult`  (línea 234)

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` |  |

`class _AdaptationHistoryEntry(dict)`  (línea 254) — Mantiene compatibilidad con el historial legado que se lee por atributo.

Métodos:

| Firma | Docstring |
|---|---|
| `def __getattr__(name)` |  |
| `def to_dict()` |  |

`class ContextualAdaptationEngine`  (línea 262) — Motor de adaptación contextual y transferencia de conocimiento de JARVIS.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path, data_dir)` |  |
| `def _load_config(config_path)` |  |
| `def _resolve_path(configured_path, default_name)` |  |
| `def _initialize_adaptation_rules()` |  |
| `def _initialize_knowledge_base()` |  |
| `def capture_context_snapshot()` |  |
| `def _collect_system_metrics()` |  |
| `def _collect_performance_metrics()` |  |
| `def _collect_user_patterns()` |  |
| `def _collect_environmental_conditions()` |  |
| `def _determine_context_type(system_metrics, performance_metrics, user_patterns)` |  |
| `def _evaluate_contextual_factors(system, performance, user, environment)` |  |
| `def _calculate_context_confidence(factors, system, performance)` |  |
| `def _record_context_pattern(snapshot)` |  |
| `def analyze_contextual_patterns(snapshot)` |  |
| `def _evaluate_rule_condition(rule, snapshot)` |  |
| `def _get_contextual_value(key, snapshot)` |  |
| `def _parse_value(value)` |  |
| `def execute_adaptation(snapshot, rules)` |  |
| `def _determine_adaptation_level(rules)` |  |
| `def _execute_adaptation_actions(rule, snapshot)` |  |
| `def _execute_single_action(action, snapshot)` |  |
| `def _set_optimization_interval(interval)` |  |
| `def _reduce_data_transfer_real()` |  |
| `def _update_rule_success_rate(rule, success)` |  |
| `def _calculate_overall_impact(data)` | Normalizar el signo de los impactos sin confundir aumentos buenos y malos. |
| `def _calculate_adaptation_confidence(rules, snapshot, impact)` |  |
| `def _record_adaptation_result(adaptation_id, snapshot, rules, confidence)` |  |
| `def transfer_knowledge(source_context, target_context, knowledge_type, transfer_strategy, include_patterns, include_strategies, include_baselines, include_metrics)` |  |
| `def _extract_knowledge_from_context(context, knowledge_type)` |  |
| `def _extract_contextual_metrics(context)` |  |
| `def _extract_relevant_metrics(context)` |  |
| `def _validate_context_compatibility(source_context, target_context)` |  |
| `def _has_transfer_history(source, target)` |  |
| `def _get_historical_compatibility(source, target, use_fallback)` |  |
| `def _calculate_factor_similarity(source, target)` |  |
| `def _calculate_transfer_efficiency(source_context, target_context, knowledge_type, transfer_strategy)` |  |
| `def _calculate_transfer_efficiency_with_strategy(source_context, target_context, knowledge_type, transfer_strategy)` |  |
| `def _get_context_adjustment_factor(source, target)` |  |
| `def _adapt_baselines_to_context(baselines, source_context, target_context)` |  |
| `def _get_context_knowledge_amount(context)` |  |
| `def _calculate_transfer_potential(source_context, target_context)` |  |
| `def _filter_patterns_by_compatibility(patterns, target_context, strategy)` |  |
| `def _filter_strategies_by_compatibility(strategies, target_context, strategy)` |  |
| `def _calculate_pattern_compatibility(pattern, target_context, strategy)` |  |
| `def _calculate_strategy_applicability(strategy, target_context)` |  |
| `def _transform_knowledge_for_target(knowledge_data, source_context, target_context, strategy, transfer_strategy)` |  |
| `def _update_transfer_patterns(transfer)` | Registrar una transferencia sin romper historiales JSON de versiones anteriores. |
| `def _apply_success_patterns(patterns, transfer)` |  |
| `def _apply_adaptation_strategies(strategies, transfer)` |  |
| `def _apply_performance_baselines(baselines, transfer)` |  |
| `def _apply_transferred_knowledge(transfer)` |  |
| `def _evaluate_knowledge_application(transfer)` |  |
| `def get_transfer_confidence(transfer_id, result)` | Obtener una confianza acotada usando primero la transferencia viva y después el historial persistido. |
| `def _resolve_transfer_confidence(transfer_id, transfer, efficiency)` | Resolver la confianza de una transferencia viva: feedback explícito > atributo > eficiencia. |
| `def register_feedback(transfer_id, feedback_data, result)` | Registrar feedback y sincronizar el objeto de transferencia con su historial. |
| `def register_transfer_feedback(transfer_id, success, feedback_score, feedback_comments)` | Alias compatible que acepta el contrato público de feedback de transferencia. |
| `def _update_global_confidence_metrics(success, feedback_score)` |  |
| `def adjust_transfer_confidence(transfer_id, adjustment_factor, feedback_success, feedback_score, reason)` |  |
| `def evaluate_transfer_result(transfer, execution_result)` | Evaluar una transferencia; acepta un KnowledgeTransfer o su identificador legacy. |
| `def _record_successful_transfer_pattern(source_context, target_context, knowledge_type)` |  |
| `def knowledge_transaptors()` | Alias de `knowledge_transfers` para los consumidores que expected este nombre. |
| `def get_knowledge_transfer_objects(context_type, knowledge_type, min_efficiency)` | Devolver objetos KnowledgeTransfer; complemento al resumen serializable legacy. |
| `def get_knowledge_transfers(context_type, knowledge_type, min_efficiency)` | Obtener transferencias filtradas. |
| `def batch_knowledge_transfer(transfer_requests)` |  |
| `def auto_transfer_knowledge(target_context, knowledge_types, min_compatibility, max_transfers)` |  |
| `def transfer_knowledge_with_feedback(source_context, target_context, knowledge_type, feedback_callback)` |  |
| `def get_transfer_recommendations(target_context, max_recommendations, min_efficiency)` |  |
| `def _calculate_transfer_urgency(target_context, knowledge_type)` |  |
| `def _generate_recommendation_reasoning(source_context, target_context, knowledge_type, compatibility, priority)` |  |
| `def _estimate_transfer_efficiency(source, target, knowledge_type)` |  |
| `def _identify_relevant_knowledge_types(source, target)` |  |
| `def _generate_transfer_reasoning(source, target, knowledge_type)` |  |
| `def _calculate_transfer_priority(compatibility, potential, knowledge_type)` |  |
| `def _get_available_knowledge_types(context)` |  |
| `def record_resource_allocation(allocation_data)` |  |
| `def _update_resource_usage_patterns(resource_type, context, priority, status)` |  |
| `def add_adaptation_rule(rule)` |  |
| `def remove_adaptation_rule(rule_id)` |  |
| `def enable_rule(rule_id)` |  |
| `def disable_rule(rule_id)` |  |
| `def get_adaptation_rule(rule_id)` |  |
| `def get_adaptation_rules()` |  |
| `def list_adaptation_rules(enabled_only)` |  |
| `def save_adaptation_rules()` |  |
| `def _save_adaptation_rules()` |  |
| `def _campos_de_formato(clave)` | Campos del FORMATO REAL de las filas de un fichero de persistencia. |
| `def _campo_de_identidad(clave)` | Campo que IDENTIFICA una fila en el FORMATO REAL de un fichero. |
| `def _identidad_de_regla(row)` | IDENTIDAD REGISTRABLE de una fila de regla. |
| `def _desviaciones_de_regla(row)` | Desviaciones de una fila de regla respecto del FORMATO REAL. |
| `def _desviaciones_estrictas_de_regla(row)` | Desviaciones de los campos de conversión ESTRICTA de una fila de regla. |
| `def _valor_por_defecto_de_recuperacion(campo, regla_id)` | Valor por DEFECTO de RECUPERACIÓN de un campo de regla. |
| `def _recuperar_fila_de_regla(row, desviaciones)` | RECUPERA la fila de regla corrupta en el NIVEL del CAMPO. |
| `def _procesar_fila_de_regla(row, identidades)` | Procesa UNA fila de regla por el pipeline COMUN a las dos vías. |
| `def _valores_del_contenedor_de_reglas(rows)` | VALORES del contenedor `rules` cuando el contenedor tiene FORMA de mapeo. |
| `def _recuperar_grupos_de_base(clave, valor)` | RECUPERA los GRUPOS sanos de una sección con un grupo corrupto. |
| `def _registrar_recuperacion(fichero, unidad, recuperaciones)` | Anota en el INFORME de recuperación lo que se ha recuperado. |
| `def recovery_report()` | INFORME de lo que el cargador ha RECUPERADO (2.8.8.9.7.2). |
| `def _fila_valida(fila, clave)` | Comprobar que una fila de persistencia respeta el FORMATO REAL. |
| `def _estrategia_aprendida_valida(entrada)` | Comprobar que una entrada de estrategia aprendida aporta EVIDENCIA. |
| `def _seccion_de_conocimiento_valida(clave, valor)` | Comprobar que una sección de la base respeta el FORMATO REAL. |
| `def load_adaptation_rules()` |  |
| `def _load_adaptation_rules()` | Alias privado legacy de load_adaptation_rules. |
| `def save_knowledge_base()` |  |
| `def load_knowledge_base()` |  |
| `def save_all_data()` |  |
| `def load_all_data()` | Carga TODA la persistencia que lee esta carga y DECLARA lo que ocurrio. |
| `def _hay_que_cargar()` | Hay AL MENOS UNO de los ficheros de persistencia que esta carga LEE. |
| `def _unidades_obtenidas()` | Unidades de datos utilizables que la ultima carga ha OBTENIDO. |
| `def backup_data(backup_dir)` | Respalda los CUATRO ficheros de persistencia (2.8.8.9.8.2). |
| `def export_adaptation_history(export_file)` |  |
| `def integrate_with_performance_optimizer()` |  |
| `def integrate_with_self_improvement_system()` |  |
| `def integrate_with_adaptive_learning_engine()` |  |
| `def integrate_with_pattern_analyzer()` |  |
| `def set_meta_learning_system(meta_learning_system)` |  |
| `def integrate_with_meta_learning_system(meta_learning_system)` |  |
| `def full_system_integration()` |  |
| `def _map_optimization_to_adaptation(recommendation)` |  |
| `def _determine_learning_mode()` |  |
| `def _sync_adaptation_rules(improvement_rules)` |  |
| `def _calculate_adaptive_learning_rate()` |  |
| `def _calculate_adaptive_batch_size()` |  |
| `def _calculate_adaptive_max_epochs()` |  |
| `def _calculate_adaptive_patience()` |  |
| `def _create_adaptation_rule_from_pattern(pattern)` |  |
| `def get_integration_status()` |  |
| `def update_system_configs()` |  |
| `def get_available_strategies(context)` |  |
| `def generate_strategy_candidates(target_context, max_candidates, min_confidence)` |  |
| `def validate_candidate_strategy(candidate)` | Validar estructura y rangos de un candidato de estrategia. |
| `def evaluate_candidate_strategy(candidate, target_context)` | Evaluar una estrategia en su contexto destino sin comparar un contexto consigo mismo como transferencia. |
| `def select_strategy(evaluated_strategies, current_strategy)` |  |
| `def compare_strategies(strategy1, strategy2)` |  |
| `def apply_strategy(strategy, target_context)` |  |
| `def _verify_strategy_application(strategy, target_context)` |  |
| `def _revert_strategy_application(strategy, target_context)` |  |
| `def represent_adaptation(original_goal, context_snapshot, adaptation_rules)` | Crear una copia adaptada del Goal; acepta objetos y diccionarios. |
| `def _goal_to_dict(goal)` |  |
| `def _rule_to_dict(rule)` |  |
| `def _snapshot_to_dict(snapshot)` |  |
| `def create_goal_adaptation_proposal(original_goal, context_snapshot, adaptation_rules)` |  |
| `def _validate_adaptation_constraints(original_goal, adapted_goal, adaptation_rules)` |  |
| `def _are_constraints_contradictory(constraint_a, constraint_b)` |  |
| `def _check_intention_preservation(original_goal, adapted_goal)` |  |
| `def _targets_equivalent(a, b)` |  |
| `def _validate_goal_structure(goal)` |  |
| `def _validate_current_state(state)` |  |
| `def _required_capabilities_for_goal(goal)` |  |
| `def _validate_capabilities(goal, available_capabilities)` |  |
| `def _validate_goal_preconditions(goal, current_state)` |  |
| `def _validate_planner_can_solve(goal, current_state)` |  |
| `def validate_adapted_goal(original_goal, adapted_goal, current_state, available_capabilities)` | Validar estructura, intención, capacidades, precondiciones y resolubilidad del Goal adaptado. |
| `def _register_validation_result(original_goal_id, adapted_goal_id, validation_result)` |  |
| `def _capture_feedback(adaptation_result)` |  |
| `def _analyze_adaptation_improvement(adaptation_result)` |  |
| `def _capture_goal_adaptation_feedback(feedback_data)` |  |
| `def _execute_goal_adaptation_learning_loop(feedback_result)` |  |
| `def _analyze_learning_patterns(patterns, metrics)` |  |
| `def _update_adaptive_strategies(learned_patterns, current_strategies)` | Actualizar estrategias manteniendo el contrato ``contexto -> lista``. |
| `def _calculate_learning_convergence(metrics, improvement)` |  |
| `def _record_feedback_analysis(adaptation_id, analysis)` |  |
| `def _record_adaptation_history(adaptation_id, analysis, adaptation_context)` |  |
| `def _extract_performance_improvement(entry)` |  |
| `def _record_learning_results(adaptation_id, patterns, strategies, convergence)` |  |
| `def _generate_pattern_description(pattern)` |  |
| `def _generate_strategy_description(pattern)` |  |
| `def _flatten_strategy_map(strategies)` | Normalizar el mapa de estrategias al índice plano ``strategy_id -> entrada``. |
| `def _known_strategy_ids()` | Identificadores de estrategias ya presentes en el mapa ``contexto -> lista``. |
| `def _project_strategies_by_context(flat)` | Proyectar el índice plano de estrategias sobre el mapa ``contexto -> lista`` del motor. |
| `def _merge_strategies_by_context(source)` | Integrar un mapa ``contexto -> lista`` de estrategias en el mapa del motor. |
| `def _save_goal_adaptation_feedback()` |  |
| `def _pattern_identity(pattern)` | Identidad estable de un patrón de aprendizaje. |
| `def _count_pattern_observations(learning_results)` | Contar las observaciones similares acumuladas por cada patrón. |
| `def _confidence_threshold()` | Umbral de confianza configurado en el motor. |
| `def _min_similar_observations()` | Mínimo de observaciones similares exigido por el motor. |
| `def _is_validated_pattern(pattern, observations)` | Comprobar si un patrón cumple el contrato de datos validados. |
| `def _filter_validated_learning_results(learning_results)` | Dejar en `learning_results` únicamente los patrones validados. |
| `def _recover_learning_patterns(learning_results)` | Recuperar únicamente los patrones de aprendizaje validados (2.8.8.9.4.4). |
| `def _save_goal_adaptation_learning_results()` |  |
| `def _load_goal_adaptation_feedback()` |  |
| `def _load_goal_adaptation_learning_results()` |  |
| `def _initialize_goal_adaptation_persistence()` |  |
| `def expected_storage_paths()` | Rutas del almacenamiento de persistencia que el motor espera encontrar. |
| `def detect_absent_storage()` | Detecta que parte del almacenamiento esperado falta en disco. |
| `def expected_storage_sections()` | Secciones de primer nivel que el motor espera en cada fichero de persistencia. |
| `def detect_absent_sections()` | Detecta secciones ausentes dentro de los ficheros de persistencia existentes. |
| `def detect_corruption()` | Detecta la corrupción del contenido en los ficheros de persistencia. |
| `def _deteccion(class_id, location)` | Desviación detectada, con los datos de la clase declarada. |
| `def _detect_corruption_in(name, payload)` | Desviaciones detectadas en un fichero de persistencia. |
| `def _es_convertible_a_entero(value)` | Comprobar si `int(value)` no lanza, como hace el cargador real. |
| `def _es_marca_iso(value)` | Comprobar si una marca de tiempo se puede leer como ISO. |
| `def _detect_corruption_rules(payload)` | Desviaciones del FORMATO REAL de `contextual_adaptation_rules.json`. |
| `def _detect_corruption_knowledge_base(payload)` | Desviaciones del FORMATO REAL de `contextual_knowledge_base.json`. |
| `def _detect_corruption_feedback(payload)` | Desviaciones del FORMATO REAL de `goal_adaptation_feedback.json`. |
| `def _detect_corruption_learning_results(payload)` | Desviaciones del FORMATO REAL de `goal_adaptation_learning_results.json`. |
| `def no_data_behavior()` | Contrato DECLARATIVO del comportamiento del motor SIN DATOS (2.8.8.9.5.3). |
| `def corruption_criteria()` | Contrato DECLARATIVO de los criterios de CORRUPCIÓN (2.8.8.9.6.1). |
| `def recoverable_data()` | Contrato DECLARATIVO de los DATOS RECUPERABLES (2.8.8.9.7.1). |
| `def total_loss_fallback()` | Contrato DECLARATIVO del FALLBACK por CORRUPCIÓN TOTAL (2.8.8.9.8.1). |
| `def minimum_evidence()` | Contrato DECLARATIVO de la EVIDENCIA MINIMA (2.8.8.9.9.2). |
| `def set_architecture_manager(architecture_manager)` |  |
| `def update_architecture_state(architecture_state)` |  |
| `def update_components(components)` |  |
| `def process_architectural_result(architectural_result)` |  |
| `def process_evidence_registration(verification_id, evidence_record)` |  |
| `def on_proposal_created(proposal)` |  |
| `def start_contextual_adaptation_loop()` |  |
| `def stop_contextual_adaptation_loop()` |  |
| `def get_adaptation_summary()` |  |
| `def get_context_insights()` |  |
| `def get_engine_status()` |  |
| `def _safe_float(value, default)` |  |
| `def _bounded_float(cls, value, minimum, maximum)` |  |
| `def _coerce_context(value)` |  |
| `def _call_optional(obj, method_name)` |  |
| `def _json_default(value)` |  |
| `def _serializable_history(cls, item)` |  |
| `def clear_conversational_memory(days_old)` | Elimina conversaciones antiguas de memoria conversacional. |
| `def clear_adaptation_history(days_old)` | Elimina registros antiguos de historial de adaptación. |
| `def clear_knowledge_base_patterns(context_type, min_success_rate)` | Limpia patrones de conocimiento con bajo rendimiento o contexto específico. |
| `def reset_learning_data()` | Reinicia datos de aprendizaje y métricas del sistema. |
| `def clear_corrupted_data()` | Elimina datos corruptos detectados por el sistema. |
| `def manual_system_reset(preserve_config)` | Reinicio manual completo del sistema. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _cumple_tipo(value, tipo)`  (L72) | Comprobar que un valor respeta el tipo declarado en el FORMATO REAL. |
| `def _tipo_de_valor(value)`  (L78) | Tipo declarado en el FORMATO REAL que corresponde a un valor concreto. |
| `def _casa_target(declarado, observados)`  (L88) | Comprobar si un `target` declarado casa con algún target observado. |
| `def main()`  (L4941) | Demostración breve; los métodos de la clase permanecen fuera de main. |

<a name="src-utils-contextual_pattern_recognizer-py"></a>
### `src/utils/contextual_pattern_recognizer.py` [509 líneas] — Reconocedor de patrones contextuales para JARVIS.

**Descripción:** Reconocedor de patrones contextuales para JARVIS.

**Importaciones:** 9.

`class ContextualPatternType(Enum)`  (línea 18) — Tipos de patrones contextuales específicos.

_Sin métodos definidos en el AST._

`class ContextualPattern`  (línea 29) — Estructura de patrón contextual detectado.

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ContextualPatternRecognizer`  (línea 44) — Reconocedor de patrones relacionados con contexto y conectarlos con PatternAnalyzer.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(pattern_analyzer)` |  |
| `def add_contextual_pattern(snapshot)` | Añadir snapshot de contexto y detectar patrones contextuales. |
| `def _detect_contextual_pattern(snapshot)` | Detectar patrones contextuales específicos. |
| `def _detect_contextual_anomaly(snapshot)` | Detectar anomalías contextuales. |
| `def _detect_contextual_trend(snapshot)` | Detectar tendencias contextuales. |
| `def _detect_contextual_correlation(snapshot)` | Detectar correlaciones contextuales. |
| `def _detect_contextual_trend(snapshot)` | Detectar tendencias contextuales. |
| `def _detect_contextual_seasonal(snapshot)` | Detectar patrones estacionales contextuales. |
| `def _detect_contextual_burst(snapshot)` | Detectar patrones de burst contextuales. |
| `def _detect_contextual_changepoint(snapshot)` | Detectar puntos de cambio contextuales. |
| `def _generate_trend_actions(trend_factors)` | Generar acciones sugeridas para tendencias. |
| `def _calculate_contextual_compatibility(snapshot)` | Calcular puntuación de compatibilidad del contexto. |
| `def _get_affected_components(snapshot)` | Obtener componentes afectados basado en el contexto. |
| `def _generate_anomaly_actions(anomalies)` | Generar acciones para anomalías. |
| `def _generate_trend_actions(trend_factors)` | Generar acciones para tendencias. |
| `def _generate_correlation_actions(correlations)` | Generar acciones para correlaciones. |
| `def _generate_seasonal_actions(patterns)` | Generar acciones para patrones estacionales. |
| `def _generate_burst_actions(burst_factors)` | Generar acciones para patrones de burst. |
| `def _generate_changepoint_actions(extreme_changes)` | Generar acciones para puntos de cambio. |
| `def get_contextual_patterns(pattern_type)` | Obtener patrones contextuales, filtrados por tipo si se especifica. |
| `def get_patterns_by_severity(severity)` | Obtener patrones por severidad. |
| `def get_high_compatibility_patterns(threshold)` | Obtener patrones con alta compatibilidad. |
| `def clear_patterns(older_than_hours)` | Limpiar patrones antiguos. |
| `def get_pattern_summary()` | Obtener resumen de patrones detectados. |
| `def export_patterns(file_path)` | Exportar patrones a archivo JSON. |

<a name="src-utils-dynamic_resource_allocator-py"></a>
### `src/utils/dynamic_resource_allocator.py` [1336 líneas] — Dynamic Resource Allocator v2.8.4.2

**Descripción:** Dynamic Resource Allocator v2.8.4.2

**Importaciones:** 9.

`class ResourceType(Enum)`  (línea 18) — Tipos de recursos gestionables

_Sin métodos definidos en el AST._

`class ResourcePriority(Enum)`  (línea 34) — Prioridades de recurso

_Sin métodos definidos en el AST._

`class AllocationStatus(Enum)`  (línea 42) — Estados de asignación

_Sin métodos definidos en el AST._

`class ResourceRequest`  (línea 53) — Representa una solicitud de recurso.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def validate()` | Validar la solicitud. |
| `def to_dict()` | Convertir a diccionario. |

`class ResourceAllocation`  (línea 132) — Representa una asignación de recurso.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class ResourceAvailability`  (línea 162) — Representa la disponibilidad de un recurso.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def can_satisfy(request_amount)` | Verificar si el recurso puede satisfacer la solicitud. |

`class DynamicResourceAllocator`  (línea 198) — Sistema de asignación de recursos según contexto.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(monitor, optimizer)` | Inicializar el asignador de recursos. |
| `def register_resource(resource_type, available, available_amount, maximum, unit)` | Registrar un recurso disponible. |
| `def create_request(request_id, resource_type, amount, context, priority, required)` | Crear una solicitud de recurso. |
| `def allocate(request)` | Asignar un recurso. |
| `def _has_conflict(request)` | Verificar si hay conflictos con asignaciones existentes. |
| `def _contexts_conflict(context1, context2)` | Verificar si dos contextos tienen conflictos. |
| `def get_conflicts(request)` | Identificar conflictos reales con asignaciones existentes. |
| `def _is_user_work(allocation)` | Determinar si una asignación es trabajo de usuario. |
| `def _can_preempt(existing_allocation, new_request)` | Verificar si una asignación existente puede ser preemptada. |
| `def _try_preempt(conflicts, new_request)` | Intentar preemptar asignaciones en conflicto según prioridad. |
| `def defer_request(request)` | Aplazar una solicitud cuando no hay recurso disponible. |
| `def get_pending_requests()` | Obtener solicitudes diferidas. |
| `def process_deferred()` | Intentar asignar solicitudes diferidas. |
| `def _allocate_direct(request)` | Intentar asignación directa sin verificación de conflictos (para deferred). |
| `def release(allocation_id)` | Liberar una asignación. |
| `def get_availability(resource_type)` | Obtener disponibilidad de un recurso. |
| `def get_allocation(allocation_id)` | Obtener una asignación. |
| `def get_all_allocations()` | Obtener todas las asignaciones. |
| `def update_usage(allocation_id, used_amount)` | Actualizar el uso real de una asignación. |
| `def cleanup()` | Limpieza de recursos. |
| `def update_system_resources()` | Actualizar recursos del sistema desde PerformanceMonitor. |
| `def update_execution_resources(registry_size)` | Actualizar recursos de ejecución. |
| `def update_thread_pool_resources(max_workers)` | Actualizar recursos de pool de hilos. |
| `def update_storage_resources(cache_size)` | Actualizar recursos de almacenamiento. |
| `def connect_context(context)` | Conectar con el contexto actual. |
| `def adjust_allocation_for_context(allocation_id)` | Ajustar una asignación usando solo datos disponibles en el contexto. |
| `def adjust_all_allocations_for_context()` | Ajustar todas las asignaciones usando datos disponibles del contexto. |
| `def recalculate_on_context_change(new_context)` | Recalcular asignaciones cuando el contexto cambia. |
| `def set_contextual_adaptation_engine(engine)` | Conectar con el ContextualAdaptationEngine. |
| `def get_contextual_adaptation_engine()` | Obtener la instancia conectada de ContextualAdaptationEngine. |
| `def set_performance_optimizer(optimizer)` | Conectar con el PerformanceOptimizer. |
| `def get_performance_optimizer()` | Obtener la instancia conectada de PerformanceOptimizer. |
| `def notify_allocation_to_contextual_engine(allocation)` | Notificar una asignación al ContextualAdaptationEngine. |
| `def request_optimization_from_performance_optimizer(optimization_request)` | Solicitar optimización al PerformanceOptimizer. |
| `def get_resource_allocation_status_for_planner()` | Obtener estado de asignación de recursos para el Planner/Executor. |
| `def integrate_with_planner_executor(planner_context)` | Integrar completamente con Planner/Executor mediante contratos existentes. |
| `def _get_available_capabilities_for_planner()` | Obtener capacidades disponibles para el Planner en formato compatible. |
| `def _get_optimization_suggestions_for_planner()` | Obtener sugerencias de optimización para el Planner. |

<a name="src-utils-error_dashboard-py"></a>
### `src/utils/error_dashboard.py` [592 líneas] — Error Recovery Dashboard for JARVIS System

**Descripción:** Error Recovery Dashboard for JARVIS System

**Importaciones:** 10.

`class DashboardView(Enum)`  (línea 17) — Dashboard view types

_Sin métodos definidos en el AST._

`class ErrorSeverity(Enum)`  (línea 25) — Error severity levels

_Sin métodos definidos en el AST._

`class ErrorRecoveryDashboard`  (línea 32) — Main dashboard for error recovery monitoring

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path, update_interval)` |  |
| `def _init_database()` | Initialize dashboard database |
| `def _setup_data_sources()` | Setup data sources for dashboard |
| `def start_dashboard()` | Start the dashboard update thread |
| `def stop_dashboard()` | Stop the dashboard update thread |
| `def _update_loop()` | Main dashboard update loop |
| `def _update_all_data()` | Update all cached data |
| `def _get_cached_data(key)` | Get cached data if available and not expired |
| `def _cache_data(key, data, ttl)` | Cache data with optional TTL |
| `def _get_overview_data()` | Get dashboard overview data |
| `def _get_active_errors_data()` | Get active errors data |
| `def _get_recovery_history_data()` | Get recovery history data |
| `def _get_system_health_data()` | Get system health data |
| `def _get_alerts_data()` | Get alerts data |
| `def _get_error_statistics()` | Get error statistics from database |
| `def _get_recovery_statistics()` | Get recovery statistics from database |
| `def _get_system_health()` | Get current system health |
| `def _get_active_recoveries()` | Get list of active recoveries |
| `def _count_errors_by_severity(errors)` | Count errors by severity |
| `def _count_errors_by_component(errors)` | Count errors by component |
| `def _count_recoveries_by_action(recoveries)` | Count recoveries by action |
| `def _count_recoveries_by_component(recoveries)` | Count recoveries by component |
| `def _count_alerts_by_severity(alerts)` | Count alerts by severity |
| `def _count_alerts_by_source(alerts)` | Count alerts by source |
| `def get_dashboard_data(view)` | Get dashboard data for specified view |
| `def get_dashboard_views()` | Get available dashboard views |
| `def refresh_data()` | Force refresh of all cached data |
| `def log_view_access(view_name)` | Log dashboard view access |
| `def get_view_statistics()` | Get dashboard view access statistics |
| `def __str__()` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_error_dashboard()`  (L576) | Get a singleton instance of ErrorRecoveryDashboard |
| `def start_error_dashboard()`  (L583) | Start the error dashboard |
| `def stop_error_dashboard()`  (L589) | Stop the error dashboard |

<a name="src-utils-error_recovery-py"></a>
### `src/utils/error_recovery.py` [522 líneas] — Error Recovery System for JARVIS

**Descripción:** Error Recovery System for JARVIS

**Importaciones:** 11.

`class ErrorSeverity(Enum)`  (línea 18) — Error severity levels

_Sin métodos definidos en el AST._

`class ErrorType(Enum)`  (línea 25) — Error categories

_Sin métodos definidos en el AST._

`class RecoveryStrategy(Enum)`  (línea 35) — Recovery strategy types

_Sin métodos definidos en el AST._

`class ErrorRecoveryManager`  (línea 44) — Main error recovery management system

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def get_error_recovery_manager()` | Get a singleton instance of ErrorRecoveryManager |
| `def _init_database()` | Initialize error recovery database |
| `def _register_default_strategies()` | Register default recovery strategies |
| `def register_strategy(name, strategy_func)` | Register a recovery strategy |
| `def register_handler(error_type, handler_func)` | Register an error handler for specific error types |
| `def log_error(error_type, severity, component, error_message, stack_trace, additional_data)` | Log an error for tracking and analysis |
| `def _update_error_stats(error_type, severity, recovered)` | Update error statistics |
| `def recover_from_error(error_id, strategy, max_retries, retry_delay)` | Attempt to recover from a logged error |
| `def _get_error_details(error_id)` | Get detailed information about an error |
| `def _determine_best_strategy(error_details)` | Determine the best recovery strategy based on error type and severity |
| `def _execute_recovery_strategy(error_id, strategy, max_retries, retry_delay)` | Execute a specific recovery strategy |
| `def _retry_strategy(error_id, max_retries, retry_delay)` | Retry strategy with exponential backoff |
| `def _fallback_strategy(error_id)` | Fallback to alternative implementation |
| `def _circuit_breaker_strategy(error_id)` | Circuit breaker pattern for handling repeated failures |
| `def _timeout_strategy(error_id)` | Timeout strategy for hanging operations |
| `def _restart_strategy(error_id)` | Restart strategy for critical failures |
| `def _update_recovery_status(error_id, success)` | Update the recovery status of an error |
| `def _update_execution_time(error_id, execution_time)` | Update the execution time of a recovery attempt |
| `def get_error_statistics(days)` | Get error statistics for the specified number of days |
| `def get_active_errors()` | Get list of active (unrecovered) errors |
| `def cleanup_old_errors(days)` | Clean up old error records |
| `def __str__()` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_error_recovery_manager()`  (L507) | Get a singleton instance of ErrorRecoveryManager |
| `def start_error_recovery()`  (L514) | Start the error recovery system |
| `def stop_error_recovery()`  (L520) | Stop the error recovery system |

<a name="src-utils-get_coords-py"></a>
### `src/utils/get_coords.py` [456 líneas] — Calibrador manual de la macro riot_api.

**Descripción:** Calibrador manual de la macro riot_api.

**Importaciones:** 11.

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _get_macros_coords_path()`  (L47) | Obtiene la ruta de macros_coords.json. |
| `def _screen_key(monitor)`  (L68) | Convierte el ID lógico del monitor a la clave sN del JSON. |
| `def _format_monitor(monitor)`  (L73) | Devuelve una descripción legible del monitor. |
| `def _get_monitor_for_screen_number(screen_number)`  (L83) | Obtiene un monitor configurado por su número lógico 1-based. |
| `def _detect_monitor_from_mouse()`  (L101) | Obtiene el monitor que contiene actualmente el puntero. |
| `def _capture_point_on_monitor(monitor, paso, paso_index)`  (L119) | Espera a que el ratón permanezca quieto IDLE_SECONDS sobre el monitor. |
| `def _calculate_capture_region(corners)`  (L176) | Calcula [x, y, ancho, alto] usando las cuatro esquinas. |
| `def _build_calibration_data(points, capture_region)`  (L207) | Construye el bloque de datos de calibración. |
| `def imprimir_resultados(datos, screen_key)`  (L223) | Muestra por consola los datos capturados. |
| `def _load_json(ruta_json)`  (L236) | Carga el JSON existente o crea una estructura raíz vacía. |
| `def _atomic_write_json(ruta_json, data)`  (L249) | Escribe el JSON de forma atómica para evitar archivos incompletos. |
| `def gestionar_json(nuevos_datos, screen_key, ruta_json)`  (L277) | Actualiza únicamente riot_api para el monitor indicado. |
| `def calibrar_api_key_riot_macro(screen_number)`  (L342) | Ejecuta la calibración manual de riot_api. |
| `def calibrarApiKeyRiotMacro(screen_number)`  (L448) | Alias compatible con la función histórica del proyecto. |

<a name="src-utils-health_checker-py"></a>
### `src/utils/health_checker.py` [498 líneas] — Sistema de verificación de salud para JARVIS.

**Descripción:** Sistema de verificación de salud para JARVIS.

**Importaciones:** 12.

`class HealthStatus(Enum)`  (línea 21) — Estados de salud de un componente.

_Sin métodos definidos en el AST._

`class HealthCheck`  (línea 30) — Resultado de una verificación de salud.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte el resultado a un diccionario serializable. |

`class HealthCheckConfig`  (línea 53) — Configuración para las verificaciones de salud.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte la configuración a un diccionario. |

`class HealthChecker`  (línea 96) — Verificador de salud del sistema JARVIS.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config)` | Inicializa el verificador de salud. |
| `def start_health_checks()` | Inicia las verificaciones periódicas de salud. |
| `def stop_health_checks()` | Detiene las verificaciones de salud. |
| `def _health_check_loop()` | Bucle principal de verificación de salud. |
| `def perform_comprehensive_health_check()` | Realiza una verificación completa de salud de todos los componentes. |
| `def check_component_health(component_name)` | Verifica la salud de un componente específico. |
| `def check_system_health()` | Verifica la salud general del sistema. |
| `def _get_component_module_path(component_name)` | Obtiene la ruta del módulo para un componente. |
| `def _process_health_check(result)` | Procesa un resultado de verificación de salud. |
| `def _notify_health_change(result)` | Notifica callbacks sobre cambios en la salud. |
| `def add_health_change_callback(callback)` | Agrega un callback para recibir notificaciones de cambios de salud. |
| `def remove_health_change_callback(callback)` | Remueve un callback de notificaciones de salud. |
| `def get_health_status(component_name)` | Obtiene el estado de salud de un componente o todos los componentes. |
| `def get_health_summary()` | Obtiene un resumen del estado de salud actual. |
| `def get_component_health_history(component_name, limit)` | Obtiene el historial de salud de un componente específico. |
| `def export_health_report(filepath, include_history)` | Exporta un reporte de salud a un archivo JSON. |
| `def clear_history()` | Limpia el historial de verificaciones de salud. |
| `def is_component_healthy(component_name)` | Verifica si un componente está saludable. |
| `def get_unhealthy_components()` | Obtiene una lista de componentes no saludables. |
| `def __enter__()` | Context manager entry. |
| `def __exit__(exc_type, exc_val, exc_tb)` | Context manager exit. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_health_checker()`  (L481) | Obtiene la instancia global del verificador de salud. |
| `def start_health_checks()`  (L489) | Inicia las verificaciones de salud globales. |
| `def stop_health_checks()`  (L495) | Detiene las verificaciones de salud globales. |

<a name="src-utils-health_monitor-py"></a>
### `src/utils/health_monitor.py` [418 líneas] — Health Monitor for JARVIS System

**Descripción:** Health Monitor for JARVIS System

**Importaciones:** 11.

`class HealthStatus(Enum)`  (línea 18) — Health status levels

_Sin métodos definidos en el AST._

`class ComponentType(Enum)`  (línea 25) — System component types

_Sin métodos definidos en el AST._

`class HealthMetric`  (línea 35) — Individual health metric

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, value, threshold, component, metric_type)` |  |
| `def is_healthy()` | Check if metric is within healthy bounds |
| `def get_status()` | Get health status based on value |

`class HealthMonitor`  (línea 64) — Main health monitoring system

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path, check_interval)` |  |
| `def _init_database()` | Initialize health monitoring database |
| `def _register_default_metrics()` | Register default health metrics |
| `def register_metric(name, threshold, component, metric_type)` | Register a health metric |
| `def register_health_callback(component, callback)` | Register callback for health status changes |
| `def check_metric(name, value)` | Check a specific metric |
| `def check_all_metrics()` | Check all registered metrics |
| `def _log_metric(metric)` | Log metric to database |
| `def _log_health_summary(metrics)` | Log overall health summary |
| `def _trigger_health_callbacks(component, metric_name, old_status, new_status)` | Trigger registered health callbacks |
| `def _create_alert(metric_name, status)` | Create health alert |
| `def start_monitoring()` | Start continuous health monitoring |
| `def stop_monitoring()` | Stop continuous health monitoring |
| `def _monitor_loop()` | Main monitoring loop |
| `def get_current_health()` | Get current health status |
| `def get_health_history(hours)` | Get health history for specified hours |
| `def get_active_alerts()` | Get list of active (unresolved) alerts |
| `def resolve_alert(alert_id)` | Resolve a specific alert |
| `def cleanup_old_data(days)` | Clean up old health data |
| `def __str__()` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_health_monitor()`  (L402) | Get a singleton instance of HealthMonitor |
| `def start_health_monitoring()`  (L409) | Start health monitoring |
| `def stop_health_monitoring()`  (L415) | Stop health monitoring |

<a name="src-utils-jarvis_logging_system-py"></a>
### `src/utils/jarvis_logging_system.py` [487 líneas] — Sistema de logging avanzado y análisis de patrones para JARVIS.

**Descripción:** Sistema de logging avanzado y análisis de patrones para JARVIS.

**Importaciones:** 15.

`class JarvisLoggingSystem`  (línea 32) — Sistema unificado de logging avanzado para JARVIS.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config)` |  |
| `def _default_config()` | Configuración por defecto del sistema de logging. |
| `def _create_logger()` | Crear logger avanzado. |
| `def _create_predictor()` | Crear sistema predictivo. |
| `def _create_alert_manager()` | Crear gestor de alertas. |
| `def _create_dashboard()` | Crear dashboard interactivo. |
| `def start()` | Iniciar el sistema de logging avanzado. |
| `def stop()` | Detener el sistema de logging avanzado. |
| `def _prediction_worker()` | Worker para predicciones automáticas. |
| `def _dashboard_worker()` | Worker para dashboard. |
| `def _perform_periodic_predictions()` | Realizar predicciones periódicas. |
| `def _extract_recent_features()` | Extraer características de logs recientes. |
| `def _check_and_retrain()` | Verificar si es necesario reentrenar modelos. |
| `def _cleanup_old_logs()` | Limpiar logs antiguos. |
| `def _process_alert(alert)` | Procesar alerta generada. |
| `def _trigger_event(event_type, data)` | Disparar evento a callbacks registrados. |
| `def register_event_callback(event_type, callback)` | Registrar callback para evento específico. |
| `def log(message, level, category)` | Método principal de logging. |
| `def log_error(message)` | Loggear error. |
| `def log_warning(message)` | Loggear warning. |
| `def log_info(message)` | Loggear info. |
| `def log_debug(message)` | Loggear debug. |
| `def log_performance(message)` | Loggear métrica de rendimiento. |
| `def log_with_trace(message, trace_id)` | Loggear con trace ID. |
| `def log_with_span(message, span_id, parent_span_id)` | Loggear con span ID. |
| `def get_logs(start_time, end_time, level, category, module, limit)` | Obtener logs desde la base de datos. |
| `def get_statistics()` | Obtener estadísticas del sistema de logging. |
| `def get_predictions()` | Obtener predicciones actuales. |
| `def get_alerts()` | Obtener alertas activas. |
| `def acknowledge_alert(alert_id)` | Reconocer alerta. |
| `def resolve_alert(alert_id)` | Resolver alerta. |
| `def export_logs(start_time, end_time, format)` | Exportar logs. |
| `def export_predictions(format)` | Exportar datos de predicción. |
| `def get_dashboard_url()` | Obtener URL del dashboard. |
| `def train_models()` | Entrenar modelos predictivos manualmente. |
| `def analyze_trends(days)` | Analizar tendencias. |
| `def get_patterns(acknowledged, limit)` | Obtener patrones detectados. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_jarvis_logger()`  (L459) | Obtener instancia del sistema de logging de JARVIS. |
| `def log_jarvis(message, level, category)`  (L464) | Loggear mensaje en el sistema de logging de JARVIS. |
| `def log_jarvis_error(message)`  (L470) | Loggear error en el sistema de logging de JARVIS. |
| `def log_jarvis_warning(message)`  (L475) | Loggear warning en el sistema de logging de JARVIS. |
| `def log_jarvis_info(message)`  (L480) | Loggear info en el sistema de logging de JARVIS. |
| `def log_jarvis_performance(message)`  (L485) | Loggear métrica de rendimiento en el sistema de logging de JARVIS. |

<a name="src-utils-log_analytics-py"></a>
### `src/utils/log_analytics.py` [966 líneas] — Sistema avanzado de análisis de logs para Jarvis con capacidades de business intelligence.

**Descripción:** Sistema avanzado de análisis de logs para Jarvis con capacidades de business intelligence.

**Importaciones:** 18.

`class AnalyticsType(Enum)`  (línea 24) — Tipos de análisis.

_Sin métodos definidos en el AST._

`class TimeGranularity(Enum)`  (línea 37) — Granularidad temporal.

_Sin métodos definidos en el AST._

`class AnalyticsResult`  (línea 47) — Resultado de análisis.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class LogAnalyticsEngine`  (línea 68) — Motor de análisis de logs.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def _create_database()` | Crear base de datos para análisis. |
| `def generate_summary_analytics(start_time, end_time)` | Generar análisis resumen. |
| `def generate_trend_analytics(start_time, end_time, granularity)` | Generar análisis de tendencias. |
| `def generate_pattern_analytics(start_time, end_time)` | Generar análisis de patrones. |
| `def generate_correlation_analytics(start_time, end_time)` | Generar análisis de correlaciones. |
| `def generate_performance_analytics(start_time, end_time)` | Generar análisis de rendimiento. |
| `def _query_logs(start_time, end_time)` | Consultar logs desde la base de datos. |
| `def _group_logs_by_time(logs, granularity)` | Agrupar logs por tiempo. |
| `def _analyze_trends(trend_data)` | Analizar tendencias. |
| `def _detect_significant_trends(trend_analysis)` | Detectar tendencias significativas. |
| `def _detect_patterns(logs)` | Detectar patrones en los logs. |
| `def _calculate_correlations(logs)` | Calcular correlaciones entre variables. |
| `def _create_summary_visualizations(category_counts, module_counts, error_count, total_logs)` | Crear visualizaciones para análisis resumen. |
| `def _create_trend_visualizations(trend_data, significant_trends)` | Crear visualizaciones para análisis de tendencias. |
| `def _create_pattern_visualizations(patterns)` | Crear visualizaciones para análisis de patrones. |
| `def _create_correlation_visualizations(correlations)` | Crear visualizaciones para análisis de correlaciones. |
| `def _create_performance_visualizations(response_times, success_rates, performance_stats)` | Crear visualizaciones para análisis de rendimiento. |
| `def _store_analytics_result(result)` | Almacenar resultado de análisis en base de datos. |
| `def get_analytics_history(analytics_type, limit)` | Obtener historial de análisis. |
| `def export_analytics(start_time, end_time, format)` | Exportar resultados de análisis. |

`class LogAnalytics`  (línea 922) — Wrapper para LogAnalyticsEngine que proporciona la interfaz esperada.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def get_analytics_summary()` | Obtener resumen de análisis. |
| `def generate_summary_analytics(start_time, end_time)` | Generar análisis resumen. |
| `def generate_trend_analytics(start_time, end_time, granularity)` | Generar análisis de tendencias. |
| `def generate_pattern_analytics(start_time, end_time)` | Generar análisis de patrones. |
| `def generate_correlation_analytics(start_time, end_time)` | Generar análisis de correlaciones. |
| `def generate_performance_analytics(start_time, end_time)` | Generar análisis de rendimiento. |
| `def get_analytics_history(analytics_type, limit)` | Obtener historial de análisis. |
| `def export_analytics(start_time, end_time, format)` | Exportar resultados de análisis. |

<a name="src-utils-log_dashboard-py"></a>
### `src/utils/log_dashboard.py` [887 líneas] — Dashboard interactivo para monitoreo y gestión de logs de Jarvis.

**Descripción:** Dashboard interactivo para monitoreo y gestión de logs de Jarvis.

**Importaciones:** 24.

`class DashboardView(Enum)`  (línea 27) — Vistas del dashboard.

_Sin métodos definidos en el AST._

`class DashboardWidget(Enum)`  (línea 39) — Tipos de widgets del dashboard.

_Sin métodos definidos en el AST._

`class WidgetConfig`  (línea 52) — Configuración de widget.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class DashboardAlert`  (línea 71) — Alerta del dashboard.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class RealTimeDataStreamer`  (línea 89) — Flujo de datos en tiempo real.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(max_points)` |  |
| `def add_data_point(stream_name, data)` | Añadir punto de datos a un flujo. |
| `def get_stream_data(stream_name, limit)` | Obtener datos de un flujo. |
| `def subscribe_to_stream(stream_name, callback)` | Suscribirse a un flujo de datos. |
| `def unsubscribe_from_stream(stream_name, callback)` | Desuscribirse de un flujo de datos. |

`class LogDashboard`  (línea 137) — Dashboard principal de logs.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path, port, host)` |  |
| `def _create_database()` | Crear base de datos del dashboard. |
| `def _setup_routes()` | Configurar rutas de la aplicación Flask. |
| `def _get_dashboard_template()` | Obtener plantilla HTML del dashboard. |
| `def _update_loop()` | Bucle de actualización del dashboard. |
| `def _update_real_time_data()` | Actualizar datos en tiempo real. |
| `def _update_widgets()` | Actualizar widgets del dashboard. |
| `def _get_widget_data(widget)` | Obtener datos para un widget específico. |
| `def _get_metric_card_data(widget)` | Obtener datos para widget de métrica. |
| `def _get_line_chart_data(widget)` | Obtener datos para widget de gráfico de línea. |
| `def _get_bar_chart_data(widget)` | Obtener datos para widget de gráfico de barras. |
| `def _get_pie_chart_data(widget)` | Obtener datos para widget de gráfico circular. |
| `def _get_table_data(widget)` | Obtener datos para widget de tabla. |
| `def _check_alerts()` | Verificar y generar alertas. |
| `def add_alert(alert)` | Añadir alerta al dashboard. |
| `def _save_alert(alert)` | Guardar alerta en base de datos. |
| `def _save_widget(widget)` | Guardar widget en base de datos. |
| `def _delete_widget(widget_id)` | Eliminar widget de base de datos. |
| `def start()` | Iniciar el dashboard. |
| `def _is_port_available(port, host)` | Comprobar si un puerto TCP puede enlazarse. |
| `def _resolve_port()` | Elegir un puerto disponible, probando alternativas si hace falta. |
| `def _run_server()` | Ejecutar el servidor Flask, tolerando fallos de bind. |
| `def run()` | Iniciar el dashboard (alias de start()). |
| `def stop()` | Detener el dashboard. |
| `def get_dashboard_url()` | Obtener la URL del dashboard (usa el puerto realmente asignado). |
| `def _load_default_widgets()` | Cargar widgets por defecto. |

<a name="src-utils-log_integration-py"></a>
### `src/utils/log_integration.py` [810 líneas] — Sistema de integración de logs para Jarvis con múltiples fuentes y normalización.

**Descripción:** Sistema de integración de logs para Jarvis con múltiples fuentes y normalización.

**Importaciones:** 17.

`class LogSource(Enum)`  (línea 24) — Fuentes de logs soportadas.

_Sin métodos definidos en el AST._

`class LogFormat(Enum)`  (línea 37) — Formatos de logs soportados.

_Sin métodos definidos en el AST._

`class IntegrationStatus(Enum)`  (línea 49) — Estados de integración.

_Sin métodos definidos en el AST._

`class LogSourceConfig`  (línea 59) — Configuración de una fuente de logs.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class LogIntegration`  (línea 83) — Integración de logs.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class LogNormalizer`  (línea 103) — Normalizador de logs para diferentes formatos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def normalize_log(raw_log, format_type, source_config)` | Normalizar un log a formato estándar. |
| `def _parse_json(raw_log)` | Parsear log en formato JSON. |
| `def _parse_text(raw_log)` | Parsear log en formato de texto libre. |
| `def _parse_csv(raw_log)` | Parsear log en formato CSV. |
| `def _parse_syslog(raw_log)` | Parsear log en formato syslog. |
| `def _parse_nginx(raw_log)` | Parsear log en formato Nginx. |
| `def _parse_apache(raw_log)` | Parsear log en formato Apache. |
| `def _parse_custom(raw_log)` | Parsear log en formato personalizado. |
| `def _standardize_fields(parsed_data, source_config)` | Estandarizar campos del log. |
| `def _extract_additional_info(normalized)` | Extraer información adicional usando regex. |

`class LogCollector`  (línea 348) — Colector de logs desde múltiples fuentes.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(max_workers)` |  |
| `def add_integration(integration)` | Añadir integración de logs. |
| `def remove_integration(integration_id)` | Remover integración de logs. |
| `def start_collection()` | Iniciar recolección de logs. |
| `def stop_collection()` | Detener recolección de logs. |
| `def _collection_loop()` | Bucle principal de recolección. |
| `def _collect_from_integration(integration)` | Recolectar logs desde una integración específica. |
| `def _simulate_log_fetch(config)` | Simular obtención de logs (para demostración). |
| `def _processing_loop()` | Bucle de procesamiento de logs. |
| `def _process_log(log_item)` | Procesar un log individual. |
| `def get_integration_status()` | Obtener estado de todas las integraciones. |
| `def get_collection_metrics()` | Obtener métricas de recolección. |

`class LogTransformer`  (línea 559) — Transformador de logs para diferentes destinos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def add_destination(name, config)` | Añadir destino de logs. |
| `def add_transform_rule(rule)` | Añadir regla de transformación. |
| `def transform_log(log_data, destination)` | Transformar log para un destino específico. |
| `def _apply_transform_rule(log_data, rule)` | Aplicar una regla de transformación. |
| `def _apply_field_mapping(log_data, mapping)` | Aplicar mapeo de campos. |

`class LogIntegrationSystem`  (línea 632) — Sistema completo de integración de logs.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def _create_database()` | Crear base de datos para integración de logs. |
| `def add_log_source(config)` | Añadir fuente de logs. |
| `def remove_log_source(integration_id)` | Remover fuente de logs. |
| `def start()` | Iniciar sistema de integración. |
| `def stop()` | Detener sistema de integración. |
| `def get_system_status()` | Obtener estado del sistema. |
| `def _save_integration(integration)` | Guardar integración en base de datos. |

`class LogIntegrator`  (línea 781) — Wrapper para LogIntegrationSystem que proporciona la interfaz esperada.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def add_log_source(config)` | Añadir fuente de logs. |
| `def remove_log_source(integration_id)` | Remover fuente de logs. |
| `def start()` | Iniciar sistema de integración. |
| `def stop()` | Detener sistema de integración. |
| `def get_system_status()` | Obtener estado del sistema. |

<a name="src-utils-log_predictor-py"></a>
### `src/utils/log_predictor.py` [749 líneas] — Sistema predictivo de logs para Jarvis con machine learning y análisis de tendencias.

**Descripción:** Sistema predictivo de logs para Jarvis con machine learning y análisis de tendencias.

**Importaciones:** 19.

`class PredictionType(Enum)`  (línea 24) — Tipos de predicciones.

_Sin métodos definidos en el AST._

`class PredictionConfidence(Enum)`  (línea 34) — Niveles de confianza de predicción.

_Sin métodos definidos en el AST._

`class Prediction`  (línea 43) — Estructura de predicción.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class TimeSeriesPredictor`  (línea 68) — Predictor de series temporales.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(max_history)` |  |
| `def add_data_point(metric_name, value, timestamp, features)` | Añadir punto de datos para predicción. |
| `def _train_model(metric_name)` | Entrenar modelo para una métrica específica. |
| `def _prepare_training_data(series)` | Preparar datos de entrenamiento. |
| `def predict(metric_name, time_horizon, features)` | Realizar predicción. |
| `def _get_prediction_type(metric_name)` | Determinar el tipo de predicción basado en el nombre de la métrica. |
| `def _generate_suggested_actions(metric_name, predicted_value, confidence)` | Generar sugerencias basadas en la predicción. |

`class FailurePredictor`  (línea 328) — Predictor de fallos del sistema.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def add_system_metrics(timestamp, metrics)` | Añadir métricas del sistema para predicción de fallos. |
| `def _train_failure_model()` | Entrenar modelo de predicción de fallos. |
| `def _detect_failure_in_window(start_time, end_time)` | Detectar si hubo fallos en un período de tiempo. |
| `def predict_failure_probability(time_horizon)` | Predecir probabilidad de fallo. |

`class LogPredictor`  (línea 459) — Sistema predictivo de logs integrado.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def _create_database()` | Crear base de datos para predicciones. |
| `def add_log_data(log_entry)` | Añadir datos de log para predicción. |
| `def generate_predictions(time_horizon)` | Generar predicciones para todas las métricas. |
| `def _store_prediction(prediction)` | Almacenar predicción en base de datos. |
| `def update_prediction_accuracy(prediction_id, actual_value)` | Actualizar precisión de predicción con valor real. |
| `def get_predictions_by_type(prediction_type, limit)` | Obtener predicciones por tipo. |
| `def get_active_predictions()` | Obtener predicciones activas (recientes). |
| `def get_prediction_statistics()` | Obtener estadísticas de predicciones. |
| `def export_predictions(start_time, end_time, format)` | Exportar predicciones. |
| `def add_prediction_result(predictions)` | Agregar resultado de predicción al historial. |
| `def train_models()` | Entrenar todos los modelos predictivos. |
| `def get_predictions()` | Obtener predicciones activas. |
| `def last_training()` | Obtener tiempo de último entrenamiento. |

<a name="src-utils-logger-py"></a>
### `src/utils/logger.py` [180 líneas] — Nuevo sistema de logging estructurado para Jarvis.

**Descripción:** Nuevo sistema de logging estructurado para Jarvis.

**Importaciones:** 6.

`class StructuredLogger`  (línea 44) — Logger estructurado con soporte para JSON y mejores prácticas.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, level)` |  |
| `def debug(message)` | Log de nivel DEBUG. |
| `def info(message)` | Log de nivel INFO. |
| `def warning(message)` | Log de nivel WARNING. |
| `def error(message)` | Log de nivel ERROR. |
| `def critical(message)` | Log de nivel CRITICAL. |
| `def _log(level, message)` | Log interno con contexto. |
| `def _print_log(level, message, file_name, method_name, method_start_line)` | Método de compatibilidad para logs antiguos. |
| `def _print_log(level, message, file_name, method_name, method_start_line)` | Método compatible con el antiguo logger. |

`class JsonFormatter(logging.Formatter)`  (línea 148) — Formateador que convierte logs a JSON.

Métodos:

| Firma | Docstring |
|---|---|
| `def format(record)` | Formatear un log record como JSON. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_logger(name, level)`  (L174) | Obtener un logger estructurado. |

<a name="src-utils-meta_learning_system-py"></a>
### `src/utils/meta_learning_system.py` [2401 líneas] — Meta Learning System v2.8.0

**Descripción:** Meta Learning System v2.8.0

**Importaciones:** 26.

`class MetaLearningLevel(Enum)`  (línea 36) — Niveles de metaprendizaje

_Sin métodos definidos en el AST._

`class MetaLearningResult(Enum)`  (línea 45) — Resultados del metaprendizaje

_Sin métodos definidos en el AST._

`class LearningExperience`  (línea 55) — Representa una experiencia de aprendizaje

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class LearningEvaluation`  (línea 71) — Resultado de evaluar una estrategia de aprendizaje con evidencia disponible

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class MetaRuleStatus(Enum)`  (línea 88) — Resultado de evaluar/aplicar una meta-regla sobre una regla de aprendizaje

_Sin métodos definidos en el AST._

`class MetaRule`  (línea 100) — Meta-regla: una regla que actúa sobre otra regla de aprendizaje existente.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def is_valid()` |  |

`class MetaRuleApplication`  (línea 129) — Registro de una aplicación de meta-regla, con estado previo para poder revertir

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class MetaLearningInsight`  (línea 143) — Representa un insight de metaprendizaje

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class MetaLearningSystem`  (línea 161) — Sistema de metaprendizaje que analiza el comportamiento de los sistemas de aprendizaje existentes

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path)` |  |
| `def _load_config()` | Cargar configuración del sistema |
| `def _save_config()` | Guardar configuración actual |
| `def capture_learning_experience(learning_system, task_type, context, strategy, parameters, outcome, success_metrics, confidence_score)` | Captura una experiencia de aprendizaje para análisis metaprendizaje |
| `def capture_structured_experience(learning_system, task_type, context_features, action_taken, strategy_applied, strategy_parameters, execution_result, performance_metrics, contextual_factors)` | Captura una experiencia de aprendizaje estructurada con asociación explícita |
| `def capture_experience_with_context(learning_system, task_type, environment_context, user_context, system_context, action_executed, strategy_info, outcome_data, learning_value)` | Captura una experiencia con asociación detallada de contexto completo |
| `def _get_current_system_state()` | Obtiene el estado actual del sistema |
| `def _extract_success_indicators(performance_metrics)` | Extrae indicadores de éxito de las métricas de rendimiento |
| `def _extract_failure_indicators(execution_result)` | Extrae indicadores de fallo del resultado de ejecución |
| `def _calculate_experience_confidence(performance_metrics)` | Calcula la confianza de la experiencia basada en métricas de rendimiento |
| `def _assess_context_completeness(context)` | Evalúa la completitud del contexto |
| `def _assess_result_quality(execution_result)` | Evalúa la calidad del resultado de ejecución |
| `def _get_session_id()` | Obtiene o genera un ID de sesión |
| `def _assess_task_complexity(task_type)` | Evalúa la complejidad de la tarea |
| `def _assess_resource_availability(system_context)` | Evalúa la disponibilidad de recursos |
| `def _extract_decision_points(action_executed)` | Extrae puntos de decisión de la acción ejecutada |
| `def _extract_resource_usage(action_executed)` | Extrae uso de recursos de la acción ejecutada |
| `def _assess_learning_potential(task_type, outcome_data)` | Evalúa el potencial de aprendizaje de la experiencia |
| `def _assess_reusability(context, outcome)` | Evalúa la reutilidad de la experiencia |
| `def _validate_experience_utility(learning_system, task_type, context, outcome)` | Valida si una experiencia tiene utilidad para el metaprendizaje |
| `def get_learning_success_indicators()` | Identifica los indicadores de éxito realmente disponibles en las experiencias |
| `def _experience_success_score(experience)` | Extrae el valor de éxito de una experiencia usando los indicadores existentes |
| `def _calculate_consistency(scores)` | Consistencia de los resultados: 1.0 = resultados idénticos, 0.0 = máxima dispersión |
| `def evaluate_learning_strategy(learning_system, task_type, strategy, experiences)` | Evalúa una estrategia de aprendizaje usando únicamente evidencia disponible. |
| `def get_learning_evaluations(learning_system, task_type)` | Evalúa todas las combinaciones sistema/tarea/estrategia presentes en las experiencias |
| `def analyze_learning_patterns()` | Analiza patrones en las experiencias de aprendizaje para generar insights |
| `def _analyze_strategy_selection()` | Análisis de selección de estrategias |
| `def _analyze_parameter_adaptation()` | Análisis de adaptación de parámetros |
| `def _analyze_contextual_optimization()` | Análisis de optimización contextual |
| `def _analyze_learning_rate_adjustment()` | Análisis de ajuste de tasa de aprendizaje |
| `def _create_context_pattern(context)` | Crea un patrón de contexto para análisis |
| `def apply_meta_learning_insights(insights)` | Aplica insights de metaprendizaje a los sistemas de aprendizaje |
| `def get_security_limits()` | Límites de seguridad normalizados desde la configuración real |
| `def reset_auto_change_cycle()` | Reinicia el contador de cambios automáticos del ciclo actual |
| `def get_shared_components()` | Componentes cuyo motor es una instancia compartida (2.8.3.6) |
| `def _component_for_insight(insight)` | Componente afectado por un insight según su sistema de origen real |
| `def _record_security_decision(subject_type, subject_id, allowed, reason, detail)` | Registra una decisión de seguridad (2.8.3.7.3) |
| `def get_security_decisions()` | Decisiones de seguridad registradas |
| `def get_security_status()` | Estado de seguridad: límites, pendientes y decisiones por resultado |
| `def check_insight_security(insight)` | Decide si un insight puede aplicarse automáticamente. |
| `def check_meta_rule_security(meta_rule)` | Decide si una meta-regla puede aplicarse automáticamente |
| `def auto_apply_insights(insights)` | Aplica insights de forma automática y limitada (2.8.3.7.1). |
| `def auto_apply_meta_rules()` | Aplica las meta-reglas registradas de forma automática y limitada |
| `def _target_store(engine, attribute)` | Devuelve el almacén real de estrategias/parámetros de un motor de aprendizaje. |
| `def _apply_strategy_selection_insight(insight)` | Aplica insight de selección de estrategia |
| `def _apply_parameter_adaptation_insight(insight)` | Aplica insight de adaptación de parámetros |
| `def _apply_contextual_optimization_insight(insight)` | Aplica insight de optimización contextual |
| `def _apply_learning_rate_adjustment_insight(insight)` | Aplica insight de ajuste de tasa de aprendizaje |
| `def get_meta_learning_metrics()` | Obtiene métricas del sistema de metaprendizaje |
| `def _calculate_confidence_distribution()` | Calcula distribución de confianza de los insights |
| `def _get_system_coverage()` | Obtiene cobertura por sistema de aprendizaje |
| `def _calculate_learning_progress()` | Calcula progreso de aprendizaje por sistema |
| `def save_meta_learning_data()` | Guarda datos de metaprendizaje |
| `def load_meta_learning_data(file_path)` | Carga datos de metaprendizaje desde archivo |
| `def start_meta_learning_process()` | Inicia el proceso asíncrono de metaprendizaje |
| `def stop_meta_learning_process()` | Detiene el proceso asíncrono de metaprendizaje |
| `def _meta_learning_loop()` | Bucle principal de procesamiento de metaprendizaje |
| `def _process_single_experience(experience)` | Procesa una experiencia individual |
| `def validate_meta_learning_insights(insight_ids)` | Valida insights específicos |
| `def get_recommendations(system_type, task_type)` | Obtiene recomendaciones basadas en insights de metaprendizaje |
| `def get_learning_rules()` | Devuelve las ImprovementRule reales del SelfImprovementSystem |
| `def get_meta_rules()` | Devuelve las meta-reglas registradas |
| `def add_meta_rule(meta_rule)` | Registra una meta-regla si su contrato es válido y no está duplicada |
| `def _compare_metric(value, operator, threshold)` |  |
| `def _evaluate_meta_rule_condition(meta_rule, rule)` | Evalúa la condición de la meta-regla sobre el estado real de la regla |
| `def _capture_rule_state(rule)` |  |
| `def apply_meta_rule(meta_rule)` | Aplica una meta-regla sobre la ImprovementRule objetivo. |
| `def verify_meta_rule_application(application)` | Verifica que el estado real de la regla coincide con el estado aplicado |
| `def revert_meta_rule_application(application)` | Revierte una aplicación de meta-regla restaurando el estado previo completo. |
| `def get_meta_rule_history()` |  |
| `def _record_meta_rule(meta_rule, status, previous_state, new_state, message)` |  |
| `def _experience_to_dict(experience)` |  |
| `def _experience_from_dict(data)` |  |
| `def _meta_rule_to_dict(meta_rule)` |  |
| `def _meta_rule_from_dict(data)` |  |
| `def _meta_rule_application_to_dict(application)` |  |
| `def _restore_rule_state_dates(state)` | Devuelve el estado de una regla con last_execution novamente como datetime. |
| `def _meta_rule_application_from_dict(data)` |  |
| `def get_meta_learning_state()` | Estado serializable del metaprendizaje (experiencias, meta-reglas e historial) |
| `def save_meta_learning_state(file_path)` | Guarda el estado de metaprendizaje en un archivo estable. |
| `def load_meta_learning_state(file_path)` | Recupera el estado de metaprendizaje. |
| `def connect_component(component, engine)` | Conecta una instancia real de un motor de aprendizaje existente. |
| `def connect_adaptive_learning_engine(engine)` | Integra con AdaptiveLearningEngine (2.8.3.6.1) |
| `def connect_self_improvement_system(system)` | Integra con SelfImprovementSystem (2.8.3.6.2) |
| `def connect_contextual_adaptation_engine(engine)` | Integra con ContextualAdaptationEngine (2.8.3.6.3). |
| `def get_integration_status()` | Estado de integración y comprobación de motores duplicados (2.8.3.6.4). |

<a name="src-utils-metrics_collector-py"></a>
### `src/utils/metrics_collector.py` [592 líneas] — Sistema de recolección de métricas para JARVIS.

**Descripción:** Sistema de recolección de métricas para JARVIS.

**Importaciones:** 13.

`class MetricData`  (línea 22) — Datos de una métrica individual.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte los datos de la métrica a un diccionario. |
| `def from_dict(cls, data)` | Crea una instancia de MetricData desde un diccionario. |

`class MetricConfig`  (línea 54) — Configuración para la recolección de métricas.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte la configuración a un diccionario. |

`class MetricsCollector`  (línea 92) — Recolector de métricas para JARVIS.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config)` | Inicializa el recolector de métricas. |
| `def _initialize_database()` | Inicializa la base de datos SQLite para métricas. |
| `def _ensure_directories()` | Asegura que los directorios necesarios existan. |
| `def start_collection()` | Inicia la recolección continua de métricas. |
| `def stop_collection()` | Detiene la recolección de métricas. |
| `def _collection_loop()` | Bucle principal de recolección de métricas. |
| `def _collect_custom_metrics()` | Recolecta métricas personalizadas del sistema. |
| `def add_metric(metric_name, value, tags, metadata)` | Añade una métrica al buffer. |
| `def _flush_buffer()` | Vacía el buffer de métricas a la base de datos. |
| `def get_metrics(metric_name, start_time, end_time, limit, tags)` | Obtiene métricas de la base de datos. |
| `def get_metric_statistics(metric_name, start_time, end_time)` | Obtiene estadísticas de una métrica específica. |
| `def get_metric_names()` | Obtiene todos los nombres de métricas disponibles. |
| `def cleanup_old_metrics()` | Limpia métricas antiguas según la configuración de retención. |
| `def backup_metrics()` | Realiza una copia de seguridad de la base de datos de métricas. |
| `def export_metrics(filepath, metric_name, start_time, end_time)` | Exporta métricas a un archivo JSON. |
| `def get_collector_status()` | Obtiene el estado actual del recolector de métricas. |
| `def _get_total_metrics_count()` | Obtiene el total de métricas en la base de datos. |
| `def _get_last_cleanup_time()` | Obtiene la última fecha de limpieza. |
| `def clear_all_metrics()` | Elimina todas las métricas de la base de datos. |
| `def __enter__()` | Context manager entry. |
| `def __exit__(exc_type, exc_val, exc_tb)` | Context manager exit. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_metrics_collector()`  (L575) | Obtiene la instancia global del recolector de métricas. |
| `def start_metrics_collection()`  (L583) | Inicia la recolección de métricas globales. |
| `def stop_metrics_collection()`  (L589) | Detiene la recolección de métricas globales. |

<a name="src-utils-monitoring_dashboard-py"></a>
### `src/utils/monitoring_dashboard.py` [417 líneas] — Sistema de dashboard de monitoreo para JARVIS.

**Descripción:** Sistema de dashboard de monitoreo para JARVIS.

**Importaciones:** 10.

`class DashboardConfig`  (línea 23) — Configuración del dashboard de monitoreo.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte la configuración a un diccionario. |

`class DashboardData`  (línea 67) — Datos del dashboard en un punto en el tiempo.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convierte los datos del dashboard a un diccionario. |

`class MonitoringDashboard`  (línea 87) — Dashboard unificado de monitoreo para JARVIS.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config, performance_monitor, health_checker, metrics_collector)` | Inicializa el dashboard de monitoreo. |
| `def start_dashboard()` | Inicia el dashboard de monitoreo. |
| `def stop_dashboard()` | Detiene el dashboard de monitoreo. |
| `def _dashboard_loop()` | Bucle principal de actualización del dashboard. |
| `def _update_dashboard_data()` | Actualiza los datos del dashboard. |
| `def _get_current_performance_metrics()` | Obtiene las métricas de rendimiento actuales. |
| `def _get_current_health_status()` | Obtiene el estado de salud actual. |
| `def _get_recent_alerts()` | Obtiene alertas recientes. |
| `def _generate_system_summary(current_metrics, health_status, recent_alerts)` | Genera un resumen del estado del sistema. |
| `def get_dashboard_data()` | Obtiene los datos actuales del dashboard. |
| `def get_dashboard_history(limit)` | Obtiene el historial del dashboard. |
| `def add_update_callback(callback)` | Agrega un callback para recibir actualizaciones del dashboard. |
| `def remove_update_callback(callback)` | Remueve un callback de actualizaciones del dashboard. |
| `def export_dashboard_report(filepath, include_history)` | Exporta un reporte del dashboard a un archivo JSON. |
| `def get_system_health_score()` | Calcula un puntaje de salud del sistema (0-100). |
| `def get_critical_metrics()` | Obtiene métricas críticas que requieren atención. |
| `def get_unhealthy_components()` | Obtiene componentes no saludables. |
| `def clear_dashboard_history()` | Limpia el historial del dashboard. |
| `def __enter__()` | Context manager entry. |
| `def __exit__(exc_type, exc_val, exc_tb)` | Context manager exit. |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_monitoring_dashboard()`  (L400) | Obtiene la instancia global del dashboard de monitoreo. |
| `def start_monitoring_dashboard()`  (L408) | Inicia el dashboard de monitoreo global. |
| `def stop_monitoring_dashboard()`  (L414) | Detiene el dashboard de monitoreo global. |

<a name="src-utils-optimization_orchestrator-py"></a>
### `src/utils/optimization_orchestrator.py` [892 líneas] — Optimization Orchestrator v2.7.0

**Descripción:** Optimization Orchestrator v2.7.0

**Importaciones:** 25.

`class OrchestrationMode(Enum)`  (línea 33) — Modos de orquestación

_Sin métodos definidos en el AST._

`class OptimizationPriority(Enum)`  (línea 41) — Prioridades de optimización

_Sin métodos definidos en el AST._

`class OptimizationJob`  (línea 50) — Trabajo de optimización

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class OrchestrationMetrics`  (línea 68) — Métricas de orquestación

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class OptimizationOrchestrator`  (línea 81) — Orquestador de optimización que coordina todos los sistemas de optimización

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path)` |  |
| `def _load_config(config_path)` | Cargar configuración del orquestador |
| `def _initialize_resource_monitor()` | Inicializar monitor de recursos |
| `def _start_orchestration_loop()` | Iniciar bucle de orquestación |
| `def _orchestration_loop()` | Bucle principal de orquestación |
| `def _update_system_metrics()` | Actualizar métricas del sistema |
| `def _calculate_resource_utilization()` | Calcular utilización de recursos |
| `def _calculate_success_rate()` | Calcular tasa de éxito de optimización |
| `def _analyze_optimization_needs()` | Analizar necesidades de optimización |
| `def _estimate_resources(strategy)` | Estimar recursos requeridos para una estrategia |
| `def _add_optimization_job(job)` | Añadir trabajo de optimización |
| `def _coordinate_optimization_strategies()` | Coordinar estrategias de optimización |
| `def _group_compatible_jobs()` | Agrupar trabajos compatibles |
| `def _are_jobs_compatible(job1, job2)` | Verificar si dos trabajos son compatibles |
| `def _execute_sequential(jobs)` | Ejecutar trabajos secuencialmente |
| `def _execute_parallel(jobs)` | Ejecutar trabajos en paralelo |
| `def _execute_coordinated(jobs)` | Ejecutar trabajos coordinados |
| `def _execute_optimized(jobs)` | Ejecutar trabajos optimizados |
| `def _process_optimization_jobs()` | Procesar trabajos de optimización |
| `def _execute_single_job(job)` | Ejecutar un trabajo de optimización individual |
| `def _execute_coordinated_job(job, resource_locks)` | Ejecutar trabajo coordinado con control de recursos |
| `def _execute_strategy(strategy, job)` | Ejecutar una estrategia de optimización |
| `def _calculate_job_efficiency(job)` | Calcular eficiencia esperada de un trabajo |
| `def _calculate_job_improvement(initial_metrics, final_metrics)` | Calcular mejora de un trabajo |
| `def _monitor_job_progress()` | Monitorear progreso de trabajos |
| `def _adapt_orchestration_mode()` | Adaptar modo de orquestación según condiciones del sistema |
| `def _optimize_orchestration_mode()` | Optimizar modo de orquestación |
| `def _calculate_mode_performance(mode)` | Calcular rendimiento de un modo de orquestación |
| `def get_orchestration_status()` | Obtener estado de orquestación |
| `def _calculate_average_job_duration()` | Calcular duración promedio de trabajos |
| `def add_custom_optimization_job(job)` | Añadir trabajo de optimización personalizado |
| `def get_job_status(job_id)` | Obtener estado de un trabajo específico |
| `def cancel_job(job_id)` | Cancelar un trabajo |
| `def export_orchestration_report(filepath)` | Exportar reporte de orquestación |
| `def stop_orchestration()` | Detener orquestación |
| `def start_orchestration()` | Iniciar orquestación |
| `def __del__()` | Destructor |

<a name="src-utils-pattern_analyzer-py"></a>
### `src/utils/pattern_analyzer.py` [650 líneas] — Analizador avanzado de patrones para Jarvis con machine learning y detección de anomalías.

**Descripción:** Analizador avanzado de patrones para Jarvis con machine learning y detección de anomalías.

**Importaciones:** 16.

`class PatternType(Enum)`  (línea 23) — Tipos de patrones detectables.

_Sin métodos definidos en el AST._

`class PatternSeverity(Enum)`  (línea 36) — Severidad de patrones.

_Sin métodos definidos en el AST._

`class Pattern`  (línea 45) — Estructura de patrón detectado.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class TimeSeriesAnalyzer`  (línea 68) — Analizador de series temporales para detección de patrones.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(window_size)` |  |
| `def add_data_point(metric_name, value, timestamp)` | Añadir punto de datos a la serie temporal. |
| `def _train_model()` | Entrenar modelo de detección de anomalías. |
| `def detect_anomalies(metric_name, window_size)` | Detectar anomalías en una serie temporal. |

`class PatternDetector`  (línea 159) — Detector de patrones con múltiples algoritmos.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def analyze_logs(logs)` | Analizar logs y detectar patrones. |
| `def _detect_error_spikes(logs)` | Detectar picos de errores. |
| `def _detect_performance_degradation(logs)` | Detectar degradación de rendimiento. |
| `def _detect_anomalies(logs)` | Detectar anomalías usando series temporales. |
| `def _detect_trends(logs)` | Detectar tendencias en los logs. |
| `def _detect_cycles(logs)` | Detectar patrones cíclicos. |
| `def _detect_periodicity(data)` | Detectar periodicidad en datos usando métodos simples. |
| `def _detect_correlations(logs)` | Detectar correlaciones entre diferentes tipos de logs. |
| `def _detect_bursts(logs)` | Detectar bursts de actividad. |
| `def get_patterns_by_type(pattern_type, limit)` | Obtener patrones por tipo. |
| `def get_active_patterns()` | Obtener patrones activos. |
| `def acknowledge_pattern(pattern_id)` | Marcar patrón como reconocido. |
| `def get_pattern_statistics()` | Obtener estadísticas de patrones. |

`class PatternAnalyzer`  (línea 606) — Wrapper para PatternDetector que proporciona la interfaz esperada.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def get_pattern_analysis()` | Obtener análisis completo de patrones. |
| `def analyze_logs(logs)` | Analizar logs y detectar patrones. |
| `def get_patterns_by_type(pattern_type, limit)` | Obtener patrones por tipo. |
| `def get_active_patterns()` | Obtener patrones activos. |
| `def acknowledge_pattern(pattern_id)` | Marcar patrón como reconocido. |
| `def get_pattern_statistics()` | Obtener estadísticas de patrones. |

<a name="src-utils-performance_monitor-py"></a>
### `src/utils/performance_monitor.py` [856 líneas] — Monitor avanzado de rendimiento para Jarvis con análisis predictivo y alertas inteligentes.

**Descripción:** Monitor avanzado de rendimiento para Jarvis con análisis predictivo y alertas inteligentes.

**Importaciones:** 18.

`class MetricType(Enum)`  (línea 25) — Tipos de métricas de rendimiento.

_Sin métodos definidos en el AST._

`class AlertSeverity(Enum)`  (línea 37) — Severidad de alertas.

_Sin métodos definidos en el AST._

`class PerformanceMetric`  (línea 46) — Métrica de rendimiento.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class PerformanceAlert`  (línea 66) — Alerta de rendimiento.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def to_dict()` | Convertir a diccionario. |

`class PerformanceCollector`  (línea 87) — Colector de métricas de rendimiento.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(collection_interval, max_history)` |  |
| `def start_collection()` | Iniciar recolección de métricas. |
| `def stop_collection()` | Detener recolección de métricas. |
| `def _collection_loop()` | Bucle de recolección de métricas. |
| `def _collect_system_metrics()` | Recolectar métricas del sistema. |
| `def _collect_process_metrics()` | Recolectar métricas de procesos. |
| `def _collect_network_metrics()` | Recolectar métricas de red. |
| `def _collect_disk_metrics()` | Recolectar métricas de disco. |
| `def _add_metric(name, value, unit, timestamp, tags)` | Añadir métrica al colector. |
| `def _get_metric_type(name)` | Determinar el tipo de métrica por nombre. |
| `def get_metric_history(name, hours)` | Obtener historial de una métrica. |
| `def get_latest_metrics()` | Obtener las métricas más recientes. |
| `def get_metric_statistics(name, hours)` | Obtener estadísticas de una métrica. |

`class PerformanceAnalyzer`  (línea 313) — Analizador de rendimiento con detección de anomalías.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(window_size)` |  |
| `def train_anomaly_detector(metric_name, history)` | Entrenar detector de anomalías para una métrica. |
| `def detect_anomalies(metric_name, current_value)` | Detectar anomalías en una métrica. |
| `def analyze_trends(metric_name, history)` | Analizar tendencias en una métrica. |

`class PerformanceMonitor`  (línea 408) — Monitor de rendimiento principal.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def _create_database()` | Crear base de datos para monitor de rendimiento. |
| `def _load_default_alert_rules()` | Cargar reglas de alerta por defecto. |
| `def start_monitoring()` | Iniciar monitoreo de rendimiento. |
| `def stop_monitoring()` | Detener monitoreo de rendimiento. |
| `def _monitoring_loop()` | Bucle principal de monitoreo. |
| `def _alert_processing_loop()` | Bucle de procesamiento de alertas. |
| `def _evaluate_alert_condition(rule, value)` | Evaluar si se cumple una condición de alerta. |
| `def _create_alert(rule, metric)` | Crear alerta basada en una regla. |
| `def _process_alert(alert)` | Procesar alerta. |
| `def _generate_corrective_actions(alert)` | Generar acciones correctivas basadas en la alerta. |
| `def _train_anomaly_detectors()` | Entrenar detectores de anomalías. |
| `def _save_alert(alert)` | Guardar alerta en base de datos. |
| `def _save_alert_rule(rule)` | Guardar regla de alerta en base de datos. |
| `def add_alert_rule(rule)` | Añadir regla de alerta. |
| `def remove_alert_rule(rule_id)` | Eliminar regla de alerta. |
| `def get_alerts(severity, acknowledged, limit)` | Obtener alertas. |
| `def acknowledge_alert(alert_id)` | Marcar alerta como reconocida. |
| `def resolve_alert(alert_id)` | Marcar alerta como resuelta. |
| `def get_performance_summary()` | Obtener resumen del rendimiento. |
| `def export_performance_data(start_time, end_time, format)` | Exportar datos de rendimiento. |

`class AlertRule`  (línea 838) — Regla de alerta.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def __post_init__()` |  |

<a name="src-utils-performance_optimizer-py"></a>
### `src/utils/performance_optimizer.py` [1099 líneas] — Performance Optimizer v2.7.0

**Descripción:** Performance Optimizer v2.7.0

**Importaciones:** 25.

`class OptimizationStrategy(Enum)`  (línea 33) — Estrategias de optimización disponibles

_Sin métodos definidos en el AST._

`class OptimizationLevel(Enum)`  (línea 46) — Niveles de optimización

_Sin métodos definidos en el AST._

`class OptimizationMetrics`  (línea 54) — Métricas de optimización

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class OptimizationAction`  (línea 69) — Acción de optimización

**Decoradores:** `@dataclass`, `@dataclass`

_Sin métodos definidos en el AST._

`class PerformanceOptimizer`  (línea 88) — Optimizador de rendimiento con machine learning y optimización predictiva

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path)` |  |
| `def _load_config(config_path)` | Cargar configuración del optimizador |
| `def _initialize_models()` | Inicializar modelos de machine learning para optimización |
| `def _load_trained_models()` | Cargar modelos pre-entrenados |
| `def _save_trained_models()` | Guardar modelos entrenados |
| `def _start_optimization_loop()` | Iniciar bucle de optimización asíncrono |
| `def _optimization_loop()` | Bucle principal de optimización |
| `def _analyze_system_performance()` | Analizar rendimiento del sistema |
| `def _calculate_efficiency_score(metrics)` | Calcular puntuación de eficiencia del sistema |
| `def _analyze_performance_trends()` | Analizar tendencias de rendimiento |
| `def _identify_optimization_opportunities()` | Identificar oportunidades de optimización |
| `def _predict_optimization_opportunities()` | Predecir oportunidades de optimización usando ML |
| `def _prepare_features_for_prediction()` | Preparar características para predicción ML |
| `def _create_cpu_optimization_action()` | Crear acción de optimización de CPU |
| `def _create_memory_optimization_action()` | Crear acción de optimización de memoria |
| `def _create_disk_optimization_action()` | Crear acción de optimización de disco |
| `def _create_response_time_optimization_action()` | Crear acción de optimización de tiempo de respuesta |
| `def _create_error_rate_optimization_action()` | Crear acción de optimización de tasa de errores |
| `def _create_ml_optimization_action(metric, prediction, confidence)` | Crear acción de optimización basada en ML |
| `def _execute_optimization_actions()` | Ejecutar acciones de optimización |
| `def _execute_single_action(action)` | Ejecutar una acción de optimización individual |
| `def _execute_optimization_command(command)` | Ejecutar comando de optimización |
| `def _calculate_improvement(pre_metrics, post_metrics)` | Calcular mejora porcentual |
| `def _calculate_actual_improvement(action)` | Calcular mejora real de una acción |
| `def _update_ml_models(action, improvement)` | Actualizar modelos ML con resultados de optimización |
| `def get_optimization_status()` | Obtener estado actual de optimización |
| `def get_optimization_history(limit)` | Obtener historial de optimización |
| `def get_current_actions()` | Obtener acciones en curso |
| `def add_custom_optimization_action(action)` | Añadir acción de optimización personalizada |
| `def stop_optimization()` | Detener optimización |
| `def start_optimization()` | Iniciar optimización |
| `def optimize_system(strategy, level)` | Optimizar sistema manualmente |
| `def get_optimization_recommendations()` | Obtener recomendaciones de optimización |
| `def export_optimization_report(filepath)` | Exportar reporte de optimización |
| `def optimize_resources(optimization_request)` | Optimizar recursos basado en solicitud contextual. |
| `def __del__()` | Destructor |

<a name="src-utils-recovery_strategies-py"></a>
### `src/utils/recovery_strategies.py` [514 líneas] — Recovery Strategies for JARVIS System

**Descripción:** Recovery Strategies for JARVIS System

**Importaciones:** 13.

`class RecoveryType(Enum)`  (línea 20) — Types of recovery operations

_Sin métodos definidos en el AST._

`class RecoveryStatus(Enum)`  (línea 26) — Recovery operation status

_Sin métodos definidos en el AST._

`class RecoveryAction`  (línea 34) — Base recovery action

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(name, description, recovery_type)` |  |
| `def execute()` | Execute the recovery action |
| `def _do_execute()` | Override this method in subclasses |
| `def cancel()` | Cancel the recovery action |
| `def get_duration()` | Get execution duration in seconds |

`class DatabaseRecoveryAction(RecoveryAction)`  (línea 80) — Database recovery action

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path, backup_path)` |  |
| `def _do_execute()` | Execute database recovery |
| `def _repair_database()` | Attempt to repair corrupted database |

`class FilesystemRecoveryAction(RecoveryAction)`  (línea 119) — Filesystem recovery action

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(file_path, backup_path)` |  |
| `def _do_execute()` | Execute filesystem recovery |

`class ProcessRecoveryAction(RecoveryAction)`  (línea 142) — Process recovery action

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(process_name, command)` |  |
| `def _do_execute()` | Execute process recovery |

`class MemoryRecoveryAction(RecoveryAction)`  (línea 165) — Memory recovery action

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(process_id)` |  |
| `def _do_execute()` | Execute memory recovery |

`class NetworkRecoveryAction(RecoveryAction)`  (línea 193) — Network recovery action

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(interface)` |  |
| `def _do_execute()` | Execute network recovery |

`class RecoveryManager`  (línea 234) — Main recovery management system

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(db_path)` |  |
| `def _init_database()` | Initialize recovery management database |
| `def register_recovery_action(action)` | Register a recovery action |
| `def execute_recovery(action_name, component, error_type, additional_data)` | Execute a recovery action |
| `def _log_recovery_history(action_name, component, error_type, success, additional_data)` | Log recovery history |
| `def get_recovery_history(days)` | Get recovery history for specified days |
| `def get_recovery_statistics(days)` | Get recovery statistics |
| `def get_active_recoveries()` | Get list of active recoveries |
| `def cancel_recovery(action_name)` | Cancel an active recovery |
| `def get_available_actions()` | Get list of available recovery actions |
| `def cleanup_old_history(days)` | Clean up old recovery history |
| `def setup_default_actions()` | Setup default recovery actions |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def create_database_recovery_action(db_path, backup_path)`  (L487) | Create a database recovery action |
| `def create_filesystem_recovery_action(file_path, backup_path)`  (L491) | Create a filesystem recovery action |
| `def create_process_recovery_action(process_name, command)`  (L495) | Create a process recovery action |
| `def create_memory_recovery_action(process_id)`  (L499) | Create a memory recovery action |
| `def get_recovery_manager()`  (L504) | Get a singleton instance of RecoveryManager |
| `def create_network_recovery_action(interface)`  (L512) | Create a network recovery action |

<a name="src-utils-screen_manager-py"></a>
### `src/utils/screen_manager.py` [1958 líneas] — Gestor unificado de pantallas y configuración del sistema Jarvis.

**Descripción:** Gestor unificado de pantallas y configuración del sistema Jarvis.

**Importaciones:** 16.

`class ScreenSetupType(Enum)`  (línea 88)

_Sin métodos definidos en el AST._

`class MonitorInfo`  (línea 97) — Información física/lógica de un monitor en el escritorio virtual.

**Decoradores:** `@dataclass`

Métodos:

| Firma | Docstring |
|---|---|
| `def center_x()` |  |
| `def center_y()` |  |
| `def center()` |  |
| `def screen_key()` |  |
| `def contains_point(x, y)` |  |
| `def contains_window(window)` |  |
| `def to_dict()` |  |

`class ScreenManager`  (línea 180) — Gestor centralizado de topología, ventanas y capturas.

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__()` |  |
| `def _make_dpi_aware()` |  |
| `def _get_monitor_dpi(handle)` |  |
| `def _load_monitors_from_windows()` |  |
| `def _load_monitors_from_config()` |  |
| `def refresh_monitors()` |  |
| `def _calculate_virtual_bounds()` |  |
| `def _analyze_setup()` |  |
| `def get_monitor(monitor_num)` |  |
| `def get_primary_monitor()` |  |
| `def get_monitor_by_point(x, y)` |  |
| `def _get_window_geometry(window)` | Obtiene la geometría real de una ventana Win32. |
| `def get_monitor_for_window(window)` | Obtiene el monitor físico de una ventana, incluso minimizada. |
| `def _get_window_handle(window)` |  |
| `def get_foreground_window()` |  |
| `def get_foreground_monitor()` |  |
| `def get_active_monitor()` |  |
| `def get_alternate_monitor(monitor_num)` |  |
| `def _get_window_class(hwnd)` |  |
| `def _get_window_process_id(window)` |  |
| `def _get_window_process_name(window)` |  |
| `def _is_chrome_window(window)` | Identifica Chrome por su proceso real, no por Chrome_WidgetWin. |
| `def _window_has_valid_size(window)` |  |
| `def _window_is_visible(window)` | Comprueba visibilidad real mediante Win32 cuando es posible. |
| `def _window_is_minimized(window)` | Comprueba si una ventana está minimizada según Windows. |
| `def _restore_and_maximize_window(window)` | Restaura y maximiza temporalmente una ventana existente. |
| `def get_chrome_windows()` | Enumera ventanas reales de Chrome evitando depender del orden que |
| `def get_chrome_window_on_monitor(monitor_num, prefer_foreground)` |  |
| `def get_chrome_monitor(prefer_foreground)` | Detecta el monitor real de Chrome. |
| `def _get_window_area(window)` | Devuelve el área aproximada de una ventana en píxeles. |
| `def get_calibration_monitor()` |  |
| `def is_window_minimized(window)` | Indica si una ventana está minimizada según Win32. |
| `def prepare_window_for_calibration(window)` | Restaura/maximiza cualquier ventana y devuelve su monitor real. |
| `def move_window_to_monitor(window_title, monitor_num)` |  |
| `def _find_chrome_executable()` |  |
| `def _snapshot_chrome_handles()` |  |
| `def _find_new_chrome_window(previous_handles, monitor, timeout)` |  |
| `def _activate_window(window)` |  |
| `def _launch_chrome_for_calibration(monitor)` |  |
| `def open_chrome_calibration_tab(monitor_num)` |  |
| `def open_chrome_on_monitor(monitor_num)` |  |
| `def capture_monitor(monitor_num)` | Captura exactamente el rectángulo físico del monitor. |
| `def close_chrome()` | Cierra Chrome como acción explícita del usuario. |
| `def move_window_to_screen(window_title, screen_num)` |  |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def get_screen_manager()`  (L1946) |  |
| `def get_monitor_info(monitor_num)`  (L1953) |  |
| `def get_monitor_setup()`  (L1957) |  |

<a name="src-utils-self_improvement_system-py"></a>
### `src/utils/self_improvement_system.py` [1261 líneas] — Self Improvement System v2.7.0

**Descripción:** Self Improvement System v2.7.0

**Importaciones:** 27.

`class LearningMode(Enum)`  (línea 35) — Modos de aprendizaje del sistema

_Sin métodos definidos en el AST._

`class ImprovementType(Enum)`  (línea 43) — Tipos de mejora

_Sin métodos definidos en el AST._

`class LearningSession`  (línea 55) — Sesión de aprendizaje

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class ImprovementRule`  (línea 71) — Regla de mejora

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class KnowledgeGraph`  (línea 86) — Grafo de conocimiento

**Decoradores:** `@dataclass`

_Sin métodos definidos en el AST._

`class SelfImprovementSystem`  (línea 95) — Sistema de automejora con aprendizaje continuo y optimización adaptativa

Métodos:

| Firma | Docstring |
|---|---|
| `def __init__(config_path)` |  |
| `def _load_config(config_path)` | Cargar configuración del sistema de automejora |
| `def _initialize_learning_models()` | Inicializar modelos de aprendizaje |
| `def _load_trained_learning_models()` | Cargar modelos pre-entrenados |
| `def _save_trained_learning_models()` | Guardar modelos entrenados |
| `def _initialize_improvement_rules()` | Inicializar reglas de mejora |
| `def _load_custom_rules()` | Cargar reglas personalizadas |
| `def _save_custom_rules()` | Guardar reglas personalizadas |
| `def _start_learning_loop()` | Iniciar bucle de aprendizaje |
| `def _learning_loop()` | Bucle principal de aprendizaje |
| `def _perform_passive_learning()` | Realizar aprendizaje pasivo |
| `def _collect_system_data()` | Recopilar datos del sistema para aprendizaje |
| `def _as_dict(value)` | Convertir cualquier valor a dict de forma segura. |
| `def _flatten_performance(status)` | Aplanar el estado del optimizador a métricas planas. |
| `def _flatten_patterns(analysis)` | Aplanar el análisis de patrones a métricas planas. |
| `def _flatten_analytics(summary)` | Aplanar el resumen analítico a contadores planos. |
| `def _summarize_predictions(predictions)` | Convertir una lista de Prediction en métricas agregadas. |
| `def _calculate_system_load()` | Calcular carga del sistema |
| `def _extract_learning_features(system_data)` | Extraer características para aprendizaje |
| `def _update_learning_models(features, system_data)` | Actualizar modelos de aprendizaje |
| `def _determine_learning_labels(system_data)` | Determinar etiquetas para aprendizaje |
| `def _identify_improvement_opportunities(system_data)` | Identificar oportunidades de mejora |
| `def _execute_improvement_rules()` | Ejecutar reglas de mejora |
| `def _evaluate_rule_condition(rule)` | Evaluar condición de una regla |
| `def _execute_rule_action(rule)` | Ejecutar acción de una regla |
| `def _analyze_learning_patterns()` | Analizar patrones de aprendizaje |
| `def _update_knowledge_graph()` | Actualizar grafo de conocimiento |
| `def _calculate_node_confidence(properties)` | Calcular confianza de un nodo |
| `def _save_knowledge_graph()` | Guardar grafo de conocimiento |
| `def _start_learning_session(mode)` | Iniciar sesión de aprendizaje |
| `def _end_learning_session(session)` | Finalizar sesión de aprendizaje |
| `def get_learning_status()` | Obtener estado actual de aprendizaje |
| `def get_learning_history(limit)` | Obtener historial de aprendizaje |
| `def add_improvement_rule(rule)` | Añadir regla de mejora personalizada |
| `def remove_improvement_rule(rule_id)` | Eliminar regla de mejora |
| `def enable_learning_mode(mode)` | Habilitar modo de aprendizaje |
| `def disable_learning_mode(mode)` | Deshabilitar modo de aprendizaje |
| `def perform_active_learning()` | Realizar aprendizaje activo |
| `def _design_experiments()` | Diseñar experimentos para aprendizaje activo |
| `def _run_experiment(experiment)` | Ejecutar experimento |
| `def _process_experiment_result(result)` | Procesar resultado de experimento |
| `def export_learning_report(filepath)` | Exportar reporte de aprendizaje |
| `def stop_learning()` | Detener aprendizaje |
| `def start_learning()` | Iniciar aprendizaje |
| `def __del__()` | Destructor |

<a name="src-utils-ui_element_model-py"></a>
### `src/utils/ui_element_model.py` [181 líneas] — Modelo canónico de elemento de interfaz de usuario (UI Element).

**Descripción:** Modelo canónico de elemento de interfaz de usuario (UI Element).

**Importaciones:** 4.

`class UIElementData(BaseModel)`  (línea 45) — Representación canónica de un elemento de interfaz de usuario.

Métodos:

| Firma | Docstring |
|---|---|
| `def is_calibrated()` | Indica si el elemento dispone de coordenadas utilizables. |
| `def _coordinates_calibrated(coordinates)` |  |
| `def has_valid_geometry()` | Devuelve ``True`` si el elemento expone geometría usable. |
| `def matches_name(name)` | Comprueba si el elemento corresponde a ``name`` (por nombre o texto). |
| `def to_dict()` | Devuelve un diccionario serializable con la forma canónica. |
| `def from_dict(cls, data)` | Construye un elemento canónico filtrando claves desconocidas. |
| `def from_compact_dict(cls, data)` | Construye desde la respuesta compacta del modelo de visión. |
| `def normalize_name(name)` | Normaliza un nombre a clave canónica (uso interno/planificador). |

Funciones a nivel módulo:

| Firma | Docstring |
|---|---|
| `def _is_number(value)`  (L30) | Devuelve ``True`` solo para valores numéricos reales (no bool). |
| `def _as_int_list(value, expected_len)`  (L35) | Normaliza ``value`` a una lista de enteros con longitud exacta. |

## 📂 Archivos de configuración y datos

Resumen de artefactos persistentes (consumidos por `utils/config.py` y `memory/storage.py`):

| Ruta | Rol |
|---|---|
| `config/config.json` | Configuración maestra: `project`, `llm`, `memory`, `execution`, `keyboard`, `visual`, `prediction`, `logging`. Accedida vía `get_memory_config()`/`get_timeout_config()`/`get_keyboard_config()`/`get_visual_config()`/`get_predictive_config()`. |
| `config/command_aliases.json` | Aliases estáticos `intención → comando` (FASE 16). |
| `data/knowledge/{entities,applications,capabilities}.json` | Conocimiento de dominio estático (FASE 5), cargado por `DomainMemory`. |
| `data/{entities,applications,capabilities,knowledge_graph,contextual_knowledge_base}.json` | Versiones de datos usadas por `MemoryManager`/`EntityResolver`. |
| `data/conversational_memory.json` | Histórico de chat con metadatos de planificación. |
| `data/prediction_memory.json` | `PredictionResult`s y estadísticas de uso (FASE 15/18). |
| `data/jarvis_memory.json` | Memoria general de largo plazo. |
| `data/jarvis_learned_aliases.json` | Aliases aprendidos en runtime. |
| `data/macros_coords.json` | Coordenadas UI calibradas (FASE 13), leídas por `CoordinateManager`. |
| `data/goal_adaptation_*.json` | Feedback/resultados de adaptación de objetivos. |
| `data/improvement_rules.json` | Reglas de mejora inferidas. |
| `data/domain_knowledge_persistence.json` | Conocimiento de dominio persistido (aplicado por `conversation.py`). |
| `data/memory/*` | Nueva memoria de dominio: `world_state`, `plans`, `executions`, `entities`, `relationships`, `user_preferences`, `learning_stats`, `predictions`, `domain_knowledge`, `conversational_memory`. |
| `data/memoria/*_analysis.json` | Snapshots de autorreferencia por submódulo (consumidos por el arquitecto). |
| `data/meta_learning_exports/*.json` | Puntos de entrenamiento de meta-aprendizaje (timestampados, FASE 18). |
| `data/temp/*` | Scratch y harness de tests de un solo objetivo. |
| `data/{integrity_report,data_integrative_report,cleaning_report}.txt` | Reportes de higiene de datos. |

| Enum `MemoryType` | Variantes: `CONVERSATIONAL`, `ENTITIES`, `RELATIONSHIPS`, `PREDICTIONS`, `EXECUTIONS`, `PLANS`, `WORLD_STATE`, `USER_PREFERENCES`, `LEARNING_STATS`, `APPLICATIONS`, `CAPABILITIES`, `DOMAIN_KNOWLEDGE`, `META_LEARNING`, `CONTEXTUAL_KNOWLEDGE_BASE`. |

## 🧪 Cobertura de inspección

Este documento se genera a partir del AST real (signatures + docstrings) de los 94 archivos fuente, complementado con inspección de implementación en los módulos centrales. Cuando un `docstring` del código es escaso, la descripción proviene del módulo que lo consume y no inventa comportamiento.

---
*Generado desde `data/temp/_ast_dump.txt` (extracción AST) — no contiene inferencias de comportamiento no verificado.*
