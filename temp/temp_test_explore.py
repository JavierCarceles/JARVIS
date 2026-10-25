import sys, logging
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
logging.disable(logging.CRITICAL)
from src.hands.planner.task_executor import TaskExecutor, TaskExecutorStatus, TaskExecutionMode, TaskExecutionConfig
from src.hands.planner.node import Task, Node, NodeType, TaskStatus
from src.hands.planner.htn_manager import TaskExecutionResult
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Test _normalize_execution_result with various types
print('=== _normalize_execution_result ===')
ter = TaskExecutionResult(task_id='t1', status=TaskStatus.COMPLETED, result={'x':1}, execution_time=1.0)
normalized = TaskExecutor._normalize_execution_result(ter)
print(f'TaskExecutionResult -> {normalized}')

normalized = TaskExecutor._normalize_execution_result({'success': True, 'result': {'x':1}})
print(f'dict success=True -> {normalized}')

normalized = TaskExecutor._normalize_execution_result({'success': False, 'error': 'fail'})
print(f'dict success=False -> {normalized}')

normalized = TaskExecutor._normalize_execution_result(True)
print(f'bool True -> {normalized}')

normalized = TaskExecutor._normalize_execution_result(None)
print(f'None -> {normalized}')

normalized = TaskExecutor._normalize_execution_result({'status': 'success', 'data': 'test'})
print(f'dict status=success -> {normalized}')

normalized = TaskExecutor._normalize_execution_result({'success': 'true'})
print(f'dict success=string -> {normalized}')

print()
print('=== _truthy_success ===')
print(f'bool True: {TaskExecutor._truthy_success(True)}')
print(f'bool False: {TaskExecutor._truthy_success(False)}')
print(f'int 1: {TaskExecutor._truthy_success(1)}')
print(f'int 0: {TaskExecutor._truthy_success(0)}')
print(f'str true: {TaskExecutor._truthy_success("true")}')
print(f'str completed: {TaskExecutor._truthy_success("completed")}')
print(f'str no: {TaskExecutor._truthy_success("no")}')
print(f'None: {TaskExecutor._truthy_success(None)}')

print()
print('=== _as_list ===')
print(f'None: {TaskExecutor._as_list(None)}')
print(f'list: {TaskExecutor._as_list([1,2])}')
print(f'tuple: {TaskExecutor._as_list((1,2))}')
print(f'set: {TaskExecutor._as_list({1,2})}')
print(f'str: {TaskExecutor._as_list("hello")}')
print(f'int: {TaskExecutor._as_list(42)}')

print()
print('=== _normalize_key ===')
print(f'normal: {TaskExecutor._normalize_key("Chrome")}')
print(f'with spaces: {TaskExecutor._normalize_key("My App Name")}')
print(f'None: {TaskExecutor._normalize_key(None)}')

print()
print('=== _safe_number ===')
print(f'5.0: {TaskExecutor._safe_number(5.0)}')
print(f'invalid: {TaskExecutor._safe_number("abc")}')
print(f'None: {TaskExecutor._safe_number(None)}')
print(f'with default: {TaskExecutor._safe_number("abc", default=99.0)}')
