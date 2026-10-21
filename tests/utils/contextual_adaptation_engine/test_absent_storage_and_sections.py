#!/usr/bin/env python3
"""
Tests de ALMACENAMIENTO AUSENTE y SECCION AUSENTE del subsistema de persistencia
del motor de adaptacion contextual (2.8.8.9.5.4).

CONTEXTO
Las hojas anteriores implementaron la DETECCION de lo que falta:
- 2.8.8.9.5.1 -> `detect_absent_storage()`: que fichero de persistencia falta.
- 2.8.8.9.5.2 -> `detect_absent_sections()`: que seccion falta dentro de un
  fichero EXISTENTE.
- 2.8.8.9.5.3 -> `no_data_behavior()`: el contrato DECLARATIVO del comportamiento
  del motor sin datos.
Esas tres hojas se verificaron con sondas de runtime independientes de la suite
pytest (`detect_absent_storage_real.py`, `detect_absent_sections_real.py` y
`no_data_behavior_real.py`). Esta hoja convierte esa cobertura en TESTS de la
suite pytest, de modo que la ausencia de datos quede fijada por la suite y no
solo por una sonda que se ejecuta a mano.

ALCANCE
Unicamente ALMACENAMIENTO AUSENTE y SECCION AUSENTE. No se comprueba aqui el
contrato declarativo de `no_data_behavior()` (2.8.8.9.5.3), ni la corrupcion del
contenido (2.8.8.9.6), ni la recuperacion parcial (2.8.8.9.7).

AISLAMIENTO
Todos los motores se crean con `data_dir` temporal (`tmp_path`), de modo que las
4 rutas de persistencia (`expected_storage_paths()`) caen en el temporal. El
`data/` de produccion solo se LEE, mediante rutas absolutas, para comprobar que
esta suite no lo modifica. Este aislamiento es obligatorio: en 2.8.8.9.4.6 se
corrigio una contaminacion de produccion causada por tests que creaban el motor
sin `data_dir`.

ADEMAS, el propio paquete `utils` es CONTAMINANTE AL IMPORTARSE: su
`__init__.py` crea un `optimization_system` global que instancia 4
`SelfImprovementSystem` (y un `AdaptiveLearningEngine`), cada uno con un hilo
que escribe con RUTAS RELATIVAS (`data/knowledge_graph.json`,
`data/improvement_rules.json`, `data/adaptive_performance.json`,
`models/adaptive_models/`) en el primer ciclo de aprendizaje. Y como el
conftest mete la raiz del repo en el `sys.path`, el paquete se importa DOS
veces (`utils.*` y `src.utils.*`), con 8 instancias en total.

Por eso este modulo:
  1. cambia el CWD a un temporal ANTES de importar `utils` (ninguna ruta
     relativa puede tocar produccion durante la importacion), y
  2. redirige a rutas absolutas temporales la configuracion de TODAS las
     instancias vivas de los dos paquetes (8 en total) justo despues de
     importar, de modo que los ciclos de aprendizaje posteriores tampoco
     escriban en produccion.
"""

import gc
import hashlib
import json
import os
import sys
import tempfile

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, '..'))
PRODUCTION_DATA_DIR = os.path.join(REPO_ROOT, 'data')

# --- AISLAMIENTO DE LAS RUTAS RELATIVAS DE LOS SUBSISTEMAS AJENOS ----------
# 1) El CWD se mueve a un temporal ANTES de importar `utils`: durante la
#    importacion (que instancia los singletons globales) ninguna ruta RELATIVA
#    puede tocar el `data/` de produccion.
# 2) Despues de importar, la configuracion de todas las instancias vivas pasa a
#    apuntar a rutas ABSOLUTAS temporales, de modo que los ciclos de aprendizaje
#    posteriores (que duermen 300 s) tampoco escriban en produccion.
DIR_AISLADO = tempfile.mkdtemp(prefix='jarvis_uit_5454_')
for _sub in ('data', 'models', 'logs'):
    os.makedirs(os.path.join(DIR_AISLADO, _sub), exist_ok=True)

RUTAS_AISLADAS = {
    # SelfImprovementSystem
    'knowledge_graph_path': os.path.join(DIR_AISLADO, 'data', 'knowledge_graph.json'),
    'learning_history_file': os.path.join(DIR_AISLADO, 'data', 'learning_history.json'),
    'rule_engine_path': os.path.join(DIR_AISLADO, 'data', 'improvement_rules.json'),
    'ml_model_path': os.path.join(DIR_AISLADO, 'models', 'learning_models'),
    # AdaptiveLearningEngine
    'model_save_path': os.path.join(DIR_AISLADO, 'models', 'adaptive_models'),
    'performance_history_file': os.path.join(DIR_AISLADO, 'data', 'adaptive_performance.json'),
}

CWD_ORIGINAL = os.getcwd()
os.chdir(DIR_AISLADO)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType  # noqa: E402
from utils.self_improvement_system import SelfImprovementSystem  # noqa: E402

CLASES_REDIRIGIBLES = ('SelfImprovementSystem', 'AdaptiveLearningEngine')


def clases_vivas(nombre):
    """Clases `nombre` de TODOS los paquetes importados (`utils.*` y `src.utils.*`)."""
    clases = {}
    for modulo in list(sys.modules.values()):
        if modulo is None:
            continue
        clase = getattr(modulo, nombre, None)
        if isinstance(clase, type) and clase.__name__ == nombre:
            clases[id(clase)] = clase
    return list(clases.values())


def redirigir_instancias_vivas():
    """Redirige la configuracion de las instancias YA CREADAS de los subsistemas.

    Importar el paquete `utils` instancia 4 `SelfImprovementSystem` y un
    `AdaptiveLearningEngine` por cada una de las dos copias del paquete
    (`utils.*` y `src.utils.*`): 8 en total. Cada una arranca un hilo que
    escribe con rutas RELATIVAS. Hay que redirigirlas nada mas importar.
    """
    clases = []
    for nombre in CLASES_REDIRIGIBLES:
        clases.extend(clases_vivas(nombre))
    ids_clases = {id(c) for c in clases}

    n = 0
    for objeto in gc.get_objects():
        if type(objeto).__name__ in CLASES_REDIRIGIBLES and id(type(objeto)) in ids_clases:
            config = getattr(objeto, 'config', None)
            if isinstance(config, dict):
                config.update(RUTAS_AISLADAS)
                n += 1
    return n


INstancias_redirigidas = redirigir_instancias_vivas()
os.chdir(CWD_ORIGINAL)

# Los 4 ficheros de persistencia que el motor espera (2.8.8.9.5.1).
STORAGE_KEYS = (
    "goal_adaptation_feedback",
    "goal_adaptation_learning_results",
    "adaptation_rules",
    "knowledge_base",
)

# Ficheros de PRODUCCION que esta suite NO debe modificar: los 4 de
# persistencia del motor y los de los subsistemas ajenos que el motor
# instancia (grafo de conocimiento, historial de aprendizaje, reglas
# personalizadas y rendimiento del motor adaptativo).
FICHEROS_DE_PERSISTENCIA = (
    "goal_adaptation_feedback.json",
    "goal_adaptation_learning_results.json",
    "contextual_adaptation_rules.json",
    "contextual_knowledge_base.json",
)
FICHEROS_DE_SUBSISTEMAS_AJENOS = (
    "knowledge_graph.json",
    "learning_history.json",
    "improvement_rules.json",
    "adaptive_performance.json",
)


# ------------------------------------------------------------------ aislamiento
@pytest.fixture(scope="module", autouse=True)
def _aislar_rutas_relativas_de_subsistemas_ajenos():
    """Saca del repo las rutas RELATIVAS de los subsistemas AJENOS al motor.

    `ContextualAdaptationEngine.__init__` instancia `SelfImprovementSystem`, que
    escribe con rutas RELATIVAS fijas (`data/knowledge_graph.json`,
    `data/learning_history.json`, `data/improvement_rules.json`,
    `models/learning_models`). Como no son parametrizables, cada motor creado por
    la suite modificaba el `data/` de PRODUCCION.

    Aqui se redirigen esas rutas a un temporal SOLO durante este modulo, para que
    los tests de esta hoja no ANADAN contaminacion. No se altera el
    comportamiento del motor bajo prueba: solo las rutas de salida de un
    subsistema que no participa en la deteccion de almacenamiento ausente.

    Se cubre por los DOS lados:
      - `_load_config` parcheado: los motores creados durante el modulo ya nace
        con las rutas redireccionadas.
      - `_save_knowledge_graph` parcheado: la redireccion se aplica en el
        MOMENTO DE ESCRIBIR, de modo que tambien cubre cualquier instancia que
        se haya creado con la ruta relativa original.
    Ademas, al IMPORTAR este modulo ya se redirigen las instancias vivas
    (`redirigir_instancias_vivas`), porque el paquete `utils` crea un
    `optimization_system` global con 4 `SelfImprovementSystem` en su interior
    ANTES de que exista cualquier fixture.
    """
    parches = []
    for clase in clases_vivas('SelfImprovementSystem'):
        original_load = clase.__dict__['_load_config']
        original_save = clase.__dict__['_save_knowledge_graph']

        def _load_config(self, config_path=None, _original=original_load):
            config = _original(self, config_path)
            config.update(RUTAS_AISLADAS)
            return config

        def _save_knowledge_graph(self, _original=original_save):
            self.config.update(RUTAS_AISLADAS)
            return _original(self)

        clase._load_config = _load_config
        clase._save_knowledge_graph = _save_knowledge_graph
        parches.append((clase, original_load, original_save))

    try:
        redirigir_instancias_vivas()
        yield DIR_AISLADO
    finally:
        for clase, original_load, original_save in parches:
            clase._load_config = original_load
            clase._save_knowledge_graph = original_save


# ------------------------------------------------------------------ utilidades
def nuevo_motor(data_dir):
    """Motor con el almacenamiento de persistencia ausente."""
    return ContextualAdaptationEngine(data_dir=str(data_dir))


def leer_json(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def escribir_json(path, payload):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def hashes_de_produccion():
    """Huella de los ficheros de PRODUCCION que esta suite no debe tocar (solo lectura)."""
    huellas = {}
    for nombre in FICHEROS_DE_PERSISTENCIA + FICHEROS_DE_SUBSISTEMAS_AJENOS:
        ruta = os.path.join(PRODUCTION_DATA_DIR, nombre)
        huellas[ruta] = sha256(ruta) if os.path.isfile(ruta) else None
    return huellas


def escribir_todo(motor):
    """Invoca los 4 escritores REALES del motor (almacenamiento completo)."""
    motor._save_goal_adaptation_feedback()
    motor._save_goal_adaptation_learning_results()
    motor._save_adaptation_rules()
    motor.save_knowledge_base()


# ================================================================ ALMACENAMIENTO AUSENTE
def test_el_motor_arranca_con_el_almacenamiento_ausente(tmp_path):
    motor = nuevo_motor(tmp_path)
    assert motor is not None
    assert len(motor.adaptation_rules) == 5


def test_la_carga_no_crea_los_ficheros_de_persistencia_ausentes(tmp_path):
    motor = nuevo_motor(tmp_path)
    assert motor.load_adaptation_rules() is True
    assert motor.load_knowledge_base() is True
    assert motor.load_all_data() is True
    for ruta in motor.expected_storage_paths().values():
        assert not os.path.isfile(ruta), ruta


def test_los_valores_por_defecto_no_son_nulos(tmp_path):
    motor = nuevo_motor(tmp_path)
    kb = motor.knowledge_base
    assert kb.get('goal_adaptation_feedback') == []
    assert kb.get('learning_results') == []
    assert motor.adaptation_history == []
    assert isinstance(kb.get('adaptation_strategies'), dict)
    assert kb.get('adaptation_strategies')
    for contexto, entradas in kb['adaptation_strategies'].items():
        assert isinstance(contexto, str)
        assert entradas == []


def test_las_apis_de_lectura_no_lanzan_excepcion_sin_almacenamiento(tmp_path):
    motor = nuevo_motor(tmp_path)
    assert isinstance(motor.get_engine_status(), dict)
    assert isinstance(motor.get_adaptation_summary(), dict)
    assert isinstance(motor.get_context_insights(), dict)
    assert isinstance(motor.get_adaptation_rules(), list)
    assert isinstance(motor.list_adaptation_rules(), list)
    assert isinstance(motor.get_available_strategies(ContextType.PRODUCTION), list)
    assert isinstance(motor.get_knowledge_transfers(), list)
    assert motor.load_adaptation_rules() is True
    assert motor.load_knowledge_base() is True
    assert motor.load_all_data() is True


def test_expected_storage_paths_declara_las_cuatro_rutas(tmp_path):
    motor = nuevo_motor(tmp_path)
    rutas = motor.expected_storage_paths()
    assert set(rutas) == set(STORAGE_KEYS)
    for ruta in rutas.values():
        assert os.path.isabs(ruta)
        assert os.path.abspath(str(tmp_path)) in os.path.abspath(ruta)


def test_detect_absent_storage_informa_de_las_cuatro_ausencias(tmp_path):
    motor = nuevo_motor(tmp_path)
    deteccion = motor.detect_absent_storage()
    assert deteccion['has_absent'] is True
    assert deteccion['absent_count'] == 4
    assert deteccion['present'] == []
    assert set(deteccion['absent']) == set(STORAGE_KEYS)
    for nombre, info in deteccion['absent'].items():
        assert info['path'] == motor.expected_storage_paths()[nombre]
        assert info['reason'] == 'file_not_found'


def test_detect_absent_storage_distingue_una_ruta_que_no_es_un_fichero(tmp_path):
    motor = nuevo_motor(tmp_path)
    directorio = os.path.join(str(tmp_path), 'knowledge_base_dir')
    os.makedirs(directorio, exist_ok=True)
    motor.config['knowledge_base_file'] = directorio
    deteccion = motor.detect_absent_storage()
    assert deteccion['absent']['knowledge_base']['reason'] == 'not_a_file'
    assert deteccion['absent_count'] == 4


def test_detect_absent_storage_es_de_solo_lectura(tmp_path):
    motor = nuevo_motor(tmp_path)
    rutas = motor.expected_storage_paths()
    motor.detect_absent_storage()
    motor.get_engine_status()
    for ruta in rutas.values():
        assert not os.path.isfile(ruta), ruta


def test_detect_absent_storage_con_almacenamiento_parcial(tmp_path):
    motor = nuevo_motor(tmp_path)
    motor._save_goal_adaptation_feedback()
    deteccion = motor.detect_absent_storage()
    assert deteccion['present'] == ['goal_adaptation_feedback']
    assert deteccion['absent_count'] == 3
    assert 'goal_adaptation_feedback' not in deteccion['absent']


def test_detect_absent_storage_con_almacenamiento_completo(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    deteccion = motor.detect_absent_storage()
    assert deteccion['absent_count'] == 0
    assert deteccion['has_absent'] is False
    assert sorted(deteccion['present']) == sorted(STORAGE_KEYS)


def test_get_engine_status_expone_la_deteccion_de_almacenamiento(tmp_path):
    motor = nuevo_motor(tmp_path)
    status = motor.get_engine_status()
    assert 'storage' in status
    assert status['storage']['absent_count'] == 4
    assert set(status['storage']['absent']) == set(STORAGE_KEYS)


def test_get_engine_status_conserva_las_claves_previas(tmp_path):
    motor = nuevo_motor(tmp_path)
    status = motor.get_engine_status()
    for clave in ('adaptation_enabled', 'is_adapting', 'current_context', 'adaptation_level',
                  'total_snapshots', 'total_rules', 'total_adaptations',
                  'total_knowledge_transfers', 'active_modes', 'knowledge_base_stats'):
        assert clave in status, clave


# ==================================================================== SECCION AUSENTE
def test_expected_storage_sections_declara_clase_de_cada_seccion(tmp_path):
    motor = nuevo_motor(tmp_path)
    secciones = motor.expected_storage_sections()
    assert set(secciones) == set(STORAGE_KEYS)
    for fichero, propias in secciones.items():
        assert propias, fichero
        for seccion, clase in propias.items():
            assert clase in ('data', 'metadata'), (fichero, seccion, clase)


def test_expected_storage_sections_devuelve_una_copia_independiente(tmp_path):
    motor = nuevo_motor(tmp_path)
    secciones = motor.expected_storage_sections()
    secciones['adaptation_rules']['rules'] = 'metadata'
    secciones['adaptation_rules']['invasada'] = 'data'
    assert motor.expected_storage_sections()['adaptation_rules'] == {
        'rules': 'data', 'total_rules': 'metadata', 'version': 'metadata', 'last_updated': 'metadata'}


def test_detect_absent_sections_detecta_una_seccion_de_datos_ausente(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['goal_adaptation_feedback']
    payload = leer_json(ruta)
    payload.pop('goal_adaptation_feedback')
    escribir_json(ruta, payload)
    deteccion = motor.detect_absent_sections()
    ausente = deteccion['absent']['goal_adaptation_feedback']
    assert set(ausente) == {'goal_adaptation_feedback'}
    assert ausente['goal_adaptation_feedback']['reason'] == 'section_not_found'
    assert ausente['goal_adaptation_feedback']['kind'] == 'data'
    assert ausente['goal_adaptation_feedback']['path'] == ruta


def test_detect_absent_sections_detecta_una_seccion_de_metadata_ausente(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['goal_adaptation_learning_results']
    payload = leer_json(ruta)
    payload.pop('last_updated')
    escribir_json(ruta, payload)
    deteccion = motor.detect_absent_sections()
    ausente = deteccion['absent']['goal_adaptation_learning_results']
    assert set(ausente) == {'last_updated'}
    assert ausente['last_updated']['kind'] == 'metadata'


def test_una_seccion_presente_pero_vacia_no_se_reporta_como_ausente(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['goal_adaptation_feedback']
    escribir_json(ruta, {'goal_adaptation_feedback': [], 'adaptation_history': [],
                          'last_updated': '2026-01-01T00:00:00'})
    deteccion = motor.detect_absent_sections()
    assert 'goal_adaptation_feedback' not in deteccion['absent']
    assert deteccion['absent_count'] == 0
    assert deteccion['has_absent'] is False


def test_varias_secciones_ausentes_en_el_mismo_fichero(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['goal_adaptation_feedback']
    escribir_json(ruta, {'adaptation_history': []})
    deteccion = motor.detect_absent_sections()
    assert set(deteccion['absent']['goal_adaptation_feedback']) == {
        'goal_adaptation_feedback', 'last_updated'}
    assert deteccion['absent_count'] == sum(len(v) for v in deteccion['absent'].values())


def test_con_el_formato_heredado_la_seccion_de_datos_se_considera_presente(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['adaptation_rules']
    escribir_json(ruta, [r.to_dict() for r in motor.adaptation_rules.values()])
    deteccion = motor.detect_absent_sections()
    ausente = deteccion['absent'].get('adaptation_rules', {})
    assert 'rules' not in ausente
    assert set(ausente) == {'version', 'last_updated', 'total_rules'}
    assert motor.load_adaptation_rules() is True
    assert len(motor.adaptation_rules) == 5


def test_un_fichero_ilegible_no_se_reporta_como_seccion_ausente(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['adaptation_rules']
    with open(ruta, 'w', encoding='utf-8') as handle:
        handle.write('{esto no es json')
    deteccion = motor.detect_absent_sections()
    assert 'adaptation_rules' not in deteccion['absent']
    assert deteccion['unreadable']['adaptation_rules']['reason'] == 'unreadable_file'


def test_un_payload_que_no_es_mapeo_se_informa_en_unreadable(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['adaptation_rules']
    escribir_json(ruta, 'no soy un mapeo')
    deteccion = motor.detect_absent_sections()
    assert deteccion['unreadable']['adaptation_rules']['reason'] == 'not_a_mapping'
    assert 'adaptation_rules' not in deteccion['absent']


def test_los_ficheros_ausentes_se_listan_en_missing_files_y_no_en_absent(tmp_path):
    motor = nuevo_motor(tmp_path)
    deteccion = motor.detect_absent_sections()
    assert set(deteccion['missing_files']) == set(STORAGE_KEYS)
    assert deteccion['absent'] == {}
    assert deteccion['absent_count'] == 0
    assert deteccion['has_absent'] is False
    assert deteccion['checked'] == []


def test_detect_absent_sections_es_de_solo_lectura(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    rutas = motor.expected_storage_paths()
    antes = {ruta: sha256(ruta) for ruta in rutas.values()}
    ficheros_antes = set(rutas.values())
    motor.detect_absent_sections()
    motor.get_engine_status()
    despues = {ruta: sha256(ruta) for ruta in rutas.values()}
    assert antes == despues
    assert ficheros_antes == set(rutas.values())


def test_get_engine_status_expone_la_deteccion_de_secciones(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['goal_adaptation_feedback']
    payload = leer_json(ruta)
    payload.pop('goal_adaptation_feedback')
    escribir_json(ruta, payload)
    status = motor.get_engine_status()
    assert 'storage_sections' in status
    assert status['storage_sections']['absent_count'] == 1
    assert 'goal_adaptation_feedback' in status['storage_sections']['absent']['goal_adaptation_feedback']


# ============================================ RELACION ENTRE LAS DOS DETECCIONES
def test_la_escritura_recrea_el_almacenamiento_ausente(tmp_path):
    motor = nuevo_motor(tmp_path)
    assert motor.detect_absent_storage()['absent_count'] == 4
    escribir_todo(motor)
    deteccion = motor.detect_absent_storage()
    assert deteccion['absent_count'] == 0
    assert deteccion['has_absent'] is False
    for ruta in motor.expected_storage_paths().values():
        assert os.path.isfile(ruta)
        with open(ruta, 'r', encoding='utf-8') as handle:
            json.load(handle)


def test_la_seccion_ausente_no_impide_la_carga_de_los_datos_presentes(tmp_path):
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    ruta = motor.expected_storage_paths()['goal_adaptation_learning_results']
    payload = leer_json(ruta)
    payload.pop('learning_results')
    escribir_json(ruta, payload)
    motor = nuevo_motor(tmp_path)
    assert motor.load_all_data() is True
    assert motor.get_engine_status()['total_rules'] == 5


# ================================================================= AISLAMIENTO
def test_este_test_no_modifica_los_ficheros_de_persistencia_de_produccion(tmp_path):
    antes = hashes_de_produccion()
    motor = nuevo_motor(tmp_path)
    motor.detect_absent_storage()
    motor.detect_absent_sections()
    motor.get_engine_status()
    escribir_todo(motor)
    motor.detect_absent_storage()
    motor.detect_absent_sections()
    despues = hashes_de_produccion()
    assert antes == despues


def test_los_4_ficheros_de_persistencia_de_produccion_no_cambian(tmp_path):
    """Los 4 ficheros que el motor declara como persistencia siguen intactos."""
    antes = hashes_de_produccion()
    motor = nuevo_motor(tmp_path)
    escribir_todo(motor)
    motor.detect_absent_storage()
    motor.detect_absent_sections()
    motor.get_engine_status()
    despues = hashes_de_produccion()
    for nombre in FICHEROS_DE_PERSISTENCIA:
        ruta = os.path.join(PRODUCTION_DATA_DIR, nombre)
        assert antes[ruta] == despues[ruta], nombre


def test_los_ficheros_de_los_subsistemas_ajenos_no_cambian(tmp_path):
    """El grafo de conocimiento y el historial de aprendizaje tampoco cambian.

    El motor instancia `SelfImprovementSystem`, que escribe con rutas relativas
    fijas. El fixture de este modulo las redirige a un temporal, de modo que la
    suite no anade contaminacion al `data/` de produccion.
    """
    antes = hashes_de_produccion()
    motor = nuevo_motor(tmp_path)
    motor.detect_absent_storage()
    motor.detect_absent_sections()
    motor.get_engine_status()
    despues = hashes_de_produccion()
    for nombre in FICHEROS_DE_SUBSISTEMAS_AJENOS:
        ruta = os.path.join(PRODUCTION_DATA_DIR, nombre)
        assert antes[ruta] == despues[ruta], nombre
