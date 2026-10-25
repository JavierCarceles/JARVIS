import sys
sys.path.insert(0, '.')
sys.dont_write_bytecode = True

from unittest.mock import MagicMock, patch
import json

results = []

with patch('src.eyes.vision_only.ollama') as m:
    m.chat.return_value = {
        'message': {
            'content': json.dumps({
                'detected': True, 'state': 'active',
                'window_title': 'Chrome',
                'visible_elements': ['tab'],
                'confidence': 0.9
            })
        }
    }
    from src.eyes.vision_only import Vision
    v = Vision()
    v.screen_capture = MagicMock()
    v.screen_capture.capture_monitor = MagicMock(return_value='/fake/img.png')

    import src.eyes.vision_only as mod
    func_globals = mod.Vision.detect_application_state.__globals__
    results.append(f"ollama is mock: {func_globals.get('ollama') is m}")

    # Call the actual method
    r = v.detect_application_state('chrome')
    results.append(f"METHOD FINAL state: {r.state}")
    results.append(f"METHOD FINAL window_title: {r.window_title}")

    # Now check: is Vision.detect_application_state the same as what we see in source?
    import inspect
    src = inspect.getsource(mod.Vision.detect_application_state)
    # Check if there are TWO except blocks
    results.append(f"Number of 'except' in source: {src.count('except')}")
    results.append(f"Has json.JSONDecodeError: {'JSONDecodeError' in src}")
    results.append(f"Has outer except: {'except Exception as exc' in src}")
    
    # Check if there's a different Vision class
    results.append(f"Vision.__module__: {Vision.__module__}")
    results.append(f"Vision.__qualname__: {Vision.__qualname__}")

with open('data/temp/debug_result.txt', 'w') as f:
    for line in results:
        f.write(line + '\n')
