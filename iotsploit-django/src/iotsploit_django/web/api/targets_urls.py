from django.urls import path

from iotsploit_django.view_handlers.arxml_views import preview_arxml_import
from iotsploit_django.view_handlers.target_views import (
    create_target,
    delete_target,
    edit_target,
    get_component_types,
    get_current_target,
    get_facet_schemas,
    get_target,
    get_target_types,
    list_targets,
    select_target,
)


urlpatterns = [
    path("list_targets/", list_targets, name="list_targets"),
    path("get_target/<str:target_id>/", get_target, name="get_target"),
    path("select_target/", select_target, name="select_target"),
    path("edit_target/", edit_target, name="edit_target"),
    path("create_target/", create_target, name="create_target"),
    path("delete_target/", delete_target, name="delete_target"),
    path("get_current_target/", get_current_target, name="get_current_target"),
    path("get_component_types/", get_component_types, name="get_component_types"),
    path("get_target_types/", get_target_types, name="get_target_types"),
    path("get_facet_schemas/", get_facet_schemas, name="get_facet_schemas"),
    path("preview_arxml_import/", preview_arxml_import, name="preview_arxml_import"),
]


