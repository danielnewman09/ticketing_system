from django.http import JsonResponse
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy

from requirements.models import HighLevelRequirement, LowLevelRequirement
from .models import OntologyNode, OntologyTriple, Compound, Member, NamespaceNode, Predicate
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

        # Composed members grouped by visibility (class interface)
        composes_pred = Predicate.objects.filter(name="composes").first()
        if composes_pred and node.kind in ("class", "interface"):
            composed = (
                OntologyNode.objects
                .filter(triples_as_object__subject=node, triples_as_object__predicate=composes_pred)
                .order_by("kind", "name")
            )
            context["public_members"] = composed.filter(visibility__in=("public", ""))
            context["private_members"] = composed.filter(visibility="private")
            context["protected_members"] = composed.filter(visibility="protected")
        else:
            context["public_members"] = []
            context["private_members"] = []
            context["protected_members"] = []

        # Non-composes outgoing triples (inheritance, dependencies, etc.)
        context["outgoing_triples"] = (
            node.triples_as_subject
            .select_related("predicate", "object")
            .exclude(predicate=composes_pred) if composes_pred else
            node.triples_as_subject.select_related("predicate", "object").all()
        )
        context["incoming_triples"] = (
            node.triples_as_object
            .select_related("predicate", "subject")
            .exclude(predicate=composes_pred) if composes_pred else
            node.triples_as_object.select_related("predicate", "subject").all()
        )

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
        "visibility": node.visibility,
        "group": "ontology",
        "compound_refid": node.compound_refid,
        "description": node.description,
        "url": reverse("ontology_node_detail", kwargs={"pk": node.pk}),
    }


def ontology_graph_data(request):
    """Return the full ontology graph as JSON for Cytoscape visualization.

    Class/interface nodes become compound parents. Members linked via
    "composes" triples become children of the class node, with visibility
    metadata so the frontend can show/hide private members.
    """
    show_private = request.GET.get("show_private", "0") == "1"
    ns_lookup = NamespaceNode.parent_lookup()

    # Build a lookup of class-member parent relationships via "composes" triples
    composes_pred = Predicate.objects.filter(name="composes").first()
    class_member_parent = {}  # member node pk -> class node pk
    if composes_pred:
        for triple in OntologyTriple.objects.filter(predicate=composes_pred).select_related("subject", "object"):
            if triple.subject.kind in ("class", "interface"):
                class_member_parent[triple.object_id] = triple.subject_id

    nodes = []
    for node in OntologyNode.objects.all():
        # Skip private/protected members in the main graph unless requested
        if node.pk in class_member_parent and not show_private and node.visibility in ("private", "protected"):
            continue

        d = _ontology_node_to_dict(node)

        # Class-member parent takes precedence over namespace parent
        if node.pk in class_member_parent:
            d["parent"] = f"node-{class_member_parent[node.pk]}"
        else:
            parent = NamespaceNode.resolve_parent(node.qualified_name, ns_lookup)
            if parent:
                d["parent"] = parent

        nodes.append(d)

    # Collect node IDs that made it into the graph for edge filtering
    included_ids = {d["id"] for d in nodes}

    edges = []
    for triple in OntologyTriple.objects.select_related("subject", "object", "predicate").all():
        source_id = f"node-{triple.subject_id}"
        target_id = f"node-{triple.object_id}"
        # Skip "composes" edges — they're represented by parent/child containment
        if composes_pred and triple.predicate_id == composes_pred.pk:
            continue
        # Only include edges where both endpoints are in the graph
        if source_id in included_ids and target_id in included_ids:
            edges.append({
                "source": source_id,
                "target": target_id,
                "predicate": triple.predicate.name,
            })

    return JsonResponse({"nodes": nodes, "edges": edges})


def _build_neighborhood_graph(node):
    """Build graph data for a non-namespace node's direct neighbors.

    For class/interface nodes, composed members are included as children
    (both public and private) so the detail view shows the full class structure.
    """
    nodes_dict = {node.pk: _ontology_node_to_dict(node)}
    edges = []
    composes_pred = Predicate.objects.filter(name="composes").first()

    for triple in node.triples_as_subject.select_related("object", "predicate").all():
        neighbor = triple.object
        if neighbor.pk not in nodes_dict:
            d = _ontology_node_to_dict(neighbor)
            # Members composed by this class become children
            if composes_pred and triple.predicate_id == composes_pred.pk and node.kind in ("class", "interface"):
                d["parent"] = f"node-{node.pk}"
            nodes_dict[neighbor.pk] = d

        # Skip composes edges — represented by containment
        if composes_pred and triple.predicate_id == composes_pred.pk:
            continue
        edges.append({
            "source": f"node-{node.pk}",
            "target": f"node-{neighbor.pk}",
            "predicate": triple.predicate.name,
        })

    for triple in node.triples_as_object.select_related("subject", "predicate").all():
        neighbor = triple.subject
        if neighbor.pk not in nodes_dict:
            nodes_dict[neighbor.pk] = _ontology_node_to_dict(neighbor)
        # Skip composes edges where this node is the member
        if composes_pred and triple.predicate_id == composes_pred.pk:
            continue
        edges.append({
            "source": f"node-{neighbor.pk}",
            "target": f"node-{node.pk}",
            "predicate": triple.predicate.name,
        })

    return nodes_dict, edges


def _build_namespace_graph(ns):
    """Build graph data for a namespace node showing its children and their triples."""
    nodes_dict = {ns.pk: _ontology_node_to_dict(ns)}
    edges = []

    for child in ns.get_children():
        d = _ontology_node_to_dict(child)
        d["parent"] = f"node-{ns.pk}"
        nodes_dict[child.pk] = d

    for triple in ns.get_child_triples():
        for endpoint in (triple.subject, triple.object):
            if endpoint.pk not in nodes_dict:
                nodes_dict[endpoint.pk] = _ontology_node_to_dict(endpoint)
        edges.append({
            "source": f"node-{triple.subject_id}",
            "target": f"node-{triple.object_id}",
            "predicate": triple.predicate.name,
        })

    return nodes_dict, edges


def ontology_node_graph_data(request, pk):
    """Return the neighborhood graph for a single ontology node.

    For namespace nodes, returns all direct children with the namespace as
    their compound parent, plus all triples where at least one endpoint is
    a child of this namespace.
    """
    node = OntologyNode.objects.get(pk=pk)

    if node.kind == "namespace":
        ns = NamespaceNode.objects.get(pk=pk)
        nodes_dict, edges = _build_namespace_graph(ns)
    else:
        nodes_dict, edges = _build_neighborhood_graph(node)

    return JsonResponse({
        "nodes": list(nodes_dict.values()),
        "edges": edges,
    })
