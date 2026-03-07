from django.urls import path
from . import views

urlpatterns = [
    path("", views.OntologyGraphView.as_view(), name="ontology_graph"),
    path("nodes/", views.OntologyNodeListView.as_view(), name="ontology_node_list"),
    path("nodes/create/", views.OntologyNodeCreateView.as_view(), name="ontology_node_create"),
    path("nodes/<int:pk>/update/", views.OntologyNodeUpdateView.as_view(), name="ontology_node_update"),
    path("edges/create/", views.OntologyEdgeCreateView.as_view(), name="ontology_edge_create"),
    path("api/graph/", views.ontology_graph_data, name="ontology_graph_data"),
]
