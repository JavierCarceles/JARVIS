# JARVIS

Asistente de voz en espanol para el ordenador: escucha lo que dices, lo interpreta con un modelo de lenguaje local (Ollama), ejecuta acciones (abrir aplicaciones, navegar, teclado, raton, calibrar interfaces) y responde hablando.

Este documento explica como esta organizado el codigo, que hace cada parte, que se usa realmente al ejecutar JARVIS y que limitaciones conocidas tiene. Describe el codigo tal como es hoy.

Otros documentos:

- `docs/readme/README_DATA.md`: ficheros de datos (`data/`, `config/`, `models/`).
- `docs/readme/README_TESTS.md`: bateria de tests.
- `mejora/`: roadmap y reglas del proceso de desarrollo (no es documentacion del codigo).

## Indice

1. [Que es y como esta construido](#1-que-es-y-como-esta-construido)
2. [Como funciona hoy (`main.py`)](#2-como-funciona-hoy-mainpy)
3. [Instalacion y arranque](#3-instalacion-y-arranque)
4. [Estructura del proyecto](#4-estructura-del-proyecto)
5. [Cerebro, oido, boca y herramientas](#5-cerebro-oido-boca-y-herramientas)
6. [Ojos: captura y vision (`src/eyes/`)](#6-ojos-captura-y-vision-srceyes)
7. [Manos: aplicaciones, calibracion y acciones (`src/hands/`)](#7-manos-aplicaciones-calibracion-y-acciones-srchands)
8. [Planificacion (`src/hands/planner/`)](#8-planificacion-srchandsplanner)
9. [Memoria (`src/memory/`)](#9-memoria-srcmemory)
10. [Nucleo, escritorio y experimental](#10-nucleo-escritorio-y-experimental)
11. [Configuracion y logs](#11-configuracion-y-logs)
12. [Windows y macOS](#12-windows-y-macos)
13. [Problemas conocidos](#13-problemas-conocidos)
14. [Como mantener este documento](#14-como-mantener-este-documento)

---

## 1. Que es y como esta construido

JARVIS se organiza como un cuerpo:

| Parte | Carpeta | Que hace |
|---|---|---|
| Oido | `src/ear/` | Graba el microfono y transcribe con Whisper (`faster-whisper`, modelo `medium`, espanol). |
| Cerebro | `src/brain/` | Interpreta el texto: acciones directas, entidades conocidas o consulta al LLM `llama3` en Ollama. |
| Herramientas | `src/tools/` | Ejecuta la accion elegida (`[CMD: nombre(args)]`) y aporta contexto del sistema. |
| Manos | `src/hands/` | Acciones reales: aplicaciones, ventanas, teclado, raton, calibracion, inventario del equipo, planificador. |
| Ojos | `src/eyes/` | Capturas de pantalla y vision con `qwen3-vl` en Ollama. |
| Memoria | `src/memory/` | Conversaciones, catalogo de entidades y aplicaciones, preferencias, prediccion. |
| Boca | `src/mouth/` | Sintesis de voz local con Kokoro (ONNX). |
| Nucleo | `src/core/` | Configuracion, sistema de logs y modelos compartidos. |
| Escritorio | `src/desktop/` | Monitores, ventanas y capturas de pantalla. |
| Experimental | `src/experimental/` | Modulos que el flujo normal no usa (monitorizacion, aprendizaje, logs avanzados). |

Conviven dos arquitecturas:

- **Heredada (la que funciona hoy):** texto -> `Brain` -> `[CMD: accion]` -> `UnifiedExecutor` -> `ActionRegistry` -> accion.
- **Nueva (en construccion):** texto -> `Goal` -> HTN/`Planner` -> `Plan` -> `Executor` -> verificacion -> estado -> replanificacion. Esta implementada en `src/hands/planner/` y `src/hands/actions/executor.py` y cubierta por tests, pero `main.py` todavia no la usa.

Modelos externos que necesita:

| Modelo | Para que | Donde |
|---|---|---|
| `llama3` | Interpretar ordenes | Ollama |
| `qwen3-vl:8b-instruct` | Vision y calibracion | Ollama |
| `qwen3-vl:8b` (variante con razonamiento) | Solo la `Vision` ligera de `vision_only.py` | Ollama |
| Whisper `medium` | Voz a texto | Cache de Hugging Face (se descarga al primer uso) |
| Kokoro ONNX + voces | Texto a voz | `models/` (Git LFS) |
| OmniParser V2 `icon_detect_v3` | Deteccion visual (opcional, solo tests) | Cache de Hugging Face |
| PaddleOCR PP-OCRv5 | OCR (opcional, solo tests) | `~/.paddlex/official_models` |

## 2. Como funciona hoy (`main.py`)

`python main.py` es el unico punto de entrada.

### Al cargar el fichero

1. Importa oido, cerebro, ejecutor, memoria, logs y configuracion. La boca (`src.mouth`) se importa dentro de `try`: si falla, JARVIS funciona en modo texto.
2. Activa el modo DPI en Windows (en otros sistemas se ignora el error).

### Inicio de `main()`

1. Llama a `setup_logging()`: los logs salen por consola y se guardan en `logs/jarvis.log` (seccion 11).
2. **Ollama** (`_preparar_ollama`, con `src/core/ollama_server.py`): si el servidor no responde y la direccion es local, arranca `ollama serve` y lo cierra al salir de JARVIS; si ya estaba en marcha, lo reutiliza y no lo cierra. Si no se puede (Ollama no instalado, direccion remota), solo deja un aviso: Brain y Vision fallaran hasta que Ollama este en marcha.
3. Crea `Ear(model_size="medium")`, `Brain(model="llama3")`, el ejecutor (`get_executor()` de `src/tools/executor.py`) y `Memory()`. Si algo falla: "FALLO CRITICO" y salida.
4. **Primer inventario del equipo:** si este ordenador no tiene ningun escaneo correcto en `data/system_inventory.sqlite3`, lanza en segundo plano un inventario completo de todos los volumenes.
5. Comprueba si existe `data/macros_coords.json` (solo informativo).
6. Crea la boca (`Mouth()`) y elige la voz.

### Bucle principal

```
texto = ear.listen()            (espera hasta oir una frase)
  |
  |-- "cambia la voz a X"  -> mouth.set_voice(X)
  |-- alias conocido       -> [CMD: alias] -> ejecutar -> memory.save_alias
  |-- sugerencia >= 0.8    -> preguntar "Quieres ejecutar X?" -> si/claro/ok/vale/dale/hazlo -> ejecutar
  '-- si no                -> brain.think(texto)
                                |-- "[CMD: accion]"         -> ejecutar con UnifiedExecutor
                                |-- "Objetivo registrado..." -> (no se ejecuta nada)
                                '-- texto normal             -> se dice tal cual
  -> mouth.speak(respuesta)
  -> memory.save_conversation(texto, respuesta)
```

- No hace falta decir "Jarvis" antes de cada orden (`listen(activation_word=False)`).
- Un alias solo se usa si su accion esta registrada (`UnifiedExecutor.get_command_info`); si no, la frase sigue hacia las sugerencias y `Brain`. Cada comando ejecutado con exito se aprende como alias (`save_alias`).
- Las sugerencias salen de `UnifiedExecutor.get_command_suggestions`, que busca la frase como subcadena en los nombres y descripciones de las acciones.
- Cuando `Brain` detecta un objetivo (por ejemplo, abrir un canal de un streamer conocido), solo lo registra y responde "Objetivo registrado... El sistema lo procesara proximamente": la planificacion no esta conectada.
- `Ctrl+C` apaga JARVIS.

## 3. Instalacion y arranque

### Requisitos

- **Python 3.14 o superior.** `src/memory/conversation.py` usa en anotaciones el nombre `Entity`, que no se importa. Solo funciona gracias a la evaluacion diferida de anotaciones de Python 3.14.
- **Ollama** instalado, con `llama3`, `qwen3-vl:8b` y `qwen3-vl:8b-instruct`. Si el servidor no esta en marcha, JARVIS (y la sesion de tests que lo necesite) arranca `ollama serve` y lo cierra al terminar.
- **Git LFS** para descargar los modelos de voz de `models/onnx/`.
- **Windows 10/11** para la mayor parte de las funciones (ver seccion 12).

### Instalar dependencias

| Sistema | Comando |
|---|---|
| Windows | `docs\requirements\jarvis_requirements.bat` |
| macOS | `docs/requirements/jarvis_requirements.command` (doble clic o `bash`) |

Ambos lanzan `docs/requirements/install_jarvis.py`, que:

1. Comprueba Python. En macOS crea `.venv` en la raiz, porque el Python de Homebrew no permite instalar paquetes de forma global.
2. Instala torch (con CUDA si hay GPU NVIDIA en Windows).
3. Instala `docs/requirements/requirements.txt`. Los paquetes de cada sistema se filtran con marcadores `sys_platform`.
4. Comprueba que cada modulo se importa.
5. Instala y arranca Ollama, descarga los tres modelos y precarga Whisper `medium` y los pesos de OmniParser.

Opciones: `--si` (responde que si a todo), `--sin-modelos`, `--sin-gpu`, `--venv` y `--cuda cuXXX`.

### Arrancar

Desde la carpeta del proyecto. En Windows:

```bash
python main.py
```

En macOS:

```bash
.venv/bin/python main.py
```

Arranca siempre desde la carpeta del proyecto: varias rutas de datos y logs son relativas al directorio de trabajo.

## 4. Estructura del proyecto

```
JARVIS/
  main.py                    Punto de entrada (seccion 2)
  config/                    config.json y command_aliases.json (README_DATA)
  data/                      Datos locales y personales (README_DATA)
  models/                    Modelo de voz Kokoro (Git LFS) y voces
  logs/                      jarvis.log (se crea solo; rota a 5 MB)
  docs/
    readme/                  README.md, README_DATA.md y README_TESTS.md
    requirements/            requirements.txt e instaladores (install_jarvis.py, .bat, .command)
  mejora/                    Roadmap, reglas y registros del proceso de desarrollo
  memoria/                   Notas del proceso de desarrollo
  src/
    core/                    Configuracion, logs y modelos comunes (secciones 10 y 11)
    desktop/                 Monitores, ventanas y capturas (seccion 10)
    brain/  ear/  mouth/     Cerebro, oido y boca (seccion 5)
    tools/                   Ejecutor de comandos y contexto del sistema (seccion 5)
    eyes/                    (seccion 6)
      capture/               Captura de pantalla y estado observable
      vision/                Vision con Qwen3-VL y OpenCV
      detection/             Fusion de detectores de interfaz
    hands/                   (seccion 7)
      apps/                  Catalogo, preflight, clasificacion, descubrimiento (y windows/)
      inventory/             Inventario de ficheros del equipo (SQLite)
      calibration/           Calibracion y coordenadas
      detection/             UI Automation, OmniParser, OCR, validacion de evidencia
      input/                 Teclado y raton
      actions/               Registro de acciones y ejecutor de planes
      browsers/              Chrome, Edge y Firefox
      planner/               Planificacion (seccion 8)
    memory/                  Memoria (seccion 9)
    experimental/            Modulos sin uso en el flujo normal (seccion 10)
  tests/                     Misma estructura que src/ (README_TESTS)
```

Reglas de organizacion:

- Cada modulo vive en el subpaquete de su responsabilidad. No hay carpetas genericas tipo `utils/`.
- Los imports son siempre absolutos con prefijo `src.` (por ejemplo `from src.hands.apps.applications_core import get_application_manager`).
- Nada del flujo normal importa `src.experimental`.
- `tests/` replica la estructura de `src/`. Las pruebas de lanzamiento, proceso y ventana estan juntas en `tests/hands/launch/`.

## 5. Cerebro, oido, boca y herramientas

### 5.1 Cerebro (`src/brain/`)

#### `llm.py` - clase `Brain`

Convierte lo que dice el usuario en una accion (`[CMD: nombre]`) o en un objetivo (`Goal`).

- `Brain(model="llama3")`. Al crearse prepara el resolutor de entidades, el gestor de precondiciones, la integracion HTN y el integrador de aplicaciones.
- `think(texto)` -> respuesta en texto. Es lo que usa `main.py`. Llama a `interpret_intent` y:
  - si es una accion, devuelve `[CMD: accion]` (los parametros se descartan);
  - si es un objetivo, lo guarda y responde "Objetivo registrado...";
  - si no entiende, responde "No entendi tu solicitud...".
- `interpret_intent(texto)` -> diccionario con `type` (`action`, `goal` o `unknown`). Orden:
  1. **Accion directa por patron:** "calibrar chrome/edge/firefox" -> `calibrar_chrome`... ; "calibrar aplicaciones/programas/todo" -> `calibrar_aplicaciones`; "calibra X a fondo" -> `calibrar_aplicacion_profunda` (exploracion en profundidad de una aplicacion).
  2. **Entidad conocida:** con `EntityResolver` (streamer -> `navigate_stream`, plataforma -> `navigate`, aplicacion -> `open_application`/`close_application`).
  3. **LLM en modo planificacion:** pide JSON con un objetivo o una accion.
  4. **LLM en modo heredado.**
  5. Desconocido.
- `generate_response(texto)`: llamada a Ollama (temperatura 0.7). El mensaje de sistema incluye las entidades de dominio, las acciones disponibles (`ActionRegistry.get_actions_for_llama()`) y el contexto del sistema (`src/tools/os_info.py`, que tarda unos 0,5 s por la medicion de CPU). No envia historial: cada llamada empieza de cero.
- `ACTION_ALIASES` traduce nombres que inventa el LLM (`open_chrome` -> `abrir_chrome`, `calibrate_chrome` -> `calibrar_chrome`...).
- Sin uso desde `main.py`: `process_intent_to_execution` y `process_with_htn` (via HTN), `execute_goal`, y `think_with_image`/`analyze_image` (codigo sin uso).
- Guarda cada interaccion en `data/memory/conversational_memory.json` y la ultima intencion en `world_state.json`.

#### `htn_integration.py` - puente con HTN

`get_htn_integration()` -> `HTNBrainIntegration`:

- `create_and_execute_htn_goal(texto)`: crea un `Goal` por palabras clave (calibrar, abrir chrome/youtube, navegar, buscar).
- `process_goal_through_htn(goal, estado)` -> `HTNIntegrationResult`: lo descompone con `HTNManager` y lo ejecuta con `TaskExecutor`.

Solo lo usa `Brain` en metodos que `main.py` no llama.

### 5.2 Oido (`src/ear/listener.py`)

`Ear(model_size="medium", language="es")` y `listen()`, que espera hasta oir una frase y devuelve el texto.

**Como escucha:**

1. Abre el microfono a 16 kHz, mono, en bloques de 30 ms.
2. Calibra el umbral de ruido (mediana de energia x 3, minimo 0.01). Como la calibracion lee la cola justo al abrir el microfono, casi siempre usa 0.01.
3. Espera hasta 30 s a que la energia supere el umbral (y vuelve a empezar si no).
4. Graba hasta 0,8 s de silencio o 10 s en total.
5. Transcribe con `faster-whisper` (CPU, `int8`, `beam_size=5`, espanol) y una lista fija de palabras de ayuda ("Jarvis, senor, abrir, YouTube, Google, LoL, Spotify...").

**Limitaciones:**

- El campo `confidence` es la probabilidad del idioma, no la de que la transcripcion sea correcta.
- Si Whisper no carga, la transcripcion devuelve `success=False` con un error y `listen()` sigue escuchando; nunca inventa texto.
- No usa el filtro de voz (VAD) de Whisper.
- El primer bloque de audio de cada frase se pierde.

Las clases `CalibrationNode`, `DetectionNode`, `RecordingNode` y `TranscriptionNode` modelan cada paso como un nodo con precondiciones, efectos y coste.

Funciona en Windows y en macOS (`sounddevice`); en macOS hace falta permiso de microfono.

### 5.3 Boca (`src/mouth/speaker.py`)

`Mouth()`:

- `speak(texto)`: sintetiza, reproduce y espera a que termine.
- `speak_async(texto)`, `get_available_voices()`, `set_voice(id)` (cambia la voz y la guarda en `data/voice_preference.json`), `get_current_voice()`.

**Como habla:**

1. Usa Kokoro (`models/onnx/model_fp16.onnx`) con la voz elegida (`models/voices/<id>.bin`).
2. Convierte el espanol a fonemas con reglas propias aproximadas (las voces de Kokoro son inglesas, asi que la pronunciacion es limitada).
3. Genera audio a 24 kHz y lo reproduce con `winsound`.
4. Si el modelo ONNX no carga (por ejemplo, si `models/onnx/` solo tiene los punteros de Git LFS), usa `pyttsx3` con la voz del sistema.

**Limitaciones:**

- **Solo Windows:** `import winsound` al cargarse. En macOS el modulo no se importa y JARVIS queda en modo texto.
- Los textos se recortan a 510 tokens.

### 5.4 Herramientas (`src/tools/`)

| Fichero | Que hace |
|---|---|
| `executor.py` | `UnifiedExecutor` (`get_executor()`), el ejecutor que usa `main.py`. `process_and_execute(respuesta)` busca el primer `[CMD: nombre(args)]`, convierte los argumentos segun los parametros de la accion y la ejecuta con `src/hands/actions/action_registry.py`. Devuelve el resultado como texto o un mensaje "Error...". Tambien: `execute_action`, `can_execute`, `get_command_suggestions(texto)` (hasta 5, por subcadena), historial de comandos. |
| `os_info.py` | Contexto del sistema para el LLM: CPU, RAM, disco, bateria, ventanas abiertas y ventana activa (`get_jarvis_system_context()`). Importa `pygetwindow` al cargarse. |
| `registry.py` | Un segundo registro de acciones, independiente del de `src/hands/actions/action_registry.py`. Nadie lo usa en ejecucion: lo que se registre aqui no lo ve ni `Brain` ni el ejecutor. |

## 6. Ojos: captura y vision (`src/eyes/`)

`from src.eyes import Vision, ScreenCapture, get_screen_capture` exporta la `Vision` ligera (`vision_only.py`) y la captura de `screen_capture.py`.

| Fichero | Que hace |
|---|---|
| `vision/vision.py` | `Vision(model=DEFAULT_VISION_MODEL)` (`qwen3-vl:8b-instruct`), la vision completa. `detect_ui_elements(imagen)` -> `VisionResponse` con elementos; `analyze_image(imagen, prompt)` -> JSON (la usa el calibrador universal); `verify_element_visibility` (un fallo de deteccion devuelve `success=False` con el error, no "no encontrado"), `verify_action_result`, `detect_application_state` (si no hay certeza devuelve cerrada, nunca abierta), `interpret_element_semantics(imagen, recorte)`, `analyze_screen_for_world_state()`. Llama a Ollama con salida JSON, `think=False`, temperatura 0 y `keep_alive` de 5 minutos. `VisionOpenCVProcessor` ofrece recortes, normalizacion, deteccion de cambios y ajuste de bordes; OpenCV solo da pistas de geometria, nunca decide si algo es interactivo. |
| `vision/vision_only.py` | `Vision` ligera (`analyze_image`, `verify_action_result`, `detect_application_state`). Siempre captura el monitor 1. |
| `capture/screen_capture.py` | `ScreenCapture` (`get_screen_capture()`): `capture_monitor(n)` (PNG temporal en la carpeta de trabajo, que no se borra aqui), `capture_region`, `capture_active_window`. Ademas, preparado para captura continua y solo usado por tests: `MssCapture`, `DXcamCapture` (solo Windows, con paso automatico a mss) y `AdaptiveCapture` (2 imagenes por segundo en reposo, rafagas de 15 cuando hay cambios, buffer de 8). |
| `capture/screen.py` | Modulo heredado. Lo que se usa son sus clases de datos: `ApplicationState`, `ApplicationInfo`, `WorldState` y las funciones de comparacion entre estado declarado y observado. Tiene otra `ScreenCapture` duplicada que nadie usa. |
| `detection/visual_ui_detector_fusion.py` | `VisualUIDetectorFusion().fuse(candidatos)` -> `FusionResult`: une los candidatos de UI Automation, OmniParser, PaddleOCR, OpenCV y Qwen3-VL sin duplicar elementos, conservando la evidencia de cada fuente y sus desacuerdos. La prioridad es UIA > Qwen3-VL > OmniParser > PaddleOCR > OpenCV. Nunca marca algo como interactivo solo por su forma. La usa `window_evidence_validator.py`; no esta conectada a la calibracion real. |

Hay dos nombres de modelo en uso: `qwen3-vl:8b-instruct` (`DEFAULT_VISION_MODEL` de `vision.py`, calibrador universal, manifiesto de detectores y `app_utils`) y `qwen3-vl:8b` (solo la `Vision` ligera de `vision_only.py`). `qwen3-vl:8b` es la variante con razonamiento: gasta la salida en `message.thinking` y deja `message.content` vacio, por eso no se usa para respuestas JSON.

Envio de imagenes a Qwen3-VL (`Vision._chat_json`, comun a todos los metodos de `vision.py`):

- Qwen3-VL usa un token visual por bloque de 32x32 pixeles. Una imagen de mas de `MODEL_IMAGE_MAX_PIXELS` (1920x1080) se reduce conservando la proporcion y se envia como PNG en memoria; las mas pequenas se envian por ruta. Una captura 4K completa (unos 8000 tokens) desbordaria el contexto de 8192.
- Si los tokens visuales estimados, el prompt y `num_predict` no caben en `num_ctx`, se usa el multiplo de 1024 suficiente.
- Con `timeout` (segundos; `analyze_image(..., timeout=, num_predict=)` lo pasa a `_chat_json`), la respuesta se lee en streaming y, al agotarse, se corta la conexion (Ollama deja de generar) y se devuelve lo recibido con `done_reason="timeout"`; sin `timeout`, una sola llamada como antes.
- `last_chat_info` guarda el tamano original y el enviado, `num_ctx`, `done_reason` y la longitud del contenido y del razonamiento. Una salida cortada (`done_reason=length`) o un contenido vacio con razonamiento se registran como aviso.

`detect_ui_elements(imagen, application=None, refine_with_opencv=False)`:

- Pide hasta `DETECTION_MAX_ELEMENTS` (60) elementos con `name`, `type`, `text`, `bbox`, `interactive` y `confidence`, con `bbox` en coordenadas normalizadas 0..1000 de la imagen completa (el formato de Qwen3-VL). El esquema JSON limita la lista con `maxItems`.
- Convierte cada caja a pixeles de la imagen original y calcula el centro; `bbox` y `center` del resultado estan siempre en pixeles de la imagen analizada, aunque al modelo se le haya enviado una copia reducida.
- Descarta cajas que no tengan 4 numeros, salgan de 0..1000, esten invertidas o queden sin area, y elementos repetidos (mismo nombre e IoU >= 0.9).
- Si el JSON llega cortado, recupera los elementos completos de la lista y marca `truncated`.
- `VisionResponse` lleva `elements`, `error` (None si la deteccion se completo, aunque no haya elementos), `image_size`, `model_image_size`, `discarded` y `truncated`. Imagen ilegible, error de Ollama, respuesta vacia o no interpretable dejan `elements` vacio, rellenan `error` y se registran como aviso; nunca se lanza la excepcion.

## 7. Manos: aplicaciones, calibracion y acciones (`src/hands/`)

Es el paquete mas grande. Esta dividido por responsabilidad:

| Subpaquete | Ficheros | Usado en ejecucion normal |
|---|---|---|
| `apps/` | `applications_core.py`, `application_preflight.py`, `application_discovery.py`, `application_launch_classifier.py`, `windows/` | Catalogo, preflight y apertura si; el descubrimiento solo en tests |
| `inventory/` | `system_inventory.py`, `system_inventory_storage.py`, `filesystem_observer.py`, `process_tree.py` | El primer escaneo al arrancar y la busqueda de rutas en el preflight |
| `calibration/` | `calibration_manager.py`, `calibrator.py`, `universal_visual_calibrator.py`, `coordinate_manager.py`, `get_coords.py` | Si (calibracion con Qwen3-VL) |
| `detection/` | `ui_automation_adapter.py`, `omniparser_adapter.py`, `paddleocr_adapter.py`, `detector_manifest.py`, `window_evidence_validator.py` | No, solo tests |
| `input/` | `keyboard.py`, `mouse.py` | Si |
| `actions/` | `action_registry.py`, `executor.py` | El registro de acciones si; el `Executor` de planes no |
| `browsers/` | `chrome/`, `edge/`, `firefox/` | Solo `chrome/` |
| `planner/` | seccion 8 | No |

**Plataforma:** `import src.hands` falla en macOS. `src/hands/__init__.py` importa `calibration_manager.py`, que al cargarse ejecuta `ctypes.windll` (solo existe en Windows). Todo lo que depende de `src.hands` hereda ese fallo.

### 7.1 `__init__.py`

`src/hands/__init__.py` reexporta `Executor`, `get_action_registry`, `register_action`, `register_module`, `ActionType`, `CalibrationManager`/`get_calibration_manager`, `CoordinateManager`/`get_coordinate_manager`, `get_application_manager`, `get_applications_by_capability`, `register_custom_application` y los modulos `chrome`, `keyboard` y `mouse`. Importar `chrome`, `keyboard` y `mouse` registra sus acciones en el `ActionRegistry`. (`chrome` se importa dos veces; no tiene efecto.)

### 7.2 Aplicaciones (`src/hands/apps/`)

#### `applications_core.py` - catalogo y apertura de aplicaciones

Es la capa que hoy abre y cierra aplicaciones de verdad.

- **`ApplicationManager`** (singleton `get_application_manager()`): al crearse registra Chrome y Spotify de serie y despues carga todas las entidades `type="application"` de `data/memory/entities.json`.
  - `get_application(nombre)`: busca por nombre normalizado (tabla fija es/en: "google chrome" -> `chrome`, "bloc de notas" -> `notepad`, "calculadora" -> `calculator`...), por clave exacta y por alias.
  - `resolve_application(nombre)` -> `ApplicationResolutionResult`: lo anterior mas coincidencia aproximada (`difflib`, umbral 0.7). Marca ambiguedad si otro candidato esta a menos de 0.05 y devuelve hasta 3 alternativas. `open_application` **no** usa esta funcion: un nombre mal escrito da "Aplicacion no encontrada".
  - `register_application(app)`: guarda la aplicacion en el catalogo (`app_<clave>`). `register_discovered_application` solo la guarda en memoria.
  - Consultas: `is_application_available`, `is_capability_available`, `is_application_open`, `get_applications_by_type`/`by_capability`, hechos observados frente a datos inferidos.
- **Acciones registradas:**
  - `open_application(nombre)`: resuelve el nombre, pasa el preflight, comprueba que el ejecutable existe, reutiliza el proceso si ya esta abierto y si no lanza `subprocess.Popen([ejecutable])` o abre la URL en el navegador. No verifica despues que aparezca la ventana. No usa el clasificador de tipos de lanzamiento (`.lnk`, AppX, URI).
  - `close_application(nombre)`: `taskkill /f /im` en Windows y `pkill -x` en macOS/Linux; despues comprueba que el proceso ya no existe.
  - `wait_for_application_state`: espera por tiempo; no comprueba el estado real.
- **Modelo de datos:** `ApplicationKnowledge` (nombre, tipo, ejecutable, URL, capacidades, elementos de interfaz, estados, login, politica de calibracion, requisitos de preflight), `ApplicationCapability` (open, close, navigate, search, type, click...), `ApplicationState` (closed, open, active, inactive, loading, ready, error, background), `UIElement`, `ApplicationClassification` (instalada, en ejecucion, registrada, automatizable, localizable).
- **Ventanas:** `verify_target_monitor`, `move_application_to_monitor`, `maximize_or_restore_application` usan APIs Win32.
- **Limitaciones conocidas:**
  - Las aplicaciones auto-registradas por el descubrimiento guardan la ruta en `properties.ruta_absoluta_observada`, pero aqui solo se lee `properties.executable`. Esas aplicaciones se cargan sin ejecutable y `open_application` no puede abrirlas.
  - `classify_application` pasa un objeto donde el preflight espera un diccionario, y por eso `automatable` siempre sale `False`.

#### `application_preflight.py` - validacion antes de abrir

Decide si una aplicacion se puede abrir o calibrar. No la ejecuta.

- `get_application_preflight().check(app_dict)` devuelve un diccionario con `allowed`, `reason`, `blocked_by`, `executable_path`, `requires_elevation`, `confidence`. `check_application` devuelve lo mismo como `PreflightResult`.
- **Orden de comprobaciones** (la primera que falla decide):
  1. Datos validos y nombre no vacio.
  2. Resolucion no ambigua.
  3. Nombre o `app_id` no bloqueados (herramientas administrativas: registro, servicios, firewall, programador de tareas, Hyper-V...; se compara por subcadena, asi que puede haber falsos positivos).
  4. Login requerido y confirmado; recursos disponibles.
  5. Se encuentra el ejecutable real: primero en `shell:AppsFolder` via PowerShell (hasta 10 s), despues en el inventario SQLite (solo `.exe` existentes; nombre exacto con y sin `.exe`; nunca rutas del almacen de componentes `\Windows\WinSxS\`), despues en PATH y por ultimo en la clave App Paths del registro (HKCU y HKLM), que localiza programas instalados fuera de PATH como `chrome.exe`. Si no hay ejecutable, se acepta una URL valida o un paquete verificado.
  6. El destino es valido (`validate_launch_destination`): `.exe`, `.lnk` o URI admitida (`ms-settings`, `microsoft-edge`, `ms-store`, `ms-windows-store`, `mailto`, `http`, `https`).
  7. El manifiesto del ejecutable no pide elevacion ni `uiAccess` (lee el `.manifest` o el recurso interno con `pefile`; sin manifiesto se permite con confianza media).
- **Plataforma:** solo Windows en la practica. En macOS no hay PowerShell ni `.exe`: todo termina en `executable_not_resolved` salvo las URL.

#### `platform_launch.py` y `launch_windows.py` - flujo unico de apertura

`ApplicationLaunchService.open(nombre)` resuelve (catalogo global o, si no esta, resolucion local del adaptador del SO), pasa el preflight, lanza y verifica proceso y ventana. Lo usa `UICalibrationPipeline` para abrir la aplicacion que calibra.

- **Catalogo con comando sin ruta** (por ejemplo `executable: "chrome"`): si el comando no esta en PATH pero el preflight resolvio y valido una ruta (`executable_path`), se lanza esa ruta como `.exe`.
- **Catalogo sin destino verificable en este equipo:** si el preflight no resuelve el ejecutable y la entrada del catalogo no tiene ejecutable ni URL, o solo un comando sin ruta (`notepad.exe`, `calc.exe`), se resuelve el nombre pedido en el equipo (`_resolve_locally`: PATH, menu Inicio/AUMID, App Paths) y se pasa el preflight del destino encontrado.
- **Varios destinos locales (`WindowsLaunchAdapter._from_resolution`):** por defecto es ambiguo y se pregunta. `preferir_destino_de_la_misma_aplicacion` solo elige cuando todos son la misma aplicacion del propio Windows: un unico paquete (AUMID) y el resto `.exe` de `%SystemRoot%` o de `WindowsApps` (se usa el AUMID; `System32\calc.exe` es un stub de la Calculadora empaquetada), o, sin paquetes, un unico `.exe` fuera de `WindowsApps` y el resto copias en `WindowsApps` con el mismo nombre de fichero (se usa el de fuera). La confianza del descubrimiento no rompe ambiguedades.
- **Paquetes del menu Inicio:** el `app_id` (AUMID `Familia!App`) de Get-StartApps se conserva en la clasificacion y el candidato descubierto; un candidato sin ruta pero con AUMID se trata como paquete lanzable y lo valida el preflight del destino (`check_launch_target`, shell:AppsFolder).
- **Reutilizacion:** solo se reutiliza una instancia con ventana visible. Si hay procesos con el nombre esperado pero ninguno tiene ventana (navegador residente en segundo plano), se lanza para obtener una ventana nueva.
- **Verificacion** (`ApplicationLaunchAdapter.verify`, espera acotada sin sleep fijo): ventana visible del PID lanzado o de procesos nuevos con el nombre esperado; para aplicaciones de instancia unica, una ventana NUEVA (no presente en la instantanea previa al lanzamiento) de un proceso que ya existia con ese nombre; para AUMID/URI sin nombre de proceso, una ventana nueva cuyo proceso tiene ese AUMID (`WindowsLaunchAdapter`: `GetApplicationUserModelId` sobre el proceso de la ventana y, en las apps alojadas en ApplicationFrameHost, sobre los procesos de sus ventanas hijas) y, si no se puede leer, una ventana nueva cuyo titulo contiene el nombre visible.
- **Procesos propios:** un proceso que ya existia antes de lanzar nunca se registra como abierto por JARVIS. La apertura recordada (idempotencia) deja de valer cuando su proceso termina o su ventana ya no existe.

### 7.3 Descubrimiento (`apps/`) e inventario (`inventory/`)

#### `application_discovery.py` - encontrar aplicaciones instaladas

Busca aplicaciones en fuentes del sistema, las clasifica y las valida sin lanzarlas. Lo usan `launch_windows.py` (resolucion local de `WindowsLaunchAdapter`) y `platform_launch.py`; `main.py` no lo llama directamente.

- `ApplicationDiscovery(...)`: `descubrir_todos()`, `buscar_por_nombre(nombre)`, `buscar_por_nombre_con_desambiguacion(nombre)`, `resolver_aplicacion_por_nombre(nombre)`, `auto_registrar_descubiertos()`, `registrar_candidatos(...)`, `verificar_aislamiento_inventario()`.
- **Fuentes, por orden de prioridad:** aplicacion ya abierta, catalogo conocido, menu Inicio, AppX, desinstaladores del registro, PATH (solo el primer nivel de cada carpeta), App Paths del registro y, por ultimo, el inventario SQLite. Si una fuente falla, las demas siguen.
- **Busqueda por nombre:** cada fuente se filtra por el nombre ANTES de aplicar su limite de resultados (`_fuentes_primarias(limite, nombre_filtro)`), y el inventario se consulta con el filtro en SQL (`search(name_contains=...)`), de modo que la aplicacion no depende de estar entre las primeras entradas. En PATH un ejecutable solo cuenta en la primera carpeta que lo contiene, como al ejecutarlo por nombre. Las rutas del almacen de componentes (`\Windows\WinSxS\`) no se proponen como candidatos.
- **Aplicaciones de Windows en cualquier idioma** (`aplicaciones_integradas_windows.py`): el menu Inicio, los titulos y los recursos de version estan traducidos. Para las aplicaciones que trae Windows (Bloc de notas, Calculadora, Paint, Explorador de archivos, Configuracion, Fotos, Camara, Reloj, Recortes, Grabadora, Microsoft Store, Terminal, Notas rapidas, Reproductor multimedia, Peliculas y TV, El Tiempo, Mapas, Panel de control, Mapa de caracteres, WordPad, Reproductor de Windows Media, Edge) la tabla da sus nombres en espanol e ingles y sus identificadores fijos (familia de paquete del AUMID, AUMID completo o `.exe`). Si el nombre pedido coincide exactamente (sin tildes ni mayusculas) con uno de ellos, la busqueda acepta tambien la entrada del menu Inicio con esa familia de paquete o con el nombre en el otro idioma, y el `.exe` en PATH/App Paths: "calculadora" encuentra "Calculator" en un Windows en ingles. Sin coincidencias parciales ("explorer" no trae "Internet Explorer"). No incluye herramientas que `CalibrationManager` trata como riesgo (Administrador de tareas, Lupa, Escritorio remoto). Las aplicaciones de terceros se llaman igual en todos los idiomas y no necesitan entrada.
- **Ambiguedad:** si hay varios candidatos y no exactamente una fuente de autoridad (abierta o catalogo), el resultado se marca como ambiguo y requiere preguntar al usuario.
- **Identidad estable** (nunca la ruta ni el idioma): `paquete:<AUMID>` (evidencia `paquete_id:` o `app_id` de Get-StartApps), `fabexe:<fabricante>:<ejecutable.exe>`, `fabprod:<fabricante>:<producto>` (solo sin `.exe` conocido), `nombre:<nombre>` o `candidato:<id>`. El producto no identifica: lo comparten aplicaciones distintas (todos los `.exe` de Windows, Word y Excel) y en Windows esta traducido. El clasificador nombra los `.exe` de `%SystemRoot%` por su `FileDescription` ("Bloc de notas" / "Notepad") y no por el producto comun. El auto-registro hace upsert en `data/memory/entities.json` sin inventar capacidades.
- **Limitaciones:** la confianza se guarda como texto en una columna numerica; cada candidato lanza un PowerShell (lento).

#### `application_launch_classifier.py` - tipo de lanzamiento

`LaunchClassifier.classify_candidate(candidato)` -> `LaunchClassification`:

- **Tipo de lanzamiento** (`LaunchType`): `ejecutable`, `acceso_directo`, `uri_aplicacion`, `paquete`, `bundle` (`.app` de macOS), `lanzador` (Steam, Epic...).
- **Subtipo** (`LaunchSubtype`): `gui_aplicacion`, `herramienta_cli`, `servicio`, `controlador`, `biblioteca`, `instalador`, `actualizador`, `desinstalador`, `componente_auxiliar`, `desconocido`. Se decide por extension, palabras en el nombre o la ruta y el subsistema del ejecutable.
- **Lanzable y confianza:** segun el tipo y la evidencia (version del fichero, ubicacion de instalacion, cabecera PE).
- `leer_version_archivo_windows` y `resolver_target_acceso_directo` solo funcionan en Windows.

#### `system_inventory.py` - contrato y escaneo del inventario

- `generate_machine_id()`: identificador del equipo a partir del nombre del equipo y el SO.
- `InventoryEntry`, `InventoryContract` (alcance, exclusiones, privacidad: nunca lee contenido de ficheros), exclusiones tecnicas (`$Recycle.Bin`, `pagefile.sys`, `/proc`, `/private/var/folders`...).
- Enumeracion de volumenes para Windows, Linux y macOS.
- `RecorridoVolumen`: recorrido iterativo con pausa, cancelacion y limites de CPU, memoria y disco. En Windows las junctions y enlaces simbolicos se reconocen por su reparse point (`tipo_enlace_entrada_windows`: etiqueta `MOUNT_POINT`/`SYMLINK` o bit "name surrogate") y se registran como `junction`/`symlink` sin recorrerse; los reparse points sin redireccion (carpetas de OneDrive, AppExecLink) se tratan como directorios o ficheros normales. Un directorio real se identifica por su propia ruta normalizada (sin `realpath`), asi que una junction hermana (`Documents and Settings`, `Archivos de programa`) no oculta `C:\Users` ni `C:\Program Files`. `conservar_entradas=False` evita guardar en memoria las entradas ya emitidas.
- `EscanerRutaVolumen` / `escanear_volumen` / `escanear_ruta`: escaneo con `scan_run` en SQLite e insercion por lotes sin retener entradas en memoria. Si la clave unica rechaza una ruta repetida dentro del mismo escaneo, el lote se reinserta entrada a entrada y la repetida cuenta como error `entrada_duplicada`. Ante una excepcion o una interrupcion manual, guarda el ultimo lote, cierra el `scan_run` como `error` o `interrumpido` (liberando el bloqueo) y propaga la excepcion.
- `es_ruta_almacen_componentes(ruta)`: True para rutas dentro de `\Windows\WinSxS\`.
- `GestorPrimerInventario`: `main.py` lo usa al arrancar. Si este equipo no tiene ningun escaneo correcto, lanza en segundo plano un **inventario completo de todos los volumenes**.
- Politicas de refresco, caducidad y retencion; validacion de rutas para lanzar.

#### `system_inventory_storage.py` - base de datos del inventario

`SystemInventoryStorage(db_path="data/system_inventory.sqlite3")`: esquema, migraciones y proteccion descritos en `docs/readme/README_DATA.md`. Metodos principales: `initialize`, `verificar_identidad_equipo`, `begin_scan_run`/`end_scan_run`, `insert_file_entries`, `insert_application_candidates`, `search` (filtros por nombre exacto, subcadena del nombre `name_contains` con comodines LIKE escapados, extension, tipo, volumen, solo volumenes montados; con filtro por nombre fija el indice anteponiendo `+` a los demas terminos y al ORDER BY: nombre exacto por `idx_file_entries_name`, subcadena con extension por `idx_file_entries_extension`, porque sin `ANALYZE` SQLite recorria toda la tabla por el indice de rutas; `search_by_name` y `count` aplican lo mismo), `buscar_candidatos_para_orden`, `revalidar_destino_aplicacion`, refrescos, deteccion de cambios, copias de seguridad, `write_manifest`.

Ojo: la ruta por defecto es relativa al directorio de trabajo, mientras que el preflight usa la ruta absoluta del proyecto. Si JARVIS no se arranca desde su carpeta, pueden usarse dos bases distintas.

#### `filesystem_observer.py` y `process_tree.py`

- `FileSystemObserver(callback)`: avisa de cambios en el disco con `watchdog`. Opcional y sin uso fuera de los tests.
- `process_tree.py`: utilidades de tests para Windows (`obtener_pids_por_nombre`, `esperar_pid_nuevo`, `cerrar_procesos_nuevos`) que cierran solo los procesos nuevos, nunca los del usuario.

### 7.4 Calibracion (`src/hands/calibration/`)

**Que significa calibrar en JARVIS hoy:** abrir o reutilizar la ventana de una aplicacion, capturar el monitor donde esta, pedir a Qwen3-VL que localice los elementos interactivos y guardar el centro de cada uno en `data/macros_coords.json`.

```
calibrate_application(app, monitor)
  -> refrescar monitores
  -> resolver la aplicacion (menu Inicio, AppX, registro)
  -> preflight
  -> reutilizar su ventana o lanzarla y esperar la ventana nueva
  -> rechazar si el proceso esta elevado
  -> restaurar, maximizar y traer al frente; mover a otro monitor si se pidio
  -> capturar el monitor completo (PNG temporal)
  -> UniversalVisualCalibrator: Qwen3-VL -> elementos con caja
  -> convertir a coordenadas absolutas del escritorio
  -> guardar en macros_coords.json["calibraciones"][app][elemento]["sN"]
  -> cerrar lo que abrio JARVIS o restaurar la ventana del usuario
```

#### `calibration_pipeline.py` - pipeline unico de calibracion

`UICalibrationPipeline(...).calibrate(app, monitor_reference=None, policy="product"|"test", depth="surface"|"deep"|"branch", reuse_window=True)` -> `CalibrationReport`. Lo usan la prueba real de calibracion y `delegate_legacy_calibration`. Etapas en orden (la primera que falla queda en `stage_failed`):

```
preflight (politica de calibracion) -> capabilities -> launch (ApplicationLaunchService.open)
  -> monitor (politica o referencia del usuario) -> window (mover, maximizar, primer plano)
  -> stability (capturas o arbol estables) -> environment -> accessibility (arbol UIA/AX)
  -> capture (mss del area visible de la ventana) -> detection (UIA + Qwen3-VL + OmniParser/PaddleOCR si estan)
  -> fusion -> quality_gate -> pointer_verification (mueve el puntero, nunca hace clic) -> persistence (SQLite)
  -> limpieza: borra temporales, devuelve el puntero, cierra lo que abrio o restaura la ventana del usuario
```

- **Qwen3-VL:** se envia una copia de la captura con el lado mayor <= `vision_max_side` (1600 px), se piden `vision_max_elements` (40) elementos con `num_predict = 60 x elementos + 400`, y la llamada tiene un presupuesto total de `vision_timeout` (300 s) con respuesta parcial (ver `vision.py`). Las cajas vuelven normalizadas 0..1000 y se convierten con el tamano de la captura original. Una respuesta cortada conserva los elementos completos (`UniversalVisualCalibrator._parse_response`, aviso y `metrics["qwen3vl"]["truncated"]`). Si Ollama no responde, la calibracion sigue con la accesibilidad.
- **Identificadores de control:** `id:<identificador de accesibilidad>` o `<tipo>:<nombre>`, con `@<rol nativo>` si lo hay. Si dos controles dan el mismo id (textos de OCR repetidos, controles sin nombre), se anade `#1`, `#2`... en orden de lectura (arriba-abajo, izquierda-derecha): el perfil exige ids unicos.
- **Foco antes del puntero:** si la ventana de prueba no esta en primer plano se reactiva una vez, se anota en `warnings` y `metrics["focus_restored"]` que aplicacion y PID tenian el foco, y `verify_before_action` comprueba despues foco, geometria, monitor e identidad.
- **Metricas** (`report.metrics`): `timings` por etapa, `total_seconds`, `candidates_by_source`, `qwen3vl` (tamano enviado, segundos, elementos), puerta de calidad, `pointer_checks`/`pointer_verified`.
- **Diagnostico previo en Windows:** `python scripts/diagnostico_calibracion_windows.py` (solo lectura, no abre aplicaciones): Python/SQLite, capacidades y monitores, Ollama y una llamada corta a Qwen3-VL con su latencia, verificacion del inventario al abrir, tiempo de `shell:AppsFolder` y resolucion de "calculadora"/"calculator"/"notepad".
- **Deteccion visual solo si hace falta:** con `visual_detectors="auto"` (por defecto) Qwen3-VL, OmniParser y PaddleOCR solo se usan si no hay arbol de accesibilidad o da menos de `min_accessible_controls` (5) controles accionables (`metrics["visual_detection"]` dice si se usaron y por que); `"always"`/`"never"` lo fuerzan. El manifiesto de detectores y los adaptadores se crean una vez por proceso (`detector_manifest.obtener_manifiesto`, `obtener_adaptador_omniparser`, `obtener_adaptador_paddleocr`): antes cada calibracion cargaba los modelos dos veces.
- **Profundidad (`depth="deep"`):** exploracion con `DeepUIExplorer` en modo clic (pestanas, menus y, con `explore_navigation=True`, elementos de navegacion dentro de `navigation_containers`, por defecto el panel NavigationView de WinUI); si la app la abrio JARVIS, las transiciones sin vuelta se resuelven reiniciandola. El mapa se guarda en `data/ui_maps/<machine_id>/<app>.json` (no se sube: `.gitignore`) y se reproduce cada camino con las coordenadas guardadas (`report.exploration["path_verification"]`, `ui_map_path`).
- **Procesos auxiliares sin consola:** las llamadas a `powershell`, `tasklist` y `taskkill` usan `CREATE_NO_WINDOW`, para que una consola nueva no quite el primer plano a la ventana calibrada cuando JARVIS no tiene consola propia.

#### `ui_exploration.py` y `ui_navigation_map.py` - mapa navegable y verificado

`DeepUIExplorer(adapter, policy, budget, interaction="accessibility"|"click", reset_root=None)` recorre la aplicacion en anchura desde el estado raiz: reproduce el camino de cada estado desde la raiz, ejecuta una accion segura, observa el resultado y vuelve comprobando que la interfaz es la de antes.

- **Acciones:** expandir, pestana, abrir menu, abrir dialogo (opcional) y `navigate` (seleccionar `ListItem`/`TreeItem` de una lista de navegacion; `ExplorationSafetyPolicy(allow_navigation=True, navigation_containers=...)`). Nunca: escribir, alternar, invocar hojas, opciones de desplegables (antepasado `ComboBox`) ni elementos fuera de los contenedores de navegacion indicados. Las etiquetas prohibidas (guardar, borrar, enviar...) en espanol e ingles se saltan y se informan.
- **Modo clic:** pestanas, menus y navegacion se pulsan con el raton en el centro de la caja del elemento; antes del clic `PointerVerifier` comprueba primer plano, posicion real del puntero y que el elemento bajo el puntero coincide con la caja. Si no, no hay clic.
- **Evidencia por transicion** (`UITransition.evidence`): metodo, punto, comprobacion del puntero y del elemento, estado antes y despues, `changed`, `element_key`. Una accion sin cambio queda como bucle con `changed=False` y en `no_effect`.
- **Vuelta:** colapsar, Escape, seleccionar el hermano previo (pestanas y navegacion), cerrar la ventana abierta o, si nada funciona y hay `reset_root` (solo apps abiertas por JARVIS), reiniciar la app y repetir la ruta. La comparacion de estados no depende de los ids de ventana (cambian al reiniciar).
- **Capa fisica** (`ExplorationResult.physical_states`): por estado, elementos interactivos visibles con `bbox` (escritorio) y `box_client_norm` (0..1 del area cliente de la ventana principal) y etiquetas `identificador|nombre` de lo visible.

`ui_navigation_map.py`:

- `build_navigation_map(resultado, app_key, machine_id, window, display)` -> JSON: `states` (profundidad, `path_from_root`, `labels`, `elements` con coordenadas), `transitions` con evidencia, `exploration` (acciones, segundos, reinicios, prohibidos, sin efecto, errores) y `path_verification`. `save_navigation_map` (escritura atomica en `data/ui_maps/<machine_id>/<app>.json`), `load_navigation_map`, `find_elements(mapa, "manolito")`.
- `UINavigator(explorer, mapa, window_id, pid, coordinates="live"|"stored")`: `go_to(estado)` reinicia a la raiz y sigue el camino paso a paso. Antes de cada clic localiza el elemento en el arbol de accesibilidad actual por su referencia logica (identificador o nombre, rol, padre, profundidad). Con `"live"` (por defecto) pulsa en su caja ACTUAL, de modo que un contenido desplazado (un contacto nuevo arriba) no lleva a otro elemento; si no lo localiza de forma unica usa la caja GUARDADA (normalizada al area cliente y recalculada sobre la ventana actual). Con `"stored"` usa siempre la guardada y, si el elemento esta en el arbol y el punto no cae en su caja actual, no pulsa. Despues `PointerVerifier` comprueba posicion real, ventana y elemento bajo el puntero, y tras el clic se verifica el estado: huella exacta o presencia de las etiquetas que distinguen el estado esperado del anterior ("Chat con Manolito" no pasa por "Chat con Lucia"). Cada paso (`StepEvidence`) anota `coordinate_source`, `identity_ok` y `stored_offset_px`. `click_stored`, `type_into(..., allow_text=True)` (solo apps propias de prueba). `verify_all_paths` reproduce todos los caminos siempre con coordenadas guardadas (prueba de que el mapa sirve) y anota el resultado en el mapa.
- `find_elements` compara sin mayusculas, acentos ni puntuacion.

#### `calibration_manager.py`

`get_calibration_manager()` -> `CalibrationManager`:

- `calibrate_application(app, screen_number=None)` -> `CalibrationResult`: sin monitor, calibra el monitor donde esta la ventana; con monitor, mueve antes la ventana alli.
- `calibrate_all_applications(applications=None, force=False)`: varias aplicaciones (maximo `calibration.max_applications`, por defecto 3), saltando las ya calibradas.
- `discover_applications()`: menu Inicio, accesos directos, AppX y desinstaladores via PowerShell (sin busqueda recursiva de disco).
- `launch_application(app)`, `move_window_to_monitor(...)`, `verify_visible_window_for_application(...)`, `wait_for_application_window(...)`, `is_application_calibrated(app)`, `get_calibration_statistics()`.
- **Reutilizar ventana:** puntua las ventanas abiertas (proceso esperado, titulo, tamano, foco) y reutiliza la mejor si supera el umbral; si no, lanza la aplicacion y espera una ventana nueva (10 s por defecto).
- **Seguridad:**
  - VS Code, juegos y herramientas administrativas se ignoran siempre. Las herramientas administrativas y de accesibilidad se reconocen por su nombre en espanol y en ingles (Administrador de tareas / Task Manager, Narrador / Narrator, Teclado en pantalla / On-Screen Keyboard, Editor del Registro / Registry Editor, Servicios / Services, etc.), porque el menu Inicio esta traducido.
  - Las ventanas creadas por JARVIS se cierran al terminar; las del usuario se restauran a su estado original.
  - En navegadores ya abiertos por el usuario se abre una pestana temporal con Ctrl+T y se cierra con Ctrl+W. Si el foco falla, esas teclas podrian ir a otra ventana.
- **Persistencia:** `data/macros_coords.json` (atomico) y `data/launch_evidence.json`.
- **Solo Windows** (Win32, PowerShell, `pygetwindow`).

#### `universal_visual_calibrator.py`

`UniversalVisualCalibrator.calibrate(app, monitor, ruta_captura)`:

- Pide a `qwen3-vl:8b-instruct` (via `src/eyes/vision/vision.py`) un JSON con hasta 80 elementos y su caja normalizada 0..1000.
- Descarta lo no interactivo, los tipos bloqueados (fondo, barra de tareas...), la confianza inferior a 0.30 y las cajas fuera del monitor.
- Convierte caja -> pixeles de la imagen -> pixeles del monitor -> coordenadas absolutas del escritorio virtual.
- No guarda nada. `CalibrationPolicy` bloquea IDE, consolas, juegos y herramientas de sistema.

#### `calibrator.py`

`get_enhanced_calibrator()` -> `EnhancedCalibrator`: capa para el planificador sobre `CalibrationManager`.

- `calibrate_applications(app=None, force=False)` calibra en todos los monitores.
- `check_element_calibration`, `calibrate_element_if_needed`, `get_element_coordinates`, `get_calibration_requirements_for_goal`.
- Estrategias: calibracion visual y atajo de teclado.
- Rechaza ejecutarse si el sistema no es Windows.

#### `coordinate_manager.py`

`get_coordinate_manager()` -> `CoordinateManager`: lee `data/macros_coords.json` y expone recursos de interfaz (`UIResource`) con sus coordenadas por monitor.

- `get_ui_resource("app.elemento")`, `get_resource_coordinates`, `get_calibrated_coordinate`, `validate_resource_for_action`, `get_calibration_strategy`, `screen_number_from_key("s2") -> 2`.
- `save_calibration` solo guarda en memoria y siempre en el monitor 1.
- Hoy ningun codigo de `src/` usa estas coordenadas para hacer clic.

#### `get_coords.py` - calibrador manual de la macro de Riot

`calibrar_api_key_riot_macro(screen_number=None)`: el usuario coloca el raton en 8 puntos y lo deja quieto 2 segundos en cada uno. Se guardan coordenadas absolutas por monitor en `data/macros_coords.json` (clave `macros.riot_api`), con escritura atomica y copia `.bak`. Script manual: no lo llama ningun modulo. La clave `macros` no coincide con la estructura actual del fichero (`calibraciones`/`legacy_data`).

#### Deteccion multi-fuente (`src/hands/detection/`, solo usada por tests)

Conjunto de piezas para detectar controles combinando accesibilidad, vision y OCR. Existen y tienen tests, pero `CalibrationManager` todavia no las usa.

| Fichero | Que hace |
|---|---|
| `ui_automation_adapter.py` | `UIAutomationAdapter.enumerate_window(hwnd, pid)` lee el arbol de controles de una ventana con UI Automation (`pywinauto`, y COM como respaldo). Solo lectura. `get_actionable_elements` filtra los que tienen patrones de accion (Invoke, Value, Toggle...). `classify_framework` identifica Win32, WinForms, WPF, UWP, Qt, Chromium/Electron, etc. Solo Windows. |
| `omniparser_adapter.py` | `OmniParserAdapter(model_path).detect(imagen)` detecta regiones que parecen interactivas con OmniParser V2 `icon_detect_v3` (torch, CUDA si hay). Nunca descarga el modelo por su cuenta. |
| `paddleocr_adapter.py` | `PaddleOCRAdapter(model_dir).detect(imagen)` lee texto con PaddleOCR (motor onnxruntime, PP-OCRv5). `associate_with_candidates` asocia etiquetas a controles cercanos sin convertir un texto en boton. |
| `detector_manifest.py` | `build_detector_manifest()` informa de que detectores estan realmente disponibles (UIA, OmniParser, PaddleOCR, Qwen3-VL, OpenCV), con version, pesos, dispositivo y licencia. Para Qwen3-VL comprueba en Ollama el mismo modelo que usa `vision.py` (`QWEN3VL_MODEL_DEFECTO` = `qwen3-vl:8b-instruct`). No descarga nada. |
| `window_evidence_validator.py` | `WindowEvidenceValidator(hwnd, pid).validate_all(...)` comprueba que el arbol, la captura y los candidatos pertenecen a la ventana objetivo y rechaza capturas del escritorio entero y cajas invalidas, solapadas o fuera de ventana. Solo Windows. |

La fusion de todas estas fuentes esta en `src/eyes/detection/visual_ui_detector_fusion.py` (seccion 6).

#### Navegadores y aplicaciones heredadas: `browsers/` y `apps/windows/`

Ya no calibran por su cuenta: delegan en `CalibrationManager.calibrate_application`.

- **`chrome/`** (`__init__.py`, `chrome.py`, `chrome_calibrator.py`): el unico en uso. Registra las acciones `abrir_chrome`, `abrir_chrome_pantalla`, `cerrar_chrome`, `calibrar_chrome`, `mover_chrome_pantalla`, `maximizar_chrome`. Las acciones se registran dos veces (en `chrome.py` y en `__init__.py`) y la segunda version de `calibrar_chrome` no tiene el parametro de pantalla.
- **`edge/`** (`edge.py`, `calibrator_edge.py`), **`firefox/`** (`firefox.py`, `calibrator_firefox.py`) y **`windows/`** (`windows.py`, `calibrator_windows.py`): codigo heredado que no importa nadie (salvo un test de `windows/`). Sus calibradores siempre informan exito aunque la calibracion falle.
- Los ficheros `*.bak_import` de `chrome/` son copias antiguas.

### 7.5 Acciones y ejecucion (`actions/` e `input/`)

#### `action_registry.py` - registro de acciones

Es el contrato entre lo que JARVIS sabe hacer y quien lo pide (el ejecutor heredado o el planificador).

- Decorador `@register_action(name, description, action_type, category, parameters, preconditions, effects, cost, success_checker, ...)`: registra una funcion. Si no se dan parametros, se sacan de su firma.
- `register_module("src.hands.browsers.chrome")`: registra todas las funciones decoradas de un modulo.
- `get_action_registry()` -> `ActionRegistry`: `get_action`, `get_all_actions`, `get_plannable_actions`, `validate_action(nombre, params)`, `can_execute(nombre, params, estado)`, `execute_action(nombre, params)`, `get_action_cost`.
- `ActionType`: `application`, `system`, `navigation`, `interaction`, `calibration`.
- Registrar otra vez el mismo nombre sobrescribe la accion anterior.

#### `executor.py` - ejecutor de planes

`get_executor()` -> `Executor`: ejecuta acciones sueltas, planes y objetivos.

- `execute_action(nombre, params, state, verify, timeout)`: valida, comprueba precondiciones, ejecuta y verifica el exito. Si vence el timeout, la accion ya iniciada no se cancela.
- `execute_plan(plan)`: nodo a nodo, con reintentos solo en acciones seguras y alternativas si un nodo falla.
- `execute_plan_with_replan(plan, goal)`: sustituye el nodo que falla por una alternativa.
- `execute_goal(goal)`: planifica con `Planner` y ejecuta.
- Envia los resultados al sistema de aprendizaje.
- **No es el ejecutor que usa `main.py`** (ver seccion 2).

#### `input/keyboard.py` y `input/mouse.py`

- **Teclado** (acciones registradas con precondiciones y coste): `type_text`, `press_key`, `execute_hotkey`, `copy_text`, `paste_text`, `cut_text`, `select_all_text`, `navigate_tab`, `navigate_enter`, `switch_window` (Alt+Tab), `close_window` (Alt+F4), `open_start_menu`, mas versiones en espanol (`escribir_texto`, `presionar_enter`...). Los atajos son de Windows (Ctrl, Alt, tecla Windows); en macOS harian falta los de Cmd. Al importarse configura `pyautogui.FAILSAFE` y `PAUSE`.
- **Raton:** `move_to_position(x, y)`, `click_element(button)` (mueve el puntero al destino, lee su posicion real, comprueba la ventana y el control bajo el puntero y aborta sin clic si supera la tolerancia medida), `scroll_at_position(x, y, clicks)`. Se registran como `move_mouse`, `click_mouse` y `scroll_mouse`.

## 8. Planificacion (`src/hands/planner/`)

Implementa la arquitectura objetivo (Goal -> HTN/Planner -> Plan -> Executor -> verificacion). **Hoy `main.py` no la usa** (ver seccion 2): se puede llamar desde codigo y los tests la cubren. Este paquete no depende de librerias externas.

### Como encajan las piezas

```
Goal (node.py)
 |-- Via A: Executor.execute_goal(goal)
 |      -> Planner.plan(goal, estado) -> PlanningResult (lista de nodos)
 |      -> Executor.execute_plan(plan) -> por nodo: precondiciones, accion, verificacion, efectos
 |
 '-- Via B: HTNBrainIntegration.process_goal_through_htn(goal)
        -> HTNManager.decompose_goal(goal) -> jerarquia de Task
        -> TaskExecutor.execute_task(task) -> ActionRegistry o Executor
```

### Ficheros

| Fichero | Que hace |
|---|---|
| `node.py` | Modelo de datos comun: `Node`, `Goal`, `Task`, `WorldState`, `NodeType` (intention, goal, task, action, condition, state, resource, application, ui_element, result, plan), `TaskStatus`. `Goal.is_achieved(estado)` dice si el objetivo ya se cumple; `Goal.get_required_capabilities()` da las capacidades necesarias segun el tipo (navigate, open_application, search...). |
| `preconditions_effects_types.py` | `Condition` (`ConditionType`: state_equals, state_exists, application_open, ui_element_calibrated, composite_and/or...) y `Effect` (state_set, state_increment, application_open/close, ui_element_calibrate...). Si fallan, lo hacen de forma segura: condicion invalida = falsa, efecto fallido = estado sin cambios. |
| `preconditions_effects.py` | `PreconditionsEffectsManager` (`get_preconditions_effects_manager()`): crea condiciones y efectos, verifica las precondiciones de una accion y aplica sus efectos. |
| `graph.py` | `StateGraph` y `AdvancedStateGraph` (con cache): grafo de estados y busqueda de rutas (A*, Dijkstra, BFS, DFS, voraz) sobre copias del estado, sin ejecutar nada. `find_route(...)` -> `RouteResult`. `GraphBuilder` crea grafos fijos de navegacion en Chrome. Exportar/importar grafo en JSON o pickle (no cargar pickles de origen no fiable). |
| `heuristic.py` | Heuristicas para A* (`HeuristicType`: goal_distance, capability_based, state_similarity, manhattan, euclidean, uniform, zero). Siempre devuelven un numero finito y positivo. |
| `planner.py` | `Planner.plan(goal, estado, nodos)` -> `PlanningResult`. Usa A* si hay grafo y si no un planificador determinista que busca, para cada capacidad que necesita el objetivo, el mejor nodo ejecutable (coste, tasa de exito, aplicacion abierta, recurso calibrado). Sin nodos propios usa 9 nodos fijos de Chrome y el conocimiento de aplicaciones. Tambien: `replan`, `plan_with_htn_integration`, validacion de recursos de interfaz y requisitos de calibracion. **No ejecuta.** |
| `htn_manager.py` | `HTNManager` (`get_htn_manager()`): descompone un `Goal` en tareas segun su tipo (navigate, navigate_stream, open_application, search, parallel_tasks), las ordena por dependencias y las ejecuta con `TaskExecutor`. El primer fallo detiene la jerarquia. |
| `task_executor.py` | `TaskExecutor` (`get_task_executor()`): ejecuta una `Task` a traves del `ActionRegistry` o delegando en el `Executor`. Exige confirmacion explicita de exito. Modos secuencial, paralelo, condicional y con alternativa. El timeout se comprueba al terminar, no interrumpe. |
| `application_integration.py` | `ApplicationKnowledgeIntegrator` (`get_application_knowledge_integrator()`): convierte el catalogo de aplicaciones en nodos (`app_<app>`, `<app>_<capacidad>`, `<app>_<elemento>`) y responde que aplicaciones tienen una capacidad. Se crea al arrancar `Brain`. |
| `learning_system.py` | `LearningSystem` (`get_learning_system()`): registra ejecuciones de acciones, nodos y planes y aprende costes, patrones y rutas. Solo guarda en disco si se llama a `export_learning_data(ruta)`. |
| `optimization.py` | `OptimizationManager`: cache de planes, quita pasos redundantes y elige alternativas sobre un `Planner`. |
| `optimization_config.py` | Configuracion tipada de la optimizacion. No la usa ningun codigo. |
| `goal_state_mapper.py` | Convierte un `Goal` y el estado en nodos y aristas del grafo. No lo usa ningun codigo. |
| `planner_integration.py` | `GraphPlannerIntegration`: otra forma de planificar con el grafo. No la usa ningun codigo. |
| `__init__.py` | Reexporta todo; carga los submodulos al primer uso para evitar importaciones circulares. |

### Limitaciones conocidas

- Las tareas que crea `HTNManager` se llaman `<goal.id>_<paso>` y `TaskExecutor` busca la accion por ese id, que no existe en el `ActionRegistry`. Salvo que la tarea traiga `metadata["action"]`, la ejecucion HTN falla.
- Hay varias implementaciones paralelas: tres ejecutores (`src/tools/executor.py`, `src/hands/actions/executor.py`, `task_executor.py`), cinco evaluadores de condiciones y dos formas de planificar con grafo. Ademas `Planner` crea su propio `LearningSystem`, distinto del que usa `Executor`.
- `src/memory/conversation.py` tiene su propia copia simplificada de `Node`, `Goal` y `Task`, que no es compatible con la de `node.py`.

## 9. Memoria (`src/memory/`)

`from src.memory import ...` exporta todo lo de `storage.py` y `entity_resolver.py`, y dos nombres de compatibilidad: `Memory` (= `ConversationMemory`) y `Storage` (= `JSONStorage`). Importar el paquete crea un `EntityResolver` global, que a su vez crea el `MemoryManager` y la carpeta `data/memory/`.

### `storage.py` - persistencia

- `JSONStorage(carpeta)`: un fichero por tipo de memoria (tabla en `docs/readme/README_DATA.md`). **`save()` no reemplaza, fusiona:** las listas se amplian, las entidades se actualizan por `id` y los diccionarios se mezclan.
- `MemoryManager` (`get_memory_manager()`, carpeta `data/memory/`) con cache en memoria (5 minutos):
  - Entidades: `save_entity` (upsert atomico), `get_entity`, `get_entities_by_type`, `find_entities`.
  - Conversacion: `add_conversational_memory`, `get_conversational_memory`.
  - Estado del mundo: `update_world_state`, `get_world_state`, `save_world_state`.
  - Planes, ejecuciones y estadisticas de aprendizaje.
  - Preferencias: `save_user_preference`, `get_user_preferences`, `learn_user_preference`.
  - Atributos de entidades y `export_memory`.
- Clases de datos: `Entity`, `ConversationalMemory`, `WorldState`, `Plan`, `ExecutionRecord`, `LearningStat`, `UserPreference`, `EntityAttribute`.

### `conversation.py` - `ConversationMemory` (la `Memory` de `main.py`)

- **Aliases:** al crearse carga los estaticos de `config/command_aliases.json` (una sola vez por proceso, con un indice por texto normalizado) y los aprendidos de `data/jarvis_learned_aliases.json`.
  - `get_alias(texto)` devuelve el comando de la frase o `None`. Ignora mayusculas, tildes, puntuacion y la palabra "jarvis", y consulta primero los aprendidos. Siempre devuelve un nombre de comando, nunca un objetivo.
  - `save_alias(texto, comando)` aprende una frase nueva y la guarda de forma atomica. Rechaza frases vacias y comandos que no sean un nombre de accion simple.
- **Historial:** `save_conversation(usuario, respuesta, goal, plan, resultado)` anade el turno y reescribe `data/conversational_memory.json` completo y de forma atomica, con los ultimos `max_history_length * 2` mensajes. Si `respuesta` esta vacia no guarda nada; por eso lo que oye `Ear` por si solo no se guarda. `get_conversation_history()` devuelve el historial sin entradas duplicadas y `clear_history()` lo vacia.
- `record_command_usage(...)` (solo en memoria, se pierde al cerrar) y `parse_user_input(texto)` -> `Goal` (patrones abrir/navegar/stream/cerrar/buscar).
- **`DomainMemory`:** carga `data/knowledge/entities.json`, `applications.json` y `capabilities.json`, y lee y guarda `data/user_preferences.json`.
- Incluye copias simplificadas de `Node`, `Goal`, `Task`, `NodeType` y `TaskStatus` (las usa `prediction.py`). No son las mismas clases que las de `src/hands/planner/node.py`.

### `entity_resolver.py` - `EntityResolver`

`resolve_entity(texto, contexto, tipo)` -> `EntityResolutionResult` (entidad, confianza, metodo, alternativas). Orden:

1. Catalogo global de aplicaciones (`ApplicationManager`): metodo `catalogo_global_aplicacion`, confianza 1.0.
2. Coincidencia exacta en la memoria.
3. Coincidencia aproximada (umbral 0.7).
4. Coincidencia por propiedades.
5. Si no encuentra nada, crea una entidad temporal (confianza 0.5).

Tambien resuelve URL, sugiere entidades y aprende preferencias. Lo usa `Brain`.

### `prediction.py` - memoria predictiva

`EnhancedPredictionMemory` (`get_prediction_memory()`):

- Registra objetivos y comandos ejecutados (exito, tiempo, coste, rutas, entidades) en `data/prediction_memory.json`, con escritura atomica.
- `predict_goal_from_input(texto, estado)` predice un objetivo.
- La usa `ActionRegistry` cada vez que ejecuta una accion. `main.py` no usa la prediccion (usa las sugerencias del ejecutor).

## 10. Nucleo, escritorio y experimental

### 10.1 Nucleo (`src/core/`)

| Fichero | Que hace |
|---|---|
| `config.py` | Configuracion (seccion 11). |
| `log.py` | Sistema unico de logs (seccion 11). |
| `ui_element_model.py` | Modelo comun de elemento de interfaz (abajo). |
| `test_result_categorizer.py` | `TestResultCategorizer` cuenta resultados de pruebas en cuatro categorias que nunca se suman entre si: `SIMULADO`, `UNIT_MOCKS`, `INTEGRACION_OS` y `APERTURA_GUI`. |
| `ollama_server.py` | Arranque y cierre del servidor local de Ollama (abajo). Lo usan `main.py` y los tests que necesitan Ollama real. |

`ollama_server.py`:

- `ensure_ollama_server(host=None, timeout=30, command=None, watch=True, register_atexit=True)` -> `OllamaServer`. La direccion sale de `host` o de `OLLAMA_HOST` (por defecto `http://127.0.0.1:11434`), con la misma regla que el cliente `ollama`. Si el servidor responde (`GET /api/version`), lo reutiliza con `started_by_us=False` y nunca lo cierra. Si no responde y la direccion es local, ejecuta `<ollama> serve` sin shell y sin ventana de consola en Windows, con `OLLAMA_HOST` = `host:puerto`, guarda su salida en un fichero temporal y espera, sin pausa fija, a que responda. Si la direccion no es local, no encuentra el ejecutable o el servidor termina o no responde en `timeout`, lanza `OllamaServerError` con el motivo y la salida de `ollama serve`.
- El ejecutable se busca en el PATH y, si no esta, en la instalacion por usuario de Windows (`%LOCALAPPDATA%/Programs/Ollama`).
- `OllamaServer.stop()` cierra el servidor y todos sus procesos hijos (los runners que cargan modelos), el vigilante y el fichero de salida, solo si `started_by_us`; es idempotente. Antes de terminar un proceso comprueba su PID y su hora de creacion, para no cerrar nunca un proceso que haya reutilizado el PID. `is_running()` indica si el servidor sigue disponible.
- Un servidor arrancado aqui se cierra tambien al salir del interprete (`atexit`) y, si el proceso que lo arranco muere sin poder limpiar, lo cierra el vigilante: `python -m src.core.ollama_server --watch ...`, un proceso aparte que cada segundo comprueba que su creador sigue vivo.
- `server_responds(host)`, `resolve_host(host)`, `is_local_host(url)` y `find_ollama_executable()` son las piezas que usa. Las comprobaciones de salud no pasan por el proxy del sistema. Nunca descarga modelos.

`ui_element_model.py`:

- `UIElementData` (pydantic): `name`, `type`, `description`, `text`, `bbox`, `center`, `coordinates`, `screen`, `interactive`, `visible`, `enabled`, `actions`, `identifier`, `confidence`, `calibrated`, `classification`. Metodos: `is_calibrated()`, `has_valid_geometry()`, `matches_name()`, `to_dict()`/`from_dict()`.
- `normalize_element_type(tipo)`: convierte el tipo libre del modelo de vision en `input`, `address_bar`, `field`, `text`, `element`, `button`, `link`, `menu`, `checkbox`, `radio`, `select` o `toolbar` (desconocido -> `element`).
- `classify_element(...)` -> `ElementClassification`: `offscreen` > `disabled` > `uia_actionable` > `text_label` > `container` > `visual_interactable_candidate` > `static_content`/`unknown`. Solo `uia_actionable` (patron de accion de UI Automation, habilitado y visible) acredita que el control se puede usar.

### 10.2 Escritorio (`src/desktop/screen_manager.py`)

`get_screen_manager()` -> `ScreenManager`, la fuente de verdad de la configuracion de pantallas.

- **Al crearse:** activa el modo DPI por monitor (Per-Monitor V2) y enumera los monitores con Win32. Cada `MonitorInfo` tiene rectangulo, tamano, principal o no, DPI efectivo, `scale_factor`, `index` (desde 0) y `monitor_id` (desde 1). Orden: primero el principal, despues por posicion; `s1` es siempre el principal.
- **Coordenadas:** pixeles nativos del escritorio virtual, sin resoluciones ni desplazamientos fijos.
- **Metodos:** `refresh_monitors()`, `get_monitor(n)`, `get_primary_monitor()`, `get_monitor_by_point(x, y)`, `get_monitor_for_window(ventana)`, `get_active_monitor()`, `move_window_to_monitor(titulo, n)`, `capture_monitor(n)` (PNG temporal), y funciones de Chrome (`open_chrome_on_monitor`, `close_chrome`, `get_chrome_windows`). Funciones de modulo: `get_monitor_info(n)`, `get_monitor_setup()`.
- **macOS:** importa `pyautogui` y `pygetwindow` al cargarse; sin Win32 usa los monitores de `config/config.json` y no puede preparar ventanas.

#### `monitor_topology.py` - modelo de topologia de monitores

`get_current_topology()` reenumera siempre los monitores por el contrato de plataforma (`src/desktop/platform_contract.py`) y construye un `MonitorTopology`; nunca reutiliza dimensiones historicas. Si el adaptador no puede enumerar levanta `TopologyUnavailableError`.

- **Datos:** `displays`, `fingerprint` (sha256 de identificador, geometria, resolucion, escala, DPI, rotacion, principal y espacio de coordenadas, independiente del orden de enumeracion) y `platform`.
- **Consultas:** `get(display_id)`, `primary()` (el marcado por el SO o el que contiene el origen 0,0; nunca el primero de la lista), `display_for_point`, `display_for_rect` (mayor area de interseccion), `display_for_window` (monitor declarado por el SO o mayor interseccion), `virtual_bounds()`.
- **Relaciones espaciales:** `relations(display_id)` devuelve los monitores a la izquierda, derecha, arriba y abajo: el otro monitor empieza donde acaba este (tolerancia de 2 unidades para redondeos) y comparte franja real en el otro eje; las listas van ordenadas por distancia entre centros.
- **Orden y numeracion:** `visual_order()` ordena por centro de izquierda a derecha y, en la misma columna, de arriba a abajo; `visual_number(display_id)` da el numero 1..N que usan las referencias habladas.
- **Clasificacion:** `largest()`/`smallest()` (empates dentro del 1%, desempate por area en pixeles fisicos), `portrait_displays()`, `landscape_displays()`, `central_displays()` (monitores que no son extremo; prioriza el centrado horizontal y, si ninguno cumple, el vertical) y `rightmost_non_primary()`.
- **Serializacion:** `to_dict()` exporta huella, plataforma, numero de monitores, limites del escritorio virtual y, por monitor, su `to_dict()` con numero visual y relaciones.
- **Cambios:** `diff_topologies(anterior, actual)` -> `TopologyChange` con monitores anadidos, quitados y campos modificados (geometria, area de trabajo, tamano de pixel, escala, DPI, rotacion, principal). `TopologyWatcher` fija una referencia con `baseline()`, la compara con `check()` (incluye los eventos recibidos del SO) y ofrece `assert_unchanged(fingerprint)`, la comprobacion obligatoria antes de una accion espacial; `start()` solo activa un listener del SO si el adaptador lo ofrece.
- **Politicas del mismo modulo:** `resolve_monitor_reference(texto, topologia, current_display_id)` resuelve referencias habladas (direccion, centro, tamano, orientacion, principal, "la otra", numero visual, nombre del monitor, relativas al actual) y devuelve `resolved`, `ambiguous` con candidatos o `not_found`; nunca adivina. `TargetMonitorPolicy` aplica la politica de producto y `TestMonitorPolicy` la de pruebas (monitor no principal mas a la derecha por geometria real).

### 10.3 Experimental (`src/experimental/`)

Modulos que el flujo normal de JARVIS no usa. Ninguno se importa al arrancar y ninguno crea hilos al importarse: `OptimizationSystem` solo se crea al llamar a `get_optimization_system()`.

| Grupo | Modulos |
|---|---|
| Logs avanzados (sustituidos por `src/core/log.py`) | `advanced_logger.py` (cola asincrona y SQLite; ya no crea ficheros `.log` propios), `jarvis_logging_system.py` (fachada con predictor y panel web), `log_dashboard.py` (panel Flask; muestra datos aleatorios), `log_predictor.py`, `log_analytics.py`, `log_integration.py`, `pattern_analyzer.py` |
| Optimizacion y automejora simuladas | `optimization_system.py` (antes `src/utils/__init__.py`), `performance_optimizer.py`, `self_improvement_system.py`, `adaptive_learning_engine.py` (PyTorch), `optimization_orchestrator.py`, `performance_monitor.py`, `gestor_errores_cometidos.py` |
| Adaptacion y aprendizaje (con tests) | `contextual_adaptation_engine.py` (por defecto guarda en `data/`, ver README_DATA), `contextual_pattern_recognizer.py`, `meta_learning_system.py`, `dynamic_resource_allocator.py`, `contextual_adaptation_audit.py`, `architectural_evolution_manager.py` |
| Monitorizacion y recuperacion (sin uso) | `alert_system.py`, `health_checker.py`, `health_monitor.py`, `metrics_collector.py`, `monitoring_dashboard.py`, `error_recovery.py`, `recovery_strategies.py`, `circuit_breaker.py`, `error_dashboard.py` |
| Utilidades de ventanas (solo Windows, sin uso) | `app_utils.py` |

## 11. Configuracion y logs

### 11.1 Configuracion (`src/core/config.py`)

Carga `config/config.json` en clases de datos tipadas (la instancia global es `config`). Si el fichero falta o esta mal, usa valores por defecto.

- **Por seccion:** `get_system_config`, `get_logging_config`, `get_keyboard_config`, `get_voice_config`, `get_memory_config`, `get_screen_config`, `get_timeout_config`, `get_predictive_config`, `get_calibration_config`, `get_chrome_config`, `get_element_types`.
- **Rutas:** `get_project_root`, `get_config_path`, `get_models_path`, `get_voices_path`, `get_macros_coords_path` (`data/macros_coords.json`), `get_voice_preference_path`.
- **Voz elegida:** `load_saved_voice_preference()` y `save_voice_preference(id)` sobre `data/voice_preference.json` (escritura atomica). La voz final es la guardada si existe su `.bin`; si no, la de `config.json`; si tampoco existe, `am_eric`.
- No lee variables de entorno. Las secciones de `config.json` estan en `docs/readme/README_DATA.md`.

### 11.2 Logs (`src/core/log.py`)

Un unico sistema, basado en el modulo estandar `logging`:

```python
from src.core.log import get_logger

logger = get_logger(__name__)
logger.info("Abriendo %s", nombre)
logger.warning("No se encontro %s", ruta)
logger.exception("Fallo al calibrar")   # dentro de un except: incluye la traza
```

- `setup_logging(level=None, log_file=None, console=True)` se llama una vez, en `main()`. Lee la seccion `logging` de `config/config.json`:
  - `level`: nivel minimo de la consola;
  - `log_file`: fichero que recibe todo desde DEBUG (por defecto `logs/jarvis.log`, relativo a la raiz del proyecto; rota a 5 MB y guarda 5 copias);
  - `format` y `datefmt`: formato del fichero.
- **Consola:** `12:30:01 INFO     hands.apps.applications_core: Abriendo chrome`. El prefijo `src.` se omite en los nombres.
- Las librerias ruidosas (urllib3, httpx, PIL, faster_whisper...) solo muestran avisos.
- Sin `setup_logging` (por ejemplo, en los tests) se aplica el comportamiento por defecto de `logging`: solo avisos y errores.
- **Normas:** sin `print` para diagnosticar, sin loggers propios con ficheros o bases de datos, sin mensajes de relleno. En un `except` que no relanza, se registra el error real.

## 12. Windows y macOS

El objetivo del proyecto es funcionar en Windows y en macOS. Hoy el codigo es practicamente **solo Windows**:

| Que | Por que no funciona en macOS |
|---|---|
| Todo `src.hands` | `calibration_manager.py` ejecuta `ctypes.windll` al importarse; `ui_automation_adapter.py` y `window_evidence_validator.py` importan `pywinauto`/`windll`. |
| Boca | `import winsound` en `speaker.py`. |
| Contexto del sistema y ventanas | `pygetwindow` (`os_info.py`, `screen_manager.py`, `coordinate_manager.py`...) no sabe manejar ventanas en macOS. |
| Preflight y descubrimiento | PowerShell, registro, `shell:AppsFolder`, solo `.exe`/`.lnk`. |
| Teclado | Atajos con Ctrl/Alt/Win en lugar de Cmd. |
| Monitores | La enumeracion real usa Win32; en otros sistemas se leen los monitores de `config.json`. |

Lo que ya es multiplataforma: oido (`sounddevice` + Whisper), vision con Ollama, el inventario de ficheros (tiene enumeracion de volumenes para macOS), `system_inventory_storage.py`, el planificador y la memoria.

El plan para que todo funcione en los dos sistemas (una capa de plataforma con un adaptador Windows y otro macOS) esta en `mejora/prompt_JARVIS_roadmap.txt`.

## 13. Problemas conocidos

Defectos encontrados al leer el codigo. No se han comprobado ejecutando JARVIS.

1. **La ruta HTN no ejecuta tareas reales:** `TaskExecutor` busca acciones con el id de la tarea (`<goal>_<paso>`), que no existe en el registro.
2. **Las aplicaciones auto-registradas no se pueden abrir:** guardan la ruta en `ruta_absoluta_observada` y `ApplicationManager` solo lee `executable`.
3. **`classify_application` nunca marca una aplicacion como automatizable** (pasa un objeto donde el preflight espera un diccionario).
4. **Los calibradores de Edge, Firefox y `windows/` siempre informan exito,** aunque la calibracion falle.
5. **`config.json` pide la voz `af_eric`, que no existe;** se usa `am_eric`.
6. **Dos rutas para la base del inventario** (relativa en `SystemInventoryStorage`, absoluta en el preflight).
7. **Solo 7 de los 29 comandos de `config/command_aliases.json` existen como acciones** (`abrir_chrome`, `abrir_chrome_pantalla`, `calibrar_aplicaciones`, `calibrar_chrome`, `cerrar_chrome`, `maximizar_chrome`, `mover_chrome_pantalla`). Los aliases del resto (`abrir_youtube`, `abrir_whatsapp`...) se ignoran.
8. **Codigo duplicado o sin uso:** dos registros de acciones (`src/tools/registry.py` y `src/hands/actions/action_registry.py`), tres ejecutores, dos `ScreenCapture`, dos familias de monitorizacion de salud, y modulos sin consumidores (`src/experimental/` y `planner_integration.py`, `goal_state_mapper.py`, `optimization_config.py`).

## 14. Como mantener este documento

- Describe solo el comportamiento actual y comprobable del codigo. No anotes fases, unidades del roadmap, fechas ni historial: eso va en `mejora/`.
- Cuando cambies un modulo de `src/`, actualiza su apartado. Si corriges un problema de la seccion 13, quitalo de la lista.
- Escribe sin tildes ni enes (regla 18 de `mejora/prompt_JARVIS_reglas.txt`).
- Todo el proyecto es ASCII puro. Si una cadena del codigo necesita un caracter acentuado para funcionar (por ejemplo, vocabulario que reconoce lo que dice el usuario), se escribe con escape: `"s\u00ed"`.
- No incluyas numeros de linea ni recuentos de lineas: se desactualizan enseguida.
- Si mueves o creas un modulo, actualiza el arbol de la seccion 4 y la seccion del paquete.
