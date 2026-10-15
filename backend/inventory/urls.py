from django.urls import path
from . import views

urlpatterns = [
    path("health", views.health),
    path("systems", views.systems),
    path("systems/<int:pk>", views.system_detail),
    path("parts", views.parts),
    path("parts/<int:pk>", views.part_detail),
    path("parts/<int:pk>/versions", views.part_versions),
    path("stocks", views.stocks),
    path("history", views.history),
    path("history/<int:pk>/correct", views.history_correct),
    path("alerts", views.alerts),
    path("alerts/bulk", views.alerts_bulk),
    path("export", views.export_excel),
    path("backup", views.backup),
]
