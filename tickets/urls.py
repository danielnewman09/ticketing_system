from django.urls import path
from . import views

urlpatterns = [
    path("", views.TicketListView.as_view(), name="ticket_list"),
    path("create/", views.TicketCreateView.as_view(), name="ticket_create"),
    path("<int:pk>/", views.TicketDetailView.as_view(), name="ticket_detail"),
    path("<int:pk>/update/", views.TicketUpdateView.as_view(), name="ticket_update"),
    path("components/", views.ComponentListView.as_view(), name="component_list"),
    path("components/<int:pk>/", views.ComponentDetailView.as_view(), name="component_detail"),
]
