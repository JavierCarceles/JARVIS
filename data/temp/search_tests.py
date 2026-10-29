import os

base = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS'
tests_dir = os.path.join(base, 'tests')
for root, dirs, files in os.walk(tests_dir):
    for fn in files:
        if fn.endswith('.py'):
            path = os.path.join(root, fn)
            with open(path, encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    low = line.lower()
                    if 'plan' in low and 'assert' in low:
                        rel = os.path.relpath(path, base)
                        print(f'{rel}:{i}: {line.rstrip()[:150]}')
