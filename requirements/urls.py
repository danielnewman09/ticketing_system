from django.urls import path
from . import views

urlpatterns = [
    path("", views.RequirementListView.as_view(), name="requirement_list"),
    path("hlr/create/", views.HLRCreateView.as_view(), name="hlr_create"),
    path("hlr/<int:pk>/", views.HLRDetailView.as_view(), name="hlr_detail"),
    path("hlr/<int:pk>/update/", views.HLRUpdateView.as_view(), name="hlr_update"),
    path("hlr/<int:pk>/graph/", views.hlr_graph_data, name="hlr_graph_data"),
    path("hlr/<int:pk>/decompose/", views.hlr_decompose, name="hlr_decompose"),
    path("llr/create/", views.LLRCreateView.as_view(), name="llr_create"),
    path("llr/<int:pk>/", views.LLRDetailView.as_view(), name="llr_detail"),
    path("llr/<int:pk>/update/", views.LLRUpdateView.as_view(), name="llr_update"),
    path("<int:pk>/update/", views.LLRUpdateView.as_view(), name="requirement_update"),
    path("llr/<int:pk>/graph/", views.llr_graph_data, name="llr_graph_data"),
    path("verification/<int:pk>/", views.VerificationDetailView.as_view(), name="verification_detail"),
    path("verification/<int:pk>/edit/", views.VerificationEditView.as_view(), name="verification_edit"),
]
