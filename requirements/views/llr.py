from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import DetailView, CreateView, UpdateView

from ai_assist.mixins import AiAssistMixin
from requirements.models import LowLevelRequirement
from requirements.forms import (
    LowLevelRequirementForm,
    VerificationMethodFormSet,
)

from .common import _build_requirement_graph


class LLRCreateView(CreateView):
    model = LowLevelRequirement
    form_class = LowLevelRequirementForm
    template_name = "requirements/llr/form.html"
    success_url = reverse_lazy("requirement_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Low-Level Requirement"
        if self.request.POST:
            context["verification_formset"] = VerificationMethodFormSet(self.request.POST)
        else:
            context["verification_formset"] = VerificationMethodFormSet()
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
    template_name = "requirements/llr/form.html"

    def get_success_url(self):
        return reverse_lazy("llr_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Requirement #{self.object.pk}"
        if self.request.POST:
            context["verification_formset"] = VerificationMethodFormSet(self.request.POST, instance=self.object)
        else:
            context["verification_formset"] = VerificationMethodFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        verification_formset = context["verification_formset"]
        if verification_formset.is_valid():
            self.object = form.save()
            verification_formset.save()
            return super().form_valid(form)
        return self.form_invalid(form)


class LLRDetailView(AiAssistMixin, DetailView):
    model = LowLevelRequirement
    template_name = "requirements/llr/detail.html"
    context_object_name = "llr"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "high_level_requirement",
        ).prefetch_related(
            "components",
            "verifications__conditions",
            "verifications__actions",
            "triples__subject",
            "triples__object",
        )

    def get_ai_context(self):
        llr = self.object
        lines = [llr.to_prompt_text(include_verifications=True)]
        if llr.high_level_requirement:
            lines.insert(0, f"Parent: {llr.high_level_requirement.to_prompt_text()}")
        comps = list(llr.components.all())
        if comps:
            lines.append(f"Components: {', '.join(c.name for c in comps)}")
        return {
            "page": "llr_detail",
            "context": "\n".join(lines),
        }


def llr_graph_data(request, pk):
    llr = LowLevelRequirement.objects.get(pk=pk)
    return JsonResponse(_build_requirement_graph(llr))
