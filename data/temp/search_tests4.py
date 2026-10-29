import os

base = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS'
tests_dir = os.path.join(base, 'tests')
for root, dirs, files in os.walk(tests_dir):
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            low = line.strip().lower()
            # Find real (non-mock) calls to .plan( 
            if '.plan(' in low and 'mock' not in low and 'patch' not in low:
                rel = os.path.relpath(path, base)
                print(f'{rel}:{i}: {line.rstrip()[:200]}')
