"""
Error Recovery Dashboard for JARVIS System
Visual interface for monitoring and managing error recovery operations
"""

import time
import threading
import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import queue

class DashboardView(Enum):
    """Dashboard view types"""
    OVERVIEW = "overview"
    ACTIVE_ERRORS = "active_errors"
    RECOVERY_HISTORY = "recovery_history"
    SYSTEM_HEALTH = "system_health"
    ALERTS = "alerts"

class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorRecoveryDashboard:
    """Main dashboard for error recovery monitoring"""
    
    def __init__(self, db_path: str = "data/error_dashboard.db", update_interval: float = 5.0):
        self.db_path = db_path
        self.update_interval = update_interval
        self.logger = logging.getLogger(__name__)
        self.current_view = DashboardView.OVERVIEW
        self.running = False
        self.update_thread = None
        self.data_cache = {}
        self.cache_expiry = {}
        self.cache_ttl = 10.0  # Cache TTL in seconds
        
        # Initialize database
        self._init_database()
        
        # Setup data sources
        self._setup_data_sources()
    
    def _init_database(self):
        """Initialize dashboard database"""
        os.makedirs(os.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Dashboard views table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dashboard_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    view_name TEXT NOT NULL UNIQUE,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                )
            ''')
            
            # User preferences table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    preference_key TEXT NOT NULL UNIQUE,
                    preference_value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Dashboard metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dashboard_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metric_type TEXT DEFAULT 'counter'
                )
            ''')
            
            conn.commit()
    
    def _setup_data_sources(self):
        """Setup data sources for dashboard"""
        # Connect to various data sources
        self.error_recovery_db = "data/error_recovery.db"
        self.health_monitor_db = "data/health_monitor.db"
        self.recovery_manager_db = "data/recovery_manager.db"
    
    def start_dashboard(self):
        """Start the dashboard update thread"""
        if self.running:
            self.logger.warning("Dashboard is already running")
            return
        
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("Error recovery dashboard started")
    
    def stop_dashboard(self):
        """Stop the dashboard update thread"""
        self.running = False
        if self.update_thread:
            self.update_thread.join()
        self.logger.info("Error recovery dashboard stopped")
    
    def _update_loop(self):
        """Main dashboard update loop"""
        while self.running:
            try:
                self._update_all_data()
                time.sleep(self.update_interval)
            except Exception as e:
                self.logger.error(f"Dashboard update error: {e}")
                time.sleep(self.update_interval)
    
    def _update_all_data(self):
        """Update all cached data"""
        # Update overview data
        self._get_overview_data()
        
        # Update active errors
        self._get_active_errors_data()
        
        # Update recovery history
        self._get_recovery_history_data()
        
        # Update system health
        self._get_system_health_data()
        
        # Update alerts
        self._get_alerts_data()
    
    def _get_cached_data(self, key: str) -> Optional[Dict]:
        """Get cached data if available and not expired"""
        current_time = time.time()
        
        if key in self.data_cache and key in self.cache_expiry:
            if current_time < self.cache_expiry[key]:
                return self.data_cache[key]
            else:
                # Cache expired, remove it
                del self.data_cache[key]
                del self.cache_expiry[key]
        
        return None
    
    def _cache_data(self, key: str, data: Dict, ttl: float = None):
        """Cache data with optional TTL"""
        self.data_cache[key] = data
        self.cache_expiry[key] = time.time() + (ttl or self.cache_ttl)
    
    def _get_overview_data(self) -> Dict:
        """Get dashboard overview data"""
        cache_key = "overview_data"
        cached_data = self._get_cached_data(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            # Get error statistics
            error_stats = self._get_error_statistics()
            
            # Get recovery statistics
            recovery_stats = self._get_recovery_statistics()
            
            # Get system health
            health_data = self._get_system_health()
            
            # Get active recoveries
            active_recoveries = self._get_active_recoveries()
            
            overview_data = {
                'timestamp': datetime.now().isoformat(),
                'error_statistics': error_stats,
                'recovery_statistics': recovery_stats,
                'system_health': health_data,
                'active_recoveries': active_recoveries,
                'total_errors': sum(stats.get('total_count', 0) for stats in error_stats.values()),
                'total_recoveries': recovery_stats.get('total_attempts', 0),
                'success_rate': recovery_stats.get('success_rate', 0.0)
            }
            
            self._cache_data(cache_key, overview_data)
            return overview_data
            
        except Exception as e:
            self.logger.error(f"Error getting overview data: {e}")
            return {}
    
    def _get_active_errors_data(self) -> Dict:
        """Get active errors data"""
        cache_key = "active_errors_data"
        cached_data = self._get_cached_data(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            active_errors = []
            
            # Get errors from error recovery database
            if os.path.exists(self.error_recovery_db):
                with sqlite3.connect(self.error_recovery_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT * FROM error_logs 
                        WHERE recovery_attempted = FALSE 
                        ORDER BY timestamp DESC
                        LIMIT 50
                    ''')
                    
                    columns = [desc[0] for desc in cursor.description]
                    active_errors.extend([dict(zip(columns, row)) for row in cursor.fetchall()])
            
            data = {
                'timestamp': datetime.now().isoformat(),
                'active_errors': active_errors,
                'total_count': len(active_errors),
                'by_severity': self._count_errors_by_severity(active_errors),
                'by_component': self._count_errors_by_component(active_errors)
            }
            
            self._cache_data(cache_key, data)
            return data
            
        except Exception as e:
            self.logger.error(f"Error getting active errors data: {e}")
            return {}
    
    def _get_recovery_history_data(self) -> Dict:
        """Get recovery history data"""
        cache_key = "recovery_history_data"
        cached_data = self._get_cached_data(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            recovery_history = []
            
            # Get recovery history from recovery manager database
            if os.path.exists(self.recovery_manager_db):
                with sqlite3.connect(self.recovery_manager_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT * FROM recovery_history 
                        ORDER BY timestamp DESC
                        LIMIT 100
                    ''')
                    
                    columns = [desc[0] for desc in cursor.description]
                    recovery_history.extend([dict(zip(columns, row)) for row in cursor.fetchall()])
            
            data = {
                'timestamp': datetime.now().isoformat(),
                'recovery_history': recovery_history,
                'total_count': len(recovery_history),
                'success_rate': sum(1 for r in recovery_history if r['success']) / len(recovery_history) if recovery_history else 0,
                'by_action': self._count_recoveries_by_action(recovery_history),
                'by_component': self._count_recoveries_by_component(recovery_history)
            }
            
            self._cache_data(cache_key, data)
            return data
            
        except Exception as e:
            self.logger.error(f"Error getting recovery history data: {e}")
            return {}
    
    def _get_system_health_data(self) -> Dict:
        """Get system health data"""
        cache_key = "system_health_data"
        cached_data = self._get_cached_data(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            health_data = {}
            
            # Get health data from health monitor database
            if os.path.exists(self.health_monitor_db):
                with sqlite3.connect(self.health_monitor_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT * FROM health_history 
                        ORDER BY timestamp DESC
                        LIMIT 10
                    ''')
                    
                    columns = [desc[0] for desc in cursor.description]
                    health_history = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    
                    # Get active alerts
                    cursor.execute('''
                        SELECT * FROM health_alerts 
                        WHERE resolved = FALSE 
                        ORDER BY timestamp DESC
                    ''')
                    
                    alert_columns = [desc[0] for desc in cursor.description]
                    active_alerts = [dict(zip(alert_columns, row)) for row in cursor.fetchall()]
                    
                    health_data = {
                        'timestamp': datetime.now().isoformat(),
                        'health_history': health_history,
                        'active_alerts': active_alerts,
                        'total_alerts': len(active_alerts),
                        'by_severity': self._count_alerts_by_severity(active_alerts)
                    }
            
            self._cache_data(cache_key, health_data)
            return health_data
            
        except Exception as e:
            self.logger.error(f"Error getting system health data: {e}")
            return {}
    
    def _get_alerts_data(self) -> Dict:
        """Get alerts data"""
        cache_key = "alerts_data"
        cached_data = self._get_cached_data(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            alerts = []
            
            # Get alerts from various sources
            if os.path.exists(self.error_recovery_db):
                with sqlite3.connect(self.error_recovery_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT * FROM error_logs 
                        WHERE recovery_attempted = FALSE 
                        ORDER BY timestamp DESC
                        LIMIT 20
                    ''')
                    
                    columns = [desc[0] for desc in cursor.description]
                    alerts.extend([dict(zip(columns, row)) for row in cursor.fetchall()])
            
            if os.path.exists(self.health_monitor_db):
                with sqlite3.connect(self.health_monitor_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT * FROM health_alerts 
                        WHERE resolved = FALSE 
                        ORDER BY timestamp DESC
                        LIMIT 20
                    ''')
                    
                    columns = [desc[0] for desc in cursor.description]
                    alerts.extend([dict(zip(columns, row)) for row in cursor.fetchall()])
            
            data = {
                'timestamp': datetime.now().isoformat(),
                'alerts': alerts,
                'total_count': len(alerts),
                'by_severity': self._count_alerts_by_severity(alerts),
                'by_source': self._count_alerts_by_source(alerts)
            }
            
            self._cache_data(cache_key, data)
            return data
            
        except Exception as e:
            self.logger.error(f"Error getting alerts data: {e}")
            return {}
    
    def _get_error_statistics(self) -> Dict:
        """Get error statistics from database"""
        stats = {}
        
        if os.path.exists(self.error_recovery_db):
            with sqlite3.connect(self.error_recovery_db) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT error_type, severity, COUNT(*) as count 
                    FROM error_logs 
                    GROUP BY error_type, severity
                ''')
                
                for row in cursor.fetchall():
                    error_type, severity, count = row
                    key = f"{error_type}_{severity}"
                    stats[key] = {'count': count}
        
        return stats
    
    def _get_recovery_statistics(self) -> Dict:
        """Get recovery statistics from database"""
        stats = {}
        
        if os.path.exists(self.recovery_manager_db):
            with sqlite3.connect(self.recovery_manager_db) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_attempts,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_attempts,
                        AVG(execution_time) as avg_execution_time
                    FROM recovery_history
                ''')
                
                result = cursor.fetchone()
                total_attempts, successful_attempts, avg_time = result
                
                stats = {
                    'total_attempts': total_attempts,
                    'successful_attempts': successful_attempts,
                    'success_rate': successful_attempts / total_attempts if total_attempts > 0 else 0,
                    'avg_execution_time': avg_time or 0.0
                }
        
        return stats
    
    def _get_system_health(self) -> Dict:
        """Get current system health"""
        # This would typically query the health monitor
        return {
            'overall_status': 'healthy',
            'components': {
                'cpu': {'status': 'healthy', 'usage': 45.2},
                'memory': {'status': 'warning', 'usage': 78.5},
                'disk': {'status': 'healthy', 'usage': 65.3},
                'network': {'status': 'healthy', 'errors': 0}
            }
        }
    
    def _get_active_recoveries(self) -> List[Dict]:
        """Get list of active recoveries"""
        # This would typically query the recovery manager
        return []
    
    def _count_errors_by_severity(self, errors: List[Dict]) -> Dict:
        """Count errors by severity"""
        counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        
        for error in errors:
            severity = error.get('severity', 'unknown')
            if severity in counts:
                counts[severity] += 1
        
        return counts
    
    def _count_errors_by_component(self, errors: List[Dict]) -> Dict:
        """Count errors by component"""
        counts = {}
        
        for error in errors:
            component = error.get('component', 'unknown')
            counts[component] = counts.get(component, 0) + 1
        
        return counts
    
    def _count_recoveries_by_action(self, recoveries: List[Dict]) -> Dict:
        """Count recoveries by action"""
        counts = {}
        
        for recovery in recoveries:
            action = recovery.get('action_name', 'unknown')
            counts[action] = counts.get(action, 0) + 1
        
        return counts
    
    def _count_recoveries_by_component(self, recoveries: List[Dict]) -> Dict:
        """Count recoveries by component"""
        counts = {}
        
        for recovery in recoveries:
            component = recovery.get('component', 'unknown')
            counts[component] = counts.get(component, 0) + 1
        
        return counts
    
    def _count_alerts_by_severity(self, alerts: List[Dict]) -> Dict:
        """Count alerts by severity"""
        counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        
        for alert in alerts:
            severity = alert.get('severity', 'unknown')
            if severity in counts:
                counts[severity] += 1
        
        return counts
    
    def _count_alerts_by_source(self, alerts: List[Dict]) -> Dict:
        """Count alerts by source"""
        counts = {}
        
        for alert in alerts:
            source = alert.get('component', 'unknown')
            counts[source] = counts.get(source, 0) + 1
        
        return counts
    
    def get_dashboard_data(self, view: DashboardView = None) -> Dict:
        """Get dashboard data for specified view"""
        if view:
            self.current_view = view
        
        if self.current_view == DashboardView.OVERVIEW:
            return self._get_overview_data()
        elif self.current_view == DashboardView.ACTIVE_ERRORS:
            return self._get_active_errors_data()
        elif self.current_view == DashboardView.RECOVERY_HISTORY:
            return self._get_recovery_history_data()
        elif self.current_view == DashboardView.SYSTEM_HEALTH:
            return self._get_system_health_data()
        elif self.current_view == DashboardView.ALERTS:
            return self._get_alerts_data()
        else:
            return self._get_overview_data()
    
    def get_dashboard_views(self) -> List[Dict]:
        """Get available dashboard views"""
        return [
            {'name': view.value, 'description': f"{view.value.replace('_', ' ').title()} View"}
            for view in DashboardView
        ]
    
    def refresh_data(self):
        """Force refresh of all cached data"""
        self.data_cache.clear()
        self.cache_expiry.clear()
        self._update_all_data()
    
    def log_view_access(self, view_name: str):
        """Log dashboard view access"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO dashboard_views (view_name, last_accessed, access_count)
                VALUES (?, CURRENT_TIMESTAMP, COALESCE((SELECT access_count FROM dashboard_views WHERE view_name = ?) + 1, 1))
            ''', (view_name, view_name))
            conn.commit()
    
    def get_view_statistics(self) -> Dict:
        """Get dashboard view access statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT view_name, access_count, last_accessed 
                FROM dashboard_views 
                ORDER BY access_count DESC
            ''')
            
            results = cursor.fetchall()
            return [
                {
                    'view_name': row[0],
                    'access_count': row[1],
                    'last_accessed': row[2]
                }
                for row in results
            ]
    
    def __str__(self):
        return f"ErrorRecoveryDashboard(db_path='{self.db_path}', view={self.current_view.value}, running={self.running})"


def get_error_dashboard():
    """Get a singleton instance of ErrorRecoveryDashboard"""
    if not hasattr(get_error_dashboard, '_instance'):
        get_error_dashboard._instance = ErrorRecoveryDashboard()
    return get_error_dashboard._instance


def start_error_dashboard():
    """Start the error dashboard"""
    dashboard = get_error_dashboard()
    return dashboard.start()


def stop_error_dashboard():
    """Stop the error dashboard"""
    dashboard = get_error_dashboard()
    return dashboard.stop()