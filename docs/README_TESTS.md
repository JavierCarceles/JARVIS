# 🧪 README — JARVIS (documentación exhaustiva de la suite de tests)

> **Alcance:** documentación generada a partir de los **ficheros de prueba** (`tests/`, espejo de `src/`).
> Cada entrada se deriva de las firmas, docstrings y clases de test extraídas mediante AST de los 149 ficheros de test (excluyendo `__pycache__`, `test__init__.py` placeholders vacíos, `__init__.py` y scripts auxiliares sin prefijo `test_`).
> Total: 783 clases de test, 4025 métodos de test individuales.

## 🗺️ Índice

- [Estructura y convenciones de `tests/`](#estructura-y-convenciones-de-tests)
- [Cómo ejecutar los tests](#cómo-ejecutar-los-tests)
- [Documentación por módulo de tests](#documentación-por-módulo-de-tests)
<!-- sección por directorio -->
- [`brain\test_htn_integration.py`](#brain/test-htn_integration)
- [`brain\test_llm.py`](#brain/test-llm)
- [`ear\test_listener.py`](#ear/test-listener)
- [`eyes\test_application_state_enumeration.py`](#eyes/test-application_state_enumeration)
- [`eyes\test_application_state_separation.py`](#eyes/test-application_state_separation)
- [`eyes\test_application_state_unknown.py`](#eyes/test-application_state_unknown)
- [`eyes\test_screen.py`](#eyes/test-screen)
- [`eyes\test_screen_capture.py`](#eyes/test-screen_capture)
- [`eyes\test_state_comparison.py`](#eyes/test-state_comparison)
- [`eyes\test_ui_element_behavior.py`](#eyes/test-ui_element_behavior)
- [`eyes\test_ui_element_type_description.py`](#eyes/test-ui_element_type_description)
- [`eyes\test_ui_elements_structure.py`](#eyes/test-ui_elements_structure)
- [`eyes\test_ui_knowledge_coordinate_separation.py`](#eyes/test-ui_knowledge_coordinate_separation)
- [`eyes\test_vision.py`](#eyes/test-vision)
- [`eyes\test_vision_calibration_integration.py`](#eyes/test-vision_calibration_integration)
- [`eyes\test_vision_only.py`](#eyes/test-vision_only)
- [`hands\planner\test_advanced_state_graph.py`](#hands/planner/test-advanced_state_graph)
- [`hands\planner\test_application_integration.py`](#hands/planner/test-application_integration)
- [`hands\planner\test_application_knowledge_to_goal.py`](#hands/planner/test-application_knowledge_to_goal)
- [`hands\planner\test_cache_performance.py`](#hands/planner/test-cache_performance)
- [`hands\planner\test_capabilities_consumible_format.py`](#hands/planner/test-capabilities_consumible_format)
- [`hands\planner\test_graph_builder.py`](#hands/planner/test-graph_builder)
- [`hands\planner\test_graph_edge.py`](#hands/planner/test-graph_edge)
- [`hands\planner\test_graph_helpers.py`](#hands/planner/test-graph_helpers)
- [`hands\planner\test_graph_node.py`](#hands/planner/test-graph_node)
- [`hands\planner\test_is_application_available_no_process_name_assumption.py`](#hands/planner/test-is_application_available_no_process_name_assumption)
- [`hands\planner\test_node.py`](#hands/planner/test-node)
- [`hands\planner\test_planner_action_verification.py`](#hands/planner/test-planner_action_verification)
- [`hands\planner\test_planner_capability_action_traceability.py`](#hands/planner/test-planner_capability_action_traceability)
- [`hands\planner\test_planner_find_nodes_for_capability.py`](#hands/planner/test-planner_find_nodes_for_capability)
- [`hands\planner\test_route_result.py`](#hands/planner/test-route_result)
- [`hands\planner\test_state_graph.py`](#hands/planner/test-state_graph)
- [`hands\planner\test_task_executor.py`](#hands/planner/test-task_executor)
- [`hands\test_action_registry.py`](#hands/test-action_registry)
- [`hands\test_application_alias_resolution.py`](#hands/test-application_alias_resolution)
- [`hands\test_application_classification.py`](#hands/test-application_classification)
- [`hands\test_application_consumers_real_model.py`](#hands/test-application_consumers_real_model)
- [`hands\test_application_contract_no_duplication.py`](#hands/test-application_contract_no_duplication)
- [`hands\test_application_data_format.py`](#hands/test-application_data_format)
- [`hands\test_application_data_incomplete.py`](#hands/test-application_data_incomplete)
- [`hands\test_application_discovered_temporary.py`](#hands/test-application_discovered_temporary)
- [`hands\test_application_discovery_no_recursive_disk_search.py`](#hands/test-application_discovery_no_recursive_disk_search)
- [`hands\test_application_discovery_persistence_contract.py`](#hands/test-application_discovery_persistence_contract)
- [`hands\test_application_discovery_separation.py`](#hands/test-application_discovery_separation)
- [`hands\test_application_discovery_sources.py`](#hands/test-application_discovery_sources)
- [`hands\test_application_identification.py`](#hands/test-application_identification)
- [`hands\test_application_invalid_json.py`](#hands/test-application_invalid_json)
- [`hands\test_application_load.py`](#hands/test-application_load)
- [`hands\test_application_load_correctness.py`](#hands/test-application_load_correctness)
- [`hands\test_application_mandatory_data.py`](#hands/test-application_mandatory_data)
- [`hands\test_application_minimal_contract.py`](#hands/test-application_minimal_contract)
- [`hands\test_application_name_resolution.py`](#hands/test-application_name_resolution)
- [`hands\test_application_optional_data.py`](#hands/test-application_optional_data)
- [`hands\test_application_preflight.py`](#hands/test-application_preflight)
- [`hands\test_application_preflight_availability.py`](#hands/test-application_preflight_availability)
- [`hands\test_application_preflight_launch_destination.py`](#hands/test-application_preflight_launch_destination)
- [`hands\test_application_preflight_resolve_executable.py`](#hands/test-application_preflight_resolve_executable)
- [`hands\test_application_read.py`](#hands/test-application_read)
- [`hands\test_application_register_duplicates.py`](#hands/test-application_register_duplicates)
- [`hands\test_application_register_in_memory.py`](#hands/test-application_register_in_memory)
- [`hands\test_application_resolution_ambiguity.py`](#hands/test-application_resolution_ambiguity)
- [`hands\test_application_resolution_evidence.py`](#hands/test-application_resolution_evidence)
- [`hands\test_application_source_missing.py`](#hands/test-application_source_missing)
- [`hands\test_applications_core.py`](#hands/test-applications_core)
- [`hands\test_calibration_manager.py`](#hands/test-calibration_manager)
- [`hands\test_calibration_requirements.py`](#hands/test-calibration_requirements)
- [`hands\test_calibrator.py`](#hands/test-calibrator)
- [`hands\test_capability_absent_verification.py`](#hands/test-capability_absent_verification)
- [`hands\test_capability_availability_distinction.py`](#hands/test-capability_availability_distinction)
- [`hands\test_capability_query_contract.py`](#hands/test-capability_query_contract)
- [`hands\test_consumer_api_compatibility.py`](#hands/test-consumer_api_compatibility)
- [`hands\test_discovery_source_report.py`](#hands/test-discovery_source_report)
- [`hands\test_discovery_source_report_3816.py`](#hands/test-discovery_source_report_3816)
- [`hands\test_entities_json_preservation_discovery.py`](#hands/test-entities_json_preservation_discovery)
- [`hands\test_executor.py`](#hands/test-executor)
- [`hands\test_executor_state.py`](#hands/test-executor_state)
- [`hands\test_restore_window_state.py`](#hands/test-restore_window_state)
- [`hands\test_system_inventory.py`](#hands/test-system_inventory)
- [`hands\test_system_inventory_storage.py`](#hands/test-system_inventory_storage)
- [`hands\test_ui_elements.py`](#hands/test-ui_elements)
- [`hands\test_ui_elements_final.py`](#hands/test-ui_elements_final)
- [`hands\test_ui_elements_minimal.py`](#hands/test-ui_elements_minimal)
- [`hands\test_ui_elements_real.py`](#hands/test-ui_elements_real)
- [`hands\test_ui_elements_simple.py`](#hands/test-ui_elements_simple)
- [`hands\test_ui_elements_working.py`](#hands/test-ui_elements_working)
- [`hands\windows\test_window_verification.py`](#hands/windows/test-window_verification)
- [`helpers\test_entities_state_helper.py`](#helpers/test-entities_state_helper)
- [`memory\test_memory_entities_json_estado_inicial.py`](#memory/test-memory_entities_json_estado_inicial)
- [`memory\test_memory_save_entity_persist_bug.py`](#memory/test-memory_save_entity_persist_bug)
- [`utils\adaptive_learning_engine\test_adaptive_learning_engine_original.py`](#utils/adaptive_learning_engine/test-adaptive_learning_engine_original)
- [`utils\adaptive_learning_engine\test_goal_adaptation_learning_loop.py`](#utils/adaptive_learning_engine/test-goal_adaptation_learning_loop)
- [`utils\contextual_adaptation_engine\test_absent_storage_and_sections.py`](#utils/contextual_adaptation_engine/test-absent_storage_and_sections)
- [`utils\contextual_adaptation_engine\test_adaptation_does_not_break_planner_executor.py`](#utils/contextual_adaptation_engine/test-adaptation_does_not_break_planner_executor)
- [`utils\contextual_adaptation_engine\test_adapted_goal_validation.py`](#utils/contextual_adaptation_engine/test-adapted_goal_validation)
- [`utils\contextual_adaptation_engine\test_context_compatibility.py`](#utils/contextual_adaptation_engine/test-context_compatibility)
- [`utils\contextual_adaptation_engine\test_context_model_origin_destination.py`](#utils/contextual_adaptation_engine/test-context_model_origin_destination)
- [`utils\contextual_adaptation_engine\test_contextual_features_signals.py`](#utils/contextual_adaptation_engine/test-contextual_features_signals)
- [`utils\contextual_adaptation_engine\test_corrupt_data.py`](#utils/contextual_adaptation_engine/test-corrupt_data)
- [`utils\contextual_adaptation_engine\test_cross_context_confidence_feedback.py`](#utils/contextual_adaptation_engine/test-cross_context_confidence_feedback)
- [`utils\contextual_adaptation_engine\test_cross_context_knowledge_transfer.py`](#utils/contextual_adaptation_engine/test-cross_context_knowledge_transfer)
- [`utils\contextual_adaptation_engine\test_cross_context_units.py`](#utils/contextual_adaptation_engine/test-cross_context_units)
- [`utils\contextual_adaptation_engine\test_direct.py`](#utils/contextual_adaptation_engine/test-direct)
- [`utils\contextual_adaptation_engine\test_evolutionary_strategy_optimizer.py`](#utils/contextual_adaptation_engine/test-evolutionary_strategy_optimizer)
- [`utils\contextual_adaptation_engine\test_final.py`](#utils/contextual_adaptation_engine/test-final)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_condition_pattern_default.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_condition_pattern_default)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_conservation.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_conservation)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_corrupted_list_section.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_corrupted_list_section)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_evidence_insufficient.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_evidence_insufficient)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_evidence_valid.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_evidence_valid)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_fabricated_identity.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_fabricated_identity)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_feedback.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_feedback)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_feedback_persistence.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_feedback_persistence)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_forgetting.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_forgetting)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_learned_strategy_persistence.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_learned_strategy_persistence)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_pattern_load.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_pattern_load)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_pattern_persistence.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_pattern_persistence)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_pattern_restart_verification.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_pattern_restart_verification)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_persistence_real.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_persistence_real)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_persistence_simple.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_persistence_simple)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_production_data_clean.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_production_data_clean)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_proposal.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_proposal)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_recoverable.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_recoverable)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_recovery_partial.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_recovery_partial)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_rejection_runtime.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_rejection_runtime)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_representation.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_representation)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_restart_compatibility.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_restart_compatibility)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_strategy_persistence.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_strategy_persistence)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_strategy_restart_verification.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_strategy_restart_verification)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_total_corruption.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_total_corruption)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_total_loss_fallback.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_total_loss_fallback)
- [`utils\contextual_adaptation_engine\test_goal_adaptation_total_loss_fallback_implemented.py`](#utils/contextual_adaptation_engine/test-goal_adaptation_total_loss_fallback_implemented)
- [`utils\contextual_adaptation_engine\test_load_goal_adaptation_feedback.py`](#utils/contextual_adaptation_engine/test-load_goal_adaptation_feedback)
- [`utils\contextual_adaptation_engine\test_simple.py`](#utils/contextual_adaptation_engine/test-simple)
- [`utils\contextual_adaptation_engine\test_transfer_recommendations.py`](#utils/contextual_adaptation_engine/test-transfer_recommendations)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_allocate.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_allocate)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_allocate_simple.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_allocate_simple)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_allocation.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_allocation)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_integration.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_integration)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_inventory.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_inventory)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_priority_conflicts.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_priority_conflicts)
- [`utils\dynamic_resource_allocator\test_dynamic_resource_allocator_release.py`](#utils/dynamic_resource_allocator/test-dynamic_resource_allocator_release)
- [`utils\test_adaptive_goal_system.py`](#utils/test-adaptive_goal_system)
- [`utils\test_adaptive_learning_engine.py`](#utils/test-adaptive_learning_engine)
- [`utils\test_architectural_evolution_manager.py`](#utils/test-architectural_evolution_manager)
- [`utils\test_auto_improvement_system.py`](#utils/test-auto_improvement_system)
- [`utils\test_contextual_pattern_recognizer.py`](#utils/test-contextual_pattern_recognizer)
- [`utils\test_contextual_pattern_recognizer_legacy.py`](#utils/test-contextual_pattern_recognizer_legacy)
- [`utils\test_dynamic_resource_allocator.py`](#utils/test-dynamic_resource_allocator)
- [`utils\test_meta_learning_system.py`](#utils/test-meta_learning_system)
- [`utils\test_pattern_analyzer.py`](#utils/test-pattern_analyzer)
- [`utils\test_performance_optimizer.py`](#utils/test-performance_optimizer)
- [`utils\test_self_improvement_system.py`](#utils/test-self_improvement_system)

---

## 📁 Estructura y convenciones de `tests/`

`tests/` es un **espejo de `src/`**:

```
src/<paquete>/<modulo>.py   ->  tests/<paquete>/test_<modulo>.py
                              (un único test para ese módulo)

src/<paquete>/<modulo>.py   ->  tests/<paquete>/<modulo>/test_*.py
                              (varios tests para ese módulo)
```

Los 4 ficheros `test__init__.py` (en `brain/`, `ear/`, `eyes/`, `hands/`) están **vacíos** y sirven solo como placeholders de paquete; no contienen tests y se excluyen de esta documentación.

El fichero `tests/conftest.py` configura el entorno de prueba: añade `src/` y la raíz al `sys.path`, activa un sandbox temporal (para que los tests no muten `data/` de producción), y define `collect_ignore` para los placeholders vacíos y scripts de corrección manual.

Todos los tests usan **`unittest`** con nomenclatura `test_<id>_<descripcion>` (ej. `test_2_8_13_5_1_brain_exported`). Los IDs siguen el versionado `2.8.13.5.X` del proyecto.

---

## 📚 Documentación por módulo de tests

## 📂 `brain/`

2 ficheros de test, 103 métodos de test.

<a name="brain/test-htn_integration"></a>
### `brain\test_htn_integration.py`

**Descripción:** Tests de integración HTN-Brain 2.8.13.5

**Módulos de origen probados:** src.brain.htn_integration, src.hands.planner.htn_manager, src.hands.planner.node

**Clases de test:**

- **`TestHTNBrainIntegrationInit`** (línea 18) — 6 método(s) de test
  - 2.8.13.5.2 — Verificar inicialización de HTNBrainIntegration

  - **`test_2_8_13_5_2_htn_manager_asignado`** (L21)
    - El gestor HTN debe estar inicializado (singleton).

  - **`test_2_8_13_5_2_task_executor_asignado`** (L26)
    - El ejecutor de tareas debe estar inicializado.

  - **`test_2_8_13_5_2_memory_manager_asignado`** (L31)
    - El gestor de memoria debe estar inicializado.

  - **`test_2_8_13_5_2_application_integrator_asignado`** (L36)
    - El integrador de aplicaciones debe estar inicializado.

  - **`test_2_8_13_5_2_is_enabled_por_defecto`** (L41)
    - La integración debe estar habilitada por defecto.

  - **`test_2_8_13_5_2_total_integrations_inicia_en_cero`** (L46)
    - El contador de integraciones debe iniciar en cero.

- **`TestHTNGGoalCreation`** (línea 52) — 9 método(s) de test
  - 2.8.13.5.3 — Verificar _create_goal_from_input

  - **`test_2_8_13_5_3_goal_calibracion`** (L58)
    - Input con 'calibrar' debe crear un Goal de calibración.

  - **`test_2_8_13_5_3_goal_open_chrome`** (L65)
    - Input con 'abrir' y 'chrome' debe crear un Goal de apertura.

  - **`test_2_8_13_5_3_goal_open_youtube`** (L72)
    - Input con 'abrir' y 'youtube' debe crear un Goal de apertura de youtube.

  - **`test_2_8_13_5_3_goal_navegar_url`** (L79)
    - Input con 'navegar' y URL debe crear un Goal de navegación.

  - **`test_2_8_13_5_3_goal_navegar_entity`** (L88)
    - Input con 'navegar' sin URL debe crear un Goal de navegación de stream.

  - **`test_2_8_13_5_3_goal_search`** (L96)
    - Input con 'buscar' debe crear un Goal de búsqueda.

  - **`test_2_8_13_5_3_goal_generic_sin_palabras_clave`** (L105)
    - Input sin palabras clave debe crear un Goal genérico.

  - **`test_2_8_13_5_3_goal_input_vacio_retorna_none`** (L113)
    - Input vacío debe retornar None.

  - **`test_2_8_13_5_3_goal_tiene_id_unico`** (L119)
    - Los goals creados deben tener IDs basados en el tipo y timestamp.

  Métodos auxiliares (no test): setUp

- **`TestHTNIntegrationStatistics`** (línea 128) — 6 método(s) de test
  - 2.8.13.5.4 — Verificar estadísticas e integración

  - **`test_2_8_13_5_4_get_integration_statistics`** (L134)
    - get_integration_statistics debe retornar un diccionario con claves esperadas.

  - **`test_2_8_13_5_4_success_rate_inicia_en_cero`** (L145)
    - Con cero integraciones, success_rate debe ser 0.0.

  - **`test_2_8_13_5_4_enable_disable_integration`** (L151)
    - enable_integration debe alternar el estado de habilitación.

  - **`test_2_8_13_5_4_record_integration_actualiza_contadores`** (L159)
    - _record_integration debe incrementar contadores correctamente.

  - **`test_2_8_13_5_4_record_integration_tiempo`** (L174)
    - _record_integration debe actualizar last_execution_time.

  - **`test_2_8_13_5_4_get_htn_insights`** (L179)
    - get_htn_insights debe retornar insights agregados del sistema HTN.

  Métodos auxiliares (no test): setUp

- **`TestHTNIntegrationSingleton`** (línea 194) — 2 método(s) de test
  - 2.8.13.5.5 — Verificar singleton get_htn_integration

  - **`test_2_8_13_5_5_get_htn_integration_retorna_instancia`** (L197)
    - get_htn_integration debe retornar una instancia de HTNBrainIntegration.

  - **`test_2_8_13_5_5_get_htn_integration_singleton`** (L202)
    - get_htn_integration debe retornar siempre la misma instancia.

- **`TestHTNIntegrationSerialization`** (línea 209) — 3 método(s) de test
  - 2.8.13.5.6 — Verificar serialización de tareas y resultados

  - **`test_2_8_13_5_6_serialize_task`** (L215)
    - _serialize_task debe convertir una Task a diccionario correctamente.

  - **`test_2_8_13_5_6_serialize_task_none`** (L226)
    - _serialize_task debe manejar None con valores por defecto.

  - **`test_2_8_13_5_6_serialize_execution_result`** (L234)
    - _serialize_execution_result debe convertir TaskExecutionResult a dict.

  Métodos auxiliares (no test): setUp

- **`TestHTNIntegrationProcessGoal`** (línea 255) — 7 método(s) de test
  - 2.8.13.5.7 — Verificar process_goal_through_htn

  - **`test_2_8_13_5_7_process_goal_disabled`** (L284)
    - Si la integración está deshabilitada, debe retornar resultado de fallo.

  - **`test_2_8_13_5_7_process_goal_none`** (L294)
    - Si el goal es None y está deshabilitado, el acceso a goal.id produce error.

  - **`test_2_8_13_5_7_process_goal_success`** (L300)
    - Un Goal navegable válido debe descomponer y ejecutar exitosamente.

  - **`test_2_8_13_5_7_process_goal_invalid_type`** (L317)
    - Un Goal con id vacío debe fallar.

  - **`test_2_8_13_5_7_create_and_execute_empty_input`** (L323)
    - create_and_execute_htn_goal con input vacío debe retornar fracaso.

  - **`test_2_8_13_5_7_create_and_execute_none_input`** (L329)
    - create_and_execute_htn_goal con input None debe retornar fracaso.

  - **`test_2_8_13_5_7_create_and_execute_valid_input`** (L334)
    - create_and_execute_htn_goal con input válido debe procesar el goal.

  Métodos auxiliares (no test): setUpClass, setUp

- **`TestHTNIntegrationResultDataclass`** (línea 351) — 2 método(s) de test
  - 2.8.13.5.8 — Verificar HTNIntegrationResult dataclass

  - **`test_2_8_13_5_8_result_defaults`** (L354)
    - HTNIntegrationResult debe retornar los valores provistos correctamente.

  - **`test_2_8_13_5_8_result_with_values`** (L375)
    - HTNIntegrationResult debe almacenar todos los valores provistos.

---

<a name="brain/test-llm"></a>
### `brain\test_llm.py`

**Descripción:** Tests del módulo Brain (LLM) 2.8.13.5

**Módulos de origen probados:** src.brain.htn_integration, src.brain.llm

**Clases de test:**

- **`TestBrainInit`** (línea 16) — 6 método(s) de test
  - 2.8.13.5.9 — Verificar inicialización del Brain

  - **`test_2_8_13_5_9_model_asignado`** (L23)
    - El modelo debe estar configurado correctamente.

  - **`test_2_8_13_5_9_htn_integration_asignado`** (L27)
    - La integración HTN debe estar inicializada.

  - **`test_2_8_13_5_9_action_registry_asignado`** (L31)
    - El registro de acciones debe estar inicializado.

  - **`test_2_8_13_5_9_entity_resolver_asignado`** (L35)
    - El resolvedor de entidades debe estar inicializado.

  - **`test_2_8_13_5_9_memory_manager_asignado`** (L39)
    - El gestor de memoria debe estar inicializado.

  - **`test_2_8_13_5_9_preconditions_effects_asignado`** (L43)
    - El gestor de precondiciones/efectos debe estar inicializado.

  Métodos auxiliares (no test): setUpClass

- **`TestBrainActionAliases`** (línea 48) — 5 método(s) de test
  - 2.8.13.5.10 — Verificar ACTION_ALIASES

  - **`test_2_8_13_5_10_calibrar_chrome_alias`** (L55)
    - calibrate_chrome debe mapear a calibrar_chrome.

  - **`test_2_8_13_5_10_calibrar_aplicaciones_alias`** (L59)
    - calibrate_applications debe mapear a calibrar_aplicaciones.

  - **`test_2_8_13_5_10_calibrate_all_alias`** (L63)
    - calibrate_all_applications debe mapear a calibrar_aplicaciones.

  - **`test_2_8_13_5_10_opener_alias`** (L67)
    - open_chrome debe mapear a abrir_chrome.

  - **`test_2_8_13_5_10_aliases_dict_no_vacio`** (L71)
    - ACTION_ALIASES debe contener múltiples entradas.

  Métodos auxiliares (no test): setUpClass

- **`TestNormalizeActionName`** (línea 76) — 7 método(s) de test
  - 2.8.13.5.11 — Verificar _normalize_action_name

  - **`test_2_8_13_5_11_normaliza_alias_chrome`** (L83)
    - 'calibrate_chrome' no está registrado; alias debe resolver a 'calibrar_chrome'.

  - **`test_2_8_13_5_11_normaliza_alias_aplicaciones`** (L88)
    - 'calibrate_applications' está registrado y debe retornarse tal cual.

  - **`test_2_8_13_5_11_normaliza_alias_chrome_ingles`** (L93)
    - 'calibrate_chrome' NO está registrado; el alias debe resolver a 'calibrar_chrome'.

  - **`test_2_8_13_5_11_normaliza_accion_registrada`** (L98)
    - Una acción ya registrada no debe ser modificada.

  - **`test_2_8_13_5_11_retorna_candidato_para_desconocida`** (L103)
    - Una acción desconocida debe retornar el candidato sin cambios.

  - **`test_2_8_13_5_11_retorna_vacio_para_no_string`** (L108)
    - Debe retornar cadena vacía para entrada no string.

  - **`test_2_8_13_5_11_retorna_vacio_para_vacio`** (L113)
    - Debe retornar cadena vacía para string vacío o en blanco.

  Métodos auxiliares (no test): setUpClass

- **`TestCleanJsonResponse`** (línea 119) — 6 método(s) de test
  - 2.8.13.5.12 — Verificar _clean_json_response

  - **`test_2_8_13_5_12_strip_markdown_fences`** (L122)
    - Debe eliminar bloques de código markdown.

  - **`test_2_8_13_5_12_extract_from_text_with_prefix`** (L128)
    - Debe extraer JSON incrustado en texto.

  - **`test_2_8_13_5_12_plain_json_unchanged`** (L135)
    - El JSON limpio debe pasar sin cambios.

  - **`test_2_8_13_5_12_empty_string`** (L141)
    - Cadena vacía debe retornar cadena vacía.

  - **`test_2_8_13_5_12_none_input`** (L145)
    - None debe retornar cadena vacía.

  - **`test_2_8_13_5_12_nested_json_from_text`** (L149)
    - Debe extraer JSON anidado del texto.

- **`TestParseModelResponse`** (línea 157) — 6 método(s) de test
  - 2.8.13.5.13 — Verificar parse_model_response

  - **`test_2_8_13_5_13_parse_valid_json`** (L164)
    - Debe parsear JSON válido a diccionario.

  - **`test_2_8_13_5_13_parse_json_con_markdown`** (L170)
    - Debe parsear JSON envuelto en markdown.

  - **`test_2_8_13_5_13_parse_json_en_texto`** (L177)
    - Debe extraer JSON de un texto con prefijo.

  - **`test_2_8_13_5_13_invalid_json_returns_none`** (L184)
    - JSON inválido debe retornar None.

  - **`test_2_8_13_5_13_empty_returns_none`** (L189)
    - Cadena vacía debe retornar None.

  - **`test_2_8_13_5_13_json_list_returns_none`** (L194)
    - Un JSON que no es dict debe retornar None.

  Métodos auxiliares (no test): setUpClass

- **`TestDetectDirectAction`** (línea 200) — 8 método(s) de test
  - 2.8.13.5.14 — Verificar _detect_direct_action

  - **`test_2_8_13_5_14_detect_chrome_calibration`** (L207)
    - Debe detectar calibración específica de Chrome.

  - **`test_2_8_13_5_14_detect_edge_calibration`** (L214)
    - Debe detectar calibración específica de Edge.

  - **`test_2_8_13_5_14_detect_firefox_calibration`** (L220)
    - Debe detectar calibración específica de Firefox.

  - **`test_2_8_13_5_14_detect_global_calibration`** (L226)
    - Debe detectar calibración global de aplicaciones.

  - **`test_2_8_13_5_14_detect_global_calibration_programas`** (L232)
    - Debe detectar calibración global usando 'programas'.

  - **`test_2_8_13_5_14_browser_specific_no_global`** (L238)
    - 'calibrar chrome' no debe interpretarse como calibración global.

  - **`test_2_8_13_5_14_no_action_for_non_calibration`** (L244)
    - Input sin calibración no debe detectar acción directa.

  - **`test_2_8_13_5_14_no_action_for_empty`** (L249)
    - Input vacío no debe detectar acción directa.

  Métodos auxiliares (no test): setUpClass

- **`TestExecuteGoal`** (línea 255) — 4 método(s) de test
  - 2.8.13.5.15 — Verificar execute_goal

  - **`test_2_8_13_5_15_navigate_stream_goal`** (L262)
    - Un goal navigate_stream debe producir navigate_to_url.

  - **`test_2_8_13_5_15_navigate_goal`** (L270)
    - Un goal navigate debe producir navigate_to_url.

  - **`test_2_8_13_5_15_open_application_goal`** (L278)
    - Un goal open_application debe producir open_{target}.

  - **`test_2_8_13_5_15_unknown_goal_type`** (L286)
    - Un goal type desconocido debe retornar error.

  Métodos auxiliares (no test): setUpClass

- **`TestBrainPublicAPI`** (línea 294) — 12 método(s) de test
  - 2.8.13.5.16 — Verificar API pública del Brain

  - **`test_2_8_13_5_16_get_current_goals_empty`** (L301)
    - get_current_goals debe retornar una lista vacía.

  - **`test_2_8_13_5_16_get_system_state`** (L305)
    - get_system_state debe retornar un estado no nulo.

  - **`test_2_8_13_5_16_get_available_actions_is_list`** (L310)
    - get_available_actions debe retornar una lista.

  - **`test_2_8_13_5_16_get_jarvis_context`** (L315)
    - get_jarvis_context debe retornar un diccionario.

  - **`test_2_8_13_5_16_interpret_intent_empty`** (L320)
    - interpret_intent con input vacío debe retornar tipo unknown.

  - **`test_2_8_13_5_16_interpret_intent_none`** (L327)
    - interpret_intent con None debe retornar tipo unknown.

  - **`test_2_8_13_5_16_think_empty_prompt`** (L332)
    - think con prompt vacío debe retornar mensaje por defecto.

  - **`test_2_8_13_5_16_think_none_prompt`** (L337)
    - think con None debe retornar mensaje por defecto.

  - **`test_2_8_13_5_16_clear_memory_no_raises`** (L342)
    - clear_memory no debe lanzar excepción.

  - **`test_2_8_13_5_16_get_conversation_history_is_list`** (L349)
    - get_conversation_history debe retornar una lista.

  - **`test_2_8_13_5_16_get_domain_entities_is_list`** (L354)
    - get_domain_entities debe retornar una lista.

  - **`test_2_8_13_5_16_get_planner_ready_data`** (L359)
    - get_planner_ready_data debe retornar dict con claves esperadas.

  Métodos auxiliares (no test): setUpClass

- **`TestBrainLLMInteraction`** (línea 369) — 6 método(s) de test
  - 2.8.13.5.17 — Verificar interacción con LLM (mocked)

  - **`test_2_8_13_5_17_generate_response_empty_prompt`** (L376)
    - generate_response con prompt vacío debe retornar cadena vacía.

  - **`test_2_8_13_5_17_generate_response_mocked`** (L381)
    - generate_response debe usar ollama.chat y retornar el contenido.

  - **`test_2_8_13_5_17_think_con_direct_action`** (L392)
    - think debe devolver comando [CMD: ...] para acciones legacy.

  - **`test_2_8_13_5_17_think_con_goal`** (L399)
    - think con goal debe registrar objetivo y retornar confirmación.

  - **`test_2_8_13_5_17_interpret_intent_action`** (L406)
    - interpret_intent debe retornar tipo goal cuando la entidad 'chrome'
existe en entities.json como alias de 'Google Chrome'.

Con el conjunto ampliado de entidades (35), 'chrome' se resuelve como
entidad conocida y el sistema retorna type=goal (no action), ya que el
entity resolver intercepta antes de consultar el LLM.

  - **`test_2_8_13_5_17_process_with_htn_disabled`** (L419)
    - process_with_htn debe manejar el caso de HTN deshabilitado.

  Métodos auxiliares (no test): setUpClass

- **`TestBrainExtractSearchQuery`** (línea 429) — 4 método(s) de test
  - 2.8.13.5.18 — Verificar _extract_search_query

  - **`test_2_8_13_5_18_extract_buscar`** (L436)
    - Debe extraer query después de 'buscar'.

  - **`test_2_8_13_5_18_extract_search_english`** (L441)
    - Debe extraer query después de 'search'.

  - **`test_2_8_13_5_18_extract_no_match`** (L446)
    - Sin patrón de búsqueda debe retornar cadena vacía.

  - **`test_2_8_13_5_18_extract_empty`** (L451)
    - Input vacío debe retornar cadena vacía.

  Métodos auxiliares (no test): setUpClass

- **`TestBrainThinkWithImage`** (línea 456) — 4 método(s) de test
  - 2.8.13.5.19 — Verificar think_with_image y analyze_image

  - **`test_2_8_13_5_19_think_with_image_empty_prompt`** (L463)
    - think_with_image con prompt vacío debe retornar mensaje.

  - **`test_2_8_13_5_19_think_with_image_no_image`** (L468)
    - think_with_image sin image_path debe retornar mensaje.

  - **`test_2_8_13_5_19_analyze_image_no_image`** (L473)
    - analyze_image sin image_path debe retornar mensaje.

  - **`test_2_8_13_5_19_analyze_image_no_prompt`** (L478)
    - analyze_image sin analysis_prompt debe retornar mensaje.

  Métodos auxiliares (no test): setUpClass

---

## 📂 `ear/`

1 ficheros de test, 36 métodos de test.

<a name="ear/test-listener"></a>
### `ear\test_listener.py`

**Descripción:** Tests de listener.py (Ear, nodos de audio, calibración, detección, grabación, transcripción).

**Módulos de origen probados:** src.ear.listener

**Clases de test:**

- **`TestAudioCapabilities`** (línea 19) — 2 método(s) de test

  - **`test_defaults`** (L20)

  - **`test_custom_values`** (L30)

- **`TestAudioNode`** (línea 45) — 5 método(s) de test

  - **`test_init`** (L46)

  - **`test_execute`** (L52)

  - **`test_get_preconditions`** (L61)

  - **`test_get_effects`** (L65)

  - **`test_get_cost`** (L69)

- **`TestCalibrationNode`** (línea 74) — 5 método(s) de test

  - **`test_init`** (L75)

  - **`test_execute_with_audio`** (L79)

  - **`test_execute_empty_queue`** (L92)

  - **`test_rms_empty`** (L100)

  - **`test_rms_non_empty`** (L105)

- **`TestDetectionNode`** (línea 113) — 3 método(s) de test

  - **`test_init`** (L114)

  - **`test_execute_detects_speech`** (L119)

  - **`test_execute_timeout`** (L135)

- **`TestRecordingNode`** (línea 148) — 2 método(s) de test

  - **`test_init`** (L149)

  - **`test_execute_records_audio`** (L154)

- **`TestTranscriptionNode`** (línea 192) — 3 método(s) de test

  - **`test_init`** (L194)

  - **`test_execute_test_mode`** (L202)

  - **`test_load_model_fallback`** (L211)

- **`TestEar`** (línea 218) — 16 método(s) de test

  - **`test_init`** (L219)

  - **`test_init_custom_params`** (L229)

  - **`test_get_audio_pipeline`** (L234)

  - **`test_get_pipeline_cost`** (L243)

  - **`test_get_pipeline_preconditions`** (L248)

  - **`test_get_pipeline_effects`** (L253)

  - **`test_check_activation_word_jarvis`** (L258)

  - **`test_check_activation_word_variant`** (L262)

  - **`test_check_activation_word_none`** (L267)

  - **`test_check_activation_word_empty`** (L271)

  - **`test_get_audio_status`** (L275)

  - **`test_listen_returns_none_on_exception`** (L286)

  - **`test_listen_success`** (L293)

  - **`test_process_audio_batch_success`** (L313)

  - **`test_process_audio_batch_failure`** (L321)

  - **`test_process_audio_batch_exception`** (L329)

---

## 📂 `eyes/`

13 ficheros de test, 518 métodos de test.

<a name="eyes/test-application_state_enumeration"></a>
### `eyes\test_application_state_enumeration.py`

**Descripción:** Inspección de estados soportados por el código y los datos (hoja 3.4.1.1).

**Módulos de origen probados:** src.eyes.screen, src.hands.applications_core, src.hands.planner.graph, src.hands.planner.node, src.utils.config

**Clases de test:**

- **`TestPerceptionLayerStateEnum`** (línea 73) — 4 método(s) de test
  - Verifica los miembros del Enum de percepción (eyes/screen.py).

  - **`test_perception_enum_has_exactly_five_members`** (L76)

  - **`test_perception_enum_member_names`** (L80)

  - **`test_perception_enum_known_values`** (L86)

  - **`test_perception_enum_no_extra_members`** (L93)
    - No hay miembros adicionales más allá los 5 declarados.

- **`TestPlanningLayerStateEnum`** (línea 103) — 3 método(s) de test
  - Verifica los miembros del Enum de planificación (applications_core.py).

  - **`test_planning_enum_has_exactly_eight_members`** (L106)

  - **`test_planning_enum_member_names`** (L113)

  - **`test_planning_enum_no_extra_members`** (L120)

- **`TestStateEnumDiscrepancy`** (línea 128) — 4 método(s) de test
  - Documenta que los dos ApplicationState Enum tienen miembros distintos.

D-STATE-TWO-ENUMS: ambos enums comparten el nombre ApplicationState pero
no comparten la misma definición. Solo 3 valores coinciden.

  - **`test_two_enums_have_different_member_sets`** (L135)

  - **`test_three_shared_members`** (L140)

  - **`test_perception_only_members`** (L146)

  - **`test_planning_only_members`** (L152)

- **`TestDataApplicationStates`** (línea 163) — 7 método(s) de test
  - Verifica el diccionario \`states\` booleano por aplicación en
data/knowledge/applications.json.

  - **`test_applications_json_states_exist_for_known_apps`** (L167)

  - **`test_chrome_states_keys`** (L172)

  - **`test_spotify_states_keys`** (L177)

  - **`test_vscode_states_keys`** (L183)

  - **`test_obs_states_keys`** (L189)

  - **`test_data_union_of_states`** (L195)
    - La unión de todas las claves 'states' del data.

  - **`test_data_states_are_boolean_dicts`** (L206)

- **`TestDataCapabilityStateAtoms`** (línea 219) — 2 método(s) de test
  - Verifica los átomos de estado en required_state y effects de
data/knowledge/capabilities.json.

  - **`test_required_state_atoms`** (L227)

  - **`test_effects_atoms`** (L241)

  Métodos auxiliares (no test): caps_data

- **`TestPlannerGraphStateKeys`** (línea 265) — 4 método(s) de test
  - Verifica las claves de hechos de estado codificadas en GraphBuilder.

  - **`test_navigation_graph_has_chrome_state_keys`** (L304)

  - **`test_application_graph_has_app_state_keys`** (L308)

  - **`test_graph_state_keys_partial_overlap_with_data`** (L312)
    - El grafo planificador usa claves de hechos de estado que apenas se
superponen con los átomos de data/knowledge/capabilities.json.

D-STATE-GRAPH-DATA-GAP: claves del grafo que NO aparecen en data:
element_focused, destination_loaded, search_performed, text_typed,
address_bar_clicked, app_closed, app_inactive, app_open, chrome_closed.
El grafo mantiene su propio vocabulario plano parcial con estados
intermedios no modelados en los datos canónicos.

  - **`test_full_graph_state_key_union`** (L339)

  Métodos auxiliares (no test): all_graph_state_keys

- **`TestDataOnlyStateNames`** (línea 354) — 2 método(s) de test
  - Documenta estados declarados en data/knowledge que no existen como miembro
de ninguno de los dos ApplicationState Enum.

D-STATE-DATA-ONLY: 'focused', 'playing', 'streaming', 'recording' aparecen
en data/knowledge/applications.json (states) y/o capabilities.json
(required_state/effects), pero no son miembros de ningún Enum de estado.

  - **`test_data_states_not_in_planning_enum`** (L379)

  - **`test_data_atoms_not_in_perception_enum`** (L389)

  Métodos auxiliares (no test): data_only_states

- **`TestApplicationKnowledgeDeclaredStates`** (línea 402) — 6 método(s) de test
  - Verifica los estados declarados en el modelo real para apps hardcoded.

Chrome y Spotify están hardcoded en ApplicationManager.__init__ con listas
de estados explícitas. Apps reconstruidas desde entities.json carecen de la
clave 'states' y reciben el default [CLOSED].

  - **`test_chrome_declared_states`** (L410)

  - **`test_spotify_declared_states`** (L417)

  - **`test_reconstructed_app_defaults_to_closed`** (L422)
    - YouTube se reconstruye desde entities.json (sin clave 'states') y
recibe [CLOSED] como único estado declarado (contrato
ApplicationKnowledge.__post_init__).

  - **`test_application_knowledge_default_state_is_closed`** (L431)

  - **`test_reconstruct_states_unknown_string_omitted`** (L436)
    - _reconstruct_states omite strings inválidos (no lanza) y devuelve
[CLOSED] si ninguno es válido.

  - **`test_reconstruct_states_valid_strings`** (L442)

- **`TestWorldStateApplicationInfo`** (línea 455) — 2 método(s) de test
  - Verifica que WorldState y ApplicationInfo usan ApplicationState de
screen.py (percepción), no el de applications_core.

  - **`test_application_info_is_screen_enum`** (L459)

  - **`test_world_state_defaults`** (L466)

---

<a name="eyes/test-application_state_separation"></a>
### `eyes\test_application_state_separation.py`

**Descripción:** Verificación de separación de estados de ventana en
data/knowledge/applications.json — hoja 3.4.1.2.

**Módulos de origen probados:** src.utils.config

**Clases de test:**

- **`TestCanonicalWindowFlagsSeparated`** (línea 53) — 5 método(s) de test
  - Las 4 flags genericas {open, active, maximized, focused} estan
presentes y separadas en toda aplicacion conocida.

  - **`test_each_known_app_has_canonical_window_flags`** (L57)
    - Cada app conoce las 4 flags genericas como keys independientes.

  - **`test_canonical_flags_are_distinct_keys`** (L65)
    - Las 4 flags genericas no colisionan ni se fusionan en una sola key.

  - **`test_canonical_flags_are_boolean_and_independent`** (L73)
    - Cada flag canonica es un booleano independiente (separado de `open`).

La separacion significa que `active` no se deduce de `open`: existe
como key propia con valor bool, no implicado ni confundido.

  - **`test_active_exists_as_separate_flag_for_non_chrome_apps`** (L85)
    - `active` (foreground window) corresponde a toda app con ventana: ya
no se confunde con `open`/ausente.

  - **`test_focused_exists_as_separate_flag_for_obs`** (L91)
    - `focused` (teclado encima de la ventana) corresponde a obs_studio.

- **`TestDomainFlagsRemainSeparated`** (línea 96) — 3 método(s) de test
  - Las flags de dominio se mantienen separadas de las genericas.

  - **`test_spotify_only_has_playing_as_domain_flag`** (L99)

  - **`test_obs_only_has_streaming_recording_as_domain_flags`** (L103)

  - **`test_chrome_and_vscode_have_no_domain_flags`** (L107)

- **`TestCanonicalFlagsIntersectionAcrossApps`** (línea 113) — 2 método(s) de test
  - Las 4 flags genericas son el conjunto canonico comun a todas las apps.

  - **`test_canonical_union_is_exactly_the_documented_set`** (L116)

  - **`test_canonical_flags_common_to_all_apps`** (L122)

---

<a name="eyes/test-application_state_unknown"></a>
### `eyes\test_application_state_unknown.py`

**Descripción:** Verificación de que un estado desconocido no se convierte en un estado
valido por defecto — hoja 3.4.1.3.

**Módulos de origen probados:** src.eyes.screen, src.hands.applications_core, src.utils.config

**Clases de test:**

- **`TestVisionOnlyUnknownStateNotOpen`** (línea 57) — 3 método(s) de test
  - 3.4.1.3: un estado desconocido en vision_only no se convierte en OPEN.

  - **`test_unknown_state_resolves_to_closed`** (L74)
    - 'unknown' no debe convertirse en ApplicationState.OPEN.

  - **`test_garbage_state_resolves_to_closed`** (L81)
    - Un string sin significado no debe convertirse en estado valido.

  - **`test_known_states_still_resolve_correctly`** (L88)
    - Estados conocidos deben seguir resolviendose correctamente.

  Métodos auxiliares (no test): _patch_ollama, _make_vision

- **`TestApplicationInfoFromDictUnknownState`** (línea 107) — 5 método(s) de test
  - 3.4.1.3: ApplicationInfo.from_dict ya resolvia estados desconocidos a
CLOSED (no OPEN). Se verifica que el comportamiento sea correcto.

  - **`test_unknown_state_from_dict_defaults_closed`** (L111)

  - **`test_missing_state_from_dict_defaults_closed`** (L115)

  - **`test_none_input_defaults_closed`** (L119)

  - **`test_empty_dict_defaults_closed`** (L123)

  - **`test_valid_states_roundtrip`** (L127)
    - Estados validos se preservan correctamente en from_dict/to_dict.

- **`TestConvertVisualWorldStateUnknownState`** (línea 138) — 3 método(s) de test
  - 3.4.1.3: _convert_visual_world_state resuelve estados desconocidos a
CLOSED en lugar de OPEN.

  - **`test_unknown_state_in_visual_to_world_state`** (L142)
    - Un estado 'unknown' en los datos visuales debe convertirse en CLOSED,
no en OPEN.

  - **`test_garbage_state_in_visual_to_world_state`** (L165)
    - Un estado completamente invalido tambien debe resolver a CLOSED.

  - **`test_known_state_preserves_correct_value`** (L186)
    - Estados conocidos deben resolverse al enum correcto.

- **`TestRegisterCustomApplicationUnknownStates`** (línea 210) — 3 método(s) de test
  - 3.4.1.3: register_custom_application omite (no lanza) estados
desconocidos en 'states' y 'default_state', registrandolos.

  - **`test_register_with_unknown_state_omits_it`** (L214)
    - Un estado desconocido en 'states' debe omitirse, no causar crash.

  - **`test_register_with_only_unknown_states_uses_default`** (L232)
    - Si todos los estados son desconocidos, se usa el default CLOSED.

  - **`test_register_with_unknown_default_state_uses_closed`** (L248)
    - Un default_state desconocido no debe causar crash; se usa CLOSED.

- **`TestUnknownStateRegression`** (línea 268) — 2 método(s) de test
  - Verifica que los cambios de 3.4.1.3 no rompen estados validos.

  - **`test_hands_application_state_valid_values`** (L271)
    - Verifica que todos los valores del Enum de applications_core son
aceptados por ApplicationState().

  - **`test_screen_application_state_valid_values`** (L278)
    - Verifica que todos los valores del Enum de screen son aceptados.

---

<a name="eyes/test-screen"></a>
### `eyes\test_screen.py`

**Descripción:** Tests de screen.py (ApplicationState, ApplicationInfo, WorldState, ScreenAnalyzer, utilidades).

**Módulos de origen probados:** src.eyes.screen

**Clases de test:**

- **`TestApplicationState`** (línea 19) — 2 método(s) de test

  - **`test_values`** (L20)

  - **`test_from_string`** (L27)

- **`TestApplicationInfoInit`** (línea 32) — 3 método(s) de test

  - **`test_defaults`** (L33)

  - **`test_visible_elements_none_becomes_list`** (L44)

  - **`test_custom_values`** (L48)

- **`TestApplicationInfoSerialization`** (línea 69) — 12 método(s) de test

  - **`test_to_dict`** (L70)

  - **`test_from_dict_roundtrip`** (L91)

  - **`test_from_dict_with_valid_state`** (L106)

  - **`test_from_dict_invalid_state_defaults_closed`** (L119)

  - **`test_from_dict_missing_state_defaults_closed`** (L123)

  - **`test_from_dict_none_position_size`** (L127)
    - position=None triggers TypeError → defaults to (0,0).
size='abc' triggers ValueError on int() → crashes.

  - **`test_from_dict_missing_position_size`** (L134)

  - **`test_from_dict_invalid_position_size`** (L139)
    - position=[1] → len 1 → fallback (0,0).
size=[1, 2, 3, 4, 5] → [:2] → (1,2) which has len 2 → passes through.

  - **`test_from_dict_invalid_monitor_raises`** (L146)
    - int('abc') raises ValueError that is NOT caught by from_dict.

  - **`test_from_dict_negative_monitor_clamped`** (L151)

  - **`test_from_dict_none_input`** (L155)

  - **`test_from_dict_empty_dict`** (L160)

- **`TestWorldState`** (línea 166) — 9 método(s) de test

  - **`test_defaults`** (L167)

  - **`test_to_dict`** (L178)

  - **`test_from_dict_roundtrip`** (L189)

  - **`test_from_dict_none_input`** (L206)

  - **`test_from_dict_app_info_conversion`** (L211)

  - **`test_from_dict_non_dict_app_data`** (L220)

  - **`test_from_dict_invalid_available_monitors`** (L226)

  - **`test_from_dict_active_monitor_max_1`** (L231)

  - **`test_from_dict_active_monitor_string`** (L236)

- **`TestGetMonitorNumber`** (línea 242) — 5 método(s) de test

  - **`test_none_monitor`** (L243)

  - **`test_monitor_id`** (L246)

  - **`test_fallback_to_index`** (L251)

  - **`test_no_valid_attrs`** (L257)

  - **`test_screen_number_fallback`** (L263)

- **`TestGetAvailableMonitorNumbers`** (línea 271) — 3 método(s) de test

  - **`test_returns_list`** (L272)

  - **`test_with_mocked_manager`** (L278)

  - **`test_manager_raises_returns_fallback`** (L286)

- **`TestScreenAnalyzer`** (línea 292) — 16 método(s) de test

  - **`test_init`** (L293)

  - **`test_get_vision_lazy_init`** (L298)

  - **`test_get_vision_caches`** (L306)

  - **`test_get_vision_import_error`** (L312)

  - **`test_analyze_application_state_empty_name`** (L319)

  - **`test_analyze_application_state_none_name`** (L325)

  - **`test_analyze_application_state_vision_available`** (L332)

  - **`test_analyze_application_state_vision_returns_dict`** (L340)

  - **`test_analyze_application_state_vision_exception_falls_back`** (L349)

  - **`test_analyze_application_state_no_vision_fallback`** (L356)

  - **`test_get_known_applications`** (L362)

  - **`test_detect_focused_application_no_window`** (L371)

  - **`test_get_active_monitor_exception`** (L381)

  - **`test_get_calibrated_elements_no_data`** (L388)

  - **`test_get_known_urls_empty`** (L395)

  - **`test_get_system_resources_exception`** (L402)

---

<a name="eyes/test-screen_capture"></a>
### `eyes\test_screen_capture.py`

**Descripción:** Tests de screen_capture.py (ScreenCapture y get_screen_capture).

**Módulos de origen probados:** src.eyes, src.eyes.screen_capture

**Clases de test:**

- **`TestScreenCaptureInit`** (línea 13) — 2 método(s) de test

  - **`test_analyzer_is_none`** (L14)

  - **`test_init_does_not_lazy_init`** (L18)

- **`TestScreenCaptureGetAnalyzer`** (línea 23) — 3 método(s) de test

  - **`test_lazy_init_success`** (L24)

  - **`test_lazy_init_import_error`** (L32)

  - **`test_cached_after_first_call`** (L42)

- **`TestCaptureMonitor`** (línea 49) — 3 método(s) de test

  - **`test_monitor_not_found_returns_none`** (L50)

  - **`test_capture_monitor_success`** (L59)

  - **`test_capture_monitor_exception_returns_none`** (L78)

- **`TestCaptureRegion`** (línea 87) — 2 método(s) de test

  - **`test_capture_region_success`** (L89)

  - **`test_capture_region_exception_returns_none`** (L103)

- **`TestCaptureElement`** (línea 109) — 2 método(s) de test

  - **`test_capture_element_not_dict_returns_none`** (L110)

  - **`test_capture_element_valid_coords`** (L116)

- **`TestCaptureActiveWindow`** (línea 127) — 4 método(s) de test

  - **`test_no_active_window_returns_none`** (L128)

  - **`test_capture_active_window_success`** (L138)

  - **`test_capture_active_window_invalid_dims`** (L157)

  - **`test_capture_active_window_exception`** (L171)

- **`TestScreenCaptureGetWorldState`** (línea 181) — 2 método(s) de test

  - **`test_get_world_state_no_analyzer`** (L182)

  - **`test_get_world_state_with_analyzer`** (L190)

- **`TestScreenCaptureGetApplicationState`** (línea 198) — 2 método(s) de test

  - **`test_get_application_state_no_analyzer`** (L199)

  - **`test_get_application_state_with_analyzer`** (L206)

- **`TestGetScreenCapture`** (línea 214) — 2 método(s) de test

  - **`test_returns_instance`** (L215)

  - **`test_singleton`** (L219)

---

<a name="eyes/test-state_comparison"></a>
### `eyes\test_state_comparison.py`

**Descripción:** Tests para la comparación de estado declarado vs. estado observable — hoja 3.4.3.1.

**Módulos de origen probados:** src.eyes.screen, src.utils.config

**Clases de test:**

- **`TestCanonicalWindowFlagsConstant`** (línea 47) — 3 método(s) de test
  - La constante CANONICAL_WINDOW_FLAGS define exactamente las 4 flags genericas.

  - **`test_has_exactly_four_flags`** (L50)

  - **`test_flags_are_the_documented_set`** (L53)

  - **`test_application_state_to_window_flags_covers_all_states`** (L56)
    - El mapping cubre todos los valores del enum ApplicationState.

- **`TestObservableStateToFlags`** (línea 61) — 8 método(s) de test
  - ``observable_state_to_flags`` mapea cada ApplicationState a las flags canonicas.

  - **`test_returns_all_four_canonical_flags`** (L65)

  - **`test_all_values_are_boolean`** (L70)

  - **`test_matches_expected_mapping`** (L76)

  - **`test_closed_all_false`** (L79)

  - **`test_active_implies_active_flag`** (L83)

  - **`test_maximized_implies_maximized_and_active`** (L90)

  - **`test_minimized_open_true_rest_false`** (L97)

  - **`test_returns_copy_not_shared_reference`** (L101)
    - La función no debe retornar una referencia al dict interno del mapping.

- **`TestCompareDeclaredAndObservable`** (línea 110) — 19 método(s) de test
  - ``compare_declared_and_observable_state`` reporta coincidencias y discrepancias.

  - **`test_exact_match_closed`** (L115)

  - **`test_exact_match_open`** (L122)

  - **`test_exact_match_active`** (L128)

  - **`test_exact_match_maximized`** (L134)

  - **`test_exact_match_minimized`** (L140)

  - **`test_match_with_domain_flags_ignored`** (L146)
    - Flags de dominio (playing, streaming, recording) no afectan el match.

  - **`test_discrepancy_open_flag`** (L158)
    - Declared dice cerrado (open=False) pero vision ve OPEN (open=True).

  - **`test_discrepancy_active_flag`** (L167)
    - Declared tiene active=False pero vision ve ACTIVE (active=True).

  - **`test_discrepancy_maximized_flag`** (L177)
    - Declared no tiene maximized=True pero vision ve MAXIMIZED.

  - **`test_multiple_discrepancies`** (L185)
    - Varias flags discrepantes a la vez.

  - **`test_discrepancy_focused_flag`** (L194)
    - Declared tiene focused=False pero vision ve ACTIVE (focused=True).

  - **`test_empty_declared_dict_all_assumed_false`** (L204)
    - Si el diccionario declarado está vacío, todas las flags se asumen False.

  - **`test_empty_declared_dict_vs_open_all_discrepant`** (L210)

  - **`test_missing_canonical_flag_assumed_false`** (L216)
    - Una flag canónica faltante en declared se asume False.

  - **`test_missing_flag_vs_state_requiring_it`** (L224)
    - Si falta una flag y el estado observable la requiere en True, hay discrepancia.

  - **`test_non_boolean_values_coerced_to_bool`** (L231)
    - Valores no booleanos en declared se convierten con bool().

  - **`test_result_structura_con_campos_requeridos`** (L240)
    - El resultado siempre contiene las 5 claves requeridas.

  - **`test_observable_flags_en_resultado`** (L248)
    - El resultado incluye las flags derivadas del estado observable.

  - **`test_declared_flags_solo_canonical`** (L253)
    - declared_flags en el resultado solo contiene las 4 flags canónicas.

- **`TestCompareWithApplicationsJsonModel`** (línea 264) — 2 método(s) de test
  - Verifica el comportamiento contra el modelo real de applications.json.

  - **`test_all_apps_start_with_all_false_flags`** (L277)
    - Las aplicaciones conocidas inicialmente declaran todas las flags a False (CLOSED).

  - **`test_domain_flags_do_not_break_closed_match`** (L284)
    - Las flags de dominio coexistiendo no rompen el match con CLOSED.

  Métodos auxiliares (no test): _load_app_states

- **`TestReconcileObservableWithDeclared`** (línea 292) — 15 método(s) de test
  - ``reconcile_observable_with_declared_state`` resuelve discrepancias priorizando la visión.

  - **`test_match_true_returns_reconciled_false`** (L297)
    - Si match es True, reconciled=False y las flags no cambian.

  - **`test_match_true_preserves_domain_flags`** (L306)
    - Flags de dominio se conservan cuando no hay discrepancia.

  - **`test_original_declared_not_mutated_on_match`** (L317)
    - El diccionario declarado original no se muta aunque match sea True.

  - **`test_reconciled_true_when_discrepancy`** (L326)
    - Si hay discrepancia, reconciled=True.

  - **`test_reconciled_flags_update_canonical_to_observable`** (L333)
    - Las 4 flags canónicas se actualizan al estado observable.

  - **`test_reconciled_preserves_domain_flags`** (L343)
    - Flags de dominio se conservan intactas durante la reconciliación.

  - **`test_reconciled_preserves_other_keys`** (L354)
    - Claves no canónicas no estándar se conservan.

  - **`test_original_declared_not_mutated_on_reconcile`** (L364)
    - El diccionario declarado original no se muta durante reconciliación.

  - **`test_reconciled_flags_is_new_dict`** (L371)
    - reconciled_flags es un dict nuevo, no referencia al original.

  - **`test_discrepancies_included_in_result`** (L381)
    - El resultado incluye el detalle de discrepancias flag a flag.

  - **`test_all_five_keys_in_result`** (L394)
    - El resultado siempre contiene las 7 claves requeridas.

  - **`test_observable_state_preserved`** (L404)
    - El estado observable original se incluye en el resultado.

  - **`test_declared_flags_reflects_pre_reconcile_state`** (L410)
    - declared_flags muestra el estado ANTES de la reconciliación.

  - **`test_empty_declared_dict_reconciles_to_observable`** (L427)
    - Diccionario vacío se reconcilia completamente al observable.

  - **`test_missing_canonical_flags_assumed_false_then_reconciled`** (L436)
    - Flags canónicas faltantes se asumen False y luego se actualizan si observables difieren.

---

<a name="eyes/test-ui_element_behavior"></a>
### `eyes\test_ui_element_behavior.py`

**Descripción:** Tests de comportamiento de elementos UI — unidad 3.4.4.2
(FASE 3.4.4 — Tests de elementos UI).

**Módulos de origen probados:** src.hands.applications_core, src.hands.planner.application_integration, src.hands.planner.node, src.utils.config, src.utils.ui_element_model

**Clases de test:**

- **`TestUIElementIsCalibrated`** (línea 95) — 11 método(s) de test
  - Verifica ``UIElement.is_calibrated()`` (applications_core.py:95).

El método:
- Devuelve ``False`` si ``coordinates`` es ``None``.
- Si ``coordinates`` es dict, comprueba que existan ambas claves ``"x"`` y
  ``"y"``.
- Si ``coordinates`` no es dict, devuelve ``bool(coordinates)``.

  - **`test_coordinates_none`** (L105)

  - **`test_coordinates_dict_with_xy`** (L111)

  - **`test_coordinates_dict_with_extra_keys`** (L117)

  - **`test_coordinates_dict_missing_y`** (L123)

  - **`test_coordinates_dict_missing_x`** (L129)

  - **`test_coordinates_empty_dict`** (L135)

  - **`test_coordinates_dict_zero_values`** (L141)
    - x=0, y=0 sigue siendo calibrado: la presencia de claves es lo que
importa, no el valor.

  - **`test_coordinates_non_dict_truthy`** (L149)
    - Lista no vacía -> bool() es True.

  - **`test_coordinates_non_dict_falsy`** (L156)
    - Lista vacía -> bool() es False.

  - **`test_coordinates_non_dict_string`** (L163)
    - String no vacío -> bool() es True.

  - **`test_coordinates_non_dict_empty_string`** (L170)

- **`TestUIElementDefaults`** (línea 181) — 5 método(s) de test
  - Verifica los valores por defecto de los campos del dataclass UIElement.

  - **`test_default_description_is_empty_string`** (L184)

  - **`test_default_required_capability_is_none`** (L190)

  - **`test_default_coordinates_is_none`** (L196)

  - **`test_default_screen_is_zero`** (L202)

  - **`test_default_calibration_data_is_none`** (L208)

- **`TestSerializeUiElementWithData`** (línea 219) — 9 método(s) de test
  - Verifica ``_serialize_ui_element`` con coordinates, screen,
calibration_data y required_capability.

Solo las claves con valores no-default se incluyen condicionalmente;
``name``, ``type``, ``description`` y ``required_capability`` siempre están.

  - **`test_serializes_coordinates`** (L227)

  - **`test_serializes_required_capability`** (L238)

  - **`test_serializes_none_required_capability`** (L250)

  - **`test_serializes_non_default_screen`** (L257)

  - **`test_omits_default_screen`** (L264)

  - **`test_serializes_calibration_data`** (L271)

  - **`test_omits_none_coordinates`** (L281)

  - **`test_omits_none_calibration_data`** (L288)

  - **`test_always_has_core_keys`** (L295)

- **`TestReconstructUiElementsCapability`** (línea 309) — 9 método(s) de test
  - Verifica ``_reconstruct_ui_elements`` con ``required_capability``
válida/inválida y preservación de coordinates/screen/calibration_data.

  - **`test_valid_required_capability`** (L313)

  - **`test_invalid_required_capability_becomes_none`** (L325)

  - **`test_no_required_capability_is_none`** (L335)

  - **`test_preserves_coordinates`** (L343)

  - **`test_preserves_screen`** (L353)

  - **`test_preserves_calibration_data`** (L361)

  - **`test_description_default_empty`** (L371)

  - **`test_description_from_input`** (L378)

  - **`test_all_capability_values_resolve`** (L387)
    - Todos los valores de ApplicationCapability son resolubles.

- **`TestApplicationKnowledgeGetUiElement`** (línea 409) — 7 método(s) de test
  - Verifica ``ApplicationKnowledge.get_ui_element(element_name)``.

  - **`test_found_exact_name`** (L412)

  - **`test_found_case_insensitive`** (L422)

  - **`test_found_with_whitespace`** (L432)

  - **`test_not_found`** (L441)

  - **`test_empty_ui_elements`** (L449)

  - **`test_none_input`** (L453)

  - **`test_multiple_elements_returns_first_match`** (L461)

- **`TestApplicationKnowledgeGetCalibratedElements`** (línea 479) — 7 método(s) de test
  - Verifica ``ApplicationKnowledge.get_calibrated_elements()``.

  - **`test_no_coord_manager_returns_empty`** (L482)

  - **`test_coord_manager_none_returns_empty`** (L496)

  - **`test_element_not_calibrated_excluded`** (L510)

  - **`test_element_calibrated_included`** (L531)

  - **`test_resource_none_excluded`** (L553)

  - **`test_uses_metadata_entity_id`** (L571)

  - **`test_falls_back_to_name_without_entity_id`** (L591)

- **`TestUIElementDataIsCalibrated`** (línea 617) — 8 método(s) de test
  - Verifica ``UIElementData.is_calibrated()`` (ui_element_model.py:76).

  - **`test_calibrated_flag_true`** (L620)

  - **`test_calibrated_flag_true_ignores_coordinates`** (L626)

  - **`test_calibrated_flag_false_with_classic_coordinates`** (L632)

  - **`test_calibrated_flag_false_with_multiscreen_coordinates`** (L640)

  - **`test_calibrated_flag_false_without_coordinates`** (L648)

  - **`test_calibrated_flag_false_empty_dict`** (L654)

  - **`test_calibrated_flag_false_multiscreen_short_value`** (L660)
    - Coordenada de pantalla con menos de 2 valores -> False.

  - **`test_calibrated_flag_false_non_xy_dict`** (L669)
    - Dict sin x/y ni claves s* -> False.

- **`TestUIElementDataCoordinatesCalibrated`** (línea 683) — 12 método(s) de test
  - Verifica ``UIElementData._coordinates_calibrated()`` directamente.

  - **`test_none`** (L686)

  - **`test_empty_dict`** (L691)

  - **`test_non_dict`** (L696)

  - **`test_classic_xy`** (L703)

  - **`test_classic_xy_non_numeric`** (L710)

  - **`test_classic_xy_zero`** (L720)

  - **`test_classic_missing_y`** (L727)

  - **`test_multiscreen_valid`** (L734)

  - **`test_multiscreen_short`** (L744)

  - **`test_multiscreen_non_numeric`** (L751)

  - **`test_no_screen_keys`** (L758)
    - Dict con claves que no empiezan por 's' ni tienen x/y -> False.

  - **`test_mixed_screens_some_valid`** (L766)

- **`TestUIElementDataHasValidGeometry`** (línea 777) — 8 método(s) de test
  - Verifica ``UIElementData.has_valid_geometry()``.

  - **`test_bbox_valid`** (L780)

  - **`test_bbox_short`** (L786)

  - **`test_bbox_non_numeric`** (L792)

  - **`test_bbox_none_center_valid`** (L798)

  - **`test_bbox_none_center_short`** (L804)

  - **`test_bbox_none_center_empty_falls_to_is_calibrated`** (L810)

  - **`test_bbox_none_center_empty_with_coordinates`** (L817)

  - **`test_bbox_none_center_empty_without_coordinates`** (L826)

- **`TestUIElementDataMatchesName`** (línea 837) — 7 método(s) de test
  - Verifica ``UIElementData.matches_name(name)``.

  - **`test_match_by_exact_name`** (L840)

  - **`test_match_by_name_case_insensitive`** (L846)

  - **`test_match_by_name_with_whitespace`** (L852)

  - **`test_match_by_type_and_text`** (L858)
    - Cuando name no coincide, se busca en 'type text'.

  - **`test_no_match`** (L866)

  - **`test_empty_target`** (L872)

  - **`test_name_takes_precedence_over_haystack`** (L880)

- **`TestUIElementDataNormalizeName`** (línea 895) — 9 método(s) de test
  - Verifica ``UIElementData.normalize_name(name)`` (staticmethod).

  - **`test_simple`** (L898)

  - **`test_multiple_separators`** (L903)

  - **`test_whitespace_trimmed`** (L908)

  - **`test_empty_string`** (L913)

  - **`test_none`** (L918)

  - **`test_accents`** (L923)

  - **`test_alphanumeric_preserved`** (L929)

  - **`test_dots_and_dashes`** (L934)

  - **`test_leading_trailing_underscores_stripped`** (L939)

- **`TestUIElementDataFromDict`** (línea 949) — 5 método(s) de test
  - Verifica ``UIElementData.from_dict(data)``.

  - **`test_basic_from_dict`** (L952)

  - **`test_extra_keys_filtered`** (L962)

  - **`test_non_dict_input`** (L973)

  - **`test_none_input`** (L981)

  - **`test_preserves_all_known_fields`** (L988)

- **`TestUIElementDataFromCompactDict`** (línea 1026) — 11 método(s) de test
  - Verifica ``UIElementData.from_compact_dict(data)``.

  - **`test_full_data`** (L1029)

  - **`test_name_inferred_from_text`** (L1051)

  - **`test_name_inferred_from_type`** (L1059)

  - **`test_name_inferred_default`** (L1065)

  - **`test_non_dict_input`** (L1071)

  - **`test_bbox_invalid`** (L1078)

  - **`test_bbox_short`** (L1086)

  - **`test_center_invalid`** (L1094)

  - **`test_center_short`** (L1102)

  - **`test_confidence_default`** (L1110)

  - **`test_interactive_default`** (L1116)

- **`TestUIElementDataToDict`** (línea 1127) — 2 método(s) de test
  - Verifica ``UIElementData.to_dict()`` devuelve todos los campos canónicos.

  - **`test_all_fields_present`** (L1130)

  - **`test_values_match`** (L1143)

- **`TestCreateUiElementNodeFull`** (línea 1174) — 29 método(s) de test
  - Verifica todas las propiedades del nodo creado por
``_create_ui_element_node`` (application_integration.py:437).

  - **`test_node_id_format`** (L1189)

  - **`test_node_name`** (L1201)

  - **`test_node_description`** (L1213)

  - **`test_node_parameters_type`** (L1225)

  - **`test_node_parameters_type_unknown_when_not_found`** (L1237)

  - **`test_node_parameters_screen`** (L1244)

  - **`test_node_parameters_screen_none_when_not_found`** (L1256)

  - **`test_node_parameters_calibrated_false`** (L1263)

  - **`test_node_parameters_calibrated_true`** (L1275)

  - **`test_node_parameters_capability`** (L1288)

  - **`test_node_preconditions_app_open`** (L1300)

  - **`test_node_preconditions_calibrated`** (L1312)

  - **`test_node_preconditions_no_calibrated_when_uncalibrated`** (L1325)

  - **`test_node_effects_available`** (L1337)

  - **`test_node_effects_no_available_when_not_found`** (L1349)

  - **`test_node_effects_calibrated`** (L1361)

  - **`test_node_cost_is_zero`** (L1374)

  - **`test_node_dependencies_empty`** (L1386)

  - **`test_node_application`** (L1398)

  - **`test_node_ui_element`** (L1410)

  - **`test_node_metadata_source`** (L1422)

  - **`test_node_metadata_known_true`** (L1434)

  - **`test_node_metadata_known_false`** (L1446)

  - **`test_node_metadata_required_by_capabilities`** (L1458)

  - **`test_node_type_resource_when_not_found`** (L1470)

  - **`test_node_type_ui_element_when_found`** (L1483)

  - **`test_app_name_normalized_in_id`** (L1496)

  - **`test_element_name_with_spaces_normalized`** (L1511)

  - **`test_capability_from_capability_def_object`** (L1524)
    - Cuando cap_def es un ApplicationCapabilityDef, se extrae su capability.

  Métodos auxiliares (no test): _make_integrator

---

<a name="eyes/test-ui_element_type_description"></a>
### `eyes\test_ui_element_type_description.py`

**Descripción:** Tests de verificación de ``type`` y ``description`` de ``ui_elements`` — unidad 3.4.2.2
(FASE 3.4.2 — UI elements).

**Módulos de origen probados:** src.eyes.vision, src.hands.applications_core, src.hands.coordinate_manager, src.hands.planner.application_integration, src.utils.config, src.utils.ui_element_model

**Clases de test:**

- **`TestTypeInDataSources`** (línea 100) — 4 método(s) de test
  - Verifica los valores reales de ``type`` en los archivos JSON de datos.

  - **`test_knowledge_json_type_values_are_finite_set`** (L103)
    - En ``data/knowledge/applications.json`` los valores de ``type``
son exactamente: ``input``, ``button``, ``panel``.

  - **`test_macros_coords_type_values`** (L116)
    - En ``data/macros_coords.json`` los valores de ``type`` son
``input``, ``button`` y ``region``.

  - **`test_all_knowledge_elements_have_non_empty_type`** (L131)
    - Todo elemento en el JSON de conocimiento tiene type no vacío.

  - **`test_all_macros_coords_elements_have_non_empty_type`** (L141)
    - Todo elemento en macros_coords.json tiene type no vacío.

- **`TestTypeIsFreeFormString`** (línea 156) — 4 método(s) de test
  - Verifica que ``type`` es un string libre sin validación por enum
central. No existe un enum ``UIElementType`` / ``ElementType`` en el
sistema.

  - **`test_ui_element_type_is_str_without_enum`** (L162)
    - ``UIElement.type`` es ``str`` (free-form), sin enum, sin default
explícito — es el segundo campo posicional requerido del dataclass.

  - **`test_ui_element_data_type_defaults_to_unknown`** (L173)
    - ``UIElementData.type`` es ``str`` con default ``"unknown"``.

No hay validación de valores permitidos: cualquier string es aceptado.

  - **`test_vision_ui_element_type_defaults_to_unknown`** (L185)
    - El ``UIElement`` de visión (hereda de ``UIElementData``) también
usa ``type: str = "unknown"`` sin enum.

  - **`test_no_central_enum_for_element_types`** (L193)
    - No existe un enum central que valide los valores de ``type`` de
elementos UI. El type es libre en todos los modelos.

- **`TestTypeConsumptionInCoordinateManager`** (línea 217) — 7 método(s) de test
  - Verifica cómo el campo ``type`` es consumido de forma real en
``coordinate_manager.py`` para tomar decisiones.

  - **`test_resource_type_for_element_region_is_region`** (L222)
    - ``_resource_type_for_element('region')`` -> ``ResourceType.REGION``.

  - **`test_resource_type_for_element_non_region_is_element`** (L227)
    - ``_resource_type_for_element('button')`` / ``'input'`` -> ELEMENT.

  - **`test_infer_element_type_button`** (L234)
    - ``_infer_element_type`` infiere ``button`` desde el nombre.

  - **`test_infer_element_type_input`** (L240)
    - ``_infer_element_type`` infiere ``input`` desde el nombre.

  - **`test_infer_element_type_no_match_defaults_to_element`** (L246)
    - Si el nombre no coincide con ningún keyword, devuelve ``element``.

  - **`test_validate_resource_focus_accepts_input`** (L252)
    - ``validate_resource_for_action('focus_...')`` acepta elementos
de type ``input`` pero rechaza ``button``.

  - **`test_get_calibration_strategy_mapping`** (L288)
    - ``get_calibration_strategy`` mapea type strings a estrategias
reales definidas en el código.

- **`TestTypeInReconstructUiElements`** (línea 306) — 2 método(s) de test
  - ``_reconstruct_ui_elements`` requiere ``type`` no vacío; items sin
type se omiten silenciosamente.

  - **`test_reconstruct_requires_type`** (L311)
    - Items sin ``type`` se omiten.

  - **`test_reconstruct_type_preserved_as_string`** (L322)
    - El type reconstruido preserva el valor string del dict.

- **`TestTypeInCreateUiElementNode`** (línea 333) — 2 método(s) de test
  - ``_create_ui_element_node`` extrae ``type`` del elemento y lo coloca
en los parámetros del nodo; si no hay elemento, default ``"unknown"``.

  - **`test_type_default_unknown_when_no_element`** (L338)
    - Sin elemento encontrado, el type del nodo es ``"unknown"``.

  - **`test_type_extracted_from_element_dict`** (L353)
    - Cuando ui_elements es un dict (formato JSON) y el elemento existe,
el type se extrae correctamente.

- **`TestTypeInVisionDetection`** (línea 372) — 2 método(s) de test
  - ``detect_ui_elements`` en ``vision.py`` produce ``type`` como string
libre extraído del LLM; si falta, default ``"other"``.

  - **`test_vision_detect_ui_elements_type_is_freeform`** (L377)
    - El schema de ``detect_ui_elements`` define ``type`` como
``{"type": "string"}`` (no enum). El código usa
``str(item.get("type", "other"))``.

  - **`test_vision_analyze_image_schema_includes_type`** (L393)
    - El schema de ``analyze_image`` también define ``type`` como string
(no enum).

- **`TestDescriptionInDataSources`** (línea 408) — 2 método(s) de test
  - Verifica que ``description`` está presente en todos los elementos
UI de los archivos JSON de datos.

  - **`test_knowledge_json_has_description_all_elements`** (L413)
    - Todo elemento en ``applications.json`` tiene ``description`` no vacío.

  - **`test_macros_coords_has_description_all_elements`** (L426)
    - Todo elemento en ``macros_coords.json`` tiene ``description``.

- **`TestDescriptionInUIElementData`** (línea 440) — 4 método(s) de test
  - ``UIElementData`` (modelo canónico) SÍ tiene y preserva ``description``.

  - **`test_ui_element_data_has_description_field`** (L444)
    - ``UIElementData`` define ``description: str = ""``.

  - **`test_from_dict_preserves_description`** (L451)
    - ``UIElementData.from_dict`` preserva ``description`` del dict.

  - **`test_from_compact_dict_does_not_set_description`** (L459)
    - ``UIElementData.from_compact_dict`` NO establece ``description``,
incluso si el dict de origen lo incluye (el output del LLM de visión
no incluye description).

  - **`test_to_dict_includes_description`** (L472)
    - ``UIElementData.to_dict()`` incluye ``description``.

- **`TestDescriptionInUIResource`** (línea 483) — 3 método(s) de test
  - ``UIResource`` (coordinate_manager) SÍ tiene y preserva ``description``
cuando se crea desde conocimiento.

  - **`test_ui_resource_has_description_field`** (L488)
    - ``UIResource`` dataclass define ``description: str = ''``.

  - **`test_create_resource_from_knowledge_preserves_description`** (L495)
    - ``_create_resource_from_knowledge`` preserva ``description`` del
elemento JSON (macros_coords.json).

  - **`test_create_resource_from_knowledge_defaults_empty_description`** (L513)
    - Sin ``description`` en el JSON, el recurso usa ``""``.

- **`TestDescriptionInApplicationModel`** (línea 530) — 5 método(s) de test
  - Verifica que ``description`` fluye de forma coherente en el modelo
``UIElement`` de ``applications_core.py`` y en todas las rutas que
derivan de él (serialize, reconstruct, get_application_ui_elements,
register_custom_application).

Discrepancia D-UI-DESCRIPTION-LOST resuelta: ``description`` está presente
en el JSON de conocimiento, en UIElementData, en UIResource y ahora tambien
en UIElement y en todas sus rutas de serializacion/reconstruccion.

  - **`test_ui_element_has_description_field`** (L541)
    - ``UIElement`` dataclass tiene campo ``description`` con default "".

  - **`test_ui_element_accepts_description`** (L547)
    - Pasar ``description`` al constructor de ``UIElement`` funciona y se
conserva en la instancia.

  - **`test_serialize_ui_element_includes_description`** (L555)
    - ``_serialize_ui_element`` incluye ``description`` en su output.

  - **`test_get_application_ui_elements_includes_description`** (L566)
    - ``get_application_ui_elements`` incluye ``description``.

  - **`test_reconstruct_ui_elements_captures_description`** (L578)
    - ``_reconstruct_ui_elements`` captura ``description`` del dict de
entrada y la conserva en el UIElement resultante.

- **`TestRegisterCustomApplicationWithDescription`** (línea 596) — 2 método(s) de test
  - ``register_custom_application`` acepta ``description`` en
``ui_elements`` (formato lista) sin fallar, porque ``UIElement`` ahora
tiene el campo ``description`` y se incluye en element_kwargs.

  - **`test_register_succeeds_with_description_in_ui_elements`** (L602)
    - Pasar ui_elements con ``description`` (formato lista) retorna True —
el campo description se conserva en el UIElement.

  - **`test_register_succeeds_without_description`** (L620)
    - Sin ``description`` en ui_elements, el registro funciona.

- **`TestDescriptionInCreateUiElementNode`** (línea 637) — 2 método(s) de test
  - ``_create_ui_element_node`` genera su propia ``description`` en el
nodo (``f"Elemento UI {element_name} de {app_name}"``) en lugar de usar
la del JSON conocimiento.

  - **`test_node_description_is_generated_not_from_json`** (L643)
    - La description del nodo es generada, no leída del JSON.

  - **`test_node_description_not_in_parameters`** (L660)
    - La description del JSON no aparece en los parámetros del nodo.

- **`_FakeApp`** (línea 344) — 0 método(s) de test

  Métodos auxiliares (no test): get_ui_element

---

<a name="eyes/test-ui_elements_structure"></a>
### `eyes\test_ui_elements_structure.py`

**Descripción:** Tests de verificacion de la estructura REAL de ``ui_elements`` — unidad 3.4.2.1
(FASE 3.4.2 — UI elements).

**Módulos de origen probados:** src.eyes.vision, src.hands.applications_core, src.hands.executor, src.hands.planner.application_integration, src.hands.planner.node, src.memory.storage, src.utils.config

**Clases de test:**

- **`TestKnowledgeJsonUiElementsStructure`** (línea 71) — 9 método(s) de test
  - Verifica la estructura REAL de ``ui_elements`` en el fichero de
conocimiento declarativo.

El formato real es **dict-of-dicts**: la clave externa es el nombre del
elemento y el valor es un dict con exactamente ``{type, description}``.

  - **`test_file_exists`** (L79)

  - **`test_all_apps_have_ui_elements`** (L82)
    - Todas las aplicaciones conocidas declaran ui_elements.

  - **`test_ui_elements_is_dict_of_dicts_across_all_apps`** (L90)
    - En TODAS las apps, ui_elements es un dict-of-dicts (no una lista).

Contrario al formato esperado por ``_reconstruct_ui_elements``
(que pide lista) y por ``UIElement`` (modelo tipo list).

  - **`test_each_element_has_exactly_type_and_description`** (L109)
    - Cada elemento del JSON tiene EXACTAMENTE las claves {type, description}.

La estructura real NO incluye 'name' como clave interna: el nombre
es la clave externa del dict.

  - **`test_type_is_non_empty_string_for_all_elements`** (L123)
    - El campo 'type' es un string no vacio en todos los elementos.

  - **`test_description_is_non_empty_string_for_all_elements`** (L133)
    - El campo 'description' es un string no vacio en todos los elementos.

La descripcion existe en el JSON de conocimiento PERO el modelo
``UIElement`` no la preserva (ver TestUIElementModelFields).

  - **`test_element_names_match_calibration_needed`** (L147)
    - Los elementos referenciados en 'calibration_needed' existen en
'ui_elements' en todas las apps donde aplica.

  - **`test_specific_element_names_per_app`** (L160)
    - Verifica los nombres de elementos UI conocidos por app.

  - **`test_chrome_address_bar_structure`** (L177)
    - El elemento 'address_bar' de chrome: {type: input, description: ...}.

- **`TestUIElementModelFields`** (línea 189) — 3 método(s) de test
  - Verifica los campos REALES del modelo ``UIElement`` y confirma que
``description`` (presente en el JSON de conocimiento) ES un campo del
modelo, por lo que ya no se pierde al reconstruir objetos UIElement.

Discrepancia D-UI-DESCRIPTION-LOST resuelta.

  - **`test_uint_element_fields`** (L197)
    - UIElement tiene exactamente estos campos (en orden deDeclaracion).

  - **`test_description_is_a_field`** (L205)
    - 'description' ES un campo del modelo UIElement.

  - **`test_application_knowledge_ui_elements_is_optional_list`** (L213)
    - ApplicationKnowledge.ui_elements esta tipado como
Optional[List[UIElement]] — una LISTA, no un dict.

Esto es incompatible con el formato dict-of-dicts usado en el
JSON de conocimiento (D-UI-FORMAT-MISMATCH).

- **`TestReconstructUiElementsFormatMismatch`** (línea 229) — 6 método(s) de test
  - Documenta D-UI-FORMAT-MISMATCH: ``_reconstruct_ui_elements`` espera una
LISTA de dicts (cada uno con 'name' y 'type'), pero el JSON de conocimiento
usa un DICT-of-dicts. Si se pasara el formato del JSON, todos los
elementos se perderian silenciosamente.

  - **`test_reconstruct_returns_empty_for_dict_format`** (L236)
    - Si recibe el dict-of-dicts del JSON, devuelve [] (elementos perdidos).

El codigo comprueba ``isinstance(elements_data, list)``; un dict no
pasa ese filtro.

  - **`test_reconstruct_works_with_list_of_dicts`** (L250)
    - El formato que expecta el codigo: lista de dicts con name+type.

  - **`test_reconstruct_preserves_description_field`** (L263)
    - Con formato lista, _reconstruct_ui_elements captura 'description'
del dict de entrada y la conserva en el UIElement resultante
(coherencia D-UI-DESCRIPTION resuelta).

  - **`test_reconstruct_skips_items_without_name`** (L276)
    - Items sin 'name' se omiten silenciosamente.

  - **`test_reconstruct_skips_items_without_type`** (L286)
    - Items sin 'type' se omiten silenciosamente.

  - **`test_reconstruct_returns_empty_for_non_list`** (L296)
    - Cualquier entrada que no sea lista devuelve [].

- **`TestSerializeUiElementFormat`** (línea 306) — 1 método(s) de test
  - Documenta que ``_serialize_ui_element`` (usado por register_application
para persistir entities) NO incluye 'description', coincidiendo con el
modelo UIElement que tampoco lo tiene.

  - **`test_serialize_output_keys`** (L312)
    - _serialize_ui_element produce: name, type, description,
required_capability (y coordinates/screen/calibration_data solo si
tienen valor). description siempre esta presente (coherencia).

- **`TestGetApplicationUiElementsOutputFormat`** (línea 335) — 2 método(s) de test
  - Verifica el formato REAL de salida de ``get_application_ui_elements``
sobre el modelo real (Chrome/Spotify hardcodeadas).

La salida es dict-of-dicts (clave = nombre de elemento) con claves
{type, coordinates, screen, is_calibrated, required_capability,
calibration_data} — NO incluye 'description'.

  - **`test_chrome_ui_elements_format`** (L344)
    - get_application_ui_elements('chrome') devuelve dict-of-dicts con
'description' y sin 'name' interno (el nombre es la clave).

  - **`test_spotify_has_play_button`** (L367)
    - Spotify expone 'play_button' como elemento UI.

- **`TestApplicationIntegrationUiElementsAsDict`** (línea 378) — 2 método(s) de test
  - Verifica que ``_create_ui_element_node`` consume ``ui_elements`` como
dict-of-dicts (compatible con el formato del JSON de conocimiento y con
la salida de ``get_application_ui_elements``).

Contrario a ``_reconstruct_ui_elements`` que espera lista.

  - **`test_create_ui_element_node_reads_dict`** (L386)
    - El integrador lee ui_elements como dict (get via .get(element_name)).

  - **`test_create_ui_element_node_finds_element_in_dict`** (L407)
    - Cuando ui_elements es un dict y el elemento existe, se encuentra.

- **`TestRuntimeStateUiElementsFormat`** (línea 432) — 2 método(s) de test
  - Verifica que los estados en runtime (WorldState y ExecutionState)
tipan ``ui_elements`` como ``Dict[str, Dict[str, Any]]`` (dict-of-dicts),
lo que coincide con el formato del JSON de conocimiento pero NO con el
modelo ``ApplicationKnowledge.ui_elements`` (List[UIElement]).

  - **`test_world_state_ui_elements_is_dict_type`** (L439)
    - WorldState.ui_elements: Dict[str, Dict[str, Any]].

No usa from __future__ import annotations, asi que el tipo es un
objeto real (no cadena).

  - **`test_execution_state_ui_elements_is_dict_type`** (L451)
    - ExecutionState.ui_elements: Dict[str, Dict[str, Any]].

executor.py usa from __future__ import annotations, asi que el tipo
se guarda como cadena.

- **`TestVisionDetectUiElementsFormat`** (línea 466) — 1 método(s) de test
  - Verifica el formato REAL que produce ``detect_ui_elements`` en vision.py:
dict-of-dicts con claves {name, type, text, interactive, monitor}.

Este es el tercer formato distinto de ui_elements en el sistema.

  - **`test_detect_ui_elements_node_format`** (L473)
    - El nodo vision.detect_ui_elements declara efecto
'ui_elements_detected' y funcion 'detect_ui_elements'.

El output en runtime es un dict-of-dicts con claves
{name, type, text, interactive, monitor} — un tercer formato
distinto al del JSON de conocimiento y al del modelo UIElement.

- **`_FakeApp`** (línea 395) — 0 método(s) de test

  Métodos auxiliares (no test): get_ui_element

---

<a name="eyes/test-ui_knowledge_coordinate_separation"></a>
### `eyes\test_ui_knowledge_coordinate_separation.py`

**Descripción:** Tests de verificacion de la separacion conocimiento UI / coordenadas concretas — unidad 3.4.2.3 (FASE 3.4.2 — UI elements).

**Módulos de origen probados:** src.hands.coordinate_manager, src.utils.config

**Clases de test:**

- **`TestUiKnowledgeWithoutCoordinates`** (línea 40) — 2 método(s) de test
  - ``ui_knowledge`` contiene solo conocimiento (no ``screens``).

  - **`test_ui_knowledge_elements_have_no_screens`** (L43)
    - Ningún elemento de ``ui_knowledge`` incluye la clave ``screens``.

  - **`test_ui_knowledge_elements_keep_knowledge_fields`** (L66)
    - Los elementos de ``ui_knowledge`` conservan campos de conocimiento.

- **`TestCalibracionesOnlyCoordinates`** (línea 86) — 3 método(s) de test
  - ``calibraciones`` contiene solo coordenadas (sin campos de conocimiento).

  - **`test_calibraciones_section_exists`** (L89)
    - La seccion ``calibraciones`` existe y es un dict.

  - **`test_calibraciones_entries_have_only_screen_keys`** (L97)
    - Cada entrada de ``calibraciones`` solo tiene claves de pantalla (sN)
y valores de coordenada.

  - **`test_calibraciones_entries_have_no_knowledge_fields`** (L119)
    - Las entradas de ``calibraciones`` no tienen campos de conocimiento.

- **`TestCoordinateManagerKnowledgeWithoutCoordinates`** (línea 136) — 2 método(s) de test
  - _create_resource_from_knowledge crea recursos sin coordenadas.

  - **`test_create_resource_from_knowledge_no_coordinates`** (L139)
    - Sin ``screens`` en element_data, el recurso no tiene coordenadas ni esta calibrado.

  - **`test_create_resource_from_knowledge_ignores_screens_if_present`** (L164)
    - Aunque element_data traiga ``screens`` (retrocompatibilidad), el
metodo no los usa como coordenadas.

- **`TestCoordinateManagerLoadCalibraciones`** (línea 185) — 3 método(s) de test
  - load_from_macros_coords carga calibraciones y fusiona con conocimiento.

  - **`test_load_from_macros_coords_loads_calibraciones`** (L188)
    - Las coordenadas de ``calibraciones`` se cargan y fusionan.

  - **`test_load_from_macros_coords_legacy_fallback_for_uncovered`** (L226)
    - Entradas solo en legacy_data.macros (no en calibraciones) siguen cargándose.

  - **`test_get_calibrated_coordinate_uses_merged_resource`** (L241)
    - get_calibrated_coordinate devuelve coordenadas del recurso fusionado.

---

<a name="eyes/test-vision"></a>
### `eyes\test_vision.py`

**Descripción:** Tests de Vision (src/eyes/vision.py).

**Módulos de origen probados:** src.eyes.screen, src.eyes.vision

**Clases de test:**

- **`TestVisionNodeType`** (línea 22) — 2 método(s) de test

  - **`test_values`** (L23)

  - **`test_ui_detecton_is_alias`** (L32)

- **`TestVisionNode`** (línea 36) — 7 método(s) de test

  - **`test_defaults`** (L57)

  - **`test_to_dict_serializes_type`** (L76)

  - **`test_from_dict_roundtrip`** (L85)

  - **`test_from_dict_with_string_type`** (L96)

  - **`test_get_preconditions`** (L106)

  - **`test_get_effects`** (L110)

  - **`test_get_cost`** (L114)

  Métodos auxiliares (no test): _make

- **`TestUIElement`** (línea 119) — 2 método(s) de test

  - **`test_create_full`** (L120)

  - **`test_create_minimum`** (L136)

- **`TestVisionResponse`** (línea 149) — 2 método(s) de test

  - **`test_empty`** (L150)

  - **`test_with_elements`** (L154)

- **`TestVisionInit`** (línea 163) — 3 método(s) de test

  - **`test_default_model`** (L164)

  - **`test_custom_model`** (L170)

  - **`test_vision_nodes_populated`** (L174)

- **`TestVisionNodeQueries`** (línea 184) — 7 método(s) de test

  - **`test_get_vision_nodes_returns_list`** (L188)

  - **`test_get_vision_node_found`** (L193)

  - **`test_get_vision_node_not_found`** (L198)

  - **`test_get_nodes_by_type`** (L201)

  - **`test_get_nodes_by_type_alias`** (L206)

  - **`test_get_total_vision_cost`** (L210)

  - **`test_get_vision_capabilities`** (L215)

  Métodos auxiliares (no test): setup_method

- **`TestVisionSafeJsonLoads`** (línea 228) — 7 método(s) de test

  - **`test_valid_json`** (L232)

  - **`test_empty_string`** (L235)

  - **`test_none`** (L238)

  - **`test_markdown_wrapped`** (L241)

  - **`test_embedded_json`** (L245)

  - **`test_invalid_json_no_braces`** (L250)

  - **`test_invalid_json_malformed`** (L253)

  Métodos auxiliares (no test): setup_method

- **`TestVisionClampFloat`** (línea 257) — 6 método(s) de test

  - **`test_normal_value`** (L258)

  - **`test_above_range`** (L261)

  - **`test_below_range`** (L264)

  - **`test_invalid_string`** (L267)

  - **`test_none`** (L270)

  - **`test_int_value`** (L273)

- **`TestVisionNormalizeIntList`** (línea 277) — 8 método(s) de test

  - **`test_valid_bbox`** (L278)

  - **`test_valid_center`** (L282)

  - **`test_wrong_length_too_short`** (L286)

  - **`test_wrong_length_too_long`** (L289)

  - **`test_invalid_items`** (L292)

  - **`test_float_items_rounded`** (L295)

  - **`test_none_input`** (L299)

  - **`test_non_list_input`** (L302)

- **`TestVisionCoordinatesMatch`** (línea 306) — 5 método(s) de test

  - **`test_no_expected_coords`** (L307)

  - **`test_no_numeric_coords`** (L310)

  - **`test_within_tolerance`** (L313)

  - **`test_outside_tolerance`** (L319)

  - **`test_custom_tolerance`** (L325)

- **`TestVisionBuildVerificationPrompt`** (línea 332) — 5 método(s) de test

  - **`test_url_loaded`** (L336)

  - **`test_element_focused`** (L344)

  - **`test_application_opened`** (L351)

  - **`test_generic_type`** (L358)

  - **`test_generic_type_with_application`** (L363)

  Métodos auxiliares (no test): setup_method

- **`TestVisionDetectUIElements`** (línea 370) — 5 método(s) de test

  - **`test_detect_ui_elements_valid`** (L375)

  - **`test_detect_ui_elements_no_response`** (L389)

  - **`test_detect_ui_elements_invalid_bbox`** (L395)

  - **`test_detect_ui_elements_exception`** (L406)

  - **`test_detect_ui_elements_with_application`** (L412)

  Métodos auxiliares (no test): setup_method

- **`TestVisionVerifyElementVisibility`** (línea 421) — 3 método(s) de test

  - **`test_element_found`** (L429)

  - **`test_element_not_found`** (L442)

  - **`test_no_screenshot`** (L452)

  Métodos auxiliares (no test): setup_method

- **`TestVisionVerifyActionResult`** (línea 460) — 5 método(s) de test

  - **`test_success_verified`** (L468)

  - **`test_not_verified_low_confidence`** (L478)

  - **`test_not_verified_false_flag`** (L487)

  - **`test_no_screenshot`** (L495)

  - **`test_invalid_response`** (L502)

  Métodos auxiliares (no test): setup_method

- **`TestVisionDetectApplicationState`** (línea 509) — 9 método(s) de test

  - **`test_app_detected`** (L516)

  - **`test_app_detected_open_state`** (L528)

  - **`test_app_not_detected`** (L538)

  - **`test_app_empty_name`** (L547)

  - **`test_app_no_screenshot`** (L554)

  - **`test_app_invalid_state_string`** (L561)
    - Un state desconocido NO se afirma como OPEN; se usa CLOSED como fallback seguro.

  - **`test_app_detected_missing_state_field`** (L571)
    - Si la visión detecta la app (detected=True) pero no incluye el campo
'state', no se afirma OPEN por defecto. Se asume CLOSED para evitar
creencias falsas — hoja 3.4.3.2 'No afirmar un estado solo por configuración'.

  - **`test_app_detected_null_state_field`** (L583)
    - Si la visión detecta la app pero 'state' es null/None, no se afirma OPEN.

  - **`test_app_exception_returns_closed`** (L593)

  Métodos auxiliares (no test): setup_method

- **`TestVisionAnalyzeImage`** (línea 600) — 4 método(s) de test

  - **`test_analyze_image_returns_json_string`** (L605)

  - **`test_analyze_image_empty_response`** (L617)

  - **`test_analyze_image_with_calibration_target`** (L623)

  - **`test_analyze_image_exception`** (L636)

  Métodos auxiliares (no test): setup_method

- **`TestVisionAnalyzeScreenForWorldState`** (línea 647) — 2 método(s) de test

  - **`test_analyze_returns_world_state`** (L658)

  - **`test_analyze_no_screenshot`** (L672)

  Métodos auxiliares (no test): setup_method

---

<a name="eyes/test-vision_calibration_integration"></a>
### `eyes\test_vision_calibration_integration.py`

**Descripción:** Tests de integracion VISION -> CALIBRACION — unidad 3.4.2.4 (FASE 3.4.2 — UI elements).

**Módulos de origen probados:** src.eyes.vision, src.hands.applications_core, src.hands.coordinate_manager, src.hands.universal_visual_calibrator, src.utils.config

**Clases de test:**

- **`TestUvcUsesVision`** (línea 43) — 2 método(s) de test
  - UniversalVisualCalibrator construye y usa una instancia de Vision.

  - **`test_uvc_has_vision_instance`** (L46)

  - **`test_calibrate_calls_vision_analyze_image`** (L52)
    - UVC.calibrate() invoca vision.analyze_image con la captura y prompt.

- **`TestVisionOutputUvcCompatible`** (línea 91) — 2 método(s) de test
  - El JSON que devuelve Vision.analyze_image es consumible por UVC.

  - **`test_analyze_image_schema_has_required_fields`** (L94)
    - analyze_image usa un schema que exige name, type, bbox, confidence.

  - **`test_uvc_normalize_single_element_uses_vision_fields`** (L104)
    - UVC._normalize_single_element lee name/type/center/bbox/confidence de Vision.

- **`TestUvcCalibrationPolicy`** (línea 133) — 6 método(s) de test
  - CalibrationPolicy de UVC permite/bloquea aplicaciones y elementos.

  - **`test_can_calibrate_application_allows_chrome`** (L136)

  - **`test_can_calibrate_application_allows_spotify`** (L141)

  - **`test_can_calibrate_application_blocks_valorant`** (L146)

  - **`test_can_calibrate_element_allows_button`** (L151)

  - **`test_can_calibrate_element_blocks_low_confidence`** (L156)

  - **`test_can_calibrate_element_blocks_background`** (L161)

- **`TestCoordinateManagerKnowledgeToCalibration`** (línea 170) — 3 método(s) de test
  - CoordinateManager carga ui_knowledge y calibraciones y las fusiona.

  - **`test_cm_loads_ui_knowledge_from_macros_coords`** (L173)

  - **`test_cm_merges_calibraciones_with_knowledge`** (L207)
    - Tras load_from_macros_coords, chrome.address_bar tiene coordenadas.

  - **`test_cm_get_calibrated_coordinate_for_chrome_address_bar`** (L242)
    - get_calibrated_coordinate devuelve las coordenadas de s1/s2.

- **`TestUiElementsToCalibrationToAction`** (línea 274) — 3 método(s) de test
  - End-to-end: elemento de get_application_ui_elements se valida para accion.

  - **`test_chrome_ui_elements_match_calibrated_resources`** (L277)
    - Cada elemento UI de chrome que tambien esta en macros_coords.json
tiene un recurso calibrado en CoordinateManager con el mismo type.

  - **`test_validate_resource_for_action_chrome_address_bar`** (L321)
    - chrome.address_bar (type=input) valida focus_ y type_ pero no click_.

  - **`test_validate_resource_for_action_chrome_new_tab_button`** (L348)
    - chrome.new_tab_button (type=button) valida click_ pero no focus_/type_.

- **`TestVisionCalibrationNode`** (línea 379) — 2 método(s) de test
  - Vision expone un nodo de analisis para calibracion.

  - **`test_vision_has_calibration_analysis_node`** (L382)

  - **`test_vision_calibration_node_uses_analyze_image`** (L392)

- **`TestVisionVerifyElementWithExpectedCoords`** (línea 404) — 1 método(s) de test
  - verify_element_visibility acepta expected_coords y compara coordenadas.

  - **`test_verify_element_visibility_accepts_expected_coords`** (L407)

---

<a name="eyes/test-vision_only"></a>
### `eyes\test_vision_only.py`

**Descripción:** Tests de vision_only.py (versión simplificada de Vision).

**Módulos de origen probados:** src.eyes.screen, src.eyes.vision_only

**Clases de test:**

- **`TestVisionNodeType`** (línea 17) — 1 método(s) de test

  - **`test_values`** (L18)

- **`TestVisionOnlyUIElement`** (línea 27) — 2 método(s) de test

  - **`test_create_full`** (L28)

  - **`test_create_minimal`** (L46)

- **`TestVisionOnlyResponse`** (línea 58) — 2 método(s) de test

  - **`test_empty`** (L59)

  - **`test_with_elements`** (L63)

- **`TestVisionOnlyInit`** (línea 69) — 2 método(s) de test

  - **`test_default_model`** (L71)

  - **`test_custom_model`** (L80)

- **`TestVisionOnlyGetVisionCapabilities`** (línea 85) — 1 método(s) de test

  - **`test_capabilities`** (L87)

- **`TestVisionOnlyGetTotalVisionCost`** (línea 97) — 1 método(s) de test

  - **`test_fixed_cost`** (L99)

- **`TestVisionOnlyAnalyzeImage`** (línea 104) — 4 método(s) de test

  - **`test_analyze_image_success`** (L106)

  - **`test_analyze_image_empty_response`** (L119)

  - **`test_analyze_image_exception`** (L126)

  - **`test_analyze_image_calls_ollama`** (L133)

- **`TestVisionOnlyVerifyActionResult`** (línea 146) — 5 método(s) de test

  - **`test_success_verified`** (L148)

  - **`test_low_confidence`** (L161)

  - **`test_no_screenshot`** (L172)

  - **`test_invalid_json`** (L181)

  - **`test_exception`** (L191)

- **`TestVisionOnlyDetectApplicationState`** (línea 202) — 6 método(s) de test

  - **`test_app_detected_active`** (L204)

  - **`test_app_not_detected`** (L219)

  - **`test_empty_name`** (L231)

  - **`test_no_screenshot`** (L239)

  - **`test_unknown_state_does_not_become_valid`** (L248)
    - 3.4.1.3: un estado desconocido NO se convierte en un estado valido
por defecto. Anteriormente caia en ApplicationState.OPEN; ahora debe
usar CLOSED como fallback seguro.

  - **`test_exception_returns_closed`** (L263)

---

## 📂 `hands/`

68 ficheros de test, 2569 métodos de test.

<a name="hands/planner/test-advanced_state_graph"></a>
### `hands\planner\test_advanced_state_graph.py`

**Descripción:** Tests para AdvancedStateGraph (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph, src.hands.planner.heuristic, src.hands.planner.node, src.hands.planner.preconditions_effects_types

**Clases de test:**

- **`TestAdvancedStateGraphInit`** (línea 39) — 12 método(s) de test

  - **`test_is_state_graph_subclass`** (L40)

  - **`test_default_cache_size`** (L44)

  - **`test_custom_cache_size`** (L48)

  - **`test_custom_cache_size_invalid_becomes_100`** (L52)

  - **`test_cache_size_minimum_is_1`** (L56)

  - **`test_default_max_cache_age`** (L60)

  - **`test_custom_max_cache_age`** (L64)

  - **`test_custom_max_cache_age_invalid`** (L68)

  - **`test_search_cache_initialized_empty`** (L72)

  - **`test_performance_metrics_initialized`** (L76)

  - **`test_default_search_strategy`** (L80)

  - **`test_custom_heuristic_propagated`** (L84)

- **`TestFindPathWithStrategy`** (línea 90) — 11 método(s) de test

  - **`test_finds_path`** (L91)

  - **`test_missing_start_node`** (L98)

  - **`test_missing_goal_node`** (L104)

  - **`test_invalid_strategy_returns_empty`** (L110)

  - **`test_string_strategy`** (L116)

  - **`test_default_strategy_is_astar`** (L121)

  - **`test_no_path`** (L126)

  - **`test_same_node`** (L134)

  - **`test_alternatives_requested`** (L140)

  - **`test_no_alternatives_when_disabled`** (L156)

  - **`test_executes_all_strategies`** (L161)

- **`TestCacheFunctionality`** (línea 169) — 16 método(s) de test

  - **`test_first_search_is_miss`** (L170)

  - **`test_cached_search_returns_cached_path`** (L175)

  - **`test_cache_hit_returns_path`** (L181)

  - **`test_cache_hit_increments_metrics`** (L188)

  - **`test_cache_miss_increments_metrics`** (L195)

  - **`test_cache_invalidated_on_graph_change`** (L201)

  - **`test_cache_entry_graph_revision_mismatch_invalidates`** (L210)
    - Cache entries are invalidated when graph_revision changes.

  - **`test_expired_cache_entry_not_used`** (L223)

  - **`test_cache_size_limit_enforced`** (L235)

  - **`test_cache_strategy_agnostic`** (L244)
    - Different strategies produce different cache keys.

  - **`test_cache_different_state_different_key`** (L252)

  - **`test_find_route_records_performance_metrics`** (L258)

  - **`test_find_route_uses_default_strategy`** (L263)

  - **`test_find_route_with_alternatives`** (L269)

  - **`test_build_route_alias`** (L284)

  - **`test_find_route_final_state_has_effects`** (L290)

- **`TestAdvancedStatsAndOptimization`** (línea 301) — 24 método(s) de test

  - **`test_get_advanced_stats_structure`** (L302)

  - **`test_get_advanced_stats_values`** (L314)

  - **`test_get_advanced_stats_search_strategies`** (L325)

  - **`test_get_advanced_stats_includes_performance_metrics`** (L335)

  - **`test_optimize_graph_for_performance_returns_changes`** (L342)

  - **`test_optimize_graph_for_performance_clears_expired_cache`** (L347)
    - Expired cache entries are removed by optimize_graph_for_performance.

  - **`test_optimize_graph_for_performance_adjusts_cache_size`** (L359)

  - **`test_optimize_graph_for_performance_large_graph`** (L365)

  - **`test_optimize_graph_for_performance_medium_graph`** (L373)

  - **`test_build_cache_key_deterministic`** (L381)

  - **`test_build_cache_key_different_strategy_different`** (L387)

  - **`test_build_cache_key_different_state_different`** (L393)

  - **`test_get_from_cache_no_entry`** (L399)

  - **`test_get_from_cache_expired_entry`** (L404)

  - **`test_get_from_cache_revision_mismatch`** (L414)

  - **`test_get_from_cache_revision_match`** (L424)

  - **`test_get_from_cache_none_revision_always_valid`** (L435)

  - **`test_get_from_cache_selects_most_recent`** (L445)

  - **`test_add_to_cache_under_limit`** (L461)

  - **`test_add_to_cache_exceeds_limit_evicts_oldest`** (L467)

  - **`test_cleanup_cache_removes_expired`** (L479)

  - **`test_cleanup_cache_removes_revision_mismatch`** (L489)

  - **`test_cache_hit_rate_after_search`** (L499)

  - **`test_search_with_all_strategies_records_metrics`** (L510)

---

<a name="hands/planner/test-application_integration"></a>
### `hands\planner\test_application_integration.py`

**Descripción:** Tests para ApplicationKnowledgeIntegrator (src/hands/planner/application_integration.py).

**Módulos de origen probados:** src.hands.applications_core, src.hands.planner.application_integration, src.hands.planner.node, src.memory.storage

**Clases de test:**

- **`TestNormalizeName`** (línea 119) — 6 método(s) de test
  - _normalize_name: normaliza nombres a claves deterministas.

  - **`test_basic`** (L122)

  - **`test_separators_collapsed`** (L125)

  - **`test_strips_whitespace`** (L128)

  - **`test_empty_string`** (L131)

  - **`test_none`** (L134)

  - **`test_unicode_preserved`** (L137)

- **`TestAsList`** (línea 143) — 8 método(s) de test
  - _as_list: normaliza valores a listas sin dividir strings/dicts.

  - **`test_none`** (L146)

  - **`test_list_preserves`** (L149)

  - **`test_tuple_to_list`** (L152)

  - **`test_set_to_list`** (L155)

  - **`test_string_not_split`** (L159)

  - **`test_dict_not_split`** (L162)

  - **`test_integer`** (L166)

  - **`test_generator`** (L169)

- **`TestGetValue`** (línea 173) — 5 método(s) de test
  - _get_value: lectura unificada de dicts y objetos.

  - **`test_dict_hit`** (L176)

  - **`test_dict_miss_default`** (L179)

  - **`test_object_attribute`** (L182)

  - **`test_object_attribute_missing_default`** (L186)

  - **`test_none_object`** (L190)

- **`TestSafeCopy`** (línea 194) — 4 método(s) de test
  - _safe_copy: deep copy con fallback.

  - **`test_deep_copy_mutable`** (L197)

  - **`test_immutable_returns_same`** (L204)

  - **`test_non_copyable_falls_back`** (L208)

  - **`test_none`** (L219)

- **`TestCapabilityValue`** (línea 223) — 7 método(s) de test
  - _capability_value: obtiene el valor de una capacidad.

  - **`test_enum`** (L226)

  - **`test_string`** (L230)

  - **`test_dict_with_value`** (L233)

  - **`test_dict_with_value_key`** (L236)

  - **`test_dict_without_value_key_returns_str_repr`** (L239)

  - **`test_object_with_value_attr`** (L245)

  - **`test_none`** (L249)

- **`TestCapabilityKey`** (línea 253) — 2 método(s) de test
  - _capability_key: normaliza el valor de capacidad.

  - **`test_basic`** (L256)

  - **`test_enum`** (L259)

- **`TestNormalizedConditions`** (línea 263) — 4 método(s) de test
  - _normalized_conditions: copia de precondiciones/efectos.

  - **`test_strings`** (L266)

  - **`test_filters_none`** (L270)

  - **`test_non_list_input`** (L274)

  - **`test_dicts_are_distinct_copies`** (L278)

- **`TestUniqueNodes`** (línea 285) — 3 método(s) de test
  - _unique_nodes: deduplicación por ID con fusión de metadata.

  - **`test_dedup_by_id`** (L288)

  - **`test_skips_nodes_without_id`** (L296)

  - **`test_merges_required_by_capabilities`** (L303)

- **`TestGetApplication`** (línea 319) — 6 método(s) de test
  - _get_application: resolución de aplicación.

  - **`test_none_manager`** (L322)

  - **`test_found_via_getter`** (L326)

  - **`test_found_via_dict`** (L332)

  - **`test_not_found`** (L338)

  - **`test_empty_name`** (L342)

  - **`test_alias_resolution`** (L346)

- **`TestConvertApplicationToNodes`** (línea 357) — 10 método(s) de test
  - convert_application_to_nodes: conversión declarativa a Nodes.

  - **`test_chrome_nodes`** (L360)

  - **`test_node_types_present`** (L367)

  - **`test_nonexistent_app_returns_empty`** (L373)

  - **`test_deduplication_ui_element`** (L377)
    - Un elemento UI requerido por dos capacidades debe aparecer una sola vez.

  - **`test_hierarchy_parent_children`** (L394)

  - **`test_capability_node_has_preconditions`** (L412)

  - **`test_ui_element_node_has_availability_effect`** (L420)

  - **`test_capability_node_is_reusable`** (L429)

  - **`test_capability_node_action_category`** (L436)

  - **`test_no_capabilities_app`** (L443)

- **`TestCreateApplicationNode`** (línea 457) — 5 método(s) de test
  - _create_application_node: estructura del nodo de aplicación.

  - **`test_node_structure`** (L460)

  - **`test_parameters`** (L470)

  - **`test_effects_app_available`** (L479)

  - **`test_metadata_source`** (L485)

  - **`test_preflight_requirements_in_preconditions`** (L492)

- **`TestCreateCapabilityNode`** (línea 509) — 5 método(s) de test
  - _create_capability_node: estructura del nodo de capacidad.

  - **`test_node_structure`** (L512)

  - **`test_app_open_precondition_added`** (L521)

  - **`test_ui_element_availability_precondition`** (L528)

  - **`test_cost_fallback`** (L535)

  - **`test_cost_invalid_fallback`** (L542)

- **`TestCreateUIElementNode`** (línea 556) — 4 método(s) de test
  - _create_ui_element_node: nodos de elementos UI.

  - **`test_element_found_type`** (L559)

  - **`test_element_not_found_type`** (L567)

  - **`test_uncalibrated_element_no_calibration_precondition`** (L575)

  - **`test_calibrated_element`** (L585)

- **`TestIsElementCalibrated`** (línea 603) — 6 método(s) de test
  - _is_element_calibrated: detección de calibración.

  - **`test_none_element`** (L606)

  - **`test_callable_method`** (L609)

  - **`test_dict_with_callable`** (L616)

  - **`test_dict_with_value`** (L620)

  - **`test_dict_without_is_calibrated_uses_calibrated_key`** (L624)

  - **`test_dict_no_keys`** (L628)

- **`TestGetCurrentState`** (línea 637) — 4 método(s) de test
  - _get_application_current_state: obtención de estado persistido.

  - **`test_none_manager`** (L640)

  - **`test_entity_found`** (L644)

  - **`test_entity_not_found`** (L654)

  - **`test_non_dict_properties`** (L661)

- **`TestGeneratePreconditions`** (línea 675) — 4 método(s) de test
  - _generate_application_preconditions: generación de precondiciones.

  - **`test_string_requirements_deduped`** (L678)

  - **`test_dict_requirements`** (L690)

  - **`test_non_string_non_dict_passes_through`** (L699)

  - **`test_empty_requirements`** (L708)

- **`TestGenerateApplicationEffects`** (línea 714) — 2 método(s) de test
  - _generate_application_effects: efectos declarativos.

  - **`test_effect_contains_app_key`** (L717)

  - **`test_empty_name`** (L723)

- **`TestValidateNodeReferences`** (línea 734) — 3 método(s) de test
  - _validate_node_references: validación de referencias jerárquicas.

  - **`test_valid_references`** (L737)

  - **`test_missing_parent_logs_warning`** (L744)

  - **`test_missing_child_logs_warning`** (L751)

- **`TestQueryGetApplicationsByCapability`** (línea 763) — 5 método(s) de test
  - get_applications_by_capability: consulta de aplicaciones por capacidad.

  - **`test_none_manager`** (L766)

  - **`test_real_query_open`** (L770)

  - **`test_real_query_enum_capability`** (L776)

  - **`test_real_query_string_capability`** (L783)
    - String capability input returns [] because ApplicationManager
only resolves enums — documented behavior.

  - **`test_unknown_capability`** (L791)

- **`TestQueryGetApplicationCapabilities`** (línea 797) — 4 método(s) de test
  - get_application_capabilities: consulta declarativa.

  - **`test_none_manager`** (L800)

  - **`test_app_not_found`** (L804)

  - **`test_chrome_capabilities_declared`** (L808)

  - **`test_capability_structure`** (L818)

- **`TestQueryGetUIElementsForCapability`** (línea 830) — 4 método(s) de test
  - get_ui_elements_for_capability: elementos UI requeridos.

  - **`test_app_not_found`** (L833)

  - **`test_known_capability`** (L837)

  - **`test_capability_with_no_elements`** (L842)

  - **`test_string_capability_name`** (L847)

- **`TestQueryIsApplicationCapable`** (línea 853) — 4 método(s) de test
  - is_application_capable: verificación de capacidad.

  - **`test_app_not_found`** (L856)

  - **`test_capable`** (L860)

  - **`test_not_capable`** (L864)

  - **`test_string_capability_not_supported_by_app`** (L868)
    - ApplicationKnowledge.is_capable doesn't normalize strings,
so the integrator returns False for string capabilities.

- **`TestRegisterApplicationKnowledge`** (línea 879) — 3 método(s) de test
  - register_application_knowledge: registro vía API pública.

  - **`test_empty_name_returns_false`** (L882)

  - **`test_non_dict_returns_false`** (L886)

  - **`test_valid_config_returns_true`** (L891)

- **`TestSingleton`** (línea 913) — 2 método(s) de test
  - get_application_knowledge_integrator: singleton.

  - **`test_returns_same_instance`** (L916)

  - **`test_singleton_has_manager`** (L921)

- **`TestLegacyCompatibility`** (línea 930) — 5 método(s) de test
  - Funciones legacy de compatibilidad.

  - **`test_legacy_get_apps_by_capability`** (L933)

  - **`test_legacy_get_apps_by_capability_invalid`** (L938)

  - **`test_legacy_get_apps_by_capability_enum`** (L942)

  - **`test_legacy_get_app_knowledge`** (L947)

  - **`test_legacy_get_app_knowledge_not_found`** (L952)

- **`TestConvertSpotify`** (línea 961) — 3 método(s) de test
  - Conversión de Spotify: aplicación con login_required.

  - **`test_spotify_nodes`** (L964)

  - **`test_spotify_login_required_in_metadata`** (L971)

  - **`test_spotify_has_preflight`** (L978)

- **`Uncopyable`** (línea 209) — 0 método(s) de test

  Métodos auxiliares (no test): __deepcopy__, __copy__

---

<a name="hands/planner/test-application_knowledge_to_goal"></a>
### `hands\planner\test_application_knowledge_to_goal.py`

**Descripción:** Tests de verificación para la conexión Application Knowledge → Goal (unidad 3.7.2.1).

**Módulos de origen probados:** src.brain.llm, src.hands.applications_core, src.hands.planner.application_integration, src.hands.planner.node

**Clases de test:**

- **`TestGoalRequiredCapabilities`** (línea 53) — 3 método(s) de test
  - Verifica que Goal.get_required_capabilities() retorna las capacidades
esperadas para cada tipo de objetivo.

  - **`test_open_application_capabilities`** (L57)

  - **`test_close_application_capabilities`** (L66)

  - **`test_navigate_capabilities`** (L75)

- **`TestApplicationCapabilityEnum`** (línea 89) — 5 método(s) de test
  - Verifica los valores declarados en ApplicationCapability enum.

  - **`test_open_capability_value`** (L92)

  - **`test_close_capability_value`** (L95)

  - **`test_navigate_capability_value`** (L98)

  - **`test_search_capability_value`** (L101)

  - **`test_type_capability_value`** (L104)

- **`TestGoalVsApplicationKnowledgeNaming`** (línea 112) — 3 método(s) de test
  - Documenta la discrepancia de nomenclatura entre Goal y Application Knowledge.

Goal usa nombres como "open_application", "close_application", etc.
Application Knowledge declara valores como "open", "close", etc.
No hay coincidencia directa. Ver heuristic.py para mapeo parcial.

  - **`test_goal_open_application_not_equal_appcap_open`** (L120)
    - Goal usa 'open_application' pero ApplicationCapability.OPEN.value es 'open'.
Esta es una discrepancia documentada de la unidad 3.7.2.1.

  - **`test_goal_close_application_not_equal_appcap_close`** (L127)
    - Goal usa 'close_application' pero ApplicationCapability.CLOSE.value es 'close'.

  - **`test_goal_capabilities_not_directly_in_appcap_values`** (L133)
    - Ninguna de las capacidades de Goal (open_application, activate_window,
focus_element, type_text, press_key) coincide directamente con los valores
de ApplicationCapability enum (open, close, navigate, search, type, click).

- **`TestApplicationKnowledgeIntegratorAvailability`** (línea 151) — 3 método(s) de test
  - Verifica que ApplicationKnowledgeIntegrator.is_capability_available()
distinga correctamente entre capacidad declarada y disponible en runtime.

  - **`test_is_capability_available_false_when_app_not_installed`** (L155)
    - is_capability_available retorna False para Chrome cuando no está
instalado en esta máquina (declarado pero no disponible en runtime).

  - **`test_is_capability_available_false_for_unknown_app`** (L164)
    - is_capability_available retorna False para aplicación inexistente.

  - **`test_get_application_capabilities_returns_dict`** (L170)
    - get_application_capabilities retorna un dict no vacío para Chrome.

- **`TestBrainApplicationKnowledgeIntegration`** (línea 182) — 4 método(s) de test
  - Verifica que Brain._get_application_knowledge exponga datos para
creación de Goals.

  - **`test_get_application_knowledge_structure`** (L187)

  - **`test_create_goal_from_user_input_application`** (L204)
    - create_goal_from_user_input con 'abre chrome' crea un Goal válido.

  - **`test_interpret_intent_returns_goal_for_application`** (L215)
    - interpret_intent con 'abre chrome' retorna type='goal'.

  - **`test_goal_required_capabilities_from_interpret_intent`** (L224)
    - El Goal creado por interpret_intent tiene required_capabilities vía
get_required_capabilities(). NOTA: metadata.required_capabilities solo
se popula para navigate/navigate_stream (no para open_application),
ver _create_goal_from_entity en llm.py líneas 671-678.

---

<a name="hands/planner/test-cache_performance"></a>
### `hands\planner\test_cache_performance.py`

**Descripción:** Tests para CacheEntry y PerformanceMetrics (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph

**Clases de test:**

- **`TestCacheEntry`** (línea 11) — 21 método(s) de test

  - **`test_default_values`** (L12)

  - **`test_path_is_copy`** (L30)

  - **`test_state_is_copy`** (L36)

  - **`test_final_state_is_copy`** (L42)

  - **`test_final_state_none_becomes_empty`** (L50)

  - **`test_alternative_paths_are_copied`** (L54)

  - **`test_alternative_paths_none_becomes_empty`** (L63)

  - **`test_cost_string_normalized`** (L70)

  - **`test_cost_inf_string_becomes_inf`** (L74)

  - **`test_cost_invalid_becomes_inf`** (L78)

  - **`test_timestamp_string_normalized`** (L82)

  - **`test_timestamp_invalid_uses_current_time`** (L86)

  - **`test_graph_revision_stored`** (L90)

  - **`test_is_not_expired`** (L94)

  - **`test_is_expired`** (L98)

  - **`test_is_expired_custom_max_age`** (L102)

  - **`test_is_expired_invalid_max_age_uses_default`** (L107)

  - **`test_is_expired_zero_max_age`** (L111)

  - **`test_increment_access`** (L115)

  - **`test_increment_access_updates_last_access`** (L123)

  - **`test_strategy_stored`** (L130)

- **`TestPerformanceMetrics`** (línea 135) — 20 método(s) de test

  - **`test_default_values`** (L136)

  - **`test_record_search_increments_count`** (L148)

  - **`test_record_search_successful`** (L153)

  - **`test_record_search_unsuccessful`** (L158)

  - **`test_record_search_multiple_updates_average`** (L164)

  - **`test_record_search_updates_min_max_iterations`** (L175)

  - **`test_record_search_negative_iterations`** (L183)

  - **`test_record_search_invalid_search_time`** (L189)

  - **`test_record_cache_hit`** (L194)

  - **`test_record_cache_miss`** (L200)

  - **`test_get_hit_rate_with_hits_and_misses`** (L207)

  - **`test_get_hit_rate_no_data`** (L214)

  - **`test_get_hit_rate_all_misses`** (L218)

  - **`test_get_hit_rate_all_hits`** (L223)

  - **`test_get_average_search_time`** (L228)

  - **`test_get_average_search_time_no_data`** (L234)

  - **`test_to_dict_structure`** (L238)

  - **`test_to_dict_min_iterations_inf_becomes_zero`** (L256)

  - **`test_to_dict_no_searches_success_rate`** (L261)

  - **`test_unsuccessful_search_not_included_in_averages`** (L266)
    - min/max iterations are updated for ALL searches; averages only for successful.

---

<a name="hands/planner/test-capabilities_consumible_format"></a>
### `hands\planner\test_capabilities_consumible_format.py`

**Descripción:** Tests de verificación de la hoja 3.3.3.1 — "Exponer capacidades en
formato consumible por planificacion.".

**Módulos de origen probados:** src.hands.planner.node, src.hands.planner.planner

**Clases de test:**

- **`TestCapabilitiesConsumibleFormat`** (línea 54) — 10 método(s) de test
  - ``get_application_capabilities_as_list`` expone capacidades como lista
de identificadores canónicos consumibles por el planificador.

  - **`test_chrome_returns_consumible_identifier_list`** (L62)
    - Chrome expone ['open', 'navigate', 'search'] (identificadores
canónicos), no los nombres específicos de la aplicación.

  - **`test_returns_list_format_not_dict`** (L70)
    - El formato exponible es una LISTA (consumible), no el dict de
nombres específicos que devuelve ``get_application_capabilities``.

  - **`test_uses_consumible_identifier_not_app_specific_name`** (L82)
    - La exposición contiene el identificador canónico ('open') y NO el
nombre específico de la aplicación ('open_chrome').

  - **`test_spotify_returns_open_and_navigate`** (L93)
    - Spotify (hardcodeada) declara OPEN + NAVIGATE.

  - **`test_known_app_without_capabilities_returns_empty`** (L100)
    - YouTube (app conocida reconstruida sin capabilities) → [] (ausente
como []), distinto del caso de aplicación con capabilities.

  - **`test_unknown_app_returns_empty`** (L106)
    - Aplicación desconocida → [] sin lanzar.

  - **`test_none_integrator_returns_empty`** (L112)
    - Integrador no disponible → [] (ausente como []), sin excepción.

  - **`test_derives_from_canonical_contract_no_duplication`** (L118)
    - La lista es una proyección del contrato canónico
``get_application_capabilities``: cada elemento proviene del campo
``capability`` del descriptor, en el mismo orden. Confirma que no
duplica lógica fuente.

  - **`test_deduplicates_and_skips_missing_capability`** (L135)
    - Frente a descriptores duplicados o sin campo ``capability``, la lista
expone identificadores únicos y omite los incompletos.

  - **`test_non_dict_descriptor_skipped`** (L152)
    - Descriptores que no son dict no rompen la proyección consumible.

  Métodos auxiliares (no test): _setup_planner

- **`TestPlanExposesConsumibleCapabilities`** (línea 166) — 2 método(s) de test
  - ``build_application_aware_plan`` expone las capacidades de la app objetivo
en formato lista consumible dentro de la metadata del plan, manejando el
ausente como ``[]``.

  - **`test_plan_exposes_consumible_capabilities_for_chrome`** (L175)
    - Un goal open_application sobre Chrome expone la lista canónica de
capacidades consumibles y la app objetivo.

  - **`test_plan_absent_app_exposes_empty_list`** (L193)
    - Cuando el goal no resuelve aplicación alguna (ausente), la metadata
expone ``application_capabilities`` como ``[]`` (manejo del ausente) y
``application_used`` como None.

  Métodos auxiliares (no test): planner

---

<a name="hands/planner/test-graph_builder"></a>
### `hands\planner\test_graph_builder.py`

**Descripción:** Tests para GraphBuilder (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph, src.hands.planner.node

**Clases de test:**

- **`TestBuildNavigationGraph`** (línea 39) — 9 método(s) de test

  - **`test_returns_state_graph`** (L40)

  - **`test_contains_all_nodes`** (L44)

  - **`test_has_edges`** (L49)

  - **`test_chrome_closed_to_open_edge_has_precondition`** (L53)

  - **`test_chrome_closed_to_open_edge_has_effect`** (L60)

  - **`test_navigation_edge_with_string_condition`** (L68)

  - **`test_navigation_graph_valid`** (L74)

  - **`test_partial_nodes_builds_partial_graph`** (L79)
    - Only edges whose both endpoints exist are created.

  - **`test_empty_nodes_dict`** (L85)

- **`TestBuildApplicationGraph`** (línea 91) — 9 método(s) de test

  - **`test_returns_state_graph`** (L92)

  - **`test_contains_all_nodes`** (L96)

  - **`test_has_edges`** (L101)

  - **`test_app_closed_to_open_has_precondition`** (L105)

  - **`test_app_closed_to_open_has_effect`** (L112)

  - **`test_application_graph_valid`** (L120)

  - **`test_empty_nodes_dict`** (L125)

  - **`test_alternative_transition_type`** (L130)

  - **`test_normal_transition_type`** (L136)

---

<a name="hands/planner/test-graph_edge"></a>
### `hands\planner\test_graph_edge.py`

**Descripción:** Tests para GraphEdge (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph, src.hands.planner.preconditions_effects_types

**Clases de test:**

- **`TestGraphEdgePostInit`** (línea 14) — 13 método(s) de test

  - **`test_string_ids_converted`** (L15)

  - **`test_int_ids_converted_to_str`** (L20)

  - **`test_cost_normalized_via_safe_float`** (L25)

  - **`test_invalid_cost_becomes_inf`** (L29)

  - **`test_nan_cost_becomes_inf`** (L33)

  - **`test_negative_cost_stays_negative`** (L37)
    - _safe_float only normalizes non-finite values; negative stays as-is.

  - **`test_none_cost_uses_default_inf`** (L42)
    - _safe_float(None, float("inf")) returns inf since None is invalid.

  - **`test_transition_type_default`** (L47)

  - **`test_transition_type_none_becomes_normal`** (L51)

  - **`test_conditions_none_becomes_empty_list`** (L55)

  - **`test_preconditions_none_becomes_empty_list`** (L59)

  - **`test_effects_none_becomes_empty_list`** (L63)

  - **`test_is_dataclass`** (L67)

- **`TestValuesEqual`** (línea 71) — 17 método(s) de test

  - **`test_same_string`** (L72)

  - **`test_different_strings`** (L75)

  - **`test_case_insensitive_string`** (L78)

  - **`test_whitespace_stripped`** (L81)

  - **`test_true_equals_true`** (L84)

  - **`test_true_not_equals_one`** (L87)
    - True and 1 should not be considered equal.

  - **`test_false_not_equals_zero`** (L91)

  - **`test_false_equals_false`** (L94)

  - **`test_bool_vs_string_true`** (L97)
    - bool and str compare via str() representation, case-insensitive.

  - **`test_int_equals_string_int`** (L102)

  - **`test_float_equals_string_float`** (L105)

  - **`test_near_float_equals_string`** (L108)
    - abs_tol=1e-9 means 1.0 vs '1.0001' are not close enough.

  - **`test_close_float_equals_string`** (L112)

  - **`test_non_matching_types`** (L115)

  - **`test_int_vs_int`** (L118)

  - **`test_int_vs_float`** (L121)

  - **`test_string_vs_int`** (L124)

- **`TestEvaluateRawCondition`** (línea 128) — 32 método(s) de test

  - **`test_empty_string_returns_false`** (L129)

  - **`test_empty_string_with_whitespace`** (L132)

  - **`test_string_key_true`** (L135)

  - **`test_string_not_met`** (L141)

  - **`test_string_with_colon`** (L146)

  - **`test_string_with_colon_case_insensitive`** (L150)

  - **`test_string_with_colon_and_whitespace`** (L153)

  - **`test_dict_state_equals`** (L157)

  - **`test_dict_equals_alias`** (L162)

  - **`test_dict_state_exists`** (L167)

  - **`test_dict_exists_alias`** (L174)

  - **`test_dict_state_not_exists`** (L179)

  - **`test_dict_state_true`** (L185)

  - **`test_dict_true_alias`** (L191)

  - **`test_dict_state_false`** (L195)

  - **`test_dict_false_alias`** (L201)

  - **`test_dict_state_greater_than`** (L205)

  - **`test_dict_gt_alias`** (L211)

  - **`test_dict_state_less_than`** (L215)

  - **`test_dict_lt_alias`** (L220)

  - **`test_dict_composite_and_true`** (L224)
    - Composite conditions need a 'key' field because key validation runs before kind dispatch.

  - **`test_dict_composite_or`** (L233)
    - Composite conditions need a 'key' field because key validation runs before kind dispatch.

  - **`test_dict_composite_and_conditions_at_top_level`** (L242)
    - Composite conditions need a 'key' field because key validation runs before kind dispatch.

  - **`test_dict_composite_without_key_returns_false`** (L250)
    - Without a 'key', key validation returns False before kind dispatch.

  - **`test_dict_no_key_returns_false`** (L258)

  - **`test_dict_unknown_kind_returns_false`** (L262)

  - **`test_dict_default_type_is_state_true`** (L266)

  - **`test_object_with_evaluate_method`** (L271)

  - **`test_object_with_evaluate_raises`** (L278)

  - **`test_callable_condition`** (L283)

  - **`test_callable_raises`** (L288)

  - **`test_non_string_non_dict_non_callable_returns_false`** (L293)

- **`TestCanTraverse`** (línea 298) — 10 método(s) de test

  - **`test_no_conditions_no_preconditions_traversable`** (L299)

  - **`test_infinite_cost_not_traversable`** (L303)

  - **`test_negative_cost_not_traversable`** (L307)

  - **`test_condition_met`** (L311)

  - **`test_condition_not_met`** (L316)

  - **`test_precondition_met`** (L320)

  - **`test_multiple_conditions_all_must_pass`** (L326)

  - **`test_does_not_mutate_input_state`** (L333)

  - **`test_dict_condition_with_colon`** (L339)

  - **`test_precondition_object_with_evaluate`** (L345)

- **`TestApplyEffects`** (línea 352) — 21 método(s) de test

  - **`test_no_effects_returns_copy`** (L353)

  - **`test_state_set_effect`** (L360)

  - **`test_state_set_effect_with_dict_effect_object`** (L366)

  - **`test_state_increment_effect`** (L372)

  - **`test_state_increment_missing_key`** (L378)

  - **`test_state_decrement_effect`** (L384)

  - **`test_state_remove_effect`** (L390)

  - **`test_state_remove_non_list_key`** (L396)

  - **`test_state_append_effect`** (L402)

  - **`test_state_append_to_missing_key`** (L408)

  - **`test_effect_object_with_apply_method`** (L414)

  - **`test_effect_object_with_apply_old_api`** (L420)
    - Effect.apply with a TypeError on first call retries with empty dict context.

  - **`test_non_dict_effect_skipped`** (L428)

  - **`test_effect_without_key_skipped`** (L433)

  - **`test_composite_effect`** (L439)

  - **`test_composite_effect_applied_incrementally`** (L450)

  - **`test_does_not_mutate_input_state`** (L461)

  - **`test_multiple_effects_applied_in_order`** (L469)

  - **`test_effect_with_unsupported_type_skipped`** (L478)

  - **`test_none_state_returns_empty`** (L484)

  - **`test_none_state_no_effects_returns_empty`** (L490)

- **`TestGetTotalCost`** (línea 496) — 7 método(s) de test

  - **`test_basic_cost`** (L497)

  - **`test_cost_plus_effects`** (L501)

  - **`test_cost_plus_preconditions`** (L507)

  - **`test_infinite_cost_returns_inf`** (L514)

  - **`test_negative_cost_returns_inf`** (L518)

  - **`test_ignores_current_state`** (L522)

  - **`test_no_effects_no_preconditions`** (L526)

---

<a name="hands/planner/test-graph_helpers"></a>
### `hands\planner\test_graph_helpers.py`

**Descripción:** Tests para funciones auxiliares de src/hands/planner/graph.py.

**Módulos de origen probados:** src.hands.planner.graph

**Clases de test:**

- **`TestSafeFloat`** (línea 19) — 10 método(s) de test

  - **`test_valid_float`** (L20)

  - **`test_valid_int`** (L23)

  - **`test_string_number`** (L26)

  - **`test_invalid_string_returns_default`** (L29)

  - **`test_none_returns_default`** (L32)

  - **`test_nan_returns_default`** (L35)

  - **`test_inf_returns_default`** (L38)

  - **`test_neg_inf_returns_default`** (L41)

  - **`test_default_is_zero`** (L44)

  - **`test_overflow_string`** (L47)

- **`TestCopyState`** (línea 51) — 6 método(s) de test

  - **`test_copies_dict`** (L52)

  - **`test_deep_copy_nested`** (L58)

  - **`test_none_returns_empty_dict`** (L65)

  - **`test_non_dict_returns_empty_dict`** (L68)

  - **`test_does_not_mutate_original`** (L72)

  - **`test_empty_dict`** (L77)

- **`TestTypeValue`** (línea 83) — 2 método(s) de test

  - **`test_enum_value`** (L84)

  - **`test_non_enum_value`** (L90)

- **`TestJsonSafe`** (línea 96) — 19 método(s) de test

  - **`test_string`** (L97)

  - **`test_int`** (L100)

  - **`test_bool`** (L103)

  - **`test_none`** (L106)

  - **`test_float_finite`** (L109)

  - **`test_float_nan`** (L112)

  - **`test_float_inf`** (L115)

  - **`test_enum`** (L118)

  - **`test_datetime`** (L124)

  - **`test_date`** (L130)

  - **`test_path`** (L136)

  - **`test_dict`** (L140)

  - **`test_list`** (L144)

  - **`test_tuple_converted_to_list`** (L147)

  - **`test_set_converted_to_list`** (L150)

  - **`test_circular_reference`** (L154)

  - **`test_unserializable_fallback_to_repr`** (L160)

  - **`test_dataclass_with_to_dict`** (L167)

  - **`test_frozen_set`** (L174)

- **`Color`** (línea 85) — 0 método(s) de test

- **`Status`** (línea 119) — 0 método(s) de test

- **`Weird`** (línea 161) — 0 método(s) de test

- **`Obj`** (línea 168) — 0 método(s) de test

  Métodos auxiliares (no test): to_dict

---

<a name="hands/planner/test-graph_node"></a>
### `hands\planner\test_graph_node.py`

**Descripción:** Tests para GraphNode (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph, src.hands.planner.node

**Clases de test:**

- **`TestGraphNodeDataclass`** (línea 18) — 2 método(s) de test

  - **`test_default_values`** (L19)

  - **`test_custom_values`** (L29)

- **`TestGraphNodeComparison`** (línea 40) — 5 método(s) de test

  - **`test_lt_by_f_cost`** (L41)

  - **`test_lt_same_f_cost_by_node_id`** (L49)

  - **`test_lt_same_f_cost_same_node_id_is_not_less`** (L58)

  - **`test_lt_against_non_graph_node_returns_not_implemented`** (L67)

  - **`test_node_id_comparison_uses_str`** (L74)
    - GraphNode.__lt__ uses str(getattr(self.node, 'id', '')).

---

<a name="hands/planner/test-is_application_available_no_process_name_assumption"></a>
### `hands\planner\test_is_application_available_no_process_name_assumption.py`

**Descripción:** Tests de la unidad 3.8.3.2.

**Módulos de origen probados:** src.hands.planner.planner

*Sin clases de test definidas.*

---

<a name="hands/planner/test-node"></a>
### `hands\planner\test_node.py`

**Descripción:** Tests para Node, Goal, Task, WorldState y funciones auxiliares (src/hands/planner/node.py).

**Módulos de origen probados:** src.hands.planner.node, src.hands.planner.preconditions_effects_types

**Clases de test:**

- **`TestNodeType`** (línea 36) — 2 método(s) de test

  - **`test_values`** (L37)

  - **`test_all_distinct`** (L50)

- **`TestTaskStatus`** (línea 55) — 2 método(s) de test

  - **`test_values`** (L56)

  - **`test_all_distinct`** (L63)

- **`TestNodePostInit`** (línea 72) — 18 método(s) de test

  - **`test_string_type_converted`** (L73)

  - **`test_enum_type_preserved`** (L77)

  - **`test_cost_normalized`** (L81)

  - **`test_cost_invalid_uses_default_1`** (L85)

  - **`test_cost_negative_becomes_zero`** (L89)

  - **`test_success_rate_clamped`** (L93)

  - **`test_success_rate_negative_clamped`** (L97)

  - **`test_success_rate_valid`** (L101)

  - **`test_average_execution_time_invalid_becomes_zero`** (L105)

  - **`test_average_execution_time_negative_becomes_zero`** (L109)

  - **`test_last_executed_string_normalized`** (L113)

  - **`test_last_executed_none_stays_none`** (L117)

  - **`test_none_list_fields_become_empty`** (L121)

  - **`test_none_dict_fields_become_empty`** (L137)

  - **`test_tuple_converted_to_list`** (L147)

  - **`test_set_converted_to_list`** (L151)

  - **`test_non_collection_value_wrapped_in_list`** (L155)

  - **`test_is_dataclass`** (L159)

- **`TestNodeEdgeOperations`** (línea 167) — 17 método(s) de test

  - **`test_add_edge`** (L168)

  - **`test_add_edge_none_id_skipped`** (L174)

  - **`test_add_edge_empty_id_skipped`** (L179)

  - **`test_add_edge_negative_cost_normalized`** (L184)

  - **`test_add_edge_invalid_cost_uses_default`** (L189)

  - **`test_add_edge_default_cost`** (L194)

  - **`test_add_edge_duplicate_updates_cost`** (L199)

  - **`test_add_in_edge`** (L206)

  - **`test_add_in_edge_none_id_skipped`** (L211)

  - **`test_add_in_edge_empty_id_skipped`** (L216)

  - **`test_add_in_edge_duplicate_ignored`** (L221)

  - **`test_get_edge_cost_existing`** (L227)

  - **`test_get_edge_cost_missing`** (L232)

  - **`test_get_valid_transitions_no_out_edges`** (L236)

  - **`test_get_valid_transitions_with_executable_targets`** (L240)

  - **`test_get_valid_transitions_all_executable`** (L250)

  - **`test_get_valid_transitions_empty_all_nodes`** (L260)
    - When all_nodes is not a dict, get_valid_transitions handles it gracefully.

- **`TestNodePreconditionFunctions`** (línea 274) — 4 método(s) de test

  - **`test_add_precondition_function`** (L275)

  - **`test_add_precondition_function_not_callable`** (L281)

  - **`test_add_effect_function`** (L286)

  - **`test_add_effect_function_not_callable`** (L292)

- **`TestNodeStateOperations`** (línea 298) — 3 método(s) de test

  - **`test_set_state_requirement`** (L299)

  - **`test_set_state_modification`** (L304)

  - **`test_mark_as_reusable_action`** (L309)

- **`TestNodeCanExecute`** (línea 316) — 10 método(s) de test

  - **`test_no_preconditions`** (L317)

  - **`test_string_precondition_met`** (L321)

  - **`test_dict_precondition_state_true`** (L326)

  - **`test_dict_precondition_state_equals`** (L331)

  - **`test_state_requirements_met`** (L336)

  - **`test_functional_precondition_met`** (L341)

  - **`test_multiple_preconditions_all_required`** (L347)

  - **`test_precondition_exception_returns_false`** (L352)

  - **`test_can_execute_with_non_dict_state`** (L358)

  - **`test_can_execute_no_preconditions_with_invalid_state`** (L363)

- **`TestNodeExecute`** (línea 373) — 11 método(s) de test

  - **`test_no_callback_returns_failure`** (L374)

  - **`test_successful_callback`** (L380)

  - **`test_callback_returning_false`** (L388)

  - **`test_callback_with_success_false_string`** (L396)

  - **`test_callback_exception_caught`** (L404)

  - **`test_effects_applied_on_success`** (L421)

  - **`test_state_modifications_applied`** (L430)

  - **`test_state_modifications_override_effects`** (L439)

  - **`test_verify_success_no_criteria`** (L451)

  - **`test_verify_success_with_criteria`** (L455)

  - **`test_verify_success_criteria_exception`** (L460)

- **`TestNodeSerialization`** (línea 469) — 10 método(s) de test

  - **`test_to_dict_structure`** (L470)

  - **`test_to_dict_serializes_callbacks_as_string`** (L484)

  - **`test_to_dict_removes_execute_callback_from_result`** (L490)
    - to_dict does not include execute_callback in output.

  - **`test_to_dict_removes_success_criteria`** (L496)

  - **`test_from_dict_basic`** (L501)

  - **`test_from_dict_non_dict_raises`** (L508)

  - **`test_from_dict_string_type`** (L512)

  - **`test_from_dict_none_type_defaults_to_action`** (L517)

  - **`test_from_dict_strips_function_fields`** (L522)

  - **`test_to_dict_from_dict_roundtrip`** (L526)

- **`TestNodeGetExecutionStats`** (línea 541) — 3 método(s) de test

  - **`test_no_history`** (L542)

  - **`test_with_history`** (L550)

  - **`test_with_corrupt_history_entries`** (L563)

- **`TestNodeEvaluatePrecondition`** (línea 578) — 14 método(s) de test

  - **`test_string_precondition`** (L579)

  - **`test_dict_state_equals`** (L585)

  - **`test_dict_state_exists`** (L591)

  - **`test_dict_state_true`** (L597)

  - **`test_dict_state_greater_than`** (L602)

  - **`test_dict_state_less_than`** (L608)

  - **`test_dict_application_open`** (L613)

  - **`test_dict_custom_function`** (L619)

  - **`test_dict_composite_and`** (L625)

  - **`test_dict_composite_or`** (L634)

  - **`test_dict_unknown_type_returns_false`** (L643)

  - **`test_object_with_evaluate`** (L648)

  - **`test_callable_precondition`** (L653)

  - **`test_unknown_type_returns_false`** (L657)

- **`TestNodeApplyEffect`** (línea 666) — 6 método(s) de test

  - **`test_string_effect`** (L667)

  - **`test_dict_state_set_effect`** (L673)

  - **`test_dict_state_increment_effect`** (L679)

  - **`test_dict_state_decrement_effect`** (L684)

  - **`test_effect_without_key_skipped`** (L689)

  - **`test_effect_object_with_apply`** (L694)

- **`TestGoal`** (línea 706) — 43 método(s) de test

  - **`test_default_values`** (L707)

  - **`test_post_init_string_type`** (L719)

  - **`test_post_init_enum_type`** (L723)

  - **`test_post_init_none_type`** (L729)
    - When type is None, __post_init__ leaves it as None (not converted to string).

  - **`test_post_init_priority_normalizes`** (L734)

  - **`test_post_init_priority_invalid`** (L738)

  - **`test_post_init_constraints_normalization`** (L742)

  - **`test_post_init_constraints_set_to_list`** (L746)

  - **`test_post_init_nodes_normalization`** (L750)

  - **`test_post_init_deadline_normalizes`** (L754)

  - **`test_post_init_deadline_nan_becomes_none`** (L758)

  - **`test_post_init_created_at_and_updated_at`** (L762)

  - **`test_is_expired_deadline_none`** (L767)

  - **`test_is_expired_past_deadline`** (L771)

  - **`test_is_expired_future_deadline`** (L775)

  - **`test_is_achieved_navigate_url`** (L779)

  - **`test_is_achieved_navigate_no_url`** (L784)

  - **`test_is_achieved_open_application`** (L788)

  - **`test_is_achieved_open_application_no_name`** (L793)

  - **`test_is_achieved_close_application`** (L797)

  - **`test_is_achieved_search`** (L802)

  - **`test_is_achieved_with_criteria_function`** (L807)

  - **`test_is_achieved_with_target_state_dict`** (L815)

  - **`test_is_achieved_criteria_exception`** (L823)

  - **`test_is_achieved_no_match_returns_false`** (L830)

  - **`test_get_required_capabilities_navigate`** (L834)

  - **`test_get_required_capabilities_open_application`** (L841)

  - **`test_get_required_capabilities_custom_from_metadata`** (L847)

  - **`test_get_required_capabilities_no_duplicates`** (L855)

  - **`test_estimate_cost_already_achieved`** (L863)

  - **`test_estimate_cost_not_achieved`** (L867)

  - **`test_estimate_cost_with_complexity`** (L872)

  - **`test_estimate_cost_with_base_cost`** (L880)

  - **`test_estimate_cost_open_application_when_not_open`** (L888)
    - When the target app is not open, estimate_cost returns base_cost * complexity.

  - **`test_estimate_cost_close_application_when_closed`** (L897)

  - **`test_to_dict_structure`** (L905)

  - **`test_to_dict_with_metadata`** (L916)

  - **`test_from_dict_basic`** (L921)

  - **`test_from_dict_non_dict_raises`** (L928)

  - **`test_from_dict_sets_defaults`** (L932)

  - **`test_from_dict_non_dict_metadata_handled`** (L939)
    - metadata=None is handled by __post_init__.

  - **`test_target_value_dict_target`** (L945)

  - **`test_target_value_string_target`** (L949)
    - When target is a string (not dict), _target_value returns the target itself.

- **`TestTask`** (línea 960) — 28 método(s) de test

  - **`test_default_values`** (L961)

  - **`test_string_status_converted`** (L972)

  - **`test_enum_status_preserved`** (L976)

  - **`test_invalid_status_defaults_to_pending`** (L980)

  - **`test_post_init_list_normalization`** (L984)

  - **`test_post_init_started_at_normalized`** (L991)

  - **`test_post_init_completed_at_normalized`** (L995)

  - **`test_post_init_started_at_none_stays_none`** (L999)

  - **`test_post_init_invalid_started_at_becomes_none`** (L1003)

  - **`test_can_execute_no_children_no_deps`** (L1008)

  - **`test_can_execute_with_completed_dependency`** (L1012)

  - **`test_can_execute_with_uncompleted_dependency`** (L1018)

  - **`test_can_execute_with_node_dependency`** (L1024)

  - **`test_can_execute_with_executable_child_node`** (L1031)

  - **`test_can_execute_completed_task`** (L1037)

  - **`test_can_execute_circular_dependency`** (L1051)

  - **`test_decompose_task_leaf`** (L1058)

  - **`test_decompose_task_with_children`** (L1063)

  - **`test_decompose_task_circular`** (L1071)

  - **`test_get_execution_plan_not_completed`** (L1079)

  - **`test_get_execution_plan_completed`** (L1086)

  - **`test_estimate_task_cost`** (L1093)

  - **`test_estimate_task_cost_completed`** (L1100)

  - **`test_to_dict`** (L1107)

  - **`test_from_dict_basic`** (L1116)

  - **`test_from_dict_non_dict_raises`** (L1122)

  - **`test_from_dict_sets_defaults`** (L1126)

  - **`test_to_dict_from_dict_roundtrip`** (L1133)

- **`TestWorldState`** (línea 1146) — 19 método(s) de test

  - **`test_default_state`** (L1147)

  - **`test_init_with_state`** (L1151)

  - **`test_state_is_copy`** (L1155)

  - **`test_get`** (L1161)

  - **`test_set`** (L1168)

  - **`test_set_replaces_value`** (L1173)

  - **`test_set_string_value`** (L1178)

  - **`test_update_with_dict`** (L1183)

  - **`test_update_with_world_state`** (L1190)

  - **`test_update_does_not_share_references`** (L1197)

  - **`test_copy`** (L1204)

  - **`test_copy_independent`** (L1211)

  - **`test_to_dict`** (L1218)

  - **`test_from_dict_basic`** (L1223)

  - **`test_from_dict_non_dict`** (L1228)

  - **`test_from_dict_with_state_key`** (L1232)

  - **`test_from_dict_without_state_key`** (L1237)

  - **`test_from_dict_with_non_dict_state`** (L1242)

  - **`test_to_dict_from_dict_roundtrip`** (L1247)

- **`TestCreateActionNode`** (línea 1258) — 5 método(s) de test

  - **`test_creates_node`** (L1259)

  - **`test_default_reusable_and_category`** (L1267)

  - **`test_custom_reusable_overrides`** (L1272)

  - **`test_custom_cost`** (L1276)

  - **`test_ui_element`** (L1280)

- **`TestCreateApplicationNode`** (línea 1285) — 3 método(s) de test

  - **`test_creates_node`** (L1286)

  - **`test_with_parameters`** (L1293)

  - **`test_with_metadata`** (L1297)

- **`TestCreateStateNode`** (línea 1302) — 3 método(s) de test

  - **`test_creates_node`** (L1303)

  - **`test_default_state_value`** (L1309)

  - **`test_with_additional_requirements`** (L1313)

- **`TestCreateConditionNode`** (línea 1321) — 3 método(s) de test

  - **`test_creates_node`** (L1322)

  - **`test_with_multiple_functions`** (L1330)

  - **`test_function_executes`** (L1339)

- **`TestEnum`** (línea 724) — 0 método(s) de test

---

<a name="hands/planner/test-planner_action_verification"></a>
### `hands\planner\test_planner_action_verification.py`

**Descripción:** Tests de verificación de la hoja 3.3.3.2 — "Verificar que Planner no recibe
acciones inexistentes".

**Módulos de origen probados:** src.hands.planner.node, src.hands.planner.planner

**Clases de test:**

- **`TestActionExists`** (línea 98) — 5 método(s) de test
  - ``action_exists`` verifica la presencia de una acción en el ActionRegistry.

  - **`test_registered_action_exists`** (L106)
    - Todas las acciones registradas reales devuelven True.

  - **`test_nonexistent_action_does_not_exist`** (L111)
    - Acciones inexistentes (compatibilidad/UI sin registrar) devuelven False.

  - **`test_empty_string_returns_false`** (L115)

  - **`test_whitespace_only_returns_false`** (L118)

  - **`test_non_string_input_returns_false`** (L121)

  Métodos auxiliares (no test): _setup_planner

- **`TestResolveNodeActionName`** (línea 132) — 9 método(s) de test
  - ``_resolve_node_action_name`` resuelve el nombre de acción efectivo de un
paso de plan, replicando la lógica del Executor.

  - **`test_node_with_action_and_id`** (L136)
    - Cuando ``action`` coincide con ``id``, se usa el nombre del nodo.

  - **`test_node_id_as_action`** (L141)
    - Si solo hay ``id``, se usa como nombre de acción.

  - **`test_node_with_callback_returns_none`** (L146)
    - Un nodo con ``execute_callback`` no necesita registro → None.

  - **`test_node_with_metadata_action_name`** (L152)
    - ``metadata['action_name']`` se prioriza sobre el ``id`` del nodo.

  - **`test_node_with_metadata_action`** (L161)
    - ``metadata['action']`` también se prioriza sobre el ``id`` del nodo.

  - **`test_node_with_explicit_action_and_id_differ`** (L170)
    - Si ``action`` difiere de ``id`, se prefiere ``action`` (no override).

  - **`test_non_dict_node_returns_none`** (L175)

  - **`test_callback_in_metadata_takes_precedence`** (L179)
    - ``metadata['execute_callback']`` también invalida la búsqueda.

  - **`test_empty_id_returns_none`** (L189)
    - Un nodo sin ``id`` ni ``action`` ni ``action_name`` → None.

- **`TestValidatePlanActions`** (línea 200) — 9 método(s) de test
  - ``validate_plan_actions`` produce un reporte de verificación estructurado.

  - **`test_all_existing_actions`** (L207)
    - Un plan con solo acciones registradas → valid: True, sin inexistentes.

  - **`test_mixed_existing_and_nonexistent`** (L222)
    - Un plan con acciones existentes y no existentes → valid: False.

  - **`test_node_with_callback_is_valid`** (L237)
    - Pasos con ``execute_callback`` cuentan como válidos sin verificación.

  - **`test_all_callbacks_valid`** (L251)
    - Un plan donde todos los pasos tienen callback → valid: True.

  - **`test_empty_plan`** (L263)

  - **`test_none_plan_treated_as_empty`** (L269)

  - **`test_non_dict_steps_skipped`** (L273)

  - **`test_resolution_via_metadata_action_name`** (L280)
    - ``metadata['action_name']`` resuelve a una acción registrada.

  - **`test_resolution_via_metadata_action`** (L293)
    - ``metadata['action']`` resuelve a una acción registrada.

  Métodos auxiliares (no test): _setup_planner

- **`TestFilterExistingActions`** (línea 312) — 6 método(s) de test
  - ``filter_existing_actions`` devuelve un plan con solo pasos ejecutables.

  - **`test_filters_nonexistent_keeps_existing`** (L319)

  - **`test_keeps_callback_steps`** (L332)

  - **`test_all_filtered_returns_empty`** (L342)

  - **`test_empty_plan_returns_empty`** (L350)

  - **`test_original_plan_not_mutated`** (L353)

  - **`test_no_registry_preserves_all`** (L362)
    - Sin ActionRegistry disponible, el plan se conserva sin filtrar.

  Métodos auxiliares (no test): _setup_planner

- **`TestCreatePlanVerification`** (línea 380) — 3 método(s) de test
  - ``_create_plan`` incluye ``action_verification`` en la metadata del
resultado y reporta advertencias sobre acciones inexistentes.

  - **`test_plan_result_has_action_verification_metadata`** (L388)
    - El PlanningResult de ``_create_plan`` incluye la clave
``action_verification`` en metadata.

  - **`test_plan_result_warns_on_nonexistent_actions`** (L407)
    - Cuando el plan contiene acciones inexistentes, aparecen como warnings.

  - **`test_plan_result_valid_when_no_actions`** (L427)
    - Un plan vacío (goal already achieved) → verification con 0 steps, valid True.

  Métodos auxiliares (no test): _setup_planner

- **`TestBuildApplicationAwarePlanVerification`** (línea 449) — 1 método(s) de test
  - ``build_application_aware_plan`` expone ``action_verification`` en metadata.

  - **`test_plan_metadata_includes_action_verification`** (L456)
    - La planificación conscious-de-aplicación incluye la verificación de
acciones en la metadata del resultado.

  Métodos auxiliares (no test): _setup_planner

- **`TestNoActionRegistry`** (línea 479) — 3 método(s) de test
  - Cuando el ActionRegistry no está disponible, la verificación es segura.

  - **`test_action_exists_returns_false_without_registry`** (L486)
    - Sin ActionRegistry → ``action_exists`` devuelve False (modo paso seguro).

  - **`test_validate_plan_without_registry_keeps_all_valid`** (L491)
    - Sin ActionRegistry, todos los pasos se conservan como válidos (no callbacks
necesarios).  Ninguna acción se marca como inexistente.

  - **`test_filter_without_registry_preserves_all`** (L504)
    - Sin ActionRegistry, ``filter_existing_actions`` conserva todo el plan.

  Métodos auxiliares (no test): _setup_planner

---

<a name="hands/planner/test-planner_capability_action_traceability"></a>
### `hands\planner\test_planner_capability_action_traceability.py`

**Descripción:** Tests de verificación de la hoja 3.3.3.3 — "Verificar trazabilidad
aplicacion -> capability -> accion".

**Módulos de origen probados:** src.hands.planner.planner

**Clases de test:**

- **`TestTraceStructure`** (línea 56) — 6 método(s) de test
  - ``trace_application_capability_to_action`` produce una estructura
establecida y serializable.

  - **`test_top_level_keys`** (L64)

  - **`test_application_echoed`** (L68)

  - **`test_available_true_for_known_app`** (L72)

  - **`test_capability_entry_shape`** (L76)

  - **`test_providing_node_shape`** (L90)

  - **`test_result_is_json_serializable`** (L103)
    - La trazabilidad no debe contener objetos ``Node`` ni estructuras no
serializables, ya que puede persistirse como JSON.

  Métodos auxiliares (no test): _setup_planner

- **`TestTraceChromeCapabilities`** (línea 116) — 7 método(s) de test
  - La cadena aplicacion -> capability -> accion se verifica realmente
contra el ActionRegistry global.

  - **`test_chrome_capabilities_in_canonical_order`** (L124)

  - **`test_open_capability_is_covered_by_registered_action`** (L128)
    - La capability 'open' de Chrome está cubierta por la acción registrada
'open_application' (nodo chrome.open, action_category registrada).

  - **`test_open_providing_nodes_are_chrome_only`** (L136)
    - No hay fuga entre aplicaciones: spotify_open no aparece al trazar
la capability 'open' de Chrome.

  - **`test_open_compat_node_category_is_registered`** (L143)
    - chrome.open: action_category 'open_application' está registrada, el
propio id 'chrome.open' no (verificado read-only contra el registry).

  - **`test_open_known_node_not_registered`** (L156)
    - chrome_open: el id no es una acción registrada; su categoría
'application_capability' tampoco lo es.

  - **`test_navigate_capability_not_backed_by_registered_action`** (L169)
    - Hecho real verificable: la capability 'navigate' de Chrome sólo está
provista por el nodo declarativo chrome_navigate cuya categoría
'application_capability' no está registrada → no cubierta.

  - **`test_search_capability_not_backed_by_registered_action`** (L179)
    - Hecho real verificable: 'search' está provista por search_google
(categoría 'search', no registrada) y chrome_search → no cubierta.

  Métodos auxiliares (no test): _setup_planner, _entry

- **`TestTraceSingleCapability`** (línea 199) — 3 método(s) de test
  - El parámetro ``capability`` restringe la trazabilidad a una sola
capability sin alterar el resto de la estructura.

  - **`test_single_capability_returns_only_that_one`** (L207)

  - **`test_single_capability_consistent_with_full`** (L211)

  - **`test_unknown_capability_yields_empty_providers`** (L218)

  Métodos auxiliares (no test): _setup_planner

- **`TestTraceNonexistentApplication`** (línea 237) — 2 método(s) de test
  - Una aplicación desconocida no expone capabilities.

  - **`test_unknown_app_available_false`** (L244)

  - **`test_empty_app_name_available_false`** (L250)

  Métodos auxiliares (no test): _setup_planner

- **`TestTraceReusesActionRegistry`** (línea 261) — 3 método(s) de test
  - La trazabilidad depende directamente de ``action_exists`` (3.3.3.2):
los nodos cuya acción/categoría está registrada se marcan como existentes
y aparecen en ``implemented_actions``.

  - **`test_registered_action_reflected_in_trace`** (L270)
    - 'open_application' está registrada → la capability 'open' se marca
cubierta y la acción aparece en implemented_actions.

  - **`test_nonexistent_action_reflected_in_trace`** (L278)
    - 'chrome_open' no está registrada → action_exists False y no aparece
en implemented_actions (solo como nodo proveedor no registrado).

  - **`test_action_exists_called_for_resolution`** (L289)
    - Se comprueba que la trazabilidad delega en action_exists (no en un
lookup paralelo del registry): forzando action_exists a devolver True
para un nodo no registrado, ese nodo pasa a implemented_actions.

  Métodos auxiliares (no test): _setup_planner, _entry

- **`TestTraceIdempotentAndPure`** (línea 313) — 2 método(s) de test
  - La trazabilidad es un método de solo-lectura: no muta el modelo de
nodos y produce resultados idénticos entre invocaciones.

  - **`test_two_calls_produce_equal_results`** (L321)

  - **`test_does_not_mutate_available_nodes`** (L326)

  Métodos auxiliares (no test): _setup_planner

---

<a name="hands/planner/test-planner_find_nodes_for_capability"></a>
### `hands\planner\test_planner_find_nodes_for_capability.py`

**Descripción:** Tests de verificación de la hoja 3.3.4.1 — «Caso de aplicacion con varias
capacidades».

**Módulos de origen probados:** src.hands.planner.node, src.hands.planner.planner

**Clases de test:**

- **`TestFindNodesForCapabilityMultipleCapabilities`** (línea 102) — 4 método(s) de test
  - El camino de planificación (``_find_nodes_for_capability``) resuelve CADA
capability de una aplicación con varias capacidades a su/s nodo/s ejecutable,
aplicando la puerta ``can_execute`` que la trazabilidad de 3.3.3.3 no aplica.

  - **`test_app_with_several_exposes_more_than_one_capability`** (L111)
    - Premisa: Chrome expone más de una capability canónica.

  - **`test_each_capability_resolves_to_distinct_executable_nodes`** (L117)
    - En un estado que las habilita, cada capability de Chrome resuelve a su
nodo ejecutable concreto (varias capabilities → nodos distintos).

  - **`test_empty_state_excludes_all_providers_via_can_execute`** (L149)
    - Contraste con 3.3.3.3: la planificación aplica ``can_execute`` y, con
un estado inicial vacío, ninguna capability de Chrome resuelve nodos
ejecutables (mientras la trazabilidad los documenta aun así).

  - **`test_open_excludes_non_executable_provider_found_by_trace`** (L162)
    - ``chrome_open`` es proveedor de 'open' (lo documenta la trazabilidad de
3.3.3.3), pero no es ejecutable en el estado actual → planificación lo
descarta, devolviendo exclusivamente ``chrome.open``.

  Métodos auxiliares (no test): _setup_planner

- **`TestFindNodesForCapabilityNoCapabilities`** (línea 202) — 8 método(s) de test
  - El camino de planificación ``_find_nodes_for_capability`` debe manejar
correctamente una aplicación **conocida pero sin capabilities** declaradas.

Complementario al caso 3.3.4.1 (app con varias capabilities). Para una
app sin capabilities:

* ``get_application_capabilities_as_list`` expone ``[]`` (ausente).
* ``trace_application_capability_to_action`` devuelve ``available: False``
  con lista de capabilities vacía (contrario a 3.3.3.3 donde Chrome sí
  expone capabilities).
* ``convert_application_to_nodes`` produce **únicamente** el nodo
  APPLICATION declarativo (no action/task), lo que prueba que la app
  *existe* en el modelo aunque no declare capabilities.
* ``_find_nodes_for_capability`` devuelve ``[]`` para toda capability,
  tanto en estado ejecutable como vacío, porque el único nodo es de tipo
  APPLICATION (excluido por la puerta de tipo ``action/task``) y no
  proporciona ninguna capability.

  - **`test_known_app_without_capabilities_exposes_empty_list`** (L226)
    - YouTube (app conocida sin capabilities) expone ``[]`` — distinto de
Chrome que expone varias. Confirma que la app es conocida pero carece
de capabilities declaradas.

  - **`test_known_app_without_capabilities_trace_returns_available_false`** (L242)
    - La trazabilidad (3.3.3.3) devuelve ``available: False`` y capabilities
vacía para una app conocida sin capabilities — la app existe pero no
expone capabilities que trazar.

  - **`test_known_app_without_capabilities_differs_from_unknown_app`** (L251)
    - La trazabilidad distingue una app conocida sin capabilities de una app
desconocida: ambas devuelven ``available: False``, pero el campo
``application`` refleja el nombre consultado en cada caso.

  - **`test_convert_app_without_capabilities_creates_only_application_node`** (L264)
    - ``convert_application_to_nodes`` para una app conocida sin capabilities
produce exactamente un nodo de tipo APPLICATION (no action/task),
demostrando que la app existe en el modelo aunque no declare
capabilities ni acciones asociadas.

  - **`test_find_nodes_returns_empty_for_all_capabilities`** (L277)
    - ``_find_nodes_for_capability`` devuelve ``[]`` para toda capability
canónica cuando se le pasan los nodos de una app sin capabilities, en un
estado ejecutable. El nodo APPLICATION es excluido por la puerta de tipo
``action/task`` y no proporciona ninguna capability.

  - **`test_find_nodes_returns_empty_with_empty_state`** (L295)
    - Con estado inicial vacío, ``_find_nodes_for_capability`` devuelve ``[]``
para toda capability de una app sin capabilities (doble filtro: tipo
APPLICATION + can_execute vacío).

  - **`test_find_nodes_returns_empty_on_empty_node_set`** (L306)
    - ``_find_nodes_for_capability`` devuelve ``[]`` cuando no hay nodos
disponibles (edge case: app sin capabilities y sin nodes cargados).

  - **`test_node_provides_capability_false_for_application_node`** (L315)
    - ``_node_provides_capability`` devuelve ``False`` para el nodo
APPLICATION de una app sin capabilities, para toda capability canónica:
el nodo no declara capabilities ni coincide por id/alias/categoría.

  Métodos auxiliares (no test): _setup_planner

- **`TestFindNodesForCapabilityUnknownCapability`** (línea 330) — 8 método(s) de test
  - El camino de planificación ``_find_nodes_for_capability`` y las utilidades
asociadas deben manejar una **capability desconocida** —una capability que no
es canónica (open/navigate/search), no está en el mapa de aliases de
``_node_provides_capability`` y no es declarada por ninguna aplicación ni
nodo— de forma determinista y segura, devolviendo ausencia de proveedores
sin falsear disponibilidad.

Complementario a 3.3.4.1 (app con varias capabilities) y 3.3.4.2 (app
conocida sin capabilities). Aquí el foco es la **capability** desconocida
solicitada contra la app más capaz del modelo (Chrome).

  - **`test_unknown_capability_resolves_no_nodes_on_capable_app`** (L348)
    - Una capability desconocida no resuelve ningún nodo, ni siquiera contra
la app más capaz (Chrome) en un estado que habilita todas sus actions.
Contrasta con 3.3.4.1 donde 'open'/'navigate'/'search' resuelven nodos.

  - **`test_unknown_capability_resolves_no_nodes_with_empty_state`** (L357)
    - Una capability desconocida no resuelve nodos con estado inicial vacío
tampoco: el doble filtro (tipo action/task + can_execute) y la
ausencia de matching por capability convergen a ``[]``.

  - **`test_unknown_capability_resolves_no_nodes_on_all_nodes`** (L366)
    - Ningún nodo del modelo completo provee una capability desconocida:
``_find_nodes_for_capability`` devuelve ``[]`` contra *todos* los nodos
disponibles en un estado ejecutable.

  - **`test_node_provides_capability_false_for_unknown_against_all_chrome_nodes`** (L377)
    - ``_node_provides_capability`` devuelve ``False`` para una capability
desconocida contra TODOS los nodos action/task de Chrome, incluido el
nodo ejecutable ``chrome.open`` que SÍ provee la capability canónica
'open'.

  - **`test_unknown_capability_not_in_exposed_capabilities`** (L403)
    - ``get_application_capabilities_as_list`` solo expone las capabilities
declaradas por la app; una capability desconocida nunca aparece.

  - **`test_trace_unknown_capability_returns_no_providers`** (L410)
    - Trazando explícitamente una capability desconocida contra Chrome, el
entry resultante documenta: ``providing_nodes: []``, ``covered: False``,
``covering_action: None``, ``implemented_actions: []``.

Nota semántica verificada: ``available`` es ``True`` porque se trazó una
capability explícita (la lista ``[capability]`` es no vacía); ``available``
indica *«se solicitó trazar»*, no *«está cubierta»*. La ausencia de
proveedores queda reflejada por ``covered: False`` y
``providing_nodes: []``.

  - **`test_trace_without_capability_never_exposes_unknown`** (L435)
    - Trazando todas las capabilities de Chrome (sin pasar capability),
``trace_application_capability_to_action`` solo expone capabilities
canónicas declaradas, nunca la capability desconocida.

  - **`test_unknown_capability_contrast_with_known_returns_empty`** (L444)
    - Contraste directo: 'open' (conocida) resuelve nodos ejecutables en
``CHROME_EXECUTABLE_STATE``, mientras que la capability desconocida
'teleportar' devuelve ``[]`` bajo las mismas condiciones.

  Métodos auxiliares (no test): _setup_planner

---

<a name="hands/planner/test-route_result"></a>
### `hands\planner\test_route_result.py`

**Descripción:** Tests para RouteResult (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph

**Clases de test:**

- **`TestRouteResultDefaults`** (línea 11) — 2 método(s) de test

  - **`test_default_values`** (L12)

  - **`test_total_cost_default_is_inf`** (L28)

- **`TestRouteResultPostInit`** (línea 33) — 14 método(s) de test

  - **`test_none_path_becomes_empty_list`** (L34)

  - **`test_none_edges_becomes_empty_list`** (L38)

  - **`test_none_alternative_paths_becomes_empty`** (L42)

  - **`test_alternative_paths_are_defensive_copies`** (L49)

  - **`test_initial_state_copied`** (L58)

  - **`test_final_state_copied`** (L67)

  - **`test_non_dict_initial_state_becomes_empty`** (L75)

  - **`test_iterations_normalized`** (L82)

  - **`test_iterations_negative_becomes_zero`** (L89)

  - **`test_iterations_invalid_becomes_zero`** (L96)

  - **`test_elapsed_time_normalized`** (L103)

  - **`test_elapsed_time_negative_becomes_zero`** (L110)

  - **`test_total_cost_string_normalized`** (L117)

  - **`test_total_cost_nan_becomes_inf`** (L124)

- **`TestRouteResultProperties`** (línea 132) — 4 método(s) de test

  - **`test_length_empty_path`** (L133)

  - **`test_length_with_path`** (L137)

  - **`test_edge_count_empty`** (L144)

  - **`test_edge_count_with_edges`** (L148)

- **`TestRouteResultToDict`** (línea 159) — 4 método(s) de test

  - **`test_to_dict_structure`** (L160)

  - **`test_to_dict_with_edges`** (L178)

  - **`test_to_dict_with_initial_state`** (L195)

  - **`test_to_dict_with_alternative_paths`** (L207)

---

<a name="hands/planner/test-state_graph"></a>
### `hands\planner\test_state_graph.py`

**Descripción:** Tests para StateGraph (src/hands/planner/graph.py).

**Módulos de origen probados:** src.hands.planner.graph, src.hands.planner.heuristic, src.hands.planner.node, src.hands.planner.preconditions_effects_types

**Clases de test:**

- **`TestSearchStrategy`** (línea 58) — 2 método(s) de test

  - **`test_strategy_values`** (L59)

  - **`test_strategy_count`** (L66)

- **`TestStateGraphInit`** (línea 74) — 7 método(s) de test

  - **`test_default_heuristic`** (L75)

  - **`test_custom_heuristic`** (L80)

  - **`test_empty_graph_stats`** (L85)

  - **`test_graph_revision_starts_at_zero`** (L93)

  - **`test_nodes_empty`** (L97)

  - **`test_edges_empty`** (L101)

  - **`test_graph_nodes_empty`** (L105)

- **`TestAddNode`** (línea 114) — 12 método(s) de test

  - **`test_add_single_node`** (L115)

  - **`test_add_none_node_raises`** (L123)

  - **`test_add_node_no_id_raises`** (L128)

  - **`test_add_node_id_none_raises`** (L134)

  - **`test_add_node_strips_id`** (L140)

  - **`test_add_duplicate_node_replaces`** (L147)

  - **`test_get_node_exists`** (L156)

  - **`test_get_node_missing`** (L161)

  - **`test_has_node_true`** (L165)

  - **`test_has_node_false`** (L169)

  - **`test_add_node_invalidates_cache`** (L173)

  - **`test_add_same_node_object_does_not_increment_revision`** (L181)

- **`TestAddEdge`** (línea 194) — 15 método(s) de test

  - **`test_add_edge_success`** (L195)

  - **`test_add_edge_missing_source`** (L199)

  - **`test_add_edge_missing_target`** (L205)

  - **`test_add_edge_invalid_cost`** (L211)

  - **`test_add_edge_negative_cost`** (L216)

  - **`test_add_edge_updates_node_adjacency`** (L221)

  - **`test_add_edge_edge_cost_in_node`** (L228)

  - **`test_add_duplicate_edge_returns_true`** (L233)

  - **`test_add_duplicate_edge_replaces_different_cost`** (L238)

  - **`test_add_edge_with_conditions`** (L244)

  - **`test_add_edge_with_transition_type`** (L252)

  - **`test_add_edge_with_preconditions`** (L260)

  - **`test_add_edge_with_effects`** (L270)

  - **`test_add_edge_invalidates_cache`** (L280)

  - **`test_add_edge_with_invalid_cost_string`** (L288)

- **`TestGetEdgesAndNodes`** (línea 298) — 4 método(s) de test

  - **`test_get_edges_from`** (L299)

  - **`test_get_edges_from_no_edges`** (L306)

  - **`test_get_edge_exists`** (L310)

  - **`test_get_edge_missing`** (L317)

- **`TestFindRouteBasic`** (línea 326) — 18 método(s) de test

  - **`test_find_route_success_astar`** (L327)

  - **`test_find_route_success_dijkstra`** (L334)

  - **`test_find_route_success_bfs`** (L340)

  - **`test_find_route_success_dfs`** (L346)

  - **`test_find_route_success_greedy`** (L352)

  - **`test_find_route_start_not_found`** (L358)

  - **`test_find_route_goal_not_found`** (L365)

  - **`test_find_route_no_path`** (L372)

  - **`test_find_route_same_node`** (L382)

  - **`test_find_route_string_strategy`** (L388)

  - **`test_find_route_string_strategy_dijkstra`** (L394)

  - **`test_find_route_invalid_strategy`** (L399)

  - **`test_find_route_total_cost`** (L405)

  - **`test_find_route_initial_state_preserved`** (L411)

  - **`test_find_route_none_state`** (L417)

  - **`test_find_route_iterations_recorded`** (L423)

  - **`test_find_route_elapsed_time_positive`** (L428)

  - **`test_find_route_edges_populated`** (L433)

- **`TestFindRouteAlternatives`** (línea 443) — 4 método(s) de test

  - **`test_find_alternatives`** (L444)

  - **`test_find_alternatives_disabled`** (L455)

  - **`test_find_alternatives_no_path`** (L461)

  - **`test_alternative_count_zero`** (L471)

- **`TestFindRouteConditional`** (línea 485) — 6 método(s) de test

  - **`test_conditional_edge_skipped_when_condition_unmet`** (L486)

  - **`test_conditional_edge_traversed_when_condition_met`** (L502)

  - **`test_effects_applied_along_path`** (L514)

  - **`test_effects_with_prerequisites`** (L525)
    - An edge requires a state set by a previous edge.

  - **`test_conditional_edge_unreachable_without_effect`** (L540)
    - If no edge sets 'ready', the b->c edge is never traversable.

  - **`test_state_with_colon_condition`** (L552)

- **`TestShortestPath`** (línea 569) — 5 método(s) de test

  - **`test_dijkstra_finds_shortest`** (L570)
    - A->C (cost 5), A->B->C (cost 1+1=2). Dijkstra should find A->B->C.

  - **`test_astar_finds_shortest`** (L578)

  - **`test_dijkstra_vs_greedy_divergence`** (L584)
    - With a uniform heuristic, greedy should behave like A* for simple graphs.

  - **`test_max_iterations_limit`** (L590)

  - **`test_max_iterations_large_enough`** (L597)

- **`TestBuildRoute`** (línea 607) — 1 método(s) de test

  - **`test_build_route_is_alias`** (L608)

- **`TestNodeEdgeOperations`** (línea 619) — 3 método(s) de test

  - **`test_add_edge_updates_node_out_edges`** (L620)

  - **`test_add_edge_updates_node_in_edges`** (L628)

  - **`test_add_edge_with_preconditions_and_effects`** (L635)

- **`TestValidateGraph`** (línea 651) — 11 método(s) de test

  - **`test_valid_graph_no_errors`** (L652)

  - **`test_invalid_graph_missing_node`** (L657)

  - **`test_invalid_cost_in_validation`** (L667)

  - **`test_out_edges_not_synchronized`** (L676)

  - **`test_disconnected_nodes_in_advanced_validation`** (L686)

  - **`test_advanced_validation_with_circular_path`** (L693)

  - **`test_advanced_validation_clean_graph`** (L703)

  - **`test_has_circular_path_no_cycle`** (L712)

  - **`test_has_circular_path_with_cycle`** (L716)

  - **`test_has_circular_path_nonexistent_node`** (L724)

  - **`test_high_degree_node_warning`** (L728)

- **`TestApplyPathEffects`** (línea 742) — 11 método(s) de test

  - **`test_apply_path_effects_simple`** (L743)

  - **`test_apply_path_effects_empty_path`** (L752)

  - **`test_apply_path_effects_single_node`** (L757)

  - **`test_apply_path_effects_no_edge_between`** (L762)

  - **`test_get_edges_for_path`** (L769)

  - **`test_get_edges_for_path_empty`** (L778)

  - **`test_get_edges_for_path_single_node`** (L782)

  - **`test_get_node_path_cost`** (L786)

  - **`test_get_node_path_cost_single_node`** (L791)

  - **`test_get_node_path_cost_empty`** (L795)

  - **`test_get_neighbors`** (L799)

- **`TestEdgeCreationHelpers`** (línea 811) — 5 método(s) de test

  - **`test_add_edge_with_preconditions`** (L812)

  - **`test_create_conditional_edge`** (L821)

  - **`test_create_conditional_edge_no_type_returns_false`** (L833)

  - **`test_create_effect_edge`** (L840)

  - **`test_create_effect_edge_no_type_returns_false`** (L850)

- **`TestSerialization`** (línea 862) — 21 método(s) de test

  - **`test_export_to_json_structure`** (L863)

  - **`test_export_to_json_node_fields`** (L872)

  - **`test_export_to_json_edge_fields`** (L880)

  - **`test_export_then_import_roundtrip`** (L889)

  - **`test_export_graph_json_file`** (L902)

  - **`test_export_graph_pickle_file`** (L911)

  - **`test_export_graph_invalid_format`** (L918)

  - **`test_import_graph_json_file`** (L923)

  - **`test_import_graph_invalid_format`** (L933)

  - **`test_import_from_json_invalid_data_raises`** (L938)

  - **`test_import_from_json_missing_edge_node_raises`** (L943)

  - **`test_import_from_json_nodes_as_dict`** (L949)

  - **`test_import_graph_invalid_json_raises`** (L955)

  - **`test_serialize_deserialize_condition`** (L960)

  - **`test_deserialize_condition_non_dict_returns_none`** (L973)

  - **`test_serialize_deserialize_effect`** (L976)

  - **`test_deserialize_effect_non_dict_returns_none`** (L987)

  - **`test_deserialize_node`** (L990)

  - **`test_deserialize_node_missing_id_raises`** (L998)

  - **`test_deserialize_node_from_dict_fallback`** (L1002)
    - When Node.from_dict fails, the fallback constructor is used.

  - **`test_json_safe_alias`** (L1008)

- **`TestNormalizeStrategy`** (línea 1017) — 8 método(s) de test

  - **`test_enum_passes_through`** (L1018)

  - **`test_string_astar`** (L1022)

  - **`test_string_a_star_variants`** (L1025)

  - **`test_string_dijkstra`** (L1030)

  - **`test_string_bfs`** (L1033)

  - **`test_string_dfs`** (L1036)

  - **`test_string_greedy`** (L1039)

  - **`test_invalid_strategy_raises`** (L1042)

- **`TestInternalHelpers`** (línea 1051) — 16 método(s) de test

  - **`test_state_signature_consistent`** (L1052)

  - **`test_state_signature_different_states_different`** (L1057)

  - **`test_state_signature_none_state`** (L1062)

  - **`test_state_signature_unserializable_fallback`** (L1067)

  - **`test_create_goal_from_node`** (L1073)

  - **`test_create_goal_from_node_with_metadata_target`** (L1081)

  - **`test_create_goal_from_node_with_metadata_description`** (L1088)

  - **`test_estimate_heuristic_no_exception`** (L1095)

  - **`test_estimate_heuristic_uses_weight`** (L1102)

  - **`test_normalize_max_iterations`** (L1108)

  - **`test_normalize_max_iterations_invalid`** (L1111)

  - **`test_normalize_max_iterations_zero`** (L1114)

  - **`test_normalize_alternative_count`** (L1117)

  - **`test_normalize_alternative_count_too_many`** (L1120)

  - **`test_normalize_alternative_count_invalid`** (L1123)

  - **`test_normalize_alternative_count_negative`** (L1126)

- **`TestCacheInvalidation`** (línea 1134) — 2 método(s) de test

  - **`test_invalidate_search_cache_increments_revision`** (L1135)

  - **`test_clear_search_cache_resets_graph_nodes`** (L1141)

- **`Weird`** (línea 1068) — 0 método(s) de test

---

<a name="hands/planner/test-task_executor"></a>
### `hands\planner\test_task_executor.py`

**Descripción:** Tests para TaskExecutor y tipos relacionados (src/hands/planner/task_executor.py).

**Módulos de origen probados:** src.hands.planner.htn_manager, src.hands.planner.node, src.hands.planner.task_executor

**Clases de test:**

- **`TestTaskExecutorStatus`** (línea 77) — 2 método(s) de test

  - **`test_values`** (L78)

  - **`test_all_distinct`** (L86)

- **`TestTaskExecutionMode`** (línea 91) — 2 método(s) de test

  - **`test_values`** (L92)

  - **`test_all_distinct`** (L98)

- **`TestTaskExecutionConfig`** (línea 103) — 10 método(s) de test

  - **`test_defaults`** (L104)

  - **`test_post_init_clamps_negatives`** (L113)

  - **`test_post_init_coerces_strings_to_bool`** (L119)

  - **`test_post_init_invalid_strings_use_defaults`** (L125)

  - **`test_post_init_finite_check`** (L131)

  - **`test_post_init_clamps_negative_floats`** (L135)

  - **`test_post_init_clamps_negative_ints`** (L139)

  - **`test_safe_int`** (L144)

  - **`test_safe_int_negative`** (L151)

  - **`test_safe_float`** (L155)

- **`TestTaskExecutorInit`** (línea 166) — 5 método(s) de test

  - **`test_default_config`** (L167)

  - **`test_custom_config`** (L178)

  - **`test_safe_get_returns_none_on_failure`** (L185)

  - **`test_safe_get_returns_value_on_success`** (L193)

  - **`test_statistics_initial`** (L199)

- **`TestTaskExecutorStaticHelpers`** (línea 215) — 31 método(s) de test

  - **`test_task_metadata_with_dict`** (L216)

  - **`test_task_metadata_without_attribute`** (L220)

  - **`test_task_metadata_non_dict`** (L224)

  - **`test_task_application_from_metadata`** (L228)

  - **`test_task_application_fallback_to_attribute`** (L232)

  - **`test_task_application_none`** (L236)

  - **`test_task_application_strips_whitespace`** (L240)

  - **`test_task_parameters_from_metadata`** (L244)

  - **`test_task_parameters_from_attribute`** (L248)

  - **`test_task_parameters_both_merge`** (L252)

  - **`test_task_parameters_no_params`** (L257)

  - **`test_as_list_none`** (L261)

  - **`test_as_list_various`** (L264)

  - **`test_as_list_empty_tuple`** (L272)

  - **`test_normalize_key_normal`** (L275)

  - **`test_normalize_key_spaces`** (L278)

  - **`test_normalize_key_none`** (L281)

  - **`test_normalize_key_empty`** (L284)

  - **`test_safe_number_float`** (L287)

  - **`test_safe_number_invalid`** (L290)

  - **`test_safe_number_none`** (L293)

  - **`test_safe_number_default`** (L296)

  - **`test_safe_number_inf`** (L299)

  - **`test_safe_number_zero`** (L302)

  - **`test_safe_number_nan`** (L305)

  - **`test_signature_accepts_matching`** (L308)

  - **`test_signature_accepts_with_kwargs`** (L314)

  - **`test_signature_rejects_non_matching`** (L320)

  - **`test_call_callback_direct_call`** (L326)

  - **`test_call_callback_single_arg_fallback`** (L334)

  - **`test_call_callback_incompatible_signature`** (L341)

- **`TestNormalizeExecutionResult`** (línea 353) — 15 método(s) de test

  - **`test_task_execution_result`** (L354)

  - **`test_task_execution_result_failed`** (L364)

  - **`test_dict_with_success_true`** (L370)

  - **`test_dict_with_success_false`** (L375)

  - **`test_dict_with_status_success`** (L380)

  - **`test_dict_with_status_failed`** (L384)

  - **`test_dict_success_as_string_true`** (L388)

  - **`test_dict_success_as_string_false`** (L392)

  - **`test_dict_no_success_no_status`** (L396)

  - **`test_bool_true`** (L400)

  - **`test_bool_false`** (L403)

  - **`test_none`** (L406)

  - **`test_object_with_success_attr`** (L411)

  - **`test_object_with_status_attr`** (L416)

  - **`test_object_without_status`** (L421)

- **`TestTruthySuccess`** (línea 428) — 15 método(s) de test

  - **`test_bool_true`** (L429)

  - **`test_bool_false`** (L432)

  - **`test_int_nonzero`** (L435)

  - **`test_int_zero`** (L438)

  - **`test_float_nonzero`** (L441)

  - **`test_str_true`** (L444)

  - **`test_str_completed`** (L447)

  - **`test_str_yes`** (L450)

  - **`test_str_ok`** (L453)

  - **`test_str_no`** (L456)

  - **`test_str_empty`** (L459)

  - **`test_str_random`** (L462)

  - **`test_none`** (L465)

  - **`test_str_1`** (L468)

  - **`test_str_0`** (L471)

- **`TestResolveActionName`** (línea 479) — 6 método(s) de test

  - **`test_from_metadata_action`** (L480)

  - **`test_from_metadata_action_name`** (L484)

  - **`test_fallback_to_task_id`** (L488)

  - **`test_fallback_to_metadata_capability`** (L493)

  - **`test_strips_whitespace`** (L498)

  - **`test_priority_order`** (L502)
    - action takes priority over action_name and capability.

- **`TestCalculateTaskCost`** (línea 508) — 10 método(s) de test

  - **`test_explicit_cost`** (L509)

  - **`test_invalid_cost_falls_back`** (L513)

  - **`test_no_explicit_cost_complexity_default`** (L519)

  - **`test_complexity_factor`** (L525)

  - **`test_complexity_with_app_open`** (L531)

  - **`test_app_not_open_no_discount`** (L539)

  - **`test_requires_ui_discount`** (L543)

  - **`test_negative_cost_ignored`** (L549)

  - **`test_estimated_cost_fallback`** (L555)

  - **`test_zero_cost_valid`** (L559)

- **`TestEvaluatePrecondition`** (línea 568) — 16 método(s) de test

  - **`test_callable_true`** (L569)

  - **`test_callable_false`** (L572)

  - **`test_callable_exception`** (L575)

  - **`test_string_key_exists`** (L578)

  - **`test_string_key_missing`** (L581)

  - **`test_string_key_falsy`** (L584)

  - **`test_dict_equals_match`** (L587)

  - **`test_dict_equals_mismatch`** (L590)

  - **`test_dict_value_match`** (L593)

  - **`test_dict_value_mismatch`** (L596)

  - **`test_dict_no_key`** (L599)

  - **`test_dict_truthy_key`** (L602)

  - **`test_dict_expected_field`** (L605)
    - TaskExecutor._evaluate_precondition does not check 'expected'; falls through to truthy check.

  - **`test_dict_expected_field_truthy`** (L609)
    - When 'expected' is present but no 'equals'/'value', uses truthy key check.

  - **`test_unknown_condition_type`** (L613)

  - **`test_string_with_spaces_not_stripped`** (L616)
    - TaskExecutor._evaluate_precondition does not strip spaces from string conditions.

- **`TestCheckTaskPreconditions`** (línea 626) — 22 método(s) de test

  - **`test_no_preconditions`** (L627)

  - **`test_dependency_satisfied`** (L631)

  - **`test_dependency_not_satisfied`** (L636)

  - **`test_no_dependencies`** (L641)

  - **`test_state_requirements_satisfied`** (L645)

  - **`test_state_requirements_not_satisfied`** (L649)

  - **`test_requires_ui_not_ready`** (L653)

  - **`test_requires_ui_ready`** (L657)

  - **`test_requires_ui_no_state`** (L661)

  - **`test_string_precondition_satisfied`** (L665)

  - **`test_string_precondition_not_satisfied`** (L669)

  - **`test_dict_precondition_satisfied`** (L673)

  - **`test_dict_precondition_not_satisfied`** (L677)

  - **`test_callable_precondition_satisfied`** (L681)

  - **`test_callable_precondition_not_satisfied`** (L685)

  - **`test_callable_precondition_exception`** (L689)

  - **`test_multiple_preconditions_all_pass`** (L693)

  - **`test_multiple_preconditions_one_fails`** (L697)

  - **`test_application_not_available_in_state`** (L701)

  - **`test_application_available_in_state`** (L706)

  - **`test_application_not_available_in_app_states`** (L711)

  - **`test_application_available_in_app_states`** (L716)

- **`TestConvertTaskToNode`** (línea 726) — 14 método(s) de test

  - **`test_basic_conversion`** (L727)

  - **`test_conversion_without_metadata`** (L747)

  - **`test_conversion_sets_callbacks`** (L755)

  - **`test_conversion_with_execute_callback`** (L761)

  - **`test_conversion_with_node_type_condition`** (L769)

  - **`test_conversion_invalid_node_type_defaults_to_action`** (L774)

  - **`test_conversion_with_dependencies`** (L779)

  - **`test_conversion_with_parameters`** (L784)

  - **`test_conversion_with_application`** (L789)

  - **`test_conversion_with_state_requirements`** (L794)

  - **`test_conversion_with_state_modifications`** (L799)

  - **`test_conversion_with_ui_element`** (L804)

  - **`test_conversion_node_type_object`** (L809)

  - **`test_conversion_handles_exception`** (L814)
    - If Node construction fails, returns None instead of crashing.

- **`TestCreateExecutionCallback`** (línea 832) — 3 método(s) de test

  - **`test_explicit_callback`** (L833)

  - **`test_explicit_callback_normalizes_dict_result`** (L843)

  - **`test_no_explicit_callback_returns_real_handler`** (L852)

- **`TestCreateSuccessCriteria`** (línea 859) — 8 método(s) de test

  - **`test_custom_checker`** (L860)

  - **`test_custom_checker_exception`** (L868)

  - **`test_default_criteria_success`** (L875)

  - **`test_default_criteria_failure`** (L880)

  - **`test_default_criteria_navigate_success`** (L885)

  - **`test_default_criteria_navigate_url_mismatch`** (L891)

  - **`test_default_criteria_url_no_target`** (L896)

  - **`test_default_criteria_url_field`** (L901)

- **`TestApplyResultToState`** (línea 911) — 5 método(s) de test

  - **`test_state_updates_applied`** (L912)

  - **`test_no_state_updates`** (L921)

  - **`test_result_mappings`** (L928)

  - **`test_unsuccessful_no_completed_task`** (L942)

  - **`test_no_execution_context_task_id`** (L949)

- **`TestShouldExecuteConditionally`** (línea 960) — 15 método(s) de test

  - **`test_no_conditions`** (L961)

  - **`test_browser_ready_true`** (L965)

  - **`test_browser_ready_false`** (L969)

  - **`test_browser_ready_missing`** (L973)

  - **`test_entity_resolved_true`** (L977)

  - **`test_entity_resolved_false`** (L981)

  - **`test_custom_string_condition_true`** (L985)

  - **`test_custom_string_condition_false`** (L989)

  - **`test_custom_string_condition_missing`** (L993)

  - **`test_callable_condition_true`** (L997)

  - **`test_callable_condition_false`** (L1001)

  - **`test_callable_condition_exception`** (L1005)

  - **`test_multiple_conditions_all_pass`** (L1011)

  - **`test_multiple_conditions_one_fails`** (L1015)

  - **`test_empty_conditions_list`** (L1019)

- **`TestExecuteTask`** (línea 1028) — 7 método(s) de test

  - **`test_successful_execution`** (L1029)

  - **`test_precondition_failure`** (L1037)

  - **`test_no_action_no_callback_failure`** (L1043)

  - **`test_stats_track_success`** (L1048)

  - **`test_stats_track_failure`** (L1056)

  - **`test_status_idle_after_execution`** (L1062)

  - **`test_timeout_exceeded_fails`** (L1070)

- **`TestExecuteTaskWithRetry`** (línea 1081) — 5 método(s) de test

  - **`test_retry_safe_succeeds_on_retry`** (L1082)

  - **`test_not_retry_safe_stops_on_first_failure`** (L1098)

  - **`test_retry_safe_max_retries_exhausted`** (L1106)

  - **`test_retry_safe_stops_after_execution_attempt`** (L1119)
    - When action_attempted is True and retry_safe is False, stops after first attempt.

  - **`test_non_retry_safe_allows_retry_on_no_attempt`** (L1133)
    - When action_attempted is False, non-retry-safe tasks still retry.

- **`TestExecuteTaskHierarchy`** (línea 1155) — 10 método(s) de test

  - **`test_sequential_all_success`** (L1165)

  - **`test_sequential_stops_on_failure`** (L1174)

  - **`test_sequential_empty`** (L1182)

  - **`test_parallel_disabled_falls_back_to_sequential`** (L1186)

  - **`test_parallel_enabled`** (L1195)

  - **`test_parallel_with_inter_task_dependency`** (L1206)
    - When tasks have dependencies between them, parallel falls back to sequential.

  - **`test_conditional_skips_when_condition_false`** (L1219)

  - **`test_conditional_executes_when_condition_true`** (L1229)

  - **`test_fallback_mode`** (L1241)

  - **`test_invalid_mode_value_error`** (L1253)
    - execute_task_hierarchy raises ValueError for unsupported modes.

  Métodos auxiliares (no test): _make_callback_task

- **`TestExecuteNode`** (línea 1264) — 5 método(s) de test

  - **`test_no_callback`** (L1265)

  - **`test_callback_success`** (L1272)

  - **`test_callback_failure`** (L1285)

  - **`test_callback_exception`** (L1298)

  - **`test_success_criteria_prevents_success`** (L1312)

- **`TestExecutionStatistics`** (línea 1334) — 8 método(s) de test

  - **`test_initial_statistics`** (L1335)

  - **`test_stats_after_success`** (L1346)

  - **`test_stats_after_failure`** (L1357)

  - **`test_update_execution_statistics_single`** (L1366)

  - **`test_update_execution_statistics_multiple`** (L1371)

  - **`test_update_execution_statistics_zero_count`** (L1379)

  - **`test_update_execution_statistics_negative`** (L1384)

  - **`test_update_execution_statistics_thread_safety`** (L1389)
    - _update_execution_statistics uses a lock for thread safety.

- **`TestLegacyCapabilityHandlers`** (línea 1398) — 8 método(s) de test

  - **`test_execute_prepare_navigator`** (L1399)

  - **`test_execute_navigate_to_target`** (L1404)

  - **`test_execute_check_availability`** (L1409)

  - **`test_execute_open_application`** (L1414)

  - **`test_execute_activate_window`** (L1419)

  - **`test_execute_navigate_to_search_engine`** (L1424)

  - **`test_execute_perform_search`** (L1429)

  - **`test_execute_legacy_task_capability`** (L1434)

- **`TestExecuteHierarchyEmpty`** (línea 1444) — 4 método(s) de test

  - **`test_sequential_empty`** (L1445)

  - **`test_parallel_empty`** (L1448)

  - **`test_conditional_empty`** (L1451)

  - **`test_fallback_empty`** (L1454)

- **`TestGetTaskExecutor`** (línea 1462) — 2 método(s) de test

  - **`test_returns_task_executor`** (L1463)

  - **`test_singleton_thread_safety`** (L1475)
    - get_task_executor uses a lock for thread safety.

---

<a name="hands/test-action_registry"></a>
### `hands\test_action_registry.py`

**Descripción:** Tests de ActionRegistry (src/hands/action_registry.py).

**Módulos de origen probados:** src.hands.action_registry

**Clases de test:**

- **`TestActionType`** (línea 17) — 2 método(s) de test

  - **`test_values`** (L18)

  - **`test_all_distinct`** (L25)

- **`TestActionInfo`** (línea 30) — 16 método(s) de test

  - **`test_post_init_normalizes_fields`** (L46)

  - **`test_post_init_resolves_string_action_type`** (L52)

  - **`test_post_init_normalizes_confidence`** (L56)

  - **`test_post_init_normalizes_cost`** (L60)

  - **`test_post_init_invalid_cost_raises`** (L64)

  - **`test_to_dict_serializes`** (L68)

  - **`test_to_dict_serializes_functions_as_string`** (L77)

  - **`test_matches_preconditions_no_conditions`** (L83)

  - **`test_matches_preconditions_dict_conditions`** (L87)

  - **`test_matches_preconditions_function`** (L92)

  - **`test_verify_success_no_checker`** (L97)

  - **`test_verify_success_checker_returns_true`** (L101)

  - **`test_verify_success_checker_returns_false`** (L106)

  - **`test_apply_effects_empty`** (L111)

  - **`test_apply_effects_dict_effect`** (L116)

  - **`test_apply_effects_function_effect`** (L121)

  Métodos auxiliares (no test): _make

- **`TestActionRegistryInit`** (línea 130) — 2 método(s) de test

  - **`test_default_init`** (L131)

  - **`test_get_action_registry_singleton`** (L140)

- **`TestActionRegistryRegister`** (línea 146) — 14 método(s) de test

  - **`test_register_action_returns_decorator`** (L150)

  - **`test_register_action_registers_function`** (L156)

  - **`test_register_action_empty_name_raises`** (L170)

  - **`test_register_action_empty_name_whitespace_raises`** (L174)

  - **`test_register_action_empty_category_raises`** (L178)

  - **`test_register_action_invalid_type_raises`** (L182)

  - **`test_register_action_strips_name`** (L186)

  - **`test_register_action_extracts_parameters_from_func`** (L193)

  - **`test_register_action_uses_explicit_parameters`** (L204)

  - **`test_register_action_detects_var_kwargs`** (L215)

  - **`test_register_action_non_callable_raises`** (L223)

  - **`test_register_action_increments_count`** (L228)

  - **`test_register_action_category_tracking`** (L237)

  - **`test_register_action_re_register_different_category`** (L254)

  Métodos auxiliares (no test): setup_method

- **`TestActionRegistryQuery`** (línea 267) — 10 método(s) de test

  - **`test_get_action_found`** (L283)

  - **`test_get_action_not_found`** (L288)

  - **`test_get_all_actions`** (L291)

  - **`test_get_actions_by_category`** (L297)

  - **`test_get_actions_by_category_not_found`** (L303)

  - **`test_get_plannable_actions`** (L307)

  - **`test_list_actions_all`** (L314)

  - **`test_list_actions_by_category`** (L318)

  - **`test_list_actions_unknown_category`** (L322)

  - **`test_get_action_categories`** (L325)

  Métodos auxiliares (no test): setup_method

- **`TestActionRegistryValidation`** (línea 330) — 9 método(s) de test

  - **`test_validate_action_exists_valid_params`** (L334)

  - **`test_validate_action_not_found`** (L344)

  - **`test_validate_action_params_not_mapping`** (L347)

  - **`test_can_execute_action_exists`** (L354)

  - **`test_can_execute_action_not_found`** (L361)

  - **`test_can_execute_with_state_no_preconditions`** (L364)

  - **`test_can_execute_with_failing_preconditions`** (L371)

  - **`test_get_action_cost_found`** (L382)

  - **`test_get_action_cost_not_found`** (L389)

  Métodos auxiliares (no test): setup_method

- **`TestActionRegistryIntegration`** (línea 394) — 5 método(s) de test

  - **`test_get_actions_for_planner_returns_dicts`** (L395)

  - **`test_get_actions_for_planner_excludes_disabled`** (L407)

  - **`test_get_actions_for_llama_returns_list_of_dicts`** (L423)

  - **`test_get_optimization_stats`** (L434)

  - **`test_optimize_logging_returns_none`** (L450)

---

<a name="hands/test-application_alias_resolution"></a>
### `hands\test_application_alias_resolution.py`

**Descripción:** Tests de resolución por alias — unidad 3.2.2.5 (FASE 3.2.2 — Carga).

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`TestEntityAliasesInMetadata`** (línea 69) — 4 método(s) de test
  - Verifica que las apps cargadas desde entities.json tienen sus
aliases almacenados en ``metadata['aliases']`` tras __init__.

  - **`test_github_has_aliases_in_metadata`** (L77)

  - **`test_youtube_has_aliases_in_metadata`** (L82)

  - **`test_twitch_has_aliases_in_metadata`** (L87)

  - **`test_entity_id_stored_in_metadata`** (L92)
    - ``_reconstruct_metadata`` almacena entity_id en metadata.

  Métodos auxiliares (no test): manager

- **`TestAliasResolutionEntityLoadedApps`** (línea 103) — 4 método(s) de test
  - ``get_application`` resuelve aliases de apps cargadas desde
entities.json (data/memory/entities.json).

  - **`test_resolve_github_by_alias`** (L112)

  - **`test_resolve_youtube_by_alias`** (L118)

  - **`test_resolve_twitch_by_alias`** (L124)

  - **`test_resolve_github_by_alias_returns_same_object_as_name`** (L129)
    - El alias y el nombre canónico devuelven la misma instancia.

  Métodos auxiliares (no test): manager

- **`TestAliasResolutionNoRegression`** (línea 142) — 4 método(s) de test
  - La resolución por alias no debe romper la resolución existente.

  - **`test_hardcoded_alias_still_works`** (L150)

  - **`test_static_alias_google_chrome`** (L155)
    - 'Google Chrome' sigue resolviendo a Chrome (alias estático).

  - **`test_canonical_name_still_works`** (L162)

  - **`test_spotify_resolvable_by_name`** (L167)

  Métodos auxiliares (no test): manager

- **`TestAliasResolutionNotFound`** (línea 177) — 3 método(s) de test
  - ``get_application`` devuelve ``None`` para aliases/nombres inexistentes.

  - **`test_unknown_alias_returns_none`** (L185)

  - **`test_none_input_returns_none`** (L188)

  - **`test_empty_string_returns_none`** (L191)

  Métodos auxiliares (no test): manager

- **`TestAliasResolutionDynamicRegistration`** (línea 199) — 4 método(s) de test
  - ``get_application`` resuelve aliases de apps registradas dinámicamente
con ``metadata['aliases']`` establecido explícitamente.

  - **`test_alias_resolves_for_dynamically_registered_app`** (L203)

  - **`test_alias_case_insensitive_for_dynamic_app`** (L216)

  - **`test_alias_does_not_shadow_existing_app`** (L226)
    - Un alias que coincide con una clave canónica distinta no debe
devolver la app equivocada. La resolución prioriza el lookup directo.

  - **`test_dynamically_registered_app_without_aliases_resolves_by_name`** (L240)
    - Una app registrada sin aliases sigue resolviéndose por su nombre.

- **`TestResolveAliasMethod`** (línea 253) — 5 método(s) de test
  - ``_resolve_alias`` retorna la app cuyo metadata['aliases'] contiene
el nombre normalizado, o ``None`` si no hay coincidencia.

  - **`test_resolve_alias_finds_matching_app`** (L257)

  - **`test_resolve_alias_no_match_returns_none`** (L266)

  - **`test_resolve_alias_empty_manager_returns_none`** (L274)

  - **`test_resolve_alias_handles_none_metadata`** (L278)
    - Apps con metadata=None o metadata sin 'aliases' no causan error.

  - **`test_resolve_alias_handles_non_dict_metadata`** (L289)
    - metadata que no es dict (p.ej. lista) se ignora gracefully.

- **`TestNormalizeNameBackwardCompat`** (línea 304) — 3 método(s) de test
  - ``_normalize_name`` sigue siendo un ``@staticmethod`` que resuelve
aliases estáticos hardcodeados. No se modificó su contrato.

  - **`test_static_alias_resolves_to_canonical`** (L316)

  - **`test_unknown_name_passes_through`** (L319)

  - **`test_none_safe`** (L322)

- **`_StubMemoryManager`** (línea 40) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity, get_entities_by_type

---

<a name="hands/test-application_classification"></a>
### `hands\test_application_classification.py`

**Descripción:** Tests de la unidad 3.8.1.3: distinguir aplicación instalada, en ejecución,
registrada en ApplicationManager y disponible para automatización.

**Módulos de origen probados:** src.hands.application_preflight, src.hands.applications_core

**Clases de test:**

- **`TestApplicationClassificationDataclass`** (línea 107) — 1 método(s) de test
  - La dataclass almacena los cuatro ejes y detalles.

  - **`test_fields_defaults`** (L110)

- **`TestClassifyRegistered`** (línea 131) — 3 método(s) de test
  - Eje registered: la app está en ApplicationManager.

  - **`test_registered_true`** (L134)

  - **`test_registered_false_unknown_app`** (L142)

  - **`test_registered_case_insensitive`** (L148)

- **`TestClassifyInstalled`** (línea 161) — 4 método(s) de test
  - Eje installed: ejecutable en disco o URL.

  - **`test_installed_true_real_executable`** (L164)

  - **`test_installed_true_url_only`** (L172)

  - **`test_installed_false_no_executable_no_url`** (L180)

  - **`test_installed_false_unknown_app`** (L188)

- **`TestClassifyRunning`** (línea 199) — 3 método(s) de test
  - Eje running: proceso activo en el sistema.

  - **`test_running_true_via_executable`** (L202)

  - **`test_running_false_no_process`** (L213)

  - **`test_running_false_unknown_app_no_executable`** (L223)

- **`TestClassifyAutomatable`** (línea 237) — 4 método(s) de test
  - Eje automatable: preflight aprobado y disponible.

  - **`test_automatable_true`** (L240)

  - **`test_automatable_false_preflight_blocked`** (L261)

  - **`test_automatable_false_confidence_unknown`** (L278)

  - **`test_automatable_false_not_installed`** (L295)

- **`TestClassifyCombined`** (línea 317) — 3 método(s) de test
  - Combinaciones de los cuatro ejes.

  - **`test_all_true`** (L320)

  - **`test_installed_not_registered_not_running_not_automatable`** (L342)

  - **`test_registered_but_not_installed_not_running`** (L354)

- **`TestClassifyEdgeCases`** (línea 383) — 3 método(s) de test
  - Casos borde: nombre vacío, None, excepciones.

  - **`test_empty_name`** (L386)

  - **`test_whitespace_name`** (L396)

  - **`test_preflight_exception_does_not_crash`** (L403)

- **`TestClassifyDetails`** (línea 420) — 1 método(s) de test
  - El diccionario details contiene información útil de depuración.

  - **`test_details_contains_executable_and_type`** (L423)

- **`TestClassifyUnknown`** (línea 439) — 3 método(s) de test
  - Eje unknown: la app no se conoce ni es resoluble sobre apps registradas.

  - **`test_unknown_true_for_unregistered_app`** (L442)

  - **`test_unknown_false_for_registered_app`** (L449)

  - **`test_unknown_true_for_empty_name`** (L458)

- **`TestClassifyLocalizable`** (línea 484) — 5 método(s) de test
  - Eje localizable: instalada y se determina un ejecutable/local concreto.

  - **`test_localizable_true_when_executable_in_path`** (L487)

  - **`test_localizable_false_when_executable_not_found`** (L496)

  - **`test_localizable_false_for_url_only_app`** (L505)

  - **`test_localizable_true_when_absolute_existing_path`** (L515)

  - **`test_localizable_false_for_unknown_app`** (L526)

- **`_FakeMemoryManager`** (línea 43) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-application_consumers_real_model"></a>
### `hands\test_application_consumers_real_model.py`

**Descripción:** Tests de verificación de consumidores con el modelo real de aplicaciones.

**Módulos de origen probados:** src.brain.llm, src.hands.applications_core, src.hands.executor, src.hands.planner.application_integration, src.hands.planner.htn_manager, src.hands.planner.planner

**Clases de test:**

- **`_RecordingIntegrator`** (línea 71) — 0 método(s) de test
  - Wrapper del integrador real que registra llamadas get_application.

  Métodos auxiliares (no test): __init__, _get_application

- **`TestIntegratorConsumesRealCatalog`** (línea 90) — 10 método(s) de test
  - El integrador consume el catálogo real (Chrome + entidades reconstruidas).

  - **`test_convert_nodes_chrome_real_with_capabilities`** (L93)
    - convert_application_to_nodes('chrome') produce nodo app + capability + ui
usando el modelo REAL (Chrome hardcodeado con capabilities y ui_elements).

  - **`test_convert_nodes_alias_through_integrator`** (L104)
    - convert_application_to_nodes('gh') resuelve el alias a GitHub (reconstruido
desde entities.json, sin capabilities) y produce solo el nodo app.

  - **`test_get_application_capabilities_chrome_real`** (L116)
    - get_application_capabilities('chrome') expone las capabilities reales.

  - **`test_get_application_capabilities_alias_no_capabilities`** (L125)
    - get_application_capabilities('yt') resuelve alias → YouTube (reconstruido
sin capabilities) → dict vacío.

  - **`test_is_application_capable_chrome_open`** (L132)
    - is_application_capable('chrome', OPEN) True con el modelo real.

  - **`test_is_application_capable_alias_not_capable`** (L137)
    - YouTube (reconstruido sin capabilities) no es capaz de OPEN.

  - **`test_get_applications_by_capability_open`** (L142)
    - get_applications_by_capability(OPEN) incluye Chrome y Spotify (las únicas
con la capability declarada en el modelo real). El integrador devuelve List[str].

  - **`test_get_ui_elements_for_capability_chrome_navigate`** (L154)
    - get_ui_elements_for_capability('chrome', NAVIGATE) → ['address_bar'].

  - **`test_get_application_ui_elements_chrome_real`** (L162)
    - ApplicationManager.get_application_ui_elements expone los elementos UI reales
de Chrome (consumido indirectamente por Planner.get_application_ui_requirements).

  - **`test_catalog_has_real_apps_beyond_hardcoded`** (L171)
    - El modelo real carga aplicaciones reconstruidas desde entities.json.

- **`TestBrainConsumesRealCatalog`** (línea 186) — 6 método(s) de test
  - Brain consume el catálogo real a través del integrador singleton.

  - **`test_returns_expected_dict_format`** (L194)
    - El formato de salida es {applications, total_applications, supported_capabilities}.

  - **`test_total_applications_matches_catalog`** (L202)
    - total_applications coincide con el número de apps del modelo real.

  - **`test_chrome_entry_has_capabilities_and_availability_keys`** (L209)
    - La entrada chrome tiene capabilities (dict), declared=True (declarada
en el modelo) y claves de disponibilidad (available, capability_available).

Nota: bajo el contrato 3.3.2.2, 'available' indica disponibilidad en tiempo
de ejecución (ejecutable en PATH o URL), no simplemente si la capability
está declarada. 'declared' refleja la capability declarada en el modelo
(determinista: Chrome declara OPEN → True).

  - **`test_reconstructed_app_entry`** (L230)
    - YouTube (reconstruido, sin capabilities) aparece con capabilities={}.

  - **`test_supported_capabilities_is_list_of_strings`** (L243)
    - supported_capabilities es una lista de strings.

  - **`test_all_entries_have_required_keys`** (L250)
    - Todas las entradas tienen capabilities, declared, available y capability_available.

  Métodos auxiliares (no test): _brain

- **`TestPlannerConsumesRealCatalog`** (línea 268) — 6 método(s) de test
  - Planner consume el catálogo real a través del integrador singleton.

  - **`test_load_application_knowledge_loads_real_nodes`** (L277)
    - load_application_knowledge carga nodos de apps reales al catálogo del planner.

  - **`test_get_applications_by_capability_open_includes_chrome`** (L285)
    - get_applications_by_capability('open') incluye Chrome.

  - **`test_get_application_capabilities_chrome`** (L290)
    - get_application_capabilities('chrome') devuelve open_chrome.

  - **`test_get_application_capabilities_alias`** (L296)
    - get_application_capabilities('gh') resuelve alias → GitHub → {}.

  - **`test_get_application_ui_requirements_chrome_navigate`** (L301)
    - get_application_ui_requirements('chrome', 'navigate') → ['address_bar'].

  - **`test_get_application_ui_requirements_chrome_open_empty`** (L306)
    - La capability 'open' de Chrome no requiere elementos UI.

  Métodos auxiliares (no test): _planner

- **`TestHTNManagerConsumesRealCatalog`** (línea 316) — 2 método(s) de test
  - HTNManager consulta disponibilidad del catálogo del integrador.

  - **`test_catalog_available_with_real_integrator`** (L319)
    - Con el integrador real y el catálogo cargado, devuelve True.

  - **`test_catalog_available_false_when_empty`** (L325)
    - Con applications vacío, devuelve False (compat con 3.1.3.2).

- **`TestExecutorConsumesRealCatalog`** (línea 344) — 4 método(s) de test
  - Executor consumir el catálogo real como fallback cuando el estado runtime está vacío.

  - **`test_browser_available_via_catalog_fallback`** (L353)
    - browser_available True vía catálogo cuando el runtime no observa apps.

  - **`test_application_available_via_catalog_fallback`** (L358)
    - application_available True vía catálogo cuando el runtime está vacío.

  - **`test_browser_available_via_runtime_state`** (L363)
    - browser_available True cuando el runtime observa Chrome abierto.

  - **`test_application_available_via_catalog_after_runtime_empty`** (L370)
    - application_available True vía catálogo real con manager cargado.

  Métodos auxiliares (no test): executor

- **`TestInternalFunctionsConsumeRealModel`** (línea 380) — 9 método(s) de test
  - open_application, _check_application_available y _check_application_login
consumen el modelo real resolviendo apps y aliases.

  - **`test_check_available_chrome_with_executable_in_path`** (L384)
    - _check_application_available('chrome') resuelve el ejecutable del modelo real
vía shutil.which. Si el ejecutable está en PATH → True.

  - **`test_check_available_chrome_executable_not_in_path`** (L392)
    - _check_application_available('chrome') False cuando el ejecutable no está en PATH.

  - **`test_check_available_url_only_fallback`** (L398)
    - _check_application_available con app sin ejecutable pero con URL → True
(fallback a url, consumido por open_application preflight).

  - **`test_check_available_youtube_via_executable`** (L406)
    - YouTube (reconstruido con executable='chrome.exe') se valida por ejecutable.

  - **`test_check_login_returns_true`** (L413)
    - _check_application_login siempre devuelve True (compat).

  - **`test_open_application_chrome_uses_model`** (L418)
    - open_application('chrome') resuelve desde el modelo real y lanza el ejecutable.

  - **`test_open_application_alias_resolves_to_real_app`** (L430)
    - open_application('gh') resuelve el alias a GitHub y lanza su ejecutable.

  - **`test_open_application_not_found_raises`** (L444)
    - open_application con app inexistente levanta ValueError.

  - **`test_open_application_minimal_app_with_executable`** (L449)
    - open_application con app minimal (contrato 3.1.2) y ejecutable funciona.

---

<a name="hands/test-application_contract_no_duplication"></a>
### `hands\test_application_contract_no_duplication.py`

**Descripción:** Tests del contrato minimo 3.1.2.4 — verificacion de duplicacion de informacion.

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage, src.utils.config

**Clases de test:**

- **`TestContractFieldOverlapWithEntityModel`** (línea 135) — 5 método(s) de test
  - Verifica cuales campos del contrato comparten nombre con el modelo Entity.

  - **`test_entity_has_10_top_level_fields`** (L138)
    - Entity define 10 campos (storage.py:46-58).

  - **`test_contract_has_13_fields`** (L145)
    - ApplicationKnowledge define 13 campos (3.1.2.3 verificado).

  - **`test_shared_top_level_field_names`** (L149)
    - Campos cuyo nombre aparece tanto en ApplicationKnowledge como en Entity.

Estos son los puntos de duplicacion de NOMBRE a nivel top-level:
- `name`: ApplicationKnowledge.name == Entity.name
- `type`: ApplicationKnowledge.type (categoria de app, ej. 'browser') vs
  Entity.type ('application' — categoria de entidad). El NOMBRE coincide
  aunque el significado sea distinto; register_application duplica el valor
  de app.type dentro de Entity.properties.type.
- `metadata`: ambos modelos disponen del campo, aunque register_application
  no lo popula (queda None en Entity).

  - **`test_entity_only_fields_not_in_contract`** (L166)
    - Campos de Entity que NO existen en el contrato (no son duplicacion).

  - **`test_contract_only_fields_not_in_entity`** (L174)
    - Campos del contrato que NO existen como campo top-level de Entity.

- **`TestRegisterApplicationDuplicatesFields`** (línea 190) — 5 método(s) de test
  - register_application copia campos del contrato a Entity.properties.

Verificacion de aplicaciones_core.py:354-368: `entity_data["properties"]`
contiene exactamente {type, executable, url, login_required, capabilities,
ui_elements, states}. Estos DUPLICAN los campos homonimos de
ApplicationKnowledge.

  - **`test_entity_properties_keys_are_duplicated_contract_fields`** (L199)
    - Las claves de Entity.properties son campos del contrato (duplicacion).

  - **`test_entity_properties_keys_count_is_seven`** (L224)
    - register_application escribe exactamente 7 claves en Entity.properties.

3.2.2.2: ui_elements y states se unen al conjunto persistido, pasando
de 5 a 7 claves.

  - **`test_entity_name_duplicated_from_contract`** (L235)
    - Entity.name es una copia directa de ApplicationKnowledge.name.

  - **`test_entity_id_derived_from_contract_name`** (L243)
    - Entity.id se DERIVA de name (app_{name.lower()}); no es un campo del contrato.

La derivacion no es duplicacion directa: `id` no existe en ApplicationKnowledge,
pero codifica el mismo identificador. Verificado para confirmar que `id` no
es un campo redundante del contrato.

  - **`test_entity_type_is_entity_category_not_app_type`** (L257)
    - Entity.type='application' (categoria de entidad) difiere de app.type.

register_application pone app.type dentro de properties.type (duplicacion
del valor real del contrato), mientras Entity.type top-level es siempre
'application'. Esto confirma que `type` se duplica con valores distintos
segun el nivel: no es redundancia inutil sino una division de responsabilidad
(Entity.type=entidad, properties.type=aplicacion).

- **`TestRegisterApplicationValueConsistency`** (línea 278) — 2 método(s) de test
  - Los valores duplicados deben ser consistentes entre contrato y Entity.

  - **`test_duplicated_scalar_values_match`** (L281)

  - **`test_capabilities_duplicated_as_string_values`** (L295)
    - capabilities se duplica como lista de strings (capability.value),
mientras el contrato usa List[ApplicationCapabilityDef]. La forma difiere:
ApplicationCapabilityDef se reduce a su enum value en la Entity.

- **`TestRegisterApplicationLostFields`** (línea 328) — 1 método(s) de test
  - Campos del contrato que register_application NO persiste en la Entity.

  - **`test_lost_optional_field_absent_from_entity_properties`** (L332)
    - Estos campos opcionales se pierden: no aparecen en Entity.properties.

- **`TestRegisterApplicationDuplicatedOptionalFields`** (línea 347) — 2 método(s) de test
  - Campos opcionales que register_application SÍ persiste en Entity.properties
(duplican el contrato). Complementa 3.1.2.3.

  - **`test_duplicated_optional_field_present_in_properties`** (L352)
    - executable, url, login_required y capabilities se duplican en properties.

  - **`test_no_extra_properties_beyond_duplication_set`** (L365)
    - Entity.properties no contiene claves ajenas al conjunto de duplicacion.

- **`TestContractOverlapWithDataFileSchema`** (línea 381) — 5 método(s) de test
  - Verifica la superposicion de nombres de campos entre el contrato y
data/knowledge/applications.json (D2, D5, D6).

applications.json NO es cargado por ApplicationManager.__init__ (D5); solo se
consume como dict raw en DomainMemory (conversation.py:170-178). El contrato
y el fichero coexisten sin adaptador (D6). Estos tests documentan la
superposicion de nombres y las diferencias de representacion.

  - **`test_applications_json_exists`** (L391)

  - **`test_applications_json_schema_keys`** (L394)
    - Schema de applications.json: name, executable, capabilities, states,
ui_elements, login_required, calibration_needed (NO `type` top-level).

  - **`test_contract_field_names_overlapping_with_applications_json`** (L409)
    - Campos del contrato cuyo nombre tambien aparece en applications.json.

  - **`test_applications_json_has_field_not_in_contract`** (L420)
    - calibration_needed existe en applications.json pero NO en el contrato.

  - **`test_construction_type_differs_between_contract_and_json`** (L427)
    - El contrato requiere `type` (obligatorio); applications.json no lo tiene.

Esto confirma D2: el modelo hardcoded (name='Chrome', type='browser') no
coincide con el JSON (key='chrome', name='Google Chrome', sin type).

- **`TestKnowledgeOutputOverlapsContract`** (línea 442) — 3 método(s) de test
  - get_application_knowledge (aplicaciones_core.py:982-1002) serializa de
vuelta los campos del contrato a un dict. Verifica cuales se duplican y
cual cae (icon).

  - **`test_knowledge_output_keys_subset_of_contract`** (L447)
    - Todas las claves devueltas estan en el contrato o son campos calculados
introducidos por 3.3.2.2 (available, declared_capabilities).

  - **`test_knowledge_output_drops_icon_field`** (L458)
    - `icon` esta en el contrato pero get_application_knowledge NO lo expone.

Esto es una duplicacion parcial/incompleta: 12 de 13 campos del contrato
se reexponen, pero `icon` se pierde en la serializacion (Chrome no lo
popula -> None). Ademas (3.3.2.2) se añaden 2 campos calculados:
'available' y 'declared_capabilities'.

  - **`test_knowledge_output_keys_count`** (L478)
    - get_application_knowledge expone 14 claves (13 - icon + 2 calculados).

- **`_FakeMemoryManager`** (línea 93) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-application_data_format"></a>
### `hands\test_application_data_format.py`

**Descripción:** Tests de verificacion del FORMATO REAL de las fuentes de datos de
Application Knowledge - unidad 3.2.1.2 (FASE 3.2.1 - Fuente de datos).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage, src.utils.config

**Clases de test:**

- **`TestMemoryEntitiesJsonFormat`** (línea 104) — 12 método(s) de test
  - Verifica el formato REAL de `data/memory/entities.json`, la fuente que
`_load_custom_applications` consume via get_entities_by_type('application').

  - **`test_file_exists`** (L108)

  - **`test_top_level_is_list`** (L111)

  - **`test_total_entity_count`** (L115)

  - **`test_application_entity_count`** (L120)

  - **`test_application_entity_ids`** (L128)

  - **`test_every_entity_has_all_entity_fields`** (L148)

  - **`test_entity_key_order_is_consistent_across_all_entities`** (L155)
    - Todas las entidades reales comparten un unico orden de claves.

  - **`test_file_key_order_differs_from_dataclass_declaration`** (L166)
    - El orden de claves del JSON difiere del orden de declaracion del
dataclass Entity (created_at/updated_at/metadata aparecen al final del
dataclass, pero intercalados tras confidence en el archivo). La lectura
no depende del orden (Entity.from_dict usa cls(**data)), pero el formato
real se documenta aqui.

  - **`test_application_entity_properties_keys`** (L177)
    - properties real: {url, executable, category} (NO type/login_required/capabilities).

  - **`test_spotify_application_has_no_url_property`** (L189)
    - spotify.properties carece de 'url' en los datos reales.

  - **`test_entity_from_dict_round_trip`** (L199)
    - Entity.from_dict parsea TODAS las entidades reales sin error.

  - **`test_entity_from_dict_preserves_metadata_none`** (L209)
    - metadata: null en JSON se mantiene como None tras from_dict.

- **`TestGetEntitiesByTypeRuntime`** (línea 220) — 7 método(s) de test
  - Verifica el canal real `get_entities_by_type('application')` (storage.py:718)
sobre una copia de los datos reales, con un MemoryManager aislado.

  - **`test_loads_all_application_entities`** (L230)
    - get_entities_by_type('application') devuelve todas las aplicaciones
reales (32) de entities.json.

  - **`test_returns_entity_instances`** (L237)

  - **`test_entity_ids_match_real_source`** (L242)

  - **`test_entity_names_match_real_source`** (L258)

  - **`test_entity_type_is_application_string`** (L274)

  - **`test_entity_properties_structure_preserved`** (L279)

  - **`test_get_entities_by_type_streamer_returns_three`** (L290)

  Métodos auxiliares (no test): isolated_mm

- **`TestApplicationsMemoryFileFormat`** (línea 299) — 6 método(s) de test
  - Verifica que `data/memory/applications.json` existe como dict vacio {} y
esta mapeado a MemoryType.APPLICATIONS, pero NO es usado por ApplicationManager.

  - **`test_file_exists`** (L303)

  - **`test_top_level_is_dict`** (L308)

  - **`test_content_is_empty_dict`** (L314)

  - **`test_memory_type_applications_maps_to_applications_json`** (L320)
    - JSONStorage.file_mapping mapea MemoryType.APPLICATIONS -> applications.json.

  - **`test_default_value_for_applications_is_dict`** (L326)

  - **`test_no_code_reads_applications_via_memory_type`** (L330)
    - Ningun codigo de applications_core.py referencia MemoryType.APPLICATIONS.

- **`TestKnowledgeApplicationsJsonFormat`** (línea 343) — 9 método(s) de test
  - Verifica el formato REAL de `data/knowledge/applications.json`, leido por
conversation.py:172 (DomainKnowledge) con un schema DISTINTO al modelo
ApplicationKnowledge (D5/D6).

  - **`test_file_exists`** (L348)

  - **`test_top_level_is_dict`** (L351)

  - **`test_keys_are_internal_app_names`** (L357)

  - **`test_entry_schema`** (L363)
    - Cada entrada: name, executable, capabilities, states, ui_elements,
login_required, calibration_needed (NO `type` top-level).

  - **`test_capabilities_are_string_list`** (L378)

  - **`test_ui_elements_are_dict_of_dicts`** (L388)

  - **`test_states_are_dict_of_bool`** (L398)

  - **`test_calibration_needed_is_string_list`** (L406)

  - **`test_schema_differs_from_contract`** (L414)
    - El schema de knowledge/applications.json difiere del contrato
ApplicationKnowledge (calibration_needed vs calibration_policy; states
Dict vs List; capabilities List[str] vs List[ApplicationCapabilityDef]).

- **`TestRegisterApplicationVsRealFormatDiscrepancy`** (línea 434) — 4 método(s) de test
  - Documenta D-ENTIDAD-PROPERTIES: register_application (aplicaciones_core.py:354)
escribe Entity.properties = {type, executable, url, login_required,
capabilities, ui_elements, states},
pero el formato REAL de entities.json tiene properties = {url, executable, category}.
Las dos representaciones son INCOMPATIBLES en las claves: _load_custom_applications
reconstruye ApplicationKnowledge desde la Entity real usando defaults para
los campos ausentes (3.2.2.2).

  - **`test_register_application_writes_documented_properties_keys`** (L443)
    - register_application persiste exactamente las 7 claves documentadas
(type, executable, url, login_required, capabilities, ui_elements, states).

  - **`test_register_application_capabilities_serialized_as_strings`** (L456)
    - capabilities se serializa a List[str] (capability.value).

  - **`test_real_entities_properties_differ_from_registered_schema`** (L474)
    - properties REAL de entities.json: {url, executable, category};
schema de register_application: {type, executable, url, login_required,
capabilities, ui_elements, states}. La intersecion es solo
{executable, url}.

  - **`test_registered_entity_properties_is_incompatible_with_real`** (L494)
    - Una Entity construida por register_application NO encajaria en el
formato real de entities.json (le faltan type/login_required/capabilities
de properties; le sobra category). Confirma la discrepancia de schema.

- **`TestKnowledgeEntitiesDuplicateFormat`** (línea 514) — 4 método(s) de test
  - Documenta D-KNOWLEDGE-ENTITIES-DUP: `data/knowledge/entities.json` existe
con contenido IDENTICO a `data/memory/entities.json`, servido por canales
distintos (conversation.py:149 vs MemoryManager.get_entities_by_type).

  - **`test_knowledge_entities_file_exists`** (L519)

  - **`test_knowledge_entities_equals_memory_entities_content`** (L524)
    - knowledge/entities.json es un SNAPSHOT OBSOLETO de 7 entidades;
memory/entities.json tiene 35 entidades actualizadas. Ya no coinciden:
documenta la desincronizacion del canal legacy (D-KNOWLEDGE-ENTITIES-DUP).
knowledge/entities.json deberia estar sincronizado con memory/entities.json
o deprecado.

  - **`test_knowledge_entities_has_same_application_ids`** (L538)
    - knowledge/entities.json (snapshot legacy de 7) contiene solo 4 apps.

  - **`test_contract_states_field_uses_application_state`** (L549)
    - El contrato declara states: Optional[List[ApplicationState]] y
default_state = ApplicationState.CLOSED (aplicaciones_core.py:147,151).
Con `from __future__ import annotations`, .type se almacena como cadena.
Esto contrasta con knowledge/applications.json donde states es
Dict[str, bool] (D5).

- **`_CapturingMemoryManager`** (línea 82) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-application_data_incomplete"></a>
### `hands\test_application_data_incomplete.py`

**Descripción:** Tests de verificacion del comportamiento ante DATOS INCOMPLETOS
— unidad 3.2.1.4 (FASE 3.2.1 — Fuente de datos).

**Módulos de origen probados:** src.hands.applications_core, src.memory.conversation, src.memory.storage

**Clases de test:**

- **`TestJsonStorageLoadCorruptedJson`** (línea 136) — 4 método(s) de test
  - JSONStorage.load() con JSON sintacticamente invalido (truncated).

  - **`test_load_truncated_json_returns_default`** (L143)
    - JSON truncado → JSONDecodeError capturado → devuelve [] (default).

  - **`test_load_truncated_json_applications_default`** (L151)
    - JSON truncado para applications.json → devuelve {} (default).

  - **`test_load_garbage_returns_default`** (L159)
    - Contenido no-JSON (garbage) → JSONDecodeError → default.

  - **`test_load_partial_json_object_returns_default`** (L165)
    - Un objeto JSON incompleto → JSONDecodeError → default.

  Métodos auxiliares (no test): storage

- **`TestJsonStorageLoadWrongTopLevelType`** (línea 175) — 5 método(s) de test
  - JSONStorage.load() con JSON valido pero tipo top-level inesperado.

load() no valida el tipo del dato parseado: solo captura JSONDecodeError
y Exception general. Si el JSON es valido pero tiene estructura incorrecta
(p.ej. dict en vez de list para entities), load() devuelve el dato tal cual.

  - **`test_load_entities_as_dict_returns_dict`** (L187)
    - entities.json con un dict (no una lista) → load() devuelve el dict.

  - **`test_load_entities_as_string_returns_string`** (L196)
    - entities.json con un string → load() lo devuelve tal cual.

  - **`test_load_entities_null_returns_none`** (L202)
    - entities.json con `null` → load() devuelve None (no JSONDecodeError).

  - **`test_load_applications_as_list_returns_list`** (L208)
    - applications.json con una lista (no un dict) → load() devuelve la lista.

  - **`test_warm_cache_normalizes_null_entities_to_list`** (L216)
    - _warm_cache: si load() devuelve None para entities, la cache se
inicializa con [] (entones `entities_data if entities_data is not None
else []`).

  Métodos auxiliares (no test): storage

- **`TestEntityFromDictMissingRequiredFields`** (línea 228) — 5 método(s) de test
  - Entity.from_dict() con campos obligatorios ausentes.

El dataclass Entity declara id, type, name y properties como campos
requeridos (sin default). from_dict() solo rellena defaults para
created_at, updated_at, aliases, confidence, tags y metadata. Si falta
cualquiera de los 4 campos requeridos, cls(**data) lanza TypeError.

  - **`test_missing_id_raises_type_error`** (L237)

  - **`test_missing_type_raises_type_error`** (L243)

  - **`test_missing_name_raises_type_error`** (L249)

  - **`test_missing_properties_raises_type_error`** (L255)

  - **`test_missing_all_required_raises_type_error`** (L261)

- **`TestEntityFromDictMissingOptionalFields`** (línea 270) — 7 método(s) de test
  - Entity.from_dict() rellena defaults para campos opcionales ausentes.

  - **`test_missing_created_at_filled`** (L273)

  - **`test_missing_updated_at_filled`** (L280)

  - **`test_missing_aliases_filled_with_empty_list`** (L286)

  - **`test_missing_confidence_filled_with_one`** (L292)

  - **`test_missing_tags_filled_with_empty_list`** (L298)

  - **`test_missing_metadata_filled_with_none`** (L304)

  - **`test_missing_all_optionals_still_constructs`** (L310)
    - Una entity con solo los 4 campos obligatorios se construye OK.

- **`TestEntityFromDictWithNullAndWrongTypeProperties`** (línea 330) — 2 método(s) de test
  - Entity.from_dict() no valida el tipo de `properties`.

- `properties: null` (JSON null → Python None) → entity.properties = None.
- `properties` como lista en vez de dict → entity.properties = lista.
Ambas se construyen sin error porque el dataclass no valida tipos.

  - **`test_properties_null_does_not_raise`** (L338)

  - **`test_properties_as_list_does_not_raise`** (L354)

- **`TestGetEntitiesByTypeWithIncompleteData`** (línea 369) — 7 método(s) de test
  - get_entities_by_type() con datos incompletos (actualizado por 3.2.3.2).

Con el manejo per-item introducido en 3.2.3.2, si una entity con `type`
que coincide carece de un campo obligatorio, `Entity.from_dict()` lanza
`TypeError` capturado per-item: la entity invalida se omite (registro de
error) y NO se pierden las entities validas del mismo tipo.

  - **`test_valid_entity_loaded_when_no_incomplete`** (L383)
    - Sin datos incompletos, la entity valida se carga correctamente.

  - **`test_incomplete_entity_missing_name_skipped_valid_loaded`** (L389)
    - Una entity application que falta `name` se omite per-item (TypeError
capturado); la entity valida 'ok' se carga correctamente. No se pierden
las applications validas. (Contrato definido por 3.2.3.2.)

  - **`test_incomplete_entity_missing_properties_skipped_valid_loaded`** (L408)
    - Una entity application que falta `properties` se omite per-item;
la entity valida 'ok' se carga. No se pierden las applications validas.
(Contrato definido por 3.2.3.2.)

  - **`test_incomplete_entity_missing_id_skipped_valid_loaded`** (L425)
    - Una entity application que falta `id` se omite per-item;
la entity valida 'ok' se carga. No se pierden las applications validas.
(Contrato definido por 3.2.3.2.)

  - **`test_non_dict_items_skipped_valid_entity_loaded`** (L442)
    - Items no-dict en la lista (string, None, int) son omitidos por el
filtro isinstance(entity_data, dict); la entity valida se carga.

  - **`test_entity_with_properties_none_loaded`** (L456)
    - Una entity con properties=null (JSON null → None) se carga sin error;
properties queda None.

  - **`test_incomplete_non_matching_type_does_not_affect`** (L467)
    - Una entity de tipo distinto (streamer) que es incompleta no afecta
a la carga de entities application validas, porque solo se filtra por
type antes de llamar from_dict.

  Métodos auxiliares (no test): isolated_mm

- **`TestGetEntityWithIncompleteData`** (línea 491) — 5 método(s) de test
  - get_entity() con datos incompletos (actualizado por 3.2.3.2).

Con el manejo per-item introducido en 3.2.3.2, si la entity con el ID
buscado carece de campos obligatorios, `Entity.from_dict()` captura el
`TypeError` y devuelve `None` (no lo propaga al llamador).

  - **`test_get_entity_incomplete_returns_none`** (L499)
    - get_entity('bad_app') con una entity incompleta (falta name)
→ devuelve None (TypeError capturado per-item, no propagado).
(Contrato definido por 3.2.3.2.)

  - **`test_get_entity_valid_returns_entity`** (L518)
    - get_entity() sobre una entity completa funciona normalmente.

  - **`test_get_entity_incomplete_other_does_not_crash`** (L527)
    - Si una entity distinta a la buscada es incompleta, get_entity no
se rompe (solo parsea la entity que coincide por ID).

  - **`test_get_entity_nonexistent_returns_none`** (L546)
    - get_entity sobre un ID inexistente devuelve None (no lanza).

  - **`test_get_entity_empty_list_returns_none`** (L552)
    - get_entity con entities.json vacia ([]) devuelve None.

- **`TestFindEntitiesWithIncompleteData`** (línea 562) — 3 método(s) de test
  - find_entities() con datos incompletos (actualizado por 3.2.3.2).

Con el manejo per-item introducido en 3.2.3.2, cada entity se reconstruye
con `Entity.from_dict()` dentro de un try/except per-item: una entity
incompleta se omite (registro de error) y no propaga `TypeError`; las
entities validas que coinciden con la query se devuelven normalmente.

  - **`test_find_entities_incomplete_skipped_valid_loaded`** (L571)
    - find_entities() con una entity incompleta (falta name) → la entity
invalida se omite per-item; la entity valida 'ok' que coincide con la
query se devuelve. No se propaga TypeError.
(Contrato definido por 3.2.3.2.)

  - **`test_find_entities_all_valid_returns_matches`** (L592)
    - find_entities() con entities completas funciona normalmente.

  - **`test_find_entities_empty_list_returns_empty`** (L603)
    - find_entities() con entities.json vacia ([]) → [].

- **`TestApplicationManagerWithIncompleteData`** (línea 613) — 6 método(s) de test
  - ApplicationManager.__init__() con datos incompletos en entities.json.

__init__ llama _initialize_applications() (hardcoded Chrome/Spotify) y
luego _load_custom_applications() que procesa entities reales. Con el
manejo per-item de 3.2.3.2, una entity application invalida (falta name)
se omite individualmente: la app valida 'Good' se carga desde entities
y la invalida se registra y descarta, sin afectar a Chrome/Spotify.

  - **`test_init_does_not_crash`** (L646)

  - **`test_chrome_and_spotify_present`** (L650)
    - Las apps hardcodeadas siguen presentes pese a datos incompletos.

  - **`test_open_capability_apps_present`** (L656)
    - get_applications_by_capability(OPEN) devuelve Chrome y Spotify.

  - **`test_load_custom_applications_returns_none`** (L663)
    - _load_custom_applications() devuelve None (metodo void), no lanza.
Procesa entities reales con manejo per-item: omite la invalida.

  - **`test_valid_custom_app_loaded_invalid_skipped`** (L670)
    - La app valida 'Good' (entity 'ok') se carga desde entities; la
entity incompleta (falta name) se omite per-item y no aparece en el
modelo. Chrome y Spotify permanecen. (Contrato definido por 3.2.3.2.)

  - **`test_repeated_load_no_effect`** (L682)
    - Llamar _load_custom_applications() explicitamente no anade apps
duplicadas (solo carga las ya registradas).

  Métodos auxiliares (no test): manager_with_incomplete

- **`TestDomainMemoryWithIncompleteData`** (línea 695) — 4 método(s) de test
  - DomainMemory.load_domain_knowledge() con datos incompletos.

- knowledge/applications.json: entries incompletos se almacenan tal
  cual (dict raw, sin validacion de schema).
- knowledge/entities.json: si una entity carece de campos obligatorios,
  StorageEntity.from_dict() lanza TypeError, capturado por el try/except
  de la carga → self.entities queda {}.

  - **`test_incomplete_app_entry_stored_as_is`** (L705)
    - Aplicación incompleta en knowledge/applications.json se almacena
tal cual (raw dict, sin validacion).

  - **`test_incomplete_entity_loses_subsequent_entities`** (L728)
    - knowledge/entities.json con una entity que falta `name` →
StorageEntity.from_dict() lanza TypeError, capturado por el try/except
de load_domain_knowledge. La entity valida CARGADA ANTES de la
incompleta se conserva en self.entities; la incompleta y las
siguientes se pierden. Se registra el error pero no se propaga.

  - **`test_complete_entities_in_knowledge_load_fine`** (L760)
    - knowledge/entities.json con entities completas se cargan OK.

  - **`test_incomplete_app_entry_does_not_break_applications_load`** (L777)
    - Una entry de aplicación incompleta no rompe la carga de aplicaciones
(DomainMemory.load_domain_knowledge carga applications como raw dict).

- **`TestErrorLoggingDuringLoad`** (línea 798) — 10 método(s) de test
  - Verifica que los errores de carga se registran con detalle y sin
ocultar la excepcion (unidad 3.2.3.3).

- Cargas per-item (entity invalida) → WARNING con id de entity y texto
  de la excepcion.
- Errores generales (JSONStorage.load/save, save_entity, _warm_cache) →
  ERROR con detalle de la excepcion.
- No se usan mensajes genericos "Procesando solicitud" en paths de error.

  - **`test_load_corrupted_json_logs_warning`** (L819)
    - JSON truncado → JSONDecodeError capturado → se registra WARNING
con referencia al archivo y la excepcion.

  - **`test_get_entity_invalid_logs_warning_with_id_and_exception`** (L836)
    - get_entity con entity que falta 'name' → WARNING que incluye el
id de la entity y el texto de la excepcion (TypeError).

  - **`test_get_entities_by_type_invalid_logs_warning`** (L861)
    - get_entities_by_type con entity incompleta → WARNING per-item
con el id y la excepcion; la entity valida se carga igual.

  - **`test_find_entities_invalid_logs_warning`** (L886)
    - find_entities con entity incompleta → WARNING per-item con el id
y la excepcion.

  - **`test_find_entities_by_property_invalid_logs_warning`** (L911)
    - find_entities_by_property con entity incompleta → WARNING per-item
con el id y la excepcion.

  - **`test_per_item_errors_are_not_info_level`** (L944)
    - Los errores per-item deben ser WARNING, nunca INFO.

  - **`test_no_generic_processing_request_in_error_paths`** (L967)
    - Ningun mensaje de error debe contener el texto generico
'Procesando solicitud'.

  - **`test_save_entity_exception_logs_error_with_exception`** (L986)
    - save_entity con file permission error → ERROR que incluye el
tipo de excepcion.

  - **`test_json_storage_save_exception_logs_error`** (L1010)
    - JSONStorage.save() con excepcion → ERROR con detalle.

  - **`test_warm_cache_exception_logs_error`** (L1026)
    - _warm_cache con excepcion en load() → ERROR con detalle.

  Métodos auxiliares (no test): storage, mm

---

<a name="hands/test-application_discovered_temporary"></a>
### `hands\test_application_discovered_temporary.py`

**Descripción:** Registro temporal en memoria de aplicaciones descubiertas (unidad 3.8.4.1).

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`_FakeMemoryManager`** (línea 38) — 0 método(s) de test
  - Memory manager simulado que registra si se llamo a save_entity.

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

- **`TestRegisterDiscoveredApplicationInMemoryOnly`** (línea 60) — 3 método(s) de test
  - La aplicacion descubierta queda solo en memoria; no toca entities.json.

  - **`test_registra_solo_en_memoria_sin_llamar_save_entity`** (L63)

  - **`test_es_recuperable_via_get_application_clave_normalizada`** (L82)

  - **`test_clave_case_insensitive`** (L91)

- **`TestDiscoveredMetadataSeparation`** (línea 99) — 4 método(s) de test
  - Separacion de hechos observados, datos inferidos y capacidades no verificadas.

  - **`test_metadata_marca_discovered_temporary_source`** (L102)

  - **`test_observed_facts_guardados_en_metadata`** (L113)

  - **`test_inferred_data_guardado_por_separado`** (L122)

  - **`test_capacidades_no_verificadas_aceptadas`** (L131)

- **`TestDiscoveredAppDoesNotOverrideRegistered`** (línea 150) — 6 método(s) de test
  - No entra en conflicto con aplicaciones ya registradas (Chrome, Spotify).

  - **`test_no_sobrescribe_app_existente_en_memoria`** (L153)

  - **`test_no_sobrescribe_por_alias_de_app_existente`** (L178)
    - Nombre normalizado de descubierta colisiona con alias de app registrada.

  - **`test_no_sobrescribe_por_alias_de_descubierta_que_colisiona_con_nombre`** (L198)
    - Alias de la descubierta colisiona con nombre normalizado de app registrada.

  - **`test_no_sobrescribe_por_alias_compartido_entre_descubiertas`** (L217)
    - Dos descubiertas comparten un alias: la primera se conserva.

  - **`test_registro_nuevo_sin_conflicto_registra_ok`** (L238)
    - Nombre y alias nuevos sin conflicto: se registra normalmente.

  - **`test_app_descubierta_no_afecta_get_de_app_registrada`** (L254)

- **`TestMinimalConstruction`** (línea 263) — 1 método(s) de test
  - Construccion minima: solo name (type default "application").

  - **`test_solo_name_es_suficiente`** (L266)

- **`TestGlobalManagerIntegration`** (línea 275) — 1 método(s) de test
  - Integracion con la instancia global get_application_manager (no persiste).

  - **`test_global_manager_puede_registrar_descubierta`** (L278)

---

<a name="hands/test-application_discovery_no_recursive_disk_search"></a>
### `hands\test_application_discovery_no_recursive_disk_search.py`

**Descripción:** Verifica que el descubrimiento de aplicaciones no usa busqueda recursiva por disco como mecanismo por defecto.

**Módulos de origen probados:** src.hands.calibration_manager

*Sin clases de test definidas.*

---

<a name="hands/test-application_discovery_persistence_contract"></a>
### `hands\test_application_discovery_persistence_contract.py`

**Descripción:** Contrato de persistencia para aplicaciones descubiertas — unidad 3.8.4.2.

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`_FakeMemoryManager`** (línea 46) — 0 método(s) de test
  - Memory manager simulado que registra las entidades pasadas a save_entity.

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

- **`TestSaveEntityDescartaMetadataDeDescubrimiento`** (línea 105) — 2 método(s) de test
  - Persistir una app descubierta mediante register_application/save_entity
descarta todos los campos que la identifican como descubierta/temporal.

  - **`test_registro_persiste_solo_siete_claves_y_descarta_metadata`** (L109)

  - **`test_capacidades_se_reducen_a_nombres_y_pierden_detalle`** (L135)
    - Las ApplicationCapabilityDef se reducen a capability.value en la Entity;
preconditions/efectos/coste/tiempo de espera de la capacidad no se
persisten, por lo que la estructura completa del contrato no sobrevive.

- **`TestDescubiertasNuncaSePersisten`** (línea 153) — 2 método(s) de test
  - register_discovered_application mantiene la app solo en memoria; no
invoca save_entity, por lo que entities.json no se altera.

  - **`test_registra_solo_en_memoria_sin_llamar_save_entity`** (L157)

  - **`test_metadata_de_descubierta_se_conserva_solo_en_memoria`** (L173)

- **`TestNoDuplicacionNiEscrituraDeEntitiesJson`** (línea 194) — 2 método(s) de test
  - Re-registrar una app descubierta no escribe en save_entity ni duplica.

  - **`test_registro_repetido_no_llama_save_entity`** (L197)

  - **`test_app_descubierta_no_sobrescribe_catalogo_persistido`** (L207)
    - Una app descubierta con nombre de app conocida (p.ej. Chrome)
se guarda solo en memoria y no genera entidad de persistencia.

---

<a name="hands/test-application_discovery_separation"></a>
### `hands\test_application_discovery_separation.py`

**Descripción:** Separacion de hechos observados, datos inferidos y capacidades no verificadas (unidad 3.8.4.3).

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`_FakeMemoryManager`** (línea 38) — 0 método(s) de test
  - Memory manager simulado que registra si se llamo a save_entity.

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

- **`TestApplicationKnowledgeObservedFacts`** (línea 75) — 4 método(s) de test
  - get_observed_facts expone los hechos observados almacenados en metadata.

  - **`test_devuelve_hechos_observados_almacenados`** (L78)

  - **`test_devuelve_dict_vacio_sin_metadata`** (L90)

  - **`test_devuelve_dict_vacio_sin_observed_facts`** (L95)

  - **`test_devuelve_copia_no_la_referencia_interna`** (L103)

- **`TestApplicationKnowledgeInferredData`** (línea 114) — 4 método(s) de test
  - get_inferred_data expone los datos inferidos almacenados en metadata.

  - **`test_devuelve_datos_inferidos_almacenados`** (L117)

  - **`test_devuelve_dict_vacio_sin_metadata`** (L129)

  - **`test_devuelve_dict_vacio_sin_inferred_data`** (L134)

  - **`test_devuelve_copia_no_la_referencia_interna`** (L142)

- **`TestApplicationKnowledgeUnverifiedCapabilities`** (línea 153) — 4 método(s) de test
  - get_unverified_capabilities expone capacidades declaradas pero no verificadas en runtime.

  - **`test_capacidad_declarada_sin_exe_es_no_verificada`** (L156)

  - **`test_capacidad_declarada_con_exe_es_verificada`** (L173)

  - **`test_sin_capacidades_devuelve_lista_vacia`** (L186)

  - **`test_mezcla_capacidades_verificadas_y_no_verificadas`** (L194)

- **`TestApplicationManagerSeparationQueries`** (línea 212) — 3 método(s) de test
  - Metodos de consulta de ApplicationManager para la separacion 3.8.4.3.

  - **`test_get_application_observed_facts`** (L215)

  - **`test_get_application_inferred_data`** (L224)

  - **`test_get_application_unverified_capabilities`** (L233)

- **`TestSeparationCoexistsWithExistingContracts`** (línea 245) — 2 método(s) de test
  - La separacion no rompe contratos existentes de 3.8.4.1 y 3.8.4.2.

  - **`test_metadata_mantiene_discovered_temporary_source`** (L248)

  - **`test_no_llama_save_entity_al_consultar_separacion`** (L262)

---

<a name="hands/test-application_discovery_sources"></a>
### `hands\test_application_discovery_sources.py`

**Descripción:** Identificacion de fuentes reales de descubrimiento de aplicaciones en Windows.

**Módulos de origen probados:** src.hands.calibration_manager

**Clases de test:**

- **`TestIdentificacionFuentesDescubrimientoWindows`** (línea 282) — 3 método(s) de test
  - Evidencia real de las fuentes de descubrimiento de aplicaciones en Windows.

  - **`test_todas_las_fuentes_retornan_estructura_bien_formada`** (L285)
    - Cada fuente ejecuta sin fallar y devuelve diccionario con campos esperados.

  - **`test_fuente_instaladas_retorna_resultados_reales`** (L304)
    - La fuente de aplicaciones instaladas ejecuta el mecanismo real y reporta hallazgos.

  - **`test_imprime_resumen_evidencia_todas_las_fuentes`** (L313)
    - Imprime el resumen completo de evidencia real de cada fuente (para registro canonico).

---

<a name="hands/test-application_identification"></a>
### `hands\test_application_identification.py`

**Descripción:** Tests del contrato minimo 3.1.2.1 — identificacion univoca de una aplicacion.

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestApplicationNameIsIdentifier`** (línea 24) — 3 método(s) de test
  - `name` es el campo que identifica inequívocamente una aplicación.

  - **`test_name_is_required_no_default`** (L27)
    - ApplicationKnowledge no permite construir sin `name`.

  - **`test_name_identifies_in_manager_dict`** (L32)
    - El gestor indexa por `name.lower()`.

  - **`test_name_case_insensitive`** (L47)
    - El identificador es case-insensitive: 'MYAPP' resuelve a 'myapp'.

- **`TestNormalizeName`** (línea 55) — 3 método(s) de test
  - `_normalize_name` resuelve aliases a la clave canónica (name.lower()).

  - **`test_alias_resolves_to_canonical`** (L66)

  - **`test_unknown_name_passes_through`** (L69)
    - Un nombre sin alias se normaliza a su lowercased directamente.

  - **`test_none_safe`** (L73)

- **`TestGetApplicationByAlias`** (línea 77) — 3 método(s) de test
  - `get_application` resuelve alias mediante `_normalize_name`.

  - **`test_resolve_alias_to_app`** (L80)

  - **`test_resolve_canonical_name`** (L86)

  - **`test_unknown_returns_none`** (L92)

- **`TestEntityIdUsesName`** (línea 97) — 2 método(s) de test
  - El Entity persistido usa `app_{name.lower()}` como id.

  - **`test_entity_id_matches_name_lowercased`** (L100)

  - **`test_entity_aliases_always_empty`** (L117)
    - `register_application` persiste aliases=[] siempre (no conecta _normalize_name).

- **`TestNameUniquenessBehavior`** (línea 136) — 2 método(s) de test
  - El nombre lowercased es la única clave; registro duplicado se omite.

Unidad 3.2.2.3 (Evitar duplicados al registrar): si el nombre normalizado
(name.lower()) ya está en ``self.applications``, ``register_application``
omite la persistencia y devuelve ``False`` sin sobreescribir la app existente.
Esto reemplaza al comportamiento PREVIO de sobrescritura (overwrite), que
esta clase de tests documentaba antes de 3.2.2.3.

  - **`test_same_name_skipped`** (L146)
    - Registro duplicado (misma clave name.lower()) se omite, no sobreescribe.

  - **`test_distinct_names_cohabit`** (L172)

- **`TestNameInKnowledgeOutput`** (línea 186) — 1 método(s) de test
  - `get_application_knowledge` expone `name` como identificador público.

  - **`test_knowledge_exposes_name`** (L189)

- **`FakeMM`** (línea 37) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity

- **`FakeMM`** (línea 126) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity

- **`FakeMM`** (línea 151) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity

- **`FakeMM`** (línea 176) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity

---

<a name="hands/test-application_invalid_json"></a>
### `hands\test_application_invalid_json.py`

**Descripción:** Tests de definicion del resultado ante JSON invalido — unidad 3.2.3.1
(FASE 3.2.3 — Errores, bajo 3.2 CARGA Y REGISTRO).

**Módulos de origen probados:** src.hands.applications_core, src.memory.conversation, src.memory.storage

**Clases de test:**

- **`TestJsonStorageLoadInvalidJson`** (línea 96) — 4 método(s) de test
  - JSONStorage.load() con JSON sintacticamente invalido.

Cualquier JSON invalido (truncated, garbage, vacio) debe ser capturado
por json.JSONDecodeError y devolver el valor por defecto correspondiente,
sin propagar la excepcion.

  - **`test_load_entities_invalid_json_returns_default`** (L117)
    - JSON invalido en entities.json -> load() devuelve [] (default).

  - **`test_load_applications_invalid_json_returns_default`** (L129)
    - JSON invalido en applications.json -> load() devuelve {} (default).

  - **`test_load_does_not_raise_on_invalid_json`** (L136)
    - load() no propaga JSONDecodeError ni ninguna excepcion.

  - **`test_load_returns_default_for_all_types_with_invalid_json`** (L142)
    - Cada tipo de memoria con JSON invalido devuelve su default.

  Métodos auxiliares (no test): storage

- **`TestJsonStorageLoadExistingDataWithInvalidJson`** (línea 167) — 3 método(s) de test
  - _load_existing_data() con JSON invalido devuelve None (no lanza).

  - **`test_load_existing_returns_none_for_invalid_json`** (L180)
    - _load_existing_data con JSON invalido -> None.

  - **`test_load_existing_returns_none_when_file_missing`** (L187)
    - _load_existing_data con fichero inexistente -> None.

  - **`test_load_existing_returns_data_when_valid`** (L192)
    - _load_existing_data con JSON valido -> devuelve el dato parseado.

  Métodos auxiliares (no test): storage

- **`TestMemoryManagerWithInvalidJson`** (línea 203) — 7 método(s) de test
  - MemoryManager.get_entities_by_type() con entities.json corrupto.

  - **`test_get_entities_by_type_returns_empty_list`** (L212)
    - JSON invalido -> get_entities_by_type('application') devuelve [].

  - **`test_get_entities_by_type_returns_empty_for_any_type`** (L218)
    - JSON invalido -> get_entities_by_type para cualquier tipo devuelve [].

  - **`test_find_entities_returns_empty`** (L223)
    - JSON invalido -> find_entities devuelve [] (no lanza).

  - **`test_get_entity_returns_none`** (L228)
    - JSON invalido -> get_entity devuelve None (no lanza).

  - **`test_warm_cache_handles_corrupted_file`** (L232)
    - _warm_cache no lanza excepcion con entities.json corrupto;
la cache se inicializa con [].

  - **`test_save_then_load_file_is_valid_json`** (L239)
    - Tras save_entity con fichero corrupto, el fichero es JSON valido
(register/save repara el fichero corrupto sobreescribiendolo).

  - **`test_save_then_get_entities_by_type_reflects_changes`** (L251)
    - Tras save_entity con fichero corrupto, get_entities_by_type
refleja las entities registradas (via cache actualizada).

  Métodos auxiliares (no test): corrupted_mm

- **`TestApplicationManagerInitWithInvalidJson`** (línea 269) — 7 método(s) de test
  - ApplicationManager.__init__() con entities.json corrupto.

El init llama register_application(chrome/spotify) + _load_custom_applications().
Con JSON invalido: no debe lanzar excepcion, las apps hardcodeadas permanecen.

  - **`test_init_does_not_crash`** (L288)
    - __init__() con JSON invalido no lanza excepcion.

  - **`test_chrome_present_after_init`** (L293)
    - Chrome (hardcodeada) esta disponible pese a JSON invalido.

  - **`test_spotify_present_after_init`** (L298)
    - Spotify (hardcodeada) esta disponible pese a JSON invalido.

  - **`test_open_capability_apps_present`** (L303)
    - Las apps con capacidad OPEN (Chrome, Spotify) estan disponibles.

  - **`test_no_custom_apps_loaded`** (L310)
    - No se cargan aplicaciones custom (el JSON estaba corrupto).

  - **`test_file_repaired_after_init`** (L315)
    - Tras __init__, entities.json es sobrescrito con JSON valido
(register_application repara el fichero corrupto).

  - **`test_init_resilient_to_various_invalid_json`** (L329)
    - __init__() no se rompe con distintos tipos de JSON invalido.

  Métodos auxiliares (no test): init_with_corrupted

- **`TestLoadCustomApplicationsWithInvalidJson`** (línea 346) — 3 método(s) de test
  - _load_custom_applications() con entities.json corrupto.

  - **`test_load_custom_applications_does_not_crash`** (L361)
    - _load_custom_applications() no lanza excepcion con JSON invalido.

  - **`test_repeated_load_no_effect`** (L367)
    - Llamar _load_custom_applications() explicitamente no anade apps
y no lanza excepcion.

  - **`test_get_entities_by_type_returns_only_init_apps`** (L376)
    - Tras init con JSON corrupto, get_entities_by_type('application')
devuelve solo las apps registradas durante init (no custom apps del
fichero corrupto, que no se pudieron cargar). No lanza excepcion.

  Métodos auxiliares (no test): manager_with_corrupted

- **`TestRegisterApplicationWithCorruptedFile`** (línea 394) — 5 método(s) de test
  - register_application() y save_entity() con entities.json corrupto.

Definicion de resultado:
- register_application no lanza excepcion (try/except interno).
- save_entity lee [] (JSON invalido -> default), anade la entity, y
  escribe JSON valido al fichero (reparacion: el fichero deja de ser
  invalido).

  - **`test_register_application_does_not_crash_with_corrupted_file`** (L404)
    - register_application con fichero corrupto no lanza excepcion.

  - **`test_register_application_repairs_file`** (L414)
    - Despues de register_application, el fichero es JSON valido.

  - **`test_register_application_app_added_to_internal_dict`** (L427)
    - La app registrada esta en el dict interno aunque el fichero sea corrupto.

  - **`test_save_entity_with_corrupted_file_returns_true`** (L437)
    - save_entity con fichero corrupto devuelve True (reparacion OK).

  - **`test_save_entity_overwrites_corrupted_file_with_valid_json`** (L445)
    - save_entity sobrescribe fichero corrupto con JSON valido.

- **`TestMemoryManagerInvalidJsonVariants`** (línea 460) — 2 método(s) de test
  - MemoryManager con distintos tipos de JSON sintacticamente invalido.

  - **`test_get_entities_by_type_returns_empty`** (L471)
    - Cualquier JSON invalido -> get_entities_by_type devuelve [].

  - **`test_null_json_does_not_cause_crash`** (L477)
    - entities.json = null -> load() devuelve None -> get_entities_by_type
normaliza a [] -> devuelve []. No crash.

- **`TestDomainMemoryWithInvalidJson`** (línea 489) — 4 método(s) de test
  - DomainMemory.load_domain_knowledge() con knowledge files corruptos.

DomainMemory lee knowledge/entities.json y knowledge/applications.json
via json.load() directo (conversation.py:149-175). Si el JSON es
invalido, el try/except externo captura la excepcion y deja
self.entities/self.applications vacios.

  - **`test_invalid_entities_json_leaves_empty`** (L498)
    - knowledge/entities.json corrupto -> self.entities = {} (no crash).

  - **`test_invalid_applications_json_leaves_empty`** (L511)
    - knowledge/applications.json corrupto -> self.applications = {} (no crash).

  - **`test_invalid_entities_json_valid_apps_ok`** (L524)
    - entities.json corrupto pero applications.json valido ->
entities vacias, applications cargadas.

  - **`test_both_files_invalid_leaves_empty`** (L541)
    - Ambos ficheros corruptos -> entities y applications vacios (no crash).

---

<a name="hands/test-application_load"></a>
### `hands\test_application_load.py`

**Descripción:** Tests de carga del conjunto de aplicaciones — unidad 3.2.2.2 (FASE 3.2.2).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage, src.utils.config

**Clases de test:**

- **`TestSerializeUIElement`** (línea 138) — 6 método(s) de test
  - Verifica que _serialize_ui_element produce dicts JSON-friendly.

UIElement ahora representa solo conocimiento declarativo (name, type,
description, required_capability). Los campos de coordenadas han sido
removidos: pertenecen al CoordinateManager en tiempo de ejecución.

  - **`test_serialize_basic_element`** (L146)

  - **`test_serialize_with_description`** (L156)

  - **`test_serialize_with_capability`** (L161)

  - **`test_serialize_is_json_serializable`** (L171)
    - El dict resultante no contiene objetos enum (solo strings).

  - **`test_serialize_no_coordinate_fields_by_default`** (L181)
    - _serialize_ui_element solo incluye coordinates cuando están presentes.

  - **`test_serialize_with_coordinates`** (L190)
    - _serialize_ui_element incluye coordinates cuando están presentes.

- **`TestReconstructUIElements`** (línea 208) — 12 método(s) de test
  - Verifica la reconstruccion robusta de UIElement desde dicts.

  - **`test_valid_elements_reconstructed`** (L211)

  - **`test_none_input_returns_empty`** (L224)

  - **`test_non_list_input_returns_empty`** (L227)

  - **`test_empty_list_returns_empty`** (L231)

  - **`test_non_dict_items_skipped`** (L234)

  - **`test_item_missing_name_skipped`** (L240)

  - **`test_item_missing_type_skipped`** (L246)

  - **`test_invalid_capability_becomes_none`** (L252)

  - **`test_none_capability_stays_none`** (L258)

  - **`test_description_reconstructed`** (L263)

  - **`test_description_defaults_empty`** (L269)

  - **`test_all_fields_preserved`** (L274)
    - Todos los campos se preservan: conocimiento declarativo y coordenadas.

- **`TestReconstructStates`** (línea 299) — 9 método(s) de test
  - Verifica la reconstruccion robusta de ApplicationState desde strings.

  - **`test_valid_states_reconstructed`** (L302)

  - **`test_none_input_returns_default_closed`** (L311)

  - **`test_non_list_input_returns_default_closed`** (L315)

  - **`test_empty_list_returns_default_closed`** (L319)

  - **`test_invalid_state_skipped`** (L322)

  - **`test_all_invalid_returns_default_closed`** (L326)

  - **`test_non_string_items_skipped`** (L330)

  - **`test_case_insensitive`** (L334)

  - **`test_error_state_reconstructed`** (L338)

- **`TestReconstructApplicationWithUIElementsAndStates`** (línea 347) — 6 método(s) de test
  - Verifica que _reconstruct_application materializa ui_elements y states.

  - **`test_reconstruct_with_ui_elements`** (L350)

  - **`test_reconstruct_with_states`** (L365)

  - **`test_reconstruct_without_ui_elements_uses_default`** (L376)
    - Entity sin ui_elements en properties -> default [].

  - **`test_reconstruct_without_states_uses_default_closed`** (L383)
    - Entity sin states en properties -> default [CLOSED].

  - **`test_reconstruct_full_app_presists_all_fields`** (L390)

  - **`test_reconstruct_capabilities_uses_minimal_defaults`** (L406)
    - Las capabilities reconstruidas usan defaults minimos (cost=5.0, empty).

- **`TestRegisterApplicationPersistsUIElementsAndStates`** (línea 422) — 5 método(s) de test
  - Verifica que register_application escribe ui_elements/states en properties.

  - **`test_register_persists_ui_elements`** (L425)

  - **`test_register_empty_ui_elements_defaults`** (L445)
    - App con defaults (ui_elements=[], states=[CLOSED]) se persiste.

  - **`test_register_saves_entity_to_memory`** (L455)

  - **`test_register_entity_properties_keys_count_is_seven`** (L462)
    - register_application escribe exactamente 7 claves en Entity.properties.

  - **`test_register_app_added_to_internal_dict`** (L473)
    - register_application también registra la app en memoria interna.

- **`TestRoundTripRegisterLoad`** (línea 485) — 4 método(s) de test
  - Round-trip completo: register_application persiste, luego _load_custom_applications
reconstruye con ui_elements y states preservados.

  - **`test_round_trip_preserves_ui_elements`** (L489)

  - **`test_round_trip_preserves_capabilities_as_strings`** (L517)

  - **`test_round_trip_multiple_apps_no_collision`** (L539)

  - **`test_round_trip_legacy_entity_gets_defaults`** (L558)
    - Legacy entity (sin ui_elements/states) -> defaults al reconstruir.

- **`TestLoadFullApplicationSet`** (línea 574) — 6 método(s) de test
  - Carga las 32 aplicaciones reales de entities.json con MemoryManager real
en sandbox (tmp_path). Verifica que el conjunto se materializa con
defaults para ui_elements/states (legacy format).

  - **`test_loads_four_applications`** (L594)

  - **`test_application_ids_match_real_source`** (L599)

  - **`test_legacy_apps_get_default_states`** (L614)
    - Entidades legacy (sin states) -> [ApplicationState.CLOSED].

  - **`test_legacy_apps_get_empty_ui_elements`** (L623)
    - Entidades legacy (sin ui_elements) -> [].

  - **`test_all_loaded_apps_are_application_knowledge`** (L632)

  - **`test_app_specific_properties_preserved`** (L638)
    - Verifica que los campos legacy se preservan tras la reconstruccion.

  Métodos auxiliares (no test): _setup, _make_manager_with_real_mm

- **`_StoringMemoryManager`** (línea 53) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-application_load_correctness"></a>
### `hands\test_application_load_correctness.py`

**Descripción:** Tests de carga correcta e incorrecta — unidad 3.2.3.4 (FASE 3.2.3 — Errores,
bajo 3.2 CARGA Y REGISTRO).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestCargaCorrecta`** (línea 155) — 6 método(s) de test
  - La carga materializa correctamente las applications válidas.

  - **`test_load_valid_application_reconstructs_all_fields`** (L158)
    - Una entidad `application` válida se reconstruye con todos sus campos
a nivel de gestor (carga correcta).

  - **`test_load_preserves_aliases_and_entity_id_in_metadata`** (L195)
    - Los aliases de la entidad aparecen en metadata y se conserva el
entity_id; el nombre normalizado no colisiona con los aliases.

  - **`test_load_preserves_application_type`** (L210)
    - El tipo de aplicación se mantiene tras la carga.

  - **`test_load_multiple_valid_applications`** (L222)
    - Varias applications válidas se cargan como apps independientes bajo
su nombre normalizado.

  - **`test_load_legacy_category_maps_to_application_type`** (L239)
    - Una entidad legacy (properties con `category`, sin `type`) reconstruye
ApplicationKnowledge.type == category (formato legacy).

  - **`test_load_returns_none_on_success`** (L259)
    - _load_custom_applications es void: retorna None (no lanza) con datos
correctos.

- **`TestCargaIncorrecta`** (línea 274) — 6 método(s) de test
  - La carga omite de forma segura las entidades que no deben materializarse
como aplicación, sin afectar a las válidas ni a las ya registradas.

  - **`test_load_skips_non_application_type_entities`** (L278)
    - Una entidad cuyo `type` (discriminador) no es `application` (p. ej.
`streamer`) no se materializa como aplicación; solo las `application`
válidas se cargan.

  - **`test_load_skips_invalid_entity_missing_name_keeps_valid`** (L301)
    - Una entidad `application` inválida (falta `name`, campo obligatorio)
se omite per-item durante `get_entities_by_type`; una entidad válida
vecina se carga igual y no se propaga la excepción a la carga.

  - **`test_load_skips_duplicate_app_keeps_registered`** (L323)
    - Una entidad cuyo nombre normaliza a una app ya registrada
(p. ej. 'Google Chrome' -> 'chrome') se omite sin sobreescribir la app
registrada: la duplicada no entra y la app existente se conserva.

  - **`test_load_skips_entity_with_empty_name`** (L370)
    - Una entidad `application` con nombre usable vacío (name/id vacíos)
produce `_reconstruct_application -> None` y se omite; no se materializa
como aplicación y no lanza.

  - **`test_load_non_list_entities_returns_none_without_crash`** (L394)
    - Si `get_entities_by_type` devuelve un tipo no lista,
`_load_custom_applications` retorna early (None) sin lanzar y sin
tocar las apps registradas.

  - **`test_load_non_dict_properties_degrades_gracefully`** (L407)
    - Una entity con `properties` de tipo no dict (dato incorrecto) no
lanza; `_reconstruct_application` normaliza properties a `{}` y la app
se materializa con valores por defecto, sin afectar a una entity válida
vecina.

---

<a name="hands/test-application_mandatory_data"></a>
### `hands\test_application_mandatory_data.py`

**Descripción:** Tests del contrato minimo 3.1.2.2 — datos obligatorios para registrar una aplicacion.

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`TestNameIsMandatory`** (línea 38) — 2 método(s) de test
  - `name` es el primer campo requerido del dataclass ApplicationKnowledge.

  - **`test_name_missing_raises_type_error`** (L41)
    - Construir ApplicationKnowledge sin `name` lanza TypeError (dataclass).

  - **`test_name_only_is_not_enough`** (L46)
    - Ni siquiera pasando type como kwarg: falta name completamente.

- **`TestTypeIsMandatory`** (línea 53) — 2 método(s) de test
  - `type` es el segundo campo requerido del dataclass ApplicationKnowledge.

  - **`test_type_missing_raises_type_error`** (L56)
    - Construir ApplicationKnowledge sin `type` lanza TypeError (dataclass).

  - **`test_type_only_is_not_enough`** (L61)
    - Ni siquiera pasando name como kwarg: falta type completamente.

- **`TestMinimalConstruction`** (línea 68) — 2 método(s) de test
  - Construir ApplicationKnowledge con SOLO los datos obligatorios funciona.

  - **`test_construct_with_only_name_and_type`** (L71)
    - name + type son suficientes: no se requiere ningun otro campo.

  - **`test_minimal_construction_all_optionals_defaulted`** (L78)
    - Verifica el valor por defecto de CADA campo opcional.

- **`TestRegisterApplicationWithMinimalData`** (línea 102) — 3 método(s) de test
  - register_application acepta un ApplicationKnowledge con solo name+type.

  - **`test_register_minimal_app_succeeds`** (L117)
    - register_application con solo name+type retorna True.

  - **`test_register_minimal_app_entity_has_defaults`** (L124)
    - La Entity persistida refleja los defaults de register_application.

  - **`test_register_minimal_app_case_insensitive_key`** (L150)
    - La clave del dict usa name.lower() (coherente con 3.1.2.1).

  Métodos auxiliares (no test): _make_minimal_manager

- **`TestRegisterCustomApplicationMandatoryData`** (línea 158) — 7 método(s) de test
  - register_custom_application valida name+type en el dict de config.

  - **`test_minimal_config_accepted`** (L161)
    - Un config con SOLO name y type es aceptado y registrado.

  - **`test_minimal_config_registered_in_manager`** (L166)
    - La aplicacion registrada con config minima aparece en el gestor.

  - **`test_missing_name_rejected`** (L174)
    - Falta name -> retorna False (ValueError interno).

  - **`test_missing_type_rejected`** (L179)
    - Falta type -> retorna False (ValueError interno).

  - **`test_empty_config_rejected`** (L184)
    - Config vacio -> retorna False por falta de name y type.

  - **`test_none_config_rejected`** (L189)
    - None -> retorna False.

  - **`test_config_extra_fields_still_requires_name_type`** (L194)
    - Incluso con campos extra, name y type siguen siendo obligatorios.

- **`_FakeMemoryManager`** (línea 110) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity

- **`_FakeMM`** (línea 129) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity

---

<a name="hands/test-application_minimal_contract"></a>
### `hands\test_application_minimal_contract.py`

**Descripción:** Tests del contrato minimo consolidado — unidad 3.1.3.3 (FASE 3.1.3 — Compatibilidad).

**Módulos de origen probados:** src.brain.llm, src.hands.applications_core

**Clases de test:**

- **`TestMinimalContractSpec`** (línea 116) — 6 método(s) de test
  - Spec autoritativo del contrato minimo: campos obligatorios, orden, defaults.

  - **`test_exactly_two_mandatory_fields_without_default`** (L119)
    - Solo `name` y `type` carecen de default; el resto es opcional.

  - **`test_field_count`** (L130)
    - ApplicationKnowledge define exactamente 13 campos (2 obligatorios + 11 opcionales).

  - **`test_field_order_is_name_then_type`** (L134)
    - name precede a type como primeros campos (contrato minimo).

  - **`test_all_optional_fields_default_to_expected_values`** (L140)
    - Construir con name+type deja CUALQUIER campo opcional en su valor por defecto.

  - **`test_none_passed_explicitly_yields_same_defaults`** (L159)
    - Pasar explicitamente None a los campos de coleccion produce el mismo
default que no pasarlos (el __post_init__ normaliza None -> coleccion nueva).

  - **`test_states_default_is_closed_not_shared_singleton`** (L174)
    - El default de states es [CLOSED] pero NO un singleton global: dos apps
pueden mutar su `states` independientemente (aislamento mutable, 3.1.3.3).

- **`TestMutableDefaultIsolation`** (línea 189) — 4 método(s) de test
  - GAP 3.1.3.3: dos ApplicationKnowledge minimas no comparten objetos de
coleccion. Evita el clasico bug 'mutable default shared across instances'.

  - **`test_collection_objects_are_distinct_instances`** (L194)
    - getattr(a, attr) is not getattr(b, attr) para toda coleccion.

  - **`test_mutation_does_not_leak_between_instances`** (L201)
    - Mutar la coleccion de una instancia no altera la de otra.

Este es el test regresivo del bug de defaults mutables: si __post_init__
usara un objeto compartido/singleton, este test fallaria. La invariante
verificada es: B conserva su valor ORIGINAL pese a mutar A (no necesariamente
vacio, pues `states` defaultea a [CLOSED]).

  - **`test_states_single_element_is_new_list_each_time`** (L231)
    - states se inicializa a una NUEVA lista [CLOSED] por instancia, no a una
lista compartida entre defaults del dataclass.

  - **`test_metadata_deep_isolation`** (L239)
    - metadata es un dict privado: mutarlo (incluso anidado) en una instancia
no afecta a otra.

- **`TestModelInvariantsMinimalApp`** (línea 256) — 5 método(s) de test
  - El modelo ApplicationKnowledge responde coherente con una app minimal
(sin capabilities declaradas, sin ui_elements).

  - **`test_get_capability_returns_none`** (L260)
    - get_capability devuelve None cuando no hay capabilities declaradas.

  - **`test_is_capable_false_with_no_capabilities`** (L266)
    - is_capable devuelve False para una app minimal (cualquier capability).

  - **`test_is_capable_true_when_capability_present`** (L272)
    - is_capable devuelve True cuando la capability esta declarada.

Verifica que el contrato minimo no quiebra el metodo: una app que declara
OPEN es capaz de OPEN y no de CLOSE.

  - **`test_get_ui_element_returns_none`** (L293)
    - get_ui_element devuelve None cuando no hay ui_elements.

  - **`test_get_calibrated_elements_empty`** (L298)
    - get_calibrated_elements devuelve [] para una app sin ui_elements.

- **`TestMinimalAppEndToEndIsolatedManager`** (línea 308) — 6 método(s) de test
  - register -> retrieve -> verificacion del contrato minimo usando un manager
aislado (no persiste, no inicializa Chrome/Spotify).

  - **`test_register_minimal_app`** (L312)
    - register_application con solo name+type retorna True y la registra.

  - **`test_register_minimal_app_case_insensitive_key`** (L319)
    - La clave usa name.lower() (coherente con 3.1.2.1).

  - **`test_retrieve_minimal_app_preserves_contract`** (L325)
    - Recuperar la app registrada conserva name, type y todos los defaults.

  - **`test_get_application_capabilities_minimal_empty`** (L337)
    - get_application_capabilities devuelve {} para una app sin capabilities.

  - **`test_get_application_ui_elements_minimal_empty`** (L343)
    - get_application_ui_elements devuelve {} para una app sin ui_elements.

  - **`test_get_applications_by_capability_minimal_empty`** (L349)
    - get_applications_by_capability devuelve [] para una app minimal (sin caps).

- **`TestMinimalAppSingletonInMemInjection`** (línea 360) — 2 método(s) de test
  - Verifica que el singleton real reconoce una app minimal inyectada
directamente en `applications` (sin pasar por register_application, por lo
que no se persiste a entities.json). Se salva/restaura el dict del singleton.

  - **`test_minimal_app_recognized_by_real_singleton`** (L365)
    - get_application resuelve una app minimal inyectada en el singleton.

  - **`test_brain_query_sees_minimal_app_in_singleton`** (L381)
    - Brain._get_application_knowledge expone la app minimal inyectada con
capabilities={} y available=False (consistente con 3.1.3.2).

- **`TestUIElementMinimalContract`** (línea 405) — 5 método(s) de test
  - UIElement es el segundo bloque del contrato minimo: name y type son
obligatorios; description/coordinates/screen/calibration_data/
required_capability son opcionales.

  - **`test_minimal_construction`** (L410)
    - UIElement(name, type) construye instancia con name y type.

  - **`test_optional_fields_default`** (L416)
    - Los campos opcionales de UIElement toman sus defaults al construir minimal.

  - **`test_is_calibrated_false_when_no_coordinates`** (L425)
    - is_calibrated() devuelve False con coordinates por defecto (None).

  - **`test_is_calibrated_false_with_empty_coordinates`** (L429)
    - is_calibrated() devuelve False con coordinates={}.

  - **`test_is_calibrated_true_with_xy_pair`** (L434)
    - is_calibrated() devuelve True con el formato claseico {x, y}.

- **`_FakeMemoryManager`** (línea 92) — 0 método(s) de test

  Métodos auxiliares (no test): save_entity

---

<a name="hands/test-application_name_resolution"></a>
### `hands\test_application_name_resolution.py`

**Descripción:** Tests de resolución de nombres de aplicación (FASE 3.8, unidad 3.8.2.2).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestApplicationResolutionResult`** (línea 71) — 1 método(s) de test

  - **`test_estructura_dataclass`** (L72)

- **`TestResolveApplication`** (línea 80) — 11 método(s) de test

  - **`test_resuelve_nombre_normalizado_exacto_chrome`** (L84)

  - **`test_resuelve_nombre_normalizado_exacto_spotify`** (L93)

  - **`test_resuelve_alias_estatico_google_chrome`** (L100)

  - **`test_resuelve_alias_dinámico_registrado`** (L107)

  - **`test_resuelve_nombre_imperfecto_typo`** (L115)
    - 'spotifiy' es una variante imperfecta de 'Spotify' (difuso sobre nombre).

  - **`test_resuelve_nombre_imperfecto_por_alias`** (L123)

  - **`test_nombre_desconocido_devuelve_none`** (L131)

  - **`test_cadena_vacia_devuelve_none`** (L140)

  - **`test_espacios_en_blanco_devuelve_none`** (L146)

  - **`test_alternativas_ordenadas_y_ganador_max_similitud`** (L166)

  - **`test_no_devuelve_alternativas_cuando_resolucion_exacta`** (L188)

  Métodos auxiliares (no test): setup_method, _mejores_ratios

- **`TestCompatibilidadGetApplication`** (línea 193) — 1 método(s) de test

  - **`test_get_application_sigue_resolviendo_exactos`** (L194)

---

<a name="hands/test-application_optional_data"></a>
### `hands\test_application_optional_data.py`

**Descripción:** Tests del contrato minimo 3.1.2.3 — datos opcionales para registrar una aplicacion.

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`TestApplicationKnowledgeOptionalDefaults`** (línea 83) — 7 método(s) de test
  - Verifica el valor por defecto de CADA campo opcional de ApplicationKnowledge.

  - **`test_minimal_construction_all_optionals_defaulted`** (L86)
    - Construir con solo name+type: todos los campos opcionales toman su default.

  - **`test_optional_fields_with_explicit_none`** (L109)
    - Pasar explicitamente None a los campos opcionales produce el mismo default.

  - **`test_optional_fields_with_explicit_values`** (L128)
    - Los campos opcionales aceptan valores reales sin perder defaults de los demas.

  - **`test_dataclass_field_order`** (L168)
    - Verifica el orden canonico de campos: name, type obligatorios primero.

  - **`test_optional_field_count`** (L181)
    - ApplicationKnowledge tiene exactamente 13 campos: 2 obligatorios + 11 opcionales.

  - **`test_register_application_persists_optional_defaults`** (L207)
    - register_application persiste los defaults correctos para campos opcionales.

  - **`test_register_application_persists_optional_provided`** (L238)
    - register_application persiste valores opcionales cuando se proveen.

  Métodos auxiliares (no test): _make_minimal_manager

- **`TestUIElementOptionalDefaults`** (línea 271) — 7 método(s) de test
  - Verifica el valor por defecto de CADA campo opcional de UIElement.

  - **`test_minimal_construction_all_optionals_defaulted`** (L274)
    - UIElement con solo name+type: los campos opcionales toman su default.

  - **`test_optional_fields_with_explicit_none`** (L284)
    - Pasar explicitamente None produce el mismo default.

  - **`test_optional_fields_with_explicit_values`** (L299)
    - Los campos opcionales aceptan valores reales.

  - **`test_field_count`** (L315)
    - UIElement tiene exactamente 7 campos: 2 obligatorios + 5 opcionales.

  - **`test_is_calibrated_defaults_false`** (L322)
    - Un UIElement con defaults es NOT calibrated (coordinates is None).

  - **`test_is_calibrated_with_coordinates`** (L327)
    - Un UIElement con coordenadas {x,y} validas es calibrated.

  - **`test_is_calibrated_false_with_empty_coordinates`** (L335)
    - Un UIElement con coordinates={} no esta calibrado.

- **`TestApplicationCapabilityDefOptionalDefaults`** (línea 348) — 4 método(s) de test
  - Verifica el valor por defecto de los campos opcionales de ApplicationCapabilityDef.

  - **`test_minimal_construction`** (L351)
    - Construir con los 7 campos obligatorios: los 3 opcionales toman default.

  - **`test_alternatives_explicit_none`** (L366)
    - alternatives=None normalizado a [] por __post_init__.

  - **`test_alternatives_provided`** (L380)
    - alternatives con valores reales se conservan.

  - **`test_field_count`** (L398)
    - ApplicationCapabilityDef tiene 10 campos: 7 obligatorios + 3 opcionales.

- **`TestRegisterCustomApplicationOptionalData`** (línea 412) — 5 método(s) de test
  - Verifica que register_custom_application acepta datos opcionales en el dict.

  - **`test_minimal_dict_accepted`** (L415)
    - Un dict con SOLO name y type es aceptado.

  - **`test_dict_with_optional_fields_accepted`** (L420)
    - Un dict con todos los campos opcionales es aceptado.

  - **`test_optional_capabilities_accepted`** (L448)
    - register_custom_application reconstruye ApplicationCapabilityDef desde dict.

  - **`test_optional_ui_elements_accepted`** (L477)
    - register_custom_application reconstruye UIElement desde dict.

  - **`test_optional_states_accepted`** (L496)
    - register_custom_application reconstruye ApplicationState desde strings.

- **`_FakeMemoryManager`** (línea 194) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-application_preflight"></a>
### `hands\test_application_preflight.py`

**Descripción:** Tests de ApplicationPreflight (src/hands/application_preflight.py).

**Módulos de origen probados:** src.hands.application_preflight

**Clases de test:**

- **`TestPreflightResult`** (línea 18) — 4 método(s) de test

  - **`test_create_full`** (L19)

  - **`test_create_defaults`** (L36)

  - **`test_to_dict_keys`** (L44)

  - **`test_frozen_dataclass`** (L54)

- **`TestApplicationPreflightInit`** (línea 60) — 2 método(s) de test

  - **`test_default_init`** (L61)

  - **`test_get_application_preflight_singleton`** (L66)

- **`TestNameBlocking`** (línea 72) — 9 método(s) de test

  - **`test_name_blocked_verifier`** (L76)

  - **`test_name_blocked_admin`** (L79)

  - **`test_name_blocked_registry`** (L82)

  - **`test_name_blocked_services`** (L85)

  - **`test_name_not_blocked_normal`** (L88)

  - **`test_name_blocked_empty`** (L91)

  - **`test_app_id_blocked`** (L94)

  - **`test_app_id_blocked_registry`** (L97)

  - **`test_app_id_not_blocked_normal`** (L100)

  Métodos auxiliares (no test): setup_method

- **`TestNormalize`** (línea 104) — 4 método(s) de test

  - **`test_normalize`** (L105)

  - **`test_normalize_special_chars`** (L112)

  - **`test_normalized_values`** (L116)

  - **`test_normalize_unicode`** (L122)

- **`TestOptionalBool`** (línea 128) — 3 método(s) de test

  - **`test_true_values`** (L129)

  - **`test_false_values`** (L137)

  - **`test_none_values`** (L145)

- **`TestResolveResourcesStatus`** (línea 152) — 6 método(s) de test

  - **`test_resources_available_bool`** (L156)

  - **`test_resources_not_available_bool`** (L160)

  - **`test_resources_dict_all_true`** (L164)

  - **`test_resources_dict_mixed`** (L170)

  - **`test_resources_none`** (L176)

  - **`test_resources_empty_dict`** (L180)

  Métodos auxiliares (no test): setup_method

- **`TestCheck`** (línea 185) — 15 método(s) de test

  - **`test_check_invalid_application_not_dict`** (L189)

  - **`test_check_empty_name`** (L194)

  - **`test_check_blocked_name`** (L199)

  - **`test_check_blocked_app_id`** (L204)

  - **`test_check_login_required_not_logged`** (L209)

  - **`test_check_login_required_unknown_state`** (L214)

  - **`test_check_resources_not_available`** (L219)

  - **`test_check_normal_app_passes_preflight`** (L224)

  - **`test_check_unresolved_executable_without_url_is_rejected`** (L236)

  - **`test_check_unresolved_executable_with_valid_uri_is_allowed`** (L245)

  - **`test_check_unresolved_executable_with_invalid_uri_is_rejected`** (L253)

  - **`test_check_ambiguous_resolution_is_rejected`** (L261)

  - **`test_check_resolved_executable_that_is_directory_is_rejected`** (L269)

  - **`test_check_resolved_executable_nonexistent_path_is_rejected`** (L278)

  - **`test_check_returns_dict`** (L286)

  Métodos auxiliares (no test): setup_method

- **`TestCheckApplication`** (línea 294) — 3 método(s) de test

  - **`test_check_application_returns_preflight_result`** (L298)

  - **`test_check_application_unresolved_executable_is_blocked`** (L311)

  - **`test_check_application_typed_blocked`** (L320)

  Métodos auxiliares (no test): setup_method

- **`TestIsSafeToCalibrate`** (línea 327) — 3 método(s) de test

  - **`test_safe_app`** (L331)

  - **`test_unsafe_blocked_name`** (L342)

  - **`test_unsafe_login_required`** (L345)

  Métodos auxiliares (no test): setup_method

- **`TestCheckLoginState`** (línea 351) — 5 método(s) de test

  - **`test_authenticated`** (L355)

  - **`test_not_authenticated`** (L360)

  - **`test_unknown_login`** (L365)

  - **`test_not_required`** (L370)

  - **`test_unknown_no_login_info`** (L375)

  Métodos auxiliares (no test): setup_method

- **`TestCheckResources`** (línea 380) — 3 método(s) de test

  - **`test_resources_available`** (L384)

  - **`test_resources_unavailable`** (L389)

  - **`test_resources_unknown`** (L394)

  Métodos auxiliares (no test): setup_method

- **`TestClearCache`** (línea 400) — 1 método(s) de test

  - **`test_clear_cache`** (L401)

- **`TestInspectExecutableManifest`** (línea 410) — 4 método(s) de test

  - **`test_inspect_not_found`** (L414)

  - **`test_parse_manifest_xml_valid`** (L418)

  - **`test_parse_manifest_xml_invalid`** (L434)

  - **`test_parse_manifest_xml_empty`** (L438)

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-application_preflight_availability"></a>
### `hands\test_application_preflight_availability.py`

**Descripción:** Tests for ApplicationPreflight availability verification (3.5.2.1).

**Módulos de origen probados:** src.hands.application_preflight

**Clases de test:**

- **`TestApplicationPreflightAvailability`** (línea 12) — 3 método(s) de test

  - **`test_available_app`** (L16)
    - An app with a resolvable executable and no blocking factors is allowed.

  - **`test_blocked_name`** (L39)
    - An app with a blocked name should not be allowed.

  - **`test_login_required_not_logged_in`** (L53)
    - App requiring login and not logged in should be blocked.

  Métodos auxiliares (no test): setUp

---

<a name="hands/test-application_preflight_launch_destination"></a>
### `hands\test_application_preflight_launch_destination.py`

**Descripción:** Tests de ApplicationPreflight.validate_launch_destination.

**Módulos de origen probados:** src.hands.application_preflight

**Clases de test:**

- **`TestValidateLaunchDestination`** (línea 17) — 11 método(s) de test

  - **`test_existing_exe_is_valid_executable`** (L21)

  - **`test_existing_lnk_is_valid_shortcut`** (L33)

  - **`test_admitted_uri_is_valid`** (L45)

  - **`test_unknown_uri_scheme_is_invalid`** (L52)

  - **`test_nonexistent_exe_is_invalid`** (L58)

  - **`test_existing_txt_file_is_invalid`** (L64)

  - **`test_existing_directory_is_invalid`** (L75)

  - **`test_empty_string_is_invalid`** (L82)

  - **`test_none_is_invalid`** (L87)

  - **`test_whitespace_only_is_invalid`** (L92)

  - **`test_relative_exe_path_is_normalized_and_valid`** (L97)

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-application_preflight_resolve_executable"></a>
### `hands\test_application_preflight_resolve_executable.py`

**Descripción:** Tests de ApplicationPreflight.resolve_executable y sus estrategias reales.

**Módulos de origen probados:** src.hands.application_preflight

**Clases de test:**

- **`TestIsExecutable`** (línea 17) — 4 método(s) de test

  - **`test_existing_exe_returns_true`** (L18)

  - **`test_nonexistent_exe_returns_false`** (L26)

  - **`test_existing_non_exe_returns_false`** (L29)

  - **`test_empty_path_returns_false`** (L37)

- **`TestResolveFromTargetString`** (línea 42) — 4 método(s) de test

  - **`test_valid_target_returns_path`** (L43)

  - **`test_nonexistent_target_returns_none`** (L61)

  - **`test_non_exe_target_returns_none`** (L69)

  - **`test_empty_target_returns_none`** (L77)

  Métodos auxiliares (no test): target_with_quotes_is_stripped

- **`TestResolveExecutable`** (línea 82) — 7 método(s) de test

  - **`test_uses_cache_on_repeated_call`** (L87)

  - **`test_casefold_cache_key`** (L103)

  - **`test_resolve_from_apps_folder_none_returns_none`** (L116)

  - **`test_resolved_path_is_abspath`** (L122)

  - **`test_resolved_path_not_a_file_returns_none`** (L135)

  - **`test_resolve_from_apps_folder_exception_returns_none`** (L141)

  - **`test_clear_cache_removes_executable_entry`** (L147)

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-application_read"></a>
### `hands\test_application_read.py`

**Descripción:** Tests de implementacion de la lectura de aplicaciones desde entidades
— unidad 3.2.2.1 (FASE 3.2.2 — Carga).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestReconstructApplication`** (línea 135) — 17 método(s) de test
  - Verifica _reconstruct_application(entity) con ambos formatos de properties.

  - **`test_reconstruct_from_register_application_format`** (L140)
    - Entity con properties.type + capabilities se reconstruye con type y capabilities.

  - **`test_reconstruct_capabilities_from_register_format`** (L156)
    - Las capabilities como List[str] se convierten a ApplicationCapabilityDef.

  - **`test_reconstruct_login_required_true`** (L178)
    - login_required=True se propaga correctamente.

  - **`test_reconstruct_from_legacy_entity_format`** (L188)
    - Entity con properties.category (sin type) se reconstruye usando category como type.

  - **`test_reconstruct_legacy_no_capabilities_empty_list`** (L199)
    - Entity legacy sin capabilities → capabilities lista vacia.

  - **`test_reconstruct_type_from_properties_type`** (L209)
    - Cuando properties.type existe, se usa como app.type.

  - **`test_reconstruct_type_fallback_to_category`** (L216)
    - Si no hay properties.type, se usa properties.category.

  - **`test_reconstruct_type_defaults_to_application`** (L223)
    - Sin type ni category, type defaults a 'application'.

  - **`test_reconstruct_with_none_properties`** (L239)
    - Entity con properties=None no lanza error; type defaults a 'application'.

  - **`test_reconstruct_with_non_dict_properties`** (L256)
    - Entity con properties como lista (no dict) no lanza error.

  - **`test_reconstruct_invalid_capabilities_skipped`** (L274)
    - Capability strings invalidas se omiten sin lanzar error.

  - **`test_reconstruct_capabilities_case_insensitive`** (L287)
    - Capability strings con mayusculas se normalizan.

  - **`test_reconstruct_missing_name_uses_id`** (L297)
    - Si entity.name es None, se usa entity.id como nombre.

  - **`test_reconstruct_missing_name_and_id_returns_none`** (L311)
    - Si tanto name como id son None/falsy, reconstruction falla → None.

  - **`test_reconstruct_stores_entity_id_in_metadata`** (L326)
    - entity.id se guarda en metadata para trazabilidad.

  - **`test_reconstruct_stores_aliases_in_metadata`** (L335)
    - entity.aliases se guardan en metadata para normalizacion futura.

  - **`test_reconstructed_app_has_valid_contract`** (L346)
    - La ApplicationKnowledge reconstruida satisface el contrato minimo (name+type).

- **`TestLoadCustomApplications`** (línea 365) — 11 método(s) de test
  - Verifica _load_custom_applications() con entities aisladas en tmp_path.

  - **`test_loads_new_applications_from_entities`** (L383)
    - Entities nuevas (no duplicadas) se cargan en self.applications.

  - **`test_loads_multiple_new_applications`** (L393)
    - Multiples entities nuevas se cargan todas.

  - **`test_skips_duplicate_applications`** (L406)
    - Entities que ya estan registradas (Chrome, Spotify) se omiten.

  - **`test_skips_duplicates_but_loads_new`** (L418)
    - Mezcla de duplicados y nuevas: solo las nuevas se cargan.

  - **`test_empty_entities_no_effect`** (L429)
    - Sin entities, no se anaden apps.

  - **`test_returns_none`** (L437)
    - _load_custom_applications devuelve None (void).

  - **`test_no_crash_on_reconstruction_failure`** (L442)
    - Entities que fallan en reconstruction no hacen crash; se omiten.

  - **`test_mixed_formats_loaded`** (L458)
    - Entities con formato register_application y legacy se cargan ambos.

  - **`test_non_list_entities_handled`** (L470)
    - Si get_entities_by_type devuelve algo que no es lista, no hace nada.

  - **`test_capabilities_from_loaded_entity`** (L477)
    - Capabilities registradas en la entity se reconstruyen en ApplicationKnowledge.

  - **`test_repeated_call_no_duplicate`** (L491)
    - Llamar _load_custom_applications dos veces no duplica apps.

  Métodos auxiliares (no test): manager_with_entities

- **`_FakeMemoryManager`** (línea 55) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, set_entities, get_entities_by_type, save_entity

---

<a name="hands/test-application_register_duplicates"></a>
### `hands\test_application_register_duplicates.py`

**Descripción:** Tests de evasion de duplicados en register_application — unidad 3.2.2.3.

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestRegisterApplicationDuplicateAvoidance`** (línea 71) — 6 método(s) de test
  - register_application evita duplicados al registrar.

  - **`test_second_registration_returns_false`** (L74)
    - Registrar la misma app dos veces: segunda vez devuelve False.

  - **`test_duplicate_does_not_call_save_entity`** (L81)
    - La segunda llamada no invoca save_entity (evita escritura duplicada).

  - **`test_duplicate_does_not_overwrite_existing_app`** (L90)
    - La app registrada original no se sobreescribe con una instancia distinta.

  - **`test_duplicate_save_entity_called_exactly_once`** (L102)
    - save_entity se llama exactamente una vez tras dos registros del mismo app.

  - **`test_duplicate_entity_stored_once`** (L110)
    - Solo se almacena una entidad para la app duplicada.

  - **`test_duplicate_id_preserved`** (L118)
    - La entidad almacenada conserva el id derivado del nombre.

- **`TestRegisterApplicationDuplicateDetection`** (línea 131) — 4 método(s) de test
  - La detección de duplicados usa app.name.lower() como clave.

  - **`test_case_insensitive_duplicate`** (L134)
    - Mismo nombre con diferente capitalización se detecta como duplicado.

  - **`test_different_apps_not_duplicates`** (L144)
    - Aplicaciones distintas no se detectan como duplicados.

  - **`test_spaces_and_case_variants`** (L155)
    - Nombre con espacios/extra se normaliza: solo el nombre lower importa.

  - **`test_app_with_ui_elements_not_duplicated`** (L163)
    - App con ui_elements/states: el duplicado se detecta igualmente.

- **`TestRegisterDuplicateConsistencyWithLoad`** (línea 181) — 2 método(s) de test
  - register_application y _load_custom_applications usan la misma clave.

  - **`test_load_skips_same_key_as_register`** (L184)
    - Una app registrada no se vuelve a registrar al cargar desde entidades.

  - **`test_load_registers_different_app`** (L233)
    - Una app distinta NO registrada se carga normalmente.

- **`TestRegisterApplicationNotBlocked`** (línea 284) — 2 método(s) de test
  - Verifica que la prevención de duplicados no bloquea registros nuevos.

  - **`test_register_new_app_still_true`** (L287)

  - **`test_register_after_duplicate_re_registers_different_app`** (L295)
    - Después de un duplicado rechazado, una app nueva se registra OK.

- **`_CountingMemoryManager`** (línea 43) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

- **`_EntityBackedMemoryManager`** (línea 196) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

- **`_EntityBackedMemoryManager`** (línea 242) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-application_register_in_memory"></a>
### `hands\test_application_register_in_memory.py`

**Descripción:** Tests de verificación del REGISTRO en memoria con MemoryManager REAL —
unidad 3.2.4.1 (FASE 3.2.4 — CIERRE, bajo 3.2 CARGA Y REGISTRO).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestRealInMemoryRegistration`** (línea 131) — 6 método(s) de test
  - register_application con MemoryManager REAL: la app queda registrada en
memoria (manager.applications) y expuesta vía get_application.

  - **`test_register_app_added_to_manager_applications`** (L135)
    - La app registrada se inserta en manager.applications bajo la clave
normalizada del nombre.

  - **`test_register_app_retrievable_by_get_application`** (L148)
    - get_application resuelve la app registrada (name y clave normalizada).

  - **`test_register_entity_in_real_cache`** (L159)
    - La Entity registrada queda en la CACHE en memoria del MemoryManager
real (get_entity / get_entities_by_type). Registro único: el entity
persiste en caché.

  - **`test_register_entity_id_type_and_name`** (L174)
    - La Entity cacheada tiene id `app_{name.lower()}`, type
`application` y name preservado.

  - **`test_register_entity_properties_structure`** (L186)
    - properties contiene exactamente las 7 claves documentadas y
refleja los valores del ApplicationKnowledge origen.

  - **`test_register_entity_aliases_empty`** (L204)
    - register_application siempre persiste aliases == [] en la Entity.

- **`TestRegisterDuplicateWithRealMemoryManager`** (línea 217) — 4 método(s) de test
  - register_application evita duplicados contra un MM real (no mockeado).

  - **`test_second_registration_returns_false`** (L220)
    - Registrar la misma app dos veces: segunda vez devuelve False.

  - **`test_duplicate_does_not_duplicate_cache`** (L229)
    - Tras dos registros del mismo app, la caché del MM real contiene una
sola entidad con el id esperado (no se duplica).

  - **`test_duplicate_preserves_original_app`** (L242)
    - La app registrada original no se sobreescribe con otra instancia del
mismo nombre.

  - **`test_duplicate_does_not_overwrite_entity_in_cache`** (L256)
    - La entidad en caché conserva los datos del registro original.

- **`TestRegisterMultipleDistinctApps`** (línea 275) — 1 método(s) de test
  - El registro real en memoria a nivel `manager.applications` retiene apps
distintas coexistentes.

  - **`test_multiple_distinct_apps_in_manager_applications`** (L279)
    - Dos apps distintas se registran simultáneamente en
manager.applications (registro real en memoria a nivel gestor).

- **`TestRegisterPersistenceGap`** (línea 301) — 3 método(s) de test
  - Documenta (sin afirmar como contrato) el comportamiento real tras
register_application sobre la persistencia en disco.

VERDAD AVERIGUADA (no contrato): tras registrar una app sobre una tienda en
`tmp_path` nueva, `entities.json` se escribe como JSON válido (lista),
reparando cualquier contenido previo; sin embargo la entidad registrada NO
se incluye en el fichero en disco (D-ENTITIES-PERSIST-BUG). Por tanto, un
gestor construido de nuevo sobre el mismo `tmp_path` no recupera la app.

Estos tests afirman hechos VERDADEROS y estables: el fichero es una lista
JSON válida. No afirman ni que la entidad esté en disco (es mentira) ni que
la recuperación funcione (es mentira); ese comportamiento roto se documenta
en docstrings y en el registro de la unidad 3.2.4.1.

  - **`test_register_repairs_file_to_valid_json`** (L317)
    - Tras register_application, entities.json es una lista JSON válida.

  - **`test_register_does_not_crash_with_existing_file`** (L327)
    - register_application repara un fichero existente (no lanza).

  - **`test_register_in_memory_persists_within_session`** (L339)
    - La app registrada queda en memoria del gestor ORIGINAL (registro real
en memoria) y es recuperable tanto por `get_application` como por la
entidad cacheada en el MemoryManager real.

La persistencia entre SESIONES (recuperación en un gestor nuevo sobre el
mismo `tmp_path`) NO se verifica como contrato: está fuera de esta hoja
("registro REAL en MEMORIA") y está cubierta por D-ENTITIES-PERSIST-BUG
(ver registro de unidad 3.2.4.1). Este test afirma hechos verdaderos sobre
la sesión activa.

---

<a name="hands/test-application_resolution_ambiguity"></a>
### `hands\test_application_resolution_ambiguity.py`

**Descripción:** Tests de detección de coincidencias ambiguas (FASE 3.8, unidad 3.8.2.4).

**Módulos de origen probados:** src.hands.applications_core, src.memory.storage

**Clases de test:**

- **`TestResolveApplicationAmbiguity`** (línea 83) — 10 método(s) de test

  - **`test_estructura_dataclass_con_campos_ambiguedad`** (L87)

  - **`test_resolucion_exacta_no_es_ambigua`** (L94)

  - **`test_alias_dinamico_no_es_ambiguo`** (L103)

  - **`test_difusa_con_ganador_claro_no_es_ambigua`** (L113)
    - 'spotifiy' gana claramente sobre el resto: no es ambigua.

  - **`test_difusa_con_coincidencia_cercana_es_ambigua`** (L123)
    - Dos nombres muy cercanos ('... Pro' y '... Lite') generan ambigüedad.

  - **`test_nombre_desconocido_no_es_ambiguo`** (L139)

  - **`test_cadena_vacia_no_es_ambigua`** (L146)

  - **`test_calcular_evidencia_propaga_ambiguedad`** (L151)

  - **`test_calcular_evidencia_exacta_no_es_ambigua`** (L160)

  - **`test_ambiguidad_conservada_en_metadata`** (L166)

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-application_resolution_evidence"></a>
### `hands\test_application_resolution_evidence.py`

**Descripción:** Tests de evidencia/confianza de resolución de aplicación (FASE 3.8, unidad 3.8.2.3).

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`TestCalculateResolutionEvidence`** (línea 51) — 8 método(s) de test

  - **`test_evidencia_resolucion_exacta_sin_alternativas`** (L55)
    - Resolución exacta (chrome) debe dar evidence_score 1.0.

  - **`test_evidencia_resolucion_alias_estatico`** (L65)
    - Alias estático (google chrome) debe dar evidence_score 1.0.

  - **`test_evidencia_resolucion_difusa_con_alternativas`** (L73)
    - Resolución difusa con typo puntúa menor que 1.0 y tiene alternativas.

  - **`test_evidencia_sin_coincidencia`** (L84)
    - Nombre desconocido debe devolver has_match False y evidence_score 0.0.

  - **`test_evidencia_cadena_vacia`** (L94)
    - Cadena vacía no debe coincidir.

  - **`test_evidencia_conservada_en_metadata`** (L100)
    - La evidencia debe conservarse en metadata de la aplicación resuelta.

  - **`test_evidencia_difusa_conservada_en_metadata`** (L111)
    - La evidencia de resolución difusa también se conserva.

  - **`test_evidencia_alias_dinamico_conservada`** (L122)
    - La evidencia de alias dinámico se conserva.

  Métodos auxiliares (no test): setup_method

- **`TestGetStoredResolutionEvidence`** (línea 135) — 5 método(s) de test

  - **`test_recupera_evidencia_guardada`** (L139)
    - Se puede recuperar la evidencia guardada por nombre de aplicación.

  - **`test_no_hay_evidencia_si_no_se_calculo`** (L148)
    - Si no se calculó evidencia, devuelve None (app nunca resuelta).

  - **`test_nombre_desconocido_no_guarda_evidencia`** (L153)
    - Un nombre desconocido no guarda evidencia recuperable.

  - **`test_evidencia_sobreescrita_en_calculo_posterior`** (L159)
    - Un nuevo cálculo sobrescribe la evidencia previa.

  - **`test_cadena_vacia_devuelve_none`** (L170)
    - Cadena vacía no debe recuperar evidencia.

  Métodos auxiliares (no test): setup_method

- **`TestCompatibilidadResolveApplication`** (línea 176) — 1 método(s) de test

  - **`test_resolve_application_sigue_funcionando`** (L180)
    - resolve_application sigue devolviendo ApplicationResolutionResult sin cambios.

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-application_source_missing"></a>
### `hands\test_application_source_missing.py`

**Descripción:** Tests de verificacion del comportamiento cuando la fuente no existe
— unidad 3.2.1.3 (FASE 3.2.1 — Fuente de datos).

**Módulos de origen probados:** src.hands.applications_core, src.memory.conversation, src.memory.storage

**Clases de test:**

- **`TestJsonStorageLoadWhenFileMissing`** (línea 48) — 13 método(s) de test
  - JSONStorage.load() devuelve valores por defecto cuando el fichero no existe.

  - **`test_load_entities_returns_empty_list_when_missing`** (L55)

  - **`test_load_applications_returns_empty_dict_when_missing`** (L60)

  - **`test_load_conversational_returns_empty_list_when_missing`** (L65)

  - **`test_load_state_returns_empty_dict_when_missing`** (L69)

  - **`test_load_plans_returns_empty_list_when_missing`** (L73)

  - **`test_load_executions_returns_empty_list_when_missing`** (L77)

  - **`test_load_relationships_returns_empty_dict_when_missing`** (L81)

  - **`test_load_preferences_returns_empty_dict_when_missing`** (L85)

  - **`test_load_learning_stats_returns_empty_dict_when_missing`** (L89)

  - **`test_load_all_memory_types_without_exception`** (L93)
    - Cargar todos los tipos de memoria: ningun tipo lanza excepcion
cuando ningun fichero existe.

  - **`test_exists_returns_false_for_all_types_when_missing`** (L100)

  - **`test_load_does_not_create_file`** (L104)
    - La lectura (load) no crea el fichero entities.json.

  - **`test_load_returns_same_as_get_default_value`** (L109)
    - El valor devuelto coincide con _get_default_value para cada tipo.

  Métodos auxiliares (no test): empty_storage

- **`TestMemoryManagerWhenSourceMissing`** (línea 120) — 6 método(s) de test
  - MemoryManager aislado en tmp_path (sin entities.json).

  - **`test_get_entities_by_type_returns_empty_list`** (L127)

  - **`test_get_entities_by_type_any_type_returns_empty`** (L132)

  - **`test_get_entity_returns_none_when_missing`** (L136)

  - **`test_find_entities_returns_empty_when_missing`** (L140)

  - **`test_warm_cache_handles_missing_files`** (L144)
    - _warm_cache (llamado en __init__) no lanza excepcion cuando
los ficheros de datos no existen. La cache se inicializa con []

  - **`test_entities_file_not_created_on_read`** (L150)
    - La lectura de get_entities_by_type no crea entities.json.

  Métodos auxiliares (no test): isolated_mm

- **`TestApplicationManagerWhenSourceMissing`** (línea 160) — 10 método(s) de test
  - Verifica el comportamiento de ApplicationManager cuando la fuente
(entities.json) no existe, usando un MemoryManager aislado en tmp_path.

Se inyecta el MemoryManager aislado mediante patch de
`get_memory_manager` en `src.hands.applications_core`, de modo que
`ApplicationManager.__init__()` use el tmp_path en lugar del singleton.

  - **`test_init_does_not_crash`** (L181)
    - ApplicationManager.__init__() no lanza excepcion cuando la fuente
no existe (entities.json ausente).

  - **`test_chrome_and_spotify_present_after_init`** (L187)
    - Las apps hardcodeadas (Chrome, Spotify) estan presentes aunque
la fuente no exista.

  - **`test_open_capability_apps_present`** (L194)
    - get_applications_by_capability(OPEN) devuelve Chrome y Spotify
aun cuando la fuente no existe.

  - **`test_only_hardcoded_apps_in_model`** (L202)
    - Sin fuente, solo Chrome y Spotify (hardcoded en _initialize_applications)
estan en el modelo. _load_custom_applications (stub) no materializa
entidades.

  - **`test_load_custom_applications_returns_none`** (L209)
    - _load_custom_applications() (aplicaciones_core.py:510) devuelve
None y no lanza excepcion cuando las entidades no existen.

  - **`test_repeated_load_custom_applications_no_effect`** (L216)
    - Llamar _load_custom_applications() explicitamente no anade apps
al modelo y no lanza excepcion.

  - **`test_get_application_by_name_works`** (L225)
    - Las apps hardcodeadas son resolubles por nombre aun sin fuente.

  - **`test_get_application_unknown_returns_none`** (L235)
    - Una app no registrada devuelve None.

  - **`test_source_file_created_after_init`** (L240)
    - Despues de __init__(), register_application persiste entities.json
en el directorio de datos (crea el fichero). La fuente no existia
antes del init pero se crea durante el init.

  - **`test_source_file_content_after_init`** (L250)
    - Caracterizacion del contenido real del fichero tras init sin fuente.

entities.json se crea con `[]` (vacia) debido a un hallazgo preexistente
(D-ENTITIES-PERSIST-BUG): save_entity pasa dicts a _process_data_for_save
que solo procesa instancias de Entity. Este test documenta el
comportamiento actual, no asume que el bug debe corregirse aqui.

  Métodos auxiliares (no test): isolated_manager

- **`TestDomainMemoryWhenSourceMissing`** (línea 266) — 3 método(s) de test
  - DomainMemory con get_project_root apuntando a tmp_path (sin ficheros
de conocimiento). Verifica que knowledge/applications.json ausente deja
self.applications como {}.

  - **`test_applications_remains_empty_dict`** (L283)
    - knowledge/applications.json ausente: self.applications = {}.

  - **`test_entities_remains_empty_dict`** (L287)
    - knowledge/entities.json ausente: self.entities = {}.

  - **`test_capabilities_remains_empty_dict`** (L291)
    - knowledge/capabilities.json ausente: self.capabilities = {}.

  Métodos auxiliares (no test): isolated_domain_memory

---

<a name="hands/test-applications_core"></a>
### `hands\test_applications_core.py`

**Descripción:** Tests de applications_core (src/hands/applications_core.py).

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`TestApplicationCapability`** (línea 37) — 3 método(s) de test

  - **`test_values`** (L38)

  - **`test_open_from_string`** (L45)

  - **`test_open_from_string_invalid`** (L48)

- **`TestApplicationState`** (línea 53) — 2 método(s) de test

  - **`test_values`** (L54)

  - **`test_from_string`** (L60)

- **`TestUIElement`** (línea 64) — 6 método(s) de test

  - **`test_create_full`** (L65)

  - **`test_create_without_description`** (L76)

  - **`test_create_with_required_capability`** (L83)

  - **`test_coordinate_fields_exist`** (L90)
    - UIElement tiene campos de coordenadas y calibración.

  - **`test_description_preserved`** (L101)

  - **`test_coordinate_methods_exist`** (L108)
    - is_calibrated() existe en UIElement para consultar calibración.

- **`TestApplicationCapabilityDef`** (línea 114) — 2 método(s) de test

  - **`test_create`** (L115)

  - **`test_post_init_defaults`** (L132)

- **`TestApplicationKnowledge`** (línea 145) — 9 método(s) de test

  - **`test_post_init_defaults`** (L153)

  - **`test_get_capability_by_value`** (L162)

  - **`test_get_capability_by_name`** (L173)

  - **`test_get_capability_not_found`** (L183)

  - **`test_is_capable`** (L187)

  - **`test_get_calibrated_elements_none`** (L197)
    - Sin CoordinateManager disponible, no se pueden verificar elementos
calibrados. El conocimiento declarativo no almacena coordenadas.

  - **`test_get_calibrated_elements_knowledge_only`** (L203)
    - UIElement no almacena coordenadas; get_calibrated_elements delega
al CoordinateManager en tiempo de ejecución. Sin él, retorna [].

  - **`test_get_ui_element_found`** (L210)

  - **`test_get_ui_element_not_found`** (L217)

  Métodos auxiliares (no test): _make

- **`TestApplicationManagerInit`** (línea 222) — 5 método(s) de test

  - **`test_default_init`** (L223)

  - **`test_get_application_manager_singleton`** (L229)

  - **`test_chrome_has_capabilities`** (L234)

  - **`test_chrome_has_ui_elements`** (L240)

  - **`test_spotify_login_required`** (L246)

- **`TestApplicationManagerNormalize`** (línea 253) — 3 método(s) de test

  - **`test_normalize_alias`** (L254)

  - **`test_normalize_unknown`** (L259)

  - **`test_normalize_none`** (L263)

- **`TestApplicationManagerQueries`** (línea 268) — 9 método(s) de test

  - **`test_get_application_found`** (L272)

  - **`test_get_application_alias`** (L277)

  - **`test_get_application_not_found`** (L282)

  - **`test_get_applications_by_type`** (L285)

  - **`test_get_applications_by_capability`** (L290)

  - **`test_get_application_capabilities`** (L294)

  - **`test_get_application_capabilities_not_found`** (L299)

  - **`test_get_application_ui_elements`** (L303)

  - **`test_get_application_ui_elements_not_found`** (L309)

  Métodos auxiliares (no test): setup_method

- **`TestApplicationManagerRegister`** (línea 314) — 1 método(s) de test

  - **`test_register_application`** (L315)

- **`TestModuleFunctions`** (línea 323) — 18 método(s) de test

  - **`test_get_available_commands`** (L324)

  - **`test_get_application_knowledge`** (L329)

  - **`test_get_application_knowledge_not_found`** (L335)

  - **`test_get_applications_by_capability_valid`** (L339)

  - **`test_get_applications_by_capability_invalid`** (L344)

  - **`test_register_custom_application_valid`** (L348)

  - **`test_register_custom_application_missing_name`** (L358)

  - **`test_register_custom_application_missing_type`** (L362)

  - **`test_navigate_to_url_valid`** (L366)

  - **`test_navigate_to_url_empty`** (L371)

  - **`test_open_application_not_found`** (L375)

  - **`test_close_application_empty_name`** (L379)

  - **`test_wait_for_application_state_empty`** (L383)

  - **`test_wait_for_application_state_negative_timeout`** (L387)

  - **`test_calibrate_application_ui_not_found`** (L391)

  - **`test_calibrar_aplicaciones`** (L395)

  - **`test_abrir_youtube`** (L408)

  - **`test_abrir_gmail`** (L413)

- **`TestApplicationKnowledgeIsCapable`** (línea 423) — 4 método(s) de test
  - is_capable: comparación por enum, no por string.

  - **`test_capable_with_enum`** (L431)

  - **`test_not_capable_with_string`** (L441)

  - **`test_not_capable_empty_capabilities`** (L451)

  - **`test_multiple_capabilities`** (L455)

  Métodos auxiliares (no test): _make

- **`TestApplicationKnowledgeGetCapability`** (línea 474) — 5 método(s) de test
  - get_capability: búsqueda por nombre o valor.

  - **`test_by_name`** (L486)

  - **`test_by_value`** (L495)

  - **`test_case_insensitive`** (L503)

  - **`test_not_found`** (L511)

  - **`test_empty_name`** (L518)

  Métodos auxiliares (no test): _make_cap

- **`TestApplicationKnowledgeDefaults`** (línea 526) — 4 método(s) de test
  - __post_init__: valoriza defaults para None.

  - **`test_all_defaults`** (L529)

  - **`test_none_states_not_overwritten`** (L542)

  - **`test_custom_states`** (L549)

  - **`test_url_and_icon`** (L557)

- **`TestApplicationManagerQueriesExtended`** (línea 566) — 11 método(s) de test
  - Consultas del gestor con casos adicionales.

  - **`test_get_application_case_insensitive`** (L572)

  - **`test_get_application_by_alias`** (L577)

  - **`test_get_applications_by_type_browser`** (L581)

  - **`test_get_applications_by_type_unknown`** (L588)

  - **`test_get_applications_by_capability_search`** (L592)

  - **`test_get_applications_by_capability_close`** (L599)

  - **`test_get_application_capabilities_full_structure`** (L603)

  - **`test_get_application_ui_elements_full_structure`** (L617)

  - **`test_get_application_ui_elements_not_found`** (L629)

  - **`test_get_application_capabilities_not_found`** (L632)

  - **`test_get_applications_by_type_case_insensitive`** (L635)

  Métodos auxiliares (no test): setup_method

- **`TestApplicationManagerRegister`** (línea 640) — 3 método(s) de test
  - Registro de aplicaciones: casos correctos y erróneos.

  - **`test_register_minimal_app`** (L643)

  - **`test_register_app_in_manager_dict`** (L649)
    - Registration stores the app in the manager's internal dict.

  - **`test_register_with_capabilities`** (L659)

- **`TestGetApplicationKnowledgeFullStructure`** (línea 676) — 3 método(s) de test
  - get_application_knowledge: estructura declarativa completa.

  - **`test_chrome_full_structure`** (L679)

  - **`test_spotify_full_structure`** (L694)

  - **`test_not_found`** (L702)

- **`TestOpenApplication`** (línea 706) — 4 método(s) de test
  - open_application: casos felices y de error.

  - **`test_open_via_executable`** (L709)

  - **`test_open_via_url`** (L723)

  - **`test_open_not_found`** (L736)

  - **`test_open_not_available`** (L742)

- **`TestCloseApplication`** (línea 755) — 8 método(s) de test
  - close_application: cierre de aplicaciones.

  - **`test_close_empty_name`** (L758)

  - **`test_close_happy_path`** (L762)

  - **`test_close_with_exe_suffix`** (L768)

  - **`test_close_verifica_estado_posterior_proceso_terminado`** (L774)
    - close_application confirma cierre solo si tasklist ya no muestra el proceso.

  - **`test_close_verifica_estado_posterior_proceso_todavia_ejecutandose`** (L791)
    - close_application informa que no se pudo confirmar si tasklist sigue mostrando el proceso.

  - **`test_close_taskkill_usa_nombre_proceso_resuelto_desde_ejecutable`** (L812)
    - close_application resuelve el nombre del proceso desde el ejecutable
registrado y se lo pasa a taskkill (3.6.2.1 identificacion de proceso correcto).

  - **`test_close_app_no_registrada_usa_nombre_objetivo_como_proceso`** (L833)
    - Si la app no esta registrada, close_application usa el nombre indicado
como nombre de proceso (comportamiento previo conservado).

  - **`test_close_no_usa_comodin_solo_proceso_objetivo`** (L854)
    - close_application no cierra todas las aplicaciones: taskkill se invoca
con /im concreto sobre el proceso objetivo, sin comodin
(3.6.2.2 cierre sin afectar otras aplicaciones).

- **`TestWaitForApplicationStateExtended`** (línea 877) — 3 método(s) de test
  - wait_for_application_state: casos adicionales.

  - **`test_timeout_zero_active`** (L880)

  - **`test_timeout_zero_ready`** (L885)

  - **`test_timeout_zero_unknown_state`** (L889)

- **`TestNavigateToUrlError`** (línea 894) — 2 método(s) de test
  - navigate_to_url: casos de error.

  - **`test_webbrowser_raises`** (L897)

  - **`test_webbrowser_returns_false`** (L902)

- **`TestRegisterCustomApplicationFull`** (línea 908) — 2 método(s) de test
  - register_custom_application: configuración completa.

  - **`test_register_with_capabilities_and_elements`** (L911)

  - **`test_missing_name_and_type`** (L957)

- **`TestUIElementKnowledgeOnly`** (línea 962) — 7 método(s) de test
  - UIElement mantiene conocimiento declarativo con datos de calibración.

UIElement contiene conocimiento declarativo (name, type, description,
required_capability) y datos de calibración (coordinates, screen,
calibration_data, is_calibrated) para poder localizar elementos en pantalla.

  - **`test_coordinates_field_exists`** (L970)

  - **`test_screen_field_exists`** (L975)

  - **`test_calibration_data_field_exists`** (L980)

  - **`test_is_calibrated_method_exists`** (L985)

  - **`test_is_calibrated_false_by_default`** (L989)

  - **`test_is_calibrated_true_with_coordinates`** (L993)

  - **`test_required_capability_only_knowledge`** (L997)

- **`TestApplicationCapabilityDef`** (línea 1009) — 3 método(s) de test
  - ApplicationCapabilityDef: defaults y alternativas.

  - **`test_default_alternatives`** (L1012)

  - **`test_custom_alternatives`** (L1020)

  - **`test_default_timeout_and_retry`** (L1028)

- **`TestCheckApplicationAvailable`** (línea 1038) — 4 método(s) de test
  - _check_application_available: resolución de ejecutables.

  - **`test_url_only_no_executable`** (L1041)

  - **`test_executable_none_and_url_none`** (L1047)

  - **`test_known_executable`** (L1053)

  - **`test_unknown_executable`** (L1059)

- **`TestCheckApplicationLogin`** (línea 1066) — 1 método(s) de test
  - _check_application_login: siempre True por compatibilidad.

  - **`test_returns_true`** (L1069)

- **`TestCalibrateApplicationUI`** (línea 1081) — 5 método(s) de test
  - calibrate_application_ui: calibración específica de UI.

  - **`test_not_found`** (L1084)

  - **`test_no_calibration_policy`** (L1088)

  - **`test_no_valid_elements`** (L1097)
    - App con calibration_policy pero sin UI elements válidos.

  - **`test_happy_path`** (L1111)
    - Calibración exitosa con elementos válidos.

  - **`test_no_valid_elements_not_in_policy`** (L1134)
    - Elements referenced in policy but not in ui_elements → no valid elements.

- **`TestCallCalibrateAllApplications`** (línea 1147) — 3 método(s) de test
  - _call_calibrate_all_applications: compatibilidad con managers.

  - **`test_manager_without_calibrate_method`** (L1150)

  - **`test_manager_with_force_parameter`** (L1155)

  - **`test_manager_without_force_parameter`** (L1165)

- **`TestVerifyTargetMonitor`** (línea 1176) — 5 método(s) de test
  - verify_target_monitor: validacion de monitor objetivo antes de operar.

  - **`test_valid_monitor_verified_true`** (L1224)

  - **`test_invalid_monitor_number_raises_value_error`** (L1239)

  - **`test_nonexistent_monitor_returns_verified_false`** (L1249)

  - **`test_screen_manager_exception_returns_verified_false`** (L1260)

  - **`test_verify_target_monitor_is_registered_action`** (L1268)

  Métodos auxiliares (no test): _make_monitor

- **`TestMoveApplicationToMonitor`** (línea 1275) — 7 método(s) de test
  - move_application_to_monitor: movimiento seguro con verificacion.

  - **`test_safe_move_success_and_verified`** (L1330)

  - **`test_invalid_monitor_fails_without_moving`** (L1349)

  - **`test_window_not_identified_fails_safely`** (L1364)

  - **`test_move_failure_is_reported`** (L1378)

  - **`test_post_move_verification_detects_wrong_monitor`** (L1393)

  - **`test_empty_app_name_raises`** (L1409)

  - **`test_move_application_to_monitor_is_registered_action`** (L1413)

  Métodos auxiliares (no test): _make_monitor, _make_screen_manager

- **`TestMaximizeOrRestoreApplication`** (línea 1420) — 7 método(s) de test
  - maximize_or_restore_application: maximizacion/restauracion con verificacion.

  - **`test_maximize_not_maximized_success_and_verified`** (L1441)

  - **`test_restore_when_maximized_success_and_verified`** (L1457)

  - **`test_already_maximized_no_change`** (L1473)

  - **`test_already_restored_no_change`** (L1486)

  - **`test_empty_app_name_raises`** (L1499)

  - **`test_window_not_identified_fails_safely`** (L1503)

  - **`test_maximize_or_restore_application_is_registered_action`** (L1513)

  Métodos auxiliares (no test): _make_snapshot, _make_screen_manager, _make_calibration_manager

---

<a name="hands/test-calibration_manager"></a>
### `hands\test_calibration_manager.py`

**Descripción:** Tests de calibration_manager (src/hands/calibration_manager.py).

**Módulos de origen probados:** src.hands.calibration_manager

**Clases de test:**

- **`TestLaunchApplicationArguments`** (línea 15) — 4 método(s) de test
  - 3.6.3.2.1 — Verificar soporte de argumentos en launch_application.

  - **`test_launch_application_pasa_argumentos_a_popen`** (L68)
    - launch_application debe pasar los argumentos al comando via shlex.split.

  - **`test_launch_application_sin_argumentos`** (L90)
    - launch_application sin argumentos lanza solo el ejecutable.

  - **`test_launch_application_argument_vacio_no_anade_nada`** (L108)
    - launch_application con arguments vacio no anade elementos al comando.

  - **`test_launch_application_argument_con_espacios`** (L127)
    - shlex.split debe separar correctamente argumentos con espacios.

  Métodos auxiliares (no test): _make_manager, _mock_launch_flow, _stop_patchers

- **`TestLaunchApplicationEjecucionConArgumentos`** (línea 152) — 15 método(s) de test
  - 3.6.3.2.2 — Verificar ejecucion con argumentos a traves de launch_application.

  - **`test_ejecucion_con_argumentos_retorna_exito`** (L203)
    - Ejecutar launch_application con argumentos debe retornar (hwnds, True).

  - **`test_ejecucion_con_argumentos_llama_popen_con_lista`** (L222)
    - subprocess.Popen debe recibirse como lista (no string) con argumentos incluidos.

  - **`test_ejecucion_con_argumentos_popen_devnull_y_contexto`** (L241)
    - 3.6.3.2.2: Popen recibe stdout/stderr DEVNULL; el contexto marca ventana/proceso propios.

  - **`test_ejecucion_sin_ventana_retorna_falso`** (L270)
    - 3.6.3.2.2: si _wait_for_application_window no detecta ventana, el lanzamiento falla.

  - **`test_ejecucion_sin_hwnd_retorna_falso`** (L290)
    - 3.6.3.2.2: ventana detectada pero sin HWND utilizable => (before, False).

  - **`test_ejecucion_popen_lanza_excepcion_retorna_falso`** (L308)
    - 3.6.3.2.2: si Popen lanza (ejecutable no ejecutable), el fallo se captura y retorna False.

  - **`test_ejecucion_proceso_elevado_retorna_falso_y_cierra_propios`** (L325)
    - 3.6.3.2.2: proceso elevado tras lanzar => False y se cierran solo las ventanas propias.

  - **`test_ejecucion_por_metadatos_con_argumentos`** (L346)
    - 3.6.3.2.2: sin ejecutable directo, los argumentos de los metadatos llegan a Popen.

  - **`test_ejecucion_por_metadatos_sin_ruta_valida_retorna_falso`** (L370)
    - 3.6.3.2.2: metadatos sin ruta valida => no se ejecuta nada y retorna False.

  - **`test_ejecucion_por_app_id_ignora_argumentos`** (L390)
    - 3.6.3.2.2: con app_id se lanza via explorer shell:AppsFolder; arguments no se adjuntan.

  - **`test_ejecucion_reutiliza_ventana_existente_sin_popen`** (L409)
    - 3.6.3.2.2: ventana existente reutilizable => True sin ejecutar Popen (argumentos no se aplican).

  - **`test_ejecucion_app_vacia_o_sin_nombre_no_ejecuta`** (L432)
    - 3.6.3.2.2: app nula/vacia o sin nombre => (set(), False) sin Popen.

  - **`test_ejecucion_sin_ejecutable_ni_metadatos_retorna_falso`** (L444)
    - 3.6.3.2.2: nombre valido pero sin ejecutable/app_id/metadatos => False sin Popen.

  - **`test_ejecucion_permiso_denegado_retorna_falso`** (L456)
    - 3.6.3.2.2: permisos insuficientes al lanzar => PermissionError capturado => False.

  - **`test_ejecucion_app_bloqueada_o_juego_no_ejecuta`** (L472)
    - 3.6.3.2.2: aplicacion ignorada/juego => (set(), False) sin Popen ni argumentos.

  Métodos auxiliares (no test): _make_manager, _mock_launch_flow, _stop_patchers

---

<a name="hands/test-calibration_requirements"></a>
### `hands\test_calibration_requirements.py`

**Descripción:** Tests de requisitos de calibración (Unidad 3.5.4).

**Módulos de origen probados:** src.hands.applications_core, src.hands.calibrator, src.hands.planner.planner

**Clases de test:**

- **`TestApplicationWithoutCalibrationRequirement`** (línea 47) — 3 método(s) de test

  - **`test_calibrator_returns_no_requirements_when_no_elements`** (L48)

  - **`test_planner_exposes_no_requirements_without_calibrator`** (L53)

  - **`test_application_knowledge_default_policy_empty`** (L59)

- **`TestApplicationWithCalibrationRequirement`** (línea 67) — 3 método(s) de test

  - **`test_calibrator_returns_pending_element`** (L68)

  - **`test_planner_exposes_requirement_from_calibrator`** (L73)

  - **`test_application_knowledge_can_declare_policy`** (L80)

- **`TestPendingCalibrationRequirement`** (línea 90) — 4 método(s) de test

  - **`test_calibrated_element_is_not_a_requirement`** (L91)

  - **`test_unknown_status_element_is_pending`** (L98)

  - **`test_different_target_not_included`** (L104)

  - **`test_different_goal_type_not_included`** (L109)

- **`TestNoRegressionCalibrationRequirements`** (línea 119) — 2 método(s) de test

  - **`test_imports`** (L120)

  - **`test_planner_methods_exist`** (L126)

---

<a name="hands/test-calibrator"></a>
### `hands\test_calibrator.py`

*Sin clases de test definidas.*

---

<a name="hands/test-capability_absent_verification"></a>
### `hands\test_capability_absent_verification.py`

**Descripción:** Tests de verificación de capacidades ausentes.

**Módulos de origen probados:** src.hands.applications_core, src.hands.planner.application_integration, src.utils.config

**Clases de test:**

- **`TestEnumCapabilityAbsence`** (línea 135) — 7 método(s) de test
  - Capacidades declaradas en data/knowledge pero ausentes del Enum.

  - **`test_applications_json_exists`** (L138)

  - **`test_some_data_capabilities_are_absent_from_enum`** (L141)
    - El gap D-CAP-MODEL-GAP: data define capacidades que el Enum no modela.

  - **`test_some_data_capabilities_present_in_enum`** (L150)

  - **`test_absent_capability_raises_value_error`** (L155)
    - Un nombre ausente del Enum no se resuelve a ningún miembro (no se falsea).

  - **`test_reconstruct_capabilities_omits_unknown_strings`** (L161)
    - _reconstruct_capabilities descarta silenciosamente los strings ausentes
del Enum (no los mapea a miembros erróneos).

  - **`test_chrome_data_declared_absent_capabilities`** (L174)
    - Chrome declara (en data) capacidades ausentes del Enum.

  - **`test_spotify_data_declared_absent_capabilities`** (L182)

- **`TestModelAbsentCapabilities`** (línea 194) — 4 método(s) de test
  - Una ApplicationKnowledge sin capabilities declaradas: todo ausente.

  - **`test_app_with_no_capabilities_is_not_capable`** (L197)

  - **`test_app_with_partial_capabilities_lacks_others`** (L204)
    - NAVIGATE declarada → True; OPEN ausente para esta app → False.

  - **`test_absent_capability_does_not_match_get_capability`** (L213)

  - **`test_available_app_without_capabilities`** (L218)
    - App disponible pero con capabilities ausentes.

- **`TestReconstructedAppAbsentCapabilities`** (línea 230) — 6 método(s) de test
  - Las apps reconstruidas desde entities.json carecen de capabilities.

  - **`test_reconstructed_apps_have_absent_capabilities`** (L236)
    - Apps del catálogo que no declaran capabilities (reconstruidas).

  - **`test_youtube_has_no_capabilities`** (L243)

  - **`test_youtube_resolves_by_alias`** (L250)

  - **`test_reconstructed_app_capabilities_empty`** (L253)

  - **`test_hardcoded_apps_declare_capabilities`** (L257)
    - Chrome y Spotify (hardcodeados) declaran capabilities; el resto no.

  - **`test_open_query_includes_declaring_apps_excludes_absent`** (L262)
    - Invariante robusta: Chrome/Spotify aparecen en OPEN; YouTube no.

  Métodos auxiliares (no test): setup_method

- **`TestKnownAppAbsentVsUnknownApp`** (línea 275) — 3 método(s) de test
  - Una app conocida con capabilities ausentes NO se confunde con una app
desconocida.

  - **`test_known_app_with_absent_capabilities`** (L279)

  - **`test_unknown_app_returns_empty`** (L286)

  - **`test_known_absent_distinct_from_unknown`** (L289)

- **`TestInverseQueryExcludesAbsent`** (línea 304) — 4 método(s) de test
  - get_applications_by_capability devuelve solo apps que declaran la
capacidad. Las invariantes exactas se verifican sobre un manager aislado
(no sobre el singleton real, que otros tests enriquecen).

  - **`test_only_declaring_apps_returned`** (L312)

  - **`test_app_without_capability_not_listed`** (L320)

  - **`test_absent_capability_returns_empty`** (L328)

  - **`test_absent_from_enum_string_does_not_raise`** (L332)

  Métodos auxiliares (no test): setup_method

- **`TestModuleLevelAbsentCapability`** (línea 342) — 5 método(s) de test
  - Las funciones módulo-level resuelven capacidades ausentes del Enum.

  - **`test_absent_enum_capability_string_returns_empty`** (L345)

  - **`test_present_enum_capability_string_returns_apps`** (L352)

  - **`test_is_capability_available_absent_for_absent_app`** (L357)

  - **`test_unknown_app_is_not_capable_nor_available`** (L362)

  - **`test_absent_enum_string_does_not_raise`** (L366)

- **`TestIntegratorAbsentCapability`** (línea 376) — 6 método(s) de test
  - El integrador verifica capabilities ausentes de forma consistente.

  - **`test_absent_capability_not_capable_on_known_app`** (L383)

  - **`test_known_app_with_partial_capabilities`** (L390)

  - **`test_unknown_app_is_not_capable`** (L398)

  - **`test_inverse_query_excludes_absent_enum`** (L403)

  - **`test_inverse_query_returns_only_declaring_apps`** (L408)

  - **`test_real_singleton_youtube_absent`** (L415)

  Métodos auxiliares (no test): setup_method

- **`_FakeMemoryManager`** (línea 69) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-capability_availability_distinction"></a>
### `hands\test_capability_availability_distinction.py`

**Descripción:** Tests de la distinción entre capability disponible y capability declarada.

**Módulos de origen probados:** src.hands.applications_core, src.hands.planner.application_integration

**Clases de test:**

- **`TestApplicationKnowledgeIsAvailable`** (línea 106) — 6 método(s) de test
  - is_available() distingue disponible de simplemente declarada.

  - **`test_available_with_real_executable`** (L109)
    - Una app cuyo ejecutable existe en el PATH está disponible.

  - **`test_available_with_absolute_path_executable`** (L116)
    - Un aple ejecutable por ruta absoluta válida está disponible.

  - **`test_not_available_with_fake_executable`** (L123)
    - Un ejecutable inexistente en el PATH no está disponible.

  - **`test_not_available_without_executable_or_url`** (L130)
    - Sin ejecutable ni URL, la app no está disponible.

  - **`test_available_with_url_only`** (L135)
    - Sin ejecutable pero con URL, la app está disponible.

  - **`test_available_with_empty_executable_and_url`** (L140)
    - Un ejecutable vacío con URL sigue disponible.

- **`TestApplicationKnowledgeIsCapabilityAvailable`** (línea 150) — 5 método(s) de test
  - is_capability_available distingue declared + available.

  - **`test_available_and_declared`** (L153)
    - App disponible + capability declarada → disponible.

  - **`test_declared_but_not_available`** (L163)
    - App no disponible (ejecutable inexistente) + capability declarada.

La capability está **declarada** (is_capable True) pero NO
**disponible** (is_capability_available False).

  - **`test_available_but_not_declared`** (L177)
    - App disponible pero capability no declarada → no disponible.

  - **`test_not_declared_not_available`** (L187)
    - App sin ejecutable válido y sin capabilities.

  - **`test_declared_capability_specific`** (L194)
    - is_capability_available respeta la capability específica.

- **`TestApplicationManagerAvailability`** (línea 208) — 8 método(s) de test
  - El gestor delega a is_available / is_capability_available del modelo.

  - **`test_is_application_available_true`** (L214)

  - **`test_is_application_available_false`** (L222)

  - **`test_is_application_available_unknown_app`** (L231)

  - **`test_is_capability_available_true`** (L234)

  - **`test_is_capability_available_declared_but_not_available`** (L244)
    - El gesto es el punto clave de 3.3.2.2: declarada ≠ disponible.

  - **`test_is_capability_available_not_declared`** (L261)

  - **`test_is_capability_available_unknown_app`** (L271)

  - **`test_is_capability_available_with_invalid_enum`** (L276)

  Métodos auxiliares (no test): setup_method

- **`TestModuleLevelAvailability`** (línea 291) — 6 método(s) de test
  - Funciones module-level is_application_available / is_capability_available.

  - **`test_is_application_available_with_real_app`** (L294)
    - Chrome está hardcodeado con ejecutable 'chrome'.

  - **`test_is_application_available_unknown_app`** (L302)

  - **`test_is_capability_available_with_enum`** (L305)

  - **`test_is_capability_available_with_string`** (L309)

  - **`test_is_capability_available_unknown_app`** (L313)

  - **`test_is_capability_available_invalid_string`** (L318)

- **`TestIntegratorAvailability`** (línea 326) — 7 método(s) de test
  - El integrador expone is_application_available / is_capability_available.

  - **`test_is_application_available_delegates_to_model`** (L333)

  - **`test_is_application_available_not_available`** (L341)

  - **`test_is_application_available_unknown_app`** (L350)

  - **`test_is_capability_available_true`** (L353)

  - **`test_is_capability_available_declared_not_available`** (L363)
    - El integrador distingue declared de available.

  - **`test_is_capability_available_not_declared`** (L380)

  - **`test_is_capability_available_unknown_app`** (L390)

  Métodos auxiliares (no test): setup_method

- **`TestDeclaredVsAvailableDistinction`** (línea 400) — 2 método(s) de test
  - Prueba el contrato central de 3.3.2.2: declarada ≠ disponible.

  - **`test_declared_true_available_false`** (L403)
    - App declarada con capability pero ejecutable no instalado.

is_application_capable → True (declarada)
is_capability_available → False (no disponible)

  - **`test_both_true`** (L426)
    - App disponible y con capability declarada: ambas True.

- **`TestGetApplicationKnowledgeIncludesAvailability`** (línea 449) — 3 método(s) de test
  - get_application_knowledge expone 'available' y 'declared_capabilities'.

  - **`test_get_application_knowledge_has_available_key`** (L452)

  - **`test_get_application_knowledge_declared_and_available_distinct`** (L467)

  - **`test_get_application_knowledge_unknown_app`** (L483)

- **`_FakeMemoryManager`** (línea 43) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-capability_query_contract"></a>
### `hands\test_capability_query_contract.py`

**Descripción:** Tests del contrato canónico de la consulta de capacidades (hoja 3.3.2.1).

**Módulos de origen probados:** src.hands.applications_core, src.hands.planner.application_integration, src.hands.planner.planner

**Clases de test:**

- **`TestCanonicalCapabilityQueryContract`** (línea 135) — 20 método(s) de test
  - Define el contrato canónico de la capability query en ApplicationManager.

  - **`test_get_application_capabilities_is_canonical_query`** (L159)
    - get_application_capabilities es la consulta canónica por aplicación.

Devuelve un dict cuyas claves son los *names* de las capability defs.

  - **`test_get_application_capabilities_structure`** (L168)
    - Cada entrada de la capability query contiene los campos canónicos.

  - **`test_get_application_capabilities_capability_field_matches_enum`** (L180)
    - El campo ``capability`` dentro del dict es el ``value`` del Enum.

  - **`test_get_application_capabilities_not_found_returns_empty`** (L186)
    - Apps desconocidas → {} (no lanza).

  - **`test_get_application_capabilities_no_capabilities_returns_empty`** (L190)
    - Apps sin capabilities declaradas → {}.

  - **`test_get_application_capabilities_resolves_alias`** (L196)
    - La query resuelve aliases de aplicación (Google Chrome → chrome).

  - **`test_get_capability_returns_def_by_name`** (L205)
    - get_capability(name) devuelve la ApplicationCapabilityDef completa.

  - **`test_get_capability_returns_def_by_value`** (L212)
    - get_capability acepta también el *value* del Enum (string).

  - **`test_get_capability_case_insensitive`** (L218)
    - get_capability no distingue mayúsculas/minúsculas.

  - **`test_get_capability_not_found_returns_none`** (L223)
    - Capability inexistente → None.

  - **`test_get_capability_returns_none_for_app_without_capabilities`** (L228)
    - App sin capabilities → get_capability siempre devuelve None.

  - **`test_is_capable_true_with_enum`** (L235)
    - is_capable(enum) devuelve True cuando la capability está declarada.

  - **`test_is_capable_false_with_enum`** (L239)
    - is_capable(enum) devuelve False cuando la capability no está declarada.

  - **`test_is_capable_false_with_string`** (L243)
    - is_capable NO acepta strings: compara enums directamente.

  - **`test_is_capable_false_empty_capabilities`** (L247)
    - App sin capabilities → is_capable siempre False.

  - **`test_get_applications_by_capability_returns_matching_apps`** (L254)
    - Devuelve las apps que declaran la capability (List[ApplicationKnowledge]).

  - **`test_get_applications_by_capability_open_excludes_others`** (L259)
    - Solo las apps con la capability aparecen en el resultado.

  - **`test_get_applications_by_capability_close_no_match`** (L271)
    - Ninguna app declara CLOSE → lista vacía.

  - **`test_module_get_application_knowledge_returns_dict`** (L278)
    - get_application_knowledge(app_name) serializa el modelo a dict.

  - **`test_module_get_applications_by_capability_returns_names`** (L286)
    - get_applications_by_capability(name) devuelve List[str] de nombres.

  Métodos auxiliares (no test): setup_method

- **`TestNoDuplicationIntegratorDelegatesToModel`** (línea 298) — 3 método(s) de test
  - ApplicationKnowledgeIntegrator DEBE delegar a ApplicationManager,
no reimplementar la query.

  - **`test_get_application_capabilities_delegates_to_manager`** (L302)
    - El integrador llama a manager.get_application_capabilities.

  - **`test_is_application_capable_delegates_to_app_knowledge`** (L316)
    - is_application_capable delega a ApplicationKnowledge.is_capable,
no reimplementa la comparación de enums.

  - **`test_get_applications_by_capability_delegates_to_manager`** (L332)
    - get_applications_by_capability del integrador delega a manager.

- **`TestQueryConsistencyAcrossLayers`** (línea 351) — 5 método(s) de test
  - La query canónica devuelve resultados consistentes a través de las capas.

  - **`test_manager_and_integrator_return_same_capability_keys`** (L357)
    - Manager.get_application_capabilities e Integrator.get_application_capabilities
devuelven las mismas claves para la misma app.

  - **`test_manager_and_integrator_is_capable_consistent`** (L366)
    - is_capable (enum) es consistente entre ApplicationKnowledge y el integrador.

  - **`test_planner_delegates_to_integrator`** (L376)
    - Planner.get_application_capabilities delega al integrador (no duplica).

  - **`test_planner_get_applications_by_capability_delegates`** (L388)
    - Planner.get_applications_by_capability delega al integrador.

  - **`test_planner_and_integrator_consistent_for_unknown_app`** (L400)
    - App desconocida → {} en todas las capas.

  Métodos auxiliares (no test): setup_method

- **`TestCanonicalQueryWithRealModel`** (línea 414) — 5 método(s) de test
  - Verifica el contrato de la capability query contra el modelo real.

  - **`test_chrome_has_open_capability`** (L420)
    - Chrome (hardcodeado) declara capability OPEN.

  - **`test_youtube_has_no_capabilities`** (L426)
    - YouTube (reconstruido desde entities.json) no declara capabilities.

Gap documentado en 3.3.1.1 (D-CAP-MODEL-GAP): las apps reconstruidas
desde entities.json carecen de la clave 'capabilities'.

  - **`test_get_applications_by_capability_open_only_hardcoded`** (L436)
    - Solo Chrome y Spotify (hardcodeadas) aparecen para OPEN.

  - **`test_query_for_unknown_capability`** (L443)
    - Una capability válida del Enum pero no declarada por ninguna app
devuelve lista vacía en la consulta inversa.

  - **`test_capability_query_returns_real_definitions`** (L449)
    - La capability query devuelve definiciones reales con estructura completa.

  Métodos auxiliares (no test): setup_method

- **`_FakeMemoryManager`** (línea 75) — 0 método(s) de test

  Métodos auxiliares (no test): __init__, save_entity, get_entities_by_type

---

<a name="hands/test-consumer_api_compatibility"></a>
### `hands\test_consumer_api_compatibility.py`

**Descripción:** Tests de compatibilidad de APIs consumidas por el modelo ApplicationKnowledge.

**Módulos de origen probados:** src.brain.llm, src.hands.applications_core, src.hands.executor, src.hands.planner.application_integration, src.hands.planner.htn_manager, src.hands.planner.planner

**Clases de test:**

- **`TestBrainApplicationKnowledgeConsumer`** (línea 102) — 5 método(s) de test
  - Brain._get_application_knowledge() consume el API del integrador.

  - **`test_returns_expected_dict_format`** (L110)
    - El resultado tiene las claves que Brain expone al LLM: applications, total_applications, supported_capabilities.

  - **`test_applications_entries_have_capabilities_and_available`** (L118)
    - Cada entrada de applications tiene capabilities (dict) y available (bool).

  - **`test_chrome_present_and_open_capable`** (L130)
    - Chrome esta en el catalogo, declara capability OPEN y expone disponibilidad.

  - **`test_spotify_present`** (L142)
    - Spotify esta en el catalogo.

  - **`test_supported_capabilities_constant`** (L147)
    - supported_capabilities es una lista de strings.

  Métodos auxiliares (no test): _brain

- **`TestHTNManagerCatalogConsumer`** (línea 159) — 3 método(s) de test
  - HTNManager._application_catalog_available() consume el API del integrador.

  - **`test_catalog_available_with_real_integrator`** (L162)
    - Devuelve True cuando el integrador tiene un manager con aplicaciones registradas.

  - **`test_catalog_available_false_when_manager_none`** (L168)
    - Devuelve False cuando application_manager es None.

  - **`test_catalog_available_false_when_applications_empty`** (L176)
    - Devuelve False cuando applications es un dict vacio.

- **`TestPlannerApplicationKnowledgeConsumer`** (línea 191) — 7 método(s) de test
  - Planner consume el API del integrador via load_application_knowledge y wrappers.

  - **`test_load_application_knowledge_loads_nodes`** (L199)
    - load_application_knowledge carga nodes de todas las apps al catalogo del planner.

  - **`test_get_applications_by_capability`** (L207)
    - get_applications_by_capability devuelve nombres de apps con la capacidad.

  - **`test_get_applications_by_capability_invalid_returns_empty`** (L213)
    - Una capacidad invalida devuelve lista vacia (no lanza).

  - **`test_get_application_capabilities`** (L218)
    - get_application_capabilities devuelve dict de capacidades para chrome.

  - **`test_get_application_capabilities_not_found`** (L225)
    - get_application_capabilities devuelve {} para una app inexistente.

  - **`test_get_application_ui_requirements`** (L230)
    - get_application_ui_requirements devuelve elementos UI requeridos.

  - **`test_get_application_ui_requirements_no_ui_for_open`** (L236)
    - Una capacidad sin elementos UI (open) devuelve lista vacia.

  Métodos auxiliares (no test): _planner

- **`TestExecutorCatalogFallbackConsumer`** (línea 246) — 4 método(s) de test
  - Executor._evaluate_condition consume el catalogo declarativo via
applications_core.get_application_manager() cuando el estado runtime esta vacio.

  - **`test_browser_available_via_catalog_fallback`** (L256)
    - browser_available es True via catalogo cuando el estado runtime no observa apps.
Ejerce: applications_core.get_application_manager().applications keys con 'chrome'.

  - **`test_application_available_via_catalog_fallback`** (L262)
    - application_available es True via catalogo cuando el estado runtime esta vacio.

  - **`test_browser_available_via_runtime_state`** (L267)
    - browser_available es True cuando el estado runtime tiene un navegador abierto.

  - **`test_browser_available_runtime_non_browser_still_true_via_catalog`** (L274)
    - browser_available sigue True via catalogo aunque el runtime observe apps no-navegador.

  Métodos auxiliares (no test): executor

- **`TestInternalFunctionsConsumerCompatibility`** (línea 286) — 7 método(s) de test
  - Funciones internas en applications_core.py consumen el modelo ApplicationKnowledge.

  - **`test_check_application_available_field_access_executable`** (L289)
    - _check_application_available accede app.executable (campo opcional del contrato).

  - **`test_check_application_available_with_url`** (L295)
    - _check_application_available usa app.url cuando executable esta vacio.

  - **`test_check_application_login_returns_true`** (L302)
    - _check_application_login siempre devuelve True por compatibilidad.

  - **`test_open_application_resolves_from_model`** (L307)
    - open_application resuelve la app desde el modelo y accede app.name, app.executable,
app.preflight_requirements — API consumida por el executor/accion registrada.

  - **`test_open_application_not_found_raises`** (L321)
    - open_application levanta ValueError cuando la app no esta en el modelo.

  - **`test_open_application_minimal_app_with_executable`** (L326)
    - open_application accede app.executable, app.name y app.preflight_requirements;
una app minimal (contrato 3.1.2) con ejecutable funciona correctamente.
Se parchea subprocess.Popen para evitar ejecucion real.

  - **`test_open_application_minimal_app_no_executable_no_url`** (L344)
    - open_application accede app.executable y app.url; con ambos None levanta RuntimeError.

NOTA: tras la correccion del manejador de errores en applications_core.py,
open_application propaga correctamente el RuntimeError original cuando la app
no tiene ejecutable ni URL configurados. La compatibilidad del API modelo no
se ve afectada: open_application accede correctamente a app.executable y app.url.

- **`TestMinimalContractConsumerCompatibility`** (línea 364) — 8 método(s) de test
  - Verifica que una ApplicationKnowledge con SOLO name + type (contrato minimo
definido en 3.1.2) es compatible con todas las APIs consumidas por los
consumidores reales identificados en 3.1.3.1.

  - **`test_minimal_app_satisfies_dataclass_contract`** (L369)
    - ApplicationKnowledge(name, type) crea instancia con todos los defaults correctos.

  - **`test_convert_application_to_nodes_with_minimal_app`** (L387)
    - convert_application_to_nodes funciona con una app minimal (solo name+type).

  - **`test_get_application_capabilities_with_minimal_app`** (L397)
    - get_application_capabilities devuelve {} para una app sin capacidades declaradas.

  - **`test_get_ui_elements_for_capability_with_minimal_app`** (L404)
    - get_ui_elements_for_capability devuelve [] para una app sin elementos UI.

  - **`test_is_application_capable_with_minimal_app`** (L411)
    - is_application_capable devuelve False para una app sin capacidades.

  - **`test_get_applications_by_capability_with_minimal_app`** (L417)
    - get_applications_by_capability funciona con una app minimal sin capacidades.

  - **`test_get_application_with_minimal_app`** (L424)
    - get_application resuelve la app minimal por nombre normalizado.

  - **`test_brain_consumer_with_minimal_app_in_catalog`** (L432)
    - Brain._get_application_knowledge() consume correctamente una app minimal
registrada en el catalogo del singleton.

---

<a name="hands/test-discovery_source_report"></a>
### `hands\test_discovery_source_report.py`

**Descripción:** Tests para CalibrationManager.get_discovery_source_report (3.8.1.5).

**Módulos de origen probados:** src.hands.calibration_manager

**Clases de test:**

- **`TestDiscoverySourceReport3815`** (línea 121) — 6 método(s) de test
  - Evidencia real de 3.8.1.5: cobertura, permisos y limitaciones de cada fuente.

  - **`test_todas_las_fuentes_estan_presentes`** (L124)

  - **`test_instaladas_ok_con_evidencia_real`** (L129)

  - **`test_path_ok_con_coverage_y_limitations`** (L135)

  - **`test_app_paths_con_coverage_y_limitations`** (L143)

  - **`test_procesos_con_coverage_y_limitations`** (L151)

  - **`test_ventanas_con_coverage_y_limitations`** (L159)

---

<a name="hands/test-discovery_source_report_3816"></a>
### `hands\test_discovery_source_report_3816.py`

**Descripción:** Tests para CalibrationManager.get_discovery_source_report (3.8.1.6).

**Módulos de origen probados:** src.hands.calibration_manager

**Clases de test:**

- **`TestDiscoverySourceReport3816`** (línea 40) — 10 método(s) de test
  - Pruebas de 3.8.1.6: resultados reales de las fuentes, fuentes inaccesibles y resultados vacios.

Cada fuente se prueba de forma isolada. Cuando una fuente falla, las demas
siguen reportando porque cada una esta en su propio bloque try/except del reporte.
El descubrimiento real (discover_applications) se mockea a [] en las pruebas que
no lo ejercitan, para aislar cada fuente y evitar ejecuciones innecesarias de PowerShell.

  - **`test_fuente_instaladas_inaccesible_reporta_ok_falso_con_error`** (L53)

  - **`test_fuente_path_inaccesible_reporta_ok_falso_con_error`** (L68)

  - **`test_fuente_app_paths_inaccesible_reporta_ok_falso_con_error`** (L80)

  - **`test_fuente_procesos_inaccesible_reporta_ok_falso_con_error`** (L93)

  - **`test_fuente_ventanas_inaccesible_reporta_ok_falso_con_error`** (L107)

  - **`test_fuente_instaladas_resultado_vacio`** (L125)

  - **`test_fuente_path_resultado_vacio`** (L137)

  - **`test_fuente_procesos_resultado_vacio`** (L150)

  - **`test_fuente_ventanas_resultado_vacio`** (L167)

  - **`test_fuente_instaladas_resultado_real_en_maquina`** (L188)
    - Ejecucion real (sin mocks) de aplicaciones_instaladas en esta maquina.

---

<a name="hands/test-entities_json_preservation_discovery"></a>
### `hands\test_entities_json_preservation_discovery.py`

**Descripción:** Preservacion de entities.json ante registro y consumo de conocimiento dinamico (unidad 3.8.4.4.4).

**Módulos de origen probados:** src.hands.applications_core

**Clases de test:**

- **`TestPreservacionEntitiesJsonDescubrimiento`** (línea 120) — 3 método(s) de test
  - register_discovered_application + consumidores no alteran entities.json.

  - **`test_knowledge_entities_json_inalterable`** (L123)
    - data/knowledge/entities.json (linea base 7 entidades) no se modifica.

  - **`test_memory_entities_json_inalterable`** (L139)
    - data/memory/entities.json (usado por MemoryManager) no se modifica
por registro/consumo de conocimiento dinamico.

  - **`test_siete_entidades_originales_intactas`** (L148)
    - Verifica concretamente que las 7 entidades originales de
data/knowledge/entities.json siguen presentes tras la operacion.

---

<a name="hands/test-executor"></a>
### `hands\test_executor.py`

**Descripción:** Tests para Executor, ExecutionResult, ExecutionState y ExecutionStatus
(src/hands/executor.py).

**Módulos de origen probados:** src.hands.action_registry, src.hands.executor

**Clases de test:**

- **`TestExecutionStatus`** (línea 110) — 3 método(s) de test

  - **`test_values`** (L111)

  - **`test_all_distinct`** (L119)

  - **`test_count`** (L123)

- **`TestExecutionResult`** (línea 131) — 12 método(s) de test

  - **`test_default_values`** (L132)

  - **`test_bool_success`** (L145)

  - **`test_bool_failed`** (L149)

  - **`test_bool_running`** (L153)

  - **`test_bool_retrying`** (L157)

  - **`test_bool_alternative`** (L161)

  - **`test_bool_pending`** (L165)

  - **`test_to_dict_keys`** (L169)

  - **`test_to_dict_values`** (L179)

  - **`test_to_dict_deepcopy_result`** (L196)

  - **`test_to_dict_deepcopy_failed_nodes`** (L202)

  - **`test_to_dict_deepcopy_alternatives_tried`** (L208)

- **`TestExecutionState`** (línea 219) — 9 método(s) de test

  - **`test_initial_state`** (L220)

  - **`test_update_merges_dicts`** (L236)

  - **`test_update_replaces_lists`** (L249)

  - **`test_update_merges_nested_dict`** (L261)
    - ExecutionState.update does shallow merge at top level (dict.update replaces keys).

  - **`test_update_raises_on_non_dict`** (L276)

  - **`test_update_skips_private_and_timestamp`** (L288)

  - **`test_update_sets_timestamp`** (L301)

  - **`test_to_dict_deepcopy`** (L316)

  - **`test_to_dict_includes_all_fields`** (L329)

- **`TestExecutorInit`** (línea 351) — 12 método(s) de test

  - **`test_init_creates_state`** (L352)

  - **`test_init_has_action_registry`** (L356)

  - **`test_init_has_modules`** (L359)

  - **`test_init_timeout_config`** (L364)

  - **`test_init_predictive_config`** (L367)

  - **`test_init_active_executions`** (L370)

  - **`test_init_execution_lock`** (L374)

  - **`test_init_state_available_actions_populated`** (L377)

  - **`test_init_planner_optional`** (L380)
    - Planner may or may not be available; either is acceptable.

  - **`test_init_learning_system`** (L384)

  - **`test_command_pattern`** (L388)

  - **`test_command_pattern_no_args`** (L395)

- **`TestNormalizePlanNode`** (línea 406) — 15 método(s) de test

  - **`test_dict_input`** (L407)

  - **`test_dict_defaults_id_from_action`** (L417)

  - **`test_dict_defaults_id_from_index`** (L422)

  - **`test_object_with_id`** (L427)

  - **`test_object_action_fallback_to_id`** (L444)
    - When object has no 'action' attr, uses 'id' as action.

  - **`test_invalid_string`** (L455)

  - **`test_invalid_int`** (L458)

  - **`test_invalid_none`** (L461)

  - **`test_parameters_not_dict`** (L464)

  - **`test_preconditions_not_list`** (L468)

  - **`test_effects_not_list`** (L472)

  - **`test_normalization_preserves_existing_fields`** (L476)

  - **`test_normalization_does_not_mutate_input`** (L481)

  - **`test_dict_with_alternatives`** (L486)

  - **`test_dict_with_metadata`** (L491)

- **`TestSafeCost`** (línea 497) — 13 método(s) de test

  - **`test_valid_float`** (L498)

  - **`test_valid_int`** (L501)

  - **`test_negative_clamped`** (L504)

  - **`test_negative_int_clamped`** (L507)

  - **`test_invalid_string`** (L510)

  - **`test_none`** (L513)

  - **`test_inf`** (L516)

  - **`test_nan`** (L519)

  - **`test_zero`** (L522)

  - **`test_custom_default`** (L525)

  - **`test_custom_default_negative_input`** (L528)

  - **`test_true_bool`** (L531)

  - **`test_false_bool`** (L534)

- **`TestGetNestedValue`** (línea 538) — 7 método(s) de test

  - **`test_flat_key`** (L539)

  - **`test_nested_key`** (L543)

  - **`test_missing_key`** (L547)

  - **`test_missing_nested_key`** (L551)

  - **`test_not_dict_mid_path`** (L555)

  - **`test_empty_key`** (L559)

  - **`test_deeply_nested`** (L563)

- **`TestEvaluateCondition`** (línea 572) — 31 método(s) de test

  - **`test_bool_true`** (L573)

  - **`test_bool_false`** (L576)

  - **`test_callable_true`** (L579)

  - **`test_callable_false`** (L582)

  - **`test_callable_exception`** (L585)

  - **`test_callable_with_state`** (L590)

  - **`test_string_key_in_state`** (L594)

  - **`test_string_key_not_in_state`** (L598)

  - **`test_string_empty_returns_true`** (L601)

  - **`test_dict_equals`** (L604)

  - **`test_dict_equals_fails`** (L608)

  - **`test_dict_gt`** (L612)

  - **`test_dict_lt`** (L616)

  - **`test_dict_ne`** (L620)

  - **`test_dict_gte`** (L624)

  - **`test_dict_lte`** (L628)

  - **`test_dict_exists`** (L632)

  - **`test_dict_exists_missing`** (L636)

  - **`test_dict_truthy_key`** (L639)

  - **`test_dict_no_key`** (L643)

  - **`test_dict_value_field`** (L646)

  - **`test_application_open_condition`** (L650)

  - **`test_application_closed_condition`** (L654)

  - **`test_application_closed_when_genuinely_closed`** (L658)

  - **`test_unknown_string_condition`** (L662)

  - **`test_app_prefix_condition`** (L665)

  - **`test_app_prefix_condition_missing`** (L669)

  - **`test_browser_available`** (L672)

  - **`test_resources_available`** (L675)

  - **`test_non_dict_non_str_non_callable`** (L678)
    - Objects with evaluate/is_satisfied/etc methods are tried.

  - **`test_non_dict_condition_with_to_dict`** (L685)

- **`TestCheckNodePreconditions`** (línea 697) — 8 método(s) de test

  - **`test_empty_preconditions`** (L698)

  - **`test_true_precondition`** (L702)

  - **`test_false_precondition`** (L706)

  - **`test_multiple_all_true`** (L710)

  - **`test_multiple_one_false`** (L714)

  - **`test_callable_precondition`** (L718)

  - **`test_empty_preconditions_list`** (L722)

  - **`test_none_preconditions`** (L726)

- **`TestVerifyNodeSuccess`** (línea 736) — 21 método(s) de test

  - **`test_dict_success_true`** (L737)

  - **`test_dict_success_false`** (L741)

  - **`test_dict_with_error`** (L745)

  - **`test_dict_with_error_message`** (L749)

  - **`test_dict_status_success`** (L753)

  - **`test_dict_status_completed`** (L757)

  - **`test_dict_status_failed`** (L761)

  - **`test_dict_no_success_no_status`** (L765)
    - execute_action already verified success before returning, so no status -> True.

  - **`test_none_result`** (L770)

  - **`test_false_result`** (L774)

  - **`test_true_result`** (L778)

  - **`test_bool_result_true`** (L782)

  - **`test_bool_result_false`** (L786)

  - **`test_success_int_one`** (L790)

  - **`test_success_int_zero`** (L794)

  - **`test_custom_checker_true`** (L798)

  - **`test_custom_checker_false`** (L802)

  - **`test_custom_checker_exception`** (L806)

  - **`test_object_with_status_attr`** (L812)

  - **`test_object_without_status_or_success`** (L817)
    - Objects without status/success default to True (execute_action already verified).

  - **`test_node_level_success_checker`** (L823)
    - success_checker at node level takes priority.

- **`TestShouldReplan`** (línea 833) — 9 método(s) de test

  - **`test_node_with_alternatives`** (L834)

  - **`test_expensive_node_no_alternatives`** (L838)

  - **`test_cheap_node_no_alternatives`** (L842)

  - **`test_mid_cost_node_no_alternatives`** (L846)

  - **`test_out_of_range_index`** (L850)

  - **`test_default_cost_node_no_alternatives`** (L854)

  - **`test_cost_exactly_5_not_expensive`** (L858)
    - cost > 5.0 is strict; cost=5.0 is not > 5.0, so falls to cost <= 3.0 check.

  - **`test_cost_exactly_3_replanable`** (L863)

  - **`test_empty_alternatives_list`** (L867)

- **`TestExtractCapability`** (línea 876) — 10 método(s) de test

  - **`test_focus_address_bar`** (L877)

  - **`test_click_address_bar`** (L880)

  - **`test_hotkey_ctrl_l`** (L883)

  - **`test_type_url`** (L886)

  - **`test_press_enter`** (L889)

  - **`test_open_chrome`** (L892)

  - **`test_activate_chrome`** (L895)

  - **`test_minimize_chrome`** (L898)

  - **`test_unknown_action_returns_itself`** (L901)

  - **`test_empty_action`** (L904)

- **`TestActionProvidesCapability`** (línea 912) — 12 método(s) de test

  - **`test_name_match`** (L922)

  - **`test_action_type_match`** (L926)

  - **`test_category_match`** (L930)

  - **`test_no_match`** (L934)

  - **`test_empty_capability`** (L938)

  - **`test_capability_declared_match`** (L942)

  - **`test_capability_declared_no_match`** (L946)

  - **`test_action_type_enum_value_match`** (L950)

  - **`test_case_insensitive_name`** (L954)

  - **`test_none_action_info_returns_false`** (L958)
    - None action_info is handled gracefully via getattr defaults.

  - **`test_real_action_info_capability_checked`** (L962)
    - A real ActionInfo whose declared capability differs from its name
must still match via the declared capability field.

  - **`test_real_action_info_keyboard_capability_checked`** (L980)
    - A real ActionInfo with a keyboard.* capability string must match.

  Métodos auxiliares (no test): _make_ai

- **`TestTryAlternative`** (línea 1002) — 6 método(s) de test

  - **`test_no_alternatives_returns_failed_result`** (L1003)

  - **`test_empty_alternatives_list`** (L1009)

  - **`test_with_string_alternative_same_as_action_skipped`** (L1019)

  - **`test_with_dict_alternative`** (L1031)

  - **`test_original_skipped_alternative_succeeds`** (L1041)
    - When an alternative action is registered and succeeds, returns SUCCESS.

  - **`test_alternative_precondition_failure`** (L1056)

- **`TestParseArgs`** (línea 1072) — 9 método(s) de test

  - **`test_none`** (L1073)

  - **`test_empty_string`** (L1076)

  - **`test_single_value`** (L1079)

  - **`test_tuple`** (L1083)

  - **`test_dict`** (L1087)

  - **`test_int`** (L1091)

  - **`test_invalid_raises`** (L1095)

  - **`test_whitespace_string`** (L1099)

  - **`test_float`** (L1103)

- **`TestPositionalToNamedParameters`** (línea 1108) — 5 método(s) de test

  - **`test_empty_args`** (L1109)

  - **`test_single_arg`** (L1115)

  - **`test_multiple_args`** (L1121)

  - **`test_too_many_args`** (L1127)

  - **`test_partial_args`** (L1133)

- **`TestGetLegacyFunction`** (línea 1144) — 6 método(s) de test

  - **`test_finds_function`** (L1145)

  - **`test_finds_mouse_function`** (L1150)

  - **`test_finds_keyboard_function`** (L1155)

  - **`test_not_found`** (L1160)

  - **`test_empty_name`** (L1163)

  - **`test_none_name`** (L1166)

- **`TestExecutePlan`** (línea 1174) — 12 método(s) de test

  - **`test_empty_plan_fails`** (L1175)

  - **`test_none_plan_fails`** (L1180)

  - **`test_non_list_plan_fails`** (L1184)

  - **`test_non_dict_plan_node_fails`** (L1188)

  - **`test_valid_node_with_callback_success`** (L1193)

  - **`test_node_failure_no_alternative`** (L1204)

  - **`test_multiple_nodes_all_success`** (L1209)

  - **`test_multiple_nodes_stop_on_failure`** (L1218)

  - **`test_plan_id_from_argument`** (L1227)

  - **`test_plan_execution_time_positive`** (L1234)

  - **`test_active_executions_tracking`** (L1241)

  - **`test_node_result_error_recorded`** (L1248)

- **`TestExecutePlanWithReplan`** (línea 1255) — 9 método(s) de test

  - **`test_empty_plan_fails`** (L1256)

  - **`test_none_plan_fails`** (L1260)

  - **`test_non_list_plan_fails`** (L1264)

  - **`test_invalid_node_fails`** (L1268)

  - **`test_successful_plan`** (L1272)

  - **`test_failed_node_triggers_replan`** (L1280)
    - When a node fails and has alternatives, replan is attempted.

  - **`test_goal_already_achieved`** (L1290)
    - If goal is achieved before executing any node, returns success.

  - **`test_replan_max_attempts_exhausted`** (L1301)

  - **`test_expensive_node_no_replan`** (L1307)
    - Expensive nodes (>5.0) don't trigger replan.

- **`TestReplanAfterFailure`** (línea 1318) — 4 método(s) de test

  - **`test_no_alternatives`** (L1319)

  - **`test_with_alternatives`** (L1325)

  - **`test_string_alternative`** (L1334)

  - **`test_out_of_range_index`** (L1339)

- **`TestFindAlternativeNodes`** (línea 1345) — 2 método(s) de test

  - **`test_returns_empty_for_unregistered_action`** (L1346)
    - If the action isn't registered, no alternatives found via capability search.

  - **`test_returns_list_type`** (L1351)

- **`TestUpdateWorldStateAfterFailure`** (línea 1360) — 2 método(s) de test

  - **`test_failure_records_application_state`** (L1361)

  - **`test_failure_without_application`** (L1368)

- **`TestUpdateWorldStateAfterFailurePersistence`** (línea 1380) — 3 método(s) de test
  - Verifica que los fallos reales se persisten en el estado del mundo
(memoria) para que la replanificacion y verificacion puedan consumirlos.

  - **`test_failure_persists_per_application`** (L1384)
    - Un fallo con aplicacion se persiste bajo la clave app_<clave>.

  - **`test_failure_persists_global_record`** (L1409)
    - Un fallo se agrega al registro global last_failures.

  - **`test_failure_without_application_persists_global_record_only`** (L1427)
    - Un fallo sin aplicacion no persiste por app_ pero sí persiste globalmente.

- **`TestGoalAchieved`** (línea 1450) — 10 método(s) de test

  - **`test_navigate_goal_success`** (L1451)

  - **`test_navigate_goal_url_mismatch`** (L1456)

  - **`test_navigate_goal_no_url`** (L1461)

  - **`test_open_application_goal_success`** (L1466)

  - **`test_close_application_goal_success`** (L1471)

  - **`test_search_goal_success`** (L1476)

  - **`test_search_goal_not_achieved`** (L1481)

  - **`test_unknown_goal_type`** (L1486)

  - **`test_target_state_dict`** (L1491)

  - **`test_target_state_dict_partial`** (L1496)

- **`TestProcessAndExecute`** (línea 1506) — 7 método(s) de test

  - **`test_no_command_returns_text`** (L1507)

  - **`test_command_pattern_matched`** (L1511)

  - **`test_non_string_input`** (L1516)

  - **`test_command_with_clean_text`** (L1520)
    - When command execution returns a truthy result, that result is returned.

  - **`test_unknown_command`** (L1526)

  - **`test_command_with_dict_args`** (L1530)

  - **`test_command_no_args`** (L1534)

- **`TestCreateGoalFromCommand`** (línea 1543) — 8 método(s) de test

  - **`test_navegar_a`** (L1544)

  - **`test_abrir_chrome`** (L1549)

  - **`test_abrir_youtube`** (L1554)

  - **`test_buscar_en_google`** (L1559)

  - **`test_cerrar_chrome`** (L1564)

  - **`test_unknown_command`** (L1569)

  - **`test_goal_has_metadata`** (L1573)

  - **`test_goal_has_id`** (L1579)

- **`TestCanExecute`** (línea 1589) — 4 método(s) de test

  - **`test_registered_action`** (L1590)

  - **`test_unregistered_action`** (L1596)

  - **`test_empty_action_name`** (L1599)

  - **`test_with_parameters`** (L1602)

- **`TestListCommands`** (línea 1613) — 4 método(s) de test

  - **`test_returns_list`** (L1614)

  - **`test_returns_sorted`** (L1618)

  - **`test_contains_strings`** (L1623)

  - **`test_non_empty`** (L1627)

- **`TestActionInfoMethods`** (línea 1636) — 3 método(s) de test

  - **`test_get_plannable_actions`** (L1637)

  - **`test_get_action_info_existing`** (L1641)

  - **`test_get_action_info_nonexistent`** (L1647)

- **`TestStateMethods`** (línea 1656) — 6 método(s) de test

  - **`test_get_current_state`** (L1657)

  - **`test_update_state`** (L1662)

  - **`test_update_state_merges_apps`** (L1666)

  - **`test_get_state_for_planning`** (L1670)

  - **`test_get_state_for_planning_includes_app_keys`** (L1677)

  - **`test_get_state_for_planning_includes_ui_elements`** (L1682)

- **`TestLearningInterfaces`** (línea 1692) — 8 método(s) de test

  - **`test_get_learning_insights_no_system`** (L1693)

  - **`test_get_action_learning_insights_no_system`** (L1698)

  - **`test_get_cost_adjustments_no_system`** (L1703)

  - **`test_export_learning_data_no_system`** (L1707)

  - **`test_import_learning_data_no_system`** (L1712)

  - **`test_clear_learning_data_no_system`** (L1716)

  - **`test_enable_learning_no_system`** (L1720)

  - **`test_get_action_stats`** (L1724)

- **`TestGetExecutor`** (línea 1733) — 3 método(s) de test

  - **`test_returns_executor`** (L1734)

  - **`test_singleton_persistence`** (L1746)

  - **`test_singleton_thread_safety`** (L1751)
    - get_executor uses a lock.

- **`TestExecuteNodeAction`** (línea 1761) — 9 método(s) de test

  - **`test_callback_executes_successfully`** (L1762)

  - **`test_no_callback_no_action_raises`** (L1770)

  - **`test_node_without_action_falls_back_to_id`** (L1776)
    - When action is None, falls back to node id, then fails if not registered.

  - **`test_declarative_node_raises`** (L1784)

  - **`test_node_type_resource_raises`** (L1790)

  - **`test_node_type_goal_raises`** (L1796)

  - **`test_invalid_parameters_raises`** (L1802)

  - **`test_explicit_action_from_metadata`** (L1807)

  - **`test_verify_false_passes_through`** (L1815)

- **`FakeCondition`** (línea 680) — 0 método(s) de test

  Métodos auxiliares (no test): evaluate

- **`Cond`** (línea 686) — 0 método(s) de test

  Métodos auxiliares (no test): to_dict

---

<a name="hands/test-executor_state"></a>
### `hands\test_executor_state.py`

**Descripción:** Tests de estados para el Executor — hoja 3.4.4.1 (Tests de estados).

**Módulos de origen probados:** src.eyes.screen, src.hands.executor, src.utils.config

**Clases de test:**

- **`TestUpdateWorldState`** (línea 101) — 21 método(s) de test
  - Tests para _update_world_state: actualización exitosa del estado del mundo.

  - **`test_non_success_does_not_update`** (L104)
    - Si el resultado no es SUCCESS, no se actualiza el estado del mundo.

  - **`test_no_application_does_not_crash`** (L112)
    - Un nodo sin aplicación no causa crash.

  - **`test_app_open_effect_updates_state`** (L120)
    - El efecto app_open actualiza open=True en application_states y la flag plana.

  - **`test_app_closed_effect_updates_state`** (L128)
    - El efecto app_closed actualiza open=False en application_states.

  - **`test_app_active_effect_updates_state`** (L138)
    - El efecto app_active actualiza active=True en application_states.

  - **`test_app_minimized_effect_updates_state`** (L146)
    - El efecto app_minimized actualiza active=False en application_states.

  - **`test_application_open_generic_effect`** (L157)
    - El efecto application_open (genérico) actualiza la flag {app_key}_open.

  - **`test_app_key_open_effect`** (L165)
    - El efecto chrome_open actualiza open=True en application_states.

  - **`test_address_bar_focused_updates_ui_element`** (L173)
    - El efecto address_bar_focused actualiza ui_elements con focused=True.

  - **`test_destination_loaded_updates_state`** (L181)
    - El efecto destination_loaded actualiza la flag destination_loaded.

  - **`test_search_performed_updates_state`** (L189)
    - El efecto search_performed actualiza la flag search_performed.

  - **`test_url_typed_updates_application_state`** (L196)
    - El efecto url_typed actualiza url_typed=True en application_states.

  - **`test_state_updates_in_result`** (L204)
    - state_updates en el resultado se aplican al estado.

  - **`test_new_state_in_result`** (L216)
    - new_state en el resultado se aplica al estado.

  - **`test_current_url_in_result`** (L228)
    - current_url en el resultado se establece en el estado.

  - **`test_ui_element_focused_effect`** (L239)
    - El efecto element_focused con ui_element actualiza ui_elements.

  - **`test_ui_element_typed_effect`** (L249)
    - El efecto text_typed con ui_element actualiza ui_elements.

  - **`test_multiple_effects`** (L258)
    - Múltiples efectos se aplican todos.

  - **`test_app_name_with_spaces`** (L268)
    - El nombre de aplicación con espacios se normaliza en app_key.

  - **`test_last_actions_updated`** (L280)
    - last_actions se actualiza después de _update_world_state.

  - **`test_timestamp_updated`** (L287)
    - El timestamp se actualiza después de _update_world_state.

- **`TestExecutorStateWithScreenComparison`** (línea 300) — 7 método(s) de test
  - Tests de integración entre ExecutionState.application_states y las
funciones de comparación/reconciliación de screen.py.

Verifica que el estado declarado del Executor (applications.json o
current_state.application_states) puede compararse y reconciliarse con
un estado observable (ApplicationState).

  - **`test_compare_chrome_closed_with_closed_state`** (L309)
    - El estado declarado de Chrome (todas False) coincide con CLOSED.

  - **`test_compare_chrome_open_with_open_state`** (L319)
    - Un estado declarado con open=True coincide con OPEN.

  - **`test_compare_chrome_discrepancy`** (L325)
    - Un estado declarado cerrado pero observable abierto produce discrepancia.

  - **`test_reconcile_chrome_state_after_effect`** (L332)
    - Después de aplicar app_open, el estado del executor puede reconciliarse
con un estado observable.

  - **`test_reconcile_discrepancy_updates_executor_state`** (L345)
    - La reconciliación puede usarse para actualizar el estado del executor
cuando hay discrepancia entre el declarado y el observable.

  - **`test_reconcile_preserves_domain_flags`** (L370)
    - La reconciliación preserva las flags de dominio (playing, streaming, recording).

  - **`test_reconcile_then_evaluate_condition`** (L383)
    - Después de reconciliar, _evaluate_condition refleja el estado real.

- **`TestEvaluateConditionNestedStates`** (línea 407) — 15 método(s) de test
  - Tests complementarios para _evaluate_condition con estados anidados
de application_states.

  - **`test_chrome_active_with_nested_state`** (L411)
    - chrome_active es True cuando application_states tiene active=True.

  - **`test_chrome_active_false_with_nested_state`** (L416)
    - chrome_active es False cuando application_states tiene active=False.

  - **`test_chrome_closed_true_when_open_false`** (L421)
    - chrome_closed es True cuando application_states tiene open=False.

  - **`test_chrome_closed_false_when_open_true`** (L426)
    - chrome_closed es False cuando application_states tiene open=True.

  - **`test_app_chrome_with_nested_state`** (L431)
    - app_chrome es True cuando Chrome está en application_states.

  - **`test_app_chrome_not_present`** (L436)
    - app_chrome es False cuando Chrome no está en application_states.

  - **`test_application_active_with_nested_state`** (L441)
    - application_active es True cuando alguna app tiene active=True.

  - **`test_application_active_false_when_all_inactive`** (L446)
    - application_active es False cuando ninguna app está activa.

  - **`test_browser_open_with_nested_state`** (L451)
    - browser_open es True cuando Chrome (navegador) está abierto.

  - **`test_browser_open_false_when_closed`** (L456)
    - browser_open es False cuando todos los navegadores están cerrados.

  - **`test_application_closed_condition`** (L461)
    - application_closed es False (no existe como sufijo _closed) —
se trata como key literal que no existe, retorna False.

  - **`test_app_state_with_domain_flags_does_not_break_evaluation`** (L470)
    - Flags de dominio coexistiendo no rompen la evaluación de condiciones canónicas.

  - **`test_multiple_apps_state`** (L480)
    - Múltiples aplicaciones en application_states se evalúan correctamente.

  - **`test_browser_active_with_firefox`** (L491)
    - browser_active es True cuando Firefox (navegador) está activo.

  - **`test_browser_active_false_when_no_browser_active`** (L496)
    - browser_active es False cuando ningún navegador está activo.

- **`TestGoalAchievedNestedStates`** (línea 506) — 8 método(s) de test
  - Tests complementarios para _goal_achieved con estados anidados.

  - **`test_open_application_uses_nested_state`** (L509)
    - open_application goal se resuelve usando application_states anidado.

_goal_achieved normaliza target a lowercase, así que la clave en
application_states también debe estar en lowercase para coincidir.

  - **`test_open_application_unsatisfied_nested`** (L519)
    - open_application goal es False cuando la app no está abierta en estado anidado.

  - **`test_close_application_uses_nested_state`** (L525)
    - close_application goal se resuelve usando application_states anidado.

  - **`test_close_application_unsatisfied_nested`** (L531)
    - close_application goal es False cuando la app aún está abierta en estado anidado.

  - **`test_open_application_flat_takes_priority`** (L537)
    - Si existe la flag plana, se usa antes que el estado anidado.

  - **`test_open_application_no_state`** (L547)
    - open_application goal es False cuando no hay estado de la app.

  - **`test_close_application_no_state`** (L553)
    - close_application goal es True cuando no hay estado de la app (asumido cerrado).

  - **`test_open_application_nested_case_insensitive_lookup`** (L559)
    - _goal_achieved normaliza target a lowercase; una clave 'Chrome' no se
encuentra pero una clave 'chrome' sí — documenta el comportamiento real.

- **`TestStateMappingConsistency`** (línea 575) — 6 método(s) de test
  - Tests de consistencia entre ApplicationState, observable_state_to_flags y
el estado declarado del Executor.

  - **`test_observable_state_to_flags_returns_all_canonical`** (L580)
    - observable_state_to_flags retorna exactamente las 4 flags canónicas.

  - **`test_observable_state_to_flags_all_boolean`** (L586)
    - Todos los valores retornados son booleans.

  - **`test_state_to_flags_then_compare`** (L593)
    - Para cada ApplicationState, las flags observables deben comparar
correctamente con un estado declarado que coincida.

  - **`test_state_to_flags_then_reconcile_match`** (L603)
    - Para cada ApplicationState, reconciliar con un estado declarado idéntico
da reconciled=False (coincidencia).

  - **`test_state_to_flags_then_reconcile_discrepancy`** (L614)
    - Para cada ApplicationState, reconciliar con un estado declarado opuesto
(todas las flags invertidas) da reconciled=True y flags actualizadas.

  - **`test_executor_state_after_open_matches_observable`** (L623)
    - Después de aplicar app_open, el estado del executor coincide con OPEN.

---

<a name="hands/test-restore_window_state"></a>
### `hands\test_restore_window_state.py`

**Descripción:** Tests for _restore_window_state (3.5.2.3) – verify reusable state without destroying user state.

**Módulos de origen probados:** src.hands.calibration_manager

**Clases de test:**

- **`TestRestoreWindowState`** (línea 12) — 3 método(s) de test

  - **`test_restore_success`** (L18)
    - Valid hwnd and snapshot should return True.

  - **`test_restore_failure_missing_hwnd`** (L40)
    - Missing hwnd should return False.

  - **`test_restore_failure_invalid_window`** (L47)
    - Invalid window handle should return False.

  Métodos auxiliares (no test): setUp

---

<a name="hands/test-system_inventory"></a>
### `hands\test_system_inventory.py`

**Descripción:** Tests de contrato del inventario persistente del sistema de archivos (unidad 3.8.5.1.4.1). Verifican serialización/deserialización de `InventoryEntry`, generación de identificador local de equipo estable (sin MAC ni serial), controles de privacidad por defecto (sin lectura de contenido, sin rutas completas en logs), exclusiones técnicas de rutas y puntos de montaje, separación entre hechos observados del SO e inferencias, truncamiento seguro de rutas para logs, controles de operación del inventario con aislamiento por equipo, valores por defecto del contrato y serialización para persistencia en JSON. También verifican el contrato común de volumen multiplataforma (`VolumenComun`), su conversión desde `VolumeInfo` sin forzar letras de unidad ni rutas de Windows en otros SO, y la enumeración unificada de volúmenes.

**Clases de test:**

| Clase | Descripción |
|---|---|
| `TestInventoryEntryRoundTrip` | Serialización/deserialización de `InventoryEntry` sin pérdida de datos. |
| `TestMachineId` | Identificador de equipo estable y determinista. |
| `TestPrivacidad` | Controles de privacidad del contrato por defecto y truncamiento seguro de rutas. |
| `TestExclusiones` | Exclusiones técnicas de rutas y puntos de montaje. |
| `TestHechosVsInferencias` | Separación entre hechos observados e inferencias. |
| `TestControlInventario` | Operaciones de control con aislamiento por equipo. |
| `TestContratoPorDefecto` | Valores por defecto del contrato de inventario. |
| `TestSerializacionParaPersistencia` | Serialización de entrada como JSON válido para persistencia. |
| `TestVolumenComun` | Contrato común de volumen: no impone letra de unidad ni rutas Windows en SO no Windows. |
| `TestVolumenComunDesdeInfo` | Conversión de `VolumeInfo` a `VolumenComun` sin forzar conceptos Windows. |
| `TestEnumerarVolumenesComun` | Enumeración unificada de volúmenes que devuelve contratos comunes de volumen. |

**Resultados:** 98 tests unitarios, 98 PASSED / 0 FAILED.

---

<a name="hands/test-system_inventory_storage"></a>
### `hands\test_system_inventory_storage.py`

**Descripción:** Tests de contrato del almacenamiento canonico SQLite del inventario persistente del sistema de archivos. Verifican creación de `data/system_inventory.sqlite3` (en directorio temporal, nunca en producción), inicialización y versionado del esquema (`schema_version`), registro de equipos y volumenes con aislamiento por equipo (`machine_id`), ejecuciones de escaneo (inicio/fin, resultado, métricas), escritura por lotes atómica de entradas de archivo y candidatos de aplicación, tablas separadas para entradas genéricas de archivo y candidatos de aplicación, consultas indexadas paginadas por nombre, extensión y prefijo de ruta, contador de entradas y recuperación de la última ejecución por equipo/volumen, migraciones verificables de esquema, búsqueda por estado, normalización de rutas, control de concurrencia de escaneos, manifiesto JSON ligero, clave unica por ruta normalizada y copia de seguridad, detección de corrupción y recuperación de la base de datos.

**Clases de test:**

| Clase | Descripción |
|---|---|
| `TestCreacionBaseDeDatos` | Creación del fichero SQLite en la ruta dada, ruta por defecto y versionado del esquema. |
| `TestMaquinasYVolumenes` | Registro de equipos y volumenes con aislamiento por `machine_id`. |
| `TestScanRuns` | Inicio y finalización de ejecuciones de escaneo, resultados permitidos y última ejecución. |
| `TestInsercionAtomica` | Inserción por lotes atómica, lote vacío y ausencia de entradas parciales tras fallo. |
| `TestConsultasIndexadas` | Búsquedas por nombre, extensión y prefijo de ruta con paginación y aislamiento por equipo. |
| `TestContexto` | Uso como gestor de contexto, cierre de conexión, WAL y claves foráneas. |
| `TestClaveUnicaRutaNormalizada` | Clave unica `(machine_id, volumen, ruta normalizada)` y ausencia de duplicados. |
| `TestNormalizacionRutas` | Normalización de rutas según la distinción mayúsculas/minúsculas del sistema de archivos. |
| `TestMigracionEsquemaV1AV2` | Migración de esquema v1 a v2 (columna `normalized_path` e índice único). |
| `TestMigracionesVerificables` | Migraciones versionadas, atómicas, sin pérdida ni reinterpretación de datos; fallo sin cambios parciales. |
| `TestBusquedaPorEstado` | Consultas de entradas por estado de exclusión. |
| `TestConcurrenciaEscaneos` | Bloqueo de concurrencia, `ConcurrentScanError`, liberación del bloqueo y modo de journaling WAL. |
| `TestBackupCorrupcionYRecuperacion` | Copia de seguridad, verificación de integridad (`PRAGMA quick_check` / `integrity_check`) y restauración desde copia sin sobrescribir una base válida con una copia vacía, incompleta o corrupta. |

**Resultados:** 70 tests unitarios, 70 PASSED / 0 FAILED.

---

<a name="hands/test-ui_elements"></a>
### `hands\test_ui_elements.py`

**Descripción:** Tests de elementos UI para JARVIS — FASE 3.4.4.2

**Módulos de origen probados:** src.eyes.screen, src.eyes.vision, src.hands.applications_core, src.hands.calibration_manager, src.hands.coordinate_manager, src.hands.keyboard, src.hands.mouse, src.hands.universal_visual_calibrator

**Clases de test:**

- **`TestUIElementDetection`** (línea 24) — 5 método(s) de test
  - Tests para detección de elementos UI

  - **`test_ui_element_basic_detection`** (L34)
    - Test básico de detección de elementos UI

  - **`test_ui_element_detection_with_calibration`** (L54)
    - Test de detección con calibración existente

  - **`test_ui_element_text_field_detection`** (L80)
    - Test de detección de campos de texto

  - **`test_ui_element_checkbox_detection`** (L98)
    - Test de detección de checkboxes

  - **`test_ui_element_dropdown_detection`** (L117)
    - Test de detección de menús desplegables

  Métodos auxiliares (no test): setup_method

- **`TestUIElementCalibration`** (línea 138) — 3 método(s) de test
  - Tests para calibración de elementos UI

  - **`test_ui_element_calibration_save`** (L146)
    - Test de calibración y guardado de elementos UI

  - **`test_ui_element_calibration_load`** (L168)
    - Test de carga de elementos calibrados

  - **`test_ui_element_calibration_update`** (L180)
    - Test de actualización de calibración existente

  Métodos auxiliares (no test): setup_method

- **`TestUIElementInteraction`** (línea 201) — 4 método(s) de test
  - Tests para interacción con elementos UI

  - **`test_ui_element_click`** (L209)
    - Test de clic en elemento UI

  - **`test_ui_element_double_click`** (L222)
    - Test de doble clic en elemento UI

  - **`test_ui_element_right_click`** (L237)
    - Test de clic derecho en elemento UI

  - **`test_ui_element_text_input`** (L250)
    - Test de entrada de texto en elemento UI

  Métodos auxiliares (no test): setup_method

- **`TestUIElementValidation`** (línea 265) — 3 método(s) de test
  - Tests para validación de elementos UI

  - **`test_ui_element_visibility_check`** (L273)
    - Test de verificación de visibilidad de elementos

  - **`test_ui_element_confidence_threshold`** (L301)
    - Test de umbral de confianza para elementos UI

  - **`test_ui_element_state_validation`** (L327)
    - Test de validación de estado de elementos

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-ui_elements_final"></a>
### `hands\test_ui_elements_final.py`

**Descripción:** Tests finales funcionales de elementos UI para JARVIS — FASE 3.4.4.2

**Módulos de origen probados:** src.hands.applications_core, src.hands.calibration_manager, src.hands.coordinate_manager

**Clases de test:**

- **`TestUIElementFinal`** (línea 16) — 9 método(s) de test
  - Tests finales funcionales para elementos UI

  - **`test_ui_element_creation_with_correct_parameters`** (L19)
    - Test de creación de elementos UI con parámetros correctos

  - **`test_application_manager_initialization_working`** (L33)
    - Test de inicialización del gestor de aplicaciones

  - **`test_application_normalization_working`** (L42)
    - Test de normalización de nombres de aplicaciones

  - **`test_coordinate_manager_methods_exist`** (L56)
    - Test de existencia de métodos en el gestor de coordenadas

  - **`test_calibration_manager_methods_exist`** (L65)
    - Test de existencia de métodos en el gestor de calibración

  - **`test_ui_element_different_types`** (L74)
    - Test de creación de diferentes tipos de elementos UI

  - **`test_application_knowledge_structure_accessible`** (L99)
    - Test de estructura de conocimiento de aplicaciones accesible

  - **`test_ui_element_coordinates_structure`** (L120)
    - Test de estructura de coordenadas de elementos UI

  - **`test_application_capabilities_structure`** (L140)
    - Test de estructura de capacidades de aplicaciones

- **`TestUIElementIntegration`** (línea 166) — 3 método(s) de test
  - Tests de integración de elementos UI

  - **`test_application_manager_integration`** (L169)
    - Test de integración del gestor de aplicaciones

  - **`test_ui_element_creation_workflow`** (L190)
    - Test de flujo de creación de elementos UI

  - **`test_ui_element_validation_workflow`** (L227)
    - Test de flujo de validación de elementos UI

---

<a name="hands/test-ui_elements_minimal"></a>
### `hands\test_ui_elements_minimal.py`

**Descripción:** Tests mínimos funcionales de elementos UI para JARVIS — FASE 3.4.4.2

**Módulos de origen probados:** src.hands.applications_core, src.hands.calibration_manager, src.hands.coordinate_manager

**Clases de test:**

- **`TestUIElementMinimal`** (línea 16) — 9 método(s) de test
  - Tests mínimos funcionales para elementos UI

  - **`test_application_manager_initialization`** (L19)
    - Test de inicialización del gestor de aplicaciones

  - **`test_application_normalization`** (L28)
    - Test de normalización de nombres de aplicaciones

  - **`test_coordinate_manager_initialization`** (L42)
    - Test de inicialización del gestor de coordenadas

  - **`test_calibration_manager_initialization`** (L50)
    - Test de inicialización del gestor de calibración

  - **`test_application_knowledge_structure`** (L58)
    - Test de estructura de conocimiento de aplicaciones

  - **`test_ui_element_structure_from_applications`** (L79)
    - Test de estructura de UI elements desde aplicaciones existentes

  - **`test_ui_element_types_from_existing`** (L107)
    - Test de tipos de UI elements desde aplicaciones existentes

  - **`test_ui_element_coordinates_from_existing`** (L122)
    - Test de coordenadas de UI elements desde aplicaciones existentes

  - **`test_application_capabilities`** (L139)
    - Test de capacidades de aplicaciones

- **`TestUIElementIntegrationMinimal`** (línea 165) — 3 método(s) de test
  - Tests mínimos de integración de elementos UI

  - **`test_application_manager_integration`** (L168)
    - Test de integración del gestor de aplicaciones

  - **`test_ui_element_validation_from_existing`** (L189)
    - Test de validación de UI elements desde aplicaciones existentes

  - **`test_application_ui_elements_count`** (L215)
    - Test de conteo de UI elements en aplicaciones

- **`TestUIElementAdvancedMinimal`** (línea 236) — 3 método(s) de test
  - Tests avanzados mínimos para elementos UI

  - **`test_ui_element_diversity`** (L239)
    - Test de diversidad de UI elements

  - **`test_ui_element_capabilities_relation`** (L262)
    - Test de relación entre UI elements y capacidades

  - **`test_application_state_consistency`** (L286)
    - Test de consistencia de estados de aplicaciones

---

<a name="hands/test-ui_elements_real"></a>
### `hands\test_ui_elements_real.py`

**Descripción:** Tests realistas de elementos UI para JARVIS — FASE 3.4.4.2

**Módulos de origen probados:** src.hands.applications_core, src.hands.calibration_manager, src.hands.coordinate_manager

**Clases de test:**

- **`TestUIElementReal`** (línea 15) — 10 método(s) de test
  - Tests realistas para elementos UI

  - **`test_ui_element_creation_real`** (L18)
    - Test de creación real de elementos UI

  - **`test_application_manager_initialization`** (L32)
    - Test de inicialización real del gestor de aplicaciones

  - **`test_application_knowledge_structure`** (L44)
    - Test de estructura de conocimiento de aplicaciones

  - **`test_application_capabilities`** (L56)
    - Test de capacidades de aplicaciones

  - **`test_coordinate_manager_initialization`** (L70)
    - Test de inicialización real del gestor de coordenadas

  - **`test_coordinate_retrieval_real`** (L80)
    - Test real de recuperación de coordenadas

  - **`test_coordinate_saving_real`** (L102)
    - Test real de guardado de coordenadas

  - **`test_calibration_manager_initialization`** (L121)
    - Test de inicialización real del gestor de calibración

  - **`test_ui_element_types`** (L127)
    - Test de tipos de elementos UI existentes

  - **`test_application_capabilities_existence`** (L152)
    - Test de existencia de capacidades en aplicaciones

---

<a name="hands/test-ui_elements_simple"></a>
### `hands\test_ui_elements_simple.py`

**Descripción:** Tests simplificados de elementos UI para JARVIS — FASE 3.4.4.2

**Módulos de origen probados:** src.eyes.screen, src.eyes.vision, src.hands.applications_core, src.hands.calibration_manager, src.hands.coordinate_manager

**Clases de test:**

- **`TestUIElementDetection`** (línea 20) — 3 método(s) de test
  - Tests para detección de elementos UI

  - **`test_ui_element_detection_basic`** (L31)
    - Test básico de detección de elementos UI

  - **`test_ui_element_detection_with_vision_mock`** (L46)
    - Test de detección con mock de visión

  - **`test_ui_element_screen_analysis`** (L68)
    - Test de análisis de pantalla para elementos UI

  Métodos auxiliares (no test): setup_method

- **`TestUIElementCalibration`** (línea 90) — 4 método(s) de test
  - Tests para calibración de elementos UI

  - **`test_calibration_manager_initialization`** (L98)
    - Test de inicialización del gestor de calibración

  - **`test_coordinate_manager_initialization`** (L102)
    - Test de inicialización del gestor de coordenadas

  - **`test_coordinate_retrieval`** (L107)
    - Test de recuperación de coordenadas calibradas

  - **`test_coordinate_saving`** (L121)
    - Test de guardado de coordenadas

  Métodos auxiliares (no test): setup_method

- **`TestUIElementValidation`** (línea 133) — 2 método(s) de test
  - Tests para validación de elementos UI

  - **`test_ui_element_creation`** (L140)
    - Test de creación de elementos UI

  - **`test_application_manager_capabilities`** (L152)
    - Test de capacidades del gestor de aplicaciones

  Métodos auxiliares (no test): setup_method

- **`TestUIElementIntegration`** (línea 165) — 2 método(s) de test
  - Tests de integración de elementos UI

  - **`test_application_knowledge_structure`** (L173)
    - Test de estructura de conocimiento de aplicaciones

  - **`test_element_interaction_flow`** (L183)
    - Test de flujo de interacción con elementos

  Métodos auxiliares (no test): setup_method

---

<a name="hands/test-ui_elements_working"></a>
### `hands\test_ui_elements_working.py`

**Descripción:** Tests funcionales de elementos UI para JARVIS — FASE 3.4.4.2

**Módulos de origen probados:** src.hands.applications_core, src.hands.calibration_manager, src.hands.coordinate_manager

**Clases de test:**

- **`TestUIElementWorking`** (línea 16) — 9 método(s) de test
  - Tests funcionales para elementos UI

  - **`test_ui_element_creation_correct`** (L19)
    - Test de creación de elementos UI con parámetros correctos

  - **`test_ui_element_different_types_correct`** (L33)
    - Test de creación de diferentes tipos de elementos UI

  - **`test_ui_element_coordinates_structure_correct`** (L58)
    - Test de estructura de coordenadas de elementos UI

  - **`test_application_manager_initialization_working`** (L78)
    - Test de inicialización del gestor de aplicaciones

  - **`test_application_normalization_working`** (L87)
    - Test de normalización de nombres de aplicaciones

  - **`test_coordinate_manager_methods_exist`** (L101)
    - Test de existencia de métodos en el gestor de coordenadas

  - **`test_calibration_manager_methods_exist`** (L110)
    - Test de existencia de métodos en el gestor de calibración

  - **`test_application_knowledge_structure_accessible`** (L118)
    - Test de estructura de conocimiento de aplicaciones accesible

  - **`test_application_capabilities_structure_correct`** (L139)
    - Test de estructura de capacidades de aplicaciones

- **`TestUIElementIntegrationWorking`** (línea 165) — 3 método(s) de test
  - Tests de integración de elementos UI

  - **`test_application_manager_integration_working`** (L168)
    - Test de integración del gestor de aplicaciones

  - **`test_ui_element_creation_workflow_correct`** (L189)
    - Test de flujo de creación de elementos UI

  - **`test_ui_element_validation_workflow_correct`** (L226)
    - Test de flujo de validación de elementos UI

- **`TestUIElementAdvanced`** (línea 252) — 3 método(s) de test
  - Tests avanzados para elementos UI

  - **`test_ui_element_type_variations`** (L255)
    - Test de variaciones de tipos de elementos UI

  - **`test_ui_element_coordinates_variations`** (L277)
    - Test de variaciones de coordenadas de elementos UI

  - **`test_application_ui_elements_integration`** (L297)
    - Test de integración de UI elements con aplicaciones

---

<a name="hands/windows/test-window_verification"></a>
### `hands\windows\test_window_verification.py`

**Descripción:** Tests for window verification (3.5.2.2).
Uses mocks to test _verificar_aplicacion_abierta.

**Módulos de origen probados:** src.hands.windows.windows

**Clases de test:**

- **`TestWindowVerification`** (línea 12) — 3 método(s) de test

  - **`test_window_visible`** (L13)
    - Mock _get_application_windows returning a visible window -> True.

  - **`test_window_not_visible`** (L21)
    - Mock window with is_visible=False -> False.

  - **`test_no_windows`** (L29)
    - Empty list -> False.

---

## 📂 `helpers/`

1 ficheros de test, 7 métodos de test.

<a name="helpers/test-entities_state_helper"></a>
### `helpers\test_entities_state_helper.py`

**Descripción:** Tests del helper reutilizable de estado de entities.json (unidad 3.8.4.4.3).

**Clases de test:**

- **`TestSnapshotYComparacion`** (línea 47) — 3 método(s) de test

  - **`test_snapshot_captura_contenido_hash_y_tamano`** (L48)

  - **`test_snapshots_iguales_si_mismo_contenido`** (L58)

  - **`test_snapshot_devuelve_objeto_inmutable`** (L65)

- **`TestCopiaTemporal`** (línea 74) — 1 método(s) de test

  - **`test_copia_queda_en_directorio_temporal_y_no_modifica_original`** (L75)

- **`TestVerifyEntitiesJsonUnchanged`** (línea 93) — 3 método(s) de test

  - **`test_operacion_sin_cambios_reporta_no_cambio_y_source_untouched`** (L116)

  - **`test_operacion_que_cambia_reporta_cambio_pero_source_untouched`** (L126)

  - **`test_trabaja_sobre_copia_temporal_y_libera_recursos`** (L146)

  Métodos auxiliares (no test): _operacion_sin_cambios, _operacion_que_cambia

---

## 📂 `memory/`

2 ficheros de test, 8 métodos de test.

<a name="memory/test-memory_save_entity_persist_bug"></a>
### `memory\test_memory_save_entity_persist_bug.py`

**Descripción:** Reproduccion del defecto D-ENTITIES-PERSIST-BUG (unidad 3.8.4.6.2).

**Módulos de origen probados:** src.memory.storage

**Clases de test:**

- **`TestDefectoDEntitiesPersistBug`** (línea 43) — 2 método(s) de test
  - save_entity debe conservar las entidades previas en disco y en cache.

  - **`test_save_entity_conserva_entidades_previas_en_disco`** (L46)

  - **`test_get_entity_recupera_todas_las_entidades_guardadas`** (L68)

---

<a name="memory/test-memory_entities_json_estado_inicial"></a>
### `memory\test_memory_entities_json_estado_inicial.py`

**Descripción:** Comprueba que un entities.json ausente, vacio o corrupto no se sobrescribe perdiendo entidades en silencio, definiendo y probando el contrato de rechazo: se crea cuando falta, se procede cuando esta vacio o es lista valida, y se rechaza (retorna False sin escribir) cuando esta corrupto o no es una lista.

**Módulos de origen probados:** src.memory.storage

**Clases de test:**

- **`TestContratoRechazoEstadoInicialEntitiesJson`** (línea 62) — 6 método(s) de test

  - **`test_crea_fichero_cuando_no_existe`** (L66)
  - **`test_sobre_fichero_vacio_no_pierde_datos`** (L78)
  - **`test_sobre_lista_vacia_preserva_y_anade`** (L92)
  - **`test_rechaza_fichero_corrupto_sin_sobreescribir`** (L106)
  - **`test_rechaza_fichero_json_no_lista_sin_sobreescribir`** (L125)
  - **`test_no_regresion_lista_valida_preserva_entidades_previas`** (L142)

---

## 📂 `utils/`

63 ficheros de test, 790 métodos de test.

<a name="utils/adaptive_learning_engine/test-adaptive_learning_engine_original"></a>
### `utils\adaptive_learning_engine\test_adaptive_learning_engine_original.py`

**Descripción:** Tests de AdaptiveLearningEngine (src/utils/adaptive_learning_engine.py).

**Clases de test:**

- **`TestLearningTask`** (línea 23) — 2 método(s) de test

  - **`test_valores`** (L24)

  - **`test_count`** (L34)

- **`TestNeuralArchitecture`** (línea 38) — 2 método(s) de test

  - **`test_valores`** (L39)

  - **`test_count`** (L48)

- **`TestLearningTaskConfig`** (línea 52) — 3 método(s) de test

  - **`test_campos_obligatorios`** (L53)

  - **`test_defaults`** (L65)

  - **`test_custom_values`** (L87)

- **`TestModelPerformance`** (línea 106) — 2 método(s) de test

  - **`test_defaults`** (L107)

  - **`test_custom_values`** (L127)

- **`TestAdaptiveLearningEngineInit`** (línea 140) — 8 método(s) de test

  - **`test_performance_optimizer_asignado`** (L150)

  - **`test_self_improvement_system_asignado`** (L153)

  - **`test_pattern_analyzer_asignado`** (L156)

  - **`test_analytics_asignado`** (L159)

  - **`test_config_tiene_claves`** (L162)

  - **`test_estado_inicial`** (L171)

  - **`test_model_registry_inicializado`** (L182)

  - **`test_knowledge_base_estructura`** (L187)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestGetLearningEngineStatus`** (línea 195) — 3 método(s) de test

  - **`test_status_contiene_claves`** (L205)

  - **`test_status_is_running_false`** (L218)

  - **`test_status_is_running_true`** (L223)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestAddLearningTask`** (línea 230) — 2 método(s) de test

  - **`test_add_task_to_queue`** (L239)

  - **`test_add_multiple_tasks`** (L250)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestGetModelInfo`** (línea 262) — 3 método(s) de test

  - **`test_model_not_found`** (L272)

  - **`test_sklearn_model_info`** (L276)

  - **`test_torch_model_info`** (L292)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestExportLearningReport`** (línea 304) — 1 método(s) de test

  - **`test_export_report`** (L314)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestStopStartLearningEngine`** (línea 333) — 2 método(s) de test

  - **`test_stop`** (L342)

  - **`test_start`** (L347)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestSafeFloat`** (línea 355) — 5 método(s) de test

  - **`test_safe_float_normal`** (L356)

  - **`test_safe_float_int`** (L359)

  - **`test_safe_float_none`** (L362)

  - **`test_safe_float_invalid`** (L365)

  - **`test_safe_float_custom_default`** (L368)

- **`TestCaptureFeedback`** (línea 372) — 4 método(s) de test

  - **`test_feedback_exitoso`** (L383)

  - **`test_feedback_error_sin_excepcion`** (L412)

  - **`test_feedback_non_dict`** (L418)

  - **`test_feedback_almacenado`** (L422)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestAnalyzeGoalLearningPatterns`** (línea 435) — 3 método(s) de test

  - **`test_analiza_patrones`** (L445)

  - **`test_empty_patterns`** (L457)

  - **`test_non_dict_pattern`** (L461)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestDescribeGoalLearningPattern`** (línea 466) — 2 método(s) de test

  - **`test_describe`** (L467)

  - **`test_describe_default_context`** (L473)

- **`TestCalculateGoalLearningConvergence`** (línea 479) — 4 método(s) de test

  - **`test_converged`** (L480)

  - **`test_no_verified`** (L487)

  - **`test_low_impact`** (L492)

  - **`test_zero_improvement`** (L497)

- **`TestExecuteLearningLoop`** (línea 504) — 3 método(s) de test

  - **`test_execute_con_feedback_exitoso`** (L514)

  - **`test_execute_con_feedback_fallido`** (L537)

  - **`test_execute_non_dict`** (L543)

  Métodos auxiliares (no test): setUpClass, tearDownClass

---

<a name="utils/adaptive_learning_engine/test-goal_adaptation_learning_loop"></a>
### `utils\adaptive_learning_engine\test_goal_adaptation_learning_loop.py`

**Descripción:** Test para el bucle de aprendizaje continuo de adaptación de Goal (2.8.8.8)

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-absent_storage_and_sections"></a>
### `utils\contextual_adaptation_engine\test_absent_storage_and_sections.py`

**Descripción:** Tests de ALMACENAMIENTO AUSENTE y SECCION AUSENTE del subsistema de persistencia
del motor de adaptacion contextual (2.8.8.9.5.4).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-adaptation_does_not_break_planner_executor"></a>
### `utils\contextual_adaptation_engine\test_adaptation_does_not_break_planner_executor.py`

**Descripción:** Tests para verificar que la adaptación contextual no rompe la integración con Planner y Executor.

**Módulos de origen probados:** src.hands.planner.node, src.hands.planner.planner, src.tools.executor, src.utils.contextual_adaptation_engine

**Clases de test:**

- **`TestAdaptationDoesNotBreakPlannerExecutor`** (línea 21) — 10 método(s) de test
  - Tests para verificar que la adaptación no rompe Planner/Executor

  - **`test_adapted_goal_can_be_validated`** (L58)
    - Test: El Goal adaptado puede ser validado exitosamente

  - **`test_adapted_goal_preserves_intention`** (L75)
    - Test: El Goal adaptado preserva la intención del original

  - **`test_adapted_goal_planner_can_solve`** (L90)
    - Test: El Planner puede generar un plan válido para el Goal adaptado

  - **`test_adapted_goal_executor_can_execute`** (L115)
    - Test: El Executor puede ejecutar el plan generado para el Goal adaptado

  - **`test_adaptation_does_not_introduce_errors`** (L140)
    - Test: La adaptación no introduce errores que rompan la integración

  - **`test_multiple_adaptations_do_not_break_integration`** (L160)
    - Test: Múltiples adaptaciones no rompen la integración

  - **`test_adaptation_with_different_goal_types`** (L205)
    - Test: Adaptación de diferentes tipos de Goals no rompe integración

  - **`test_adapted_goal_with_valid_constraints`** (L237)
    - Test: Goals adaptados con restricciones válidas no rompen integración

  - **`test_adapted_goal_with_high_priority`** (L270)
    - Test: Goals adaptados con prioridad alta no rompen integración

  - **`test_validation_result_is_registered`** (L296)
    - Test: El resultado de validación se registra correctamente

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-adapted_goal_validation"></a>
### `utils\contextual_adaptation_engine\test_adapted_goal_validation.py`

**Descripción:** Tests para la validación de Goal adaptado (2.8.8.5)

**Módulos de origen probados:** src.hands.planner.node, src.hands.planner.planner, src.utils.contextual_adaptation_engine

**Clases de test:**

- **`TestAdaptedGoalValidation`** (línea 16) — 13 método(s) de test
  - Tests para validación de Goal adaptado

  - **`test_validate_goal_structure_success`** (L49)
    - Test de validación de estructura de Goal exitoso

  - **`test_validate_goal_structure_missing_fields`** (L57)
    - Test de validación de Goal con campos faltantes

  - **`test_validate_current_state_success`** (L72)
    - Test de validación de State exitoso

  - **`test_validate_current_state_invalid_structure`** (L80)
    - Test de validación de State con estructura inválida

  - **`test_validate_capabilities_success`** (L89)
    - Test de validación de capacidades exitoso

  - **`test_validate_capabilities_missing`** (L101)
    - Test de validación de capacidades con capacidades faltantes

  - **`test_validate_goal_preconditions_navigate_success`** (L114)
    - Test de validación de precondiciones para navigate exitoso

  - **`test_validate_goal_preconditions_navigate_invalid_url`** (L126)
    - Test de validación de precondiciones para navigate con URL inválida

  - **`test_validate_planner_can_solve_success`** (L144)
    - Test de validación de Planner exitoso

  - **`test_validate_planner_can_solve_failure`** (L167)
    - Test de validación de Planner con fallo

  - **`test_validate_adapted_goal_complete_success`** (L189)
    - Test de validación completa de Goal adaptado exitoso

  - **`test_validate_adapted_goal_complete_failure`** (L206)
    - Test de validación completa de Goal adaptado con fallo

  - **`test_register_validation_result`** (L227)
    - Test de registro de resultado de validación

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-context_compatibility"></a>
### `utils\contextual_adaptation_engine\test_context_compatibility.py`

**Descripción:** Tests para Context Compatibility (2.8.5.3)
Verifica la compatibilidad entre contextos para transferencia de conocimiento

**Clases de test:**

- **`TestContextCompatibility`** (línea 18) — 5 método(s) de test
  - Tests para la compatibilidad entre contextos

  - **`test_2_8_5_3_1_reutilizar_validate_context_compatibility`** (L28)
    - 2.8.5.3.1 Reutilizar _validate_context_compatibility existente

  - **`test_2_8_5_3_2_verificar_umbrales_existentes`** (L49)
    - 2.8.5.3.2 Verificar umbrales existentes de compatibilidad

  - **`test_2_8_5_3_3_rechazar_transferencia_incompatible`** (L78)
    - 2.8.5.3.3 Rechazar transferencia incompatible

  - **`test_2_8_5_3_4_registrar_motivo`** (L103)
    - 2.8.5.3.4 Registrar motivo de rechazo o compatibilidad

  - **`test_2_8_5_3_5_tests`** (L126)
    - 2.8.5.3.5 Tests de compatibilidad integrados

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-context_model_origin_destination"></a>
### `utils\contextual_adaptation_engine\test_context_model_origin_destination.py`

**Descripción:** Tests para Context Model Origin/Destination (2.8.5.2)
Verifica el modelo de contexto origen/destino para transferencia de conocimiento

**Clases de test:**

- **`TestContextModelOriginDestination`** (línea 18) — 6 método(s) de test
  - Tests para el modelo de contexto origen/destino

  - **`test_2_8_5_2_1_identificar_contexto_origen`** (L28)
    - 2.8.5.2.1 Identificar contexto origen

  - **`test_2_8_5_2_2_identificar_contexto_destino`** (L61)
    - 2.8.5.2.2 Identificar contexto destino

  - **`test_2_8_5_2_3_verificar_datos_disponibles`** (L77)
    - 2.8.5.2.3 Verificar datos disponibles para contexto origen/destino

  - **`test_2_8_5_2_4_detectar_contexto_incompleto`** (L95)
    - 2.8.5.2.4 Detectar contexto incompleto

  - **`test_2_8_5_2_5_tests`** (L114)
    - 2.8.5.2.5 Tests de integración del modelo de contexto

  - **`test_context_snapshot_model`** (L167)
    - Test del modelo ContextSnapshot para representar estados

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-contextual_features_signals"></a>
### `utils\contextual_adaptation_engine\test_contextual_features_signals.py`

**Descripción:** Tests para 2.8.7.2 - Features/Señales
Verifica la representación de señales contextuales disponibles

**Clases de test:**

- **`TestFeaturesSignals`** (línea 25) — 5 método(s) de test
  - Tests para features/señales contextuales

  - **`test_2_8_7_2_1_enumerate_contextual_data`** (L68)
    - 2.8.7.2.1 - Enumerar datos contextuales disponibles

  - **`test_2_8_7_2_2_separate_real_signals_from_unavailable`** (L96)
    - 2.8.7.2.2 - Separar señales reales de campos no disponibles

  - **`test_2_8_7_2_3_build_minimal_representation`** (L145)
    - 2.8.7.2.3 - Construir representación mínima

  - **`test_2_8_7_2_4_handle_missing_signal`** (L169)
    - 2.8.7.2.4 - Manejar señal ausente

  - **`test_2_8_7_2_5_confidence_threshold_handling`** (L187)
    - Test adicional: manejar umbrales de confianza

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-corrupt_data"></a>
### `utils\contextual_adaptation_engine\test_corrupt_data.py`

**Descripción:** Test de DATOS CORRUPTOS (2.8.8.9.6.2).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-cross_context_confidence_feedback"></a>
### `utils\contextual_adaptation_engine\test_cross_context_confidence_feedback.py`

**Descripción:** Tests para 2.8.5.6 — CONFIDENCIA/FEEDBACK
Tests de confianza en transferencias de conocimiento y feedback

**Módulos de origen probados:** src.utils.contextual_adaptation_engine

**Clases de test:**

- **`TestTransferConfidence`** (línea 16) — 4 método(s) de test
  - Tests para obtener confianza en transferencias de conocimiento

  - **`test_get_transfer_confidence_basic`** (L24)
    - Test: Obtener confianza básica de una transferencia

  - **`test_get_transfer_confidence_with_result`** (L48)
    - Test: Obtener confianza con resultado de transferencia

  - **`test_get_transfer_confidence_nonexistent`** (L81)
    - Test: Obtener confianza de transferencia inexistente

  - **`test_get_transfer_confidence_zero_efficiency`** (L88)
    - Test: Obtener confianza con eficiencia cero

  Métodos auxiliares (no test): engine

- **`TestTransferFeedback`** (línea 105) — 4 método(s) de test
  - Tests para registrar feedback en transferencias de conocimiento

  - **`test_register_feedback_basic`** (L113)
    - Test: Registrar feedback básico en una transferencia

  - **`test_register_feedback_with_result`** (L145)
    - Test: Registrar feedback con resultado de aplicación

  - **`test_register_feedback_nonexistent`** (L183)
    - Test: Registrar feedback en transferencia inexistente

  - **`test_register_feedback_quality_update`** (L195)
    - Test: Actualizar calidad del conocimiento transferido

  Métodos auxiliares (no test): engine

- **`TestTransferResultEvaluation`** (línea 222) — 4 método(s) de test
  - Tests para evaluar resultados de transferencias de conocimiento

  - **`test_evaluate_transfer_result_success`** (L230)
    - Test: Evaluar resultado exitoso de transferencia

  - **`test_evaluate_transfer_result_partial`** (L264)
    - Test: Evaluar resultado parcial de transferencia

  - **`test_evaluate_transfer_result_failure`** (L296)
    - Test: Evaluar resultado fallido de transferencia

  - **`test_evaluate_transfer_result_nonexistent`** (L328)
    - Test: Evaluar resultado de transferencia inexistente

  Métodos auxiliares (no test): engine

- **`TestFeedbackIntegrationWithExistingMechanisms`** (línea 346) — 3 método(s) de test
  - Tests de integración de feedback con mecanismos existentes

  - **`test_feedback_updates_transfer_patterns`** (L354)
    - Test: Feedback exitoso actualiza patrones de transferencia

  - **`test_feedback_does_not_modify_critical_data`** (L388)
    - Test: Feedback no modifica datos críticos de la transferencia

  - **`test_confidence_calculation_uses_existing_mechanisms`** (L420)
    - Test: Cálculo de confianza usa mecanismos existentes

  Métodos auxiliares (no test): engine

---

<a name="utils/contextual_adaptation_engine/test-cross_context_knowledge_transfer"></a>
### `utils\contextual_adaptation_engine\test_cross_context_knowledge_transfer.py`

**Descripción:** Tests para Cross Context Knowledge Transfer (2.8.5)
Verifica las funciones de transferencia de conocimiento ya implementadas en ContextualAdaptationEngine

**Clases de test:**

- **`TestCrossContextKnowledgeTransfer`** (línea 18) — 26 método(s) de test
  - Tests para las funciones de transferencia de conocimiento entre contextos

  - **`test_2_8_5_1_1_localizar_cross_context_knowledge_transfer`** (L62)
    - 2.8.5.1.1 Verificar que no existe CrossContextKnowledgeTransfer separado

  - **`test_2_8_5_1_2_localizar_transfer_knowledge`** (L75)
    - 2.8.5.1.2 Verificar función transfer_knowledge existente

  - **`test_2_8_5_1_3_localizar_batch_knowledge_transfer`** (L90)
    - 2.8.5.1.3 Verificar función batch_knowledge_transfer existente

  - **`test_2_8_5_1_4_localizar_auto_transfer_knowledge`** (L108)
    - 2.8.5.1.4 Verificar función auto_transfer_knowledge existente

  - **`test_2_8_5_1_5_localizar_transfer_knowledge_with_feedback`** (L121)
    - 2.8.5.1.5 Verificar función transfer_knowledge_with_feedback existente

  - **`test_2_8_5_1_6_localizar_get_transfer_recommendations`** (L134)
    - 2.8.5.1.6 Verificar función get_transfer_recommendations existente

  - **`test_2_8_5_1_7_definir_que_parte_se_reutiliza`** (L146)
    - 2.8.5.1.7 Definir qué parte se reutiliza y evitar duplicación

  - **`test_2_8_5_1_8_evitar_duplicacion`** (L168)
    - 2.8.5.1.8 Evitar duplicación de funcionalidad existente

  - **`test_2_8_5_1_9_tests`** (L183)
    - 2.8.5.1.9 Tests de integración básica

  - **`test_2_8_5_2_1_identificar_contexto_origen`** (L219)
    - 2.8.5.2.1 Identificar contexto origen

  - **`test_2_8_5_2_2_identificar_contexto_destino`** (L233)
    - 2.8.5.2.2 Identificar contexto destino

  - **`test_2_8_5_2_3_verificar_datos_disponibles`** (L247)
    - 2.8.5.2.3 Verificar datos disponibles para transferencia

  - **`test_2_8_5_2_4_detectar_contexto_incompleto`** (L267)
    - 2.8.5.2.4 Detectar contexto incompleto

  - **`test_2_8_5_3_1_reutilizar_validate_context_compatibility`** (L291)
    - 2.8.5.3.1 Reutilizar _validate_context_compatibility existente

  - **`test_2_8_5_3_2_verificar_umbrales_existentes`** (L309)
    - 2.8.5.3.2 Verificar umbrales existentes

  - **`test_2_8_5_3_3_rechazar_transferencia_incompatible`** (L328)
    - 2.8.5.3.3 Rechazar transferencia incompatible

  - **`test_2_8_5_3_4_registrar_motivo`** (L343)
    - 2.8.5.3.4 Registrar motivo de rechazo

  - **`test_2_8_5_4_1_identificar_que_conocimiento_puede_transferirse`** (L361)
    - 2.8.5.4.1 Identificar qué conocimiento puede transferirse

  - **`test_2_8_5_4_2_separar_conocimiento_no_reutilizable`** (L375)
    - 2.8.5.4.2 Separar conocimiento de estado actual no reutilizable

  - **`test_2_8_5_4_3_extraer_usando_logica_existente`** (L393)
    - 2.8.5.4.3 Extraer usando lógica existente

  - **`test_2_8_5_4_4_transformar_usando_mecanismos_existentes`** (L411)
    - 2.8.5.4.4 Transformar usando mecanismos existentes

  - **`test_2_8_5_6_1_obtener_confianza_existente`** (L447)
    - 2.8.5.6.1 Obtener confianza existente

  - **`test_2_8_5_6_2_registrar_feedback`** (L474)
    - 2.8.5.6.2 Registrar feedback

  - **`test_2_8_5_6_3_evaluar_resultado`** (L504)
    - 2.8.5.6.3 Evaluar resultado

  - **`test_2_8_5_6_4_ajustar_confianza`** (L533)
    - 2.8.5.6.4 Ajustar confianza solo mediante mecanismo existente

  - **`test_2_8_5_6_5_tests`** (L566)
    - 2.8.5.6.5 Tests de integración de confianza/feedback

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-cross_context_units"></a>
### `utils\contextual_adaptation_engine\test_cross_context_units.py`

**Descripción:** Tests para Cross Context Knowledge Transfer - Unidades de Conocimiento (2.8.5.4)
Verifica la extracción, filtrado y transformación de unidades de conocimiento

**Clases de test:**

- **`TestCrossContextUnits`** (línea 18) — 5 método(s) de test
  - Tests para unidades de conocimiento en transferencia entre contextos

  - **`test_2_8_5_4_1_identificar_que_conocimiento_puede_transferirse`** (L68)
    - 2.8.5.4.1 Identificar qué conocimiento puede transferirse

  - **`test_2_8_5_4_2_separar_conocimiento_no_reutilizable`** (L84)
    - 2.8.5.4.2 Separar conocimiento de estado actual no reutilizable

  - **`test_2_8_5_4_3_extraer_usando_logica_existente`** (L99)
    - 2.8.5.4.3 Extraer conocimiento usando lógica existente

  - **`test_2_8_5_4_4_transformar_usando_mecanismos_existentes`** (L117)
    - 2.8.5.4.4 Transformar conocimiento usando mecanismos existentes

  - **`test_2_8_5_4_5_tests`** (L138)
    - 2.8.5.4.5 Tests de integración de unidades de conocimiento

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-direct"></a>
### `utils\contextual_adaptation_engine\test_direct.py`

**Descripción:** Test para verificar los métodos de la clase ContextualAdaptationEngine

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-evolutionary_strategy_optimizer"></a>
### `utils\contextual_adaptation_engine\test_evolutionary_strategy_optimizer.py`

**Descripción:** Tests para EvolutionaryStrategyOptimizer (2.8.6.1)
Verifica la integración de optimización evolutiva en ContextualAdaptationEngine existente

**Clases de test:**

- **`TestEvolutionaryStrategyOptimizer`** (línea 19) — 27 método(s) de test
  - Tests para la integración de optimización evolutiva

  - **`test_2_8_6_1_1_localizar_evolutionary_strategy_optimizer`** (L55)
    - 2.8.6.1.1 Verificar que no existe EvolutionaryStrategyOptimizer separado

  - **`test_2_8_6_1_2_identificar_representacion_estrategia_existente`** (L68)
    - 2.8.6.1.2 Identificar representación de estrategia existente

  - **`test_2_8_6_1_3_representar_estrategia_candidata`** (L86)
    - 2.8.6.1.3 Representar una estrategia candidata usando estructuras existentes

  - **`test_2_8_6_1_4_verificar_parametros_validos`** (L106)
    - 2.8.6.1.4 Verificar parámetros válidos usando validación existente

  - **`test_2_8_6_1_5_tests`** (L128)
    - 2.8.6.1.5 Tests de integración básica

  - **`test_2_8_6_2_1_identificar_estrategias_disponibles`** (L160)
    - 2.8.6.2.1 Identificar estrategias disponibles

  - **`test_2_8_6_2_2_generar_candidato_solo_mecanismos_soportados`** (L180)
    - 2.8.6.2.2 Generar candidato solo con mecanismos soportados

  - **`test_2_8_6_2_3_evitar_candidatos_identico`** (L206)
    - 2.8.6.2.3 Evitar candidatos idénticos

  - **`test_2_8_6_2_4_limitar_cantidad_si_existe_configuracion_limite`** (L230)
    - 2.8.6.2.4 Limitar cantidad si existe configuración/límite

  - **`test_2_8_6_2_5_tests`** (L255)
    - 2.8.6.2.5 Tests de integración

  - **`test_2_8_6_4_1_seleccionar_estrategia_valida`** (L284)
    - 2.8.6.4.1 Seleccionar estrategia válida según resultado medido

  - **`test_2_8_6_4_2_seleccionar_con_estrategia_actual`** (L323)
    - 2.8.6.4.2 Seleccionar estrategia comparando con estrategia actual

  - **`test_2_8_6_4_3_sin_mejora_significativa`** (L352)
    - 2.8.6.4.3 No cambiar cuando no hay mejora significativa

  - **`test_2_8_6_4_4_sin_estrategias_validas`** (L379)
    - 2.8.6.4.4 Manejar caso sin estrategias válidas

  - **`test_2_8_6_4_5_comparar_estrategias`** (L392)
    - 2.8.6.4.5 Comparar dos estrategias directamente

  - **`test_2_8_6_4_6_empate_en_comparacion`** (L416)
    - 2.8.6.4.6 Manejar empate en comparación de estrategias

  - **`test_2_8_6_5_1_aplicar_cambio_estrategia`** (L441)
    - 2.8.6.5.1 Aplicar un cambio de estrategia de forma controlada

  - **`test_2_8_6_5_2_verificar_comportamiento_posterior`** (L476)
    - 2.8.6.5.2 Verificar comportamiento posterior a la aplicación

  - **`test_2_8_6_5_3_revertir_cuando_exista_soporte_y_resultado_invalido`** (L530)
    - 2.8.6.5.3 Revertir cuando exista soporte y el resultado sea inválido

  - **`test_2_8_6_6_1_conectar_contextual_adaptation_engine`** (L603)
    - 2.8.6.6.1 Conectar ContextualAdaptationEngine

  - **`test_2_8_6_6_2_conectar_performance_optimizer_cuando_proceda`** (L642)
    - 2.8.6.6.2 Conectar PerformanceOptimizer cuando proceda

  - **`test_2_8_6_6_3_exponer_resultado_a_planner_executor_solo_mediante_contratos_existentes`** (L674)
    - 2.8.6.6.3 Exponer resultado a Planner/Executor solo mediante contratos existentes

  - **`test_2_8_6_6_4_tests`** (L730)
    - 2.8.6.6.4 Tests de integración

  - **`test_2_8_6_7_1_persistencia_y_estabilidad`** (L775)
    - 2.8.6.7.1 Persistir una evolución válida

  - **`test_2_8_6_7_2_evitar_oscilacion_entre_estrategias`** (L840)
    - 2.8.6.7.2 Evitar oscilación entre estrategias

  - **`test_2_8_6_7_3_registrar_cambios`** (L892)
    - 2.8.6.7.3 Registrar cambios

  - **`test_2_8_6_7_4_tests`** (L941)
    - 2.8.6.7.4 Tests de persistencia y estabilidad

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-final"></a>
### `utils\contextual_adaptation_engine\test_final.py`

**Descripción:** Test para verificar los métodos de la clase ContextualAdaptationEngine

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_condition_pattern_default"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_condition_pattern_default.py`

**Descripción:** Test del VALOR POR DEFECTO de `condition_pattern` (2.8.8.9.8.4.3).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_conservation"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_conservation.py`

**Descripción:** Test de conservacion (2.8.8.9.11.5): verificar que no se eliminan datos
validos prematuramente.

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_corrupted_list_section"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_corrupted_list_section.py`

**Descripción:** Test de la SECCION LISTA corrupta de la base de conocimiento (2.8.8.9.8.4.1).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_evidence_insufficient"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_evidence_insufficient.py`

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_evidence_valid"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_evidence_valid.py`

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_fabricated_identity"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_fabricated_identity.py`

**Descripción:** Test de la IDENTIDAD INVENTADA y de la COLISION de identidad (2.8.8.9.8.4.2).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_feedback"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_feedback.py`

**Descripción:** Test para el método de feedback de adaptación de Goal (2.8.8.7)

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_feedback_persistence"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_feedback_persistence.py`

**Descripción:** Test de persistencia de feedback de adaptación de Goal (2.8.8.9.2.2)

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_forgetting"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_forgetting.py`

**Descripción:** Test de olvido (2.8.8.9.11.4): verificar eliminación/expiración correcta.

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_learned_strategy_persistence"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_learned_strategy_persistence.py`

**Descripción:** Test de persistencia de estrategias aprendidas de Goal (2.8.8.9.3.2).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_pattern_load"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_pattern_load.py`

**Descripción:** Test de carga de patrones de aprendizaje (2.8.8.9.4.4).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_pattern_persistence"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_pattern_persistence.py`

**Descripción:** Test de persistencia de patrones de aprendizaje (2.8.8.9.4.2).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_pattern_restart_verification"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_pattern_restart_verification.py`

**Descripción:** Verificacion de los patrones recuperados tras el reinicio (2.8.8.9.4.5).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_persistence_real"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_persistence_real.py`

**Descripción:** Test real de persistencia de feedback de adaptación de Goal (2.8.8.9.2.3)

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_persistence_simple"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_persistence_simple.py`

**Descripción:** Test simple de persistencia de feedback de adaptación de Goal (2.8.8.9.2.3)

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_production_data_clean"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_production_data_clean.py`

**Descripción:** Guarda de integridad de los ficheros de persistencia de Goal en `data/` (2.8.8.9.4.6).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_proposal"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_proposal.py`

**Descripción:** Tests unitarios para la propuesta de adaptación de Goal (2.8.8.4)

**Módulos de origen probados:** src.hands.planner.node, src.utils.contextual_adaptation_engine

**Clases de test:**

- **`TestGoalAdaptationProposal`** (línea 27) — 11 método(s) de test
  - Tests para propuesta de adaptación de Goal

  - **`test_create_goal_adaptation_proposal_basic`** (L86)
    - Test básico de creación de propuesta de adaptación

  - **`test_create_goal_adaptation_proposal_with_adaptation`** (L115)
    - Test de creación de propuesta con Goal adaptado

  - **`test_create_goal_adaptation_proposal_no_rules`** (L137)
    - Test de creación de propuesta sin reglas aplicables

  - **`test_validate_adaptation_constraints`** (L154)
    - Test de validación de restricciones

  - **`test_check_intention_preservation`** (L172)
    - Test de verificación de preservación de intención

  - **`test_are_constraints_contradictory`** (L197)
    - Test de detección de restricciones contradictorias

  - **`test_proposal_registration`** (L211)
    - Test de registro de propuestas

  - **`test_priority_validation`** (L228)
    - Test de validación de prioridad

  - **`test_deadline_validation`** (L246)
    - Test de validación de deadline

  - **`test_navigation_integrity_preservation`** (L265)
    - Test de preservación de integridad en navegación

  - **`test_application_integrity_preservation`** (L298)
    - Test de preservación de integridad en aplicaciones

  Métodos auxiliares (no test): setUp, tearDown

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_recoverable"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_recoverable.py`

**Descripción:** Test de los DATOS RECUPERABLES (2.8.8.9.7.1).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_recovery_partial"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_recovery_partial.py`

**Descripción:** Test de la RECUPERACIÓN PARCIAL (2.8.8.9.7.2).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_rejection_runtime"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_rejection_runtime.py`

**Descripción:** Test del RECHAZO EN RUNTIME de la corrupcion (2.8.8.9.6.4).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_representation"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_representation.py`

**Descripción:** Tests unitarios para la representación de adaptación de Goal (2.8.8.2)

**Módulos de origen probados:** src.hands.planner.node, src.utils.contextual_adaptation_engine

**Clases de test:**

- **`TestGoalAdaptationRepresentation`** (línea 26) — 8 método(s) de test
  - Tests para representación de adaptación de Goal

  - **`test_represent_adaptation_no_rules`** (L60)
    - Test: Sin reglas aplicables, no debe haber adaptación

  - **`test_represent_adaptation_priority_change`** (L70)
    - Test: Cambio de prioridad basado en regla

  - **`test_represent_adaptation_constraints_addition`** (L93)
    - Test: Adición de restricciones

  - **`test_represent_adaptation_metadata_update`** (L119)
    - Test: Actualización de metadata

  - **`test_represent_adaptation_deadline_addition`** (L145)
    - Test: Añadir deadline

  - **`test_represent_adaptation_multiple_rules`** (L171)
    - Test: Aplicación de múltiples reglas

  - **`test_represent_adaptation_preserve_original`** (L223)
    - Test: El Goal original no debe modificarse

  - **`test_represent_adaptation_trazabilidad`** (L252)
    - Test: Trazabilidad de la adaptación

  Métodos auxiliares (no test): setUp

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_restart_compatibility"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_restart_compatibility.py`

**Descripción:** Verificacion de compatibilidad tras reinicio (2.8.12.5).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_strategy_persistence"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_strategy_persistence.py`

**Descripción:** Test de persistencia de estrategias aprendidas de Goal (2.8.8.9.2.6).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_strategy_restart_verification"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_strategy_restart_verification.py`

**Descripción:** Verificacion de la estrategia recuperada tras el reinicio (2.8.8.9.3.5).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_total_corruption"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_total_corruption.py`

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_total_loss_fallback"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_total_loss_fallback.py`

**Descripción:** Test del FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.1).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-goal_adaptation_total_loss_fallback_implemented"></a>
### `utils\contextual_adaptation_engine\test_goal_adaptation_total_loss_fallback_implemented.py`

**Descripción:** Test de la IMPLEMENTACION del FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.2).

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-load_goal_adaptation_feedback"></a>
### `utils\contextual_adaptation_engine\test_load_goal_adaptation_feedback.py`

**Descripción:** Test de carga de feedback acumulado de adaptación de Goal (2.8.8.9.2.4 / 2.8.8.9.2.5)

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-simple"></a>
### `utils\contextual_adaptation_engine\test_simple.py`

**Descripción:** Test simple para verificar los métodos de estrategia

*Sin clases de test definidas.*

---

<a name="utils/contextual_adaptation_engine/test-transfer_recommendations"></a>
### `utils\contextual_adaptation_engine\test_transfer_recommendations.py`

**Descripción:** Tests para 2.8.5.7 — RECOMENDACIONES

**Clases de test:**

- **`Test2_8_5_7_Recommendations`** (línea 19) — 9 método(s) de test
  - Tests para la unidad 2.8.5.7 - RECOMENDACIONES

  - **`test_2_8_5_7_1_generar_recomendacion_usando_datos_existentes`** (L30)
    - 2.8.5.7.1 Generar recomendación usando datos existentes

  - **`test_2_8_5_7_2_verificar_compatibilidad`** (L70)
    - 2.8.5.7.2 Verificar compatibilidad

  - **`test_2_8_5_7_3_evitar_recomendar_transferencias_no_ejecutables`** (L88)
    - 2.8.5.7.3 Evitar recomendar transferencias no ejecutables

  - **`test_2_8_5_7_4_integrar_con_contextual_adaptation_engine`** (L108)
    - 2.8.5.7.4 Integrar con ContextualAdaptationEngine

  - **`test_2_8_5_7_5_ordenacion_por_prioridad`** (L132)
    - 2.8.5.7.5 Verificar que las recomendaciones están ordenadas por prioridad

  - **`test_2_8_5_7_6_limitar_numero_de_recomendaciones`** (L145)
    - 2.8.5.7.6 Verificar que se respeta el límite de recomendaciones

  - **`test_2_8_5_7_7_tipos_de_conocimiento_evaluados`** (L155)
    - 2.8.5.7.7 Verificar que se evalúan los tipos de conocimiento correctos

  - **`test_2_8_5_7_8_manejo_de_errores`** (L169)
    - 2.8.5.7.8 Verificar manejo de errores

  - **`test_2_8_5_7_9_confianza_y_razonamiento`** (L183)
    - 2.8.5.7.9 Verificar que la confianza y razonamiento son consistentes

  Métodos auxiliares (no test): setUp

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_allocate"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_allocate.py`

**Descripción:** Tests de asignacion compleja: conflictos, defusion y preemption.

**Clases de test:**

- **`TestAllocateConflicts`** (línea 27) — 2 método(s) de test
  - 2.8.4.3 — Conflictos de asignacion

  - **`test_2_8_4_3_2_conflict_identical_context`** (L40)
    - allocate rechaza solicitud con contexto idéntico (required=True)

  - **`test_2_8_4_3_2_conflict_shared_keys_different_values`** (L67)
    - allocate rechaza solicitud con claves compartidas y valores diferentes

  Métodos auxiliares (no test): setUp

- **`TestAllocatePreemption`** (línea 90) — 5 método(s) de test
  - 2.8.4.5.2 — Preempt por prioridad

  - **`test_2_8_4_5_2_preempt_critical`** (L117)
    - allocate preempta si la nueva solicitud es CRITICAL

  - **`test_2_8_4_5_2_preempt_mayor_prioridad_no_user`** (L133)
    - allocate preempta si existente no es user work y prioridad es mayor

  - **`test_2_8_4_5_2_preempt_consentimiento`** (L148)
    - allocate preempta si nueva solicitud tiene preempt_consent en contexto

  - **`test_2_8_4_5_2_no_preempt_user_work`** (L164)
    - allocate NO preempta si existente es user work y nueva no es CRITICAL

  - **`test_2_8_4_5_2_no_preempt_prioridad_igual`** (L181)
    - allocate NO preempta si la prioridad es igual (no estrictamente mayor)

  Métodos auxiliares (no test): setUp, _allocate_and_set_in_use

- **`TestAllocateDeferred`** (línea 197) — 5 método(s) de test
  - 2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso

  - **`test_2_8_4_5_3_defer_no_required_recurso_no_disponible`** (L210)
    - allocate difiere solicitud cuando required=False y recurso no disponible

  - **`test_2_8_4_5_3_defer_no_required_cantidad_insuficiente`** (L231)
    - allocate difiere solicitud cuando required=False y cantidad insuficiente

  - **`test_2_8_4_5_3_reject_required_recurso_no_disponible`** (L243)
    - allocate rechaza solicitud cuando required=True y recurso no disponible

  - **`test_2_8_4_5_3_reject_required_cantidad_insuficiente`** (L262)
    - allocate rechaza solicitud cuando required=True y cantidad insuficiente

  - **`test_2_8_4_3_3_defer_almacena_metadata`** (L274)
    - defer_request almacena defer_id en metadata del request

  Métodos auxiliares (no test): setUp

- **`TestAllocateInvalidRequest`** (línea 287) — 1 método(s) de test
  - allocate con solicitudes invalidas

  - **`test_2_8_4_3_4_allocate_solicitud_invalida`** (L293)
    - allocate retorna None para una solicitud invalida (resource_type=None)

  Métodos auxiliares (no test): setUp

- **`TestOnAllocationChangedCallback`** (línea 305) — 2 método(s) de test
  - Verificacion del callback on_allocation_changed en varios flujos

  - **`test_2_8_4_3_5_callback_no_registrado_no_lanza`** (L318)
    - allocate funciona sin on_allocation_changed registrado

  - **`test_2_8_4_3_5_callback_debe_ser_callable`** (L328)
    - on_allocation_changed debe ser None por defecto

  Métodos auxiliares (no test): setUp

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_allocate_simple"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_allocate_simple.py`

**Descripción:** Tests del modelo de solicitud (ResourceRequest) y asignacion simple.

**Clases de test:**

- **`TestResourceRequestDataclass`** (línea 24) — 3 método(s) de test
  - 2.8.4.2 — ResourceRequest es el modelo de solicitud

  - **`test_2_8_4_2_1_request_campos`** (L27)
    - ResourceRequest tiene los campos esperados

  - **`test_2_8_4_2_1_request_defaults`** (L46)
    - ResourceRequest tiene valores por defecto

  - **`test_2_8_4_2_1_request_to_dict`** (L59)
    - ResourceRequest.to_dict serializa todos los campos

- **`TestResourceRequestValidate`** (línea 78) — 7 método(s) de test
  - 2.8.4.2.5 — Validar solicitud

  - **`test_2_8_4_2_2_validate_valida`** (L81)
    - validate retorna (True, []) para una solicitud correcta

  - **`test_2_8_4_2_2_validate_sin_resource_type`** (L92)
    - validate retorna (False, [errors]) si resource_type es None

  - **`test_2_8_4_2_2_validate_request_id_vacio`** (L103)
    - validate retorna (False, [errors]) si request_id es None

  - **`test_2_8_4_2_2_validate_amount_negativo`** (L114)
    - validate retorna (False, [errors]) si amount es negativo

  - **`test_2_8_4_2_2_validate_amount_cero_valido`** (L125)
    - amount=0 es valido (solo < 0 es invalido)

  - **`test_2_8_4_2_2_validate_amount_none_valido`** (L135)
    - amount=None es valido

  - **`test_2_8_4_2_2_validate_priority_invalida`** (L145)
    - validate retorna (False, [errors]) si priority no es ResourcePriority

- **`TestCreateRequest`** (línea 158) — 4 método(s) de test
  - 2.8.4.2 — create_request construye un ResourceRequest

  - **`test_2_8_4_2_3_create_request`** (L164)
    - create_request genera un ResourceRequest con todos los campos

  - **`test_2_8_4_2_3_create_request_defaults`** (L183)
    - create_request usa valores por defecto si no se especifican

  - **`test_2_8_4_2_3_create_request_id_unico`** (L194)
    - create_request mantiene IDs unicos al pasar request_id explicito

  - **`test_2_8_4_2_3_create_request_invalido_lanza`** (L210)
    - create_request levanta ValueError para una solicitud invalida

  Métodos auxiliares (no test): setUp

- **`TestAllocateSimple`** (línea 220) — 8 método(s) de test
  - 2.8.4.3 — Asignar (camino basico sin conflictos)

  - **`test_2_8_4_3_1_allocate_exitoso`** (L233)
    - allocate asigna correctamente un recurso disponible

  - **`test_2_8_4_3_1_allocate_deduce_disponibilidad`** (L248)
    - allocate reduce la cantidad disponible tras la asignacion

  - **`test_2_8_4_3_1_allocate_registra_en_allocations`** (L259)
    - allocate registra la asignacion en el dict allocations

  - **`test_2_8_4_3_1_allocate_callback_on_changed`** (L269)
    - allocate llama a on_allocation_changed con (allocation_id, allocation)

  - **`test_2_8_4_3_1_allocate_sin_amount`** (L284)
    - allocate funciona con amount=None (solo marca disponible True)

  - **`test_2_8_4_3_1_allocate_recurso_no_registrado`** (L295)
    - allocate retorna None si el recurso no esta registrado

  - **`test_2_8_4_3_1_allocate_cantidad_insuficiente`** (L305)
    - allocate retorna None si la cantidad solicitada excede la disponible

  - **`test_2_8_4_3_1_allocate_recurso_no_disponible`** (L315)
    - allocate retorna None si el recurso esta marcado como no disponible

  Métodos auxiliares (no test): setUp

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_allocation"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_allocation.py`

**Descripción:** Tests del modelo de asignacion (ResourceAllocation) y contexto.

**Clases de test:**

- **`TestResourceAllocationDataclass`** (línea 27) — 5 método(s) de test
  - 2.8.4.2 — ResourceAllocation es el modelo de asignacion

  - **`test_2_8_4_2_4_allocation_campos`** (L30)
    - ResourceAllocation tiene los campos esperados

  - **`test_2_8_4_2_4_allocation_defaults`** (L53)
    - ResourceAllocation tiene valores por defecto

  - **`test_2_8_4_2_4_allocation_assigned_at_default`** (L68)
    - ResourceAllocation asigna assigned_at por defecto a datetime.now()

  - **`test_2_8_4_2_4_allocation_to_dict`** (L81)
    - ResourceAllocation.to_dict serializa y convierte enums a valores

  - **`test_2_8_4_2_4_allocation_to_dict_released`** (L104)
    - to_dict incluye released_at cuando se libera

- **`TestGetAllocation`** (línea 118) — 3 método(s) de test
  - Obtener asignaciones

  - **`test_2_8_4_2_5_get_allocation_existente`** (L137)
    - get_allocation retorna la asignacion por ID

  - **`test_2_8_4_2_5_get_allocation_no_existente`** (L142)
    - get_allocation retorna None para un ID inexistente

  - **`test_2_8_4_2_5_get_all_allocations`** (L146)
    - get_all_allocations retorna todas las asignaciones

  Métodos auxiliares (no test): setUp

- **`TestConnectContext`** (línea 153) — 5 método(s) de test
  - 2.8.4.6 — Contexto: connect_context

  - **`test_2_8_4_6_1_connect_context_valido`** (L159)
    - connect_context almacena el contexto y retorna True

  - **`test_2_8_4_6_1_connect_context_none`** (L166)
    - connect_context rechaza None y retorna False

  - **`test_2_8_4_6_1_connect_context_no_dict`** (L171)
    - connect_context rechaza tipos no dict y retorna False

  - **`test_2_8_4_6_1_connect_context_vacio`** (L178)
    - connect_context acepta un dict vacio

  - **`test_2_8_4_6_1_connect_context_reemplaza`** (L184)
    - connect_context reemplaza el contexto anterior

  Métodos auxiliares (no test): setUp

- **`TestAdjustAllocationForContext`** (línea 192) — 6 método(s) de test
  - 2.8.4.6.2 — Ajustar asignacion usando datos disponibles

  - **`test_2_8_4_6_2_ajustar_con_datos_disponibles`** (L212)
    - adjust_allocation_for_context actualiza claves presentes en el contexto

  - **`test_2_8_4_6_2_ajustar_sin_cambios`** (L222)
    - adjust_allocation_for_context retorna False si los valores coinciden

  - **`test_2_8_4_6_2_ajustar_asignacion_no_existente`** (L228)
    - adjust_allocation_for_context retorna False para asignacion inexistente

  - **`test_2_8_4_6_2_ajustar_sin_contexto_global`** (L234)
    - adjust_allocation_for_context retorna False si no hay contexto global conectado

  - **`test_2_8_4_6_2_ajustar_sin_contexto_asignacion`** (L239)
    - adjust_allocation_for_context retorna False si la asignacion tiene contexto vacio

  - **`test_2_8_4_6_2_ajustar_notifica_cambio`** (L262)
    - adjust_allocation_for_context llama on_allocation_changed cuando hay ajuste

  Métodos auxiliares (no test): setUp

- **`TestAdjustAllAllocationsForContext`** (línea 271) — 2 método(s) de test
  - 2.8.4.6.2 — Ajustar todas las asignaciones

  - **`test_2_8_4_6_2_adjust_all_vacio`** (L291)
    - adjust_all_allocations_for_context retorna {} cuando no hay asignaciones

  - **`test_2_8_4_6_2_adjust_all_con_cambios`** (L296)
    - adjust_all_allocations_for_context ajusta asignaciones afectadas

  Métodos auxiliares (no test): setUp

- **`TestRecalculateOnContextChange`** (línea 305) — 4 método(s) de test
  - 2.8.4.6.3 — Recalcular cuando el contexto cambie

  - **`test_2_8_4_6_3_recalculate_cambio_claves`** (L325)
    - recalculate_on_context_change detecta claves cambiadas

  - **`test_2_8_4_6_3_recalculate_sin_cambios`** (L334)
    - recalculate_on_context_change con contexto idéntico: changed_keys vacia

  - **`test_2_8_4_6_3_recalculate_no_dict`** (L344)
    - recalculate_on_context_change rechaza contexto no dict

  - **`test_2_8_4_6_3_recalculate_actualiza_recursos_sistema`** (L351)
    - recalculate_on_context_change llama update_system_resources para claves de sistema

  Métodos auxiliares (no test): setUp

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_integration"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_integration.py`

**Descripción:** Tests de integración para DynamicResourceAllocator 2.8.4.7

**Clases de test:**

- **`TestDynamicResourceAllocatorIntegration`** (línea 26) — 4 método(s) de test
  - Tests de integración para DynamicResourceAllocator

  - **`test_2_8_4_7_1_connect_contextual_adaptation_engine`** (L39)
    - 2.8.4.7.1 — Conectar ContextualAdaptationEngine

Verificar que el DynamicResourceAllocator puede conectarse y usar
el ContextualAdaptationEngine.

  - **`test_2_8_4_7_2_connect_performance_optimizer`** (L92)
    - 2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda

Verificar que el DynamicResourceAllocator puede conectarse y usar
el PerformanceOptimizer.

  - **`test_2_8_4_7_3_expose_result_to_planner_executor`** (L147)
    - 2.8.4.7.3 — Exponer resultado a Planner/Executor solo mediante contratos existentes

Verificar que el estado de recursos se expone en formato compatible
con contratos existentes del Planner/Executor.

  - **`test_2_8_4_7_4_integration_workflow`** (L222)
    - Test del flujo de integración completo

Verificar el flujo completo de integración entre todos los componentes.

  Métodos auxiliares (no test): setUp

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_inventory"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_inventory.py`

**Descripción:** Tests de inventario y modelo para DynamicResourceAllocator 2.8.4.1.

**Clases de test:**

- **`TestResourceTypeEnum`** (línea 25) — 2 método(s) de test
  - 2.8.4.1 — Tipos de recursos gestionables

  - **`test_2_8_4_1_1_resource_type_valores`** (L28)
    - Verificar valores del enum ResourceType

  - **`test_2_8_4_1_1_resource_type_cuantos`** (L43)
    - Verificar que hay 11 tipos de recursos

- **`TestResourcePriorityEnum`** (línea 49) — 1 método(s) de test
  - 2.8.4.2.3 — Prioridades

  - **`test_2_8_4_1_2_resource_priority_valores`** (L52)
    - Verificar valores del enum ResourcePriority

- **`TestAllocationStatusEnum`** (línea 60) — 1 método(s) de test
  - Estados de asignacion

  - **`test_2_8_4_1_3_allocation_status_valores`** (L63)
    - Verificar valores del enum AllocationStatus

- **`TestResourceAvailability`** (línea 73) — 5 método(s) de test
  - 2.8.4.2.5 — Validar solicitud / disponibilidad

  - **`test_2_8_4_1_4_can_satisfy_disponible_sin_limites`** (L76)
    - can_satisfy retorna True cuando no hay limites conocidos

  - **`test_2_8_4_1_4_can_satisfy_disponible_con_amount_none`** (L86)
    - can_satisfy retorna True cuando el amount solicitado es None

  - **`test_2_8_4_1_4_can_satisfy_cantidad_suficiente`** (L96)
    - can_satisfy retorna True cuando la cantidad disponible es suficiente

  - **`test_2_8_4_1_4_can_satisfy_cantidad_insuficiente`** (L106)
    - can_satisfy retorna False cuando la cantidad es insuficiente

  - **`test_2_8_4_1_4_can_satisfy_no_disponible`** (L116)
    - can_satisfy retorna False cuando el recurso no esta disponible

- **`TestRegisterResource`** (línea 127) — 4 método(s) de test
  - 2.8.4.1 — Registrar recursos

  - **`test_2_8_4_1_5_register_resource_crea_availability`** (L133)
    - register_resource crea un ResourceAvailability

  - **`test_2_8_4_1_5_register_resource_unidad_no_disponible`** (L149)
    - register_resource puede marcar un recurso como no disponible

  - **`test_2_8_4_1_5_get_availability_no_registrado`** (L162)
    - get_availability retorna None para recurso no registrado

  - **`test_2_8_4_1_5_get_availability_default_cpu`** (L167)
    - get_availability retorna datos para recursos ya registrados tras init

  Métodos auxiliares (no test): setUp

- **`TestUpdateSystemResources`** (línea 177) — 5 método(s) de test
  - 2.8.4.1.2 — Identificar como se mide disponibilidad

  - **`test_2_8_4_1_6_update_system_resources_sin_error`** (L183)
    - update_system_resources no lanza error si no hay metricas

  - **`test_2_8_4_1_6_update_system_resources_con_metricas`** (L189)
    - update_system_resources registra CPU, memoria, disco, red con metricas simuladas

  - **`test_2_8_4_1_6_update_execution_resources`** (L219)
    - update_execution_resources registra EXECUTION_REGISTRY y EXECUTION_HISTORY

  - **`test_2_8_4_1_6_update_thread_pool_resources`** (L233)
    - update_thread_pool_resources registra THREAD_POOL con workers disponibles

  - **`test_2_8_4_1_6_update_storage_resources`** (L243)
    - update_storage_resources registra STORAGE_DATABASE y STORAGE_CACHE

  Métodos auxiliares (no test): setUp

- **`TestDynamicResourceAllocatorInit`** (línea 258) — 4 método(s) de test
  - Verificacion del estado inicial del allocador

  - **`test_2_8_4_1_7_init_estado_inicial`** (L261)
    - El allocador inicia con allocations vacias, locks y contextos vacios

  - **`test_2_8_4_1_7_init_monitor_asignado`** (L271)
    - El allocador tiene un PerformanceMonitor asignado

  - **`test_2_8_4_1_7_init_optimizer_asignado`** (L276)
    - El allocador tiene un PerformanceOptimizer asignado (por defecto o pasado)

  - **`test_2_8_4_1_7_init_lock_es_rlock`** (L281)
    - El lock usado es un RLock (permitido reentrar)

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_priority_conflicts"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_priority_conflicts.py`

**Descripción:** Tests de prioridad y conflictos.

**Clases de test:**

- **`TestContextsConflict`** (línea 27) — 6 método(s) de test
  - 2.8.4.5.1 — _contexts_conflict

  - **`test_2_8_4_5_1_conflict_identico`** (L33)
    - Contextos idénticos → conflicto

  - **`test_2_8_4_5_1_conflict_clave_compartida_valor_diferente`** (L39)
    - Claves compartidas con valores diferentes → conflicto

  - **`test_2_8_4_5_1_no_conflict_claves_disjuntas`** (L45)
    - Claves disjuntas → sin conflicto

  - **`test_2_8_4_5_1_no_conflict_valores_iguales_clave_compartida`** (L51)
    - Clave compartida con mismo valor → no conflicto

  - **`test_2_8_4_5_1_no_conflict_contexto_vacio`** (L57)
    - Contexto vacio → sin conflicto

  - **`test_2_8_4_5_1_no_conflict_ambos_none`** (L64)
    - Ambos contextos None → sin conflicto

  Métodos auxiliares (no test): setUp

- **`TestHasConflict`** (línea 70) — 4 método(s) de test
  - 2.8.4.5.1 — _has_conflict

  - **`test_2_8_4_5_1_1_conflict_in_use_mismo_contexto`** (L95)
    - _has_conflict retorna True si hay asignacion IN_USE con contexto conflictivo

  - **`test_2_8_4_5_1_1_no_conflict_assigned`** (L106)
    - _has_conflict retorna False si la asignacion esta en ASSIGNED (no IN_USE)

  - **`test_2_8_4_5_1_1_no_conflict_diferente_recurso`** (L117)
    - _has_conflict retorna False si el recurso es diferente

  - **`test_2_8_4_5_1_1_no_conflict_contexto_no_conflictivo`** (L128)
    - _has_conflict retorna False si el contexto no entra en conflicto

  Métodos auxiliares (no test): setUp, _make_allocation

- **`TestGetConflicts`** (línea 141) — 3 método(s) de test
  - 2.8.4.5.1 — get_conflicts

  - **`test_2_8_4_5_1_2_conflict_vacio`** (L154)
    - get_conflicts retorna lista vacia sin asignaciones

  - **`test_2_8_4_5_1_2_conflict_encontrado`** (L164)
    - get_conflicts retorna tuplas (alloc_id, allocation) de conflictos

  - **`test_2_8_4_5_1_2_conflict_multiples`** (L187)
    - get_conflicts encuentra multiples asignaciones en conflicto

  Métodos auxiliares (no test): setUp

- **`TestIsUserWork`** (línea 211) — 6 método(s) de test
  - 2.8.4.5.4 — _is_user_work

  - **`test_2_8_4_5_4_user_context_key`** (L225)
    - _is_user_work True si el contexto tiene clave 'user'

  - **`test_2_8_4_5_4_user_type_key`** (L230)
    - _is_user_work True si el contexto tiene 'type'='user'

  - **`test_2_8_4_5_4_user_source_key`** (L235)
    - _is_user_work True si el contexto tiene 'source'='user'

  - **`test_2_8_4_5_4_interactive_key`** (L240)
    - _is_user_work True si el contexto tiene 'interactive'=True

  - **`test_2_8_4_5_4_no_user_work`** (L245)
    - _is_user_work False para contextos sin indicadores de usuario

  - **`test_2_8_4_5_4_contexto_vacio`** (L250)
    - _is_user_work False para contexto vacio

  Métodos auxiliares (no test): setUp, _make_alloc

- **`TestCanPreempt`** (línea 256) — 7 método(s) de test
  - 2.8.4.5.4 — _can_preempt

  - **`test_2_8_4_5_2_1_critical_puede_preemptar`** (L283)
    - CRITICAL puede preemptar cualquier asignacion

  - **`test_2_8_4_5_2_1_preempt_consent_puede_preemptar`** (L289)
    - preempt_consent=True en el contexto puede preemptar

  - **`test_2_8_4_5_2_1_mayor_prioridad_no_user`** (L295)
    - Mayor prioridad sobre no-user work puede preemptar

  - **`test_2_8_4_5_2_1_igual_prioridad_no_preempta`** (L301)
    - Igual prioridad sobre no-user work no puede preemptar

  - **`test_2_8_4_5_2_1_menor_prioridad_no_preempta`** (L307)
    - Menor prioridad sobre no-user work no puede preemptar

  - **`test_2_8_4_5_2_1_user_work_no_preempta_sin_critical`** (L313)
    - User work no puede preemptar con prioridad alta (solo CRITICAL)

  - **`test_2_8_4_5_2_1_user_work_no_preempta_sin_consent`** (L319)
    - User work no puede preemptar con preempt_consent=False

  Métodos auxiliares (no test): setUp, _make_alloc, _make_request

- **`TestTryPreempt`** (línea 332) — 2 método(s) de test
  - 2.8.4.5.2 — _try_preempt

  - **`test_2_8_4_5_2_2_try_preempt_exitoso`** (L345)
    - _try_preempt retorna True y libera la asignacion cuando se puede preemptar

  - **`test_2_8_4_5_2_2_try_preempt_fracaso`** (L372)
    - _try_preempt retorna False cuando no se puede preemptar

  Métodos auxiliares (no test): setUp

- **`TestDeferRequest`** (línea 400) — 2 método(s) de test
  - 2.8.4.5.3 — defer_request

  - **`test_2_8_4_5_3_1_defer_request_retorna_id`** (L413)
    - defer_request retorna un string con prefijo defer_

  - **`test_2_8_4_5_3_1_defer_request_almacena_pending`** (L426)
    - defer_request almacena la solicitud en pending_requests

  Métodos auxiliares (no test): setUp

- **`TestGetPendingRequests`** (línea 438) — 2 método(s) de test
  - 2.8.4.5.3 — get_pending_requests

  - **`test_2_8_4_5_3_2_pending_vacio`** (L444)
    - get_pending_requests retorna lista vacia sin deferidos

  - **`test_2_8_4_5_3_2_pending_con_solicitudes`** (L448)
    - get_pending_requests retorna copia de las solicitudes diferidas

  Métodos auxiliares (no test): setUp

- **`TestProcessDeferred`** (línea 468) — 3 método(s) de test
  - 2.8.4.5.3 — process_deferred

  - **`test_2_8_4_5_3_3_process_deferred_asigna_exitosa`** (L481)
    - process_deferred asigna solicitudes deferidas cuando hay disponibilidad

  - **`test_2_8_4_5_3_3_process_deferred_mantiene_fallidas`** (L499)
    - process_deferred mantiene en pending las que no se pueden asignar

  - **`test_2_8_4_5_3_3_process_deferred_prioridad_descendente`** (L514)
    - process_deferred procesa en orden de prioridad descendente

  Métodos auxiliares (no test): setUp

- **`TestAllocateDirect`** (línea 537) — 4 método(s) de test
  - _allocate_direct — asignacion directa para procesamiento diferido

  - **`test_2_8_4_5_5_allocate_direct_exitoso`** (L550)
    - _allocate_direct asigna una solicitud sin verificar conflictos

  - **`test_2_8_4_5_5_allocate_direct_recurso_no_registrado`** (L561)
    - _allocate_direct retorna None si el recurso no esta registrado

  - **`test_2_8_4_5_5_allocate_direct_cantidad_insuficiente`** (L571)
    - _allocate_direct retorna None si la cantidad no se puede satisfacer

  - **`test_2_8_4_5_5_allocate_direct_no_disponible`** (L581)
    - _allocate_direct retorna None si el recurso no esta disponible

  Métodos auxiliares (no test): setUp

---

<a name="utils/dynamic_resource_allocator/test-dynamic_resource_allocator_release"></a>
### `utils\dynamic_resource_allocator\test_dynamic_resource_allocator_release.py`

**Descripción:** Tests de liberacion y uso de asignaciones.

**Clases de test:**

- **`TestReleaseBasic`** (línea 28) — 3 método(s) de test
  - 2.8.4.4.1 — Liberar recurso (basico)

  - **`test_2_8_4_4_1_release_exitoso`** (L47)
    - release retorna True y cambia el status a AVAILABLE

  - **`test_2_8_4_4_1_release_no_existe`** (L54)
    - release retorna False para un allocation_id inexistente

  - **`test_2_8_4_4_1_3_release_doble`** (L59)
    - release retorna False al liberar una asignacion ya liberada (doble lib)

  Métodos auxiliares (no test): setUp

- **`TestReleaseUnexpectedStatus`** (línea 66) — 2 método(s) de test
  - 2.8.4.4.3 — Verificar liberacion con estados inesperados

  - **`test_2_8_4_4_3_release_status_pendiente`** (L79)
    - release retorna False si el status es PENDING

  - **`test_2_8_4_4_3_release_status_conflict`** (L92)
    - release retorna False si el status es CONFLICT

  Métodos auxiliares (no test): setUp

- **`TestReleaseRestoresAvailability`** (línea 106) — 3 método(s) de test
  - 2.8.4.4.2 — Restaurar disponibilidad del recurso

  - **`test_2_8_4_4_2_release_restaura_amount`** (L119)
    - release restaura la cantidad disponible al liberar

  - **`test_2_8_4_4_2_release_restaura_disponible`** (L137)
    - release marca el recurso como disponible=True si se agoto

  - **`test_2_8_4_4_2_release_sin_amount_no_restaura`** (L160)
    - release no restaura cantidad si amount es None

  Métodos auxiliares (no test): setUp

- **`TestReleaseWithCallback`** (línea 177) — 1 método(s) de test
  - Verificacion del callback on_allocation_changed en release

  - **`test_2_8_4_4_1_release_notifica_cambio`** (L196)
    - release llama a on_allocation_changed con (allocation_id, allocation)

  Métodos auxiliares (no test): setUp

- **`TestUpdateUsage`** (línea 205) — 3 método(s) de test
  - Actualizar uso real de una asignacion

  - **`test_2_8_4_4_5_update_usage_exitoso`** (L224)
    - update_usage establece actual_used y cambia status a IN_USE

  - **`test_2_8_4_4_5_update_usage_no_existe`** (L231)
    - update_usage retorna False para assignment_id inexistente

  - **`test_2_8_4_4_5_update_usage_multiple_updates`** (L236)
    - update_usage permite actualizaciones sucesivas

  Métodos auxiliares (no test): setUp

- **`TestCleanup`** (línea 244) — 2 método(s) de test
  - Limpieza de todas las asignaciones

  - **`test_2_8_4_4_6_cleanup_vacio`** (L257)
    - cleanup no lanza error con allocations vacias

  - **`test_2_8_4_4_6_cleanup_limpia_todo`** (L263)
    - cleanup elimina todas las asignaciones

  Métodos auxiliares (no test): setUp

---

<a name="utils/test-adaptive_goal_system"></a>
### `utils\test_adaptive_goal_system.py`

*Sin clases de test definidas.*

---

<a name="utils/test-adaptive_learning_engine"></a>
### `utils\test_adaptive_learning_engine.py`

**Descripción:** Tests consolidados para utils.adaptive_learning_engine. Consolida 2 archivos originales: test_adaptive_learning_engine.py y test_goal_adaptation_learning_loop.py

**Módulos de origen probados:** utils.adaptive_learning_engine

**Clases de test:**

- **`TestLearningTask`** (línea 25) — 2 método(s) de test

  - **`test_valores`** (L26)
  - **`test_count`** (L36)

- **`TestNeuralArchitecture`** (línea 40) — 2 método(s) de test

  - **`test_valores`** (L41)
  - **`test_count`** (L50)

- **`TestLearningTaskConfig`** (línea 54) — 3 método(s) de test

  - **`test_campos_obligatorios`** (L55)
  - **`test_defaults`** (L67)
  - **`test_custom_values`** (L89)

- **`TestModelPerformance`** (línea 108) — 2 método(s) de test

  - **`test_defaults`** (L109)
  - **`test_custom_values`** (L129)

- **`TestAdaptiveLearningEngineInit`** (línea 142) — 8 método(s) de test

  - **`test_performance_optimizer_asignado`** (L152)
  - **`test_self_improvement_system_asignado`** (L155)
  - **`test_pattern_analyzer_asignado`** (L158)
  - **`test_analytics_asignado`** (L161)
  - **`test_config_tiene_claves`** (L164)
  - **`test_estado_inicial`** (L173)
  - **`test_model_registry_inicializado`** (L184)
  - **`test_knowledge_base_estructura`** (L189)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestGetLearningEngineStatus`** (línea 197) — 3 método(s) de test

  - **`test_status_contiene_claves`** (L207)
  - **`test_status_is_running_false`** (L220)
  - **`test_status_is_running_true`** (L225)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestAddLearningTask`** (línea 232) — 2 método(s) de test

  - **`test_add_task_to_queue`** (L241)
  - **`test_add_multiple_tasks`** (L252)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestGetModelInfo`** (línea 264) — 3 método(s) de test

  - **`test_model_not_found`** (L274)
  - **`test_sklearn_model_info`** (L278)
  - **`test_torch_model_info`** (L294)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestExportLearningReport`** (línea 306) — 1 método(s) de test

  - **`test_export_report`** (L316)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestStopStartLearningEngine`** (línea 335) — 2 método(s) de test

  - **`test_stop`** (L344)
  - **`test_start`** (L349)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestSafeFloat`** (línea 357) — 5 método(s) de test

  - **`test_safe_float_normal`** (L358)
  - **`test_safe_float_int`** (L361)
  - **`test_safe_float_none`** (L364)
  - **`test_safe_float_invalid`** (L367)
  - **`test_safe_float_custom_default`** (L370)

- **`TestCaptureFeedback`** (línea 374) — 4 método(s) de test

  - **`test_feedback_exitoso`** (L385)
  - **`test_feedback_error_sin_excepcion`** (L414)
  - **`test_feedback_non_dict`** (L420)
  - **`test_feedback_almacenado`** (L424)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestAnalyzeGoalLearningPatterns`** (línea 437) — 3 método(s) de test

  - **`test_analiza_patrones`** (L447)
  - **`test_empty_patterns`** (L459)
  - **`test_non_dict_pattern`** (L463)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`TestDescribeGoalLearningPattern`** (línea 468) — 2 método(s) de test

  - **`test_describe`** (L469)
  - **`test_describe_default_context`** (L475)

- **`TestCalculateGoalLearningConvergence`** (línea 481) — 4 método(s) de test

  - **`test_converged`** (L482)
  - **`test_no_verified`** (L489)
  - **`test_low_impact`** (L494)
  - **`test_zero_improvement`** (L499)

- **`TestExecuteLearningLoop`** (línea 506) — 3 método(s) de test

  - **`test_execute_con_feedback_exitoso`** (L516)
  - **`test_execute_con_feedback_fallido`** (L539)
  - **`test_execute_non_dict`** (L545)

  Métodos auxiliares (no test): setUpClass, tearDownClass

---

<a name="utils/test-architectural_evolution_manager"></a>
### `utils\test_architectural_evolution_manager.py`

*Sin clases de test definidas.*

---

<a name="utils/test-auto_improvement_system"></a>
### `utils\test_auto_improvement_system.py`

*Sin clases de test definidas.*

---

<a name="utils/test-contextual_pattern_recognizer"></a>
### `utils\test_contextual_pattern_recognizer.py`

**Descripción:** Tests de ContextualPatternRecognizer (src/utils/contextual_pattern_recognizer.py).

**Clases de test:**

- **`TestContextualPatternType`** (línea 49) — 2 método(s) de test

  - **`test_values`** (L50)

  - **`test_count`** (L58)

- **`TestContextualPatternDataclass`** (línea 62) — 2 método(s) de test

  - **`test_campos`** (L63)

  - **`test_default_compatibility_score`** (L82)

- **`TestInit`** (línea 99) — 3 método(s) de test

  - **`test_default_pattern_analyzer`** (L100)

  - **`test_injected_pattern_analyzer`** (L104)

  - **`test_initial_state`** (L110)

- **`TestDetectContextualAnomaly`** (línea 119) — 7 método(s) de test

  - **`test_anomaly_system_resources`** (L120)

  - **`test_anomaly_user_behavior`** (L130)

  - **`test_anomaly_network_conditions`** (L138)

  - **`test_anomaly_error_rates`** (L146)

  - **`test_anomaly_alta_severidad`** (L154)

  - **`test_anomaly_no_anomalia`** (L167)

  - **`test_anomaly_confidence`** (L174)

- **`TestDetectContextualTrend`** (línea 182) — 4 método(s) de test

  - **`test_trend_high_factors`** (L183)

  - **`test_trend_low_factors`** (L197)

  - **`test_trend_no_trend`** (L209)

  - **`test_trend_mixed`** (L216)

- **`TestDetectContextualCorrelation`** (línea 229) — 4 método(s) de test

  - **`test_correlation_high_high`** (L230)

  - **`test_correlation_low_low`** (L242)

  - **`test_no_correlation`** (L253)

  - **`test_no_correlation_empty`** (L263)

- **`TestDetectContextualSeasonal`** (línea 270) — 4 método(s) de test

  - **`test_morning_peak`** (L271)

  - **`test_afternoon_peak`** (L279)

  - **`test_evening_peak`** (L286)

  - **`test_night_low`** (L293)

- **`TestDetectContextualBurst`** (línea 301) — 3 método(s) de test

  - **`test_burst_high`** (L302)

  - **`test_burst_medium`** (L315)

  - **`test_no_burst`** (L323)

- **`TestDetectContextualChangepoint`** (línea 331) — 4 método(s) de test

  - **`test_changepoint_high`** (L332)

  - **`test_changepoint_low`** (L344)

  - **`test_changepoint_critical_severity`** (L352)

  - **`test_no_changepoint`** (L364)

- **`TestCalculateContextualCompatibility`** (línea 372) — 3 método(s) de test

  - **`test_values`** (L373)

  - **`test_empty_factors`** (L380)

  - **`test_multiple_factors`** (L386)

- **`TestGetAffectedComponents`** (línea 397) — 5 método(s) de test

  - **`test_system_resources`** (L398)

  - **`test_user_behavior`** (L404)

  - **`test_network_conditions`** (L410)

  - **`test_error_rates`** (L416)

  - **`test_no_affectados`** (L422)

- **`TestAddContextualPattern`** (línea 430) — 3 método(s) de test

  - **`test_add_anomaly`** (L431)

  - **`test_add_no_pattern`** (L440)

  - **`test_add_registra_history`** (L450)

- **`TestGetContextualPatterns`** (línea 462) — 3 método(s) de test

  - **`test_get_all`** (L463)

  - **`test_filter_by_type`** (L471)

  - **`test_filter_no_match`** (L478)

- **`TestGetPatternsBySeverity`** (línea 486) — 2 método(s) de test

  - **`test_filter_by_severity`** (L487)

  - **`test_empty`** (L500)

- **`TestGetHighCompatibilityPatterns`** (línea 505) — 2 método(s) de test

  - **`test_high_compatibility`** (L506)

  - **`test_no_match`** (L514)

- **`TestClearPatterns`** (línea 523) — 2 método(s) de test

  - **`test_clear_all`** (L524)

  - **`test_clear_old_only`** (L534)

- **`TestGetPatternSummary`** (línea 572) — 3 método(s) de test

  - **`test_empty_summary`** (L573)

  - **`test_summary_con_patrones`** (L580)

  - **`test_summary_multiple_types`** (L591)

- **`TestExportPatterns`** (línea 605) — 2 método(s) de test

  - **`test_export_to_json`** (L606)

  - **`test_export_empty`** (L640)

- **`TestDetectContextualPatternChain`** (línea 653) — 2 método(s) de test
  - Verifica que _detect_contextual_pattern prueba detectores en orden

  - **`test_returns_first_match`** (L656)

  - **`test_no_match_returns_none`** (L665)

---

<a name="utils/test-contextual_pattern_recognizer_legacy"></a>
### `utils\test_contextual_pattern_recognizer_legacy.py`

**Descripción:** Tests para ContextualPatternRecognizer

**Módulos de origen probados:** src.utils.contextual_adaptation_engine, src.utils.contextual_pattern_recognizer, src.utils.pattern_analyzer

**Clases de test:**

- **`TestContextualPatternRecognizer`** (línea 14) — 14 método(s) de test

  - **`test_detect_contextual_anomaly`** (L31)
    - Test de detección de anomalías contextuales.

  - **`test_detect_contextual_trend`** (L40)
    - Test de detección de tendencias contextuales.

  - **`test_detect_contextual_correlation`** (L48)
    - Test de detección de correlaciones contextuales.

  - **`test_detect_contextual_seasonal`** (L64)
    - Test de detección de patrones estacionales.

  - **`test_detect_contextual_burst`** (L79)
    - Test de detección de patrones de burst.

  - **`test_detect_contextual_changepoint`** (L87)
    - Test de detección de puntos de cambio.

  - **`test_add_contextual_pattern`** (L103)
    - Test de añadir patrón contextual.

  - **`test_get_contextual_patterns`** (L111)
    - Test de obtener patrones por tipo.

  - **`test_get_patterns_by_severity`** (L133)
    - Test de obtener patrones por severidad.

  - **`test_get_high_compatibility_patterns`** (L140)
    - Test de obtener patrones con alta compatibilidad.

  - **`test_get_pattern_summary`** (L147)
    - Test de obtener resumen de patrones.

  - **`test_clear_patterns`** (L156)
    - Test de limpiar patrones.

  - **`test_export_patterns`** (L164)
    - Test de exportar patrones.

  - **`test_no_patterns_detected`** (L176)
    - Test cuando no se detectan patrones.

  Métodos auxiliares (no test): setUp

---

<a name="utils/test-dynamic_resource_allocator"></a>
### `utils\test_dynamic_resource_allocator.py`

**Descripción:** Tests consolidados para utils.dynamic_resource_allocator
Consolida 7 archivos originales.

**Clases de test:**

- **`TestAllocateConflicts`** (línea 35) — 2 método(s) de test
  - 2.8.4.3 — Conflictos de asignacion

  - **`test_2_8_4_3_2_conflict_identical_context`** (L48)
    - allocate rechaza solicitud con contexto idéntico (required=True)

  - **`test_2_8_4_3_2_conflict_shared_keys_different_values`** (L75)
    - allocate rechaza solicitud con claves compartidas y valores diferentes

  Métodos auxiliares (no test): setUp

- **`TestAllocatePreemption`** (línea 98) — 5 método(s) de test
  - 2.8.4.5.2 — Preempt por prioridad

  - **`test_2_8_4_5_2_preempt_critical`** (L125)
    - allocate preempta si la nueva solicitud es CRITICAL

  - **`test_2_8_4_5_2_preempt_mayor_prioridad_no_user`** (L141)
    - allocate preempta si existente no es user work y prioridad es mayor

  - **`test_2_8_4_5_2_preempt_consentimiento`** (L156)
    - allocate preempta si nueva solicitud tiene preempt_consent en contexto

  - **`test_2_8_4_5_2_no_preempt_user_work`** (L172)
    - allocate NO preempta si existente es user work y nueva no es CRITICAL

  - **`test_2_8_4_5_2_no_preempt_prioridad_igual`** (L189)
    - allocate NO preempta si la prioridad es igual (no estrictamente mayor)

  Métodos auxiliares (no test): setUp, _allocate_and_set_in_use

- **`TestAllocateDeferred`** (línea 205) — 5 método(s) de test
  - 2.8.4.5.3 — Rechazar o aplazar cuando no exista recurso

  - **`test_2_8_4_5_3_defer_no_required_recurso_no_disponible`** (L218)
    - allocate difiere solicitud cuando required=False y recurso no disponible

  - **`test_2_8_4_5_3_defer_no_required_cantidad_insuficiente`** (L239)
    - allocate difiere solicitud cuando required=False y cantidad insuficiente

  - **`test_2_8_4_5_3_reject_required_recurso_no_disponible`** (L251)
    - allocate rechaza solicitud cuando required=True y recurso no disponible

  - **`test_2_8_4_5_3_reject_required_cantidad_insuficiente`** (L270)
    - allocate rechaza solicitud cuando required=True y cantidad insuficiente

  - **`test_2_8_4_3_3_defer_almacena_metadata`** (L282)
    - defer_request almacena defer_id en metadata del request

  Métodos auxiliares (no test): setUp

- **`TestAllocateInvalidRequest`** (línea 295) — 1 método(s) de test
  - allocate con solicitudes invalidas

  - **`test_2_8_4_3_4_allocate_solicitud_invalida`** (L301)
    - allocate retorna None para una solicitud invalida (resource_type=None)

  Métodos auxiliares (no test): setUp

- **`TestOnAllocationChangedCallback`** (línea 313) — 2 método(s) de test
  - Verificacion del callback on_allocation_changed en varios flujos

  - **`test_2_8_4_3_5_callback_no_registrado_no_lanza`** (L326)
    - allocate funciona sin on_allocation_changed registrado

  - **`test_2_8_4_3_5_callback_debe_ser_callable`** (L336)
    - on_allocation_changed debe ser None por defecto

  Métodos auxiliares (no test): setUp

- **`TestResourceRequestDataclass`** (línea 347) — 3 método(s) de test
  - 2.8.4.2 — ResourceRequest es el modelo de solicitud

  - **`test_2_8_4_2_1_request_campos`** (L350)
    - ResourceRequest tiene los campos esperados

  - **`test_2_8_4_2_1_request_defaults`** (L369)
    - ResourceRequest tiene valores por defecto

  - **`test_2_8_4_2_1_request_to_dict`** (L382)
    - ResourceRequest.to_dict serializa todos los campos

- **`TestResourceRequestValidate`** (línea 401) — 7 método(s) de test
  - 2.8.4.2.5 — Validar solicitud

  - **`test_2_8_4_2_2_validate_valida`** (L404)
    - validate retorna (True, []) para una solicitud correcta

  - **`test_2_8_4_2_2_validate_sin_resource_type`** (L415)
    - validate retorna (False, [errors]) si resource_type es None

  - **`test_2_8_4_2_2_validate_request_id_vacio`** (L426)
    - validate retorna (False, [errors]) si request_id es None

  - **`test_2_8_4_2_2_validate_amount_negativo`** (L437)
    - validate retorna (False, [errors]) si amount es negativo

  - **`test_2_8_4_2_2_validate_amount_cero_valido`** (L448)
    - amount=0 es valido (solo < 0 es invalido)

  - **`test_2_8_4_2_2_validate_amount_none_valido`** (L458)
    - amount=None es valido

  - **`test_2_8_4_2_2_validate_priority_invalida`** (L468)
    - validate retorna (False, [errors]) si priority no es ResourcePriority

- **`TestCreateRequest`** (línea 481) — 4 método(s) de test
  - 2.8.4.2 — create_request construye un ResourceRequest

  - **`test_2_8_4_2_3_create_request`** (L487)
    - create_request genera un ResourceRequest con todos los campos

  - **`test_2_8_4_2_3_create_request_defaults`** (L506)
    - create_request usa valores por defecto si no se especifican

  - **`test_2_8_4_2_3_create_request_id_unico`** (L517)
    - create_request mantiene IDs unicos al pasar request_id explicito

  - **`test_2_8_4_2_3_create_request_invalido_lanza`** (L533)
    - create_request levanta ValueError para una solicitud invalida

  Métodos auxiliares (no test): setUp

- **`TestAllocateSimple`** (línea 543) — 8 método(s) de test
  - 2.8.4.3 — Asignar (camino basico sin conflictos)

  - **`test_2_8_4_3_1_allocate_exitoso`** (L556)
    - allocate asigna correctamente un recurso disponible

  - **`test_2_8_4_3_1_allocate_deduce_disponibilidad`** (L571)
    - allocate reduce la cantidad disponible tras la asignacion

  - **`test_2_8_4_3_1_allocate_registra_en_allocations`** (L582)
    - allocate registra la asignacion en el dict allocations

  - **`test_2_8_4_3_1_allocate_callback_on_changed`** (L592)
    - allocate llama a on_allocation_changed con (allocation_id, allocation)

  - **`test_2_8_4_3_1_allocate_sin_amount`** (L607)
    - allocate funciona con amount=None (solo marca disponible True)

  - **`test_2_8_4_3_1_allocate_recurso_no_registrado`** (L618)
    - allocate retorna None si el recurso no esta registrado

  - **`test_2_8_4_3_1_allocate_cantidad_insuficiente`** (L628)
    - allocate retorna None si la cantidad solicitada excede la disponible

  - **`test_2_8_4_3_1_allocate_recurso_no_disponible`** (L638)
    - allocate retorna None si el recurso esta marcado como no disponible

  Métodos auxiliares (no test): setUp

- **`TestResourceAllocationDataclass`** (línea 661) — 5 método(s) de test
  - 2.8.4.2 — ResourceAllocation es el modelo de asignacion

  - **`test_2_8_4_2_4_allocation_campos`** (L664)
    - ResourceAllocation tiene los campos esperados

  - **`test_2_8_4_2_4_allocation_defaults`** (L687)
    - ResourceAllocation tiene valores por defecto

  - **`test_2_8_4_2_4_allocation_assigned_at_default`** (L702)
    - ResourceAllocation asigna assigned_at por defecto a datetime.now()

  - **`test_2_8_4_2_4_allocation_to_dict`** (L715)
    - ResourceAllocation.to_dict serializa y convierte enums a valores

  - **`test_2_8_4_2_4_allocation_to_dict_released`** (L738)
    - to_dict incluye released_at cuando se libera

- **`TestGetAllocation`** (línea 752) — 3 método(s) de test
  - Obtener asignaciones

  - **`test_2_8_4_2_5_get_allocation_existente`** (L771)
    - get_allocation retorna la asignacion por ID

  - **`test_2_8_4_2_5_get_allocation_no_existente`** (L776)
    - get_allocation retorna None para un ID inexistente

  - **`test_2_8_4_2_5_get_all_allocations`** (L780)
    - get_all_allocations retorna todas las asignaciones

  Métodos auxiliares (no test): setUp

- **`TestConnectContext`** (línea 787) — 5 método(s) de test
  - 2.8.4.6 — Contexto: connect_context

  - **`test_2_8_4_6_1_connect_context_valido`** (L793)
    - connect_context almacena el contexto y retorna True

  - **`test_2_8_4_6_1_connect_context_none`** (L800)
    - connect_context rechaza None y retorna False

  - **`test_2_8_4_6_1_connect_context_no_dict`** (L805)
    - connect_context rechaza tipos no dict y retorna False

  - **`test_2_8_4_6_1_connect_context_vacio`** (L812)
    - connect_context acepta un dict vacio

  - **`test_2_8_4_6_1_connect_context_reemplaza`** (L818)
    - connect_context reemplaza el contexto anterior

  Métodos auxiliares (no test): setUp

- **`TestAdjustAllocationForContext`** (línea 826) — 6 método(s) de test
  - 2.8.4.6.2 — Ajustar asignacion usando datos disponibles

  - **`test_2_8_4_6_2_ajustar_con_datos_disponibles`** (L846)
    - adjust_allocation_for_context actualiza claves presentes en el contexto

  - **`test_2_8_4_6_2_ajustar_sin_cambios`** (L856)
    - adjust_allocation_for_context retorna False si los valores coinciden

  - **`test_2_8_4_6_2_ajustar_asignacion_no_existente`** (L862)
    - adjust_allocation_for_context retorna False para asignacion inexistente

  - **`test_2_8_4_6_2_ajustar_sin_contexto_global`** (L868)
    - adjust_allocation_for_context retorna False si no hay contexto global conectado

  - **`test_2_8_4_6_2_ajustar_sin_contexto_asignacion`** (L873)
    - adjust_allocation_for_context retorna False si la asignacion tiene contexto vacio

  - **`test_2_8_4_6_2_ajustar_notifica_cambio`** (L896)
    - adjust_allocation_for_context llama on_allocation_changed cuando hay ajuste

  Métodos auxiliares (no test): setUp

- **`TestAdjustAllAllocationsForContext`** (línea 905) — 2 método(s) de test
  - 2.8.4.6.2 — Ajustar todas las asignaciones

  - **`test_2_8_4_6_2_adjust_all_vacio`** (L925)
    - adjust_all_allocations_for_context retorna {} cuando no hay asignaciones

  - **`test_2_8_4_6_2_adjust_all_con_cambios`** (L930)
    - adjust_all_allocations_for_context ajusta asignaciones afectadas

  Métodos auxiliares (no test): setUp

- **`TestRecalculateOnContextChange`** (línea 939) — 4 método(s) de test
  - 2.8.4.6.3 — Recalcular cuando el contexto cambie

  - **`test_2_8_4_6_3_recalculate_cambio_claves`** (L959)
    - recalculate_on_context_change detecta claves cambiadas

  - **`test_2_8_4_6_3_recalculate_sin_cambios`** (L968)
    - recalculate_on_context_change con contexto idéntico: changed_keys vacia

  - **`test_2_8_4_6_3_recalculate_no_dict`** (L978)
    - recalculate_on_context_change rechaza contexto no dict

  - **`test_2_8_4_6_3_recalculate_actualiza_recursos_sistema`** (L985)
    - recalculate_on_context_change llama update_system_resources para claves de sistema

  Métodos auxiliares (no test): setUp

- **`TestDynamicResourceAllocatorIntegration`** (línea 998) — 4 método(s) de test
  - Tests de integración para DynamicResourceAllocator

  - **`test_2_8_4_7_1_connect_contextual_adaptation_engine`** (L1011)
    - 2.8.4.7.1 — Conectar ContextualAdaptationEngine

Verificar que el DynamicResourceAllocator puede conectarse y usar
el ContextualAdaptationEngine.

  - **`test_2_8_4_7_2_connect_performance_optimizer`** (L1064)
    - 2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda

Verificar que el DynamicResourceAllocator puede conectarse y usar
el PerformanceOptimizer.

  - **`test_2_8_4_7_3_expose_result_to_planner_executor`** (L1119)
    - 2.8.4.7.3 — Exponer resultado a Planner/Executor solo mediante contratos existentes

Verificar que el estado de recursos se expone en formato compatible
con contratos existentes del Planner/Executor.

  - **`test_2_8_4_7_4_integration_workflow`** (L1194)
    - Test del flujo de integración completo

Verificar el flujo completo de integración entre todos los componentes.

  Métodos auxiliares (no test): setUp

- **`TestResourceTypeEnum`** (línea 1259) — 2 método(s) de test
  - 2.8.4.1 — Tipos de recursos gestionables

  - **`test_2_8_4_1_1_resource_type_valores`** (L1262)
    - Verificar valores del enum ResourceType

  - **`test_2_8_4_1_1_resource_type_cuantos`** (L1277)
    - Verificar que hay 11 tipos de recursos

- **`TestResourcePriorityEnum`** (línea 1283) — 1 método(s) de test
  - 2.8.4.2.3 — Prioridades

  - **`test_2_8_4_1_2_resource_priority_valores`** (L1286)
    - Verificar valores del enum ResourcePriority

- **`TestAllocationStatusEnum`** (línea 1294) — 1 método(s) de test
  - Estados de asignacion

  - **`test_2_8_4_1_3_allocation_status_valores`** (L1297)
    - Verificar valores del enum AllocationStatus

- **`TestResourceAvailability`** (línea 1307) — 5 método(s) de test
  - 2.8.4.2.5 — Validar solicitud / disponibilidad

  - **`test_2_8_4_1_4_can_satisfy_disponible_sin_limites`** (L1310)
    - can_satisfy retorna True cuando no hay limites conocidos

  - **`test_2_8_4_1_4_can_satisfy_disponible_con_amount_none`** (L1320)
    - can_satisfy retorna True cuando el amount solicitado es None

  - **`test_2_8_4_1_4_can_satisfy_cantidad_suficiente`** (L1330)
    - can_satisfy retorna True cuando la cantidad disponible es suficiente

  - **`test_2_8_4_1_4_can_satisfy_cantidad_insuficiente`** (L1340)
    - can_satisfy retorna False cuando la cantidad es insuficiente

  - **`test_2_8_4_1_4_can_satisfy_no_disponible`** (L1350)
    - can_satisfy retorna False cuando el recurso no esta disponible

- **`TestRegisterResource`** (línea 1361) — 4 método(s) de test
  - 2.8.4.1 — Registrar recursos

  - **`test_2_8_4_1_5_register_resource_crea_availability`** (L1367)
    - register_resource crea un ResourceAvailability

  - **`test_2_8_4_1_5_register_resource_unidad_no_disponible`** (L1383)
    - register_resource puede marcar un recurso como no disponible

  - **`test_2_8_4_1_5_get_availability_no_registrado`** (L1396)
    - get_availability retorna None para recurso no registrado

  - **`test_2_8_4_1_5_get_availability_default_cpu`** (L1401)
    - get_availability retorna datos para recursos ya registrados tras init

  Métodos auxiliares (no test): setUp

- **`TestUpdateSystemResources`** (línea 1411) — 5 método(s) de test
  - 2.8.4.1.2 — Identificar como se mide disponibilidad

  - **`test_2_8_4_1_6_update_system_resources_sin_error`** (L1417)
    - update_system_resources no lanza error si no hay metricas

  - **`test_2_8_4_1_6_update_system_resources_con_metricas`** (L1423)
    - update_system_resources registra CPU, memoria, disco, red con metricas simuladas

  - **`test_2_8_4_1_6_update_execution_resources`** (L1453)
    - update_execution_resources registra EXECUTION_REGISTRY y EXECUTION_HISTORY

  - **`test_2_8_4_1_6_update_thread_pool_resources`** (L1467)
    - update_thread_pool_resources registra THREAD_POOL con workers disponibles

  - **`test_2_8_4_1_6_update_storage_resources`** (L1477)
    - update_storage_resources registra STORAGE_DATABASE y STORAGE_CACHE

  Métodos auxiliares (no test): setUp

- **`TestDynamicResourceAllocatorInit`** (línea 1492) — 4 método(s) de test
  - Verificacion del estado inicial del allocador

  - **`test_2_8_4_1_7_init_estado_inicial`** (L1495)
    - El allocador inicia con allocations vacias, locks y contextos vacios

  - **`test_2_8_4_1_7_init_monitor_asignado`** (L1505)
    - El allocador tiene un PerformanceMonitor asignado

  - **`test_2_8_4_1_7_init_optimizer_asignado`** (L1510)
    - El allocador tiene un PerformanceOptimizer asignado (por defecto o pasado)

  - **`test_2_8_4_1_7_init_lock_es_rlock`** (L1515)
    - El lock usado es un RLock (permitido reentrar)

- **`TestContextsConflict`** (línea 1527) — 6 método(s) de test
  - 2.8.4.5.1 — _contexts_conflict

  - **`test_2_8_4_5_1_conflict_identico`** (L1533)
    - Contextos idénticos → conflicto

  - **`test_2_8_4_5_1_conflict_clave_compartida_valor_diferente`** (L1539)
    - Claves compartidas con valores diferentes → conflicto

  - **`test_2_8_4_5_1_no_conflict_claves_disjuntas`** (L1545)
    - Claves disjuntas → sin conflicto

  - **`test_2_8_4_5_1_no_conflict_valores_iguales_clave_compartida`** (L1551)
    - Clave compartida con mismo valor → no conflicto

  - **`test_2_8_4_5_1_no_conflict_contexto_vacio`** (L1557)
    - Contexto vacio → sin conflicto

  - **`test_2_8_4_5_1_no_conflict_ambos_none`** (L1564)
    - Ambos contextos None → sin conflicto

  Métodos auxiliares (no test): setUp

- **`TestHasConflict`** (línea 1570) — 4 método(s) de test
  - 2.8.4.5.1 — _has_conflict

  - **`test_2_8_4_5_1_1_conflict_in_use_mismo_contexto`** (L1595)
    - _has_conflict retorna True si hay asignacion IN_USE con contexto conflictivo

  - **`test_2_8_4_5_1_1_no_conflict_assigned`** (L1606)
    - _has_conflict retorna False si la asignacion esta en ASSIGNED (no IN_USE)

  - **`test_2_8_4_5_1_1_no_conflict_diferente_recurso`** (L1617)
    - _has_conflict retorna False si el recurso es diferente

  - **`test_2_8_4_5_1_1_no_conflict_contexto_no_conflictivo`** (L1628)
    - _has_conflict retorna False si el contexto no entra en conflicto

  Métodos auxiliares (no test): setUp, _make_allocation

- **`TestGetConflicts`** (línea 1641) — 3 método(s) de test
  - 2.8.4.5.1 — get_conflicts

  - **`test_2_8_4_5_1_2_conflict_vacio`** (L1654)
    - get_conflicts retorna lista vacia sin asignaciones

  - **`test_2_8_4_5_1_2_conflict_encontrado`** (L1664)
    - get_conflicts retorna tuplas (alloc_id, allocation) de conflictos

  - **`test_2_8_4_5_1_2_conflict_multiples`** (L1687)
    - get_conflicts encuentra multiples asignaciones en conflicto

  Métodos auxiliares (no test): setUp

- **`TestIsUserWork`** (línea 1711) — 6 método(s) de test
  - 2.8.4.5.4 — _is_user_work

  - **`test_2_8_4_5_4_user_context_key`** (L1725)
    - _is_user_work True si el contexto tiene clave 'user'

  - **`test_2_8_4_5_4_user_type_key`** (L1730)
    - _is_user_work True si el contexto tiene 'type'='user'

  - **`test_2_8_4_5_4_user_source_key`** (L1735)
    - _is_user_work True si el contexto tiene 'source'='user'

  - **`test_2_8_4_5_4_interactive_key`** (L1740)
    - _is_user_work True si el contexto tiene 'interactive'=True

  - **`test_2_8_4_5_4_no_user_work`** (L1745)
    - _is_user_work False para contextos sin indicadores de usuario

  - **`test_2_8_4_5_4_contexto_vacio`** (L1750)
    - _is_user_work False para contexto vacio

  Métodos auxiliares (no test): setUp, _make_alloc

- **`TestCanPreempt`** (línea 1756) — 7 método(s) de test
  - 2.8.4.5.4 — _can_preempt

  - **`test_2_8_4_5_2_1_critical_puede_preemptar`** (L1783)
    - CRITICAL puede preemptar cualquier asignacion

  - **`test_2_8_4_5_2_1_preempt_consent_puede_preemptar`** (L1789)
    - preempt_consent=True en el contexto puede preemptar

  - **`test_2_8_4_5_2_1_mayor_prioridad_no_user`** (L1795)
    - Mayor prioridad sobre no-user work puede preemptar

  - **`test_2_8_4_5_2_1_igual_prioridad_no_preempta`** (L1801)
    - Igual prioridad sobre no-user work no puede preemptar

  - **`test_2_8_4_5_2_1_menor_prioridad_no_preempta`** (L1807)
    - Menor prioridad sobre no-user work no puede preemptar

  - **`test_2_8_4_5_2_1_user_work_no_preempta_sin_critical`** (L1813)
    - User work no puede preemptar con prioridad alta (solo CRITICAL)

  - **`test_2_8_4_5_2_1_user_work_no_preempta_sin_consent`** (L1819)
    - User work no puede preemptar con preempt_consent=False

  Métodos auxiliares (no test): setUp, _make_alloc, _make_request

- **`TestTryPreempt`** (línea 1832) — 2 método(s) de test
  - 2.8.4.5.2 — _try_preempt

  - **`test_2_8_4_5_2_2_try_preempt_exitoso`** (L1845)
    - _try_preempt retorna True y libera la asignacion cuando se puede preemptar

  - **`test_2_8_4_5_2_2_try_preempt_fracaso`** (L1872)
    - _try_preempt retorna False cuando no se puede preemptar

  Métodos auxiliares (no test): setUp

- **`TestDeferRequest`** (línea 1900) — 2 método(s) de test
  - 2.8.4.5.3 — defer_request

  - **`test_2_8_4_5_3_1_defer_request_retorna_id`** (L1913)
    - defer_request retorna un string con prefijo defer_

  - **`test_2_8_4_5_3_1_defer_request_almacena_pending`** (L1926)
    - defer_request almacena la solicitud en pending_requests

  Métodos auxiliares (no test): setUp

- **`TestGetPendingRequests`** (línea 1938) — 2 método(s) de test
  - 2.8.4.5.3 — get_pending_requests

  - **`test_2_8_4_5_3_2_pending_vacio`** (L1944)
    - get_pending_requests retorna lista vacia sin deferidos

  - **`test_2_8_4_5_3_2_pending_con_solicitudes`** (L1948)
    - get_pending_requests retorna copia de las solicitudes diferidas

  Métodos auxiliares (no test): setUp

- **`TestProcessDeferred`** (línea 1968) — 3 método(s) de test
  - 2.8.4.5.3 — process_deferred

  - **`test_2_8_4_5_3_3_process_deferred_asigna_exitosa`** (L1981)
    - process_deferred asigna solicitudes deferidas cuando hay disponibilidad

  - **`test_2_8_4_5_3_3_process_deferred_mantiene_fallidas`** (L1999)
    - process_deferred mantiene en pending las que no se pueden asignar

  - **`test_2_8_4_5_3_3_process_deferred_prioridad_descendente`** (L2014)
    - process_deferred procesa en orden de prioridad descendente

  Métodos auxiliares (no test): setUp

- **`TestAllocateDirect`** (línea 2037) — 4 método(s) de test
  - _allocate_direct — asignacion directa para procesamiento diferido

  - **`test_2_8_4_5_5_allocate_direct_exitoso`** (L2050)
    - _allocate_direct asigna una solicitud sin verificar conflictos

  - **`test_2_8_4_5_5_allocate_direct_recurso_no_registrado`** (L2061)
    - _allocate_direct retorna None si el recurso no esta registrado

  - **`test_2_8_4_5_5_allocate_direct_cantidad_insuficiente`** (L2071)
    - _allocate_direct retorna None si la cantidad no se puede satisfacer

  - **`test_2_8_4_5_5_allocate_direct_no_disponible`** (L2081)
    - _allocate_direct retorna None si el recurso no esta disponible

  Métodos auxiliares (no test): setUp

- **`TestReleaseBasic`** (línea 2104) — 3 método(s) de test
  - 2.8.4.4.1 — Liberar recurso (basico)

  - **`test_2_8_4_4_1_release_exitoso`** (L2123)
    - release retorna True y cambia el status a AVAILABLE

  - **`test_2_8_4_4_1_release_no_existe`** (L2130)
    - release retorna False para un allocation_id inexistente

  - **`test_2_8_4_4_1_3_release_doble`** (L2135)
    - release retorna False al liberar una asignacion ya liberada (doble lib)

  Métodos auxiliares (no test): setUp

- **`TestReleaseUnexpectedStatus`** (línea 2142) — 2 método(s) de test
  - 2.8.4.4.3 — Verificar liberacion con estados inesperados

  - **`test_2_8_4_4_3_release_status_pendiente`** (L2155)
    - release retorna False si el status es PENDING

  - **`test_2_8_4_4_3_release_status_conflict`** (L2168)
    - release retorna False si el status es CONFLICT

  Métodos auxiliares (no test): setUp

- **`TestReleaseRestoresAvailability`** (línea 2182) — 3 método(s) de test
  - 2.8.4.4.2 — Restaurar disponibilidad del recurso

  - **`test_2_8_4_4_2_release_restaura_amount`** (L2195)
    - release restaura la cantidad disponible al liberar

  - **`test_2_8_4_4_2_release_restaura_disponible`** (L2213)
    - release marca el recurso como disponible=True si se agoto

  - **`test_2_8_4_4_2_release_sin_amount_no_restaura`** (L2236)
    - release no restaura cantidad si amount es None

  Métodos auxiliares (no test): setUp

- **`TestReleaseWithCallback`** (línea 2253) — 1 método(s) de test
  - Verificacion del callback on_allocation_changed en release

  - **`test_2_8_4_4_1_release_notifica_cambio`** (L2272)
    - release llama a on_allocation_changed con (allocation_id, allocation)

  Métodos auxiliares (no test): setUp

- **`TestUpdateUsage`** (línea 2281) — 3 método(s) de test
  - Actualizar uso real de una asignacion

  - **`test_2_8_4_4_5_update_usage_exitoso`** (L2300)
    - update_usage establece actual_used y cambia status a IN_USE

  - **`test_2_8_4_4_5_update_usage_no_existe`** (L2307)
    - update_usage retorna False para assignment_id inexistente

  - **`test_2_8_4_4_5_update_usage_multiple_updates`** (L2312)
    - update_usage permite actualizaciones sucesivas

  Métodos auxiliares (no test): setUp

- **`TestCleanup`** (línea 2320) — 2 método(s) de test
  - Limpieza de todas las asignaciones

  - **`test_2_8_4_4_6_cleanup_vacio`** (L2333)
    - cleanup no lanza error con allocations vacias

  - **`test_2_8_4_4_6_cleanup_limpia_todo`** (L2339)
    - cleanup elimina todas las asignaciones

  Métodos auxiliares (no test): setUp

---

<a name="utils/test-meta_learning_system"></a>
### `utils\test_meta_learning_system.py`

**Descripción:** Tests de MetaLearningSystem (src/utils/meta_learning_system.py).

**Clases de test:**

- **`TestMetaLearningLevel`** (línea 55) — 2 método(s) de test

  - **`test_valores`** (L56)

  - **`test_count`** (L63)

- **`TestMetaLearningResult`** (línea 67) — 2 método(s) de test

  - **`test_valores`** (L68)

  - **`test_count`** (L75)

- **`TestMetaRuleStatus`** (línea 79) — 2 método(s) de test

  - **`test_valores`** (L80)

  - **`test_count`** (L89)

- **`TestLearningExperience`** (línea 93) — 3 método(s) de test

  - **`test_campos`** (L110)

  - **`test_metadata_default`** (L119)

  - **`test_metadata_custom`** (L123)

  Métodos auxiliares (no test): _make_experience

- **`TestLearningEvaluation`** (línea 128) — 2 método(s) de test

  - **`test_campos`** (L129)

  - **`test_defaults`** (L146)

- **`TestMetaRule`** (línea 164) — 7 método(s) de test

  - **`test_campos`** (L165)

  - **`test_is_valid_true`** (L183)

  - **`test_is_valid_metric_invalid`** (L187)

  - **`test_is_valid_operator_invalid`** (L191)

  - **`test_is_valid_action_invalid`** (L195)

  - **`test_is_valid_set_priority`** (L199)

  - **`test_supported_constants`** (L204)

- **`TestMetaRuleApplication`** (línea 211) — 2 método(s) de test

  - **`test_campos`** (L212)

  - **`test_defaults`** (L226)

- **`TestMetaLearningInsight`** (línea 237) — 1 método(s) de test

  - **`test_campos`** (L238)

- **`TestMetaLearningSystemInit`** (línea 252) — 8 método(s) de test

  - **`test_adaptive_engine_asignado`** (L262)

  - **`test_self_improvement_asignado`** (L265)

  - **`test_performance_optimizer_asignado`** (L268)

  - **`test_pattern_analyzer_asignado`** (L271)

  - **`test_config_tiene_claves`** (L274)

  - **`test_estado_inicial`** (L281)

  - **`test_seguridad_config`** (L293)

  - **`test_learning_queue_vacia`** (L299)

  Métodos auxiliares (no test): setUpClass, tearDownClass

- **`_MLSTestBase`** (línea 303) — 0 método(s) de test
  - Base con MLS singleton y threads detenidos.

  Métodos auxiliares (no test): setUpClass, tearDownClass, setUp

- **`TestGetLearningSuccessIndicators`** (línea 339) — 1 método(s) de test

  - **`test_indicators`** (L340)

- **`TestCaptureLearningExperience`** (línea 351) — 8 método(s) de test

  - **`test_capture_exitoso`** (L358)

  - **`test_capture_confianza_invalida_alta`** (L369)

  - **`test_capture_confianza_string`** (L376)

  - **`test_capture_sistema_no_soportado`** (L383)

  - **`test_capture_tarea_trivial`** (L391)

  - **`test_capture_contexto_vacio`** (L398)

  - **`test_capture_outcome_vacio`** (L405)

  - **`test_capture_duplicado`** (L412)

  Métodos auxiliares (no test): _mk_context, _mk_outcome

- **`TestCaptureStructuredAndWithContext`** (línea 428) — 3 método(s) de test

  - **`test_capture_estructurada_exitoso`** (L429)

  - **`test_capture_contextual_exitoso`** (L441)

  - **`test_capture_contextual_bajo_valor`** (L451)

- **`TestEvaluateLearningStrategy`** (línea 461) — 5 método(s) de test

  - **`test_sin_experiencias`** (L462)

  - **`test_con_experiencias_insuficientes`** (L468)

  - **`test_experiencias_externas_improvement`** (L482)

  - **`test_experiencias_externas_degradation`** (L506)

  - **`test_experiencias_externas_conflict`** (L529)

- **`TestGetLearningEvaluations`** (línea 555) — 2 método(s) de test

  - **`test_sin_experiencias`** (L556)

  - **`test_con_experiencia`** (L559)

- **`TestAnalyzeLearningPatterns`** (línea 572) — 1 método(s) de test

  - **`test_insuficientes_experiencias`** (L573)

- **`TestSecurityLimits`** (línea 578) — 3 método(s) de test

  - **`test_limites_default`** (L579)

  - **`test_reset_auto_change_cycle`** (L587)

  - **`test_limites_valor_invalido`** (L594)

- **`TestSharedComponents`** (línea 600) — 4 método(s) de test

  - **`test_sin_componentes_compartidos`** (L601)

  - **`test_con_componente_conectado`** (L604)

  - **`test_componente_no_soportado`** (L609)

  - **`test_engine_none`** (L613)

- **`TestSecurityDecisions`** (línea 618) — 2 método(s) de test

  - **`test_decisiones_vacias`** (L619)

  - **`test_registrar_decision`** (L622)

- **`TestSecurityStatus`** (línea 630) — 1 método(s) de test

  - **`test_status`** (L631)

- **`TestCheckInsightSecurity`** (línea 640) — 3 método(s) de test

  - **`test_auto_apply_disabled`** (L641)

  - **`test_auto_apply_enabled_allowed`** (L651)

  - **`test_limit_reached`** (L663)

- **`TestCheckMetaRuleSecurity`** (línea 677) — 3 método(s) de test

  - **`test_auto_apply_disabled`** (L678)

  - **`test_protected_action`** (L683)

  - **`test_allowed`** (L689)

- **`TestMetaLearningMetrics`** (línea 696) — 2 método(s) de test

  - **`test_empty_metrics`** (L697)

  - **`test_confidence_distribution_empty`** (L705)

- **`TestValidateMetaLearningInsights`** (línea 712) — 3 método(s) de test

  - **`test_validate_not_found`** (L713)

  - **`test_validate_found`** (L717)

  - **`test_validate_low_confidence`** (L729)

- **`TestGetRecommendations`** (línea 741) — 3 método(s) de test

  - **`test_sin_insights`** (L742)

  - **`test_con_insight_aplicado`** (L745)

  - **`test_insight_no_aplicado`** (L761)

- **`TestLearningRules`** (línea 773) — 2 método(s) de test

  - **`test_get_vacio`** (L774)

  - **`test_add_learning_rule`** (L777)

- **`TestMetaRules`** (línea 793) — 4 método(s) de test

  - **`test_get_vacio`** (L794)

  - **`test_add_valida`** (L797)

  - **`test_add_invalida`** (L803)

  - **`test_add_duplicada`** (L808)

- **`TestCompareMetric`** (línea 817) — 7 método(s) de test

  - **`test_lt`** (L818)

  - **`test_le`** (L822)

  - **`test_gt`** (L825)

  - **`test_ge`** (L828)

  - **`test_eq`** (L831)

  - **`test_invalid_value`** (L834)

  - **`test_invalid_operator`** (L837)

- **`TestApplyMetaRule`** (línea 841) — 9 método(s) de test

  - **`test_apply_invalid_rule`** (L852)

  - **`test_apply_target_not_found`** (L856)

  - **`test_apply_disabled_meta_rule`** (L861)

  - **`test_apply_insufficient_samples`** (L867)

  - **`test_apply_condition_not_met`** (L873)

  - **`test_apply_disable`** (L878)

  - **`test_apply_enable`** (L884)

  - **`test_apply_set_priority`** (L891)

  - **`test_apply_reset_stats`** (L898)

  Métodos auxiliares (no test): setUp

- **`TestVerifyAndRevert`** (línea 906) — 4 método(s) de test

  - **`test_verify_success`** (L917)

  - **`test_revert`** (L922)

  - **`test_revert_already_reverted`** (L931)

  - **`test_history`** (L937)

  Métodos auxiliares (no test): setUp

- **`TestMetaLearningState`** (línea 946) — 3 método(s) de test

  - **`test_get_state`** (L947)

  - **`test_save_state`** (L956)

  - **`test_save_state_default_path`** (L968)

- **`TestIntegrationStatus`** (línea 973) — 3 método(s) de test

  - **`test_integration_status`** (L974)

  - **`test_component_conectado`** (L980)

  - **`test_component_no_compartido`** (L986)

- **`MockAdaptiveEngine`** (línea 987) — 0 método(s) de test

  Métodos auxiliares (no test): get_learning_engine_status

---

<a name="utils/test-pattern_analyzer"></a>
### `utils\test_pattern_analyzer.py`

**Descripción:** Tests de PatternAnalyzer (src/utils/pattern_analyzer.py).

**Clases de test:**

- **`TestPatternType`** (línea 65) — 2 método(s) de test

  - **`test_values`** (L66)

  - **`test_count`** (L77)

- **`TestPatternSeverity`** (línea 81) — 2 método(s) de test

  - **`test_values`** (L82)

  - **`test_count`** (L88)

- **`TestPatternDataclass`** (línea 96) — 4 método(s) de test

  - **`test_campos`** (L97)

  - **`test_defaults`** (L105)

  - **`test_to_dict_serializa_enums`** (L120)

  - **`test_to_dict_serializable_to_json`** (L131)
    - to_dict debe producir algo JSON-serializable.

- **`TestTimeSeriesAnalyzerInit`** (línea 142) — 3 método(s) de test

  - **`test_default_window_size`** (L143)

  - **`test_custom_window_size`** (L147)

  - **`test_initial_state`** (L151)

- **`TestTimeSeriesAnalyzerAddDataPoint`** (línea 157) — 4 método(s) de test

  - **`test_add_data_point_basic`** (L158)

  - **`test_add_data_point_with_timestamp`** (L164)

  - **`test_add_multiple_points`** (L172)

  - **`test_add_trains_model_at_threshold`** (L178)
    - add_data_point entrena el modelo cuando hay >=100 puntos.

- **`TestTimeSeriesAnalyzerDetectAnomalies`** (línea 188) — 3 método(s) de test

  - **`test_detect_anomalies_insufficient_data`** (L189)
    - detect_anomalies retorna [] cuando hay menos puntos que window_size.

  - **`test_detect_anomalies_no_metric`** (L197)

  - **`test_detect_anomalies_statistical`** (L202)
    - detect_anomalies encuentra anomalias estadisticas con datos suficientes.

- **`TestPatternDetectorInit`** (línea 218) — 1 método(s) de test

  - **`test_init`** (L219)

- **`TestDetectErrorSpikes`** (línea 226) — 3 método(s) de test

  - **`test_detect_error_spikes`** (L227)
    - detect_error_spikes detecta picos cuando > 30% de errores en ventana.

  - **`test_no_error_spikes`** (L242)

  - **`test_error_spike_high_severity`** (L251)
    - High severity when 30% < rate <= 50%.

- **`TestDetectPerformanceDegradation`** (línea 266) — 2 método(s) de test

  - **`test_degradation_detected`** (L267)
    - detect_performance_degradation encuentra degradacion con >=10 puntos y 50% aumento.

  - **`test_no_degradation`** (L285)

- **`TestDetectAnomalies`** (línea 301) — 2 método(s) de test

  - **`test_detect_anomalies_no_performance_logs`** (L302)
    - detect_anomalies retorna [] sin logs de rendimiento.

  - **`test_detect_anomalies_insufficient_series`** (L308)
    - Necesita >=50 puntos por metrica para detectar anomalias.

- **`TestDetectTrends`** (línea 322) — 2 método(s) de test

  - **`test_trend_increasing`** (L323)
    - detect_trends encuentra tendencia creciente con slope > 2 y >=6 horas.

  - **`test_no_trend_insufficient_hours`** (L339)
    - detect_trends necesita >=6 horas de datos.

- **`TestDetectCycles`** (línea 351) — 2 método(s) de test

  - **`test_no_cycles_insufficient_data`** (L352)
    - detect_cycles necesita >=60 minutos recientes.

  - **`test_detect_periodicity_short_data`** (L359)
    - _detect_periodicity retorna None con menos de 30 puntos.

- **`TestDetectCorrelations`** (línea 366) — 1 método(s) de test

  - **`test_no_correlations_simple`** (L367)

- **`TestDetectBursts`** (línea 374) — 3 método(s) de test

  - **`test_detect_burst`** (L375)
    - detect_bursts detecta cuando hay >10 logs/segundo.

  - **`test_detect_burst_high_severity`** (L391)
    - High severity when count > 50.

  - **`test_no_burst`** (L402)

- **`TestPatternDetectorAnalyzeLogs`** (línea 409) — 3 método(s) de test

  - **`test_analyze_logs_returns_patterns`** (L410)

  - **`test_analyze_logs_empty`** (L425)

  - **`test_analyze_logs_stores_in_history`** (L430)

- **`TestPatternDetectorQuery`** (línea 444) — 8 método(s) de test

  - **`test_get_patterns_by_type`** (L445)

  - **`test_get_patterns_by_type_limit`** (L453)

  - **`test_get_active_patterns_excludes_acknowledged`** (L463)

  - **`test_get_active_patterns_excludes_inactive`** (L472)

  - **`test_acknowledge_pattern`** (L481)

  - **`test_acknowledge_pattern_not_found`** (L488)

  - **`test_get_pattern_statistics`** (L493)

  - **`test_get_pattern_statistics_empty`** (L506)

- **`TestPatternAnalyzer`** (línea 517) — 7 método(s) de test

  - **`test_init`** (L518)

  - **`test_analyze_logs_delegates`** (L522)

  - **`test_get_pattern_analysis`** (L531)

  - **`test_get_patterns_by_type_delegates`** (L544)

  - **`test_get_active_patterns_delegates`** (L551)

  - **`test_acknowledge_pattern_delegates`** (L555)

  - **`test_get_pattern_statistics_delegates`** (L562)

- **`TestGlobalInstance`** (línea 568) — 1 método(s) de test

  - **`test_pattern_detector_instance`** (L569)
    - La instancia global pattern_detector existe y es PatternDetector.

---

<a name="utils/test-performance_optimizer"></a>
### `utils\test_performance_optimizer.py`

**Descripción:** Tests de PerformanceOptimizer (src/utils/performance_optimizer.py).

**Clases de test:**

- **`TestOptimizationStrategy`** (línea 23) — 2 método(s) de test

  - **`test_valores`** (L24)

  - **`test_count`** (L36)

- **`TestOptimizationLevel`** (línea 40) — 2 método(s) de test

  - **`test_valores`** (L41)

  - **`test_count`** (L47)

- **`TestOptimizationMetrics`** (línea 51) — 2 método(s) de test

  - **`test_defaults`** (L52)

  - **`test_custom_values`** (L65)

- **`TestOptimizationAction`** (línea 76) — 2 método(s) de test

  - **`test_campos`** (L77)

  - **`test_defaults`** (L100)

- **`TestPerformanceOptimizerInit`** (línea 119) — 8 método(s) de test

  - **`test_monitor_asignado`** (L126)

  - **`test_pattern_analyzer_asignado`** (L129)

  - **`test_analytics_asignado`** (L132)

  - **`test_config_tiene_claves`** (L135)

  - **`test_estado_inicial`** (L141)

  - **`test_models_inicializados`** (L146)

  - **`test_scalers_inicializados`** (L153)

  - **`test_thresholds`** (L157)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestOptimizationStatus`** (línea 165) — 4 método(s) de test

  - **`test_status_contiene_claves`** (L172)

  - **`test_status_is_running`** (L185)

  - **`test_status_baseline_none`** (L190)

  - **`test_status_last_analysis`** (L195)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestOptimizationHistory`** (línea 200) — 2 método(s) de test

  - **`test_history_vacia`** (L207)

  - **`test_history_limit`** (L212)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestGetCurrentActions`** (línea 221) — 1 método(s) de test

  - **`test_empty`** (L228)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestAddCustomOptimizationAction`** (línea 232) — 1 método(s) de test

  - **`test_add_action_to_queue`** (L239)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestStopStartOptimization`** (línea 257) — 2 método(s) de test

  - **`test_stop`** (L264)

  - **`test_start_desde_parado`** (L269)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestOptimizeSystem`** (línea 276) — 3 método(s) de test

  - **`test_optimiza_sistema`** (L283)

  - **`test_optimiza_default_level`** (L294)

  - **`test_optimiza_action_id_formato`** (L299)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestGetOptimizationRecommendations`** (línea 304) — 6 método(s) de test

  - **`test_no_recommendations`** (L311)
    - Sin metricas altas, no hay recomendaciones.

  - **`test_cpu_recommendation`** (L317)

  - **`test_memory_recommendation`** (L324)

  - **`test_response_time_recommendation`** (L329)

  - **`test_error_rate_recommendation`** (L334)

  - **`test_multiple_recommendations`** (L339)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestExportOptimizationReport`** (línea 350) — 1 método(s) de test

  - **`test_export_report`** (L357)

  Métodos auxiliares (no test): setUp, tearDown

- **`TestOptimizeResources`** (línea 375) — 3 método(s) de test

  - **`test_optimize_basic`** (L382)

  - **`test_optimize_sin_contexto`** (L390)

  - **`test_optimize_sin_recursos`** (L397)

  Métodos auxiliares (no test): setUp, tearDown

---

<a name="utils/test-self_improvement_system"></a>
### `utils\test_self_improvement_system.py`

*Sin clases de test definidas.*

---
