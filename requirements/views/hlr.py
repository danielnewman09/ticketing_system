from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import DetailView, CreateView, UpdateView

from requirements.models import HighLevelRequirement
from requirements.forms import HighLevelRequirementForm

from .common import _build_requirement_graph


class HLRCreateView(CreateView):
    model = HighLevelRequirement
    form_class = HighLevelRequirementForm
    template_name = "requirements/hlr/form.html"
    success_url = reverse_lazy("requirement_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create High-Level Requirement"
        return context


class HLRUpdateView(UpdateView):
    model = HighLevelRequirement
    form_class = HighLevelRequirementForm
    template_name = "requirements/hlr/form.html"

    def get_success_url(self):
        return reverse_lazy("hlr_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit HLR #{self.object.pk}"
        return context


class HLRDetailView(DetailView):
    model = HighLevelRequirement
    template_name = "requirements/hlr/detail.html"
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
