import sys, io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.hands.executor import Executor, ExecutionStatus, ExecutionResult, ExecutionState, get_executor
sys.stdout = old_stdout
sys.stderr = old_stdout
sys.stdout = sys.stderr

# Check process_and_execute signature
import inspect
sig = inspect.signature(Executor.process_and_execute)
print(f'process_and_execute sig: {sig}')

# Check can_execute
exp = Executor()
print(f'can_execute type_text: {exp.can_execute("type_text")}')

# Check get_current_state and update_state
state = exp.get_current_state()
print(f'get_current_state type: {type(state).__name__}')

# Check execute_plan with empty
result = exp.execute_plan([])
print(f'execute_plan empty status: {result.status}, error: {result.error}')

# Check _normalize_plan_node
sig2 = inspect.signature(Executor._normalize_plan_node)
print(f'_normalize_plan_node sig: {sig2}')

# Check _safe_cost
sig3 = inspect.signature(Executor._safe_cost)
print(f'_safe_cost sig: {sig3}')

# Check _get_nested_value
sig4 = inspect.signature(Executor._get_nested_value)
print(f'_get_nested_value sig: {sig4}')

# Check _evaluate_condition
sig5 = inspect.signature(Executor._evaluate_condition)
print(f'_evaluate_condition sig: {sig5}')

# Check _check_node_preconditions
sig6 = inspect.signature(Executor._check_node_preconditions)
print(f'_check_node_preconditions sig: {sig6}')

# Check _verify_node_success
sig7 = inspect.signature(Executor._verify_node_success)
print(f'_verify_node_success sig: {sig7}')

# Check _should_replan
sig8 = inspect.signature(Executor._should_replan)
print(f'_should_replan sig: {sig8}')

# Check _extract_capability_from_action
sig9 = inspect.signature(Executor._extract_capability_from_action)
print(f'_extract_capability_from_action sig: {sig9}')

# Check _action_provides_capability
sig10 = inspect.signature(Executor._action_provides_capability)
print(f'_action_provides_capability sig: {sig10}')

# Check _try_alternative
sig11 = inspect.signature(Executor._try_alternative)
print(f'_try_alternative sig: {sig11}')

# Check _parse_args
sig12 = inspect.signature(Executor._parse_args)
print(f'_parse_args sig: {sig12}')

# Check _positional_to_named_parameters
sig13 = inspect.signature(Executor._positional_to_named_parameters)
print(f'_positional_to_named_parameters sig: {sig13}')

# Check _get_legacy_function
sig14 = inspect.signature(Executor._get_legacy_function)
print(f'_get_legacy_function sig: {sig14}')

# Check _normalize_goal
sig15 = inspect.signature(Executor._normalize_goal)
print(f'_normalize_goal sig: {sig15}')

# Check create_goal_from_command signature
sig16 = inspect.signature(Executor.create_goal_from_command)
print(f'create_goal_from_command sig: {sig16}')

# Check _replan_after_failure
sig17 = inspect.signature(Executor._replan_after_failure)
print(f'_replan_after_failure sig: {sig17}')
