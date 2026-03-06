from django.urls import path
from . import views

urlpatterns = [
    path("", views.ticket_list, name="ticket_list"),
    path("create/", views.ticket_create, name="ticket_create"),
    path("<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("<int:pk>/update/", views.ticket_update, name="ticket_update"),
]
