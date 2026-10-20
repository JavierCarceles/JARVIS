# -*- coding: utf-8 -*-
"""Correcciones sobre el motor de adaptacion contextual (contrato de los tests 2.8.6.x)."""
import io

TARGET = 'src/utils/contextual_adaptation_engine.py'
src = io.open(TARGET, encoding='utf-8', newline='').read()
# Normalizar fin de linea para que los patrones coincidan
src = src.replace('\r\n', '\n')

# --- 1. _calculate_transfer_efficiency_with_strategy: aceptar KnowledgeTransfer ---
import re

pat = re.compile(
    r"    def _calculate_transfer_efficiency_with_strategy\(self, source_context: ContextType,\s*\n"
    r"\s*target_context: ContextType,\s*\n"
    r"\s*knowledge_type: str,\s*\n"
    r"\s*transfer_strategy: str\) -> float:"
)
m = pat.search(src)
assert m, 'firma no encontrada'
new_sig = (
    "    def _calculate_transfer_efficiency_with_strategy(self, source_context: ContextType,\n"
    "                                                     target_context: ContextType = None,\n"
    "                                                     knowledge_type: str = None,\n"
    "                                                     transfer_strategy: str = None) -> float:"
)
src = src[:m.start()] + new_sig + src[m.end():]

old = (
    "        try:\n"
    "            # Base compatibility\n"
    "            base_compatibility = self._validate_context_compatibility(source_context, target_context)\n"
    "            \n"
    "            # Strategy modifier\n"
)
new = (
    "        try:\n"
    "            # Invocacion con KnowledgeTransfer: se derivan los parametros\n"
    "            if isinstance(source_context, KnowledgeTransfer):\n"
    "                transfer = source_context\n"
    "                source_context = transfer.source_context\n"
    "                target_context = target_context or transfer.target_context\n"
    "                knowledge_type = knowledge_type or transfer.knowledge_type\n"
    "                transfer_strategy = transfer_strategy or transfer.transfer_strategy\n"
    "\n"
    "            # Base compatibility\n"
    "            base_compatibility = self._validate_context_compatibility(source_context, target_context)\n"
    "            \n"
    "            # Strategy modifier\n"
)
assert src.count(old) == 1, 'cuerpo no encontrado'
src = src.replace(old, new, 1)

# --- 2. strategy_type por defecto: nombre del tipo de conocimiento ---
old = '"strategy_type": entry.get("strategy_type", "adaptation_strategy"),'
new = '"strategy_type": entry.get("strategy_type", "adaptation_strategies"),'
assert src.count(old) == 1, 'strategy_type no encontrado'
src = src.replace(old, new, 1)

old = '"strategy_type": "adaptation_strategy",'
new = '"strategy_type": "adaptation_strategies",'
assert src.count(old) >= 1, 'strategy_type aplicado no encontrado'
src = src.replace(old, new)

old = '"strategy_type": strategy.get("strategy_type", "adaptation_strategy"),'
new = '"strategy_type": strategy.get("strategy_type", "adaptation_strategies"),'
assert src.count(old) == 1, 'strategy_type candidato no encontrado'
src = src.replace(old, new, 1)

# --- 3. IDs de candidatos unicos entre llamadas ---
old = '''        candidates: List[Dict[str, Any]] = []
        context_value = target_context.value if isinstance(target_context, ContextType) else str(target_context)

        for strategy in self.get_available_strategies(target_context):'''
new = '''        candidates: List[Dict[str, Any]] = []
        context_value = target_context.value if isinstance(target_context, ContextType) else str(target_context)
        generation = int(time.time() * 1000000)

        for strategy in self.get_available_strategies(target_context):'''
assert src.count(old) == 1, 'cabecera de generate_strategy_candidates no encontrada'
src = src.replace(old, new, 1)

old = '"strategy_id": f"cand_{strategy[\'strategy_id\']}",'
new = '"strategy_id": f"cand_{generation}_{strategy[\'strategy_id\']}",'
assert src.count(old) == 1, 'strategy_id de candidato no encontrado'
src = src.replace(old, new, 1)

# --- 4. evaluate_candidate_strategy ---
old = '''    def select_strategy(
        self,
        evaluated_strategies: List[Dict[str, Any]],
        current_strategy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:'''
new = '''    def evaluate_candidate_strategy(self, candidate: Dict[str, Any], target_context: ContextType) -> Dict[str, Any]:
        """
        Evaluar un candidato de estrategia en un contexto destino.

        Returns:
            Dict[str, Any]: Evaluación con valid, overall_score, applicability,
            efficiency y knowledge_data
        """
        evaluation: Dict[str, Any] = {
            "valid": False,
            "errors": [],
            "strategy_id": (candidate or {}).get("strategy_id"),
            "strategy_name": (candidate or {}).get("name"),
            "strategy_type": (candidate or {}).get("strategy_type", "adaptation_strategies"),
            "description": (candidate or {}).get("description"),
            "confidence": float((candidate or {}).get("confidence", 0.0) or 0.0),
            "knowledge_data": (candidate or {}).get("knowledge_data", {}) or {},
            "target_context": target_context.value if isinstance(target_context, ContextType) else str(target_context),
            "overall_score": 0.0,
            "applicability": 0.0,
            "efficiency": 0.0,
        }

        is_valid, errors = self.validate_candidate_strategy(candidate)
        evaluation["valid"] = is_valid
        evaluation["errors"] = errors

        if not is_valid:
            return evaluation

        knowledge_data = evaluation["knowledge_data"]
        try:
            applicability = float(self._calculate_strategy_applicability(knowledge_data, target_context))
        except Exception:
            applicability = 0.0
        try:
            efficiency = float(self._calculate_transfer_efficiency_with_strategy(
                source_context=target_context,
                target_context=target_context,
                knowledge_type=evaluation["strategy_type"],
                transfer_strategy="adaptive",
            ))
        except Exception:
            efficiency = 0.0

        evaluation["applicability"] = max(0.0, min(1.0, applicability))
        evaluation["efficiency"] = max(0.0, min(1.0, efficiency))
        evaluation["overall_score"] = round(
            evaluation["confidence"] * 0.4 + evaluation["applicability"] * 0.3 + evaluation["efficiency"] * 0.3, 4
        )
        return evaluation

    def select_strategy(
        self,
        evaluated_strategies: List[Dict[str, Any]],
        current_strategy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:'''
assert src.count(old) == 1, 'select_strategy no encontrado'
src = src.replace(old, new, 1)

io.open(TARGET, 'w', encoding='utf-8', newline='').write(src)
print('4 correcciones aplicadas')
