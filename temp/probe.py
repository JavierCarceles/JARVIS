from unittest.mock import patch

with patch("src.hands.applications_core.get_memory_manager") as m:
    m.return_value.get_entities_by_type.return_value = []
    from src.hands.applications_core import ApplicationManager
    am = ApplicationManager()

print("APPS", list(am.applications))
for k, v in am.applications.items():
    print(k, "caps=", len(v.capabilities),
          "ui=", [(e.name, type(e.coordinates).__name__, e.coordinates) for e in v.ui_elements],
          "states=", len(v.states))
