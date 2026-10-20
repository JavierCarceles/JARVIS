import marshal, importlib.util, sys
p = r'src\utils\__pycache__\contextual_adaptation_engine_backup.cpython-314.pyc'
raw = open(p,'rb').read()
code = marshal.loads(raw[16:])
print('top-level co_names:', [n for n in code.co_names][:40])
consts = [c for c in code.co_consts if not hasattr(c,'co_code')]
print('consts str:', [c for c in consts if isinstance(c,str)][:40])
print('submodules:', [c.co_name for c in code.co_consts if hasattr(c,'co_code')])
