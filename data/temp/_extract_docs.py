import re

code_path = r'c:\Informatica\PROYECTOS\BACKEND/IA_PYTHON/IA/JARVIS/src/utils/contextual_adaptation_engine.py'
with open(code_path, encoding='utf-8') as f:
    lines = f.readlines()

# List of missing methods from our analysis
missing_methods = {
    'public': [
        'apply_strategy', 'clear_adaptation_history', 'clear_conversational_memory',
        'clear_corrupted_data', 'clear_knowledge_base_patterns', 'compare_strategies',
        'create_goal_adaptation_proposal', 'evaluate_candidate_strategy',
        'get_adaptation_rule', 'get_knowledge_transfer_objects', 'knowledge_transaptors',
        'list_adaptation_rules', 'manual_system_reset', 'minimum_evidence',
        'on_proposal_created', 'process_architectural_result', 'process_evidence_registration',
        'register_feedback', 'represent_adaptation', 'reset_learning_data',
        'select_strategy', 'set_architecture_manager', 'to_dict',
        'update_architecture_state', 'update_components', 'validate_adapted_goal',
        'validate_candidate_strategy',
    ],
    'private': [
        '__getattr__', '__iter__', '_analyze_adaptation_improvement',
        '_are_constraints_contradictory', '_bounded_float', '_calculate_learning_convergence',
        '_calculate_transfer_efficiency_with_strategy', '_calculate_transfer_priority',
        '_call_optional', '_campos_de_formato', '_capture_feedback',
        '_check_intention_preservation', '_coerce_context', '_confidence_threshold',
        '_count_pattern_observations', '_desviaciones_estrictas_de_regla', '_deteccion',
        '_detect_corruption_feedback', '_detect_corruption_in', '_detect_corruption_knowledge_base',
        '_detect_corruption_learning_results', '_detect_corruption_rules',
        '_es_convertible_a_entero', '_es_marca_iso', '_estimate_transfer_efficiency',
        '_estrategia_aprendida_valida', '_extract_contextual_metrics',
        '_extract_knowledge_from_context', '_extract_performance_improvement',
        '_filter_validated_learning_results', '_generate_pattern_description',
        '_generate_strategy_description', '_generate_transfer_reasoning',
        '_get_context_adjustment_factor', '_get_context_knowledge_amount', '_goal_to_dict',
        '_has_transfer_history', '_hay_que_cargar', '_identify_relevant_knowledge_types',
        '_is_validated_pattern', '_json_default', '_known_strategy_ids',
        '_min_similar_observations', '_pattern_identity', '_record_adaptation_history',
        '_record_feedback_analysis', '_record_successful_transfer_pattern',
        '_recover_learning_patterns', '_register_validation_result',
        '_required_capabilities_for_goal', '_resolve_path', '_resolve_transfer_confidence',
        '_revert_strategy_application', '_rule_to_dict', '_safe_float', '_serializable_history',
        '_snapshot_to_dict', '_targets_equivalent', '_unidades_obtenidas',
        '_validate_adaptation_constraints', '_validate_capabilities', '_validate_current_state',
        '_validate_goal_preconditions', '_validate_goal_structure', '_validate_planner_can_solve',
        '_verify_strategy_application',
    ],
}

# Find each method and print its signature + first 3 lines of docstring
for category in ['public', 'private']:
    print(f'\n=== {category.upper()} METHODS ===')
    for method_name in missing_methods[category]:
        for i, line in enumerate(lines):
            if re.match(r'^    def ' + re.escape(method_name) + r'\(', line):
                # Print signature
                sig = line.strip()
                # Find docstring
                doc_lines = []
                for j in range(i+1, min(i+10, len(lines))):
                    stripped = lines[j].strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        doc_lines.append(stripped)
                        if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                            break
                    elif stripped.startswith('-') or stripped.startswith('Args'):
                        break
                    elif doc_lines:
                        doc_lines.append(stripped)
                doc = ' '.join(doc_lines[:2]) if doc_lines else '(no docstring)'
                print(f'  L{i+1}: {sig}')
                print(f'       Doc: {doc}')
                break
