from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView

from requirements.models import VerificationMethod
from requirements.forms import (
    VerificationConditionFormSet,
    VerificationActionFormSet,
)


class VerificationDetailView(DetailView):
    model = VerificationMethod
    template_name = "requirements/verification/detail.html"
    context_object_name = "verification"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "low_level_requirement__high_level_requirement",
        ).prefetch_related(
            "conditions__ontology_node",
            "actions__ontology_node",
        )


class VerificationEditView(UpdateView):
    model = VerificationMethod
    fields = ["method", "test_name", "description"]
    template_name = "requirements/verification/edit.html"

    def get_success_url(self):
        return reverse_lazy("verification_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["precondition_formset"] = VerificationConditionFormSet(
                self.request.POST, instance=self.object, prefix="pre",
                queryset=self.object.conditions.filter(phase="pre"),
            )
            context["action_formset"] = VerificationActionFormSet(
                self.request.POST, instance=self.object, prefix="actions",
            )
            context["postcondition_formset"] = VerificationConditionFormSet(
                self.request.POST, instance=self.object, prefix="post",
                queryset=self.object.conditions.filter(phase="post"),
            )
        else:
            context["precondition_formset"] = VerificationConditionFormSet(
                instance=self.object, prefix="pre",
                queryset=self.object.conditions.filter(phase="pre"),
            )
            context["action_formset"] = VerificationActionFormSet(
                instance=self.object, prefix="actions",
            )
            context["postcondition_formset"] = VerificationConditionFormSet(
                instance=self.object, prefix="post",
                queryset=self.object.conditions.filter(phase="post"),
            )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        pre_fs = context["precondition_formset"]
        action_fs = context["action_formset"]
        post_fs = context["postcondition_formset"]

        if pre_fs.is_valid() and action_fs.is_valid() and post_fs.is_valid():
            self.object = form.save()

            # Save preconditions with phase set
            instances = pre_fs.save(commit=False)
            for obj in instances:
                obj.phase = "pre"
                obj.save()
            for obj in pre_fs.deleted_objects:
                obj.delete()

            action_fs.save()

            # Save postconditions with phase set
            instances = post_fs.save(commit=False)
            for obj in instances:
                obj.phase = "post"
                obj.save()
            for obj in post_fs.deleted_objects:
                obj.delete()

            return super().form_valid(form)
        return self.form_invalid(form)
