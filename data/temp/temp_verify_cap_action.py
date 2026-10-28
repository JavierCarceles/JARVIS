import sys, io
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, '.')
from src.hands.action_registry import ActionInfo, ActionType, get_action_registry
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Create a real ActionInfo with capability set
ai = ActionInfo(
    name='open_application',
    description='Open an app',
    action_type=ActionType.APPLICATION,
    function=None,
    parameters={},
    module='test',
    category='aplicacion',
    tags=['aplicacion', 'open'],
    confidence_threshold=0.8,
    capability='open_application',  # singular, the real field
)

print('ActionInfo has capability (singular):', hasattr(ai, 'capability'))
print('ActionInfo.capability:', getattr(ai, 'capability', 'N/A'))
print('ActionInfo has capabilities (plural):', hasattr(ai, 'capabilities'))
print('getattr capabilities:', getattr(ai, 'capabilities', 'N/A (default)'))

# Now test with Executor's _action_provides_capability
from src.hands.executor import Executor, get_executor
exp = get_executor()

# Test: does open_application action provide 'open_application' capability via its declared capability field?
print()
print('--- Testing _action_provides_capability with real ActionInfo ---')

# The action name IS the capability, so name match works
result1 = exp._action_provides_capability(ai, 'open_application')
print("capability='open_application' (name match):", result1)

# But what about checking via the declared capability field?
# _action_provides_capability checks action_info.capabilities (plural) which doesn't exist
# The real field is capability (singular string)
# Let's test with a capability that's declared but NOT in the name
ai2 = ActionInfo(
    name='my_custom_action',
    description='custom',
    action_type=ActionType.APPLICATION,
    function=None,
    parameters={},
    module='test',
    category='general',
    tags=[],
    confidence_threshold=0.8,
    capability='open_application',  # declared capability differs from action name
)
result2 = exp._action_provides_capability(ai2, 'open_application')
print("ai2.capability='open_application', name='my_custom_action':")
print("  _action_provides_capability(ai2, 'open_application'):", result2, "(should be True but bug makes it False)")

# Also check keyboard type_text action
from src.hands import keyboard
reg = get_action_registry()
if hasattr(reg, 'get_all_actions'):
    actions = reg.get_all_actions()
else:
    actions = {}
    for name in reg.list_actions():
        actions[name] = reg.get_action(name)

type_text_ai = actions.get('type_text')
if type_text_ai:
    print()
    print("type_text ActionInfo:")
    print("  name:", type_text_ai.name)
    print("  capability:", getattr(type_text_ai, 'capability', 'N/A'))
    print("  category:", type_text_ai.category)
    print("  action_type:", type_text_ai.action_type)
    # type_text has capability='keyboard.basic', name='type_text'
    # _action_provides_capability(ai, 'keyboard.basic') should check the declared capability
    result3 = exp._action_provides_capability(type_text_ai, 'keyboard.basic')
    print("  _action_provides_capability(type_text, 'keyboard.basic'):", result3, "(bug: should be True via declared capability, but is False)")
else:
    print("type_text action not found in registry")

# Also check open_application action registered in applications_core
open_app_ai = actions.get('open_application')
if open_app_ai:
    print()
    print("Registered open_application ActionInfo:")
    print("  capability:", getattr(open_app_ai, 'capability', 'N/A'))
    result4 = exp._action_provides_capability(open_app_ai, 'open_application')
    print("  _action_provides_capability(open_app, 'open_application'):", result4)
