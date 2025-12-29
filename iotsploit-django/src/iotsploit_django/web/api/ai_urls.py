from django.urls import path

from sat_toolkit.view_handlers.ai_model_views import (
    ai_model_create,
    ai_model_delete,
    ai_model_detail,
    ai_model_list,
    ai_model_set_default,
    ai_model_test_connection,
    ai_model_update,
    ai_provider_list,
    ai_template_list,
)


urlpatterns = [
    path("ai-models/", ai_model_list, name="ai_model_list"),
    path("ai-models/create/", ai_model_create, name="ai_model_create"),
    path("ai-models/<int:pk>/", ai_model_detail, name="ai_model_detail"),
    path("ai-models/<int:pk>/update/", ai_model_update, name="ai_model_update"),
    path("ai-models/<int:pk>/delete/", ai_model_delete, name="ai_model_delete"),
    path("ai-models/<int:pk>/test/", ai_model_test_connection, name="ai_model_test_connection"),
    path("ai-models/<int:pk>/set-default/", ai_model_set_default, name="ai_model_set_default"),
    path("ai-models/providers/", ai_provider_list, name="ai_provider_list"),
    path("ai-templates/", ai_template_list, name="ai_template_list"),
]


