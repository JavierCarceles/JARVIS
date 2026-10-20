import sys, traceback
print('step1', flush=True)
try:
    from importlib.machinery import SourcelessFileLoader
    import importlib.util
    p = r'src\utils\__pycache__\contextual_adaptation_engine_backup.cpython-314.pyc'
    loader = SourcelessFileLoader('cae_pyc', p)
    spec = importlib.util.spec_from_loader('cae_pyc', loader)
    old = importlib.util.module_from_spec(spec)
    sys.modules['cae_pyc'] = old
    print('step2 (modulo creado)', flush=True)
    loader.exec_module(old)
    print('step3 OK', flush=True)
    print('clases:', [n for n,v in vars(old).items() if isinstance(v,type)], flush=True)
except BaseException:
    traceback.print_exc()
    sys.stdout.flush()
