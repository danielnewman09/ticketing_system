from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, CreateView, UpdateView

from ai_assist.mixins import AiAssistMixin
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationMethod,
)
from requirements.forms import HighLevelRequirementForm
from components.models import Component

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


class HLRDetailView(AiAssistMixin, DetailView):
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

    def get_ai_context(self):
        hlr = self.object
        llrs = []
        for llr in hlr.low_level_requirements.all():
            verifications = []
            for v in llr.verifications.all():
                verifications.append({
                    "id": v.id, "method": v.method,
                    "test_name": v.test_name, "description": v.description,
                })
            llrs.append({
                "id": llr.id, "description": llr.description,
                "verifications": verifications,
            })
        return {
            "page": "hlr_detail",
            "high_level_requirement": {
                "id": hlr.id,
                "description": hlr.description,
                "component": hlr.component.name if hlr.component else None,
                "low_level_requirements": llrs,
            },
        }


def decompose_hlr(hlr, model="", prompt_log_file=""):
    """Run the LLM decomposition agent on an existing HLR, adding LLRs to it.

    Returns the number of LLRs created.
    """
    from agents.decompose.decompose_hlr import decompose

    # Provide sibling HLRs (with component) as context for separation of concerns
    other_hlrs = list(
        HighLevelRequirement.objects.exclude(pk=hlr.pk)
        .select_related("component")
        .values("id", "description", "component__name")
    )

    # Include this HLR's component assignment for scoping
    component_name = hlr.component.name if hlr.component_id else ""

    result = decompose(
        hlr.description,
        other_hlrs=other_hlrs,
        component=component_name,
        dependency_context=hlr.dependency_context,
        model=model,
        prompt_log_file=prompt_log_file,
    )

    with transaction.atomic():
        for llr_data in result.low_level_requirements:
            llr = LowLevelRequirement.objects.create(
                high_level_requirement=hlr,
                description=llr_data.description,
            )
            for v in llr_data.verifications:
                VerificationMethod.objects.create(
                    low_level_requirement=llr,
                    method=v.method,
                    test_name=v.test_name,
                    description=v.description,
                )

    return len(result.low_level_requirements)


@require_POST
def hlr_decompose(request, pk):
    """View wrapper for decompose_hlr."""
    hlr = get_object_or_404(HighLevelRequirement, pk=pk)
    decompose_hlr(hlr)
    return redirect("hlr_detail", pk=hlr.pk)


def assign_hlr_components(model="", prompt_log_file=""):
    """Run the assign_components agent on all HLRs.

    Returns the list of assignment dicts from the agent.
    """
    from agents.design.assign_components import assign_components

    hlrs = HighLevelRequirement.objects.all()
    if not hlrs.exists():
        return []

    hlr_dicts = list(hlrs.values("id", "description"))
    existing = list(Component.objects.values_list("name", flat=True))

    assignments = assign_components(
        hlr_dicts,
        existing_components=existing or None,
        model=model,
        prompt_log_file=prompt_log_file,
    )

    with transaction.atomic():
        for assignment in assignments:
            component, _ = Component.objects.get_or_create(
                name=assignment["component_name"],
            )
            HighLevelRequirement.objects.filter(pk=assignment["hlr_id"]).update(
                component=component,
            )

    return assignments


@require_POST
def hlr_assign_components(request):
    """View wrapper for assign_hlr_components."""
    assign_hlr_components()
    return redirect("requirement_list")


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
