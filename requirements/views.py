from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, CreateView, UpdateView
from .models import HighLevelRequirement, LowLevelRequirement
from .forms import HighLevelRequirementForm, LowLevelRequirementForm, LLRVerificationFormSet


class RequirementListView(ListView):
    model = HighLevelRequirement
    template_name = "requirements/requirement_list.html"
    context_object_name = "hlrs"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            "low_level_requirements__components",
            "low_level_requirements__verifications",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unlinked_llrs"] = LowLevelRequirement.objects.filter(
            high_level_requirement__isnull=True
        ).prefetch_related("verifications")
        return context


class HLRCreateView(CreateView):
    model = HighLevelRequirement
    form_class = HighLevelRequirementForm
    template_name = "requirements/hlr_form.html"
    success_url = reverse_lazy("requirement_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create High-Level Requirement"
        return context


class HLRUpdateView(UpdateView):
    model = HighLevelRequirement
    form_class = HighLevelRequirementForm
    template_name = "requirements/hlr_form.html"

    def get_success_url(self):
        return reverse_lazy("hlr_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit HLR #{self.object.pk}"
        return context


class LLRCreateView(CreateView):
    model = LowLevelRequirement
    form_class = LowLevelRequirementForm
    template_name = "requirements/requirement_form.html"
    success_url = reverse_lazy("requirement_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Low-Level Requirement"
        if self.request.POST:
            context["verification_formset"] = LLRVerificationFormSet(self.request.POST)
        else:
            context["verification_formset"] = LLRVerificationFormSet()
        return context

    def get_initial(self):
        initial = super().get_initial()
        hlr_id = self.request.GET.get("hlr")
        if hlr_id:
            initial["high_level_requirement"] = hlr_id
        return initial

    def form_valid(self, form):
        context = self.get_context_data()
        verification_formset = context["verification_formset"]
        if verification_formset.is_valid():
            self.object = form.save()
            verification_formset.instance = self.object
            verification_formset.save()
            return super().form_valid(form)
        return self.form_invalid(form)


class LLRUpdateView(UpdateView):
    model = LowLevelRequirement
    form_class = LowLevelRequirementForm
    template_name = "requirements/requirement_form.html"

    def get_success_url(self):
        return reverse_lazy("llr_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Requirement #{self.object.pk}"
        if self.request.POST:
            context["verification_formset"] = LLRVerificationFormSet(self.request.POST, instance=self.object)
        else:
            context["verification_formset"] = LLRVerificationFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        verification_formset = context["verification_formset"]
        if verification_formset.is_valid():
            self.object = form.save()
            verification_formset.save()
            return super().form_valid(form)
        return self.form_invalid(form)


class HLRDetailView(DetailView):
    model = HighLevelRequirement
    template_name = "requirements/hlr_detail.html"
    context_object_name = "hlr"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            "low_level_requirements__components",
            "low_level_requirements__verifications",
        )


class LLRDetailView(DetailView):
    model = LowLevelRequirement
    template_name = "requirements/llr_detail.html"
    context_object_name = "llr"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "high_level_requirement",
        ).prefetch_related("components", "verifications")


def _build_requirement_graph(req, req_type):
    """Build graph data for a single requirement's ontology connections.

    Returns nodes and edges for the requirement itself plus any ontology
    nodes it references via actor/subject compound_refid.
    """
    from codebase.models import OntologyNode, OntologyEdge

    # Map compound refids to ontology nodes
    refid_to_node = {}
    for node in OntologyNode.objects.all():
        if node.compound_refid:
            refid_to_node[node.compound_refid] = node

    nodes = []
    edges = []

    req_id = f"{req_type}-{req.pk}"
    nodes.append({
        "id": req_id,
        "name": f"{req_type.upper()} {req.pk}",
        "qualified_name": str(req),
        "kind": req_type,
        "group": "requirement",
        "description": req.description,
    })

    # Collect ontology node PKs connected to this requirement
    connected_node_pks = set()

    if req.actor_compound_refid and req.actor_compound_refid in refid_to_node:
        ont_node = refid_to_node[req.actor_compound_refid]
        connected_node_pks.add(ont_node.pk)
        edges.append({
            "source": req_id,
            "target": f"node-{ont_node.pk}",
            "relationship": "actor",
            "label": f"actor: {req.actor}",
        })

    if req.subject_compound_refid and req.subject_compound_refid in refid_to_node:
        ont_node = refid_to_node[req.subject_compound_refid]
        connected_node_pks.add(ont_node.pk)
        edges.append({
            "source": req_id,
            "target": f"node-{ont_node.pk}",
            "relationship": "subject",
            "label": f"subject: {req.subject}",
        })

    # Add the connected ontology nodes and their inter-relationships
    ont_nodes = OntologyNode.objects.filter(pk__in=connected_node_pks)
    for node in ont_nodes:
        nodes.append({
            "id": f"node-{node.pk}",
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            "group": "ontology",
            "compound_refid": node.compound_refid,
            "description": node.description,
        })

    # Include edges between the connected ontology nodes
    if connected_node_pks:
        for edge in OntologyEdge.objects.filter(
            source_id__in=connected_node_pks,
            target_id__in=connected_node_pks,
        ).select_related("source", "target"):
            edges.append({
                "source": f"node-{edge.source_id}",
                "target": f"node-{edge.target_id}",
                "relationship": edge.relationship,
                "label": edge.label or edge.get_relationship_display(),
            })

    return {"nodes": nodes, "edges": edges}


def hlr_graph_data(request, pk):
    hlr = HighLevelRequirement.objects.get(pk=pk)
    return JsonResponse(_build_requirement_graph(hlr, "hlr"))


def llr_graph_data(request, pk):
    llr = LowLevelRequirement.objects.get(pk=pk)
    return JsonResponse(_build_requirement_graph(llr, "llr"))
