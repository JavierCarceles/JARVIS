import sys, io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.hands.planner.node import Task, TaskStatus, NodeType
sys.stdout = old_stdout
sys.stderr = old_stdout

task = Task(id='t1', name='test', description='test')
task.metadata = {'action': 'test_action', 'cost': 5.0}
task.parameters = {'param1': 'val1'}
task.application = 'Chrome'
print(f'task.metadata: {task.metadata}')
print(f'task.parameters: {task.parameters}')
print(f'task.application: {task.application}')
print(f'getattr metadata: {getattr(task, "metadata", None)}')
print(f'getattr parameters: {getattr(task, "parameters", None)}')

# Test dependencies
task2 = Task(id='t2', name='test2', description='test2', dependencies=['t1'])
print(f'task2.dependencies: {task2.dependencies}')

# Test with SimpleNamespace
from types import SimpleNamespace
sn_task = SimpleNamespace(id='sn1', name='sn_test', description='sn desc', metadata={'action': 'sn_action'}, parameters={}, application='Edge', dependencies=[])
print(f'sn_task.metadata: {sn_task.metadata}')
print(f'sn_task.dependencies: {sn_task.dependencies}')
