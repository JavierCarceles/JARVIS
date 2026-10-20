"""
Circuit Breaker Pattern Implementation
Provides resilience against cascading failures
"""

import time
import logging
import threading
from enum import Enum
from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, calls allowed
    OPEN = "open"         # Circuit is open, calls blocked
    HALF_OPEN = "half_open" # Testing if service is restored

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5        # Number of failures before opening circuit
    recovery_timeout: float = 30.0    # Time to wait before trying again
    expected_exception: tuple = (Exception,)  # Exceptions that count as failures
    timeout: float = 10.0             # Timeout for individual calls
    half_open_max_calls: int = 3      # Max calls in half-open state before deciding

class CircuitBreaker:
    """Circuit breaker implementation"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.logger.info(f"Circuit breaker {self.name} moving to HALF_OPEN state")
                else:
                    raise CircuitBreakerOpenError(f"Circuit {self.name} is OPEN")
        
        try:
            # Add timeout protection
            if self.config.timeout:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(func, *args, **kwargs)
                    result = future.result(timeout=self.config.timeout)
            else:
                result = func(*args, **kwargs)
            
            self._on_success()
            return result
            
        except self.config.expected_exception as e:
            self._on_failure()
            raise e
        except Exception as e:
            # Non-expected exceptions don't count as circuit breaker failures
            self.logger.warning(f"Non-expected exception in circuit {self.name}: {e}")
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset"""
        if self.last_failure_time is None:
            return True
        
        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure >= self.config.recovery_timeout
    
    def _on_success(self):
        """Handle successful call"""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.half_open_max_calls:
                    self._reset_circuit()
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                if self.failure_count > 0:
                    self.failure_count = 0
                    self.logger.debug(f"Reset failure count for circuit {self.name}")
    
    def _on_failure(self):
        """Handle failed call"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self._open_circuit()
            elif self.state == CircuitState.HALF_OPEN:
                self._open_circuit()
    
    def _open_circuit(self):
        """Open the circuit breaker"""
        self.state = CircuitState.OPEN
        self.logger.warning(f"Circuit breaker {self.name} opened after {self.failure_count} failures")
    
    def _reset_circuit(self):
        """Reset circuit breaker to closed state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.logger.info(f"Circuit breaker {self.name} reset to CLOSED state")
    
    def force_open(self):
        """Force circuit breaker to open state"""
        with self.lock:
            self.state = CircuitState.OPEN
            self.logger.warning(f"Circuit breaker {self.name} forced to OPEN state")
    
    def force_close(self):
        """Force circuit breaker to closed state"""
        with self.lock:
            self._reset_circuit()
            self.logger.info(f"Circuit breaker {self.name} forced to CLOSED state")
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state"""
        return self.state
    
    def get_stats(self) -> Dict:
        """Get circuit breaker statistics"""
        with self.lock:
            return {
                'state': self.state.value,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'last_failure_time': self.last_failure_time,
                'name': self.name
            }

class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit is open"""
    pass

class CircuitBreakerManager:
    """Manages multiple circuit breakers"""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.logger = logging.getLogger(__name__)
    
    def get_breaker(self, name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Get or create circuit breaker"""
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)
            self.logger.info(f"Created circuit breaker: {name}")
        return self.breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all circuit breakers"""
        return {name: breaker.get_stats() for name, breaker in self.breakers.items()}
    
    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self.breakers.values():
            breaker.force_close()
        self.logger.info("Reset all circuit breakers")
    
    def cleanup_stale(self, max_age_hours: int = 24):
        """Clean up stale circuit breakers"""
        current_time = time.time()
        stale_breakers = []
        
        for name, breaker in self.breakers.items():
            if (breaker.last_failure_time and 
                current_time - breaker.last_failure_time > max_age_hours * 3600):
                stale_breakers.append(name)
        
        for name in stale_breakers:
            del self.breakers[name]
            self.logger.info(f"Cleaned up stale circuit breaker: {name}")

# Decorator for easy circuit breaker usage
def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Decorator for circuit breaker protection"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            manager = CircuitBreakerManager()
            breaker = manager.get_breaker(name, config)
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator