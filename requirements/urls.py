from django.urls import path
from . import views

urlpatterns = [
    path("", views.RequirementListView.as_view(), name="requirement_list"),
    path("hlr/create/", views.HLRCreateView.as_view(), name="hlr_create"),
    path("hlr/<int:pk>/update/", views.HLRUpdateView.as_view(), name="hlr_update"),
    path("llr/create/", views.LLRCreateView.as_view(), name="llr_create"),
    path("<int:pk>/update/", views.LLRUpdateView.as_view(), name="requirement_update"),
]
