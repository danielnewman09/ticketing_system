from django.db import models
from django import forms
from .models import Ticket, LowLevelRequirement, HighLevelRequirement


class TicketForm(forms.ModelForm):
    link_llrs = forms.ModelMultipleChoiceField(
        queryset=LowLevelRequirement.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Link Low-Level Requirements",
    )

    class Meta:
        model = Ticket
        fields = ["title", "priority", "complexity", "summary", "ticket_type",
                  "target_components", "languages", "requires_math", "generate_tutorial"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "priority": forms.TextInput(attrs={"class": "form-control"}),
            "complexity": forms.TextInput(attrs={"class": "form-control"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "ticket_type": forms.TextInput(attrs={"class": "form-control"}),
            "target_components": forms.TextInput(attrs={"class": "form-control"}),
            "languages": forms.TextInput(attrs={"class": "form-control"}),
            "requires_math": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "generate_tutorial": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Editing: show already-linked LLRs plus unlinked ones
            linked_ids = self.instance.low_level_requirements.values_list("id", flat=True)
            self.fields["link_llrs"].queryset = LowLevelRequirement.objects.filter(
                models.Q(id__in=linked_ids) | ~models.Q(tickets__isnull=False)
            ).distinct().select_related("high_level_requirement")
            self.fields["link_llrs"].initial = linked_ids
        else:
            # Creating: show only LLRs not linked to any ticket
            self.fields["link_llrs"].queryset = LowLevelRequirement.objects.exclude(
                tickets__isnull=False
            ).select_related("high_level_requirement")


class HighLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = HighLevelRequirement
        fields = ["description"]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class LowLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = LowLevelRequirement
        fields = ["description", "verification", "high_level_requirement"]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "verification": forms.Select(attrs={"class": "form-select"}),
            "high_level_requirement": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "high_level_requirement": "Parent HLR",
        }
