import sys, logging
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
logging.disable(logging.CRITICAL)
from src.hands.planner.task_executor import TaskExecutor, TaskExecutorStatus, TaskExecutionMode, TaskExecutionConfig
from src.hands.executor import Executor, ExecutionStatus, ExecutionResult, ExecutionState
from src.hands.planner.node import Task, Node, NodeType, TaskStatus, Goal
from src.hands.planner.htn_manager import TaskExecutionResult
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock
import copy

# Test TaskExecutionConfig normalization
print('=== TaskExecutionConfig ===')
config = TaskExecutionConfig()
print(f'Defaults: max_retries={config.max_retries}, retry_delay={config.retry_delay}, timeout={config.timeout_per_task}, fallback={config.enable_fallback}, parallel={config.parallel_execution}, log={config.log_execution_details}')

config2 = TaskExecutionConfig(max_retries=-5, retry_delay=-1, timeout_per_task=-10, enable_fallback="yes", parallel_execution="no", log_execution_details="true")
print(f'Normalized: max_retries={config2.max_retries}, retry_delay={config2.retry_delay}, timeout={config2.timeout_per_task}, fallback={config2.enable_fallback}, parallel={config2.parallel_execution}, log={config2.log_execution_details}')

config3 = TaskExecutionConfig(max_retries="abc", retry_delay="invalid", timeout_per_task="xyz")
print(f'Invalid strings: max_retries={config3.max_retries}, retry_delay={config3.retry_delay}, timeout={config3.timeout_per_task}')

# Test TaskExecutor init
print()
print('=== TaskExecutor init ===')
executor = TaskExecutor()
print(f'status: {executor.status}')
print(f'config: {executor.config}')
print(f'total_executions: {executor.total_executions}')
print(f'successful: {executor.successful_executions}')
print(f'failed: {executor.failed_executions}')
print(f'total_attempts: {executor.total_attempts}')
stats = executor.get_execution_statistics()
print(f'stats: {stats}')

# Test TaskExecutor._task_metadata
print()
print('=== _task_metadata ===')
task_with_meta = Task(id='t1', name='test', description='test', metadata={'action': 'test_action', 'cost': 5.0, 'requires_ui': True})
meta = TaskExecutor._task_metadata(task_with_meta)
print(f'with metadata: {meta}')

task_without_meta = Task(id='t2', name='test2', description='test2')
meta = TaskExecutor._task_metadata(task_without_meta)
print(f'without metadata: {meta}')

# Test _task_application
print()
print('=== _task_application ===')
task_with_app = Task(id='t3', name='test3', description='test3', metadata={'application': 'Chrome'})
app = TaskExecutor._task_application(task_with_app)
print(f'with application: {app}')

task_without_app = Task(id='t4', name='test4', description='test4')
app = TaskExecutor._task_application(task_without_app)
print(f'without application: {app}')

# Test _resolve_action_name
print()
print('=== _resolve_action_name ===')
task_with_action = Task(id='t5', name='test5', description='test5', metadata={'action': 'open_chrome'})
action = executor._resolve_action_name(task_with_action)
print(f'with action: {action}')

task_without_action = Task(id='t6', name='test6', description='test6')
action = executor._resolve_action_name(task_without_action)
print(f'without action (uses id): {action}')

# Test _task_parameters
print()
print('=== _task_parameters ===')
task_with_params = Task(id='t7', name='test7', description='test7', metadata={'parameters': {'url': 'https://example.com'}})
params = TaskExecutor._task_parameters(task_with_params)
print(f'with metadata params: {params}')

task_with_direct_params = Task(id='t8', name='test8', description='test8', parameters={'query': 'test'}, metadata={'parameters': {'url': 'https://example.com'}})
params = TaskExecutor._task_parameters(task_with_direct_params)
print(f'with both (direct overrides): {params}')

# Test _calculate_task_cost
print()
print('=== _calculate_task_cost ===')
# Explicit cost
task_explicit_cost = Task(id='t9', name='test9', description='test9', metadata={'cost': 5.0})
cost = executor._calculate_task_cost(task_explicit_cost, {})
print(f'explicit cost: {cost}')

# Invalid cost -> falls back to registry or complexity
task_invalid_cost = Task(id='t10', name='test10', description='test10', metadata={'cost': 'invalid'})
cost = executor._calculate_task_cost(task_invalid_cost, {})
print(f'invalid cost (complexity default 1.0): {cost}')

# No explicit cost, no registration -> complexity default
task_no_cost = Task(id='t11', name='test11', description='test11')
cost = executor._calculate_task_cost(task_no_cost, {})
print(f'no cost (complexity default 1.0): {cost}')

# With complexity
task_complexity = Task(id='t12', name='test12', description='test12', metadata={'complexity': 3.0})
cost = executor._calculate_task_cost(task_complexity, {})
print(f'complexity 3.0: {cost}')

# Test _evaluate_precondition
print()
print('=== _evaluate_precondition ===')
# Callable
print(f'callable True: {TaskExecutor._evaluate_precondition(lambda s: True, {})}')
print(f'callable False: {TaskExecutor._evaluate_precondition(lambda s: False, {})}')

# String
print(f'string key exists: {TaskExecutor._evaluate_precondition("browser_ready", {"browser_ready": True})}')
print(f'string key missing: {TaskExecutor._evaluate_precondition("browser_ready", {})}')

# Dict - equals
print(f'dict equals: {TaskExecutor._evaluate_precondition({"key": "x", "equals": 5}, {"x": 5})}')
print(f'dict equals fail: {TaskExecutor._evaluate_precondition({"key": "x", "equals": 5}, {"x": 3})}')

# Dict - value
print(f'dict value: {TaskExecutor._evaluate_precondition({"key": "y", "value": 10}, {"y": 10})}')

# Dict - no match
print(f'dict no match: {TaskExecutor._evaluate_precondition({"key": "z", "equals": 5}, {"x": 3})}')

# Test _check_task_preconditions
print()
print('=== _check_task_preconditions ===')
# No preconditions
task_no_prec = Task(id='t13', name='test13', description='test13', metadata={'preconditions': []})
print(f'no preconditions: {executor._check_task_preconditions(task_no_prec, {})}')

# String preconditions - satisfied
task_str_prec = Task(id='t14', name='test14', description='test14', metadata={'preconditions': ['browser_ready']})
print(f'satisfied str precondition: {executor._check_task_preconditions(task_str_prec, {"browser_ready": True})}')

# String preconditions - not satisfied
print(f'unsatisfied str precondition: {executor._check_task_preconditions(task_str_prec, {})}')

# State requirements - satisfied
task_state_req = Task(id='t15', name='test15', description='test15', metadata={'state_requirements': {'chrome_open': True}})
print(f'satisfied state requirements: {executor._check_task_preconditions(task_state_req, {"chrome_open": True})}')

# State requirements - not satisfied
print(f'unsatisfied state requirements: {executor._check_task_preconditions(task_state_req, {"chrome_open": False})}')

# Test _should_execute_conditionally
print()
print('=== _should_execute_conditionally ===')
task_no_conditions = Task(id='t16', name='test16', description='test16')
print(f'no conditions: {executor._should_execute_conditionally(task_no_conditions, {})}')

task_with_conditions = Task(id='t17', name='test17', description='test17', metadata={'conditions': ['browser_ready']})
print(f'browser_ready true: {executor._should_execute_conditionally(task_with_conditions, {"browser_ready": True})}')
print(f'browser_ready false: {executor._should_execute_conditionally(task_with_conditions, {"browser_ready": False})}')

# Test _convert_task_to_node
print()
print('=== _convert_task_to_node ===')
task_simple = Task(id='t18', name='test18', description='test node', metadata={'action': 'test_action', 'cost': 2.0})
node = executor._convert_task_to_node(task_simple, {})
print(f'converted node type: {type(node).__name__}')
print(f'node.id: {node.id}')
print(f'node.type: {node.type}')
print(f'node.name: {node.name}')
print(f'node.cost: {node.cost}')
print(f'node.metadata action_name: {node.metadata.get("action_name")}')

# Test execute_task_hierarchy - sequential with callbacks
print()
print('=== execute_task_hierarchy (SEQQNSUMCIAL) ===')
task_callback = Task(id='callback_task', name='cb', description='callback', metadata={
    'execute_callback': lambda **kwargs: {'success': True, 'result': 'done'},
})
results = executor.execute_task_hierarchy([task_callback], {}, mode=TaskExecutionMode.SEQUENTIAL)
print(f'sequential results: {len(results)}, status={results[0].status}')

# Test execute_task_hierarchy with invalid mode
print()
print('=== execute_task_hierarchy INVALID mode ===')
try:
    task_empty = Task(id='t_invalid', name='invalid', description='invalid')
    executor.execute_task_hierarchy([], {}, mode=TaskExecutionMode.SEQUENTIAL)
    print('Empty tasks OK')
except Exception as e:
    print(f'Error: {e}')

# Test execute_task_with_retry - with mocked registry
print()
print('=== execute_task_with_retry ===')
# Create a task with mock callback that succeeds
task_retry = Task(id='retry_task', name='retry', description='retry', metadata={
    'execute_callback': lambda **kwargs: {'success': True, 'result': 'retried'},
    'retry_safe': True,
})
result = executor.execute_task_with_retry(task_retry, {})
print(f'retry result status: {result.status}')

# Test execute_plan - empty plan
print()
print('=== execute_plan ===')
exp = Executor()
result = exp.execute_plan([])
print(f'empty plan status: {result.status}')
print(f'empty plan error: {result.error}')

# Test create_goal_from_command
print()
print('=== create_goal_from_command ===')
goal = exp.create_goal_from_command('abrir_youtube', {})
print(f'abrir_youtube: {goal.type if goal else None}, {goal.target if goal else None}')

goal = exp.create_goal_from_command('abrir_chrome', {})
print(f'abrir_chrome: {goal.type if goal else None}, {goal.target if goal else None}')

goal = exp.create_goal_from_command('navegar_a', {'url': 'https://example.com'})
print(f'navegar_a: {goal.type if goal else None}, {goal.target if goal else None}')

goal = exp.create_goal_from_command('buscar_en_google', {'query': 'test'})
print(f'buscar_en_google: {goal.type if goal else None}, {goal.target if goal else None}')

goal = exp.create_goal_from_command('unknown_command', {})
print(f'unknown_command: {goal}')

# Test ExecutionResult
print()
print('=== ExecutionResult ===')
er = ExecutionResult(status=ExecutionStatus.SUCCESS)
print(f'bool success: {bool(er)}')
er2 = ExecutionResult(status=ExecutionStatus.FAILED)
print(f'bool failed: {bool(er2)}')
d = er.to_dict()
print(f'to_dict keys: {sorted(d.keys())}')

# Test ExecutionState
print()
print('=== ExecutionState ===')
state = ExecutionState(timestamp=123, application_states={}, ui_elements={}, available_actions=['a','b'], last_actions=[], constraints=[])
state.update({'constraints': ['c1'], 'new_key': 'val'})
print(f'after update constraints: {state.constraints}')
print(f'after update new_key: {state.new_key}')
d = state.to_dict()
print(f'to_dict keys: {sorted(d.keys())}')
