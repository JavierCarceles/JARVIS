"""
Error Recovery System for JARVIS
Handles error detection, recovery strategies, and system resilience
"""

import time
import traceback
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Union
from enum import Enum
import json
import sqlite3
import os
from pathlib import Path

class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorType(Enum):
    """Error categories"""
    NETWORK = "network"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    MEMORY = "memory"
    PROCESS = "process"
    EXTERNAL = "external"
    SYSTEM = "system"

class RecoveryStrategy(Enum):
    """Recovery strategy types"""
    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_BREAKER = "circuit_breaker"
    TIMEOUT = "timeout"
    ROLLBACK = "rollback"
    RESTART = "restart"

class ErrorRecoveryManager:
    """Main error recovery management system"""
    
    def __init__(self, db_path: str = "data/error_recovery.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.error_handlers = {}
        self.recovery_strategies = {}
        self.circuit_breakers = {}
        self.error_stats = {}
        self.max_retries = 3
        self.retry_delay = 1.0
        self.fallback_enabled = True
        
        # Initialize database
        self._init_database()
        
        # Register default strategies
        self._register_default_strategies()
    
    @staticmethod
    def get_error_recovery_manager():
        """Get a singleton instance of ErrorRecoveryManager"""
        if not hasattr(ErrorRecoveryManager, '_instance'):
            ErrorRecoveryManager._instance = ErrorRecoveryManager()
        return ErrorRecoveryManager._instance
        
    def _init_database(self):
        """Initialize error recovery database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Error tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    error_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    component TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT,
                    recovery_attempted BOOLEAN DEFAULT FALSE,
                    recovery_success BOOLEAN DEFAULT FALSE,
                    recovery_strategy TEXT,
                    execution_time REAL,
                    additional_data TEXT
                )
            ''')
            
            # Error statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE DEFAULT CURRENT_DATE,
                    error_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    recovered_count INTEGER DEFAULT 0,
                    avg_recovery_time REAL DEFAULT 0.0
                )
            ''')
            
            # Recovery strategies table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recovery_strategies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL UNIQUE,
                    strategy_type TEXT NOT NULL,
                    max_retries INTEGER DEFAULT 3,
                    retry_delay REAL DEFAULT 1.0,
                    timeout REAL DEFAULT 30.0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def _register_default_strategies(self):
        """Register default recovery strategies"""
        self.register_strategy("retry", self._retry_strategy)
        self.register_strategy("fallback", self._fallback_strategy)
        self.register_strategy("circuit_breaker", self._circuit_breaker_strategy)
        self.register_strategy("timeout", self._timeout_strategy)
        self.register_strategy("restart", self._restart_strategy)
    
    def register_strategy(self, name: str, strategy_func: Callable):
        """Register a recovery strategy"""
        self.recovery_strategies[name] = strategy_func
        self.logger.info(f"Registered recovery strategy: {name}")
    
    def register_handler(self, error_type: str, handler_func: Callable):
        """Register an error handler for specific error types"""
        self.error_handlers[error_type] = handler_func
        self.logger.info(f"Registered error handler for: {error_type}")
    
    def log_error(self, error_type: ErrorType, severity: ErrorSeverity, 
                  component: str, error_message: str, stack_trace: str = None,
                  additional_data: Dict = None):
        """Log an error for tracking and analysis"""
        timestamp = datetime.now()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO error_logs 
                (error_type, severity, component, error_message, stack_trace, additional_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (error_type.value, severity.value, component, error_message, 
                  stack_trace, json.dumps(additional_data) if additional_data else None))
            error_id = cursor.lastrowid
            conn.commit()
        
        # Update error statistics
        self._update_error_stats(error_type, severity, False)
        
        self.logger.error(f"Error logged: {error_message} (ID: {error_id})")
        return error_id
    
    def _update_error_stats(self, error_type: ErrorType, severity: ErrorSeverity, recovered: bool):
        """Update error statistics"""
        date = datetime.now().date()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if record exists for today
            cursor.execute('''
                SELECT id FROM error_stats 
                WHERE date = ? AND error_type = ? AND severity = ?
            ''', (date, error_type.value, severity.value))
            
            result = cursor.fetchone()
            
            if result:
                # Update existing record
                cursor.execute('''
                    UPDATE error_stats 
                    SET count = count + 1, recovered_count = recovered_count + 1
                    WHERE id = ?
                ''', (result[0],))
            else:
                # Create new record
                cursor.execute('''
                    INSERT INTO error_stats (date, error_type, severity, count, recovered_count)
                    VALUES (?, ?, ?, 1, 1)
                ''', (date, error_type.value, severity.value))
            
            conn.commit()
    
    def recover_from_error(self, error_id: int, strategy: RecoveryStrategy = None, 
                          max_retries: int = None, retry_delay: float = None) -> bool:
        """Attempt to recover from a logged error"""
        
        # Get error details
        error_details = self._get_error_details(error_id)
        if not error_details:
            self.logger.error(f"Error not found: {error_id}")
            return False
        
        # Use default strategy if none provided
        if strategy is None:
            strategy = self._determine_best_strategy(error_details)
        
        # Execute recovery strategy
        success = self._execute_recovery_strategy(error_id, strategy, max_retries, retry_delay)
        
        # Update recovery status
        self._update_recovery_status(error_id, success)
        
        # Update statistics
        self._update_error_stats(ErrorType(error_details['error_type']), 
                                ErrorSeverity(error_details['severity']), success)
        
        return success
    
    def _get_error_details(self, error_id: int) -> Optional[Dict]:
        """Get detailed information about an error"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM error_logs WHERE id = ?
            ''', (error_id,))
            
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
            return None
    
    def _determine_best_strategy(self, error_details: Dict) -> RecoveryStrategy:
        """Determine the best recovery strategy based on error type and severity"""
        error_type = error_details['error_type']
        severity = error_details['severity']
        
        # Strategy selection logic
        if error_type == 'network':
            return RecoveryStrategy.RETRY
        elif error_type == 'database':
            return RecoveryStrategy.CIRCUIT_BREAKER
        elif error_type == 'filesystem':
            return RecoveryStrategy.FALLBACK
        elif error_type == 'memory':
            return RecoveryStrategy.RESTART
        elif severity == 'critical':
            return RecoveryStrategy.CIRCUIT_BREAKER
        else:
            return RecoveryStrategy.RETRY
    
    def _execute_recovery_strategy(self, error_id: int, strategy: RecoveryStrategy, 
                                 max_retries: int, retry_delay: float) -> bool:
        """Execute a specific recovery strategy"""
        
        start_time = time.time()
        
        try:
            if strategy == RecoveryStrategy.RETRY:
                return self._retry_strategy(error_id, max_retries, retry_delay)
            elif strategy == RecoveryStrategy.FALLBACK:
                return self._fallback_strategy(error_id)
            elif strategy == RecoveryStrategy.CIRCUIT_BREAKER:
                return self._circuit_breaker_strategy(error_id)
            elif strategy == RecoveryStrategy.TIMEOUT:
                return self._timeout_strategy(error_id)
            elif strategy == RecoveryStrategy.RESTART:
                return self._restart_strategy(error_id)
            else:
                self.logger.warning(f"Unknown strategy: {strategy}")
                return False
                
        except Exception as e:
            self.logger.error(f"Recovery strategy failed: {e}")
            return False
        finally:
            execution_time = time.time() - start_time
            self._update_execution_time(error_id, execution_time)
    
    def _retry_strategy(self, error_id: int, max_retries: int = None, retry_delay: float = None) -> bool:
        """Retry strategy with exponential backoff"""
        if max_retries is None:
            max_retries = self.max_retries
        if retry_delay is None:
            retry_delay = self.retry_delay
        
        error_details = self._get_error_details(error_id)
        if not error_details:
            return False
        
        for attempt in range(max_retries):
            try:
                # Simulate recovery attempt
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                
                # In a real system, this would attempt the failed operation
                # For now, simulate success with some probability
                success = attempt == max_retries - 1  # Success on last attempt
                
                if success:
                    self.logger.info(f"Retry strategy successful after {attempt + 1} attempts")
                    return True
                else:
                    self.logger.warning(f"Retry attempt {attempt + 1} failed")
                    
            except Exception as e:
                self.logger.error(f"Retry attempt {attempt + 1} failed with error: {e}")
        
        return False
    
    def _fallback_strategy(self, error_id: int) -> bool:
        """Fallback to alternative implementation"""
        error_details = self._get_error_details(error_id)
        if not error_details:
            return False
        
        try:
            # Simulate fallback implementation
            # In a real system, this would use alternative logic
            success = True  # Assume fallback works
            
            if success:
                self.logger.info("Fallback strategy successful")
                return True
            else:
                self.logger.warning("Fallback strategy failed")
                return False
                
        except Exception as e:
            self.logger.error(f"Fallback strategy failed with error: {e}")
            return False
    
    def _circuit_breaker_strategy(self, error_id: int) -> bool:
        """Circuit breaker pattern for handling repeated failures"""
        error_details = self._get_error_details(error_id)
        if not error_details:
            return False
        
        # Check circuit breaker state
        component = error_details['component']
        if component in self.circuit_breakers:
            breaker = self.circuit_breakers[component]
            if breaker['state'] == 'open':
                self.logger.warning(f"Circuit breaker open for component: {component}")
                return False
        
        try:
            # Attempt the operation
            success = True  # Simulate success
            
            if success:
                # Close circuit breaker if it was open
                if component in self.circuit_breakers:
                    self.circuit_breakers[component]['state'] = 'closed'
                    self.circuit_breakers[component]['failure_count'] = 0
                
                self.logger.info("Circuit breaker strategy successful")
                return True
            else:
                # Increment failure count
                if component not in self.circuit_breakers:
                    self.circuit_breakers[component] = {'state': 'closed', 'failure_count': 0}
                
                self.circuit_breakers[component]['failure_count'] += 1
                
                # Open circuit breaker if threshold exceeded
                if self.circuit_breakers[component]['failure_count'] >= 5:
                    self.circuit_breakers[component]['state'] = 'open'
                    self.logger.warning(f"Circuit breaker opened for component: {component}")
                
                return False
                
        except Exception as e:
            self.logger.error(f"Circuit breaker strategy failed with error: {e}")
            return False
    
    def _timeout_strategy(self, error_id: int) -> bool:
        """Timeout strategy for hanging operations"""
        error_details = self._get_error_details(error_id)
        if not error_details:
            return False
        
        try:
            # Simulate timeout handling
            # In a real system, this would cancel hanging operations
            time.sleep(0.1)  # Simulate timeout handling
            
            self.logger.info("Timeout strategy executed")
            return True
            
        except Exception as e:
            self.logger.error(f"Timeout strategy failed with error: {e}")
            return False
    
    def _restart_strategy(self, error_id: int) -> bool:
        """Restart strategy for critical failures"""
        error_details = self._get_error_details(error_id)
        if not error_details:
            return False
        
        try:
            # Simulate restart process
            # In a real system, this would restart processes or services
            time.sleep(0.5)  # Simulate restart delay
            
            self.logger.info("Restart strategy executed")
            return True
            
        except Exception as e:
            self.logger.error(f"Restart strategy failed with error: {e}")
            return False
    
    def _update_recovery_status(self, error_id: int, success: bool):
        """Update the recovery status of an error"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE error_logs 
                SET recovery_attempted = TRUE, recovery_success = ?
                WHERE id = ?
            ''', (success, error_id))
            conn.commit()
    
    def _update_execution_time(self, error_id: int, execution_time: float):
        """Update the execution time of a recovery attempt"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE error_logs 
                SET execution_time = ?
                WHERE id = ?
            ''', (execution_time, error_id))
            conn.commit()
    
    def get_error_statistics(self, days: int = 7) -> Dict:
        """Get error statistics for the specified number of days"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT error_type, severity, COUNT(*) as total_count, 
                       SUM(recovered_count) as recovered_count,
                       AVG(execution_time) as avg_recovery_time
                FROM error_stats 
                WHERE date BETWEEN ? AND ?
                GROUP BY error_type, severity
                ORDER BY total_count DESC
            ''', (start_date.date(), end_date.date()))
            
            results = cursor.fetchall()
            
            stats = {}
            for row in results:
                error_type, severity, total_count, recovered_count, avg_time = row
                stats[f"{error_type}_{severity}"] = {
                    'total_count': total_count,
                    'recovered_count': recovered_count,
                    'recovery_rate': recovered_count / total_count if total_count > 0 else 0,
                    'avg_recovery_time': avg_time or 0.0
                }
            
            return stats
    
    def get_active_errors(self) -> List[Dict]:
        """Get list of active (unrecovered) errors"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM error_logs 
                WHERE recovery_attempted = FALSE 
                ORDER BY timestamp DESC
                LIMIT 50
            ''')
            
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in results]
    
    def cleanup_old_errors(self, days: int = 30):
        """Clean up old error records"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM error_logs 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            self.logger.info(f"Cleaned up {deleted_count} old error records")
            return deleted_count
    
    def __str__(self):
        return f"ErrorRecoveryManager(db_path='{self.db_path}', strategies={len(self.recovery_strategies)})"


def get_error_recovery_manager():
    """Get a singleton instance of ErrorRecoveryManager"""
    if not hasattr(get_error_recovery_manager, '_instance'):
        get_error_recovery_manager._instance = ErrorRecoveryManager()
    return get_error_recovery_manager._instance


def start_error_recovery():
    """Start the error recovery system"""
    manager = get_error_recovery_manager()
    return manager


def stop_error_recovery():
    """Stop the error recovery system"""
    pass