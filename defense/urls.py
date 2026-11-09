from django.urls import path

from . import views

app_name = "defense"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("defense/new/", views.defense_form, name="defense_create"),
    path("defense/<int:pk>/edit/", views.defense_form, name="defense_edit"),
    path("defense/<int:pk>/toggle/", views.defense_toggle, name="defense_toggle"),
    path("defense/<int:pk>/delete/", views.defense_delete, name="defense_delete"),
    path("defense/<int:pk>/evaluate/", views.defense_evaluate, name="defense_evaluate"),
    path("defense/<int:pk>/results/", views.results, name="results"),
    path("defense/<int:pk>/results/status/", views.results_status_json, name="results_status"),
    path("defense/<int:pk>/results/print/", views.print_results, name="print_results"),
    path("evaluation/<int:pk>/", views.evaluate, name="evaluate"),
    path("evaluation/<int:pk>/unlock/", views.evaluation_unlock, name="evaluation_unlock"),
    path("evaluation/<int:pk>/print/", views.print_panelist_form, name="print_form"),
    path("panelists/", views.panelist_list, name="panelist_list"),
    path("panelists/new/", views.panelist_form, name="panelist_create"),
    path("panelists/<int:pk>/edit/", views.panelist_form, name="panelist_edit"),
    path("panelists/<int:pk>/delete/", views.panelist_delete, name="panelist_delete"),
    path("settings/", views.scoring_settings, name="scoring_settings"),
]
