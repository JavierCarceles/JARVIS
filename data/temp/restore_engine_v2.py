"""
Restauracion final de src/utils/contextual_adaptation_engine.py

Base   : original del 04/10 (API completa: ContextType, AdaptationLevel,
         ContextualFactor, ContextSnapshot, AdaptationRule, KnowledgeTransfer,
         AdaptationResult + motor con 110 metodos).
Anadido: los 16 metodos de HOY (persistencia de adaptacion de Goal).
Quitado: 2 lineas (pre-poblacion por contexto de 'adaptation_strategies'),
         porque hoy esa clave es global-plana y el test exige == {} al inicio;
         el codigo original la crea de forma lazy y la lee con .get(ctx, []).
"""
import ast
import io
import sys

ORIG = 'data/temp/orig_full.py'
TODAY = 'data/temp/cae_backup.py'
TARGET = 'src/utils/contextual_adaptation_engine.py'

orig = io.open(ORIG, encoding='utf-8', errors='replace').read()
today = io.open(TODAY, encoding='utf-8', errors='replace').read()
merged = orig

# --------------------------------------------------------------------------
# 1. knowledge_base: anadir las dos estructuras globales de Goal
# --------------------------------------------------------------------------
old = '''            "context_patterns": {},
            "adaptation_strategies": {},
'''
new = '''            "context_patterns": {},
            "adaptation_strategies": {},
            "goal_adaptation_feedback": [],
            "learning_results": [],
'''
assert merged.count(old) == 1, 'kb literal no encontrado'
merged = merged.replace(old, new, 1)

# --------------------------------------------------------------------------
# 2. Quitar la pre-poblacion por contexto de adaptation_strategies.
#    El codigo original la crea de forma lazy (_record_adaptation_result) y
#    la lee siempre con .get(contexto, []), por lo que no se pierde nada.
# --------------------------------------------------------------------------
old = '''            if "adaptation_strategies" not in self.knowledge_base or context_value not in self.knowledge_base["adaptation_strategies"]:
                self.knowledge_base["adaptation_strategies"][context_value] = []
'''
assert merged.count(old) == 1, 'pre-poblacion no encontrada'
merged = merged.replace(old, '', 1)

# --------------------------------------------------------------------------
# 3. __init__: aceptar data_dir y arrancar la persistencia de Goal
# --------------------------------------------------------------------------
old = '    def __init__(self, config_path: str = None):\n'
new = '    def __init__(self, config_path: str = None, data_dir: Optional[str] = None):\n'
assert merged.count(old) == 1, '__init__ no encontrado'
merged = merged.replace(old, new, 1)

old = '''        except Exception as e:
            self.logger.warning(f"No se pudo cargar configuraci\u00f3n persistente: {e}")

    # ------------------------------------------------------------------
    # Configuraci\u00f3n
'''
new = '''        except Exception as e:
            self.logger.warning(f"No se pudo cargar configuraci\u00f3n persistente: {e}")

        # --------------------------------------------------------------
        # Persistencia de adaptaci\u00f3n de Goal (2.8.8.9.2.x)
        # --------------------------------------------------------------
        self.data_dir = os.path.abspath(data_dir) if data_dir else os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data")
        )
        self._initialize_goal_adaptation_persistence()

    # ------------------------------------------------------------------
    # Configuraci\u00f3n
'''
assert merged.count(old) == 1, 'fin de __init__ no encontrado'
merged = merged.replace(old, new, 1)

# --------------------------------------------------------------------------
# 4. Adaptador de historial: las entradas de Goal son dicts, el motor original
#    usa AdaptationResult (objetos). El adaptador da acceso por clave Y por
#    atributo, para que ambos coexistan en self.adaptation_history.
# --------------------------------------------------------------------------
adapter = '''
class _MissingHistoryAttribute:
    """Valor por defecto tolerante para entradas de historial sin atributo."""

    value = 0

    def __bool__(self):
        return False

    def __float__(self):
        return 0.0

    def __int__(self):
        return 0

    def __eq__(self, other):
        return other in (0, 0.0, False, None, "")

    def __hash__(self):
        return hash(0)


class _AdaptationHistoryEntry(dict):
    """
    Entrada del historial de adaptaci\u00f3n de Goal.

    Es un dict (acceso por clave: entry["adaptation_id"]) que adem\u00e1s tolera
    el acceso por atributo que usa el motor original sobre AdaptationResult
    (entry.success, entry.confidence_score, entry.adaptation_level.value).
    """

    _DEFAULTS = {
        "success": False,
        "confidence_score": 0.0,
        "performance_impact": {},
    }

    def __getattr__(self, name):
        if name in self._DEFAULTS:
            return self.get(name, self._DEFAULTS[name])
        if name == "adaptation_level":
            return _MissingHistoryAttribute()
        if name == "adaptation_id":
            return self.get("adaptation_id", "")
        raise AttributeError(name)

    def to_dict(self):
        return dict(self)


'''

anchor = 'class ContextualAdaptationEngine:'
assert merged.count(anchor) == 1, 'clase no encontrada'
merged = merged.replace(anchor, adapter.lstrip('\n') + anchor, 1)

# --------------------------------------------------------------------------
# 5. Metodos de HOY: se anaden al final de la clase, verbatim (salvo el
#    historial, que se envuelve en _AdaptationHistoryEntry).
# --------------------------------------------------------------------------
t_orig = ast.parse(orig)
t_today = ast.parse(today)


def get_class(tree, name):
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == name:
            return n
    return None


cls_o = get_class(t_orig, 'ContextualAdaptationEngine')
cls_t = get_class(t_today, 'ContextualAdaptationEngine')
orig_names = {m.name for m in cls_o.body if isinstance(m, ast.FunctionDef)}

today_lines = today.splitlines(keepends=True)
blocks = []
for m in cls_t.body:
    if not isinstance(m, ast.FunctionDef) or m.name in orig_names:
        continue
    start = min([d.lineno for d in m.decorator_list] + [m.lineno]) - 1
    blk = ''.join(today_lines[start:m.end_lineno])
    blocks.append((m.name, blk))

assert len(blocks) == 16, 'se esperaban 16 metodos, hay %d' % len(blocks)

# Ajustes de compatibilidad en los metodos de HOY
adjusted = []
for name, blk in blocks:
    if name == '_record_adaptation_history':
        old = '            self.adaptation_history.append(history_entry)\n'
        new = '            self.adaptation_history.append(_AdaptationHistoryEntry(history_entry))\n'
        assert blk.count(old) == 1, name
        blk = blk.replace(old, new, 1)
    if name == '_load_goal_adaptation_feedback':
        old = '                    self.adaptation_history = feedback_data.get("adaptation_history", [])\n'
        new = ('                    self.adaptation_history = [\n'
               '                        _AdaptationHistoryEntry(entry)\n'
               '                        for entry in feedback_data.get("adaptation_history", [])\n'
               '                    ]\n')
        assert blk.count(old) == 1, name
        blk = blk.replace(old, new, 1)
    adjusted.append((name, blk))

# Insertar al final de la clase ContextualAdaptationEngine
lines = merged.splitlines(keepends=True)
cls_end = cls_o.end_lineno  # 1-based inclusivo (lineas del original)
tail = []
tail.append('\n')
tail.append('    # ------------------------------------------------------------------\n')
tail.append('    # Persistencia de adaptaci\u00f3n de Goal (2.8.8.9.2.x)\n')
tail.append('    # ------------------------------------------------------------------\n')
for name, blk in adjusted:
    tail.append('\n')
    tail.append(blk)

# cls_end corresponde al original; tras las ediciones el numero de linea
# puede variar, asi que se localiza por el final real de la clase.
merged_lines = merged.splitlines(keepends=True)
tree = ast.parse(merged)
cls_m = get_class(tree, 'ContextualAdaptationEngine')
end = cls_m.end_lineno  # 1-based

out = merged_lines[:end] + tail + merged_lines[end:]
merged = ''.join(out)

# --------------------------------------------------------------------------
# 6. Validar
# --------------------------------------------------------------------------
try:
    ast.parse(merged)
except SyntaxError as e:
    print('ERROR DE SINTAXIS:', e)
    sys.exit(1)

io.open(TARGET, 'w', encoding='utf-8', newline='').write(merged)
print('escrito: %s' % TARGET)
print('  lineas: %d' % merged.count('\n'))
print('  metodos anadidos de HOY: %s' % ', '.join(n for n, _ in adjusted))
