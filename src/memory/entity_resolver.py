# src/memory/entity_resolver.py
"""
Sistema de resolución avanzada de entidades para FASE 5 - DOMAIN MEMORY.

Implementa:
- Resolución de entidades con contexto
- Manejo de ambigüedades
- Búsqueda semántica
- Integración con HTN y Goals
"""

import re
import difflib
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import json

from src.utils.logger import get_logger
from src.memory.storage import MemoryManager, Entity, MemoryType, UserPreference, EntityAttribute
from src.hands.planner.node import NodeType

logger = get_logger(__name__)


@dataclass
class EntityResolutionResult:
    """Resultado de la resolución de entidad."""
    entity: Entity
    confidence: float
    resolution_method: str
    alternatives: List[Entity]
    context_used: Dict[str, Any]
    timestamp: str


@dataclass
class ResolutionContext:
    """Contexto para resolución de entidades."""
    conversation_history: List[Dict[str, Any]]
    current_intent: Optional[str]
    recent_entities: List[str]
    user_preferences: Dict[str, Any]
    session_info: Dict[str, Any]


class EntityResolver:
    """Sistema avanzado de resolución de entidades."""
    
    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self.memory_manager = memory_manager or MemoryManager()
        self.resolution_threshold = 0.7
        self.max_alternatives = 3
        self.default_user_id = "default_user"
        
        # Patrones para diferentes tipos de entidades
        self.patterns = {
            'streamer': re.compile(r'@?[\w_]+', re.IGNORECASE),
            'application': re.compile(r'[\w\s]+(?:app|program|software)', re.IGNORECASE),
            'platform': re.compile(r'(twitch|youtube|tiktok|twitter|instagram)', re.IGNORECASE),
            'website': re.compile(r'https?://[\w\.\-]+', re.IGNORECASE)
        }
        
        # Expresiones regulares para detección y parseo de URLs
        self.url_patterns = {
            'full_url': re.compile(r'https?://[^\s<>"]+\.[^\s<>"]+[^\s<>"]*'),
            'domain': re.compile(r'^(?:https?:\/\/)?(?:www\.)?([^\/?:]+)'),
            'twitch_channel': re.compile(r'https?:\/\/(?:www\.)?twitch\.tv\/([^\/\?\s]+)'),
            'youtube_channel': re.compile(r'https?:\/\/(?:www\.)?youtube\.com(?:\/(?:c\/|channel\/|user\/))?([^\/\?\s]+)'),
            'generic_path': re.compile(r'\/([^\/\?\s]+)')
        }
    
    def resolve_entity(self, 
                      entity_reference: str, 
                      context: Optional[ResolutionContext] = None,
                      entity_type: Optional[str] = None) -> EntityResolutionResult:
        """
        Resuelve una referencia de entidad a una entidad específica.
        
        Args:
            entity_reference: Referencia a la entidad (nombre, alias, URL, etc.)
            context: Contexto de resolución
            entity_type: Tipo específico de entidad (opcional)
            
        Returns:
            EntityResolutionResult con la entidad resuelta y alternativas
        """
        logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
        
        # Normalizar la referencia
        normalized_ref = self._normalize_reference(entity_reference)
        
        # 1. Búsqueda exacta
        exact_matches = self._find_exact_matches(normalized_ref, entity_type)
        
        if exact_matches:
            return self._select_best_match(exact_matches, normalized_ref, context or ResolutionContext([], None, [], {}, {}))
        
        # 2. Búsqueda por similitud
        fuzzy_matches = self._find_fuzzy_matches(normalized_ref, entity_type)
        
        if fuzzy_matches:
            return self._select_best_match(fuzzy_matches, normalized_ref, context or ResolutionContext([], None, [], {}, {}))
        
        # 3. Búsqueda por propiedades
        property_matches = self._find_by_properties(normalized_ref, entity_type)
        
        if property_matches:
            return self._select_best_match(property_matches, normalized_ref, context or ResolutionContext([], None, [], {}, {}))
        
        # 4. Si no hay matches, crear entidad temporal
        return self._create_temporary_entity(normalized_ref, entity_type)
    
    def resolve_entities_batch(self, 
                              entity_references: List[str],
                              context: Optional[ResolutionContext] = None) -> List[EntityResolutionResult]:
        """
        Resuelve múltiples entidades en lote.
        """
        results = []
        context = context or ResolutionContext([], None, [], {}, {})
        
        # Actualizar entidades recientes en el contexto
        context.recent_entities = []
        
        for ref in entity_references:
            result = self.resolve_entity(ref, context)
            results.append(result)
            context.recent_entities.append(result.entity.id)
        
        return results
    
    def _normalize_reference(self, reference: str) -> str:
        """Normaliza una referencia de entidad."""
        if not reference:
            return ""
        
        # Eliminar espacios extra
        normalized = re.sub(r'\s+', ' ', reference.strip())
        
        # Convertir a minúsculas para comparación
        normalized = normalized.lower()
        
        # Eliminar caracteres especiales comunes (manteniendo @ para usernames)
        normalized = re.sub(r'[^\w\s\-@]', '', normalized)
        
        return normalized
    
    def _find_exact_matches(self, reference: str, entity_type: Optional[str]) -> List[Entity]:
        """Busca coincidencias exactas."""
        matches = []
        
        # Buscar por nombre exacto
        try:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            logger._print_log("debug", f"Buscando coincidencias exactas para: {reference}", "entity_resolver.py", "method", 157)
            logger._print_log("debug", "Buscando entidades por nombre exacto", "entity_resolver.py", "method", 158)
            entities = self.memory_manager.find_entities(reference, entity_type)
            logger._print_log("debug", f"Encontradas {len(entities)} entidades por nombre exacto", "entity_resolver.py", "method", 160)
            matches.extend(entities)
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            import traceback
            traceback.print_exc()
        
        # Buscar por aliases
        if not matches:
            all_entities = self.memory_manager.find_entities(reference) if not entity_type else self.memory_manager.get_entities_by_type(entity_type)
            for entity in all_entities:
                if reference in [alias.lower() for alias in entity.aliases]:
                    matches.append(entity)
        
        # Buscar por tags
        if not matches:
            all_entities = self.memory_manager.find_entities(reference) if not entity_type else self.memory_manager.get_entities_by_type(entity_type)
            for entity in all_entities:
                if reference in [tag.lower() for tag in entity.tags]:
                    matches.append(entity)
        
        return matches
    
    def _find_fuzzy_matches(self, reference: str, entity_type: Optional[str]) -> List[Entity]:
        """Busca coincidencias difusas."""
        matches = []
        all_entities = self.memory_manager.find_entities() if not entity_type else self.memory_manager.get_entities_by_type(entity_type)
        
        for entity in all_entities:
            # Calcular similitud del nombre
            name_similarity = difflib.SequenceMatcher(None, reference, entity.name.lower()).ratio()
            
            # Calcular similitud de aliases
            max_alias_similarity = 0
            for alias in entity.aliases:
                alias_similarity = difflib.SequenceMatcher(None, reference, alias.lower()).ratio()
                max_alias_similarity = max(max_alias_similarity, alias_similarity)
            
            # Calcular similitud de tags
            max_tag_similarity = 0
            for tag in entity.tags:
                tag_similarity = difflib.SequenceMatcher(None, reference, tag.lower()).ratio()
                max_tag_similarity = max(max_tag_similarity, tag_similarity)
            
            # Tomar la mejor similitud
            best_similarity = max(name_similarity, max_alias_similarity, max_tag_similarity)
            
            if best_similarity >= self.resolution_threshold:
                entity.confidence = best_similarity
                matches.append(entity)
        
        # Ordenar por similitud
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches[:self.max_alternatives]
    
    def _find_by_properties(self, reference: str, entity_type: Optional[str]) -> List[Entity]:
        """Busca entidades por propiedades."""
        matches = []
        
        # Buscar por URL
        url_matches = self.memory_manager.find_entities_by_property('url', reference)
        matches.extend(url_matches)
        
        # Buscar por otras propiedades comunes
        common_properties = ['username', 'channel', 'domain']
        for prop in common_properties:
            prop_matches = self.memory_manager.find_entities_by_property(prop, reference)
            matches.extend(prop_matches)
        
        # Eliminar duplicados
        unique_matches = []
        seen_ids = set()
        for entity in matches:
            if entity.id not in seen_ids:
                unique_matches.append(entity)
                seen_ids.add(entity.id)
        
        return unique_matches
    
    def _select_best_match(self, 
                          matches: List[Entity], 
                          reference: str, 
                          context: ResolutionContext) -> EntityResolutionResult:
        """Selecciona la mejor coincidencia basada en contexto."""
        if not matches:
            return self._create_temporary_entity(reference, None)
        
        # Si solo hay una coincidencia, usarla
        if len(matches) == 1:
            return EntityResolutionResult(
                entity=matches[0],
                confidence=1.0,
                resolution_method="exact_match",
                alternatives=[],
                context_used=context.__dict__,
                timestamp=datetime.now().isoformat()
            )
        
        # Si hay múltiples coincidencias, usar contexto para desambiguar
        best_entity = self._disambiguate_with_context(matches, reference, context)
        
        # Obtener alternativas
        alternatives = [m for m in matches if m.id != best_entity.id][:self.max_alternatives-1]
        
        return EntityResolutionResult(
            entity=best_entity,
            confidence=best_entity.confidence,
            resolution_method="context_disambiguation",
            alternatives=alternatives,
            context_used=context.__dict__,
            timestamp=datetime.now().isoformat()
        )
    
    def _disambiguate_with_context(self, 
                                 matches: List[Entity], 
                                 reference: str, 
                                 context: ResolutionContext) -> Entity:
        """Usa contexto para desambiguar entre múltiples entidades."""
        
        # 1. Verificar preferencias aprendidas del usuario
        user_preferences = self.memory_manager.get_user_preferences("default", "entity_preferred")
        preferred_entities = [pref.preference_value for pref in user_preferences 
                            if pref.confidence > 0.7]
        
        if preferred_entities:
            for entity in matches:
                if entity.id in preferred_entities:
                    logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
                    # Aprender de esta selección exitosa
                    self.memory_manager.learn_user_preference(self.default_user_id, entity.id, "resolution", True)
                    return entity
        
        # 2. Verificar preferencias del usuario en contexto actual
        if context.user_preferences:
            for entity in matches:
                if entity.id in context.user_preferences.get('preferred_entities', []):
                    logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
                    return entity
        
        # 3. Verificar entidades recientes
        if context.recent_entities:
            for entity in matches:
                if entity.id in context.recent_entities:
                    logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
                    # Aprender de la selección reciente
                    self.memory_manager.learn_user_preference(self.default_user_id, entity.id, "recent_usage", True)
                    return entity
        
        # 4. Verificar historial conversacional
        if context.conversation_history:
            # Buscar menciones recientes en el historial
            recent_mentions = {}
            for entry in context.conversation_history[-5:]:  # Últimas 5 entradas
                if 'entities' in entry:
                    for entity_id in entry['entities']:
                        if entity_id in [m.id for m in matches]:
                            recent_mentions[entity_id] = recent_mentions.get(entity_id, 0) + 1
            
            if recent_mentions:
                # Seleccionar la más mencionada
                most_mentioned = max(recent_mentions.items(), key=lambda x: x[1])
                for entity in matches:
                    if entity.id == most_mentioned[0]:
                        logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
                        # Aprender de la mención frecuente
                        self.memory_manager.learn_user_preference(self.default_user_id, entity.id, "frequent_mention", True)
                        return entity
        
        # 5. Verificar atributos extendidos de preferencia
        for entity in matches:
            # Buscar atributos de preferencia para esta entidad
            preference_attrs = self.memory_manager.get_entity_attributes(entity.id)
            for attr in preference_attrs:
                if attr.attribute_name == "user_preference_score":
                    if float(attr.attribute_value) > 0.8:
                        logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
                        return entity
        
        # 6. Si no hay contexto, seleccionar por confianza
        best_match = max(matches, key=lambda x: x.confidence)
        logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
        
        # Aprender de esta selección por confianza
        self.memory_manager.learn_user_preference(self.default_user_id, best_match.id, "confidence_selection", True)
        
        return best_match
    
    def _create_temporary_entity(self, reference: str, entity_type: Optional[str]) -> EntityResolutionResult:
        """Crea una entidad temporal para referencias no encontradas."""
        temp_entity = Entity(
            id=f"temp_{datetime.now().timestamp()}",
            type=entity_type or "unknown",
            name=reference,
            properties={"reference": reference},
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            aliases=[reference],
            confidence=0.5,
            tags=["temporary", "unresolved"]
        )
        
        logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
        
        return EntityResolutionResult(
            entity=temp_entity,
            confidence=0.5,
            resolution_method="temporary_creation",
            alternatives=[],
            context_used={},
            timestamp=datetime.now().isoformat()
        )
    
    def get_entity_suggestions(self, 
                              partial_text: str, 
                              entity_type: Optional[str] = None,
                              limit: int = 5) -> List[Entity]:
        """
        Obtiene sugerencias de entidades basadas en texto parcial.
        """
        suggestions = []
        
        # Buscar entidades que coincidan con el texto parcial
        all_entities = self.memory_manager.find_entities() if not entity_type else self.memory_manager.get_entities_by_type(entity_type)
        
        for entity in all_entities:
            # Verificar si el texto parcial está en el nombre, aliases o tags
            partial_lower = partial_text.lower()
            
            if (partial_lower in entity.name.lower() or
                any(partial_lower in alias.lower() for alias in entity.aliases) or
                any(partial_lower in tag.lower() for tag in entity.tags)):
                
                suggestions.append(entity)
                
                if len(suggestions) >= limit:
                    break
        
        return suggestions
    
    def resolve_url(self, 
                   url_input: str, 
                   context: Optional[ResolutionContext] = None) -> EntityResolutionResult:
        """
        Resuelve una URL a una entidad específica del sistema.
        
        Args:
            url_input: URL completa o parcial del usuario
            context: Contexto de resolución
            
        Returns:
            EntityResolutionResult con la entidad asociada a la URL
        """
        logger._print_log("info", f"Resolviendo URL: {url_input}", "entity_resolver.py", "method", 412)
        
        # Normalizar la URL
        normalized_url = self._normalize_url(url_input)
        
        # 1. Intentar parsear y extraer información de la URL
        url_info = self._parse_url(normalized_url)
        
        # 2. Buscar entidades por URL exacta
        if url_info.get('full_url'):
            url_matches = self.memory_manager.find_entities_by_property('url', url_info['full_url'])
            if url_matches:
                return self._select_best_match(url_matches, normalized_url, context or ResolutionContext([], None, [], {}, {}))
        
        # 3. Buscar por dominio
        if url_info.get('domain'):
            domain_matches = self.memory_manager.find_entities_by_property('domain', url_info['domain'])
            if domain_matches:
                return self._select_best_match(domain_matches, normalized_url, context or ResolutionContext([], None, [], {}, {}))
        
        # 4. Buscar por plataforma específica
        if url_info.get('platform'):
            platform_matches = self.memory_manager.find_entities_by_type(url_info['platform'])
            if platform_matches:
                return self._select_best_match(platform_matches, normalized_url, context or ResolutionContext([], None, [], {}, {}))
        
        # 5. Buscar por nombre de canal/usuario extraído
        if url_info.get('channel_name'):
            channel_matches = self.memory_manager.find_entities(url_info['channel_name'])
            if channel_matches:
                return self._select_best_match(channel_matches, normalized_url, context or ResolutionContext([], None, [], {}, {}))
        
        # 6. Si no hay coincidencias, crear entidad temporal con información de URL
        return self._create_entity_from_url(url_info, normalized_url, context or ResolutionContext([], None, [], {}, {}))
    
    def extract_urls_from_text(self, text: str) -> List[str]:
        """
        Extrae todas las URLs de un texto.
        
        Args:
            text: Texto que puede contener URLs
            
        Returns:
            Lista de URLs encontradas
        """
        urls = []
        
        # Buscar URLs completas con expresión más conservadora
        full_url_pattern = re.compile(r'https?://[^\s<>"]+\.[^\s<>"]+[^\s<>"]*')
        full_url_matches = full_url_pattern.findall(text)
        
        for match in full_url_matches:
            # Limpiar la URL de caracteres no deseados
            clean_url = match.rstrip('.,;:!?')
            if clean_url and clean_url not in urls:
                urls.append(clean_url)
        
        # Buscar dominios sin protocolo (siempre, no solo si no hay URLs)
        domain_pattern = re.compile(r'\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
        domain_matches = domain_pattern.findall(text)
        
        for domain in domain_matches:
            # Verificar que no es parte de una URL ya encontrada
            if not any(domain in url for url in urls):
                clean_domain = domain.rstrip('.,;:!?')
                if clean_domain and '.' in clean_domain:
                    full_domain_url = f"https://{clean_domain}"
                    if full_domain_url not in urls:
                        urls.append(full_domain_url)
        
        return urls
    
    def _normalize_url(self, url_input: str) -> str:
        """
        Normaliza una URL de entrada.
        
        Args:
            url_input: URL cruda del usuario
            
        Returns:
            URL normalizada
        """
        if not url_input:
            return ""
        
        # Si no tiene protocolo, añadir https://
        if not url_input.startswith(('http://', 'https://')):
            if '.' in url_input and not url_input.startswith('www.'):
                url_input = f"https://{url_input}"
            else:
                url_input = f"https://{url_input}"
        
        # Eliminar caracteres finales no deseados
        url_input = url_input.rstrip('.,;:!?')
        
        return url_input
    
    def _parse_url(self, url: str) -> Dict[str, Any]:
        """
        Parsea una URL y extrae información estructurada.
        
        Args:
            url: URL normalizada
            
        Returns:
            Diccionario con información extraída
        """
        url_info = {
            'full_url': url,
            'domain': '',
            'platform': '',
            'channel_name': '',
            'path': '',
            'params': {}
        }
        
        try:
            parsed = urlparse(url)
            
            # Extraer dominio principal
            domain = parsed.netloc.replace('www.', '')
            url_info['domain'] = domain
            
            # Determinar plataforma basada en dominio
            if 'twitch.tv' in domain:
                url_info['platform'] = 'streamer'
                # Extraer nombre de canal
                channel_match = self.url_patterns['twitch_channel'].search(url)
                if channel_match:
                    url_info['channel_name'] = channel_match.group(1)
            elif 'youtube.com' in domain or 'youtu.be' in domain:
                url_info['platform'] = 'application'
                # Extraer ID de canal/usuario
                channel_match = self.url_patterns['youtube_channel'].search(url)
                if channel_match:
                    url_info['channel_name'] = channel_match.group(1)
            elif 'github.com' in domain:
                url_info['platform'] = 'application'
            elif 'spotify.com' in domain:
                url_info['platform'] = 'application'
            
            # Extraer path principal
            if parsed.path:
                path_parts = [part for part in parsed.path.split('/') if part]
                if path_parts:
                    url_info['path'] = path_parts[0]
            
            # Extraer parámetros
            if parsed.query:
                url_info['params'] = parse_qs(parsed.query)
                
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
        
        return url_info
    
    def _create_entity_from_url(self, url_info: Dict[str, Any], url: str, context: ResolutionContext) -> EntityResolutionResult:
        """
        Crea una entidad basada en información de URL.
        
        Args:
            url_info: Información parseada de la URL
            url: URL original
            context: Contexto de resolución
            
        Returns:
            EntityResolutionResult con la entidad creada
        """
        # Determinar tipo de entidad basado en plataforma
        platform = url_info.get('platform', '')
        if platform:
            entity_type = platform
        else:
            entity_type = 'unknown'
        
        # Crear propiedades básicas
        properties = {
            'url': url_info['full_url'],
            'domain': url_info['domain'],
            'source_url': url
        }
        
        # Añadir información específica de plataforma
        if entity_type == 'streamer':
            properties['platform'] = 'twitch'
            if url_info.get('channel_name'):
                properties['channel'] = url_info['channel_name']
                # Usar nombre de canal como nombre principal
                entity_name = url_info['channel_name']
            else:
                entity_name = url_info['domain'].replace('.twitch.tv', '')
        elif entity_type == 'application':
            properties['platform'] = 'web'
            entity_name = url_info['domain'].replace('.com', '').replace('.www', '')
        else:
            entity_name = url_info['domain']
        
        # Crear entidad temporal
        temp_entity = Entity(
            id=f"url_{datetime.now().timestamp()}",
            type=entity_type,
            name=entity_name,
            properties=properties,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            aliases=[entity_name, url_info['domain']],
            confidence=0.6,
            tags=["url_resolved", "temporary"]
        )
        
        logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
        logger._print_log("info", "_create_entity_from_url", "entity_resolver.py", "method", 622)
        
        return EntityResolutionResult(
            entity=temp_entity,
            confidence=0.6,
            resolution_method="url_parsing",
            alternatives=[],
            context_used=context.__dict__,
            timestamp=datetime.now().isoformat()
        )
    
    def get_url_suggestions(self, 
                          partial_url: str, 
                          limit: int = 5) -> List[Entity]:
        """
        Obtiene sugerencias de entidades basadas en URL parcial.
        
        Args:
            partial_url: URL parcial para buscar coincidencias
            limit: Número máximo de sugerencias
            
        Returns:
            Lista de entidades sugeridas
        """
        suggestions = []
        
        # Buscar por dominio parcial
        all_entities = self.memory_manager.find_entities()
        
        for entity in all_entities:
            # Verificar si el dominio parcial está en las propiedades de la entidad
            if 'domain' in entity.properties:
                domain = entity.properties['domain']
                if partial_url.lower() in domain.lower():
                    suggestions.append(entity)
            
            # Verificar si la URL parcial está en las propiedades
            if 'url' in entity.properties:
                url = entity.properties['url']
                if partial_url.lower() in url.lower():
                    suggestions.append(entity)
            
            if len(suggestions) >= limit:
                break
        
        return suggestions
    
    def learn_from_resolution(self, 
                            result: EntityResolutionResult, 
                            user_feedback: Optional[bool] = None) -> None:
        """
        Aprende de los resultados de resolución para mejorar futuras resoluciones.
        """
        if user_feedback is not None:
            # Ajustar confianza según feedback
            if user_feedback:
                result.entity.confidence = min(1.0, result.entity.confidence + 0.1)
                # Aprender preferencia positiva
                self.memory_manager.learn_user_preference(self.default_user_id, result.entity.id, "user_feedback", True)
            else:
                result.entity.confidence = max(0.1, result.entity.confidence - 0.1)
                # Aprender preferencia negativa
                self.memory_manager.learn_user_preference(self.default_user_id, result.entity.id, "user_feedback", False)
            
            # Guardar entidad actualizada
            self.memory_manager.save_entity(result.entity)
            
            logger._print_log("info", f"Actualizada confianza de entidad {result.entity.id} a {result.entity.confidence}", "entity_resolver.py", "method", 689)
    
    # Métodos para gestión de preferencias (SUBFASE 5.4)
    
    def set_user_preference(self, entity_id: str, preference_type: str, 
                          preference_value: Any, context: Optional[Dict[str, Any]] = None) -> bool:
        """Establece una preferencia de usuario para una entidad."""
        try:
            return self.memory_manager.update_user_preference(
                self.default_user_id, 
                preference_type, 
                entity_id, 
                preference_value, 
                context
            )
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return False
    
    def get_user_preferences_for_entity(self, entity_id: str) -> List[UserPreference]:
        """Obtiene todas las preferencias del usuario para una entidad específica."""
        try:
            return self.memory_manager.get_user_preferences("default", f"entity_{entity_id}")
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return []
    
    def get_preferred_entities(self, preference_type: str = None) -> List[Entity]:
        """Obtiene entidades preferidas por el usuario."""
        try:
            preferences = self.memory_manager.get_user_preferences("default", preference_type)
            
            preferred_entities = []
            for pref in preferences:
                if pref.confidence > 0.7:  # Umbral de preferencia
                    entity = self.memory_manager.get_entity(pref.preference_value)
                    if entity:
                        preferred_entities.append(entity)
            
            return preferred_entities
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return []
    
    # Métodos para gestión de atributos extendidos (SUBFASE 5.4)
    
    def set_entity_attribute(self, entity_id: str, attribute_name: str, 
                           attribute_value: Any, attribute_type: str = "string",
                           source: str = "resolver", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Establece un atributo extendido para una entidad."""
        try:
            return self.memory_manager.update_entity_attribute(
                entity_id, 
                attribute_name, 
                attribute_value, 
                attribute_type, 
                source, 
                metadata
            )
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return False
    
    def get_entity_attributes(self, entity_id: str) -> List[EntityAttribute]:
        """Obtiene todos los atributos extendidos de una entidad."""
        try:
            return self.memory_manager.get_entity_attributes(entity_id)
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return []
    
    def get_entities_with_attribute(self, attribute_name: str, attribute_value: Any) -> List[Entity]:
        """Busca entidades que tienen un atributo específico."""
        try:
            return self.memory_manager.get_entities_by_attribute(attribute_name, attribute_value)
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return []
    
    def learn_entity_interaction(self, entity_id: str, interaction_type: str, 
                               success: bool = True, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Aprende de interacciones con entidades y actualiza atributos."""
        try:
            # Aprender preferencia de usuario
            self.memory_manager.learn_user_preference(self.default_user_id, entity_id, interaction_type, success)
            
            # Actualizar atributo de interacción
            interaction_count_key = f"interaction_count_{interaction_type}"
            current_count = 0
            
            # Obtener contador actual
            current_attr = self.memory_manager.get_entity_attribute(entity_id, interaction_count_key)
            if current_attr:
                current_count = int(current_attr.attribute_value)
            
            # Actualizar contador
            new_count = current_count + 1
            self.set_entity_attribute(
                entity_id, 
                interaction_count_key, 
                new_count, 
                "integer", 
                "interaction_learning",
                {"interaction_type": interaction_type, "success": success, **(metadata or {})}
            )
            
            # Actualizar score de preferencia si la interacción fue exitosa
            if success:
                preference_score_key = "user_preference_score"
                current_score = 0.5  # Score base
                
                current_score_attr = self.memory_manager.get_entity_attribute(entity_id, preference_score_key)
                if current_score_attr:
                    current_score = float(current_score_attr.attribute_value)
                
                # Incrementar score con factor de atenuación
                new_score = min(1.0, current_score + 0.1)
                self.set_entity_attribute(
                    entity_id,
                    preference_score_key,
                    new_score,
                    "float",
                    "preference_learning",
                    {"based_on": interaction_type}
                )
            
            logger._print_log("info", f"Interacción aprendida para entidad {entity_id}: {interaction_type} ({'success' if success else 'failure'}", "entity_resolver.py", "method", 815)
            return True
            
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "entity_resolver.py", "method", 89)
            return False


# Instancia global para uso fácil
entity_resolver = EntityResolver()