from django.http import JsonResponse
from django.views.generic import TemplateView, ListView, CreateView, UpdateView
from django.urls import reverse_lazy

from requirements.models import HighLevelRequirement, LowLevelRequirement
from .models import OntologyNode, OntologyTriple
from .forms import OntologyNodeForm, OntologyTripleForm


class OntologyGraphView(TemplateView):
    template_name = "codebase/ontology_graph.html"


class OntologyNodeListView(ListView):
    model = OntologyNode
    template_name = "codebase/node_list.html"
    context_object_name = "nodes"
    ordering = ["kind", "name"]


class OntologyNodeCreateView(CreateView):
    model = OntologyNode
    form_class = OntologyNodeForm
    template_name = "codebase/node_form.html"
    success_url = reverse_lazy("ontology_node_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Ontology Node"
        return context


class OntologyNodeUpdateView(UpdateView):
    model = OntologyNode
    form_class = OntologyNodeForm
    template_name = "codebase/node_form.html"
    success_url = reverse_lazy("ontology_node_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Node: {self.object}"
        return context


class OntologyTripleCreateView(CreateView):
    model = OntologyTriple
    form_class = OntologyTripleForm
    template_name = "codebase/edge_form.html"
    success_url = reverse_lazy("ontology_node_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Triple"
        return context


def ontology_graph_data(request):
    """Return the full ontology graph as JSON for Cytoscape visualization.

    All edges are triples (subject --predicate--> object). Requirement nodes
    appear connected to ontology nodes via their associated triples.
    """
    nodes = []
    node_ids = set()

    for node in OntologyNode.objects.all():
        node_id = f"node-{node.pk}"
        node_ids.add(node_id)
        nodes.append({
            "id": node_id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            "group": "ontology",
            "compound_refid": node.compound_refid,
            "description": node.description,
        })

    edges = []
    # All triples become edges
    for triple in OntologyTriple.objects.select_related("subject", "object").all():
        edges.append({
            "source": f"node-{triple.subject_id}",
            "target": f"node-{triple.object_id}",
            "predicate": triple.predicate,
        })

    # Add requirement nodes connected via their triples
    def add_requirement_nodes(requirements, req_type):
        for req in requirements.prefetch_related("triples__subject", "triples__object"):
            req_triples = list(req.triples.all())
            if not req_triples:
                continue
            req_id = f"{req_type}-{req.pk}"
            nodes.append({
                "id": req_id,
                "name": f"{req_type.upper()} {req.pk}",
                "qualified_name": str(req),
                "kind": req_type,
                "group": "requirement",
                "description": req.description,
            })
            for triple in req_triples:
                edges.append({
                    "source": req_id,
                    "target": f"node-{triple.subject_id}",
                    "predicate": triple.predicate,
                })
                if triple.subject_id != triple.object_id:
                    edges.append({
                        "source": req_id,
                        "target": f"node-{triple.object_id}",
                        "predicate": triple.predicate,
                    })

    add_requirement_nodes(HighLevelRequirement.objects, "hlr")
    add_requirement_nodes(LowLevelRequirement.objects, "llr")

    return JsonResponse({"nodes": nodes, "edges": edges})
