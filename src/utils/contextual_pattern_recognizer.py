"""
Reconocedor de patrones contextuales para JARVIS.
Integra contexto con detección de patrones sin duplicar funcionalidad existente.
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np

from .pattern_analyzer import PatternAnalyzer, PatternType, PatternSeverity, Pattern
from .contextual_adaptation_engine import ContextSnapshot, ContextualFactor


class ContextualPatternType(Enum):
    """Tipos de patrones contextuales específicos."""
    CONTEXTUAL_ANOMALY = "contextual_anomaly"
    CONTEXTUAL_TREND = "contextual_trend"
    CONTEXTUAL_CORRELATION = "contextual_correlation"
    CONTEXTUAL_SEASONAL = "contextual_seasonal"
    CONTEXTUAL_BURST = "contextual_burst"
    CONTEXTUAL_CHANGEPOINT = "contextual_changepoint"


@dataclass
class ContextualPattern:
    """Estructura de patrón contextual detectado."""
    id: str
    type: ContextualPatternType
    severity: PatternSeverity
    description: str
    timestamp: datetime
    confidence: float
    context_snapshot: ContextSnapshot
    pattern_data: Dict[str, Any]
    affected_components: List[str]
    suggested_actions: List[str]
    compatibility_score: float = 0.0


class ContextualPatternRecognizer:
    """Reconocedor de patrones relacionados con contexto y conectarlos con PatternAnalyzer."""
    
    def __init__(self, pattern_analyzer: Optional[PatternAnalyzer] = None):
        self.pattern_analyzer = pattern_analyzer or PatternAnalyzer()
        self.contextual_patterns = []
        self.pattern_history = []
        self.compatibility_thresholds = {
            'high': 0.8,
            'medium': 0.6,
            'low': 0.4
        }
        
    def add_contextual_pattern(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Añadir snapshot de contexto y detectar patrones contextuales."""
        # Detectar patrones contextuales
        pattern = self._detect_contextual_pattern(snapshot)
        if pattern:
            self.contextual_patterns.append(pattern)
            self.pattern_history.append({
                'timestamp': datetime.now(),
                'pattern_id': pattern.id,
                'compatibility_score': pattern.compatibility_score
            })
            return pattern
        return None
    
    def _detect_contextual_pattern(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar patrones contextuales específicos."""
        
        # 1. Detectar anomalías contextuales
        anomaly_pattern = self._detect_contextual_anomaly(snapshot)
        if anomaly_pattern:
            return anomaly_pattern
            
        # 2. Detectar tendencias contextuales
        trend_pattern = self._detect_contextual_trend(snapshot)
        if trend_pattern:
            return trend_pattern
            
        # 3. Detectar correlaciones contextuales
        correlation_pattern = self._detect_contextual_correlation(snapshot)
        if correlation_pattern:
            return correlation_pattern
            
        # 4. Detectar patrones estacionales
        seasonal_pattern = self._detect_contextual_seasonal(snapshot)
        if seasonal_pattern:
            return seasonal_pattern
            
        # 5. Detectar patrones de burst
        burst_pattern = self._detect_contextual_burst(snapshot)
        if burst_pattern:
            return burst_pattern
            
        # 6. Detectar puntos de cambio
        changepoint_pattern = self._detect_contextual_changepoint(snapshot)
        if changepoint_pattern:
            return changepoint_pattern
            
        return None
    
    def _detect_contextual_anomaly(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar anomalías contextuales."""
        factors = snapshot.contextual_factors
        
        # Definir umbrales para anomalías
        anomaly_thresholds = {
            ContextualFactor.SYSTEM_RESOURCES: 0.9,
            ContextualFactor.USER_BEHAVIOR: 0.9,
            ContextualFactor.NETWORK_CONDITIONS: 0.8,
            ContextualFactor.ERROR_RATES: 0.15
        }
        
        anomalies = []
        for factor, threshold in anomaly_thresholds.items():
            if factor in factors and factors[factor] >= threshold:
                anomalies.append({
                    'factor': factor.name,
                    'value': factors[factor],
                    'threshold': threshold
                })
        
        if anomalies:
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_anomaly_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_ANOMALY,
                severity=PatternSeverity.HIGH if len(anomalies) > 2 else PatternSeverity.MEDIUM,
                description=f"Anomalía contextual detectada: {len(anomalies)} factores fuera de rango",
                timestamp=datetime.now(),
                confidence=min(0.9, 0.5 + len(anomalies) * 0.1),
                context_snapshot=snapshot,
                pattern_data={'anomalies': anomalies},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_anomaly_actions(anomalies),
                compatibility_score=compatibility
            )
        
        return None
    
    def _detect_contextual_trend(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar tendencias contextuales."""
        # Aquí se analizarían las tendencias históricas de los factores contextuales
        # Por simplicidad, se detecta una tendencia basada en valores actuales
        
        factors = snapshot.contextual_factors
        high_values = sum(1 for v in factors.values() if v > 0.7)
        
        if high_values >= 3:  # Al menos 3 factores con valores altos
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_TREND,
                severity=PatternSeverity.MEDIUM,
                description=f"Tendencia de alto consumo detectada: {high_values} factores elevados",
                timestamp=datetime.now(),
                confidence=0.7,
                context_snapshot=snapshot,
                pattern_data={'high_factors': high_values},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_trend_actions(),
                compatibility_score=compatibility
            )
        
        return None
    
    def _detect_contextual_correlation(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar correlaciones contextuales."""
        factors = snapshot.contextual_factors
        factor_names = list(factors.keys())
        
        # Detectar correlaciones fuertes entre factores
        correlations = []
        for i, factor1 in enumerate(factor_names):
            for factor2 in factor_names[i+1:]:
                value1 = factors[factor1]
                value2 = factors[factor2]
                
                # Correlación fuerte si ambos valores son altos o ambos son bajos
                if (value1 > 0.8 and value2 > 0.8) or (value1 < 0.15 and value2 < 0.15):
                    correlations.append({
                        'factor1': factor1.name,
                        'factor2': factor2.name,
                        'value1': value1,
                        'value2': value2,
                        'type': 'high_high' if value1 > 0.8 else 'low_low'
                    })
        
        if correlations:
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_correlation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_CORRELATION,
                severity=PatternSeverity.MEDIUM,
                description=f"Correlación contextual detectada: {len(correlations)} pares correlacionados",
                timestamp=datetime.now(),
                confidence=0.8,
                context_snapshot=snapshot,
                pattern_data={'correlations': correlations},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_correlation_actions(correlations),
                compatibility_score=compatibility
            )
        
        return None
    
    def _detect_contextual_trend(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar tendencias contextuales."""
        factors = snapshot.contextual_factors
        
        # Detectar tendencias: valores consistentemente altos o bajos
        trend_factors = []
        
        for factor, value in factors.items():
            if value > 0.8:  # Tendencia alta
                trend_factors.append({
                    'factor': factor.name,
                    'value': value,
                    'trend_type': 'high'
                })
            elif value < 0.1:  # Tendencia baja (más estricto)
                trend_factors.append({
                    'factor': factor.name,
                    'value': value,
                    'trend_type': 'low'
                })
        
        if trend_factors:
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_TREND,
                severity=PatternSeverity.MEDIUM,
                description=f"Tendencia contextual detectada: {len(trend_factors)} factores en tendencia",
                timestamp=datetime.now(),
                confidence=0.7,
                context_snapshot=snapshot,
                pattern_data={'trend_factors': trend_factors},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_trend_actions(trend_factors),
                compatibility_score=compatibility
            )
        
        return None
    
    def _detect_contextual_seasonal(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar patrones estacionales contextuales."""
        # Basado en la hora del día del snapshot
        current_hour = snapshot.timestamp.hour
        
        # Patrones típicos por hora
        seasonal_patterns = {
            'morning_peak': (6, 10),  # Mañana temprana
            'afternoon_peak': (14, 18),  # Tarde
            'evening_peak': (19, 23),  # Noche
            'night_low': (0, 5)  # Madrugada
        }
        
        detected_patterns = []
        for pattern_name, (start_hour, end_hour) in seasonal_patterns.items():
            if start_hour <= current_hour <= end_hour:
                detected_patterns.append(pattern_name)
        
        if detected_patterns:
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_seasonal_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_SEASONAL,
                severity=PatternSeverity.LOW,
                description=f"Patrón estacional detectado: {', '.join(detected_patterns)}",
                timestamp=datetime.now(),
                confidence=0.6,
                context_snapshot=snapshot,
                pattern_data={'seasonal_patterns': detected_patterns, 'current_hour': current_hour},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_seasonal_actions(detected_patterns),
                compatibility_score=compatibility
            )
        
        return None
    
    def _detect_contextual_burst(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar patrones de burst contextuales."""
        factors = snapshot.contextual_factors
        
        # Detectar burst: cambio rápido en valores
        burst_threshold = 0.4
        burst_factors = []
        
        for factor, value in factors.items():
            if value > burst_threshold:
                burst_factors.append({
                    'factor': factor.name,
                    'value': value,
                    'burst_level': 'high' if value > 0.7 else 'medium'
                })
        
        if burst_factors:
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_burst_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_BURST,
                severity=PatternSeverity.HIGH if any(f['burst_level'] == 'high' for f in burst_factors) else PatternSeverity.MEDIUM,
                description=f"Patrón de burst detectado: {len(burst_factors)} factores en burst",
                timestamp=datetime.now(),
                confidence=0.7,
                context_snapshot=snapshot,
                pattern_data={'burst_factors': burst_factors},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_burst_actions(burst_factors),
                compatibility_score=compatibility
            )
        
        return None
    
    def _detect_contextual_changepoint(self, snapshot: ContextSnapshot) -> Optional[ContextualPattern]:
        """Detectar puntos de cambio contextuales."""
        # Simplificado: detectar cambios extremos en factores
        factors = snapshot.contextual_factors
        
        extreme_changes = []
        for factor, value in factors.items():
            if value > 0.9 or value < 0.1:  # Valores extremos
                extreme_changes.append({
                    'factor': factor.name,
                    'value': value,
                    'change_type': 'high' if value > 0.9 else 'low'
                })
        
        if extreme_changes:
            compatibility = self._calculate_contextual_compatibility(snapshot)
            
            return ContextualPattern(
                id=f"contextual_changepoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=ContextualPatternType.CONTEXTUAL_CHANGEPOINT,
                severity=PatternSeverity.CRITICAL if len(extreme_changes) > 2 else PatternSeverity.HIGH,
                description=f"Punto de cambio contextual detectado: {len(extreme_changes)} factores extremos",
                timestamp=datetime.now(),
                confidence=0.8,
                context_snapshot=snapshot,
                pattern_data={'extreme_changes': extreme_changes},
                affected_components=self._get_affected_components(snapshot),
                suggested_actions=self._generate_changepoint_actions(extreme_changes),
                compatibility_score=compatibility
            )
        
        return None
    
    def _generate_trend_actions(self, trend_factors: List[Dict]) -> List[str]:
        """Generar acciones sugeridas para tendencias."""
        actions = []
        
        for factor in trend_factors:
            if factor['trend_type'] == 'high':
                actions.append(f"Monitor {factor['factor']} closely due to high trend")
                actions.append(f"Consider scaling resources for {factor['factor']}")
            else:
                actions.append(f"Optimize {factor['factor']} usage due to low trend")
                actions.append(f"Review configuration for {factor['factor']}")
        
        return actions
    
    def _calculate_contextual_compatibility(self, snapshot: ContextSnapshot) -> float:
        """Calcular puntuación de compatibilidad del contexto."""
        factors = snapshot.contextual_factors
        
        # Calcular compatibilidad basada en valores de factores
        if not factors:
            return 0.0
        
        # Normalizar valores y calcular compatibilidad
        normalized_values = [min(1.0, max(0.0, value)) for value in factors.values()]
        compatibility = np.mean(normalized_values)
        
        return float(compatibility)
    
    def _get_affected_components(self, snapshot: ContextSnapshot) -> List[str]:
        """Obtener componentes afectados basado en el contexto."""
        components = []
        
        # Determinar componentes afectados según factores contextuales
        if snapshot.contextual_factors.get(ContextualFactor.SYSTEM_RESOURCES, 0) > 0.8:
            components.append("System-intensive")
        if snapshot.contextual_factors.get(ContextualFactor.USER_BEHAVIOR, 0) > 0.8:
            components.append("User-intensive")
        if snapshot.contextual_factors.get(ContextualFactor.NETWORK_CONDITIONS, 0) > 0.8:
            components.append("Network-intensive")
        if snapshot.contextual_factors.get(ContextualFactor.ERROR_RATES, 0) > 0.1:
            components.append("Error-prone")
        
        return components if components else ["General"]
    
    def _generate_anomaly_actions(self, anomalies: List[Dict]) -> List[str]:
        """Generar acciones para anomalías."""
        actions = []
        
        for anomaly in anomalies:
            if anomaly['factor'] == ContextualFactor.SYSTEM_RESOURCES.name:
                actions.append("Optimize system resources")
            elif anomaly['factor'] == ContextualFactor.USER_BEHAVIOR.name:
                actions.append("Adjust user behavior patterns")
            elif anomaly['factor'] == ContextualFactor.NETWORK_CONDITIONS.name:
                actions.append("Check network connectivity and optimize")
            elif anomaly['factor'] == ContextualFactor.ERROR_RATES.name:
                actions.append("Investigate error sources and implement monitoring")
        
        return actions
    
    def _generate_trend_actions(self, trend_factors: List[Dict]) -> List[str]:
        """Generar acciones para tendencias."""
        return [
            "Monitor resource usage patterns",
            "Implement proactive scaling",
            "Review system configuration"
        ]
    
    def _generate_correlation_actions(self, correlations: List[Dict]) -> List[str]:
        """Generar acciones para correlaciones."""
        return [
            "Analyze correlated factors for optimization opportunities",
            "Consider batch processing for correlated high-load operations",
            "Implement monitoring for correlated patterns"
        ]
    
    def _generate_seasonal_actions(self, patterns: List[str]) -> List[str]:
        """Generar acciones para patrones estacionales."""
        return [
            "Adjust resource allocation based on time patterns",
            "Schedule maintenance during low-activity periods",
            "Implement time-based optimizations"
        ]
    
    def _generate_burst_actions(self, burst_factors: List[Dict]) -> List[str]:
        """Generar acciones para patrones de burst."""
        return [
            "Implement burst handling mechanisms",
            "Add resource buffers for peak periods",
            "Monitor and alert on burst patterns"
        ]
    
    def _generate_changepoint_actions(self, extreme_changes: List[Dict]) -> List[str]:
        """Generar acciones para puntos de cambio."""
        return [
            "Investigate root causes of extreme changes",
            "Implement emergency protocols",
            "Review system configuration and dependencies"
        ]
    
    def get_contextual_patterns(self, pattern_type: Optional[ContextualPatternType] = None) -> List[ContextualPattern]:
        """Obtener patrones contextuales, filtrados por tipo si se especifica."""
        if pattern_type:
            return [p for p in self.contextual_patterns if p.type == pattern_type]
        return self.contextual_patterns
    
    def get_patterns_by_severity(self, severity: PatternSeverity) -> List[ContextualPattern]:
        """Obtener patrones por severidad."""
        return [p for p in self.contextual_patterns if p.severity == severity]
    
    def get_high_compatibility_patterns(self, threshold: float = 0.7) -> List[ContextualPattern]:
        """Obtener patrones con alta compatibilidad."""
        return [p for p in self.contextual_patterns if p.compatibility_score >= threshold]
    
    def clear_patterns(self, older_than_hours: int = 24) -> None:
        """Limpiar patrones antiguos."""
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        self.contextual_patterns = [
            p for p in self.contextual_patterns 
            if p.timestamp > cutoff_time
        ]
    
    def get_pattern_summary(self) -> Dict[str, Any]:
        """Obtener resumen de patrones detectados."""
        if not self.contextual_patterns:
            return {'total_patterns': 0, 'by_type': {}, 'by_severity': {}}
        
        by_type = {}
        by_severity = {}
        
        for pattern in self.contextual_patterns:
            by_type[pattern.type.value] = by_type.get(pattern.type.value, 0) + 1
            by_severity[pattern.severity.value] = by_severity.get(pattern.severity.value, 0) + 1
        
        return {
            'total_patterns': len(self.contextual_patterns),
            'by_type': by_type,
            'by_severity': by_severity,
            'avg_compatibility': np.mean([p.compatibility_score for p in self.contextual_patterns])
        }
    
    def export_patterns(self, file_path: str) -> None:
        """Exportar patrones a archivo JSON."""
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'patterns': [asdict(p) for p in self.contextual_patterns],
            'summary': self.get_pattern_summary()
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)