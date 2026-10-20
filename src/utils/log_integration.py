"""
Sistema de integración de logs para Jarvis con múltiples fuentes y normalización.
"""

import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import asyncio
import queue
import re
from concurrent.futures import ThreadPoolExecutor
import gzip
import os


class LogSource(Enum):
    """Fuentes de logs soportadas."""

    APPLICATION = "application"
    SYSTEM = "system"
    DATABASE = "database"
    NETWORK = "network"
    SECURITY = "security"
    PERFORMANCE = "performance"
    THIRD_PARTY = "third_party"
    CUSTOM = "custom"


class LogFormat(Enum):
    """Formatos de logs soportados."""

    JSON = "json"
    TEXT = "text"
    CSV = "csv"
    SYSLOG = "syslog"
    NGINX = "nginx"
    APACHE = "apache"
    CUSTOM = "custom"


class IntegrationStatus(Enum):
    """Estados de integración."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class LogSourceConfig:
    """Configuración de una fuente de logs."""

    id: str
    name: str
    source_type: LogSource
    format: LogFormat
    connection_string: str
    enabled: bool = True
    batch_size: int = 100
    timeout: int = 30
    retry_count: int = 3
    tags: Dict[str, Any] = None
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data["source_type"] = self.source_type.value
        data["format"] = self.format.value
        return data


@dataclass
class LogIntegration:
    """Integración de logs."""

    id: str
    config: LogSourceConfig
    status: IntegrationStatus
    last_sync: datetime
    total_processed: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    performance_metrics: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data["status"] = self.status.value
        data["last_sync"] = self.last_sync.isoformat()
        return data


class LogNormalizer:
    """Normalizador de logs para diferentes formatos."""

    def __init__(self):
        self.parsers = {
            LogFormat.JSON: self._parse_json,
            LogFormat.TEXT: self._parse_text,
            LogFormat.CSV: self._parse_csv,
            LogFormat.SYSLOG: self._parse_syslog,
            LogFormat.NGINX: self._parse_nginx,
            LogFormat.APACHE: self._parse_apache,
            LogFormat.CUSTOM: self._parse_custom,
        }

        # Patrones regex comunes
        self.patterns = {
            "timestamp": re.compile(
                r"(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)"
            ),
            "ip_address": re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"),
            "level": re.compile(
                r"(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)", re.IGNORECASE
            ),
            "http_status": re.compile(r"(\d{3})"),
            "duration": re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s|sec|min|h|hour)"),
            "memory": re.compile(r"(\d+(?:\.\d+)?)\s*(KB|MB|GB)"),
            "error_code": re.compile(r"([A-Z0-9]{3,10})"),
        }

    def normalize_log(
        self, raw_log: str, format_type: LogFormat, source_config: LogSourceConfig
    ) -> Dict[str, Any]:
        """Normalizar un log a formato estándar."""
        try:
            # Obtener parser adecuado
            parser = self.parsers.get(format_type, self._parse_text)

            # Parsear log
            parsed_data = parser(raw_log)

            # Estandarizar campos
            normalized = self._standardize_fields(parsed_data, source_config)

            # Extraer información adicional
            normalized = self._extract_additional_info(normalized)

            return normalized

        except Exception as e:
            logging.error(f"Error normalizando log: {e}")
            return {
                "raw_log": raw_log,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "source": source_config.name,
            }

    def _parse_json(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato JSON."""
        try:
            data = json.loads(raw_log)
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido: {e}")

    def _parse_text(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato de texto libre."""
        # Intentar extraer información común usando regex
        parsed = {}

        # Extraer timestamp
        timestamp_match = self.patterns["timestamp"].search(raw_log)
        if timestamp_match:
            parsed["timestamp"] = timestamp_match.group(1)

        # Extraer nivel de log
        level_match = self.patterns["level"].search(raw_log)
        if level_match:
            parsed["level"] = level_match.group(1).upper()

        # Extraer IP
        ip_match = self.patterns["ip_address"].search(raw_log)
        if ip_match:
            parsed["ip_address"] = ip_match.group(1)

        # El mensaje completo
        parsed["message"] = raw_log.strip()

        return parsed

    def _parse_csv(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato CSV."""
        # Simple CSV parsing (assumes comma-separated)
        fields = raw_log.split(",")
        if len(fields) >= 2:
            return {
                "timestamp": fields[0].strip(),
                "level": fields[1].strip(),
                "message": ",".join(fields[2:]).strip(),
            }
        else:
            return {"message": raw_log.strip()}

    def _parse_syslog(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato syslog."""
        # Ejemplo: Jan 1 12:00:00 hostname service[pid]: message
        parts = raw_log.split()
        if len(parts) >= 4:
            return {
                "timestamp": f"{parts[0]} {parts[1]} {parts[2]}",
                "hostname": parts[3],
                "service": parts[4].split("[")[0],
                "pid": parts[4].split("[")[1].rstrip("]") if "[" in parts[4] else None,
                "message": " ".join(parts[5:]),
            }
        else:
            return {"message": raw_log.strip()}

    def _parse_nginx(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato Nginx."""
        # Ejemplo: 192.168.1.1 - - [01/Jan/2023:12:00:00 +0000] "GET /path HTTP/1.1" 200 1024 "referer" "user-agent"
        nginx_pattern = re.compile(
            r"(?P<ip>\d+\.\d+\.\d+\.\d+) - - \[(?P<timestamp>[^\]]+)\] "
            r'"(?P<method>\w+) (?P<path>[^\s]+) (?P<protocol>[^"]+)" '
            r'(?P<status>\d+) (?P<size>\d+) "(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)"'
        )

        match = nginx_pattern.match(raw_log)
        if match:
            return match.groupdict()
        else:
            return {"message": raw_log.strip()}

    def _parse_apache(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato Apache."""
        # Ejemplo: 192.168.1.1 - - [01/Jan/2023:12:00:00 +0000] "GET /path HTTP/1.1" 200 1024
        apache_pattern = re.compile(
            r"(?P<ip>\d+\.\d+\.\d+\.\d+) - - \[(?P<timestamp>[^\]]+)\] "
            r'"(?P<method>\w+) (?P<path>[^\s]+) (?P<protocol>[^"]+)" '
            r"(?P<status>\d+) (?P<size>\d+)"
        )

        match = apache_pattern.match(raw_log)
        if match:
            return match.groupdict()
        else:
            return {"message": raw_log.strip()}

    def _parse_custom(self, raw_log: str) -> Dict[str, Any]:
        """Parsear log en formato personalizado."""
        # Para formatos personalizados, se puede extender esta función
        return {"message": raw_log.strip()}

    def _standardize_fields(
        self, parsed_data: Dict[str, Any], source_config: LogSourceConfig
    ) -> Dict[str, Any]:
        """Estandarizar campos del log."""
        standardized = {
            "source": source_config.name,
            "source_type": source_config.source_type.value,
            "format": source_config.format.value,
            "received_at": datetime.now().isoformat(),
            "tags": source_config.tags or {},
        }

        # Mapear campos comunes
        field_mapping = {
            "timestamp": "timestamp",
            "time": "timestamp",
            "date": "timestamp",
            "level": "level",
            "severity": "level",
            "message": "message",
            "msg": "message",
            "logger": "logger",
            "component": "component",
            "service": "service",
            "ip": "ip_address",
            "client_ip": "ip_address",
            "status": "status_code",
            "http_status": "status_code",
            "method": "http_method",
            "user": "user",
            "username": "user",
            "session": "session_id",
            "trace": "trace_id",
            "span": "span_id",
        }

        # Aplicar mapeo
        for source_field, target_field in field_mapping.items():
            if source_field in parsed_data:
                standardized[target_field] = parsed_data[source_field]

        # Añadir campos no mapeados como metadata
        metadata = {}
        for key, value in parsed_data.items():
            if key not in field_mapping.values() and key not in standardized:
                metadata[key] = value

        if metadata:
            standardized["metadata"] = metadata

        return standardized

    def _extract_additional_info(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        """Extraer información adicional usando regex."""
        # Extraer códigos de error
        if "message" in normalized:
            error_matches = self.patterns["error_code"].findall(normalized["message"])
            if error_matches:
                normalized["error_codes"] = error_matches

        # Extraer duraciones
        if "message" in normalized:
            duration_matches = self.patterns["duration"].findall(normalized["message"])
            if duration_matches:
                durations = []
                for match in duration_matches:
                    value = float(match[0])
                    unit = match[1].lower()

                    # Convertir a milisegundos
                    if unit == "s" or unit == "sec":
                        value *= 1000
                    elif unit == "min":
                        value *= 60 * 1000
                    elif unit == "h" or unit == "hour":
                        value *= 60 * 60 * 1000

                    durations.append({"value": value, "unit": "ms"})

                normalized["durations"] = durations

        # Normalizar nivel de log
        if "level" in normalized:
            level = normalized["level"].upper()
            if level in ["WARN", "WARNING"]:
                normalized["level"] = "WARNING"
            elif level in ["FATAL"]:
                normalized["level"] = "CRITICAL"

        return normalized


class LogCollector:
    """Colector de logs desde múltiples fuentes."""

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.normalizer = LogNormalizer()
        self.integrations = {}
        self.is_collecting = False
        self.collection_thread = None
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.log_queue = queue.Queue(maxsize=10000)
        self.lock = threading.Lock()

    def add_integration(self, integration: LogIntegration) -> None:
        """Añadir integración de logs."""
        with self.lock:
            self.integrations[integration.config.id] = integration

    def remove_integration(self, integration_id: str) -> None:
        """Remover integración de logs."""
        with self.lock:
            if integration_id in self.integrations:
                del self.integrations[integration_id]

    def start_collection(self) -> None:
        """Iniciar recolección de logs."""
        if self.is_collecting:
            return

        self.is_collecting = True

        # Iniciar hilo principal de recolección
        self.collection_thread = threading.Thread(
            target=self._collection_loop, daemon=True
        )
        self.collection_thread.start()

        # Iniciar hilo de procesamiento
        processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        processing_thread.start()

    def stop_collection(self) -> None:
        """Detener recolección de logs."""
        self.is_collecting = False

        if self.collection_thread:
            self.collection_thread.join(timeout=5)

        self.executor.shutdown(wait=True)

    def _collection_loop(self) -> None:
        """Bucle principal de recolección."""
        while self.is_collecting:
            try:
                # Procesar cada integración activa
                for integration_id, integration in self.integrations.items():
                    if integration.status == IntegrationStatus.ACTIVE:
                        self._collect_from_integration(integration)

                time.sleep(1)  # Revisar cada segundo

            except Exception as e:
                logging.error(f"Error en bucle de recolección: {e}")
                time.sleep(5)

    def _collect_from_integration(self, integration: LogIntegration) -> None:
        """Recolectar logs desde una integración específica."""
        try:
            # Aquí se implementaría la lógica específica para cada tipo de fuente
            # Por ahora, simulamos la recolección

            # Simular obtención de logs
            raw_logs = self._simulate_log_fetch(integration.config)

            # Procesar cada log
            for raw_log in raw_logs:
                # Normalizar log
                normalized = self.normalizer.normalize_log(
                    raw_log, integration.config.format, integration.config
                )

                # Añadir a cola de procesamiento
                try:
                    self.log_queue.put(
                        {
                            "integration_id": integration.config.id,
                            "log_data": normalized,
                            "timestamp": datetime.now(),
                        }
                    )
                except queue.Full:
                    logging.warning("Cola de logs llena, descartando log")

            # Actualizar métricas de la integración
            integration.total_processed += len(raw_logs)
            integration.last_sync = datetime.now()

        except Exception as e:
            logging.error(f"Error recolectando desde {integration.config.name}: {e}")
            integration.status = IntegrationStatus.ERROR
            integration.last_error = str(e)

    def _simulate_log_fetch(self, config: LogSourceConfig) -> List[str]:
        """Simular obtención de logs (para demostración)."""
        # En un sistema real, esto se conectaría a la fuente real
        time.sleep(0.1)  # Simular latencia

        # Generar logs de ejemplo según el tipo de fuente
        logs = []

        if config.source_type == LogSource.APPLICATION:
            logs.extend(
                [
                    '{"timestamp": "2023-01-01T12:00:00Z", "level": "INFO", "message": "Application started successfully"}',
                    '{"timestamp": "2023-01-01T12:01:00Z", "level": "WARNING", "message": "High memory usage detected"}',
                    '{"timestamp": "2023-01-01T12:02:00Z", "level": "ERROR", "message": "Database connection failed"}',
                ]
            )
        elif config.source_type == LogSource.SYSTEM:
            logs.extend(
                [
                    "Jan 1 12:00:00 hostname kernel: CPU usage: 45%",
                    "Jan 1 12:01:00 hostname systemd: Started service xyz",
                    "Jan 1 12:02:00 hostname kernel: Memory usage: 78%",
                ]
            )
        elif config.source_type == LogSource.NETWORK:
            logs.extend(
                [
                    '192.168.1.1 - - [01/Jan/2023:12:00:00 +0000] "GET /api/users HTTP/1.1" 200 1024',
                    '192.168.1.2 - - [01/Jan/2023:12:01:00 +0000] "POST /api/login HTTP/1.1" 401 256',
                    '192.168.1.3 - - [01/Jan/2023:12:02:00 +0000] "GET /api/data HTTP/1.1" 500 512',
                ]
            )

        return logs

    def _processing_loop(self) -> None:
        """Bucle de procesamiento de logs."""
        while self.is_collecting:
            try:
                # Obtener log de la cola
                log_item = self.log_queue.get(timeout=1)
                if log_item:
                    # Procesar log en hilo separado
                    self.executor.submit(self._process_log, log_item)
                    self.log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error en bucle de procesamiento: {e}")

    def _process_log(self, log_item: Dict[str, Any]) -> None:
        """Procesar un log individual."""
        try:
            # Aquí se procesaría el log (almacenamiento, análisis, etc.)
            # Por ahora, solo lo registramos

            integration_id = log_item["integration_id"]
            log_data = log_item["log_data"]
            timestamp = log_item["timestamp"]

            # Actualizar métricas de la integración
            with self.lock:
                if integration_id in self.integrations:
                    integration = self.integrations[integration_id]
                    integration.total_processed += 1

                    # Aquí se almacenaría el log en la base de datos o sistema de destino
                    logging.info(
                        f"Procesado log de {integration.config.name}: {log_data.get('message', 'N/A')}"
                    )

        except Exception as e:
            logging.error(f"Error procesando log: {e}")

    def get_integration_status(self) -> Dict[str, Any]:
        """Obtener estado de todas las integraciones."""
        with self.lock:
            status = {}
            for integration_id, integration in self.integrations.items():
                status[integration_id] = integration.to_dict()
            return status

    def get_collection_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de recolección."""
        with self.lock:
            total_processed = sum(
                integration.total_processed
                for integration in self.integrations.values()
            )
            total_errors = sum(
                integration.error_count for integration in self.integrations.values()
            )

            return {
                "total_integrations": len(self.integrations),
                "active_integrations": len(
                    [
                        i
                        for i in self.integrations.values()
                        if i.status == IntegrationStatus.ACTIVE
                    ]
                ),
                "total_processed": total_processed,
                "total_errors": total_errors,
                "queue_size": self.log_queue.qsize(),
                "is_collecting": self.is_collecting,
            }


class LogTransformer:
    """Transformador de logs para diferentes destinos."""

    def __init__(self):
        self.destinations = {}
        self.transform_rules = []

    def add_destination(self, name: str, config: Dict[str, Any]) -> None:
        """Añadir destino de logs."""
        self.destinations[name] = config

    def add_transform_rule(self, rule: Dict[str, Any]) -> None:
        """Añadir regla de transformación."""
        self.transform_rules.append(rule)

    def transform_log(
        self, log_data: Dict[str, Any], destination: str
    ) -> Dict[str, Any]:
        """Transformar log para un destino específico."""
        if destination not in self.destinations:
            raise ValueError(f"Destino no encontrado: {destination}")

        config = self.destinations[destination]

        # Aplicar reglas de transformación
        for rule in self.transform_rules:
            if rule.get("destination") == destination:
                log_data = self._apply_transform_rule(log_data, rule)

        # Aplicar configuración específica del destino
        if "field_mapping" in config:
            log_data = self._apply_field_mapping(log_data, config["field_mapping"])

        return log_data

    def _apply_transform_rule(
        self, log_data: Dict[str, Any], rule: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aplicar una regla de transformación."""
        # Ejemplo de transformación: añadir campos, renombrar, etc.
        if "add_fields" in rule:
            for field, value in rule["add_fields"].items():
                log_data[field] = value

        if "rename_fields" in rule:
            for old_field, new_field in rule["rename_fields"].items():
                if old_field in log_data:
                    log_data[new_field] = log_data.pop(old_field)

        if "remove_fields" in rule:
            for field in rule["remove_fields"]:
                log_data.pop(field, None)

        return log_data

    def _apply_field_mapping(
        self, log_data: Dict[str, Any], mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """Aplicar mapeo de campos."""
        mapped_data = {}

        for source_field, target_field in mapping.items():
            if source_field in log_data:
                mapped_data[target_field] = log_data[source_field]

        # Añadir campos no mapeados
        for key, value in log_data.items():
            if key not in mapping:
                mapped_data[key] = value

        return mapped_data


class LogIntegrationSystem:
    """Sistema completo de integración de logs."""

    def __init__(self, db_path: str = "logs/integration.db"):
        self.db_path = Path(db_path)
        self.collector = LogCollector()
        self.transformer = LogTransformer()
        self.is_running = False

        # Crear base de datos
        self._create_database()

    def _create_database(self) -> None:
        """Crear base de datos para integración de logs."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Tabla de integraciones
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS integrations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    format TEXT NOT NULL,
                    connection_string TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    batch_size INTEGER DEFAULT 100,
                    timeout INTEGER DEFAULT 30,
                    retry_count INTEGER DEFAULT 3,
                    tags TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    last_sync TEXT,
                    total_processed INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    status TEXT DEFAULT 'inactive'
                )
            """)

            # Tabla de logs procesados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    integration_id TEXT NOT NULL,
                    raw_log TEXT NOT NULL,
                    normalized_log TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    status TEXT DEFAULT 'success',
                    error_message TEXT,
                    FOREIGN KEY (integration_id) REFERENCES integrations (id)
                )
            """)

            conn.commit()

    def add_log_source(self, config: LogSourceConfig) -> None:
        """Añadir fuente de logs."""
        # Crear integración
        integration = LogIntegration(
            id=config.id,
            config=config,
            status=IntegrationStatus.ACTIVE
            if config.enabled
            else IntegrationStatus.INACTIVE,
            last_sync=datetime.now() if config.enabled else None,
        )

        # Añadir al colector
        self.collector.add_integration(integration)

        # Guardar en base de datos
        self._save_integration(integration)

    def remove_log_source(self, integration_id: str) -> None:
        """Remover fuente de logs."""
        self.collector.remove_integration(integration_id)

        # Eliminar de base de datos
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
            conn.commit()

    def start(self) -> None:
        """Iniciar sistema de integración."""
        if self.is_running:
            return

        self.is_running = True
        self.collector.start_collection()

        logging.info("Sistema de integración de logs iniciado")

    def stop(self) -> None:
        """Detener sistema de integración."""
        self.is_running = False
        self.collector.stop_collection()

        logging.info("Sistema de integración de logs detenido")

    def get_system_status(self) -> Dict[str, Any]:
        """Obtener estado del sistema."""
        return {
            "is_running": self.is_running,
            "integrations": self.collector.get_integration_status(),
            "collection_metrics": self.collector.get_collection_metrics(),
            "destinations": list(self.transformer.destinations.keys()),
        }

    def _save_integration(self, integration: LogIntegration) -> None:
        """Guardar integración en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO integrations (
                    id, name, source_type, format, connection_string, enabled,
                    batch_size, timeout, retry_count, tags, metadata, created_at,
                    last_sync, total_processed, error_count, last_error, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    integration.config.id,
                    integration.config.name,
                    integration.config.source_type.value,
                    integration.config.format.value,
                    integration.config.connection_string,
                    integration.config.enabled,
                    integration.config.batch_size,
                    integration.config.timeout,
                    integration.config.retry_count,
                    json.dumps(integration.config.tags or {}),
                    json.dumps(integration.config.metadata or {}),
                    datetime.now().isoformat(),
                    integration.last_sync.isoformat()
                    if integration.last_sync
                    else None,
                    integration.total_processed,
                    integration.error_count,
                    integration.last_error,
                    integration.status.value,
                ),
            )
            conn.commit()


class LogIntegrator:
    """Wrapper para LogIntegrationSystem que proporciona la interfaz esperada."""
    
    def __init__(self, db_path: str = "logs/integration.db"):
        self.system = LogIntegrationSystem(db_path)
    
    def add_log_source(self, config: LogSourceConfig) -> None:
        """Añadir fuente de logs."""
        self.system.add_log_source(config)
    
    def remove_log_source(self, integration_id: str) -> None:
        """Remover fuente de logs."""
        self.system.remove_log_source(integration_id)
    
    def start(self) -> None:
        """Iniciar sistema de integración."""
        self.system.start()
    
    def stop(self) -> None:
        """Detener sistema de integración."""
        self.system.stop()
    
    def get_system_status(self) -> Dict[str, Any]:
        """Obtener estado del sistema."""
        return self.system.get_system_status()


# Instancia global del sistema de integración
log_integration = LogIntegrationSystem()
log_integrator = LogIntegrator()
