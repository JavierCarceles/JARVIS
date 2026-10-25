import sys, io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.hands.executor import Executor, ExecutionStatus, ExecutionResult, ExecutionState
from src.hands.action_registry import ActionInfo, ActionType, get_action_registry
from src.hands.planner.node import Task, TaskStatus
from src.hands.planner.htn_manager import TaskExecutionResult
sys.stdout = old_stdout
sys.stderr = old_stdout

exp = Executor()

# Test can_execute
print('can_execute type_text:', exp.can_execute("type_text"))
# Check _get_legacy_function
func = exp._get_legacy_function("type_text")
print('_get_legacy_function type_text:', func)
func = exp._get_legacy_function("nonexistent_cmd")
print('_get_legacy_function nonexistent:', func)
func = exp._get_legacy_function("")
print('_get_legacy_function empty:', func)

# Test _action_provides_capability
ai = exp.action_registry.get_action("type_text")
print('type_text ActionInfo:', ai)
if ai:
    print('has name:', getattr(ai, 'name', 'N/A'))
    print('has action_type:', getattr(ai, 'action_type', 'N/A'))
    print('has category:', getattr(ai, 'category', 'N/A'))
    print('has capabilities:', getattr(ai, 'capabilities', 'N/A'))
    # Test _action_provides_capability
    print('_action_provides_capability type_text for type_text:', exp._action_provides_capability(ai, "type_text"))
    print('_action_provides_capability type_text for typing:', exp._action_provides_capability(ai, "typing"))
    print('_action_provides_capability type_text for unknown:', exp._action_provides_capability(ai, "unknown"))
    print('_action_provides_capability for open_application:', exp._action_provides_capability(ai, "open_application"))

# Test _positional_to_named_parameters
ai2 = exp.action_registry.get_action("type_text")
if ai2:
    print('type_text parameters:', ai2.parameters)
    # positional args
    params = exp._positional_to_named_parameters(ai2, ("hello world",))
    print('positional params:', params)
    # too many args
    try:
        params = exp._positional_to_named_parameters(ai2, ("a", "b", "c", "d"))
        print('too many params:', params)
    except ValueError as e:
        print('too many args: ValueError')

# Test list_commands
commands = exp.list_commands()
print('list_commands type:', type(commands).__name__)
print('list_commands has type_text:', "type_text" in commands if commands else False)

# Test get_plannable_actions
plannable = exp.get_plannable_actions()
print('get_plannable_actions type:', type(plannable).__name__)
print('get_plannable_actions has type_text:', "type_text" in plannable if plannable else False)

# Test get_action_info
ai3 = exp.get_action_info("type_text")
print('get_action_info type_text is not None:', ai3 is not None)

# Test create_goal_from_command - detailed
goal = exp.create_goal_from_command('abrir_youtube', {})
print('goal type:', goal.type if goal else None)
print('goal target:', goal.target if goal else None)
print('goal id:', goal.id if goal else None)
print('goal description:', goal.description if goal else None)
print('goal metadata:', goal.metadata if goal else None)

goal = exp.create_goal_from_command('navegar_a', {'url': 'https://example.com'})
print('navegar_a goal:', goal.type, goal.target)

goal = exp.create_goal_from_command('buscar_en_google', {'query': 'test search'})
print('buscar_en_google goal:', goal.type, goal.target)

goal = exp.create_goal_from_command('cerrar_chrome', {})
print('cerrar_chrome goal:', goal.type, goal.target)

# Test _COMMAND_PATTERN
print('COMMAND_PATTERN:', exp._COMMAND_PATTERN.pattern)

# Test process_and_execute with no command
result = exp.process_and_execute("Hello world, no command here")
print('process_and_execute no command:', repr(result))

# Test execute_plan with non-list
result = exp.execute_plan("not a list")
print('execute_plan string:', result.status, result.error)

# Test execute_plan with None
result = exp.execute_plan(None)
print('execute_plan None:', result.status, result.error)

# Test _replan_after_failure - out of range
plan = [{"id": "n1", "action": "test", "cost": 1.0}]
new_plan = exp._replan_after_failure(plan, 5, {})
print('replan out of range same plan:', new_plan is plan)

# Test _replan_after_failure - no alternatives
plan = [{"id": "n1", "action": "test", "cost": 1.0, "alternatives": []}]
new_plan = exp._replan_after_failure(plan, 0, {})
print('replan no alternatives same plan:', new_plan is plan)

# Test _find_alternative_nodes
plan = [{"id": "n1", "action": "type_text", "cost": 1.0, "alternatives": []}]
alts = exp._find_alternative_nodes(plan[0], {})
print('find_alternative_nodes count:', len(alts) if alts else 0)

# Test get_task_executor singleton
from src.hands.planner.task_executor import get_task_executor
te1 = get_task_executor()
te2 = get_task_executor()
print('get_task_executor singleton:', te1 is te2)
