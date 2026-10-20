"""
Sistema predictivo de logs para Jarvis con machine learning y análisis de tendencias.
"""

import json
import logging
import sqlite3
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error
import pickle
import os


class PredictionType(Enum):
    """Tipos de predicciones."""
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    RESOURCE_USAGE = "resource_usage"
    SYSTEM_HEALTH = "system_health"
    FAILURE_PROBABILITY = "failure_probability"


class PredictionConfidence(Enum):
    """Niveles de confianza de predicción."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Prediction:
    """Estructura de predicción."""
    id: str
    type: PredictionType
    timestamp: datetime
    predicted_value: float
    confidence: PredictionConfidence
    confidence_score: float
    time_horizon: timedelta
    features: Dict[str, Any]
    model_used: str
    accuracy_metrics: Dict[str, float]
    suggested_actions: List[str]
    is_valid: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['type'] = self.type.value
        data['confidence'] = self.confidence.value
        data['time_horizon'] = self.time_horizon.total_seconds()
        return data


class TimeSeriesPredictor:
    """Predictor de series temporales."""
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.time_series = defaultdict(lambda: deque(maxlen=max_history))
        self.models = {}
        self.scalers = {}
        self.label_encoders = {}
        self.model_accuracies = {}
        self.lock = threading.Lock()
        
    def add_data_point(self, metric_name: str, value: float, 
                     timestamp: datetime = None, features: Dict[str, Any] = None) -> None:
        """Añadir punto de datos para predicción."""
        if timestamp is None:
            timestamp = datetime.now()
            
        self.time_series[metric_name].append({
            'timestamp': timestamp,
            'value': value,
            'features': features or {}
        })
        
        # Entrenar modelo si tenemos suficientes datos
        if len(self.time_series[metric_name]) >= 100:
            self._train_model(metric_name)
    
    def _train_model(self, metric_name: str) -> None:
        """Entrenar modelo para una métrica específica."""
        try:
            series = list(self.time_series[metric_name])
            if len(series) < 50:
                return
            
            # Preparar datos
            X, y = self._prepare_training_data(series)
            
            if len(X) < 10:
                return
            
            # Escalar características
            if metric_name not in self.scalers:
                self.scalers[metric_name] = StandardScaler()
            
            X_scaled = self.scalers[metric_name].fit_transform(X)
            
            # Entrenar múltiples modelos y seleccionar el mejor
            models = {
                'linear': LinearRegression(),
                'random_forest': RandomForestRegressor(n_estimators=50, random_state=42),
                'gradient_boosting': GradientBoostingRegressor(n_estimators=50, random_state=42)
            }
            
            best_model = None
            best_score = float('inf')
            best_model_name = None
            
            for model_name, model in models.items():
                try:
                    model.fit(X_scaled, y)
                    predictions = model.predict(X_scaled)
                    mae = mean_absolute_error(y, predictions)
                    
                    if mae < best_score:
                        best_score = mae
                        best_model = model
                        best_model_name = model_name
                except Exception as e:
                    logging.warning(f"Error entrenando {model_name} para {metric_name}: {e}")
            
            if best_model:
                self.models[metric_name] = best_model
                self.model_accuracies[metric_name] = {
                    'mae': best_score,
                    'model_type': best_model_name,
                    'training_samples': len(X)
                }
                
        except Exception as e:
            logging.error(f"Error entrenando modelo para {metric_name}: {e}")
    
    def _prepare_training_data(self, series: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
        """Preparar datos de entrenamiento."""
        X, y = [], []
        
        for i in range(1, len(series)):
            # Características basadas en valores pasados
            features = []
            
            # Valores pasados (lag features)
            for lag in [1, 2, 3, 6, 12]:
                if i >= lag:
                    features.append(series[i - lag]['value'])
                else:
                    features.append(0)
            
            # Características temporales
            timestamp = series[i]['timestamp']
            features.extend([
                timestamp.hour / 24.0,  # Hora normalizada
                timestamp.weekday() / 6.0,  # Día de la semana normalizado
                timestamp.day / 31.0,  # Día del mes normalizado
            ])
            
            # Características adicionales si existen
            if 'features' in series[i]:
                for key, value in series[i]['features'].items():
                    if isinstance(value, (int, float)):
                        features.append(value)
            
            X.append(features)
            y.append(series[i]['value'])
        
        return np.array(X), np.array(y)
    
    def predict(self, metric_name: str, time_horizon: timedelta, 
                features: Dict[str, Any] = None) -> Optional[Prediction]:
        """Realizar predicción."""
        if metric_name not in self.models or metric_name not in self.scalers:
            return None
        
        try:
            series = list(self.time_series[metric_name])
            if len(series) < 10:
                return None
            
            # Preparar características para predicción
            X_pred = []
            
            # Valores pasados
            for lag in [1, 2, 3, 6, 12]:
                if len(series) >= lag:
                    X_pred.append(series[-lag]['value'])
                else:
                    X_pred.append(0)
            
            # Características temporales
            last_timestamp = series[-1]['timestamp']
            future_timestamp = last_timestamp + time_horizon
            
            X_pred.extend([
                future_timestamp.hour / 24.0,
                future_timestamp.weekday() / 6.0,
                future_timestamp.day / 31.0,
            ])
            
            # Características adicionales
            if features:
                for key, value in features.items():
                    if isinstance(value, (int, float)):
                        X_pred.append(value)
            
            # Escalar características
            X_pred_scaled = self.scalers[metric_name].transform([X_pred])
            
            # Realizar predicción
            model = self.models[metric_name]
            predicted_value = model.predict(X_pred_scaled)[0]
            
            # Calcular confianza basada en precisión del modelo
            accuracy = self.model_accuracies[metric_name]
            mae = accuracy['mae']
            
            # Confidencia inversamente proporcional al error
            if mae < 0.1:
                confidence = PredictionConfidence.HIGH
                confidence_score = 0.9
            elif mae < 0.5:
                confidence = PredictionConfidence.MEDIUM
                confidence_score = 0.7
            elif mae < 1.0:
                confidence = PredictionConfidence.LOW
                confidence_score = 0.5
            else:
                confidence = PredictionConfidence.LOW
                confidence_score = 0.3
            
            # Generar sugerencias basadas en la predicción
            suggested_actions = self._generate_suggested_actions(
                metric_name, predicted_value, confidence
            )
            
            return Prediction(
                id=f"pred_{metric_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=self._get_prediction_type(metric_name),
                timestamp=datetime.now(),
                predicted_value=predicted_value,
                confidence=confidence,
                confidence_score=confidence_score,
                time_horizon=time_horizon,
                features={
                    'metric': metric_name,
                    'last_value': series[-1]['value'],
                    'prediction_horizon_seconds': time_horizon.total_seconds(),
                    'model_accuracy': accuracy
                },
                model_used=accuracy['model_type'],
                accuracy_metrics=accuracy,
                suggested_actions=suggested_actions
            )
            
        except Exception as e:
            logging.error(f"Error en predicción para {metric_name}: {e}")
            return None
    
    def _get_prediction_type(self, metric_name: str) -> PredictionType:
        """Determinar el tipo de predicción basado en el nombre de la métrica."""
        if 'error' in metric_name.lower():
            return PredictionType.ERROR_RATE
        elif 'response' in metric_name.lower() or 'latency' in metric_name.lower():
            return PredictionType.RESPONSE_TIME
        elif 'throughput' in metric_name.lower() or 'rate' in metric_name.lower():
            return PredictionType.THROUGHPUT
        elif 'cpu' in metric_name.lower() or 'memory' in metric_name.lower():
            return PredictionType.RESOURCE_USAGE
        elif 'health' in metric_name.lower():
            return PredictionType.SYSTEM_HEALTH
        else:
            return PredictionType.FAILURE_PROBABILITY
    
    def _generate_suggested_actions(self, metric_name: str, 
                                   predicted_value: float, confidence: PredictionConfidence) -> List[str]:
        """Generar sugerencias basadas en la predicción."""
        actions = []
        
        # Acciones generales basadas en tipo de métrica
        if 'error' in metric_name.lower():
            if predicted_value > 0.1:  # Alta tasa de error
                actions.extend([
                    "Revisar logs de errores detallados",
                    "Verificar conectividad de servicios",
                    "Considerar rollback de cambios recientes"
                ])
        elif 'response' in metric_name.lower():
            if predicted_value > 1000:  # Alta latencia
                actions.extend([
                    "Optimizar consultas de base de datos",
                    "Aumentar recursos del sistema",
                    "Implementar caché"
                ])
        elif 'cpu' in metric_name.lower() or 'memory' in metric_name.lower():
            if predicted_value > 80:  # Alto uso de recursos
                actions.extend([
                    "Revisar procesos consumidores de recursos",
                    "Considerar escalamiento horizontal",
                    "Optimizar uso de memoria"
                ])
        
        # Acciones basadas en confianza
        if confidence == PredictionConfidence.CRITICAL:
            actions.append("Implementar medidas correctivas inmediatas")
        elif confidence == PredictionConfidence.HIGH:
            actions.append("Monitorear de cerca las próximas horas")
        elif confidence == PredictionConfidence.MEDIUM:
            actions.append("Preparar plan de contingencia")
        
        return actions


class FailurePredictor:
    """Predictor de fallos del sistema."""
    
    def __init__(self):
        self.failure_patterns = []
        self.system_metrics = defaultdict(list)
        self.failure_model = None
        self.is_trained = False
        self.lock = threading.Lock()
        
    def add_system_metrics(self, timestamp: datetime, metrics: Dict[str, float]) -> None:
        """Añadir métricas del sistema para predicción de fallos."""
        with self.lock:
            self.system_metrics[timestamp] = metrics
            
            # Mantener solo las últimas 1000 mediciones
            if len(self.system_metrics) > 1000:
                oldest_key = min(self.system_metrics.keys())
                del self.system_metrics[oldest_key]
            
            # Entrenar modelo si tenemos suficientes datos
            if len(self.system_metrics) >= 100 and not self.is_trained:
                self._train_failure_model()
    
    def _train_failure_model(self) -> None:
        """Entrenar modelo de predicción de fallos."""
        try:
            # Preparar datos de entrenamiento
            X, y = [], []
            
            timestamps = sorted(self.system_metrics.keys())
            for i in range(1, len(timestamps)):
                # Características: métricas pasadas
                features = []
                prev_metrics = self.system_metrics[timestamps[i-1]]
                
                for metric_name, value in prev_metrics.items():
                    features.append(value)
                
                # Variable objetivo: 1 si hay fallo en el siguiente período, 0 si no
                has_failure = self._detect_failure_in_window(timestamps[i-1], timestamps[i])
                y.append(1 if has_failure else 0)
                
                X.append(features)
            
            if len(X) >= 50:
                from sklearn.ensemble import RandomForestClassifier
                
                self.failure_model = RandomForestClassifier(
                    n_estimators=100, random_state=42, class_weight='balanced'
                )
                self.failure_model.fit(X, y)
                self.is_trained = True
                
        except Exception as e:
            logging.error(f"Error entrenando modelo de fallos: {e}")
    
    def _detect_failure_in_window(self, start_time: datetime, end_time: datetime) -> bool:
        """Detectar si hubo fallos en un período de tiempo."""
        # Aquí se podría implementar lógica más compleja
        # Por simplicidad, asumimos que hay fallos si hay muchos errores en el período
        return False
    
    def predict_failure_probability(self, time_horizon: timedelta) -> Optional[Prediction]:
        """Predecir probabilidad de fallo."""
        if not self.is_trained or not self.system_metrics:
            return None
        
        try:
            # Obtener métricas más recientes
            latest_timestamp = max(self.system_metrics.keys())
            latest_metrics = self.system_metrics[latest_timestamp]
            
            # Preparar características
            features = list(latest_metrics.values())
            
            # Realizar predicción
            prediction_proba = self.failure_model.predict_proba([features])[0]
            failure_probability = prediction_proba[1]  # Probabilidad de fallo
            
            # Determinar confianza
            confidence = PredictionConfidence.LOW
            confidence_score = 0.5
            
            if failure_probability > 0.8:
                confidence = PredictionConfidence.CRITICAL
                confidence_score = 0.9
            elif failure_probability > 0.6:
                confidence = PredictionConfidence.HIGH
                confidence_score = 0.8
            elif failure_probability > 0.4:
                confidence = PredictionConfidence.MEDIUM
                confidence_score = 0.6
            
            # Generar sugerencias
            suggested_actions = []
            if failure_probability > 0.6:
                suggested_actions.extend([
                    "Implementar medidas preventivas inmediatas",
                    "Preparar sistema para posible fallo",
                    "Notificar al equipo de operaciones"
                ])
            elif failure_probability > 0.4:
                suggested_actions.extend([
                    "Aumentar monitoreo del sistema",
                    "Revisar configuración crítica",
                    "Preparar plan de recuperación"
                ])
            
            return Prediction(
                id=f"failure_pred_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                type=PredictionType.FAILURE_PROBABILITY,
                timestamp=datetime.now(),
                predicted_value=failure_probability,
                confidence=confidence,
                confidence_score=confidence_score,
                time_horizon=time_horizon,
                features={
                    'system_metrics': latest_metrics,
                    'prediction_horizon_seconds': time_horizon.total_seconds()
                },
                model_used='random_forest_failure',
                accuracy_metrics={'trained_samples': len(self.system_metrics)},
                suggested_actions=suggested_actions
            )
            
        except Exception as e:
            logging.error(f"Error en predicción de fallos: {e}")
            return None


class LogPredictor:
    """Sistema predictivo de logs integrado."""
    
    def __init__(self, db_path: str = "logs/predictions.db"):
        self.db_path = Path(db_path)
        self.time_series_predictor = TimeSeriesPredictor()
        self.failure_predictor = FailurePredictor()
        self.predictions = []
        self.prediction_history = defaultdict(list)
        self.lock = threading.Lock()
        
        # Crear base de datos
        self._create_database()
        
        # Seguimiento de entrenamiento
        self.last_training_time = None
        self.training_count = 0
        
    def _create_database(self) -> None:
        """Crear base de datos para predicciones."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabla de predicciones
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS predictions (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    predicted_value REAL NOT NULL,
                    confidence TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    time_horizon_seconds INTEGER NOT NULL,
                    features TEXT,
                    model_used TEXT,
                    accuracy_metrics TEXT,
                    suggested_actions TEXT,
                    actual_value REAL,
                    prediction_accuracy REAL,
                    is_valid BOOLEAN DEFAULT TRUE
                )
            ''')
            
            conn.commit()
    
    def add_log_data(self, log_entry: Dict[str, Any]) -> None:
        """Añadir datos de log para predicción."""
        timestamp = datetime.fromisoformat(log_entry['timestamp'])
        
        # Extraer métricas del log
        metrics = {}
        
        if log_entry.get('category') == 'performance':
            # Extraer tiempo de respuesta
            import re
            time_match = re.search(r'time=(\d+(?:\.\d+)?)', log_entry.get('message', ''))
            if time_match:
                metrics['response_time'] = float(time_match.group(1))
            
            # Extraer tasa de éxito
            success_match = re.search(r'success_rate=(\d+(?:\.\d+)?)', log_entry.get('message', ''))
            if success_match:
                metrics['success_rate'] = float(success_match.group(1))
        
        # Añadir errores como métricas
        if log_entry.get('level') in ['ERROR', 'CRITICAL']:
            metrics['error_count'] = 1
        
        # Añadir métricas al predictor de series temporales
        for metric_name, value in metrics.items():
            self.time_series_predictor.add_data_point(
                metric_name, value, timestamp, log_entry
            )
        
        # Añadir métricas del sistema al predictor de fallos
        if metrics:
            self.failure_predictor.add_system_metrics(timestamp, metrics)
    
    def generate_predictions(self, time_horizon: timedelta = timedelta(hours=1)) -> List[Prediction]:
        """Generar predicciones para todas las métricas."""
        predictions = []
        
        with self.lock:
            # Predicciones de series temporales
            for metric_name in self.time_series_predictor.models.keys():
                prediction = self.time_series_predictor.predict(
                    metric_name, time_horizon
                )
                if prediction:
                    predictions.append(prediction)
            
            # Predicción de fallos
            failure_prediction = self.failure_predictor.predict_failure_probability(time_horizon)
            if failure_prediction:
                predictions.append(failure_prediction)
            
            # Almacenar predicciones
            for prediction in predictions:
                self.predictions.append(prediction)
                self.prediction_history[prediction.type.value].append(prediction)
                self._store_prediction(prediction)
        
        return predictions
    
    def _store_prediction(self, prediction: Prediction) -> None:
        """Almacenar predicción en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO predictions (
                    id, type, timestamp, predicted_value, confidence, confidence_score,
                    time_horizon_seconds, features, model_used, accuracy_metrics,
                    suggested_actions, actual_value, prediction_accuracy, is_valid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                prediction.id,
                prediction.type.value,
                prediction.timestamp.isoformat(),
                prediction.predicted_value,
                prediction.confidence.value,
                prediction.confidence_score,
                prediction.time_horizon.total_seconds(),
                json.dumps(prediction.features),
                prediction.model_used,
                json.dumps(prediction.accuracy_metrics),
                json.dumps(prediction.suggested_actions),
                None,  # actual_value (se actualizará cuando se verifique)
                None,  # prediction_accuracy (se calculará después)
                prediction.is_valid
            ))
            conn.commit()
    
    def update_prediction_accuracy(self, prediction_id: str, actual_value: float) -> None:
        """Actualizar precisión de predicción con valor real."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Obtener predicción original
            cursor.execute("SELECT predicted_value FROM predictions WHERE id = ?", (prediction_id,))
            result = cursor.fetchone()
            
            if result:
                predicted_value = result[0]
                accuracy = 1 - abs(predicted_value - actual_value) / max(predicted_value, actual_value, 1)
                
                cursor.execute('''
                    UPDATE predictions 
                    SET actual_value = ?, prediction_accuracy = ?
                    WHERE id = ?
                ''', (actual_value, accuracy, prediction_id))
                conn.commit()
    
    def get_predictions_by_type(self, prediction_type: PredictionType, 
                               limit: int = 50) -> List[Prediction]:
        """Obtener predicciones por tipo."""
        return [p for p in self.predictions 
                if p.type == prediction_type and p.is_valid][:limit]
    
    def get_active_predictions(self) -> List[Prediction]:
        """Obtener predicciones activas (recientes)."""
        cutoff_time = datetime.now() - timedelta(hours=24)
        return [p for p in self.predictions 
                if p.timestamp > cutoff_time and p.is_valid]
    
    def get_prediction_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de predicciones."""
        stats = {
            'total_predictions': len(self.predictions),
            'active_predictions': len(self.get_active_predictions()),
            'predictions_by_type': defaultdict(int),
            'predictions_by_confidence': defaultdict(int),
            'model_accuracy': self.time_series_predictor.model_accuracies,
            'recent_predictions': len([p for p in self.predictions 
                                     if (datetime.now() - p.timestamp).total_seconds() < 3600])
        }
        
        for prediction in self.predictions:
            stats['predictions_by_type'][prediction.type.value] += 1
            stats['predictions_by_confidence'][prediction.confidence.value] += 1
        
        return dict(stats)
    
    def export_predictions(self, start_time: datetime = None, 
                          end_time: datetime = None, format: str = 'json') -> str:
        """Exportar predicciones."""
        query = "SELECT * FROM predictions WHERE 1=1"
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
            
            predictions = []
            for row in rows:
                prediction = {
                    'id': row[0],
                    'type': row[1],
                    'timestamp': row[2],
                    'predicted_value': row[3],
                    'confidence': row[4],
                    'confidence_score': row[5],
                    'time_horizon_seconds': row[6],
                    'features': json.loads(row[7]) if row[7] else {},
                    'model_used': row[8],
                    'accuracy_metrics': json.loads(row[9]) if row[9] else {},
                    'suggested_actions': json.loads(row[10]) if row[10] else [],
                    'actual_value': row[11],
                    'prediction_accuracy': row[12],
                    'is_valid': bool(row[13])
                }
                predictions.append(prediction)
            
            if format == 'json':
                return json.dumps(predictions, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Formato no soportado: {format}")
    
    def add_prediction_result(self, predictions: List[Prediction]) -> None:
        """Agregar resultado de predicción al historial."""
        with self.lock:
            for prediction in predictions:
                self.predictions.append(prediction)
                self.prediction_history[prediction.type.value].append(prediction)
                self._store_prediction(prediction)
    
    def train_models(self) -> Dict[str, Any]:
        """Entrenar todos los modelos predictivos."""
        training_results = {}
        
        with self.lock:
            try:
                # Entrenar modelos de series temporales
                for metric_name in list(self.time_series_predictor.time_series.keys()):
                    if len(self.time_series_predictor.time_series[metric_name]) >= 100:
                        self.time_series_predictor._train_model(metric_name)
                        training_results[metric_name] = 'success'
                    else:
                        training_results[metric_name] = 'insufficient_data'
                
                # Entrenar modelo de fallos si hay suficientes datos
                if len(self.failure_predictor.system_metrics) >= 100:
                    self.failure_predictor._train_failure_model()
                    training_results['failure_model'] = 'success'
                else:
                    training_results['failure_model'] = 'insufficient_data'
                
                # Actualizar tiempo de último entrenamiento
                self.last_training_time = datetime.now()
                self.training_count += 1
                
                return {
                    'status': 'success',
                    'training_results': training_results,
                    'total_models_trained': len([r for r in training_results.values() if r == 'success']),
                    'training_count': self.training_count,
                    'last_training': self.last_training_time
                }
                
            except Exception as e:
                logging.error(f"Error en entrenamiento de modelos: {e}")
                return {
                    'status': 'error',
                    'error': str(e),
                    'training_results': training_results
                }
    
    def get_predictions(self) -> List[Prediction]:
        """Obtener predicciones activas."""
        return self.get_active_predictions()
    
    @property
    def last_training(self) -> Optional[datetime]:
        """Obtener tiempo de último entrenamiento."""
        return self.last_training_time


# Instancia global del predictor de logs
log_predictor = LogPredictor()