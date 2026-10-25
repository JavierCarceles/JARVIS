import sys, io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.hands.executor import Executor, ExecutionStatus, ExecutionResult, ExecutionState, get_executor
from src.hands.planner.node import Goal, NodeType
sys.stdout = old_stdout
sys.stderr = old_stdout
sys.stdout = sys.stderr  # send to stderr

import inspect
methods = [m for m in dir(Executor) if not m.startswith('_')]
print('Public Executor methods:', methods)
print('ExecutionStatus values:', [e.value for e in ExecutionStatus])

# Check create_goal_from_command returns
exp = Executor()
for cmd in ['abrir_youtube', 'abrir_chrome', 'navegar_a', 'buscar_en_google', 'type_text', 'close_application', 'unknown_cmd']:
    args = {'url': 'https://example.com'} if cmd == 'navegar_a' else {'query': 'test'} if cmd == 'buscar_en_google' else {}
    try:
        goal = exp.create_goal_from_command(cmd, args)
        if goal:
            print(f'create_goal {cmd}: type={goal.type}, target={goal.target}')
        else:
            print(f'create_goal {cmd}: None')
    except Exception as e:
        print(f'create_goal {cmd}: ERROR {e}')

# Check process_and_execute
result = exp.process_and_execute('type_text', {'text': 'hello'}, {})
print(f'process_and_execute type_text: {result}')

# Check can_execute
print(f'can_execute type_text: {exp.can_execute("type_text")}')
print(f'can_execute unknown: {exp.can_execute("unknown_action")}')

# Check list_commands
commands = exp.list_commands()
print(f'list_commands count: {len(commands)}')
print(f'list_commands sample: {commands[:3]}')

# Check get_current_state and update_state
state = exp.get_current_state()
print(f'get_current_state type: {type(state).__name__}')

exp.update_state({'test_key': 'test_value'})
updated = exp.get_current_state()
print(f'updated state has test_key: {"test_key" in updated}')
