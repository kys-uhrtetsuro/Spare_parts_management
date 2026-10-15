from django.urls import include, path
from inventory.views import index, asset, favicon

urlpatterns = [
    path("api/", include("inventory.urls")),
    path("assets/<path:filepath>", asset),
    path("favicon.ico", favicon),
    path("", index),
]
