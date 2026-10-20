"""
Adaptive Learning Engine v2.7.0
Motor de aprendizaje adaptativo con deep learning y optimización de hiperparámetros
"""

import asyncio
import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split, GridSearchCV, RandomizedSearchCV
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import joblib
import threading
import queue
import os
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import torch.nn.functional as F

from .advanced_logger import AdvancedLogger
from .performance_optimizer import PerformanceOptimizer, OptimizationStrategy
from .self_improvement_system import SelfImprovementSystem, LearningMode
from .pattern_analyzer import PatternAnalyzer
from .log_analytics import LogAnalytics

class LearningTask(Enum):
    """Tareas de aprendizaje"""
    HYPERPARAMETER_OPTIMIZATION = "hyperparameter_optimization"
    MODEL_TRAINING = "model_training"
    FEATURE_SELECTION = "feature_selection"
    ARCHITECTURE_SEARCH = "architecture_search"
    KNOWLEDGE_TRANSFER = "knowledge_transfer"
    ONLINE_LEARNING = "online_learning"
    BATCH_LEARNING = "batch_learning"
    REINFORCEMENT_LEARNING = "reinforcement_learning"

class NeuralArchitecture(Enum):
    """Arquitecturas neuronales"""
    MLP = "mlp"
    CNN = "cnn"
    LSTM = "lstm"
    TRANSFORMER = "transformer"
    ATTENTION = "attention"
    RESNET = "resnet"
    GAN = "gan"

@dataclass
class LearningTaskConfig:
    """Configuración de tarea de aprendizaje"""
    task_id: str
    task_type: LearningTask
    model_name: str
    hyperparameters: Dict[str, Any]
    training_data: Optional[np.ndarray] = None
    validation_data: Optional[np.ndarray] = None
    test_data: Optional[np.ndarray] = None
    target_variable: str = "efficiency_score"
    optimization_metric: str = "r2_score"
    max_epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 0.001
    patience: int = 10
    early_stopping: bool = True
    save_best_model: bool = True
    cross_validation_folds: int = 5
    search_iterations: int = 50
    random_state: int = 42

@dataclass
class ModelPerformance:
    """Rendimiento del modelo"""
    model_name: str
    task_type: LearningTask
    training_loss: float = 0.0
    validation_loss: float = 0.0
    test_loss: float = 0.0
    training_score: float = 0.0
    validation_score: float = 0.0
    test_score: float = 0.0
    convergence_rate: float = 0.0
    overfitting_indicator: float = 0.0
    training_time: float = 0.0
    inference_time: float = 0.0
    model_size: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

class AdaptiveLearningEngine:
    """
    Motor de aprendizaje adaptativo con deep learning y optimización de hiperparámetros
    """
    
    def __init__(self, config_path: str = None):
        self.logger = AdvancedLogger("AdaptiveLearningEngine")
        self.performance_optimizer = PerformanceOptimizer()
        self.self_improvement_system = SelfImprovementSystem()
        self.pattern_analyzer = PatternAnalyzer()
        self.analytics = LogAnalytics()
        
        # Configuración
        self.config = self._load_config(config_path)
        self.learning_tasks = {}
        self.model_registry = {}
        self.task_queue = queue.Queue()
        self.is_running = False
        
        # Modelos y dispositivos
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.torch_models = {}
        self.sklearn_models = {}
        self.optimizers = {}
        
        # Historial de rendimiento
        self.performance_history = []
        self.hyperparameter_tuning_history = []
        
        # Inicialización
        self._initialize_model_registry()
        self._start_learning_engine()
        
        self.logger.log("AdaptiveLearningEngine inicializado", level="INFO")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Cargar configuración del motor de aprendizaje"""
        default_config = {
            'learning_enabled': True,
            'auto_learning': True,
            'engine_interval': 60,  # segundos
            'max_concurrent_tasks': 3,
            'model_save_path': 'models/adaptive_models',
            'performance_history_file': 'data/adaptive_performance.json',
            'hyperparameter_config': {
                'learning_rates': [0.001, 0.01, 0.1],
                'batch_sizes': [16, 32, 64, 128],
                'hidden_layers': [1, 2, 3, 4],
                'neurons_per_layer': [32, 64, 128, 256, 512],
                'dropout_rates': [0.1, 0.2, 0.3, 0.4, 0.5],
                'activation_functions': ['relu', 'tanh', 'sigmoid', 'leaky_relu'],
                'optimizers': ['adam', 'sgd', 'rmsprop', 'adagrad'],
                'weight_decays': [0.0, 0.001, 0.01, 0.1]
            },
            'neural_architectures': {
                'mlp': {
                    'input_size': 64,
                    'hidden_layers': [128, 64],
                    'output_size': 1,
                    'activation': 'relu',
                    'dropout': 0.2
                },
                'lstm': {
                    'input_size': 64,
                    'hidden_size': 128,
                    'num_layers': 2,
                    'output_size': 1,
                    'dropout': 0.2
                }
            },
            'training_config': {
                'max_epochs': 100,
                'batch_size': 32,
                'learning_rate': 0.001,
                'patience': 10,
                'early_stopping': True,
                'gradient_clipping': 1.0,
                'scheduler_patience': 5,
                'scheduler_factor': 0.1
            },
            'optimization_config': {
                'cv_folds': 5,
                'search_iterations': 50,
                'n_jobs': -1,
                'scoring': 'r2',
                'refit': True,
                'random_state': 42
            }
        }
        
        try:
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
        except Exception as e:
            self.logger.log(f"Error cargando configuración: {e}", level="ERROR")
        
        return default_config
    
    def _initialize_model_registry(self):
        """Inicializar registro de modelos"""
        try:
            # Crear directorio para modelos si no existe
            os.makedirs(self.config['model_save_path'], exist_ok=True)
            
            # Registrar modelos disponibles
            self.model_registry = {
                'mlp': {
                    'class': MLPRegressor,
                    'hyperparameters': {
                        'hidden_layer_sizes': [(64,), (128,), (256,), (128, 64), (256, 128)],
                        'activation': ['relu', 'tanh', 'logistic'],
                        'solver': ['adam', 'sgd'],
                        'alpha': [0.0001, 0.001, 0.01],
                        'learning_rate': ['constant', 'adaptive'],
                        'max_iter': [1000]
                    },
                    'scaler': StandardScaler()
                },
                'random_forest': {
                    'class': RandomForestRegressor,
                    'hyperparameters': {
                        'n_estimators': [50, 100, 200],
                        'max_depth': [None, 10, 20, 30],
                        'min_samples_split': [2, 5, 10],
                        'min_samples_leaf': [1, 2, 4],
                        'max_features': ['auto', 'sqrt', 'log2']
                    },
                    'scaler': StandardScaler()
                },
                'gradient_boosting': {
                    'class': GradientBoostingRegressor,
                    'hyperparameters': {
                        'n_estimators': [50, 100, 200],
                        'learning_rate': [0.01, 0.1, 0.2],
                        'max_depth': [3, 5, 7],
                        'min_samples_split': [2, 5, 10],
                        'min_samples_leaf': [1, 2, 4]
                    },
                    'scaler': StandardScaler()
                }
            }
            
            # Cargar modelos pre-entrenados si existen
            self._load_trained_models()
            
            self.logger.log("Registro de modelos inicializado", level="INFO")
        except Exception as e:
            self.logger.log(f"Error inicializando registro de modelos: {e}", level="ERROR")
    
    def _load_trained_models(self):
        """Cargar modelos pre-entrenados"""
        try:
            for model_name, model_info in self.model_registry.items():
                model_path = os.path.join(self.config['model_save_path'], f'{model_name}_model.pkl')
                scaler_path = os.path.join(self.config['model_save_path'], f'{model_name}_scaler.pkl')
                
                if os.path.exists(model_path):
                    self.sklearn_models[model_name] = joblib.load(model_path)
                    self.logger.log(f"Modelo {model_name} cargado desde {model_path}", level="INFO")
                
                if os.path.exists(scaler_path):
                    self.model_registry[model_name]['scaler'] = joblib.load(scaler_path)
                    self.logger.log(f"Escalador {model_name} cargado desde {scaler_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error cargando modelos pre-entrenados: {e}", level="WARNING")
    
    def _save_trained_models(self):
        """Guardar modelos entrenados"""
        try:
            for model_name, model in self.sklearn_models.items():
                model_path = os.path.join(self.config['model_save_path'], f'{model_name}_model.pkl')
                scaler_path = os.path.join(self.config['model_save_path'], f'{model_name}_scaler.pkl')
                
                joblib.dump(model, model_path)
                joblib.dump(self.model_registry[model_name]['scaler'], scaler_path)
                
                self.logger.log(f"Modelo {model_name} guardado en {model_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error guardando modelos: {e}", level="ERROR")
    
    def _start_learning_engine(self):
        """Iniciar motor de aprendizaje"""
        self.is_running = True
        self.learning_thread = threading.Thread(target=self._learning_engine_loop)
        self.learning_thread.daemon = True
        self.learning_thread.start()
        
        self.logger.log("Motor de aprendizaje iniciado", level="INFO")
    
    def _learning_engine_loop(self):
        """Bucle principal del motor de aprendizaje"""
        while self.is_running:
            try:
                if self.config['learning_enabled'] and self.config['auto_learning']:
                    self._process_learning_queue()
                    self._auto_detect_learning_opportunities()
                    self._optimize_hyperparameters()
                    self._evaluate_model_performance()
                
                time.sleep(self.config['engine_interval'])
            except Exception as e:
                self.logger.log(f"Error en bucle del motor de aprendizaje: {e}", level="ERROR")
                time.sleep(5)
    
    def _process_learning_queue(self):
        """Procesar cola de tareas de aprendizaje"""
        try:
            while not self.task_queue.empty() and len(self.learning_tasks) < self.config['max_concurrent_tasks']:
                task_config = self.task_queue.get()
                
                # Ejecutar tarea en hilo separado
                task_thread = threading.Thread(target=self._execute_learning_task, args=(task_config,))
                task_thread.daemon = True
                task_thread.start()
                
                self.learning_tasks[task_config.task_id] = {
                    'task': task_config,
                    'thread': task_thread,
                    'start_time': datetime.now(),
                    'status': 'running'
                }
            
            # Verificar estado de tareas en curso
            completed_tasks = []
            for task_id, task_info in self.learning_tasks.items():
                if not task_info['thread'].is_alive():
                    completed_tasks.append(task_id)
            
            # Limpiar tareas completadas
            for task_id in completed_tasks:
                task_info = self.learning_tasks.pop(task_id)
                task_config = task_info['task']
                task_config.end_time = datetime.now()
                
                # Guardar en historial
                self.performance_history.append({
                    'task_id': task_config.task_id,
                    'task_type': task_config.task_type.value,
                    'model_name': task_config.model_name,
                    'performance': task_config.performance.__dict__,
                    'start_time': task_config.start_time.isoformat(),
                    'end_time': task_config.end_time.isoformat(),
                    'duration': (task_config.end_time - task_config.start_time).total_seconds()
                })
                
        except Exception as e:
            self.logger.log(f"Error procesando cola de aprendizaje: {e}", level="ERROR")
    
    def _execute_learning_task(self, task_config: LearningTaskConfig):
        """Ejecutar tarea de aprendizaje"""
        try:
            self.logger.log(f"Iniciando tarea de aprendizaje: {task_config.task_type.value}", level="INFO")
            
            task_config.start_time = datetime.now()
            task_config.status = "running"
            
            # Ejecutar tarea según tipo
            if task_config.task_type == LearningTask.HYPERPARAMETER_OPTIMIZATION:
                self._optimize_hyperparameters_task(task_config)
            elif task_config.task_type == LearningTask.MODEL_TRAINING:
                self._train_model_task(task_config)
            elif task_config.task_type == LearningTask.FEATURE_SELECTION:
                self._select_features_task(task_config)
            elif task_config.task_type == LearningTask.ARCHITECTURE_SEARCH:
                self._search_architecture_task(task_config)
            elif task_config.task_type == LearningTask.ONLINE_LEARNING:
                self._online_learning_task(task_config)
            elif task_config.task_type == LearningTask.BATCH_LEARNING:
                self._batch_learning_task(task_config)
            
            task_config.end_time = datetime.now()
            task_config.status = "completed"
            
            self.logger.log(f"Tarea de aprendizaje completada: {task_config.task_type.value}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error ejecutando tarea de aprendizaje: {e}", level="ERROR")
            task_config.status = "failed"
    
    def _optimize_hyperparameters_task(self, task_config: LearningTaskConfig):
        """Optimizar hiperparámetros de un modelo"""
        try:
            model_info = self.model_registry.get(task_config.model_name)
            if not model_info:
                raise ValueError(f"Modelo {task_config.model_name} no encontrado en el registro")
            
            # Preparar datos
            X, y = self._prepare_training_data(task_config)
            
            # Escalar datos
            X_scaled = model_info['scaler'].fit_transform(X)
            
            # Configurar búsqueda de hiperparámetros
            param_grid = model_info['hyperparameters']
            
            if task_config.task_type == LearningTask.HYPERPARAMETER_OPTIMIZATION:
                # Grid Search
                grid_search = GridSearchCV(
                    model_info['class'](),
                    param_grid,
                    cv=task_config.cross_validation_folds,
                    scoring=task_config.optimization_metric,
                    n_jobs=self.config['optimization_config']['n_jobs'],
                    refit=self.config['optimization_config']['refit']
                )
                
                grid_search.fit(X_scaled, y)
                
                # Guardar mejor modelo
                best_model = grid_search.best_estimator_
                self.sklearn_models[task_config.model_name] = best_model
                
                # Guardar hiperparámetros
                task_config.hyperparameters = grid_search.best_params_
                
                # Evaluar rendimiento
                performance = self._evaluate_model(best_model, X_scaled, y, task_config)
                task_config.performance = performance
                
                # Guardar en historial
                self.hyperparameter_tuning_history.append({
                    'task_id': task_config.task_id,
                    'model_name': task_config.model_name,
                    'best_params': grid_search.best_params_,
                    'best_score': grid_search.best_score_,
                    'performance': performance.__dict__,
                    'timestamp': datetime.now().isoformat()
                })
                
            self.logger.log(f"Hiperparámetros optimizados para {task_config.model_name}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error optimizando hiperparámetros: {e}", level="ERROR")
            raise
    
    def _train_model_task(self, task_config: LearningTaskConfig):
        """Entrenar un modelo"""
        try:
            model_info = self.model_registry.get(task_config.model_name)
            if not model_info:
                raise ValueError(f"Modelo {task_config.model_name} no encontrado en el registro")
            
            # Preparar datos
            X, y = self._prepare_training_data(task_config)
            
            # Escalar datos
            X_scaled = model_info['scaler'].fit_transform(X)
            
            # Dividir datos
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=task_config.random_state
            )
            
            # Crear modelo
            model = model_info['class'](**task_config.hyperparameters)
            
            # Entrenar modelo
            start_time = time.time()
            model.fit(X_train, y_train)
            training_time = time.time() - start_time
            
            # Evaluar modelo
            performance = self._evaluate_model(model, X_test, y_test, task_config)
            performance.training_time = training_time
            
            # Guardar modelo
            self.sklearn_models[task_config.model_name] = model
            
            task_config.performance = performance
            
            self.logger.log(f"Modelo {task_config.model_name} entrenado exitosamente", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error entrenando modelo: {e}", level="ERROR")
            raise
    
    def _select_features_task(self, task_config: LearningTaskConfig):
        """Seleccionar características para un modelo"""
        try:
            # Preparar datos
            X, y = self._prepare_training_data(task_config)
            
            # Implementar selección de características (simplificado)
            from sklearn.feature_selection import SelectKBest, f_regression
            
            # Seleccionar mejores características
            selector = SelectKBest(score_func=f_regression, k=min(20, X.shape[1]))
            X_selected = selector.fit_transform(X, y)
            
            # Obtener índices de características seleccionadas
            selected_features = selector.get_support(indices=True)
            
            # Guardar información de características
            task_config.selected_features = selected_features
            task_config.feature_scores = selector.scores_
            
            # Entrenar modelo con características seleccionadas
            model_info = self.model_registry.get(task_config.model_name)
            if model_info:
                X_scaled = model_info['scaler'].fit_transform(X_selected)
                
                model = model_info['class'](**task_config.hyperparameters)
                model.fit(X_scaled, y)
                
                performance = self._evaluate_model(model, X_scaled, y, task_config)
                task_config.performance = performance
                
                self.sklearn_models[f"{task_config.model_name}_selected"] = model
            
            self.logger.log(f"Características seleccionadas para {task_config.model_name}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error seleccionando características: {e}", level="ERROR")
            raise
    
    def _search_architecture_task(self, task_config: LearningTaskConfig):
        """Buscar arquitectura neural óptima"""
        try:
            # Preparar datos para redes neuronales
            X, y = self._prepare_training_data(task_config)
            
            # Convertir a tensores
            X_tensor = torch.FloatTensor(X)
            y_tensor = torch.FloatTensor(y).unsqueeze(1)
            
            # Dividir datos
            dataset = TensorDataset(X_tensor, y_tensor)
            train_size = int(0.8 * len(dataset))
            test_size = len(dataset) - train_size
            train_dataset, test_dataset = torch.utils.data.random_split(dataset, [train_size, test_size])
            
            # Buscar arquitectura
            best_architecture = None
            best_performance = 0.0
            
            for arch_name, arch_config in self.config['neural_architectures'].items():
                # Crear modelo
                model = self._create_neural_model(arch_name, arch_config)
                
                # Entrenar modelo
                performance = self._train_neural_model(
                    model, train_dataset, test_dataset, task_config
                )
                
                if performance.test_score > best_performance:
                    best_performance = performance.test_score
                    best_architecture = arch_name
                    best_model = model
            
            # Guardar mejor modelo
            if best_model:
                self.torch_models[task_config.model_name] = best_model
                task_config.best_architecture = best_architecture
                task_config.performance = ModelPerformance(
                    model_name=task_config.model_name,
                    task_type=task_config.task_type,
                    test_score=best_performance
                )
            
            self.logger.log(f"Arquitectura óptima encontrada: {best_architecture}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error buscando arquitectura: {e}", level="ERROR")
            raise
    
    def _online_learning_task(self, task_config: LearningTaskConfig):
        """Aprendizaje online incremental"""
        try:
            # Preparar datos iniciales
            X, y = self._prepare_training_data(task_config)
            
            # Crear modelo inicial
            model_info = self.model_registry.get(task_config.model_name)
            if model_info:
                model = model_info['class'](**task_config.hyperparameters)
                
                # Entrenamiento incremental
                batch_size = task_config.batch_size
                n_samples = len(X)
                
                for epoch in range(task_config.max_epochs):
                    # Mezclar datos
                    indices = np.random.permutation(n_samples)
                    
                    for i in range(0, n_samples, batch_size):
                        batch_indices = indices[i:i + batch_size]
                        X_batch = X[batch_indices]
                        y_batch = y[batch_indices]
                        
                        # Escalar datos
                        X_batch_scaled = model_info['scaler'].transform(X_batch)
                        
                        # Entrenamiento parcial
                        model.partial_fit(X_batch_scaled, y_batch)
                    
                    # Evaluar cada época
                    if epoch % 10 == 0:
                        X_scaled = model_info['scaler'].transform(X)
                        score = model.score(X_scaled, y)
                        
                        self.logger.log(f"Época {epoch}, Score: {score:.4f}", level="INFO")
                
                # Guardar modelo
                self.sklearn_models[task_config.model_name] = model
                
                # Evaluar rendimiento final
                performance = self._evaluate_model(model, X_scaled, y, task_config)
                task_config.performance = performance
            
            self.logger.log(f"Aprendizaje online completado para {task_config.model_name}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error en aprendizaje online: {e}", level="ERROR")
            raise
    
    def _batch_learning_task(self, task_config: LearningTaskConfig):
        """Aprendizaje por lotes"""
        try:
            # Preparar datos
            X, y = self._prepare_training_data(task_config)
            
            # Crear modelo
            model_info = self.model_registry.get(task_config.model_name)
            if model_info:
                model = model_info['class'](**task_config.hyperparameters)
                
                # Entrenamiento por lotes
                batch_size = task_config.batch_size
                n_samples = len(X)
                
                for epoch in range(task_config.max_epochs):
                    # Mezclar datos
                    indices = np.random.permutation(n_samples)
                    
                    for i in range(0, n_samples, batch_size):
                        batch_indices = indices[i:i + batch_size]
                        X_batch = X[batch_indices]
                        y_batch = y[batch_indices]
                        
                        # Escalar datos
                        X_batch_scaled = model_info['scaler'].fit_transform(X_batch)
                        
                        # Entrenamiento
                        model.fit(X_batch_scaled, y_batch)
                    
                    # Evaluar cada época
                    if epoch % 10 == 0:
                        X_scaled = model_info['scaler'].transform(X)
                        score = model.score(X_scaled, y)
                        
                        self.logger.log(f"Época {epoch}, Score: {score:.4f}", level="INFO")
                
                # Guardar modelo
                self.sklearn_models[task_config.model_name] = model
                
                # Evaluar rendimiento final
                performance = self._evaluate_model(model, X_scaled, y, task_config)
                task_config.performance = performance
            
            self.logger.log(f"Aprendizaje por lotes completado para {task_config.model_name}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error en aprendizaje por lotes: {e}", level="ERROR")
            raise
    
    def _prepare_training_data(self, task_config: LearningTaskConfig) -> Tuple[np.ndarray, np.ndarray]:
        """Preparar datos para entrenamiento"""
        try:
            # Recopilar datos del sistema
            system_data = self.self_improvement_system._collect_system_data()
            
            # Extraer características
            features = self.self_improvement_system._extract_learning_features(system_data)
            
            # Crear matriz de características
            X = np.array(features).reshape(1, -1)
            
            # Variable objetivo (eficiencia)
            y = np.array([system_data.get('efficiency_score', 0)])
            
            # Generar datos históricos si es necesario
            if len(X) < 10:
                # Generar datos sintéticos para entrenamiento
                n_samples = max(10, 100 - len(X))
                synthetic_X = np.random.randn(n_samples, len(features))
                synthetic_y = np.random.uniform(0, 100, n_samples)
                
                X = np.vstack([X, synthetic_X])
                y = np.hstack([y, synthetic_y])
            
            return X, y
            
        except Exception as e:
            self.logger.log(f"Error preparando datos de entrenamiento: {e}", level="ERROR")
            return np.array([[0] * 64]), np.array([0])
    
    def _create_neural_model(self, architecture_name: str, config: Dict[str, Any]) -> nn.Module:
        """Crear modelo neural según arquitectura"""
        if architecture_name == 'mlp':
            return self._create_mlp_model(config)
        elif architecture_name == 'lstm':
            return self._create_lstm_model(config)
        else:
            raise ValueError(f"Arquitectura {architecture_name} no soportada")
    
    def _create_mlp_model(self, config: Dict[str, Any]) -> nn.Module:
        """Crear modelo MLP"""
        layers = []
        
        # Capa de entrada
        layers.append(nn.Linear(config['input_size'], config['hidden_layers'][0]))
        layers.append(getattr(nn, config['activation'])())
        if config['dropout'] > 0:
            layers.append(nn.Dropout(config['dropout']))
        
        # Capas ocultas
        for i in range(len(config['hidden_layers']) - 1):
            layers.append(nn.Linear(config['hidden_layers'][i], config['hidden_layers'][i + 1]))
            layers.append(getattr(nn, config['activation'])())
            if config['dropout'] > 0:
                layers.append(nn.Dropout(config['dropout']))
        
        # Capa de salida
        layers.append(nn.Linear(config['hidden_layers'][-1], config['output_size']))
        
        return nn.Sequential(*layers)
    
    def _create_lstm_model(self, config: Dict[str, Any]) -> nn.Module:
        """Crear modelo LSTM"""
        class LSTMModel(nn.Module):
            def __init__(self, config):
                super(LSTMModel, self).__init__()
                self.lstm = nn.LSTM(
                    input_size=config['input_size'],
                    hidden_size=config['hidden_size'],
                    num_layers=config['num_layers'],
                    dropout=config['dropout'],
                    batch_first=True
                )
                self.fc = nn.Linear(config['hidden_size'], config['output_size'])
            
            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                output = self.fc(lstm_out[:, -1, :])
                return output
        
        return LSTMModel(config)
    
    def _train_neural_model(self, model: nn.Module, train_dataset: DataLoader, 
                           test_dataset: DataLoader, task_config: LearningTaskConfig) -> ModelPerformance:
        """Entrenar modelo neural"""
        try:
            model.to(self.device)
            
            # Configurar optimizador
            optimizer = optim.Adam(model.parameters(), lr=task_config.learning_rate)
            criterion = nn.MSELoss()
            
            # Entrenamiento
            model.train()
            train_losses = []
            
            for epoch in range(task_config.max_epochs):
                for batch_X, batch_y in train_dataset:
                    batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)
                    
                    optimizer.zero_grad()
                    outputs = model(batch_X)
                    loss = criterion(outputs, batch_y)
                    loss.backward()
                    optimizer.step()
                    
                    train_losses.append(loss.item())
                
                # Early stopping
                if task_config.early_stopping and len(train_losses) > task_config.patience:
                    recent_losses = train_losses[-task_config.patience:]
                    if all(recent_losses[i] >= recent_losses[i + 1] for i in range(len(recent_losses) - 1)):
                        break
            
            # Evaluación
            model.eval()
            test_losses = []
            predictions = []
            targets = []
            
            with torch.no_grad():
                for batch_X, batch_y in test_dataset:
                    batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)
                    
                    outputs = model(batch_X)
                    loss = criterion(outputs, batch_y)
                    test_losses.append(loss.item())
                    
                    predictions.extend(outputs.cpu().numpy())
                    targets.extend(batch_y.cpu().numpy())
            
            # Calcular métricas
            test_loss = np.mean(test_losses)
            r2 = r2_score(targets, predictions)
            mse = mean_squared_error(targets, predictions)
            mae = mean_absolute_error(targets, predictions)
            
            return ModelPerformance(
                model_name=task_config.model_name,
                task_type=task_config.task_type,
                test_loss=test_loss,
                test_score=r2,
                training_time=len(train_losses)
            )
            
        except Exception as e:
            self.logger.log(f"Error entrenando modelo neural: {e}", level="ERROR")
            return ModelPerformance(
                model_name=task_config.model_name,
                task_type=task_config.task_type,
                test_score=0.0
            )
    
    def _evaluate_model(self, model, X: np.ndarray, y: np.ndarray, 
                       task_config: LearningTaskConfig) -> ModelPerformance:
        """Evaluar rendimiento de un modelo"""
        try:
            # Predicciones
            predictions = model.predict(X)
            
            # Métricas
            r2 = r2_score(y, predictions)
            mse = mean_squared_error(y, predictions)
            mae = mean_absolute_error(y, predictions)
            
            # Tiempo de inferencia
            start_time = time.time()
            _ = model.predict(X)
            inference_time = time.time() - start_time
            
            # Tamaño del modelo
            model_size = len(joblib.dumps(model)) / 1024 / 1024  # MB
            
            return ModelPerformance(
                model_name=task_config.model_name,
                task_type=task_config.task_type,
                training_score=r2,
                validation_score=r2,
                test_score=r2,
                training_time=0.0,
                inference_time=inference_time,
                model_size=model_size
            )
            
        except Exception as e:
            self.logger.log(f"Error evaluando modelo: {e}", level="ERROR")
            return ModelPerformance(
                model_name=task_config.model_name,
                task_type=task_config.task_type,
                test_score=0.0
            )
    
    def _auto_detect_learning_opportunities(self):
        """Detectar automáticamente oportunidades de aprendizaje"""
        try:
            # Analizar rendimiento actual
            performance_status = self.performance_optimizer.get_optimization_status()
            
            # Detectar si se necesita reentrenamiento
            if performance_status.get('efficiency_score', 0) < 70:
                # Crear tarea de reentrenamiento
                task_config = LearningTaskConfig(
                    task_id=f"retrain_{int(time.time())}",
                    task_type=LearningTask.MODEL_TRAINING,
                    model_name="random_forest",
                    hyperparameters={'n_estimators': 100, 'random_state': 42}
                )
                
                self.task_queue.put(task_config)
                self.logger.log("Oportunidad de reentrenamiento detectada", level="INFO")
            
            # Detectar si se necesita optimización de hiperparámetros
            if len(self.performance_history) > 10:
                recent_performance = [p.get('test_score', 0) for p in self.performance_history[-10:]]
                if np.mean(recent_performance) < 0.8:
                    task_config = LearningTaskConfig(
                        task_id=f"hyperopt_{int(time.time())}",
                        task_type=LearningTask.HYPERPARAMETER_OPTIMIZATION,
                        model_name="gradient_boosting",
                        hyperparameters={'n_estimators': 100, 'random_state': 42}
                    )
                    
                    self.task_queue.put(task_config)
                    self.logger.log("Oportunidad de optimización de hiperparámetros detectada", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error detectando oportunidades de aprendizaje: {e}", level="ERROR")
    
    def _optimize_hyperparameters(self):
        """Optimizar hiperparámetros automáticamente"""
        try:
            # Para cada modelo en el registro
            for model_name in self.model_registry.keys():
                if model_name in self.sklearn_models:
                    # Verificar si necesita optimización
                    last_performance = self._get_last_model_performance(model_name)
                    
                    if last_performance and last_performance.test_score < 0.8:
                        # Crear tarea de optimización
                        task_config = LearningTaskConfig(
                            task_id=f"auto_hyperopt_{int(time.time())}",
                            task_type=LearningTask.HYPERPARAMETER_OPTIMIZATION,
                            model_name=model_name,
                            hyperparameters=self.model_registry[model_name]['hyperparameters']
                        )
                        
                        self.task_queue.put(task_config)
                        
        except Exception as e:
            self.logger.log(f"Error optimizando hiperparámetros: {e}", level="ERROR")
    
    def _evaluate_model_performance(self):
        """Evaluar rendimiento de todos los modelos"""
        try:
            for model_name, model in self.sklearn_models.items():
                performance = self._get_last_model_performance(model_name)
                
                if performance:
                    # Guardar en historial
                    self.performance_history.append({
                        'model_name': model_name,
                        'timestamp': datetime.now().isoformat(),
                        'performance': performance.__dict__
                    })
            
            # Limitar tamaño del historial
            if len(self.performance_history) > 1000:
                self.performance_history = self.performance_history[-1000:]
            
        except Exception as e:
            self.logger.log(f"Error evaluando rendimiento de modelos: {e}", level="ERROR")
    
    def _get_last_model_performance(self, model_name: str) -> Optional[ModelPerformance]:
        """Obtener último rendimiento de un modelo"""
        try:
            # Buscar en historial reciente
            for history_entry in reversed(self.performance_history):
                if history_entry.get('model_name') == model_name:
                    return ModelPerformance(
                        model_name=model_name,
                        task_type=LearningTask.MODEL_TRAINING,
                        **history_entry.get('performance', {})
                    )
            return None
        except Exception as e:
            self.logger.log(f"Error obteniendo rendimiento del modelo: {e}", level="ERROR")
            return None
    
    def get_learning_engine_status(self) -> Dict[str, Any]:
        """Obtener estado del motor de aprendizaje"""
        try:
            return {
                'is_running': self.is_running,
                'learning_enabled': self.config['learning_enabled'],
                'auto_learning': self.config['auto_learning'],
                'active_tasks': len(self.learning_tasks),
                'queued_tasks': self.task_queue.qsize(),
                'total_models': len(self.sklearn_models) + len(self.torch_models),
                'performance_history_size': len(self.performance_history),
                'hyperparameter_tuning_history_size': len(self.hyperparameter_tuning_history),
                'best_model': self._get_best_model(),
                'average_performance': self._get_average_performance()
            }
        except Exception as e:
            self.logger.log(f"Error obteniendo estado del motor de aprendizaje: {e}", level="ERROR")
            return {}
    
    def _get_best_model(self) -> Optional[Dict[str, Any]]:
        """Obtener mejor modelo"""
        try:
            if not self.performance_history:
                return None
            
            best_performance = max(
                self.performance_history,
                key=lambda x: x.get('performance', {}).get('test_score', 0)
            )
            
            return {
                'model_name': best_performance.get('model_name'),
                'test_score': best_performance.get('performance', {}).get('test_score', 0),
                'timestamp': best_performance.get('timestamp')
            }
        except Exception as e:
            self.logger.log(f"Error obteniendo mejor modelo: {e}", level="ERROR")
            return None
    
    def _get_average_performance(self) -> float:
        """Obtener rendimiento promedio"""
        try:
            if not self.performance_history:
                return 0.0
            
            scores = [h.get('performance', {}).get('test_score', 0) for h in self.performance_history]
            return np.mean(scores)
        except Exception as e:
            self.logger.log(f"Error calculando rendimiento promedio: {e}", level="ERROR")
            return 0.0
    
    def add_learning_task(self, task_config: LearningTaskConfig):
        """Añadir tarea de aprendizaje"""
        try:
            self.task_queue.put(task_config)
            self.logger.log(f"Tarea de aprendizaje añadida: {task_config.task_type.value}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error añadiendo tarea de aprendizaje: {e}", level="ERROR")
    
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Obtener información de un modelo"""
        try:
            if model_name in self.sklearn_models:
                return {
                    'model_type': 'sklearn',
                    'model': self.sklearn_models[model_name],
                    'hyperparameters': self.model_registry[model_name]['hyperparameters'],
                    'scaler': self.model_registry[model_name]['scaler']
                }
            elif model_name in self.torch_models:
                return {
                    'model_type': 'torch',
                    'model': self.torch_models[model_name],
                    'device': str(self.device)
                }
            else:
                return None
        except Exception as e:
            self.logger.log(f"Error obteniendo información del modelo: {e}", level="ERROR")
            return None
    
    def export_learning_report(self, filepath: str):
        """Exportar reporte de aprendizaje"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'learning_engine_status': self.get_learning_engine_status(),
                'performance_history': self.performance_history[-100:],
                'hyperparameter_tuning_history': self.hyperparameter_tuning_history[-50:],
                'model_registry': list(self.model_registry.keys()),
                'active_tasks': [
                    {
                        'task_id': task_id,
                        'task_type': task_info['task'].task_type.value,
                        'model_name': task_info['task'].model_name,
                        'start_time': task_info['start_time'].isoformat(),
                        'status': task_info['status']
                    }
                    for task_id, task_info in self.learning_tasks.items()
                ],
                'best_model': self._get_best_model(),
                'average_performance': self._get_average_performance(),
                'total_training_time': sum(
                    h.get('performance', {}).get('training_time', 0) 
                    for h in self.performance_history
                )
            }
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.log(f"Reporte de aprendizaje exportado a {filepath}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error exportando reporte de aprendizaje: {e}", level="ERROR")
    
    def stop_learning_engine(self):
        """Detener motor de aprendizaje"""
        try:
            self.is_running = False
            self.config['learning_enabled'] = False
            self.logger.log("Motor de aprendizaje detenido", level="INFO")
        except Exception as e:
            self.logger.log(f"Error deteniendo motor de aprendizaje: {e}", level="ERROR")
    
    def start_learning_engine(self):
        """Iniciar motor de aprendizaje"""
        try:
            self.config['learning_enabled'] = True
            self.is_running = True
            self.logger.log("Motor de aprendizaje iniciado", level="INFO")
        except Exception as e:
            self.logger.log(f"Error iniciando motor de aprendizaje: {e}", level="ERROR")
    
    def __del__(self):
        """Destructor"""
        try:
            self.is_running = False
            if hasattr(self, 'learning_thread'):
                self.learning_thread.join(timeout=5)
        except Exception as e:
            self.logger.log(f"Error en destructor: {e}", level="ERROR")