import re

with open('src/hands/application_preflight.py', encoding='utf-8') as f:
    content = f.read()

for method_name in ['def __init__', 'def check', 'def check_application', 'def is_safe_to_calibrate', 'def _name_is_blocked', 'def resolve_executable', 'def inspect_executable_manifest']:
    match = re.search(r'def ' + method_name + r'\(.*?(?=\n    def |\n    @|\nclass )', content, re.DOTALL)
    if match:
        print(f'=== {method_name} ===')
        print(match.group()[:500])
        print()
