import re, os, sys

base = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS\src'
for root, dirs, files in os.walk(base):
    for fn in files:
        if fn.endswith('.py'):
            path = os.path.join(root, fn)
            with open(path, encoding='utf-8') as f:
                content = f.read()
            if '@register_action' not in content:
                continue
            # Find all register_action decorators and their name parameter
            for m in re.finditer(r'@register_action\((.*?)\)\s*\ndef\s+(\w+)', content, re.DOTALL):
                args = m.group(1)
                name_m = re.search(r'name\s*=\s*["\'](\w+)["\']', args)
                name = name_m.group(1) if name_m else m.group(2)
                planner_m = re.search(r'planner_enabled\s*=\s*(True|False)', args)
                if planner_enabled := (planner_m.group(1) if planner_m else None):
                    planner_val = planner_enabled
                elif 'planner_enabled' in args:
                    planner_val = 'False'
                else:
                    planner_val = 'True (default)'
                rel = os.path.relpath(path, base)
                print(f'{rel}: name={name} func={m.group(2)} planner_enabled={planner_enabled}')
