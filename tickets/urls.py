from django.urls import path
from . import views

urlpatterns = [
    path("", views.ticket_list, name="ticket_list"),
    path("create/", views.ticket_create, name="ticket_create"),
    path("<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("<int:pk>/update/", views.ticket_update, name="ticket_update"),
    path("requirements/", views.requirement_list, name="requirement_list"),
    path("requirements/hlr/create/", views.hlr_create, name="hlr_create"),
    path("requirements/hlr/<int:pk>/update/", views.hlr_update, name="hlr_update"),
    path("requirements/llr/create/", views.llr_create, name="llr_create"),
    path("requirements/<int:pk>/update/", views.requirement_update, name="requirement_update"),
]
