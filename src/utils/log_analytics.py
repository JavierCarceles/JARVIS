"""
Sistema avanzado de análisis de logs para Jarvis con capacidades de business intelligence.
"""

import json
import logging
import sqlite3
import threading
from collections import defaultdict, deque, Counter
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import io
import base64


class AnalyticsType(Enum):
    """Tipos de análisis."""
    SUMMARY = "summary"
    TREND = "trend"
    PATTERN = "pattern"
    CORRELATION = "correlation"
    ANOMALY = "anomaly"
    PERFORMANCE = "performance"
    ERROR_ANALYSIS = "error_analysis"
    BUSINESS_INTELLIGENCE = "business_intelligence"
    REAL_TIME = "real_time"


class TimeGranularity(Enum):
    """Granularidad temporal."""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass
class AnalyticsResult:
    """Resultado de análisis."""
    id: str
    type: AnalyticsType
    timestamp: datetime
    title: str
    summary: str
    data: Dict[str, Any]
    insights: List[str]
    recommendations: List[str]
    visualizations: Dict[str, str]  # Base64 encoded images
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['type'] = self.type.value
        return data


class LogAnalyticsEngine:
    """Motor de análisis de logs."""
    
    def __init__(self, db_path: str = "logs/analytics.db"):
        self.db_path = Path(db_path)
        self.analytics_results = []
        self.analytics_history = defaultdict(list)
        self.lock = threading.Lock()
        self.cache = {}
        self.cache_ttl = 300  # 5 minutos
        
        # Crear base de datos
        self._create_database()
        
    def _create_database(self) -> None:
        """Crear base de datos para análisis."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabla de resultados de análisis
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analytics_results (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    data TEXT,
                    insights TEXT,
                    recommendations TEXT,
                    visualizations TEXT,
                    metadata TEXT
                )
            ''')
            
            # Tabla de métricas agregadas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics_aggregated (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    granularity TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    value REAL NOT NULL,
                    tags TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
    
    def generate_summary_analytics(self, start_time: datetime = None, 
                                 end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis resumen."""
        cache_key = f"summary_{start_time}_{end_time}"
        
        # Verificar caché
        if cache_key in self.cache:
            cached_result, cached_time = self.cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl:
                return cached_result
        
        # Obtener datos de logs
        logs = self._query_logs(start_time, end_time)
        
        if not logs:
            return AnalyticsResult(
                id=f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=AnalyticsType.SUMMARY,
                timestamp=datetime.now(),
                title="Resumen de Sistema",
                summary="No hay datos disponibles para el período solicitado",
                data={},
                insights=[],
                recommendations=[],
                visualizations={},
                metadata={}
            )
        
        # Calcular métricas
        total_logs = len(logs)
        error_count = sum(1 for log in logs if log.get('level') in ['ERROR', 'CRITICAL'])
        warning_count = sum(1 for log in logs if log.get('level') == 'WARNING')
        
        # Métricas por categoría
        category_counts = Counter(log.get('category', 'unknown') for log in logs)
        
        # Métricas por módulo
        module_counts = Counter(log.get('module', 'unknown') for log in logs)
        
        # Periodo de análisis
        if logs:
            first_log = min(logs, key=lambda x: x['timestamp'])
            last_log = max(logs, key=lambda x: x['timestamp'])
            duration = (last_log['timestamp'] - first_log['timestamp']).total_seconds()
        else:
            duration = 0
        
        # Generar insights
        insights = []
        if error_count / total_logs > 0.1:
            insights.append("Alta tasa de errores detectada")
        if warning_count / total_logs > 0.2:
            insights.append("Alta tasa de warnings que requieren atención")
        if duration > 0:
            logs_per_second = total_logs / duration
            if logs_per_second > 10:
                insights.append("Alta actividad del sistema detectada")
        
        # Generar recomendaciones
        recommendations = []
        if error_count > 0:
            recommendations.append("Revisar logs de errores detallados")
        if warning_count > 0:
            recommendations.append("Investigar causas de los warnings")
        if len(category_counts) > 10:
            recommendations.append("Considerar optimización de categorías de logs")
        
        # Crear visualizaciones
        visualizations = self._create_summary_visualizations(
            category_counts, module_counts, error_count, total_logs
        )
        
        result = AnalyticsResult(
            id=f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            type=AnalyticsType.SUMMARY,
            timestamp=datetime.now(),
            title="Resumen del Sistema",
            summary=f"Análisis de {total_logs} logs en {duration/3600:.1f} horas",
            data={
                'total_logs': total_logs,
                'error_count': error_count,
                'warning_count': warning_count,
                'category_distribution': dict(category_counts),
                'module_distribution': dict(module_counts),
                'duration_seconds': duration,
                'logs_per_second': total_logs / duration if duration > 0 else 0
            },
            insights=insights,
            recommendations=recommendations,
            visualizations=visualizations,
            metadata={'period': {'start': start_time, 'end': end_time}}
        )
        
        # Almacenar en caché
        self.cache[cache_key] = (result, datetime.now())
        
        # Guardar en base de datos
        self._store_analytics_result(result)
        
        return result
    
    def generate_trend_analytics(self, start_time: datetime = None,
                               end_time: datetime = None,
                               granularity: TimeGranularity = TimeGranularity.HOUR) -> AnalyticsResult:
        """Generar análisis de tendencias."""
        logs = self._query_logs(start_time, end_time)
        
        if not logs:
            return AnalyticsResult(
                id=f"trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=AnalyticsType.TREND,
                timestamp=datetime.now(),
                title="Análisis de Tendencias",
                summary="No hay datos disponibles para el período solicitado",
                data={},
                insights=[],
                recommendations=[],
                visualizations={},
                metadata={}
            )
        
        # Agrupar por granularidad
        trend_data = self._group_logs_by_time(logs, granularity)
        
        # Calcular tendencias
        trend_analysis = self._analyze_trends(trend_data)
        
        # Detectar tendencias significativas
        significant_trends = self._detect_significant_trends(trend_analysis)
        
        # Generar insights
        insights = []
        for trend in significant_trends:
            insights.append(f"Tendencia {trend['direction']} detectada en {trend['metric']}")
        
        # Generar recomendaciones
        recommendations = []
        if any(trend['direction'] == 'increasing' and trend['metric'] == 'errors' 
               for trend in significant_trends):
            recommendations.append("Implementar medidas preventivas para el aumento de errores")
        if any(trend['direction'] == 'decreasing' and trend['metric'] == 'performance'
               for trend in significant_trends):
            recommendations.append("Mantener las optimizaciones actuales")
        
        # Crear visualizaciones
        visualizations = self._create_trend_visualizations(trend_data, significant_trends)
        
        result = AnalyticsResult(
            id=f"trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            type=AnalyticsType.TREND,
            timestamp=datetime.now(),
            title="Análisis de Tendencias",
            summary=f"Análisis de tendencias con granularidad {granularity.value}",
            data={
                'trend_data': trend_data,
                'trend_analysis': trend_analysis,
                'significant_trends': significant_trends
            },
            insights=insights,
            recommendations=recommendations,
            visualizations=visualizations,
            metadata={'granularity': granularity.value, 'period': {'start': start_time, 'end': end_time}}
        )
        
        self._store_analytics_result(result)
        return result
    
    def generate_pattern_analytics(self, start_time: datetime = None,
                                 end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis de patrones."""
        logs = self._query_logs(start_time, end_time)
        
        if not logs:
            return AnalyticsResult(
                id=f"pattern_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=AnalyticsType.PATTERN,
                timestamp=datetime.now(),
                title="Análisis de Patrones",
                summary="No hay datos disponibles para el período solicitado",
                data={},
                insights=[],
                recommendations=[],
                visualizations={},
                metadata={}
            )
        
        # Detectar patrones
        patterns = self._detect_patterns(logs)
        
        # Agrupar patrones por tipo
        pattern_types = defaultdict(list)
        for pattern in patterns:
            pattern_types[pattern['type']].append(pattern)
        
        # Generar insights
        insights = []
        for pattern_type, pattern_list in pattern_types.items():
            insights.append(f"{len(pattern_list)} patrones {pattern_type} detectados")
        
        # Generar recomendaciones
        recommendations = []
        if patterns:
            recommendations.append("Implementar medidas basadas en los patrones detectados")
        
        # Crear visualizaciones
        visualizations = self._create_pattern_visualizations(patterns)
        
        result = AnalyticsResult(
            id=f"pattern_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            type=AnalyticsType.PATTERN,
            timestamp=datetime.now(),
            title="Análisis de Patrones",
            summary=f"Se detectaron {len(patterns)} patrones en los logs",
            data={
                'patterns': patterns,
                'patterns_by_type': dict(pattern_types)
            },
            insights=insights,
            recommendations=recommendations,
            visualizations=visualizations,
            metadata={'period': {'start': start_time, 'end': end_time}}
        )
        
        self._store_analytics_result(result)
        return result
    
    def generate_correlation_analytics(self, start_time: datetime = None,
                                    end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis de correlaciones."""
        logs = self._query_logs(start_time, end_time)
        
        if not logs:
            return AnalyticsResult(
                id=f"correlation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=AnalyticsType.CORRELATION,
                timestamp=datetime.now(),
                title="Análisis de Correlaciones",
                summary="No hay datos disponibles para el período solicitado",
                data={},
                insights=[],
                recommendations=[],
                visualizations={},
                metadata={}
            )
        
        # Calcular correlaciones
        correlations = self._calculate_correlations(logs)
        
        # Filtrar correlaciones significativas
        significant_correlations = [c for c in correlations if c['correlation'] > 0.5]
        
        # Generar insights
        insights = []
        for corr in significant_correlations:
            insights.append(f"Correlación fuerte entre {corr['var1']} y {corr['var2']}")
        
        # Generar recomendaciones
        recommendations = []
        if significant_correlations:
            recommendations.append("Investigar las correlaciones detectadas")
        
        # Crear visualizaciones
        visualizations = self._create_correlation_visualizations(significant_correlations)
        
        result = AnalyticsResult(
            id=f"correlation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            type=AnalyticsType.CORRELATION,
            timestamp=datetime.now(),
            title="Análisis de Correlaciones",
            summary=f"Se detectaron {len(significant_correlations)} correlaciones significativas",
            data={
                'correlations': correlations,
                'significant_correlations': significant_correlations
            },
            insights=insights,
            recommendations=recommendations,
            visualizations=visualizations,
            metadata={'period': {'start': start_time, 'end': end_time}}
        )
        
        self._store_analytics_result(result)
        return result
    
    def generate_performance_analytics(self, start_time: datetime = None,
                                     end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis de rendimiento."""
        logs = self._query_logs(start_time, end_time)
        
        # Filtrar logs de rendimiento
        performance_logs = [log for log in logs if log.get('category') == 'performance']
        
        if not performance_logs:
            return AnalyticsResult(
                id=f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=AnalyticsType.PERFORMANCE,
                timestamp=datetime.now(),
                title="Análisis de Rendimiento",
                summary="No hay logs de rendimiento disponibles",
                data={},
                insights=[],
                recommendations=[],
                visualizations={},
                metadata={}
            )
        
        # Extraer métricas de rendimiento
        response_times = []
        success_rates = []
        
        for log in performance_logs:
            import re
            time_match = re.search(r'time=(\d+(?:\.\d+)?)', log.get('message', ''))
            if time_match:
                response_times.append(float(time_match.group(1)))
            
            success_match = re.search(r'success_rate=(\d+(?:\.\d+)?)', log.get('message', ''))
            if success_match:
                success_rates.append(float(success_match.group(1)))
        
        # Calcular estadísticas
        performance_stats = {
            'avg_response_time': np.mean(response_times) if response_times else 0,
            'max_response_time': np.max(response_times) if response_times else 0,
            'min_response_time': np.min(response_times) if response_times else 0,
            'avg_success_rate': np.mean(success_rates) if success_rates else 0,
            'total_performance_logs': len(performance_logs)
        }
        
        # Detectar problemas de rendimiento
        issues = []
        if performance_stats['avg_response_time'] > 1000:
            issues.append("Tiempo de respuesta promedio elevado")
        if performance_stats['avg_success_rate'] < 0.95:
            issues.append("Tasa de éxito baja")
        
        # Generar insights
        insights = []
        insights.append(f"Tiempo de respuesta promedio: {performance_stats['avg_response_time']:.2f}ms")
        insights.append(f"Tasa de éxito promedio: {performance_stats['avg_success_rate']:.2%}")
        
        # Generar recomendaciones
        recommendations = []
        if issues:
            recommendations.extend(issues)
            recommendations.append("Optimizar consultas de base de datos")
            recommendations.append("Implementar caché")
        
        # Crear visualizaciones
        visualizations = self._create_performance_visualizations(
            response_times, success_rates, performance_stats
        )
        
        result = AnalyticsResult(
            id=f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            type=AnalyticsType.PERFORMANCE,
            timestamp=datetime.now(),
            title="Análisis de Rendimiento",
            summary=f"Análisis de {len(performance_logs)} logs de rendimiento",
            data=performance_stats,
            insights=insights,
            recommendations=recommendations,
            visualizations=visualizations,
            metadata={'period': {'start': start_time, 'end': end_time}}
        )
        
        self._store_analytics_result(result)
        return result
    
    def _query_logs(self, start_time: datetime = None, 
                   end_time: datetime = None) -> List[Dict[str, Any]]:
        """Consultar logs desde la base de datos."""
        # Esta es una implementación simplificada
        # En un sistema real, se conectaría a la base de datos de logs
        return []
    
    def _group_logs_by_time(self, logs: List[Dict[str, Any]], 
                          granularity: TimeGranularity) -> Dict[str, List[Dict[str, Any]]]:
        """Agrupar logs por tiempo."""
        grouped = defaultdict(list)
        
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp'])
            
            if granularity == TimeGranularity.MINUTE:
                key = timestamp.strftime('%Y-%m-%d %H:%M')
            elif granularity == TimeGranularity.HOUR:
                key = timestamp.strftime('%Y-%m-%d %H:00')
            elif granularity == TimeGranularity.DAY:
                key = timestamp.strftime('%Y-%m-%d')
            elif granularity == TimeGranularity.WEEK:
                # Obtener lunes de la semana
                monday = timestamp - timedelta(days=timestamp.weekday())
                key = monday.strftime('%Y-%m-%d')
            elif granularity == TimeGranularity.MONTH:
                key = timestamp.strftime('%Y-%m')
            
            grouped[key].append(log)
        
        return dict(grouped)
    
    def _analyze_trends(self, trend_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Analizar tendencias."""
        analysis = {}
        
        for period, logs in trend_data.items():
            # Contar errores
            error_count = sum(1 for log in logs if log.get('level') in ['ERROR', 'CRITICAL'])
            
            # Contar logs totales
            total_count = len(logs)
            
            # Calcular tasa de error
            error_rate = error_count / total_count if total_count > 0 else 0
            
            analysis[period] = {
                'total_logs': total_count,
                'error_count': error_count,
                'error_rate': error_rate
            }
        
        return analysis
    
    def _detect_significant_trends(self, trend_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detectar tendencias significativas."""
        trends = []
        
        # Extraer valores por período
        periods = sorted(trend_analysis.keys())
        if len(periods) < 3:
            return trends
        
        # Analizar tendencias de errores
        error_rates = [trend_analysis[p]['error_rate'] for p in periods]
        
        # Simple trend detection
        if len(error_rates) >= 3:
            # Calcular pendiente simple
            n = len(error_rates)
            x = list(range(n))
            mean_x = sum(x) / n
            mean_y = sum(error_rates) / n
            
            covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, error_rates))
            variance = sum((xi - mean_x) ** 2 for xi in x)
            
            if variance > 0:
                slope = covariance / variance
                
                if slope > 0.01:  # Tendencia creciente
                    trends.append({
                        'metric': 'errors',
                        'direction': 'increasing',
                        'slope': slope,
                        'severity': 'high' if slope > 0.05 else 'medium'
                    })
                elif slope < -0.01:  # Tendencia decreciente
                    trends.append({
                        'metric': 'errors',
                        'direction': 'decreasing',
                        'slope': abs(slope),
                        'severity': 'positive'
                    })
        
        return trends
    
    def _detect_patterns(self, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detectar patrones en los logs."""
        patterns = []
        
        # Detección de patrones repetitivos
        message_patterns = defaultdict(int)
        for log in logs:
            message = log.get('message', '')
            # Simplificar mensaje para detección de patrones
            simplified = re.sub(r'\d+', 'NUM', message)
            message_patterns[simplified] += 1
        
        # Detectar mensajes repetitivos
        for message, count in message_patterns.items():
            if count >= 5:  # Al menos 5 ocurrencias
                patterns.append({
                    'type': 'repetitive_message',
                    'message': message,
                    'count': count,
                    'severity': 'medium'
                })
        
        return patterns
    
    def _calculate_correlations(self, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calcular correlaciones entre variables."""
        correlations = []
        
        # Correlación entre nivel de log y categoría
        level_category_matrix = defaultdict(lambda: defaultdict(int))
        
        for log in logs:
            level = log.get('level', 'INFO')
            category = log.get('category', 'system')
            level_category_matrix[level][category] += 1
        
        # Calcular correlación simple
        total_logs = len(logs)
        if total_logs > 0:
            for level, categories in level_category_matrix.items():
                for category, count in categories.items():
                    correlation = count / total_logs
                    if correlation > 0.1:  # Umbral de correlación
                        correlations.append({
                            'var1': f"level_{level}",
                            'var2': f"category_{category}",
                            'correlation': correlation,
                            'count': count
                        })
        
        return correlations
    
    def _create_summary_visualizations(self, category_counts: Counter, 
                                     module_counts: Counter, error_count: int, 
                                     total_logs: int) -> Dict[str, str]:
        """Crear visualizaciones para análisis resumen."""
        visualizations = {}
        
        # Gráfico de distribución de categorías
        try:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
            
            # Gráfico de pastel de categorías
            categories = list(category_counts.keys())[:10]  # Top 10
            counts = [category_counts[cat] for cat in categories]
            ax1.pie(counts, labels=categories, autopct='%1.1f%%')
            ax1.set_title('Distribución por Categoría')
            
            # Gráfico de barras de módulos
            modules = list(module_counts.keys())[:10]  # Top 10
            module_counts_list = [module_counts[mod] for mod in modules]
            ax2.bar(range(len(modules)), module_counts_list)
            ax2.set_xticks(range(len(modules)))
            ax2.set_xticklabels(modules, rotation=45, ha='right')
            ax2.set_title('Logs por Módulo')
            
            plt.tight_layout()
            
            # Convertir a base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            visualizations['summary_chart'] = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
        except Exception as e:
            logging.warning(f"Error creando visualización: {e}")
        
        return visualizations
    
    def _create_trend_visualizations(self, trend_data: Dict[str, Any], 
                                   significant_trends: List[Dict[str, Any]]) -> Dict[str, str]:
        """Crear visualizaciones para análisis de tendencias."""
        visualizations = {}
        
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Extraer datos de tendencia
            periods = sorted(trend_data.keys())
            error_rates = [trend_data[p]['error_rate'] for p in periods]
            
            # Gráfico de línea
            ax.plot(periods, error_rates, marker='o')
            ax.set_title('Tendencia de Tasa de Errores')
            ax.set_xlabel('Período')
            ax.set_ylabel('Tasa de Errores')
            ax.tick_params(axis='x', rotation=45)
            
            plt.tight_layout()
            
            # Convertir a base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            visualizations['trend_chart'] = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
        except Exception as e:
            logging.warning(f"Error creando visualización de tendencias: {e}")
        
        return visualizations
    
    def _create_pattern_visualizations(self, patterns: List[Dict[str, Any]]) -> Dict[str, str]:
        """Crear visualizaciones para análisis de patrones."""
        visualizations = {}
        
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Gráfico de barras de tipos de patrones
            pattern_types = defaultdict(int)
            for pattern in patterns:
                pattern_types[pattern['type']] += 1
            
            types = list(pattern_types.keys())
            counts = [pattern_types[ptype] for ptype in types]
            
            ax.bar(types, counts)
            ax.set_title('Distribución de Tipos de Patrones')
            ax.set_xlabel('Tipo de Patrón')
            ax.set_ylabel('Cantidad')
            ax.tick_params(axis='x', rotation=45)
            
            plt.tight_layout()
            
            # Convertir a base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            visualizations['pattern_chart'] = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
        except Exception as e:
            logging.warning(f"Error creando visualización de patrones: {e}")
        
        return visualizations
    
    def _create_correlation_visualizations(self, correlations: List[Dict[str, Any]]) -> Dict[str, str]:
        """Crear visualizaciones para análisis de correlaciones."""
        visualizations = {}
        
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Gráfico de dispersión de correlaciones
            vars1 = [c['var1'] for c in correlations]
            vars2 = [c['var2'] for c in correlations]
            corr_values = [c['correlation'] for c in correlations]
            
            # Crear matriz de correlación
            unique_vars = list(set(vars1 + vars2))
            n_vars = len(unique_vars)
            correlation_matrix = np.zeros((n_vars, n_vars))
            
            for corr in correlations:
                i = unique_vars.index(corr['var1'])
                j = unique_vars.index(corr['var2'])
                correlation_matrix[i, j] = corr['correlation']
                correlation_matrix[j, i] = corr['correlation']  # Simétrica
            
            # Heatmap
            im = ax.imshow(correlation_matrix, cmap='coolwarm', aspect='auto')
            ax.set_xticks(range(n_vars))
            ax.set_yticks(range(n_vars))
            ax.set_xticklabels(unique_vars, rotation=45, ha='right')
            ax.set_yticklabels(unique_vars)
            ax.set_title('Matriz de Correlación')
            
            # Añadir barra de color
            plt.colorbar(im, ax=ax)
            
            plt.tight_layout()
            
            # Convertir a base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            visualizations['correlation_heatmap'] = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
        except Exception as e:
            logging.warning(f"Error creando visualización de correlaciones: {e}")
        
        return visualizations
    
    def _create_performance_visualizations(self, response_times: List[float], 
                                         success_rates: List[float],
                                         performance_stats: Dict[str, Any]) -> Dict[str, str]:
        """Crear visualizaciones para análisis de rendimiento."""
        visualizations = {}
        
        try:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
            
            # Histograma de tiempos de respuesta
            if response_times:
                ax1.hist(response_times, bins=30, alpha=0.7)
                ax1.set_title('Distribución de Tiempos de Respuesta')
                ax1.set_xlabel('Tiempo (ms)')
                ax1.set_ylabel('Frecuencia')
            
            # Gráfico de línea de tiempos de respuesta
            if response_times:
                ax2.plot(response_times)
                ax2.set_title('Serie de Tiempos de Respuesta')
                ax2.set_xlabel('Muestra')
                ax2.set_ylabel('Tiempo (ms)')
            
            # Histograma de tasas de éxito
            if success_rates:
                ax3.hist(success_rates, bins=30, alpha=0.7, color='green')
                ax3.set_title('Distribución de Tasas de Éxito')
                ax3.set_xlabel('Tasa de Éxito')
                ax3.set_ylabel('Frecuencia')
            
            # Gráfico de dispersión
            if response_times and success_rates:
                ax4.scatter(response_times, success_rates, alpha=0.6)
                ax4.set_title('Relación Tiempo de Respuesta vs Tasa de Éxito')
                ax4.set_xlabel('Tiempo de Respuesta (ms)')
                ax4.set_ylabel('Tasa de Éxito')
            
            plt.tight_layout()
            
            # Convertir a base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            visualizations['performance_dashboard'] = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
        except Exception as e:
            logging.warning(f"Error creando visualización de rendimiento: {e}")
        
        return visualizations
    
    def _store_analytics_result(self, result: AnalyticsResult) -> None:
        """Almacenar resultado de análisis en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO analytics_results (
                    id, type, timestamp, title, summary, data, insights, 
                    recommendations, visualizations, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.id,
                result.type.value,
                result.timestamp.isoformat(),
                result.title,
                result.summary,
                json.dumps(result.data),
                json.dumps(result.insights),
                json.dumps(result.recommendations),
                json.dumps(result.visualizations),
                json.dumps(result.metadata)
            ))
            conn.commit()
    
    def get_analytics_history(self, analytics_type: AnalyticsType = None, 
                            limit: int = 50) -> List[AnalyticsResult]:
        """Obtener historial de análisis."""
        if analytics_type:
            return self.analytics_history[analytics_type.value][:limit]
        else:
            # Devolver todos los análisis ordenados por timestamp
            all_analytics = []
            for type_history in self.analytics_history.values():
                all_analytics.extend(type_history)
            return sorted(all_analytics, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def export_analytics(self, start_time: datetime = None, 
                        end_time: datetime = None, format: str = 'json') -> str:
        """Exportar resultados de análisis."""
        # Consultar resultados de base de datos
        query = "SELECT * FROM analytics_results WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT 1000"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                result = {
                    'id': row[0],
                    'type': row[1],
                    'timestamp': row[2],
                    'title': row[3],
                    'summary': row[4],
                    'data': json.loads(row[5]) if row[5] else {},
                    'insights': json.loads(row[6]) if row[6] else [],
                    'recommendations': json.loads(row[7]) if row[7] else [],
                    'visualizations': json.loads(row[8]) if row[8] else {},
                    'metadata': json.loads(row[9]) if row[9] else {}
                }
                results.append(result)
            
            if format == 'json':
                return json.dumps(results, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Formato no soportado: {format}")


class LogAnalytics:
    """Wrapper para LogAnalyticsEngine que proporciona la interfaz esperada."""
    
    def __init__(self, db_path: str = "logs/analytics.db"):
        self.engine = LogAnalyticsEngine(db_path)
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Obtener resumen de análisis."""
        # Generar análisis resumen
        summary = self.engine.generate_summary_analytics()
        return summary.to_dict()
    
    def generate_summary_analytics(self, start_time: datetime = None, end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis resumen."""
        return self.engine.generate_summary_analytics(start_time, end_time)
    
    def generate_trend_analytics(self, start_time: datetime = None, end_time: datetime = None, 
                                 granularity: TimeGranularity = TimeGranularity.HOUR) -> AnalyticsResult:
        """Generar análisis de tendencias."""
        return self.engine.generate_trend_analytics(start_time, end_time, granularity)
    
    def generate_pattern_analytics(self, start_time: datetime = None, end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis de patrones."""
        return self.engine.generate_pattern_analytics(start_time, end_time)
    
    def generate_correlation_analytics(self, start_time: datetime = None, end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis de correlaciones."""
        return self.engine.generate_correlation_analytics(start_time, end_time)
    
    def generate_performance_analytics(self, start_time: datetime = None, end_time: datetime = None) -> AnalyticsResult:
        """Generar análisis de rendimiento."""
        return self.engine.generate_performance_analytics(start_time, end_time)
    
    def get_analytics_history(self, analytics_type: AnalyticsType = None, limit: int = 50) -> List[AnalyticsResult]:
        """Obtener historial de análisis."""
        return self.engine.get_analytics_history(analytics_type, limit)
    
    def export_analytics(self, start_time: datetime = None, end_time: datetime = None, format: str = 'json') -> str:
        """Exportar resultados de análisis."""
        return self.engine.export_analytics(start_time, end_time, format)


# Instancia global del motor de análisis
log_analytics = LogAnalyticsEngine()
log_analytics_wrapper = LogAnalytics()