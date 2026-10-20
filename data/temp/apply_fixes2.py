# -*- coding: utf-8 -*-
"""Parchear la definicion ACTIVA de _calculate_transfer_efficiency_with_strategy (linea ~3703)."""
import io

TARGET = 'src/utils/contextual_adaptation_engine.py'
src = io.open(TARGET, encoding='utf-8', newline='').read().replace('\r\n', '\n')

old = """    def _calculate_transfer_efficiency_with_strategy(
        self, source: ContextType, target: ContextType, knowledge_type: str, strategy: str
    ) -> float:"""
new = """    def _calculate_transfer_efficiency_with_strategy(
        self, source: ContextType, target: ContextType = None, knowledge_type: str = None, strategy: str = None
    ) -> float:"""
assert src.count(old) == 1, 'firma activa no encontrada'
src = src.replace(old, new, 1)

old = """        try:
            # Base de eficiencia
            base_efficiency = self._calculate_transfer_efficiency(source, target)"""
new = """        try:
            # Invocacion con KnowledgeTransfer: se derivan los parametros
            if isinstance(source, KnowledgeTransfer):
                transfer = source
                source = transfer.source_context
                target = target or transfer.target_context
                knowledge_type = knowledge_type or transfer.knowledge_type
                strategy = strategy or transfer.transfer_strategy

            # Base de eficiencia
            base_efficiency = self._calculate_transfer_efficiency(source, target)"""
assert src.count(old) == 1, 'cuerpo activo no encontrado'
src = src.replace(old, new, 1)

io.open(TARGET, 'w', encoding='utf-8', newline='').write(src)
print('definicion activa parcheada')
