"""Routes for interactive plugin executions."""

from django.urls import path

from iotsploit_django.view_handlers import interaction_views as views


urlpatterns = [
    path(
        "plugin-executions/pending/",
        views.list_pending_requests,
        name="list_pending_input_requests",
    ),
    path(
        "plugin-executions/<uuid:execution_id>/",
        views.get_execution,
        name="get_plugin_execution",
    ),
    path(
        "plugin-executions/<uuid:execution_id>/cancel/",
        views.cancel_execution,
        name="cancel_plugin_execution",
    ),
    path(
        "plugin-executions/<uuid:execution_id>/inputs/<uuid:request_id>/answer/",
        views.answer_input_request,
        name="answer_input_request",
    ),
]
