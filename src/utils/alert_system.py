"""
Sistema de alertas integrado para JARVIS.

Este módulo proporciona un sistema unificado de alertas que coordina
los diferentes sistemas de monitoreo y gestiona notificaciones y acciones.
"""

import json
import smtplib
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum

from src.utils.logger import get_logger


class AlertSeverity(Enum):
    """Severidad de las alertas."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(Enum):
    """Estado de las alertas."""
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class AlertRule:
    """Regla de alerta configurada."""
    
    name: str
    condition: str  # Expresión condicional
    severity: AlertSeverity
    enabled: bool = True
    cooldown_minutes: int = 5
    actions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la regla a un diccionario."""
        return {
            'name': self.name,
            'condition': self.condition,
            'severity': self.severity.value,
            'enabled': self.enabled,
            'cooldown_minutes': self.cooldown_minutes,
            'actions': self.actions
        }


@dataclass
class AlertAction:
    """Acción a realizar ante una alerta."""
    
    name: str
    type: str  # 'email', 'webhook', 'log', 'command'
    config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la acción a un diccionario."""
        return {
            'name': self.name,
            'type': self.type,
            'config': self.config
        }


@dataclass
class Alert:
    """Alerta generada por el sistema."""
    
    id: str
    timestamp: datetime
    title: str
    message: str
    severity: AlertSeverity
    source: str  # 'performance', 'health', 'metrics'
    status: AlertStatus
    details: Dict[str, Any] = field(default_factory=dict)
    actions_triggered: List[str] = field(default_factory=list)
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la alerta a un diccionario."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'title': self.title,
            'message': self.message,
            'severity': self.severity.value,
            'source': self.source,
            'status': self.status.value,
            'details': self.details,
            'actions_triggered': self.actions_triggered,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }


class AlertSystem:
    """Sistema de alertas integrado para JARVIS."""
    
    def __init__(self):
        """Inicializa el sistema de alertas."""
        self.logger = get_logger("AlertSystem")
        
        # Almacenamiento de alertas
        self.alerts: List[Alert] = []
        self.alert_rules: List[AlertRule] = []
        self.alert_actions: List[AlertAction] = []
        
        # Estado del sistema
        self.is_running = False
        self.monitoring_thread: Optional[threading.Thread] = None
        
        # Gestión de cooldown
        self.last_alert_times: Dict[str, datetime] = {}
        
        # Callbacks
        self.alert_callbacks: List[Callable[[Alert], None]] = []
        self.acknowledgement_callbacks: List[Callable[[Alert], None]] = []
        self.resolution_callbacks: List[Callable[[Alert], None]] = []
        
        # Configuración por defecto
        self.default_rules = self._create_default_rules()
        self.default_actions = self._create_default_actions()
        
        # Inicialización
        self.alert_rules.extend(self.default_rules)
        self.alert_actions.extend(self.default_actions)
        
        self.logger._print_log("info", "[ALERT-SYSTEM] Sistema de alertas inicializado", "alert_system.py", "__init__", 85)
        
    def _create_default_rules(self) -> List[AlertRule]:
        """Crea reglas de alerta por defecto."""
        return [
            AlertRule(
                name="high_cpu_usage",
                condition="cpu_percent > 90",
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=10,
                actions=["log_alert", "send_email"]
            ),
            AlertRule(
                name="high_memory_usage", 
                condition="memory_percent > 85",
                severity=AlertSeverity.WARNING,
                cooldown_minutes=15,
                actions=["log_alert"]
            ),
            AlertRule(
                name="disk_space_critical",
                condition="disk_percent > 95",
                severity=AlertSeverity.EMERGENCY,
                cooldown_minutes=5,
                actions=["log_alert", "send_email", "send_webhook"]
            ),
            AlertRule(
                name="component_failure",
                condition="health_status == 'critical'",
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=10,
                actions=["log_alert", "send_email"]
            ),
            AlertRule(
                name="system_overload",
                condition="cpu_percent > 80 and memory_percent > 80",
                severity=AlertSeverity.WARNING,
                cooldown_minutes=20,
                actions=["log_alert"]
            )
        ]
        
    def _create_default_actions(self) -> List[AlertAction]:
        """Crea acciones de alerta por defecto."""
        return [
            AlertAction(
                name="log_alert",
                type="log",
                config={"level": "warning"}
            ),
            AlertAction(
                name="send_email",
                type="email",
                config={
                    "smtp_server": "localhost",
                    "smtp_port": 587,
                    "sender": "jarvis@system.local",
                    "recipients": ["admin@system.local"]
                }
            ),
            AlertAction(
                name="send_webhook",
                type="webhook",
                config={
                    "url": "http://localhost:8080/api/alerts",
                    "method": "POST"
                }
            )
        ]
        
    def start_monitoring(self) -> None:
        """Inicia el monitoreo de alertas."""
        if self.is_running:
            self.logger._print_log("warning", "[ALERT-SYSTEM] El monitoreo de alertas ya está en ejecución", "alert_system.py", "start_monitoring", 92)
            return
            
        self.is_running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        self.logger._print_log("info", "[ALERT-SYSTEM] Monitoreo de alertas iniciado", "alert_system.py", "start_monitoring", 98)
        
    def stop_monitoring(self) -> None:
        """Detiene el monitoreo de alertas."""
        if not self.is_running:
            self.logger._print_log("warning", "[ALERT-SYSTEM] El monitoreo de alertas no está en ejecución", "alert_system.py", "stop_monitoring", 105)
            return
            
        self.is_running = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5.0)
            
        self.logger._print_log("info", "[ALERT-SYSTEM] Monitoreo de alertas detenido", "alert_system.py", "stop_monitoring", 111)
        
    def _monitoring_loop(self) -> None:
        """Bucle principal de monitoreo de alertas."""
        while self.is_running:
            try:
                # Evaluar reglas de alerta
                self._evaluate_alert_rules()
                
                # Limpiar alertas antiguas
                self._cleanup_old_alerts()
                
                time.sleep(30)  # Revisar cada 30 segundos
                
            except Exception as exc:
                self.logger._print_log("error", f"[ALERT-SYSTEM] Error en monitoreo: {exc}", "alert_system.py", "_monitoring_loop", 138)
                time.sleep(60)
                
    def _evaluate_alert_rules(self) -> None:
        """Evalúa todas las reglas de alerta activas."""
        current_time = datetime.now()
        
        for rule in self.alert_rules:
            if not rule.enabled:
                continue
                
            # Verificar cooldown
            rule_key = f"{rule.name}_{rule.severity.value}"
            if rule_key in self.last_alert_times:
                time_since_last = current_time - self.last_alert_times[rule_key]
                if time_since_last < timedelta(minutes=rule.cooldown_minutes):
                    continue
                    
            # Evaluar condición (simplificación - en implementación real usar evaluador de expresiones)
            if self._evaluate_condition(rule.condition):
                # Crear alerta
                alert = Alert(
                    id=f"{rule.name}_{int(current_time.timestamp())}",
                    timestamp=current_time,
                    title=f"Alerta: {rule.name}",
                    message=f"Se ha activado la regla de alerta: {rule.name}",
                    severity=rule.severity,
                    source="alert_system",
                    status=AlertStatus.OPEN,
                    details={'rule': rule.name, 'condition': rule.condition}
                )
                
                # Procesar alerta
                self._process_alert(alert, rule)
                
                # Actualizar tiempo de última alerta
                self.last_alert_times[rule_key] = current_time
                
    def _evaluate_condition(self, condition: str) -> bool:
        """Evalúa una condición de alerta (simplificado)."""
        # En una implementación real, usar un evaluador de expresiones seguro
        try:
            # Evaluar condiciones simples
            if "cpu_percent > 90" in condition:
                # Aquí se obtendría el valor real de CPU
                return True  # Simplificado para demostración
            elif "memory_percent > 85" in condition:
                return True  # Simplificado para demostración
            elif "disk_percent > 95" in condition:
                return True  # Simplificado para demostración
            elif "health_status == 'critical'" in condition:
                return True  # Simplificado para demostración
            elif "cpu_percent > 80 and memory_percent > 80" in condition:
                return True  # Simplificado para demostración
        except Exception:
            pass
            
        return False
        
    def _process_alert(self, alert: Alert, rule: AlertRule) -> None:
        """Procesa una alerta y ejecuta acciones."""
        # Agregar alerta al sistema
        self.alerts.append(alert)
        
        # Ejecutar acciones
        for action_name in rule.actions:
            action = self._get_action(action_name)
            if action:
                try:
                    self._execute_action(action, alert)
                    alert.actions_triggered.append(action_name)
                except Exception as exc:
                    self.logger._print_log("error", f"[ALERT-SYSTEM] Error ejecutando acción {action_name}: {exc}", "alert_system.py", "_process_alert", 195)
                    
        # Notificar callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as exc:
                self.logger._print_log("error", f"[ALERT-SYSTEM] Error en callback de alerta: {exc}", "alert_system.py", "_process_alert", 203)
                
        # Loggear alerta
        log_level = "error" if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY] else "warning"
        self.logger._print_log(log_level, f"[ALERT-SYSTEM] {alert.severity.value.upper()}: {alert.title}", "alert_system.py", "_process_alert", 207)
        
    def _get_action(self, action_name: str) -> Optional[AlertAction]:
        """Obtiene una acción por nombre."""
        for action in self.alert_actions:
            if action.name == action_name:
                return action
        return None
        
    def _execute_action(self, action: AlertAction, alert: Alert) -> None:
        """Ejecuta una acción de alerta."""
        if action.type == "log":
            self._execute_log_action(action, alert)
        elif action.type == "email":
            self._execute_email_action(action, alert)
        elif action.type == "webhook":
            self._execute_webhook_action(action, alert)
        elif action.type == "command":
            self._execute_command_action(action, alert)
            
    def _execute_log_action(self, action: AlertAction, alert: Alert) -> None:
        """Ejecuta acción de logging."""
        log_level = action.config.get("level", "warning")
        self.logger._print_log(log_level, f"[ALERT-ACTION] {alert.title}: {alert.message}", "alert_system.py", "_execute_log_action", 231)
        
    def _execute_email_action(self, action: AlertAction, alert: Alert) -> None:
        """Ejecuta acción de email."""
        # Configuración de email
        smtp_server = action.config.get("smtp_server", "localhost")
        smtp_port = action.config.get("smtp_port", 587)
        sender = action.config.get("sender", "jarvis@system.local")
        recipients = action.config.get("recipients", ["admin@system.local"])
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = f"[JARVIS Alert] {alert.severity.value.upper()}: {alert.title}"
        
        # Cuerpo del mensaje
        body = f"""
Alerta del sistema JARVIS:

Título: {alert.title}
Mensaje: {alert.message}
Severidad: {alert.severity.value}
Fuente: {alert.source}
Timestamp: {alert.timestamp}

Detalles:
{json.dumps(alert.details, indent=2, ensure_ascii=False)}
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Enviar email
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.send_message(msg)
            self.logger._print_log("info", f"[ALERT-ACTION] Email enviado para alerta {alert.id}", "alert_system.py", "_execute_email_action", 262)
        except Exception as exc:
            self.logger._print_log("error", f"[ALERT-ACTION] Error enviando email: {exc}", "alert_system.py", "_execute_email_action", 264)
            
    def _execute_webhook_action(self, action: AlertAction, alert: Alert) -> None:
        """Ejecuta acción de webhook."""
        url = action.config.get("url")
        method = action.config.get("method", "POST")
        
        if not url:
            return
            
        try:
            import requests
            alert_data = alert.to_dict()
            
            if method.upper() == "POST":
                response = requests.post(url, json=alert_data, timeout=10)
            elif method.upper() == "PUT":
                response = requests.put(url, json=alert_data, timeout=10)
            else:
                return
                
            if response.status_code == 200:
                self.logger._print_log("info", f"[ALERT-ACTION] Webhook enviado para alerta {alert.id}", "alert_system.py", "_execute_webhook_action", 288)
            else:
                self.logger._print_log("warning", f"[ALERT-ACTION] Webhook falló para alerta {alert.id}: {response.status_code}", "alert_system.py", "_execute_webhook_action", 290)
                
        except Exception as exc:
            self.logger._print_log("error", f"[ALERT-ACTION] Error enviando webhook: {exc}", "alert_system.py", "_execute_webhook_action", 293)
            
    def _execute_command_action(self, action: AlertAction, alert: Alert) -> None:
        """Ejecuta acción de comando."""
        command = action.config.get("command")
        if not command:
            return
            
        try:
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger._print_log("info", f"[ALERT-ACTION] Comando ejecutado para alerta {alert.id}", "alert_system.py", "_execute_command_action", 309)
            else:
                self.logger._print_log("error", f"[ALERT-ACTION] Comando fallido para alerta {alert.id}: {result.stderr}", "alert_system.py", "_execute_command_action", 311)
                
        except Exception as exc:
            self.logger._print_log("error", f"[ALERT-ACTION] Error ejecutando comando: {exc}", "alert_system.py", "_execute_command_action", 314)
            
    def _cleanup_old_alerts(self) -> None:
        """Limpia alertas antiguas resueltas."""
        cutoff_time = datetime.now() - timedelta(days=30)
        
        # Mantener solo alertas no resueltas o recientes
        self.alerts = [
            alert for alert in self.alerts 
            if alert.status != AlertStatus.RESOLVED or alert.resolved_at and alert.resolved_at > cutoff_time
        ]
        
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acepta una alerta."""
        for alert in self.alerts:
            if alert.id == alert_id and alert.status == AlertStatus.OPEN:
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_by = acknowledged_by
                alert.acknowledged_at = datetime.now()
                
                # Notificar callbacks
                for callback in self.acknowledgement_callbacks:
                    try:
                        callback(alert)
                    except Exception as exc:
                        self.logger._print_log("error", f"[ALERT-SYSTEM] Error en callback de aceptación: {exc}", "alert_system.py", "acknowledge_alert", 338)
                        
                self.logger._print_log("info", f"[ALERT-SYSTEM] Alerta {alert_id} aceptada por {acknowledged_by}", "alert_system.py", "acknowledge_alert", 340)
                return True
                
        return False
        
    def resolve_alert(self, alert_id: str, resolved_by: str) -> bool:
        """Resuelve una alerta."""
        for alert in self.alerts:
            if alert.id == alert_id and alert.status in [AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now()
                
                # Notificar callbacks
                for callback in self.resolution_callbacks:
                    try:
                        callback(alert)
                    except Exception as exc:
                        self.logger._print_log("error", f"[ALERT-SYSTEM] Error en callback de resolución: {exc}", "alert_system.py", "resolve_alert", 356)
                        
                self.logger._print_log("info", f"[ALERT-SYSTEM] Alerta {alert_id} resuelta por {resolved_by}", "alert_system.py", "resolve_alert", 358)
                return True
                
        return False
        
    def get_alerts(self, 
                  severity: Optional[AlertSeverity] = None,
                  status: Optional[AlertStatus] = None,
                  source: Optional[str] = None,
                  limit: Optional[int] = None) -> List[Alert]:
        """Obtiene alertas filtradas."""
        alerts = self.alerts
        
        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]
        if status:
            alerts = [alert for alert in alerts if alert.status == status]
        if source:
            alerts = [alert for alert in alerts if alert.source == source]
            
        # Ordenar por timestamp (más recientes primero)
        alerts.sort(key=lambda x: x.timestamp, reverse=True)
        
        if limit:
            alerts = alerts[:limit]
            
        return alerts
        
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas de alertas."""
        total_alerts = len(self.alerts)
        open_alerts = len([a for a in self.alerts if a.status == AlertStatus.OPEN])
        acknowledged_alerts = len([a for a in self.alerts if a.status == AlertStatus.ACKNOWLEDGED])
        resolved_alerts = len([a for a in self.alerts if a.status == AlertStatus.RESOLVED])
        
        severity_counts = {}
        for severity in AlertSeverity:
            severity_counts[severity.value] = len([a for a in self.alerts if a.severity == severity])
            
        source_counts = {}
        for source in set(alert.source for alert in self.alerts):
            source_counts[source] = len([a for a in self.alerts if a.source == source])
            
        return {
            'total_alerts': total_alerts,
            'open_alerts': open_alerts,
            'acknowledged_alerts': acknowledged_alerts,
            'resolved_alerts': resolved_alerts,
            'severity_counts': severity_counts,
            'source_counts': source_counts,
            'last_24h': len([a for a in self.alerts if a.timestamp > datetime.now() - timedelta(hours=24)])
        }
        
    def add_alert_callback(self, callback: Callable[[Alert], None]) -> None:
        """Agrega un callback para recibir alertas."""
        self.alert_callbacks.append(callback)
        
    def add_acknowledgement_callback(self, callback: Callable[[Alert], None]) -> None:
        """Agrega un callback para recibir aceptaciones de alertas."""
        self.acknowledgement_callbacks.append(callback)
        
    def add_resolution_callback(self, callback: Callable[[Alert], None]) -> None:
        """Agrega un callback para recibir resoluciones de alertas."""
        self.resolution_callbacks.append(callback)
        
    def add_alert_rule(self, rule: AlertRule) -> None:
        """Agrega una regla de alerta."""
        self.alert_rules.append(rule)
        self.logger._print_log("info", f"[ALERT-SYSTEM] Regla de alerta agregada: {rule.name}", "alert_system.py", "add_alert_rule", 418)
        
    def add_alert_action(self, action: AlertAction) -> None:
        """Agrega una acción de alerta."""
        self.alert_actions.append(action)
        self.logger._print_log("info", f"[ALERT-SYSTEM] Acción de alerta agregada: {action.name}", "alert_system.py", "add_alert_action", 423)
        
    def export_alerts(self, filepath: str, 
                     severity: Optional[AlertSeverity] = None,
                     status: Optional[AlertStatus] = None,
                     source: Optional[str] = None) -> None:
        """Exporta alertas a un archivo JSON."""
        alerts = self.get_alerts(severity, status, source)
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'total_alerts': len(alerts),
            'alerts': [alert.to_dict() for alert in alerts]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
            
        self.logger._print_log("info", f"[ALERT-SYSTEM] Alertas exportadas a {filepath}", "alert_system.py", "export_alerts", 439)
        
    def clear_resolved_alerts(self) -> None:
        """Limpia alertas resueltas."""
        resolved_count = len([a for a in self.alerts if a.status == AlertStatus.RESOLVED])
        self.alerts = [a for a in self.alerts if a.status != AlertStatus.RESOLVED]
        
        self.logger._print_log("info", f"[ALERT-SYSTEM] {resolved_count} alertas resueltas limpiadas", "alert_system.py", "clear_resolved_alerts", 447)
        
    def __enter__(self):
        """Context manager entry."""
        self.start_monitoring()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_monitoring()


# Instancia global única
_alert_system: Optional[AlertSystem] = None


def get_alert_system() -> AlertSystem:
    """Obtiene la instancia global del sistema de alertas."""
    global _alert_system
    if _alert_system is None:
        _alert_system = AlertSystem()
    return _alert_system


def start_alert_monitoring() -> None:
    """Inicia el monitoreo de alertas global."""
    alert_system = get_alert_system()
    alert_system.start_monitoring()


def stop_alert_monitoring() -> None:
    """Detiene el monitoreo de alertas global."""
    alert_system = get_alert_system()
    alert_system.stop_monitoring()