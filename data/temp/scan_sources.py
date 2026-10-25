import re

files = [
    'src/hands/executor.py',
    'src/hands/calibrator.py',
    'src/hands/calibration_manager.py',
    'src/hands/applications_core.py',
    'src/hands/application_preflight.py',
]

for fpath in files:
    with open(fpath, encoding='utf-8') as f:
        content = f.read()
    classes = re.findall(r'class (\w+)', content)
    methods = re.findall(r'def (\w+)\(self', content)
    funcs = re.findall(r'^def (\w+)\(', content, re.MULTILINE)
    print(f'{fpath}: {len(content.splitlines())} lines')
    print(f'  Classes: {classes}')
    print(f'  Methods: {methods[:25]}')
    print(f'  Funcs: {funcs[:10]}')
    print()
