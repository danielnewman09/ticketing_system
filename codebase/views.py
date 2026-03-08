from django.http import JsonResponse
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy

from requirements.models import HighLevelRequirement, LowLevelRequirement
from .models import OntologyNode, OntologyTriple, Compound, Member
from .forms import OntologyNodeForm, OntologyTripleForm


class OntologyGraphView(TemplateView):
    template_name = "codebase/ontology_graph.html"


class OntologyNodeListView(ListView):
    model = OntologyNode
    template_name = "codebase/node_list.html"
    context_object_name = "nodes"
    ordering = ["kind", "name"]


class OntologyNodeDetailView(DetailView):
    model = OntologyNode
    template_name = "codebase/node_detail.html"
    context_object_name = "node"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            "triples_as_subject__object",
            "triples_as_object__subject",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        node = self.object

        # Resolve linked compound and its members from external DB
        try:
            compound = node.get_compound()
        except Exception:
            compound = None
        context["compound"] = compound
        if compound:
            try:
                context["members"] = (
                    Member.objects.using("codebase")
                    .filter(compound=compound)
                    .order_by("kind", "name")
                )
            except Exception:
                context["members"] = []
        else:
            context["members"] = []

        # Gather requirements linked via this node's triples
        triple_ids = set()
        for t in node.triples_as_subject.all():
            triple_ids.add(t.pk)
        for t in node.triples_as_object.all():
            triple_ids.add(t.pk)

        context["linked_hlrs"] = (
            HighLevelRequirement.objects
            .filter(triples__pk__in=triple_ids)
            .distinct()
        )
        context["linked_llrs"] = (
            LowLevelRequirement.objects
            .filter(triples__pk__in=triple_ids)
            .distinct()
        )

        return context


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

    def get_success_url(self):
        return reverse_lazy("ontology_node_detail", kwargs={"pk": self.object.pk})

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


def _ontology_node_to_dict(node):
    """Serialize an OntologyNode for the graph JSON API."""
    from django.urls import reverse
    return {
        "id": f"node-{node.pk}",
        "name": node.name,
        "qualified_name": node.qualified_name,
        "kind": node.kind,
        "group": "ontology",
        "compound_refid": node.compound_refid,
        "description": node.description,
        "url": reverse("ontology_node_detail", kwargs={"pk": node.pk}),
    }


def ontology_graph_data(request):
    """Return the full ontology graph as JSON for Cytoscape visualization."""
    nodes = []
    for node in OntologyNode.objects.all():
        nodes.append(_ontology_node_to_dict(node))

    edges = []
    for triple in OntologyTriple.objects.select_related("subject", "object").all():
        edges.append({
            "source": f"node-{triple.subject_id}",
            "target": f"node-{triple.object_id}",
            "predicate": triple.predicate,
        })

    return JsonResponse({"nodes": nodes, "edges": edges})


def ontology_node_graph_data(request, pk):
    """Return the neighborhood graph for a single ontology node."""
    from django.urls import reverse

    node = OntologyNode.objects.get(pk=pk)
    nodes_dict = {}
    edges = []

    # Add the focal node
    nodes_dict[node.pk] = _ontology_node_to_dict(node)

    # Add all neighbors via triples
    for triple in node.triples_as_subject.select_related("object").all():
        neighbor = triple.object
        if neighbor.pk not in nodes_dict:
            nodes_dict[neighbor.pk] = _ontology_node_to_dict(neighbor)
        edges.append({
            "source": f"node-{node.pk}",
            "target": f"node-{neighbor.pk}",
            "predicate": triple.predicate,
        })

    for triple in node.triples_as_object.select_related("subject").all():
        neighbor = triple.subject
        if neighbor.pk not in nodes_dict:
            nodes_dict[neighbor.pk] = _ontology_node_to_dict(neighbor)
        edges.append({
            "source": f"node-{neighbor.pk}",
            "target": f"node-{node.pk}",
            "predicate": triple.predicate,
        })

    return JsonResponse({
        "nodes": list(nodes_dict.values()),
        "edges": edges,
    })
