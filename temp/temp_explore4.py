import sys, io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.hands.executor import Executor, ExecutionStatus, ExecutionResult
from src.hands.executor import ExecutionState
sys.stdout = old_stdout
sys.stderr = old_stdout

exp = Executor()

# Test _evaluate_condition - bool
print(f'bool True: {exp._evaluate_condition(True)}')
print(f'bool False: {exp._evaluate_condition(False)}')

# Test with callable
print(f'callable True: {exp._evaluate_condition(lambda s: True)}')
print(f'callable False: {exp._evaluate_condition(lambda s: False)}')

# Test with dict - equals
print(f'dict equals: {exp._evaluate_condition({"key": "x", "equals": 5})}')  # depends on state
# Set state
exp.update_state({"x": 5})
print(f'dict equals (x=5): {exp._evaluate_condition({"key": "x", "equals": 5})}')

# Test with string - depends on state
current_state = exp._get_state_for_planning()
print(f'string x in state: {exp._evaluate_condition("x")}')

# Test _check_node_preconditions
node_no_prec = {"id": "test", "action": "test", "preconditions": []}
print(f'no preconditions: {exp._check_node_preconditions(node_no_prec)}')

node_with_prec = {"id": "test2", "action": "test2", "preconditions": [True]}
print(f'true precondition: {exp._check_node_preconditions(node_with_prec)}')

node_false_prec = {"id": "test3", "action": "test3", "preconditions": [False]}
print(f'false precondition: {exp._check_node_preconditions(node_false_prec)}')

node_str_prec = {"id": "test4", "action": "test4", "preconditions": ["x"]}
print(f'string precondition x=5: {exp._check_node_preconditions(node_str_prec)}')

# Test _verify_node_success
print()
print('=== _verify_node_success ===')
node = {"id": "v1", "action": "test"}
print(f'dict success=True: {exp._verify_node_success(node, {"success": True})}')
print(f'dict success=False: {exp._verify_node_success(node, {"success": False})}')
print(f'dict no success: {exp._verify_node_success(node, {"data": "test"})}')
print(f'None: {exp._verify_node_success(node, None)}')
print(f'False: {exp._verify_node_success(node, False)}')
print(f'bool True: {exp._verify_node_success(node, True)}')
print(f'dict with error: {exp._verify_node_success(node, {"error": "fail"})}')
print(f'dict status=success: {exp._verify_node_success(node, {"status": "success"})}')
print(f'dict status=failed: {exp._verify_node_success(node, {"status": "failed"})}')

# Test _normalize_plan_node
print()
print('=== _normalize_plan_node ===')
# Dict input
result = exp._normalize_plan_node({"id": "n1", "action": "test"}, 0)
print(f'dict input: {result}')

# Object with id
class MockNode:
    id = "mock1"
    name = "mock_name"
    action = "mock_action"
    parameters = {"p": 1}
    preconditions = []
    effects = []
    cost = 1.0
    application = None
    ui_element = None
    metadata = {}
result = exp._normalize_plan_node(MockNode, 0)
print(f'object input: {result}')

# Invalid type
result = exp._normalize_plan_node("invalid", 0)
print(f'invalid str: {result}')
result = exp._normalize_plan_node(42, 0)
print(f'invalid int: {result}')

# Dict with invalid parameters
result = exp._normalize_plan_node({"id": "n2", "parameters": "not_a_dict"}, 0)
print(f'invalid params: {result}')

# Dict with invalid preconditions
result = exp._normalize_plan_node({"id": "n3", "preconditions": "not_a_list"}, 0)
print(f'invalid preconds: {result}')

# Test _safe_cost
print()
print('=== _safe_cost ===')
print(f'5.0: {exp._safe_cost(5.0)}')
print(f'-1.0: {exp._safe_cost(-1.0)}')
print(f'invalid: {exp._safe_cost("abc")}')
print(f'None: {exp._safe_cost(None)}')
print(f'0.0: {exp._safe_cost(0.0)}')

# Test _get_nested_value
print()
print('=== _get_nested_value ===')
state = {"a": {"b": {"c": 42}}, "top": "value"}
print(f'flat key: {Executor._get_nested_value(state, "top")}')
print(f'nested key: {Executor._get_nested_value(state, "a.b.c")}')
print(f'missing key: {Executor._get_nested_value(state, "missing")}')
print(f'missing nested: {Executor._get_nested_value(state, "a.b.missing")}')

# Test _extract_capability_from_action
print()
print('=== _extract_capability_from_action ===')
print(f'focus_address_bar: {exp._extract_capability_from_action("focus_address_bar")}')
print(f'type_url: {exp._extract_capability_from_action("type_url")}')
print(f'unknown: {exp._extract_capability_from_action("unknown_action")}')

# Test _should_replan
print()
print('=== _should_replan ===')
plan_with_alt = [{"id": "n1", "action": "test", "alternatives": [{"action": "alt1"}], "cost": 1.0}]
print(f'with alternatives: {exp._should_replan(plan_with_alt, 0)}')

plan_cheap = [{"id": "n1", "action": "test", "alternatives": [], "cost": 2.0}]
print(f'cheap no alt: {exp._should_replan(plan_cheap, 0)}')

plan_expensive = [{"id": "n1", "action": "test", "alternatives": [], "cost": 10.0}]
print(f'expensive no alt: {exp._should_replan(plan_expensive, 0)}')

plan_no_alt_mid = [{"id": "n1", "action": "test", "alternatives": [], "cost": 4.0}]
print(f'mid cost no alt (4.0>3.0): {exp._should_replan(plan_no_alt_mid, 0)}')

plan_out_of_range = [{"id": "n1", "action": "test", "alternatives": [], "cost": 4.0}]
print(f'out of range: {exp._should_replan(plan_out_of_range, 5)}')

# Test _parse_args
print()
print('=== _parse_args ===')
print(f'None: {exp._parse_args(None)}')
print(f'empty: {exp._parse_args("")}')
print(f'valid text: {exp._parse_args(\'"hello"\')}')
print(f'valid tuple: {exp._parse_args("(1, 2, 3)")}')
print(f'invalid: {exp._parse_args("not valid python")}')
