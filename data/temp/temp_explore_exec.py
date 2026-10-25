import sys, io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.hands.executor import Executor, ExecutionStatus, ExecutionResult, ExecutionState
sys.stdout = old_stdout
sys.stderr = old_stdout

exp = Executor()

# Test _evaluate_condition - bool
print('bool True:', exp._evaluate_condition(True))
print('bool False:', exp._evaluate_condition(False))

# Test with callable
print('callable True:', exp._evaluate_condition(lambda s: True))
print('callable False:', exp._evaluate_condition(lambda s: False))

# Test with dict - equals
print('dict equals x=5:', exp._evaluate_condition({"key": "x", "equals": 5}))
exp.update_state({"x": 5})
print('dict equals x=5 (after update):', exp._evaluate_condition({"key": "x", "equals": 5}))

# Test _check_node_preconditions
node_no_prec = {"id": "test", "action": "test", "preconditions": []}
print('no preconditions:', exp._check_node_preconditions(node_no_prec))

node_true = {"id": "test2", "action": "test2", "preconditions": [True]}
print('true precondition:', exp._check_node_preconditions(node_true))

node_false = {"id": "test3", "action": "test3", "preconditions": [False]}
print('false precondition:', exp._check_node_preconditions(node_false))

# Test _verify_node_success
print('dict success=True:', exp._verify_node_success({"id": "v1", "action": "test"}, {"success": True}))
print('dict success=False:', exp._verify_node_success({"id": "v1", "action": "test"}, {"success": False}))
print('None:', exp._verify_node_success({"id": "v1", "action": "test"}, None))
print('False:', exp._verify_node_success({"id": "v1", "action": "test"}, False))
print('bool True:', exp._verify_node_success({"id": "v1", "action": "test"}, True))
print('dict with error:', exp._verify_node_success({"id": "v1", "action": "test"}, {"error": "fail"}))
print('dict status=success:', exp._verify_node_success({"id": "v1", "action": "test"}, {"status": "success"}))
print('dict status=failed:', exp._verify_node_success({"id": "v1", "action": "test"}, {"status": "failed"}))

# Test _normalize_plan_node
result = exp._normalize_plan_node({"id": "n1", "action": "test"}, 0)
print('dict input:', result)

result = exp._normalize_plan_node(42, 0)
print('invalid int:', result)

result = exp._normalize_plan_node({"id": "n2", "parameters": "not_a_dict"}, 0)
print('invalid params:', result)

result = exp._normalize_plan_node({"id": "n3", "preconditions": "not_a_list"}, 0)
print('invalid preconds:', result)

# Test _safe_cost
print('safe_cost 5.0:', exp._safe_cost(5.0))
print('safe_cost -1.0:', exp._safe_cost(-1.0))
print('safe_cost invalid:', exp._safe_cost("abc"))
print('safe_cost None:', exp._safe_cost(None))
print('safe_cost 0.0:', exp._safe_cost(0.0))

# Test _get_nested_value
state = {"a": {"b": {"c": 42}}, "top": "value"}
print('flat key:', Executor._get_nested_value(state, "top"))
print('nested key:', Executor._get_nested_value(state, "a.b.c"))
print('missing key:', Executor._get_nested_value(state, "missing"))
print('missing nested:', Executor._get_nested_value(state, "a.b.missing"))

# Test _extract_capability_from_action
print('focus_address_bar:', exp._extract_capability_from_action("focus_address_bar"))
print('type_url:', exp._extract_capability_from_action("type_url"))
print('unknown:', exp._extract_capability_from_action("unknown_action"))

# Test _should_replan
print('with alternatives:', exp._should_replan([{"id": "n1", "action": "test", "alternatives": [{"action": "alt1"}], "cost": 1.0}], 0))
print('cheap no alt:', exp._should_replan([{"id": "n1", "action": "test", "alternatives": [], "cost": 2.0}], 0))
print('expensive no alt:', exp._should_replan([{"id": "n1", "action": "test", "alternatives": [], "cost": 10.0}], 0))
print('mid cost no alt:', exp._should_replan([{"id": "n1", "action": "test", "alternatives": [], "cost": 4.0}], 0))
print('out of range:', exp._should_replan([{"id": "n1", "action": "test", "alternatives": [], "cost": 4.0}], 5))

# Test _parse_args
print('parse_args None:', exp._parse_args(None))
print('parse_args empty:', exp._parse_args(""))
print('parse_args text:', exp._parse_args('"hello"'))
print('parse_args tuple:', exp._parse_args("(1, 2, 3)"))
try:
    print('parse_args invalid:', exp._parse_args("not valid python"))
except ValueError as e:
    print('parse_args invalid: ValueError raised')

# Test ExecutionState
state_obj = ExecutionState(timestamp=123, application_states={}, ui_elements={}, available_actions=['a','b'], last_actions=[], constraints=[])
state_obj.update({'constraints': ['c1'], 'new_key': 'val'})
print('state update constraints:', state_obj.constraints)
print('state update new_key:', getattr(state_obj, 'new_key', None))

# Test ExecutionResult
er = ExecutionResult(status=ExecutionStatus.SUCCESS)
print('ExecutionResult bool:', bool(er))
er2 = ExecutionResult(status=ExecutionStatus.FAILED)
print('ExecutionResult failed bool:', bool(er2))
d = er.to_dict()
print('ExecutionResult to_dict keys:', sorted(d.keys()))

# Test can_execute
print('can_execute type_text:', exp.can_execute("type_text"))

# Test get_executor singleton
from src.hands.executor import get_executor
e1 = get_executor()
e2 = get_executor()
print('get_executor singleton:', e1 is e2)
