"""
Analizador avanzado de patrones para Jarvis con machine learning y detección de anomalías.
"""

import json
import logging
import re
import sqlite3
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import pickle
import os


class PatternType(Enum):
    """Tipos de patrones detectables."""
    ERROR_SPIKE = "error_spike"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    ANOMALY = "anomaly"
    TREND = "trend"
    CYCLE = "cycle"
    CORRELATION = "correlation"
    SEASONAL = "seasonal"
    BURST = "burst"
    CHANGEPONT = "changepoint"


class PatternSeverity(Enum):
    """Severidad de patrones."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Pattern:
    """Estructura de patrón detectado."""
    id: str
    type: PatternType
    severity: PatternSeverity
    description: str
    timestamp: datetime
    confidence: float
    data: Dict[str, Any]
    affected_components: List[str]
    suggested_actions: List[str]
    is_active: bool = True
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['type'] = self.type.value
        data['severity'] = self.severity.value
        return data


class TimeSeriesAnalyzer:
    """Analizador de series temporales para detección de patrones."""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.time_series = defaultdict(lambda: deque(maxlen=window_size))
        self.scaler = StandardScaler()
        self.isolation_forest = IsolationForest(contamination=0.1, random_state=42)
        self.is_trained = False
        
    def add_data_point(self, metric_name: str, value: float, timestamp: datetime = None) -> None:
        """Añadir punto de datos a la serie temporal."""
        if timestamp is None:
            timestamp = datetime.now()
            
        self.time_series[metric_name].append({
            'timestamp': timestamp,
            'value': value
        })
        
        # Entrenar modelo si tenemos suficientes datos
        if len(self.time_series[metric_name]) >= 100 and not self.is_trained:
            self._train_model()
    
    def _train_model(self) -> None:
        """Entrenar modelo de detección de anomalías."""
        try:
            # Preparar datos de entrenamiento
            training_data = []
            for metric_name, series in self.time_series.items():
                if len(series) >= 50:
                    values = [point['value'] for point in series]
                    training_data.extend(values)
            
            if len(training_data) >= 100:
                training_array = np.array(training_data).reshape(-1, 1)
                self.scaler.fit(training_array)
                normalized_data = self.scaler.transform(training_array)
                self.isolation_forest.fit(normalized_data)
                self.is_trained = True
        except Exception as e:
            logging.warning(f"Error entrenando modelo de detección de anomalías: {e}")
    
    def detect_anomalies(self, metric_name: str, window_size: int = 100) -> List[Dict[str, Any]]:
        """Detectar anomalías en una serie temporal."""
        if metric_name not in self.time_series or len(self.time_series[metric_name]) < window_size:
            return []
        
        series = list(self.time_series[metric_name])[-window_size:]
        values = [point['value'] for point in series]
        
        anomalies = []
        
        # Detección estadística simple
        if len(values) >= 10:
            mean = np.mean(values)
            std = np.std(values)
            
            for i, value in enumerate(values):
                z_score = abs(value - mean) / std if std > 0 else 0
                if z_score > 3:  # Umbral de 3 desviaciones
                    anomalies.append({
                        'type': 'statistical_anomaly',
                        'index': i,
                        'value': value,
                        'z_score': z_score,
                        'severity': 'high' if z_score > 5 else 'medium'
                    })
        
        # Detección con ML si está entrenado
        if self.is_trained:
            try:
                recent_values = np.array(values[-50:]).reshape(-1, 1)
                normalized_values = self.scaler.transform(recent_values)
                anomaly_scores = self.isolation_forest.decision_function(normalized_values)
                
                for i, score in enumerate(anomaly_scores):
                    if score < -0.5:  # Umbral para anomalías
                        anomalies.append({
                            'type': 'ml_anomaly',
                            'index': len(values) - 50 + i,
                            'value': values[len(values) - 50 + i],
                            'anomaly_score': score,
                            'severity': 'high' if score < -0.8 else 'medium'
                        })
            except Exception as e:
                logging.warning(f"Error en detección ML: {e}")
        
        return anomalies


class PatternDetector:
    """Detector de patrones con múltiples algoritmos."""
    
    def __init__(self):
        self.time_series_analyzer = TimeSeriesAnalyzer()
        self.patterns = []
        self.pattern_history = defaultdict(list)
        self.lock = threading.Lock()
        
    def analyze_logs(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Analizar logs y detectar patrones."""
        detected_patterns = []
        
        with self.lock:
            # Detección de picos de errores
            error_spike_patterns = self._detect_error_spikes(logs)
            detected_patterns.extend(error_spike_patterns)
            
            # Detección de degradación de rendimiento
            performance_patterns = self._detect_performance_degradation(logs)
            detected_patterns.extend(performance_patterns)
            
            # Detección de anomalías
            anomaly_patterns = self._detect_anomalies(logs)
            detected_patterns.extend(anomaly_patterns)
            
            # Detección de tendencias
            trend_patterns = self._detect_trends(logs)
            detected_patterns.extend(trend_patterns)
            
            # Detección de ciclos
            cycle_patterns = self._detect_cycles(logs)
            detected_patterns.extend(cycle_patterns)
            
            # Detección de correlaciones
            correlation_patterns = self._detect_correlations(logs)
            detected_patterns.extend(correlation_patterns)
            
            # Detección de bursts
            burst_patterns = self._detect_bursts(logs)
            detected_patterns.extend(burst_patterns)
            
            # Almacenar patrones detectados
            for pattern in detected_patterns:
                self.patterns.append(pattern)
                self.pattern_history[pattern.type.value].append(pattern)
        
        return detected_patterns
    
    def _detect_error_spikes(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar picos de errores."""
        patterns = []
        
        # Agrupar logs por ventana de tiempo
        time_windows = defaultdict(list)
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            window_key = timestamp.replace(minute=0, second=0, microsecond=0)
            time_windows[window_key].append(log)
        
        # Analizar cada ventana
        for window_time, window_logs in time_windows.items():
            error_count = sum(1 for log in window_logs 
                           if log.get('level') in ['ERROR', 'CRITICAL'])
            total_count = len(window_logs)
            
            if total_count > 0:
                error_rate = error_count / total_count
                
                # Detectar picos
                if error_rate > 0.3:  # 30% de errores
                    severity = PatternSeverity.CRITICAL if error_rate > 0.5 else PatternSeverity.HIGH
                    
                    pattern = Pattern(
                        id=f"error_spike_{window_time.strftime('%Y%m%d_%H%M%S')}",
                        type=PatternType.ERROR_SPIKE,
                        severity=severity,
                        description=f"Pico de errores detectado: {error_rate:.1%} ({error_count}/{total_count})",
                        timestamp=window_time,
                        confidence=min(error_rate * 2, 1.0),
                        data={
                            'error_count': error_count,
                            'total_count': total_count,
                            'error_rate': error_rate,
                            'window_size': total_count
                        },
                        affected_components=list(set(log.get('module', 'unknown') for log in window_logs)),
                        suggested_actions=[
                            "Revisar logs detallados del período",
                            "Verificar estado de servicios afectados",
                            "Considerar reinicio de servicios críticos"
                        ]
                    )
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_performance_degradation(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar degradación de rendimiento."""
        patterns = []
        
        # Extraer métricas de rendimiento
        performance_metrics = defaultdict(list)
        for log in logs:
            if log.get('category') == 'performance':
                # Extraer tiempo de respuesta
                time_match = re.search(r'time=(\d+(?:\.\d+)?)', log.get('message', ''))
                if time_match:
                    response_time = float(time_match.group(1))
                    performance_metrics[log.get('module', 'unknown')].append(response_time)
        
        # Analizar degradación
        for module, times in performance_metrics.items():
            if len(times) >= 10:
                # Calcular tendencia
                recent_avg = sum(times[-10:]) / 10
                older_avg = sum(times[-20:-10]) / 10 if len(times) >= 20 else recent_avg
                
                if recent_avg > older_avg * 1.5:  # 50% de aumento
                    degradation_percent = ((recent_avg - older_avg) / older_avg) * 100
                    
                    pattern = Pattern(
                        id=f"performance_degradation_{module}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        type=PatternType.PERFORMANCE_DEGRADATION,
                        severity=PatternSeverity.HIGH if degradation_percent > 100 else PatternSeverity.MEDIUM,
                        description=f"Degradación de rendimiento en {module}: {degradation_percent:.1f}% aumento",
                        timestamp=datetime.now(),
                        confidence=min(degradation_percent / 200, 1.0),
                        data={
                            'module': module,
                            'recent_avg': recent_avg,
                            'older_avg': older_avg,
                            'degradation_percent': degradation_percent,
                            'sample_size': len(times)
                        },
                        affected_components=[module],
                        suggested_actions=[
                            "Optimizar consultas de base de datos",
                            "Revisar código de aplicación",
                            "Aumentar recursos del sistema",
                            "Implementar caché"
                        ]
                    )
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_anomalies(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar anomalías usando series temporales."""
        patterns = []
        
        # Agregar datos al analizador de series temporales
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            
            # Extraer métricas numéricas
            if log.get('category') == 'performance':
                time_match = re.search(r'time=(\d+(?:\.\d+)?)', log.get('message', ''))
                if time_match:
                    value = float(time_match.group(1))
                    module = log.get('module', 'unknown')
                    self.time_series_analyzer.add_data_point(f"{module}_response_time", value, timestamp)
        
        # Detectar anomalías en cada métrica
        for metric_name, series in self.time_series_analyzer.time_series.items():
            if len(series) >= 50:
                anomalies = self.time_series_analyzer.detect_anomalies(metric_name)
                
                for anomaly in anomalies:
                    pattern = Pattern(
                        id=f"anomaly_{metric_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        type=PatternType.ANOMALY,
                        severity=PatternSeverity.HIGH if anomaly.get('severity') == 'high' else PatternSeverity.MEDIUM,
                        description=f"Anomalía detectada en {metric_name}: valor {anomaly['value']}",
                        timestamp=datetime.now(),
                        confidence=0.8,
                        data={
                            'metric': metric_name,
                            'anomaly_value': anomaly['value'],
                            'anomaly_type': anomaly['type'],
                            'severity': anomaly['severity']
                        },
                        affected_components=[metric_name.split('_')[0]],
                        suggested_actions=[
                            "Investigar causa de la anomalía",
                            "Verificar configuración del sistema",
                            "Revisar logs del período afectado"
                        ]
                    )
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_trends(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar tendencias en los logs."""
        patterns = []
        
        # Agrupar por hora
        hourly_counts = defaultdict(lambda: defaultdict(int))
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            hour_key = timestamp.replace(minute=0, second=0, microsecond=0)
            hourly_counts[hour_key][log.get('level', 'INFO')] += 1
        
        # Analizar tendencias
        hours = sorted(hourly_counts.keys())
        if len(hours) >= 6:  # Al menos 6 horas de datos
            # Calcular tendencia de errores
            error_counts = [hourly_counts[hour].get('ERROR', 0) + hourly_counts[hour].get('CRITICAL', 0) 
                          for hour in hours]
            
            # Simple linear regression for trend detection
            n = len(error_counts)
            x = list(range(n))
            mean_x = sum(x) / n
            mean_y = sum(error_counts) / n
            
            covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, error_counts))
            variance = sum((xi - mean_x) ** 2 for xi in x)
            
            if variance > 0:
                slope = covariance / variance
                
                if slope > 2:  # Tendencia creciente fuerte
                    pattern = Pattern(
                        id=f"trend_increasing_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        type=PatternType.TREND,
                        severity=PatternSeverity.MEDIUM,
                        description=f"Tendencia creciente de errores detectada (pendiente: {slope:.2f})",
                        timestamp=datetime.now(),
                        confidence=min(slope / 5, 1.0),
                        data={
                            'slope': slope,
                            'error_counts': error_counts,
                            'period_hours': n
                        },
                        affected_components=['system'],
                        suggested_actions=[
                            "Revisar causas del aumento de errores",
                            "Implementar monitoreo proactivo",
                            "Preparar plan de contingencia"
                        ]
                    )
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_cycles(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar patrones cíclicos."""
        patterns = []
        
        # Agrupar por minuto
        minute_counts = defaultdict(lambda: defaultdict(int))
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            minute_key = timestamp.replace(second=0, microsecond=0)
            minute_counts[minute_key][log.get('category', 'system')] += 1
        
        # Buscar ciclos en las últimas horas
        recent_minutes = sorted(minute_counts.keys())[-120:]  # Últimas 2 horas
        
        if len(recent_minutes) >= 60:
            # Contar frecuencias por categoría
            category_frequencies = defaultdict(list)
            for minute in recent_minutes:
                for category, count in minute_counts[minute].items():
                    category_frequencies[category].append(count)
            
            # Detectar ciclos usando FFT simple
            for category, frequencies in category_frequencies.items():
                if len(frequencies) >= 30:
                    # Detectar periodicidad
                    cycle_detected = self._detect_periodicity(frequencies)
                    
                    if cycle_detected:
                        pattern = Pattern(
                            id=f"cycle_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            type=PatternType.CYCLE,
                            severity=PatternSeverity.LOW,
                            description=f"Patón cíclico detectado en {category}",
                            timestamp=datetime.now(),
                            confidence=0.7,
                            data={
                                'category': category,
                                'cycle_info': cycle_detected,
                                'sample_size': len(frequencies)
                            },
                            affected_components=[category],
                            suggested_actions=[
                                "Analizar causas del ciclo detectado",
                                "Optimizar procesos periódicos",
                                "Considerar programación de mantenimiento"
                            ]
                        )
                        patterns.append(pattern)
        
        return patterns
    
    def _detect_periodicity(self, data: List[int]) -> Optional[Dict[str, Any]]:
        """Detectar periodicidad en datos usando métodos simples."""
        if len(data) < 30:
            return None
        
        # Buscar periodicidad buscando repetición de patrones
        for period in range(5, min(20, len(data) // 3)):
            pattern_matches = 0
            for i in range(period, len(data) - period):
                if abs(data[i] - data[i - period]) <= 2:  # Tolerancia de 2 unidades
                    pattern_matches += 1
            
            if pattern_matches >= period * 2:  # Buen patrón de coincidencias
                return {
                    'period': period,
                    'confidence': pattern_matches / (len(data) - period),
                    'match_count': pattern_matches
                }
        
        return None
    
    def _detect_correlations(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar correlaciones entre diferentes tipos de logs."""
        patterns = []
        
        # Contar co-ocurrencias
        co_occurrences = defaultdict(lambda: defaultdict(int))
        time_windows = defaultdict(list)
        
        # Agrupar logs en ventanas de 5 minutos
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            window_key = timestamp.replace(minute=(timestamp.minute // 5) * 5, second=0, microsecond=0)
            time_windows[window_key].append(log)
        
        # Analizar co-ocurrencias
        for window_logs in time_windows.values():
            categories_in_window = set()
            for log in window_logs:
                category = log.get('category', 'system')
                categories_in_window.add(category)
            
            # Contar pares de categorías
            categories_list = list(categories_in_window)
            for i in range(len(categories_list)):
                for j in range(i + 1, len(categories_list)):
                    cat1, cat2 = categories_list[i], categories_list[j]
                    co_occurrences[cat1][cat2] += 1
        
        # Detectar correlaciones fuertes
        for cat1, cat2_counts in co_occurrences.items():
            total_co_occurrences = sum(cat2_counts.values())
            for cat2, count in cat2_counts.items():
                if count >= 5 and count / total_co_occurrences > 0.7:  # Alta correlación
                    pattern = Pattern(
                        id=f"correlation_{cat1}_{cat2}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        type=PatternType.CORRELATION,
                        severity=PatternSeverity.MEDIUM,
                        description=f"Correlación fuerte detectada: {cat1} <-> {cat2}",
                        timestamp=datetime.now(),
                        confidence=count / total_co_occurrences,
                        data={
                            'category1': cat1,
                            'category2': cat2,
                            'co_occurrence_count': count,
                            'total_occurrences': total_co_occurrences
                        },
                        affected_components=[cat1, cat2],
                        suggested_actions=[
                            "Investigar relación entre categorías",
                            "Optimizar procesos relacionados",
                            "Monitorear conjuntamente ambas categorías"
                        ]
                    )
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_bursts(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Detectar bursts de actividad."""
        patterns = []
        
        # Agrupar por segundos
        second_counts = defaultdict(int)
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            second_key = timestamp.replace(microsecond=0)
            second_counts[second_key] += 1
        
        # Detectar bursts
        for second_key, count in second_counts.items():
            if count > 10:  # Más de 10 logs por segundo
                pattern = Pattern(
                    id=f"burst_{second_key.strftime('%Y%m%d_%H%M%S')}",
                    type=PatternType.BURST,
                    severity=PatternSeverity.HIGH if count > 50 else PatternSeverity.MEDIUM,
                    description=f"Burst de actividad detectado: {count} logs/segundo",
                    timestamp=second_key,
                    confidence=min(count / 100, 1.0),
                    data={
                        'log_count': count,
                        'timestamp': second_key.isoformat()
                    },
                    affected_components=['system'],
                    suggested_actions=[
                        "Investigar causa del burst",
                        "Verificar si es actividad normal o ataque",
                        "Considerar límites de tasa de requests"
                    ]
                )
                patterns.append(pattern)
        
        return patterns
    
    def get_patterns_by_type(self, pattern_type: PatternType, 
                           limit: int = 50) -> List[Pattern]:
        """Obtener patrones por tipo."""
        return [p for p in self.patterns 
                if p.type == pattern_type and p.is_active][:limit]
    
    def get_active_patterns(self) -> List[Pattern]:
        """Obtener patrones activos."""
        return [p for p in self.patterns if p.is_active and not p.acknowledged]
    
    def acknowledge_pattern(self, pattern_id: str) -> None:
        """Marcar patrón como reconocido."""
        for pattern in self.patterns:
            if pattern.id == pattern_id:
                pattern.acknowledged = True
                break
    
    def get_pattern_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de patrones."""
        stats = {
            'total_patterns': len(self.patterns),
            'active_patterns': len(self.get_active_patterns()),
            'patterns_by_type': defaultdict(int),
            'patterns_by_severity': defaultdict(int),
            'recent_patterns': len([p for p in self.patterns 
                                 if (datetime.now() - p.timestamp).total_seconds() < 3600])
        }
        
        for pattern in self.patterns:
            stats['patterns_by_type'][pattern.type.value] += 1
            stats['patterns_by_severity'][pattern.severity.value] += 1
        
        return dict(stats)


class PatternAnalyzer:
    """Wrapper para PatternDetector que proporciona la interfaz esperada."""
    
    def __init__(self):
        self.detector = PatternDetector()
    
    def get_pattern_analysis(self) -> Dict[str, Any]:
        """Obtener análisis completo de patrones."""
        stats = self.detector.get_pattern_statistics()
        active = self.detector.get_active_patterns()
        
        return {
            'statistics': stats,
            'active_patterns': [p.to_dict() for p in active],
            'total_patterns': stats.get('total_patterns', 0),
            'active_count': len(active),
            'patterns_by_type': stats.get('patterns_by_type', {}),
            'patterns_by_severity': stats.get('patterns_by_severity', {}),
            'recent_count': stats.get('recent_patterns', 0)
        }
    
    def analyze_logs(self, logs: List[Dict[str, Any]]) -> List[Pattern]:
        """Analizar logs y detectar patrones."""
        return self.detector.analyze_logs(logs)
    
    def get_patterns_by_type(self, pattern_type: PatternType, limit: int = 50) -> List[Pattern]:
        """Obtener patrones por tipo."""
        return self.detector.get_patterns_by_type(pattern_type, limit)
    
    def get_active_patterns(self) -> List[Pattern]:
        """Obtener patrones activos."""
        return self.detector.get_active_patterns()
    
    def acknowledge_pattern(self, pattern_id: str) -> None:
        """Marcar patrón como reconocido."""
        self.detector.acknowledge_pattern(pattern_id)
    
    def get_pattern_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de patrones."""
        return self.detector.get_pattern_statistics()


# Instancia global del analizador de patrones
pattern_detector = PatternDetector()
pattern_analyzer = PatternAnalyzer()