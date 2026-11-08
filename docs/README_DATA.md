# 📁 README_DATA — Documentación de los ficheros de `data/`

> **Proyecto:** JARVIS — Asistente de IA (Backend Python)  
> **Ruta base:** `c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS\data\`  
> **Generado a partir del análisis estático de `src/`**  
> **Prohibido crear scripts que escriban este fichero automáticamente.**

---

## Índice

1. [Descripción general](#descripción-general)
2. [Mapa de datos por archivo](#mapa-de-datos-por-archivo)
3. [Detalle por fichero (raíz de `data/`](#detalle-por-fichero-raíz-de-data)
4. [Subdirectorio `data/knowledge/`](#subdirectorio-dataknowledge)
5. [Subdirectorio `data/memory/`](#subdirectorio-datamemory)
6. [Flujo de datos: quién lee, quién escribe, a dónde se envía](#flujo-de-datos)
7. [Formato de los ficheros](#formato-de-los-ficheros)
8. [Estado de integridad conocido](#estado-de-integridad-conocido)

---

## 1. Descripción general

El directorio `data/` almacena todo el estado persistente del sistema JARVIS: memoria conversacional, conocimiento de dominio, calibración de UI (coordenadas), preferencias de usuario, reglas de mejora, feedback de adaptación de objetivos, estadísticas de predicción y logs de diagnóstico.

Los ficheros se consumen principalmente a través de:
- **`src/memory/storage.py`** — `MemoryManager` / `JSONStorage` (almacenamiento genérico JSON por tipos de memoria).
- **`src/memory/conversation.py`** — `ConversationMemory` / `DomainMemory` (memoria conversacional, aliases, entidades, preferencias).
- **`src/memory/prediction.py`** — `EnhancedPredictionMemory` (memoria predictiva de comandos).
- **`src/hands/coordinate_manager.py`** — `CoordinateManager` (calibración de coordenadas UI desde `macros_coords.json`).
- **`src/hands/calibration_manager.py`** — `CalibrationManager` (persistencia de calibración en `macros_coords.json`).
- **`src/brain/llm.py`** — `Brain` (interpreta intenciones, guarda memoria conversacional vía `memory_manager`).
- **`src/hands/action_registry.py`** — Registro de acciones, graba estadísticas de predicción.
- **`src/utils/contextual_adaptation_engine.py`** — Motor de adaptación contextual (usa `contextual_knowledge_base.json`, `goal_adaptation_*.json`, `improvement_rules.json`).
- **`src/utils/self_improvement_system.py`** — Sistema de auto-mejora (usa `knowledge_graph.json`, `improvement_rules.json`).

---

## 2. Mapa de datos por archivo

| Fichero | Formato | ¿Quién lo lee? | ¿Quién lo escribe? | ¿Dónde se envía / se usa? |
|---------|---------|----------------|--------------------|---------------------------|
| `conversational_memory.json` | JSON (array) | `ConversationMemory`, `Brain.llm`, `MemoryManager` | `MemoryManager.save()`, `add_conversational_memory()` | Memoria conversacional persistente del sistema |
| `jarvis_memory.json` | JSON (array) | `ConversationMemory` (chat_memory_file), `Brain.llm` | `MemoryManager` | Memoria conversacional legacy (formato simple role/content) |
| `prediction_memory.json` | JSON (objeto) | `EnhancedPredictionMemory` | `action_registry._record_prediction()` | Estadísticas de uso de comandos para predicción |
| `user_preferences.json` | JSON (objeto) | `DomainMemory.load_user_preferences()`, `MemoryManager` | `DomainMemory.save_user_preferences()` | Preferencias de usuario (apps preferidas, entidades, UI) |
| `macros_coords.json` | JSON (objeto) | `CoordinateManager`, `CalibrationManager` | `CalibrationManager` (guarda calibraciones) | Coordenadas calibradas de elementos UI por pantalla (sN) |
| `knowledge/entities.json` | JSON (array) | `DomainMemory.load_domain_knowledge()` | (estático, inicializado por limpieza) | Entidades de dominio: streamers y aplicaciones |
| `knowledge/applications.json` | JSON (objeto) | `DomainMemory.load_domain_knowledge()` | (estático) | Conocimiento de aplicaciones: capacidades, estados, elementos UI |
| `knowledge/capabilities.json` | JSON (objeto) | `DomainMemory.load_domain_knowledge()` | (estático) | Definiciones de capacidades por categoría (sistema, browser, media, dev, streaming) |
| `contextual_knowledge_base.json` | JSON (objeto) | `contextual_adaptation_engine.py` | `contextual_adaptation_engine.py` | Patrones de contexto, estrategias de adaptación, feedback de adaptación de objetivos |
| `knowledge_graph.json` | JSON (array) | `self_improvement_system.py` | `self_improvement_system.py` | Nodos del grafo de conocimiento (estado del sistema) |
| `learning_config.json` | JSON (objeto) | Sistema de configuración de aprendizaje | (estático) | Configuración del sistema de aprendizaje (tasas, umbrales, exportación) |
| `improvement_rules.json` | JSON (array) | `self_improvement_system.py` (rule_engine_path) | `self_improvement_system.py` | Reglas de mejora/optimización del sistema (CPU, memoria, errores, etc.) |
| `goal_adaptation_feedback.json` | JSON (objeto) | `contextual_adaptation_engine.py` | `contextual_adaptation_engine.py` | Feedback de adaptación de objetivos (métricas de rendimiento) |
| `goal_adaptation_learning_results.json` | JSON (objeto) | `contextual_adaptation_engine.py` | `contextual_adaptation_engine.py` | Resultados de aprendizaje de adaptación de objetivos |
| `system_inventory.sqlite3` | SQLite | `SystemInventoryStorage` (`src/hands/system_inventory_storage.py`) | `SystemInventoryStorage` (crea e inicializa `data/system_inventory.sqlite3`) | Índice canonico persistente del inventario de archivos del sistema (maquinas, volumenes, ejecuciones de escaneo, entradas de archivo y candidatos de aplicacion). |
| `system_inventory_manifest.json` | JSON (objeto) | `SystemInventoryStorage` (`src/hands/system_inventory_storage.py`) | `SystemInventoryStorage.write_manifest()` (llamado tras registrar volumenes y finalizar escaneos) | Manifiesto/resumen JSON ligero del inventario: version del esquema, identificador del equipo, volumenes descubiertos y ultimo escaneo. No almacena el listado entero de archivos (eso reside en SQLite). Se mantiene coherente con la base de datos SQLite. |

---

## 3. Detalle por fichero (raíz de `data/`)

### 3.1 `conversational_memory.json`
- **Formato:** JSON array de objetos `ConversationalMemory`.
- **Campos por entrada:** `id`, `message`, `response`, `timestamp`, `context` (dict o null), `intent`, `entities` (array), `confidence`, `execution_time`, `success`.
- **Quién lo lee:** `src/memory/storage.py` (`JSONStorage` → `MemoryType.CONVERSATIONAL`), `src/memory/conversation.py` (`ConversationMemory.chat_storage`), `src/brain/llm.py` (`memory_manager.get_conversational_memory()`, `add_conversational_memory()`).
- **Quién lo escribe:** `MemoryManager.save()` vía `JSONStorage.save()`; `htn_integration.py` (`_register_goal_memory` → `add_conversational_memory`); `llm.py` (`_store_conversation_memory`).
- **Tamaño:** ~10.442 líneas (miles de entradas).
- **Ejemplo de entrada:**
  ```json
  {
    "id": "conv_1790589308.616109",
    "message": "¡Suscríbete al canal!",
    "response": "Objetivo creado: Suscribirse al canal de Nissaxter",
    "timestamp": "2026-09-28T11:55:08.616115",
    "context": null,
    "intent": "navigate_stream",
    "entities": [],
    "confidence": 1.0,
    "execution_time": 0.0,
    "success": null
  }
  ```

### 3.2 `jarvis_memory.json`
- **Formato:** JSON array de objetos `{role, content}`.
- **Quién lo lee:** `src/memory/conversation.py` (`ConversationMemory` usa `config.chat_memory_file = "data/jarvis_memory.json"`), `src/brain/llm.py`.
- **Quién lo escribe:** `MemoryManager` (ciclo de conversación principal en `main.py` → `jarvis_memory.save_conversation()`).
- **Tamaño:** 106 líneas (26 entradas).
- **Contenido:** Diálogos legacy de ejemplo (suscribirse, abrir Chrome, YouTube, calibrar aplicaciones, etc.). Algunas respuestas son acciones JSON (`{ "action": "abrir_chrome", "parameters": {} }`) y otras son texto natural o mensajes de error (`❌ Acción no válida...`).
- **Nota:** Es la memoria conversacional "legacy" de formato simple, distinta del `conversational_memory.json` mejorado (FASE 5+).

### 3.3 `prediction_memory.json`
- **Formato:** JSON objeto.
- **Campos:** `command_usage_stats` (dict comando→contador), `time_patterns` (dict comando→array de horas), `context_patterns` (dict patrón→array de timestamps), `last_updated` (timestamp Unix).
- **Quién lo lee:** `src/memory/prediction.py` (`EnhancedPredictionMemory.__init__(filepath="data/prediction_memory.json")`).
- **Quién lo escribe:** `src/hands/action_registry.py` (`_record_prediction()` → `get_prediction_memory().record_command()`).
- **Tamaño:** 32 líneas.
- **Contenido actual:** `calibrar_aplicaciones` (1 uso, hora 5), `abrir_youtube` (1 uso, hora 8).

### 3.4 `user_preferences.json`
- **Formato:** JSON objeto.
- **Campos:** `version`, `created_at`, `preferred_app` (dict), `preferred_entities` (array), `interaction_settings` (suggestion_enabled, auto_correction, confidence_threshold), `ui_preferences` (default_application, preferred_browser, auto_maximize), `learning_settings` (enable_adaptive_learning, max_interaction_history, update_frequency).
- **Quién lo lee:** `src/memory/conversation.py` (`DomainMemory.load_user_preferences()` lee `data/user_preferences.json`), `src/memory/storage.py` (`MemoryType.PREFERENCES` → `user_preferences.json`).
- **Quién lo escribe:** `DomainMemory.save_user_preferences()` (escribe de vuelta a `data/user_preferences.json`).
- **Tamaño:** 21 líneas.
- **Contenido actual:** `preferred_browser: "chrome"`, `enable_adaptive_learning: true`, `preferred_app: {}`, `preferred_entities: []`.

### 3.5 `macros_coords.json`
- **Formato:** JSON objeto con 4 secciones principales.
- **Secciones:**
  1. `ui_knowledge` — Conocimiento declarativo de elementos UI por aplicación (chrome, spotify, riot_api) con tipo, descripción, estrategia de calibración, alternativas (hotkeys) y confianza.
  2. `calibraciones` — Coordenadas reales calibradas por pantalla (`s1`, `s2`) para cada elemento. Ejemplo: `chrome.address_bar.s1 = [3582, 339]`, `spotify.play_button.s1 = [950, 1025]`, `riot_api.captcha.s1 = [1361, 1584, 100, 50]` (región: x, y, w, h).
  3. `calibration_policies` — `blocked_applications` (juegos, Steam, VS Code, etc.), `allowed_strategies` (visual_detection, window_detection, screen_capture, keyboard_shortcut), `auto_calibration_rules` (por app: true/false).
  4. `legacy_data.macros` — Formato legacy con coordenadas adicionales (riot_api, supercomplete).
- **Quién lo lee:** `src/hands/coordinate_manager.py` (`macros_coords_path` apunta a `data/macros_coords.json`; `_load_ui_knowledge()` y `load_from_macros_coords()` lo leen al inicializar `CoordinateManager`). También referenciado en `src/hands/applications_core.py` (docstring).
- **Quién lo escribe:** `src/hands/calibration_manager.py` (usa `get_macros_coords_path()` en líneas 1904, 2396, 2567 para guardar resultados de calibración). Los calibradores específicos (`edge/calibrator_edge.py`, `firefox/calibrator_firefox.py`, `windows/calibrator_windows.py`) mencionan que "escribe macros_coords.json directamente" en sus docstrings pero el flujo real pasa por `CalibrationManager`.
- **Tamaño:** 156 líneas.
- **Uso:** `CoordinateManager` expone `UIResource` con `calibrated_coordinates` por número de pantalla (`sN`). `get_best_coordinates()` devuelve coordenadas del monitor activo o del primero calibrado disponible.

### 3.6 `contextual_knowledge_base.json`
- **Formato:** JSON objeto (versión 2.0).
- **Campos principales:** `version`, `last_updated`, `context_snapshots`, `adaptation_history`, `knowledge_transfers`, `data` (objeto anidado).
- **Dentro de `data`:**
  - `context_patterns` — dict por contexto (development, production, testing, maintenance, emergency, optimization, learning, idle, recovery) con arrays de patrones.
  - `adaptation_strategies` — dict por contexto con estrategias de adaptación (ej. `strategy_1792858089865_0` para `idle`: `goal_adaptation_idle`, métricas response_time=1.5, accuracy=0.95, confidence=1.0, success_rate=0.9).
  - `goal_adaptation_feedback` — array de feedbacks con `adaptation_id`, `analysis` (performance_improvement, response_time_improvement, accuracy_improvement, pattern_recognition, strategic_insights), `timestamp`, `status`.
  - `learning_results` — array de resultados de aprendizaje con `adaptation_id`, `learned_patterns`, `updated_strategies`, `convergence_metrics` (convergence_status, convergence_score, learning_rate, stability, trend).
  - `goal_adaptation_proposals`, `goal_validations` — arrays vacíos.
  - `performance_baselines`, `success_patterns`, `failure_patterns` — dicts/arrays por contexto.
  - `global_confidence_metrics` — total_feedback, successful_transfers, average_feedback_score, confidence_trend.
- **Quién lo lee/escribe:** `src/utils/contextual_adaptation_engine.py` (referencia `knowledge_base_file = "data/contextual_knowledge_base.json"`, `goal_adaptation_feedback.json`, `goal_adaptation_learning_results.json`, `improvement_rules.json`).
- **Tamaño:** 203 líneas.

### 3.7 `knowledge_graph.json`
- **Formato:** JSON array de nodos.
- **Campos por nodo:** `node_id`, `node_type`, `properties` (timestamp, efficiency_score, optimization_gain, system_load, learning_rate, exploration_rate), `connections` (array), `confidence`, `last_updated`.
- **Contenido actual:** 1 nodo (`node_1794091774`, tipo `system_state`, confidence 0.9).
- **Quién lo lee/escribe:** `src/utils/self_improvement_system.py` (`knowledge_graph_path = "data/knowledge_graph.json"`).
- **Tamaño:** 17 líneas.

### 3.8 `learning_config.json`
- **Formato:** JSON objeto.
- **Secciones:** `learning_system` (enabled, max_memory_size, learning_rate, cost_learning_enabled, pattern_learning_enabled, route_learning_enabled, auto_export, export_interval_hours, export_path), `optimization_integration`, `action_learning` (minimum_executions, success_rate_threshold, cost_accuracy_threshold, pattern_window_size, temporal_patterns), `plan_learning`, `system_health`, `export_settings`, `logging`.
- **Quién lo lee:** Sistema de configuración de aprendizaje (referenciado por `src/utils/`).
- **Tamaño:** 56 líneas.

### 3.9 `improvement_rules.json`
- **Formato:** JSON array de reglas.
- **Campos por regla:** `rule_id`, `name`, `description`, `condition` (expresión), `action` (llamada a función), `priority`, `enabled`, `success_rate`, `execution_count`, `last_execution`, `improvement_score`.
- **Reglas actuales (6 únicas tras limpieza):** `perf_high_cpu`, `mem_high_usage`, `error_rate_high`, `response_time_high`, `efficiency_low`, `custom_rule`.
- **Quién lo lee/escribe:** `src/utils/self_improvement_system.py` (`rule_engine_path = "data/improvement_rules.json"`).
- **Historial:** Originalmente 172 elementos con 166 duplicados; reducido a 6 elementos únicos tras limpieza.
- **Tamaño:** 80 líneas.

### 3.10 `goal_adaptation_feedback.json`
- **Formato:** JSON objeto.
- **Campos:** `goal_adaptation_feedback` (array de feedbacks con `adaptation_id`, `analysis`, `timestamp`, `status`), `adaptation_history` (array con `adaptation_id`, `performance_impact`, `context`, `timestamp`, `success`), `last_updated`.
- **Contenido actual:** 2 feedbacks (adaptation_id "t1", timestamps 2026-10-24T18:08:09 y 2026-10-24T21:51:32), ambos con performance_improvement≈15.28, response_time_improvement=25.0, accuracy_improvement≈5.56, success=true.
- **Quién lo lee/escribe:** `src/utils/contextual_adaptation_engine.py`.
- **Tamaño:** 141 líneas.

### 3.11 `goal_adaptation_learning_results.json`
- **Formato:** JSON objeto.
- **Campos:** `learning_results` (array con `adaptation_id`, `learned_patterns`, `updated_strategies`, `convergence_metrics`, `timestamp`, `status`), `adaptation_strategies` (dict de estrategias por ID), `last_updated`.
- **Estrategia actual:** `strategy_1792858089865_0` (`goal_adaptation_idle`, pattern_id `pattern_001`, response_time=1.5, accuracy=0.95, confidence=1.0, success_rate=0.9, failure_count=0).
- **Quién lo lee/escribe:** `src/utils/contextual_adaptation_engine.py`.
- **Tamaño:** 108 líneas.



---

### 3.12 `system_inventory.sqlite3`
- **Formato:** SQLite (biblioteca estandar `sqlite3`), gestionado por `src/hands/system_inventory_storage.py` (unidad 3.8.5.1.4.2.3).
- **Quien lo lee/escribe:** `SystemInventoryStorage` (`src/hands/system_inventory_storage.py`). Es el almacenamiento canonico del indice de inventario persistente del sistema de archivos (unidad 3.8.5.1.4.2). No lo lee ni lo escribe ningun otro componente de `src/` todavia.
- **Esquema (version 2):**
  - `schema_version(version)`: version del esquema.
  - `machines(machine_id PK, created_at)`: equipos que crean el inventario (aislamiento por equipo, sin MAC ni serial de hardware).
  - `volumes(volume_id PK, machine_id FK, volume, volume_type, state, first_seen_at, last_seen_at)`: volumenes descubiertos por equipo.
  - `scan_runs(scan_id PK, machine_id FK, volume, mode, started_at, finished_at, result, entries_count, errors_count, exclusions_count, coverage_estimate)`: ejecuciones de escaneo (completo/incremental, resultado y metrica de cobertura). El resultado inicial es `interrumpido` (no confirmado); solo `end_scan_run` con `ok` confirma un escaneo completo (3.8.5.1.4.2.7). Un escaneo interrumpido nunca se presenta como inventario completo.
  - `file_entries(entry_id PK, scan_id FK, machine_id FK, volume, absolute_path, normalized_path, relative_path, name, extension, entry_type, size_bytes, modified_at, created_at, accessed_at, attributes JSON, excluded, source, last_checked_at)`: entradas genericas de archivos y directorios (solo metadatos observados, nunca contenido de archivos personales). `normalized_path` es la ruta normalizada segun la case-sensitividad del sistema de archivos (minusculas en sistemas insensibles como Windows/macOS; tal cual en Linux).
  - `application_candidates(candidate_id PK, scan_id FK, machine_id FK, volume, name, absolute_path, launch_type, confidence, source, last_checked_at)`: candidatos de aplicacion, almacenados en tabla propia separada de las entradas genericas de archivo.
  - Indices de consulta por `(machine_id, volume)`, `lower(name)`, `lower(extension)`, `entry_type`, `absolute_path`, `normalized_path`, `excluded` y `(machine_id, started_at)`.
  - Indice unico `idx_file_entries_unique_path(machine_id, volume, normalized_path)`: impide duplicar la misma ruta de archivo para un equipo y volumen dados.
- **Transacciones:** escrituras por lotes en transaccion atomica (`BEGIN`/`COMMIT` con `ROLLBACK` ante fallo); un escaneo interrumpido no deja media base presentada como inventario completo.
- **Migraciones de esquema:** `initialize()` aplica las migraciones registradas en orden (actual: v1 a v2), cada una dentro de su propia transaccion, y verifica que los conteos de filas de todas las tablas se conserven, de modo que no se borren ni se reinterpretan datos de versiones previas al avanzar la version del esquema.
- **Modo de journaling:** WAL, con claves foraneas activadas (`PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`).
- **Ruta por defecto:** `data/system_inventory.sqlite3` (creada por el gestor al inicializar; se crea el directorio padre si no existe).

### 3.13 `system_inventory_manifest.json`

- **Formato:** JSON objeto (un único documento de resumen).
- **Campos principales:**
  - `version` (int): versión del esquema SQLite almacenada en `schema_version`.
  - `machine_id` (str): identificador del equipo que crea el inventario (aislamiento por equipo, sin MAC ni serial de hardware).
  - `volumes` (array de objetos): cada volumen con `volume_id`, `volume`, `volume_type`, `state`, `first_seen_at`, `last_seen_at`.
  - `last_scan` (objeto o null): última ejecución de escaneo del equipo con `scan_id`, `volume`, `mode`, `started_at`, `finished_at`, `result`, `entries_count`, `errors_count`, `exclusions_count`, `coverage_estimate`.
  - `updated_at` (str): timestamp ISO 8601 (UTC) de la última escritura del manifiesto.
- **Quién lo lee/escribe:** `SystemInventoryStorage` (`src/hands/system_inventory_storage.py`). `write_manifest()` se invoca tras registrar un volumen (`record_volume`) y tras finalizar un escaneo (`end_scan_run`), por lo que el manifiesto se mantiene coherente con SQLite automáticamente. `read_manifest()` lo devuelve o `None` si no existe.
- **Contenido:** solo metadatos de resumen. **No almacena el listado entero de archivos** (eso reside en `system_inventory.sqlite3` en la tabla `file_entries`).
- **Ruta por defecto:** `data/system_inventory_manifest.json` (junto a la base de datos SQLite; se crea el directorio padre si no existe).

## 4. Subdirectorio `data/knowledge/`

Contiene el conocimiento de dominio estático cargado por `DomainMemory` (`src/memory/conversation.py`).

### 4.1 `data/knowledge/entities.json`
- **Formato:** JSON array de entidades `Entity`.
- **Campos:** `id`, `type` (streamer/application), `name`, `properties` (url, executable, platform, category), `aliases` (array), `tags` (array), `confidence`, `created_at`, `updated_at`, `metadata`.
- **Entidades (7):**
  - `nissaxter` (streamer, Twitch, gaming), aliases: nissax, nisax, nisa
  - `shroud` (streamer, Twitch, gaming), aliases: shroudo, shurdo
  - `pokimane` (streamer, Twitch, just_chatting), aliases: poki, pokimein
  - `youtube` (application, video_platform, executable chrome.exe), aliases: yt, you
  - `spotify` (application, music, executable spotify.exe), aliases: spoti, music
  - `github` (application, development, executable chrome.exe), aliases: gh, git
  - `twitch` (application, streaming, executable chrome.exe), aliases: twich, twitchtv
- **Quién lo lee:** `src/memory/conversation.py` (`DomainMemory.load_domain_knowledge()` lee `data/knowledge/entities.json`).
- **Tamaño:** 113 líneas.

### 4.2 `data/knowledge/applications.json`
- **Formato:** JSON objeto claveado por nombre de aplicación.
- **Aplicaciones:** `chrome`, `spotify`, `vscode`, `obs_studio`.
- **Campos por aplicación:** `name`, `executable`, `capabilities` (array de strings), `states` (open, active, maximized, focused, etc.), `ui_elements` (dict nombre→{type, description}), `login_required` (bool), `calibration_needed` (array).
- **Quién lo lee:** `src/memory/conversation.py` (`DomainMemory.load_domain_knowledge()` lee `data/knowledge/applications.json`).
- **Tamaño:** 163 líneas.

### 4.3 `data/knowledge/capabilities.json`
- **Formato:** JSON objeto claveado por categoría.
- **Categorías:** `system`, `browser`, `media`, `development`, `streaming`.
- **Campos por capacidad:** `description`, `required_state` (array), `effects` (array), `cost` (float), `applications` (array).
- **Ejemplo:** `browser.navigate` requiere `["chrome_open", "chrome_active"]`, efectos `["url_changed"]`, coste 2.0, aplica a `chrome`.
- **Quién lo lee:** `src/memory/conversation.py` (`DomainMemory.load_domain_knowledge()` lee `data/knowledge/capabilities.json`).
- **Tamaño:** 173 líneas.

---

## 5. Subdirectorio `data/memory/`

Contiene los ficheros de almacenamiento mejorado del `MemoryManager` (`src/memory/storage.py`), mapeados por `MemoryType`:

| Fichero | MemoryType | Formato | Contenido actual |
|---------|-----------|---------|------------------|
| `conversational_memory.json` | CONVERSATIONAL | JSON array | ~9.639 líneas, entradas de conversación con id, message, response, timestamp, context, intent, entities, confidence, execution_time, success |
| `entities.json` | ENTITIES | JSON array | ~1.346 líneas, entidades extendidas (nissaxter, shroud, pokimane, youtube, spotify, github, twitch, google_chrome, brave, microsoft_edge, discord, steam, battle_net, epic_games_launcher, ubisoft_connect, riot_client, obs_studio, docker_desktop, visual_studio_code, pycharm, intellij_idea, ollama, plex, teamspeak, tlauncher, overwolf, outplayed, ...) |
| `applications.json` | APPLICATIONS | JSON object | `{}` (vacío) |
| `domain_knowledge.json` | DOMAIN_KNOWLEDGE | JSON object | `{}` (vacío) |
| `executions.json` | EXECUTIONS | JSON array | `[]` (vacío) |
| `learning_stats.json` | LEARNING_STATS | JSON object | `{}` (vacío) |
| `plans.json` | PLANS | JSON array | `[]` (vacío) |
| `relationships.json` | RELATIONSHIPS | JSON object | `{}` (vacío) |
| `user_preferences.json` | PREFERENCES | JSON object | 1 entrada: `default_user_entity_confidence_selection_entity_confidence_selection_google_chrome` (confidence 1.0, usage_count 24) |
| `world_state.json` | STATE | Texto corrupto | `"<MagicMock name='WorldState().to_dict().to_dict()' ...>"` (corrupto, no es JSON válido) |

**Quién lee/escribe:** `src/memory/storage.py` (`JSONStorage` con `file_mapping` que asocia cada `MemoryType` a su fichero). `MemoryManager.save(data, memory_type)` y `MemoryManager.load(memory_type)` operan sobre estos ficheros.

---

## 6. Flujo de datos: quién lee, quién escribe, a dónde se envía

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUJO PRINCIPAL (main.py)                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                                                        │
                                                                        ▼
┌─────────────┐    voz/texto    ┌───────────┐    intención    ┌──────────┐
│   Ear       │ ───────────────►│  Brain    │ ───────────────►│ Executor │
│ (listener)  │  Whisper STT    │  (llm.py) │  [CMD:] o goal  │ (executor│
└─────────────┘                 └───────────┘                 │   .py)   │
                                                              └────┬─────┘
                                                                   │
                                                                   ▼
                                                            ┌──────────────┐
                                                            │   Mouth      │
                                                            │  (speaker)   │  Kokoro ONNX TTS
                                                            └──────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE MEMORIA Y DATOS                            │
└─────────────────────────────────────────────────────────────────────────────┘

1. main.py → jarvis_memory.save_conversation(texto, respuesta, ...)
   └─► MemoryManager.save() → JSONStorage → data/jarvis_memory.json (legacy)
   └─► ConversationalMemory → data/conversational_memory.json (mejorado, FASE 5+)

2. main.py → jarvis_memory.get_alias(texto) / save_alias()
   └─► Lee config/command_aliases.json (estáticos)

3. Brain.llm.think() → interpreta intención
   └─► memory_manager.add_conversational_memory() → data/conversational_memory.json
   └─► memory_manager.get_user_preferences() → data/user_preferences.json
   └─► memory_manager.get_entities_by_type("streamer"/"platform") → data/knowledge/entities.json

4. Executor.execute_action() → acción física (teclado/ratón)
   └─► action_registry._record_prediction() → data/prediction_memory.json
   └─► CalibrationManager.calibrate_application() → data/macros_coords.json

5. DomainMemory.load_domain_knowledge()
   └─► Lee data/knowledge/entities.json, applications.json, capabilities.json

6. DomainMemory.load_user_preferences() / save_user_preferences()
   └─► Lee/escribe data/user_preferences.json

7. EnhancedPredictionMemory
   └─► Lee/escribe data/prediction_memory.json

8. ContextualAdaptationEngine
   └─► Lee/escribe data/contextual_knowledge_base.json
   └─► Lee/escribe data/goal_adaptation_feedback.json
   └─► Lee/escribe data/goal_adaptation_learning_results.json
   └─► Lee data/improvement_rules.json

9. SelfImprovementSystem
   └─► Lee/escribe data/knowledge_graph.json
   └─► Lee/escribe data/improvement_rules.json

10. MetaLearningSystem
    └─► Persiste estado en data/meta_learning_state.json

11. CoordinateManager
    └─► Lee data/macros_coords.json (coordenadas UI calibradas)
    └─► CalibrationManager escribe calibraciones en data/macros_coords.json
```

### Destino de las respuestas (adonde se envía la información)

- **Voz:** `jarvis_mouth.speak(texto)` → síntesis de voz Kokoro ONNX (salida de audio).
- **Log:** `log_jarvis_info/error/warning()` → sistema de logging avanzado (`src/utils/jarvis_logging_system.py`) y `logs/jarvis.log`.
- **Acción física:** `jarvis_executor.process_and_execute()` → control de teclado/ratón (`pyautogui`) vía `src/hands/keyboard.py`, `src/hands/mouse.py`.
- **Memoria persistente:** Todos los ficheros de `data/` descritos arriba.

---

## 7. Formato de los ficheros

| Fichero | Formato | Estructura principal |
|---------|---------|---------------------|
| `*.json` (mayoría) | JSON | Objeto o array, codificación UTF-8, indentado |
| `conversational_memory.json` | JSON array | Array de `ConversationalMemory` (dataclass con `to_dict()`/`from_dict()`) |
| `jarvis_memory.json` | JSON array | Array de `{role, content}` (formato legacy simple) |
| `macros_coords.json` | JSON objeto | 4 secciones: `ui_knowledge`, `calibraciones`, `calibration_policies`, `legacy_data` |
| `knowledge_graph.json` | JSON array | Array de nodos `{node_id, node_type, properties, connections, confidence, last_updated}` |
| `improvement_rules.json` | JSON array | Array de reglas `{rule_id, name, description, condition, action, priority, enabled, ...}` |
| `user_preferences.json` | JSON objeto | Preferencias anidadas por categoría |
| `contextual_knowledge_base.json` | JSON objeto | Conocimiento de adaptación anidado por contexto |

**Serialización:** Todos los ficheros JSON se escriben con `json.dump(..., ensure_ascii=False, indent=2, default=str)` (véase `src/memory/storage.py` `JSONStorage.save()`).

---

## 8. Estado de integridad conocido

> **Nota:** Los reportes de integridad (`integrity_report.txt`, `data_integrity_report.txt`, `data_integrity_summary.json`) y `cleaning_report.txt` fueron eliminados al ser ficheros huérfanos no referenciados por ningún código de `src/` ni `tests/`. También se eliminó `jarvis_learned_aliases.json` (era un directorio corrupto, no un archivo JSON, con permisos denegados). La información siguiente se conserva como registro histórico del estado conocido antes de la limpieza.

Según los reportes de integridad (fecha 2025-06-17, antes de su eliminación):

- **Puntuación de integridad:** 95.7%
- **Estado general:** Todos los ficheros restantes en `data/` están referenciados por código de `src/` y no tienen problemas de integridad conocidos.

### Acciones recomendadas (extraídas de los reportes históricos):
1. **MEDIA:** Implementar monitoreo automático de integridad (script diario, 1 hora).
2. **MEDIA:** Crear sistema de backup automático para ficheros críticos (30 minutos).

---

## Apéndice: Ficheros de configuración relacionados (fuera de `data/`)

| Fichero | Ruta | Uso en relación con `data/` |
|---------|------|------------------------------|
| `config/config.json` | `config/config.json` | Define `memory.chat_memory_file = "data/jarvis_memory.json"`, rutas de voz, calibración, timeouts, logging |
| `config/command_aliases.json` | `config/command_aliases.json` | Aliases estáticos de comandos de voz (44.050 líneas, mapeo frase→comando). Leído por `ConversationMemory._load_aliases()` |

---

*Fin del README_DATA. Generado a partir del análisis exhaustivo de `src/` y los ficheros presentes en `data/`. No se ha creado ningún script automático para generar este documento.*