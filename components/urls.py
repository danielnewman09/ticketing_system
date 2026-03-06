from django.urls import path
from . import views

urlpatterns = [
    path("", views.ComponentListView.as_view(), name="component_list"),
    path("create/", views.ComponentCreateView.as_view(), name="component_create"),
    path("<int:pk>/", views.ComponentDetailView.as_view(), name="component_detail"),
]
