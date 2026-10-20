"""
Dashboard interactivo para monitoreo y gestión de logs de Jarvis.
"""

import json
import logging
import socket
import sqlite3
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import time
import asyncio
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO, emit
import plotly.graph_objects as go
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
import pandas as pd
import numpy as np


class DashboardView(Enum):
    """Vistas del dashboard."""
    OVERVIEW = "overview"
    REAL_TIME = "real_time"
    ANALYTICS = "analytics"
    PATTERNS = "patterns"
    PREDICTIONS = "predictions"
    PERFORMANCE = "performance"
    ALERTS = "alerts"
    SETTINGS = "settings"


class DashboardWidget(Enum):
    """Tipos de widgets del dashboard."""
    METRIC_CARD = "metric_card"
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    HEATMAP = "heatmap"
    TABLE = "table"
    LOG_VIEWER = "log_viewer"
    ALERT_LIST = "alert_list"


@dataclass
class WidgetConfig:
    """Configuración de widget."""
    id: str
    type: DashboardWidget
    title: str
    data_source: str
    refresh_interval: int = 30
    position: Tuple[int, int] = (0, 0)
    size: Tuple[int, int] = (6, 4)
    options: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['type'] = self.type.value
        return data


@dataclass
class DashboardAlert:
    """Alerta del dashboard."""
    id: str
    title: str
    message: str
    severity: str  # info, warning, error, critical
    timestamp: datetime
    acknowledged: bool = False
    source: str = "system"
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class RealTimeDataStreamer:
    """Flujo de datos en tiempo real."""
    
    def __init__(self, max_points: int = 1000):
        self.max_points = max_points
        self.data_streams = defaultdict(lambda: deque(maxlen=max_points))
        self.subscribers = defaultdict(list)
        self.lock = threading.Lock()
        
    def add_data_point(self, stream_name: str, data: Dict[str, Any]) -> None:
        """Añadir punto de datos a un flujo."""
        with self.lock:
            timestamp = datetime.now()
            data_point = {
                'timestamp': timestamp,
                'value': data.get('value'),
                'metadata': data.get('metadata', {})
            }
            
            self.data_streams[stream_name].append(data_point)
            
            # Notificar subscriptores
            for subscriber in self.subscribers[stream_name]:
                try:
                    subscriber(data_point)
                except Exception as e:
                    logging.error(f"Error notificando subscriptor: {e}")
    
    def get_stream_data(self, stream_name: str, limit: int = None) -> List[Dict[str, Any]]:
        """Obtener datos de un flujo."""
        with self.lock:
            stream_data = list(self.data_streams[stream_name])
            if limit:
                return stream_data[-limit:]
            return stream_data
    
    def subscribe_to_stream(self, stream_name: str, callback: callable) -> None:
        """Suscribirse a un flujo de datos."""
        with self.lock:
            self.subscribers[stream_name].append(callback)
    
    def unsubscribe_from_stream(self, stream_name: str, callback: callable) -> None:
        """Desuscribirse de un flujo de datos."""
        with self.lock:
            if callback in self.subscribers[stream_name]:
                self.subscribers[stream_name].remove(callback)


class LogDashboard:
    """Dashboard principal de logs."""
    
    # Puertos alternativos si el configurado no está disponible.
    # En Windows, hacer bind sobre un puerto ya servido por otro proceso
    # devuelve WSAEACCES (10013) en vez de WSAEADDRINUSE.
    FALLBACK_PORTS = (8051, 8052, 8053, 5001, 5055)
    
    def __init__(self, db_path: str = "logs/dashboard.db", 
                 port: int = 5000, host: str = "localhost"):
        self.db_path = Path(db_path)
        self.port = port
        self.host = host
        self.active_port = port
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.data_streamer = RealTimeDataStreamer()
        
        # Estado del dashboard
        self.current_view = DashboardView.OVERVIEW
        self.widgets = {}
        self.alerts = []
        self.user_preferences = {}
        self.is_running = False
        
        # Configurar rutas
        self._setup_routes()
        
        # Crear base de datos
        self._create_database()
        
        # Iniciar hilo de actualización
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        
    def _create_database(self) -> None:
        """Crear base de datos del dashboard."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabla de widgets
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS widgets (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    refresh_interval INTEGER DEFAULT 30,
                    position_x INTEGER DEFAULT 0,
                    position_y INTEGER DEFAULT 0,
                    size_width INTEGER DEFAULT 6,
                    size_height INTEGER DEFAULT 4,
                    options TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Tabla de alertas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    source TEXT DEFAULT "system",
                    metadata TEXT
                )
            ''')
            
            # Tabla de preferencias de usuario
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    preferences TEXT,
                    last_updated TEXT NOT NULL
                )
            ''')
            
            conn.commit()
    
    def _setup_routes(self) -> None:
        """Configurar rutas de la aplicación Flask."""
        
        @self.app.route('/')
        def dashboard():
            """Página principal del dashboard."""
            return render_template_string(self._get_dashboard_template())
        
        @self.app.route('/api/widgets')
        def get_widgets():
            """Obtener widgets del dashboard."""
            return jsonify([widget.to_dict() for widget in self.widgets.values()])
        
        @self.app.route('/api/widgets', methods=['POST'])
        def create_widget():
            """Crear nuevo widget."""
            data = request.get_json()
            widget = WidgetConfig(
                id=data.get('id', f"widget_{int(time.time())}"),
                type=DashboardWidget(data['type']),
                title=data['title'],
                data_source=data['data_source'],
                refresh_interval=data.get('refresh_interval', 30),
                position=data.get('position', (0, 0)),
                size=data.get('size', (6, 4)),
                options=data.get('options', {})
            )
            
            self.widgets[widget.id] = widget
            self._save_widget(widget)
            
            return jsonify(widget.to_dict()), 201
        
        @self.app.route('/api/widgets/<widget_id>', methods=['DELETE'])
        def delete_widget(widget_id):
            """Eliminar widget."""
            if widget_id in self.widgets:
                del self.widgets[widget_id]
                self._delete_widget(widget_id)
                return '', 204
            return jsonify({'error': 'Widget not found'}), 404
        
        @self.app.route('/api/alerts')
        def get_alerts():
            """Obtener alertas."""
            return jsonify([alert.to_dict() for alert in self.alerts])
        
        @self.app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
        def acknowledge_alert(alert_id):
            """Marcar alerta como reconocida."""
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    self._save_alert(alert)
                    return jsonify(alert.to_dict())
            return jsonify({'error': 'Alert not found'}), 404
        
        @self.app.route('/api/data/<stream_name>')
        def get_stream_data(stream_name):
            """Obtener datos de un flujo."""
            limit = request.args.get('limit', 100, type=int)
            data = self.data_streamer.get_stream_data(stream_name, limit)
            return jsonify(data)
        
        @self.app.route('/api/analytics/<analytics_type>')
        def get_analytics(analytics_type):
            """Obtener análisis de datos."""
            # Aquí se integraría con el sistema de análisis
            return jsonify({'message': 'Analytics endpoint not implemented yet'})
        
        @self.socketio.on('connect')
        def handle_connect():
            """Manejar conexión WebSocket."""
            print('Client connected')
            emit('connected', {'data': 'Connected to dashboard'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Manejar desconexión WebSocket."""
            print('Client disconnected')
        
        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """Manejar suscripción a datos en tiempo real."""
            stream_name = data.get('stream')
            if stream_name:
                self.data_streamer.subscribe_to_stream(stream_name, 
                    lambda data: emit('data_update', {'stream': stream_name, 'data': data}))
    
    def _get_dashboard_template(self) -> str:
        """Obtener plantilla HTML del dashboard."""
        return '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard de Logs - Jarvis</title>
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { margin: 0; padding: 20px; font-family: Arial, sans-serif; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        .nav { display: flex; gap: 10px; margin-bottom: 20px; }
        .nav button { padding: 10px 20px; border: none; border-radius: 5px; background: #3498db; color: white; cursor: pointer; }
        .nav button.active { background: #2980b9; }
        .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .widget { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .widget h3 { margin-top: 0; color: #2c3e50; }
        .metric { font-size: 2em; font-weight: bold; color: #3498db; }
        .chart { width: 100%; height: 300px; }
        .alerts { margin-top: 20px; }
        .alert { padding: 10px; margin: 5px 0; border-radius: 5px; }
        .alert.info { background: #d1ecf1; color: #0c5460; }
        .alert.warning { background: #fff3cd; color: #856404; }
        .alert.error { background: #f8d7da; color: #721c24; }
        .alert.critical { background: #f5c6cb; color: #721c24; font-weight: bold; }
        .log-viewer { background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; font-family: monospace; max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Dashboard de Logs - Jarvis</h1>
        <p>Monitoreo y gestión avanzada de logs</p>
    </div>
    
    <div class="nav">
        <button class="active" onclick="switchView('overview')">Resumen</button>
        <button onclick="switchView('real_time')">Tiempo Real</button>
        <button onclick="switchView('analytics')">Análisis</button>
        <button onclick="switchView('patterns')">Patrones</button>
        <button onclick="switchView('predictions')">Predicciones</button>
        <button onclick="switchView('performance')">Rendimiento</button>
        <button onclick="switchView('alerts')">Alertas</button>
    </div>
    
    <div id="dashboard-content">
        <div class="dashboard" id="widgets-container">
            <!-- Los widgets se cargarán dinámicamente -->
        </div>
        
        <div class="alerts" id="alerts-container">
            <h3>Alertas Recientes</h3>
            <div id="alerts-list">
                <!-- Las alertas se cargarán dinámicamente -->
            </div>
        </div>
    </div>
    
    <script>
        const socket = io();
        let currentView = 'overview';
        
        // Conectar al servidor
        socket.on('connect', function() {
            console.log('Connected to dashboard server');
        });
        
        // Suscribirse a datos en tiempo real
        socket.emit('subscribe', { stream: 'system_metrics' });
        
        socket.on('data_update', function(data) {
            console.log('Data update:', data);
            updateCharts(data);
        });
        
        function switchView(view) {
            currentView = view;
            document.querySelectorAll('.nav button').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            loadDashboardContent(view);
        }
        
        function loadDashboardContent(view) {
            // Cargar contenido específico para cada vista
            fetch(`/api/widgets`)
                .then(response => response.json())
                .then(widgets => {
                    renderWidgets(widgets, view);
                });
            
            loadAlerts();
        }
        
        function renderWidgets(widgets, view) {
            const container = document.getElementById('widgets-container');
            container.innerHTML = '';
            
            widgets.forEach(widget => {
                if (widget.data_source.includes(view) || view === 'overview') {
                    const widgetElement = createWidgetElement(widget);
                    container.appendChild(widgetElement);
                }
            });
        }
        
        function createWidgetElement(widget) {
            const div = document.createElement('div');
            div.className = 'widget';
            div.style.gridColumn = `${widget.position[0] + 1} / span ${widget.size[0]}`;
            div.style.gridRow = `${widget.position[1] + 1} / span ${widget.size[1]}`;
            
            div.innerHTML = `
                <h3>${widget.title}</h3>
                <div id="chart-${widget.id}" class="chart"></div>
            `;
            
            return div;
        }
        
        function updateCharts(data) {
            // Actualizar gráficos con datos en tiempo real
            const chartId = `chart-${data.widget_id}`;
            const chartElement = document.getElementById(chartId);
            if (chartElement) {
                // Crear o actualizar gráfico
                const trace = {
                    x: [new Date().toISOString()],
                    y: [data.value],
                    type: 'scatter',
                    mode: 'lines+markers',
                    name: data.stream
                };
                
                const layout = {
                    title: data.stream,
                    xaxis: { title: 'Tiempo' },
                    yaxis: { title: 'Valor' }
                };
                
                Plotly.newPlot(chartId, [trace], layout);
            }
        }
        
        function loadAlerts() {
            fetch('/api/alerts')
                .then(response => response.json())
                .then(alerts => {
                    const alertsList = document.getElementById('alerts-list');
                    alertsList.innerHTML = '';
                    
                    alerts.forEach(alert => {
                        const alertElement = document.createElement('div');
                        alertElement.className = `alert ${alert.severity}`;
                        alertElement.innerHTML = `
                            <strong>${alert.title}</strong>
                            <p>${alert.message}</p>
                            <small>${new Date(alert.timestamp).toLocaleString()}</small>
                            ${!alert.acknowledged ? `<button onclick="acknowledgeAlert('${alert.id}')">Reconocer</button>` : '<span style="color: green;">✓ Reconocida</span>'}
                        `;
                        alertsList.appendChild(alertElement);
                    });
                });
        }
        
        function acknowledgeAlert(alertId) {
            fetch(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' })
                .then(response => response.json())
                .then(() => loadAlerts());
        }
        
        // Cargar contenido inicial
        loadDashboardContent('overview');
        
        // Actualizar datos periódicamente
        setInterval(() => {
            loadDashboardContent(currentView);
        }, 30000);
    </script>
</body>
</html>
        '''
    
    def _update_loop(self) -> None:
        """Bucle de actualización del dashboard."""
        while self.is_running:
            try:
                # Actualizar datos en tiempo real
                self._update_real_time_data()
                
                # Actualizar widgets
                self._update_widgets()
                
                # Verificar alertas
                self._check_alerts()
                
                time.sleep(5)  # Actualizar cada 5 segundos
                
            except Exception as e:
                logging.error(f"Error en bucle de actualización: {e}")
                time.sleep(10)  # Esperar más tiempo en caso de error
    
    def _update_real_time_data(self) -> None:
        """Actualizar datos en tiempo real."""
        # Simular datos de sistema
        import random
        
        # Métricas del sistema
        self.data_streamer.add_data_point('cpu_usage', {
            'value': random.uniform(20, 80),
            'metadata': {'unit': '%', 'source': 'system'}
        })
        
        self.data_streamer.add_data_point('memory_usage', {
            'value': random.uniform(30, 90),
            'metadata': {'unit': '%', 'source': 'system'}
        })
        
        self.data_streamer.add_data_point('error_rate', {
            'value': random.uniform(0, 0.1),
            'metadata': {'unit': 'ratio', 'source': 'logs'}
        })
        
        self.data_streamer.add_data_point('response_time', {
            'value': random.uniform(100, 2000),
            'metadata': {'unit': 'ms', 'source': 'performance'}
        })
    
    def _update_widgets(self) -> None:
        """Actualizar widgets del dashboard."""
        for widget in self.widgets.values():
            if widget.refresh_interval > 0:
                # Obtener datos para el widget
                data = self._get_widget_data(widget)
                
                # Notificar actualización a clientes WebSocket
                self.socketio.emit('widget_update', {
                    'widget_id': widget.id,
                    'data': data
                })
    
    def _get_widget_data(self, widget: WidgetConfig) -> Dict[str, Any]:
        """Obtener datos para un widget específico."""
        try:
            if widget.type == DashboardWidget.METRIC_CARD:
                return self._get_metric_card_data(widget)
            elif widget.type == DashboardWidget.LINE_CHART:
                return self._get_line_chart_data(widget)
            elif widget.type == DashboardWidget.BAR_CHART:
                return self._get_bar_chart_data(widget)
            elif widget.type == DashboardWidget.PIE_CHART:
                return self._get_pie_chart_data(widget)
            elif widget.type == DashboardWidget.TABLE:
                return self._get_table_data(widget)
            else:
                return {'error': 'Widget type not supported'}
        except Exception as e:
            logging.error(f"Error obteniendo datos para widget {widget.id}: {e}")
            return {'error': str(e)}
    
    def _get_metric_card_data(self, widget: WidgetConfig) -> Dict[str, Any]:
        """Obtener datos para widget de métrica."""
        # Simular datos de métrica
        import random
        
        return {
            'value': random.uniform(0, 100),
            'unit': widget.options.get('unit', '%'),
            'trend': random.choice(['up', 'down', 'stable']),
            'change': random.uniform(-10, 10)
        }
    
    def _get_line_chart_data(self, widget: WidgetConfig) -> Dict[str, Any]:
        """Obtener datos para widget de gráfico de línea."""
        stream_name = widget.data_source
        data = self.data_streamer.get_stream_data(stream_name, 50)
        
        return {
            'timestamps': [point['timestamp'].isoformat() for point in data],
            'values': [point['value'] for point in data]
        }
    
    def _get_bar_chart_data(self, widget: WidgetConfig) -> Dict[str, Any]:
        """Obtener datos para widget de gráfico de barras."""
        # Simular datos de categorías
        categories = ['Errors', 'Warnings', 'Info', 'Debug']
        values = [random.randint(0, 100) for _ in categories]
        
        return {
            'categories': categories,
            'values': values
        }
    
    def _get_pie_chart_data(self, widget: WidgetConfig) -> Dict[str, Any]:
        """Obtener datos para widget de gráfico circular."""
        # Simular datos de distribución
        import random
        labels = ['System', 'Application', 'Network', 'Security']
        values = [random.randint(10, 100) for _ in labels]
        
        return {
            'labels': labels,
            'values': values
        }
    
    def _get_table_data(self, widget: WidgetConfig) -> Dict[str, Any]:
        """Obtener datos para widget de tabla."""
        # Simular datos de tabla
        import random
        columns = ['Timestamp', 'Level', 'Category', 'Message']
        rows = []
        
        for i in range(10):
            rows.append([
                datetime.now().isoformat(),
                random.choice(['INFO', 'WARNING', 'ERROR']),
                random.choice(['system', 'application', 'network']),
                f"Sample message {i}"
            ])
        
        return {
            'columns': columns,
            'rows': rows
        }
    
    def _check_alerts(self) -> None:
        """Verificar y generar alertas."""
        # Verificar umbrales de métricas
        cpu_data = self.data_streamer.get_stream_data('cpu_usage', 1)
        if cpu_data and cpu_data[-1]['value'] > 90:
            alert = DashboardAlert(
                id=f"cpu_high_{int(time.time())}",
                title="Alto uso de CPU",
                message=f"La CPU está al {cpu_data[-1]['value']:.1f}% de uso",
                severity="warning",
                timestamp=datetime.now(),
                source="system",
                metadata={'metric': 'cpu_usage', 'value': cpu_data[-1]['value']}
            )
            self.add_alert(alert)
        
        # Verificar tasa de errores
        error_data = self.data_streamer.get_stream_data('error_rate', 1)
        if error_data and error_data[-1]['value'] > 0.05:
            alert = DashboardAlert(
                id=f"error_rate_high_{int(time.time())}",
                title="Alta tasa de errores",
                message=f"La tasa de errores es del {error_data[-1]['value']:.1%}",
                severity="error",
                timestamp=datetime.now(),
                source="logs",
                metadata={'metric': 'error_rate', 'value': error_data[-1]['value']}
            )
            self.add_alert(alert)
    
    def add_alert(self, alert: DashboardAlert) -> None:
        """Añadir alerta al dashboard."""
        self.alerts.append(alert)
        self._save_alert(alert)
        
        # Notificar a clientes WebSocket
        self.socketio.emit('new_alert', alert.to_dict())
    
    def _save_alert(self, alert: DashboardAlert) -> None:
        """Guardar alerta en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO alerts (
                    id, title, message, severity, timestamp, acknowledged, source, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                alert.id,
                alert.title,
                alert.message,
                alert.severity,
                alert.timestamp.isoformat(),
                alert.acknowledged,
                alert.source,
                json.dumps(alert.metadata)
            ))
            conn.commit()
    
    def _save_widget(self, widget: WidgetConfig) -> None:
        """Guardar widget en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO widgets (
                    id, type, title, data_source, refresh_interval,
                    position_x, position_y, size_width, size_height, options, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                widget.id,
                widget.type.value,
                widget.title,
                widget.data_source,
                widget.refresh_interval,
                widget.position[0],
                widget.position[1],
                widget.size[0],
                widget.size[1],
                json.dumps(widget.options),
                datetime.now().isoformat()
            ))
            conn.commit()
    
    def _delete_widget(self, widget_id: str) -> None:
        """Eliminar widget de base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM widgets WHERE id = ?", (widget_id,))
            conn.commit()
    
    def start(self) -> None:
        """Iniciar el dashboard."""
        self.is_running = True
        if not self.update_thread.is_alive():
            self.update_thread.start()
        
        # Cargar widgets iniciales
        self._load_default_widgets()
        
        # Iniciar servidor Flask
        self._run_server()
    
    @staticmethod
    def _is_port_available(port: int, host: str = "127.0.0.1") -> bool:
        """Comprobar si un puerto TCP puede enlazarse."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
            return True
        except OSError:
            return False
    
    def _resolve_port(self) -> Optional[int]:
        """Elegir un puerto disponible, probando alternativas si hace falta."""
        candidates = [self.port] + [p for p in self.FALLBACK_PORTS if p != self.port]
        for port in candidates:
            if self._is_port_available(port, self.host):
                return port
        return None
    
    def _run_server(self) -> None:
        """Ejecutar el servidor Flask, tolerando fallos de bind."""
        port = self._resolve_port()
        if port is None:
            logging.warning(
                "Dashboard de logs no iniciado: no hay puertos disponibles "
                f"(intentados: {self.port}, {', '.join(str(p) for p in self.FALLBACK_PORTS)})"
            )
            self.is_running = False
            return
        
        if port != self.port:
            logging.warning(
                f"Puerto {self.port} no disponible para el dashboard de logs, "
                f"usando {port} en su lugar"
            )
        
        self.active_port = port
        
        try:
            self.socketio.run(self.app, host=self.host, port=port, debug=False)
        except OSError as e:
            # No debe tumbar el sistema principal (p.ej. WinError 10013).
            logging.error(f"No se pudo iniciar el dashboard de logs en {self.host}:{port}: {e}")
            self.is_running = False
        except Exception as e:
            logging.error(f"Error inesperado en el dashboard de logs: {e}")
            self.is_running = False
    
    def run(self) -> None:
        """Iniciar el dashboard (alias de start())."""
        self.start()
    
    def stop(self) -> None:
        """Detener el dashboard."""
        self.is_running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=5)
    
    def get_dashboard_url(self) -> Optional[str]:
        """Obtener la URL del dashboard (usa el puerto realmente asignado)."""
        if not self.is_running:
            return None
        host = "127.0.0.1" if self.host in ("localhost", "127.0.0.1", "0.0.0.0") else self.host
        return f"http://{host}:{self.active_port}"
    
    def _load_default_widgets(self) -> None:
        """Cargar widgets por defecto."""
        # Widget de CPU
        cpu_widget = WidgetConfig(
            id="cpu_usage",
            type=DashboardWidget.METRIC_CARD,
            title="Uso de CPU",
            data_source="cpu_usage",
            refresh_interval=10,
            position=(0, 0),
            size=(3, 2),
            options={'unit': '%', 'threshold': 90}
        )
        self.widgets[cpu_widget.id] = cpu_widget
        self._save_widget(cpu_widget)
        
        # Widget de memoria
        memory_widget = WidgetConfig(
            id="memory_usage",
            type=DashboardWidget.METRIC_CARD,
            title="Uso de Memoria",
            data_source="memory_usage",
            refresh_interval=10,
            position=(3, 0),
            size=(3, 2),
            options={'unit': '%', 'threshold': 85}
        )
        self.widgets[memory_widget.id] = memory_widget
        self._save_widget(memory_widget)
        
        # Widget de tasa de errores
        error_widget = WidgetConfig(
            id="error_rate",
            type=DashboardWidget.LINE_CHART,
            title="Tasa de Errores",
            data_source="error_rate",
            refresh_interval=30,
            position=(0, 2),
            size=(6, 4),
            options={'y_axis_range': [0, 0.1]}
        )
        self.widgets[error_widget.id] = error_widget
        self._save_widget(error_widget)
        
        # Widget de tiempo de respuesta
        response_widget = WidgetConfig(
            id="response_time",
            type=DashboardWidget.LINE_CHART,
            title="Tiempo de Respuesta",
            data_source="response_time",
            refresh_interval=30,
            position=(6, 2),
            size=(6, 4),
            options={'y_axis_range': [0, 3000]}
        )
        self.widgets[response_widget.id] = response_widget
        self._save_widget(response_widget)
        
        # Widget de distribución de logs
        distribution_widget = WidgetConfig(
            id="log_distribution",
            type=DashboardWidget.PIE_CHART,
            title="Distribución de Logs",
            data_source="log_categories",
            refresh_interval=60,
            position=(0, 6),
            size=(6, 4)
        )
        self.widgets[distribution_widget.id] = distribution_widget
        self._save_widget(distribution_widget)
        
        # Widget de tabla de logs recientes
        logs_widget = WidgetConfig(
            id="recent_logs",
            type=DashboardWidget.TABLE,
            title="Logs Recientes",
            data_source="recent_logs",
            refresh_interval=30,
            position=(6, 6),
            size=(6, 4)
        )
        self.widgets[logs_widget.id] = logs_widget
        self._save_widget(logs_widget)


# Instancia global del dashboard
log_dashboard = LogDashboard()