from django.urls import path
from . import views

urlpatterns = [
    path("", views.ComponentListView.as_view(), name="component_list"),
    path("create/", views.ComponentCreateView.as_view(), name="component_create"),
    path("<int:pk>/", views.ComponentDetailView.as_view(), name="component_detail"),
    path("languages/", views.LanguageListView.as_view(), name="language_list"),
    path("languages/<int:pk>/", views.LanguageDetailView.as_view(), name="language_detail"),
    path("languages/<int:pk>/edit/", views.LanguageEditView.as_view(), name="language_edit"),
    path(
        "dependency-managers/<int:dm_pk>/dependencies/",
        views.DependencyEditView.as_view(),
        name="dependency_edit",
    ),
]
