# Datos de JARVIS (`data/`, `config/`, `models/`)

Este documento explica que ficheros de datos usa JARVIS, para que sirve cada uno, que forma tienen, que codigo los lee y los escribe, y cuales son propios de cada ordenador. Describe el comportamiento actual del codigo.

> Privacidad: varios de estos ficheros contienen conversaciones, habitos de uso y rutas del equipo. Aqui solo se describe su estructura. En GitHub solo se suben `config/`, el conocimiento estatico de `data/knowledge/` (`applications.json`, `capabilities.json`, `entities.json`) y el modelo de voz en uso de `models/`. El resto de `data/` y todo `logs/` son locales: `.gitignore` los excluye.

## Indice

1. [Mapa rapido](#1-mapa-rapido)
2. [Como se guardan los datos](#2-como-se-guardan-los-datos)
3. [Catalogo de aplicaciones](#3-catalogo-de-aplicaciones)
4. [Perfil y preferencias del usuario](#4-perfil-y-preferencias-del-usuario)
5. [Inventario local y calibracion (propios de cada equipo)](#5-inventario-local-y-calibracion-propios-de-cada-equipo)
6. [Memoria de conversacion y del planificador](#6-memoria-de-conversacion-y-del-planificador)
7. [Aprendizaje, prediccion y automejora](#7-aprendizaje-prediccion-y-automejora)
8. [Configuracion (`config/`)](#8-configuracion-config)
9. [Modelo de voz (`models/`)](#9-modelo-de-voz-models)
10. [Ficheros que se crean solos](#10-ficheros-que-se-crean-solos)
11. [Problemas conocidos en los datos](#11-problemas-conocidos-en-los-datos)

---

## 1. Mapa rapido

| Responsabilidad | Ficheros | Propio del equipo |
|---|---|---|
| Catalogo global de aplicaciones | `data/memory/entities.json` | En parte (campo `executable`) |
| Conocimiento estatico para planificar | `data/knowledge/entities.json`, `data/knowledge/applications.json`, `data/knowledge/capabilities.json` | No |
| Preferencias del usuario | `data/user_preferences.json`, `data/memory/user_preferences.json`, `data/voice_preference.json`, `data/jarvis_learned_aliases.json` | No (pero son personales) |
| Inventario del ordenador | `data/system_inventory.sqlite3`, `data/system_inventory_manifest.json` | Si |
| Calibracion de coordenadas | `data/macros_coords.json`, `data/launch_evidence.json` | Si |
| Conversaciones | `data/conversational_memory.json`, `data/memory/conversational_memory.json`, `data/jarvis_memory.json` | No (personales) |
| Estado y planes | `data/memory/world_state.json`, `plans.json`, `executions.json`, `relationships.json`, `learning_stats.json`, `domain_knowledge.json`, `applications.json` | No |
| Aprendizaje y prediccion (salvo `prediction_memory.json`, solo los usan modulos de `src/experimental/`) | `data/prediction_memory.json`, `data/contextual_knowledge_base.json`, `data/goal_adaptation_*.json`, `data/improvement_rules.json`, `data/knowledge_graph.json`, `data/errores_cometidos*.json`, otros | No |
| Configuracion | `config/config.json`, `config/command_aliases.json` | `config.json` tiene ajustes de pantalla del equipo |
| Voz (TTS) | `models/` | No |

## 2. Como se guardan los datos

### `JSONStorage` y `MemoryManager` (`src/memory/storage.py`)

La mayoria de ficheros JSON pasan por `JSONStorage`. Se crea con una carpeta base (si recibe la ruta de un fichero, usa su carpeta) y cada tipo de memoria (`MemoryType`) tiene un nombre de fichero fijo:

| `MemoryType` | Fichero | Valor por defecto si falta o esta corrupto |
|---|---|---|
| `CONVERSATIONAL` | `conversational_memory.json` | `[]` |
| `ENTITIES` | `entities.json` | `[]` |
| `PLANS` | `plans.json` | `[]` |
| `EXECUTIONS` | `executions.json` | `[]` |
| `DOMAIN_KNOWLEDGE` | `domain_knowledge.json` | `{}` |
| `APPLICATIONS` | `applications.json` | `{}` |
| `STATE` | `world_state.json` | `{}` |
| `LEARNING_STATS` | `learning_stats.json` | `{}` |
| `RELATIONSHIPS` | `relationships.json` | `{}` |
| `PREFERENCES` | `user_preferences.json` | `{}` |

- `MemoryManager` usa como base `data/memory/`.
- La clase `Memory` de `src/memory/conversation.py` crea su `JSONStorage` a partir de `data/jarvis_memory.json`, asi que su base es `data/`. Por eso existen dos `conversational_memory.json` con formatos distintos (ver seccion 6).

### Escritura atomica

Escriben de forma atomica (fichero temporal + `os.replace`), y por tanto no dejan el fichero a medias si el proceso se corta:

- `MemoryManager.save_entity` (catalogo de aplicaciones).
- Memoria predictiva (`data/prediction_memory.json`).
- `ContextualAdaptationEngine`: base de conocimiento y reglas.
- `CalibrationManager`: `data/macros_coords.json` y `data/launch_evidence.json`.
- `save_voice_preference` (`data/voice_preference.json`).

Todo lo demas se escribe con `open(..., "w")` directo y no es atomico.

Si `entities.json` no es una lista JSON valida (corrupto, cortado o con otro tipo de contenido), `save_entity` no pierde lo que habia: guarda una copia exacta del original junto a el (`entities.json.corrupto-<fecha>`), recupera todas las entidades completas que contenga (objetos con `id`, `type`, `name` y `properties`) y escribe una lista valida con ellas y la entidad nueva. Si no puede escribir la copia, no toca el fichero y devuelve `False`.

## 3. Catalogo de aplicaciones

### `data/memory/entities.json` - catalogo global

- **Que es:** la lista de entidades que JARVIS conoce, sobre todo aplicaciones. Las aplicaciones descubiertas en el equipo se registran aqui automaticamente (upsert por `id`, sin duplicar).
- **Forma:** lista de objetos.

```json
[
  {
    "id": "app_ejemplo",
    "type": "application",
    "name": "Ejemplo",
    "properties": { "executable": "...", "category": "...", "capabilities": [], "states": {}, "ui_elements": {}, "url": null, "login_required": false },
    "aliases": ["ejemplo", "..."],
    "tags": [],
    "confidence": 0.9,
    "created_at": "...",
    "updated_at": "...",
    "metadata": null
  }
]
```

  `type` es `application` en casi todas; tambien hay entidades `streamer`. El contenido de `properties` varia segun como se registro la aplicacion.
- **Escribe:** `MemoryManager.save_entity` (atomico); los descubrimientos llegan desde `src/hands/apps/application_discovery.py`.
- **Lee:** `MemoryManager.get_entity` / `find_entities`, `src/memory/entity_resolver.py`, `src/hands/apps/application_launch_classifier.py` (solo lectura).
- **Ojo:** `properties.executable` puede contener una ruta de este equipo. Es una observacion, no una ruta fiable en otro ordenador: para lanzar, la ruta valida se obtiene del inventario local (seccion 5) y pasa por `ApplicationPreflight`.

### `data/knowledge/entities.json` - semilla de entidades

- Lista corta y estatica de entidades (aplicaciones y streamers) que `DomainMemory.load_domain_knowledge` carga en memoria. Mismo formato que el catalogo, pero sin rutas.
- Nadie la escribe por codigo. Sus IDs tambien estan en `data/memory/entities.json`.

### `data/knowledge/applications.json` - modelo estatico de aplicaciones

- Describe unas pocas aplicaciones (por ejemplo Chrome, Spotify, VS Code, OBS) con sus capacidades, estados posibles y elementos de interfaz.

```json
{
  "chrome": {
    "name": "...", "executable": "...",
    "capabilities": ["..."],
    "states": { "open": false, "active": false, "maximized": false, "focused": false },
    "ui_elements": { "address_bar": { "...": "..." } },
    "login_required": false,
    "calibration_needed": ["..."]
  }
}
```

- Lo lee `DomainMemory.load_domain_knowledge`. Se edita a mano.
- No confundir con `data/memory/applications.json`, que es un almacen en tiempo de ejecucion y ahora mismo esta vacio (`{}`).

### `data/knowledge/capabilities.json` - capacidades para el planificador

- Catalogo de capacidades agrupado por categoria (`system`, `browser`, `media`, `development`, `streaming`):

```json
{ "browser": { "open_url": { "description": "...", "required_state": ["..."], "effects": ["..."], "cost": 1.0, "applications": ["chrome"] } } }
```

- Lo lee `DomainMemory.load_domain_knowledge`. Nadie lo escribe.

## 4. Perfil y preferencias del usuario

| Fichero | Que guarda | Codigo |
|---|---|---|
| `data/user_preferences.json` | Preferencias por defecto: aplicacion y navegador preferidos, maximizar automaticamente, umbral de confianza, ajustes de aprendizaje. | `DomainMemory.load_user_preferences` / `save_user_preferences` (`src/memory/conversation.py`) |
| `data/memory/user_preferences.json` | Preferencias aprendidas, una por clave `"<usuario>_<tipo>_<clave>"`, con valor, confianza, contexto y numero de usos. | `MemoryManager.save_user_preference` / `get_user_preferences`; las lee `entity_resolver.py` |
| `data/voice_preference.json` | La voz elegida: `{"voice_id": "..."}`. | `load_saved_voice_preference` / `save_voice_preference` (`src/core/config.py`), usada por `src/mouth/speaker.py` |
| `data/jarvis_learned_aliases.json` | Frases aprendidas: `{"frase normalizada": "comando"}`. Se crea al ejecutar con exito un comando. | `ConversationMemory.save_alias` (atomico) y `_load_aliases` (`src/memory/conversation.py`) |

## 5. Inventario local y calibracion (propios de cada equipo)

Estos datos solo valen para el ordenador donde se crearon. No deben copiarse a otro equipo.

### `data/system_inventory.sqlite3` - inventario del ordenador

- **Que es:** indice de los ficheros y de las aplicaciones candidatas encontrados en los volumenes del equipo. Es la fuente de rutas reales para abrir aplicaciones y la base sobre la que trabajan las pruebas de inventario (prohibido repetir un escaneo completo; ver `mejora/prompt_JARVIS_reglas.txt`, seccion 17).
- **Codigo:** `src/hands/inventory/system_inventory_storage.py` (almacenamiento) y `src/hands/inventory/system_inventory.py` (identidad del equipo y contrato).
- **Identidad del equipo:** `generate_machine_id()` = `uuid5(NAMESPACE_DNS, "jarvis-local-<hostname>-<SO>")`. No usa MAC, numero de serie ni usuario. Si la base pertenece a otro `machine_id`, se rechaza (`InventoryIncompatibleMachineError`).
- **Proteccion:** modo WAL, claves foraneas activas, permisos solo para el usuario, copia de seguridad con sufijo `.bak` y comprobacion de integridad antes de restaurar (`InventoryCorruptError`, `InventoryBackupError`).
- **Integridad al abrir** (`initialize` -> `verify_integrity_al_abrir`): bases de hasta 256 MB, `PRAGMA quick_check` + `integrity_check` completos; mayores, `PRAGMA quick_check(tabla)` de cada tabla con sus indices salvo `file_entries` (con la base real, 5,6 M filas y 14 GB, la completa tardaba unos 6 minutos en cada apertura: 136 s + 231 s medidos). `JARVIS_INVENTARIO_VERIFICACION_COMPLETA=1` fuerza la completa; `verify_integrity()` la ejecuta bajo demanda.
- **Version de esquema:** 6.

| Tabla | Para que | Columnas principales |
|---|---|---|
| `schema_version` | Version del esquema | `version` |
| `machines` | Equipos conocidos | `machine_id`, `created_at` |
| `volumes` | Discos/volumenes de cada equipo | `volume_id`, `machine_id`, `volume`, `volume_type`, `state`, `first_seen_at`, `last_seen_at` |
| `scan_runs` | Cada escaneo realizado | `scan_id`, `machine_id`, `volume`, `mode` (`completo`/`incremental`), `started_at`, `finished_at`, `result` (`ok`/`parcial`/`interrumpido`/`error`), contadores, `coverage_estimate`. Las ejecuciones `registro-...` solo registran candidatos de aplicacion (`ApplicationDiscovery.registrar_candidatos`): no recorren el volumen y `get_latest_scan` y el ultimo escaneo completo ok las ignoran. |
| `file_entries` | Ficheros y carpetas encontrados | `entry_id`, `scan_id`, `machine_id`, `volume`, `absolute_path`, `normalized_path`, `relative_path`, `name`, `extension`, `entry_type`, `size_bytes`, fechas, `attributes` (JSON), `excluded`, `source`, `last_checked_at` |
| `application_candidates` | Posibles aplicaciones | `candidate_id`, `scan_id`, `machine_id`, `volume`, `name`, `absolute_path`, `launch_type`, `confidence`, `version`, `producto`, `evidencia` (JSON), `source`, `last_checked_at` |
| `lineas_base` | Linea base por volumen (una por equipo y volumen) | `linea_id`, `machine_id`, `volume`, `fecha_base`, `estado_volumen`, `cobertura`, contadores, `scan_id`, `created_at` |
| `calibration_profiles` | Perfiles de calibracion UI por equipo y aplicacion | `profile_id`, `machine_id`, `app_id`, `window_fingerprint`, `topology_fingerprint`, `display_id`, `scale_factor`, `dpi`, `client_width`, `client_height`, `status`, `is_active`, `absolute_cache` (JSON), `metadata` (JSON), `obsolete_reason`, `created_at`, `updated_at` |
| `calibration_controls` | Controles calibrados de un perfil | `profile_id`, `control_id`, `machine_id`, `app_id`, `name`, `control_type`, `semantic_state`, `geometric_state`, `action_state`, `client_box_normalized`, `client_box_px`, `safe_point_normalized`, `interaction_method`, `provenance` (JSON), `detector_versions` (JSON), `original_box`, `refined_box`, `confidences` (JSON), `reasons` (JSON), `calibrated_at` |

- **Migraciones:** cada paso va en su propia transaccion, se deshace si falla y comprueba que el numero de filas no cambia. v1->v2 anade `normalized_path`; v2->v3 crea `lineas_base`; v3->v4 cambia el indice unico para incluir `scan_id`; v4->v5 anade `version`, `producto` y `evidencia` a los candidatos; v5->v6 crea las tablas de calibracion UI local (`calibration_profiles`, `calibration_controls`) y sus indices. Si la base es mas nueva que el codigo, no se toca.
- `normalized_path` va en minusculas en sistemas de ficheros que no distinguen mayusculas (Windows, macOS).
- **No se sube al repositorio** (`.gitignore` excluye `data/system_inventory*.sqlite3*` salvo la muestra). En el repositorio solo esta `data/system_inventory_sample.sqlite3`, una muestra pequena de ejemplo.
- **Copia completa en GitHub:** `scripts/bbdd_github.py` la guarda comprimida con xz (partes de hasta 1900 MiB y `bbdd_manifest.json` con tamanos y SHA-256) en la release `bbdd` del repositorio privado `JavierCarceles/JARVIS-datos`. Usa GitHub CLI (`gh`); si falta, ofrece instalarlo e iniciar sesion.
  - `python scripts/bbdd_github.py subir`: vuelca el WAL, comprime la base con una transaccion de lectura abierta (copia coherente) y sustituye la copia anterior de la release. Si JARVIS esta usando la base, pide cerrarlo.
  - `python scripts/bbdd_github.py descargar`: comprueba el SHA-256 de cada parte, descomprime y pasa `PRAGMA quick_check`. La deja en `data/system_inventory.sqlite3`, igual que en el equipo de origen (la anterior se renombra a `.antes_descarga` tras confirmarlo). Si la copia es de otro equipo, `SystemInventoryStorage.initialize()` la rechaza con `InventoryIncompatibleMachineError` sin borrarla, asi que JARVIS no la usa en ese equipo pero puede consultarse.
  - Sin argumentos muestra un menu; en Windows se puede abrir con doble clic.

### `data/system_inventory_manifest.json`

Resumen ligero que se regenera junto a la base (`write_manifest`): version del esquema, `machine_id`, lista de volumenes y datos del ultimo escaneo. No contiene la lista de ficheros.

### `data/macros_coords.json` - calibraciones de coordenadas

```json
{
  "ui_knowledge": { "<app>": { "<elemento>": { "type": "...", "description": "...", "calibration_strategy": "...", "alternatives": [], "confidence": 0.0 } } },
  "calibraciones": { "<app>": { "<elemento>": { "s1": [100, 200], "s2": [1500, 200] } } },
  "calibration_policies": { "blocked_applications": [], "allowed_strategies": [], "auto_calibration_rules": { "chrome": true } },
  "legacy_data": { "macros": { "...": {} } }
}
```

- `s1`, `s2`... son monitores y los valores son pixeles de pantalla. `CalibrationManager` solo acepta claves `s<numero>` con dos enteros.
- La ruta la da `get_macros_coords_path()` (`src/core/config.py`). `src/hands/calibration/get_coords.py` tambien acepta una copia antigua en la raiz del proyecto.
- Escribe `CalibrationManager` (atomico). Es un formato heredado: el destino previsto de las calibraciones nuevas es la base SQLite local, vinculada a `machine_id` y a la configuracion de pantallas.

### `data/launch_evidence.json`

Evidencia del ultimo lanzamiento (ventana detectada, tiempos). La escribe `CalibrationManager` de forma atomica. Se crea al usarse.

## 6. Memoria de conversacion y del planificador

| Fichero | Quien lo usa | Formato |
|---|---|---|
| `data/memory/conversational_memory.json` | `MemoryManager.add_conversational_memory`, llamado desde `src/brain/llm.py` y `src/brain/htn_integration.py` | Lista de registros `{id, message, response, timestamp, context, intent, entities, confidence, execution_time, success}` |
| `data/conversational_memory.json` | Clase `Memory` (`src/memory/conversation.py`): `save_conversation`, `get_conversation_history`, `clear_history`. Se reescribe completo y de forma atomica con los ultimos `max_history_length * 2` mensajes | Lista alterna de mensajes `user` (texto, objetivo y plan generados, estado del sistema) y `assistant` (texto, resultado de ejecucion) |
| `data/jarvis_memory.json` | Heredado. La configuracion lo nombra (`memory.chat_memory_file`), pero `Memory` solo lo usa para saber que su carpeta es `data/` | Lista `{role, content}` |

Mismo nombre de fichero, distinto escritor y distinto formato: el de `data/memory/` es el registro estructurado del cerebro; el de `data/` es el historial de chat de `Memory`.

Almacenes del planificador en `data/memory/` (todos via `MemoryManager`):

- `world_state.json`: estado del mundo (`save_world_state` / `update_world_state`).
- `plans.json` y `executions.json`: planes y ejecuciones (`save_plan`, `save_execution_record`).
- `learning_stats.json`, `relationships.json`, `domain_knowledge.json`, `applications.json`: almacenes genericos.

Ahora mismo estan vacios, salvo `world_state.json` (ver seccion 11).

## 7. Aprendizaje, prediccion y automejora

| Fichero | Que guarda | Codigo |
|---|---|---|
| `data/prediction_memory.json` | Uso de comandos: veces que se uso cada uno, horas de uso, patrones de contexto | `src/memory/prediction.py` (atomico) |
| `data/contextual_knowledge_base.json` | Patrones y estrategias por contexto (`development`, `testing`, `idle`, ...) | `src/experimental/contextual_adaptation_engine.py` (atomico) |
| `data/contextual_adaptation_rules.json` | Reglas de adaptacion | mismo motor (atomico); se crea al usarse |
| `data/goal_adaptation_feedback.json` | Feedback e historial de adaptaciones de objetivos (maximo ~1000) | mismo motor |
| `data/goal_adaptation_learning_results.json` | Resultados de aprendizaje y estrategias aprendidas (maximo ~500) | mismo motor |
| `data/improvement_rules.json` | Reglas de automejora, incluidas las de "no repetir este error" | `src/experimental/gestor_errores_cometidos.py` y `src/experimental/self_improvement_system.py` (los dos escriben el mismo fichero) |
| `data/errores_cometidos.json`, `data/errores_cometidos_archivados.json` | Errores registrados y ya procesados | `src/experimental/gestor_errores_cometidos.py` |
| `data/knowledge_graph.json` | Nodos de metricas del sistema de automejora (maximo ~1000) | `src/experimental/self_improvement_system.py` |
| `data/learning_history.json` | Historial del sistema de automejora | `src/experimental/self_improvement_system.py`; se crea al usarse |
| `data/meta_learning_config.json` | Configuracion del meta-aprendizaje | `src/experimental/meta_learning_system.py`; se crea al usarse |
| `data/domain_knowledge_persistence.json` | Conocimiento de dominio persistido | `DomainMemory` (`src/memory/conversation.py`); se crea al usarse |
| `data/learning_config.json` | Configuracion de un sistema de aprendizaje | Ningun codigo lo lee ni lo escribe (huerfano) |

## 8. Configuracion (`config/`)

### `config/config.json`

Configuracion principal. La carga `src/core/config.py` en clases de datos; si falta una clave se usa su valor por defecto. En ejecucion solo se lee.

| Seccion | Contenido |
|---|---|
| `system` | Nombre, version, modo depuracion, sistema de coordenadas |
| `voice` | Voz por defecto, carpeta del modelo (`models`), fichero ONNX (`model_fp16.onnx`), carpeta de voces, tokenizador |
| `calibration` | Activada, limites de intentos, confianza minima de deteccion, guardar resultados, coordenadas nativas, `calibration_screen` |
| `screen` | Multipantalla, calidad de captura, conversion de coordenadas |
| `timeout` | Tiempos de llamada a Ollama, captura, clics y escritura |
| `predictive` | Activacion y parametros de la prediccion de comandos |
| `keyboard` | `fail_safe` y pausa entre acciones |
| `memory` | `chat_memory_file`, `alias_memory_file`, longitud maxima del historial |
| `element_types` | Tamanos minimos y umbrales por tipo de elemento de interfaz |
| `chrome` | Tamano y posicion por defecto de la ventana |
| `logging` | Nivel, formato y fichero de log |

Ojo: `calibration` y `screen` contienen ajustes que dependen de las pantallas de este equipo, aunque el fichero se versiona.

### `config/command_aliases.json`

Tabla grande (unas 44.000 entradas) de frases habladas -> comando, por ejemplo variantes de una misma orden. Formato: `{ "frase": "comando" }`. La carga `ConversationMemory` una vez por proceso (solo lectura). `main.py` solo usa los aliases cuya accion esta registrada; hoy son 7 de los 29 comandos distintos del fichero.

## 9. Modelo de voz (`models/`)

Modelo de sintesis de voz Kokoro en formato ONNX, usado por `src/mouth/speaker.py`.

| Ruta | Que es |
|---|---|
| `models/onnx/model_fp16.onnx` | Modelo que se usa (`voice.onnx_model_file`). Es el unico que se sube a GitHub; si tienes otras variantes en local (`model`, `model_quantized`, `model_uint8`, `model_uint8f16`), `.gitignore` las excluye. |
| `models/voices/*.bin` | 46 voces. Nombre `<idioma><genero>_<nombre>`, por ejemplo `am_eric`, `ef_dora`. |
| `models/tokenizer.json`, `models/tokenizer_config.json`, `models/config.json` | Tokenizador y configuracion del modelo |
| `models/README.md` | Ficha original del modelo, de sus autores. No es documentacion del proyecto. |

El `.onnx` se guarda con Git LFS. Si el repositorio se clona sin LFS, solo quedan ficheros de unos 134 bytes (punteros) y la voz no funciona hasta descargar los modelos reales con `git lfs pull`.

## 10. Ficheros que se crean solos

Si faltan, el codigo crea la carpeta y usa valores por defecto. Se generan al usar la funcion correspondiente:

- Todos los almacenes de `data/memory/`.
- `data/system_inventory.sqlite3` (y `-wal`, `-shm`, `.bak`) y su manifiesto. `scripts/bbdd_github.py` crea ademas `data/_bbdd_tmp/` mientras trabaja y, al descargar sobre una base existente, `data/system_inventory.sqlite3.antes_descarga`.
- `data/voice_preference.json`, `data/launch_evidence.json`, `data/errores_cometidos*.json`.
- Los ficheros de aprendizaje de la seccion 7 y `data/prediction_memory.json`.
- `logs/jarvis.log` (y sus copias rotadas `jarvis.log.1` ... `.5`), creado por `setup_logging()` al arrancar `main.py`. Los `.log` por clase y las bases `logs/*.db` que hubiera de versiones anteriores ya no se generan en ejecucion normal; solo los crean los modulos de `src/experimental/` si alguien los usa. Se pueden borrar.

Hay que aportar o editar a mano: `config/*.json`, `data/knowledge/*.json` y los modelos de `models/`. `data/macros_coords.json` se completa al calibrar.

## 11. Problemas conocidos en los datos

1. **`data/memory/world_state.json` contaminado por un test.** Contiene el texto de un `MagicMock` en lugar de un estado valido. Un test escribio en el fichero real. Se puede reemplazar por `{}`.
2. **`data/jarvis_memory.json` con formato inesperado.** Es una lista `{role, content}`, pero la limpieza de `contextual_adaptation_engine.py` espera un objeto con la clave `conversations`.
3. **`DomainMemory.get_application_capabilities`** busca por nombre de aplicacion en `capabilities.json`, pero ese fichero esta agrupado por categoria, asi que no encuentra nada.
4. **`data/learning_config.json`** no lo usa ningun codigo.
5. **Escrituras no atomicas.** `JSONStorage.save` y varios motores de aprendizaje escriben directamente; un corte durante la escritura puede dejar un JSON roto (el codigo cae entonces al valor por defecto).
