from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import TemplateView, ListView, CreateView, UpdateView
from django.urls import reverse_lazy

from requirements.models import HighLevelRequirement, LowLevelRequirement
from .models import OntologyNode, OntologyEdge
from .forms import OntologyNodeForm, OntologyEdgeForm


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


class OntologyEdgeCreateView(CreateView):
    model = OntologyEdge
    form_class = OntologyEdgeForm
    template_name = "codebase/edge_form.html"
    success_url = reverse_lazy("ontology_node_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Relationship"
        return context


def ontology_graph_data(request):
    """Return the ontology graph as JSON for D3 visualization.

    Includes ontology nodes, ontology edges, and requirement nodes
    (HLRs/LLRs) linked via compound_refid as actor/subject.
    """
    # Build a refid -> ontology node id lookup for linking requirements
    refid_to_node_id = {}
    nodes = []
    for node in OntologyNode.objects.all():
        nodes.append({
            "id": f"node-{node.pk}",
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            "group": "ontology",
            "compound_refid": node.compound_refid,
            "description": node.description,
        })
        if node.compound_refid:
            refid_to_node_id[node.compound_refid] = f"node-{node.pk}"

    edges = []
    for edge in OntologyEdge.objects.select_related("source", "target").all():
        edges.append({
            "source": f"node-{edge.source_id}",
            "target": f"node-{edge.target_id}",
            "relationship": edge.relationship,
            "label": edge.label or edge.get_relationship_display(),
        })

    # Add HLRs that reference compounds as actor or subject
    has_compound = Q(actor_compound_refid__gt="") | Q(subject_compound_refid__gt="")

    for hlr in HighLevelRequirement.objects.filter(has_compound):
        hlr_id = f"hlr-{hlr.pk}"
        nodes.append({
            "id": hlr_id,
            "name": f"HLR {hlr.pk}",
            "qualified_name": str(hlr),
            "kind": "hlr",
            "group": "requirement",
            "description": hlr.description,
        })
        if hlr.actor_compound_refid and hlr.actor_compound_refid in refid_to_node_id:
            edges.append({
                "source": hlr_id,
                "target": refid_to_node_id[hlr.actor_compound_refid],
                "relationship": "actor",
                "label": f"actor: {hlr.actor}",
            })
        if hlr.subject_compound_refid and hlr.subject_compound_refid in refid_to_node_id:
            edges.append({
                "source": hlr_id,
                "target": refid_to_node_id[hlr.subject_compound_refid],
                "relationship": "subject",
                "label": f"subject: {hlr.subject}",
            })

    # Add LLRs that reference compounds as actor or subject
    for llr in LowLevelRequirement.objects.filter(has_compound):
        llr_id = f"llr-{llr.pk}"
        nodes.append({
            "id": llr_id,
            "name": f"LLR {llr.pk}",
            "qualified_name": str(llr),
            "kind": "llr",
            "group": "requirement",
            "description": llr.description,
        })
        if llr.actor_compound_refid and llr.actor_compound_refid in refid_to_node_id:
            edges.append({
                "source": llr_id,
                "target": refid_to_node_id[llr.actor_compound_refid],
                "relationship": "actor",
                "label": f"actor: {llr.actor}",
            })
        if llr.subject_compound_refid and llr.subject_compound_refid in refid_to_node_id:
            edges.append({
                "source": llr_id,
                "target": refid_to_node_id[llr.subject_compound_refid],
                "relationship": "subject",
                "label": f"subject: {llr.subject}",
            })

    return JsonResponse({"nodes": nodes, "edges": edges})
