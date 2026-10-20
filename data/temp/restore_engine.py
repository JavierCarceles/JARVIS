"""
Restauracion de src/utils/contextual_adaptation_engine.py

Base: original del 04/10 (Recycle Bin, 6811 lineas, API completa:
      ContextType, AdaptationLevel, ContextualFactor, ContextSnapshot,
      AdaptationRule, KnowledgeTransfer, AdaptationResult + motor con 110 metodos)
+ Incorpora el trabajo de HOY (persistencia de adaptacion de Goal, 16 metodos)
  que se perdio al sobrescribir el fichero.

Criterio de fusion:
  - Las 7 clases/enums del original se conservan intactas.
  - Los 110 metodos del motor original se conservan intactos.
  - Los 16 metodos de hoy se anaden al final de la clase (sin colisiones: solo
    colisiona __init__, que se resuelve integrando ambas firmas).
  - knowledge_base: el original usa claves por contexto; hoy anade
    'goal_adaptation_feedback', 'learning_results' y 'adaptation_strategies'
    en formato global. Se respetan ambos: las claves globales se anaden
    sin tocar el esquema original por contexto.
"""
import ast
import io
import os
import re
import sys

ORIG = 'data/temp/orig_full.py'
TODAY = 'data/temp/cae_backup.py'
TARGET = 'src/utils/contextual_adaptation_engine.py'

orig = io.open(ORIG, encoding='utf-8', errors='replace').read()
today = io.open(TODAY, encoding='utf-8', errors='replace').read()

# --- 1. Localizar la clase ContextualAdaptationEngine en el original ---
lines = orig.splitlines(keepends=True)
t_orig = ast.parse(orig)
cls = None
for n in t_orig.body:
    if isinstance(n, ast.ClassDef) and n.name == 'ContextualAdaptationEngine':
        cls = n
        break
assert cls is not None, 'No se encontro ContextualAdaptationEngine en el original'

cls_start = cls.lineno - 1            # indice 0-based de 'class ContextualAdaptationEngine:'
cls_end = cls.end_lineno              # 1-based, inclusivo

# --- 2. Localizar los metodos de HOY (solo los 16 nuevos) ---
t_today = ast.parse(today)
cls_today = None
for n in t_today.body:
    if isinstance(n, ast.ClassDef) and n.name == 'ContextualAdaptationEngine':
        cls_today = n
        break
assert cls_today is not None

orig_methods = {m.name for m in cls.body if isinstance(m, ast.FunctionDef)}
new_methods = [m for m in cls_today.body
               if isinstance(m, ast.FunctionDef) and m.name not in orig_methods]
print('metodos a incorporar de HOY: %d' % len(new_methods))
for m in new_methods:
    print('   +', m.name)

today_lines = today.splitlines(keepends=True)

def extract_method(node):
    """Extrae el bloque de texto del metodo (decoradores + def + cuerpo)."""
    start = min([d.lineno for d in node.decorator_list] + [node.lineno]) - 1
    end = node.end_lineno
    return ''.join(today_lines[start:end])

blocks = []
for m in new_methods:
    blk = extract_method(m)
    # normalizar indentacion: en el fichero de hoy los metodos estan a 4 espacios
    # dentro de la clase -> identico a como deben quedar en el original.
    blocks.append(blk)

# --- 3. Construir el __init__ unificado ---
# Original: __init__(self, config_path: str = None)
# Hoy     : __init__(self, data_dir: Optional[str] = None)
init_today = [m for m in cls_today.body if isinstance(m, ast.FunctionDef)
              and m.name == '__init__'][0]
init_today_blk = extract_method(init_today)

# Extraer del __init__ de HOY la parte de persistencia de Goal (data_dir,
# knowledge_base con claves globales, _initialize_goal_adaptation_persistence).
today_init_lines = today_lines[init_today.lineno - 1:init_today.end_lineno]
print('\n__init__ de HOY:')
for l in today_init_lines:
    print('   |', l.rstrip())

# --- 4. Ensamblar ---
out = list(lines[:cls_start])          # cabecera + imports + enums/dataclasses
out.append(lines[cls_start])            # 'class ContextualAdaptationEngine:'
out.append(lines[cls_start + 1])        # docstring de la clase (linea siguiente)
body_original = lines[cls_start + 2:cls_end]
out.extend(body_original)

# anadir los metodos de hoy al final de la clase
out.append('\n')
out.append('    # ------------------------------------------------------------------\n')
out.append('    # Persistencia de adaptacion de Goal (2.8.8.9.2.x)\n')
out.append('    # ------------------------------------------------------------------\n')
for blk in blocks:
    out.append('\n')
    out.append(blk)
out.append('\n')

merged = ''.join(out)

# 5. Ajustar el __init__ del original para soportar data_dir y las claves
#    globales de knowledge_base, preservando su comportamiento original.
merged = merged.replace(
    '    def __init__(self, config_path: str = None):\n',
    '    def __init__(self, config_path: str = None, data_dir: Optional[str] = None):\n',
    1)

# 5a. tras _initialize_knowledge_base(), inyectar data_dir + claves globales
old_init_tail = """        self._initialize_adaptation_rules()
        self._initialize_knowledge_base()
"""
new_init_tail = """        self._initialize_adaptation_rules()
        self._initialize_knowledge_base()

        # Directorio de persistencia de adaptacion de Goal (opcional).
        self.data_dir = os.path.abspath(data_dir) if data_dir else os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'data')
        )

        # Estructuras globales de persistencia de adaptacion de Goal.
        # Se anaden sin alterar el esquema original por contexto.
        if "goal_adaptation_feedback" not in self.knowledge_base:
            self.knowledge_base["goal_adaptation_feedback"] = []
        if "learning_results" not in self.knowledge_base:
            self.knowledge_base["learning_results"] = []
        if "goal_adaptation_strategies" not in self.knowledge_base:
            self.knowledge_base["goal_adaptation_strategies"] = {}
"""
assert old_init_tail in merged, 'No se localizo el final de __init__ del original'
merged = merged.replace(old_init_tail, new_init_tail, 1)

# 5b. el metodo _update_adaptive_strategies de HOY escribe en
#     knowledge_base["adaptation_strategies"] (por contexto en el original).
#     Redirigirlo a la clave global "goal_adaptation_strategies".
merged = merged.replace(
    '        self.knowledge_base["adaptation_strategies"] = strategies\n',
    '        self.knowledge_base["goal_adaptation_strategies"] = strategies\n')
merged = merged.replace(
    '        self.knowledge_base["adaptation_strategies"] = learning_data.get("adaptation_strategies", {})\n',
    '        self.knowledge_base["goal_adaptation_strategies"] = learning_data.get("adaptation_strategies", {})\n')

# 5c. _load_goal_adaptation_feedback / _load_goal_adaptation_learning_results
#     deben escribir tambien en las claves que leen los tests.
merged = merged.replace(
    '        self.knowledge_base["learning_results"] = learning_data.get("learning_results", [])\n',
    '        self.knowledge_base["learning_results"] = learning_data.get("learning_results", [])\n')

# 5d. _save_goal_adaptation_learning_results: persistir la clave global
merged = merged.replace(
    '            "adaptation_strategies": self.knowledge_base.get("adaptation_strategies", {}),',
    '            "adaptation_strategies": self.knowledge_base.get("goal_adaptation_strategies", {}),')

# 6. Validar sintaxis
try:
    ast.parse(merged)
    print('\nsintaxis OK')
except SyntaxError as e:
    print('ERROR DE SINTAXIS:', e)
    sys.exit(1)

io.open(TARGET, 'w', encoding='utf-8', newline='').write(merged)
print('escrito: %s (%d lineas)' % (TARGET, merged.count('\n')))
