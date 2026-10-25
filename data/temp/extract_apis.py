import re, ast, sys

files = [
    'src/hands/action_registry.py',
    'src/hands/application_preflight.py',
    'src/hands/applications_core.py',
    'src/hands/calibrator.py',
    'src/hands/calibration_manager.py',
    'src/hands/executor.py',
    'src/utils/pattern_analyzer.py',
    'src/utils/performance_optimizer.py',
    'src/utils/meta_learning_system.py',
    'src/utils/self_improvement_system.py',
    'src/utils/architectural_evolution_manager.py',
    'src/utils/dynamic_resource_allocator.py',
    'src/utils/contextual_adaptation_engine.py',
    'src/utils/adaptive_learning_engine.py',
]

for fpath in files:
    try:
        with open(fpath, encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        print(f'\n=== {fpath} ({len(source.splitlines())} lines) ===')
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                print(f'  class {node.name}')
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        args = [a.arg for a in item.args.args]
                        print(f'    def {item.name}({", ".join(args)})')
            elif isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                print(f'  def {node.name}({", ".join(args)})')
    except Exception as e:
        print(f'\n=== {fpath} ERROR: {e} ===')
