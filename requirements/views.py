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
            "low_level_requirements__triples__subject",
            "low_level_requirements__triples__object",
            "triples__subject",
            "triples__object",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hlr = self.object
        # Combine HLR's own triples with all child LLR triples
        all_triples = set(hlr.triples.all())
        for llr in hlr.low_level_requirements.all():
            all_triples.update(llr.triples.all())
        context["all_triples"] = sorted(all_triples, key=lambda t: t.pk)
        return context


class LLRDetailView(DetailView):
    model = LowLevelRequirement
    template_name = "requirements/llr_detail.html"
    context_object_name = "llr"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "high_level_requirement",
        ).prefetch_related(
            "components",
            "verifications",
            "triples__subject",
            "triples__object",
        )


def _build_requirement_graph(req):
    """Build graph data for a single requirement's ontology triples."""
    nodes = []
    edges = []
    seen_node_ids = set()

    for triple in req.triples.select_related("subject", "object").all():
        for ont_node in (triple.subject, triple.object):
            node_id = f"node-{ont_node.pk}"
            if node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                nodes.append({
                    "id": node_id,
                    "name": ont_node.name,
                    "qualified_name": ont_node.qualified_name,
                    "kind": ont_node.kind,
                    "group": "ontology",
                    "compound_refid": ont_node.compound_refid,
                    "description": ont_node.description,
                })
        edges.append({
            "source": f"node-{triple.subject_id}",
            "target": f"node-{triple.object_id}",
            "predicate": triple.predicate,
        })

    return {"nodes": nodes, "edges": edges}


def hlr_graph_data(request, pk):
    hlr = HighLevelRequirement.objects.prefetch_related(
        "low_level_requirements__triples__subject",
        "low_level_requirements__triples__object",
    ).get(pk=pk)
    graph = _build_requirement_graph(hlr)
    # Include triples from child LLRs
    for llr in hlr.low_level_requirements.all():
        llr_graph = _build_requirement_graph(llr)
        existing_ids = {n["id"] for n in graph["nodes"]}
        for node in llr_graph["nodes"]:
            if node["id"] not in existing_ids:
                graph["nodes"].append(node)
                existing_ids.add(node["id"])
        existing_edges = {(e["source"], e["predicate"], e["target"]) for e in graph["edges"]}
        for edge in llr_graph["edges"]:
            key = (edge["source"], edge["predicate"], edge["target"])
            if key not in existing_edges:
                graph["edges"].append(edge)
                existing_edges.add(key)
    return JsonResponse(graph)


def llr_graph_data(request, pk):
    llr = LowLevelRequirement.objects.get(pk=pk)
    return JsonResponse(_build_requirement_graph(llr))
