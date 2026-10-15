from django.urls import include, path
from inventory.views import index, asset

urlpatterns = [
    path("api/", include("inventory.urls")),
    path("assets/<path:filepath>", asset),
    path("", index),
]
