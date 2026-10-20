from typing import Dict, Any, List, Optional
from datetime import datetime
import os

import numpy as np

class MockLogger:
    """Logger simulado para pruebas"""
    def error(self, message):
        print(f"ERROR: {message}")
    def info(self, message):
        print(f"INFO: {message}")
    def warning(self, message):
        print(f"WARNING: {message}")

class ContextualAdaptationEngine:
    """Motor de adaptación contextual para adaptación de Goal."""

    def __init__(self, data_dir: Optional[str] = None):
        """
        Inicializar el motor de adaptación contextual.

        Args:
            data_dir: Directorio de persistencia de datos de adaptación.
                      Si es None se usa el directorio 'data' del proyecto.
        """
        self.data_dir = os.path.abspath(data_dir) if data_dir else os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'data')
        )
        self.knowledge_base = {
            "goal_adaptation_feedback": [],
            "learning_results": [],
            "adaptation_strategies": {}
        }
        self.logger = MockLogger()
        self.adaptation_history = []
        
        # Inicializar persistencia de adaptación de Goal
        self._initialize_goal_adaptation_persistence()

    def _capture_goal_adaptation_feedback(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Capturar feedback de adaptación de Goal y analizar el resultado.

        Args:
            feedback_data: Datos de feedback con información sobre la adaptación

        Returns:
            Dict con análisis de feedback y resultados de aprendizaje
        """
        try:

            # Validar datos de entrada
            if not all(key in feedback_data for key in
                      ["adaptation_id", "original_goal_id", "adapted_goal_id",
                       "adaptation_context", "execution_result", "verification_result"]):
                raise ValueError("Datos de feedback incompletos")

            # Procesar datos de ejecución
            execution_result = feedback_data["execution_result"]
            verification_result = feedback_data["verification_result"]

            # Calcular métricas de rendimiento
            performance_metrics = {
                "response_time": execution_result.get("performance_metrics", {}).get("response_time", 0.0),
                "accuracy": execution_result.get("performance_metrics", {}).get("accuracy", 0.0),
                "success": execution_result.get("success", False),
                "verified": verification_result.get("verified", False),
                "impact_score": verification_result.get("impact_score", 0.0)
            }

            # Analizar mejora
            improvement_analysis = {
                "performance_improvement": 0.0,
                "resource_efficiency": 0.0,
                "response_time_improvement": 0.0,
                "accuracy_improvement": 0.0,
                "pattern_recognition": [],
                "strategic_insights": []
            }

            # Calcular mejoras si hay datos de referencia.
            # Las métricas base pueden venir en 'original_metrics' o, según el
            # contrato de feedback, en 'adaptation_context.expected_metrics'.
            original_metrics = feedback_data.get("original_metrics")
            if not original_metrics:
                original_metrics = feedback_data.get("adaptation_context", {}).get("expected_metrics", {}) or {}
            current_metrics = performance_metrics

            # Calcular mejoras en tiempo de respuesta (menor tiempo = mejor)
            if original_metrics.get("response_time") and current_metrics.get("response_time"):
                improvement_analysis["response_time_improvement"] = (
                    (original_metrics["response_time"] - current_metrics["response_time"]) /
                    original_metrics["response_time"] * 100
                )

            # Calcular mejoras en precisión (mayor precisión = mejor)
            if original_metrics.get("accuracy") and current_metrics.get("accuracy"):
                improvement_analysis["accuracy_improvement"] = (
                    (current_metrics["accuracy"] - original_metrics["accuracy"]) /
                    original_metrics["accuracy"] * 100
                )

            # La mejora de rendimiento es la media de las mejoras calculadas
            computed_improvements = [
                improvement_analysis["response_time_improvement"],
                improvement_analysis["accuracy_improvement"]
            ]
            computed_improvements = [value for value in computed_improvements if value]
            if computed_improvements:
                improvement_analysis["performance_improvement"] = sum(computed_improvements) / len(computed_improvements)

            # Detectar patrones de éxito
            if performance_metrics["success"] and performance_metrics["verified"]:
                pattern = {
                    "pattern_type": "goal_adaptation_success",
                    "context": feedback_data["adaptation_context"],
                    "metrics": performance_metrics,
                    "timestamp": datetime.now().isoformat(),
                    "confidence": 0.9
                }
                improvement_analysis["pattern_recognition"].append(pattern)

            # Detectar patrones de fallo
            if not performance_metrics["success"] or not performance_metrics["verified"]:
                pattern = {
                    "pattern_type": "goal_adaptation_failure",
                    "context": feedback_data["adaptation_context"],
                    "metrics": performance_metrics,
                    "timestamp": datetime.now().isoformat(),
                    "confidence": 0.8
                }
                improvement_analysis["pattern_recognition"].append(pattern)

            # Detectar estrategias exitosas
            if performance_metrics["impact_score"] > 0.7:
                strategy = {
                    "strategy_type": "adaptation_strategy",
                    "context": feedback_data["adaptation_context"],
                    "metrics": performance_metrics,
                    "timestamp": datetime.now().isoformat(),
                    "confidence": 0.85
                }
                improvement_analysis["strategic_insights"].append(strategy)

            # Guardar análisis en knowledge base
            self._record_feedback_analysis(feedback_data["adaptation_id"], improvement_analysis)

            # Registrar en el historial de adaptación (dato crítico para convergencia)
            self._record_adaptation_history(
                feedback_data["adaptation_id"],
                improvement_analysis,
                feedback_data["adaptation_context"]
            )

            return {
                "success": True,
                "adaptation_id": feedback_data["adaptation_id"],
                "original_goal_id": feedback_data["original_goal_id"],
                "adapted_goal_id": feedback_data["adapted_goal_id"],
                "improvement_analysis": improvement_analysis,
                "feedback_metrics": performance_metrics,
                "adaptation_context": feedback_data["adaptation_context"],
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error capturando feedback de adaptación: {e}")
            return {
                "success": False,
                "adaptation_id": feedback_data.get("adaptation_id"),
                "error_message": str(e),
                "feedback_metrics": {},
                "adaptation_context": feedback_data.get("adaptation_context", {})
            }

    def _execute_goal_adaptation_learning_loop(self, feedback_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar bucle de aprendizaje continuo para adaptación de Goal.

        Args:
            feedback_result: Resultado del análisis de feedback

        Returns:
            Dict con resultados del bucle de aprendizaje
        """
        try:

            # Verificar que el feedback fue exitoso
            if not feedback_result.get("success", False):
                return {
                    "success": False,
                    "message": "No se pudo ejecutar el bucle de aprendizaje debido a un error en el feedback",
                    "learned_patterns": [],
                    "adaptation_strategies": {}
                }

            # Procesar análisis de mejora
            improvement_analysis = feedback_result["improvement_analysis"]

            # Analizar patrones de aprendizaje
            learned_patterns = self._analyze_learning_patterns(
                improvement_analysis["pattern_recognition"],
                feedback_result["feedback_metrics"]
            )

            # Actualizar estrategias adaptativas
            updated_strategies = self._update_adaptive_strategies(
                learned_patterns,
                self.knowledge_base.get("adaptation_strategies", {})
            )

            # Calcular convergencia
            convergence_metrics = self._calculate_learning_convergence(
                feedback_result["feedback_metrics"],
                improvement_analysis["performance_improvement"]
            )

            # Guardar resultados en knowledge base
            self._record_learning_results(
                feedback_result.get("adaptation_id", "unknown"),
                learned_patterns,
                updated_strategies,
                convergence_metrics
            )
            return {
                "success": True,
                "learned_patterns": learned_patterns,
                "adaptation_strategies": updated_strategies,
                "convergence_metrics": convergence_metrics,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error ejecutando bucle de aprendizaje: {e}")
            return {
                "success": False,
                "error_message": str(e),
                "learned_patterns": [],
                "adaptation_strategies": {},
                "convergence_metrics": {}
            }

    def _analyze_learning_patterns(self, patterns: List[Dict[str, Any]], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analizar patrones de aprendizaje de adaptación de Goal.

        Args:
            patterns: Lista de patrones detectados
            metrics: Métricas de rendimiento

        Returns:
            Lista de patrones de aprendizaje analizados
        """
        try:
            analyzed_patterns = []
            for pattern in patterns:

                # Calcular confianza basada en métricas
                confidence = pattern.get("confidence", 0.0)

                # Ajustar confianza según métricas
                if metrics.get("impact_score", 0.0) > 0.7:
                    confidence = min(1.0, confidence * 1.2)
                elif metrics.get("impact_score", 0.0) < 0.3:
                    confidence = max(0.0, confidence * 0.8)

                # Convertir a formato estructurado
                analyzed_pattern = {
                    "pattern_id": f"pattern_{len(analyzed_patterns) + 1}",
                    "pattern_type": pattern["pattern_type"],
                    "context": pattern["context"],
                    "metrics": pattern["metrics"],
                    "confidence": confidence,
                    "timestamp": pattern["timestamp"],
                    "description": self._generate_pattern_description(pattern)
                }
                analyzed_patterns.append(analyzed_pattern)
            return analyzed_patterns
        except Exception as e:
            self.logger.error(f"Error analizando patrones de aprendizaje: {e}")
            return []

    def _update_adaptive_strategies(self, learned_patterns: List[Dict[str, Any]], current_strategies: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actualizar estrategias adaptativas basadas en patrones de aprendizaje.

        Args:
            learned_patterns: Patrones de aprendizaje analizados
            current_strategies: Estrategias existentes

        Returns:
            Diccionario actualizado de estrategias
        """
        try:
            updated_strategies = current_strategies.copy()

            # Procesar patrones de éxito
            success_patterns = [p for p in learned_patterns if p["pattern_type"] == "goal_adaptation_success"]
            if success_patterns:

                # Crear estrategias basadas en patrones de éxito
                for pattern in success_patterns:
                    strategy = {
                        "strategy_id": f"strategy_{len(updated_strategies) + 1}",
                        "strategy_type": "adaptation",
                        "context": pattern["context"],
                        "pattern_id": pattern["pattern_id"],
                        "metrics": pattern["metrics"],
                        "confidence": pattern["confidence"],
                        "success_rate": 0.9,
                        "last_updated": datetime.now().isoformat(),
                        "description": self._generate_strategy_description(pattern)
                    }
                    updated_strategies[strategy["strategy_id"]] = strategy

            # Procesar patrones de fallo
            failure_patterns = [p for p in learned_patterns if p["pattern_type"] == "goal_adaptation_failure"]
            if failure_patterns:

                # Actualizar estrategias existentes con patrones de fallo
                for pattern in failure_patterns:
                    if pattern["pattern_id"] in updated_strategies:
                        updated_strategies[pattern["pattern_id"]]["failure_count"] = (
                            updated_strategies[pattern["pattern_id"]].get("failure_count", 0) + 1
                        )
                        updated_strategies[pattern["pattern_id"]]["confidence"] = (
                            updated_strategies[pattern["pattern_id"]]["confidence"] * 0.9
                        )
            return updated_strategies
        except Exception as e:
            self.logger.error(f"Error actualizando estrategias adaptativas: {e}")
            return current_strategies

    def _calculate_learning_convergence(self, metrics: Dict[str, Any], improvement: float) -> Dict[str, Any]:
        """
        Calcular métricas de convergencia del aprendizaje.

        Args:
            metrics: Métricas de rendimiento
            improvement: Mejora detectada en el ciclo

        Returns:
            Diccionario con métricas de convergencia
        """
        try:
            convergence = {
                "convergence_status": "incomplete",
                "convergence_score": 0.0,
                "learning_rate": 0.0,
                "stability": 0.0,
                "trend": "unknown",
                "timestamp": datetime.now().isoformat()
            }

            # Calcular puntuación de convergencia
            if metrics.get("success", False) and metrics.get("verified", False):
                convergence["convergence_status"] = "partial"
                convergence["convergence_score"] = min(1.0, improvement / 100.0)

                # Calcular tasa de aprendizaje
                if self.adaptation_history:
                    history = self.adaptation_history[-10:]
                    if history:
                        avg_improvement = sum(
                            self._extract_performance_improvement(h) for h in history
                        ) / len(history)
                        convergence["learning_rate"] = avg_improvement / 10  # Ajuste de escala
                else:
                    convergence["learning_rate"] = 0.0

                # Calcular estabilidad
                if len(self.adaptation_history) > 5:
                    recent_improvements = [
                        self._extract_performance_improvement(h)
                        for h in self.adaptation_history[-5:]
                    ]
                    if recent_improvements:
                        std_dev = np.std(recent_improvements)
                        scale = max(abs(value) for value in recent_improvements)
                        convergence["stability"] = (
                            1.0 - (std_dev / scale) if scale > 0 else 1.0
                        )
                        convergence["stability"] = max(0.0, min(1.0, convergence["stability"]))

                # Determinar tendencia
                if improvement > 0.2:
                    convergence["trend"] = "improving"
                elif improvement < -0.2:
                    convergence["trend"] = "deteriorating"
                else:
                    convergence["trend"] = "stable"
            return convergence
        except Exception as e:
            self.logger.error(f"Error calculando convergencia del aprendizaje: {e}")
            return {
                "convergence_status": "failed",
                "convergence_score": 0.0,
                "learning_rate": 0.0,
                "stability": 0.0,
                "trend": "unknown",
                "error": str(e)
            }

    def _record_feedback_analysis(self, adaptation_id: str, analysis: Dict[str, Any]) -> None:
        """Grabar análisis de feedback en la base de conocimiento."""
        try:
            if "goal_adaptation_feedback" not in self.knowledge_base:
                self.knowledge_base["goal_adaptation_feedback"] = []
            feedback_record = {
                "adaptation_id": adaptation_id,
                "analysis": analysis,
                "timestamp": datetime.now().isoformat(),
                "status": "processed"
            }
            self.knowledge_base["goal_adaptation_feedback"].append(feedback_record)

            # Limitar tamaño del historial
            if len(self.knowledge_base["goal_adaptation_feedback"]) > 1000:
                self.knowledge_base["goal_adaptation_feedback"] = self.knowledge_base["goal_adaptation_feedback"][-1000:]

            # Persistir feedback en archivo JSON
            self._save_goal_adaptation_feedback()
        except Exception as e:
            self.logger.error(f"Error registrando análisis de feedback: {e}")

    def _record_adaptation_history(
        self,
        adaptation_id: str,
        analysis: Dict[str, Any],
        adaptation_context: Dict[str, Any]
    ) -> None:
        """
        Registrar una entrada en el historial de adaptación.

        El historial de adaptación es un dato crítico: alimenta el cálculo de
        convergencia (tasa de aprendizaje y estabilidad) y debe sobrevivir al
        reinicio, por lo que se persiste junto al feedback.
        """
        try:
            history_entry = {
                "adaptation_id": adaptation_id,
                "performance_impact": {
                    "performance_improvement": analysis.get("performance_improvement", 0.0),
                    "response_time_improvement": analysis.get("response_time_improvement", 0.0),
                    "accuracy_improvement": analysis.get("accuracy_improvement", 0.0)
                },
                "context": adaptation_context,
                "timestamp": datetime.now().isoformat()
            }
            self.adaptation_history.append(history_entry)

            # Limitar tamaño del historial
            if len(self.adaptation_history) > 1000:
                self.adaptation_history = self.adaptation_history[-1000:]

            # Persistir historial junto al feedback
            self._save_goal_adaptation_feedback()
        except Exception as e:
            self.logger.error(f"Error registrando historial de adaptación: {e}")

    @staticmethod
    def _extract_performance_improvement(history_entry: Dict[str, Any]) -> float:
        """
        Extraer la mejora de rendimiento de una entrada del historial.

        Tolera tanto el formato canónico (performance_impact como diccionario)
        como el formato legacy (performance_impact numérico).
        """
        try:
            performance_impact = history_entry.get("performance_impact", 0.0)
            if isinstance(performance_impact, dict):
                return float(performance_impact.get("performance_improvement", 0.0) or 0.0)
            return float(performance_impact or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _record_learning_results(self, adaptation_id: str, patterns: List[Dict[str, Any]], strategies: Dict[str, Any], convergence: Dict[str, Any]) -> None:
        """Grabar resultados del bucle de aprendizaje en la base de conocimiento."""
        try:
            if "learning_results" not in self.knowledge_base:
                self.knowledge_base["learning_results"] = []

            # Las estrategias actualizadas son el estado vigente del motor:
            # deben reflejarse en la base de conocimiento para persistirse
            # y sobrevivir al reinicio.
            if strategies:
                self.knowledge_base["adaptation_strategies"] = strategies

            learning_record = {
                "adaptation_id": adaptation_id,
                "learned_patterns": patterns,
                "updated_strategies": strategies,
                "convergence_metrics": convergence,
                "timestamp": datetime.now().isoformat(),
                "status": "completed"
            }
            self.knowledge_base["learning_results"].append(learning_record)

            # Limitar tamaño del historial
            if len(self.knowledge_base["learning_results"]) > 500:
                self.knowledge_base["learning_results"] = self.knowledge_base["learning_results"][-500:]

            # Persistir resultados de aprendizaje en archivo JSON
            self._save_goal_adaptation_learning_results()
        except Exception as e:
            self.logger.error(f"Error registrando resultados de aprendizaje: {e}")

    def _generate_pattern_description(self, pattern: Dict[str, Any]) -> str:
        """Generar descripción de patrón de aprendizaje."""
        try:
            if pattern["pattern_type"] == "goal_adaptation_success":
                return f"Patrón de éxito: Contexto {pattern['context']['goal_type']} en {pattern['context']['context_type']}, mejoras en {pattern['metrics']['response_time']:.2f}s y precisión {pattern['metrics']['accuracy']:.2f}"
            elif pattern["pattern_type"] == "goal_adaptation_failure":
                return f"Patrón de fallo: Contexto {pattern['context']['goal_type']} en {pattern['context']['context_type']}, resultado negativo"
            return "Patrón desconocido"
        except Exception as e:
            return f"Error generando descripción: {e}"

    def _generate_strategy_description(self, pattern: Dict[str, Any]) -> str:
        """Generar descripción de estrategia adaptativa."""
        try:
            return f"Estrategia de adaptación para {pattern['context']['goal_type']} en {pattern['context']['context_type']}, basada en mejoras de {pattern['metrics']['response_time']:.2f}s y precisión {pattern['metrics']['accuracy']:.2f}"
        except Exception as e:
            return f"Error generando descripción de estrategia: {e}"

    def _save_goal_adaptation_feedback(self) -> None:
        """Guardar feedback de adaptación de Goal en archivo JSON."""
        try:
            import json

            # Ruta del archivo de persistencia
            feedback_file = os.path.join(self.data_dir, 'goal_adaptation_feedback.json')

            # Crear directorio si no existe
            os.makedirs(os.path.dirname(feedback_file), exist_ok=True)

            # Preparar datos para guardar
            feedback_data = {
                "goal_adaptation_feedback": self.knowledge_base.get("goal_adaptation_feedback", []),
                "adaptation_history": self.adaptation_history,
                "last_updated": datetime.now().isoformat()
            }

            # Guardar en archivo
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedback_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Feedback de adaptación guardado en {feedback_file}")
        except Exception as e:
            self.logger.error(f"Error guardando feedback de adaptación: {e}")

    def _save_goal_adaptation_learning_results(self) -> None:
        """Guardar resultados de aprendizaje de adaptación de Goal en archivo JSON."""
        try:
            import json

            # Ruta del archivo de persistencia
            learning_file = os.path.join(self.data_dir, 'goal_adaptation_learning_results.json')

            # Crear directorio si no existe
            os.makedirs(os.path.dirname(learning_file), exist_ok=True)

            # Preparar datos para guardar
            learning_data = {
                "learning_results": self.knowledge_base.get("learning_results", []),
                "adaptation_strategies": self.knowledge_base.get("adaptation_strategies", {}),
                "last_updated": datetime.now().isoformat()
            }

            # Guardar en archivo
            with open(learning_file, 'w', encoding='utf-8') as f:
                json.dump(learning_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Resultados de aprendizaje guardados en {learning_file}")
        except Exception as e:
            self.logger.error(f"Error guardando resultados de aprendizaje: {e}")

    def _load_goal_adaptation_feedback(self) -> None:
        """Cargar feedback de adaptación de Goal desde archivo JSON."""
        try:
            import json

            # Ruta del archivo de persistencia
            feedback_file = os.path.join(self.data_dir, 'goal_adaptation_feedback.json')
            if os.path.exists(feedback_file):
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedback_data = json.load(f)
                    self.knowledge_base["goal_adaptation_feedback"] = feedback_data.get("goal_adaptation_feedback", [])
                    self.adaptation_history = feedback_data.get("adaptation_history", [])
                self.logger.info(f"Feedback de adaptación cargado desde {feedback_file}")
        except Exception as e:
            self.logger.error(f"Error cargando feedback de adaptación: {e}")

    def _load_goal_adaptation_learning_results(self) -> None:
        """Cargar resultados de aprendizaje de adaptación de Goal desde archivo JSON."""
        try:
            import json

            # Ruta del archivo de persistencia
            learning_file = os.path.join(self.data_dir, 'goal_adaptation_learning_results.json')
            if os.path.exists(learning_file):
                with open(learning_file, 'r', encoding='utf-8') as f:
                    learning_data = json.load(f)
                    self.knowledge_base["learning_results"] = learning_data.get("learning_results", [])
                    self.knowledge_base["adaptation_strategies"] = learning_data.get("adaptation_strategies", {})
                self.logger.info(f"Resultados de aprendizaje cargados desde {learning_file}")
        except Exception as e:
            self.logger.error(f"Error cargando resultados de aprendizaje: {e}")

    def _initialize_goal_adaptation_persistence(self) -> None:
        """Inicializar la persistencia de adaptación de Goal cargando datos existentes."""
        try:

            # Cargar feedback acumulado
            self._load_goal_adaptation_feedback()

            # Cargar resultados de aprendizaje
            self._load_goal_adaptation_learning_results()

            # Inicializar estructuras base si no existen
            if "goal_adaptation_feedback" not in self.knowledge_base:
                self.knowledge_base["goal_adaptation_feedback"] = []
            if "learning_results" not in self.knowledge_base:
                self.knowledge_base["learning_results"] = []
            if "adaptation_strategies" not in self.knowledge_base:
                self.knowledge_base["adaptation_strategies"] = {}
            self.logger.info("Persistencia de adaptación de Goal inicializada exitosamente")
        except Exception as e:
            self.logger.error(f"Error inicializando persistencia de adaptación: {e}")
