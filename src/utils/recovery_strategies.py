"""
Recovery Strategies for JARVIS System
Advanced recovery mechanisms for different types of failures
"""

import time
import logging
import threading
import subprocess
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Union
from enum import Enum
import shutil
import tempfile
from pathlib import Path

class RecoveryType(Enum):
    """Types of recovery operations"""
    AUTOMATIC = "automatic"
    SEMI_AUTOMATIC = "semi_automatic"
    MANUAL = "manual"

class RecoveryStatus(Enum):
    """Recovery operation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class RecoveryAction:
    """Base recovery action"""
    
    def __init__(self, name: str, description: str, recovery_type: RecoveryType):
        self.name = name
        self.description = description
        self.recovery_type = recovery_type
        self.status = RecoveryStatus.PENDING
        self.start_time = None
        self.end_time = None
        self.result = None
        self.error_message = None
    
    def execute(self) -> bool:
        """Execute the recovery action"""
        self.status = RecoveryStatus.IN_PROGRESS
        self.start_time = datetime.now()
        
        try:
            result = self._do_execute()
            self.result = result
            self.status = RecoveryStatus.COMPLETED
            self.end_time = datetime.now()
            return True
        except Exception as e:
            self.error_message = str(e)
            self.status = RecoveryStatus.FAILED
            self.end_time = datetime.now()
            return False
    
    def _do_execute(self) -> Any:
        """Override this method in subclasses"""
        raise NotImplementedError
    
    def cancel(self):
        """Cancel the recovery action"""
        if self.status == RecoveryStatus.IN_PROGRESS:
            self.status = RecoveryStatus.CANCELLED
            self.end_time = datetime.now()
    
    def get_duration(self) -> Optional[float]:
        """Get execution duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

class DatabaseRecoveryAction(RecoveryAction):
    """Database recovery action"""
    
    def __init__(self, db_path: str, backup_path: str = None):
        super().__init__(
            name="Database Recovery",
            description="Recover database from backup or repair",
            recovery_type=RecoveryType.AUTOMATIC
        )
        self.db_path = db_path
        self.backup_path = backup_path or f"{db_path}.backup"
    
    def _do_execute(self) -> bool:
        """Execute database recovery"""
        if os.path.exists(self.backup_path):
            # Restore from backup
            shutil.copy2(self.backup_path, self.db_path)
            return True
        else:
            # Attempt to repair database
            self._repair_database()
            return True
    
    def _repair_database(self):
        """Attempt to repair corrupted database"""
        # This is a simplified version - in reality, you'd use specific database repair tools
        if os.path.exists(self.db_path):
            # Create a backup of the corrupted database
            corrupted_backup = f"{self.db_path}.corrupted.{int(time.time())}"
            shutil.copy2(self.db_path, corrupted_backup)
            
            # Try to vacuum the database
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("VACUUM")
                conn.close()
            except Exception as e:
                raise Exception(f"Database repair failed: {e}")

class FilesystemRecoveryAction(RecoveryAction):
    """Filesystem recovery action"""
    
    def __init__(self, file_path: str, backup_path: str = None):
        super().__init__(
            name="Filesystem Recovery",
            description="Recover file from backup or recreate",
            recovery_type=RecoveryType.AUTOMATIC
        )
        self.file_path = file_path
        self.backup_path = backup_path
    
    def _do_execute(self) -> bool:
        """Execute filesystem recovery"""
        if os.path.exists(self.backup_path):
            # Restore from backup
            shutil.copy2(self.backup_path, self.file_path)
            return True
        else:
            # Create empty file
            Path(self.file_path).touch()
            return True

class ProcessRecoveryAction(RecoveryAction):
    """Process recovery action"""
    
    def __init__(self, process_name: str, command: str):
        super().__init__(
            name="Process Recovery",
            description="Restart or recover process",
            recovery_type=RecoveryType.SEMI_AUTOMATIC
        )
        self.process_name = process_name
        self.command = command
    
    def _do_execute(self) -> bool:
        """Execute process recovery"""
        try:
            # Try to restart the process
            subprocess.run(self.command, shell=True, check=True, timeout=30)
            return True
        except subprocess.TimeoutExpired:
            raise Exception("Process restart timeout")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Process restart failed: {e}")

class MemoryRecoveryAction(RecoveryAction):
    """Memory recovery action"""
    
    def __init__(self, process_id: int = None):
        super().__init__(
            name="Memory Recovery",
            description="Clear memory cache or restart process",
            recovery_type=RecoveryType.AUTOMATIC
        )
        self.process_id = process_id
    
    def _do_execute(self) -> bool:
        """Execute memory recovery"""
        if self.process_id:
            # Restart specific process
            try:
                subprocess.run(f"kill -9 {self.process_id}", shell=True, check=True)
                return True
            except subprocess.CalledProcessError as e:
                raise Exception(f"Process termination failed: {e}")
        else:
            # Clear system cache (requires root/admin privileges)
            try:
                subprocess.run("sync && echo 3 > /proc/sys/vm/drop_caches", shell=True, check=True)
                return True
            except subprocess.CalledProcessError as e:
                raise Exception(f"Cache clearing failed: {e}")

class NetworkRecoveryAction(RecoveryAction):
    """Network recovery action"""
    
    def __init__(self, interface: str = None):
        super().__init__(
            name="Network Recovery",
            description="Reset network interface or DNS",
            recovery_type=RecoveryType.SEMI_AUTOMATIC
        )
        self.interface = interface
    
    def _do_execute(self) -> bool:
        """Execute network recovery"""
        if self.interface:
            # Restart specific network interface
            try:
                subprocess.run(f"ifdown {self.interface} && ifup {self.interface}", shell=True, check=True)
                return True
            except subprocess.CalledProcessError as e:
                raise Exception(f"Network interface restart failed: {e}")
        else:
            # Flush DNS cache
            try:
                # Try different DNS cache clearing commands
                commands = [
                    "systemctl flush-dns",
                    "service dnsmasq restart",
                    "rndc flush"
                ]
                
                for cmd in commands:
                    try:
                        subprocess.run(cmd, shell=True, check=True)
                        return True
                    except subprocess.CalledProcessError:
                        continue
                
                raise Exception("No DNS cache clearing method available")
            except subprocess.CalledProcessError as e:
                raise Exception(f"DNS cache clearing failed: {e}")

class RecoveryManager:
    """Main recovery management system"""
    
    def __init__(self, db_path: str = "data/recovery_manager.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.recovery_actions = {}
        self.recovery_history = []
        self.active_recoveries = {}
        self.lock = threading.Lock()
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize recovery management database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Recovery actions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recovery_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    recovery_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time DATETIME,
                    end_time DATETIME,
                    result TEXT,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Recovery history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recovery_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_name TEXT NOT NULL,
                    component TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    execution_time REAL,
                    success BOOLEAN NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    additional_data TEXT
                )
            ''')
            
            conn.commit()
    
    def register_recovery_action(self, action: RecoveryAction):
        """Register a recovery action"""
        with self.lock:
            self.recovery_actions[action.name] = action
            self.logger.info(f"Registered recovery action: {action.name}")
    
    def execute_recovery(self, action_name: str, component: str, error_type: str, 
                        additional_data: Dict = None) -> bool:
        """Execute a recovery action"""
        if action_name not in self.recovery_actions:
            raise ValueError(f"Unknown recovery action: {action_name}")
        
        action = self.recovery_actions[action_name]
        
        # Log recovery attempt
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO recovery_actions 
                (name, description, recovery_type, status)
                VALUES (?, ?, ?, ?)
            ''', (action.name, action.description, action.recovery_type.value, 
                  action.status.value))
            action_id = cursor.lastrowid
            conn.commit()
        
        # Execute recovery in separate thread
        def execute_recovery_thread():
            try:
                success = action.execute()
                
                # Update recovery status
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE recovery_actions 
                        SET status = ?, end_time = ?, result = ?, error_message = ?
                        WHERE id = ?
                    ''', (action.status.value, action.end_time, 
                          json.dumps(action.result) if action.result else None,
                          action.error_message, action_id))
                    conn.commit()
                
                # Log to recovery history
                self._log_recovery_history(action_name, component, error_type, success, additional_data)
                
                # Update active recoveries
                with self.lock:
                    if action_name in self.active_recoveries:
                        del self.active_recoveries[action_name]
                
                self.logger.info(f"Recovery action {action_name} {'completed successfully' if success else 'failed'}")
                
            except Exception as e:
                self.logger.error(f"Recovery action {action_name} failed with error: {e}")
                with self.lock:
                    if action_name in self.active_recoveries:
                        del self.active_recoveries[action_name]
        
        # Start recovery thread
        recovery_thread = threading.Thread(target=execute_recovery_thread, daemon=True)
        recovery_thread.start()
        
        # Track active recovery
        with self.lock:
            self.active_recoveries[action_name] = {
                'action': action,
                'thread': recovery_thread,
                'start_time': datetime.now()
            }
        
        return True
    
    def _log_recovery_history(self, action_name: str, component: str, error_type: str, 
                             success: bool, additional_data: Dict = None):
        """Log recovery history"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO recovery_history 
                (action_name, component, error_type, success, additional_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (action_name, component, error_type, success, 
                  json.dumps(additional_data) if additional_data else None))
            conn.commit()
    
    def get_recovery_history(self, days: int = 7) -> List[Dict]:
        """Get recovery history for specified days"""
        start_time = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM recovery_history 
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            ''', (start_time,))
            
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in results]
    
    def get_recovery_statistics(self, days: int = 7) -> Dict:
        """Get recovery statistics"""
        start_time = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_attempts,
                    AVG(execution_time) as avg_execution_time
                FROM recovery_history 
                WHERE timestamp >= ?
            ''', (start_time,))
            
            result = cursor.fetchone()
            total_attempts, successful_attempts, avg_time = result
            
            return {
                'total_attempts': total_attempts,
                'successful_attempts': successful_attempts,
                'success_rate': successful_attempts / total_attempts if total_attempts > 0 else 0,
                'avg_execution_time': avg_time or 0.0
            }
    
    def get_active_recoveries(self) -> List[Dict]:
        """Get list of active recoveries"""
        with self.lock:
            return [
                {
                    'action_name': name,
                    'status': recovery['action'].status.value,
                    'start_time': recovery['start_time'],
                    'duration': (datetime.now() - recovery['start_time']).total_seconds()
                }
                for name, recovery in self.active_recoveries.items()
            ]
    
    def cancel_recovery(self, action_name: str):
        """Cancel an active recovery"""
        with self.lock:
            if action_name in self.active_recoveries:
                recovery = self.active_recoveries[action_name]
                recovery['action'].cancel()
                del self.active_recoveries[action_name]
                self.logger.info(f"Cancelled recovery action: {action_name}")
    
    def get_available_actions(self) -> List[Dict]:
        """Get list of available recovery actions"""
        return [
            {
                'name': action.name,
                'description': action.description,
                'recovery_type': action.recovery_type.value,
                'status': action.status.value
            }
            for action in self.recovery_actions.values()
        ]
    
    def cleanup_old_history(self, days: int = 30):
        """Clean up old recovery history"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM recovery_history 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            self.logger.info(f"Cleaned up {deleted_count} old recovery history records")
            return deleted_count
    
    def setup_default_actions(self):
        """Setup default recovery actions"""
        # Database recovery
        db_action = DatabaseRecoveryAction("data/jarvis.db")
        self.register_recovery_action(db_action)
        
        # Filesystem recovery
        fs_action = FilesystemRecoveryAction("config/config.json", "config/config.json.backup")
        self.register_recovery_action(fs_action)
        
        # Memory recovery
        memory_action = MemoryRecoveryAction()
        self.register_recovery_action(memory_action)
        
        # Network recovery
        network_action = NetworkRecoveryAction("eth0")
        self.register_recovery_action(network_action)
        
        self.logger.info("Setup default recovery actions")

# Factory functions for creating common recovery actions
def create_database_recovery_action(db_path: str, backup_path: str = None) -> DatabaseRecoveryAction:
    """Create a database recovery action"""
    return DatabaseRecoveryAction(db_path, backup_path)

def create_filesystem_recovery_action(file_path: str, backup_path: str = None) -> FilesystemRecoveryAction:
    """Create a filesystem recovery action"""
    return FilesystemRecoveryAction(file_path, backup_path)

def create_process_recovery_action(process_name: str, command: str) -> ProcessRecoveryAction:
    """Create a process recovery action"""
    return ProcessRecoveryAction(process_name, command)

def create_memory_recovery_action(process_id: int = None) -> MemoryRecoveryAction:
    """Create a memory recovery action"""
    return MemoryRecoveryAction(process_id)


def get_recovery_manager():
    """Get a singleton instance of RecoveryManager"""
    if not hasattr(get_recovery_manager, '_instance'):
        get_recovery_manager._instance = RecoveryManager()
    return get_recovery_manager._instance
    """Create a memory recovery action"""
    return MemoryRecoveryAction(process_id)

def create_network_recovery_action(interface: str = None) -> NetworkRecoveryAction:
    """Create a network recovery action"""
    return NetworkRecoveryAction(interface)