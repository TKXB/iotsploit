from django.urls import path

from iotsploit_django.iot_fuzzer.views import (
    # Testing Page Endpoints
    get_campaign_statistics,
    get_campaign_status,
    get_test_groups,
    pause_campaign,
    reset_campaign,
    start_campaign,
    stop_campaign,
    # Configuration Page Endpoints
    delete_template,
    get_generator_config,
    get_generator_types,
    get_protocol_config,
    get_protocol_types,
    get_saved_config,
    get_templates_list,
    load_template,
    save_generator_config,
    save_protocol_config,
    save_template,
    test_protocol_connection,
    validate_configuration,
    # Management Page Endpoints
    build_protocol_frame,
    create_test_case,
    create_test_group,
    delete_test_case,
    delete_test_group,
    export_test_data,
    get_protocol_frame_templates,
    get_test_cases_list,
    get_test_groups_list,
    import_test_data,
    move_test_case,
    update_test_case,
    update_test_group,
    validate_protocol_frame,
    # Results Page Endpoints
    export_results,
    filter_logs,
    get_artifacts,
    get_file_content,
    get_files_tree,
    get_logs_list,
    get_results_charts,
    get_results_summary,
    download_file as download_fuzzer_file,
)


urlpatterns = [
    # IoT Fuzzer endpoints
    # Testing Page Endpoints - Campaign Control
    path("iot-fuzzer/testing/campaign/start/", start_campaign, name="iot_fuzzer_start_campaign"),
    path("iot-fuzzer/testing/campaign/stop/", stop_campaign, name="iot_fuzzer_stop_campaign"),
    path("iot-fuzzer/testing/campaign/pause/", pause_campaign, name="iot_fuzzer_pause_campaign"),
    path("iot-fuzzer/testing/campaign/reset/", reset_campaign, name="iot_fuzzer_reset_campaign"),
    # Testing Page Endpoints - Status and Statistics
    path("iot-fuzzer/testing/campaign/status/", get_campaign_status, name="iot_fuzzer_campaign_status"),
    path("iot-fuzzer/testing/statistics/", get_campaign_statistics, name="iot_fuzzer_campaign_statistics"),
    path("iot-fuzzer/testing/test-groups/", get_test_groups, name="iot_fuzzer_test_groups"),
    # Configuration Page Endpoints - Protocol Configuration
    path("iot-fuzzer/configuration/protocols/types/", get_protocol_types, name="iot_fuzzer_protocol_types"),
    path("iot-fuzzer/configuration/protocols/config/", get_protocol_config, name="iot_fuzzer_protocol_config"),
    path(
        "iot-fuzzer/configuration/protocols/config/save/",
        save_protocol_config,
        name="iot_fuzzer_save_protocol_config",
    ),
    path(
        "iot-fuzzer/configuration/protocols/test-connection/",
        test_protocol_connection,
        name="iot_fuzzer_test_protocol_connection",
    ),
    path(
        "iot-fuzzer/configuration/protocols/saved-config/",
        get_saved_config,
        name="iot_fuzzer_get_saved_config",
    ),
    # Configuration Page Endpoints - Generator Configuration
    path(
        "iot-fuzzer/configuration/generators/types/",
        get_generator_types,
        name="iot_fuzzer_generator_types",
    ),
    path(
        "iot-fuzzer/configuration/generators/config/",
        get_generator_config,
        name="iot_fuzzer_generator_config",
    ),
    path(
        "iot-fuzzer/configuration/generators/config/save/",
        save_generator_config,
        name="iot_fuzzer_save_generator_config",
    ),
    # Configuration Page Endpoints - Template Management
    path(
        "iot-fuzzer/configuration/templates/list/",
        get_templates_list,
        name="iot_fuzzer_templates_list",
    ),
    path("iot-fuzzer/configuration/templates/load/", load_template, name="iot_fuzzer_load_template"),
    path("iot-fuzzer/configuration/templates/save/", save_template, name="iot_fuzzer_save_template"),
    path(
        "iot-fuzzer/configuration/templates/delete/",
        delete_template,
        name="iot_fuzzer_delete_template",
    ),
    # Configuration Page Endpoints - Configuration Validation
    path(
        "iot-fuzzer/configuration/validate/",
        validate_configuration,
        name="iot_fuzzer_validate_configuration",
    ),
    # Management Page Endpoints - Test Group Management
    path(
        "iot-fuzzer/management/test-groups/list/",
        get_test_groups_list,
        name="iot_fuzzer_test_groups_list",
    ),
    path(
        "iot-fuzzer/management/test-groups/create/",
        create_test_group,
        name="iot_fuzzer_create_test_group",
    ),
    path(
        "iot-fuzzer/management/test-groups/update/<int:group_id>/",
        update_test_group,
        name="iot_fuzzer_update_test_group",
    ),
    path(
        "iot-fuzzer/management/test-groups/delete/<int:group_id>/",
        delete_test_group,
        name="iot_fuzzer_delete_test_group",
    ),
    # Management Page Endpoints - Test Case Management
    path(
        "iot-fuzzer/management/test-cases/list/",
        get_test_cases_list,
        name="iot_fuzzer_test_cases_list",
    ),
    path(
        "iot-fuzzer/management/test-cases/create/",
        create_test_case,
        name="iot_fuzzer_create_test_case",
    ),
    path(
        "iot-fuzzer/management/test-cases/update/<int:case_id>/",
        update_test_case,
        name="iot_fuzzer_update_test_case",
    ),
    path(
        "iot-fuzzer/management/test-cases/delete/<int:case_id>/",
        delete_test_case,
        name="iot_fuzzer_delete_test_case",
    ),
    path("iot-fuzzer/management/test-cases/move/", move_test_case, name="iot_fuzzer_move_test_case"),
    # Management Page Endpoints - Protocol Frame Builder
    path(
        "iot-fuzzer/management/protocol-frames/build/",
        build_protocol_frame,
        name="iot_fuzzer_build_protocol_frame",
    ),
    path(
        "iot-fuzzer/management/protocol-frames/validate/",
        validate_protocol_frame,
        name="iot_fuzzer_validate_protocol_frame",
    ),
    path(
        "iot-fuzzer/management/protocol-frames/templates/",
        get_protocol_frame_templates,
        name="iot_fuzzer_protocol_frame_templates",
    ),
    # Management Page Endpoints - Export/Import
    path("iot-fuzzer/management/export/", export_test_data, name="iot_fuzzer_export_test_data"),
    path("iot-fuzzer/management/import/", import_test_data, name="iot_fuzzer_import_test_data"),
    # Results Page Endpoints - File Management
    path("iot-fuzzer/results/files/tree/", get_files_tree, name="iot_fuzzer_files_tree"),
    path(
        "iot-fuzzer/results/files/content/<int:file_id>/",
        get_file_content,
        name="iot_fuzzer_file_content",
    ),
    path(
        "iot-fuzzer/results/files/download/<int:file_id>/",
        download_fuzzer_file,
        name="iot_fuzzer_download_file",
    ),
    # Results Page Endpoints - Log Management
    path("iot-fuzzer/results/logs/list/", get_logs_list, name="iot_fuzzer_logs_list"),
    path("iot-fuzzer/results/logs/filter/", filter_logs, name="iot_fuzzer_filter_logs"),
    # Results Page Endpoints - Results Analysis
    path(
        "iot-fuzzer/results/analysis/summary/",
        get_results_summary,
        name="iot_fuzzer_results_summary",
    ),
    path(
        "iot-fuzzer/results/analysis/charts/",
        get_results_charts,
        name="iot_fuzzer_results_charts",
    ),
    path(
        "iot-fuzzer/results/analysis/export/",
        export_results,
        name="iot_fuzzer_export_results",
    ),
    # Results Page Endpoints - Artifact Management
    path("iot-fuzzer/results/artifacts/", get_artifacts, name="iot_fuzzer_artifacts"),
]


