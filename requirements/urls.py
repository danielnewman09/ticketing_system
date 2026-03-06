from django.urls import path
from . import views

urlpatterns = [
    path("", views.requirement_list, name="requirement_list"),
    path("hlr/create/", views.hlr_create, name="hlr_create"),
    path("hlr/<int:pk>/update/", views.hlr_update, name="hlr_update"),
    path("llr/create/", views.llr_create, name="llr_create"),
    path("<int:pk>/update/", views.requirement_update, name="requirement_update"),
]
