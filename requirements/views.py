from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from .models import HighLevelRequirement, LowLevelRequirement
from .forms import HighLevelRequirementForm, LowLevelRequirementForm


class RequirementListView(ListView):
    model = HighLevelRequirement
    template_name = "requirements/requirement_list.html"
    context_object_name = "hlrs"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("low_level_requirements")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unlinked_llrs"] = LowLevelRequirement.objects.filter(high_level_requirement__isnull=True)
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
    success_url = reverse_lazy("requirement_list")

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
        return context

    def get_initial(self):
        initial = super().get_initial()
        hlr_id = self.request.GET.get("hlr")
        if hlr_id:
            initial["high_level_requirement"] = hlr_id
        return initial


class LLRUpdateView(UpdateView):
    model = LowLevelRequirement
    form_class = LowLevelRequirementForm
    template_name = "requirements/requirement_form.html"
    success_url = reverse_lazy("requirement_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Requirement #{self.object.pk}"
        return context
