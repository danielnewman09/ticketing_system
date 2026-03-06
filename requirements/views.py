from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
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
    success_url = reverse_lazy("requirement_list")

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
