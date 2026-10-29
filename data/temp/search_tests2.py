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
            low = line.lower()
            # Find tests that call real planner methods and check plan actions
            if ('planner.plan(' in low or 'build_application_aware_plan' in low) and 'assert' in low:
                rel = os.path.relpath(path, base)
                print(f'{rel}:{i}: {line.rstrip()[:180]}')
            # Also find assertions on plan action
            if ('result.plan' in low or 'result["plan"]' in low) and 'action' in low:
                rel = os.path.relpath(path, base)
                print(f'{rel}:{i}: {line.rstrip()[:180]}')
