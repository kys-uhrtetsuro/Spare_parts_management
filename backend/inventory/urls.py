from django.urls import path
from . import views

urlpatterns = [
    path("health", views.health),
    path("systems", views.systems),
    path("systems/<int:pk>", views.system_detail),
    path("equipment", views.equipment),
    path("equipment/<int:pk>", views.equipment_detail),
    path("equipment/sections", views.equipment_sections),
    path("equipment/sections/<int:pk>", views.equipment_section_detail),
    path("categories", views.categories),
    path("categories/<int:pk>", views.category_detail),
    path("parts", views.parts),
    path("parts/<int:pk>", views.part_detail),
    path("parts/<int:pk>/versions", views.part_versions),
    path("stocks", views.stocks),
    path("history", views.history),
    path("history/<int:pk>/correct", views.history_correct),
    path("alerts", views.alerts),
    path("alerts/bulk", views.alerts_bulk),
    path("export", views.export_excel),
    path("import/preview", views.import_preview),
    path("import/apply", views.import_apply),
    path("backup", views.backup),
]
