"""Diagnostic: check what actions are registered and what plan actions the planner produces."""
import logging
logging.disable(logging.CRITICAL)

from src.hands.action_registry import get_action_registry
from src.hands.planner.planner import Planner

# Check registered actions
registry = get_action_registry()
all_actions = registry.get_all_actions()
plannable = registry.get_plannable_actions()
action_names = sorted(all_actions.keys())
print("=== Registered actions (all) ===")
print(action_names)
print()
print("=== Plannable actions ===")
print(sorted(plannable.keys()))
print()

# Check what the planner produces
planner = Planner()
planner.load_application_knowledge()
nodes = planner._get_available_nodes()
print("=== Available nodes (sample) ===")
for nid, node in list(nodes.items())[:20]:
    print(f"  node_id={nid}, type={getattr(node, 'type', '?')}, action_category={getattr(node, 'action_category', None)}, metadata.action_name={getattr(node, 'metadata', {}).get('action_name', None)}")
print(f"Total available nodes: {len(nodes)}")
print()

# Check what build_application_aware_plan produces for an open_application goal
from src.hands.planner.node import Goal
goal = Goal(
    id="g-open-chrome",
    type="open_application",
    target={"app_name": "chrome"},
    description="Abrir Chrome",
)
result = planner.build_application_aware_plan(goal, {})
print("=== build_application_aware_plan for open_application/chrome ===")
print(f"  status: {result.status}")
print(f"  application_used: {result.metadata.get('application_used')}")
print(f"  application_capabilities: {result.metadata.get('application_capabilities')}")
print(f"  plan: {result.plan}")
print()

# Check which plan actions exist in the registry
print("=== Plan action existence check ===")
for step in result.plan:
    action = step.get("action", "")
    exists = registry.get_action(action) is not None
    print(f"  action={action}, exists_in_registry={exists}, has_callback={'execute_callback' in step.get('metadata', {})}")
