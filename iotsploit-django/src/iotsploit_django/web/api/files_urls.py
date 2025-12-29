from django.urls import path

from iotsploit_django.view_handlers.file_views import (
    delete_file,
    download_file,
    list_files,
    upload_file,
)


urlpatterns = [
    path("upload_file/", upload_file, name="upload_file"),
    path("list_files/", list_files, name="list_files"),
    path("download_file/<path:file_path>", download_file, name="download_file"),
    path("download_file/", download_file, name="download_file"),
    path("delete_file/<path:file_path>", delete_file, name="delete_file"),
]


